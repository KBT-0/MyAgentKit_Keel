"""Interrupt the shipped existing-file example: the checkout is never the one it changes."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest


class BoundaryRestoreTests(unittest.TestCase):
    def test_existing_file_example_runs_in_a_disposable_copy(self):
        # The example once overwrote the file in the checkout and restored it from traps:
        # a concurrent `git add -A` staged the injection, and SIGKILL left it there.
        template = (Path(__file__).resolve().parents[1] /
                    'core/scripts/boundary_selftests.sh').read_text()
        example = '\n'.join(line[4:] for line in template.splitlines() if line.startswith('# | '))
        self.assertTrue(example.strip(), 'missing executable existing-file example')
        for interruption in (None, signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
            with self.subTest(interruption=interruption), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / 'project'
                source = root / 'src/domain/existing.py'
                source.parent.mkdir(parents=True)
                source.write_bytes(b'committed original\n')
                (root / 'scripts').mkdir()
                gate = root / 'scripts/check.sh'
                gate.write_text('''#!/bin/sh
cd "$(dirname "$0")/.."
if [ "${1:-}" = --self-test ]; then
  work=$(mktemp -d)
  trap 'rm -rf "$work"' EXIT INT TERM
  st_fail=0
''' + example + '''
  : > "$CONTINUED"
  exit "$st_fail"
fi
grep -q 'myapp.web' src/domain/existing.py || exit 0
if [ "$INTERRUPT" = yes ]; then
  : > "$READY"
  while :; do sleep 1; done
fi
echo 'FAIL [boundary]: the domain layer imports the web layer:'
exit 1
''')
                git = lambda *args: subprocess.run(['git', *args], cwd=root, check=True,
                                                   capture_output=True, text=True).stdout
                git('init', '-q')
                git('add', '.')
                git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                    'commit', '-qm', 'fixture')
                original = b'Uncommitted owner content.\nPreserve these exact bytes.\n'
                source.write_bytes(original)
                source.chmod(0o640)
                status = git('status', '--porcelain')
                scratch, ready, continued = (Path(tmp) / name for name in ('scratch', 'ready', 'continued'))
                scratch.mkdir()
                child = subprocess.Popen(['sh', str(gate), '--self-test'], cwd=root,
                                         env=dict(os.environ, TMPDIR=str(scratch), READY=str(ready),
                                                  CONTINUED=str(continued),
                                                  INTERRUPT='yes' if interruption else 'no'),
                                         start_new_session=True, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
                try:
                    if interruption:
                        deadline = time.monotonic() + 5
                        while not ready.exists() and time.monotonic() < deadline:
                            if child.poll() is not None:
                                break
                            time.sleep(0.01)
                        self.assertTrue(ready.exists(), 'injection did not reach the gate')
                        # Mid-injection, the checkout is untouched: the copy took the edit.
                        self.assertEqual(source.read_bytes(), original)
                        os.killpg(child.pid, interruption)
                    stdout, stderr = child.communicate(timeout=5)
                    self.assertEqual(child.returncode,
                                     -interruption if interruption == signal.SIGKILL
                                     else 128 + interruption if interruption else 0,
                                     (stdout + stderr).decode(errors='replace'))
                    self.assertEqual(source.read_bytes(), original)
                    self.assertEqual(source.stat().st_mode & 0o777, 0o640)
                    self.assertEqual(git('status', '--porcelain'), status)
                    # Traps remove the copy; only SIGKILL leaves it, in TMPDIR, not the checkout.
                    if interruption != signal.SIGKILL:
                        self.assertEqual(list(scratch.iterdir()), [])
                    self.assertEqual(continued.exists(), interruption is None)
                    # check.sh --self-test counts a boundary self-test as run only by this line.
                    if interruption is None:
                        self.assertIn('\n  ok   — ', '\n' + stdout.decode())
                finally:
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGKILL)
                    child.communicate()


if __name__ == '__main__':
    unittest.main()
