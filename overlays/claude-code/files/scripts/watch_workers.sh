#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Watch worker sessions; return as soon as one is GONE, WAITING on a person, stopped by its
# usage LIMIT, or has a result.
#
# Usage: watch_workers.sh [--interval S] [--max-minutes M] [--context-warn NNNk|NN%]
#                         [--result NAME=PATH]... NAME [NAME...]
#        watch_workers.sh --once [the same options] NAME [NAME...]
#        watch_workers.sh --limit NAME
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
# last pane lines for a WAITING one and the result report of a GONE one, and exits 0. Nothing waiting after --max-minutes
# (default 55; 0 checks once, then prints the line) prints one line saying so and exits 0.
# The 55 minutes stay under the one-hour prompt cache the kit pins (promptCacheTtl "1h" in
# .claude/settings.json), so a quiet window's wake reads the lead's cache instead of rewriting
# it; they also fit the two-hour limit on unattended background commands below. The 45 s and
# the 10 s floor are the owner's choice, not measurements; so are the display limits (the last 15
# pane lines, 200 bytes a line, six question lines). A local interactive lead has no limit on a
# background command; an unattended one (`-p`, the Agent SDK, CI) stops it after 30 minutes
# unless started with a `timeout` (at most two hours): pass one there (Claude Code tools
# reference, "Time limit for background commands"). --once checks once and prints nothing
# when nothing waits (spawn_worker.sh uses it). Exit 2 is a usage error, a name with no record
# in this checkout's .myagentkit/workers and no tmux session too (run it from the checkout
# the worker was spawned in: the line spawn_worker.sh prints cds there), unless its --result
# file holds a ready result, which is then reported as any result. Exit 3: a pane of
# a session that exists could not be read, or tmux could not say whether it exists
# (`watch_workers: NAME: capture failed: ...` on stderr), or a committed result could not be
# read (`... could not read the committed result ...`), or a report could not be written
# (`... could not write its report ...`), or, on Windows, a state file is invalid or unreadable
# (`watch_workers: NAME: state unreadable: ...`, the message names the file: delete it); that is an observation failure, never "nothing
# waiting", and the run prints no result or context report. With several sessions, the GONE
# and WAITING lines print first, then the result and context lines. Run once per spawn, the
# watcher stopped watching at the first PROGRESS, QUESTIONS or CONTEXT report (see above).
#
# A session that is not waiting is checked for two more things (a GONE one for its result
# only):
# - --result NAME=PATH names its result file (docs/HANDOFF.md). Once the file is committed
#   (it is in HEAD of the tree that holds it) and that tree is clean, its head is read from
#   the committed blob, never the working file, and the blob must be a regular file:
#   `Kind: completed` is DONE; blocked, handoff and progress are reported as BLOCKED, HANDOFF
#   and PROGRESS (not done); a missing or malformed head is MALFORMED (not done). A file with
#   questions under "## Open questions for ..." is QUESTIONS with their text, first. Each
#   committed version of the file is reported once. A file not in HEAD (the kit's default
#   RESULT-NAME.md, never committed: docs/HANDOFF_KIT.md) is read from the working file instead,
#   once per content, when this run published it: a regular file, not a symlink, newer than
#   .myagentkit/workers/NAME.result-path (spawn_worker.sh writes it at every spawn and resume,
#   so an older file is an earlier run's), its last non-blank line the supervisor's ready
#   marker `<!-- codex-worker: ready -->` (without it the worker is still writing).
# - The `context` rule in waiting_patterns.txt finds the context figure (<used>/<window>) in
#   the pane's status line: the line right under the input box's bottom rule (a line of `─`
#   only), which is the second or third line from the bottom (the mode line may follow), with
#   two or more ` │ ` separators. A figure anywhere else in the pane, a quoted status line too,
#   is output, not the status. Past the warning line it is CONTEXT, once per session. The
#   line is the smaller of an absolute count (default 200k, the lead's band: docs/WORKFLOW.md,
#   "Worker cost", rule 8) and a share of the window (default 50%): on a 1M window 50% is 500k,
#   past the band's 400k ceiling, and context rot grows with tokens, not with the share
#   (Anthropic, "Context windows"). `--context-warn NNNk` sets the count, `--context-warn NN%`
#   (or a bare NN) the share. A status line without the figure, or none, is a CONTEXT note
#   once too, and the figure is never guessed. The note is printed but ends no watch: it
#   reaches the lead with the next report or the window-end line (a lead wake per worker for
#   a status line the kit does not ship cost too much). --once skips it, as spawn_worker.sh
#   runs it before the status line is drawn.
#   Worktree hook snapshots use the same override; a percentage needs a pane window figure.
#   Without an override their bands come from context_size.py, once per band per session.
# The once-markers are user options of the tmux session, so they end with it, but for the
# result's, kept in .myagentkit/workers/NAME.watch-result too. Every report
# exits 0; its first line is `watch_workers: KIND: NAME, ...`.
#
# Native Windows: a worker is a Windows Terminal tab whose pane nothing can read. The
# Notification and Stop hooks spawn_worker.sh gives it write one line to
# .myagentkit/workers/NAME.state at the top of this checkout (or this folder outside git):
# `waiting permission|question TIME ID [context_tokens=N]` or `idle TIME ID [context_tokens=N]`.
# The optional count is the last request's context, zero after a compaction boundary;
# context_size.py supplies its yellow/red/ceiling label (owner decision 23, 2026-10-16).
# A waiting line is WAITING, before the
# result file is read. Legacy `waiting input` means idle, with no state event; once per worker
# the watcher says its hook is from an older kit and asks for a re-spawn.
# The Stop hook writes an idle line at every turn end: when the result file says nothing new
# it is IDLE, the worker's session stopped: a question in the tab, a usage limit or an error,
# or a park on its own background job (it goes on by itself when the job ends). Each event
# (the whole line, id included) is reported once; the once-markers are NAME.watch-* files
# beside it, which spawn_worker.sh removes. After the result and before the idle line, GONE:
# the supervisor's exit record NAME.exit there (its first line, once per line), or, with none,
# its NAME.live record whose lock dropped (a closed tab or a kill; the lock is checked by
# codex_worker.py's own gone()). A record older than NAME.result-path is an earlier run's.
# There is no pane context figure there, and no tmux is needed. An invalid state file is an
# observation failure (exit 3); an absent or zero-byte one means no signal yet. A session name is letters, digits, - and _, not starting with -
# (spawn_worker.sh's rule): anything else is a usage error (exit 2).
#
# A Claude Code background session (NAME.host bg, on every host) has no pane and needs no tmux:
# its row in `claude agents --json --all` (list_workers.sh --row: by NAME.id) is read instead.
# A file wins over any state: first QUESTION-NAME.md in the worker's folder (.claude/worktrees/NAME of the main checkout or of this one,
# else this checkout: where the supervisor reads it), published (its ready marker) and newer than
# NAME.result-path (`QUESTION: NAME, a decision waits in PATH`, once per content), then the result
# as above. Then blocked is WAITING with its waitingFor (`no reason given` when the row names
# none: docs/research/worker-orchestration-spike-posix.md); done with a process still idling is
# IDLE, a turn end the lead re-arms after, as the tab path's; stopped, failed, done with no
# process and absent (no row, as after `claude rm`) are GONE; working says nothing. A published
# question, completed or handoff result of this run ended the session by design (the supervisor
# stops it on those alone, 60 s later; a Codex worker 10 s): no IDLE or GONE then. Nor within a minute of the spawn or resume
# (NAME.id or NAME.result-path that new): the spike saw no row at first, and a resumed row reads
# done until it wakes. Each state (with what it waits for) is said once, in the file
# NAME.watch-bg, cleared when the session works again. A worker spawned on the other host (native
# Windows or WSL: their lists are disjoint) is ELSEWHERE, once. A list that cannot be read, or two
# rows of the name and no NAME.id, is exit 3 (`watch_workers: NAME: could not list ...`).
#
# LIMIT: a worker its usage limit stopped sits idle until the reset, and no result, state hook or
# row says why (2026-10-22: two sat ~1 h, their rows blocked). The `limit` rule in
# waiting_patterns.txt finds it: on tmux in the pane's last line above the input box but for
# turn-summary lines (`✻ ... for ...`); on a background or a Windows Terminal tab worker in its
# transcript, ${CLAUDE_CONFIG_DIR:-~/.claude}/projects/*/ID*.jsonl (ID its NAME.id, the sessionId
# a tab spawn recorded), whose last user or assistant entry is the API-error entry Claude Code
# writes then. It is said once per stop while the session lives (a background row working,
# blocked, or done with its process; an ended one is GONE as before), and then the row's state
# and a tab's IDLE say nothing while it lasts; a message or a resume adds a user entry, and that
# ends it. --limit NAME checks that alone, with no once-marker and no row: it prints the same
# line and exits 0, else exits 1 and prints nothing (spawn_worker.sh's printed until-loop runs it).
set -eu

