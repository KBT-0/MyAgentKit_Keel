# Kit BACKLOG — filed review findings and parked work

Low findings of the kit's own reviews are filed here, not fixed in the round (owner decision B,
2026-10-13). A line leaves when its work starts or when the owner closes it.

## Filed from v0.11 D-1 (Claude review r1, logic label)

- The Turkish-locale branch of `check_kit.locale_matrix` and its NOT RUN line have no test;
  patch `run` so `locale -a` lists `C POSIX` and assert the line (a regression there cannot
  produce a false pass: the PASS line names only the cases that ran).
- Text paths the locale sensor does not see (pre-existing, both r2 reviewers):
  `guard_destructive_git.py` runs a text subprocess without an encoding inside `except
  Exception`, so the sensor's EncodingWarning is swallowed (it fails safe: it blocks);
  `check_kit.utf8_locale` decodes
  `locale -a` strictly. Name UTF-8 in each and add the suites that reach them to the sensor.

## Filed from v0.11 D-5 (Claude review r1, portability, 20261014T131347Z-b5b427332134)

- Pre-existing: `check_kit` repeats in its final summary only the NOT RUN lines of unit outputs;
  the killing-test note's own NOT RUN line (no upstream branch, e.g. a detached CI checkout) is
  printed by `main()` early and not repeated, so it can be lost in a long output.
- Pre-existing (logic r2, v011-d5fix-logic): an added line whose content starts with `++ `
  shows in the `-U0` diff as `+++ ...` and is read as a file header, so the file's later
  refusals get no note or name the wrong file. Read `+++ ` as a header only outside a hunk
  (reset at `diff --git`).

## Filed from v0.11 R (Claude review r2, portability, 20261014T131242Z-d60c67ef7f45)

- `plain_report.py` CODE regex: a fence closes at any later fence of either kind, so a
  four-backtick fence holding a ``` line, or a ``` fence holding a `~~~` line, ends early and a
  label after it is bounced. Match the closing run to the opening one (same character, at least
  as long).

## Filed from v0.11 item F (Claude review r2, 20261013T164417Z-c2eb9992cc7d)

- The dispositions file is read once per reviewer attempt, not once per review: on a fallback
  the second adapter reads it again. Read the bytes once in `review_dispatch.py` and hand them on.
- A missing or non-UTF-8 `REVIEW_DISPOSITIONS` path raises a raw OSError/UnicodeDecodeError before
  the "no earlier rounds" message; wrap it in a BridgeError.
- Unkeyed answer lines are not counted; record `unkeyed: n` so the summary can show them.
- The Task, Total and Behaviour lines of `usage_summary.py` mix shadow runs into `rejects`,
  `findings` and `per_round`; report them there as a separate `shadow=` count.
- The dispatcher's chain record and result line do not mark a shadow review; add `shadow: true`
  and a `REVIEW [shadow]` line, and warn when `REVIEW_SHADOW` is left exported.
- A `model at capacity` answer is retried by hand, about ten minutes apart;
  the proposal's item H wanted an `unavailable` class in the adapter with up to twelve recorded
  retries. Owner decision 2026-10-13: a backlog line, not a mechanism in this batch.
- `claude_bridge.MEASURED` is module-level mutable state filled by `prior_rounds()`; return it
  from `prior_rounds()` instead and pass it to the record (AGENTS.md: no static mutable state).

## Filed from v0.11 final Codex review r1 (labels v011-codex-code, v011-codex-docs)

- `core/scripts/context_buckets.py:100`: when the twentieth post-compaction request is a refusal,
  the forward window stops after counting the request and omits its refusal; the backward window
  counts it, so the comparison is biased.
- `core/docs/WORKFLOW.md:482` requires sequential review runs unless parallel is asked, while
  Worker cost rule 6 and REVIEW_GATE require parallel reviewers for an authorized high-risk review.
- `core/docs/WORKFLOW.md:735`: the unconditional two-reviewer floor contradicts the risk table's
  one reviewer for a low- or medium-risk change.
- `docs/context-is-a-budget.md:90` still argues compaction at 200k with the retracted ten-turn
  cost figure; WORKFLOW gives about 25-49 requests.
- `core/docs/USAGE.md:111`: two default attempts are 2 x 2700 s = 90 minutes, not 120.
- `core/docs/DEV_SETUP.md:125` (pre-existing) says the review self-test needs POSIX, against the
  native Windows support at line 164.

## Filed from the v0.11 round-2 fix worker's notes (fix brief 3)

- `tests/test_close_worker.py` on native Windows (issue #56): the round-2 stubs (`uname` says
  Linux, tmux through `sh`) take the tmux path, but 17 of 23 tests still fail there: paths print
  with backslashes, the `windows()` cases meet the Codex process lister, the gate-lock case holds
  `fcntl.flock`, the lingering-session case sends SIGKILL, and the bad-name case finds a tmux call.
  Porting it is its own task; the suite stays excluded on Windows until then.
