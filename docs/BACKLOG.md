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
  `agent_usage.py` reads records with a bare `read_text()`; `check_kit.utf8_locale` decodes
  `locale -a` strictly. Name UTF-8 in each and add the suites that reach them to the sensor.

## Filed from v0.11 item F (Claude review r2, 20261013T164417Z-c2eb9992cc7d)

- The dispositions file is read once per reviewer attempt, not once per review: on a fallback
  the second adapter reads it again. Read the bytes once in `review_dispatch.py` and hand them on.
- A missing or non-UTF-8 `REVIEW_DISPOSITIONS` path raises a raw OSError/UnicodeDecodeError before
  the "no earlier rounds" message; read with `encoding='utf-8'` and wrap it in a BridgeError.
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
