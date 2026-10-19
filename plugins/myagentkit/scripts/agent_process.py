"""Bounded child execution shared by both CLI adapters; preserve partial diagnostics.

Sources (D01 inv2#66): docs.python.org/3/library/subprocess.html (timeout, start_new_session);
CPython issue 26534 (bugs.python.org/issue26534); Airflow's reap_process_group
(airflow.apache.org/docs/apache-airflow/stable/_modules/airflow/utils/process_utils.html).
"""
import os
from pathlib import Path
import queue
import signal
import select
import selectors
import shutil
import subprocess
import sys
import tempfile
import threading
import time

# A high-effort review of a large diff outran 1800 seconds and 12 turns; a review the kit's own
# caps kill is paid for and returns nothing. The defaults leave such a review room to finish;
# the kit's Claude reviews ended in 1-9 minutes, its high-effort Codex reviews in 37-58 (RL
# 2026-10-13), so a high-effort Codex review defaults to the maximum (codex_bridge; owner
# decision 2026-10-13, H: 2700/3600; KARARLAR B03 inv2#31). Claude Code's ultrareview
# --timeout defaults to 45 minutes, the same 2700 s.
# REVIEW_TIMEOUT_SECONDS and REVIEW_MAX_TURNS (review.sh) change them per run, up to the maxima.
DEFAULT_REVIEW_TIMEOUT = 2700
MAX_REVIEW_TIMEOUT = 3600
DEFAULT_REVIEW_TURNS = 200
MAX_REVIEW_TURNS = 500
# Seconds the pipes still drain once the reviewer itself has exited. A descendant that inherited
# its stdout held the pipe open, and a finished review waited out the wall-clock limit as a
# timeout (#197). Five is the kit's choice: the leader's own output is in the pipe at its exit.
DRAIN_GRACE_SECONDS = 5
# Ctrl-C, kill and a closed terminal or restarted host session. The reviewer runs in its own
# session so none of these reach it; left at their defaults, SIGTERM and SIGHUP end this
# process without its cleanup and the paid reviewer keeps running, unaccounted. Native Windows
# Python has no SIGHUP: the tuple holds the ones that exist, and the import never fails there.
CANCEL_SIGNALS = tuple(getattr(signal, name) for name in ("SIGINT", "SIGTERM", "SIGHUP")
                       if hasattr(signal, name))
# The platform seam: every launch, signal block and group kill of the review tooling goes
# through the five functions below (test_claude_bridge checks that no other place makes one).
# Off POSIX (native Windows Python) there is no signal mask, no session and no killpg: the
# blocks record cancels, and a child starts suspended, joins a Job Object of its own and only then
# runs, so every process it starts is in that job and TerminateJobObject stops them all, also
# after the child itself has exited (taskkill /T finds no tree below an exited process). The
# job is killed when its last handle closes: a supervisor that dies takes its reviewer with it.
# Ceiling: a packaged-app execution alias (the WindowsApps `python3` stub that opens the Python
# install manager) is started by the system broker, not by the child, so it is outside the job
# and cancel and timeout cannot stop what a reviewer starts through it.
POSIX = os.name == "posix"
_WIN = {}


def _win() -> dict:
    """kernel32, ntdll and the job limits structure, set up on first use: at import, a module
    run where ctypes has no Windows half (a test that names the platform nt) did not load."""
    if not _WIN:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll")
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                     wintypes.DWORD)
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)

        class JobLimits(ctypes.Structure):
            """JOBOBJECT_EXTENDED_LIMIT_INFORMATION; only LimitFlags is set."""
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD), ("IoInfo", ctypes.c_uint64 * 6),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        _WIN.update(ctypes=ctypes, kernel32=kernel32, ntdll=ntdll, JobLimits=JobLimits)
    return _WIN


def block_cancels():
    """Block the cancel signals; return what restore_mask() needs.

    Off POSIX there is no signal mask: until restore_mask() the cancels go to a recorder, which
    hands each one on to the handler then in place. Without it a Ctrl-C between the reviewer's
    launch and the caller holding its handle met the caller's raising handler there, and the
    reviewer ran on with nobody to stop it. Only the main thread installs handlers.
    """
    if POSIX:
        return signal.pthread_sigmask(signal.SIG_BLOCK, CANCEL_SIGNALS)
    if threading.current_thread() is not threading.main_thread():
        return None
    held = []

    def recorder(signum, frame):
        held.append(signum)
    recorder.held = held
    return recorder, {sig: signal.signal(sig, recorder) for sig in CANCEL_SIGNALS}, held


