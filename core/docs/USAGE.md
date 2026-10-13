# Cross-model usage and recovery

Both supported CLI adapters write one local JSON record per launched invocation under
`.myagentkit/usage/`. This directory is ignored by Git: raw provider output and account
diagnostics are local operational evidence, not material for a public push. Back it up
privately if you need retention across machines. Preflight refusals launch no child and
are not counted as billed invocations.

Both direct adapters and the dispatcher verify private storage before model work. The
usage directory and each review/proposal archive must be Git-ignored; existing raw records
must not be tracked. Symlinked storage is rejected. Publication checks the rules again,
and temporary archive content is staged inside the ignored usage directory. Existing
projects must merge the ignore rules and complete companion list in `docs/DEV_SETUP.md`
before using either the wrapper or the standalone plugin adapters.

## Attribution and reports

For Claude-host Codex reviews, set `MYAGENTKIT_REQUESTER=claude/ACTUAL_MODEL` and
`MYAGENTKIT_TASK_ID=STABLE_TASK_LABEL` when running `scripts/review.sh`. The caller model is
reported metadata, never an attestation. If absent, it stays unknown. For Codex-host Claude
calls, pass `--requester codex/ACTUAL_MODEL --task-id STABLE_TASK_LABEL` to the bundled
`claude_bridge.py`. Reuse the task label across review rounds: the next round's prompt carries
the earlier completed reviews with that label (`docs/REVIEW_RUNNING.md`).

```sh
python3 scripts/agent_usage.py --repo .
python3 scripts/agent_usage.py --repo . --task-id STABLE_TASK_LABEL --json
```

In the kit checkout, use `core/scripts/agent_usage.py`; an installed Codex plugin also has
`scripts/agent_usage.py` beside its bundled bridge. The report omits raw transcripts by
default. A lack of records means no recorded evidence, not zero historical usage.

`python3 scripts/usage_summary.py --repo .` lists the recorded invocations per task and per
model and effort: review rounds, verdicts, duration and rejects. A round is a completed
review whose dispatch chain also completed; a verdict is read only from an archive that
still matches its record's sha256. Worker and sub-agent errands write no record, so they
are not in it.

The summary also measures each reviewer configuration (model, effort, backend):

- `findings` counts the list items under each archive's Findings heading; `per_round`
  divides them by the rounds. A configuration whose new findings per round fall toward
  zero while the rounds continue is re-reviewing what it already said.
- `accepted=A/T (rate, author-claimed)` comes from the author's `REVIEW_DISPOSITIONS`
  file of the next round under the same label: each finding is answered with one key,
  `fixed:<commit>`, `disproved:<evidence>` or `deferred:<issue or decision>`, one answer per
  line (a file without a key is refused before any model runs; the file is read once, before
  launch, so editing it during the review changes nothing). Accepted = fixed + deferred. The counts are
  credited to the round the dispositions answer, so the rate belongs to the configuration
  that produced the findings. The author rates its own reviewer, as Google's Tricorder has
  the developer click "not useful"; the next round's reviewer verifies every disproved
  claim against the code, and a claim it rejects comes back as a finding. The rate is
  information for the owner, never an automatic switch: after about twenty rounds of one
  configuration, the owner reads its rate together with how the verifying rounds treated
  its disproved claims and decides whether to keep, change or retire it.
- A configuration under trial runs in shadow first: `REVIEW_SHADOW=1` on the review
  archives its verdict with a `SHADOW REVIEW` banner, records `shadow` in the task, and the
  summary lists it in its own `/ shadow` group with its findings and as no round. A shadow
  run is no round of the change: a later real review under the same label does not carry
  it, and the lead's closure reading of the summary leaves it out. The real review of the
  change still runs. After ten to twenty shadow runs the owner compares its findings with
  the real reviewer's and decides whether it goes live.

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

Each review attempt has a total wall-clock limit (3600 seconds by default, maximum 7200,
`REVIEW_TIMEOUT_SECONDS`) and a Claude review a turn limit (200 by default, maximum 500, `REVIEW_MAX_TURNS`);
Claude proposals retain their separate 600-second default. This is not an inactivity or
connection timer: the current Claude final-JSON adapter cannot reliably distinguish silent
active work from a stalled request. Output does not reset the deadline. A fallback attempt
gets its own deadline, so two default review attempts can take roughly 120 minutes plus
local processing and quota-observation overhead. Each invocation also has an 8 MB
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

Individual adapters never automatically retry, buy credits, switch models, or promote a
failed review to approval. Only when `--fallback` is passed does the wrapper's
dispatcher try the other configured model once after operational unavailability; that
record carries `review_fallback_from`. A cancelled attempt is recorded as `cancelled`. Each attempt keeps its own `.myagentkit/usage/*.json`
record, with `review_chain_id` and `review_attempt` linking it to the invocation. Immutable
checkpoints under `.myagentkit/usage/chains/` contain references to these records, not
additional token/cost charges. The usage reporter reads only top-level provider records;
it does not count chain checkpoints as calls. Unknown or partial usage remains unknown or
partial even when the second provider succeeds. Requested/actual reviewer, failure reason,
configured pins, and final outcome remain visible in the chain.

If both providers fail, structured recovery instructs the host to record the blocker and continue
independent authorized work. Optional coding assistance can fall back to host implementation.
Required independent review cannot fall back to self-approval: its protected commit/push
remains blocked until the review gate is satisfied. If all remaining work depends on the
missing response, return the blocker rather than wait forever. This is a host workflow rule,
not an autonomous background job or an operating-system enforcement of commit policy.
