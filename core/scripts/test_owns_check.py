"""owns_check.py must refuse every changed path outside the brief's Owns: line, in each review scope."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parent / 'owns_check.py'


class OwnsCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / 'repo'
        self.repo.mkdir()
        self.brief = Path(self.tmp.name) / 'brief.md'
        self.git('init', '-q')
        self.git('config', 'core.autocrlf', 'false')
        for path in ('src/a.py', 'docs/STATE.md', 'tests/test_a.py', 'other.txt'):
            self.write(path, 'one\n')
        self.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)

    def commit(self):
        self.git('add', '-A')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'core.hooksPath=',
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')

    def write(self, path, text='changed\n'):
        (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / path).write_text(text, encoding='utf-8')

    def check(self, owns, *scope):
        self.brief.write_text('Task: fixture.\n' + owns + '\n', encoding='utf-8')
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.brief), *scope], cwd=self.repo,
                                capture_output=True, text=True, timeout=30)
        return result.returncode, result.stderr

    def test_uncommitted_counts_untracked_and_renamed_paths_and_allows_state(self):
        self.write('src/a.py')
        self.write('src/new/b.py')
        self.write('docs/STATE.md')
        self.write('tests/test_b.py')
        self.assertEqual(self.check('- **Owns:** `src/`, tests/test_*.py')[0], 0)
        self.git('mv', 'other.txt', 'src/other.txt')
        code, errors = self.check('Owns: src/, tests/test_*.py', '--uncommitted')
        self.assertEqual(code, 1, errors)
        self.assertIn('  other.txt\n', errors)
        self.assertNotIn('src/', errors.split(':\n', 1)[1])
        # A folder pattern owns that folder, not a sibling sharing the prefix.
        self.write('srcx/c.py')
        self.assertIn('  srcx/c.py\n', self.check('Owns: src/, other.txt, tests/')[1])

    def test_base_and_commit_scopes_see_committed_changes(self):
        self.write('other.txt')
        self.commit()
        self.write('src/untracked.py')
        for scope in (('--base', 'HEAD~1'), ('--commit', 'HEAD')):
            with self.subTest(scope=scope):
                code, errors = self.check('Owns: src/', *scope)
                self.assertEqual(code, 1, errors)
                self.assertIn('  other.txt\n', errors)
        self.assertIn('  src/untracked.py\n', self.check('Owns: other.txt', '--base', 'HEAD~1')[1])
        self.assertNotIn('untracked', self.check('Owns: other.txt', '--commit', 'HEAD')[1])
        # The root commit has no parent and is still checked.
        root = self.git('rev-list', '--max-parents=0', 'HEAD').stdout.decode().strip()
        self.assertIn('  other.txt\n', self.check('Owns: src/', '--commit', root)[1])

    def test_no_owns_line_checks_nothing_and_a_bad_call_is_an_error(self):
        self.write('other.txt')
        self.assertEqual(self.check('Files: src/')[0], 0)
        self.assertEqual(self.check('Owns:')[0], 2)
        self.assertEqual(self.check('Owns: src/', '--base')[0], 2)
        self.assertEqual(self.check('Owns: src/', '--base', '--output=x')[0], 2)
        self.assertEqual(self.check('Owns: src/', '--base', 'no-such-ref')[0], 2)


if __name__ == '__main__':
    unittest.main()
