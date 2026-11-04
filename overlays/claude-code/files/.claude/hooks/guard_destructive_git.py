#!/usr/bin/env python3
"""PreToolUse(Bash|PowerShell|Monitor): refuse a git command that loses work, or one that skips the gate.

Every tool that runs a command is judged: the settings matcher names them all (one list there),
and the hook reads `tool_input.command` whatever the tool's name. A PowerShell command is read
after two translations (no backslash escape in PowerShell, `$env:NAME = v` sets a variable for
the commands after it); a backtick (PowerShell's escape and line continuation) beside a git word
is refused as unreadable.

Threat model: an agent's ACCIDENT, not an adversary; Claude Code's permissions and sandbox are
the boundary. What the hook can parse it reads as the shell and git would; what it cannot parse
it refuses. Two kinds of command are refused (the loss-certain subset; AGENTS.md's rule "commit
or stash before any command that discards work" still covers every destructive command):

- Always, whatever the tree's state: `git stash drop/clear` (the stash may be the only copy; dropping an entry whose every file HEAD holds as stashed passes),
  a force push (`--force`, `-f`, `+refspec`, `:ref`, `--mirror`, `--delete`, and a
  `--force-with-lease` without `=ref:expected` or a final `--force-if-includes`),
  `git remote set-url/add` (it moves where a push goes), `git commit --amend` of a commit a
  remote branch already holds, and a skipped gate: `--no-verify`, `commit -n`, `--no-gpg-sign`,
  `-c`/`--config-env` core.hooksPath, writing core.hooksPath away from `.githooks`, and a
  `GIT_CONFIG_*`, `HUSKY*`, `SKIP` or `PRE_COMMIT*` variable on a command that runs hooks. The
  gate's hatch is the owner's, typed in the owner's own terminal; this hook sees only an agent's
  tool calls. Also always: a ref delete or forced move (`branch -D/-f/-M/-C`, `tag -d/-f`,
  `update-ref`, `remote remove`) when the ref holds commits no other ref under refs/ reaches
  (HEAD does not count: it may point at that very ref), in every repository the command may
  reach, `reflog expire/delete`, `gc --prune=<time>` (or `-c gc.pruneExpire`/`gc.reflogExpire*`)
  and `prune`, and `worktree remove --force` while the worktree it names holds uncommitted or
  untracked work. The guard fails closed on what it cannot read: a subcommand, ref, remote,
  worktree or folder named by a `$var`, a `$(...)`, an operand xargs appends, a `{}`, an
  interpolated part of a code string (`{b}`, `#{b}`, `%s`) or a PowerShell splat (`git @a`) is the
  worst case (a variable refspec on push is not: a force push's `+`/`:` is typed by hand).
- While the target tree has uncommitted work: `git reset --hard`, `git checkout` of paths
  (only those paths are asked, the ones a `--pathspec-from-file` lists included; its stdin or an
  unreadable file asks the whole tree; an ignored file counts only where the checkout's revision
  holds its path) or with `-f`, `git switch -f`, `git restore` (unless index-only: `--staged` without
  `--worktree`), `git clean` (unless `-n`/`--dry-run`; with `-x`/`-X` ignored files count) and
  an alias the hook cannot read. Uncommitted changes are not in the reflog: once they are gone,
  they are gone. The tree checked is the one the command reaches (`cd X &&`, `git -C`,
  `--git-dir`, `--work-tree`, `GIT_DIR=`, `GIT_WORK_TREE=`), and the caller's folder is always
  checked too: a `cd` only adds a folder. A `sh -c` string (also behind a wrapper: `timeout`,
  `xargs`) is judged with its own `cd`s; code that names a folder (`cwd=`, `chdir`, a `cd`) adds
  one the hook cannot name, judged dirty. A command after one that changes the tree (anything
  but `cd`, `echo`, a read-only git command ...) is judged dirty. `git rm -f` (not `--cached`),
  `mv -f`, `checkout-index -f` and `read-tree -u --reset` are judged the same way, and so is a
  command named by a substitution or a variable (`$(which git) reset --hard`, backticks), first or behind a
  wrapper (`timeout 60 $(which git) ...`): the words after it are read as git's. The cost, accepted: a non-git
  program so named whose words spell a git verb (`$(which make) clean`) is refused on a dirty tree.

The floor runs first: the base implementation's patterns (`git reset ... --hard`, `checkout --`,
`checkout -f`, `restore` without `--staged`, `clean -f/-d/-x` without `-n`, `stash drop/clear`,
`push --force`/`-f`) anywhere in the raw text, quoted strings and here-document bodies included,
refused while the caller's tree is dirty. The parser below only adds refusals to it. The cost,
accepted: a command that only mentions such a pattern is refused while the tree is dirty.

Read as git reads it: option values (`clean -e -n` excludes "-n"), `--` ends the options, the
last of `--x`/`--no-x` wins, a unique abbreviation (`--no-veri`) counts, an alias is resolved,
`GIT.EXE` is git on Windows. A `#` comment ends at its line. Shell text inside shell text is parsed
as shell: backticks, `$(...)`, `eval`, `sh -c` strings, a here-document a shell on its line may read
(these with every folder and variable the line reaches), a `!` alias and `submodule foreach`
(in folders it does not name, so judged dirty). Text the hook cannot
parse as shell (any interpreter argument or here-document: python*, node, deno, bun, perl, ruby,
php, PowerShell ...; the part of a here-document only a shell elsewhere on its line may run that
follows a quote it never closes, such as prose with an apostrophe; any argument of another program: a wrapper such as sudo or xargs may run it,
data such as a gh title never does) has each `git ...` in it judged as the command it would be,
so a mention of a safe command passes and a loss-certain one is refused (#77); a quoted `'git'`
starts an argv list read to its closing bracket, across lines, a bare item being a variable. Refused as
unreadable when it carries a git word: shell or interpreter input piped from a command that holds
git (not awk running a literal program that starts no command), a backslash-newline, a `<<<`
here-string outside quotes and comments (anywhere in a line with `$(...)`/backticks or in an
interpreter's here-document), env/exec options, a command named by a variable, and an unbalanced
quote. Other here-documents are dropped before parsing, so a commit message may mention git; a
quoted or commented `<<` is not one. Shell redirections are removed before reading git arguments; quoted/escaped
operators remain arguments. `git config core.hooksPath .githooks` wires the project's own gate
when `.githooks` stays inside the tree of every folder the command may stand in, through its own
`cd`, `-C`, `--git-dir` and `GIT_DIR` routes (doctor's printed fix passes as printed).
Sources: the vendor's default auto-mode block list
(https://code.claude.com/docs/en/permission-modes), Bash rule limits
(https://code.claude.com/docs/en/permissions), git-push, git-clean, git-restore, git-config,
githooks (https://git-scm.com/docs), anthropics/claude-code#40117 (an agent committed with
--no-verify despite a written rule). Settings run this hook with `onFailure: block`; a payload
it cannot read also blocks, because any exit but 2 lets the call through
(https://code.claude.com/docs/en/hooks).
ponytail: the option tables below cover the subcommands this hook judges; an option missing
from a table is read as a flag without a value. Add it there when one shows. Git assembled in
code from parts (`"refs/heads/" + name`, a variable holding the subcommand), the folders
`find -execdir` visits and `rm -rf` of a worktree are not seen.

Exit 2 blocks the call and returns the message to the agent (Claude Code hook protocol).
"""
import itertools
import json
import os
import re
import shlex
import subprocess
import sys

