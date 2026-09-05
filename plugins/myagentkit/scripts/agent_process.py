"""Bounded child execution shared by both CLI adapters; preserve partial diagnostics."""
import os
from pathlib import Path
import signal
import selectors
import subprocess
import tempfile
import time


def run(command: list[str], prompt: str, repo: Path, timeout: int) -> dict:
    """Return exit status, partial output, and termination reason without retrying."""
    if not 1 <= timeout <= 3600:
        raise ValueError("timeout must be 1..3600 seconds")
    started = time.monotonic()
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
        for name, stream in (("stdout", child.stdout), ("stderr", child.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        try:
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
