# Review Gate — Tool-Agnostic (CANONICAL)

A change passes this gate before it reaches the main branch: in a single session before its
commit; for branch work, on the branch or the integration branch's merged commit, before that
merges into the main branch or is pushed (`docs/WORKFLOW.md`, "The lead's steps when a
branch is ready"). A worker may commit on its own branch before it. This is the one place
the timing is written. The reviewer reads this file; running a review is
`docs/REVIEW_RUNNING.md`.

## Invariant

**The session that wrote a patch never reviews or approves it.** The review runs in a FRESH
session, and the working mode's table names who takes it (`docs/WORKFLOW.md`, "Working modes,
by name"): in solo, another tier of the same family, never the author's tier; in cross, the
other family by the direction rule. This is the one place the rule is written; other documents
point here. One family is enough; a second vendor (`--reviewer codex`, a `claude@NAME`
backend) is pluggable, never required. No published measurement says how much another tier of
the same family adds. The lead names the author's model in `MYAGENTKIT_AUTHOR`;
`scripts/review.sh` then refuses a reviewer pin of the author's tier, blocks a substitute of
that tier, and records the author in the chain and the usage record. Without the variable the
lead checks independence before launch. A project's copy states this rule here only: an
upgrade replaces this whole section and deletes every other statement of who reviews whom,
in this file and in `AGENTS.md`, rather than keeping an older paragraph beside it.
Independence comes from the model family, not the CLI: a `claude@NAME` review of another
family counts as the second model; its record says the model was requested, unattested. A green gate is
necessary, not sufficient. The reviewer works in a throwaway copy without network or paid
model calls and marks each finding REPRODUCED or REASONED; its runs are evidence for
findings, not for acceptance, which is the gate run (`./scripts/check.sh`) on the reviewed head.

## Risk tiers

The brief's `Risk:` line (`docs/HANDOFF.md`) names the tier: the higher of the row the changed
files fall into (table below) and the lead's proposal. {{OWNER_NAME}} may raise or lower it,
with the reason in the brief; a working mode never lowers it.

| Tier | What | Review |
|---|---|---|
| low | documentation (a behaviour-rule document such as `AGENTS.md`, `docs/WORKFLOW.md` or this file included), tests only, one file outside the rows below | one light reviewer, medium effort |
| medium | code in {{RISKY_AREAS}} outside the high row | one reviewer, medium effort |
| high | gates, hooks, check scripts, review tooling, the state helper (`scripts/working_mode.py`), deleting or moving files, concurrency, CI, tool settings | two fresh reviewers, `REVIEW_FOCUS=portability` and `logic`, each at high effort, one after the other unless {{OWNER_NAME}} allows parallel; {{OWNER_NAME}} reads the diff before the merge |

Before a high-tier merge the lead gives {{OWNER_NAME}} a ten-line summary and the diff. When
the diff is too long to read, a longer summary lists every changed file with its line counts,
every open or deferred finding and every manual check, and {{OWNER_NAME}} may ask for the diff.

Every tier's review is a gate: the change does not pass without its result
(`docs/REVIEW_RUNNING.md`, "Unavailable reviewer"). Every review's Lows are capped as
`REVIEW_PROMPT` caps them (`scripts/claude_bridge.py`), the only place the number is written.

- **Review tooling** is the code that runs a review: `scripts/review.sh`, the bridges and the
  dispatcher (`scripts/claude_bridge.py`, `scripts/codex_bridge.py`,
  `scripts/review_dispatch.py`) and a reviewer's agent definition (the Claude Code overlay's
  `diff-reviewer.md`). The review protocol documents are documentation, the low row.
- **Critical work** is architecture, a gate's or the review tooling's design, and a security
  boundary. It is a mark beside the tier, not a tier: the brief writes `Risk: <tier>
  (critical)`, `REVIEW_RISK` stays the tier, and the mark changes only who writes and who
  reviews it (`docs/WORKFLOW.md`, "Model routing", rule 7).

## Rounds

At most two rounds under one label (`MYAGENTKIT_TASK_ID`); both adapters refuse a third
(`claude_bridge.prior_rounds`). A high-tier change keeps one label and rounds count per
`REVIEW_FOCUS`, so its logic and portability reviewers each get round 1 and round 2. A review
without a focus counts toward every focus. The rounds used are the current focus's count; an
unset or never-seen focus takes the highest count under the label, so unsetting or renaming
the focus never opens a fresh budget. The prompt's "round N" is that count plus one, and it
carries only the current focus's earlier reports and reports without a focus.
Every completed review whose archive matches its record is carried and counts. It leaves the
count only when the checkpoint the dispatcher wrote after that same attempt says the chain
failed (a checkout that changed during the review, `stale_checkout`); it is still carried. A
pending, missing or damaged checkpoint, or an earlier attempt's failure, leaves it counted.
Round 2 confirms every finding the dispositions claim fixed, a Medium
included, and reports new Critical or High only. A third round needs
`REVIEW_ROUND_EXCEPTION=<reason>`, kept in the record; what remains goes to {{OWNER_NAME}}
or an issue. Sources: KARARLAR B02 inv2#12 / D06 inv2#12; Claude Code Code Review's
re-review convergence and best-practices guidance on repeated corrections. The two-round cap
is the owner's choice. Round 2 runs only when round 1 left a Critical or High fix to verify.
The final review is due once per release, never per branch, and is written only here: one
fresh NEW-label review of the release's merged diff, high effort, by a session that did not
write its larger part; its Critical or High fix gets one re-read at medium effort, not a new
loop (`docs/WORKFLOW.md`, "The lead's steps when a branch is ready"). A high-tier branch thus
costs one round of its two focus reviewers, a verify-only round 2 when needed, and its share
of the one release review. Time target: about 20 minutes per reviewer, the sector's figure
(Anthropic Code Review averages 20, Cloudflare's P99 is 10; the kit's
`docs/research/ai-review-workflows.md`, finding 4 and S5); a round far past it is split.