# A `git/` is a folder (awk's `/git/`, `.git/`), never the command (#327).
GIT_WORD = re.compile(r"(?<![\w.\\/-])(?:[\w.:\\/-]*[\\/])?git(?:\.exe)?(?![\w.\\/-])", re.I)
SEPARATORS = set(";&|\n()")
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "pwsh", "powershell", "cmd", ".", "source"}
# The floor: the base implementation's patterns, matched on the raw text (quoted strings and
# here-document bodies included) and refused while the caller's tree is dirty. It runs first and
# the parser below only adds refusals. restore --staged and clean -n pass (they lose nothing).
FLOOR = [(re.compile(p, re.I), why) for p, why in [
    (r"\bgit(\.exe)?\s+reset\b[^|;&]*--hard", "git reset --hard discards every uncommitted change"),
    (r"\bgit(\.exe)?\s+checkout\b[^|;&]*\s--\s", "git checkout -- <path> overwrites the working copy"),
    (r"\bgit(\.exe)?\s+checkout\s+-f\b", "git checkout -f overwrites the working copy"),
    # restore passes only index-only: --staged/-S present AND --worktree/-W absent.
    (r"\bgit(\.exe)?\s+restore\b(?!(?=[^|;&]*(--staged|(?-i:\s-[a-zA-Z]*S)))(?![^|;&]*(--worktree|(?-i:\s-[a-zA-Z]*W))))",
     "git restore overwrites the working copy"),
    # clean passes on a dry run, but not on an -n that -e/--exclude takes as its pattern
    # (`-e -n`, `--exclude -n`, the cluster `-fen`).
    (r"\bgit(\.exe)?\s+clean\b(?![^|;&]*(?<=\S)(?<!\s-e)(?<!--exclude)\s+(?-i:-[a-df-zA-Z]*n|--dry-run))"
     r"[^|;&]*(\s-[a-zA-Z]*[fdxX]|--force)", "git clean deletes untracked files"),
    (r"\bgit(\.exe)?\s+stash\s+(drop|clear)\b", "git stash drop/clear deletes stashed work"),
    (r"\bgit(\.exe)?\s+push\b[^|;&]*(--force(?![\w-])|\s-f\b)", "a force push can discard remote commits"),
]]
PLAIN_GIT = {"status", "log", "diff", "show", "commit", "tag", "add", "checkout", "rev-parse", "ls-files"}
TRANSPARENT = {"command", "exec", "builtin", "nohup", "env"}
# A variable git or a tool runs as a command (GIT_EDITOR, GIT_EXTERNAL_DIFF, GIT_SSH_COMMAND, ...): its value is shell
# text, judged as such (review r327 High: `GIT_EDITOR='git reset --hard #' git commit` ran the reset). Only the ones
# git(1) ENVIRONMENT gives a command or config: GIT_AUTHOR_NAME="O'Brien git" is a name, not shell text with an
# unbalanced quote (leeway v0.14.1 sync review).
COMMAND_VAR = re.compile(r"GIT_(?:SSH|SSH_COMMAND|PROXY_COMMAND|EDITOR|SEQUENCE_EDITOR|PAGER|EXTERNAL_DIFF|CONFIG\w*)"
                         r"|EDITOR|VISUAL|PAGER|\w*ASKPASS")
# Names and dates only: a plain line keeps its blanked floor with these (any other GIT_* may carry a command or config).
NAME_VAR = re.compile(r"GIT_(?:AUTHOR|COMMITTER)_(?:NAME|EMAIL|DATE)")
KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until", "time"}
CALM = {"cd", "pushd", "echo", "printf", "pwd", "ls", "cat", "true", ":", "test", "[", "export"}
# #327: commands that run none of the text they are given (sort is not: --compress-program). Their
# arguments are data, and on a line of these and PLAIN_GIT alone the floor reads the line with quotes,
# comments and here-document bodies blanked, so a message that names a hard reset is no reset.
INERT = CALM | {"grep", "egrep", "fgrep", "head", "tail", "wc", "uniq", "cut", "tr"}
# Programs whose quoted arguments are prose (a title, a body) and that run no text of this line: a git word
# inside such an argument is no git for commit_folders (the cb35ca5 review). An allowlist: any other command
# that names git may be a wrapper or an interpreter the hook cannot look through.
TEXT_ARGS = {"gh", "glab"}
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
# Every long option (git 2.47 `-h`), so a unique abbreviation (`--del`, `--forc`) resolves and a
# value is never read as the ref a ref command moves.
SPEC["branch"] = ("verbose quiet track no-track set-upstream-to= unset-upstream color no-color remotes "
                  "contains= no-contains= abbrev no-abbrev all delete move omit-empty copy list show-current "
                  "create-reflog edit-description force merged= no-merged= column no-column sort= points-at= "
                  "ignore-case recurse-submodules format=", dict(u="set-upstream-to="))
SPEC["tag"] = ("list delete verify annotate message= file= trailer= edit sign cleanup= local-user= force "
               "create-reflog column no-column contains= no-contains= merged= no-merged= omit-empty sort= "
               "points-at= format= color ignore-case", dict(m="message=", F="file=", u="local-user="))
SPEC["update-ref"] = ("", dict(m="m="))
GIT_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix"}
# An operand the shell or a wrapper fills in at run time: xargs appends one, find/xargs -I put one
# at `{}`, a `$var` or `$(...)` holds one. The hook cannot know it, so a ref or folder named by
# one is judged as the worst case (the guard fails closed on what it cannot read).
UNKNOWN = "{}"
# One item of an interpreter's argv list: a quoted string is one word, a bare name is a variable.
ARGV = re.compile(r'"((?:\\.|[^"\\])*)"|\'((?:\\.|[^\'\\])*)\'|([^\s,\[\]{}()"\']+)')
# Code that names a folder for the git it runs (`cwd=`, `chdir`, a `cd` in a shell string): the
# hook does not resolve it, so that git may stand in a folder the hook cannot name.
MOVES = re.compile(r"\bcwd\b|chdir|\b(?:cd|pushd|popd|sl)\b|set-location|push-location", re.I)
# A string's interpolated part (`{b}`, `{0}`, Ruby `#{b}`, `%s`, `%(b)s`), not git's `@{u}`/`^{tree}`.
INTERPOLATED = re.compile(r"(?<![@^])\{[^{}]*\}|%(?:\(\w+\))?[-#0 +\d.]*[sdr]")
SPLAT = False  # set for PowerShell input, where `git @a` splats an array the hook cannot read
LINE = ""  # the whole command line, for a file a path option reads (--pathspec-from-file)


def splat(word):
    return SPLAT and re.match(r"@(?:\w|$)", word) is not None


def unknowable(word):
    return "$" in word or UNKNOWN in word or "`" in word or splat(word)


def native(path):
    """A folder as Windows reads it. Git Bash spells a drive `/d/x`; Windows Python and git.exe read
    that as `\\d\\x` on the current drive, so `cd /d/repo && git merge-base ...` asked git in a
    folder that does not exist and was refused as unreadable. PowerShell (SPLAT) has no such form."""
    found = re.fullmatch(r"/([A-Za-z])(/.*)?", path) if os.name == "nt" and not SPLAT else None
    return found.group(1) + ":" + (found.group(2) or "/") if found else path


class Unreadable(Exception):
    pass


def base(token):
    name = re.split(r"[\\/]", token)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def interpreter(name):
    # The runtime's flags do not define a safe boundary: any argument can carry code.
    unversioned = re.sub(r"\d+(?:\.\d+)*$", "", name)
    return name.startswith("python") or unversioned in {
        "node", "nodejs", "deno", "bun", "perl", "ruby", "php", "pwsh", "powershell",
        "osascript", "lua", "luajit", "julia", "r", "rscript", "tclsh", "wish",
        "awk", "gawk", "mawk", "js", "qjs",
    }


