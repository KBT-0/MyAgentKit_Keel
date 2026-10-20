#!/usr/bin/env python3
"""PreToolUse(Bash|PowerShell|Monitor): refuse a search or walk rooted at a filesystem or drive root.

An agent ran `find / -name x.h` in Git Bash on Windows: it passed the Bash tool's timeout, moved
to the background, outlived its session and kept a CPU core busy for seven hours, which skewed
every benchmark in that window (#298). A walk from a root is refused before it starts: `find`,
`fd`, `grep -r`, `rg`, `ag`, `ack`, `ls -R`, `du`, `tree`, `where /r`, cmd's `dir /s` and
PowerShell's `Get-ChildItem -Recurse` or `-Depth` (`gci`, `ls`, `dir`). A root is `/`, `/*`, a
drive (`C:`, `C:/`, `C:\\`, `\\`), Git Bash's `/c`, WSL's `/mnt/c` and Cygwin's `/cygdrive/c`. A
walk bounded to a small depth (`find / -maxdepth 3`, `rg --max-depth 3`, `tree -L 3`,
`gci -Depth 3`) passes; `du` sums the whole tree whatever its depth, so it never does. After a
`cd`, `pushd` or `Set-Location` to a root (until `popd`), `.` and a walk with no path count as
that root. Any other path passes, the project or a folder below a root included. Glob and Grep
are not guarded: they run inside the tool and never outlive the session.

The command is read as its shell reads it: a heredoc's body is data, an escaped newline joins two
lines, `#` starts a comment only at the start of a word, quotes and escapes are taken off (bash
`\\`, PowerShell `` ` ``, cmd `^`), and the text of `sh -c`, `bash -lc`, `powershell -Command`
and `cmd /c` is read too. Threat model: an agent's ACCIDENT; a path a variable holds passes.

This guard fails open: its settings entry has no `onFailure: block`, so a timeout or a crash lets
the call through (a stalled guard must not refuse every call), and unreadable input passes with
a note. No process is listed here: the hook must stay cheap. Exit 2 blocks the call and returns
the message to the agent (Claude Code hook protocol).
"""
import json
import re
import sys

MAX_DEPTH = 3  # ponytail: a fixed bound; the depth of C:/*/*/* stays in the seconds
ROOT = re.compile(r"|[A-Za-z]:|/[A-Za-z]|/mnt(?:/[A-Za-z])?|/cygdrive(?:/[A-Za-z])?")
ESCAPE = {"bash": "\\", "ps": "`", "cmd": "^"}
SEPARATORS = {"bash": ";&|()<>`\n", "ps": ";&|()<>\n", "cmd": "&|()<>\n"}
# A command that runs the rest of its words, with those of its options that take a value.
WRAPPERS = {"sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T"}, "doas": {"-u", "-C"},
            "nice": {"-n", "--adjustment"}, "ionice": {"-c", "-n", "--class", "--classdata"},
            "env": {"-u", "--unset", "-C", "--chdir"}, "stdbuf": {"-i", "-o", "-e"},
            "time": {"-f", "-o", "--format", "--output"}, "timeout": {"-s", "-k", "--signal", "--kill-after"},
            "nohup": set(), "command": set(), "exec": {"-a"}, "builtin": set(),
            "xargs": {"-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a", "--max-args", "--max-procs", "--delimiter",
                      "--arg-file", "--max-chars"}}
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!"}  # the command follows the keyword
SHELLS = {"sh", "bash", "dash", "zsh", "ksh"}
GCI = {"get-childitem", "gci", "dir", "ls"}
ADVICE = ("Search inside the project instead (`find . -name x`, `rg PATTERN src/`, a Glob or Grep "
          "call in the project), or bound the walk: `find / -maxdepth %d`, `rg --max-depth %d`, "
          "`tree -L %d`, `Get-ChildItem -Depth %d`." % ((MAX_DEPTH,) * 4))


def root(word, windows=False):
    """Whether WORD names a filesystem or drive root (a trailing /, /. or /* included; /mnt and
    /cygdrive hold every drive). PowerShell and cmd have no /c drive form: there `/c` is a switch
    or a folder."""
    w = word.replace("\\", "/")
    if not w or "/" not in w and ":" not in w:
        return False
    w = re.sub(r"(?:/[.*]*)+$", "", w)
    return bool(ROOT.fullmatch(w)) and not (windows and re.fullmatch(r"/[A-Za-z]", w))


