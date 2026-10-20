# Spike: Claude Code background sessions as the worker layer on POSIX (WSL Debian)

Date: 2026-10-20. Host: WSL2 Debian on Windows 11 (kernel 6.18.33.2-microsoft-standard-WSL2), Claude Code
**2.1.302** (`/usr/local/bin/claude`), tmux, zsh login shell. Brief: `.myagentkit/v012/bgspikeposix-brief.md`.
Companion of `docs/research/worker-orchestration-spike.md` (native Windows, 2.1.304; "the Windows spike" below)
and the contract in `.myagentkit/v012/bgshared.md`.

**Go/no-go for `--bg` as the POSIX default: GO**, with three contract changes found here (top of the next
section). Everything the Windows spike confirmed holds on POSIX; nothing POSIX-only blocks the design.

## Contract changes (bgspawn / bgmanage)

1. **Resume by the full `sessionId`, never by the short id.** `claude --resume 0a1e8225 --bg` (the printed
   short id, no flags) did not wake the session: it started a new session `5613d4c8` that sat in the "Resume
   session" picker with `No sessions match "0a1e8225"`, listed as `state: blocked` with no `waitingFor`. Only
   `claude --resume 0a1e8225-e6d6-4287-8bdc-6cd49b0903d3 --bg` woke `0a1e8225` itself (see 6). The CLI says so:
   "To continue a session under its own id, pass its full session id (lowercase, as `claude agents --json`
   prints it) to --resume." The kit must store the row's `sessionId` (e.g. `.myagentkit/workers/NAME.session`,
   or look it up by id in `claude agents --json --all` at resume time). `stop`, `rm`, `logs`, `attach` accept
   the short id (all used here).