say() { printf '%s\n' "$1" | LC_ALL=C tr '\001-\011\013-\037\177' '?'; }
die() { say "watch_workers: $1" >&2; exit 2; }
# newer A B: A was modified after B, test's -nt, which POSIX sh lacks (SC3013). A or B missing:
# false, so `! newer B A` is test's `! A -ot B` for an A that exists.
newer() {
  case $1 in -*) set -- "./$1" "$2" ;; esac
  [ -n "$(find "$1" -prune -newer "$2" 2>/dev/null)" ]
}
# Git for Windows' dirname handles both separators, including mixed paths such as D:/p\scripts\x.sh.
case $0 in *'\'*) here=$(dirname -- "$0") ;; */*) here=${0%/*} ;; *) here=. ;; esac
patterns=$here/waiting_patterns.txt
[ -r "$patterns" ] || die "cannot read $patterns"
ctx_re="" limit_re=""
while read -r kind status version where re; do
  if [ "$kind" = context ]; then ctx_re=$re; fi
  if [ "$kind" = limit ]; then limit_re=$re; fi
done <"$patterns"
[ -n "$ctx_re" ] || die "no context rule in $patterns"
[ -n "$limit_re" ] || die "no limit rule in $patterns"
nl='
'
# The mappings are joined by newlines, so a newline inside one argument split it in two:
# `w1=docs/a<LF>w1=docs/b.md` announced docs/b.md. No control byte or newline is accepted.
plain() {
  [ "$(printf '%sx' "$1" | LC_ALL=C tr -d '\001-\037\177')" = "${1}x" ] ||
    die "a session name or result path contains a control character or a newline; it is not printed"
}

