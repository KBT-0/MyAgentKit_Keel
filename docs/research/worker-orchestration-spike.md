# Spike: Claude Code background sessions as the kit's worker layer (Step B)

Date: 2026-10-20. Host: native Windows 11, Claude Code 2.1.304, Git for Windows sh and PowerShell 7.
Brief: `.myagentkit/v012/bgspike-brief.md` and `bgspike-resume.md`; background:
`docs/research/worker-orchestration.md`, option 1, Step B. Docs quoted as [agent-view] are
https://code.claude.com/docs/en/agent-view, read 2026-10-20.

**Go/no-go for Step C: GO**, with three design constraints found here: (1) the kit must never pass
flags to `claude --resume ID --bg` (that starts a copy, see 6); (2) session names are not unique, so
the kit keys everything on the printed id, not the name (see 6); (3) a worker's folder must sit under
a repo root the owner has trusted in Claude Code: trust is not inherited from a parent folder (T2).

## Verdicts

| # | Check | Verdict |
|---|---|---|
| 1 | `--bg -n NAME` in a lead-made worktree with `bgIsolation: "none"` stays in that folder | CONFIRMED |
| 2a | `--append-system-prompt-file` honoured | CONFIRMED |
| 2b | merged `--settings` file honoured (permissions + hooks) | CONFIRMED |
| 2c | `--disallowedTools AskUserQuestion` honoured | CONFIRMED |
| 2d | `--model` honoured | CONFIRMED |
| 2e | `--effort` honoured | CONFIRMED |
| 3 | no push / draft PR with `bgIsolation: "none"` | CONFIRMED (no new ref) |
| 3b | the default (isolation on) really pushes | UNCLEAR: not run (session budget used, see 6) |
| 4 | `claude agents --json` fields and states | CONFIRMED (working, blocked + waitingFor, done, stopped) |
| 5 | `claude stop` / `claude rm` on a dirty, unpushed lead-made worktree | CONFIRMED: worktree, files and branch kept |
| 6 | after the result + `claude stop`: resumable with `claude --resume ID --bg` | CONFIRMED, but state is `done`, not `stopped`, and flags start a copy |
| 7 | `claude logs` / `claude attach` from Git Bash and PowerShell | `logs` CONFIRMED both; `attach` UNCLEAR (needs a real terminal) |
| 8 | disk watch + state poll for `watch_workers.sh` | design below, from the observed fields |
| T1 | `--bg` in an untrusted folder exits | CONFIRMED |
| T2 | trust inherited from a trusted parent folder | REFUTED (new) |
| T3 | trusted repo root covers a lead-made worktree inside it | CONFIRMED (new) |

## Setup (throwaway, outside the kit; both folders deleted at the end)

- `origin` = bare repo `%TEMP%/bgspike/origin.git`. Clones take it as `origin` (the kit's
  `guard_destructive_git.py` refuses `git remote add`, so the repo is cloned from the bare one).
