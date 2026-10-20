#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Open a SEPARATE Claude Code worker session in tmux and hand it a brief file. On native
# Windows (Git for Windows' sh, MSYS2, Cygwin), which has no tmux, it opens as a Windows
# Terminal tab instead (see "Native Windows" below), and what follows about showing a tmux
# session does not apply there (watching and closing have Windows paths of their own). Nothing
# can read that tab, so there the worker's --settings gain a Notification and a Stop hook (the owner's settings and
# hooks are kept; the merged file is .myagentkit/workers/NAME.settings.json) that write its
# state line, `waiting permission|question TIME ID [context_tokens=N]` or
# `idle TIME ID [context_tokens=N]`, to .myagentkit/workers/NAME.state, which watch_workers.sh
# reads in place of a pane. Worktree workers get these hooks on either platform, and their
# --settings also carries project settings absent from their checkout. The result file
# stays the done signal (owner decision 23, 2026-10-16).
# Copied project hook files are listed, by exact path, in a .claude/hooks/.gitignore of the
# worktree that ignores itself too, keeping result reports clean; never in info/exclude, which a
# linked worktree shares with the main checkout (it hid the lead's own untracked hooks there).
# Worker names use letters, digits, - and _, not starting with -. The longest generated
# filename (NAME.state.XXXXXXXX) must fit in 255 bytes; on native Windows its full path
# must fit in 259 characters too, including the checkout's .myagentkit/workers folder.
#
# Usage: spawn_worker.sh NAME BRIEF_FILE --model M --effort LEVEL [--settings JSON_OR_FILE]
#                        [--allowed-tools LIST] [--worktree] [--batch] [--backend NAME]
#                        [--result FILE] [--resume SESSION_ID]
#
# --resume SESSION_ID continues that worker's own conversation under the same NAME, with
# BRIEF_FILE holding the answer or the next step: with --worktree in its existing
# .claude/worktrees/NAME, locked again for the run. The session keeps `-n NAME`, so
# close_worker.sh and the post-merge hook find and close it. A tab opened by hand
# (`wt ... claude --resume ID`) has no name: nothing could close it, and the lead ended one
# with Stop-Process (2026-10-16). The spawn prints the id when Claude Code registered the
# session; it is also the sessionId in ${CLAUDE_CONFIG_DIR:-~/.claude}/sessions/PID.json.
# Only once the earlier session has ended: a running one with the name is refused.
#
# --backend NAME starts the worker on the endpoint that NAME.env in the backend folder names
# (claude_bridge.backends_dir(); the old .myagentkit/backends/ is read while projects move;
# docs/DEV_SETUP.md, section 3).
#
# --result FILE names the worker's result, which the instruction names to it (relative: to the
# worker's folder), else RESULT-NAME.md there. codex_worker.py supervises the session, as it
# does spawn_codex.sh's: a result published with its header (Kind/Task/Attempt/Remaining) and end marker as Kind:
# completed or Kind: handoff, or a decision published to QUESTION-NAME.md there, ends the session 10 s later,
# once no commit (index.lock) or gate (check.sh's check.lock) runs in its checkout, and its tab
# or tmux session ends with it (owner 2026-10-16: finished worker tabs stayed open for hours). A progress result or a free-form file ends nothing. The path is recorded in
# .myagentkit/workers/NAME.result-path, which close_worker.sh --finished reads after a merge.
#
# Once the worker has its brief, its session is SHOWN: show_workers.sh opens a terminal tab
# attached to it, because a session nobody sees can wait on a dialog for hours (Claude Code's
# agent teams and agent view surface a waiting session the same way). --batch skips
# that, for a lead that starts several and then shows them together in one call:
# `scripts/show_workers.sh NAME1 NAME2 ...`. A failure to show never fails the spawn: a kit
# design principle (the view is a side effect, the worker is the job), not a sourced rule.
#
# Why a separate session and not a sub-agent: a worker that waits on a long job re-writes its
# whole context after a wait its prompt cache did not outlive (docs/WORKFLOW.md, "Worker
# cost"). The worker's MAIN conversation follows `promptCacheTtl`, which the kit's
# .claude/settings.json pins to "1h" (unset it is automatic: 1 hour on a subscription within its
# usage limits, 5 minutes on an API key, Bedrock, Vertex or Foundry; CLAUDE_CODE_PROMPT_CACHE_TTL
# overrides it; Claude Code 2.1.302's settings schema). CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h
# on the launch line below covers only the worker's own sub-agents, workflows and helper
# requests; the lead's own sub-agents keep five minutes, since they rarely wait longer (#116).
# A --backend endpoint may not cache at all (#190). The start costs either way: a new session
# pays its whole first request as a cache write (about 47k to 52k tokens on five kit worker
# transcripts, mostly Claude Code's own system prompt and tools), and a sub-agent pays its own
# system prompt too, so the session's advantage is the waits, not the start (#192). A spawned
# worker skips the lead's start-up checks (doctor.sh) unless its brief asks: the lead ran them.
# The session adds visibility (`tmux attach -t NAME`) and survives the lead ending. It also sets
# MYAGENTKIT_ROLE=worker: the worker's report is for the lead, so the plain-words Stop hook
# (plain_report.py) steps aside (docs/COMMUNICATION.md, "Workers").
#
# The lead then starts the printed `sh scripts/watch_workers.sh --result NAME=PATH NAME` as ONE
# background command, on every platform: its exit is the done signal (the result file, GONE or
# WAITING), and the lead starts it again after every report but DONE and GONE. It may also
# subscribe with SendMessage `notify_when_idle` (a peer session; a tmux worker registers), but
# never relies on that alone: the supervisor's close of a finished worker often sends no idle
# notice (4 of 5 closes on 2026-10-20). It reads the result FILE the brief asks the worker to
# write. It does not poll and it does not chat with the worker: every message to an idle
# session is a full-context turn. After reading the file
# the lead reuses the session or closes it with `scripts/close_worker.sh NAME`; it ends by
# itself only on a completed result or a decision (--result above).
#
# Pitfalls this script encodes (each one cost a session):
#   - The prompt is never placed after a variadic flag (--allowedTools, --disallowedTools,
#     --tools, --add-dir, --mcp-config, --plugin-dir, --betas): it would be swallowed as one
#     more value and leave the session idle at an empty input line (claude-code issue #25978).
#     Those flags come LAST. On native Windows the prompt is the first positional argument,
#     ahead of every flag, in the script the tab runs (`claude "query"`, Claude Code CLI
#     reference). On tmux it is typed once the TUI is up: whether a first-argument prompt is
#     taken after the folder-trust dialog is not documented and untried here, so typing stays
#     until a tmux host tests it (docs/BACKLOG.md).
#   - The prompt is ONE line, "Read '<brief path>' and follow it." and then the protocol its
#     supervisor reads (#189): the result path, its four header lines and end marker, the
#     publish through codex_worker.py --publish, and the question path in place of asking in the
#     pane; not the brief pasted as a block: one model took a pasted brief with no typed
#     sentence of the user's own for mere content and sat idle for 35 minutes asking for
#     confirmation. --disallowedTools AskUserQuestion enforces the question rule.
#   - Every wait below (60 s for the input line, 30 s for the line to land, 3 s before a second
#     Enter, 30 s for a Windows process and its registration, 10 s for a quick exit) is a
#     bound, not a measurement: the poll ends as soon as its condition holds (owner's choice).
#   - tmux receives only `sh PATH`, without quotes, for its default shell (fish included).
#     Before worktree creation, the temporary script path is made absolute and checked for
#     letters, digits, _, ., / and -. Set TMPDIR to an existing safe absolute directory
#     and retry if refused; the template honours TMPDIR on macOS and Linux alike.
#   - Every value that goes into the temporary script's shell command, and the brief path, passes
#     through `q`: a value with an apostrophe (a --settings JSON string) otherwise
#     ends its quoting and the rest runs as shell in the new pane.
#   - --worktree makes the worktree here with `git worktree add` from the commit the lead's
#     checkout is on now. Passing `-w` to the tool built it from a stale base, and workers
#     started without fixes the lead had already merged: `-w` branches from the remote default
#     branch unless `worktree.baseRef: head` is set, and that has had bugs across versions
#     (code.claude.com/docs/en/worktrees, "Choose the base branch").
#   - Readiness is detected from the pane text, not from `pgrep -f`, which matches its own
#     command line.
#   - The folder must already be trusted by Claude Code; an untrusted folder blocks the
#     session in the trust dialog, which this script reports instead of waiting forever. The
#     dialog is recognised by watch_workers.sh --once from waiting_patterns.txt, the same
#     definition the lead's watcher uses, and so is a session that exited during start-up.
set -eu

