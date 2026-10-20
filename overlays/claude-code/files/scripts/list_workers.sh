#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# List this checkout's kit workers, one line each, and change nothing.
#
# Usage: list_workers.sh              NAME HOST ID STATE WAITING-FOR RESULT, a tab between them
#        list_workers.sh --row NAME   one worker's `claude agents` row, for the other worker scripts
#
# A worker is a name with a record in .myagentkit/workers at the top of this checkout: NAME.host
# (spawn_worker.sh: bg, tab or tmux), NAME.id, NAME.result-path, or NAME.session (spawn_codex.sh).
# A record older than NAME.host shows HOST -. A bg worker's STATE and WAITING-FOR are those of its
# row in `claude agents --json --all` (--all keeps the done and stopped rows; absent: no row, as
# after `claude rm`; ? when the list cannot be read, its words on stderr); a tmux worker is running
# or gone (`tmux has-session`); a tab worker shows -. RESULT is y when its result file exists: the
# path NAME.result-path names, else RESULT-NAME.md in its folder. Any empty field shows -.
#
# The row is the one whose id (or sessionId) is NAME.id, the id `claude --bg` printed; with no
# NAME.id, the one row named NAME whose cwd is the worker's folder: names are not unique, a resume
# with flags starts a copy under the same name (docs/research/worker-orchestration-spike.md, 6).
# The worker's folder is .claude/worktrees/NAME when it exists, else this checkout. --row prints
# STATE WAITING-FOR PID HERE ID CWD with a tab between them, HERE y when the row's cwd is the
# worker's folder, else n (another checkout's session); or `absent`; or `ambiguous` and the ids;
# or `elsewhere` and windows or posix: the native-Windows and the WSL lists are disjoint (two
# daemons: docs/research/worker-orchestration-spike-posix.md, 9), so a worker whose
# NAME.result-path has the other host's form (D:/x on native Windows, /x on POSIX) is never
# looked up here (the list shows STATE elsewhere:HOST).
# Exit 2 on a usage error, and with --row when `claude agents` cannot answer (its words on stderr).
set -u

say() { printf 'list_workers: %s\n' "$1" | LC_ALL=C tr '\001-\011\013-\037\177' '?'; }
mode=list name=""
case ${1-} in
  --row)
    [ $# -eq 2 ] || { sed -n '5,6p' "$0"; exit 2; }
    mode=row name=$2
    case $name in ''|-*|*[!A-Za-z0-9_-]*) say "refused the worker name: letters, digits, - and _, not starting with -" >&2; exit 2 ;; esac ;;
  '') ;;
  *) sed -n '5,6p' "$0"; exit 2 ;;
esac
if python3 -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python3
elif python -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python
else kit_python="py -3"; fi   # unquoted at every use
top=$(git rev-parse --show-toplevel 2>/dev/null) || top=$(pwd -P)
# Git for Windows: the Windows Python reads D:/x, never /d/x.
! command -v cygpath >/dev/null 2>&1 || top=$(cygpath -m "$top")
wdir=$top/.myagentkit/workers
json="" listed=y
if [ "$mode" = row ] || grep -qsx bg "$wdir"/*.host; then
  # Its stdout alone is the list: a notice on stderr (an update) broke the parse.
  errf=$(mktemp) || { say "cannot make a temporary file" >&2; exit 2; }
  if ! json=$(claude agents --json --all 2>"$errf"); then
    say "claude agents --json --all failed: $json$(cat -- "$errf")" >&2
    json="" listed=n
  fi
  rm -f -- "$errf"
fi
printf '%s' "$json" | $kit_python -I -c 'import json, os, re, subprocess, sys
mode, wdir, top, name, listed = sys.argv[1:]
raw = sys.stdin.buffer.read().decode("utf-8", "replace")
rows = None
if raw.strip():
    try:
        rows = json.loads(raw)
        assert isinstance(rows, list) and all(isinstance(r, dict) for r in rows)
    except (ValueError, AssertionError):
        sys.stderr.write("list_workers: claude agents --json --all printed no list of sessions: %s\n" % raw[:200])
        rows = None

def read(n, ext):
    try:
        with open(os.path.join(wdir, n + "." + ext), encoding="utf-8") as f:
            return f.read().strip()
    except (OSError, ValueError):
        return ""

def folder(n):
    tree = os.path.join(top, ".claude", "worktrees", n)
    return tree if os.path.isdir(tree) else top

def same(a, b):
    key = lambda p: os.path.normcase(os.path.realpath(p))
    return bool(a) and key(a) == key(b)

def field(v):
    return "-" if v in (None, "") else " ".join(str(v).split())

# The native-Windows and the WSL `claude agents` lists are disjoint (two daemons: POSIX spike, 9).
# NAME.result-path, which spawn_worker.sh writes in its host form (D:/x on native Windows), names it.
def host_of(path):
    if re.match(r"[A-Za-z]:[/\\]", path):
        return "windows"
    return "posix" if path.startswith("/") else ""

def row(n):
    spawned = host_of(read(n, "result-path"))
    if spawned and spawned != ("windows" if sys.platform in ("win32", "cygwin", "msys") else "posix"):
        return ["elsewhere", spawned]
    if rows is None:
        return ["?"]
    i, here = read(n, "id"), folder(n)
    if i:
        found = [r for r in rows if i in (r.get("id"), r.get("sessionId"))]
    else:
        found = [r for r in rows if r.get("name") == n and same(r.get("cwd"), here)]
    if not found:
        return ["absent"]
    if len(found) > 1:
        return ["ambiguous", " ".join(field(r.get("id")) for r in found)]
    r = found[0]
    return [field(r.get("state")), field(r.get("waitingFor")), field(r.get("pid")),
            "y" if same(r.get("cwd"), here) else "n", field(r.get("id")), field(r.get("cwd"))]

def out(fields):
    sys.stdout.buffer.write(("\t".join(fields) + "\n").encode("utf-8"))

if mode == "row":
    r = row(name)
    if r == ["?"]:
        raw.strip() or listed == "n" or sys.stderr.write("list_workers: claude agents --json --all printed nothing\n")
        sys.exit(2)
    out(r)
    sys.exit(0)
names = set()
for entry in (os.listdir(wdir) if os.path.isdir(wdir) else []):
    n, _, ext = entry.partition(".")
    if ext in ("host", "id", "result-path", "session"):
        names.add(n)
out(["NAME", "HOST", "ID", "STATE", "WAITING-FOR", "RESULT"])
for n in sorted(names):
    host, waiting = read(n, "host"), "-"
    if host == "bg":
        r = row(n)
        state, waiting = r[0], (r[1] if len(r) > 1 else "-")
        if state == "elsewhere":
            state, waiting = "elsewhere:" + waiting, "-"
    elif host == "tmux":
        alive = subprocess.run(["sh", "-c", "tmux has-session -t \"=$1\"", "sh", n],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        state = "running" if alive.returncode == 0 else "gone"
    else:
        state = "-"
    result = os.path.join(top, read(n, "result-path") or os.path.join(folder(n), "RESULT-%s.md" % n))
    out([n, field(host), field(read(n, "id")), state, waiting, "y" if os.path.isfile(result) else "n"])
' "$mode" "$wdir" "$top" "$name" "$listed"
