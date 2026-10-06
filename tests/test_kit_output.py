"""The kit check prints a passing suite as one line and a failing suite in full."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_kit', ROOT / 'scripts/check_kit.py')
check_kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_kit)

PROBE = '''import unittest
class Probe(unittest.TestCase):
    def test_passes(self):
        pass
    def test_maybe(self):
        self.assertTrue(%s, "probe failure message")
'''


class KitOutputTests(unittest.TestCase):
    def test_a_pass_is_one_line_and_a_failure_is_the_whole_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'quiet').mkdir()
            (root / 'quiet/test_kit_probe_pass.py').write_text(PROBE % 'True')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                check_kit.run_tests(root, 'quiet', {'test_kit_probe_pass': 2})
            self.assertEqual(out.getvalue(), 'PASS: quiet ran 2 tests, each suite at or above its'
                                             ' minimum (test_kit_probe_pass 2)\n')
            (root / 'loud').mkdir()
            (root / 'loud/test_kit_probe_fail.py').write_text(PROBE % 'False')
            with self.assertRaises(RuntimeError) as raised:
                check_kit.run_tests(root, 'loud', {'test_kit_probe_fail': 2})
            log = str(raised.exception)
            self.assertIn('test_passes', log)
            self.assertIn('... ok', log)
            self.assertIn('probe failure message', log)


if __name__ == '__main__':
    unittest.main()
