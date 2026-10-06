#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Watch worker sessions; return as soon as one is GONE, WAITING on a person, has a result.
#
# Usage: watch_workers.sh [--interval S] [--max-minutes M] [--context-warn P]
#                         [--result NAME=PATH]... NAME [NAME...]
#        watch_workers.sh --once [the same options] NAME [NAME...]
#        watch_workers.sh --list-patterns
# It returns at the first report: while work remains, start it again after every report but
# DONE and GONE, and after its window ends.
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
# when nothing waits (spawn_worker.sh uses it). Exit 2 is a usage error. Exit 3: a pane of
# a session that exists could not be read, or tmux could not say whether it exists
# (`watch_workers: NAME: capture failed: ...` on stderr), or a committed result could not be
# read (`... could not read the committed result ...`), or a report could not be written
# (`... could not write its report ...`); that is an observation failure, never "nothing
# waiting", and the run prints no result or context report. With several sessions, the GONE
# and WAITING lines print first, then the result and context lines. Run once per spawn, the
# watcher stopped watching at the first PROGRESS, QUESTIONS or CONTEXT report (see above).
#
# A session that is neither gone nor waiting is checked for two more things:
# - --result NAME=PATH names its result file (docs/HANDOFF.md). Once the file is committed
#   (it is in HEAD of the tree that holds it) and that tree is clean, its head is read from
#   the committed blob, never the working file, and the blob must be a regular file:
#   `Kind: completed` is DONE; blocked, handoff and progress are reported as BLOCKED, HANDOFF
#   and PROGRESS (not done); a missing or malformed head is MALFORMED (not done). A file with
#   questions under "## Open questions for ..." is QUESTIONS with their text, first. Each
#   committed version of the file is reported once.
# - The `context` rule in waiting_patterns.txt finds the context figure (<used>/<window>) in
#   the pane's status line, the last line with two or more ` │ ` separators; a figure anywhere
#   else in the pane is output, not the status. Past --context-warn percent (default 50) it
#   is CONTEXT, once per session. A status line without the figure, or none, is CONTEXT once too, and the figure is
#   never guessed; --once skips that note, as spawn_worker.sh runs it before the status line
#   is drawn.
# The once-markers are user options of the tmux session, so they end with it. Every report
# exits 0; its first line is `watch_workers: KIND: NAME, ...`.
set -eu

