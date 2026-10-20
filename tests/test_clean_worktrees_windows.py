"""scripts/clean_worktrees.sh on native Windows: liveness, the gate lock and junctions.

There the working directory of every process is read from its PEB, the gate's lock is held
when its file cannot be opened for writing, and a folder that is a reparse point (a junction,
a folder symlink) is a mount point: Git for Windows' recursive remove went through a junction
into the main checkout's virtual environment and deleted part of it. Each case builds the state
in a throwaway repository and runs the real script under Git for Windows' sh. Every case here
runs only on native Windows; elsewhere each one declares a platform skip, reported as NOT RUN
by the kit check.
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
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'overlays/claude-code/files/scripts'
SCRIPT = SCRIPTS / 'clean_worktrees.sh'
WINDOWS = os.name == 'nt'


def windows_only(test):
    def run(self):
        if not shutil.which('sh'):
            raise AssertionError('no sh on PATH: run this suite from Git for Windows or MSYS2')
        return test(self)
    run.__name__, run.__doc__ = test.__name__, test.__doc__
    run = unittest.skipUnless(WINDOWS, 'native Windows only')(run)
    run._kit_platform_skip = not WINDOWS
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
    def test_the_gates_own_state_does_not_keep_a_finished_worktree(self):
        # bge2e: gate_on_stop.sh keeps "<result> <code> <tree>" in kit-stop-gate and the names'
        # input in kit-stop-gate.tree, `git ls-files --stage` included; pre-commit keeps the tree
        # it gated in check-gated-tree. Their blob and tree ids kept every finished worker.
        path = self.worktree('done')
        state = Path(self.git('rev-parse', '--path-format=absolute', '--git-path', 'kit-stop-gate', cwd=path))
        state.with_name('kit-stop-gate.tree').write_text(
            self.git('rev-parse', 'HEAD', cwd=path) + '\n' + self.git('ls-files', '--stage', cwd=path) + '\n')
        state.write_text('pass %s %s\n' % ('1' * 40, '2' * 40))
        state.with_name('check-gated-tree').write_text(self.git('write-tree', cwd=path) + '\n')
        out = self.run_script('--apply')
        self.assertFalse(path.exists(), out)

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
    def test_a_crlf_checkout_under_autocrlf_is_removed_and_an_edit_in_it_kept(self):
        # Git for Windows' default core.autocrlf=true checks text out with CRLF: compared with
        # the raw LF blob, every finished worktree read as "not byte for byte" and was kept
        # (16 stale worktrees, dry run 2026-10-16). The checkout's own bytes are the reference.
        # The script drops GIT_CONFIG_COUNT with git's other local variables: the setting
        # reaches it from a config file, as Git for Windows' system config gives it.
        self.env['GIT_CONFIG_VALUE_2'] = 'true'
        self.git('config', 'core.autocrlf', 'true')
        (self.main / 'lf.txt').write_bytes(b'one\ntwo\n')
        self.git('add', 'lf.txt')
        self.git('commit', '-q', '-m', 'an LF text file')
        path = self.worktree('crlf')
        self.assertEqual((path / 'lf.txt').read_bytes(), b'one\r\ntwo\r\n')
        out = self.run_script('--apply')
        self.assertFalse(path.exists(), out)
        path = self.worktree('edited')
        (path / 'a').write_bytes(b'a\r\nan edit the stat cache hides\r\n')
        self.git('update-index', '--assume-unchanged', 'a', cwd=path)
        self.assertEqual(self.git('status', '--porcelain', cwd=path), '')
        self.assertKept(path, self.run_script('--apply'), 'not byte for byte what its index records')

    @windows_only
    def test_a_native_process_working_inside_keeps_it(self):
        path = self.worktree('busy')
        child = self.start_inside([sys.executable, '-c', 'import sys; sys.stdin.read()'], path)
        out = self.run_script('--apply')
        self.assertProcessKept(path, out, child.pid)

    @windows_only
    def test_a_process_working_past_260_characters_keeps_it(self):
        # A working directory past MAX_PATH (proposal D-4): the handle's name comes back whole
        # (\\?\C:\..., as every name does) and the audit still finds the worktree in it.
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\FileSystem') as key:
            self.assertEqual(winreg.QueryValueEx(key, 'LongPathsEnabled')[0], 1,
                             'the case needs LongPathsEnabled=1, as GitHub-hosted Windows runners have')
        path = self.worktree('long')
        deep = path / ('d' * 120) / ('e' * 120)
        deep.mkdir(parents=True)
        self.assertGreater(len(str(deep)), 260)
        # CreateProcess refuses a working directory past MAX_PATH; the process enters it itself,
        # from outside the worktree, so only the long path can keep it.
        child = self.start_inside([sys.executable, '-c', 'import os, sys; os.chdir(sys.argv[1]); sys.stdin.read()',
                                   str(deep)], self.tmp)

        def remove_deep():
            # cmd's rmdir stops at MAX_PATH; the child must leave first.
            child.kill()
            child.wait()
            shutil.rmtree(path / ('d' * 120), ignore_errors=True)
        self.addCleanup(remove_deep)
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
        # Git names the worktree by its long path; the temp folder may come as an 8.3 short name
        # (C:/Users/RUNNER~1 on a CI runner).
        self.assertIn(Path(os.path.realpath(path)).as_posix(), self.git('worktree', 'list', '--porcelain'))
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

    @windows_only
    def test_a_disposable_entry_takes_effect_only_committed_and_slash_names_the_root_alone(self):
        # #288 (tests/test_clean_worktrees.py proves it on POSIX): an uncommitted `build` entry
        # removed a worktree with an uncopied build/ scratch file at the next merge; and no entry
        # could name the root's build alone.
        disposable = self.main / '.claude/worktree-disposable'
        disposable.parent.mkdir()
        disposable.write_text('cache\n')
        self.git('add', '.claude/worktree-disposable')
        self.git('commit', '-q', '-m', 'list')
        disposable.write_text('build\n')
        path = self.worktree('done')
        (path / 'build').mkdir()
        (path / 'build/out.o').write_text('o\n')
        (path / 'src/build').mkdir(parents=True)
        (path / 'src/build/scratch.py').write_text('only here\n')
        out = self.run_script('--apply')
        self.assertIn('differs from its committed version; only the entries in both apply', out)
        self.assertKept(path, out, 'outside a disposable folder: build/out.o')
        disposable.write_text('/build\n')
        self.git('commit', '-q', '-am', 'the root build is disposable')
        self.assertKept(path, self.run_script('--apply'), 'outside a disposable folder: src/build/scratch.py')
        (path / 'src/build/scratch.py').unlink()
        # Kept for another reason when /build came in, it keeps the list before it: build/out.o
        # is previewed once.
        self.assertIn('would remove .claude/worktrees/done', self.run_script('--apply'))
        out = self.run_script('--apply')
        self.assertFalse(path.exists(), out)

    @windows_only
    def test_a_changed_disposable_list_previews_its_removals_before_the_next_apply_makes_them(self):
        # #288 point 2 (tests/test_clean_worktrees.py proves it on POSIX): a new entry took
        # uncopied scratch at the next merge, unseen by the owner.
        disposable = self.main / '.claude/worktree-disposable'
        disposable.parent.mkdir()
        disposable.write_text('build\n')
        (self.main / '.gitignore').write_text('build/\nout/\n/.claude/worktrees/\n')
        self.git('add', '.gitignore', '.claude/worktree-disposable')
        self.git('commit', '-q', '-m', 'list')
        old = self.worktree('old')
        (old / 'build').mkdir()
        (old / 'build/out.o').write_text('o\n')
        new = self.worktree('new')
        (new / 'out').mkdir()
        (new / 'out/scratch.py').write_text('only here\n')
        out = self.run_script('--apply')
        self.assertFalse(old.exists(), out)  # no list recorded yet: the one in force is adopted
        self.assertKept(new, out, 'outside a disposable folder: out/scratch.py')
        disposable.write_text('build\nout\n')
        self.git('commit', '-q', '-am', 'out is disposable')
        out = self.run_script('--apply', '--quiet')  # what the post-merge hook runs
        self.assertIn('would remove .claude/worktrees/new (branch worktree-new, 0 identical files, ', out)
        self.assertIn('not yet: files only the changed .claude/worktree-disposable makes disposable', out)
        self.assertTrue((new / 'out/scratch.py').is_file())
        out = self.run_script('--apply')
        self.assertFalse(new.exists(), out)

    @windows_only
    def test_an_only_run_previews_then_removes_and_a_kept_worktree_keeps_the_list_it_was_covered_by(self):
        # Round-1 review of #288 point 2 (tests/test_clean_worktrees.py proves it on POSIX):
        # close_worker.sh's --apply --only=NAME previewed forever, as only a full --apply recorded
        # the list; a dry run called the preview a removal; and a worktree kept when the list
        # changed was later removed under the new list unseen.
        disposable = self.main / '.claude/worktree-disposable'
        disposable.parent.mkdir()
        disposable.write_text('build\n')
        (self.main / '.gitignore').write_text('build/\nout/\n/.claude/worktrees/\n')
        self.git('add', '.gitignore', '.claude/worktree-disposable')
        self.git('commit', '-q', '-m', 'list')
        new, held = self.worktree('new'), self.worktree('held')
        for path in (new, held):
            (path / 'out').mkdir()
            (path / 'out/scratch.py').write_text('only here\n')
        self.git('worktree', 'lock', str(held))
        self.run_script('--apply')
        disposable.write_text('build\nout\n')
        self.git('commit', '-q', '-am', 'out is disposable')
        out = self.run_script('--only=new')
        self.assertIn('would preview .claude/worktrees/new (branch worktree-new, ', out)
        self.assertIn('dry run: would remove 0, keep 1,', out)
        out = self.run_script('--apply', '--only=new', '--no-quiet')
        self.assertIn('would remove .claude/worktrees/new (branch worktree-new, ', out)
        self.assertTrue((new / 'out/scratch.py').is_file(), out)
        out = self.run_script('--apply', '--only=new', '--no-quiet')
        self.assertFalse(new.exists(), out)
        self.assertKept(held, self.run_script('--apply'), 'locked (git worktree lock)')
        self.git('worktree', 'unlock', str(held))
        out = self.run_script('--apply')
        self.assertIn('would remove .claude/worktrees/held (branch worktree-held, ', out)
        self.assertTrue((held / 'out/scratch.py').is_file(), out)
        out = self.run_script('--apply')
        self.assertFalse(held.exists(), out)

    @windows_only
    def test_an_uncommitted_narrowing_of_the_disposable_list_protects_at_once(self):
        # Round-1 review of #288: following the committed list alone, a removal took uncopied
        # scratch that the owner had just taken off the list, before the edit was committed.
        disposable = self.main / '.claude/worktree-disposable'
        disposable.parent.mkdir()
        disposable.write_text('build\n')
        self.git('add', '.claude/worktree-disposable')
        self.git('commit', '-q', '-m', 'list')
        disposable.write_text('')
        path = self.worktree('done')
        (path / 'src/build').mkdir(parents=True)
        (path / 'src/build/scratch.py').write_text('only here\n')
        self.assertKept(path, self.run_script(), 'outside a disposable folder: src/build/scratch.py')
        self.assertKept(path, self.run_script('--apply'), 'outside a disposable folder: src/build/scratch.py')
        self.assertTrue((path / 'src/build/scratch.py').is_file())

    @windows_only
    def test_paths_print_and_log_with_single_separators(self):
        # #243: show() escaped every Windows separator as \\, in the output and the log.
        path = self.worktree('sep')
        (path / 'notes.txt').write_text('only here\n')
        out = self.run_script()
        self.assertIn('keep   .claude/worktrees/sep\n', out)
        (path / 'notes.txt').unlink()
        out = self.run_script('--apply')
        self.assertFalse(path.exists(), out)
        self.assertNotIn('\\\\', out)
        log = (self.main / '.git/kit-worktree-removals.log').read_text(encoding='utf-8')
        self.assertIn('\toutcome\t%s\tremoved' % os.path.realpath(path).replace('\\', '/'), log)

    @windows_only
    def test_a_nested_repository_is_named_as_one(self):
        # #244: its .git internals were listed as unique files, the cause never named.
        path = self.worktree('nest')
        (path / 'vendor/lib').mkdir(parents=True)
        self.git('init', '-q', cwd=path / 'vendor/lib')
        out = self.run_script('--all-reasons')
        self.assertKept(path, out, 'holds a nested repository (a .git of its own), outside a disposable folder, '
                        'whose history this script does not judge: vendor/lib\n')
        self.assertNotIn('vendor/lib/.git/', out)

    @windows_only
    def test_a_worktree_kept_for_its_files_is_never_read_byte_for_byte(self):
        # #196: the byte check read every tracked file (LFS and CRLF ones twice) before the
        # untracked files kept the worktree, after every merge. It now runs last.
        path = self.worktree('built')
        (path / 'a').write_bytes(b'an edit the stat cache hides\n')
        self.git('update-index', '--assume-unchanged', 'a', cwd=path)
        (path / 'notes.txt').write_text('only here\n')
        out = self.run_script()
        self.assertKept(path, out, 'files with no identical copy in main, outside a disposable folder: notes.txt')
        self.assertNotIn('byte for byte', out)
        (path / 'notes.txt').unlink()
        self.assertKept(path, self.run_script(), 'not byte for byte what its index records')

    @windows_only
    def test_a_file_held_open_from_outside_keeps_it_whole_and_a_leftover_folder_is_reported(self):
        # #193: a holder whose working directory is elsewhere went unseen; `git worktree remove`
        # deleted part of the worktree and failed, and every later run said nothing of the rest.
        (self.main / '.claude').mkdir()
        (self.main / '.claude/worktree-disposable').write_text('build\n')
        path = self.worktree('held')
        (path / 'build').mkdir()
        (path / 'build/vc140.pdb').write_bytes(b'x' * 1024)
        self.start_inside([sys.executable, '-c', 'import sys; f = open(sys.argv[1], "rb"); sys.stdin.read()',
                           str(path / 'build/vc140.pdb')], self.tmp)
        out = self.run_script('--apply')
        self.assertIn('Windows refuses to move its folder', out)
        self.assertTrue((path / '.git').is_file(), out)
        self.assertTrue((path / 'held.txt').is_file(), out)
        self.assertIn('held', self.git('worktree', 'list'))
        stray = self.main / '.claude/worktrees/stray'
        stray.mkdir()
        (stray / 'x.txt').write_text('left over\n')
        out = self.run_script()
        self.assertIn('clean_worktrees: left as it is: .claude/worktrees/stray is a folder no registered worktree '
                      'names', out)
        result = subprocess.run(['sh', str(SCRIPT), '--apply', '--only=stray'], cwd=self.main, env=self.env,
                                capture_output=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertTrue((stray / 'x.txt').is_file())

    @windows_only
    def test_a_path_with_a_newline_is_kept_as_not_printable(self):
        # NTFS refuses a newline in a name, so git and the folder are stood in for, git answering
        # rev-parse as it does, one line per flag. Split on newlines, the answer once judged such a
        # worktree not its own, and the reason printed was not the real one (issue #41).
        sys.path.insert(0, str(SCRIPTS))
        import clean_worktrees
        home = os.path.realpath(os.fsencode(self.main / '.claude/worktrees'))
        real = os.path.join(home, b'new\nline')
        common = os.path.realpath(os.fsencode(self.main / '.git'))
        answers = {'--show-toplevel': real, '--git-common-dir': common}

        def git(cwd, *args, **kwargs):
            self.assertEqual(args[0], 'rev-parse')
            return subprocess.CompletedProcess(args, 0, b''.join(answers[a] + b'\n' for a in args[1:]), b'')

        is_dir = os.path.isdir
        ctx = {'main_root': os.path.realpath(os.fsencode(self.main)), 'own': b'', 'home': home,
               'common': common, 'all': False}
        record = {'worktree': real, 'branch': b'refs/heads/worktree-newline', 'HEAD': b'0' * 40}
        with unittest.mock.patch.object(clean_worktrees, 'git', git), \
                unittest.mock.patch.object(os.path, 'isdir', lambda p: p == real or is_dir(p)):
            reasons, facts = clean_worktrees.audit(record, ctx)
        self.assertIsNone(facts)
        self.assertEqual(reasons, ['its path or branch name is not printable UTF-8: the command that brings '
                                   'it back could not be printed'])


if __name__ == '__main__':
    unittest.main()
