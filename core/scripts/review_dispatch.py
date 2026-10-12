#!/usr/bin/env python3
"""Collect a review from the requested reviewer; fail over once only when explicitly allowed."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

import agent_usage
import agent_process
import claude_bridge
import codex_bridge

# Operational failures only. Invalid evidence, configuration, changed scope and storage
# failures must not be laundered into success by trying another reviewer.
UNAVAILABLE = frozenset({"quota", "authentication", "timeout", "unavailable", "cli_error",
                         "context_limit", "budget_or_turn_limit", "output_limit", "content_flagged"})
# Set only while a substitute reviewer runs, so its archived evidence says so in its body.
FALLBACK_ENV = "MYAGENTKIT_REVIEW_FALLBACK_FROM"
# What a backend file may set: the endpoint, its token and the model names Claude Code maps.
BACKEND_KEYS = frozenset({"ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
                          "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                          "ANTHROPIC_DEFAULT_HAIKU_MODEL"})


def pin_valid(provider, model, backend=None):
    # A backend's model is no claude- id; its file names it, so it is no moving alias either.
    return bool(model.strip()) and not any(c.isspace() for c in model) and (
        provider != "claude" or bool(backend) or model.startswith("claude-"))


def load_backend(repo, name):
    """The environment and the model pin of backend `name`, from .myagentkit/backends/NAME.env.

    Fails closed, like an empty pin: a file without an endpoint or a model would send the
    review to Anthropic's own endpoint under a name that claims another. No message prints a
    value, because the file holds the endpoint's token.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError("backend name must be letters, digits, '.', '_' or '-' (got %r)" % name)
    path = repo / ".myagentkit/backends" / (name + ".env")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError("backend %s: %s cannot be read (%s)" % (name, path, type(error).__name__)) from error
    env = {}
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key not in BACKEND_KEYS:
            raise ValueError("backend %s: line %d of %s is not KEY=VALUE with one of %s"
                             % (name, number, path, ", ".join(sorted(BACKEND_KEYS))))
        env[key] = value
    if not env.get("ANTHROPIC_BASE_URL"):
        raise ValueError("backend %s: %s sets no ANTHROPIC_BASE_URL" % (name, path))
    model = env.get("ANTHROPIC_MODEL") or env.get("ANTHROPIC_DEFAULT_OPUS_MODEL")
    if not model or not pin_valid("claude", model, name):
        raise ValueError("backend %s: %s sets no model (ANTHROPIC_MODEL or "
                         "ANTHROPIC_DEFAULT_OPUS_MODEL, one id without spaces)" % (name, path))
    return env, model


