"""Git itself must call the shipped hooks: on a clean merge commit and on every commit message."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kit_check', ROOT / 'scripts/check_kit.py')
kit_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit_check)


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
        git = lambda *args, check=True, **extra: subprocess.run(
            ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
             '-c', 'core.hooksPath=.githooks', *args],
            cwd=root, env=dict(env, **extra), capture_output=True, text=True, check=check)
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

    def commit(self, root, git, message, *opts, **extra):
        (root / 'c').write_text(message)
        git('add', 'c')
        return git('commit', '-q', *opts, '-m', 'change c', '-m', message, check=False, **extra)

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
                            'Co-authored-by: Helper\n\t<helper@ampcode.com>',
                            # A quoted display name is still the tool's name.
                            'Co-Authored-By: "GitHub Copilot" <copilot@github.com>',
                            "Co-Authored-By: 'Claude' <noreply@example.invalid>",
                            'Co-authored-by: "Claude Opus 5.5" <noreply@example.invalid>',
                            # A tool name folded over several lines is the tool's name once joined.
                            'Co-authored-by:\n  Claude\n  Opus 5.5 <noreply@example.invalid>',
                            'Co-authored-by:\n  GitHub\n  Copilot <copilot@example.invalid>',
                            # A whitespace-only line ends the value: unfolded across it, the
                            # indented prose below hid the bare tool name.
                            'Co-Authored-By: Claude\n \n  Additional notes',
                            'Co-Authored-By: Claude\n\t\n\tAdditional notes',
                            # Current model and tool names, with an address no domain rule knows.
                            'Co-Authored-By: Claude Fable 5.1 <noreply@example.invalid>',
                            'Co-Authored-By: Claude Mythos 5.1 <noreply@example.invalid>',
                            'Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@example.invalid>',
                            'Co-authored-by: opencode <opencode@example.invalid>',
                            'Co-authored-by: Junie <junie@example.invalid>',
                            'Co-authored-by: OpenHands <openhands@example.invalid>',
                            'Co-authored-by: Warp <agent@example.invalid>'):
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
                            # Only the completed value is matched: a partial fold read
                            # "Co-authored-by: Claude" and rejected the painter.
                            'Co-authored-by:\n  Claude\n  Monet <claude.monet@example.invalid>',
                            'Co-authored-by: Claude\n  Monet <claude.monet@example.invalid>',
                            'Co-authored-by: "Claude Monet" <claude.monet@example.invalid>',
                            "Co-authored-by: 'A Person' <person@example.invalid>",
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

    def test_the_comment_setting_git_reads_last_is_the_one_skipped(self):
        # Git 2.45 added core.commentString as an alias of core.commentChar, and the one set
        # last wins: a hook that read only commentChar, or preferred commentString wherever it
        # was set, skipped the wrong prefix and passed "x Co-Authored-By: ...". The hook runs
        # directly, with git reporting 2.45: on an older git this case returned early and
        # counted as a pass. Reading both keys in order works on any git.
        real_git = shutil.which('git')
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            shim = Path(tmp) / 'shim'
            shim.mkdir()
            (shim / 'git').write_text('#!/bin/sh\n[ "$1" != version ] || { echo "git version 2.45.0"; exit 0; }\n'
                                      'exec %s "$@"\n' % real_git)
            (shim / 'git').chmod(0o755)
            glob = Path(tmp) / 'global.gitconfig'
            # (global settings, local settings), each in the order written; x is set last.
            for case, scopes in enumerate((((), (('commentChar', ';'), ('commentString', 'x'))),
                           ((), (('commentString', 'y'), ('commentChar', 'x'))),
                           ((('commentString', 'y'),), (('commentChar', 'x'),)),
                           ((('commentChar', 'y'),), (('commentString', 'x'),)))):
                with self.subTest(scopes=scopes):
                    glob.write_text('')
                    git('config', '--local', '--remove-section', 'core', check=False)
                    for key, value in scopes[0]:
                        git('config', '--file', str(glob), 'core.' + key, value)
                    for key, value in scopes[1]:
                        git('config', '--local', 'core.' + key, value)
                    (root / 'msg').write_text('y%d\n\nx Co-Authored-By: Claude <noreply@anthropic.com>\n'
                                              % case)
                    result = subprocess.run(['sh', '.githooks/commit-msg', 'msg'], cwd=root, text=True,
                                            capture_output=True,
                                            env=dict(os.environ, GIT_CONFIG_GLOBAL=str(glob),
                                                     GIT_CONFIG_NOSYSTEM='1',
                                                     PATH='%s%s%s' % (shim, os.pathsep, os.environ['PATH'])))
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('crediting an AI tool', result.stderr)

    def test_a_git_before_2_45_reads_only_comment_char(self):
        # Git before 2.45 ignores core.commentString: with commentChar=x set before
        # commentString=y it keeps "x Co-Authored-By: ..." under -m, and a hook that took the
        # last of the two skipped only "y" and passed it.
        real_git = shutil.which('git')
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            git('config', 'core.commentChar', 'x')
            git('config', 'core.commentString', 'y')
            shim = Path(tmp) / 'shim'
            shim.mkdir()
            (shim / 'git').write_text('#!/bin/sh\n[ "$1" != version ] || { echo "git version 2.44.0"; exit 0; }\n'
                                      'exec %s "$@"\n' % real_git)
            (shim / 'git').chmod(0o755)
            (root / 'msg').write_text('change c\n\nx Co-Authored-By: Claude <noreply@anthropic.com>\n')
            result = subprocess.run(['sh', '.githooks/commit-msg', 'msg'], cwd=root, text=True,
                                    capture_output=True,
                                    env=dict(os.environ, PATH='%s%s%s' % (shim, os.pathsep, os.environ['PATH'])))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('crediting an AI tool', result.stderr)

    def test_a_configured_trailer_separator_is_a_separator(self):
        # With trailer.separators set, git takes "Co-Authored-By=Claude" as a trailer; the
        # hook's expressions required a colon and passed it.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            for separators in ('=', '#=', ']-^'):
                with self.subTest(separators=separators):
                    git('config', 'trailer.separators', separators)
                    for sep in separators:
                        result = self.commit(root, git, 'Co-Authored-By%s Claude <noreply@anthropic.com>\n' % sep)
                        self.assertNotEqual(result.returncode, 0, sep + result.stdout + result.stderr)
                        self.assertIn('crediting an AI tool', result.stderr)
                    # The default colon stays a separator whatever is configured.
                    result = self.commit(root, git, 'Co-Authored-By: Claude <noreply@anthropic.com>\n')
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    result = self.commit(root, git, 'Co-authored-by%s A Person <person@example.invalid>\n'
                                         % separators[0])
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_failed_config_transformation_fails_closed(self):
        # The tr results were unchecked: a failed one left only ":" as a separator, and
        # "Co-Authored-By=Claude" passed; a failed comment-prefix one passed "x Co-Authored-By".
        real_tr = shutil.which('tr')
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            shim = Path(tmp) / 'shim'
            shim.mkdir()
            for flag, key, value, line in (('-cd', 'core.commentChar', 'x', 'x Co-Authored-By: Claude'),
                                           ('-d', 'trailer.separators', '=', 'Co-Authored-By=Claude')):
                with self.subTest(transformation=key):
                    git('config', key, value)
                    (shim / 'tr').write_text('#!/bin/sh\n[ "$1" != %s ] || exit 1\nexec %s "$@"\n'
                                             % (flag, real_tr))
                    (shim / 'tr').chmod(0o755)
                    (root / 'msg').write_text('change c\n\n%s <noreply@anthropic.com>\n' % line)
                    result = subprocess.run(['sh', '.githooks/commit-msg', 'msg'], cwd=root, text=True,
                                            capture_output=True,
                                            env=dict(os.environ, PATH='%s%s%s' % (shim, os.pathsep,
                                                                                   os.environ['PATH'])))
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('cannot parse %s' % key, result.stderr)
                    git('config', '--unset', key)

    def test_a_failed_config_read_fails_closed(self):
        # Only an absent key (git config exit 1) means the default: a failed read of
        # trailer.separators left only ":" as a separator and "Co-Authored-By=Claude" passed.
        real_git = shutil.which('git')
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            shim = Path(tmp) / 'shim'
            shim.mkdir()
            # The comment settings are read together, in configuration order.
            for key, read, line in (('trailer.separators', 'trailer.separators', 'Co-Authored-By=Claude'),
                                    ('core.commentChar or core.commentString', '^core\\.comment',
                                     'x Co-Authored-By: Claude')):
                with self.subTest(key=key):
                    (shim / 'git').write_text('#!/bin/sh\ncase " $* " in " config "*\'%s\'*) exit 3 ;; esac\n'
                                              'exec %s "$@"\n' % (read, real_git))
                    (shim / 'git').chmod(0o755)
                    (root / 'msg').write_text('change c\n\n%s <noreply@anthropic.com>\n' % line)
                    result = subprocess.run(['sh', '.githooks/commit-msg', 'msg'], cwd=root, text=True,
                                            capture_output=True,
                                            env=dict(os.environ, PATH='%s%s%s' % (shim, os.pathsep,
                                                                                   os.environ['PATH'])))
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('cannot read %s' % key, result.stderr)

    def test_a_missing_agents_file_keeps_the_hook_on(self):
        # Only the owner's choice turns the hook off: an AGENTS.md that is not there is a
        # broken setup, and the credit is still refused.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            (root / 'AGENTS.md').unlink()
            result = self.commit(root, git, 'Co-Authored-By: Claude <noreply@anthropic.com>\n')
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('crediting an AI tool', result.stderr)

    def test_a_tool_that_fails_inside_the_hook_fails_it_closed(self):
        # Each of these once had an unchecked result: a version git did not report, a message
        # that could not be unfolded, or a trailer check that failed would have let the
        # credit below through.
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = self.repo(tmp)
            shim = Path(tmp) / 'shim'
            shim.mkdir()
            (root / 'msg').write_text('change c\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n')
            for tool, broken, message in (
                    ('git', '[ "$1" != version ] || { echo "version unknown"; exit 0; }',
                     'cannot read the git version'),
                    ('awk', 'exit 1', 'cannot unfold the commit message'),
                    ('grep', 'case " $* " in *" -iE "*) exit 2 ;; esac', 'the trailer check itself failed')):
                with self.subTest(tool=tool):
                    for stale in shim.iterdir():
                        stale.unlink()
                    (shim / tool).write_text('#!/bin/sh\n%s\nexec %s "$@"\n' % (broken, shutil.which(tool)))
                    (shim / tool).chmod(0o755)
                    result = subprocess.run(['sh', '.githooks/commit-msg', 'msg'], cwd=root, text=True,
                                            capture_output=True,
                                            env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull,
                                                     GIT_CONFIG_NOSYSTEM='1',
                                                     PATH='%s%s%s' % (shim, os.pathsep, os.environ['PATH'])))
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn(message, result.stderr)

    def test_the_owner_may_allow_ai_attribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            (root / 'AGENTS.md').write_text('AI tools may be credited.\n')
            result = self.commit(root, git, 'Co-Authored-By: Claude <noreply@anthropic.com>\n')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def docs(self, root, git, state='', backlog=''):
        (root / 'docs').mkdir(exist_ok=True)
        (root / 'docs/STATE.md').write_text('# STATE\n\n## Active work\n' + state)
        (root / 'docs/BACKLOG.md').write_text('# BACKLOG\n\n## Next tasks\n' + backlog)
        git('add', 'docs')

    def test_a_done_task_the_staged_state_files_still_mention_is_rejected_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            for state, backlog, where in (('- K4: in flight\n', '', 'docs/STATE.md'),
                                          ('', '- K4 later\n', 'docs/BACKLOG.md')):
                with self.subTest(where=where):
                    self.docs(root, git, state, backlog)
                    result = self.commit(root, git, where + '\n\nDone: K4\n')
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('closes K4 but %s still mentions it' % where, result.stderr)
                    self.assertIn(where + ':4:', result.stderr)
            # The line deleted and staged, the same commit passes; a longer id is another task.
            self.docs(root, git, '- K4b: a different task\n')
            result = self.commit(root, git, 'closed\n\nDone: K4\n')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_index_is_checked_not_the_working_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            self.docs(root, git, '- K4: in flight\n')
            (root / 'docs/STATE.md').write_text('# STATE\n\n## Active work\n')
            result = self.commit(root, git, 'unstaged\n\nDone: K4\n')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('closes K4 but docs/STATE.md', result.stderr)
            self.docs(root, git)
            (root / 'docs/STATE.md').write_text('# STATE\n\n## Active work\n- K4: in flight\n')
            result = self.commit(root, git, 'staged\n\nDone: K4\n')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_every_done_trailer_is_checked_and_must_name_a_task_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            self.docs(root, git, '- L1b: still here\n')
            result = self.commit(root, git, 'two\n\nDone: K4\nDone: L1b\n')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('closes L1b but docs/STATE.md', result.stderr)
            for value in ('K', '4K', 'K4,', 'K4-', 'K-4-a'):
                with self.subTest(value=value):
                    result = self.commit(root, git, value + '\n\nDone: ' + value + '\n')
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("'Done: %s' does not name a task id" % value, result.stderr)
            result = self.commit(root, git, 'valid\n\nDone: R12\nDone: K7-a\n')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_done_check_runs_without_the_attribution_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            (root / 'AGENTS.md').write_text('AI tools may be credited.\n')
            self.docs(root, git, '- K4: in flight\n')
            result = self.commit(root, git, 'Done: K4\n')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('closes K4 but docs/STATE.md', result.stderr)

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
        # A directory cannot be read by any user, root included. Mode 000 does not stop root,
        # and a case that cannot run under root is no pass there: a grep that fails to read
        # the file (exit 2, as on a permission error) stands in for it under every user.
        real_grep = shutil.which('grep')
        for damage in ('directory', 'grep cannot read it'):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as tmp:
                root, git = self.repo(tmp)
                agents = root / 'AGENTS.md'
                extra = {}
                if damage == 'directory':
                    agents.unlink()
                    agents.mkdir()
                else:
                    shim = Path(tmp) / 'shim'
                    shim.mkdir()
                    (shim / 'grep').write_text('#!/bin/sh\nfor last; do :; done\n[ "$last" != AGENTS.md ] || exit 2\n'
                                               'exec %s "$@"\n' % real_grep)
                    (shim / 'grep').chmod(0o755)
                    extra['PATH'] = '%s%s%s' % (shim, os.pathsep, os.environ['PATH'])
                result = self.commit(root, git, 'Co-Authored-By: Claude <noreply@anthropic.com>\n', **extra)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('cannot read AGENTS.md', result.stderr)

    def test_a_non_utf8_byte_on_the_trailer_line_is_checked_in_a_utf8_locale(self):
        # In a UTF-8 locale grep's "." stopped at a byte that is not valid UTF-8, and a
        # "[bot]" trailer whose name held a Latin-1 byte passed the hook.
        # The kit check's own selection, one copy: none is an error, never a pass.
        utf8 = kit_check.utf8_locale()
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = self.repo(tmp)
            message = root / 'message'
            message.write_bytes(b'change\n\nCo-authored-by: Caf\xe9 Helper '
                                b'<1+helper[bot]@users.noreply.github.com>\n')
            result = subprocess.run(['sh', '.githooks/commit-msg', str(message)], cwd=root,
                                    env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull,
                                             GIT_CONFIG_NOSYSTEM='1', LC_ALL=utf8, LANG=utf8),
                                    capture_output=True)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