interval=45; max=55; warn_abs=""; warn_pct=50; warn_set=""; once=""; results=""; limit_only=""
while [ $# -gt 0 ]; do
  case $1 in
    --context-warn)
      [ $# -ge 2 ] || die "$1 needs a value"
      v=${2%[k%]}
      case $v in ""|*[!0-9]*) die "$1 takes NNNk (tokens) or NN% (of the window): $2" ;; esac
      v=${v#"${v%%[!0]*}"}; v=${v:-0}  # decimal: shell arithmetic reads a leading 0 as octal
      case $2 in *k) warn_abs=$((v * 1000)); warn_set=abs ;; *) warn_pct=$v; warn_set=pct ;; esac
      shift 2 ;;
    --interval|--max-minutes)
      [ $# -ge 2 ] || die "$1 needs a value"
      case $2 in ""|*[!0-9]*) die "$1 takes a whole number: $2" ;; esac
      v=${2#"${2%%[!0]*}"}; v=${v:-0}  # decimal, as above
      case $1 in --interval) interval=$v ;; *) max=$v ;; esac
      shift 2 ;;
    --result)
      [ $# -ge 2 ] || die "$1 needs a value"
      plain "$2"
      case $2 in ?*=?*) ;; *) die "--result takes NAME=PATH: $2" ;; esac
      results=$results$nl$2; shift 2 ;;
    --once) once=1; shift ;;
    --limit) limit_only=1; shift ;;
    --list-patterns)
      say "KIND STATUS VERSION WHERE ERE ($patterns)"
      grep -v '^#' "$patterns" | grep . | while IFS= read -r line; do say "$line"; done
      exit 0 ;;
    --) shift; break ;;
    -*) die "unknown option: $1" ;;
    *) break ;;
  esac
done
[ $# -ge 1 ] || { sed -n '3,12p' "$0"; exit 2; }
[ -z "$limit_only" ] || [ $# -eq 1 ] || die "--limit takes one name"
[ "$interval" -ge 10 ] || die "--interval $interval is below the floor of 10 seconds"
for n in "$@"; do
  plain "$n"
  case $n in
    ''|-*|*[!ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-]*)
      die "refused the session name: use letters, digits, - and _, not starting with -" ;;
  esac
done
# A name given twice is watched once: its second pass reported what the first had queued.
seen=$nl
for n in "$@"; do case $seen in *"$nl$n$nl"*) ;; *) seen=$seen$n$nl ;; esac; done
# shellcheck disable=SC2086 # one name per line: split on newlines, globbing off
{ set -f; IFS=$nl; set -- $seen; unset IFS; set +f; }
# Native Windows (Git for Windows' sh, MSYS2, Cygwin) has no tmux: a worker is a Windows Terminal
# tab, and the hooks spawn_worker.sh gives it keep its state line in $wdir/NAME.state.
case $(uname -s 2>/dev/null) in MINGW*|MSYS*|CYGWIN*) windows=1 ;; *) windows="" ;; esac
wdir=$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)/.myagentkit/workers
# isbg NAME: whether NAME runs as a Claude Code background session (NAME.host bg); no tmux then.
isbg() { [ "$(cat -- "$wdir/$1.host" 2>/dev/null)" = bg ]; }
# norec NAME: this checkout holds no record of NAME (spawn_worker.sh writes NAME.result-path and
# NAME.host at every spawn, in the checkout it ran from).
norec() { for x in state pid result-path host id live exit; do [ ! -e "$wdir/$1.$x" ] || return 1; done; }
# lone NAME: NAME has no record here, no tmux session and a ready --result (in $lonely, below).
lonely=$nl
lone() { case $lonely in *"$nl$1$nl"*) return 0 ;; esac; return 1; }
tmuxok=""
if [ -n "$windows" ]; then :
elif command -v tmux >/dev/null; then tmuxok=1
elif [ -z "$limit_only" ]; then for n in "$@"; do isbg "$n" || norec "$n" || die "tmux is not installed"; done
fi
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
# A once-marker: a user option of the tmux session (on Windows the file $wdir/NAME.watch-KEY).
# The result marker is that file too, when $wdir exists: it outlives the session, so a result
# reported while it lived is not reported again once it is GONE (#294). setmark only queues
# it: the queue is stored after the run's reports are printed, and dropped with them by a run
# that exits 3. mark reads only the stored marker: a name is watched once per run, so its
# queue is never read.
mark() {
  if [ -z "$windows" ] && ! isbg "$1"; then
    v=$(tmux show-options -qv -t "=$1:" "@kit_watch_$2" 2>/dev/null) || v=""
    [ -z "$v" ] || { printf '%s\n' "$v"; return 0; }
  fi
  cat -- "$wdir/$1.watch-$2" 2>/dev/null || true
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
  [ -z "$windows" ] || return 0
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
    printf '%s\n' "WAITING $k $s ${h##*:}"
    return 0
  done
  t=$(pane_limit) || return 0
  t=$(printf '%s\n' "$t" | cksum)  # the once-marker: tmux options may not keep the text's bytes
  [ -n "$limit_only" ] || [ "$(mark "$1" limit)" != "$t" ] || return 0
  echo LIMIT
}

# The pane's last line above the input box ($win; over the second rule from the bottom) that is
# no turn summary (`✻ Crunched for 2m · done 8:16 PM`, as idle.txt shows after a turn), when the
# limit rule matches it.
pane_limit() {
  LC_ALL=C awk '{ l[NR] = $0 }
    END { for (i = NR; i > 1; i--) if (l[i] ~ /^ *(─)+$/ && ++r == 2) {
            for (i--; i > 0 && l[i] ~ /^ *✻ .* for /; i--) ;
            if (i > 0) print l[i]; exit } }' "$win" |
    LC_ALL=C grep -E -- "$limit_re"
}

