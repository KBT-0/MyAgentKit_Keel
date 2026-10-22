<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->
# Development Workflow — the rationale

Why the rules of `docs/WORKFLOW.md` are what they are: their sources, the measurements behind
them, the long examples and the full text of the kit's worker mechanics. The headings are
`docs/WORKFLOW.md`'s, and a section there whose reasons are here ends with a "Why:" line that
names its heading. The rules, the owner's decisions and every choice a project makes stay in
`docs/WORKFLOW.md`; this file is the kit's, and a sync replaces it.

## How we work — roles

Every review's usage record notes `behaviour: on` or `off`, and `scripts/usage_summary.py` totals
the rounds and rejects of each side. A resumed session keeps the system prompt it started with,
so an A/B counts only sessions started fresh on its side (code.claude.com/docs/en/cli-reference,
"System prompt flags in resumed conversations"). `BEHAVIOUR.md` is unmeasured: the on/off toggle
and the usage record exist so the A/B can decide, and until it runs the appendix is the owner's
choice. It holds only lines `AGENTS.md` does not already say in the same words.

## Task ids

Finished work that nobody deleted is how `docs/STATE.md` rots: a project's state file held
lines like "Committed: K4" and "merged after three review rounds" long after the work was in
git, and a size limit could not tell those lines from live ones. A task id makes the
deletion checkable.

## The state, backlog and phase files

The order is `docs/AGENTS.md`'s; these are its reasons. The hash and the bytes come from one
read: a hash read apart from the bytes it names let a copy read at the session's start pass
over an edit published in between. The helper compares under the same lock as a mode switch and
replaces the file atomically, keeping a successor at the supplied path, because publication and
rollback could otherwise erase another writer's work. A snapshot lives only in `.myagentkit/`
(ignored by Git) or the temporary folder, because `/myagentkit:mode` runs the helper unprompted
and a snapshot elsewhere can land where `git add -A` commits it; OUT is a name prefix and FILE a
regular file, because OUT naming `.myagentkit` put the snapshot in the project root and FILE
naming a folder moved it whole. The "Working mode:" line is the mode switch's, which writes it
together with `.myagentkit/mode`. Sources: HTTP If-Match (the lost update,
developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-Match), anthropics/claude-code#24130
(an auto-memory file is not safe for concurrent agents), Python `tempfile.mkstemp` (an exclusively
created snapshot; CWE-377).

- `docs/STATE.md` is read at the start of every session, in every tool, so its length is a
  bill paid every session. What is planned next, and what was parked on purpose, is a
  backlog, and it lives in `docs/BACKLOG.md`, which is read only when the next task is chosen.
  A backlog only grows, and in STATE.md it is read every session for nothing. STATE.md holds
  current state only, and traps live in `docs/GOTCHAS.md`: every line read at session start
  costs on every session (code.claude.com/docs/en/memory), and a working list is rewritten,
  not appended to (Manus, "Context Engineering for AI Agents"). An empty Active work section
  means nothing is in flight, a contract the gate does not check.
- **Why the tool+model trace.** Record which tool and model did the work, so a later session
  can tell who wrote a change (the author never reviews it) and where the cost went. The
  trace is kept in STATE.md, not in git, because git carries no AI attribution; the Linux
  kernel's `Assisted-by:` trailer (docs.kernel.org/process/coding-assistants.html) is the
  opposite placement, which the owner's no-attribution rule rules out.
- Updating STATE.md at the end of a session is the agent's job: a long-running agent leaves
  its progress file for the next session, which starts with no memory (Anthropic,
  "Effective harnesses for long-running agents").
- A `[LESSON]` or `[GOTCHA]` tag makes harvesting a grep, not a re-read. Deleting a tagged
  line before it has a home is caught only as a NOTE (`scripts/check.sh`); the rest is
  discipline.
- Pruning without harvesting buries the lesson in the git history, and nobody looks there —
  git is an audit trail, not a knowledge base. A context that is rewritten whole loses detail
  ("context collapse", Zhang et al., arXiv:2510.04618), so a lesson is moved, not summarised away.
- Completed work is deleted, not marked DONE: the dates live in git
  (`git log -p -- docs/STATE.md`). The state templates name no example task id, because
  those files are the ones checked ("Task ids"). No outside kit enforces the deletion; the
  check is the kit's own lesson (its RESEARCH_LOG, 2026-10-03).

- No size limit applies to STATE.md. A limit cannot tell a live line from a finished one,
  and a project that added one hit it again and again while half the file was backlog and
  much of the rest narrated work already in git. What keeps an always-read file useful is
  what it holds, not a line count: a long or conflicting file is followed less
  (code.claude.com/docs/en/memory; IFScale, arxiv.org/abs/2507.11538).

**The non-goals are the useful half.** "Build the inventory system" gives an agent no edge
to stop at, so it invents scope: it adds persistence, a UI, an event system, and returns one
monolithic file touching five modules. "Build the grid placement rules; do NOT add
persistence, do NOT write UI" is the same task with a fence around it. Scope invention is
the most expensive habit an agent has, and `docs/PHASES.md` is the cheapest cure.

## Decay early-warning system

