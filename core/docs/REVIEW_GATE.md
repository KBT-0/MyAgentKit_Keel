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

## Running it

```
./scripts/review.sh [--uncommitted | --base <ref> | --commit <sha>] [--reviewer codex|claude]
```

It collects the change set with git, hands it to a read-only REVIEWER carrying THIS
document's priority order, archives the report as evidence under
`docs/reviews/<UTC-timestamp>-<random>-<reviewer>-review.md` and prints it. Omitting
`--reviewer` uses the one configured during setup at the top of `scripts/review.sh`.

**The two directions are interchangeable, not merely both present.** Each archives the same
header table — reviewer, model, whether the model is attested, effort, sandbox, limits,
scope, reference, HEAD, checkout fingerprint, diff hash, status, failure kind — followed by
exactly one `VERDICT:` line, or none at all when the run failed. The renderer refuses a
header that has drifted, and refuses to print a verdict for a run that did not complete, so
"same format" is enforced rather than agreed.

**Both models are pinned by name, in both directions.** An unpinned run archives whatever
default the CLI happened to have that week, which no later record can be compared against;
the wrapper stops rather than record it. Claude's model is additionally ATTESTED — the
adapter matches the pin against the CLI's own `modelUsage` — while Codex publishes no model
identity in its output, so its record says the pin is requested but unattested. The
evidence says which of the two it is instead of implying a check that did not happen.

The script accepts no flags beyond those above: the reviewer is matched against a closed
list and arbitrary user flags are not passed through to the underlying CLI. Both adapters
require Python 3.10+ and do not resume an author session. Claude restricts source tools to
Read/Glob/Grep and disables customizations and MCP. Codex requests its read-only sandbox
and never-approve policy; it does not implement Claude's tool allowlist or customization
isolation. A shared evidence format does not imply identical permission mechanisms.
Reference reviews require matching clean checkout context. Both share scope collection and
checkout fingerprint validation, so a change while the reviewer runs invalidates its
result, and evidence is published exclusively before usage can say completed.

`./scripts/review.sh --self-test` exercises both adapters' offline failure cases and is
included in `./scripts/check.sh --self-test`; these self-tests require Python 3.10+ for
both providers. Missing tests or missing completion evidence fail. Exit 0 from a reviewer means collection
completed, not that the verdict is Accept. Missing final evidence fails closed.

**The output is unverified INPUT.** The requesting agent verifies every finding against the
code, drops what it disproves, keeps what it confirms, and owns the verdict. Relaying a
reviewer's verdict verbatim — in either direction — is a failed review. A confirmed
critical finding is a stop signal.

Reviews cost budget: {{OWNER_NAME}} must have asked in this session or explicitly authorized
a bounded automatic-review policy in the project's canonical instructions. Installing a
plugin or having the skill selected automatically does not grant spending permission.
The host must stop review-and-fix automation at its round limit and on unresolved owner
decisions. This is an agent instruction, not an adapter-enforced session counter or
authorization check. The adapter enforces per-invocation limits only. Automation never
authorizes a commit, push, deployment, or an author-only approval. The host is responsible
for choosing a different reviewing model; `--requester` is reported metadata, not attestation.

## Unavailable reviewer

Reviews have no default monetary budget cap. Pass a supported monetary-cap option only
when the owner explicitly specifies one. This does not remove timeout, turn, output,
authorization, or provider-account limits; it does not authorize automatic retries.

If a reviewing CLI cannot finish because of quota, context exhaustion, timeout,
authentication, or missing final evidence, do not treat that failure as Accept. Both
adapters return a failure with a local usage record. Codex uses `REVIEW_TIMEOUT_SECONDS`
(1800 by default); Claude reviews use `--timeout` (1800 by default). Timeout stops the child process
group and preserves captured partial output. Through the wrapper, `REVIEW_TIMEOUT_SECONDS`
sets the timeout for each provider, with the same 1800-second default. This is a total
wall-clock deadline, not an idle timer: active work can continue beyond ten minutes, but
is still stopped at thirty minutes by default. Claude's final-JSON output does not provide
reliable startup/activity detection. Two timed-out default attempts can take about one hour
plus local processing and quota-observation overhead. There is no purchase
of extra credits and no retry of the same provider.

The wrapper and bundled `review_dispatch.py` automatically try the other configured model
once after an operational failure: quota, authentication, timeout, missing CLI, CLI error,
context exhaustion, turn/budget exhaustion, or output limit. Both model pins remain owned
by project setup (`REVIEW_CLAUDE_MODEL` / `REVIEW_CODEX_MODEL` override them). An absent or
invalid alternate pin stops failover rather than choosing a model. Direct adapter calls
remain single-provider. A completed Reject or manual-check verdict is a result, not an
availability failure; it never triggers another provider. Invalid evidence, wrong model
attestation, invalid scope, missing guidance, changed checkout, and evidence/usage storage
failures stop the chain. The original scope is checked between attempts and at completion.

Each attempt retains separate evidence and usage. Immutable checkpoints under
`.myagentkit/usage/chains/<chain-id>-<attempt-count>.json` link the attempts; these are not
additional token records. The final `review dispatch:` JSON names the selected reviewer or
failure. At most two provider attempts occur per invocation. If both fail, leave review
pending and continue independent authorized work; never restart an exhausted chain
automatically. A review-and-fix round is separate from a provider attempt and may consume
two calls; hosts must account for that when applying task-level authorization.

If the fallback model authored any part of the patch, its findings are advisory only.
The host must check all patch authors before treating any completed result as independent
review; neither a new process nor automatic failover grants author-independent approval.

Record the affected task, evidence path, and pending review in current project state. Then
continue independent authorized implementation, tests, or documentation. When Claude was
providing an optional implementation proposal, the host can implement the task itself;
this is not independent review. Do not commit or push a protected diff before its required
review is satisfied. If no independent work remains, hand off the blocker instead of
waiting indefinitely. Accounting details live in `docs/USAGE.md`.

## Template to paste (tools without a wrapper)

```
You are the safety diff reviewer for {{PROJECT_NAME}}. You are READ-ONLY: no file edits,
no state-changing commands.

Read AGENTS.md, docs/ARCHITECTURE.md and docs/REVIEW_GATE.md, then review the diff below
in the REVIEW_GATE.md priority order. Grep the callers of every changed public member.

Report each finding with the file, the line, why it is wrong, and how it fails concretely,
so the calling agent can verify or disprove it independently. Finish with a line
"VERDICT: Accept" / "VERDICT: Accept with Manual Checks" / "VERDICT: Reject", followed by
any manual checks written as full sentences ready to paste into docs/STATE.md.

[DIFF HERE]
```
