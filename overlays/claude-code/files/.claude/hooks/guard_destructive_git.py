#!/usr/bin/env python3
"""PreToolUse(Bash): refuse a git command that loses work, or one that skips the gate.

Threat model: an agent's ACCIDENT, not an adversary; Claude Code's permissions and sandbox are
the boundary. What the hook can parse it reads as the shell and git would; what it cannot parse
it refuses. Two kinds of command are refused (the loss-certain subset; AGENTS.md's rule "commit
or stash before any command that discards work" still covers every destructive command):

- Always, whatever the tree's state: `git stash drop/clear` (the stash may be the only copy),
  a force push (`--force`, `-f`, `+refspec`, `:ref`, `--mirror`, `--delete`, and a
  `--force-with-lease` without `=ref:expected` or a final `--force-if-includes`),
  `git remote set-url/add` (it moves where a push goes), `git commit --amend` of a commit a
  remote branch already holds, and a skipped gate: `--no-verify`, `commit -n`, `--no-gpg-sign`,
  `-c`/`--config-env` core.hooksPath, writing core.hooksPath with `git config`, and a
  `GIT_CONFIG_*`, `HUSKY*`, `SKIP` or `PRE_COMMIT*` variable on a command that runs hooks. The
  gate's hatch is the owner's, typed in the owner's own terminal; this hook sees only an agent's
  Bash calls.
- While the target tree has uncommitted work: `git reset --hard`, `git checkout` of paths or
  with `-f`, `git switch -f`, `git restore` (unless index-only: `--staged` without
  `--worktree`), `git clean` (unless `-n`/`--dry-run`; with `-x`/`-X` ignored files count) and
  an alias the hook cannot read. Uncommitted changes are not in the reflog: once they are gone,
  they are gone. The tree checked is the one the command reaches (`cd X &&`, `git -C`,
  `--git-dir`, `--work-tree`, `GIT_DIR=`, `GIT_WORK_TREE=`), and the caller's folder is always
  checked too: a `cd` only adds a folder. A command after one that changes the tree (anything
  but `cd`, `echo`, a read-only git command ...) is judged dirty.

The floor runs first: the base implementation's patterns (`git reset ... --hard`, `checkout --`,
`checkout -f`, `restore` without `--staged`, `clean -f/-d/-x` without `-n`, `stash drop/clear`,
`push --force`/`-f`) anywhere in the raw text, quoted strings and here-document bodies included,
refused while the caller's tree is dirty. The parser below only adds refusals to it. The cost,
accepted: a command that only mentions such a pattern is refused while the tree is dirty.

Read as git reads it: option values (`clean -e -n` excludes "-n"), `--` ends the options, the
last of `--x`/`--no-x` wins, a unique abbreviation (`--no-veri`) counts, an alias is resolved,
`GIT.EXE` is git on Windows. Refused as unreadable when it carries a git word: backticks, `$(...)`,
`eval`, `sh -c`-style command strings, a shell reading a here-string or pipe, a here-document on
a line where any shell appears (`cat <<EOF | sh`), a backslash-newline, `sudo`/`xargs`-style
wrappers, and an unbalanced quote. Any other here-document is dropped before parsing, so a
commit message may mention git.
Sources: the vendor's default auto-mode block list
(https://code.claude.com/docs/en/permission-modes), Bash rule limits
(https://code.claude.com/docs/en/permissions), git-push, git-clean, git-restore, git-config,
githooks (https://git-scm.com/docs), anthropics/claude-code#40117 (an agent committed with
--no-verify despite a written rule). Settings run this hook with `onFailure: block`; a payload
it cannot read also blocks, because any exit but 2 lets the call through
(https://code.claude.com/docs/en/hooks).
ponytail: the option tables below cover the subcommands this hook judges; an option missing
from a table is read as a flag without a value. Add it there when one shows.

Exit 2 blocks the call and returns the message to the agent (Claude Code hook protocol).
"""
import json
import os
import re
import shlex
import subprocess
import sys

