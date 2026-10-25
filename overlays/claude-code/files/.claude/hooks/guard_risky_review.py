#!/usr/bin/env python3
"""PreToolUse(shell): refuse a `git commit` that changes a risky path no diff review has seen.

AGENTS.md makes a review of every risky diff required, and only the text held it: 2 of 10
headless kit runs committed a money-rounding fix without one (#307, ctl3 and ctl5). The risky
paths are `risky_paths` in scripts/gate_config.sh (space-separated globs, matched as Python's
fnmatch.fnmatchcase does, so a * also crosses a /); empty or still a placeholder, the hook is off.
`record_review.py` (SubagentStop, diff-reviewer) writes the paths changed against HEAD when a
review ends; a commit passes when every risky path it would change is among the paths recorded
for the current HEAD. Fixing the review's findings before the commit is the author's job
(docs/REVIEW_GATE.md, "Verdicts and who decides"), so a change after the review does not void it;
a new commit moves HEAD and starts the next record.
shortcut: it reads the shell command for `git ... commit` on one line, so a commit inside a script
(`sh scripts/sync_kit.sh`) is not seen; upgrade to the git hook if an agent commits that way.

Exit 2 blocks the call and returns the message to the agent (Claude Code hook protocol).
"""
import fnmatch
import json
import os
import re
import subprocess
import sys

COMMIT = re.compile(r"\bgit\b[^\n;&|]*?\bcommit\b")


def git(root, *args):
    result = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=20)
    return result.stdout if result.returncode == 0 else None


def head(root):
    return (git(root, "rev-parse", "--verify", "-q", "HEAD") or "").strip()


def changed(root):
    """Paths that differ from HEAD (staged, unstaged or untracked): what `git add -A` would commit."""
    tracked = git(root, "diff", "--name-only", "-z", "HEAD") if head(root) else git(root, "ls-files", "-z")
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    return {p for p in ((tracked or "") + (untracked or "")).split("\0") if p}


def record_path(root):
    path = (git(root, "rev-parse", "--git-path", "myagentkit-reviewed") or "").strip()
    return path if os.path.isabs(path) else os.path.join(root, path)


def risky_globs(root):
    try:
        with open(os.path.join(root, "scripts", "gate_config.sh"), encoding="utf-8") as f:
            match = re.search(r'^risky_paths="([^"]*)"', f.read(), re.M)
    except (OSError, UnicodeError):
        return []
    value = match.group(1) if match else ""
    return [] if "{{" in value else value.split()


def reviewed(root):
    try:
        with open(record_path(root), encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return set()
    return set(record.get("paths", [])) if record.get("head") == head(root) else set()


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if not COMMIT.search((data.get("tool_input") or {}).get("command") or ""):
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
    globs = risky_globs(root)
    if not globs:
        return 0
    risky = sorted(p for p in changed(root) if any(fnmatch.fnmatchcase(p, g) for g in globs))
    missing = [p for p in risky if p not in reviewed(root)]
    if not missing:
        return 0
    print("BLOCKED: this commit changes risky paths no diff review has seen since HEAD (%s). Start the "
          "diff-reviewer agent on the uncommitted diff (docs/REVIEW_GATE.md, \"Risk tiers\"), fix what it "
          "finds, then commit." % ", ".join(missing), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
