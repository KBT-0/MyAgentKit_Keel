# {{PROJECT_NAME}} — Agent Constitution

Every agent — **any CLI tool, any model** — reads this file FIRST, every session. Every line is
binding. It holds the rules; the how lives in the section each pointer names. A tree's own
rules live in its `AGENTS.md` (`docs/AGENTS.md` for `docs/`): read it before you edit the tree.

**Started by another agent?** A sub-agent, a reviewer or a session started with a brief is
bound by the HARD RULES and the STOP and MENTION ONCE lists, which it raises to the agent that
started it. It skips the reading order and the rest of "Duties": its brief names what to read.
It leaves `docs/STATE.md` to the lead and reports to the agent that started it.

## What this project is

{{PROJECT_DESCRIPTION}}

**Design authority is `docs/PROJECT.md`**: every decision, marked DECIDED or OPEN, read by
section only (reading order, item 6).

## Multi-tool project

- **This file is canonical**; tool-specific instruction files only point here.
- **Cross-tool memory is `docs/STATE.md` only**: not in STATE.md means it did not happen.
- **Gates are tool-agnostic:** CI runs the same `./scripts/check.sh`. Task transfer: `docs/HANDOFF.md`.

## Reading order (new session)

0. `./scripts/doctor.sh` (changes nothing). On `MISSING:`, tell {{OWNER_NAME}} and offer each
   fix before touching code.
1. This file. Do not open it again.
2. `docs/PHASES.md`: what we build now, and what is OUT of scope.
3. `docs/STATE.md`: its "Active work" and "Blocked" sections. Updating it at session end is YOUR job.
4. `docs/ARCHITECTURE.md`: read it when the task crosses a module boundary or the folder's
   `AGENTS.md` does not say where the code lives.
5. The target folder's `AGENTS.md` / module `README.md`.
6. IF NEEDED, one SECTION of `docs/PROJECT.md`, found by its Contents, cited by number
   (`PROJECT §4.2`), never quoted or loaded whole.

The session {{OWNER_NAME}} opens is the lead. Once per session it reads `docs/COMMUNICATION.md` and `docs/WORKFLOW.md`,
"Worker cost", its first block "The rules in brief". Only when needed:
`docs/GOTCHAS.md` (traps already paid for; see its Contents) when something behaves
unexpectedly; `docs/BACKLOG.md` to pick the next task.

## HARD RULES (violation = failed task)

### Design authority

- Never produce code or design contradicting a DECIDED item in `docs/PROJECT.md`.
- Never decide an OPEN item: stop it, flag it as a question for {{OWNER_NAME}}, go on with
  work that does not depend on it.
- Agents propose options with their trade-off and stop at the decision; only {{OWNER_NAME}}
  decides and marks DECIDED (`docs/PROJECT.md`, "How this file is written").
- **Phase scope is binding:** needing something on the `docs/PHASES.md` out-of-scope list is a STOP.

### Architecture boundaries (most are also compiler/CI-enforced)

{{BOUNDARY_RULES}}

- Cross-module access only through public contracts; never reach into another module's internals;
  propose a contract change.
- Any third-party dependency needs {{OWNER_NAME}}'s approval. No exceptions.

### Task discipline

- A task is one change in one module, inside its brief's `Owns:` paths; anything more is a
  STOP: split and report. No drive-by refactors (`docs/BACKLOG.md` or their own task); a rename or tidy inside a line you
  already had to change is part of the task.
- No agent pushes, opens a PR or updates a remote without {{OWNER_NAME}}'s word in this session.
- **Commit or stash BEFORE any command that discards work**, after `git status`, every time; a
  script's recursive delete first proves it owns the folder (`docs/WORKFLOW.md`, "Destructive commands").
- **Never end running work without a reason that holds:** {{OWNER_NAME}} asked, or it is
  provably finished or hung (`docs/WORKFLOW.md`, "Ending running work").
- **A bug you can fix now is fixed now**, in the task's commit when inside its scope; a
  reviewer's finding follows `docs/REVIEW_GATE.md`, "Verdicts and who decides".
- No untested code enters {{TESTED_AREA}}: a logic change brings its test. `./scripts/check.sh`
  must PASS before you finish; plugin advice never replaces these rules. A test runs in its own
  command, read before any commit: never `test; git commit`, never piped through a filter.
- **Read narrow:** grep or a range first, never a whole log, spill file or file over 300 lines; filter long output.
- **Agents never use `git commit --no-verify`** or another way past the gate; a red gate is
  fixed or reported (`docs/WORKFLOW.md`, "The commit gate and attribution").