say() { printf '%s\n' "$1" | LC_ALL=C tr '\001-\011\013-\037\177' '?'; }
die() { say "watch_workers: $1" >&2; exit 2; }
case $0 in */*) here=${0%/*} ;; *) here=. ;; esac
patterns=$here/waiting_patterns.txt
[ -r "$patterns" ] || die "cannot read $patterns"
ctx_re=""
while read -r kind status version where re; do
  if [ "$kind" = context ]; then ctx_re=$re; fi
done <"$patterns"
[ -n "$ctx_re" ] || die "no context rule in $patterns"
nl='
'
# The mappings are joined by newlines, so a newline inside one argument split it in two:
# `w1=docs/a<LF>w1=docs/b.md` announced docs/b.md. No control byte or newline is accepted.
plain() {
  [ "$(printf '%sx' "$1" | LC_ALL=C tr -d '\001-\037\177')" = "${1}x" ] ||
    die "a session name or result path contains a control character or a newline; it is not printed"
}

interval=45; max=110; warn=50; once=""; results=""
while [ $# -gt 0 ]; do
  case $1 in
    --interval|--max-minutes|--context-warn)
      [ $# -ge 2 ] || die "$1 needs a value"
      case $2 in ""|*[!0-9]*) die "$1 takes a whole number: $2" ;; esac
      case $1 in --interval) interval=$2 ;; --max-minutes) max=$2 ;; *) warn=$2 ;; esac
      shift 2 ;;
    --result)
      [ $# -ge 2 ] || die "$1 needs a value"
      plain "$2"
      case $2 in ?*=?*) ;; *) die "--result takes NAME=PATH: $2" ;; esac
      results=$results$nl$2; shift 2 ;;
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
[ $# -ge 1 ] || { sed -n '3,10p' "$0"; exit 2; }
[ "$interval" -ge 10 ] || die "--interval $interval is below the floor of 10 seconds"
for n in "$@"; do plain "$n"; done
# A name given twice is watched once: its second pass reported what the first had queued.
seen=$nl
for n in "$@"; do case $seen in *"$nl$n$nl"*) ;; *) seen=$seen$n$nl ;; esac; done
set -f; IFS=$nl; set -- $seen; unset IFS; set +f
command -v tmux >/dev/null || die "tmux is not installed"
win=$(mktemp) || die "cannot make a temporary file"
qs=$(mktemp) || { rm -f "$win"; die "cannot make a temporary file"; }
body=$(mktemp) || { rm -f "$win" "$qs"; die "cannot make a temporary file"; }
err=$(mktemp) || { rm -f "$win" "$qs" "$body"; die "cannot make a temporary file"; }
out=$(mktemp) || { rm -f "$win" "$qs" "$body" "$err"; die "cannot make a temporary file"; }
trap 'rm -f "$win" "$qs" "$body" "$err" "$out"' EXIT

# Each line cut to 200 BYTES in every locale (`cut -c` counted bytes in some), then a
# UTF-8 character the cut split is dropped whole: the output stays UTF-8 when the input was.
cutb() {
  c=$(printf '\200-\277')
  LC_ALL=C cut -b1-200 | LC_ALL=C sed -e "s/[$(printf '\300-\337')]\$//" \
    -e "s/[$(printf '\340-\357')][$c]\{0,1\}\$//" -e "s/[$(printf '\360-\367')][$c]\{0,2\}\$//"
}
# A once-marker: a user option of the tmux session. setmark only queues it: the queue is
# stored after the run's reports are printed, and dropped with them by a run that exits 3.
# mark reads the queue first, then the stored option.
mark() {
  m=""
  while IFS='	' read -r pn pk pv; do
    if [ "$pn" = "$1" ] && [ "$pk" = "$2" ]; then m=$pv; fi
  done <<EOF
$pending
EOF
  if [ -n "$m" ]; then printf '%s\n' "$m"; else tmux show-options -qv -t "=$1:" "@kit_watch_$2" 2>/dev/null || true; fi
}
setmark() { pending="$pending$1	$2	$3$nl"; }

# has NAME: 0 the session exists, 1 tmux says it or its server does not, 2 tmux could not
# tell (its words in $why): only the second is proof of absence. The wordings are those of
# has() in close_worker.sh; keep the two lists identical (a test compares them).
has() {
  why=$(tmux has-session -t "=$1" 2>&1) && return 0
  case $why in
    *"can't find session"*|*"session not found"*|*"no server running"*|*"no sessions"*) return 1 ;;
    *"error connecting to "*"(No such file or directory)"*) return 1 ;;
  esac
  return 2
}

# Print GONE, FAILED (the pane could not be read, or tmux could not say whether the session
# exists; tmux's error is in $err), or "WAITING KIND STATUS VERSION", or nothing; leaves the
# pane's last 15 non-empty lines, control bytes removed, in $win.
classify() {
  s=0; has "$1" || s=$?
  [ "$s" -ne 1 ] || { echo GONE; return 0; }
  [ "$s" -eq 0 ] || { printf '%s\n' "$why" >"$err"; echo FAILED; return 0; }
  # A session that ended during the capture is GONE, not an observation failure.
  tmux capture-pane -p -J -t "=$1:" >"$win" 2>"$err" || {
    s=0; has "$1" || s=$?
    [ "$s" -ne 2 ] || printf '%s\n' "$why" >"$err"
    if [ "$s" -eq 1 ]; then echo GONE; else echo FAILED; fi
    return 0; }
  LC_ALL=C tr -d '\001-\011\013-\037\177' <"$win" | LC_ALL=C sed 's/[[:space:]]*$//' |
    grep -v '^$' | tail -n 15 >"$qs" || true
  cat "$qs" >"$win"
  last=$(tail -n 1 "$win")
  hits=" "
  while read -r kind status version where re; do
    case $kind in ""|\#*) continue ;; esac
    case $where in last|near) ;; *) continue ;; esac
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
  if [ "$1" = FAILED ]; then
    say "watch_workers: $name: capture failed: $(tr '\n' ' ' <"$err")" >&2
    return 0
  fi
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
  tail -n 12 "$win" | cutb | while IFS= read -r line; do say "  | $line"; done
  say "  look at it: scripts/show_workers.sh $name   (or: tmux attach -t $name)"
}

# Line $1 of file $2, control bytes and trailing blanks removed.
hl() { LC_ALL=C sed -n "$1p" "$2" | LC_ALL=C tr -d '\001-\011\013-\037\177' | LC_ALL=C sed 's/[[:space:]]*$//'; }

# Report NAME's result file and return 0 when it is committed, its tree is clean and this
# version was not reported yet; return 1 otherwise, 2 when the report could not be written.
# The once-marker is queued only after the blob was read and its report written: a failed
# read or write is done again on the next run.
result() {
  report_result "$1" || return $?
  setmark "$1" result "$blob"
}

report_result() {
  # No `case` inside $( ): bash 3.2, macOS's sh, cannot parse its pattern's `)` there.
  f=""
  while IFS= read -r r; do
    case $r in "$1="*) f=${r#"$1="} ;; esac
  done <<EOF
$results
EOF
  [ -n "$f" ] || return 1
  case $f in */*) d=${f%/*} ;; *) d=. ;; esac
  # The commit is what is trusted: the head is read from the committed blob, never the working
  # file, which a committed symlink pointed outside the tree and a later write could change
  # after the clean-tree check. The marker is that blob's id. HEAD is resolved once, and must
  # still be that commit after the clean-tree check: else entry and check saw different commits.
  head=$(git -C "$d" rev-parse -q --verify HEAD 2>/dev/null) || return 1
  entry=$(git -C "$d" ls-tree "$head" -- "./${f##*/}" 2>/dev/null) || return 1
  [ -n "$entry" ] || return 1
  mode=${entry%% *}; blob=${entry#* }; blob=${blob#* }; blob=${blob%%"	"*}
  dirty=$(git -C "$d" status --porcelain 2>/dev/null) || return 1
  [ -z "$dirty" ] || return 1
  [ "$(git -C "$d" rev-parse -q --verify HEAD 2>/dev/null)" = "$head" ] || return 1
  [ "$(mark "$1" result)" != "$blob" ] || return 1
  case $mode in 100644|100755) ;; *)
    say "watch_workers: MALFORMED: $1, result file $f: it is not a regular file in HEAD (mode $mode); not done" || return 2
    return ;;
  esac
  if ! git -C "$d" cat-file blob "$blob" >"$body" 2>"$err"; then
    say "watch_workers: $1: could not read the committed result $blob: $(tr '\n' ' ' <"$err")" >&2
    failed=1; return 1
  fi
  k=$(hl 1 "$body"); t=$(hl 2 "$body"); a=$(hl 3 "$body"); r=$(hl 4 "$body")
  case $a in "Attempt: "*) a=${a#Attempt: } ;; *) a=x ;; esac
  bad=""
  case $k in "Kind: completed"|"Kind: blocked"|"Kind: handoff"|"Kind: progress") ;;
    *) bad="line 1 is not 'Kind: completed|blocked|handoff|progress'" ;; esac
  case $t in "Task: "?*) ;; *) bad=${bad:-"line 2 is not 'Task: <id>'"} ;; esac
  case $a in ""|*[!0-9]*) bad=${bad:-"line 3 is not 'Attempt: <n>'"} ;; esac
  case $r in "Remaining: "?*) ;; *) bad=${bad:-"line 4 is not 'Remaining: <what is left>'"} ;; esac
  if [ -n "$bad" ]; then
    say "watch_workers: MALFORMED: $1, result file $f: $bad; not done" || return 2
    return
  fi
  k=${k#Kind: }
  what=$(printf 'task %s, attempt %s, remaining: %s\n' "${t#Task: }" "$a" "${r#Remaining: }" | cutb)
  # The questions: each numbered line under the heading and up to six lines after it.
  LC_ALL=C awk '
    /^## / { inq = (index($0, "## Open questions for ") == 1)
             if (inq && owner == "") { owner = substr($0, 23); print "O" owner }
             next }
    !inq || !NF { next }
    /^[0-9]+[.)] / { q++; n = 0; print "Q" $0; next }
    q { if (++n <= 6) print "L" $0; else if (n == 7) print "L   [more in the result file]" }
  ' "$body" | LC_ALL=C tr -d '\001-\011\013-\037\177' >"$qs"
  nq=$(grep -c '^Q' "$qs" || true)
  if [ "$nq" -gt 0 ]; then
    owner=$(sed -n 's/^O//p' "$qs" | cutb)
    qw=questions; [ "$nq" -gt 1 ] || qw=question
    say "watch_workers: QUESTIONS: $1, $nq $qw for $owner (Kind: $k, $what)" || return 2
    sed -n 's/^[QL]//p' "$qs" | cutb | while IFS= read -r line; do say "  | $line" || exit 1; done || return 2
    say "  ask them now, one at a time; each line is cut at 200 bytes, the full text is in $f" || return 2
    return
  fi
  case $k in completed) k=DONE ;; blocked) k=BLOCKED ;; handoff) k=HANDOFF ;; *) k=PROGRESS ;; esac
  say "watch_workers: $k: $1, $what (result file $f)" || return 2
}