# Every message is printed with its control bytes as `?`: a value echoed raw (an unknown
# option, a --settings value) put ESC sequences on the lead's terminal.
die() { { printf 'spawn_worker: %s' "$1" | LC_ALL=C tr '\001-\037\177' '?'; echo; } >&2; stranded; exit 1; }
# A spawn that fails once its session was started leaves the worktree to that session, which may
# still run there (a tab waiting on Enter, a slow start, a dialog): the lead is told how to
# remove it, as the audit keeps a worktree no worker committed in. Before that, cleanup removes it.
stranded() {
  [ -n "${made:-}" ] && [ -n "${launched:-}" ] || return 0
  printf '%s\n' "spawn_worker: the worktree $dir stays (locked: kit worker $name) while its session may run; once it has ended, run scripts/close_worker.sh $name; it removes the worktree only when no work would be lost, so never remove it by hand with --force" >&2
}
# Quote one value for a POSIX shell: wrap it in '...' and write each ' inside as '\''.
# The x keeps a trailing newline that $(...) would strip.
q() { set -- "$(printf '%sx' "$1" | sed "s/'/'\\\\''/g")"; printf "'%s'" "${1%x}"; }

[ $# -ge 2 ] || { sed -n '3,23p' "$0"; exit 2; }
name=$1; brief=$2; shift 2
# The name and the brief path reach tmux and the TUI: `send-keys -l` types every byte, and a
# control byte (0x01-0x1F, 0x7F) acts as a key there: a carriage return submitted the
# instruction early, ESC edits it. Refused by name, checked on bytes, FIRST: before any other
# check prints the argument and before any tmux call. The message names the argument, never
# its bytes.
ctl() {
  [ "$(printf '%sx' "$2" | LC_ALL=C tr -d '\001-\037\177')" = "${2}x" ] ||
    die "the $1 contains a control character (a newline, carriage return, tab, ESC or DEL), which the worker's input line would act on; it is not printed"
}
# Checked in the argument itself, before anything rewrites it: $(...) strips trailing
# newlines, and "task.md<newline>" was checked while "task.md" was handed over. The folder
# and file name are split by parameter expansion, which keeps every byte, and the folder's
# absolute path keeps a trailing newline through the x guard; the resolved path is checked again.
ctl "worker name" "$name"
case $name in
  ''|-*|*[!ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-]*)
    die "refused the worker name: use letters, digits, - and _, not starting with -" ;;
esac
longest=$name.state.XXXXXXXX
[ "${#longest}" -le 255 ] || die "refused the worker name: generated filenames must fit in 255 bytes (at most 240 characters in the name); use a shorter name"
ctl "brief path" "$brief"
nl='
'
case $(uname -s 2>/dev/null) in MINGW*|MSYS*|CYGWIN*) windows=1 ;; *) windows="" ;; esac
# Git for Windows' sh takes C:\dir\brief.md too, but the split below is at `/` only: there
# every backslash is a separator, spelled `/` first. The x guard keeps a trailing newline.
if [ -n "$windows" ]; then brief=$(printf '%sx' "$brief" | tr '\\' '/') && brief=${brief%x}; fi
{ [ -f "$brief" ] && [ -r "$brief" ]; } || die "brief file not found or not readable: $brief"
case "$brief" in */*) brief_dir=${brief%/*}/ ;; *) brief_dir=. ;; esac
# Every path handed on is physical (`pwd -P`): a plain `pwd` printed the logical path when the
# caller exported a matching PWD and the physical one otherwise, so the same brief was named
# /var/... by one caller and /private/var/... by another on macOS.
brief_dir=$(CDPATH= cd -P -- "$brief_dir" && pwd -P && echo x) || die "cannot resolve the brief's folder: $brief"
brief=${brief_dir%"${nl}x"}/${brief##*/}
ctl "brief path" "$brief"
[ -n "$windows" ] || command -v tmux >/dev/null || die "tmux is not installed"
command -v claude >/dev/null || die "claude is not on PATH"

