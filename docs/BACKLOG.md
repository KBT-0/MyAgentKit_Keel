# Kit BACKLOG — filed review findings and parked work

Low findings of the kit's own reviews are filed here, not fixed in the round (owner decision B,
2026-10-13). A line leaves when its work starts or when the owner closes it.

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

## Filed from v0.12 release prep

- bootstrap.sh / sync-kit.sh reviewer detection does not scan a symlinked `.claude/agents`
  folder (rdet round 2).
- #298 follow-up: a SessionEnd hook for orphaned tool processes whose shell already died (orph).
- #298 / orph: POSIX-only tests not run on the maintainer's Windows host (close_worker session
  tree, D3 start-time re-check, doctor's POSIX host list): the first CI / macOS run must confirm.
- `test_clean_worktrees.py` (POSIX only) not run for mfix's twin test: the first CI run must confirm.
- v0.10 upgrade checklist: the `rev-list --before=<date>` guess at a v0.10 project's `--base` can
  pick a later kit commit than the one the project synced from; sync-kit's base check stops only
  when a kit-owned file differs (mfix r2 light review manual check; kept, owner may revisit).
