#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Open a SEPARATE Claude Code worker session in tmux and hand it a brief file. On native
# Windows (Git for Windows' sh, MSYS2, Cygwin), which has no tmux, it opens as a Windows
# Terminal tab instead (see "Native Windows" below), and what follows about showing,
# watching and closing a tmux session does not apply there. Nothing can read that tab, so
# there the worker's --settings gain a Notification and a Stop hook (the owner's settings and
# hooks are kept; the merged file is .myagentkit/workers/NAME.settings.json) that write its
# state line, `waiting permission|question TIME ID` or `idle TIME ID`, to .myagentkit/workers/
# NAME.state, which watch_workers.sh reads in place of a pane. The result file stays the done
# signal.
#
# Usage: spawn_worker.sh NAME BRIEF_FILE --model M --effort LEVEL [--settings JSON_OR_FILE]
#                        [--allowed-tools LIST] [--worktree] [--batch]
#
# Once the worker has its brief, its session is SHOWN: show_workers.sh opens a terminal tab
# attached to it, because a session nobody sees can wait on a dialog for hours. --batch skips
# that, for a lead that starts several and then shows them together in one call:
# `scripts/show_workers.sh NAME1 NAME2 ...`. A failure to show never fails the spawn.
#
# Why a separate session and not a sub-agent: a sub-agent's prompt cache lives 5 minutes and
# a separate session's lives an hour, so a worker that waits on a long job re-writes its
# whole context after every wait as a sub-agent and does not as a session (docs/WORKFLOW.md,
# "Worker cost"). A sub-agent with `experimental.cacheTtl: 1h` in its definition costs the
# same; the session adds visibility (`tmux attach -t NAME`) and survives the lead ending.
#
# The lead then subscribes once with SendMessage `notify_when_idle` (on native Windows only
# when the spawn printed "is a peer session"; a tmux worker registers) and reads the result
# FILE the brief asks the worker to write. It does not poll and it does not chat with the
# worker: every message to an idle session is a full-context turn. After reading the file
# the lead reuses the session or closes it with `scripts/close_worker.sh NAME`; it does not
# end by itself.
#
# Pitfalls this script encodes (each one cost a session):
#   - The prompt is typed AFTER the TUI is up, never passed on the command line after a
#     variadic flag such as --allowedTools, which would swallow it as one more value and
#     leave the session idle at an empty input line.
#   - The prompt is ONE typed line, "Read '<brief path>' and follow it." and a second sentence
#     telling it to write questions into its result file instead of asking in the pane, not
#     the brief pasted as a block: one model took a pasted brief with no typed sentence of the
#     user's own for mere content and sat idle for 35 minutes asking for confirmation.
#   - tmux receives only `sh PATH`, without quotes, for its default shell (fish included).
#     Before worktree creation, the temporary script path is made absolute and checked for
#     letters, digits, _, ., / and -. Set TMPDIR to an existing safe absolute directory
#     and retry if refused; the template honours TMPDIR on macOS and Linux alike.
#   - Every value that goes into the temporary script's shell command, and the brief path, passes
#     through `q`: a value with an apostrophe (a --settings JSON string) otherwise
#     ends its quoting and the rest runs as shell in the new pane.
#   - --worktree makes the worktree here with `git worktree add` from the commit the lead's
#     checkout is on now. Passing `-w` to the tool built it from a stale base, and workers
#     started without fixes the lead had already merged.
#   - Readiness is detected from the pane text, not from `pgrep -f`, which matches its own
#     command line.
#   - The folder must already be trusted by Claude Code; an untrusted folder blocks the
#     session in the trust dialog, which this script reports instead of waiting forever. The
#     dialog is recognised by watch_workers.sh --once from waiting_patterns.txt, the same
#     definition the lead's watcher uses, and so is a session that exited during start-up.
set -eu

# Every message is printed with its control bytes as `?`: a value echoed raw (an unknown
# option, a --settings value) put ESC sequences on the lead's terminal.
die() { { printf 'spawn_worker: %s' "$1" | LC_ALL=C tr '\001-\037\177' '?'; echo; } >&2; exit 1; }
# Quote one value for a POSIX shell: wrap it in '...' and write each ' inside as '\''.
# The x keeps a trailing newline that $(...) would strip.
q() { set -- "$(printf '%sx' "$1" | sed "s/'/'\\\\''/g")"; printf "'%s'" "${1%x}"; }

