# Codex-host Claude bridge — current work

Codex / GPT-6 Astra resumed the owner's task on 2026-09-05. The owner requested Claude
review, not another Codex review. The baseline kit commit is
c358c917c212e002ae220926e1fc161ef240cec0. No commit or push has been made.

## Implemented scope

The kit now has a Codex plugin for Claude review-and-fix and read-only patch proposals.
Both directions retain per-task usage and fail without blocking independent authorized work.
Account quota observations are not exact per-call subscription debits. Raw diagnostics and
usage stay local and ignored. The host remains the only writer and must not self-approve
a protected diff. No background daemon or unrestricted second writer was added.

## Current review status

The resumed Claude Opus 5/high invocation timed out after 600 seconds, with no final output
or reported usage. It did not report a quota error, but it is not successful review evidence.
Local artifacts are docs/reviews/20260905T080440Z-94d55e741d99-claude-review.json and
.myagentkit/usage/20260905T081440Z-25bbae76d0f1.json. Unknown usage is not zero usage.
The owner subsequently removed the default monetary cap for reviews and chose to start
the pending Claude review manually. Do not launch another review from this session.
The adapter and review skill now omit a monetary cap unless explicitly specified.
Timeout, turn, output, usage-accounting, and independent-approval safeguards remain.

The previous completed Sol review returned Reject. Its raw output is preserved in
.myagentkit/usage/20260905T022627Z-b7fea0f0ead5.json. All five findings were independently
checked against code and reproduced by negative tests; corrections are implemented:

- Raw archive exclusions now ship in core/.gitignore, with a summary re-include.
- Claude kit-layout guidance includes core/docs/ARCHITECTURE.md.
- Both providers use the same snapshot capture and stale-check implementation.
- Immutable evidence is published before usage can claim completed collection.
- Captured stdout/stderr use bounded pipes, not unbounded temporary output files.

These fixes still require a fresh accepting Claude review. Tests are not that review.

## Remaining work

- [x] Validate and transfer the latest corrections to the owner checkout.
- [ ] Await the owner's manual Claude review, verify findings, and resolve remaining defects.
- [ ] Complete a successful live patch-proposal smoke test; earlier attempts hit HTTP 429.
- [ ] Reinstall the updated Codex plugin after validation and review.
- [ ] Confirm skill discovery in a new Codex conversation.
- [ ] Commit and push the approved changes as previously requested by the owner.

The installed plugin remains myagentkit@personal version 0.1.0, not the updated source.
The owner-checkout `./scripts/check.sh --self-test` passed after transfer: 28 adapter/
process/accounting/quota tests, two packaging/bootstrap tests, and the core negative cases.
The official plugin validator and `git diff --check` also passed. The source plugin version
is 0.1.0+codex.20260905090559; it has not been reinstalled. Review remains pending.
After the owner-requested review-budget change, Codex / GPT-6 Astra ran the full owner-
checkout self-test successfully: 29 adapter tests, two packaging/bootstrap tests, and core
negative cases. The budget regression was observed RED before the change and GREEN after;
the plugin and changed skill validators passed. No real model invocation was started.
The current dated validation details and historical evidence are in docs/ACCEPTANCE.md.
The application repository has not been changed by this kit task.
