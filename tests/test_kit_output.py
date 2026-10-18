"""The kit check prints a passing suite as one line and a failing suite as its failures only."""
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
    def test_a_pass_is_one_line_and_a_failure_is_only_what_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'quiet').mkdir()
            (root / 'quiet/test_kit_probe_pass.py').write_text(PROBE % 'True', encoding='utf-8')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                check_kit.run_tests(root, 'quiet', {'test_kit_probe_pass': 2})
            self.assertEqual(out.getvalue(), 'PASS: quiet ran 2 tests, each suite at or above its'
                                             ' minimum (test_kit_probe_pass 2)\n')
            (root / 'loud').mkdir()
            (root / 'loud/test_kit_probe_fail.py').write_text(PROBE % 'False', encoding='utf-8')
            with self.assertRaises(RuntimeError) as raised:
                check_kit.run_tests(root, 'loud', {'test_kit_probe_fail': 2})
            log = str(raised.exception)
            # The failing test's block and the count; a passing test has no line (#111).
            self.assertIn('FAIL: test_maybe (test_kit_probe_fail.Probe.test_maybe)', log)
            self.assertIn('probe failure message', log)
            self.assertIn('Ran 2 tests', log)
            self.assertNotIn('test_passes', log)
            self.assertNotIn('... ok', log)


if __name__ == '__main__':
    unittest.main()