model=""; settings=""; tools=""; worktree=""; effort=""; batch=""; backend=""; resume=""; result=""
# Git for Windows' dirname handles both separators, including mixed paths such as D:/p\scripts\x.sh.
case $0 in *'\'*) kit=$(dirname -- "$0") ;; */*) kit=${0%/*} ;; *) kit=. ;; esac
while [ $# -gt 0 ]; do
  case "$1" in
    --model)         model=$2; shift 2 ;;
    --settings)      settings=$2; shift 2 ;;
    --allowed-tools) tools=$2; shift 2 ;;
    --worktree)      worktree=1; shift ;;
    --effort)        effort=$2; shift 2 ;;
    --batch)         batch=1; shift ;;
    --backend)       backend=$2; shift 2 ;;
    --result)        result=${2-}; [ -n "$result" ] || die "--result needs a file"; shift 2 ;;
    --resume)        case ${2-} in ""|-*) die "--resume needs the session id of the worker's conversation: --resume SESSION_ID" ;; esac
                     resume=$2; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
# The lead picks both for every worker (docs/WORKFLOW.md, "Model routing"); left out, the
# session silently took the user's default.
[ -n "$model" ] || die "--model is required: the lead picks the model for every worker"
[ -n "$effort" ] || die "--effort is required: the lead picks the effort for every worker"
ctl "session id" "$resume"
ctl "result path" "$result"

[ -n "$windows" ] || ! tmux has-session -t "=$name" 2>/dev/null || die "tmux session '$name' already exists"

run=""; launch_pending=""; cleaned=""; made=""; launched=""; base=""
cleanup() {
  [ -z "$cleaned" ] || return 0
  cleaned=1
  trap - EXIT HUP INT TERM
  # A signal may arrive before new-session returns. Only a confirmed session owns the script.
  # The session can end between this check and handoff; its pane removes the script itself.
  if [ -n "$launch_pending" ] && tmux has-session -t "=$name" 2>/dev/null; then run=""; launched=1; fi
  [ -z "$run" ] || rm -f -- "$run" || :
  # A spawn that stops after making its worktree and before any session runs in it removes the
  # worktree and its branch: the audit keeps a locked worktree, and one no worker committed in,
  # for good, and the branch blocked the name (ultrareview part 5 #8). The branch goes only while
  # it is still the commit it was made at (update-ref's old-value check).
  if [ -n "$made" ] && [ -z "$launched" ] &&
     { [ -e "$dir" ] || git show-ref --verify --quiet "refs/heads/worktree-$name"; }; then
    # The branch goes only with the worktree this add registered; an add that registered none
    # leaves the empty folder it claimed, removed, and a branch someone else may have made, kept.
    if git worktree remove -f -f "$dir" >/dev/null 2>&1; then
      if git update-ref -d "refs/heads/worktree-$name" "$base" 2>/dev/null; then
        printf '%s\n' "spawn_worker: removed the unused worktree $dir and its branch worktree-$name; the name is free again" >&2
      else
        printf '%s\n' "spawn_worker: removed the unused worktree $dir; its branch worktree-$name moved or is gone, so it is kept" >&2
      fi
    elif rmdir -- "$dir" 2>/dev/null; then
      printf '%s\n' "spawn_worker: removed the empty folder $dir it claimed; a branch worktree-$name, if any, is not this spawn's to delete" >&2
    else
      printf '%s\n' "spawn_worker: could not remove the unused worktree $dir; remove it by hand: git worktree remove --force --force $(q "$dir") && git update-ref -d refs/heads/worktree-$name $base" >&2
    fi
  fi
}
trap 'cleanup' 0
trap 'trap - 0; cleanup; exit 129' HUP
trap 'trap - 0; cleanup; exit 130' INT
trap 'trap - 0; cleanup; exit 143' TERM
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

here=$(pwd -P && echo x) || die "cannot resolve the current folder"
dir=${here%"${nl}x"}
# The kit's behaviour appendix reaches the worker as system-prompt text: BEHAVIOUR.md here, or
# core/BEHAVIOUR.md in the kit's own checkout. MYAGENTKIT_NO_BEHAVIOUR=1 leaves it out (an A/B).
behaviour=""
if [ "${MYAGENTKIT_NO_BEHAVIOUR:-}" != 1 ]; then
  for f in "$dir/BEHAVIOUR.md" "$dir/core/BEHAVIOUR.md"; do
    if [ -f "$f" ]; then behaviour=$f; break; fi
  done
fi
# The existing Python selector is also used by the backend reader on either platform.
if python3 -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python3
elif python -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python
else kit_python="py -3"; fi   # unquoted at every use
# Validate here, then read again in the child at start. The launch script/command holds
# only the reader and paths, never backend values. Both entry points use load_backend's
# grammar, privacy checks, regular-file check and bounded read.
if [ -n "$backend" ]; then
  case "$model" in claude-*) die "--backend requires a backend model id or a mapped alias, not a claude- model" ;; esac
  backend_repo=$dir
  backend_scripts=$(CDPATH= cd -P -- "$kit" && pwd -P && echo x) || die "cannot resolve the review companion folder"
  backend_scripts=${backend_scripts%"${nl}x"}
  backend_reader='if 1:
    import os, shlex, subprocess, sys
    from pathlib import Path
    if os.name == "nt":
        sys.argv[1:3] = [subprocess.check_output(["cygpath", "-m", p], text=True).rstrip("\r\n")
                         for p in sys.argv[1:3]]
    sys.path.insert(0, sys.argv[1])
    from review_dispatch import load_backend, BACKEND_CLEAR_KEYS
    try:
        values, model = load_backend(Path(sys.argv[2]), sys.argv[3])
    except (OSError, ValueError) as error:
        print("spawn_worker: " + str(error), file=sys.stderr)
        sys.exit(1)
    if len(sys.argv) > 4:
        # Captured and evaluated only in the child shell, never put in a launch argument.
        # Read raw shell names: Windows os.environ uppercases them, so an unset generated
        # from it missed an inherited mixed-case name in Git Bash.
        raw = sys.stdin.buffer.read()
        if not raw.endswith(b"\0"):
            print("spawn_worker: cannot read the child environment names", file=sys.stderr)
            sys.exit(1)
        keys = []
        for entry in raw.split(b"\0"):
            key = os.fsdecode(entry.partition(b"=")[0])
            match = key.upper() if os.name == "nt" else key
            if match.startswith("ANTHROPIC_") or match in BACKEND_CLEAR_KEYS:
                keys.append(key)
        print("unset " + " ".join(shlex.quote(k) for k in keys))
        for key, value in values.items():
            print("export " + key + "=" + shlex.quote(value))'
  $kit_python -I -c "$backend_reader" "$backend_scripts" "$backend_repo" "$backend" || exit 1
