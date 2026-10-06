# Overlay: Claude Code

Install with `bootstrap.sh . --overlay claude-code`. This README is NOT copied — only
`files/` is.

**The commands live in the plugin, not here.** `/myagentkit:handoff`,
`/myagentkit:cross-review` and `/myagentkit:kit-feedback` are installed once per machine:

```
/plugin marketplace add KBT-0/MyAgentKit_Keel
/plugin install myagentkit@myagentkit
```

Those two lines are typed by a human — an agent cannot invoke slash commands. This overlay
is the part that has to be copied into each project instead, because every file in it is
project-specific.

## Why this split

A command is the same in every project, so it belongs in a versioned plugin you install once
and upgrade in place. The files below are not: they carry `{{PLACEHOLDERS}}` that the setup
interview fills with THIS project's boundaries, risky areas and gated paths. A plugin cannot
hold them, and copying a command into every project would mean fixing a bug in it once per
repository.

## What it adds

| File | What it is |
|---|---|
| `CLAUDE.md` | One-line pointer to `AGENTS.md`. Content never goes here |
| `.claude/settings.json` | Registers the three hooks below |
| `.claude/hooks/gate_on_stop.sh` | Runs the gate if a turn left the watched paths dirty — early feedback, never the rule |
| `.claude/hooks/guard_boundaries.py` | Flags a forbidden import the moment it is written, seconds instead of a commit |
| `.claude/hooks/guard_destructive_git.py` | Refuses `reset --hard`, `checkout --`, `clean -f`, `stash drop` and force pushes while the tree is dirty, and prints what would be lost |
| `.claude/agents/diff-reviewer.md` | Read-only review subagent carrying THIS project's risky areas and `docs/REVIEW_GATE.md` |
| `.claude/agents/worker.md` | Implementation worker with a one-hour prompt cache and a 150-turn cap, for tasks that run jobs longer than five minutes (`docs/WORKFLOW.md`, "Worker cost") |
| `scripts/spawn_worker.sh` | Opens a SEPARATE worker session in tmux and hands it a brief file; the lead then subscribes for its idle notice instead of polling |
| `scripts/clean_worktrees.sh` (+ `.py`) | Removes the finished worktrees under `.claude/worktrees`, only what it proves safe to lose, never a branch; `.githooks/post-merge` runs it after every merge git completes itself in the main worktree |
| `.claude/worktree-disposable` | The project's list of folders a finished worktree may lose (build output) and its quiet period; ships empty, the interview fills it; without it the hook does nothing |

## A worker session is always visible

A spawned session can stop on a permission prompt, the folder-trust dialog or a question,
and the idle notice does not fire for a session that waits inside a dialog: it hangs where
nobody looks, for as long as nobody looks. Two scripts close that, both kit-owned.

**`scripts/show_workers.sh NAME [NAME...]`** opens ONE terminal window with a tab per named
tmux session, each running `tmux attach -t =NAME`. `spawn_worker.sh` calls it for every
session it starts, once the brief has landed. A lead starting several passes `--batch` to each
spawn and then shows them together, so they open as one window and not one at a time:

```sh
scripts/spawn_worker.sh w1 briefs/w1.md --batch
scripts/spawn_worker.sh w2 briefs/w2.md --batch
scripts/show_workers.sh w1 w2
```

What opens where:

- **WSL with Windows Terminal**: one `wt.exe -w kit-<project folder> new-tab ...` call, a
  tab per session. The window name is fixed per project, so a later call adds its tabs to
  the window that holds the earlier ones: that is what `-w NAME` is documented to do; a
  script on the WSL side can see that each tab attached, not which window it is in.
  `KIT_WT` names another launcher than the `wt.exe` found on PATH or under `/mnt/c/Users`.
- **macOS, iTerm2** (the lead runs in it, or it is installed and the lead does not run in
  Terminal.app): a new window, a tab per session, through `osascript`.
- **macOS, Terminal.app**: one window per session. Adding a tab there needs the
  accessibility permission, which a script must not ask for; the output says so.
