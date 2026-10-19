# docs/ — rules for editing this tree

Binding for every agent that edits a file under `docs/`. The constitution is the root
`AGENTS.md`; this file holds only what applies when a document here is written.

## Writing to docs/PROJECT.md

- You may add an OPEN item at any time. **You may never mark an item DECIDED on your own
  judgement.** DECIDED is written only for an item {{OWNER_NAME}} has explicitly approved,
  in this session, as that item; transcribing their approval is the job, inferring it is
  not. Anything you concluded, inferred or thought was implied stays OPEN. When they appear
  to settle something in passing, record it as OPEN with a note that they appeared to
  decide it, and ask.
- If the code and `docs/PROJECT.md` conflict: inform {{OWNER_NAME}} first; do not silently
  change either. Report which side you think is stale and why; {{OWNER_NAME}} decides.

## STATE.md discipline

- An authorized session edit is a direct Read, then Edit of `docs/STATE.md`: Claude Code's Edit
  refuses a file changed since its Read, so on refusal read it again and redo the edit. Never
  change the "Working mode:" line; it belongs to the mode switch.
- A shell write uses the state helper from the project root:
  `python3 scripts/working_mode.py --read-state .myagentkit/STATE.edit.md` (`python` on native
  Windows) prints `SHA256 PATH`; edit that PATH, then run
  `python3 scripts/working_mode.py --replace-state "PATH" --expect SHA256`. On refusal, run
  `--read-state` again, redo the edit there, and retry; a changed "Working mode:" line is refused.
- `docs/STATE.md` is TRANSIENT: current state only — what is in flight and what waits on
  someone.
- A next task or a parked item is written to `docs/BACKLOG.md`, never to STATE.md.
- **Completed work is DELETED, not marked DONE.** The history lives in git. The commit that
  finishes a task with an id carries a `Done: <id>` trailer, and the commit-msg hook and
  `./scripts/check.sh` then refuse a STATE.md or BACKLOG.md that still names it
  (`docs/WORKFLOW.md`, "Task ids").
- Before deleting a line, ask: *is this still true next month?* If yes, it must have a
  permanent home BEFORE it leaves — `docs/PROJECT.md` (a decision, as a numbered item),
  `docs/ARCHITECTURE.md` (a module or boundary), `docs/WORKFLOW.md` (a process or gate
  constraint), `docs/GOTCHAS.md` (an environment or tooling trap). If it is true only until
  this phase ends, it belongs in `docs/PHASES.md` instead. Permanent knowledge is never
  written INTO STATE.md; it passes THROUGH it.
- **TAG permanent findings as you write them:** prefix a line worth keeping with `[LESSON]`
  (process or architecture insight) or `[GOTCHA]` (environment or tooling trap). **A tagged
  line may not be deleted until it has a permanent home.** `scripts/check.sh` prints a NOTE
  when a commit deletes one from STATE.md and adds no line elsewhere; the rest is discipline.
- Multi-item operations track their progress in their OWN file, `docs/<OPERATION>.md`, with
  checkboxes; workers write results straight into it, and STATE.md keeps one status line
  and a pointer.
- No size limit applies to STATE.md. What keeps it small is deleting finished work in the
  commit that finishes it, and the backlog living in `docs/BACKLOG.md`.
- Every entry carries a tool+model trace, and updating STATE.md at session end is the
  agent's job, not {{OWNER_NAME}}'s. A session on a branch or in a worktree writes
  `docs/worktree-notes/<branch>.md` instead; the lead folds it in at the merge
  (`docs/WORKFLOW.md`, "Parallel work — where a branch agent writes its notes").
