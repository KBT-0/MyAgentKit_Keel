"""The kit runs its own hooks from a pinned installed copy (PLAN item 11, owner 2026-11-10):
scripts/install_self.sh makes the copy, scripts/kit_hook.sh runs a hook from it, from the main
checkout or a worktree, and a missing copy blocks the guards that must not open silently."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOKS = 'overlays/claude-code/files/.claude/hooks'
CLOSED = ('guard_destructive_git.py', 'guard_risky_review.py', 'guard_private_email.py', 'guard_worker_route.py')
OPEN = ('guard_root_scan.py', 'guard_secret_files.py', 'context_size.py', 'plain_report.py')


def git(cwd, *args):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


class InstallSelfTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.cleanup, tmp)
        self.kit = Path(tmp.name) / 'kit'
        self.kit.mkdir()
        git(self.kit, 'init', '-q', '-b', 'master')
        git(self.kit, 'config', 'user.email', 't@example.invalid')
        git(self.kit, 'config', 'user.name', 't')
        # A kit in miniature: the real py.sh and git hook wrappers, hooks that say which tree ran them.
        (self.kit / HOOKS).mkdir(parents=True)
        (self.kit / '.gitattributes').write_text('*.sh text eol=lf\n', encoding='utf-8')
        shutil.copyfile(ROOT / HOOKS / 'py.sh', self.kit / HOOKS / 'py.sh')
        for folder in ('core/.githooks', 'core/scripts', 'overlays/claude-code/files/scripts', 'scripts', '.githooks'):
            (self.kit / folder).mkdir(parents=True, exist_ok=True)
        for name in ('install_self.sh', 'kit_hook.sh'):
            shutil.copyfile(ROOT / 'scripts' / name, self.kit / 'scripts' / name)
        for name in os.listdir(ROOT / '.githooks'):
            shutil.copyfile(ROOT / '.githooks' / name, self.kit / '.githooks' / name)
            os.chmod(self.kit / '.githooks' / name, 0o755)
        (self.kit / 'core/scripts/agent_cost.py').write_text('', encoding='utf-8')
        (self.kit / 'overlays/claude-code/files/scripts/spawn_worker.sh').write_text('', encoding='utf-8')
        self.version('pinned')
        self.pinned = git(self.kit, 'rev-parse', 'HEAD')
        (self.kit / 'scripts/installed_ref').write_text(self.pinned[:7] + '\n', encoding='utf-8')
        self.version('edited')  # the source moves on; the copy must not

    @staticmethod
    def cleanup(tmp):
        for folder, dirs, _ in os.walk(tmp.name):
            for d in dirs:
                os.chmod(os.path.join(folder, d), 0o755)
        tmp.cleanup()

    def version(self, word):
        for name in CLOSED + OPEN + ('marker.py',):
            (self.kit / HOOKS / name).write_text(
                'import sys\nsys.stdin.read()\nprint("%s %s", *sys.argv[1:])\n' % (word, name), encoding='utf-8')
        for name in ('pre-commit', 'commit-msg', 'pre-merge-commit', 'post-merge'):
            hook = self.kit / 'core/.githooks' / name
            hook.write_text('#!/bin/sh\necho "%s %s $0" >&2\n' % (word, name), encoding='utf-8')
            os.chmod(hook, 0o755)
        git(self.kit, 'add', '-A')
        git(self.kit, 'commit', '-q', '-m', word)

    def install(self, env=None):
        return subprocess.run(['sh', 'scripts/install_self.sh'], cwd=self.kit, capture_output=True, text=True,
                              env=env)

    def hook(self, name, project=None, *args):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project or self.kit))
        return subprocess.run(['sh', str(self.kit / 'scripts/kit_hook.sh'), name, *args], input='{}',
                              capture_output=True, text=True, env=env)

    def test_the_copy_is_the_pinned_ref_read_only_and_core_hooks_path_is_set(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        copy = self.kit / '.myagentkit/installed' / self.pinned
        self.assertEqual((self.kit / '.myagentkit/installed/current').read_text().strip(), self.pinned)
        self.assertIn('print("pinned marker.py"', (copy / '.claude/hooks/marker.py').read_text())
        for path in ('.claude/hooks/py.sh', '.githooks/pre-commit', 'scripts/agent_cost.py', 'scripts/spawn_worker.sh'):
            self.assertTrue((copy / path).is_file(), path)
        self.assertEqual(git(self.kit, 'config', 'core.hooksPath'), '.githooks')
        if os.name != 'nt':
            modes = [p.stat().st_mode for p in [copy, *copy.rglob('*')]]
            self.assertFalse([m for m in modes if m & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)])
        again = self.install()  # idempotent: the same commit's copy is kept
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self.hook('marker.py', None, 'x').stdout.strip(), 'pinned marker.py x')

    def test_the_pinned_gitattributes_keep_the_copy_lf_under_core_autocrlf(self):
        # Git for Windows defaults to core.autocrlf=true; a CRLF py.sh dies on $'\r' and every hook blocks.
        env = dict(os.environ, GIT_CONFIG_PARAMETERS="'core.autocrlf=true'")
        result = self.install(env)
        self.assertEqual(result.returncode, 0, result.stderr)
        copy = self.kit / '.myagentkit/installed' / self.pinned
        self.assertNotIn(b'\r', (copy / '.claude/hooks/py.sh').read_bytes())
        self.assertEqual(self.hook('marker.py', None, 'x').stdout.strip(), 'pinned marker.py x')

    def test_a_worktree_runs_the_main_checkouts_copy_for_claude_and_git_hooks(self):
        self.assertEqual(self.install().returncode, 0)
        tree = self.kit / '.claude/worktrees/w'
        git(self.kit, 'worktree', 'add', '-q', '-b', 'w', str(tree))
        result = self.hook('marker.py', tree)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'pinned marker.py'), result.stderr)
        (tree / 'f').write_text('x', encoding='utf-8')
        git(tree, 'add', 'f')
        commit = subprocess.run(['git', '-C', str(tree), 'commit', '-q', '-m', 'f'], capture_output=True, text=True)
        self.assertEqual(commit.returncode, 0, commit.stderr)
        self.assertIn('pinned pre-commit %s' % (self.kit / '.myagentkit/installed' / self.pinned / '.githooks/pre-commit'),
                      commit.stderr)

    def test_before_the_first_install_a_hook_runs_from_source_with_a_notice(self):
        result = self.hook('guard_destructive_git.py')
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'edited guard_destructive_git.py'))
        self.assertIn('install_self.sh', result.stderr)

    def test_a_missing_copy_blocks_the_closed_guards_and_lets_the_others_through(self):
        self.assertEqual(self.install().returncode, 0)
        copy = self.kit / '.myagentkit/installed' / self.pinned
        os.chmod(copy, 0o755)
        shutil.move(str(copy), str(copy) + '.gone')  # no fallback to the source once installed/ exists
        for name in CLOSED + OPEN:
            with self.subTest(hook=name):
                result = self.hook(name)
                self.assertEqual(result.returncode, 2 if name in CLOSED else 0)
                self.assertEqual(result.stdout, '')
                self.assertEqual(len(result.stderr.splitlines()), 1)
                self.assertIn('scripts/install_self.sh', result.stderr)
        (self.kit / 'f').write_text('x', encoding='utf-8')
        git(self.kit, 'add', 'f')
        commit = subprocess.run(['git', '-C', str(self.kit), 'commit', '-q', '-m', 'f'], capture_output=True, text=True)
        self.assertEqual(commit.returncode, 1, commit.stderr)
        self.assertIn('install_self.sh', commit.stderr)

    def test_the_kits_settings_run_every_hook_through_the_resolver_from_the_pinned_ref(self):
        settings = json.loads((ROOT / '.claude/settings.json').read_text(encoding='utf-8'))
        commands = [h['command'] for event in settings['hooks'].values() for entry in event for h in entry['hooks']]
        self.assertNotIn('overlays/', ' '.join(commands))
        names = [m for c in commands for m in re.findall(r'scripts/kit_hook\.sh\\?" ([\w.]+)', c)]
        self.assertEqual(len(names), len(commands))
        self.assertIn('guard_risky_review.py', names)
        ref = (ROOT / 'scripts/installed_ref').read_text(encoding='utf-8').strip()
        for name in names:
            with self.subTest(hook=name):
                self.assertTrue((ROOT / HOOKS / name).is_file())
                found = subprocess.run(['git', '-C', str(ROOT), 'cat-file', '-e', '%s:%s/%s' % (ref, HOOKS, name)])
                self.assertEqual(found.returncode, 0, 'the pinned ref %s lacks %s' % (ref, name))


if __name__ == '__main__':
    unittest.main()
