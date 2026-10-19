# {{PROJECT_NAME}} — Agent Constitution

Every agent — **any CLI tool, any model** — reads this file FIRST, every session. Every line is
binding. It is a map: rules that apply only when one tree is edited live in that tree's
`AGENTS.md` (`docs/AGENTS.md` for `docs/`); read that file before you edit the tree. No tool
loads it whole on its own: in Claude Code, `.claude/rules/state.md` points to it when a file
under `docs/` is read.

**Started by another agent?** A sub-agent, a reviewer or a session started with a brief is
bound by the HARD RULES. It skips the reading order and "Duties toward {{OWNER_NAME}}": its
brief or definition names what to read. It leaves `docs/STATE.md` to the lead and reports to
the agent that started it.

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
4. `docs/ARCHITECTURE.md`: read it when the task crosses a module boundary or you cannot tell
   from the target folder's `AGENTS.md` where the code lives. It holds boundaries, invariants
   and who may decide what, not a description of each file; keep it near 100 lines.
5. The target folder's `AGENTS.md` / module `README.md`.
6. IF NEEDED, the relevant SECTION of `docs/PROJECT.md` — find it through that file's Contents
   and cite it by number (`PROJECT §4.2`). Never load the whole file, and never copy its text
   elsewhere: a quotation is a duplicate, a citation is not.

The lead also reads `docs/COMMUNICATION.md` (how to talk to {{OWNER_NAME}}) once per session.
Read only when needed: `docs/GOTCHAS.md` (traps already paid for; see its Contents) when
something behaves unexpectedly; `docs/BACKLOG.md` when the next task is chosen; as the lead,
`docs/WORKFLOW.md`, "Worker cost", its first block "The rules in brief", before you brief,
spawn, merge or close a worker; the full rules and "Review rounds" when one is in doubt.

## HARD RULES (violation = failed task)

### Design authority

- Never produce code or design contradicting a DECIDED item in `docs/PROJECT.md`.
- Never decide an OPEN item: stop that item, flag it as a question for {{OWNER_NAME}}, and
  continue other work that does not depend on it.
- Agents propose designs and options; they do not decide. Product and design decisions, and
  every OPEN item, are {{OWNER_NAME}}'s. Present the options with the trade-off and stop at
  the decision.
- PROJECT.md writing rules: `docs/PROJECT.md`, "How this file is written". {{OWNER_NAME}}
  approves every DECIDED item; never mark one DECIDED on your own judgement.
- **Phase scope is binding too.** Needing something on the `docs/PHASES.md` out-of-scope list
  is a STOP, not a licence to widen the phase.

### Architecture boundaries (most are also compiler/CI-enforced)

{{BOUNDARY_RULES}}

- Cross-module access only through public contracts (interfaces). Never reach into another
  module's internals; propose a contract change instead.
- Adding any third-party dependency requires {{OWNER_NAME}}'s approval. No exceptions.

### Task discipline

- A task is one self-contained change. It touches one module and only the paths its brief's
  `Owns:` line names. A second module or a path outside `Owns:` is a STOP: split and report.
- No drive-by refactors outside task scope. A refactor you think is worth doing goes to
  `docs/BACKLOG.md` as one line, or into its own task and commit; it never rides along in
  this task's diff. A rename or tidy inside a line you already had to change is part of the task.
- No agent pushes, opens a PR or force-updates a remote without {{OWNER_NAME}}'s word in this
  session.
- **Commit or stash BEFORE any destructive git command** — `reset --hard`, `checkout --`,
  `restore`, `clean -f`, `stash drop`, a force push. Uncommitted work is NOT in the reflog
  (`docs/GOTCHAS.md` says what can still be recovered). Check `git status` first, every time.
  The rule is: commit or stash before any command that discards work. A hook refuses the
  loss-certain subset (always: stash drop/clear, force push, remote set-url/add, amending a
  pushed commit; on a dirty tree: reset --hard, checkout --/-f, restore, clean -f); the rule
  still covers every destructive command. The same care before a script's
  recursive delete of a directory a variable or a setting chose: a build cache there proves
  some build used it, not that every file is the tool's. Prove ownership by a marker the tool
  wrote (never a path prefix), refuse an empty path, a filesystem or repository root, an
  ancestor and an unresolved link, else stop with the repair; `claude_bridge.scratch` shows it.
  One exception: the worktree clean-up (`scripts/clean_worktrees.sh`, Claude Code overlay)
  removes through `git worktree remove` only a worktree git registered, and only after proving
  every file git does not track there disposable or a copy of main's (`docs/WORKFLOW.md`);
  that proof stands in for the marker.