# What the shell reads as quoted or as a comment: an escape, an ANSI-C `$'...'`, a quoted string,
# a `#` where a word starts.
QUOTED = re.compile(r"""\\.|\$'(?:\\.|[^'\\])*'|'[^']*'|"(?:\\.|[^"\\])*"|(?:^|(?<=[\s;&|()]))#[^\n]*""", re.S)


def unquoted(text):
    """text with its quoted strings and comments blanked (the same length), so a `<<`/`<<<` left in
    it is a shell operator; None when a `$(...)` or backtick may nest quotes this scan cannot follow."""
    if "$(" in text or "`" in text:
        return None
    return QUOTED.sub(lambda m: " " * len(m.group()), text)


def unquote(word):
    try:
        return "".join(shlex.split(word))
    except ValueError:
        return None


def plain_awk(args, text):
    """awk running a literal program that starts and loads no command (no system, pipe, getline
    from a command, @include/@load, -f/-e file), so what is piped into it is data."""
    i = 0
    while i < len(args) and args[i].startswith("-") and args[i] != "--":
        if args[i] in ("-F", "-v"):
            i += 1
        elif not re.fullmatch(r"-[Fv].+", args[i]):
            return False
        i += 1
    i += i < len(args) and args[i] == "--"
    program = args[i] if i < len(args) else ""
    # Every raw word that reads as the program is single-quoted (or nothing expands): a decoy
    # `'...'` elsewhere cannot vouch for a double-quoted program built from variables.
    raw = [w for w in re.findall(WORD, text) if unquote(w) == program]
    literal = not re.search(r"[$`\\]", program) or bool(raw) and all(w == f"'{program}'" for w in raw)
    return bool(program) and literal and not re.search(r"system|[|@]", program)


def strip_heredocs(text):
    """(the text without here-document bodies, [(read_by_a_shell, body)]). A body that holds git
    is listed by its receiving command/pipeline first: a shell's is judged as shell, an
    interpreter's (`cat <<EOF | python`) as loose text. Any other is judged as shell when a
    command elsewhere is a shell (it may run the file the body writes), up to a quote that never
    closes. A quoted or commented `<<` is an argument, not a here-document. Every body is cut
    first, so one body's apostrophes never read as a quote while another's readers are found. The part after
    that never-closing quote is listed with None (falsy, judged as an interpreter's is), as no reader runs it."""
    cut, pos, marker, expanded = [], 0, "__guard_heredoc_input__", []
    while True:
        m = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([\w.-]+)\2").search(text, pos)
        if not m:
            break
        blank = unquoted(text)
        if blank is not None and blank[m.start()] != "<":
            pos = m.end()
            continue
        start = text.find("\n", m.end())
        if start < 0:
            text = text[:m.start()] + text[m.end():]
            break
        end = start + 1
        lines = text[start + 1:].split("\n")
        for line in lines:
            end += len(line) + 1
            if (line.lstrip("\t") if m.group(1) else line).removesuffix("\r") == m.group(3):
                break
        line = text.rfind("\n", 0, m.start()) + 1
        if not m.group(2):
            # An unquoted delimiter: the shell runs the body's $( ) and backticks before any reader sees it
            # (review r327 High: `cat <<E` over `$(git reset --hard)` ran the reset). Judged as shell.
            expanded += [(True, inner) for inner in substitutions(text[start:end]) if GIT_WORD.search(inner)]
        cut.append((text[line:m.start()] + " " + marker + " " + text[m.end():start], text[start:end]))
        text = text[:m.start()] + text[m.end():start] + "\n" + text[end:]
    cut = [(header, body) for header, body in cut if GIT_WORD.search(body)]
    # Include readers behind wrappers, but ordinary prose (`echo python`) is not a reader.
    # A substitution's own commands too: the lexer reads each unquoted $( ) as one word, so `x=$(bash run.sh)`
    # hid its shell (syncfind r2 High).
    commands = [w for t in [text, *substitutions(text)] for seg in segments(t)
                if base(seg[0]) not in CALM | {"git"} for w in seg] if cut else []
    shell_reads = any(base(w) in SHELLS and not interpreter(base(w)) for w in commands)
    bodies = []
    for header, body in cut:
        try:
            headers = list(segments(header, with_endings=True, strict=True))
        except Unreadable:
            # A heredoc in "$(...)" has an outer quote that closes AFTER its body.
            # Parse the substitution's command, not the incomplete enclosing argument.
            inside = substitutions(header)
            if not inside:
                raise
            headers = list(segments(inside[-1], with_endings=True, strict=True))
        receiving = False
        for seg, ending in headers:
            receiving = receiving or marker in seg
            if receiving and base(seg[0]) not in CALM | {"git"}:
                if any(base(w) in SHELLS and not interpreter(base(w)) for w in seg):
                    bodies.append((True, body))  # its own reader is a shell: judged (and refused) as shell
                    break
                if any(interpreter(base(w)) for w in seg):
                    bodies.append((False, body))
                    break
            receiving = receiving and ending in {"|", "|&"}
        else:
            if shell_reads:
                # A shell elsewhere on the line may run the file this body writes. A shell runs it up to
                # a quote it never closes (prose: `the worker's`), so that part is judged as shell; the
                # rest never runs, and each git in it is judged as code is. A nested body's apostrophe
                # is its data, not an open quote: the nested bodies are cut and judged by their readers.
                body, nested = strip_heredocs(body)
                start = next((m.start() for m in UNCLOSED.finditer(body) if m.group("open")), None)
                bodies.append((True, body[:start]))
                if start is not None:
                    bodies.append((None, body[start:]))  # data no reader runs: falsy, judged as code is
                bodies.extend(nested)
    return text, bodies + expanded


UNCLOSED = re.compile(QUOTED.pattern + r"""|(?P<open>['"])""", re.S)


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


# One raw shell word, its quotes kept.
WORD = r'''(?:[^\s;&|()<>'"\\]+|\\.|'[^']*'|"(?:\\.|[^"\\])*")+'''


def blank_substitutions(text):
    """text with each unquoted `$( )` and backtick pair made one unknown word: the lexer split `git -C $(pwd) reset
    --hard` at the parentheses and read `reset --hard` as a command named reset, so a dirty tree's reset passed
    (syncfind), and split `` `which git` reset `` into `` `which `` and `` git` `` (whichgit). Its inner text is still
    judged, by substitutions(); a `$(` or backtick that never closes is left as it was."""
    out, i, quote = [], 0, ""
    while i < len(text):
        if text[i] == "\\" and quote != "'":
            out.append(text[i:i + 2])
            i += 2
            continue
        if quote:
            quote = "" if text[i] == quote else quote
        elif text[i] in "'\"":
            quote = text[i]
        elif text[i] == "`" and text.find("`", i + 1) > 0:
            j = text.find("`", i + 1)
            out.append('"$(pwd)"' if text[i + 1:j].strip() == "pwd" else UNKNOWN)
            i = j + 1
            continue
        elif text.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            if not depth:
                # `$(pwd)` stays a word into() and commit_folders resolve, as its quoted form (syncfind r2 Medium)
                out.append('"$(pwd)"' if text[i + 2:j - 1].strip() == "pwd" else UNKNOWN)
                i = j
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def shell_tokens(text, strict=False):
    """Shell words and separators, with redirections removed before quote information is lost."""
    text = blank_substitutions(text)
    # Consume complete raw shell words so quoted/escaped >, < and descriptor numbers survive.
    # Strip a redirection together with its target before shlex discards quote information or
    # splits `2>&1` at `&`. A separate `2 >out` leaves 2 as an argument, as the shell does.
    redirect = r'(?:\d+)?(?:&>>?|>>|>&|>\||>|<>|<<|<&|<)'
    # A `#` starts a comment only where a word starts (`page#top` is one word), and the comment ends
    # before its newline, which stays a separator (shlex's own comments ate it, joining two lines).
    text = re.sub(r'(?P<comment>#[^\n]*)|(?P<redirect>' + redirect + r'[ \t]*' + WORD + r')|' + WORD,
                  lambda m: ' ' if m.group('redirect') or m.group('comment') else m.group(), text)
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|\n()<>")
    lexer.whitespace, lexer.whitespace_split, lexer.commenters = " \t\r", True, ""
    try:
        tokens = list(lexer)
    except ValueError:
        if strict or GIT_WORD.search(text):
            raise Unreadable("an unbalanced quote")
        return []
    return tokens