GIT_WORD = re.compile(r"(?<![\w.\\/-])(?:[\w.:\\/-]*[\\/])?git(?:\.exe)?(?![\w.-])", re.I)
SEPARATORS = set(";&|\n()")
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "pwsh", "powershell", "cmd", ".", "source"}
# The floor: the base implementation's patterns, matched on the raw text (quoted strings and
# here-document bodies included) and refused while the caller's tree is dirty. It runs first and
# the parser below only adds refusals. restore --staged and clean -n pass (they lose nothing).
FLOOR = [(re.compile(p, re.I), why) for p, why in [
    (r"\bgit(\.exe)?\s+reset\b[^|;&]*--hard", "git reset --hard discards every uncommitted change"),
    (r"\bgit(\.exe)?\s+checkout\b[^|;&]*\s--\s", "git checkout -- <path> overwrites the working copy"),
    (r"\bgit(\.exe)?\s+checkout\s+-f\b", "git checkout -f overwrites the working copy"),
    (r"\bgit(\.exe)?\s+restore\b(?![^|;&]*(--staged|\s-S\b))", "git restore overwrites the working copy"),
    (r"\bgit(\.exe)?\s+clean\b(?![^|;&]*(\s-[a-zA-Z]*n|--dry-run))[^|;&]*(\s-[a-zA-Z]*[fdxX]|--force)",
     "git clean deletes untracked files"),
    (r"\bgit(\.exe)?\s+stash\s+(drop|clear)\b", "git stash drop/clear deletes stashed work"),
    (r"\bgit(\.exe)?\s+push\b[^|;&]*(--force(?![\w-])|\s-f\b)", "a force push can discard remote commits"),
]]
OPAQUE = {"sudo", "xargs", "timeout", "nice", "watch", "stdbuf", "doas", "parallel", "find"}
TRANSPARENT = {"command", "exec", "builtin", "nohup", "env"}
KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until", "time"}
CALM = {"cd", "pushd", "echo", "printf", "pwd", "ls", "cat", "true", ":", "test", "[", "export"}
READ_ONLY = {"status", "log", "diff", "show", "fetch", "rev-parse", "ls-files", "describe", "blame",
             "grep", "help", "version", "reflog", "shortlog", "remote", "config", "branch", "tag"}
HOOK_SUBS = {"commit", "merge", "push", "rebase", "am", "pull", "cherry-pick", "revert"}
HOOK_ENV = re.compile(r"GIT_CONFIG|HUSKY|SKIP$|PRE_COMMIT", re.I)
GATE = ("this skips a git hook (the commit gate) or commit signing. Fix the failure. "
        "Only the owner bypasses this gate")

