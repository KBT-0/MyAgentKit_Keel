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


def duplicate(handle):
    """A second handle on the same open file, so closing its fd leaves handle open."""
    out = wintypes.HANDLE()
    me = KERNEL32.GetCurrentProcess()
    if not KERNEL32.DuplicateHandle(me, handle, me, ctypes.byref(out), 0, False, 2):
        raise ctypes.WinError(ctypes.get_last_error())
    return out.value


def write_handle(handle, text):
    """Write text as the whole file through handle, as the gate's holder writes its token."""
    import msvcrt
    fd = msvcrt.open_osfhandle(duplicate(handle), os.O_RDWR)
    try:
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, 0)
        os.write(fd, text.encode())
    finally:
        os.close(fd)


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


def pid_descendants(pid):
    """(pid, image name) of each process under pid, from snapshots; tests/test_stop_hook.py's
    walk, which needs no handle on the root."""
    found = children(pid)
    for child, _ in found:
        found.extend(children(child))
    return found


def lock_holder(pid):
    """(holder, gate): the first python under pid whose direct child is an sh, and that sh.
    A launcher (the WindowsApps alias, a venv redirector) can run between pid and the holder."""
    return next((parent, child) for parent, image in pid_descendants(pid) if image.lower().startswith('python')
                for child, name in children(parent) if name == 'sh.exe')