def segments(text, with_endings=False, strict=False):
    """Simple commands, optionally paired with their following shell separator."""
    segment = []
    for token in shell_tokens(text, strict) + [";"]:
        if token and set(token) <= SEPARATORS:
            if segment:
                yield (segment, token) if with_endings else segment
            segment = []
        else:
            segment.append(token)


def loose(text, cwds, changed=False, env=None, appended=False):
    """Findings for the git words in text the hook cannot parse as shell: code an interpreter runs,
    or another program's arguments. Each `git ...` up to the line's end or a shell operator is
    judged as the command it would be, quotes, brackets and commas read as word breaks. A quoted
    git word starts an argv list (`['git', 'push', '--mirror']`, one item per line or not): its
    items up to the closing bracket, a bare item (a variable) unknown. `appended`: the wrapper
    (xargs) adds operands the hook cannot see. An interpolated part of a string is an unknown
    operand, and code that names a folder adds one the hook cannot name."""
    if MOVES.search(text):
        cwds = [*cwds, None]
    for m in GIT_WORD.finditer(text):
        quote, after = text[m.start() - 1:m.start()], text[m.end():m.end() + 1]
        # #327: code and data name git in prose: a label ('GIT', "Git"), or a git that ends a string it
        # did not start (grep 'class git' "$f"). An all-caps GIT only: a case-insensitive file system runs
        # ['Git', ...] (review r327 Low). shortcut: an argv ['GIT', ...] passes; none was seen.
        if (re.search(r"GIT$", m.group())
                or after in ("'", '"') and quote != after):
            continue
        if quote in ("'", '"') and text[m.end():m.end() + 1] == quote:
            items = re.split(r"[\])]", text[m.end() + 1:], maxsplit=1)[0]
            words = [next((w for w in x.groups()[:2] if w is not None), UNKNOWN) for x in ARGV.finditer(items)]
        else:
            tail = INTERPOLATED.sub(UNKNOWN, re.split(r"[;&|\n]", text[m.end():], maxsplit=1)[0])
            words = re.sub(r"[\"'`,\[\]()]|\{(?!\})|(?<!\{)\}", " ", tail).split()
        yield from findings(Git(words + [UNKNOWN] * appended, dict(env or {}), cwds), changed)


def findings(g, changed, aliases=True):
    """The verdict on one git invocation as judge's findings. A shell alias or `submodule foreach`
    has its shell text judged where it runs."""
    found = verdict(g, aliases=aliases)
    if found and found[0] == "shell":
        _, text, cwds, fallback = found
        inner = list(judge(text, cwds, changed, g.env))
        yield from inner
        found = None if inner or not fallback else (False, fallback, False)
    if found:
        yield found[0], found[1], (g, found[2], changed)


def unreached(g, refs, where):
    """Whether deleting or moving `refs` loses commits in the repository at `where`: one is
    reachable from them and from no other ref under refs/ (HEAD and other worktrees' HEADs are
    left out: they may point at the very ref). None in refs or where, or a git error, = cannot
    tell = True. A ref that does not exist loses nothing."""
    if where is None or None in refs:
        return True
    try:
        alive = []
        for ref in refs:
            code, full = g.ask("rev-parse", "--verify", "--quiet", "--symbolic-full-name", ref, where=where)
            if code not in (0, 1):
                return True
            alive += [full or ref] * (code == 0)  # HEAD reads as the branch it points at
        if not alive:
            return False
        code, out = g.ask("rev-list", "-n1", *alive, "--not", *("--exclude=" + r for r in alive),
                          "--glob=refs/*", where=where)
        return code != 0 or bool(out)
    except Exception:
        return True


def moved_refs(g, sub, names, words, where):
    """The refs a branch, tag, update-ref or remote call deletes or overwrites (None: unknown)."""
    force = bool(names & {"f", "force"})
    refs = []
    if sub == "branch":
        prefix = "refs/remotes/" if names & {"r", "remotes"} else "refs/heads/"
        if "D" in names or (names & {"d", "delete"} and force):
            refs = [prefix + w for w in words]
        elif names & {"M", "C"} or (names & {"m", "move", "c", "copy"} and force):
            refs = [prefix + words[-1]] if words else []
        else:
            refs = [prefix + words[0]] if force and words else []
    elif sub == "tag":
        if names & {"d", "delete"}:
            refs = ["refs/tags/" + w for w in words]
        else:
            refs = ["refs/tags/" + words[0]] if force and words else []
    elif sub == "update-ref":
        refs = words[:1]
    elif sub == "remote" and words[:1] in (["remove"], ["rm"]) and len(words) > 1:
        if unknowable(words[1]):
            return [None]
        try:
            code, out = g.ask("for-each-ref", "--format=%(refname)", f"refs/remotes/{words[1]}/", where=where)
        except Exception:
            code = 1
        return out.split() if code == 0 else [None]
    return [None if unknowable(r) else r for r in refs]


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
        self.paths = []  # set by a path checkout: only these paths' changes are lost (#327)
        self.tree = None  # a path checkout's revision: an ignored file is lost only where it holds the path
        self.options = []  # the global options, their separate values skipped (r327 r2: `-C . --icase-pathspecs`)
        self.dirs = []  # the -C values, in order: where commits() says the commit stands
        self.cwd = next((c for c in reversed(cwds) if c), None)  # where questions other than status go
        while i < len(tokens) and tokens[i].startswith("-"):
            tok, nxt = tokens[i], tokens[i + 1] if i + 1 < len(tokens) else ""
            takes = tok in GIT_VALUE
            self.options.append(tok)
            if tok in ("-C", "--git-dir", "--work-tree"):
                self.route += [tok, native(nxt)]
                self.dirs += [nxt] if tok == "-C" else []
            elif tok.startswith(("--git-dir=", "--work-tree=")):
                key, value = tok.split("=", 1)
                self.route.append(key + "=" + native(value))
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
                code, out = self.ask("status", "--porcelain", *(["--ignored"] if ignored else []),
                                     *(["--", *self.paths] if self.paths else []), where=where)
            except Exception:
                code, out = 1, ""
            # If we cannot tell whether the tree is dirty, assume it is. Refusing a safe command
            # costs a sentence; allowing an unsafe one costs the work.
            if code != 0:
                return "(could not read git status — assuming there is uncommitted work)"
            if ignored and self.paths:  # leeway v0.14.1 sync review: `checkout REV -- build/` keeps build/x.o
                out = "\n".join(line for line in out.splitlines()  # unless REV holds it
                                 if not line.startswith("!! ") or self.holds(line[3:], where))
            if out:
                return out
        return ""

    def holds(self, path, where):
        """Whether the path checkout's revision holds this root-relative path. A C-quoted name, or a revision
        the hook cannot read or git cannot resolve (`$(...)`, `$R`: review leewayfix High), holds it."""
        try:
            return (path.startswith('"') or unknowable(self.tree)
                    or self.ask("rev-parse", "--verify", "-q", self.tree + "^{tree}", where=where)[0] != 0
                    or self.ask("cat-file", "-e", f"{self.tree}:{path}", where=where)[0] == 0)
        except Exception:  # noqa: BLE001 - cannot tell: the ignored file counts
            return True