2. **Launch-time environment variables do not reach the worker.** The session runs in a spare process the
   daemon pre-started, so its environment is the daemon's, not the launching shell's: a resume launched with
   `export BGSPIKE_ENV=s2` gave a worker (pid 4706, a `claude bg-spare` process) whose `/proc/4706/environ`
   had no `BGSPIKE_ENV`; a worker started from inside tmux had no `TMUX`. `spawn_worker.sh` today passes
   `MYAGENTKIT_ROLE=worker` (read by `plain_report.py` and `progress_reminder.py`) and
   `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h` through `env ...` (line 527): on the bg path both are lost.
   Carry them in the merged `--settings` file's `"env"` block instead (that block applies to the session and
   its hooks by the settings docs; **not verified in this spike**, the session budget was spent: the first
   bgspawn test should assert `MYAGENTKIT_ROLE=worker` inside a bg worker's hook). The daemon itself inherits
   the environment of whichever `claude --bg` call started it (its `environ` had the first launcher's `PWD`),
   so the `env -u CLAUDE_CODE_* ...` unmarking must stay on the launch command: if the lead's launch starts
   the daemon, the daemon (and every later spare) would otherwise carry the lead's session markers.
3. **Run resume from the worker's folder.** The trust check of `claude --resume ... --bg` uses the caller's
   cwd, not the session's: from `/tmp` it exited 1 with `Workspace not trusted. Run claude in /tmp once ...`.
   `cd WORKTREE && claude --resume SESSIONID --bg`.

Unchanged and confirmed: key on the id, never the name (here a copy got an auto title, `"name": "hello.txt
marker tools.txt"`, on Windows a copy took the same name: neither is reliable); never pass flags on resume;
never `claude daemon stop`; a result/question file wins over any state.

## Verdicts

| # | Check | Verdict |
|---|---|---|
| T1 | `--bg` in an untrusted folder exits | CONFIRMED (stderr, exit 1, no row) |
| T2 | trust inherited from a trusted parent: a nested clone inside the trusted repo root | REFUTED (same as Windows) |
| T3 / 1 | trusted repo root covers its lead-made worktree; the session stays in it with `bgIsolation: "none"` | CONFIRMED |
| 2a-e | `--append-system-prompt-file`, merged `--settings`, `--disallowedTools AskUserQuestion`, `--model`, `--effort` | CONFIRMED |
| 3 | no push with `bgIsolation: "none"` | CONFIRMED |
| 3b | without it, the session isolates, commits and pushes | CONFIRMED (push to the bare origin; no PR attempt) |
| 4 | `claude agents --json --all` fields and states | CONFIRMED (same fields and states as Windows) |
| 5 | `stop` / `rm` on a dirty, unpushed lead-made worktree | CONFIRMED: worktree, files, branch kept |
| 6 | resume with no flags | CONFIRMED with the **full sessionId** only; the short id starts a picker copy (new trap) |
| 6b | flags on resume start a copy | CONFIRMED (here: "already running, so this started a copy") |
| 7a | `claude logs` | CONFIRMED (raw screen dump, as on Windows) |
| 7b | `claude attach` with a TTY (tmux pane, `script -qc`) | CONFIRMED; Ctrl+Z / killing the client leaves the session running |
| 8a | session survives its tmux session being killed | CONFIRMED |
| 8b | session survives the WSL shell (`wsl.exe ... bash -lc`) ending | CONFIRMED |
| 8c | daemon is per user | CONFIRMED (socket dir `/tmp/cc-daemon-1000/`, state in `~/.claude/daemon/`) |
| 8d | hooks under a supervisor-started process: `CLAUDE_PROJECT_DIR`, `PATH`, `python3` | CONFIRMED (worktree, login PATH, `/usr/bin/python3`) |
| 8e | launch-time env vars reach the worker | REFUTED (contract change 2) |
| 9 | a native-Windows lead and WSL bg sessions see each other | REFUTED: two separate lists |

## Setup (throwaway; deleted at the end)

- Bare origin `~/bgspike_posix/origin.git`, repo `~/bgspike_posix/repo` cloned from it, root trusted by the
  owner. Before anything else a second clone `repo/fresh` was made from origin (T2 probe), and
  `.claude/settings.json` = `{"worktree": {"bgIsolation": "none"}}` was committed and pushed.
- Lead-made worktree: `git worktree add -q -b w1 .claude/worktrees/w1`.
- Inputs outside the repo (`~/bgspike_posix/inputs`): `behaviour.md` ("the first line of every file you
  create must be exactly `MARKER: append-file-honoured`"); `settings.json` (`worktree.bgIsolation: "none"`,
  allow Read/Write/Edit/`Bash(git:*)`/`Bash(ls:*)`/`Bash(cat:*)`, deny `Bash(gh:*)`; SessionStart, Stop and
  Notification hooks append time, event, `CLAUDE_PROJECT_DIR`, `PWD`, `command -v python3`, `PATH` and their
  JSON input to `hook.log`); `task1.txt` (write `hello.txt` and commit it, write `tools.txt` with
  AskUserQuestion YES/NO, model id, branch, `python3 --version`, `pwd`, write `RESULT-w1.md`). No push asked.
- A poller wrote every change of the `bgspike*` rows of `claude agents --json --all` (every 2 s) to
  `poll.log`. The kit's `guard_destructive_git.py` blocked two inline command lines on the Windows side
  (git in quotes), so the WSL commands ran from small script files.
- Sessions started: **four**, all Sonnet 5.5, effort low: `0a1e8225` (the worker), `5613d4c8` (the
  short-id resume copy), `df079bef` (the flags/running copy, used for the blocked state), `28f387e5` (3b).
  All stopped and removed (see Cleanup). The owner's three older WSL sessions (`5a4d0bf2`, `8b81e49e`,
  `e4733c27`) were listed but never touched.

## Observations

### T1. Untrusted folder — CONFIRMED

```
$ cd ~/bgspike_posix/untrusted && claude --bg -n bgspike-t1 --model claude-sonnet-5-5 --effort low "Reply OK and stop."
(stderr) Workspace not trusted. Run `claude` in /home/lil_pasa/bgspike_posix/untrusted once and accept the trust prompt, then retry.
exit=1
$ claude agents --json --all | grep -c bgspike
0
```

