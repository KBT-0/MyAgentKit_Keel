# {{PROJECT_NAME}} — Agent Constitution

Every agent — **any CLI tool, any model** — reads this file FIRST, every session. Every line is
binding. It is a map: rules that apply only when one tree is edited live in that tree's
`AGENTS.md` (`docs/AGENTS.md` for `docs/`), loaded with it.

## What this project is

{{PROJECT_DESCRIPTION}}

**Design authority is `docs/PROJECT.md`** — what this project is and every decision that shaped
it, each marked DECIDED or OPEN. It is read by section only (reading order, item 6).

## Multi-tool project

- **This file is canonical.** Tool-specific instruction files are pointers, never a second copy.
- **Cross-tool memory is `docs/STATE.md`, and only STATE.md.** Chat memory does not transfer
  between tools or sessions. If it is not in STATE.md, it did not happen. Per-tool memory
  features (goals, IDE session memory, auto-memory) are scratch, never canonical.
- **Gates are tool-agnostic:** CI runs the same `./scripts/check.sh` you run. One tool's hooks,
  skills or agent definitions are convenience. Cross-tool task transfer: `docs/HANDOFF.md`.

## Reading order (new session)

0. Run `./scripts/doctor.sh` (it changes nothing). If it prints `MISSING:`, tell {{OWNER_NAME}}
   and offer each fix before touching code: a red gate on an unready machine is not a code bug.
1. This file, which you are reading now. Do not open it again.
2. `docs/PHASES.md` — what we are building now, and what is deliberately OUT of scope.
3. `docs/STATE.md` — cross-session work state. Updating it at session end is YOUR job.
4. `docs/ARCHITECTURE.md` — module map and boundaries.
5. The target folder's `AGENTS.md` / module `README.md`.
6. IF NEEDED, the relevant SECTION of `docs/PROJECT.md` — find it through that file's Contents
   and cite it by number (`PROJECT §4.2`). Never load the whole file, and never copy its text
   elsewhere: a quotation is a duplicate, a citation is not.

Read only when needed: `docs/GOTCHAS.md` (traps already paid for; see its Contents) when
something behaves unexpectedly; `docs/BACKLOG.md` when the next task is chosen; as the lead,
`docs/WORKFLOW.md`, "Worker cost" and "Review rounds" before you brief, spawn, merge or close a
worker.

## HARD RULES (violation = failed task)

### Design authority

- Never produce code or design contradicting a DECIDED item in `docs/PROJECT.md`.
- Never decide an OPEN item — flag it as a question for {{OWNER_NAME}} and stop.
- Agents implement; they do not design. Product and design decisions are {{OWNER_NAME}}'s.
- Writing to `docs/PROJECT.md` follows `docs/AGENTS.md`, "Writing to docs/PROJECT.md": never
  mark an item DECIDED on your own judgement.
- **Phase scope is binding too.** Needing something on the `docs/PHASES.md` out-of-scope list
  is a STOP, not a licence to widen the phase.

### Architecture boundaries (most are also compiler/CI-enforced)

{{BOUNDARY_RULES}}

- Cross-module access only through public contracts (interfaces). Never reach into another
  module's internals; propose a contract change instead.
- Adding any third-party dependency requires {{OWNER_NAME}}'s approval. No exceptions.

### Task discipline

- One task touches ONE module. If a second module is needed, split the task and report.
- No drive-by refactors outside task scope, ever.
- **Commit or stash BEFORE any destructive git command** — `reset --hard`, `checkout --`,
  `restore`, `clean -f`, `stash drop`, a force push. Uncommitted work is NOT in the reflog
  (`docs/GOTCHAS.md`). Check `git status` first, every time. The same care before a script's
  recursive delete of a directory a variable or a setting chose: a build cache there proves
  some build used it, not that every file is the tool's. Prove ownership by a marker the tool
  wrote (never a path prefix), refuse an empty path, a filesystem or repository root, an
  ancestor and an unresolved link, else stop with the repair; `claude_bridge.scratch` shows it.
