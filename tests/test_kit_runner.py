"""The kit check runs its units at once and reports them in a fixed order, failures in full."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
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

    def test_declared_platform_skips_do_not_satisfy_suite_minimums(self):
        for declared, minimum, expected in ((True, 1, True), (True, 2, False), (False, 1, False)):
            with self.subTest(declared=declared, minimum=minimum):
                command = self.suite_unit('True', minimum)
                source = PROBE % 'True'
                source = source.replace('    def test_maybe',
                                        '    @unittest.skip("platform probe")\n    def test_maybe')
                if declared:
                    source += '    test_maybe._kit_platform_skip = True\n'
                (self.tmp / 'suite/test_kit_probe.py').write_text(source)
                passed, out = runner(('suite', command))
                self.assertEqual(passed, expected, out)
                if declared:
                    self.assertIn('NOT RUN: test_kit_probe.Probe.test_maybe', out)

    def test_a_nested_only_failing_module_fails_the_run(self):
        command = self.suite_unit('True', 2)
        nested = self.tmp / 'suite/nested'
        nested.mkdir()
        (nested / '__init__.py').write_text('')
        (nested / 'test_nested_failure.py').write_text(PROBE % 'False')
        passed, out = runner(('suite', command))
        self.assertFalse(passed, out)
        self.assertIn('nested test modules are not supported: nested/test_nested_failure.py', out)

    def test_a_linked_package_with_failing_tests_is_refused(self):
        command = self.suite_unit('True', 2)
        package = self.tmp / 'package'
        package.mkdir()
        (package / '__init__.py').write_text('')
        (package / 'test_linked_failure.py').write_text(PROBE % 'False')
        link = self.tmp / 'suite/linked'
        link.symlink_to(package, target_is_directory=True)
        passed, out = runner(('suite', command))
        self.assertFalse(passed, out)
        self.assertIn('linked test directories are not supported: linked', out)

    def test_reparse_directories_are_refused_without_is_junction(self):
        folder = self.tmp / 'suite'
        folder.mkdir()
        (folder / 'linked').mkdir()
        original = Path.lstat

        def lstat(path, *args, **kwargs):
            if path.name == 'linked':
                return unittest.mock.Mock(st_file_attributes=0x400, st_reparse_tag=0xA0000003)
            return original(path, *args, **kwargs)

        # Python 3.10/3.11 have lstat's Windows attributes but no Path.is_junction.
        with unittest.mock.patch.object(Path, 'is_symlink', return_value=False), \
                unittest.mock.patch.object(Path, 'is_junction', None, create=True), \
                unittest.mock.patch.object(Path, 'lstat', lstat):
            with self.assertRaisesRegex(RuntimeError, 'linked test directories.*linked'):
                check_kit.discover(folder)

    def test_cloud_reparse_directories_allow_discovery(self):
        folder = self.tmp / 'suite'
        folder.mkdir()
        (folder / 'test_probe.py').write_text(PROBE % 'True')
        original = Path.lstat

        def lstat(path, *args, **kwargs):
            if path == folder:
                return unittest.mock.Mock(st_file_attributes=0x400, st_reparse_tag=0x9000001A)
            return original(path, *args, **kwargs)

        for modern in (False, True):
            with self.subTest(is_junction=modern), \
                    unittest.mock.patch.object(Path, 'is_symlink', return_value=False), \
                    unittest.mock.patch.object(Path, 'is_junction', return_value=False, create=True), \
                    unittest.mock.patch.object(Path, 'lstat', lstat):
                if not modern:
                    Path.is_junction = None
                suite, counts = check_kit.discover(folder)
                self.assertEqual(counts, {'test_probe': 2})
                self.assertTrue(unittest.TextTestRunner(stream=io.StringIO()).run(suite).wasSuccessful())

    def test_an_unreadable_test_directory_refuses_discovery(self):
        def walk(folder, **kwargs):
            if 'onerror' in kwargs:
                kwargs['onerror'](PermissionError('unreadable test directory'))
            return iter(())

        with unittest.mock.patch.object(check_kit.os, 'walk', walk):
            with self.assertRaisesRegex(PermissionError, 'unreadable test directory'):
                check_kit.discover(self.tmp)

    def test_a_passing_nested_module_is_refused_before_import(self):
        command = self.suite_unit('True', 2)
        nested = self.tmp / 'suite/nested'
        nested.mkdir()
        (nested / '__init__.py').write_text('print("nested package imported")\n')
        (nested / 'test_extra.py').write_text(PROBE % 'True')
        passed, out = runner(('suite', command))
        self.assertFalse(passed, out)
        self.assertIn('nested test modules are not supported: nested/test_extra.py', out)
        self.assertNotIn('nested package imported', out)

    def test_a_nested_module_without_a_package_is_refused(self):
        command = self.suite_unit('True', 2)
        nested = self.tmp / 'suite/nested/deeper'
        nested.mkdir(parents=True)
        (nested / 'test_extra.py').write_text(PROBE % 'True')
        passed, out = runner(('suite', command))
        self.assertFalse(passed, out)
        self.assertIn('nested test modules are not supported: nested/deeper/test_extra.py', out)

    def test_excluded_modules_are_not_imported(self):
        command = self.suite_unit('True', 2)
        (self.tmp / 'suite/test_excluded.py').write_text('raise AssertionError("excluded module imported")\n')
        script = self.tmp / 'unit.py'
        script.write_text(script.read_text().replace(
            "sys.exit(check_kit.unit", "check_kit.NOT_ON_WINDOWS = {'suite': {'test_excluded': 'fixture'}}\n"
            "check_kit.REQUIRED_SUITES['suite']['test_excluded'] = 1\nsys.exit(check_kit.unit"))
        passed, out = runner(('suite', command))
        self.assertTrue(passed, out)
        self.assertIn('suite ran 2 tests', out)
        nested = self.tmp / 'suite/nested'
        nested.mkdir()
        (nested / 'test_excluded.py').write_text('raise AssertionError("excluded module imported")\n')
        passed, out = runner(('suite', command))
        self.assertFalse(passed, out)
        self.assertIn('nested test modules are not supported: nested/test_excluded.py', out)
        self.assertNotIn('excluded module imported', out)

    def test_the_wrapper_tries_python_when_python3_cannot_run(self):
        import shlex
        project = self.tmp / 'kit'
        (project / 'scripts').mkdir(parents=True)
        shutil.copyfile(ROOT / 'scripts/check.sh', project / 'scripts/check.sh')
        (project / 'scripts/check_kit.py').write_text(
            'import os, sys\nfrom pathlib import Path\nprint("gate ran", sys.argv[1:])\n'
            'Path(os.environ["KIT_CHECK_PASSED"]).touch()\n')
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

    def test_completion_recovers_its_missing_marker_directory_and_refuses_a_file(self):
        # The full native run completed every unit, but its temporary marker directory
        # was gone by then. A PASS line followed by a failed marker write is not a pass.
        for obstacle in (False, True):
            with self.subTest(obstacle=obstacle):
                owner = self.tmp / ('marker-file' if obstacle else 'missing-marker')
                if obstacle:
                    owner.write_text('keep this file')
                marker = owner / 'passed'
                out = io.StringIO()
                with unittest.mock.patch.object(check_kit, '_PASSED_FILE', str(marker)), \
                        unittest.mock.patch.object(check_kit, 'check_syntax'), \
                        unittest.mock.patch.object(check_kit, 'check_release'), \
                        unittest.mock.patch.object(check_kit, 'run', return_value='packaged source matches'), \
                        unittest.mock.patch.object(check_kit, 'run_units', return_value=True), \
                        unittest.mock.patch.object(sys, 'argv', ['check_kit.py']), \
                        contextlib.redirect_stdout(out):
                    if obstacle:
                        with self.assertRaises(OSError):
                            check_kit.main()
                        self.assertNotIn('KIT CHECK: PASS', out.getvalue())
                        self.assertEqual(owner.read_text(), 'keep this file')
                    else:
                        self.assertEqual(check_kit.main(), 0)
                        self.assertTrue(marker.is_file())
                        self.assertIn('KIT CHECK: PASS', out.getvalue().splitlines())

    def cancel_wrapper(self, early=False):
        if os.name == 'nt':
            sys.stderr.write('\nNOT RUN: %s (POSIX only: signals to the wrapper PID)\n' % self.id())
            return
        # Keep the real startup, handlers, run_units and unit. Only main selects a small suite.
        source = (ROOT / 'scripts/check_kit.py').read_text()
        source = source.replace('ROOT = Path(__file__).resolve().parents[1]', 'ROOT = Path(%r)' % str(ROOT))
        begin, end = source.split('\ndef main():', 1)
        end = end[end.index('\nif __name__ == "__main__":'):]
        for sig, status in ((signal.SIGTERM, 143), (signal.SIGINT, 130)):
            with self.subTest(signal=sig):
                project = self.tmp / sig.name
                (project / 'scripts').mkdir(parents=True)
                (project / 'suite').mkdir()
                shutil.copyfile(ROOT / 'scripts/check.sh', project / 'scripts/check.sh')
                (project / 'suite/test_kit_probe.py').write_text('''import os, time, unittest
from pathlib import Path
class Probe(unittest.TestCase):
    def test_wait(self):
        Path('unit-pid').write_text(str(os.getpid()))
        Path('ready').touch()
        time.sleep(30)
        Path('unit-completed').touch()
''')
                startup = ("import os, sys, time\nfrom pathlib import Path\n"
                           "if '--unit' not in sys.argv:\n    Path('pid').write_text(str(os.getpid()))\n")
                if early:
                    # Before check_kit even imports signal: ignored SIGINT used to vanish here.
                    startup += "Path('ready').touch()\ntime.sleep(30)\nPath('startup-completed').touch()\n"
                (project / 'scripts/check_kit.py').write_text(startup + begin + '''
def main():
    global ROOT, REQUIRED_SUITES
    ROOT = Path(__file__).resolve().parents[1]
    REQUIRED_SUITES = {'suite': {'test_kit_probe': 1}}
    if '--unit' in sys.argv:
        return unit('suite', False)
    Path('cache').write_text(_PYCACHE)
    atexit.register(Path('stopped').touch)
    command = [sys.executable, '-B', '-u', __file__, '--unit', 'suite']
    pending = [sys.executable, '-c', 'import time; from pathlib import Path; time.sleep(30); '
               'Path("pending-completed").touch()']
    run_units([('suite', command), ('pending', pending)], parallel=1)
    Path('completed').touch()
    return 0
''' + end)
                proc = subprocess.Popen(['sh', str(project / 'scripts/check.sh')],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, start_new_session=True)
                try:
                    deadline = time.monotonic() + 10
                    while not (project / 'ready').exists() and time.monotonic() < deadline and proc.poll() is None:
                        time.sleep(0.01)
                    self.assertTrue((project / 'ready').exists(), 'the child did not start')
                    proc.send_signal(sig)
                    out = proc.communicate(timeout=10)[0]
                    self.assertEqual(proc.returncode, status, out)
                    for name in ('completed', 'unit-completed', 'pending-completed', 'startup-completed'):
                        self.assertFalse((project / name).exists(), name + ' ran on after cancellation')
                    if not early:
                        self.assertTrue((project / 'stopped').exists(), 'the coordinator cleanup did not run')
                        self.assertFalse(Path((project / 'cache').read_text()).exists(), 'private cache leaked')
                    for name in ('pid', 'unit-pid'):
                        if (project / name).exists():
                            with self.assertRaises(ProcessLookupError, msg=name + ' was not reaped'):
                                os.kill(int((project / name).read_text()), 0)
                finally:
                    if (project / 'pid').exists():
                        with contextlib.suppress(ProcessLookupError):
                            os.killpg(int((project / 'pid').read_text()), signal.SIGKILL)
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.communicate(timeout=10)

    def test_a_signal_to_the_wrapper_stops_and_reaps_its_child(self):
        self.cancel_wrapper()

    def test_a_signal_during_python_startup_is_not_lost(self):
        self.cancel_wrapper(early=True)

    def test_readme_version_matches_the_newest_changelog_heading(self):
        check_kit.check_release(ROOT)
        (self.tmp / 'CHANGELOG.md').write_text('## Unreleased\n\n## v0.11 — 2026-10-09\n\n## v0.10\n')
        for version in ('v0.11', 'v0.10', 'v0.9', ''):
            with self.subTest(version=version):
                (self.tmp / 'README.md').write_text('**%s.** The kit.\n' % version)
                if version == 'v0.11':
                    check_kit.check_release(self.tmp)
                else:
                    with unittest.mock.patch.object(check_kit, 'ROOT', self.tmp), \
                            unittest.mock.patch.object(check_kit, 'check_syntax'), \
                            unittest.mock.patch.object(sys, 'argv', ['check_kit.py']), \
                            contextlib.redirect_stdout(io.StringIO()), \
                            self.assertRaisesRegex(RuntimeError, 'bold version.*newest versioned heading'):
                        check_kit.main()
        (self.tmp / 'CHANGELOG.md').write_text('## Unreleased\n')
        with self.assertRaisesRegex(RuntimeError, 'bold version.*newest versioned heading'):
            check_kit.check_release(self.tmp)

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

    def test_the_locale_sensor_fails_a_suite_that_needs_utf8_by_default(self):
        utf8 = "__import__('locale').getpreferredencoding(False).lower().replace('-', '') == 'utf8'"
        (self.tmp / 'test_kit_probe.py').write_text(PROBE % utf8)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaisesRegex(RuntimeError, 'probe failure message'), \
                unittest.mock.patch.dict(os.environ, PYTHONUTF8='1'):
            check_kit.locale_matrix(self.tmp, ('test_kit_probe',), {'test_kit_probe': 2})
        (self.tmp / 'test_kit_probe.py').write_text(PROBE % 'True')
        with contextlib.redirect_stdout(out):
            check_kit.locale_matrix(self.tmp, ('test_kit_probe',), {'test_kit_probe': 2})
        self.assertIn('PASS: the locale suites ran under', out.getvalue())
        with contextlib.redirect_stdout(out), self.assertRaisesRegex(RuntimeError, '2 tests, 3 required'):
            check_kit.locale_matrix(self.tmp, ('test_kit_probe',), {'test_kit_probe': 3})


if __name__ == '__main__':
    unittest.main()
