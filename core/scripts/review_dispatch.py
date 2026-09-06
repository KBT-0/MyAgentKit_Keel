#!/usr/bin/env python3
"""Collect a review with at most one failover, preserving each attempt's evidence."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid

import agent_usage
import agent_process
import claude_bridge
import codex_bridge

# Operational failures only. Invalid evidence, configuration, changed scope and storage
# failures must not be laundered into success by trying another reviewer.
UNAVAILABLE = frozenset({"quota", "authentication", "timeout", "unavailable", "cli_error",
                         "context_limit", "budget_or_turn_limit", "output_limit"})


def pin_valid(provider, model):
    return bool(model.strip()) and not any(c.isspace() for c in model) and (
        provider != "claude" or model.startswith("claude-"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--reviewer", choices=("claude", "codex"), default="claude")
    parser.add_argument("--claude-model", default=os.environ.get("REVIEW_CLAUDE_MODEL", ""))
    parser.add_argument("--codex-model", default=os.environ.get("REVIEW_CODEX_MODEL", ""))
    parser.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"), default="high")
    scope_args = parser.add_mutually_exclusive_group()
    scope_args.add_argument("--uncommitted", action="store_true")
    scope_args.add_argument("--base")
    scope_args.add_argument("--commit")
    args = parser.parse_args(argv)
    repo = args.repo.resolve(strict=True)
    if os.environ.get("MYAGENTKIT_DELEGATION_DEPTH", "0") != "0":
        raise ValueError("nested delegation is disabled")
    if Path(os.fsdecode(claude_bridge.git(repo, "rev-parse", "--show-toplevel")).strip()).resolve() != repo:
        raise ValueError("--repo must name the repository root")
    pins = {"claude": args.claude_model, "codex": args.codex_model}
    if not pins[args.reviewer].strip():
        raise ValueError("no model pinned for reviewer '%s'" % args.reviewer)
    if not pin_valid(args.reviewer, pins[args.reviewer]):
        raise ValueError("invalid primary model pin")
    scope, ref = ("base", args.base) if args.base else (("commit", args.commit) if args.commit else ("uncommitted", None))
    original = claude_bridge.snapshot(repo, scope, ref)
    if not original[2].strip():
        raise ValueError("empty diff: nothing was reviewed")
    timeout = int(os.environ.get("REVIEW_TIMEOUT_SECONDS", str(agent_process.DEFAULT_REVIEW_TIMEOUT)))
    if not 1 <= timeout <= 3600:
        raise ValueError("REVIEW_TIMEOUT_SECONDS must be 1..3600")
    agent_usage.require_private_storage(repo)
    chain_id = uuid.uuid4().hex
    os.environ["MYAGENTKIT_REVIEW_CHAIN_ID"] = chain_id
    os.environ.setdefault("MYAGENTKIT_TASK_ID", "review-" + chain_id)
    chain = {"schema_version": 1, "chain_id": chain_id, "requested_reviewer": args.reviewer,
             "configured_models": pins, "task_id": os.environ["MYAGENTKIT_TASK_ID"],
             "head": original[0], "fingerprint": original[1], "scope": scope, "reference": ref,
             "attempts": [], "status": "pending", "failure_kind": None,
             "review_approved": False, "independence": "host_must_check_all_patch_authors"}

    def checkpoint():
        # Separate from provider records: usage reporting must not double-count a chain.
        chain["recovery"] = {"action": "inspect_result" if chain["status"] == "completed" else "continue_independent_work",
                             "review_approved": False, "automatic_retry": False}
        path = repo / ".myagentkit/usage/chains" / (chain_id + "-%d.json" % len(chain["attempts"]))
        chain["chain_record"] = str(path)
        agent_usage.write_evidence(repo, path, json.dumps(chain, indent=2) + "\n", private=True)

    checkpoint()  # No model is called if the chain cannot be recorded.
    other = "codex" if args.reviewer == "claude" else "claude"
    exit_code = 5
    for provider in (args.reviewer, other):
        os.environ["MYAGENTKIT_REVIEW_ATTEMPT"] = str(len(chain["attempts"]) + 1)
        received = []
        command = ["--repo", str(repo), "--model", pins[provider], "--effort", args.effort,
                   "--" + scope] + ([ref] if ref else [])
        try:
            if provider == "claude":
                exit_code = claude_bridge.main(["review", "--timeout", str(timeout), *command], received.append)
            else:
                exit_code = codex_bridge.main(command, received.append)
        except (OSError, ValueError, claude_bridge.BridgeError, subprocess.SubprocessError) as error:
            # Includes persistence failures. No machine result means no safe failover.
            exit_code = 5
            received = [{"status": "failed", "failure_kind": "adapter_error", "error": str(error)}]
        result = received[-1] if received else {"status": "failed", "failure_kind": "preflight_failed"}
        chain["attempts"].append(dict(result, reviewer=provider, model=pins[provider]))
        chain.update(status=result["status"], failure_kind=result.get("failure_kind"))
        try:
            if claude_bridge.snapshot(repo, scope, ref) != original:
                raise ValueError("checkout changed between review attempts")
        except (OSError, ValueError, claude_bridge.BridgeError):
            reason = chain["failure_kind"]
            chain.update(status="failed", checkout_changed=True,
                         failure_kind="stale_checkout" if reason is None or reason in UNAVAILABLE else reason)
            exit_code = 5
        if chain["status"] == "completed" and exit_code == 0:
            chain["selected_reviewer"] = provider
            checkpoint()
            break  # Accept, manual checks AND Reject are terminal review results.
        chain["status"] = "failed"
        eligible = (provider == args.reviewer and chain["failure_kind"] in UNAVAILABLE
                    and bool(result.get("evidence")) and bool(result.get("usage_record")))
        if eligible and not pin_valid(other, pins[other]):
            chain["fallback_blocked"] = "other reviewer has no valid configured model pin"
            eligible = False
        checkpoint()  # Never spend on the alternate if primary evidence cannot be saved.
        if not eligible:
            break
        print("Reviewer unavailable (%s: %s); trying configured %s model %s once."
              % (provider, chain["failure_kind"], other, pins[other]), flush=True)
    print("review dispatch: " + json.dumps(chain))
    if chain["status"] != "completed":
        print("FAIL [review]: " + str(chain["failure_kind"]))
    return 0 if chain["status"] == "completed" else (exit_code or 5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, claude_bridge.BridgeError, subprocess.SubprocessError) as error:
        print("FAIL [review]: " + str(error))
        raise SystemExit(2)
