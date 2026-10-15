"""guard_destructive_git.py: which git commands an agent's Bash call may run.

A command that discards work in the tree is refused while the tree is dirty; one that loses work
whatever the tree's state (a dropped stash, a rewritten remote, a skipped gate) is always refused.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/hooks/guard_destructive_git.py'
ENV = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
ENV.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')


def git(cwd, *args):
    return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *args], cwd=cwd,
                          env=ENV, capture_output=True, encoding='utf-8', errors='replace', check=True, timeout=60)


class GuardDestructiveGitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q', '-b', 'main')
        (self.repo / 'f.txt').write_text('one\n', encoding='utf-8')
        git(self.repo, 'add', 'f.txt')
        git(self.repo, 'commit', '-q', '-m', 'base')

    def run_hook(self, command, cwd=None, payload=None, python_args=()):
        payload = payload if payload is not None else json.dumps({'tool_name': 'Bash', 'tool_input': {'command': command}})
        return subprocess.run([sys.executable, *python_args, str(HOOK)], input=payload.encode('utf-8'),
                              cwd=cwd or self.repo, env=ENV, capture_output=True, timeout=60)

    def assertVerdict(self, commands, code, **kw):
        for command in commands:
            with self.subTest(command=command):
                result = self.run_hook(command, **kw)
                self.assertEqual(result.returncode, code, result.stderr.decode('utf-8', 'replace'))

    def dirty(self):
        (self.repo / 'f.txt').write_text('two\n', encoding='utf-8')

    def test_loss_certain_commands_are_refused_on_a_clean_tree(self):
        self.assertVerdict([
            'git stash drop', 'git stash clear', 'git -C . stash drop',
            'git push --force', 'git push -f origin main', 'git push origin +main', 'git push --mirror',
            'git push --delete origin x', 'git push origin :x', 'git push --force-with-lease',
            'git push --force-with-lease=main', 'git push --force-with-lease=main:abc --force',
            'git remote set-url origin x', 'git remote add up x', 'git -C . remote add up x',
            'echo ok && git push -f', "sh -c 'git push --force'",
        ], 2)

    def test_gate_bypasses_are_refused(self):
        self.assertVerdict([
            'git commit --no-verify -m x', 'git commit -n -m x', 'git commit -nm x', 'git commit -anm x',
            'git -c core.hooksPath=/dev/null commit -m x', 'git -c core.hookspath= commit -m x',
            'git commit --no-gpg-sign -m x', 'git push --no-verify', 'git merge --no-verify x',
        ], 2)
        result = self.run_hook('git commit --no-verify -m x')
        self.assertIn('Only the owner bypasses this gate', result.stderr.decode('utf-8'))

    def test_safe_forms_pass_on_a_clean_tree(self):
        self.assertVerdict([
            'git status', 'git log --oneline -n 5', 'git push origin main', 'git push -n origin main',
            'git push --force-with-lease=main:abc123 origin main', 'git push --force-with-lease --force-if-includes',
            'git commit -m x', 'git commit -mn', "git commit -m 'do not use --no-verify'", 'git commit -m "refuse git push --force"','git stash list',
            'git remote -v', 'git reset --hard', 'git -c color.ui=never status', 'ls -n',
        ], 0)

    def test_work_discarding_commands_are_refused_on_a_dirty_tree(self):
        self.dirty()
        self.assertVerdict([
            'git reset --hard', 'git -C . reset --hard', 'git -c x.y=1 reset --hard HEAD',
            'git checkout -- f.txt', 'git checkout -f', 'git restore f.txt', 'git restore --staged --worktree f.txt',
            'git restore -SW f.txt', 'git clean -fd', 'git clean -x -f', 'git clean --force',
        ], 2)

    def test_index_only_and_dry_run_forms_pass_on_a_dirty_tree(self):
        self.dirty()
        self.assertVerdict([
            'git clean -nd', 'git clean --dry-run -fd', 'git clean -n', 'git restore --staged f.txt',
            'git restore -S f.txt', 'git checkout main', 'git status',
        ], 0)

    def test_the_dirty_check_reads_the_tree_git_dash_C_names(self):
        self.dirty()
        self.assertVerdict(['git -C repo reset --hard'], 2, cwd=self.tmp)

    def test_amending_a_pushed_commit_is_refused(self):
        remote = self.tmp / 'remote.git'
        git(self.tmp, 'init', '-q', '--bare', str(remote))
        git(self.repo, 'remote', 'add', 'origin', str(remote))
        git(self.repo, 'push', '-q', 'origin', 'main')
        self.assertVerdict(['git commit --amend --no-edit'], 2)
        git(self.repo, 'commit', '-q', '--allow-empty', '-m', 'local')
        self.assertVerdict(['git commit --amend --no-edit'], 0)

    def test_an_unreadable_payload_blocks(self):
        result = self.run_hook(None, payload='not json')
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_git_status_is_read_as_utf8(self):
        # A text subprocess without an encoding raised EncodingWarning inside `except Exception`,
        # so a clean tree was taken for a dirty one (BACKLOG, D-1 r2).
        result = self.run_hook('git reset --hard', python_args=('-X', 'warn_default_encoding', '-W', 'error::EncodingWarning'))
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))


if __name__ == '__main__':
    unittest.main()