def reject_line_ending_churn(repo, scope, reference, diff):
    if os.environ.get("REVIEW_ALLOW_EOL_ONLY") == "1":
        return
    # Use the captured scope's paths, including its archive exclusions. `git apply --numstat
    # -z` prints one name per patch, a rename's new name; only `git diff` has a rename form.
    names = {entry.split(b"\t", 2)[2]
             for entry in claude_bridge.git(repo, "apply", "--numstat", "-z",
                                            stdin=diff.encode("utf-8")).split(b"\0") if entry}
    refs = ["HEAD"]
    if scope == "base":
        refs = [reference + "...HEAD"]
    elif scope == "commit":
        parents = claude_bridge.git(repo, "rev-list", "--parents", "-n", "1", reference).split()[1:]
        if not parents:
            return  # A root commit only adds files.
        refs = [os.fsdecode(parents[0]), reference]

    def counts(data):
        result = {}
        for entry in data.split(b"\0"):
            if entry:
                added, deleted, name = entry.split(b"\t", 2)
                if added != b"-":  # Binary changes have no line counts.
                    result[name] = int(added) + int(deleted)
        return result

    # Two queries for the whole scope, independent of its file count. The captured names
    # also exclude legacy review archives that snapshot discovered in the reference trees.
    args = ["diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--numstat", "-z", *refs,
            "--", ".", *claude_bridge.ARCHIVES]
    changed = counts(claude_bridge.git(repo, *args))
    meaningful = counts(claude_bridge.git(repo, *args[:1], "--ignore-cr-at-eol", *args[1:]))
    for name in sorted(names):
        total, real = changed.get(name, 0), meaningful.get(name, 0)
        if total > 2 * real:  # Most changed lines are CR-only, even with a real edit.
            kind = "line-ending-only churn" if real == 0 else "line-ending churn"
            raise ValueError("%s in %r; restore its line endings before review, or set "
                             "REVIEW_ALLOW_EOL_ONLY=1 for a deliberate normalization"
                             % (kind, os.fsdecode(name)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--reviewer", choices=("claude", "codex"), default="claude")
    parser.add_argument("--claude-model", default=os.environ.get("REVIEW_CLAUDE_MODEL", ""))
    parser.add_argument("--codex-model", default=os.environ.get("REVIEW_CODEX_MODEL", ""))
    parser.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"), default="high")
    # Off by default: the requested reviewer is usually chosen because the other model
    # authored the patch, so a silent substitute could be the author reviewing itself.
    parser.add_argument("--allow-fallback", action="store_true")
    # The Claude reviewer through an Anthropic-compatible endpoint, as reviewer claude@NAME.
    parser.add_argument("--backend")
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
    # Another reviewer identity: a patch Claude wrote may be reviewed by claude@NAME.
    names, backend_env = {"claude": "claude", "codex": "codex"}, {}
    if args.backend:
        backend_env, pins["claude"] = load_backend(repo, args.backend)
        names["claude"] = "claude@" + args.backend
    if not pins[args.reviewer].strip():
        raise ValueError("no model pinned for reviewer '%s'" % args.reviewer)
    if not pin_valid(args.reviewer, pins[args.reviewer], args.backend):
        raise ValueError("invalid primary model pin")
    scope, ref = ("base", args.base) if args.base else (("commit", args.commit) if args.commit else ("uncommitted", None))
    original = claude_bridge.snapshot(repo, scope, ref)
    if not original[2].strip():
        raise ValueError("empty diff: nothing was reviewed")
    reject_line_ending_churn(repo, scope, original[3], original[2])
    # Once for either reviewer: a missing, foreign or oversized earlier round stops the review
    # here, exit 2 with one message, before a chain is recorded or any model is called.
    claude_bridge.prior_rounds(repo, os.environ.get("MYAGENTKIT_TASK_ID"), scope, original[3],
                               original[0], original[2])
    timeout = int(os.environ.get("REVIEW_TIMEOUT_SECONDS", str(agent_process.DEFAULT_REVIEW_TIMEOUT)))
    if not 1 <= timeout <= agent_process.MAX_REVIEW_TIMEOUT:
        raise ValueError("REVIEW_TIMEOUT_SECONDS must be 1..%d" % agent_process.MAX_REVIEW_TIMEOUT)
    # Claude only: Codex has no turn limit to set.
    if args.reviewer == "claude" or args.allow_fallback:
        turns = int(os.environ.get("REVIEW_MAX_TURNS", str(agent_process.DEFAULT_REVIEW_TURNS)))
        if not 1 <= turns <= agent_process.MAX_REVIEW_TURNS:
            raise ValueError("REVIEW_MAX_TURNS must be 1..%d" % agent_process.MAX_REVIEW_TURNS)
    agent_usage.require_private_storage(repo)
    chain_id = uuid.uuid4().hex
    os.environ["MYAGENTKIT_REVIEW_CHAIN_ID"] = chain_id
    # An empty label is no label: kept as "", it was recorded as an id every later labelled
    # round refused as damaged.
    if not os.environ.get("MYAGENTKIT_TASK_ID"):
        os.environ["MYAGENTKIT_TASK_ID"] = "review-" + chain_id
    chain = {"schema_version": 1, "chain_id": chain_id, "requested_reviewer": names[args.reviewer],
             "configured_models": pins, "task_id": os.environ["MYAGENTKIT_TASK_ID"],
             "head": original[0], "fingerprint": original[1], "scope": scope, "reference": ref,
             "fallback_allowed": args.allow_fallback,
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
    os.environ.pop(FALLBACK_ENV, None)
    for provider in (args.reviewer, other):
        os.environ["MYAGENTKIT_REVIEW_ATTEMPT"] = str(len(chain["attempts"]) + 1)
        received = []
        command = ["--repo", str(repo), "--model", pins[provider], "--effort", args.effort,
                   "--" + scope] + ([ref] if ref else [])
        print("REVIEW [about to run]: %s model %s, effort %s" % (names[provider], pins[provider], args.effort),
              flush=True)
        # The backend's variables reach the Claude CLI of this attempt only, in place of every
        # inherited ANTHROPIC_* one: an inherited API key would otherwise go to the backend's
        # endpoint, and a Codex fallback after it would see the backend's token.
        backend = provider == "claude" and args.backend
        if backend:
            inherited = {key: os.environ.pop(key) for key in list(os.environ) if key.startswith("ANTHROPIC_")}
            os.environ.update(backend_env)
        try:
            if provider == "claude":
                exit_code = claude_bridge.main(["review", "--timeout", str(timeout), "--max-turns", str(turns), *command]
                                               + (["--backend", args.backend] if backend else []), received.append)
            else:
                exit_code = codex_bridge.main(command, received.append)
        except (OSError, ValueError, claude_bridge.BridgeError, subprocess.SubprocessError) as error:
            # Includes persistence failures. No machine result means no safe failover.
            exit_code = 5
            received = [{"status": "failed", "failure_kind": "adapter_error", "error": str(error)}]
        finally:
            if backend:
                for key in [key for key in os.environ if key.startswith("ANTHROPIC_")]:
                    del os.environ[key]
                os.environ.update(inherited)
        result = received[-1] if received else {"status": "failed", "failure_kind": "preflight_failed"}
        chain["attempts"].append(dict(result, reviewer=names[provider], model=pins[provider]))
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
            chain["selected_reviewer"] = names[provider]
            checkpoint()
            break  # Accept, manual checks AND Reject are terminal review results.
        chain["status"] = "failed"
        # A cancel at any point after launch ends the chain: both adapters relabel a cancelled
        # failure "cancelled", which is not in UNAVAILABLE, before they return.
        eligible = (provider == args.reviewer and chain["failure_kind"] in UNAVAILABLE
                    and bool(result.get("evidence")) and bool(result.get("usage_record")))
        if eligible and not args.allow_fallback:
            chain["fallback_blocked"] = "not requested; --fallback allows one other configured reviewer"
            eligible = False
        if eligible and not pin_valid(other, pins[other], args.backend):
            chain["fallback_blocked"] = "other reviewer has no valid configured model pin"
            eligible = False
        checkpoint()  # Never spend on the alternate if primary evidence cannot be saved.
        if not eligible:
            break
        print("FALLBACK [review]: requested reviewer %s did not complete (%s); --fallback was "
              "passed, so configured %s model %s runs once instead."
              % (names[provider], chain["failure_kind"], names[other], pins[other]), flush=True)
        os.environ[FALLBACK_ENV] = "%s (%s)" % (names[provider], chain["failure_kind"])
    os.environ.pop(FALLBACK_ENV, None)
    print("review dispatch: " + json.dumps(chain))
    if chain["status"] != "completed":
        print("FAIL [review]: requested reviewer %s did not produce a review (%s)%s"
              % (names[args.reviewer], chain["failure_kind"], "; " + chain["fallback_blocked"]
                 if chain.get("fallback_blocked") else ""))
        if chain["failure_kind"] == "cli_unsupported":
            print("FAIL [review]: the installed CLI rejected a flag the review requires; "
                  "upgrade the CLI. The review never drops a sandbox flag to make a run start.")
        if chain["failure_kind"] == "sandbox_unavailable":
            print("FAIL [review]: Claude Code's Bash sandbox cannot start on this host, and the "
                  "review never runs Bash outside it. On Linux and WSL2 install bubblewrap and "
                  "socat (see scripts/doctor.sh); WSL1 cannot sandbox.")
        if chain["failure_kind"] == "content_flagged":
            print("FAIL [review]: the provider's content classifier stopped the review; run it "
                  "again, or send a smaller scope (--commit, or a shorter --base range).")
        if chain["failure_kind"] == "stale_checkout":
            # Correct to fail: the reviewer reads files while it runs, so its findings may
            # describe a tree the archived diff and fingerprint do not. The fix is the caller's.
            print("FAIL [review]: the checkout changed while the review ran (an edit, a new "
                  "untracked file, a moved HEAD or base), so the result cannot be tied to the "
                  "diff it names. Leave this checkout untouched until review.sh exits: keep "
                  "working in another worktree, or wait for it, then run the review again.")
    elif chain.get("selected_reviewer") != names[args.reviewer]:
        print("FALLBACK [review]: this review is by %s, not the requested %s; check it did not "
              "author the patch." % (chain["selected_reviewer"], names[args.reviewer]))
    return 0 if chain["status"] == "completed" else (exit_code or 5)


if __name__ == "__main__":
    claude_bridge.utf8_output()
    try:
        raise SystemExit(main())
    except (OSError, ValueError, claude_bridge.BridgeError, subprocess.SubprocessError) as error:
        print("FAIL [review]: " + str(error))
        raise SystemExit(2)