Sources: a weakened or deleted test is how agents game a task (Kent Beck, "Augmented Coding:
Beyond the Vibes"; METR, "Recent Frontier Models Are Reward Hacking", 2025), so it stops the
work; the rest is drift that an audit removes in batches (Thoughtworks Technology Radar,
"Architecture drift reduction with LLMs"; GitClear's 2025 code-quality report). File size
predicts defects without a clean threshold
(Yamashita et al., QRS 2016), so the rule names the symptom, not a number.

## Model routing — by cost per task and by scarcity

The review row is `docs/REVIEW_GATE.md`, "Invariant", with its sources (Anthropic's separate
writer and reviewer sessions, `docs/research/ai-review-workflows.md` [1]; self-review's zero
gain measured in the same session, [25]); no source measured the tier order, which is the
owner's choice. The prices behind the table come from third-party summaries of OpenAI's launch figures:
Luna costs about a twentieth of Sol's token price, and Sol 6.1 about a fifth of Astra's.
Neither the per-model Codex allowance nor the quality claims were verified. **The table is
provisional**: API token prices say nothing about how much each model draws from a
subscription's five-hour and weekly allowance. Measure that draw (`/status` before and after
a few errands per model) and move the tiers by it (rule 5).

### Working modes, by name

Without names, the owner explained the same situation in a long prompt at the start of every
session ("Claude is low today, let Codex write and fix"), and a lead that was not told routed
by habit. A name is one word, and a lesson one project learns improves the mode for every
project through the kit. A few named modes the user switches are common practice (Aider's
chat modes, aider.chat/docs/usage/modes.html; Roo Code's modes,
roocodeinc.github.io/Roo-Code/basic-usage/using-modes); what each mode here decides is the
kit's own.

## Worker cost — waits and long lives are what you pay for

### The measurements and the full rules

Measured in the kit's founding project (one lead session with background workers: 336 USD in
eleven hours, 87 percent of it the workers; the transcripts were then counted request by
request, and a controlled experiment ran the same task in six setups). What the numbers say:

- **Within a subscription's included usage, the default cache lifetime is five minutes for
  a sub-agent and one hour for the main conversation.** A worker that waits longer than its
  cache re-writes its whole context on the next request, at
  more than ten times the price of reading it. 87 percent of all cache-write tokens followed
  such a gap: poll loops, a ten-minute job, a wait on a lock, a resume after a handback.
- **Every request re-reads the whole context**, and context grows by about 2k tokens per
  request whatever the tool output size. One worker resumed for three review rounds (377
  requests, context 36k to 711k) was 38 percent of all cache read and 48 percent of all
  cache write.
- **Polling is paid twice**: each poll turn re-reads the context, and the wait then expires
  the cache. Fifteen percent of all cache read went to turns that only waited.
- **A background job alone saves nothing** (+12 percent in the experiment): the wait still
  outlives the five-minute cache. A one-hour cache with background jobs and no polling saved
  36 to 38 percent; splitting every wait under five minutes saved more on a small context but
  pays a full context read per poll, so it loses at real worker sizes.
- **Tool output was not the problem**: all tool results of all agents together were about one
  million tokens. Trimming output is hygiene, a small lever.

Rules, binding for whoever routes workers:

