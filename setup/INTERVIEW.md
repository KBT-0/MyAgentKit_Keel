<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->

# SETUP INTERVIEW — read this, then run it

You are a CLI coding agent. Someone just installed a project foundation kit into this
repository and asked you to set it up. This file is the whole procedure. It assumes you know
nothing else, and it does not depend on any conversation that happened before you read it.

**What was installed.** A set of instruction files, gates and templates that make a
repository safe for agents to work in over a long time: a constitution (`AGENTS.md`), a
workflow (`docs/WORKFLOW.md`), a review protocol (`docs/REVIEW_GATE.md`), a cross-session
memory file (`docs/STATE.md`) with its backlog (`docs/BACKLOG.md`), a task-handoff
template (`docs/HANDOFF.md`), a trap log (`docs/GOTCHAS.md`), a quality gate
(`scripts/check.sh`) wired into git as a pre-commit hook, and a cross-model review wrapper
(`scripts/review.sh`).

**What is missing.** Everything project-specific. The files are full of `{{PLACEHOLDER}}`
markers, and `./scripts/check.sh` FAILS while any of them survive. Your job is to have a
real conversation with the owner, and then fill every one of them with an answer they
actually gave.

---

## Rules for how you run this

These override any habit you have about being efficient.

1. **One topic per turn. Never dump all the questions at once.** A wall of questions gets a
   wall of shallow answers, and shallow answers become rules nobody believes in three weeks.
2. **Wait for the answer.** Do not propose and immediately assume. Do not move on because
   the answer seems obvious to you.
3. **Do not invent answers.** If the owner is unsure, explain the tradeoff in two sentences,
   say what you would pick and why, and let them decide.
4. **Record the RATIONALE for every decision.** A rule without its reason gets deleted six
   months later by someone who cannot see what it was protecting. When you write a rule into
   a file, write the reason next to it.
5. **Anything the owner did not explicitly approve is OPEN, not DECIDED.** Never record a
   decision they merely failed to object to.
6. **Never claim you ran something you did not run.** If a command could not be executed,
   say "not run". This rule is in the constitution you are installing; break it here and the
   whole thing is theatre.
7. **Ask, do not assume, about scale.** A solo hobby project and a five-person team need
   different answers to the same questions, and the kit's defaults lean solo.

---

## Phase 0 — the owner's note

If `docs/kit/BOOTSTRAP_NOTE.md` exists, read it FIRST. It is the owner's agenda for this
setup, written when they ran the installer: a tool they want added, a model they want to
try, a problem they hit last time.

Address every item in it explicitly during the interview. If you end up not doing something
it asks for, say so out loud and say why. Silently ignoring it is the one failure mode this
phase exists to prevent.

If the file does not exist, move on without comment.

## Phase 0.5 — one question about the kit itself

Ask this BEFORE the research pass, because that pass is the first thing that could produce
something worth sending upstream. Ask it plainly, and do not oversell it:

> "This foundation keeps learning inside your project either way — the research pass we are
> about to run, the traps we hit later, all of that gets written into your own docs for your
> own benefit, and none of it leaves this machine.
>
> Separately: some of what we learn is about the KIT rather than about this project. Do you
> want me to occasionally offer to send those bits upstream to MyAgentKit_Keel as an issue or a
> PR? You would see the exact text first, with everything about this project stripped out,
> and nothing is ever sent without you saying yes.
>
> If you would rather I never bring it up, that is a completely normal answer — the command
> `/myagentkit:kit-feedback` stays available for whenever you feel like it, and I just stay
> quiet about it otherwise."

Be accurate about what this is. There is **no collection and no telemetry**: nothing is
gathered anywhere except this project's own `RESEARCH_LOG.md` and docs, nothing is
transmitted without the owner reading the full body first, and the answer here changes only
whether the agent OFFERS. Do not present it as a data or privacy setting — describing it as
scarier than it is would be its own kind of dishonesty.

Then fill `{{KIT_FEEDBACK_RULE}}` in `AGENTS.md` with exactly ONE of the two bullets below,
whole and unedited.

**If yes:**

> - **Something about the FOUNDATION itself was wrong, unclear or missing** — a gate that
>   failed open, a rule that did not survive contact with real work, an ambiguous setup
>   instruction, a document contradicting itself → offer to send it upstream with
>   `/myagentkit:kit-feedback`. It scrubs this project out, shows the exact text, and sends
>   nothing without a yes. Offer ONCE per finding, take no for an answer, never send on your
>   own initiative. Keep it light: a footnote in a closing summary, not a campaign.