[ $# -ge 2 ] || { sed -n '3,19p' "$0"; exit 2; }
name=$1; brief=$2; shift 2
# The name and the brief path reach tmux and the TUI: `send-keys -l` types every byte, and a
# control byte (0x01-0x1F, 0x7F) acts as a key there: a carriage return submitted the
# instruction early, ESC edits it. Refused by name, checked on bytes, FIRST: before any other
# check prints the argument and before any tmux call. The message names the argument, never
# its bytes.
ctl() {
  [ "$(printf '%sx' "$2" | LC_ALL=C tr -d '\001-\037\177')" = "${2}x" ] ||
    die "the $1 contains a control character (a newline, carriage return, tab, ESC or DEL), which the worker's input line would act on; it is not printed"
}
# Checked in the argument itself, before anything rewrites it: $(...) strips trailing
# newlines, and "task.md<newline>" was checked while "task.md" was handed over. The folder
# and file name are split by parameter expansion, which keeps every byte, and the folder's
# absolute path keeps a trailing newline through the x guard; the resolved path is checked again.
ctl "worker name" "$name"
case $name in
  ''|-*|*[!ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-]*)
    die "refused the worker name: use letters, digits, - and _, not starting with -" ;;
esac
ctl "brief path" "$brief"
nl='
'
case $(uname -s 2>/dev/null) in MINGW*|MSYS*|CYGWIN*) windows=1 ;; *) windows="" ;; esac
# Git for Windows' sh takes C:\dir\brief.md too, but the split below is at `/` only: there
# every backslash is a separator, spelled `/` first. The x guard keeps a trailing newline.
if [ -n "$windows" ]; then brief=$(printf '%sx' "$brief" | tr '\\' '/') && brief=${brief%x}; fi
{ [ -f "$brief" ] && [ -r "$brief" ]; } || die "brief file not found or not readable: $brief"
case "$brief" in */*) brief_dir=${brief%/*}/ ;; *) brief_dir=. ;; esac
# Every path handed on is physical (`pwd -P`): a plain `pwd` printed the logical path when the
# caller exported a matching PWD and the physical one otherwise, so the same brief was named
# /var/... by one caller and /private/var/... by another on macOS.
brief_dir=$(CDPATH= cd -P -- "$brief_dir" && pwd -P && echo x) || die "cannot resolve the brief's folder: $brief"
brief=${brief_dir%"${nl}x"}/${brief##*/}
ctl "brief path" "$brief"
[ -n "$windows" ] || command -v tmux >/dev/null || die "tmux is not installed"
command -v claude >/dev/null || die "claude is not on PATH"

model=""; settings=""; tools=""; worktree=""; effort=""; batch=""
# Git for Windows' dirname handles both separators, including mixed paths such as D:/p\scripts\x.sh.
case $0 in *'\'*) kit=$(dirname -- "$0") ;; */*) kit=${0%/*} ;; *) kit=. ;; esac
while [ $# -gt 0 ]; do
  case "$1" in
    --model)         model=$2; shift 2 ;;
    --settings)      settings=$2; shift 2 ;;
    --allowed-tools) tools=$2; shift 2 ;;
    --worktree)      worktree=1; shift ;;
    --effort)        effort=$2; shift 2 ;;
    --batch)         batch=1; shift ;;
    *) die "unknown option: $1" ;;
  esac
done
# The lead picks both for every worker (docs/WORKFLOW.md, "Model routing"); left out, the
# session silently took the user's default.
[ -n "$model" ] || die "--model is required: the lead picks the model for every worker"
[ -n "$effort" ] || die "--effort is required: the lead picks the effort for every worker"

[ -n "$windows" ] || ! tmux has-session -t "=$name" 2>/dev/null || die "tmux session '$name' already exists"

