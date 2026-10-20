#!/usr/bin/env python3
"""Collect bounded Codex review evidence before recording completion and usage."""
import argparse
from datetime import datetime, timezone
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
import agent_process
import agent_usage
import codex_quota
from claude_bridge import (REVIEW_DOCS, REVIEW_PROMPT, REVIEW_RUNS,
                           BridgeError, accept_allows, allow_secret_files, default_effort, git, placeholder,
                           prior_rounds, stricter_verdict,
                           review_context, review_parts, recheck, scratch, snapshot, throwaway_copy, review_tmpdir,
                           utf8_output)


VERDICT = r"^VERDICT: (Accept|Accept with Manual Checks|Reject)[ \t]*$"


def verdict_refused(final):
    """True when Codex's final text is no valid verdict: not exactly one VERDICT line, or a
    verdict its findings and manual checks contradict. The same rules as claude_bridge.validate():
    a plain Accept carries Lows and items outside the diff at most and no manual check; the other
    Accept names one; a Reject names a finding (fix4 notes)."""
    verdicts = re.findall(VERDICT, final, re.M)
    if len(verdicts) != 1 or len(re.findall(r"^[ \t]*VERDICT[ \t]*:.*$", final, re.M)) != 1:
        return True
    findings, checks = review_parts(final)
    return bool(verdicts[0] == 'Accept' and (checks or not accept_allows(findings))
                or verdicts[0] == 'Accept with Manual Checks' and not checks
                or verdicts[0] == 'Reject' and all(placeholder(f) for f in findings))


def corrected(final):
    """Codex's final text with a contradicted Accept read as the stricter verdict, as
    claude_bridge.validate() does (owner decision 59, #120): the VERDICT line names it and a
    Manual checks section, first line the correction, carries what moved. Any other text is
    returned as it is, for verdict_refused() to judge."""
    if re.findall(VERDICT, final, re.M) != ["Accept"] or not verdict_refused(final):
        return final
    findings, checks = review_parts(final)
    blocking = [item for item in findings if not accept_allows([item])]
    verdict, note = stricter_verdict(blocking)
    moved = [] if verdict == "Reject" else blocking
    final = re.sub(VERDICT, "VERDICT: " + verdict, final, flags=re.M)
    return final.rstrip("\n") + "\n\n## Manual checks\n\n" + "".join("- %s\n" % item for item in [note] + moved)


