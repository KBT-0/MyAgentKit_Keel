#!/bin/sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# limit_watchdog.sh PROJECT_DIR: reopen an autopilot lead that stopped on a usage limit.
#
# The one exception to "the owner opens the session" (owner, 2026-11-09; docs/WORKFLOW.md,
# "autopilot, the owner-away switch"): under autopilot, after a limit stop, this opens the next
# lead. The systemd user timer of scripts/limit_watchdog_install.sh runs it every 10 minutes
# with the main checkout's path. It exits 0 and launches nothing unless ALL of these hold:
#   1. .myagentkit/limit-stop exists (scripts/limit_stop.py writes it: RESETS_AT ORG HANDOFF);
#   2. the flock on .myagentkit/limit-watchdog.lock is free (one run at a time);
#   3. no launch for this same limit-stop line failed before (.myagentkit/limit-watchdog.failed);
#   4. RESETS_AT has passed, or this account (CLAUDE_CONFIG_DIR, else ~/.claude) is the marker's
#      org and its rate-limits.json shows the five-hour window gone or under 50 %; and no window
#      of that org is at a spawn refusal cap again (five_hour 95 %, seven_day 98 %);
#   5. scripts/working_mode.py prints "Owner: away (autopilot since ...)";
#   6. .myagentkit/handoff-pending exists, names an existing file, that file is the one
#      limit-stop names, and handoff-pending is not newer than limit-stop (a later hand-off is
#      no limit stop); the file's first line names the model and the effort (docs/HANDOFF.md);
#   7. no live lead: .myagentkit/master-writer names nobody, or `claude agents --json --all`
#      lists that session with no process and neither working nor blocked (a blocked session
#      can be woken, so it counts as running; an unreadable list is a doubt). A lead keeps the
#      marker at a limit stop, so this waits until that session is closed.
# Then ONE `claude PROMPT --bg --model M --effort E --settings AUTO` in PROJECT_DIR, in its own
# systemd scope, the bg host's form (spawn_worker.sh, "The bg host": the prompt first), one log line (time, session
# id, hand-off) in .myagentkit/limit-watchdog.log, and limit-stop deleted. A failed launch keeps
# limit-stop, logs the error and records the line in limit-watchdog.failed, so no later run
# launches for it again: nothing retries, nothing is sent. A doubt is no launch and one log
# line (a repeated skip reason is logged once). No marker at all is the normal state: silent.
set -u
project=${1:-}
if [ -z "$project" ] || [ ! -d "$project" ]; then
  printf '%s\n' "usage: limit_watchdog.sh PROJECT_DIR (the main checkout)" >&2
  exit 2
