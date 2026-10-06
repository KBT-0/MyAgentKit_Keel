# Development Workflow

Goal: this project is written almost entirely by AI agents. Prevent spaghetti, keep the
code readable by a human, and stop the classic decay where agent productivity drops as the
codebase grows.

## How we work — roles

- **LEAD** — plans with {{OWNER_NAME}}. Reads `docs/PROJECT.md` (by section), `docs/PHASES.md`
  and `docs/ARCHITECTURE.md`.
  Produces the task brief (`docs/HANDOFF.md`). Decides model routing. Does not implement.
- **WORKER** — implements one task in one module. Bound by `AGENTS.md`, the gates, the tests.
- **REVIEWER** — `docs/REVIEW_GATE.md`. A fresh session, never the writer, preferably a
  different model.

{{OWNER_NAME}} alone decides: OPEN design items, taste and balance calls, scope, and whether
a risky change ships. Agents propose; {{OWNER_NAME}} decides.

**If the task brief does not state a role, you are the WORKER.**

## Task lifecycle (every task)

1. **Read:** `AGENTS.md` → `docs/PHASES.md` → `docs/STATE.md` → `docs/ARCHITECTURE.md` →
   the target folder's `AGENTS.md`. Do not explore beyond the files the task lists; context
   is a budget. `docs/PROJECT.md` is read by SECTION, only when the task needs one.
2. **Plan:** LIST the files you will touch. If that exceeds one module, STOP and propose
   splitting the task. Check the task against the current phase's out-of-scope list —
   needing something on it is a STOP, not a reason to widen the phase.
3. **Implement:** a small, focused change. No out-of-scope refactors.
4. **Test and gate:** write or update tests, then run `./scripts/check.sh` before finishing.
   The same script is wired into git as `.githooks/pre-commit`, so a failing gate aborts the
   commit for every tool — but running it yourself is still the rule. The hook is the
   backstop, not the plan, and agents never bypass it with `--no-verify`.
5. **Review, if risky:** {{RISKY_AREAS}} — and any change to a gate, CI config or check
   script — go through `docs/REVIEW_GATE.md` before commit, in a FRESH session. The author
   never approves their own patch. Any other change needs no review by default
   (`docs/REVIEW_GATE.md`, "What counts as a risky diff").
6. **Document:** if a public API changed, update that module's README in the same task.
7. **Update `docs/STATE.md`:** active work and what waits on {{OWNER_NAME}}, with a
   tool+model trace. Unwritten progress does not exist. A next task or a parked item goes to
   `docs/BACKLOG.md`, which is read when the next task is chosen, not every session.
8. **Summarize:** what, why, which files. If you hit an OPEN design item, flag it as a
   question rather than deciding it.

## Task ids

Finished work that nobody deleted is how `docs/STATE.md` rots: a project's state file held
lines like "Committed: K4" and "merged after three review rounds" long after the work was in
git, and a size limit could not tell those lines from live ones. A task id makes the
deletion checkable.

- A task id is a short token that starts with a letter and holds at least one digit:
  letters and digits, with at most one inner `-` (`K4`, `L1b`, `R12`, `K7-a`). A line in
  `docs/STATE.md` or `docs/BACKLOG.md` MAY name its task by id; none has to.
- The commit that finishes a task says so with a trailer, ONE per id, in the last paragraph
  of the message: `Done: K4`. The value is exactly one id: the hook rejects `Done: K4 K5`,
  `Done: K4, K5` and an empty `Done:`, and such a value already in the history closes
  nothing (`check.sh` prints a NOTE naming the commit). Git reads the key in any case, so
  `done: K4` closes K4 too. For work done on a branch, the integrating session's merge
  commit carries it.
- `.githooks/commit-msg` rejects that commit while the `docs/STATE.md` or `docs/BACKLOG.md`
  it records still names the id, and says which line; `./scripts/check.sh` fails `[state]`
  when either file names an id that any commit in the history closed. Whole word: closing
  `K3` says nothing about `K3b`.
