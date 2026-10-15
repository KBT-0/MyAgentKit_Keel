#!/usr/bin/env sh
# Runs a Python hook with the first interpreter that actually runs. Windows installs Python
# as `python` or `py`, and its `python3` may be a Store alias that exists on PATH but does
# not run: a hook command naming python3 then exits 9009 or 126, and Claude Code goes on
# without the hook (https://learn.microsoft.com/en-us/windows/python/faqs,
# https://docs.python.org/3/using/windows.html). The probe reads no stdin (the hook's payload
# is there) and runs isolated (-I): a sitecustomize.py on PYTHONPATH must not run twice.
# Usage: sh py.sh HOOK.py
# ponytail: one extra interpreter start per hook call (tens of ms); resolve once per session
# if that ever shows.
for p in python3 python; do
  "$p" -I -c '' </dev/null >/dev/null 2>&1 && exec "$p" "$@"
done
py -3 -I -c '' </dev/null >/dev/null 2>&1 && exec py -3 "$@"
printf '%s\n' "no Python found; install it or run doctor ($1 did not run)" >&2
# A guard fails closed: any exit but 2 lets the tool call through
# (https://code.claude.com/docs/en/hooks). Any other hook only reports: exit 2 from
# UserPromptSubmit would erase every prompt, and from Stop would refuse every stop.
# The hook's own file name decides, never a folder above it.
name=${1##*/}
name=${name##*\\}
case "$name" in guard_*) exit 2 ;; esac
exit 1