run=""
cleanup() { [ -z "$run" ] || rm -f -- "$run" || :; }
trap 'cleanup' 0
trap 'trap - 0; cleanup; exit 129' HUP
trap 'trap - 0; cleanup; exit 130' INT
trap 'trap - 0; cleanup; exit 143' TERM
# Reserve and validate the script before creating a worktree. An explicit template
# honours TMPDIR on BSD and GNU; resolve relative paths before tmux changes directory.
if [ -z "$windows" ]; then
  run=$(mktemp "${TMPDIR:-/tmp}/kit-run.XXXXXX") || die "cannot write the session's script"
  case "$run" in */*) run_dir=${run%/*}/ ;; *) run_dir=. ;; esac
  run_dir=$(CDPATH= cd -P -- "$run_dir" && pwd -P && echo x)
  run=${run_dir%"${nl}x"}/${run##*/}
  case "$run" in *[!ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./-]*)
    rm -f -- "$run"
    die "unsafe session script path: set TMPDIR to an absolute directory containing only letters, digits, _, ., / and -" ;;
  esac
fi

here=$(pwd -P && echo x) || die "cannot resolve the current folder"
dir=${here%"${nl}x"}
# The kit's behaviour appendix reaches the worker as system-prompt text: BEHAVIOUR.md here, or
# core/BEHAVIOUR.md in the kit's own checkout. MYAGENTKIT_NO_BEHAVIOUR=1 leaves it out (an A/B).
behaviour=""
if [ "${MYAGENTKIT_NO_BEHAVIOUR:-}" != 1 ]; then
  for f in "$dir/BEHAVIOUR.md" "$dir/core/BEHAVIOUR.md"; do
    if [ -f "$f" ]; then behaviour=$f; break; fi
  done
