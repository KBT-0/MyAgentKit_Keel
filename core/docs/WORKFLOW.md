# Development Workflow

Goal: this project is written almost entirely by AI agents. Prevent spaghetti, keep the
code readable by a human, and stop the classic decay where agent productivity drops as the
codebase grows.

## How we work — roles

- **LEAD** — plans with {{OWNER_NAME}}. Reads `docs/PROJECT.md` (by section), `docs/PHASES.md`
  and `docs/ARCHITECTURE.md`.
  Produces the task brief (`docs/HANDOFF.md`). Decides model routing. Does not implement.
- **WORKER** — implements one task in one module. Bound by `AGENTS.md`, the gates, the tests.
- **REVIEWER** — `docs/REVIEW_GATE.md`. A fresh session that did not write the patch; the
  working mode names who takes it (`docs/REVIEW_GATE.md`, "Invariant"). Its findings go back
  to the author's side ("Worker cost", rule 2).

{{OWNER_NAME}} alone decides: OPEN design items, taste and balance calls, scope, and whether
a risky change ships. Agents propose; {{OWNER_NAME}} decides.

**If the task brief does not state a role, you are the WORKER.** This default covers a session
started from a brief and a sub-agent; the session {{OWNER_NAME}} opens and talks to has no
brief and is the LEAD. A default falls to the
narrowest role (a fail-safe default, Saltzer and Schroeder); the choice is the owner's, no
study measured it.

Three Claude sessions get the short appendix, `BEHAVIOUR.md`: a lead started with the
command below, a worker session, and a bridged reviewer. It is a kit-owned
file that a sync refreshes; the project changes it only through the kit. `scripts/spawn_worker.sh`
passes it to every worker session with `--append-system-prompt-file`. `scripts/claude_bridge.py`
appends it to the reviewer's prompt without the lines marked `<!-- author-only -->`. An Agent-tool
sub-agent (the Claude Code overlay's `worker.md` and `diff-reviewer.md`, the inner review
included) gets no appendix: its definition is its whole system prompt, so the A/B below
covers spawned workers and bridged reviews only. The lead starts a fresh enabled session with:
`env -u MYAGENTKIT_NO_BEHAVIOUR claude --append-system-prompt-file BEHAVIOUR.md`.
The lead starts a fresh disabled session with:
`MYAGENTKIT_NO_BEHAVIOUR=1 claude`.
A Codex session gets no appendix, because Codex has no such flag.
`MYAGENTKIT_NO_BEHAVIOUR=1` disables the worker and reviewer appendix; the disabled lead command
omits the appendix flag and passes the toggle to its workers and reviews.
Every review's usage record notes `behaviour: on` or `off`, and `scripts/usage_summary.py` totals
the rounds and rejects of each side. A resumed session keeps the system prompt it started with,
so an A/B counts only sessions started fresh on its side (code.claude.com/docs/en/cli-reference,
"System prompt flags in resumed conversations"). `BEHAVIOUR.md` is unmeasured: the on/off toggle
and the usage record exist so the A/B can decide, and until it runs the appendix is the owner's
choice. It holds only lines `AGENTS.md` does not already say in the same words.

## Task lifecycle (every task)

1. **Read:** `AGENTS.md` → `docs/PHASES.md` → `docs/STATE.md` → the target folder's
   `AGENTS.md`; `docs/ARCHITECTURE.md` when the task crosses a module boundary (`AGENTS.md`,
   reading order; a sub-agent, reviewer or briefed session reads what its brief names
   instead, as `AGENTS.md` says at its top). Do not explore beyond the files the
   task lists; context is a budget.
   `docs/PROJECT.md` is read by SECTION, only when the task needs one.
2. **Plan:** LIST the files you will touch; a diff you can describe in one sentence skips the
   list, and the brief's `Owns:` line holds either way. If the files exceed one module, STOP
   and propose splitting the task. Check the task against the current phase's out-of-scope
   list — needing something on it is a STOP, not a reason to widen the phase.
3. **Implement:** a small, focused change (`AGENTS.md`, "Task discipline": no drive-by
   refactors).
