# RESEARCH LOG

Two kinds of entry live here, and they are kept apart on purpose.

**Ecosystem findings** come from `setup/RESEARCH_PROTOCOL.md`, which runs at every
bootstrap and at every project's periodic audit. Each finding is recorded with its date,
what it would change, what it costs, and a verdict — **including rejections**, so the next
pass does not spend budget re-litigating a decision that was already made. A research pass
asks "what changed since the last dated entry below?", so the dates are load-bearing.

**Backflow findings** come from projects USING the kit (`setup/INTERVIEW.md` Phase 5,
and the audit question in `docs/UPDATING.md`). A project learns something the hard way, and
the lesson belongs in the kit rather than in that one project. This section is why the kit
is not a static template.

Nothing is written here as a summary of something else. If a finding changed the kit, the
change is in `CHANGELOG.md` and the rule is in the file it governs; this log records **why**,
which is the part that gets lost.

---

## Implementation observations

### 2026-09-06 — The first setup commit must obey its own review rule (#1)

Phase 4 previously ordered a commit immediately after writing gates, contradicting the
constitution installed by the same interview. Setup now stages the intended files and
hands them to a fresh reviewer, recording any unavailable review or manual checks in
STATE.md. This prevents a new project from starting with an unreviewed gate merely because
it was created during setup. The general rule is unchanged; no setup exemption is added.

### 2026-09-06 — Green review tooling still hid five reproduced failures

A fresh owner-requested Astra review of the combined local change returned Reject despite
the existing acceptance suite passing. The host reproduced all five findings. Diagnostics
could be staged in projects missing the ignore rules while the review snapshot excluded
them. Successful `{}` output was misclassified as operational failure and launched a second
model. A valid Accept line followed by a malformed Reject line became an Accept report
after rendering removed the rejection. Deleting the packaging regression still left the
acceptance gate green, and the documented upgrade list omitted an imported runtime file.

The corrections check private storage before launch and again during publication, place
temporary raw archives under the ignored usage directory, classify malformed successful
envelopes as invalid evidence, count all verdict declarations before accepting one, and
require named test suites without skips. The upgrade test reads the canonical documentation
list so a missing companion cannot hide behind a separately maintained test fixture.
These are corrections to reproduced failures, not a new independent approval. The owner
explicitly authorized push with a fresh Claude review still pending; that task-specific
exception does not change the kit's general review policy.

### 2026-09-05 — Review deadline is not an activity detector

The owner objected to cancelling productive review at ten minutes and explicitly approved
a thirty-minute total deadline as the alternative to reliable startup detection. The
current Claude adapter requests final JSON, which may remain silent while the model is
working; silence alone cannot prove that a request has not started. The shared review
default is therefore 1800 seconds, still measured from process startup, with explicit
overrides preserved. This does not claim inactivity detection. Each failover attempt gets
its own deadline; proposals retain their separate default. A mocked-launch regression was
observed rejecting the old 600-second default on both direct adapters and both dispatcher
routes before the change, without waiting thirty minutes or calling a paid model.

### 2026-09-05 — Bounded operational reviewer failover

The owner requested automatic use of the other configured reviewer when the preferred
provider cannot complete, including subscription quota exhaustion. A single-provider
failure previously stopped evidence collection despite the other selected model being
available. Blindly trying another model for every nonzero exit would instead hide stale
scope, broken evidence, or persistence errors; switching after Reject would hunt for a
favorable verdict. The dispatcher therefore uses structured adapter outcomes, not prose
matching or exit status alone. It tries each provider at most once, preserves one original
scope, and stores separate per-attempt usage plus immutable chain checkpoints. A completed
Reject is terminal. An author-model fallback supplies advisory findings, not independent
approval. This is orchestration of existing CLIs, not a new provider API or quota estimate.

The offline quota regression was observed failing on the old wrapper (exit 5; no Codex
call) and passing after dispatch was introduced. No paid model invocation was needed to
prove the transition. Live subscription exhaustion and plugin rediscovery remain manual
checks, not claims established by fixtures.

## Last ecosystem research pass

**Never run.** The kit was extracted from a working project on 2026-07-26 without a
research pass of its own. The first `bootstrap.sh` run must therefore treat every
ecosystem claim in these files as unverified and run `setup/RESEARCH_PROTOCOL.md` from
scratch.

---

