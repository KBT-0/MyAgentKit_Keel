#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Open a SEPARATE interactive Codex worker session and hand it a brief file: a Windows Terminal
# tab on native Windows (Git for Windows' sh, MSYS2, Cygwin), a tmux session elsewhere.
#
# Usage: spawn_codex.sh NAME BRIEF_FILE --model M --effort LEVEL [--worktree] [--result FILE] [--resume [SESSION_ID]]
#
# The Codex worker runs with the workspace-write sandbox and no approval prompts, in this
# checkout or, with --worktree, in .claude/worktrees/NAME on the branch worktree-NAME, cut from
# the commit this checkout is on now. Git metadata stays read-only; the lead commits.
# The brief uses the spawn-time result path; codex_worker.py --wait reports its handoff.
# The kit's BEHAVIOUR.md is not passed: Codex has no --append-system-prompt (spawn_worker.sh's).
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
#   - tmux receives only `sh PATH`, without quotes, for its default shell (fish included).
#     Before worktree creation, the temporary script path is made absolute and checked for
#     letters, digits, _, ., / and -. Set TMPDIR to an existing safe absolute directory
#     and retry if refused; the template honours TMPDIR on macOS and Linux alike.
#   - The spawning checkout records .myagentkit/workers/NAME.session outside the worker.
#     A decision is published as QUESTION-NAME.md there. --result FILE chooses another result
#     and FILE.question.md, both inside the worker. Session and question files are ignored.
#     NAME.question names the decision file. codex_worker.py writes NAME.exit beside them on
#     every way out it controls and holds NAME.live locked while it runs, so the lead's --wait
#     ends even when the wrapper is killed. close_worker.sh removes these records, refuses
#     while the decision file exists, and moves an uncommitted RESULT-NAME.md to NAME.result.md.
#   - A session is resumed only once its own tab or tmux session has ended: two clients on
#     one session were never tried.
#   - agents.max_concurrent_threads_per_session=2 caps the sub-agents a worker opens at once
#     (docs/WORKFLOW.md, "cross"); each one spends the same Codex allowance, and the key
#     must be at least 1 (codex-cli 0.162.1).
#   - `-s workspace-write -a never` is the unattended sandboxed use Codex documents
#     (learn.chatgpt.com/docs/agent-approvals-security). `--no-daemon` keeps Codex 0.157+'s
#     shared background server out of this worker's life; it is not in the official docs
#     (secondary sources only), so check it with `codex --help` when Codex changes version.
#   - The instruction names the result header codex_worker.py reads (Kind, Task, Attempt,
#     Remaining): b2fix2 (2026-10-16) published `Kind: completed` and the end marker without
#     the other three, the wrapper never saw DONE, and its tab stayed open for hours.
#   - The result file lies inside the worker's folder: workspace-write and Claude Code's
#     worktree isolation both refuse writes outside it. The `.md` suffix and the QUESTION-NAME.md
#     name are the kit's contract.
#   - KIT_SESSION_WAIT (60 s) and the 10 s flush are bounds, not measurements (owner's choice).
#   - workspace-write protects Git metadata, including a linked worktree's resolved git
#     directory, even when --add-dir names it. The worker leaves all work uncommitted and
#     lists the exact files in its result. The lead cross-reviews the diff and commits with
#     the usual gate. Never bypass the sandbox or the gate to make a commit work (issue #43).
set -eu

# The same helpers as spawn_worker.sh: messages with control bytes as `?`, values quoted for a
# POSIX shell, control bytes refused in a name, path or id before anything uses it.
die() { { printf 'spawn_codex: %s' "$1" | LC_ALL=C tr '\001-\037\177' '?'; echo; } >&2; exit 1; }
q() { set -- "$(printf '%sx' "$1" | sed "s/'/'\\\\''/g")"; printf "'%s'" "${1%x}"; }
ctl() {
  [ "$(printf '%sx' "$2" | LC_ALL=C tr -d '\001-\037\177')" = "${2}x" ] ||
    die "the $1 contains a control character (a newline, carriage return, tab, ESC or DEL); it is not printed"
}

[ $# -ge 2 ] || { sed -n '3,18p' "$0"; exit 2; }
name=$1; brief=$2; shift 2
ctl "worker name" "$name"
ctl "brief path" "$brief"
case "$name" in ""|*[!a-zA-Z0-9_-]*|-*) die "worker name must contain only letters, digits, underscore or dash, and cannot start with dash" ;; esac
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