def depth(args, names):
    """The depth an option in NAMES bounds the walk to (`-maxdepth 3`, `--max-depth=3`), or None."""
    for i, a in enumerate(args):
        key, eq, value = a.partition("=")
        if key.lower() in names:
            value = value if eq else (args[i + 1] if i + 1 < len(args) else "")
            if value.isdigit():
                return int(value)
    return None


def operands(args, takes_value, named=None):
    """The path operands of ARGS: options, and the value of each option TAKES_VALUE accepts, left
    out. For a searcher (NAMED given) the first operand is its pattern unless an option in NAMED
    named it or needs none (`-e`, `rg --files`)."""
    found, skip, given = [], False, False
    for i, a in enumerate(args):
        if skip:
            skip = False
        elif a == "--":
            found += args[i + 1:]
            break
        elif a.startswith("-") and len(a) > 1:
            given = given or named is not None and a.partition("=")[0] in named
            skip = takes_value(a)
        else:
            found.append(a)
    return found[1:] if named is not None and not given else found


GREP_VALUED = {"-e", "-f", "-A", "-B", "-C", "-m", "-d", "-D", "--regexp", "--file", "--include", "--exclude",
               "--exclude-dir", "--max-count", "--context", "--after-context", "--before-context", "--label"}
RG_VALUED = {"-e", "-f", "-g", "-t", "-T", "-A", "-B", "-C", "-m", "-d", "-j", "-M", "-E", "-r", "--regexp", "--file",
             "--glob", "--iglob", "--type", "--type-not", "--type-add", "--type-clear", "--max-depth", "--max-count",
             "--context", "--after-context", "--before-context", "--threads", "--replace", "--encoding", "--sort",
             "--sortr", "--max-filesize", "--ignore-file", "--color", "--colors", "--max-columns", "--pre",
             "--pre-glob", "--path-separator", "--context-separator", "--field-match-separator", "--engine"}
AG_VALUED = {"-A", "-B", "-C", "-m", "-g", "-G", "-p", "-W", "--after", "--before", "--context", "--max-count",
             "--depth", "--ignore", "--ignore-dir", "--path-to-ignore", "--pager", "--width", "--file-search-regex",
             "--type", "--match", "--ignore-file", "--type-add", "--type-set", "--output"}
FD_VALUED = {"-d", "-t", "-e", "-x", "-X", "-E", "-S", "-o", "-c", "-j", "--max-depth", "--min-depth", "--exact-depth",
             "--depth", "--type", "--extension", "--exec", "--exec-batch", "--exclude", "--size", "--changed-within",
             "--changed-before", "--owner", "--color", "--threads", "--max-results", "--base-directory",
             "--search-path", "--path-separator", "--ignore-file", "--batch-size", "--format"}
FD = (FD_VALUED, set(), {"-d", "--max-depth", "--depth", "--exact-depth"})
# name: (options that take a value, options after which no pattern operand comes, depth options)
SEARCHERS = {"rg": (RG_VALUED, {"-e", "-f", "--regexp", "--file", "--files", "--type-list"}, {"-d", "--max-depth"}),
             "ag": (AG_VALUED, {"-g"}, {"--depth"}), "ack": (AG_VALUED, {"-f", "-g", "--match"}, set()),
             "fd": FD, "fdfind": FD}
# Get-ChildItem's parameters that take a value (any unambiguous prefix works), its path left out.
GCI_VALUED = ("-fi", "-in", "-ex", "-de", "-at", "-er", "-ea", "-ev", "-wa", "-wv", "-iv", "-ou", "-ov", "-pi")