4. **Test and gate:** a logic change brings its test in the same change; writing the test
   first is advice, not a rule (a bug fix starts well from a failing test that reproduces
   it). An ordinary test needs no mandatory red proof; the review asks whether it breaks when
   the code is reverted. Only a gate check must prove red, by its fixture test ("Writing a
   gate"). A generated-content pipeline validates its output (data validation, captures);
   unit tests of the generator are not mandatory. Existing tests stay; only tests measured as redundant or slow
   are consolidated (the kit's `docs/research/test-rules.md`). Then run `./scripts/check.sh`
   before finishing.
   The same script is wired into git as `.githooks/pre-commit`, so a failing gate aborts the
   commit for every tool — but running it yourself is still the rule. The hook is the
   backstop, not the plan, and agents never bypass it with `--no-verify`.
5. **Review by tier:** the brief's `Risk:` line names the tier, and the tier names the
   review (`docs/REVIEW_GATE.md`, "Risk tiers"): one light reviewer for low, one for medium,
   two for high (gates, hooks, check scripts, review tooling); code in {{RISKY_AREAS}} is
   medium.
   It runs in a FRESH session before the change reaches the main branch (when exactly:
   `docs/REVIEW_GATE.md`, its opening lines). The author never approves their own patch.
6. **Document:** a changed public API updates its README in the same task (`AGENTS.md`,
   "Task discipline").
7. **Update `docs/STATE.md`:** active work and what waits on {{OWNER_NAME}}, with a
   tool+model trace ("The state, backlog and phase files" says why). Unwritten progress does
   not exist. A next task or a parked item goes to
   `docs/BACKLOG.md`, which is read when the next task is chosen, not every session.
   Edit it as `docs/AGENTS.md`, "STATE.md discipline", says, never touching the "Working mode:" line.
8. **Summarize:** what, why, which files. If you hit an OPEN design item, flag it as a
   question rather than deciding it, and go on with work that does not depend on it.

## Task ids

- A task id is a short token that starts with a letter and holds at least one digit:
  letters and digits, with at most one inner `-` (`K4`, `L1b`, `R12`, `K7-a`). A line in
  `docs/STATE.md` or `docs/BACKLOG.md` MAY name its task by id; none has to. Ids are
  case-insensitive: `k4` and `K4` are the same task. The format is the owner's choice: the
  digit keeps a plain word from being read as an id, and one inner `-` keeps ids short and
  greppable. Pick a shape no other label in these files uses: a task `M7` and a milestone
  `M7` are one token, so closing the task fails every later line naming the milestone (#136);
  a prefix of the project's own (`T-12`) keeps them apart.
- The commit that finishes a task says so with a trailer, ONE per id, in the last paragraph
  of the message: `Done: K4`. The value is exactly one id: the hook rejects `Done: K4 K5`,
  `Done: K4, K5` and an empty `Done:`, and such a value already in the history closes
  nothing (`check.sh` prints a NOTE naming the commit). Git reads the key in any case, so
  `done: K4` closes K4 too. For work done on a branch, the integrating session's merge
  commit carries it: `git merge --no-commit <branch>`, delete the id's line from
  `docs/STATE.md` and stage it, then `git commit` with the trailer, because `commit-msg`
  reads the staged STATE.md and a plain `git merge` commits before that line is gone. The trailer is git's own format (git-scm.com/docs/git-interpret-trailers).
- `.githooks/commit-msg` rejects that commit while the `docs/STATE.md` or `docs/BACKLOG.md`
  it records still names the id, and says which line; `./scripts/check.sh` fails `[state]`
  when either file names an id that any commit in the history closed. The strong review
  cycle's `docs/STRONG_REVIEW.md` and `docs/reviews/strong-*.md` are checked the same way, and
  so is every audit in the index (`docs/audits/*.md`, however old; "Periodic architecture
  audit"). A mention is the id as a whole token anywhere in the file, prose included: "the E7
  session" blocks closing E7 as a finding line does, so reword or delete it.
  Whole word: closing `K3` says nothing about `K3b`.
- A closed id is never reused. A task needed again gets a new id. A closed id is already in
  git history as `Done: K4`; reusing it would make the old commit look like it closed the new
  work (issue trackers keep retired keys reserved for the same reason: GitLab issue 4068,
  Jira JRACLOUD-78272).

Why: docs/WORKFLOW_RATIONALE.md, "Task ids".

## Task sizing

- Ideal: one module, one to five files, finishes in one session, describable in one sentence.
- "Write the billing system" is not a task. "Add the retry policy to the payment client,
  with tests" is.
- Big work is split into a task list first — planning is itself a task.

A duration (an answer to "how long", a plan's size, an option's cost) is agent wall clock,
summed from the rows below: the steps, a review and its fix round per step, a gate run per
merge, the merges, and a session start or compaction for every fresh, handed-off or compacted
worker. It is a range with the rows' n, and owner waits, approvals and nights are named apart.
A part whose row says "not measured" is said so, never filled with a guess: a model prices work
in human time and has no clock, an early guess anchors later ones, and the project's own past
runs are the reference that holds (the kit's `docs/research/agent-durations.md`, findings
1-8). Never weeks, person-days, a human-team figure or a line count alone; a rewrite that
replaces a library is sized by what the library does, its implicit features included.

Measured agent times. After a merge the lead overwrites a row whose range the run changes,
from git timestamps, the result file, `scripts/usage_summary.py` (reviews) and Claude Code's
`claude_code.compaction` `duration_ms`; a row is never appended and an old figure is never kept
beside a new one (findings 2 and 9).

| Unit | Measured (range, n, date) |
|---|---|
| Worker step, brief to result | not measured |
| Review fix round | not measured |
| Light review | not measured |
| Full review | not measured |
| Gate run | not measured |
| Merge | not measured |
| Session start or compaction | not measured |

## The state, backlog and phase files

The rules for `docs/STATE.md` are in `docs/AGENTS.md`, "STATE.md discipline"; their reasons are
in `docs/WORKFLOW_RATIONALE.md`, so that the always-loaded files carry only the rules.

The branch and worktree policy below decides which session may edit STATE.md.

- **A living file never keeps a closed item.** Every file that collects items deletes an item
  in the step that closes it. The `Done:` check enforces it mechanically for STATE.md,
  BACKLOG.md and the strong review files; for an operation file (its last acceptance item)
  and a handoff (its writer deletes) it is a discipline rule. A new file of that kind ships
  with its deletion step, because STATE.md bloated whenever cleanup was left to an agent's
  judgement (code.claude.com/docs/en/best-practices: a bloated instruction file gets ignored).
- **Open issues are never closed to finish a release.** A release is done when its issues are
  fixed, or when {{OWNER_NAME}} has moved them, explicitly, to a named later version: an issue
  closed unfixed hides the defect it named.
- **A lesson is written into the project's own documents** (and, for the kit, through
  `/myagentkit:kit-feedback`), never only into a lead's private memory, because the next
  session, the other model and the other projects never read that memory (Claude Code's auto
  memory is per machine and per tool, code.claude.com/docs/en/memory).
- An operation's detail lives in its own file, `docs/<OPERATION>.md`, never in STATE.md. The
  operation file tracks progress with checkboxes; its last acceptance item is "STATE.md
  harvested and pruned", and the file is deleted when the operation closes (the history is
  in git). Without this rule every integration folds more into STATE.md, and it only grows:
  one project's state file reached 38 KB. Spec tools keep a task list in its own file the same
  way (Kiro's `tasks.md`, kiro.dev/docs/specs); they archive it when done, the kit deletes it.
- Compressed chat styles do not apply to STATE.md: the next tool reading it knows nothing
  about your plugins.

`docs/PHASES.md` is read every session. It is short on purpose: the CURRENT phase in full,
everything after it in one line each. Detail arrives when a phase becomes current, not before — a plan written
for a phase three steps away is mostly aspiration, and aspiration in an always-loaded file
is a bill with nothing behind it. Project managers call this rolling-wave planning; GitHub
Spec Kit's `spec-driven.md` likewise steers away from speculative features.

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

Other kits archive a finished plan instead (OpenAI's `exec-plans/completed`, OpenSpec's archive
folder); the kit harvests and deletes, the owner's choice: an archive costs no context, but it
goes stale and needs upkeep. That is the same harvest-then-prune rule `docs/STATE.md` follows, one scale up. The three
files differ only in how long their contents stay true:

| File | Horizon | On completion |
|---|---|---|
| `docs/PROJECT.md` | Permanent | Superseded, never deleted |
| `docs/PHASES.md` | This phase | Deleted after harvest |
| `docs/STATE.md` | Right now | Deleted when the task is done |

A multi-item operation with checkboxes is NOT a phase. It gets a throwaway file of its own —
`docs/CHANGE_ORDER.md`, or whatever the operation is called — which is deleted when the
operation closes; the rule is in `docs/AGENTS.md`, "STATE.md discipline". Phases are standing; operations are
disposable, and neither one is ever tracked inside the other.

Why: docs/WORKFLOW_RATIONALE.md, "The state, backlog and phase files".

## Writing a gate

Gates get their own rules because they fail differently from ordinary code: when a gate
breaks, everything keeps looking green.

- **Prove it RED, and keep it red with a fixture test.** Construct the failure condition,
  watch the check reject it, undo it, and add a fixture test for the check to the project's
  test suite in the same task (the kit's `docs/gates-must-be-proven-red.md`). This red proof
  is for gate checks; an ordinary test needs none (the kit's `docs/research/test-rules.md`,
  findings 4 to 6). It is TDD's red step at the size of a gate; seeded failures measurably
  improved the tests developers wrote (Petrović et al., ICSE 2021,
  arxiv.org/abs/2103.07189), and a check that cannot fail does not fail securely (OWASP,
  "Fail securely").
- **One fixture test per check, never a run of the whole gate.** The test feeds the check a
  small input in a throwaway folder: an input that breaks the rule must turn it red with its
  own `FAIL [tag]` line, and a clean one must leave it green, as rule checkers test their rules
  (Semgrep's `ruleid:`/`ok:` cases, ESLint's RuleTester valid/invalid cases). It runs in the
  normal suite in milliseconds to seconds, never writes into the checkout and never runs the
  project build (the kit's `docs/research/kit-self-checks.md`, findings 1 and 2).
  `scripts/boundary_checks.sh` shows the test for its example check; the build command runs
  it. The kit tests the shipped `scripts/check.sh` checks the same way.
- **The build cache is opt-in: declare what the build reads outside the tree.** Set
  `build_cache_inputs` in `scripts/check.sh` to a command printing those inputs; its key also
  covers every file `git ls-files --cached --others --exclude-standard` names, read from disk,
  and the gate script itself. Starters: `cmake --version`, the MSVC banner (`cl 2>&1 | head -n 1`),
  `ninja --version`, `python --version` and a hash of `python -m pip freeze`, `blender --version`,
  `git lfs ls-files -l`. Unity: `ProjectSettings/ProjectVersion.txt` and
  `Packages/packages-lock.json` are tracked, so already in the key; `Library/` stays out. A
  cached run prints `NOTE [build]: not run: cached PASS <key> from <date>` and says so in its
  PASS line: report it as a cached build, never as a build you ran.
- **One gate run per checkout at a time.** `check.sh` holds a per-checkout lock for a whole
  run, so a second gate run waits instead of racing; tests that write scratch files still use
  a unique temporary directory, never a fixed name in the build or working directory.
- **A test or an experiment never executes a file whose name ends in `.exe`.** Under WSL a
  Windows executable is handed to Windows, which may show {{OWNER_NAME}} a GUI error dialog;
  whether WSL matches the name or the file's first bytes is not verified yet
  (`docs/GOTCHAS.md`), so the rule keeps both out. Name a stub
  for a Windows launcher without `.exe`, and reach it through an overridable variable
  (`docs/GOTCHAS.md`).
- **Test both directions** where a gate can produce false positives. A gate that always
  fails is as useless as one that never does, and it gets deleted by the first person it
  blocks unfairly (Fowler, "Eradicating Non-Determinism in Tests").
- **Fail on absent evidence.** No output file, an empty diff, a tool that did not run: all
  FAIL. An exit code is not evidence that work happened: pytest exits 5 when it collected no
  test (docs.pytest.org/en/stable/reference/exit-codes.html), and jest passes an empty run
  only when told to (`--passWithNoTests`, jestjs.io/docs/cli).
- **Parse tool output defensively.** Parse machine output from a structured format (JSON),
  not from coloured text; set `NO_COLOR` for any CLI whose text you must match (no-color.org;
  Claude Code's `--output-format json`, code.claude.com/docs/en/cli-reference). When you must
  match text, strip ANSI escapes first: a coloured phrase silently stops matching. If an
  extracted field comes out empty, SAY it was not found; never write it out blank, because a
  blank field looks like a field.

## A red gate that passes on re-run

A FAIL that does not reproduce is not a PASS to forget. A timing-dependent test, a gate that
overlapped another gate, or a real race all look the same afterwards: the next
run is green, and the failing test, its error line and the load it ran under are gone, so a
real race is never seen again until it bites in CI or production.

- **Record it before you commit on the green run**, in `docs/STATE.md` or the operation's
  own file (a branch session writes its worktree note instead) as a `[GOTCHA]` line: the
  failing test and its error line, the retry count, what else was running (another gate, a
  review) and the suspected cause.
- **Re-run once only to learn whether the failure is repeatable in the same state;** a pass
  does not show it was chance (Gruber et al., "An Empirical Study of Flaky Tests in Python",
  arxiv.org/abs/2101.09077). A second red is a real failure. Never re-run until it turns
  green: a retry that is not recorded is a failure silently deleted. "Once" is the owner's
  choice for cost, not a measured number.
- **A test seen twice is fixed.** If the same test shows up in a second `[GOTCHA]` line, it is
  quarantined or fixed within the task, never left (Fowler, "Eradicating Non-Determinism in
  Tests", martinfowler.com/articles/nonDeterminism.html).

## Spike protocol

Uncertain or risky topics are tried as throwaway code on a `spike/` branch first. Spike code
NEVER moves into the main code — the learning is rewritten cleanly. Record the outcome as a
five-to-ten line note in `docs/spikes/`.

## Decay early-warning system

Two levels. **Stop the task and report** when you see:

- Tests skipped, weakened or deleted, and the task did not ask for it.
- A gate that has been edited but not re-proven red.
- A forbidden dependency crossing a boundary.

**Mention once** in the closing summary, without stopping the work, and add it to the
audit's list ("Periodic architecture audit"):

- A SECOND system or class doing the same job — propose a merge.
- A README contradicting the actual public API (doc drift).
- A file that does two jobs, or is too large to read in one pass, or a class doing
  everything (`AGENTS.md`, "Language & style"). The kit sets no line count; a project that
  wants a number writes one NOTE into `scripts/check.sh`.

Why: docs/WORKFLOW_RATIONALE.md, "Decay early-warning system".

## Periodic architecture audit (critical ritual)

At a regular cadence — suggested every ~20 tasks or monthly — run an audit-only task in
which NO code is written:

- Boundary violation scan.
- Duplicate and dead code hunt.
- READMEs versus actual public APIs.
- Module size and complexity report.
- **Gate audit:** run the fixture tests. Does every check still go red, and does every check
  have a test? Then ask the question the fixture tests cannot: **does any gate
  guard a path that does not exist?** A scan over a missing directory finds nothing and
  looks exactly like a clean result, so such a gate reports PASS forever while protecting
  nothing — and its silence is identical before and after the module it guards arrives.
  The mechanical answer lives in `boundary_checks.sh`' dormant notice; the audit confirms the
  notice fires, it does not replace it.
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
  nothing without the owner's yes, in the chat or given in advance as `kit_feedback:
  standing-approval` (the command's §4). A fix that stays local works, which is precisely why the
  upstream one then never happens and the next project inherits the original problem.

Output: a short `docs/audits/YYYY-MM.md` whose findings carry task ids ("Task ids"), plus the
cleanup tasks that enter the normal loop under those ids. The file is deleted by the commit
that closes its last id: a living file keeps no closed item ("The state, backlog and phase
files"), and debt that is not tracked to its close stays open (Martini, Besker and Bosch,
2018). The gate reads audit files and prints a NOTE for ids closed in reachable history;
old audit mentions do not fail an upgraded project. The commit-msg hook still refuses a
closing `Done:` trailer while any audit in the index names that id, an old one included. **The audit is itself a task; skip it and decay advances
invisibly.**

## The strong review cycle — at least every ten days

The audit above looks for decay; this cycle asks the strongest models what everyone working
day to day has stopped seeing. It runs at least every ten days or after 20 closed tasks,
whichever comes first (`STRONG_REVIEW_DAYS` and `STRONG_REVIEW_TASKS` in `scripts/check.sh`),
and the gate prints a NOTE when no strong review report was added in that span, so it does
not depend on anyone remembering it. The numbers are the owner's choice, not a measured
cadence (ten days came from a project's request, kit issue #61).

- **The list:** `docs/STRONG_REVIEW.md` holds the questions for the next cycle and the open
  findings of earlier ones. Each strong model writes its own report,
  `docs/reviews/strong-<YYYY-MM-DD>-<model>.md`, and never edits another model's report.
- **Scope:** everything that reached the main branch since the previous cycle's report, and
  the open questions in the list.
- **First reviewer:** the strongest model available, read-only, in a fresh session
  ("Model routing"). Its report has four headings: consistency with the design
  document's decisions; the look, where the project has one; performance and cost at full
  scale; code health (duplicate systems, test gaps). Each finding carries a task id
  ("Task ids"), a severity and its evidence. The id is a task id of the project's own shape,
  never a label of the report's own (`P3`, `F16`): such a label is one token with a task of
  that name, and closing the task is refused while the report names it (#301). A report that
  needs labels of its own gives them a prefix no task id uses.
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
- **A second tool or family is welcome, never required:** it reduces correlated blind spots
  but does not remove them, and the one controlled measurement found the direction asymmetric
  (the kit's `docs/research/claude-lead-codex.md`, finding 4). The reviewer's model family,
  not its CLI, makes it independent (`docs/REVIEW_GATE.md`, "Invariant"), and the working
  mode says which family takes which role ("Working modes, by name"): when the author's
  budget runs short, saver applies and the review is never dropped.
- **A second agent's output is untrusted INPUT to a decision the calling agent owns**, never
  a verdict to relay verbatim. Verify each finding against the code: drop what is disproved,
  keep what is confirmed, and treat a confirmed critical finding as a stop signal. The author
  of the patch drops nothing: it records dispositions (`docs/REVIEW_GATE.md`, "Verdicts and
  who decides").
- **A worker's "not done" or "noticed, not fixed" line about something the brief asked for
  is a finding.** The lead has it fixed before the merge. A worker's list of new ideas is a
  question for {{OWNER_NAME}}, never an automatic next round.
- The review gate the brief's `Risk:` tier requires starts without asking, in the family
  the working mode names. An extra review beyond it (another family, a higher effort, a paid
  backend) spends budget the gate did not plan: {{OWNER_NAME}} asks for it in the session, or
  it does not happen (`/myagentkit:cross-review`). Sources: Anthropic's prompting guide asks
  an agent to stay inside the scope it was given (platform.claude.com, "Prompting Claude
  Sonnet 5.5", "Steer initiative and scope"), and OpenAI's own Codex plugin warns that an
  automatic review loop "may drain usage limits quickly" (github.com/openai/codex-plugin-cc).

## Parallel work — worktree policy

Not every part of a repository tolerates a second working copy. Before starting parallel
work, check the path you are about to touch:

{{WORKTREE_POLICY}}

**Ceiling: 2 concurrent worktrees, 3 at the absolute most.** Published ceilings of four to
eight per developer assume review capacity is not the bottleneck. For a solo developer on a
limited token budget it is exactly the bottleneck: parallelism multiplies token burn
linearly while review capacity stays fixed, so a fourth branch does not produce a fourth
stream of merged work — it produces a queue.

**One master writer per main checkout.** Only one session writes to the main branch in the
main checkout: the one {{OWNER_NAME}} opened for the release and merge work, recorded as a
`**Master writer:**` line in `docs/STATE.md` next to the "Working mode:" line. Every other lead
(another operation, another project session on the same repository) works on its own branch in
its own worktree and never commits or merges in the main checkout. Its merge goes to the master
writer as a MERGE REQUEST message, or waits for the writer's MAIN CHECKOUT IDLE message (both
shapes: `docs/COMMUNICATION.md`, "Workers"). IDLE hands the main checkout over: the waiting lead
makes its own merge there, nothing else, and sends MAIN CHECKOUT IDLE back when done; the writer
writes nothing in the main checkout until that reply comes, even after the window. Why (field data, project_leeway, 2026-10-22: three
lead sessions in one main checkout in one night): (1) a lead's staged file rode into another
lead's merge commit, since staging and the gated commit are minutes apart; (2) a gated merge
passed its gate and then failed with "cannot lock ref HEAD: is at X but expected Y", because
another lead fast-forwarded the main branch during the gate, and the retry would have recorded
a plain commit instead of the merge; (3) a retry hit `.git/index.lock`, held by a third lead's
gated commit. The enforcing hook (a `.myagentkit/master-writer` marker that the gate and commit
hook check) is planned for v0.13; until then this rule is what holds.

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
  rebase onto it. A rebase, cherry-pick or revert runs no git hook, so the gate never saw the
  rebased tree: run `./scripts/check.sh` on it before it fast-forwards the main branch.
- A contract-first task therefore comes BEFORE any parallel fan-out. If the interfaces are
  not settled, do not fan out yet.
- A shared contract that two branches both use has a test that states what its consumer
  expects; a change that breaks it names the branch (consumer-driven contract tests,
  Thoughtworks Technology Radar; Pact).
- Merge in dependency order, and run the gate after every merge before the next one (the
  same idea as a merge queue, docs.github.com, "Managing a merge queue"). A gate run on the
  merged tree is the only thing that catches a semantic conflict.

## Parallel work — a second session may be live in the SAME tree

This happened and it cost budget: two sessions worked the same task list at the same time in
one working tree, with no branch and no note. Nothing was lost by luck rather than design.

Reading `docs/STATE.md` at session start is therefore not enough on its own — it is a
snapshot of a file another process may be editing right now.

- Before declaring a task item unapplied, run `git status` and look for modifications you
  did not make. Unexpected changes mean someone else is working here.
- If they are there, stop and ask rather than re-applying: a second application costs budget
  and can overwrite the first.

## Model routing — by cost per task and by scarcity

The tiers below sort the work; the working mode in force ("Working modes, by name") says
which side takes each tier. The model names are this kit's as of 2026-10-08: replace them
with what the owner's subscriptions offer today (rule 4). The top model the plan has is the
lead (it plans, briefs, routes and merges); the workers are the tiers below it (owner's
choice, 2026-10-19; rule 2 says when the top model takes an errand itself).

| Tier | Work | Codex | Claude |
|---|---|---|---|
| 1 | Mechanical: renames, figure fixes, data fetches, proof runs, summaries | `gpt-6-luna`, medium effort | Haiku 5.5 or Sonnet 5.5, medium effort |
| 2 | Detail-bearing errands, ordinary reviews | `gpt-6.1-sol`, high effort | Opus 5.5, high effort, only for design-bearing work |
| 3 | Risky and gate reviews, design consultations | `gpt-6.1-sol`, high effort; `gpt-6-astra` when the lead picks it | Opus 5.5, high effort; Fable 5.1 when the lead picks it |
| Review | The required review of any change, chosen per task like a worker | at least the author's tier: a stronger one; for an Astra author, Astra again in a fresh session | the same rule: for a Fable author, Fable in a fresh session |

The review row is `docs/REVIEW_GATE.md`, "Invariant", with its sources (Anthropic's separate
writer and reviewer sessions, `docs/research/ai-review-workflows.md` [1]; self-review's zero
gain measured in the same session, [25]); no source measured the tier order, which is the
owner's choice. The prices behind the table come from third-party summaries of OpenAI's launch figures:
Luna costs about a twentieth of Sol's token price, and Sol 6.1 about a fifth of Astra's.
Neither the per-model Codex allowance nor the quality claims were verified. **The table is
provisional**: API token prices say nothing about how much each model draws from a
subscription's five-hour and weekly allowance. Measure that draw (`/status` before and after
a few errands per model) and move the tiers by it (rule 5).

The principle behind whatever the table says: **route by cost per completed task, and by
scarcity where the owner's subscriptions differ.** Send volume to the cheaper model only when
the output is checkable (tests, a compiler, a diff the lead reads) and the work either has a
long cost tail or does not fit one context; a single dependent chain stays with one model at
lower effort. Source: Anthropic, "Optimizing for cost and intelligence"
(platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence: compare
models by cost per completed task; delegation saved only on those two work shapes). The
scarcity half is the owner's judgement, measured by rule 5. The review of a risky diff stays
mandatory, in a fresh session with no shared context: that is what decorrelates its judgement
from the author's (`docs/REVIEW_GATE.md`, "Invariant", says who takes it).

The table decides the AUTHOR and REVIEWER roles and may change its mind each month. A swap is
recorded in `scripts/review.sh` and in `docs/STATE.md`; the review records stay comparable
across it because both directions publish one format. **Limit:** no change is reviewed by a
weaker tier than its author's alone (the review row), so a budget swap moves the authors, never
a review below its author (`docs/research/claude-lead-codex.md`, findings 4 and 9: a weaker
reviewer of a stronger author measured worse than the author alone).

Caveat worth stating once: a more autonomous model fills ambiguity by itself instead of
asking. The mitigations are sharper briefs (`docs/HANDOFF.md`) and the gates, not trust.

**Reasoning effort is the second dial.** Choose effort from this table for implementation
and review. Running everything high spends the scarce budget on work that did not need it.

| Work | Effort |
|---|---|
| Mechanical work and re-review of a small fix round | medium |
| A new mechanism's first round, a gate/hook/review-tooling change, or a risky diff | high |
| A review | medium; on a high-tier change each of the two reviewers at high (`REVIEW_RISK=high` sets the default); never xhigh or max |
| Work requiring xhigh/max | Only by the lead's decision, with the reason in the brief; never a review |

Effort is chosen anew for every round from this table: effort is never carried up from the
round before, and a `REVIEW_ROUND_EXCEPTION` round picks its model and effort here again.
Anthropic's guide does the same: a step up to a stronger model starts at that model's
default effort, and effort levels are compared in separate sessions ("Optimizing for cost and
intelligence"; code.claude.com/docs/en/model-config, "Adjust effort level").

Every brief carries `Route: quick|build|deep · Risk: low|medium|high · Checks: ...`, plus
the chosen model and effort. Route describes the task's shape: `quick` is a fully specified
small change (a few lines, one file, no design block); `build` is an ordinary implementation
task in one module, with the brief's five-to-ten-line design; `deep` needs a design decision
or an investigation first (a new mechanism, a cross-module change, an unknown root cause),
so its design is reviewed under its own label before code ("Design before code"). Risk names
the review tier (`docs/REVIEW_GATE.md`, "Risk tiers"). `Checks:` lists what the worker runs
on top of the gate, never instead of it (rule 9 of "Worker cost": the gate always runs): for
low, the tests of the touched files; for medium, the focused suites, plus the project's
packaging consistency check when it has one, a check of seconds such as the kit's
`python3 scripts/package_codex_plugin.py --check` (`python` on native Windows) (the package build itself runs once after
the merge, rule 9); for high, the full gate run by hand and a careful diff read. The lead session changes
its model only at a task boundary, never mid-task, because a model switch rebuilds the prompt
cache at full price; an effort switch keeps the cache on Claude, and still waits for the
boundary so that a round's record names one configuration.

Rules for whoever routes work, binding with any table:

1. **Model and effort are chosen with equal care.** The lead picks the model from the tier
   table and effort from the work table above; the values live in those two tables only.
   It writes both into the brief, and before the start tells the owner in one plain line which
   model and effort and why ("Sonnet, medium: web research and notes, tier 1"); a skill
   whose template names no model is no exception. The line is the owner's decision (v0.11)
   and keeps the spend visible: a multi-agent run uses about 15 times the tokens of a chat
   (Anthropic, "How we built our multi-agent research system"). Neither is left to a default
   or to inheritance.
   Both start at the cheapest table row that fits: mechanical work, docs, small fixes and
   re-reviews go to tier 1 at medium; the strongest model at high is for a new mechanism's or
   a gate change's first round only. Every brief names the model, the effort and the table
   row, because an unnamed choice drifts to the lead's own ("Worker cost", rule 5). Before a batch of more than one paid run (workers, reviews, `codex
   exec` errands), the lead tells the owner in one line how many, which model and which
   effort, and runs them one after another unless the owner asks for parallel: the
   allowance is a limit as real as memory (in one session, twelve parallel reviews spent
   63% of a five-hour allowance in about 25 minutes).
2. **The top models are the lead's pick, and only where the subscription has them.** A model
   above the strongest routine one (for example Codex Astra or Claude Fable) is never a
   default. The lead picks it for one errand when the errand needs it, without asking the
   owner. The lead first checks that the current subscription includes that model; a basic
   plan does not, and then the strongest routine model takes the errand. While that side's
   allowance is low (a saver mode, below),
   the top model and the highest effort need the owner's yes. Sources: both vendors name a
   routine default and keep the top model for work it fails (platform.claude.com/docs/en/models/overview:
   start with Opus 5.5, Fable 5.1 where Opus at high effort falls short; learn.chatgpt.com/docs/models:
   Sol where the plan has it, and some paid plans lack Astra Extra High). "Without asking" and
   "the owner's yes" are the owner's policy, with no source.
3. **A failed mechanical errand is rerun one tier up**, never retried at the same tier. A
   step up moves the model only: the effort is chosen again from the work table, and the
   stronger model's lower effort comes before its higher one. Carrying an effort along
   (a cheaper model's xhigh to the top model's xhigh) is the costliest step there is.
4. **Model versions are kept current.** A lead that learns of a newer Codex or Claude model
   switches to it: the reviewer pins in `scripts/review.sh` and the machine's Codex
   configuration (`~/.codex/config.toml`). The lead then reports the switch to the kit, so
   that the kit and every project built from it follow. A pin is a fixed snapshot with its
   own retirement date, and an alias such as `opus` moves between versions
   (platform.claude.com/docs/en/about-claude/models/model-ids-and-versions;
   code.claude.com/docs/en/model-config, "Version history"); Codex models retire from
   ChatGPT sign-in too (learn.chatgpt.com/docs/models).
5. **The tier boundaries are measured, not guessed.** After about ten errands in a tier, the
   lead counts review rejects and rework per tier and moves the boundaries where they show.
   `python3 scripts/usage_summary.py` (`python` on native Windows) gives the review side: rounds, verdicts, rejects and
   the author-claimed acceptance rate (`accepted=`) per task and per model, effort and
   backend. The rate informs; nothing switches a reviewer off by itself. For reviewer
   acceptance, use the decided-finding sample and distinct-rated-round floors in
   `docs/USAGE.md`; the owner reads the archives before changing routing (KARARLAR B03
   inv2/(d)). Worker errands write no record; the lead counts their rework separately.
6. **A low allowance shrinks what that side does, never the review.** When the owner says
   one side's allowance is low, the saver mode is in force (below), naming that side. It
   lasts until the allowance resets or the owner says otherwise; then the mode before it is
   back at once, unasked (`AGENTS.md`, "Duties toward {{OWNER_NAME}}").
7. **Critical work is written by Opus until {{OWNER_NAME}} says otherwise** (owner decision,
   2026-10-15): architecture, a gate's or the review tooling's design, a security boundary.
   The brief marks it `Risk: <tier> (critical)`; the mark keeps the tier
   (`docs/REVIEW_GATE.md`, "Risk tiers").
   It never goes to the plugged family, in saver too. In solo, the subscription's stronger
   Claude tier (Fable today, rule 2's check) reviews it; on a plan without Fable, Opus reviews
   it in a fresh session, at high effort, one round, and {{OWNER_NAME}}'s diff read before the
   merge is the second check (owner decision, 2026-10-16). In cross, Codex reviews it, and the
   strongest Claude tier takes the other focus ("cross", direction rule). When Codex cannot
   review it (its content classifier stopped the review, `content_flagged`), the strongest
   Claude tier the plan has reviews it in a fresh session, at high effort, one round; on a plan
   without Fable that is Opus, the author's tier, in a fresh session (owner decisions,
   2026-10-15). No source
   measured routing by criticality (`docs/research/claude-lead-codex.md`, finding 9): the
   rule is the owner's judgement and is measured like the tiers (rule 5).

### A second Claude-compatible backend

A third model can take work beside Codex: the Claude CLI pointed at another provider's
Anthropic-compatible endpoint (GLM today), with no third bridge. The owner writes the
endpoint, its token and its model ids into `NAME.env` in the backend folder, outside the
repository (`docs/DEV_SETUP.md`, section 3). `scripts/review.sh --backend NAME` runs the Claude reviewer
there as reviewer `claude@NAME` (`docs/REVIEW_RUNNING.md`). `scripts/spawn_worker.sh
--backend NAME` starts a Claude worker session there. The backend changes neither the tiers
above nor the sandbox. The lead measures it before routing work to it: run a few real reviews
on it, then compare rejects and rework in `usage_summary.py`, which shows the backend column.
A `claude@NAME` review of another model family counts as the second model (`docs/REVIEW_GATE.md`,
"Invariant").

### Working modes, by name

The owner switches the working mode by its name: `solo`, `cross` or `saver`. The lead never
switches it on its own initiative; the one standing exception is saver's return, which the
owner granted when choosing saver ("saver", Ends). The "Working mode:"
line of `docs/STATE.md` and the small `.myagentkit/mode` file (ignored by Git, never committed)
name the mode in force.
`/myagentkit:mode` uses `scripts/working_mode.py` to show or set both records, preserving
the rest of STATE.md. Reads refuse disagreeing records; an explicit owner choice repairs
them. A project without either record works in **solo**, the main mode. Beside the mode,
`autopilot` and `present` switch the owner's presence ("autopilot, the owner-away switch").

A mode decides who writes, who reviews and who fixes the findings. It never removes a
review and never lowers a risk tier (`docs/REVIEW_GATE.md`, "Risk tiers"): the longer agents
work unattended, the more an independent check matters (code.claude.com/docs/en/best-practices).
Rules 1 to 7
above hold in every mode, and the worker caps never exceed the worktree ceiling ("Parallel
work — worktree policy"). The note after the mode name in `docs/STATE.md` names what the
mode needs: `**Working mode:** solo (family: codex)` (no note means `family: claude`) or
`**Working mode:** saver (low: claude, after: cross)`; cross takes none. A switch to saver
adds the `after:` part itself: the mode it interrupts, with a solo family (`after: solo,
family: codex`). A switch sets the note from its
second argument (`working_mode.py saver "low: claude"`, `working_mode.py solo "family:
codex"`) or keeps one of the right shape; a stale note never survives a switch. Every
Claude worker (a sub-agent, a spawned session, a tab) draws on the same plan limits; a
model-specific cap, where the plan has one, applies on top (code.claude.com/docs/en/sub-agents:
a sub-agent's requests count toward the same usage limits as the main conversation;
code.claude.com/docs/en/errors: the session and weekly limits are shared by every model, and
Opus and Sonnet have their own). The lead is the session that plans with the owner, whichever
side it runs on.

| Mode | Writes | Reviews | Fixes the findings |
|---|---|---|---|
| `solo` | one model family's workers, by tier | a fresh session of a stronger tier of the same family; the top tier's own work, that tier in a fresh session | the author's side ("Worker cost", rule 2) |
| `cross` | both families, each task by fit | the other family by the direction rule, in a fresh session | the author's side ("Worker cost", rule 2) |
| `saver` | the side that is not low | the low side, within a small budget, at low and medium tier; a high or critical change as in cross | the side that is not low |

Why: docs/WORKFLOW_RATIONALE.md, "Working modes, by name".

#### solo, the main mode

For a subscription with one model family, which is the kit's default (owner decision,
2026-10-13): one family is enough, and a second vendor is pluggable, never required. The
family is Claude unless the note names another (owner decision, 2026-10-15): `family:
codex` runs the same rules on Codex's tiers. One family reviewing in a fresh session is the
vendor's own pattern: its `/code-review` is a fresh sub-agent of the same family
(code.claude.com/docs/en/code-review), and the one controlled measurement gives no case for
requiring a second vendor (`docs/research/claude-lead-codex.md`, findings 4 and 7: cross
review cost 1.7 to 2.3 times, and its gain depends on the direction).

- **Writes:** the family's workers do all the implementation, at the tier table's column
  for that family.
- **Reviews and fixes:** the author and the reviewer each run in a fresh bridged session with
  no shared context, and the reviewer is at least the author's tier ("Model routing", the
  review row): Sonnet authors and Opus or Fable reviews it, Opus authors and Fable reviews it,
  and Fable, the top tier, authors and Fable reviews it in a fresh session; the review's
  effort follows `docs/REVIEW_GATE.md`, "Invariant". A second session of the author's own tier below the top
  is never the review, with one exception: on a plan with no tier above the author's (Opus
  without Fable), a high-tier or critical change gets Opus in a fresh session, at high effort,
  one round, plus {{OWNER_NAME}}'s diff read (owner decision, 2026-10-16; the same-model review
  alone added 0 points at 1.7 times the cost, `docs/research/claude-lead-codex.md`, finding 4,
  so the diff read carries the weight). Findings go to the author's side ("Worker cost", rule 2), and the
  next round reviews the fix. Two tiers decorrelate less than two vendors (Goel et al.,
  ICML 2025, arxiv.org/abs/2502.04313: model errors overlap more as capability grows; one
  measured Claude-to-Claude review added 0 points at 1.7 times the cost,
  `docs/research/claude-lead-codex.md`, finding 4); fresh sessions with no shared context
  are what keeps the review independent, since a fresh context is not biased toward code it
  just wrote (code.claude.com/docs/en/best-practices).
- **The reviewer:** `scripts/review.sh --reviewer claude` (or `DEFAULT_REVIEWER="claude"`)
  with `REVIEW_CLAUDE_MODEL` set for that run to a tier at least the author's (the review row
  above). It
  is the existing per-reviewer Claude pin, so the review records stay in one format, and
  `--model` applies only to the session it starts (code.claude.com/docs/en/model-config).
  `CODEX_MODEL` stays empty: `--fallback` then has no other reviewer to hand the review to.
  With `family: codex`, the same holds with `--reviewer codex` and `REVIEW_CODEX_MODEL`.
- **Workers:** up to the worktree ceiling; no second vendor runs.
- **Effort:** the tier and effort tables as written.
- **Ends:** when the owner names another mode, for example once a second vendor is added.
- **Lessons:** none yet.

#### cross

A second family is plugged in beside the Claude lead (Codex today, through `codex exec`;
a `claude@NAME` backend counts as a family too). Both families write, each reviews the
other, and the lead routes every task by the rules below (owner decisions, 2026-10-15;
evidence: `docs/research/claude-lead-codex.md`, recommendations 1 to 11).

- **Writes, Codex:** a task with written acceptance criteria, checkable by tests, inside one
  module: mechanical work on `gpt-6-luna` at medium; bounded implementation and bug fixes
  on `gpt-6.1-sol` at medium; multi-file work, or work whose tests are easy to miss, on
  `gpt-6.1-sol` at high; `gpt-6-astra` only as the lead's one-errand pick (rule 2). xhigh is
  the effort table's last row: the lead's reasoned exception, written in the brief, never a
  default and never a review; max and ultra are not used (`spawn_codex.sh` refuses them).
  Codex's own guide asks most tasks for neither Max nor Ultra (learn.chatgpt.com/docs/models),
  and xhigh measured 2.4 to 4.5 times the cost of high with no significant gain
  (`docs/research/token-optimization.md`, 1.10). A Codex worker opens at most two sub-agents
  of its own (`spawn_codex.sh` sets `agents.max_concurrent_threads_per_session=2`; Codex has
  the cap setting and says sub-agents spend more tokens,
  learn.chatgpt.com/docs/agent-configuration/subagents; the number two is the kit's choice
  until measured).
- **Writes, Claude:** everything else: a task whose acceptance criteria are not written
  yet, a design decision, instruction-sensitive work, and critical work (rule 7).
- **Owns:** every brief names the paths its worker may change (`docs/HANDOFF.md`, "The
  brief"), the two sides never share a file, and `scripts/review.sh` refuses a review whose
  diff leaves them. Each author works in its own short-lived worktree; one side lands, the
  other rebases.
- **Direction rule:** the family that did not write a change reviews it, at every tier
  (owner decision, 2026-10-15). Claude reviews what Codex wrote. Codex reviews what Claude
  wrote, a low-tier change's light pass included, one pass, report only, at medium effort, and
  the lead checks each Codex finding before it enters a fix round. When Codex's allowance is
  exhausted, a Claude tier at least the author's takes the review (`docs/REVIEW_GATE.md`,
  "Invariant"), and the lead records the
  switch in the task's STATE line and reports it. A high-tier change has two focus reviewers
  under one label (`docs/REVIEW_GATE.md`, "Risk tiers"): for critical work Claude wrote, the
  strongest Claude tier takes one focus and Codex the other. Findings go to the author's side
  ("Worker cost", rule 2), and each focus gets the label's two rounds
  (`docs/REVIEW_GATE.md`, "Rounds").
- **Quota:** before the switch to cross and before a large Codex errand, the lead reads
  Codex's allowance (`python3 scripts/codex_quota.py`, `python` on native Windows). A Codex worker stopped by its quota
  leaves its session id in the task's STATE line, and `spawn_codex.sh ... --resume`
  continues it once the allowance resets.
- **Measured before it is fixed:** the split above is provisional. For the first ten Codex
  errands the lead records the task type, model, effort, review verdict, fix rounds and
  quota draw in this mode's Lessons; on three to five real tasks it runs the same task on
  both sides and compares (rule 5). What the numbers do not support is deleted.
- **Workers:** up to the worktree ceiling, both sides together.
- **Effort:** the tier and effort tables, with the Codex rows above.
- **Ends:** when the owner names another mode.
- **Lessons:** a lead that sends every errand to its own side spends its allowance on
  volume: one Opus lead routed no implementation to Codex and spent five Opus sessions on
  review rounds.

#### saver

One side's allowance is low. The STATE note names it: `(low: claude)` or `(low: codex)` in
cross, a tier such as `(low: opus)` in solo. A session or weekly limit is shared by every
Claude model, so `low: opus` or `low: sonnet` applies only when the CLI reports that model's
own limit. When the shared limit is low, the whole family is low: stop at a clean point, and
Claude Code's automatic continue resumes an interactive session after the reset
(code.claude.com/docs/en/errors; code.claude.com/docs/en/interactive-mode, "Wait for a usage
limit to reset"), or switch to cross with the owner's yes. saver saves at low and medium tier
only: critical work never goes to the plugged family (rule 7), a high-tier or critical change
gets the reviews cross gives it, and the strongest Claude tier reviews a high-tier or
critical Claude change.

- **Writes:** the side that is not low implements every errand and fixes every finding, the
  low side's findings included.
- **Reviews:** the low side reviews within a small budget, at the lowest effort that fits:
  a re-review of a small fix round at medium; high for a gate, hook or review-tooling
  change, a risky diff and a new mechanism's first round. The top model or the highest
  effort needs the owner's yes. A running review is not cancelled to lower its effort, since
  what it spent is gone. A review that fails on quota leaves its rerun command in the task's
  issue or STATE line and waits; it goes to the other side only with the owner's yes,
  because the independent judgement is the point of it. When the low side is Codex, its
  review follows cross's direction rule (one pass, report only, at medium effort, the lead
  checks each finding before a fix round; `docs/research/claude-lead-codex.md`,
  recommendation 2). Sources: a top model may draw on usage credits
  (code.claude.com/docs/en/model-config); cross review costs 1.7 to 2.3 times, and a quota
  stop needs its rerun command (`docs/research/claude-lead-codex.md`, findings 4 and 7).
  "Not cancelled" has no source.
- **Workers:** none on the low side, and no implementing sub-agent there; the other side's
  workers up to the worktree ceiling. In solo, the low side is a tier: the cheaper tier
  writes and the scarce one reviews. Set the sub-agents' model explicitly there (`model:` in
  the definition, or `CLAUDE_CODE_SUBAGENT_MODEL`): an unset sub-agent runs on the lead's
  model, which may be the low tier (code.claude.com/docs/en/sub-agents, "Choose a model").
- **Effort:** the writing side by the tier table; the low side by the rule above.
- **Ends:** the low side's allowance resets, or the owner says otherwise. Then the mode
  before it is back at once, unasked: the lead runs `scripts/working_mode.py <mode>` for
  the mode the note's `after:` names, which a hand-off keeps; a switch to solo brings the
  recorded family back. The `after:` return is the owner's standing permission, given when
  choosing saver, and holds in a later session too; Claude Code resumes after a limit reset
  the same way, unasked (code.claude.com/docs/en/interactive-mode).
- **Lessons:** every Claude worker counts against the low side: a sub-agent spends the same
  allowance as a spawned session.

#### How a mode improves

Each mode's **Lessons** list is how a mode gets cheaper with use. When a mode cost more
than it should have (a wasted round, a worker on the wrong side, an allowance that ran out
early), the lead adds one line to that mode's list: the failure, with a number when there is
one, and the rule that prevents it. The lead then offers it to the kit with
`/myagentkit:kit-feedback`, so every project's copy of the mode learns it. A lesson that the
mode's own rules come to state leaves the list, and a lesson a later one supersedes is
deleted: the list holds only what is not yet a rule. Written lessons kept for later attempts
measurably help (Shinn et al., Reflexion, arxiv.org/abs/2303.11366), while a context file that
grows hurts (Gloaguen et al., arxiv.org/abs/2602.11988; code.claude.com/docs/en/best-practices:
cut any line whose removal would not cause a mistake), so a lesson that became a rule leaves.

### autopilot, the owner-away switch

Not a mode: a presence switch beside the mode in force, which keeps deciding who writes and
reviews. `**Owner:** away (autopilot since <time>)` or `**Owner:** present` in
`docs/STATE.md`, under the "Working mode:" line, and `.myagentkit/presence` (ignored by Git,
read by the hooks) record it; `scripts/working_mode.py autopilot` and `present` write both
under the mode switch's rules, and nothing else changes the line. No record is present.

- **Starts:** `/myagentkit:mode autopilot`, or {{OWNER_NAME}} saying so in plain words
  ("autopilot'a al", "gece moduna alalım", "I'm off, keep going"): the lead runs
  `python3 scripts/working_mode.py autopilot` (`python` on native Windows) itself and shows what it prints, this subsection
  and the `/goal` line. A second run keeps the first stamp.
- **Before {{OWNER_NAME}} leaves** (the lead checks each and says what is missing):
  1. `docs/STATE.md` lists the work for the absence, each item with its done criterion, and
     what comes next when the list is done; nothing outside the list starts.
  2. This lead session stays open, interactive and in the foreground, never `--bg` or `-p`:
     only there does a usage-limit stop wait and resume (`autoContinueAtUsageLimit`, on by
     default).
  3. Auto mode, or allow rules for the actions the list needs, written now: a permission
     prompt nobody answers waits until morning.
  4. The machine stays awake: plugged in, lid open, sleep off (Windows: PowerToys Awake or
     `powercfg /change standby-timeout-ac 0`; macOS: `caffeinate -i`).
  5. Every running worker's disk watch is armed (rule 4).
  6. {{OWNER_NAME}} types the printed `/goal` line; the lead cannot run a slash command.
- **Stops** only when: the list is done and the report written; the end time {{OWNER_NAME}}
  gave has come (the lead reads `date` at each checkpoint); a usage limit resets more than
  24 hours away; every remaining item needs {{OWNER_NAME}} (the list below); an error the
  lead cannot fix. A usage-limit note, the context band, a compaction (the second too), a
  worker's hand-off, a parked question, one stuck item (three tries, then a WIP commit and the
  next item) is no stop. No turn ends with nothing to wake it: every wait is a disk watch or
  a `ScheduleWakeup`. No AskUserQuestion: a question goes to the report.
