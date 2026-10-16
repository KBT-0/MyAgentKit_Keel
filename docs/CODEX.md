# Codex as manager, Claude as second model

The owner-selected default reviewer is Claude. Once model pins are configured,
`./scripts/review.sh --uncommitted` selects Claude; `--reviewer codex` explicitly selects
Codex. Setup may change the default for another project. A co-authored diff still needs
a non-authoring reviewer rather than blindly using the configured default.

This page documents ONE of the two directions, a Codex session managing the project. It is
not the kit's default: the main mode is `solo`, one family, and in `cross` the lead is
Claude and Codex reviews every change Claude wrote, a low-tier one included
([core/docs/WORKFLOW.md](../core/docs/WORKFLOW.md), "Working modes, by name"). For the
reverse, and for what in-session delegation does and does not exist on each side, see
[delegation-is-not-symmetric.md](delegation-is-not-symmetric.md).

The Codex plugin packages two skills, both standard-library-only review adapters, and
their shared failover dispatcher.
Existing repositories must merge the kit's `core/.gitignore` private-record exclusions
before launching the plugin adapters. Ignored, untracked storage is now checked before
model work and during publication; tracked diagnostics and symlinked storage are refused.
The complete runtime/test upgrade list is maintained in `core/docs/DEV_SETUP.md`.
It requires Python 3.10+, Git, and an installed, authenticated Claude Code CLI with
the documented safe-mode/restricted/structured-output options. It installs no MCP server
and makes no change to the existing Claude Code plugin.

## Install the repository-local plugin

Run from the kit checkout after validating and reviewing the change:

```sh
python3 scripts/package_codex_plugin.py
codex plugin marketplace add /absolute/path/to/MyAgentKit_Keel
codex plugin add myagentkit@personal
```

The repo-local catalog is `.agents/plugins/marketplace.json`, whose generated name is
`personal`. Do not replace an existing unrelated marketplace with the same name: inspect
`codex plugin marketplace list` first and resolve a conflict deliberately. The marketplace
root is the kit repository; its source entry resolves to `plugins/myagentkit`.

Start a new Codex thread after installation. Use `/skills` to select the skill, `$` to
mention it, or a natural-language request:

```text
$myagentkit-review Ask Claude to review this change and fix confirmed findings.
$myagentkit-delegate Ask Claude to propose the implementation for this scoped task.
Ask Claude for a second review before finishing this task.
```

These are Codex skills, NOT registered Claude-style `/myagentkit:...` commands. Do not
promise that namespace as a native Codex slash command. Invocation and discovery follow
the current [official skill interface](https://learn.chatgpt.com/docs/build-skills).

## What is automatic

Within an authorized review-and-fix task, Codex starts a fresh Claude process, waits for
structured evidence, checks every finding, fixes confirmed defects, runs the project gate,
and requests a fresh review of the fixes. Default is at most two review rounds, each with
at most two provider attempts (four calls maximum); a
remaining Reject or unmet manual check is reported, never promoted into approval.

For automatic reviews without repeating the request, the owner may explicitly authorize
the project policy in its canonical instructions. The policy should name the triggering
tasks, permitted model, maximum rounds, and spending limits. Installing or implicitly
selecting the skill alone is NOT permission to spend a second model's budget.

This is an agent-managed loop, not a background daemon or a shell loop that blindly applies
model output. It requires an active Codex session. Permission prompts, rate limits, missing
authentication, unresolved decisions, failed gates, and budget limits can stop progress.
Authorization and the two-round task limit are instructions to the host agent, not a
Python-enforced session counter or a security boundary. Only each invocation's CLI budget,
turn limit, timeout, evidence validation, and tool configuration are enforced by the adapter.

## Reviewer and implementation permissions

`review` and `propose` both pin `dontAsk`, safe mode, restricted mode, empty MCP
configuration, and no session persistence. `propose` offers only `Read,Glob,Grep` in the
checkout. `review` adds Bash and runs in a throwaway copy the adapter makes and removes
(`core/docs/REVIEW_RUNNING.md`). Its Bash runs in Claude Code's own sandbox (`--settings`
with `sandbox.enabled`, `failIfUnavailable`, `allowUnsandboxedCommands: false` and an empty
strict network allowlist): writes reach only the copy and Claude Code's per-user temporary
directory, and a host where the sandbox cannot start fails the review. On native Windows,
where Claude Code has no sandbox, `review` offers no Bash. The prompt forbids both modes from
committing to the checkout or launching another agent; a review that reaches the checkout
anyway is detected afterwards and fails as `stale_checkout`. Safe mode disables automatic
customization loading; the prompt explicitly identifies the canonical project documents.
Claude's normal CLI authentication is retained; `--bare` is intentionally not used because
it bypasses subscription login. The machine must still authorize launching the CLI.

