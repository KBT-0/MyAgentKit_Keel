# A worker that waits pays for its whole context again — the measured setups

`docs/WORKFLOW.md` (template) states the production rule in one line: a one-hour cache, long
jobs in the background, no polling. This page keeps the whole comparison, because the rule
assumes the one-hour cache is available and the host is Claude Code in a terminal. Where that
is not true, the next best setup is chosen from this table, not guessed.

## The experiment (founding project, 2026-10-03)

The same task in six setups: read three files (context about 100k tokens), wait twice for a
400-second job (a script standing in for a build), four short commands, one answer. Model:
Sonnet 5.5. Measured from the session and sub-agent transcripts, deduplicated by request id.
The cost column is in input-token equivalents (cache read 0.1, five-minute cache write 1.25,
one-hour cache write 2, plain input 1); output is excluded, being equal and small in all six.

| # | Setup | Re-write after each wait | Cache write | Cache read | Cost equivalent | Against baseline |
|---|---|---|---|---|---|---|
| 1 | Sub-agent, blocks on the job, five-minute cache (the default) | 85k + 86k | 256k | 394k | 360k | baseline |
| 2 | Sub-agent, job in the background, re-invoked on exit | 86k + 87k | 276k | 585k | 403k | +12 % |
| 3 | Sub-agent, each wait split into 200-second pieces | 0 + 0 | 86k | 668k | 174k | −52 % |
| 4 | Separate headless session (`claude -p`) | 1.7k + 0.2k | 86k (one-hour) | 514k | 223k | −38 % |
| 5 | Separate interactive session in tmux | 0.2k + 0.2k | 84k (one-hour) | 627k | 232k | −36 % |
| 6 | Sub-agent with the one-hour cache (`CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h`, or `experimental.cacheTtl: 1h` in its definition) | 0.2k + 0.2k | 84k (one-hour) | 554k | 223k | −38 % |

What the rows mean:

1. **The sub-agent's cache expires at five minutes**, and every wait that outlives it ends in
   a re-write of the whole context at more than ten times the price of a read. In the
   founding project's real day, 87 percent of all cache-write tokens were such re-writes.
2. **Backgrounding alone saves nothing.** The agent is re-invoked when the job exits, but
   the wait was still longer than five minutes, so the re-write happens anyway; the extra
   wake-up turn made it slightly worse.
3. **Splitting the wait avoids every re-write**, but each piece is a request that reads the
   whole context. At 100k that read is cheap, so this row wins here; at a real worker's
   300k to 700k it loses, because the reads then cost more than the re-writes they prevent.
   The break-even moves with context size: the larger the worker, the worse this row gets.
4. **A separate headless session** has the main conversation's one-hour cache and a
   `--max-budget-usd` / `--max-turns` cap, but no screen to watch and no idle notice.
5. **A separate tmux session** costs the same, can be watched, survives the lead ending, and
   the lead can subscribe to its idle notice. It needs tmux and a trusted folder.
