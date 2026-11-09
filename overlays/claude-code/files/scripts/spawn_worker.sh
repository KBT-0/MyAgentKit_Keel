#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Usage: spawn_worker.sh NAME BRIEF_FILE --model M --effort LEVEL [--settings JSON_OR_FILE]
#                        [--allowed-tools LIST] [--worktree] [--batch] [--backend NAME]
#                        [--result FILE] [--resume SESSION_ID] [--owner-approved-fable REASON]
# Four facts to know before the details below:
# - --model and --effort are required, from docs/WORKFLOW.md, "Model routing"; nothing is inherited.
# - --worktree makes .claude/worktrees/NAME on branch worktree-NAME and locks it for the worker.
# - The result file (RESULT-NAME.md, or --result FILE) is the done signal: only Kind: completed is done.
# - --resume SESSION_ID continues the same worker; pass the launch's options again, as the printed
#   resume command does (it repeats --model, --effort, --worktree, --backend, --settings, --allowed-tools).
#
# Open a SEPARATE Claude Code worker session and hand it a brief file. By default it is a Claude
# Code background session (`claude --bg`) on every platform whose CLI lists --bg; the tab and
# tmux paths below are the fallback, and MYAGENTKIT_WORKER_HOST=bg|tab|tmux forces one (see
# "The bg host" below: trust, resume without flags, never `claude daemon stop`).
# The fallback opens the session in tmux. On native
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
# --owner-approved-fable REASON: a Fable model (fable, claude-fable-*) is refused without it (docs/WORKFLOW.md
# "Worker cost" rule 2, owner 2026-11-03: Fable leads, reviews and consults, never works); REASON is the owner's
# words for this task, printed in the spend line and kept in .myagentkit/workers/NAME.fable-approved.
#
# Four refusals come before anything is made (docs/WORKFLOW.md, "Worker cost — the rules in brief"),
# each with its variable: a brief over 12000 bytes, its size printed on every launch
# (MYAGENTKIT_BRIEF_MAX=N sets the cap); a --resume of a worker whose last context is over 150,000
# tokens, which a fresh worker from the RESULT replaces (MYAGENTKIT_RESUME_FORCE=REASON passes it);
# an account at 95% of its five-hour or 98% of its seven-day limit, where another account spawns and
# nobody waits for the reset (MYAGENTKIT_LIMIT_FORCE=1 passes it); a project where 3 Claude Code
# sessions run already (MYAGENTKIT_MAX_SESSIONS=N raises it, MYAGENTKIT_LIMIT_FORCE=1 passes it).
#
# CLAUDE_CONFIG_DIR=DIR spawn_worker.sh ... runs the worker on another account's login folder, the
# owner's call per spawn and off otherwise (docs/WORKFLOW.md, "Worker cost" rule 10). DIR stays in
# .myagentkit/workers/NAME.config for close_worker.sh, watch_workers.sh and a later --resume; close,
# watch, list, show and the name check read that folder, or with no record the default one, whatever
# the caller's own CLAUDE_CONFIG_DIR says (the rule: list_workers.sh).
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
# completed or Kind: handoff, or a decision published to QUESTION-NAME.md there, ends the session 60 s later,
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
# overrides it; Claude Code 2.1.302's settings schema). CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=5m
# on the launch line below covers the worker's own sub-agents, workflows, forks and compaction
# (the "everything else" bucket, code.claude.com/docs/en/prompt-caching): short errands, since
# one that waits runs as a session of its own (guard_worker_route.py). It was 1h until #307
# measured that premium unused; 5m also beats a 1h a spawner or the bg daemon carries.
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
# background command, on every platform: its exit is the done signal (the result file, GONE,
# WAITING or LIMIT), and the lead starts it again after every report but DONE and GONE. It is the
# ONE done signal: the worker sends the lead no message (owner, 2026-11-09: each
# result woke the lead twice, once by the message and once by the watch). The lead may also
# subscribe with SendMessage `notify_when_idle` (a peer session; a tmux worker registers), but
# never relies on it alone: the supervisor's close of a finished worker often sends no idle
# notice (4 of 5 closes on 2026-10-20). The watch reads the result FILE the brief asks the worker to
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
#   - --worktree makes the worktree in the main checkout's .claude/worktrees, with `git worktree
#     add` from the commit the lead's checkout is on now. Passing `-w` to the tool built it from a stale base, and workers
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

[ $# -ge 2 ] || { sed -n '3,12p' "$0"; exit 2; }
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
brief_src=$brief  # the file just checked, which a copy into the worker's folder reads (below)
# leeway lead 43: an Owns: line in prose let the worker start, and review.sh refused its diff mid-task
if [ -f scripts/owns_check.py ]; then
  owns_py=python3; command -v python3 >/dev/null 2>&1 || owns_py=python
  owns_out=$($owns_py -I scripts/owns_check.py "$brief" --brief 2>&1) ||
    die "the brief's Owns: line cannot be read: $owns_out"
fi
# leeway lead 43 items 5-6: a bench holds the machine's quiet window; a new worker would load it
if [ -f scripts/calm.sh ] && held=$(sh scripts/calm.sh status); then
  die "the machine's quiet window is $held. Wait (sh scripts/calm.sh window) or ask its holder to release it"
fi
case "$brief" in */*) brief_dir=${brief%/*}/ ;; *) brief_dir=. ;; esac
# Every path handed on is physical (`pwd -P`): a plain `pwd` printed the logical path when the
# caller exported a matching PWD and the physical one otherwise, so the same brief was named
# /var/... by one caller and /private/var/... by another on macOS.
brief_dir=$(CDPATH= cd -P -- "$brief_dir" && pwd -P && echo x) || die "cannot resolve the brief's folder: $brief"
brief=${brief_dir%"${nl}x"}/${brief##*/}
ctl "brief path" "$brief"
command -v claude >/dev/null || die "claude is not on PATH"

model=""; settings=""; tools=""; worktree=""; effort=""; batch=""; backend=""; resume=""; result=""; fable=""
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
    --owner-approved-fable) fable=${2-}; [ -n "$fable" ] || die "--owner-approved-fable needs the owner's words for this task"; shift 2 ;;
    --resume)        case ${2-} in ""|-*) die "--resume needs the session id of the worker's conversation: --resume SESSION_ID" ;; esac
                     resume=$2; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
# The lead picks both for every worker (docs/WORKFLOW.md, "Model routing"); left out, the
# session silently took the user's default.
[ -n "$model" ] || die "--model is required: the lead picks the model for every worker"
[ -n "$effort" ] || die "--effort is required: the lead picks the effort for every worker"
# A backend's model is its own id or alias, never Anthropic's Fable.
if [ -z "$backend" ] && [ -z "$fable" ]; then
  case $(printf '%s' "$model" | tr 'A-Z' 'a-z') in
    fable|fable[!a-z0-9_]*|claude-fable|claude-fable[!a-z0-9_]*)
      die "refused a Fable ($model) worker: Fable leads, reviews and consults; it never does the work (docs/WORKFLOW.md \"Worker cost\" rule 2, owner 2026-11-03). Pick the routine model from \"Model routing\"; for a worker the owner approved for this task, add --owner-approved-fable REASON with the owner's words" ;;
  esac
