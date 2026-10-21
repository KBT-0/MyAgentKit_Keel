#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Machine readiness, read-only. Run it at session start, on every machine and every clone:
#
#   ./scripts/doctor.sh
#
# It checks the MACHINE, not the code, so it is not part of the gate and CI does not run it.
# Each trap it finds prints one line, "MISSING: <what> — fix: <command>", and the run exits
# 1. The fixes are printed for the owner to run, never run here: the same read-only pattern as
# `brew doctor` (non-zero exit on a problem; docs.brew.sh/Manpage) and `claude doctor`
# ("read-only installation and settings diagnostics"; code.claude.com/docs/en/cli-reference).
# One exception to "read-only": the grep probe below runs the owner's interactive shell rc
# files ($SHELL -ic), bounded by probe_seconds, and only where `timeout` exists. The promise
# covers the kit's part only: scripts/doctor.project.sh, when the project has one, is its own.
#
# Why it exists: every trap below made a gate fail on a machine for a reason unrelated to
# the change being tested, and each one looked like a code failure and cost a session to
# diagnose — a hook that could not execute, an older Node resolved from a hook's PATH, a
# missing reviewer CLI, a commit with no author, a cache npm could not write to, a checkout
# on a Windows drive under WSL, CRLF in a script, a node_modules symlink git does not ignore.
set -u
# CDPATH cleared: exported, it sent this cd into another tree with a scripts/ in it.
CDPATH= cd -- "$(dirname "$0")/.." || exit 1
missing=0
# The bound of each probe that starts another program (a CLI's --help or --version, the
# interactive shell). Measured 2026-10-15 on native Windows 11, 20 threads: `claude --help`
# took 0.3-0.6 s (native claude.exe), 0.7-1.5 s (npm's sh launcher) and 3.5 s on the first,
# cold start of an older winget install (1.9-2.0 s after); about three times the slowest is
# 10 s (KARARLAR B02 inv2#104, #147). The earlier 5 s had no measurement behind it. macOS is
# not measured yet. A probe that takes longer is reported as not answered, never as MISSING.
probe_seconds=10

miss() { printf '%s\n' "MISSING: $1 — fix: $2"; missing=$((missing + 1)); }

# The same PATH preamble as scripts/check.sh, read from it so it is configured once: a check
# here that saw a different PATH from the hook would prove nothing about the hook. The line
# is READ, never run: evaluating it executed whatever a project wrote there, so a read-only
# check ran `$(...)` from a configuration line. $NAME and ${NAME} are expanded from the
# environment, as check.sh's sh would; any other shell syntax is reported, not guessed at
# (a configuration value run as code is command injection: CWE-78).
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
# Resolved AFTER toolchain_path joined PATH, as the gate does.
# Windows installs Python as `python` or `py`: when `python3` is absent or does not run (a
# Store alias exits 9009), the scripts call the first of those that runs under the usual
# name. A function is enough for a call; an `exec` cannot run a function, so the exec sites
# use $kit_python, the resolved command.
if python3 -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python3
elif python -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python
else kit_python="py -3"; fi   # the launcher, told which Python: unquoted at every use
[ "$kit_python" = python3 ] || python3() { $kit_python "$@"; }

