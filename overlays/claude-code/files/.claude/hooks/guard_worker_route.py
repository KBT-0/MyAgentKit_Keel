#!/usr/bin/env python3
"""PreToolUse(Agent): refuse a subagent started without a model and an effort.

A subagent without them inherits the lead's model and effort, and nothing in its output shows
which it got: five research errands once ran on the strongest model because the call named
neither. `docs/WORKFLOW.md` ("Model routing", "Worker cost" rule 5) says both are chosen from
the tables and never inherited; this hook makes the Agent call obey it. A fork is exempt: it
always runs on the lead's model and effort, and the call cannot change either.
Claude Code sub-agents doc: a fork keeps the main conversation's model and cannot take a
per-call effort (code.claude.com/docs/en/sub-agents).
An agent whose definition (the `.claude/agents/` file whose `name:` is the type, in the project
or the user folder) pins
both `model` and `effort` is exempt too: the pin is the choice (#137). A per-call value still
overrides the pin, so a call never needs one for such an agent.

The reason for the choice is the lead's to tell the owner before the start; no hook sees chat.

It also refuses a sub-agent, a fork included, whose description or prompt tells it to run or
wait on a long job: a merge, `gh run watch`, or run/watch/wait for/wait on with a gate, CI, a
pipeline, review.sh, check.sh or `gh run` among the next few words of the same line (backticks or
quotes around the job do not hide it). Naming a
job is not a wait: the kit's own task prompt (core/docs/HANDOFF.md, "Day-to-day task prompt")
names the commit gate and CI, a reviewer reports that the author ran check.sh or reads "the
merge commit"; none is refused. A sub-agent runs on the five-minute cache, so a wait past five
minutes re-writes its whole context, and such a worker runs as a scripts/spawn_worker.sh session (docs/WORKFLOW.md "Worker cost" rule 1). In #307's
14-day baseline these waits cost $100 of Keel's re-writes, all background Agent calls ("Fix
round-3 review gate findings", "Merge three branches"). A refusal, not a warning: a warning
arrives after the sub-agent has started, and a false match costs one call again with a line
`No long wait: REASON` in the prompt.
shortcut: the hook reads only the call's description and prompt, so "Read briefs/w3.md and follow
it" with the merge inside the brief file passes, as does a verb and its job split across two
lines; upgrade to reading the files a prompt names if such a wait costs again (#307 baseline).

Exit 2 blocks the call and returns the message to the agent (Claude Code hook protocol).
"""
import json
import os
import re
import sys


def frontmatter(path):
    """The definition's `key: value` lines, YAML quotes taken off the value."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeError):
        return {}
    head = text.split("---", 2)[1] if text.startswith("---") else ""
    return {k: v.strip().strip("'\"") for k, v in re.findall(r"^(\w+):[ \t]*(.*?)[ \t]*$", head, re.M)}


def pinned(kind):
    """Whether the agent definition named `kind` pins both model and effort (not a setup
    placeholder), or writes `model: inherit`, which chooses the session's model and effort. Claude Code finds a definition by its `name:` field in any .md
    under the folder, not by the file name, and the project folder wins over the user folder
    (code.claude.com/docs/en/sub-agents). Two definitions with one name: both must pin. A plugin
    agent (`plugin:name`) is not looked up."""
    if not re.fullmatch(r"[\w.-]+", kind or ""):
        return False
    for folder in (os.path.join(os.environ.get("CLAUDE_PROJECT_DIR") or ".", ".claude", "agents"),
                   os.path.join(os.path.expanduser("~"), ".claude", "agents")):
        found = [head for root, _, files in os.walk(folder) for name in files if name.endswith(".md")
                 for head in [frontmatter(os.path.join(root, name))] if head.get("name") == kind]
        if found:
            # `model: inherit` is a written choice (the reviewer runs on the session's tier, #307).
            chosen = lambda head, field: bool(re.match(r"[^\s{]", head.get(field, "")))
            return all(chosen(head, "model") and (head["model"] == "inherit" or chosen(head, "effort"))
                       for head in found)
    return False


data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
if data.get("tool_name") not in ("Agent", "Task"):
    sys.exit(0)
call = data.get("tool_input") or {}
text = "%s\n%s" % (call.get("description") or "", call.get("prompt") or "")
# A present-tense verb only: "the author ran check.sh" reports a job, it does not wait on one;
# "the merge" and "a merge" are a noun.
LONG_JOB = re.compile(
    r"\b(?:(?<!the )(?<!a )merg(?:e|es|ing)|gh[ \t]+run[ \t]+watch"
    r"|(?:run|runs|running|watch|watches|watching|wait(?:s|ing)?[ \t]+(?:for|on))[ \t]+"
    r"(?:[^\s.;:]+[ \t]+){0,3}?[\w./-]*?\b(?:gate|ci|pipeline|review\.sh|check\.sh|gh[ \t]+run))\b", re.I)
# Backticks and quotes dropped, blank runs made one space: "run `check.sh`" is the same wait.
scan = re.sub(r"[ \t]+", " ", re.sub(r"[`\"']", "", text))
jobs = sorted({m.group(0).lower() for m in LONG_JOB.finditer(scan)})
if jobs and not re.search(r"^\s*No long wait:", text, re.M | re.I):
    print(
        "BLOCKED: this sub-agent names a long job (%s). A sub-agent runs on the five-minute cache, "
        "so a wait past five minutes re-writes its whole context: run it as a scripts/spawn_worker.sh "
        "session (docs/WORKFLOW.md \"Worker cost\" rule 1). If it will not wait past five minutes, "
        "add a line \"No long wait: REASON\" to the prompt and call again." % ", ".join(jobs),
        file=sys.stderr,
    )
    sys.exit(2)
if call.get("subagent_type") == "fork":
    sys.exit(0)
missing = [name for name in ("model", "effort") if not call.get(name)]
if not missing or pinned(call.get("subagent_type")):
    sys.exit(0)
print(
    "BLOCKED: this Agent call names no %s, so it would inherit the lead's. Pick the model from "
    "docs/WORKFLOW.md \"Model routing\" (a worker: the cheapest tier that fits the work; a reviewer: "
    "a small risky diff the diff-reviewer agent, which inherits the session's; a larger one the "
    "strongest model available that is not the author's tier, docs/REVIEW_GATE.md \"Invariant\") and the "
    "effort from its effort "
    "table, pass both on the call, and tell the owner first, in one plain line, which model and "
    "effort and why." % " and no ".join(missing),
    file=sys.stderr,
)
sys.exit(2)