fi
ctl "session id" "$resume"
ctl "result path" "$result"
# The host, which MYAGENTKIT_WORKER_HOST=bg|tab|tmux forces: a Claude Code background session
# where the CLI has --bg (`claude --help` lists it; `claude --bg --help` STARTS an idle session, so
# it is never the probe), else the fallback: a Windows Terminal tab on native Windows, tmux
# elsewhere. --backend keeps the fallback: whether a background session takes the launch's
# environment, which carries the endpoint, is untried (docs/research/worker-orchestration-spike.md).
# The probe is bounded at 10 s, as doctor.sh's (its measurements): its output goes to a file, never
# a pipe, since a child that holds a pipe open hung every spawn; past the bound it is killed.
lists_bg() {
  help=$(mktemp) || return 1
  claude --help </dev/null >"$help" 2>/dev/null &
  p=$! i=0
  while kill -0 "$p" 2>/dev/null; do
    [ "$i" -lt 100 ] || { kill "$p" 2>/dev/null || :; break; }
    i=$((i + 1)); sleep 0.1
  done
  rc=0; grep -qE -e '--bg([, ]|$)' "$help" || rc=1
  rm -f -- "$help"
  return "$rc"
}
host=${MYAGENTKIT_WORKER_HOST:-}
case $host in
  "") if [ -z "$backend" ] && lists_bg; then host=bg
      elif [ -n "$windows" ]; then host=tab; else host=tmux; fi ;;
  bg) [ -z "$backend" ] || die "--backend runs on the tab or tmux host, not with MYAGENTKIT_WORKER_HOST=bg" ;;
  tab) [ -n "$windows" ] || die "MYAGENTKIT_WORKER_HOST=tab is the native Windows host; use bg or tmux here" ;;
  tmux) [ -z "$windows" ] || die "MYAGENTKIT_WORKER_HOST=tmux: native Windows has no tmux; use bg or tab" ;;
  *) die "MYAGENTKIT_WORKER_HOST must be bg, tab or tmux" ;;
esac
bg=""; [ "$host" != bg ] || bg=1
[ "$host" != tmux ] || command -v tmux >/dev/null || die "tmux is not installed"

# A name in use is refused on every host: a tmux worker (one from before the bg host, or forced)
# has no NAME.id, and a bg spawn of its name replaced its records. Native Windows checks below.
[ -n "$windows" ] || ! command -v tmux >/dev/null || ! tmux has-session -t "=$name" 2>/dev/null ||
  die "tmux session '$name' already exists"

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
if [ "$host" = tmux ]; then
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
# The lean start (v0.16): no plugin, skill, auto-memory or CLAUDE.md tree; AGENTS.worker.md, the
# hard rules, rides with the appendix instead (docs/WORKFLOW.md, "Worker cost"). `--bare` is no
# way there: it skips the settings' hooks (the kit's guards) and OAuth. MYAGENTKIT_WORKER_FULL=1
# keeps the full start (the A/B's other side).
lean=""; worker_rules=""
if [ "${MYAGENTKIT_WORKER_FULL:-}" != 1 ]; then
  lean=1
  for f in "$dir/AGENTS.worker.md" "$dir/core/AGENTS.worker.md"; do
    if [ -f "$f" ]; then worker_rules=$f; break; fi
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
[ -z "$fable" ]    || again="$again --owner-approved-fable $(q "$fable")"
# Validate the lead checkout's generated paths before creating a worktree or worker files.
wdir=$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)/.myagentkit/workers
project_settings=$dir/.claude/settings.json
# The login folder (the header): a resume with no CLAUDE_CONFIG_DIR of its own goes on in the one its
# NAME.config names. Exported, so the checks below and the launch read it. Made absolute against the
# caller's folder: the session starts in the worker's, and close and watch run from anywhere.
if [ -z "${CLAUDE_CONFIG_DIR:-}" ] && [ -n "$resume" ] && [ -s "$wdir/$name.config" ]; then
  CLAUDE_CONFIG_DIR=$(cat -- "$wdir/$name.config") || die "cannot read the login folder in $wdir/$name.config"
