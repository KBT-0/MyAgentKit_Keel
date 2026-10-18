"""The kit check runs its units at once and reports them in a fixed order, failures in full."""
import ast
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
import types
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
sys.exit(check_kit.unit('suite', *sys.argv[2:3]))
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

    def test_every_unit_runs_git_without_the_developers_own_configuration(self):
        # Importing check_kit above exported them: units and tests inherit this environment (issue #147).
        self.assertEqual(os.environ['GIT_CONFIG_GLOBAL'], os.devnull)
        self.assertEqual(os.environ['GIT_CONFIG_NOSYSTEM'], '1')
        shown = subprocess.run(['git', 'config', '--list', '--show-scope'], cwd=self.tmp, capture_output=True,
                               text=True).stdout
        self.assertEqual([line for line in shown.splitlines() if line.split('\t')[0] in ('system', 'global')], [])

    def test_the_kit_article_describes_the_author_tier_refusal(self):
        # This article belongs to the kit, not to a bootstrapped project's docs.
        page = ' '.join((ROOT / 'docs/decorrelated-review.md').read_text(encoding='utf-8').split())
        self.assertIn("refuses a reviewer of the author's tier", page)
        self.assertNotIn('planned work', page)

    def test_review_shards_require_complete_unique_successful_reports(self):
        # Use the shipped runner in fresh processes, with cheap cases that require overlap.
        source = (ROOT / 'core/scripts/test_claude_bridge.py').read_text(encoding='utf-8')
        source = source.rpartition('if __name__ == "__main__":')[0]
        source = source.replace('ROOT = Path(__file__).resolve().parent',
                                'ROOT = Path(%r)' % str(ROOT / 'core/scripts'))
        probe = self.tmp / 'shard_probe.py'
        source = ('import sys\nsys.path.insert(0, %r)\n' % str(ROOT / 'core/scripts')) + source
        probe.write_text(source + '''
class Probe(unittest.TestCase):
    def test_a(self):
        self.overlap()
    def test_b(self):
        self.overlap()
    def overlap(self):
        folder = Path(os.environ['PROBE_FOLDER'])
        (folder / str(os.getpid())).touch()
        until = time.monotonic() + 10
        while len(list(folder.iterdir())) < 2 and time.monotonic() < until:
            time.sleep(.01)
        self.assertEqual(len(list(folder.iterdir())), 2, 'shards did not run in parallel')
    def test_c(self):
        if os.environ['PROBE_MODE'] == 'unexpected_skip':
            self.skipTest('undeclared exclusion')
        if os.environ['PROBE_MODE'] == 'failure':
            self.fail('real shard failure')
    @unittest.skip('declared platform exclusion')
    def test_d(self):
        pass
    test_d._kit_platform_skip = True

if __name__ == '__main__':
    if sys.argv[1:2] == ['--review-shard']:
        code = run_review_shard(*sys.argv[2:])
        path = Path(sys.argv[3])
        report = json.loads(path.read_text(encoding='utf-8'))
        mode = os.environ['PROBE_MODE']
        if mode == 'missing': report['ids'].pop()
        if mode == 'duplicate': report['ids'].append(report['ids'][0])
        if mode == 'zero': report.update(ids=[], executed=0, skipped=[])
        if mode == 'count': report['executed'] += 1
        if mode == 'missing_report': path.unlink()
        else: path.write_text(json.dumps(report), encoding='utf-8')
        raise SystemExit(7 if mode == 'exit' else code)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Probe)
    raise SystemExit(0 if run_review_shards(suite, minimum=int(sys.argv[1]),
                                          timeout=.01 if os.environ['PROBE_MODE'] == 'timeout' else None) else 1)
''', encoding='utf-8')
        for mode, minimum, passes in (('success', 3, True), ('missing', 3, False),
                                      ('duplicate', 3, False), ('exit', 3, False),
                                      ('zero', 3, False), ('count', 3, False),
                                      ('missing_report', 3, False), ('unexpected_skip', 3, False),
                                      ('failure', 3, False), ('timeout', 3, False), ('success', 4, False)):
            folder = self.tmp / ('pids-%s-%d' % (mode, minimum))
            folder.mkdir()
            with self.subTest(mode=mode, minimum=minimum):
                result = subprocess.run([sys.executable, '-B', str(probe), str(minimum)],
                                        env=dict(os.environ, PROBE_FOLDER=str(folder), PROBE_MODE=mode),
                                        capture_output=True, text=True, timeout=40)
                self.assertEqual(result.returncode, 0 if passes else 1, result.stdout + result.stderr)
                if passes:
                    self.assertIn('Ran 3 tests: OK', result.stdout)
                    self.assertEqual(result.stdout.count('NOT RUN:'), 1, result.stdout)
                else:
                    self.assertIn('FAIL: review shards', result.stdout, result.stderr)

    def test_review_shards_cancel_both_process_trees_on_parent_exception(self):
        source = (ROOT / 'core/scripts/test_claude_bridge.py').read_text(encoding='utf-8')
        source = source.rpartition('if __name__ == "__main__":')[0]
        source = source.replace('ROOT = Path(__file__).resolve().parent',
                                'ROOT = Path(%r)' % str(ROOT / 'core/scripts'))
        probe = self.tmp / 'cancel_probe.py'
        probe.write_text(('import sys\nsys.path.insert(0, %r)\n' % str(ROOT / 'core/scripts')) + source + '''
import _thread, threading
folder = Path(os.environ['PROBE_FOLDER'])
class Probe(unittest.TestCase):
    def test_a(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (folder / str(os.getpid())).write_text(str(child.pid), encoding='utf-8')
        time.sleep(8)
    test_b = test_a

def alive(pid):
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return False
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    status = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(status) and not status.startswith('Z')

if __name__ == '__main__':
    if sys.argv[1:2] == ['--review-shard']:
        raise SystemExit(run_review_shard(*sys.argv[2:]))
    def interrupt():
        until = time.monotonic() + 10
        while len(list(folder.iterdir())) < 2 and time.monotonic() < until:
            time.sleep(.01)
        _thread.interrupt_main()
    def fail(signum, frame):
        raise RuntimeError('parent failure')
    expected = KeyboardInterrupt if sys.argv[1] == 'interrupt' else RuntimeError
    if expected is RuntimeError:
        signal.signal(signal.SIGINT, fail)
    timer = threading.Thread(target=interrupt)
    timer.start()
    started = time.monotonic()
    try:
        run_review_shards(unittest.defaultTestLoader.loadTestsFromTestCase(Probe))
    except expected:
        elapsed = time.monotonic() - started
    else:
        raise AssertionError('parent exception was swallowed')
    finally:
        timer.join(timeout=12)
    assert elapsed < 4, 'parent exception took %.3f seconds' % elapsed
    markers = list(folder.iterdir())
    assert len(markers) == 2, 'both shards must have started'
    pids = [int(value) for path in markers for value in (path.name, path.read_text(encoding='utf-8'))]
    until = time.monotonic() + 2
    while any(alive(pid) for pid in pids) and time.monotonic() < until:
        time.sleep(.02)
    assert not any(alive(pid) for pid in pids), 'shard or descendant survived parent exception'
''', encoding='utf-8')
        for mode in ('interrupt', 'error'):
            folder = self.tmp / mode
            folder.mkdir()
            with self.subTest(mode=mode):
                result = subprocess.run([sys.executable, '-B', str(probe), mode],
                                        env=dict(os.environ, PROBE_FOLDER=str(folder)),
                                        capture_output=True, text=True, timeout=25)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_empty_review_companion_is_refused_before_shards_start(self):
        code = '''import runpy, sys, unittest
sys.path.insert(0, %r)
import test_codex_quota
class EmptyQuota(unittest.TestCase):
    pass
test_codex_quota.QuotaTests = EmptyQuota
runpy.run_path(%r, run_name='__main__')
''' % (str(ROOT / 'core/scripts'), str(ROOT / 'core/scripts/test_claude_bridge.py'))
        result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('EmptyQuota has 0 of at least', result.stderr)

    def suite_unit(self, condition, minimum):
        (self.tmp / 'suite').mkdir(exist_ok=True)
        (self.tmp / 'suite/test_kit_probe.py').write_text(PROBE % condition)
        script = self.tmp / 'unit.py'
        script.write_text(UNIT % (str(ROOT / 'scripts/check_kit.py'), str(self.tmp), minimum))
        return [sys.executable, '-B', '-u', str(script)]

    def test_a_failing_suite_prints_only_its_failures_and_fails_the_run(self):
        passed, out = runner(('suite', self.suite_unit('False', 2)))
        self.assertFalse(passed)
        self.assertNotIn('test_passes', out)
        self.assertNotIn('... ok', out)
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
                if declared and expected:
                    self.assertIn('NOT RUN: test_kit_probe.Probe.test_maybe', out)

    def test_platform_wrappers_do_not_satisfy_suite_minimums(self):
        # Exercise the shipped decorators on cheap probes, including the platform branch
        # this host cannot run. A print-and-return replacement used to pass a minimum of 2.
        for module, decorator, windows in (
                ('test_spawn_worker', 'tmux_path_cases', True),
                ('test_check_gate_windows', 'windows_only', False),
                ('test_clean_worktrees_windows', 'windows_only', False),
                ('test_review_windows', 'windows_only', False)):
            tree = ast.parse((ROOT / 'tests' / (module + '.py')).read_text(encoding='utf-8'))
            helper = next(node for node in tree.body
                          if isinstance(node, ast.FunctionDef) and node.name == decorator)
            source = ('import shutil, sys, unittest\nWINDOWS = %r\nON_WINDOWS = set()\n'
                      % windows) + ast.unparse(helper) + '\n' + PROBE % 'False'
            if decorator == 'tmux_path_cases':
                # Keep one real passing scenario beside the excluded probe.
                source = source.replace('ON_WINDOWS = set()', "ON_WINDOWS = {'test_passes'}")
                source += '\nProbe = tmux_path_cases(Probe)\n'
            else:
                source += '\nProbe.test_maybe = windows_only(Probe.test_maybe)\n'
            for minimum, expected in ((2, False), (1, True)):
                with self.subTest(module=module, minimum=minimum):
                    command = self.suite_unit('True', minimum)
                    (self.tmp / 'suite/test_kit_probe.py').write_text(source)
                    passed, out = runner(('suite', command))
                    self.assertEqual(passed, expected, out)
                    # A declared skip is left out before the run: at 2 nothing runs.
                    self.assertEqual('NOT RUN: test_kit_probe.Probe.test_maybe' in out, expected, out)

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

        # Python 3.11 has lstat's Windows attributes but no Path.is_junction.
        with unittest.mock.patch.object(Path, 'is_symlink', return_value=False), \
                unittest.mock.patch.object(Path, 'is_junction', None, create=True), \
                unittest.mock.patch.object(Path, 'lstat', lstat):
            with self.assertRaisesRegex(RuntimeError, 'linked test directories.*linked'):
                check_kit.discover(folder)

    def test_discovery_needs_no_windows_only_stat_constants(self):
        # Linux and macOS on Python 3.11: no Path.is_junction, and stat has no IO_REPARSE_TAG_*
        # (issue #96: the lookup raised AttributeError before any suite ran).
        folder = self.tmp / 'suite'
        folder.mkdir()
        (folder / 'test_stat_probe.py').write_text(PROBE % 'True')
        with unittest.mock.patch.object(check_kit, 'stat', types.SimpleNamespace()), \
                unittest.mock.patch.object(Path, 'is_junction', None, create=True):
            suite, counts = check_kit.discover(folder)
        self.assertEqual(counts, {'test_stat_probe': 2})

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

    def test_discovery_without_is_junction_reads_no_windows_only_stat_names(self):
        # POSIX Python 3.11 has neither Path.is_junction nor stat's reparse tag names: reading
        # the names failed discovery there, and no suite ran (#96).
        folder = self.tmp / 'suite'
        folder.mkdir()
        (folder / 'test_posix_probe.py').write_text(PROBE % 'True')
        with unittest.mock.patch.object(Path, 'is_junction', None, create=True), \
                unittest.mock.patch.object(check_kit, 'stat', types.SimpleNamespace()):
            suite, counts = check_kit.discover(folder)
        self.assertEqual(counts, {'test_posix_probe': 2})

    def test_a_module_unit_imports_and_runs_only_its_module(self):
        # tests/ runs as one unit per module (#146): a unit must not run its neighbours.
        command = self.suite_unit('True', 2)
        (self.tmp / 'suite/test_other.py').write_text('raise AssertionError("other module imported")\n')
        script = self.tmp / 'unit.py'
        script.write_text(script.read_text().replace("unit('suite'", "unit('suite/test_kit_probe'"))
        passed, out = runner(('suite/test_kit_probe', command))
        self.assertTrue(passed, out)
        self.assertIn('suite ran 2 tests', out)
        self.assertNotIn('other module imported', out)
        # A shard checks the module's whole count and runs every second test: test_maybe
        # (failing here) runs in shard 0 alone.
        (self.tmp / 'suite/test_kit_probe.py').write_text(PROBE % 'False')
        text = script.read_text()
        for index, expected in ((0, False), (1, True)):
            with self.subTest(shard=index):
                script.write_text(text.replace("sys.exit(", "check_kit.SHARDS = {'test_kit_probe': 2}\nsys.exit(")
                                  .replace("unit('suite/test_kit_probe'", "unit('suite/test_kit_probe@%d'" % index))
                passed, out = runner(('suite/test_kit_probe@%d' % index, command))
                self.assertEqual(passed, expected, out)
                self.assertIn('probe failure message' if index == 0 else 'suite ran 1 tests', out)

    def test_main_runs_one_unit_per_module_and_refuses_a_module_without_a_count(self):
        # A module that does not run on this host gets its NOT RUN line, no unit ("ran 0 tests"),
        # and the sharded modules start right after acceptance. Each unit is in one tier: the
        # default run is the fast tier, --slow the SLOW units, --all both.
        off_host = {'tests': {'test_doctor': 'a reason', 'test_bootstrap': 'r'}}

        def units(*argv, slow=check_kit.SLOW):
            names, out = [], io.StringIO()
            with unittest.mock.patch.object(check_kit, 'NOT_ON_WINDOWS', off_host),                     unittest.mock.patch.object(check_kit, 'SLOW', slow),                     unittest.mock.patch.object(check_kit, 'check_syntax'),                     unittest.mock.patch.object(check_kit, 'check_release'),                     unittest.mock.patch.object(check_kit, 'check_actions'),                     unittest.mock.patch.object(check_kit, 'untested_guards'),                     unittest.mock.patch.object(check_kit, 'validate_plugin'),                     unittest.mock.patch.object(check_kit, 'run', return_value=''),                     unittest.mock.patch.object(check_kit, 'run_units',
                                               side_effect=lambda units, *a, **k: names.extend(n for n, _ in units)),                     unittest.mock.patch.object(sys, 'argv', ['check_kit.py', *argv]),                     contextlib.redirect_stdout(out):
                self.assertEqual(check_kit.main(), 1)
            return names, out.getvalue()

        names, out = units('--all')
        self.assertIn('NOT RUN: tests/test_doctor on native Windows (a reason)', out)
        sharded = ['%s/%s@%d' % (directory, name, index) for directory, required in check_kit.REQUIRED_SUITES.items()
                   for name in required if name in check_kit.SHARDS and name not in off_host.get(directory, {})
                   for index in range(check_kit.SHARDS[name])]
        expected = ['structure', 'acceptance'] + sharded + ['locale/' + name for name in check_kit.LOCALE_SUITES] + [
            directory + '/' + name for directory, required in check_kit.REQUIRED_SUITES.items()
            for name in required if name not in check_kit.SHARDS and name not in off_host.get(directory, {})]
        self.assertEqual(names[:len(sharded) + 2], ['structure', 'acceptance'] + sharded)
        self.assertEqual(sorted(names), sorted(expected))
        self.assertTrue(set(check_kit.SHARDS) <= set(check_kit.REQUIRED_SUITES['tests'])
                        | set(check_kit.REQUIRED_SUITES['core/scripts']))
        module = lambda name: name.rpartition('/')[2].partition('@')[0]
        slow, out = units('--slow')
        self.assertEqual(slow, [name for name in names if module(name) in check_kit.SLOW])
        self.assertIn('slow tier', out)
        fast, out = units()
        self.assertEqual(fast, [name for name in names if module(name) not in check_kit.SLOW])
        self.assertIn('fast tier', out)
        self.assertTrue(slow and fast)
        # A long unit starts right after the shards, never last.
        self.assertTrue(set(check_kit.LONG) <= set(check_kit.REQUIRED_SUITES['tests']))
        self.assertLess(fast.index('tests/test_close_worker'), fast.index('tests/test_packaging'))
        with self.assertRaisesRegex(RuntimeError, 'SLOW names no unit of the kit check: test_gone'):
            units(slow=check_kit.SLOW | {'test_gone'})
        (self.tmp / 'suite').mkdir()
        for name in ('test_kit_probe', 'test_new'):
            (self.tmp / 'suite' / (name + '.py')).write_text(PROBE % 'True')
        with unittest.mock.patch.object(check_kit, 'ROOT', self.tmp), \
                unittest.mock.patch.object(check_kit, 'REQUIRED_SUITES', {'suite': {'test_kit_probe': 2}}), \
                unittest.mock.patch.object(sys, 'argv', ['check_kit.py']), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'suite: no count in REQUIRED_SUITES for test_new'):
                check_kit.main()

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

    def test_an_inherited_work_variable_never_chooses_the_scratch_folder(self):
        # An exported `work` once named the folder the wrapper's git_view wrote and deleted
        # git-paths* in, even when the check then refused its arguments (round-3 Codex Critical).
        project, decoy = self.tmp / 'kit', self.tmp / 'decoy'
        (project / 'scripts').mkdir(parents=True)
        decoy.mkdir()
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        shutil.copyfile(ROOT / 'scripts/check.sh', project / 'scripts/check.sh')
        (project / 'scripts/check_kit.py').write_text('import sys\nsys.exit("unknown argument")\n')
        names = ('git-paths', 'git-paths.hashes', 'git-paths.errors')
        for name in names:
            (decoy / name).write_text('owner data\n')
        result = subprocess.run(['sh', str(project / 'scripts/check.sh'), '--bogus'],
                                cwd=project, capture_output=True, text=True,
                                env=dict(os.environ, work=decoy.as_posix()))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in names:
            self.assertEqual((decoy / name).read_text() if (decoy / name).exists() else None,
                             'owner data\n', name)

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
        return unit('suite')
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
        (self.tmp / 'CHANGELOG.md').write_text('## Unreleased\n\n## v0.11 — 2026-10-09\n\n## v0.10\n', encoding='utf-8')
        (self.tmp / 'plugin/.claude-plugin').mkdir(parents=True)
        (self.tmp / 'plugin/.claude-plugin/plugin.json').write_text('{"version": "0.11.0"}', encoding='utf-8')
        for version in ('v0.11', 'v0.10', 'v0.9', ''):
            with self.subTest(version=version):
                (self.tmp / 'README.md').write_text('**%s.** The kit.\n' % version, encoding='utf-8')
                if version == 'v0.11':
                    check_kit.check_release(self.tmp)
                else:
                    with unittest.mock.patch.object(check_kit, 'ROOT', self.tmp), \
                            unittest.mock.patch.object(check_kit, 'check_syntax'), \
                            unittest.mock.patch.object(sys, 'argv', ['check_kit.py']), \
                            contextlib.redirect_stdout(io.StringIO()), \
                            self.assertRaisesRegex(RuntimeError, 'bold version.*newest versioned heading'):
                        check_kit.structure()
        # A plugin whose version string stays the same is not updated where it is installed:
        # its MAJOR.MINOR is the kit's, three parts as the manifest reference shows them.
        (self.tmp / 'README.md').write_text('**v0.11.** The kit.\n', encoding='utf-8')
        for version in ('0.11.3', '0.1.0', '0.11', '0.110.0', 'v0.11.0', None):
            with self.subTest(plugin=version):
                (self.tmp / 'plugin/.claude-plugin/plugin.json').write_text(
                    '{}' if version is None else '{"version": "%s"}' % version, encoding='utf-8')
                if version == '0.11.3':
                    check_kit.check_release(self.tmp)
                else:
                    with self.assertRaisesRegex(RuntimeError, r'plugin\.json.*version.*v0\.11'):
                        check_kit.check_release(self.tmp)
        (self.tmp / 'CHANGELOG.md').write_text('## Unreleased\n', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'bold version.*newest versioned heading'):
            check_kit.check_release(self.tmp)

    def test_a_changed_project_owned_kit_file_needs_an_action_item_naming_it(self):
        # A fix to a file sync never copies reached no project without an ACTION item (#134).
        # TemporaryDirectory: its clean-up removes git's read-only objects on Windows too.
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        (root / 'core/scripts').mkdir(parents=True)
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')

        def git(*args):
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@example.com',
                            *args], env=env, check=True, capture_output=True)

        def check():
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                check_kit.check_actions(root)
            return out.getvalue()

        changelog = '# CHANGELOG\n\n## v0.2 — date\n\n- %s\n\n## v0.1 — date\n\n- first\n'
        (root / 'core/scripts/check.sh').write_text('echo one\n')
        (root / 'core/scripts/sync.sh').write_text('# KIT-OWNED: synced\necho one\n')
        (root / 'CHANGELOG.md').write_text(changelog % 'nothing yet', encoding='utf-8')
        git('init', '-q')
        git('add', '-A')
        git('commit', '-qm', 'one')
        self.assertIn('NOT RUN: the ACTION check', check())
        git('tag', 'v0.1')
        (root / 'core/scripts/sync.sh').write_text('# KIT-OWNED: synced\necho two\n')
        self.assertEqual(check(), '')
        (root / 'core/scripts/check.sh').write_text('echo two\n')
        with self.assertRaisesRegex(RuntimeError, 'no ACTION item naming them under CHANGELOG v0.2: '
                                                  'core/scripts/check.sh$'):
            check()
        (root / 'CHANGELOG.md').write_text(changelog % 'A gate fix.\n  **ACTION:** merge `scripts/check.sh`.',
                                           encoding='utf-8')
        self.assertIn('PASS: every project-owned kit file changed since v0.1', check())
        (root / 'CHANGELOG.md').write_text('# CHANGELOG\n\n## v0.1 — date\n\n- **ACTION:** check.sh\n',
                                           encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'no newer version for their ACTION items: core/scripts/check.sh'):
            check()
        # A diff git cannot make is a FAIL line, not a CalledProcessError traceback.
        real = subprocess.run

        def broken_diff(args, **kwargs):
            if 'diff' in args:
                return subprocess.CompletedProcess(args, 128, '', 'fatal: bad object v0.1')
            return real(args, **kwargs)

        with unittest.mock.patch.object(check_kit.subprocess, 'run', broken_diff), \
                self.assertRaisesRegex(RuntimeError, 'git diff against v0.1 failed: fatal: bad object'):
            check()

    def test_a_unit_over_its_cap_is_stopped_and_fails_with_its_name_and_seconds(self):
        # run_units waited for a unit without a bound: a hung test module hung the kit check. The
        # hung unit starts a child that holds the output pipe, as a test's shell or git does.
        hang = [sys.executable, '-c', 'import subprocess, sys, time\n'
                'subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])\n'
                'print("hang started", flush=True)\ntime.sleep(60)']
        quick = [sys.executable, '-c', 'print("UNIT DONE: quick")']
        started = time.monotonic()
        passed, out = runner(('hang', hang), ('quick', quick), caps=[2, 2])
        self.assertFalse(passed)
        self.assertIn('hang started', out)
        self.assertRegex(out, r'unit hang ran over its cap of 2 s and was stopped at \d+ s')
        self.assertIn('failed: hang', out)
        self.assertNotIn('quick (FAILED)', out)
        # The child is stopped with the unit (Windows: its tree; POSIX: the unit's own process
        # group), so its pipe closes at once; before, POSIX waited for the child's 20 s.
        self.assertLess(time.monotonic() - started, 15)

    def test_a_tier_over_its_budget_fails_with_its_seconds(self):
        quiet = [sys.executable, '-c', 'import time; time.sleep(1.5); print("UNIT DONE: quiet")']
        real = check_kit.run_units
        for budget, code in ((1, 1), (600, 0)):
            with self.subTest(budget=budget):
                out = io.StringIO()
                with unittest.mock.patch.dict(os.environ, {check_kit.SCALE: '1'}), \
                        unittest.mock.patch.object(check_kit, 'CAPS', {'fast': (60, budget), 'slow': (60, 60)}), \
                        unittest.mock.patch.object(check_kit, 'check_syntax'), \
                        unittest.mock.patch.object(check_kit, 'check_release'), \
                        unittest.mock.patch.object(check_kit, 'check_actions'), \
                        unittest.mock.patch.object(check_kit, 'untested_guards'), \
                        unittest.mock.patch.object(check_kit, 'validate_plugin'), \
                        unittest.mock.patch.object(check_kit, 'run', return_value='packaged source matches'), \
                        unittest.mock.patch.object(check_kit, 'run_units',
                                                   side_effect=lambda units, *a, **kw: real([('quiet', quiet)], **kw)), \
                        unittest.mock.patch.object(check_kit, '_PASSED_FILE', None), \
                        unittest.mock.patch.object(sys, 'argv', ['check_kit.py']), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                    self.assertEqual(check_kit.main(), code, out.getvalue())
                self.assertEqual(bool(re.search(r'the fast tier took \d+ s, over its budget of 1 s', out.getvalue())),
                                 bool(code), out.getvalue())
                self.assertEqual('KIT CHECK: PASS' in out.getvalue(), not code)

    def test_the_gate_checks_count_drops_with_its_link_test_on_a_host_without_symlinks(self):
        # Without symlink privilege (Windows without Developer Mode) BuildCacheTests' link test is a
        # declared skip, which never counts: a fixed count of 12 turned every test_gate_checks unit red.
        probe = ("import importlib.util, os, sys\n"
                 "def refuse(*a, **k): raise OSError('no privilege')\n"
                 "os.symlink = refuse\n"
                 "spec = importlib.util.spec_from_file_location('check_kit', sys.argv[1])\n"
                 "kit = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(kit)\n"
                 "tests = kit.ROOT / 'tests'\n"
                 "suite, found = kit.discover(tests, {p.stem for p in tests.glob('test_*.py')} - {'test_gate_checks'})\n"
                 "skips = sum(bool(getattr(getattr(t, t._testMethodName), '_kit_platform_skip', False))"
                 " for t in kit._cases(suite))\n"
                 "print(skips, found['test_gate_checks'] - skips, kit.REQUIRED_SUITES['tests']['test_gate_checks'])\n")
        result = subprocess.run([sys.executable, '-B', '-c', probe, str(ROOT / 'scripts/check_kit.py')],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        skips, countable, required = map(int, result.stdout.split())
        self.assertEqual(skips, 1, result.stdout)
        self.assertEqual(required, countable)

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

    def test_what_the_early_checks_could_not_run_is_repeated_under_the_summary_too(self):
        # The killing-test note's NOT RUN line (no upstream branch) and shellcheck's were printed
        # before the units and never repeated, so a long output lost them. They now come from the
        # structure unit, which runs beside the suites (#146).
        code = ("import importlib.util, sys\n"
                "spec = importlib.util.spec_from_file_location('check_kit', %r)\n"
                "ck = importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(ck)\n"
                "ck.check_syntax = lambda root: print('NOT RUN: shellcheck probe')\n"
                "ck.check_release = ck.check_actions = lambda root: None\n"
                "ck.untested_guards = lambda root: print('NOT RUN: killing-test probe')\n"
                "ck.validate_plugin = lambda root: print('NOT RUN: validator probe')\n"
                "ck.run = lambda *a, **k: 'packaged source matches'\n"
                "sys.exit(ck.unit('structure'))\n") % check_kit.__file__
        quiet = [sys.executable, '-c', 'print("quiet output\\nUNIT DONE: quiet")']
        passed, out = runner(('structure', [sys.executable, '-c', code]), ('quiet', quiet))
        self.assertTrue(passed, out)
        tail = out[out.index('UNIT DONE: quiet'):]
        for line in ('NOT RUN: shellcheck probe', 'NOT RUN: killing-test probe', 'NOT RUN: validator probe'):
            self.assertIn('\n%s\n' % line, tail)
            self.assertEqual(out.count(line), 2, out)

    def test_the_claude_plugin_is_validated_strictly_and_not_run_without_the_cli(self):
        # The vendor's validator (`claude plugin validate --strict`) over plugin/, where the
        # CLI is on PATH; without it one NOT RUN line, never a silent pass (D08 inv2#178).
        out = io.StringIO()
        with unittest.mock.patch.object(check_kit.shutil, 'which', return_value=None), \
                unittest.mock.patch.object(check_kit, 'run') as ran, contextlib.redirect_stdout(out):
            check_kit.validate_plugin(ROOT)
        ran.assert_not_called()
        self.assertIn('NOT RUN: claude plugin validate plugin --strict', out.getvalue())
        with unittest.mock.patch.object(check_kit.shutil, 'which', return_value='/bin/claude'), \
                unittest.mock.patch.object(check_kit, 'run', return_value='') as ran, \
                contextlib.redirect_stdout(io.StringIO()):
            check_kit.validate_plugin(ROOT)
        self.assertEqual(ran.call_args.args[0], ['/bin/claude', 'plugin', 'validate', 'plugin', '--strict'])
        self.assertEqual(ran.call_args.kwargs['cwd'], ROOT)
        with unittest.mock.patch.object(check_kit.shutil, 'which', return_value='/bin/claude'), \
                unittest.mock.patch.object(check_kit, 'run', side_effect=RuntimeError('warning: x')), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, 'warning'):
            check_kit.validate_plugin(ROOT)

    def test_an_added_line_starting_with_two_pluses_is_not_a_file_header(self):
        # `++ b/x` added in a file shows in the -U0 diff as `+++ b/x`: read as a header, it
        # renamed the file of every later refusal (BACKLOG, v0.11 D-5 logic r2).
        # TemporaryDirectory, not self.tmp: its cleanup removes Git's read-only objects on Windows.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / 'repo'
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        git = lambda *args: subprocess.run(['git', '-C', str(root), *args], env=env, check=True,
                                           capture_output=True)
        root.mkdir()
        git('init', '-q', '-b', 'main')
        git('-c', 'user.name=t', '-c', 'user.email=t@x', 'commit', '-q', '--allow-empty', '-m', 'base')
        git('branch', 'upstream')
        git('branch', '-q', '--set-upstream-to=upstream')
        (root / 'gate.sh').write_text('x=1\n++ b/elsewhere.sh\n[ -n "$x" ] || exit 2\n', encoding='utf-8')
        git('add', '-A')
        with unittest.mock.patch.dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1'), \
                contextlib.redirect_stdout(io.StringIO()):
            notes = check_kit.untested_guards(root)
        self.assertEqual([note.split(' adds')[0] for note in notes], ['NOTE [killing test]: gate.sh:3'])

    def test_the_locale_sensor_names_a_missing_turkish_locale_and_runs_one_it_has(self):
        # The POSIX branch: locale -a decides whether tr_TR.UTF-8 runs; without one, NOT RUN.
        for listed, said in (('C\nPOSIX\n', 'NOT RUN: the locale suites under tr_TR.UTF-8'),
                             ('C\ntr_TR.utf8\n', 'PASS: the locale suites ran under LC_ALL=C, LC_ALL=tr_TR.utf8')):
            out = io.StringIO()
            with self.subTest(listed=listed), \
                    unittest.mock.patch.object(check_kit, 'os', types.SimpleNamespace(name='posix', environ={})), \
                    unittest.mock.patch.object(check_kit, 'run', return_value=listed) as ran, \
                    contextlib.redirect_stdout(out):
                check_kit.locale_matrix(self.tmp, (), {})
            self.assertEqual(ran.call_args.args[0], ['locale', '-a'])
            self.assertIn(said, out.getvalue())
            self.assertEqual('NOT RUN' in out.getvalue(), 'tr_TR' not in listed)

    def test_a_locale_list_that_is_not_utf8_still_yields_a_utf8_locale(self):
        # `locale -a` was decoded strictly in the host's encoding: one name holding a Latin-1
        # byte raised there instead of choosing among the rest (BACKLOG, v0.11 D-1).
        real = subprocess.run

        def fake(args, **kw):
            if args == ['locale', '-a']:
                args = [sys.executable, '-c', 'import sys; sys.stdout.buffer.write('
                        'b"C\\nfr_FR.ISO8859-1\\xe9\\nde_DE.UTF-8\\n")']
            return real(args, **kw)
        with unittest.mock.patch.object(check_kit.subprocess, 'run', side_effect=fake):
            self.assertEqual(check_kit.utf8_locale(), 'de_DE.UTF-8')

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
                         [1, 1, 1, 2, 3, 3, 3])
        self.assertEqual(check_kit.degree(5, 1), 1)
        # One unit per test module (#146): dozens of units, one per two CPUs at once.
        self.assertEqual([check_kit.degree(cpus, 60) for cpus in (3, 4, 20, 64)], [1, 2, 10, 32])
        with unittest.mock.patch.dict(os.environ, {'MYAGENTKIT_TEST_TIMEOUT_SCALE': '1.5'}):
            self.assertEqual(check_kit.limit(300), 450)

    def test_units_run_that_many_at_once_with_their_timeouts_scaled_by_it(self):
        unit = [sys.executable, '-c', 'import os, time; s = time.time(); time.sleep(0.5); '
                'print("span", os.environ["MYAGENTKIT_TEST_TIMEOUT_SCALE"], s, time.time()); '
                'import sys; print("UNIT DONE: " + sys.argv[1])']
        # The factor stops at 4: at 10 at once a hung 1800 s phase ran five hours (#146).
        for parallel, scale, overlap in ((1, 2.0, False), (2, 4.0, True), (6, 8.0, True)):
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
        probe = self.tmp / 'test_kit_probe.py'
        out = io.StringIO()

        def red(condition, reason, minimum=2, source=PROBE):
            probe.write_text(source % condition, encoding='utf-8')
            with contextlib.redirect_stdout(out), self.assertRaisesRegex(RuntimeError, reason), \
                    unittest.mock.patch.dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
                                             PYTHONWARNINGS='ignore'):
                check_kit.locale_matrix(self.tmp, ('test_kit_probe',), {'test_kit_probe': minimum})

        on_windows_utf8 = os.name == 'nt' and __import__('locale').getpreferredencoding(False).lower() in ('utf-8', 'cp65001')
        if not on_windows_utf8:
            red(utf8, 'probe failure message')
        red("open(__file__).read()", 'EncodingWarning')
        red('True', '1 tests run, 2 required',
            source=PROBE.replace('    def test_maybe', '    @unittest.skip("x")\n    def test_maybe'))
        red('True', '2 tests run, 3 required', minimum=3)
        # The caller's PYTHONIOENCODING would hide a non-ASCII print under C; the run drops it.
        probe.write_text(PROBE % "__import__('os').environ.get('PYTHONIOENCODING') is None", encoding='utf-8')
        with contextlib.redirect_stdout(out), unittest.mock.patch.dict(os.environ, PYTHONIOENCODING='utf-8'):
            check_kit.locale_matrix(self.tmp, ('test_kit_probe',), {'test_kit_probe': 2})
        self.assertIn('PASS: the locale suites ran under', out.getvalue())


if __name__ == '__main__':
    unittest.main()
