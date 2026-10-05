#!/usr/bin/env sh
# Remove the finished worker worktrees under .claude/worktrees, and nothing else.
#
# Usage: clean_worktrees.sh [--apply] [--assume-idle]
#   no option      a dry run: prints `remove` or `keep` per worktree, with every reason
#   --apply        removes what the dry run would; .githooks/post-merge runs this after every
#                  merge in the main worktree (KIT_NO_WORKTREE_CLEANUP=1 turns that off)
#   --assume-idle  only where processes cannot be inspected (no /proc): take it that none
#                  works inside a worktree
#
# Why: a project using the kit piled up 39 merged worker worktrees, 34 GB, and a session
# audited each one by hand before removing it: merged into main, no uncommitted change, and in
# 17 of them the only extra file was a review report whose identical copy was archived on main.
# This is that audit, done the same way every time with nothing left to judgement. A worktree
# is removed only when every check in clean_worktrees.py is PROVEN; anything else is a keep,
# with the reason. Each removal is logged first, in <git dir>/kit-worktree-removals.log, and
# prints the line that brings its branch back.
#
# What it does not guard against, by decision: a process changing a worktree between its audit
# and its removal. The liveness checks (a process working inside it, a tmux session of its
# name, the gate's lock) and `git worktree remove` without --force, which checks again on its
# own, are the mitigation. It never runs `rm -rf`, --force, `git worktree prune`, `git clean`
# or `git branch -D`, and never touches a stash, a tag or a remote.
#
# The audit is Python because it reads git's NUL-separated output and compares bytes: a file
# name may hold a newline or a byte that is not UTF-8, and sh cannot hold a NUL.
set -eu
exec python3 "$(dirname -- "$0")/clean_worktrees.py" "$@"
