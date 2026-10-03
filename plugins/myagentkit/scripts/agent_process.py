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
# process without its cleanup and the paid reviewer keeps running, unaccounted.
CANCEL_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


def _cancel(signum, frame):
    raise KeyboardInterrupt


def hold(handler=_cancel) -> dict:
    """Route the cancel signals to `handler`; return the handlers to restore()."""
    if threading.current_thread() is not threading.main_thread():
        return {}
    # nohup ignores SIGHUP and a background job SIGINT; the caller chose that, keep it.
    return {sig: signal.signal(sig, handler) for sig in CANCEL_SIGNALS
            if signal.getsignal(sig) is not signal.SIG_IGN}


def restore(previous: dict) -> None:
    for sig, handler in previous.items():
        signal.signal(sig, handler)


def run(command: list[str], prompt: str, repo: Path, timeout: int) -> dict:
    """Return exit status, partial output, and termination reason without retrying."""
    if not 1 <= timeout <= 3600:
        raise ValueError("timeout must be 1..3600 seconds")
    started = time.monotonic()
    previous = hold()
    try:
        return _supervise(command, prompt, repo, timeout, started)
    finally:
        restore(previous)


def _supervise(command, prompt, repo, timeout, started):
    with tempfile.TemporaryFile() as inp, selectors.DefaultSelector() as selector:
        # A file gives even a slow-starting CLI the entire prompt and EOF. Repeated
        # communicate(input=None) after a short timeout can strand a partially written pipe.
        inp.write(prompt.encode())
        inp.seek(0)
        child = termination = None
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        try:
            try:
                # Blocked across Popen: a cancel after the child existed but before Popen
                # returned left no handle, and the group ran on. The child unblocks before
                # exec; here a pending cancel is raised on unblock, with the handle kept.
                mask = signal.pthread_sigmask(signal.SIG_BLOCK, CANCEL_SIGNALS)
                try:
                    child = subprocess.Popen(command, cwd=repo, stdin=inp, stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, start_new_session=True,
                                             env=dict(os.environ, MYAGENTKIT_DELEGATION_DEPTH="1"),
                                             preexec_fn=lambda: signal.pthread_sigmask(signal.SIG_SETMASK, mask))
                finally:
                    signal.pthread_sigmask(signal.SIG_SETMASK, mask)
            except OSError as error:
                return {"exit_code": 127, "stdout": "", "stderr": str(error),
                        "termination": "unavailable", "duration_ms": 0}
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
        except KeyboardInterrupt:
            # Cancelled: stop the group below and return what was captured, so the adapter
            # records the attempt (it may have been billed) and the dispatcher never fails over.
            termination = "cancelled"
        finally:
            # From here a cancel is noted, not raised: raised, it broke off the group kill or
            # the reap, and run() returned nothing to record. run() restores the handlers.
            noted = []
            hold(lambda signum, frame: noted.append(signum))
            # Also stop descendants left behind by a parent that already exited.
            if child is not None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
                child.stdout.close()
                child.stderr.close()
            # As in the adapters: a failed attempt that was cancelled is cancelled, so the
            # dispatcher never fails over; a completed one keeps its paid result.
            if noted and (termination or (child and child.returncode)):
                termination = "cancelled"
        return {"exit_code": child.returncode if child else None, "stdout": buffers['stdout'].decode(errors="replace"),
                "stderr": buffers['stderr'].decode(errors="replace"), "termination": termination,
                "duration_ms": round((time.monotonic() - started) * 1000)}