- **Anything else**: nothing opens; the script prints `attach by hand: tmux attach -t NAME`
  for each session and exits 0.

A session counts as shown only once `tmux list-clients` lists a client for it within eight
seconds; any other gets its attach line. A session that already has a client is skipped
with a line, so running the command twice opens no second tab. A session name outside
`[A-Za-z0-9_-]` is refused by name (it crosses into a Windows command line or an AppleScript
string, where `;` starts another subcommand), and so is a session that does not exist: in
both cases nothing opens and the exit status is 1. Every launch is bounded at five seconds;
WSL interop down ("Exec format error") is one line plus the attach lines. `--print` prints
the exact command and runs nothing. Closing a tab detaches; the session keeps running.
Attaching resizes the tmux window to the new tab, and the worker's TUI redraws to it.

**`scripts/watch_workers.sh NAME [NAME...]`** is run by the lead as a BACKGROUND command. It
returns, and so re-invokes the lead, as soon as a named session is GONE or WAITING on a
person; for WAITING it prints what waits and the last lines of the pane, so the lead can tell
the owner. Otherwise it ends after `--max-minutes` (110) with one line saying nothing waited.
It reads each pane every `--interval` seconds (45, at least 10) with `tmux capture-pane`,
which costs the worker nothing.

What counts as waiting is in ONE file, `scripts/waiting_patterns.txt`, which
`spawn_worker.sh` uses too (for the trust dialog at start-up). A rule needs the dialog's own
key hint on the pane's LAST line and its option line just above: a worker whose output
quotes "Do you want to proceed?" is not waiting, and a phrase match anywhere said it was.
Each rule is flagged:

- **VERIFIED**: written from a real pane captured on the Claude Code version it names (the
  trust dialog, a permission prompt and a question on 2.1.285; the captures are the kit's
  test fixtures).
- **UNVERIFIED**: a guess nobody has seen on a real pane (an older wording of the trust
  dialog, any other numbered choice ending in "Esc to cancel"). It ships, because a missed
  wait costs more than a false one.

`scripts/watch_workers.sh --list-patterns` prints the table. Not covered: a session idle at
its input box (the idle notice covers that), a dialog drawn differently by a later version
(capture it, add the rule with its version), and a terminal other than the three above.

A session that is neither gone nor waiting is checked for two more things, and every report
exits 0 with its kind on the first line (`watch_workers: KIND: NAME, ...`):

- **The result file**, named per session with `--result NAME=PATH`. Once the file is in HEAD
  of the tree that holds it and that tree is clean, the watcher reads its head
  (`docs/HANDOFF.md`): `Kind: completed` is **DONE** with the task, the attempt and the
  `Remaining:` line; `blocked`, `handoff` and `progress` are **BLOCKED**, **HANDOFF** and
  **PROGRESS**, none of them done; a missing or malformed head is **MALFORMED**, not done. A
  file with questions under `## Open questions for ...` is **QUESTIONS** first: "N questions
  for OWNER" and their text with the options, each line cut at 200 bytes. Each committed
  version of the file is reported once.