## Ecosystem findings

### 2026-09-05 — Correcting role-neutral workflow claims

The owner approved correcting three overstatements in the role-neutral handoff. A skill
calling a CLI and a command calling a CLI both delegate work; the missing capability is a
Codex proposal adapter, not Claude-host review delegation. A live synthetic smoke test
demonstrates integration, not acceptance of the actual implementation. Finally, neither
co-author can provide the independent review of their combined change, and creating a
local commit does not move the review requirement from before commit to before push.
The update instructions also distinguish automatic sync from manually adopting a new
project-owned wrapper. These are documentation corrections, not new delegation features.

The owner then selected Claude as the default reviewer because Astra now authors the work.
The default changes, not the available roles or the independent-review invariant. A fake-
CLI test was observed rejecting the old default before the change, then confirms the
Claude default and explicit Codex override. No monetary review cap is reintroduced.

### 2026-09-05 — Owner-selected review budget policy

The owner explicitly requested no default monetary cap for reviews and chose to start the
pending Claude review manually. Review invocations now omit the CLI budget flag unless a
cap is explicitly supplied. Existing timeout, turn, output, accounting, and authorization
controls remain; proposal defaults are unchanged. A fake-CLI regression first rejected
the previously injected default flag and then verified omitted and explicit-cap calls.

### 2026-09-05 — Codex-host Claude delegation — ACCEPTED for owner-requested implementation

This targeted implementation check is not a full ecosystem research pass. Current Codex
skills/plugins and Claude headless structured output allow the inverse of the kit's
original Claude-host/Codex-reviewer workflow without an MCP service or runtime SDK.
Sources checked: https://learn.chatgpt.com/docs/build-skills,
https://learn.chatgpt.com/docs/build-plugins, https://code.claude.com/docs/en/headless,
and https://code.claude.com/docs/en/cli-reference. Installed interfaces: Codex 0.153.4 and
Claude Code 2.1.261. The live review and execution limits are recorded in docs/ACCEPTANCE.md.

The implementation keeps Claude read-only and returns patch proposals to the Codex writer.
Unrestricted concurrent writers, a background daemon, and an unlimited fix loop were not
implemented: they need additional ownership, isolation, and spending controls. No new MCP
server or runtime third-party package is needed. Skill discovery does not authorize spend.

The old wrapper accepted transcript-only or conflicting verdict evidence. Regression tests
were first observed failing on both conditions, then passed after strict final-message
validation. A quoted second verdict is intentionally rejected as ambiguous, not resolved
by trusting the last line. Fresh review also exposed self-test environment leakage and
absent-test evidence; their fixes are regression-tested in temporary repositories.

The owner subsequently requested per-task usage history and useful continuation when a
child exhausts quota. The real failed Claude call had already consumed tokens and reported
API-equivalent cost, so success-only accounting would hide spend. Both directions now share
a bounded process runner and a local usage recorder. Timeout preserves partial output;
subscription percentages are not synthesized from token counts or public price tables.
The follow-up review found that usage could say completed before an archive write failed,
and the shell-owned Codex diff was not validated against later checkout state. Both adapters
now archive evidence before recording completion, and use the same snapshot implementation
for scope and staleness. Negative tests reproduce archive failure and checkout mutation.
Separate tests reject omitted kit architecture guidance and raw archives entering review
scope. Captured stdout/stderr now use bounded pipes: polling the size of temporary files
was not a hard disk bound, even when returned output was truncated correctly.
Running the new Python helpers also exposed an installer assumption: bootstrap copied local
bytecode alongside source, and the acceptance fixture then tried to decode it as text.
Bootstrap now skips Python bytecode; a synthetic binary-cache test was observed failing
before the correction and passes afterward. Bytecode is also ignored in both checkouts.
Official usage semantics were checked at https://learn.chatgpt.com/docs/pricing and
https://code.claude.com/docs/en/costs. Those values are not a per-call subscription debit.
Publishing raw account diagnostics was rejected; local ignored JSON retains the evidence,
while public acceptance notes carry only deliberately scrubbed conclusions.
The official Codex app-server `account/rateLimits/read` method provides supported account
window percentages and plan labels without starting a model turn. A live read succeeded;
the adapter uses bounded optional observations rather than scraping credentials or calling
undocumented endpoints. Before/after account observations are not per-invocation debits.

