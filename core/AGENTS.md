# {{PROJECT_NAME}} — Agent Constitution

Every agent — **any CLI tool, any model** — reads this file FIRST, every session. Every line
is binding.

## What this project is

{{PROJECT_DESCRIPTION}}

**Design authority is `docs/PROJECT.md`** — what this project is and every decision that
shaped it, each marked DECIDED or OPEN. It is read by section only (reading order, item 6).

## Multi-tool project

- **This file is canonical.** Tool-specific instruction files are pointers, never a second
  copy.
- **Cross-tool memory is `docs/STATE.md`, and only STATE.md.** Chat memory does not transfer
  between tools or sessions. If it is not in STATE.md, it did not happen.
- **Tool-specific memory features are scratch, never canonical.** Per-tool goals, IDE
  session memory, auto-memory and the like are private conveniences of one tool; the next
  tool cannot read them.
- **Gates are tool-agnostic:** CI runs the same `./scripts/check.sh` you run. A single
  tool's hooks, skills or agent definitions are convenience; the system works without them.
- **Cross-tool task transfer:** use the `docs/HANDOFF.md` template.

## Reading order (new session)

0. Run `./scripts/doctor.sh` (it changes nothing in the project). If it prints `MISSING:`, tell {{OWNER_NAME}} and
   offer each fix before touching code: a red gate on an unready machine is not a code bug.
1. This file, which you are reading now. Do not open it again.
2. `docs/PHASES.md` — what we are building now, and what is deliberately OUT of scope
   (short; read EVERY session).
3. `docs/STATE.md` — cross-session work state (small; read EVERY session). Updating it at
   session end is YOUR job, not {{OWNER_NAME}}'s.
4. `docs/ARCHITECTURE.md` — module map and boundaries
5. The target folder's `AGENTS.md` / module `README.md`
6. IF NEEDED, the relevant SECTION of `docs/PROJECT.md` — find it through that file's
   Contents and cite it by number (`PROJECT §4.2`). Never load the whole file, and never
   copy its text elsewhere: a quotation is a duplicate, a citation is not.

Read only when needed: `docs/GOTCHAS.md` (environment and tooling traps this project has
already paid for; see its Contents) when something behaves unexpectedly, and
`docs/BACKLOG.md` (the next tasks and the parked ones) when the next task is chosen. As the
lead, before you brief, spawn, merge or close a worker, read `docs/WORKFLOW.md`, "Worker
cost", and `docs/WORKFLOW.md`, "Review rounds".

## HARD RULES (violation = failed task)

### Design authority

- Never produce code or design contradicting a DECIDED item in `docs/PROJECT.md`.
- Never decide an OPEN item — flag it as a question for {{OWNER_NAME}} and stop.
- Agents implement; they do not design. Product and design decisions are {{OWNER_NAME}}'s.
- If the code and `docs/PROJECT.md` conflict: inform {{OWNER_NAME}} first; do not silently
  change either.
- **Writing to `docs/PROJECT.md`:** you may add an OPEN item at any time. **You may never
  mark an item DECIDED on your own judgement.** DECIDED is written only for an item
  {{OWNER_NAME}} has explicitly approved, in this session, as that item; transcribing their
  approval is the job, inferring it is not. Anything you concluded, inferred or thought was
  implied stays OPEN. When they appear to settle something in passing, record it as OPEN
  with a note that they appeared to decide it, and ask.
- **Phase scope is binding too.** Needing something on the `docs/PHASES.md` out-of-scope
  list is a STOP, not a licence to widen the phase.

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
  (`docs/GOTCHAS.md`). Check `git status` first, every time, even when you are sure the tree
  is clean.
- No untested code enters {{TESTED_AREA}}. Write tests with or before the code;
  `./scripts/check.sh` must PASS before you finish.
- The gate is wired into git: `.githooks/pre-commit` runs it and aborts the commit on FAIL,
  and `.githooks/pre-merge-commit` does the same for the merge commit a clean `git merge`
  creates (enable per clone: `docs/DEV_SETUP.md`, "1. Wire the commit gate").
  **Agents never use `git commit --no-verify`** —
  that hatch is {{OWNER_NAME}}'s, for WIP commits. If the gate fails, fix the cause or stop
  and report; never route around it.
