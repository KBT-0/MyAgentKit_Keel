#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Line-ending repair for a clone made before `.gitattributes` held `eol=lf`. Run it once from
# the repository root, with no uncommitted change to the scripts or hooks:
#
#   sh scripts/fix_crlf.sh
#
# `sh` cannot run a CRLF script, and a pull does not check out again a file it did not change,
# so an old clone keeps its CRLF gate and hooks. The core is the documented one: rewrite the
# working copy, then `git add --renormalize -- '*.sh' '.githooks/*'` (gitattributes, "eol" and
# --renormalize: git-scm.com/docs/gitattributes; GitHub Docs, "Configuring Git to handle line
# endings"). Each CRLF becomes LF in a regular file, a lone CR is kept, each file is replaced
# whole with its mode. A file that is, or lies below, a symlink or a junction is left alone
# with a line saying so: the rewrite would write outside the project (the kit's own review
# finding, not a reported incident; harmless, so it stays: KARARLAR D07 inv3#82). A failed
# rewrite or a failed `git ls-files` (a corrupt index) stops before anything is staged; a
# temporary copy a SIGKILL left (`.crlf-*`) stops the next run.
# A file added after the attributes checks out with LF, so this script itself can run.

# Windows installs Python as `python` or `py`: the first that runs, as doctor.sh resolves it.
if python3 -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python3
elif python -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python
else kit_python="py -3"; fi   # the launcher, told which Python: unquoted at every use

left=$(git ls-files --others -- ':(glob)**/.crlf-*')
[ -z "$left" ] || { printf '%s\n' "STOP: a killed run left $left; delete it, then run this again" >&2; exit 1; }
list=$(mktemp) || exit 1
trap 'rm -f "$list"' EXIT; trap 'exit 129' HUP; trap 'exit 130' INT; trap 'exit 143' TERM
set -- '*.sh' '.githooks/*'
git ls-files -z -- "$@" > "$list" || { echo "STOP: git ls-files failed (above); nothing was changed" >&2; exit 1; }
$kit_python -I -c 'if 1:
    import os, signal, stat, sys, tempfile
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(143))
    def plain(name):
        # Every folder on the way and the file itself: no symlink, no junction (a reparse
        # point), or the rewrite wrote into what the link points at, outside the project.
        parts = name.split(b"/")
        for i in range(1, len(parts) + 1):
            info = os.lstat(b"/".join(parts[:i]))
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                return False
        return stat.S_ISREG(info.st_mode)
    for name in sys.stdin.buffer.read().split(b"\0"):
        if name and not plain(name):
            sys.stderr.write("left alone, a link or not a regular file on its way: %r\n" % name)
        elif name:
            with open(name, "rb") as script:
                data = script.read()
            if b"\r\n" in data:
                handle, new = tempfile.mkstemp(prefix=b".crlf-", dir=os.path.dirname(name) or b".")
                try:
                    with os.fdopen(handle, "wb") as copy:
                        copy.write(data.replace(b"\r\n", b"\n"))
                    os.chmod(new, stat.S_IMODE(os.lstat(name).st_mode))
                    os.replace(new, name)
                finally:
                    if os.path.lexists(new):
                        os.unlink(new)' < "$list" ||
  { echo "STOP: a script could not be rewritten (above); nothing was staged" >&2; exit 1; }
if [ -s "$list" ]; then xargs -0 git add --renormalize -- < "$list"; fi
