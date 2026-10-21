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

## Filed from v0.12 bg worker migration (bge2e, bgspawn, bgmanage)

- `show_workers.sh` says "runs in the background" for a session whose state is done (bge2e Low).
- A finished bg session's row can vanish from `claude agents --all` without a kit `claude rm`
  (bge2e e2e2); close treats it as nothing to end, a later `--resume` of such a session is untried.
- POSIX: the bg suites' minimums (test_spawn_worker 98, test_spawn_codex 60/59, test_codex_worker 67/66,
  test_worker_visibility 95, test_close_worker 51, test_sync_kit 59) are the Windows deltas, not
  measured: the first CI run must confirm. `MYAGENTKIT_ROLE=worker` seen inside a live bg worker's
  hook is asserted only through the merged settings (bgspawn NOT RUN).

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
- check.sh once exited 1 after `KIT CHECK: PASS` with no message (concurrent git and review
  activity); a rerun under `bash -x` was clean, not reproduced.
- #293 code half (v0.13, gate round accounting): write worktree review records to the main
  checkout's usage dir (`git rev-parse --git-common-dir`), let a `--commit` round continue an
  `--uncommitted` round 1 of the same change, and fall back when `prior_rounds` evidence paths
  point into a removed worktree.
- #294: watch_workers.sh never checks a committed result against NAME.result-path's age, so after
  `spawn_worker.sh --resume` the first poll reports the earlier run's committed result again.
- #297: guard_secret_files.py does not see a shell write of a secret file (`echo >> .env`, `cp`,
  `Set-Content`) nor a read.
- #295 / #294 / usagesum: POSIX-only runs owed to the first CI run (test_clean_worktrees, the
  watch_workers suite under dash and macOS sh, the Windows-path usage_summary test's red).

## Filed from the v0.12 fix round (reports/fullrev-*.md; fixcl, fixhooks, fixkit, fixsync, fixworkers)

- fullrev-review L: a past-mode `--commit` of an older commit on a dirty tree is refused for a
  secret-looking or filtered file in the working tree the review never reads; the message blames
  the file, not the dirty tree (`claude_bridge.py` past mode).
- fullrev-review L: `review_dispatch.judge`, same-tier branch: a bad `MYAGENTKIT_AUTHOR_EFFORT`
  passes silently under the exception (effort is forced high, so the floor holds; the typo is
  not named).
- fullrev-review L: `agent_process.py:251` the checkout watch stops after one slow look and the
  record does not say so.
- fullrev-hooks M1: `guard_destructive_git.py` does not route `git checkout -B` / `git switch -C`
  through `moved_refs`; add it with an ancestor check (old tip reachable from the new start point)
  so `git checkout -B <current branch>` is not refused; `switch -f -C` returns the dirty-tree
  reason before the ref check.
- fullrev-hooks M2 (rest): `git clone URL && cd r && git submodule update --init` is still
  refused; skip the alias lookup for git's builtins (`git --list-cmds=builtins`).
- fullrev-gate L: `owns_check.py:24` FENCE allows more than three leading spaces; a fence inside
  a list item is indented by the item, so the fix needs list-context tracking.
- fullrev-gate L: `unity_gate.sh:93` prints the editor's stderr on a passing run too (whether a
  pass should hide it is a behaviour choice).
- fixsync: `sync-kit.sh` own_repo on Git for Windows: a kit path holding `'` gives no kit commit
  and no review line (MSYS does not convert such a path for git.exe); a silent degrade.
- fullrev-kitcheck M: the CI tier budgets (fast 1800 s, slow 10800 s) are unmeasured on 2-4 vCPU
  runners; set them from the first CI run.
- fullrev-kitcheck L: `check_actions` matches a basename anywhere in the ACTION text (README.md
  covers both overlay READMEs); match whole paths if a shared name ever lets a change through.
- fullrev-docs M5: push master and the release tag in one atomic push (release order).
- fullrev-workers L3: `spawn_worker.sh` place_brief: a plain spawn from a subfolder of the
  checkout with a brief outside it copies the brief and a `*` `.gitignore` to
  `SUBFOLDER/.myagentkit/workers/`, which no close removes (`wt_dir == top` skips the removal).
- fullrev-workers L4 (pre-exists): a lead in a linked worktree: the post-merge hook in main runs
  `close_worker.sh --finished` with no records there, so the lead's `NAME.*` records stay and
  `list_workers.sh` lists the worker as `absent` for good.
- fullrev-workers L5 (pre-exists): `watch_workers.sh` lone `--result` path: a ready result outside
  a git repository (`report_result` needs a HEAD) prints nothing and exits 0.
- fullrev-workers L6: a spawn refused after place_brief (the trust refusal) leaves `NAME.brief.md`
  in the lead's records with no worker; harmless, the next spawn of the name overwrites it.
- slowfix observation: `agent_process._supervise` does not collect output queued by the drain
  thread (Windows) or still in the pipe (POSIX) when the deadline hits at the loop head; a
  non-blocking `take(chunks, 0)` before the break, plus its POSIX twin.
