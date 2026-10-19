# Task Handoff Template — Tool-Agnostic (CANONICAL)

When handing work to another tool, model or session, produce ONE self-contained prompt. The
target has NO chat memory: if it is not in the prompt or in `docs/STATE.md`, it does not
exist. A brief is a written artifact (`AGENTS.md`, "Language & style", rule 2): full
sentences, one instruction per sentence, one term per thing. State each requirement once.

## Owner summary

A handoff between sessions opens with a few lines for {{OWNER_NAME}}, in the chat language,
before the technical brief (`docs/COMMUNICATION.md`, "Handoff"): the state in one word (on
track, at risk, blocked); what finished, each marked verified or not verified; what is open
and whose it is (the agent's or the owner's); known risks as "if X, do Y"; the one decision
wanted from the owner. No session labels in this layer. The next session reads the summary
back to the owner in two or three lines before it starts, so a misreading is caught first.
The technical brief below keeps the six things a compaction summary keeps: open problems,
approaches tried and dropped with why, the owner's decisions in their own words, the current
state, open work, and details that are hard to reproduce.

## The brief

Every brief includes `Route: quick|build|deep · Risk: low|medium|high · Checks: ...`
(`docs/WORKFLOW.md`, "Model routing", defines the values; critical work adds a
mark, `Risk: <tier> (critical)`). Name the model and effort from `docs/WORKFLOW.md`, "Model routing", alongside that line.

1. **Task:** one paragraph, exact scope, explicit non-goals ("do not touch X").
2. **Files:** full paths and member names — verified to exist RIGHT NOW with grep or a
   read, never from memory. A path that has moved sends the implementer somewhere else and
   the diff comes back in the wrong place.
   **Owns:** one line, `Owns: src/combat/, tests/test_combat_*.py`: the paths the worker may
   change, a folder ending in `/` or a glob with git's rules (`*` stays in one folder, `**/`
   spans zero or more), comma-separated; code blocks are skipped, a second line is refused;
   `docs/STATE.md` and `docs/BACKLOG.md` are always allowed. With the brief as `REVIEW_TASK_FILE`,
   `scripts/review.sh` refuses a diff that leaves them (`scripts/owns_check.py`). In cross
   mode every brief has it, and the two sides never own the same path.
