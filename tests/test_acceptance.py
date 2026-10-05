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
                found = gate.discover(ROOT / directory)[1]
                self.assertEqual(required, found)

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
