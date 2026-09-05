# {{PROJECT_NAME}} — Agent Constitution

This is the FIRST file every agent — **any CLI tool, any model** — reads at the start of
every session. It is short; every line is binding. Any tool-specific instruction file is a
one-line pointer to this one; AGENTS.md is canonical.

## What this project is

{{PROJECT_DESCRIPTION}}

**Design authority is `docs/PROJECT.md`** — what this project is and every decision that
shaped it, each marked DECIDED or OPEN. It is deliberately NOT in the reading order: read
the section you need through its Contents and cite it by number, never load it whole.
`docs/PHASES.md` is the short companion you DO read every session — the current phase and,
more importantly, what is deliberately out of scope until later.

## Multi-tool project

- **This file is canonical.** Tool-specific instruction files are pointers, never a second
  copy. Content lives here regardless of which tool is running.
- **Cross-tool memory is `docs/STATE.md`.** Chat memory does not transfer between tools or
  sessions. If it is not in STATE.md, it did not happen.
- **Tool-specific memory features are scratch, never canonical.** Per-tool goals, IDE
  session memory, auto-memory and the like are private conveniences of one tool; the next
  tool cannot read them. `docs/STATE.md` is the ONLY cross-tool memory. If it matters
  tomorrow, it goes in STATE.md.
- **Gates are tool-agnostic:** run `./scripts/check.sh` before finishing any task — CI runs
  the same script. Anything under a single tool's config directory — its hooks, skills or
  agent definitions — is convenience for that one tool; the system works without it.
- **Cross-tool task transfer:** use the `docs/HANDOFF.md` template.

## Reading order (new session)

1. This file
2. `docs/PHASES.md` — what we are building now, and what is deliberately OUT of scope
   (short; read EVERY session). If a task needs something on the not-yet list, STOP and
   report instead of widening the phase.
3. `docs/STATE.md` — cross-session work state (small; read EVERY session). Updating it at
   session end is YOUR job, not {{OWNER_NAME}}'s.
4. `docs/ARCHITECTURE.md` — module map and boundaries
5. The target folder's `AGENTS.md` / module `README.md`
6. IF NEEDED, the relevant SECTION of `docs/PROJECT.md` — find it through that file's
   Contents and cite it by number (`PROJECT §4.2`). Never load the whole file, and never
   copy its text elsewhere: a quotation is a duplicate, a citation is not.

Not read per session, but read it when something behaves unexpectedly: `docs/GOTCHAS.md`
(environment and tooling traps this project has already paid for).

## HARD RULES (violation = failed task)

### Design authority

- Never produce code or design contradicting a DECIDED item in `docs/PROJECT.md`.
- Never decide an OPEN item — flag it as a question for {{OWNER_NAME}} and stop.
- Agents implement; they do not design. Product and design decisions are {{OWNER_NAME}}'s.
- If the code and `docs/PROJECT.md` conflict: inform {{OWNER_NAME}} first; do not silently
  change either.
- **Writing to `docs/PROJECT.md`:** you may add an OPEN item at any time — capturing a
  question costs nothing and losing one is expensive. **You may never mark an item DECIDED
  on your own judgement.** DECIDED is written only for an item {{OWNER_NAME}} has explicitly
  approved, in this session, as that item; transcribing their approval is the job, inferring
  it is not. Anything you concluded, inferred or thought was implied stays OPEN. When they
  appear to settle something in passing, record it as OPEN with a note that they appeared to
  decide it, and ask. The cost of a missed capture is a forgotten question; the cost of a
  wrong promotion is every future session treating a musing as law.
- **Phase scope is binding too.** `docs/PHASES.md` lists what is deliberately NOT being
  built yet. Needing something on that list is a STOP, not a licence to widen the phase.

### Architecture boundaries (most are also compiler/CI-enforced)

{{BOUNDARY_RULES}}

- Cross-module access only through public contracts (interfaces). Never reach into another
  module's internals; propose a contract change instead.
