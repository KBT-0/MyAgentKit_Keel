# Acceptance evidence

## Final issue repairs and live plugin checks — 2026-09-06

The final `./scripts/check.sh --self-test` passes on macOS/Python 3.14 with 59 runtime
tests, seven kit tests, installed core negative gates and packaged runtime parity.
The final two review findings and scanner error cases were reproduced before repair.
The initial hosted matrix passed both macOS jobs but failed both Linux jobs; the scanner
portability and negative-fixture repairs are included in this final local result.
The replacement hosted matrix is pending.

The Codex plugin was reinstalled as `0.1.0+codex.20260906131755`; all 11 installed files
match the source package. A fresh ephemeral Codex thread discovered both skills at that
version, read the review skill and read the preserved arithmetic fixture correctly.
Its reported write denial was not present as a command event in JSONL, so it is not
used as proof. A separate host-observed `codex sandbox -P :read-only` shell write probe
exited 1 with `Operation not permitted`, and no canary file existed afterward. The
profile identifier was verified against the official Codex source. This is a bounded
local sandbox check, not a full adversarial audit or proof of Claude permissions.

The existing-project upgrade used a disposable project bootstrapped from `c358c917` and
the documented companion list. Its earlier runtime self-test passed, and the fresh
host read the retained project context after the final companion update. No unrelated
production checkout was changed. The live probe produced a separate local usage record;
subscription consumption remains unknown, not inferred from account-window percentages.

Both review rounds returned Reject. All verified findings have fixes, but these last
repairs have not received another review because the two-round limit was reached. Claude
returned organization-level HTTP 403. The owner authorized commit/push with review
pending; final-source review and Claude live proposal/permission checks remain in #6.
Raw local evidence and logs are ignored under
`.myagentkit/review-verification/20260906-issues/`.

## Issue follow-up and second repair — 2026-09-06

The issue-specific commits address #1–#5. After the configured Astra fallback exposed
four more failures, each new regression failed before its fix and passed afterward.
The full `./scripts/check.sh --self-test` then passed with 57 runtime tests, six kit
tests, installed core negative gates and packaged runtime parity on macOS/Python 3.14.
The runtime tests also passed in an isolated project bootstrapped from `c358c917` and
manually upgraded using the documented companion list. This is a synthetic upgrade,
not an unrelated production project. Local logs are `/tmp/keel-round2-full-check.log`
and `/tmp/keel-upgraded-project-test.log`.

Claude was attempted but returned organization-level HTTP 403. The failure and the
completed Astra Reject are described in the dated scrubbed follow-up review summary.
The final review, hosted CI matrix and plugin discovery are still to be recorded.
Claude-specific live checks remain tracked by issue #6.

## Review repairs — 2026-09-06

Codex repaired all five findings in the dated Astra review summary. The final
`./scripts/check.sh --self-test` passed with 50 adapter/process/accounting/quota tests,
five kit acceptance/packaging/bootstrap/upgrade tests, and the installed core negative
gates. It also ran the installed review self-test suite successfully. Packaged runtime
parity passed. The full gate ran on the owner checkout without invoking a paid model.
Local logs are under `.myagentkit/review-verification/20260906-repairs/` and remain ignored.

The new malformed-envelope and conflicting-verdict regressions were observed failing
before the fixes. The privacy regression demonstrated a provider launch before storage
validation on the old code, then passed with the new preflight. The upgrade regression
reproduced the missing `review_dispatch` import from the old companion list before
passing with the complete list; it also runs the updated wrapper with a fake Codex CLI.
Missing, empty, decorator-skipped, and runtime-skipped required suites are exercised by
the acceptance regression. Private staging, tracked diagnostics, and in-repository
symlink redirection are covered. An intermediate full test caught an indented-verdict
rendering failure, which was corrected before the final successful run.

The owner explicitly authorized commit and push after these repairs with a fresh Claude
review still pending. No fresh Claude review, live proposal, plugin reinstall/discovery,
adversarial permission audit, real-project upgrade, or Python/OS compatibility matrix was
run in this repair task. The passing tests do not establish independent acceptance. The
current follow-up scope and the task-specific push exception are recorded in
`docs/worktree-notes/role-neutral-review.md`.

