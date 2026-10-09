#!/usr/bin/env sh
# Kit-source acceptance, distinct from the project gate template under core/.
set -eu
# dash cannot enable job control without a terminal; bash can, including Git for Windows.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -m
kit=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$kit"
# A python.org or setup-python CPython on native Windows is `python`; there may be no python3.
if python3 -c 'import sys' >/dev/null 2>&1; then py=python3; else py=python; fi
# Help ends at exit 0 with no PASS line by design.
case " $* " in *" -h "*|*" --help "*) exec "$py" -B scripts/check_kit.py "$@" ;; esac
# A run once exited 0 without printing KIT CHECK: PASS. The check writes this file right after
# that line, so exit 0 without it is a failure, whatever ended the run early.
passed=$(mktemp -d)
trap 'rm -rf "$passed"' EXIT
cancel() {
  trap '' INT TERM
  child=${child:-${!:-}}
  if [ -n "$child" ]; then
    kill -s "$1" -- -"$child" 2>/dev/null || :
    wait "$child" 2>/dev/null || :
  fi
  exit "$2"
}
trap 'cancel INT 130' INT
trap 'cancel TERM 143' TERM
status=0
KIT_CHECK_PASSED="$passed/passed" "$py" -B scripts/check_kit.py "$@" &
child=$!
wait "$child" || status=$?
if [ "$status" -eq 0 ] && [ ! -f "$passed/passed" ]; then
  echo "KIT CHECK: FAIL — the kit check exited 0 without reaching its PASS line" >&2
  status=1
fi
exit "$status"
