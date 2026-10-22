# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""owns_check.py must refuse every changed path outside the brief's Owns: line, in each review scope."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parent / 'owns_check.py'
# Every bound here times MYAGENTKIT_TEST_TIMEOUT_SCALE: check_kit raises it while units run side by side.
SCALE = float(os.environ.get('MYAGENTKIT_TEST_TIMEOUT_SCALE', '1'))


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
                                capture_output=True, text=True, timeout=30 * SCALE)
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

    def test_merge_commit_and_diverged_base_see_what_the_review_sees(self):
        # The review diffs a commit against its first parent (merges too) and a base as REF...HEAD.
        main = self.git('rev-parse', '--abbrev-ref', 'HEAD').stdout.decode().strip()
        self.git('checkout', '-qb', 'side')
        self.write('other.txt')
        self.commit()
        self.git('checkout', '-q', main)
        self.write('src/a.py')
        self.commit()
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'core.hooksPath=',
                 'merge', '-q', '--no-ff', '--no-edit', 'side')
        self.assertIn('  other.txt\n', self.check('Owns: src/', '--commit', 'HEAD')[1])
        # A base that made the same out-of-scope edit on its own still leaves it in REF...HEAD.
        self.git('checkout', '-qb', 'base', 'HEAD~1')
        self.write('other.txt')
        self.commit()
        self.git('checkout', '-q', 'side')
        self.assertIn('  other.txt\n', self.check('Owns: src/', '--base', 'base')[1])

    def test_no_owns_line_fails_closed_and_a_bad_call_is_an_error(self):
        self.write('other.txt')
        code, errors = self.check('Files: src/')
        self.assertEqual(code, 2)
        self.assertIn(str(self.brief), errors)
        self.assertEqual(self.check('Owns:')[0], 2)
        self.assertEqual(self.check('Owns: src/', '--base')[0], 2)
        self.assertEqual(self.check('Owns: src/', '--base', '--output=x')[0], 2)
        self.assertEqual(self.check('Owns: src/', '--base', 'no-such-ref')[0], 2)

    def test_numbered_bold_owns_is_checked(self):
        self.write('other.txt')
        for prefix in ('3. **Owns:**', '3) **Owns:**'):
            code, errors = self.check(prefix + ' src/')
            self.assertEqual(code, 1, errors)
            self.assertIn('  other.txt\n', errors)

    def test_globs_follow_git_rules(self):
        # fnmatch let '*' cross '/' (`*.md` owned docs/DESIGN.md) and needed a folder for '**/'.
        for path in ('top.md', 'docs/DESIGN.md', 'tests/test_a/deep/b.py', 'src/sim/b.cpp', 'src/sim/x/y/c.cpp'):
            self.write(path)
        code, errors = self.check('Owns: *.md, tests/test_*.py, src/sim/**/*.cpp')
        self.assertEqual(code, 1, errors)
        self.assertEqual(errors.split(':\n', 1)[1], '  docs/DESIGN.md\n  tests/test_a/deep/b.py\n')
        code, errors = self.check('Owns: docs/**, tests/**, src/**/b.cpp, src/**/c.cpp')
        self.assertEqual(errors.split(':\n', 1)[1], '  top.md\n')

    def test_owns_in_a_code_block_is_skipped_and_a_second_line_is_refused(self):
        # An example `Owns: *` in a fenced block above the real line owned every path.
        self.write('other.txt')
        for brief in ('```\nOwns: *\n```\nOwns: src/', '~~~~md\nOwns: *\n~~~~\n> Owns: src/'):
            code, errors = self.check(brief)
            self.assertEqual(code, 1, errors)
            self.assertIn('  other.txt\n', errors)
        code, errors = self.check('Owns: *\nOwns: src/')
        self.assertEqual(code, 2)
        self.assertIn('2 Owns: lines', errors)
        # An unclosed fence hides the rest, so the brief is refused.
        self.assertEqual(self.check('```\nOwns: *')[0], 2)
        code, errors = self.check('Owns: src/\n```\nx')
        self.assertEqual(code, 2)
        self.assertIn('unclosed code fence', errors)

    def test_a_list_item_fence_and_inline_backticks_pair_as_commonmark_pairs_them(self):
        # A fence opened after a list marker went unseen: its indented closer opened a block to
        # the end, hid the real Owns: line and left the example `Owns: **` owning every path.
        self.write('other.txt')
        for brief in ('- ```\n  Owns: **\n  ```\nOwns: src/', '```inline``` prose\nOwns: src/'):
            code, errors = self.check(brief)
            self.assertEqual(code, 1, errors)
            self.assertIn('  other.txt\n', errors)

    def test_worker_reports_are_allowed_only_at_the_repository_root(self):
        for name in ('RESULT-worker.md', 'QUESTION-worker.md'):
            self.write(name)
        self.assertEqual(self.check('Owns: src/')[0], 0)
        for name in ('nested/RESULT-worker.md', 'RESULT-worker.py', 'QUESTION.md'):
            self.write(name)
            self.assertIn('  ' + name + '\n', self.check('Owns: src/')[1])

    def test_review_sh_checks_the_linked_worktree_it_runs_in(self):
        # #302: the main checkout's review.sh run from a worker's linked worktree diffed the
        # main checkout, so an unrelated commit on main left the brief's Owns: line.
        scripts = self.repo / 'scripts'
        scripts.mkdir()
        for name in ('review.sh', 'owns_check.py'):
            (scripts / name).write_bytes((SCRIPT.parent / name).read_bytes())
        (scripts / 'review_dispatch.py').write_text('import os; print("dispatched in", os.getcwd())\n',
                                                    encoding='utf-8')
        self.commit()
        base = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        worktree = Path(self.tmp.name) / 'worktree'
        self.git('worktree', 'add', '-q', '-b', 'worker', str(worktree))
        self.write('other.txt')
        self.commit()
        (worktree / 'src/a.py').write_text('worker\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(worktree), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', '-c', 'core.hooksPath=', '-c', 'commit.gpgsign=false',
                        'commit', '-qam', 'worker'], check=True, capture_output=True)
        env = {k: v for k, v in os.environ.items() if k != 'REVIEW_REPO_ROOT'}
        env['REVIEW_TASK_FILE'] = str(self.brief)
        other = Path(self.tmp.name) / 'other'
        other.mkdir()
        subprocess.run(['git', 'init', '-q', str(other)], check=True, capture_output=True)
        # An unrelated repository's folder keeps the script's own checkout, main's commit included,
        # and REVIEW_REPO_ROOT names the reviewed checkout even from a linked worktree.
        for cwd, root, owns, reviewed in ((worktree, None, 'src/', worktree),
                                          (other, None, 'src/, other.txt', self.repo),
                                          (worktree, self.repo, 'src/, other.txt', self.repo)):
            with self.subTest(cwd=cwd.name, root=root):
                self.brief.write_text('Task: fixture.\nOwns: %s\n' % owns, encoding='utf-8')
                result = subprocess.run(['sh', str(scripts / 'review.sh'), '--base', base], cwd=cwd,
                                        env=dict(env, REVIEW_REPO_ROOT=str(root)) if root else env,
                                        capture_output=True, text=True, timeout=60 * SCALE)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(Path(result.stdout.split('dispatched in ', 1)[1].strip()).resolve(),
                                 reviewed.resolve())


if __name__ == '__main__':
    unittest.main()
