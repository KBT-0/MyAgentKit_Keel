#!/usr/bin/env sh
# Show worker sessions: ONE terminal window, one tab per named tmux session.
#
# Usage: show_workers.sh [--print] NAME [NAME...]
#   --print  print the exact command it would run, and run nothing.
#
# Why: a worker session nobody can see can sit behind a permission prompt, the folder-trust
# dialog or a question for as long as nobody looks. spawn_worker.sh calls this for every
# session it starts; a lead that starts several with --batch calls it once with all their
# names, so they open together instead of one window at a time.
#
# What it does, in order (nothing opens unless every step before it passed):
#   - Refuses a session name outside [A-Za-z0-9_-], by name: the name crosses into a Windows
#     command line or an AppleScript string, where `;` starts another Windows Terminal
#     subcommand and a quote ends a string. tmux itself accepts more.
#   - Refuses, by name, a session that does not exist (exact match, `-t =NAME`).
#   - Skips a session that already has a client attached, with a line: running it twice never
#     opens a second tab.
#   - Opens the rest, by the first backend that fits:
#       WSL + Windows Terminal: `wt.exe -w kit-<repository folder> new-tab ...`, one tab per
#         session in a window named after the project, so a later call adds its tabs to the
#         same window. Run from the drive's root: from a WSL path wt.exe warns about a UNC
#         working directory. KIT_WT names the launcher instead of the wt.exe found on PATH or
#         under /mnt/c/Users; the kit's tests point it at a stub, because under WSL any file
#         named *.exe is handed to Windows, and a test double of that name opened dialogs.
#       macOS: iTerm2 (when the lead runs in it, or it is installed and the lead does not run
#         in Terminal.app): a new window with one tab per session. Terminal.app: one WINDOW
#         per session, because adding a tab there needs accessibility permission.
#       anything else: opens nothing and prints `attach by hand: tmux attach -t NAME`.
#   - Proves it: a session counts as shown only once `tmux list-clients` lists a client for
#     it within 8 seconds; for any other it prints the attach line. Every launch is bounded
#     (5 seconds). Closing a tab detaches; the session keeps running.
# Exit status: 1 for a refused or missing session (nothing opened), 0 otherwise, including
# when no terminal could be opened (the lines say so).
set -eu

say() { printf 'show_workers: %s\n' "$1" | LC_ALL=C tr '\001-\011\013-\037\177' '?'; }
die() { say "$1" >&2; exit 1; }
# Quote one value for a POSIX shell, as spawn_worker.sh does.
q() { set -- "$(printf '%sx' "$1" | sed "s/'/'\\\\''/g")"; printf "'%s'" "${1%x}"; }

print=""
[ "${1-}" != --print ] || { print=1; shift; }
[ $# -ge 1 ] || { sed -n '2,5p' "$0"; exit 2; }
for n in "$@"; do
  case $n in
    ""|*[!A-Za-z0-9_-]*) die "refused session name '$n': only letters, digits, - and _ are opened here (it would cross into a Windows command line or an AppleScript string); attach by hand" ;;
  esac
done
command -v tmux >/dev/null || die "tmux is not installed"
missing=""
for n in "$@"; do tmux has-session -t "=$n" 2>/dev/null || missing="$missing $n"; done
[ -z "$missing" ] || die "no tmux session named:$missing; nothing opened"

show=""
for n in "$@"; do
  case " $show " in *" $n "*) continue ;; esac
  if [ -n "$(tmux list-clients -t "=$n" 2>/dev/null)" ]; then
    say "$n already has a terminal attached; not opened again"
  else
    show="$show $n"
  fi
done
[ -n "$show" ] || exit 0

by_hand() {
  [ -z "${1-}" ] || say "$1"
  for n in $show; do say "attach by hand: tmux attach -t $n"; done
  exit 0
}

# The window is named after the project's main checkout, also from a worktree.
top=$(git rev-parse --git-common-dir 2>/dev/null) && top=$(CDPATH= cd -P -- "$top/.." && pwd -P) ||
  top=$(pwd -P)