# Per subcommand: long options (a value-taking one ends in "="), and short letter -> long name.
SPEC = {
    "commit": ("all patch reuse-message= reedit-message= fixup= squash= reset-author short branch porcelain "
               "long null file= author= date= message= template= signoff no-signoff trailer= no-verify verify "
               "allow-empty allow-empty-message cleanup= edit no-edit amend no-post-rewrite include only "
               "pathspec-from-file= pathspec-file-nul untracked-files verbose quiet dry-run status no-status "
               "gpg-sign no-gpg-sign",
               dict(a="all", p="patch", C="reuse-message=", c="reedit-message=", s="signoff", F="file=",
                    m="message=", t="template=", n="no-verify", e="edit", i="include", o="only",
                    u="untracked-files", v="verbose", q="quiet", S="gpg-sign", z="null")),
    "merge": ("commit no-commit edit no-edit ff no-ff ff-only log no-log signoff no-signoff stat no-stat "
              "squash no-squash verify no-verify strategy= strategy-option= verify-signatures "
              "no-verify-signatures summary no-summary quiet verbose progress no-progress autostash "
              "no-autostash allow-unrelated-histories message= file= into-name= rerere-autoupdate "
              "no-rerere-autoupdate overwrite-ignore no-overwrite-ignore abort quit continue cleanup= "
              "gpg-sign no-gpg-sign",
              dict(e="edit", n="no-stat", s="strategy=", X="strategy-option=", q="quiet", v="verbose",
                   m="message=", F="file=", S="gpg-sign")),
    "pull": ("verify no-verify gpg-sign no-gpg-sign strategy= strategy-option= rebase no-rebase "
             "commit no-commit edit no-edit ff no-ff ff-only squash no-squash autostash no-autostash "
             "all append upload-pack= force tags no-tags depth= quiet verbose",
             dict(s="strategy=", X="strategy-option=", q="quiet", v="verbose", r="rebase", f="force",
                  S="gpg-sign")),
    "rebase": ("onto= keep-base continue skip abort quit edit-todo show-current-patch apply merge "
               "strategy= strategy-option= exec= interactive verify no-verify gpg-sign no-gpg-sign "
               "autosquash no-autosquash autostash no-autostash root update-refs no-update-refs "
               "quiet verbose signoff force-rebase no-ff",
               dict(s="strategy=", X="strategy-option=", x="exec=", i="interactive", q="quiet",
                    v="verbose", f="force-rebase", S="gpg-sign")),
    "am": ("signoff keep keep-non-patch keep-cr no-keep-cr scissors no-scissors quiet utf8 no-utf8 "
           "3way no-3way rerere-autoupdate ignore-space-change ignore-whitespace directory= exclude= "
           "include= reject patch-format= interactive verify no-verify committer-date-is-author-date "
           "ignore-date skip gpg-sign no-gpg-sign continue resolved resolvemsg= abort quit "
           "show-current-patch empty=",
           dict(s="signoff", k="keep", q="quiet", u="utf8", i="interactive", n="no-verify", r="resolved",
                S="gpg-sign")),
    "cherry-pick": ("edit no-edit cleanup= mainline= no-commit signoff strategy= strategy-option= "
                    "rerere-autoupdate allow-empty keep-redundant-commits empty= continue skip quit abort "
                    "ff gpg-sign no-gpg-sign",
                    dict(e="edit", m="mainline=", n="no-commit", s="signoff", X="strategy-option=",
                         x="x", S="gpg-sign")),
    "push": ("all branches mirror prune tags follow-tags no-follow-tags dry-run porcelain delete "
             "atomic no-atomic signed= no-signed push-option= receive-pack= exec= repo= force no-force "
             "force-with-lease no-force-with-lease force-if-includes no-force-if-includes "
             "recurse-submodules= no-recurse-submodules set-upstream thin no-thin quiet verbose progress "
             "no-progress verify no-verify ipv4 ipv6",
             dict(n="dry-run", d="delete", f="force", o="push-option=", u="set-upstream", q="quiet",
                  v="verbose")),
    "clean": ("dry-run force interactive quiet exclude=",
              dict(n="dry-run", f="force", i="interactive", q="quiet", e="exclude=", d="d", x="x", X="X")),
    "restore": ("source= staged worktree patch quiet progress no-progress ours theirs merge conflict= "
                "ignore-unmerged ignore-skip-worktree-bits recurse-submodules no-recurse-submodules "
                "overlay no-overlay pathspec-from-file= pathspec-file-nul",
                dict(s="source=", S="staged", W="worktree", p="patch", q="quiet", m="merge")),
    "checkout": ("quiet progress no-progress force ours theirs track no-track guess no-guess detach "
                 "orphan= ignore-skip-worktree-bits merge conflict= patch ignore-other-worktrees "
                 "overwrite-ignore no-overwrite-ignore recurse-submodules no-recurse-submodules overlay "
                 "no-overlay pathspec-from-file= pathspec-file-nul",
                 dict(q="quiet", f="force", b="b=", B="B=", t="track", l="l", m="merge", p="patch")),
    "switch": ("create= force-create= detach guess no-guess force discard-changes merge conflict= "
               "quiet progress no-progress track no-track orphan= ignore-other-worktrees "
               "recurse-submodules no-recurse-submodules",
               dict(c="create=", C="force-create=", d="detach", f="force", m="merge", q="quiet", t="track")),
    "reset": ("soft mixed hard merge keep quiet no-quiet refresh no-refresh recurse-submodules "
              "no-recurse-submodules pathspec-from-file= pathspec-file-nul intent-to-add",
              dict(q="quiet", N="intent-to-add", p="patch")),
}
SPEC["revert"] = SPEC["cherry-pick"]  # the same options
GIT_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix"}


class Unreadable(Exception):
    pass


