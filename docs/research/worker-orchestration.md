# How should the kit run worker sessions? Options for opening, listing, closing and watching workers

Date: 2026-10-20. Claude Code on the research host: 2.1.304, native Windows 11 (Git for Windows sh).
Question: the owner's request of 2026-10-18 (`.myagentkit/v012/next-batch.md`, "orch-research"):
is there a better way to run worker sessions than `spawn_worker.sh`'s tmux / Windows Terminal tab
paths, so that opening and closing a worker cannot go wrong, and what signal reliably says a worker
is done. Research only; nothing in the kit was changed.

Sources are numbered `[n]` and listed in section 7. Each one carries its kind: **P** = primary
(the vendor's or the project's own page, repository, issue tracker, or the CLI's own output),
**B** = secondary (a mirror, a curated list, a blog about someone else's product). Every source was
read on 2026-10-20. Sources marked *(author)* were read by the author of this report; the others were
read by three research helpers (Sonnet 5.5, medium effort) and their reports were not re-read line
by line: they are as good as the helper's reading. **UNVERIFIED** marks a claim nobody confirmed.
**Inference** marks the author's own reasoning from the sources, not a sourced fact.

---

## 1) Summary

1. **Claude Code now ships its own session supervisor, and it runs on native Windows.** `claude --bg`
   starts a session in the background, prints an id, and `claude agents --json`, `claude logs`,
   `claude attach`, `claude stop` and `claude rm` list, read, show, stop and delete it [1][2]. On
   this Windows host `claude agents --json` already lists every running session, interactive ones
   included, with pid, folder, name and state, without a TTY [3]. This is the "tool lists and closes
   the sessions, never the tab" the owner asked for, and it is first-party, not a third-party
   framework.
2. **It is a research preview that changes fast** (introduced in 2.1.139; about 60 changelog rows
   to 2.1.304, many of them Windows and worktree-deletion fixes) [1]. One default conflicts with the
   kit: a background session that isolates itself in a worktree commits, **pushes its branch and
   opens a draft PR** when it finishes [1, v2.1.198]. The kit must turn that isolation off
   (`worktree.bgIsolation: "none"`) and keep making its own worktrees.
3. **No third-party orchestrator fits.** None of Claude Squad, dmux, ccmanager, Conductor, Vibe Kanban,
   agent-deck, workmux runs natively on Windows *and* is scriptable; the tmux-based ones need WSL,
   Vibe Kanban is sunsetting, Conductor is macOS only [15]–[25]. Each would sit in the middle, which
   `patterns/multi-tool-orchestration.md` rejects.
4. **No mature tmux for native Windows exists.** psmux is the only serious one: native, MIT, 3.7k
   stars, but under a year old, and its current release breaks arrow keys for Claude Code (#845,
   open); Anthropic closed the request to support it as "not planned" [6][28].
5. **Agent Teams, the Workflow tool and sub-agents do not replace long workers**: they live inside
   the lead's session (teammates and workflow agents die or stop with it, no resume for in-process
   teammates, five-minute cache unless raised) and Agent Teams has no split panes on Windows [5][7][8].
6. **Done signal: the result file on disk stays the signal.** Idle notices and hooks are best-effort
   by Anthropic's own docs and by many bug reports [4][13][14]. The 4-of-5 missed `notify_when_idle`
   notices of 2026-10-20 are most likely the kit's own doing: on Windows the supervisor hard-kills the
   worker's process tree 10 s after its result, possibly mid-turn, so the session never goes idle and
   cannot send an exit notice (inference, section 3, Q4).
7. **Recommendation:** (1) adopt `claude agents --json` now as the kit's session list on Windows
   (small, low risk); (2) run one spike, then move the Windows worker path from a WT tab to
   `claude --bg` with lead-made worktrees, keeping the result file as the done signal; later the same
   path can serve POSIX, giving one layer for both hosts; (3) psmux only as an opt-in experiment.

---

## 2) Per-option table

"Close by tool" = the kit can end exactly this worker by id or name without touching a window.
"Worktree safety" = what protects uncommitted or unpushed work when the session is removed.

| Option | Native Windows | List sessions | Close by tool | Result hand-back | Worktree safety | Survives terminal close / reboot | Maturity | Dependency kind |
|---|---|---|---|---|---|---|---|---|
| **Today: `spawn_worker.sh`, WT tab** (Windows) | yes | kit: CIM process list parsed for `-n NAME` (`close_worker.sh`) | `taskkill /T /F` by recorded pid; tab closes by `exit 0` | result file + `codex_worker.py` supervisor | kit's `clean_worktrees.sh` audit, `git worktree lock` | terminal close kills it; no | kit-owned, field-tested, tabs misbehave | none |
| **Today: tmux** (POSIX) | no | `tmux ls` | `tmux kill-session -t =NAME` + process-tree SIGTERM | same | same | terminal close: yes; reboot: no | mature | tmux (OS package) |
| **`claude --bg` / agent view** | yes [1][2][3] | `claude agents --json [--all]`, no TTY [2][3] | `claude stop ID`, `claude rm ID` [2] | no result channel; `claude logs`, peek panel; the kit's file still needed [1][2] | `rm` keeps a worktree with uncommitted changes or unpushed commits, or one another live session runs in [1, v2.1.208/227]; holds `git worktree lock` while running [1, v2.1.248] | terminal close and sleep: yes; reboot: stops, resumable on attach [1] | research preview, heavy churn [1] | first-party (Claude Code) |
| **Agent Teams** | in-process only; split panes "not supported in … Windows Terminal" [5] | agent panel; task list files [5] | `x` in the panel, or ask the lead [5] | teammate's final answer to the lead [5] | none of its own | dies with the lead's process; no resume for in-process teammates [5] | experimental, off by default [5] | first-party |
| **Workflow tool** | yes (survives restart "including on Windows") [1, v2.1.196] | `/workflows` [7] | stop `x` in `/workflows` [7] | the script's return value [7] | per-agent isolated copy if the script asks (option name UNVERIFIED) [7] | inside the lead session; replay after `--resume` [7] | stable feature, opt-in per run | first-party |
| **Sub-agents** | yes | the session's agent list; VS Code "Agent map" [8][9] | stop from the panel / Agent map [9] | final report to the parent [8] | `isolation: worktree`: temp worktree from the **default branch**, removed if unchanged [8] | tied to the parent session [8] | stable | first-party |
| **`claude -p` headless** | implied, not stated (UNVERIFIED) [11] | none: the caller owns the process [11] | kill the process (SIGTERM exits 143) [11] | `--output-format json` result + session id [11] | none of its own | no | stable | first-party |
| **psmux** (tmux for Windows) | yes, ConPTY [28] | `list-sessions`, `has-session` [28] | `kill-session` [28] | via the kit, as with tmux | via the kit | like tmux | ~11 months old; Claude Code input regressions open [28] | **hard third-party** |
| **WSL tmux** | no (Linux inside Windows) | tmux | tmux | via the kit | via the kit, on `/mnt/d` (slow) [32] | like tmux | mature | WSL + a second Claude install [12][32] |
| **Claude Squad / dmux / agent-deck / workmux** | no (tmux; WSL only) [15][16][21][22] | own TUI | own TUI (`D`, merge, `worktree finish`) | none (screen/hook status) | own merge/cleanup, safety UNVERIFIED | via tmux | active, 1k–8.6k stars | **hard third-party, in the middle** |
| **ccmanager** | not stated (likely no) [17] | own TUI | own TUI; sessions live inside its process (inference) | screen-parsed Waiting/Busy/Idle [17] | own; UNVERIFIED | no (inference) | active | hard third-party |
| **Conductor / Nimbalyst / Vibe Kanban** | Conductor macOS only [18]; Nimbalyst has a Windows build [20]; Vibe Kanban sunsetting [19] | GUI | GUI | GUI | own worktrees | app-bound | varies | GUI app, not scriptable from a lead |

---

## 3) Findings per question

### Q1. Claude Code's own options

**Background sessions / agent view (`claude --bg`, `claude agents`).**
- What it is. `--bg` "Start[s] the session in the background and return[s] immediately. Prints the
  id that `claude attach`, `logs`, `stop` and `rm` take; `claude agents` lists them." With
  `--resume <session-id>` it continues that session in the background under the same id [2]
  *(author)*, [1, v2.1.257] *(author)*. `claude stop <id>`: "Its conversation is kept; resume it
  later with `claude attach <id>`." `claude rm <id>`: "Delete a background session and its worktree.
  Unlike `stop`, works on already-exited sessions." `claude logs <id|name>` prints recent terminal
  output; `attach` and `logs` take part of the name in place of the id [2] *(author)*.
- Native Windows: yes. The changelog carries Windows-specific fixes: in-flight background work
  carries over "on Windows too" (2.1.195); background shell commands and workflows survive the
  session's process being stopped, restarted or updated, "including on Windows" (2.1.196); a stale
  Windows `daemon.lock` made every start fail until deleted by hand (fixed 2.1.257); `claude agents`
  keyboard in win32-input-mode tabs (2.1.248). A stuck supervisor on Windows is ended with
  `taskkill /PID` [1] *(author)*. On this host, `claude agents --json` printed five sessions: four
  interactive (with `pid`, `cwd`, `name`, `sessionId`, `status: busy`) and one background (with
  `state: blocked`), this worker among them as `orchresearch` with its worktree as `cwd` [3]
  *(author)*. The owner already has a background session on this host [3].
- States: Working, Needs input (a question, a permission, a sandbox/MCP prompt, a held peer message
  shows `approve message from`), Idle, Completed, Failed, Stopped; `--json` reports them, with
  `waitingFor` since 2.1.212 [1] *(author)*.
- Persistence. A separate supervisor process runs the sessions, so a closed terminal does not stop
  them. An idle or finished session left unattached for about an hour has its process stopped; "the
  conversation stays on disk, and the next time you attach or reply, the session resumes"; `Ctrl+T`
  pins a session's process. After a reboot sessions show as failed or as stopped "ended while the
  background service was off" (older than 48 h) and resume on attach [1] *(author)*.
- Worktrees. A dispatched session "moves into an isolated git worktree under `.claude/worktrees/`"
  before editing; `worktree.bgIsolation: "none"` turns that off [1] *(author)*. Since 2.1.251 a
  background session that has not moved into a worktree can edit files inside a linked worktree [1]
  *(author)*: that is the kit's case (the lead makes the worktree, the worker runs in it). Deleting a
  session removes its worktree but keeps it when it has uncommitted changes, unpushed commits
  (2.1.208/2.1.260), or another live session runs inside it (2.1.227); a running background session
  holds `git worktree lock` (2.1.248) [1] *(author)*. **Conflict with the kit:** "A background session
  that isolated its work in a worktree commits, pushes its own isolated branch, never `main` or
  `master`, and opens a draft pull request when it finishes instead of asking first" [1, v2.1.198]
  *(author)*. The kit pushes only on the owner's request, so its workers must run with
  `bgIsolation: "none"` in a lead-made worktree. Whether that alone stops the push is UNVERIFIED
  (spike item).
- Model, effort, flags. `claude agents` takes `--model`, `--effort`, `--permission-mode`,
  `--add-dir`, `--mcp-config`, `--plugin-dir`, `--setting-sources` as dispatch defaults [2]
  *(author)*. Whether `claude --bg` honours every flag `spawn_worker.sh` passes today
  (`--append-system-prompt-file`, `--settings` with the merged hooks, `--disallowedTools
  AskUserQuestion`, `-n NAME`, `--effort`) is UNVERIFIED; `--setting-sources` carries over since
  2.1.281 [1]. `--bg` with `-p` is rejected (2.1.198), and `--bg` in a script exits with
  "Workspace not trusted" in an untrusted folder (2.1.281) [1] *(author)*, which matches the kit's
  existing trust rule.
- Peer messaging: background sessions bind an inbox (a named pipe on native Windows, 2.1.234+) and
  appear in `ListAgents` [4] *(author)*.
- Maturity: "Agent view is in research preview. The interface and keyboard shortcuts may change"
  [1] *(author)*. The version table runs from 2.1.139 to 2.1.290+ with about 60 rows, a third of
  them deletion, worktree and supervisor-start fixes [1] *(author)*.

**What it would replace and what each side loses** (inference from the above and the kit's scripts):

| Guarantee | `spawn_worker.sh` + WT tab today | `claude --bg` |
|---|---|---|
| List workers | CIM process list, command line split by CommandLineToArgvW rules, `-n NAME` matched, pid record (`close_worker.sh`) | `claude agents --json`: id, name, cwd, state; no parsing |
| Close the right one | `taskkill /T /F` on the recorded pid, cwd checks against #171 | `claude stop ID` / `claude rm ID`; no window involved, so no wrong tab |
| Owner sees the work | a tab per worker, live | `claude agents` (one list, Needs-input first) and `claude attach NAME` |
| Waits on a person | the kit's Notification/Stop hooks write `NAME.state` | `state` / `waitingFor` in `--json`; hooks still possible |
| Supervisor ends it after the result | `codex_worker.py` owns the child in a kill-on-close job | the daemon owns the process; the kit would call `claude stop` instead (design change) |
| Terminal or lead closes | worker dies with its tab | worker keeps running |
| Worktree | lead-made, locked, audited removal | same if `bgIsolation: none`; plus Claude Code's own refusal to delete unpushed or dirty worktrees |
| Third-party risk | none | none (first-party), but preview churn |

**Agent Teams.** Experimental, off by default (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). Split-pane
mode needs tmux or iTerm2 and is "not supported in VS Code's integrated terminal, Windows Terminal,
or Ghostty"; in-process mode works anywhere. No `/resume` or `/rewind` for in-process teammates, one
team per session, a fixed lead, permission prompts bubble to the lead; a stopping teammate notifies
the lead with its final answer; `TeammateIdle`, `TaskCreated`, `TaskCompleted` hooks [5]. The kit's
earlier research measured about seven times the tokens [36, finding 7]. anthropics/claude-code#34150
(opened 2026-03-13 by the psmux author) asked for tmux-compatible multiplexers on Windows; it says
`process.stdout.isTTY` is undefined under the Windows build and forces in-process mode even with
`teammateMode: "tmux"`; it was closed "not planned" by the stale bot on 2026-04-10 and locked, with
no maintainer reply [6]. Verdict: not a replacement; teammates live and die with the lead.

**Workflow tool.** A JavaScript script the lead writes; a runtime runs it in the background; up to
16 concurrent agents by default, 1,000 per run; `/workflows` shows, pauses and stops it; no mid-run
user input; resume replays cached agent results; a silent agent is restarted up to five times;
workflow agents use the five-minute cache unless `subagentPromptCacheTtl: "1h"` [7]. The kit's own
host instructions require the owner's explicit opt-in before a workflow runs. Verdict: right for a
bounded fan-out the lead waits on, wrong for an hours-long worker that commits and waits on gates.

**Sub-agents.** Background by default from the main conversation; `isolation: worktree` makes a
temporary worktree **from the default branch, not the parent's HEAD** [8], the same stale-base trap
`spawn_worker.sh` already avoids for `-w`. Tied to the parent session. The kit already uses them for
short errands (WORKFLOW "Worker cost": over about an hour = own session).

**VS Code "Agent map"** (2.1.269+): a tree of the current session's sub-agents with status, elapsed
time and tokens; stop from there; `/tasks` for background shells (2.1.277+) [9]. It shows agents
inside one session, not separate worker sessions; no Windows limit stated [9]. Not a replacement.

### Q2. Third-party orchestrators

No tool found both runs on native Windows and lets a lead create, list and end Claude Code sessions
from a script, while being a stable dependency.

| Tool | What | Native Windows | Latest release / stars / license | Sessions | Worktrees | Idle/done detection |
|---|---|---|---|---|---|---|
| Claude Squad [15] | Go TUI over tmux | **no**: Windows binary fails "error starting tmux session: unsupported" (#275, open) | v1.0.20 2026-08-20, ~8.6k, **AGPL-3.0** | `n` new, `D` kill, `c` commit+pause | yes | none; `--autoyes` auto-accepts prompts |
| dmux [16] | Node TUI over tmux ≥3.0 | **no** (#85: exits on Windows, HOME undefined) | v5.11.1 2026-08-16, ~1.8k, MIT | `n` pane = worktree+agent; merge/PR menu | yes, with hooks | UNVERIFIED |
| ccmanager [17] | Node TUI, own PTYs, no tmux | not stated; maintainer reply in #164 only covers WSL | v4.4.9 2026-10-18, ~1.3k, MIT | inside its own process (closing the TUI ends them: inference) | create/merge/delete | screen parsing per tool: Waiting/Busy/Idle |
| Conductor [18] | Mac desktop app | **no**, macOS only | cask v0.85.0; license UNVERIFIED | GUI workspaces | yes | UNVERIFIED |
| Vibe Kanban [19] | local web UI (npx) | UNVERIFIED | v0.1.44 2026-04-24, ~28k, Apache-2.0; **README: "sunsetting"** | workspaces | yes | UNVERIFIED |
| Nimbalyst (was Crystal) [20] | Electron app | **yes**, Windows download | Crystal v0.3.5 2026-02-26 MIT, deprecated; Nimbalyst repo/license UNVERIFIED | GUI | Crystal: per session | UNVERIFIED |
| agent-deck [21] | Go TUI over tmux | **no** ("Windows (WSL)") | v1.16.30 2026-10-18, ~1.1k, MIT | `worktree finish` merges, removes worktree, deletes session | yes | running/waiting/done; method UNVERIFIED |
| workmux [22] | CLI + tmux | **no** | v0.1.276 2026-10-14, ~2.9k, MIT | `add`, `merge` cleans worktree, window, branch | yes | agent hooks write status icons; open bugs #202, #219 |
| uzi [23] | Go CLI + tmux | no | v0.0.2 2025-06-03: abandoned | — | yes | — |
| container-use [24] | MCP server, Docker per agent | needs Docker | v0.4.2 2025-08-19, Apache-2.0 | not a session manager | branch per container | — |
| Sculptor [25] | desktop app | not seen (UNVERIFIED) | v0.48.0 2026-09-21, ~240, MIT | GUI | yes | UNVERIFIED |

The curated list [26] tags several Windows-capable GUI tools (Agent Console, MonoCode, Runner, wmux,
Yardsort, Pragma); none was checked (UNVERIFIED). A vendor comment in Claude Squad #275 describes a
product (magent) that watches Claude Code sessions in Windows Terminal tabs through Claude Code's
lifecycle hooks [15] (UNVERIFIED product): the same hook-file pattern the kit already uses.

Addy Osmani's "Code Agent Orchestra" (2026-03-26) [27]: three tiers (one synchronous agent, local
orchestrators such as Conductor, Vibe Kanban, Claude Squad and Agent Teams for 3–10 agents, cloud
async agents); worktree per agent, which "a ~12-line bash alias set" can script; quality gates through
hooks; 3–5 agents as the sweet spot and one reviewer per 3–4 builders; kill agents stuck for several
iterations. It matches the kit's own limits (WORKFLOW "Worker cost", rule 6).

**Where a tool would be a hard dependency:** every row above. Each owns session creation and
closing, so the kit's spawn, supervisor, close and audit would route through it, the
"framework in the middle" `patterns/multi-tool-orchestration.md` rejects. GUI apps (Conductor,
Nimbalyst) cannot be driven by a lead at all. AGPL (Claude Squad) adds a licence question for a kit
that vendors its scripts into projects (inference).

### Q3. Windows: one tmux layer or two paths

- **psmux** [28]: native Rust on ConPTY, reads `.tmux.conf`, documents the commands the kit uses
  (`new-session -d -s`, `send-keys -l`, `capture-pane -p`, `has-session`, `kill-session`,
  `list-sessions`); MIT, ~3.7k stars, created 2025-11-30, v3.4.0 on 2026-10-13. Open Claude Code bugs:
  #845 (3.4.0 regression: arrow and named keys never reach Claude Code; 3.3.8 works), #578 (agent
  view clears `TMUX`), #580, #597 (mouse), #611 (Shift+Enter becomes Enter under load), #610.
  Anthropic declined to support it (#34150 closed "not planned") [6]. Young, effectively single
  maintainer, live regressions in the exact program the kit runs: not a base layer today.
- **tmuxw, tmux-windows** [29]: winget packages, source or compatibility not confirmed (UNVERIFIED).
  **itmux** bundles Cygwin: not native. **tmux upstream** has no native Windows build.
- **Zellij** [30]: native Windows support is being merged now (tracking #4745; PRs merged
  2026-10-13 and 2026-10-20), with open Windows display and paste bugs; its CLI is not
  tmux-compatible.
- **WezTerm CLI** [31]: `wezterm cli list|spawn|kill-pane|get-text|send-text` would cover the
  kit's needs, but it is a different CLI (a second adapter), and its last tagged release is from
  2024-02-03 (nightlies since).
- **WSL tmux** [12][32]: mature, but Microsoft recommends against working across file systems
  ("store your files in the WSL file system"); the owner's projects live on `D:\` with Windows-only
  tools (Unity); Claude Code inside WSL is a separate install with its own `~/.claude`; and a WSL 2
  session and a native Windows session cannot message each other [4] *(author)*. It moves the
  problem, not solves it.
- **Windows Terminal's `wt`** [33][34]: can open a tab with a title, split, and focus a tab **by
  index**; it cannot list tabs, close a tab, or read its text. The request to query tab state
  (microsoft/terminal#19818, 2026-01-30) is open with no commitment. The kit's tab path therefore
  can never close or list by itself; it closes the process and lets the tab follow.

**Finding:** a single *tmux* layer for both hosts is not available at a quality the kit can depend on
today. A single *session* layer is: Claude Code's own background sessions run on Windows, macOS and
Linux with one CLI [1][2]. That changes the question from "which tmux" to "keep tmux at all"
(inference).

### Q4. Done and idle signals

- **`notify_when_idle`** [4] *(author)*: "one notice when that session next goes idle or exits";
  "idle" = a finished turn with nothing queued; dropped after 12 hours; `refuse` on either side means
  nothing arrives; `hold` on either side means the notice arrives without its status and **is shown
  in the transcript without being delivered to Claude**. With no `crossSessionInbound` set, a
  session that bypasses permissions holds messages from one that does not. Only the main
  conversation can subscribe. The docs promise no delivery on a forced kill.
- **Bug reports** (B, mirrors; open/closed state mostly UNVERIFIED) [13]: background agents dropping
  queued messages and skipping completion notices (#78338, listed fixed 2026-08-17), going idle
  without their final report (#74113), a completion notice lost after a mid-run message (#88001),
  a notice enqueued and never delivered (#76681), idle racing the inbox (#82858), duplicate or
  stale idle notices (#74112).
- **Hooks** [10][14]: Stop (each turn), SubagentStop, Notification (`idle_prompt`,
  `permission_prompt`, and from agent view `agent_needs_input` / `agent_completed` [1, v2.1.198]
  *(author)*), SessionEnd (1.5 s default budget), TeammateIdle, TaskCompleted. A hook that times out
  fails open; no delivery guarantee is documented. Reports of Stop hooks stopping mid-session
  (#32055, Windows 11), mid-session hooks never invoked on Windows 2.1.x (#60746), SessionEnd not run
  on `/exit` (#35892), Notification not firing in VS Code or Desktop (#28774, #81788), `idle_prompt`
  fixed 60 s delay (#12048) [14] (B; fixed state at 2.1.304 UNVERIFIED).
- **The kit's 4-of-5 miss (inference, not reproduced).** On Windows `codex_worker.py` owns the worker
  in a job object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and ends it by closing the job
  (`codex_worker.py`, `windows_job()` and `stop()`), after the result is
  published: 60 s for `spawn_worker.sh` from v0.13 (`KIT_WORKER_GRACE`),
  10 s for `spawn_codex.sh`. A worker that publishes and then writes its closing reply is still mid-turn when the
  kill comes: it never goes idle, and a killed process cannot send the "exited" notice. The docs'
  hold rule is a second candidate only if the lead and the workers sit in different permission
  classes (the kit's settings set no `defaultMode`, so normally they do not). Either way the notice
  cannot be the done signal; the disk watch merged as "donewatch" (#294) is the right fix, and
  `claude agents --json` `state` would be a second, cheap observation.
- **Ranking, most to least reliable** (inference from the above): (1) the published result file on
  disk, read by the lead's background watch: it does not depend on the session's process at all;
  (2) the session's state from the supervisor (`claude agents --json`: Completed/Failed/Stopped/Needs
  input) or, for tabs, the kit's own `NAME.state` hook file and process exit; (3) hooks; (4) peer idle
  notices. Third-party tools fall to screen parsing (ccmanager) or the same hooks (workmux, magent)
  [17][22][15].

---

## 4) Recommendation (ranked)

**1. Claude Code background sessions as the worker session layer, Windows first (recommended).**
Staged:
- *Step A, now, small:* `close_worker.sh` and a new read-only `list_workers` view take the session
  list from `claude agents --json` (pid, cwd, name, kind, state) instead of parsing CIM command lines;
  the cwd field settles #171-style "same name, other checkout" by folder [3]. Interactive tab workers
  keep `taskkill` by pid, so nothing else changes.
- *Step B, one spike (one worker, one small real task, this host):* `claude --bg -n NAME` started from
  inside a lead-made worktree with `worktree.bgIsolation: "none"`; check that
  `--append-system-prompt-file`, merged `--settings`, `--disallowedTools AskUserQuestion`, `--model`,
  `--effort` are honoured; that no push or draft PR happens; that `claude stop` / `claude rm` behave
  as documented on a dirty and an unpushed worktree; that a published result plus `claude stop`
  leaves the session `Stopped` and resumable with `--resume ID --bg`.
- *Step C:* on Windows `spawn_worker.sh` starts `claude --bg` instead of a WT tab; the supervisor
  ends it with `claude stop` (the kill-on-close job goes); `watch_workers.sh` reads `state` /
  `waitingFor` instead of `NAME.state`; `show_workers.sh` becomes `claude agents` / `claude attach`.
  The result file stays the done signal. *Step D, later:* the same path on POSIX, after a release of
  field use, retiring tmux → one layer for both hosts.
- Gains: the tool lists and closes, never a tab; workers survive a closed terminal; Needs-input
  visible in one list; Claude Code itself refuses to delete dirty or unpushed worktrees [1][2][3].
- Cost: no extra tokens (same sessions); the supervisor's one-hour idle stop matches the kit's
  one-hour cache. Migration effort: medium (Windows branches of spawn, close, watch and the
  supervisor, their tests with a `claude` stub; doc sections). Risk: medium: research preview with
  frequent behaviour changes [1]; the auto push/PR default must stay off; reboot stops sessions
  (resumable); the kit's Windows path then depends on Claude Code's daemon (first-party, which the
  single-model mandate allows).

**2. Keep the WT tab path, harden it (fallback if the spike fails).** Step A above, plus: the
lead never asks the owner to close a tab (only `close_worker.sh`), tab titles carry the worker name
(`wt new-tab --title`) [33]. Cost: low; risk: low; the tab cannot be listed or closed by id while
Windows Terminal lacks it (#19818 open) [34], so "cannot go wrong" is not reached, only narrowed.

**3. psmux as an opt-in tmux stand-in on Windows (not now).** One tmux code path for both hosts
[28], but a hard third-party dependency with open Claude Code input regressions and no Anthropic
support [6][28]. Revisit only if option 1 fails and psmux has a release without Claude Code input
bugs for a few months. Cost: low code (the tmux path exists); risk: high.

**Not recommended:** third-party orchestrators (no native Windows + scriptable + stable candidate;
all sit in the middle) [15]–[25]; Agent Teams (no Windows panes, teammates die with the lead,
~7× tokens) [5][6][36]; Workflow tool and sub-agents for long workers (session-bound) [7][8]; WSL
tmux (fights `D:\` projects and Windows-only tools) [32].

---

## 5) Open questions for the owner

1. May the lead run the one-worker spike of step B on this host (one Sonnet or Opus worker, a small
   real task)? It is the only way to verify the UNVERIFIED flag and push behaviour.
2. Is a first-party **research preview** acceptable as the base of the Windows worker path, given
   option 2 stays as the fallback?
3. Visibility: today every worker has its own tab. With option 1 the owner sees workers in
   `claude agents` (one list) and opens one with `claude attach NAME`. Acceptable?
4. Windows only first, POSIX after a release of use, or both together?

---

## 6) Limits of this report

- No `claude --bg` session was started; every behaviour of a background *worker* is from the docs and
  the CLI's help, not observed. Only `claude agents --json` was run [3].
- The helper-read sources (marked without *(author)*) were summarised by Sonnet 5.5 helpers; the
  author re-read only the agent-view and cross-session-messaging pages and the local CLI.
- Bug state from claudeissues.com mirrors [13][14][35] may lag GitHub.
- The cause of the 4-of-5 notice miss is an inference from the kit's code and the docs; it was not
  reproduced.

---

## 7) Sources

1. Claude Code docs — Agent view / background sessions (incl. version history 2.1.139–2.1.290+) — https://code.claude.com/docs/en/agent-view — P — read 2026-10-20 *(author)*
2. Claude Code 2.1.304 CLI help: `claude --help`, `claude agents --help`, `claude stop|rm|logs|attach|respawn|daemon --help` — local CLI output — P — 2026-10-20 *(author)*
3. `claude agents --json` on the research host (native Windows 11), five sessions listed — local CLI output — P — 2026-10-20 *(author)*
4. Claude Code docs — Message your other Claude Code sessions (`notify_when_idle`, `crossSessionInbound`, Windows named pipe, WSL/native isolation) — https://code.claude.com/docs/en/cross-session-messaging — P — 2026-10-20 *(author)*
5. Claude Code docs — Agent teams — https://code.claude.com/docs/en/agent-teams — P — 2026-10-20
6. anthropics/claude-code#34150 — tmux-compatible multiplexer (psmux) support on Windows; closed not planned 2026-04-10 — https://github.com/anthropics/claude-code/issues/34150 — P — 2026-10-20
7. Claude Code docs — Workflows — https://code.claude.com/docs/en/workflows — P — 2026-10-20
8. Claude Code docs — Subagents (background, `isolation: worktree`, limits, cache TTL) — https://code.claude.com/docs/en/sub-agents — P — 2026-10-20
9. Claude Code docs — VS Code extension (Agent map, `/tasks`) — https://code.claude.com/docs/en/vs-code — P — 2026-10-20
10. Claude Code docs — Hooks reference (partly read) — https://code.claude.com/docs/en/hooks — P — 2026-10-20
11. Claude Code docs — Headless / `-p` (json and stream-json output, resume, exit codes) — https://code.claude.com/docs/en/headless — P — 2026-10-20
12. Claude Code docs — Setup (native Windows, Git for Windows, WSL as a separate install) — https://code.claude.com/docs/en/setup — P — 2026-10-20
13. Idle/notification bug reports, claudeissues.com mirrors of anthropics/claude-code: #78338 https://claudeissues.com/issue/78338-background-agents-drop-queued-sendmessages-and-skip-completion-notifications ; #74113 https://claudeissues.com/issue/74113-bug-background-agents-frequently-go-idle-without-delivering-their-final-sendmess ; #88001 https://claudeissues.com/issue/88001-background-agent-completion-notification-lost-after-messaging-the-agent-mid-run ; #76681 https://claudeissues.com/issue/76681-background-task-notification-enqueued-but-never-delivered-when-the-owning-subage ; #82858 https://claudeissues.com/issue/82858-bug-agent-idle-transition-doesnt-drain-queued-inbox-idle-notification-races-send ; #74112 https://claudeissues.com/issue/74112-bug-duplicate-stale-idle-notification-messages-from-background-teammate-agents-f — B — 2026-10-20
14. Hook bug reports, claudeissues.com mirrors: #38199 https://claudeissues.com/issue/38199-bug-stop-hook-fires-on-every-response-turn-not-session-exit-breaks-interactive-w ; #32055 https://claudeissues.com/issue/32055-stop-hook-intermittently-stops-firing-mid-session ; #60746 https://claudeissues.com/issue/60746-bug-hook-executor-silent-fail-in-v2-1-x-mid-session-hooks-never-invoked-despite ; #56096 https://claudeissues.com/issue/56096-bug-ralph-loop-stop-hook-silently-fails-on-windows-after-claude-code-2-1-126-wor ; #35892 https://claudeissues.com/issue/35892-sessionend-stop-hooks-should-fire-on-exit-command ; #73924 https://claudeissues.com/issue/73924-bug-sessionend-hooks-never-fire-for-long-lived-remote-control-sessions-lifecycle ; also #26770, #77480, #28774, #79881, #83577, #81788, #42487, #51882, #12048 (same site) — B — 2026-10-20
15. Claude Squad — https://github.com/smtg-ai/claude-squad ; Windows issue #275 (incl. a vendor comment on magent) https://github.com/smtg-ai/claude-squad/issues/275 — P — 2026-10-20
16. dmux — https://github.com/standardagents/dmux ; issue #85 https://github.com/standardagents/dmux/issues/85 — P — 2026-10-20
17. ccmanager — https://github.com/kbwo/ccmanager ; issue #164 https://github.com/kbwo/ccmanager/issues/164 — P — 2026-10-20
18. Conductor — https://conductor.build — P; Homebrew cask https://formulae.brew.sh/cask/conductor — B — 2026-10-20
19. Vibe Kanban — https://github.com/BloopAI/vibe-kanban — P — 2026-10-20
20. Nimbalyst — https://nimbalyst.com — P; Crystal (deprecated) https://github.com/stravu/crystal — P — 2026-10-20
21. agent-deck — https://github.com/asheshgoplani/agent-deck — P — 2026-10-20
22. workmux — https://github.com/raine/workmux (issues #202, #219) — P — 2026-10-20
23. uzi — https://github.com/devflowinc/uzi — P — 2026-10-20
24. container-use — https://github.com/dagger/container-use — P — 2026-10-20
25. Sculptor — https://github.com/imbue-ai/sculptor — P — 2026-10-20
26. awesome-agent-orchestrators (curated list) — https://github.com/andyrewlee/awesome-agent-orchestrators — B — 2026-10-20
27. Addy Osmani — The Code Agent Orchestra (2026-03-26) — https://addyosmani.com/blog/code-agent-orchestra/ — B — 2026-10-20
28. psmux — https://github.com/psmux/psmux ; compatibility https://github.com/psmux/psmux/blob/master/docs/compatibility.md ; issues #845, #578, #580, #597, #610, #611 https://github.com/psmux/psmux/issues — P — 2026-10-20
29. tmuxw / tmux-windows winget listings — https://wingetly.io/apps/turin/tmuxw — B — 2026-10-20
30. Zellij — https://github.com/zellij-org/zellij (tracking issue #4745; PRs #5652, #5679, #5734) — P — 2026-10-20
31. WezTerm CLI — https://wezterm.org/cli/cli/index.html — P; repo https://github.com/wezterm/wezterm — P; Claude Code statusline in WezTerm Win11 https://claudeissues.com/issue/60386 — B — 2026-10-20
32. Microsoft — Working across Windows and Linux file systems — https://learn.microsoft.com/en-us/windows/wsl/filesystems — P — 2026-10-20
33. Microsoft — Windows Terminal command line arguments — https://learn.microsoft.com/en-us/windows/terminal/command-line-arguments — P — 2026-10-20
34. microsoft/terminal#19818 — Add commands to query the state and metadata of tabs (open) — https://github.com/microsoft/terminal/issues/19818 — P — 2026-10-20
35. Windows TUI bug reports, claudeissues.com mirrors: #14599, #22970, #77975 — https://claudeissues.com — B — 2026-10-20
36. The kit's own report — `docs/research/agent-kits-in-practice.md`, finding 7 (agent teams about 7× tokens, its source [3]) — kit — 2026-10-13