- **The context figure** in the pane's status line, `<used>/<window>` with k or M (`Opus 5.5
  58k/1.0M high` in the real capture; the `context` rule of `waiting_patterns.txt`). Past
  `--context-warn` percent (50) it is **CONTEXT** with the figure, once per session. A status
  line without the figure, or none at all, is CONTEXT once too, and the figure is never
  guessed; `--once` skips that note, because `spawn_worker.sh` runs it before the status line
  is drawn. The figure comes from the status line the project configured; a project whose
  status line does not show it gets the note once and no warning.

The once-markers are user options of the tmux session (`@kit_watch_result`,
`@kit_watch_context`), so they end with the session. What the lead does with each report is
in `docs/WORKFLOW.md`, "The lead's steps when a branch is ready".

## Placeholders this overlay brings

| Placeholder | What goes in |
|---|---|
| `{{WORKER_MODEL}}` | The author model from the interview (`sonnet`, `opus`, or a full model id) |
| `{{LONG_JOBS}}` | The project's jobs that run longer than a few minutes, by name, as the interview's question 8 recorded them |
| `{{WORKER_EFFORT}}` | The worker's reasoning effort (`low`, `medium`, `high`), as the interview's question 8 recorded it: `high` when the worker's tasks bear design, lower when they are mechanical |

`diff-reviewer.md` ships with `effort: high` and no placeholder: reviews run at high effort.

If the project has no such jobs, delete both files instead of filling them.

## Worker sessions — what cost a session each before it was written down

- **Separate sessions and one-hour sub-agents cost the same.** Both were measured against a
  sub-agent with the default five-minute cache on the same task; both avoid the re-writes.
  Choose by visibility: a tmux session can be watched and survives the lead ending.
- **A new `.claude/agents/*.md` file is not loaded by a running session.** Restart the
  session (or spawn the worker from a session started after the file existed) and verify in
  the worker's transcript that its cache writes are `ephemeral_1h`, which
  `scripts/agent_cost.py` prints in its `1h/5m` column. The one-hour cache is ignored while
  the account runs on usage credits.
- **The prompt must never follow a variadic flag.** `claude --allowedTools A,B "prompt"`
  reads the prompt as one more tool name and opens idle at an empty input line.
  `spawn_worker.sh` types its prompt after the TUI is up for that reason.
- **The brief goes by path, as one typed sentence, never pasted as a block.** A session
  handed its brief as one pasted block with no sentence typed by the user took it for
  content carrying no instruction and sat idle for about 35 minutes asking for
  confirmation; another model given the same block started at once. `spawn_worker.sh`
  types `Read '<absolute path of the brief>' and follow it.` and refuses, before any tmux
  session opens, a brief file that does not exist or cannot be read.
- **A worker's worktree is made with `git worktree add`, not with `claude -w`.**
  `claude -w` built the worktree from a stale base, so workers spawned after the lead
  merged fixes started without them. `spawn_worker.sh --worktree` runs
  `git worktree add .claude/worktrees/NAME -b worktree-NAME HEAD` from the lead's checkout
  and opens the session inside it; a leftover `worktree-NAME` branch is refused by name.
- **Every value the script puts into the session's shell command is quoted by one helper.**
  A `--settings` JSON string or a name with an apostrophe otherwise ended its quoting and
  the rest ran as shell in the new pane.
- **A standalone `sleep` in a Bash tool call is refused by the tool**, so a worker cannot
  even wait badly; it starts the job in the background and is re-invoked when it exits.
- **`pgrep -f` matches its own command line** (`docs/GOTCHAS.md`).
- **An untrusted folder blocks a spawned session in the trust dialog.** Open the folder once
  by hand before the first spawn; the script reports the dialog instead of waiting.
- **Decide the permission mode of spawned sessions with the owner before the first one.** A
  permission prompt stalls an unattended session, and an agent never widens permissions on
  its own. In the founding project the owner chose the same auto mode the lead sessions use,
  with the project hooks active and no allow-list; a narrow `--allowed-tools` list is the
  alternative where the owner wants it, at the price of a stall on any command outside it.
- **The worker definition's body carries the project's job rules**, not only the kit's: the
  lock that serialises heavy jobs, the memory ceiling, the environment variable a worktree
  needs. The interview's question 8 asks for them; without them the first worker learns them
  from a crash.
- **The idle notice fires every time the worker parks on a background job**, not only at
  the end: a session whose turn ended with a job running is "idle" to the harness, and the
  same notice was delivered three times for one pilot. Subscribe once, and have the brief
  end with a result FILE (plus, if the lead wants a push, one message from the worker);
  re-subscribing on every notice is a poll loop in disguise.
- **A sub-agent inherits its lead session's effort unless its definition sets `effort:`**,
  and nothing in its output says so: a side-by-side comparison ran two sub-agents at the
  lead's medium against a high-effort run of another CLI, and the skew surfaced only in the
  transcripts. Both definitions here set it. A spawned session takes the user's default
  effort instead; pass `--effort` to the spawn script. `scripts/agent_cost.py` does not show
  effort, so verify it after the run by grepping the transcript for `"effort"`.
- **A spawned session does not end when its task does.** A pilot worker wrote its result
  file and then sat idle in tmux for 40 minutes until it was killed by hand, and the idle
  notice cannot tell that apart from a park on a background job (above). The LEAD closes
  it: read the result file, then `tmux kill-session -t NAME`. The brief says so, and
  `spawn_worker.sh` prints the line when it starts the session.
- **A worktree-isolated agent refuses any shell command it cannot prove keeps git inside
  its worktree**, and each refusal costs a turn (a project saw about 177 across 40 worker
  transcripts). Refused: `$(...)` or a variable around a program, loops, `sh -c` or `source`
  of a string, `flock <lock> <cmd>` when the command runs git (`check.sh` does), `cd` to the
  main checkout before git. The brief's shape: one plain command per call, anything
  repeated or compound in a script file run as `sh that-file`, merging left to the lead in
  the main tree. `worker.md` says so; keep the line when you edit the definition.
- **A sub-agent is refused when it writes a report file.** Claude Code answers "Subagents
  should return findings as text, not write report files" (eight refused `REPORT.md`
  writes in one project; `notes.md` and code files were not refused). The advice to end a
  brief with a result FILE is for a separate spawned session. A sub-agent's brief asks for a
  short final message and lets it write only logs, tables and captures to files
  (`docs/WORKFLOW.md`, "Worker cost", rule 7).
- **Every message to an idle session is a full-context turn.** Ask the brief for a result
  FILE, subscribe once with `notify_when_idle`, and read the file.

## Finished worktrees are removed after a merge, and only those

A project using the kit piled up 39 merged worker worktrees, 34 GB, and a session removed them
by hand after auditing each: merged into main, nothing uncommitted, and in 17 the only extra
file a review report whose identical copy was archived on main. `scripts/clean_worktrees.sh`
is that audit, run by `.githooks/post-merge` after every merge git completes itself in the main
worktree (never after a merge inside a linked one). git does not run that hook after a merge
that stopped on a conflict and was finished with `git commit`, nor after `git pull --rebase` or
`git cherry-pick`: the next merge, or the script by hand, cleans up then. Without an option the
script is a dry run that prints the first reason to keep each worktree (`--all-reasons` prints
every one); `--apply` removes. The hook prints the removals and the summary lines. It needs git
2.36 or newer (`git worktree list --porcelain -z`); with an older git the hook says so once and
then stays quiet.

- **It never deletes a branch.** The disk is in the worktree; the branch keeps the worker's
  commits whatever happens to main later (a merge undone with `git reset`, a merge into a
  detached HEAD). The report lists the branches whose worktrees it removed and says how to
  delete merged branches yourself: `git branch --merged <main branch>` lists them, `git branch
  -d <name>` deletes one, and its reflog with it; the refs under `refs/kit/saved/` keep the old
  tips a removal saved. Nothing is removed while the main worktree's HEAD is detached:
  "merged" is tested against its branch.
- **Removed** only when every check holds, cheapest first: a linked worktree directly under
  `.claude/worktrees/`, its folder its own (not missing, not prunable), not locked, its path
  and branch printable; on a branch; **a commit made in that worktree**, which its own HEAD
  reflog records (`commit`, an amend, a conflicted merge or cherry-pick concluded by `git
  commit`, `cherry-pick`, `revert`, `am`, a rebase step that wrote a commit; not a
  fast-forward, not a merge made by `git merge` alone: a worktree added on a finished branch,
  or a worker that only fast-forwarded, is kept); its HEAD in the main branch; nothing in its
  git directory changed within the quiet period; no merge, rebase, cherry-pick, revert, bisect
  or sequencer under way; no process working inside it that the listing shows, no tmux session
  of its name, the gate's lock free; **nothing only its git directory holds**: every object id,
  in either case, in every file of that directory (both columns of every reflog line, every ref
  such as `refs/worktree/*`, `refs/bisect/*`, `refs/rewritten/*`, every pseudo-ref such as
  `ORIG_HEAD` or `FETCH_HEAD`, and any file the script does not know; only the index, the
  gate's build log and `AUTO_MERGE`, a tree git leaves after a merge or rebase step, are
  skipped) names no object, or a commit a ref of the repository holds (no reflog counts, nor a
  remote-tracking ref, which a later `git fetch --prune` drops), or a commit it saves first
  (below); the files ref
  backend (another one is kept); no per-worktree config; **tracked content by bytes**: no
  change `git status` reports with the stat settings forced to their defaults, the index equal
  to HEAD's tree, and every tracked path in the worktree byte for byte the blob the index
  records, with the same executable bit (a symlink: the same text), so no stat cache, filter or
  line-ending conversion is trusted; no unresolved entry, no submodule; **no mount point
  anywhere in it**, disposable folders included: `git worktree remove` would delete what is
  under one, which is not the worktree's; every file git does not
  track inside a folder `.claude/worktree-disposable` lists or byte-identical to the regular
  file at the same path in main, outside main's `.claude/worktrees` under any spelling (what is
  there is a worktree's, which may go too), **not at or below a mount point in main** (a
  mount inside main is not main),
  not the worktree's own file seen from main (a hard link, a worktree folder mounted into
  main: the same device and inode), and not a tracked file under another name (a
  case-only rename on macOS, a hard link: the same file on disk); no file at all under the
  worktree's own `.claude/worktrees` (a worktree inside a worktree is not judged);
  nothing anywhere in it, those folders included, changed within the quiet period.
- **Mount points are out of what it reasons about.** A mount point is an entry on another
  device than the worktree's root (or main's), or, on Linux, one `/proc/self/mountinfo` lists:
  only that table shows a bind mount on the same device. On macOS and other systems a bind
  mount on the same device cannot be seen; a mount on another device is seen everywhere. On
  Linux without a readable mount table every worktree is kept.
- **Case.** Where a probe finds the file system ignores case (macOS by default: a file made
  in the git directory is found under its name in upper case), the places that hold work
  (`docs`, `.claude`, `.myagentkit`, `scripts`, `.git`), the worktree's own
  `.claude/worktrees` and the disposable entries are compared case-folded, as that file system
  compares names: `Docs/build` is under `docs`, never disposable. Elsewhere byte for byte.
- **What only its git directory holds is saved, then it is removed.** A commit no ref holds
  (an amended, reset or rebased-away tip, a squash's intermediate commits, a `FETCH_HEAD`, a
  `refs/worktree/*` ref) is pinned before anything is deleted, in one `git update-ref --stdin`
  transaction, as `refs/kit/saved/<git directory name>-<hash>-<UTC time>/<n>`, never under the
  branch name; only the commits no other saved one reaches get a ref. Every byte of the name but
  a letter, a digit, `-` and `_` is percent-encoded, the result is cut to 64 bytes, and 12 hex
  digits of the whole name's SHA-256 tell two cut names apart (the log holds the whole name). The audit then runs again with those refs
  counted. A failed save keeps the worktree. The report names
  each saved commit and prints one command that deletes all of that removal's saved refs: `git
  for-each-ref --format='delete %(refname)' 'refs/kit/saved/<name>-<hash>-<time>/' | git update-ref
  --stdin`. **These refs never expire on their own**: they are gc roots, they appear in `git
  log --all`, and `git push --mirror` would publish them. They pile up, one
  `<git directory name>-<hash>-<UTC time>/` folder per removal that saved something: `git
  for-each-ref refs/kit/saved/` lists them all, and `git for-each-ref --format='delete
  %(refname)' refs/kit/saved/ | git update-ref --stdin` deletes them all.
- **Kept**, with the reason, otherwise; each of these is the owner's to remove by hand: check
  what the reason names, then `git worktree remove <path>` without `--force` (git refuses a
  worktree with changes of its own; the branch stays). A squash-merged branch, or one whose
  commits main took by rebase or cherry-pick, is kept: its own tip is not in main. A tree or
  blob id in its git directory keeps it: reachability is checked for commits only. A repository
  using Git LFS or any other filter, or `core.autocrlf`, is not cleaned automatically: the
  worktree's bytes differ from the blobs. A worktree holding build output that is not listed as
  disposable is kept, and the report names the folders to consider listing.
- **Not in use: what each platform counts.** Before it trusts a process listing the script
  finds ITSELF in it with its own working directory; a listing that does not show it is not
  proven, and every worktree is kept. Linux reads `/proc`: another user's process, or one of
  ours made non-dumpable, is listed but unreadable, and the report counts it. Elsewhere (macOS)
  it runs `lsof`; a non-zero exit is accepted only when the listing shows the script and every
  line on stderr is lsof's "can't stat()" warning. lsof escapes a name it cannot print (`café`
  as `caf\xc3\xa9`); the script reads each escape back to its bytes, and a name it cannot read
  back exactly (lsof writes a control byte and a `^` in a name the same way) leaves the listing
  unproven. A working directory is compared case-folded and Unicode-normalised, as macOS
  compares names. macOS `lsof` does not list another user's
  processes at all, so the count there does not include them. Where no listing is proven (no
  `/proc`, `lsof` missing or failing), every worktree is kept and the report gives
  `scripts/clean_worktrees.sh --apply --assume-idle` to run by hand.
- **Proven, and what is a margin.** Finished, merged, unchanged and nothing only its git
  directory holds are proven from git and the filesystem. "Not in use" is not: a sub-agent
  worker holds no process inside its worktree between commands and has no tmux session. The
  commit made in it and the quiet period (`quiet-minutes=<n>` in `.claude/worktree-disposable`,
  default 60, at least 10, given once: a second or invalid line refuses the whole list, so
  nothing is disposable and 60 applies; the newest mtime or ctime of anything in it or its git
  directory) cover that worker; they are a margin, not a proof. The process listing is read
  afresh for each worktree, and again right before the first deletion and right before `git
  worktree remove`. Not guarded, by the owner's decision: a process changing a worktree's files
  between its audit and its removal, files planted to attack the script, and a SIGKILL between
  two removal steps.
- **With `core.logAllRefUpdates=false`** git writes no HEAD reflog, so every worktree is kept
  ("no commit was made in this worktree").
- **To keep a worktree** the lead still wants, lock it: `git worktree lock <path>`.
- **The log**, `<git dir>/kit-worktree-removals.log`, gets two lines per removal, each after
  the time and `run=<UTC time>-<process id>`, the run's id, which pairs them. The `intent`
  line comes first, before any ref is saved or file deleted: path, branch, tip commit,
  main HEAD, git directory, identical files, disposable bytes, each ref to save with its commit,
  each file to delete. The `outcome` line comes once `git worktree remove` returns or a step
  stops it: `removed` when git removed it, whatever was deleted before; else `partly-modified`
  (stopped after a deletion), `possibly-modified` (`git worktree remove` failed) or `kept`;
  why, and each file deleted. **An intent with no outcome of the same run and path is a run
  that did not finish** (a SIGKILL, a crash): the refs and files it names may be saved or
  deleted. Both are on disk before the script goes on, and every line the script
  prints about a removal comes after the log line it reports. An outcome that cannot be written
  leaves the removal as it is, stops the run there (the worktrees after it are not looked at)
  and exits 1. A print never raises: what the terminal cannot encode is escaped, and a terminal
  closed from the start, closed or hung up is ignored, so neither changes the removal, its
  outcome or its exit status. Every name the script prints or logs is escaped reversibly,
  as the log's first line says: a backslash as `\\`, a newline as `\n`, any other byte that is
  not printable UTF-8 as `\xNN`. After the saved refs the identical copies git does not track
  go, then `git worktree remove` without `--force` checks again on its own. SIGINT, SIGTERM and SIGHUP are caught from the saved refs
  to the end of `git worktree remove` and stop it at the next step. If a step fails or is
  stopped after a copy was deleted, the report says **PARTLY MODIFIED**, lists each deleted file
  (its byte-identical copy is at the same path in the main worktree) and the script exits 1. A
  failed `git worktree remove` may have deleted files first (git deletes file by file, then the
  worktree's git directory even after a failure): the report says **POSSIBLY MODIFIED**, what
  is left, and how each kind of file comes back (tracked: the printed `git restore` or `git
  worktree add`; untracked: its copy in the main worktree; disposable: the build), and the
  script exits 1. When copies were deleted and then `git worktree remove` failed, the log says
  `possibly-modified` (git may have deleted more) and the report lists both. A re-run is safe; each deletion changed its folder, so it finishes after the
  quiet period.
- **A worktree comes back** with the command each removal prints on a line of its own, `git
  worktree add '<path>' '<branch>'`, quoted for a POSIX shell: its tracked files at the
  branch's last commit. A name that is not printable ASCII is printed as `"$(printf
  '\NNN...')"`, octal escapes a POSIX shell turns back into its bytes, so the pasted command
  reaches the same path and branch whatever the terminal can show. Lost for good: the ignored files in its disposable folders and its own
  reflogs (every commit they named is held by a ref, or saved).
- **Installed** by the overlay: the two scripts (kit-owned: a sync updates them) and
  `.claude/worktree-disposable` (the project's). The hook comes with the core; without all
  three it does nothing and says so once.
- **Off:** `KIT_NO_WORKTREE_CLEANUP=1` in the merge's environment.

## Why this is an overlay and not part of the core

The kit's rules are tool-agnostic: `AGENTS.md`, the workflow, the review protocol, the state
file, `scripts/check.sh`, the git hook and CI all work under any CLI agent, or none.

These files do not. They are Claude Code's config format — its hook events, its subagent
definition. Shipping them in the core meant every project got a `.claude/` directory whether
or not anyone used that tool, and it let the kit imply a neutrality its automation did not
have. An engine is an overlay here; so is a host agent.

If you use a different tool, take the IDEAS: the hooks are worth reproducing, and the
commands are thin wrappers over `docs/HANDOFF.md` and `docs/REVIEW_GATE.md`, which are in
the core and readable by anything.

## What `/myagentkit:cross-review` needs

A SECOND CLI on the machine — a DIFFERENT model from the one authoring the change, in
whichever direction the project configured. `scripts/review.sh` ships adapters for two,
selected with `--reviewer codex` or `--reviewer claude`, and both archive the same evidence.
Install the other one and log in, or the command reports that it is missing and falls back to
the paste-by-hand template in `docs/REVIEW_RUNNING.md`.

This overlay is for Claude Code as the HOST, not for Claude Code as the author. A project
where Codex writes and Claude reviews still installs it if anyone opens Claude Code in the
repository. There is no `overlays/codex/`, and
[docs/delegation-is-not-symmetric.md](../../docs/delegation-is-not-symmetric.md) says why.

The vendor plugin (`openai/codex-plugin-cc`) is OPTIONAL and is not used by
`scripts/review.sh`; it adds in-session delegation commands, which the kit does not ship for
this direction. `docs/DEV_SETUP.md` §3 covers
both, including the two cautions worth reading before installing it.

Install it ALONGSIDE `/myagentkit:cross-review`, not instead of it. Its `/codex:review` is a
review TOOL — a second model over your git state, generic and fast. `/myagentkit:cross-review`
is the review GATE: it carries this project's own priority order, requires the caller to
verify each finding instead of relaying it, archives the report as evidence under
`docs/reviews/`, and ends in a verdict whose manual checks land in `docs/STATE.md` before the
commit. Different jobs. The kit README's "Recommended setup" section spells the difference
out.

## The hooks are not the gate

`.githooks/pre-commit` is. These fire earlier and only in one tool; they exist to shorten the
feedback loop, not to carry enforcement. Nothing here is load-bearing — deleting the whole
overlay leaves every rule intact and every gate running.