def listed_paths(g, name, nul):
    """The paths a --pathspec-from-file names, or None for stdin, an unreadable or empty file, a name the
    hook cannot read or a C-quoted line (leeway v0.14.1 sync review)."""
    steps = [v for k, v in zip(g.route, g.route[1:]) if k == "-C"]  # git reads it after -C
    if name in ("-", None) or g.cwd is None or unknowable(name) or any(unknowable(s) for s in steps):
        return None
    # the option names hold `paths`, `spec`, `file`: a file so named is counted outside them (review leewayfix r3 Low)
    if not once(name, re.sub(r"--pathspec-(?:from-file|file-nul)", " ", LINE)):  # review leewayfix Medium: `echo f.txt > list.txt && git checkout --pathspec-from-file=list.txt`
        return None  # the line names the file elsewhere, so it may write it before the checkout reads it
    try:
        with open(os.path.join(g.cwd, *steps, native(os.path.expanduser(name))), encoding="utf-8") as file:
            text = file.read()
    except (OSError, ValueError):
        return None
    paths = [p for p in (text.split("\0") if nul else text.splitlines()) if p]
    return None if not paths or any(p.startswith('"') and not nul for p in paths) else paths


def hooks_config_allowed(g):
    """Read or a single project-local hooksPath value, using config's option/operand grammar."""
    actions = {"--get": "get", "--get-all": "get", "--get-regexp": "get",
               "--replace-all": "set", "--list": "list", "-l": "list"}
    action, scope, operands, literal = None, None, [], False
    for arg in g.args:
        if not literal and arg == "--":
            literal = True
        elif not literal and arg in {"--show-origin", "--show-scope", "--null", "-z"}:
            continue  # output form only: it neither reads nor writes a value
        elif not literal and arg in {"--local", "--worktree", "--global", "--system"}:
            if scope is not None:
                return False
            scope = arg
        elif not literal and arg in actions:
            if action is not None:
                return False
            action = actions[arg]
        elif not literal and not operands and action is None and arg in {"set", "get", "list"}:
            action = arg  # Only a subcommand in command position, never a value or value-pattern.
        elif not literal and arg.startswith("-"):
            return False
        else:
            operands.append(arg)
    if not operands or operands[0].lower() != "core.hookspath":
        return False
    if action in {None, "get"} and len(operands) == 1:
        return True
    if (action not in {None, "set"} or len(operands) != 2 or operands[1] != ".githooks"
            or scope in {"--global", "--system"}):
        return False
    try:
        # The write lands in the repository of one of the folders the command may stand in,
        # reached through the command's own routes and env: .githooks stays inside each one's tree.
        for where in g.cwds:
            if where is None:
                return False
            code, root = g.ask("rev-parse", "--show-toplevel", where=where)
            if code or not root:
                return False
            root = os.path.normcase(os.path.realpath(root))
            hooks = os.path.normcase(os.path.realpath(os.path.join(root, operands[1])))
            if os.path.commonpath([root, hooks]) != root:
                return False
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def stash_in_head(g, ref):
    """Whether every file stash entry `ref` saved (worktree, index and untracked parts) is in HEAD with
    the same content and mode, in every folder the command may run in: dropping it then loses nothing."""
    if unknowable(ref) or not g.cwds or None in g.cwds:
        return False
    if ref.isdigit():  # git takes a bare index for stash@{n} (review r-v0141-fields Low)
        ref = "stash@{%s}" % ref
    try:
        for where in g.cwds:
            code, stash = g.ask("rev-parse", "--verify", "-q", ref + "^{commit}", where=where)
            if code or not stash:
                return False
            code, parents = g.ask("rev-list", "--parents", "-n", "1", stash, where=where)
            parents = parents.split()[1:]
            if code or len(parents) not in (2, 3):
                return False
            # the worktree and index parts against their base; the untracked part is a tree of its own
            parts = [(stash, parents[0]), (parents[1], parents[0])] + ([(parents[2], None)] if len(parents) == 3 else [])
            for tree, base_ in parts:
                code, names = (g.ask("diff", "--name-only", "--no-renames", "-z", base_, tree, where=where) if base_
                               else g.ask("ls-tree", "-r", "--name-only", "-z", tree, where=where))
                paths = [n for n in names.split("\0") if n]
                if code:
                    return False
                if not paths:
                    continue
                listed = [g.ask("--literal-pathspecs", "ls-tree", "-r", "-z", t, "--", *paths, where=where)
                          for t in (tree, "HEAD")]
                if any(c for c, _ in listed) or listed[0][1] != listed[1][1]:
                    return False
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def verdict(g, depth=0, aliases=True):
    """None, or (always, why, ignored_counts) for one git invocation, or ("shell", text, cwds,
    fallback why) when git runs shell text (findings() judges it). `aliases=False`: an unknown
    subcommand is no alias (a command that may not be git: `$(which python3) x.py`)."""
    sub, args = g.sub, g.args
    if any(c.split("=", 1)[0].lower() == "core.hookspath" for c in g.configs):
        return True, GATE, False
    if sub in HOOK_SUBS and any(HOOK_ENV.match(k) for k in g.env):
        return True, "a GIT_CONFIG_*, HUSKY, SKIP or PRE_COMMIT variable on this command can switch the gate off", False
    if unknowable(sub) or any(splat(a) for a in args):
        return True, "the git subcommand or arguments come from a variable, a splat or xargs, so the hook cannot read them", False
    if sub == "config" and any(a.lower() == "core.hookspath" or unknowable(a) for a in args):
        if not hooks_config_allowed(g):
            return True, "setting core.hooksPath (or a key or value the hook cannot read) moves the commit gate. " + GATE, False
        return None
    opts, words = options(sub, args)
    names = {n for n, _ in opts}
    first = (words or [""])[0]
    if sub in ("stash", "remote", "reflog", "worktree", "submodule") and unknowable(first):
        return True, f"git {sub} gets its action from a variable or from xargs, so the hook cannot read it", False
    if sub in HOOK_SUBS and (not last(opts, "verify", "no-verify", True)
                             or last(opts, "no-gpg-sign", "gpg-sign")):
        return True, GATE, False
    if sub == "stash" and first == "drop" and len(words) <= 2 and stash_in_head(g, (words[1:] or ["stash@{0}"])[0]):
        return None  # leeway lead 43: every file of the entry is in HEAD as stashed, so the drop loses nothing
    if sub == "stash" and first in ("drop", "clear"):
        return True, ("git stash drop/clear deletes stashed work, which may be its only copy (an entry whose "
                      "every file HEAD holds as stashed is dropped; commit it first). Set work aside with a "
                      "WIP commit, not a stash"), False
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
        for where in g.cwds:
            try:
                code, out = g.ask("branch", "-r", "--contains", "HEAD", where=where) if where else (1, "")
            except Exception:
                code = 1
            if code != 0 or out:  # cannot tell: refuse, as below
                return True, "git commit --amend rewrites a commit a remote branch already holds", False
    if sub == "reset" and last(opts, "hard", "soft") and "hard" in names:
        if [n for n, _ in opts if n in ("hard", "soft", "mixed", "merge", "keep")][-1] == "hard":
            return False, "git reset --hard discards every uncommitted change", False
    if sub == "checkout" and not names & {"b", "B", "orphan", "patch"}:
        if "force" in names or "--" in args or len(words) != 1 or "pathspec-from-file" in names:
            paths = args[args.index("--") + 1:] if "--" in args else []
            rev = (options(sub, args[:args.index("--")])[1] if "--" in args else words)[:1]
            if "pathspec-from-file" in names:  # leeway v0.14.1 sync review: no path word, no `--`, still a path checkout
                paths = listed_paths(g, dict(opts)["pathspec-from-file"], "pathspec-file-nul" in names)
                if paths is None:
                    return False, ("git checkout --pathspec-from-file overwrites the paths it lists, which the hook "
                                   "cannot see (stdin, an empty or unreadable file, or one this line also names and so "
                                   "may write first), so the whole tree is judged"), False
            # A pathspec option or variable (--icase-pathspecs) changes what the paths match: the whole tree is asked
            # (review r327 Medium; status would get the paths without it).
            if (paths and "force" not in names and not any(unknowable(p) for p in paths)
                    and not any("pathspecs" in t for t in g.options)
                    and not any(k.endswith("_PATHSPECS") for k in g.env)):
                # #327: labricore's path checkouts were refused over staged files elsewhere (59 hits).
                # An ignored file counts only for a revision that holds its path: from the index it is never touched.
                g.paths, g.tree = paths, (rev or [None])[0]
                return False, ("git checkout of these paths overwrites their working copy" + (
                    " (its revision cannot be read, so ignored files count as well)"
                    if rev and unknowable(rev[0]) else "")), bool(rev)
            if "pathspec-from-file" in names:
                return False, "git checkout of the listed paths, or -f, overwrites the working copy", False
            if "force" in names or words:
                return False, "git checkout of a path, or -f, overwrites the working copy", False
        else:
            try:
                revision = "@{-1}" if first == "-" else first
                code, _ = g.ask("rev-parse", "--verify", "--quiet", revision + "^{commit}")
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
    if sub == "update-ref" and "stdin" in names:
        return True, "git update-ref --stdin changes refs this hook cannot read", False
    for where in g.cwds if sub in ("branch", "tag", "update-ref", "remote") else []:
        refs = moved_refs(g, sub, names, words, where)  # in every repository the command may reach
        if refs and unreached(g, refs, where):
            return True, (f"this git {sub} deletes or moves a ref whose commits no other branch or tag reaches "
                          "(or one the hook cannot name), so they would be lost. Merge them into a kept branch "
                          "first; a ref that only points where another ref already does can go "
                          "(`git update-ref -d <ref> <expected-commit>`)"), False
    if sub == "reflog" and first in ("expire", "delete"):
        return True, "git reflog expire/delete removes the record that makes a lost commit recoverable", False
    expire_now = any(re.fullmatch(r"gc\.(?:pruneexpire|reflogexpire(?:unreachable)?)=(?!never$).*", c, re.I | re.S)
                     for c in g.configs)
    if (sub == "gc" and (expire_now or any(n == "prune" and v not in (None, "never") for n, v in opts))
            or sub == "prune" and not names & {"n", "dry-run"}):
        return True, "pruning unreachable objects now deletes commits and stashes only they still hold", False
    if sub == "worktree" and first == "remove" and names & {"f", "force"}:
        # The worktree named, from every folder the command may stand in and through each -C.
        steps = [v for k, v in zip(g.route, g.route[1:]) if k == "-C"]
        unknown = len(words) < 2 or any(unknowable(w) for w in [*steps, *words[1:2]])
        for c in g.cwds:
            held = Git([], {}, [None if c is None or unknown else
                                os.path.join(c, *steps, native(os.path.expanduser(words[1])))]).dirty()
            if held:
                return True, (f"git worktree remove --force deletes the worktree with the work it holds:\n\n{held}\n\n"
                              "Commit it there first. A kit worker's worktree is closed with "
                              "scripts/close_worker.sh <name>, which keeps a worktree that holds work"), False
    if (sub == "rm" and names & {"f", "force"} and "cached" not in names
            or sub in ("mv", "checkout-index") and names & {"f", "force"}
            or sub == "read-tree" and "u" in names and "reset" in names):
        return False, f"git {sub} with this option overwrites or deletes uncommitted changes", False
    if sub == "submodule" and first == "foreach":
        # The command runs as shell in every submodule, folders the hook does not name.
        rest = args[args.index("foreach") + 1:]
        while rest and rest[0] in ("--recursive", "-q", "--quiet"):
            rest = rest[1:]
        return "shell", " ".join(rest), [None], None
    if aliases and sub and sub not in SPEC and sub not in READ_ONLY and sub not in ("stash", "add", "init", "clone"):
        if g.cwd and not os.path.isdir(g.cwd):  # made by an earlier command of the line (a clone)
            return False, (f"git {sub} runs in {g.cwd}, a folder that does not exist yet, so the hook "
                           "cannot read whether it is an alias"), False
        try:
            code, alias = g.ask("config", "--get", "alias." + sub)
        except Exception:
            code, alias = 2, ""
        if code == 1:
            return None  # not an alias: a command of git's own or a git-<name> program
        if code == 0 and alias.startswith("!"):
            # A shell alias: its text, with the call's arguments after it, runs at the top of the
            # repository (one this hook cannot name when a route moves it).
            return ("shell", alias[1:] + " " + shlex.join(args), [None] if g.route else g.cwds,
                    f"git {sub} is an alias the hook cannot read")
        if code == 0 and depth < 5:
            try:
                g.sub, *rest = shlex.split(alias)
            except ValueError:
                return False, f"git {sub} is an alias the hook cannot read", False
            g.args = rest + args
            return verdict(g, depth + 1)
        return False, f"git {sub} is an alias the hook cannot read", False
    return None


