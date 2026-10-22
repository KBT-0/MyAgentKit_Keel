<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->

# GOTCHAS — the kit's part

The kit's generic entries of `docs/GOTCHAS.md`, under its headings. The project's file keeps
its placeholders, its owner's decisions and its own rules, and each heading there whose text
moved ends with a "Kit rules:" line naming the heading here. This file is the kit's, and a sync
replaces it. Generic rules live here by the owner's decision of 2026-10-22 (docsowned question
1, #94); the rule that a kit-owned file holds only reasons (`docs/WORKFLOW_RATIONALE.md`) is
`docs/WORKFLOW.md`'s alone. Do not edit it: a project that needs a different rule writes it in
`docs/GOTCHAS.md`, the project-owned file, and the project file wins over this one.

The entries below ship with the kit. They are not hypothetical: each cost a real day
somewhere, and none of them depends on a particular language or stack.

## Contents

A new entry adds its heading to this list. A project's `docs/GOTCHAS.md` lists the
entries it was installed with; one the kit added later is listed here.

- Uncommitted work is NOT in the reflog
- `.gitignore` — the LAST matching rule wins
- The executable bit has to be put in the git index by hand
- A fake-CLI test harness cannot catch what the real CLI rejects
- A tool's relative output path resolves against ITS working directory, not yours
- Waiting on your own process: `pgrep -f` and shell wait loops match themselves
- An agent puts the user's e-mail into a web request
- A red gate that passes on re-run is a finding, not a pass
- A checkout under `/mnt/<drive>` in WSL
- Under WSL, a file named `*.exe` runs on Windows
- A build server the gate started keeps the gate lock
- A worker spawned from a lead's shell inherits its child-session markers
- Background jobs die with the session and in a low-memory reap
- An incremental build misses its always-run inputs
- A timing taken on a busy machine is not a result
- PowerShell from the Microsoft Store leaves suspended processes behind
- A variable the session set does not reach the git hook
- A PowerShell probe whose Set-Location fails goes on in the current folder

---

## Uncommitted work is NOT in the reflog

`git reset --hard`, `git checkout -- <path>`, `git restore`, `git clean -f` and
`git stash drop` discard the working tree, and the reflog does not save you: it records
COMMITS. Uncommitted edits and untracked files are not in the reflog and cannot be
recovered; content you had staged may survive as a loose object for a while
(`git fsck --lost-found`), but do not count on it. No message, no trace, and the next
`git status` looks clean.

This kit exists because of failures like it, and it still happened during the kit's own
development: a `git reset --hard HEAD~1`, run to drop a throwaway test commit, also took a
set of uncommitted fixes and a review record the owner had written by hand. The second was
unrecoverable and had to be reconstructed from a chat transcript.

**Commit or stash first, every time**, including — especially — when you are sure the tree
is clean. `git stash push -u -m '...'` costs two seconds and is reversible.

The Claude Code overlay ships `guard_destructive_git.py`. It refuses `stash drop`/`clear`, a
force push, `remote set-url`/`add`, amending a pushed commit, a ref delete or forced move that
loses unmerged commits, `reflog expire`, an immediate prune and `worktree remove --force` of a
worktree that holds work whatever the tree's state, and `reset --hard`, `checkout --`/`-f`,
`restore`, `clean -f` and `rm -f` while the tree is dirty, printing what would be lost. It judges
Bash, PowerShell and Monitor calls alike. A hook refuses the loss-certain subset; the rule still covers every
destructive command, and in any other tool it is yours to keep.

