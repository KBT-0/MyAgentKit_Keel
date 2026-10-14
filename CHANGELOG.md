# CHANGELOG

What changed in the kit, dated, newest first. `sync-kit.sh` prints the entries added since
a project's recorded kit version, so an entry must say what a project OWNER has to do —
not just what moved. Mark anything needing hand-application with **ACTION**.

Versions are `MAJOR.MINOR`. MINOR adds or refines; MAJOR changes a rule or a file layout in
a way that existing projects must reconcile by hand.

WHY an entry exists belongs in `RESEARCH_LOG.md`; this file records WHAT changed.

---

## v0.11 — 2026-10-09

- **ACTION — v0.11 is used for real in its first projects; report every kit problem.** leeway
  and labricore-web take v0.11 straight away, and their daily work is part of its dogfood. A
  lead upgrading one of them is extra careful with the upgrade and with the kit afterwards:
  every problem, surprise or doubt about MyAgentKit, and about this release above all, goes
  upstream through `/myagentkit:kit-feedback` (an issue), not only into the project's notes.
- **Symlinks, junctions and long paths in the kit check** (tests only; nothing for a project to
  do): the symlink and junction classes were already held by required suites
  (`test_boundary_restore`, `test_check_gate`, `test_check_gate_windows` and `check.sh
  --self-test`), so no new fixture was written. One gap is closed: on native Windows a process
  whose working directory lies past 260 characters keeps its worktree from `clean_worktrees`;
  `test_clean_worktrees_windows` minimum 11.
- **The kit check's shell sensor** (`scripts/check_kit.py`; the shipped `check.sh`, `doctor.sh`,
  `watch_workers.sh`, `boundary_selftests.sh`, the `commit-msg` and `post-merge` hooks and the
  Unity overlay's `unity_gate.sh` change only in how they print): over the sh scripts git tracks
  (`.sh` files and files with an sh shebang), the kit's own lint refuses an `echo` that prints an
  expansion or a backslash (dash reads the backslash as an escape; 65 lines now use
  `printf '%s\n'`) and `mktemp -p`, `-t`, `--suffix`, `--tmpdir` (GNU-only, or another meaning
  on macOS), and `shellcheck -s sh` refuses a bashism (SC3xxx) or an error; its warnings stay a
  reviewer's, and no rc file or SHELLCHECK_OPTS can hide a code. Without shellcheck the step is
  NOT RUN, except on CI's Linux job. REVIEW_GATE's attack list keeps these classes: a project's
  `scripts/check.sh` has no such sensor.
- **The kit check's locale sensor** (`scripts/check_kit.py`, the kit's own check; nothing for a
  project to do): a `locale` unit runs seven fast text suites again with `PYTHONUTF8=0`, under
  `LC_ALL=C` and `tr_TR.UTF-8` on POSIX (NOT RUN without the Turkish locale; CI's Ubuntu job
  generates it) and under the ANSI code page on Windows, with an encoding-less `open`,
  `read_text`, `write_text` or text subprocess an error (`EncodingWarning`, PEP 597); each suite
  is held to its own minimum, skipped tests not counted. Locale and UTF-8 bugs were the second
  most frequent review finding class (91 mentions in the v0.11 archives). Its first run found
  encoding-less reads in the kit check and in the Claude Code overlay's `context_size.py` hook,
  which now reads and writes its state as UTF-8. **ACTION** (Claude Code overlay): the hook has
  no KIT-OWNED header, so `sync-kit.sh` does not copy it; copy
  `overlays/claude-code/files/.claude/hooks/context_size.py` over the project's copy by hand.
- **One review policy in two files, and one model** (`docs/REVIEW_GATE.md`,
  `docs/REVIEW_RUNNING.md`, `AGENTS.md`, `docs/WORKFLOW.md`; `claude_bridge.py`,
  `codex_bridge.py`, `review_dispatch.py`, `review.sh`, `agent_process.py`, `working_mode.py`,
  `agent_cost.py`; the Claude Code overlay): the review rules that lived in eight files live
  in two, each rule once, and the kit runs on one model family with a second vendor
  pluggable. A brief's `Risk:` line picks the tier: low gets the gate and one light review,
  medium one reviewer in one pass, high two reviewers at once with narrow prompts
  (`REVIEW_FOCUS`); the session that wrote a patch never reviews it. Reject needs a Critical
  or High; a Medium is fixed in the round only when the fix is one place with a test, else
  filed; Low is filed, and an Accept may carry Lows and pre-existing items. A label carries
  two rounds: the second confirms the first round's Critical and High fixes and reports new
  Critical or High only; a third attempt stops with exit 2 unless
  `REVIEW_ROUND_EXCEPTION=<reason>` is set, and the record keeps the reason. The one review
  prompt (`claude_bridge.REVIEW_PROMPT`, both adapters) states the finding threshold, the
  severities for this kit, what not to report, the Low ceiling and the round-two narrowing,
  and reads the brief (`REVIEW_TASK_FILE`), the tier (`REVIEW_RISK`) and the focus from the
  environment, which the wrapper passes. Default effort follows the tier (high for a high
  tier, else medium; xhigh and max are not review choices). `REVIEW_TIMEOUT_SECONDS`
  defaults to 2700 and is capped at 3600; a timed-out review returns no verdict and its
  quota is spent. The routing escalation rule is gone. The seven working modes are three:
  `solo` (default: one family, a fresh session of another tier reviews), `normal` (the
  side the STATE note names writes, the other side reviews) and `saver` (the low side
  reviews within a small budget); `working_mode.py` refuses an old mode name and prints the
  mapping, a switch to normal or saver sets the sides note from its second argument
  (`working_mode.py normal "writes: claude, reviews: codex"`, `saver "low: claude"`) and solo
  drops it, and `--replace-state` accepts one edit of the mode line: an old name becoming one
  of the three. A high-tier change takes one label per focus reviewer. Worker and lead prompt caches live one hour
  (`CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h` in `spawn_worker.sh`, `promptCacheTtl` and
  `subagentPromptCacheTtl` in the overlay `settings.json`; the frontmatter `cacheTtl` is
  dropped). `AGENTS.md` is a 165-line map: the review paragraph is three lines and a
  pointer, the STATE discipline moved to `docs/AGENTS.md` with the path-scoped
  `.claude/rules/state.md` pointing at it. `agent_cost.py` prints the cache-hit share
  per agent with an 80% target, and `docs/context-is-a-budget.md` corrects the cache and
  MCP-catalogue claims and states the compaction rule. **ACTION:** copy the listed scripts
  and the overlay files (`.claude/agents/worker.md`, `diff-reviewer.md`,
  `.claude/settings.json`, `.claude/rules/state.md`, `scripts/spawn_worker.sh`); take the
  kit's `docs/REVIEW_GATE.md`, `docs/REVIEW_RUNNING.md`, `docs/WORKFLOW.md`, `AGENTS.md` and
  `docs/AGENTS.md` and re-apply your project's own lines; BEFORE running `working_mode.py`,
  rewrite the `**Working mode:**` line of `docs/STATE.md` to `solo`, `normal` or `saver`
  through `--read-state` and `--replace-state` (cross-performance and claude-only become
  solo; claude-first and codex-first become normal with a `(writes: ..., reviews: ...)`
  note; cross-saving, claude-saver and codex-saver become saver with a `(low: ...)` note)
  and the mode table of `docs/WORKFLOW.md` to those three rows, since the script refuses
  the old names;
  measure your first large review's duration from the chain record's timestamps and, if
  3600 s cut it off, ask the owner whether `MAX_REVIEW_TIMEOUT` rises.

- **Two ordinary accidents named** (issues #75, #76; `AGENTS.md` task discipline,
  `docs/REVIEW_GATE.md` attack list): a script's recursive delete of a directory chosen by a
  variable or a setting proves ownership by a marker it wrote and refuses roots, ancestors
  and unresolved links; a freshness stamp is bound to the fingerprints taken before the work,
  re-checked before it is published. Both were found by a downstream review in that
  project's own tooling, not in the kit, whose scratch folders and review snapshots already
  follow the pattern; the kit records them as guidance, not as a new gate. **ACTION:** copy
  the two sentences into your `AGENTS.md` and `docs/REVIEW_GATE.md`.

- **Reviewer configurations are measured** (`claude_bridge.py`, `codex_bridge.py`,
  `agent_usage.py`, `usage_summary.py`): each answer in `REVIEW_DISPOSITIONS` carries one
  key, `fixed:<commit>`, `disproved:<evidence>` or `deferred:<issue or decision>`; a file
  without a key stops the review (exit 2) before any model runs. The usage record keeps the
  counts, and `usage_summary.py` prints per task and per model, effort and backend the
  findings per round and the author-claimed acceptance rate (fixed + deferred over all
  answered), credited to the round the answers refer to. `REVIEW_SHADOW=1` archives a
  trial configuration's verdict with a `SHADOW REVIEW` banner, records `shadow` in the
  task, and the summary lists it apart as no round. The rate informs the owner; nothing
  switches a reviewer off by itself (`docs/USAGE.md`). **ACTION:** sync the review
  scripts and the Codex plugin; write every disposition with its key from now on.

- **Windows worker observation and generated paths corrected** (`spawn_worker.sh`,
  `watch_workers.sh`): an older hook's `waiting input` line means an idle prompt, never a
  permission WAIT; the watcher prints one older-kit notice per worker and asks for a re-spawn.
  State is read once as bytes: a zero-byte file is no signal yet, a NUL-only file is invalid,
  an unreadable one is an observation failure (exit 3). Spawn bounds every generated filename
  at 255 bytes (240 name characters) and the longest native Windows path at 259 characters
  before any worker file or worktree is made. **ACTION:** sync both scripts and re-spawn
  workers that still run the older hook; shorten the worker name or the checkout path when
  spawn refuses a generated path.

- **Worker launch cleanup follows confirmed session ownership** (`spawn_worker.sh`,
  `spawn_codex.sh`): an accepted tmux pane keeps its temporary script when its spawner is
  interrupted; a failed or interrupted launch without a confirmed session removes the script
  and releases the Codex reservation even when unlinking fails. Cleanup runs once, clears its
  traps and releases only its own reservation, so a repeated signal cannot remove a lock
  another spawner took meanwhile. **ACTION:** sync both launcher scripts.

- **Spawned workers register as peers** (`spawn_worker.sh`, `spawn_codex.sh`,
  `docs/WORKFLOW.md`): the lead's session markers are cleared with an `env -u` prefix on the
  worker's command; on the tmux path the command goes into a self-removing temporary script
  that tmux runs as `sh SCRIPT`, so tmux's default shell (fish included) parses two plain
  words. The lead subscribes with `notify_when_idle` conditionally on native Windows only; a
  tmux worker always registers. **ACTION:** sync both launcher scripts.

