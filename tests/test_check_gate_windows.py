"""The gate lock on native Windows: Git for Windows' sh running the gate, a native python3.

Native Windows Python has no fcntl. The gate there holds its lock as a file handle opened
without write sharing, which the holder makes inheritable, so the gate and every process it
starts keep it and Windows closes it when the last of them exits. A nested run proves the
inherited handle: open in its own process on this lock file, with write access, while a fresh
open for writing is refused, the file compared by FILE_ID_INFO. Platform-specific cases run
only on native Windows; elsewhere they declare platform skips, reported as NOT RUN by the kit check.
On native Windows no case is NOT RUN: a guard whose case cannot run there fails.
"""
import ctypes
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'core/scripts'))
import agent_process  # noqa: E402

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


if WINDOWS:
    from ctypes import wintypes
    KERNEL32 = ctypes.WinDLL('kernel32', use_last_error=True)
    KERNEL32.CreateFileW.restype = wintypes.HANDLE
    KERNEL32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    KERNEL32.CloseHandle.argtypes = (wintypes.HANDLE,)
    KERNEL32.GetCurrentProcess.restype = wintypes.HANDLE
    KERNEL32.DuplicateHandle.argtypes = (wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                         ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL,
                                         wintypes.DWORD)
    KERNEL32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    KERNEL32.OpenProcess.restype = wintypes.HANDLE
    KERNEL32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    KERNEL32.GetProcessId.restype = wintypes.DWORD
    KERNEL32.GetProcessId.argtypes = (wintypes.HANDLE,)
    KERNEL32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    KERNEL32.WaitForSingleObject.restype = wintypes.DWORD
    KERNEL32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    KERNEL32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(ctypes.c_uint64),) * 4

    class ProcessBasicInformation(ctypes.Structure):
        _fields_ = [('ExitStatus', ctypes.c_long), ('PebBaseAddress', ctypes.c_void_p),
                    ('AffinityMask', ctypes.c_size_t), ('BasePriority', ctypes.c_long),
                    ('UniqueProcessId', ctypes.c_size_t), ('InheritedFromUniqueProcessId', ctypes.c_size_t)]

    NTDLL = ctypes.WinDLL('ntdll')
    NTDLL.NtQueryInformationProcess.argtypes = (wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p,
                                               wintypes.ULONG, ctypes.POINTER(wintypes.ULONG))

    class ProcessEntry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', ctypes.c_long),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_wchar * 260)]

GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
SHARE_READ, SHARE_WRITE = 1, 2


