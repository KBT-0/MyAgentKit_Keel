"""Native Windows gate lock cases, run by tests/test_check_gate_windows.py (WindowsLockCaseTests).

Usage: python -I windows_lockcase.py MODE LOCK GATE, where GATE is a copy of check.sh whose
LOCKCASE_* lines (added by the test) stop or kill it right after it holds the lock. Each mode
prints a "lockcase: ..." line or exits with the gate's status; the test asserts both.
"""
import ctypes, os, re, struct, subprocess, sys, time
mode, lock, gate = sys.argv[1:4]
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateFileW.restype = ctypes.c_void_p
kernel32.CreateFileW.argtypes = (ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                                 ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p)
kernel32.DeviceIoControl.argtypes = (ctypes.c_void_p, ctypes.c_ulong, ctypes.c_char_p, ctypes.c_ulong,
                                     ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)
kernel32.GetFileInformationByHandleEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong)
kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
RW, R = 0xC0000000, 0x80000000
def handle(path, access, share, disposition=4, flags=0x80):
    opened = kernel32.CreateFileW(path, access, share, None, disposition, flags, None)
    if opened in (None, ctypes.c_void_p(-1).value):
        print("lockcase: cannot open %s (Windows error %d)" % (path, ctypes.get_last_error()))
        sys.exit(2)
    return opened
def run(environment=None, wait=None):
    return subprocess.call(["sh", gate], env=environment, close_fds=False, timeout=wait)
def claimed(claim):
    os.set_handle_inheritable(claim, True)
    # A run whose refusal is lost goes on to wait for the lock the case holds: 2 s, then 75.
    return dict(os.environ, GATE_LOCK_HELD=lock, GATE_LOCK_FD=str(claim), GATE_LOCK_WAIT="2")
class Entry(ctypes.Structure):
    _fields_ = [("size", ctypes.c_ulong), ("usage", ctypes.c_ulong), ("pid", ctypes.c_ulong),
                ("heap", ctypes.c_size_t), ("module", ctypes.c_ulong), ("threads", ctypes.c_ulong),
                ("parent", ctypes.c_ulong), ("priority", ctypes.c_long), ("flags", ctypes.c_ulong),
                ("exe", ctypes.c_wchar * 260)]
def children(pid):
    snapshot, entry, found = kernel32.CreateToolhelp32Snapshot(2, 0), Entry(), []
    entry.size = ctypes.sizeof(Entry)
    more = kernel32.Process32FirstW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
    while more:
        if entry.parent == pid:
            found.append((entry.pid, entry.exe.lower()))
        more = kernel32.Process32NextW(ctypes.c_void_p(snapshot), ctypes.byref(entry))
    kernel32.CloseHandle(snapshot)
    return found
if mode == "reparse":
    link = handle(lock, 0x40000000, 0, 2, 0x02200000)
    data = struct.pack("<IHH", 0x99, 8, 0) + bytes(range(1, 17)) + b"reparse!"
    done = kernel32.DeviceIoControl(link, 0x000900A4, data, len(data), None, 0,
                                    ctypes.byref(ctypes.c_ulong()), None)
    error = ctypes.get_last_error()
    kernel32.CloseHandle(link)
    try:
        if not done:
            print("lockcase: cannot set a reparse point on %s (Windows error %d)" % (lock, error))
            sys.exit(2)
        sys.exit(run())
    finally:
        os.remove(lock)
if mode == "readonly":
    # Writable, on the lock file, nothing else holding it; then the file is made read-only, so a
    # fresh open for writing fails with access denied (5), not a sharing violation (32).
    environment = claimed(handle(lock, RW, 7))
    if not kernel32.SetFileAttributesW(lock, 1):
        print("lockcase: cannot make %s read-only (Windows error %d)" % (lock, ctypes.get_last_error()))
        sys.exit(2)
    try:
        sys.exit(run(environment))
    finally:
        kernel32.SetFileAttributesW(lock, 0x80)