- **The behaviour appendix belongs to the reviewed snapshot** (issue #74; `claude_bridge.py`,
  `agent_usage.py`, `spawn_worker.sh`): a Claude review refuses a symlinked, non-regular or
  escaping appendix before launch. The appendix bytes reach the review copy, the fingerprint,
  the evidence and the usage record as `behaviour_sha256`; a change during the review fails as
  `stale_checkout`. The worker's appendix status line strips terminal control bytes, and the
  enabled and disabled lead launches are separate commands in `docs/WORKFLOW.md`. **ACTION:**
  sync the core scripts and the Claude worker overlay; start a fresh lead with the enabled or
  the disabled command.

- **Named Claude-compatible backends** (`review_dispatch.py`, `claude_bridge.py`, `review.sh`,
  `spawn_worker.sh`, `usage_summary.py`, `docs/DEV_SETUP.md`): `.myagentkit/backends/NAME.env`
  (Git-ignored, untracked, a regular file) holds a non-empty provider token and an explicit
  model id; `--backend NAME` or `MYAGENTKIT_BACKEND=NAME` routes a Claude review or worker
  through it. The launch clears every inherited Claude credential and routing control (one
  shared list) and restores it afterwards; a backend worker refuses a `claude-` model id; a
  Codex review ignores a backend request with one notice; the evidence records the reviewer as
  `claude@NAME`; Claude reviews deny reads of the backends folder. The usage summary groups by
  model, effort and backend. **ACTION:** sync the review and worker scripts; create the
  backend file by hand where a backend is wanted; configure the documented Codex administrator
  read-deny policy where supported.

- **Review results survive a late failure; the self-test and the check gate on native
  Windows** (issues #41 #53 #60 #71; `review_dispatch.py`, both adapters, `check.sh`,
  `check_kit.py`): the dispatcher's attempt loop keeps a handed-over result when printing or
  recording fails afterwards (`error_after_result`, the delivered exit code); each adapter's
  NOTE says whether the result completed, failed, or its evidence was never written. The tree
  check in both `check.sh` wrappers hashes every path in one batched `git hash-object` call
  under the run directory and fails by the first uncovered path. Self-test status, the check
  gate, boundary restore and `clean_worktrees` carry Windows-only suites. **ACTION:** sync
  `scripts/check.sh`; Git 2.42 or newer is required (`docs/DEV_SETUP.md`).

