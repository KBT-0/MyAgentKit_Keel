#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Runs a brief's check list without a model and writes one result file, read once:
#
#   sh scripts/run_checks.sh NAME.checks [--out RESULT]
#
# NAME.checks holds one shell command per line; blank lines and lines starting with `#` are
# skipped. The commands run one after another from the current directory, stdin closed, each
# through `sh -c`. RESULT (default .myagentkit/checks/NAME.checks.result.md) is written once,
# atomically, when the last command has ended; it does not exist while the run goes on:
#
#   PASS m/m | FAIL k/m              k commands failed out of m
#   PASS|FAIL <exit> <seconds>s <command>     one line per command, in order
#       <the last 20 output lines>            under a FAIL line only, indented four spaces
#
# The full output of every command goes to RESULT.log. Pipeline field report 2026-11-09,
# proposal 5: workers spent model requests running each check in its own request and
# re-reading its output; this one run and one read replace them (docs/HANDOFF.md, "The brief").
#
# EXIT CODES: 0 every command passed, 1 one or more failed, 2 usage or an unreadable list,
# 75 NOT RUN: another run holds RESULT's lock; it prints `running: RESULT` and waits for nothing.
#
# ONE RUN PER RESULT AT A TIME: the lock is flock(2) on RESULT.lock (RESULT itself is replaced
# by a rename, so a lock on it would sit on the old file). flock(1) takes it where installed;
# elsewhere the few lines of Python below do, as scripts/check.sh does, and re-run this script
# holding it. The lock file stays: removing a flock file lets two runs lock two files. The
# commands run with the lock's descriptor closed, so a server a check leaves running never
# holds it. No model, no network, no git write.
# shortcut: native Windows without flock(1) takes msvcrt.locking in the Python holder, which
# waits for the run and passes its status on; that path has not been run on Windows, and an
# absolute MSYS path (/c/...) is spelled for Windows Python with cygpath, as spawn_worker.sh's
# native() does.

usage() { echo "usage: sh scripts/run_checks.sh CHECKS_FILE [--out RESULT]" >&2; exit 2; }
[ $# -eq 1 ] || [ $# -eq 3 ] || usage
checks=$1 result=""
case $checks in ''|-*) usage ;; esac
if [ $# -eq 3 ]; then
  [ "$2" = --out ] && [ -n "$3" ] || usage
  result=$3
fi
[ -f "$checks" ] && [ -r "$checks" ] || { printf '%s\n' "run_checks: cannot read the check list: $checks" >&2; exit 2; }
[ -n "$result" ] || result=.myagentkit/checks/$(basename "$checks").result.md
lock=$result.lock

if [ "${RUN_CHECKS_LOCK_HELD:-}" = "$lock" ]; then
  # Re-run by the Python holder below, which holds the lock on descriptor RUN_CHECKS_LOCK_FD.
  lock_fd=${RUN_CHECKS_LOCK_FD:-}
  unset RUN_CHECKS_LOCK_HELD RUN_CHECKS_LOCK_FD
  case $lock_fd in [0-9]|[0-9][0-9]|[0-9][0-9][0-9]) ;; *) lock_fd="" ;; esac
else
  mkdir -p "$(dirname "$result")" || { printf '%s\n' "run_checks: cannot create the folder of $result" >&2; exit 2; }
  if command -v flock >/dev/null 2>&1; then
    exec 9>>"$lock" || { printf '%s\n' "run_checks: cannot open the lock $lock" >&2; exit 2; }
    flock -n 9 || { printf '%s\n' "running: $result"; exit 75; }
    lock_fd=9
  else
    native() {
      case $(uname -s 2>/dev/null) in
        MINGW*|MSYS*|CYGWIN*) cygpath -m "$1" ;;
        *) printf '%s' "$1" ;;
      esac
    }
    py=python3; command -v python3 >/dev/null 2>&1 || py=python
    # The re-run gets the lock path as this run spelled it: the variable is compared with it.
    RUN_CHECKS_LOCK_HELD=$lock exec "$py" -I -c '
import os, subprocess, sys
lock, script, result, args = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
try:
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o644)
except OSError as error:
    print("run_checks: cannot open the lock %s (%s)" % (lock, error.strerror), file=sys.stderr)
    sys.exit(2)
try:
    import fcntl
except ImportError:
    fcntl = None
if fcntl:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("running: " + result, flush=True)
        sys.exit(75)
    os.set_inheritable(fd, True)
    os.environ["RUN_CHECKS_LOCK_FD"] = str(fd)
    os.execvp("sh", ["sh", script] + args)
import msvcrt
try:
    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
except OSError:
    print("running: " + result, flush=True)
    sys.exit(75)
sys.exit(subprocess.call(["sh", script] + args))
' "$(native "$lock")" "$(native "$0")" "$result" "$@"
  fi
fi

work=$(mktemp -d) || { echo "run_checks: cannot create a temp dir" >&2; exit 2; }
trap 'rm -rf "$work"; rm -f "$result.tmp.$$"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
log=$result.log
# A result left by an earlier run would read as this run's: none exists until this one ends.
rm -f "$result"
: > "$log" || { printf '%s\n' "run_checks: cannot write $log" >&2; exit 2; }

cr=$(printf '\r')
total=0 failed=0
: > "$work/lines"
while IFS= read -r line || [ -n "$line" ]; do
  line=${line%"$cr"}
  cmd=${line#"${line%%[![:space:]]*}"}
  case $cmd in ''|'#'*) continue ;; esac
  total=$((total + 1))
  printf '=== %s\n' "$cmd" >> "$log"
  start=$(date +%s)
  if [ -n "$lock_fd" ]; then
    eval 'sh -c "$cmd" </dev/null >"$work/out" 2>&1 '"$lock_fd"'>&-'
  else
    sh -c "$cmd" </dev/null >"$work/out" 2>&1
  fi
  status=$?
  seconds=$(( $(date +%s) - start ))
  cat "$work/out" >> "$log"
  printf '=== exit %s, %ss\n\n' "$status" "$seconds" >> "$log"
  if [ "$status" -eq 0 ]; then
    printf 'PASS %s %ss %s\n' "$status" "$seconds" "$cmd" >> "$work/lines"
  else
    failed=$((failed + 1))
    printf 'FAIL %s %ss %s\n' "$status" "$seconds" "$cmd" >> "$work/lines"
    tail -n 20 "$work/out" | sed 's/^/    /' >> "$work/lines"
  fi
done < "$checks"

[ "$total" -gt 0 ] || { printf '%s\n' "run_checks: no command in $checks" >&2; exit 2; }
if [ "$failed" -eq 0 ]; then header="PASS $total/$total"; else header="FAIL $failed/$total"; fi
if ! { printf '%s\n' "$header"; cat "$work/lines"; } > "$result.tmp.$$" ||
   ! mv -f "$result.tmp.$$" "$result"; then
  printf '%s\n' "run_checks: cannot write $result" >&2; exit 2
fi
printf '%s: %s\n' "$header" "$result"
[ "$failed" -eq 0 ]
