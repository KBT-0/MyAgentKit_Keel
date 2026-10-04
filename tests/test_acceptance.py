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
