<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->
# Development Workflow — the rationale

Why the rules of `docs/WORKFLOW.md` are what they are: their sources, the measurements behind
them and the long examples. The headings are `docs/WORKFLOW.md`'s, and a section there whose
reasons are here ends with a "Why:" line that names its heading. The rules, the owner's
decisions and every choice a project makes stay in `docs/WORKFLOW.md`; this file is the kit's,
and a sync replaces it.

## Task ids

Finished work that nobody deleted is how `docs/STATE.md` rots: a project's state file held
lines like "Committed: K4" and "merged after three review rounds" long after the work was in
git, and a size limit could not tell those lines from live ones. A task id makes the
deletion checkable.

## The state, backlog and phase files

The order is `docs/AGENTS.md`'s; these are its reasons. The hash and the bytes come from one
read: a hash read apart from the bytes it names let a copy read at the session's start pass
over an edit published in between. The helper compares under the same lock as a mode switch and
replaces the file atomically, keeping a successor at the supplied path, because publication and
rollback could otherwise erase another writer's work. A snapshot lives only in `.myagentkit/`
(ignored by Git) or the temporary folder, because `/myagentkit:mode` runs the helper unprompted
and a snapshot elsewhere can land where `git add -A` commits it; OUT is a name prefix and FILE a
regular file, because OUT naming `.myagentkit` put the snapshot in the project root and FILE
naming a folder moved it whole. The "Working mode:" line is the mode switch's, which writes it
together with `.myagentkit/mode`. Sources: HTTP If-Match (the lost update,
developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-Match), anthropics/claude-code#24130
(an auto-memory file is not safe for concurrent agents), Python `tempfile.mkstemp` (an exclusively
created snapshot; CWE-377).

- `docs/STATE.md` is read at the start of every session, in every tool, so its length is a
  bill paid every session. What is planned next, and what was parked on purpose, is a
  backlog, and it lives in `docs/BACKLOG.md`, which is read only when the next task is chosen.
  A backlog only grows, and in STATE.md it is read every session for nothing. STATE.md holds
  current state only, and traps live in `docs/GOTCHAS.md`: every line read at session start
  costs on every session (code.claude.com/docs/en/memory), and a working list is rewritten,
  not appended to (Manus, "Context Engineering for AI Agents"). An empty Active work section
  means nothing is in flight, a contract the gate does not check.
- **Why the tool+model trace.** Record which tool and model did the work, so a later session
  can tell who wrote a change (the author never reviews it) and where the cost went. The
  trace is kept in STATE.md, not in git, because git carries no AI attribution; the Linux
  kernel's `Assisted-by:` trailer (docs.kernel.org/process/coding-assistants.html) is the
  opposite placement, which the owner's no-attribution rule rules out.
- Updating STATE.md at the end of a session is the agent's job: a long-running agent leaves
  its progress file for the next session, which starts with no memory (Anthropic,
  "Effective harnesses for long-running agents").
- A `[LESSON]` or `[GOTCHA]` tag makes harvesting a grep, not a re-read. Deleting a tagged
  line before it has a home is caught only as a NOTE (`scripts/check.sh`); the rest is
  discipline.
- Pruning without harvesting buries the lesson in the git history, and nobody looks there —
  git is an audit trail, not a knowledge base. A context that is rewritten whole loses detail
  ("context collapse", Zhang et al., arXiv:2510.04618), so a lesson is moved, not summarised away.
- Completed work is deleted, not marked DONE: the dates live in git
  (`git log -p -- docs/STATE.md`). The state templates name no example task id, because
  those files are the ones checked ("Task ids"). No outside kit enforces the deletion; the
  check is the kit's own lesson (its RESEARCH_LOG, 2026-10-03).

- No size limit applies to STATE.md. A limit cannot tell a live line from a finished one,
  and a project that added one hit it again and again while half the file was backlog and
  much of the rest narrated work already in git. What keeps an always-read file useful is
  what it holds, not a line count: a long or conflicting file is followed less
  (code.claude.com/docs/en/memory; IFScale, arxiv.org/abs/2507.11538).

