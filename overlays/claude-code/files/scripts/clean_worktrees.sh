#!/usr/bin/env sh
# Remove the finished worker worktrees under .claude/worktrees, and nothing else.
#
# Usage: clean_worktrees.sh [--apply] [--all-reasons] [--assume-idle] [--quiet]
#   no option      a dry run: prints `remove` or `keep` per worktree, with the first reason
#   --apply        removes what the dry run would; .githooks/post-merge runs this after every
#                  merge in the main worktree (KIT_NO_WORKTREE_CLEANUP=1 turns that off)
#   --all-reasons  runs every check instead of stopping at the first reason to keep
#   --assume-idle  only where processes cannot be inspected at all (no /proc, and lsof missing
#                  or failing): take it that none works inside a worktree
#   --quiet        prints the removals and one summary line (the hook)
#
# Why: a project using the kit piled up 39 merged worker worktrees, 34 GB, and a session
# audited each one by hand before removing it: merged into main, no uncommitted change, and in
# 17 of them the only extra file was a review report whose identical copy was archived on main.
# This is that audit, done the same way every time. A worktree is removed only when every check
# in clean_worktrees.py holds; anything else is a keep, with the reason. Each removal is logged
# first, in <git dir>/kit-worktree-removals.log, and prints the command that restores its
# branch at its last commit (every commit the branch had is in main by then).
#
# What is proven: the branch moved since it was created, every commit its HEAD, branch,
# reflogs and per-worktree refs name is in main, nothing tracked changed (no git filter can
# hide a change), nothing untracked is lost. What is a margin, not a proof: that no worker is
# still in it. A sub-agent worker holds no process inside it between commands, and another
# user's or a non-dumpable process cannot be inspected (the report counts them), so nothing
# in it may have changed for the quiet period (quiet-minutes in .claude/worktree-disposable,
# default 60). Not guarded, by the owner's decision: a process changing a worktree between its
# audit and its removal, files planted to attack this script, and a SIGKILL between two
# removal steps. `git worktree remove` without --force checks again on its own. It never runs
# `rm -rf`, --force, `git worktree prune`, `git clean` or `git branch -D`, and never touches a
# stash, a tag or a remote. `git worktree lock <path>` keeps a worktree out of its reach.
#
# The audit is Python because it reads git's NUL-separated output and compares bytes: a file
# name may hold a newline or a byte that is not UTF-8, and sh cannot hold a NUL.
set -eu
exec python3 "$(dirname -- "$0")/clean_worktrees.py" "$@"