The message is on stderr. Called from Git Bash as `wsl.exe -d Debian -e bash -lc '... 2>&1'`, the inner
stderr line did not arrive at all (exit 1, empty output); it showed only when redirected to a file inside
WSL. A Windows-side script driving WSL must capture the launch's output inside WSL.

### T2. Nested clone inside the trusted root — REFUTED

```
$ cd ~/bgspike_posix/repo/fresh && claude "..." --bg -n bgspike-3b ...
Workspace not trusted. Run `claude` in /home/lil_pasa/bgspike_posix/repo/fresh once and accept the trust prompt, then retry.
exit=1
```

`~/.claude.json` has `/home/lil_pasa/bgspike_posix/repo: hasTrustDialogAccepted true`, and `repo/fresh` is a
folder below it. A path prefix does not carry trust; the worktree in T3 is covered because it belongs to the
trusted repository (its git common dir is the trusted root).

### T3 and 1. Lead-made worktree inside the trusted root; the session stays — CONFIRMED

Launched from inside a detached tmux session (`tmux new -d -s bgspike "bash s1.sh"`):

```
$ cd ~/bgspike_posix/repo/.claude/worktrees/w1
$ claude "$(cat task1.txt)" --bg -n bgspike-w1 --model claude-sonnet-5-5 --effort low \
    --settings ~/bgspike_posix/inputs/settings.json --append-system-prompt-file ~/bgspike_posix/inputs/behaviour.md \
    --disallowedTools AskUserQuestion
Starting background service…
backgrounded · 0a1e8225 · bgspike-w1
  claude agents             list sessions
  claude attach 0a1e8225    open in this terminal
  claude logs 0a1e8225      show recent output
  claude stop 0a1e8225      stop this session
exit=0
```

Same output format as Windows, so the contract's `backgrounded · ID` parse holds. Every row had
`"cwd": "/home/lil_pasa/bgspike_posix/repo/.claude/worktrees/w1"`; `tools.txt` line 3 (branch) = `w1`, line
5 (`pwd`) = the worktree; `git log` in w1: `12e05b8 (HEAD -> w1) w1: hello`; `git worktree list` showed only
`repo` and `w1`: no session-made worktree.

### 2. Flags — CONFIRMED

| Flag | Evidence |
|---|---|
| `--append-system-prompt-file` | `hello.txt`, `tools.txt`, `RESULT-w1.md` all start with `MARKER: append-file-honoured` |
| `--settings` (merged file) | `hook.log`: `SessionStart` (`"source":"startup"`), `Stop`, `Notification` lines from the file's hooks; the transcript's permission context lists the allow/deny rules with `"source":"flagSettings"` |
| `--disallowedTools AskUserQuestion` | request shape tools: `Agent, Artifact, Bash, Edit, EnterWorktree, ListAgents, Read, ReportFindings, ScheduleWakeup, Skill, ToolSearch, Workflow, DeferredToolPlaceholder, Write, advisor` (no AskUserQuestion); permission context `"deny":[{"rule":"AskUserQuestion","source":"cliArg"}, ...]`; `tools.txt`: `NO` |
| `--model claude-sonnet-5-5` | transcript: 7 of 7 assistant entries `model=claude-sonnet-5-5`; `tools.txt` line 2; status bar `Sonnet 5.5 · low` |
| `--effort low` | transcript: 7 of 7 `effort=low`; `Sonnet 5.5 with low effort` in the logs header |
| `-n NAME` | `"name": "bgspike-w1"` |

As on Windows, the owner's user settings carry into the session: `"permissionMode": "auto"` (5 entries;
`⏵⏵ auto mode on` in the logs), so `python3 --version` and `pwd`, outside the allow list, ran unprompted.

Side finding (raised by the owner during the spike): the worker's commit carried
`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`, which the task never asked for. The throwaway
repo had no `attribution` setting, so Claude Code's default applied. A kit project is covered twice: the
overlay's `.claude/settings.json` ships `"attribution": {"commit": "", "pr": ""}` (a project setting, which a
bg session reads from its folder: check 3b shows project settings decide the session's behaviour), and the
kit's `.githooks/commit-msg` rejects an AI `Co-Authored-By` trailer. Suggestion for bgspawn: also put
`"attribution": {"commit": "", "pr": ""}` in the merged `--settings` file, so a worker in a project whose
overlay is missing or edited still makes no credited commit; the hook stays the hard stop.