## v0.7 development — 2026-09-05

### Thirty-minute review deadline — Codex / GPT-6 Astra

The owner approved a thirty-minute total deadline as the alternative to reliable startup
detection. The current final-JSON Claude adapter cannot prove inactivity from silence.
The mocked-launch regression was run before implementation and rejected the old
600-second default on both direct adapters and both dispatcher routes. It then passed
with 1800 seconds, also checking that explicit overrides still reach the process runner.
No model was called and no thirty-minute wait was needed for this test.

The isolated-source `./scripts/check.sh --self-test` passed with 44
adapter/process/accounting/quota tests, two packaging/bootstrap tests, and core negative
cases. Plugin runtime equality, plugin validation, skill validation, and whitespace checks
passed. These checks do not establish live provider compatibility or independent review
approval. The plugin source was repackaged; installation and protected commits remain
pending the existing independent-review gate.

### Automatic operational reviewer failover — Codex / GPT-6 Astra

The owner requested one automatic attempt with the other configured model when the
requested reviewer is unavailable. The quota regression was run on the old wrapper and
failed for the intended reason: Claude returned exit 5 and Codex was not called. It passed
after the dispatcher was implemented. Offline cases now exercise both directions,
selected pins, identical scope, separate usage linked to one chain, authentication,
missing CLIs, timeout, context/turn limits, and both providers failing. Negative cases
verify that completed Reject/manual-check results do not switch models, absent alternate
pins do not choose defaults, and invalid/stale evidence or storage failure prevents failover.

The isolated-checkout `./scripts/check.sh --self-test` passed with 43
adapter/process/accounting/quota tests, two packaging/bootstrap tests, and the core
negative cases. Packaged runtime equality, the official plugin validator, skill validator,
and whitespace checks passed. The validators used an existing isolated PyYAML installation;
no runtime dependency was added. This is offline behavioral validation, not an independent
review verdict or a real subscription-exhaustion test. No paid model call was made.

After transfer, byte-for-byte source parity was verified and the owner-checkout
`./scripts/check.sh --self-test` passed with the same 43 plus two tests and core negative
cases. The final runtime packaging and whitespace checks also passed. This paragraph
records those executed checks and does not change the validated runtime. Plugin
reinstallation, independent acceptance of the final combined source, and commit/push
remain pending. The requested default remains Claude; no review monetary cap was added.

### Corrected delegation claims and default reviewer

The owner approved correcting delegation, sync, and independent-review statements, then
selected Claude as the default reviewer for Astra-authored work. Codex / GPT-6 Astra
implemented these changes in an isolated clone. Both hosts' review paths are documented
as delegation; the missing capability is a structured Codex proposal adapter. Synthetic
integration checks are not presented as independent acceptance of the implementation.
Project-owned wrappers do not change on sync alone. The review gate remains before commit,
not merely before push; neither co-author can independently approve the combined change.

The new Claude-default regression was observed failing with the old Codex default and
passing after correction; it also verifies explicit Codex selection. The isolated-clone
`./scripts/check.sh --self-test` passed with 34 adapter/process/accounting/quota tests,
two packaging/bootstrap tests, and all core negative cases. No monetary cap was introduced.

A non-authoring gpt-5.6-sol/high reviewer was invoked against the entire existing combined
commit 7882a5a, while that owner checkout stayed unchanged. At the 600-second timeout it
had emitted partial diagnostics but no final verdict or reported usage. The run stopped
with failed/timeout, not Accept. Its ignored local report is
`docs/reviews/20260905T142746Z-ab3b26b92d33-codex-review.md`; the local accounting record is
`.myagentkit/usage/20260905T143749Z-8cb30fdf716a.json`. Unknown usage is not zero cost.
No automatic retry followed, and no new commit or push is authorized by this result.
The later documentation/default-reviewer corrections still need independent review.
After transfer, the owner-checkout `./scripts/check.sh --self-test` passed with the same
34 plus two tests and core negative cases, and `git diff --check` passed. No new commit,
push, plugin reinstall, or additional model invocation followed. This final entry only
records validation; it is not an independent review verdict.