def open_handle(path, access, share, inheritable=True):
    """A Win32 handle on path (created if absent), inherited by children started with
    close_fds=False when inheritable; the caller closes it with close_handle."""
    handle = KERNEL32.CreateFileW(str(path), access, share, None, 4, 0x80, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    os.set_handle_inheritable(handle, inheritable)
    return handle


def close_handle(handle):
    KERNEL32.CloseHandle(handle)


def children(pid):
    """(pid, image name) of each direct child of pid."""
    snapshot = KERNEL32.CreateToolhelp32Snapshot(2, 0)
    entry = ProcessEntry()
    entry.dwSize = ctypes.sizeof(ProcessEntry)
    found = []
    try:
        ok = KERNEL32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.th32ParentProcessID == pid:
                found.append((entry.th32ProcessID, entry.szExeFile))
            ok = KERNEL32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        KERNEL32.CloseHandle(snapshot)
    return found


def set_reparse_point(path):
    """Make path a file carrying a reparse point with a non-Microsoft tag. Unlike a symlink,
    this needs no privilege; Python's os.remove deletes it, MSYS rm cannot."""
    import struct
    KERNEL32.DeviceIoControl.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                         ctypes.c_void_p)
    handle = KERNEL32.CreateFileW(str(path), GENERIC_WRITE, 0, None, 2, 0x02200000, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        data = struct.pack('<IHH', 0x99, 8, 0) + bytes(range(1, 17)) + b'reparse!'
        if not KERNEL32.DeviceIoControl(handle, 0x000900A4, data, len(data), None, 0,
                                        ctypes.byref(wintypes.DWORD()), None):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        KERNEL32.CloseHandle(handle)


PROBE_RUNNER = '''
import ctypes, os, sys
mode, source = sys.argv[1], sys.argv[2]
sys.argv = ['-c'] + sys.argv[3:]
if mode == 'noid':
    real = ctypes.WinDLL
    class Failing:
        argtypes = restype = None
        def __call__(self, *args):
            ctypes.set_last_error(87)
            return 0
    class Proxy:
        def __init__(self, dll):
            object.__setattr__(self, 'dll', dll)
            object.__setattr__(self, 'failing', Failing())
        def __getattr__(self, name):
            return self.failing if name == 'GetFileInformationByHandleEx' else getattr(self.dll, name)
    ctypes.WinDLL = lambda *a, **k: Proxy(real(*a, **k))
exec(compile(open(source, encoding='utf-8').read(), '<probe>', 'exec'), {'__name__': '__main__'})
'''

def terminate(handle):
    """Force the process behind `handle` to exit, and wait until it has: TerminateProcess only
    starts the exit. Not taskkill: restricted Windows hosts deny it even for these children.
    A denied termination of a live process fails the test."""
    killed = KERNEL32.TerminateProcess(handle, 1)
    error = ctypes.get_last_error()
    # TerminateProcess reports access denied for a process already exiting (the python3
    # alias's launcher takes the real python with it). Its handle is signalled once it has
    # gone; a denied process still live then fails.
    waited = KERNEL32.WaitForSingleObject(handle, 10000)
    if waited != 0:
        if waited == 0xffffffff:
            raise ctypes.WinError(ctypes.get_last_error())
        if not killed:
            raise ctypes.WinError(error)
        raise OSError('process exit was not signalled after termination (wait result %#x)' % waited)


def created(handle):
    """The creation time of the process behind `handle` (FILETIME ticks)."""
    times = [ctypes.c_uint64() for _ in range(4)]
    if not KERNEL32.GetProcessTimes(handle, *map(ctypes.byref, times)):
        raise ctypes.WinError(ctypes.get_last_error())
    return times[0].value


def parent_pid(handle):
    """The parent pid recorded by the process behind `handle`, not by a process snapshot."""
    info = ProcessBasicInformation()
    status = NTDLL.NtQueryInformationProcess(handle, 0, ctypes.byref(info), ctypes.sizeof(info), None)
    if status != 0:
        raise OSError('cannot read process parent (NTSTATUS %#x)' % (status & 0xffffffff))
    return info.InheritedFromUniqueProcessId


def child_handle(pid, parent_handle):
    """A terminate and wait handle on `pid` only if its parent matches the retained handle.
    A younger creation time also rules out children of an earlier process with that parent pid."""
    handle = KERNEL32.OpenProcess(0x1 | 0x1000 | 0x00100000, False, pid)
    try:
        if handle and parent_pid(handle) == KERNEL32.GetProcessId(parent_handle) and \
                created(handle) >= created(parent_handle):
            return handle
    except OSError:
        pass
    if handle:
        close_handle(handle)
    return None


def descendants(proc):
    """(pid, parent pid, image name, handle) of each descendant of proc, parents before
    children; the caller closes each handle. Each acquired handle's parent pid and creation
    time must match the retained parent, so a snapshot pid replaced before OpenProcess is
    never trusted. Every handle stays open through the walk. Not a Job Object
    query: the Python install manager's python3 alias starts the gate's lock holder outside
    the fixture's job, with the gate and the build below it."""
    found, parents = [], [(proc.pid, int(proc._handle))]
    for parent, parent_handle in parents:
        for pid, name in children(parent):
            handle = None if any(pid == seen for seen, _ in parents) else child_handle(pid, parent_handle)
            if handle:
                found.append((pid, parent, name, handle))
                parents.append((pid, handle))
    return found


def kill_tree(proc):
    # Parents before children, then the job. TerminateJobObject alone stops the job's
    # processes in no fixed order: the build died before the lock holder, which saw its gate
    # end and cleared the token test_variables_copied_out_of_a_killed_gate_are_refused reads.
    # Every kill goes through a handle descendants() checked, never a bare pid; the job then
    # stops what started inside it after the walk.
    members = descendants(proc)
    try:
        for *_, handle in members:
            terminate(handle)
    finally:
        for *_, handle in members:
            close_handle(handle)
        agent_process.stop_group(proc, proc.pid)


def read_line(stream, seconds=30):
    """stream.readline(), raising queue.Empty after `seconds` instead of hanging the suite."""
    lines = queue.SimpleQueue()
    threading.Thread(target=lambda: lines.put(stream.readline()), daemon=True).start()
    return lines.get(timeout=seconds)


def released(lock, seconds=45):
    """Wait until no process holds `lock` (a write open succeeds). A killed build's handles
    close only once Windows has ended it, which on a CI runner can lag kill_tree."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            with open(lock, 'a'):
                return
        except FileNotFoundError:
            return
        except PermissionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def make_project(path):
    """A project the gate passes: every marker filled, the build is $GATE_TEST_BUILD."""
    (path / 'scripts').mkdir(parents=True)
    (path / 'docs').mkdir()
    text = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
    text = text.replace('{{TOOLCHAIN_PATH_SETUP}}', '').replace('{{BUILD_TEST_COMMAND}}',
                                                                'sh $GATE_TEST_BUILD')
    files = {'scripts/check.sh': re.sub(r'\{\{[A-Z0-9_]+\}\}', 'fixture', text),
             'scripts/boundary_checks.sh': '# The fixture has no boundaries.\n',
             'docs/STATE.md': '# STATE\n\n## Active work\n',
             'docs/PROJECT.md': '# PROJECT\n\n## Contents\n'}
    for name, content in files.items():
        (path / name).write_text(content, encoding='utf-8', newline='\n')
    (path / 'scripts/check.sh').chmod(0o755)  # the Stop and pre-commit hooks run ./scripts/check.sh
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    # Git for Windows' default core.autocrlf=true would check a linked worktree's gate out as CRLF.
    subprocess.run(['git', 'config', 'core.autocrlf', 'false'], cwd=path, check=True)


def environment(build, **extra):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('GATE_', 'BOUNDARY_')) and k not in ('CDPATH', 'CI')}  # CI turns the cache off
    env.update(GATE_TEST_BUILD=build.as_posix(), **extra)
    return env


def start(cwd, build, **extra):
    return agent_process.launch(['sh', 'scripts/check.sh'], None, cwd=cwd, env=environment(build, **extra),
                                text=True, errors='replace', stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, close_fds=False)


def finish(proc, timeout=90):
    try:
        out = proc.communicate(timeout=timeout)[0]
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        return None, proc.communicate()[0]
    finally:
        kill_tree(proc)
    return proc.returncode, out


def gate(cwd, build, timeout=90, **extra):
    return finish(start(cwd, build, **extra), timeout)


class KillTreeTests(unittest.TestCase):
    # The helpers' own self-checks are in tests/test_check_gate_windows_harness.py: they test
    # this file, not the kit, and do not count toward this suite's minimum (#263).
    @windows_only
    def test_kill_tree_stops_a_child_started_after_its_snapshot(self):
        # A real descendant starts after a walk that misses it (children() patched to find
        # none). The launch job still owns it.
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scripts').mkdir()
            (root / 'scripts/check.sh').write_text('exec "$FIXTURE_PYTHON" -u parent.py\n')
            (root / 'parent.py').write_text(
                'import os, pathlib, subprocess, sys, time\n'
                'print("ready", flush=True)\n'
                'while not pathlib.Path(os.environ["GATE_TEST_BUILD"]).exists(): time.sleep(.01)\n'
                'child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])\n'
                'print(child.pid, flush=True)\nchild.wait()\n')
            proc = start(root, root / 'spawn', FIXTURE_PYTHON=sys.executable)
            handle = None
            try:
                self.assertIsNotNone(proc._kit_job, 'the fixture must join its job before running')
                self.assertEqual(read_line(proc.stdout).strip(), 'ready')
                with patch.object(sys.modules[__name__], 'children', return_value=[]):
                    (root / 'spawn').touch()
                    pid = int(read_line(proc.stdout))
                    handle = KERNEL32.OpenProcess(0x00100000, False, pid)
                    self.assertTrue(handle, 'the descendant must still exist before cleanup')
                    self.assertEqual(KERNEL32.WaitForSingleObject(handle, 0), 0x102)
                    began = time.monotonic()
                    kill_tree(proc)
                # Within half its sleep: a cleanup that only waited saw it end by itself.
                self.assertEqual(KERNEL32.WaitForSingleObject(handle, 10000), 0,
                                 'cleanup left the late descendant alive')
                self.assertLess(time.monotonic() - began, 30, 'cleanup waited for the descendant to end')
            finally:
                kill_tree(proc)
                proc.communicate()
                if handle:
                    close_handle(handle)


class WindowsGateLockTests(unittest.TestCase):
    def setUp(self):
        if not WINDOWS:
            return
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / 'project'
        make_project(self.project)
        self.build = self.tmp / 'build.sh'
        self.side = self.tmp / 'side'
        self.side.mkdir()
        self.lock = self.project / '.git' / 'check.lock'

    def write_build(self, text):
        self.build.write_text(text, encoding='utf-8', newline='\n')

    def lock_form(self):
        """The lock path in the form the gate compares GATE_LOCK_HELD with."""
        return subprocess.run(['sh', '-c', 'cygpath -m "$(pwd -P)/.git/check.lock"'], cwd=self.project,
                              capture_output=True, text=True, check=True).stdout.strip()

    @windows_only
    def test_the_gate_passes_holding_its_lock(self):
        # v0.9 failed every run here: "FAIL [lock]: python3 has no fcntl module".
        self.write_build('( : >> "$GATE_TEST_LOCK" ) 2>/dev/null && echo free > "$SIDE/during" '
                         '|| echo held > "$SIDE/during"\n')
        code, out = gate(self.project, self.build, GATE_TEST_LOCK=self.lock.as_posix(),
                         SIDE=self.side.as_posix())
        self.assertEqual(code, 0, out)
        self.assertIn('CHECK: PASS', out)
        self.assertEqual((self.side / 'during').read_text().strip(), 'held',
                         'the build ran while a fresh open for writing could take the lock file')
        # The lock is released when the gate ends, and nothing was written into it.
        close_handle(open_handle(self.lock, GENERIC_READ | GENERIC_WRITE, SHARE_READ))
        self.assertEqual(self.lock.read_text(), '')

    @windows_only
    def test_a_held_lock_makes_a_second_run_wait_and_a_bounded_wait_not_run(self):
        self.write_build('true\n')
        handle = open_handle(self.lock, GENERIC_READ | GENERIC_WRITE, SHARE_READ, inheritable=False)
        try:
            code, out = gate(self.project, self.build, GATE_LOCK_WAIT='2')
        finally:
            close_handle(handle)
        self.assertEqual(code, 75, out)
        # The count is this run's wait: "has held ... for 0s" read as the holder's age (#250).
        lock = self.lock_form()
        self.assertIn('NOTE [lock]: another gate run, or a process it started, holds %s; '
                      'this run has waited 0s for it.' % lock, out)
        self.assertIn('To see the holder: Resource Monitor', out)
        self.assertIn('NOT RUN [lock]: another gate run, or a process it started, holds %s; '
                      'this run waited 2s for it and GATE_LOCK_WAIT=2 ran out.' % lock, out)

    @windows_only
    def test_a_nested_run_starts_no_python_and_the_holder_two(self):
        # Each start of the python3 alias cost about 0.4 s, seven before the gate body: a nested
        # run calls the holder's interpreter and checks nothing, and the first pass finds and
        # checks its Python in one start (#249). Shims on PATH log each start through it.
        shims, log = self.tmp / 'shims', self.tmp / 'starts'
        shims.mkdir()
        for name in ('python3', 'python'):
            (shims / name).write_text('#!/bin/sh\necho "%s ${GATE_LOCK_HELD:+nested}" >> "$SHIM_LOG"\n'
                                      'exec "%s" "$@"\n' % (name, Path(sys.executable).as_posix()),
                                      encoding='utf-8', newline='\n')
        self.write_build('true\n')
        code, out = gate(self.project, self.build, SHIM_LOG=log.as_posix(),
                         PATH=str(shims) + os.pathsep + os.environ['PATH'])
        self.assertEqual(code, 0, out)
        starts = log.read_text(encoding='utf-8').split('\n')[:-1]
        self.assertEqual([line for line in starts if 'nested' in line], [], 'a nested run started a Python')
        self.assertLessEqual(len(starts), 2, starts)

    @windows_only
    def test_a_lock_path_outside_the_code_page_is_printed_not_a_traceback(self):
        # Output to a pipe is in the ANSI code page; a checkout under a name outside it ended
        # the waiting NOTE in a UnicodeEncodeError, and the gate failed instead of waiting.
        project = self.tmp / 'proje-\u015f\u011f'
        make_project(project)
        self.write_build('true\n')
        handle = open_handle(project / '.git' / 'check.lock', GENERIC_READ | GENERIC_WRITE, SHARE_READ,
                             inheritable=False)
        try:
            code, out = gate(project, self.build, GATE_LOCK_WAIT='1')
        finally:
            close_handle(handle)
        self.assertEqual(code, 75, out)
        self.assertIn('NOT RUN [lock]:', out)
        self.assertNotIn('Traceback', out)

    @windows_only
    def test_two_runs_sharing_a_build_directory_run_one_at_a_time(self):
        self.write_build('mkdir "$SIDE/build" && sleep 2 && rmdir "$SIDE/build"\n')
        pair = [start(self.project, self.build, SIDE=self.side.as_posix()) for _ in range(2)]
        results = [finish(proc) for proc in pair]
        outputs = '\n'.join(out for _, out in results)
        self.assertEqual([code for code, _ in results], [0, 0], outputs)
        self.assertIn('NOTE [lock]', outputs)

    @windows_only
    def test_a_nested_run_inherits_the_lock_and_does_not_wait(self):
        # The lock path crosses native Python and back into sh: in a different form
        # (/d/... against D:/...) the nested run would not know its own lock and would wait.
        self.write_build('[ -n "$INNER" ] && exit 0\n'
                         'INNER=1 GATE_LOCK_WAIT=2 sh scripts/check.sh > "$SIDE/inner" 2>&1\n')
        code, out = gate(self.project, self.build, SIDE=self.side.as_posix())
        inner = (self.side / 'inner').read_text()
        self.assertEqual(code, 0, out + inner)
        self.assertIn('CHECK: PASS', inner)
        self.assertNotIn('NOTE [lock]', inner)

    @windows_only
    def test_a_gate_in_a_linked_worktree_locks_its_own_git_dir(self):
        # Git for Windows prints a linked worktree's git path as C:/...; read as relative,
        # it was appended to the working directory and the lock could not be opened.
        git = ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', '-c', 'core.hooksPath=/dev/null']
        subprocess.run(git + ['add', '-A'], cwd=self.project, check=True)
        subprocess.run(git + ['commit', '-q', '-m', 'fixture'], cwd=self.project, check=True)
        linked = self.tmp / 'linked'
        subprocess.run(['git', 'worktree', 'add', '-q', str(linked)], cwd=self.project, check=True,
                       capture_output=True)
        self.write_build('true\n')
        code, out = gate(linked, self.build)
        self.assertEqual(code, 0, out)
        self.assertTrue((self.project / '.git/worktrees/linked/check.lock').is_file())

    @windows_only
    def test_a_handle_on_another_file_is_not_the_lock(self):
        # The lock held, and an inherited handle on another file under the number GATE_LOCK_FD
        # names: without the identity check the run skipped the lock another gate held.
        self.write_build('false\n')
        held = open_handle(self.lock, GENERIC_READ | GENERIC_WRITE, SHARE_READ, inheritable=False)
        other = open_handle(self.tmp / 'another-file', GENERIC_READ | GENERIC_WRITE, SHARE_READ | SHARE_WRITE)
        try:
            code, out = gate(self.project, self.build, GATE_LOCK_HELD=self.lock_form(),
                             GATE_LOCK_FD=str(other), GATE_LOCK_WAIT='2')
        finally:
            close_handle(other)
            close_handle(held)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL [env]: GATE_LOCK_HELD names this checkout's lock, but this run did not inherit", out)

    @windows_only
    def test_a_read_only_handle_on_the_lock_file_is_not_the_lock(self):
        # Opened independently while another holder has the lock: right file, lock held, but
        # it cannot write, so it is not the holder's handle.
        self.write_build('false\n')
        held = open_handle(self.lock, GENERIC_READ | GENERIC_WRITE, SHARE_READ, inheritable=False)
        reader = open_handle(self.lock, GENERIC_READ, SHARE_READ | SHARE_WRITE)
        try:
            code, out = gate(self.project, self.build, GATE_LOCK_HELD=self.lock_form(),
                             GATE_LOCK_FD=str(reader), GATE_LOCK_WAIT='2')
        finally:
            close_handle(reader)
            close_handle(held)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL [env]: GATE_LOCK_HELD names this checkout's lock, but this run did not inherit", out)

    @windows_only
    def test_a_shared_write_handle_with_no_holder_is_not_the_lock(self):
        # A write handle that shares writing is open on the right file, but nothing holds the
        # lock: a fresh open for writing succeeds, so the claim is refused.
        self.write_build('false\n')
        plain = open_handle(self.lock, GENERIC_READ | GENERIC_WRITE, SHARE_READ | SHARE_WRITE)
        try:
            code, out = gate(self.project, self.build, GATE_LOCK_HELD=self.lock_form(),
                             GATE_LOCK_FD=str(plain), GATE_LOCK_WAIT='2')
        finally:
            close_handle(plain)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL [env]: GATE_LOCK_HELD names this checkout's lock, but this run did not inherit", out)

    @windows_only
    def test_variables_copied_out_of_a_killed_gate_are_refused(self):
        # The lock variables of a killed gate, copied into a process that did not inherit the
        # handle, are refused.
        self.write_build('echo "$GATE_LOCK_FD" > "$SIDE/fd"\n'
                         'echo "$GATE_LOCK_HELD" > "$SIDE/held.tmp"\nmv "$SIDE/held.tmp" "$SIDE/held"\n'
                         'sleep 30\n')
        proc = start(self.project, self.build, GATE_TEST_LOCK=self.lock.as_posix(), SIDE=self.side.as_posix())
        self.addCleanup(released, self.lock)  # runs before the folder is removed
        deadline = time.monotonic() + 60
        while not (self.side / 'held').exists():
            self.assertIsNone(proc.poll(), 'the gate to be killed ended before its build started')
            self.assertLess(time.monotonic(), deadline, 'the gate to be killed never started its build')
            time.sleep(0.1)
        kill_tree(proc)
        proc.communicate()
        self.write_build('false\n')
        code, out = gate(self.project, self.build,
                         GATE_LOCK_HELD=(self.side / 'held').read_text().strip(),
                         GATE_LOCK_FD=(self.side / 'fd').read_text().strip())
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL [env]: GATE_LOCK_HELD names this checkout's lock, but this run did not inherit", out)
        self.assertNotIn('CHECK: PASS', out)

    @windows_only
    def test_a_killed_holder_leaves_the_lock_with_the_build(self):
        # The process that took the lock is killed while the build runs: the build still holds
        # the handle, so neither waiter builds beside it. A lock owned by one process (a
        # byte-range lock) let the waiters in at once, and they failed on "File exists".
        self.write_build('mkdir "$SIDE/build" || exit 1\nsleep "${HOLD:-1}"\nrmdir "$SIDE/build"\n')
        proc = start(self.project, self.build, SIDE=self.side.as_posix(), HOLD='6')
        deadline = time.monotonic() + 60
        while not (self.side / 'build').is_dir():
            self.assertIsNone(proc.poll(), 'the gate ended before its build started')
            self.assertLess(time.monotonic(), deadline, 'the gate never started its build')
            time.sleep(0.1)
        members = descendants(proc)
        try:
            # The holder is the python whose direct child is the gate's sh, at whatever depth:
            # a launcher (the WindowsApps alias, a venv redirector) can run between proc and it.
            holders = [handle for pid, _, name, handle in members if name.lower().startswith('python')
                       and any(parent == pid and child.lower() == 'sh.exe' for _, parent, child, _ in members)]
            self.assertEqual(len(holders), 1, members)
            terminate(holders[0])
        finally:
            for *_, handle in members:
                close_handle(handle)
        waiters = [start(self.project, self.build, SIDE=self.side.as_posix()) for _ in range(2)]
        results = [finish(waiter, 120) for waiter in waiters]
        kill_tree(proc)
        proc.communicate()
        outputs = '\n'.join(out for _, out in results)
        self.assertEqual([code for code, _ in results], [0, 0], outputs)

    @windows_only
    def test_a_ctrl_c_just_before_the_launch_starts_no_gate(self):
        # r8: the holder read its Ctrl-C record, then launched the gate. A Ctrl-C between the
        # two reached no gate (it did not exist yet), and the gate it then started ran its build.
        self.write_build('echo built > "$SIDE/built"\n')
        code, out = gate(self.project, self.build, SIDE=self.side.as_posix(), GATE_LOCK_TEST_SIGINT_AT_LAUNCH='1')
        self.assertEqual(code, 130, out)
        self.assertIn('GATE_LOCK_TEST_SIGINT_AT_LAUNCH is set', out)
        self.assertFalse((self.side / 'built').exists(), 'the gate ran its build after the Ctrl-C:\n' + out)
        self.assertNotIn('CHECK:', out)
        code, out = gate(self.project, self.build, SIDE=self.side.as_posix())
        self.assertEqual(code, 0, out)

    @windows_only
    def test_a_gate_killed_by_a_signal_never_exits_zero(self):
        # Git for Windows reports a child that died of signal N to native Python as N << 8;
        # passed on as the exit status, sh read its low byte: 0, a pass.
        self.write_build('kill -9 $PPID\nsleep 5\n')
        code, out = gate(self.project, self.build)
        # The build's gate is gone, so the walk in finish()'s kill_tree may not reach it: only
        # the job stops it, and a python3 alias that starts the holder outside the job leaves it
        # to run out its sleep. It holds the lock: removing the fixture under it failed the
        # clean-up (Codex review). Wait until it lets the lock go.
        deadline = time.monotonic() + 30
        while True:
            try:
                close_handle(open_handle(self.lock, GENERIC_READ | GENERIC_WRITE, SHARE_READ))
                break
            except OSError:
                self.assertLess(time.monotonic(), deadline, 'the killed gate\'s build never ended')
                time.sleep(0.2)
        self.assertIsNotNone(code, out)
        self.assertNotEqual(code, 0, out)
        self.assertNotIn('CHECK: PASS', out)

    @windows_only
    def test_a_directory_at_the_lock_path_fails_by_name(self):
        self.lock.mkdir()
        self.write_build('true\n')
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [lock]: cannot open', out)
        self.assertNotIn('Traceback', out)

    @windows_only
    def test_a_reparse_point_at_the_lock_path_is_refused(self):
        # A symlink needs a privilege most accounts lack, and this case used to print NOT RUN
        # and pass, so deleting the guard left the host green. Any user may set a reparse
        # point with a non-Microsoft tag on a file of their own: the guard sees the same bit.
        set_reparse_point(self.lock)
        self.addCleanup(lambda: self.lock.exists() and os.remove(self.lock))
        self.assertTrue(os.lstat(self.lock).st_file_attributes & 0x400)
        self.write_build('true\n')
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [lock]: cannot open', out)
        self.assertIn('reparse point', out)

    def probe(self, mode, handle):
        """Run the gate's own nested-run proof (the Python check.sh hands GATE_LOCK_FD to) with
        `mode` faked: 'noid' makes the volume give no FILE_ID_INFO; 'none' fakes nothing."""
        text = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
        source = re.search(r"lock_probe=0\n  python3 -I -c '\n(.*?)\n' \"\$\{GATE_LOCK_FD:-\}\"", text, re.S)
        self.assertIsNotNone(source, 'the nested-run proof was not found in check.sh')
        program = self.tmp / 'probe.py'
        program.write_text(source[1], encoding='utf-8')
        runner = self.tmp / 'runner.py'
        runner.write_text(PROBE_RUNNER, encoding='utf-8')
        return subprocess.run([sys.executable, str(runner), mode, str(program), str(handle), self.lock_form()],
                              capture_output=True, text=True, close_fds=False)

    def lock_case(self, mode):
        """Run one mode of tests/fixtures/windows_lockcase.py against a copy of the gate in a
        throwaway repository; the copy stops, fails or kills itself right after it holds the lock
        when the case asks it to, and otherwise passes there."""
        case = self.tmp / ('lock-' + mode)
        subprocess.run(['git', 'init', '-q', str(case)], check=True)
        (case / 'scripts').mkdir()
        text = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
        anchor = '\nwork=$(mktemp -d)'
        self.assertIn(anchor, text)
        inserted = (
            '\n[ -z "${LOCKCASE_NEST:-}" ] || { LOCKCASE_NEST= sh "$gate"; exit $?; }'
            '\n[ -z "${LOCKCASE_HOLD:-}" ] || { : > "$LOCKCASE_HOLD"; sleep 10; exit 0; }'
            '\n[ -z "${LOCKCASE_KILL:-}" ] || { : > "$LOCKCASE_KILL"; kill -9 $$; }'
            '\n[ -z "${LOCKCASE_FAIL:-}" ] || { : > "$LOCKCASE_FAIL"; exit 3; }'
            '\n[ -z "${LOCKCASE_BUILD:-}" ] || { python3 -I -c "import os, sys, time; f = os.open(sys.argv[1] + chr(46)'
            ' + chr(116), os.O_WRONLY | os.O_CREAT); os.write(f, str(os.getpid()).encode()); os.close(f);'
            ' os.replace(sys.argv[1] + chr(46) + chr(116), sys.argv[1]); time.sleep(60)" "$LOCKCASE_BUILD"; exit 0; }'
            '\necho "lockcase: the copy of the gate got past the lock"; exit 0')
        copy = case / 'scripts/check.sh'
        copy.write_text(text.replace(anchor, inserted + anchor, 1), encoding='utf-8', newline='\n')
        lock = subprocess.run(['sh', '-c', 'cygpath -m "$(pwd -P)/.git/check.lock"'], cwd=case,
                              capture_output=True, text=True, check=True).stdout.strip()
        env = {k: v for k, v in os.environ.items() if not k.startswith(('GATE_', 'LOCKCASE_'))}
        result = subprocess.run([sys.executable, '-I', str(ROOT / 'tests/fixtures/windows_lockcase.py'), mode, lock,
                                 copy.as_posix()], env=env, capture_output=True, text=True, errors='replace',
                                timeout=240)
        return result.returncode, result.stdout + result.stderr

    @windows_only
    def test_a_fresh_open_that_failed_for_another_reason_is_not_the_lock(self):
        # Writable, on the lock file, nothing else holding it, the file then made read-only: a
        # fresh open for writing fails with access denied (5), not a sharing violation (32).
        code, out = self.lock_case('readonly')
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL [env]: GATE_LOCK_HELD names this checkout's lock, but this run did not inherit", out)

    @windows_only
    def test_the_holder_passes_a_failing_gates_exit_status_on(self):
        code, out = self.lock_case('failgate')
        self.assertEqual(code, 0, out)
        self.assertIn('lockcase: a gate that failed with 3 exited 3\n', out)

    @windows_only
    def test_the_holder_imports_no_stand_in_module_from_pythonpath(self):
        code, out = self.lock_case('shadow')
        self.assertEqual(code, 0, out)
        self.assertIn('lockcase: stand-ins imported: none; the gate exited 0\n', out)

    @windows_only
    def test_ctrl_c_stops_the_gate_and_its_build_and_the_next_gate_takes_the_lock(self):
        # The case gives the gate a hidden console of its own, with that console as sh's input,
        # as a terminal window does, and sends it CTRL_C_EVENT; the holder must outlive it.
        code, out = self.lock_case('interrupt')
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r'(?m)^lockcase: the interrupted gate exited [1-9][0-9]*; its holder exited 130; '
                              r'its build stopped; the next gate exited 0$')

    @windows_only
    def test_a_ctrl_c_while_the_holder_waits_for_the_lock_starts_no_gate(self):
        code, out = self.lock_case('earlyint')
        self.assertEqual(code, 0, out)
        self.assertIn('lockcase: a Ctrl-C before the gate started: its holder exited 130 while the lock was held; '
                      'the gate never ran\n', out)

    @windows_only
    def test_a_handle_whose_64_bit_identity_collides_is_not_the_lock(self):
        # The proof compared os.stat's (st_dev, st_ino). Before Python 3.12 that held 64 bits of
        # the file id, which ReFS does not keep unique: a writable handle on another file whose
        # truncated id matched passed while the real lock was held. The whole FILE_ID_INFO is
        # compared now: the 'wide' case hands the proof another file whose FILE_ID_INFO equals the
        # lock's but for its last byte (same volume, same first 64 id bits).
        code, out = self.lock_case('wide')
        self.assertEqual(code, 0, out)
        self.assertIn('lockcase: proof exit 1\n', out)
        held = open_handle(self.lock, GENERIC_READ | GENERIC_WRITE, SHARE_READ)
        try:
            control = self.probe('none', held)
        finally:
            close_handle(held)
        self.assertEqual(control.returncode, 0, control.stdout + control.stderr)

    @windows_only
    def test_a_volume_without_a_stable_file_id_fails_closed(self):
        # The holder's own handle, but no FILE_ID_INFO to prove it with: FAIL [lock], not a pass.
        held = open_handle(self.lock, GENERIC_READ | GENERIC_WRITE, SHARE_READ)
        try:
            result = self.probe('noid', held)
        finally:
            close_handle(held)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn('FAIL [lock]:', result.stdout)
        self.assertIn('file id', result.stdout)


class GateRuleTests(unittest.TestCase):
    """Gate rules that do not depend on the lock: these run on every host, native Windows included
    (tests/test_check_gate.py, the POSIX gate suite, does not run there)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / 'project'
        make_project(self.project)
        self.build = self.tmp / 'build.sh'
        self.build.write_text('true\n', encoding='utf-8', newline='\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'init')

    def git(self, *args):
        return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                               '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', *args],
                              cwd=self.project, check=True, capture_output=True, text=True).stdout

    def write(self, name, text):
        (self.project / name).parent.mkdir(parents=True, exist_ok=True)
        (self.project / name).write_text(text, encoding='utf-8', newline='\n')

    def run_gate(self, *args, **extra):
        result = subprocess.run(['sh', 'scripts/check.sh', *args], cwd=self.project,
                                env=environment(self.build, **extra), capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=120)
        return result.returncode, result.stdout + result.stderr

    def test_a_file_named_dash_is_scanned_inside_and_outside_git(self):
        # grep takes a bare "-" as stdin, so a marker in a file named "-" passed (b7 review, round 2).
        self.write('-', '{{BUILD_TEST_COMMAND}}\n')
        self.git('add', '--', '-')
        code, out = self.run_gate()
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [setup]', out)
        away = self.tmp / 'git-away'
        (self.project / '.git').rename(away)
        try:
            code, out = self.run_gate()
        finally:
            away.rename(self.project / '.git')
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [setup]', out)

    def test_a_deletion_only_commit_is_scanned_and_only_an_empty_tree_is_refused(self):
        # The empty-list FAIL counts files in the tree, not in the commit (KARARLAR D03 inv2#159).
        self.write('docs/old.md', 'old\n')
        self.git('add', 'docs/old.md')
        self.git('commit', '-q', '-m', 'old')
        self.git('rm', '-q', 'docs/old.md')
        code, out = self.run_gate('--for-commit')
        self.assertEqual(code, 0, out)
        self.assertNotIn('EMPTY', out)
        bare = self.tmp / 'bare'
        bare.mkdir()
        subprocess.run(['git', 'init', '-q', str(bare)], check=True)
        shutil.copytree(self.project / 'scripts', bare / 'scripts')
        (bare / '.gitignore').write_text('*\n', encoding='utf-8')
        result = subprocess.run(['sh', 'scripts/check.sh'], cwd=bare, env=environment(self.build),
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('FAIL [scan]: the file list is EMPTY', result.stdout)

    def test_a_tagged_state_line_deleted_with_nothing_added_elsewhere_is_noted(self):
        # KARARLAR D05 inv1#76, lead decision 7: told at commit time, never failed. A colour the
        # user's config forces on every diff must not hide the deleted line (b7 review, round 1).
        self.git('config', 'color.ui', 'always')
        self.git('config', 'color.diff', 'always')
        self.write('docs/STATE.md', '# STATE\n\n## Active work\n- [LESSON] keep the lock inherited\n')
        self.git('commit', '-q', '-am', 'lesson')
        self.write('docs/STATE.md', '# STATE\n\n## Active work\n')
        self.git('add', 'docs/STATE.md')
        code, out = self.run_gate('--for-commit')
        self.assertEqual(code, 0, out)
        self.assertIn('NOTE [state]: this commit deletes a tagged line from docs/STATE.md', out)
        self.assertIn('[LESSON] keep the lock inherited', out)
        self.write('docs/GOTCHAS.md', '# GOTCHAS\n\nKeep the lock inherited.\n')
        self.git('add', 'docs/GOTCHAS.md')
        code, out = self.run_gate('--for-commit')
        self.assertEqual(code, 0, out)
        self.assertNotIn('NOTE [state]: this commit deletes', out)

    def test_the_strong_review_reminder_counts_closed_tasks_as_well_as_days(self):
        # KARARLAR B11 inv1#119 + inv2#152: N days or M tasks, whichever comes first.
        source = (self.project / 'scripts/check.sh').read_text(encoding='utf-8')
        tasks = int(re.search(r'^STRONG_REVIEW_TASKS=(\d+)$', source, re.M).group(1))
        self.write('docs/STRONG_REVIEW.md', '# STRONG_REVIEW\n')
        self.write('docs/reviews/strong-2026-01-01-model.md', 'report\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'strong review')
        for n in range(1, tasks):
            self.git('commit', '-q', '--allow-empty', '-m', 'task %d' % n, '-m', 'Done: T%d' % n)
        # A malformed trailer closes nothing for the state parser, so it is no closed task here.
        self.git('commit', '-q', '--allow-empty', '-m', 'bypassed hook', '-m', 'Done: two ids')
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        self.assertNotIn('NOTE [strong-review]', out)
        self.git('commit', '-q', '--allow-empty', '-m', 'task %d' % tasks, '-m', 'Done: T%d' % tasks)
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        self.assertIn('NOTE [strong-review]: the newest strong review report was added 0 days ago, and %d tasks'
                      % tasks, out)
        self.assertIn('whichever comes first', out)

    def test_a_module_folder_the_map_does_not_name_fails(self):
        # KARARLAR B10 inv1#239: prefer a check to a promise.
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        self.assertIn('NOTE [architecture]: module_roots is empty', out)
        gate_file = self.project / 'scripts/check.sh'
        source = gate_file.read_text(encoding='utf-8')
        self.assertIn('\nmodule_roots=""\n', source)
        gate_file.write_text(source.replace('\nmodule_roots=""\n', '\nmodule_roots="src"\n', 1),
                             encoding='utf-8', newline='\n')
        self.write('src/billing/a.py', 'a = 1\n')
        self.write('src/ledger/b.py', 'b = 1\n')
        self.write('docs/ARCHITECTURE.md', '# Architecture\n\n## Module map\n\n- billing: money in\n\n'
                                           '## Boundary enforcement\n\nledger is not enforced.\n')
        code, out = self.run_gate()
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL [architecture]: src/ledger is a module folder that the '## Module map'", out)
        self.assertNotIn('src/billing is a module folder', out)
        self.write('docs/ARCHITECTURE.md', '# Architecture\n\n## Module map\n\n- billing: money in\n'
                                           '- ledger: the books\n')
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        # Outside a Git repository the find fallback names the same files (b7 review, round 1).
        away = self.tmp / 'git-away'
        (self.project / '.git').rename(away)
        try:
            code, out = self.run_gate()
        finally:
            away.rename(self.project / '.git')
        self.assertNotIn('FAIL [architecture]', out)
        gate_file.write_text(source.replace('\nmodule_roots=""\n', '\nmodule_roots="lib"\n', 1),
                             encoding='utf-8', newline='\n')
        code, out = self.run_gate()
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [architecture]: the module root lib in scripts/check.sh holds no file', out)

    def module_root(self, root):
        gate_file = self.project / 'scripts/check.sh'
        source = gate_file.read_text(encoding='utf-8')
        gate_file.write_text(source.replace('\nmodule_roots=""\n', '\nmodule_roots="%s"\n' % root, 1),
                             encoding='utf-8', newline='\n')

    def test_dot_module_root_finds_top_level_folders(self):
        self.module_root('.')
        self.write('docs/ARCHITECTURE.md', '## Module map\n- docs: documents\n- scripts: checks\n')
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        self.assertNotIn('the module root . in scripts/check.sh holds no file', out)
        self.write('extra/file.txt', 'module\n')
        code, out = self.run_gate()
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [architecture]: extra is a module folder', out)

    def test_module_names_match_whole_entries_including_hyphens_and_dots(self):
        self.module_root('src')
        for module in ('api', 'api-gateway', 'core', 'core.utils', '.claude', '.claude-plugin'):
            self.write('src/%s/file.txt' % module, 'module\n')
        self.write('docs/ARCHITECTURE.md', '## Module map\n- `api-gateway`: gateway\n'
                                          '| core.utils | utilities |\n- .claude-plugin: plugin\n')
        code, out = self.run_gate()
        self.assertEqual(code, 1, out)
        for module in ('api', 'core', '.claude'):
            self.assertIn('FAIL [architecture]: src/%s is a module folder' % module, out)
        self.write('docs/ARCHITECTURE.md', (self.project / 'docs/ARCHITECTURE.md').read_text()
                   + '- api: API\n| `core` | engine |\n- `.claude`: settings\n')
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)

    def test_a_module_may_be_named_by_its_path_from_the_top(self):
        # A map naming `src/app/` or game/sim, as the template's table invites, failed every
        # module (#88, #141). A path under another root names nothing there.
        self.module_root('game engine')
        for module in ('game/sim', 'game/ui', 'engine/sim'):
            self.write('%s/file.txt' % module, 'module\n')
        self.write('docs/ARCHITECTURE.md', '## Module map\n| `game/sim/` | rules |\n- game/ui: menus\n')
        code, out = self.run_gate()
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [architecture]: engine/sim is a module folder', out)
        for module in ('game/sim', 'game/ui'):
            self.assertNotIn('%s is a module folder' % module, out)
        self.write('docs/ARCHITECTURE.md', '## Module map\n| `game/sim/` | rules |\n- game/ui: menus\n'
                                          '| engine/sim | rendering |\n')
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)

    def test_module_names_come_from_table_rows_and_list_entries_only(self):
        # The shipped template's paragraph and comment name design, work and tests: read as
        # names, those module folders passed unmapped (#274). Its multi-line comment holds a
        # line with pipes ("Module | Responsibility | ... the design"), so design proves the
        # comment is skipped. Rows without outer pipes and rows or entries with an inline or
        # trailing comment still name their module.
        rows = ('| `economy` | prices |', 'trade | goods', '- market: stalls', '1. port: ships',
                '| bank | money | <!-- note -->', '| mint <!-- coined --> | coins |', '- shop: sales <!-- x -->')
        named = ('economy', 'trade', 'market', 'port', 'bank', 'mint', 'shop')
        self.module_root('src')
        for module in named + ('design', 'work', 'tests'):
            self.write('src/%s/file.txt' % module, 'module\n')
        text = (ROOT / 'core/docs/ARCHITECTURE.md').read_text(encoding='utf-8')
        self.assertIn('{{MODULE_MAP}}', text)
        self.assertRegex(text, r'<!--[^\n]*\|[^\n]*design[^\n]*\n')
        self.write('docs/ARCHITECTURE.md', re.sub(r'\{\{[A-Z0-9_]+\}\}', 'fixture',
                                                  text.replace('{{MODULE_MAP}}', '\n'.join(rows))))
        code, out = self.run_gate()
        self.assertEqual(code, 1, out)
        for module in ('design', 'work', 'tests'):
            self.assertIn('FAIL [architecture]: src/%s is a module folder' % module, out)
        for module in named:
            self.assertNotIn('src/%s is a module folder' % module, out)

    def test_historical_audit_ids_are_notes_but_live_state_and_reviews_still_fail(self):
        self.write('docs/audits/2026-01.md', 'K4: audit finding\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'old audit')
        self.git('commit', '-q', '--allow-empty', '-m', 'close task', '-m', 'Done: K4')
        code, out = self.run_gate()
        self.assertEqual(code, 0, out)
        self.assertIn('NOTE [state]: docs/audits/2026-01.md:1 names K4', out)
        for path in ('docs/STATE.md', 'docs/BACKLOG.md', 'docs/STRONG_REVIEW.md',
                     'docs/reviews/strong-2026-01-01-model.md'):
            with self.subTest(path=path):
                self.write(path, '## Active work\nK4: reopened\n')
                code, out = self.run_gate()
                self.assertEqual(code, 1, out)
                self.assertIn('FAIL [state]: %s:2 names K4' % path, out)
                self.write(path, '## Active work\n')

    def test_shellcheck_selects_shell_hooks_and_sh_files_only(self):
        # A selection double records inputs; this does not claim real ShellCheck validation.
        shim = self.tmp / 'bin'
        shim.mkdir()
        log = self.tmp / 'shellcheck-inputs'
        (shim / 'shellcheck').write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$SC_INPUTS"\n',
                                        encoding='utf-8', newline='\n')
        (shim / 'shellcheck').chmod(0o755)
        for name, body in (('pre-commit', '#!/bin/sh\ntrue\n'),
                           ('post-commit.project', '#!/usr/bin/env sh\ntrue\n'),
                           ('prepare-commit-msg.project', '#!/usr/bin/env python3\npass\n'),
                           ('node.project', '#!/usr/bin/env node\nconsole.log("hook");\n'),
                           ('README', 'Hook documentation\n')):
            self.write('.githooks/' + name, body)
        shell_hooks = ['.githooks/pre-commit', '.githooks/post-commit.project']
        for shell in ('bash', 'dash', 'ksh'):
            for launcher in ('/bin/', '/usr/bin/env '):
                name = '.githooks/%s-%s.project' % (shell, 'env' if 'env' in launcher else 'direct')
                self.write(name, '#!%s%s\necho $unquoted\n' % (launcher, shell))
                shell_hooks.append(name)
        self.write('scripts/no-shebang.sh', 'true\n')
        code, out = self.run_gate(PATH=str(shim) + os.pathsep + os.environ['PATH'],
                                  SC_INPUTS=log.as_posix())
        self.assertEqual(code, 0, out)
        inputs = log.read_text().splitlines()
        for name in (*shell_hooks, 'scripts/no-shebang.sh'):
            with self.subTest(hook=name):
                self.assertIn(name, inputs)
        for name in ('.githooks/prepare-commit-msg.project', '.githooks/node.project', '.githooks/README'):
            self.assertNotIn(name, inputs)

    def test_shellcheck_diagnostic_from_an_extensionless_bash_hook_fails_the_gate(self):
        # A diagnostic double proves gate wiring, not the inaccessible host's real lint.
        shim = self.tmp / 'bin'
        shim.mkdir()
        (shim / 'shellcheck').write_text(
            '#!/bin/sh\nfor f do\n  case "$f" in .githooks/*)\n'
            '    printf "%s:2:1: warning: Quote expansion [SC2086]\\n" "$f"; exit 1 ;;\n'
            '  esac\ndone\n', encoding='utf-8', newline='\n')
        (shim / 'shellcheck').chmod(0o755)
        self.write('.githooks/pre-commit.project', '#!/bin/bash\necho $unquoted\n')
        code, out = self.run_gate(PATH=str(shim) + os.pathsep + os.environ['PATH'])
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [shellcheck]', out)
        self.assertIn('.githooks/pre-commit.project:2:1:', out)


if __name__ == '__main__':
    unittest.main()