- **Decides:**

  | What | When | The lead |
  |---|---|---|
  | Alone | the rules settle it; reversible inside the tree or branch; equal options; order; routing | decides, records it (decision, options, reason, undo), goes on |
  | Proxy, then act | critical or radical but reversible: a lasting design choice, reading the scope, a reading close to an owner rule | consults (below), does the work so the owner's answer changes one named spot, records "the proxy's call, not the owner's approval" |
  | Park | a scope change; a decision the owner kept; the proxy unsure or against the evidence | queues it with a recommendation, takes other work |
  | Never | the list below | does not do it, queues it, skips what depends on it |

  **Never without {{OWNER_NAME}}:** a force push or history rewrite; deleting files that
  existed before the session (`git reset --hard`, `clean`, `stash drop`); an issue, comment
  or message (written as an Issue draft in the report, title and body ready); usage credits
  or spend beyond the plan; changing the owner's rules (`BEHAVIOUR.md`, the owner's
  decisions here, memory); moving an owner item to a later version; ending running work
  without a valid reason; credentials, permissions or a security boundary; skipping a review
  or lowering a risk tier. **Allowed:** local merges into the main branch; push and tag once
  every check and CI are green.
- **Proxy consult:** a sub-agent with model and effort stated: Fable 5.1 first; when it is
  unavailable or asks to bill usage credits, never approve them: Opus 5.5 at high. First the
  question, why now, the binding rules and the owner's words verbatim, the evidence and the
  options in neutral order; the lead's own view only after the answer, for the proxy to
  refute.