if mode in ("noid", "wide"):
    # The proof's own code from the gate, run with GetFileInformationByHandleEx faked: 'noid'
    # gives no FILE_ID_INFO at all; 'wide' reports, for a handle on another file, the lock's
    # FILE_ID_INFO with only its last byte changed (same volume, same first 64 id bits).
    source = re.search(r"lock_probe=0\n  python3 -I -c '\n(.*?)\n' \"\$\{GATE_LOCK_FD:-\}\"",
                       open(gate, encoding="utf-8").read(), re.S)
    if not source:
        print("lockcase: the nested-run proof was not found in %s" % gate)
        sys.exit(2)
    held = handle(lock, RW, 1)
    claim = held if mode == "noid" else handle(lock + ".other", RW, 3)
    os.set_handle_inheritable(claim, True)
    info = ctypes.create_string_buffer(24)
    if not kernel32.GetFileInformationByHandleEx(held, 18, info, 24):
        print("lockcase: this volume gives the lock file no FILE_ID_INFO (Windows error %d)" % ctypes.get_last_error())
        sys.exit(2)
    near = info.raw[:23] + bytes([info.raw[23] ^ 1])
    real = ctypes.WinDLL
    class Fake:
        argtypes = restype = None
        def __init__(self, function):
            self.function = function
        def __call__(self, target, kind, buffer, size):
            if mode == "noid":
                ctypes.set_last_error(87)
                return 0
            if target != claim:
                return self.function(target, kind, buffer, size)
            ctypes.memmove(buffer, near, 24)
            return 1
    class Kernel:
        def __init__(self, dll):
            object.__setattr__(self, "dll", dll)
            object.__setattr__(self, "fake", Fake(dll.GetFileInformationByHandleEx))
        def __getattr__(self, name):
            return self.fake if name == "GetFileInformationByHandleEx" else getattr(self.dll, name)
    ctypes.WinDLL = lambda *args, **kwargs: Kernel(real(*args, **kwargs))
    sys.argv = ["-c", str(claim), lock]
    try:
        exec(compile(source[1], "nested-run proof", "exec"), {"__name__": "__main__"})
        status = 0
    except SystemExit as stop:
        status = stop.code if isinstance(stop.code, int) else 1
    sys.stdout.flush()
    print("lockcase: proof exit %d" % status)
    sys.exit(0)
if mode == "shadow":
    # Stand-ins on PYTHONPATH for modules the holder imports; each marks that it was imported.
    folder = lock + ".shadow"
    os.mkdir(folder)
    for name in ("fcntl", "secrets"):
        with open(os.path.join(folder, name + ".py"), "w") as stand_in:
            stand_in.write('open(__file__ + ".imported", "w").close()\nraise ImportError("a stand-in")\n')
    status = run(dict(os.environ, PYTHONPATH=folder))
    imported = sorted(name for name in os.listdir(folder) if name.endswith(".imported"))
    print("lockcase: stand-ins imported: %s; the gate exited %d" % (", ".join(imported) or "none", status))
    sys.exit(0)
if mode in ("interrupt", "earlyint"):
    # A console of its own, hidden, so the Ctrl-C reaches only this case's processes.
    inside = "console" if mode == "interrupt" else "early"
    try:
        inner = subprocess.run([sys.executable, "-I", __file__, inside, lock, gate], creationflags=0x10,
                               startupinfo=subprocess.STARTUPINFO(dwFlags=1, wShowWindow=0),
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, errors="replace", timeout=150)
    except subprocess.TimeoutExpired:
        print("lockcase: the interrupt case did not end in 150 s")
        sys.exit(2)
    sys.stdout.write(inner.stdout)
    sys.exit(inner.returncode)