# --- a checkout on a Windows drive under WSL -----------------------------------------
# /mnt/<drive> is the Windows filesystem seen from WSL: git converts line endings to CRLF,
# the scripts then die in sh, node_modules fills with Windows-native binaries, and the gate
# runs many times slower. Microsoft: keep the files in the WSL filesystem for the fastest
# performance (learn.microsoft.com/en-us/windows/wsl/filesystems); the CRLF and binary parts
# are the kit's own observation. DOCTOR_CHECKOUT and DOCTOR_PROC_VERSION exist for the test only.
here=${DOCTOR_CHECKOUT:-$(pwd -P)}
case "$here" in
  /mnt/[a-zA-Z]|/mnt/[a-zA-Z]/*)
    if grep -qi microsoft "${DOCTOR_PROC_VERSION:-/proc/version}" 2>/dev/null; then
      miss "the checkout $here is on a Windows drive under WSL (CRLF scripts, Windows-native binaries, a much slower gate)" "clone the repository into the WSL home (git clone <url> ~/<name>) and work there"
    fi ;;
esac

# --- the gate's own files -------------------------------------------------------------
# The executable-bit loop below inspects only the files it finds: a deleted pre-commit
# once left every ordinary commit ungated and doctor ready. Check required files too.
# The .py files cover every review import and the mode command's helper: one deleted left
# doctor ready and a kit command unable to start. A project has no other list to read them
# from, so the kit's tests require exactly those modules in this list and the plugin package.
for f in scripts/check.sh .githooks/pre-commit .githooks/pre-merge-commit .githooks/commit-msg \
         scripts/doctor.sh scripts/review.sh \
         scripts/review_dispatch.py scripts/claude_bridge.py scripts/codex_bridge.py scripts/agent_process.py \
         scripts/agent_usage.py scripts/codex_quota.py; do
  [ -f "$f" ] || miss "$f does not exist (the gate needs it)" "git checkout -- $f, or sync the kit again"
done
[ -f scripts/working_mode.py ] ||
  miss "scripts/working_mode.py does not exist (the /myagentkit:mode command needs it)" "git checkout -- scripts/working_mode.py, or sync the kit again"
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
  # A project hook is executed, never sourced: without a #! line Git for Windows never runs it (#165).
  case "$first" in
    '#!'*) ;;
    *) case $f in
         .githooks/*.project) miss "$f has no #! line (Git for Windows never runs it; the kit's hook refuses it)" "make #!/bin/sh its first line, then chmod +x $f" ;;
         scripts/doctor.project.sh) project_bare=1
           miss "$f has no #! line (Git for Windows never runs it, and doctor skipped it)" "make #!/bin/sh its first line, then chmod +x $f" ;;
       esac
       continue ;;
  esac
  # A CR before a line feed (CRLF), not any CR: a lone CR inside a line runs, and the
  # line-ending repair keeps it. Read as bytes: Git for Windows' grep does not show a CR at
  # a line's end to a pattern.
  if python3 -c 'import sys; sys.exit(b"\r\n" not in open(sys.argv[1], "rb").read())' "$f" 2>/dev/null; then
    miss "$f has CRLF line endings" "rewrite it with LF and keep the eol=lf lines of .gitattributes (docs/DEV_SETUP.md section 1)"
  fi
  mode=$(git ls-files -s -- "$f" 2>/dev/null | cut -d' ' -f1)
  if [ -z "$mode" ]; then
    miss "$f is not in the git index (the next clone will not have it)" "chmod +x $f && git add --chmod=+x $f"
  elif [ ! -x "$f" ] && case $f in .githooks/*.project) true ;; *) false ;; esac; then
    # chmod -x is the off switch of a project hook with a #! line: the kit's hook skips it.
    printf '%s\n' "NOTE: $f is switched off (no execute bit); the kit's hook skips it. To switch it on: chmod +x $f && git update-index --chmod=+x $f"
  elif [ ! -x "$f" ] || [ "$mode" != 100755 ]; then
    miss "$f is not executable (disk or git index)" "chmod +x $f && git update-index --chmod=+x $f"
  fi
done

# --- node_modules as a symlink git does not ignore -----------------------------------
# "node_modules/" (trailing slash) matches directories only, and git does not treat a
# symlink as one (git-scm.com/docs/gitignore: "If there is a separator at the end of the
# pattern then the pattern will only match directories"): the link shows as an untracked
# file and the gate's scanners fail on it.
# Asked of git itself, so any rule that does ignore it counts.
if [ -L node_modules ] && ! git check-ignore -q node_modules 2>/dev/null; then
  miss "node_modules is a symlink that .gitignore does not ignore (a pattern 'node_modules/' matches directories only)" "write node_modules without the trailing slash in .gitignore"
fi

# --- git wiring and identity ---------------------------------------------------------
hooks_path=$(git config core.hooksPath 2>/dev/null) || hooks_path=""
if [ "$hooks_path" != .githooks ]; then
  miss "the commit gate is not wired (core.hooksPath is '${hooks_path:-unset}'; a hook of the project's own belongs beside the kit's as .githooks/<name>.project)" "git config core.hooksPath .githooks"
fi
[ -n "$(git config user.name 2>/dev/null)" ] && [ -n "$(git config user.email 2>/dev/null)" ] ||
  miss "git identity (user.name / user.email)" "git config user.name '<name>' && git config user.email '<email>'"
# With the hooks path at .githooks git never runs the LFS hooks in .git/hooks: a push uploaded
# no LFS object and a fresh clone failed on "smudge filter lfs failed" (#164). pre-push is the
# one that loses data; the others only handle locked files.
if grep -Eq '^[^#]*filter=lfs' .gitattributes 2>/dev/null && ! grep -Eq 'git[ -]lfs' .githooks/pre-push 2>/dev/null; then
  miss ".githooks/pre-push does not run Git LFS, although .gitattributes uses filter=lfs (git runs no hook in .git/hooks here, so a push uploads no LFS object)" "commit Git LFS's pre-push, post-checkout and post-commit in .githooks and its post-merge as .githooks/post-merge.project (docs/DEV_SETUP.md §1); never git lfs update --force"
fi

# --- tools the kit's own scripts need ------------------------------------------------
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  miss "Python 3.11 or newer as python3, python or py (the review tooling needs it)" "install Python 3.11+"
fi
# Told, not MISSING: without ShellCheck the gate prints NOT RUN [shellcheck] and still passes,
# and SC2028, SC2086 and ShellCheck's errors are then checked by nobody (#155).
command -v shellcheck >/dev/null 2>&1 ||
  echo "NOTE: shellcheck is not installed, so the gate's ShellCheck step does not run; install it: apt install shellcheck, brew install shellcheck or winget install koalaman.shellcheck"
# Native Windows Python (os.name 'nt') runs the gate lock, a review and the worktree clean-up
# its own way, under Git for Windows' sh (or MSYS2, Cygwin). Under any other sh (WSL, where a
# Windows python.exe on PATH runs through interop) it is handed POSIX paths and takes the
# Windows lock on them: a trap. Only where python3 runs at all; a missing one is the line above.
case $(uname -s 2>/dev/null) in MINGW*|MSYS*|CYGWIN*) windows_sh=1 ;; *) windows_sh="" ;; esac
if [ -z "$windows_sh" ] && python3 -c 'import sys' 2>/dev/null &&
   ! python3 -c "import os,sys; sys.exit(os.name!='posix')" 2>/dev/null; then
  miss "a POSIX python3 for this POSIX shell (the python3 found is native Windows Python, which runs the kit only under Git for Windows' sh)" "install python3 in this system (in WSL: sudo apt install python3), or run the kit from Git for Windows' sh"
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
# The probes below capture into temp files: an interrupt (Ctrl-C, a hook's time limit) in
# the middle of one still removes them.
help_out=; probe_out=
trap 'rm -f ${help_out:+"$help_out"} ${probe_out:+"$probe_out"}' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# The Claude CLI alone runs the review; any other reviewer is a second CLI, which only a
# cross-model review needs (docs/DEV_SETUP.md §3).
reviewer_what="a second CLI, needed only for cross-model review"
case "$reviewer" in
  codex) reviewer_cli=${REVIEW_CLI_BIN-codex}; override=REVIEW_CLI_BIN ;;
  claude) reviewer_cli=${CLAUDE_CLI_BIN-claude}; override=CLAUDE_CLI_BIN; reviewer_what="the review runs on it" ;;
  *) reviewer_cli=$reviewer ;;
esac
if [ -n "$reviewer" ] && [ -z "$reviewer_cli" ]; then
  miss "$override is set to empty, so scripts/review.sh would run an empty command for $reviewer" "unset $override, or set it to the $reviewer executable"
elif [ -n "$reviewer" ] && ! reviewer_path=$( [ -x "$HOME/.local/bin/codex" ] && PATH="$PATH:$HOME/.local/bin"
                            command -v "$reviewer_cli" 2>/dev/null ); then
  miss "the $reviewer CLI '$reviewer_cli' that scripts/review.sh calls ($reviewer_what)" "install and log in to $reviewer (docs/DEV_SETUP.md §3)"
elif [ "$reviewer" = claude ]; then
  if ! command -v timeout >/dev/null 2>&1; then
    echo "NOTE: Claude CLI --effort probe skipped, no timeout on this machine"
  elif ! help_out=$(mktemp); then
    echo "NOTE: Claude CLI --effort probe skipped, cannot create a temp file"
  else
    # Probe the command the adapter runs, found as above: a newer installation later on PATH
    # cannot supply --effort to an older CLI that actually runs. Bounded as the grep probe is
    # (below): a --help that blocks would hang every session start.
    # A child can keep stdout open after the CLI exits; a file capture never waits for EOF.
    # Where setsid exists, the CLI's background children are killed with its process group,
    # as the grep probe's are (the comment there says why the leader kills its own group).
    if command -v setsid >/dev/null 2>&1; then
      help_mark="<<DOCTOR-HELP-$$>>-exit"
      ( setsid sh -c 'timeout --foreground -k 1 "$2" "$0" --help; printf "\n%s %s\n" "$1" "$?"; kill -s KILL 0' \
          "$reviewer_path" "$help_mark" "$probe_seconds" </dev/null >"$help_out" 2>/dev/null; : ) 2>/dev/null
      help_status=$(awk -v m="$help_mark " 'index($0, m) == 1 { print substr($0, length(m) + 1) }' "$help_out")
    else
      timeout -k 1 "$probe_seconds" "$reviewer_path" --help </dev/null >"$help_out" 2>/dev/null; help_status=$?
      echo "NOTE: no setsid on this machine: a process the Claude CLI's --help starts in the background is not stopped"
    fi
    help=$(cat "$help_out")
    rm -f "$help_out"
    if [ -z "$help_status" ] || [ "$help_status" -eq 124 ] || [ "$help_status" -eq 137 ]; then
      printf '%s\n' "NOTE: the Claude CLI '$reviewer_cli' did not answer --help within $probe_seconds s; --effort was not checked"
    elif [ "$help_status" -ne 0 ] || ! printf '%s\n' "$help" | grep -Eq -- '(^|[[:space:],])--effort([[:space:]=,]|$)'; then
      miss "the Claude CLI '$reviewer_cli' does not support --effort (an old CLI earlier on PATH can shadow the current installation)" "update that CLI, reorder PATH, or set CLAUDE_CLI_BIN to the current executable"
    fi
  fi
  if [ -f scripts/claude_bridge.py ]; then
    # Present is not enough: a claude too old for a flag the review passes (--restricted), or
    # npm's claude.cmd on native Windows, failed every review. The adapter itself names the
    # claude it would launch and the flags it needs (claude_bridge.cli_readiness).
    # The output replaces what the pipe's code page cannot hold: Windows' own error text (a
    # Turkish "[WinError 193] ... değil") raised in print, and the hidden traceback read as ready.
    cli_problem=$(python3 -B -c 'import sys; sys.path.insert(0, "scripts"); import claude_bridge
sys.stdout.reconfigure(errors="replace")
print(claude_bridge.cli_readiness() or "")' 2>/dev/null)
    [ -n "$cli_problem" ] && miss "${cli_problem%%|*}" "${cli_problem#*|}"
    # The review's Bash runs only in Claude Code's sandbox, which needs these two on Linux and
    # WSL2; without them every Claude review stops at startup (sandbox_unavailable).
    if [ "$(uname -s 2>/dev/null)" = Linux ]; then
      for tool in bwrap socat; do
        command -v "$tool" >/dev/null 2>&1 ||
          miss "$tool, which Claude Code's Bash sandbox needs for the Claude review" "sudo apt-get install bubblewrap socat (or your distribution's packages)"
      done
    fi
  fi
fi
# --- a Claude Code too old for the overlay's guard hooks ----------------------------
# The overlay's guard hooks carry "onFailure": "block", which Claude Code reads from 2.1.295 on;
# an older one ignores the field, and a guard that crashes, times out or finds no Python lets
# the call through (code.claude.com/docs/en/hooks; KARARLAR D09 inv3#5, #12). Told, not
# MISSING: the guards still run. The version is compared with the documented minimum; --help
# is no evidence of what a CLI supports (code.claude.com/docs/en/cli-reference).
if [ -f .claude/settings.json ] && grep -q '"onFailure"' .claude/settings.json 2>/dev/null &&
   command -v claude >/dev/null 2>&1; then
  # Into a file, as the --help probe: a child that keeps a pipe open made sed wait past the bound.
  if command -v timeout >/dev/null 2>&1 && help_out=$(mktemp); then
    timeout -k 1 "$probe_seconds" claude --version </dev/null >"$help_out" 2>/dev/null
    host_version=$(sed -n '1s/^[^0-9]*\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' "$help_out")
    rm -f "$help_out"
  else
    host_version=""
  fi
  if [ -z "$host_version" ]; then
    echo "NOTE: could not read 'claude --version'; the overlay's onFailure: block needs Claude Code 2.1.295 or later"
  elif printf '%s\n' "$host_version" | awk -F. '{ exit !($1 * 1000000 + $2 * 1000 + $3 < 2001295) }'; then
    printf '%s\n' "NOTE: Claude Code $host_version is older than 2.1.295: the overlay's \`onFailure: block\` is ignored, so a guard hook that crashes lets the call through. Update Claude Code."
  fi
fi

# --- guard hooks the committed settings do not register (Claude Code overlay) ---------
# A worktree worker runs HEAD's .claude/settings.json (spawn_worker.sh; the working file only
# when HEAD has none): a sync copied five guards, the merged settings stayed uncommitted, and
# every worker ran without them while doctor said ready (#101). Only a file with a #! line is
# a hook that needs an entry: every kit hook has one (py.sh is named as the wrapper), while a
# helper module a project's hook imports, or a text file, has none and no entry of its own.
if [ -d .claude/hooks ]; then
  if registered=$(git show HEAD:.claude/settings.json 2>/dev/null); then
    git diff --quiet HEAD -- .claude/settings.json 2>/dev/null ||
      echo "NOTE: .claude/settings.json differs from the committed one; worktree workers run the committed one, so the owner commits it"
  else
    registered=$(cat .claude/settings.json 2>/dev/null)
  fi
  # A Windows path (%CLAUDE_PROJECT_DIR%\\.claude\\hooks\\x.py in JSON) is read with slashes,
  # and a relative one (python3 .claude/hooks/x.py) counts too: only "/" before it did.
  registered=$(printf '%s\n' "$registered" | sed 's|\\\\*|/|g')
  for f in .claude/hooks/*; do
    [ -f "$f" ] || continue
    first=""; IFS= read -r first < "$f" || true
    case $first in '#!'*) ;; *) continue ;; esac
    case $registered in
      *"/$f"*|*" $f"*|*"\"$f"*|*"'$f"*) ;;
      *) miss "$f is not registered in the committed .claude/settings.json (worktree workers run without it)" "add its entry from the kit's overlay settings.json and commit it (the owner's edit, docs/UPDATING.md)" ;;
    esac
  done
  # Only $CLAUDE_PROJECT_DIR paths: a user-level hook under ~/.claude/hooks is not this checkout's.
  # A hook in a subfolder is read whole: cut at its folder, it named one that is no file.
  for f in $(printf '%s\n' "$registered" | grep -o 'PROJECT_DIR[}%]\{0,1\}/\.claude/hooks/[A-Za-z0-9_./-]*' | sed 's|.*/\.claude/|.claude/|; s|/*$||' | sort -u); do
    [ -f "$f" ] || miss ".claude/settings.json registers $f, which does not exist" "sync the kit again, or remove the entry and commit settings.json"
  done
fi

# --- build output a merged worktree keeps (Claude Code overlay) -----------------------
# The list ships empty, the safe default: a worktree holding build output is then kept. A
# project that never filled it kept all eight merged worktrees of a CMake build, 373 MB each
# (#145). Told, not MISSING: a list left empty on purpose is the owner's choice. The names are
# the interview's usual ones (setup/INTERVIEW.md, question 10).
if [ -f .claude/worktree-disposable ] &&
   ! grep -Ev '^[[:space:]]*(#|quiet-minutes|$)' .claude/worktree-disposable >/dev/null 2>&1; then
  held=""
  for d in build node_modules dist target .venv; do
    for w in .claude/worktrees/*/"$d"; do
      [ -d "$w" ] && { held="$held${held:+, }$d"; break; }
    done
  done
  [ -z "$held" ] ||
    printf '%s\n' "NOTE: .claude/worktree-disposable lists no folder, and worktrees hold $held: every merged worktree that holds them is kept. List the build-output folders there, one per line, and ignore them in .gitignore; scripts/clean_worktrees.sh shows what each removal would take"
