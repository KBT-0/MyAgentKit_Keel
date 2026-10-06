#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Machine readiness, read-only. Run it at session start, on every machine and every clone:
#
#   ./scripts/doctor.sh
#
# It checks the MACHINE, not the code, so it is not part of the gate and CI does not run it.
# Each trap it finds prints one line, "MISSING: <what> — fix: <command>", and the run exits
# 1. It changes nothing: the fixes are printed for the owner to run, never run here. The one
# exception to "read-only" is the grep probe below, which runs the owner's interactive shell
# rc files ($SHELL -ic) under a 5 s timeout, and only where `timeout` exists.
#
# Why it exists: every trap below made a gate fail on a machine for a reason unrelated to
# the change being tested, and each one looked like a code failure and cost a session to
# diagnose — a hook that could not execute, an older Node resolved from a hook's PATH, a
# missing second CLI, a commit with no author, a cache npm could not write to, a checkout
# on a Windows drive under WSL, CRLF in a script, a node_modules symlink git does not ignore.
set -u
# CDPATH cleared: exported, it sent this cd into another tree with a scripts/ in it.
CDPATH= cd -- "$(dirname "$0")/.." || exit 1
missing=0

miss() { printf '%s\n' "MISSING: $1 — fix: $2"; missing=$((missing + 1)); }

# The same PATH preamble as scripts/check.sh, read from it so it is configured once: a check
# here that saw a different PATH from the hook would prove nothing about the hook. The line
# is READ, never run: evaluating it executed whatever a project wrote there, so a read-only
# check ran `$(...)` from a configuration line. $NAME and ${NAME} are expanded from the
# environment, as check.sh's sh would; any other shell syntax is reported, not guessed at.
# An UNSET variable is reported too: check.sh's `set -u` stops on it, so expanding it to
# nothing reported a ready machine whose gate could not start.
# Only the form check.sh ships is read: a line in any other form (a comment after it, single
# quotes, no quotes) was read as empty, and doctor probed a PATH the gate never uses.
toolchain_line=$(sed -n '/^[[:space:]]*toolchain_path=/{p;q;}' scripts/check.sh 2>/dev/null)
toolchain_line=${toolchain_line%"$(printf '\r')"}  # CRLF is reported once, below
toolchain_path=""
case "$toolchain_line" in
  "") [ -f scripts/check.sh ] && echo "NOTE: scripts/check.sh has no toolchain_path line; doctor probes the PATH it was started with" ;;
  toolchain_path=\"*\"*\") ;;
  toolchain_path=\"*\") toolchain_path=${toolchain_line#toolchain_path=\"}; toolchain_path=${toolchain_path%\"} ;;
esac
if [ -n "$toolchain_line" ] && [ -z "$toolchain_path" ] && [ "$toolchain_line" != 'toolchain_path=""' ]; then
  miss "toolchain_path line not in the supported form toolchain_path=\"...\"; doctor cannot see the gate's PATH" "write it in scripts/check.sh on a line of its own, exactly toolchain_path=\"<path>\", with no comment after it"
fi
unsupported=""
case "$toolchain_path" in
  *'$('*|*'`'*|*';'*|*'\'*) unsupported=1 ;;
  *) expanded=$(printf '%s\n' "$toolchain_path" | awk '{
       out = ""; s = $0
       while ((i = index(s, "$")) > 0) {
         out = out substr(s, 1, i - 1); s = substr(s, i + 1)
         if (match(s, /^[{][A-Za-z_][A-Za-z0-9_]*[}]/)) name = substr(s, 2, RLENGTH - 2)
         else if (match(s, /^[A-Za-z_][A-Za-z0-9_]*/)) name = substr(s, 1, RLENGTH)
         else exit 1
         if (!(name in ENVIRON)) { print name; exit 2 }
         out = out ENVIRON[name]; s = substr(s, RLENGTH + 1)
       }
       print out s }')
     case $? in
       0) ;;
       2) miss "toolchain_path refers to \$$expanded, which is not set" "export $expanded in the environment the gate runs in, or write the path in scripts/check.sh"
          expanded="" ;;
       *) unsupported=1 ;;
     esac ;;