if mode == "early":
    # Ctrl-C after the holder's handler is installed and before the gate exists: the holder is
    # kept waiting for the lock this process holds, interrupted, and then given the lock.
    kernel32.SetConsoleCtrlHandler(None, False)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    held, started, log = handle(lock, RW, 1), lock + ".started", lock + ".log"
    output = open(log, "w")
    first = subprocess.Popen(["sh", gate], stdin=open("CONIN$"), stdout=output, stderr=subprocess.STDOUT,
                             env=dict(os.environ, LOCKCASE_HOLD=started))
    try:
        deadline = time.monotonic() + 60
        while "NOTE [lock]" not in open(log).read():
            if first.poll() is not None or time.monotonic() > deadline:
                print("lockcase: the gate never waited for the lock")
                sys.exit(2)
            time.sleep(0.1)
        holders = [found for found, exe in children(first.pid) if exe.startswith("python")]
        if len(holders) != 1:
            print("lockcase: expected one python holder under the gate, found %r" % children(first.pid))
            sys.exit(2)
        holder, code = kernel32.OpenProcess(0x101000, False, holders[0]), ctypes.c_ulong()
        kernel32.SetConsoleCtrlHandler(None, True)
        kernel32.GenerateConsoleCtrlEvent(0, 0)
        time.sleep(3)
        kernel32.CloseHandle(ctypes.c_void_p(held))
        held = None
        if not holder or kernel32.WaitForSingleObject(ctypes.c_void_p(holder), 30000) != 0 or \
                not kernel32.GetExitCodeProcess(ctypes.c_void_p(holder), ctypes.byref(code)):
            print("lockcase: the holder did not end in 30 s after the lock was free")
            sys.exit(2)
        print("lockcase: a Ctrl-C before the gate started: its holder exited %d; the gate %s"
              % (code.value, "ran" if os.path.exists(started) else "never ran"))
        sys.exit(0)
    finally:
        if held:
            kernel32.CloseHandle(ctypes.c_void_p(held))
        subprocess.call(["taskkill", "/F", "/T", "/PID", str(first.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        first.wait()
        output.close()
if mode == "console":
    # A caller (a CI runner, an agent's shell) may hand down an ignored Ctrl-C; a terminal does not.
    kernel32.SetConsoleCtrlHandler(None, False)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    build = lock + ".build"
    first = subprocess.Popen(["sh", gate], stdin=open("CONIN$"), env=dict(os.environ, LOCKCASE_BUILD=build))
    pid, status, stopped, holder, held = None, None, False, None, None
    try:
        deadline = time.monotonic() + 60
        while pid is None:
            text = open(build).read() if os.path.exists(build) else ""
            if text.isdigit():
                pid = int(text)
            elif first.poll() is not None or time.monotonic() > deadline:
                print("lockcase: the gate never started its build")
                sys.exit(2)
            else:
                time.sleep(0.1)
        # The holder, which must outlive Ctrl-C to pass on the status of the gate it waits for.
        holders = [found for found, exe in children(first.pid) if exe.startswith("python")]
        if len(holders) != 1:
            print("lockcase: expected one python holder under the gate, found %r" % children(first.pid))
            sys.exit(2)
        holder = kernel32.OpenProcess(0x101000, False, holders[0])
        time.sleep(1)
        kernel32.SetConsoleCtrlHandler(None, True)
        kernel32.GenerateConsoleCtrlEvent(0, 0)
        try:
            status = first.wait(10)
        except subprocess.TimeoutExpired:
            pass
        process = kernel32.OpenProcess(0x100000, False, pid)
        stopped = not process or kernel32.WaitForSingleObject(ctypes.c_void_p(process), 10000) == 0
        if process:
            kernel32.CloseHandle(process)
        code = ctypes.c_ulong()
        if holder and kernel32.WaitForSingleObject(ctypes.c_void_p(holder), 10000) == 0 and \
                kernel32.GetExitCodeProcess(ctypes.c_void_p(holder), ctypes.byref(code)):
            held = code.value
        after = subprocess.call(["sh", gate], env=dict(os.environ, GATE_LOCK_WAIT="5"),
                                stdin=subprocess.DEVNULL, timeout=60)
        print("lockcase: the interrupted gate exited %s; its holder exited %s; its build %s; the next gate exited %d"
              % (status, held, "stopped" if stopped else "ran on", after))
        sys.exit(0)
    finally:
        if pid and not stopped:
            subprocess.call(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.call(["taskkill", "/F", "/T", "/PID", str(first.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        first.wait()
if mode in ("killgate", "failgate"):
    marker = lock + "." + mode
    status = run(dict(os.environ, **{"LOCKCASE_KILL" if mode == "killgate" else "LOCKCASE_FAIL": marker}))
    if not os.path.exists(marker):
        print("lockcase: the copy of the gate never reached its LOCKCASE line")
        sys.exit(2)
    print("lockcase: a gate %s exited %d" % ("killed by a signal" if mode == "killgate" else "that failed with 3", status))
    sys.exit(0)
if mode == "killholder":
    started = lock + ".started"
    first = subprocess.Popen(["sh", gate], env=dict(os.environ, LOCKCASE_HOLD=started), close_fds=False)
    try:
        deadline = time.monotonic() + 60
        while not os.path.exists(started):
            if first.poll() is not None or time.monotonic() > deadline:
                print("lockcase: the first gate never reached its LOCKCASE line")
                sys.exit(2)
            time.sleep(0.1)
        holders = [pid for pid, exe in children(first.pid) if exe.startswith("python")]
        if len(holders) != 1:
            print("lockcase: expected one python holder under the first gate, found %r" % children(first.pid))
            sys.exit(2)
        subprocess.call(["taskkill", "/F", "/PID", str(holders[0])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sys.exit(run(dict(os.environ, LOCKCASE_HOLD=lock + ".second", GATE_LOCK_WAIT="2"), 60))
    finally:
        subprocess.call(["taskkill", "/F", "/T", "/PID", str(first.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        first.wait()
if mode != "unheld":
    holder = handle(lock, RW, 1)
claim = {"other": lambda: handle(lock + ".other", RW, 3), "reader": lambda: handle(lock, R, 3),
         "unheld": lambda: handle(lock, RW, 3)}[mode]()
sys.exit(run(claimed(claim)))
