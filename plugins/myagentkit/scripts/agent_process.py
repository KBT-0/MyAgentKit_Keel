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


def run(command: list[str], prompt: str, repo: Path, timeout: int) -> dict:
    """Return exit status, partial output, and termination reason without retrying."""
    if not 1 <= timeout <= 3600:
        raise ValueError("timeout must be 1..3600 seconds")
    started = time.monotonic()
    previous = {}
    if threading.current_thread() is threading.main_thread():
        previous = {sig: signal.signal(sig, _cancel) for sig in CANCEL_SIGNALS}
    try:
        return _supervise(command, prompt, repo, timeout, started)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _supervise(command, prompt, repo, timeout, started):
    with tempfile.TemporaryFile() as inp, selectors.DefaultSelector() as selector:
        # A file gives even a slow-starting CLI the entire prompt and EOF. Repeated
        # communicate(input=None) after a short timeout can strand a partially written pipe.
        inp.write(prompt.encode())
        inp.seek(0)
        try:
            child = subprocess.Popen(command, cwd=repo, stdin=inp, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, start_new_session=True,
                                     env=dict(os.environ, MYAGENTKIT_DELEGATION_DEPTH="1"))
        except OSError as error:
            return {"exit_code": 127, "stdout": "", "stderr": str(error),
                    "termination": "unavailable", "duration_ms": 0}
        termination = None
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        try:
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
            # Also stop descendants left behind by a parent that already exited.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
            child.stdout.close()
            child.stderr.close()
        return {"exit_code": child.returncode, "stdout": buffers['stdout'].decode(errors="replace"),
                "stderr": buffers['stderr'].decode(errors="replace"), "termination": termination,
                "duration_ms": round((time.monotonic() - started) * 1000)}
