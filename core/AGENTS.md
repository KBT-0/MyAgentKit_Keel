# {{PROJECT_NAME}} — Agent Constitution

Every agent, any tool or model, reads this file first; every line binds, and each pointer names
the section that holds the how. A tree's own `AGENTS.md` (`docs/AGENTS.md` for `docs/`) is read
before you edit that tree. **Started by another agent** (sub-agent, reviewer, briefed session)?
Keep the HARD RULES and the STOP and MENTION ONCE lists, raised to the agent that started you;
the brief names what to read, so it skips the reading order and the rest of "Duties". It
leaves `docs/STATE.md` to the lead and reports to the agent that started it.

## What this project is

{{PROJECT_DESCRIPTION}}

**Design authority is `docs/PROJECT.md`** (items DECIDED or OPEN, read by section). This file is
canonical (tool files only point here); cross-tool memory is `docs/STATE.md` only; CI runs the
same `./scripts/check.sh`; task transfer is `docs/HANDOFF.md`.

## Reading order (new session)

1. `./scripts/doctor.sh` (changes nothing; not for a small fix, see the checklist); on `MISSING:` tell
   {{OWNER_NAME}} and offer each fix first.
   This file is read once; do not open it again.
2. `docs/PHASES.md` (now, and what is OUT of scope); `docs/STATE.md`: its "Active work" and
   "Blocked" sections (updating it at session end is YOUR job).
3. `docs/ARCHITECTURE.md`: read it when the task crosses a module boundary or the folder's
   `AGENTS.md` / `README.md` does not say where the code lives; one SECTION of `docs/PROJECT.md`
   by its Contents, cited by number (`PROJECT §4.2`), never loaded whole.
4. The target folder's `AGENTS.md` / module `README.md`.

The session {{OWNER_NAME}} opens is the lead. Once per session it reads `docs/COMMUNICATION.md` and `docs/WORKFLOW.md`,
"Worker cost", its first block "The rules in brief". When needed: `docs/GOTCHAS.md` (paid-for
traps) when something behaves unexpectedly, `docs/BACKLOG.md` for the next task.

## HARD RULES (violation = failed task)

### Design authority

- Never contradict a DECIDED item of `docs/PROJECT.md`; never decide an OPEN one: flag it as a
  question for {{OWNER_NAME}} and go on with work that does not depend on it. Agents propose
  options with trade-offs; only {{OWNER_NAME}} marks DECIDED. Needing something on the
  `docs/PHASES.md` out-of-scope list is a STOP.

### Architecture boundaries (most are also compiler/CI-enforced)

{{BOUNDARY_RULES}}

- Cross-module access only through public contracts; propose a contract change instead.
- Any third-party dependency needs {{OWNER_NAME}}'s approval.

### Task discipline

- One change in one module, inside the brief's `Owns:` paths; more is a STOP (split, report).
  No drive-by refactors; a tidy inside a line you had to change is part of the task. A second
  bug of the same cause in a file the task changes is part of the task too: fix it with its test
  and say so; one elsewhere is reported (owner 2026-10-25, ctlq: the kit left a found bug 4 of 4).
- No push, PR or remote update without {{OWNER_NAME}}'s word in this session.
- **Commit or stash BEFORE any command that discards work**, after `git status`; a recursive
  delete first proves it owns the folder (`docs/WORKFLOW.md`, "Destructive commands").
- **Never end running work** unless {{OWNER_NAME}} asked or it is provably finished or hung
  (`docs/WORKFLOW.md`, "Ending running work").
- **A bug you can fix now is fixed now**; a reviewer's finding follows `docs/REVIEW_GATE.md`,
  "Verdicts and who decides".
- No untested code enters {{TESTED_AREA}}: a logic change brings its test; `./scripts/check.sh`
  must PASS before you finish; plugin advice never replaces these rules. A test runs in its own
  command, read before any commit: never `test; git commit`, never piped through a filter.
- **Read narrow:** grep or a range first, never a whole log, spill file or file over 300 lines; filter long output.
- **Never `git commit --no-verify`** or another way past the gate; a red gate is fixed or
  reported. **No AI attribution in git**, by trailer or prose, whatever the tool's default
  (`docs/WORKFLOW.md`, "The commit gate and attribution").