### 3. No push with `bgIsolation: "none"` — CONFIRMED

```
$ git --git-dir=$HOME/bgspike_posix/origin.git log --all --oneline --decorate     (after the run)
295af85 (HEAD -> master) bgIsolation none
fe99a3f init
```

`12e05b8` stayed local on `w1`; the transcript's Bash calls are `git branch --show-current; python3 --version;
pwd` and `git add hello.txt && git commit ...` only, no push, no `gh`.

### 3b. Without the setting the session isolates, commits and pushes — CONFIRMED (new)

The repo root (trusted) with `.claude/settings.json` moved aside for the launch only, restored 2 s later
(`git status` clean afterwards); `--settings` was the same file without the `worktree` key:

```
$ cd ~/bgspike_posix/repo && claude "Create note.txt containing the single line: hi from 3b. Then finish your task as you normally would." \
    --bg -n bgspike-3b --model claude-sonnet-5-5 --effort low --settings settings-3b.json --disallowedTools AskUserQuestion
backgrounded · 28f387e5 · bgspike-3b
```

About 60 s later:

```
row:  {"id": "28f387e5", "cwd": "/home/lil_pasa/bgspike_posix/repo/.claude/worktrees/note-3b", "state": "done", "status": "idle", ...}
$ git worktree list
/home/lil_pasa/bgspike_posix/repo                            295af85 [master]
/home/lil_pasa/bgspike_posix/repo/.claude/worktrees/note-3b  345d4f0 [worktree-note-3b] locked
/home/lil_pasa/bgspike_posix/repo/.claude/worktrees/w1       12e05b8 [w1]
$ git --git-dir=$HOME/bgspike_posix/origin.git log --all --oneline --decorate
345d4f0 (worktree-note-3b) Add note.txt
295af85 (HEAD -> master) bgIsolation none
fe99a3f init
tool calls: EnterWorktree; Bash "echo ... > note.txt && git add note.txt && git commit ... && git remote -v && git log --oneline -1";
            Bash "git push -u origin worktree-note-3b 2>&1 | tail -3"
```

The documented default (isolate, commit, push) is real: a kit project without `bgIsolation: "none"` would
have its worker push a branch. No PR was attempted (no `gh` call; the origin is a local bare repo, not
GitHub), so the draft-PR half stays documentation only. This is the case for keeping `"none"` in **both**
the overlay's project settings and the merged `--settings`, as the contract says.

### 4. `claude agents --json --all` — CONFIRMED

From `poll.log` (row of `0a1e8225`):

```
21:16:27 ABSENT
21:16:31 {"cwd": ".../w1", "id": "0a1e8225", "kind": "background", "name": "bgspike-w1", "sessionId": "0a1e8225-e6d6-...", "startedAt": 1792520190321, "state": "working"}
21:16:38 {... "pid": 393, "startedAt": 1792520194789, "state": "working", "status": "busy"}
21:17:01 RESULT-w1.md on disk (row unchanged)
21:17:08 {... "pid": 393, "state": "done", "status": "idle"}
```

The copy `df079bef`, given a command outside the allow list with `--permission-mode default`:

```
{"pid": 4706, "id": "df079bef", "cwd": ".../w1", "kind": "background", "name": "hello.txt marker tools.txt",
 "status": "waiting", "waitingFor": "permission prompt", "state": "blocked"}
$ claude stop df079bef        -> stopped df079bef
{"id": "df079bef", ..., "state": "stopped"}          (no pid, no status)
```

Same field set and states as Windows: `pid` and `status` only while the process lives, `waitingFor` only
while waiting, `startedAt` changes once in the first seconds, `done` 7 s after the result file. New: the
short-id copy (6) showed `state: blocked` with **no** `status` and no `waitingFor` (a picker on screen). The
watcher's reason line must cope with an absent `waitingFor` (e.g. "blocked, no reason given").

The Notification hook fired once for `0a1e8225`: `"notification_type":"idle_prompt"` at 21:18:05, 60 s after
the Stop hook (21:17:05), the same fixed delay as Windows.

### 5. `stop` / `rm` on a dirty, unpushed lead-made worktree — CONFIRMED (kept)

```
$ echo "spike edit" >> README.md; git status --short          (in w1; 12e05b8 not on origin)
 M README.md