fi
# --settings is inline JSON or a file. The tool starts in the worktree, so a relative file is
# made absolute here, against the caller's folder: resolved there, an untracked settings file
# was missing and a tracked one of the same name was loaded instead. A relative value that is
# neither is refused for the same reason. The other values name no file: the brief is
# absolute already, and --allowed-tools patterns are meant for the worker's own tree.
# JSON may start with whitespace: only a leading `{` counted, and ' {"model":"x"}' was refused
# as a file name with --worktree. JSON's four whitespace characters (space, tab, LF, CR)
# before the `{` mark it inline, and the value is passed on unchanged.
ws=" $(printf '\t\r')$nl"
lead=${settings%%[!$ws]*}
case "$settings" in
  ""|"$lead{"*|/*) ;;
  *) [ -f "$settings" ] || [ -z "$worktree" ] ||
       die "--settings is neither inline JSON nor a file here, and the worktree could hold another: $settings"
     [ ! -f "$settings" ] || settings=$dir/$settings ;;
esac
if [ -n "$worktree" ]; then
  top=$(git rev-parse --show-toplevel) || die "--worktree needs a git repository"
  dir=$top/.claude/worktrees/$name
  ! git show-ref --verify --quiet "refs/heads/worktree-$name" ||
    die "branch worktree-$name already exists and may be stale; delete it or pick another name"
  [ ! -e "$dir" ] || die "worktree path already exists: $dir"
  git worktree add -q "$dir" -b "worktree-$name" HEAD >&2 || die "git worktree add failed: $dir"
fi

# Native Windows: nothing can read the tab's pane, so the worker gets a Notification and a Stop
# hook that keep its state line in .myagentkit/workers/NAME.state for watch_workers.sh. Its
# --settings becomes NAME.settings.json beside it: the owner's settings with the two hooks
# added, theirs kept. The file is written once the name is known to be free (below).
if [ -n "$windows" ]; then
  wdir=$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)/.myagentkit/workers
  own=$settings
  settings=$(cygpath -m "$wdir/$name.settings.json") || die "cygpath cannot convert the path: $wdir"
fi
# A worker is a session of its own, never the lead's child. The lead's shell carries Claude
# Code's child-session markers, and a claude that sees CLAUDE_CODE_CHILD_SESSION skips its peer
# registration (no sessions/<pid>.json: ListAgents never lists the worker, SendMessage cannot
# reach it). tmux ignores the marker, a Windows Terminal tab does not, so both paths clear them.
# CLAUDE_CLI_BIN and CLAUDE_CODE_EXECPATH name the binary and stay.
unmark="env -u CLAUDE_CODE_CHILD_SESSION -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u CLAUDE_PID -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ATTENDED -u CLAUDE_CODE_ENTRYPOINT"

# Variadic flags come LAST and the prompt is never on this line (see the header).
cmd="claude -n $(q "$name")"
[ -n "$model" ]    && cmd="$cmd --model $(q "$model")"
[ -n "$effort" ]   && cmd="$cmd --effort $(q "$effort")"
[ -n "$settings" ] && cmd="$cmd --settings $(q "$settings")"
if [ -n "$behaviour" ]; then
  [ -z "$windows" ] || behaviour=$(cygpath -m "$behaviour") || die "cygpath cannot convert the behaviour appendix's path"
  cmd="$cmd --append-system-prompt-file $(q "$behaviour")"
fi
printf '%s\n' "spawn_worker: behaviour appendix: ${behaviour:-off}"
[ -n "$tools" ]    && cmd="$cmd --allowedTools $(q "$tools")"
# One line naming the brief by its absolute path, quoted by the same helper so a path with a
# space or an apostrophe still reads as one path. Its second sentence keeps questions out of
# the pane, where nobody may be looking. On native Windows the path is Windows' own spelling:
# Git Bash's /tmp/... is a folder the worker's tools do not know.
[ -z "$windows" ] || brief=$(cygpath -m "$brief") || die "cygpath cannot convert the brief's path: $brief"
instruction="Read $(q "$brief") and follow it. Do not ask questions in this pane: write a question into your result file and go on with what does not depend on it."

# Native Windows: no tmux, so nothing can type into the session or read its pane. The worker
# opens as a Windows Terminal tab (KIT_WT names another launcher, as for show_workers.sh) with
# the instruction as its first prompt, BEFORE the variadic flags; it is visible from the start,
# so it is not shown again, and the lead watches the tab and waits for the result file. Two
# faults, each of which left the tab with an error and no worker: a bare `bash` in a new tab
# is WSL's launcher (WindowsApps\bash.exe), so Git Bash is named by its full Windows path; and
# wt.exe splits its command line at every `;` (a new-tab separator), even inside quotes, and
# cut the instruction in two, so every `;` it is handed is escaped as `\;`. The tab's command
# ends with `exit 0`, not an exec of claude: Windows Terminal keeps a tab open, with "[process
# exited with code 1]", when its command ends nonzero, as claude does when close_worker.sh ends
# it. A name a running session already has is refused, as tmux refuses a second session.
# Native Windows (Git for Windows' sh, MSYS2, Cygwin): no tmux; a worker is a Windows Terminal
# tab running `claude -n NAME` (spawn_worker.sh). sessions NAME prints, on one line, the process
# id of each Claude Code process whose arguments hold `-n NAME`: a claude.exe, or a node.exe
# running Claude Code's cli.js (an npm install of `claude`). The command line Win32_Process
# gives is split as Windows splits it (CommandLineToArgvW's rules), so `-n w1` inside a quoted
# prompt is part of the prompt, never the name: read as words, it closed the wrong worker.
# KIT_PS names another lister (the kit's tests), printing "<pid> <command line>" lines as this
# one does. A command line Windows does not show (another user's process) names nothing. A
# lister that fails prints its words instead and returns 2.
if python3 -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python3
elif python -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python
else kit_python="py -3"; fi   # unquoted at every use
sessions() {
  out=$(${KIT_PS:-powershell.exe -NoProfile -NonInteractive -Command} \
    "Get-CimInstance Win32_Process -Filter \"Name='claude.exe' or Name='node.exe'\" | ForEach-Object { \"\$(\$_.ProcessId) \$(\$_.CommandLine)\" }" \
    2>&1) || { printf '%s' "$out"; return 2; }
  printf '%s\n' "$out" | $kit_python -I -c 'if 1:
    import ntpath, sys
    def split(line):
        # CommandLineToArgvW: 2n backslashes and a quote are n and a toggle, 2n+1 are n and a
        # literal quote, "" inside quotes is a quote; any other backslash is itself.
        args, cur, have, quoted, i = [], [], False, False, 0
        while i < len(line):
            c = line[i]
            if c == "\\":
                n = len(line[i:]) - len(line[i:].lstrip("\\"))
                i += n
                if line[i:i + 1] == "\"":
                    cur.append("\\" * (n // 2))
                    if n % 2:
                        cur.append("\"")
                        i += 1
                else:
                    cur.append("\\" * n)
                have = True
            elif c == "\"":
                if quoted and line[i + 1:i + 2] == "\"":
                    cur.append("\"")
                    i += 1
                else:
                    quoted = not quoted
                have, i = True, i + 1
            elif c in " \t" and not quoted:
                if have:
                    args.append("".join(cur))
                cur, have, i = [], False, i + 1
            else:
                cur.append(c)
                have, i = True, i + 1
        if have:
            args.append("".join(cur))
        return args
    pids = []
    for line in sys.stdin.read().replace("\r", "").split("\n"):
        pid, _, command = line.strip().partition(" ")
        argv = split(command)
        if not pid.isdigit() or not argv:
            continue
        exe = ntpath.basename(argv[0]).lower()
        if exe == "claude.exe" or exe == "claude":
            rest = argv[1:]
        elif exe in ("node.exe", "node") and len(argv) > 1 and \
                argv[1].replace("\\", "/").lower().split("/")[-3:] == ["@anthropic-ai", "claude-code", "cli.js"]:
            rest = argv[2:]
        else:
            continue
        if any(a in ("-n", "--name") and b == sys.argv[1] for a, b in zip(rest, rest[1:])):
            pids.append(pid)
    sys.stdout.write(" ".join(pids))' "$1"
}
if [ -n "$windows" ]; then
  running=$(sessions "$name") || die "cannot list the Claude Code sessions to check the name '$name': $running"
  [ -z "$running" ] || die "a Claude Code session named '$name' already runs (process $running)"
  # The hook: `waiting permission|question TIME ID` on a Notification asking for input,
  # `idle TIME ID` on Stop. Python is the interpreter chosen
  # above by running it, as .claude/hooks/py.sh chooses for the project's hooks.
  hook=$kit_python' -I -c '$(q 'import json, os, sys, tempfile, time
e = json.loads(sys.stdin.buffer.read() or b"{}")
m = str(e.get("message", "")).lower()
s = {"permission_prompt": "waiting permission", "elicitation_dialog": "waiting question"}.get(e.get("notification_type"), "")
if "notification_type" not in e:
    s = "waiting question" if "question" in m else "waiting permission" if "permission" in m or "approval" in m else ""
s = "idle" if e.get("hook_event_name") == "Stop" else s
if s:
    d, b = os.path.split(sys.argv[1])
    f = tempfile.NamedTemporaryFile(mode="w", dir=d, prefix=b + ".", delete=False, newline="")
    try:
        with f:
            f.write(s + time.strftime(" %Y-%m-%dT%H:%M:%S") + " " + str(time.time_ns()) + chr(10))
        os.replace(f.name, sys.argv[1])
    finally:
        if os.path.exists(f.name): os.unlink(f.name)')' '$(q "$(cygpath -m "$wdir/$name.state")")
  mkdir -p -- "$wdir" && rm -f -- "$wdir/$name".state* "$wdir/$name".watch-* || die "cannot prepare $wdir"
  { case $own in "") echo '{}' ;; "$lead{"*) printf '%s' "$own" ;; *) cat -- "$own" ;; esac; } |
    $kit_python -I -c 'if 1:
    import json, sys
    d = json.loads(sys.stdin.buffer.read())
    h = d.setdefault("hooks", {})
    for e in ("Notification", "Stop"):
        h.setdefault(e, []).append({"hooks": [{"type": "command", "command": sys.argv[1]}]})
    print(json.dumps(d, indent=2))' "$hook" >"$wdir/$name.settings.json" ||
    die "cannot add the worker's hooks to its --settings (not a JSON object?): $own"
  wt=${KIT_WT:-wt.exe}
  command -v "$wt" >/dev/null || die "Windows Terminal ($wt) is not on PATH; start the worker by hand: $cmd"
  bash=$(command -v bash) || die "bash is not on PATH"
  bash=$(cygpath -w "$bash") || die "cygpath cannot convert the path of bash: $bash"
  semi() { printf '%s' "$1" | sed 's/;/\\;/g'; }
  # wt.exe also drops every double quote it is handed: inline --settings JSON reached claude
  # as {permissions:{defaultMode:auto}}, claude refused it, and the tab closed before anyone
  # saw why. So the tab's command goes into a script the tab runs and deletes, and only paths
  # pass through wt.exe. A claude that ends within ten seconds of its own start, whatever its
  # status, failed to start: the tab then waits for Enter, so its error stays on screen.
  tab=$(mktemp) || die "cannot write the tab's script"
  printf '%s\n' 'rm -f -- "$0"' "cd $(q "$dir") || exit 1" \
    "t=\$(date +%s); $unmark claude $(q "$instruction") ${cmd#claude }; s=\$?; [ \$((\$(date +%s) - t)) -gt 10 ] || { echo \"claude ended at once (exit \$s); press Enter to close\"; read -r _; }" \
    'exit 0' > "$tab" || die "cannot write the tab's script: $tab"
  "$wt" -w 0 new-tab --title "$(semi "$name")" "$(semi "$bash")" -l "$(semi "$(cygpath -w "$tab")")" ||
    { rm -f -- "$tab"; die "$wt could not open a tab for '$name'"; }
  # The lead can message a worker and hear when it stops (SendMessage notify_when_idle) only
  # when Claude Code registers it as a peer: sessions/<pid>.json in its config folder. A tab
  # that inherited the lead's child-session markers was not registered (2026-10-08; the tab's
  # script now clears them): one that stopped on a usage limit waited unseen for hours. So the
  # spawn waits up to 30 s for the process and its registration, fails when no process starts
  # (the tab shows why), and says so when it is not registered.
  i=0; pids=""
  while [ "$i" -lt 30 ]; do
    pids=$(sessions "$name") || pids=""
    [ -z "$pids" ] || break
    i=$((i + 1)); sleep 1
  done
  [ -n "$pids" ] || die "no Claude Code session named '$name' started within 30 s; its tab shows why"
  reg=${CLAUDE_CONFIG_DIR:-$HOME/.claude}/sessions
  peer=""
  # The listing is taken again on every round: a worker that ended meanwhile did not start.
  while :; do
    pids=$(sessions "$name") || pids=""
    [ -n "$pids" ] || die "the Claude Code session '$name' ended right after it started; its tab shows why"
    for pid in $pids; do [ ! -f "$reg/$pid.json" ] || peer=$pid; done
    [ -z "$peer" ] && [ "$i" -lt 30 ] || break
    i=$((i + 1)); sleep 1
  done
  printf '%s\n' "spawn_worker: '$name' started with $brief in a Windows Terminal tab; watch it there"
  if [ -n "$peer" ]; then
    printf '%s\n' "spawn_worker: '$name' is a peer session (process $peer): ListAgents lists it; subscribe once with SendMessage notify_when_idle"
  else
    printf '%s\n' "spawn_worker: WARNING: '$name' (process $pids) is not registered as a peer session (unusual: a spawned worker normally registers): ListAgents does not list it, SendMessage cannot reach it, and no notice comes when it stops on a question, a usage limit or an error. Look at its tab after every wait and every limit reset; its result file is the only other signal"
  fi
  printf '%s\n' "spawn_worker: the result file its brief names is the done signal; once you decide the session is finished, close it: scripts/close_worker.sh $name"
  exit 0
fi

# `cd` first: tmux hands new sessions the PWD of whichever client last created one, and
# the tool exits with "the current working directory was deleted" when that folder (a
# removed worktree, say) is gone, whatever -c says.
# The reserved script removes itself; tmux receives two plain words for its default shell.
printf '%s\n' 'rm -f -- "$0"' "cd $(q "$dir") && exec $unmark $cmd" > "$run" || { rm -f -- "$run"; die "cannot write the session's script: $run"; }
# Transfer ownership before tmux can accept; an interrupted parent must not delete it.
launch_run=$run; run=""
tmux new-session -d -s "$name" -c "$dir" -x 200 -y 50 "sh $launch_run" || { rm -f -- "$launch_run" || :; die "tmux could not start '$name'"; }

# Wait for the input line: the TUI shows its prompt arrow at the start of a line once ready
# (v2.1.285 follows the arrow with a NO-BREAK space, so the match is on the arrow alone)
# or its mode hint in the status bar. A dialog (the trust dialog) or an exit is checked
# FIRST, by the watcher's own rules: the trust dialog's option line also starts with the arrow.
# Bounded: 60 seconds, then report. A watcher that is missing or fails (any exit but 0) stops
# the spawn with one line: without it nothing checks for a dialog before the brief is typed,
# and a missing file's shell error never matched `watch_workers:`. The session stays open.
i=0
while :; do
  rc=0; state=$(sh "$kit/watch_workers.sh" --once "$name" 2>&1) || rc=$?
  case ${state%%"$nl"*} in
    *"WAITING: "*"folder-trust"*)
      printf '%s\n' "$state" >&2
      die "session '$name' is waiting in the trust dialog; open the folder once by hand (tmux attach -t $name)" ;;
    *"WAITING: "*)
      printf '%s\n' "$state" >&2
      die "session '$name' is waiting on a person before its brief was typed (tmux attach -t $name)" ;;
    *"GONE: "*) die "session '$name' exited before its input line showed" ;;
    *watch_workers:*) die "cannot check session '$name': $state" ;;
  esac
  [ "$rc" -eq 0 ] || die "cannot check session '$name': the watcher exited $rc: $state"
  pane=$(tmux capture-pane -p -t "$name" 2>/dev/null || true)
  case "$pane" in
    *"
❯"*|*"shift+tab to cycle"*|*"for shortcuts"*) break ;;
  esac
  i=$((i + 1))
  [ "$i" -lt 60 ] || die "session '$name' did not show its input line within 60 s (tmux attach -t $name)"
  sleep 1
done

# The instruction, typed as one line.
tmux send-keys -t "$name" -l "$instruction"

# Submit only once the line has landed: an Enter sent while the TUI is still receiving
# input is swallowed and the line sits unsent at the prompt (seen on the first run of this
# script). Fast input may show as the placeholder "[Pasted text", so both count. The END of
# the line is what must have landed, and the TUI wraps a long line at a blank: blanks and
# line ends are squeezed to one space before the match.
# Then confirm the prompt line emptied; if not, press Enter once more.
landed() { tmux capture-pane -p -t "$name" -J | tr -s ' \n' '  ' | grep -qF -e "does not depend on it." -e "[Pasted text"; }
i=0
until landed; do
  i=$((i + 1)); [ "$i" -lt 30 ] || die "the instruction did not appear in session '$name' (tmux attach -t $name)"
  sleep 1
done
sleep 1
tmux send-keys -t "$name" Enter
sleep 3
if tmux capture-pane -p -t "$name" -J | grep -qE '^❯.*(\[Pasted text|and follow it\.)'; then
  tmux send-keys -t "$name" Enter
fi
printf '%s\n' "spawn_worker: '$name' started with $brief (tmux attach -t $name to watch)"
# The session does not end when its task does: a pilot worker wrote its result file and sat
# idle for 40 minutes until killed by hand, and the idle notice also fires on every park on a
# background job. A committed `Kind: completed` result file is the end signal, and closing
# is the lead's job.
printf '%s\n' "spawn_worker: once you decide the session is finished (no next task fits what it holds, or it is idle past the cache lifetime), close it: scripts/close_worker.sh $name"
if [ -n "$batch" ]; then
  printf '%s\n' "spawn_worker: --batch: not shown. Once every worker of this batch is started, show them together in one window: scripts/show_workers.sh NAME1 NAME2 ..."
else
  sh "$kit/show_workers.sh" "$name" || printf '%s\n' "spawn_worker: '$name' was not shown and runs anyway; attach by hand: tmux attach -t $name"
fi
printf '%s\n' "spawn_worker: watch it, as a background command: scripts/watch_workers.sh --result $name=PATH $name (PATH: the result file its brief names)"
