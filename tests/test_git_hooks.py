"""Git itself must call the shipped hooks: on a clean merge commit and on every commit message."""
import importlib.util
import os
from pathlib import Path
import shlex
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
            'echo ran >> .git/gate-runs\n[ ! -e a ] || [ ! -e b ] || { echo "CHECK: FAIL"; exit 1; }\n', encoding='utf-8')
        (root / 'scripts/check.sh').chmod(0o755)
        # C locale: the hook recognises the English text git writes under the scissors line.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_EDITOR='true',
                   LC_ALL='C', LANGUAGE='C')
        git = lambda *args, check=True, **extra: subprocess.run(
            ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
             '-c', 'core.hooksPath=.githooks', *args],
            cwd=root, env=dict(env, **extra), capture_output=True, text=True, check=check, encoding='utf-8')
        # init then checkout: `git init -b` needs git 2.28, older than some CI images carry.
        git('init', '-q')
        git('checkout', '-q', '-b', 'main')
        (root / 'AGENTS.md').write_text('- **No AI attribution in git.**\n', encoding='utf-8')
        # A quoted trailer in a tracked file shows up in `git commit -v`'s diff below the scissors.
        (root / 'notes').write_text('top\nCo-Authored-By: Claude <noreply@anthropic.com>\n', encoding='utf-8')
        git('add', '-A')
        git('commit', '-q', '-m', 'base')
        return root, git

    def test_a_clean_merge_into_a_red_tree_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            for branch in ('a', 'b'):
                git('checkout', '-q', '-b', branch, 'main')
                (root / branch).write_text(branch + '\n', encoding='utf-8')
                git('add', branch)
                git('commit', '-q', '-m', 'add ' + branch)
            git('checkout', '-q', 'a')
            runs = (root / '.git/gate-runs').read_text(encoding='utf-8').count('ran')
            merge = git('merge', '-q', '--no-edit', 'b', check=False)
            self.assertNotEqual(merge.returncode, 0, 'a clean merge into a red tree was committed')
            self.assertGreater((root / '.git/gate-runs').read_text(encoding='utf-8').count('ran'), runs)
            self.assertEqual(git('rev-list', '--count', 'HEAD').stdout.strip(), '2')

    def test_a_commit_of_heads_own_tree_skips_the_gate_and_a_merge_never_does(self):
        # Git runs pre-commit before it finds nothing to commit: each of these ran the whole
        # gate, then git said "nothing to commit" (#232).
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            runs = lambda: (root / '.git/gate-runs').read_text(encoding='utf-8').count('ran')
            before = runs()
            self.assertNotEqual(git('commit', '-a', '-m', 'clean tree', check=False).returncode, 0)
            git('commit', '-q', '--amend', '-m', 'message only')
            (root / 'notes').write_text('edited, never added\n', encoding='utf-8')
            self.assertNotEqual(git('commit', '-m', 'forgot add', check=False).returncode, 0)
            self.assertEqual(runs(), before, 'a commit of HEAD\'s own tree ran the gate')
            git('add', 'notes')
            git('commit', '-q', '-m', 'a change')
            self.assertEqual(runs(), before + 1)
            # A conflicted merge resolved to HEAD's tree is still a merge: gated.
            git('checkout', '-q', '-b', 'side', 'HEAD~1')
            (root / 'notes').write_text('side\n', encoding='utf-8')
            git('commit', '-q', '-am', 'side')
            git('checkout', '-q', 'main')
            self.assertNotEqual(git('merge', '-q', 'side', check=False).returncode, 0)
            git('checkout', '-q', '--ours', 'notes')
            git('add', 'notes')
            git('commit', '-q', '--no-edit')
            self.assertEqual(runs(), before + 3)

    def test_a_staged_submodule_bump_and_an_ours_merge_run_the_gate(self):
        # diff.ignoreSubmodules=all hid a staged submodule bump from the no-op check, and git
        # committed it ungated; a clean merge whose result is HEAD's tree has no MERGE_HEAD at
        # pre-merge-commit, so only --merge keeps its gate (round-1 review).
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            runs = lambda: (root / '.git/gate-runs').read_text(encoding='utf-8').count('ran')
            git('update-index', '--add', '--cacheinfo', '160000,%s,sub' % ('1' * 40))
            git('commit', '-q', '-m', 'add sub')
            before = runs()
            git('update-index', '--cacheinfo', '160000,%s,sub' % ('2' * 40))
            git('-c', 'diff.ignoreSubmodules=all', 'commit', '-q', '-m', 'bump', check=False)
            self.assertEqual(runs(), before + 1, 'a staged submodule bump skipped the gate')
            git('checkout', '-q', '-b', 'side', 'HEAD~1')
            (root / 'side').write_text('s\n', encoding='utf-8')
            git('add', 'side')
            git('commit', '-q', '-m', 'side')
            git('checkout', '-q', 'main')
            before = runs()
            git('merge', '-q', '-s', 'ours', '--no-edit', 'side')
            self.assertEqual(runs(), before + 1, 'a merge whose result is HEAD skipped the gate')

    def test_a_project_hook_without_a_shebang_stops_the_operation_loudly(self):
        # Git for Windows never runs a file without a #! line, chmod +x or not: the documented
        # one-line .project hook was skipped in silence (#165). Mode 644 makes the file
        # unrunnable on every platform; a #! hook with no execute bit stays switched off.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            for n, name in enumerate(('pre-commit', 'commit-msg')):
                own = root / '.githooks' / (name + '.project')
                own.write_text('exit 0\n', encoding='utf-8', newline='\n')
                own.chmod(0o644)
                (root / 'c').write_text('%d\n' % n, encoding='utf-8')
                git('add', 'c')
                result = git('commit', '-q', '-m', name, check=False)
                self.assertNotEqual(result.returncode, 0, name)
                self.assertIn('.githooks/%s.project has no #! line' % name, result.stderr)
                if os.name != 'nt':
                    own.write_text('#!/bin/sh\nexit 1\n', encoding='utf-8', newline='\n')
                    own.chmod(0o644)
                    self.assertEqual(git('commit', '-q', '-m', name, check=False).returncode, 0, name)
                own.unlink()
            git('commit', '-q', '--allow-empty', '-m', 'c')
            git('checkout', '-q', '-b', 'side', 'HEAD~1')
            (root / 'side').write_text('s\n', encoding='utf-8')
            git('add', 'side')
            git('commit', '-q', '-m', 'side')
            git('checkout', '-q', 'main')
            (root / '.githooks/pre-merge-commit.project').write_text('exit 0\n', encoding='utf-8', newline='\n')
            (root / '.githooks/pre-merge-commit.project').chmod(0o644)
            merge = git('merge', '-q', '--no-edit', 'side', check=False)
            self.assertNotEqual(merge.returncode, 0)
            self.assertIn('.githooks/pre-merge-commit.project has no #! line', merge.stderr)
            git('merge', '--abort', check=False)
            (root / '.githooks/pre-merge-commit.project').unlink()
            (root / '.githooks/post-merge.project').write_text('exit 0\n', encoding='utf-8', newline='\n')
            (root / '.githooks/post-merge.project').chmod(0o644)
            merge = git('merge', '-q', '--no-edit', 'side')
            self.assertIn('.githooks/post-merge.project has no #! line', merge.stderr)

    def test_a_clean_merge_runs_the_projects_merge_hook_then_its_commit_hook(self):
        # Git's own pre-merge-commit runs pre-commit (githooks(5)), so a clean merge runs the
        # project's pre-merge-commit.project and then its pre-commit.project, once each (#153,
        # owner decision 60).
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            for name in ('pre-commit', 'pre-merge-commit'):
                own = root / '.githooks' / (name + '.project')
                own.write_text('#!/bin/sh\necho %s >> .git/project-runs\n' % name, encoding='utf-8', newline='\n')
                own.chmod(0o755)
            git('add', '-A')
            git('commit', '-q', '-m', 'project hooks')
            git('checkout', '-q', '-b', 'side', 'HEAD~1')
            (root / 'side').write_text('s\n', encoding='utf-8')
            git('add', 'side')
            git('commit', '-q', '-m', 'side')
            git('checkout', '-q', 'main')
            (root / '.git/project-runs').unlink()
            git('merge', '-q', '--no-edit', 'side')
            self.assertEqual((root / '.git/project-runs').read_text(encoding='utf-8').split(), ['pre-merge-commit', 'pre-commit'])

    def docs_project(self, tmp):
        """A gated project whose base commit went through the hooks, so the gate recorded its tree.
        The build passes and, from here on, leaves a mark."""
        spec = importlib.util.spec_from_file_location('check_gate', ROOT / 'tests/test_check_gate.py')
        check_gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check_gate)
        root = Path(tmp) / 'project'
        check_gate.make_project(root)
        shutil.copytree(ROOT / 'core/.githooks', root / '.githooks')
        (root / 'scripts/check.sh').chmod(0o755)
        mark, build = Path(tmp) / 'built', Path(tmp) / 'build.sh'
        build.write_text('true\n', encoding='utf-8')
        env = dict({k: v for k, v in os.environ.items() if not k.startswith(('GATE_', 'BOUNDARY_'))},
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                   # The build command expands it unquoted: a Windows path keeps its `\` only as `/`.
                   GATE_TEST_BUILD=build.as_posix())
        git = lambda *args, check=True: subprocess.run(
            ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
             '-c', 'core.hooksPath=.githooks', *args],
            cwd=root, env=env, capture_output=True, text=True, check=check, encoding='utf-8')
        git('checkout', '-q', '-b', 'main')
        # A document the build reads is listed in docs_always_build (#97).
        gate = root / 'scripts/check.sh'
        self.assertIn('docs_always_build=""', gate.read_text(encoding='utf-8').splitlines())
        gate.write_bytes(gate.read_bytes().replace(b'docs_always_build=""',
                                                   b'docs_always_build="docs/*.md README.md"', 1))
        git('add', '-A')
        git('commit', '-q', '-m', 'base')
        build.write_text('echo ran > "%s"\n' % mark, encoding='utf-8')
        return root, git, build, mark

    def test_a_documentation_only_commit_defers_the_build_to_the_next_code_commit(self):
        # pre-commit asks for the documentation-only path; a clean merge (pre-merge-commit)
        # never takes it, whatever the merge brings in.
        with tempfile.TemporaryDirectory() as tmp:
            root, git, build, mark = self.docs_project(tmp)
            # From here on the build leaves a mark and fails.
            build.write_text('echo ran > "%s"; exit 1\n' % mark, encoding='utf-8')
            (root / 'notes.md').write_text('notes\n', encoding='utf-8')
            git('add', 'notes.md')
            result = git('commit', '-q', '-m', 'notes', check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(mark.exists(), result.stdout + result.stderr)
            self.assertIn('build not run: documentation-only commit, 1 file)', result.stdout + result.stderr)
            # A listed document builds, an unlisted one still skips (#97).
            (root / 'docs/api.md').write_text('api\n', encoding='utf-8')
            git('add', 'docs/api.md')
            result = git('commit', '-q', '-m', 'api', check=False)
            self.assertNotEqual(result.returncode, 0, 'a listed document skipped the failing build')
            self.assertTrue(mark.exists(), result.stdout + result.stderr)
            git('reset', '-q', '--hard', 'HEAD')
            mark.unlink()
            (root / 'notes.md').write_text('more notes\n', encoding='utf-8')
            git('add', 'notes.md')
            result = git('commit', '-q', '-m', 'notes', check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(mark.exists(), result.stdout + result.stderr)
            (root / 'code.c').write_text('int x;\n', encoding='utf-8')
            git('add', 'code.c')
            result = git('commit', '-q', '-m', 'code', check=False)
            self.assertNotEqual(result.returncode, 0, 'a code commit skipped the failing build')
            self.assertTrue(mark.exists(), result.stdout + result.stderr)
            git('reset', '-q', '--hard', 'HEAD')
            mark.unlink()
            # A clean merge that brings in only a document still runs the build.
            git('checkout', '-q', '-b', 'side', 'main~1')
            (root / 'side.md').write_text('side\n', encoding='utf-8')
            git('add', 'side.md')
            git('-c', 'core.hooksPath=/dev/null', 'commit', '-q', '-m', 'side')
            git('checkout', '-q', 'main')
            result = git('merge', '-q', '--no-edit', 'side', check=False)
            self.assertTrue(mark.exists(), 'a clean merge skipped the build: ' + result.stdout + result.stderr)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_documentation_only_commit_after_a_rebase_builds_once(self):
        # A rebase runs no hook, so the gate never saw the tree it leaves; the documentation-only
        # path trusted that HEAD and skipped the build (#115).
        with tempfile.TemporaryDirectory() as tmp:
            root, git, build, mark = self.docs_project(tmp)
            git('checkout', '-q', '-b', 'feat')
            (root / 'feat.c').write_text('int f;\n', encoding='utf-8')
            git('add', 'feat.c')
            git('commit', '-q', '-m', 'feat')
            git('checkout', '-q', 'main')
            (root / 'main.c').write_text('int m;\n', encoding='utf-8')
            git('add', 'main.c')
            git('commit', '-q', '-m', 'main')
            git('checkout', '-q', 'feat')
            git('rebase', '-q', 'main')
            for n, builds in ((1, True), (2, False)):
                if mark.exists():
                    mark.unlink()
                (root / 'notes.md').write_text('notes %d\n' % n, encoding='utf-8')
                git('add', 'notes.md')
                result = git('commit', '-q', '-m', 'notes %d' % n, check=False)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(mark.exists(), builds, result.stdout + result.stderr)

    def commit(self, root, git, message, *opts, **extra):
        (root / 'c').write_text(message, encoding='utf-8')
        git('add', 'c')
        return git('commit', '-q', *opts, '-m', 'change c', '-m', message, check=False, **extra)

    def hook(self, root, message):
        """commit-msg run on the file `commit` would hand it, without a commit: git's own
        clean-up of a -m message (git stripspace), then the hook. A commit per case also ran
        pre-commit and the stub gate, and made the case list the file's slowest test (#262)."""
        cleaned = subprocess.run(['git', 'stripspace'], input='change c\n\n' + message, cwd=root,
                                 capture_output=True, text=True, check=True, encoding='utf-8').stdout
        (root / 'msg').write_text(cleaned, encoding='utf-8')
        return subprocess.run(['sh', '.githooks/commit-msg', 'msg'], cwd=root, capture_output=True,
                              text=True, encoding='utf-8')

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
                            'Co-authored-by: Warp <agent@example.invalid>',
                            # Vendors the projects name as working tools (#204).
                            'Co-Authored-By: Kimi <noreply@moonshot.ai>',
                            'Co-authored-by: Kimi K2 <kimi@moonshot.cn>',
                            'Co-authored-by: GLM-4.6 <noreply@z.ai>',
                            'Co-authored-by: DeepSeek <noreply@deepseek.com>',
                            'Co-authored-by: Grok <noreply@x.ai>',
                            'Co-authored-by: Grok 4 <grok@example.invalid>'):
                with self.subTest(trailer=trailer):
                    result = self.hook(root, trailer + '\n')
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('crediting an AI tool', result.stderr)

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
                            # Kimi is a given name: only the vendor's domain marks the tool.
                            'Co-authored-by: Kimi <kimi@example.invalid>',
                            'Bump openai SDK to the next minor version'):
                with self.subTest(trailer=trailer):
                    result = self.commit(root, git, trailer + '\n')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_trailer_quoted_in_a_commit_v_diff_is_rejected_with_the_way_out(self):
        # The hook cannot tell git's editor header from the same text given with -m, so it
        # cuts nothing: a credit quoted in the diff below the scissors line fails closed.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            (root / 'notes').write_text('changed\nCo-Authored-By: Claude <noreply@anthropic.com>\n', encoding='utf-8')
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
        real_git = shlex.quote(shutil.which('git'))
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            shim = Path(tmp) / 'shim'
            shim.mkdir()
            (shim / 'git').write_text('#!/bin/sh\n[ "$1" != version ] || { echo "git version 2.45.0"; exit 0; }\n'
                                      'exec %s "$@"\n' % real_git, encoding='utf-8')
            (shim / 'git').chmod(0o755)
            glob = Path(tmp) / 'global.gitconfig'
            # (global settings, local settings), each in the order written; x is set last.
            for case, scopes in enumerate((((), (('commentChar', ';'), ('commentString', 'x'))),
                           ((), (('commentString', 'y'), ('commentChar', 'x'))),
                           ((('commentString', 'y'),), (('commentChar', 'x'),)),
                           ((('commentChar', 'y'),), (('commentString', 'x'),)))):
                with self.subTest(scopes=scopes):
                    glob.write_text('', encoding='utf-8')
                    git('config', '--local', '--remove-section', 'core', check=False)
                    for key, value in scopes[0]:
                        git('config', '--file', str(glob), 'core.' + key, value)
                    for key, value in scopes[1]:
                        git('config', '--local', 'core.' + key, value)
                    (root / 'msg').write_text('y%d\n\nx Co-Authored-By: Claude <noreply@anthropic.com>\n'
                                              % case, encoding='utf-8')
                    result = subprocess.run(['sh', '.githooks/commit-msg', 'msg'], cwd=root, text=True,
                                            capture_output=True,
                                            env=dict(os.environ, GIT_CONFIG_GLOBAL=str(glob),
                                                     GIT_CONFIG_NOSYSTEM='1',
                                                     PATH='%s%s%s' % (shim, os.pathsep, os.environ['PATH'])), encoding='utf-8')
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('crediting an AI tool', result.stderr)

    def test_a_git_before_2_45_reads_only_comment_char(self):
        # Git before 2.45 ignores core.commentString: with commentChar=x set before
        # commentString=y it keeps "x Co-Authored-By: ..." under -m, and a hook that took the
        # last of the two skipped only "y" and passed it.
        real_git = shlex.quote(shutil.which('git'))
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            git('config', 'core.commentChar', 'x')
            git('config', 'core.commentString', 'y')
            shim = Path(tmp) / 'shim'
            shim.mkdir()
            (shim / 'git').write_text('#!/bin/sh\n[ "$1" != version ] || { echo "git version 2.44.0"; exit 0; }\n'
                                      'exec %s "$@"\n' % real_git, encoding='utf-8')
            (shim / 'git').chmod(0o755)
            (root / 'msg').write_text('change c\n\nx Co-Authored-By: Claude <noreply@anthropic.com>\n', encoding='utf-8')
            result = subprocess.run(['sh', '.githooks/commit-msg', 'msg'], cwd=root, text=True,
                                    capture_output=True,
                                    env=dict(os.environ, PATH='%s%s%s' % (shim, os.pathsep, os.environ['PATH'])), encoding='utf-8')
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
        real_tr = shlex.quote(shutil.which('tr'))
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            shim = Path(tmp) / 'shim'
            shim.mkdir()
            for flag, key, value, line in (('-cd', 'core.commentChar', 'x', 'x Co-Authored-By: Claude'),
                                           ('-d', 'trailer.separators', '=', 'Co-Authored-By=Claude')):
                with self.subTest(transformation=key):
                    git('config', key, value)
                    (shim / 'tr').write_text('#!/bin/sh\n[ "$1" != %s ] || exit 1\nexec %s "$@"\n'
                                             % (flag, real_tr), encoding='utf-8')
                    (shim / 'tr').chmod(0o755)
                    (root / 'msg').write_text('change c\n\n%s <noreply@anthropic.com>\n' % line, encoding='utf-8')
                    result = subprocess.run(['sh', '.githooks/commit-msg', 'msg'], cwd=root, text=True,
                                            capture_output=True,
                                            env=dict(os.environ, PATH='%s%s%s' % (shim, os.pathsep,
                                                                                   os.environ['PATH'])), encoding='utf-8')
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('cannot parse %s' % key, result.stderr)
                    git('config', '--unset', key)

    def test_a_failed_config_read_fails_closed(self):
        # Only an absent key (git config exit 1) means the default: a failed read of
        # trailer.separators left only ":" as a separator and "Co-Authored-By=Claude" passed.
        real_git = shlex.quote(shutil.which('git'))
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
                                              'exec %s "$@"\n' % (read, real_git), encoding='utf-8')
                    (shim / 'git').chmod(0o755)
                    (root / 'msg').write_text('change c\n\n%s <noreply@anthropic.com>\n' % line, encoding='utf-8')
                    result = subprocess.run(['sh', '.githooks/commit-msg', 'msg'], cwd=root, text=True,
                                            capture_output=True,
                                            env=dict(os.environ, PATH='%s%s%s' % (shim, os.pathsep,
                                                                                   os.environ['PATH'])), encoding='utf-8')
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
            (root / 'msg').write_text('change c\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n', encoding='utf-8')
            for tool, broken, message in (
                    ('git', '[ "$1" != version ] || { echo "version unknown"; exit 0; }',
                     'cannot read the git version'),
                    ('awk', 'exit 1', 'cannot unfold the commit message'),
                    ('grep', 'case " $* " in *" -iE "*) exit 2 ;; esac', 'the trailer check itself failed')):
                with self.subTest(tool=tool):
                    for stale in shim.iterdir():
                        stale.unlink()
                    (shim / tool).write_text('#!/bin/sh\n%s\nexec %s "$@"\n' % (broken, shlex.quote(shutil.which(tool))), encoding='utf-8')
                    (shim / tool).chmod(0o755)
                    result = subprocess.run(['sh', '.githooks/commit-msg', 'msg'], cwd=root, text=True,
                                            capture_output=True,
                                            env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull,
                                                     GIT_CONFIG_NOSYSTEM='1',
                                                     PATH='%s%s%s' % (shim, os.pathsep, os.environ['PATH'])), encoding='utf-8')
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn(message, result.stderr)

    def test_the_owner_may_allow_ai_attribution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            trailers = ('Co-Authored-By: Claude <noreply@anthropic.com>', 'Assisted-by: Claude:claude-opus',
                        'Assisted-by: LLM [Claude]')
            # Each case is refused under the rule, so only the opt-in lets it through.
            for agents, expected in (('No AI attribution in git.\n', 1), ('AI tools may be credited.\n', 0)):
                (root / 'AGENTS.md').write_text(agents, encoding='utf-8')
                for trailer in trailers:
                    with self.subTest(agents=agents, trailer=trailer):
                        result = self.commit(root, git, trailer)
                        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def docs(self, root, git, state='', backlog=''):
        (root / 'docs').mkdir(exist_ok=True)
        (root / 'docs/STATE.md').write_text('# STATE\n\n## Active work\n' + state, encoding='utf-8')
        (root / 'docs/BACKLOG.md').write_text('# BACKLOG\n\n## Next tasks\n' + backlog, encoding='utf-8')
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

    def test_a_report_refusal_says_the_report_is_a_living_file(self):
        # #301: told only "or drop the trailer", a project dropped it, losing the task-id trace;
        # the strong review list, a report or an audit loses the closed finding's line instead.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            self.docs(root, git)
            for where in ('docs/reviews/strong-today.md', 'docs/audits/2026-10.md', 'docs/STRONG_REVIEW.md'):
                with self.subTest(where=where):
                    (root / where).parent.mkdir(parents=True, exist_ok=True)
                    (root / where).write_text('- P3: a finding\n', encoding='utf-8')
                    git('add', 'docs')
                    result = self.commit(root, git, 'close\n\nDone: P3\n')
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('closes P3 but %s still mentions it' % where, result.stderr)
                    self.assertIn('Closing deletes', result.stderr)
                    self.assertNotIn('drop the trailer', result.stderr)
                    git('rm', '-qf', where)
            self.docs(root, git, '- P3: in flight\n')
            result = self.commit(root, git, 'close\n\nDone: P3\n')
            self.assertNotIn('Closing deletes', result.stderr)

    def test_a_done_id_matches_the_state_files_in_any_case(self):
        # `Done: k4` passed while the staged STATE.md named K4: ids are case-insensitive.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            for state, trailer in (('- K4: in flight\n', 'k4'), ('- k5: in flight\n', 'K5')):
                with self.subTest(trailer=trailer):
                    self.docs(root, git, state)
                    result = self.commit(root, git, 'case\n\nDone: %s\n' % trailer)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('closes %s but docs/STATE.md still mentions it' % trailer, result.stderr)

    def test_a_failed_report_listing_refuses_a_done_trailer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            report = root / 'docs/reviews/strong-today.md'
            report.parent.mkdir(parents=True)
            report.write_text('- K4: open\n', encoding='utf-8')
            git('add', 'docs')
            message = root / 'message'
            message.write_text('close\n\nDone: K4\n', encoding='utf-8')
            shim = root / 'shim'
            shim.mkdir()
            (shim / 'git').write_text('#!/bin/sh\ncase " $* " in *" ls-files "*) exit 128 ;; esac\n'
                                      'exec %s "$@"\n' % shlex.quote(shutil.which('git')), encoding='utf-8')
            (shim / 'git').chmod(0o755)
            result = subprocess.run(['sh', '.githooks/commit-msg', str(message)], cwd=root,
                                    capture_output=True, text=True,
                                    env=dict(os.environ, PATH=str(shim) + os.pathsep + os.environ['PATH']), encoding='utf-8')
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('cannot list the index', result.stderr)

    def test_done_listing_is_scoped_even_with_literal_pathspecs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            self.docs(root, git, '')
            report = root / 'docs/reviews/strong-today.md'
            report.parent.mkdir()
            report.write_text('- K4: open\n', encoding='utf-8')
            git('add', 'docs/reviews')
            message = root / 'message'
            message.write_text('close\n\nDone: K4\n', encoding='utf-8')
            shim = root / 'bin'
            shim.mkdir()
            (shim / 'git').write_text(
                '#!/bin/sh\ncase " $* " in *" ls-files "*)\n'
                '  case " $* " in *" -- :(icase)docs/reviews :(icase)docs/audits "*) ;; *) echo unscoped-index >&2; exit 128 ;; esac ;; esac\n'
                'exec %s "$@"\n' % shlex.quote(shutil.which('git')), encoding='utf-8')
            (shim / 'git').chmod(0o755)
            result = subprocess.run(['sh', '.githooks/commit-msg', str(message)], cwd=root,
                                    capture_output=True, text=True,
                                    env=dict(os.environ, GIT_LITERAL_PATHSPECS='1',
                                             PATH=str(shim) + os.pathsep + os.environ['PATH']), encoding='utf-8')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('still mentions it', result.stderr)
            self.assertNotIn('unscoped-index', result.stderr)

    def check_report_name(self, name, message_text='close\n\nDone: K4\n', expected=1):
        # Index-only names also exercise characters Windows refuses in a working-tree name.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], cwd=root,
                                  input='- K4: open\n', capture_output=True, text=True, check=True, encoding='utf-8').stdout.strip()
            # As UTF-8 bytes: under the locale suite's LC_ALL=C and PYTHONUTF8=0 an 'é' in a str
            # argument cannot be encoded for the child.
            git('-c', 'core.protectNTFS=false', 'update-index', '--add', '--cacheinfo',
                ('100644,' + blob + ',' + name).encode('utf-8'))
            message = root / 'message'
            message.write_text(message_text, encoding='utf-8')
            result = subprocess.run(['sh', '.githooks/commit-msg', str(message)], cwd=root,
                                    capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
            return result.stderr

    def test_noncanonical_reports_do_not_block_commits_without_done(self):
        for name in ('docs/Reviews/strong-today.md', 'docs/reviews/strong-\t.md'):
            with self.subTest(path=name):
                self.check_report_name(name, 'plain change\n', expected=0)
                self.assertIn('crediting an AI tool', self.check_report_name(
                    name, 'change\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n'))

    def test_git_quoted_report_names_cannot_bypass_closure(self):
        for special in ('\t', '\\', '"', '\n'):
            with self.subTest(special=special):
                self.assertIn('quoted paths under docs/reviews',
                              self.check_report_name('docs/reviews/strong-' + special + '.md'))
        for name in ('space here', 'é'):
            with self.subTest(name=name):
                self.assertIn('still mentions it', self.check_report_name('docs/reviews/strong-' + name + '.md'))

    def test_noncanonical_review_directory_case_is_refused(self):
        for directory in ('docs/Reviews', 'Docs/reviews', 'DOCS/REVIEWS'):
            with self.subTest(directory=directory):
                self.assertIn('use docs/reviews or docs/audits with this exact case',
                              self.check_report_name(directory + '/strong-today.md'))

    def test_the_index_is_checked_not_the_working_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            self.docs(root, git, '- K4: in flight\n')
            (root / 'docs/STATE.md').write_text('# STATE\n\n## Active work\n', encoding='utf-8')
            result = self.commit(root, git, 'unstaged\n\nDone: K4\n')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('closes K4 but docs/STATE.md', result.stderr)
            self.docs(root, git)
            (root / 'docs/STATE.md').write_text('# STATE\n\n## Active work\n- K4: in flight\n', encoding='utf-8')
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

    def test_a_done_trailer_after_a_divider_line_is_read(self):
        # Without --no-divider, a body line "---" read as a patch start and hid every trailer
        # after it, while `git log` and check.sh still read them (#173).
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            self.docs(root, git, '- K4: in flight\n')
            for divider in ('---', '--- note'):
                with self.subTest(divider=divider):
                    result = self.commit(root, git, 'close\n\nnotes\n%s\nmore notes\n\nDone: K4\n' % divider)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('closes K4 but docs/STATE.md', result.stderr)
            result = self.commit(root, git, 'bad\n\nnotes\n---\n\nDone: K4 K5\n')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("'Done: K4 K5' does not name a task id", result.stderr)

    def test_a_done_value_is_one_id_whole_folded_and_any_key_case(self):
        # Word splitting passed "Done: K4 K5" as two ids, which the gate reads as one bad
        # value closing neither; an empty value passed unchecked. Git unfolds a folded value
        # and matches the key in any case; the hook reads it the same way.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            self.docs(root, git)
            for trailer, value in (('Done: K4 K5', 'K4 K5'), ('Done: K4, K5', 'K4, K5'), ('Done:', ''),
                                   ('Done:   ', ''), ('Done: K4\n  K5', 'K4 K5')):
                with self.subTest(trailer=trailer):
                    result = self.commit(root, git, 'bad\n\n' + trailer + '\n')
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("'Done: %s' does not name a task id" % value, result.stderr)
            self.docs(root, git, '- K4: in flight\n- K5: in flight\n')
            for trailer, closed in (('done: K4', 'K4'), ('DONE: K5', 'K5'), ('Done:\n  K4', 'K4')):
                with self.subTest(trailer=trailer):
                    result = self.commit(root, git, 'case\n\n' + trailer + '\n')
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('closes %s but docs/STATE.md' % closed, result.stderr)

    def test_the_done_check_runs_without_the_attribution_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            (root / 'AGENTS.md').write_text('AI tools may be credited.\n', encoding='utf-8')
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
            # Native Windows takes it another way; tests/test_check_gate_windows holds it there.
            if os.name == 'nt':
                sys.stderr.write('\nNOT RUN: %s (POSIX only: the flock gate lock)\n' % self.id())
                return
            holder = subprocess.Popen(
                [sys.executable, '-c',
                 # Binary: under the locale suite a text open without an encoding is an error.
                 'import fcntl, sys, time; f = open(sys.argv[1], "ab"); '
                 'fcntl.flock(f, fcntl.LOCK_EX); print("held", flush=True); time.sleep(60)',
                 str(root / '.git/check.lock')], stdout=subprocess.PIPE, text=True, encoding='utf-8')
            try:
                self.assertEqual(holder.stdout.readline().strip(), 'held')
                (root / 'c').write_text('locked\n', encoding='utf-8')
                git('add', 'c')
                result = subprocess.run(
                    ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                     '-c', 'core.hooksPath=.githooks', 'commit', '-q', '-m', 'locked'],
                    cwd=root, capture_output=True, text=True, timeout=60,
                    env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                             GATE_LOCK_WAIT='1'), encoding='utf-8')
            finally:
                holder.kill()
                holder.wait()
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('check.sh did NOT RUN (another gate run holds the lock); commit blocked',
                          result.stderr)
            self.assertNotIn('FAILED', result.stderr)

    def test_the_private_store_in_another_case_never_reaches_a_commit(self):
        # Windows and macOS fold case, so `.MYAGENTKIT/` is the private store; with
        # core.ignorecase false a lowercase-only ignore rule missed it and `git add -A`
        # committed its credential. The kit's rule and the project rule it ships match any case.
        for ignore in ('.gitignore', 'core/.gitignore'):
            with self.subTest(ignore=ignore), tempfile.TemporaryDirectory() as tmp:
                root, git = self.repo(tmp)
                shutil.copyfile(ROOT / ignore, root / '.gitignore')
                git('config', 'core.ignorecase', 'false')
                for name in ('.MYAGENTKIT/Backends/glm.env', '.MyAgentKit/usage/r.json'):
                    (root / name).parent.mkdir(parents=True)
                    (root / name).write_text('ANTHROPIC_AUTH_TOKEN=fixture\n', encoding='utf-8')
                git('add', '-A')
                git('commit', '-q', '-m', 'everything')
                self.assertEqual(git('ls-files', ':(icase).myagentkit').stdout, '')

    def test_an_unreadable_agents_file_fails_closed(self):
        # A grep that could not read the rule is not an owner's choice to allow AI credit.
        # A directory cannot be read by any user, root included. Mode 000 does not stop root,
        # and a case that cannot run under root is no pass there: a grep that fails to read
        # the file (exit 2, as on a permission error) stands in for it under every user.
        real_grep = shlex.quote(shutil.which('grep'))
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
                                               'exec %s "$@"\n' % real_grep, encoding='utf-8')
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
