#!/usr/bin/env python3
"""PreToolUse(Bash|PowerShell|TaskStop): the owner decides before running work is ended.

On 2026-10-08 agents ended running work for no reason that held: a lead stopped a Codex
review that was fine (TaskStop), which left its `codex exec` running on, orphaned, spending
quota; another lead killed stuck worker sessions, which orphaned their `check.sh`, and those
raced its own gate in the same worktrees. Nothing was gained either time.

So ending a process (taskkill, Stop-Process, kill, pkill, killall, tmux kill-session) or
stopping a background task (TaskStop) is put to the owner first: the hook answers "ask", and
Claude Code asks the owner, who allows the valid cases. `scripts/close_worker.sh` is the
audited way to end a finished worker (it refuses while a gate or a commit runs); its call
names no ending command, so it is not asked about, while one chained to it is. Silent on
anything it cannot read: a broken input must never block a call.
"""
import json
import re
import sys

ENDS = re.compile(
    r"\b(taskkill|tskill|pkill|killall|Stop-Process|kill)\b|\btmux\s+kill-(session|server)\b|\.Kill\(\)",
    re.IGNORECASE)

try:
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")
    command = (data.get("tool_input") or {}).get("command", "") or ""
except Exception:
    sys.exit(0)

if tool == "TaskStop":
    what = "stops a running background task"
elif tool in ("Bash", "PowerShell") and ENDS.search(command):
    what = "ends a running process"
else:
    sys.exit(0)

print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": (
        f"This call {what}. Running work (a session, a review, a gate, a build) is never ended "
        "without a reason that holds: a stopped review or a killed worker orphans what it "
        "started, which runs on, spends quota and races the next run. Allow only if the owner "
        "asked for it or the work is provably finished or hung. A finished worker is closed "
        "with scripts/close_worker.sh. Never route around this check with another command "
        "or tool: if it is refused, the work keeps running."),
}}))