6. **A one-hour sub-agent** costs the same as a session, needs no tmux and no permission
   decision (it inherits the lead's), but it dies with the lead and reports only to the
   session that spawned it; its definition file is not loaded by a session already running.

Rows 4 to 6 are the same mechanism: a cache that outlives the wait. The one-hour cache
writes at twice the price of a five-minute write, which is the whole of the cost they still
carry above row 3's figure and why they do not reach −52 percent on a small context.

Projected on the measured day (1,824 requests, 336 USD, 87 percent workers): the cache
lifetime alone removes about a third of the worker cost; with fresh workers capped at about
150 requests, 45 to 50 percent. The first real task (2026-10-03, founding project): the same pipeline task as a separate tmux
session (setup 5, Opus, 107 requests, one 496-second background job) against a comparable
sub-agent (setup 1, Opus, 110 requests). Cache write after gaps over five minutes fell from
218k of 442k (49 percent) to 2k of 249k (1 percent): the mechanism works on a real worker.
Cost equivalent, however, came out level (2.44M against 2.40M), because the task had only
ONE wait over five minutes, the one-hour write costs twice the five-minute one on the first
load, and the session started with a larger context (49k against 36k: its own system prompt
and worktree banner) that every one of its 107 requests then re-read. So: the saving is
proportional to the number of waits that outlive the five-minute cache (87 percent of all
writes on the measured day, one wait here), and a sub-agent with the one-hour cache (setup
6) keeps the smaller starting context, so it is the cheaper of the two equals; the session
is for visibility. Both runs were at effort high.

## Which setup, when

| Situation | Setup | Why |
|---|---|---|
| Claude Code host honours the selected one-hour cache, workers that run jobs over five minutes | 6, or 5 when the lead should be able to watch the worker or hand over while it runs | Same cost; 5 adds visibility and survives a lead handoff, 6 needs no tmux and no permission decision |
| The one-hour cache is unavailable: a gateway does not forward `anthropic-beta`, the Claude apps gateway, a Bedrock model without it, or a host without a lifetime setting | 3: split every wait into pieces under five minutes, each piece a separate short command, never a loop in one call | The measured fallback avoids the re-write without the one-hour cache; accept the per-piece read, and keep the worker's context small so that read stays cheap |
| No tmux, no interactive terminal (CI, a server, a scripted pipeline) | 4, with `--max-budget-usd` and `--max-turns` | Same cache as 5, and the only row with a hard budget cap |
| The worker's whole context is small (under about 100k) and the job is short | 3 is cheapest; 6 is simplest | At this size the per-piece reads cost less than a one-hour write |
| The job is under five minutes | 1 is fine | Nothing expires; do not add machinery for a wait the cache covers |
| A different host agent with its own cache rules | Measure first with the method above (same task, each setup, transcripts deduplicated by request id), then fill this table for that host | The numbers here are Claude Code's; the shape (waits times context) transfers, the figures may not |

The `experimental.cacheTtl` definition field is ignored while a subscription uses usage
credits; the kit's `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` variable is not subject to that
exception. Check the recorded write buckets before choosing a fallback
(KARARLAR D06 inv1#161; [Claude Code cache controls](https://code.claude.com/docs/en/prompt-caching),
checked 2026-10-16).

The worker never polls: a poll turn pays for another context read. For a review-fix round,
use [WORKFLOW rule 2](../core/docs/WORKFLOW.md), which routes a small local fix to its author
while the context still fits and sends a redesign or exhausted context to a fresh worker
(KARARLAR D06 inv1#37/#163). The founding project's costly example was one worker resumed
three times, from 36k to 711k over 377 requests (RESEARCH_LOG, 2026-10-03).

## Read the measurements

Run `python3 scripts/agent_cost.py --latest` alongside `/usage` at handoff, with completed
task counts. `/usage`'s Session block covers only the main conversation; the analyzer also
reads worker transcripts (KARARLAR D06 inv1#172/#287;
[Claude Code costs](https://code.claude.com/docs/en/costs), stage-2 review 2026-10-15).
In this kit checkout, the script lives at `core/scripts/agent_cost.py`.

`cWrite>TTL` counts writes after a gap longer than the lifetime reported for that write:
one hour for `ephemeral_1h_input_tokens`, five minutes for `ephemeral_5m_input_tokens`.
Mixed writes use each bucket separately; legacy unbucketed writes assume five minutes.
This is a gap diagnostic, not proof of the cause of a miss (B03 inv2/(h), cache source above).
The historical experiment above still reports gaps over five minutes for comparison;
its figures were not recomputed with the new analyzer.

The initial 80% cache-hit alarm is the owner's choice, not a target or a measured optimum.
Record the median of the kit's first ten workers as its baseline; investigate lower hits
with `cWrite>TTL` and `poll` (KARARLAR B03 inv1#173). No new baseline was measured in this batch.

Reusing a session depends on its actual cache lifetime: one hour on included subscription
usage, otherwise five minutes unless explicitly set to one hour. An idle session past
that lifetime has no warm cache to preserve (KARARLAR D01 inv1#191; cache source above).
The fork threshold of 120k and a few requests (about eight) is the owner's choice,
not a measured crossover; compare total lead-plus-worker usage before changing routing
(B03 inv1#186/#187; [subagent mechanisms](https://code.claude.com/docs/en/sub-agents),
stage-2 review 2026-10-15).

## What the alternatives to the rule set were, and why they were not taken

From the same research pass, each with its evidence, so the next pass does not re-litigate:

| Problem | Options seen | Evidence | Taken |
|---|---|---|---|
| A worker that waits re-writes its context | (a) the cache-lifetime setting or `experimental.cacheTtl: 1h` in the worker definition; (b) a separate session; (c) keep-alive plugins | (a) official docs, and one user's repository measuring sub-agent re-reads from 28 to 1.3 percent; (c) tiny repositories that burn subscription quota | (a) now, in the definition; (b) as a measured pilot; (c) no |
| A worker waits on or polls a long job | background commands with re-invocation; a monitor tool; a CI-event channel; one script that makes the job a single command | official docs; poll-loop failure reports | one proof command, in the background; rule: no polling |
| A worker grows without bound | `maxTurns` in the definition; a context-threshold warning hook; rotating workers at 60 to 65 percent fullness | official docs; the others are experience reports without measurement | `maxTurns` about 150 turns as a backstop (owner's choice, KARARLAR D06 inv1#164); fix routing follows WORKFLOW rule 2 |
| Nobody sees where the money goes | the built-in usage screen; a usage CLI; status-line scripts; OpenTelemetry; transcript analysers | all show spend, none reduce it | the kit's own analyser, run at the end of the day |
| How the lead runs its workers | sub-agents; separate sessions (`--bg`, tmux, worktrees) with cross-session messages; agent teams (experimental, about seven times the tokens); scripted workflows | no comparative measurement found; practitioners stay at three to five parallel agents and name review as the bottleneck; a message to an idle session is a full-context turn | sub-agents stay; separate sessions for long pipeline tasks, measured |
| Tool output fills the context | output compressors; an output-filter hook; context-mode tools | the leading compressor's own README: output reduction is not bill reduction; all tool output in the measured day was about one million tokens | not installed; long output goes to a file |
| Session memory and handover | handoff skills, spec kits, memory plugins | no measured cost effect; memory plugins have added-cost reports; spec kits cost more on small tasks | the existing state file and handoff template stay |
| Shorter output packs | terse-style prompt packs | one author claims 65 percent, an independent measurement over 86 tasks found 8.5 percent; output is about three percent of the bill | not installed |
| A budget ceiling | `--max-budget-usd` and `--max-turns` (headless only); an open feature request for interactive sessions | official docs | used on headless and background sessions |

## The failure mode it prevents

A project that cannot use the production rule (the gateway cannot honour its chosen TTL,
its host has no such setting, it runs workers from CI) falls back to the setup that looks
cheapest — backgrounding the job, or polling it in small pieces at a large context — and
pays the baseline or worse while believing it has applied the fix. The table above makes
the fallback a measured choice with a known price, and the method a way to re-measure it
on a host the numbers here do not cover.
