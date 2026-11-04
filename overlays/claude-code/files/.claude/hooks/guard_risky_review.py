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
a new commit moves HEAD and starts the next record. A path also passes when it holds content an
accepted review saw (the common git folder's myagentkit-reviewed-content, path -> blob, "" = deleted),
which a --commit or --base review.sh round and a diff-reviewer record: so the commit or the merge of a
branch reviewed after its commits passes in any checkout (labricore A1), and a risky file that differs
from what was reviewed does not. A symlink's content is its target text, as git stores it. The tree
judged is every one the commit may stand in: a `cd DIR` before it adds DIR, read by
guard_destructive_git.commit_folders (one reader for both guards), and a `cd` the hook cannot resolve is
refused like such a `-C`.
A commit is found by guard_destructive_git.commit_folders too, the one git reader of both guards: this hook had
a regex of its own that missed `"git" commit` and `git --namespace x commit` (syncfind).
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


def content_path(root):
    common = (git(root, "rev-parse", "--git-common-dir") or "").strip()
    return os.path.join(common if os.path.isabs(common) else os.path.join(root, common), "myagentkit-reviewed-content")


def reviewed_content(root):
    try:
        with open(content_path(root), encoding="utf-8") as f:
            content = json.load(f)
    except (OSError, ValueError):
        return {}
    return content if isinstance(content, dict) else {}


def blob(root, path):
    """The working tree's content of `path` as a git blob id, "" when it is gone."""
    full = os.path.join(root, path)
    if os.path.islink(full):  # git's blob of a link (mode 120000) is its target text, as review_dispatch records it
        target = os.readlink(full)  # leeway v0.14.1 sync review: hash-object hashed the target's content
        try:
            run = subprocess.run(["git", "-C", root, "hash-object", "--stdin"], capture_output=True, timeout=20,
                                 input=os.fsencode(target.replace("\\", "/") if os.name == "nt" else target))
        except (OSError, subprocess.SubprocessError):
            return None
        return run.stdout.decode("ascii", "replace").strip() or None if run.returncode == 0 else None
    if not os.path.isfile(full):
        return ""
    return (git(root, "hash-object", "--", path) or "").strip() or None


def note_content(root, paths):
    """Add the current content of `paths` to the reviewed-content record (record_review.py)."""
    content = reviewed_content(root)
    content.update({p: b for p in paths for b in [blob(root, p)] if b is not None})
    with open(content_path(root), "w", encoding="utf-8") as f:
        json.dump(content, f, sort_keys=True)


def project_root(data):
    """The work tree the call runs in (a worktree session's own), not the folder the session started in (#317):
    the top folder of the call's cwd (for a commit, a folder commit_folders gives, its -C values applied);
    outside any work tree, the session's."""
    cwd = where = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    for folder in (where, cwd, os.environ.get("CLAUDE_PROJECT_DIR") or "."):
        top = (git(folder, "rev-parse", "--show-toplevel") or "").strip() if os.path.isdir(folder) else ""
        if top:
            return top
    return where


def folders(command, cwd, tool_name=None, why=None):
    """Every folder the commit may stand in, read by guard_destructive_git.commit_folders, so both guards follow
    the same `cd`s (keywords, if bodies, PowerShell's Set-Location/sl/Push-Location and `.\\wt`; review
    leewayfix High), [] when the line holds no commit; None for one the hook cannot name; a folder that does not
    exist is left out. A missing or unreadable reader, or an unbalanced quote, is None too on a line naming git."""
    try:
        sys.dont_write_bytecode = True  # no untracked __pycache__ beside the synced hooks
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import guard_destructive_git
        found = guard_destructive_git.commit_folders(command, cwd, tool_name, why)
    except Exception:  # noqa: BLE001 - an older or missing guard_destructive_git.py, or Unreadable
        return [None] if re.search("git", command, re.I) else []
    # A shell cannot stand in a folder that does not exist (`cd wt; cd wt` adds wt/wt), so none is judged there:
    # project_root would judge the session's tree in its place.
    return [c for c in found if c is None or c == cwd or os.path.isdir(c)]


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    command = (data.get("tool_input") or {}).get("command") or ""
    if "commit" not in command:  # each commit the reader finds holds the word; most calls end here, unparsed
        return 0
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    why = []
    roots = [None if c is None else project_root(dict(data, cwd=c))
             for c in folders(command, cwd, data.get("tool_name"), why)]
    if None in roots and why:
        # leeway v0.15 sync review: `git commit -am x && rg -n "git commit" docs` was refused with a message about
        # a cd or -C the line does not hold. Still refused: rg may run its text (--pre), as a wrapper or code may.
        print("BLOCKED: this line also runs %s, which names a git commit in the text of a program the hook cannot "
              "look through, so where that commit would stand, and its risky paths, cannot be checked. Run the "
              "commit as a command of its own, and the other command apart (grep reads its text as data)."
              % ", ".join("`%s`" % w for w in dict.fromkeys(why)), file=sys.stderr)
        return 2
    if None in roots:
        print("BLOCKED: this commit's git -C folder, or the folder a cd before it moves to, cannot be resolved by the "
              "hook (a variable, a shell-only expansion, an unbalanced quote, or guard_destructive_git.py missing "
              "beside this hook), so its risky paths cannot be checked. Run it with a literal folder.",
              file=sys.stderr)
        return 2
    missing = []
    for root in dict.fromkeys(roots):
        globs = risky_globs(root)
        risky = sorted(p for p in changed(root) if any(fnmatch.fnmatchcase(p, g) for g in globs)) if globs else []
        content = reviewed_content(root)
        missing += [p for p in risky if p not in reviewed(root) and (p not in content or content[p] != blob(root, p))]
    if not missing:
        return 0
    print("BLOCKED: this commit changes risky paths no diff review has seen since HEAD (%s). Start the "
          "diff-reviewer agent on the uncommitted diff, or for a hook, gate, CI or check-script change one "
          "`scripts/review.sh` round (--uncommitted, or --commit/--base for a committed branch you merge; "
          "docs/REVIEW_GATE.md, \"Invariant\"), fix what it finds, then commit." % ", ".join(missing), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
