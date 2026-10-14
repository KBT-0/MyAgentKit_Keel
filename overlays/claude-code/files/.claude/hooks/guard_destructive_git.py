#!/usr/bin/env python3
"""PreToolUse(Bash): refuse a destructive git command while work is uncommitted.

`git reset --hard`, `git checkout -- <path>`, `git restore`, `git stash drop/clear`,
`git clean -f` and a force push all discard work that git cannot get back. Uncommitted
changes are not in the reflog: once they are gone, they are gone, and the only copy may
have been something a human wrote by hand.

This is not a style rule. An agent tidying up after itself will eventually run one of these
with somebody else's uncommitted work in the tree, and the loss is silent — the command
succeeds, prints nothing alarming, and the next `git status` looks clean.

The rule enforced here: **commit or stash first, then destroy.** The hook does not decide
whether the command is a good idea; it only refuses to let it take work nobody saved.

Exit 2 blocks the call and returns the message to the agent (Claude Code hook protocol).
"""
import json
import re
import subprocess
import sys

# (pattern, what it discards)
DESTRUCTIVE = [
    (r"\bgit\s+reset\b[^|;&]*--hard", "git reset --hard discards every uncommitted change"),
    (r"\bgit\s+checkout\b[^|;&]*\s--\s", "git checkout -- <path> overwrites the working copy"),
    (r"\bgit\s+checkout\s+-f\b", "git checkout -f overwrites the working copy"),
    (r"\bgit\s+restore\b(?![^|;&]*--staged\s*$)", "git restore overwrites the working copy"),
    (r"\bgit\s+clean\b[^|;&]*-[a-zA-Z]*[fdx]", "git clean deletes untracked files"),
    (r"\bgit\s+stash\s+(drop|clear)\b", "git stash drop/clear deletes stashed work"),
    (r"\bgit\s+push\b[^|;&]*(--force(?!-with-lease)|\s-f\b)", "a force push can discard remote commits"),
]

data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
if data.get("tool_name") != "Bash":
    sys.exit(0)
command = data.get("tool_input", {}).get("command", "") or ""

hit = next(((p, why) for p, why in DESTRUCTIVE if re.search(p, command)), None)
if hit is None:
    sys.exit(0)

try:
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()
except Exception:
    # If we cannot tell whether the tree is dirty, assume it is. Refusing a safe command
    # costs a sentence; allowing an unsafe one costs the work.
    dirty = "(could not read git status — assuming there is uncommitted work)"

if not dirty:
    sys.exit(0)

print(
    f"BLOCKED: {hit[1]}, and this tree has uncommitted changes:\n\n"
    f"{dirty}\n\n"
    "Uncommitted work is NOT in the reflog. If any of the above is not yours — a file the "
    "owner edited by hand, a note written this session — this command is the last moment it "
    "exists.\n\n"
    "Do one of these first, then re-run:\n"
    "  git stash push -u -m 'before <what you are about to do>'   # recoverable\n"
    "  git add -A && git commit -m 'wip'                          # recoverable\n\n"
    "If you have checked the list above and every entry is disposable, say so to the owner "
    "and ask them to run the command themselves.",
    file=sys.stderr,
)
sys.exit(2)