**If it already happened.** Stop writing to the repository. Content you had staged, and a
dropped stash, may still be in the object database: `git fsck --lost-found` (staged blobs)
or `git fsck --unreachable` (dropped stash) lists them, and `git gc` removes them after about
two weeks. Edits you never staged are gone. (Sources: https://git-scm.com/docs/git-fsck,
https://git-scm.com/docs/git-stash.)

## `.gitignore` — the LAST matching rule wins

Git applies the last pattern that matches, so a broad rule written *after* a re-include
silently re-ignores the files you just rescued. This is easy to get backwards, because the
file reads top-to-bottom like a list of exceptions and behaves bottom-to-top.

Keep any re-include block at the very END of `.gitignore` and mark it as such. Never verify
by reading the file and reasoning about it: run `git check-ignore -v <path>`, which names
the winning rule and its line number. A pattern cannot re-include a file whose parent
directory is excluded; write `dir/*` instead of `dir/` when you need an exception inside it.
(Sources: https://git-scm.com/docs/gitignore, https://git-scm.com/docs/git-check-ignore.)

A trailing slash matters too: `node_modules/` matches directories only, and git does not
count a symlink as one. A `node_modules` symlinked into a throwaway worktree is then an
untracked, non-ignored file: `git status` lists it, and the gate's scan skips it with a
`NOTE [scan]` line (older gates failed on it as "a scanner failed to run"). Write
`node_modules` without the slash when the directory may ever be a symlink
(`scripts/doctor.sh` flags it).

## The executable bit has to be put in the git index by hand

On filesystems where `core.filemode` is `false` — Windows mounts, some network shares — git
never notices a `chmod`. The mode recorded in the index is whatever was written when the
file was first added, and files added from such a mount land as `100644`. The script runs
fine locally and CI dies on it with `Permission denied`, exit 126.

That exact failure kept a CI pipeline red for weeks in this kit's founding project, because
a local `CHECK: PASS` was mistaken for evidence about CI. Anyone adding a script runs
`git update-index --chmod=+x <path>`, confirms with `git ls-files -s`, and checks the
pipeline after pushing rather than assuming. For a new file `git add --chmod=+x <path>` does
it in one step. (Sources: https://git-scm.com/docs/git-update-index,
https://git-scm.com/docs/git-add.)

## A fake-CLI test harness cannot catch what the real CLI rejects

A wrapper script was fully proven against a stub binary that recorded its arguments — and
the first REAL run failed instantly, because the actual CLI accepts either a scope flag or
custom instructions, never both.

A stub validates YOUR argument handling. Only a live run validates the CONTRACT. Budget one
real invocation before declaring any CLI wrapper done, and say "not run" until you have
spent it. A cheap probe such as `--help` is a double too (a CLI's help need not list every
flag it takes); one real call is the contract test. (Sources: Fowler, "Contract Test",
https://martinfowler.com/bliki/ContractTest.html; https://code.claude.com/docs/en/cli-reference.)

## A tool's relative output path resolves against ITS working directory, not yours

A test runner was told to write results to a relative path. It resolved that path against
the project directory it had been handed rather than the calling shell's, so the file
landed somewhere nobody looked. The runner still exited 0, and a gate that checked only the
exit code reported PASS for a run that had executed nothing.

Pass absolute paths to any tool you will read output back from, and make the gate **fail
when the evidence is absent** — no results file is a FAIL, not a pass. An exit code is not
evidence that work was done. (`scripts/check.sh` carries this rule and a negative test for
it; failing closed is Saltzer and Schroeder's fail-safe default.) Unity's manual does not say
which directory a relative `-logFile` or results path is resolved against, so pass absolute
paths and treat a missing results file as FAIL
(https://docs.unity3d.com/Manual/EditorCommandLineArguments.html).

## Waiting on your own process: `pgrep -f` and shell wait loops match themselves

A wait loop such as `while pgrep -f "<pattern>"; do sleep 20; done` never ends when the
pattern also appears in the loop's own command line, because `pgrep -f` matches the shell
that runs the loop. It happened three times in one day in the founding project before the
rule was written. Match on the process name (`pgrep -x`), on a pid, or on a file the job
writes; never on text that is also in your command. The same holds for "wait until the
screen shows DONE" when the task text itself contains DONE. `pgrep` never reports itself, but
it does report the shell around it; `pgrep -A` also skips the loop's own ancestors
(https://man7.org/linux/man-pages/man1/pgrep.1.html).

Better still, do not wait at all: an agent that starts the job in the background is told
when it exits, and every waiting turn costs a full read of its context
(`docs/WORKFLOW.md`, "Worker cost").

## An agent puts the user's e-mail into a web request

Some APIs ask clients to put contact details in the `User-Agent` header, and an agent that
has the owner's e-mail address in its session context uses it. In one project five research
agents did, in up to thirteen requests each, before a rule was added to their briefs. The
address then sits in a third party's logs and cannot be recalled.

No personal data in any web request. Some APIs refuse a generic User-Agent outright
(Wikimedia answers 403; SEC EDGAR and OpenStreetMap's Nominatim want the application named):
for those, use the project contact in `docs/PROJECT.md` ("Web contact": a role address or
project URL the owner chose); if it is empty, ask the owner once and record the answer there.
Otherwise send the generic project User-Agent. Never the owner's own address. A brief that
sends an agent to the web repeats the rule and names that contact (`docs/WORKFLOW.md`, "Web
requests carry no personal data"). In the Claude Code overlay, `guard_private_email.py`
refuses a web request that carries the owner's address. (Sources:
https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy,
https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data,
https://operations.osmfoundation.org/policies/nominatim/.)

## A red gate that passes on re-run is a finding, not a pass

A gate that failed once and passed on a re-run with no change has found a race, not a fluke:
write the `[GOTCHA]` line and follow `docs/WORKFLOW.md`, "A red gate that passes on re-run".

## A checkout under `/mnt/<drive>` in WSL

A repository on a Windows drive seen from WSL gets CRLF line endings from git's autocrlf
(scripts then die with `\r: command not found` or a bad interpreter), installs
Windows-native binaries into `node_modules`, and runs its gate many times slower than on the
Linux filesystem. Clone into the WSL home instead. `scripts/doctor.sh` names the path and
flags a CR in a script. (Source for the speed and the advice: Microsoft,
https://learn.microsoft.com/en-us/windows/wsl/filesystems; the CRLF and binary effects are
this kit's own observation.)

## Under WSL, a file named `*.exe` runs on Windows

WSL hands a Windows executable to Windows; the match is on the file's first bytes ('MZ') in
the binfmt_misc registration, not the name - verify on the target WSL before relying on the
name alone (not verified here yet). In one run a test stub named like a Windows launcher
started on the Windows side, and Windows may show the owner a GUI error dialog in the middle
of a test run. A test or an experiment never executes a `*.exe` file. Name a stub for a
Windows launcher without `.exe`, and reach it through an overridable variable
(`docs/WORKFLOW.md`, "Writing a gate"). (Sources:
https://learn.microsoft.com/en-us/windows/wsl/filesystems,
https://docs.kernel.org/admin-guide/binfmt-misc.html.)

## A build server the gate started keeps the gate lock

`scripts/check.sh` runs one gate per checkout at a time, through a kernel lock that every
process the build command starts inherits. A build tool that leaves a server running after
the build holds that lock for the server's whole idle life, and the next gate waits for it;
the commit hook waits without a limit. Known ones: MSBuild node reuse and the VBCSCompiler
server after `dotnet build` or `dotnet test`, the Gradle daemon, the `sccache` server. Turn
the server off in the build command (`dotnet build -nodeReuse:false
-p:UseSharedCompilation=false`, `gradle --no-daemon`, `sccache --stop-server` at the end).
The gate's waiting `NOTE [lock]` line names the lock file; `fuser -v <lock file>` or
`lsof <lock file>` shows which process holds it. On native Windows, search for `check.lock`
under Associated Handles on the CPU tab of Resource Monitor (`resmon`). Gradle itself
recommends the daemon on CI; `--no-daemon` costs a JVM start per gate. The lock is inherited
on purpose so a running build keeps it after its holder dies; a server that outlives the
build is the price, which is why the list above is per tool. (Sources:
https://learn.microsoft.com/en-us/visualstudio/msbuild/msbuild-command-line-reference,
https://docs.gradle.org/current/userguide/gradle_daemon.html,
https://man7.org/linux/man-pages/man1/flock.1.html.)

## A worker spawned from a lead's shell inherits its child-session markers

A Claude Code session's shell carries `CLAUDE_CODE_CHILD_SESSION`, `CLAUDECODE` and a few
siblings. A `claude` started from that shell, such as a worker in a Windows Terminal tab (the
tab hands on the environment), takes itself for the lead's child and never registers as a peer:
`~/.claude/sessions/<pid>.json` is not written, ListAgents does not list it and SendMessage
cannot reach it. Under tmux the marker is ignored, so the same worker registered there. Clear
the markers (`unset CLAUDE_CODE_CHILD_SESSION CLAUDECODE ...`) in the command that starts the
worker; `spawn_worker.sh` does.

## Background jobs die with the session and in a low-memory reap

A job started from the lead's tool shell ends with the session on most hosts: a hand-off
in the middle of a batch killed three Codex jobs in one evening. Observed to survive on
native Windows (2026-10-12): a separate Windows Terminal tab and a `codex exec` run in it.
`&` under `sh -c` and `nohup` are unverified there (a Job Object may kill them;
`RESEARCH_LOG.md` 2026-10-10). Others report the same: Claude Code issues on background Bash
tasks cleaned up at session end (claudeissues.com 25188, 27959).
Candidate, untested: `claude --bg --exec '<command>'` runs the job under the
Claude Code supervisor instead of the lead's shell (https://code.claude.com/docs/en/agent-view);
its survival of a session end on native Windows is not documented - test before relying on it.
Before resuming work after a cut-off, list the processes whose command line names the checkout
or its worktrees. Quote the checkout path and match it literally:
Windows `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf('<checkout>', [StringComparison]::OrdinalIgnoreCase) -ge 0 } | Select ProcessId,CommandLine`;
Linux `ps -eo pid,args | grep -F -- '<checkout>'`; macOS `ps -eww -o pid,args | grep -iF -- '<checkout>'` (APFS ignores case).
The listing finds jobs whose arguments name the checkout (a `codex exec` with a brief path, a worker with its worktree). Ignore the listing's own rows: the `grep`, and the shell or PowerShell that runs the listing when an agent runs it through a tool (on Windows, the `powershell` process whose command line holds the query).
The command-line listing is only a shortcut for the jobs it can see. The project's gate holds
the lock at `git rev-parse --git-path check.lock`;
find the lock holder as described under "A build server the gate started keeps the gate lock" above.
A review holds no checkout lock; read its chain record as follows.
For reviews, read the highest-numbered `<chain>-N.json` in `.myagentkit/usage/chains/`; nothing in
the record names its process. `<chain>-0.json` always stays pending and is not evidence of a
running review. A review is finished only when that latest record has status `completed`, or
status `failed` and no `next_attempt`. A failed record with `next_attempt` is followed by that
attempt: a capacity retry after its `not_before` time, a quota switch to Claude (without
`--fallback`), or a fallback.
Use the mtime of `<chain>-0.json` as the review start time. The number of possible attempts is
one, plus up to two capacity retries of Codex (a wait of up to 20 minutes before each), plus one
quota switch or fallback. After a cut-off, treat the review as running for at least
`REVIEW_TIMEOUT_SECONDS` (2700 s when unset, 3600 for a high-effort Codex review and at most; the record does not store it) times
the number of possible attempts plus the capacity waits and overhead (about 4 h 40 min with 3600 s: four attempts and two 20-minute waits),
unless the latest record shows it is finished as above.
This window is a lower bound, not proof that an orphaned reviewer stopped.
After the window, the lead still confirms completion in the process listing.
On POSIX, the reviewer runs in its own session; a supervisor killed with `SIGKILL` cannot enforce its timeout.
Look for a `codex` or `claude` process whose arguments name the throwaway copy under the temp folder
(`myagentkit-codex-*` or `myagentkit-review-*`). Use the same listing commands with the copy path;
confirm its working directory if the arguments omit that path. On native Windows the working
directory is not visible through CIM: read `Get-Process -Id N | Select-Object Path` beside the
command line, and when the checkout cannot be confirmed treat the process as a survivor.
If a reviewer survives, wait for it or ask the owner before starting any heavy job.
Never start a heavy job beside a survivor, or edit or merge its worktree.
The kit's own check (`scripts/check.sh` → `scripts/check_kit.py`) holds no checkout lock.
It is visible only in the process listing:
look for a `python` process whose arguments name `check_kit.py` under the checkout.
If those arguments are relative, confirm the checkout through the process's working directory.
After a cut-off, look for this check before resuming heavy work; wait for any survivor or ask the owner.
A checkout path containing an apostrophe cannot go inside the single quotes as is; on Linux/macOS write it as `'\''` or put the path in a variable and match "$checkout";
on Windows double the apostrophe inside the PowerShell single-quoted string.
The Windows match ignores case because Windows paths do; search for every spelling the launching shell may have used: `C:/x`, `C:\x` and Git Bash's `/c/x` on Windows, the `pwd -P` form of a symlinked checkout on Linux and macOS, and `/private/var` for `/var` on macOS.
Wait for the survivors by default. Stop one only under the hard rule in `AGENTS.md` ("Never end
running work without a reason that holds": the owner asked, or it is provably finished or hung).
When the machine runs low on memory, the host can reap jobs: five heavy jobs started together
were killed at once, and their work was lost. Follow the memory budget and finish jobs before
ending their session (`docs/WORKFLOW.md`, "Worker cost", rules 6 and 8). A Codex or Claude
session that was cut off is resumed, not restarted (`docs/WORKFLOW.md`, "Worker cost").

## An incremental build misses its always-run inputs

An incremental-build planner in a downstream project skipped stages whose real inputs had
changed: steps that run every time read files no stage declared, and the driver script that
holds the stage commands was in no stage's dependency set (kit CHANGELOG v0.11, "An
incremental-build brief names both shared dependencies"). Include the inputs read by
always-run steps in every stage's dependency set, and make the driver script invalidate
every stage when it changes. A build tool has no reason to invalidate a cached result when
an undeclared input changes (Bazel, hermeticity: https://bazel.build/basics/hermeticity).


## A timing taken on a busy machine is not a result

A stray `find /` an agent had left running kept one CPU core busy for seven hours; a view that
gave about 950 FPS on a quiet machine gave 520-720 FPS under that load and a test job, and a
worker spent an attempt chasing a frame-rate regression that was machine load (#298). Before
any timing or benchmark run, record what else is running: the heaviest processes by CPU
(Windows `Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 Id,Name,CPU`, POSIX
`ps -A -o pid,pcpu,etime,args | sort -k2 -nr | head`), the CPU load, the GPU load where the
number depends on it (`nvidia-smi`, Task Manager), and the free memory. Start only on a quiet
machine: no gate, test suite, build or review running, and no process you cannot account for
using a noticeable share of a core (`scripts/doctor.sh` lists stray tool commands and how to end
them; ending one that is not yours is the owner's call). Write that record beside the number. A
number without it is not a result, and a slower number is a regression only once a quiet rerun
confirms it.

## PowerShell from the Microsoft Store leaves suspended processes behind

On one Windows host, 377 `pwsh.exe` processes piled up in two days (about 1.2 GB): each had
one thread in the Suspended state, most had no living parent, and every one ran the user's
Claude Code status line, a `pwsh` command set to refresh every 3 s (#304, 2026-10-22). That
`pwsh` was the Microsoft Store package, started through its app execution alias in
`%LOCALAPPDATA%\Microsoft\WindowsApps`. Diagnosis on that host, not a documented mechanism:
a run that is cancelled or abandoned while the packaged app is still being activated stays
suspended for good, and closing a session or a worker never reaches it. Claude Code's PowerShell
tool started the same Store `pwsh`; no stuck process from it was seen, but it can be cut off the
same way. Expected remedy, observed for minutes only (no new suspended process after the switch):
install PowerShell 7 from the MSI (`winget install --id Microsoft.PowerShell --source winget --installer-type wix`;
add `--force` when winget reports the Store package as already installed; it lands in
`C:\Program Files\PowerShell\7`), and name `"C:/Program Files/PowerShell/7/pwsh.exe"` by its
full path in every command Claude Code runs often (`statusLine`, hooks). The MSI adds its folder to
the machine PATH, which comes before the user PATH, so sessions started after the install pick it
for the PowerShell tool as well. A status line has no reason to refresh faster than every 10 s.
To count the stuck processes: `@(Get-Process pwsh | Where-Object { $_.Threads.Count -eq 1 -and
$_.Threads[0].ThreadState -eq 'Wait' -and $_.Threads[0].WaitReason -eq 'Suspended' }).Count`.
Ending them is the owner's call.

## A variable the session set does not reach the git hook

A lead set a venv's interpreter variable (`LEEWAY_PIPELINE_PYTHON`) in its session, and the
pre-commit gate ran another Python (project_leeway, 2026-10-22). A git hook inherits only the
environment of the `git` process that runs it, and an agent's shell call starts a fresh shell
each time, so an `export` or a venv activation in one call is gone by the commit; a terminal's
activation never reaches a commit started elsewhere either. Put the line in `.myagentkit/env`
(`KEY=VALUE`, Git-ignored): `check.sh` exports each key not already set before it resolves
anything (`docs/DEV_SETUP.md`, section 2).


## A PowerShell probe whose Set-Location fails goes on in the current folder

A worker tested a git hook from PowerShell with a throwaway commit: `Set-Location $T` into a
scratch folder, then `git add` and `git commit` (kit v0.13 masterhook, 2026-10-22). The folder did
not exist (the shell step that was to create it had been refused), `Set-Location` failed, and
PowerShell went on: a cmdlet's error does not stop the script by default. The commit landed in the worker's own
worktree, under the throwaway author, and the lead had to rebase it out. Make a throwaway step
stop on the first error (`$ErrorActionPreference = 'Stop'`, or `-ErrorAction Stop` on the
`Set-Location`), and before the commit check that `git rev-parse --show-toplevel` names the
throwaway folder.
