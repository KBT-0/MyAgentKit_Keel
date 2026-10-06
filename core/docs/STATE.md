# STATE.md — Cross-Session Work State ({{PROJECT_NAME}})

**If it is not written here, it did not happen.** This file holds current state only: what
is in flight and what waits on someone. Its rules, and the permanent home for anything still
true next month, are in `AGENTS.md`, "STATE.md discipline" (the reasons: `docs/WORKFLOW.md`,
"The state, backlog and phase files"). Every entry has a tool+model trace.

---

## Active work

(task + module + status, or one line per operation pointing at its `docs/<OPERATION>.md`;
delete when done — an EMPTY section means nothing is in flight, so never park closed work
here)

## Blocked / waiting on {{OWNER_NAME}}

(a decision, an approval, or a manual check owed by {{OWNER_NAME}})

## Known issues / watch out

Environment and tooling traps have a permanent home: **`docs/GOTCHAS.md`**. Read it when
something behaves unexpectedly. What belongs here instead is a check that is outstanding
RIGHT NOW — a manual verification owed before the next commit, a claim that has not been
observed yet.