### Role-neutral review gate — Claude Opus 5 session

Ran by Claude Opus 5 on 2026-09-05, on the owner's checkout, on top of the uncommitted
Codex/GPT-6 Astra work described in the sections below. NOT independently reviewed — see
"What this session did NOT establish" at the end of this subsection.

**Both directions ran live**, against the same commit in a synthetic repository built for
the purpose (a two-function money module with a real integer-division defect):

| | reviewer | model | outcome |
|---|---|---|---|
| `--reviewer claude` | Claude Code 2.1.261 | `claude-opus-5` (attested via `modelUsage`) | completed, `VERDICT: Reject`, 7 findings |
| `--reviewer codex` | Codex CLI | `gpt-6-astra` (requested pin, unattested) | completed, `VERDICT: Accept with Manual Checks` |

Both reports were compared field by field: the header field list is byte-identical, each
carries exactly one `VERDICT:` line, and both record the same `fingerprint` and
`diff_sha256` for the shared scope. That the two models reached different verdicts on the
same diff does not by itself establish review quality or defect-detection coverage. These
were integration smoke tests, not independent review of the combined kit implementation.

**Eight gates were broken on purpose and observed RED**, each caught by a named negative
test, then restored:

| Deliberate break | Test that went red |
|---|---|
| Codex grows an extra header column | `test_both_reviewers_publish_one_identical_evidence_format` |
| Claude renames a header field on its side only | `test_both_reviewers_publish_one_identical_evidence_format` |
| Wrapper stops refusing an empty Codex pin | `test_an_unpinned_model_is_refused_in_both_directions` |
| Codex adapter stops refusing an empty pin | `test_an_unpinned_model_is_refused_in_both_directions` |
| A failed run is allowed to publish a verdict | `test_the_shared_renderer_refuses_a_drifted_header_or_a_verdict_without_a_run` |
| The renderer stops enforcing the field list | `test_the_shared_renderer_refuses_a_drifted_header_or_a_verdict_without_a_run` |
| The model's own verdict line is left in the body | `test_codex_wrapper_rejects_absent_and_conflicting_final_evidence` |
| The `--reviewer` closed list is opened up | `test_the_wrapper_accepts_no_reviewer_it_cannot_name` |

The verdict-stripping gate was not written speculatively: the first run of the new
cross-format test found that Codex's own prose repeated its `VERDICT:` line into the report
body, so a completed Codex review published two verdict lines and a FAILED one published a
verdict it had not earned. The fix promotes the verdict out of the prose in the shared
renderer, where no adapter can reintroduce it.

`./scripts/check.sh --self-test` passes: 33 adapter/process/accounting/quota tests (up from
29), two packaging/bootstrap tests, the bootstrap and core negative cases, and the packaged
Codex plugin runtime re-checked against canonical core.

**A test-harness defect was found and fixed while proving the above.** An early version of
the unpinned-model test cleared the pin through an environment variable, which POSIX `:-`
expansion then filled from the script default — so the test launched the REAL Claude CLI
instead of a fixture. It was killed. The suite's `review_env` now points both
`CLAUDE_CLI_BIN` and `REVIEW_CLI_BIN` at a nonexistent path by default, so a test that
forgets its fixture fails to launch rather than spending money.

**What this session did NOT establish:**

- No independent review of any of it. This session wrote the changes; the kit's own rule
  forbids it reviewing them. Both Astra and Opus contributed code; a non-authoring model
  must independently review the combined change. An author session cannot close this debt.
- The live runs used one small synthetic diff on one machine. They prove the two paths
  execute and agree on format, not that either handles a large or unusual repository.
- Codex's hook event names and schema were not verified, which is why no `overlays/codex/`
  was written. `openai/codex-plugin-cc` availability was not checked either.
- The `model_attested` distinction is a statement about what each CLI reports, not an
  independent verification that a specific model served the request.

