#!/usr/bin/env sh
# Runs a Python hook with the first interpreter that actually runs. Windows installs Python
# as `python` or `py`, and its `python3` may be a Store alias that exists on PATH but does
# not run: a hook command naming python3 then exits 9009 or 126, and Claude Code goes on
# without the hook (https://learn.microsoft.com/en-us/windows/python/faqs,
# https://docs.python.org/3/using/windows.html). The probe reads no stdin (the hook's payload
# is there) and runs isolated (-I): a sitecustomize.py on PYTHONPATH must not run twice.
# Usage: sh py.sh HOOK.py
#
# The probe is a second Python start, about 0.5 s on native Windows, for every hook of every
# tool call (#83). The interpreter that passed it is kept in the user's cache folder and tried
# first. A hook exits 0, 1 or 2; any other code (126/127: not found; 9009 & 255: a Store alias
# that stopped running) means Python did not run the hook, so the cache is dropped and the
# probe decides again.

# A guard fails closed: any exit but 2 lets the tool call through
# (https://code.claude.com/docs/en/hooks). Any other hook only reports: exit 2 from
# UserPromptSubmit would block every prompt, and from Stop would refuse every stop.
# The hook's own file name decides, never a folder above it. The root-scan and secret-file
# guards fail open: a guard that cannot run must not refuse every shell call or edit (#298, #297).
fail() {
  printf '%s\n' "$1" >&2
  name=${2##*/}
  name=${name##*\\}
  case "$name" in guard_root_scan.py | guard_secret_files.py) exit 1 ;; guard_*) exit 2 ;; esac
  exit 1
}

# CPython exits 2 on a script it cannot open: a missing hook would block every prompt (#139).
[ -f "$1" ] && [ -r "$1" ] || fail "hook file missing or unreadable: $1; re-sync the kit's .claude/hooks or fix .claude/settings.json" "$1"

cache=
[ -n "$HOME" ] && cache=${XDG_CACHE_HOME:-$HOME/.cache}/myagentkit-python
if [ -n "$cache" ] && read -r p 2>/dev/null <"$cache"; then
  case "$p" in
    python3 | python | 'py -3')
      # shellcheck disable=SC2086 # $p is one of the three names above; py -3 splits on purpose
      $p "$@"
      rc=$?
      case "$rc" in 0 | 2) exit "$rc" ;; esac
      # Exit 1 is a hook's error, or an interpreter that failed before the hook (`py` with no
      # Python, a pyenv shim for a removed version): only a failed probe drops the cache.
      # shellcheck disable=SC2086
      [ "$rc" = 1 ] && $p -I -c '' </dev/null >/dev/null 2>&1 && exit 1
      ;;
  esac
  rm -f "$cache"
fi
for p in python3 python 'py -3'; do
  # shellcheck disable=SC2086
  if $p -I -c '' </dev/null >/dev/null 2>&1; then
    [ -n "$cache" ] && mkdir -p "${cache%/*}" 2>/dev/null && printf '%s\n' "$p" >"$cache" 2>/dev/null
    exec $p "$@"
  fi
done
fail "no Python found; install it or run doctor ($1 did not run)" "$1"
