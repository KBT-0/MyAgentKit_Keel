#!/usr/bin/env python3
"""PreToolUse(Bash): refuse a git command that loses work, or one that skips the gate.

Two kinds of command are refused (the loss-certain subset; AGENTS.md's rule "commit or stash
before any command that discards work" still covers every destructive command):

- Always, whatever the tree's state: `git stash drop/clear` (the stash may be the only copy),
  a force push (`--force`, `-f`, `+refspec`, `--mirror`, `--delete`, `:ref`, and a bare
  `--force-with-lease`: only `--force-with-lease=ref:expected` or `--force-if-includes` pass),
  `git remote set-url/add` (it moves where a push goes), `git commit --amend` of a commit a
  remote branch already holds, and a skipped gate: `--no-verify`, `commit -n`,
  `-c core.hooksPath=...`, `--no-gpg-sign`. The gate's hatch is the owner's, typed in the
  owner's own terminal; this hook sees only an agent's Bash calls.
- While the tree has uncommitted work: `git reset --hard`, `git checkout -- <path>`,
  `git checkout -f`, `git restore` (unless index-only: `--staged` without `--worktree`) and
  `git clean -f/-d/-x` (unless `-n`/`--dry-run`). Uncommitted changes are not in the reflog:
  once they are gone, they are gone, and the only copy may have been something a human wrote.

The command is split with `shlex`, as the shell would; the options between `git` and its
subcommand (`-C dir`, `-c k=v`, `--git-dir=...`) are skipped, so `git -C . reset --hard` is
seen. The command string of `sh -c '...'` or `eval` is read the same way.
Sources: the vendor's default auto-mode block list
(https://code.claude.com/docs/en/permission-modes), Bash rule limits
(https://code.claude.com/docs/en/permissions), git-push, git-clean, git-restore
(https://git-scm.com/docs), githooks and anthropics/claude-code#40117 (an agent committed with
--no-verify despite a written rule). Settings run this hook with `onFailure: block`; a payload
it cannot read also blocks, because any exit but 2 lets the call through
(https://code.claude.com/docs/en/hooks).
ponytail: exact option names only; git also accepts unique abbreviations (`--no-veri`). The
hook stops accidents, not a determined caller; match prefixes if one ever shows.

Exit 2 blocks the call and returns the message to the agent (Claude Code hook protocol).
"""
import json
import re
import shlex
import subprocess
import sys

SEPARATORS = set(";&|\n()")
VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
GATE = ("this skips a git hook (the commit gate) or commit signing. Fix the failure. "
        "Only the owner bypasses this gate")


