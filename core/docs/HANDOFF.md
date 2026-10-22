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
   A task whose checks build, download or write outside the worktree quotes its environment:
   a fresh worktree has no build tree, dependency cache or virtual environment, and a sandboxed
   worker has no network and writes only in its worktree and the temporary directory. Name the
   downloads to stage and the user-profile paths to redirect.
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
   one at the top of its result before any code (the same section). A sub-agent's brief
   carries the design and names the lines to read: a sub-agent has about 120k of context
   before its first compaction (`docs/WORKFLOW.md`, "Worker cost", rule 3).
5. **Routing check:** does this task belong on the model it is being sent to? Judgement work
   — architecture, contracts, risky diffs — goes to the strongest model; bulk, mechanical,
   well-specified work goes to the cheaper one. If the requested route violates that, say so
   instead of producing the prompt. The brief names the model AND the effort level, chosen
   from `docs/WORKFLOW.md`, "Model routing" (both tables), and the lead verifies both after
   the run from the transcript (Claude Code: the `"effort"` field; Codex: the
   `reasoning effort:` header of its log). Why neither is left to inheritance, and how it is
   enforced: `docs/WORKFLOW.md`, "Worker cost", rule 5.
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
- A compaction never ends a worker's task. It is a cost signal the worker records in its
  report (how many, and the context at which each fired, the `preTokens` of its
  `compact_boundary` record, when its transcript shows it, else "compacted N times"), then
  it goes on: running work "keeps running unless {{OWNER_NAME}} asked for it to end, or it
  is provably finished or hung" (`AGENTS.md`). Two workers that handed off at their second
  compaction had written no code, and the next one paid their reading again (#303,
  2026-10-22). A
  worker writes `Kind: handoff` on its own only when the task truly cannot finish in its session (the
  turn backstop is near with work left, or the brief turns out to be more than one task),
  and when the lead tells it to (the red band, below); either way with a handoff section in the shape of this file. The code it wrote is never discarded: a
  Claude worker commits it on its branch when the brief and host permit it, a Codex worker
  leaves it uncommitted in its worktree and names the changed files; either names the exact
  next step. "Nothing is edited" is never a hand-off body. The `SessionStart` (compact) hook reminds it. The lead's own session
  follows a different rule, the context band and one compaction at most (`docs/WORKFLOW.md`,
  "Worker cost", rule 8).
  A worktree worker carries the project's hooks, and at red the lead sends
  "finish the item, commit, Kind: handoff", the code committed or named first as above (owner decision 23, 2026-10-16; Claude Code project settings:
  https://code.claude.com/docs/en/settings, checked 2026-10-16).
- `Task:` and `Attempt:` name the work the file reports on, so a result left by an earlier
  task of a reused session is never taken for the current one.

The Claude Code overlay's `scripts/watch_workers.sh --result NAME=PATH` reads this head once
the file is committed on a clean tree, and reports the open questions with their text.

A handoff written at the end of a working day also carries the cost figures that
`docs/WORKFLOW.md`, "Worker cost", rule 8 names (`/usage` and `scripts/agent_cost.py
--latest`), next to the number of tasks done, so the next lead routes from a number.

A project that needs a different rule writes it here, and this file wins over `docs/HANDOFF_KIT.md`.
Kit rules: docs/HANDOFF_KIT.md, "The brief".

## Sizing the task before you write the brief

Kit rules: docs/HANDOFF_KIT.md, "Sizing the task before you write the brief".

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
