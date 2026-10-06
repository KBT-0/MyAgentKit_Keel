"""Bounded child execution shared by both CLI adapters; preserve partial diagnostics."""
import os
from pathlib import Path
import signal
import selectors
import subprocess
import tempfile
import threading
import time

DEFAULT_REVIEW_TIMEOUT = 1800
# Ctrl-C, kill and a closed terminal or restarted host session. The reviewer runs in its own
# session so none of these reach it; left at their defaults, SIGTERM and SIGHUP end this
# process without its cleanup and the paid reviewer keeps running, unaccounted. Native Windows
# Python has no SIGHUP: the tuple holds the ones that exist, and the import never fails there.
CANCEL_SIGNALS = tuple(getattr(signal, name) for name in ("SIGINT", "SIGTERM", "SIGHUP")
                       if hasattr(signal, name))
# The platform seam: every launch, signal block and group kill of the review tooling goes
# through the five functions below (test_claude_bridge checks that no other place makes one).
# Off POSIX (native Windows Python) there is no signal mask, no session and no killpg: the
# blocks are no-ops, a child gets a process group of its own, and taskkill stops its tree.
POSIX = os.name == "posix"


def block_cancels():
    """Block the cancel signals; return the previous mask for restore_mask(). None off POSIX."""
    return signal.pthread_sigmask(signal.SIG_BLOCK, CANCEL_SIGNALS) if POSIX else None


def restore_mask(mask) -> None:
    if POSIX:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)


def pending() -> set:
    """The signals pending while blocked; none off POSIX, where nothing is blocked."""
    return signal.sigpending() if POSIX else set()


def launch(command, mask, **popen_kw) -> subprocess.Popen:
    """Popen in a group of its own. Called with the cancels blocked (`mask` is what
    block_cancels() returned): on POSIX the child restores `mask` before exec."""
    if POSIX:
        return subprocess.Popen(command, start_new_session=True,
                                preexec_fn=lambda: restore_mask(mask), **popen_kw)
    return subprocess.Popen(command, **popen_kw,
                            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200))


def stop_group(child, pgid) -> None:
    """Kill `child`'s group (or, off POSIX, its process tree) and reap the leader.

    POSIX: the leader may have exited while a descendant still holds a pipe open. On macOS a
    group whose leader is a zombie answers EPERM: the leader is then signalled by its pid, and
    the group again once it is reaped. Windows: `taskkill /T /F` stops the tree it can still
    find from the leader; child.kill() when taskkill is missing or fails.
    """
    if POSIX:
        # The leader's pid is signalled only while it is ours (not yet reaped): a reaped
        # pid may already be another process.
        for target, group in ((pgid, True), (child.pid, False), (pgid, True)):
            if not group and child.returncode is not None:
                continue
            try:
                if group:
                    os.killpg(target, signal.SIGKILL)
                else:
                    os.kill(target, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            if not group:
                child.wait()
    else:
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
    cancel that is new since the last sample, and the block is lifted right after a sample
    that found none, with nothing in between.
    """
    mask = block_cancels()
    try:
        restore(previous)
        seen = None
        while True:
            held = pending() & set(previous)
            if seen is not None and held <= seen:
                break
            seen = held
            settle(held)
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
            for sig in sorted(pending() & set(self.previous)):
                self.noted.append(signal.sigwait({sig}))
        finally:
            restore_mask(mask)


def run(command: list[str], prompt: str, repo: Path, timeout: float, into: dict | None = None,
        noted: list | None = None) -> dict:
    """Return exit status, partial output, and termination reason within a fractional seconds budget.

    `into` receives the result before the caller's handlers are restored: a raising one
    restored there raised before the returned result was assigned, and the attempt was lost.
    `noted` is the caller's own list of cancels its noting handler saw before this guard was
    up: one there stops the launch, as a cancel during the run stops the reviewer.
    """
    if not 0 < timeout <= 3600:
        raise ValueError("timeout must be greater than zero and at most 3600 seconds")
    started = time.monotonic()
    result = {} if into is None else into
    guard = OneShot()
    try:
        with guard:
            result.update(_supervise(command, prompt, repo, timeout, started, guard, noted))
            return result
    finally:
        # Noted while the handlers were restored: still a cancel.
        if result and guard.noted:
            result["cancelled"] = True


def _supervise(command, prompt, repo, timeout, started, guard, prior=None):
    with tempfile.TemporaryFile() as inp, selectors.DefaultSelector() as selector:
        # A file gives even a slow-starting CLI the entire prompt and EOF. Repeated
        # communicate(input=None) after a short timeout can strand a partially written pipe.
        inp.write(prompt.encode())
        inp.seek(0)
        child = termination = None
        launch_failed = False
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
                    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")
                           and k not in ("OLDPWD", "REVIEW_REPO_ROOT", "CLAUDE_PROJECT_DIR",
                                         "REVIEW_DISPOSITIONS")}
                    # The reviewer's git never discovers a repository above its working
                    # directory: a copy made inside some checkout stays inside the copy.
                    env["GIT_CEILING_DIRECTORIES"] = str(repo.parent)
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
                for name, stream in (("stdout", child.stdout), ("stderr", child.stderr)):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, name)
                while selector.get_map():
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        termination = "timeout"
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
                    try:
                        child.wait(timeout=max(0, timeout - (time.monotonic() - started)))
                    except subprocess.TimeoutExpired:
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
            # Not when wait() had already reaped the reviewer: that review ran to its end, and
            # the cancel is returned as noted, never as its termination.
            if termination or child is None or child.returncode is None:
                termination = "cancelled"
        finally:
            # Already noting on every path through the try; this covers an unexpected error.
            guard.armed = False
            noted = guard.noted
            # Also stop descendants left behind by a parent that already exited.
            if child is not None:
                stop_group(child, child.pid)
                child.stdout.close()
                child.stderr.close()
    # Built after the with block: closing the prompt file and the selector runs with the
    # noting handler too, and a cancel noted there once left a launch failure 'unavailable',
    # an eligible failure that started the fallback reviewer.
    if noted and (termination or (child and child.returncode)):
        termination = "cancelled"
    # Cancellation is returned as its own fact, whatever the exit code: a zero exit is not
    # a completed review until the adapter has read the response (a Claude result with
    # is_error exits zero). The adapter keeps a completed review completed and turns a
    # failed one into a cancel, so the dispatcher never fails over.
    return {"exit_code": child.returncode if child else 127 if launch_failed else None,
            "stdout": buffers['stdout'].decode(errors="replace"),
            "stderr": buffers['stderr'].decode(errors="replace"), "termination": termination,
            "cancelled": termination == "cancelled" or bool(noted),
            "duration_ms": round((time.monotonic() - started) * 1000)}
