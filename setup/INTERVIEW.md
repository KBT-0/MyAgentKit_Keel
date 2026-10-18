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

   Rules 1-3 are the kit's reading of "one question, one decision, your recommendation and
   its reason" (the kit's `docs/research/communication-style.md`, finding 6 and proposal 10)
   and of the vendor's "Let Claude interview you" (code.claude.com/docs/en/best-practices).
   Sources (D08 inv3#96): [Spec Kit, spec-driven.md](https://github.com/github/spec-kit/blob/main/spec-driven.md)
   and ["Let Claude interview you"](https://code.claude.com/docs/en/best-practices#let-claude-interview-you).
4. **Record the RATIONALE for every decision: one sentence next to the rule, and the longer
   reason in `docs/PROJECT.md` (DECIDED) or `RESEARCH_LOG.md`, linked from the rule.** A rule
   without its reason gets deleted by someone who cannot see what it was protecting; a rule
   file padded with long reasons gets ignored (Nygard, "Documenting Architecture Decisions";
   code.claude.com/docs/en/best-practices, the over-specified CLAUDE.md).
5. **Anything the owner did not explicitly approve is OPEN, not DECIDED.** Never record a
   decision they merely failed to object to.
6. **Never claim you ran something you did not run** (`AGENTS.md`, "Review gate and
   validation honesty"). If a command could not be executed, say "not run"; break it here and
   the whole thing is theatre.
7. **Ask, do not assume, about scale: how many people work on it, and what a mistake costs.**
   A solo hobby project and a five-person team need different answers to the same questions
   (Boehm and Turner, "Balancing Agility and Discipline": size and criticality decide the
   method). The kit's defaults lean solo: the owner's choice, in line with the finding that
   needless requirements in a context file lower success and raise cost (arXiv 2602.11988).

---

## Phase 0 — the owner's note

If `docs/kit/BOOTSTRAP_NOTE.md` exists, read it FIRST. It is the owner's agenda for this
setup, written when they ran the installer: a tool they want added, a model they want to
try, a problem they hit last time.

Copy its items into `docs/STATE.md` as a numbered list, each line with a status: done (with
the file or command that shows it), not done (with the reason), or open (waiting for the
owner). Show that list to the owner before Phase 1 ends. Saying an item was handled is not
handling it: point to the evidence. Once the owner has seen the list, delete the done lines
(a living file keeps no closed item). Silently ignoring the note is the one failure mode this
phase exists to prevent. Sources: code.claude.com/docs/en/best-practices ("show evidence
rather than asserting success"); "The Compliance Gap" (arXiv 2605.01771: a model can say it
will follow a process and not do it; one author, not peer-reviewed, so low confidence).

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
scarier than it is would be its own kind of dishonesty. (Ask first, send nothing unasked: the
opt-in that clig.dev, "Analytics", asks of any command-line tool.)

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
strictly worse than an honest gap (models lose accuracy on API changes after their cutoff:
RustEvo^2, arXiv 2503.16922; the vendor's "Minimizing hallucinations in agentic coding",
platform.claude.com prompting best practices). Note the skip in `RESEARCH_LOG.md` if that
file is present.

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

   - **Which model family is the AUTHOR?** The one that writes most of the code. The kit's
     default is one family alone (`solo`, `docs/WORKFLOW.md`, "Working modes, by name"):
     one tier writes and another tier of the same family reviews, each in a fresh session.
     The family is Claude unless the owner names another (`solo "family: codex"`).
   - **Is there a SECOND vendor?** Only then do both families write, each task by fit,
     and each reviews the other (`cross`), with Claude as the lead.
   - **Which budget is scarce, and which is generous?** This fills the model-routing table,
     and it is often what decides the two answers above. A capable model on a nearly
     exhausted plan makes a better reviewer than an author (`saver`).

   Record the answers where the tooling reads them: the `DEFAULT_REVIEWER`, `CODEX_MODEL`
   and `CLAUDE_MODEL` values at the top of `scripts/review.sh`. **The reviewer must be
   pinned by its FULL model ID, not an alias such as `opus` or `sonnet`:** an alias moves
   with the vendor's recommended version (code.claude.com/docs/en/model-config), so an
   archived review could not be compared with a later one. An unpinned reviewer archives
   whatever default its CLI had that day, and the wrapper refuses to run, an alias included,
   rather than record something no later review can be compared against. Say plainly that the roles can be swapped later by editing those three
   values, and that swapping them does not change the evidence format; a high-tier change is
   still never reviewed by a weaker tier than its author's (`docs/WORKFLOW.md`, "Model routing").

   Then ask specifically about the **review CLI**, because it is the one part of this kit
   that needs software the owner may not have. `scripts/review.sh` shells out to a CLI in a
   fresh session, and it ships with adapters for two: `--reviewer claude` and
   `--reviewer codex`. So:

   - Check which are installed: `command -v claude`, `command -v codex`. Do not assume
     either way — report what you found. One is enough: in `solo` a second tier of the same
     family reviews through `--reviewer claude` with `REVIEW_CLAUDE_MODEL` pinned to the
     tier that did not write. A second vendor is pluggable, never required.
   - If neither is installed, explain the trade: without a review CLI, the review protocol
     becomes the paste-the-template-by-hand version in `docs/REVIEW_RUNNING.md`. That is a
     genuine fallback, and the kit works without it. With it, `/myagentkit:cross-review`
     runs the whole thing in-session.
   - **Offer to install it.** You can run the installer; the owner does the login. Say what
     you are about to run before you run it, and do not install anything they did not agree
     to — a new dependency needs their approval, which is a STOP rule in the constitution
     you are installing (clig.dev: ask before changing what is not yours, and say exactly
     what you did).
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
     `openai-codex`; installation uses the marketplace name after `@`, which is the `name`
     in its `marketplace.json` (code.claude.com/docs/en/plugin-marketplaces). Do not derive
     it from the repository name. `docs/DEV_SETUP.md` has the same pair and the cautions about
     model-invocable commands and automatic review gates.
   - For a Codex host, offer the kit's Codex plugin and its Claude review/delegation skills
     (`docs/CODEX.md` in the kit). `--reviewer claude` selects the Claude adapter from any
     host; `REVIEW_CLI_BIN` and `CLAUDE_CLI_BIN` change only which binary is launched. Any
     THIRD CLI still needs a separately implemented and live-validated adapter, not merely a
     binary substitution — `--reviewer` deliberately accepts only the two names it has
     adapters for.
   - Review delegation works from both hosts (`docs/delegation-is-not-symmetric.md`);
     structured implementation PROPOSALS are shipped only for Codex-as-host calling Claude,
     so do not promise a Claude-to-Codex proposal path.
7. **What is the FIRST phase, and what is deliberately not in it?** Not the whole plan —
   the one question the project should answer first, and the things that are tempting but
   must wait. Order by risk: the assumption that would hurt most if it turned out wrong goes
   first, even when it is not the foundation (Boehm's risk-driven spiral model; the Lean
   Startup's "leap-of-faith assumptions" tested first). One question per phase is the kit's
   own choice.

8. **Do your workers wait on anything longer than five minutes (a job, a lock, a person)?**
   A build, a bake, a test suite, a render, a data import, a lock another job holds, a
   permission prompt nobody answers — anything a worker starts or meets and then has to wait
   for. Ask for the job names and their typical lengths, and what a worker must know BEFORE
   running them (a lock that serialises them, a memory ceiling, an environment variable, a
   copy step), which goes into the worker definition's body under its project rules. The
   reason: a sub-agent's prompt cache lives five minutes (code.claude.com/docs/en/prompt-caching),
   so a worker that waits longer re-writes its whole context after every wait; in the kit's
   founding project that was 87 percent of all cache-write tokens (`docs/WORKFLOW.md`,
   "Worker cost"). If the Claude Code overlay is installed, fill `{{WORKER_MODEL}}`,
   `{{WORKER_EFFORT}}` and `{{LONG_JOBS}}` in `.claude/agents/worker.md` with the author
   model, its effort (`high` when the workers' tasks bear design, lower when they are
   mechanical; without the field a sub-agent runs at whatever effort its lead session has)
   and those job names, and tell the owner that workers are spawned with that definition
   instead of the general-purpose one. If the answer is no, keep `.claude/agents/worker.md`
   (it pins model, effort and the turn cap) with `{{LONG_JOBS}}` set to `none`, and delete
   only `scripts/spawn_worker.sh` (Phase 4, "Delete what does not apply"). Either way the
   rules in that section bind the lead from day one.

9. **May AI tools be credited in commit messages?** Coding tools add a co-author trailer by
   default, and in the kit's founding project that put one into most commits against the
   owner's wish; removing it later meant rewriting every commit and a force-push. The answer
   is a hard rule in `AGENTS.md` either way. No (the default): keep the "No AI attribution
   in git" rule; `.githooks/commit-msg` enforces it, and the Claude Code overlay's
   `.claude/settings.json` ships `"attribution": {"commit": "", "pr": ""}` so the tool does
   not add the trailer in the first place (code.claude.com/docs/en/settings-reference; the hook is the
   backstop). On a retrofit the project's own `AGENTS.md` was kept: for No, add the rule line
   with the exact phrase "No AI attribution in git" (the hook keys on it and passes every
   message without it), and add the `attribution` block to a kept `.claude/settings.json` as
   Q11 does for its entries. Yes: replace that rule with one saying AI tools may be credited; the hook keys
   on the rule line, so without it the hook gives way, an `Assisted-by:` trailer included.
   If the project takes outside
   contributions, check its policy first: the Linux kernel and Fedora ask for an
   `Assisted-by:` trailer, not a co-author line (docs.kernel.org/process/coding-assistants.html;
   Fedora's AI-assisted contributions policy). If the Claude Code overlay is installed, also
   remove the `attribution` block from `.claude/settings.json` and delete the block from
   `<!-- BEGIN attribution rule` to `<!-- END attribution rule -->` in
   `.claude/agents/worker.md`, and tell the owner you did: left there, the block told every
   worker the opposite of the owner's answer, and the setting keeps dropping the credit the
   owner allowed.

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
    the kit, merged worktrees piled up to 34 GB before anyone removed them (the kit's
    `RESEARCH_LOG.md`); Claude Code removes only the worktrees it made itself and never those
    a lead adds (code.claude.com/docs/en/worktrees), and stale ones are a reported problem
    (anthropics/claude-code issue 26725).

11. **Should sessions and workers write code in ponytail mode? Default: yes.** Ponytail
    (`DietrichGebert/ponytail`, MIT) makes the agent climb a ladder before writing code: does
    it need to exist, is it already in the codebase, does the standard library or the
    platform do it, an installed dependency, one line, and only then the minimum code. It
    keeps input validation, error handling and security in. Cost and gain, honestly: its own
    benchmark (run by its author, one model, 39 tasks, 5 runs each, Opus 5.5) reports about
    half the code and 26 percent lower cost than the same agent without it; nobody has checked
    it independently (its README, github.com/DietrichGebert/ponytail). Its session-start cost
    was not measured here. It comes from its author's own marketplace at the latest version
    (the owner's choice: not pinned to a ref or sha). Yes: keep
    `extraKnownMarketplaces` (`ponytail`) and `enabledPlugins` (`ponytail@ponytail`) in
    `.claude/settings.json` (the Claude Code overlay ships them; where bootstrap kept the
    project's own file, add both entries to it and leave the rest as it is);
    Claude Code offers the install when the folder is trusted, and spawned worker sessions
    and sub-agents get the mode with it. Its hooks need `node` on PATH. An owner who already
    enabled `ponytail@ponytail` in their user settings gets the same plugin, loaded once.
    For Codex sessions and workers, give the owner the two commands to type, then `/hooks`
    in Codex to trust its hooks:
    ```text
    codex plugin marketplace add DietrichGebert/ponytail
    codex plugin add ponytail@ponytail
    ```
    No: in `.claude/settings.json`, set `"ponytail@ponytail": false` under `enabledPlugins`
    (a project setting overrides a user-level install, so this turns it off here too) and
    delete the `ponytail` marketplace entry; say so.

12. **In which language does the owner want to be talked to, and which terms need no
    explanation?** Two answers. The language goes into `{{CHAT_LANGUAGE}}` in `AGENTS.md`
    (identifiers stay English in backticks whatever the answer; `docs/COMMUNICATION.md` has
    the rules). The terms go into `docs/GLOSSARY.md`, the first list: ask for the owner's
    field (a Unity developer knows C# and the editor; a security engineer knows other
    things) and the tools they use daily, and write those as the terms an agent never
    explains. Everything else is explained at first use, and the glossary grows with every
    "what does this mean". The reason to ask: in the kit's founding project the owner read
    reports full of the agents' own labels ("D-1", "r2", "Accept-MC") and the most common
    Claude complaint of 2026 is this invented jargon. If the Claude Code overlay is
    installed, say that `.claude/hooks/plain_report.py` bounces a final message that still
    carries such a label: task ids come from the task grammar in `.githooks/commit-msg`
    (where a project extends it), and `.claude/plain_report_labels.json` (a JSON list of
    regular expressions) is where a project adds any other shape.

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
| `{{CHAT_LANGUAGE}}` | The language the owner is talked to in (question 12), e.g. `English` or `Turkish`; identifiers stay English |
| `{{KNOWN_TERMS}}` | In `docs/GLOSSARY.md`: the terms from question 12 an agent never explains, one per line, or `(none yet)` |

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

One value sits beside them, not a placeholder: ask "Which top-level folders hold modules?"
and write the answer into `module_roots` in `scripts/check.sh` (space-separated). The gate
then fails when a subfolder of one is not named in the `## Module map` of
`docs/ARCHITECTURE.md`; empty, it prints a NOTE and checks nothing (a single-module project).

### Gates

| Placeholder | What goes in |
|---|---|
| `{{BUILD_TEST_COMMAND}}` | One shell command that builds and tests. It runs on every commit — keep it fast: seconds, not minutes; put anything slower in CI (a client hook can be skipped, so CI is the last line anyway). No deploy step, dry runs included: an agent's permission layer may refuse to run the whole gate (it did once: the kit's `RESEARCH_LOG.md`, "Gates that did not gate"). No server left running: a compiler server or build daemon the command starts (MSBuild node reuse, VBCSCompiler, the Gradle daemon, sccache) holds the gate lock until it exits, and the commit hook waits for it; turn it off in the command (`docs/GOTCHAS.md`) |
| `{{BOUNDARY_CHECKS}}` | **Replace the whole of `scripts/boundary_checks.sh`**: one grep per enforceable boundary, each setting `fail=1`, and a fixture test per check in the project's test suite. Not optional — see below |
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
| `{{REJECTED_DECISIONS}}` | Everything considered and turned down in this interview, with the reason and what would reopen it |
| `{{PROJECT_STOP_RULES}}` | Project-specific reasons an agent must stop and ask |
| `{{PROJECT_SETUP_STEPS}}` | Anything else a fresh clone needs |
| `{{MODULE}}` | Only in `MODULE_AGENTS_TEMPLATE.md` — copy that file per module, delete the copy's KIT-OWNED first line, and fill it there |

**Model routing ships filled.** `docs/WORKFLOW.md`, "Model routing", carries the kit's tier
table and its working modes. Replace the table's model names with what the owner's
subscriptions offer today, and ask which working mode starts (solo unless the owner names
another). Run `scripts/working_mode.py <name>` with the host's Python to record
the choice in both `.myagentkit/mode` (ignored by Git) and the "Working mode:" line of `docs/STATE.md`.

### Then, in this order

1. **Write the boundary checks and their fixture tests together.** The checks live in
   `scripts/boundary_checks.sh`, which `scripts/check.sh` sources. Replace the file WHOLE —
   that is why it is a separate file rather than a marked region inside the gate script, and
   it is not a stylistic preference: the first person to fill a marked region left the comment
   character on the first line, and the entire check sat inert inside a comment while the gate
   reported PASS. For every check you add, add a fixture test to the suite the build command
   runs: an input that breaks the rule turns the check red with its own `FAIL` line, a clean
   one leaves it green, and nothing touches the checkout or runs the build. A gate you have
   only seen pass has not been tested; it is an untested branch that runs on every commit (a
   check never seen failing does not show what it checks; Google checks the same at scale with
   mutants in code review: "Practical Mutation Testing at Scale"). The file ships a worked
   example of both.
2. **Run `./scripts/check.sh`.** Show the owner the real output. If it fails, fix the cause.
3. **Watch each check go red once.** Break its rule by hand (add the forbidden import), run
   `./scripts/check.sh`, show the owner the check's `FAIL` line, and undo it. If a check does
   not go red, it is protecting nothing — fix it before you continue. Output shown, not a
   claim of success: code.claude.com/docs/en/best-practices, "Give Claude a way to verify its
   work".
4. **Initialise `docs/STATE.md`**: what was set up, what is open, what the owner still has to
   do, with a tool+model trace. Full sentences. The first tasks after setup, and anything the
   owner parked, go to `docs/BACKLOG.md`.
5. **Delete what does not apply.** An overlay or a section for something this project does
   not have is not harmless — it is a lie the next agent will believe: agents follow what a
   context file says, and needless requirements in it lower success and raise cost
   (arXiv 2602.11988; code.claude.com/docs/en/memory, conflicting instructions;
   code.claude.com/docs/en/best-practices, the over-specified CLAUDE.md).
6. **Stage and hand off for fresh review before commit.** If the repository has no commit
   gate yet, wire it with `git config core.hooksPath .githooks`. Stage the intended setup
   files and follow `docs/REVIEW_GATE.md` in a fresh reviewer session. This setup writes
   gate code, so the setup author cannot approve it. `scripts/review.sh` cannot take a first
   setup: it diffs against a commit, a new repository has none, and a whole install can be
   several times the diff one review takes (a Unity install measured 1.35 MB). So review it
   with a fresh reviewer that reads the staged files directly (the Claude Code overlay's
   `diff-reviewer` subagent), and give it the list of files this setup wrote or changed: you
   know them from this session. Every other staged file is the release's unchanged copy, and
   the reviewer reads those only for context. Record the pending review and any
   manual checks in `docs/STATE.md`; do not commit until the review requirement is met.
   If review cannot run, leave the staged work and an explicit handoff rather than treating
   setup as an exemption. Commit only after verified acceptance and required manual checks.
   (A fresh context is not biased toward code it just wrote: code.claude.com/docs/en/best-practices,
   Writer/Reviewer; a pull request's author cannot approve it either: GitHub Docs, required
   reviews; self-review measured no gain: the kit's `docs/research/ai-review-workflows.md`, S4.)

## Phase 5 — backflow

**Skip this phase entirely if the owner said no in Phase 0.5.** Do not ask a softer version
of the question; they already answered it.

Otherwise, ask once:

> "Did anything from this setup belong in the kit itself, rather than only in this project?"

A rule you had to invent because the kit lacked it, a placeholder that was ambiguous, a
question you needed that this file does not ask — those are the candidates. If the answer is
yes, run `/myagentkit:kit-feedback` with that finding instead of drafting the patch here: it
confirms the finding in one sentence, scrubs the project out, and shows the exact text before
anything is sent. If the answer is no, or a shrug, that is the end of it.

The reason the question exists: a foundation only finds out where it is wrong from the
projects that hit its edges, and this setup is the one moment its gaps are freshly visible.
A day later nobody remembers which instruction was confusing.

---

## When you are finished

Report, briefly and honestly:

- What was decided, and what stayed OPEN.
- The real output of `./scripts/check.sh`, and of each check going red in step 3.
- Whether fresh review accepted the setup diff, or remains pending with a handoff.
- Anything you could not verify, named as "not run".
- What the owner still has to do by hand.
