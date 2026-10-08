#!/usr/bin/env sh
# Kit-source acceptance, distinct from the project gate template under core/.
set -eu
kit=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$kit"
# A python.org or setup-python CPython on native Windows is `python`; there may be no python3.
if command -v python3 >/dev/null 2>&1; then exec python3 -B scripts/check_kit.py "$@"; fi
exec python -B scripts/check_kit.py "$@"
