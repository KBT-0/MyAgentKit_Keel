"""One master writer per main checkout, enforced: the marker, the commit hooks' refusal, and the
gate's project env file (docs/WORKFLOW.md, "Parallel work — worktree policy")."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_check_gate_windows import environment, make_project  # noqa: E402

SCRIPT = ROOT / 'core/scripts/master_writer.py'
STATE = '# STATE\n\n**Working mode:** solo (`docs/WORKFLOW.md`).\n\n## Active work\n'


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in ('CLAUDE_CODE_SESSION_ID', 'MYAGENTKIT_SESSION_ID')}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_EDITOR='true', LC_ALL='C', **extra)
    return env


class HookTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = root = Path(tmp.name) / 'main'
        root.mkdir()
        shutil.copytree(ROOT / 'core/.githooks', root / '.githooks')
        (root / 'scripts').mkdir()
        (root / 'docs').mkdir()
        shutil.copy(ROOT / 'core/docs/COMMUNICATION.md', root / 'docs/COMMUNICATION.md')
        (root / 'scripts/check.sh').write_text('echo ran >> "$(git rev-parse --git-common-dir)/gate-runs"\n',
                                                encoding='utf-8', newline='\n')
        (root / 'scripts/check.sh').chmod(0o755)
        (root / '.gitignore').write_text('/.myagentkit/\n', encoding='utf-8')
        self.git('init', '-q')
        self.git('checkout', '-q', '-b', 'main')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'base', CLAUDE_CODE_SESSION_ID='writer-1')

    def git(self, *args, cwd=None, check=True, **extra):
        return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                               '-c', 'core.hooksPath=.githooks', '-c', 'commit.gpgsign=false', *args],
                              cwd=cwd or self.root, env=clean_env(**extra), capture_output=True, text=True,
                              encoding='utf-8', errors='replace', check=check)

    def runs(self):
        path = self.root / '.git/gate-runs'
        return path.read_text(encoding='utf-8').count('ran') if path.exists() else 0

    def claim(self, writer):
        (self.root / '.myagentkit').mkdir(exist_ok=True)
        (self.root / '.myagentkit/master-writer').write_text(writer + '\n', encoding='utf-8')

    def commit(self, name, cwd=None, **extra):
        (Path(cwd or self.root) / name).write_text(name + '\n', encoding='utf-8')
        self.git('add', name, cwd=cwd)
        return self.git('commit', '-q', '-m', 'add ' + name, cwd=cwd, check=False, **extra)

    def test_a_foreign_session_is_refused_in_the_main_checkout_before_the_gate(self):
        self.claim('writer-1')
        before = self.runs()
        result = self.commit('a', CLAUDE_CODE_SESSION_ID='other-2')
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.runs(), before, 'the gate ran before the refusal')
        self.assertIn('writer-1', result.stderr)
        self.assertIn('other-2', result.stderr)
        self.assertIn('MERGE REQUEST: `branch, base commit, review evidence path, the Owns list, '
                      '"tests green at <sha>"`', result.stderr)
        self.assertIn('or wait for MAIN CHECKOUT IDLE', result.stderr)
        # No identity is the owner's terminal (owner 2026-10-22): let through, with one note naming the holder.
        result = self.commit('b')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.runs(), before + 1)
        self.assertIn('writer-1', result.stderr)
        self.assertNotIn('MERGE REQUEST', result.stderr)
        # An empty marker names nobody: refused, fail closed.
        self.claim('')
        self.assertNotEqual(self.commit('c', CLAUDE_CODE_SESSION_ID='writer-1').returncode, 0)

    def test_a_foreign_merge_is_refused_before_the_projects_merge_hook_and_the_gate(self):
        self.git('checkout', '-q', '-b', 'side')
        self.assertEqual(self.commit('s', CLAUDE_CODE_SESSION_ID='writer-1').returncode, 0)
        self.git('checkout', '-q', 'main')
        self.assertEqual(self.commit('m', CLAUDE_CODE_SESSION_ID='writer-1').returncode, 0)
        own = self.root / '.githooks/pre-merge-commit.project'
        own.write_text('#!/bin/sh\necho own >> .git/own-runs\n', encoding='utf-8', newline='\n')
        own.chmod(0o755)
        self.claim('writer-1')
        before = self.runs()
        merge = self.git('merge', '-q', '--no-edit', 'side', check=False, CLAUDE_CODE_SESSION_ID='other-2')
        self.assertNotEqual(merge.returncode, 0, merge.stderr)
        self.assertIn('MAIN CHECKOUT IDLE', merge.stderr)
        self.assertEqual(self.runs(), before)
        self.assertFalse((self.root / '.git/own-runs').exists(), 'the project hook ran before the refusal')
        self.git('merge', '--abort', check=False)
        merge = self.git('merge', '-q', '--no-edit', 'side', check=False, CLAUDE_CODE_SESSION_ID='writer-1')
        self.assertEqual(merge.returncode, 0, merge.stderr)
        self.assertEqual(self.runs(), before + 1)

    def test_the_marked_session_commits_through_the_gate(self):
        self.claim('writer-1')
        before = self.runs()
        result = self.commit('a', CLAUDE_CODE_SESSION_ID='writer-1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.runs(), before + 1)
        # MYAGENTKIT_SESSION_ID names a session that has no Claude Code id, and wins over it.
        result = self.commit('b', CLAUDE_CODE_SESSION_ID='other-2', MYAGENTKIT_SESSION_ID='writer-1')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_worktree_is_never_refused(self):
        self.claim('writer-1')
        tree = self.root.parent / 'tree'
        self.git('worktree', 'add', '-q', '-b', 'work', str(tree))
        (tree / '.myagentkit').mkdir()
        (tree / '.myagentkit/master-writer').write_text('writer-1\n', encoding='utf-8')
        result = self.commit('w', cwd=tree, CLAUDE_CODE_SESSION_ID='other-2')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_marker_no_refusal(self):
        result = self.commit('a', CLAUDE_CODE_SESSION_ID='other-2')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('master writer', result.stderr.lower())


class ScriptTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'main'
        (self.root / 'docs').mkdir(parents=True)
        (self.root / 'docs/STATE.md').write_bytes(STATE.encode())
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, env=clean_env())

    def run_script(self, *args, cwd=None, **extra):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.root, env=clean_env(**extra),
                              capture_output=True, text=True, encoding='utf-8')

    def marker(self):
        return (self.root / '.myagentkit/master-writer').read_text(encoding='utf-8').strip()

    def test_claim_writes_the_marker_and_the_state_line_and_release_clears_both(self):
        result = self.run_script('claim', CLAUDE_CODE_SESSION_ID='writer-1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.marker(), 'writer-1')
        state = (self.root / 'docs/STATE.md').read_text(encoding='utf-8')
        lines = state.splitlines()
        self.assertTrue(lines[3].startswith('**Master writer:** writer-1 '), state)
        self.assertEqual(lines[2], '**Working mode:** solo (`docs/WORKFLOW.md`).')
        self.assertIn('writer-1', self.run_script('show').stdout)
        # Another session is refused; the owner's word (--force) takes it over.
        refused = self.run_script('claim', CLAUDE_CODE_SESSION_ID='other-2')
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('writer-1', refused.stderr)
        self.assertNotEqual(self.run_script('release', CLAUDE_CODE_SESSION_ID='other-2').returncode, 0)
        self.assertEqual(self.run_script('claim', '--force', CLAUDE_CODE_SESSION_ID='other-2').returncode, 0)
        self.assertEqual(self.marker(), 'other-2')
        state = (self.root / 'docs/STATE.md').read_text(encoding='utf-8')
        self.assertEqual(state.count('**Master writer:**'), 1, state)
        result = self.run_script('release', CLAUDE_CODE_SESSION_ID='other-2')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / '.myagentkit/master-writer').exists())
        self.assertIn('**Master writer:** none\n', (self.root / 'docs/STATE.md').read_text(encoding='utf-8'))

    def test_claim_without_an_identity_or_in_a_worktree_is_refused(self):
        self.assertNotEqual(self.run_script('claim').returncode, 0)
        git = lambda *a: subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                                         '-c', 'core.hooksPath=/dev/null', *a], cwd=self.root,
                                        env=clean_env(), check=True, capture_output=True)
        git('add', '-A')
        git('commit', '-q', '-m', 'base')
        tree = self.root.parent / 'tree'
        git('worktree', 'add', '-q', '-b', 'work', str(tree))
        result = self.run_script('claim', cwd=tree, CLAUDE_CODE_SESSION_ID='writer-1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('main checkout', result.stderr)
        self.assertFalse((tree / '.myagentkit/master-writer').exists())
        # show works in a worktree: a worker learns whom to send its MERGE REQUEST.
        self.assertEqual(self.run_script('claim', CLAUDE_CODE_SESSION_ID='writer-1').returncode, 0)
        result = self.run_script('show', cwd=tree, CLAUDE_CODE_SESSION_ID='other-2')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Master writer: writer-1', result.stdout)
        self.assertNotEqual(self.run_script('release', cwd=tree, CLAUDE_CODE_SESSION_ID='writer-1').returncode, 0)


class EnvFileTests(unittest.TestCase):
    """check.sh reads .myagentkit/env: a git hook does not inherit what the session set."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / 'project'
        make_project(self.project)
        self.out = self.tmp / 'seen'
        self.build = self.tmp / 'build.sh'
        self.build.write_text('printf "%s" "${KIT_ENV_PROBE-UNSET}" > "$KIT_ENV_OUT"\n', encoding='utf-8', newline='\n')
        (self.project / '.gitignore').write_text('/.myagentkit/\n', encoding='utf-8')
        git = ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', '-c', 'core.hooksPath=/dev/null']
        subprocess.run(git + ['add', '-A'], cwd=self.project, check=True)
        subprocess.run(git + ['commit', '-q', '-m', 'init'], cwd=self.project, check=True)

    def run_gate(self, env_text, **extra):
        (self.project / '.myagentkit').mkdir(exist_ok=True)
        (self.project / '.myagentkit/env').write_bytes(env_text.encode())
        env = environment(self.build, KIT_ENV_OUT=self.out.as_posix(), **extra)
        result = subprocess.run(['sh', 'scripts/check.sh'], cwd=self.project, env=env, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=120)
        return result.returncode, result.stdout + result.stderr

    def test_a_key_reaches_the_gate_literally(self):
        code, out = self.run_gate('# the venv\n\nKIT_ENV_PROBE=C:/venv/py $HOME `x` "q"\r\n')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.out.read_text(encoding='utf-8'), 'C:/venv/py $HOME `x` "q"')

    def test_a_utf8_bom_is_stripped_and_utf16_is_named(self):
        code, out = self.run_gate('﻿KIT_ENV_PROBE=bom\n')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.out.read_text(encoding='utf-8'), 'bom')
        self.out.unlink()
        # Windows PowerShell 5.1's Out-File writes UTF-16 LE with a BOM; without the BOM it still has NULs.
        for data in ('﻿KIT_ENV_PROBE=x\r\n'.encode('utf-16-le'), 'KIT_ENV_PROBE=x\n'.encode('utf-16-le')):
            with self.subTest(data=data[:4]):
                (self.project / '.myagentkit/env').write_bytes(data)
                result = subprocess.run(['sh', 'scripts/check.sh'], cwd=self.project, capture_output=True,
                                        env=environment(self.build, KIT_ENV_OUT=self.out.as_posix()),
                                        text=True, encoding='utf-8', errors='replace', timeout=120)
                out = result.stdout + result.stderr
                self.assertEqual(result.returncode, 1, out)
                self.assertIn('FAIL [env]: .myagentkit/env is UTF-16', out)
                self.assertIn('save it as UTF-8', out)
                self.assertFalse(self.out.exists())

    def test_an_already_set_key_wins(self):
        code, out = self.run_gate('KIT_ENV_PROBE=from-file\n', KIT_ENV_PROBE='from-session')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.out.read_text(encoding='utf-8'), 'from-session')

    def test_a_malformed_line_is_refused_with_its_number(self):
        for bad in ('export KIT_ENV_PROBE=x', 'kit_env_probe=x', 'KIT ENV=x', '1KIT=x', 'KIT_ENV_PROBE', '$(true)'):
            with self.subTest(bad=bad):
                code, out = self.run_gate('# ok\nKIT_ENV_PROBE=x\n' + bad + '\n')
                self.assertEqual(code, 1, out)
                self.assertIn('FAIL [env]: .myagentkit/env line 3', out)
                self.assertFalse(self.out.exists(), 'the gate ran on a refused env file')