- **Checkpoints:** each finished item is committed; STATE and the hand-off file are current
  after each; at red (300k) the hand-off file is written and the session goes on (rule 8).
  Reviews run by tier; only Critical and High block.
- **The report:** `.myagentkit/autopilot/<date of the stamp>.md` (ignored by Git), from
  `docs/AUTOPILOT.md`; `python3 scripts/autopilot_report.py` prints its Done section from git.
- **Ends:** only by `working_mode.py present` (`/myagentkit:mode present`), or by a message
  from {{OWNER_NAME}} that says or implies being back or wanting autopilot ended; the lead
  judges the message. Any other message (a farewell, the `/goal` line, a late instruction)
  is an instruction: the lead acts on it and stays in autopilot. When it ends, before
  anything else the lead runs
  `python3 scripts/working_mode.py present`, gives the report in two layers
  (`docs/COMMUNICATION.md`, "Handoff"), then asks its Questions one by one with
  AskUserQuestion, the recommended option first; an Issue draft is posted only on
  {{OWNER_NAME}}'s yes. The Claude Code overlay's `context_size.py` repeats this rule at each
  prompt while away.

Why: docs/WORKFLOW_RATIONALE.md, "autopilot, the owner-away switch".

## Worker cost — waits and long lives are what you pay for