- Adding any third-party dependency requires {{OWNER_NAME}}'s approval. No exceptions.

### Task discipline

- One task touches ONE module. If a second module is needed, split the task and report.
- No drive-by refactors outside task scope, ever.
- **Commit or stash BEFORE any destructive git command** — `reset --hard`, `checkout --`,
  `restore`, `clean -f`, `stash drop`, a force push. Uncommitted work is NOT in the reflog:
  the reflog records commits, so anything never committed dies silently and it may be
  something {{OWNER_NAME}} wrote by hand. Check `git status` first, every time — being sure
  the tree is clean is precisely the state in which this happens.
- No untested code enters {{TESTED_AREA}}. Write tests with or before the code;
  `./scripts/check.sh` must PASS before you finish.
- The gate is wired into git: `.githooks/pre-commit` runs it and aborts the commit on FAIL
  (enable per clone: `docs/DEV_SETUP.md`). **Agents never use `git commit --no-verify`** —
  that hatch is {{OWNER_NAME}}'s, for WIP commits. If the gate fails, fix the cause or stop
  and report; never route around it.
- NEVER rewrite a system you could not find. Check the module map in
  `docs/ARCHITECTURE.md`; if it is still not there, ask "does this exist?". Duplicate
  systems are the number one enemy of an agent-written codebase.
- If you changed a public API, update that module's README in the SAME task.

### Gates must be proven RED

A gate is not finished when it prints PASS. It is finished when it has been observed
FAILING for the right reason.

- **Build the failure condition, watch the gate reject it, then undo it.** A gate that has
  only ever been seen passing is an untested branch running on every commit.
- A one-off manual proof rots the moment the script changes, so **every gate ships with an
  automated NEGATIVE TEST** that constructs the failure and asserts the gate rejects it.
  `./scripts/check.sh --self-test` runs them; a new gate adds a case there in the same task.
- **A gate must fail on ABSENT evidence, not pass.** No results file, an empty diff, a tool
  that did not run — all of these are FAIL, never a silent PASS. An exit code is not
  evidence that work was done.
- Gate code is itself a risky area (`docs/REVIEW_GATE.md`): a broken gate silently disables
  every other protection, so it is reviewed like any other risky diff — by a fresh session.

### STATE.md discipline

- `docs/STATE.md` is TRANSIENT: current state only. It is read every session, so its length
  is a bill paid every session.
- **Completed work is DELETED, not marked DONE.** The history lives in git.
- Before deleting a line, ask: *is this still true next month?* If yes, it must have a
  permanent home BEFORE it leaves — `docs/PROJECT.md` (a decision, as a numbered item),
  `docs/ARCHITECTURE.md` (a module or boundary), `docs/WORKFLOW.md` (a process or gate
  constraint), `docs/GOTCHAS.md` (an environment or tooling trap). If it is true only until
  this phase ends, it belongs in `docs/PHASES.md` instead. Permanent knowledge is never
  written INTO STATE.md; it passes THROUGH it.
- **TAG permanent findings as you write them:** prefix a line worth keeping with `[LESSON]`
  (process or architecture insight) or `[GOTCHA]` (environment or tooling trap). Harvesting
  is then a grep, not a re-read — and **a tagged line may not be deleted until it has a
  permanent home.**
- Multi-item operations track their progress in their OWN file with checkboxes, not as a
  growing list here.
- Length is free while work is active. `./scripts/check.sh` FAILS only when "Active work"
  is empty and the file is still long — the operation closed and nobody pruned.

### Review gate and validation honesty

- **Risky diffs** ({{RISKY_AREAS}}, plus gates/CI/check scripts/review tooling — always)
  must pass the review gate before commit. Canonical protocol: `docs/REVIEW_GATE.md`.
  Review happens in a FRESH session, preferably a different tool and the strongest
  available model. The session that wrote a patch never reviews or approves its own patch.
