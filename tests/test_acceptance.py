"""Acceptance must reject absent, empty, and skipped required regression suites."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kit_acceptance', ROOT / 'scripts/check_kit.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class AcceptanceTests(unittest.TestCase):
    def test_required_suites_cannot_disappear_or_skip(self):
        for case in ('missing', 'empty', 'skipped', 'runtime_skip', 'pass'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'tests').mkdir()
                name = 'test_required_' + case
                if case != 'missing':
                    code = 'import unittest\n'
                    if case != 'empty':
                        code += 'class Required(unittest.TestCase):\n'
                        if case == 'skipped':
                            code += '    @unittest.skip("fixture skip")\n'
                        code += '    def test_protection(self):\n'
                        code += ('        self.skipTest("fixture skip")\n' if case == 'runtime_skip'
                                 else '        self.assertTrue(True)\n')
                    (root / 'tests' / (name + '.py')).write_text(code)
                if case == 'pass':
                    gate.run_tests(root, 'tests', {name: 1})
                else:
                    with self.assertRaisesRegex(RuntimeError, 'required|skipped'):
                        gate.run_tests(root, 'tests', {name: 1})

    def test_python_newer_than_3_10_is_refused(self):
        # The parse used the host's grammar: syntax newer than 3.10, the oldest CI runs,
        # passed here and broke only on CI.
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'module.py'
            source.write_text('match value:\n    case 1:\n        pass\n')
            gate.check_syntax(Path(tmp))
            source.write_text('type Alias = int\n')
            with self.assertRaisesRegex(RuntimeError, 'is not Python 3.10 syntax'):
                gate.check_syntax(Path(tmp))

    def test_every_suite_is_required_at_its_current_count(self):
        # A minimum far below its suite (1 of 30 tests) let the suite lose almost every test
        # with the kit check still green: each minimum is the suite's count, and a new test
        # raises it in the same change.
        for directory, required in gate.REQUIRED_SUITES.items():
            with self.subTest(directory=directory):
                # On native Windows the suites not yet ported there are left out (issue #56).
                leave_out = set(gate.NOT_ON_WINDOWS.get(directory, {}))
                found = gate.discover(ROOT / directory, leave_out)[1]
                self.assertEqual({k: v for k, v in required.items() if k not in leave_out}, found)

    def test_a_utf8_locale_is_picked_by_its_codeset_and_none_is_not_run(self):
        # Only four locale names counted: a host with de_DE.UTF-8 alone failed acceptance.
        self.assertEqual(gate.utf8_locale(['C', 'POSIX', 'de_DE.UTF-8']), 'de_DE.UTF-8')
        self.assertEqual(gate.utf8_locale(['en_GB.iso885915', 'sr_RS.utf8@latin']), 'sr_RS.utf8@latin')
        self.assertEqual(gate.utf8_locale(['fr_FR.Utf-8', 'C.UTF-8']), 'C.UTF-8')
        with self.assertRaisesRegex(RuntimeError, 'NOT RUN'):
            gate.utf8_locale(['C', 'POSIX', 'en_US.iso885915', 'utf8'])

    def test_the_kit_check_never_reads_a_stale_pyc_from_the_tree(self):
        # A module edited within the same second at the same size was read from its stale
        # `.pyc`, even under `python3 -B` (-B stops writing, not reading). The top of the kit
        # check, run as a script up to `ROOT =`, must see the new source, and so must a child.
        import os
        import subprocess
        import sys
        top = (ROOT / 'scripts/check_kit.py').read_text().split('\nROOT =')[0]
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / 'stale_probe.py'
            # Without the prefix a kit check run hands its children, so the pyc lands in the tree.
            env = {k: v for k, v in os.environ.items() if k != 'PYTHONPYCACHEPREFIX'}
            module.write_text('X = 1\n')
            subprocess.run([sys.executable, '-c', 'import stale_probe'], cwd=tmp, env=env, check=True)
            stamp = module.stat().st_mtime_ns
            module.write_text('X = 2\n')
            os.utime(module, ns=(stamp, stamp))
            probe = [sys.executable, '-B', '-c', 'import stale_probe; print(stale_probe.X)']
            stale = subprocess.run(probe, cwd=tmp, env=env, capture_output=True, text=True)
            self.assertEqual(stale.stdout, '1\n', 'the stale-pyc condition was not produced')
            code = (top + '\nimport stale_probe, subprocess\nprint(stale_probe.X, sys.pycache_prefix, flush=True)\n'
                    'subprocess.run(%r, check=True)\n' % probe)
            seen = subprocess.run([sys.executable, '-B', '-c', code], cwd=tmp, env=env,
                                  capture_output=True, text=True)
            self.assertEqual(seen.returncode, 0, seen.stderr)
            first, child = seen.stdout.splitlines()
            value, folder = first.split(' ', 1)
            self.assertEqual((value, child), ('2', '2'), 'the kit check read the stale .pyc')
            self.assertFalse(os.path.exists(folder), 'the private pycache folder was left behind')

    def test_a_windows_self_test_may_fail_only_its_review_case(self):
        # Issue #54: on native Windows a project's review case fails; any other FAIL or skip
        # must still fail the kit check, and so must a review case that suddenly passes.
        ok, review = '  ok   — a gate case\n', '  FAIL — review adapter negative tests failed or did not run\n'
        cygpath = '  skip — a stray cygpath on a POSIX PATH: this host is MSYS\n'
        self.assertIn('NOT RUN', gate.windows_self_test(ok + review + cygpath + 'SELF-TEST: FAIL\n'))
        for odd in ('  FAIL — another gate\n', '  skip — another case\n', ''):
            with self.subTest(odd=odd), self.assertRaisesRegex(RuntimeError, 'beyond its review case'):
                gate.windows_self_test(ok + odd + (review if odd else '') + 'SELF-TEST: FAIL\n')

    def test_packaging_suite_is_required_by_the_real_gate(self):
        self.assertGreaterEqual(gate.REQUIRED_SUITES['tests']['test_packaging'], 1)

    def test_the_record_marks_covered_limitations_superseded_and_names_real_tests(self):
        # The record still listed the Popen-window orphan and a syntax-only Stop hook check as
        # current after both had regressions, and readers could not tell history from a gap.
        import re
        record = (ROOT / 'docs/ACCEPTANCE.md').read_text()
        for bullet in re.split(r'\n- ', record):
            if 'inside `Popen`' in bullet or 'exit-75' in bullet:
                self.assertIn('Superseded', bullet, bullet)
        cited = re.findall(r'`([\w/]+\.py)`\s*\(`(test_\w+)`\)', record)
        self.assertTrue(cited, 'the superseded statements name no covering test')
        for path, name in cited:
            self.assertIn('def %s(' % name, (ROOT / path).read_text(), path)