# limited ID: the transcript of session ID ends on a usage-limit stop (LIMIT above): its text in
# $lim, the entry's checksum, the once-marker, in $limkey.
limited() {
  case $1 in ''|*[!0-9a-f-]*) return 1 ;; esac
  for t in "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/projects/*/"$1"*.jsonl; do
    [ -f "$t" ] || continue
    e=$(tail -n 50 -- "$t" 2>/dev/null | LC_ALL=C grep -E '"type":"(user|assistant)"' |
      LC_ALL=C grep -vF '"isSidechain":true' | tail -n 1) || continue
    case $e in *'"isApiErrorMessage":true'*) ;; *) continue ;; esac
    lim=$(printf '%s\n' "$e" | LC_ALL=C sed -n 's/.*"text":"\([^"]*\)".*/\1/p')
    printf '%s\n' "$lim" | LC_ALL=C grep -qE -- "$limit_re" || continue
    limkey=$(printf '%s\n' "$e" | cksum)
    return 0
  done
  return 1
}

# limit_report NAME: say LIMIT once per stop of the session NAME.id names. Return 0 when said,
# 1 when it is not stopped so, 2 when the report could not be written, 4 when this stop was said.
limit_report() {
  limited "$(cat -- "$wdir/$1.id" 2>/dev/null)" || return 1
  [ "$(mark "$1" limit)" != "$limkey" ] || return 4
  limit_say "$1" "$lim" || return 2
  setmark "$1" limit "$limkey"
}

limit_say() {
  say "watch_workers: LIMIT: $1, its session stopped on a usage limit (You${2#*You}): resume it after the reset (SendMessage 'limit reset, continue', or spawn_worker.sh --resume)"
}

# Only a validated numeric field reaches the companion hook. Its constants remain the
# single source of the band; an older installation without it still shows the raw count.
context_label() {
  case $1 in *' context_tokens='*) tokens=${1##* context_tokens=} ;; *) return 0 ;; esac
  case $tokens in ''|*[!0-9]*) return 0 ;; esac
  word=$(sh "$here/../.claude/hooks/py.sh" "$here/../.claude/hooks/context_size.py" --band "$tokens" </dev/null 2>/dev/null) || word=""
  printf '; context %s tokens%s' "$tokens" "${word:+, $word}"
}
# level_of LABEL FLOOR: the band level of a context label (2 yellow, 3 red, 4 ceiling), else
# FLOOR. One definition for the snapshot's eligibility and the once-per-level marker.
level_of() {
  case $1 in *', yellow') level=2 ;; *', red') level=3 ;; *', ceiling') level=4 ;; *) level=$2 ;; esac
}
pane_context() {
  [ -f "$wdir/$1.state" ] || return 0
  saved=$(cat -- "$wdir/$1.state" 2>/dev/null) || return 0
  context_label "$saved"
}

# Return 2 when the report could not be written.
report() {
  name=$1; shift
  if [ "$1" = FAILED ]; then
    say "watch_workers: $name: capture failed: $(tr '\n' ' ' <"$err")" >&2
    return 0
  fi
  if [ "$1" = GONE ]; then
    say "watch_workers: GONE: $name (the tmux session no longer exists: read its result file)" || return 2
    return 0
  fi
  if [ "$1" = LIMIT ]; then
    t=$(pane_limit) || t=""
    limit_say "$name" "$t" || return 2
    setmark "$name" limit "$(printf '%s\n' "$t" | cksum)"
    return 0
  fi
  case $2 in
    trust) what="the folder-trust dialog" ;;
    permission) what="a permission prompt" ;;
    question) what="a question" ;;
    *) what="a choice ($2)" ;;
  esac
  say "watch_workers: WAITING: $name, on $what (rule $3, Claude Code $4)$(pane_context "$name")" || return 2
  say "  the last lines of its pane:" || return 2
  # The writing command last, so the pipeline's status is the write's.
  tail -n 12 "$win" | cutb | sed 's/^/  | /' | LC_ALL=C tr '\001-\011\013-\037\177' '?' || return 2
  say "  look at it: scripts/show_workers.sh $name   (or: tmux attach -t $name)" || return 2
}

# Line $1 of file $2, a leading UTF-8 BOM (codex_worker.py reads past it too, #169), control
# bytes and trailing blanks removed.
bom=$(printf '\357\273\277')
hl() { LC_ALL=C sed -n "$1p" "$2" | LC_ALL=C sed "s/^$bom//" | LC_ALL=C tr -d '\001-\011\013-\037\177' | LC_ALL=C sed 's/[[:space:]]*$//'; }
# published FILE: its last non-blank line is the supervisor's ready marker (else still being written).
published() {
  [ "$(LC_ALL=C tr -d '\r' <"$1" | LC_ALL=C sed 's/[[:space:]]*$//' | grep -v '^$' | tail -n 1)" = '<!-- codex-worker: ready -->' ]
}

# Report NAME's result file and return 0 when it is committed and its tree is clean, or it is
# not in HEAD and this run published it (the header says how), and this version was not
# reported yet; return 1 otherwise, 2 when the report could not be written.
# The once-marker is queued only after the blob was read and its report written: a failed
# read or write is done again on the next run.
result() {
  report_result "$1" || return $?
  setmark "$1" result "$blob"
}

# rfile NAME: its --result path in $f, or nothing.
rfile() {
  # No `case` inside $( ): bash 3.2, macOS's sh, cannot parse its pattern's `)` there.
  f=""
  while IFS= read -r r; do
    case $r in "$1="*) f=${r#"$1="} ;; esac
  done <<EOF
$results
EOF
}

