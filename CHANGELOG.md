# CHANGELOG

What changed in the kit, dated, newest first. `sync-kit.sh` prints the entries added since
a project's recorded kit version, so an entry must say what a project OWNER has to do —
not just what moved. Mark anything needing hand-application with **ACTION**.

Versions are `MAJOR.MINOR`. MINOR adds or refines; MAJOR changes a rule or a file layout in
a way that existing projects must reconcile by hand.

WHY an entry exists belongs in `RESEARCH_LOG.md`; this file records WHAT changed.

---

## v0.9 — 2026-10-03

Hardening from the unreported findings of two projects using the kit, then from cross-model
reviews of the result. Why each change was made, and the review history that shaped it, is
in `RESEARCH_LOG.md` (2026-10-03). Most of the files below are project-owned, so the section
"Upgrading a project from v0.8" at the end lists what to do by hand, once, in order.

- **Gate lock (issues #19, #20, #11).** `scripts/check.sh` runs one gate per checkout at a
  time. It re-executes itself, by the path it was called with, under a few lines of Python
  holding `fcntl.flock` on `<git dir>/check.lock`; the gate and everything it starts hold
  the lock until the last of them exits, and the kernel releases it. Nothing is reclaimed
  and no pid is trusted: a nested run skips the lock only by proving the descriptor it
  inherited (`GATE_LOCK_FD`) is open on this lock file and held, so variables copied from a
  gate killed with SIGKILL fail `FAIL [env]`. A second run (Stop hook, commit hook, manual)
  waits with a NOTE every 30 s that names `fuser -v` and `lsof` on the lock file instead of
  sharing the build directory and reporting a false FAIL. `GATE_LOCK_WAIT=<seconds>` bounds
  the wait: when it runs out the gate prints `NOT RUN [lock]` and exits 75 ("did not run",
  neither pass nor fail); `pre-commit` and `pre-merge-commit` report that as "did NOT RUN,
  commit blocked", and the Claude Code Stop hook waits up to 500 s and reports "gate did not
  run". INT/TERM stop the run after cleanup. The lock works on NFS; a file system without
  locks, or a Python without `fcntl` (native Windows), fails `FAIL [lock]` by name. The gate
  now needs `python3`, and applies `toolchain_path`, now at the top of the script, before it
  looks for one. It ignores `CDPATH`. A build that leaves a compiler server or build daemon
  running holds the lock until that exits (`docs/GOTCHAS.md`). A commit made during a long
  self-test waits for it.
- **Self-test seams are not a bypass (issues #25, #11).** `--self-test` writes nothing into
  the working tree: its injections come from outside it (`GATE_SELFTEST_EXTRA_FILE`), and
  "a self-test case never changes a tracked file" is a rule in `check.sh` and
  `docs/WORKFLOW.md`. The overrides are `GATE_BUILD_CMD_OVERRIDE`, `GATE_SELFTEST_STATE_FILE`,
  `GATE_SELFTEST_PROJECT_FILE`, `BOUNDARY_CHECKS_FILE`, `BOUNDARY_SELFTESTS_FILE`,
  `GATE_SELFTEST_EXTRA_FILE` and `GATE_SELFTEST_BREAK_SCANNER` (`STATE_FILE` and
  `PROJECT_FILE` were renamed). Only the self-test's own nested runs, which hold the lock,
  honour them; any other run prints `FAIL [env]: <name> is set; ...` and exits 1. The
  self-test fails when `boundary_checks.sh` has checks but the boundary self-tests printed no
  `  ok   — <label>` line, and has new cases for the hooks loop, the commit-msg hook and the
  build failure output.
- **Scan (issues #13, #14).** The gate reads text in the C locale: in a UTF-8 locale
  `grep -I` printed nothing for a line holding a non-UTF-8 byte, so a placeholder on a
  Latin-1 line passed. The build command still gets your own locale. A tracked file deleted
  without `git rm` fails `[scan]` under its own name with the command that fixes it, and
  every other scan still runs. Every tracked symlink's link text is scanned and the link is
  never followed, so an unfilled marker in a dangling link fails the setup gate (a link in
  `setup/` stays exempt); only regular files reach grep. A directory symlink (`node_modules`
  linked into a throwaway worktree), a submodule or a repository inside the tree is skipped
  with a `NOTE [scan]` line. A real grep failure keeps its old message.
- **Build output (issue #23).** The build step is quiet on a pass. On a failure it prints
  `FAIL [build]`, the last 150 lines (the whole log when `CI` is set) and the path of the
  full log, never a filtered subset. Keep deploy-shaped steps, dry runs included, out of the
  build command.
- **Commit gates (issues #16, #24).** `.githooks/pre-merge-commit` (new, kit-owned) runs the
  gate for the commit a clean `git merge` creates, where git does not run pre-commit; git
  older than 2.24 has no such hook and leaves merges ungated (`docs/DEV_SETUP.md` says so).
  `.githooks/commit-msg` (new, kit-owned) rejects an AI credit: a `Co-Authored-By`,
  `Signed-off-by` or `Assisted-by` trailer or a "Generated with" line whose whole name is a
  tool or model (quoted or not, from a list of current tool names), or whose address is a
  vendor's or a `[bot]`; a human name that contains a tool's passes. It checks the message whatever git later keeps: comment
  lines too, and nothing below a `commit -v` scissors line is cut (a credit quoted in that
  diff is rejected; commit without `-v`). It honours `Key : value` spacing, folded trailers,
  `trailer.separators`, `core.commentChar` and, on git 2.45 or later, `core.commentString`,
  and rejects the message when reading any of them fails. The line "No AI attribution in
  git" in `AGENTS.md` is the owner's switch: without it the hook passes every message; a
  missing or unreadable `AGENTS.md` keeps it on. The setup interview asks, and its opt-out
  also removes the worker definition's bullet.
- **Review tooling fails closed (issues #12, #9, #8).** A named reviewer is never silently
  replaced: `review.sh` fails when the requested reviewer cannot run, and `--fallback`
  (dispatcher `--allow-fallback`) allows one substitute whose evidence opens with
  `FALLBACK REVIEWER:`. A CLI that rejects a required flag (`cli_unsupported`) or cannot be
  launched after a cancel never fails over. A review scope with an effective git clean or
  process filter (any configured value) or `ident` is refused before launch, since the
  filtered diff can omit lines the fingerprint hashed. Ctrl-C, SIGTERM and SIGHUP kill the
  reviewer's process group and record `cancelled` wherever the cancel lands (launch, cleanup,
  the closing Codex quota read, the evidence and usage writes); a cancelled attempt never
  starts the fallback reviewer, a cancel after the reviewer finished keeps the completed
  review, and a signal the caller set to ignore (`nohup`, a background job) stays ignored.
  The Claude adapter prints a final `"correction": true` JSON line when a cancel lands while
  it prints its result; the last JSON line is authoritative. A failed quota read is
  "unavailable" and never costs a finished review its evidence. The usage record carries the
  archive's sha256 (a lost archive is `evidence_unavailable`); a malformed, unreadable or
  mismatching record, or a usage directory that cannot be listed, stops a labelled round
  (exit 2), and the refusal names the file and the command that moves it aside. An empty
  `MYAGENTKIT_TASK_ID` counts as unset. `review.sh` puts `~/.local/bin` at the end of PATH,
  not the front (an old binary there shadowed the current one), and ignores `CDPATH`. Claude's
  pin is attested only by its exact id or that id plus `-YYYYMMDD` (`claude-opus-5-5` used
  to attest the pin `claude-opus-5`; issue #36). One review resolves its base once, and the
  diff, the usage record and the carried-round check share that commit (issue #37). A Codex
  review that completed is not failed by a stream error it recovered from, such as an MCP
  reconnect (issue #34). A Claude review whose final result names an API error status is
  failed (`quota` for 429), never recorded as completed with a failure kind. The
  review self-test has a minimum test count per suite.
- **Review rounds converge (issue #18).** Both reviewers are asked for every finding, a
  severity (Critical, High, Medium, Low) on each, and a fix sketch. With the same
  `MYAGENTKIT_TASK_ID` a later round's prompt carries the earlier completed reviews from the
  reviewer's own archive, plus `REVIEW_DISPOSITIONS=<file>` for the author's answers. A
  disposition is a claim the reviewer verifies, never a settlement: a deferred finding stays
  open under Manual checks, and the closing Accept comes from one fresh review under a new
  label. Carried rounds must share scope and resolved reference with the new review, the same
  HEAD for `--commit` and `--uncommitted`, an ancestor head, and an archive whose sha256
  matches its usage record (a rebase, an amend or another head is refused and the message
  says to use a new label); they count toward the 400000-byte diff budget and show their
  verdicts as `Earlier verdict:`. A missing earlier archive exits 2 for both reviewers.
  `stale_checkout` still fails the review, and now says why and what to do.
  `docs/REVIEW_GATE.md` and `docs/USAGE.md` describe the rounds and the fallback.
- **Sync and bootstrap (issue #15).** `sync-kit.sh` records a new kit version only after its
  ACTION items are confirmed: it prints the entries, then the items again as a checklist,
  each item whole; leaves `docs/kit/.kit-version` unchanged and exits 2 until you rerun with
  `--actions-applied`. A line of the form `**ACTION** — none` is not an item, and versions
  without items are stamped as before. A kit-owned path holding a differing file without the
  KIT-OWNED header is reported as `conflict:`, and the sync copies nothing and keeps the
  stamp. A failed ACTION scan, or INT/TERM, never stamps. After a STOP, running
  `bootstrap.sh` again passes over every file identical to the kit's and lists only the
  files that differ; a differing gate file (`scripts/check.sh` or one of the three hooks)
  stops the run as `conflict: <path>`; `--force` overwrites every differing file listed.
  Both scripts judge every path they write or create one way (copied files, the version
  stamp, the note, the folders): each existing component below the target must be a real
  folder and the destination absent or a regular file; a FIFO, device, symlink, or a file
  where a folder belongs is a conflict that is not opened, `--force` included (a FIFO used
  to hang the run). Any failed write stops the run before the version is recorded or the
  hooks are wired (a regular file at `.githooks` used to end in a stamped project with no
  hooks). A retry after a failed run never records a version over a weaker state. There is no
  rollback: files a run already copied stay copied when a later step fails; each single
  file is either the old one or the new one, whole. A file is unchanged only when its
  content and its executable bit both match. Every file is written to a fresh `mktemp`
  sibling (`.kit-tmp.XXXXXX`) that takes the destination's mode first (a new file takes the
  umask's) and is then moved over it, so a full disk leaves the old stamp, note or hook
  whole and a 0600 note stays 0600; a stopped run's leftovers are named in a NOTE, not
  deleted. In bootstrap this run's own stamp move is the commit (a stamp that already held
  the version, on a re-run, is not): before it, a failure or INT, TERM or HUP puts the
  project's own `core.hooksPath` back; after it nothing is undone. Both
  scripts state their threat model in their header and `docs/UPDATING.md` repeats it: they
  protect against their own failures and interruptions and against honest mistakes in the
  tree, and by decision not against another process changing the tree during the run,
  files placed to attack them, or SIGKILL or power loss between two steps. Bootstrap's stop lists gate-file conflicts apart from
  other destinations it could not write. No script prints a supplied value through `echo`,
  so a backslash in a name or path is not turned into a terminal escape.
  `docs/UPDATING.md` and the README describe both.
- **`scripts/doctor.sh` (new, kit-owned; issue #10).** A machine check to run at session
  start, with one `MISSING: <what> — fix: <command>` line per trap and `DOCTOR: ready` or
  `DOCTOR: setup incomplete` (exit 1): mode 100755 on disk and in the index for every
  required hook and script (an untracked one is MISSING), `core.hooksPath`, the git identity,
  Python 3.10+, the six review runtime modules, `scripts/review.sh` with a readable
  `DEFAULT_REVIEWER="..."` line and the reviewer CLI it names (with `review.sh`'s
  `~/.local/bin` fallback and the `REVIEW_REVIEWER`, `REVIEW_CLI_BIN` and `CLAUDE_CLI_BIN`
  overrides; an explicitly empty one is MISSING), tmux where the worker script is installed,
  the `node` a git hook resolves with the PATH the gate really uses (`toolchain_path`) against
  `.nvmrc` (the login-less probe is a separate NOTE), the npm cache owner (three levels deep),
  `grep` shadowed by an alias or function in the interactive shell, a checkout under
  `/mnt/<drive>` on WSL, CRLF in a script, and an unignored `node_modules` symlink. It never
  evaluates `toolchain_path`: the line must read exactly `toolchain_path="..."`, only
  `$NAME` and `${NAME}` are expanded, an unset variable in it is reported, and a `check.sh`
  without the line gets a NOTE. A grep alias is accepted only when each word is a plain
  allowlisted option (`--color`, `--colour`, `--exclude-dir`). It changes nothing in the
  project; the grep probe starts the owner's interactive shell, so the shell's rc files run,
  under a 5 s bound on its whole process tree, and is skipped with a NOTE where `timeout` is
  absent.
- **Effort, STATE operation files, closing a worker (issues #17, #21, #30).** Delegated
  agents run at a stated effort: `worker.md` gets `effort: {{WORKER_EFFORT}}` (setup
  interview question 8), `diff-reviewer.md` gets `effort: high`, and WORKFLOW and HANDOFF
  say the brief names model and effort and the lead verifies both in the transcript.
  `docs/STATE.md` keeps a status line and a pointer; operation detail and worker results go
  to `docs/<OPERATION>.md`. A spawned worker session is
  closed by the lead once it has read the result file; `spawn_worker.sh` prints the command.
- **STATE.md stays clean by lifetime, not by size.** The next and parked tasks move to a
  new template, `docs/BACKLOG.md`, read when the next task is chosen, not every session;
  `docs/STATE.md` holds only what is in flight or waiting on someone, and its "Last session
  summary" heading is gone (it invited narrating finished work). A task may carry an id
  (K4, L1b: a letter first, at least one digit). The commit that finishes it carries one
  `Done: <id>` trailer per id; `commit-msg` rejects that commit while the staged STATE.md or
  BACKLOG.md still names the id, and `check.sh` fails `[state]` with file, line and closing
  commit when either file names an id any commit closed (git 2.22 or later; a shallow clone
  checks only the commits it holds and says so). A `Done:` value is exactly one id, read whole by the hook and the gate
  (folded values unfolded, the key in any case); a malformed one already in history closes
  nothing and gets a NOTE. A closed id is never reused, and the two templates name no id. Every length
  limit on STATE.md is removed: a limit saw neither a backlog that only grows nor finished
  work left in a live bullet.
- **How agents write.** `AGENTS.md` ("Language & style") states two registers and one rule
  above both. Chat and final answers: the result first, no restating, no prose between
  routine tool calls, listable facts in a list or table. Written artifacts another session
  reads cold (STATE.md, BACKLOG.md, operation files, handoff prompts, review verdicts,
  docs): full sentences, one instruction per sentence, a target of 20 words per instruction
  and 25 per description, active voice, one term per thing, numbered steps. Never shortened
  by a cap or a style: what failed, what was not run or not verified, a security warning,
  an action that cannot be undone. A worker's report defaults to 350 words with the
  sections "Not run / not verified" and "Noticed, not fixed" always present and outside the
  cap (`worker.md`, `docs/HANDOFF.md`). No standard or style product is named or required.
- **Worker routing and a documentation-only commit.** A worker runs the proof its brief
  names (`Proof:` in the brief skeleton); if it names none, it runs the gate; the expensive
  build or package step runs once, by the integrating session, after the merge. A review-fix
  round goes back to the worker that wrote the change while its context is not spent; a
  fresh worker takes it when the context is spent or the fix is a redesign; the reviewer is
  fresh in every round. A change outside the risky list does not require a review, and a
  lead that asks for one anyway says what doubt it is to settle (the blocking rule is
  unchanged). Work that ends in one exclusive resource is not run in parallel. The shape
  has a threshold: work expected to take more than about an hour, or more than one review
  round, runs in its own separate session the owner can talk to; a short read-only diagnosis
  or review runs as a sub-agent under the lead. `WORKFLOW.md` now says what the 2026-10-03
  comparison measured (cost per worker on one task) and what it did not (wall-clock,
  throughput, the lead's cost). `pre-commit` runs `check.sh --for-commit`: when every staged
  path is a regular `.md` file the build alone is skipped and the PASS line says so
  (`docs_only_skip_build=0` beside `build_test_cmd` turns it off); merges, manual runs, the
  Stop hook and the self-test always build. A staged submodule revision always builds, whatever
  `diff.ignoreSubmodules` or the submodule's `ignore` says.
- **A spawned worker is always visible, and watched.** `spawn_worker.sh` shows its session
  in a terminal tab once the worker has its brief (`--batch` defers; `scripts/show_workers.sh
  NAME...` opens a batch together in one window: Windows Terminal under WSL, iTerm2 or
  Terminal on macOS, otherwise it prints the attach line); its typed line tells the worker
  to write questions into its result file. `scripts/watch_workers.sh NAME...` returns when
  a session is gone or waits on a permission prompt, the folder-trust dialog or a question
  (`scripts/waiting_patterns.txt`, from real captures, each marked VERIFIED or UNVERIFIED).
  A spawned worker's result file starts with `Kind:` (`completed`, `blocked`, `handoff` or
  `progress`), `Task:`, `Attempt:` and `Remaining:`; only `completed` is done, an idle
  notice is a hint, and a worker that notices a compaction writes `Kind: handoff` at once.
  `watch_workers.sh --result NAME=PATH` reports DONE, BLOCKED, HANDOFF, PROGRESS or
  MALFORMED once the file is committed on a clean tree, QUESTIONS with their text when the
  file holds a "## Open questions" section (the lead asks them at once, one at a time), and
  CONTEXT once per session when the pane's status line shows more than `--context-warn`
  percent of the window used (the lead decides: finish, compact or hand off). The lead
  decides per task whether a finished session is reused or closed, from that figure, the
  idle time and the next task's length (`docs/worker-lifecycle-options.md` has the costs).
  `scripts/close_worker.sh NAME` closes a finished worker: it ends the tmux session (the
  terminal tab closes with it), waits up to 15 s for its processes to go, and removes the
  worktree through the same audit as the hook (`clean_worktrees.sh --apply --only=NAME
  --no-quiet`: the quiet period alone is lifted for that one worktree, because the lead has
  just decided the work is finished; the hook never lifts it); the branch is never deleted.
  `spawn_worker.sh`, `show_workers.sh`, `watch_workers.sh` and `waiting_patterns.txt` now
  carry the KIT-OWNED header, so a sync updates them where they exist.
- **Finished worker worktrees are removed after a merge, and only when nothing in them can
  be lost.** The new kit-owned `.githooks/post-merge` runs `scripts/clean_worktrees.sh
  --apply` (Claude Code overlay) after every merge that git completes in the main worktree.
  A worktree under `.claude/worktrees/` is removed only when every proof holds: registered,
  its own, not locked, no operation in progress, main on a branch; finished (a commit made
  in that worktree, its branch tip merged into main's branch); nothing reachable only from
  it (every object id the private git directory names is held by a ref, or is first saved
  under `refs/kit/saved/<name>-<time>/` by one atomic `update-ref`); every tracked file byte
  for byte what the index records and the index equal to HEAD; every untracked or ignored
  entry either in a disposable folder the project lists in `.claude/worktree-disposable`
  (matched exactly; never under `docs`, `.claude`, `.myagentkit`, `scripts` or `.git`,
  compared case-folded) or a regular file byte-identical to main's file outside every
  worktree and below no mount point; no mount point in the worktree or its git directory;
  quiet for 60 minutes (`quiet-minutes=` in the list); not in use (no process with its
  working directory inside, read fresh before each step through `/proc` or, elsewhere,
  `lsof`, which must show the script itself; no tmux session of its name; the gate lock not
  held); no filter or `ident` trusted: the bytes are compared. A branch is never deleted. The log
  `<git dir>/kit-worktree-removals.log` gets an `intent` line before anything is deleted and
  an `outcome` line after; the report prints the restore command. A failed `git worktree
  remove` is POSSIBLY MODIFIED and SIGINT, SIGTERM or SIGHUP during a removal is reported;
  both exit 1. Everything unproven keeps the worktree with its reason (`scripts/
  clean_worktrees.sh` is the dry run, `--all-reasons` prints every reason). Excluded by
  decision: a process changing a worktree's files, or main's copies of them, between the
  audit and the removal; files planted to attack the script; SIGKILL between two steps (a
  re-run is safe). Needs git 2.36. `KIT_NO_WORKTREE_CLEANUP=1` turns the hook off.
- **Six lessons become rules.** Before a review loop: write the threat model and agree the
  stopping rule; a stopping rule ends the hunt, not the reviewing of what is merged after
  it; a platform the kit claims is run before anything is called accepted; a review that
  ran no tests is not test evidence; a worker's "not done" line on something the brief
  asked for is a finding; under WSL a test never executes a `*.exe`.
- **Less context, same rules.** The always-loaded files lose a third (AGENTS.md, STATE.md,
  PHASES.md, ARCHITECTURE.md: duplicates and explanation moved to WORKFLOW and GOTCHAS, no
  rule lost) and the reviewer's document loses half: the caller's part of the review
  protocol moves to `docs/REVIEW_RUNNING.md`. `AGENTS.md` names sections, not whole files,
  and a test holds every named heading to its file. Passing suites print one line; a
  failing one prints its whole log. The Stop hook returns the whole failing gate output.
- **Faster review rounds, same coverage.** A worker that can start sub-agents reviews its
  own diff with fresh reviewers before it reports; reviewers are asked to run suites and
  reproductions in a throwaway copy and mark each finding REPRODUCED or REASONED; a new
  mechanism gets a one-page design review first; `REVIEW_GATE.md` gains "What a reviewer
  attacks first" and the worker a pre-report checklist pointing at it; the lead starts the
  self-test and two reviewers together under one label per feature.
- **The bridged reviewers execute, in a throwaway copy the adapter makes.** Codex runs
  `workspace-write` with the network off and Claude gets Bash, each with a copy of the
  checkout as its working directory, never the repository: the copy is built from the
  checkout's bytes (not a patch: git's stat cache and `apply.whitespace` cannot change what
  the reviewer reads), into a fresh tree that follows no symlink, under the review's one
  deadline, with its preparation processes killed as groups on a cancel; a temporary
  directory inside the repository is refused; the reviewer's environment names the
  repository through no variable and its git cannot discover a repository above the copy;
  the fingerprint covers the index as well as the working tree, so a reviewer's `git reset`
  fails the review as `stale_checkout`. Ten batched Codex rounds with the executing
  reviewer found and fixed the holes in this list (`docs/reviews/20261006T12*` to `16*`).
  A provider's content classifier stopping a run is `content_flagged`, an availability
  failure `--fallback` may route around.
- **A faster kit check.** The kit's own check runs its suites and acceptance phases at
  once where the CPUs allow (sequential under four), rebuilds only the PATH directories a
  fixture must change, scales its child timeouts with the degree of parallelism, and prints
  one line per unit with its seconds (`--timing` for a table). About eight minutes down to
  under two on a twenty-CPU host. The kit check reads bytecode only from a private folder
  (a stale `.pyc` of the same size and second was read even under `-B`), the bridged review
  prompt asks the reviewer to run the suite and reproductions, a `Done:` id
  matches the state files in any case, and the kit check prints a `NOT RUN:` line for each
  test that could not run on that host.
- **The bridged reviewers execute.** Each review attempt runs in its own throwaway
  `git archive` copy of HEAD with the uncommitted diff applied, made and removed by the
  adapter, with Codex in `-s workspace-write` and Claude given Bash, and the evidence's
  sandbox field says so (`core/docs/REVIEW_RUNNING.md`).
- **Rules (issues #26, #27, #28, #31).** A web request carries no personal data
  (`docs/WORKFLOW.md` "Web requests carry no personal data", HANDOFF brief item 3,
  `docs/GOTCHAS.md`). A sub-agent returns its report as its final message; only a spawned
  session writes a result file (WORKFLOW rule 7). Worktree-isolated agents run plain
  commands, one per call, and put compound work in a script file (`worker.md`, overlay
  README). A red gate that passes on re-run is recorded, not retried away (WORKFLOW,
  GOTCHAS).
- **The boundary self-test examples.** The worked existing-file example in
  `scripts/boundary_selftests.sh` runs its probe in a disposable copy of the checkout, for a
  plain repository only: a checkout whose `.git` is not a directory (a linked worktree, a
  submodule, a separate git directory) or that holds a nested repository is refused by name
  and reported `NOT RUN`, which fails the self-test, so run `--self-test` from the main
  checkout. The copy is made with `cp -RP` outside the checkout (a `TMPDIR` inside it is
  refused); an audit of each copy before its run refuses every symlink that leads
  out of the copy and fails by name on a folder or link it cannot read; the target and the
  gate are resolved physically and a symlinked one is refused; git and the copied gate run
  under `probe_env`, which passes only the variables it names, with an empty HOME and no
  system or global git configuration; the copy's `.git/config` is replaced by an allowlist
  plus the keys named in `probe_config_keys`, and its `.git/hooks` is emptied. The baseline gate run and
  the injected run each get a fresh copy with its own empty HOME and TMPDIR, and the
  baseline's copy is deleted first, so nothing the baseline run wrote (a hook, a git
  setting, a Python start-up file in HOME, a link swapped in, a rewritten gate) can act in
  the injected run; the tree is copied twice. Each copy is hashed as taken, and a checkout
  that changed between the two is reported `NOT RUN` (run the self-test again). The example
  changes no mode and deletes a copy only through the folder `mktemp` made, entry by entry
  from that open folder: a root that is no longer that folder is refused by name with
  nothing deleted (one stated limit: an empty directory swapped into the name between that
  check and the last `rmdir` is removed), and a copy the gate left unreadable fails the case with its path. The
  carried git settings are read from the copy, never from the live checkout again, and the
  hash covers every entry's permission bits and the git index. Any `include.path` or
  `includeIf` entry in the repository's configuration is refused by name (`NOT RUN`),
  whatever its condition: an include matching only the checkout could turn the real gate
  off while the copies ran it on. For the same reason a key named in `probe_config_keys`
  that has a value from outside the repository's own config file (system, global, worktree
  or command scope) is `NOT RUN` by name, checked once in the real checkout before the first
  copy; this needs git 2.26. `TMPDIR` is resolved once, so a relative one names the same
  folder for both copies. The dot-file
  example runs in a subshell that removes its injection on INT/TERM as well as on exit.
- **Worker spawning (issues #32, #35).** `spawn_worker.sh` `cd`s into the folder before
  starting the tool (tmux hands a new session a stale `PWD`) and ignores `CDPATH`. Every
  value it puts into the session command goes through one quoting helper. The brief is not
  pasted: the script types `Read '<absolute path>' and follow it.`, and refuses a missing or
  unreadable brief, or a newline in its argument, before any session opens. `--worktree`
  runs `git worktree add .claude/worktrees/NAME -b worktree-NAME HEAD` itself instead of the
  tool's `-w` and refuses a leftover branch or path of that name; a relative `--settings`
  file is made absolute against the caller's folder, and inline JSON may start with
  whitespace. A control character in the worker name or the brief path is refused before
  anything else, and no message prints a raw control byte. `unity_gate.sh` and
  `gate_on_stop.sh` ignore `CDPATH`.
- **Tests that could not go red.** Twenty-two guards in `doctor.sh`, `commit-msg`,
  `check.sh`, `claude_bridge.py` and `sync-kit.sh` had a negative test that stayed green with
  the guard deleted; each now has one that goes red. A case that cannot run (uid 0, an old
  git) is no longer counted as a pass, the suites no longer fail when the caller ignores
  SIGINT, and `check_kit.py` holds every suite to its current test count and every unit to
  a `UNIT DONE:` line printed after its checks (an early exit 0 passed). The boundary
  suites wait 30 s per step, times `MYAGENTKIT_TEST_TIMEOUT_SCALE` on a slow host, and a
  deadline that fires ends the child's whole process group and prints its output (issue
  #29).

### Upgrading a project from v0.8

<!-- Each numbered item is one checklist entry. sync-kit.sh prints an item from its marker to
the end of the item, so an item holds no blank line and no line that starts a list. -->

Work from the project's root, top to bottom. `KIT` is the kit checkout you run `sync-kit.sh`
from, and `5c80c36` is the kit's v0.8 commit.

1. **ACTION:** If this project was stamped past a version whose ACTION items it never
   applied, set `docs/kit/.kit-version` back to the last version really applied and sync
   again, so those versions' items are listed too. A script of yours that runs
   `sync-kit.sh` must expect exit 2 while items are pending.
2. **ACTION:** With the Claude Code overlay, do this before the sync: copy
   `scripts/spawn_worker.sh` from `$KIT/overlays/claude-code/files/scripts/` over yours,
   along with any other script of that folder the project already has. The v0.8 copies
   have no KIT-OWNED header, so the sync stops on them as `conflict:`. Then let the sync
   install the kit-owned files: `.githooks/commit-msg`, `.githooks/pre-merge-commit` and
   `.githooks/post-merge` (all new), `.githooks/pre-commit`, `scripts/doctor.sh` (new) and
   `setup/INTERVIEW.md`. If it stops with `conflict:` lines on any of those, the project has
   a file of its own at that path: move yours aside, run the sync again, then carry what
   your file did into the project by hand (the kit's `docs/RETROFIT.md`). If it stops on an
   overlay file, replace it with the kit's copy the message names and sync again. A symlink
   or special file at one of those paths, or a symlinked folder on the way to it, is a
   conflict too: replace it with a real file or folder first.
3. **ACTION:** Copy these files whole from `$KIT/core/scripts/` into `scripts/`, replacing
   yours (they hold no project content): `agent_process.py`, `agent_usage.py`,
   `claude_bridge.py`, `codex_bridge.py`, `codex_quota.py`, `review_dispatch.py`,
   `test_agent_usage.py`, `test_claude_bridge.py`, `test_codex_quota.py`. With the Claude
   Code overlay also copy `scripts/spawn_worker.sh`, `scripts/show_workers.sh`,
   `scripts/watch_workers.sh`, `scripts/waiting_patterns.txt`,
   `scripts/clean_worktrees.sh`, `scripts/clean_worktrees.py` and `scripts/close_worker.sh` from
   `$KIT/overlays/claude-code/files/scripts/`, and `.claude/worktree-disposable` from
   `$KIT/overlays/claude-code/files/.claude/` (the sync never adds an overlay file that is
   missing; `chmod +x` the `.sh` files and `git add --chmod=+x` them); list your
   build-output folders in `.claude/worktree-disposable` and run `scripts/clean_worktrees.sh`
   once as a dry run; with the Unity overlay, `scripts/unity_gate.sh` from
   `$KIT/overlays/unity/files/scripts/`. Copy `$KIT/core/docs/REVIEW_RUNNING.md` to
   `docs/REVIEW_RUNNING.md` (new) and fill its `{{PROJECT_NAME}}` and `{{OWNER_NAME}}`.
4. **ACTION:** Before the merge of the next item, split `docs/STATE.md` by hand: copy
   `$KIT/core/docs/BACKLOG.md` to `docs/BACKLOG.md`, move your "Next tasks" and "Deferred /
   parked" entries into it, delete the two headings and the "Last session summary" heading
   from `docs/STATE.md`, and delete every line that narrates finished, committed work (it
   is in git). Remove any size or line limit your own `scripts/check.sh` put on STATE.md.
   From now on name tasks by id in both files and end the commit that finishes one (or the
   merge commit that integrates it) with `Done: <id>`; never reuse a closed id.
5. **ACTION:** Merge the kit's changes since v0.8 into the files that hold your setup
   content, one three-way merge per file (yours, the kit's v0.8 copy, the kit's current
   copy). Start from a committed project: the next item compares each merged file with
   `HEAD`. Conflicts are left in the file as `<<<<<<<` markers for the next item:
   ```sh
   for f in AGENTS.md docs/ARCHITECTURE.md docs/DEV_SETUP.md docs/GOTCHAS.md docs/HANDOFF.md \
       docs/PHASES.md docs/REVIEW_GATE.md docs/STATE.md docs/USAGE.md docs/WORKFLOW.md \
       scripts/check.sh scripts/review.sh scripts/boundary_selftests.sh; do
     git -C "$KIT" show "5c80c36:core/$f" > "$f.v0.8" && git merge-file "$f" "$f.v0.8" "$KIT/core/$f"
     rm -f "$f.v0.8"
   done
   ```
   With the Claude Code overlay, run the same loop over `.claude/agents/diff-reviewer.md`,
   `.claude/agents/worker.md` and `.claude/hooks/gate_on_stop.sh`, with
   `overlays/claude-code/files/$f` in place of `core/$f` in both places.
6. **ACTION:** Resolve every conflict the merge left (`git diff --check` names each
   leftover marker) so that both sides survive: the kit's new structure, and everything your
   side added, that is each value you had filled in and every check, step or rule of your
   own. Never drop a line of yours without knowing what it did: taking the kit's side whole
   deleted a project's own check from the build arm and the gate still passed. Expect
   conflicts where a filled placeholder sits next to a kit change: the
   `.githooks/pre-merge-commit` sentence in `AGENTS.md`, `build_test_cmd` in
   `scripts/check.sh`, and the `model:` line of both `.claude/agents/` files; and wherever
   you extended a block the kit rewrote, such as a check of your own in the build arm of
   `scripts/check.sh`, which goes into the kit's new arm after its `fi`, before the `;;`.
   If you replaced `scripts/boundary_selftests.sh` with your own cases at setup, the whole
   file is one conflict: keep your side there and see the boundary self-test item below.
   Then compare each merged file with your pre-merge copy (`git diff HEAD -- <file>`) and
   account for every removed line. For each file `$f` of the previous item, with `$src` its
   kit path there (`core/$f` or `overlays/claude-code/files/$f`), this prints the removed
   lines (taken from inside the hunks, so a removed `- rule` shows too) that the kit's own
   change does not also remove; each must be a line of yours whose job
   now sits in a kit line (a value you put back, a kit line you had edited), never a check,
   step or rule of yours that is gone:
   ```sh
   git -C "$KIT" diff 5c80c36 -- "$src" | sed '1,/^@@/d' | grep '^-' > "$f.kit-removed"
   git diff HEAD -- "$f" | sed '1,/^@@/d' | grep '^-' | grep -vxF -f "$f.kit-removed"; rm -f "$f.kit-removed"
   ```
   Then fill the placeholders the merge brought in, which
   `./scripts/check.sh` lists: `{{OWNER_NAME}}` in new lines of `AGENTS.md` and
   `docs/WORKFLOW.md`, and `{{WORKER_EFFORT}}` in `.claude/agents/worker.md` (`low`,
   `medium` or `high`: the effort a delegated worker runs at, setup interview question 8).
7. **ACTION:** Check the configured lines of `scripts/check.sh`: `toolchain_path` must read
   exactly `toolchain_path="<path>"` with no trailing comment, or doctor reports it. The
   build command is the proof a commit must pass; a package or pipeline step that takes
   many minutes is an integration step outside it. Set `docs_only_skip_build=0` beside it
   only if your build reads markdown. The
   build command must not filter its output (remove a `grep error` filter: the gate prints
   the tail and the log path itself), must not leave a compiler server or build daemon
   running (it would hold the gate lock; `docs/GOTCHAS.md` shows the flags) and must hold no
   deploy-shaped step, dry runs included. The gate now needs `python3` on the PATH a git
   hook sees; `toolchain_path` is applied first. Add any override variable your own boundary
   checks read to the list in the SELF-TEST SEAMS block; the kit's list now also holds
   `GATE_SELFTEST_HISTORY`.
8. **ACTION:** Bring `scripts/boundary_selftests.sh` up to the new contract: every case
   prints `  ok   — <label>` when it passes; a case that writes into the working tree moves
   outside it, or removes its file on INT/TERM as well as on exit, as the kit's dot-file
   example now does in a subshell with its own trap. If you adapted the existing-file
   example, replace your copy with the kit's current one and adapt its target and
   diagnostic again, name each repository setting your gate reads in `probe_config_keys`
   (it must be set in the repository's own config file) and add each variable your gate
   needs to `probe_env` by name (a tool that needs a cache directory gets its own); if the
   repository's configuration uses `include.path` or `includeIf`, move the settings your
   gate reads into `.git/config`, or do not use the existing-file example; the same goes
   for a key you name in `probe_config_keys` that is set in your global or system git
   configuration.
9. **ACTION:** Decide the attribution rule. The merged `AGENTS.md` now holds the bullet "No
   AI attribution in git", and the kit's `commit-msg` hook rejects AI credit while that
   line is there. To allow AI credit, delete that bullet, and with the Claude Code overlay
   the block marked "attribution rule" in `.claude/agents/worker.md`.
10. **ACTION:** Outside the files: unset the self-test seam variables named in
   `scripts/check.sh` wherever a shell profile or CI step exports them, since a normal gate
   run now fails `FAIL [env]` on them; pass `--fallback` to `scripts/review.sh` in any
   automation that relied on automatic reviewer failover; a repository with Git LFS, a
   clean filter or `ident` in the review scope cannot use `review.sh`, so use the manual
   template in `docs/REVIEW_RUNNING.md`, "Template to paste"; and where `.gitignore` says `node_modules/` and
   `node_modules` is a symlink, write `node_modules` without the slash.
11. **ACTION:** Move aside the review usage records that v0.7 and v0.8 wrote with an empty
   task id, which now stop every review: find them with
   `grep -l '"id": ""' .myagentkit/usage/*.json` and move each with
   `mkdir -p .myagentkit/usage-set-aside && mv <record> .myagentkit/usage-set-aside/`.
   Rounds recorded before v0.9 are not carried: give the next review a new
   `MYAGENTKIT_TASK_ID`.
12. **ACTION:** Prove the result, in this order: `git add -A` (doctor requires every hook
   and script in the index with mode 100755), `./scripts/doctor.sh` (fix each `MISSING:`
   line), `./scripts/check.sh` (expect `CHECK: PASS`), `./scripts/check.sh --self-test`
   from the main checkout, then commit. With the Claude Code overlay, restart Claude Code so
   the agents' `effort:` lines take effect.
13. **ACTION:** As the lead, from now on: a brief names the worker's model and effort and
   you check both in the transcript; you close a spawned worker session once you have read
   its result file (`spawn_worker.sh` prints the command); a brief file stays in place
   until the worker has read it; a brief that sends an agent to the web names a generic
   User-Agent. Then record the version with `"$KIT/sync-kit.sh" . --actions-applied`.

## v0.8 — 2026-10-03

- **Worker cost (issue #22).** A measured rule set for routing workers lands in the
  `docs/WORKFLOW.md` template as the section "Worker cost — waits and long lives are what
  you pay for": a worker's cache must outlive its waits and it never polls, a review-fix
  round goes to a fresh worker, about 150 requests per worker, the lead does not poll,
  mechanical work to the cheaper model, short reports, cost read at the end of the day. The
  reasoning and the numbers are in `RESEARCH_LOG.md`. **ACTION:** copy the section into your
  project-owned `docs/WORKFLOW.md` (before "Token economics").
- `scripts/agent_cost.py` (kit-owned, synced): per-agent requests, cache read, cache write,
  cache write after gaps over five minutes, poll-only turns and the cache lifetime used,
  from a Claude Code session transcript and its sub-agents. `docs/HANDOFF.md` and the
  handoff command now ask for its table plus the tool's cost screen in an end-of-day
  handoff. **ACTION:** add the end-of-day paragraph to your project-owned `docs/HANDOFF.md`.
- Claude Code overlay: `.claude/agents/worker.md`, a worker definition with
  `experimental.cacheTtl: 1h`, `maxTurns: 150` and the worker rules in its body (placeholders
  `{{WORKER_MODEL}}`, `{{LONG_JOBS}}`), and `scripts/spawn_worker.sh`, which opens a separate
  worker session in tmux and pastes a brief file into it after the TUI is up. The overlay
  README documents the placeholders and the pitfalls. **ACTION:** overlays are not synced;
  copy both files from `overlays/claude-code/files/` by hand, fill the two placeholders, and
  restart any running session before spawning the worker.
- `docs/worker-cost-setups.md`: the six measured setups with their figures, a "which setup,
  when" table for projects that cannot use the first choice (the one-hour cache ignored, no
  tmux, CI, a different host), and the alternatives the research pass rejected with their
  evidence. The WORKFLOW template's rule 1 points at it for the fallback.
- The first real-task measurement is in `docs/worker-cost-setups.md`; `agent_cost.py`'s poll
  detector no longer counts a Python run or a plain `tail` as waiting; `spawn_worker.sh` takes
  `--effort`; the overlay README records that the idle notice fires on every background park.
- `setup/INTERVIEW.md` asks question 8, "Will workers run jobs longer than five minutes?",
  and fills or deletes the worker files from the answer. It also asks what a worker must know
  before running those jobs, and the overlay README says to settle the permission mode of
  spawned sessions with the owner first (both were found missing when the founding project
  took this version).
- `docs/GOTCHAS.md` template: `pgrep -f` and shell wait loops match their own command line.
  **ACTION:** add the entry to your project-owned `docs/GOTCHAS.md` if your agents wait on
  processes.

## v0.7 — 2026-09-05 (unreleased)

- Downstream adoption exposed four review self-tests that assumed installed projects still
  used the template's empty model pins and Claude default. The fixture now explicitly sets
  those defaults in its temporary copy; project settings are preserved. **ACTION:** copy
  the updated `test_claude_bridge.py` with the complete companion set when upgrading.

- **Issue #7:** existing-file negative tests must restore current bytes and mode before
  deleting backups, including on EXIT/INT/TERM. A separate scaffold example isolates
  traps and terminates after signals; its regression preserves uncommitted content.
  **ACTION:** prefer disposable snapshots, or update project-owned destructive probes
  with restoration registered before mutation and interruption tests.

- The final review exposed initially hidden index changes and a verdict-only manual-check
  section. Review now rejects assume-unchanged/skip-worktree entries before model launch
  and excludes verdict declarations from manual-check validation. **ACTION:** upgrade the
  complete review runtime; clear such index flags before reviewing a complete checkout.

- The platform matrix exposed scanner exit-code differences between GNU and BSD xargs.
  The scanner now preserves each grep batch's match/no-match/error outcome explicitly.
  Real missing-file errors fail on both platforms. **ACTION:** take the updated project-owned
  `scripts/check.sh` scanner carefully, retaining your configured gates and build command.

- A follow-up review exposed four additional scope/evidence failures. Git diff drivers
  are disabled, raw checkout bytes and resolved references enter the fingerprint, merge
  commits are reviewed against their first parent, and Codex manual-check verdicts require
  actual checks. All four fixes have failing-before/passing-after regressions.
  **ACTION:** copy the complete review runtime/test companion list and repackage the plugin.

- The kit's own four legacy raw review archives are now untracked and preserved locally.
  Reference and commit reviews exclude removed legacy transcripts while keeping scrubbed
  summaries in scope. **ACTION:** use the same preserve-and-untrack migration for old
  project archives; historical Git commits are not rewritten by this change.

- The kit-source CI runs the full offline acceptance suite on Linux/macOS with Python
  3.10 and 3.14. Action revisions are pinned and jobs have read-only repository access.
  This does not run paid model calls or change installed projects' CI templates.

- **Issue #5:** an explicit transcript-Accept/no-final-response regression verifies that
  transcript text remains diagnostic only. Missing, empty, malformed and conflicting final
  responses are rejected by the wrapper. **ACTION:** take the complete review runtime/tests.

- **Issue #4:** a timeout-then-success regression proves failed evidence stays immutable,
  carries no verdict, and does not change the next review's diff or checkout fingerprint.
  **ACTION:** keep failed diagnostics locally; upgrade the adapters and ignore rules rather
  than deleting immutable reports to repair review scope.

- **Issue #3:** the interview now gives both vendor-plugin install commands explicitly
  and explains repository versus marketplace names. **ACTION:** use `codex@openai-codex`,
  matching the official marketplace manifest, rather than deriving the name from the repo.

- **Issue #2:** the boundary self-test example requires a green baseline and both a
  nonzero exit and the boundary's own diagnostic. An executable regression rejects
  unrelated failures and misleading success output. **ACTION:** adapt the example when
  maintaining project-owned boundary tests; generic exit-only gate cases remain explicit.

- **Issue #1:** setup now stages the foundation and hands it to fresh review before the
  first commit. The closing report identifies pending review explicitly. **ACTION:**
  use the updated setup interview; initial gate code has no implicit review exemption.

- **2026-09-06 review fixes:** model calls now require ignored, untracked private storage;
  malformed successful Claude envelopes stop without failover; malformed or conflicting
  Codex verdict declarations fail evidence validation. Kit acceptance requires the named
  regression suites and rejects skips. The existing-project companion list is canonical
  in `core/docs/DEV_SETUP.md` and has an upgrade regression. **ACTION:** copy that complete
  list, merge the ignore rules, and preserve/untrack any previously tracked raw diagnostics.
  The owner authorized committing and pushing these repairs with Claude review explicitly
  pending. This is not a review approval; see `docs/worktree-notes/role-neutral-review.md`.

- Review attempts now default to 30 minutes rather than 10, in both directions and in
  direct adapters. Explicit timeouts are preserved. This remains a total wall-clock limit,
  not an inactivity detector; two fallback attempts can take about an hour. Claude proposal
  defaults are unchanged. **ACTION:** upgrade the companion Python runtime files and
  repackage the Codex plugin after source review; existing explicit overrides still win.

- Owner-selected reviewer default is Claude. Reviews automatically fail over once to the
  other configured model on operational unavailability, in both directions. Each attempt
  retains its own evidence and usage, linked by immutable chain checkpoints. Completed
  Reject results, invalid evidence, stale scope, and storage failures never trigger failover.
  Author-model fallback findings remain advisory, not independent review approval.
  No default review monetary cap is added. **ACTION:** manually upgrade project-owned
  `review.sh` and its companion Python files, including `review_dispatch.py`; keep existing
  model pins. Sync does not overwrite those files. Repackage and reinstall the Codex plugin
  after source review to use the updated skill and bundled dispatcher.

**The kit no longer has an opinion about which model writes and which reviews.** The rule
was always "the author never reviews its own patch, and the reviewer is a different model".
The tooling did not say that: `review.sh` was pinned to Codex, and the documents described
Claude as the author. A real project ran out of the author's budget and swapped the roles;
the kit did not support the arrangement it had been claiming to require.

- `./scripts/review.sh [scope] --reviewer codex|claude` runs either direction. The default
  is the one configured at the top of the script, and the script accepts nothing else — the
  reviewer name is matched against a closed list and no flag is passed through to a CLI.
- **Both directions publish ONE evidence format**: the same header table, exactly one
  `VERDICT:` line (or none when the run failed), and the same
  `docs/reviews/<stamp>-<reviewer>-review.md` naming. The renderer refuses a header that has
  drifted and refuses a verdict for a run that did not complete, so this is enforced rather
  than agreed. Records made before and after a role swap can be compared.
- **Both models are pinned by name and the wrapper refuses to run unpinned.** A record that
  said "CLI default" named nothing a later review could be compared against. Claude's pin is
  additionally ATTESTED against the CLI's own `modelUsage`; Codex publishes no model identity
  in its output, so its record says the pin is requested and unattested. The evidence states
  which of the two it is.
- `AGENTS.md`, `WORKFLOW.md` and `REVIEW_GATE.md` now name AUTHOR and REVIEWER as roles and
  say the roles are expected to swap with the budget.
- The setup interview asks three separate questions — which model authors, which reviews,
  and which budget is scarce — instead of asking about budget and assuming the rest.
- New `docs/delegation-is-not-symmetric.md` records what in-session delegation actually
  exists in each direction, and why there is no `overlays/codex/`. Nothing was written from
  an inferred schema.

**ACTION — existing projects.** `scripts/review.sh` and the adapter Python files beside it
are PROJECT-OWNED: `sync-kit.sh` will not touch them, by design. To take this change:

Sync alone does not replace an existing wrapper or empty its model pins. The new pin
requirement applies to new installations and to projects that manually adopt this wrapper.

1. Copy `core/scripts/review.sh` over your own, then re-apply any local edits.
2. Copy every runtime and test companion in the canonical upgrade list in
   [core/docs/DEV_SETUP.md](core/docs/DEV_SETUP.md#3-the-second-model--only-if-you-want-cross-model-review).
3. **Fill in `DEFAULT_REVIEWER`, `CODEX_MODEL` and `CLAUDE_MODEL` at the top of
   `scripts/review.sh`.** Both model pins ship EMPTY and the wrapper stops until they are
   set. This is deliberate: an unpinned reviewer archives whatever its CLI defaulted to.
4. Run `./scripts/check.sh --self-test` and `./scripts/review.sh --self-test`.

Older reports named `<stamp>-<branch>.md` or `<stamp>-codex.md` are left alone; they stay
readable, they are simply not in the new shape.

Clarifications: both hosts can delegate reviews through the shipped command/skill entry
points; only structured implementation-proposal support is asymmetric. Synthetic live
checks are integration evidence, not independent acceptance of the implementation. For a
co-authored change, use a reviewer that did not author any part of the combined diff.

The owner selected Claude as the default reviewer for the Astra-author workflow. The
shipped wrapper now defaults to Claude; explicit `--reviewer codex` and per-project setup
remain available. Existing project-owned wrappers still require a manual settings update.

Codex can host the cross-model workflow through the MyAgentKit Codex plugin.

- Two skills request fresh Claude review-and-fix and implementation proposals. Codex remains
  the writer. Both support explicit and implicit discovery; spending still needs authorization.
- The Claude adapter restricts tools, disables customizations/MCP, pins the model, bounds
  execution, and archives structured results with source hashes. Stale or absent evidence fails.
- The wrapper gained a Claude adapter beside the Codex one; the kit-root wrapper now
  delegates to the core implementation rather than carrying a second copy. Codex collection
  rejects absent and conflicting final verdicts. (Reviewer selection and model pinning were
  reworked later in this same release — see the role-neutrality entry above for the shape
  that actually ships.)
- The new kit-source `scripts/check.sh` runs packaging drift, adapter regressions, and
  bootstrapped-project acceptance. Its self-test proves existing and new rejection paths.
- Both CLI directions now have bounded process execution and local per-invocation usage
  records, including partial/failing calls. Caller/task labels make review rounds comparable.
  Missing subscription percentages remain unknown, not inferred from tokens or API dollars.
- Quota, context exhaustion, timeout, and invalid replies stop the delegation loop while
  the host continues independent authorized work. Required review still blocks its protected
  commit/push. No automatic retry, credit purchase, or silent model fallback was added.
- Codex calls also capture bounded official account-quota observations before/after work,
  including the reported plan and window percentages. These are not per-call consumption
  claims. `MYAGENTKIT_CAPTURE_QUOTA=0` disables the optional reads.
- Both reviewers now capture and validate the same checkout snapshot, reject stale or
  mismatched reference context, and persist immutable evidence before reporting completed
  usage. Output capture uses bounded pipes rather than unbounded temporary output files.
- Bootstrapped projects ignore raw review archives; deliberately scrubbed summaries remain
  versionable. Claude's kit-layout guidance includes the architecture document.
- Bootstrap excludes locally generated Python bytecode from installed project files.
- Reviews no longer impose a default monetary cap. Claude's `--max-budget-usd` is sent
  only when explicitly supplied; timeout/turn/output protections remain unchanged.

**ACTION:** existing projects must hand-merge the project-owned review/check scripts and
review policy, and copy the Python runtime/test companions listed in
`core/docs/DEV_SETUP.md`. Merge the private usage and raw archive ignore rules from
`core/.gitignore`, and add `core/docs/USAGE.md`. Do not
overwrite customized project gates. Codex plugin installation is separate; see
`docs/CODEX.md`. Live validation and review debt are recorded in `docs/ACCEPTANCE.md`.
Python 3.10+ is now required for both live providers and their self-tests. Missing test
files and missing completion evidence fail closed. Runtime updates require rebuilding and
reinstalling the Codex plugin; Claude's cross-review command also carries recovery guidance.

## v0.6 — 2026-07-27

Renamed: **MyAgentKit → MyAgentKit_Keel**. A keel is a ship's backbone and the first part
laid down — "laying the keel" is the moment construction begins — which is what a project
foundation is for. It also carries the sense in "on an even keel": the thing that keeps a
project stable rather than the thing that moves it.

- The repository is now `KBT-0/MyAgentKit_Keel`. GitHub redirects the old path, so existing
  clones and marketplace entries keep working; the install lines in the README are updated
  to the new one.
- **The plugin is deliberately NOT renamed.** It stays `myagentkit`, so `/myagentkit:handoff`,
  `/myagentkit:cross-review` and `/myagentkit:kit-feedback` are exactly what they were. A
  command a person has learned to type is a bad thing to rename for cosmetic reasons.
- Archived review reports under `docs/reviews/` are left untouched. They are dated evidence
  of what was said at the time, and evidence is not edited afterwards — including for a
  rename.

**ACTION** — none required. If you cloned by URL, `git remote set-url origin
git@github.com:KBT-0/MyAgentKit_Keel.git` avoids relying on the redirect.

## v0.5 — 2026-07-27

Sending findings upstream becomes opt-in, asked once, and the README stops describing an
overlay that no longer exists.

- **New placeholder `{{KIT_FEEDBACK_RULE}}` in the constitution.** Setup Phase 0.5 now asks
  whether the agent should ever offer to send kit findings upstream, and fills the
  placeholder with one of two whole bullets: the offer rule, or an instruction never to raise
  it. A no is therefore structural — the clause is simply absent from that project's
  constitution — instead of a preference every future session has to be told again.
- **The offer is separated from the learning.** Research passes, audits and trap logging run
  unchanged whatever the answer; they write to the project's own docs and always did. Only
  the outward-facing offer is gated. `setup/RESEARCH_PROTOCOL.md` checks the constitution
  before offering, and `INTERVIEW.md` Phase 5 is skipped outright on a no.
- **Tone.** The two sentences that leaned on obligation — "this is not a courtesy" and "a
  complaint that stays in a chat log improves nothing" — are gone. The mechanism is worth
  explaining; it is not worth guilting somebody into.
- **README corrections.** The overlay no longer claims to hold skills and commands (commands
  are the plugin; there are no skills), the status block tracks the real version, and the
  platform claim now says Linux native and WSL, naming macOS/BSD as the untested surface and
  the GNU `grep`/`sed` assumptions as where they would break first.

**ACTION** — existing projects: `AGENTS.md` is project-owned and is never overwritten, so
`sync-kit.sh` will not add this. Decide the question yourself and paste the matching bullet
from `setup/INTERVIEW.md` Phase 0.5 into the MENTION ONCE list, replacing the old
kit-feedback bullet if it is there. Doing nothing leaves the v0.4 behaviour, which is the
offer being made.

## v0.4 — 2026-07-27

A guard against the failure that produced it. During this kit's own development a
`git reset --hard`, run to drop a throwaway commit, destroyed uncommitted work — including a
review record the owner had written by hand, which git could not recover because the reflog
holds commits and nothing else.

- **`overlays/claude-code/files/.claude/hooks/guard_destructive_git.py`** blocks
  `reset --hard`, `checkout --`, `restore`, `clean -f`, `stash drop` and force pushes while
  the tree is dirty, printing the file list that would have been lost. `stash push`, `commit`
  and `--force-with-lease` pass through — the recoverable ways to do the same jobs.
- **The constitution** gains the rule for tools without the hook: commit or stash first,
  every time, and check `git status` rather than trusting that the tree is clean.
- **`core/docs/GOTCHAS.md`** carries the reasoning; `RESEARCH_LOG.md` finding #11 carries
  the general form, which is not about git: an agent's cleanup is the most dangerous thing it
  does, because attention has already moved to the next task.

**ACTION** — projects on v0.3 that took the claude-code overlay: copy the new hook in and add
the `PreToolUse` block to `.claude/settings.json` (see `overlays/claude-code/files/`).
Projects using another tool get the constitution rule and nothing enforcing it, which is
worth knowing rather than assuming.

## v0.3 — 2026-07-27

Project knowledge gets its own layer. Until now the kit had a slot for a design document
(`{{DESIGN_DOC}}`, a path the project supplied) and nothing at all for "what are we building
right now, and what are we deliberately not building yet". Both are shipped files now.

- **`docs/PROJECT.md`** replaces the `{{DESIGN_DOC}}` placeholder. Same role — permanent
  decisions, DECIDED/OPEN tagging, design authority — but a real file at a fixed path, so
  two placeholders disappear and the constitution stops pointing at something that might not
  exist. It is NOT in the reading order: sections are numbered, listed in a Contents, and
  cited by number rather than quoted.
- **`docs/PHASES.md`** is new and read every session. Current phase in full, later phases
  one line each, and — the half that earns its place — what is explicitly OUT of scope until
  later. Promoted from `patterns/staged-prototype.md`, which stays as the long-form
  reasoning.
- **An agent may add OPEN items to PROJECT.md freely and may NEVER mark anything DECIDED.**
  When the owner appears to settle something in conversation, it is recorded as OPEN with a
  note and a question. A wrongly captured question costs a minute; a wrongly promoted
  decision is invisible, binding, and compounds.
- **`scripts/check.sh` fails when a numbered PROJECT.md section is missing from its
  Contents.** Selective reading is what keeps that file affordable as it grows, and it only
  works while the Contents is complete. Four self-test cases, sixteen in total now.
- **No ROADMAP.md**, considered and rejected — the reasoning is in
  `docs/knowledge-has-three-horizons.md` along with the permanent / episodic / momentary
  split the three files implement.

**ACTION** — projects on v0.2 must add both files: copy `core/docs/PROJECT.md` and
`core/docs/PHASES.md` in and fill them. Add **`docs/PHASES.md` to the reading order** in
`AGENTS.md`, as the step after the constitution. Do NOT put `docs/PROJECT.md` in the reading
order — it is read by section, on demand; putting it there is the cost this release exists
to avoid. A project with an existing design document under another name (`GDD.md`,
`SPEC.md`) either renames it or makes `docs/PROJECT.md` the file that owns the Contents;
two canonical design documents is the duplicate-authority problem this release exists to
avoid. The gate FAILS until `docs/PROJECT.md` exists, which is deliberate.

## v0.2 — 2026-07-26

The three commands moved out of the Claude Code overlay into a proper plugin, and the kit
gained a way to be maintained by the projects using it rather than only by its author.

- **Commands are now a Claude Code plugin**, installed once per machine instead of copied
  into every project: `/myagentkit:cross-review`, `/myagentkit:handoff` and the new
  `/myagentkit:kit-feedback`. Namespacing comes from the plugin, which also ends the risk of
  a bare `handoff` or `cross-review` colliding silently with something else.
- **`/myagentkit:kit-feedback`** sends a finding upstream as a GitHub issue or pull request.
  It scrubs the project out of the text, shows the exact body, and sends nothing without an
  explicit yes.
- **Two places now offer it unprompted:** the end of an ecosystem research pass
  (`setup/RESEARCH_PROTOCOL.md`) and the audit's backflow question
  (`core/docs/WORKFLOW.md`). A third lives in the constitution's MENTION ONCE list, for when
  the foundation itself misbehaves during ordinary work.
- **`CONTRIBUTING.md`** is the same process by hand, with what belongs upstream and what
  does not, the privacy rules, and the requirement that a gate change carries its negative
  test.

**ACTION** — install the plugin (`/plugin marketplace add KBT-0/MyAgentKit_Keel`, then
`/plugin install myagentkit@myagentkit`), then delete `.claude/skills/handoff` and
`.claude/skills/cross-review` from projects installed with v0.1. They are superseded;
leaving them means two copies of the same command, one of which no longer receives fixes.

## v0.1 — 2026-07-26

First extraction. The kit's Layer 1 (universal core), the Unity overlay and the optional
patterns were taken from a Unity + .NET multiplayer codebase written almost entirely by CLI
agents. Nothing here was designed in the abstract; every rule was paid for by real work.

Founding content, with the failure each rule prevents recorded in `RESEARCH_LOG.md`
(Backflow findings, 2026-07-26):

- Gates must be proven RED before they count, and each ships with an automated negative
  test — `core/scripts/check.sh --self-test`.
- Gates, CI and review tooling are a permanent risky area in every project's review gate.
- The cross-session state file is transient: completed work is deleted, permanent findings
  are tagged `[LESSON]` / `[GOTCHA]` and routed to a permanent home before deletion, and
  the rot gate keys on an empty "Active work" section rather than a line count.
- CLI output parsing strips ANSI escapes and never writes an extracted field as silently
  blank.
- Always-loaded documents are a recurring token bill and are kept small and stable.

Reviewed before release by TWO other models, read-only, both returning **Reject** — the
second one reviewing the first one's fixes:

- Codex CLI (gpt-5.6-sol): **seventeen findings**, five of them fail-open paths in the gates.
  Consequences worth naming: `.claude/` moved out of `core/` into `overlays/claude-code/`,
  and `scripts/review.sh` now states that it targets the Codex CLI's interface rather than
  implying vendor neutrality. Reasoning in `RESEARCH_LOG.md` backflow finding #6.
- Claude Fable 5, on the fixed tree: **eleven findings, two critical.** The remediation for
  the scanner had reintroduced the fail-open shape it fixed (`exit` inside a command
  substitution kills only the subshell), and the editor-side boundary hook read a payload
  field no tool sends, so everything written through Edit passed uninspected. Reasoning in
  backflow finding #7 — which is why `docs/REVIEW_GATE.md` now says a Reject is not closed
  by its own fixes.

Both reports are archived under `docs/reviews/` as evidence. `docs/ACCEPTANCE.md` lists what
was executed and what was not.

The first backflow from a project arrived the same day: applying these findings back to the
founding project uncovered a gate aimed at two directories that did not exist yet, which had
therefore reported PASS without reading a line since it was written. `boundary_checks.sh` and
the audit checklist now cover it (`RESEARCH_LOG.md` backflow finding #8).

**ACTION** — none. There is no earlier version to upgrade from.