3. **Constraints:** the rules THIS task can break, quoted verbatim (the one-module rule, the
   boundary that applies here, no untested core code, no drive-by refactors), and only
   those. A Claude Code sub-agent and a separate session already load `AGENTS.md`; do not
   paste it whole, and do not rely on "follow AGENTS.md" for a rule the task is likely to
   break: a rule that must reach the worker is restated in its prompt
   (code.claude.com/docs/en/sub-agents), and a padded prompt buries it
   (code.claude.com/docs/en/best-practices).
   A task with web access also quotes the web rule: no personal data in any request, and the
   "Web contact" line of `docs/PROJECT.md` to use (`docs/WORKFLOW.md`, "Web requests carry no
   personal data").
   A task that writes an incremental-build planner quotes `docs/GOTCHAS.md`, "An incremental
   build misses its always-run inputs".
4. **Acceptance:** what the diff must and must NOT contain, and which gate follows (a risky
   area means `docs/REVIEW_GATE.md`, fresh session). Any other change gets its tier's review
   (`docs/REVIEW_GATE.md`, "Risk tiers"); {{OWNER_NAME}}'s check or the manual check named here
   accepts it.
   **Review:** a worker reviews its own diff with fresh sub-agents before it reports, whether
   it runs as a session or as a sub-agent: Claude Code nests sub-agents three layers deep by
   default (code.claude.com/docs/en/sub-agents, "Let subagents spawn their own subagents";
   checked 2026-10-15 on 2.1.300, where a sub-agent worker was offered the Agent tool). Where
   `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` is 1, it says it could not, and the lead starts the
   review when the branch exists (`docs/WORKFLOW.md`, "Review rounds — early, inside the
   worker, in parallel"). The fresh sub-agent is a reviewer, not the author.
   **Design:** the brief carries a design of five to ten lines, or tells the worker to write
   one at the top of its result before any code (the same section).
5. **Routing check:** does this task belong on the model it is being sent to? Judgement work
   — architecture, contracts, risky diffs — goes to the strongest model; bulk, mechanical,
   well-specified work goes to the cheaper one. If the requested route violates that, say so
   instead of producing the prompt. Choose effort from the "Model routing" table: medium
   for mechanical work and small fix re-reviews; high for a new mechanism's first round,
   gate/hook/review-tooling changes and risky diffs. Only the lead chooses xhigh/max and
   writes the reason in the brief. The brief names the model AND the effort level, and the
   lead verifies both after the run from the transcript (Claude Code: the `"effort"` field;
   Codex: the `reasoning effort:` header of its log). An unnamed choice drifts to the lead's
   own model and effort: Claude Code resolves an omitted sub-agent model to the main
   conversation's (code.claude.com/docs/en/sub-agents; `docs/WORKFLOW.md`, "Worker cost").
   Prefer a named sub-agent definition whose frontmatter fixes `model` and `effort`; the
   guard remains for calls that name a generic agent. `CLAUDE_CODE_EFFORT_LEVEL`, if set,
   overrides the definition's effort, so the lead checks it is unset before relying on the
   field.
6. **Definition of Done — verifiable:** the exact command or observation that proves the
   task is finished, e.g. "`./scripts/check.sh` prints `CHECK: PASS` with the new test
   visible in the run". Not "it works", not "tests added" — something the implementer can
   run and {{OWNER_NAME}} can re-run. If a stated check could not be executed, the
   implementer reports "not run". It is never assumed.
   **Proof:** the cheapest check that proves this change beyond the commit gate. The gate
   (`./scripts/check.sh`, which pre-commit runs on every commit) always runs; the Proof line
   names what the worker runs for its claim on top of it, never instead of it. The expensive
   integration step outside the gate runs once, in the integrating session, after the merge.
   A brief with no Proof line means the gate alone (`docs/WORKFLOW.md`, "Worker cost").
   The implementer's report has a word cap: 350 words unless the brief sets another. Its two sections
   "Not run / not verified" and "Noticed, not fixed" are always present, outside the cap.
7. **If the ambiguity changes the work, STOP and ask.** Readings that would lead to
   materially different work, or an irreversible or outward action, stop the task and come
   back as a question. A routine, reversible choice is made on the most conservative reading
   and written in the report as an assumption (`docs/COMMUNICATION.md`, "Questions and
   approvals": with {{OWNER_NAME}} present, ask; away, nothing waits on a question). Never
   widen the task to make an unclear part fit; an unanswered question comes back as a
   question, not as a guess buried in the diff. Sources: Anthropic, "Prompting Claude Opus 5"
   (check in only when readings lead to materially different work); Edwards and Schuster,
   "Ask or Assume?", arxiv.org/abs/2603.26233 (well-calibrated information-seeking:
   fewer questions on simple tasks, more on complex tasks); resuming the same session with
   the answer keeps its context
   (code.claude.com/docs/en/sub-agents, "Resuming subagents"). A spawned session has nobody
   to ask in its pane: it finishes independent work and stops its running jobs before
   publishing the question. It writes `Kind: blocked` and QUESTIONS into its result file, then publishes the question to the
   known sidecar and exits its separate session. A peer ends its turn and accepts SendMessage.
   The answer comes into that same session, never a fresh one (`docs/WORKFLOW.md`, "Worker cost").

End the prompt with: updating `docs/STATE.md` at session end is the implementer's job. A
worker on a branch or in a worktree writes `docs/worktree-notes/<branch>.md` instead and
leaves `docs/STATE.md`, `docs/BACKLOG.md` and the `Done: <id>` trailer to the lead at the
merge (`docs/WORKFLOW.md`, "Parallel work — where a branch agent writes its notes"). When
the task belongs to an operation with its own file, `docs/<OPERATION>.md`, the detail and
the result go straight into THAT file and `docs/STATE.md` gets one status line pointing at
it — no separate note and no fold step. A project that folded every worker's note into
`docs/STATE.md` grew one bullet without end. When the task has an id, the commit that
finishes it carries `Done: <id>` and its line leaves `docs/STATE.md` in that same commit
(`docs/WORKFLOW.md`, "Task ids"). A handoff carries open work only: the writer deletes every
closed item from it before handing over (`docs/WORKFLOW.md`, "The state, backlog and phase
files").

A brief for a separate worker session (`scripts/spawn_worker.sh` or `scripts/spawn_codex.sh`
in the Claude Code overlay) names its result FILE and its question and session sidecars.
For Codex the brief must use the spawn-time result path: `RESULT-NAME.md` at the worker's
repository top by default, or `--result FILE` (a `.md` file inside the worker's folder).
Its question is `QUESTION-NAME.md`, or `FILE.question.md` for a custom result. The spawning
checkout records `.myagentkit/workers/NAME.session` and the question's path in `NAME.question`,
outside the worker's folder; successful `close_worker.sh NAME` removes those records so the
name can be reused, and refuses while the question waits for its answer. The default result
reports on the work and is never committed: the close moves it to
`.myagentkit/workers/NAME.result.md` once the lead has committed the files it lists. A custom
result is a project file, such as an operation file, that the lead commits with the work.
Pass the custom result again on resume. The brief says to publish the question last, after
independent work and jobs finish. Publish questions and finished results atomically: write a
temporary file beside the destination, end with `<!-- codex-worker: ready -->`, then rename it
into place with `codex_worker.py --publish TEMPORARY_FILE DESTINATION`, as spawn's instruction
names it: Windows refuses a rename over a file a poll holds open, and it retries for a moment.
Publish the blocked result with this same protocol before publishing the question.
End the turn immediately; the wrapper allows ten seconds to flush (overridden by
`KIT_WORKER_GRACE`) before closing the worker's process tree. A question reaches the lead
through its sidecar without a commit, and the recorded session is resumed with the answer.
For Claude the lead uses SendMessage or records the separate session's id for
`scripts/spawn_worker.sh NAME ANSWER_FILE ... --resume SESSION_ID`; the lead never opens a
worker tab by hand, which nothing could close.
For Codex, the brief says to leave all work uncommitted and ready for the lead; the result
lists the exact changed and added files. The lead reads that uncommitted result and reviews
the diff through the normal cross-review, then commits in the worker's worktree with the
usual commit gate. A Claude worker commits its result and leaves the tree clean when the
brief and host permit it; otherwise it leaves the files for the lead.
For Codex the lead runs the `codex_worker.py --wait FILE --since START --stale FILE_ID --exit RECORD` command
printed by spawn as a background command; it reports DONE for a published uncommitted
`Kind: completed` result from this run. A previous task's result cannot signal the new run,
and neither can an in-place edit of it: spawn captures FILE_ID before launch, and a new result
is published by the rename. A file that changed in the run but sat unchanged for 60 s
without the result header and ready marker (a free-form report) ends the wait with NOT A
RESULT instead of a silent wait; the lead reads it by hand. `--since` (the launch time) is
required; with no supervisor record 300 s after the launch the wait ends with NOT STARTED (the
tab failed before the supervisor ran; running the same wait again is safe). Other result
kinds report BLOCKED, HANDOFF or PROGRESS. A completed result, a handoff or a decision ends
the session; a progress result leaves it running. After HANDOFF, `--wait` prints how to continue
the session with `--resume`. After PROGRESS, `--wait` also prints its exact follow-up
command: the same wait with `--stale` set to the reported result's content hash, and
`--since` still the run's start. It counts a publication as new when its content hash differs
from the reported one, by rename or by in-place rewrite; a byte-identical republication is
suppressed. The lead runs it as the next background command,
since spawn's command would return the same result at once. A worker that stops without publishing a result reports EXITED,
from the `.myagentkit/workers/NAME.exit` record the wrapper writes on every way out, a decision
without a blocked result included, or from its `NAME.live` lock once the wrapper itself was
killed. For Claude the committed `Kind: completed` result is
the watcher's done signal. The supervisor ends either worker's session on a completed result,
a handoff or a decision; the session stays resumable with `--resume`.
`spawn_worker.sh --result FILE` names a Claude worker's result. Merging a worker's branch closes the rest
(the post-merge hook runs `scripts/close_worker.sh --finished NAME`, which leaves a session
still running without a completed result); the lead runs `scripts/close_worker.sh NAME`
itself only for a session it finishes without a merge.
An idle notice or a question sidecar reports a waiting worker, never completion.

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
- `blocked` means the worker waits on a decision, or failed: the worker could not finish and
  says why.
- A worker whose context was compacted once finishes only if its `Remaining:` line is short;
  it writes `Kind: handoff` at the second compaction, or at once when much work remains,
  with a handoff section in the shape of this file. The `SessionStart` (compact) hook reminds
  it. This is the lead's rule too (`docs/WORKFLOW.md`, "Worker cost", rule 8). A Codex
  worker leaves the handoff uncommitted for the lead; a Claude worker commits it when its
  brief permits.
  A worktree worker carries the project's hooks, and at red the lead sends
  "finish the item, commit, Kind: handoff" (owner decision 23, 2026-10-16; Claude Code project settings:
  https://code.claude.com/docs/en/settings, checked 2026-10-16).
- `Task:` and `Attempt:` name the work the file reports on, so a result left by an earlier
  task of a reused session is never taken for the current one.

The Claude Code overlay's `scripts/watch_workers.sh --result NAME=PATH` reads this head once
the file is committed on a clean tree, and reports the open questions with their text.

A handoff written at the end of a working day also carries the cost figures that
`docs/WORKFLOW.md`, "Worker cost", rule 8 names (`/usage` and `scripts/agent_cost.py
--latest`), next to the number of tasks done, so the next lead routes from a number.

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

Sources for the brief's shape: an exact scope with its non-goals, sources to read and a check
that proves the result (code.claude.com/docs/en/best-practices, "Provide specific context",
"Give Claude a way to verify its work"; Anthropic, "How we built our multi-agent research
system": a vague delegation duplicates or misses work); the Proof line's cheapest check first,
the slow stage once (Fowler, "Continuous Integration", staged builds); routing judgement work
to the strongest model and checkable volume to a cheaper one (Anthropic, "Optimizing for cost
and intelligence"); a fresh session reviews better because it is not biased toward code it
just wrote (best-practices, Writer/Reviewer). The tool+model trace's reason is in
`docs/WORKFLOW.md`, "The state, backlog and phase files"; the ending lines follow the same
file's state rules (Anthropic, "Effective harnesses for long-running agents").

## Day-to-day task prompt

The full brief above is for handing work across tools. For an ordinary task inside one
session, the same skeleton compressed. A worker the lead manages on a branch gets the full
brief instead: its gate review is the lead's (`docs/WORKFLOW.md`, "The lead's steps when a
branch is ready").

```
Read: docs/PHASES.md, docs/STATE.md, <target folder>/AGENTS.md
      (docs/ARCHITECTURE.md only when the task crosses a module boundary)

TASK:   <one sentence — one module>
SCOPE:  <the files you may touch>
DO NOT: <explicit non-goals — and everything docs/PHASES.md puts out of scope>
PROOF:  <the cheapest check beyond the commit gate that proves this change; none: the gate>
        — never report a check you did not run
DONE:   <the command or observation that proves it>
REVIEW: you review your diff with fresh sub-agents before the commit; where
        CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH is 1 you cannot, so say so

If this task touches {{RISKY_AREAS}}, or any gate/CI/check script: before commit, run the
review gate per docs/REVIEW_RUNNING.md in a FRESH session that the working mode names
(docs/REVIEW_GATE.md, "Invariant").
Any other change gets its tier's review (docs/REVIEW_GATE.md, "Risk tiers").

When finishing: update docs/STATE.md with a tool+model trace (a follow-up task goes to
docs/BACKLOG.md; on a branch or in a worktree, write docs/worktree-notes/<branch>.md
instead), then a short summary.
```
