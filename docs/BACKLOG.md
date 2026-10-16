# Kit BACKLOG — filed review findings and parked work

Low findings of the kit's own reviews are filed here, not fixed in the round (owner decision B,
2026-10-13). A line leaves when its work starts or when the owner closes it.

## Filed from v0.11 final Codex review r1 (labels v011-codex-code, v011-codex-docs)

- `docs/context-is-a-budget.md:90` still argues compaction at 200k with the retracted ten-turn
  cost figure; WORKFLOW gives about 25-49 requests.

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