fi

# On native Windows (Git for Windows' sh, MSYS2, Cygwin) spawn_worker.sh opens a Windows
# Terminal tab instead of a tmux session, which that host cannot run.
# Sources (D02 inv2#145): code.claude.com/docs/en/agent-teams;
# learn.microsoft.com/en-us/windows/terminal/command-line-arguments.
if [ -f scripts/spawn_worker.sh ]; then
  case $(uname -s 2>/dev/null) in
    MINGW*|MSYS*|CYGWIN*)
      command -v "${KIT_WT:-wt.exe}" >/dev/null 2>&1 ||
        miss "Windows Terminal (${KIT_WT:-wt.exe}), which scripts/spawn_worker.sh opens worker tabs in on native Windows" "install Windows Terminal, or name its launcher in KIT_WT" ;;
    *)
      command -v tmux >/dev/null 2>&1 ||
        miss "tmux, which scripts/spawn_worker.sh needs for worker sessions" "install tmux" ;;
  esac
fi

# --- the Unity gate's editor and path converter (unity overlay) ----------------------
# Resolved as scripts/unity_gate.sh resolves it, and never started: the editor opens a window
# on any probe. So doctor cannot tell whether a UNITY_PATH the owner set is the editor (a
# wrapper script is fine; the gate names a non-editor after its run).
# A bare `unity` from PATH must sit in an editor install, Data beside it (Windows, Linux) or
# inside Unity.app (macOS): Unity Hub puts no editor on PATH, and Unity's separate CLI is
# installed there as `unity`, which doctor once called ready (#216).
if [ -f scripts/unity_gate.sh ]; then
  unity_bin=${UNITY_PATH:-unity} unity_from="UNITY_PATH unset, no unity on PATH"
  [ -z "${UNITY_PATH:-}" ] || unity_from=UNITY_PATH
  if ! unity_found=$(command -v "$unity_bin" 2>/dev/null); then
    miss "the Unity Editor '$unity_bin' that scripts/unity_gate.sh runs, not found ($unity_from)" "set UNITY_PATH to the editor executable (docs/UNITY_SETUP.md §5)"
  elif [ -z "${UNITY_PATH:-}" ]; then
    unity_real=$(readlink -f "$unity_found" 2>/dev/null) || unity_real=$unity_found
    case "$unity_real" in
      */Unity.app/Contents/MacOS/*) ;;
      *) [ -d "$(dirname -- "$unity_real")/Data" ] ||
           miss "the unity on PATH ($unity_found) is not in a Unity Editor install (Unity's separate CLI is also named unity); scripts/unity_gate.sh would run it" "set UNITY_PATH to the editor executable (docs/UNITY_SETUP.md §5)" ;;
    esac
  fi
  # The converter the gate hands the Windows editor its paths with.
  if [ -n "$windows_sh" ]; then
    command -v cygpath >/dev/null 2>&1 ||
      miss "cygpath, which scripts/unity_gate.sh needs to hand the Windows editor its paths" "reinstall Git for Windows (or MSYS2, Cygwin), which ships it"
  else
    case "$unity_bin" in
      *.exe) command -v wslpath >/dev/null 2>&1 ||
               miss "wslpath, which scripts/unity_gate.sh needs for a Windows Unity.exe" "run the gate in WSL or in Git for Windows' sh, or set UNITY_PATH to an editor for this system" ;;
    esac
  fi
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
    # The status starts on its own line: an rc file's unterminated output hid it mid-line.
    ( setsid sh -c 'timeout --foreground -k 1 "$3" "$0" -ic "$1"; printf "\n%s %s\n" "$2" "$?"; kill -s KILL 0' \
        "$SHELL" "$probe_cmd" "$probe_mark-exit" "$probe_seconds" </dev/null >"$probe_out" 2>/dev/null; : ) 2>/dev/null
    probe_status=$(awk -v m="$probe_mark-exit " 'index($0, m) == 1 { print substr($0, length(m) + 1) }' "$probe_out")
  else
    timeout --foreground -k 1 "$probe_seconds" "$SHELL" -ic "$probe_cmd" </dev/null >"$probe_out" 2>/dev/null
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
  # A NOTE, not MISSING (KARARLAR D03 inv2#146): the gate runs in a non-interactive sh that reads
  # no rc file, so the alias never reaches it; only a pipeline tried by hand in that shell lies.
  if [ -n "$shadowed" ]; then
    printf '%s\n' "NOTE: grep is shadowed in $SHELL ($grep_is): a pipeline tried there can behave differently than in the gate's sh; remove it from the rc file, or test gate pipelines with sh -c"
  elif [ "$probe_status" != 0 ] || [ "${grep_is#grep is }" = "$grep_is" ]; then
    printf '%s\n' "NOTE: grep probe did not complete (exit ${probe_status:-unknown}, answered: ${grep_is:-nothing between its delimiters}); grep shadowing was not checked"
  fi
fi

# --- stray tool commands --------------------------------------------------------------
# An agent's `find /` passed the Bash tool's timeout, moved to the background, lost its session
# and kept a CPU core busy for seven hours; every benchmark in that window was wrong (#298).
# Listed here, never ended: a process older than two hours whose parent is gone (Windows: no
# such process, or one born after it; POSIX: pid 1 or a subreaper such as systemd, launchd or
# WSL's init) that used more than 5% of a CPU over its life, and whose name is a typical tool
# command, never another program: a search or walk tool or a shell, and on Windows also python,
# node and npm. On POSIX those three are left out, as a service of the owner (systemd, launchd)
# has a parent of that kind too. A name matches whole once its .exe and trailing version are cut
# (python3.13 is python): pythonw or a helper such as node-gyp is not listed. Each line is a
# NOTE with the command that ends it, for the owner to run.
# One process listing: Win32_Process (about a second) or ps. DOCTOR_PROCESSES (lines "pid ppid
# age-seconds cpu-seconds name") and DOCTOR_STRAY_AGE exist for the test only.
stray_age=${DOCTOR_STRAY_AGE:-7200}
if [ -n "${DOCTOR_PROCESSES:-}" ]; then
  procs=$(cat -- "$DOCTOR_PROCESSES") || procs=""
elif [ -n "$windows_sh" ]; then
  procs=$(powershell.exe -NoProfile -NonInteractive -Command '$now = Get-Date
    $all = Get-CimInstance Win32_Process; $born = @{}
    foreach ($p in $all) { $born[[int]$p.ProcessId] = $p.CreationDate }
    foreach ($p in $all) {
      if (-not $p.CreationDate) { continue }
      $dad = $born[[int]$p.ParentProcessId]
      $ppid = if ($dad -and $dad -le $p.CreationDate) { $p.ParentProcessId } else { 0 }
      [string]::Format([cultureinfo]::InvariantCulture, "{0} {1} {2:F1} {3:F1} {4}", $p.ProcessId, $ppid,
        ($now - $p.CreationDate).TotalSeconds, (($p.KernelModeTime + $p.UserModeTime) / 1e7), $p.Name) }' 2>/dev/null | tr -d '\r')
else
  # etime is [[dd-]hh:]mm:ss, time [dd-]hh:mm:ss (macOS m:ss.cc): both summed from the right.
  procs=$(ps -A -o pid= -o ppid= -o etime= -o time= -o comm= 2>/dev/null | awk '
    function secs(t,   d, n, part, i, s) {
      d = 0; if (index(t, "-")) { d = substr(t, 1, index(t, "-") - 1); t = substr(t, index(t, "-") + 1) }
      n = split(t, part, ":"); s = 0; for (i = 1; i <= n; i++) s = s * 60 + part[i]
      return d * 86400 + s }
    { name = $5; for (i = 6; i <= NF; i++) name = name " " $i
      print $1, $2, secs($3), secs($4), name }')
fi
if [ -z "$procs" ]; then
  echo "NOTE: stray-process check skipped, the process list could not be read"
else
  printf '%s\n' "$procs" | awk -v min="$stray_age" -v win="$windows_sh" '
    { pid[NR] = $1; dad[NR] = $2; age[NR] = $3; cpu[NR] = $4
      n = $5; for (i = 6; i <= NF; i++) n = n " " $i
      sub(/.*[\/\\]/, "", n); n = tolower(n); sub(/\.exe$/, "", n); sub(/[0-9.]+$/, "", n); name[NR] = n; by[$1] = n }
    END {
      split("find fd fdfind rg grep egrep fgrep ag ack du tree ls bash sh dash zsh ksh pwsh powershell" (win ? " python py node npm npx" : ""), t, " ")
      for (i in t) tool[t[i]] = 1
      for (k = 1; k <= NR; k++) {
        p = dad[k]
        gone = p == 0 || p == 1 || !(p in by) || by[p] ~ /^(systemd|launchd|init)$/
        if (!gone || !(name[k] in tool) || age[k] < min || cpu[k] <= 0.05 * (age[k] > 1 ? age[k] : 1)) continue
        fix = win ? "taskkill /PID " pid[k] " /T /F" : "kill " pid[k]
        printf "NOTE: stray process %s (%s, running %.1f h, %.0f%% of a CPU, its parent is gone): it skews every timing; if it is not yours, end it: %s\n",
          pid[k], name[k], age[k] / 3600, 100 * cpu[k] / (age[k] > 1 ? age[k] : 1), fix } }'
fi

# --- the project's own machine checks ------------------------------------------------
# This file is kit-owned, so a project's own checks (its dependencies installed, a browser for
# its render tests) live in scripts/doctor.project.sh, project-owned, as a hook of its own lives
# beside the kit's as .githooks/<name>.project (#86). It runs last, when it is executable; its
# lines print as they are, and a non-zero exit is one MISSING. The loop above checks its #!
# line, line endings and index mode like any other script; without a #! line it is skipped on
# every host, as Git for Windows' sh skips it, so the report above holds everywhere.
if [ -x scripts/doctor.project.sh ] && [ -z "${project_bare-}" ]; then
  scripts/doctor.project.sh; project_status=$?
  [ "$project_status" = 0 ] ||
    miss "scripts/doctor.project.sh reported a problem (exit $project_status)" "see its lines above"
fi

if [ "$missing" -gt 0 ]; then
  printf '%s\n' "DOCTOR: setup incomplete ($missing)"
  exit 1
fi
echo "DOCTOR: ready"
