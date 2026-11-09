#!/usr/bin/env python3
"""SubagentStop, then the lead's PostToolUse and Stop: tell the lead when a sub-agent was answered
by another model than the one its call asked for (#342).

An Agent call with `model: fable` on an account without Fable credits runs on Opus with no
error, and the launch's `resolvedModel` still says Fable (leeway, 2026-11: ten such background
agents); only the `model` of the sub-agent transcript's answers is the truth. At SubagentStop the
hook reads the asked model from the `.meta.json` beside the sub-agent transcript (a "Fable
consult:" line in its prompt counts as asking Fable) and the answering models with
agent_cost.requests(); on a family mismatch it shows the owner a systemMessage and keeps the line
in the session folder (`<session>/myagentkit-model-fallback.txt`). A SubagentStop hook cannot put
context into the lead (its additionalContext keeps the sub-agent running, Claude Code hooks
docs, SubagentStop), so the lead's next PostToolUse or Stop takes the line as additionalContext:
MODEL_FALLBACK: asked <requested>, answered by <model>. It never blocks and always exits 0.
shortcut: a call that asks for no model family (none, `inherit`, a fork) is not checked, and a
broken read stays silent; upgrade if a fallback on the session's model costs a report.
"""
import collections
import json
import os
from pathlib import Path
import re
import sys

FAMILY = re.compile(r"fable|opus|sonnet|haiku", re.I)
CONSULT = re.compile(r"^[ \t]*Fable consult:[ \t]*\S", re.M)
NOTE = "myagentkit-model-fallback.txt"


def family(model):
    match = FAMILY.search(str(model or ""))
    return match.group(0).lower() if match else None


def prompt_of(path):
    """The sub-agent's first user message: its prompt."""
    with open(path, encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") == "user":
                content = (rec.get("message") or {}).get("content")
                return content if isinstance(content, str) else " ".join(
                    c.get("text", "") for c in content or [] if isinstance(c, dict))
    return ""


def fallback(data):
    """The MODEL_FALLBACK line for a stopped sub-agent, or None."""
    path = data.get("agent_transcript_path")
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(re.sub(r"\.jsonl$", ".meta.json", path), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        meta = {}
    asked = meta.get("model") if family(meta.get("model")) else ("fable" if CONSULT.search(prompt_of(path)) else None)
    if not asked:
        return None
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
    sys.path.insert(0, str(root / "scripts"))
    from agent_cost import requests  # noqa: E402 (the project's scripts/, beside the gate)
    models = [r["model"] for r in requests(Path(path))]
    wrong = collections.Counter(m for m in models if family(m) != family(asked))
    if not wrong:
        return None
    model, count = wrong.most_common(1)[0]
    return ("MODEL_FALLBACK: asked %s, answered by %s (%d of %d requests), sub-agent %r: do not report its "
            "result as %s's (#342)." % (asked, model, count, len(models), meta.get("description") or
                                        data.get("agent_type") or data.get("agent_id"), asked))


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if not data.get("transcript_path"):
        return
    event = data.get("hook_event_name")
    note = os.path.join(os.path.splitext(data["transcript_path"])[0], NOTE)
    if event == "SubagentStop":
        line = fallback(data)
        if line:
            os.makedirs(os.path.dirname(note), exist_ok=True)
            with open(note, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            print(json.dumps({"systemMessage": line}))
    elif event in ("PostToolUse", "Stop") and not data.get("agent_id"):  # the lead, not a sub-agent
        taken = note + ".%d" % os.getpid()
        try:
            os.replace(note, taken)  # one reader takes the lines, a second finds none
        except OSError:
            return
        with open(taken, encoding="utf-8") as f:
            text = f.read().strip()
        os.remove(taken)
        if text:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # a check that cannot read stays silent; it never stops the session
        print("model_check: %s" % error, file=sys.stderr)
    sys.exit(0)
