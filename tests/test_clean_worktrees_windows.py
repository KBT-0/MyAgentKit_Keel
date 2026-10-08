"""scripts/clean_worktrees.sh on native Windows: liveness, the gate lock and junctions.

There the working directory of every process is read from its PEB, the gate's lock is held
when its file cannot be opened for writing, and a folder that is a reparse point (a junction,
a folder symlink) is a mount point: Git for Windows' recursive remove went through a junction
into the main checkout's virtual environment and deleted part of it. Each case builds the state
in a throwaway repository and runs the real script under Git for Windows' sh. Every case here
runs only on native Windows; elsewhere each one prints a NOT RUN line and passes.
"""
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'overlays/claude-code/files/scripts'
SCRIPT = SCRIPTS / 'clean_worktrees.sh'
WINDOWS = os.name == 'nt'


def windows_only(test):
    def run(self):
        if not WINDOWS:
            sys.stderr.write('\nNOT RUN: %s (native Windows only)\n' % self.id())
            return
        if not shutil.which('sh'):
            raise AssertionError('no sh on PATH: run this suite from Git for Windows or MSYS2')
        return test(self)
    run.__name__, run.__doc__ = test.__name__, test.__doc__
    return run


class CleanWorktreesOnWindows(unittest.TestCase):
    def setUp(self):
        if not WINDOWS:
            return
        self.tmp = Path(tempfile.mkdtemp(prefix='kit-clean-win-'))
        self.addCleanup(self.remove_tree, self.tmp)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                        GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid',
                        CLEAN_WORKTREES_NOW=str(time.time() + 7200), PYTHONUTF8='1',
                        GIT_CONFIG_COUNT='3', GIT_CONFIG_KEY_0='gc.auto', GIT_CONFIG_VALUE_0='0',
                        GIT_CONFIG_KEY_1='maintenance.auto', GIT_CONFIG_VALUE_1='false',
                        GIT_CONFIG_KEY_2='core.autocrlf', GIT_CONFIG_VALUE_2='false')
        for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'CLEAN_WORKTREES_PROC'):
            self.env.pop(name, None)
        self.main = self.tmp / 'main'
        self.main.mkdir()
        self.git('init', '-q', '-b', 'main')
        (self.main / '.gitignore').write_text('build/\n/.claude/worktrees/\n')
        (self.main / 'a').write_text('a\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'base')
        self.children = []
        self.addCleanup(self.stop_children)

    @staticmethod
    def remove_tree(path):
        # rmdir /s removes a junction as a link and never goes through it.
        subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', str(path)], capture_output=True)

    def stop_children(self):
        for child in self.children:
            child.kill()
            child.wait()
            child.stdin.close()

    def git(self, *args, cwd=None):
        result = subprocess.run(['git', *args], cwd=cwd or self.main, env=self.env, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        return result.stdout.decode(errors='replace').strip()

    def worktree(self, name):
        """A worker's worktree with one commit, merged into main."""
        path = self.main / '.claude/worktrees' / name
        self.git('worktree', 'add', '-q', str(path), '-b', 'worktree-' + name)
        (path / (name + '.txt')).write_text(name + '\n')
        self.git('add', name + '.txt', cwd=path)
        self.git('commit', '-q', '-m', 'work in ' + name, cwd=path)
        self.git('merge', '-q', '--no-edit', 'worktree-' + name)
        return path

    def run_script(self, *args):
        result = subprocess.run(['sh', str(SCRIPT), *args], cwd=self.main, env=self.env, capture_output=True)
        out = result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace')
        self.assertNotIn('Traceback', out)
        return out

    def start_inside(self, command, cwd):
        """A process whose working directory is CWD, running until the case ends."""
        child = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        self.children.append(child)
        time.sleep(1)  # the process has set its working directory
        return child

    def assertKept(self, path, out, reason):
        self.assertTrue(path.is_dir(), 'removed although it had to be kept:\n' + out)
        self.assertIn('keep   .claude', out)
        self.assertIn(reason, out)

    def assertProcessKept(self, path, out, pid):
        self.assertKept(path, out, 'works inside it')
        match = re.search(r'in use: process ([0-9, ]+) works inside it', out)
        self.assertIsNotNone(match, out)
        self.assertIn(pid, [int(value) for value in match[1].split(',')], out)

    @windows_only
    def test_a_finished_idle_worktree_is_removed(self):
        path = self.worktree('done')
        out = self.run_script('--apply')
        self.assertFalse(path.exists(), out)
        self.assertIn('processes listed by the Windows process table', out)
        self.assertIn('worktree-done', self.git('branch', '--list', 'worktree-done'))

    @windows_only
    def test_a_finished_worktree_with_an_executable_script_is_removed(self):
        # Codex review: core.fileMode=true and the executable-bit comparison read a tracked
        # 100755 script as modified on Windows, which keeps no such bit: the kit's own layout
        # (scripts/*.sh) kept every finished worktree.
        path = self.main / '.claude/worktrees/script'
        self.git('worktree', 'add', '-q', str(path), '-b', 'worktree-script')
        (path / 'run.sh').write_text('#!/bin/sh\necho ran\n')
        self.git('add', '--chmod=+x', 'run.sh', cwd=path)
        self.git('commit', '-q', '-m', 'an executable script', cwd=path)
        self.assertIn('100755', self.git('ls-files', '-s', 'run.sh', cwd=path))
        self.git('merge', '-q', '--no-edit', 'worktree-script')
        out = self.run_script('--apply')
        self.assertFalse(path.exists(), out)

    @windows_only
    def test_a_native_process_working_inside_keeps_it(self):
        path = self.worktree('busy')
        child = self.start_inside([sys.executable, '-c', 'import sys; sys.stdin.read()'], path)
        out = self.run_script('--apply')
        self.assertProcessKept(path, out, child.pid)

    @windows_only
    def test_a_process_that_entered_through_a_junction_keeps_it(self):
        # Codex review: the PEB names the junction's path, the audit compared the resolved
        # worktree path, and the worktree was removed while the process worked in it.
        path = self.worktree('aliased')
        alias = self.tmp / 'alias'
        made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(path)], capture_output=True)
        self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
        child = self.start_inside([sys.executable, '-c', 'import sys; sys.stdin.read()'], alias)
        out = self.run_script('--apply')
        self.assertProcessKept(path, out, child.pid)

    @windows_only
    def test_a_retargeted_junction_keeps_the_directory_the_process_holds(self):
        path = self.worktree('retargeted')
        tracked = {name: (path / name).read_bytes()
                   for name in self.git('ls-files', cwd=path).splitlines()}
        alias = self.tmp / 'alias'
        other = self.tmp / 'other'
        other.mkdir()
        made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(path)], capture_output=True)
        self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
        self.start_inside([sys.executable, '-c', 'import sys; sys.stdin.read()'], alias)
        # Remove only the junction, then point the same pathname somewhere else before audit.
        alias.rmdir()
        made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(other)], capture_output=True)
        self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
        out = self.run_script('--apply')
        self.assertKept(path, out, 'works inside it')
        self.assertIn(path.as_posix(), self.git('worktree', 'list', '--porcelain'))
        self.assertEqual({name: (path / name).read_bytes() for name in tracked}, tracked)

    @windows_only
    def test_a_junction_worker_with_a_venv_launcher_keeps_it(self):
        import venv
        from unittest.mock import patch
        env = self.tmp / 'venv'
        venv.EnvBuilder(with_pip=False).create(env)
        with patch.object(sys, 'executable', str(env / 'Scripts/python.exe')):
            self.test_a_process_that_entered_through_a_junction_keeps_it()

    @windows_only
    def test_a_git_bash_shell_in_a_subfolder_keeps_it(self):
        # An MSYS process keeps its own working directory; the PEB copy follows it.
        path = self.worktree('shell')
        (path / 'sub').mkdir()
        self.start_inside(['sh', '-c', 'cd sub && read line'], path)
        out = self.run_script('--apply')
        self.assertKept(path, out, 'works inside it')

    @windows_only
    def test_a_held_gate_lock_keeps_it(self):
        path = self.worktree('gated')
        lock = Path(self.git('rev-parse', '--absolute-git-dir', cwd=path)) / 'check.lock'
        # As the gate's holder opens it: for writing, shared for reading only.
        holder = self.start_inside([sys.executable, '-c', (
            'import ctypes, sys\n'
            'k = ctypes.WinDLL("kernel32", use_last_error=True)\n'
            'k.CreateFileW.restype = ctypes.c_void_p\n'
            'k.CreateFileW.argtypes = (ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,'
            ' ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p)\n'
            'h = k.CreateFileW(sys.argv[1], 0xC0000000, 1, None, 4, 0x80, None)\n'
            'assert h not in (None, ctypes.c_void_p(-1).value)\n'
            'sys.stdin.read()\n'), str(lock)], self.tmp)
        out = self.run_script('--apply')
        self.assertKept(path, out, 'in use: the gate holds its lock')
        holder.stdin.close()
        holder.wait()
        out = self.run_script('--apply')
        self.assertFalse(path.exists(), out)

    @windows_only
    def test_a_junction_inside_keeps_it_and_its_target_is_untouched(self):
        # The data-loss case: a worker linked the main checkout's virtual environment into its
        # worktree; `git worktree remove` followed the junction and deleted part of the target.
        path = self.worktree('linked')
        sentinel = self.tmp / 'shared-venv'
        sentinel.mkdir()
        (sentinel / 'keep.txt').write_text('shared\n')
        (path / 'build').mkdir()
        link = path / 'build' / 'venv'
        made = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(sentinel)], capture_output=True)
        self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
        (self.main / '.claude/worktree-disposable').write_text('build\n')
        out = self.run_script('--apply')
        self.assertKept(path, out, 'holds a mount point')
        self.assertEqual((sentinel / 'keep.txt').read_text(), 'shared\n')


if __name__ == '__main__':
    unittest.main()
