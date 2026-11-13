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
overrides the pin, so a call never needs one for such an agent. So is one that writes `model: inherit`
(the session's model and effort), but for its effort only while nothing sets
`CLAUDE_CODE_SUBAGENT_EFFORT`: Claude Code takes that variable before the session's effort for a
definition with no `effort:` (RESEARCH_LOG 2026-11-10 "subeffort", verified live), so a project that
sets it would run its required reviewer, `diff-reviewer` (inherit, no effort), below the author's
effort. With the variable in the hook's environment or in the `env` of the local, project or user
settings, such a call names its effort, except a review's when the variable is high, the ceiling a
review may run at (REVIEW_GATE.md, "Invariant"); xhigh or max is above it and refused too. A refusal for no model and no effort prints the routing
table's tier-1 row, copy-paste ready, for a read-only errand (one page, one lookup, #346): the
choice stays the lead's, it only no longer needs a look into the table.

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

It refuses a Fable worker too (docs/WORKFLOW.md "Worker cost" rule 2, owner 2026-11-03): Fable
leads, reviews and consults, it never does the work. A call whose model is Fable (`fable`,
`claude-fable-*`) passes only for a reviewer (a type whose name holds "review") or with a line
`Fable consult: REASON` (reads and answers, edits nothing) or `Fable worker approved by the owner:
REASON` (the owner's words for this task) at a line's start. A fork, and a type pinned `model:
inherit`, run on the session's model, which the last `message.model` in the tail of the hook
input's transcript gives; that check runs before the fork exemption.

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


def definitions(kind):
    """The frontmatter of the agent definitions named `kind`. Claude Code finds a definition by its
    `name:` field in any .md under the folder, not by the file name, and the project folder wins
    over the user folder (code.claude.com/docs/en/sub-agents). A plugin agent (`plugin:name`) is
    not looked up."""
    if not re.fullmatch(r"[\w.-]+", kind or ""):
        return []
    for folder in (os.path.join(os.environ.get("CLAUDE_PROJECT_DIR") or ".", ".claude", "agents"),
                   os.path.join(os.path.expanduser("~"), ".claude", "agents")):
        found = [head for root, _, files in os.walk(folder) for name in files if name.endswith(".md")
                 for head in [frontmatter(os.path.join(root, name))] if head.get("name") == kind]
        if found:
            return found
    return []


def chosen(head, field):
    """The definition writes a value for `field`, not a setup placeholder."""
    return bool(re.match(r"[^\s{]", head.get(field, "")))


def pinned(kind):
    """Whether the agent definition named `kind` pins both model and effort (not a setup
    placeholder), or writes `model: inherit`, which chooses the session's model and effort. Two
    definitions with one name: both must pin."""
    found = definitions(kind)
    # `model: inherit` is a written choice (the reviewer runs on the session's tier, #307).
    return bool(found) and all(chosen(head, "model") and (head["model"] == "inherit" or chosen(head, "effort"))
                               for head in found)


def subagent_effort():
    """CLAUDE_CODE_SUBAGENT_EFFORT as the session may see it: the hook's environment, else the `env`
    of .claude/settings.local.json, .claude/settings.json or the user's settings.json, in that order.
    An unreadable file counts as none; managed settings are not read."""
    if os.environ.get("CLAUDE_CODE_SUBAGENT_EFFORT"):
        return os.environ["CLAUDE_CODE_SUBAGENT_EFFORT"]
    project = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR") or ".", ".claude")
    user = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    for path in (os.path.join(project, "settings.local.json"), os.path.join(project, "settings.json"),
                 os.path.join(user, "settings.json")):
        try:
            with open(path, encoding="utf-8") as f:
                value = (json.load(f).get("env") or {}).get("CLAUDE_CODE_SUBAGENT_EFFORT")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(value, str) and value:
            return value
    return None


def session_model(path):
    """The session's model: the last transcript line whose JSON has message.model, read from the
    last 64 KiB. Missing, unreadable or none found: None, and the call passes (fail-open: the
    explicit-model check is the main guard, and a hook must not stop every fork on a bad read)."""
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.fstat(f.fileno()).st_size - 65536))
            tail = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError, ValueError):
        return None
    for line in reversed(tail):
        try:
            model = (json.loads(line).get("message") or {}).get("model")
        except (ValueError, AttributeError):
            continue
        if isinstance(model, str) and model and not model.startswith("<"):  # not "<synthetic>"
            return model
    return None


data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
if data.get("tool_name") not in ("Agent", "Task"):
    sys.exit(0)
call = data.get("tool_input") or {}
text = "%s\n%s" % (call.get("description") or "", call.get("prompt") or "")
# A present-tense verb only: "the author ran check.sh" reports a job, it does not wait on one;
# "Merge-sort" is no merge ("re-merge" is), and ci only on its own ("CI/CD", "ci.yml" are names; "ci-build" is a job, "ci-lint.sh" a file).
LONG_JOB = re.compile(
    r"\b(?:(?<![\w-])(?:re-)?merg(?:e|es|ing)(?!-)|gh run watch"
    r"|(?:run|runs|running|watch|watches|watching|wait(?:s|ing)? (?:for|on)) "
    r"(?:[^\s.;:]+ ){0,3}?(?:[\w./-]*?\b(?:gate|pipeline|review\.sh|check\.sh|gh run)|(?<![\w./-])ci(?![./]|-cd\b|-[\w-]*\.\w)))\b", re.I)