esac
if [ -n "$unsupported" ]; then
  expanded=""
  miss "toolchain_path uses shell syntax doctor does not evaluate; set a plain path" "write it in scripts/check.sh as a path, using only \$HOME or \${HOME}-style variables"
fi
toolchain_path=$expanded
case "$toolchain_path" in
  ""|*"{{"*) toolchain_path="" ;;
  *) PATH="$toolchain_path:$PATH"; export PATH ;;
esac

# --- a checkout on a Windows drive under WSL -----------------------------------------
# /mnt/<drive> is the Windows filesystem seen from WSL: git converts line endings to CRLF,
# the scripts then die in sh, node_modules fills with Windows-native binaries, and the gate
# runs many times slower. DOCTOR_CHECKOUT and DOCTOR_PROC_VERSION exist for the test only.
here=${DOCTOR_CHECKOUT:-$(pwd -P)}
case "$here" in
  /mnt/[a-zA-Z]|/mnt/[a-zA-Z]/*)
    if grep -qi microsoft "${DOCTOR_PROC_VERSION:-/proc/version}" 2>/dev/null; then
      miss "the checkout $here is on a Windows drive under WSL (CRLF scripts, Windows-native binaries, a much slower gate)" "clone the repository into the WSL home (git clone <url> ~/<name>) and work there"
    fi ;;
esac

# --- the gate's own files -------------------------------------------------------------
# The loop below inspects the files it finds, and the wiring check reads core.hooksPath
# only: a deleted .githooks/pre-commit left every ordinary commit ungated and doctor ready.
# The .py files are every module scripts/review.sh runs: one deleted left doctor ready and
# the review gate unable to start. A project has no other list to read them from, so the
# kit's tests keep this one equal to what review_dispatch.py imports.
for f in scripts/check.sh .githooks/pre-commit .githooks/pre-merge-commit .githooks/commit-msg \
         scripts/doctor.sh scripts/review.sh \
         scripts/review_dispatch.py scripts/claude_bridge.py scripts/codex_bridge.py scripts/agent_process.py \
         scripts/agent_usage.py scripts/codex_quota.py; do
  [ -f "$f" ] || miss "$f does not exist (the gate needs it)" "git checkout -- $f, or sync the kit again"
done
# Not the gate's: without it finished worker worktrees are never cleaned up after a merge.
[ -f .githooks/post-merge ] ||
  miss ".githooks/post-merge does not exist (worktree clean-up after a merge needs it)" "git checkout -- .githooks/post-merge, or sync the kit again"

# --- the executable bit, on disk AND in the index -------------------------------------
# On disk for this machine; in the index for CI and the next clone, where a 100644 script
# dies with exit 126 although it ran fine here (docs/GOTCHAS.md), and a script missing from
# the index is not in the next clone at all: the index must say 100755. Only files with a #! line:
# the boundary files are sourced, not executed, and need no bit. The same files must have
# LF line endings: "#!/bin/sh<CR>" is a bad interpreter and "set -eu<CR>" an invalid option.
for f in scripts/*.sh .githooks/* .claude/hooks/*.sh; do
  [ -f "$f" ] || continue
  first=""; IFS= read -r first < "$f" || true
  case "$first" in '#!'*) ;; *) continue ;; esac
  if grep -q "$(printf '\r')" "$f"; then
    miss "$f has CRLF line endings" "tr -d '\\r' < $f > $f.lf && cat $f.lf > $f && rm $f.lf; git config core.autocrlf input"
  fi
  mode=$(git ls-files -s -- "$f" 2>/dev/null | cut -d' ' -f1)
  if [ -z "$mode" ]; then
    miss "$f is not in the git index (the next clone will not have it)" "chmod +x $f && git add --chmod=+x $f"
  elif [ ! -x "$f" ] || [ "$mode" != 100755 ]; then
    miss "$f is not executable (disk or git index)" "chmod +x $f && git update-index --chmod=+x $f"
  fi
done

# --- node_modules as a symlink git does not ignore -----------------------------------
# "node_modules/" (trailing slash) matches directories only, and git does not treat a
# symlink as one: the link shows as an untracked file and the gate's scanners fail on it.
# Asked of git itself, so any rule that does ignore it counts.
if [ -L node_modules ] && ! git check-ignore -q node_modules 2>/dev/null; then
  miss "node_modules is a symlink that .gitignore does not ignore (a pattern 'node_modules/' matches directories only)" "write node_modules without the trailing slash in .gitignore"
fi

# --- git wiring and identity ---------------------------------------------------------
[ "$(git config core.hooksPath 2>/dev/null)" = .githooks ] ||
  miss "the commit gate is not wired (core.hooksPath)" "git config core.hooksPath .githooks"
[ -n "$(git config user.name 2>/dev/null)" ] && [ -n "$(git config user.email 2>/dev/null)" ] ||
  miss "git identity (user.name / user.email)" "git config user.name '<name>' && git config user.email '<email>'"

# --- tools the kit's own scripts need ------------------------------------------------
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null ||
  miss "Python 3.10 or newer as python3 (the review tooling needs it)" "install Python 3.10+"
# Native Windows Python (os.name is not posix): no fcntl, /proc, lsof or killpg there. Only
# where python3 runs at all; a missing one is the line above.
if python3 -c 'import sys' 2>/dev/null && ! python3 -c "import os,sys; sys.exit(os.name!='posix')" 2>/dev/null; then
  echo "NOTE: native Windows Python: the review tooling runs, the gate lock and the worktree clean-up need a POSIX host (WSL)"
fi
# Resolved as review.sh and its adapters resolve it: REVIEW_REVIEWER over the configured
# reviewer, REVIEW_CLI_BIN (codex) or CLAUDE_CLI_BIN (claude) over the command name, and
# PATH first, then ~/.local/bin when codex is there. A configured reviewer doctor cannot read
# skipped this check, and a checkout without its review entry point was reported ready.
configured=$(sed -n 's/^DEFAULT_REVIEWER="\(.*\)"$/\1/p' scripts/review.sh 2>/dev/null)
if [ -f scripts/review.sh ] && [ -z "$configured" ]; then
  miss "scripts/review.sh names no reviewer doctor can read (a DEFAULT_REVIEWER=\"claude\" or \"codex\" line)" "set DEFAULT_REVIEWER=\"claude\" or DEFAULT_REVIEWER=\"codex\" on a line of its own in scripts/review.sh"
fi
# An override set to empty is not unset: the adapters read it with os.environ.get and run
# an empty command, so it is MISSING here, never read as the default.
reviewer=${REVIEW_REVIEWER:-$configured}
case "$reviewer" in
  codex) reviewer_cli=${REVIEW_CLI_BIN-codex}; override=REVIEW_CLI_BIN ;;
  claude) reviewer_cli=${CLAUDE_CLI_BIN-claude}; override=CLAUDE_CLI_BIN ;;
  *) reviewer_cli=$reviewer ;;
esac
if [ -n "$reviewer" ] && [ -z "$reviewer_cli" ]; then
  miss "$override is set to empty, so scripts/review.sh would run an empty command for $reviewer" "unset $override, or set it to the $reviewer executable"
elif [ -n "$reviewer" ] && ! ( [ -x "$HOME/.local/bin/codex" ] && PATH="$PATH:$HOME/.local/bin"
                            command -v "$reviewer_cli" ) >/dev/null 2>&1; then
  miss "the second CLI '$reviewer_cli' that scripts/review.sh calls" "install and log in to $reviewer (docs/DEV_SETUP.md §3)"
fi
if [ -f scripts/spawn_worker.sh ] && ! command -v tmux >/dev/null 2>&1; then
  miss "tmux, which scripts/spawn_worker.sh needs for worker sessions" "install tmux"
fi

# --- Node as a hook sees it ----------------------------------------------------------
# A git hook inherits the PATH of whatever started git, and check.sh puts toolchain_path in
# front of it; PATH here is built the same way (above), so this is the node the gate runs.
# It was once probed with an empty environment and the system PATH instead, which read a
# system Node the gate never ran: ready with an older Node first on PATH, MISSING with the
# right one. nvm sets PATH in the interactive shell's rc file only, so a hook started from
# a login-less shell (a GUI client, a service) sees less: that probe is a NOTE, not a fault.
if [ -f .nvmrc ] || [ -f package.json ]; then
  want=$(sed -n '1s/^v\{0,1\}\([0-9][0-9]*\).*/\1/p' .nvmrc 2>/dev/null)
  hook_node=$(node --version 2>/dev/null)
  have=$(printf '%s' "$hook_node" | sed -n 's/^v\([0-9][0-9]*\).*/\1/p')
  if [ -z "$hook_node" ]; then
    miss "node is not resolvable on the PATH a git hook inherits from this shell" "set toolchain_path in scripts/check.sh to the directory of the right node (docs/DEV_SETUP.md §2)"
  elif [ -n "$want" ] && [ "$have" != "$want" ]; then
    miss "a git hook resolves node $hook_node, .nvmrc wants $want" "set toolchain_path in scripts/check.sh to the directory of node $want (docs/DEV_SETUP.md §2)"
  fi
  base="$(getconf PATH 2>/dev/null || echo /usr/bin:/bin):/usr/local/bin:/opt/homebrew/bin"
  [ -n "$toolchain_path" ] && base="$toolchain_path:$base"
  bare_node=$(env -i HOME="$HOME" PATH="$base" sh -c 'node --version' 2>/dev/null)
  [ "$bare_node" = "$hook_node" ] ||
    printf '%s\n' "NOTE: a hook started from a login-less shell would see node ${bare_node:-none} (set toolchain_path in scripts/check.sh if hooks start that way)"