### Resumed Claude review and remediation

Latest follow-up: the owner requested no default monetary cap for reviews and chose to
start Claude manually. The no-default/explicit-budget regression was observed RED then
GREEN. After implementation, the owner-checkout `./scripts/check.sh --self-test` passed
with 29 adapter tests, two packaging/bootstrap tests, and core negative cases. Plugin and
changed-skill validation and `git diff --check` passed. No live model call, reinstall,
commit, or push was performed for this follow-up. Independent review remains pending.

The owner resumed the paused work and explicitly requested Claude review instead of another
Codex review. The first resumed Claude Opus 5/high invocation reached its 600-second limit
without stdout, stderr, final evidence, or reported token usage. It was stopped and recorded
as failed/timeout, with unknown cost rather than zero cost. Its raw local evidence is
`docs/reviews/20260905T080440Z-94d55e741d99-claude-review.json`; accounting is in
`.myagentkit/usage/20260905T081440Z-25bbae76d0f1.json`. These artifacts remain ignored.
No accepting review, commit, or push resulted from this invocation.

While the owner checkout remained frozen for review, Codex / GPT-6 Astra verified the five
previously reported Sol findings in an isolated working copy. New regressions were observed
failing for missing kit architecture guidance, raw review archives not ignored by the
bootstrap template, archive failure leaving completed usage, stale Codex results after a
checkout mutation, and temporary output files exceeding a supposed hard capture limit.
The fixes share snapshot validation across both providers, publish immutable evidence
before completed accounting, include the omitted guidance/ignore rules, and bound captured
stdout/stderr with pipes. The separate Codex CLI-owned final-message file is checked after
execution; its on-disk size is not promised to be bounded by this capture mechanism.

The corrected isolated-copy gate subsequently passed with 28 adapter/process/accounting/
quota methods, two packaging/bootstrap tests, and bootstrap/core negative tests under
Python 3.14. The exclusive-write/path-containment regression passed. The new bootstrap
test first reproduced the accidental installation of local bytecode, then passed after
the installer excluded it. The official plugin validator and git whitespace check passed.
These are offline checks, not Claude acceptance of the corrected source. The next live
review requires the owner's renewed authorization after the timeout.

After transfer to the owner checkout, `./scripts/check.sh --self-test` passed with the
same 28 plus two tests and core negative cases. The official plugin validator and
`git diff --check` passed there too. The updated plugin source has not been reinstalled;
no accepting review, commit, or push is claimed. This final note is documentation-only.

### Usage/recovery follow-up

The owner requested usage attribution in both directions, useful continuation on exhausted
or unresponsive children, and a push after verification. Before implementation, regressions
demonstrated that quota failures had no normalized classification/usage record and timeout
discarded already-emitted usage. Both tests failed for those exact missing behaviors.

The updated offline suite passed: nineteen adapter/process/accounting test methods and one
packaging method, plus the bootstrap and core negative tests. Cases include Claude and Codex
quota/timeout, partial-cost retention, process-group termination, missing usage as unknown,
cache/reasoning non-double-counting, task filtering, and ignored local accounting records.
Fresh independent review and the push are pending in the current work note; green tests are
not substituted for that review. The original invocation history below is retained as dated
history, not a claim that later code was reviewed by the earlier Claude session.

A first Codex Sol review attempt was stopped at its 600-second deadline with no final
message or usage. The attempt was recorded as failed/unknown, not as a zero-cost review.
Diagnosis reproduced a large-input stdin deadlock in the polling runner. The 200 KB
slow-reader regression was observed failing before stdin changed to a complete temporary
file. A live read of Codex's official account-quota endpoint succeeded without a model turn;
three offline tests cover its allowed methods, privacy filtering, and bounded failure.
These corrections and quota observations require the next fresh review, not retroactive
approval from the timed-out attempt.

### Initial bridge validation

Implemented by Codex / GPT-6 Astra in a temporary clone of clean kit HEAD
`c358c917c212e002ae220926e1fc161ef240cec0`, on macOS with Python 3.14, Codex CLI 0.153.4,
and Claude Code 2.1.261. No commit, push, or public release was performed.

