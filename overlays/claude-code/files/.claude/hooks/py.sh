#!/usr/bin/env sh
# Runs a Python hook with the first interpreter that actually runs. Windows installs Python
# as `python` or `py`, and its `python3` may be a Store alias that exists on PATH but does
# not run: a hook command naming python3 then exits 9009 or 126, and Claude Code goes on
# without the hook. Usage: sh py.sh HOOK.py
# ponytail: one extra interpreter start per hook call (tens of ms); resolve once per session
# if that ever shows.
for p in python3 python; do
  "$p" -c '' >/dev/null 2>&1 && exec "$p" "$@"
done
exec py -3 "$@"