fi
config_cmd=""
if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
  case $CLAUDE_CONFIG_DIR in /*|[a-zA-Z]:*|\\*) ;; *) CLAUDE_CONFIG_DIR=$dir/$CLAUDE_CONFIG_DIR ;; esac
  export CLAUDE_CONFIG_DIR
  config_cmd="CLAUDE_CONFIG_DIR=$(q "$CLAUDE_CONFIG_DIR") "
fi
if [ -n "$windows" ]; then
  longest_path=$(cygpath -m "$wdir/$longest") || die "cygpath cannot convert the path: $wdir"
  [ "${#longest_path}" -le 259 ] ||
    die "refused the worker path: generated paths must fit in 259 characters on native Windows (MAX_PATH 260); use a shorter name or a shorter checkout path, or enable LongPathsEnabled for long-path tooling"
fi
# kit_script FILE: a kit script that a check below imports, the project's copy first, then the
# kit's own checkout (core/scripts, four folders above this overlay script). None: it prints nothing.
kit_script() {
  for f in "$dir/scripts/$1" "$dir/core/scripts/$1" "$kit/$1" "$kit/../../../../core/scripts/$1"; do
    [ -f "$f" ] && { native "$(CDPATH='' cd -P -- "${f%/*}" && pwd -P)"; return 0; }
  done
  return 1
}
# native PATH: the path as the Windows tools spell it on native Windows (cygpath -m), else as is.
native() { if [ -n "$windows" ]; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
# The brief fits one session (owner, 2026-11-09): a brief that does not ends in
# hand-offs. 12000 = 1.5 x 7,677 bytes, the largest brief that ran to Kind: completed (tokfield,
# 2026-11-04) of the v0.16-reset and worker briefs measured with `wc -c` on 2026-11-09, rounded.
brief_max=${MYAGENTKIT_BRIEF_MAX:-12000}
case $brief_max in ''|*[!0-9]*) die "MYAGENTKIT_BRIEF_MAX must be a whole number of bytes" ;; esac
brief_size=$(wc -c < "$brief_src" | tr -d ' ') || die "cannot measure the brief: $brief_src"
printf '%s\n' "spawn_worker: brief: $brief_size bytes (cap $brief_max)"
[ "$brief_size" -le "$brief_max" ] ||
  die "refused the brief: $brief_size bytes, over the cap of $brief_max (MYAGENTKIT_BRIEF_MAX): a brief that does not fit one session ends in hand-offs; split it into briefs of one session each (docs/HANDOFF.md, \"The brief\")"
# A resume rewrites the worker's whole context as a cache write (up to 371k per resume, pipeline
# report 2026-11-09): above 150,000 tokens it is refused for a fresh worker that starts from the
# RESULT (owner, 2026-11-09). The last known context is NAME.state's context_tokens=N (the
# state hook), else the last request of the session's transcript, read by agent_cost.py.
# MYAGENTKIT_RESUME_FORCE=REASON passes; an unknown context passes, said.
if [ -n "$resume" ]; then
  told_result=${result:-RESULT-$name.md}
  [ ! -r "$wdir/$name.result-path" ] || told_result=$(cat -- "$wdir/$name.result-path") || told_result=${result:-RESULT-$name.md}
  cost_dir=$(kit_script agent_cost.py) || cost_dir=""
  ctx=$($kit_python -I -c 'import glob, os, re, sys
from pathlib import Path
state, sid, config = sys.argv[1:4]
try:
    with open(state, encoding="utf-8", errors="replace") as f:
        found = re.findall(r"context_tokens=(\d+)", f.read())
except OSError:
    found = []
if found:
    print(found[-1], "the state line")
    sys.exit(0)
pattern = glob.escape(sid) + (".jsonl" if "-" in sid else "-*.jsonl")
files = sorted(glob.glob(os.path.join(glob.escape(config), "projects", "*", pattern)), key=os.path.getmtime)
if files and len(sys.argv) > 4:
    sys.path.insert(0, sys.argv[4])
    from agent_cost import requests
    rows = requests(Path(files[-1]))
    if rows:
        print(rows[-1]["inp"] + rows[-1]["cr"] + rows[-1]["cw"], "the transcript")' \
    "$(native "$wdir/$name.state")" "$resume" "$(native "${CLAUDE_CONFIG_DIR:-$HOME/.claude}")" \
    ${cost_dir:+"$cost_dir"} 2>/dev/null) || ctx=""
  case ${ctx%% *} in
    ''|*[!0-9]*) printf '%s\n' "spawn_worker: resume: context unknown (no context_tokens in $name.state, no transcript of $resume): it passes" ;;
    *) if [ "${ctx%% *}" -le 150000 ]; then
         printf '%s\n' "spawn_worker: resume: context ${ctx%% *} tokens (${ctx#* }), within 150000"
       elif [ -n "${MYAGENTKIT_RESUME_FORCE:-}" ]; then
         printf '%s\n' "spawn_worker: resume: context ${ctx%% *} tokens (${ctx#* }), over 150000, forced: $MYAGENTKIT_RESUME_FORCE" | LC_ALL=C tr '\001-\011\013-\037\177' '?'
       else
         die "refused the resume: context ${ctx%% *} tokens (${ctx#* }), over 150000, and a resume rewrites all of it; start a fresh worker from the RESULT ($told_result), or set MYAGENTKIT_RESUME_FORCE=REASON"
       fi ;;
  esac
fi
# A limit is per account, and nobody waits for a reset (owner, 2026-11-09: a lead
# waited ~3.5 h on one account's five-hour limit while four others were free). The account's
# rate-limits.json, as quota_snapshot.py reads it: five_hour at 95% or over, or seven_day at 98% or
# over, refuses the spawn. No file or no key (it exists only while a window runs): it passes,
# silent. MYAGENTKIT_LIMIT_FORCE=1 passes.
if [ "${MYAGENTKIT_LIMIT_FORCE:-}" != 1 ] && quota_dir=$(kit_script quota_snapshot.py); then
  limit=$($kit_python -I -c 'import sys, time
sys.path.insert(0, sys.argv[1])
from quota_snapshot import snapshot
s = snapshot("spawn", "check")
for key, cap, window in (("five_hour", 95, "five-hour"), ("seven_day", 98, "seven-day")):
    w = s.get(key)
    used = w.get("used_percentage") if isinstance(w, dict) else None
    if type(used) not in (int, float) or used < cap:
        continue
    reset = w.get("resets_at")
    when = time.strftime("%Y-%m-%d %H:%M %Z", time.localtime(reset)) if type(reset) in (int, float) else "unknown"
    print("%s: %s window at %g%% (refused at %d%%), resets %s" % (s.get("org_name") or "this account", window, used, cap, when))
    break' "$quota_dir" 2>/dev/null) || limit=""
  [ -z "$limit" ] || die "refused the spawn: the account $limit; another account may spawn now; no waiting (MYAGENTKIT_LIMIT_FORCE=1 passes)"
fi
# The cap on sessions running at once (owner, 2026-11-09: count per project; docs/WORKFLOW.md, "Worker
# cost" rule 10). This project's sessions count, the lead's too: a registry file whose cwd is the main
# checkout (`git worktree list`, first line; out of a repository this folder) or under its
# .claude/worktrees; another project's or a missing cwd does not. Only the spawning login folder's
# registry is read. Live: the pid of a registry file exists; a stale file is skipped, not deleted. A resume does not count the session
# it continues, which it replaces (it may still be in its closing grace). No registry or an
# unreadable file: it passes, silent. On native Windows os.kill(pid, 0) is no probe but a Ctrl-C
# to that process group (CTRL_C_EVENT is 0), so there the process is opened instead; unmeasured.
if [ "${MYAGENTKIT_LIMIT_FORCE:-}" != 1 ]; then
  max_sessions=${MYAGENTKIT_MAX_SESSIONS:-3}
  case $max_sessions in *[!0-9]*) max_sessions=0 ;; esac
  [ "$max_sessions" -ge 1 ] 2>/dev/null || {
    printf '%s\n' "spawn_worker: MYAGENTKIT_MAX_SESSIONS is no whole number of 1 or more: the default 3 applies" >&2
    max_sessions=3
  }
  project=$(git worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')
  [ -n "$project" ] || project=${wdir%/.myagentkit/workers}
  live_sessions=$($kit_python -I -c 'import glob, json, os, sys
def alive(pid):
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED: it exists
        code = ctypes.c_ulong()
        known = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(known) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, OverflowError):
        return False
    return True
folder, resume, cap = sys.argv[1], sys.argv[2], int(sys.argv[3])
key = lambda path: os.path.normcase(os.path.realpath(path))
main = key(sys.argv[4])
trees = os.path.join(main, ".claude", "worktrees", "")
live = []
for path in sorted(glob.glob(os.path.join(glob.escape(folder), "*.json"))):
    try:
        with open(path, encoding="utf-8") as f:
            row = json.load(f)
        pid = row["pid"]
    except (OSError, ValueError, KeyError, TypeError):
        continue
    cwd = row.get("cwd")
    if not cwd or not isinstance(cwd, str) or (key(cwd) != main and not key(cwd).startswith(trees)):
        continue
    if type(pid) is not int or pid < 1 or not alive(pid):
        continue
    session = str(row.get("sessionId") or "")
    if resume and (session == resume or session.startswith(resume + "-")):
        continue
    live.append("%s (%s)" % (row.get("name") or "process %d" % pid, cwd))
if len(live) >= cap:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(len(live), ", ".join(live))' "$(native "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/sessions")" "$resume" "$max_sessions" "$(native "$project")" 2>/dev/null) || live_sessions=""
  [ -z "$live_sessions" ] || die "refused the spawn: ${live_sessions%% *} Claude Code sessions run in this project (cap $max_sessions, MYAGENTKIT_MAX_SESSIONS): ${live_sessions#* }; every running session rewrites its context at an account switch; close one (scripts/close_worker.sh NAME) or wait for it; the cap: docs/WORKFLOW.md rule 10 (MYAGENTKIT_MAX_SESSIONS=N raises it, MYAGENTKIT_LIMIT_FORCE=1 passes)"
fi
# The spend line, as review.sh prints its own before a review: the owner sees what each worker
# costs before it runs (issue #68; docs/WORKFLOW.md, "Model routing").
printf '%s\n' "spawn_worker: about to run '$name': model $model, effort $effort${fable:+, owner-approved Fable: $fable}" | LC_ALL=C tr '\001-\011\013-\037\177' '?'
# The subscription's percent before the worker runs; close_worker.sh writes the end, and
# agent_cost.py --quota compares them. It never fails the spawn.
for f in "$dir/scripts/quota_snapshot.py" "$dir/core/scripts/quota_snapshot.py"; do
  [ -f "$f" ] && { $kit_python -I "$f" "$name" start --dir "${wdir%/workers}/usage" </dev/null || true; break; }
done
if [ -n "$worktree" ]; then
  top=$(git rev-parse --show-toplevel) || die "--worktree needs a git repository"
  project_settings=$top/.claude/settings.json
  # In the MAIN checkout's .claude/worktrees, whichever checkout the lead works in: the audit
  # (close_worker.sh, the post-merge hook) removes from that folder alone, and a worktree nested in
  # a lead's linked worktree was left there by its close (bgwait). A resume takes the folder git
  # lists for its branch: an older spawn may have nested it.
  main=$(git worktree list --porcelain | sed -n '1s/^worktree //p') && [ -n "$main" ] ||
    die "--worktree: git worktree list names no main checkout"
  dir=$main/.claude/worktrees/$name
  if [ -n "$resume" ]; then
    listed=$(git worktree list --porcelain | awk -v b="branch refs/heads/worktree-$name" '/^worktree /{p=substr($0,10)} $0==b{print p; exit}')
    [ -z "$listed" ] || dir=$listed
    [ -d "$dir" ] || die "--resume --worktree: no worktree at $dir"
  else
    ! git show-ref --verify --quiet "refs/heads/worktree-$name" ||
      die "branch worktree-$name already exists and may be stale; delete it or pick another name"
    [ ! -e "$dir" ] || die "worktree path already exists: $dir"
  fi
elif [ -n "$resume" ]; then
  # A resume without --worktree of a worker whose worktree git still lists ran in this folder: its
  # result, records and session landed in the lead's checkout, where close_worker.sh then refused to
  # stop it (resumefix, 2026-11-03: the lead typed the resume line without --worktree).
  listed=$(git worktree list --porcelain 2>/dev/null | awk -v b="branch refs/heads/worktree-$name" '/^worktree /{p=substr($0,10)} $0==b{print p; exit}')
  [ -z "$listed" ] || [ ! -d "$listed" ] || [ "$(CDPATH= cd -P -- "$listed" && pwd -P)" = "$dir" ] ||
    die "--resume without --worktree: '$name' has its worktree at $listed; resume it there with the launch's options again, as its printed resume line has them (--worktree, --settings, ...)"
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
# #324: a resume into a linked worktree where files changed after the worker's last result says so
# (leeway: a lead cd'd into it from the main checkout, which no session list shows). A NOTE, never a
# refusal: the worker's own work after a progress result, or the lead in its own tree, look the same
# (review 0c64f4627e84). shortcut: file times only (not git-ignored files).
if [ -n "$resume" ] && [ -f "$result" ]; then
  newer=$($kit_python -I -c 'import os, subprocess, sys
result, brief = (os.path.realpath(p) for p in sys.argv[1:3])
git = lambda *a: subprocess.run(["git", "-C", os.path.dirname(result), *a], capture_output=True).stdout
top, here, common = (git("rev-parse", o).decode().strip() for o in ("--show-toplevel", "--absolute-git-dir", "--git-common-dir"))
if not top or os.path.realpath(os.path.join(os.path.dirname(result), common)) == os.path.realpath(here):
    sys.exit(0)  # the main checkout: the lead works there by design
since = os.stat(result).st_mtime
skip = {result, brief, os.path.realpath(sys.argv[3])}
for rel in git("ls-files", "-z", "-c", "-o", "--exclude-standard", "--full-name", ":/").split(b"\0"):
    path = os.path.realpath(os.path.join(top, os.fsdecode(rel))) if rel else ""
    if path and path not in skip and os.path.isfile(path) and os.stat(path).st_mtime > since:
        print(os.fsdecode(rel))' "$result" "$brief" "$cquestion" 2>/dev/null | head -n 5) || newer=""
  [ -z "$newer" ] || printf '%s\n' "spawn_worker: NOTE: files in the worker's worktree changed after its result $result: $(printf '%s' "$newer" | tr '\n' ' ' | sed 's/ $//'). If another session works there, stop it first: two writers in one tree collide (#324)."
fi
if [ -n "$windows" ]; then
  { cworker=$(cygpath -m "$cworker") && cresult=$(cygpath -m "$result") && cquestion=$(cygpath -m "$cquestion"); } ||
    die "cygpath cannot convert the result's path: $result"
fi
# The run starts once its worktree exists (#168): a committed result that the checkout wrote is
# older than the start, so the supervisor takes it for an earlier run's and never as this run's DONE.
# The supervisor ends a finished worker 60 s after its result, not codex_worker.py's 10: a bound
# set for the worker's message to the lead (delivered 21 and 27 s after the publish on a loaded
# host, donemsg spikes 2026-10-22), which v0.16 removed; kept, since an idle session costs nothing.
supervisor() {
  start=$($kit_python -I -c 'import time; print(time.time())')
  supervise="KIT_WORKER_GRACE=$(q "${KIT_WORKER_GRACE:-60}") KIT_WORKER_STARTED=$(q "$start")${resume:+ KIT_WORKER_RESUME=1} $kit_python $(q "$cworker") $(q "$cquestion") $(q "$cresult") --"
}
# Written once the name is known to be free: a running worker's record is never replaced.
# NAME.host names the host it runs on (bg, tab or tmux) for close_worker.sh and the watcher;
# NAME.config the login folder it runs on, only when one is set (the header): a fresh spawn here, a
# resume once its launch succeeded (record_config), so a failed resume leaves the record as it was.
# No NAME.config MEANS the default folder ~/.claude, never a caller's (the rule: list_workers.sh).
record_config() {
  if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then printf '%s\n' "$CLAUDE_CONFIG_DIR" > "$wdir/$name.config" || die "cannot record the login folder in $wdir"
  else rm -f -- "$wdir/$name.config"; fi
}
record_result() {
  # A resume's earlier result belongs to the closed run: moved into the lead's records as
  # NAME.result-prev.md, so neither the watch nor the worker takes it for this run's (leeway
  # 2026-11-02: the worker's merge renewed its mtime and the watch said DONE at once), and no copy
  # stays in the worker's tree to keep it at close (review r-leewayfield). Only the last one is kept:
  # the lead has read it. A committed result stays: the watch's earlier() check sets it aside.
  if [ -n "$resume" ] && [ -f "$result" ] &&
     ! git -C "${result%/*}" ls-files --error-unmatch -- "${result##*/}" >/dev/null 2>&1; then
    mkdir -p -- "$wdir" && mv -f -- "$result" "$wdir/$name.result-prev.md" ||
      die "cannot move the earlier result aside: $result"
  fi
  mkdir -p -- "$wdir" && printf '%s\n' "$cresult" > "$wdir/$name.result-path" &&
    printf '%s\n' "$host" > "$wdir/$name.host" || die "cannot record the result path and host in $wdir"
  [ -n "$resume" ] || record_config
  if [ -n "$fable" ]; then printf '%s\n' "$fable" > "$wdir/$name.fable-approved" || die "cannot record the Fable approval in $wdir"
  else rm -f -- "$wdir/$name.fable-approved"; fi
}

