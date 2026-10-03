"""Git itself must call the shipped hooks: on a clean merge commit and on every commit message."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GitHookTests(unittest.TestCase):
    def repo(self, tmp):
        root = Path(tmp)
        shutil.copytree(ROOT / 'core/.githooks', root / '.githooks')
        (root / 'scripts').mkdir()
        # A stub gate: each branch alone is green, the two together are red.
        (root / 'scripts/check.sh').write_text(
            'echo ran >> .git/gate-runs\n[ ! -e a ] || [ ! -e b ] || { echo "CHECK: FAIL"; exit 1; }\n')
        (root / 'scripts/check.sh').chmod(0o755)
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_EDITOR='true')
        git = lambda *args, check=True: subprocess.run(
            ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
             '-c', 'core.hooksPath=.githooks', *args],
            cwd=root, env=env, capture_output=True, text=True, check=check)
        # init then checkout: `git init -b` needs git 2.28, older than some CI images carry.
        git('init', '-q')
        git('checkout', '-q', '-b', 'main')
        (root / 'AGENTS.md').write_text('- **No AI attribution in git.**\n')
        # A quoted trailer in a tracked file shows up in `git commit -v`'s diff below the scissors.
        (root / 'notes').write_text('top\nCo-Authored-By: Claude <noreply@anthropic.com>\n')
        git('add', '-A')
        git('commit', '-q', '-m', 'base')
        return root, git

    def test_a_clean_merge_into_a_red_tree_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            for branch in ('a', 'b'):
                git('checkout', '-q', '-b', branch, 'main')
                (root / branch).write_text(branch + '\n')
                git('add', branch)
                git('commit', '-q', '-m', 'add ' + branch)
            git('checkout', '-q', 'a')
            runs = (root / '.git/gate-runs').read_text().count('ran')
            merge = git('merge', '-q', '--no-edit', 'b', check=False)
            self.assertNotEqual(merge.returncode, 0, 'a clean merge into a red tree was committed')
            self.assertGreater((root / '.git/gate-runs').read_text().count('ran'), runs)
            self.assertEqual(git('rev-list', '--count', 'HEAD').stdout.strip(), '2')

    def commit(self, root, git, message, *opts):
        (root / 'c').write_text(message)
        git('add', 'c')
        return git('commit', '-q', *opts, '-m', 'change c', '-m', message, check=False)

    def test_an_ai_co_author_trailer_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            for trailer in ('Co-Authored-By: Claude <noreply@anthropic.com>',
                            'co-authored-by: GitHub Copilot <copilot@github.com>',
                            'Co-authored-by: Amp <amp@ampcode.com>',
                            'Co-authored-by: Helper <helper@ampcode.com>',
                            'Co-authored-by: some-agent[bot] <1+some-agent[bot]@users.noreply.github.com>',
                            'Co-authored-by: GPT-5 <noreply@example.invalid>',
                            'Co-authored-by: Qwen-Coder <qwen@example.invalid>',
                            'Co-authored-by: Cline <cline@example.invalid>',
                            'Co-authored-by: Kiro <kiro@example.invalid>',
                            'Co-authored-by: Claude Opus 5.5 <noreply@example.invalid>',
                            'Co-authored-by: aider (openai/gpt-4o) <aider@example.invalid>',
                            'Signed-off-by: Claude <noreply@example.invalid>',
                            'Assisted-by: Claude:claude-opus',
                            '\U0001f916 Generated with [Claude Code](https://example.invalid)',
                            'Generated with GitHub Copilot',
                            'Generated with Google Gemini'):
                with self.subTest(trailer=trailer):
                    result = self.commit(root, git, trailer + '\n')
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_human_or_a_quoted_trailer_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            for trailer in ('Co-authored-by: A Person <person@example.invalid>',
                            'Co-authored-by: Claude Monet <claude.monet@example.invalid>',
                            'Co-authored-by: Devin Smith <devin@example.invalid>',
                            'Co-authored-by: Ana Raider <ana@example.invalid>',
                            'Co-authored-by: Jo Park <jo@precursor.example.invalid>',
                            'Signed-off-by: Paola Geminiani <paola@example.invalid>',
                            'Bump openai SDK to the next minor version'):
                with self.subTest(trailer=trailer):
                    result = self.commit(root, git, trailer + '\n')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # git commit -v: the hook sees the diff below the scissors line before git strips it.
            (root / 'notes').write_text('changed\nCo-Authored-By: Claude <noreply@anthropic.com>\n')
            git('add', 'notes')
            result = git('commit', '-q', '-v', '-e', '-m', 'edit notes', check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_owner_may_allow_ai_attribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            (root / 'AGENTS.md').write_text('AI tools may be credited.\n')
            result = self.commit(root, git, 'Co-Authored-By: Claude <noreply@anthropic.com>\n')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_comment_lines_are_checked_where_git_keeps_them(self):
        # Git keeps "#" lines under commit.cleanup=verbatim (and whitespace), and with another
        # core.commentChar it keeps "#" lines and strips that character's instead.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            for config in (('commit.cleanup', 'verbatim'), ('commit.cleanup', 'whitespace'),
                           ('core.commentChar', ';')):
                with self.subTest(config=config):
                    git('config', *config)
                    try:
                        # Each case its own content: an unchanged tree would fail as "nothing to commit".
                        result = self.commit(root, git, '='.join(config) + '\n# Generated with Claude\n')
                    finally:
                        git('config', '--unset', config[0])
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('crediting an AI tool', result.stderr)
            # A comment line git strips is not part of the message, with either comment char.
            for char in ('#', ';'):
                with self.subTest(char=char):
                    git('config', 'core.commentChar', char)
                    result = self.commit(root, git, 'body\n' + char + ' Generated with Claude\n',
                                         '--cleanup=strip')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    log = git('log', '-1', '--format=%B').stdout
                    self.assertNotIn('Generated with Claude', log)

    def test_an_unreadable_agents_file_fails_closed(self):
        # A grep that could not read the rule is not an owner's choice to allow AI credit.
        if os.geteuid() == 0:
            return  # root reads a mode-000 file; this case cannot be built here
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            (root / 'AGENTS.md').chmod(0)
            try:
                result = self.commit(root, git, 'Co-Authored-By: Claude <noreply@anthropic.com>\n')
            finally:
                (root / 'AGENTS.md').chmod(0o644)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('cannot read AGENTS.md', result.stderr)


if __name__ == '__main__':
    unittest.main()
