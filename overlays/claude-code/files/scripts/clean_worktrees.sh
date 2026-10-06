#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Remove the finished worker worktrees under .claude/worktrees, and nothing else.
#
# Usage: clean_worktrees.sh [--apply] [--all-reasons] [--assume-idle] [--quiet]
#   no option      a dry run: prints `remove` or `keep` per worktree, with the first reason
#   --apply        removes what the dry run would; .githooks/post-merge runs this after every
#                  merge git completes itself in the main worktree (not after a conflicted merge
#                  finished with `git commit`, nor `pull --rebase` or `cherry-pick`);
#                  KIT_NO_WORKTREE_CLEANUP=1 turns that off
#   --all-reasons  runs every check instead of stopping at the first reason to keep
#   --assume-idle  only where processes cannot be inspected at all (no /proc, and lsof missing,
#                  failing, or not showing this script itself): take it that none works inside
#   --quiet        prints the removals and the summary lines (the hook)
# Needs git 2.36 or newer (`git worktree list --porcelain -z`); the hook says so once otherwise.
#
# Why: a project using the kit piled up 39 merged worker worktrees, 34 GB, and a session
# audited each one by hand before removing it: merged into main, no uncommitted change, and in
# 17 of them the only extra file was a review report whose identical copy was archived on main.
# This is that audit, done the same way every time. A worktree is removed only when every check
# in clean_worktrees.py holds; anything else is a keep, with the reason. Each removal is logged
# first, in <git dir>/kit-worktree-removals.log, and prints the command that brings the
# worktree back (`git worktree add <path> <branch>`).
#
# It never deletes a branch: the branch keeps the worker's commits whatever happens to main
# later (a merge undone, a reset). The report lists the branches whose worktrees it removed and
# says how to delete merged branches yourself. Nothing is removed while the main worktree's
# HEAD is detached.
#
# What is proven: a commit was made in the worktree itself (its own HEAD reflog) and its HEAD
# is in the main branch; every object id in any file of its git directory, which removal
# destroys, names a commit that a ref holds (no reflog counts: `git branch -d` deletes the
# branch's), or one it saves first: every commit only its git directory holds (an amended,
# reset or rebased-away tip, a squash's intermediate commits, FETCH_HEAD) is pinned under
# refs/kit/saved/<its git directory name>-<UTC time>/, in one transaction, before anything is
# deleted, and the report prints the command that deletes those refs; a tree or blob id keeps
# it, as reachability is checked for commits only; every tracked file is byte for byte what the
# index records (no stat cache, filter or line-ending conversion trusted); nothing untracked is
# lost. What is a margin, not a proof: that no worker is still in it. A sub-agent worker holds
# no process inside it between commands, and some processes cannot be inspected (Linux: another
# user's or a non-dumpable one, counted in the report; macOS: lsof does not list another user's
# at all, so they are not counted), so nothing in it, its git directory and its disposable
# folders included, may have changed (mtime or ctime) for the quiet period (quiet-minutes in
# .claude/worktree-disposable, default 60). Not guarded, by the owner's decision: a process
# changing a worktree's files between its audit and its removal (the process listing is read
# again right before), files planted to attack this script, and a SIGKILL between two removal
# steps. A step that fails, or SIGINT, SIGTERM or SIGHUP, after an identical copy was deleted
# reports the worktree PARTLY MODIFIED with each file deleted; a failed `git worktree remove`
# reports it POSSIBLY MODIFIED with how each file comes back; both exit 1. Lost for good with a removal: the ignored files
# in disposable folders, and the worktree's own reflogs. `git worktree remove` without --force
# checks again on its own. It never runs `rm -rf`, --force, `git worktree prune`, `git clean`
# or `git branch -d`/`-D`, and never touches a stash, a tag or a remote. `git worktree lock
# <path>` keeps a worktree out of its reach.
#
# The audit is Python because it reads git's NUL-separated output and compares bytes: a file
# name may hold a newline or a byte that is not UTF-8, and sh cannot hold a NUL.
set -eu
exec python3 "$(dirname -- "$0")/clean_worktrees.py" "$@"