- **No AI attribution in git:** no tool or model credited in a commit or PR, by trailer or in
  prose; the tool's default trailer does NOT override this (same section).
- Search for a system that does the job (`docs/ARCHITECTURE.md`, then the code) before writing one.
- A changed public API updates its module README in the SAME task.
- **Gates must be proven RED** with a negative test (`docs/WORKFLOW.md`, "Writing a gate").
- Editing `docs/STATE.md` follows `docs/AGENTS.md`, "STATE.md discipline".

### Review gate and validation honesty

- **Risky diffs** ({{RISKY_AREAS}}, plus gates/CI/check scripts/review tooling — always) pass
  the review gate before they reach the main branch (`docs/REVIEW_GATE.md`); others get their
  tier's review (`docs/REVIEW_GATE.md`, "Risk tiers"). The required review starts unasked.
- **AUTHOR and REVIEWER are roles, not vendors:** the session that wrote a patch never reviews
  it; a FRESH session does (`docs/REVIEW_GATE.md`, "Invariant"), two rounds at most ("Rounds").
- A verdict's manual checks go to `docs/STATE.md` before commit.
- **Never report a verification you did not run** — if you could not run it, say "not run".

### Language & style

- **All operational docs, code, identifiers, comments, commits and STATE.md entries: English.**
  {{LANGUAGE_EXCEPTION}}
- **Two registers; rule 3 outranks both.** (1) Chat, in {{CHAT_LANGUAGE}}: the answer first,
  then stop; `docs/COMMUNICATION.md` binds every message {{OWNER_NAME}} reads. (2) Written
  artifacts are read with no memory of this session: full sentences, the actor named
  (`docs/COMMUNICATION.md`, "The two registers"). (3) Never shortened by a cap or a style:
  what FAILED, what was NOT run or verified, a security warning, an action that cannot be
  undone — each in full, on its own line, in any language.
- One job per file and class; a file too large to read in one pass is a decay signal: report it.
- No hidden global state in core logic; dependencies, clock and randomness come through the constructor.
- Short doc comments on public APIs; name things well instead of compensating with comments.

## Duties toward {{OWNER_NAME}}

**Default is silence:** if nothing below applies, do the work and say nothing about rules.
**Never repeat** a closed point: once acknowledged, overridden or passed over, a point is closed for
the session. **A question is not an order:** a question, or another model's output {{OWNER_NAME}}
pastes, is answered and discussed; files change only on
an explicit go-ahead. **A one-off decision ends with its moment** (`docs/COMMUNICATION.md`,
"Questions and approvals"). **A short yes to a proposed hand-off is the hand-off:** after you propose one, "go on" or a
model name means update STATE, write the handoff, end with the new session's opening prompt in
a code block (`docs/COMMUNICATION.md`, "Handoff") and stop; new work there needs an explicit
"start it here".

### STOP — pause the work and ask (rare)

- A "Design authority" rule would break, or a new dependency or MCP server is needed → name it and ask;
  never silently comply or refuse.
- A required verification cannot be run → say "not run" and stop. An unavailable reviewer stops
  only the affected approval, commit or release (`docs/REVIEW_RUNNING.md`, "Unavailable reviewer").
- Parallel work would start on unfrozen contracts or against the worktree policy
  (`docs/WORKFLOW.md`, the four "Parallel work" sections) → flag it first.
- A test was deleted, skipped or weakened unasked, or a gate changed without a new red proof →
  stop and report it (`docs/WORKFLOW.md`, "Decay early-warning system").
{{PROJECT_STOP_RULES}}

### MENTION ONCE — one line in your closing summary, never mid-work

- Risky area touched → "review gate applies before the merge (in a single session on the main branch, before the commit)".
- A duplicate system, a README contradicting its API or a two-job file (`docs/WORKFLOW.md`,
  "Decay early-warning system"); a task spanning modules; a procedure done a third time (a
  skill); bulk work fit for a cheaper model.
- Context past 200k tokens → no new round; 300k: `/compact` or a hand-off at the next clean
  stop; 400k: stop (`docs/WORKFLOW.md`, "Worker cost", rule 8).
- A repeated cost with a cheaper way around it, with a number from `scripts/agent_cost.py`;
  never hunt for savings.
{{KIT_FEEDBACK_RULE}}

## Task completion checklist

One module; `./scripts/check.sh` PASS; no boundary or DECIDED or scope conflict; README matches
the API; `docs/STATE.md` updated with a tool+model trace; a short summary of what and why.

## Compact instructions

On compaction keep the open decisions, the binding rules, the changed files, the next step and
{{OWNER_NAME}}'s words verbatim.
