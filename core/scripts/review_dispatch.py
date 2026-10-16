#!/usr/bin/env python3
"""Collect a review from the requested reviewer; fail over once only when explicitly allowed."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from time import sleep
import uuid

import agent_usage
import agent_process
import claude_bridge
import codex_bridge

# Operational failures only (KARARLAR D04 inv2#44). Invalid evidence, configuration, changed
# scope and storage failures must not be laundered into success by trying another reviewer, and
# a setup fault (cli_unsupported, sandbox_unavailable, authentication) is fixed, never failed over.
UNAVAILABLE = frozenset({"rate_limited", "quota_exhausted", "timeout", "unavailable", "cli_error",
                         "context_limit", "budget_or_turn_limit", "output_limit", "content_flagged"})
# A Codex capacity error passes (KARARLAR B01 (6) inv2#46): retried after the delay the tool
# reports, else after about ten minutes, doubled, at most twice. Ten minutes is an owner choice;
# both vendors bound their own retries. A used-up quota is never retried.
CAPACITY_RETRY_SECONDS = 600
CAPACITY_RETRIES = 2
# Set only while a substitute reviewer runs, so its archived evidence says so in its body.
FALLBACK_ENV = "MYAGENTKIT_REVIEW_FALLBACK_FROM"
# What a backend file may set: the endpoint, its token and the model names Claude Code maps.
BACKEND_KEYS = frozenset({"ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
                          "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                          "ANTHROPIC_DEFAULT_HAIKU_MODEL"})
# Claude Code credential/provider controls (env-vars reference and CLI 2.1.296).
# The worker imports this list; include token descriptors and host/gateway routing.
BACKEND_CLEAR_KEYS = frozenset({
    'CLAUDE_CODE_API_BASE_URL',
    'CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR',
    'CLAUDE_CODE_API_KEY_HELPER_TTL_MS',
    'CLAUDE_CODE_ARTIFACTS_API_BASE_URL',
    'CLAUDE_CODE_ARTIFACTS_API_TOKEN',
    'CLAUDE_CODE_ARTIFACT_ASSET_BASE_URL',
    'CLAUDE_CODE_ARTIFACT_LIVE_BASE_URL',
    'CLAUDE_CODE_ARTIFACT_SYNC_BASE_URL',
    'CLAUDE_CODE_ARTIFACT_VIEWER_BASE_URL',
    'CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL',
    'CLAUDE_CODE_AUTO_MODE_MODEL',
    'CLAUDE_CODE_AWS_CHAIN_RESOLVE_TIMEOUT_MS',
    'CLAUDE_CODE_BG_CLASSIFIER_MODEL',
    'CLAUDE_CODE_CLIENT_CERT',
    'CLAUDE_CODE_CLIENT_KEY',
    'CLAUDE_CODE_CLIENT_KEY_PASSPHRASE',
    'CLAUDE_CODE_CUSTOM_OAUTH_URL',
    'CLAUDE_CODE_DESIGN_OAUTH_CLIENT_ID',
    'CLAUDE_CODE_DISABLE_AUTH_REFRESH_LOCK',
    'CLAUDE_CODE_ENABLE_PROXY_AUTH_HELPER',
    'CLAUDE_CODE_GATEWAY_HINT_HEADERS',
    'CLAUDE_CODE_GATEWAY_TOKEN',
    'CLAUDE_CODE_GATEWAY_TOKEN_FILE_DESCRIPTOR',
    'CLAUDE_CODE_GB_BASE_URL',
    'CLAUDE_CODE_HFI_BEARER_TOKEN',
    'CLAUDE_CODE_HOST_AUTH_ENV_VAR',
    'CLAUDE_CODE_HOST_AUTH_REFRESH_TIMEOUT_MS',
    'CLAUDE_CODE_HOST_GATEWAY_LINEAGE',
    'CLAUDE_CODE_HOST_HTTP_PROXY_PORT',
    'CLAUDE_CODE_HOST_SOCKS_PROXY_PORT',
    'CLAUDE_CODE_HTTPS_PROXY',
    'CLAUDE_CODE_HTTP_PROXY',
    'CLAUDE_CODE_MCP_SERVE_AUTH_TOKEN',
    'CLAUDE_CODE_MEMORY_API_BASE_URL',
    'CLAUDE_CODE_MEMORY_API_TOKEN',
    'CLAUDE_CODE_MESSAGING_TOKEN',
    'CLAUDE_CODE_METRICS_ENDPOINT',
    'CLAUDE_CODE_MODEL_CATALOG_URL',
    'CLAUDE_CODE_OAUTH_CLIENT_ID',
    'CLAUDE_CODE_OAUTH_REFRESH_TOKEN',
    'CLAUDE_CODE_OAUTH_SCOPES',
    'CLAUDE_CODE_OAUTH_TOKEN',
    'CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR',
    'CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST',
    'CLAUDE_CODE_PROXY_AUTHENTICATE',
    'CLAUDE_CODE_PROXY_AUTH_HELPER_TTL_MS',
    'CLAUDE_CODE_PROXY_HOST',
    'CLAUDE_CODE_PROXY_RESOLVES_HOSTS',
    'CLAUDE_CODE_PROXY_URL',
    'CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH',
    'CLAUDE_CODE_SDK_HAS_OAUTH_REFRESH',
    'CLAUDE_CODE_SESSION_ACCESS_TOKEN',
    'CLAUDE_CODE_SKIP_ANTHROPIC_AWS_AUTH',
    'CLAUDE_CODE_SKIP_ANTHROPIC_GOOGLE_CLOUD_AUTH',
    'CLAUDE_CODE_SKIP_AWS_CRED_CACHE',
    'CLAUDE_CODE_SKIP_BEDROCK_AUTH',
    'CLAUDE_CODE_SKIP_FOUNDRY_AUTH',
    'CLAUDE_CODE_SKIP_MANTLE_AUTH',
    'CLAUDE_CODE_SKIP_VERTEX_AUTH',
    'CLAUDE_CODE_SLACK_TAG_TOKEN',
    'CLAUDE_CODE_SUBAGENT_MODEL',
    'CLAUDE_CODE_SUBAGENT_MODEL_FORCE',
    'CLAUDE_CODE_USE_ANTHROPIC_AWS',
    'CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD',
    'CLAUDE_CODE_USE_BEDROCK',
    'CLAUDE_CODE_USE_CCR_V',
    'CLAUDE_CODE_USE_FOUNDRY',
    'CLAUDE_CODE_USE_GATEWAY',
    'CLAUDE_CODE_USE_MANTLE',
    'CLAUDE_CODE_USE_VERTEX',
    'CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR',
    'CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL',
})
BACKEND_MAX_BYTES = 64 * 1024


def pin_valid(provider, model, backend=None):
    # A backend's model is no claude- id; its file names it, so it is no moving alias either.
    return bool(model.strip()) and not any(c.isspace() for c in model) and (
        provider != "claude" or bool(backend) or model.startswith("claude-"))


def tier(model):
    """The tier a model id belongs to: `claude-opus` for every Opus id (claude-opus-5,
    claude-opus-5-5, a dated one), else the id without a -YYYYMMDD date. A `vendor/` prefix,
    as MYAGENTKIT_REQUESTER writes it, is dropped."""
    model = model.strip().lower().rpartition("/")[2]
    family = re.match(r"claude-([a-z]+)", model)
    return "claude-" + family[1] if family else re.sub(r"-\d{8}$", "", model)


def load_backend(repo, name):
    """The environment and the model pin of backend `name`, from NAME.env in the backend folder
    (claude_bridge.backends_dir()), else the old .myagentkit/backends/NAME.env.

    Fails closed: a file without an endpoint, token or model could send the
    review to Anthropic's own endpoint under a name that claims another. No message prints a
    value, because the file holds the endpoint's token.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError("backend name must be letters, digits, '.', '_' or '-' (got %r)" % name)
    # KARARLAR D09 inv2#80, LIDER 10: outside the repository by default, so a checkout can never
    # provide or change the file; the old in-repository place is read while projects move.
    folder = claude_bridge.backends_dir()
    if folder.resolve() == repo or repo in folder.resolve().parents:
        raise ValueError("backend folder %s must be outside the repository (MYAGENTKIT_BACKENDS_DIR)" % folder)
    path = folder / (name + ".env")
    if not os.path.lexists(path):
        path = repo / ".myagentkit/backends" / (name + ".env")
        relative = path.relative_to(repo).as_posix()
        tracked = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"],
                                 capture_output=True)
        ignored = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", "--", relative],
                                 capture_output=True)
        if tracked.returncode != 0 or ignored.returncode != 0 or any(
                os.fsdecode(entry).casefold().startswith(".myagentkit/backends/")
                for entry in tracked.stdout.split(b"\0") if entry):
            raise ValueError("backend %s: %s must be Git-ignored and untracked" % (name, path))
        if os.path.lexists(path):
            print("NOTE [review]: backend %s is read from %s, the old place; move it to %s (the "
                  "old place is read only while projects move)" % (name, path, folder),
                  file=sys.stderr, flush=True)
    try:
        if path.is_symlink() or not os.path.isfile(path):
            raise ValueError("backend %s: %s cannot be read: expected a regular file" % (name, path))
        # Nonblocking open also prevents a FIFO swapped in after isfile() from blocking.
        flags = (os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(os.open(path, flags), "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("backend %s: %s must be a regular file" % (name, path))
            data = stream.read(BACKEND_MAX_BYTES + 1)
        if len(data) > BACKEND_MAX_BYTES:
            raise ValueError("backend %s: %s is too large (maximum %d bytes)" % (name, path, BACKEND_MAX_BYTES))
        lines = data.decode("utf-8").splitlines()
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
        if "\x00" in value:
            raise ValueError("backend %s: line %d of %s contains an invalid environment value" % (name, number, path))
        env[key] = value
    if not env.get("ANTHROPIC_BASE_URL"):
        raise ValueError("backend %s: %s sets no ANTHROPIC_BASE_URL" % (name, path))
    model = env.get("ANTHROPIC_MODEL") or env.get("ANTHROPIC_DEFAULT_OPUS_MODEL")
    if not model or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@-]*", model):
        raise ValueError("backend %s: %s sets no model (ANTHROPIC_MODEL or "
                         "ANTHROPIC_DEFAULT_OPUS_MODEL, id matching [A-Za-z0-9][A-Za-z0-9._:/@-]*)" % (name, path))
    if not env.get("ANTHROPIC_AUTH_TOKEN"):
        raise ValueError("backend %s: %s sets no ANTHROPIC_AUTH_TOKEN" % (name, path))
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
    parser.add_argument("--effort", choices=("low", "medium", "high"),
                        default=claude_bridge.default_effort())  # no xhigh for a review
    # Off by default: the requested reviewer is usually chosen because the other model
    # authored the patch, so a silent substitute could be the author reviewing itself.
    parser.add_argument("--allow-fallback", action="store_true")
    # The Claude reviewer through an Anthropic-compatible endpoint, as reviewer claude@NAME.
    parser.add_argument("--backend")
    scope_args = parser.add_mutually_exclusive_group()
    scope_args.add_argument("--uncommitted", action="store_true")
    scope_args.add_argument("--base")
    scope_args.add_argument("--commit")
    # A secret-looking file the owner reviews knowingly (KARARLAR B12 inv2#106), by its path.
    parser.add_argument("--allow-secret-file", action="append", default=[])
    args = parser.parse_args(argv)
    os.environ.pop(claude_bridge.ALLOW_SECRETS_ENV, None)  # only this run's flags count
    claude_bridge.allow_secret_files(args.allow_secret_file)
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
    # KARARLAR B01 (1): the author never reviews its own patch, and the default excludes the
    # author's tier. Only the lead knows the author; when it says so, the pin is checked here.
    author = os.environ.get("MYAGENTKIT_AUTHOR", "").strip() or None
    if author and tier(author) == tier(pins[args.reviewer]):
        raise ValueError("MYAGENTKIT_AUTHOR %s is the author's tier (%s), which reviewer %s model %s "
                         "would run: the author never reviews its own patch (docs/REVIEW_GATE.md, "
                         "\"Invariant\"). Pin another tier (REVIEW_CLAUDE_MODEL) or the other family "
                         "(--reviewer)" % (author, tier(author), names[args.reviewer], pins[args.reviewer]))
    scope, ref = ("base", args.base) if args.base else (("commit", args.commit) if args.commit else ("uncommitted", None))
    original = claude_bridge.snapshot(repo, scope, ref)
    if not original[2].strip():
        raise ValueError("empty diff: nothing was reviewed")
    reject_line_ending_churn(repo, scope, original[3], original[2])
    # Once for either reviewer: a missing, foreign or oversized earlier round stops the review
    # here, exit 2 with one message, before a chain is recorded or any model is called.
    # The dispositions file is read here once and its text handed to every attempt: a
    # fallback attempt never reads a file that changed meanwhile.
    claims = claude_bridge.dispositions_text()
    claude_bridge.prior_rounds(repo, os.environ.get("MYAGENTKIT_TASK_ID"), scope, original[3],
                               original[0], original[2], claims)
    timeout = int(os.environ.get("REVIEW_TIMEOUT_SECONDS", str(agent_process.DEFAULT_REVIEW_TIMEOUT)))
    if not 1 <= timeout <= agent_process.MAX_REVIEW_TIMEOUT:
        raise ValueError("REVIEW_TIMEOUT_SECONDS must be 1..%d" % agent_process.MAX_REVIEW_TIMEOUT)
    def review_turns():
        turns = int(os.environ.get("REVIEW_MAX_TURNS", str(agent_process.DEFAULT_REVIEW_TURNS)))
        if not 1 <= turns <= agent_process.MAX_REVIEW_TURNS:
            raise ValueError("REVIEW_MAX_TURNS must be 1..%d" % agent_process.MAX_REVIEW_TURNS)
        return turns
    # Claude only: Codex has no turn limit to set. A Codex review that switches to Claude on a
    # used-up quota checks it then.
    turns = review_turns() if args.reviewer == "claude" or args.allow_fallback else None
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
    if author:
        chain["author"] = author  # the lead's claim, recorded; the pairs are measured per author
    if os.environ.get("REVIEW_SHADOW") == "1":
        # Marked where a later reader looks: the chain record and the console. A variable left
        # exported after a shadow run turns every later review into one, so the line says so.
        chain["shadow"] = True
        print("REVIEW [shadow]: this run measures a reviewer configuration; its verdict closes "
              "nothing. REVIEW_SHADOW=1 is set: unset REVIEW_SHADOW after the shadow run, or "
              "every later review is a shadow too.", flush=True)

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
    queue, retries = [args.reviewer], 0
    while queue:
        provider = queue.pop(0)
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
            inherited = {key: value for key, value in os.environ.items()
                         if key.startswith("ANTHROPIC_") or key in BACKEND_CLEAR_KEYS}
        error = None
        try:
            if backend:
                for key in inherited:
                    del os.environ[key]
                os.environ.update(backend_env)
            if provider == "claude":
                exit_code = claude_bridge.main(["review", "--timeout", str(timeout), "--max-turns", str(turns), *command]
                                               + (["--backend", args.backend] if backend else []), received.append,
                                               claims=claims)
            else:
                exit_code = codex_bridge.main(command, received.append, claims=claims)
        except (OSError, ValueError, claude_bridge.BridgeError, subprocess.SubprocessError) as caught:
            exit_code, error = 5, caught
        finally:
            if backend:
                for key in [key for key in os.environ
                            if key.startswith("ANTHROPIC_") or key in BACKEND_CLEAR_KEYS]:
                    del os.environ[key]
                os.environ.update(inherited)
        if received:
            # An adapter hands its result over only after its evidence and usage record are
            # written, its own checkout check included. A failure after that (printing the
            # review) does not change what was recorded: relabelled adapter_error, a completed,
            # paid review was reported as no review (issue #71). The result decides, not the
            # exit code; the checkout check below still runs.
            result = received[-1]
            delivered = 0 if result["status"] == "completed" else 5
            if error is None and exit_code != delivered:
                error = "the adapter exited %s" % exit_code
            exit_code = delivered
        elif error is not None:
            # Includes persistence failures. No machine result means no safe failover.
            result = {"status": "failed", "failure_kind": "adapter_error", "error": str(error)}
        else:
            result = {"status": "failed", "failure_kind": "preflight_failed"}
        attempt = dict(result, reviewer=names[provider], model=pins[provider])
        if received and error is not None:
            attempt["error_after_result"] = str(error)
        chain["attempts"].append(attempt)
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
        else:
            chain["status"] = "failed"
        # A cancel at any point after launch ends the chain: both adapters relabel a cancelled
        # failure "cancelled", which is not in UNAVAILABLE, before they return.
        recorded = bool(result.get("evidence")) and bool(result.get("usage_record"))
        retry = (chain["status"] != "completed" and provider == "codex" and recorded
                 and chain["failure_kind"] == "rate_limited" and retries < CAPACITY_RETRIES)
        eligible = (chain["status"] != "completed" and provider == args.reviewer and chain["failure_kind"] in UNAVAILABLE
                    and recorded and not retry)
        # Lead decision 7 (decisions.md; the kit runs on Claude alone): a used-up Codex quota
        # switches the role to Claude without --fallback, recorded in the chain and reported.
        switch = eligible and provider == "codex" and chain["failure_kind"] == "quota_exhausted"
        if switch and turns is None:
            try:
                turns = review_turns()
            except ValueError as error:
                chain["fallback_blocked"] = str(error)
                switch = eligible = False
        if eligible and not args.allow_fallback and not switch:
            chain["fallback_blocked"] = "not requested; --fallback allows one other configured reviewer"
            eligible = False
        if eligible and not pin_valid(other, pins[other], args.backend):
            chain["fallback_blocked"] = "other reviewer has no valid configured model pin"
            eligible = False
        if eligible and author and tier(author) == tier(pins[other]):
            chain["fallback_blocked"] = ("other reviewer %s model %s is the author's tier (MYAGENTKIT_AUTHOR %s)"
                                         % (names[other], pins[other], author))
            eligible = False
        checkpoint()  # Never spend on the alternate if primary evidence cannot be saved.
        if attempt.get("error_after_result"):  # Save once, before a closed console can raise again.
            # The result stands only when the chain completed; after a stale_checkout it did not.
            print("NOTE [review]: %s failed after it handed over its result (%s); %s %s%s"
                  % (names[provider], attempt["error_after_result"],
                     "the result stands as recorded in" if chain["status"] == "completed"
                     else "the adapter recorded the result in", result.get("evidence"),
                     ", but the checkout changed, so the chain failed"
                     if chain.get("checkout_changed") else ""), flush=True)
        if retry:
            delay = (result.get("retry_after") or CAPACITY_RETRY_SECONDS) * 2 ** retries
            retries += 1
            print("RETRY [review]: %s is at capacity (rate_limited); retry %d of %d in %s seconds."
                  % (names[provider], retries, CAPACITY_RETRIES, delay), flush=True)
            sleep(delay)
            queue.insert(0, provider)
            continue
        if chain["status"] == "completed" or not eligible:
            break
        if switch:
            chain["switched"] = ("quota_exhausted: the Codex quota is used up, so the role switched "
                                 "to Claude (decisions.md 7)")
            print("SWITCH [review]: codex quota is exhausted (quota_exhausted); the kit runs on Claude "
                  "alone, so configured %s model %s runs once instead. Tell the owner."
                  % (names[other], pins[other]), flush=True)
        else:
            print("FALLBACK [review]: requested reviewer %s did not complete (%s); --fallback was "
                  "passed, so configured %s model %s runs once instead."
                  % (names[provider], chain["failure_kind"], names[other], pins[other]), flush=True)
        os.environ[FALLBACK_ENV] = "%s (%s)" % (names[provider], chain["failure_kind"])
        queue.append(other)
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
        if chain["failure_kind"] == "quota_exhausted":
            print("FAIL [review]: the reviewer's quota is exhausted (a plan, session or spend limit); "
                  "it is not retried. Tell the owner: wait for the reset, or run the review with "
                  "--fallback on the other configured reviewer.")
        if chain["failure_kind"] == "rate_limited":
            print("FAIL [review]: the reviewer was rate limited or at capacity; run the review "
                  "again later, or with --fallback on the other configured reviewer.")
        if chain["failure_kind"] == "content_flagged":
            print("FAIL [review]: the provider's content classifier stopped the review; run it "
                  "again, or send a smaller scope (--commit, or a shorter --base range).")
        if chain["failure_kind"] == "stale_checkout":
            # Correct to fail: the reviewer reads files while it runs, so its findings may
            # describe a tree the archived diff and fingerprint do not. The fix is the caller's.
            print("FAIL [review]: the checkout changed while the review ran (an edit, a staged "
                  "change, a new untracked file Git does not ignore, a moved HEAD or base), so "
                  "the result cannot be tied to the "
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
