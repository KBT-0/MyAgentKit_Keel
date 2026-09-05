#!/usr/bin/env python3
"""Local cross-model usage records and reporting; no inferred subscription percentages."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import uuid
import tempfile


def write_evidence(repo: Path, path: Path, text: str) -> None:
    """Publish a complete, flushed archive exclusively; never replace prior evidence."""
    if not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError("evidence path must remain inside the repository")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent) as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
        os.link(stream.name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


# The ONE review-evidence format, published by every reviewer in every direction.
#
# The kit takes no position on which model authors and which reviews, so the records must
# stay comparable when the roles swap. That only holds if both adapters emit the same header
# fields in the same order and the same verdict contract — so the format lives here, once,
# and `report()` REFUSES a header that does not carry exactly these fields. A renderer that
# quietly accepted an adapter's own extra column is how two directions drift into two
# formats that no later reader can line up.
REVIEW_FIELDS = ("reviewer", "model", "model_attested", "effort", "sandbox", "limits", "scope",
                 "reference", "head", "fingerprint", "diff_sha256", "status", "failure_kind")
VERDICT_LINE = "VERDICT: "
REVIEW_VERDICTS = ("Accept", "Accept with Manual Checks", "Reject")


def report(stamp: str, header: dict, verdict: str | None, body: str) -> str:
    """Render review evidence. A failed run carries NO verdict line, never a default one."""
    if tuple(header) != REVIEW_FIELDS:
        raise ValueError("review evidence header must be exactly, in order: "
                         + ", ".join(REVIEW_FIELDS))
    if verdict is not None and verdict not in REVIEW_VERDICTS:
        raise ValueError("unknown verdict: " + str(verdict))
    if verdict is not None and header["status"] != "completed":
        raise ValueError("a verdict may only be published by a completed review")
    # The verdict is promoted OUT of the model's prose into the one contract line above the
    # body, so a reader (and the self-test) can find it without parsing free text. Any copy
    # left in the body is therefore stripped here rather than in each adapter: a reviewer
    # whose prose still said "VERDICT: Accept" under a failed run would publish an approval
    # the run never earned, and one that repeated its verdict would break "exactly one".
    body = "\n".join(line for line in body.splitlines() if not line.startswith(VERDICT_LINE))
    rows = "".join("| %s | %s |\n" % (key, "-" if header[key] in (None, "") else header[key])
                   for key in REVIEW_FIELDS)
    text = ("# Review — " + stamp + "\n\nThis is immutable evidence, not approval. The verdict is\n"
            "INPUT to the calling agent's own review decision, never an approval to relay.\n\n"
            "| field | value |\n| --- | --- |\n" + rows + "\n"
            + (VERDICT_LINE + verdict + "\n" if verdict
               else "NO VERDICT — this run failed before one was recorded. Failure is not Accept.\n")
            + "\n" + body.strip() + "\n")
    if text.count("\n" + VERDICT_LINE) != (1 if verdict else 0):
        raise ValueError("review evidence must carry exactly one verdict line, or none when it failed")
    return text


def number(value):
    """Return a finite nonnegative reported number, otherwise unknown."""
    return value if (isinstance(value, (int, float)) and not isinstance(value, bool)
                     and math.isfinite(value) and value >= 0) else None


def decode(provider: str, stdout: str) -> list[dict]:
    """Read only structured CLI output, never mine model prose for token counts."""
    chunks = [stdout] if provider == "claude" else stdout.splitlines()
    values = []
    for chunk in chunks:
        try:
            value = json.loads(chunk)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def failure(provider: str, execution: dict, values: list[dict]) -> str | None:
    """Classify provider errors without searching review findings for error-like words."""
    if execution.get("termination"):
        return execution["termination"]
    errors = []
    for value in values:
        if value.get("api_error_status") == 429:
            return "quota"
        if provider == "claude" and (value.get("is_error") or value.get("subtype") != "success"):
            errors.append(str(value.get("result", "")) + " " + str(value.get("subtype", "")))
        if provider == "codex" and value.get("type") in ("error", "turn.failed"):
            errors.append(str(value.get("error", value.get("message", ""))))
    text = " ".join(errors).lower()
    if any(word in text for word in ("quota", "rate limit", "usage limit", "session limit", "429")):
        return "quota"
    if any(word in text for word in ("context", "token limit", "max_tokens")):
        return "context_limit"
    if any(word in text for word in ("max_turns", "budget")):
        return "budget_or_turn_limit"
    if any(word in text for word in ("auth", "login", "401", "403")):
        return "authentication"
    return "cli_error" if errors or execution.get("exit_code") != 0 else None


def normalize(provider: str, values: list[dict], complete: bool) -> dict:
    """Keep source token semantics explicit; cache/reasoning are not additive totals."""
    reports = [v for v in values if v.get("type") == ("result" if provider == "claude" else "turn.completed")]
    raw = [v.get("usage") for v in reports if isinstance(v.get("usage"), dict)]
    keys = {"input_tokens": "input_tokens", "output_tokens": "output_tokens",
            "cache_read_tokens": "cache_read_input_tokens" if provider == "claude" else "cached_input_tokens",
            "cache_creation_tokens": "cache_creation_input_tokens",
            "reasoning_tokens": "reasoning_output_tokens"}
    usage = {"complete": complete, "input_includes_cache": provider == "codex"}
    for target, key in keys.items():
        samples = [number(item.get(key)) for item in raw]
        if target == "reasoning_tokens" and provider == "claude":
            samples = [number(item.get("output_tokens_details", {}).get("thinking_tokens"))
                       for item in raw if isinstance(item.get("output_tokens_details", {}), dict)]
        usage[target] = sum(samples) if samples and all(n is not None for n in samples) else None
    costs = [number(v.get("total_cost_usd")) for v in reports]
    usage["api_cost_usd_reported"] = sum(costs) if costs and all(n is not None for n in costs) else None
    usage.update(credits_used_reported=None, subscription_percent_consumed=None,
                 subscription_percent_reason="CLI output does not attest a per-call subscription delta",
                 usage_raw=raw,
                 model_usage_raw=[v["modelUsage"] for v in reports if isinstance(v.get("modelUsage"), dict)],
                 quota_snapshots_raw=[v["rate_limits"] for v in values if isinstance(v.get("rate_limits"), dict)])
    return usage


def record(repo: Path, provider: str, model: str, requester: str, task: dict,
           execution: dict, status: str, reason: str | None, evidence: str | None) -> tuple[Path, dict]:
    """Write one exclusive local record, including failed and partially billed calls."""
    values = decode(provider, execution.get("stdout", ""))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    recovery = {"action": "inspect_result" if status == "completed" else "continue_independent_work",
                "review_approved": False, "automatic_retry": False,
                "instruction": "Keep required review pending; do not approve, commit, or push its protected diff."}
    value = {"schema_version": 1, "invocation_id": stamp,
             "recorded_at": datetime.now(timezone.utc).isoformat(),
             "requester_reported": requester, "callee": provider, "model_requested": model,
             "task": task, "status": status, "failure_kind": reason,
             "duration_ms": execution.get("duration_ms"), "exit_code": execution.get("exit_code"),
             "usage": normalize(provider, values, status == "completed"), "recovery": recovery,
             "evidence": evidence, "raw_stdout": execution.get("stdout", ""),
             "raw_stderr": execution.get("stderr", "")}
    value["usage"]["account_quota_snapshots"] = execution.get("account_quota_snapshots")
    directory = repo / ".myagentkit/usage"
    if not directory.resolve().is_relative_to(repo.resolve()):
        raise ValueError("usage directory must remain inside the repository")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (stamp + ".json")
    write_evidence(repo, path, json.dumps(value, indent=2, allow_nan=False) + "\n")
    return path, value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--task-id")
    args = parser.parse_args()
    rows = []
    for path in sorted((args.repo / ".myagentkit/usage").glob("*.json")):
        value = json.loads(path.read_text())
        if args.task_id and value["task"].get("id") != args.task_id:
            continue
        rows.append({k: v for k, v in value.items() if not k.startswith("raw_")})
    if args.json:
        print(json.dumps(rows, indent=2))
    elif not rows:
        print("No recorded invocations. This does not mean zero historical usage.")
    else:
        for row in rows:
            u = row["usage"]
            print(f'{row["invocation_id"]} {row["task"].get("id")} '
                  f'{row["requester_reported"]} -> {row["callee"]}/{row["model_requested"]} '
                  f'{row["status"]}/{row["failure_kind"]} input={u["input_tokens"]} '
                  f'cache_read={u["cache_read_tokens"]} output={u["output_tokens"]} '
                  f'api_usd={u["api_cost_usd_reported"]} subscription%=unknown')
            snapshots = u.get("account_quota_snapshots") or {}
            for when in ("before", "after"):
                snapshot = snapshots.get(when) or {}
                for bucket, value in snapshot.get("buckets", {}).items():
                    for window in ("primary", "secondary"):
                        observed = value.get(window)
                        if observed:
                            print(f'  quota_{when} {bucket}/{window} plan={value.get("plan_type")} '
                                  f'used={observed["used_percent"]}% window={observed["window_minutes"]}m '
                                  '(account observation; not a per-call debit)')


if __name__ == "__main__":
    main()
