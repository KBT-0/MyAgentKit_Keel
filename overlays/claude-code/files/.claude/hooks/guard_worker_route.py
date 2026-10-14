#!/usr/bin/env python3
"""PreToolUse(Agent): refuse a subagent started without a model and an effort.

A subagent without them inherits the lead's model and effort, and nothing in its output shows
which it got: five research errands once ran on the strongest model because the call named
neither. `docs/WORKFLOW.md` ("Model routing", "Worker cost" rule 5) says both are chosen from
the tables and never inherited; this hook makes the Agent call obey it. A fork is exempt: it
always runs on the lead's model and effort, and the call cannot change either.

The reason for the choice is the lead's to tell the owner before the start; no hook sees chat.

Exit 2 blocks the call and returns the message to the agent (Claude Code hook protocol).
"""
import json
import sys

data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
if data.get("tool_name") not in ("Agent", "Task"):
    sys.exit(0)
call = data.get("tool_input") or {}
if call.get("subagent_type") == "fork":
    sys.exit(0)
missing = [name for name in ("model", "effort") if not call.get(name)]
if not missing:
    sys.exit(0)
print(
    "BLOCKED: this Agent call names no %s, so it would inherit the lead's. Pick the model from "
    "docs/WORKFLOW.md \"Model routing\" (the cheapest tier that fits the work) and the effort from "
    "its effort table, pass both on the call, and tell the owner first, in one plain line, which "
    "model and effort and why." % " and no ".join(missing),
    file=sys.stderr,
)
sys.exit(2)
