#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Open a SEPARATE interactive Codex worker session and hand it a brief file: a Windows Terminal
# tab on native Windows (Git for Windows' sh, MSYS2, Cygwin), a tmux session elsewhere.
#
# Usage: spawn_codex.sh NAME BRIEF_FILE --model M --effort LEVEL [--worktree] [--resume [SESSION_ID]]
#
# The Codex worker runs with the workspace-write sandbox and no approval prompts, in this
# checkout or, with --worktree, in .claude/worktrees/NAME on the branch worktree-NAME, cut from
# the commit this checkout is on now. The repository's git directory is a writable root.
# The brief names a result file, and that file is the done signal.
#
# --resume answers a worker that stopped for a decision IN ITS OWN SESSION: the BRIEF_FILE then
# holds the answer, and `codex resume` keeps everything the session read, where a fresh session
# reads it all again (docs/WORKFLOW.md, "A stopped worker is answered in its own session").
# Without SESSION_ID it takes the id this script recorded when it started the worker. With
# --worktree it resumes in the existing .claude/worktrees/NAME.
#
# Pitfalls this script encodes, besides spawn_worker.sh's own (Git Bash by its full Windows path,
# every `;` handed to wt.exe escaped, the tab's command in a script because wt.exe drops double
# quotes, `exit 0` at the tab's end, values quoted with `q`, control bytes refused):
#   - The session id is recorded at spawn time in the checkout's git directory (the path is
#     printed), so the lead never searches ~/.codex/sessions by hand. It is not a file in the
#     worktree: an untracked file there is committed by `git add -A` and keeps
#     clean_worktrees.sh from removing the finished worktree.
#   - A session is resumed only once its own tab or tmux session has ended: two clients on
#     one session were never tried.
#   - Codex 0.162 on native Windows denies every write into a linked worktree's git directory,
#     whatever writable root it is given (`index.lock: Permission denied`, issue #43; tried
#     with `codex sandbox` on 2026-10-09). A worker in a worktree there cannot run `git add`,
#     `git commit` or the gate's lock; the lead commits its work. In this checkout (no
#     --worktree) the writable git directory lets it commit.
set -eu

# The same helpers as spawn_worker.sh: messages with control bytes as `?`, values quoted for a
# POSIX shell, control bytes refused in a name, path or id before anything uses it.
die() { { printf 'spawn_codex: %s' "$1" | LC_ALL=C tr '\001-\037\177' '?'; echo; } >&2; exit 1; }
q() { set -- "$(printf '%sx' "$1" | sed "s/'/'\\\\''/g")"; printf "'%s'" "${1%x}"; }
ctl() {
  [ "$(printf '%sx' "$2" | LC_ALL=C tr -d '\001-\037\177')" = "${2}x" ] ||
    die "the $1 contains a control character (a newline, carriage return, tab, ESC or DEL); it is not printed"
}

[ $# -ge 2 ] || { sed -n '3,17p' "$0"; exit 2; }
name=$1; brief=$2; shift 2
ctl "worker name" "$name"
ctl "brief path" "$brief"
nl='
'
case $(uname -s 2>/dev/null) in MINGW*|MSYS*|CYGWIN*) windows=1 ;; *) windows="" ;; esac
if [ -n "$windows" ]; then brief=$(printf '%sx' "$brief" | tr '\\' '/') && brief=${brief%x}; fi
{ [ -f "$brief" ] && [ -r "$brief" ]; } || die "brief file not found or not readable: $brief"
case "$brief" in */*) brief_dir=${brief%/*}/ ;; *) brief_dir=. ;; esac
brief_dir=$(CDPATH= cd -P -- "$brief_dir" && pwd -P && echo x) || die "cannot resolve the brief's folder: $brief"
brief=${brief_dir%"${nl}x"}/${brief##*/}
ctl "brief path" "$brief"
[ -n "$windows" ] || command -v tmux >/dev/null || die "tmux is not installed"
command -v codex >/dev/null || die "codex is not on PATH"

model=""; effort=""; worktree=""; resume=""; session=""
case $0 in *'\'*) kit=$(dirname -- "$0") ;; */*) kit=${0%/*} ;; *) kit=. ;; esac
while [ $# -gt 0 ]; do
  case "$1" in
    --model)    model=${2-}; shift; [ $# -eq 0 ] || shift ;;
    --effort)   effort=${2-}; shift; [ $# -eq 0 ] || shift ;;
    --worktree) worktree=1; shift ;;
    --resume)   resume=1; shift
                case ${1-} in ""|--*) ;; *) session=$1; shift ;; esac ;;
    *) die "unknown option: $1" ;;
  esac