def segments(command):
    """Simple commands of a command line, each a token list."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|\n()<>")
    lexer.whitespace, lexer.whitespace_split = " \t\r", True
    try:
        tokens = list(lexer)
    except ValueError:  # an unbalanced quote, e.g. an apostrophe in a here-document
        tokens = [t.strip("'\"") for t in re.findall(r"[^\s;&|()]+|[;&|()\n]+", command)]
    segment = []
    for token in tokens + [";"]:
        if token and set(token) <= SEPARATORS:
            if segment:
                yield segment
            segment = []
        else:
            segment.append(token)


def short(args, letters, takes_value=""):
    """Whether a short-option cluster (`-anm`) sets one of `letters`."""
    for arg in args:
        if arg == "--":
            break
        if arg.startswith("-") and not arg.startswith("--"):
            for ch in arg[1:]:
                if ch in letters:
                    return True
                if ch in takes_value:
                    break
    return False


def git_out(dirs, *args):
    command = ["git", *[x for d in dirs for x in ("-C", d)], *args]
    return subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace",
                          timeout=10, check=True).stdout.strip()


def verdict(tokens):
    """(always, why) for a git invocation that must stop, (False, why) for one that needs a clean
    tree, None for one that may run. `tokens` follow the word `git`."""
    dirs, configs, i = [], [], 0
    while i < len(tokens) and tokens[i].startswith("-"):
        if tokens[i] in VALUE_OPTIONS and i + 1 < len(tokens):
            (dirs if tokens[i] == "-C" else configs).append(tokens[i + 1])
            i += 2
        else:
            configs += [tokens[i].split("=", 1)[1]] if tokens[i].startswith("--config-env=") else []
            i += 1
    sub, args = (tokens[i:i + 1] or [""])[0], tokens[i + 1:]
    flags, words = set(args), [a for a in args if not a.startswith("-")]
    first = (words or [""])[0]
    if (flags & {"--no-verify", "--no-gpg-sign"} or (sub == "commit" and short(args, "n", "mFCctuS"))
            or any(c.split("=", 1)[0].lower() == "core.hookspath" for c in configs)):
        return True, GATE, dirs
    if sub == "stash" and first in ("drop", "clear"):
        return True, "git stash drop/clear deletes stashed work, which may be its only copy", dirs
    if sub == "remote" and first in ("set-url", "add"):
        return True, "git remote set-url/add changes where a push goes", dirs
    if sub == "push":
        lease = [a for a in args if a.split("=", 1)[0] == "--force-with-lease"]
        lease_ok = "--force-if-includes" in flags or all("=" in a and ":" in a for a in lease)
        if (flags & {"--force", "--mirror", "--delete"} or short(args, "fd", "o")
                or any(w.startswith(("+", ":")) for w in words) or not lease_ok):
            return True, "a force push or a remote delete can discard commits on the remote", dirs
    if sub == "commit" and "--amend" in flags:
        try:
            pushed = bool(git_out(dirs, "branch", "-r", "--contains", "HEAD"))
        except Exception:
            pushed = True  # cannot tell: refuse, as below
        if pushed:
            return True, "git commit --amend rewrites a commit a remote branch already holds", dirs
    if sub == "reset" and "--hard" in flags:
        return False, "git reset --hard discards every uncommitted change", dirs
    if sub == "checkout" and ("--" in flags or "--force" in flags or short(args, "f", "bB")):
        return False, "git checkout -- <path> / -f overwrites the working copy", dirs
    if sub == "restore":
        staged = "--staged" in flags or short(args, "S", "s")
        worktree = "--worktree" in flags or short(args, "W", "s")
        if worktree or not staged:
            return False, "git restore overwrites the working copy", dirs
    if sub == "clean" and not ("--dry-run" in flags or short(args, "n", "e")):
        if "--force" in flags or short(args, "fdx", "e"):
            return False, "git clean deletes untracked files", dirs
    return None


def hits(command):
    for segment in segments(command):
        for n, token in enumerate(segment):
            if re.split(r"[\\/]", token)[-1].lower() in ("git", "git.exe"):
                found = verdict(segment[n + 1:])
                if found:
                    yield found
                break
        for k, token in enumerate(segment[1:], 1):  # sh -c '...', eval "..."
            if (segment[k - 1] in ("-c", "-Command", "/c") or segment[0] == "eval") and "git" in token:
                yield from hits(token)


try:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    command = (data.get("tool_input") or {}).get("command", "") or "" if data.get("tool_name") == "Bash" else ""
except Exception as exc:
    print(f"BLOCKED: guard_destructive_git.py could not read the hook input ({exc}), so it cannot "
          "tell whether this command loses work. Report this to the owner.", file=sys.stderr)
    sys.exit(2)

found = list(hits(command)) if "git" in command else []
for always, why, _ in found:
    if always:
        print(f"BLOCKED: {why}.\n\nThis is refused whatever the tree's state. If it is really "
              "needed, say so to the owner and ask them to run it themselves.", file=sys.stderr)
        sys.exit(2)

for _, why, dirs in found:
    try:
        dirty = git_out(dirs, "status", "--porcelain")
    except Exception:
        # If we cannot tell whether the tree is dirty, assume it is. Refusing a safe command
        # costs a sentence; allowing an unsafe one costs the work.
        dirty = "(could not read git status — assuming there is uncommitted work)"
    if not dirty:
        continue
    print(
        f"BLOCKED: {why}, and this tree has uncommitted changes:\n\n"
        f"{dirty}\n\n"
        "Uncommitted work is NOT in the reflog. If any of the above is not yours — a file the "
        "owner edited by hand, a note written this session — this command is the last moment it "
        "exists.\n\n"
        "Do one of these first, then re-run:\n"
        "  git stash push -u -m 'before <what you are about to do>'   # recoverable\n"
        "  git add -A && git commit -m 'wip'      # recoverable; the gate runs, never --no-verify\n\n"
        "If you have checked the list above and every entry is disposable, say so to the owner "
        "and ask them to run the command themselves.",
        file=sys.stderr,
    )
    sys.exit(2)