A live Codex run exposed a large-stdin deadlock in the new polling runner: after a short
`communicate()` timeout, retrying with no input could strand the unread remainder. A slow
child and a 200 KB input reproduced the failure before the fix. The shared runner now gives
the child a complete temporary stdin file and monitors its process, not partial pipe writes.

---

## Backflow findings

### 2026-07-26 — from the founding project (the codebase this kit was extracted from)

A Unity + .NET multiplayer game written almost entirely by CLI agents (Claude Code and
Codex). The findings below are what it paid for in real budget and real broken gates. They
are the kit's founding content, not later additions.

#### 1. Gates tend to fail OPEN, and a fail-open gate is worse than no gate — ACCEPTED

Three of that project's three gates were fail-open when first written, and every one of
them printed PASS while protecting nothing:

- The cross-model review script exited 0 when `git` produced no change set, so "nothing to
  review" and "the diff could not be collected" looked identical.
- The engine test gate wrote its results file to a path resolved against the ENGINE's
  working directory, not the shell's. The file landed where nobody looked, the engine
  exited 0 for a run that executed zero tests, and the gate reported PASS.
- The state-file rot gate counted every non-blank line under a heading as "active work",
  including the heading's own placeholder hint, so its condition could never be true.

The failure mode is identical in all three: the gate was verified GREEN and never verified
RED. Nobody had ever seen it fail. A gate that has only been observed passing is an
untested branch that runs in production on every commit.

What went into the kit: the rule that **a gate is not finished until it has been proven to
go RED**, and — because a one-off manual proof rots the moment the script changes — the
requirement that every gate ships with an automated NEGATIVE TEST that constructs the
failure condition and asserts the gate rejects it. `core/scripts/check.sh --self-test` is
the worked example.

#### 2. Gates, CI and review tooling are themselves a high-risk area — ACCEPTED

A broken gate disables every other protection SILENTLY. That makes gate code the single
highest-leverage place a defect can land: one wrong line there costs more than a wrong line
almost anywhere else, and it costs it invisibly, for as long as nobody looks.

The observation that proved it: **the session that wrote a gate could not validate its own
gate.** It ran the script, saw PASS, and reported the gate as working — while the gate was
structurally incapable of failing. A fresh reviewing session found it in minutes. That is
the review-gate invariant ("the author of a change never reviews it") demonstrated on the
review machinery itself.

What went into the kit: `core/docs/REVIEW_GATE.md` lists **gates, CI configuration, check
scripts and review tooling** as a PERMANENT risky area, present in every project regardless
of what that project does. It is the one entry in that list that is not a placeholder.

#### 3. The cross-session state file bloats, and pruning it destroys permanent knowledge — ACCEPTED

That project's `STATE.md` reached 906 lines / roughly 18K tokens — a bill paid at the start
of every session, in every tool. Two independent causes:

- **Completed work accumulated as a diary.** Items were marked DONE instead of deleted, so
  the file grew monotonically and the reader had to skim history to find the present.
- **Permanent lessons had nowhere else to live.** This is the dangerous one. Pruning a
  transient file buries permanent knowledge in the git history, where nobody looks for it.
  Git is an audit trail, not a knowledge base: "why is this rule here" is not a question
  anyone answers with `git log -p`.

What went into the kit, as four separate mechanisms because they fail separately:

- **The routing rule.** Before deleting a line, ask: *is this still true next month?* If
  yes, it must have a permanent home BEFORE it leaves. Homes: a design decision → the
  design document; a module or boundary → the architecture map; a process or gate
  constraint → the workflow doc; an environment or tooling trap → `GOTCHAS.md`. Permanent
  knowledge is never written INTO the state file; it passes THROUGH it.
- **Tagging at write time.** A line worth keeping is prefixed `[LESSON]` or `[GOTCHA]` the
  moment it is written. Harvesting is then a `grep`, not a re-read of the whole file — and
  the tag doubles as a flag meaning "this line may not be deleted until it has a home".
- **The template rule.** Completed work is DELETED, not marked DONE; the dates live in git.
  A multi-item operation tracks its progress in its OWN file with checkboxes, not as a
  growing list in the state file.