# Worktree sessions read shared project settings from their own working directory
# (https://code.claude.com/docs/en/settings, checked 2026-10-16). Tracked settings arrive
# with the checkout; absent settings must travel in --settings, with the owner's overrides
# and hooks kept. Hook commands retain $CLAUDE_PROJECT_DIR and run in the worker.
# Both worktree sessions and Windows tabs get state telemetry (owner decision 23, 2026-10-16).
own=$settings
if [ -n "$windows$worktree$bg$lean" ]; then
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
    if sys.argv[3]:
        # The bg host: no isolation of its own (no worktree, push or draft PR), and the worker
        # settings in the session itself, whatever environment Claude Code gives the session.
        d.setdefault("worktree", {})["bgIsolation"] = "none"
        # No variable of the launch reaches the session (it runs in a process the daemon
        # started; POSIX spike), and no AI attribution in its commits (a rule of the owner).
        d.setdefault("env", {}).update(MYAGENTKIT_ROLE="worker", CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL="5m",
                                       MYAGENTKIT_SESSION_ID="worker-" + sys.argv[4])
        d["attribution"] = {"commit": "", "pr": ""}
    if sys.argv[5]:
        # The lean start: every plugin a settings file enables or the CLI installed is off (a
        # flag setting outranks the user, project and local ones), no auto-memory, and no
        # CLAUDE.md of the folder or above it, nor the user one; one in a subtree stays.
        import os, pathlib
        config = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"))
        top = pathlib.Path(sys.argv[6])
        names = set(d.get("enabledPlugins") or {})
        for f in (config / "settings.json", top / ".claude/settings.json", top / ".claude/settings.local.json",
                  config / "plugins/installed_plugins.json"):
            try:
                found = json.load(open(f, encoding="utf-8-sig"))
                names.update(found.get("enabledPlugins") or found.get("plugins") or {})
            except (OSError, ValueError, AttributeError, TypeError):
                pass  # an absent or unreadable file enables nothing to turn off
        d["enabledPlugins"] = dict.fromkeys(sorted(names), False)
        d["autoMemoryEnabled"] = False
        # shortcut: exact paths, matched as Claude Code spells them; on native Windows unmeasured.
        d["claudeMdExcludes"] = [(a / n).as_posix() for a in (top, *top.parents)
                                 for n in ("CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md")] + [
                                 (config / "CLAUDE.md").as_posix()]
    print(json.dumps(d, indent=2))' "$hook" "$project" "$bg" "$name" "$lean" "$(native "$dir")" >"$wdir/$name.settings.json" ||
    die "cannot merge the project and worker hooks into --settings (not a JSON object?): $own"
}
reset_state() {
  # All launches, including plain tmux sessions, begin without the previous run's snapshot.
  rm -f -- "$wdir/$name".state* "$wdir/$name".watch-* "$wdir/$name.pid" "$wdir/$name.exit" "$wdir/$name.live" \
    "$wdir/$name.host" "$wdir/$name.supervisor.log" ||
    die "cannot clear the previous state in $wdir"
  # A resume keeps the session's ids until its launch prints the id: a failed one (a trust
  # refusal, no id, a copy) leaves the session it names on record for close and watch.
  [ -n "$resume" ] || rm -f -- "$wdir/$name.id" "$wdir/$name.session" ||
    die "cannot clear the previous state in $wdir"
}
# A worker is a session of its own, never the lead's child. The lead's shell carries Claude
# Code's child-session markers, and a claude that sees CLAUDE_CODE_CHILD_SESSION skips its peer
# registration (no sessions/<pid>.json: ListAgents never lists the worker, SendMessage cannot
# reach it). tmux ignores the marker, a Windows Terminal tab does not, so both paths clear them.
# CLAUDE_CLI_BIN and CLAUDE_CODE_EXECPATH name the binary and stay. MYAGENTKIT_SESSION_ID names the
# worker to the master-writer hooks, so a git command it runs is never taken for the owner's terminal
# (#311); the bg host carries it in the settings' env, as its other worker variables (below).
bare="env -u CLAUDE_CODE_CHILD_SESSION -u CLAUDECODE -u CLAUDE_CODE_SESSION_ID -u CLAUDE_PID -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN -u CLAUDE_CODE_SESSION_ATTENDED -u CLAUDE_CODE_ENTRYPOINT"
unmark="$bare CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=5m MYAGENTKIT_ROLE=worker MYAGENTKIT_SESSION_ID=worker-$name"
# The login folder on the session's own line: a new tmux session takes the server's environment and
# a tab Windows Terminal's, not this shell's. The bg launch inherits the export (its daemon is per folder).
[ -z "$config_cmd" ] || unmark="$unmark ${config_cmd% }"