## Verdicts and who decides

`Accept` / `Accept with Manual Checks` / `Reject`. Reject only on an open Critical or High.
An Accept whose own findings or manual checks a plain Accept cannot carry is read as the
stricter verdict: Reject when such a finding names Critical or High, else Accept with Manual
Checks; its first manual check names the correction (`scripts/claude_bridge.py`,
`stricter_verdict`).
A Medium is fixed in the round when the lead can verify the fix with a test; otherwise it is
an issue {{OWNER_NAME}} sees at the merge. A Low a reviewer reports goes to `docs/BACKLOG.md`
or an issue, never fixed in the round, because a fix adds code no reviewer has seen; a defect
the author finds while working is fixed in the task (`AGENTS.md`, "Task discipline"). Manual checks go into `docs/STATE.md` before the commit, so an
unverifiable claim becomes a standing obligation (owner decision; this is the one place the
rule is written). **A Reject is not closed by its fixes.** Round 2 reviews them. Sources:
KARARLAR D06 inv2#18; Yin et al., "How Do Fixes Become Bugs?" (2011), and GitHub protected
branches' dismissal of stale approvals.

The reviewer's output is unverified INPUT: the lead verifies every finding against the code
and owns the technical verdict; a verdict relayed verbatim is a failed review. When the lead
wrote the patch, the author of the patch drops nothing and issues no verdict of its own: it
records a disposition for each finding and reports the reviewer's verdict beside them; a
disproved finding goes to round 2 or to {{OWNER_NAME}}.
{{OWNER_NAME}} decides whether a change ships, a Medium's fate, "enough" after round 2,
taste, product direction and every OPEN item of `docs/PROJECT.md`; away, the lead files an
issue and goes on.

## Findings and dispositions

A finding opens with its severity (defined in `scripts/claude_bridge.py`, `REVIEW_PROMPT`)
and names file and line, trigger and wrong outcome. The author answers every earlier round
(round 1 by default; a third round answers rounds 1 and 2 again) in
`REVIEW_DISPOSITIONS`, one line per finding: `<id> fixed:<commit>`, `disproved:<evidence>`
or `deferred:<issue or decision>`. They are claims: a disproved finding counts only after
the reviewer has checked it against the code, and a deferred one stays open under Manual
checks, so it rules out a plain Accept. A design reviewed under its own label
(`docs/WORKFLOW.md`, "Design before code") supplies the exclusions a disposition cites.

## Priorities, in order

The order is {{OWNER_NAME}}'s choice and has no source: it starts with the doubt rule, and the
test-integrity floor below rests on it.

1. **{{TOP_RISK_PRIORITY}}**: a doubt here that the reviewer cannot tie to a file, line and
   triggering input is no finding: it goes under Manual checks, and {{OWNER_NAME}} decides it.
2. Boundary violations across modules or layers.
3. State: nothing half-written, duplicated or lost on a crash or retry.
4. Determinism: no ambient clock, randomness or hidden global state.
5. Test integrity: a weakened, skipped or deleted test, or untested core logic, is High at least.
   A deletion that consolidates tests measured as redundant or slow, with the measurement in
   the change, is not weakening; a deletion without it stays High. A logic change carries its
   test in the same change. A new test needs no red-proof record; ask whether it breaks when
   the code is reverted (the kit's `docs/research/test-rules.md`).
6. Gate integrity: a gate check observed RED, kept so by its bad-input fixture test.
7. Blast radius: every caller of every changed public member.
8. Scope creep: "Pre-existing", never fixed by the reviewer.
9. Design conformance with `docs/PROJECT.md` and `docs/PHASES.md`.

## What a reviewer attacks first

Classes `scripts/check.sh` does not cover yet; one leaves when its sensor lands. The worker
runs the list before reporting. A class that a ShellCheck rule already catches (e.g. SC2028,
SC2086) belongs in `scripts/check.sh`, not in this list; keep here only classes no static
check sees.

- Check-then-act windows: a freshness stamp hashed after the work certifies inputs edited
  meanwhile (fingerprint before, re-check before publishing, publish atomically, as
  `claude_bridge` binds the reviewed snapshot); a recursive delete of a directory that
  configuration chose, without proof the tool owns it (`AGENTS.md`, task discipline); trust
  in git's stat cache (`core.checkStat`, `core.autocrlf`, filters).
- Reflog message text; case-sensitive scans where git is not; byte work outside `LC_ALL=C`.
- Symlinks, hard links, FIFOs, `PATH_MAX`; Apple `mktemp`, dash as `sh`, a `.exe` under WSL.
  (`echo` with a backslash and an unquoted expansion left this list: `scripts/check.sh` runs
  ShellCheck, SC2028 and SC2086; NOT RUN where it is not installed, and there a reviewer still
  looks for them.)
- A hollow test; a guard with no killing test; a mechanism added where removing an operation would do.