?? RESULT-w1.md
?? tools.txt
$ claude stop 0a1e8225   -> stopped 0a1e8225
$ claude rm 0a1e8225     -> removed 0a1e8225, exit=0
$ ls; git status --short; git log --oneline -1
hello.txt README.md RESULT-w1.md tools.txt
 M README.md
?? RESULT-w1.md
?? tools.txt
12e05b8 w1: hello
```

For contrast, the session-made worktree of 3b (pushed):

```
$ claude stop 28f387e5
stopped 28f387e5
  worktree retained at /home/lil_pasa/bgspike_posix/repo/.claude/worktrees/note-3b
  run 'claude rm 28f387e5' to remove worktree and job state
$ claude rm 28f387e5 </dev/null
removed 28f387e5
  worktree: "/home/lil_pasa/bgspike_posix/repo/.claude/worktrees/note-3b"
```

`rm` deleted the session-made worktree and its local branch `worktree-note-3b` (no prompt: it was pushed);
the lead-made `w1` stayed. The kit's split holds: `claude rm` on a kit worker never removes its worktree.

### 6. Resume — CONFIRMED with the full sessionId; new short-id trap

After `claude stop 0a1e8225` (state `done`, pid gone; the daemon then idle-exited, see 8):

```
$ cd /tmp && claude --resume 0a1e8225 --bg
Workspace not trusted. Run `claude` in /tmp once and accept the trust prompt, then retry.      exit=1
$ cd .../worktrees/w1 && claude --resume 0a1e8225 --bg
Starting background service…
note: started a copy of that conversation as 5613d4c8. To continue a session under its own id, pass its full session id (lowercase, as `claude agents --json` prints it) to --resume.
backgrounded · 5613d4c8 (idle — send a prompt to start)
row: {"pid": 4377, "id": "5613d4c8", "name": "5613d4c8", "state": "blocked", ...}
claude logs 5613d4c8 (last screen): Resume session ⌕0a1e8225  No sessions match "0a1e8225".
$ claude --resume 0a1e8225-e6d6-4287-8bdc-6cd49b0903d3 --bg
note: woke session 0a1e8225 with its saved options (-n, --effort, --settings, --append-system-prompt-file, --disallowedTools, --model).
backgrounded · 0a1e8225 · bgspike-w1 (idle — send a prompt to start)
row: {"pid": 4376, "id": "0a1e8225", "state": "done", "status": "idle", ...}
```

`hook.log` got a `SessionStart` with `"source":"resume"`. Flags on resume (with the session now running):

```
$ export BGSPIKE_ENV=s2
$ claude "Run this exact command ... python3 -c ..." --resume 0a1e8225-e6d6-4287-8bdc-6cd49b0903d3 --bg --permission-mode default
note: session 0a1e8225 is already running in the background, so this started a copy as df079bef. `claude attach 0a1e8225` opens the original.
backgrounded · df079bef
```

The copy kept Sonnet 5.5 low (transcript: 7 of 7) and took an auto title as its name, not the original's
name (Windows: same name). The Windows trap (flags on a stopped session start a copy) was not re-run; the
running-session variant above shows the same outcome: any resume other than "full sessionId, no flags, from
the worker's folder" yields a new session id.

### 7. `claude logs` and `claude attach` — CONFIRMED

```
$ claude logs 0a1e8225          -> 50,564 bytes, exit 0; raw screen redraws (ANSI, spinner frames, status bar)
$ claude logs bgspike-nosuch    -> No job matching 'bgspike-nosuch'. Run 'claude agents' to list running sessions.  exit=1
$ tmux new -d -s bgattach -x 160 -y 45 "claude attach 0a1e8225"; sleep 6; tmux capture-pane -p -t bgattach
  ... ✻ Baked for 30s · done 9:17 PM
  ──────── bgspike-w1 ─
  ❯
  Sonnet 5.5 · low │ w1 │ w1*
  ⏵⏵ auto mode on (shift+tab to cycle) · ← 2 agents