- A closed id is never reused. A task needed again gets a new id.

## Task sizing

- Ideal: one module, one to five files, finishes in one session, describable in one sentence.
- "Write the billing system" is not a task. "Add the retry policy to the payment client,
  with tests" is.
- Big work is split into a task list first — planning is itself a task.

## Writing a gate

Gates get their own rules because they fail differently from ordinary code: when a gate
breaks, everything keeps looking green.

- **Prove it RED before you call it done.** Construct the failure condition, watch the gate
  reject it, then undo it. A gate observed only passing is an untested branch that runs on
  every commit.
- **Ship a negative test with it** — `./scripts/check.sh --self-test`. A manual proof rots
  the moment someone edits the script; the automated one does not.
- **A self-test case never changes a tracked file**, and writes nothing else into the
  working tree when it can avoid it: point the gate at a synthetic file outside the tree
  through an overridable path, or run against a disposable copy. Several sessions share one
  checkout, and a file injected into it is seen by their `git add -A`, their edits and their
  commits. `check.sh` holds a per-checkout lock for a whole run (the self-test included), so
  a second gate run waits instead of racing; tests that write scratch files still use a
  unique temporary directory, never a fixed name in the build or working directory.
- **Run a probe that edits an existing file in a disposable copy of the checkout**, never
  in the checkout. Restoring the file from EXIT/INT/TERM traps was not enough: until the
  restore, a concurrent `git add -A` staged the injection, and SIGKILL or a power loss,
  which run no trap, left it in the tree. The existing-file example in
  `scripts/boundary_selftests.sh` copies the tree (uncommitted edits included), runs the
  copy's gate, deletes the copy on exit and on INT/TERM, and ends the test on a signal; its
  traps live in a subshell so they do not replace the surrounding self-test's. The injected
  run gets a fresh copy of its own, so nothing the baseline run wrote exists in it; the cost
  is two copies of the tree instead of one. It supports a PLAIN repository only: a checkout
  whose `.git` is a file or a symlink (a linked worktree, a submodule, a separate git
  directory), a nested repository, or a symlink anywhere in a copy that leads out of it is
  refused by name and reported NOT RUN before the gate runs. Each copy must lie outside the
  checkout (it refuses a TMPDIR inside it); git and the gate run with only the environment
  variables the example names, the copy's own empty HOME and TMPDIR, no system or global git
  configuration, and an allowlist of the repository's own settings. Prove it by interrupting the injected test, SIGKILL included: the checkout's bytes
  and `git status` stay as they were.
- **Test both directions** where a gate can produce false positives. A gate that always
  fails is as useless as one that never does, and it gets deleted by the first person it
  blocks unfairly.
- **Fail on absent evidence.** No output file, an empty diff, a tool that did not run: all
  FAIL. An exit code is not evidence that work happened.
- **Parse tool output defensively.** Strip ANSI escapes before matching — CLIs colour their
  output and a coloured phrase silently stops matching. If an extracted field comes out
  empty, SAY it was not found; never write it out blank, because a blank field looks like a
  field.

## A red gate that passes on re-run

A FAIL that does not reproduce is not a PASS to forget. A timing-dependent test, a gate that
overlapped another gate or a self-test, or a real race all look the same afterwards: the next
run is green, and the failing test, its error line and the load it ran under are gone, so a
real race is never seen again until it bites in CI or production.

- **Record it before you commit on the green run**, in `docs/STATE.md` or the operation's
  own file (a branch session writes its worktree note instead) as a `[GOTCHA]` line: the
  failing test and its error line, the retry count, what else was running (another gate, a
  self-test, a review) and the suspected cause.
- **Re-run once** to learn whether it reproduces. A second red is a real failure. Never
  re-run until it turns green: a retry that is not recorded is a failure silently deleted.

