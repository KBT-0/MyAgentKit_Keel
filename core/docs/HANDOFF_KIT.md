<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->

# HANDOFF — the kit's part

The kit's generic rules of `docs/HANDOFF.md`, under its headings. The project's file keeps its
placeholders, its owner's decisions and its own rules, and each heading there whose text moved
ends with a "Kit rules:" line naming the heading here. This file is the kit's, and a sync
replaces it. Generic rules live here by the owner's decision of 2026-10-22 (docsowned question
1, #94); the rule that a kit-owned file holds only reasons (`docs/WORKFLOW_RATIONALE.md`) is
`docs/WORKFLOW.md`'s alone. Do not edit it: a project that needs a different rule writes it in
`docs/HANDOFF.md`, the project-owned file, and the project file wins over this one.

## The brief

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
`KIT_WORKER_GRACE`) before closing the worker's process tree. A Claude worker first
publishes, then messages the lead: `spawn_worker.sh` names the lead's session in its
instruction (one SendMessage with the published file's path, its Kind and one line; none
after a progress result) and gives it sixty seconds, since a loaded host delivered that message
21 and 27 seconds after the publish. The message is best-effort; the lead's disk watch stays the
done signal. A question reaches the lead
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