- **The gate, deliberately WITHOUT a fixed line limit.** Length alone is the wrong signal:
  1000 lines is healthy in the middle of a long operation and rot the day after it closes.
  The script can tell the two apart — it FAILS when the "Active work" section is empty
  while the file is still long, and stays quiet (or emits an informational note) while work
  is genuinely in flight. Note that this very parser was finding #1's third fail-open gate:
  it must count STRUCTURAL MARKERS (bullets), never lines, and must ignore placeholder and
  hint prose. It ships with a negative test.
- **The ritual.** The last acceptance item of every multi-item operation is *"the state
  file has been harvested and pruned"*.

#### 4. Parsing CLI output: strip ANSI, and never pass an empty field silently — ACCEPTED

The review wrapper extracted the run's token usage by grepping the CLI transcript. It
silently produced nothing, because the CLI wraps that phrase in ANSI colour codes — the
archived report recorded `tokens used<ESC>[0m` with no number, and nobody noticed, because
an empty field looks like a field.

What went into the kit: `core/scripts/review.sh` strips ANSI escapes before matching, and
an extracted field that comes out empty is REPORTED as not found rather than written as
blank. Same shape as finding #1 — absent evidence must be visible, not silent.

#### 5. A placeholder inside a comment is a fail-open gate waiting to happen — ACCEPTED

Found by the kit's own first end-to-end run, not by a project using it. `scripts/check.sh`
carried a `# {{BOUNDARY_CHECKS}}` line meant to be replaced in place. The first fill
substituted the marker but left the leading `#` on the first line, so the entire boundary
check sat inside a comment. The gate reported `CHECK: PASS`, enforcing nothing — finding #1
reproduced, in the very script written to prevent it, within an hour of writing it.

That is the useful part: the trap is not a lapse of care, it is a property of the design.
Any "replace this marked line with code" instruction can be half-followed, and a half-
followed edit to a gate fails silently by default.

What went into the kit: the checks and their negative tests live in their own sourced files
(`scripts/boundary_checks.sh`, `scripts/boundary_selftests.sh`), replaced WHOLE. When the
unit of replacement is a file rather than a line, the mistake is not available. Where a
placeholder must stay inline it is now a VALUE in a quoted string, never a statement.

#### 6. A gate's author cannot find its fail-open paths — ACCEPTED

The strongest evidence in this log, because it happened to this kit rather than to the
project it came from. v0.1 was written in one session, its gates were exercised, its
negative tests passed, and it was published with an acceptance record. A cross-model review
then returned **Reject** with seventeen findings, five of which were fail-open paths in the
gates themselves.

The two that matter most were invisible from the inside:

- **A bootstrapped project could never go green.** The placeholder scan flagged markers in
  `setup/INTERVIEW.md` and the module template — two files that carry them on purpose,
  forever, and that `sync-kit.sh` restores if deleted. The author's own acceptance test had
  missed it because that test deleted `setup/` before running the gate. **The verification
  was shaped by the same assumption as the defect.**
- **A failing file-listing became "no matches".** The producer sat on the non-final side of
  a pipeline ending in `|| true`, so a failed `git ls-files` was indistinguishable from a
  clean scan, and the gate went green having scanned nothing. This is finding #1 of this log
  reappearing inside the script written to prevent finding #1.

What went into the kit: the fixes, each with a negative test; `docs/ACCEPTANCE.md` rewritten
to separate what was executed from what was not; and the review report archived under
`docs/reviews/` as evidence rather than summarised.

What is worth keeping beyond the fixes: **an author's negative tests inherit the author's
blind spot.** They prove the failures you thought of. A second model is not a formality on
top of them — it is the only thing that finds the failure mode you designed your test
around. Reviewing gate code by a fresh session is now a permanent, non-placeholder entry in
`core/docs/REVIEW_GATE.md`; this is the third time in two repositories that the rule has
been earned rather than assumed.

#### 7. A review's FIXES are unreviewed code, and they fail the same way — ACCEPTED

Finding #6 ended with seventeen findings fixed and the kit published. A third model then
reviewed the FIXED tree and returned Reject again — eleven findings, two critical. The one
that matters:

Round 1's most serious finding was a scanner whose failure was indistinguishable from a
clean scan, because the producer sat in a pipeline ending `|| true`. The fix introduced
`scan_or_die`, which printed a diagnostic and called `exit 1` on a failed scan. It was
called as `hits=$(scan_or_die … | grep -Ev … || true)`.