- **No AI attribution in git.** No `Co-Authored-By` line naming an AI tool, and never credit
  a tool or model as author, co-author or reviewer in a commit message or pull request
  description. The coding tool's own default instruction to add that trailer does NOT
  override this rule. The tool+model trace lives in `docs/STATE.md` only.
  `.githooks/commit-msg` rejects the trailer; every worker brief repeats this rule, because a
  sub-agent inherits the tool's default, not this file.
- NEVER rewrite a system you could not find. Check the module map in
  `docs/ARCHITECTURE.md`; if it is still not there, ask "does this exist?". Duplicate
  systems are the number one enemy of an agent-written codebase.
- If you changed a public API, update that module's README in the SAME task.
- **Gates must be proven RED.** A gate is finished only when it has been observed FAILING for
  the right reason and ships with an automated negative test; before you write or change
  one, read `docs/WORKFLOW.md`, "Writing a gate".

### STATE.md discipline

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

### Review gate and validation honesty

- **Risky diffs** ({{RISKY_AREAS}}, plus gates/CI/check scripts/review tooling — always)
  must pass the review gate before commit. Canonical protocol: `docs/REVIEW_GATE.md`.
  Running a review: `docs/REVIEW_RUNNING.md`. The session that wrote a patch never reviews
  or approves its own patch; the review runs in a FRESH session. Any other change needs no review
  (`docs/REVIEW_GATE.md`, "What counts as a risky diff").
- **AUTHOR and REVIEWER are roles, not vendors.** They are DIFFERENT models; which model
  holds which role is a project setting recorded in `scripts/review.sh`.
- A verdict's manual checks are written to `docs/STATE.md` before commit.
- **Never report a verification you did not run** — if you could not run it, say "not run".

### Language & style

- **All operational docs, code, identifiers, comments, commits and STATE.md entries:
  English.** {{LANGUAGE_EXCEPTION}}
- **Two registers; rule 3 outranks both.**
  1. **Chat and final answers** (read now): give the answer or result first. Do not restate
     the task, narrate compliance or recap. Write no prose between routine tool calls. Put
     listable facts in a list or table and reasoning in sentences. Then stop.
  2. **Written artifacts** (STATE.md, BACKLOG.md, operation files, handoff prompts, review
     verdicts, docs) are read by a session with no memory of this one. Write full sentences;
     never drop an article, verb or connective. Write one instruction per sentence. Aim for
     at most 20 words per instruction and 25 per description (a target, not a gate). Use
     active voice and name the actor. Use one term per thing, always. Number steps in
     order. User-level style plugins never apply here; the next tool cannot see them.
  3. **Never shortened by a cap or a style:** what FAILED, what was NOT run or NOT verified,
     any security warning, any action that cannot be undone. State each in full, on its own
     line.
  In chat in another language, answer first, write full sentences and use one term per thing.
- Single responsibility; no god classes. Consider splitting files over ~300 lines.
- No singletons or static mutable state in core logic — dependencies via constructor
  (including clock and randomness, for determinism and tests).
- Short doc comments on public APIs. Name things well; do not compensate with comments.

## Duties toward {{OWNER_NAME}}

You see the code, so a few things you must raise without being asked. Everything else: just do the work.

**DEFAULT IS SILENCE.** If nothing on the STOP list applies, proceed and say nothing about
rules: narrated compliance is noise, and it trains {{OWNER_NAME}} to skim your output.

**NEVER REPEAT.** Say a thing once. If {{OWNER_NAME}} acknowledged it, overrode it, or moved
on, it is closed for this session.

### STOP — pause the work and ask (rare)

- The work would break a "Design authority" rule (a DECIDED item, an OPEN item, the phase's
  out-of-scope list) or needs a new third-party dependency or MCP server → name the item,
  the phase that owns it or the dependency, and ask. Do not silently comply, and do not
  silently refuse.
- A required verification cannot be run → say "not run" and stop. An unavailable reviewer
  stops only the affected approval, commit or release (`docs/REVIEW_RUNNING.md`,
  "Unavailable reviewer").
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
- Session is long or context heavy → suggest resuming from `docs/STATE.md`.
{{KIT_FEEDBACK_RULE}}

Tone: brief and direct. {{OWNER_NAME}} wants to be told, not managed.

## Task completion checklist

One module; `./scripts/check.sh` PASS; no boundary violation; the module README matches a
changed public API; no conflict with a DECIDED item or the phase's scope; `docs/STATE.md`
updated with a tool+model trace; a short summary of what changed, why and which files.