done
# The lead picks both for every worker (docs/WORKFLOW.md, "Model routing").
[ -n "$model" ] || die "--model is required: the lead picks the model for every worker"
[ -n "$effort" ] || die "--effort is required: the lead picks the effort for every worker"
ctl "session id" "$session"

[ -n "$windows" ] || ! tmux has-session -t "=$name" 2>/dev/null ||
  die "tmux session '$name' still runs; a session is resumed or replaced only after it ended"

here=$(pwd -P && echo x) || die "cannot resolve the current folder"
dir=${here%"${nl}x"}
top=$(git rev-parse --show-toplevel) || die "a Codex worker needs a git repository"
if [ -n "$worktree" ]; then
  dir=$top/.claude/worktrees/$name
  if [ -n "$resume" ]; then
    [ -d "$dir" ] || die "--resume --worktree: no worktree at $dir"
  else
    ! git show-ref --verify --quiet "refs/heads/worktree-$name" ||
      die "branch worktree-$name already exists and may be stale; delete it or pick another name"
    [ ! -e "$dir" ] || die "worktree path already exists: $dir"
    git worktree add -q "$dir" -b "worktree-$name" HEAD >&2 || die "git worktree add failed: $dir"
  fi
fi
# The common git directory holds a worktree's own one (.git/worktrees/NAME), its objects and
# its refs: one writable root covers every write a commit makes.
gitdir=$(git -C "$dir" rev-parse --absolute-git-dir) || die "cannot find the git directory of $dir"
common=$(cd "$dir" && CDPATH= cd -P -- "$(git rev-parse --git-common-dir)" && pwd -P) ||
  die "cannot find the common git directory of $dir"
record=$gitdir/codex-session-$name
if [ -n "$resume" ] && [ -z "$session" ]; then
  session=$(cat "$record" 2>/dev/null) || die "--resume: no session id recorded at $record; pass it: --resume SESSION_ID"
  ctl "session id" "$session"
fi

# Codex is a native program on Windows: every path it is handed is Windows' own spelling.
if [ -n "$windows" ]; then
  wpath() { cygpath -w "$1" || die "cygpath cannot convert: $1"; }
  shown=$(cygpath -m "$brief") || die "cygpath cannot convert the brief's path: $brief"
  cdir=$(wpath "$dir"); cgit=$(wpath "$common")
else
  shown=$brief; cdir=$dir; cgit=$common
fi
instruction="Read $(q "$shown") and follow it. Do not ask questions in this pane: write a question into your result file and go on with what does not depend on it."
# The instruction comes first, before any option, as spawn_worker.sh puts it.
cmd="codex${resume:+ resume $(q "$session")} $(q "$instruction") -m $(q "$model") -c $(q "model_reasoning_effort=$effort")"
cmd="$cmd -s workspace-write -a never --add-dir $(q "$cgit") -C $(q "$cdir")"

if python3 -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python3
elif python -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python
else kit_python="py -3"; fi   # unquoted at every use
# found START: the id of the newest Codex session started at or after START whose working
# folder is this worker's and whose transcript holds its instruction. Codex writes each
# session to $CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl, its first line `session_meta`.
codex_home=${CODEX_HOME:-$HOME/.codex}
[ -z "$windows" ] || codex_home=$(cygpath -m "$codex_home")
found() {
  $kit_python -I -c 'if 1:
    import json, os, sys
    root, start, cwd, prompt = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4]
    norm = lambda p: os.path.normcase(os.path.normpath(p))
    def texts(o):
        if isinstance(o, str):
            yield o
        for v in (o.values() if isinstance(o, dict) else o if isinstance(o, list) else ()):
            yield from texts(v)
    best = (0, "")
    for folder, _, files in os.walk(os.path.join(root, "sessions")):
        for f in files:
            path = os.path.join(folder, f)
            try:
                if not f.endswith(".jsonl") or os.path.getmtime(path) < start:
                    continue
                with open(path, encoding="utf-8") as h:
                    lines = h.read().splitlines()
                meta = json.loads(lines[0])["payload"]
            except (OSError, ValueError, KeyError, IndexError, TypeError):
                continue
            if norm(meta.get("cwd") or "") != norm(cwd):
                continue
            for line in lines[1:]:
                try:
                    hit = any(prompt in t for t in texts(json.loads(line)))
                except ValueError:
                    hit = False   # the line Codex is writing now
                if hit:
                    best = max(best, (os.path.getmtime(path), str(meta.get("id", ""))))
                    break
    print(best[1])' "$codex_home" "$1" "$cdir" "$instruction"
}
# running: the process ids of the Codex programs whose command line names this worker's folder
# with -C. KIT_PS names another lister (the kit's tests), printing "<pid> <command line>".
# ponytail: a text match on `-C <folder>`, not a full command-line parse; enough to tell
# whether this worker's session still runs.
running() {
  out=$(${KIT_PS:-powershell.exe -NoProfile -NonInteractive -Command} \
    "Get-CimInstance Win32_Process -Filter \"Name='codex.exe'\" | ForEach-Object { \"\$(\$_.ProcessId) \$(\$_.CommandLine)\" }" \
    2>&1) || { printf '%s' "$out"; return 2; }
  printf '%s\n' "$out" | $kit_python -I -c 'if 1:
    import re, sys
    folder = re.escape(sys.argv[1].rstrip("\\/"))
    pat = re.compile(r"\s-C\s+(\"%s[\\/]?\"|%s[\\/]?)(\s|$)" % (folder, folder), re.I)
    print(" ".join(l.split(" ", 1)[0] for l in sys.stdin.read().replace("\r", "").split("\n")
                   if l.split(" ", 1)[0].isdigit() and pat.search(l)))' "$cdir"
}

