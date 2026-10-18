"""The Unity gate's evidence checks, each fed a stub editor: red with its own line, or green.

The failure that matters is not "Unity returned an error" but "Unity returned success and
proved nothing", which needs no Unity install to reproduce. These cases replace the gate's own
--self-test (owner decision 2026-10-18; docs/research/kit-self-checks.md, finding 1).
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / 'overlays/unity/files/scripts/unity_gate.sh'
# The stub writes its body's document to the path after -testResults, then exits 0.
WRITE = ('#!/bin/sh\nprev=\nfor a in "$@"; do\n'
         '  [ "$prev" = -testResults ] && printf \'%%s\\n\' \'%s\' > "$a"\n  prev="$a"\ndone\nexit 0\n')


class UnityGateTests(unittest.TestCase):
    def run_gate(self, stub_body):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'scripts').mkdir()
            (tmp / 'scripts/unity_gate.sh').write_bytes(GATE.read_bytes())
            stub = tmp / 'unity-stub'
            stub.write_text(stub_body, encoding='utf-8', newline='\n')
            stub.chmod(0o755)
            result = subprocess.run(['sh', 'scripts/unity_gate.sh'], cwd=tmp, capture_output=True, text=True,
                                    env=dict(os.environ, UNITY_PATH=stub.as_posix(),
                                             UNITY_PROJECT=(tmp / 'proj').as_posix()), timeout=60)
            return result.returncode, result.stdout + result.stderr

    def assert_red(self, stub_body, line):
        code, out = self.run_gate(stub_body)
        self.assertEqual(code, 1, out)
        self.assertIn(line, out)
        self.assertIn('UNITY GATE: FAIL', out)

    def test_a_clean_exit_that_wrote_no_results_file_fails(self):
        self.assert_red('#!/bin/sh\nexit 0\n', 'produced no results file')

    def test_a_results_file_that_is_not_an_nunit_document_fails(self):
        self.assert_red(WRITE % '<test-case />', 'is not an NUnit result document')

    def test_a_run_whose_every_test_was_skipped_fails(self):
        self.assert_red(WRITE % '<test-run><test-case name="a" result="Skipped" /></test-run>',
                        'no test executed on either platform')

    def test_an_all_skipped_run_fails_when_its_suite_and_run_are_marked_skipped_too(self):
        # #166: NUnit marks the enclosing suite and run Skipped; those must not count as skipped cases.
        self.assert_red(WRITE % ('<test-run result="Skipped">\n<test-suite type="Assembly" result="Skipped">\n'
                                 '<test-case name="a" result="Skipped" />\n</test-suite>\n</test-run>'),
                        'no test executed on either platform')

    def test_an_ignored_test_counts_once_however_many_parents_are_marked_skipped(self):
        code, out = self.run_gate(WRITE % ('<test-run result="Skipped">\n<test-suite result="Skipped">\n'
                                           '<test-case name="a" result="Passed" />\n'
                                           '<test-case name="b" result="Skipped" />\n</test-suite>\n</test-run>'))
        self.assertEqual(code, 0, out)
        self.assertIn('2 case(s), 1 skipped, 0 failed, 1 executed.', out)

    def test_a_failed_suite_fails_even_when_every_case_passed(self):
        # A OneTimeTearDown that throws marks the suite and run Failed over passing cases.
        self.assert_red(WRITE % ('<test-run result="Failed">\n<test-suite result="Failed" site="TearDown">\n'
                                 '<test-case name="a" result="Passed" />\n</test-suite>\n</test-run>'),
                        'reports a failed suite or run')

    def test_a_case_whose_result_sits_on_a_later_line_is_still_counted(self):
        self.assert_red(WRITE % '<test-run>\n<test-case name="a"\n result="Skipped" />\n</test-run>',
                        'no test executed on either platform')

    def test_a_failed_test_fails(self):
        self.assert_red(WRITE % '<test-run><test-case name="a" result="Failed" /></test-run>',
                        'reports 1 failed test(s)')

    def test_a_nonzero_editor_exit_fails_even_with_passing_results(self):
        self.assert_red((WRITE % '<test-run><test-case name="a" result="Passed" /></test-run>')
                        .replace('exit 0\n', 'exit 1\n'), 'FAIL [unity]: EditMode tests failed')

    def test_a_run_that_executed_a_passing_test_passes(self):
        code, out = self.run_gate(WRITE % '<test-run><test-case name="a" result="Passed" /></test-run>')
        self.assertEqual(code, 0, out)
        self.assertIn('UNITY GATE: PASS', out)


if __name__ == '__main__':
    unittest.main()
