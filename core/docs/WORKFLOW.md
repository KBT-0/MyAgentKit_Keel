# Development Workflow

Goal: this project is written almost entirely by AI agents. Prevent spaghetti, keep the
code readable by a human, and stop the classic decay where agent productivity drops as the
codebase grows.

## How we work — roles

- **LEAD** — plans with {{OWNER_NAME}}. Reads `docs/PROJECT.md` (by section), `docs/PHASES.md`
  and `docs/ARCHITECTURE.md`.
  Produces the task brief (`docs/HANDOFF.md`). Decides model routing. Does not implement.
- **WORKER** — implements one task in one module. Bound by `AGENTS.md`, the gates, the tests.
- **REVIEWER** — `docs/REVIEW_GATE.md`. A fresh session of the other model (in claude-only,
  of another Claude tier); its verdict counts only for parts it did not write. It fixes its
  own findings afterwards, unless the working mode in force ("Working modes, by name" under
  "Model routing": codex-first and the saver modes) names another fix author.

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
   Publish session edits through the compare-and-swap protocol below, never by overwriting STATE.md directly.
8. **Summarize:** what, why, which files. If you hit an OPEN design item, flag it as a
   question rather than deciding it.

## Task ids

Finished work that nobody deleted is how `docs/STATE.md` rots: a project's state file held
lines like "Committed: K4" and "merged after three review rounds" long after the work was in
git, and a size limit could not tell those lines from live ones. A task id makes the
deletion checkable.

- A task id is a short token that starts with a letter and holds at least one digit:
  letters and digits, with at most one inner `-` (`K4`, `L1b`, `R12`, `K7-a`). A line in
  `docs/STATE.md` or `docs/BACKLOG.md` MAY name its task by id; none has to. Ids are
  case-insensitive: `k4` and `K4` are the same task.
- The commit that finishes a task says so with a trailer, ONE per id, in the last paragraph
  of the message: `Done: K4`. The value is exactly one id: the hook rejects `Done: K4 K5`,
  `Done: K4, K5` and an empty `Done:`, and such a value already in the history closes
  nothing (`check.sh` prints a NOTE naming the commit). Git reads the key in any case, so
  `done: K4` closes K4 too. For work done on a branch, the integrating session's merge
  commit carries it.
- `.githooks/commit-msg` rejects that commit while the `docs/STATE.md` or `docs/BACKLOG.md`
  it records still names the id, and says which line; `./scripts/check.sh` fails `[state]`
  when either file names an id that any commit in the history closed. The strong review
  cycle's `docs/STRONG_REVIEW.md` and `docs/reviews/strong-*.md` are checked the same way.
  Whole word: closing `K3` says nothing about `K3b`.
- A closed id is never reused. A task needed again gets a new id.

## Task sizing

- Ideal: one module, one to five files, finishes in one session, describable in one sentence.
- "Write the billing system" is not a task. "Add the retry policy to the payment client,
  with tests" is.
- Big work is split into a task list first — planning is itself a task.

## The state, backlog and phase files

The rules for `docs/STATE.md` are in `AGENTS.md`, "STATE.md discipline". This section keeps
their reasons, so that the always-loaded files carry only the rules.

For every authorized session edit, run `python scripts/working_mode.py --read-state
.myagentkit/STATE.edit.md` first: it creates a fresh, exclusively owned per-edit snapshot with
that prefix and prints `SHA256 PATH`, from one read. Each caller gets its own path; an existing
file is never reused, including a hard link. Edit the returned PATH, never a copy of STATE.md
read earlier, then run `python scripts/working_mode.py --replace-state "PATH" --expect SHA256`
with that sha. On refusal, run `--read-state` again, redo the edit there, and retry. Do not retry
stale contents. A hash read apart from the bytes it names let a copy read at the session's start
pass over an edit published in between. The helper compares the bytes under the same lock as a
mode switch, then replaces the file atomically. It preserves the file mode, runs no arbitrary
command, consumes the snapshot into a caller-private name, and deletes only the object verified
by the read descriptor after publication; a successor at the supplied path stays. Both publication
and rollback can otherwise erase another writer's work. The STATE operations run from the project root without another
`--project`, and read or write a snapshot only in `.myagentkit/` (ignored by Git) or the
temporary folder: `/myagentkit:mode` runs the helper unprompted, so it copies no other file,
and a snapshot never lands where `git add -A` commits it. OUT is a name prefix and FILE a regular
file, never a folder: OUT naming `.myagentkit` put the snapshot in the project root, and FILE
naming a folder moved it whole. An unpublished draft that cannot go back to FILE stays in a
private folder beside it, whose path the helper prints. An edit that changes or removes the
"Working mode:" line is refused: the mode switch writes that line together with `.claude/mode`.
The branch and worktree policy below still decides which session may edit STATE.md.

- `docs/STATE.md` is read at the start of every session, in every tool, so its length is a
  bill paid every session. What is planned next, and what was parked on purpose, is a
  backlog, and it lives in `docs/BACKLOG.md`, which is read only when the next task is chosen.
  A backlog only grows, and in STATE.md it is read every session for nothing.
- A `[LESSON]` or `[GOTCHA]` tag makes harvesting a grep, not a re-read.
- Pruning without harvesting buries the lesson in the git history, and nobody looks there —
  git is an audit trail, not a knowledge base.
- Completed work is deleted, not marked DONE: the dates live in git
  (`git log -p -- docs/STATE.md`). The state templates name no example task id, because
  those files are the ones checked ("Task ids").