- **The shell case lint runs under bash 5.2** (issue #40; `scripts/check_kit.py`): every
  kit shell file is parsed with `bash --posix -n` by a bash of 5.2 or newer, found on PATH or
  through `MYAGENTKIT_BASH`; the prerequisite is checked even when no file needs it, scripts
  are decoded as UTF-8, and the version probe and the parser run in the C locale, so a
  translated version banner still satisfies the prerequisite and a syntax failure keeps bash's
  own reason. The macOS CI job installs Homebrew bash before the gate. **ACTION:** a kit
  checkout on macOS needs `brew install bash` before `scripts/check.sh` passes.

- **Review launch and cut-off guidance corrected** (`docs/WORKFLOW.md`, `docs/REVIEW_RUNNING.md`,
  `docs/GOTCHAS.md`, `docs/REVIEW_GATE.md`, `docs/HANDOFF.md`, `AGENTS.md`): reviewers start
  together within the measured memory budget and the self-test is scheduled when capacity
  permits; running jobs take slots; never fewer reviews. When two jobs still do not fit, the
  lead asks the owner; no answer within one `REVIEW_TIMEOUT_SECONDS` permits a sequential
  exception only when one job fits, recorded with the budget in the lead's notes. After a
  cut-off, inspect the project gate lock at `git rev-parse --git-path check.lock` and the
  `check-selftest` marker beside it; reviews and the kit's own self-test hold no lock. Read the
  highest-numbered review chain checkpoint: a completed record is finished; a failed one is
  finished when its attempts equal the possible attempts, its `failure_kind` is outside the
  dispatcher's unavailable set, or no fallback is allowed; a failed attempt without evidence or
  a usage record ends the chain. Otherwise wait from the first checkpoint's mtime for the
  timeout (3600 s when the record stores none) times the possible attempts, then still confirm
  completion in the process listing by the reviewer copy (`myagentkit-codex-*` /
  `myagentkit-review-*`; on Windows `Get-Process -Id N | Select-Object Path` when CIM hides
  the working directory). Wait for survivors or ask the owner; never start heavy work beside
  them. **ACTION:** sync these docs or apply the launch and recovery rules by hand.

- **The existing-file boundary probe runs on native Windows** (issue #60;
  `scripts/boundary_selftests.sh`): under `env -i` the Python install manager's `python3`
  alias, missing LOCALAPPDATA, found no Python and downloaded and installed one on every
  self-test. On Git for Windows, MSYS2 and Cygwin `probe_env` now keeps SYSTEMROOT, WINDIR,
  LOCALAPPDATA, APPDATA, USERPROFILE, PATHEXT and COMSPEC, sets PYTHONNOUSERSITE=1 (the user
  site lives in the real APPDATA, where HOME is the copy's own on POSIX), and the probe's
  audit runs the Python `check.sh` resolved (`$kit_python`: python3, python or `py -3`), never
  a bare `python3`. The probe then ran into its own POSIX calls; it is ported: the copy keeps
  a symlink or junction as a link (`winsymlinks:nativestrict`; a host that cannot make one is
  reported NOT RUN by name, with Developer Mode as the remedy), the audit treats every reparse point as a link and never enters one, and
  the delete opens each entry as itself and removes it with POSIX semantics that ignore the
  read-only attribute without changing it, so git's read-only objects go and a file
  hard-linked with the checkout keeps its attribute. A copy is left (`cd /`) before it is
  deleted, a gate called by a Windows path (`C:\...\check.sh`) is found in the copy, the
  audit names paths with `/`, and the probe's Python prints UTF-8. On POSIX the delete and
  audit behave as before. Known limit on Windows: a relative folder link whose target sorts
  after it becomes a file symlink in the copy, so a gate that walks through it fails in the
  copy; the checkout is never at risk. **ACTION:** if you adapted the existing-file example, take the new `probe_env`,
  `probe_delete`, `probe_audit` and `cp` line from `$KIT/core/scripts/boundary_selftests.sh`
  into your `scripts/boundary_selftests.sh`.
- **A worktree path holding a newline is kept for the right reason** (issue #41;
  `scripts/clean_worktrees.py`): `git rev-parse` is asked one flag per call, each answer less
  exactly its own newline. Split on newlines, such a path was judged "its folder is not its
  own worktree"; it is now kept because the path is not printable. It was kept before too.
  **ACTION:** copy `$KIT/overlays/claude-code/files/scripts/clean_worktrees.py` to
  `scripts/clean_worktrees.py`.
- **Doctor catches an old Claude CLI earlier on PATH** (`scripts/doctor.sh`): the configured
  Claude reviewer must advertise `--effort`, which the adapter already requires. A newer
  installation later on PATH cannot satisfy that check. The probe finds the CLI as `review.sh`
  does, `~/.local/bin` included, under the grep probe's 5-second bound. Its `--help` output
  goes to a temp file, never a pipe, so a CLI whose background child keeps stdout open
  cannot hold session start past that bound. Where `setsid` exists, that child is killed with
  the probe's process group (otherwise a NOTE says it is not), and an interrupted doctor
  removes the temp file. Without `timeout` or a temp file the probe is skipped with a NOTE.
  Both probes print their exit status on a line of its own: a `--help` or an rc file ending
  without a newline once hid it, and doctor gave a false 'did not answer' (or 'did not
  complete') NOTE.
  **ACTION:** sync the kit or copy
  `$KIT/core/scripts/doctor.sh` to `scripts/doctor.sh`.
- **Live Claude adapter acceptance recorded** (issue #6; `docs/ACCEPTANCE.md`): a live
  proposal, and live permission and customization probes, passed on native Windows.
  On 2026-10-10, Bash write and network containment passed on WSL2 Debian; macOS is not covered.
- **The Claude reviewer's shell is sandboxed, or absent** (issue #39; `claude_bridge.py`,
  `review.sh`): on macOS, Linux and WSL2 its Bash runs inside Claude Code's sandbox. Verified:
  native Windows (no Bash) and the live WSL2 probe. NOT RUN: macOS and native Linux, where the
  enforcement is unverified. The sandbox allows writes only in the throwaway copy and Claude
  Code's temporary directory, allows no network, never retries a command outside it, and
  stops the review at startup where it
  cannot start (`sandbox_unavailable`, never a fallback). On native Windows, where Claude
  Code has no sandbox, the Claude reviewer gets no Bash: it reads the copy and marks its
  findings REASONED. A reviewer that found the repository by its absolute path could
  write to it before. **ACTION:** copy the core scripts; on Linux and WSL2 install
  `bubblewrap` and `socat` (`scripts/doctor.sh` says so).
- **Review clean-up gaps closed** (issue #39): a copy left by a killed adapter is removed
  by a later run once it is old and its lifetime lock is free. An old archive timestamp
  cannot cause a live copy to be swept; unmarked legacy folders are kept. A proposal makes
  no temporary folder. A copy that cannot be made, including an operating-system error,
  is a recorded failure (`copy_failed`, with evidence and a usage record) in both adapters.
  Scratch setup failures are recorded too and cleaned up. By the owner's decision, a
  temporary filesystem that refuses locks fails each review as `copy_failed`, whose message
  says to set `TMPDIR` to a filesystem with lock support; there is no age-only fallback. A
  `.lock` the adapter did not create is never removed: it picks another folder. A `TMPDIR`
  inside the reviewed repository is now a recorded `copy_failed` (exit 5, evidence and a
  usage record), not exit 2 without a record. Old orphan lock files are swept after acquiring
  their lock. Errors from a running reviewer are recorded as `run_failed`, with evidence,
  and the archive says whether the reviewer launched (`agent_process.run` records it), so a
  launch that failed and then raised on cleanup reads `did not start`, not `ran`,
  a failed usage record, captured output and a structured dispatcher result. They are never
  labelled as copy failures or preflight failures; one before the launch says the reviewer did
  not start. The evidence keeps only the tail of the reviewer's stderr, outside its own text;
  the usage record keeps all of it. A cancel stays a cancel when the look at the reviewer's
  exit fails; timeout handling stays unchanged.
  **ACTION:** update both the copied core scripts and the plugin to the same kit version;
  an older adapter still sweeps by age alone and can remove a new adapter's live copy.
  While no review is running, delete leftover `myagentkit-review-*` and `myagentkit-codex-*`
  temporary folders that have no `.lock` sibling; these unmarked legacy copies are kept.
- **A Codex copy failure says why** (`codex_bridge.py`): a review whose copy could not be
  made keeps the adapter's reason in its evidence (`## Failure`, `Codex never ran:` and the
  tail of the error), as Claude's evidence already did; the wrapper once printed
  `copy_failed` and no reason. **ACTION:** copy the core scripts.
- **One lock seam for the scratch copy** (`agent_process.lock_file()`): the copy's lifetime
  lock (Windows' one-byte range lock, `flock` elsewhere) moved out of `claude_bridge.py` into
  `agent_process.py`, beside the other process seams the review self-test stubs.
  **ACTION:** copy the core scripts.
- **doctor finds a claude CLI the review cannot use** (`scripts/doctor.sh`): one too old for
  a flag the review passes (the winget claude 2.1.218 lacked `--restricted`), or npm's
  `claude.cmd` on native Windows, or a CLI whose help probe cannot launch or times out,
  first on PATH or named by `CLAUDE_CLI_BIN`, is MISSING
  with the binary to put first or the `CLAUDE_CLI_BIN` to set. **ACTION:** copy
  `$KIT/core/scripts/doctor.sh` to `scripts/doctor.sh` and run it.
  Each executable's help is probed once per doctor run, and all probes share one 90-second
  budget; launch failures suggest reinstalling or selecting a working executable, and timeouts
  suggest checking first-run prompts and retrying. A candidate the spent budget cut short is
  named in the fix, never hidden.
- **The review self-test runs on native Windows** (issue #54): offline CLI fixtures use
  executable Python launchers, tests inject cancels without terminating the test runner,
  and per-platform suite minimums count executed tests. POSIX-only cases report NOT RUN;
  Linux and macOS CI still run them. The kit acceptance no longer bypasses review tests on
  Windows. Native gate-lock fixtures use owned Win32 process handles for forced exits;
  restricted hosts need no taskkill CLI. Redirected adapter output uses UTF-8 so a completed review with non-ANSI text
  remains usable. LFS fixtures use their own driver rather than the host's Git LFS process.
  The kit check recovers a missing temporary completion-marker directory and prints PASS
  only after writing that marker; a failed marker write still fails the check.
  **ACTION:** copy the review companion files listed in `core/docs/DEV_SETUP.md`,
  including the new `review_test_support.py`; Windows self-tests require pip's bundled launcher.
- **Cancels and timeouts also stop detached review descendants** (`agent_process.py`):
  Linux and macOS cleanup scans a unique inherited environment marker in addition to killing
  the reviewer's process group. Native Windows Job Object tests prove that detached children
  remain contained and breakaway is refused. A descendant whose environment cleanup cannot
  read is outside the POSIX marker mechanism: a cleared environment, a non-dumpable,
  setuid, setgid or file-capability process on Linux, or one `ps -E` does not show on
  macOS; on Windows a packaged-app execution alias (the WindowsApps `python3` stub) is started
  by the system broker and escapes the Job Object. On macOS each process is read on its own once the marker shows, so a multi-line
  environment value can no longer credit the marker to the wrong pid. A failed scan is
  retried, up to 20 scans, and a give-up is reported; a `ps` that cannot list environments
  is tried once per stop, and a pid that exits mid-scan is no failure. **ACTION:** copy
  `core/scripts/agent_process.py`.
- **Routing sets effort, risk checks and second-round escalation.** Briefs name route,
  risk, checks, model and effort. `scripts/usage_summary.py` (kit-owned, synced) reports
  review rounds, verdicts and rejects per task and per model and effort; worker errands
  write no record and are not in it. Every printed label is escaped, the backslash included,
  so a literal `\x1b` and the control character it names print differently and stay in
  separate groups; a missing, null or empty model, callee, kind or effort prints as the reserved
  label `unknown`, and a value that is literally `unknown` joins that group. **ACTION:** reconcile `$KIT/core/docs/WORKFLOW.md`
  into `docs/WORKFLOW.md`,
  `$KIT/core/docs/HANDOFF.md` into `docs/HANDOFF.md`,
  `$KIT/core/docs/USAGE.md` into `docs/USAGE.md`, and
  `$KIT/overlays/claude-code/files/.claude/agents/worker.md` into `.claude/agents/worker.md`,
  preserving project settings.
- **Two models writing requires two final reviews.** Each model runs a fresh NEW-label
  review over parts it did not write; both must return without a High or Medium finding.
  **ACTION:** reconcile `$KIT/core/docs/REVIEW_RUNNING.md` into `docs/REVIEW_RUNNING.md`,
  `$KIT/core/docs/REVIEW_GATE.md` into `docs/REVIEW_GATE.md`, and `$KIT/core/AGENTS.md`
  into `AGENTS.md`; copy `$KIT/core/scripts/claude_bridge.py` to `scripts/claude_bridge.py`.
- **Refused moves leave no marker** (owner decision): a report move refused before the report left its path (a Windows sharing violation, EACCES or EXDEV from `renameat2`, a failed probe link, "no-overwrite guarantee unavailable") exits 3 and clears `NAME.report-move`; the close keeps the worktree without the audit, and the next close runs normally. **ACTION:** sync `close_worker.sh` from the Claude Code overlay.
- **Stale markers are named**: when `NAME.report-move` cannot be removed after a publication, the close prints the published path and says only the marker is stale, instead of reporting a failed publication.
- **Clearer marker refusals**: the refusal says the session is not ended and prints the recorded source and target on lines of their own; the header lists a marker among the reasons a dry run exits 1.
- **STATE refusals name FILE**: `--replace-state FILE` whose own folder is not private names FILE and says its folder must be inside `.myagentkit/` or the temporary folder. **ACTION:** sync `scripts/working_mode.py`.
- **Unfinished report moves survive retries**: `NAME.report-move` records each move before consumption and, once the report left its path, blocks later closes, keeping the worktree and session records until the lead recovers the report and removes the marker. **ACTION:** sync `close_worker.sh` from the Claude Code overlay.
- **Failed moves skip the audit**: every non-collision report-move failure keeps the worktree, even when a successor occupies the source path; a collision whose restoration failed also stops the close.
- **Private STATE recovery parents**: `--replace-state FILE` checks the recovery folder's parent before consumption, so failed folder restoration cannot expose private contents to Git. **ACTION:** sync `scripts/working_mode.py`.
- **Archives without listing permission**: a denied archive scan supplies no reuse evidence; exclusive publication still proceeds without replacing an existing archive.
- **Exclusive STATE snapshots**: `--read-state OUT` creates with O_CREAT|O_EXCL; an existing hard link is never truncated. **ACTION:** sync `scripts/working_mode.py`.
- **A snapshot per edit**: `--read-state OUT` treats OUT as a prefix and prints `SHA256 PATH`; writers edit and replace their own returned PATH. **ACTION:** update the STATE protocol from `core/AGENTS.md` and `core/docs/WORKFLOW.md`.
- **Verified snapshot cleanup**: replacement consumes a private name and deletes only the published fstat identity, preserving a successor draft at the supplied path.
- **A folder is never a STATE file**: `--replace-state FILE` refuses a FILE that `lstat` does not show as a regular file before anything moves, and renames back a folder swapped in after that check; `.myagentkit`, a subfolder of it or the temporary folder named as FILE was moved whole into a private name. **ACTION:** sync `scripts/working_mode.py`.
- **A folder is never a snapshot prefix**: `--read-state OUT` refuses an OUT that is an existing folder or ends in a separator, and creates the snapshot only in a private folder; `--read-state .myagentkit/` put a committable copy of STATE.md in the project root.
- **Kept drafts are named**: a STATE draft that cannot go back to FILE stays in its private folder, and `working_mode.py` prints that path on stderr with its control bytes as `?`.
- **Private archive sources**: the hard-link fallback first moves the report into a caller-private name, preserving a newer publication at the source path. **ACTION:** sync `close_worker.sh` from the Claude Code overlay.
- **Archive refusal without safe publication**: when exclusive rename and hard links are unavailable, the helper refuses with "no-overwrite guarantee unavailable" instead of replacing an empty claim; the report and the worktree stay (owner decision, accepted trade).
- **Interrupted archive retries**: an existing archive of the same object is reused before another number is claimed; restoration uses the returned archive path. A byte-identical report from another run gets its own number (owner decision: separate runs never share an archive).
- **Archive reuse on native Windows**: archive names are compared within the records folder, so the same-object reuse also works with the `C:/` paths Git Bash passes.
- **Unreadable archives**: an earlier archive that vanishes or cannot be examined is not taken for this report and no longer fails the close.
- **Kept reports are named**: a report the archive move consumed and could not publish or put back stays in its `.report-move-*` folder, and the helper prints that path on stderr with its control bytes as `?`.
- **No audit without the report**: when the move fails after the report left the worktree, `close_worker.sh` keeps the worktree without running the audit and says where to recover the report.
- **Consecutive polling refusals**: every successful observation, cached results included, resets that path's refusal count. **ACTION:** sync `codex_worker.py` from the Claude Code overlay.
- **Working modes, by name** (issue #57; `docs/WORKFLOW.md`, "Model routing"): the kit ships
  the tier table and seven modes, claude-first, cross-performance (the main mode),
  cross-saving, codex-first, claude-saver, codex-saver and claude-only, each with who writes, reviews and
  fixes, worker caps, effort, when it ends and a Lessons list. The `{{MODEL_ROUTING}}`
  placeholder is gone, and `docs/STATE.md` carries a "Working mode:" line.
  `/myagentkit:mode` (and the Codex skill `myagentkit-mode`) uses the shared
  `scripts/working_mode.py` to show or switch the mode, recording `.claude/mode` and the
  STATE line under a shared `.claude/mode.lock`, refusing overlapping switches. Interrupted
  switches report disagreement on reads and name the repair: choose a mode explicitly.
  A STATE edit detected before replacement refuses the switch; rollback preserves later
  independent edits. Session edits of STATE are a compare-and-swap under the same lock that
  refuses a stale edit instead of losing a concurrent one (owner decision, `RESEARCH_LOG.md`):
  `--read-state OUT` creates a per-edit snapshot using OUT as a prefix and prints `SHA256 PATH`
  from one read; the writer edits PATH, and `--replace-state FILE --expect SHA256` publishes
  it and deletes the verified object. No command
  prints a hash apart from its bytes, which let a copy read earlier pass. The snapshot lives in
  `.myagentkit/` or the temporary folder outside the project, the STATE operations run only from
  the project root, and an edit that changes the "Working mode:" line is refused. Links
  below the project root, Windows junctions on Python 3.10/3.11 included, are refused before lock
  creation. The supplied root is resolved once, so macOS
  `/tmp` or a linked home names a project as usual; on Windows only a name-surrogate reparse
  point (a junction or symlink) is a link, a cloud-file placeholder is not.
  Handwritten names and Turkish
  labels are matched without case (including capital Turkish dotted I); a list-item or
  indented line is read and switched in place, and an unknown value, a second line or any
  other line naming "Working mode:" is refused before writes. The command's allowed tools
  are only `python`, `python3` and `py -3` running `scripts/working_mode.py`. Switches preserve STATE permissions and print UTF-8
  rules even through a Windows cp1252 pipe. Doctor names the mode command when its helper is
  missing. Saver modes route fixes to the
  side with allowance while preserving independent acceptance and the fresh final review.
  Codex-first now follows the owner's confirmed definition: the Claude Opus lead only
  plans, briefs, routes and reviews; Codex implements and fixes all findings. Only work the
  lead judges too heavy or too important goes to an Opus worker, reviewed by Codex; that
  Opus worker fixes Codex's findings on it, so no model reviews its own fix.
  Codex-saver remains the separate low-Codex-allowance mode: Claude leads and does the work;
  no Codex worker, Codex reviews only. The shared saver rules keep Claude as lead in both
  saver modes.
  **ACTION:** copy the "Model routing" section and "Working modes, by name" from the kit's
  `core/docs/WORKFLOW.md` into yours over your own routing text, keeping your model names,
  and add the "Working mode:" line to `docs/STATE.md`. Sync the core scripts to install
  `scripts/working_mode.py` and the updated doctor check; copy the `/.claude/mode.lock`
  ignore rule from `core/.gitignore`.
- **`claude-only` (Sadece Claude Modu), a seventh working mode** (owner's decision of
  2026-10-11; `docs/WORKFLOW.md`, "Working modes, by name"): for a subscription with only
  Claude. Claude workers write; a different Claude tier reviews in a fresh bridged session
  with no shared context (Opus authors and Fable or Sonnet reviews, or the reverse, picked by
  the tier table), and the reviewing tier fixes its findings. Cross review stays mandatory,
  and the escalation and closure rules are those of every mode. The second reviewer is
  `scripts/review.sh --reviewer claude` with `REVIEW_CLAUDE_MODEL` set for the run to the
  tier that did not write the change: the existing per-reviewer Claude pin, so
  `review_dispatch.py` is unchanged. Codex-saver stays a separate mode, in which Codex still
  reviews. `scripts/working_mode.py` now requires all seven modes in `docs/WORKFLOW.md`.
  **ACTION:** copy the `claude-only` table row and subsection from the kit's
  `core/docs/WORKFLOW.md` into yours, and sync `scripts/working_mode.py` with it: for a
  WORKFLOW.md whose table is exactly the six earlier modes the helper prints this ACTION,
  switches nothing, and exits 1 when a switch was asked for.
  **ACTION:** a project on claude-only sets `DEFAULT_REVIEWER="claude"` in
  `scripts/review.sh`, leaves `CODEX_MODEL` empty, and passes `REVIEW_CLAUDE_MODEL=<the
  reviewing tier>` on every review run.
- **A stopped worker is answered in its own session** (issue #57; `docs/WORKFLOW.md`,
  "Worker cost"; `docs/HANDOFF.md`, rule 7): never by a fresh session. The handoff names
  the sidecars and publishes the blocked result atomically with the ready end marker before
  publishing the question the same way after independent work, without requiring a commit.
  A ten-second grace period lets the turn flush.
- **`scripts/spawn_codex.sh`** (issues #57 and #43; Claude Code overlay): an interactive Codex
  worker in a Windows Terminal tab on native Windows and in tmux elsewhere, with the
  workspace-write sandbox and no approval prompts. The lead commits all Codex worker work
  after the normal cross-review, with the usual commit gate; the brief and result identify
  exact uncommitted files. Git-directory writable roots are removed: the owner's native
  Windows codex-cli 0.162 probe proved `git add` still fails on `index.lock` with both roots.
  The spawning checkout records `.myagentkit/workers/NAME.session`, outside the worker,
  under a shared `.myagentkit/workers/spawn.lock` reservation from the initial checks through
  session recording, refusing concurrent launches. An unrecorded launch keeps its reservation,
  with its worker's name inside, until the printed `--resume SESSION_ID` of that name records
  the launch and takes it over, or the lead confirms the launch ended and runs
  `rm -r .myagentkit/workers/spawn.lock`; printed resume commands quote the model argument.
  The lead resumes it with `--resume`; successful `close_worker.sh NAME` removes the records,
  allowing cleanup and name reuse. The close refuses while the worker's decision file (its path
  recorded in `NAME.question`) waits for its answer; a resume removes the answered file once
  the resumed session publishes a new result or exits cleanly, never on elapsed time. It moves
  an uncommitted default `RESULT-NAME.md`, which the lead never commits, to `.myagentkit/workers/NAME.result.md`, so
  the audit can remove the finished worktree. An earlier report there is kept (the new one
  takes the number above the highest, `NAME.result-2.md` and on), never replaced, also on a
  filesystem without an exclusive rename (WSL `/mnt/c`, NFS, FUSE, SMB), and a worktree the audit
  keeps gets its result back.
  Workers publish decisions to `QUESTION-NAME.md`;
  `codex_worker.py` waits for the end marker and grace period before ending their process
  tree, and a fresh replacement is refused. Only a decision or a newly published
  `Kind: completed` result closes the worker; a progress, handoff or blocked result, or an
  in-place edit of an older result, leaves it running. The wrapper writes
  `.myagentkit/workers/NAME.exit` on every way out it controls, a decision without a blocked
  result included, and holds `NAME.live` locked while it runs, so `--wait` reports EXITED for
  a worker that stops without publishing, even when the wrapper is killed or its tab closed.
  A spawn whose session never shows still prints the wait command and the resume form. On native
  Windows `close_worker.sh` refuses while a Codex session runs in the worker's folder, and a
  kept worktree keeps its session record. Its printed
  `--wait FILE --since START --stale FILE_ID --exit RECORD` command notifies the lead of an
  uncommitted handoff as a background command. It uses the result identity captured before
  launch, so a delayed wait still excludes an in-place edit of an old result. On POSIX the
  supervisor and the waiter hold that result open, so a new result cannot be given its freed
  inode number. After PROGRESS or HANDOFF the wait prints its exact follow-up command, which
  waits for the worker's next result: other contents than the reported result's, by rename or
  by in-place rewrite; a byte-identical republication does not count. A follow-up printed with
  the earlier `INO:HASH` form compares its hash. A poll opens the result, and a new question,
  only after its id, size or time changed; the answered question is opened only to consume it.
  On Windows a poll's stat still holds the file for a moment and refuses a rename over it, so the
  worker publishes with `codex_worker.py --publish TEMPORARY_FILE DESTINATION`, which retries a
  refused rename for about two seconds. An open that meets a rename is read again at the next
  poll; 50 consecutive refusals of one file, about five seconds, are an error, not an endless
  wait. A resumed supervisor retries the rename of its live record while a waiter probes the
  previous run's, and a supervisor that fails to start writes its exit record, so the wait ends.
  Windows children join their job before running; POSIX escalation kills the entire group.
  POSIX SIGTERM and SIGHUP unwind supervisor cleanup and reap the worker's process group.
  The worker's instruction tells it to run the checks named on its brief's
  `Route: ... · Risk: ... · Checks: ...` line. The tab preserves quick startup errors behind an
  Enter prompt, and launches Git Bash by its full Windows path. `--no-daemon` keeps each
  runtime private. The default result is at the repository top; the brief uses the spawn-time
  path. `--result FILE` requires a `.md`
  file inside the worker's folder; its path and parent directory are validated before a
  worktree or branch is created, so a rejected path leaves the name available for retry.
  Ignore patterns keep project `docs/QUESTION-*.md` visible.
  **ACTION:** adopt the lead-owned commit rule from `core/docs/WORKFLOW.md` and copy
  `overlays/claude-code/files/scripts/spawn_codex.sh` and `codex_worker.py` into `scripts/` (`chmod +x`,
  `git add --chmod=+x`); a sync keeps them updated from then on. Copy `close_worker.sh` too
  and the worker-sidecar ignore rules from `core/.gitignore` into your project ignore file.
  Update Codex briefs with the atomic publication protocol and run spawn's printed wait
  command in the background.
  **ACTION:** a Codex worker started by the first v0.11 `spawn_codex.sh` (2026-10-09)
  recorded its session id in the git directory: `.git/codex-session-NAME`, or
  `.git/worktrees/NAME/codex-session-NAME` for a worktree worker. The new script does not
  read it: resume such a worker with `--resume <that id>`, then delete the file.
- **A review no longer dies on the kit's own limits** (`agent_process.py`, the adapters,
  `review.sh`): a review attempt now gets 3600 seconds (maximum 7200) and a Claude review
  200 turns (maximum 500); three high-effort reviews had died on 1800 seconds and 12 turns.
  `REVIEW_MAX_TURNS` is new and reaches the Claude CLI through `review.sh`, like
  `REVIEW_TIMEOUT_SECONDS`. The turn setting is validated only when Claude is the reviewer
  or fallback is allowed. Codex has no turn limit. Proposal ceilings stay at 3600 seconds
  and 100 turns. **ACTION:** copy `$KIT/core/scripts/agent_process.py` to `scripts/agent_process.py`,
  `$KIT/core/scripts/claude_bridge.py` to `scripts/claude_bridge.py`,
  `$KIT/core/scripts/codex_bridge.py` to `scripts/codex_bridge.py`,
  `$KIT/core/scripts/review_dispatch.py` to `scripts/review_dispatch.py`,
  `$KIT/core/scripts/review.sh` to `scripts/review.sh`, keeping your project configuration, and
  `$KIT/core/scripts/test_claude_bridge.py` to `scripts/test_claude_bridge.py`.
- **A spawned handoff records its question** (issue #42; the plugin's handoff command):
  item 7 now matches `docs/HANDOFF.md`; the upgrade checklist no longer copies
  `spawn_worker.sh` twice.
- **Linked test directories fail the kit check** (issue #65; `scripts/check_kit.py`):
  a linked package can no longer leave failing tests undiscovered, including Windows
  junctions on Python 3.10/3.11. Cloud reparse folders (including OneDrive) are accepted.
  Unreadable test directories fail discovery too.
- **The merge-action test probes mktemp** (issue #66; `tests/test_sync_kit.py`):
  BSD and GNU temporary-folder behavior is tested on every host, including macOS.
- **Strong review closure fails on missing or hidden index evidence** (issue #69;
  `.githooks/commit-msg`): a failed listing refuses a commit with a `Done:` trailer. Quoted paths under
  `docs/reviews` and a different case of that directory are refused before closure checks.
  Only review paths are listed, even when the caller exports `GIT_LITERAL_PATHSPECS`.
- **Context warnings survive concurrent prompts and compaction** (issue #70): the hook
  announces each step once, keeps its highest step until compaction, and re-arms even when
  a new request already followed the boundary. Upgrading an integer step preserves the
  warning already given in the current compaction. A state of the wrong type (a null or
  string step) counts as no state, so the hook is not silenced. **ACTION:** copy
  `$KIT/overlays/claude-code/files/.claude/hooks/context_size.py` to `.claude/hooks/context_size.py`.
- **A completed review is never relabelled adapter_error** (issue #71; `scripts/review_dispatch.py`,
  `scripts/review.sh`, `docs/REVIEW_RUNNING.md`, `docs/WORKFLOW.md`): an adapter that failed
  after it had recorded and handed over its result (printing the review) had that result
  replaced with `adapter_error`, so a completed, paid review was reported as none. The handed-over
  result now stands, the later failure is kept as `error_after_result`, and a checkout changed
  meanwhile still fails as `stale_checkout`. The docs say when a self-test may share the
  review's worktree: only when it writes files Git ignores and nothing else. **ACTION:** copy
  the core scripts, and update the self-test lines in `docs/WORKFLOW.md` (the lead's step 1)
  and `docs/REVIEW_RUNNING.md`.
- **A file deleted inside a sparse checkout's rules is refused** (issue #53; `scripts/claude_bridge.py`):
  under a sparse checkout every missing skip-worktree file was tolerated, so a file inside
  the cone marked skip-worktree by hand and deleted was a deletion the diff omitted. Only a
  path the sparse rules exclude may be missing now, asked of `git sparse-checkout check-rules`
  in one call; a Git older than 2.42, or a failed check, refuses the review. **ACTION:** copy
  the core scripts, and copy the Git 2.42 requirement in `docs/DEV_SETUP.md`.
- **The self-test fails when it changes the worktree** (`scripts/check.sh --self-test`, and the
  kit's own wrapper): it compares HEAD, the index, `git status --porcelain
  --untracked-files=all` and per-file content hashes of every tracked and untracked non-ignored
  file, using `git hash-object --no-filters --stdin-paths`, before and after; a difference FAILS
  it, naming each path. Files Git ignores may change. This proves only the end state is unchanged:
  sharing a review's worktree is allowed only when every case writes nothing but ignored files
  (`docs/WORKFLOW.md`, step 1); a non-ignored file written and removed can still fail the review
  as `stale_checkout`.
  **Your self-test can turn red after this upgrade without any code change:** a case, a
  build or a test that leaves an untracked file Git does not ignore now fails it. Make that
  case remove what it writes, or ignore its output path in `.gitignore`. **ACTION:** copy
  `$KIT/core/scripts/check.sh` to `scripts/check.sh` with your filled-in values, and update
  the self-test lines in `docs/WORKFLOW.md` (the lead's step 1, "Writing a gate") and
  `docs/REVIEW_RUNNING.md`.
- **Both adapters keep their handed-over status** (`scripts/claude_bridge.py`,
  `scripts/codex_bridge.py`): run directly, a failure after a result was recorded and handed
  over (printing it) made the Claude adapter print a "failed" line after the "completed" one
  and exit 2, and the Codex adapter raise it, ending in a FAIL line. The handed-over status decides the
  exit; the failure is a NOTE on stderr naming the evidence, and the dispatcher records it as
  `error_after_result`. The dispatcher's `stale_checkout` message now says "a new untracked
  file Git does not ignore", and the review threat model names a write to an ignored file as
  an accepted limit. **ACTION:** copy the core scripts.
- **A review names its next attempt** (issue #68, item 1; `scripts/review.sh`, `scripts/review_dispatch.py`):
  before each adapter runs, including a fallback, it prints the model and effort as
  "about to run"; adapter preflights may still stop the attempt before any model call.
  **ACTION:** copy `$KIT/core/scripts/review_dispatch.py` to `scripts/review_dispatch.py`.
- **Line-ending churn stops a review** (issue #68, item 2; `scripts/review.sh`,
  `scripts/review_dispatch.py`): two scope-wide line-count queries refuse files whose
  changed lines are mostly CR-only, including normalization mixed with real edits.
  The refusal names the file and repair; `REVIEW_ALLOW_EOL_ONLY=1` explicitly permits
  a deliberate normalization.
  **ACTION:** copy `$KIT/core/scripts/review_dispatch.py` to `scripts/review_dispatch.py`.
- **The lead's Stop hook stays out of a worker's self-test** (issue #68, item 3): the lead
  uses `git -C <worktree>` and keeps its shell in its own checkout. `check.sh --self-test`
  atomically publishes its shell pid and lock token to `check-selftest` beside the gate lock
  and removes it on exit. Linked markers are refused without changing their target data.
  After the cheap gated-paths check, the Stop hook skips with a NOTE only while that shell
  lives (an unreaped zombie does not count where `ps -o stat=` works), its token equals the
  lock file, and the lock is held. Surviving build descendants
  cannot make a killed self-test's marker skip the gate.
  File names never do: a `.selftest.*` file, tracked or not, no longer skips or blocks.
  **ACTION:** add the two sentences under "The lead's steps when a branch is ready" in
  `$KIT/core/docs/WORKFLOW.md` to your `docs/WORKFLOW.md`, copy
  `$KIT/overlays/claude-code/files/.claude/hooks/gate_on_stop.sh` to `.claude/hooks/gate_on_stop.sh`,
  keeping your gated paths and file pattern. Merge the marker removal in `cleanup` and the
  full marker-publication block at the start of `self_test` from `$KIT/core/scripts/check.sh`
  into `scripts/check.sh`. Upgrade both marker publication and the hook together. Without them
  the hook waits for a self-test's lock as for any gate run.
- **An incremental-build brief names both shared dependencies** (issue #68, item 4;
  `docs/HANDOFF.md`, "The brief"): always-run inputs belong to every stage's dependency
  set, and a changed driver script invalidates every stage. **ACTION:** add the two
  sentences in item 3 from `$KIT/core/docs/HANDOFF.md` to your `docs/HANDOFF.md`.
- **Bootstrap records executable Git modes on Windows** (issue #59; `bootstrap.sh`): in
  a Git repository it records executable modes for every kit-named shell script and hook,
  including differing older or customized copies, even when
  `core.fileMode=false`. Repair runs before a gate-content conflict stops installation.
  Only stage-0 100644 entries are repaired; symlinks and other index types stay unchanged.
  Tracked files keep their staged content, including in repository subfolders;
  new nonignored kit scripts are staged only at the repository top level, and only after
  the conflict check: a stopped install stages nothing new. Bootstrap prints each staged
  path and notes once that other kit files were not staged. Subfolder installs print
  the exact `git add --chmod=+x -- <files>` commands to run from the target instead.
  Ignored files stay out of the index.
  Other project-owned scripts are left alone. **ACTION:** rerun bootstrap with the project's
  overlays to repair kit modes. A customized gate still returns STOPPING (exit 1), but its
  mode is repaired; merge content separately, without `--force`.
- **Python that does not run** (issue #67): on Windows `python3` may be a Store alias that is
  on PATH but exits 9009. The Claude Code overlay's three Python hooks now start through the
  new `.claude/hooks/py.sh`, which runs the first of `python3`, `python`, `py -3` that runs;
  before, each hook failed there and Claude Code went on without it, so `git reset --hard`
  on a dirty tree was not refused. `check.sh`, `review.sh`, `doctor.sh`, `spawn_worker.sh`,
  `close_worker.sh` and `clean_worktrees.sh` choose the same way, by running the candidate
  instead of `command -v`. The sync updates `doctor.sh` and the three worker scripts
  (KIT-OWNED), but none of the files below. **ACTION:** copy
  `$KIT/overlays/claude-code/files/.claude/hooks/py.sh` to `.claude/hooks/py.sh`, and in
  `.claude/settings.json` replace `python3 ` at the start of each Python hook command with
  `sh "$CLAUDE_PROJECT_DIR/.claude/hooks/py.sh" `. In `scripts/check.sh` and
  `scripts/review.sh` (the project's own), replace `command -v python3` and `command -v
  python` in the `kit_python=` lines with `python3 -I -c '' </dev/null` and `python -I -c ''
  </dev/null`. Then, with an uncommitted change, `echo
  '{"tool_name":"Bash","tool_input":{"command":"git reset --hard"}}' | sh .claude/hooks/py.sh
  .claude/hooks/guard_destructive_git.py` must print BLOCKED.
- **A worker starts on native Windows** (issue #72; `scripts/spawn_worker.sh`): wt.exe drops
  every double quote it is handed, so inline `--settings` JSON reached claude broken and the
  tab closed at once with no error shown. The tab now runs a script that holds its command
  and deletes itself, a claude that ends within ten seconds keeps the tab open with its exit
  code, and the brief is named by its Windows path (`C:/...`), not Git Bash's `/tmp/...`.
- **A worker is never ended mid-run, and the lead knows when it cannot hear one**
  (`scripts/close_worker.sh`, `scripts/spawn_worker.sh`, `docs/WORKFLOW.md` "Worker cost"):
  `close_worker.sh` ends nothing while a gate (`check.sh`, by its lock) or a git operation
  (`index.lock`) runs in the worker's worktree, since a session ended mid-run orphans the run.
  On native Windows `spawn_worker.sh` waits up to 30 s for the worker's process, fails when
  none starts, and warns when Claude Code did not register it as a peer session: ListAgents
  then does not list it and no idle notice comes, so the lead watches its tab.
- **Running work is never ended without a reason that holds** (`AGENTS.md`, "Task
  discipline"): a session, a review, a gate or a build keeps running unless the owner asked
  for it to end, or it is provably finished or hung. On 2026-10-08 a stopped review left its
  `codex exec` running orphaned, and killed workers left their `check.sh` racing the lead's
  gate. **ACTION:** add the rule to your `AGENTS.md` under "Task discipline".
- **Routine commands ask no one** (`.claude/settings.json`, Claude Code overlay; the list the
  owner chose with project_leeway): the gate (`scripts/check.sh` and `--self-test`, exactly)
  and read-only commands (`git status`, `git log`/`diff`/`show` only as `git <cmd>
  --no-textconv --no-ext-diff ...`, `git worktree list`, `cat`,
  `head`, `tail`, `ls`, `wc`, `grep`, `date`, `pwd`, PowerShell `Get-Content` and
  `Get-ChildItem`) run without a permission prompt; ending a process, deleting a file and every
  other command still ask. `git branch` is allowed only in exact listing forms (a `*` admitted
  `git branch -vD`), no rule has a `*` before its subcommand (`git -C * diff*` admitted
  `git -C . branch -D x`), a `*` follows a whole word (`git diff*` admitted `git difftool
  --extcmd=...`, `date*` admitted `date -s`), and `git *--out*`, `git *--ext*`,
  `git *--textc*` and `git *--sub*` are denied (the first overwrites a file, the
  others run the repository's or a submodule's diff drivers). These prefixes cover Git
  versions that accept unambiguous long-option abbreviations; `--out`, not `--ou`, so
  `git checkout --ours` stays usable.
  The allow rules guard only the command's own arguments. The repository's local git
  configuration, including `diff.submodule` and every submodule's own configuration, is
  trusted: `git status` and the gate already run what it names
  (`core.fsmonitor`). No allow rule can defend against a hostile local config.
  **ACTION:** a project with its own `.claude/settings.json` adds the
  overlay's `permissions` block, `deny` included. Replace any plain `git diff`, `git show` and
  `git log` allowances with the overlay's `--no-textconv --no-ext-diff` forms: a plain one runs
  a repository-configured textconv driver, so a read could run any command.
- **A killed self-test's injection is named, not guessed at** (`scripts/boundary_selftests.sh`,
  worked example): SIGKILL and `taskkill /F` run no trap, so an injection can be left behind
  and every later self-test refuses to start. The refusal now says so and names the file to
  check and delete by hand; the self-test never deletes it itself, since a junction above it
  or an edit after the check would put the owner's content in its place. **ACTION:** add the
  same two lines to each refusal in your `scripts/boundary_selftests.sh`. Move the existing-path
  refusal BEFORE the baseline check, since a stale injection makes the baseline fail too.
- **A review archive written on Windows matches its record** (`scripts/agent_usage.py`): the
  archive was written in text mode, so Windows stored CRLF while the usage record hashed the
  LF text, and the next review of the same task refused the earlier archive as changed. The
  archive now holds the text's own bytes.
- **The kit check passes only with its PASS line** (`scripts/check.sh`, the kit's own wrapper):
  a self-test on native Windows exited 0 without printing `KIT CHECK: PASS`. The wrapper now
  asks the check to leave a file right after that line and fails an exit 0 without it. Kit
  only; nothing to do in a project.
- **A low allowance ends** (`docs/WORKFLOW.md`, "Model routing", rule 7; a v0.10 rule): the
  rule said when a low allowance starts and not when it ends, so a lead kept the low side
  reviewing only after its allowance had reset. It now ends when that side's allowance resets
  or the owner says otherwise; then the reviewing model fixes its own findings again. A
  decision made for a moment never outlives its reason. **ACTION:** replace rule 7's ending in
  your `docs/WORKFLOW.md` with these closing sentences.
- **The reviewing model fixes its own findings** (`docs/REVIEW_GATE.md`; the review prompt in
  `scripts/claude_bridge.py`): the gate said an author fixes what a review found. The reviewer
  still never changes the checkout during its review run; afterwards it fixes its own
  findings, and the fix goes to a review by the other model, so no model approves its own
  work. A round may review the whole cumulative diff for context; its verdict counts only
  for parts it did not write. Its last fix is accepted only by the other model's next round.
  The loop ends at the first round with no High or Medium finding whose reviewer did not write the latest fix.
  Inner same-model checks stay with the worker; cross-model gate findings go to a fresh
  worker of the model that found them, since a gate reviewer cannot be resumed.
  **ACTION:** update `docs/REVIEW_GATE.md`, `docs/REVIEW_RUNNING.md` and the review-fix rules
  in `docs/WORKFLOW.md`, and copy the Claude Code overlay's `.claude/agents/worker.md`; copy `claude_bridge.py` as listed in the first ACTION above.

## v0.10 — 2026-10-07

Native Windows (Git for Windows' `sh` with python.org CPython) becomes a host the kit runs on,
not one it sends to WSL: the gate lock, a review run, a worker's spawn and close, and the
worktree clean-up each work there, with tests that run on native Windows (a CI job of their
own). It started as two fixes for a project that moved there from WSL, hardened by cross-model
reviews. Why each change is safe is in `RESEARCH_LOG.md` (2026-10-06 and 2026-10-07).

- **A low allowance** (`docs/WORKFLOW.md`, "Model routing", rule 7): when the owner says one
  side's allowance is low, that side only reviews and the other side fixes; reviews run at
  the lowest effort that fits, and the top model or highest effort needs the owner's yes
  (rule 2 says so too). A running review is not cancelled to lower its effort; a quota
  failure leaves its rerun command and waits. `docs/REVIEW_RUNNING.md`: a test failure in Codex's
  sandbox is set aside only when its diagnostic names a sandbox restriction and the same
  test passes outside the sandbox on the same platform.
- **The strong review cycle** (issue #61; `docs/WORKFLOW.md`, "The strong review cycle"): at
  least every ten days the strongest model available reviews what reached the main branch,
  a strong model of the other family reviews that report and the triage, and the owner
  decides after one exchange. New project-owned template `docs/STRONG_REVIEW.md` (the open
  list); reports are `docs/reviews/strong-<date>-<model>.md`. A closed finding is deleted:
  `.githooks/commit-msg` and `check.sh` refuse a `Done:` id that the list or a report still
  names. `check.sh` prints `NOTE [strong-review]` when the list exists and no report was
  added in ten days. **ACTION:** copy `$KIT/core/docs/STRONG_REVIEW.md` to
  `docs/STRONG_REVIEW.md` to start the cycle (the reminder stays silent without it).
- **Lead context line** (issue #58; `docs/WORKFLOW.md`, "Worker cost", rule 8): past 200k
  tokens of context the lead recommends `/compact` or a hand-off, whichever is cheaper at
  that moment, never a hand-off by default. The Claude Code overlay's new UserPromptSubmit
  hook `.claude/hooks/context_size.py` tells the agent the size once per 50k step past the
  line. `AGENTS.md` MENTION ONCE gains "a cheaper way you can see". `scripts/agent_cost.py
  --latest` now finds the transcripts of a project whose path holds `_` or another
  non-alphanumeric character. **ACTION:** a project with its own `.claude/settings.json`
  adds the UserPromptSubmit entry from the overlay's.
- **Ponytail mode** (`setup/INTERVIEW.md`, question 11; default yes): the Claude Code
  overlay's `.claude/settings.json` turns on `ponytail@ponytail`, which makes sessions and
  workers try the smallest working solution first: reuse, standard library, platform, one
  line, then the minimum code. It comes from `DietrichGebert/ponytail`'s own marketplace at
  the latest version, the same id as a user-level install, so it loads once. About 1.3k tokens at each session and sub-agent start; it saves
  most on code-writing workers. Codex installs it with `codex plugin add ponytail@ponytail`. **ACTION:** to
  turn it on in an existing project, add the overlay's `extraKnownMarketplaces` and
  `enabledPlugins` entries to `.claude/settings.json`.
- **Model routing rules** (`docs/WORKFLOW.md`, "Model routing"): work is sorted into three
  tiers; the lead chooses model and effort for every errand with equal care and writes both
  into the brief; the top models (Codex Astra, Claude Fable) are the lead's pick for one
  errand and only where the subscription includes them; a failed mechanical errand is rerun
  one tier up; after three review rounds that do not come back clean the lead raises the
  effort or the model of the fixer, and of the reviewer when needed; model versions are kept
  current and a switch is reported to the kit; tier boundaries are moved by measured rejects
  and rework. `setup/INTERVIEW.md` carries an example tier table, provisional until the
  allowance draw per model is measured. `scripts/spawn_worker.sh` now refuses a worker
  without `--model` and `--effort`; a sub-agent gets both on every Agent call. The kit's own reviewer
  pins move to Codex `gpt-6.1-sol` and Claude `claude-opus-5-5`.
  **ACTION:** copy the six rules into your `docs/WORKFLOW.md` under "Model routing", fill your
  routing table by tier, and update the pins in your `scripts/review.sh` and the `model` in
  `~/.codex/config.toml` to the newest models your subscriptions include. Every
  `spawn_worker.sh` call in your briefs and notes now needs `--model` and `--effort`.
- **Worker scripts take Windows paths.** `spawn_worker.sh`, `close_worker.sh` and
  `watch_workers.sh` called by a path with backslashes (`D:\p\scripts\spawn_worker.sh`) looked
  for their sibling scripts in the current folder, and the spawn stopped at "the watcher
  exited 127". A brief named `C:\dir\brief.md` reached the worker as the caller's folder
  followed by that whole string. Both now resolve as with `/`.
- **The gate's Windows lock self-test under a short-name TEMP.** Where TEMP is an 8.3 short
  name (`C:\Users\RUNNER~1\...`, as on a GitHub Windows runner), four claim cases of
  `./scripts/check.sh --self-test` waited for the lock instead of being refused, and the
  self-test failed: the case named the lock by its short path, the gate by its long one. The
  case now computes the path as the gate does.
- **The kit's own check runs on native Windows** (`scripts/check.sh`, issue #56). Each suite
  or case that needs a POSIX host prints one NOT RUN line with its reason. CI's Linux and macOS
  jobs still run everything. Two Windows defects it found are filed: #59 (a project
  bootstrapped on Windows commits its scripts without the executable bit) and #60 (the
  existing-file boundary probe starts the Python install manager; fixed in v0.11).
- **The gate lock on native Windows.** `scripts/check.sh` run by Git for Windows' `sh` with a
  Windows `python3` failed every run with `FAIL [lock]: python3 has no fcntl module`, so every
  commit there was blocked. On that host the lock is now the lock file opened for writing
  without write sharing; the holder makes its handle inheritable and runs the gate as its
  child, so the gate and every process it starts hold the lock, and Windows releases it when
  the last of them exits. Nothing is reclaimed and no pid is trusted, as on POSIX. A second
  run waits with the same `NOTE [lock]` line (the hint names Resource Monitor instead of
  `fuser`) and honours `GATE_LOCK_WAIT` (`NOT RUN [lock]`, exit 75). On Windows
  `GATE_LOCK_FD` holds the holder's Win32 handle: a nested run proves it is open in its own
  process on this lock file, compared by the whole `FILE_ID_INFO` (volume serial and 128-bit
  file id), with write access, while a fresh open for writing fails with a sharing violation,
  so variables copied out of a killed gate fail `FAIL [env]`. A volume that gives no
  `FILE_ID_INFO` fails `FAIL [lock]` by name in a nested run. The self-test marker is a random
  token the holder clears when the gate ends. A gate that dies of a signal exits 128 + N
  there, never 0. On a host whose `uname -s` is MSYS, MINGW or Cygwin the lock path is kept in
  the `C:/` form a native program receives (`cygpath -m`); a `cygpath` that is merely on a
  POSIX `PATH` is never run. A linked worktree's `C:/` git path is read as absolute. The POSIX
  lock is unchanged. `python3` without `fcntl` on any other system still fails `FAIL [lock]`
  by name. The host (`os.name`) picks the lock, never whether `import fcntl` works, and both
  lock programs run isolated (`python3 -I`), so a `fcntl.py` or another stand-in module in
  the checkout or on `PYTHONPATH` is never imported. `docs/DEV_SETUP.md` and
  `docs/GOTCHAS.md` say so.
- **`--self-test` proves the Windows lock.** Thirteen new cases on native Windows: a nested run
  refuses a writable handle on another file, a read-only handle on the held lock file, a
  write handle while nothing holds the lock, a fresh open refused for a reason other than the
  lock (a read-only file), and a file id equal to the lock's in its volume and first 64 bits
  only; a volume without `FILE_ID_INFO` fails closed; the lock refuses a reparse point at its
  path (set with a tag any user may set, so the case never needs the symlink privilege and is
  never skipped); a gate killed by a signal never exits 0; the holder passes a failing gate's
  exit status on; a killed lock holder leaves the lock with the gate it started; the
  holder imports no stand-in `fcntl.py` or `secrets.py` from `PYTHONPATH`; and Ctrl-C (a
  `CTRL_C_EVENT` sent to a hidden console of the case's own) stops the gate and its build, the
  gate exits nonzero, the holder outlives it and exits 130, and the next gate takes the lock;
  and a Ctrl-C while the holder waits for the lock, before the gate exists, starts no gate
  and exits 130. The holder survives Ctrl-C through a handler that records it, not
  `SIG_IGN`; the two behave alike for the gate on the hosts measured, so the first case
  proves the survival, not which one, and the second proves the record (with a handler that
  records nothing, the Ctrl-C reached no gate, and the gate then ran and passed). The host check and the case runner run isolated
  (`python3 -I`) beside a `sitecustomize.py` on `PYTHONPATH` that marks its import and calls
  the host POSIX; imported, it would have skipped every Windows case, so the import fails the
  self-test there and the skip line is printed only without it. Each case
  asserts its exit status as well as its message, and the gate's throwaway copy passes right
  after it holds the lock, so a guard that prints its refusal and then carries on fails its
  case. On POSIX, a `cygpath` on `PATH` is never run. On every host, a nested run with a
  stand-in `fcntl.py` on `PYTHONPATH` passes without importing it. The Windows cases print one
  `skip` line on POSIX, and the POSIX case one on MSYS, MINGW and Cygwin.
- **Shell scripts and hooks check out with LF everywhere.** Git for Windows' default
  `core.autocrlf=true` checked them out with CRLF, which `sh` cannot run, so on such a clone
  the gate, the hooks and `doctor.sh` could not start. Bootstrap now installs a
  `.gitattributes` with `*.sh text eol=lf` and the same for each of the gate's four hooks by
  name, and the kit's own clone carries the rule for its scripts. A project that already has
  a `.gitattributes` keeps it: bootstrap appends the rules it lacks, and never replaces the
  file, `--force` included. An existing project adds them by hand (item 1 below);
  `docs/DEV_SETUP.md` section 1 says why.
- **`spawn_worker.sh` on native Windows.** There is no tmux there, and the script stopped
  with `tmux is not installed`. On Git for Windows' `sh`, MSYS2 and Cygwin the worker now opens
  as a Windows Terminal tab (`wt.exe`, or the launcher `KIT_WT` names), not a tmux session,
  with the brief's instruction as its first prompt. The tab runs Git Bash by its full Windows
  path, because a bare `bash` in a new tab is WSL's launcher, and every `;` handed to `wt.exe`
  is escaped as `\;`, because `wt.exe` splits its command line there even inside quotes and
  cut the instruction in two. The tab opens in the window the lead runs in (`-w 0`), its
  command ends with `exit 0` (Windows Terminal keeps a tab whose command ended nonzero open),
  and a name a running Claude Code session already has is refused. Nothing can read the tab,
  so the start-up dialog check, `--batch`, `show_workers.sh` and `watch_workers.sh` do not
  apply there: watch the tab and wait for the result file. `doctor.sh` asks for `wt.exe` (or
  `KIT_WT`) there instead of tmux.
- **`close_worker.sh` on native Windows.** It ends the Claude Code process (`claude.exe`, or
  `node.exe` running Claude Code's `cli.js`) whose arguments, split as Windows splits a
  command line, hold `-n NAME` (`taskkill /T /F`; the tab closes), waits up to 15 s for it to be gone, then
  removes the worktree through the audit, as on POSIX. A session that survives, or a process
  list it cannot read (PowerShell's `Get-CimInstance`, or the lister `KIT_PS` names), leaves
  the worktree untouched and fails the close.
- **`clean_worktrees.sh` on native Windows, and a junction is never followed.** It said
  `NOT RUN on this platform` there and kept everything. It now reads each process's working
  directory from the process itself (its PEB; MSYS shells included; a process it cannot read
  counts as unseen, as on Linux), and the gate's lock is held when its file cannot be opened
  for writing. There a tracked script's bytes are compared, and its executable bit only in the
  index: Windows keeps none on disk. On Windows a folder in the worktree that is a reparse point (a junction, a
  folder symlink) counts as a mount point, which keeps the worktree: `git worktree remove` on
  Windows went through a junction to the main checkout's virtual environment and deleted part
  of it. Workers must not link shared folders into a worktree (`docs/WORKFLOW.md`).
- **WSL: worker tabs open in the lead's window.** `show_workers.sh` passed `wt.exe -w
  kit-<project>`, which opened a second window beside the lead's; it now passes `-w 0`.
- **A review run on native Windows.** `select()` takes only sockets there, so `review.sh`
  failed at once. Each pipe of the reviewer, of the copy's preparation and of the quota
  reader is now read by a thread, and a reviewer starts suspended, joins a Job Object with
  kill-on-close, then runs: stopping it ends every process it started, also one that outlived
  it holding a pipe, and a supervisor that dies takes its reviewer with it. The review
  self-test (`review.sh --self-test`, and with it the review case of `check.sh --self-test`)
  still needs a POSIX host (item 4 below).
- **`doctor.sh` and native Windows Python.** Native Windows Python under Git for Windows' `sh`
  is no longer a MISSING line; under any other `sh` (WSL, through interop) it still is, since
  it would take the Windows lock on POSIX paths. A CRLF is a CR before a line feed, read as
  bytes; a lone CR is not one.
- **`review.sh` and Git LFS.** The v0.9 filter refusal checked every path in the checkout,
  not the paths a review changes, and `git lfs install` sets `filter.lfs.clean` globally:
  one LFS file anywhere refused every review. A filtered path the review does not change now
  passes, and only when HEAD records it as a canonical LFS pointer, its working bytes (read
  with no filter) are that pointer or the content it names by size and sha256, and Git's own
  rendered diff of the working tree and of the index does not name it, proven both before and
  after the diff and the fingerprint read the checkout, so a file replaced in between is
  refused (`which changed while the review was being prepared`). The payload diff leaves such a
  proven path out, so its filter is never asked again. A filtered path the
  review changes is refused, whichever side was filtered: candidates include names staged in
  the index, deleted and renamed-away names, and the attributes are read in the working tree,
  in the index and at each end of the reviewed range. So an index-only change to an LFS file, a commit
  that deletes one, renames it out of the filter or drops its attribute while changing it,
  a filter rule staged together with the object it filters, and any other clean filter or
  `ident` on a path are refused. A path the review excludes (its own archives) is never
  refused, and the refusal says whether the review changes the path or the path is not an
  unchanged LFS file.
- **A changed LFS path is refused with no LFS driver configured.** A fresh machine without
  `git lfs install` let a staged LFS pointer through (the named filter counted only with its
  driver); a changed path with any named filter is now refused. A snapshot reads commit
  attributes through an index in the git directory, never under `TMPDIR`.
- **The Windows lock holder and a Ctrl-C at the launch.** The gate is created suspended and the
  Ctrl-C record read after it exists: a Ctrl-C just before the launch starts no gate.
- **Bootstrap** stops when it cannot read the kit's own `.gitattributes` rules, instead of
  stamping the version without them, and when a later line of the project's own file overrides
  one of them (asked of git, not read as text).
- **A review run on native Windows, end to end.** A reviewer installed as a `.cmd` (npm's
  `codex`, `claude`) is found by its bare name, and an argument `cmd.exe` would read as shell
  is refused; the evidence writer no longer opens a folder to fsync it; a scratch folder that
  cannot be removed never loses a completed review; a Ctrl-C as the reviewer's launch returns
  is held until the reviewer is owned, then stops it.
- **The line-ending repair** (item 1, `docs/DEV_SETUP.md`) leaves alone a script below a
  symlinked or junction folder instead of writing into the link's target.

### Upgrading a project from v0.9

<!-- Each numbered item is one checklist entry. sync-kit.sh prints an item from its marker to
the end of the item, so an item holds no blank line and no line that starts a list. -->

Work from the project's root, top to bottom. `KIT` is a fresh, full clone of the kit at v0.10
or later, never a v0.9 clone pulled forward and never a shallow one: on Windows a clone made
with `core.autocrlf=true` keeps its CRLF scripts after a pull (a pull does not rewrite a file
it did not change), so its `sync-kit.sh` cannot start, and item 3 merges from `620f25e` (or `KIT_BASE`), the
kit's v0.9 base commit, which a shallow clone lacks. Start with `"$KIT/sync-kit.sh" .`: it
installs the new kit-owned files (`doctor.sh`, `spawn_worker.sh` and the rest) and prints
this list, exits 2 and records no version (item 5 does). A conflict it lists stops it before
it copies anything: resolve that and run it again until it prints this list, so that item 4
checks the new files and not v0.9's (on native Windows, v0.9's `doctor.sh` asks for tmux).

1. **ACTION:** Line endings first, before any script of the project runs: add the kit's
   rules to the project's `.gitattributes` (created if absent; a symlink or anything else that
   is not a regular file there stops the step before it writes), turn each CRLF into LF in
   the shell scripts and hooks they name (regular files only: a file that is, or lies below,
   a symlink or a junction is left alone, with a line saying so, and a
   lone CR is kept; each file is replaced whole, with its mode, so a killed run leaves it old
   or new, and a failed rewrite stops the step before anything is staged), then renormalize
   those files alone, from a committed project. The file list is read once and checked: a
   `git ls-files` that fails (a corrupt index) stops the step. A temporary copy is removed when
   the run is stopped; one a SIGKILL left behind (`.crlf-*`) stops the next run by its name:
   ```sh
   ( if [ -L .gitattributes ] || { [ -e .gitattributes ] && [ ! -f .gitattributes ]; }; then
       echo "STOP: .gitattributes is a symlink or not a regular file; make it a regular file first" >&2; exit 1
     fi
     left=$(git ls-files --others -- ':(glob)**/.crlf-*')
     [ -z "$left" ] || { echo "STOP: a killed run left $left; delete it, then run this again" >&2; exit 1; }
     list=$(mktemp) || exit 1
     trap 'rm -f "$list"' EXIT; trap 'exit 129' HUP; trap 'exit 130' INT; trap 'exit 143' TERM
     set -- '*.sh' .githooks/pre-commit .githooks/pre-merge-commit .githooks/commit-msg .githooks/post-merge
     git ls-files -z -- "$@" > "$list" ||
       { echo "STOP: git ls-files failed (above); nothing was changed" >&2; exit 1; }
     { echo; cat "$KIT/core/.gitattributes"; } >> .gitattributes || exit 1
     python3 -I -c 'if 1:
         import os, signal, stat, sys, tempfile
         signal.signal(signal.SIGTERM, lambda *a: sys.exit(143))
         def plain(name):
             # Every folder on the way and the file itself: no symlink, no junction (a reparse
             # point), or the rewrite wrote into what the link points at, outside the project.
             parts = name.split(b"/")
             for i in range(1, len(parts) + 1):
                 info = os.lstat(b"/".join(parts[:i]))
                 if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                     return False
             return stat.S_ISREG(info.st_mode)
         for name in sys.stdin.buffer.read().split(b"\0"):
             if name and not plain(name):
                 sys.stderr.write("left alone, a link or not a regular file on its way: %r\n" % name)
             elif name:
                 with open(name, "rb") as script:
                     data = script.read()
                 if b"\r\n" in data:
                     handle, new = tempfile.mkstemp(prefix=b".crlf-", dir=os.path.dirname(name) or b".")
                     try:
                         with os.fdopen(handle, "wb") as copy:
                             copy.write(data.replace(b"\r\n", b"\n"))
                         os.chmod(new, stat.S_IMODE(os.lstat(name).st_mode))
                         os.replace(new, name)
                     finally:
                         if os.path.lexists(new):
                             os.unlink(new)' < "$list" ||
       { echo "STOP: a script could not be rewritten (above); nothing was staged" >&2; exit 1; }
     if [ -s "$list" ]; then
       xargs -0 git add --renormalize -- < "$list" || { echo "STOP: renormalizing failed (above)" >&2; exit 1; }
     fi
     git add .gitattributes )
   ```
   `git status` then lists `.gitattributes`, and any script the index held with CRLF as
   modified; both go into the upgrade commit (item 5). Every other clone on Windows runs the
   lines of `docs/DEV_SETUP.md` section 1 once after it pulls that commit: a pull does not
   check out again a file it did not change, so its scripts stay CRLF until then.
2. **ACTION:** Copy `claude_bridge.py` and `test_claude_bridge.py` whole from
   `$KIT/core/scripts/` into `scripts/`, replacing yours (they hold no project content). Each
   is copied beside its destination and renamed over it, so a symlink at either name is
   replaced by the file, never written through (a plain `cp` wrote into the link's target).
   A linked parent folder (a symlink or Windows reparse point) stops the step before any copy:
   ```sh
   ( new=; trap '[ -z "$new" ] || rm -f "$new"' EXIT; trap 'exit 130' INT; trap 'exit 143' TERM
     python3 -I -c 'if 1:
         import os, stat, sys
         for name in sys.argv[1:]:
             parts = name.split("/")
             for i in range(1, len(parts)):
                 parent = "/".join(parts[:i])
                 info = os.lstat(parent)
                 if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                     sys.exit("STOP: %s is a linked folder; nothing was copied" % parent)
                 if not stat.S_ISDIR(info.st_mode):
                     sys.exit("STOP: %s is not a folder; nothing was copied" % parent)' \
       scripts/claude_bridge.py scripts/test_claude_bridge.py || exit 1
     for f in claude_bridge.py test_claude_bridge.py; do
       new=$(mktemp scripts/.kit-copy-XXXXXX) && cp -p "$KIT/core/scripts/$f" "$new" && mv -f "$new" "scripts/$f" ||
         { echo "STOP: scripts/$f could not be replaced; it and the files after it are unchanged" >&2; exit 1; }
       new=
     done )
   ```
   If
   v0.9's item 10 sent this project to the manual review template only because of Git LFS,
   use `scripts/review.sh` again for every scope that changes no LFS file.
3. **ACTION:** Merge the kit's changes since v0.9 into the three files that hold your setup
   content, one three-way merge per file, from a committed project. A file that is not a
   regular file (a symlink), or below a linked folder, stops the step before any merge.
   Windows reparse points count as links too. The v0.9 copies go to a private
   folder outside the project (a `TMPDIR` inside it stops the step), each merge result replaces
   its file whole, with its mode, and a failed read or merge stops the step there. A run that
   is stopped removes what it made; what a SIGKILL left (`.kit-merge-*`) stops the next run by
   name. The base is the kit commit your v0.9 came from: `620f25e`, the v0.9 release, unless
   the project synced an earlier v0.9 commit (project_leeway synced `00581dd`): then set
   `KIT_BASE` to that commit first, or the merge reads the kit's own later v0.9 fixes as yours:
   ```sh
   ( from=${KIT_BASE:-620f25e}
     set -- scripts/check.sh docs/DEV_SETUP.md docs/GOTCHAS.md
     python3 -I -c 'if 1:
         import os, stat, sys
         for name in sys.argv[1:]:
             parts = name.split("/")
             for i in range(1, len(parts) + 1):
                 path = "/".join(parts[:i])
                 info = os.lstat(path)
                 if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                     sys.exit("STOP: %s is a link; nothing was merged" % path)
                 if i < len(parts) and not stat.S_ISDIR(info.st_mode):
                     sys.exit("STOP: %s is not a folder; nothing was merged" % path)
             if not stat.S_ISREG(info.st_mode):
                 sys.exit("STOP: %s is not a regular file; nothing was merged" % name)' "$@" || exit 1
     for f do
       [ -f "$f" ] && [ ! -L "$f" ] ||
         { echo "STOP: $f is not a regular file (a symlink?); nothing was merged" >&2; exit 1; }
     done
     left=$(git ls-files --others -- ':(glob)**/.kit-merge-*')
     [ -z "$left" ] || { echo "STOP: a killed run left $left; delete it, then run this again" >&2; exit 1; }
     git -C "$KIT" cat-file -e "$from^{commit}" ||
       { echo "STOP: $KIT has no commit $from (a shallow clone?); clone the kit whole" >&2; exit 1; }
     base=$(mktemp -d) || exit 1
     new=; trap 'rm -rf "$base"; [ -z "$new" ] || rm -f "$new"' EXIT
     trap 'exit 129' HUP; trap 'exit 130' INT; trap 'exit 143' TERM
     case $(CDPATH= cd -- "$base" && pwd -P)/ in "$(pwd -P)"/*)
       echo "STOP: the temporary folder $base is inside the project (TMPDIR?); set TMPDIR outside it" >&2; exit 1 ;;
     esac
     for f do
       git -C "$KIT" show "$from:core/$f" > "$base/v0.9" ||
         { echo "STOP: cannot read core/$f at $from; $f and the files after it are not merged" >&2; exit 1; }
       git merge-file -p "$f" "$base/v0.9" "$KIT/core/$f" > "$base/merged"
       [ $? -lt 128 ] && new=$(mktemp "${f%/*}/.kit-merge-XXXXXX") && cp -p "$f" "$new" &&
         cat "$base/merged" > "$new" && mv -f "$new" "$f" ||
         { [ -z "${new:-}" ] || rm -f "$new"; echo "STOP: $f could not be merged; it and the files after it are unchanged" >&2; exit 1; }
       new=
     done )
   ```
   Resolve every conflict the merge left (`git diff --check` names each leftover marker) so
   that the kit's new lines and every line of yours survive, then read `git diff HEAD --
   <file>` for each file and account for every removed line.
4. **ACTION:** Prove the result: `./scripts/doctor.sh`, `./scripts/check.sh` (expect `CHECK:
   PASS`), then `./scripts/check.sh --self-test` (expect `SELF-TEST: PASS`). On native Windows
   the self-test cannot pass yet: its review case fails because `review.sh` needs POSIX
   signals (above). There, run `./scripts/check.sh` and `./scripts/check.sh --self-test` from
   Git for Windows' `sh` with the Windows `python3` and expect exactly this: `CHECK: PASS`;
   in the self-test, `ok` for every case including the thirteen Windows lock cases and the
   `sitecustomize.py` line, except
   `FAIL — review adapter negative tests failed or did not run` with the review tests' own
   output, the line `skip — a stray cygpath on a POSIX PATH` (a POSIX-only case), and a
   `skip` the project's own setup prints (the commit-msg hook when `AGENTS.md` has no
   attribution rule line); the last line is then `SELF-TEST: FAIL`. Any other `FAIL` or `skip`
   blocks the upgrade. Then run the whole `--self-test` once more from WSL or another POSIX
   shell on the same commit, where it must say `SELF-TEST: PASS` (there the Windows cases
   print one `skip` line). A project with no POSIX shell has partial acceptance only; say so
   in its state file.
5. **ACTION:** Record the version BEFORE the upgrade commit, so the commit carries it: run
   `"$KIT/sync-kit.sh" . --actions-applied`, which writes `docs/kit/.kit-version` (the first
   run already installed the kit-owned files, so it copies nothing new; if it lists a file as
   overwritten, prove item 4 again), then run `./scripts/check.sh` again and commit everything the upgrade changed together with
   `docs/kit/.kit-version` in one commit. Stamped after the commit, the version file was left
   modified and every other clone still read v0.9.

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
- **A project that is not a plain POSIX checkout.** The kit ships a `.gitattributes` that
  keeps the hooks and scripts LF under `core.autocrlf=true` (a CRLF `#!/usr/bin/env sh`
  killed every hook); `bootstrap.sh` stops, and names it, on a `core.hooksPath` of the
  project's own (husky, lefthook) instead of replacing it in silence; the scripts find
  Python as `python` or `py` where `python3` is absent; a sparse checkout is reviewable (a
  skip-worktree entry whose file is absent hides nothing; a present one is still refused);
  a project that already runs its own hooks (husky, lefthook) keeps them beside the kit's
  as `.githooks/<name>.project`, project-owned, run first by the kit's hook with git's
  arguments (its failure is the commit's; the kit's hook runs after it); `bootstrap.sh`
  stops on any other `core.hooksPath` from any scope and verifies the wiring as git sees
  it; the review tooling and the worktree clean-up IMPORT on native Windows Python through one
  platform seam in `agent_process.py`, and no more than that: a review run (pipes are not
  selectable there), the gate lock and the clean-up need a POSIX host, and `doctor.sh` says
  so and sends the owner to WSL; the clean-up keeps every worktree there and says why. **ACTION:** `.gitattributes` is
  project-owned (a project's own merge and LFS rules must survive a sync), so the sync
  does not install it: copy `$KIT/core/.gitattributes` into the project, or append its
  three rules to the project's own file, and commit.
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
   Code overlay also copy `scripts/show_workers.sh`,
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

14. **ACTION:** A checkout holding the kit's hooks and scripts with CRLF (Windows,
    `core.autocrlf=true`) cannot even run its pre-commit (`sh\r`), so the repair comes
    before any commit. First commit or stash your edits under `.githooks/` and `scripts/`.
    Add the kit's `.gitattributes` rules (the bullet above) and stage them:
    `git add .gitattributes`. Then `git add --renormalize .githooks scripts` (LF in the
    index), then re-check out ONLY the tracked files there:
    `git ls-files -z -- .githooks scripts | xargs -0 rm -f && git checkout -- .githooks scripts`
    (untracked and ignored files under those folders stay), then
    `git commit -qm "Renormalise the kit scripts"`. A hook that still starts with `sh\r`
    is one this step missed.

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