def restore_mask(mask) -> None:
    if POSIX:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        return
    if mask is None:
        return
    recorder, saved, held = mask
    for sig, handler in saved.items():
        # A handler swapped in inside the block (handing_back restores the caller's) stays.
        if signal.getsignal(sig) is recorder and handler is not None:
            signal.signal(sig, handler)
    for sig in held:
        signal.raise_signal(sig)


def pending() -> set:
    """The signals pending while blocked, or held by the off-POSIX recorder."""
    if POSIX:
        return signal.sigpending()
    return {sig for cancel in CANCEL_SIGNALS for sig in getattr(signal.getsignal(cancel), 'held', ())}


def _holds(pid, name) -> bool:
    """Whether /proc shows `name`=1 in the environment of process `pid`."""
    try:
        with open("/proc/%s/environ" % pid, "rb") as environ:
            return name.encode() + b"=1" in environ.read().split(b"\0")
    except OSError:
        return False  # gone, another user's, or not dumpable (launch())


_SCAN_UNAVAILABLE = []


def _marked(name) -> list | None | bool:
    """Pids holding `name`=1 (/proc or ps -E). None: a ps read failed after the listing showed
    the marker, and found no match (worth another scan). False: the listing itself failed (a ps
    without -E, the BSDs, or no /bin/ps), which another scan does not mend."""
    if os.path.isdir("/proc/self"):
        return [int(pid) for pid in filter(str.isdigit, os.listdir("/proc")) if _holds(pid, name)]
    failed = False
    def ps(*options):
        nonlocal failed
        try:
            # A project's PATH may contain CLI fixtures or wrappers; use the host's ps.
            result = subprocess.run(["/bin/ps", *options], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if not result.returncode:
                return result
        except OSError:
            pass
        # BSD ps exits 1 for a pid that exited since the enumeration: that one is gone, and the
        # scan is whole. Read as a failure, any process on the host exiting mid-scan warned.
        if options[-2] == "-p":
            try:
                os.kill(int(options[-1]), 0)
            except ProcessLookupError:
                return None
            except PermissionError:
                pass
        failed = True
        # A failed ps is no scan, not an empty one: say so once per process.
        if not _SCAN_UNAVAILABLE:
            _SCAN_UNAVAILABLE.append(name)
            sys.stderr.write("agent_process: /bin/ps %s failed; review descendant scan is incomplete\n"
                             % " ".join(options))
        return None
    entry = name.encode() + b"=1"
    listing = ps("-A", "-E", "-ww", "-o", "command=")
    if listing is None:
        return False
    # A raw newline inside an environment value (PORTS=$'8080\n8081') splits a record over
    # lines, and a continuation line led by digits read as a new record: the marker went to a
    # pid naming another process, which was killed while the marked one ran on. The whole
    # listing says only whether any process holds the marker; each pid is then read on its
    # own, so all of its output is its own.
    if entry not in listing.stdout.split():
        return []
    every = ps("-A", "-o", "pid=")
    if every is None:
        return None
    pids = []
    for pid in filter(bytes.isdigit, every.stdout.split()):
        record = ps("-E", "-ww", "-o", "command=", "-p", pid.decode())
        if record is not None and entry in record.stdout.split():
            pids.append(int(pid))
    return pids if pids or not failed else None


def launch(command, mask, **popen_kw) -> subprocess.Popen:
    """Popen in a group of its own. Called with the cancels blocked (`mask` is what
    block_cancels() returned): on POSIX the child restores `mask` before exec."""
    if POSIX:
        # A descendant that calls setsid (start_new_session) leaves this group, and killpg
        # never reached it: it ran on after a cancel or a timeout. Every descendant inherits
        # this variable, and stop_group kills each process whose environment holds it. Chosen
        # over PR_SET_CHILD_SUBREAPER, which is Linux only (macOS has none) and makes this
        # supervisor the parent of every orphan of the run. A name per launch, not one shared
        # name: a nested run adds its own and keeps the outer one, so the outer stop still
        # finds it. Ceiling: a descendant whose environment cannot be read escapes: one
        # started with a cleared environment (env -i); on Linux one that is not dumpable
        # (prctl PR_SET_DUMPABLE 0, as ssh-agent does, or a setuid, setgid or file-capability
        # binary), whose /proc environ is closed to us; on macOS one whose environment ps -E
        # does not show; and one that rewrites its process title (setproctitle: nginx, Redis,
        # Perl `$0`), which overwrites its environment memory, the marker included (#198). A
        # daemon that also calls setsid escapes the group kill too. A cgroup per run would hold
        # all of these, but it is Linux only and needs delegation; that change is the owner's.
        marker = "MYAGENTKIT_PROCESS_" + os.urandom(8).hex()
        environment = os.environ if popen_kw.get("env") is None else popen_kw["env"]
        popen_kw["env"] = dict(environment, **{marker: "1"})
        child = subprocess.Popen(command, start_new_session=True,
                                 preexec_fn=lambda: restore_mask(mask), **popen_kw)
        child._kit_marker = marker
        return child
    # A bare name is looked up as a shell would, PATHEXT included: CreateProcess adds only
    # .exe, and an npm-installed CLI (codex, claude) is a .cmd, so every review there failed
    # to launch. The search follows the child's PATH when the caller gives it one.
    if os.path.basename(command[0]) == command[0]:
        path = (popen_kw.get("env") or os.environ).get("PATH")
        command = [shutil.which(command[0], path=path) or command[0], *command[1:]]
    # A .cmd or .bat runs under cmd.exe, which reads its command line as shell: Popen's quoting
    # does not escape `&` or `%` for it, and an argument `a&echo>x` ran `echo` (BatBadBut). An
    # argument or launcher path with a character cmd.exe acts on is refused before anything starts.
    if command[0].lower().endswith((".cmd", ".bat")):
        unsafe = [arg for arg in command if any(c in arg for c in '"%^&|<>!\r\n')]
        if unsafe:
            raise OSError("%s is a batch file, and cmd.exe would read %r as shell; name the CLI's "
                          "executable instead (REVIEW_CLI_BIN, CLAUDE_CLI_BIN)" % (command[0], unsafe[0]))
    # Suspended (0x4) until it is in the job: running, it could start a process outside it first.
    child = subprocess.Popen(command, **popen_kw, creationflags=0x200 | 0x4)  # CREATE_NEW_PROCESS_GROUP
    job = None
    try:
        win = _win()
        ctypes, kernel32 = win["ctypes"], win["kernel32"]
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = win["JobLimits"](LimitFlags=0x2000)  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel32.AssignProcessToJobObject(job, int(child._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
        if win["ntdll"].NtResumeProcess(int(child._handle)) != 0:
            raise OSError("cannot resume %s after it joined its job" % command[0])
    except BaseException:
        if job:
            kernel32.CloseHandle(job)
        child.kill()
        child.wait()
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream is not None:
                stream.close()
        raise
    child._kit_job = job
    return child


def lock_file(lock, create: bool) -> None:
    """Take a nonblocking exclusive lock on the open file `lock`, or raise OSError. Windows
    locks a byte range, so a file just created (`create`) gets its one byte first."""
    if os.name == "nt":
        import msvcrt
        if create:
            lock.write(b"0")
            lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def stop_group(child, pgid) -> None:
    """Kill `child`'s group (or, off POSIX, its process tree) and reap the leader.

    POSIX: the leader may have exited while a descendant still holds a pipe open. On macOS a
    group whose leader is a zombie answers EPERM: the leader is then signalled by its pid, and
    the group again once it is reaped. Windows: TerminateJobObject stops every process in the
    child's job (launch()), once; a child launched elsewhere gets `taskkill /T /F`, and
    child.kill() when taskkill is missing or fails.

    POSIX also kills every process whose environment holds the child's marker (launch()), so
    a descendant that left the group with setsid stops too. A failed scan is retried, up to 20
    scans, and a give-up is reported. A ps that cannot list environments is tried once, unless
    an earlier scan found a process. Ceilings: a descendant whose
    environment cannot be read survives (launch() names them), and outside Linux pidfds a pid
    reused between the scan and the kill can be signalled (below).
    """
    if POSIX:
        # The leader's pid is signalled only while it is ours (not yet reaped): a reaped
        # pid may already be another process.
        # The group is signalled ONCE, while its leader is still ours (not yet reaped): a
        # reaped group id may already be another process's. macOS answers EPERM for a group
        # whose only member is the zombie leader (nothing left to stop); the leader is then
        # signalled by pid, a no-op for a zombie, and reaped.
        if child.returncode is None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                os.kill(child.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            child.wait()
        # The descendants that left the group (launch()). Scanned again until none is left:
        # one may have started another before it was killed. A zombie's environment reads
        # empty, so a reaped id is never matched.
        # A failed scan (None) is retried. A failed listing (False) is retried only after a scan
        # found a process: where ps -E never works, 20 doomed scans cost every stop a second.
        found = False
        for _ in range(20):
            pids = _marked(child._kit_marker) if hasattr(child, "_kit_marker") else ()
            if pids is None or (pids is False and found):
                time.sleep(0.05)
                continue
            if not pids:
                break
            found = True
            for pid in pids:
                # A process found may have exited since the scan and its pid gone to another.
                # On Linux the kill goes through a pidfd opened first, and only after the
                # environment is read again: a pid reused before the open fails that read, one
                # reused after it leaves the pidfd on the dead process. Ceiling: on macOS, or a
                # Linux kernel without pidfds (before 5.3), the window between the scan and
                # os.kill stays; sequential pid allocation keeps it small.
                try:
                    handle = os.pidfd_open(pid) if hasattr(signal, "pidfd_send_signal") else None
                except ProcessLookupError:
                    continue
                except OSError:
                    handle = None
                try:
                    if handle is None:
                        os.kill(pid, signal.SIGKILL)
                    elif _holds(pid, child._kit_marker):
                        signal.pidfd_send_signal(handle, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                finally:
                    if handle is not None:
                        os.close(handle)
            time.sleep(0.05)
        else:
            sys.stderr.write("agent_process: review descendant cleanup gave up after 20 scans\n")
    elif getattr(child, "_kit_job", None) is not None:
        job, child._kit_job = child._kit_job, None
        _win()["kernel32"].TerminateJobObject(job, 1)
        _win()["kernel32"].CloseHandle(job)
    elif not hasattr(child, "_kit_job"):
        try:
            done = subprocess.run(["taskkill", "/T", "/F", "/PID", str(child.pid)],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL).returncode == 0
        except OSError:
            done = False
        if not done:
            try:
                child.kill()
            except OSError:
                pass
    child.wait()


def hold(handler) -> dict:
    """Route the cancel signals to `handler`; return the handlers to restore()."""
    if threading.current_thread() is not threading.main_thread():
        return {}
    # nohup ignores SIGHUP and a background job SIGINT; the caller chose that, keep it.
    return {sig: signal.signal(sig, handler) for sig in CANCEL_SIGNALS
            if signal.getsignal(sig) is not signal.SIG_IGN}


def restore(previous: dict) -> None:
    for sig, handler in previous.items():
        signal.signal(sig, handler)


def handing_back(previous: dict, settle) -> None:
    """Restore `previous` with the cancel signals blocked; `settle(pending)` the records.

    Restored one at a time, a cancel between two swaps met the caller's handler (SIG_DFL ends
    the process) before the adapter had persisted the cancel it had already noted. Blocked, it
    waits while the adapter corrects its records and writes its last line, then reaches the
    caller's handler when the block exits. Sampled once, a cancel arriving while `settle` ran
    reached the caller with the records still saying quota: `settle` runs again for every
    cancel that is new since the last sample. Windows has no signal mask: finish settlement
    with the recorder still installed, restore the caller's handlers last, then forward.
    On Windows, cancels received after the last settlement sample through the end of
    `restore(previous)` are excluded and may reach the caller unsettled.
    """
    mask = block_cancels()
    try:
        # Off POSIX the recorder must keep the handlers until the last settlement finishes.
        if POSIX:
            restore(previous)
        seen = None
        while True:
            held = pending() & set(previous)
            if seen is not None and held <= seen:
                break
            seen = held
            settle(held)
    finally:
        try:
            if not POSIX and mask is not None:
                # If a restored caller raises midway, cleanup must restore the remaining
                # caller handlers, not the adapter's abandoned handlers saved by the block.
                mask[1].update(previous)
                while True:
                    # Read this block's recorder directly, including a cancel received after
                    # the loop's last sample. A second cancel cannot interrupt persistence.
                    held = set(mask[2]) & set(previous)
                    # seen is None when the loop failed before its first sample.
                    if seen is not None and held <= seen:
                        break
                    seen = held
                    settle(held)
                restore(previous)
        finally:
            restore_mask(mask)


class OneShot:
    """Cancel handler: the first cancel raises, every later one is only noted.

    Switching to noting is `guard.armed = False`, an attribute store with no signal check
    before it. Swapping in noting handlers one signal at a time left a window in which a
    cancel still met the raising handler: once past the group kill and the reap, once
    before the Codex adapter had written its evidence and usage.
    """

    def __init__(self):
        self.armed = True
        self.noted = []
        self.previous = {}

    def __call__(self, signum, frame):
        self.noted.append(signum)
        if self.armed:
            self.armed = False
            raise KeyboardInterrupt

    def __enter__(self):
        self.previous = hold(self)
        return self

    def __exit__(self, *exc):
        # Restored with the cancel signals blocked: one at a time, a cancel after the first
        # restore met the caller's raising handler there and left the other signals routed to
        # this guard, whose notes nobody read afterwards. A cancel held while they went back is
        # this guard's: taken off the pending set and noted, so run() returns it as a cancel.
        mask = block_cancels()
        try:
            restore(self.previous)
            if POSIX:
                for sig in sorted(pending() & set(self.previous)):
                    self.noted.append(signal.sigwait({sig}))
            elif mask is not None:
                # Off POSIX this block's own recorder held them (there is no sigwait): noted
                # here and not handed on. One an outer block's recorder holds stays its own:
                # read through pending(), it reached sigwait, which Windows lacks.
                held = mask[2]
                self.noted.extend(sig for sig in held if sig in self.previous)
                held[:] = [sig for sig in held if sig not in self.previous]
        finally:
            restore_mask(mask)


def run(command: list[str], prompt: str, repo: Path, timeout: float, into: dict | None = None,
        noted: list | None = None) -> dict:
    """Return launch status, exit status, partial output, and termination reason within a fractional seconds budget.

    `into` receives the result before the caller's handlers are restored: a raising one
    restored there raised before the returned result was assigned, and the attempt was lost.
    `noted` is the caller's own list of cancels its noting handler saw before this guard was
    up: one there stops the launch, as a cancel during the run stops the reviewer.
    """
    if not 0 < timeout <= MAX_REVIEW_TIMEOUT:
        raise ValueError("timeout must be greater than zero and at most %d seconds" % MAX_REVIEW_TIMEOUT)
    started = time.monotonic()
    result = {} if into is None else into
    guard = OneShot()
    try:
        with guard:
            result.update(_supervise(command, prompt, repo, timeout, started, guard, noted, result))
            return result
    finally:
        # Noted while the handlers were restored: still a cancel.
        if result and guard.noted:
            result["cancelled"] = True


def drain(streams: dict) -> queue.SimpleQueue:
    """Off POSIX, where select() takes sockets only: one daemon thread per pipe in `streams`
    ({name: stream}) reads it to EOF and puts (name, bytes) on the returned queue, b"" last.
    The threads end when the pipes close, which stop_group() makes happen."""
    chunks = queue.SimpleQueue()

    def read(name, fd):
        try:
            while True:
                data = os.read(fd, 65536)
                chunks.put((name, data))
                if not data:
                    return
        except OSError:
            chunks.put((name, b""))

    for name, stream in streams.items():
        threading.Thread(target=read, args=(name, stream.fileno()), daemon=True).start()
    return chunks


def take(chunks: queue.SimpleQueue, timeout: float) -> list:
    """What drain() queued, waiting up to `timeout` for the first chunk. A sleep loop, not a
    blocking get: Windows raises a Ctrl-C in a sleep, while a lock wait there may not see it."""
    deadline = time.monotonic() + timeout
    got = []
    while True:
        try:
            while True:
                got.append(chunks.get_nowait())
        except queue.Empty:
            pass
        if got or time.monotonic() >= deadline:
            return got
        time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))


def _exited_unreaped(child, timeout: float) -> bool:
    """True once `child` has exited, leaving it unreaped on POSIX so its process group is still
    its own for stop_group (a reaped id may be another process's); False at the deadline.
    Linux: waitid with WNOWAIT. macOS has no waitid in CPython: a kqueue NOTE_EXIT event says
    the same. Elsewhere the ordinary wait reaps it: there is no group to keep."""
    if child.returncode is not None:
        return True
    deadline = time.monotonic() + timeout
    if POSIX and hasattr(os, "waitid"):
        while True:
            try:
                if os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
                    return True
            except ChildProcessError:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
    if POSIX and hasattr(select, "kqueue"):
        kq = select.kqueue()
        try:
            try:
                kq.control([select.kevent(child.pid, select.KQ_FILTER_PROC, select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                                          select.KQ_NOTE_EXIT)], 0)
            except ProcessLookupError:
                return True  # exited before the watch: the zombie is still ours
            return bool(kq.control(None, 1, max(0.0, timeout)))
        finally:
            kq.close()
    try:
        child.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


def finish(child, pgid, timeout: float) -> bool:
    """Wait for `child` to exit (unreaped), stop its group, then reap it. True on exit, False
    when the deadline passed (the group is stopped either way)."""
    exited = _exited_unreaped(child, timeout)
    stop_group(child, pgid)
    return exited


def _supervise(command, prompt, repo, timeout, started, guard, prior=None, into=None):
    with tempfile.TemporaryFile() as inp, selectors.DefaultSelector() as selector:
        # A file gives even a slow-starting CLI the entire prompt and EOF. Repeated
        # communicate(input=None) after a short timeout can strand a partially written pipe.
        inp.write(prompt.encode())
        inp.seek(0)
        child = termination = None
        launch_failed = exited = False
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        try:
            try:
                # Blocked across Popen: a cancel after the child existed but before Popen
                # returned left no handle, and the group ran on. The child unblocks before
                # exec; here a pending cancel is raised on unblock, with the handle kept.
                mask = block_cancels()
                try:
                    # A cancel the caller noted before this guard was up: never launched. One
                    # after that met the guard, or is pending here and raised on unblock.
                    if prior:
                        raise KeyboardInterrupt
                    # PWD names the working directory, never the caller's: a reviewer in a
                    # throwaway copy is not told the repository's path (claude_bridge.
                    # throwaway_copy). A GIT_DIR from a hook would send its git to the repository.
                    # D09 inv2#122: denylist: a new GIT_* style variable would pass; an allowlist (PATH, HOME,
                    # auth, locale) is stricter (Saltzer-Schroeder, fail-safe defaults).
                    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")
                           and k not in ("OLDPWD", "REVIEW_REPO_ROOT", "CLAUDE_PROJECT_DIR",
                                         "REVIEW_DISPOSITIONS", "REVIEW_SHADOW")}
                    # The reviewer's git never discovers a repository above its working
                    # directory: a copy made inside some checkout stays inside the copy.
                    env["GIT_CEILING_DIRECTORIES"] = str(repo.parent)
                    # No bytecode in the copy: on Windows the Codex sandbox writes __pycache__
                    # under an account whose folders this user cannot open, read or remove.
                    env["PYTHONDONTWRITEBYTECODE"] = "1"
                    child = launch(command, mask, cwd=repo, stdin=inp, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   env=dict(env, PWD=str(repo), MYAGENTKIT_DELEGATION_DEPTH="1"))
                finally:
                    restore_mask(mask)
            except OSError as error:
                # Not returned here: the result is built after cleanup, which can note a cancel.
                termination, launch_failed = "unavailable", True
                buffers["stderr"].extend(str(error).encode())
            else:
                if POSIX:
                    for name, stream in (("stdout", child.stdout), ("stderr", child.stderr)):
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, selectors.EVENT_READ, name)
                else:
                    chunks, open_streams = drain({"stdout": child.stdout, "stderr": child.stderr}), 2
                gone = None

                def drained():
                    # The leader exited (seen without reaping) DRAIN_GRACE_SECONDS ago: what still
                    # holds a pipe is a descendant, which stop_group ends below (#197).
                    nonlocal gone
                    try:
                        if gone is None and _exited_unreaped(child, 0):
                            gone = time.monotonic()
                    except OSError:
                        pass  # only the grace's look: the wait once the pipes close reports the fault
                    return gone is not None and time.monotonic() - gone >= DRAIN_GRACE_SECONDS
                # 8,000,000 bytes per stream is the owner's choice of safety cap,
                # not a provider limit (B03 inv2#65).
                while not POSIX and open_streams:
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        termination = "timeout"
                        break
                    if drained():
                        break
                    for name, data in take(chunks, min(0.2, remaining)):
                        if not data:
                            open_streams -= 1
                            continue
                        buffer = buffers[name]
                        space = 8_000_000 - len(buffer)
                        buffer.extend(data[:space])
                        if len(data) > space:
                            termination = "output_limit"
                            break
                    if termination:
                        break
                while POSIX and selector.get_map():
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        termination = "timeout"
                        break
                    if drained():
                        break
                    for key, _ in selector.select(min(0.2, remaining)):
                        data = os.read(key.fd, 65536)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        buffer = buffers[key.data]
                        space = 8_000_000 - len(buffer)
                        buffer.extend(data[:space])
                        if len(data) > space:
                            termination = "output_limit"
                            break
                    if termination:
                        break
                if not termination:
                    # Waited for WITHOUT reaping: the leader stays a zombie until stop_group
                    # has signalled its group, so the group id is still this reviewer's when
                    # its descendants are stopped (a reaped id may be another process's).
                    if _exited_unreaped(child, max(0, timeout - (time.monotonic() - started))):
                        exited = True
                    else:
                        termination = "timeout"
            # Leaving supervision: the guard turns to noting INSIDE the try. Armed into the
            # `finally`, a cancel at a signal check there raised past the group kill, the reap
            # and the result. A cancel before this store raises here and is caught below; one
            # after it is noted. No signal block around it: a cancel raised just after the
            # block returned left the signals blocked for good.
            guard.armed = False
        except KeyboardInterrupt:
            # Cancelled: stop the group below and return what was captured, so the adapter
            # records the attempt (it may have been billed) and the dispatcher never fails over.
            # Not when the reviewer had already exited (seen by the non-reaping wait): that
            # review ran to its end, and the cancel is returned as noted, never as its
            # termination.
            # A cancel raised inside the wait, after the exit was seen but before it was
            # recorded here, is the same case: a non-reaping look settles it.
            # A look that fails is no exit seen: the cancel stands, never a run_failed.
            if child is not None and not exited and not termination:
                try:
                    exited = _exited_unreaped(child, 0)
                except OSError:
                    pass
            if termination or child is None or not exited:
                termination = "cancelled"
        except OSError as error:
            # The reviewer may already have emitted billed usage. Keep those bytes and
            # finish cleanup before returning this distinct execution failure.
            termination = "run_failed"
            buffers["stderr"].extend(("\n" + str(error)).encode())
        finally:
            # Already noting on every path through the try; this covers an unexpected error.
            guard.armed = False
            noted = guard.noted
            # Also stop descendants left behind by a parent that already exited.
            try:
                if child is not None:
                    try:
                        stop_group(child, child.pid)
                    finally:
                        try:
                            child.stdout.close()
                        finally:
                            child.stderr.close()
            finally:
                # A cleanup OSError also escapes run(). Hand the captured state to the
                # adapter before that happens, so its run_failed record keeps billed usage.
                if into is not None:
                    into.update(launched=child is not None, exit_code=child.returncode if child else None,
                                stdout=buffers['stdout'].decode(errors="replace"),
                                stderr=buffers['stderr'].decode(errors="replace"),
                                termination=termination, cancelled=bool(guard.noted),
                                duration_ms=round((time.monotonic() - started) * 1000))
    # Built after the with block: closing the prompt file and the selector runs with the
    # noting handler too, and a cancel noted there once left a launch failure 'unavailable',
    # an eligible failure that started the fallback reviewer.
    if noted and (termination or (child and child.returncode)):
        termination = "cancelled"
    # Cancellation is returned as its own fact, whatever the exit code: a zero exit is not
    # a completed review until the adapter has read the response (a Claude result with
    # is_error exits zero). The adapter keeps a completed review completed and turns a
    # failed one into a cancel, so the dispatcher never fails over.
    return {"launched": child is not None,
            "exit_code": child.returncode if child else 127 if launch_failed else None,
            "stdout": buffers['stdout'].decode(errors="replace"),
            "stderr": buffers['stderr'].decode(errors="replace"), "termination": termination,
            "cancelled": termination == "cancelled" or bool(noted),
            "duration_ms": round((time.monotonic() - started) * 1000)}