- An operation's detail lives in its own file, `docs/<OPERATION>.md`, never in STATE.md. The
  operation file tracks progress with checkboxes; its last acceptance item is "STATE.md
  harvested and pruned", and the file is deleted when the operation closes (the history is
  in git). Without this rule every integration folds more into STATE.md, and it only grows:
  one project's state file reached 38 KB.
- No size limit applies to STATE.md. A limit cannot tell a live line from a finished one,
  and a project that added one hit it again and again while half the file was backlog and
  much of the rest narrated work already in git.
- Compressed chat styles do not apply to STATE.md: the next tool reading it knows nothing
  about your plugins.

`docs/PHASES.md` is read every session. It is short on purpose: the CURRENT phase in full,
everything after it in one line each. Detail arrives when a phase becomes current, not before — a plan written
for a phase three steps away is mostly aspiration, and aspiration in an always-loaded file
is a bill with nothing behind it.

**The non-goals are the useful half.** "Build the inventory system" gives an agent no edge
to stop at, so it invents scope: it adds persistence, a UI, an event system, and returns one
monolithic file touching five modules. "Build the grid placement rules; do NOT add
persistence, do NOT write UI" is the same task with a fence around it. Scope invention is
the most expensive habit an agent has, and `docs/PHASES.md` is the cheapest cure.

The reasoning behind phase-shaped work — ordering by risk rather than by dependency, why
each phase should be independently useful — is in `patterns/staged-prototype.md` if the
project took it. `docs/PHASES.md` is the working document, not the argument for it.

**Phase lifecycle.** A phase is **episodic**: true for as long as it runs, then gone. When it
closes, its detail is DELETED from `docs/PHASES.md` — history lives in git — after anything
permanent has been moved to its real home:

- A decision the phase produced → `docs/PROJECT.md`, as a numbered item
- A module, boundary or contract → `docs/ARCHITECTURE.md`
- A process or gate lesson → `docs/WORKFLOW.md`
- An environment trap → `docs/GOTCHAS.md`

That is the same harvest-then-prune rule `docs/STATE.md` follows, one scale up. The three
files differ only in how long their contents stay true:

| File | Horizon | On completion |
|---|---|---|
| `docs/PROJECT.md` | Permanent | Superseded, never deleted |
| `docs/PHASES.md` | This phase | Deleted after harvest |
| `docs/STATE.md` | Right now | Deleted when the task is done |

A multi-item operation with checkboxes is NOT a phase. It gets a throwaway file of its own —
`docs/CHANGE_ORDER.md`, or whatever the operation is called — which is deleted when the
operation closes; the rule is in `AGENTS.md`, "STATE.md discipline". Phases are standing; operations are
disposable, and neither one is ever tracked inside the other.

## Writing a gate

Gates get their own rules because they fail differently from ordinary code: when a gate
breaks, everything keeps looking green.

- **Prove it RED before you call it done.** Construct the failure condition, watch the gate
  reject it, then undo it. A gate observed only passing is an untested branch that runs on
  every commit.
- **Ship a negative test with it** — `./scripts/check.sh --self-test`. A new gate adds its
  case there in the same task. A manual proof rots the moment someone edits the script; the
  automated one does not.
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
- **A test or an experiment never executes a file whose name ends in `.exe`.** Under WSL
  such a file runs on Windows, which may show {{OWNER_NAME}} a GUI error dialog. Name a stub
  for a Windows launcher without `.exe`, and reach it through an overridable variable
  (`docs/GOTCHAS.md`).
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

## The strong review cycle — at least every ten days

The audit above looks for decay; this cycle asks the strongest models what everyone working
day to day has stopped seeing. It runs at least every ten days, and `./scripts/check.sh`
prints a NOTE when no strong review report was added in that time, so it does not depend on
anyone remembering it.

- **The list:** `docs/STRONG_REVIEW.md` holds the questions for the next cycle and the open
  findings of earlier ones. Each strong model writes its own report,
  `docs/reviews/strong-<YYYY-MM-DD>-<model>.md`, and never edits another model's report.
- **Scope:** everything that reached the main branch since the previous cycle's report, and
  the open questions in the list.
- **First reviewer:** the strongest model available, read-only, in a fresh session
  ("Model routing"). Its report has four headings: consistency with the design
  document's decisions; the look, where the project has one; performance and cost at full
  scale; code health (duplicate systems, test gaps). Each finding carries a task id
  ("Task ids"), a severity and its evidence.
- **Triage:** the lead and the owner mark each finding in the list as accepted, parked or
  rejected. An accepted finding becomes a task under its id.
- **Second reviewer**, a strong model of the other family when one is available: reviews the
  first report, the triage and what was built, and adds findings of its own.
- **One exchange:** where the second reviewer disagrees, those points go back to the first
  reviewer in its own session for one answer; then the owner decides. One round only, which
  keeps the cost bounded.
- **Closing deletes.** A finding is closed when both strong models have reviewed it and the
  change it called for has landed, or when the owner rejected it. The closing commit deletes
  its lines from the list and from every report and carries `Done: <id>`;
  `.githooks/commit-msg` and `./scripts/check.sh` refuse a closed id that any of them still
  names. A report left with no finding is deleted; the history is in git, and the reminder
  dates the cycle by the commit that added its report, not by the file.

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
- **A worker's "not done" or "noticed, not fixed" line about something the brief asked for
  is a finding.** The lead has it fixed before the merge. A worker's list of new ideas is a
  question for {{OWNER_NAME}}, never an automatic next round.
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