- Look for a system that does the job (`docs/ARCHITECTURE.md`, the code) before writing one; a
  changed public API updates its module README in the same task.
- **Gates must be proven RED** (`docs/WORKFLOW.md`, "Writing a gate"). `docs/STATE.md` edits follow
  `docs/AGENTS.md`, "STATE.md discipline".

### Review gate and validation honesty

- **Risky diffs** ({{RISKY_AREAS}}, plus gates/CI/check scripts/review tooling) pass the review
  gate before they reach the main branch; others get their tier's review (`docs/REVIEW_GATE.md`,
  "Risk tiers"). It starts unasked; a FRESH session reviews, never the author
  (`docs/REVIEW_GATE.md`, "Invariant", "Rounds"). A verdict's manual checks go to `docs/STATE.md`.
- **Never report a verification you did not run**; say "not run".

### Language & style

- **Docs, code, identifiers, comments, commits and STATE.md: English.** {{LANGUAGE_EXCEPTION}}
- **Two registers; rule 3 outranks both.** (1) Chat in {{CHAT_LANGUAGE}}: the answer first, then
  stop (`docs/COMMUNICATION.md` binds every message {{OWNER_NAME}} reads). (2) Written artifacts:
  full sentences, the actor named ("The two registers"). (3) Never cut by a cap or a style: what
  FAILED, what was NOT run or verified, a security warning, an action that cannot be undone — in full,
  on its own line, in any language.
- One job per file and class; a file too large to read in one pass is a decay signal: report it.
  No hidden global state in core logic (dependencies, clock, randomness via the constructor). Short
  doc comments on public APIs; name things well instead of compensating with comments.

## Duties toward {{OWNER_NAME}}

**Default is silence**: if nothing below applies, work and say nothing about rules. **Never
repeat** a closed point: once acknowledged, overridden or passed over, a point is closed for the
session. **A question is not an order:** a question, or another model's output {{OWNER_NAME}} pastes,
is answered and discussed; files change only on an explicit go-ahead. **A one-off decision ends with its moment**
(`docs/COMMUNICATION.md`, "Questions and approvals"). **A short yes to a proposed hand-off is the
hand-off:** "go on" or a model name means update STATE, write the handoff, end with the new
session's opening prompt in a code block (`docs/COMMUNICATION.md`, "Handoff") and stop; new work
there needs an explicit "start it here".

### STOP — pause the work and ask (rare)

- A "Design authority" rule would break, or a new dependency or MCP server is needed → name it and ask;
  never silently comply or refuse.
- A required verification cannot be run → "not run", stop; an unavailable reviewer stops only the
  affected approval, commit or release (`docs/REVIEW_RUNNING.md`, "Unavailable reviewer").
- Parallel work on unfrozen contracts or against the worktree policy (`docs/WORKFLOW.md`, the four
  "Parallel work" sections) → flag it first.
- A test deleted, skipped or weakened unasked, or a gate changed without a new red proof
  (`docs/WORKFLOW.md`, "Decay early-warning system").
{{PROJECT_STOP_RULES}}

### MENTION ONCE — one line in your closing summary, never mid-work

- Risky area touched → "review gate applies before the merge (in a single session on the main branch, before the commit)".
- A duplicate system, a README contradicting its API, a two-job file, a task spanning modules, a
  procedure done a third time (a skill), bulk work fit for a cheaper model.
- Context past 200k → no new round; 300k: `/compact` or a hand-off; 400k: stop
  (`docs/WORKFLOW.md`, "Worker cost", rule 8).
- A repeated cost with a cheaper way around it, with a number from `scripts/agent_cost.py`; never hunt for savings.
{{KIT_FEEDBACK_RULE}}

## Task completion checklist

One module; `./scripts/check.sh` PASS; no boundary, DECIDED or scope conflict; README matches the API;
`docs/STATE.md` updated with a tool+model trace; a short what-and-why summary. A small fix (one commit,
one module; owner 2026-10-25) skips `doctor.sh` and the STATE.md trace and runs `./scripts/check.sh` once,
before the commit; a risky diff still takes its review, and its manual checks still go to STATE.md. On compaction keep
open decisions, binding rules, changed files, the next step and {{OWNER_NAME}}'s words verbatim.