def walk(name, args, shell, cwd):
    """What NAME ARGS walks from a root, as `name root`, or None. A walk with no path walks the
    current folder: CWD, when a cd named a root."""
    windows, bound = shell != "bash", None
    if name == "find":
        # Paths come before the first expression word; -H, -L, -P, -D LIST, -O3 and -- before them.
        i = 0
        while i < len(args) and (args[i] in ("-H", "-L", "-P", "-D", "--") or re.fullmatch(r"-O\d*", args[i])):
            i += 2 if args[i] == "-D" else 1
        paths = []
        for a in args[i:]:
            if a.startswith(("-", "(", "!")):
                break
            paths.append(a)
        bound, label = depth(args, {"-maxdepth"}), "find"
    elif name in SEARCHERS:
        valued, named, depths = SEARCHERS[name]
        paths, bound, label = operands(args, valued.__contains__, named), depth(args, depths), name
    elif name in ("grep", "egrep", "fgrep"):
        if not any(a in ("--recursive", "--dereference-recursive") or re.fullmatch(r"-[A-Za-z]*[rR][A-Za-z]*", a)
                   for a in args) and not re.search(r"(?:^| )(?:-d|--directories)[ =]?recurse(?: |$)", " ".join(args)):
            return None
        paths, label = operands(args, GREP_VALUED.__contains__, {"-e", "-f", "--regexp", "--file"}), name + " -r"
    elif name == "tree":
        paths = operands(args, {"-L", "-P", "-I", "-o", "--filelimit", "--charset"}.__contains__)
        bound, label = depth(args, {"-l"}), "tree"
    elif name == "du":
        paths = operands(args, {"-d", "-B", "--exclude", "--max-depth", "--block-size", "--time-style"}.__contains__)
        label = "du"
    elif name == "where":
        if not any(a.lower() == "/r" for a in args):
            return None
        paths, label = [a for a in args if a.lower() != "/r"], "where /r"
    elif shell == "cmd" and name == "dir":
        if not any(a.startswith("/") and "s" in a.lower().split("/") for a in args):  # /s, /s/b
            return None
        # `dir C:\x.h /s` looks for x.h in C:\ and every folder below it.
        paths = [re.sub(r"(?<=[\\/:])[^\\/:]*[*?.][^\\/:]*$", "", a) for a in args if not a.startswith("/")]
        label = "dir /s"
    elif name in GCI and (windows or name in ("get-childitem", "gci")):
        # PowerShell takes any unambiguous prefix of a parameter (-r, -Rec) and -s for -Recurse;
        # -Depth recurses on its own.
        bound = depth(args, {"-de", "-dep", "-dept", "-depth"})
        if bound is None and not any(re.fullmatch(r"-(?:r(?:e(?:c(?:u(?:r(?:se?)?)?)?)?)?|s)(?::\$true)?", a, re.I)
                                     for a in args):
            return None
        paths = operands(args, lambda a: a.lower().startswith(GCI_VALUED))
        label = "Get-ChildItem -Recurse"
    elif name in ("ls", "dir"):
        if not any(a == "--recursive" or re.fullmatch(r"-[A-Za-z]*R[A-Za-z]*", a) for a in args):
            return None
        paths, label = operands(args, set().__contains__), "ls -R"
    else:
        return None
    paths = [cwd if cwd and p in (".", "./", ".\\") else p for p in paths] or [cwd or ""]
    hit = next((p for p in paths if root(p, windows)), None)
    return hit and (bound is None or bound > MAX_DEPTH) and label + " " + hit


def commands(text, shell):
    """The simple commands of TEXT as word lists, read as SHELL reads them: quotes and escapes
    taken off, an escaped newline joined, `#` at the start of a word a comment to the end of its
    line (not in cmd), and a heredoc's body skipped (bash: it is data). A `$(...)` or a bash
    backtick inside double quotes runs: its text is read as commands too (ponytail: a `)` quoted
    inside it ends it early)."""
    esc, seps, quotes = ESCAPE[shell], SEPARATORS[shell], '"' if shell == "cmd" else "'\""
    text = text.replace("\r\n", "\n")
    found, command, word, heredocs, delimiter, subs = [], [], None, [], False, []
    i = 0
    while i <= len(text):
        c = text[i] if i < len(text) else "\n"
        if c == esc and i < len(text):  # a trailing escape is dropped
            if text[i + 1:i + 2] not in ("", "\n"):
                word = (word or "") + text[i + 1]
            i += 2 if i + 1 < len(text) else 1
            continue
        if c in quotes:
            j, part = i + 1, ""
            while j < len(text) and text[j] != c:
                if c == '"' and shell != "cmd" and text[j] == esc and j + 1 < len(text) \
                        and (shell == "ps" or text[j + 1] in '"\\$`\n'):
                    part += text[j + 1].strip("\n")
                    j += 2
                    continue
                if c == '"' and shell != "cmd" and (text.startswith("$(", j) or shell == "bash" and text[j] == "`"):
                    start = j + (2 if text[j] == "$" else 1)
                    if text[j] == "$":
                        k, level = start, 1
                        while level and k < len(text):
                            level += {"(": 1, ")": -1}.get(text[k], 0)
                            k += 1
                    else:
                        k = text.find("`", start) + 1 or len(text)
                    subs.append(text[start:k - 1])
                    part, j = part + text[j:k], k
                    continue
                part += text[j]
                j += 1
            word, i = (word or "") + part, j + 1
            continue
        if c == "#" and word is None and shell != "cmd":
            i = text.find("\n", i)
            i = len(text) if i < 0 else i
            continue
        if word is None and (c in seps or c in "{}") or c in seps or c in " \t":
            if word is not None:
                if delimiter:
                    heredocs.append(word)
                else:
                    command.append(word)
                word, delimiter = None, False
            if c in " \t":
                i += 1
                continue
            if command:
                found.append(command)
            command = []
            if shell == "bash" and text.startswith("<<", i):  # <<<: a here-string, no body
                delimiter = not text.startswith("<<<", i)
                i += 3 if text.startswith(("<<<", "<<-"), i) else 2
                continue
            i += 1
            if c == "\n":
                delimiter = False
                for end in heredocs:  # skip the body, up to the line that is its delimiter
                    while i < len(text):
                        j = text.find("\n", i)
                        j = len(text) if j < 0 else j
                        line, i = text[i:j], j + 1
                        if line.strip() == end:
                            break
                heredocs = []
            continue
        word = (word or "") + c
        i += 1
    return found + [argv for sub in subs for argv in commands(sub, shell)]