# Variadic flags come LAST and the prompt is never on this line (see the header).
cmd="claude -n $(q "$name")${resume:+ --resume $(q "$resume")}"
[ -n "$model" ]    && cmd="$cmd --model $(q "$model")"
[ -n "$effort" ]   && cmd="$cmd --effort $(q "$effort")"
[ -n "$settings" ] && cmd="$cmd --settings $(q "$settings")"
# The lean start's one appendix: the hard rules, then the behaviour appendix (one file flag).
if [ -n "$worker_rules" ]; then
  mkdir -p -- "$wdir" && cat -- "$worker_rules" ${behaviour:+"$behaviour"} > "$wdir/$name.appendix.md" ||
    die "cannot write the worker's appendix in $wdir"
  behaviour=$wdir/$name.appendix.md
fi
[ -z "$lean" ] || cmd="$cmd --disable-slash-commands"
if [ -n "$behaviour" ]; then
  [ -z "$windows" ] || behaviour=$(cygpath -m "$behaviour") || die "cygpath cannot convert the behaviour appendix's path"
  cmd="$cmd --append-system-prompt-file $(q "$behaviour")"
fi
printf '%s' "spawn_worker: behaviour appendix: ${behaviour:-off}" | LC_ALL=C tr '\001-\037\177' '?'
printf '\n'
# Said, since a CLI whose help does not list --bg (or does not answer) falls back without a word.
printf '%s\n' "spawn_worker: host: $host"
launch="full (MYAGENTKIT_WORKER_FULL=1)"
[ -z "$lean" ] || launch="lean (no plugins, skills, auto-memory or root CLAUDE.md; MYAGENTKIT_WORKER_FULL=1 for the full start)"
printf '%s\n' "spawn_worker: start: $launch"
[ -n "$tools" ]    && cmd="$cmd --allowedTools $(q "$tools")"
# No question dialog in a pane nobody may watch: QUESTION-NAME.md is the question channel (the
# instruction says so; this enforces it). Permission prompts are not tools and
# stay. AskUserQuestion is the tool's name in Claude Code 2.1.300 (code.claude.com/docs/en/sub-agents).
# The rest are tools a worker never uses, off its start prefix: --disallowedTools removes them
# from the model's context (CLI reference). Measured on 2.1.310 (#307 rank 5): a bg worker's
# first request went from 46.5k to 27.4k tokens. SendMessage, ToolSearch, Monitor, Agent, Skill,
# ReportFindings and the task tools stay.
cmd="$cmd --disallowedTools AskUserQuestion Artifact ArtifactComments ArtifactData Workflow DesignSync RemoteTrigger"
cmd="$cmd CronCreate CronDelete CronList ScheduleWakeup EnterWorktree ExitWorktree EnterPlanMode ExitPlanMode"
cmd="$cmd PushNotification SendFeedback"
# One line naming the brief by its absolute path, quoted by the same helper so a path with a
# space or an apostrophe still reads as one path. The rest is the protocol codex_worker.py
# reads (#189): a result without its header and marker, or not renamed into place, is never
# seen, and only a published question ends the session for the lead; it keeps questions out of
# the pane, where nobody may be looking. On native Windows every path is Windows' own spelling:
# Git Bash's /tmp/... is a folder the worker's tools do not know.
[ -z "$windows" ] || brief=$(cygpath -m "$brief") || die "cygpath cannot convert the brief's path: $brief"
# The worker reads its brief inside its own folder: one outside it (a --worktree worker's always)
# stopped a host not in auto mode on a read-permission prompt before the worker's first step
# (bgwait), and the worker's reach stays that folder (owner: no --add-dir of the lead's checkout).
# Such a brief, or a resume's answer, is copied to .myagentkit/workers/NAME.brief.md there, the
# private store the kit's .gitignore keeps out of commits, and kept as NAME.brief.md in the lead's
# records: close_worker.sh removes the worker's copy before its audit while it is that record.
# Where the copy is not the record (a worktree), a .gitignore beside it that ignores itself and
# the copy keeps the worktree clean in a project that does not ignore the store; close removes it.
brief_ignore="# spawn_worker.sh: ignores the worker's copy of its brief; close_worker.sh removes both"
told=$brief; copy=""
case $brief in "$(native "$dir")"/*) ;; *)
  copy=$dir/.myagentkit/workers/$name.brief.md
  told=$(native "$copy") || die "cygpath cannot convert the path: $copy" ;;
esac
# same_file A B: test's -ef (both exist, one device and inode), which POSIX sh lacks (SC3013).
same_file() {
  $kit_python -I -c 'import os, sys
try:
    sys.exit(not os.path.samefile(sys.argv[1], sys.argv[2]))
except OSError:
    sys.exit(1)' "$(native "$1")" "$(native "$2")"
}
place_brief() {
  [ -n "$copy" ] || return 0
  { mkdir -p -- "$wdir" "${copy%/*}" &&
    { same_file "$brief_src" "$wdir/$name.brief.md" || cp -- "$brief_src" "$wdir/$name.brief.md"; } &&
    { same_file "$copy" "$wdir/$name.brief.md" || { cp -- "$wdir/$name.brief.md" "$copy" &&
      { [ -e "${copy%/*}/.gitignore" ] || printf '%s\n*\n' "$brief_ignore" > "${copy%/*}/.gitignore"; }; }; }; } ||
    die "cannot copy the brief into the worker's folder: $copy"
}
instruction="Read $(q "$told") and follow it. Your result file is $(q "$cresult"): its first four lines are Kind: completed (or Kind: blocked, Kind: handoff, Kind: progress), Task: THE TASK, Attempt: N and Remaining: WHAT IS LEFT, and its last line is <!-- codex-worker: ready -->; publish it whole, as a temporary file beside it renamed over it with $kit_python $(q "$cworker") --publish TEMPORARY_FILE DESTINATION: without them the supervisor never sees it. A published completed or handoff result ends this session 60 seconds later, once no commit or gate runs. Do not ask questions in this pane: for a decision, stop your jobs, publish a Kind: blocked result and then the question, the same way and with the same last line, to $(q "$cquestion"), which ends this session for the lead's answer; until then go on with what does not depend on it."
[ -z "$resume" ] || instruction="$instruction This resumes your session: that file is the lead's new instruction, a new task or an answer to go on with the current one. Your earlier result is closed even if it said the work was done (an uncommitted one was moved out of your folder): publish a new result once the work is done."

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
# The watch reads the records in the checkout that holds them (this one): run from another, it
# saw none and said nothing, forever (2026-10-21). So the line cds there and names the script by
# its absolute path: it works pasted in any folder. The until-loop needs no records for the
# result; it also ends on a worker its usage limit stopped (watch_workers.sh --limit, run in that
# checkout), which writes no result and sat ~1 h unseen (2026-10-22). It gives up after 24 h
# (2880 polls): two loops on results written elsewhere waited two days (leeway, 2026-10-26).
watch_line() {
  ctop=${wdir%/.myagentkit/workers}
  [ -z "$windows" ] || ctop=$(cygpath -m "$ctop") || ctop=${wdir%/.myagentkit/workers}
  wsh=$(q "${cworker%/*}/watch_workers.sh") rq=$(q "$cresult") rp=$(q "$ctop/.myagentkit/workers/$name.result-path")
  printf '%s\n' "spawn_worker: watch it now, as ONE background command whose exit is the only done signal (the worker sends no message; start it again after every report but DONE and GONE): cd $(q "$ctop") && sh $wsh --result $name=$rq $name"
  printf '%s\n' "spawn_worker: the plainest done signal, from any folder (any Kind; only Kind: completed is done; a LIMIT line instead: its usage limit stopped it): n=0; until [ $rq -nt $rp ] && grep -qF '<!-- codex-worker: ready -->' $rq || (CDPATH= cd $(q "$ctop") && sh $wsh --limit $name) || [ \$((n+=1)) -gt 2880 ]; do sleep 30; done; [ \$n -le 2880 ] || printf '%s\\n' 'spawn_worker: GAVE UP: no result from $name in 24 h; if it still runs (scripts/watch_workers.sh $name), start this watch again'; [ ! $rq -nt $rp ] || head -n 4 $rq"
}
# The bg host: a Claude Code background session, on every platform. It starts in the worker's
# folder, which must sit under a repo root the owner trusted in Claude Code (a trusted root
# covers its worktrees; trust is not inherited from a parent folder), with the prompt first and
# the merged --settings carrying worktree.bgIsolation "none". Everything is keyed on the id it
# prints, kept in NAME.id: names repeat. A resume is `claude PROMPT --resume ID --bg` and no flag:
# a flag starts a copy under the same name, and the session keeps its saved options, so a model
# or effort change is a new spawn. codex_worker.py --detach supervises it and ends it with
# `claude stop ID`; nothing calls `claude daemon stop`, which ends every background session on
# the host (docs/research/worker-orchestration-spike.md, T1-T3, 6, T4).
# bg_row ID prints "blocked" (a usage limit or a wait for a person stops a session so), "live" (a
# process), "starting" (working with no pid: a starting session lists none, spike check 4) or "-",
# then the sessionId of that row, or nothing. All but "-" run, as codex_worker.py counts them.
bg_row() {
  claude agents --json --all </dev/null 2>/dev/null | $kit_python -I -c 'import json, sys
for row in json.loads(sys.stdin.buffer.read()):
    if row.get("id") == sys.argv[1]:
        state = row.get("state")
        live = "blocked" if state == "blocked" else "live" if row.get("pid") else "starting" if state == "working" else "-"
        print(live, row.get("sessionId") or "-")' "$1"
}
# A published result or question ends its session KIT_WORKER_GRACE (60) s later, and a lead that
# answers at once, on the watch's report, resumes inside that grace (donemsgfix): a resume waits for
# that end instead of refusing it. Waiting, not stopping it as close_worker.sh does: the grace exists
# so any commit finishes. Only a file published in THIS run counts: newer than
# NAME.result-path (a resumed worker's earlier result keeps its marker); no record, no grace
# (`-nt` against a missing file is true in bash, false in dash). The wait mirrors the supervisor:
# the grace and 15 s for its stop (close_worker.sh's wait), then on while a commit or gate holds
# a lock in the worker's checkout (codex_worker.py busy(), which the supervisor waits out however
# long it runs); 100 s in all at most, under Claude Code's 120 s Bash timeout (lead decision),
# then the lead is told to run the resume again. Wall clock, not loops: a loop took ~6 s on a
# loaded host. in_grace sleeps one second and succeeds while the wait goes on.
grace_end=""
in_grace() {
  [ -n "$resume" ] || return 1
  if [ -z "$grace_end" ]; then
    [ -e "$wdir/$name.result-path" ] || return 1
    for f in "$result" "$dir/QUESTION-$name.md" ""; do
      [ -n "$f" ] || return 1
      # find -newer: test's -nt is undefined in POSIX sh (SC3013), as in watch_workers.sh's newer().
      [ -n "$(find "$f" -prune -newer "$wdir/$name.result-path" 2>/dev/null)" ] && grep -qsF -- '<!-- codex-worker: ready -->' "$f" && break
    done
    g=${KIT_WORKER_GRACE:-60}; g=${g%%.*}; waited_from=$(date +%s); grace_end=$((waited_from + ${g:-0} + 15)); held=""; said=""
    printf '%s\n' "spawn_worker: the earlier session of '$name' has published and is in its closing grace: waiting up to $((grace_end - waited_from)) s for it to end, longer while a commit or gate runs in its checkout (100 s in all)"
  fi
  now=$(date +%s)
  [ $((now - waited_from)) -lt 100 ] ||
    die "the earlier session of '$name' still finishes${held:+ (a commit or gate holds its checkout: $held)}: run this resume again in a few minutes"
  if [ "$now" -ge "$grace_end" ]; then
    held=$(KIT_WORKER_CHECKOUT=$dir $kit_python -I -c 'import importlib.util, sys
s = importlib.util.spec_from_file_location("codex_worker", sys.argv[1])
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
print(" and ".join(p.name for p in m.locks() if m.busy([p])))' "$cworker" 2>/dev/null | tail -n 1) || held=""
    [ -n "$held" ] || return 1
    [ "$held" = "$said" ] || printf '%s\n' "spawn_worker: waiting on a commit or gate in its checkout ($held held)"
    said=$held
  fi
  sleep 1
}
# The name is refused while a Claude Code session of it runs, on the bg host too: a tab worker's
# NAME.id (a full sessionId) names no bg row, and a bg spawn of its name replaced its records (the bg check below is by id).
if [ -n "$windows" ]; then
  running=$(sessions "$name") || die "cannot list the Claude Code sessions to check the name '$name': $running"
  while [ -n "$running" ] && in_grace; do
    running=$(sessions "$name") || die "cannot list the Claude Code sessions to check the name '$name': $running"
  done
  [ -z "$running" ] || die "a Claude Code session named '$name' already runs (process $running)"
fi
if [ -n "$bg" ]; then
  # The daemon a launch starts keeps that launch's environment and hands it to every background
  # session while it lives, the owner's own too (POSIX spike, contract change 2): the worker's
  # variables travel in the merged settings' env only, and a spawning worker's own never leave here.
  unset MYAGENTKIT_ROLE CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL MYAGENTKIT_SESSION_ID
  old=""; [ ! -f "$wdir/$name.id" ] || old=$(cat -- "$wdir/$name.id")
  # An earlier session on another login folder than this spawn's is listed there alone: the list of
  # the folder it lives on (the rule: list_workers.sh) says whether it runs, or this spawn would
  # replace the record of a running worker.
  recorded=""
  if [ -n "$old" ]; then
    recorded=$(CDPATH= cd -- "${wdir%/.myagentkit/workers}" && sh "${cworker%/*}/list_workers.sh" --config "$name") ||
      die "cannot read the login folder of the earlier session $old of '$name'"
  fi
  old_row() { if [ -n "$recorded" ]; then export CLAUDE_CONFIG_DIR="$recorded"; else unset CLAUDE_CONFIG_DIR; fi; bg_row "$old"; }
  if [ -n "$old" ] && [ "${recorded:-$HOME/.claude}" != "${CLAUDE_CONFIG_DIR:-$HOME/.claude}" ]; then
    row=$(old_row) || die "cannot read claude agents of the login folder ${recorded:-$HOME/.claude} to check the earlier session $old of '$name'"
    while case $row in [!-]*) in_grace ;; *) false ;; esac; do
      row=$(old_row) || die "cannot read claude agents of the login folder ${recorded:-$HOME/.claude} to check the earlier session $old of '$name'"
    done
    attach_cmd="env -u CLAUDE_CONFIG_DIR "; [ -z "$recorded" ] || attach_cmd="CLAUDE_CONFIG_DIR=$(q "$recorded") "
    case $row in
      [!-]*) die "the background session $old of '$name' still runs on the login folder ${recorded:-$HOME/.claude}: close it first (scripts/close_worker.sh $name), or look at it (${attach_cmd}claude attach $old)" ;;
    esac
  fi
  if [ -n "$old" ]; then
    row=$(bg_row "$old") || die "cannot read claude agents to check the earlier session $old of '$name'"
    # L17: a usage limit leaves the session blocked after its reset, and a session whose daemon
    # died keeps its last row (blocked, or working with no pid) while `claude logs` finds no job.
    # A resume takes either over in place: `claude stop` (best effort: a gone daemon has no job),
    # then a wait for its supervisor, so the stop's exit record never lands on the resumed run.
    # Never close_worker.sh, which removes the worktree; a session that truly runs still refuses.
    # Blocked is a limit only when its transcript ends on one (watch_workers.sh --limit, as its
    # LIMIT line): a session blocked on a permission prompt or a question waits for the lead.
    # Any row may be frozen by a gone daemon, one that listed a pid too: `claude logs` tells on its
    # first line ("No job matching", "connect ENOENT .../control.sock"); the rest is the worker's screen.
    stale=""
    case $row in blocked*)
      ! (CDPATH= cd -- "${wdir%/.myagentkit/workers}" && sh "${cworker%/*}/watch_workers.sh" --limit "$name") >/dev/null 2>&1 ||
        stale="blocked at a usage limit" ;;
    esac
    case $stale$row in blocked*|live*|starting*) case $(claude logs "$old" </dev/null 2>&1 | head -n 1) in
        *"job not found"*|*"No job matching"*|*"connect ENOENT"*control.sock*) stale="left by its gone daemon" ;; esac ;;
    esac
    if [ -n "$stale" ]; then
      [ -n "$resume" ] || die "the background session $old of '$name' is $stale: resume it in place with --resume $old (it stops the session first; close_worker.sh would remove its worktree)"
      claude stop "$old" </dev/null >/dev/null 2>&1 || :
      printf '%s\n' "spawn_worker: the background session $old of '$name' is $stale: stopped it, resuming it in place"
      [ ! -e "$wdir/$name.live" ] || $kit_python -I -c 'import importlib.util, sys, time
from pathlib import Path
s = importlib.util.spec_from_file_location("codex_worker", sys.argv[1])
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
live, end = Path(sys.argv[2]), time.monotonic() + 20
while live.exists() and not m.gone(live, 0) and time.monotonic() < end:
    time.sleep(1)
sys.exit(live.exists() and not m.gone(live, 0))' "$cworker" "$wdir/$name.live" ||
        printf '%s\n' "spawn_worker: its earlier supervisor still runs after 20 s (its session never ended): it watches the resumed run too"
      row="-"
    fi
    while case $row in [!-]*) in_grace ;; *) false ;; esac; do
      row=$(bg_row "$old") || die "cannot read claude agents to check the earlier session $old of '$name'"
    done
    case $row in
      blocked*) die "the background session $old of '$name' still runs, blocked on a question or a permission prompt: answer it (${config_cmd}claude attach $old); close_worker.sh would stop it and drop its pending call" ;;
      [!-]*) die "the background session $old of '$name' still runs: close it first (scripts/close_worker.sh $name)" ;;
    esac
  fi
  sid=$resume
  if [ -n "$resume" ] && [ "${resume%%-*}" = "$resume" ]; then
    # A short id resumes nothing: it starts a new session stuck in the resume picker (POSIX
    # spike). The full sessionId comes from NAME.session, else from the session's row.
    sid=""; [ ! -f "$wdir/$name.session" ] || sid=$(cat -- "$wdir/$name.session")
    case $sid in "$resume"-*) ;; *)
      row=$(bg_row "$resume") || die "cannot read claude agents to find the session $resume"
      sid=${row#* } ;;
    esac
    case $sid in "$resume"-*) ;; *) die "no full session id for $resume: pass the sessionId that claude agents --json --all lists" ;; esac
  fi
  prepare_settings
  prepare_worktree
  place_brief
  supervisor
  reset_state
  record_result
  if [ -n "$resume" ]; then
    bg_cmd="claude $(q "$instruction") --resume $(q "$sid") --bg"
  else
    bg_cmd="claude $(q "$instruction") --bg ${cmd#claude }"
  fi
  # From here a session may run in the worktree: a failure leaves it there (stranded above).
  launched=1
  rc=0; out=$(CDPATH= cd -- "$dir" && eval "exec $bare $bg_cmd" </dev/null 2>&1) || rc=$?
  printf '%s\n' "$out" | LC_ALL=C tr '\001-\011\013-\037\177' '?'
  case $out in *"Workspace not trusted"*)
    launched=""  # refused before any session (spike T1): the unused worktree goes
    common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) && root=${common%/.git} || root=$dir
    die "Claude Code does not trust this folder yet: run \`claude\` once in $(native "$root") and accept the trust prompt, then spawn again (a trusted repo root covers the worktrees inside it)" ;;
  esac
  id=$(printf '%s\n' "$out" | LC_ALL=C sed -n 's/.*backgrounded[^0-9a-f]*\([0-9a-f]\{8,\}\).*/\1/p' | sed -n 1p)
  [ "$rc" -eq 0 ] && [ -n "$id" ] || die "claude --bg exited $rc and printed no session id, so no worker is recorded; its output is above"
  if [ -n "$resume" ] && [ "$id" != "${sid%%-*}" ]; then
    claude stop "$id" </dev/null >/dev/null 2>&1 || :
    claude rm "$id" </dev/null >/dev/null 2>&1 || :
    die "claude --resume started a copy ($id, now stopped and removed) instead of continuing ${sid%%-*}; answer it by hand: ${config_cmd}claude attach ${sid%%-*}"
  fi
  [ -z "$resume" ] || record_config
  printf '%s\n' "$id" > "$wdir/$name.id" || die "cannot record the session id $id in $wdir"
  # The full sessionId, the only one a resume takes: from the row, which may lag the launch.
  [ -z "$resume" ] || full=$sid
  i=0
  while [ -z "${full:-}" ] && [ "$i" -lt 10 ]; do
    row=$(bg_row "$id") || row=""
    case ${row#* } in "$id"-*) full=${row#* } ;; *) i=$((i + 1)); sleep 1 ;; esac
  done
  [ -z "${full:-}" ] || printf '%s\n' "$full" > "$wdir/$name.session" || die "cannot record the session id $full in $wdir"
  # Started in the worker's folder, which names its checkout's locks; the supervisor itself then
  # runs from the temporary folder, so it never holds the worktree a close removes.
  (CDPATH= cd -- "$dir" && eval "KIT_WORKER_EXIT=$(q "$(native "$wdir/$name.exit")") KIT_WORKER_GRACE=$(q "${KIT_WORKER_GRACE:-60}") KIT_WORKER_STARTED=$(q "$start")${resume:+ KIT_WORKER_RESUME=1} $kit_python $(q "$cworker") --detach $(q "$(native "$wdir/$name.supervisor.log")") $(q "$cquestion") $(q "$cresult") --bg $(q "$id")") ||
    die "the session $id runs without its supervisor, so nothing ends it on its result: close it with scripts/close_worker.sh $name once it is finished"
  printf '%s\n' "spawn_worker: '$name' started with $brief as background session $id"
  watch_line
  printf '%s\n' "spawn_worker: to see it: ${config_cmd}claude agents (every session, one list), ${config_cmd}claude attach $id (opens it in a real terminal; detaching leaves it running), ${config_cmd}claude logs $id (its last screen)"
  printf '%s\n' "spawn_worker: to answer it in its own session once it has ended: ${config_cmd}scripts/spawn_worker.sh $name ANSWER_FILE $again --resume ${full:-$id} (the session keeps its saved options: a changed model or effort needs a new spawn)"
  printf '%s\n' "spawn_worker: once you decide the session is finished, close it: scripts/close_worker.sh $name"
  exit 0
fi
if [ -n "$windows" ]; then
  prepare_settings
  prepare_worktree
  place_brief
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
    "t=\$(date +%s); $tab_cmd; s=\$?; grep -q ' published at ' $(q "$wdir/$name.exit") 2>/dev/null || [ \$((\$(date +%s) - t)) -gt 10 ] || { printf 'claude ended at once (exit %s); press Enter to close\n' \"\$s\"; read -r _; }" \
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
  [ -z "$resume" ] || record_config
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
  # Its transcript is how watch_workers.sh sees a usage-limit stop (LIMIT); close_worker.sh removes it.
  [ -z "$sid" ] || printf '%s\n' "$sid" > "$wdir/$name.id" || die "cannot record the session id $sid in $wdir"
  printf '%s\n' "spawn_worker: to answer it in its own session once its tab has ended: ${config_cmd}scripts/spawn_worker.sh $name ANSWER_FILE $again --resume ${sid:-SESSION_ID}"
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
[ -z "$worktree$lean" ] || prepare_settings
prepare_worktree
place_brief
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
[ -z "$resume" ] || record_config

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
# line ends are squeezed to one space before the match. The end is the instruction's own last
# 40 characters, so a sentence appended to it moves the match with it (a fixed phrase, left
# behind by one, let Enter arrive while the new tail was still being typed).
# Then confirm the prompt line emptied; if not, press Enter once more.
line_end=$(printf '%s' "$instruction" | tr -s ' \n' '  ' | tail -c 40)
landed() { tmux capture-pane -p -t "$name" -J | tr -s ' \n' '  ' | grep -qF -e "$line_end" -e "[Pasted text"; }
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
printf '%s\n' "spawn_worker: to answer it in its own session once its tmux session has ended: ${config_cmd}scripts/spawn_worker.sh $name ANSWER_FILE $again --resume SESSION_ID (the sessionId of the ${CLAUDE_CONFIG_DIR:-~/.claude}/sessions/PID.json named $name)"
if [ -n "$batch" ]; then
  printf '%s\n' "spawn_worker: --batch: not shown. Once every worker of this batch is started, show them together in one window: scripts/show_workers.sh NAME1 NAME2 ..."
else
  sh "$kit/show_workers.sh" "$name" || printf '%s\n' "spawn_worker: '$name' was not shown and runs anyway; attach by hand: tmux attach -t $name"
fi