model=""; effort=""; worktree=""; resume=""; session=""; result=""
case $0 in *'\'*) kit=$(dirname -- "$0") ;; */*) kit=${0%/*} ;; *) kit=. ;; esac
kit=$(CDPATH= cd -P -- "$kit" && pwd -P) || die "cannot resolve this script's directory"
while [ $# -gt 0 ]; do
  case "$1" in
    --model)    model=${2-}; shift; [ $# -eq 0 ] || shift ;;
    --effort)   effort=${2-}; shift; [ $# -eq 0 ] || shift ;;
    --worktree) worktree=1; shift ;;
    --result)   result=${2-}; shift; [ $# -eq 0 ] || shift; [ -n "$result" ] || die "--result needs a file" ;;
    --resume)   resume=1; shift
                case ${1-} in ""|--*) ;; *) session=$1; shift ;; esac ;;
    *) die "unknown option: $1" ;;
  esac
done
# The lead picks both for every worker (docs/WORKFLOW.md, "Model routing").
[ -n "$model" ] || die "--model is required: the lead picks the model for every worker"
[ -n "$effort" ] || die "--effort is required: the lead picks the effort for every worker"
ctl "session id" "$session"
ctl "model" "$model"
ctl "effort" "$effort"
ctl "result path" "$result"
case "$effort" in minimal|low|medium|high|xhigh) ;; *) die "unsupported effort: $effort" ;; esac

top=$(git rev-parse --show-toplevel) || die "a Codex worker needs a git repository"
dir=$top
ctl "working directory" "$dir"
# Reserve names and checkouts before checks or worktree creation, through session recording.
# An unrecorded launch keeps the reservation with its name inside. A --resume of that name
# records the launch, so it takes the reservation over: only one rm of the name succeeds.
# mkdir is the lock because it is atomic: it fails when the directory exists (mutual exclusion
# in shell, mywiki.wooledge.org/BashFAQ/045).
spawn_lock=$top/.myagentkit/workers/spawn.lock
mkdir -p -- "${spawn_lock%/*}" || die "cannot create the worker records directory"
took=""
mkdir -- "$spawn_lock" 2>/dev/null || { [ -n "$resume" ] && rm -- "$spawn_lock/$name" 2>/dev/null && took=1; } ||
  die "spawn in progress or an unrecorded launch at $spawn_lock; retry after it ends. An unrecorded launch has its worker's name inside: answer that worker with spawn_codex.sh NAME ANSWER_FILE ... --resume SESSION_ID, which records it and takes the reservation over; once its tab or tmux session has ended, or its id is written to NAME.session, release it: rm -r -- $(q "$spawn_lock")"
spawn_owner=$spawn_lock/.owner-$$
mkdir -- "$spawn_owner" || die "cannot mark the spawn reservation owner"
spawn_launched=""; spawn_recorded=""; run=""; launch_pending=""; cleaned=""; made=""; base=""
cleanup() {
  [ -z "$cleaned" ] || return 0
  cleaned=1
  trap - EXIT HUP INT TERM
  # A signal can precede the client's return. Confirm the session before handing ownership over.
  # The session can end between this check and handoff; its pane removes the script itself.
  if [ -n "$launch_pending" ] && tmux has-session -t "=$name" 2>/dev/null; then
    run=""; spawn_launched=1
  fi
  [ -z "$run" ] || rm -f -- "$run" || :
  # A spawn that stops after making its worktree and before any session runs in it removes the
  # worktree and its branch, as spawn_worker.sh does (the audit keeps a locked or unworked worktree
  # for good, and the branch blocked the name; ultrareview part 5 #8). The branch goes only while
  # it is still the commit it was made at.
  if [ -n "$made" ] && [ -z "$spawn_launched" ]; then
    if git worktree remove -f -f "$dir" >/dev/null 2>&1 &&
       git update-ref -d "refs/heads/worktree-$name" "$base" 2>/dev/null; then
      printf '%s\n' "spawn_codex: removed the unused worktree $dir and its branch worktree-$name; the name is free again" >&2 || :
    else
      printf '%s\n' "spawn_codex: could not remove the unused worktree $dir; remove it by hand: git worktree remove --force --force $(q "$dir"); git branch -D worktree-$name" >&2 || :
    fi
  fi
  # Reservation cleanup must run even when unlinking the temporary script fails.
  # A replaced reservation belongs to another spawner. The owner directory avoids rm failures.
  [ -d "$spawn_owner" ] || return 0
  rmdir -- "$spawn_owner" || return 0
  if [ -n "$spawn_recorded" ] || { [ -z "$spawn_launched" ] && [ -z "$took" ]; }; then
    rmdir -- "$spawn_lock" || :
  else
    : > "$spawn_lock/$name" || :
    printf "spawn_codex: unrecorded launch of %s; reservation kept at %s. Answer it with --resume SESSION_ID, which records it and takes the reservation over; once its tab or tmux session has ended, or its id is written to %s, release it: rm -r -- %s\n" "$name" "$spawn_lock" "${spawn_lock%/*}/$name.session" "$(q "$spawn_lock")" >&2 || :
  fi
}
trap 'cleanup' 0
trap 'trap - 0; cleanup; exit 129' HUP
trap 'trap - 0; cleanup; exit 130' INT
trap 'trap - 0; cleanup; exit 143' TERM
[ -n "$windows" ] || ! tmux has-session -t "=$name" 2>/dev/null ||
  die "tmux session '$name' still runs; a session is resumed or replaced only after it ended"