## Spike protocol

Uncertain or risky topics are tried as throwaway code on a `spike/` branch first. Spike code
NEVER moves into the main code — the learning is rewritten cleanly. Record the outcome as a
five-to-ten line note in `docs/spikes/`.

## Decay early-warning system

Stop the task and report if you see any of:

- A SECOND system or class doing the same job — propose a merge.
- A forbidden dependency crossing a boundary.
- A README contradicting the actual public API (doc drift).
- A file ballooning past ~400 lines, or a class doing everything.
- Tests skipped, weakened or deleted.
- A gate that has been edited but not re-proven.

## Periodic architecture audit (critical ritual)

At a regular cadence — suggested every ~20 tasks or monthly — run an audit-only task in
which NO code is written:

- Boundary violation scan.
- Duplicate and dead code hunt.
- READMEs versus actual public APIs.
- Module size and complexity report.
- **Gate audit:** run `./scripts/check.sh --self-test`. Does every gate still go red, and
  does every check have a case? Then ask the question the self-test cannot: **does any gate
  guard a path that does not exist?** A scan over a missing directory finds nothing and
  looks exactly like a clean result, so such a gate reports PASS forever while protecting
  nothing — and its silence is identical before and after the module it guards arrives.
- **Tooling review:** "Has anything appeared in the agent-tooling ecosystem that would
  measurably help this workflow — and what would it cost in permanent context tokens?" The
  default answer is NO; a tool must earn its recurring cost. Record the answer either way,
  including "nothing this cycle", so the question gets asked on a schedule instead of
  whenever someone happens to think of it, and so a rejected tool is not re-evaluated from
  scratch every month.
- **Backflow question:** "Did we learn anything this cycle that belongs in the kit rather
  than only here?" If yes, change the kit FIRST, then sync. Record the answer, including
  "nothing".
  Then the second half, which is what keeps the kit alive rather than merely local:
  **offer to send it upstream.** `/myagentkit:kit-feedback` opens an issue or a pull request
  against the kit repository — it scrubs this project out, shows the exact body, and sends
  nothing without an explicit yes. A fix that stays local works, which is precisely why the
  upstream one then never happens and the next project inherits the original problem.

Output: a short `docs/audits/YYYY-MM.md` plus a list of cleanup tasks that enter the normal
loop. **The audit is itself a task; skip it and decay advances invisibly.**

## Multi-tool orchestration

- The canonical instruction file is `AGENTS.md` (root and per folder). Tool-specific files
  are pointers.
- `docs/STATE.md` is the single cross-tool memory. Every entry carries a tool+model trace.
- Cross-tool transfer uses `docs/HANDOFF.md` — the target has no chat memory.
- **Gates are tool-agnostic:** `scripts/check.sh` runs the same everywhere. Any tool's own
  hooks are early feedback, never the rule itself; `.githooks/pre-commit` is the gate that
  actually holds, for every tool.
- **Cross-tool review is preferred:** author and reviewer being different tools reduces
  correlated blind spots. Which tool takes which role is configuration, not doctrine — when
  the author's budget runs short, swap them rather than dropping the review.
- **A second agent's output is untrusted INPUT to a decision the calling agent owns**, never
  a verdict to relay verbatim. Verify each finding against the code: drop what is disproved,
  keep what is confirmed, and treat a confirmed critical finding as a stop signal.
- Agents do not spend another tool's budget on their own initiative. {{OWNER_NAME}} asks for
  it in the session, or it does not happen.

## Parallel work — worktree policy

Not every part of a repository tolerates a second working copy. Before starting parallel
work, check the path you are about to touch:

{{WORKTREE_POLICY}}

**Ceiling: 2 concurrent worktrees, 3 at the absolute most.** Published ceilings of four to
eight per developer assume review capacity is not the bottleneck. For a solo developer on a
limited token budget it is exactly the bottleneck: parallelism multiplies token burn
linearly while review capacity stays fixed, so a fourth branch does not produce a fourth
stream of merged work — it produces a queue.

