# {{PROJECT_NAME}} — Agent Constitution

Every agent reads this first; every line binds; a pointer names the how. A tree's own `AGENTS.md`
(`docs/AGENTS.md` for `docs/`) is read before editing that tree. **Started by
another agent?** It keeps the HARD RULES, STOP and MENTION ONCE, raised to that agent, skips the
reading order and the rest of "Duties", leaves `docs/STATE.md` to the lead and reports to that agent.

## What this project is

{{PROJECT_DESCRIPTION}}

Design authority: `docs/PROJECT.md` (DECIDED or OPEN items, by section). This file is canonical
(tool files point here); cross-tool memory: `docs/STATE.md`; task transfer: `docs/HANDOFF.md`.

## Commands

Build and test: `{{BUILD_TEST_COMMAND}}`. The gate, which must PASS (CI, commit hook): `./scripts/check.sh`.

## Reading order (new session)

1. `./scripts/doctor.sh --quiet` (not for a small fix); offer a fix per `MISSING:`. This file is read once.
2. `docs/PHASES.md` (now, and what is OUT of scope); `docs/STATE.md`: its "Active work" and
   "Blocked" sections (its session-end update is YOUR job).
3. `docs/ARCHITECTURE.md`: read it when the task crosses a module boundary or no doc says where
   code lives; `docs/PROJECT.md` by SECTION (`PROJECT §4.2`), never whole.
4. The target folder's `AGENTS.md` / `README.md`.

The session {{OWNER_NAME}} opens is the lead. Once per session it reads `docs/COMMUNICATION.md` and `docs/WORKFLOW.md`,
"Worker cost", its first block "The rules in brief"; `docs/GOTCHAS.md` on a surprise, `docs/BACKLOG.md` for the next task.

## HARD RULES (violation = failed task)

### Design authority

- Never contradict a DECIDED item of `docs/PROJECT.md`; OPEN items and marking DECIDED are
  {{OWNER_NAME}}'s: ask with options, go on with what does not depend on it. Needing something
  on the `docs/PHASES.md` out-of-scope list is a STOP.

### Architecture boundaries (most are also compiler/CI-enforced)

{{BOUNDARY_RULES}}

- Cross-module access only through public contracts; propose a contract change instead.
- Any third-party dependency needs {{OWNER_NAME}}'s approval.

### Task discipline (`docs/WORKFLOW.md`, "Task discipline — the details"; a quoted section with no file named is in that file)

- One change in one module, inside the brief's `Owns:` paths; more is a STOP. No drive-by
  refactors; a same-cause bug in a changed file is part of the task.
- No push, PR or remote update without {{OWNER_NAME}}'s word in this session.
- A git line holding `--out`, `--ext`, `--textc` or `--sub` (a commit message too) is denied:
  `git commit -F` a `mktemp` file written in its own step.
- **Commit or stash BEFORE any command that discards work**, after `git status`; a recursive
  delete first proves it owns the folder ("Destructive commands").
- **Never end running work** unless {{OWNER_NAME}} asked or it is provably finished or hung ("Ending running work").
- **A bug you can fix now is fixed now**; a reviewer's finding follows `docs/REVIEW_GATE.md`, "Verdicts and who decides".
- No untested code enters {{TESTED_AREA}}: a logic change brings its test, run in its own command
  and read before any commit (never `test; git commit`, never piped through a filter); plugin
  advice never replaces these rules.
- A commit reads its hook's `CHECK: PASS` (none: run the gate, say the hook is unwired); no
  commit: run the gate. **Never `git commit --no-verify`** or another way past the gate.
- **Read narrow:** grep or a range first, never a whole log, spill file or file over 300 lines; filter long output.
- **No AI attribution in git**, by trailer or prose ("The commit gate and attribution").
- Reuse an existing system before writing one; a changed public API updates its README in the same task.
- **Gates must be proven RED** ("Writing a gate"); `docs/STATE.md` edits follow `docs/AGENTS.md`.

### Review gate and validation honesty

- **Risky diffs** ({{RISKY_AREAS}}, gates, CI, check scripts, review tooling) pass the review gate
  before the main branch, others their tier's (`docs/REVIEW_GATE.md`, "Risk tiers"): unasked, by a
  FRESH session, never the author; a verdict's manual checks go to `docs/STATE.md`.
- **Never report a verification you did not run**; say "not run".

### Language & style

- **Docs, code, identifiers, comments, commits and STATE.md: English.** {{LANGUAGE_EXCEPTION}}
- Chat in {{CHAT_LANGUAGE}}, the answer first, then stop; written artifacts in full sentences; a
  failure, a "not run", a security warning or an irreversible action is never cut
  (`docs/COMMUNICATION.md`, "The two registers").
- One job per file and class; no hidden global state; good names over comments.

## Duties toward {{OWNER_NAME}}

Duties: `docs/COMMUNICATION.md`, read once per session; each rule there binds, as do the two lists below.

### STOP — pause the work and ask (rare)

Name it and ask; never silently comply or refuse.

- A "Design authority" rule would break, or a new dependency or MCP server is needed.
- A required verification cannot be run; an unavailable reviewer stops only what needs it
  (`docs/REVIEW_RUNNING.md`, "Unavailable reviewer").
- Parallel work on unfrozen contracts or against the worktree policy (`docs/WORKFLOW.md`, the
  four "Parallel work" sections).
- A test deleted, skipped or weakened unasked, or a gate changed without a red proof.
{{PROJECT_STOP_RULES}}

### MENTION ONCE — one line in your closing summary, never mid-work

- Risky area touched → "review gate applies before the merge".
- A duplicate system, a README contradicting its API, a two-job file, a task spanning modules, a
  procedure done a third time (a skill), bulk work fit for a cheaper model.
- Context past 150k → no new round; 200k: `/compact` or a hand-off; 300k: stop; a spawn refusal
  cap: hand-off at once (`docs/WORKFLOW.md`, "Worker cost", rule 8).
- A repeated cost with a cheaper way around it, numbered by `scripts/agent_cost.py`; never hunt for savings.
{{KIT_FEEDBACK_RULE}}

## Task completion checklist

The rules above held; `docs/STATE.md` has a tool+model trace; a what-and-why summary. A small
fix skips `doctor.sh` and the trace.

# Compact instructions

Keep: the open decisions, the binding rules, the changed files and commits, the next step,
{{OWNER_NAME}}'s words verbatim. Drop: finished work's tool output.