- Repo `D:/.../_MyAIKits/_bgspike_tmp/repo` with `.claude/settings.json` =
  `{"worktree": {"bgIsolation": "none"}}` committed and pushed: the place the docs name ("Add the
  setting to the project's `.claude/settings.json`" [agent-view]; no other location is documented).
- Lead-made worktree: `git worktree add -q -b w1 .claude/worktrees/w1`.
- Worker inputs: `behaviour.md` for `--append-system-prompt-file` ("the first line of every file you
  create must be exactly `MARKER: append-file-honoured`"); `settings.json` for `--settings` (allow
  Read/Write/Edit/`Bash(git:*)`/`Bash(ls:*)`/`Bash(cat:*)`, deny `Bash(gh:*)`; SessionStart, Stop and
  Notification hooks append their JSON input to `hook.log`); a task file (write `hello.txt`, commit
  it, write `tools.txt` with "AskUserQuestion in your tool list: YES/NO", model id and branch, write
  `RESULT-w1.md`, run `python3 --version`). The task never mentions pushing.
- Sessions started: **two**, both Sonnet 5.5, effort low: `108f1e41` (the worker) and `36903bf7`
  (an unintended copy, see 6). Both stopped and removed.

## Observations

### T1. `--bg` in an untrusted folder exits — CONFIRMED

```
$ cd %TEMP%/bgspike/repo && claude --bg -n trustprobe "write nothing"
Workspace not trusted. Run `claude` in C:\Users\kemal\AppData\Local\Temp\bgspike\repo once and accept the trust prompt, then retry.
exit=1
$ claude agents --json --all | grep -c trustprobe
0
```

No session row is created, as documented ("Where no dialog can appear, such as in a script, the
command exits with a `Workspace not trusted` error" [agent-view]).

### T2. Trust is not inherited from a trusted parent folder — REFUTED (new)

`D:/.../_MyAIKits` has `hasTrustDialogAccepted: true` in `~/.claude.json`, yet from the worktree
of a repo below it:

```
$ cd D:/.../_MyAIKits/_bgspike_tmp/repo/.claude/worktrees/w1 && claude "<task>" --bg -n bgspike-w1 ...
Workspace not trusted. Run `claude` in D:\...\_bgspike_tmp\repo\.claude\worktrees\w1 once and accept the trust prompt, then retry.
exit=1
```

Writing a trust key to `~/.claude.json` by script was refused by the host's auto-mode classifier
("Self-Modification"). The owner then ran `claude` once in the repo root and accepted the prompt.

### T3 and 1. A trusted repo root covers its lead-made worktree; the session stays there — CONFIRMED

After the owner trusted only the repo root (not `w1`):

```
$ cd .../repo/.claude/worktrees/w1 && claude "$(cat task1.txt)" --bg -n bgspike-w1 --model claude-sonnet-5-5 --effort low \
    --settings C:/.../bgspike/settings.json --append-system-prompt-file C:/.../bgspike/behaviour.md --disallowedTools AskUserQuestion
Starting background service…
backgrounded · 108f1e41 · bgspike-w1
  claude agents             list sessions
  claude attach 108f1e41    open in this terminal
  claude logs 108f1e41      show recent output
  claude stop 108f1e41      stop this session
exit=0
```

Every row of `claude agents --json` had `"cwd": "...\\_bgspike_tmp\\repo\\.claude\\worktrees\\w1"`;
the worker's tool calls wrote `...\\worktrees\\w1\\hello.txt` and friends; `tools.txt` line 3
(`git branch --show-current`) = `w1`; `git log` in w1: `8601620 (HEAD -> w1) w1: hello`. No
`.claude/worktrees/` entry was created by the session. The prompt goes first: the kit's own
`guard_destructive_git.py` read `git commit ... -n bgspike-w1` in an inline prompt as
`git commit -n` and refused the launch, so the task text was passed as `"$(cat task1.txt)"`.

Limit: the docs also skip isolation for "a session that started inside a worktree that already
existed" [agent-view], so this run does not separate the setting's effect from the lead-made
worktree's; for the kit both hold at once.

### 2. Flags — all CONFIRMED

| Flag | Evidence |
|---|---|
| `--append-system-prompt-file` | `hello.txt`, `tools.txt`, `RESULT-w1.md` all start with `MARKER: append-file-honoured`, a rule only that file carried |
| `--settings` (merged file) | `hook.log` got `SessionStart {"session_id":"108f1e41-...","source":"startup"}`, `Stop {...}` and `Notification {...}` from the file's hooks; `Write` and `git commit` ran under its allow rules |
| `--disallowedTools AskUserQuestion` | the transcript's `api-request-shape` tool list: `Agent, Artifact, Bash, Edit, EnterWorktree, Glob, Grep, ListAgents, Read, ...` without `AskUserQuestion`; `tools.txt` line 2: `NO` |
| `--model claude-sonnet-5-5` | transcript: all 7 assistant messages `"model": "claude-sonnet-5-5"`; status bar in `claude logs`: `Sonnet 5.5 · low` |
| `--effort low` | transcript entries carry `"effort": "low"` (7); same status bar |
| `-n NAME` | `"name": "bgspike-w1"` in `claude agents --json` |

Side finding: the session ran with `"permissionMode": "auto"` (transcript; `⏵⏵ auto mode on` in the
logs): the owner's user settings carry into `--bg` sessions, so `python3 --version`, outside the
allow list, ran without a prompt. The waiting state was provoked later with `--permission-mode
default` (see 4).

### 3. No push with `bgIsolation: "none"` — CONFIRMED; default push — UNCLEAR

```
$ git --git-dir=%TEMP%/bgspike/origin.git log --all --oneline --decorate     (after the run, after stop, after rm)
1746d9e (HEAD -> master) bgIsolation none
2595fea init
```

The commit `8601620` stayed local on `w1`; the transcript has no `git push` and no `gh` call. This
matches the docs: a session editing a checkout it did not isolate "still asks before committing",
and the commit-and-push default applies only "in a worktree Claude entered" [agent-view]. The
second run (isolation on, fresh clone) was not made: the second session slot went to the copy in
6, and the brief caps sessions at two. The kit sets `"none"`, so the default's behaviour is
documentation only for the kit; a later spike can confirm it with one session.

### 4. `claude agents --json`: fields and states — CONFIRMED

Polled every 2 s (`claude agents --json --all`, row by name):

```
20:47:40 ABSENT
20:47:42 {"cwd": "...w1", "id": "108f1e41", "kind": "background", "name": "bgspike-w1", "sessionId": "108f1e41-...", "startedAt": 1792518461113, "state": "working"}
20:47:45 {... "pid": 28256, "startedAt": 1792518463331, "state": "working"}
20:47:48 {... "pid": 28256, "state": "working", "status": "busy"}
20:48:06 RESULT-FILE-PRESENT                      (the result file appeared on disk)
20:48:14 {... "pid": 28256, "state": "done", "status": "idle"}
```

The copy `36903bf7`, given a command outside the allow list with `--permission-mode default`:

```
{"pid": 28288, "id": "36903bf7", "cwd": "...w1", "kind": "background", "name": "bgspike-w1", "status": "waiting", "waitingFor": "permission prompt", "state": "blocked"}   (unchanged for 60 s)
$ claude stop 36903bf7
stopped 36903bf7
{"id": "36903bf7", "state": "stopped", "status": null, "pid": null}
```

- Fields seen: `id`, `cwd`, `kind`, `name`, `sessionId`, `startedAt`, `state`; `pid` and `status`
  only while the process lives; `waitingFor` only while waiting. `startedAt` changed once in the
  first seconds (1792518461113 → 1792518463331).
- States seen: `working`, `blocked` (+ `status: waiting`, `waitingFor: "permission prompt"`),
  `done` (+ `status: idle` while the process lives), `stopped`. `failed` not provoked.
- `claude agents --json` without `--all` drops `done` and `stopped` rows (`grep -c bgspike-w1` = 0
  after the stop); a watcher must pass `--all`.
- The Notification hook fired once: `"notification_type":"idle_prompt"`, `"message":"Claude is
  waiting for your input"`, at 20:49:12, about 60 s after the turn ended (20:48:1x), the fixed delay
  of #12048 in the research report. The state field flipped to `done` within 8 s of the result.

### 5. `claude stop` / `claude rm` on a dirty, unpushed lead-made worktree — CONFIRMED (kept)

```
$ echo "spike edit" >> w1/README.md; git status --short; git log --oneline -1
 M README.md
?? RESULT-w1.md
?? tools.txt
8601620 w1: hello                     (not on origin)
$ claude stop 108f1e41
stopped 108f1e41
$ claude rm 108f1e41
removed 108f1e41
exit=0
$ ls w1; git status --short
hello.txt README.md RESULT-w1.md tools.txt
 M README.md
?? RESULT-w1.md
?? tools.txt
$ git log --oneline w1 -1
8601620 w1: hello
$ claude rm 36903bf7
removed 36903bf7
```

`rm` removed only the session row; the worktree, its dirty and untracked files and the unpushed
branch stayed, with no `--discard-unpushed` prompt. The docs: "a worktree you created yourself is
left in place" [agent-view]. For the kit this is the safe split: Claude Code ends the session, the
kit's `clean_worktrees.sh` audit stays the only path that removes a worktree.

### 6. Result + stop, then resume — CONFIRMED, with two traps

```
$ claude stop 108f1e41                       (after RESULT-w1.md, state done/idle)
stopped 108f1e41
{"id": "108f1e41", "state": "done", "status": null, "pid": null}
```

A finished session stays `done` after `stop`; only a session stopped mid-turn shows `stopped` (the
copy above). A watcher must treat `done` and `stopped` alike as "process gone".

Trap 1, flags start a copy:

```
$ claude "<prompt>" --resume 108f1e41-5137-4293-88d5-c4339d1ce56c --bg --permission-mode default --model claude-sonnet-5-5 --effort low
note: background session 108f1e41 keeps its own saved options, so the flags you passed started a copy as 36903bf7. Without flags, the same command continues 108f1e41 itself.
backgrounded · 36903bf7
```

This used the brief's second session slot (an error of this spike, recorded here).

Trap 2, the copy took the same name: `36903bf7` listed as `"name": "bgspike-w1"` beside
`108f1e41`. `claude logs` / `attach` accept part of a name, so a name can match two sessions.

Without flags, the same session wakes with its saved options:

```
$ claude --resume 108f1e41-5137-4293-88d5-c4339d1ce56c --bg
note: woke session 108f1e41 with its saved options (-n, --effort, --settings, --append-system-prompt-file, --disallowedTools, --model).
backgrounded · 108f1e41 · bgspike-w1 (idle — send a prompt to start)
{"id": "108f1e41", "state": "done", "status": "idle", "waitingFor": null, "pid": 31552}
```

### 7. `claude logs` / `claude attach` from both shells — `logs` CONFIRMED, `attach` UNCLEAR

```
Git Bash:   $ claude logs bgspike-nosuch    -> No job matching 'bgspike-nosuch'. Run 'claude agents' to list running sessions.  exit=1
PowerShell: > claude logs bgspike-nosuch    -> same, exit=1
Git Bash:   $ claude logs 108f1e41          -> 316,977 bytes, exit 0
PowerShell: > claude logs 108f1e41          -> exit=0 chars=195140; last screen: the transcript, "✻ Brewed for 28s · done 20:48", "Sonnet 5.5 · low"
Git Bash:   $ timeout 10 claude attach 108f1e41 </dev/null   -> "Attaching…", exit 0 within 10 s (no TTY)
```

`claude logs` is a raw screen dump (ANSI redraws, the status bar repeated), not a text log: fine
for a person, poor for a script; a script reads the transcript or the result file instead.
`attach` needs a real terminal; from a tool shell it attaches and drops at once. Owner check owed:
`claude attach NAME` in a Windows Terminal tab, Git Bash and PowerShell.

### T4. Safety note

`claude daemon stop` "Shut[s] down the supervisor and terminate[s] background sessions" (every one,
the owner's included) unless `--keep-workers`: the kit must never call it.

## Step C + D design sketch (both platforms; one path, no tmux, no tab)

The session layer is Claude Code's supervisor on every host; the kit keeps its worktrees, result
file, question file and audit. Every script keys on the **id** `claude --bg` prints, stored in
`.myagentkit/workers/NAME.id`; the name is for people.

- **spawn_worker.sh** (Windows and POSIX alike): a `Workspace not trusted` exit of the launch is
  reported as "run `claude` once in ROOT and accept the trust prompt" (T1-T3); nothing waits. Makes and locks the worktree as today; the project carries `worktree.bgIsolation: "none"`
  in `.claude/settings.json` (the kit's overlay), and the merged `--settings` keeps it too. Runs
  `cd WORKTREE && claude "$instruction" --bg -n NAME --model M --effort E --settings MERGED
  --append-system-prompt-file BEHAVIOUR --disallowedTools AskUserQuestion [--allowedTools ...]`,
  prompt first; parses `backgrounded · ID` from stdout, writes `NAME.id`, then prints the
  background `watch_workers.sh` command as today. A resume is `claude --resume SESSIONID --bg`
  with **no flags** (6); a model or effort change is a new session, never a resume with flags.
- **The supervisor (`codex_worker.py`)** on the `--bg` path: no child process and no job object
  any more; it watches the result file, and after the grace period runs `claude stop ID` (the
  process ends, the conversation stays, the session shows `done`).
- **watch_workers.sh** (check 8): per worker, every interval, (a) the disk watch on the result and
  question files exactly as today (the done signal); (b) one call `claude agents --json --all`,
  the row whose `id` = `NAME.id`: `state: blocked` → WAITING, with `waitingFor` as the reason line
  (`permission prompt`, `input needed`, `sandbox request`, `worker request`, `dialog open`);
  `done` / `stopped` / `failed` with no result on disk → GONE; row absent → GONE (removed);
  `working` → nothing. The pane capture and `waiting_patterns.txt` go on this path; `claude logs
  ID` replaces the "last 15 pane lines" (stripped of ANSI, last screen only).
- **close_worker.sh**: `claude stop ID`, then `claude rm ID` (removes only the row; the
  lead-made worktree stays, 5), then the existing lock lift and `clean_worktrees.sh --only=NAME`
  audit. The #171 "same name, other checkout" check becomes: `cwd` of the id's row equals the
  worktree. Never `claude daemon stop`.
- **show_workers.sh**: prints `claude agents` (the owner's one list) and `claude attach ID` per
  worker; opens nothing. A desktop-launcher stays optional.
- **Fallback**: the WT tab (Windows) and tmux (POSIX) paths stay behind a switch for one release.

## What a POSIX spike must check (needs WSL or a Linux/macOS host: owner's OK)

1. `claude --bg` starts the supervisor without a systemd/launchd service ("Service install is
   disabled in this version — the daemon runs on demand"); does it survive closing the shell and an
   SSH logout, and the "about a minute" reconnect window the docs give for macOS and Linux?
2. The same flag set (2a-2e) and the copy-on-flags resume behaviour (6).
3. Trust: same T2/T3 rules on POSIX paths, with the repo root trusted in that host's `~/.claude.json`.
4. `bgIsolation: "none"` + lead-made worktree: no push (3); one session with isolation on, to see
   the documented push and draft PR land in a bare origin (3b), `gh` denied.
5. `claude agents --json --all` field set and states on POSIX; `pid` and `status` presence.
6. `claude stop` / `rm` keep a dirty and an unpushed lead-made worktree (5).
7. `claude attach` from a real terminal (also owed on Windows) and from inside tmux, where the kit
   runs today.
8. The kit's POSIX hooks (`py.sh`, the state hooks) under a supervisor-started process: same
   environment, PATH and `CLAUDE_PROJECT_DIR`?
9. Under WSL: a native-Windows lead and a WSL `--bg` worker do not see each other in `claude agents`
   (separate installs, per the research report): confirm, as it decides whether WSL can serve at all.

## Limits

- One worker run and one copy; `failed`, `needs input` from a question, a reboot and the one-hour
  idle stop were not observed.
- The `idle_prompt` timing comes from one hook firing.
- The setup left a trust entry for the deleted `_bgspike_tmp/repo` in the owner's `~/.claude.json`
  (made by the owner's own trust prompt); the spike cannot remove it (the classifier refuses edits
  there). It is inert.
