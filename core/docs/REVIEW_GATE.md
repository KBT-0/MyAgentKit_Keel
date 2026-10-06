# Review Gate — Tool-Agnostic (CANONICAL)

Risky diffs pass this gate before commit.

## Invariant

**The session that wrote a patch never reviews or approves it.** Review happens in a FRESH
session — preferably a different tool and the strongest available model, because the value
of a second opinion is that it is decorrelated. A passing compile is not a review;
`scripts/check.sh` PASS is necessary but not sufficient; implementer self-reports ("0
errors", "all tests green") are never validation.

## AUTHOR and REVIEWER are roles, not vendors

This document names two roles and never a product:

- **AUTHOR** — the session that writes the patch. It owns the change and the verdict it
  eventually acts on. It never approves its own work.
- **REVIEWER** — a fresh session running a DIFFERENT model. It produces findings and one
  verdict, which are input the AUTHOR verifies, not an approval the AUTHOR relays.

Which model holds which role is a project configuration, set during setup and recorded in
`scripts/review.sh`. It is expected to change: the roles follow the budget, and the budget
moves. A project that runs out of the AUTHOR's quota mid-phase swaps the two and keeps
working — the invariant is that the author and the reviewer are different models, never
that a particular vendor sits on a particular side.

Because the roles swap, **both directions publish the same evidence format** (same header
table, same one-line verdict contract, same `docs/reviews/<stamp>-<reviewer>-review.md`
naming). Records made before and after a swap line up against each other. Two formats would
mean each reader — and the self-test — had to learn both, which is how one of them stops
being checked.

## What counts as a risky diff

When multiple models have authored the combined change, select a fresh reviewer that did
not author any of it. Keep the reviewer read-only; an author verifies and implements its
findings, then requests fresh review of the corrections. An existing local commit without
review is still unreviewed work, not an exception that moves this gate to push time.

A diff is risky when a silent bug in it is expensive, hard to attribute, or slow to
surface. For this project:

{{RISKY_AREAS}}

**Always, in every project, whatever the project does:**

- **Gates, CI configuration, check scripts and review tooling.** A broken gate silently
  disables every other protection in the repository. That makes gate code the
  highest-leverage place a defect can land, and the place where nobody notices for the
  longest. The project this kit came from shipped three gates that printed PASS while
  protecting nothing.
  The observation worth keeping: **the session that wrote a gate could not validate its own
  gate.** It ran the script, saw PASS, and reported success while the gate was structurally
  incapable of failing; a fresh session found it in minutes. That is this document's
  invariant demonstrated on the review machinery itself.
  A gate diff is reviewed for one question above all others: *has this been observed going
  RED, and does an automated negative test keep it that way?*

**A change outside this list does not require a review.** {{OWNER_NAME}}'s own check, or the
manual check that the brief names, is its acceptance. A lead does not send such a change
through this gate by default. When a lead asks for a review anyway, it states the specific
doubt the review is to settle. In one project a change outside the list went through review
although no rule required it.

## What the reviewer reads

Root `AGENTS.md` → `docs/ARCHITECTURE.md` → the diff → ALL callers of every changed public
member (grep them; do not assume). Design authority is `docs/PROJECT.md` — its DECIDED items
are law, and the reviewer never decides an OPEN one.

## Review priorities (in order)

1. **{{TOP_RISK_PRIORITY}}** — the project's own worst failure mode goes first. Any doubt
   here is a Reject.
2. **Boundary violations:** a forbidden dependency crossing a layer; a module reaching into
   another module's internals instead of through its contract.
3. **State and persistence correctness:** an operation that must be atomic actually is —
   state may never end up half-written, duplicated, or lost on a crash or a retry.
4. **Determinism in core logic:** no ambient clock, no static randomness, no hidden global
   state. Clock and randomness are injected, or the code cannot be tested.
5. **Test integrity:** untested changes to core logic, or tests weakened, skipped or
   deleted to make a build pass — automatic Reject.
6. **Gate integrity:** if the diff touches a gate, CI or review tooling — was it proven to
   go RED, and did it ship with a negative test?
7. **Regression blast radius:** every caller of every changed public member.
8. **Scope creep:** changes the task did not require. Flag them; do not fix them.
9. **Design conformance:** conflicts with a DECIDED item in `docs/PROJECT.md`, or work
   the current phase in `docs/PHASES.md` puts out of scope.

## Verdicts

`Accept` / `Accept with Manual Checks` / `Reject`.

Manual checks are written to `docs/STATE.md` BEFORE the commit, as full explicit sentences.
Questions of taste, feel, balance or product direction go to {{OWNER_NAME}} — the reviewer
proposes, never decides.

**A Reject is not closed by its fixes.** The fixes go through this gate too, in a fresh
session, and a risky-area diff stays risky when the diff is the remediation. This is not
ceremony: a fix is written by the party that just accepted the criticism, it lands in the
code that was already subtle enough to get wrong once, and it ships beside a document
asserting the problem is now solved — which is what the next reader trusts instead of the
code. This kit's own first remediation replaced a fail-open scanner with a differently
fail-open scanner, and wrote "enforced by construction" in two places while it was false.

For the same reason, **"enforced by construction" is a claim that needs a negative test**,
exactly like any other. Where a construction genuinely cannot be tested, say so in the
acceptance record instead of asserting the guarantee.

## Findings, earlier rounds and dispositions

Asked only for "file, line, impact", a reviewer reports a different top few on every fresh
pass; one medium-size change took more than ten Reject rounds, each finding two or three new
Medium problems, many in code the previous fix had added. The reviewer therefore reports
every finding the pass can establish, each opening with a severity (Critical, High, Medium or
Low) and ending with a `Fix sketch:` — a direction the author verifies, never a patch to
paste.

When the prompt carries earlier rounds of the same change, the reviewer says for each earlier
finding whether it is fixed or still present, then reviews the whole diff again. The
author's dispositions (fixed in a commit, disproved with evidence, deferred to the owner) are
claims to verify, because the author never approves its own work: a disproved finding counts
only after the reviewer has checked it against the code, and a deferred one stays open under
Manual checks, so it rules out a plain Accept.

## A review loop: threat model, stopping rule, evidence

- **Write the threat model before a hardening or review loop starts.** It names what the
  change protects and what is excluded by decision. Agree the stopping rule with
  {{OWNER_NAME}} before the first round. Answer a finding outside the threat model with a
  disposition, not with a fix. Without a threat model, a loop over an adversarial reviewer
  has no edge: one project ran twelve rounds in one day.
- **A stopping rule ends the hunt for new classes of finding.** It does not excuse
  unreviewed code: every fix merged after a loop ends is still reviewed.
- **A platform the project claims is a platform it is run on** (in CI or by hand) before
  anything is called accepted. "NOT RUN: <platform>" repeated across rounds is a finding,
  not a footnote. One release passed on the development machine a dozen times and failed
  all four CI jobs on its first run.
- **A review that executed no tests is not test evidence.** The evidence that the tests ran
  is the self-test, run by the author or the lead on the reviewed head and named in the
  acceptance record.

Running a review, an unavailable reviewer and the paste-by-hand template are for the caller,
not the reviewer: `docs/REVIEW_RUNNING.md`.
