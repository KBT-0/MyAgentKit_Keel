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
    def run_gate(self, stub_body, stub_name='unity-stub', project=True, tools=None):
        """tools: {name: script} put first on PATH, as stand-ins for the host's own."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'scripts').mkdir()
            (tmp / 'scripts/unity_gate.sh').write_bytes(GATE.read_bytes())
            if project:
                (tmp / 'proj/ProjectSettings').mkdir(parents=True)
            stub = tmp / stub_name
            stub.write_text(stub_body, encoding='utf-8', newline='\n')
            stub.chmod(0o755)
            env = dict(os.environ, UNITY_PATH=stub.as_posix(), UNITY_PROJECT=(tmp / 'proj').as_posix())
            if tools:
                (tmp / 'tools').mkdir()
                for name, body in tools.items():
                    (tmp / 'tools' / name).write_text(body, encoding='utf-8', newline='\n')
                    (tmp / 'tools' / name).chmod(0o755)
                env['PATH'] = str(tmp / 'tools') + os.pathsep + env['PATH']
            result = subprocess.run(['sh', 'scripts/unity_gate.sh'], cwd=tmp, capture_output=True, text=True,
                                    env=env, timeout=60)
            self.project_created = (tmp / 'proj').exists()
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

    def test_an_exe_editor_on_git_for_windows_is_run_with_cygpath_paths(self):
        # #175: Git for Windows has cygpath, never wslpath; Unity.exe was refused there. The host
        # is named by a stand-in uname, so this runs the same on every machine.
        code, out = self.run_gate(WRITE % '<test-run><test-case name="a" result="Passed" /></test-run>',
                                  stub_name='Unity.exe',
                                  tools={'uname': '#!/bin/sh\necho MINGW64_NT-10.0-26300\n',
                                         'cygpath': '#!/bin/sh\n[ "$1" = -m ] || exit 1\nprintf \'%s\\n\' "$2"\n'})
        self.assertEqual(code, 0, out)
        self.assertIn('UNITY GATE: PASS', out)

    def test_unity_s_separate_cli_is_named_not_reported_as_failed_tests(self):
        # #175: Unity's CLI, also named unity, rejects the editor's flags.
        code, out = self.run_gate('#!/bin/sh\necho "error: unknown option \'-batchmode\'" >&2\nexit 2\n')
        self.assertEqual(code, 1, out)
        self.assertIn('is not the Unity Editor (it rejected -batchmode', out)
        self.assertNotIn('tests failed', out)
        self.assertIn('UNITY GATE: FAIL', out)

    def test_a_missing_project_folder_is_refused_and_not_created(self):
        code, out = self.run_gate(WRITE % '<test-run><test-case name="a" result="Passed" /></test-run>',
                                  project=False)
        self.assertEqual(code, 1, out)
        self.assertIn('is not a Unity project (no ProjectSettings folder)', out)
        self.assertFalse(self.project_created, out)

    def test_a_run_that_executed_a_passing_test_passes(self):
        code, out = self.run_gate(WRITE % '<test-run><test-case name="a" result="Passed" /></test-run>')
        self.assertEqual(code, 0, out)
        self.assertIn('UNITY GATE: PASS', out)


if __name__ == '__main__':
    unittest.main()
