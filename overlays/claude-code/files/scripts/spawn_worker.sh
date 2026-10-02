#!/usr/bin/env sh
# Open a SEPARATE Claude Code worker session in tmux and hand it a brief file.
#
# Usage: spawn_worker.sh NAME BRIEF_FILE [--model M] [--settings JSON_OR_FILE]
#                        [--allowed-tools LIST] [--worktree]
#
# Why a separate session and not a sub-agent: a sub-agent's prompt cache lives 5 minutes and
# a separate session's lives an hour, so a worker that waits on a long job re-writes its
# whole context after every wait as a sub-agent and does not as a session (docs/WORKFLOW.md,
# "Worker cost"). A sub-agent with `experimental.cacheTtl: 1h` in its definition costs the
# same; the session adds visibility (`tmux attach -t NAME`) and survives the lead ending.
#
# The lead then subscribes once with SendMessage `notify_when_idle` and reads the result
# FILE the brief asks the worker to write. It does not poll and it does not chat with the
# worker: every message to an idle session is a full-context turn.
#
# Pitfalls this script encodes (each one cost a session):
#   - The prompt is pasted AFTER the TUI is up, never passed on the command line after a
#     variadic flag such as --allowedTools, which would swallow it as one more value and
#     leave the session idle at an empty input line.
#   - Readiness is detected from the pane text, not from `pgrep -f`, which matches its own
#     command line.
#   - The folder must already be trusted by Claude Code; an untrusted folder blocks the
#     session in the trust dialog, which this script reports instead of waiting forever.
set -eu

die() { echo "spawn_worker: $1" >&2; exit 1; }
[ $# -ge 2 ] || { sed -n '2,8p' "$0"; exit 2; }
name=$1; brief=$2; shift 2
[ -f "$brief" ] || die "brief file not found: $brief"
command -v tmux >/dev/null || die "tmux is not installed"
command -v claude >/dev/null || die "claude is not on PATH"

model=""; settings=""; tools=""; worktree=""
while [ $# -gt 0 ]; do
  case "$1" in
    --model)         model=$2; shift 2 ;;
    --settings)      settings=$2; shift 2 ;;
    --allowed-tools) tools=$2; shift 2 ;;
    --worktree)      worktree=1; shift ;;
    *) die "unknown option: $1" ;;
  esac
done

tmux has-session -t "=$name" 2>/dev/null && die "tmux session '$name' already exists"

# Variadic flags come LAST and the prompt is never on this line (see the header).
cmd="claude -n '$name'"
[ -n "$model" ]    && cmd="$cmd --model '$model'"
[ -n "$worktree" ] && cmd="$cmd -w '$name'"
[ -n "$settings" ] && cmd="$cmd --settings '$settings'"
[ -n "$tools" ]    && cmd="$cmd --allowedTools '$tools'"

tmux new-session -d -s "$name" -c "$PWD" -x 200 -y 50 "$cmd"

# Wait for the input line: the TUI shows its prompt arrow at the start of a line once ready
# (v2.1.285 follows the arrow with a NO-BREAK space, so the match is on the arrow alone)
# or its mode hint in the status bar; the trust dialog prints a question instead.
# Bounded: 60 seconds, then report.
i=0
while :; do
  pane=$(tmux capture-pane -p -t "$name" 2>/dev/null || true)
  case "$pane" in
    *"trust"*"folder"*|*"Do you trust"*)
      die "session '$name' is waiting in the trust dialog; open the folder once by hand (tmux attach -t $name)" ;;
    *"
❯"*|*"shift+tab to cycle"*|*"for shortcuts"*) break ;;
  esac
  i=$((i + 1))
  [ "$i" -lt 60 ] || die "session '$name' did not show its input line within 60 s (tmux attach -t $name)"
  sleep 1
done

tmux load-buffer -b "spawn-$name" "$brief"
tmux paste-buffer -d -b "spawn-$name" -t "$name"

# Submit only once the paste has landed: an Enter sent while the TUI is still receiving a
# bracketed paste is swallowed and the brief sits unsent at the prompt (seen on the first
# run of this script). Then confirm the prompt line emptied; if not, press Enter once more.
head=$(head -c 40 "$brief" | tr -d '\n')
i=0
until tmux capture-pane -p -t "$name" -J | grep -qF -- "$head"; do
  i=$((i + 1)); [ "$i" -lt 30 ] || die "the brief did not appear in session '$name' (tmux attach -t $name)"
  sleep 1
done
sleep 1
tmux send-keys -t "$name" Enter
sleep 3
if tmux capture-pane -p -t "$name" -J | grep -q "^❯.*$(printf '%s' "$head" | head -c 20 | sed 's/[][\\.*^$/]/\\&/g')"; then
  tmux send-keys -t "$name" Enter
fi
echo "spawn_worker: '$name' started with $brief (tmux attach -t $name to watch)"
