"""Git itself must call the shipped hooks: on a clean merge commit and on every commit message."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
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
        # C locale: the hook recognises the English text git writes under the scissors line.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_EDITOR='true',
                   LC_ALL='C', LANGUAGE='C')
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
                            'Generated with Google Gemini',
                            # Git takes whitespace before the separator and a folded value.
                            'Co-Authored-By : Claude <noreply@anthropic.com>',
                            'Co-Authored-By:\n  Claude <noreply@anthropic.com>',
                            'Co-authored-by: Helper\n\t<helper@ampcode.com>'):
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
                            'Co-authored-by:\n  Claude Monet <claude.monet@example.invalid>',
                            'Bump openai SDK to the next minor version'):
                with self.subTest(trailer=trailer):
                    result = self.commit(root, git, trailer + '\n')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_trailer_quoted_in_a_commit_v_diff_is_rejected_with_the_way_out(self):
        # The hook cannot tell git's editor header from the same text given with -m, so it
        # cuts nothing: a credit quoted in the diff below the scissors line fails closed.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            (root / 'notes').write_text('changed\nCo-Authored-By: Claude <noreply@anthropic.com>\n')
            git('add', 'notes')
            result = git('commit', '-q', '-v', '-e', '-m', 'edit notes', check=False)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('commit without -v, or remove the quoted line', result.stderr)

    def test_a_scissors_line_cuts_nothing(self):
        # With -m git keeps a scissors line and everything below it, the complete header
        # git writes for an editor included.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            cut = '# ------------------------ >8 ------------------------\n'
            explain = '# Do not modify or remove the line above.\n'
            for below in ('', explain, explain + '# Everything below it will be ignored.\n'):
                with self.subTest(below=below):
                    result = self.commit(root, git, cut + below
                                         + 'Co-Authored-By: Claude <noreply@anthropic.com>\n')
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('crediting an AI tool', result.stderr)

    def test_a_commented_out_trailer_is_checked(self):
        # Git keeps a "#" line under -m or verbatim cleanup, so a commented trailer is a trailer.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            # An alphanumeric core.commentChar too: "x Co-Authored-By: ..." is kept like "# ...".
            for char in ('#', ';', 'x'):
                with self.subTest(char=char):
                    git('config', 'core.commentChar', char)
                    result = self.commit(root, git, 'x\n' + char
                                         + ' Co-Authored-By: Claude <noreply@anthropic.com>\n')
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('crediting an AI tool', result.stderr)

    def test_core_comment_string_takes_precedence_over_comment_char(self):
        # Git 2.45 added core.commentString, which wins over core.commentChar: a hook that read
        # only commentChar skipped the wrong prefix and passed "x Co-Authored-By: ...".
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            version = git('--version').stdout.split()[2]
            if tuple(int(part) for part in version.split('.')[:2]) < (2, 45):
                sys.stderr.write('NOT RUN: core.commentString needs git 2.45, this is %s\n' % version)
                return
            git('config', 'core.commentChar', ';')
            git('config', 'core.commentString', 'x')
            result = self.commit(root, git, 'y\nx Co-Authored-By: Claude <noreply@anthropic.com>\n')
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('crediting an AI tool', result.stderr)

    def test_the_owner_may_allow_ai_attribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            (root / 'AGENTS.md').write_text('AI tools may be credited.\n')
            result = self.commit(root, git, 'Co-Authored-By: Claude <noreply@anthropic.com>\n')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_comment_lines_are_checked_whatever_git_would_do_with_them(self):
        # Whether git keeps a "#" line depends on commit.cleanup, a --cleanup flag the hook
        # cannot see, and -m versus the editor (git's default keeps them for -m). The hook
        # fails closed on every one of them, with either comment char.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            cases = ((('commit.cleanup', 'verbatim'), ()), (('commit.cleanup', 'whitespace'), ()),
                     (('core.commentChar', ';'), ()), (('core.commentChar', '#'), ('--cleanup=strip',)))
            for config, flags in cases:
                with self.subTest(config=config, flags=flags):
                    git('config', *config)
                    char = ';' if config == ('core.commentChar', ';') else '#'
                    try:
                        # Each case its own content: an unchanged tree would fail as "nothing to commit".
                        result = self.commit(root, git, '='.join(config) + '\n' + char
                                             + ' Generated with Claude\n', *flags)
                    finally:
                        git('config', '--unset', config[0])
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('crediting an AI tool', result.stderr)

    def test_a_gate_that_did_not_run_blocks_the_commit_as_not_run(self):
        # Exit 75 is "another gate run holds the lock": the commit stays blocked, and the
        # message says the gate did not run rather than that it failed.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            shutil.copyfile(ROOT / 'core/scripts/check.sh', root / 'scripts/check.sh')
            # The lock is a kernel lock: hold it the way the gate does, through fcntl.flock.
            holder = subprocess.Popen(
                [sys.executable, '-c',
                 'import fcntl, sys, time; f = open(sys.argv[1], "a+"); '
                 'fcntl.flock(f, fcntl.LOCK_EX); print("held", flush=True); time.sleep(60)',
                 str(root / '.git/check.lock')], stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(holder.stdout.readline().strip(), 'held')
                (root / 'c').write_text('locked\n')
                git('add', 'c')
                result = subprocess.run(
                    ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                     '-c', 'core.hooksPath=.githooks', 'commit', '-q', '-m', 'locked'],
                    cwd=root, capture_output=True, text=True, timeout=60,
                    env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                             GATE_LOCK_WAIT='1'))
            finally:
                holder.kill()
                holder.wait()
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('check.sh did NOT RUN (another gate run holds the lock); commit blocked',
                          result.stderr)
            self.assertNotIn('FAILED', result.stderr)

    def test_an_unreadable_agents_file_fails_closed(self):
        # A grep that could not read the rule is not an owner's choice to allow AI credit.
        # A directory cannot be read by any user, root included; mode 000 stops everyone but
        # root, so under root that variant says it did not run instead of passing silently.
        for damage in ('directory', 'mode 000'):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as tmp:
                root, git = self.repo(tmp)
                agents = root / 'AGENTS.md'
                if damage == 'directory':
                    agents.unlink()
                    agents.mkdir()
                elif os.geteuid() == 0:
                    sys.stderr.write('NOT RUN: unreadable AGENTS.md (mode 000) under root; '
                                     'the directory case covers the read failure\n')
                    continue
                else:
                    agents.chmod(0)
                try:
                    result = self.commit(root, git, 'Co-Authored-By: Claude <noreply@anthropic.com>\n')
                finally:
                    agents.chmod(0o755 if damage == 'directory' else 0o644)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('cannot read AGENTS.md', result.stderr)


if __name__ == '__main__':
    unittest.main()
