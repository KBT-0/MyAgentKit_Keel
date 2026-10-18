#!/usr/bin/env python3
"""Local cross-model usage records and reporting; no inferred subscription percentages."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import tempfile


def require_private_storage(repo: Path, archive: Path | None = None) -> None:
    """Refuse model work when private output could be staged or is already tracked."""
    paths = [repo / '.myagentkit/usage', repo / '.myagentkit/backends']
    if archive is not None:
        paths.append(archive)
    for path in paths:
        if not path.resolve().is_relative_to(repo.resolve()):
            raise ValueError('private evidence must remain inside the repository')
        if path.resolve() != repo.resolve() / path.relative_to(repo):
            raise ValueError('private evidence must not follow symlinked storage')
        relative = path.relative_to(repo).as_posix()
        if path in paths[:2]:
            relative += '/'
        ignored = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--quiet', '--no-index',
                                  '--', relative], capture_output=True)
        if ignored.returncode != 0:
            raise ValueError('private evidence must be Git-ignored before review: ' + relative
                             + '; merge the ignore rules documented in docs/DEV_SETUP.md')
    # icase: Windows and macOS fold case, so `.MYAGENTKIT/Backends/x.env` is the same store; a
    # case-sensitive pathspec let a tracked credential through to the reviewer's prompt.
    tracked = subprocess.run(['git', '-C', str(repo), 'ls-files', '-z', '--',
                              *(':(icase)' + spec for spec in (
                                  '.myagentkit/usage', '.myagentkit/backends', 'docs/reviews/*-review.md',
                                  'docs/reviews/????????T??????Z-*.md',
                                  'docs/reviews/*-claude-review.json',
                                  'docs/handoffs/*-claude-propose.json')),
                              ':(exclude,icase)docs/reviews/*-summary.md'], capture_output=True)
    if tracked.returncode != 0:
        raise ValueError('Git could not verify private storage: '
                         + tracked.stderr.decode('utf-8', 'replace').strip())
    if tracked.stdout:
        # Named: a project that committed its review reports (the pre-v0.11 convention) saw only
        # "is tracked" and could not tell which records, or that it was a convention, not a leak.
        found = [p for p in tracked.stdout.decode('utf-8', 'surrogateescape').split('\0') if p]
        raise ValueError('private evidence is tracked (%d path(s): %s%s); untrack these records with '
                         '`git rm --cached` (the files stay on disk) or keep a final review as '
                         'docs/reviews/*-summary.md before review; see docs/DEV_SETUP.md'
                         % (len(found), ', '.join(found[:5]), ', ...' if len(found) > 5 else ''))


def write_evidence(repo: Path, path: Path, text: str, *, private: bool = False,
                   replace: bool = False) -> None:
    """Publish a complete, flushed archive exclusively; never replace prior evidence.

    `replace` is for relabel_cancelled() alone: the records this call has just published.
    """
    if not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError("evidence path must remain inside the repository")
    if private:
        require_private_storage(repo, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = repo / '.myagentkit/usage' if private else path.parent
    staging.mkdir(parents=True, exist_ok=True)
    # newline="": the bytes on disk are the text's own. Text mode on Windows wrote CRLF while
    # every record hashes the LF text, so each archive written there failed its own sha256.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=staging) as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
        if replace:
            # Staged beside the temporary file, in the storage verified ignored above: a
            # sibling `<archive>.cancel` matched no ignore rule, so a failure before the
            # replace left raw output for `git add -A`.
            pending = stream.name + ".replace"
            os.link(stream.name, pending)
            try:
                os.replace(pending, path)
            finally:
                if os.path.lexists(pending):
                    os.unlink(pending)
        else:
            os.link(stream.name, path)
        # The new name made durable. Windows opens no folder with os.open (PermissionError, which
        # failed every review there) and NTFS journals the name itself.
        if os.name != "nt":
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
                 "reference", "head", "fingerprint", "diff_sha256", "behaviour_sha256", "status", "failure_kind")
VERDICT_LINE = "VERDICT: "
REVIEW_VERDICTS = ("Accept", "Accept with Manual Checks", "Reject")
DISPOSITION_KEYS = ("fixed", "disproved", "deferred")


def dispositions(text: str) -> dict:
    """Count the author's answers to the earlier findings: one key per finding.

    `fixed:<commit>`, `disproved:<evidence>` or `deferred:<issue or decision>`, case-insensitive;
    one answer per line, so a key quoted inside an answer's evidence is not a second answer.
    These are the author's claims (the next round's reviewer verifies them), recorded so the
    usage summary can show each reviewer configuration's author-claimed acceptance rate.
    A file that answers no finding with a key is refused before any model is called. Other
    lines (a heading or a blank line excepted) are counted as `unkeyed`, only when there is one,
    so a record with none reads as before.
    """
    counts, unkeyed = dict.fromkeys(DISPOSITION_KEYS, 0), 0
    for line in text.splitlines():
        first = re.search(r"\b(%s):" % "|".join(DISPOSITION_KEYS), line, re.I)
        if first:
            counts[first[1].lower()] += 1
        elif line.strip() and not line.lstrip().startswith("#"):
            unkeyed += 1
    if unkeyed:
        counts["unkeyed"] = unkeyed
    if not any(counts[key] for key in DISPOSITION_KEYS):
        raise ValueError("REVIEW_DISPOSITIONS answers no finding: each finding needs a fixed:, "
                         "disproved: or deferred: key")
    return counts


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
    # body, so a reader (and the tests) can find it without parsing free text. Any copy
    # left in the body is therefore normalized here rather than in each adapter: a reviewer
    # whose prose still said "VERDICT: Accept" under a failed run would publish an approval
    # the run never earned, and one that repeated its verdict would break "exactly one".
    # Failed declarations are retained as explicitly unvalidated prose, never contract lines.
    lines = []
    for line in body.splitlines():
        if re.match(r'^[ \t]*VERDICT[ \t]*:', line):
            if verdict is None:
                lines.append('Unvalidated reviewer text: ' + line.strip())
        else:
            lines.append(line)
    body = '\n'.join(lines)
    # A substitute reviewer says so in its own record, not only in the dispatcher's output:
    # the evidence file is what a later reader opens, and it must not pass for the requested one.
    # A shadow run measures a reviewer configuration: its verdict is recorded, never counted.
    if os.environ.get("REVIEW_SHADOW") == "1":
        body = ("SHADOW REVIEW: this run measures a reviewer configuration; its verdict counts "
                "for no closure and the usage summary lists it apart.\n\n" + body)
    fallback = os.environ.get("MYAGENTKIT_REVIEW_FALLBACK_FROM")
    if fallback:
        why = ("the Codex quota was used up, so the role switched to Claude" if fallback.startswith("codex ")
               and fallback.endswith("(quota_exhausted)") else "--fallback was passed")
        body = ("FALLBACK REVIEWER: the requested reviewer " + fallback + " did not complete; "
                "this " + str(header["reviewer"]) + " review ran because " + why + ". "
                "Check that " + str(header["reviewer"]) + " did not author the patch.\n\n" + body)
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


# Error wording of the two quota kinds (KARARLAR D04 inv2#126), checked in this order: Codex says
# "try again in 3 days" under a used-up plan, which is no passing limit. USAGE.md lists the map.
# Claude Code's documented session, weekly and model-family plan limits are exhausted
# quotas (https://code.claude.com/docs/en/costs, "When a developer asks about a limit";
# checked 2026-10-17).
EXHAUSTED = ("quota", "usage limit", "session limit", "weekly limit", "opus limit", "sonnet limit",
             "spend", "billing", "credit", "on_hold", "on hold")
RATE_LIMITED = ("rate limit", "rate_limit", "429", "529", "overloaded", "at capacity", "too many requests")


def retry_after(values: list[dict]) -> float | None:
    """Seconds an error event says to wait ("try again in 30 seconds", "retry after 2m"), or None."""
    for value in values:
        if value.get("type") not in ("error", "turn.failed"):
            continue
        found = re.search(r"(?i)(?:try again|retry)(?: in| after)\s+(\d+(?:\.\d+)?)\s*"
                          r"(ms|s|secs?|seconds?|m|mins?|minutes?)\b", str(value.get("error", value.get("message", ""))))
        if found:
            number, unit = float(found[1]), found[2].lower()
            seconds = number / 1000 if unit == "ms" else number * 60 if unit.startswith("m") else number
            return int(seconds) if seconds == int(seconds) else seconds
    return None


def failure(provider: str, execution: dict, values: list[dict]) -> str | None:
    """Classify provider errors without searching review findings for error-like words."""
    if execution.get("termination"):
        return execution["termination"]
    if provider == 'claude' and execution.get('exit_code') == 0 and (
            len(values) != 1 or values[0].get('type') != 'result'
            or type(values[0].get('is_error')) is not bool
            or not isinstance(values[0].get('subtype'), str)
            or not values[0]['subtype']):
        return 'invalid_evidence'
    errors, limited = [], False
    for value in values:
        # 429 rate_limit_error and 529 overloaded_error (Anthropic API errors page).
        limited |= value.get("api_error_status") in (429, 529)
        if provider == "claude" and (value.get("is_error") or value.get("subtype") != "success"
                                     or value.get("api_error_status") in (429, 529)):
            errors.append(str(value.get("result", "")) + " " + str(value.get("subtype", "")))
        if provider == "codex" and value.get("type") in ("error", "turn.failed"):
            errors.append(str(value.get("error", value.get("message", ""))))
    text = " ".join(errors).lower()
    # KARARLAR D04 inv2#126: a quota that is used up for now (a plan or session limit, a spend
    # cap, billing, an account hold, credits) goes to the owner; a rate limit, an overload or a
    # model at capacity passes and is retried (B01 (6)). USAGE.md maps the vendors' names.
    if any(word in text for word in EXHAUSTED):
        return "quota_exhausted"
    if limited or any(word in text for word in RATE_LIMITED):
        return "rate_limited"
    if any(word in text for word in ("context", "token limit", "max_tokens")):
        return "context_limit"
    if any(word in text for word in ("max_turns", "budget")):
        return "budget_or_turn_limit"
    # A provider's content classifier stopping the turn is its own kind: the wording
    # ("authorized security work") would otherwise read as an authentication fault. A retry
    # with the same content may pass; a smaller scope usually does.
    if any(word in text for word in ("flagged for", "content policy", "safety system", "usage policies")):
        return "content_flagged"
    if any(word in text for word in ("auth", "login", "401", "403")):
        return "authentication"
    # A CLI that rejects a required flag fails identically on every run. It is a setup fault,
    # never availability, so it must not be routed around to another reviewer.
    stderr = str(execution.get("stderr", "")).lower()
    if execution.get("exit_code") != 0 and ("unknown option" in stderr or "unexpected argument" in stderr):
        return "cli_unsupported"
    # Claude Code's Bash sandbox could not start (bubblewrap or socat missing, WSL1): the same
    # setup fault on every run, and never a reason to run unsandboxed or to switch reviewer.
    if execution.get("exit_code") != 0 and "sandbox required but unavailable" in stderr:
        return "sandbox_unavailable"
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
           execution: dict, status: str, reason: str | None, evidence: str | None,
           published: bytes | None = None, backend: str | None = None) -> tuple[Path, dict]:
    """Write one exclusive local record, including failed and partially billed calls.

    `published` is the evidence exactly as archived. Hashing it here, never the archive
    reopened, keeps an archive lost in between from aborting the accounting of a paid run;
    that run is recorded as failed, evidence_unavailable, since no later round can carry it.
    """
    if evidence and published is None:
        raise ValueError("evidence needs the published bytes it is hashed from")
    if not isinstance(task.get("id"), str) or not task["id"]:
        raise ValueError("a usage record needs a task label; the history reader refuses one without")
    if evidence and not (os.path.isfile(evidence) and os.access(evidence, os.R_OK)):
        status, reason = "failed", "evidence_unavailable"
    values = decode(provider, execution.get("stdout", ""))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    recovery = {"action": "inspect_result" if status == "completed" else "continue_independent_work",
                "review_approved": False, "automatic_retry": False,
                "instruction": "Keep required review pending; do not approve, commit, or push its protected diff."}
    value = {"schema_version": 1, "invocation_id": stamp,
             "review_chain_id": os.environ.get("MYAGENTKIT_REVIEW_CHAIN_ID"),
             "review_attempt": os.environ.get("MYAGENTKIT_REVIEW_ATTEMPT"),
             "review_fallback_from": os.environ.get("MYAGENTKIT_REVIEW_FALLBACK_FROM"),
             "recorded_at": datetime.now(timezone.utc).isoformat(),
             "requester_reported": requester, "callee": provider, "model_requested": model,
             "task": task, "status": status, "failure_kind": reason,
             "duration_ms": execution.get("duration_ms"), "exit_code": execution.get("exit_code"),
             "usage": normalize(provider, values, status == "completed"), "recovery": recovery,
             "evidence": evidence,
             # A later round carries this archive only while its bytes still match.
             "evidence_sha256": hashlib.sha256(published).hexdigest() if evidence else None,
             "raw_stdout": execution.get("stdout", ""),
             "raw_stderr": execution.get("stderr", "")}
    if backend:  # Only then: a record without a backend stays as it was.
        value["backend"] = backend
    value["usage"]["account_quota_snapshots"] = execution.get("account_quota_snapshots")
    directory = repo / ".myagentkit/usage"
    if not directory.resolve().is_relative_to(repo.resolve()):
        raise ValueError("usage directory must remain inside the repository")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (stamp + ".json")
    write_evidence(repo, path, json.dumps(value, indent=2, allow_nan=False) + "\n", private=True)
    return path, value


def relabel_cancelled(repo: Path, usage_path: Path, evidence: str | None, text: str) -> dict:
    """Persist a cancel noted while the records were written: failed/cancelled in both.

    The usage reporter reads these records, and a direct adapter call has no chain to keep the
    cancel: once only the returned result said cancelled while both files still said quota.
    `text` is the archive re-rendered with the cancel; it replaces the one just published.
    The usage record is the authority and goes first, with the new archive's sha256: written
    second, a failure in between left the archive cancelled and the record quota. Now an
    archive left unreplaced fails that sha256, and the error says what the bytes show.
    Whether the archive exists at this moment is not asked: one absent when sampled kept the
    old sha256 and was not replaced, and the old archive put back later matched a record
    that said cancelled. A recorded archive always gets the new sha256 and is written anew.
    """
    value = json.loads(usage_path.read_text(encoding="utf-8"))
    archived = bool(evidence)
    if archived:
        value["evidence_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    value.update(status="failed", failure_kind="cancelled")
    value["recovery"]["action"] = "continue_independent_work"
    write_evidence(repo, usage_path, json.dumps(value, indent=2, allow_nan=False) + "\n",
                   private=True, replace=True)
    if archived:
        try:
            write_evidence(repo, Path(evidence), text, private=True, replace=True)
        except (OSError, ValueError) as error:
            # Say only what the bytes on disk show, never which step failed: the replacement
            # can land and a later directory fsync or staging cleanup still raise.
            try:
                current = hashlib.sha256(Path(evidence).read_bytes()).hexdigest()
            except OSError as unread:
                state = "could not be read (%s)" % unread
            else:
                state = ("matches the record (sha256 %s)" % current
                         if current == value["evidence_sha256"] else "does not match the record")
            raise OSError("the usage record says cancelled; the archive %s on disk %s; "
                          "the write reported: %s" % (evidence, state, error)) from error
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--task-id")
    args = parser.parse_args()
    rows = []
    for path in sorted((args.repo / ".myagentkit/usage").glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
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
    # A Windows pipe is cp1252 unless UTF-8 mode is on: a task label outside it raised.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    main()
