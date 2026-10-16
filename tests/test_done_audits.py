"""A closed task cannot survive in an audit, in history or the staged index."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DoneAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kit-done-audit-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        self.git('init', '-q')
        self.git('-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                 '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                 'commit', '-q', '--allow-empty', '-m', 'close K4', '-m', 'Done: K4')
        self.state = self.repo / 'docs/STATE.md'
        self.audit = self.repo / 'docs/audits/audit space ü.md'
        self.audit.parent.mkdir(parents=True)
        self.state.write_text('# STATE\n\n## Active work\n', encoding='utf-8')
        self.audit.write_text('- K4: unresolved finding\n', encoding='utf-8')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, env=self.env,
                              check=True, capture_output=True)

    def test_history_gate_rejects_an_audit_and_accepts_a_different_id_or_removed_line(self):
        # Execute only the production Done: block, not the full gate or its self-test.
        source = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
        block = source.split('# Finished work.', 1)[1].split('# A [LESSON]', 1)[0]
        work = self.repo / 'scratch'
        work.mkdir()
        script = ('work=%s\nGATE_SELFTEST_STATE_FILE=%s\nGATE_SELFTEST_HISTORY=%s\n'
                  'fail=0\nfixture_env() { :; }\n# Finished work.%s\nexit "$fail"\n') % (
                      shlex.quote(work.as_posix()), shlex.quote(self.state.as_posix()),
                      shlex.quote(self.repo.as_posix()), block)
        for text, expected in (('- K4: unresolved\n', 1), ('- K4b: another task\n', 0), ('', 0)):
            with self.subTest(text=text):
                self.audit.write_text(text, encoding='utf-8')
                result = subprocess.run(['sh', '-c', script], cwd=self.repo, env=self.env,
                                        capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                if expected:
                    self.assertIn('audit space ü.md:1 names K4', result.stdout)
                    self.assertIn('FAIL [state]', result.stdout)

    def test_commit_hook_reads_the_staged_audit_and_accepts_its_removal(self):
        message = self.repo / 'message'
        message.write_text('close\n\nDone: K4\n', encoding='utf-8')
        self.git('add', 'docs')
        # A working-tree deletion must not hide the line this commit still records.
        self.audit.write_text('', encoding='utf-8')
        for staged, expected in ((True, 1), (False, 0)):
            with self.subTest(staged=staged):
                if not staged:
                    self.git('add', 'docs')
                result = subprocess.run(['sh', str(ROOT / 'core/.githooks/commit-msg'), str(message)],
                                        cwd=self.repo, env=dict(self.env, GIT_LITERAL_PATHSPECS='1'),
                                        capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                if expected:
                    self.assertIn('closes K4 but docs/audits/audit space ü.md still mentions it', result.stderr)


if __name__ == '__main__':
    unittest.main()