def kill_process(pid):
    """Terminate a fixture process directly; taskkill needs privileges absent in sandboxes."""
    KERNEL32.OpenProcess.restype = ctypes.c_void_p
    KERNEL32.TerminateProcess.argtypes = (ctypes.c_void_p, ctypes.c_uint)
    KERNEL32.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD))
    handle = KERNEL32.OpenProcess(0x1001, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:  # The fixture already exited.
            return
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not KERNEL32.TerminateProcess(handle, 1):
            error, status = ctypes.get_last_error(), wintypes.DWORD()
            if not KERNEL32.GetExitCodeProcess(handle, ctypes.byref(status)) or status.value == 259:
                raise ctypes.WinError(error)
    finally:
        close_handle(handle)


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
if mode == 'collide':
    class Same:
        def __init__(self, result):
            self.result = result
        def __getattr__(self, name):
            return 1 if name in ('st_dev', 'st_ino') else getattr(self.result, name)
    real_stat, real_fstat = os.stat, os.fstat
    os.stat = lambda *a, **k: Same(real_stat(*a, **k))
    os.fstat = lambda *a, **k: Same(real_fstat(*a, **k))
elif mode == 'noid':
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
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    # Git for Windows' default core.autocrlf=true would check a linked worktree's gate out as CRLF.
    subprocess.run(['git', 'config', 'core.autocrlf', 'false'], cwd=path, check=True)


def environment(build, **extra):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('GATE_', 'BOUNDARY_')) and k != 'CDPATH'}
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
    @windows_only
    def test_kill_tree_spares_a_pid_replaced_between_snapshot_and_open(self):
        from unittest.mock import Mock, patch
        module = sys.modules[__name__]
        proc = Mock(pid=1, _handle=101, _kit_job=99)
        events, closed = [], []

        def query(handle, info, out, size, returned):
            self.assertEqual(handle, 102)
            out._obj.InheritedFromUniqueProcessId = 900
            return 0

        kernel32 = Mock()
        kernel32.TerminateJobObject.side_effect = lambda job, code: events.append('job')
        with patch.object(module, 'children', side_effect=lambda pid: [(2, 'python.exe')] if pid == 1 else []), \
                patch.object(module, 'KERNEL32', Mock(OpenProcess=Mock(return_value=102),
                                                   GetProcessId=Mock(return_value=1))), \
                patch.object(module, 'NTDLL', Mock(NtQueryInformationProcess=Mock(side_effect=query)), create=True), \
                patch.object(module, 'created', side_effect={101: 100, 102: 200}.get), \
                patch.object(module, 'terminate', events.append), patch.object(module, 'close_handle', closed.append), \
                patch('agent_process._win', return_value={'kernel32': kernel32}):
            kill_tree(proc)
        self.assertEqual(events, ['job'], 'a newer replacement with another parent must never be killed')
        self.assertEqual(closed, [102])

    @windows_only
    def test_terminate_requires_a_signalled_wait_even_after_a_successful_kill(self):
        from unittest.mock import Mock, patch
        for killed in (0, 1):
            for waited in (0x102, 0xffffffff):
                with self.subTest(killed=killed, waited=waited), \
                        patch.object(sys.modules[__name__], 'KERNEL32',
                                     Mock(TerminateProcess=Mock(return_value=killed),
                                          WaitForSingleObject=Mock(return_value=waited))), \
                        patch.object(ctypes, 'get_last_error', return_value=5), self.assertRaises(OSError):
                    terminate(101)
            with patch.object(sys.modules[__name__], 'KERNEL32',
                              Mock(TerminateProcess=Mock(return_value=killed),
                                   WaitForSingleObject=Mock(return_value=0))):
                terminate(101)  # already exited processes can refuse TerminateProcess

    @windows_only
    def test_kill_tree_stops_parents_first_and_spares_a_child_of_an_earlier_pid(self):
        # TerminateJobObject alone stopped the build (4, 5) before the lock holder (2), which
        # then cleared its token. 3 names 2 as its parent but is older than 2: its parent was
        # an earlier process with that pid. It is never killed; the job is stopped last.
        from unittest.mock import Mock, patch
        events = []
        proc = Mock(pid=1, _handle=1, _kit_job=99)
        tree = {1: [(2, 'python.exe')], 2: [(4, 'sh.exe'), (3, 'unrelated.exe')], 4: [(5, 'sh.exe')]}
        born = {1: 100, 2: 110, 3: 50, 4: 120, 5: 130}
        kernel32 = Mock()
        kernel32.TerminateJobObject.side_effect = lambda job, code: events.append('job')
        module = sys.modules[__name__]
        with patch.object(module, 'children', lambda pid: tree.get(pid, [])), \
                patch.object(module, 'KERNEL32', Mock(OpenProcess=lambda access, inherit, pid: pid,
                                                   GetProcessId=lambda handle: handle)), \
                patch.object(module, 'parent_pid', side_effect={2: 1, 3: 2, 4: 2, 5: 4}.get), \
                patch.object(module, 'created', born.get), \
                patch.object(module, 'terminate', events.append), patch.object(module, 'close_handle'), \
                patch('agent_process._win', return_value={'kernel32': kernel32}):
            kill_tree(proc)
        self.assertEqual(events, [2, 4, 5, 'job'])

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
    def test_a_linked_self_test_marker_never_changes_owner_data(self):
        self.write_build('false\n')  # End at the baseline, without running the full self-test.
        marker, owner = self.project / '.git/check-selftest', self.tmp / 'owner.txt'
        owner.write_bytes(b'owner data\n')
        for kind in ('hard link', 'symbolic link', 'reparse point'):
            with self.subTest(kind=kind):
                if kind == 'hard link':
                    os.link(owner, marker)
                elif kind == 'symbolic link':
                    os.symlink(owner, marker)
                else:
                    set_reparse_point(marker)
                try:
                    proc = subprocess.Popen(['sh', 'scripts/check.sh', '--self-test'], cwd=self.project,
                                            env=environment(self.build), text=True, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT)
                    code, out = finish(proc)
                    self.assertEqual(owner.read_bytes(), b'owner data\n', out)
                    self.assertEqual(code, 1, out)
                    self.assertIn('FAIL [self-test]:', out)
                    self.assertEqual(list(marker.parent.glob('check-selftest-*')), [], 'temporary left')
                finally:
                    if os.path.lexists(marker):
                        os.remove(marker)


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
        # The lock is released when the gate ends, and the holder's token is cleared.
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
        self.assertIn('NOTE [lock]: another gate run, or a process it started, has held', out)
        self.assertIn('To see the holder: Resource Monitor', out)
        self.assertIn('NOT RUN [lock]:', out)
        self.assertIn('GATE_LOCK_WAIT=2 ran out', out)

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
        # The lock held with the holder's token, the token copied, and an inherited handle on
        # another file under the number GATE_LOCK_FD names: without the identity check the
        # seams turned a red build green.
        self.write_build('false\n')
        held = open_handle(self.lock, GENERIC_READ | GENERIC_WRITE, SHARE_READ, inheritable=False)
        other = open_handle(self.tmp / 'another-file', GENERIC_READ | GENERIC_WRITE, SHARE_READ | SHARE_WRITE)
        try:
            write_handle(held, 'token')
            code, out = gate(self.project, self.build, GATE_LOCK_HELD=self.lock_form(),
                             GATE_LOCK_FD=str(other), GATE_SELFTEST_NESTED='token',
                             GATE_BUILD_CMD_OVERRIDE='true', GATE_LOCK_WAIT='2')
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
            write_handle(held, 'token')
            code, out = gate(self.project, self.build, GATE_LOCK_HELD=self.lock_form(),
                             GATE_LOCK_FD=str(reader), GATE_SELFTEST_NESTED='token',
                             GATE_BUILD_CMD_OVERRIDE='true', GATE_LOCK_WAIT='2')
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
            write_handle(plain, 'token')
            code, out = gate(self.project, self.build, GATE_LOCK_HELD=self.lock_form(),
                             GATE_LOCK_FD=str(plain), GATE_SELFTEST_NESTED='token',
                             GATE_BUILD_CMD_OVERRIDE='true', GATE_LOCK_WAIT='2')
        finally:
            close_handle(plain)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL [env]: GATE_LOCK_HELD names this checkout's lock, but this run did not inherit", out)

    @windows_only
    def test_a_marker_that_is_not_the_holders_token_is_refused(self):
        # A process the build starts inherits the handle, so the handle proof accepts it; only
        # the marker check keeps a stray GATE_SELFTEST_NESTED from turning on the seams.
        self.write_build('GATE_SELFTEST_NESTED=1 GATE_BUILD_CMD_OVERRIDE=true sh scripts/check.sh\n')
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [env]: GATE_BUILD_CMD_OVERRIDE is set', out)

    @windows_only
    def test_variables_copied_out_of_a_killed_gate_are_refused(self):
        # The holder's token stays in the lock file when the gate is killed. Copied with the
        # handle number into a process that did not inherit the handle, it is refused.
        self.write_build('cat "$GATE_TEST_LOCK" > "$SIDE/token"\necho "$GATE_LOCK_FD" > "$SIDE/fd"\n'
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
        token = (self.side / 'token').read_text()
        self.assertTrue(token, 'the holder wrote no token into the lock file')
        self.assertEqual(self.lock.read_text(), token, "the killed gate's token was not left in the lock file")
        self.write_build('false\n')
        code, out = gate(self.project, self.build, GATE_SELFTEST_NESTED=token,
                         GATE_LOCK_HELD=(self.side / 'held').read_text().strip(),
                         GATE_LOCK_FD=(self.side / 'fd').read_text().strip(),
                         GATE_BUILD_CMD_OVERRIDE='true')
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [env]', out)
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
        `mode` faked: 'collide' makes os.stat report one identity for every file, as a 64-bit
        file id that is not unique (ReFS before Python 3.12) does; 'noid' makes the volume give
        no FILE_ID_INFO; 'none' fakes nothing."""
        text = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
        source = re.search(r"lock_probe=0\n  python3 -I -c '\n(.*?)\n' \"\$\{GATE_LOCK_FD:-\}\"", text, re.S)
        self.assertIsNotNone(source, 'the nested-run proof was not found in check.sh')
        program = self.tmp / 'probe.py'
        program.write_text(source[1], encoding='utf-8')
        runner = self.tmp / 'runner.py'
        runner.write_text(PROBE_RUNNER, encoding='utf-8')
        return subprocess.run([sys.executable, str(runner), mode, str(program), str(handle), self.lock_form()],
                              capture_output=True, text=True, close_fds=False)

    @windows_only
    def test_a_handle_whose_64_bit_identity_collides_is_not_the_lock(self):
        # The proof compared os.stat's (st_dev, st_ino). Before Python 3.12 that held 64 bits of
        # the file id, which ReFS does not keep unique: a writable handle on another file whose
        # truncated id matched passed while the real lock was held. FILE_ID_INFO is compared now.
        held = open_handle(self.lock, GENERIC_READ | GENERIC_WRITE, SHARE_READ)
        other = open_handle(self.tmp / 'another-file', GENERIC_READ | GENERIC_WRITE, SHARE_READ | SHARE_WRITE)
        try:
            control = self.probe('none', held)
            collided = self.probe('collide', other)
        finally:
            close_handle(other)
            close_handle(held)
        self.assertEqual(control.returncode, 0, control.stdout + control.stderr)
        self.assertEqual(collided.returncode, 1, collided.stdout + collided.stderr)

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


WINDOWS_PROGRAM_VARIABLES = ('SYSTEMROOT', 'WINDIR', 'LOCALAPPDATA', 'APPDATA', 'USERPROFILE', 'PATHEXT', 'COMSPEC')


class WindowsBoundaryProbeTests(unittest.TestCase):
    """The existing-file boundary example's probe on native Windows (issue #60): under `env -i` the
    Python install manager's python3 alias, missing LOCALAPPDATA, downloaded and installed a Python.
    Offline: python3 and python here are stubs, and the stub python runs this test's interpreter."""

    def run_probe(self, **extra):
        template = (ROOT / 'core/scripts/boundary_selftests.sh').read_text(encoding='utf-8')
        example = '\n'.join(line[4:] for line in template.splitlines() if line.startswith('# | '))
        # The fixture resolves its Python with check.sh's own lines, as the sourced example sees it.
        check = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
        start = check.index("if python3 -I -c '' </dev/null")
        resolve = check[start:check.index('\n', check.index('python3() { $kit_python "$@"; }'))]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            records, scratch, stubs = tmp / 'records', tmp / 'scratch', tmp / 'bin'
            for folder in (records, scratch, stubs):
                folder.mkdir()
            # A python3 that does not run, as a Store alias exits 9009: check.sh resolves `python`.
            # A run under the probe, recognised by the copy's HOME, is recorded, except the copied
            # gate's own resolution (`python3 -I -c ''`).
            (stubs / 'python3').write_text('#!/bin/sh\ncase "$HOME" in */tmp.*/home) [ "$#" = 3 ] && [ -z "$3" ] ||'
                                           ' : > "%s/python3-ran" ;; esac\nexit 9009\n' % records.as_posix(),
                                           newline='\n')
            # The probe's own Python records what it was given.
            (stubs / 'python').write_text('#!/bin/sh\ncase "$HOME" in */tmp.*/home) env > "%s/probe.env" ;; esac\n'
                                          'exec "%s" "$@"\n' % (records.as_posix(), Path(sys.executable).as_posix()),
                                          newline='\n')
            for name, body in extra.items():
                (stubs / name).write_text('#!/bin/sh\n' + body, newline='\n')
            root = tmp / 'project'
            (root / 'src/domain').mkdir(parents=True)
            (root / 'src/domain/existing.py').write_bytes(b'committed original\n')
            (root / 'scripts').mkdir()
            (root / 'scripts/check.sh').write_text(
                '#!/bin/sh\ncd "$(dirname "$0")/.."\n' + resolve + '\n'
                'if [ "${1:-}" = --self-test ]; then\n  st_fail=0\n' + example + '\n  exit "$st_fail"\nfi\n'
                "grep -q 'myapp.web' src/domain/existing.py || exit 0\n"
                "echo 'FAIL [boundary]: the domain layer imports the web layer:'\nexit 1\n",
                encoding='utf-8', newline='\n')
            for args in (('init', '-q'), ('config', 'core.autocrlf', 'false'), ('add', '.'),
                         ('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                          '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')):
                subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)
            # In lower case, still valid: the MSYS runtime adds its own SYSTEMROOT, WINDIR and
            # USERPROFILE to a child that lacks them, so only the caller's spelling proves probe_env.
            env = dict(os.environ, TMPDIR=str(scratch), PROBE_LEAK_CANARY='leaked',
                       PATH=str(stubs) + os.pathsep + os.environ['PATH'],
                       **{name: os.environ[name].lower() for name in WINDOWS_PROGRAM_VARIABLES})
            env.pop('PYTHONNOUSERSITE', None)
            result = subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=root, env=env,
                                    capture_output=True, encoding='utf-8', errors='replace', timeout=120)
            recorded = (records / 'probe.env').read_text(errors='replace') if (records / 'probe.env').exists() else None
            return result, recorded, (records / 'python3-ran').exists()

    @windows_only
    def test_the_probe_keeps_what_a_windows_program_needs_and_nothing_else(self):
        result, recorded, _ = self.run_probe()
        output = result.stdout + result.stderr
        self.assertIsNotNone(recorded, 'the probe never ran its Python:\n' + output)
        seen = dict(line.split('=', 1) for line in recorded.splitlines() if '=' in line)
        for name in WINDOWS_PROGRAM_VARIABLES:
            self.assertEqual(seen.get(name), os.environ[name].lower(), name + ' did not reach the probe:\n' + output)
        # Still isolated: the copy's own HOME and TMPDIR, no user site in the real APPDATA (what the
        # empty HOME is on POSIX), and nothing probe_env does not name.
        self.assertRegex(seen.get('HOME', ''), r'/tmp\.[^/]+/home$')
        self.assertRegex(seen.get('TMPDIR', ''), r'/tmp\.[^/]+/tmp$')
        self.assertEqual(seen.get('PYTHONNOUSERSITE'), '1', output)
        self.assertNotIn('PROBE_LEAK_CANARY', seen)
        # And the case runs to its end on native Windows.
        self.assertEqual(result.returncode, 0, output)
        self.assertIn('  ok   — domain/web boundary gate rejects a forbidden import in an existing file', output)

    @windows_only
    def test_the_probe_runs_the_python_check_sh_resolved_not_bare_python3(self):
        result, recorded, python3_ran = self.run_probe()
        output = result.stdout + result.stderr
        self.assertIsNotNone(recorded, 'the probe never ran the resolved Python:\n' + output)
        self.assertFalse(python3_ran, 'the probe ran python3, not the Python check.sh resolved:\n' + output)

    @windows_only
    def test_a_host_that_cannot_make_symlinks_is_not_run_by_name(self):
        # Without Developer Mode or the privilege, cp under winsymlinks:nativestrict fails on any
        # link in the checkout; its raw error said nothing about why. Stubs stand for that host.
        refused = "echo \"$(basename \"$0\"): cannot create symbolic link 'x': Operation not permitted\" >&2; exit 1\n"
        result, _, _ = self.run_probe(cp=refused, ln=refused)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn('  NOT RUN — existing-file probe: this host cannot make symbolic links; enable Developer Mode'
                      ' or the privilege, or run the self-test on a host that can.', output)
        self.assertNotIn('Operation not permitted', output)
        # A copy that failed for another reason keeps cp's own error and names no privilege.
        result, _, _ = self.run_probe(cp="echo 'cp: disk full' >&2; exit 1\n")
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn('cp: disk full', output)
        self.assertNotIn('cannot make symbolic links', output)


def probe_script(which):
    """The existing-file example's own Python: 'delete' (probe_delete) or 'audit' (probe_audit)."""
    template = (ROOT / 'core/scripts/boundary_selftests.sh').read_text(encoding='utf-8')
    example = '\n'.join(line[4:] for line in template.splitlines() if line.startswith('# | '))
    scripts = re.findall(r"-I -c '\n(.*?)\n'", example, re.S)
    return scripts[['delete', 'audit'].index(which)]


class WindowsProbeCopyTests(unittest.TestCase):
    """The existing-file probe's copy on native Windows: the audit and the delete never follow a
    junction or a symlink out of the copy, the delete removes git's read-only object files, and a
    file the copy shares with the checkout (a hard link) keeps its read-only attribute."""

    def setUp(self):
        if not WINDOWS:
            return
        self.tmp = Path(tempfile.mkdtemp(prefix='kit-probe-copy-'))
        # rmdir /s removes a junction as a link and never goes through it.
        self.addCleanup(subprocess.run, ['cmd', '/c', 'rmdir', '/s', '/q', str(self.tmp)], capture_output=True)
        self.copy = self.tmp / 'copy'
        self.outside = self.tmp / 'outside'
        (self.copy / 'checkout/.git/objects/ab').mkdir(parents=True)
        self.outside.mkdir()
        (self.outside / 'keep.txt').write_text('outside the copy\n')

    def delete(self, made=None):
        made = made or os.lstat(self.copy)
        return subprocess.run([sys.executable, '-I', '-c', probe_script('delete'), str(self.copy),
                               '%d %d' % (made.st_dev, made.st_ino)],
                              capture_output=True, encoding='utf-8', errors='replace', timeout=60)

    def audit(self):
        return subprocess.run([sys.executable, '-I', '-c', probe_script('audit'), str(self.copy / 'checkout')],
                              capture_output=True, encoding='utf-8', errors='replace', timeout=60)

    def read_only(self, path):
        path.write_text('object\n')
        os.chmod(path, 0o444)
        self.assertTrue(os.stat(path).st_file_attributes & 1, 'no read-only attribute was set')

    @windows_only
    def test_the_delete_removes_a_junction_as_a_link_and_its_target_survives(self):
        import _winapi
        _winapi.CreateJunction(str(self.outside), str(self.copy / 'checkout/build'))
        result = self.delete()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.copy.exists(), 'the copy was not deleted')
        self.assertEqual((self.outside / 'keep.txt').read_text(), 'outside the copy\n')

    @windows_only
    def test_the_delete_removes_a_folder_symlink_as_a_link_and_its_target_survives(self):
        try:
            os.symlink(self.outside, self.copy / 'checkout/linked', target_is_directory=True)
        except OSError as error:
            # Without Developer Mode or the privilege no symlink can exist here; the junction case stands.
            sys.stderr.write('\nNOT RUN: %s (no symlink privilege: %s)\n' % (self.id(), error))
            return
        result = self.delete()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.copy.exists(), 'the copy was not deleted')
        self.assertEqual((self.outside / 'keep.txt').read_text(), 'outside the copy\n')

    @windows_only
    def test_the_audit_never_enters_a_junction_and_refuses_one_leading_out(self):
        import _winapi
        # A junction back to the audited root: entered, its .git would be a nested repository.
        _winapi.CreateJunction(str(self.copy / 'checkout'), str(self.copy / 'checkout/self'))
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r'^[0-9a-f]{64}\n$')
        _winapi.CreateJunction(str(self.outside), str(self.copy / 'checkout/out'))
        result = self.audit()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('out is a symlink that leads out of the disposable copy', result.stderr)

    @windows_only
    def test_a_replaced_root_is_refused_and_nothing_is_deleted(self):
        # A running gate cannot rename the folder that holds its working directory here, so the
        # POSIX case's gate cannot build this; the root is replaced around the delete instead.
        import _winapi
        made = os.lstat(self.copy)
        self.copy.rename(self.tmp / 'moved')
        self.copy.mkdir()
        (self.copy / 'kept').write_text('replacement\n')
        result = self.delete(made)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('is no longer the directory made for the disposable copy; deleted nothing', result.stderr)
        # In UTF-8, as sh prints the rest of the self-test: Windows Python wrote the ANSI code page.
        self.assertIn('  FAIL — existing-file probe: ', result.stderr)
        self.assertEqual((self.copy / 'kept').read_text(), 'replacement\n')
        (self.copy / 'kept').unlink()
        self.copy.rmdir()
        _winapi.CreateJunction(str(self.outside), str(self.copy))
        result = self.delete(made)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('deleted nothing', result.stderr)
        self.assertEqual((self.outside / 'keep.txt').read_text(), 'outside the copy\n')

    @windows_only
    def test_the_delete_removes_read_only_git_objects(self):
        self.read_only(self.copy / 'checkout/.git/objects/ab/cdef')
        result = self.delete()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.copy.exists(), 'the copy was not deleted')

    @windows_only
    def test_the_delete_removes_a_tree_whose_paths_pass_260_characters(self):
        # A deep tree (node_modules) in the copy, under a longer temporary folder than the checkout's.
        # Without the long-path prefix the scan and the delete fail on a host with LongPathsEnabled=0;
        # on a host with it enabled this case passes either way and proves only that the prefix works.
        deep = self.copy / 'checkout'
        for _ in range(6):
            deep = deep / ('d' * 50)
        self.assertGreater(len(str(deep)), 260)
        prefix = os.sep * 2 + '?' + os.sep
        os.makedirs(prefix + str(deep))
        (Path(prefix + str(deep)) / 'file.txt').write_text('deep\n')
        result = self.delete()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.copy.exists(), 'the copy was not deleted')

    @windows_only
    def test_a_file_hard_linked_with_the_checkout_keeps_its_read_only_attribute(self):
        # Clearing the attribute to delete the copy's name would clear it on the checkout's file too.
        checkout = self.tmp / 'checkout'
        checkout.mkdir()
        self.read_only(checkout / 'object')
        os.link(checkout / 'object', self.copy / 'checkout/.git/objects/ab/linked')
        result = self.delete()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.copy.exists(), 'the copy was not deleted')
        self.assertEqual((checkout / 'object').read_text(), 'object\n')
        self.assertTrue(os.stat(checkout / 'object').st_file_attributes & 1, 'the read-only attribute was cleared')
        os.chmod(checkout / 'object', 0o644)


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

    def test_any_exported_self_test_prefix_fails_a_normal_run_by_name(self):
        # A seam added later is refused without joining a list (KARARLAR D03 inv2#161).
        code, out = self.run_gate(GATE_SELFTEST_SOMETHING_NEW='1')
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [env]: GATE_SELFTEST_SOMETHING_NEW is set', out)
        code, out = self.run_gate(GATE_BUILD_CMD_OVERRIDE='true')
        self.assertIn('FAIL [env]: GATE_BUILD_CMD_OVERRIDE is set', out)

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
                           ('README', 'Hook documentation\n')):
            self.write('.githooks/' + name, body)
        self.write('scripts/no-shebang.sh', 'true\n')
        code, out = self.run_gate(PATH=str(shim) + os.pathsep + os.environ['PATH'],
                                  SC_INPUTS=log.as_posix())
        self.assertEqual(code, 0, out)
        inputs = log.read_text().splitlines()
        for name in ('.githooks/pre-commit', '.githooks/post-commit.project', 'scripts/no-shebang.sh'):
            self.assertIn(name, inputs)
        for name in ('.githooks/prepare-commit-msg.project', '.githooks/README'):
            self.assertNotIn(name, inputs)


if __name__ == '__main__':
    unittest.main()