$ tmux send-keys -t bgattach C-z     -> the pane closed (attach exited); session 0a1e8225 still pid 393, state done/idle
$ script -qc "timeout 8 claude attach 0a1e8225" /dev/null   -> 10,547 bytes of the session screen ("Baked for 30s · done"), session still alive
```

`claude attach --help`: "← returns to agent view, Ctrl+Z drops back to your shell. The session keeps running
either way." With a TTY (a tmux pane, or `script`) attach works on POSIX; from a pipe it is useless, as on
Windows. For the owner, `claude attach ID` in any terminal or tmux pane is the per-worker view; the tmux
fallback's `tmux attach -t NAME` is no longer needed on the bg path.

### 8. Survival, daemon, process tree, hooks — CONFIRMED

Process tree right after the launch from tmux (`ps -eo pid,ppid,pgid,sid,tty,cmd`):

```
  310  205  310  310 ?  tmux new -d -s bgspike bash .../s1.sh
  350  205  350  350 ?  claude.exe daemon run --origin transient --spawned-by {"label":"claude --bg","cwd":".../w1","pid":317}
  376  350  376  376 ?  claude bg-pty-host --bg-pty-host /tmp/cc-daemon-1000/07dee75a/spare/b70a9359.pty.sock 200 50 -- claude.exe --bg-spare ...
  377  350  377  377 ?  claude bg-pty-host --bg-pty-host /tmp/cc-daemon-1000/07dee75a/pty/0a1e8225.sock 200 50 -- claude.exe --session-id 0a1e8225-... <prompt> <flags>
  392  376  376  376 ?  claude bg-spare --bg-spare .../spare/b70a9359.claim.sock
  393  377  377  377 ?  claude.exe --session-id 0a1e8225-... (the worker)
  205    1               /init
