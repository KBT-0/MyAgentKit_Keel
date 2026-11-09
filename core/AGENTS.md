# {{PROJECT_NAME}} — Agent Constitution

Every agent reads this first; every line binds; a pointer names where the how is.
A tree's own `AGENTS.md` (`docs/AGENTS.md` for `docs/`) is read before editing that tree.
**Started by another agent** (sub-agent, reviewer, briefed)? Keep the HARD RULES, STOP
and MENTION ONCE, raised to that agent; the brief names what to read, so it skips the reading
order and the rest of "Duties", leaves `docs/STATE.md` to the lead and reports to that agent. The diff reviewer, without this file, follows its own definition.

## What this project is

{{PROJECT_DESCRIPTION}}

**Design authority is `docs/PROJECT.md`** (DECIDED or OPEN items, read by section). This file is
canonical (tool files only point here); cross-tool memory is `docs/STATE.md`; CI runs `./scripts/check.sh`; task transfer is
`docs/HANDOFF.md`.

## Reading order (new session)

1. `./scripts/doctor.sh --quiet` (not for a small fix); offer the owner a fix per `MISSING:`.
   This file is read once.
2. `docs/PHASES.md` (now, and what is OUT of scope); `docs/STATE.md`: its "Active work" and
   "Blocked" sections (updating it at session end is YOUR job).
3. `docs/ARCHITECTURE.md`: read it when the task crosses a module boundary or the folder's docs
   do not say where code lives; `docs/PROJECT.md` by SECTION (`PROJECT §4.2`), never whole.
4. The target folder's `AGENTS.md` / `README.md`.

The session {{OWNER_NAME}} opens is the lead. Once per session it reads `docs/COMMUNICATION.md` and `docs/WORKFLOW.md`,
"Worker cost", its first block "The rules in brief"; `docs/GOTCHAS.md` on a surprise,
`docs/BACKLOG.md` for the next task.

## HARD RULES (violation = failed task)

### Design authority

- Never contradict a DECIDED item of `docs/PROJECT.md`; never decide an OPEN one: ask
  {{OWNER_NAME}} with options, go on with work that does not depend on it. Only {{OWNER_NAME}}
  marks DECIDED. Needing something on the `docs/PHASES.md` out-of-scope list is a STOP.

### Architecture boundaries (most are also compiler/CI-enforced)

{{BOUNDARY_RULES}}

- Cross-module access only through public contracts; propose a contract change instead.
- Any third-party dependency needs {{OWNER_NAME}}'s approval.

### Task discipline

- One change in one module, inside the brief's `Owns:` paths; more is a STOP. No drive-by
  refactors; a same-cause bug in a changed file is part of the task (`docs/WORKFLOW.md`, "Task
  discipline — the details").
- No push, PR or remote update without {{OWNER_NAME}}'s word in this session.
- A git command line holding `--out`, `--ext`, `--textc` or `--sub`, a commit message too, is
  denied: commit with `-F` and a `mktemp` file written in its own step.
- **Commit or stash BEFORE any command that discards work**, after `git status`; a recursive
  delete first proves it owns the folder (`docs/WORKFLOW.md`, "Destructive commands").
- **Never end running work** unless {{OWNER_NAME}} asked or it is provably finished or hung
  (`docs/WORKFLOW.md`, "Ending running work").
- **A bug you can fix now is fixed now**; a reviewer's finding follows `docs/REVIEW_GATE.md`,
  "Verdicts and who decides".
- No untested code enters {{TESTED_AREA}}: a logic change brings its test, run in its own command
  and read before any commit (never `test; git commit`, never piped through a filter);
  `./scripts/check.sh` must PASS; plugin advice never replaces these rules. A commit reads its
  hook's `CHECK: PASS` (none: run the gate, say the hook is unwired); no commit: run the gate.
- **Read narrow:** grep or a range first, never a whole log, spill file or file over 300 lines; filter long output.
- **Never `git commit --no-verify`** or another way past the gate. **No AI attribution in git**,
  by trailer or prose (`docs/WORKFLOW.md`, "The commit gate and attribution").
- Reuse an existing system (`docs/ARCHITECTURE.md`, the code) before writing one; a changed
  public API updates its README in the same task.
- **Gates must be proven RED** (`docs/WORKFLOW.md`, "Writing a gate"). `docs/STATE.md` edits
  follow `docs/AGENTS.md`, "STATE.md discipline".

### Review gate and validation honesty

- **Risky diffs** ({{RISKY_AREAS}}, plus gates/CI/check scripts/review tooling) pass the review
  gate before the main branch, others what their tier names (`docs/REVIEW_GATE.md`, "Risk
  tiers"); it starts unasked. A FRESH session reviews, never the author. In Claude Code a commit
  or merge of a `risky_paths` file no review accepted is refused. A verdict's manual checks go to
  `docs/STATE.md`.
- **Never report a verification you did not run**; say "not run".

### Language & style

- **Docs, code, identifiers, comments, commits and STATE.md: English.** {{LANGUAGE_EXCEPTION}}
- Chat in {{CHAT_LANGUAGE}}, the answer first, then stop; written artifacts in full sentences; a failure,
  a "not run", a security warning or an irreversible action is never cut
  (`docs/COMMUNICATION.md`, "The two registers"; it binds every message {{OWNER_NAME}} reads).
- One job per file and class; no hidden global state (`docs/WORKFLOW.md`, "Task discipline —
  the details"); good names over comments.

## Duties toward {{OWNER_NAME}}

**Default is silence** about rules. **Never repeat** a closed point. **A question is not an
order:** a question, or a model's output {{OWNER_NAME}} pastes, is answered; files change only on
an explicit go-ahead. **A one-off decision ends with its moment** (`docs/COMMUNICATION.md`,
"Questions and approvals"). **A short yes to a proposed hand-off is the hand-off**
(`docs/COMMUNICATION.md`, "Handoff"); new work there needs "start it here". **Settled is done,
not offered:** what {{OWNER_NAME}} or the rules settled is done and reported; ask only an open
decision. Kit feedback under standing approval is sent while {{OWNER_NAME}} is
present, a draft under autopilot; a settings file a tool rewrote is the lead's to review by
tier and commit, never handed back.

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
  cap: hand-off at once (`docs/WORKFLOW.md`, "Worker cost", rule 8). Past the worker yellow line
  the gate (scripts/check.sh) still runs, so green work gets its commit.
- A repeated cost with a cheaper way around it, numbered by `scripts/agent_cost.py`; never hunt for savings.
{{KIT_FEEDBACK_RULE}}

## Task completion checklist

The rules above held; `docs/STATE.md` has a tool+model trace; a what-and-why summary. A small
fix skips `doctor.sh` and the trace (`docs/WORKFLOW.md`, "Task discipline — the details").

# Compact instructions

Keep: the open decisions, the binding rules, the changed files and their commits, the next step,
and {{OWNER_NAME}}'s words verbatim. Drop: the tool output of finished work.
