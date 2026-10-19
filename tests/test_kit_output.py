"""The kit check prints a passing suite as one line and a failing suite as its failures only."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
import unittest.mock

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

    def test_run_reads_a_childs_output_as_utf8(self):
        # Without UTF-8 mode (a test file run directly on Windows) the ANSI code page read the
        # child's em dash as three letters; under the locale suites an encoding-less read is an
        # error (#275).
        out = check_kit.run([sys.executable, '-c', 'import os; os.write(1, b"ok \\xe2\\x80\\x94 done\\n")'])
        self.assertEqual(out.splitlines(), ['ok — done'])

    def test_the_summary_totals_the_tests_this_platform_did_not_run(self):
        # One NOT RUN line per test was easy to scroll past: the summary adds them up, with the
        # suites left out on this host; a NOT RUN line of another check is no test (#231), and
        # neither is one a passing test prints of its own (it ran: counted once, in M).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'suite').mkdir()
            (root / 'suite/test_kit_probe_skip.py').write_text(
                PROBE.replace('    def test_maybe', '    @unittest.skip("probe platform")\n    def test_maybe')
                % 'True' + '    test_maybe._kit_platform_skip = True\n', encoding='utf-8')
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                check_kit.run_tests(root, 'suite', {'test_kit_probe_skip': 1})
        printed = ('NOT RUN: suite.Probe.test_posix (POSIX only)\n' + said.getvalue()
                   + 'NOT RUN: shellcheck -s sh (not installed)\n')
        unit = [sys.executable, '-c', 'import sys; sys.stdout.write(%r + "UNIT DONE: u\\n")' % printed]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertTrue(check_kit.run_units([('u', unit)], said=['NOT RUN: tests/test_x on native Windows'],
                                                left_out=5))
        self.assertIn("\nNOT RUN: 6 of 7 tests of this run's suites on this platform (1 declared platform skips, "
                      "5 in suites that do not run here, counted by their REQUIRED_SUITES number)\n", out.getvalue())
        # A suite left out here counts in the tier that holds it.
        off_host = {'tests': {'test_check_gate': 'a reason'}}
        for argv, left_out in (([], check_kit.REQUIRED_SUITES['tests']['test_check_gate']), (['--slow'], 0)):
            with self.subTest(argv=argv), unittest.mock.patch.object(check_kit, 'NOT_ON_WINDOWS', off_host), \
                    unittest.mock.patch.object(check_kit, 'run_units', return_value=False) as units, \
                    unittest.mock.patch.object(sys, 'argv', ['check_kit.py', *argv]), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(check_kit.main(), 1)
                self.assertEqual(units.call_args.kwargs['left_out'], left_out)


if __name__ == '__main__':
    unittest.main()