start=$(date +%s)
if [ -n "$windows" ]; then
  pids=$(running) || die "cannot list the Codex processes to check '$name': $pids"
  [ -z "$pids" ] || die "a Codex session already runs in $cdir (process $pids); a session is resumed or replaced only after it ended: quit it in its tab (/quit)"
  wt=${KIT_WT:-wt.exe}
  command -v "$wt" >/dev/null || die "Windows Terminal ($wt) is not on PATH; start the worker by hand: $cmd"
  bash=$(command -v bash) || die "bash is not on PATH"
  bash=$(cygpath -w "$bash") || die "cygpath cannot convert the path of bash: $bash"
  semi() { printf '%s' "$1" | sed 's/;/\\;/g'; }
  tab=$(mktemp) || die "cannot write the tab's script"
  printf '%s\n' 'rm -f -- "$0"' "cd $(q "$dir") || exit 1" \
    "t=\$(date +%s); $cmd; s=\$?; [ \$((\$(date +%s) - t)) -gt 10 ] || { echo \"codex ended at once (exit \$s); press Enter to close\"; read -r _; }" \
    'exit 0' > "$tab" || die "cannot write the tab's script: $tab"
  "$wt" -w 0 new-tab --title "$(semi "$name")" "$(semi "$bash")" -l "$(semi "$(cygpath -w "$tab")")" ||
    { rm -f -- "$tab"; die "$wt could not open a tab for '$name'"; }
  where="in a Windows Terminal tab; watch it there"; view=tab
else
  # `cd` first: tmux hands a new session the PWD of whichever client last created one.
  tmux new-session -d -s "$name" -c "$dir" -x 200 -y 50 "cd $(q "$dir") && exec $cmd"
  where="(tmux attach -t $name to watch)"; view="tmux session"
fi

if [ -z "$resume" ]; then
  i=0
  while :; do
    session=$(found "$((start - 2))") || session=""
    [ -z "$session" ] && [ "$i" -lt 60 ] || break
    i=$((i + 1)); sleep 1
  done
fi
printf '%s\n' "spawn_codex: '$name' started with $brief $where"
if [ -n "$session" ] && printf '%s\n' "$session" > "$record"; then
  printf '%s\n' "spawn_codex: session $session recorded in $record"
  printf '%s\n' "spawn_codex: to answer a question it stops on, once its session has ended: scripts/spawn_codex.sh $name ANSWER_FILE --model $model --effort $effort${worktree:+ --worktree} --resume"
else
  printf '%s\n' "spawn_codex: WARNING: no Codex session for '$name' showed within 60 s; nothing is recorded. Look at its $view; its id is in the first line of the newest $codex_home/sessions/*/*/*/rollout-*.jsonl whose cwd is $cdir"
fi
[ -z "$windows" ] || [ -z "$worktree" ] ||
  printf '%s\n' "spawn_codex: native Windows: Codex cannot write this worktree's git directory, so the worker cannot commit or run the gate there; the lead commits its work (issue #43)"
[ -n "$windows" ] || sh "$kit/show_workers.sh" "$name" || printf '%s\n' "spawn_codex: '$name' was not shown and runs anyway; attach by hand: tmux attach -t $name"
printf '%s\n' "spawn_codex: the result file its brief names is the done signal"