## Parallel work — where a branch agent writes its notes

`docs/STATE.md` is a single hot file. If three branches append to it, every merge is a
conflict in the one file nobody may resolve carelessly.

- A session working on a branch or in a worktree **does not write `docs/STATE.md`** or
  `docs/BACKLOG.md`, which is just as shared.
- It writes `docs/worktree-notes/<branch>.md` — its own file, so it cannot conflict. Same
  content rules: full sentences, tool+model trace, an honest "not run". A follow-up task it
  found goes in the note too.
- `docs/STATE.md` and `docs/BACKLOG.md` are updated on the main branch at merge time by the
  integrating session, which folds the note in and deletes it.
- "If it is not in STATE.md it did not happen" still holds; it simply applies at merge. A
  branch note is a draft, not memory.

## Parallel work — contracts are frozen while it is in flight

The silent killer of parallel agents is not a textual merge conflict, it is a SEMANTIC one:
two branches each pass the gate in isolation and break the moment they meet, because one
changed a shared contract under the other.

- While parallel work is in flight, public interfaces are **FROZEN**.
- Contract changes are serialized: one task, alone, on the main branch; then the branches
  rebase onto it.
- A contract-first task therefore comes BEFORE any parallel fan-out. If the interfaces are
  not settled, do not fan out yet.
- Merge in dependency order, and run the gate after every merge before the next one. A gate
  run on the merged tree is the only thing that catches a semantic conflict.

## Parallel work — a second session may be live in the SAME tree

This happened and it cost budget: two sessions worked the same task list at the same time in
one working tree, with no branch and no note. Nothing was lost by luck rather than design.

Reading `docs/STATE.md` at session start is therefore not enough on its own — it is a
snapshot of a file another process may be editing right now.

- Before declaring a task item unapplied, run `git status` and look for modifications you
  did not make. Unexpected changes mean someone else is working here.
- If they are there, stop and ask rather than re-applying: a second application costs budget
  and can overwrite the first.

## Model routing — by scarcity, not by capability

{{MODEL_ROUTING}}

The principle behind whatever the table says: **spend the scarce budget on judgement and the
generous one on volume.** Cross-model review stays mandatory for risky diffs — the value of
a second model is decorrelated judgement, which two agents of the same model cannot give you
no matter how many you run.

The table decides the AUTHOR and REVIEWER roles, and it is allowed to change its mind. If
the generous budget is the stronger model this month, it authors and the scarcer one
reviews; if that reverses, so do the roles. Record the swap in `scripts/review.sh` and in
`docs/STATE.md` — the review records themselves stay comparable across the change because
both directions publish one format.

Caveat worth stating once: a more autonomous model fills ambiguity by itself instead of
asking. The mitigations are sharper briefs (`docs/HANDOFF.md`) and the gates, not trust.

**Reasoning effort is the second dial.** Mechanical, well-specified work goes at low effort
or to the cheaper model; architecture, contract design and risky-diff review go at high
effort. Effort is chosen per task, not per session — running everything high spends the
scarce budget on work that did not need it.

## Worker cost — waits and long lives are what you pay for

Measured in the kit's founding project (one lead session with background workers: 336 USD in
eleven hours, 87 percent of it the workers; the transcripts were then counted request by
request, and a controlled experiment ran the same task in six setups). What the numbers say:

- **A sub-agent's prompt cache lives five minutes; a main conversation's lives an hour.** A
  worker that waits longer than its cache re-writes its whole context on the next request, at
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
   runs jobs longer than a few minutes runs with a one-hour cache (a separate session, or a
   sub-agent whose definition sets `experimental.cacheTtl: 1h` — the Claude Code overlay
   ships one as `.claude/agents/worker.md`), starts long jobs in the background and is
   re-invoked when they exit, and never runs `sleep`, `until`, `pgrep` or tail-the-log
   loops. Where a one-hour cache is unavailable (it is ignored on usage credits; another host
   may have no such setting), choose the fallback from the measured table in the kit's
   `docs/worker-cost-setups.md`: usually waits split into pieces under five minutes, at the
   price of a context read per piece.
