# Role-neutral review — current work

Updated by Codex on 2026-09-06 for the owner-authorized repair and push task.
The combined change starts at base `c358c917c212e002ae220926e1fc161ef240cec0`, includes
commit `7882a5a60e14bcce98c37275bcfbdc988cca96bf`, the subsequent failover/timeout work,
and the five review repairs in this task.

## Claude review is required and remains pending

The owner explicitly instructed Codex to fix the five confirmed findings, record that
Claude must still review the change, and commit and push on the owner's behalf before
that review. This is a task-specific exception to review-before-commit/push, not a change
to the kit's general policy and not an Accept verdict. No new paid review is being run
in this task. Claude must review the complete combined delta, including these repairs,
in a fresh read-only session. Reviewing only the last repair commit would miss the
previously unreviewed implementation. On a clean checkout, use base `c358c917`.

Astra and Claude both authored earlier parts of the combined implementation. The pending
owner-selected Claude review must retain that authorship context; this note does not
claim different-model independence for co-authored code. Neither the previous Astra
Reject nor this session's successful tests are independent acceptance of the final tree.

The requested Git identity is the owner's configured identity, with no AI co-author or
session trailers. The existing review/model pins, thirty-minute review deadline,
no-default-monetary-cap policy, bounded failover, and usage accounting remain in effect.

## Repair status

All five findings from `docs/reviews/20260905T193132Z-astra-combined-summary.md` have
implementation fixes and regression coverage:

- Private output requires ignored, untracked storage before model launch and during
  publication; symlinked storage is rejected, and temporary raw archives are ignored too.
- Malformed successful Claude envelopes are invalid evidence and cannot start failover.
- All Codex verdict declarations are counted. Malformed or conflicting declarations are
  rejected and retained only as unvalidated diagnostic prose in failed reports.
- Kit acceptance requires the named regression suites and rejects missing, empty, or
  skipped tests, including the packaging suite.
- `core/docs/DEV_SETUP.md` owns the complete runtime/test companion list. The upgrade
  regression imports that list and runs the upgraded wrapper with a fake CLI.

The new malformed-output and privacy regressions were observed failing on the old code.
The documented-upgrade regression reproduced the missing dispatcher import before the
list was fixed. Missing and skipped suite cases are exercised by the acceptance tests.
The full validation result for this repair is recorded in `docs/ACCEPTANCE.md`.
The final `./scripts/check.sh --self-test` passed with 50 runtime tests, five kit tests,
and the installed core negative gates. Packaged runtime parity also passed.

## Remaining work

- [ ] Obtain the owner's requested fresh Claude review of the full combined change.
- [ ] Verify any new findings, correct them, and review the resulting source again.
- [ ] Perform the outstanding live/manual checks listed below.
- [ ] Reinstall the Codex plugin after its source has been reviewed. The packaged source
      contains these repairs; the installed cache has not been replaced in this task.

Live Claude compatibility, adversarial permission tests, a successful live proposal,
fresh-thread plugin discovery, a real-project upgrade, and a supported Python/OS matrix
remain unverified. The offline upgrade regression uses fake CLIs. The known working-tree
versus index pre-commit limitation remains out of scope. Historical evidence and prior
failed reviews remain in `docs/ACCEPTANCE.md` and the dated review summary; they do not
approve this source state. Related upstream issues have not been closed by this task.