# Report the context figure in NAME's status line ($win) when it is past the warning line,
# or (not with --once) when there is none; once per session. Return 1 when nothing is said,
# 2 when the report could not be written (and no marker is queued).
context() {
  fig=$(CTX_RE=$ctx_re LC_ALL=C awk -v warn="$warn" '
    function num(s) { return substr(s, 1, length(s) - 1) * (s ~ /M$/ ? 1000000 : 1000) }
    gsub(/ │ /, "&") >= 2 {
      bar = 1; tok = ""; for (i = 1; i <= NF; i++) if ($i ~ ENVIRON["CTX_RE"]) tok = $i }
    END { if (tok == "") { print (bar ? "unparsable" : "absent"); exit }
          split(tok, p, "/"); u = num(p[1]); w = num(p[2])
          if (w <= 0) { print "unparsable"; exit }
          printf "%s %d %s\n", (u * 100 > warn * w ? "over" : "under"), u * 100 / w, tok }
  ' "$win") || fig=""
  set -- "$1" ${fig:-absent}
  [ "$2" != under ] || return 1
  said=$(mark "$1" context)
  [ "$said" != over ] || return 1
  if [ "$2" = over ]; then
    say "watch_workers: CONTEXT: $1, $4 is $3% of its context window, past the $warn% warning line (finish, compact or hand off: read its Remaining: line)" || return 2
    setmark "$1" context over
    return 0
  fi
  [ -z "$once" ] && [ -z "$said" ] || return 1
  say "watch_workers: CONTEXT: $1, no context figure: its status line is $2 (said once; nothing is guessed)" || return 2
  setmark "$1" context noted
}

end=$(( $(date +%s) + max * 60 ))
while :; do
  found="" failed="" pending=""
  : >"$out"
  for n in "$@"; do
    st=$(classify "$n")
    if [ "$st" = FAILED ]; then report "$n" FAILED; failed=1
    elif [ -n "$st" ]; then report "$n" $st; found=1
    else
      # A report that could not be written ends the run like a failed capture; w stays x
      # when the buffer cannot even be opened.
      w=x
      { w=0; result "$n" || w=$?; [ "$w" -ne 1 ] || { w=0; context "$n" || w=$?; }; } >>"$out" || :
      case $w in
        0) found=1 ;;
        1) ;;
        *) say "watch_workers: $n: could not write its report: the report buffer failed" >&2; failed=1 ;;
      esac
    fi
  done
  # A run that failed (exit 3) is rerun: its result and context reports are not printed and
  # their once-markers not stored, so the rerun reports them.
  [ -z "$failed" ] || exit 3
  cat "$out"
  printf '%s' "$pending" | while IFS='	' read -r n k v; do
    tmux set-option -t "=$n:" "@kit_watch_$k" "$v" >/dev/null 2>&1 || true
  done
  [ -z "$found" ] || exit 0
  [ -z "$once" ] || exit 0
  [ $(( $(date +%s) + interval )) -le "$end" ] ||
    { say "watch_workers: nothing was waiting on a person within $max minute(s): $*"; exit 0; }
  sleep "$interval"
done