class DocsOnlyMergeTests(unittest.TestCase):
    """A clean merge whose result differs from a gated HEAD only in documents skips the build, as a
    documentation-only commit does; one that brings in anything else builds (project_leeway, 2026-10-22)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp = Path(tmp.name)
        self.project = tmp / 'project'
        make_project(self.project)
        shutil.copytree(ROOT / 'core/.githooks', self.project / '.githooks')
        self.log = tmp / 'builds'
        self.build = tmp / 'build.sh'
        self.build.write_text('echo built >> "$KIT_BUILD_LOG"\n', encoding='utf-8', newline='\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'base')
        self.main = self.git('rev-parse', '--abbrev-ref', 'HEAD').stdout.strip()

    def git(self, *args, check=True, cwd=None):
        env = environment(self.build, KIT_BUILD_LOG=self.log.as_posix())
        env.pop('CLAUDE_CODE_SESSION_ID', None)
        return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                               '-c', 'core.hooksPath=.githooks', '-c', 'commit.gpgsign=false', *args],
                              cwd=cwd or self.project, env=env, capture_output=True, text=True, encoding='utf-8',
                              errors='replace', check=check)

    def builds(self):
        return self.log.read_text(encoding='utf-8').count('built') if self.log.exists() else 0

    def branch_commit(self, name, path):
        # In its own worktree, as a worker commits: check-gated-tree is one file per worktree.
        tree = self.project.parent / name
        self.git('worktree', 'add', '-q', '-b', name, str(tree), self.main)
        (tree / path).write_text(name + '\n', encoding='utf-8', newline='\n')
        self.git('add', path, cwd=tree)
        self.git('commit', '-q', '-m', 'add ' + path, cwd=tree)

    def test_a_docs_only_merge_onto_a_gated_head_skips_the_build_and_a_code_merge_builds(self):
        self.branch_commit('docs', 'docs/guide.md')
        before = self.builds()
        merge = self.git('merge', '-q', '--no-ff', '--no-edit', 'docs', check=False)
        self.assertEqual(merge.returncode, 0, merge.stdout + merge.stderr)
        self.assertEqual(self.builds(), before, 'a docs-only merge onto a gated HEAD built')
        self.assertIn('NOTE [build]: not run: every path this commit changes is documentation (1 file).',
                      merge.stdout + merge.stderr)
        self.branch_commit('code', 'tool.txt')
        before = self.builds()
        merge = self.git('merge', '-q', '--no-ff', '--no-edit', 'code', check=False)
        self.assertEqual(merge.returncode, 0, merge.stdout + merge.stderr)
        self.assertEqual(self.builds(), before + 1, 'a merge bringing in a code file skipped the build')
        self.assertNotIn('NOTE [build]: not run', merge.stdout + merge.stderr)

    def test_a_docs_only_merge_onto_an_ungated_head_builds(self):
        self.branch_commit('docs', 'docs/guide.md')
        (self.project / '.git/check-gated-tree').unlink()
        before = self.builds()
        merge = self.git('merge', '-q', '--no-ff', '--no-edit', 'docs', check=False)
        self.assertEqual(merge.returncode, 0, merge.stdout + merge.stderr)
        self.assertEqual(self.builds(), before + 1)


if __name__ == '__main__':
    unittest.main()