fi
backend_command() {
  read_cmd="env -0 | $kit_python -I -c $(q "$backend_reader") $(q "$backend_scripts") $(q "$backend_repo") $(q "$backend") export"
  # Python ends after reading; the child shell exports the result and execs the TUI, so
  # no waiting Python process can intercept the worker's Ctrl-C.
  printf '%s' "sh -c $(q "set -e; backend_values=\$($read_cmd) || exit 1; eval \"\$backend_values\"; unset backend_values; exec $1")"
}
# --settings is inline JSON or a file. The tool starts in the worktree, so a relative file is
# made absolute here, against the caller's folder: resolved there, an untracked settings file
# was missing and a tracked one of the same name was loaded instead. A relative value that is
# neither is refused for the same reason. The other values name no file: the brief is
# absolute already, and --allowed-tools patterns are meant for the worker's own tree.
# JSON may start with whitespace: only a leading `{` counted, and ' {"model":"x"}' was refused
# as a file name with --worktree. JSON's four whitespace characters (space, tab, LF, CR)
# before the `{` mark it inline, and the value is passed on unchanged.
case $settings in [a-zA-Z]:\\*) settings=$(printf '%s' "$settings" | tr '\\' '/') ;; esac
ws=" $(printf '\t\r')$nl"
lead=${settings%%[!$ws]*}
case "$settings" in
  ""|"$lead{"*|/*|[a-zA-Z]:/*) ;;
  *) [ -f "$settings" ] || [ -z "$worktree" ] ||
       die "--settings is neither inline JSON nor a file here, and the worktree could hold another: $settings"
     [ ! -f "$settings" ] || settings=$dir/$settings ;;
esac
# again: the launch's own options, for the printed resume command: one that left out --backend
# (or --settings, --allowed-tools) resumed the worker on another provider (Codex review).
again="--model $(q "$model") --effort $(q "$effort")${worktree:+ --worktree}"
[ -z "$backend" ]  || again="$again --backend $(q "$backend")"
[ -z "$settings" ] || again="$again --settings $(q "$settings")"
[ -z "$tools" ]    || again="$again --allowed-tools $(q "$tools")"
[ -z "$result" ]   || again="$again --result $(q "$result")"
# Validate the lead checkout's generated paths before creating a worktree or worker files.
wdir=$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)/.myagentkit/workers
project_settings=$dir/.claude/settings.json
if [ -n "$windows" ]; then
  longest_path=$(cygpath -m "$wdir/$longest") || die "cygpath cannot convert the path: $wdir"
  [ "${#longest_path}" -le 259 ] ||
    die "refused the worker path: generated paths must fit in 259 characters on native Windows (MAX_PATH 260); use a shorter name or a shorter checkout path, or enable LongPathsEnabled for long-path tooling"
fi
# The spend line, as review.sh prints its own before a review: the owner sees what each worker
# costs before it runs (issue #68; docs/WORKFLOW.md, "Model routing").
printf '%s\n' "spawn_worker: about to run '$name': model $model, effort $effort" | LC_ALL=C tr '\001-\011\013-\037\177' '?'
if [ -n "$worktree" ]; then
  top=$(git rev-parse --show-toplevel) || die "--worktree needs a git repository"
  project_settings=$top/.claude/settings.json
  dir=$top/.claude/worktrees/$name
  if [ -n "$resume" ]; then
    [ -d "$dir" ] || die "--resume --worktree: no worktree at $dir"
  else
    ! git show-ref --verify --quiet "refs/heads/worktree-$name" ||
      die "branch worktree-$name already exists and may be stale; delete it or pick another name"
    [ ! -e "$dir" ] || die "worktree path already exists: $dir"
  fi
fi
# The first line of the ignore file for copied hooks (close_worker.sh compares it).
hooks_mark="# spawn_worker.sh: hook files copied from the lead's checkout; close_worker.sh sets this file aside"
prepare_worktree() {
  [ -n "$worktree" ] || return 0
  # Settings have been validated before a locked worktree or branch is created.
  # Locked from spawn to close_worker.sh, which unlocks it: the worktree audit never removes a
  # locked worktree, so no clean-up races a live worker, as Claude Code locks its own agents'
  # worktrees while they run (code.claude.com/docs/en/worktrees). The quiet period stays as the
  # second check for worktrees no kit script locked. `add --lock --reason` needs git 2.33
  # (its release notes); the audit already needs 2.36.
  if [ -z "$resume" ]; then
    base=$(git rev-parse --verify -q HEAD) || die "--worktree needs a commit to start from"
    # The folder is claimed before the add: mkdir without -p fails when it exists, so of two
    # spawns of one name only one gets it, and only that one may remove anything (Codex r2: a
    # spawn that lost the race removed the winner's worktree). `git worktree add` takes the empty
    # folder. A failing post-checkout hook makes the add exit non-zero with both made: cleanup.
    ! git show-ref --verify --quiet "refs/heads/worktree-$name" ||
      die "the branch worktree-$name appeared before this spawn made it; nothing was changed"
    mkdir -p -- "${dir%/*}" && mkdir -- "$dir" 2>/dev/null ||
      die "the folder $dir exists: another spawn of '$name' claimed it; nothing was changed"
    made=1
    git worktree add -q --lock --reason "kit worker $name" "$dir" -b "worktree-$name" "$base" >&2 ||
      die "git worktree add failed: $dir"
  # A resumed worker is locked again: a close lifted the lock, and the audit must not remove the
  # worktree under the new run. A lock someone else set stays as it is.
  elif ! gd=$(git -C "$dir" rev-parse --absolute-git-dir) ||
       { [ ! -e "$gd/locked" ] && ! git worktree lock --reason "kit worker $name" "$dir"; }; then
    die "--resume --worktree: cannot lock $dir for the resumed worker"
  fi
  # Untracked kit installs carry settings and hooks together. Fill missing hook files,
  # preserving the committed versions already present in the worker's checkout.
  if [ -d "${project_settings%/*}/hooks" ]; then
    # The copies are ignored by a .claude/hooks/.gitignore that lists them and itself, written
    # only where the worktree has none (a tracked or copied one stays as it is, and the copies
    # then show as untracked). Its exact bytes are recorded in NAME.hooks-ignore-spawned:
    # close_worker.sh sets it aside for the audit only while it is still byte for byte that.
    $kit_python -I -c 'import os, shutil, sys
from pathlib import Path
hooks = Path(sys.argv[2])
copied = []
def missing(source, destination):
    if not os.path.lexists(destination):
        shutil.copy2(source, destination)
        copied.append(Path(destination).relative_to(hooks).as_posix())
shutil.copytree(sys.argv[1], sys.argv[2], dirs_exist_ok=True, copy_function=missing)
ignore, record = hooks / ".gitignore", Path(sys.argv[4])
if not sys.argv[5] and os.path.lexists(record):
    record.unlink()  # a fresh spawn: an earlier run of the name left it; a resume keeps its own
if copied and not os.path.lexists(ignore):
    text = sys.argv[3] + "\n/.gitignore\n" + "".join(
        "/" + "".join("\\" + ch if ch in "\\*?[ " else ch for ch in name) + "\n" for name in copied)
    with ignore.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    record.parent.mkdir(parents=True, exist_ok=True)
    with record.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
elif copied:
    print("spawn_worker: the worktree has its own .claude/hooks/.gitignore; the hook files copied into it show as untracked there", file=sys.stderr)' \
      "${project_settings%/*}/hooks" "$dir/.claude/hooks" "$hooks_mark" "$wdir/$name.hooks-ignore-spawned" "$resume" ||
      die "cannot carry project hooks into $dir"
  fi
}

# The result and the supervisor (--result in the header). Absolute paths: the session starts in
# the worker's folder.
[ -n "$result" ] || result=RESULT-$name.md
[ -z "$windows" ] || result=$(printf '%s' "$result" | tr '\\' '/')
case $result in /*|[a-zA-Z]:/*) ;; *) result=$dir/$result ;; esac
[ -r "$kit/codex_worker.py" ] || die "codex_worker.py is missing beside this script"
cworker=$(CDPATH= cd -P -- "$kit" && pwd -P)/codex_worker.py || die "cannot resolve the folder of codex_worker.py"
cresult=$result; cquestion=$dir/QUESTION-$name.md
# A fresh spawn's supervisor refuses a leftover question deep in its start, where a tmux pane
# closed with the error (#235): it is refused here, before any worktree, tab or session. Only a
# spawn without --worktree can meet one: a fresh worktree is a new folder.
[ -n "$resume" ] || [ ! -e "$cquestion" ] ||
  die "QUESTION-$name.md from an earlier run is unanswered in $dir: answer it with --resume SESSION_ID, or remove it once it is settled"
if [ -n "$windows" ]; then
  { cworker=$(cygpath -m "$cworker") && cresult=$(cygpath -m "$result") && cquestion=$(cygpath -m "$cquestion"); } ||
    die "cygpath cannot convert the result's path: $result"
fi
# The run starts once its worktree exists (#168): a committed result that the checkout wrote is
# older than the start, so the supervisor takes it for an earlier run's and never as this run's DONE.
supervisor() {
  start=$($kit_python -I -c 'import time; print(time.time())')
  supervise="KIT_WORKER_STARTED=$(q "$start")${resume:+ KIT_WORKER_RESUME=1} $kit_python $(q "$cworker") $(q "$cquestion") $(q "$cresult") --"
}
# Written once the name is known to be free: a running worker's record is never replaced.
record_result() {
  mkdir -p -- "$wdir" && printf '%s\n' "$cresult" > "$wdir/$name.result-path" ||
    die "cannot record the result path in $wdir"
}

# Worktree sessions read shared project settings from their own working directory
# (https://code.claude.com/docs/en/settings, checked 2026-10-16). Tracked settings arrive
# with the checkout; absent settings must travel in --settings, with the owner's overrides
# and hooks kept. Hook commands retain $CLAUDE_PROJECT_DIR and run in the worker.
# Both worktree sessions and Windows tabs get state telemetry (owner decision 23, 2026-10-16).
native() { if [ -n "$windows" ]; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
own=$settings
if [ -n "$windows$worktree" ]; then
  settings=$(native "$wdir/$name.settings.json") || die "cannot convert the path: $wdir"
fi
prepare_settings() {
  hook=$kit_python' -I -c '$(q 'import importlib.util, json, os, sys, tempfile, time
sys.dont_write_bytecode = True  # Loading telemetry must not create untracked hook caches.
e = json.loads(sys.stdin.buffer.read() or b"{}")
m = str(e.get("message", "")).lower()
s = {"permission_prompt": "waiting permission", "elicitation_dialog": "waiting question"}.get(e.get("notification_type"), "")
if "notification_type" not in e:
    s = "waiting question" if "question" in m else "waiting permission" if "permission" in m or "approval" in m else ""
s = "idle" if e.get("hook_event_name") == "Stop" else s
if s:
    extra = ""
    try:
        spec = importlib.util.spec_from_file_location("context_size", sys.argv[2])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tokens, _ = module.context(e["transcript_path"], require_request=True)
        if type(tokens) is int and tokens >= 0:
            extra = " context_tokens=" + str(tokens)
    except Exception:
        pass  # Telemetry never prevents the state event when the transcript is unavailable.
    d, b = os.path.split(sys.argv[1])
    f = tempfile.NamedTemporaryFile(mode="w", dir=d, prefix=b + ".", delete=False, newline="")
    try:
        with f:
            f.write(s + time.strftime(" %Y-%m-%dT%H:%M:%S") + " " + str(time.time_ns()) + extra + chr(10))
        os.replace(f.name, sys.argv[1])
    finally:
        if os.path.exists(f.name): os.unlink(f.name)')' '$(q "$(native "$wdir/$name.state")")' '$(q "${cworker%/*}/../.claude/hooks/context_size.py")
  project=""
  # Do not duplicate a tracked project's hooks: Claude Code already loads that file.
  if [ -n "$worktree" ] && [ -f "$project_settings" ]; then
    # A fresh checkout does not exist yet: inspect its commit, not the absent folder.
    if { [ -n "$resume" ] && [ ! -e "$dir/.claude/settings.json" ]; } ||
       { [ -z "$resume" ] && ! git cat-file -e HEAD:.claude/settings.json 2>/dev/null; }; then
      project=$(native "$project_settings") || die "cannot convert the project settings path"
    fi
  fi
  mkdir -p -- "$wdir" || die "cannot prepare $wdir"
  { case $own in "") echo '{}' ;; "$lead{"*) printf '%s' "$own" ;; *) cat -- "$own" ;; esac; } |
    $kit_python -I -c 'if 1:
    import json, sys
    def merge(base, override):
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                merge(base[key], value)
            elif key in base and isinstance(base[key], list) and isinstance(value, list):
                base[key] += [item for item in value if item not in base[key]]
            else:
                base[key] = value
        return base
    owner = json.loads(sys.stdin.buffer.read())
    project = json.load(open(sys.argv[2], encoding="utf-8-sig")) if sys.argv[2] else {}
    if not isinstance(owner, dict) or not isinstance(project, dict):
        raise ValueError("settings must be JSON objects")
    d = merge(project, owner)
    h = d.setdefault("hooks", {})
    for e in ("Notification", "Stop"):
        h.setdefault(e, []).append({"hooks": [{"type": "command", "command": sys.argv[1]}]})
    print(json.dumps(d, indent=2))' "$hook" "$project" >"$wdir/$name.settings.json" ||
    die "cannot merge the project and worker hooks into --settings (not a JSON object?): $own"
}
reset_state() {
  # All launches, including plain tmux sessions, begin without the previous run's snapshot.
  rm -f -- "$wdir/$name".state* "$wdir/$name".watch-* "$wdir/$name.pid" "$wdir/$name.exit" "$wdir/$name.live" ||
    die "cannot clear the previous state in $wdir"
}
# A worker is a session of its own, never the lead's child. The lead's shell carries Claude
# Code's child-session markers, and a claude that sees CLAUDE_CODE_CHILD_SESSION skips its peer
# registration (no sessions/<pid>.json: ListAgents never lists the worker, SendMessage cannot
# reach it). tmux ignores the marker, a Windows Terminal tab does not, so both paths clear them.
# CLAUDE_CLI_BIN and CLAUDE_CODE_EXECPATH name the binary and stay.
unmark="env -u CLAUDE_CODE_CHILD_SESSION -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u CLAUDE_PID -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ATTENDED -u CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h MYAGENTKIT_ROLE=worker"

# Variadic flags come LAST and the prompt is never on this line (see the header).
cmd="claude -n $(q "$name")${resume:+ --resume $(q "$resume")}"
[ -n "$model" ]    && cmd="$cmd --model $(q "$model")"
[ -n "$effort" ]   && cmd="$cmd --effort $(q "$effort")"
[ -n "$settings" ] && cmd="$cmd --settings $(q "$settings")"
if [ -n "$behaviour" ]; then
  [ -z "$windows" ] || behaviour=$(cygpath -m "$behaviour") || die "cygpath cannot convert the behaviour appendix's path"
  cmd="$cmd --append-system-prompt-file $(q "$behaviour")"
fi
printf '%s' "spawn_worker: behaviour appendix: ${behaviour:-off}" | LC_ALL=C tr '\001-\037\177' '?'
printf '\n'
[ -n "$tools" ]    && cmd="$cmd --allowedTools $(q "$tools")"
# No question dialog in a pane nobody may watch: QUESTION-NAME.md is the question channel (the
# instruction says so; this enforces it). Permission prompts are not tools and
# stay. AskUserQuestion is the tool's name in Claude Code 2.1.300 (code.claude.com/docs/en/sub-agents).
cmd="$cmd --disallowedTools AskUserQuestion"
# One line naming the brief by its absolute path, quoted by the same helper so a path with a
# space or an apostrophe still reads as one path. The rest is the protocol codex_worker.py
# reads (#189): a result without its header and marker, or not renamed into place, is never
# seen, and only a published question ends the session for the lead; it keeps questions out of
# the pane, where nobody may be looking. On native Windows every path is Windows' own spelling:
# Git Bash's /tmp/... is a folder the worker's tools do not know.
[ -z "$windows" ] || brief=$(cygpath -m "$brief") || die "cygpath cannot convert the brief's path: $brief"
instruction="Read $(q "$brief") and follow it. Your result file is $(q "$cresult"): its first four lines are Kind: completed (or Kind: blocked, Kind: handoff, Kind: progress), Task: THE TASK, Attempt: N and Remaining: WHAT IS LEFT, and its last line is <!-- codex-worker: ready -->; publish it whole, as a temporary file beside it renamed over it with $kit_python $(q "$cworker") --publish TEMPORARY_FILE DESTINATION: without them the supervisor never sees it. A published completed or handoff result ends this session 10 seconds later, once no commit or gate runs. Do not ask questions in this pane: for a decision, stop your jobs, publish a Kind: blocked result and then the question, the same way, to $(q "$cquestion"), which ends this session for the lead's answer; until then go on with what does not depend on it."

# Native Windows: no tmux, so nothing can type into the session or read its pane. The worker
# opens as a Windows Terminal tab (KIT_WT names another launcher, as for show_workers.sh) with
# the instruction as its first prompt, BEFORE the variadic flags; it is visible from the start,
# so it is not shown again, and the lead watches the tab and waits for the result file. Two
# faults, each of which left the tab with an error and no worker: a bare `bash` in a new tab
# is WSL's launcher (WindowsApps\bash.exe), so Git Bash is named by its full Windows path; and
# wt.exe splits its command line at every `;` (a new-tab separator), even inside quotes, and
# cut the instruction in two, so every `;` it is handed is escaped as `\;`. The tab's command
# ends with `exit 0`, not an exec of claude: Windows Terminal keeps a tab open, with "[process
# exited with code 1]", when its command ends nonzero, as claude does when close_worker.sh ends
# it. A name a running session already has is refused, as tmux refuses a second session.
# Native Windows (Git for Windows' sh, MSYS2, Cygwin): no tmux; a worker is a Windows Terminal
# tab running `claude -n NAME` (spawn_worker.sh). sessions NAME prints, on one line, the process
# id of each Claude Code process whose arguments hold `-n NAME`: a claude.exe, or a node.exe
# running Claude Code's cli.js (an npm install of `claude`). The command line Win32_Process
# gives is split as Windows splits it (CommandLineToArgvW's rules), so `-n w1` inside a quoted
# prompt is part of the prompt, never the name: read as words, it closed the wrong worker.
# KIT_PS names another lister (the kit's tests), printing "<pid> <command line>" lines as this
# one does. A command line Windows does not show (another user's process) names nothing. A
# lister that fails prints its words instead and returns 2.
sessions() {
  out=$(${KIT_PS:-powershell.exe -NoProfile -NonInteractive -Command} \
    "Get-CimInstance Win32_Process -Filter \"Name='claude.exe' or Name='node.exe'\" | ForEach-Object { \"\$(\$_.ProcessId) \$(\$_.CommandLine)\" }" \
    2>&1) || { printf '%s' "$out"; return 2; }
  printf '%s\n' "$out" | $kit_python -I -c 'if 1:
    import ntpath, sys
    def split(line):
        # CommandLineToArgvW: 2n backslashes and a quote are n and a toggle, 2n+1 are n and a
        # literal quote, "" inside quotes is a quote; any other backslash is itself.
        args, cur, have, quoted, i = [], [], False, False, 0
        while i < len(line):
            c = line[i]
            if c == "\\":
                n = len(line[i:]) - len(line[i:].lstrip("\\"))
                i += n
                if line[i:i + 1] == "\"":
                    cur.append("\\" * (n // 2))
                    if n % 2:
                        cur.append("\"")
                        i += 1
                else:
                    cur.append("\\" * n)
                have = True
            elif c == "\"":
                if quoted and line[i + 1:i + 2] == "\"":
                    cur.append("\"")
                    i += 1
                else:
                    quoted = not quoted
                have, i = True, i + 1
            elif c in " \t" and not quoted:
                if have:
                    args.append("".join(cur))
                cur, have, i = [], False, i + 1
            else:
                cur.append(c)
                have, i = True, i + 1
        if have:
            args.append("".join(cur))
        return args
    pids = []
    for line in sys.stdin.read().replace("\r", "").split("\n"):
        pid, _, command = line.strip().partition(" ")
        argv = split(command)
        if not pid.isdigit() or not argv:
            continue
        exe = ntpath.basename(argv[0]).lower()
        if exe == "claude.exe" or exe == "claude":
            rest = argv[1:]
        elif exe in ("node.exe", "node") and len(argv) > 1 and \
                argv[1].replace("\\", "/").lower().split("/")[-3:] == ["@anthropic-ai", "claude-code", "cli.js"]:
            rest = argv[2:]
        else:
            continue
        if any(a in ("-n", "--name") and b == sys.argv[1] for a, b in zip(rest, rest[1:])):
            pids.append(pid)
    sys.stdout.write(" ".join(pids))' "$1"
}
# The disk is the done signal on every platform: a supervised close often sends no idle notice
# (4 of 5 on 2026-10-20), so the watch comes first, before the optional subscription.
watch_line() {
  printf '%s\n' "spawn_worker: watch it now, as ONE background command whose exit is the done signal (start it again after every report but DONE and GONE): sh scripts/watch_workers.sh --result $name=$(q "$cresult") $name"
}
if [ -n "$windows" ]; then
  running=$(sessions "$name") || die "cannot list the Claude Code sessions to check the name '$name': $running"
  [ -z "$running" ] || die "a Claude Code session named '$name' already runs (process $running)"
  prepare_settings
  prepare_worktree
  supervisor
  reset_state
  record_result
  wt=${KIT_WT:-wt.exe}
  command -v "$wt" >/dev/null || die "Windows Terminal ($wt) is not on PATH; start the worker by hand: $cmd"
  bash=$(command -v bash) || die "bash is not on PATH"
  bash=$(cygpath -w "$bash") || die "cygpath cannot convert the path of bash: $bash"
  semi() { printf '%s' "$1" | sed 's/;/\\;/g'; }
  # wt.exe also drops every double quote it is handed: inline --settings JSON reached claude
  # as {permissions:{defaultMode:auto}}, claude refused it, and the tab closed before anyone
  # saw why. So the tab's command goes into a script the tab runs and deletes, and only paths
  # pass through wt.exe. A claude that ends within ten seconds of its own start, whatever its
  # status, failed to start: the tab then waits for Enter, so its error stays on screen. One
  # its supervisor ended on a published result (its exit record says so) closes at once. The
  # exit record is NAME.exit in the workers folder, and the supervisor holds NAME.live locked
  # while it runs: both stay after the tab, so watch_workers.sh sees a worker that ended (#185);
  # the next spawn of the name clears them (reset_state).
  tab=$(mktemp) || die "cannot write the tab's script"
  tab_cmd="$unmark claude $(q "$instruction") ${cmd#claude }"
  [ -z "$backend" ] || tab_cmd=$(backend_command "$tab_cmd")
  tab_cmd="KIT_WORKER_EXIT=$(q "$(native "$wdir/$name.exit")") $supervise $(q "$bash") -c $(q "exec $tab_cmd")"
  printf '%s\n' 'rm -f -- "$0"' "cd $(q "$dir") || exit 1" \
    "t=\$(date +%s); $tab_cmd; s=\$?; grep -q ' published at ' $(q "$wdir/$name.exit") 2>/dev/null || [ \$((\$(date +%s) - t)) -gt 10 ] || { echo \"claude ended at once (exit \$s); press Enter to close\"; read -r _; }" \
    'exit 0' > "$tab" || die "cannot write the tab's script: $tab"
  # From here a session may run in the worktree: a failure leaves it there (stranded above).
  launched=1
  "$wt" -w 0 new-tab --title "$(semi "$name")" "$(semi "$bash")" -l "$(semi "$(cygpath -w "$tab")")" ||
    { launched=""; rm -f -- "$tab"; die "$wt could not open a tab for '$name'"; }
  # The lead can message a worker and hear when it stops (SendMessage notify_when_idle) only
  # when Claude Code registers it as a peer: sessions/<pid>.json in its config folder. A tab
  # that inherited the lead's child-session markers was not registered (2026-10-08; the tab's
  # script now clears them): one that stopped on a usage limit waited unseen for hours. So the
  # spawn waits up to 30 s for the process and its registration, fails when no process starts
  # (the tab shows why), and says so when it is not registered.
  i=0; pids=""
  while [ "$i" -lt 30 ]; do
    pids=$(sessions "$name") || pids=""
    [ -z "$pids" ] || break
    i=$((i + 1)); sleep 1
  done
  [ -n "$pids" ] || die "no Claude Code session named '$name' started within 30 s; its tab shows why"
  # The name was free machine-wide before the launch (above), so a session found now started
  # since: close_worker.sh ends only the recorded id, never another project's session of the
  # name (#171). Two of them mean another one started in the same moment, and which is this
  # checkout's cannot be told: none is recorded. ponytail: one other that starts alone while
  # this claude is not yet listed is still taken for this worker; a launch-time id would end that.
  case $pids in
    *' '*) printf '%s\n' "spawn_worker: NOTE: more than one Claude Code session named '$name' started (processes $pids), another checkout's perhaps, so none is recorded as this checkout's: close_worker.sh will not end '$name'; quit its tab by hand once it is finished, then close it" ;;
    *) printf '%s\n' "$pids" > "$wdir/$name.pid" || die "cannot record the session's process id in $wdir" ;;
  esac
  reg=${CLAUDE_CONFIG_DIR:-$HOME/.claude}/sessions
  peer=""
  # The listing is taken again on every round: a worker that ended meanwhile did not start.
  while :; do
    pids=$(sessions "$name") || pids=""
    [ -n "$pids" ] || die "the Claude Code session '$name' ended right after it started; its tab shows why"
    for pid in $pids; do [ ! -f "$reg/$pid.json" ] || peer=$pid; done
    [ -z "$peer" ] && [ "$i" -lt 30 ] || break
    i=$((i + 1)); sleep 1
  done
  printf '%s\n' "spawn_worker: '$name' started with $brief in a Windows Terminal tab; watch it there"
  watch_line
  sid=""; [ -z "$peer" ] || sid=$($kit_python -I -c 'import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("sessionId", ""))' "$reg/$peer.json" 2>/dev/null) || sid=""
  ctl "session id" "$sid"
  printf '%s\n' "spawn_worker: to answer it in its own session once its tab has ended: scripts/spawn_worker.sh $name ANSWER_FILE $again --resume ${sid:-SESSION_ID}"
  if [ -n "$peer" ]; then
    printf '%s\n' "spawn_worker: '$name' is a peer session (process $peer): ListAgents lists it; you may also subscribe with SendMessage notify_when_idle, but a supervised close often sends no notice: never rely on it alone"
  else
    printf '%s\n' "spawn_worker: WARNING: '$name' (process $pids) is not registered as a peer session (unusual: a spawned worker normally registers): ListAgents does not list it, SendMessage cannot reach it, and no notice comes when it stops on a question, a usage limit or an error. The watcher above reports its waits and its end"
  fi
  printf '%s\n' "spawn_worker: once you decide the session is finished, close it: scripts/close_worker.sh $name"
  exit 0
fi

# `cd` first: tmux hands new sessions the PWD of whichever client last created one, and
# the tool exits with "the current working directory was deleted" when that folder (a
# removed worktree, say) is gone, whatever -c says.
[ -z "$worktree" ] || prepare_settings
prepare_worktree
supervisor
reset_state
[ -z "$backend" ] || cmd=$(backend_command "$cmd")
# The reserved script removes itself; tmux receives two plain words for its default shell.
record_result
printf '%s\n' 'rm -f -- "$0"' "cd $(q "$dir") && exec $unmark $supervise sh -c $(q "exec $cmd")" > "$run" || { rm -f -- "$run"; die "cannot write the session's script: $run"; }
# Keep ownership pending until tmux confirms the session, including in signal cleanup.
launch_pending=1
# Marked before the session can start, and never cleared: a session that ran and ended before the
# check below may have written into the worktree, which then stays (stranded above).
launched=1
tmux new-session -d -s "$name" -c "$dir" -x 200 -y 50 "sh $run" || { launch_pending=""; die "tmux could not start '$name'"; }
tmux has-session -t "=$name" 2>/dev/null || { launch_pending=""; die "tmux could not start '$name'"; }
run=""; launch_pending=""; launched=1

# Wait for the input line: the TUI shows its prompt arrow at the start of a line once ready
# (v2.1.285 follows the arrow with a NO-BREAK space, so the match is on the arrow alone)
# or its mode hint in the status bar. A dialog (the trust dialog) or an exit is checked
# FIRST, by the watcher's own rules: the trust dialog's option line also starts with the arrow.
# Bounded: 60 seconds, then report. A watcher that is missing or fails (any exit but 0) stops
# the spawn with one line: without it nothing checks for a dialog before the brief is typed,
# and a missing file's shell error never matched `watch_workers:`. The session stays open.
i=0
while :; do
  rc=0; state=$(sh "$kit/watch_workers.sh" --once "$name" 2>&1) || rc=$?
  case ${state%%"$nl"*} in
    *"WAITING: "*"folder-trust"*)
      printf '%s\n' "$state" >&2
      die "session '$name' is waiting in the trust dialog; open the folder once by hand (tmux attach -t $name)" ;;
    *"WAITING: "*)
      printf '%s\n' "$state" >&2
      die "session '$name' is waiting on a person before its brief was typed (tmux attach -t $name)" ;;
    *"GONE: "*) die "session '$name' exited before its input line showed" ;;
    *watch_workers:*) die "cannot check session '$name': $state" ;;
  esac
  [ "$rc" -eq 0 ] || die "cannot check session '$name': the watcher exited $rc: $state"
  pane=$(tmux capture-pane -p -t "$name" 2>/dev/null || true)
  case "$pane" in
    *"
❯"*|*"shift+tab to cycle"*|*"for shortcuts"*) break ;;
  esac
  i=$((i + 1))
  [ "$i" -lt 60 ] || die "session '$name' did not show its input line within 60 s (tmux attach -t $name)"
  sleep 1
done

# The instruction, typed as one line.
tmux send-keys -t "$name" -l "$instruction"

# Submit only once the line has landed: an Enter sent while the TUI is still receiving
# input is swallowed and the line sits unsent at the prompt (seen on the first run of this
# script). Fast input may show as the placeholder "[Pasted text", so both count. The END of
# the line is what must have landed, and the TUI wraps a long line at a blank: blanks and
# line ends are squeezed to one space before the match.
# Then confirm the prompt line emptied; if not, press Enter once more.
landed() { tmux capture-pane -p -t "$name" -J | tr -s ' \n' '  ' | grep -qF -e "does not depend on it." -e "[Pasted text"; }
i=0
until landed; do
  i=$((i + 1)); [ "$i" -lt 30 ] || die "the instruction did not appear in session '$name' (tmux attach -t $name)"
  sleep 1
done
sleep 1
tmux send-keys -t "$name" Enter
sleep 3
if tmux capture-pane -p -t "$name" -J | grep -qE '^❯.*(\[Pasted text|and follow it\.)'; then
  tmux send-keys -t "$name" Enter
fi
printf '%s\n' "spawn_worker: '$name' started with $brief (tmux attach -t $name to watch)"
watch_line
printf '%s\n' "spawn_worker: you may also subscribe with SendMessage notify_when_idle, but a supervised close often sends no notice: never rely on it alone"
# The session does not end when its task does: a pilot worker wrote its result file and sat
# idle for 40 minutes until killed by hand, and the idle notice also fires on every park on a
# background job. A published `Kind: completed` result file is the end signal: its supervisor
# ends the session on it (--result in the header); any other close is the lead's job.
printf '%s\n' "spawn_worker: once you decide the session is finished (no next task fits what it holds, or it is idle past the cache lifetime), close it: scripts/close_worker.sh $name"
printf '%s\n' "spawn_worker: to answer it in its own session once its tmux session has ended: scripts/spawn_worker.sh $name ANSWER_FILE $again --resume SESSION_ID (the sessionId of the ${CLAUDE_CONFIG_DIR:-~/.claude}/sessions/PID.json named $name)"
if [ -n "$batch" ]; then
  printf '%s\n' "spawn_worker: --batch: not shown. Once every worker of this batch is started, show them together in one window: scripts/show_workers.sh NAME1 NAME2 ..."
else
  sh "$kit/show_workers.sh" "$name" || printf '%s\n' "spawn_worker: '$name' was not shown and runs anyway; attach by hand: tmux attach -t $name"
fi