`exit` inside a command substitution terminates the SUBSHELL. The diagnostic printed, the
subshell died, the main script carried on and reached `CHECK: PASS`. The fix for the
fail-open scanner was a fail-open scanner. Worse, the repository had by then written the
claim down in two places — the self-test's closing message and the acceptance record both
said the path was "enforced by construction" — so the false belief was now documented,
which is how it survives.

The general shape, and the reason this is a finding rather than a bug report:

- **A fix is written under time pressure, by the party who just accepted the criticism, and
  it is the least reviewed code in the repository.** Everyone's attention is on whether the
  original finding was real. Nobody asks whether the patch is.
- **Fixes cluster in exactly the code that was already subtle enough to get wrong once.**
  The second attempt is not safer than the first; it is written in the same place, by the
  same author, against the same blind spot.
- **A remediation commit tends to be self-certifying.** It ships alongside a document
  asserting the problem is now solved, and that document is what the next reader trusts
  instead of the code.

What went into the kit: `core/docs/REVIEW_GATE.md` states that **fixes made in response to a
review are themselves subject to the gate** — a Reject is not closed by the fixes, only by a
fresh pass over them — and that a claim of "enforced by construction" is a claim requiring a
negative test like any other. Where a construction genuinely cannot be tested, the acceptance
record says so instead of asserting the guarantee.

The mechanical lesson is worth its own line, because it is invisible and general: **in POSIX
shell, a failure signal that must escape a command substitution cannot be an `exit` or a
variable — it has to be a side effect on the filesystem.** The kit's scanner now drops a flag
file, checked by the main shell after every scan has run.

#### 8. A gate aimed at a path that does not exist is worse than no gate — ACCEPTED

Found by applying this kit's own review findings back to the project it came from, which is
the backflow loop working as intended — though in the wrong order: the fix landed in the
project first and reached the kit afterwards, which is exactly the drift `docs/UPDATING.md`
warns against.

That project's highest-risk check guards its money modules against floating-point
arithmetic:

```sh
hits=$(grep -rn --include="*.cs" -E "float|double" \
  shared/Core.Economy shared/Core.Trade 2>/dev/null | grep -v "// non-monetary:" || true)
```

Neither directory exists yet — that work is scheduled, not started. `grep` exits 2,
`2>/dev/null` hides the reason, `|| true` converts the failure into success, `hits` is
empty, and the most important gate in a project about a player-driven economy had been
printing PASS without reading one line, for its entire existence. Confirmed directly before
anything was changed: exit status 2, no output.

Two distinct traps, and the second is the one worth carrying:

- **A scanner pointed at a missing path is indistinguishable from a scanner that found
  nothing.** Only the exit status separates them, and `|| true` throws it away. This is
  finding #1's shape once more, arriving through a construct that reads as defensive.
- **A gate written ahead of the code it guards accrues the CREDIBILITY of a gate while
  doing nothing.** Everyone can see the check in the script, so nobody re-derives whether
  it fires. When the module finally lands — quite possibly under a slightly different name,
  because names change between planning and building — nothing announces that the gate
  missed it. The gate's silence is identical before and after.

What went into the kit: `core/scripts/boundary_checks.sh` tells the author to declare the
guarded paths in a variable, to check that at least one of them EXISTS, and to print an
explicit dormant notice when none do, rather than scanning nothing quietly. Absent evidence
must be visible — the same rule as finding #1, applied to the target of a scan rather than
to its result. The periodic-audit checklist gained the matching question: *does any gate
guard a path that no longer exists?*

#### 9. Non-goals need a home that is read every session — ACCEPTED

The founding project grew a document the kit had never shipped: a per-stage scope file
listing, for each stage, the question it answers, what to build, what NOT to build yet, and
how to tell it was done. Nobody planned it. It appeared because the work needed it, which is
the strongest signal available that a document belongs in the foundation.

What it prevents is the most expensive habit an agent has. "Build the inventory system"
gives an agent no edge to stop at, so it invents scope — persistence, a UI, an event system,
one monolithic file across five modules. "Build the grid placement rules; do NOT add
persistence, do NOT write UI, those are later phases" is the same task with a fence around
it. The non-goals are the useful half of a specification and the half everyone skips.

The reason it needs its OWN file rather than a section somewhere: non-goals only work if
they are in front of the agent before it starts. Put them in the design document and they
are not read (that file is deliberately not in the reading order). Put them in the state
file and they are deleted the moment the current task closes, so the next session re-invents
the same scope.

