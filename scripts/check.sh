#!/usr/bin/env sh
# Kit-source acceptance, distinct from the project gate template under core/.
set -eu
kit=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$kit"
exec python3 -B scripts/check_kit.py "$@"