**The non-goals are the useful half.** "Build the inventory system" gives an agent no edge
to stop at, so it invents scope: it adds persistence, a UI, an event system, and returns one
monolithic file touching five modules. "Build the grid placement rules; do NOT add
persistence, do NOT write UI" is the same task with a fence around it. Scope invention is
the most expensive habit an agent has, and `docs/PHASES.md` is the cheapest cure.

## Decay early-warning system

Sources: a weakened or deleted test is how agents game a task (Kent Beck, "Augmented Coding:
Beyond the Vibes"; METR, "Recent Frontier Models Are Reward Hacking", 2025), so it stops the
work; the rest is drift that an audit removes in batches (Thoughtworks Technology Radar,
"Architecture drift reduction with LLMs"; GitClear's 2025 code-quality report). File size
predicts defects without a clean threshold
(Yamashita et al., QRS 2016), so the rule names the symptom, not a number.

## Model routing — by cost per task and by scarcity

### Working modes, by name

Without names, the owner explained the same situation in a long prompt at the start of every
session ("Claude is low today, let Codex write and fix"), and a lead that was not told routed
by habit. A name is one word, and a lesson one project learns improves the mode for every
project through the kit. A few named modes the user switches are common practice (Aider's
chat modes, aider.chat/docs/usage/modes.html; Roo Code's modes,
roocodeinc.github.io/Roo-Code/basic-usage/using-modes); what each mode here decides is the
kit's own.

### autopilot, the owner-away switch

The owner asked for a mode to start before leaving the lead overnight, with no stop on "a
silly excuse", decisions taken and reported in the morning, questions saved for the morning
(2026-10-22); the whole study is the kit's `docs/research/unattended-lead.md`. Every source it
read rests unattended work on the same three legs: a scope with a done criterion written
beforehand, stop conditions the machine enforces, and state kept in files with a report at the
end (code.claude.com/docs/en/best-practices; the report's summary 1 names the OpenAI and
Devin sources). Presence is a switch beside the mode, not a fourth mode, so a night in saver is
still expressible; the explicit record replaces the 45-minute inference, which stays for a
project without one. The keep-going engine is Claude Code's own `/goal` (a condition checked
after every turn, paused and resumed at a usage limit) and the automatic continue at a usage
limit, which works only in an open interactive session that stopped mid-task
(code.claude.com/docs/en/goal, code.claude.com/docs/en/interactive-mode): hence the
foreground lead and no turn without a wake-up. The decision table follows bounded-autonomy
practice: reversible work inside the workspace is autonomous; irreversible, outward or
credential-touching work stays with the human (AWS Well-Architected Agentic AI Lens; OWASP
Least-Agency; Claude Code auto mode's default block list), with the owner's amendments of
2026-10-22: push and tag once every check and CI are green, local merges, issues as drafts.
A stronger-model consult is the vendors' advisor pattern (the advisor tool, Amp's Oracle,
Aider's architect mode), where the advisor counsels and the executor decides; no source counts
the advisor's word as a human approval, a same-family judge shares blind spots, and a question
that carries the asker's answer anchors the reply, hence the two steps and the label. The
report's Done section comes from git, never from the agent's own account. Left out: an own
Stop hook (only if `/goal` shows a gap in use), a `-p` or Ralph loop as the lead (no usage-limit
wait, no hooks with `--bare`, a fresh context loses the orchestration state), the lead in
`--bg` (no limit wait, no question timeout), `--dangerously-skip-permissions` (no sandbox on
native Windows), and blanket allow rules (auto mode is no guarantee).

## Worker cost — waits and long lives are what you pay for

### The measurements and the full rules

Measured in the kit's founding project (one lead session with background workers: 336 USD in
eleven hours, 87 percent of it the workers; the transcripts were then counted request by
request, and a controlled experiment ran the same task in six setups). What the numbers say:

- **Within a subscription's included usage, the default cache lifetime is five minutes for
  a sub-agent and one hour for the main conversation.** A worker that waits longer than its
  cache re-writes its whole context on the next request, at
  more than ten times the price of reading it. 87 percent of all cache-write tokens followed
  such a gap: poll loops, a ten-minute job, a wait on a lock, a resume after a handback.
- **Every request re-reads the whole context**, and context grows by about 2k tokens per
  request whatever the tool output size. One worker resumed for three review rounds (377
  requests, context 36k to 711k) was 38 percent of all cache read and 48 percent of all
  cache write.
- **Polling is paid twice**: each poll turn re-reads the context, and the wait then expires
  the cache. Fifteen percent of all cache read went to turns that only waited.
- **A background job alone saves nothing** (+12 percent in the experiment): the wait still
  outlives the five-minute cache. A one-hour cache with background jobs and no polling saved
  36 to 38 percent; splitting every wait under five minutes saved more on a small context but
  pays a full context read per poll, so it loses at real worker sizes.
- **Tool output was not the problem**: all tool results of all agents together were about one
  million tokens. Trimming output is hygiene, a small lever.

## Review rounds — early, inside the worker, in parallel

In one project a feature took five fix rounds in about seven hours. Each round cost a fresh
worker re-reading 100k to 300k tokens (20 to 60 minutes), a ten-minute gate run, reviews of
5 to 15 minutes and a merge with another gate run. Most findings of rounds 2 to 5 sat in code
the previous fix had added, in classes the reviewers had already shown once. A fix is new,
unreviewed code: 15 to 24 percent of fixes in large systems were themselves wrong (Yin et al.
2011). The rules of this section in `docs/WORKFLOW.md`
move the review into the worker's warm context and run together what can run together. They
remove no review.

### Design before code

In the kit's own two observed cases a one-page design round took about fifteen minutes where
the same flaws cost hours of code rounds (the kit's RESEARCH_LOG, 2026-10-03).

### Review inside the worker

- Sources: a fresh reviewer step finds what the author missed (code.claude.com/docs/en/best-practices,
  "Add an adversarial review step"); a model correcting its own reasoning without outside
  feedback does not improve (Huang et al., ICLR 2024, arxiv.org/abs/2310.01798), which is why
  the reviewer is new each round.

## MCP hygiene

An enabled MCP server costs little by default in Claude Code: it defers the tool definitions
and loads only the tool names and the server's instructions until a tool is needed. The full
catalogue is paid on every request only where tool search is off (a non-Anthropic
`ANTHROPIC_BASE_URL`, `ENABLE_TOOL_SEARCH=false`, an older model) and on hosts that inline
schemas, such as API gateways (code.claude.com/docs/en/mcp, "Scale with MCP tool
search"; the kit's `docs/research/token-optimization.md`, 1.7). Most custom servers duplicate
what a plain CLI already does more reliably.

## Where the constitution's rules come from

`AGENTS.md` is read every session, so its rules carry no source lines; their sources live
here, by rule. A rule with no source below is the owner's choice or a lesson named beside it.
A citation of `KARARLAR` (Turkish for "decisions"; an item such as `B03 inv2#31` or `D06`)
names an entry of the kit maintainer's decision log, which the kit does not ship: it records
that the rule is an owner decision, and the reason stands beside the citation.

- **Reading order.** The constitution is loaded at session start, so opening it again adds a
  second copy (code.claude.com/docs/en/memory). `docs/ARCHITECTURE.md` is read only when the
  task crosses a module boundary: every always-read line is paid every session, and context
  files that grow lower task success (Gloaguen et al., arxiv.org/abs/2602.11988; matklad,
  "ARCHITECTURE.md"). A reviewer still reads it every time: it is on both bridges' one
  reading list (`REVIEW_DOCS` in `scripts/claude_bridge.py`).
- **Design authority** (DECIDED, OPEN, agents propose, phase scope, a code-versus-PROJECT
  conflict): Anthropic, "Building effective agents" and "Measuring AI agent autonomy in
  practice"; code.claude.com/docs/en/best-practices ("Let Claude interview you", plan mode);
  Nygard, "Documenting Architecture Decisions"; GitHub Spec Kit, `spec-driven.md` (an open
  question is marked, never guessed); Anthropic's prompting guide on overeagerness.
- **Cross-module access through contracts:** OpenAI's harness team enforces architecture
  with linters and structural tests (the kit's `docs/research/agent-kits-in-practice.md`,
  2.2); code.claude.com/docs/en/best-practices.
- **Third-party dependency approval:** models invent package names that attackers then
  register (Spracklen et al., USENIX Security 2025, arxiv.org/abs/2406.10279). The STOP
  for a new dependency or MCP server rests on the same source; a permission `ask` rule on a
  manifest file would make it mechanical (code.claude.com/docs/en/permissions).
- **One task, one module, its `Owns:` paths; no drive-by refactors:** Google Engineering
  Practices, "Small CLs"; Anthropic's prompting guide, "Overeagerness"; tangled refactoring
  in an agent's patch is linked to patches that do not compile
  (Tian et al., "Refactoring Runaway", arxiv.org/abs/2605.22526).
- **No push without the owner's word:** code.claude.com/docs/en/permission-modes and
  /permissions (a push leaves the machine and cannot be recalled); the kit's
  `docs/research/communication-style.md`, recommendation 9.
- **Commit or stash before a destructive git command:** reported agent sessions destroyed
  uncommitted work with `git reset --hard` and `git checkout -- .` (claudeissues.com, issue
  34327); git keeps only committed or staged content (git-scm.com/docs/git-fsck). A recursive
  delete proves ownership by a marker the tool wrote, as `CACHEDIR.TAG` does
  (bford.info/cachedir), because an empty variable once turned `rm -rf "$STEAMROOT/"*` into a
  wipe of a user's files (Steam for Linux, 2015).
- **Never end running work; end the whole tree:** a stopped parent leaves its children
  running (anthropics/claude-code#19045, #27959), and Claude Code's own team and worktree
  docs close a teammate and clean a worktree as one step (code.claude.com/docs/en/agent-teams,
  /worktrees).
- **The gate is wired into git and never skipped:** git-scm.com/docs/githooks; agents were
  seen skipping it with `--no-verify` despite deny rules (anthropics/claude-code#40117), so a
  hook refuses the flag and CI runs the same gate (pre-commit.com).
- **No AI attribution in git:** the owner's policy; the tool's `attribution` setting turns
  the trailer off at its source (code.claude.com/docs/en/settings). Why the trace lives in
  STATE.md: "The state, backlog and phase files".
- **A test in the same change; red proof for gate checks only:** Software Engineering at
  Google, ch. 11 (every change includes its tests); DORA, "Test automation"; the only study
  that measured test-first ordering found no effect (Fucci et al., IEEE TSE, arxiv.org/abs/1611.05994);
  a red proof of every ordinary test is practitioner convention only, and the evidence-backed
  question is whether the test breaks when the code is reverted or mutated (Petrović et al.,
  "Practical Mutation Testing at Scale"); studios validate generated content on its output
  (the kit's `docs/research/test-rules.md`, findings 1 to 11; owner decision 2026-10-18; the content-pipeline part is the leeway
  project's decision, a recommendation here).
- **Search before writing a system:** code.claude.com/docs/en/best-practices; duplicated
  code rose with AI assistants (GitClear's 2025 code-quality report).
- **A changed public API updates its README:** Google Engineering Practices, "What to look
  for in a code review" (documentation).
- **Language & style:** one job per file (Google's review guide; size predicts defects
  without a clean threshold, Yamashita et al., QRS 2016); no hidden global state (Hevery,
  "Singletons are Pathological Liars", Google Testing Blog, 2008); short doc comments
  (Google Python Style Guide, "Comments and Docstrings").
- **Duties: default silence, never repeat:** repeated alerts are ignored (Ancker et al.,
  BMC Medical Informatics and Decision Making 17:36, 2017); Anthropic's prompting guides for
  Sonnet 5.5 ("Steer initiative and scope") and Opus 5 ("Response length and verbosity").
- **A one-off decision writes its end condition:** agent memory fails when a temporary state
  overwrites a lasting one (Zhao et al., "LifeFuse-Mem", arxiv.org/abs/2609.12436).
- **MENTION ONCE items:** "Small CLs" (split by module); code.claude.com/docs/en/skills (a
  repeated procedure becomes a skill; the third time is the rule of three);
  code.claude.com/docs/en/costs (a saving needs a number). Decay findings: "Decay
  early-warning system" above.
- **Tone:** Anthropic, "Prompting Claude Opus 5"; the kit's
  `docs/research/communication-style.md`, findings 1 to 3, recommendations 1 and 16.
- **Task completion checklist:** the Scrum Guide's Definition of Done;
  code.claude.com/docs/en/best-practices ("Give Claude a way to verify its work").
