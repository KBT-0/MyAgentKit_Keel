# STATE.md — Cross-Session Work State ({{PROJECT_NAME}})

This file lists OPEN items only: active work, what waits on {{OWNER_NAME}}, and manual checks
not yet done. A closed item is deleted in the edit that closes it, never ticked or narrated:
the history is git's. Its rules, and the permanent home for anything still true next month,
are in `docs/AGENTS.md`, "STATE.md discipline" (the reasons: `docs/WORKFLOW.md`, "The state,
backlog and phase files"). Every entry has a tool+model trace.

---

**Working mode:** solo (`docs/WORKFLOW.md`, "Working modes, by name"; `/myagentkit:mode` switches it).

## Active work

(task + module + status, or one line per operation pointing at its `docs/<OPERATION>.md`;
delete when done — an EMPTY section means nothing is in flight, so never park closed work
here; that meaning is a contract the gate does not check)

## Blocked / waiting on {{OWNER_NAME}}

(a decision, an approval, or a manual check owed by {{OWNER_NAME}})

## Known issues / watch out

Environment and tooling traps have a permanent home: **`docs/GOTCHAS.md`**. Read it when
something behaves unexpectedly. What belongs here instead is a check that is outstanding
RIGHT NOW — a manual verification owed before the next commit, a claim that has not been
observed yet.

