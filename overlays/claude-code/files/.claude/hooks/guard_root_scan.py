#!/usr/bin/env python3
"""PreToolUse(Bash|PowerShell|Monitor|Glob|Grep): refuse a search or walk rooted at a filesystem or drive root.

An agent ran `find / -name x.h` in Git Bash on Windows: it passed the Bash tool's timeout, moved
to the background, outlived its session and kept a CPU core busy for seven hours, which skewed
every benchmark in that window (#298). A walk from a root is refused before it starts: `find`,
`fd`, `grep -r`, `rg`, `ag`, `ack`, `ls -R`, `du`, `tree`, `where /r`, PowerShell's
`Get-ChildItem -Recurse` (`gci`, `ls`, `dir`), and a Glob or Grep tool call whose path (or
Glob's absolute pattern) is a root. A root is `/`, `/*`, a drive (`C:`, `C:/`, `C:\\`, `\\`),
Git Bash's `/c`, WSL's `/mnt/c` and Cygwin's `/cygdrive/c`. A walk bounded to a small depth
(`find / -maxdepth 3`, `rg --max-depth 3`, `tree -L 3`, `gci -Depth 3`) passes; `du` sums the
whole tree whatever its depth, so it never does. After a `cd` to a root, `.` and a find with no
path count as that root. Any other path passes, the project or a folder below a root included.

Threat model: an agent's ACCIDENT; the hook reads the words it can split (shell text inside
`sh -c`, `bash -c` and `powershell -Command` too) and lets anything else through, a path a
variable holds included. No process is listed here: the hook must stay cheap.

Exit 2 blocks the call and returns the message to the agent (Claude Code hook protocol).
"""
import json
import os
import re
import shlex
import sys

MAX_DEPTH = 3  # ponytail: a fixed bound; the depth of C:/*/*/* stays in the seconds
ROOT = re.compile(r"|[A-Za-z]:|/[A-Za-z]|/mnt/[A-Za-z]|/cygdrive/[A-Za-z]")
WRAPPERS = {"sudo", "nohup", "time", "nice", "command", "exec", "builtin", "env", "stdbuf", "ionice"}
SHELLS = {"sh", "bash", "dash", "zsh", "ksh"}
GCI = {"get-childitem", "gci", "dir", "ls"}
ADVICE = ("Search inside the project instead (`find . -name x`, `rg PATTERN src/`, a Glob or Grep "
          "path in the project), or bound the walk: `find / -maxdepth %d`, `rg --max-depth %d`, "
          "`tree -L %d`, `Get-ChildItem -Depth %d`." % ((MAX_DEPTH,) * 4))


def block(message):
    print("BLOCKED: " + message, file=sys.stderr)
    sys.exit(2)


def root(word, powershell=False):
    """Whether WORD names a filesystem or drive root (a trailing / or /* included). PowerShell has
    no /c drive form: there `/c` is a switch or a folder."""
    w = word.strip("'\"").replace("\\", "/")
    if not w or "/" not in w and ":" not in w:
        return False
    w = re.sub(r"(?:/\**)+$", "", w)
    return bool(ROOT.fullmatch(w)) and not (powershell and re.fullmatch(r"/[A-Za-z]", w))


def depth(args, names):
    """The depth an option in NAMES bounds the walk to (`-maxdepth 3`, `--max-depth=3`), or None."""
    for i, a in enumerate(args):
        key, eq, value = a.partition("=")
        if key.lower() in names:
            value = value if eq else (args[i + 1] if i + 1 < len(args) else "")
            if value.isdigit():
                return int(value)
    return None


def operands(args, valued, pattern_first):
    """The path operands of ARGS: options and the values of those in VALUED left out, and, for a
    searcher (PATTERN_FIRST), its first operand unless -e or -f named the pattern."""
    found, skip, given = [], False, False
    for i, a in enumerate(args):
        if skip:
            skip = False
        elif a == "--":
            found += args[i + 1:]
            break
        elif a.startswith("-") and len(a) > 1:
            given = given or a in ("-e", "-f", "--regexp", "--file") or a.startswith(("--regexp=", "--file="))
            skip = a in valued
        else:
            found.append(a)
    return found[1:] if pattern_first and not given else found


GREP_VALUED = {"-e", "-f", "-A", "-B", "-C", "-m", "-d", "-D", "--regexp", "--file", "--include", "--exclude",
               "--exclude-dir", "--max-count", "--context", "--after-context", "--before-context", "--label"}
RG_VALUED = {"-e", "-f", "-g", "-t", "-T", "-A", "-B", "-C", "-m", "-d", "-j", "-M", "-E", "-r", "--glob", "--iglob",
             "--type", "--type-not", "--max-depth", "--max-count", "--context", "--threads", "--replace",
             "--encoding", "--sort", "--sortr", "--max-filesize", "--ignore-file", "--exclude", "--extension",
             "--depth", "--exact-depth", "-x", "-X", "--exec", "--exec-batch", "-S", "--size", "--changed-within",
             "--changed-before", "-o", "--owner", "--color", "--max-results", "--base-directory"}