def start(seg):
    """Where a simple command's own name stands: after keywords, VAR=value words and the TRANSPARENT wrappers
    with their options (judge() and commit_folders() read a segment alike). Raises Unreadable."""
    i = 0
    while i < len(seg):
        if seg[i] in KEYWORDS or re.match(r"[A-Za-z_]\w*=", seg[i]):
            i += 1
        elif base(seg[i]) in TRANSPARENT:
            wrapper = base(seg[i])
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                # env/exec options may consume or split the next word, or change cwd.
                # Do not mistake an option VALUE named `git` for the command itself.
                if wrapper in {"env", "exec"} and seg[i] != "--" and any(GIT_WORD.search(t) for t in seg[i:]):
                    raise Unreadable(f"git run through {wrapper} options")
                i += 1
        else:
            break
    return i


def shell_flag(rest, name):
    """The index of the `-c` of a shell this command runs, itself or behind a wrapper (`timeout 60 sh -c`,
    `xargs sh -c`): the words after it are the shell's text. None when there is none."""
    shell = next((k for k, t in enumerate(rest) if base(t) in SHELLS and not interpreter(base(t))
                  and (k == 0 or base(t) not in {".", "source"})), None) if name not in CALM | {"git"} else None
    return None if shell is None else next((k for k, t in enumerate(rest[shell + 1:], shell + 1)
                                            if re.fullmatch(r"-\w*c\w*|/c|-command", t, re.I)), None)


