# Spike: Claude Code background sessions as the kit's worker layer (Step B)

Date: 2026-10-20. Host: native Windows 11, Claude Code 2.1.304, Git for Windows sh and PowerShell 7.
Brief: `.myagentkit/v012/bgspike-brief.md`; background: `docs/research/worker-orchestration.md`,
option 1, Step B.

**Status: INCOMPLETE, blocked on workspace trust.** No background session has been started yet
(0 of the 2 allowed). Checks 1-6 and 8 wait for a trusted throwaway folder; see "Blocker" below.

## Setup (throwaway, outside the kit)

- `origin` = bare repo `C:/Users/kemal/AppData/Local/Temp/bgspike/origin.git`; clones take it as
  `origin` (the kit's `guard_destructive_git.py` refuses `git remote add`, so the repo is cloned from
  the bare one instead).
- First clone `C:/Users/kemal/AppData/Local/Temp/bgspike/repo` (untrusted, used only for the trust
  probe). Second clone `D:/_Production_D/Development/Projects/_MyAIKits/_bgspike_tmp/repo` with
  `.claude/settings.json` = `{"worktree": {"bgIsolation": "none"}}` committed and pushed (the place
  the docs name: "Add the setting to the project's `.claude/settings.json`" [agent-view]).
- Lead-made worktree: `git worktree add -q -b w1 .claude/worktrees/w1` in that clone.
- Worker inputs ready: `behaviour.md` (marker rule for `--append-system-prompt-file`),
  `settings.json` for `--settings` (allow Read/Write/Edit/`Bash(git:*)`, deny `Bash(gh:*)`,
  SessionStart/Stop/Notification hooks appending their JSON input to `bgspike/hook.log`, so the hook
  log proves the merged settings were read), `task1.txt` (write, commit, report tools/model/branch,
  result file, then one unallowed command to provoke a permission wait).

## Observations so far

### T1. `--bg` in an untrusted folder — CONFIRMED as documented

```
$ cd C:/Users/kemal/AppData/Local/Temp/bgspike/repo && claude --bg -n trustprobe "write nothing"
Workspace not trusted. Run `claude` in C:\Users\kemal\AppData\Local\Temp\bgspike\repo once and accept the trust prompt, then retry.
exit=1
$ claude agents --json --all | grep -c trustprobe
0
```

No session row is created. Matches the docs ("Where no dialog can appear, such as in a script, the
command exits with a `Workspace not trusted` error").

### T2. Trust is not inherited from a trusted parent folder — CONFIRMED (new)

`D:/_Production_D/Development/Projects/_MyAIKits` is trusted in `~/.claude.json`
(`hasTrustDialogAccepted: true`), yet:

```
$ cd D:/.../_MyAIKits/_bgspike_tmp/repo/.claude/worktrees/w1 && claude "<task>" --bg -n bgspike-w1 --model claude-sonnet-5-5 --effort low --settings .../settings.json --append-system-prompt-file .../behaviour.md --disallowedTools AskUserQuestion
Workspace not trusted. Run `claude` in D:\_Production_D\Development\Projects\_MyAIKits\_bgspike_tmp\repo\.claude\worktrees\w1 once and accept the trust prompt, then retry.
exit=1
```

The folder named is the worktree itself. Whether trusting the **repository root** is enough for a
lead-made worktree inside it (the kit's real case: the project is trusted, `.claude/worktrees/NAME`
never is by itself) is the first thing to check once unblocked. The kit's own worktrees carry no
trust key of their own in `~/.claude.json` and their interactive sessions start, so the interactive
path resolves worktrees to the repo; `--bg` is unverified.

### T3. `claude logs` / `claude attach` / `claude agents --json` from both shells — partly CONFIRMED

```
Git Bash:   $ claude logs bgspike-nosuch     -> No job matching 'bgspike-nosuch'. Run 'claude agents' to list running sessions.  exit=1
            $ claude attach bgspike-nosuch   -> same message, exit=1
            $ claude agents --json           -> 5 rows; keys: cwd id kind name pid sessionId startedAt state status
PowerShell: > claude logs bgspike-nosuch     -> same message, exit=1
            > claude attach bgspike-nosuch   -> same message, exit=1
            > claude agents --json | ConvertFrom-Json  -> 5 rows
```

All three commands run and resolve names from both shells without a TTY; the output on a real
session (and `attach` in a real terminal) is still to check.

### T4. Safety note for Step C

`claude daemon stop` "Shut[s] down the supervisor and terminate[s] background sessions" (all of them,
the owner's included) unless `--keep-workers`: the kit must never call it.

## Blocker

Making the throwaway folder trusted needs either the owner to run `claude` once in it and accept the
trust prompt, or a write to `~/.claude.json`; the second was refused by this host's auto-mode
classifier ("Self-Modification") and is not attempted again. The question went to the lead
(`QUESTION-bgspike.md`).
