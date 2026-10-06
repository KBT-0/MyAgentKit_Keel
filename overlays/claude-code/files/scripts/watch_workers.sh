#!/usr/bin/env sh
# Watch worker sessions; return as soon as one is GONE or WAITING on a person.
#
# Usage: watch_workers.sh [--interval S] [--max-minutes M] NAME [NAME...]
#        watch_workers.sh --once NAME [NAME...]
#        watch_workers.sh --list-patterns
#
# The lead runs it as a BACKGROUND command: its exit re-invokes the lead, which then tells the
# owner what the session waits on. A spawned session can block on a permission prompt, the
# folder-trust dialog or a question, and the idle notice does not fire for a session that
# waits inside a dialog: it hangs where nobody looks.
#
# Every --interval seconds (default 45, at least 10) it reads each session's pane with
# `tmux capture-pane`, which costs the worker nothing, and matches its bottom against
# waiting_patterns.txt beside this script (the rules and why they look at the last line only
# are explained there). It prints one block per session that is GONE or WAITING, with the
# last pane lines for a WAITING one, and exits 0. Nothing waiting after --max-minutes
# (default 110) prints one line saying so and exits 0. --once checks once and prints nothing
# when nothing waits (spawn_worker.sh uses it). Exit 2 is a usage error.
set -eu

say() { printf '%s\n' "$1" | LC_ALL=C tr '\001-\011\013-\037\177' '?'; }
die() { say "watch_workers: $1" >&2; exit 2; }
case $0 in */*) here=${0%/*} ;; *) here=. ;; esac
patterns=$here/waiting_patterns.txt
[ -r "$patterns" ] || die "cannot read $patterns"

interval=45; max=110; once=""
while [ $# -gt 0 ]; do
  case $1 in
    --interval|--max-minutes)
      [ $# -ge 2 ] || die "$1 needs a value"
      case $2 in ""|*[!0-9]*) die "$1 takes a whole number: $2" ;; esac
      if [ "$1" = --interval ]; then interval=$2; else max=$2; fi
      shift 2 ;;
    --once) once=1; shift ;;
    --list-patterns)
      say "KIND STATUS VERSION WHERE ERE ($patterns)"
      grep -v '^#' "$patterns" | grep . | while IFS= read -r line; do say "$line"; done
      exit 0 ;;
    --) shift; break ;;
    -*) die "unknown option: $1" ;;
    *) break ;;
  esac
done
[ $# -ge 1 ] || { sed -n '2,6p' "$0"; exit 2; }
[ "$interval" -ge 10 ] || die "--interval $interval is below the floor of 10 seconds"
for n in "$@"; do
  [ "$(printf '%sx' "$n" | LC_ALL=C tr -d '\001-\037\177')" = "${n}x" ] ||
    die "a session name contains a control character; it is not printed"
done
command -v tmux >/dev/null || die "tmux is not installed"
win=$(mktemp) || die "cannot make a temporary file"
trap 'rm -f "$win"' EXIT

# Print GONE, or "WAITING KIND STATUS VERSION", or nothing; leaves the pane's last 15
# non-empty lines, control bytes removed, in $win.
classify() {
  tmux has-session -t "=$1" 2>/dev/null || { echo GONE; return 0; }
  tmux capture-pane -p -J -t "=$1:" 2>/dev/null | LC_ALL=C tr -d '\001-\011\013-\037\177' |
    LC_ALL=C sed 's/[[:space:]]*$//' | grep -v '^$' | tail -n 15 >"$win" || true
  last=$(tail -n 1 "$win")
  hits=" "
  while read -r kind status version where re; do
    case $kind in ""|\#*) continue ;; esac
    if [ "$where" = last ]; then printf '%s\n' "$last"; else cat "$win"; fi |
      LC_ALL=C grep -qE -- "$re" && hits="$hits$kind:$where:$status:$version "
  done <"$patterns"
  for h in $hits; do
    case $h in *:last:*) ;; *) continue ;; esac
    k=${h%%:*}
    case $hits in *" $k:near:"*) ;; *) continue ;; esac
    s=UNVERIFIED
    case $hits in *" $k:last:VERIFIED:"*) case $hits in *" $k:near:VERIFIED:"*) s=VERIFIED ;; esac ;; esac
    echo "WAITING $k $s ${h##*:}"
    return 0
  done
}

report() {
  name=$1; shift
  if [ "$1" = GONE ]; then
    say "watch_workers: GONE: $name (the tmux session no longer exists: read its result file)"
    return 0
  fi
  case $2 in
    trust) what="the folder-trust dialog" ;;
    permission) what="a permission prompt" ;;
    question) what="a question" ;;
    *) what="a choice ($2)" ;;
  esac
  say "watch_workers: WAITING: $name, on $what (rule $3, Claude Code $4)"
  say "  the last lines of its pane:"
  tail -n 12 "$win" | cut -c1-200 | while IFS= read -r line; do say "  | $line"; done
  say "  look at it: scripts/show_workers.sh $name   (or: tmux attach -t $name)"
}

end=$(( $(date +%s) + max * 60 ))
while :; do
  found=""
  for n in "$@"; do
    st=$(classify "$n")
    [ -z "$st" ] || { report "$n" $st; found=1; }
  done
  [ -z "$found" ] || exit 0
  [ -z "$once" ] || exit 0
  [ $(( $(date +%s) + interval )) -le "$end" ] ||
    { say "watch_workers: nothing was waiting on a person within $max minute(s): $*"; exit 0; }
  sleep "$interval"
done
