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

# The machine-wide quiet window (leeway lead 43, items 5-6: a bench waited 2 h and the lead
# sent PAUSE by hand to 5 sessions). One file per user for every project on the machine:
#   sh scripts/calm.sh hold SECONDS REASON   a bench takes the window (refused while another holds it)
#   sh scripts/calm.sh release               ends it (it also ends by itself after SECONDS)
#   sh scripts/calm.sh status                prints the live hold and exits 0, else exits 1
#   sh scripts/calm.sh window                a heavy job waits, up to CALM_WAIT, for no live hold
# spawn_worker.sh refuses a new worker while the window is held.
# A fixed /tmp path, never $TMPDIR: a sandboxed Claude Code shell and the owner's terminal differ there.
window=${CALM_WINDOW_FILE:-/tmp/myagentkit-quiet-window-$(id -u)}
window_live() {  # prints the live hold, or fails: none, expired or unreadable
  { IFS= read -r until && IFS= read -r why; } 2>/dev/null < "$window" || return 1
  case $until in ''|*[!0-9]*) return 1 ;; esac
  left=$(( until - $(date +%s) ))
  [ "$left" -gt 0 ] || return 1
  printf 'held for %s s more: %s\n' "$left" "$why"
}
case ${1:-} in
  hold)
    case ${2:-} in ''|*[!0-9]*) echo "usage: sh scripts/calm.sh hold SECONDS REASON" >&2; exit 2 ;; esac
    secs=$2; shift 2
    if held=$(window_live); then echo "QUIET WINDOW refused: already $held" >&2; exit 1; fi
    if ! { printf '%s\n%s\n' "$(( $(date +%s) + secs ))" "${*:-unnamed} ($(pwd -P))" > "$window.$$" &&
           mv -f "$window.$$" "$window"; }; then
      rm -f "$window.$$"; echo "QUIET WINDOW not held: cannot write $window" >&2; exit 1
    fi
    echo "QUIET WINDOW held for $secs s; end it with: sh scripts/calm.sh release"
    exit 0 ;;
  release) rm -f "$window" && echo "QUIET WINDOW released"; exit ;;
  status) window_live; exit ;;
  window)
    start=$(date +%s)
    while held=$(window_live); do
      [ $(( $(date +%s) - start )) -lt "$wait_s" ] || { echo "QUIET WINDOW still $held"; exit 1; }
      sleep "$step_s"
    done
    exit 0 ;;
  '') ;;
  *) echo "usage: sh scripts/calm.sh [hold SECONDS REASON | release | status | window]" >&2; exit 2 ;;
esac

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
    printf '%s\n' "CALM load1=$load cores=$cores heavy=none"
    exit 0
  fi
  waited=$(( $(date +%s) - start ))
  if [ "$waited" -ge "$wait_s" ]; then
    printf '%s\n' "NOT CALM load1=$load cores=$cores heavy=$heavy after $waited s"
    exit 1
  fi
  sleep "$step_s"
done