What went into the kit: `core/docs/PHASES.md`, read every session, holding the current phase
in full and later phases at one line each. Detail for a distant phase is aspiration, and
aspiration in an always-loaded file is a bill with nothing behind it.

This also settled the shape of the layer above it. Knowledge has three horizons, not two —
permanent (`PROJECT.md`, superseded but never deleted), episodic (`PHASES.md`, deleted after
harvest when a phase closes) and momentary (`STATE.md`). A separate ROADMAP file was
proposed and rejected: "offline support in v2" is both a decision and a plan, so a roadmap
document creates a seam with no clear side and the item gets written twice or lost. The long
view is one line per future phase at the bottom of PHASES.md. Full reasoning in
`docs/knowledge-has-three-horizons.md`.

#### 10. A living document an agent may write to needs an asymmetric permission — ACCEPTED

The appealing version of a project document is one the agent keeps current from
conversation. The dangerous version is the same sentence, and the difference is entirely in
what the agent is allowed to write.

An agent recording decisions autonomously will eventually promote a musing to a settled
decision, do it silently, and every session afterwards will treat it as law — while the
constitution's hardest rule says agents implement and do not design. The file meant to hold
the owner's decisions becomes where the agent's inferences accumulate, indistinguishable
from the real ones.

What went into the kit, as a deliberately asymmetric rule: **an agent may add OPEN items
freely and may never mark anything DECIDED.** Hearing what sounds like a decision, it
records it as OPEN with a note that the owner appeared to settle it, and asks.

The asymmetry is the point. A wrongly captured question is noise somebody deletes in a
minute. A wrongly promoted decision is invisible, binding on every future session, and
compounds — nobody re-reads a DECIDED item to ask whether it was ever really decided.

#### 11. Uncommitted work has no undo, and an agent will eventually take some — ACCEPTED

The reflog records COMMITS. `git reset --hard`, `checkout --`, `restore`, `clean -f` and
`stash drop` discard the working tree, and anything never committed is then gone with no
message, no trace, and a `git status` that looks clean afterwards.

It happened during this kit's own development, which is the only reason it is written down
rather than assumed. A `git reset --hard HEAD~1`, run to remove a throwaway test commit,
also took a set of uncommitted gate fixes and — worse — a long review record the owner had
written BY HAND and not yet committed. The fixes were re-typed from context. His paragraph
was unrecoverable from git and had to be reconstructed from a chat transcript.

Three things make this specifically an agent failure rather than a git one:

- **The command was correct for its stated purpose.** Removing a test commit is exactly what
  `reset --hard` does. Nothing about the invocation looked wrong.
- **The agent believed the tree was clean**, because it was thinking about its own work and
  had not looked at `git status`. The owner's edit was invisible to it.
- **The loss is silent.** No error, no warning, no diff. It surfaced only when the owner went
  looking for something he had written and found it missing.

What went into the kit: the rule in the constitution (commit or stash first, every time,
especially when sure), the reasoning in `GOTCHAS.md`, and — because a rule an agent promises
to remember is worth nothing here — a mechanism.
`overlays/claude-code/files/.claude/hooks/guard_destructive_git.py` blocks all of these
commands while the tree is dirty and prints the file list that would have been destroyed. It
allows `stash push`, `commit` and `--force-with-lease`, which are the recoverable ways to do
the same jobs.

The general lesson is not about git. **An agent's cleanup is the most dangerous thing it
does**, because it is the one action taken while attention has already moved to the next
task, and it is the one place where "I was sure" replaces looking.

#### 12. Every-session files are a recurring bill, not a style preference — ACCEPTED

Cached input tokens are discounted heavily, which makes the always-loaded prefix — the
constitution, the architecture map, the state file — the largest single cost lever in a
repeated-session workflow. Size there is money, and editing one of those files mid-session
invalidates the cache for every session after it.

What went into the kit: `core/docs/WORKFLOW.md` states the rule (keep always-loaded docs
small and stable, batch documentation edits into their own session, volatile state goes in
the on-demand state file), and the kit's own core files are kept short for the same reason.
`GOTCHAS.md` is explicitly NOT a session-start file — it is referenced from the
constitution in one line and read only when something behaves unexpectedly.