def judge(command, cwds, changed=False, env=None):
    """(always, why, (git, ignored, changed)) findings; raises Unreadable."""
    text, bodies = strip_heredocs(command)
    # A body for a file or cat is data and a shell's body is judged as a command below; an
    # interpreter's body is code no shell lexes, so a `<<<` anywhere in it counts.
    code = [body for shell, body in bodies if not shell]
    if GIT_WORD.search(command) and (any(re.search(r"\\\r?\n", t) for t in [text, *code])
                                     or any("<<<" in t for t in [unquoted(text) or text, *code])):
        raise Unreadable("a backslash-newline or a here-string")
    # Every folder the command may stand in. The caller's folder is always one: a `cd` may not run
    # (after `||`), may run in a subshell (`( )`, a pipeline, `&`), so it only adds a folder.
    env, cwds, pipeline_git = dict(env or {}), list(cwds), False
    for seg, ending in segments(text, with_endings=True):
        input_git = pipeline_git
        pipeline_git = ending in {"|", "|&"} and (input_git or any(GIT_WORD.search(t) for t in seg))
        local, i = {}, start(seg)
        for k, _, v in (w.partition("=") for w in seg[:i] if re.match(r"[A-Za-z_]\w*=", w)):
            local[k] = v
            if COMMAND_VAR.fullmatch(k) and GIT_WORD.search(v):
                yield from judge(v, cwds, changed, env)
                # GIT_CONFIG_PARAMETERS holds 'key=value' pairs; core.editor, diff.external or
                # core.sshCommand there runs as a command (r327 r2 Low).
                for pair in re.findall(r"'([^']*)'", v):
                    if GIT_WORD.search(pair.partition("=")[2]):
                        yield from judge(pair.partition("=")[2], cwds, changed, env)
        rest = seg[i:]
        name = base(rest[0]) if rest else ""
        has_git = any(GIT_WORD.search(t) for t in rest)
        here = {**env, **local}
        flag = shell_flag(rest, name)
        leading = list(itertools.takewhile(lambda t: t.startswith("-"), rest[1:]))
        if rest and rest[0].startswith("$") and any(t in SPEC or t in ("stash", "remote", "config") for t in rest[1:]):
            raise Unreadable("a command named by a variable")
        if name == "eval" and has_git:
            yield from judge(" ".join(rest[1:]), cwds, changed, here)
        elif flag and has_git:  # judged with its own folders: a `cd` inside moves only that text
            yield from judge(" ".join(rest[flag + 1:]), cwds, changed, here)
        elif (name in SHELLS and not interpreter(name) and any(GIT_WORD.search(t) for t in text.split())
              and (len(leading) == len(rest) - 1 or any(re.fullmatch(r"-[a-zA-Z]*s[a-zA-Z]*", t) for t in leading))):
            raise Unreadable(f"{name} reading commands from its input")  # no script operand, or -s
        elif (input_git and name not in CALM | {"git"} and any(interpreter(base(t)) for t in rest)
              and not (name in ("awk", "gawk", "mawk") and plain_awk(rest[1:], text))):
            raise Unreadable(f"interpreter input through {name}")
        elif name != "git" and name not in INERT and has_git:
            # An interpreter's code, a wrapper's command (sudo, xargs: it appends operands) or
            # another program's data.
            yield from loose(" ".join(rest[1:]), cwds, changed, here, name in ("xargs", "parallel"))
        if name == "export":
            env.update(dict(t.split("=", 1) for t in rest[1:] if "=" in t))
            for t in rest[1:]:
                k, _, v = t.partition("=")
                if COMMAND_VAR.fullmatch(k) and GIT_WORD.search(v):
                    yield from judge(v, cwds, changed, env)
                    # GIT_CONFIG_PARAMETERS holds 'key=value' pairs; core.editor, diff.external or
                    # core.sshCommand there runs as a command (r327 r2 Low).
                    for pair in re.findall(r"'([^']*)'", v):
                        if GIT_WORD.search(pair.partition("=")[2]):
                            yield from judge(pair.partition("=")[2], cwds, changed, env)
        if name in CD:
            cwds = moved(rest, cwds)
            continue
        at = next((k for k, t in enumerate(rest) if unknowable(t)), None) if name not in INERT else None
        if name == "git":
            g = Git(rest[1:], here, cwds)
            # A -c value git may run (core.editor, diff.external, core.sshCommand, alias.x=!...) is shell text (r327 r2).
            for config in g.configs:
                if GIT_WORD.search(config.partition("=")[2]):
                    yield from judge(config.partition("=")[2].lstrip("!"), cwds, changed, here)
            yield from findings(g, changed)
            changed = changed or g.sub not in READ_ONLY
        elif at is not None:
            # whichgit: `$(which git) reset --hard`, first or behind a wrapper (`timeout 60 $(which git) ...`, r2), names
            # a command the hook cannot resolve, so it may be git: the words after it are read as git's, by the same
            # verdict(), without an alias lookup. An unreadable subcommand (`$(which python3) "$f"`) is no git verb.
            g = Git(rest[at + 1:] + [UNKNOWN] * (at > 0 and name in ("xargs", "parallel")), here, cwds)
            word = rest[at].replace(UNKNOWN, "$(...)")
            for always, why, found in [] if unknowable(g.sub) else findings(g, changed, aliases=False):
                yield always, f"`{word}` names a command the hook cannot resolve, so it is read as git: {why}", found
            changed = True
        elif name not in CALM:
            changed = True
    # Here-document bodies and substitutions run inside some command of the line: judged with
    # every folder, variable and change the whole line reaches, so a `cd` before them counts.
    for shell, body in bodies:
        yield from (judge if shell else loose)(body, cwds, changed, env)
    for inner in substitutions(text):  # shell text inside shell text: parsed as shell
        if GIT_WORD.search(inner):
            yield from judge(inner, cwds, changed, env)


CD = {"cd", "pushd", "popd", "set-location", "sl", "push-location", "pop-location"}


def moved(rest, cwds):
    """The folders after `cd DIR` (a CD command and its words): a `cd` may not run (after `||`, in a subshell), so it
    only adds a folder; None for one the hook cannot name. guard_risky_review.py reads its tree with this too."""
    args = [t for t in rest[1:] if not t.startswith("-") or t == "-"]
    target = native(os.path.expanduser(os.path.expandvars(args[0]))) if args and "pop" not in base(rest[0]) else None
    return list(dict.fromkeys(cwds + [None if target is None or unknowable(target) or target == "-" or c is None
                                      else os.path.join(c, target) for c in cwds]))


def powershell(command):
    """A PowerShell line as the shell reader reads it: a backslash is a path's (`cd .\\wt`), `$env:NAME = v` sets NAME
    for later commands, and a `( ... )` operand is a sub-expression, PowerShell's `$( ... )`."""
    global SPLAT
    SPLAT = True
    command = re.sub(r"\$env:(\w+)\s*=\s*", r"export \1=", command.replace("\\", "/"), flags=re.I)
    return re.sub(r"(?<!\$)\(", " $(", command)


def commit_folders(command, cwd, tool_name=None, why=None):
    """Every folder a `git commit` on this line stands in, its `cd`s read as judge() reads them (after a keyword,
    in an if body, PowerShell's Set-Location/sl/Push-Location, a Git Bash drive path) and its -C values applied;
    None for one the hook cannot name; [] for a line that holds no commit. `why`, a list, gets the text of each
    command that names a git commit the hook cannot look through. Raises Unreadable (an unbalanced quote). The one
    commit reader of guard_risky_review.py, which had a regex of its own that missed `"git" commit` and
    `git --namespace x commit` (syncfind; review leewayfix)."""
    if tool_name == "PowerShell":
        command = powershell(command)
    return list(dict.fromkeys(commits(command, [cwd], [] if why is None else why)))


def into(cwd, dirs):
    """The folder `git -C DIR ...` stands in from cwd; None when a DIR is only known at run time or is no folder
    (labricore A4: it fell back to the session's tree). A cwd that is no folder is left as it is: no shell stands
    there, and guard_risky_review.folders() leaves it out."""
    for value in dirs:
        if cwd is None or not os.path.isdir(cwd):
            break
        value = re.sub(r"\$\{?PWD\}?|\$\(pwd\)|`pwd`", lambda _: cwd, value)
        value = native(os.path.expanduser(os.path.expandvars(value)))
        cwd = None if unknowable(value) or not os.path.isdir(os.path.join(cwd, value)) else os.path.join(cwd, value)
    return cwd


