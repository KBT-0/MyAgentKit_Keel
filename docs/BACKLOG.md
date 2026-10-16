# Kit BACKLOG — filed review findings and parked work

Low findings of the kit's own reviews are filed here, not fixed in the round (owner decision B,
2026-10-13). A line leaves when its work starts or when the owner closes it.

## Filed from v0.11 D-1 (Claude review r1, logic label)

- The Turkish-locale branch of `check_kit.locale_matrix` and its NOT RUN line have no test;
  patch `run` so `locale -a` lists `C POSIX` and assert the line (a regression there cannot
  produce a false pass: the PASS line names only the cases that ran).
- A text path the locale sensor does not see (pre-existing, both r2 reviewers):
  `check_kit.utf8_locale` decodes `locale -a` strictly. Name UTF-8 there and add the suites
  that reach it to the sensor.

## Filed from v0.11 D-5 (Claude review r1, portability, 20261014T131347Z-b5b427332134)

- Pre-existing: `check_kit` repeats in its final summary only the NOT RUN lines of unit outputs;
  the killing-test note's own NOT RUN line (no upstream branch, e.g. a detached CI checkout) is
  printed by `main()` early and not repeated, so it can be lost in a long output.
- Pre-existing (logic r2, v011-d5fix-logic): an added line whose content starts with `++ `
  shows in the `-U0` diff as `+++ ...` and is read as a file header, so the file's later
  refusals get no note or name the wrong file. Read `+++ ` as a header only outside a hunk
  (reset at `diff --git`).

## Filed from v0.11 final Codex review r1 (labels v011-codex-code, v011-codex-docs)

- `docs/context-is-a-budget.md:90` still argues compaction at 200k with the retracted ten-turn
  cost figure; WORKFLOW gives about 25-49 requests.

## Filed from v0.11 close-out batch 3 (KARARLAR D04 inv2#26)

- The project gate `core/scripts/check.sh` runs no ShellCheck, so the attack list in
  `core/docs/REVIEW_GATE.md` still carries classes a static rule sees (SC2028 `echo` with a
  backslash, SC2086 unquoted expansion). Add a ShellCheck step to the gate (NOT RUN when it is
  not installed, as the kit's own `check_kit` does) and drop those classes from the list.

## Filed from v0.11 close-out batch 6 (need a tmux host: macOS, Linux, or WSL with the owner's OK)

- Worker signals on tmux (KARARLAR D02 inv3#63, inv3#30): re-capture the `waiting_patterns.txt`
  fixtures on the current Claude Code (last 2.1.285; 2.1.300 installed on 2026-10-15); try the
  `Notification`/`Stop` state hooks as the watcher's first signal there (their delay, about six
  seconds, and the folder-trust dialog untried); try the instruction as claude's first
  positional argument instead of `send-keys` (is it taken after the trust dialog?).

## Filed from v0.11 close-out batch 4 (KARARLAR D04 inv2#117, inv2#118; a paid Codex run)

- Try `codex exec --output-schema <FILE>` (codex-cli 0.162.1 lists it) on one small Codex
  review: the schema of `claude_bridge.schema("review")`, the final message read as JSON. If the
  verdict, findings and manual checks arrive as JSON, `codex_bridge` reads them as the Claude
  side does and drops its Markdown parser (`review_parts` stays for the archive text). Not run
  in batch 4: the run spends Codex quota, and the owner was away.