- Offline adapter regressions, packaged-runtime drift tests, syntax checks, and the
  bootstrap's absent-configuration RED/configured-fixture PASS were executed successfully.
  The pre-review `./scripts/check.sh --self-test` passed. These use synthetic repositories
  and fake CLIs; they do not spend model budget or prove real provider behavior.
- Official plugin and both skill validators passed. PyYAML was installed only into a
  temporary validator dependency directory; it is not a kit runtime dependency.
- Legacy transcript-only and conflicting-verdict regression tests were observed failing
  before the wrapper was fixed. Both then passed.
- A real fresh Claude Opus 5 / high review completed with structured evidence, verified
  `modelUsage`, and a stable checkout fingerprint. The bridge exited 0 for successful
  evidence collection; the actual verdict was **Reject**, not approval. The invocation
  used 24 turns, a 600-second timeout, and a $3 CLI API-cost limit. Evidence:
  local raw file `docs/reviews/20260905T011858Z-215555c43676-claude-review.json`.
  This proves the installed CLI accepted the adapter flags and returned its real result.
- Confirmed review findings led to fixture environment isolation, missing-test/completion
  evidence checks, negative cases for the new gate branch, preserved legacy model defaults,
  explicit custom-guidance configuration, caller metadata, and documentation corrections.
  Three fake-CLI reports accidentally created in the temporary kit checkout were removed;
  they were not genuine reviews and were never committed or copied to the owner checkout.

- The post-fix `./scripts/check.sh --self-test` passed: eleven adapter test methods, one
  packaging test method, all existing core negative cases, and explicit rejection of a
  missing review test file, a failing runner, and a zero-exit runner with no evidence.
  The official plugin and both skill validators passed again after the corrections.

- The same full self-test passed in the owner checkout after transfer.
  `./scripts/review.sh --self-test` also passed with fixture reports confined to temporary
  repositories. The documented shell entry points are executable.
- `myagentkit@personal` version 0.1.0 was installed and reported both installed and enabled
  by `codex plugin list --marketplace personal --json`. Its source is the owner checkout;
  the cached plugin at `~/.codex/plugins/cache/personal/myagentkit/0.1.0` passed the official
  plugin validator. Packaging comparison and `git diff --check` passed in the owner checkout.
- A second fresh review of the corrections failed with Claude session-limit HTTP 429,
  CLI exit 1 and bridge exit 5. No verdict was returned. The CLI reported quota reset at
  08:50 Europe/Istanbul on 2026-09-05. Evidence:
  local raw file `docs/reviews/20260905T013255Z-f2da3898036f-claude-review.json`.
- A real `propose` call through the installed cached plugin, targeting a disposable counter
  fixture, failed with the same HTTP 429 before model work. It used 180 seconds, eight turns,
  and a $1 API-cost limit; it returned no patch. Evidence:
  local raw file `docs/handoffs/20260905T013656Z-7597120cc2e8-claude-propose.json`.

The first Reject must not be cited as acceptance of subsequent fixes. No source was edited
while either review was running. Fresh acceptance of the corrected code and a successful
live proposal remain outstanding; no third review or automatic quota-limit retry was made.
The quota blocker is not a skill failure and was not converted into successful evidence.

### Disposition of first-review concerns

Confirmed defects were fixed and checked as described above. Implicit skill discovery stays
enabled because it is a requested feature; host authorization and round limits are explicitly
documented as instructions rather than programmatic guarantees. Multiple final verdict lines
remain a deliberate fail-closed rejection, including quoted examples: choosing the last one
could silently replace a conflicting verdict. The different-model rule remains in README's
recommended-setup section; the adapter records reported caller identity but does not claim
to attest it. The usage follow-up keeps raw Claude JSON/account diagnostics local and ignored;
scrubbed review summaries remain versionable. Tests are isolated from the real repository. Documentation-only evidence
updates after the failed re-review are not presented as independently approved source.