# A merge after an article, a demonstrative or a possessive is a noun ("the merge", "the author's merge");
# "Let's merge", "it's merging" are verbs.
NOUN = re.compile(r"(?:\b(?:the|a|an|this|that|its|each|every|any|one)|\b(?!(?:let|it|that|what|there|here|who|he|she)'s )\w+'s) $", re.I)
# A prohibition waits on nothing: "Do not run the gate.", "Never run check.sh", "Don't wait for CI".
NOT = re.compile(r"\b(?:not|never|don't|do not|no need to) (?:to )?$", re.I)
# Backticks, double quotes and quoting apostrophes dropped (not the one in "don't"), every blank
# run (a newline, a tab, a rich-text paste's non-breaking space) one space: "run `check.sh`" is the same wait.
scan = re.sub(r"\s+", " ", re.sub(r"[`\"]|'(?!\w)|(?<!\w)'", "", text))
jobs = sorted({m.group(0).lower() for m in LONG_JOB.finditer(scan)
               if not NOT.search(scan, 0, m.start())
               and not (re.match(r"(?:re-)?merg", m.group(0), re.I) and NOUN.search(scan, 0, m.start()))})
if jobs and not re.search(r"^\s*No long wait:", text, re.M | re.I):
    print(
        "BLOCKED: this sub-agent names a long job (%s). A sub-agent runs on the five-minute cache, "
        "so a wait past five minutes re-writes its whole context: run it as a scripts/spawn_worker.sh "
        "session (docs/WORKFLOW.md \"Worker cost\" rule 1). If it will not wait past five minutes, "
        "add a line \"No long wait: REASON\" to the prompt and call again." % ", ".join(jobs),
        file=sys.stderr,
    )
    sys.exit(2)
kind = call.get("subagent_type") or ""
if "review" not in kind.lower():
    # A fork runs on the session's model whatever the call names; so does a type pinned `model: inherit`.
    # With no per-call model a type runs on its definition's pin (review 20261103T200903Z-9741b0f48830).
    pins = [] if call.get("model") or kind == "fork" else [h.get("model") for h in definitions(kind)]
    inherits = kind == "fork" or "inherit" in pins
    models = ([session_model(data.get("transcript_path"))] if inherits else [call.get("model")]) + pins
    model = next((m for m in models if isinstance(m, str) and re.match(r"(?:claude-)?fable(?:-|\b)", m, re.I)), None)
    if (model
            and not re.search(r"^[ \t]*(?:Fable consult|Fable worker approved by the owner):[ \t]*\S",
                              call.get("prompt") or "", re.M)):
        print(
            "BLOCKED: this sub-agent would be a Fable (%s) worker. Fable leads, reviews and consults; it never "
            "does the work (docs/WORKFLOW.md \"Worker cost\" rule 2, owner 2026-11-03): pick the routine model "
            "from \"Model routing\". For a read-only consultation that edits nothing, add a line \"Fable consult: "
            "REASON\"; for a worker the owner approved for this task, a line \"Fable worker approved by the owner: "
            "REASON\" with the owner's words; then call again." % model,
            file=sys.stderr,
        )
        sys.exit(2)
if kind == "fork":
    sys.exit(0)
missing = [name for name in ("model", "effort") if not call.get(name)]
level = None if call.get("effort") else subagent_effort()
# hooka2, hookb: high is the ceiling a review may run at (REVIEW_GATE.md, "Invariant": never xhigh or max),
# so only high runs a review at it; xhigh or max would run it above, any other value below. A worker type
# that inherits still names its own effort.
ceiling = "review" in kind.lower() and str(level).strip().lower() == "high"
if level and not ceiling and any(head.get("model") == "inherit" and not chosen(head, "effort") for head in definitions(kind)):
    print(
        "BLOCKED: CLAUDE_CODE_SUBAGENT_EFFORT=%s is set and `%s` writes `model: inherit` with no effort, so this "
        "call would run at %s, not at your own effort: Claude Code takes the variable before the session's effort. "
        "Call again with \"effort\" named: for a required review at least your own effort and never above "
        "\"effort\": \"high\" (docs/REVIEW_GATE.md, \"Invariant\"), else from the effort table in docs/WORKFLOW.md "
        "\"Model routing\"." % (level, kind, level),
        file=sys.stderr,
    )
    sys.exit(2)
if not missing or pinned(kind):
    sys.exit(0)
print(
    "BLOCKED: this Agent call names no %s. Call again with both model and effort (or pin both in the "
    "agent's .claude/agents/ definition): the model from docs/WORKFLOW.md \"Model routing\", the effort from "
    "its effort table; tell the owner first, in one plain line, which and why.\n"
    "A read-only errand (one web page, one lookup, a search, a summary) is that table's tier 1: add "
    "\"model\": \"haiku\", \"effort\": \"medium\" (\"sonnet\" when the summary must weigh details)." % " and no ".join(missing),
    file=sys.stderr,
)
sys.exit(2)
