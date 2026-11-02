#!/usr/bin/env python3
"""PreToolUse(shell): refuse a `git commit` that changes a risky path no diff review has seen.

AGENTS.md makes a review of every risky diff required, and only the text held it: 2 of 10
headless kit runs committed a money-rounding fix without one (#307, ctl3 and ctl5). The risky
paths are `risky_paths` in scripts/gate_config.sh (space-separated globs, matched as Python's
fnmatch.fnmatchcase does, so a * also crosses a /); empty or still a placeholder, the hook is off.
`record_review.py` notes the paths changed against HEAD when a diff-reviewer starts
(SubagentStart) and records them when it ends (SubagentStop); a commit passes when every risky
path it would change is among the paths recorded for the current HEAD. A rename counts as both
its paths, and the risky paths are HEAD's setting joined with the working tree's, so a commit
cannot narrow the setting it is checked against. Fixing the review's findings before the commit is the author's job
(docs/REVIEW_GATE.md, "Verdicts and who decides"), so a change after the review does not void it;
a new commit moves HEAD and starts the next record.
shortcut: it reads the shell command for `git ... commit` on one line, so a commit inside a script
(`sh scripts/sync_kit.sh`) is not seen, and it runs before the command, so a risky file the same
command writes first (`git apply fix.patch && git commit -am fix`) is not seen either; upgrade to
the git hook if an agent commits that way.

Exit 2 blocks the call and returns the message to the agent (Claude Code hook protocol).
"""
import fnmatch
import json
import os
import re
import subprocess
import sys

# `commit` as git's subcommand, after global options (-C dir, -c k=v, --no-pager): `git show HEAD:commit.md` is none
# The two option forms never match the same text (-c/-C take a value; others never are -c/-C): no backtracking blow-up.
COMMIT = re.compile(r"\bgit(?:\s+(?:-[Cc]\s+(?:[^\s\"']|\"[^\"]*\"|'[^']*')+|-(?![Cc]\s)[\w-]+(?:=\S+)?))*"
                    r"\s+commit(?![\w-])")


def git(root, *args):
    result = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=20)
    return result.stdout if result.returncode == 0 else None


def head(root):
    return (git(root, "rev-parse", "--verify", "-q", "HEAD") or "").strip()


def changed(root):
    """Paths that differ from HEAD (staged, unstaged or untracked): what `git add -A` would commit."""
    # --no-renames: a rename out of a risky folder lists its old path too
    tracked = git(root, "diff", "--name-only", "--no-renames", "-z", "HEAD") if head(root) else git(root, "ls-files", "-z")
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    return {p for p in ((tracked or "") + (untracked or "")).split("\0") if p}


def record_path(root):
    path = (git(root, "rev-parse", "--git-path", "myagentkit-reviewed") or "").strip()
    return path if os.path.isabs(path) else os.path.join(root, path)


def risky_globs(root):
    """HEAD's risky_paths joined with the working tree's: an edit that empties the setting does
    not switch the guard off for its own commit."""
    texts = [git(root, "show", "HEAD:scripts/gate_config.sh") if head(root) else None]
    try:
        with open(os.path.join(root, "scripts", "gate_config.sh"), encoding="utf-8") as f:
            texts.append(f.read())
    except (OSError, UnicodeError):
        pass
    globs = set()
    for text in filter(None, texts):
        match = re.search(r'^risky_paths=(["\'])(.*?)\1', text, re.M)
        value = match.group(2) if match else ""
        globs |= set() if "{{" in value else set(value.split())
    return sorted(globs)


def read_record(root):
    try:
        with open(record_path(root), encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) and record.get("head") == head(root) else {}


def reviewed(root):
    return set(read_record(root).get("paths", []))


def project_root(data):
    """The work tree the call runs in (a worktree session's own), not the folder the session started in (#317)."""
    where = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    return (git(where, "rev-parse", "--show-toplevel") or "").strip() or where


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if not COMMIT.search((data.get("tool_input") or {}).get("command") or ""):
        return 0
    root = project_root(data)
    globs = risky_globs(root)
    if not globs:
        return 0
    risky = sorted(p for p in changed(root) if any(fnmatch.fnmatchcase(p, g) for g in globs))
    missing = [p for p in risky if p not in reviewed(root)]
    if not missing:
        return 0
    print("BLOCKED: this commit changes risky paths no diff review has seen since HEAD (%s). Start the "
          "diff-reviewer agent on the uncommitted diff, or for a hook, gate, CI or check-script change one "
          "`scripts/review.sh --uncommitted` round (docs/REVIEW_GATE.md, \"Invariant\"), fix what it finds, "
          "then commit." % ", ".join(missing), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
