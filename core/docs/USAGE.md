# Cross-model usage and recovery

Both supported CLI adapters write one local JSON record per launched invocation under
`.myagentkit/usage/`. This directory is ignored by Git: raw provider output and account
diagnostics are local operational evidence, not material for a public push. Back it up
privately if you need retention across machines. Preflight refusals launch no child and
are not counted as billed invocations.

## Attribution and reports

For Claude-host Codex reviews, set `MYAGENTKIT_REQUESTER=claude/ACTUAL_MODEL` and
`MYAGENTKIT_TASK_ID=STABLE_TASK_LABEL` when running `scripts/review.sh`. The caller model is
reported metadata, never an attestation. If absent, it stays unknown. For Codex-host Claude
calls, pass `--requester codex/ACTUAL_MODEL --task-id STABLE_TASK_LABEL` to the bundled
`claude_bridge.py`. Reuse the task label across review rounds.

```sh
python3 scripts/agent_usage.py --repo .
python3 scripts/agent_usage.py --repo . --task-id STABLE_TASK_LABEL --json
```

In the kit checkout, use `core/scripts/agent_usage.py`; an installed Codex plugin also has
`scripts/agent_usage.py` beside its bundled bridge. The report omits raw transcripts by
default. A lack of records means no recorded evidence, not zero historical usage.

Every record includes task, requester, requested callee model, source revision/hash,
elapsed time, status, failure classification, evidence location, and available usage.
Claude's per-model `modelUsage` is retained; a Codex requested model is not misrepresented
as observed model identity when its JSONL events do not attest the actual model.

## What the numbers mean

- Token fields are CLI-reported values, not estimates. Missing or invalid numbers are null.
- Codex input tokens include cached input; do not add the cache field again. Claude input,
  cache-read, and cache-creation fields retain their separate provider semantics.
- Reasoning tokens are a breakdown of output, not additional output to add again.
- Claude's reported API-equivalent dollar cost is retained even on a failed call. It is
  not an invoice or the amount of subscription credit consumed. Codex dollars stay unknown
  unless its supported output reports them; no price table is guessed or maintained here.
- Subscription percentage and credits consumed stay unknown. Token counts cannot reliably
  reconstruct a subscription allowance. Codex account quota snapshots are recorded before
  and after a call using the existing CLI's official `account/rateLimits/read` interface.
  They include reported plan, bucket, window, used percentage, and reset time. They are not
  attributed to this call: concurrent usage and resets can make the difference misleading.
  Claude quota percentage remains unknown unless supported output supplies it. No credential
  store or undocumented account endpoint is scraped.
- Failure or timeout marks accounting incomplete. Available partial tokens/cost remain
  visible; absent final usage is not recorded as zero. Only completed-turn usage available
  in Codex JSONL can be recovered. Claude final-JSON mode may emit no usage before timeout.

Sources checked on 2026-09-05: [Codex JSONL usage](https://learn.chatgpt.com/docs/non-interactive-mode),
[subscription usage semantics](https://learn.chatgpt.com/docs/pricing), and
[Claude cost reporting](https://code.claude.com/docs/en/costs).
Codex quota source: [official account rate limits](https://learn.chatgpt.com/docs/app-server).

Codex quota observation is enabled by default; set `MYAGENTKIT_CAPTURE_QUOTA=0` to disable
it. Each optional read has a five-second deadline (at most ten seconds of extra telemetry
time around the model invocation). It starts no model thread/turn and performs no login,
logout, reset-credit consumption, credit purchase, or account mutation request. An
unavailable observation is recorded as unknown and does not prevent the model task.

## Bounded failure, useful continuation

Each invocation has a wall-clock limit (600 seconds by default, maximum 3600) and an 8 MB
captured-output limit per stream. The parent stops its child process group and preserves
partial diagnostics in memory through bounded pipes, not temporary output files. Codex's
separate CLI-owned final-message file is size-checked after execution; the adapter does not
claim to bound files the CLI itself writes. Both adapters publish complete evidence before
recording a successful collection; archive failure records failed usage with no evidence
path. Accounting-write failure also returns failure, never review approval. The parent preserves
captured partial output. Claude additionally uses its CLI turn/API-budget flags; the Codex
adapter does not claim a dollar-budget or per-turn limit unsupported by its CLI.
Claude reviews omit the monetary-budget flag unless explicitly requested; their recorded
`limits.api_usd` is null when no cap was specified. This null describes configuration,
not unknown spend. Reported cost/token accounting remains unchanged. Patch proposals retain
their separate three-dollar default; timeout, turn and output protections still apply.

The adapters never automatically retry, buy credits, switch models, or promote a failed
review to approval. Structured recovery instructs the host to record the blocker and continue
independent authorized work. Optional coding assistance can fall back to host implementation.
Required independent review cannot fall back to self-approval: its protected commit/push
remains blocked until the review gate is satisfied. If all remaining work depends on the
missing response, return the blocker rather than wait forever. This is a host workflow rule,
not an autonomous background job or an operating-system enforcement of commit policy.