# Reserve and validate the script before creating a worktree. An explicit template
# honours TMPDIR on BSD and GNU; resolve relative paths before tmux changes directory.
if [ -z "$windows" ]; then
  run=$(mktemp "${TMPDIR:-/tmp}/kit-run.XXXXXX") || die "cannot write the session's script"
  case "$run" in */*) run_dir=${run%/*}/ ;; *) run_dir=. ;; esac
  run_dir=$(CDPATH= cd -P -- "$run_dir" && pwd -P && echo x)
  run=${run_dir%"${nl}x"}/${run##*/}
  case "$run" in *[!ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./-]*)
    rm -f -- "$run"
    die "unsafe session script path: set TMPDIR to an absolute directory containing only letters, digits, _, ., / and -" ;;
  esac
fi
if python3 -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python3
elif python -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python
else kit_python="py -3"; fi   # unquoted at every use
if [ -n "$worktree" ]; then
  dir=$top/.claude/worktrees/$name
  if [ -n "$resume" ]; then
    [ -d "$dir" ] || die "--resume --worktree: no worktree at $dir"
  else
    ! git show-ref --verify --quiet "refs/heads/worktree-$name" ||
      die "branch worktree-$name already exists and may be stale; delete it or pick another name"
    [ ! -e "$dir" ] || die "worktree path already exists: $dir"
  fi
