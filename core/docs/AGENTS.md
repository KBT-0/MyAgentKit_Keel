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
  change either.

## STATE.md discipline

- Every authorized session edit is a compare-and-swap, in this order, from the project root:
  `python scripts/working_mode.py --read-state .myagentkit/STATE.edit.md` creates a fresh,
  exclusively owned per-edit snapshot using that prefix and prints `SHA256 PATH`. Edit the
  returned PATH, never a copy read earlier or another writer's snapshot; then run
  `python scripts/working_mode.py --replace-state "PATH" --expect SHA256`.
  The file lives in `.myagentkit/` (ignored) or the temporary folder, and the helper deletes it
  once published. On refusal, run `--read-state` again, redo the edit there, and retry. The
  "Working mode:" line belongs to the mode switch: an edit that changes it is refused.
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
  line may not be deleted until it has a permanent home.**
- Multi-item operations track their progress in their OWN file, `docs/<OPERATION>.md`, with
  checkboxes; workers write results straight into it, and STATE.md keeps one status line
  and a pointer.
- No size limit applies to STATE.md. What keeps it small is deleting finished work in the
  commit that finishes it, and the backlog living in `docs/BACKLOG.md`.
- Every entry carries a tool+model trace, and updating STATE.md at session end is the
  agent's job, not {{OWNER_NAME}}'s.