window=kit-$(printf '%s' "${top##*/}" | LC_ALL=C tr -c 'A-Za-z0-9._-' '_')
tmux_bin=$(command -v tmux)
case $tmux_bin in
  /*) case $tmux_bin in *[!A-Za-z0-9._/-]*) by_hand "tmux's path has characters this script does not pass on: $tmux_bin" ;; esac ;;
  *) by_hand "tmux is not a program file here ($tmux_bin)" ;;
esac

# Run DIR CMD... detached from our output, bounded; or print it with --print.
launch() {
  dir=$1; shift
  if [ -n "$print" ]; then
    line="cd $(q "$dir") &&"
    for a in "$@"; do line="$line $(q "$a")"; done
    printf '%s\n' "$line" | LC_ALL=C tr '\001-\011\013-\037\177' '?'
    exit 0
  fi
  log=$(mktemp) || by_hand "cannot make a temporary file"
  ( CDPATH= cd -- "$dir" && exec "$@" ) >"$log" 2>&1 </dev/null &
  pid=$!
  ( sleep 5; kill "$pid" ) >/dev/null 2>&1 </dev/null &
  dog=$!
  rc=0; wait "$pid" || rc=$?
  kill "$dog" 2>/dev/null || true
  out=$(head -n 1 "$log"); rm -f "$log"
  case $rc:$out in
    0:*) ;;
    *"Exec format error"*) by_hand "$1 failed with \"Exec format error\": WSL interop is down (wsl --shutdown from Windows restarts it)" ;;
    143:*) by_hand "$1 did not return within 5 s (on macOS it may be asking to allow automation)" ;;
    *) by_hand "$1 failed (exit $rc): $out" ;;
  esac
}

wsl_wt() {
  wt=${KIT_WT:-$(command -v wt.exe 2>/dev/null || true)}
  if [ -z "$wt" ]; then
    for f in /mnt/c/Users/*/AppData/Local/Microsoft/WindowsApps/wt.exe; do
      [ -e "$f" ] || continue
      [ -z "$wt" ] || by_hand "several wt.exe found under /mnt/c/Users; put the right one on PATH"
      wt=$f
    done
  fi
  [ -n "$wt" ] || by_hand "WSL without Windows Terminal (no wt.exe on PATH or under /mnt/c/Users)"
  case $WSL_DISTRO_NAME in
    *[!A-Za-z0-9._-]*) by_hand "the WSL distribution's name has characters this script does not pass on" ;;
  esac
  case $wt in /mnt/?/*) dir=${wt%"${wt#/mnt/?}"} ;; *) dir=${wt%/*} ;; esac
  set -- "$wt" -w "$window"
  sep=""
  for n in $show; do
    [ -z "$sep" ] || set -- "$@" "$sep"
    sep=";"
    # --exec: no login shell in between, whose syntax (zsh expands `=NAME`) is not ours.
    set -- "$@" new-tab --title "$n" wsl.exe -d "$WSL_DISTRO_NAME" --exec "$tmux_bin" attach -t "=$n"
  done
  launch "$dir" "$@"
}

# One AppleScript string: the command a new shell runs, with " and \ escaped.
as_cmd() { printf '"%s"' "$(printf '%s' "exec $(q "$tmux_bin") attach -t $(q "=$1")" | sed 's/[\\"]/\\&/g')"; }

iterm() {
  set -- osascript -e 'tell application "iTerm"' -e 'activate' -e 'set w to (create window with default profile)'
  first=1
  for n in $show; do
    [ -n "$first" ] || set -- "$@" -e 'tell w to create tab with default profile'
    first=""
    set -- "$@" -e "tell current session of w to write text $(as_cmd "$n")"
  done
  launch / "$@" -e 'end tell'
}

terminal() {
  say "Terminal.app opens one window per session: adding a tab needs accessibility permission"
  set -- osascript -e 'tell application "Terminal"' -e 'activate'
  for n in $show; do set -- "$@" -e "do script $(as_cmd "$n")"; done
  launch / "$@" -e 'end tell'
}

if [ -n "${WSL_DISTRO_NAME-}" ]; then
  wsl_wt
elif [ "$(uname -s)" = Darwin ] && command -v osascript >/dev/null; then
  case ${TERM_PROGRAM-} in
    iTerm.app) iterm ;;
    Apple_Terminal) terminal ;;
    *) if [ -d /Applications/iTerm.app ]; then iterm; else terminal; fi ;;
  esac
else
  by_hand "no supported terminal here (WSL with Windows Terminal, or macOS)"
fi

# Shown only once a client is attached: the launcher returning proves nothing.
pending=$show; i=0
while :; do
  left=""
  for n in $pending; do [ -n "$(tmux list-clients -t "=$n" 2>/dev/null)" ] || left="$left $n"; done
  pending=$left
  [ -n "$pending" ] && [ "$i" -lt 8 ] || break
  i=$((i + 1)); sleep 1
done
for n in $show; do
  case " $pending " in
    *" $n "*) say "no terminal attached to $n within 8 s; attach by hand: tmux attach -t $n" ;;
    *) say "shown: $n" ;;
  esac
done