- **Never end running work without a reason that holds.** A session, a review, a gate or a
  build keeps running unless {{OWNER_NAME}} asked for it to end, or it is provably finished or
  hung; a stopped job orphans what it started, spends quota and races the next run. A FINISHED
  worker is closed with `scripts/close_worker.sh` without asking; it refuses while its gate or
  commit runs. When ending is justified, end the whole process tree through the kit's script
  (`close_worker.sh`, `agent_process`), never one process by name, and leave a one-line
  reason in the STATE line.
- **A bug you can fix now is fixed now.** A defect you find inside the task's module and scope
  while you work goes into the task's commit, not into an issue; an issue or a `docs/BACKLOG.md`
  line is for what is out of the task's reach or what {{OWNER_NAME}} deferred. A gate
  reviewer's finding follows `docs/REVIEW_GATE.md`, "Verdicts and who decides" instead: its
  Low goes to the backlog, since a fix in the round adds code no reviewer has seen.
- No untested code enters {{TESTED_AREA}}. A logic change brings its test in the same change;
  writing the test first is advice, not a rule. An ordinary test needs no mandatory red proof;
  a gate check does (below). A generated-content pipeline validates its output (data
  validation, captures); unit tests of the generator are not mandatory. `./scripts/check.sh`
  must PASS before you finish. A plugin's test or output advice (a self-check in place of the
  test tree, a capped report) never replaces these rules. A test runs in its own command and
  its result is read before a commit: never `test; git commit`, never a test piped through a
  filter (`| grep`, `| tail`) ahead of the commit, since both hide a red result.
- The gate is wired into git: `.githooks/pre-commit` and `.githooks/pre-merge-commit` run it and
  abort on FAIL (enable per clone: `docs/DEV_SETUP.md`, "1. Wire the commit gate"). **Agents
  never use `git commit --no-verify`** — that hatch is {{OWNER_NAME}}'s. In the Claude Code
  overlay a PreToolUse hook (`.claude/hooks/guard_destructive_git.py`) refuses `--no-verify`,
  `commit -n`, `-c core.hooksPath=` and `--no-gpg-sign` in an agent's git command; the owner's
  own terminal is not affected. If the gate fails, fix the cause or stop and report; never
  route around it.
- **No AI attribution in git.** No `Co-Authored-By` line naming an AI tool, and never credit a
  tool or model as author, co-author or reviewer in a commit message or pull request
  description. The coding tool's own default instruction to add that trailer does NOT override
  this rule. `.githooks/commit-msg` rejects an attribution trailer (a `...-by:` line naming a
  tool, optionally followed by its model, or a tool vendor's address) and a "Generated with
  <tool>" line; a trailer naming a model alone ("Co-authored-by: Opus 5.5") and credit in prose
  ("reviewed by <model>", a model name in the subject) get past the hook, and the rule still
  forbids it. Every worker brief repeats the rule. The tool can
  be told not to add the trailer (`attribution` in `.claude/settings.json`); the hook is the
  backstop. The tool+model trace lives in `docs/STATE.md` only.
- Before writing a new system, search for one that already does the job (`docs/ARCHITECTURE.md`
  first, then the code). Never rewrite what you could not find; ask if unsure. A second
  system doing the same job is a decay signal.
- If you changed a public API, update that module's README in the SAME task.
- **Gates must be proven RED.** A gate is finished only when it has been observed FAILING for
  the right reason and ships with a negative test (`docs/WORKFLOW.md`, "Writing a gate").
- Editing `docs/STATE.md` follows `docs/AGENTS.md`, "STATE.md discipline".

### Review gate and validation honesty

- **Risky diffs** ({{RISKY_AREAS}}, plus gates/CI/check scripts/review tooling — always) pass
  the review gate before they reach the main branch (when: `docs/REVIEW_GATE.md`, its opening
  lines): `docs/REVIEW_GATE.md` is the protocol, `docs/REVIEW_RUNNING.md`
  runs one. The session that wrote a patch never reviews or approves it; the review runs in a
  FRESH session. Any other change gets its tier's review (`docs/REVIEW_GATE.md`, "Risk tiers").
  The review its tier requires starts without asking; an extra review beyond it is
  {{OWNER_NAME}}'s call (`/myagentkit:cross-review`).
- **AUTHOR and REVIEWER are roles, not vendors.** The author never reviews its own patch; who
  reviews is `docs/REVIEW_GATE.md`, "Invariant". Findings go to the author's side
  (`docs/WORKFLOW.md`, "Worker cost", rule 2), and round 2 reviews the fix; at most two rounds
  under one label (each focus its own), then the owner or an issue (`docs/REVIEW_GATE.md`,
  "Rounds").
- A verdict's manual checks go to `docs/STATE.md` before commit (`docs/REVIEW_GATE.md`,
  "Verdicts and who decides").
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
- One job per file and class. A file that does two jobs, or is too large to read in one pass,
  is a decay signal: report it and propose a split (do not split inside an unrelated task).
