"""The kit check runs its units at once and reports them in a fixed order, failures in full."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import shutil
import sys
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
# One unit run the way the kit check runs it, against a suite of its own.
UNIT = '''import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('check_kit', %r)
check_kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_kit)
check_kit.ROOT = Path(%r)
check_kit.REQUIRED_SUITES = {'suite': {'test_kit_probe': %d}}
sys.exit(check_kit.unit('suite', False, *sys.argv[2:3]))
'''


def runner(*units, timing=False):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        passed = check_kit.run_units(list(units), timing)
    return passed, out.getvalue()


class KitRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def suite_unit(self, condition, minimum):
        (self.tmp / 'suite').mkdir(exist_ok=True)
        (self.tmp / 'suite/test_kit_probe.py').write_text(PROBE % condition)
        script = self.tmp / 'unit.py'
        script.write_text(UNIT % (str(ROOT / 'scripts/check_kit.py'), str(self.tmp), minimum))
        return [sys.executable, '-B', '-u', str(script)]

    def test_a_failing_suite_is_printed_whole_and_fails_the_run(self):
        passed, out = runner(('suite', self.suite_unit('False', 2)))
        self.assertFalse(passed)
        self.assertIn('test_passes', out)
        self.assertIn('... ok', out)
        self.assertIn('probe failure message', out)
        self.assertIn('KIT CHECK: FAIL — 1 of 1 units failed: suite', out)
        passed, out = runner(('suite', self.suite_unit('True', 2)))
        self.assertTrue(passed, out)

    def test_a_suite_under_its_minimum_fails_the_run(self):
        passed, out = runner(('suite', self.suite_unit('True', 3)))
        self.assertFalse(passed)
        self.assertIn('required test suite is incomplete: test_kit_probe', out)

    def test_units_print_in_the_given_order_whichever_ends_first(self):
        slow = [sys.executable, '-c', 'import time; time.sleep(1); print("slow output")']
        fast = [sys.executable, '-c', 'print("fast output")']
        failing = [sys.executable, '-c', 'import sys; print("failing output"); sys.exit(3)']
        passed, out = runner(('slow', slow), ('failing', failing), ('fast', fast))
        self.assertFalse(passed)
        self.assertLess(out.index('slow output'), out.index('failing output'))
        self.assertLess(out.index('failing output'), out.index('fast output'))
        self.assertIn('failed: failing', out)
        # One line per unit with its seconds, after every unit's output, and no table.
        lines = out.splitlines()
        times = [n for n, line in enumerate(lines) if line.startswith('TIME: ')]
        self.assertEqual([re.sub(r'[0-9.]+ s', 'N s', lines[n]) for n in times],
                         ['TIME: N s  slow', 'TIME: N s  failing (FAILED)', 'TIME: N s  fast'])
        self.assertGreater(times[0], lines.index('fast output'))
        self.assertNotIn('TIMING', out)

    def test_timing_prints_a_table_of_units_phases_and_tests_at_the_end(self):
        passed, out = runner(('suite', self.suite_unit('True', 2)),
                             ('other', [sys.executable, '-c', 'print("other output")']), timing=True)
        self.assertTrue(passed, out)
        table = out[out.index('TIMING'):]
        self.assertGreater(out.index('TIMING'), out.index('other output'))
        self.assertRegex(table, r'\n +[0-9.]+ s  suite\n')
        self.assertRegex(table, r'\n +[0-9.]+ s    suite ran 2 tests')
        self.assertRegex(table, r'\n +[0-9.]+ s    test test_kit_probe\.Probe\.test_passes\n')
        self.assertRegex(table, r'\n +[0-9.]+ s  other\n')
        self.assertNotIn('TIME: ', out)

    def test_path_without_drops_only_the_named_commands(self):
        # A directory without them stays as it is; one with them becomes links to the rest.
        plain, mixed = self.tmp / 'plain', self.tmp / 'mixed'
        for directory in (plain, mixed):
            directory.mkdir()
        for path in (plain / 'kept', mixed / 'dropped', mixed / 'other'):
            path.write_text('#!/bin/sh\n')
            path.chmod(0o755)
        (mixed / 'dangling').symlink_to(self.tmp / 'absent')
        path = check_kit.path_without(os.pathsep.join((str(plain), str(mixed), str(self.tmp / 'none'))),
                                      lambda name: name == 'dropped', self.tmp / 'links')
        entries = path.split(os.pathsep)
        self.assertEqual(entries[0], str(plain))
        self.assertEqual(len(entries), 2)
        self.assertIsNone(shutil.which('dropped', path=path))
        self.assertEqual(os.path.realpath(shutil.which('other', path=path)), str((mixed / 'other').resolve()))
        self.assertEqual(sorted(os.listdir(entries[1])), ['other'])


if __name__ == '__main__':
    unittest.main()