report_result() {
  rfile "$1"
  [ -n "$f" ] || return 1
  case $f in */*) d=${f%/*} ;; *) d=. ;; esac
  # The commit is what is trusted: the head is read from the committed blob, never the working
  # file, which a committed symlink pointed outside the tree and a later write could change
  # after the clean-tree check. The marker is that blob's id. HEAD is resolved once, and must
  # still be that commit after the clean-tree check: else entry and check saw different commits.
  head=$(git -C "$d" rev-parse -q --verify HEAD 2>/dev/null) || return 1
  # A lookup that fails is an observation failure (exit 3), not an absent entry.
  if ! entry=$(git -C "$d" ls-tree "$head" -- "./${f##*/}" 2>"$err"); then
    say "watch_workers: $1: could not read the tree of $head for $f: $(tr '\n' ' ' <"$err")" >&2
    failed=1; return 1
  fi
  if [ -z "$entry" ]; then
    # Not in HEAD: the kit's default result, never committed (#167). Its bytes are copied once
    # and only the copy is read; the copy's blob id is the marker. NAME.result-path is the
    # run's start: an older file is an earlier run's. No ready marker: still being written.
    # A lone name has no run start to compare with: its explicit result path wins.
    rp=$wdir/$1.result-path
    if lone "$1"; then [ -f "$f" ] && [ ! -L "$f" ] || return 1
    else [ -f "$rp" ] && [ -f "$f" ] && [ ! -L "$f" ] && newer "$f" "$rp" || return 1; fi
    cat -- "$f" >"$body" 2>/dev/null || return 1
    published "$body" || return 1
    # Hashed as git would store it (eol and attribute filters of its path): a later commit of
    # the same content under core.autocrlf=true has this id and is not reported again.
    blob=$(git -C "$d" hash-object --path="${f##*/}" --stdin <"$body" 2>/dev/null) || return 1
    [ "$(mark "$1" result)" != "$blob" ] || return 1
  else
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
  ' "$body" | LC_ALL=C tr -d '\001-\011\013-\037\177' >"$qs" || return 2
  nq=$(grep -c '^Q' "$qs" || true)
  if [ "$nq" -gt 0 ]; then
    owner=$(sed -n 's/^O//p' "$qs" | cutb)
    qw=questions; [ "$nq" -gt 1 ] || qw=question
    say "watch_workers: QUESTIONS: $1, $nq $qw for $owner (Kind: $k, $what)" || return 2
    sed -n 's/^[QL]//p' "$qs" | cutb | sed 's/^/  | /' | LC_ALL=C tr '\001-\011\013-\037\177' '?' || return 2
    say "  ask them now, one at a time; each line is cut at 200 bytes, the full text is in $f" || return 2
    return
  fi
  case $k in completed) k=DONE ;; blocked) k=BLOCKED ;; handoff) k=HANDOFF ;; *) k=PROGRESS ;; esac
  say "watch_workers: $k: $1, $what (result file $f)" || return 2
}

# Native Windows: report NAME's state line when it starts with $2 (waiting or idle) and was not
# reported yet. Return 1 when nothing is said, 2 when the report could not be written,
# 3 when its state is unreadable or invalid.
tab() {
  if [ -z "$tab_read" ]; then
    tab_read=1; line=""; reason=""
    state=$wdir/$1.state
    [ -e "$state" ] || [ -L "$state" ] || return 1
    if [ ! -f "$state" ]; then reason="not a regular file"
    # Read the live file once. Both emptiness and content come from this byte snapshot.
    # Capture stderr first, including a shell failure to open either redirection.
    elif ! cat -- "$state" 2>"$err" >"$win"; then
      [ -e "$state" ] || return 1  # removed by a re-spawn: no signal yet
      reason=$(cat "$err"); reason=${reason:-"could not read the state file"}
    elif ! bytes=$(wc -c 2>"$err" <"$win") || ! line=$(cat -- "$win" 2>"$err"); then
      reason=$(cat "$err"); reason=${reason:-"could not read the state snapshot"}
    elif [ "$bytes" -eq 0 ]; then return 1  # an older hook truncates before it writes
    elif ! printf '%s\n' "$line" | LC_ALL=C grep -Eq '^(waiting (permission|question|input)|idle) [0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}( [0-9]+)?( context_tokens=[0-9]+)?$' ||
         [ "$(printf '%s\n' "$line" | wc -l)" -ne 1 ]; then reason="invalid state content"
    fi
    if [ -n "$reason" ]; then
      say "watch_workers: $1: state unreadable: $reason ($state; delete it to clear)" >&2
      failed=1; return 3
    fi
    case $line in "waiting input "*)
      if [ "$(mark "$1" legacy)" != noted ]; then
        say "watch_workers: $1: its state hook is from an older kit; re-spawn to install the current one" || return 2
        setmark "$1" legacy noted; found=1
      fi
      line="" ;;  # the old idle notification is no state event, never WAITING
    esac
  fi
  case $line in "$2 "*) ;; *) return 1 ;; esac
  [ "$(mark "$1" state)" != "$line" ] || return 1
  if [ "$2" = waiting ]; then
    case $line in "waiting question "*) what="a question" ;; *) what="a permission prompt" ;; esac
    say "watch_workers: WAITING: $1, on $what (its state file: $line)$(context_label "$line")" || return 2
  else
    say "watch_workers: IDLE: $1, its session stopped: a question in its tab, a usage limit or an error, or a park on its own background job (it goes on by itself when the job ends), with no new result report (its state file: $line)$(context_label "$line")" || return 2
  fi
  say "  look at it: its Windows Terminal tab, titled $1" || return 2
  setmark "$1" state "$line"
}

