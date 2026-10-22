<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->
<!-- Do not edit it: a project that needs a different rule writes it in `docs/WORKFLOW.md`, the project-owned file, and the project file wins over this one. -->
# Cross-model usage and recovery

Both supported CLI adapters write one local JSON record per launched invocation under
`.myagentkit/usage/`. Worker cost lives in `scripts/agent_cost.py`; review cost lives here
(KARARLAR D06 inv2#55). This directory is ignored by Git: raw provider output and account
diagnostics are local operational evidence, not material for a public push. Back it up
privately if you need retention across machines. Preflight refusals launch no child and
are not counted as billed invocations.

Both direct adapters and the dispatcher verify private storage before model work. The
usage directory and each review/proposal archive must be Git-ignored; existing raw records
must not be tracked. Symlinked storage is rejected. Publication checks the rules again,
and temporary archive content is staged inside the ignored usage directory. Existing
projects must merge the ignore rules and complete companion list in `docs/DEV_SETUP.md`
before using either the wrapper or the standalone plugin adapters.
Sources (D09 inv2#53): [gitignore](https://git-scm.com/docs/gitignore) describes ignored untracked files;
[git ls-files](https://git-scm.com/docs/git-ls-files) distinguishes cached and other files.

## Attribution and reports

For Claude-host Codex reviews, set `MYAGENTKIT_REQUESTER=claude/ACTUAL_MODEL` and
`MYAGENTKIT_TASK_ID=STABLE_TASK_LABEL` when running `scripts/review.sh`. The caller model is
reported metadata, never an attestation. If absent, it stays unknown. For Codex-host Claude
calls, pass `--requester codex/ACTUAL_MODEL --task-id STABLE_TASK_LABEL` to the bundled
`claude_bridge.py`. Reuse the task label across review rounds: the next round's prompt carries
the earlier completed reviews with that label (`docs/REVIEW_RUNNING.md`).

```sh
# native Windows: python instead of python3
python3 scripts/agent_usage.py --repo .
python3 scripts/agent_usage.py --repo . --task-id STABLE_TASK_LABEL --json
```

In the kit checkout, use `core/scripts/agent_usage.py`; an installed Codex plugin also has
`scripts/agent_usage.py` beside its bundled bridge. The report omits raw transcripts by
default. A lack of records means no recorded evidence, not zero historical usage.

`python3 scripts/usage_summary.py --repo .` lists the recorded invocations per task and per
model and effort: review rounds, verdicts, duration and rejects; `--task LABEL` limits it to
one label. Rounds are numbered per `REVIEW_FOCUS`, as the two-round cap counts them. A round
is a completed review unless the checkpoint its dispatcher wrote after it says the chain
failed, the same rule the two-round cap uses (`docs/REVIEW_GATE.md`, "Rounds"); a verdict is read only from an archive that
still matches its record's sha256; a record from before v0.9 has none, so its verdict is read
unverified and marked `hash=none`, and an archive whose recorded absolute path is gone (a moved
or recloned checkout) is read from `docs/reviews/<name>`. Worker and sub-agent errands write no record, so they
are not in it.

The summary also measures each reviewer configuration (model, effort, backend):

- `findings` counts the severity-first list items under each archive's Findings heading
  (both reviewers are asked for exactly that form), repeats of still-open findings included;
  `per_round` divides them by the rounds. Read it with the archives: a configuration whose
  listed findings per round do not fall while the rounds continue is re-listing what it
  already said or is not being fixed.
- `accepted=A/T (rate, author-claimed)` comes from the author's `REVIEW_DISPOSITIONS`
  file of the next round under the same label: each finding is answered with one key,
  `fixed:<commit>`, `disproved:<evidence>` or `deferred:<issue or decision>`, one answer per
  line (a file without a key is refused before any model runs; the file is read once, before
  launch and handed to every attempt, so editing it during the review changes nothing; a
  line without a key, a heading or blank line excepted, is recorded as `unkeyed`). Accepted = fixed + deferred.
  The answers refer to every earlier round under the label, so the counts are split over
  those rounds by the findings each listed, and the rate belongs to the configurations that
  produced the findings. The author rates its own reviewer, as Google's Tricorder has
  the developer click "not useful"; the next round's reviewer verifies every disproved
  claim against the code, and a claim it rejects comes back as a finding. The rate is
  information for the owner, never an automatic switch. The summary prints decided findings
  as `n`, `rated_rounds` with credited answers, and a two-sided 95% Wilson interval.
  The owner uses a rate for a decision only at `n >= 30` from at least ten distinct rated
  rounds; smaller samples stay descriptive. These floors are the owner's choice, not
  measurements (KARARLAR B03 inv2#57/#58/(d)); the interval follows
  [NIST, section 7.2.4.1](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
  The latest completed round's cumulative answers replace earlier snapshots under its label
  and `REVIEW_FOCUS` (a focus answers its own and the unfocused rounds, an unfocused round
  only the unfocused ones), so answering the same findings again cannot increase `n`; the
  newest file wins a round two focuses answer. A file that answers fewer findings than the
  one before it is not cumulative, and the summary prints a `Note:` line for it. Allocation across earlier
  configurations follows their finding counts; fractional `n` and its Wilson interval are
  descriptive estimates, not independent, individually matched finding outcomes.
  The owner reads the archives and how later reviewers treated disproved claims before
  deciding whether to keep, change or retire a configuration.
- A configuration under trial runs in shadow first: `REVIEW_SHADOW=1` on the review
  archives its verdict with a `SHADOW REVIEW` banner, records `shadow` in the task, and the
  summary lists it in its own `/ shadow` group with its findings and as no round. A shadow
  run is no round of the change: a later real review under the same label does not carry
  it, and the lead's closure reading of the summary leaves it out. The real review of the
  change still runs. Task, Total and Behaviour lines print a separate `shadow=` count and
  exclude shadow verdicts and findings from their real-review rates (BACKLOG B9).
  The same decided-finding and distinct-round floors govern a shadow comparison; run count
  alone cannot qualify it (KARARLAR B03 inv2#58). Shadow runs carry no accepted dispositions,
  so the owner must compare their findings with real reviews before deciding to go live.

`Pair AUTHOR -> REVIEWER` groups use `task.author` and `model_requested`, with the same
author-claimed rates and sample checks. A missing author remains `unknown`; requester
metadata never substitutes for it (KARARLAR B01-1; batch 3 Outside Owns 8).
`quota=` totals `rate_limited`, `quota_exhausted` and legacy `quota` records; the separate
counts retain the distinction (KARARLAR D04 inv2#126; batch 4 Outside Owns 5).
Behaviour on/off groups are observational, not randomized: their differences do not prove
the appendix caused an improvement (KARARLAR B03 inv2#128).

Sources for attribution and grouping: [Claude Code usage events](https://code.claude.com/docs/en/monitoring-usage),
as reviewed in stage 2, D06 inv2#54/#55 (2026-10-15). The optional requested/reported-model
field rename was not adopted. Prior-round carry and verified archives follow
[re-review convergence](https://code.claude.com/docs/en/code-review) and
[fresh reviewer context](https://code.claude.com/docs/en/best-practices)
(D06 inv2#108; B02 inv2#12). Control characters are escaped to prevent forged report lines
([MITRE CWE-117](https://cwe.mitre.org/data/definitions/117.html), B03 inv2#128).

Every record includes task, requester, requested callee model, source revision/hash,
elapsed time, status, failure classification, evidence location, and available usage.
Claude's per-model `modelUsage` is retained; a Codex requested model is not misrepresented
as observed model identity when its JSONL events do not attest the actual model.
Checkout identity covers HEAD, diff, index and tracked/untracked bytes; a rendered diff
alone can miss index flags and hidden changes (KARARLAR D06 inv2#107;
[Git index semantics](https://git-scm.com/docs/git-update-index), stage-2 review 2026-10-15).

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
time around the model invocation). The five-second deadline and 1,000,000-byte response
cap are the owner's choice of telemetry safeguards, not measured vendor limits
(KARARLAR B03 inv2#62; `core/scripts/codex_quota.py`). It starts no model thread/turn and performs no login,
logout, reset-credit consumption, credit purchase, or account mutation request. An
unavailable observation is recorded as unknown and does not prevent the model task.

## Bounded failure, useful continuation

Each review attempt has a total wall-clock limit (2700 seconds by default, 3600 for a high-effort Codex review, maximum 3600,
`REVIEW_TIMEOUT_SECONDS`) and a Claude review a turn limit (200 by default, maximum 500, `REVIEW_MAX_TURNS`);
Claude proposals retain their separate 600-second default. This is not an inactivity or
connection timer: the current Claude final-JSON adapter cannot reliably distinguish silent
active work from a stalled request. Output does not reset the deadline. A fallback attempt
gets its own deadline: two timed-out attempts take about `2 x REVIEW_TIMEOUT_SECONDS`,
plus local processing and quota-observation overhead (KARARLAR D06 inv2#45; B03 inv2/(a)).
With no override, this is about 90 minutes at 2700 seconds per attempt, or 120 minutes
for two high-effort Codex attempts at 3600 seconds; mixed defaults add their own deadlines.
Each invocation also has an 8 MB
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
Process cleanup sources (D01 inv2#66): [Python subprocess](https://docs.python.org/3/library/subprocess.html),
[CPython issue 26534](https://bugs.python.org/issue26534), and Airflow's
[`reap_process_group`](https://airflow.apache.org/docs/apache-airflow/stable/_modules/airflow/utils/process_utils.html).

The 200/500-turn limits, 8,000,000-byte stream cap, and proposal defaults (600 seconds,
12 turns, 3 USD) are the owner's choice of safeguards, not measured provider limits
(KARARLAR B03 inv2#31/#64/#65). The optional `0 < --max-budget-usd <= 100` bound is also
the owner's choice: it catches typing errors, not a vendor maximum (B03 inv2#101).
Reviews omit a default monetary cap because exhausting it pays for a review without a
usable result; proposals are bounded because one invocation should return one patch
(B03 inv3/(j)). Sources: [CLI limits](https://code.claude.com/docs/en/cli-reference) and
[agent-loop budget outcomes](https://code.claude.com/docs/en/agent-sdk/agent-loop),
reviewed in stage 2 on 2026-10-15. Proposal tuning needs recorded turn/cost distributions;
a default is not evidence of a typical run.
The wall-clock bound follows the same timeout mechanism as
[Claude Code ultrareview](https://code.claude.com/docs/en/ultrareview)
(KARARLAR B03 inv2#63, stage-2 review 2026-10-15); output never renews it.

Individual adapters never automatically retry, buy credits, switch models, or promote a
failed review to approval. The wrapper's dispatcher retries a Codex `rate_limited` attempt
at most twice (the delay Codex names, else ten minutes, doubled). It tries the other
configured model once after a failover-eligible failure only when `--fallback` is passed,
with one exception: a Codex `quota_exhausted` switches the role to Claude without it
(`switched` in the chain). That record carries `review_fallback_from`
(`docs/REVIEW_RUNNING.md`, "Unavailable reviewer"). A cancelled attempt is recorded as `cancelled`. Each attempt keeps its own `.myagentkit/usage/*.json`
record, with `review_chain_id` and `review_attempt` linking it to the invocation. Immutable
checkpoints under `.myagentkit/usage/chains/` contain references to these records, not
additional token/cost charges. The usage reporter reads only top-level provider records;
it does not count chain checkpoints as calls. Unknown or partial usage remains unknown or
partial even when the second provider succeeds. Requested/actual reviewer, failure reason,
configured pins, and final outcome remain visible in the chain.

### Failure kinds of a provider error

`agent_usage.failure()` reads only the CLI's structured error fields, never the review's
prose (KARARLAR D04 inv2#126). The two quota kinds:

| `failure_kind` | Meaning | Vendor names and statuses it maps |
|---|---|---|
| `rate_limited` | passes; a Codex attempt is retried | HTTP 429 `rate_limit_error`, 529 `overloaded_error` (Anthropic API errors); Claude Code `rate_limit`; Codex "Selected model is at capacity", "Rate limit reached", "429 Too Many Requests" |
| `quota_exhausted` | used up until a reset or a payment; goes to the owner, never retried | Claude Code "You've hit your session limit", "You've hit your weekly limit", "You've hit your Opus limit", "You've hit your Sonnet limit", `billing_error`, `account_on_hold`; Codex "You've hit your usage limit", OpenAI `insufficient_quota` ("exceeded your current quota") |

An error that names a used-up quota is `quota_exhausted` even with status 429 or a
"try again in" delay: Codex names days there. Sources: Anthropic API errors
(platform.claude.com/docs/en/api/errors), [Claude Code errors](https://code.claude.com/docs/en/errors)
(plan-limit messages, checked 2026-10-16), Claude Code headless error types
(code.claude.com/docs/en/headless), OpenAI error codes (platform.openai.com/docs/guides/error-codes).

If both providers fail, structured recovery instructs the host to record the blocker and continue
independent authorized work. Optional coding assistance can fall back to host implementation.
Required independent review cannot fall back to self-approval: its protected commit/push
remains blocked until the review gate is satisfied. If all remaining work depends on the
missing response, return the blocker rather than wait forever. This is a host workflow rule,
not an autonomous background job or an operating-system enforcement of commit policy.
