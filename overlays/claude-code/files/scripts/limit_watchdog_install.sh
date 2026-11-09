#!/bin/sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# limit_watchdog_install.sh PROJECT_DIR [--uninstall]: the systemd user timer that runs
# scripts/limit_watchdog.sh for one project every 10 minutes (docs/WORKFLOW.md, "autopilot, the
# owner-away switch"). The owner runs it once per project; neither the kit installer nor
# sync-kit.sh ever enables it. Linux with systemd only: macOS's launchd is not built (owner: later).
#
# It writes, under ${XDG_CONFIG_HOME:-~/.config}/systemd/user:
#   myagentkit-watchdog@.service and .timer   the templates (OnBootSec=2min, OnUnitActiveSec=10min);
#   myagentkit-watchdog@NAME.service.d/project.conf   the instance's project path, the watchdog
#     script, and this shell's whole PATH and CLAUDE_CONFIG_DIR (the account, when set) the timer
#     runs with: a user service gets neither from a login shell, and the launched lead and its
#     workers inherit that PATH.
# NAME is the project folder's name, systemd-escaped. A folder of that name already installed for
# another path is refused. Then it enables and starts the timer and prints `systemctl --user
# list-timers`. --uninstall disables that timer and removes its drop-in, and the templates once
# no instance is left. The timer's runs log in the project's .myagentkit/limit-watchdog.log and
# in `journalctl --user -u myagentkit-watchdog@NAME`.
set -u
die() { printf '%s\n' "limit_watchdog_install: $*" >&2; exit 1; }
project="" uninstall=""
for arg in "$@"; do
  case $arg in
    --uninstall) uninstall=1 ;;
    -*) die "unknown option $arg (usage: limit_watchdog_install.sh PROJECT_DIR [--uninstall])" ;;
    *) [ -z "$project" ] || die "one PROJECT_DIR only"; project=$arg ;;
  esac
done
[ -n "$project" ] || die "usage: limit_watchdog_install.sh PROJECT_DIR [--uninstall]"
[ -d "$project" ] || die "no folder $project"
project=$(CDPATH='' cd -P -- "$project" && pwd -P) || die "cannot enter $project"
case $(uname -s) in
  Darwin) die "macOS: the launchd agent is not built yet (owner: later); the owner opens the session after a limit" ;;
  Linux) ;;
  *) die "$(uname -s): only a Linux systemd user timer is built" ;;
esac
command -v systemctl >/dev/null 2>&1 || die "no systemctl: this host has no systemd user manager"
here=$(CDPATH='' cd -P -- "$(dirname -- "$0")" && pwd -P) || die "cannot find this script's folder"
watchdog=$here/limit_watchdog.sh
[ -f "$watchdog" ] || die "no $watchdog beside this script"
units=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
if command -v systemd-escape >/dev/null 2>&1; then
  name=$(systemd-escape -- "${project##*/}") || die "systemd-escape refused ${project##*/}"
else
  name=$(printf '%s' "${project##*/}" | LC_ALL=C tr -c 'A-Za-z0-9:_.\n' '_')
fi
unit=myagentkit-watchdog@$name
dropin=$units/$unit.service.d
if [ -n "$uninstall" ]; then
  systemctl --user disable --now "$unit.timer" 2>/dev/null || :
  rm -f -- "$dropin/project.conf"
  rmdir -- "$dropin" 2>/dev/null || :
  if ! ls -d "$units"/myagentkit-watchdog@?*.service.d >/dev/null 2>&1; then
    rm -f -- "$units/myagentkit-watchdog@.service" "$units/myagentkit-watchdog@.timer"
  fi
  systemctl --user daemon-reload || :
  printf '%s\n' "limit_watchdog_install: removed $unit.timer for $project"
  exit 0
fi
if [ -f "$dropin/project.conf" ]; then
  had=$(sed -n 's/^Environment="MYAGENTKIT_PROJECT=\(.*\)"$/\1/p' "$dropin/project.conf")
  [ "$had" = "$project" ] || die "$unit is installed for $had; uninstall it there first (limit_watchdog_install.sh $had --uninstall)"
fi
# The values go inside "..." of a unit line: a quote, a backslash, a % or a newline would change it.
for value in "$project" "$watchdog" "$PATH" "${CLAUDE_CONFIG_DIR:-}"; do
  case $value in *[\"\\%]*|*'
'*) die "a path holds a quote, a backslash, a % or a newline, which a unit file cannot carry as is: $value" ;; esac
done
command -v claude >/dev/null 2>&1 || die "claude is not on PATH: install Claude Code first, the timer runs it"
command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || die "no Python on PATH"
mkdir -p -- "$dropin" || die "cannot create $dropin"
cat >"$units/myagentkit-watchdog@.service" <<'EOF' || die "cannot write $units/myagentkit-watchdog@.service"
# Written by MyAgentKit's scripts/limit_watchdog_install.sh; remove it with its --uninstall.
[Unit]
Description=MyAgentKit limit watchdog for %i: reopen an autopilot lead after a usage limit

[Service]
Type=oneshot
ExecStart=/bin/sh ${MYAGENTKIT_WATCHDOG} ${MYAGENTKIT_PROJECT}
EOF
cat >"$units/myagentkit-watchdog@.timer" <<'EOF' || die "cannot write $units/myagentkit-watchdog@.timer"
# Written by MyAgentKit's scripts/limit_watchdog_install.sh; remove it with its --uninstall.
[Unit]
Description=MyAgentKit limit watchdog timer for %i

[Timer]
OnBootSec=2min
OnActiveSec=2min
OnUnitActiveSec=10min
Unit=myagentkit-watchdog@%i.service

[Install]
WantedBy=timers.target
EOF
{
  printf '%s\n' "# Written by MyAgentKit's scripts/limit_watchdog_install.sh for $project." '[Service]'
  printf 'Environment="%s"\n' "MYAGENTKIT_PROJECT=$project" "MYAGENTKIT_WATCHDOG=$watchdog" "PATH=$PATH"
  [ -z "${CLAUDE_CONFIG_DIR:-}" ] || printf 'Environment="%s"\n' "CLAUDE_CONFIG_DIR=$CLAUDE_CONFIG_DIR"
} >"$dropin/project.conf" || die "cannot write $dropin/project.conf"
systemctl --user daemon-reload || die "systemctl --user daemon-reload failed"
systemctl --user enable --now "$unit.timer" || die "systemctl --user enable --now $unit.timer failed"
printf '%s\n' "limit_watchdog_install: $unit.timer runs $watchdog for $project every 10 minutes"
systemctl --user list-timers "$unit.timer" --no-pager || :