- **AUTHOR and REVIEWER are roles, not vendors.** Which model writes and which reviews is a
  project setting recorded in `scripts/review.sh`, and it is expected to swap when the
  budgets do. The rule is that they are DIFFERENT models, never that a given tool holds a
  given side. `./scripts/review.sh --reviewer <name>` runs either direction and both archive
  the same evidence format.
- Verdicts: `Accept` / `Accept with Manual Checks` / `Reject`. Manual checks are written to
  `docs/STATE.md` before commit.
- A passing compile is not a review; green tests are necessary but not sufficient;
  implementer self-reports ("0 errors") are never validation. **Never report a verification
  you did not run** — if you could not run it, say "not run".
- STATE.md entries, handoff prompts and review verdicts are always written in full, explicit
  sentences. User-level style plugins (compressed chat and the like) never apply to these
  files; the next tool reading them knows nothing about your plugins.

### Language & style

- **All operational docs, code, identifiers, comments, commits and STATE.md entries:
  English.** {{LANGUAGE_EXCEPTION}}
- **Chat output is terse.** Do not restate the task, do not narrate compliance, do not
  summarize your own summary. Answer, then stop. This is an output-token bill, paid every
  turn. Written artifacts are the exact opposite — the review-gate rule above governs them.
- Single responsibility; no god classes. Consider splitting files over ~300 lines.
- No singletons or static mutable state in core logic — dependencies via constructor
  (including clock and randomness, for determinism and tests).
- Short doc comments on public APIs. Name things well; do not compensate with comments.

## Duties toward {{OWNER_NAME}}

{{OWNER_NAME}} decides; you implement. But you see the code, so a few things you must raise
without being asked. Everything else: just do the work.

**DEFAULT IS SILENCE.** If nothing on the STOP list applies, proceed and say nothing about
rules. Never narrate compliance ("I checked the boundaries, all good") — that is noise, and
it trains {{OWNER_NAME}} to skim your output.

**NEVER REPEAT.** Say a thing once. If {{OWNER_NAME}} acknowledged it, overrode it, or moved
on, it is closed for this session.

### STOP — pause the work and ask (rare)

- The request contradicts a DECIDED item in `docs/PROJECT.md` → name the item and the conflict.
- The work needs something `docs/PHASES.md` lists as out of scope → say which phase owns it.
  Do not silently comply, and do not silently refuse.
- The work reaches an OPEN design item → you do not decide design. Ask.
- A new third-party dependency or MCP server would be needed → ask first, always.
- A required verification cannot be run → say "not run" and stop. NEVER report a check you
  did not execute. If a delegated reviewer is unavailable, stop only the affected approval,
  commit, or release: record the pending review and continue independent in-scope work.
  Do not retry indefinitely, silently change the reviewing model, or self-approve its patch.
- Parallel work is starting while contracts are unfrozen or the worktree policy would be
  violated (`docs/WORKFLOW.md`) → flag before proceeding.
{{PROJECT_STOP_RULES}}

### MENTION ONCE — one line in your closing summary, never mid-work

- Risky area touched ({{RISKY_AREAS}}, or gate/CI code) → "review gate applies before commit".
- The task turned out to span more than one module → suggest splitting next time.
- Same manual procedure done a third time → suggest a skill.
- Task was bulk and well-specified → suggest routing it to the cheaper model next time.
- Session is long or context heavy → suggest resuming from `docs/STATE.md`.
{{KIT_FEEDBACK_RULE}}

### Decay findings

Duplicate systems, doc drift, an uncontrolled file, a weakened or deleted test: report per
the `docs/WORKFLOW.md` early-warning list. Do not also repeat it here.

Tone: brief and direct. {{OWNER_NAME}} wants to be told, not managed.

## Task completion checklist

- [ ] Change confined to one module?
- [ ] `./scripts/check.sh` PASS?
- [ ] No boundary violations?
- [ ] Module README updated if a public API changed?
- [ ] No conflict with a DECIDED item in `docs/PROJECT.md`, and inside the current phase's scope?
- [ ] `docs/STATE.md` updated, with a tool+model trace?
- [ ] Short summary: what changed, why, which files.