2. **A review-fix round goes back to the worker that wrote the change** (a resumed
   sub-agent, or the same separate session) while it is available and its context is not
   spent: a fresh worker re-reads the whole context to change a few lines. A fresh worker,
   briefed with the findings, the branch and the files to read, takes the round when the
   context is spent (near rule 3's limit) or the fix is a redesign. The reviewer is fresh in
   every round; the worker never reviews its own change.
3. **One small task per worker**, sized to end under roughly 150 requests (`maxTurns` in the
   worker definition enforces it). Split before starting: a mechanism first, then its uses.
4. **The lead does not poll either.** It waits for task notifications or an idle notice from
   a separate session; it does not check on workers or CI in a loop.
5. **Mechanical work goes to the cheaper model at a lower effort**: doc fixes, running a
   documented proof, folding notes. Design-bearing code and reviews get the strongest model
   at high effort. Effort is never left to inheritance: a sub-agent runs at its lead
   session's effort unless its definition sets `effort:` (the Claude Code overlay's
   `worker.md` and `diff-reviewer.md` do), and nothing in its output shows which one it got.
   A separate session takes `scripts/spawn_worker.sh --effort`. The brief states model and
   effort, and the lead verifies both in the transcript after the run, not in the report.
6. **Parallel workers only for independent modules**; each one multiplies the bill. Workers
   whose last step waits on one exclusive resource (a heavy lock, a device, a licence) run
   one after another, or run only their independent parts in parallel: in one project,
   "parallel" workers queued at one machine-wide lock.
