#!/usr/bin/env python3
"""SubagentStop(diff-reviewer): record the paths a diff review saw, for guard_risky_review.py.

Writes {"head": HEAD, "paths": [...]} to the git folder's myagentkit-reviewed file: the paths
changed against HEAD when the review ends, joined with an earlier record for the same HEAD. It
only records and always exits 0: a SubagentStop hook's exit 2 would keep the reviewer running.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard_risky_review import changed, head, record_path, reviewed  # noqa: E402


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        if data.get("agent_type") != "diff-reviewer":
            return 0
        root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
        paths = sorted(changed(root) | reviewed(root))
        with open(record_path(root), "w", encoding="utf-8") as f:
            json.dump({"head": head(root), "paths": paths}, f)
    except Exception as error:  # a broken record only means the guard asks for the review again
        print("record_review: %s" % error, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
