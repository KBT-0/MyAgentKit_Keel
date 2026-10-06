# Task Handoff Template — Tool-Agnostic (CANONICAL)

When handing work to another tool, model or session, produce ONE self-contained prompt. The
target has NO chat memory: if it is not in the prompt or in `docs/STATE.md`, it does not
exist. A brief is a written artifact (`AGENTS.md`, "Language & style", rule 2): full
sentences, one instruction per sentence, one term per thing. State each requirement once.

## The brief

1. **Task:** one paragraph, exact scope, explicit non-goals ("do not touch X").
2. **Files:** full paths and member names — verified to exist RIGHT NOW with grep or a
   read, never from memory. A path that has moved sends the implementer somewhere else and
   the diff comes back in the wrong place.
3. **Constraints:** restate the relevant `AGENTS.md` rules verbatim — the one-module rule,
   the boundary that applies here, no untested core code, no drive-by refactors. Do not
   write "follow AGENTS.md"; the target will not weigh a pointer the same as a quoted rule.
   A task with web access also quotes the web rule: no personal data in any request, and the
   generic User-Agent to use (`docs/WORKFLOW.md`, "Web requests carry no personal data").
4. **Acceptance:** what the diff must and must NOT contain, and which gate follows (a risky
   area means `docs/REVIEW_GATE.md`, fresh session). Any other change needs no review;
   {{OWNER_NAME}}'s check or the manual check named here accepts it.
   **Review:** the brief says which of two cases it expects. A worker in a separate session
   reviews its own diff with fresh sub-agents before it reports; a sub-agent worker says it
   could not, and the lead starts the review when the branch exists (`docs/WORKFLOW.md`,
   "Review rounds — early, inside the worker, in parallel").
5. **Routing check:** does this task belong on the model it is being sent to? Judgement work
   — architecture, contracts, risky diffs — goes to the strongest model; bulk, mechanical,
   well-specified work goes to the cheaper one. If the requested route violates that, say so
   instead of producing the prompt. The brief names the model AND the effort level, and the
   lead verifies both after the run from the transcript (Claude Code: the `"effort"` field;
   Codex: the `reasoning effort:` header of its log). A delegated agent that was never told
   its effort runs at whatever its parent had (`docs/WORKFLOW.md`, "Worker cost").
6. **Definition of Done — verifiable:** the exact command or observation that proves the
   task is finished, e.g. "`./scripts/check.sh` prints `CHECK: PASS` with the new test
   visible in the run". Not "it works", not "tests added" — something the implementer can
   run and {{OWNER_NAME}} can re-run. If a stated check could not be executed, the
   implementer reports "not run". It is never assumed.
   **Proof:** the cheapest check that proves this change, which the worker runs instead of
   the expensive build; the integrating session builds after the merge. A brief with no
   Proof line means the worker runs `./scripts/check.sh` (`docs/WORKFLOW.md`, "Worker cost").
   The implementer's report has a word cap: 350 words unless the brief sets another. Its two sections
   "Not run / not verified" and "Noticed, not fixed" are always present, outside the cap.
7. **If ambiguous: STOP and ask.** Do not assume, do not invent scope, do not widen the task
   to make an unclear part fit. An unanswered question comes back as a question, not as a
   guess buried in the diff. A spawned session has nobody to ask in its pane: it writes the
   question into its result file, with `Kind: blocked` if the work cannot continue, and
   commits the file. It then goes on with what does not depend on the answer.

End the prompt with: updating `docs/STATE.md` at session end is the implementer's job. When
the task belongs to an operation with its own file, `docs/<OPERATION>.md`, the detail and
the result go straight into THAT file and `docs/STATE.md` gets one status line pointing at
it — no separate note and no fold step. A project that folded every worker's note into
`docs/STATE.md` grew one bullet without end. When the task has an id, the commit that
finishes it carries `Done: <id>` and its line leaves `docs/STATE.md` in that same commit
(`docs/WORKFLOW.md`, "Task ids").

A brief for a separate worker session (`scripts/spawn_worker.sh` in the Claude Code overlay)
also ends with the path of its result FILE and these lines: "Commit the result file and
leave the tree clean; the watcher reads it only then; a question written there reaches the
owner only after that commit. The lead reuses or closes this session after reading the
result file (`scripts/close_worker.sh NAME`); write the file last and stop."
The session does not end by itself when the task is done, and its idle notice also fires
whenever it parks on a background job, so the result file is the only end signal.

The result file starts with four lines, exact keys, in this order:

```
Kind: completed|blocked|handoff|progress
Task: <the task id, or the brief's name>
Attempt: <n>
Remaining: <one line: what is left, or "none">
```

Then the body (the report above). Then, when the worker has questions it could not ask, the
section `## Open questions for {{OWNER_NAME}}`: one numbered question per item, each with its
options on the lines after it. The sections "Not run / not verified" and "Noticed, not
fixed" follow as always.

- Only `Kind: completed` is done. `blocked`, `handoff` and `progress` are not done, and an
  idle notice is a hint, never the done signal.
- A worker that notices a compaction of its context writes `Kind: handoff` at once, with a
  handoff section in the shape of this file, and commits it.
- `Task:` and `Attempt:` name the work the file reports on, so a result left by an earlier
  task of a reused session is never taken for the current one.

The Claude Code overlay's `scripts/watch_workers.sh --result NAME=PATH` reads this head once
the file is committed on a clean tree, and reports the open questions with their text.

A handoff written at the end of a working day also carries the cost: the tool's cost screen
(`/cost` in Claude Code) and the table from `scripts/agent_cost.py --latest`, next to the number
of tasks done, so the next lead routes from a number (`docs/WORKFLOW.md`, "Worker cost").

## Sizing the task before you write the brief

- **Too big** ("build the payments system") — the implementer invents scope and returns one
  monolithic, untestable file. Split it first.
- **Too small** ("write an add function") — the context switch costs more than the work
  saves. Fold it into the neighbouring task.
- **Right size** — ONE named piece, in ONE module, built on contracts that already exist,
  with a Definition of Done someone else can run.

The loop is **specify → generate → validate.** Interfaces, data shapes and constraints are
specified BEFORE generation, and the result is validated by a gate, never by the
implementer's self-report.

## Day-to-day task prompt

The full brief above is for handing work across tools. For an ordinary task inside one
session, the same skeleton compressed:

```
Read: AGENTS.md, docs/PHASES.md, docs/STATE.md, docs/ARCHITECTURE.md, <target folder>/AGENTS.md

TASK:   <one sentence — one module>
SCOPE:  <the files you may touch>
DO NOT: <explicit non-goals — and everything docs/PHASES.md puts out of scope>
PROOF:  <the cheapest check that proves this change; none named means ./scripts/check.sh>
        — never report a check you did not run
DONE:   <the command or observation that proves it>
REVIEW: <inner: you review your diff with fresh sub-agents before reporting | lead: you
        cannot start sub-agents; say so, and the lead reviews your branch>

If this task touches {{RISKY_AREAS}}, or any gate/CI/check script: before commit, run the
review gate per docs/REVIEW_RUNNING.md in a FRESH session, preferably a different tool.
Any other change needs no review unless this brief names the doubt a review is to settle.

When finishing: update docs/STATE.md with a tool+model trace (a follow-up task goes to
docs/BACKLOG.md), then a short summary.
```