**If no:**

> - **Never offer to report anything upstream to the kit.** The owner declined this at
>   setup. Keep writing what we learn into this project's own docs exactly as before — that
>   half is unchanged. If they ever want to send something, they will run
>   `/myagentkit:kit-feedback` themselves.

Record the answer as a DECIDED row in `docs/PROJECT.md` either way, so a later session knows
it was asked and answered instead of asking again.

## Phase 1 — ecosystem research

Run `setup/RESEARCH_PROTOCOL.md` now, before the project questions, so that any tooling you
recommend later is current rather than remembered.

**If you have no web access, say so plainly and skip this phase.** Do not improvise "what's
new" from training data — you cannot tell how stale it is, and invented ecosystem news is
strictly worse than an honest gap. Note the skip in `RESEARCH_LOG.md` if that file is
present.

Present findings one at a time, each with its COST as well as its benefit. The default
verdict is REJECT. The owner approves or rejects each one.

## Phase 2 — the project interview

One topic per turn. Suggested order, because each answer informs the next:

1. **What is this project, in one paragraph, and who is it for?** You will paste a tightened
   version of their answer into the constitution, so get it concrete.
2. **Stack and shape.** Languages, runtime, build tool, test runner. Is there an engine, a
   server, a database, a mobile client? What does "run the tests" mean here, as a command?
3. **The risky areas — where does a silent bug cost the most?** This is the single most
   project-specific decision in the whole setup: it becomes the trigger list for the review
   gate. Push for specifics. "The payment flow" is useful; "the backend" is not. Ask what
   would be hardest to notice, hardest to attribute, and hardest to undo.
4. **Hard boundaries.** What must never depend on what? Which of those can be enforced by a
   compiler, a project reference, or a grep — rather than by prose in a document? Every
   boundary you can enforce becomes a check in `scripts/check.sh`; every one you cannot,
   note honestly as unenforced.
5. **Gates.** What exists today and what should: build, tests, lint, type check, engine
   tests, anything slow enough to be opt-in.
6. **People and tools.** Solo or a team? Which CLI agents and models, on what budget?

   Ask these three separately, because the kit needs all three and they are not the same
   question. Do not infer any of them from which tool you happen to be running in — that
   assumption is exactly what this section exists to stop:

   - **Which model is the AUTHOR?** The one that writes most of the code.
   - **Which model is the REVIEWER?** It must be a DIFFERENT model. Either direction is
     supported and neither is the "normal" one.
   - **Which budget is scarce, and which is generous?** This fills the model-routing table,
     and it is often what decides the two answers above. A capable model on a nearly
     exhausted plan makes a better reviewer than an author.

   Record the answers where the tooling reads them: the `DEFAULT_REVIEWER`, `CODEX_MODEL`
   and `CLAUDE_MODEL` values at the top of `scripts/review.sh`. **Both models must be pinned
   by name** — an unpinned reviewer archives whatever default its CLI had that day, and the
   wrapper refuses to run rather than record something no later review can be compared
   against. Say plainly that the roles can be swapped later by editing those three values,
   and that swapping them does not change the evidence format.

   Then ask specifically about **cross-model review**, because it is the one part of this
   kit that needs software the owner may not have. `scripts/review.sh` shells out to a
   SECOND CLI, and it ships with adapters for two: `--reviewer codex` and
   `--reviewer claude`. So:

   - Check which are installed: `command -v codex`, `command -v claude`. Do not assume
     either way — report what you found. If only one is present, the OTHER one is the
     reviewer only if the owner installs it; the review gate needs two.
   - If it is missing, explain the trade: without a second model, the review protocol
     becomes the paste-the-template-by-hand version in `docs/REVIEW_RUNNING.md`. That is a
     genuine fallback, and the kit works without it. With it, `/myagentkit:cross-review`
     runs the whole thing in-session.
   - **Offer to install it.** You can run the installer; the owner does the login. Say what
     you are about to run before you run it, and do not install anything they did not agree
     to — a new dependency needs their approval, which is a STOP rule in the constitution
     you are installing.
   - Mention the OPTIONAL vendor plugin for their host agent (for Claude Code and Codex:
     `openai/codex-plugin-cc`). It is NOT needed by `scripts/review.sh`; it adds in-session
     delegation and review commands. Installing it takes two slash commands that a HUMAN
     must type — you cannot invoke slash commands. Give them the exact lines and say so
     plainly rather than implying you handled it:
     ```text
     /plugin marketplace add openai/codex-plugin-cc
     /plugin install codex@openai-codex
     ```
     The repository is `openai/codex-plugin-cc`, but its declared marketplace name is
     `openai-codex`; installation uses the marketplace name after `@`. Do not derive it
     from the repository name. `docs/DEV_SETUP.md` has the same pair and the cautions about
     model-invocable commands and automatic review gates.
   - For a Codex host, offer the kit's Codex plugin and its Claude review/delegation skills
     (`docs/CODEX.md` in the kit). `--reviewer claude` selects the Claude adapter from any
     host; `REVIEW_CLI_BIN` and `CLAUDE_CLI_BIN` change only which binary is launched. Any
     THIRD CLI still needs a separately implemented and live-validated adapter, not merely a
     binary substitution — `--reviewer` deliberately accepts only the two names it has
     adapters for.
   - In-session delegation is NOT symmetric between the two hosts. Read
     `docs/delegation-is-not-symmetric.md` before promising it in either direction; the
     script-based review gate works from both, which is the part the kit guarantees.