# A background session NAME (NAME.host bg), by its row in `claude agents --json --all`
# (list_workers.sh --row). Return 0 when something was said, 1 when nothing, 2 when the report
# could not be written, 3 when the sessions cannot be listed.
bg() {
  if ! row=$(sh "$here/list_workers.sh" --row "$1" 2>"$err"); then
    say "watch_workers: $1: could not list the background sessions: $(tr '\n' ' ' <"$err")" >&2
    failed=1; return 3
  fi
  IFS='	' read -r bstate bwait bpid _ bid _ <<EOF
$row
EOF
  key="$bstate ${bwait-}"
  if [ "$bstate" = ambiguous ]; then
    say "watch_workers: $1: no $wdir/$1.id, and several background sessions named $1 run in its folder ($bwait): stop the wrong one by its id (claude stop ID)" >&2
    failed=1; return 3
  fi
  if [ "$bstate" = elsewhere ]; then
    [ "$(mark "$1" bg)" != "$key" ] || return 1
    say "watch_workers: ELSEWHERE: $1, its background session was started on $bwait, whose session list this host cannot see: watch it there" || return 2
    setmark "$1" bg "$key"; return 0
  fi
  # The question first, then the result. A published question, or a published completed or
  # handoff result, of this run (newer than NAME.result-path) ends the session by design (the
  # supervisor stops it on those alone): no IDLE or GONE for it.
  rp=$wdir/$1.result-path; settled=""
  # The question is where the supervisor and the worker's instruction put it: the worker's folder.
  # Its worktree is in the main checkout's .claude/worktrees (both spawns), or nested in this
  # checkout by an older spawn.
  q=${wdir%/.myagentkit/workers}
  m=$(git -C "$q" worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p'); [ -n "$m" ] || m=$q
  for t in "$m/.claude/worktrees/$1" "$q/.claude/worktrees/$1"; do [ ! -d "$t" ] || { q=$t; break; }; done
  q=$q/QUESTION-$1.md
  if [ -f "$q" ] && ! newer "$rp" "$q" && published "$q"; then
    settled=1
    sum=$(cksum <"$q" 2>/dev/null) || sum=""
    if [ -n "$sum" ] && [ "$(mark "$1" question)" != "$sum" ]; then
      say "watch_workers: QUESTION: $1, a decision waits in $q: read it and answer it" || return 2
      setmark "$1" question "$sum"; return 0
    fi
  fi
  rfile "$1"
  if [ -n "$f" ] && [ -f "$f" ] && ! newer "$rp" "$f" && published "$f"; then
    case $(hl 1 "$f") in "Kind: completed"|"Kind: handoff") settled=1 ;; esac
  fi
  # Not the main loop's w: a report here returns 0, and the caller keeps w as bg() left it.
  rw=0; result "$1" || rw=$?
  [ "$rw" -eq 1 ] || return "$rw"
  # A usage-limit stop of a live session before the row's state, which says nothing while it
  # lasts; an ended session is GONE below, whatever its transcript says (LIMIT above).
  case $bstate in working|blocked|done)
    [ "$bstate:$bpid" = done:- ] || { rw=0; limit_report "$1" || rw=$?
      case $rw in 1) ;; 4) return 1 ;; *) return "$rw" ;; esac; } ;;
  esac
  case $bstate in
    working) [ -z "$(mark "$1" bg)" ] || setmark "$1" bg ""; return 1 ;;
    blocked)
      [ "$(mark "$1" bg)" != "$key" ] || return 1
      [ "$bwait" != - ] || bwait="no reason given"  # POSIX spike: blocked may name nothing
      say "watch_workers: WAITING: $1, waiting for: $bwait (background session $bid, state blocked)" || return 2
      say "  look at it: claude attach $bid   (claude agents lists every session)" || return 2
      setmark "$1" bg "$key"; return 0 ;;
    done|stopped|failed|absent) ;;
    *) return 1 ;;  # a state this kit does not know says nothing
  esac
  [ -z "$settled" ] && [ "$(mark "$1" bg)" != "$key" ] || return 1
  # The spike saw no row for the first seconds after a launch, and a resumed row reads done
  # until it wakes: a spawn or resume less than a minute old is not GONE yet.
  [ -z "$(find "$wdir/$1.id" "$rp" -mmin -1 2>/dev/null)" ] || return 1
  if [ "$bstate" = absent ]; then
    bid=$(cat -- "$wdir/$1.id" 2>/dev/null) || bid=""
    say "watch_workers: GONE: $1, its background session ${bid:-named $1} is no longer listed (claude agents --all): read its result file" || return 2
  elif [ "$bstate" = done ] && [ "$bpid" != - ]; then
    # A turn end, as the tab path's IDLE: the session lives on, and the lead re-arms the watch.
    say "watch_workers: IDLE: $1, its background session $bid is done with no new result report and its process still idles: a question in its view, a usage limit or an error, or a park on its own background job (it goes on by itself when the job ends): claude attach $bid" || return 2
  else
    say "watch_workers: GONE: $1, its background session $bid is $bstate with no new result report: read its result file" || return 2
  fi
  setmark "$1" bg "$key"
}

# ended LIVE: whether the supervisor that locked LIVE has ended, by codex_worker.py's own gone().
# No Python, or any failure, counts as not ended. The interpreters are spawn_worker.sh's.
ended() {
  for p in python3 python 'py -3'; do
    pyrc=0
    # shellcheck disable=SC2086 # py -3 splits on purpose
    $p -I -c 'import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("codex_worker", sys.argv[1])
cw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cw)
sys.exit(0 if cw.gone(Path(sys.argv[2]), 0) else 1)' "$here/codex_worker.py" "$1" </dev/null >/dev/null 2>&1 || pyrc=$?
    case $pyrc in 0) return 0 ;; 1) return 1 ;; esac  # else not found, or a Store alias: the next
  done
  return 1
}