### The rules in brief

The lead reads this block before it briefs, spawns, merges or closes a worker and after a
compaction; the full rule below, with its sources, when one is in doubt (the measurements:
`docs/WORKFLOW_RATIONALE.md`).

1. A worker's cache outlives its waits (one-hour cache); long jobs, `git commit` and `git merge` included, run in the background; nobody polls.
2. A gate finding goes back to the author's side while its context is under the band and the
   fix is no redesign; otherwise a fresh worker takes it.
3. One small task per worker, sized to end under the context band; a sub-agent's brief to the
   about 120k it has before its first compaction (rule 3).
4. The lead does not poll either; it waits for notifications. After every spawn it starts the
   printed `sh scripts/watch_workers.sh` line as ONE background command: the disk is the done
   signal, and an idle notice is optional, never relied on alone.
5. Mechanical work: the cheaper model at medium effort; design-bearing code: the strongest at
   high. Model and effort are always passed, never inherited.
6. Parallel workers only for independent modules, heavy jobs within the memory budget, paid
   reviews one after the other unless {{OWNER_NAME}} allows parallel, never fewer reviewers than the tier's.
7. Worker reports are short (about 350 words); long output goes to a file.
8. The context band: plan the cut at 200k, cut at the next clean stop at 300k, stop at 400k.
9. A worker runs the cheapest check that proves its change; the expensive step runs once.

