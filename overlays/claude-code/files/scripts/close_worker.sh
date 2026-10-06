#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Close finished worker sessions: end each tmux session, then remove its worktree through the
# audited path. The branch is never deleted.
#
# Usage: close_worker.sh [--dry-run] NAME [NAME...]
#   --dry-run  says what it would do, runs the removal's dry run, and changes nothing
#
# The lead runs it once it decides a worker session is finished: no next task fits what the
# session holds, or the session has been idle past the cache lifetime (docs/WORKFLOW.md,
# "Worker cost"). Left to the owner, finished sessions sat idle for hours and 39 worktrees
# piled up. For each NAME, in order, each step on its own line:
#   1. A name outside [A-Za-z0-9_-], a control character included, or one starting with `-`,
#      is refused before any tmux call; the next name still runs.
#   2. `tmux kill-session -t =NAME`; the terminal tab attached to it closes by itself. A
#      session that does not exist is reported, not an error. Then it waits, up to 15 s, until
#      `tmux has-session` no longer finds it and, where /proc exists, no process works inside
#      the worktree: the tool inside takes a moment to exit, and the audit would see it.
#   3. `clean_worktrees.sh --apply --only=NAME --no-quiet`: the post-merge hook's audit, every
#      proof, for .claude/worktrees/NAME alone, without the quiet period: that margin stands in
#      for "no worker is still in it", and here the lead has just ended the session and decided
#      the work is finished (the hook never lifts it). No --assume-idle: a process still inside
#      keeps the worktree, as does anything else the audit cannot prove; the hook after a later
#      merge, or this script again, removes it then.
#   4. The branch worktree-NAME is never deleted; the line says how to delete merged branches.
# Exit 0 when every named session is gone and every named worktree was removed or did not
# exist; 1 otherwise, with the first reason on the last line; 2 on a usage error. A dry run
# exits 1 only for a refused name or a removal that could not run.
set -u

# Every line of this script is printed with its control bytes as `?` (a name is an argument).
say() { { printf 'close_worker: %s' "$1" | LC_ALL=C tr '\001-\037\177' '?'; echo; }; }
first=""
fail() { say "$1"; [ -n "$first" ] || first=$1; }
nl='
'
case $0 in */*) kit=${0%/*} ;; *) kit=. ;; esac
# The physical path of the worktree, or empty; /proc/PID/cwd names physical paths.
top=$(git rev-parse --show-toplevel 2>/dev/null) || top=""
# inside DIR: prints one process working in DIR or below and succeeds; Linux /proc only.
inside() {
  [ -n "$1" ] && [ -e /proc/self/cwd ] || return 1
  for d in /proc/[0-9]*; do
    c=$(readlink "$d/cwd" 2>/dev/null) || continue
    case $c in "$1"|"$1"/*) printf '%s' "${d#/proc/}"; return 0 ;; esac
  done
  return 1
}
dry=""
[ "${1-}" = --dry-run ] && { dry=1; shift; }
[ $# -ge 1 ] || { sed -n '6,7p' "$0"; exit 2; }

for name; do
  case $name in
    ''|-*|*[!ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-]*)
      fail "refused the name '$name' (a control character shows as ?): a worker name is letters, digits, - and _, not starting with -; nothing done for it"
      continue ;;
  esac

  if ! command -v tmux >/dev/null 2>&1; then
    say "$name: no tmux session (tmux is not installed); nothing to end"
  elif ! tmux has-session -t "=$name" 2>/dev/null; then
    say "$name: no tmux session named $name; nothing to end"
  elif [ -n "$dry" ]; then
    say "$name: dry run: would end tmux session $name (tmux kill-session -t =$name) and wait up to 15 s for it; while it runs, the audit below keeps its worktree"
  elif tmux kill-session -t "=$name" 2>/dev/null; then
    say "$name: tmux session ended; the terminal tab attached to it closes by itself"
    wt=""; [ -z "$top" ] || wt=$(CDPATH= cd -P -- "$top/.claude/worktrees/$name" 2>/dev/null && pwd -P) || wt=""
    i=0; on=""
    while :; do
      if tmux has-session -t "=$name" 2>/dev/null; then w="the tmux session to end"
      elif pid=$(inside "$wt"); then w="process $pid inside its worktree to exit"
      else break; fi
      case " $on " in *" $w; "*) ;; *) on="$on$w; " ;; esac
      [ "$i" -lt 15 ] || { say "$name: still waiting on ${on%; } after 15 s; the audit below decides"; break; }
      i=$((i + 1)); sleep 1
    done
    [ "$i" -eq 0 ] || [ "$i" -ge 15 ] || say "$name: waited $i s for ${on%; }"
  else
    fail "$name: tmux kill-session -t =$name failed; the session may still run"
  fi

  apply=--apply; [ -z "$dry" ] || { apply=""; say "$name: dry run: the removal would lift the quiet period for this worktree alone (--no-quiet), every other proof stays"; }
  out=$(sh "$kit/clean_worktrees.sh" $apply "--only=$name" --no-quiet 2>&1); rc=$?
  printf '%s\n' "$out" | LC_ALL=C tr '\001-\011\013-\037\177' '?'
  case $nl$out in
    *"${nl}clean_worktrees: no worktree at "*)
      say "$name: no worktree at .claude/worktrees/$name; nothing to remove" ;;
    *"${nl}clean_worktrees: removed 1,"*)
      say "$name: worktree removed through the audit (its log: kit-worktree-removals.log in the git directory)" ;;
    *"${nl}clean_worktrees: dry run: would remove 1,"*)
      say "$name: dry run: the audit would remove the worktree" ;;
    *)
      # The audit's first reason to keep, else its last line (a run that stopped).
      why=$(printf '%s\n' "$out" | sed -n -e 's/^         - //p' -e 's/^         stopped: //p' | sed -n 1p)
      [ -n "$why" ] || why=$(printf '%s\n' "$out" | sed -n '$p')
      if [ -n "$dry" ] && [ "$rc" -eq 0 ]; then
        say "$name: dry run: the audit would keep the worktree: $why"
      else
        fail "$name: worktree kept: $why"
      fi ;;
  esac
  if git show-ref --verify --quiet "refs/heads/worktree-$name" 2>/dev/null; then
    say "$name: branch worktree-$name is kept, never deleted here; \`git branch --merged\` lists the merged branches, \`git branch -d <name>\` deletes one"
  else
    say "$name: no branch worktree-$name; nothing to keep"
  fi
done

[ -z "$dry" ] || say "dry run: nothing was changed"
[ -z "$first" ] || { say "FAILED: $first"; exit 1; }
exit 0