fi
project=$(CDPATH='' cd -P -- "$project" && pwd -P) || exit 2
store=$project/.myagentkit
marker=$store/limit-stop
[ -f "$marker" ] || exit 0
log=$store/limit-watchdog.log
here=$(CDPATH='' cd -P -- "$(dirname -- "$0")" && pwd -P) || exit 2
# note LINE: one log line, mirrored to stdout (the journal). skip REASON: a note, dropped when
# the log's last line is the same skip, then exit 0.
note() {
  line="$(date '+%Y-%m-%dT%H:%M:%S%z') $1"
  printf '%s\n' "$line" | LC_ALL=C tr '\001-\011\013-\037\177' '?' >>"$log" || :
  printf '%s\n' "limit_watchdog: $1" | LC_ALL=C tr '\001-\011\013-\037\177' '?'
}
skip() {
  last=$(tail -n 1 -- "$log" 2>/dev/null) || last=""
  [ "${last#* }" = "skip: $1" ] || note "skip: $1"
  exit 0
}
command -v flock >/dev/null 2>&1 || skip "no flock(1) on this host, so no run can be made the only one"
exec 9>>"$store/limit-watchdog.lock" || skip "cannot open $store/limit-watchdog.lock"
flock -n 9 || skip "another watchdog run holds $store/limit-watchdog.lock"
if python3 -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python3
elif python -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python
else skip "no Python on PATH"; fi
command -v claude >/dev/null 2>&1 || skip "claude is not on PATH (the timer's PATH comes from limit_watchdog_install.sh)"
# Conditions 3 to 7. Prints "skip REASON", or "go MODEL EFFORT" and the hand-off's path.
verdict=$($kit_python -I -c 'import json, os, re, shutil, subprocess, sys, time
from pathlib import Path
project, here = Path(sys.argv[1]), Path(sys.argv[2])
store = project / ".myagentkit"
def skip(reason):
    print("skip " + reason)
    sys.exit(0)
def read(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
def when(epoch):
    return time.strftime("%Y-%m-%d %H:%M %Z", time.localtime(epoch))
marker = store / "limit-stop"
try:
    line = marker.read_text(encoding="utf-8").strip()
except OSError as error:
    skip("cannot read limit-stop: %s" % error)
found = re.fullmatch(r"(\d{9,11}) (\S+) (\S.*)", line)
if not found:
    skip("limit-stop is not one line RESETS_AT_EPOCH ORG_UUID HANDOFF_PATH: %.200s" % line)
reset, org, stopped = int(found[1]), found[2], found[3]
failed = store / "limit-watchdog.failed"
if failed.is_file() and failed.read_text(encoding="utf-8", errors="replace").strip() == line:
    skip("the launch for this limit-stop failed before (its error is above in this log); the owner opens the session")
config = os.environ.get("CLAUDE_CONFIG_DIR")
folder = Path(config) if config else Path.home() / ".claude"
limits = read(folder / "rate-limits.json")
account = read(folder / ".claude.json" if config else Path.home() / ".claude.json").get("oauthAccount")
same = org != "-" and isinstance(account, dict) and account.get("organizationUuid") == org
now = time.time()
def window(key):
    w = limits.get(key)
    if not isinstance(w, dict) or type(w.get("resets_at")) not in (int, float) or w["resets_at"] <= now:
        return None, None
    used = w.get("used_percentage")
    return w, (used if type(used) in (int, float) else None)
five, used = window("five_hour")
free = same and bool(limits) and (five is None or (used is not None and used < 50))
if now < reset and not free:
    skip("the limit resets at %s" % when(reset) + ("" if same else " (this account is not the marker\x27s org, so only that time counts)"))
if same:
    for key, cap in (("five_hour", 95), ("seven_day", 98)):
        w, used = window(key)
        if w is not None and (used is None or used >= cap):
            skip("this account\x27s %s window is at %s%% again, resets %s" % (key, used, when(w["resets_at"])))
tools = [here / "working_mode.py", project / "scripts/working_mode.py"]
if len(here.parents) > 3:
    tools.append(here.parents[3] / "core/scripts/working_mode.py")
tool = next((t for t in tools if t.is_file()), None)
if tool is None:
    skip("no working_mode.py beside this script or in the project, so autopilot cannot be read")
try:
    mode = subprocess.run([sys.executable, "-I", str(tool), "--project", str(project)], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
except (OSError, subprocess.SubprocessError) as error:
    skip("working_mode.py did not run: %s" % error)
if mode.returncode != 0:
    skip("working_mode.py failed: %.200s" % (mode.stderr.strip().splitlines() or ["exit %d" % mode.returncode])[-1])
if not re.search(r"^Owner: away \(autopilot since ", mode.stdout, re.M):
    skip("autopilot is off")
pending = store / "handoff-pending"
try:
    words = pending.read_text(encoding="utf-8").split()
except OSError:
    words = []
if not words:
    skip("no .myagentkit/handoff-pending")
handoff = Path(words[0]) if Path(words[0]).is_absolute() else project / words[0]
if not handoff.is_file():
    skip("handoff-pending names %s, which is not a file" % handoff)
if handoff.resolve() != Path(stopped).resolve():
    skip("limit-stop names %s and handoff-pending %s: not the same hand-off" % (stopped, handoff))
if pending.stat().st_mtime > marker.stat().st_mtime:
    skip("handoff-pending is newer than limit-stop: a later hand-off, no limit stop")
try:
    first = (handoff.read_text(encoding="utf-8", errors="replace").splitlines() or [""])[0]
except OSError as error:
    skip("cannot read the hand-off %s: %s" % (handoff, error))
model = re.search(r"(?:--model[ =]+|\bmodel:[ ]*)`?([A-Za-z][\w.\[\]-]{1,79})", first, re.I)
effort = re.search(r"(?:--effort[ =]+|\beffort:[ ]*)`?(low|medium|high|xhigh|max)\b", first, re.I)
if not model or not effort:
    skip("the first line of %s names no model and effort (docs/HANDOFF.md): %.200s" % (handoff, first))
holder = ""
writer = store / "master-writer"
if writer.exists():
    try:
        holder = (writer.read_text(encoding="utf-8").splitlines() or [""])[0].strip()
    except OSError as error:
        skip("cannot read master-writer: %s" % error)
if holder:
    try:
        rows = json.loads(subprocess.run([shutil.which("claude") or "claude", "agents", "--json", "--all"],
                                         stdin=subprocess.DEVNULL, capture_output=True, timeout=60).stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        skip("master-writer names %s and claude agents is unreadable: %s" % (holder, error))
    if not isinstance(rows, list):
        skip("master-writer names %s and claude agents printed no list" % holder)
    for row in rows:
        if isinstance(row, dict) and row.get("sessionId") == holder and (
                row.get("pid") or row.get("state") in ("working", "blocked")):
            skip("the lead %s (master-writer) still runs: %s" % (holder, row.get("state") or "pid %s" % row.get("pid")))
print("go %s %s" % (model[1], effort[1].lower()))
print(handoff.resolve())' "$project" "$here" 2>&1) || skip "the condition check failed: $(printf '%s' "$verdict" | tail -n 1)"
case $verdict in
  "skip "*) skip "${verdict#skip }" ;;
  "go "*) ;;
  *) skip "the condition check printed no verdict: $(printf '%s' "$verdict" | tail -n 1)" ;;
esac
# sed, not `set -- $verdict`: a model id such as claude-opus-5-5[1m] is a glob pattern.
model=$(printf '%s\n' "$verdict" | sed -n '1s/^go \([^ ]*\) [^ ]*$/\1/p')
effort=$(printf '%s\n' "$verdict" | sed -n '1s/^go [^ ]* \([^ ]*\)$/\1/p')
[ -n "$model" ] && [ -n "$effort" ] || skip "the condition check printed no model and effort"
handoff=$(printf '%s\n' "$verdict" | sed -n 2p)
[ -n "$handoff" ] || skip "the condition check named no hand-off"
stop_line=$(cat -- "$marker") || skip "limit-stop vanished before the launch"
settings='{"permissions":{"defaultMode":"auto"}}'
# The session's own variables are dropped, as spawn_worker.sh's $bare does: run by hand from a
# Claude Code shell, the new lead must not inherit that session's id. The launch gets its own
# transient scope rather than KillMode=process on the service: a `claude --bg` that starts the bg
# daemon would leave it in this oneshot's cgroup, which systemd kills when ExecStart exits (man
# systemd.kill: KillMode= defaults to control-group, and process is "not recommended": what it
# spares stays in a stopped unit's cgroup). --scope execs the command itself, so its output and
# exit code stay this script's (man systemd-run). No systemd-run (no systemd, a test): a plain
# launch. Fd 9 is closed for the launch: a daemon that inherited it would hold the flock for life.
set --
if command -v systemd-run >/dev/null 2>&1; then set -- systemd-run --user --scope --collect --quiet --; fi
rc=0
out=$(CDPATH='' cd -- "$project" && exec env -u CLAUDE_CODE_CHILD_SESSION -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID \
  -u CLAUDE_PID -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ATTENDED \
  -u CLAUDE_CODE_ENTRYPOINT "$@" claude "Read $handoff and follow it" --bg --model "$model" --effort "$effort" \
  --settings "$settings" </dev/null 2>&1 9>&-) || rc=$?
if [ "$rc" -ne 0 ]; then
  printf '%s\n' "$stop_line" >"$store/limit-watchdog.failed" || :
  note "launch failed: claude --bg exited $rc for $handoff: $(printf '%s' "$out" | tr '\n' ' ' | cut -c1-300); limit-stop kept, no retry"
  exit 1
fi
id=$(printf '%s\n' "$out" | LC_ALL=C sed -n 's/.*backgrounded[^0-9a-f]*\([0-9a-f]\{8,\}\).*/\1/p' | sed -n 1p)
rm -f -- "$marker" "$store/limit-watchdog.failed"
note "launched ${id:-unknown-session} $handoff (model $model, effort $effort)"