fi

# --- an npm cache this user cannot write ---------------------------------------------
# One `sudo npm` leaves root-owned files in the cache, and every later install as the user
# fails with EACCES. Three levels deep is where they land, the third level included (it was
# once pruned before its owner was read); the full cache can be huge. npm
# itself is not asked (`npm config get` writes a log and the cache dir), so a cache moved
# only in an .npmrc is not seen.
cache=${npm_config_cache:-$HOME/.npm}
uid=$(id -u)
if [ -d "$cache" ] && [ -n "$(find "$cache" -path "$cache/*/*/*" -prune ! -user "$uid" -print -o ! -user "$uid" -print 2>/dev/null | head -1)" ]; then
  miss "files in the npm cache $cache are owned by another user" "sudo chown -R $(id -u):$(id -g) $cache"
fi

# --- grep shadowed in the owner's interactive shell ----------------------------------
# A function or alias that swaps grep for another engine, or forces colour into pipes, makes
# a pipeline behave differently in the shell where it was tried than in the gate's sh. The
# common `grep --color=auto` alias is harmless and passes; any other option does not. A child process cannot see its
# caller's functions, so this probes the login shell's rc files; a host tool may shadow
# grep in its own shell too, which only `type grep` in that shell shows. An rc file that
# prompts on /dev/tty (keychain, ssh-add, an updater) would hang the probe, hence the timeout
# (-k: an interactive shell ignores SIGTERM). Where setsid exists the probe runs in a session
# of its own, with no terminal to stop on, and the whole process group is killed once the
# probe returns, normally or by timeout, by the group's own leader (below): `timeout` ends
# when its own child does, so a child the rc file started in the background outlived the
# probe. Without setsid, --foreground keeps the shell from stopping on SIGTTIN,
# only the shell is signalled, and such a child is not stopped: that is a NOTE. The output
# goes to a file, never a pipe: a child left running held the pipe open, and reading it
# waited for that child, far past the bound. Stock macOS has no `timeout`, and an unbounded
# probe there could block every session start, so it is skipped with a note. The rc files
# may print too (a banner, a fortune): the answer is read only between two delimiter lines
# the probe prints around `command -V grep`, never the shell's first line, which once read
# a banner and called a shell aliasing grep to `grep -v` ready. A probe that failed, printed
# no delimited answer, or an answer that is not `grep is ...`, is not a clean result: it says
# so. bash prints a function's whole body: the first line is enough.
if [ -n "${SHELL:-}" ] && ! command -v timeout >/dev/null 2>&1; then
  echo "NOTE: grep probe skipped, no timeout on this machine"