```

- The daemon is reparented to WSL's per-instance `/init` (pid 205) and runs in its own session (`sid` =
  pid); each worker sits under its own `bg-pty-host`, again its own session, with no controlling terminal.
  Nothing is in the tmux or launching shell's process group, so SIGHUP from a closing terminal does not
  reach it.
- `tmux kill-session -t bgspike` (no tmux server left): pids 350, 377, 393 alive (`Ssl`, `SNsl`, `SNsl+`),
  the worker went on to write its result. The `wsl.exe -d Debian -e bash -lc ...` call that started the
  daemon ended long before the worker finished: survived too. Not tested: an SSH logout, `wsl --shutdown` /
  `wsl --terminate` (it would end the owner's sessions as well, so it was not run) and a reboot.
- Daemon per user: control socket `/tmp/cc-daemon-1000/07dee75a/control.sock` (uid 1000 in the path, folder
  mode `drwx------`), roster `~/.claude/daemon/roster.json`, log `~/.claude/daemon.log`. Service install is
  disabled in 2.1.302 too: `claude daemon status` printed `not running` before the spike; the first `--bg`
  printed `Starting background service…`. The daemon log shows its lifetime is "while a worker lives":
  `bg settled 0a1e8225 (killed)` at 18:18:52, then `idle 5s with no clients — exiting` at 18:18:57; the next
  `--resume ... --bg` started a new daemon (`origin=transient`). No "about a minute" window was seen: with
  no live worker the daemon goes after 5 s, with one it stays. A stopped worker is resumable either way (6
  ran against a fresh daemon).
- The daemon keeps a warm spare (`bg spare spawned host pid=...`) and hands it to the next launch
  (`bg claimed-spare df079bef`, `... 28f387e5`): this is why launch-time env vars do not reach the worker
  (contract change 2). `/proc/4376/environ` (the woken `0a1e8225`) had `CLAUDE_CODE_SESSION_KIND=bg`,
  `CLAUDE_BG_BACKEND=daemon`, `PWD` = the first launcher's folder, and no `TMUX`.
- Hooks (8d), from `hook.log`, SessionStart and Stop alike: `CLAUDE_PROJECT_DIR=/home/lil_pasa/bgspike_posix/repo/.claude/worktrees/w1`,
  `PWD` = the same, `command -v python3` = `/usr/bin/python3`, `PATH` = the owner's login-shell PATH
  (`~/.atuin/bin:~/.local/bin:...:/usr/bin:...` plus the Windows interop entries `/mnt/c/...`). The kit's
  `py.sh` finds `python3` and the hooks resolve against the worktree, as in a tmux worker. The kit's own
  POSIX hooks were not loaded (the throwaway repo has no overlay).
- Signals: `claude stop` ended the worker (`bg settled ... (killed)`), the pty host and the spare chain; no
  orphan `claude.exe` was left (`ps -eo cmd | grep -c claude.exe` = 0 after the last stop).

### 9. Native-Windows lead and WSL sessions — separate (REFUTED that they see each other)

`claude agents --json --all` in WSL listed the owner's WSL sessions `5a4d0bf2`, `8b81e49e`, `e4733c27`; the
same command on native Windows listed 12 rows, none of those three ids (`grep -cE` = 0). Two installs, two
daemons, two lists. A native-Windows lead can drive WSL workers only by shelling every command through
`wsl.exe -d DISTRO -e bash -lc '...'`, and their rows never show in the Windows `claude agents`. For the kit
this means: on a Windows host the bg path is the native Windows one (the Windows spike); WSL is a POSIX
host of its own, with its own lead.

## Differences from Windows

| Point | Windows (2.1.304) | POSIX / WSL (2.1.302) |
|---|---|---|
| Resume target | full sessionId used; short id not tried | short id starts a picker copy; full sessionId required |
| Copy's name | same name as the original | auto title (or its own id) |
| Copy reason seen | flags on a stopped session | short id; flags on a running session |
| Untrusted-launch message | printed in the Git Bash call (stream not recorded) | stderr; lost through `wsl.exe ... 2>&1` from Git Bash |
| Daemon lifetime | not observed | exits 5 s after the last live worker; restarts on the next `--bg` |
| Env of the worker | not checked | the daemon's (spare process), not the launcher's |
| `attach` | UNCLEAR (no TTY) | works with a TTY (tmux pane, `script -qc`) |
| Session-made worktree on `rm` | not observed | deleted with its branch (pushed); lead-made kept |

## Cleanup (proof)

```
$ claude agents --json --all | grep -cE "0a1e8225|5613d4c8|df079bef|28f387e5"
0
$ claude agents --json --all     (ids, states, names)
5a4d0bf2 blocked CHANGE_ORDER.md devamı E1 ve G2-G8 maddeleri
8b81e49e done consent-v2-age-ai-mark implementation
e4733c27 blocked Project Leeway geliştirme koordinasyonu        (the owner's, unchanged)
$ ps -eo pid,cmd | grep -c "[c]laude.exe"
0
$ claude daemon status   -> not running (it idle-exited on its own; `claude daemon stop` was never called)
$ rm -rf ~/bgspike_posix; ls -d ~/bgspike_posix
ls: cannot access '/home/lil_pasa/bgspike_posix': No such file or directory
```

Left behind: the four sessions' transcripts under `~/.claude/projects/-home-lil-pasa-bgspike-posix-repo*`
and the owner's trust entry for the deleted repo in `~/.claude.json` (both inert; the spike does not edit the
owner's Claude config).

## Limits

- One worker run, one 3b run, two copies; `failed`, a question-driven wait, an SSH logout, `wsl --shutdown`,
  a reboot and the one-hour idle retire were not observed.
- The `--settings` `"env"` route of contract change 2 is unverified (no session left in the budget).
- macOS (launchd, a real login session) was not tested; WSL2 has systemd running but the daemon did not use
  it (`origin=transient`).
- Version skew: POSIX 2.1.302 against Windows 2.1.304; the short-id behaviour may differ by version, so the
  kit should resume by full sessionId on both.