Not verified: an OS-level read-only mount, adversarial CLI tool-denial testing, a successful
live patch-proposal invocation, Python 3.10 execution, Linux/Windows execution, or skill discovery
in a newly opened Codex conversation. Python 3.10 is the intended minimum, not a tested
version. Task-level authorization and round counts are host instructions; the adapter
does not enforce a cross-call session budget. Subscription quota accounting is not promised.

## Historical v0.1 record

A kit whose central rule is "a gate you have only seen pass has not been tested" cannot ship
on the strength of its author's assurance. This page records what was actually executed, and
— more usefully — what was not.

Anything not listed here was not verified. If a claim elsewhere in this repository is not
backed by something below, that claim is unproven and should be read that way.

## Two cross-model reviews, and what they found

v0.1 was written end to end in a single session by one model. That is exactly the situation
`docs/decorrelated-review.md` says cannot self-validate, so it was reviewed by other models —
twice, because the first round of fixes turned out to need reviewing too.

### Round 2 — Claude Fable 5, on the fixed tree

After the seventeen findings below were fixed, a third model reviewed the result read-only at
HEAD `70668e9`. Report:
[`docs/reviews/20260726T150630Z-master.md`](reviews/20260726T150630Z-master.md).

**Verdict: Reject. Eleven findings, two critical.** The important one:

| What it found | Status |
|---|---|
| `scan_or_die` was fail-open — its `exit 1` ran inside a command substitution and killed only the subshell, so the gate continued to `CHECK: PASS`. Round 1's fix for the pipeline bug had reintroduced the pipeline bug | fixed — a flag file crosses the subshell boundary, checked last, with a negative test |
| `guard_boundaries.py` read the edited text from `new_str`; the Edit tool sends `new_string`, so every violation written through Edit passed uninspected while the hook looked installed | fixed — both fields read, and the same bug fixed in the founding project |
| `sync-kit.sh` printed an EMPTY changelog when the recorded version was a prefix of a later one (`v0.1` vs `v0.10`) — an empty report reads as "no changes" | fixed — the version is matched as an exact field, not a prefix |
| A KIT-OWNED file inside an overlay could never be synced; and detection matched the bare phrase anywhere, so a doc that merely *mentioned* it would be overwritten | fixed — the marker is anchored to a header line, and overlays sync where installed |
| `bootstrap.sh` stamped `.kit-version` and wired the hooks path BEFORE refusing a dangerous retrofit, so `sync-kit.sh` then greeted a gateless project with "already current" | fixed — the stop precedes every state change |
| The comment-marker trap the kit banned was shipped in three of its own files | fixed — instructions to delete the `#`, and the hook's marker is now a live list element |
| The worked example in `boundary_checks.sh` taught the fail-open calling pattern | fixed — the scanner fix makes that pattern safe, and the file says so |
| An all-whitespace build command reached `sh -c`, exited 0 and passed the gate | fixed — whitespace is stripped before the test |
| `unity_gate.sh --self-test` left stub XML and a `Logs/` directory in the real project tree | fixed — it runs against a throwaway directory |
| `bootstrap.sh` iterated filenames line-by-line | fixed — a name containing a newline is refused outright |
| `review.sh` exited 0 when the report had no `VERDICT:` line | fixed — exit 5 |

Every fix was regressed on purpose and watched failing before being accepted; the scanner and
whitespace cases are quoted under "Verified by execution" below.

### Round 1 — Codex CLI, on the original tree

Reviewed read-only by a different model (Codex CLI, gpt-5.6-sol, high effort) on 2026-07-26.
Report: [`docs/reviews/20260726T141411Z-master.md`](reviews/20260726T141411Z-master.md).

**Verdict: Reject. Seventeen findings.** Five were fail-open paths in the gates themselves —
in the kit written to prevent fail-open gates:

