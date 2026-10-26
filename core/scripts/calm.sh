#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Waits until the machine is calm enough to measure, then prints one line to put beside the numbers:
#
#   sh scripts/calm.sh && <bench or timing command>
#
# Calm: the 1-minute load is under CALM_MAX_LOAD (default cores / 5) and no process matches
# CALM_HEAVY (a generator, Blender, a compiler, a gate, a game client: extend it per project).
# Prints `CALM load1=2.1 cores=20 heavy=none` and exits 0, or, after CALM_WAIT seconds (default
# 1200), `NOT CALM load1=.. cores=.. heavy=<names> after N s` and exits 1: a number taken then is
# reported as "measured under load N", never as a cost. Where no load average exists (native
# Windows) it prints `NOT MEASURED [calm]: ...` and exits 0. Leeway field report 2026-10-26: a
# frame time was measured at load 13-16 on 20 cores beside a generate run and a gate build.

# An idle editor (Unity, Godot, clangd) is no job: only what runs a build or an export is listed.
heavy_re=${CALM_HEAVY:-'generate\.py|[Bb]lender|check\.sh|check_kit\.py|cargo build|rustc|cc1|ninja|msbuild|dotnet build'}
wait_s=${CALM_WAIT:-1200}
step_s=${CALM_STEP:-15}
py=python3; command -v python3 >/dev/null 2>&1 || py=python

read_load() {  # "load1 cores", or nothing where the host has no load average
  "$py" -c 'import os
try: print("%.1f %d" % (os.getloadavg()[0], os.cpu_count() or 1))
except (AttributeError, OSError): pass' 2>/dev/null
}

heavy_now() {  # the heavy processes' names, comma-joined, or "none"; this script's own line excluded
  # Read first: a grep running beside ps would list its own pattern as a heavy job.
  procs=$(ps -A -o args= 2>/dev/null)
  names=$(printf '%s\n' "$procs" | grep -v 'calm\.sh' | grep -Eo "$heavy_re" | sort -u | paste -sd, -)
  printf '%s\n' "${names:-none}"
}

start=$(date +%s)
while :; do
  # shellcheck disable=SC2046 # the two words split on purpose
  set -- $(read_load)
  if [ $# -ne 2 ]; then
    echo "NOT MEASURED [calm]: this host gives no load average; say \"load unknown\" beside the numbers"
    exit 0
  fi
  load=$1 cores=$2 heavy=$(heavy_now)
  max=${CALM_MAX_LOAD:-$(awk -v c="$cores" 'BEGIN { printf "%.1f", c / 5 }')}
  if [ "$heavy" = none ] && awk -v l="$load" -v m="$max" 'BEGIN { exit !(l < m) }'; then
    echo "CALM load1=$load cores=$cores heavy=none"
    exit 0
  fi
  waited=$(( $(date +%s) - start ))
  if [ "$waited" -ge "$wait_s" ]; then
    echo "NOT CALM load1=$load cores=$cores heavy=$heavy after $waited s"
    exit 1
  fi
  sleep "$step_s"
done