fi
chosen_result=$result
if [ -n "$result" ]; then
  [ -z "$windows" ] || result=$(printf '%s' "$result" | tr '\\' '/')
  case "$result" in /*|[a-zA-Z]:/*) ;; *) result=$dir/$result ;; esac
  question=$result.question.md
else
  result=$dir/RESULT-$name.md; question=$dir/QUESTION-$name.md
fi
# -X utf8: a Windows pipe is cp1252, and -I ignores PYTHONUTF8; a Unicode path must print.
result=$($kit_python -I -X utf8 -c 'import pathlib, subprocess, sys
root, target = (pathlib.Path(p).resolve() for p in sys.argv[1:3])
try:
    target.relative_to(root)
    if target.suffix != ".md": raise ValueError()
except ValueError:
    sys.exit("result must be a .md file inside the worker folder")
if sys.argv[3] == "new":
    parent = target.parent.relative_to(root).as_posix()
    if parent != ".":
        kind = subprocess.run(["git", "cat-file", "-t", "HEAD:" + parent], cwd=sys.argv[4],
                              capture_output=True, text=True)
        if kind.returncode or kind.stdout.strip() != "tree":
            sys.exit("result directory does not exist in HEAD: " + parent)
elif not target.parent.is_dir():
    sys.exit("result directory does not exist: " + str(target.parent))
print(target.as_posix())' "$dir" "$result" "${worktree:+${resume:-new}}" "$top") || die "invalid result path"
# Recompute the custom question after resolving links and parent components.
[ -z "$chosen_result" ] || question=$result.question.md
record=$top/.myagentkit/workers/$name.session
exited=$top/.myagentkit/workers/$name.exit
[ -n "$resume" ] || { [ ! -e "$question" ] && [ ! -e "$record" ]; } ||
  die "worker '$name' has a session or a decision recorded; answer it with --resume, never replace it"
if [ -n "$resume" ] && [ -z "$session" ]; then
  session=$(cat "$record" 2>/dev/null) || die "--resume: no session id recorded at $record; pass it: --resume SESSION_ID"
  ctl "session id" "$session"
fi
[ -z "$resume" ] || [ -n "$session" ] || die "--resume: the recorded session id is empty; never open a fresh picker"
# The spend line, as review.sh prints its own before a review (issue #68).
printf '%s\n' "spawn_codex: about to run '$name': model $model, effort $effort"
# Locked from spawn to close_worker.sh, as spawn_worker.sh locks its worktree (the reason there).
if [ -n "$worktree" ] && [ -z "$resume" ]; then
  base=$(git rev-parse --verify -q HEAD) || die "--worktree needs a commit to start from"
  git worktree add -q --lock --reason "kit worker $name" "$dir" -b "worktree-$name" "$base" >&2 ||
    die "git worktree add failed: $dir"
  made=1
fi

# Codex is a native program on Windows: every path it is handed is Windows' own spelling.
if [ -n "$windows" ]; then
  wpath() { cygpath -w "$1" || die "cygpath cannot convert: $1"; }
  shown=$(cygpath -m "$brief") || die "cygpath cannot convert the brief's path: $brief"
  cdir=$(wpath "$dir")
  cquestion=$(cygpath -m "$question"); cresult=$(cygpath -m "$result")
  cworker=$(cygpath -m "$kit/codex_worker.py"); cexited=$(cygpath -m "$exited")
else
  shown=$brief; cdir=$dir; cquestion=$question; cresult=$result; cworker=$kit/codex_worker.py; cexited=$exited
fi
instruction="Read $(q "$shown") and follow it. The brief carries its Route: quick|build|deep · Risk: low|medium|high · Checks: ... line; run the checks it names. Write your result to $(q "$cresult"). Leave all work uncommitted and ready for the lead; list the exact changed and added files in the result. The result's first four lines are Kind: completed (or Kind: blocked, Kind: handoff, Kind: progress), Task: THE TASK, Attempt: N and Remaining: WHAT IS LEFT; without them the wrapper never sees the result and keeps this worker open. The lead reviews the diff through the normal cross-review, then commits with the usual commit gate. Publish a finished result atomically: write a temporary file beside it, end with <!-- codex-worker: ready -->, then rename it to the result path with $kit_python $(q "$cworker") --publish TEMPORARY_FILE DESTINATION, which retries a rename Windows refuses while a poll reads the file. If a decision is needed, finish independent work and stop all jobs first, then write Kind: blocked and QUESTIONS in the result; publish the blocked result atomically using the same temporary-file, end-marker and rename protocol before publishing the question atomically to $(q "$cquestion") using that protocol too. End your turn immediately after publishing; the wrapper allows 10 seconds to flush before closing this worker. The lead answers by resuming this same session."
# The instruction comes first, before any option, as spawn_worker.sh puts it.
# A worker is a session of its own, never the lead's child (spawn_worker.sh): clear the lead's
# Claude Code session markers, which hooks the worker starts would otherwise inherit.
unmark="env -u CLAUDE_CODE_CHILD_SESSION -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u CLAUDE_PID -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ATTENDED -u CLAUDE_CODE_ENTRYPOINT"
cmd="codex${resume:+ resume $(q "$session")} $(q "$instruction") -m $(q "$model") -c $(q "model_reasoning_effort=$effort")"
cmd="$cmd -c agents.max_concurrent_threads_per_session=2 -s workspace-write -a never --no-daemon -C $(q "$cdir")"

[ -r "$kit/codex_worker.py" ] || die "codex_worker.py is missing beside this script"
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

start=$($kit_python -I -c 'import time; print(time.time())')
stale=$($kit_python -I -c 'from pathlib import Path; import sys
try:
    print(Path(sys.argv[1]).stat().st_ino)
except FileNotFoundError:
    print(0)' "$result") || die "cannot capture the previous result identity"
session_wait=${KIT_SESSION_WAIT:-60}
case "$session_wait" in ""|*[!0-9]*) die "KIT_SESSION_WAIT must be seconds" ;; esac
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
    'began=$(date +%s)' \
    "KIT_WORKER_STARTED=$(q "$start") KIT_WORKER_STALE=$(q "$stale") KIT_WORKER_EXIT=$(q "$cexited") KIT_WORKER_RESUME=$(q "$resume") $unmark $kit_python $(q "$cworker") $(q "$cquestion") $(q "$cresult") -- $(q "$bash") -c $(q "exec $cmd")" \
    's=$?; if [ "$s" -ne 0 ] && [ "$(( $(date +%s) - began ))" -lt 10 ]; then printf "codex ended at once (exit %s); press Enter to close\\n" "$s"; read -r ignored; fi' \
    'exit 0' > "$tab" || die "cannot write the tab's script: $tab"
  spawn_launched=1
  "$wt" -w 0 new-tab --title "$(semi "$name")" "$(semi "$bash")" -l "$(semi "$(cygpath -w "$tab")")" ||
    { spawn_launched=""; rm -f -- "$tab"; die "$wt could not open a tab for '$name'"; }
  where="in a Windows Terminal tab; watch it there"; view=tab
else
  # `cd` first: tmux hands a new session the PWD of whichever client last created one.
  # The reserved script removes itself; tmux receives two plain words for its default shell.
  printf '%s\n' 'rm -f -- "$0"' "cd $(q "$dir") && exec $unmark KIT_WORKER_STARTED=$(q "$start") KIT_WORKER_STALE=$(q "$stale") KIT_WORKER_EXIT=$(q "$exited") KIT_WORKER_RESUME=$(q "$resume") $kit_python $(q "$cworker") $(q "$cquestion") $(q "$cresult") -- sh -c $(q "exec $cmd")" > "$run" ||
    { rm -f -- "$run"; die "cannot write the session's script: $run"; }
  # Keep ownership pending until tmux confirms the session, including in signal cleanup.
  launch_pending=1
  tmux new-session -d -s "$name" -c "$dir" -x 200 -y 50 "sh $run" ||
    { launch_pending=""; die "tmux could not start '$name'"; }
  tmux has-session -t "=$name" 2>/dev/null ||
    { launch_pending=""; die "tmux could not start '$name'"; }
  run="" launch_pending="" spawn_launched=1
  where="(tmux attach -t $name to watch)"; view="tmux session"
fi

if [ -z "$resume" ]; then
  i=0
  while :; do
    session=$(found "$start") || session=""
    [ -z "$session" ] && [ "$i" -lt "$session_wait" ] || break
    i=$((i + 1)); sleep 1
  done
fi
printf '%s\n' "spawn_codex: '$name' started with $brief $where"
printf '%s\n' "spawn_codex: decision file: $question; result file: $result"
result_arg=""; [ -z "$chosen_result" ] || result_arg=" --result $(q "$result")"
answer="scripts/spawn_codex.sh $name ANSWER_FILE --model $(q "$model") --effort $effort${worktree:+ --worktree}$result_arg --resume"
waiter="spawn_codex: run as a background command for the uncommitted handoff: $kit_python $(q "$cworker") --wait $(q "$cresult") --since $(q "$start") --stale $(q "$stale") --exit $(q "$cexited")"
# NAME.question names the decision file, so close_worker.sh finds a custom one too.
if [ -n "$session" ] && $kit_python -I -c 'from pathlib import Path; import sys
record = Path(sys.argv[1]); record.parent.mkdir(parents=True, exist_ok=True)
record.write_text(sys.argv[2] + "\n", encoding="utf-8")
record.with_suffix(".question").write_text(sys.argv[3] + "\n", encoding="utf-8")' "$record" "$session" "$question"; then
  spawn_recorded=1
  printf '%s\n' "spawn_codex: session $session recorded in $record"
  printf '%s\n' "spawn_codex: to answer a question it stops on, once its session has ended: $answer $(q "$session")"
elif [ -z "$session" ]; then
  # The worker runs anyway: the lead still waits on it, and answers it once it finds the id.
  printf '%s\n' "$waiter"
  die "no Codex session for '$name' showed within $session_wait s; nothing is recorded. Look at its $view; do not replace it with a fresh session. Once its id is found (in $codex_home/sessions), answer a question it stops on with: $answer SESSION_ID"
else
  # A record written before the failure stays: it is the resume handle. close_worker.sh keeps
  # it while NAME.question is empty, and without NAME.question looks only for QUESTION-NAME.md.
  printf '%s\n' "$waiter"
  qrecord=${record%.session}.question; left=""
  for f in "$record" "$qrecord"; do [ ! -e "$f" ] || left="$left $f"; done
  die "session $session was found, but writing its records failed; left:${left:- nothing}. Write $session into $record and the decision file's path $question into $qrecord, then answer a question it stops on with: $answer $(q "$session")"
fi
printf '%s\n' "spawn_codex: leave all work uncommitted and ready for the lead, with the exact files in the result; the lead cross-reviews the diff, then commits with the usual gate (issue #43)"
[ -n "$windows" ] || sh "$kit/show_workers.sh" "$name" || printf '%s\n' "spawn_codex: '$name' was not shown and runs anyway; attach by hand: tmux attach -t $name"
printf '%s\n' "$waiter"