1. **A worker's cache must outlive its waits, and the worker must not poll.** A worker that
   waits on jobs past five minutes runs as a `scripts/spawn_worker.sh` session, the only one
   with the one-hour cache: the session has the project's `promptCacheTtl`, and the launch
   line sets `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h`. The `worker` sub-agent and the lead's
   other sub-agents run on the five-minute default: in one project sub-agents wrote 4.56M
   one-hour cache tokens over 1,582 requests and only 11 gaps passed five minutes (#116); a
   one-hour write costs 2x base input, a five-minute one 1.25x.
   The worker starts long jobs in the background and is re-invoked when they exit, and never
   runs `sleep`, `until`, `pgrep` or tail-the-log loops. `git commit` and `git merge` are long
   jobs too: the pre-commit and pre-merge-commit hooks run the full gate. Claude Code's Bash
   tool stops waiting on a foreground command after 120 seconds by default and moves it to
   the background, so a commit runs in the background or with a `timeout` above the
   project's measured gate time (in one project the gate took a median 167 s, at most 462 s). To react to a log line or a state
   change, use the Monitor tool with a filtered command, not a loop
   (code.claude.com/docs/en/tools-reference). Only a worker definition's
   `experimental.cacheTtl: 1h` is ignored while a subscription draws usage credits; the kit's
   `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` variable is not subject to that exception
   ([Claude Code cache controls](https://code.claude.com/docs/en/prompt-caching),
   checked 2026-10-16). Where the one-hour cache is unavailable (a gateway that does not
   forward `anthropic-beta`, the Claude apps gateway, a Bedrock model without it, or another
   host with no such setting), choose the fallback from the measured table in the kit's
   `docs/worker-cost-setups.md`: usually waits split into pieces under five minutes, at the
   price of a context read per piece.
   A separate, visible session (`scripts/spawn_worker.sh` in a tab or tmux) is for a worker
   that waits on long jobs or must outlive the lead; an ordinary errand runs as a sub-agent,
   and the lead never opens visible sessions to show the workflow, because each one is a
   full session's bill (code.claude.com/docs/en/costs, agent team token costs).
2. **Gate findings go to the author's side**; in saver mode, that is the side that is not
   low. A small, local fix goes back to the worker that wrote the change (a SendMessage
   resume, or the same separate session) while its context is under the context band (rule 8)
   and the fix is not a redesign: a fresh worker re-reads the whole context to change a few
   lines. Otherwise (context past the band, a redesign, or two failed corrections of the same
   finding) a fresh worker takes it, briefed with the findings, the branch and the files to
   read. Inner rounds ("Review inside the worker") follow the same rule. The gate's reviewer
   is a headless process in a throwaway copy, fresh in every round; no session reviews its
   own change, and sending a fix back to its author is routing, not review. The worker
   definition sets `autoCompactWindow` at the band, so a resumed worker cannot grow past it.
   Sources: a resumed sub-agent keeps its cache (code.claude.com/docs/en/prompt-caching);
   after two failed corrections a fresh context does better (code.claude.com/docs/en/best-practices);
   Anthropic's research system hands work to fresh sub-agents near the context limit
   ("How we built our multi-agent research system").
3. **One small task per worker.** Size it to end under the context band (about 200k): the
   worker definition sets `maxTurns` as a backstop (about 150 turns, the tool-using model
   requests `maxTurns` counts; a worker stopped there returns partial output and can be
   resumed) and `autoCompactWindow` at the band (code.claude.com/docs/en/sub-agents). 150 is a
   backstop, not a measured optimum. Split before starting: a mechanism first, then its uses.
   **A sub-agent compacts near 168k.** In one project, 83 sub-agent compactions
   (2026-10-19 to 10-21, the `preTokens` of their `compact_boundary` records; #303) fired at
   165k to 180k of context, median 168k: the definition's `autoCompactWindow` of 200000 less
   a reserve. That is a measured figure, not a documented limit: Anthropic names no point at
   which a sub-agent compacts; the field can only lower the window, and
   `CLAUDE_CODE_AUTO_COMPACT_WINDOW` or `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` overrides it
   (code.claude.com/docs/en/sub-agents, checked 2026-10-22). A worker starts near 49k (its
   definition, `AGENTS.md` and the brief), so about 120k of reading and work fit before the
   first compaction. The two #303 workers were compacted twice before their first edit
   (peaks 165.7k and 166.8k); the 79.8k and 77.9k read as their peak were their last
   request, after the second compaction. So a sub-agent's brief is sized to those 120k: one
   file group per task, the design already done by the lead (`docs/HANDOFF.md`, "The brief",
   **Design:**), the files and lines to read named in the brief, never "read the module and
   design first". Work that needs more reading is split, or runs as a separate session ("The
   shape follows a threshold", below). `scripts/agent_cost.py` shows each agent's compactions
   (`cmp`) and its peak context (`ctx0->max->ctxN`); a compaction never ends a worker's task
   (`docs/HANDOFF.md`, the result file).
4. **The lead does not poll either.** It waits for task notifications or the exit of a
   background command that watches the disk: `scripts/watch_workers.sh` for a separate session
   (an idle notice is optional and never relied on alone: "The disk is the done signal", below), a log
   watch for a review started in the background (`docs/REVIEW_RUNNING.md`, "Running it"). It
   does not check on workers or CI in a loop (a background sub-agent notifies on completion,
   code.claude.com/docs/en/sub-agents).
5. **Mechanical work goes to the cheaper model at medium effort**: doc fixes, running a
   documented proof, folding notes. Design-bearing code gets the strongest model at high
   effort; reviews follow the "Model routing" effort table. Model and effort are never left
   to inheritance: an omitted sub-agent model resolves to the main conversation's
   (code.claude.com/docs/en/sub-agents, "Choose a model"), a sub-agent runs at its
   lead session's effort unless its definition sets `effort:` (the Claude Code overlay's
   `worker.md` and `diff-reviewer.md` do, as a fallback), and nothing in its output shows
   which one it got. The lead passes `model` and `effort` on every Agent call; the Claude Code
   overlay's `guard_worker_route.py` hook refuses one that lacks either (a fork excepted, it
   cannot change them). A separate
   session takes `scripts/spawn_worker.sh --model --effort`, which refuses a spawn without
   them; a Codex errand (`codex exec`) takes the model and `-c model_reasoning_effort`, and
   `scripts/spawn_codex.sh --model --effort` refuses a Codex worker without them. The brief states model and
   effort, and the lead verifies both in the transcript after the run, not in the report.
   Prefer a named sub-agent definition whose frontmatter fixes `model` and `effort`; the
   guard remains for calls that name a generic agent. `CLAUDE_CODE_EFFORT_LEVEL`, if set,
   overrides the definition's effort, so the lead checks it is unset before relying on the
   field (code.claude.com/docs/en/sub-agents; code.claude.com/docs/en/model-config).
6. Rule 6 is in `docs/WORKFLOW.md`, "The measurements and the full rules", whole.
7. **Worker reports are short** (about 350 words), and long output goes to a file with a
   summary line: the lead pays for a report again on every later turn. A separate spawned
   session writes its report to the result FILE its brief names. A sub-agent cannot: Claude
   Code refuses its write of a report file ("Subagents should return findings as text, not
   write report files"), and a worker briefed for a `REPORT.md` spends turns working around
   the refusal. A sub-agent keeps its short report in its final message and writes only
   logs, tables and captures to files. Sub-agents return a summary, and many detailed returns
   fill the caller's context (code.claude.com/docs/en/sub-agents); Anthropic's research system
   passes references to files instead (its multi-agent research post). "About 350 words" is
   the owner's choice. A failed attempt (a result file with another `Kind`, a sub-agent's final message reporting the task not done, or an exit with neither) is reported to the owner
   at once, with its cost row (`docs/COMMUNICATION.md`, "Workers").
8. **The lead session is compacted or handed over before it grows**, and at the end of a
   working day it reads `/usage`'s Session block (the main conversation only, not
   sub-agents) and runs `scripts/agent_cost.py --latest`, and writes both into the handoff
   next to the number of tasks done, so the next routing decision is made from a number
   (code.claude.com/docs/en/costs). The table's `hit` column (cache reads over all input) is
   the figure to watch. An initial hit below 80% is an alarm, not a target (the owner's
   choice, KARARLAR B03 inv1#173). Record the median of the kit's first ten workers as the
   baseline; investigate lower hits with `cWrite>TTL` and `poll`. The analyzer compares each
   write bucket with its recorded TTL (B03 inv2/(h)); a gap is diagnostic, not proof of the
   cause of a miss. The line
   is a band of context, the same for every model: **yellow at 200k** (plan the cut: no new
   round, let the running batch finish, commit, keep STATE and the handoff current), **red at
   300k** (cut at the next clean stop), **ceiling at 400k** (stop now and secure the work).
   Quality, not only cost, sets it: accuracy falls as context grows and compaction is lossy
   (Anthropic names no number); practitioners cut between 120k and 400k; at today's cache
   prices a fresh session pays itself back in about 25 requests from 200k (Opus, Sonnet) or
   49 (Fable). The numbers are a judgement, not a measurement (the kit's
   `docs/research/context-limit.md`). A symptom cuts at any size: the owner corrected the
   same rule twice, or the worker-route hook refused twice. The Claude Code overlay's
   `context_size.py` hook names the band once per 50k step past 200k (the step is the owner's
   choice, like the band), at a prompt and after a tool call, so a long turn meets it too;
   the lead then
   recommends one of two, with the number and the reason. The overlay's `autoCompactWindow`
   of 450k is only a safety valve for a session nobody stops, never the cut; after any
   compaction its `after_compact.txt` hook names what to re-read. **Compact** when
   `docs/STATE.md` and the open operation files already hold what matters and the work in
   flight continues: one summary turn is cheaper than a handoff note plus a cold start, but
   only while the cache is warm; a session resumed after more than an hour writes a summary into the
   handoff first, since its context is re-written at full price on the next request anyway.
   Never a bare `/compact`: `/compact keep the open decisions, the binding rules, the changed
   files, the next step and the owner's words verbatim`. A session compacted once hands off
   instead of compacting again, since a summary of a summary drifts.
   **Hand off** (update STATE, write the handoff, `/clear`, start fresh) when the work
   changes direction, a batch has just closed, or most of the context is the detail of
   finished work that a summary would still carry. A Codex lead sets
   `model_auto_compact_token_limit` to 200k–250k in `~/.codex/config.toml` for the same
   line. At red the lead stops at the next clean point and proposes a hand-off or `/compact`,
   because a session end kills the background jobs started from its tool shell (survivors:
   `docs/GOTCHAS.md`, "Background jobs die with the session and in a low-memory reap"); the owner
   decides at that stop, never mid-flow. With the owner away, the lead writes the hand-off
   file, runs `/compact` when jobs are in flight, and continues; it does not wait for an
   answer (`docs/COMMUNICATION.md`).
   A worker session uses the same absolute band: `scripts/watch_workers.sh --context-warn`
   warns at the smaller of 200k and 50% of the window (`NNNk` or `NN%` changes it).
   A sub-agent compacts near 168k, before the red band (rule 3), and its compactions never end
   its task.
   The lead keeps big output out of its own context: logs, diffs and images go to
   files and it reads the summary line; long reads go to a worker that returns conclusions;
   independent calls go out in one turn.
9. **A worker runs the cheapest check that proves its change; the expensive step runs
   once.** The commit gate, `./scripts/check.sh` through pre-commit, always runs; the brief's
   **Proof:** line names what the worker runs for its claim beyond the gate, never instead of
   it (`docs/HANDOFF.md`, "The brief"), and with none named the gate alone is the proof. The
   expensive integration step outside the gate, a full build or package step, runs once, in
   the integrating session, after the merge: in one project every
   worker built the whole package in its worktree (7 to 40 minutes each), and the lead built
   it again. A defect only the full build shows is then found at integration. So the
   integrating session builds after each merge when the build is cheap, and names the merge
   that broke it when it is not.

`scripts/spawn_worker.sh` (Claude Code overlay) opens the session with a brief file. By default
it is a Claude Code background session (`claude --bg`, on native Windows and POSIX alike, where
`claude --help` lists `--bg` within 10 s); a Windows Terminal tab (native Windows) or tmux is
the fallback, `MYAGENTKIT_WORKER_HOST=bg|tab|tmux` forces one, and the spawn prints the host it
took. A name a running tab, tmux or background worker holds is refused on every host. The
worker's variables (`MYAGENTKIT_ROLE`) travel in its merged settings, never on the launch line:
the background service a launch starts gives that launch's environment to every later session,
the owner's own too. A background session is keyed on the id
the launch prints (`.myagentkit/workers/NAME.id`), seen in `claude agents` or with
`claude attach ID`, and ended by its detached `codex_worker.py` with `claude stop ID` once its
result is published. Three traps (`docs/research/worker-orchestration-spike.md`): its folder
must sit under a repo root the owner trusted in Claude Code, or the spawn stops with the fix;
a resume passes no flag (a flag starts a copy under the same name); and nothing runs
`claude daemon stop`, which ends every background session on the host. The rest of this
paragraph is the tmux fallback.
Both spawn scripts hand tmux a quote-free `sh PATH` command, with an absolute temporary script path.
They refuse paths containing anything except letters, digits, underscore, dot, slash and dash.
The script is created and checked before any worktree is added, so a refused path leaves no
worktree or branch. If refused, set `TMPDIR` to an existing absolute directory using those
characters and retry; spaces are refused too. This remedy works on macOS and Linux alike.

A committed result file of
`Kind: completed` is therefore the end signal; a file of another kind reports a worker still
working or waiting, and is never a reason to close it. After reading a completed one, the
lead decides per task whether the session is reused or closed. It reuses a session that was
active within its actual cache lifetime when the next task is short or needs most of what
the session holds. It closes the session when no
next task fits what it holds, or when it has been idle past the cache lifetime (nothing warm
is lost then). The main conversation defaults to one hour only within a subscription's
included usage; usage credits, API keys and cloud providers default to five minutes unless
explicitly set to one hour ([Claude Code cache lifetime](https://code.claude.com/docs/en/prompt-caching),
checked 2026-10-16). Closing is automatic: finished worker tabs stayed open for hours while closing
was a step the lead had to remember (2026-10-16). A worker ends its own session once it
publishes a `Kind: completed` result or a decision: `codex_worker.py` supervises every Claude
and Codex worker, so the lead passes `--result FILE` to `spawn_worker.sh` when the brief names
another result than `RESULT-NAME.md`; a progress result or a free-form file ends nothing. When
the lead merges a kit worker's branch (`worktree-NAME`, whose worktree its spawn locked `kit
worker NAME`) and that branch's tip is what the merge merged, not a base another worker built
on, the post-merge hook runs `scripts/close_worker.sh --finished NAME`: it leaves a worker
whose session still runs without a `Kind: completed` result, marked
`.myagentkit/workers/NAME.merged-running`, and a later merge closes it once it has finished. A refused close is printed, never a veto of the merge. The
explicit `scripts/close_worker.sh NAME` stays for a session closed without a merge (work not
merged, a worker without a worktree, a reused session the lead now finishes). It ends the tmux
session (its terminal tab closes by itself), on native Windows the worker's Claude Code session
or the Codex session in its own worktree (the tab's script then ends with `exit 0`, on which
Windows Terminal closes the tab), unlocks the worktree its spawn locked (`kit worker NAME`;
cleanup never touches a locked one), and removes it through the same audit as the
post-merge hook's, for that worktree alone. It never deletes the branch. It ends nothing while
a gate (`check.sh`, by its lock) or a git operation (`index.lock`) runs in the worktree: a
session ended mid-run orphans the run, which then races the next gate there. For the same
reason the lead never ends a worker's `claude` process by hand (Task Manager, `Stop-Process`,
`kill`), and never opens a worker tab by hand (`wt ... claude --resume ID`, `codex resume ID`):
such a tab carries no kit name, so neither the hook nor `close_worker.sh` can close it. A resume
goes through `spawn_worker.sh` or `spawn_codex.sh --resume` under the same NAME. If one was ended mid-run, wait for its `check.sh` to end, or end that process tree
too (on Windows: Resource Monitor, CPU tab, Associated Handles, search for `check.lock`),
before any gate runs in that worktree. On native Windows a worker in a Windows Terminal tab
may not be registered as a peer session; `spawn_worker.sh` then says so, and no idle notice
comes when it stops on a question, a usage limit or an error. Nothing can read the tab's
pane either. `spawn_worker.sh` adds a Notification and a Stop hook to Windows tabs and
worktree workers on either platform through the worker's
`--settings` (the owner's settings and hooks are kept, merged into
`.myagentkit/workers/NAME.settings.json`); they write its state line to
`.myagentkit/workers/NAME.state`: `waiting permission|question TIME ID [context_tokens=N]` when it asks for a
permission, an approval or an answer, `idle TIME ID [context_tokens=N]` when it stops (ID tells two events of
the same second apart). The optional count comes from the last request; compaction resets it
to zero. The watcher labels it using `context_size.py`'s yellow, red and ceiling thresholds.
On tmux it reports each band once per session, including a higher band reached later.
`--context-warn NNNk` changes the snapshot warning count; a percentage also needs a pane
window figure, so a snapshot alone cannot establish it. These notices advise the lead;
they never end a worker. Every spawn clears the previous run's state before launch.
`scripts/watch_workers.sh --result NAME=PATH NAME`, run from the same
checkout, reads that file in place of a pane on Windows: WAITING, then the result file as on tmux, then
IDLE (it stopped with no new result), each event once. Legacy `waiting input` means an idle
prompt, with no state event; the watcher never reports WAITING for it. Once per worker it
prints "hook is from an older kit; re-spawn to install the current one".
A worker name uses letters, digits, `-` and `_`, not starting with `-`; both scripts refuse
any other. Spawn bounds the longest generated filename (`NAME.state.XXXXXXXX`) at 255 bytes
(240 name characters). On native Windows it also bounds the full generated path at 259
characters (MAX_PATH 260). Use a shorter name or checkout path; LongPathsEnabled enables
long-path tooling, but spawn retains this portable bound.
A state file the watcher cannot read or understand is exit 3 (it names the file: delete it).
An absent or zero-byte file is no signal yet; a NUL-only file is invalid (exit 3).
The watcher reads the state once and checks size and content from the same byte snapshot.
The folder-trust dialog writes no state line, so the folder must be trusted
already. The lead still looks at the tab after every usage-limit reset. What `close_worker.sh` does NOT see, so
the lead closes only a worker whose result says it is done: a gate or a commit that starts
in the instant between its last check and the kill; a commit waiting in a project's own
pre-commit hook before the gate takes its lock, or in an editor; and a worker whose checkout
is not the one the close runs in (run it from the lead's checkout).

The Codex case of "A stopped worker is answered in its own session" (`docs/WORKFLOW.md`,
"The measurements and the full rules"):

- A Codex worker (`scripts/spawn_codex.sh`) is resumed: the lead writes the answer to a file
  and runs `scripts/spawn_codex.sh NAME ANSWER_FILE --model M --effort LEVEL [--worktree]
  --resume`. The spawning checkout records `.myagentkit/workers/NAME.session`, outside
  the worker; successful `close_worker.sh NAME` removes that record, and on native Windows
  ends a Codex session still running in the worker's own worktree (one spawned without
  `--worktree` shares this checkout, where any Codex session matches: there it refuses). The
  wrapper closes a worker on its own only when the result starts with the four header lines
  (`docs/HANDOFF.md`); spawn's instruction names them. It also refuses while the
  worker's decision file waits for its answer. The default result is
  `RESULT-NAME.md` at the worker's repository top, and the decision file is `QUESTION-NAME.md`.
  The lead never commits the default result: the close moves it to
  `.myagentkit/workers/NAME.result.md`, so the audit can remove the finished worktree. A move
  that stopped after the report left its path leaves `.myagentkit/workers/NAME.report-move`,
  naming its source and target, and every later close of NAME refuses until the lead puts the
  report back at one of them (a `.report-move-*` folder beside either holds it), removes the
  marker and closes again.
  `--result FILE` selects another `.md` result inside the worker's folder (Codex's
  workspace-write sandbox and Claude Code's worktree isolation refuse a write outside it;
  the `.md` suffix and the QUESTION name are the kit's contract) and `FILE.question.md`;
  the brief must use that spawn-time path, and it is passed again on resume. Publish a question
  or finished result atomically: write a temporary file beside it, end with
  `<!-- codex-worker: ready -->`, then rename it into place with `codex_worker.py --publish
  TEMPORARY_FILE DESTINATION` (spawn's instruction names it; it refuses a file without the
  marker, which the supervisor would never see), which retries for about two
  seconds a rename Windows refuses while a poll reads the file, and end the turn immediately.
  `codex_worker.py` allows ten seconds for the turn to flush (`KIT_WORKER_GRACE` overrides
  the grace period), then closes only that worker's process tree, using a Windows job or
  an interactive POSIX process group. Windows children start suspended until assigned to
  their job; POSIX escalation signals the entire group. `-s workspace-write` and `-a never`
  are the unattended sandboxed use Codex documents (learn.chatgpt.com/docs/agent-approvals-security);
  `--no-daemon` keeps the worker's runtime separate from the shared background server of
  Codex 0.157 and later (not in the official docs; a secondary source), so it is re-checked
  with `codex --help` when the version changes. The script refuses a
  resume while the old session still runs, and refuses a
  fresh replacement when its session or question record exists. On resume the wrapper removes
  the answered question file once the resumed session publishes a new result or exits
  cleanly, never on elapsed time; a failed launch, or a CLI that fails without a new result,
  keeps it for the retry. The result retains the question history.

**A cut-off worker is resumed in place, never restarted.** When a worker's session is cut off
mid-task (its host session ended, its pipe closed), the lead resumes that same session: a
Codex worker by `scripts/spawn_codex.sh ... --resume` with a file that says to continue (the
id is in `.myagentkit/workers/NAME.session`), a bare `codex exec` errand by `codex exec resume
<session id>`, a Claude worker by `scripts/spawn_worker.sh ... --resume <session id>`. A fresh session with a
takeover prompt re-reads everything, loses the session's reasoning and redoes finished parts.
Only when a resume is clearly worse (its context spent, the session corrupt) does a fresh
session take over, from a `Kind: handoff` result the old session writes when it still can
(`docs/HANDOFF.md`).

**The lead commits a Codex worker's work (#43)**, and every `codex exec` errand's. The
worker's brief instructs it to leave
all work uncommitted and ready for the lead. Its result lists the exact changed and added
files and their verification. The lead reviews the diff through the normal cross-review,
then stages those files and commits in the worker's worktree; the commit gate runs as usual.
Codex 0.162 on native Windows keeps Git metadata read-only even with `--add-dir`, so
`spawn_codex.sh` does not add Git directories as writable roots. If the worker cannot take
the gate's Git-directory lock, it records that limitation; the lead runs the gate when
committing. Never bypass the gate or switch to full access for this failure.

For Codex, the lead runs the `codex_worker.py --wait FILE --since START --stale FILE_ID --exit RECORD`
command printed by spawn as a background command, also when spawn found no session. Its exit
notifies the lead of DONE, BLOCKED, HANDOFF or PROGRESS after a result from this run is
published with the end marker (by a rename over an older result), and of EXITED when the worker
stopped without publishing one, even when its wrapper was killed; no commit or lead polling is
needed. `--since` (the launch time) is required. With neither the `.live` nor the exit record
300 s after the launch, the wait ends with NOT STARTED: the tab or session failed before the
supervisor ran; the lead looks at it, and running the same wait again is safe. After PROGRESS or HANDOFF the worker goes on, and `--wait` prints its exact follow-up
command (`--stale` set to the reported result's content hash, the same `--since`; other
contents count as new, by rename or by in-place rewrite, and a byte-identical republication
does not): the lead runs that one next, since spawn's command would return the same result
at once. A spawn that found no
session keeps the checkout's `.myagentkit/workers/spawn.lock` reservation with the worker's name
inside, and refuses every other spawn there. The printed `--resume SESSION_ID` of that name
records the launch and takes the reservation over; once the tab or tmux session has ended, or
the id is written to `NAME.session`, `rm -r .myagentkit/workers/spawn.lock` releases it.
The wrapper closes the worker after the grace period only for a decision
or a completed result. The lead reads the
uncommitted result and diff before committing. The watcher below accepts committed Claude
results; it is not used for the uncommitted Codex handoff.
The result file starts with a fixed head (`docs/HANDOFF.md`): `Kind:`, `Task:`, `Attempt:`
and `Remaining:`, and only `Kind: completed` is done. The lead runs `scripts/watch_workers.sh
--result NAME=PATH NAME` as a background command, and starts it again after every report
but DONE and GONE while work remains, and after its window ends: it stops at its first
report. When the lead itself runs unattended (`-p`, the SDK, CI), it passes `timeout` when it
starts the watcher in the background: the default background limit there is 30 minutes and
the maximum two hours (code.claude.com/docs/en/tools-reference). It returns DONE, BLOCKED,
HANDOFF or PROGRESS once the file is committed on a clean tree, QUESTIONS when the file holds
open questions, CONTEXT when the session's context passes the warning line (the smaller of
200k and 50% of the window by default, rule 8), WAITING on a dialog, and GONE. The lead acts on the report's first line
("The lead's steps when a branch is ready"). Exit 3 means the watcher could not observe:
a pane of a session that exists could not be read, or tmux could not say whether it exists
(`watch_workers: NAME: capture failed: ...` on stderr), or a committed result could not be
read (`... could not read the committed result ...`), or a report could not be written
(`... could not write its report ...`). The lead reads that stderr line, fixes what it names (or
looks at that tab itself) and reruns the watcher. In a run with several sessions, the GONE and
WAITING lines print first, then the result and context lines.

`close_worker.sh` waits up to 15 seconds for the session and the processes inside the worktree
to be gone, then runs the audit below with one change: it lifts the quiet period
(`--no-quiet`). The quiet period stands in for "no worker is still in it"; here the lead has
just ended the session and decided the work is finished, so it is not needed. The post-merge
hook never lifts it. A worktree any other proof cannot clear is kept, with the reason, and
the script exits 1. Closing the session with `tmux kill-session` alone leaves the worktree. **Once a worktree's branch is merged, the
worktree is FINISHED**: a further round on that task starts a NEW worktree, never the old one. With the
Claude Code overlay, `.githooks/post-merge` removes a finished worktree after the next merge
git completes itself in the main worktree (not a conflicted merge finished with `git commit`,
nor `pull --rebase` or `cherry-pick`), but only when `scripts/clean_worktrees.sh` finds
nothing in it that would be lost: a commit was made in that worktree (its own HEAD reflog) and
its HEAD is in the main branch; every commit a file of its git directory names is held by a
ref of the repository (no reflog, no remote-tracking ref counts), or saved first under
`refs/kit/saved/`; every tracked file is byte
for byte what the index
records; no operation under way; and every file git does not track either in a folder
`.claude/worktree-disposable` lists or byte-identical to main's copy. It never deletes a
branch, and removes nothing while the main worktree's HEAD is detached. That it is no longer in
use is NOT proven (a sub-agent worker holds no process inside it between commands): nothing in
it may have changed for the quiet period (60 minutes by default), a margin, not a proof.
Anything else keeps the worktree with the reason, a squash-merged branch included (its commits
are not in main); `git worktree lock <path>` keeps one the lead still wants. Each removal is
logged first in `<git dir>/kit-worktree-removals.log` and prints the command that brings the
worktree back. `KIT_NO_WORKTREE_CLEANUP=1` turns the hook off; the script without `--apply` is
a dry run.

## Review rounds — early, inside the worker, in parallel

In one project a feature took five fix rounds in about seven hours. Each round cost a fresh
worker re-reading 100k to 300k tokens (20 to 60 minutes), a ten-minute gate run, reviews of
5 to 15 minutes and a merge with another gate run. Most findings of rounds 2 to 5 sat in code
the previous fix had added, in classes the reviewers had already shown once. A fix is new,
unreviewed code: 15 to 24 percent of fixes in large systems were themselves wrong (Yin et al.
2011). The rules below
move the review into the worker's warm context and run together what can run together. They
remove no review.

### Design before code

In the kit's own two observed cases a one-page design round took about fifteen minutes where
the same flaws cost hours of code rounds (the kit's RESEARCH_LOG, 2026-10-03).

### Review inside the worker

- Sources: a fresh reviewer step finds what the author missed (code.claude.com/docs/en/best-practices,
  "Add an adversarial review step"); a model correcting its own reasoning without outside
  feedback does not improve (Huang et al., ICLR 2024, arxiv.org/abs/2310.01798), which is why
  the reviewer is new each round.

## MCP hygiene

An enabled MCP server costs little by default in Claude Code: it defers the tool definitions
and loads only the tool names and the server's instructions until a tool is needed. The full
catalogue is paid on every request only where tool search is off (a non-Anthropic
`ANTHROPIC_BASE_URL`, `ENABLE_TOOL_SEARCH=false`, an older model) and on hosts that inline
schemas, such as API gateways (code.claude.com/docs/en/mcp, "Scale with MCP tool
search"; the kit's `docs/research/token-optimization.md`, 1.7). Most custom servers duplicate
what a plain CLI already does more reliably.

## Where the constitution's rules come from

`AGENTS.md` is read every session, so its rules carry no source lines; their sources live
here, by rule. A rule with no source below is the owner's choice or a lesson named beside it.
A citation of `KARARLAR` (Turkish for "decisions"; an item such as `B03 inv2#31` or `D06`)
names an entry of the kit maintainer's decision log, which the kit does not ship: it records
that the rule is an owner decision, and the reason stands beside the citation.

- **Reading order.** The constitution is loaded at session start, so opening it again adds a
  second copy (code.claude.com/docs/en/memory). `docs/ARCHITECTURE.md` is read only when the
  task crosses a module boundary: every always-read line is paid every session, and context
  files that grow lower task success (Gloaguen et al., arxiv.org/abs/2602.11988; matklad,
  "ARCHITECTURE.md"). A reviewer still reads it every time: it is on both bridges' one
  reading list (`REVIEW_DOCS` in `scripts/claude_bridge.py`).
- **Design authority** (DECIDED, OPEN, agents propose, phase scope, a code-versus-PROJECT
  conflict): Anthropic, "Building effective agents" and "Measuring AI agent autonomy in
  practice"; code.claude.com/docs/en/best-practices ("Let Claude interview you", plan mode);
  Nygard, "Documenting Architecture Decisions"; GitHub Spec Kit, `spec-driven.md` (an open
  question is marked, never guessed); Anthropic's prompting guide on overeagerness.
- **Cross-module access through contracts:** OpenAI's harness team enforces architecture
  with linters and structural tests (the kit's `docs/research/agent-kits-in-practice.md`,
  2.2); code.claude.com/docs/en/best-practices.
- **Third-party dependency approval:** models invent package names that attackers then
  register (Spracklen et al., USENIX Security 2025, arxiv.org/abs/2406.10279). The STOP
  for a new dependency or MCP server rests on the same source; a permission `ask` rule on a
  manifest file would make it mechanical (code.claude.com/docs/en/permissions).
- **One task, one module, its `Owns:` paths; no drive-by refactors:** Google Engineering
  Practices, "Small CLs"; Anthropic's prompting guide, "Overeagerness"; tangled refactoring
  in an agent's patch is linked to patches that do not compile
  (Tian et al., "Refactoring Runaway", arxiv.org/abs/2605.22526).
- **No push without the owner's word:** code.claude.com/docs/en/permission-modes and
  /permissions (a push leaves the machine and cannot be recalled); the kit's
  `docs/research/communication-style.md`, recommendation 9.
- **Commit or stash before a destructive git command:** reported agent sessions destroyed
  uncommitted work with `git reset --hard` and `git checkout -- .` (claudeissues.com, issue
  34327); git keeps only committed or staged content (git-scm.com/docs/git-fsck). A recursive
  delete proves ownership by a marker the tool wrote, as `CACHEDIR.TAG` does
  (bford.info/cachedir), because an empty variable once turned `rm -rf "$STEAMROOT/"*` into a
  wipe of a user's files (Steam for Linux, 2015).
- **Never end running work; end the whole tree:** a stopped parent leaves its children
  running (anthropics/claude-code#19045, #27959), and Claude Code's own team and worktree
  docs close a teammate and clean a worktree as one step (code.claude.com/docs/en/agent-teams,
  /worktrees).
- **The gate is wired into git and never skipped:** git-scm.com/docs/githooks; agents were
  seen skipping it with `--no-verify` despite deny rules (anthropics/claude-code#40117), so a
  hook refuses the flag and CI runs the same gate (pre-commit.com).
- **No AI attribution in git:** the owner's policy; the tool's `attribution` setting turns
  the trailer off at its source (code.claude.com/docs/en/settings). Why the trace lives in
  STATE.md: "The state, backlog and phase files".
- **A test in the same change; red proof for gate checks only:** Software Engineering at
  Google, ch. 11 (every change includes its tests); DORA, "Test automation"; the only study
  that measured test-first ordering found no effect (Fucci et al., IEEE TSE, arxiv.org/abs/1611.05994);
  a red proof of every ordinary test is practitioner convention only, and the evidence-backed
  question is whether the test breaks when the code is reverted or mutated (Petrović et al.,
  "Practical Mutation Testing at Scale"); studios validate generated content on its output
  (the kit's `docs/research/test-rules.md`, findings 1 to 11; owner decision 2026-10-18; the content-pipeline part is the leeway
  project's decision, a recommendation here).
- **Search before writing a system:** code.claude.com/docs/en/best-practices; duplicated
  code rose with AI assistants (GitClear's 2025 code-quality report).
- **A changed public API updates its README:** Google Engineering Practices, "What to look
  for in a code review" (documentation).
- **Language & style:** one job per file (Google's review guide; size predicts defects
  without a clean threshold, Yamashita et al., QRS 2016); no hidden global state (Hevery,
  "Singletons are Pathological Liars", Google Testing Blog, 2008); short doc comments
  (Google Python Style Guide, "Comments and Docstrings").
- **Duties: default silence, never repeat:** repeated alerts are ignored (Ancker et al.,
  BMC Medical Informatics and Decision Making 17:36, 2017); Anthropic's prompting guides for
  Sonnet 5.5 ("Steer initiative and scope") and Opus 5 ("Response length and verbosity").
- **A one-off decision writes its end condition:** agent memory fails when a temporary state
  overwrites a lasting one (Zhao et al., "LifeFuse-Mem", arxiv.org/abs/2609.12436).
- **MENTION ONCE items:** "Small CLs" (split by module); code.claude.com/docs/en/skills (a
  repeated procedure becomes a skill; the third time is the rule of three);
  code.claude.com/docs/en/costs (a saving needs a number). Decay findings: "Decay
  early-warning system" above.
- **Tone:** Anthropic, "Prompting Claude Opus 5"; the kit's
  `docs/research/communication-style.md`, findings 1 to 3, recommendations 1 and 16.
- **Task completion checklist:** the Scrum Guide's Definition of Done;
  code.claude.com/docs/en/best-practices ("Give Claude a way to verify its work").
