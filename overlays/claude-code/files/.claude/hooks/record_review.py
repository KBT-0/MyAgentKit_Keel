#!/usr/bin/env python3
"""SubagentStart / SubagentStop (diff-reviewer): record the paths a diff review saw, for guard_risky_review.py.

The git folder's myagentkit-reviewed file holds {"head": HEAD, "paths": [...], "pending": {agent_id:
[...]}}. A review's start notes the paths changed against HEAD under its agent id; its stop moves
them into "paths", joined with an earlier record for the same HEAD. A file made while the reviewer
ran is not among them, so the guard asks for it again. A stop with no start note records nothing.
It only records and always exits 0: a SubagentStop hook's exit 2 would keep the reviewer running.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard_risky_review import changed, head, read_record, record_path  # noqa: E402


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        if data.get("agent_type") != "diff-reviewer":
            return 0
        root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
        record = read_record(root)
        paths, pending = set(record.get("paths", [])), dict(record.get("pending", {}))
        agent = str(data.get("agent_id") or "")
        if data.get("hook_event_name") == "SubagentStart":
            pending[agent] = sorted(changed(root))
        else:
            paths |= set(pending.pop(agent, []))
        with open(record_path(root), "w", encoding="utf-8") as f:
            json.dump({"head": head(root), "paths": sorted(paths), "pending": pending}, f)
    except Exception as error:  # a broken record only means the guard asks for the review again
        print("record_review: %s" % error, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