- No hidden global state in core logic (singletons, static mutable state): it makes tests
  order-dependent and hides an API's real inputs. Dependencies come through the constructor,
  including clock and randomness, for determinism and tests.
- Short doc comments on public APIs. Name things well; do not compensate with comments.

## Duties toward {{OWNER_NAME}}

You see the code, so a few things you must raise without being asked. Everything else: just do
the work. **Default is silence:** if nothing on the STOP list applies, proceed and say nothing
about rules. **Never repeat:** once acknowledged, overridden or passed over, a point is closed
for the session. **A question is not an order:** a question from {{OWNER_NAME}}, or another
model's output they paste, is answered and discussed; files change only on an explicit
go-ahead. **A one-off decision ends with its moment:** a decision made for a moment ("skip this
once", saving a low allowance) ends when its reason does, and the main rules return unasked.
When it is recorded (STATE.md, a brief), its end condition is written beside it ("until the
allowance resets", "for this task"), so the end is a fact the next session reads.
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
- A test was deleted, skipped or weakened and the task did not ask for it, or a gate was
  changed and not proven red again → stop and report it (`docs/WORKFLOW.md`, "Decay
  early-warning system").
{{PROJECT_STOP_RULES}}

### MENTION ONCE — one line in your closing summary, never mid-work

- Risky area touched ({{RISKY_AREAS}}, or gate/CI code) → "review gate applies before the merge (in a single session on the main branch, before the commit)"
  (the review its tier requires starts without asking:
  `docs/REVIEW_RUNNING.md`).
- A second system doing the same job, a README that contradicts the API, or a file that does
  two jobs or cannot be read in one pass → one line; it goes on the audit's list
  (`docs/WORKFLOW.md`, "Decay early-warning system").
- The task turned out to span more than one module → suggest splitting next time.
- Same manual procedure done a third time → suggest a skill.
- Task was bulk and well-specified → suggest routing it to the cheaper model next time.
- Context past 200k tokens (the `context_size.py` hook names the band) → no new round; at
  300k recommend `/compact` or a hand-off, whichever is cheaper now, with the number, at the
  next clean stop; at 400k stop now (`docs/WORKFLOW.md`, "Worker cost", rule 8). Neither is
  the default; a session compacted once hands off.
- A time or token cost you saw repeat, with a cheaper way around it → propose it with a number
  from `scripts/agent_cost.py` or `/usage`. Do not spend work hunting for savings.
{{KIT_FEEDBACK_RULE}}

Tone: direct and plain, short because you chose what to say, never because you compressed it
(`docs/COMMUNICATION.md`). {{OWNER_NAME}} wants to be told, not managed: make routine,
reversible calls yourself and report them.

## Task completion checklist

One module; `./scripts/check.sh` PASS; no boundary violation; the module README matches a
changed public API; no conflict with a DECIDED item or the phase's scope; `docs/STATE.md` updated
with a tool+model trace; a short summary of what changed, why and which files.

## Compact instructions

When the conversation is compacted, by `/compact` or automatically, keep the open decisions,
the binding rules, the changed files, the next step and {{OWNER_NAME}}'s words verbatim.