# Native Windows: report once that NAME's supervisor ended: its exit record (its first line),
# else its .live record whose lock dropped. A record older than NAME.result-path (the run's
# start) is an earlier run's. Return 1 when nothing is said, 2 when the report could not be written.
gone_tab() {
  rp=$wdir/$1.result-path; x=$wdir/$1.exit; l=$wdir/$1.live; v=""; dropped=""
  # The lock first, as codex_worker.py --wait reads it: an exit record written between the two
  # reads is still seen below, never reported as a dropped lock.
  if [ -f "$l" ] && ! newer "$rp" "$l"; then
    v=$(cat -- "$l" 2>/dev/null) || v=""
    if [ -n "$v" ] && [ "$(mark "$1" live)" != "$v" ] && ended "$l"; then dropped=1; fi
  fi
  if [ -f "$x" ] && ! newer "$rp" "$x"; then
    e=$(LC_ALL=C sed -n 1p "$x" 2>/dev/null | LC_ALL=C tr -d '\001-\037\177')
    # Empty: being written; the next check reads it.
    [ -n "$e" ] && [ "$(mark "$1" exit)" != "$e" ] || return 1
    say "watch_workers: GONE: $1, its session ended ($e): read its result file" || return 2
    setmark "$1" exit "$e"
    return 0
  fi
  [ -n "$dropped" ] || return 1
  say "watch_workers: GONE: $1, its supervisor ended without an exit record (its tab closed or it was killed): read its result file" || return 2
  setmark "$1" live "$v"
}

# Report the context figure in NAME's status line ($win) when it is past the warning line,
# or (not with --once) when there is none; once per session. Return 1 when nothing is said,
# 2 when the report could not be written (and no marker is queued), 4 after the no-figure note.
context() {
  if [ -z "$warn_abs" ]; then
    # A project's older context_size.py (it has no KIT-OWNED line, so sync keeps it) cannot
    # answer --line, and with no Python nothing can: the built-in 200k line, never a stop (the
    # watcher died, and every tmux spawn with it; ultrareview part 7 #1). stdin is closed: the
    # older hook reads its JSON payload there and waited on a terminal.
    warn_abs=$(sh "$here/../.claude/hooks/py.sh" "$here/../.claude/hooks/context_size.py" --line </dev/null 2>/dev/null) || warn_abs=""
    case $warn_abs in ''|*[!0-9]*) warn_abs=200000 ;; esac
  fi
  fig=$(CTX_RE=$ctx_re LC_ALL=C awk -v abs="$warn_abs" -v pct="$warn_pct" '
    function num(s) { return substr(s, 1, length(s) - 1) * (s ~ /M$/ ? 1000000 : 1000) }
    { l[NR] = $0 }
    END { row = ""; tok = ""
          for (i = NR - 1; i >= NR - 2 && i > 0; i--) if (l[i] ~ /^ *(─)+$/) { row = l[i + 1]; break }
          bar = gsub(/ │ /, "&", row) >= 2
          if (bar) { n = split(row, f, " "); for (i = 1; i <= n; i++) if (f[i] ~ ENVIRON["CTX_RE"]) tok = f[i] }
          if (tok == "") { print (bar ? "unparsable" : "absent"); exit }
          split(tok, p, "/"); u = num(p[1]); w = num(p[2])
          if (w <= 0) { print "unparsable"; exit }
          line = pct * w / 100; if (abs < line) line = abs
          printf "%s %d %s %dk %d %d\n", (u > line ? "over" : "under"), u * 100 / w, tok, line / 1000, w, u }
  ' "$win") || fig=""
  # shellcheck disable=SC2086 # the figure's fields: split on purpose
  set -- "$1" ${fig:-absent}
  # A Stop/Notification snapshot can predate this turn. Consider both sources and keep
  # their highest reported band together. A percentage still needs the pane window.
  source=""; count=0; label=""
  snapshot=""; tokens=""
  if [ -f "$wdir/$1.state" ]; then snapshot=$(cat -- "$wdir/$1.state" 2>/dev/null) || snapshot=""; fi
  case $snapshot in *' context_tokens='*) tokens=${snapshot##* context_tokens=} ;; esac
  case $tokens in ''|*[!0-9]*) ;;
    *)
      label=$(context_label "$snapshot")
      level_of "$label" 0
      eligible=""
      case $warn_set in
        abs|pct) if [ -n "${6:-}" ]; then
               eligible=$(LC_ALL=C awk -v t="$tokens" -v w="$6" -v p="$warn_pct" -v a="$warn_abs" \
                 'BEGIN { line = p * w / 100; if (a < line) line = a; if (t >= line) print 1 }')
             elif [ "$warn_set" = abs ] && [ "$tokens" -ge "$warn_abs" ]; then eligible=1
             fi ;;
        *) [ "$level" -eq 0 ] || eligible=1 ;;
      esac
      if [ -n "$eligible" ]; then
        source=snapshot; count=$tokens
      fi ;;
  esac
  if [ "$2" = over ] && { [ -z "$source" ] || [ "$7" -gt "$count" ]; }; then
    source=pane; count=$7
    label=$(context_label " context_tokens=$count")
  fi
  if [ -n "$source" ]; then
    level_of "$label" 1
    said=$(mark "$1" state-context)
    case $said in 1|2|3|4) [ "$said" -lt "$level" ] || return 1 ;; esac
    if [ "$source" = snapshot ]; then
      say "watch_workers: CONTEXT: $1$label (its state hook; docs/WORKFLOW.md, \"Worker cost\", rule 8)" || return 2
    else
      say "watch_workers: CONTEXT: $1, $4 is $3% of its context window, past its $5 warning line (finish, compact or hand off: read its Remaining: line; docs/WORKFLOW.md, \"Worker cost\", rule 8)" || return 2
      setmark "$1" context over
    fi
    setmark "$1" state-context "$level"
    return 0
  fi
  [ "$2" != under ] || return 1
  said=$(mark "$1" context)
  [ "$said" != over ] || return 1
  [ -z "$once" ] && [ -z "$said" ] || return 1
  say "watch_workers: CONTEXT: $1, no context figure: its status line is $2 (said once; nothing is guessed)" || return 2
  setmark "$1" context noted
  return 4
}