The tiers below sort the work; the working mode in force ("Working modes, by name") says
which side takes each tier. The model names are this kit's as of 2026-10-08: replace them
with what the owner's subscriptions offer today (rule 5).

| Tier | Work | Codex | Claude |
|---|---|---|---|
| 1 | Mechanical: renames, figure fixes, data fetches, proof runs, summaries | `gpt-6-luna`, medium effort | Haiku 5.5 or Sonnet 5.5, medium effort |
| 2 | Detail-bearing errands, ordinary reviews | `gpt-6.1-sol`, high effort | Opus 5.5, high effort, only for design-bearing work |
| 3 | Risky and gate reviews, design consultations | `gpt-6.1-sol`, xhigh effort; `gpt-6-astra` when the lead picks it | Opus 5.5, high effort; Fable 5.1 when the lead picks it |

The prices behind the table come from third-party summaries of OpenAI's launch figures:
Luna costs about a twentieth of Sol's token price, and Sol 6.1 about a fifth of Astra's.
Neither the per-model Codex allowance nor the quality claims were verified. **The table is
provisional**: API token prices say nothing about how much each model draws from a
subscription's five-hour and weekly allowance. Measure that draw (`/status` before and after
a few errands per model) and move the tiers by it (rule 6).

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

**Reasoning effort is the second dial.** Choose effort from this table for implementation
and review. Running everything high spends the scarce budget on work that did not need it.

| Work | Effort |
|---|---|
| Mechanical work and re-review of a small fix round | medium |
| A new mechanism's first round, a gate/hook/review-tooling change, or a risky diff | high |
| Work requiring xhigh/max | Only by the lead's decision, with the reason in the brief |

Every brief carries `Route: quick|build|deep · Risk: low|medium|high · Checks: ...`, plus
the chosen model and effort. Route describes the task; risk determines the check list:
low means tests for touched files; medium means focused suites plus the package check;
high means the full gate plus a careful diff read. Review effort follows the work table
above: a small fix re-review uses medium; a risky diff or mechanism change uses high.
The lead session changes its model or effort only at a task boundary, never mid-task,
because a switch rebuilds the prompt cache at full price.

Rules for whoever routes work, binding with any table:

1. **Model and effort are chosen with equal care.** The table sorts work into tiers:
   mechanical work (renames, figure fixes, data fetches, proof runs, summaries);
   detail-bearing errands and ordinary reviews; risky and gate reviews and design
   consultations. The lead picks the model from its tier and effort from the work table above.
   It writes both into the brief. Neither is left to a default or to inheritance.
2. **The top models are the lead's pick, and only where the subscription has them.** A model
   above the strongest routine one (for example Codex Astra or Claude Fable) is never a
   default. The lead picks it for one errand when the errand needs it, without asking the
   owner. The lead first checks that the current subscription includes that model; a basic
   plan does not, and then the strongest routine model takes the errand. While that side's
   allowance is low (a saver mode, below), the top model and the highest effort need the
   owner's yes.
3. **A failed mechanical errand is rerun one tier up**, never retried at the same tier.
4. **A review loop is broken by escalation after the second dirty round.** When round 2
   still returns a High or Medium finding, round 3 runs one step up. If the fixer skipped
   a file or did not run the tests, raise its effort. If it had the full context and was
   still wrong, raise its model tier. The lead writes the choice and reason into the next
   brief. One stronger round costs less than several more rounds at the same level.
5. **Model versions are kept current.** A lead that learns of a newer Codex or Claude model
   switches to it: the reviewer pins in `scripts/review.sh` and the machine's Codex
   configuration (`~/.codex/config.toml`). The lead then reports the switch to the kit, so
   that the kit and every project built from it follow.
6. **The tier boundaries are measured, not guessed.** After about ten errands in a tier, the
   lead counts review rejects and rework per tier and moves the boundaries where they show.
   `python3 scripts/usage_summary.py` gives the review side: rounds, verdicts and rejects per
   task and per model and effort. Worker errands write no record; the lead counts their rework.
7. **A low allowance shrinks what that side does, never the review.** When the owner says
   one side's allowance is low, the saver mode for that side is in force (below).
   The low allowance lasts until that side's allowance resets, or until the owner says
   otherwise; then the main rule is back at once, unasked: the reviewing model fixes its own
   findings again. A decision made for a moment never outlives its reason.

### Working modes, by name

The owner switches the working mode by its name, in English or Turkish. The "Working mode:"
line of `docs/STATE.md` and the small `.claude/mode` file name the mode in force.
`/myagentkit:mode` uses `scripts/working_mode.py` to show or set both records, preserving
the rest of STATE.md. Reads refuse disagreeing records; an explicit owner choice repairs
them. A project without either record works in **cross-performance**, the main mode.

Without names, the owner explained the same situation in a long prompt at the start of every
session ("Claude is low today, let Codex write and fix"), and a lead that was not told routed
by habit: one Opus lead routed no implementation to Codex and spent five Opus sessions on
review rounds. A name is one word, and a lesson one project learns improves the mode for
every project through the kit.

