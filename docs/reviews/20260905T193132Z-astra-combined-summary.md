# Combined change review — 2026-09-05

This report records the pre-repair snapshot. On 2026-09-06 the owner authorized repairs
and push with Claude review pending. Current remediation and validation status is in
[the work note](../worktree-notes/role-neutral-review.md); the original findings and
review evidence below remain historical evidence, not approval of the repaired tree.

The owner requested a comprehensive fresh Astra review. The reviewer returned **Reject**,
and the calling Codex session reproduced all five findings. The combined implementation
remains rejected and has not received independent approval.

## Scope and provenance

- The source checkout was local commit `7882a5a60e14bcce98c37275bcfbdc988cca96bf`, plus
  all existing tracked and untracked working changes, including the failover dispatcher.
- The comparison base was `c358c917c212e002ae220926e1fc161ef240cec0`. A separate checkout
  at that base received the source files byte for byte, so its uncommitted diff included
  both the local commit and its subsequent changes. The raw report therefore records the
  **comparison base as HEAD**, rather than the source checkout's local commit.
- The requested model was `gpt-6-astra`, with high reasoning effort, a read-only sandbox,
  and a 1800-second limit. The direct Codex adapter completed in approximately 153 seconds.
  No alternate provider was invoked. Codex does not attest the model identity in its output;
  the model name is the requested pin.
- The review diff SHA-256 was
  `d4fa2d654ce72fec14755cd27df73c0e29ba787cc58f3531e8042308989ad13b`.
  Source file hashes still matched the snapshot before this summary and state update.
- Astra previously authored part of this implementation. This fresh process provides
  advisory findings; it cannot satisfy the project's different-model approval requirement.

## Verified findings

### P1 — Private diagnostics can be staged and then excluded from review

Location: `core/scripts/agent_usage.py:161`, with exclusions in
`core/scripts/claude_bridge.py:22` and `:34`.

Both adapters use the shared recorder, and the packaged plugin contains the same code.
In an existing project without the new ignore rules, a successful synthetic review wrote
raw usage and review records that `git add .` staged. The next review snapshot excluded
both staged records. This confirms accidental publication is possible while subsequent
diff reviews omit the evidence files. The kit checkout itself already ignores these paths.
The fixtures do not consistently require ignores or assert that diagnostics cannot be staged.

Require private evidence storage to be ignored and untracked before launching a provider,
or use an equivalent storage location that cannot enter project commits.

### P1 — A malformed Claude envelope triggers operational failover

Location: `core/scripts/claude_bridge.py:268`, with classification in
`core/scripts/agent_usage.py:94` and routing in `core/scripts/review_dispatch.py`.

A fake Claude CLI returned `{}` with exit code zero. The real wrapper classified the first
attempt as `failed/cli_error`, launched the fake Codex fallback, and returned a completed
chain with exit code zero. The missing envelope fields must be `invalid_evidence`, which
the dispatcher's documented contract forbids retrying through another provider.

Validate the envelope shape before preserving an operational classification, and add a
regression proving that malformed envelopes never launch the alternate provider.

### P1 — A conflicting rejection is removed from an accepting report

Location: `core/scripts/codex_bridge.py:89`, followed by
`core/scripts/agent_usage.py:59`.

A fake Codex CLI emitted a completed-turn event and this final response:

```text
VERDICT: Accept
VERDICT: Reject — unresolved defect
```

The adapter completed successfully. Its report contained only `VERDICT: Accept`; the
conflicting rejection and its explanation were gone. The parser counts only fully valid
verdict lines, while the renderer removes every line beginning with `VERDICT: `.

Reject malformed or conflicting verdict declarations before rendering, including a valid
declaration followed by an invalid declaration. The existing two-valid-verdict test does
not protect this case.

### P2 — Missing packaging tests do not fail the acceptance gate

Location: `scripts/check_kit.py:39`.

In a second disposable copy, deleting only `tests/test_packaging.py` still allowed
`./scripts/check.sh --self-test` to exit zero and print `KIT CHECK: PASS`. The general
test discovery ran the one remaining bootstrap test without requiring the missing
packaging suite. The explicit review-suite count does not protect this separate suite.

Require the expected suites to execute and reject missing or skipped gate regressions.
The missing-file case was reproduced; a separate skipped-test reproduction was not run.

### P2 — Existing-project upgrade instructions omit required companions

Location: `core/docs/DEV_SETUP.md:66`; related numbered instructions in `CHANGELOG.md:66`.

Copying the documented runtime and test companions plus the updated wrapper into a
synthetic project left out `review_dispatch.py`. Invoking the wrapper exited with code two
because that file was missing. The numbered changelog list also omits `test_agent_usage.py`
and `test_codex_quota.py`, which the review self-test runner imports. The earlier changelog
mention of the dispatcher does not repair these incomplete copy lists. `sync-kit.sh`
does not install these project-owned files automatically.

Use a single complete upgrade list and add an existing-installation upgrade regression.

## Validation and evidence

- The unmodified review snapshot passed `./scripts/check.sh --self-test`: 44 runtime,
  accounting, process, and quota tests; two packaging/bootstrap tests; packaged-source
  parity; and the bootstrap and core negative gates. That command also exercised the
  review self-test runner. Its standalone entry point was not rerun separately.
- Four focused offline reproductions confirmed the diagnostics, malformed-envelope,
  conflicting-verdict, and missing-runtime findings. They used synthetic repositories
  and fake CLIs and made no further model calls.
- The separate missing-packaging-suite acceptance run also passed, confirming the fifth
  defect despite the successful baseline.
- The immutable reviewer output is
  [the raw review](20260905T193132Z-2805ccdd35a8-codex-review.md).
  Its byte-identical local usage record is
  `.myagentkit/usage/20260905T193409Z-86399940d6a7.json`.
- Local verification logs, reproduction results, and source hashes are under
  `.myagentkit/review-verification/20260905T193132Z-astra-combined/`.
  Copied raw records retain their original temporary-checkout paths for provenance.

The live Codex collection completed. Live Claude compatibility, adversarial permission
tests, successful live proposal collection, fresh-thread plugin discovery, and a supported
Python/operating-system matrix were **not run**. The synthetic upgrade failure does not
replace a successful real-project upgrade test after remediation.

This was review-only work. No implementation files were changed, and no commit, push, or
plugin reinstall was performed. All five findings remain open. Confirmed fixes need
regression tests, the project gate, and fresh review by a model that did not author the
combined patch before independent acceptance can be recorded.