| What it found | Status |
|---|---|
| A bootstrapped project could NEVER go green: `setup/` and the module template carry markers by design, and the placeholder scan flagged them | fixed — those two paths are exempt, and a case proves the exemption |
| A failed file-listing became "no matches", so the scanners went green having scanned nothing | fixed — the list is collected once into a file and its failure is fatal |
| A missing `boundary_checks.sh` was silently skipped | fixed — missing is now FAIL |
| An unconfigured build/test command was a warning | fixed — now FAIL |
| A missing or renamed `## Active work` heading disabled the rot gate entirely | fixed — both are now FAIL |
| The Unity gate died with `Illegal number` before reaching its zero-test check, and counted skipped tests as executed | fixed — counts validated, skipped excluded, document shape checked |
| `review.sh` exited 0 on an empty diff — the founding project's own bug | fixed — exits 3 |
| `review.sh` ignored failures to write its own report | fixed — unwritable or empty report is FAIL |
| Retrofit could finish "successfully" while leaving an existing no-op gate in place | fixed — bootstrap stops with exit 1 |
| `--self-test` claimed more than it proved | fixed — the message now states what is NOT covered |
| The tool-neutrality framing was false for the shipped automation | fixed — `.claude/` is an overlay; README and `review.sh` say what they target |
| "Local PASS == CI PASS" is disproved by this repo's own trap log | fixed — reworded everywhere it appeared |
| `ARCHITECTURE.md` demanded every boundary be enforced while also permitting "not enforced" | fixed |
| Filenames with newlines, or shaped like options, were skipped by the scanner | fixed — `git ls-files -z`, `--`, `-e` |
| `sync-kit.sh` word-split its file list on spaces | fixed |
| The acceptance numbers here were wrong (27 vs 29 files, 33 vs 34 markers) | fixed — see below |
| POSIX claim broader than the implementation | acknowledged, see "Not verified" |

Every finding was checked against the code before being accepted; none was relayed on the
reviewer's authority. Two were confirmed by reproducing them in a scratch shell rather than
by reading: the pipeline-status one and the `Illegal number` crash.

## Verified by execution

**`bootstrap.sh` produces a working skeleton in an empty directory.** 20 files from `core/`
plus 2 from `setup/`, `docs/` subdirectories created, executable bits set,
`docs/kit/.kit-version` written from the changelog. With `--overlay claude-code --overlay
unity`, both overlays land in the right places.

**The gate FAILS in a freshly bootstrapped project** — unfilled markers, and no build
command configured. Exit 1. An unconfigured project is not a green project.

**The gate PASSES once the placeholders are filled**, with `setup/` still present. The
earlier run that "proved" this had deleted `setup/` first, which is how the blocker above
went unnoticed; the current run does not.

**`check.sh --self-test` — twelve cases, all observed:**

```
ok — placeholder gate rejects an unfilled marker
ok — placeholder gate ignores setup/ and the module template
ok — rot gate rejects a long file nobody pruned after the work closed
ok — rot gate stays quiet while a real bullet is under 'Active work'
ok — rot gate rejects a MISSING state file
ok — rot gate rejects a renamed 'Active work' heading
ok — boundary checks missing is a FAILURE, not a skip
ok — an unconfigured build/test command is a FAILURE, not a warning
ok — a failing build/test command fails the gate
ok — an all-whitespace build/test command is unconfigured, not a no-op
ok — a failed scanner cannot report a clean scan
ok — domain boundary gate rejects a forbidden import
```

**The self-test catches a broken gate**, in three separate sabotage runs:

- The rot parser was reverted to counting non-blank lines instead of bullets, so the
  section's own hint text reads as work. Self-test FAIL, exit 1.
- The scanner was reverted to the round-1 design, where the failure path `exit`s from inside
  a command substitution. The gate **stayed green** — reproducing the critical finding — and
  the new case caught it: `FAIL — a failed scanner cannot report a clean scan: the gate
  stayed GREEN with its failure condition present.`
- The build-command guard was reverted to matching a single literal space. Same result: the
  gate stayed green with `"  "` configured, and the case caught it.

A negative test that cannot detect the historical bug is not a negative test.