def main(argv=None, result_sink=None, claims=None):
    """`claims`: the dispositions text the dispatcher read once; None reads REVIEW_DISPOSITIONS."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--effort", choices=("low", "medium", "high"), default=default_effort())  # no xhigh for a review
    scopes = parser.add_mutually_exclusive_group()
    scopes.add_argument("--uncommitted", action="store_true")
    scopes.add_argument("--base")
    scopes.add_argument("--commit")
    parser.add_argument("--allow-secret-file", action="append", default=[])
    args = parser.parse_args(argv)
    allow_secret_files(args.allow_secret_file)
    if os.environ.get("MYAGENTKIT_DELEGATION_DEPTH", "0") != "0":
        raise ValueError("nested delegation is disabled")
    # The wrapper already refuses an empty pin; this repeats the refusal because the adapter
    # is directly callable, and an unpinned run is a record that names no comparable model.
    if not args.model.strip() or any(c.isspace() for c in args.model):
        raise ValueError("--model must pin one model id; Codex attests none in its output")
    # KARARLAR B03 inv2#31: a high-effort Codex review ran 37-58 minutes (RL 2026-10-13).
    default = agent_process.MAX_REVIEW_TIMEOUT if args.effort == "high" else agent_process.DEFAULT_REVIEW_TIMEOUT
    timeout = int(os.environ.get("REVIEW_TIMEOUT_SECONDS", str(default)))
    if not 1 <= timeout <= agent_process.MAX_REVIEW_TIMEOUT:
        raise ValueError("REVIEW_TIMEOUT_SECONDS must be 1..%d" % agent_process.MAX_REVIEW_TIMEOUT)
    repo = args.repo.resolve(strict=True)
    if Path(os.fsdecode(git(repo, "rev-parse", "--show-toplevel")).strip()).resolve() != repo:
        raise ValueError("--repo must name the repository root")
    scope, ref = ("base", args.base) if args.base else (("commit", args.commit) if args.commit else ("uncommitted", None))
    # resolved is captured with the snapshot: the usage record names what was reviewed even
    # when the reference is deleted or moved before the review ends.
    head, fingerprint, diff, resolved = snapshot(repo, scope, ref)
    if not diff.strip():
        raise ValueError("empty diff: nothing was reviewed")
    docs = os.environ.get("REVIEW_DOCS", ", ".join(REVIEW_DOCS))
    for name in re.split(r",\s*|\s+and\s+", docs):
        if not (repo / name).is_file() or not (repo / name).resolve().is_relative_to(repo):
            raise ValueError("required project guidance is missing or outside repository: " + name)
    carried, measured = prior_rounds(repo, os.environ.get("MYAGENTKIT_TASK_ID"), scope, resolved, head,
                                     diff, claims)
    prompt = (
        REVIEW_PROMPT % docs + REVIEW_RUNS + " Write exactly one "
        "line: VERDICT: Accept / VERDICT: Accept with Manual Checks / VERDICT: Reject "
        "(choose one). Put the findings under a '## Findings' heading, one '- ' list item per "
        "finding that starts with its severity, and the explicit manual checks under a "
        "'## Manual checks' heading at the end of the response, as full sentences. With no finding, write the one item "
        "'- None.' under '## Findings'.\n"
        + carried
        + review_context()
        + f"Scope: {scope} {ref or ''}; HEAD: {head}\nDiff:\n{diff}"
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    report = repo / "docs/reviews" / (stamp + "-codex-review.md")
    agent_usage.require_private_storage(repo, report)
    report.parent.mkdir(parents=True, exist_ok=True)
    # Held from here to the last line printed: with the default handlers back after the
    # review, a cancel during the closing quota read ended the adapter before a paid,
    # completed review was recorded, and one while the result printed (a blocked stdout)
    # ended it before the dispatcher's checkpoint. A cancel ends that read, and only that
    # read: the first one raises, every later one is noted.
    guard = agent_process.OneShot()
    guard.previous = agent_process.hold(guard)
    result = unverified = None
    deadline = time.monotonic() + timeout
    try:
        # The reviewer's workspace is a throwaway copy inside this directory, removed with it
        # on every way out (threat model: claude_bridge.throwaway_copy). Its sandbox confines
        # writes to the copy and the temporary directories and keeps the network off.
        with contextlib.ExitStack() as copies:
            last = None
            prepared = None
            try:
                review_tmpdir(repo)
                tmp = copies.enter_context(scratch("myagentkit-codex-"))
                last = Path(tmp) / "final.txt"
                workdir = Path(tmp) / "copy"
                workdir.mkdir()
                throwaway_copy(repo, head, diff if scope == "uncommitted" else None, workdir,
                               deadline=deadline)
            except (BridgeError, OSError) as error:
                # A preparation that used up the deadline is recorded as a timeout; a copy that
                # could not be made, as copy_failed (never a fallback): it once ended the
                # adapter with exit 2 and no record.
                prepared = {"exit_code": None, "stdout": "", "stderr": str(error),
                            "termination": "timeout" if time.monotonic() >= deadline else "copy_failed",
                            "cancelled": False, "duration_ms": 0}
            command = [os.environ.get("REVIEW_CLI_BIN", "codex"), "exec", "--json", "--ephemeral",
                       "-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=false",
                       "--skip-git-repo-check", "-c", "model_reasoning_effort=" + args.effort,
                       "-c", "approval_policy=never", "-o", str(last), "-m", args.model,
                       # #117: the copy's AGENTS.md is evidence the prompt names (REVIEW_DOCS), not
                       # instructions; 0 bytes loads no project doc (openai/codex agents_md.rs).
                       "-c", "project_doc_max_bytes=0", "-"]
            capture_quota = os.environ.get("MYAGENTKIT_CAPTURE_QUOTA", "1") == "1"
            def quota_read():
                # Optional telemetry: ANY error of the read is "unavailable". Raised, one after
                # the review (BrokenPipeError from a reader that exited at once) left a
                # completed, paid review with no evidence and no usage record. A cancel is not
                # an Exception and still ends the read.
                try:
                    return codex_quota.snapshot(command[0], repo)
                except Exception as error:
                    return {"status": "unavailable", "error": "quota read failed: %r" % error,
                            "buckets": {}}

            before = quota_read() if capture_quota else {"status": "disabled"}
            execution = None
            cancelled = []
            # run() fills this before it restores the raising handler held above: a cancel
            # during that restore raised before the return value was assigned.
            handed = {}
            try:
                remaining = deadline - time.monotonic()
                if prepared is None and remaining <= 0:
                    prepared = {"exit_code": None, "stdout": "", "stderr": "the review wall-clock limit passed during preparation", "termination": "timeout",
                             "cancelled": False, "duration_ms": 0}
                started = time.monotonic()

                def changed():
                    # A look during the review (#118). One that cannot read the checkout proves
                    # no change: the check after the review decides.
                    try:
                        now = recheck(repo, scope, ref)
                        return now is None or now[1] != fingerprint
                    except (OSError, ValueError, BridgeError):
                        return False
                try:
                    execution = prepared or agent_process.run(command, prompt, workdir, remaining, into=handed,
                                                              watch=changed)
                except OSError as error:
                    execution = dict(handed) if handed else {
                        "exit_code": None, "stdout": "", "stderr": "", "cancelled": False,
                        "duration_ms": round((time.monotonic() - started) * 1000)}
                    execution.update(termination="run_failed",
                                     stderr=execution["stderr"] + "\n" + str(error))
                if execution.pop("cancelled", False):
                    cancelled.append(True)
                # A cancelled review must stop now, not start another CLI process to read quota.
                after = ({"status": "disabled"} if not capture_quota else
                         {"status": "skipped: review cancelled"} if cancelled
                         else quota_read())
                # From here to the record a cancel is noted, not acted on: the record is what
                # it would lose. A flag set inside the try, not a second hold(): a cancel while
                # that one installed its handlers met the raising one, and the review was lost
                # unrecorded. A cancel before the flag is caught below.
                guard.armed = False
            except KeyboardInterrupt:
                guard.armed = False
                execution = execution or handed or None
                if execution is None:
                    raise
                execution.pop("cancelled", None)
                after = {"status": "cancelled"}
                cancelled.append(True)
            execution["account_quota_snapshots"] = {"before": before, "after": after,
                                                   "per_call_attribution": "unproven"}
            values = agent_usage.decode("codex", execution["stdout"])
            reason = agent_usage.failure("codex", execution, values)
            # Exit 0 and a turn that completed and did not fail: an error event in the stream is
            # one the CLI recovered from (a reconnect), kept in the usage record's raw output.
            # It once failed a paid, completed review as cli_error. A check below that fails keeps
            # its own kind: put back, a recovered 429 turned invalid_evidence into rate_limited
            # and the dispatcher re-ran the review (#180).
            types = [value.get("type") for value in values]
            if (reason and execution["exit_code"] == 0 and not execution["termination"]
                    and "turn.completed" in types and "turn.failed" not in types):
                reason = None
            # Only a run that failed on Codex's side names its events: a recovered reconnect
            # must not be blamed for a check below that fails.
            codex_failed = bool(reason)
            final = ""
            try:
                if last is not None and last.is_file():
                    with last.open("rb") as stream:
                        raw = stream.read(8_000_001)
                    if len(raw) > 8_000_000:
                        reason = reason or "output_limit"
                    final = raw[:8_000_000].decode(errors="replace")
                try:
                    now = recheck(repo, scope, ref)
                    changed = now is None or now[1] != fingerprint
                except (OSError, ValueError, BridgeError) as error:
                    # Unreadable proves no change: the review stays completed in its record, so
                    # its round counts (fail closed), and the result fails as checkout_unverified.
                    changed, unverified = False, "the checkout could not be read after the review: %s" % error
                if changed:
                    reason = reason or "stale_checkout"
            except (OSError, ValueError, BridgeError):
                reason = reason or "stale_checkout"
            # The adapter's diagnostic, kept out of the reviewer's text, and only its tail: the
            # usage record keeps the whole stderr.
            failure = ("\n\n## Failure\n\n" + ("Codex ran, then its supervision failed: " if execution.get("launched")
                       else "Codex did not start: ") + execution["stderr"][-4000:]
                       if reason == "run_failed" else
                       # As Claude's evidence says why its copy failed: without it the wrapper
                       # printed copy_failed and no reason.
                       "\n\n## Failure\n\nCodex never ran: " + execution["stderr"][-4000:]
                       if reason == "copy_failed" else "")
            final = corrected(final)
            verdicts = re.findall(VERDICT, final, re.M)
            if not reason and (verdict_refused(final)
                               or not any(v.get("type") == "turn.completed" for v in values)):
                reason = "invalid_evidence"
            # A failed attempt that was cancelled is cancelled: its eligible failure once let
            # --fallback launch the other paid reviewer after the owner had stopped the review.
            if (cancelled or guard.noted) and reason:
                reason = "cancelled"
            # #292: a refused model or any other turn.failed/error event left its reason only in
            # the usage record's raw stdout; the evidence said "No final message".
            reported = [str(v["error"].get("message", "")) if isinstance(v.get("error"), dict)
                        else str(v.get("message", "")) for v in values
                        if v.get("type") in ("error", "turn.failed")]
            if codex_failed and reason and not failure and any(reported):
                failure = "\n\n## Failure\n\nCodex reported: " + "\n".join(filter(None, reported))[-4000:]
        status = "failed" if reason else "completed"
        # The exec JSONL interface does not attest actual model identity; App Server's
        # `model/rerouted` is a different interface (KARARLAR B03 inv2#119;
        # https://learn.chatgpt.com/docs/non-interactive-mode and
        # https://learn.chatgpt.com/docs/app-server, stage-2 evidence checked 2026-10-15).
        # Codex publishes no model identity in its JSON output, so the pin is recorded as
        # requested-not-attested. Saying which it is beats a record that implies verification
        # the CLI never performed. Claude's adapter attests the same field from modelUsage.
        header = {"reviewer": "codex", "model": args.model, "model_attested": "no (Codex reports "
                  "no model identity; this is the requested pin)", "effort": args.effort,
                  "sandbox": "workspace-write (throwaway copy)", "limits": str(timeout) + "s wall clock", "scope": scope, "reference": ref, "head": head,
                  "fingerprint": fingerprint,
                  "diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
                  "behaviour_sha256": None,
                  "status": status, "failure_kind": reason}
        metadata = dict(header)
        report_text = agent_usage.report(stamp, header, verdicts[0] if status == "completed" else None,
            final + failure or "No final message. Inspect the local usage record for diagnostics.")
        archived = None
        try:
            agent_usage.write_evidence(repo, report, report_text, private=True)
            archived = str(report)
        except (OSError, ValueError) as error:
            status, reason = "failed", "evidence_write_failed"
            print("FAIL [review]: could not archive evidence: " + str(error))
        path, usage = agent_usage.record(repo, "codex", metadata["model"],
            os.environ.get("MYAGENTKIT_REQUESTER", "claude/unknown" if os.environ.get("CLAUDECODE") == "1" else "unspecified"),
            # An empty label is no label: recorded as "", every later labelled round refused it.
            {"id": os.environ.get("MYAGENTKIT_TASK_ID") or "review-" + scope, "kind": "review",
             "scope": scope, "reference": ref, "resolved": resolved, "head": head,
             "fingerprint": fingerprint,
             "diff_sha256": metadata["diff_sha256"],
             "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), **measured},
            execution, status, reason, archived, report_text.encode())
        def persist_cancel(usage):
            header.update(status="failed", failure_kind="cancelled")
            text = agent_usage.report(stamp, header, None,
                final + failure or "No final message. Inspect the local usage record for diagnostics.")
            try:
                return agent_usage.relabel_cancelled(repo, path, archived, text), text
            except (OSError, ValueError) as error:
                # Still a cancel, delivered as one: raising here lost the structured result.
                print("FAIL [review]: cancellation could not be persisted: " + str(error))
                return dict(usage, status="failed", failure_kind="cancelled"), text

        def cancel_noted():
            return bool(cancelled or guard.noted) or execution["termination"] == "cancelled"

        def reconcile():
            # A cancel noted during either write is persisted too, not only returned: the usage
            # reporter reads the records, and a direct call has no chain to keep it. Decided by
            # the record on disk, never by the returned flag: the two were separate samples, and
            # a cancel between them returned cancelled while both files kept quota. Idempotent,
            # so it runs at every sample and once more at the very end.
            nonlocal usage, report_text
            if not cancel_noted() or not usage["failure_kind"]:
                return
            try:
                if json.loads(path.read_text(encoding="utf-8")).get("failure_kind") == "cancelled":
                    return
            except (OSError, ValueError):
                pass
            usage, report_text = persist_cancel(usage)

        # The handler kept noting signals through both writes above: a cancel there is a cancel
        # too, or a quota-failed attempt stayed eligible and --fallback started another reviewer.
        # Sampled before the records are reconciled, so a cancel the flag saw is on disk.
        was_cancelled = cancel_noted()
        reconcile()
        status, reason = usage["status"], usage["failure_kind"]
        if unverified and status == "completed":
            status, reason = "failed", "checkout_unverified"
        result = {"status": status, "failure_kind": reason, "evidence": archived,
                  "usage_record": str(path), "recovery": usage["recovery"], "cancelled": was_cancelled}
        if reason == "checkout_unverified":
            result["error"] = unverified
        if reason == "rate_limited":
            # The wait the CLI named, for the dispatcher's capacity retry (KARARLAR B01 (6)).
            result["retry_after"] = agent_usage.retry_after(values)
        if result_sink is not None:
            result_sink(result)
        try:
            print("review invocation: " + json.dumps(result))
            # Not a report the accounting contradicted: a lost archive once printed its Accept.
            if archived and status == header["status"]:
                print(report_text)
            if reason:
                print("FAIL [review]: " + reason)
            sys.stdout.flush()  # Catch buffered pipe failures before shutdown can replace the exit with 120.
        except (OSError, ValueError) as error:
            # Recorded and handed over: a failure printing it keeps the result's exit code. The
            # dispatcher, holding this same dict, records the failure with the attempt.
            result["error_after_result"] = str(error)
            try:
                sys.stdout.flush()
            except (OSError, ValueError):
                sys.stdout = open(os.devnull, "w")
            with contextlib.suppress(OSError, ValueError):
                note = ("its %s result is recorded in %s" % (result["status"], archived)
                        if archived else "its %s result has no archive; evidence was not written" % result["status"])
                print("NOTE [review]: codex failed after it handed over its result (%s); %s"
                      % (error, note), file=sys.stderr, flush=True)
        return 5 if reason else 0
    finally:
        # A cancel noted while the result printed, or held while the caller's handlers went
        # back, is persisted and printed as a correction line; the dispatcher holds the same
        # result dict. A first cancel noted during the restore and a second one meeting the
        # caller's SIGTERM default once ended the adapter before the records said cancelled.
        def correct():
            if result is None:
                return
            cancelled.append(True)
            reconcile()
            if result["cancelled"]:
                return
            result["cancelled"] = True
            if usage["failure_kind"]:  # a checkout_unverified result has a completed record
                result.update(status=usage["status"], failure_kind="cancelled")
            print("review invocation: " + json.dumps(dict(result, correction=True)))

        if guard.noted:
            correct()
        def settle(pending):
            if pending or guard.noted:
                correct()
            elif result is not None:
                reconcile()

        agent_process.handing_back(guard.previous, settle)


if __name__ == "__main__":
    utf8_output()
    try:
        raise SystemExit(main())
    except (OSError, ValueError, BridgeError, subprocess.SubprocessError) as error:
        print("FAIL [review]: " + json.dumps({"status": "failed", "error": str(error),
              "recovery": {"action": "continue_independent_work", "review_approved": False}}))
        raise SystemExit(5)
