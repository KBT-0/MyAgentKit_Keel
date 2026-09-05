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
   never approves their own patch.
6. **Document:** if a public API changed, update that module's README in the same task.
7. **Update `docs/STATE.md`:** active work, next steps, deferred items, with a tool+model
   trace. Unwritten progress does not exist.
8. **Summarize:** what, why, which files. If you hit an OPEN design item, flag it as a
   question rather than deciding it.

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
- **Test both directions** where a gate can produce false positives. A gate that always
  fails is as useless as one that never does, and it gets deleted by the first person it
  blocks unfairly.
- **Fail on absent evidence.** No output file, an empty diff, a tool that did not run: all
  FAIL. An exit code is not evidence that work happened.
- **Parse tool output defensively.** Strip ANSI escapes before matching — CLIs colour their
  output and a coloured phrase silently stops matching. If an extracted field comes out
  empty, SAY it was not found; never write it out blank, because a blank field looks like a
  field.

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

- A session working on a branch or in a worktree **does not write `docs/STATE.md`.**
- It writes `docs/worktree-notes/<branch>.md` — its own file, so it cannot conflict. Same
  content rules: full sentences, tool+model trace, an honest "not run".
- `docs/STATE.md` is updated on the main branch at merge time by the integrating session,
  which folds the note in and deletes it.
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