def unwrap(argv):
    """ARGV without the variable assignments and wrappers (`sudo -u x`, `nice -n 19`,
    `timeout 60`) in front of the command they run."""
    while argv:
        name = argv[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
        if re.match(r"\w+=", argv[0]):
            argv = argv[1:]
            continue
        if name in KEYWORDS:
            argv = argv[1:]
            continue
        if name not in WRAPPERS:
            return argv
        argv = argv[1:]
        while argv and argv[0].startswith("-"):
            argv = argv[2:] if argv[0] in WRAPPERS[name] else argv[1:]
        if name == "timeout":  # timeout [OPTION]... DURATION COMMAND
            argv = argv[1:]
    return argv


def scan(text, shell, cwd=None):
    """The first rooted walk in TEXT, as a short description, or None. CWD is the root a `cd`,
    `pushd` or `Set-Location` named (ponytail: no other folder change is followed)."""
    windows, stack = shell != "bash", []
    for argv in commands(text, shell):
        argv = unwrap(argv)
        if not argv:
            continue
        name = re.sub(r"\.exe$", "", argv[0].replace("\\", "/").rsplit("/", 1)[-1].lower())
        args = argv[1:]
        if name in ("cd", "chdir", "pushd", "set-location", "sl", "push-location"):
            if name in ("pushd", "push-location"):
                stack.append(cwd)
            options = ("-", "/") if shell == "cmd" else ("-",)  # cmd: cd /d C:\
            target = next((a for a in args if not a.startswith(options)), "")
            cwd = target if root(target, windows) else None
            continue
        if name in ("popd", "pop-location"):
            cwd = stack.pop() if stack else None
            continue
        found = None
        if name in SHELLS:
            at = next((k for k, a in enumerate(args) if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a)), None)
            inner = None if at is None else next((a for a in args[at + 1:] if not a.startswith("-")), None)
            found = inner and scan(inner, "bash", cwd)
        elif name in ("powershell", "pwsh"):
            at = next((k for k, a in enumerate(args) if a.lower() in ("-c", "-command")), None)
            found = at is not None and scan(" ".join(args[at + 1:]), "ps", cwd)
        elif name == "cmd":
            at = next((k for k, a in enumerate(args) if a.lower() in ("/c", "/k", "//c", "//k")), None)
            found = at is not None and scan(" ".join(args[at + 1:]), "cmd", cwd)
        else:
            found = walk(name, args, shell, cwd)
        if found:
            return found
    return None


try:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    call = data.get("tool_input") or {}
except Exception as exc:  # fails open
    print("guard_root_scan.py could not read the hook input (%s); the call goes on. Report this to the "
          "owner." % exc, file=sys.stderr)
    sys.exit(1)
if isinstance(call, dict) and isinstance(call.get("command"), str):
    found = scan(call["command"], "ps" if data.get("tool_name") == "PowerShell" else "bash")
    if found:
        print("BLOCKED: `%s` is refused: it walks a whole filesystem or drive: on a big disk it passes the "
              "tool's timeout, moves to the background and can keep a CPU core busy for hours after the "
              "session ends (#298). %s" % (found, ADVICE), file=sys.stderr)
        sys.exit(2)