elif [ -n "${SHELL:-}" ] && ! probe_out=$(mktemp); then
  echo "NOTE: grep probe skipped, cannot create a temp file"
elif [ -n "${SHELL:-}" ]; then
  probe_mark="<<DOCTOR-PROBE-$$>>"
  probe_cmd="printf '%s\\n' '$probe_mark'; command -V grep; printf '%s\\n' '$probe_mark'"
  if command -v setsid >/dev/null 2>&1; then
    # The sh that setsid starts leads the new session's process group; --foreground keeps
    # the shell and its children in that group. Once timeout returns, the leader writes the
    # exit status, then kills its own group (kill 0) while it is still alive, so the group
    # killed is the probe's. doctor once reaped the leader first and then killed the group
    # by its saved number, which by then could name another process group. The subshell
    # takes the "Killed" line bash prints for a command killed by a signal; the ":" keeps it
    # from exec-ing setsid in its own place, which put that line back on doctor's stderr.
    ( setsid sh -c 'timeout --foreground -k 1 5 "$0" -ic "$1"; echo "$2 $?"; kill -s KILL 0' \
        "$SHELL" "$probe_cmd" "$probe_mark-exit" </dev/null >"$probe_out" 2>/dev/null; : ) 2>/dev/null
    probe_status=$(awk -v m="$probe_mark-exit " 'index($0, m) == 1 { print substr($0, length(m) + 1) }' "$probe_out")
  else
    timeout --foreground -k 1 5 "$SHELL" -ic "$probe_cmd" </dev/null >"$probe_out" 2>/dev/null
    probe_status=$?
    echo "NOTE: no setsid on this machine: a process the grep probe's rc files start in the background is not stopped"
  fi
  # The first line between the two delimiters, and only when both were printed.
  grep_is=$(awk -v m="$probe_mark" '$0 == m { n++; next } n == 1 && !got { said = $0; got = 1 }
                                    END { if (n == 2) print said }' "$probe_out")
  rm -f "$probe_out"
  shadowed=""
  case "$grep_is" in
    "grep is "*function*) shadowed=1 ;;
    "grep is "*alias*)
      expansion=${grep_is#*alias for }; expansion=${expansion#*aliased to }; expansion=${expansion#\`}
      # grep plus an ALLOWLIST of options that leave a named file's matches alone: colour
      # off or auto, and --exclude-dir, which skips only directories (oh-my-zsh's default
      # alias adds it). `grep -v` inverts every match, --color=always puts escape codes into
      # pipes, and --exclude skips a NAMED file whose name matches: all shadow grep. Each word
      # must be a whole plain token: `--exclude-dir=x>/dev/null` passed a prefix match and sent
      # every match to /dev/null, so a directory list holds only name characters and braces.
      printf '%s\n' "${expansion%\'}" | LC_ALL=C awk '$1 != "grep" { exit 1 }
        { for (i = 2; i <= NF; i++)
            if ($i !~ /^--colou?r(=(auto|never))?$/ && $i !~ /^--exclude-dir=[A-Za-z0-9._,{}\/-]+$/) exit 1 }' ||
        shadowed=1 ;;
  esac
  if [ -n "$shadowed" ]; then
    miss "grep is shadowed in $SHELL ($grep_is)" "remove it from the rc file, or test gate pipelines with sh -c"
  elif [ "$probe_status" != 0 ] || [ "${grep_is#grep is }" = "$grep_is" ]; then
    printf '%s\n' "NOTE: grep probe did not complete (exit ${probe_status:-unknown}, answered: ${grep_is:-nothing between its delimiters}); grep shadowing was not checked"
  fi
fi

if [ "$missing" -gt 0 ]; then
  echo "DOCTOR: setup incomplete ($missing)"
  exit 1
fi
echo "DOCTOR: ready"