7. **Worker reports are short** (about 400 words), and long output goes to a file with a
   summary line: the lead pays for a report again on every later turn. A separate spawned
   session writes its report to the result FILE its brief names. A sub-agent cannot: Claude
   Code refuses its write of a report file ("Subagents should return findings as text, not
   write report files"), and a worker briefed for a `REPORT.md` spends turns working around
   the refusal. A sub-agent keeps its short report in its final message and writes only
   logs, tables and captures to files.
8. **The lead session is handed over before it grows**, and at the end of a working day it
   reads the tool's cost screen and runs `scripts/agent_cost.py --latest` and writes both
   into the handoff, so the next routing decision is made from a number.
9. **A worker runs the cheapest check that proves its change; the expensive step runs
   once.** The brief names that check (`docs/HANDOFF.md`, "Proof"); with none named, the
   worker runs `./scripts/check.sh`. The expensive build or package step runs once, in the
   integrating session, after the merge: in one project every worker built the whole
   package in its worktree (7 to 40 minutes each), and the lead built it again. A defect only
   the full build shows is then found at integration. So the integrating session builds after
   each merge when the build is cheap, and names the merge that broke it when it is not.

**The shape follows a threshold, so the lead does not decide it each time.** Work expected
to take more than about an hour, or more than one review round, runs in its own separate
session that {{OWNER_NAME}} can talk to directly (`scripts/spawn_worker.sh`): under a lead it
would wake the whole lead context at every hand-back and stay hidden from {{OWNER_NAME}}. A
short read-only diagnosis or review runs as a sub-agent under the lead: its own session
would pay a session start for nothing. The lead merges and, as the integrating session, runs
the integration build.

The threshold is {{OWNER_NAME}}'s decision from use. The only cost comparison of the two
shapes is one task on 2026-10-03 (`docs/worker-cost-setups.md`): about 107 against 110
requests, a cost equivalent of about 2.44M against 2.40M tokens. It measured the cost per
worker on one task with one long wait, not wall-clock time, the throughput of several tasks,
or the lead's own cost. Measure in passing: wall-clock from brief to merge, total tokens
including the lead's, review rounds, and waits on an exclusive resource. The sample will be
thin.

`scripts/spawn_worker.sh` (Claude Code overlay) opens the session in tmux with a brief file.
The lead subscribes once for its idle notice and does not message it: every message to an
idle session is a full-context turn. The idle notice also fires on every park on a
background job, and the session does not end with its task. The result file is therefore
the end signal, and the lead closes the session after reading it (`tmux kill-session -t
NAME`).

Closing the session leaves the worktree. **Once a worktree's branch is merged, the worktree
is FINISHED**: a further round on that task starts a NEW worktree, never the old one. With the
Claude Code overlay, `.githooks/post-merge` removes a finished worktree after the next merge
git completes itself in the main worktree (not a conflicted merge finished with `git commit`,
nor `pull --rebase` or `cherry-pick`), but only when `scripts/clean_worktrees.sh` finds
nothing in it that would be lost: a commit was made in that worktree (its own HEAD reflog) and
its HEAD is in the main branch; every commit a file of its git directory names is held by a
ref or its branch's reflog, or saved first under `refs/kit/saved/`; every tracked file is byte
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

A worker whose worktree directory is missing STOPS and reports. It never recreates the
directory and never runs a git command from where it used to be: that folder lies inside the
main checkout, so git there acts on the owner's main worktree.

## Token economics — the always-loaded prefix is money

Cached input tokens are discounted heavily, so a STABLE prompt prefix — the documents loaded
at the start of every session — is the largest single cost lever available. Every edit to
one of those files invalidates the cache for every session after it.

- Do NOT edit `AGENTS.md`, `docs/ARCHITECTURE.md` or any other always-loaded doc in the
  middle of a session unless the task IS that document.
- Batch documentation edits into their own task and their own session.
- Keep always-loaded docs SMALL and STABLE. Size here is not a readability preference; it is
  a recurring bill.
- Volatile state belongs in `docs/STATE.md`, which is read on demand. Reference docs like
  `docs/GOTCHAS.md` stay off the session-start list entirely.

## Web requests carry no personal data

Some APIs ask clients to put contact details in the `User-Agent`, and an agent that has
{{OWNER_NAME}}'s e-mail address in its session context uses it: in one project five
research agents did, in up to thirteen requests each. A request reaches a third party and
its logs, and cannot be recalled.

- **Never put a person's name, e-mail address or other personal data into a web request**
  (headers, query strings, bodies, scripts an agent writes to fetch pages). When an API asks
  for contact details, send a generic project User-Agent without personal data, or stop and
  ask {{OWNER_NAME}}.
- **A brief for a task with web access repeats the rule** and names that generic
  User-Agent (`docs/HANDOFF.md`): a sub-agent does not read this file unless told to.

## MCP hygiene

Every enabled MCP server injects its tool catalogue and schemas into every request, whether
or not a single tool is called. Verbose catalogues are a real recurring cost, and most
custom servers duplicate what a plain CLI already does more reliably.

- Enable a server only for the work that needs it. Otherwise keep it off.
- Prefer plain CLI tools over adding a server.
- **A new MCP server needs {{OWNER_NAME}}'s approval, exactly like a new dependency.** It is
  a permanent context cost, so it must earn its place.

## Evaluated and rejected — do not re-litigate

Decisions turned down, written here so no session spends budget deciding them again. Each
one names what would have to change before it is worth reopening.

{{REJECTED_DECISIONS}}

## Documentation maintenance contract

- `docs/PROJECT.md` changes only with {{OWNER_NAME}}'s approval for anything DECIDED; an
  agent may add OPEN items freely (`AGENTS.md`, design authority).
- `docs/ARCHITECTURE.md` is updated in the SAME task that adds a module or moves a boundary.
- These files are worth more than the code: code can be regenerated, context cannot.
