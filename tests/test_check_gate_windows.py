"""The gate lock on native Windows: Git for Windows' sh running the gate, a native python3.

Native Windows Python has no fcntl. The gate there holds its lock as a file handle opened
without write sharing, which the holder makes inheritable, so the gate and every process it
starts keep it and Windows closes it when the last of them exits. A nested run proves the
inherited handle: open in its own process on this lock file, with write access, while a fresh
open for writing is refused, the file compared by FILE_ID_INFO. Every case here runs only on
native Windows; elsewhere each one prints a NOT RUN line and passes, as the kit check expects.
On native Windows no case is NOT RUN: a guard whose case cannot run there fails.
"""
import ctypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
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

def kill_tree(pid):
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True)


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
    return subprocess.Popen(['sh', 'scripts/check.sh'], cwd=cwd, env=environment(build, **extra),
                            text=True, errors='replace', stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, close_fds=False)


def finish(proc, timeout=90):
    try:
        out = proc.communicate(timeout=timeout)[0]
    except subprocess.TimeoutExpired:
        kill_tree(proc.pid)
        return None, proc.communicate()[0]
    return proc.returncode, out


def gate(cwd, build, timeout=90, **extra):
    return finish(start(cwd, build, **extra), timeout)


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
        deadline = time.monotonic() + 60
        while not (self.side / 'held').exists():
            self.assertIsNone(proc.poll(), 'the gate to be killed ended before its build started')
            self.assertLess(time.monotonic(), deadline, 'the gate to be killed never started its build')
            time.sleep(0.1)
        kill_tree(proc.pid)
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
        holders = [pid for pid, name in children(proc.pid) if name.lower().startswith('python')]
        self.assertEqual(len(holders), 1, children(proc.pid))
        subprocess.run(['taskkill', '/F', '/PID', str(holders[0])], check=True, capture_output=True)
        waiters = [start(self.project, self.build, SIDE=self.side.as_posix()) for _ in range(2)]
        results = [finish(waiter, 120) for waiter in waiters]
        kill_tree(proc.pid)
        proc.communicate()
        outputs = '\n'.join(out for _, out in results)
        self.assertEqual([code for code, _ in results], [0, 0], outputs)

    @windows_only
    def test_a_gate_killed_by_a_signal_never_exits_zero(self):
        # Git for Windows reports a child that died of signal N to native Python as N << 8;
        # passed on as the exit status, sh read its low byte: 0, a pass.
        self.write_build('kill -9 $PPID\nsleep 5\n')
        code, out = gate(self.project, self.build)
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
        source = re.search(r"lock_probe=0\n  python3 -c '\n(.*?)\n' \"\$\{GATE_LOCK_FD:-\}\"", text, re.S)
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

if __name__ == '__main__':
    unittest.main()
