#!/usr/bin/env sh
# Kit source only; projects never get this file (their .claude/settings.json calls .claude/hooks/
# directly). The kit's own .claude/settings.json runs every hook through it, and .githooks/* every
# git hook, from the pinned installed copy scripts/install_self.sh makes in the MAIN checkout's
# .myagentkit/installed/ (PLAN item 11, owner 2026-11-10): a session that edits
# overlays/claude-code/files/.claude/hooks/X.py or core/.githooks/X is never governed by its own
# edit, and an edit there changes nothing until a deliberate re-install.
#
# Usage: sh scripts/kit_hook.sh HOOK [ARG...]         a Claude Code hook: a file name of .claude/hooks/
#        sh scripts/kit_hook.sh --git HOOK [ARG...]   a git hook (pre-commit, commit-msg, ...)
#
# The main checkout is the parent of `git rev-parse --git-common-dir` from $CLAUDE_PROJECT_DIR (a
# git hook: from git's cwd), as core/.githooks/pre-commit finds it: .myagentkit/ is per checkout,
# so a worktree resolving its own would have no copy and every worker would be hookless again.
#
# No copy:
# - Before the first install (no .myagentkit/installed/ at all) a Claude Code hook runs the source
#   file under overlays/ with a one-line notice, as before this file existed, so the commit that
#   brings it in leaves no session hookless. A git hook has no such case: only install_self.sh sets
#   core.hooksPath.
# - Once installed/ exists, a missing or unreadable copy never falls back to the source. A guard that
#   refuses exits 2 and blocks the call: guard_destructive_git and guard_risky_review (a missing copy
#   must not open the gate silently), and guard_private_email and guard_worker_route, by py.sh's own
#   rule for a guard that cannot run. guard_root_scan and guard_secret_files fail open as in py.sh
#   (#298, #297), and every advisory hook exits 0. A git hook refuses the commit or merge, but
#   post-merge, which cannot veto one. While the shell guards block, run the install from a terminal.
git_mode=
[ "${1:-}" != --git ] || { git_mode=1; shift; }
name=${1:-}
[ $# -eq 0 ] || shift

stop() {
  printf 'kit_hook.sh: %s\n' "$1" >&2
  if [ -n "$git_mode" ]; then
    case $name in post-*) exit 0 ;; esac
    exit 1
  fi
  case $name in guard_root_scan.py | guard_secret_files.py) exit 0 ;; guard_*) exit 2 ;; esac
  exit 0
}

case $name in
  '' | .* | */* | *\\*) stop "'$name' is not a hook file name (sh scripts/kit_hook.sh [--git] HOOK)" ;;
esac

# Runs HOOK, with the hook's own arguments, from the hook folder of $base (a copy's root, or the
# source overlay's).
run() {
  if [ -n "$git_mode" ]; then
    file=$base/.githooks/$name
    [ -f "$file" ] || stop "$file is missing; $name did not run. Re-run sh scripts/install_self.sh in the main checkout."
    exec sh "$file" "$@"
  fi
  file=$base/.claude/hooks/$name
  case $name in
    *.py) exec sh "$base/.claude/hooks/py.sh" "$file" "$@" ;;
    *.txt) exec cat -- "$file" ;;
    *.sh) exec sh "$file" "$@" ;;
  esac
  stop "$name is no .py, .sh or .txt hook; it did not run"
}

from=.
[ -n "$git_mode" ] || from=${CLAUDE_PROJECT_DIR:-.}
main=$(CDPATH= cd -- "$from" && common=$(git rev-parse --git-common-dir) && CDPATH= cd -- "$common/.." && pwd -P) ||
  stop "$from is in no git checkout, so the kit's installed hooks cannot be found; $name did not run"
inst=$main/.myagentkit/installed

if [ ! -e "$inst" ] && [ ! -L "$inst" ]; then
  [ -z "$git_mode" ] ||
    stop "no installed copy ($inst) though core.hooksPath runs this; run sh scripts/install_self.sh in the main checkout. $name did not run."
  printf '%s\n' "kit_hook.sh: no installed copy yet; $name runs from overlays/ until sh scripts/install_self.sh runs once in the main checkout" >&2
  base=${CLAUDE_PROJECT_DIR:-.}/overlays/claude-code/files
  run "$@"
fi

ref=$(sed -n '1s/[[:space:]]*$//p' "$inst/current" 2>/dev/null)
case $ref in
  '' | *[!0-9a-f]*) stop "$inst/current names no installed ref ('$ref'); $name did not run. Run sh scripts/install_self.sh in the main checkout (from a terminal while the shell guards block)." ;;
esac
[ -d "$inst/$ref" ] ||
  stop "the installed copy $inst/$ref is missing; $name did not run. Run sh scripts/install_self.sh in the main checkout (from a terminal while the shell guards block)."
base=$inst/$ref
run "$@"