def commits(command, cwds, why):
    """commit_folders() for one shell text: a segment is read as judge() reads it (start(), shell_flag()); a
    shell's text (`sh -c`, eval, a shell's here-document, a substitution) is read with the same folders, its own
    `cd`s moving only it; a wrapper that runs git (timeout, xargs, sudo) is looked through to its git word. A
    segment with a word that holds git and commit (code, a wrapper's text) the hook does not read as a git command
    is None (review leewayfix r3 High); without one it commits nothing and cannot move a later commit (a program
    never changes its shell's folder), so `rg -n "git log" docs/commit.md` holds no commit. shortcut: a commit is read by its word, so an alias (`git ci`) is not seen;
    upgrade to the git hook if an agent commits that way."""
    text, bodies = strip_heredocs(command)
    found = []
    for seg in segments(text, strict=True):
        rest = seg[start(seg):]
        name = base(rest[0]) if rest else ""
        has_git = any(GIT_WORD.search(t) for t in rest)
        flag = shell_flag(rest, name)
        at = next((k for k, t in enumerate(rest) if base(t) == "git"), None)
        if name in CD:
            cwds = moved(rest, cwds)
        elif flag is not None and has_git:
            found += commits(" ".join(rest[flag + 1:]), cwds, why)
        elif name == "eval" and has_git:
            found += commits(" ".join(rest[1:]), cwds, why)
        elif at is not None and (at == 0 or name not in INERT):
            g = Git(rest[at + 1:], {}, cwds)
            # --git-dir/--work-tree name a tree rev-parse may not find from a folder: unresolvable (syncfind r2).
            # An attached -Cwt needs nothing: git refuses it ("unknown option").
            other = any(r.startswith(("--git-dir", "--work-tree")) for r in g.route)
            found += [None if other else into(c, g.dirs) for c in cwds] if g.sub == "commit" else []
        elif rest and unknowable(rest[0]) and "commit" in rest[1:]:
            found.append(None)  # `$GIT commit`: judge() refuses a command named by a variable (syncfind r2)
        elif any(GIT_WORD.search(t) and "commit" in t for t in rest) and name not in INERT and not (
                name in TEXT_ARGS and not any(GIT_WORD.match(t.lstrip("($`")) for t in rest[1:])):
            # Code or a wrapper's text that names git: the hook cannot tell where it runs. Only a git inside
            # the prose argument of a TEXT_ARGS program (gh --title "fix the git hook") is none (cb35ca5 review).
            found.append(None)
            why.append(shlex.join(rest))
    for shell, body in bodies:
        if GIT_WORD.search(body) and shell:
            found += commits(body, cwds, why)
        elif GIT_WORD.search(body) and shell is not None and "commit" in body:  # an interpreter's body is code
            found.append(None)  # (cb35ca5 review)
            why.append(body.strip().splitlines()[0])
    for inner in substitutions(text):
        found += commits(inner, cwds, why) if GIT_WORD.search(inner) else []
    return found


def once(operand, text):
    """Whether the line names the operand's file only as the operand: by its base name, any case
    (a case-folding disk), quotes and backslashes dropped (`x".py"`, `./x.py`; review r-v0141-fields)."""
    return re.sub(r"['\"\\]", "", text).lower().count(operand.rsplit("/", 1)[-1].lower()) == 1


def plain(command):
    """The command with its quoted strings, comments and here-document bodies blanked when every
    command of the line is INERT, a PLAIN_GIT git without -c (#327) or an interpreter given plain file
    operands alone; None otherwise."""
    try:
        text, bodies = strip_heredocs(command)
        blank = unquoted(text)
        if any(shell for shell, _ in bodies):
            return None  # a body the shell runs or expands (review r327 High)
        for seg in segments(text, strict=True) if blank is not None else [["eval"]]:
            if any((COMMAND_VAR.fullmatch(k := w.split("=", 1)[0]) or k.startswith("GIT_")) and not NAME_VAR.fullmatch(k)
                   for w in seg if re.match(r"[A-Za-z_]\w*=", w)):
                return None  # a variable git runs as a command (review r327 High)
            words = list(itertools.dropwhile(lambda w: w in KEYWORDS or re.match(r"[A-Za-z_]\w*=", w), seg))
            if not words:
                continue
            if base(words[0]) == "git":
                g = Git(words[1:], {}, [None])
                if g.configs or g.sub not in PLAIN_GIT:
                    return None
            elif base(words[0]) not in INERT and not (
                    # leeway-43: `cat > n.md <<EOF ... EOF; python3 x.py` read the cat's body raw; an
                    # interpreter given only plain file operands runs no text of this line
                    interpreter(base(words[0])) and len(words) > 1 and not re.search(r"[$`{*?[]", text)
                    and all(re.fullmatch(r"[\w.+/][\w.+/-]*", w) and once(w, text) for w in words[1:])):
                # ... unless the line also names that file (it may write it: `cat > n.py <<EOF`)
                return None
        return blank
    except Exception:  # noqa: BLE001 - unreadable: the floor reads the raw text
        return None


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        # Any tool's command: the settings matcher picks the tools (Bash, PowerShell, Monitor).
        command = (data.get("tool_input") or {}).get("command") or ""
        if not isinstance(command, str):
            raise ValueError("tool_input.command is not a string")
    except Exception as exc:
        return f"guard_destructive_git.py could not read the hook input ({exc}), so it cannot tell whether this command loses work. Report this to the owner"
    if not re.search("git", command, re.I):
        return None
    unreadable = ("this command holds git inside {}, which this hook cannot read, so it cannot tell "
                  "whether the command loses work; run the git command directly, as its own command")
    if data.get("tool_name") == "PowerShell":
        if "`" in command and GIT_WORD.search(command):
            return unreadable.format("a PowerShell backtick (an escape or a line continuation)")
        command = powershell(command)
    global LINE
    LINE = command
    # On a plain line the parser judges a path checkout by those paths alone (#327).
    text = plain(command)
    floor = next((why for pattern, why in FLOOR if pattern.search(command if text is None else text)
                  and (text is None or pattern is not FLOOR[1][0])), None)
    # A lone `git stash drop [REF]` of an entry HEAD holds as stashed loses nothing, dirty tree or not
    # (review r-v0141-fields Medium: the floor refused it before verdict() could tell).
    lone = re.fullmatch(r"\s*git(?:\.exe)?\s+stash\s+drop(?:\s+([\w@{}]+))?\s*", command)
    if lone and stash_in_head(Git([], {}, [os.getcwd()]), lone.group(1) or "stash@{0}"):
        return None
    if floor:  # the base rule, first and never cleared by the parser below
        dirty = Git([], {}, [os.getcwd()]).dirty()
        if dirty:
            return lost(floor, dirty)
    try:
        found = list(judge(command, [os.getcwd()]))
    except Unreadable as exc:
        return unreadable.format(exc)
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
    lines = dirty.splitlines()
    if len(lines) > 10:  # #327: a long list was printed whole on every refusal
        dirty = "\n".join(lines[:10] + [f"... and {len(lines) - 10} more (git status --porcelain)"])
    return (f"{why}, and this tree has uncommitted changes:\n\n{dirty}\n\n"
            "Uncommitted work is NOT in the reflog. If any of the above is not yours — a file the "
            "owner edited by hand, a note written this session — this command is the last moment it "
            "exists.\n\n"
            "Do one of these first, then re-run:\n"
            "  git add -A && git commit -m 'wip'      # recoverable; the gate runs, never --no-verify\n"
            "  git stash push -u -m 'before <what you are about to do>'   # recoverable; drop it once committed\n\n"
            "If you have checked the list above and every entry is disposable, say so to the owner "
            "and ask them to run the command themselves")


if __name__ == "__main__":  # guard_risky_review.py imports commit_folders
    refusal = main()
    if refusal:
        print("BLOCKED: " + refusal + ".", file=sys.stderr)
        sys.exit(2)
