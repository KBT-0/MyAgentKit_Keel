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
# A run once exited 0 without printing KIT CHECK: PASS. The check writes this file only once
# all checks complete, just before that line, so exit 0 without it fails an early-ended run.
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
# The self-test leaves this checkout's HEAD, index, git status and tracked changes as it found
# them, as the project gate's own self-test does (core/scripts/check.sh, self_test): a review
# running here meanwhile fails as stale_checkout on anything else. Ignored files may change.
git_view() {
  git rev-parse --verify -q HEAD || :; git ls-files -s; git status --porcelain --untracked-files=all
  # The content of tracked files already modified before the run: status names them alike.
  echo "diff $(git diff --no-ext-diff --no-textconv --binary HEAD 2>/dev/null | git hash-object --stdin)"
}
view=""
case " $* " in
  *" --self-test "*) if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
                       view="$passed/git-view"; git_view > "$view.before" 2>&1
                     fi ;;
esac
status=0
KIT_CHECK_PASSED="$passed/passed" "$py" -B scripts/check_kit.py "$@" &
child=$!
wait "$child" || status=$?
if [ "$status" -eq 0 ] && [ ! -f "$passed/passed" ]; then
  echo "KIT CHECK: FAIL — the kit check exited 0 without reaching its PASS line" >&2
  status=1
fi
if [ -n "$view" ] && ! { git_view > "$view.after" 2>&1 && cmp -s "$view.before" "$view.after"; }; then
  echo "KIT CHECK: FAIL — the self-test changed this checkout, so a review running here meanwhile" >&2
  echo "  fails as stale_checkout. Lines before (-) and after (+): HEAD, index, status, diff hash:" >&2
  diff "$view.before" "$view.after" | sed -n 's/^< /    - /p; s/^> /    + /p' | head -40 >&2
  status=1
fi
exit "$status"
