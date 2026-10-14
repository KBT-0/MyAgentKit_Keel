# Review Gate — Tool-Agnostic (CANONICAL)

A risky diff passes this gate before commit. The reviewer reads this file; running a review
is `docs/REVIEW_RUNNING.md`.

## Invariant

**The session that wrote a patch never reviews or approves it.** The review runs in a FRESH
session, preferably another model tier or family. One family is enough; a second vendor
(`--reviewer codex`, a `claude@NAME` backend) is pluggable, never required. Independence
comes from the model family, not the CLI: a `claude@NAME` review of another family counts as
the second model; its record says the model was requested, unattested. A green gate is
necessary, not sufficient. The reviewer works in a throwaway copy without network or paid
model calls and marks each finding REPRODUCED or REASONED; its runs are evidence for
findings, not for acceptance, which is the self-test on the reviewed head.

## Risk tiers

The brief's `Risk:` line (`docs/HANDOFF.md`) names the tier; the lead proposes it,
{{OWNER_NAME}} may change it, a working mode never lowers it.

| Tier | What | Review |
|---|---|---|
| low | documentation, tests only, one file outside the rows below | one light reviewer, medium effort |
| medium | code in {{RISKY_AREAS}} outside the high row | one reviewer, medium effort |
| high | gates, hooks, check scripts, review tooling, the STATE helper, deleting or moving files, concurrency, CI, tool settings | two fresh reviewers in parallel, `REVIEW_FOCUS=portability` and `logic`, one at high effort; {{OWNER_NAME}} reads the diff or a ten-line summary before the merge |

A documentation change that alters a behaviour rule (`AGENTS.md`, `docs/WORKFLOW.md`, this
file) gets one light pass, Low cap three, non-blocking.

## Rounds

At most two rounds under one label (`MYAGENTKIT_TASK_ID`); both adapters refuse a third
(`claude_bridge.prior_rounds`). A high-tier change takes one label per focus reviewer (`<change>-logic`,
`<change>-portability`), since the limit counts the completed reviews under a label.
Round 2 confirms every finding the dispositions claim fixed, a Medium
included, and reports new Critical or High only. A third round needs
`REVIEW_ROUND_EXCEPTION=<reason>`, kept in the record; what remains goes to {{OWNER_NAME}}
or an issue. A release gets one fresh NEW-label final review, high effort, by a session
that did not write its larger part (`docs/WORKFLOW.md`, "The lead's steps when a branch is
ready").

## Verdicts and who decides

`Accept` / `Accept with Manual Checks` / `Reject`. Reject only on an open Critical or High.
A Medium is fixed in the round only when the fix is one place and tested; otherwise it is an
issue {{OWNER_NAME}} sees at the merge, at once when the fix adds a mechanism. A Low goes to
`docs/BACKLOG.md` or an issue, never fixed in the round. Manual checks go into
`docs/STATE.md` before the commit. **A Reject is not closed by its fixes.** Round 2 reviews them.

The reviewer's output is unverified INPUT: the lead verifies every finding against the code
and owns the technical verdict; a verdict relayed verbatim is a failed review.
{{OWNER_NAME}} decides whether a change ships, a Medium's fate, "enough" after round 2,
taste, product direction and every OPEN item of `docs/PROJECT.md`; away, the lead files an
issue and goes on.

## Findings and dispositions

A finding opens with its severity (defined in `scripts/claude_bridge.py`, `REVIEW_PROMPT`)
and names file and line, trigger and wrong outcome. The author answers round 1 in
`REVIEW_DISPOSITIONS`, one line per finding: `<id> fixed:<commit>`, `disproved:<evidence>`
or `deferred:<issue or decision>`. They are claims: a disproved finding counts only after
the reviewer has checked it against the code, and a deferred one stays open under Manual
checks, so it rules out a plain Accept. A design reviewed under its own label
(`docs/WORKFLOW.md`, "Design before code") supplies the exclusions a disposition cites.

## Priorities, in order

1. **{{TOP_RISK_PRIORITY}}**: any doubt is a Reject.
2. Boundary violations across modules or layers.
3. State: nothing half-written, duplicated or lost on a crash or retry.
4. Determinism: no ambient clock, randomness or hidden global state.
5. Test integrity: a weakened, skipped or deleted test, or untested core logic, is a Reject.
6. Gate integrity: observed RED, kept so by a negative test.
7. Blast radius: every caller of every changed public member.
8. Scope creep: "Pre-existing", never fixed by the reviewer.
9. Design conformance with `docs/PROJECT.md` and `docs/PHASES.md`.

## What a reviewer attacks first

Classes `scripts/check.sh` does not cover yet; one leaves when its sensor lands. The worker
runs the list before reporting.

- Check-then-act windows: a freshness stamp hashed after the work certifies inputs edited
  meanwhile (fingerprint before, re-check before publishing, publish atomically, as
  `claude_bridge` binds the reviewed snapshot); a recursive delete of a directory that
  configuration chose, without proof the tool owns it (`AGENTS.md`, task discipline); trust
  in git's stat cache (`core.checkStat`, `core.autocrlf`, filters).
- Reflog message text; case-sensitive scans where git is not; byte work outside `LC_ALL=C`.
- Symlinks, hard links, FIFOs, `PATH_MAX`; Apple `mktemp`, dash as `sh`, `echo` with a
  backslash, unquoted interpolation, a `.exe` under WSL.
- A hollow test; a guard with no killing test; a mechanism added where removing an operation would do.
