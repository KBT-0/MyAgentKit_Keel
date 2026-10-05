"""Execute the shipped boundary-test example against real and misleading gate failures."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BoundaryExampleTests(unittest.TestCase):
    def setUp(self):
        # A caller that ignores SIGINT (a `&` job of a non-interactive shell, nohup) passes that
        # on to every child, an ignored signal cannot be trapped, and the interrupted cases
        # failed only there. Each test starts from Python's own default, its children from SIG_DFL.
        self.addCleanup(signal.signal, signal.SIGINT, signal.signal(signal.SIGINT, signal.default_int_handler))

    def test_example_requires_a_green_baseline_and_the_intended_failure(self):
        template = (ROOT / 'core/scripts/boundary_selftests.sh').read_text()
        example = '\n'.join(line[4:] for line in template.splitlines() if line.startswith('#   '))
        self.assertTrue(example.strip())
        for case in ('intended', 'baseline_red', 'wrong_reason', 'missing_gate', 'misleading_success', 'collision'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                injection = root / 'src/domain/.selftest.py'
                if case == 'collision':
                    injection.parent.mkdir(parents=True)
                    injection.write_text('Uncommitted owner content.\n')
                gate = root / 'check.sh'
                gate.write_text('''#!/bin/sh
if [ "${1:-}" = --self-test ]; then
  st_fail=0
''' + example + '''
  exit "$st_fail"
fi
[ "$CASE" != collision ] || exit 0
[ "$CASE" != baseline_red ] || { echo 'FAIL: unrelated baseline'; exit 1; }
[ -f src/domain/.selftest.py ] || exit 0
case "$CASE" in
  intended) echo 'FAIL [boundary]: the domain layer imports the web layer:'; exit 1 ;;
  wrong_reason) echo 'FAIL: unrelated build error'; exit 1 ;;
  misleading_success) echo 'FAIL [boundary]: the domain layer imports the web layer:'; exit 0 ;;
  missing_gate) exit 0 ;;
esac
''')
                result = subprocess.run(['sh', str(gate), '--self-test'], cwd=root,
                                        env=dict(os.environ, CASE=case), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0 if case == 'intended' else 1,
                                 result.stdout + result.stderr)
                if case == 'collision':
                    self.assertEqual(injection.read_text(), 'Uncommitted owner content.\n')
                else:
                    self.assertFalse(injection.exists())

    def test_example_removes_its_injection_when_interrupted(self):
        # The injection was removed by a plain `rm -f` after the gate returned: SIGINT during
        # the injected run left src/domain/.selftest.py in the checkout, where `git add -A`
        # staged it and the next self-test refused the path as owner content.
        template = (ROOT / 'core/scripts/boundary_selftests.sh').read_text()
        example = '\n'.join(line[4:] for line in template.splitlines() if line.startswith('#   '))
        for interruption in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(interruption=interruption), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ready = root / 'ready'
                gate = root / 'check.sh'
                gate.write_text('''#!/bin/sh
trap 'exit 130' INT
trap 'exit 143' TERM
if [ "${1:-}" = --self-test ]; then
  st_fail=0
''' + example + '''
  exit "$st_fail"
fi
[ -f src/domain/.selftest.py ] || exit 0
: > "$READY"
while :; do sleep 1; done
''')
                child = subprocess.Popen(['sh', str(gate), '--self-test'], cwd=root, start_new_session=True,
                                         env=dict(os.environ, READY=str(ready)),
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    deadline = time.monotonic() + 5
                    while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(ready.exists(), 'the injected run did not start')
                    os.killpg(child.pid, interruption)
                    child.communicate(timeout=5)
                    self.assertEqual(child.returncode, 128 + interruption)
                    self.assertFalse((root / 'src/domain/.selftest.py').exists(), 'the injection was left behind')
                finally:
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGKILL)
                    child.communicate()

    def test_the_interrupted_cases_pass_under_a_caller_that_ignores_sigint(self):
        # A `&` job of a non-interactive shell, or nohup, starts with SIGINT ignored, which a
        # shell cannot trap: the interrupted cases failed only there, as timeouts.
        result = subprocess.run(
            [sys.executable, '-m', 'unittest',
             'test_boundary_example.BoundaryExampleTests.test_example_removes_its_injection_when_interrupted',
             'test_boundary_restore.BoundaryRestoreTests.test_existing_file_example_runs_in_a_disposable_copy'],
            cwd=Path(__file__).resolve().parent, capture_output=True, text=True, timeout=300,
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN))
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
