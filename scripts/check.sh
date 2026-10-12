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
# The self-test compares HEAD, index, status and file contents at its end, as the project gate
# does. It cannot catch a non-ignored file that a case writes and removes meanwhile, which fails a
# review in this worktree as stale_checkout, and the kit's own boundary example does that: run the
# kit's self-test in another worktree or after the review (a project's own self-test may share the
# review's worktree only when every case writes nothing but ignored files; owner decision,
# 2026-10-12). Ignored files may change.
git_view() {
  git rev-parse --verify -q HEAD || :; git ls-files -s; git status --porcelain --untracked-files=all
  # One ls-files and ONE git hash-object for the whole tree (a process per file cost minutes on a
  # large project). The list is newline-separated, so a path holding a newline is not hashed
  # correctly; the kit refuses such paths elsewhere (#41). Only readable regular files are listed:
  # hash-object stops at the first path it cannot read, and `git status` already covers deletions.
  # Each path goes in as ./path, since hash-object unquotes a line that starts with a double quote.
  paths=$(mktemp) || return 1
  git -c core.quotePath=false ls-files -z --cached --others --exclude-standard | tr '\0' '\n' |
    LC_ALL=C sort -u | while IFS= read -r path; do
      if [ -f "$path" ] && [ -r "$path" ]; then printf '%s\n' "$path"; fi
    done > "$paths"
  sed 's|^|./|' "$paths" | git hash-object --no-filters --stdin-paths 2>/dev/null | paste -d ' ' - "$paths"
  rm -f "$paths"
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
  echo "  fails as stale_checkout, or another process edited the checkout meanwhile." >&2
  echo "  Lines before (-) and after (+): HEAD, index, status, content hashes by path:" >&2
  diff "$view.before" "$view.after" | sed -n 's/^< /    - /p; s/^> /    + /p' | head -40 >&2
  status=1
fi
exit "$status"