A mode decides who writes, who reviews, who fixes the review findings, how many workers run
and at which effort. It never removes a review. Codex-first and saver modes change the fix author as
explicitly defined below; they keep the independent stopping rule and fresh NEW-label final
review. In every mode the review loop of
`docs/REVIEW_GATE.md` ("What counts as a risky diff") and `docs/REVIEW_RUNNING.md` ("Rounds,
labels and designs") holds as written there, and rules 1 to 6 above hold too. The worker
caps below never exceed the worktree ceiling ("Parallel work — worktree policy"). Every
Claude worker spends the same Claude allowance: a sub-agent, a spawned session and a tab
alike. The lead is the session that plans with the owner, whichever side it runs on.

| Mode | Turkish name | Writes | Reviews | Fixes the findings |
|---|---|---|---|---|
| `claude-first` | Claude Öncelikli Mod | Claude workers | Codex | the reviewing model |
| `cross-performance` | Çapraz Performans Modu (main mode) | both sides, by tier | the other side of the author | the reviewing model |
| `cross-saving` | Çapraz Tasarruf Modu | both sides, at most one Opus worker at a time | the other side of the author | the reviewing model |
| `codex-first` | Codex Öncelikli Mod | Codex; Opus only for lead-selected heavy or important work | Claude; Codex for Opus work | Codex; the Opus worker for Codex's findings on its own work |
| `claude-saver` | Claude Tasarruf Modu | Codex workers | Claude, on a small budget | Codex |
| `codex-saver` | Codex Tasarruf Modu | Claude workers | Codex, on a small budget | Claude |
| `claude-only` | Sadece Claude Modu | Claude workers | another Claude tier, in a fresh session | the reviewing tier |

#### claude-first (Claude Öncelikli Mod)

- **Writes:** Claude workers do all the implementation, at the tier table's Claude column.
- **Reviews and fixes:** Codex reviews every risky diff and fixes its own findings; a Claude
  round reviews that fix.
- **Workers:** Claude workers up to the worktree ceiling; Codex runs reviews and its fix
  rounds only.
- **Effort:** Claude workers at high for design-bearing work and at medium for mechanical
  work; Codex reviews at high, and at xhigh for a gate or a risky area.
- **Ends:** when the owner names another mode.
- **Lessons:** none yet.

#### cross-performance (Çapraz Performans Modu), the main mode

- **Writes:** both sides share the work. The lead plans, briefs and verifies. Design-bearing
  and critical parts go to Opus workers; exact, bounded, mechanical errands go to Codex
  workers (`scripts/spawn_codex.sh` in the Claude Code overlay).
- **Reviews and fixes:** a review always crosses to the other side of the author, and the
  reviewing model fixes its own findings.
- **Workers:** up to the worktree ceiling, both sides together.
- **Effort:** the tier table as written.
- **Ends:** this is the mode every other one returns to.
- **Lessons:** a lead that sends every errand to its own side spends its allowance on
  volume: one Opus lead routed no implementation to Codex and spent five Opus sessions on
  review rounds.

#### cross-saving (Çapraz Tasarruf Modu)

- **Writes:** as cross-performance, with at most ONE Opus worker running at a time. Every
  other errand that can be stated exactly goes to Codex.
- **Reviews and fixes:** as cross-performance.
- **Workers:** one Opus worker; Codex workers fill the rest of the worktree ceiling.
- **Effort:** the tier table; Opus only at tier 2 and 3, never for tier-1 work.
- **Ends:** when the owner names another mode.
- **Lessons:** every Claude worker counts against the one: a sub-agent spends the same
  allowance as a spawned session.

#### codex-first (Codex Öncelikli Mod)

This mode chooses routing for quality and cost. Codex-saver is a separate mode for when
Codex's allowance is low; it sends implementation and fixes to Claude.

- **Lead:** the Claude Opus lead plans, briefs, routes and reviews. It writes no implementation
  or fixes, including fixes of its own review findings. Model management aims for the
  healthiest work at the lowest cost.
- **Writes and fixes:** Codex workers write all implementation and all fixes on it,
  including fixes of Claude's review findings. Only work the lead judges
  too heavy or too important for Codex goes to a Claude Opus worker; Codex reviews that work,
  and that Opus worker fixes Codex's findings on it, so no model reviews its own fix.
- **Reviews:** Claude reviews Codex work and Codex's fixes; Codex reviews Opus worker work and
  the Opus worker's fixes. Independent acceptance and the fresh NEW-label final review still apply.
- **Workers:** Codex workers up to the worktree ceiling; Claude Opus workers only for the
  lead's heavy or important exceptions. The lead itself only leads and reviews.
- **Effort:** Codex workers at high for design-bearing work and at medium for mechanical
  work; Claude reviews at high.
- **Ends:** when the owner names another mode.
- **Lessons:** none yet.

#### The two saver modes

A saver mode is for a side whose allowance is low. That side reviews within a small budget,
and the other side implements AND fixes the findings, the low side's findings included.
Claude leads in both saver modes: in claude-saver it plans, briefs, verifies and reviews;
in codex-saver it also does the work, and Codex only reviews. Every fix goes back to a review
by the low side, so the loop keeps both models. These rules bind both saver modes:

- The low side's reviews run at the lowest effort that fits: a re-review of a small fix
  round at medium; high for a gate, hook or review-tooling change, a risky diff and a new
  mechanism's first round. The top model or the highest effort needs the owner's yes.
- A running review is not cancelled to lower its effort, since what it spent is gone.
- Independent reviews run at the same time, with each other and with the self-test.
- A review that fails on quota leaves its rerun command in the task's issue or STATE line
  and waits. It goes to the other side only with the owner's yes, because a second model's
  judgement is the point of it.
- **Ends:** the low side's allowance resets, or the owner says otherwise. Then
  cross-performance is back at once, unasked: the lead runs `scripts/working_mode.py
  cross-performance` to update both records, and the
  reviewing model fixes its own findings again. A decision made for a moment never outlives
  its reason.

#### claude-saver (Claude Tasarruf Modu): Claude's allowance is low

- **Writes:** Codex workers implement every errand and fix every finding.
- **Reviews:** Claude reviews within a small budget, by the saver rules above.
- **Workers:** no Claude worker and no implementing sub-agent; the Claude lead itself, and
  Claude reviews. Codex workers up to the worktree ceiling.
- **Effort:** Codex workers by the tier table's Codex column; Claude reviews by the saver
  rules above.
- **Ends:** on Claude's allowance reset or the owner's direction; cross-performance returns.
- **Lessons:** none yet.

#### codex-saver (Codex Tasarruf Modu): Codex's allowance is low

- **Writes:** Claude workers implement every errand and fix every finding.
- **Reviews:** Codex reviews within a small budget, by the saver rules above.
- **Workers:** no Codex worker; Codex reviews only. Claude leads and does the work,
  with Claude workers up to the worktree ceiling.
- **Effort:** Claude workers by the tier table's Claude column; Codex reviews by the saver
  rules above.
- **Ends:** on Codex's allowance reset or the owner's direction; cross-performance returns.
- **Lessons:** none yet.

#### claude-only (Sadece Claude Modu)

For a subscription with only Claude. Unlike codex-saver, where Codex still reviews on a small
budget, no Codex runs here at all.

- **Writes:** Claude workers do all the implementation, at the tier table's Claude column.
- **Reviews and fixes:** the author and the reviewer are different Claude tiers, each in a
  fresh bridged session with no shared context: Opus authors and Fable or Sonnet reviews, or
  the reverse; the lead picks both by the tier table. A second session of the author's own
  tier is never the review. The reviewing tier fixes its own findings, and the other tier
  reviews that fix. Cross review stays mandatory, and rule 4's escalation and the review
  loop's closure rules hold as in every mode. Two Claude tiers decorrelate less than two
  vendors; fresh sessions with no shared context are what keeps the review independent.
- **The second reviewer:** `scripts/review.sh --reviewer claude` (or `DEFAULT_REVIEWER="claude"`)
  with `REVIEW_CLAUDE_MODEL` set for that run to the tier that did not write the change. It is
  the existing per-reviewer Claude pin, so the review records stay in one format. `CODEX_MODEL`
  stays empty: `--fallback` then has no other reviewer to hand the review to.
- **Workers:** Claude workers up to the worktree ceiling; no Codex worker and no Codex review.
- **Effort:** Claude workers at high for design-bearing work and at medium for mechanical
  work; reviews at high, with the top tier (rule 2) for a gate or a risky area.
- **Ends:** when the owner names another mode, for example once a Codex subscription is added.
- **Lessons:** none yet.

#### How a mode improves

Each mode's **Lessons** list is how a mode gets cheaper with use. When a mode cost more
than it should have (a wasted round, a worker on the wrong side, an allowance that ran out
early), the lead adds one line to that mode's list: the failure, with a number when there is
one, and the rule that prevents it. The lead then offers it to the kit with
`/myagentkit:kit-feedback`, so every project's copy of the mode learns it. A lesson that the
mode's own rules come to state leaves the list, and a lesson a later one supersedes is
deleted: the list holds only what is not yet a rule.

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
2. **Cross-model gate findings go to a fresh worker of the reviewing model**, briefed with
   the findings, the branch and the files to read. The gate's reviewer is a headless process
   in a throwaway copy, so it cannot be resumed. Only inner same-model rounds ("Review inside
   the worker") go back to the worker that wrote the change (a resumed sub-agent, or the same
   separate session) while its context is not spent: a fresh worker re-reads the whole
   context to change a few lines. A fresh worker of that model takes such a round when the
   context is spent (near rule 3's limit) or the fix is a redesign. The gate's reviewer is
   fresh in every round and runs the other model; no model reviews its own change.
   The codex-first and saver-mode fix-author exceptions above take precedence over this route.
3. **One small task per worker**, sized to end under roughly 150 requests (`maxTurns` in the
   worker definition enforces it). Split before starting: a mechanism first, then its uses.
4. **The lead does not poll either.** It waits for task notifications or an idle notice from
   a separate session; it does not check on workers or CI in a loop.
5. **Mechanical work goes to the cheaper model at medium effort**: doc fixes, running a
   documented proof, folding notes. Design-bearing code gets the strongest model at high
   effort; reviews follow the "Model routing" effort table. Model and effort are never left
   to inheritance: a sub-agent runs at its
   lead session's effort unless its definition sets `effort:` (the Claude Code overlay's
   `worker.md` and `diff-reviewer.md` do, as a fallback), and nothing in its output shows
   which one it got. The lead passes `model` and `effort` on every Agent call. A separate
   session takes `scripts/spawn_worker.sh --model --effort`, which refuses a spawn without
   them; a Codex errand takes the model and `-c model_reasoning_effort`, and
   `scripts/spawn_codex.sh --model --effort` refuses a Codex worker without them. The brief states model and
   effort, and the lead verifies both in the transcript after the run, not in the report.
6. **Parallel workers only for independent modules**; each one multiplies the bill. Workers
   whose last step waits on one exclusive resource (a heavy lock, a device, a licence) run
   one after another, or run only their independent parts in parallel: in one project,
   "parallel" workers queued at one machine-wide lock.
7. **Worker reports are short** (about 350 words), and long output goes to a file with a
   summary line: the lead pays for a report again on every later turn. A separate spawned
   session writes its report to the result FILE its brief names. A sub-agent cannot: Claude
   Code refuses its write of a report file ("Subagents should return findings as text, not
   write report files"), and a worker briefed for a `REPORT.md` spends turns working around
   the refusal. A sub-agent keeps its short report in its final message and writes only
   logs, tables and captures to files.
8. **The lead session is compacted or handed over before it grows**, and at the end of a
   working day it reads the tool's cost screen and runs `scripts/agent_cost.py --latest` and
   writes both into the handoff, so the next routing decision is made from a number. The line
   is 200k tokens of context: a lead measured at 52k to 449k over 248 requests re-read about
   250k per request, and a fresh session (about 60k, its cache written at up to twice the
   input price) pays itself back in under ten turns from 200k. The Claude Code overlay's
   `context_size.py` hook says the size once per 50k step past the line; the lead then
   recommends one of two, with the number and the reason. **Compact** when `docs/STATE.md`
   and the open operation files already hold what matters and the work in flight continues:
   one summary turn is cheaper than a handoff note plus a cold start. **Hand off** (update
   STATE, write the handoff, start fresh) when the work changes direction, a batch has just
   closed, or most of the context is the detail of finished work that a summary would still
   carry. After the warning the lead starts no new round: it lets the running jobs finish,
   commits what is done, updates STATE, then stops and reports, because a session end
   kills every background job it started; the owner decides at that stop, never mid-flow.
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

**The shape follows a threshold, so the lead does not decide it each time.** Work expected
to take more than about an hour, or more than one review round, runs in its own separate
session that {{OWNER_NAME}} can talk to directly (`scripts/spawn_worker.sh`): under a lead it
would wake the whole lead context at every hand-back and stay hidden from {{OWNER_NAME}}. A
short read-only diagnosis or review runs as a sub-agent under the lead: its own session
would pay a session start for nothing. The lead merges and, as the integrating session, runs
the integration build.

The threshold is {{OWNER_NAME}}'s decision from use. The only cost comparison of the two
shapes is one task on 2026-10-03 (the kit's `docs/worker-cost-setups.md`): about 107 against
110 requests, a cost equivalent of about 2.44M against 2.40M tokens. It measured the cost
per worker on one task with one long wait, not wall-clock time, the throughput of several
tasks, or the lead's own cost. Measure in passing: wall-clock from brief to merge, total
tokens including the lead's, review rounds, and waits on an exclusive resource. The sample
will be thin.

`scripts/spawn_worker.sh` (Claude Code overlay) opens the session in tmux with a brief file.
The lead subscribes once for its idle notice and does not message it: every message to an
idle session is a full-context turn. The idle notice also fires on every park on a
background job, and the session does not end with its task. A committed result file of
`Kind: completed` is therefore the end signal; a file of another kind reports a worker still
working or waiting, and is never a reason to close it. After reading a completed one, the
lead decides per task whether the session is reused or closed. It reuses a session that was active within the cache lifetime (one hour) when the
next task is short or needs most of what the session holds. It closes the session when no
next task fits what it holds, or when it has been idle past the cache lifetime (nothing warm
is lost then). Closing is explicit: `scripts/close_worker.sh NAME` ends the tmux session (its
terminal tab closes by itself) and removes the worktree through the same audit as the
post-merge hook's, for that worktree alone. It never deletes the branch. It ends nothing while
a gate (`check.sh`, by its lock) or a git operation (`index.lock`) runs in the worktree: a
session ended mid-run orphans the run, which then races the next gate there. For the same
reason the lead never ends a worker's `claude` process by hand (Task Manager, `Stop-Process`,
`kill`). If one was ended mid-run, wait for its `check.sh` to end, or end that process tree
too (on Windows: Resource Monitor, CPU tab, Associated Handles, search for `check.lock`),
before any gate runs in that worktree. On native Windows a worker in a Windows Terminal tab
may not be registered as a peer session; `spawn_worker.sh` then says so, and no idle notice
comes when it stops on a question, a usage limit or an error. Nothing can read the tab's
pane either, so there `spawn_worker.sh` adds a Notification and a Stop hook to the worker's
`--settings` (the owner's settings and hooks are kept, merged into
`.myagentkit/workers/NAME.settings.json`); they write its state line to
`.myagentkit/workers/NAME.state`: `waiting permission|question TIME ID` when it asks for a
permission, an approval or an answer, `idle TIME ID` when it stops (ID tells two events of
the same second apart). `scripts/watch_workers.sh --result NAME=PATH NAME`, run from the same
checkout, reads that file in place of a pane: WAITING, then the result file as on tmux, then
IDLE (it stopped with no new result), each event once. A worker name is letters, digits, `-`
and `_`, not starting with `-`; both scripts refuse any other. A state file the watcher cannot
read or understand is exit 3 (it names the file: delete it); an absent or empty one is no
signal yet. The folder-trust dialog writes no state line, so the folder must be trusted
already. The lead still looks at the tab after every usage-limit reset. What `close_worker.sh` does NOT see, so
the lead closes only a worker whose result says it is done: a gate or a commit that starts
in the instant between its last check and the kill; a commit waiting in a project's own
pre-commit hook before the gate takes its lock, or in an editor; and a worker whose checkout
is not the one the close runs in (run it from the lead's checkout).

**A stopped worker is answered in its own session, never replaced by a fresh one.** A Codex
worker stopped at a design question; the lead had no channel into its tab, ended it and
started a fresh session on a continuation brief, which read the whole context again and
spent the allowance for nothing. A worker that stops for a decision first finishes what
does not depend on the answer and stops all running jobs. It writes `Kind: blocked` and
QUESTIONS in its result file (`docs/HANDOFF.md`), then publishes the question in the known
question file named in its brief and exits its separate session. A peer worker ends its turn
and remains available to SendMessage. The lead gets the
answer from {{OWNER_NAME}} and delivers it into the SAME session:

- A Claude worker registered as a peer session gets the answer through SendMessage. One that
  is not registered (a Windows Terminal tab, above) gets it typed into its tab by
  {{OWNER_NAME}}, or is resumed (`claude --resume <session id>`) once its tab has closed.
- A Codex worker (`scripts/spawn_codex.sh`) is resumed: the lead writes the answer to a file
  and runs `scripts/spawn_codex.sh NAME ANSWER_FILE --model M --effort LEVEL [--worktree]
  --resume`. The spawning checkout records `.myagentkit/workers/NAME.session`, outside
  the worker; successful `close_worker.sh NAME` removes that record, and on native Windows
  refuses while a Codex session still runs in the worker's folder. It also refuses while the
  worker's decision file waits for its answer. The default result is
  `RESULT-NAME.md` at the worker's repository top, and the decision file is `QUESTION-NAME.md`.
  The lead never commits the default result: the close moves it to
  `.myagentkit/workers/NAME.result.md`, so the audit can remove the finished worktree. A move
  that stopped after the report left its path leaves `.myagentkit/workers/NAME.report-move`,
  naming its source and target, and every later close of NAME refuses until the lead puts the
  report back at one of them (a `.report-move-*` folder beside either holds it), removes the
  marker and closes again.
  `--result FILE` selects another `.md` result inside the worker's folder and `FILE.question.md`;
  the brief must use that spawn-time path, and it is passed again on resume. Publish a question
  or finished result atomically: write a temporary file beside it, end with
  `<!-- codex-worker: ready -->`, then rename it into place with `codex_worker.py --publish
  TEMPORARY_FILE DESTINATION` (spawn's instruction names it), which retries for about two
  seconds a rename Windows refuses while a poll reads the file, and end the turn immediately.
  `codex_worker.py` allows ten seconds for the turn to flush (`KIT_WORKER_GRACE` overrides
  the grace period), then closes only that worker's process tree, using a Windows job or
  an interactive POSIX process group. Windows children start suspended until assigned to
  their job; POSIX escalation signals the entire group. `--no-daemon`
  keeps the worker's runtime separate from any shared Codex server. The script refuses a
  resume while the old session still runs, and refuses a
  fresh replacement when its session or question record exists. On resume the wrapper removes
  the answered question file once the resumed session publishes a new result or exits
  cleanly, never on elapsed time; a failed launch, or a CLI that fails without a new result,
  keeps it for the retry. The result retains the question history.

A stopped worker is always answered in its own session, never replaced with a fresh one.

**The lead commits a Codex worker's work (#43).** The worker's brief instructs it to leave
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
needed. After PROGRESS or HANDOFF the worker goes on, and `--wait` prints its exact follow-up
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
report. It returns DONE, BLOCKED,
HANDOFF or PROGRESS once the file is committed on a clean tree, QUESTIONS when the file holds
open questions, CONTEXT when the session's context passes the warning line (50 percent by
default), WAITING on a dialog, and GONE. The lead acts on the report's first line
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

A worker never links a shared folder into its worktree (a junction, a symlink, a bind
mount: a virtual environment, a cache, a data set). It names the shared one by path or
environment variable instead (the interpreter's full path, `VIRTUAL_ENV`, a cache variable).
On Windows, `git worktree remove` went through such a junction and deleted part of the main
checkout's virtual environment; `clean_worktrees.sh` now keeps a worktree that holds one, and
it stays until the link is removed by hand (`rmdir <link>` removes a junction, not what it
points at).

A worker whose worktree directory is missing STOPS and reports. It never recreates the
directory and never runs a git command from where it used to be: that folder lies inside the
main checkout, so git there acts on the owner's main worktree.

## Review rounds — early, inside the worker, in parallel

In one project a feature took five fix rounds in about seven hours. Each round cost a fresh
worker re-reading 100k to 300k tokens (20 to 60 minutes), a ten-minute self-test, reviews of
5 to 15 minutes and a merge with another self-test. Most findings of rounds 2 to 5 sat in code
the previous fix had added, in classes the reviewers had already shown once. The rules below
move the review into the worker's warm context and run together what can run together. They
remove no review.

### Design before code

- A new mechanism gets a one-page design before any code. A new mechanism is anything that
  deletes or moves files, rewrites history, or changes a gate.
- The design names what the mechanism protects, what it excludes by decision, its rules, and
  the cases in which it still loses data or fails. It is the threat model of
  `docs/REVIEW_GATE.md`, "A review loop: threat model, stopping rule, evidence".
- The design is reviewed under its own review label (`docs/REVIEW_RUNNING.md`, "Rounds,
  labels and designs"). Code starts after that review.
- The design's exclusions are the dispositions for later code rounds. A finding inside an
  exclusion is answered with the exclusion, not with a fix.
- The kit repository's `docs/worker-lifecycle-options.md` shows the shape: the facts, the
  options with their costs, and what a second model should attack.

A design round on one page takes about fifteen minutes, and the same flaw found in code
costs a fix round.

### Review inside the worker

- A worker that can start a sub-agent (a separate session) reviews its own diff before it
  reports. It starts a fresh diff reviewer as a sub-agent (the Claude Code overlay's
  `diff-reviewer`), fixes what the review finds, and starts a new fresh reviewer on the
  result. This inner pass is the same model's early check; the gate's review by the other
  model follows `docs/REVIEW_GATE.md` and `docs/REVIEW_RUNNING.md`, including the named
  saver mode's exception for who fixes findings.
- Each inner round's prompt carries the earlier inner rounds' findings and the worker's
  dispositions (`docs/REVIEW_GATE.md`, "Findings, earlier rounds and dispositions").
- The reviewer is a new sub-agent in every inner round, because the author never reviews its
  own change.
- The worker reports when a review returns no Critical, High or Medium finding, or when it
  has argued a disposition for each one that remains.
- The report lists the inner rounds: their count, the findings fixed and each disposition.
- A worker that cannot start a sub-agent (a sub-agent itself) says so in its report. The lead
  then starts the review the moment the worker's branch exists, in parallel with the
  self-test, never after it.
- The inner rounds do not replace the lead's review. A risky diff still passes
  `docs/REVIEW_GATE.md` before the merge, and the inner rounds make that review shorter.

A fix in the worker's warm context, in an inner round, costs minutes. The same finding left
for the gate's cross-model review goes to a fresh worker of the reviewing model, which pays
the whole re-read. The brief states which of the two cases it expects (`docs/HANDOFF.md`,
"The brief").

### Before you report

A worker goes through `docs/REVIEW_GATE.md`, "What a reviewer attacks first", against its own
diff before it reports. It fixes each hit or names it in the report. A class the reviewer has
already shown once costs a whole round when the worker leaves it for the reviewer to find again.

### The lead's steps when a branch is ready

The lead never changes its shell directory into a worker's worktree; use `git -C <worktree>` for its Git commands.
The shell stays in the lead's checkout, so its Stop hook runs that checkout's gate.

1. Start the self-test and the review together, on the same commit, never one after the other.
2. Run two reviewers at the same time, never one after the other.
3. Keep one review label for the whole feature, so that each round carries the earlier ones.
   Only the final reviews (one per model, each over the parts it did not write) take a label
   never used before (`docs/REVIEW_RUNNING.md`,
   "Rounds, labels and designs").
   When model B's final review finds a High or Medium, model B fixes its own findings.
   Then model A reviews B's fix under a fresh label.
   B's final review counts as clean for every other part.
   Closure requires no open High or Medium finding on any part by a model that did not write that part.
4. Start the next worker while the self-test after a merge still runs. If that self-test
   fails, tell the next worker to rebase onto the fix.

Each step that waits on another adds its whole duration to the round, and nothing in a round
needs another step's result before it starts.

What the watcher reports decides the lead's next step for a spawned worker:

- **QUESTIONS:** the lead asks them at once, one at a time, through its question tool, before
  the merge or in the same breath. It records each answer, and the general rule the answer
  sets, in its permanent home, not only in the chat.
- **CONTEXT:** the lead decides from the worker's `Remaining:` line and the figure whether
  the worker finishes, compacts or hands off. A session with two short steps left finishes;
  one with a long operation ahead hands off or compacts, because it pays the figure on every
  remaining request.
- **DONE:** the lead reads the result file before anything else.
- **HANDOFF:** the lead reads the result file and starts a fresh session from it. A
  `Kind: handoff` file is not done.
- **BLOCKED** and **PROGRESS:** the lead reads the result file. Neither is done.
- **Finished session:** when the lead decides a session is finished (no next task fits what
  it holds, or it is idle past the cache lifetime), it runs `scripts/close_worker.sh NAME`.
  The worktree then goes through the same audit as the post-merge hook's; a kept worktree
  is reported with its reason, and the branch is never deleted.

## Token economics — the always-loaded prefix is money

Cached input tokens are discounted heavily, so a STABLE prompt prefix — the documents loaded
at the start of every session — is the largest single cost lever available. Every edit to
one of those files invalidates the cache for every session after it.

- Do NOT edit `AGENTS.md`, `docs/ARCHITECTURE.md` or any other always-loaded doc in the
  middle of a session unless the task IS that document.
- Batch documentation edits into their own task and their own session.
- Keep always-loaded docs SMALL and STABLE. Size here is not a readability preference; it is
  a recurring bill.
- Volatile state belongs in `docs/STATE.md`, which is read every session and therefore kept
  small. Reference docs like `docs/GOTCHAS.md` stay off the session-start list entirely.

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
  agent may add OPEN items freely (`AGENTS.md`, design authority). Capturing a question costs
  nothing and losing one is expensive. The cost of a missed capture is a forgotten question;
  the cost of a wrong promotion is every future session treating a musing as law.
- `docs/ARCHITECTURE.md` is updated in the SAME task that adds a module or moves a boundary.
  It is also the reason this project does not need a code-search or embedding tool: the
  module table IS the navigation. If agents start failing to find things through it, the
  first reading of that signal is architectural decay, not a missing tool.
- These files are worth more than the code: code can be regenerated, context cannot.
