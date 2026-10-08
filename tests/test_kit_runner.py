"""The kit check runs its units at once and reports them in a fixed order, failures in full."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
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


def runner(*units, timing=False, **parallel):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        passed = check_kit.run_units(list(units), timing, **parallel)
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

    def test_a_unit_that_exits_0_before_its_checks_finish_fails_the_run(self):
        # A test module that called os._exit(0) while it was discovered ended its unit with
        # status 0 before any suite ran, and the kit check passed. A unit's last line proves it.
        command = self.suite_unit('True', 2)
        (self.tmp / 'suite/test_kit_probe.py').write_text('import os\nos._exit(0)\n')
        passed, out = runner(('suite', command))
        self.assertFalse(passed, out)
        self.assertIn('unit suite exited 0 without its completion line', out)
        self.assertIn('KIT CHECK: FAIL — 1 of 1 units failed: suite', out)
        passed, out = runner(('suite', self.suite_unit('True', 2)))
        self.assertTrue(passed, out)
        self.assertIn('\nUNIT DONE: suite\n', out)

    def test_git_routing_variables_never_reach_a_unit(self):
        # Inside a hook git exports GIT_INDEX_FILE: a synthetic project's `git add -A` wrote
        # the caller's index. The kit check drops every such variable before any unit starts.
        script = self.tmp / 'env.py'
        script.write_text(UNIT.split('check_kit.ROOT')[0] % str(ROOT / 'scripts/check_kit.py')
                          + 'import os\nprint(sorted(k for k in os.environ if k.startswith("GIT_")))\n')
        env = dict(os.environ, GIT_INDEX_FILE=str(self.tmp / 'index'), GIT_DIR=str(self.tmp),
                   GIT_OBJECT_DIRECTORY=str(self.tmp), GIT_CONFIG_COUNT='0')
        out = subprocess.run([sys.executable, '-B', str(script)], env=env, capture_output=True, text=True).stdout
        self.assertIn("'GIT_CONFIG_COUNT'", out)
        for name in ('GIT_INDEX_FILE', 'GIT_DIR', 'GIT_OBJECT_DIRECTORY'):
            self.assertNotIn(repr(name), out)

    def test_a_suite_under_its_minimum_fails_the_run(self):
        passed, out = runner(('suite', self.suite_unit('True', 3)))
        self.assertFalse(passed)
        self.assertIn('required test suite is incomplete: test_kit_probe', out)

    def test_a_nested_only_failing_module_fails_the_run(self):
        command = self.suite_unit('True', 2)
        nested = self.tmp / 'suite/nested'
        nested.mkdir()
        (nested / '__init__.py').write_text('')
        (nested / 'test_nested_failure.py').write_text(PROBE % 'False')
        passed, out = runner(('suite', command))
        self.assertFalse(passed, out)
        self.assertIn('nested.test_nested_failure.Probe.test_maybe', out)
        self.assertIn('probe failure message', out)

    def test_excluded_modules_are_not_imported_even_in_a_nested_package(self):
        command = self.suite_unit('True', 2)
        nested = self.tmp / 'suite/nested'
        nested.mkdir()
        (nested / '__init__.py').write_text('')
        for directory in (self.tmp / 'suite', nested):
            (directory / 'test_excluded.py').write_text('raise AssertionError("excluded module imported")\n')
        (nested / 'test_nested_pass.py').write_text(PROBE % 'True')
        script = self.tmp / 'unit.py'
        script.write_text(script.read_text().replace(
            "sys.exit(check_kit.unit", "check_kit.NOT_ON_WINDOWS = {'suite': {'test_excluded': 'fixture'}}\n"
            "check_kit.REQUIRED_SUITES['suite']['test_excluded'] = 1\nsys.exit(check_kit.unit"))
        passed, out = runner(('suite', command))
        self.assertTrue(passed, out)
        self.assertIn('suite ran 4 tests', out)

    def test_the_wrapper_tries_python_when_python3_cannot_run(self):
        import shlex
        project = self.tmp / 'kit'
        (project / 'scripts').mkdir(parents=True)
        shutil.copyfile(ROOT / 'scripts/check.sh', project / 'scripts/check.sh')
        (project / 'scripts/check_kit.py').write_text('import sys; print("gate ran", sys.argv[1:])\n')
        shims = self.tmp / 'bin'
        shims.mkdir()
        (shims / 'python3').write_text('#!/bin/sh\nexit 126\n')
        (shims / 'python').write_text('#!/bin/sh\nexec %s "$@"\n' % shlex.quote(sys.executable))
        for path in shims.iterdir():
            path.chmod(0o755)
        result = subprocess.run(['sh', str(project / 'scripts/check.sh'), '--timing'], capture_output=True,
                                text=True, env=dict(os.environ, PATH=str(shims) + os.pathsep + os.environ['PATH']))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("gate ran ['--timing']", result.stdout)

    def test_units_print_in_the_given_order_whichever_ends_first(self):
        slow = [sys.executable, '-c', 'import time; time.sleep(1); print("slow output\\nUNIT DONE: slow")']
        fast = [sys.executable, '-c', 'print("fast output\\nUNIT DONE: fast")']
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

    def test_what_a_unit_could_not_run_is_repeated_under_the_summary(self):
        # A test that cannot run on this host (no unprivileged mount namespace, always on
        # macOS) passed silently: its NOT RUN line is collected and printed after the TIME
        # lines, so the end of the output says what this host did not run.
        said = [sys.executable, '-c', 'import sys; sys.stderr.write("noise\\nNOT RUN: probe a (no b here)\\n"); '
                'print("UNIT DONE: said")']
        quiet = [sys.executable, '-c', 'print("quiet output\\nUNIT DONE: quiet")']
        passed, out = runner(('said', said), ('quiet', quiet))
        self.assertTrue(passed, out)
        tail = out[out.rindex('TIME: '):]
        self.assertIn('\nNOT RUN: probe a (no b here)\n', tail)
        self.assertEqual(out.count('NOT RUN: probe a'), 2, out)

    def test_timing_prints_a_table_of_units_phases_and_tests_at_the_end(self):
        passed, out = runner(('suite', self.suite_unit('True', 2)),
                             ('other', [sys.executable, '-c', 'print("other output\\nUNIT DONE: other")']),
                             timing=True)
        self.assertTrue(passed, out)
        table = out[out.index('TIMING'):]
        self.assertGreater(out.index('TIMING'), out.index('other output'))
        self.assertRegex(table, r'\n +[0-9.]+ s  suite\n')
        self.assertRegex(table, r'\n +[0-9.]+ s    suite ran 2 tests')
        self.assertRegex(table, r'\n +[0-9.]+ s    test test_kit_probe\.Probe\.test_passes\n')
        self.assertRegex(table, r'\n +[0-9.]+ s  other\n')
        self.assertNotIn('TIME: ', out)

    def test_the_units_at_once_follow_the_cpu_count(self):
        # Three units at once on a 3-CPU runner took 300 s each and hit their timeouts.
        self.assertEqual([check_kit.degree(cpus, 3) for cpus in (1, 2, 3, 4, 7, 8, 64)],
                         [1, 1, 1, 2, 2, 3, 3])
        self.assertEqual(check_kit.degree(5, 1), 1)
        with unittest.mock.patch.dict(os.environ, {'MYAGENTKIT_TEST_TIMEOUT_SCALE': '1.5'}):
            self.assertEqual(check_kit.limit(300), 450)

    def test_units_run_that_many_at_once_with_their_timeouts_scaled_by_it(self):
        unit = [sys.executable, '-c', 'import os, time; s = time.time(); time.sleep(0.5); '
                'print("span", os.environ["MYAGENTKIT_TEST_TIMEOUT_SCALE"], s, time.time()); '
                'import sys; print("UNIT DONE: " + sys.argv[1])']
        for parallel, scale, overlap in ((1, 2.0, False), (2, 4.0, True)):
            with self.subTest(parallel=parallel), \
                    unittest.mock.patch.dict(os.environ, {'MYAGENTKIT_TEST_TIMEOUT_SCALE': '2'}):
                passed, out = runner(('a', unit + ['a']), ('b', unit + ['b']), parallel=parallel)
                self.assertTrue(passed, out)
                spans = [line.split()[1:] for line in out.splitlines() if line.startswith('span ')]
                self.assertEqual([float(s) for s, _, _ in spans], [scale, scale])
                (_, a_start, a_end), (_, b_start, b_end) = [map(float, s) for s in spans]
                self.assertEqual(b_start < a_end and a_start < b_end, overlap, out)

    def test_path_without_drops_only_the_named_commands(self):
        # A directory without them stays as it is; one with them becomes links to the rest.
        # path_without serves the POSIX lock cases only; Windows' which finds PATHEXT names alone.
        if os.name == 'nt':
            sys.stderr.write('\nNOT RUN: %s (POSIX only: commands without an extension)\n' % self.id())
            return
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