7. **What is the FIRST phase, and what is deliberately not in it?** Not the whole plan —
   the one question the project should answer first, and the things that are tempting but
   must wait. Order by risk: the assumption that would hurt most if it turned out wrong goes
   first, even when it is not the foundation.

8. **Will workers run jobs longer than five minutes?** A build, a bake, a test suite, a
   render, a data import — anything an agent starts and then has to wait for. Ask for the
   job names and their typical lengths, and what a worker must know BEFORE running them (a
   lock that serialises them, a memory ceiling, an environment variable, a copy step), which
   goes into the worker definition's body under its project rules. The reason: a sub-agent's prompt cache lives five
   minutes, so a worker that waits longer re-writes its whole context after every wait; in
   the kit's founding project that was 87 percent of all cache-write tokens
   (`docs/WORKFLOW.md`, "Worker cost"). If the answer is yes and the Claude Code overlay is
   installed, fill `{{WORKER_MODEL}}`, `{{WORKER_EFFORT}}` and `{{LONG_JOBS}}` in
   `.claude/agents/worker.md` with the author model, its effort (`high` when the workers'
   tasks bear design, lower when they are mechanical; without the field a sub-agent runs at
   whatever effort its lead session has) and those job names, and tell the owner that workers for such tasks are
   spawned with that definition instead of the general-purpose one. If the answer is no,
   delete `.claude/agents/worker.md` and `scripts/spawn_worker.sh` (Phase 4, "Delete what
   does not apply"). Either way the rules in that section bind the lead from day one.

9. **May AI tools be credited in commit messages?** Coding tools add a co-author trailer by
   default, and in the kit's founding project that put one into most commits against the
   owner's wish; removing it later meant rewriting every commit and a force-push. The answer
   is a hard rule in `AGENTS.md` either way. No (the default): keep the "No AI attribution
   in git" rule; `.githooks/commit-msg` enforces it. Yes: replace that rule with one saying
   AI tools may be credited; the hook keys on the rule line, so without it the hook gives
   way and `check.sh --self-test` reports its case as a `skip` naming the absent rule line
   (`AGENTS.md has no 'No AI attribution in git' rule line`). If the Claude
   Code overlay is installed, also delete the block from `<!-- BEGIN attribution rule` to
   `<!-- END attribution rule -->` in `.claude/agents/worker.md`, and tell the owner you did:
   left there, it told every worker the opposite of the owner's answer.

10. **Which folders may a finished worktree lose?** Only if the Claude Code overlay is
    installed. `.githooks/post-merge` removes a merged worker worktree (never its branch) only
    when every file git does not track in it has an identical copy in the main worktree or sits
    in a folder the project declared disposable: build output and installed dependencies a
    checkout makes again (the usual ones: `build`, `node_modules`, `dist`, `target`, `.venv`). Write the owner's
    answer into `.claude/worktree-disposable`, one name or root-relative path per line; those
    folders must also be in `.gitignore`. A name never matches below `docs`, `.claude`,
    `scripts`, `.myagentkit` or `.git`. Nothing listed is the safe default: a worktree with
    build output is then kept and its report names the folders. Keep the file even if empty:
    without it the hook does nothing. Ask too whether the quiet period suits them: a worktree
    in which anything changed in the last 60 minutes, build output included, is kept
    (`quiet-minutes=<n>` in the same file, at least 10). The reason to ask: in a project using
    the kit, merged worktrees piled up to 34 GB before anyone removed them.

11. **Should sessions and workers write code in ponytail mode? Default: yes.** Ponytail
    (`DietrichGebert/ponytail`, MIT) makes the agent climb a ladder before writing code: does
    it need to exist, is it already in the codebase, does the standard library or the
    platform do it, an installed dependency, one line, and only then the minimum code. It
    keeps input validation, error handling and security in. Cost and gain, honestly: its
    rules add about 1.3k tokens to every session start and every sub-agent start (cached, so
    a tenth of that on each later request); its own agentic benchmark on a real repository
    cut code by 60 to 94 percent on tasks with an over-build trap and was even on code that
    was already minimal, and an independent multi-turn run found it can cost more tool calls
    on large tasks that force completion. It saves most for workers that write code.
    It comes from its author's own marketplace at the latest version. Yes: keep
    `extraKnownMarketplaces` (`ponytail`) and `enabledPlugins` (`ponytail@ponytail`) in
    `.claude/settings.json` (the Claude Code overlay ships them);
    Claude Code offers the install when the folder is trusted, and spawned worker sessions
    and sub-agents get the mode with it. Its hooks need `node` on PATH. An owner who already
    enabled `ponytail@ponytail` in their user settings gets the same plugin, loaded once.
    For Codex sessions and workers, give the owner the two commands to type, then `/hooks`
    in Codex to trust its hooks:
    ```text
    codex plugin marketplace add DietrichGebert/ponytail
    codex plugin add ponytail@ponytail
    ```
    No: delete both entries from `.claude/settings.json` and say so.

## Phase 3 — PROJECT.md and PHASES.md

Both files ship as skeletons and both are LIVING documents. Do not fill them in from a
template, and do not generate plausible content to make them look complete — an agent
writing sections nobody asked for is inventing a project rather than recording one.

**`docs/PROJECT.md`** starts nearly empty and grows through conversation over the project's
whole life. In this session, write only what the owner actually told you. Interview them the
way a design partner would:

- Challenge weak ideas. Say when something contradicts something they said earlier.
- Surface contradictions rather than smoothing them over.
- Record every decision WITH its rationale — a rule without its reason gets deleted later.
- Tag each item **DECIDED** or **OPEN**. Mark DECIDED only what the owner explicitly
  approved in this session. Everything you inferred is OPEN.
- Number every `##` section and list it in the Contents. `scripts/check.sh` fails when a
  section is missing from the Contents, because selective reading is the only thing that
  keeps this file affordable as it grows.

A project with nothing settled yet gets a PROJECT.md holding one paragraph and a list of
OPEN questions. That is a correct outcome, not a failure — the file exists so that the next
decision has somewhere to land instead of dissolving into a chat log.

**`docs/PHASES.md`** gets the answer to question 7: the current phase's question, what is in
scope, what is explicitly NOT, and how anyone can tell it is done. Spend real effort on the
not-yet list; it is the half that stops an agent inventing scope, and it is the half people
skip. Later phases get ONE LINE each — detail is written when a phase becomes current.

If the owner does not know their phases yet, say so in the file and leave it. A phase
invented by an agent is worse than an empty section, because the constitution makes it
binding on everyone who comes after.

## Phase 4 — write the foundation

Now fill in the files. Work through the placeholders below; `grep -rn '{{[A-Z_]*}}' .` finds
any you missed, and the gate will find the rest.

An installed overlay brings its own placeholders, which are not in these tables — the grep
above is what catches them, and the overlay's own document explains each one.

### Identity and people

| Placeholder | What goes in |
|---|---|
| `{{PROJECT_NAME}}` | The repository's name, as it should read in a heading |
| `{{PROJECT_DESCRIPTION}}` | The one-paragraph answer from Phase 2, tightened |
| `{{OWNER_NAME}}` | Who decides. Used throughout the duties section |
| `{{LANGUAGE_EXCEPTION}}` | Empty if everything is in English. If a document is deliberately in another language, name it and say why |

### The current phase (`docs/PHASES.md`)

Read every session, so keep every one of these tight. Detail for later phases is written
when they become current, never now.

| Placeholder | What goes in |
|---|---|
| `{{CURRENT_PHASE}}` | A short name, e.g. "Phase 0 — skeleton and gates" |
| `{{PHASE_QUESTION}}` | ONE sentence: the question this phase answers, or the risk it retires. If it cannot be phrased as a question, it is a wish list, not a phase |
| `{{PHASE_IN_SCOPE}}` | What gets built, as a list. Concrete enough that "is this in scope?" has an answer |
| `{{PHASE_OUT_OF_SCOPE}}` | What is tempting and must WAIT, each naming the phase that owns it instead. Spend as much effort here as on the line above — this is the half that stops scope invention |
| `{{PHASE_ACCEPTANCE}}` | Commands or observations, never adjectives. A subjective criterion is valid only if it names WHO decides and when |
| `{{LATER_PHASES}}` | One line per phase, in order. The question each will answer, nothing more. Say "not decided yet" if that is the truth |

### Risk and review

| Placeholder | What goes in |
|---|---|
| `{{RISKY_AREAS}}` | The Phase 2 list, as specific nouns. Gates and CI are already listed permanently — do not repeat them |
| `{{TOP_RISK_PRIORITY}}` | The single worst failure mode, as the first review priority, with what makes it expensive |
| `{{REVIEWER_MODEL}}` | The strongest model available for reviews |

### Architecture

| Placeholder | What goes in |
|---|---|
| `{{RUNTIME_TOPOLOGY}}` | A small diagram plus one line per process: what it is, what authority it has |
| `{{REPO_LAYOUT}}` | The folder tree with one line each. Only real folders |
| `{{MODULE_MAP}}` | A table per area: module, responsibility, one line. A map, not documentation |
| `{{BOUNDARY_ENFORCEMENT}}` | Numbered: each rule and WHAT enforces it. Write "not enforced" where nothing does |
| `{{BOUNDARY_RULES}}` | The same boundaries stated as rules in the constitution |
| `{{TESTED_AREA}}` | Which part of the tree may not receive untested code |

### Gates

| Placeholder | What goes in |
|---|---|
| `{{BUILD_TEST_COMMAND}}` | One shell command that builds and tests. It runs on every commit — keep it fast. No deploy step, dry runs included: an agent's permission layer may refuse to run the whole gate. No server left running: a compiler server or build daemon the command starts (MSBuild node reuse, VBCSCompiler, the Gradle daemon, sccache) holds the gate lock until it exits, and the commit hook waits for it; turn it off in the command (`docs/GOTCHAS.md`) |
| `{{BOUNDARY_CHECKS}}` | **Replace the whole of `scripts/boundary_checks.sh`**: one grep per enforceable boundary, each setting `fail=1` |
| `{{BOUNDARY_SELF_TESTS}}` | **Replace the whole of `scripts/boundary_selftests.sh`**: one negative test per check above. Not optional — see below |
| `{{TOOLCHAIN}}` / `{{TOOLCHAIN_PATH_SETUP}}` / `{{TOOLCHAIN_SETUP_NOTES}}` / `{{TOOLCHAIN_SETUP_STEP}}` | What the gate needs on PATH, how to find it in a non-login shell, how CI installs it. `{{TOOLCHAIN_PATH_SETUP}}` is a directory to prepend, not a line of code |
| `{{DEFAULT_BRANCH}}` | The branch CI runs on |
| `{{STACK_IGNORE_RULES}}` | Stack-appropriate `.gitignore` rules. Remember: the re-include block stays LAST |
| `{{GATED_PATHS}}` / `{{GATED_FILE_PATTERN}}` / `{{BOUNDARY_GUARDS}}` | Which paths the editor-side hooks watch, mirroring the checks above. `{{BOUNDARY_GUARDS}}` is a live list element: replace the quoted string with real tuples, or delete the line if nothing is guardable — do not leave it a string |

**Two of these sit on a commented line, and the `#` is part of what you replace.**
`{{TOOLCHAIN_SETUP_STEP}}` in the CI workflow and `{{STACK_IGNORE_RULES}}` in `.gitignore`
are followed by an instruction comment; delete the marker, the leading `#` and the
instruction together. Substituting only the token leaves the replacement inside a comment,
which is how a check ends up enforcing nothing while everything still reports green. That
mistake has already been made twice in this kit's history, which is why every other
placeholder is either a quoted value or a whole file.

### Process

| Placeholder | What goes in |
|---|---|
| `{{WORKTREE_POLICY}}` | A table: path, worktrees yes/no/conditional, and the condition. Anything with a huge cache or a shared database is a "no" or a "needs its own" |
| `{{MODEL_ROUTING}}` | Which model gets judgement work, which gets volume, and which budget is scarce |
| `{{REJECTED_DECISIONS}}` | Everything considered and turned down in this interview, with the reason and what would reopen it |
| `{{PROJECT_STOP_RULES}}` | Project-specific reasons an agent must stop and ask |
| `{{PROJECT_SETUP_STEPS}}` | Anything else a fresh clone needs |
| `{{MODULE}}` | Only in `MODULE_AGENTS_TEMPLATE.md` — copy that file per module and fill it there |

**An example `{{MODEL_ROUTING}}`**, by the tiers of `docs/WORKFLOW.md`, "Model routing" (a
project's own as of 2026-10-08; replace the model names with what the owner's subscriptions
offer today):

| Tier | Work | Codex | Claude |
|---|---|---|---|
| 1 | Mechanical: renames, figure fixes, data fetches, proof runs, summaries | `gpt-6-luna`, medium effort | Haiku 5.5 or Sonnet 5.5 |
| 2 | Detail-bearing errands, ordinary reviews | `gpt-6.1-sol`, high effort | Opus 5.5, only for design-bearing work |
| 3 | Risky and gate reviews, design consultations | `gpt-6.1-sol`, xhigh effort; `gpt-6-astra` when the lead picks it | Opus 5.5; Fable 5.1 when the lead picks it |

The prices behind it come from third-party summaries of OpenAI's launch figures: Luna costs
about a twentieth of Sol's token price, and Sol 6.1 about a fifth of Astra's. Neither the
per-model Codex allowance nor the quality claims were verified. Astra and Fable are
available only on the subscriptions that include them. **The table is provisional**: API
token prices say nothing about how much each model draws from a subscription's five-hour and
weekly allowance. Measure that draw (`/status` before and after a few errands per model) and
move the tiers by it.

### Then, in this order

1. **Write the boundary checks and their negative tests together.** They live in two files
   that `scripts/check.sh` sources: `scripts/boundary_checks.sh` and
   `scripts/boundary_selftests.sh`. Replace each file WHOLE — that is why they are separate
   files rather than a marked region inside the gate script, and it is not a stylistic
   preference: the first person to fill a marked region left the comment character on the
   first line, and the entire check sat inert inside a comment while the gate reported PASS.
   For every check you add, add the case that constructs the violation and asserts the gate
   rejects it. A gate you have only seen pass has not been tested; it is an untested branch
   that runs on every commit. Both files ship with a worked example.
2. **Run `./scripts/check.sh`.** Show the owner the real output. If it fails, fix the cause.
3. **Run `./scripts/check.sh --self-test`.** Show that output too. If a gate does not go red
   when its failure is injected, it is protecting nothing — fix it before you continue.
4. **Initialise `docs/STATE.md`**: what was set up, what is open, what the owner still has to
   do, with a tool+model trace. Full sentences. The first tasks after setup, and anything the
   owner parked, go to `docs/BACKLOG.md`.
5. **Delete what does not apply.** An overlay or a section for something this project does
   not have is not harmless — it is a lie the next agent will believe.
6. **Stage and hand off for fresh review before commit.** If the repository has no commit
   gate yet, wire it with `git config core.hooksPath .githooks`. Stage the intended setup
   files and follow `docs/REVIEW_GATE.md` in a fresh reviewer session. This setup writes
   gate code, so the setup author cannot approve it. Record the pending review and any
   manual checks in `docs/STATE.md`; do not commit until the review requirement is met.
   If review cannot run, leave the staged work and an explicit handoff rather than treating
   setup as an exemption. Commit only after verified acceptance and required manual checks.

## Phase 5 — backflow

**Skip this phase entirely if the owner said no in Phase 0.5.** Do not ask a softer version
of the question; they already answered it.

Otherwise, ask once:

> "Did anything from this setup belong in the kit itself, rather than only in this project?"

A rule you had to invent because the kit lacked it, a placeholder that was ambiguous, a
question you needed that this file does not ask — those are the candidates. If the answer is
yes, produce a ready-to-apply patch for the kit repository plus a `CHANGELOG.md` entry, and
tell the owner where to send it. If the answer is no, or a shrug, that is the end of it.

The reason the question exists: a foundation only finds out where it is wrong from the
projects that hit its edges, and this setup is the one moment its gaps are freshly visible.
A day later nobody remembers which instruction was confusing.

---

## When you are finished

Report, briefly and honestly:

- What was decided, and what stayed OPEN.
- The real output of `./scripts/check.sh` and of `./scripts/check.sh --self-test`.
- Whether fresh review accepted the setup diff, or remains pending with a handoff.
- Anything you could not verify, named as "not run".
- What the owner still has to do by hand.