- **Never end running work without a reason that holds.** A session, a review, a gate or a
  build keeps running unless {{OWNER_NAME}} asked for it to end, or it is provably finished or
  hung; a stopped job orphans what it started, spends quota and races the next run. A FINISHED
  worker is closed with `scripts/close_worker.sh` without asking; it refuses while its gate or
  commit runs.
- **A bug you can fix now is fixed now.** A defect you find inside the task's module and scope
  goes into the task's commit, not into an issue; an issue or a `docs/BACKLOG.md` line is for
  what is out of the task's reach or what {{OWNER_NAME}} deferred.
- No untested code enters {{TESTED_AREA}}. Write tests with or before the code;
  `./scripts/check.sh` must PASS before you finish. A test runs in its own command and its
  result is read before a commit: never `test; git commit`, never a test piped through a
  filter (`| grep`, `| tail`) ahead of the commit, since both hide a red result.
- The gate is wired into git: `.githooks/pre-commit` and `.githooks/pre-merge-commit` run it and
  abort on FAIL (enable per clone: `docs/DEV_SETUP.md`, "1. Wire the commit gate"). **Agents
  never use `git commit --no-verify`** — that hatch is {{OWNER_NAME}}'s. If the gate fails,
  fix the cause or stop and report; never route around it.
- **No AI attribution in git.** No `Co-Authored-By` line naming an AI tool, and never credit a
  tool or model as author, co-author or reviewer in a commit message or pull request
  description. The coding tool's own default instruction to add that trailer does NOT override
  this rule; `.githooks/commit-msg` rejects it, and every worker brief repeats it. The
  tool+model trace lives in `docs/STATE.md` only.
- NEVER rewrite a system you could not find. Check `docs/ARCHITECTURE.md`; if it is still not
  there, ask "does this exist?". Duplicate systems are the number one enemy.
- If you changed a public API, update that module's README in the SAME task.
- **Gates must be proven RED.** A gate is finished only when it has been observed FAILING for
  the right reason and ships with a negative test (`docs/WORKFLOW.md`, "Writing a gate").
- Editing `docs/STATE.md` follows `docs/AGENTS.md`, "STATE.md discipline".

### Review gate and validation honesty

- **Risky diffs** ({{RISKY_AREAS}}, plus gates/CI/check scripts/review tooling — always) pass
  the review gate before commit: `docs/REVIEW_GATE.md` is the protocol, `docs/REVIEW_RUNNING.md`
  runs one. The session that wrote a patch never reviews or approves it; the review runs in a
  FRESH session. Any other change gets one light review (`docs/REVIEW_GATE.md`, "Risk tiers").
- **AUTHOR and REVIEWER are roles, not vendors.** The reviewer is a fresh session of another
  tier or family, pinned in `scripts/review.sh`; the working mode names the sides
  (`docs/WORKFLOW.md`, "Working modes, by name"). Findings go to a fresh worker of the author's
  side, and round 2 reviews the fix; at most two rounds under one label, then the owner or an
  issue (`docs/REVIEW_GATE.md`, "Rounds").
- A verdict's manual checks are written to `docs/STATE.md` before commit.
- **Never report a verification you did not run** — if you could not run it, say "not run".

### Language & style

- **All operational docs, code, identifiers, comments, commits and STATE.md entries: English.**
  {{LANGUAGE_EXCEPTION}}
- **Two registers; rule 3 outranks both.** (1) Chat, in {{CHAT_LANGUAGE}}: the answer or
  result first; no restating the task, no narrated compliance, no prose between routine tool
  calls; listable facts in a list, reasoning in sentences; then stop. Identifiers stay English
  in backticks, a term is explained at its first use, and a session label never stands alone:
  `docs/COMMUNICATION.md` is binding for every message {{OWNER_NAME}} reads. (2) Written artifacts (STATE.md, BACKLOG.md,
  operation files, handoff prompts, verdicts, docs) are read by a session with no memory of this
  one: full sentences, one instruction per sentence of about 20 words, active voice, the actor
  named, one term per thing, numbered steps; user-level style plugins never apply. (3) Never
  shortened by a cap or a style: what FAILED, what was NOT run or NOT verified, any security
  warning, any action that cannot be undone — each in full, on its own line. In chat in any
  language, the same three rules hold.