def base(token):
    name = re.split(r"[\\/]", token)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def strip_heredocs(text):
    """The text without here-document bodies. A body that holds git is unreadable when any command
    on the line is a shell: it may read the body (`cat <<EOF | sh`, `tee x.sh <<EOF; . x.sh`)."""
    while True:
        m = re.search(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([\w.-]+)\2", text)
        if not m:
            return text
        start = text.find("\n", m.end())
        if start < 0:
            return text[:m.start()] + text[m.end():]
        end = start + 1
        lines = text[start + 1:].split("\n")
        for line in lines:
            end += len(line) + 1
            if (line.lstrip("\t") if m.group(1) else line) == m.group(3):
                break
        body, outside = text[start:end], text[:start] + "\n" + text[end:]
        commands = [(piece.split() or [""])[0] for piece in re.split(r"[;&|()\n]", outside)]
        if GIT_WORD.search(body) and any(base(w.strip("'\"")) in SHELLS for w in commands):
            raise Unreadable("a here-document a shell on the same line may read")
        text = text[:m.start()] + text[m.end():start] + "\n" + text[end:]


def substitutions(text):
    """The text inside each backtick pair and each $( ), <( ), >( )."""
    found = re.findall(r"`([^`]*)`", text)
    for m in re.finditer(r"[$<>]\(", text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
        found.append(text[m.end():i])
    return found


def segments(text):
    """Simple commands of a command line, each a token list."""
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|\n()<>")
    lexer.whitespace, lexer.whitespace_split = " \t\r", True
    try:
        tokens = list(lexer)
    except ValueError:
        if GIT_WORD.search(text):
            raise Unreadable("an unbalanced quote")
        return
    segment = []
    for token in tokens + [";"]:
        if token and set(token) <= SEPARATORS:
            if segment:
                yield segment
            segment = []
        else:
            segment.append(token)


def resolve(name, names):
    """The long option `name` means, by exact name or unique prefix; a list if ambiguous."""
    if name in names:
        return name
    found = [n for n in names if n.startswith(name)]
    return found[0] if len(found) == 1 else found or name


def options(sub, args):
    """(options in order as (name, value), positionals) for a subcommand, as git parses them."""
    spec = SPEC.get(sub)
    longs = {n.rstrip("="): n.endswith("=") for n in (spec[0].split() if spec else [])}
    shorts = spec[1] if spec else {}
    opts, words, i = [], [], 0
    while i < len(args):
        arg = args[i]
        i += 1
        if arg == "--":
            words += args[i:]
            break
        if arg.startswith("--"):
            name, eq, value = arg[2:].partition("=")
            found = resolve(name, longs)
            for n in (found if isinstance(found, list) else [found]):  # ambiguous: git refuses; so do we
                if longs.get(n) and not eq and i < len(args):
                    value, i = args[i], i + 1
                opts.append((n, value if eq or longs.get(n) else None))
        elif arg.startswith("-") and arg != "-":
            for k, ch in enumerate(arg[1:], 1):
                name = shorts.get(ch, ch)
                if name.endswith("="):
                    value = arg[k + 1:]
                    if not value and i < len(args):
                        value, i = args[i], i + 1
                    opts.append((name[:-1], value))
                    break
                opts.append((name, None))
        else:
            words.append(arg)
    return opts, words


def last(opts, on, off, default=False):
    state = default
    for name, _ in opts:
        state = True if name == on else False if name == off else state
    return state


class Git:
    """One git invocation and how to ask git about the repository it reaches."""

    def __init__(self, tokens, env, cwds):
        self.env, self.cwds, self.route, self.configs, i = env, cwds, [], [], 0
        self.cwd = next((c for c in reversed(cwds) if c), None)  # where questions other than status go
        while i < len(tokens) and tokens[i].startswith("-"):
            tok, nxt = tokens[i], tokens[i + 1] if i + 1 < len(tokens) else ""
            takes = tok in GIT_VALUE
            if tok in ("-C", "--git-dir", "--work-tree"):
                self.route += [tok, nxt]
            elif tok.startswith(("--git-dir=", "--work-tree=")):
                self.route.append(tok)
            elif tok == "-c" or tok == "--config-env":
                self.configs.append(nxt)
            elif tok.startswith("--config-env="):
                self.configs.append(tok.split("=", 1)[1])
            elif tok.startswith("-c"):
                self.configs.append(tok[2:])
            i += 2 if takes else 1
        self.sub, self.args = (tokens[i:i + 1] or [""])[0], tokens[i + 1:]

    def ask(self, *args, where=None):
        """git's answer as (exit code, stdout); an OSError or a timeout raises."""
        command = ["git", *self.route, *[x for c in self.configs for x in ("-c", c)], *args]
        run = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                             cwd=where or self.cwd, env=dict(os.environ, **self.env))
        return run.returncode, run.stdout.strip()

    def dirty(self, ignored=False):
        """What uncommitted work any folder the command may stand in holds ("" for none)."""
        for where in self.cwds:
            if where is None:
                return "(the command changes to a folder the hook cannot name — assuming uncommitted work)"
            try:
                code, out = self.ask("status", "--porcelain", *(["--ignored"] if ignored else []), where=where)
            except Exception:
                code, out = 1, ""
            # If we cannot tell whether the tree is dirty, assume it is. Refusing a safe command
            # costs a sentence; allowing an unsafe one costs the work.
            if code != 0:
                return "(could not read git status — assuming there is uncommitted work)"
            if out:
                return out
        return ""


def verdict(g, depth=0):
    """None, or (always, why, ignored_counts) for one git invocation."""
    sub, args = g.sub, g.args
    if any(c.split("=", 1)[0].lower() == "core.hookspath" for c in g.configs):
        return True, GATE, False
    if sub in HOOK_SUBS and any(HOOK_ENV.match(k) for k in g.env):
        return True, "a GIT_CONFIG_*, HUSKY, SKIP or PRE_COMMIT variable on this command can switch the gate off", False
    if sub == "config" and any(a.lower() == "core.hookspath" for a in args):
        reads = {"--get", "--get-all", "--get-regexp", "get", "-l", "--list", "list"}
        writes = {"--unset", "--unset-all", "unset", "set", "--add", "--replace-all", "--edit", "-e"}
        key_last = args[-1].lower() == "core.hookspath"
        if not (set(args) & reads) and (set(args) & writes or not key_last):
            return True, "setting core.hooksPath moves the commit gate. " + GATE, False
        return None
    opts, words = options(sub, args)
    names = {n for n, _ in opts}
    first = (words or [""])[0]
    if sub in HOOK_SUBS and (not last(opts, "verify", "no-verify", True)
                             or last(opts, "no-gpg-sign", "gpg-sign")):
        return True, GATE, False
    if sub == "stash" and first in ("drop", "clear"):
        return True, "git stash drop/clear deletes stashed work, which may be its only copy", False
    if sub == "remote" and first in ("set-url", "add"):
        return True, "git remote set-url/add changes where a push goes", False
    if sub == "push":
        lease = None
        for name, value in opts:
            lease = (value or "") if name == "force-with-lease" else None if name == "no-force-with-lease" else lease
        lease_ok = lease is None or ":" in lease or last(opts, "force-if-includes", "no-force-if-includes")
        if (last(opts, "force", "no-force") or names & {"mirror", "delete"} or not lease_ok
                or any(w.startswith(("+", ":")) for w in words[1:])):
            return True, "a force push or a remote delete can discard commits on the remote", False
    if sub == "commit" and "amend" in names:
        try:
            code, out = g.ask("branch", "-r", "--contains", "HEAD")
        except Exception:
            code = 1
        if code != 0 or out:  # cannot tell: refuse, as below
            return True, "git commit --amend rewrites a commit a remote branch already holds", False
    if sub == "reset" and last(opts, "hard", "soft") and "hard" in names:
        if [n for n, _ in opts if n in ("hard", "soft", "mixed", "merge", "keep")][-1] == "hard":
            return False, "git reset --hard discards every uncommitted change", False
    if sub == "checkout" and not names & {"b", "B", "orphan", "patch"}:
        if "force" in names or "--" in args or len(words) != 1:
            if "force" in names or words:
                return False, "git checkout of a path, or -f, overwrites the working copy", False
        else:
            try:
                code, _ = g.ask("rev-parse", "--verify", "--quiet", first + "^{commit}")
            except Exception:
                code = 1
            if code != 0:
                return False, "git checkout of a path overwrites the working copy", False
    if sub == "switch" and names & {"force", "discard-changes"}:
        return False, "git switch -f discards uncommitted changes", False
    if sub == "restore" and ("worktree" in names or "staged" not in names):
        return False, "git restore overwrites the working copy", False
    if sub == "clean" and not names & {"dry-run", "interactive"}:
        return False, "git clean deletes untracked files", bool(names & {"x", "X"})
    if sub and sub not in SPEC and sub not in READ_ONLY and sub not in ("stash", "add", "init", "clone"):
        try:
            code, alias = g.ask("config", "--get", "alias." + sub)
        except Exception:
            code, alias = 2, ""
        if code == 1:
            return None  # not an alias: a command of git's own or a git-<name> program
        if code == 0 and not alias.startswith("!") and depth < 5:
            try:
                g.sub, *rest = shlex.split(alias)
            except ValueError:
                return False, f"git {sub} is an alias the hook cannot read", False
            g.args = rest + args
            return verdict(g, depth + 1)
        return False, f"git {sub} is an alias the hook cannot read", False
    return None


def judge(command, cwd):
    """(always, why, git) findings; raises Unreadable."""
    if (re.search(r"\\\r?\n", command) or "<<<" in command) and GIT_WORD.search(command):
        raise Unreadable("a backslash-newline or a here-string")
    text = strip_heredocs(command)
    if any(GIT_WORD.search(s) for s in substitutions(text)):
        raise Unreadable("a command substitution (backticks or $(...))")
    # Every folder the command may stand in. The caller's folder is always one: a `cd` may not run
    # (after `||`), may run in a subshell (`( )`, a pipeline, `&`), so it only adds a folder.
    env, changed, cwds = {}, False, [cwd]
    for seg in segments(text):
        local, i = {}, 0
        while i < len(seg):
            if seg[i] in KEYWORDS:
                i += 1
            elif re.match(r"[A-Za-z_]\w*=", seg[i]):
                k, v = seg[i].split("=", 1)
                local[k] = v
                i += 1
            elif base(seg[i]) in TRANSPARENT:
                i += 1
                while i < len(seg) and seg[i].startswith("-"):
                    i += 1
            else:
                break
        rest = seg[i:]
        name = base(rest[0]) if rest else ""
        has_git = any(base(t) == "git" for t in rest[1:])
        if name == "eval" and any(GIT_WORD.search(t) for t in rest):
            raise Unreadable("eval")
        if name in SHELLS and any(GIT_WORD.search(t) for t in text.split()):
            if any(re.fullmatch(r"-\w*c\w*|/c|-command", t, re.I) for t in rest[1:]):
                raise Unreadable(f"a command string run by {name} -c")
            if not [t for t in rest[1:] if not t.startswith("-")]:
                raise Unreadable(f"{name} reading commands from its input")
        if name in OPAQUE and has_git:
            raise Unreadable(f"git run through {name}")
        if rest and rest[0].startswith("$") and any(t in SPEC or t in ("stash", "remote", "config") for t in rest[1:]):
            raise Unreadable("a command named by a variable")
        if name == "export":
            env.update(dict(t.split("=", 1) for t in rest[1:] if "=" in t))
        if name in ("cd", "pushd"):
            target = os.path.expanduser(os.path.expandvars(rest[1])) if len(rest) > 1 else None
            moved = [None if target is None or "$" in target or target == "-" or c is None else os.path.join(c, target)
                     for c in cwds]
            cwds = list(dict.fromkeys(cwds + moved))
            continue
        if name == "git":
            g = Git(rest[1:], {**env, **local}, cwds)
            found = verdict(g)
            if found:
                yield found[0], found[1], (g, found[2], changed)
            changed = changed or g.sub not in READ_ONLY
        elif name not in CALM:
            changed = True


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        command = (data.get("tool_input") or {}).get("command", "") or "" if data.get("tool_name") == "Bash" else ""
    except Exception as exc:
        return f"guard_destructive_git.py could not read the hook input ({exc}), so it cannot tell whether this command loses work. Report this to the owner"
    if not re.search("git", command, re.I):
        return None
    floor = next((why for pattern, why in FLOOR if pattern.search(command)), None)
    if floor:  # the base rule, first and never cleared by the parser below
        dirty = Git([], {}, [os.getcwd()]).dirty()
        if dirty:
            return lost(floor, dirty)
    try:
        found = list(judge(command, os.getcwd()))
    except Unreadable as exc:
        return (f"this command holds git inside {exc}, which this hook cannot read, so it cannot tell "
                "whether the command loses work; run the git command directly, as its own command")
    for always, why, _ in found:
        if always:
            return (f"{why}.\n\nThis is refused whatever the tree's state. If it is really needed, say so "
                    "to the owner and ask them to run it themselves")
    for _, why, (g, ignored, changed) in found:
        dirty = ("(an earlier command in this line changes the tree — judged as uncommitted work)"
                 if changed else g.dirty(ignored))
        if dirty:
            return lost(why, dirty)
    return None


def lost(why, dirty):
    return (f"{why}, and this tree has uncommitted changes:\n\n{dirty}\n\n"
            "Uncommitted work is NOT in the reflog. If any of the above is not yours — a file the "
            "owner edited by hand, a note written this session — this command is the last moment it "
            "exists.\n\n"
            "Do one of these first, then re-run:\n"
            "  git stash push -u -m 'before <what you are about to do>'   # recoverable\n"
            "  git add -A && git commit -m 'wip'      # recoverable; the gate runs, never --no-verify\n\n"
            "If you have checked the list above and every entry is disposable, say so to the owner "
            "and ask them to run the command themselves")


refusal = main()
if refusal:
    print("BLOCKED: " + refusal + ".", file=sys.stderr)
    sys.exit(2)