`propose` returns a patch or questions. Codex is the ONLY writer and runs validation. This
does not claim unrestricted autonomous Claude coding in a shared working directory. The
propose prompt's "do not delegate, commit, or access external services" is a reminder, not
the safeguard: the tool restriction above is what holds, as Claude Code's own guidance puts
prompt-injection defence in permissions and the sandbox
([Security](https://code.claude.com/docs/en/security)).

Source: [Claude programmatic usage](https://code.claude.com/docs/en/headless) and
[CLI options](https://code.claude.com/docs/en/cli-reference), checked on 2026-09-05.
Tool restriction is an application-level control, not a claim of an OS read-only mount.

## Adapter and evidence contract

Canonical sources live in `core/scripts/`: `review_dispatch.py`, `claude_bridge.py`, and
`codex_bridge.py`. Bootstrap installs them into project scripts.
`scripts/package_codex_plugin.py` copies them and the shared process/accounting/quota
helpers into the plugin artifact; `--check`
rejects stale or missing generated content. Never hand-edit the packaged runtime.

Existing projects can use `./scripts/review.sh --uncommitted --reviewer claude` after
updating the wrapper and copying its companion Python files. Which reviewer is the DEFAULT is
a project setting at the top of `scripts/review.sh`, not a property of the kit: see
[core/docs/REVIEW_GATE.md](../core/docs/REVIEW_GATE.md) on AUTHOR and REVIEWER as roles.
The kit's own root wrapper delegates to the same core wrapper rather than carrying another
implementation. `REVIEW_CLI_BIN` remains Codex-only; `CLAUDE_CLI_BIN` selects the Claude
binary, not arbitrary extra arguments.
Both reviewers pin their model by name and the wrapper refuses to run unpinned;
`REVIEW_CODEX_MODEL` and `REVIEW_CLAUDE_MODEL` override a pin for one run.
`REVIEW_DOCS` remains the Codex prompt setting. For a nonstandard Claude project
layout, set `CLAUDE_REVIEW_DOCS` to a nonempty JSON array of repository-relative guidance
paths. Missing or outside-repository paths fail before launch. `--requester codex/MODEL`
records the caller's reported identity, not verified model attestation. The host must use a
fresh, different model for cross-model review; this adapter cannot discover its caller.

The Claude adapter emits final JSON with `status`, `evidence`, `fingerprint`, `result`, and
`error`. Exit 0 means valid evidence collection, including Reject; inspect the actual
verdict. Failure to run, absent structured output, missing model evidence, invalid verdicts,
and a changed checkout all fail closed. Failures after launch also receive evidence files.
No trace text can substitute for the final structured result.

Evidence records HEAD, diff hash, checkout fingerprint, requested model/effort, limits,
and raw CLI stdout/stderr. They are written exclusively under docs/reviews or docs/handoffs.
The adapter's timestamped JSON archives are excluded from subsequent review diffs to avoid
recursively embedding prior transcripts; source and ordinary documentation are not excluded.
Reference reviews require a clean checkout, and commit mode requires the checked-out HEAD.

Default review limits are 2700 seconds per attempt (3600 for a high-effort Codex review,
maximum 3600) and 200 Claude turns (maximum 500);
`REVIEW_TIMEOUT_SECONDS` and `REVIEW_MAX_TURNS` change them per run. Reviews have no default monetary cap; the
adapter passes `--max-budget-usd` only when explicitly specified. Patch proposals retain
their separate $3 default. Omitting a cap does not remove provider/account limits.
Reviews omit a default monetary cap because a capped-out review costs money without
returning a usable result. A proposal should produce one patch without growing indefinitely,
so its 600-second, 12-turn and $3 safeguards remain the owner's choice, not measured defaults
(KARARLAR B03 inv2#64, inv3/(j); [agent-loop limits](https://code.claude.com/docs/en/agent-sdk/agent-loop),
reviewed 2026-10-15). The 200/500-turn bounds are likewise the owner's choice (B03 inv2#31).
The wall-clock timeout kills the child process group. These limits are not a promise of
precise subscription quota accounting. The wrapper and packaged dispatcher visibly fail
over once to the other configured model on eligible failure with `--fallback`; exhausted
Codex quota switches the role to Claude automatically. Direct adapters do not
([USAGE.md](../core/docs/USAGE.md), "Bounded failure, useful continuation"; KARARLAR decision 7).
Each wrapper attempt uses `REVIEW_TIMEOUT_SECONDS` independently, or its own default. This
measures total elapsed time, not inactivity or connection setup. Output does not reset it;
two timed-out attempts take about `2 x REVIEW_TIMEOUT_SECONDS` plus local overhead
(KARARLAR D06 inv2#45; B03 inv2/(a)). The defaults total about 90 minutes for two
2700-second attempts or 120 minutes for two 3600-second high-effort Codex attempts;
mixed defaults add the individual deadlines. Claude's final-JSON
mode does not reliably expose whether silent work has started. Proposal mode retains its
separate 600-second default. No
new monetary cap is imposed. An explicit direct-adapter cap must not be dropped to obtain
failover.

## Validation and release

```sh
./scripts/check.sh
./scripts/check.sh --self-test
./scripts/review.sh --self-test
```

Python 3.10+ is required for the kit acceptance suite and installed review self-tests,
including on Codex-only projects. Both live review paths also require Python for bounded
execution and usage recording. The shell entry point remains the same.

## Usage and unavailable children

Set a stable task label and caller model on each invocation; both directions write local
`.myagentkit/usage/*.json` records. Use `core/scripts/agent_usage.py` in the kit checkout to
inspect them. Tokens, cache, reported API-equivalent cost, failures, and duration remain
separate; missing subscription percentages are unknown. The full contract is
[core/docs/USAGE.md](../core/docs/USAGE.md).

Quota, context exhaustion, or timeout stops the affected child, not independent work.
The host records the pending result and continues authorized work that does not need it.
Failed review never authorizes committing or pushing its protected diff. Neither adapter
retries indefinitely. The dispatcher preserves the configured pins, announces failover,
and bounds retries as described in [USAGE.md](../core/docs/USAGE.md). A completed Reject does not trigger a switch.
Invalid evidence, stale scope, and persistence failures stop without trying the alternate.
An author-model fallback is advisory and leaves independent approval pending. Immutable
chain checkpoints in `.myagentkit/usage/chains/` link individual evidence and usage records;
the final `review dispatch:` JSON identifies the outcome. Raw account diagnostics and
usage are ignored by Git; publish only deliberately scrubbed review summaries.

Offline tests construct missing, contradictory, stale, timed-out, and wrong-model evidence
and assert the specific failure. They do not prove authentication or real CLI compatibility.
A live run is required before claiming the integration works on a particular machine;
see the dated result in ACCEPTANCE.md. Any future cache update requires packaging again,
a plugin cachebuster/reinstall, and a new Codex thread. Publishing to a remote marketplace
or pushing the kit is a separate owner-authorized action.
