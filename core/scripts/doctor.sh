#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Machine readiness, read-only. Run it at session start, on every machine and every clone:
#
#   ./scripts/doctor.sh
#
# It checks the MACHINE, not the code, so it is not part of the gate and CI does not run it.
# Each trap it finds prints one line, "MISSING: <what> — fix: <command>", and the run exits
# 1. It changes nothing: the fixes are printed for the owner to run, never run here.
#
# Why it exists: every trap below made a gate fail on a machine for a reason unrelated to
# the change being tested, and each one looked like a code failure and cost a session to
# diagnose — a hook that could not execute, an older Node resolved from a hook's PATH, a
# missing second CLI, a commit with no author, a cache npm could not write to.
set -u
cd "$(dirname "$0")/.." || exit 1
missing=0

miss() { echo "MISSING: $1 — fix: $2"; missing=$((missing + 1)); }

# The same PATH preamble as scripts/check.sh, read from it so it is configured once: a check
# here that saw a different PATH from the hook would prove nothing about the hook.
toolchain_path=$(sed -n 's/^toolchain_path="\(.*\)"$/\1/p' scripts/check.sh 2>/dev/null)
case "$toolchain_path" in
  ""|*"{{"*) toolchain_path="" ;;
  *) PATH="$toolchain_path:$PATH"; export PATH ;;
esac

# --- the executable bit, on disk AND in the index -------------------------------------
# On disk for this machine; in the index for CI and the next clone, where a 100644 script
# dies with exit 126 although it ran fine here (docs/GOTCHAS.md). Only files with a #! line:
# the boundary files are sourced, not executed, and need no bit.
for f in scripts/*.sh .githooks/* .claude/hooks/*.sh; do
  [ -f "$f" ] || continue
  first=""; IFS= read -r first < "$f" || true
  case "$first" in '#!'*) ;; *) continue ;; esac
  mode=$(git ls-files -s -- "$f" 2>/dev/null | cut -d' ' -f1)
  if [ ! -x "$f" ] || [ "$mode" = 100644 ]; then
    miss "$f is not executable (disk or git index)" "chmod +x $f && git update-index --chmod=+x $f"
  fi
done

# --- git wiring and identity ---------------------------------------------------------
[ "$(git config core.hooksPath 2>/dev/null)" = .githooks ] ||
  miss "the commit gate is not wired (core.hooksPath)" "git config core.hooksPath .githooks"
[ -n "$(git config user.name 2>/dev/null)" ] && [ -n "$(git config user.email 2>/dev/null)" ] ||
  miss "git identity (user.name / user.email)" "git config user.name '<name>' && git config user.email '<email>'"

# --- tools the kit's own scripts need ------------------------------------------------
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null ||
  miss "Python 3.10 or newer as python3 (the review tooling needs it)" "install Python 3.10+"
reviewer=$(sed -n 's/^DEFAULT_REVIEWER="\(.*\)"$/\1/p' scripts/review.sh 2>/dev/null)
if [ -n "$reviewer" ] && ! command -v "$reviewer" >/dev/null 2>&1; then
  miss "the second CLI '$reviewer' that scripts/review.sh calls" "install and log in to $reviewer (docs/DEV_SETUP.md §3)"
fi
if [ -f scripts/spawn_worker.sh ] && ! command -v tmux >/dev/null 2>&1; then
  miss "tmux, which scripts/spawn_worker.sh needs for worker sessions" "install tmux"
fi

# --- Node as a hook sees it ----------------------------------------------------------
# nvm sets PATH in the interactive shell's rc file only, so its default alias never reaches
# a non-interactive sh such as a git hook: the hook resolves no node, or an older system one.
# Probed with an empty environment and the system PATH plus the gate's own preamble.
if [ -f .nvmrc ] || [ -f package.json ]; then
  base="$(getconf PATH 2>/dev/null || echo /usr/bin:/bin):/usr/local/bin:/opt/homebrew/bin"
  [ -n "$toolchain_path" ] && base="$toolchain_path:$base"
  hook_node=$(env -i HOME="$HOME" PATH="$base" sh -c 'node --version' 2>/dev/null)
  want=$(sed -n '1s/^v\{0,1\}\([0-9][0-9]*\).*/\1/p' .nvmrc 2>/dev/null)
  have=$(printf '%s' "$hook_node" | sed -n 's/^v\([0-9][0-9]*\).*/\1/p')
  if [ -z "$hook_node" ]; then
    miss "node is not resolvable from a non-interactive sh (a git hook)" "set toolchain_path in scripts/check.sh to the directory of the right node (docs/DEV_SETUP.md §2)"
  elif [ -n "$want" ] && [ "$have" != "$want" ]; then
    miss "a git hook resolves node $hook_node, .nvmrc wants $want" "set toolchain_path in scripts/check.sh to the directory of node $want (docs/DEV_SETUP.md §2)"
  fi
fi

# --- an npm cache this user cannot write ---------------------------------------------
# One `sudo npm` leaves root-owned files in the cache, and every later install as the user
# fails with EACCES. Two levels deep is where they land; the full cache can be huge.
if command -v npm >/dev/null 2>&1; then
  cache=$(npm config get cache 2>/dev/null)
  if [ -d "$cache" ] && [ -n "$(find "$cache" -path "$cache/*/*/*" -prune -o ! -user "$(id -u)" -print 2>/dev/null | head -1)" ]; then
    miss "files in the npm cache $cache are owned by another user" "sudo chown -R $(id -u):$(id -g) $cache"
  fi
fi

# --- grep shadowed in the owner's interactive shell ----------------------------------
# A function or alias that swaps grep for another engine, or forces colour into pipes, makes
# a pipeline behave differently in the shell where it was tried than in the gate's sh. The
# common `grep --color=auto` alias is harmless and passes. A child process cannot see its
# caller's functions, so this probes the login shell's rc files; a host tool may shadow
# grep in its own shell too, which only `type grep` in that shell shows.
if [ -n "${SHELL:-}" ]; then
  grep_is=$("$SHELL" -ic 'command -V grep' </dev/null 2>/dev/null)
  shadowed=""
  case "$grep_is" in
    *function*) shadowed=1 ;;
    *alias*)
      expansion=${grep_is#*alias for }; expansion=${expansion#*aliased to }; expansion=${expansion#\`}
      case "$expansion" in
        *always*) shadowed=1 ;;
        grep|"grep "*) ;;
        *) shadowed=1 ;;
      esac ;;
  esac
  [ -z "$shadowed" ] ||
    miss "grep is shadowed in $SHELL ($grep_is)" "remove it from the rc file, or test gate pipelines with sh -c"
fi

if [ "$missing" -gt 0 ]; then
  echo "DOCTOR: setup incomplete ($missing)"
  exit 1
fi
echo "DOCTOR: ready"
