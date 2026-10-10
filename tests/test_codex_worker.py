"""A decision sidecar ends the interactive worker without losing its session."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/scripts/codex_worker.py'


class CodexWorkerTests(unittest.TestCase):
    def test_a_decision_closes_descendants_as_well_as_the_cli_shim(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, started, escaped = (Path(tmp) / name for name in ('QUESTION-w.md', 'started', 'escaped'))
            grandchild = ('from pathlib import Path; import time; Path(%r).write_text("ready"); '
                          'time.sleep(2); Path(%r).write_text("orphan survived")') % (str(started), str(escaped))
            parent = ('from pathlib import Path; import subprocess,sys,time; '
                      'subprocess.Popen([sys.executable,"-c",%r]); '
                      '\nwhile not Path(%r).exists(): time.sleep(.05)\n'
                      'Path(%r).write_text("Choose A or B."); time.sleep(30)') % (grandchild, str(started), str(question))
            result = subprocess.run([sys.executable, str(SCRIPT), str(question), '--', sys.executable, '-c', parent],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            time.sleep(2.2)
            self.assertFalse(escaped.exists(), 'the CLI child outlived its stopped worker')

    def test_question_stops_the_process_and_preserves_the_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            question = Path(tmp) / 'QUESTION-w.md'
            code = 'from pathlib import Path; import time; Path(%r).write_text("Choose A or B."); time.sleep(30)' % str(question)
            started = time.monotonic()
            result = subprocess.run([sys.executable, str(SCRIPT), str(question), '--', sys.executable, '-c', code],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(time.monotonic() - started, 10)
            self.assertEqual(question.read_text(), 'Choose A or B.')

    def test_normal_exit_status_is_preserved_and_no_question_is_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            question = Path(tmp) / 'QUESTION-w.md'
            result = subprocess.run([sys.executable, str(SCRIPT), str(question), '--', sys.executable, '-c', 'raise SystemExit(7)'],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertFalse(question.exists())


if __name__ == '__main__':
    unittest.main()