if [ -n "$limit_only" ]; then
  if isbg "$1" || [ -n "$windows" ]; then limited "$(cat -- "$wdir/$1.id" 2>/dev/null)" || exit 1; t=$lim
  elif [ -n "$tmuxok" ] && [ "$(classify "$1")" = LIMIT ]; then t=$(pane_limit)
  else exit 1; fi
  limit_say "$1" "$t"; exit 0
fi

# A name with no record here and no session tmux knows was spawned from another checkout (its
# records are in that one's .myagentkit/workers). A ready --result file of it is read and
# reported all the same. Else it is a usage error on every host: without tmux it said nothing,
# forever (2026-10-21), and tmux's "no session" proves nothing for a bg worker, never a tmux one.
for n in "$@"; do
  norec "$n" || continue
  s=1; [ -z "$tmuxok" ] || { s=0; has "$n" || s=$?; }
  [ "$s" -eq 1 ] || continue
  rfile "$n"
  if [ -n "$f" ] && [ -f "$f" ] && published "$f"; then lonely=$lonely$n$nl; continue; fi
  at=""
  while IFS= read -r t; do
    [ -n "$t" ] && { [ -e "$t/.myagentkit/workers/$n.result-path" ] || [ -e "$t/.myagentkit/workers/$n.host" ]; } &&
      at=$t && break
  done <<EOF
$(git worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p')
EOF
  die "$n: no record of it in $wdir and no session of that name: run the watch from the checkout it was spawned in (${at:-the one whose .myagentkit/workers holds $n.result-path}), or pass --result $n=PATH of its ready result"
done

end=$(( $(date +%s) + max * 60 ))
while :; do
  found="" failed="" pending=""
  : >"$out"
  for n in "$@"; do
    tab_read=""; line=""
    st=""; isbg "$n" || { [ -z "$tmuxok" ] && lone "$n"; } || st=$(classify "$n")
    if [ "$st" = FAILED ]; then report "$n" FAILED; failed=1
    elif [ -n "$st" ]; then
      found=1
      # A finished worker's session ends a minute after its result (Codex: ten seconds), often before the next
      # poll: a GONE session's result is read too (#294).
      if [ "$st" = GONE ]; then
        w=x
        { w=0; result "$n" || w=$?; } >>"$out" || :
        case $w in
          0|1) ;;
          *) say "watch_workers: $n: could not write its report: the report buffer failed" >&2; failed=1 ;;
        esac
      fi
      # shellcheck disable=SC2086 # the state's fields: split on purpose
      report "$n" $st || { say "watch_workers: $n: could not write its report to stdout" >&2; failed=1; }
    else
      # A report that could not be written ends the run like a failed capture; w stays x
      # when the buffer cannot even be opened.
      w=x
      # On Windows: the state line's WAITING first, then the result, then GONE, then its IDLE;
      # the optional API context count is part of either state report.
      { w=1; if isbg "$n"; then w=0; bg "$n" || w=$?; elif lone "$n"; then w=0; result "$n" || w=$?; else
        [ -z "$windows" ] || { w=0; tab "$n" waiting || w=$?; }
        [ "$w" -ne 1 ] || { w=0; result "$n" || w=$?; }
        [ -z "$windows" ] || [ "$w" -ne 1 ] || { w=0; gone_tab "$n" || w=$?; }
        # 4, this stop said before: no IDLE for it either.
        [ -z "$windows" ] || [ "$w" -ne 1 ] || { w=0; limit_report "$n" || w=$?; }
        [ "$w" -ne 1 ] || { w=0; if [ -n "$windows" ]; then tab "$n" idle; else context "$n"; fi || w=$?; }
      fi; } >>"$out" || :
      case $w in
        0) found=1 ;;
        1) ;;
        3) failed=1 ;;
        4) ;;  # the no-figure note: printed, but no wake; the run goes on (#188)
        *) say "watch_workers: $n: could not write its report: the report buffer failed" >&2; failed=1 ;;
      esac
    fi
  done
  # A run that failed (exit 3) is rerun: its result and context reports are not printed and
  # their once-markers not stored, so the rerun reports them.
  [ -z "$failed" ] || exit 3
  cat "$out" || { say "watch_workers: could not write its report to stdout" >&2; exit 3; }
  printf '%s' "$pending" | while IFS='	' read -r n k v; do
    if [ -d "$wdir" ] && { [ -n "$windows" ] || isbg "$n" || [ "$k" = result ]; }; then
      printf '%s\n' "$v" >"$wdir/$n.watch-$k" 2>/dev/null || true
    fi
    [ -n "$windows" ] || isbg "$n" || tmux set-option -t "=$n:" "@kit_watch_$k" "$v" >/dev/null 2>&1 || true
  done
  [ -z "$found" ] || exit 0
  [ -z "$once" ] || exit 0
  [ $(( $(date +%s) + interval )) -le "$end" ] ||
    { say "watch_workers: nothing was waiting on a person within $max minute(s): $*"; exit 0; }
  sleep "$interval"
done