**The boundary hook was proven against real tool payloads.** A violation sent as an Edit
(`new_string`) fires; the same violation sent as a Write (`content`) fires; a clean edit
stays silent; a project that deleted the guard line is not nagged; and the previous field
name (`new_str`) was re-run against the Edit payload to confirm it stayed **silent** — the
bug was real, not theoretical.

**The self-test refuses to run on a red tree**, and prints the baseline output rather than
asserting why it was red.

**`unity_gate.sh --self-test` — three cases, no Unity installed:** rejects a clean exit that
wrote nothing; rejects a results file that is not an NUnit document; rejects a run in which
every test was skipped. The last two came from the review.

**`review.sh` exits 3 on an empty change set** instead of reporting a silent success.

**`bootstrap.sh` refuses a dangerous retrofit.** Into a repository whose `scripts/check.sh`
was a `exit 0` stub: exit 1, with instructions for both choices.

**`bootstrap.sh` is safe to re-run.** A second run skips existing files and clobbers nothing.

**`--note` writes `docs/kit/BOOTSTRAP_NOTE.md`,** and `setup/INTERVIEW.md` reads it in Phase 0.

**`sync-kit.sh` respects both ownership tiers.** A local edit to project-owned `AGENTS.md`
survived; a local edit to kit-owned `.githooks/pre-commit` was overwritten; the changelog
since the recorded version was printed; `--dry-run` wrote nothing.

**Every shipped script parses.** `sh -n` on all shell scripts, `ast.parse` on the Python
hook, `json.load` on the settings file.

**No Layer 1 file names a tool or a domain.** `core/` mentions no engine, no vendor and none
of the founding project's nouns. The one exception is documented and deliberate:
`scripts/review.sh` names the Codex CLI, because it targets its flags and says so.

**`setup/` is self-contained.** Neither setup document references the kit repository's own
layout.

## NOT verified — read this part

**No second project has been set up with it.** The interview has never been run by an agent
with a real owner answering. That is the biggest unknown, and it is where the placeholders
and the phase ordering will show their edges.

**The ecosystem notes are unresearched.** The kit was extracted without a research pass of
its own; everything it says about specific tools, plugins and model routing is inherited
from one project over about two months and may already be stale. `RESEARCH_LOG.md` records
the baseline as "never run".

**`scripts/review.sh` has never completed a live run from this repository.** Its empty-diff
and argument paths were exercised; a full review through it was not. The report above was
produced by invoking the CLI directly with the same instructions. The kit's own trap log has
the entry for exactly this: a stub validates your argument handling, only a live run
validates the contract.

**The self-test does not prove attribution.** It proves each injection made the gate exit
nonzero, not that the INTENDED check fired rather than a different one reacting to the same
injection. The final message says so.

**The scanner-failure case breaks the scanner through a test switch**, not by making `grep`
or `git ls-files` genuinely crash. It proves the flag-file plumbing end to end — a failed
scan cannot end in `CHECK: PASS` — but a real crash could still fail in some way the switch
does not model.

**`sync-kit.sh` has never run against a genuine version upgrade.** Its version-collision,
marker-anchoring and overlay behaviour were tested with a synthetic changelog and a copied
kit; no project has yet been carried from one released version to the next.

**The Unity overlay's asmdef layout has not been applied from these files**, and no real
Unity run has gone through `unity_gate.sh`. Only its rejection paths were exercised.

**The editor-side hooks have never been observed firing at a real turn end.** They were
proven by direct invocation with fabricated input.

**POSIX portability is an intention, not a result.** The scripts parse under `dash` and
avoid obvious bashisms, but they rely on `xargs -0`, `grep -r`, `mktemp` and `trap ... EXIT`,
which are common but not guaranteed by POSIX. Only Linux under WSL was tested — no macOS,
no BSD, no Windows.

## How to re-run this

```sh
tmp=$(mktemp -d) && ./bootstrap.sh "$tmp" && cd "$tmp" && git init -q && git add -A
./scripts/check.sh                # expect FAIL: markers remain, no build command
# fill the placeholders and write the two boundary files, then:
./scripts/check.sh                # expect PASS
./scripts/check.sh --self-test    # expect every case observed going red
```