Work over about an hour runs in its own session, a short errand as a sub-agent; a stopped
worker is answered in its own session, a cut-off one resumed in place; the lead commits a
Codex worker's work. Reviews: two rounds at most, inner rounds too; round 2 confirms every
finding the dispositions claim fixed, a Medium included, and reports new Critical or High
only; one final review per release (`docs/REVIEW_GATE.md`, "Rounds").

### The measurements and the full rules

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
6. **Parallel workers only for independent modules**; each one multiplies the bill. The lead
   runs heavy background jobs (a gate, a review, a build, a `codex exec`
   errand) within a memory budget: two at a time until the lead has measured its host, then
   (free memory minus a 4 GB reserve) divided by the measured peak of one job; heavy jobs
   already running take slots. Paid reviews run one after the other (rule 1); the two
   reviewers of a high-tier round run together only when {{OWNER_NAME}} allows it for that
   round and two slots are free. The acceptance gate run starts beside a review when the budget
   has a slot for it, otherwise when the review ends. Never reduce a tier's reviews: a high-tier
   round's floor is its two reviewers, a low or medium round's its one (`docs/REVIEW_GATE.md`,
   "Risk tiers"). When not even one job fits, the lead first frees memory it owns (waits for or
   closes its own finished jobs, never ending running work without a reason); if one still does
   not fit, the review round stays blocked and the lead reports the capacity figure to the
   owner; nothing heavy starts. Read free
   memory with `Get-CimInstance Win32_OperatingSystem | Select FreePhysicalMemory` in
   PowerShell on Windows, `free -g` on Linux, `vm_stat` or `memory_pressure` on macOS. Measure
   a job's peak on your host; one measured example: a review or gate took 1–2 GB on native
   Windows 11 with Git Bash (2026-10-12). The 4 GB reserve and two at a time are starting
   values, tuned by the first measurement; the formula is the one large builds use (LLVM's
   `LLVM_PARALLEL_*_JOBS` and RAM-per-job settings, llvm.org/docs/CMake.html). On Linux and
   WSL, `CLAUDE_CODE_TOOL_MEMORY_LIMIT` caps the whole session's commands as a second line of
   defence (code.claude.com/docs/en/tools-reference). The lead lowers the number after a low-memory reap,
   because five jobs started together were killed at once
   (`docs/GOTCHAS.md`, "Background jobs die with the session and in a low-memory reap"). Workers
   whose last step waits on one exclusive resource (a heavy lock, a device, a licence) run
   one after another, or run only their independent parts in parallel: in one project,
   "parallel" workers queued at one machine-wide lock.
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
   decides at that stop, never mid-flow. With the owner away (`**Owner:** away` in STATE,
   the switch of "autopilot, the owner-away switch"; without that record,
   `docs/COMMUNICATION.md`'s 45 minutes), the lead writes the hand-off file, runs `/compact`
   when jobs are in flight, and continues, after a second compaction too; it does not wait
   for an answer.
   A worker session uses the same absolute band: `scripts/watch_workers.sh --context-warn`
   warns at the smaller of 200k and 50% of the window (`NNNk` or `NN%` changes it).
   A sub-agent compacts near 168k, before the red band (rule 3), and its compactions never end
   its task.
   A worktree worker carries the project's hooks, and at red the lead sends
   "finish the item, commit, Kind: handoff", the worker's one hand-off besides its own (`docs/HANDOFF.md`) (owner decision 23, 2026-10-16; Claude Code project settings:
   https://code.claude.com/docs/en/settings, checked 2026-10-16).
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
would pay a session start for nothing. A short errand that needs the lead's own context
runs as a forked sub-agent, which inherits that context instead of re-reading it, while the
lead is under about 120k tokens; above that, a fresh sub-agent with a brief is cheaper. The
lead merges and, as the integrating session, runs the integration build. The 120k fork
threshold is the owner's choice, not a measured crossover
(KARARLAR B03 inv1#186); compare total lead-plus-worker usage before changing them
(code.claude.com/docs/en/sub-agents).

The threshold is {{OWNER_NAME}}'s decision from use. The only cost comparison of the two
shapes is one task on 2026-10-03 (the kit's `docs/worker-cost-setups.md`): about 107 against
110 requests, a cost equivalent of about 2.44M against 2.40M tokens. It measured the cost
per worker on one task with one long wait, not wall-clock time, the throughput of several
tasks, or the lead's own cost. Measure in passing: wall-clock from brief to merge (into "Task sizing"'s rows), total
tokens including the lead's, review rounds, and waits on an exclusive resource. The sample
will be thin.

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
**The disk is the done signal, on every platform.** Right after every spawn the lead starts
ONE background command: the `sh scripts/watch_workers.sh --result NAME=PATH NAME` line the
spawn prints. It exits when the worker reports (its result file, GONE or WAITING), and the
lead starts it again after every report but DONE and GONE. The printed line starts with a `cd`
to the checkout that holds the worker's records (`.myagentkit/workers`), so it works pasted in
any folder; run elsewhere with no record and no session it can see, the watcher exits 2 naming
the checkout to run from, unless `--result` names a ready result, which it then reports. On
native Windows it reads the
worker's state file, result file and exit record in place of a pane (below). The lead may
also subscribe with SendMessage `notify_when_idle` when the spawn prints "is a peer session"
(a tmux worker always registers), but never relies on it alone: a supervised close often
sends no notice. The subscription costs no tokens. It lapses after 12 hours without a
notice (the lead is told). A worker with `crossSessionInbound` set to `refuse` sends no notice.
The worker also messages the lead's session itself right after it publishes (the spawn prints
`lead session: NAME`; 4 of 4 arrived in the 2026-10-22 spike), but a cross-session message is
best-effort too, so the watch stays.
The docs define idle as "finished a turn with nothing queued"
(code.claude.com/docs/en/cross-session-messaging). In the lead's 2026-10-17 observation, one
subscription on a `spawn_worker` worker that published its result and was then closed
delivered no idle notice. On 2026-10-20, 4 of 5 subscriptions on native Windows workers that
`codex_worker.py` closed about 10 seconds after their `Kind: completed` result delivered no
notice, and the lead sat idle with all work done until {{OWNER_NAME}} asked. These
observations do not establish how many notices a subscription gives.
The lead does not message an idle session: every message to an
idle session is a full-context turn. A worker session does not end with its task.
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
  {{OWNER_NAME}}, or is resumed once its tab has closed: `scripts/spawn_worker.sh NAME
  ANSWER_FILE --model M --effort LEVEL [--worktree] --resume SESSION_ID` (spawn prints the line
  with the id when Claude Code registered the session), which keeps `-n NAME`.
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

Why: docs/WORKFLOW_RATIONALE.md, "The measurements and the full rules".

## Review rounds — early, inside the worker, in parallel

**Prevention over detection.** Quality goes in before the code is written: every task
starts with a design of five to ten lines, in the brief or at the top of the worker's result
(what changes, where, the one test that proves it, what is left out); the worker makes the
smallest change that works, reuses what the project already has, and reads its own diff as a
reviewer would before it reports ("Before you report"). The review loop is unchanged and
reviews are never reduced (`docs/REVIEW_GATE.md`, "Risk tiers"); prevention
is what lets its first round find nothing. A project or a kit that spends its budget
reviewing itself fails at its purpose, which is the product.

"In parallel" means the review inside the worker and the acceptance gate run beside a review; the gate's
reviewers run one after the other unless {{OWNER_NAME}} allows parallel ("Worker cost", rule 6).

Why: docs/WORKFLOW_RATIONALE.md, "Review rounds — early, inside the worker, in parallel".

### Design before code

- A new mechanism gets a one-page design before any code. A new mechanism is anything that
  deletes or moves files, rewrites history, or changes a gate.
- The design names what the mechanism protects, what it excludes by decision, its rules, and
  the cases in which it still loses data or fails: the threat model every review loop needs
  before its first round, with the stopping rule (`docs/REVIEW_GATE.md`, "Rounds"). The design
  page writes the stopping rule as a line: the loop ends at the first round with no High
  inside this model.
- The design is reviewed under its own review label (`docs/REVIEW_RUNNING.md`, "Rounds,
  labels and designs"). Code starts after that review.
- The design's exclusions are the dispositions for later code rounds. A finding inside an
  exclusion is answered with the exclusion, not with a fix.
- The kit repository's `docs/worker-lifecycle-options.md` shows the shape: the facts, the
  options with their costs, and what a second model should attack.

Why: docs/WORKFLOW_RATIONALE.md, "Design before code".

### Review inside the worker

- A worker reviews its own diff with fresh sub-agents before it reports, whether it runs as
  a session or as a sub-agent (Claude Code nests sub-agents three layers deep by default,
  code.claude.com/docs/en/sub-agents, "Let subagents spawn their own subagents"). It starts
  a fresh diff reviewer as a sub-agent (the Claude Code overlay's
  `diff-reviewer`), fixes what the review finds, and starts a new fresh reviewer on the
  result only when round 1 left a Critical or High fix to verify (the cap below). This inner pass is the author's side's early check; the gate's review in a fresh
  session follows `docs/REVIEW_GATE.md` and `docs/REVIEW_RUNNING.md`, and its findings go
  to the author's side ("Worker cost", rule 2).
- Each inner round's prompt carries the earlier inner rounds' findings and the worker's
  dispositions (`docs/REVIEW_GATE.md`, "Findings and dispositions").
- The reviewer is a new sub-agent in every inner round, because the author never reviews its
  own change.
- Inner rounds keep the gate's cap (`docs/REVIEW_GATE.md`, "Rounds"): at most two; round 2 runs
  only when round 1 left a Critical or High fix, confirms every finding the dispositions claim
  fixed, a Medium included, and reports new Critical or High only. A Medium is fixed when a test
  verifies it, else named in the report; a Low goes to the report; what remains after round 2
  goes to the lead. A fresh reviewer nearly always finds another Medium, so "until clean"
  never ends (the kit's `docs/research/ai-review-workflows.md`, findings 2 and 8).
- The report lists the inner rounds: their count, the findings fixed and each disposition.
- Where `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` is 1, the worker cannot start a sub-agent and
  says so in its report. The lead then starts the review the moment the worker's branch
  exists. The launch sequence follows "Worker cost", rule 6.

A fix in the worker's warm context, in an inner round, costs minutes while the cache is warm.
The same finding left
for the gate's review goes to a fresh worker, which pays the whole re-read. The brief states which of the two cases it expects (`docs/HANDOFF.md`,
"The brief").

Why: docs/WORKFLOW_RATIONALE.md, "Review inside the worker".

### Before you report

A worker goes through `docs/REVIEW_GATE.md`, "What a reviewer attacks first", against its own
diff before it reports. It fixes each hit or names it in the report. The same list goes into
the inner reviewer's prompt ("Review inside the worker"). A class the reviewer has
already shown once costs a whole round when the worker leaves it for the reviewer to find again.

### The lead's steps when a branch is ready

The lead never changes its shell directory into a worker's worktree; use `git -C <worktree>` for its Git commands.
The shell stays in the lead's checkout, so its Stop hook runs that checkout's gate.

1. Merge the ready branches into the integration branch in dependency order, each through
   its gate (the commit runs `./scripts/check.sh`). A merge-conflict resolution is a part
   authored by whoever resolved it, so the final review covers it. A member branch rejected
   or abandoned after the merge leaves by rebuilding the integration branch without it.
2. Start the acceptance gate run (`./scripts/check.sh`) and the reviews on the same commit,
   following "Worker cost", rule 6. The gate runs the project's build, so it may share the
   reviews' worktree only when that run writes nothing but files Git ignores (owner decision,
   2026-10-12); otherwise it runs in its own worktree of that commit, or after the reviews
   (`docs/REVIEW_RUNNING.md`, "Rounds, labels and designs").
   The acceptance run is once per batch, never between worker rounds while
   workers wait for it, because each run locks the checkout and every waiting worker pays
   for the wait. CI runs on the same commit.
3. Keep one review label per change for its rounds (a high-tier change's two focus reviewers
   get two rounds each under it), so that each round carries the matching earlier reports
   (`docs/REVIEW_GATE.md`, "Rounds"). A release's merged diff
   then gets ONE final review under a label never used before, as that section states.
4. Fix a Critical or High finding of the final review; a Medium goes to {{OWNER_NAME}} and a
   Low to `docs/BACKLOG.md` (`docs/REVIEW_GATE.md`, "Verdicts and who decides").
5. A release gets one day of real use before the push; the lead records what it ran and
   what it saw in `docs/STATE.md`, and pushes on {{OWNER_NAME}}'s OK.
6. Start the next worker while the gate run after a merge still runs. If that run
   fails, tell the next worker to rebase onto the fix.

Each step that waits on another adds its whole duration to the round. In the review round no
step needs another step's result before it starts, so the acceptance gate run starts beside a review
when memory permits; a step that does need a result waits for it, and paid reviews run one
after the other ("Worker cost", rule 6). A merge-conflict resolution is reviewed because it is
authored code (Fowler, "Semantic Conflict").

What the watcher reports decides the lead's next step for a spawned worker:

- **QUESTIONS:** the lead asks them at once, one at a time, through its question tool, before
  the merge or in the same breath. It records each answer, and the general rule the answer
  sets, in its permanent home, not only in the chat.
- **CONTEXT:** the lead decides from the figure (absolute tokens, rule 8's band) and the
  worker's `Remaining:` line, which is the worker's estimate: the figure decides when they
  disagree. The lead decides whether the worker finishes, compacts or hands off; at red it
  sends "finish the item, commit, Kind: handoff". A session with two short steps left finishes;
  one with a long operation ahead hands off or compacts, because it pays the figure on every
  remaining request.
- **DONE:** the lead reads the result file before anything else.
- **HANDOFF:** the lead reads the result file and starts a fresh session from it. A
  `Kind: handoff` file is not done.
- **BLOCKED** and **PROGRESS:** the lead reads the result file. Neither is done.
- **Finished session:** a completed result, a handoff or a decision ends the session; merging the
  worker's branch closes the rest (the post-merge hook runs `scripts/close_worker.sh
  --finished NAME`). A session finished without a merge (no next task fits what
  it holds, or it is idle past the cache lifetime) the lead closes with that command.
  The worktree then goes through the same audit as the post-merge hook's; a kept worktree
  is reported with its reason, and the branch is never deleted.

## Token economics — the always-loaded prefix is money

Cached input tokens are discounted heavily, so a STABLE prompt prefix — the documents loaded
at the start of every session — is the largest single cost lever available. A running
session keeps the cache it was built with; an edit to one of those files changes the prefix
of every session started after it, so the sessions of one batch read different rules.

- Do NOT edit `AGENTS.md`, `docs/ARCHITECTURE.md` or any other always-loaded doc in the
  middle of a session unless the task IS that document: the reason is consistency between
  the sessions in flight, not the running session's cache.
- Batch documentation edits into their own task and their own session.
- Keep always-loaded docs SMALL and STABLE. Size here is not a readability preference; it is
  a recurring bill.
- Volatile state belongs in `docs/STATE.md`, which is read every session and therefore kept
  small. Reference docs like `docs/GOTCHAS.md` stay off the session-start list entirely
  (code.claude.com/docs/en/memory: what loads at start is paid every session; topic files
  load on demand). A trap stays in GOTCHAS only, with no path-scoped copy in
  `.claude/rules/`: one canonical place.

## Web requests carry no personal data

Some APIs ask clients to put contact details in the `User-Agent`, and an agent that has
{{OWNER_NAME}}'s e-mail address in its session context uses it: in one project five
research agents did, in up to thirteen requests each. A request reaches a third party and
its logs, and cannot be recalled.

- **Never put a person's name, e-mail address or other personal data into a web request**
  (headers, query strings, bodies, scripts an agent writes to fetch pages). When an API asks
  for contact details, use the "Web contact" line in `docs/PROJECT.md` (a role address or
  project URL {{OWNER_NAME}} chose, never a person's own); if it is empty, ask
  {{OWNER_NAME}} once and record the answer there. Otherwise send a generic project
  User-Agent. In the Claude Code overlay, `guard_private_email.py` refuses a request that
  carries the owner's address.
- **A brief for a task with web access repeats the rule** and names that contact
  (`docs/HANDOFF.md`): a sub-agent does not read this file unless told to. A hook decides
  every time, an instruction is only advice (code.claude.com/docs/en/hooks-guide), which is
  why the overlay adds the hook beside the brief.

## MCP hygiene

- Enable a server only for the work that needs it, and turn it off afterwards anyway: a
  server is a trust boundary, and changing servers mid-session breaks the prompt cache.
  Overlay setup files point here instead of repeating this rule.
- Prefer plain CLI tools over adding a server.
- **A new MCP server, connector, or plugin that bundles one needs {{OWNER_NAME}}'s approval,
  exactly like a new dependency;** the reason is the trust boundary (a server runs code and
  feeds the model text), not only cost (code.claude.com/docs/en/security, "MCP security").
  Workers do not run with `--strict-mcp-config`, because Unity work needs the project's
  server; the reviewer already runs with MCP off. That choice is the owner's.

Why: docs/WORKFLOW_RATIONALE.md, "MCP hygiene".

## Evaluated and rejected — do not re-litigate

Decisions turned down, written here so no session spends budget deciding them again. Each
one names what would have to change before it is worth reopening.

{{REJECTED_DECISIONS}}

## Documentation maintenance contract

- PROJECT.md writing rules: `docs/PROJECT.md`, "How this file is written". {{OWNER_NAME}}
  approves every DECIDED item. Capturing a question costs nothing and losing one is
  expensive: the cost of a missed capture is a forgotten question; the cost of a wrong
  promotion is every future session treating a musing as law.
- Update `docs/ARCHITECTURE.md` in the same task only when the task adds or removes a module
  or moves a boundary (the map is coarse on purpose, matklad's "ARCHITECTURE.md"). Prefer a
  check to a promise: `scripts/check.sh` fails when a folder under `module_roots` is missing
  from the module map. The agent finds code with grep and glob; the map orients, it does not
  replace search. If agents keep failing to orient, ask first whether the file is too long
  or stale.
- These files hold what the code cannot tell you: why a decision was made, what was tried
  and dropped, what is still open. Code can be re-read; this cannot. Keep only that kind of
  content here (code.claude.com/docs/en/best-practices; Gloaguen et al.,
  arxiv.org/abs/2602.11988; Böckeler on spec-driven development, martinfowler.com).
- A process rule or decision should name its source: a vendor document, a research report, or
  a lesson this project paid for (a `[LESSON]` line, a `docs/GOTCHAS.md` entry). A rule
  without one is the first a later session deletes (code.claude.com/docs/en/best-practices:
  cut a line whose removal would cause no mistake). The source line lives in the rationale
  page, not in `AGENTS.md`: `docs/WORKFLOW_RATIONALE.md`, "Where the constitution's rules come from", holds them.
  When nothing covers the point, research it first; when the research settles nothing,
  {{OWNER_NAME}} decides. The kit works this way itself (its `CONTRIBUTING.md` and
  `docs/research/`).