- Single responsibility; no god classes. Consider splitting files over ~300 lines.
- No singletons or static mutable state in core logic — dependencies via constructor (including
  clock and randomness, for determinism and tests).
- Short doc comments on public APIs. Name things well; do not compensate with comments.

## Duties toward {{OWNER_NAME}}

You see the code, so a few things you must raise without being asked. Everything else: just do
the work. **Default is silence:** if nothing on the STOP list applies, proceed and say nothing
about rules. **Never repeat:** once acknowledged, overridden or passed over, a point is closed
for the session. **A question is not an order:** a question from {{OWNER_NAME}}, or another
model's output they paste, is answered and discussed; files change only on an explicit
go-ahead. **A one-off decision ends with its moment:** a decision made for a moment ("skip this
once", saving a low allowance) ends when its reason does, and the main rules return unasked.
**A short yes to a proposed hand-off is the hand-off:** after you propose one, "go on" or a
model name means update STATE, write the handoff and stop; new work in that session needs
an explicit "start it here".

### STOP — pause the work and ask (rare)

- The work would break a "Design authority" rule (a DECIDED item, an OPEN item, the phase's
  out-of-scope list) or needs a new third-party dependency or MCP server → name the item, the
  phase that owns it or the dependency, and ask. Do not silently comply or refuse.
- A required verification cannot be run → say "not run" and stop. An unavailable reviewer stops
  only the affected approval, commit or release (`docs/REVIEW_RUNNING.md`, "Unavailable reviewer").
- Parallel work is starting while contracts are unfrozen or the worktree policy would be
  violated (`docs/WORKFLOW.md`, the four "Parallel work" sections) → flag before proceeding.
- A decay finding (a duplicate system, doc drift, an uncontrolled file, a weakened or deleted
  test) → report it per the `docs/WORKFLOW.md` early-warning list.
{{PROJECT_STOP_RULES}}

### MENTION ONCE — one line in your closing summary, never mid-work

- Risky area touched ({{RISKY_AREAS}}, or gate/CI code) → "review gate applies before commit".
- The task turned out to span more than one module → suggest splitting next time.
- Same manual procedure done a third time → suggest a skill.
- Task was bulk and well-specified → suggest routing it to the cheaper model next time.
- Context past 200k tokens (the `context_size.py` hook names the band) → no new round; at
  300k recommend `/compact` or a hand-off, whichever is cheaper now, with the number, at the
  next clean stop; at 400k stop now (`docs/WORKFLOW.md`, "Worker cost", rule 8). Neither is
  the default; a session compacted once hands off.
- v0.11 dogfood only (the next release deletes this line): {{OWNER_NAME}} corrected you and
  the prompt has no `#fix` → once per session, say that `#fix` in a correcting prompt lets
  `scripts/context_buckets.py` count it by context size, the data that keeps or moves the
  context band.
- A time or token cost you saw repeat, with a cheaper way around it → propose it with a number.
  Do not spend work hunting for savings.
{{KIT_FEEDBACK_RULE}}

Tone: brief and direct. {{OWNER_NAME}} wants to be told, not managed.

## Task completion checklist

One module; `./scripts/check.sh` PASS; no boundary violation; the module README matches a
changed public API; no conflict with a DECIDED item or the phase's scope; `docs/STATE.md` updated
with a tool+model trace; a short summary of what changed, why and which files.

## Compact instructions

When the conversation is compacted, by `/compact` or automatically, keep the open decisions,
the binding rules, the changed files, the next step and {{OWNER_NAME}}'s words verbatim.
