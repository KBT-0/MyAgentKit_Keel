"""Read an account quota snapshot through the existing Codex CLI, without starting a turn."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time


def sanitize(result):
    """Retain quota/plan fields only, never login tokens or account identity."""
    buckets = result.get("rateLimitsByLimitId")
    if not isinstance(buckets, dict) or not buckets:
        single = result.get("rateLimits")
        buckets = {single.get("limitId", "codex"): single} if isinstance(single, dict) else {}
    safe = {}
    for key, value in buckets.items():
        if not isinstance(value, dict):
            continue
        plan = value.get("planType")
        item = {"plan_type": plan if isinstance(plan, str) else None, "primary": None, "secondary": None}
        for window in ("primary", "secondary"):
            raw = value.get(window)
            if not isinstance(raw, dict):
                continue
            percent = raw.get("usedPercent")
            if (isinstance(percent, (int, float)) and not isinstance(percent, bool)
                    and math.isfinite(percent) and 0 <= percent <= 100):
                minutes, resets = raw.get("windowDurationMins"), raw.get("resetsAt")
                item[window] = {"used_percent": percent,
                                "window_minutes": minutes if type(minutes) is int and minutes > 0 else None,
                                "resets_at": resets if type(resets) is int and resets >= 0 else None}
        safe[str(key)] = item
    return safe


def snapshot(cli: str, repo: Path, timeout: float = 5) -> dict:
    """Optional telemetry may fail; it must not block or authorize model work."""
    observed = datetime.now(timezone.utc).isoformat()
    proc = None
    try:
        deadline = time.monotonic() + timeout
        proc = subprocess.Popen([cli, "app-server", "--stdio"], cwd=repo,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, start_new_session=True)
        def send(value):
            proc.stdin.write((json.dumps(value) + "\n").encode())
            proc.stdin.flush()
        send({"method": "initialize", "id": 1,
              "params": {"clientInfo": {"name": "myagentkit-usage", "version": "0.1.0"}}})
        buffer = b""
        total = 0
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                if not selector.select(max(0, deadline - time.monotonic())):
                    break
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk:
                    raise ValueError("quota reader exited without its response")
                buffer += chunk
                total += len(chunk)
                if total > 1_000_000:
                    raise ValueError("quota response exceeds capture limit")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        continue
                    if value.get("id") not in (1, 2):
                        continue
                    if "error" in value:
                        raise ValueError("quota endpoint unavailable: " + str(value["error"]))
                    if value["id"] == 1:
                        send({"method": "initialized", "params": {}})
                        send({"method": "account/rateLimits/read", "id": 2})
                    elif isinstance(value.get("result"), dict):
                        buckets = sanitize(value["result"])
                        return {"status": "available" if buckets else "unavailable",
                                "observed_at": observed, "buckets": buckets,
                                "source": "codex account/rateLimits/read"}
            raise ValueError("quota snapshot timed out")
    except (OSError, ValueError) as error:
        return {"status": "unavailable", "observed_at": observed, "error": str(error), "buckets": {}}
    finally:
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            proc.stdin.close()
            proc.stdout.close()


if __name__ == "__main__":
    print(json.dumps(snapshot(os.environ.get("REVIEW_CLI_BIN", "codex"), Path.cwd()), indent=2))
