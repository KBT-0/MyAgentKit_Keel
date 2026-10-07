#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Open a SEPARATE Claude Code worker session in tmux and hand it a brief file. On native
# Windows (Git for Windows' sh, MSYS2, Cygwin), which has no tmux, it opens as a Windows
# Terminal tab instead (see "Native Windows" below), and what follows about showing,
# watching and closing a tmux session does not apply there.
#
# Usage: spawn_worker.sh NAME BRIEF_FILE [--model M] [--settings JSON_OR_FILE]
#                        [--allowed-tools LIST] [--worktree] [--effort LEVEL] [--batch]
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
# The lead then subscribes once with SendMessage `notify_when_idle` and reads the result
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
#   - Every value that goes into the session's shell command, and the brief path, passes
#     through `q`: a value with an apostrophe (a --settings JSON string, a name) otherwise
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

[ $# -ge 2 ] || { sed -n '3,14p' "$0"; exit 2; }
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
ctl "brief path" "$brief"
nl='
'
{ [ -f "$brief" ] && [ -r "$brief" ]; } || die "brief file not found or not readable: $brief"
case "$brief" in */*) brief_dir=${brief%/*}/ ;; *) brief_dir=. ;; esac
# Every path handed on is physical (`pwd -P`): a plain `pwd` printed the logical path when the
# caller exported a matching PWD and the physical one otherwise, so the same brief was named
# /var/... by one caller and /private/var/... by another on macOS.
brief_dir=$(CDPATH= cd -P -- "$brief_dir" && pwd -P && echo x) || die "cannot resolve the brief's folder: $brief"
brief=${brief_dir%"${nl}x"}/${brief##*/}
ctl "brief path" "$brief"
case $(uname -s 2>/dev/null) in MINGW*|MSYS*|CYGWIN*) windows=1 ;; *) windows="" ;; esac
[ -n "$windows" ] || command -v tmux >/dev/null || die "tmux is not installed"
command -v claude >/dev/null || die "claude is not on PATH"

model=""; settings=""; tools=""; worktree=""; effort=""; batch=""
case $0 in */*) kit=${0%/*} ;; *) kit=. ;; esac
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

[ -n "$windows" ] || ! tmux has-session -t "=$name" 2>/dev/null || die "tmux session '$name' already exists"

here=$(pwd -P && echo x) || die "cannot resolve the current folder"
dir=${here%"${nl}x"}
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

# Variadic flags come LAST and the prompt is never on this line (see the header).
cmd="claude -n $(q "$name")"
[ -n "$model" ]    && cmd="$cmd --model $(q "$model")"
[ -n "$effort" ]   && cmd="$cmd --effort $(q "$effort")"
[ -n "$settings" ] && cmd="$cmd --settings $(q "$settings")"
[ -n "$tools" ]    && cmd="$cmd --allowedTools $(q "$tools")"
# One line naming the brief by its absolute path, quoted by the same helper so a path with a
# space or an apostrophe still reads as one path. Its second sentence keeps questions out of
# the pane, where nobody may be looking.
instruction="Read $(q "$brief") and follow it. Do not ask questions in this pane: write a question into your result file and go on with what does not depend on it."

# Native Windows: no tmux, so nothing can type into the session or read its pane. The worker
# opens as a Windows Terminal tab (KIT_WT names another launcher, as for show_workers.sh) with
# the instruction as its first prompt, BEFORE the variadic flags; it is visible from the start,
# so it is not shown again, and the lead watches the tab and waits for the result file. Two
# faults, each of which left the tab with an error and no worker: a bare `bash` in a new tab
# is WSL's launcher (WindowsApps\bash.exe), so Git Bash is named by its full Windows path; and
# wt.exe splits its command line at every `;` (a new-tab separator), even inside quotes, and
# cut the instruction in two, so every `;` it is handed is escaped as `\;`.
if [ -n "$windows" ]; then
  wt=${KIT_WT:-wt.exe}
  command -v "$wt" >/dev/null || die "Windows Terminal ($wt) is not on PATH; start the worker by hand: $cmd"
  bash=$(command -v bash) || die "bash is not on PATH"
  bash=$(cygpath -w "$bash") || die "cygpath cannot convert the path of bash: $bash"
  semi() { printf '%s' "$1" | sed 's/;/\\;/g'; }
  "$wt" -w 0 new-tab --title "$(semi "$name")" "$(semi "$bash")" -lc \
    "$(semi "cd $(q "$dir") && exec claude $(q "$instruction") ${cmd#claude }")" ||
    die "$wt could not open a tab for '$name'"
  printf '%s\n' "spawn_worker: '$name' started with $brief in a Windows Terminal tab; watch it there"
  printf '%s\n' "spawn_worker: the result file its brief names is the done signal; close the tab once you decide the session is finished"
  exit 0
fi

# `cd` first: tmux hands new sessions the PWD of whichever client last created one, and
# the tool exits with "the current working directory was deleted" when that folder (a
# removed worktree, say) is gone, whatever -c says.
tmux new-session -d -s "$name" -c "$dir" -x 200 -y 50 "cd $(q "$dir") && exec $cmd"

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
