#!/usr/bin/env python3
"""PreToolUse(Agent): refuse a subagent started without a model and an effort.

A subagent without them inherits the lead's model and effort, and nothing in its output shows
which it got: five research errands once ran on the strongest model because the call named
neither. `docs/WORKFLOW.md` ("Model routing", "Worker cost" rule 5) says both are chosen from
the tables and never inherited; this hook makes the Agent call obey it. A fork is exempt: it
always runs on the lead's model and effort, and the call cannot change either.
Claude Code sub-agents doc: a fork keeps the main conversation's model and cannot take a
per-call effort (code.claude.com/docs/en/sub-agents).
An agent whose definition (`.claude/agents/<type>.md` in the project or the user folder) pins
both `model` and `effort` is exempt too: the pin is the choice (#137). A per-call value still
overrides the pin, so a call never needs one for such an agent.

The reason for the choice is the lead's to tell the owner before the start; no hook sees chat.

Exit 2 blocks the call and returns the message to the agent (Claude Code hook protocol).
"""
import json
import os
import re
import sys


def pinned(kind):
    """Whether the agent definition `kind` pins both model and effort (not a setup placeholder,
    not `inherit`). A plugin agent (`plugin:name`) is not looked up."""
    if not re.fullmatch(r"[\w.-]+", kind or ""):
        return False
    for folder in (os.path.join(os.environ.get("CLAUDE_PROJECT_DIR") or ".", ".claude", "agents"),
                   os.path.join(os.path.expanduser("~"), ".claude", "agents")):
        try:
            with open(os.path.join(folder, kind + ".md"), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        head = text.split("---", 2)[1] if text.startswith("---") else ""
        return all(re.search(rf"^{field}:[ \t]*(?!inherit\b)[^\s{{]", head, re.M) for field in ("model", "effort"))
    return False


data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
if data.get("tool_name") not in ("Agent", "Task"):
    sys.exit(0)
call = data.get("tool_input") or {}
if call.get("subagent_type") == "fork":
    sys.exit(0)
missing = [name for name in ("model", "effort") if not call.get(name)]
if not missing or pinned(call.get("subagent_type")):
    sys.exit(0)
print(
    "BLOCKED: this Agent call names no %s, so it would inherit the lead's. Pick the model from "
    "docs/WORKFLOW.md \"Model routing\" (a worker: the cheapest tier that fits the work; a reviewer: "
    "the strongest model available that is not the author's tier) and the effort from its effort "
    "table, pass both on the call, and tell the owner first, in one plain line, which model and "
    "effort and why." % " and no ".join(missing),
    file=sys.stderr,
)
sys.exit(2)