def walk(name, args, powershell):
    """What NAME ARGS walks from a root, as `name root`, or None."""
    def first(paths):
        return next((p for p in paths if root(p, powershell)), None)
    if name == "find":
        # Paths come before the first expression word; -H/-L/-P and -D/-O come before them.
        paths = []
        for a in args:
            if a.startswith(("-", "(", "!")):
                if paths or a not in ("-H", "-L", "-P"):
                    break
                continue
            paths.append(a)
        hit = first(paths)
        return hit and (depth(args, {"-maxdepth"}) or 99) > MAX_DEPTH and "find " + hit
    if name in ("fd", "fdfind", "rg", "ag", "ack"):
        hit = first(operands(args, RG_VALUED, True))
        return hit and (depth(args, {"-d", "--max-depth", "--depth", "--exact-depth"}) or 99) > MAX_DEPTH \
            and name + " " + hit
    if name in ("grep", "egrep", "fgrep"):
        recursive = any(a in ("--recursive", "--dereference-recursive", "--directories=recurse")
                        or re.fullmatch(r"-[A-Za-z]*[rR][A-Za-z]*", a) for a in args)
        hit = recursive and first(operands(args, GREP_VALUED, True))
        return hit and name + " -r " + hit
    if name == "tree":
        hit = first(operands(args, {"-L", "-P", "-I", "-o", "--filelimit", "--charset"}, False))
        return hit and (depth(args, {"-l"}) or 99) > MAX_DEPTH and "tree " + hit
    if name == "du":
        hit = first(operands(args, {"-d", "-B", "--exclude", "--max-depth", "--block-size", "--time-style"}, False))
        return hit and "du " + hit
    if name == "where":
        hit = any(a.lower() == "/r" for a in args) and first(a for a in args if a.lower() != "/r")
        return hit and "where /r " + hit
    if name in GCI and (powershell or name != "ls"):
        # PowerShell takes any unambiguous prefix of a parameter: -r, -rec, -Recurse.
        recurse = any(re.fullmatch(r"-r(?:e(?:c(?:u(?:r(?:s(?:e)?)?)?)?)?)?(?::\$true)?", a, re.I) for a in args)
        hit = recurse and first(a for a in args if not a.startswith("-"))
        return hit and (depth(args, {"-depth"}) or 99) > MAX_DEPTH and "Get-ChildItem -Recurse " + hit
    if name == "ls":
        recursive = any(a == "--recursive" or re.fullmatch(r"-[A-Za-z]*R[A-Za-z]*", a) for a in args)
        hit = recursive and first(operands(args, set(), False))
        return hit and "ls -R " + hit
    return None


def words(text):
    """Simple commands of TEXT as word lists; quotes taken off, backslashes kept (Windows paths)."""
    lex = shlex.shlex(text.replace("\n", ";"), posix=True, punctuation_chars=True)
    lex.whitespace_split, lex.escape = True, ""
    try:
        tokens = list(lex)
    except ValueError:  # an unclosed quote: read the words as they stand
        tokens = text.split()
    command = []
    for token in tokens:
        if token and set(token) <= set("();<>|&"):
            if command:
                yield command
            command = []
        else:
            command.append(token.lstrip("`$").rstrip("`"))
    if command:
        yield command


def scan(text, powershell):
    """The first rooted walk in TEXT, as a short description, or None. After a `cd` to a root, `.`
    and a find with no path count as that root (ponytail: no other relative path is followed)."""
    at_root = None
    for argv in words(text):
        while argv and (re.match(r"\w+=", argv[0]) or os.path.basename(argv[0]).lower() in WRAPPERS):
            argv = argv[1:]
        if argv and argv[0].lower() == "timeout":  # timeout [OPTION]... DURATION COMMAND
            argv = argv[1:]
            while argv and argv[0].startswith("-"):
                argv = argv[2:] if argv[0] in ("-s", "-k", "--signal", "--kill-after") else argv[1:]
            argv = argv[1:]
        if not argv:
            continue
        name = re.sub(r"\.exe$", "", os.path.basename(argv[0].replace("\\", "/")).lower())
        args = argv[1:]
        if name in ("cd", "pushd", "chdir", "set-location", "sl"):
            target = next((a for a in args if not a.startswith("-")), "")
            at_root = target if root(target, powershell) else None
            continue
        if at_root:
            args = [at_root if a in (".", "./") else a for a in args]
            if name == "find" and not any(a and not a.startswith(("-", "(", "!")) for a in args[:1]):
                args = [at_root] + args
        if name in SHELLS and "-c" in args[:-1]:
            found = scan(args[args.index("-c") + 1], False)
        elif name in ("powershell", "pwsh") and any(a.lower() in ("-c", "-command") for a in args[:-1]):
            at = next(i for i, a in enumerate(args) if a.lower() in ("-c", "-command"))
            found = scan(" ".join(args[at + 1:]), True)
        else:
            found = walk(name, args, powershell)
        if found:
            return found
    return None


try:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    tool = data.get("tool_name") or ""
    call = data.get("tool_input") or {}
except Exception as exc:
    block(f"guard_root_scan.py could not read the hook input ({exc}). Report this to the owner.")
why = ("it walks a whole filesystem or drive: on a big disk it passes the tool's timeout, moves to "
       "the background and can keep a CPU core busy for hours after the session ends (#298). ")
if tool in ("Glob", "Grep"):
    path = call.get("path") if isinstance(call.get("path"), str) else ""
    pattern = call.get("pattern") if tool == "Glob" and isinstance(call.get("pattern"), str) else ""
    start = re.split(r"[*?\[{]", pattern, 1)[0]  # an absolute Glob pattern walks from its fixed part
    hit = path if root(path) else pattern if start != pattern and root(start) else None
    if hit:
        block("this %s call searches from a root (%s); %s%s" % (tool, hit, why, ADVICE))
elif isinstance(call.get("command"), str):
    found = scan(call["command"], tool == "PowerShell")
    if found:
        block("`%s` is refused: %s%s" % (found, why, ADVICE))
