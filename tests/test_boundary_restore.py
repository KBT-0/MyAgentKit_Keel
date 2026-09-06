"""Interrupt the shipped existing-file example and preserve uncommitted owner bytes."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest


class BoundaryRestoreTests(unittest.TestCase):
    def test_existing_file_restores_on_exit_and_signals_before_backup_cleanup(self):
        template = (Path(__file__).resolve().parents[1] /
                    'core/scripts/boundary_selftests.sh').read_text()
        example = '\n'.join(line[4:] for line in template.splitlines() if line.startswith('# | '))
        self.assertTrue(example.strip(), 'missing executable existing-file restoration example')
        for interruption in (None, signal.SIGINT, signal.SIGTERM):
            with self.subTest(interruption=interruption), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / 'src/domain/existing.py'
                source.parent.mkdir(parents=True)
                source.write_bytes(b'committed original\n')
                for args in (['init', '-q'], ['add', '.'],
                             ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                              '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                              'commit', '-qm', 'fixture']):
                    subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)
                original = b'Uncommitted owner content.\nPreserve these exact bytes.\n'
                source.write_bytes(original)
                source.chmod(0o640)
                scratch = root / 'scratch'
                scratch.mkdir()
                gate = root / 'check.sh'
                gate.write_text('''#!/bin/sh
if [ "${1:-}" = --self-test ]; then
  work=$(mktemp -d)
  trap 'rm -rf "$work"' EXIT INT TERM
  st_fail=0
''' + example + '''
  : > continued
  exit "$st_fail"
fi
grep -q 'myapp.web' src/domain/existing.py || exit 0
if [ "$INTERRUPT" = yes ]; then
  : > ready
  while :; do sleep 1; done
fi
echo 'FAIL [boundary]: the domain layer imports the web layer:'
exit 1
''')
                child = subprocess.Popen(['sh', str(gate), '--self-test'], cwd=root,
                                         env=dict(os.environ, TMPDIR=str(scratch),
                                                  INTERRUPT='yes' if interruption else 'no'),
                                         start_new_session=True, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
                try:
                    if interruption:
                        deadline = time.monotonic() + 5
                        while not (root / 'ready').exists() and time.monotonic() < deadline:
                            if child.poll() is not None:
                                break
                            time.sleep(0.01)
                        self.assertTrue((root / 'ready').exists(), 'injection did not reach the gate')
                        os.killpg(child.pid, interruption)
                    stdout, stderr = child.communicate(timeout=5)
                    self.assertEqual(child.returncode, 128 + interruption if interruption else 0,
                                     (stdout + stderr).decode(errors='replace'))
                    self.assertEqual(source.read_bytes(), original)
                    self.assertEqual(source.stat().st_mode & 0o777, 0o640)
                    self.assertEqual(list(scratch.iterdir()), [])
                    self.assertEqual((root / 'continued').exists(), interruption is None)
                finally:
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGKILL)
                    child.communicate()


if __name__ == '__main__':
    unittest.main()
