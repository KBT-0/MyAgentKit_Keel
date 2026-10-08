#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Remove the finished worktrees under .claude/worktrees, and only what is proven safe to lose.

Run through scripts/clean_worktrees.sh, which says why this exists. It needs git 2.36 or newer
(`git worktree list --porcelain -z`). With no option it is a dry run; --apply removes. It never deletes a branch: the branch keeps every commit it had whatever
happens to main later (a merge undone, a reset), and the disk is in the worktree, not in the
branch. Nothing is removed while the main worktree's HEAD is detached: "merged" is tested
against its branch. A worktree is removed only when every check below holds; a check that
fails, errors, or meets output it does not know keeps the worktree, with the reason printed.
The checks run cheapest first and stop at the first reason to keep (--all-reasons runs them
all):

  a. a linked worktree of this repository, physically directly under
     <main worktree>/.claude/worktrees/, not the main worktree, not the one this runs in, its
     folder its own worktree (not missing, not prunable), not locked; its path and branch
     printable, so that the command that brings it back can be printed;
  b. finished: on a branch; its OWN HEAD reflog records a commit made in it (WORK below); its
     HEAD is in the main worktree's branch;
  c. quiet: nothing in its git directory changed (mtime or ctime) within quiet-minutes (60
     unless .claude/worktree-disposable says otherwise);
  d. no merge, rebase, cherry-pick, revert, bisect or sequencer in progress;
  e. not in use: the process listing shows this script itself and no process with its working
     directory inside it (/proc on Linux, lsof elsewhere, its escaped names read back exactly or
     the listing is not proven; native Windows: each process's own record of it, its PEB;
     compared case-folded and Unicode-normalised, as macOS names are), no tmux session has its
     name, the gate's lock is free (Windows: its file can be opened for writing);
  f. nothing only its git directory holds: removal destroys that directory, so every object id
     in every file of it (both columns of every reflog line, every ref, every pseudo-ref, any
     file this script does not know, in either case), NO_HISTORY excepted, names no object, or
     a commit or tag reachable from what a ref of the repository points at (no reflog: `git
     branch -d` deletes the branch's, so an amended, reset or rebased-away tip is saved too;
     no remote-tracking ref: `git fetch --prune` drops it), or a commit this saves: before
     removing, one `git update-ref --stdin` transaction pins every commit only its git
     directory holds that no other of them reaches, as refs/kit/saved/<its git directory name,
     percent-encoded, cut to 64 bytes>-<12 hex digits of its SHA-256>-<UTC time>/<n>, and the
     check runs again with those refs. A tree or
     blob id keeps it: rev-list cannot tell whether one is held. The files ref backend; no
     per-worktree config;
  g. tracked content, by bytes: no change `git status` reports with the stat settings forced to
     their defaults; the index equals HEAD's tree; every tracked path is, in the worktree,
     exactly the blob the index records (raw bytes, no filter or line-ending conversion, the
     same executable bit; a symlink's text); no unresolved entry, no submodule;
  h. no mount point in it or in its git directory, its folder itself and disposable folders
     included (git's recursive remove of both would delete what is under one, which is not the
     worktree's): no entry on another device than its root, no root on another device than
     its parent folder, none the mount table lists (Linux: /proc/self/mountinfo, which alone
     shows a bind mount on the same device; elsewhere such a bind mount cannot be seen; on
     Windows a folder that is a reparse point, a junction or a folder symlink, counts as one:
     Git for Windows' recursive remove went through a junction and deleted what it pointed at);
     the walk does not go into a mount point; no file under its own .claude/worktrees under any
     spelling (a worktree inside a worktree, which this script does not judge);
     every other file git does not track is inside a directory .claude/worktree-disposable
     lists, or a regular file whose byte-identical copy is at the same path in the main
     worktree, outside its .claude/worktrees under any spelling (what is there is a worktree's,
     which may go too), not at or below a mount point in main (a mount inside main is not main:
     another device than main's root, or listed in the mount table) and not the worktree's file
     itself (a hard link, a mounted worktree folder: the same device and inode), and that is not
     a tracked file under another name (a case alias, a link: the same device and inode);
     nothing anywhere in it, disposable folders included, changed within quiet-minutes. Case: a
     place that holds work (REFUSED) is compared case-folded on every file system, as macOS
     compares names, and a disposable entry byte for byte: either only ever keeps more.

Proven: a, b, d, f, g, h's accounting. The quiet period (c, h) is a margin, not a proof: it
covers a worker whose process the scan in e cannot see. e is read afresh for every worktree
and twice more right before removal. Not guarded, by the owner's decision: a process that
changes a worktree's files, or main's copies of them, between its audit and its removal, files planted to attack this
script, and a SIGKILL between two removal steps. Lost with a removal and never restored: the
ignored files in disposable folders, and the worktree's own reflogs (every commit they name is
held or saved, by f).

Every name it prints or logs is escaped reversibly (ESCAPING). The filesystem is walked on its
own, never through a symlink, and every entry that is not tracked must be accounted for: `git
status` does not list a FIFO, a socket or a device, and `git worktree remove` deletes them and
every ignored file without asking.

Removal order: the log's intent line (on disk; it names every ref to save and every file to
delete), the saved refs, f and e again, the identical copies git does not track, e again, `git
worktree remove` without --force (git's own check, independent of this one), the log's outcome
line (removed when git removed it, whatever was deleted before; else possibly-modified when
`git worktree remove` failed, even after a copy was deleted, as git may have deleted more;
partly-modified when a step stopped it after a copy was deleted; or kept; why; each file
deleted). Both lines carry the run's id, which pairs
them; an intent with no outcome is a run that did not finish. An outcome that cannot be
written leaves the removal as it is, stops the run and exits 1. Each line about the removal is
printed after the log line it reports; a print never raises (what stdout cannot encode is
escaped, a stdout closed or hung up is ignored), and the outcome is what happened, never
whether a line could be printed. A printed command reads back to the exact bytes of its names
whatever stdout can encode (sh_word). SIGINT, SIGTERM and SIGHUP are caught from
the saved refs on and stop it at the next step. A step that fails or is
stopped after a copy was deleted reports the worktree PARTLY MODIFIED, lists each file deleted
(its identical copy is at the same path in the main worktree) and exits 1; a failed `git
worktree remove`, which may have deleted files before it failed, is reported POSSIBLY
MODIFIED with what is left and how each kind of file comes back, and exits 1. A re-run is
safe, as what is left still holds; each deletion changed its folder, so it finishes after the
quiet period.
"""
import argparse
import codecs
import datetime
import filecmp
import hashlib
import importlib.util
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
import unicodedata

DISPOSABLE_FILE = b'.claude/worktree-disposable'
# Places that hold work: refused as a disposable entry, and a NAME entry does not match below them.
REFUSED = {b'.git', b'docs', b'.claude', b'.myagentkit', b'scripts'}
# Files and folders in a worktree's git directory while an operation is unfinished.
OPERATIONS = (b'MERGE_HEAD', b'CHERRY_PICK_HEAD', b'REVERT_HEAD', b'BISECT_START',
              b'rebase-merge', b'rebase-apply', b'sequencer')
# HEAD reflog subjects git writes when it made a NEW commit in that worktree: commit (also
# amend, initial, merge and cherry-pick: a conflicted one concluded by `git commit`), cherry-pick,
# revert, am, and a rebase step that wrote a commit. Not counted: a fast-forward (checkout,
# reset, `merge: Fast-forward`, `cherry-pick: fast-forward`, a rebase that only moved), and a
# merge made by `git merge` or `git pull` alone, which joins work made elsewhere.
WORK = re.compile(rb'(commit( \([a-z-]+\))?|cherry-pick|revert|am|rebase \((pick|reword|squash|fixup|continue)\)): ')
# Top-level files of a worktree's git directory that hold no history (f): index, the tracked
# state g verifies by bytes (and binary); check-build.log, the gate's build output, which may
# print any id; AUTO_MERGE, the tree git writes for a merge or rebase step and leaves behind
# when it ends (d proves none is under way): a pseudo-ref, which gc does not keep either, and
# a tree, not a commit. Every other file is scanned, the ones that hold no id at all included.
NO_HISTORY = {b'index', b'check-build.log', b'AUTO_MERGE'}
# The warnings lsof prints on stderr when one file system cannot be read; its listing of the
# rest stands (lsof(8), "can't stat()"). Any other stderr line makes a non-zero exit a failure.
LSOF_WARNINGS = re.compile(rb"lsof: WARNING: can't stat\(\) [^\n]*|\s*Output information may be incomplete\.")
QUIET_DEFAULT, QUIET_MIN = 60, 10
CAP = 5
# Caught while a worktree is being removed, so that a stop is reported, never silent; the
# signals that came, checked between two removal steps. Those that exist: native Windows
# Python has no SIGHUP, and the import must not fail there (main() then stops at once).
SIGNALS = tuple(getattr(signal, name) for name in ('SIGINT', 'SIGTERM', 'SIGHUP') if hasattr(signal, name))
STOP = []


class Unproven(Exception):
    """A check could not be completed; the worktree is kept with this text as its reason."""


ESCAPING = 'a backslash is \\\\, a newline \\n, any other byte that is not printable UTF-8 \\xNN'
# Two lines per removal: the intent, logged before anything is saved or deleted, and the outcome.
LOG_HEADER = ('# two lines per removal, tab-separated, after the time and run=<the run\'s id>, which pairs them: '
              '"intent", logged before anything is saved or deleted (its commits to save as saved=<ref>=<id>, its '
              'files to delete as delete=<path>), and "outcome", logged when it ends (removed, partly-modified, '
              'possibly-modified or kept, why, and deleted=<path> for each file deleted); an intent with no outcome '
              'is a run that did not finish; in every name %s\n' % ESCAPING)


def show(path):
    """A name as one printable line, reversibly (ESCAPING): a non-printable character is
    escaped byte by byte, so \\xNN always stands for the byte NN."""
    out = []
    for c in path.decode('utf-8', 'surrogateescape'):
        if c == '\\':
            out.append('\\\\')
        elif c == '\n':
            out.append('\\n')
        elif c.isprintable():
            out.append(c)
        else:
            out.extend('\\x%02x' % b for b in c.encode('utf-8', 'surrogateescape'))
    return ''.join(out)


def utf8_escape(error):
    """The codec error handler of say(): a character stdout cannot encode becomes its UTF-8
    bytes as \\xNN, as ESCAPING reads."""
    return ''.join('\\x%02x' % b for b in error.object[error.start:error.end].encode('utf-8', 'surrogatepass')), error.end


codecs.register_error('kit-utf8-escape', utf8_escape)


def say(text):
    """Print TEXT now; it never raises. What stdout cannot encode is escaped (utf8_escape); a
    stdout that is closed from the start (`>&-`: sys.stdout is None), closed or hung up (SIGHUP)
    is ignored from then on, so a removal still reaches its log lines, its report and its exit
    status."""
    try:
        sys.stdout.buffer.write(text.encode(sys.stdout.encoding, 'kit-utf8-escape') + b'\n')
        sys.stdout.buffer.flush()
    except (OSError, AttributeError, ValueError):
        try:
            fd = sys.stdout.fileno()
            null = os.open(os.devnull, os.O_WRONLY)
            try:
                os.dup2(null, fd)
            finally:
                os.close(null)
        except (OSError, AttributeError, ValueError):
            pass


def names(paths):
    paths = sorted(paths)
    more = len(paths) - CAP
    return ', '.join(show(p) for p in paths[:CAP]) + (' and %d more' % more if more > 0 else '')


def short(ref):
    return ref[len(b'refs/heads/'):] if ref.startswith(b'refs/heads/') else ref


def sh_quote(text):
    """TEXT as one word for a POSIX shell: in '...', each ' inside written as '\\''."""
    return "'" + text.replace("'", "'\\''") + "'"


def sh_word(raw):
    """The bytes RAW (no trailing newline) as one word a POSIX shell reads back exactly, in
    printable ASCII whatever stdout can encode: quoted (sh_quote) when RAW is printable ASCII,
    else "$(printf '...')" with every byte but a letter, a digit, / . _ as an octal escape."""
    if re.fullmatch(rb'[ -~]*', raw):
        return sh_quote(raw.decode())
    return '"$(printf \'%s\')"' % re.sub(rb'[^A-Za-z0-9/._]', lambda m: b'\\%03o' % m.group()[0], raw).decode()


def git_env():
    """This environment without the variables that bind git to one repository: a hook runs
    with GIT_DIR set, and `git -C <worktree> status` would then read the wrong index."""
    env = dict(os.environ, LC_ALL='C')
    local = subprocess.run(['git', 'rev-parse', '--local-env-vars'], capture_output=True, env=env)
    if local.returncode != 0:
        raise Unproven('git rev-parse --local-env-vars failed')
    for name in local.stdout.split():
        env.pop(name.decode(), None)
    return env


ENV = None
# `git status` compares by its stat cache; these make it compare every stat field and the mode.
# Windows keeps no executable bit: a tracked 100755 script read as modified there, and every
# worktree holding one was kept. Its mode is still proven where Windows keeps it, in the index
# against HEAD (g); its bytes are compared on every host.
NO_EXEC_BIT = os.name == 'nt'
STAT = ('-c', 'core.checkStat=default', '-c', 'core.trustctime=true',
        '-c', 'core.fileMode=%s' % ('false' if NO_EXEC_BIT else 'true'))


def git(cwd, *args, codes=(0,), stdin=None):
    result = subprocess.run(['git', '--no-optional-locks', *args], cwd=cwd, env=ENV, input=stdin,
                            stdin=None if stdin is not None else subprocess.DEVNULL, capture_output=True)
    if result.returncode not in codes:
        raise Unproven('`git %s` failed: %s' % (' '.join(a if isinstance(a, str) else show(a) for a in args),
                                                show(result.stderr.strip()) or 'exit %d' % result.returncode))
    return result


def worktrees(cwd):
    """The records of `git worktree list --porcelain -z`, each a dict; an unknown field is kept
    under 'unknown' and makes that worktree a keep."""
    records, record = [], {}
    for field in git(cwd, 'worktree', 'list', '--porcelain', '-z').stdout.split(b'\0'):
        if not field:
            if record:
                records.append(record)
            record = {}
            continue
        key, _, value = field.partition(b' ')
        if key in (b'worktree', b'HEAD', b'branch', b'locked', b'prunable', b'detached', b'bare'):
            record[key.decode()] = value
        else:
            record.setdefault('unknown', []).append(field)
    if record:
        records.append(record)
    if not records or any('worktree' not in r for r in records):
        raise Unproven('`git worktree list --porcelain -z` printed a record without a path')
    return records


def read_disposable(main_root):
    """The project's disposable entries, the lines refused, and the quiet period in minutes. A
    quiet-minutes line given twice or not valid refuses the whole list (fail closed). A place that
    holds work is refused under any spelling (fold)."""
    try:
        with open(os.path.join(main_root, DISPOSABLE_FILE), 'rb') as handle:
            data = handle.read()
    except FileNotFoundError:
        return [], [], QUIET_DEFAULT
    entries, refused, quiet = [], [], None
    for line in data.split(b'\n'):
        line = line.strip()
        if not line or line.startswith(b'#'):
            continue
        if line.startswith(b'quiet-minutes'):
            value = re.fullmatch(rb'quiet-minutes=(\d{1,6})', line)
            if quiet is not None or not value or int(value.group(1)) < QUIET_MIN:
                return [], [(line, '(a quiet-minutes line twice, or not a whole number of at least %d): the whole '
                             'list is refused, nothing is disposable and quiet-minutes=%d applies'
                             % (QUIET_MIN, QUIET_DEFAULT))], QUIET_DEFAULT
            quiet = int(value.group(1))
            continue
        entry = line.rstrip(b'/')
        parts = entry.split(b'/')
        # An absolute path has an empty first part.
        if (b'' in parts or b'.' in parts or b'..' in parts
                or {fold(r) for r in REFUSED}.intersection(fold(p) for p in parts)):
            refused.append((line, '(empty, absolute, "..", or a place that holds work: %s)'
                            % ', '.join(sorted(r.decode() for r in REFUSED))))
        else:
            entries.append(entry)
    return entries, refused, quiet or QUIET_DEFAULT


def disposable(rel, entries):
    """Whether REL lies inside a disposable directory, compared folder by folder: a NAME entry
    matches a folder of that name with no place that holds work (REFUSED, under any spelling)
    above it; a PATH entry matches its own subtree from the root. Entries match byte for byte."""
    folders = rel.split(b'/')[:-1]
    refused = {fold(r) for r in REFUSED}
    for entry in entries:
        parts = entry.split(b'/')
        if len(parts) > 1:
            if folders[:len(parts)] == parts:
                return True
            continue
        for folder in folders:
            if fold(folder) in refused:
                break
            if folder == parts[0]:
                return True
    return False


def mount_points(path):
    """The mount points the mount table PATH lists (Linux: /proc/self/mountinfo, its fifth field
    with its octal escapes read back); none where there is no such file outside Linux, where a
    bind mount on the same device cannot be seen. Compared with paths as the bytes the kernel
    gives, never folded: the table holds each path as it resolved it."""
    try:
        with open(path, 'rb') as handle:
            data = handle.read()
    except FileNotFoundError:
        if sys.platform.startswith('linux'):
            raise Unproven('no mount table %s: a bind mount could not be seen' % show(path))
        return set()
    points = set()
    for line in data.split(b'\n'):
        if not line:
            continue
        fields = line.split(b' ')
        if len(fields) < 5 or not fields[4].startswith(b'/'):
            raise Unproven('the mount table %s holds a line this script does not know: %s' % (show(path), show(line[:60])))
        points.add(re.sub(rb'\\([0-7]{3})', lambda m: bytes([int(m.group(1), 8)]), fields[4]))
    return points


def below_mount(ctx, rel):
    """Whether REL in the main worktree is, or lies below, a mount point: a folder on its way, or
    the file, on another device than main's root, or listed in the mount table (a bind mount on
    the same device). A mount inside main is not main."""
    device = os.lstat(ctx['main_root']).st_dev
    path = ctx['main_root']
    for part in rel.split(b'/'):
        path = os.path.join(path, part)
        if path in ctx['mounts']:
            return True
        info = os.lstat(path)
        if info.st_dev != device or reparse_folder(info):
            return True
        if not stat.S_ISDIR(info.st_mode):
            return False
    return False


def entry(root, rel, avoid=None):
    """The lstat of ROOT/REL reached through folders only (no symlink on the way, nor the folder
    whose (device, inode) is AVOID), or None."""
    path = root
    parts = rel.split(b'/')
    for part in parts[:-1]:
        path = os.path.join(path, part)
        try:
            info = os.lstat(path)
        except OSError:
            return None
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) == avoid:
            return None
    try:
        return os.lstat(os.path.join(path, parts[-1]))
    except OSError:
        return None


def copy_in(ctx, real, rel):
    """Whether the main worktree holds a regular file at REL with the bytes of REAL/REL, reached
    without a symlink and not through its .claude/worktrees, under any spelling: what is there is
    a worktree's, which this run may remove too. Not a copy: REAL/REL itself (a hard link, a
    worktree folder mounted into main: the same device and inode). Whether it is below a mount
    is below_mount's."""
    home = os.lstat(ctx['home'])
    info = entry(ctx['main_root'], rel, avoid=(home.st_dev, home.st_ino))
    return (info is not None and stat.S_ISREG(info.st_mode)
            and not os.path.samestat(info, os.lstat(os.path.join(real, rel)))
            and filecmp.cmp(os.path.join(real, rel), os.path.join(ctx['main_root'], rel), shallow=False))


def reparse_folder(info):
    """Native Windows: whether an lstat is a folder that is a reparse point (a junction, a
    folder symlink, a volume mount point). Git for Windows' recursive remove went into a
    junction and deleted what it pointed at, so the walk treats one as a mount point."""
    return bool(getattr(info, 'st_file_attributes', 0) & 0x410 == 0x410)


def walk(root, mounts=frozenset()):
    """(rel, lstat, is a folder, is a mount point) for every entry under ROOT, the root itself as
    b'', never through a symlink nor into a mount point: an entry MOUNTS lists, or on another
    device than ROOT (the root: than its parent folder). The worktree's own `.git` file is git's,
    not content, unless it is a mount point."""
    top = os.lstat(root)
    mount = root in mounts or top.st_dev != os.lstat(os.path.dirname(root)).st_dev or reparse_folder(top)
    yield b'', top, True, mount
    stack = [] if mount else [b'']
    while stack:
        folder = stack.pop()
        with os.scandir(os.path.join(root, folder) if folder else root) as entries:
            for item in entries:
                rel = folder + b'/' + item.name if folder else item.name
                path = os.path.join(root, rel)
                info = os.lstat(path)
                is_dir = stat.S_ISDIR(info.st_mode)
                mount = path in mounts or info.st_dev != top.st_dev or reparse_folder(info)
                if rel == b'.git' and not mount:
                    continue
                if is_dir and not mount:
                    stack.append(rel)
                yield rel, info, is_dir, mount


def changed(info):
    """When an entry last changed: its mtime, or its ctime when later (a tool that keeps the
    mtime of what it rewrites cannot keep the ctime)."""
    return max(info.st_mtime, info.st_ctime)


def status(path):
    """Untracked and ignored paths, and the tracked changes as (kind, path)."""
    out = git(path, *STAT, '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false', 'status',
              '--porcelain=v2', '-z', '--untracked-files=all', '--ignored=traditional',
              '--ignore-submodules=none').stdout
    untracked, ignored, changes = set(), set(), []
    fields = out.split(b'\0')
    i = 0
    while i < len(fields):
        field = fields[i]
        i += 1
        if not field:
            continue
        kind = field[:2]
        if kind == b'? ':
            untracked.add(field[2:])
        elif kind == b'! ':
            ignored.add(field[2:])
        elif kind in (b'1 ', b'2 ', b'u '):
            xy = field[2:4]
            target = field.split(b' ', {b'1 ': 8, b'2 ': 9, b'u ': 10}[kind])[-1]
            if kind == b'2 ':
                i += 1  # the rename's source path is the next field
            if kind == b'u ':
                changes.append(('unmerged', target))
            elif xy[:1] != b'.':
                changes.append(('staged', target))
            else:
                changes.append(({b'M': 'modified', b'D': 'deleted', b'A': 'intent-to-add'}
                                .get(xy[1:], 'changed (%s)' % show(xy)), target))
        else:
            raise Unproven('`git status` printed an entry this script does not know: %s' % show(field[:40]))
    return untracked, ignored, changes


def same_bytes(real, rel, mode, size, stream):
    """Whether the worktree entry REL is exactly the blob of SIZE bytes now on STREAM, which
    this reads to its end either way: a regular file with those raw bytes and the executable
    bit MODE records, or a symlink whose text they are."""
    info = entry(real, rel)
    path = os.path.join(real, rel)
    if mode == b'120000':
        blob = stream.read(size)
        return info is not None and stat.S_ISLNK(info.st_mode) and os.readlink(path) == blob
    same = (info is not None and stat.S_ISREG(info.st_mode)
            and (NO_EXEC_BIT or bool(info.st_mode & stat.S_IXUSR) == (mode == b'100755')))
    handle = open(path, 'rb') if same else None
    try:
        while size:
            chunk = stream.read(min(size, 1 << 20))
            if not chunk:
                raise Unproven('`git cat-file --batch` ended inside the blob of %s' % show(rel))
            size -= len(chunk)
            same = same and handle.read(len(chunk)) == chunk
        return same and handle.read(1) == b''
    finally:
        if handle:
            handle.close()


def differing(real, blobs):
    """The tracked paths in BLOBS [(mode, blob id, path)] whose worktree entry is not exactly
    their blob, read through one `git cat-file --batch`."""
    out = []
    with subprocess.Popen(['git', '--no-optional-locks', 'cat-file', '--batch'], cwd=real, env=ENV,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as batch:
        for mode, oid, rel in blobs:
            try:
                os.write(batch.stdin.fileno(), oid + b'\n')  # unbuffered: nothing left to fail at close
                header = batch.stdout.readline().split()
            except BrokenPipeError:
                header = []
            if len(header) != 3:
                raise Unproven('`git cat-file --batch` printed %s for %s' % (show(b' '.join(header)), show(rel)))
            if not same_bytes(real, rel, mode, int(header[2]), batch.stdout):
                out.append(rel)
            batch.stdout.read(1)  # the newline after the content
        batch.stdin.close()
    return out


# How Linux lsof names a cwd it cannot read; any other name is a path, whatever it ends with.
LSOF_UNREADABLE = re.compile(rb'/proc/\d+/cwd \((readlink|stat): [^)]*\)')
LSOF_ESCAPES = {b'\\': b'\\', b'b': b'\b', b'f': b'\f', b'n': b'\n', b'r': b'\r', b't': b'\t'}


def lsof_name(value):
    """The bytes an lsof name stands for. lsof (LC_ALL=C) writes a backslash as \\\\, a byte it
    does not print as \\xNN (octal \\NNN accepted too), \\b \\f \\n \\r \\t, and any other control
    byte as ^ and a letter, which a ^ in the name reads as too: a ^, or a backslash that starts
    none of these, cannot be read back exactly, and the listing is not proven."""
    parts = re.split(rb'(\\(?:x[0-9a-fA-F]{2}|[0-3][0-7]{2}|[\\bfnrt]))', value)
    if any(b'\\' in part or b'^' in part for part in parts[::2]):
        raise Unproven('`lsof` printed a name this script cannot read back exactly: %s' % show(value))
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            out.append(part)
        elif part[1:] in LSOF_ESCAPES:
            out.append(LSOF_ESCAPES[part[1:]])
        else:
            out.append(bytes([int(part[2:], 16) if part[1:2] == b'x' else int(part[1:], 8)]))
    return b''.join(out)


def parse_lsof(out):
    """{pid: cwd} and the number of processes listed without a readable cwd, from the output
    of `lsof -a -d cwd -F pn`: a `p<pid>` record per process, then its `n<path>` record (macOS
    lsof also prints an `fcwd` record between them), read back by lsof_name. A process whose cwd
    Linux lsof could not read (LSOF_UNREADABLE), or whose name is not an absolute path, counts as
    not inspected; the first is kept as a cwd all the same, so that a worktree of that name is
    never taken for an error."""
    cwds, pids, unseen, pid = {}, [], set(), None
    for line in out.split(b'\n'):
        if not line:
            continue
        tag, value = line[:1], line[1:]
        if tag == b'p' and value.isdigit():
            pid = value
            pids.append(pid)
        elif tag == b'f' and value == b'cwd' and pid is not None:
            continue
        elif tag == b'n' and pid is not None:
            if value.startswith(b'/'):
                cwds[pid] = lsof_name(value)
            if LSOF_UNREADABLE.fullmatch(value):
                unseen.add(pid)
        else:
            raise Unproven('`lsof` printed a record this script does not know: %s' % show(line[:40]))
    return cwds, len(unseen.union(p for p in pids if p not in cwds))


def read_proc(proc):
    """{pid: cwd} from a /proc file system, and how many processes it could not read."""
    cwds, unseen = {}, 0
    for pid in os.listdir(proc):
        if not pid.isdigit():
            continue
        try:
            cwds[pid] = os.readlink(os.path.join(proc, pid, b'cwd'))
        except (FileNotFoundError, ProcessLookupError):
            continue  # it ended
        except OSError:
            # Another user's process, or one of ours made non-dumpable (systemd --user,
            # ssh-agent). Counted and reported, not a keep: every host has some, and requiring
            # them kept every worktree. The quiet period covers a worker hidden this way.
            unseen += 1
    return cwds, unseen


def windows_cwds():
    """{pid: cwd} from the live directory handle in each process's PEB (its
    RTL_USER_PROCESS_PARAMETERS.CurrentDirectory, which MSYS updates too), and how many
    processes could not be read: another
    user's, an elevated or protected one, one that ended while it was read. A 32-bit process is
    read through its 32-bit PEB. The layout read is the one every Windows since XP keeps."""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    ntdll = ctypes.WinDLL('ntdll')
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.DuplicateHandle.argtypes = (wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                         ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                                         wintypes.BOOL, wintypes.DWORD)
    kernel32.GetFinalPathNameByHandleW.argtypes = (wintypes.HANDLE, wintypes.LPWSTR,
                                                  wintypes.DWORD, wintypes.DWORD)
    kernel32.ReadProcessMemory.argtypes = (wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                           ctypes.POINTER(ctypes.c_size_t))
    kernel32.IsWow64Process.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL))
    ntdll.NtQueryInformationProcess.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG,
                                                ctypes.c_void_p)
    size = 4096
    while True:
        pids, used = (wintypes.DWORD * size)(), wintypes.DWORD()
        if not kernel32.K32EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(used)):
            raise Unproven('EnumProcesses failed (Windows error %d)' % ctypes.get_last_error())
        if used.value < ctypes.sizeof(pids):
            break
        size *= 2

    def read(handle, address, length):
        buffer, done = ctypes.create_string_buffer(length), ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(handle, ctypes.c_void_p(address), buffer, length, ctypes.byref(done)) \
                or done.value != length:
            raise OSError('ReadProcessMemory')
        return buffer.raw

    cwds, unseen = {}, 0
    for pid in pids[:used.value // 4]:
        if pid == 0:  # the idle process: no user space
            continue
        handle = kernel32.OpenProcess(0x0450, False, pid)  # QUERY_INFORMATION | VM_READ | DUP_HANDLE
        if not handle:
            unseen += 1
            continue
        try:
            wow = wintypes.BOOL()
            if not kernel32.IsWow64Process(handle, ctypes.byref(wow)):
                raise OSError('IsWow64Process')
            if wow:
                peb = ctypes.c_ulonglong()
                if ntdll.NtQueryInformationProcess(handle, 26, ctypes.byref(peb), 8, None):
                    raise OSError('ProcessWow64Information')
                params = int.from_bytes(read(handle, peb.value + 0x10, 4), 'little')
                directory = int.from_bytes(read(handle, params + 0x2c, 4), 'little')
            else:
                basic = (ctypes.c_ulonglong * 6)()  # PROCESS_BASIC_INFORMATION: PebBaseAddress is [1]
                if ntdll.NtQueryInformationProcess(handle, 0, basic, ctypes.sizeof(basic), None):
                    raise OSError('ProcessBasicInformation')
                params = int.from_bytes(read(handle, basic[1] + 0x20, 8), 'little')
                directory = int.from_bytes(read(handle, params + 0x48, 8), 'little')
            # Resolving the PEB's pathname follows a junction's CURRENT target, which may
            # have changed since the process entered it. The held handle still names its cwd.
            duplicate = wintypes.HANDLE()
            if not kernel32.DuplicateHandle(handle, directory, kernel32.GetCurrentProcess(),
                                             ctypes.byref(duplicate), 0, False, 2):
                raise OSError('DuplicateHandle')
            try:
                name = ctypes.create_unicode_buffer(32768)
                length = kernel32.GetFinalPathNameByHandleW(duplicate, name, len(name), 0)
                if not 0 < length < len(name):
                    raise OSError('GetFinalPathNameByHandleW')
                cwd = name.value
            finally:
                kernel32.CloseHandle(duplicate)
            if cwd.startswith('\\\\?\\UNC\\'):
                cwd = '\\\\' + cwd[8:]
            elif cwd.startswith('\\\\?\\'):
                cwd = cwd[4:]
            cwds[str(pid).encode()] = os.fsencode(cwd)
        except (OSError, UnicodeDecodeError):
            unseen += 1
        finally:
            kernel32.CloseHandle(handle)
    return cwds, unseen


def process_cwds(proc):
    """({pid: cwd}, how many processes could not be inspected, where the listing came from).
    /proc where it lists this process with its own working directory, else lsof on the same
    terms: a listing in which this script cannot find itself does not match this platform, and
    is not proven."""
    me, here = str(os.getpid()).encode(), os.getcwdb()

    def sees_me(cwds):
        return me in cwds and os.path.realpath(cwds[me]) == os.path.realpath(here)

    if os.name == 'nt':
        cwds, unseen = windows_cwds()
        if not sees_me(cwds):
            raise Unproven('the Windows process listing does not show this process with its working directory')
        return cwds, unseen, 'the Windows process table'
    tried = []
    try:
        cwds, unseen = read_proc(proc)
        if sees_me(cwds):
            return cwds, unseen, '/proc'
        tried.append('/proc does not show this process')
    except OSError as error:
        tried.append('no /proc (%s)' % error.strerror)
    exe = shutil.which('lsof')
    if not exe:
        raise Unproven('%s, and no lsof here' % '; '.join(tried))
    result = subprocess.run([exe, '-a', '-d', 'cwd', '-F', 'pn'], capture_output=True,
                            stdin=subprocess.DEVNULL, env=dict(os.environ, LC_ALL='C'))
    errors = [line for line in result.stderr.split(b'\n') if line and not LSOF_WARNINGS.fullmatch(line)]
    # Exit 1 is lsof's "some of it could not be read"; any other status, or a signal (negative),
    # is a listing cut short, whatever it printed.
    if result.returncode not in (0, 1) or result.returncode and errors:
        raise Unproven('%s; `lsof -a -d cwd -F pn` failed (exit %d): %s'
                       % ('; '.join(tried), result.returncode, show(errors[0]) if errors else 'nothing on stderr'))
    cwds, unseen = parse_lsof(result.stdout)
    if not sees_me(cwds):
        raise Unproven('%s; `lsof -a -d cwd -F pn` (exit %d) does not show this process with its working directory'
                       % ('; '.join(tried), result.returncode))
    return cwds, unseen, 'lsof (exit %d)' % result.returncode


def fold(path):
    """PATH (bytes) as macOS compares names: Unicode-normalised and case-folded. Where names are
    compared exactly, this matches more, never less, so it can only keep more."""
    if os.name == 'nt':
        path = path.replace(b'\\', b'/')
    return unicodedata.normalize('NFC', path.decode('utf-8', 'surrogateescape')).casefold()


def within(cwd, root):
    """Whether the working directory CWD is ROOT or inside it, compared folded."""
    cwd, root = fold(cwd), fold(root)
    return cwd == root or cwd.startswith(root + '/')


def tmux_sessions():
    """The tmux session names; none only when tmux is absent or says no server runs."""
    exe = shutil.which('tmux')
    if not exe:
        return set()
    result = subprocess.run([exe, 'list-sessions', '-F', '#{session_name}'], capture_output=True,
                            stdin=subprocess.DEVNULL, env=dict(os.environ, LC_ALL='C'))
    if result.returncode == 0:
        return set(result.stdout.split(b'\n')) - {b''}
    error = result.stderr.strip()
    # tmux's own two answers for "nothing listens on the socket": refused, or no socket file.
    # Permission denied and every other error are not proof of no session.
    if (re.fullmatch(rb'no server running on [^\n]*', error)
            or re.fullmatch(rb'error connecting to [^\n]* \(No such file or directory\)', error)):
        return set()
    raise Unproven('`tmux list-sessions` failed: %s' % (show(error) or 'exit %d' % result.returncode))


def lock_held(gitdir):
    if os.name == 'nt':
        # The gate's holder has its lock file open without write sharing (scripts/check.sh):
        # a fresh open for writing, which shares everything, fails with a sharing violation.
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                         wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        path = os.path.join(gitdir, b'check.lock')
        handle = kernel32.CreateFileW(os.fsdecode(path), 0x40000000, 7, None, 3, 0x00200000, None)
        if handle in (None, wintypes.HANDLE(-1).value):
            error = ctypes.get_last_error()
            if error in (2, 3):  # no lock file, no folder: no gate ever ran here
                return False
            if error == 32:
                return True
            raise Unproven('cannot open the gate lock %s to test it (Windows error %d)' % (show(path), error))
        kernel32.CloseHandle(handle)
        return False
    import fcntl  # here, not at the top: native Windows Python has none
    try:
        fd = os.open(os.path.join(gitdir, b'check.lock'), os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    finally:
        os.close(fd)
    return False


def too_recent(when, ctx, what):
    """A reason when WHEN lies within the quiet period (a time in the future counts)."""
    if when is None or ctx['no_quiet'] or when + ctx['quiet'] * 60 <= ctx['now']:
        return []
    left = when + ctx['quiet'] * 60 - ctx['now']
    return ['quiet period: %s changed %d min ago; it qualifies in %d min (quiet-minutes=%d, a margin, '
            'not a proof)' % (what, max(0, ctx['now'] - when) // 60, -(-left // 60), ctx['quiet'])]


def printable(raw):
    """RAW as text when it is UTF-8 with no control character, else None."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        return None
    return text if text.isprintable() else None


def made_here(log):
    """Whether a HEAD reflog records a commit made in that worktree (WORK)."""
    return any(WORK.match(line.partition(b'\t')[2]) and not line.endswith(b'\tcherry-pick: fast-forward')
               for line in log.split(b'\n'))


def audit(record, ctx):
    """(reasons to keep, facts for the removal). Empty reasons means every clause holds."""
    path = record['worktree']
    real = os.path.realpath(path)
    if real == ctx['main_root']:
        return ['the main worktree'], None
    if real == ctx['own']:
        return ['the worktree this script runs in'], None
    if os.path.dirname(real) != ctx['home']:
        return ['not directly under .claude/worktrees: not the kit\'s to remove'], None
    reasons = []
    if 'unknown' in record:
        reasons.append('`git worktree list` printed a field this script does not know: %s'
                       % names(record['unknown']))
    if 'locked' in record:
        reasons.append('locked (git worktree lock)%s' % (': ' + show(record['locked']) if record['locked'] else ''))
    if 'prunable' in record or not os.path.isdir(real):
        return reasons + ['missing or prunable: its folder is gone or no longer its worktree; '
                          '`git worktree prune` is the owner\'s call'], None
    # A folder that is not its own worktree resolves elsewhere: its .git file gone, to the MAIN
    # repository, and every git command below would judge main; a `git init` in it, to a
    # repository of its own that `git worktree remove` would delete.
    top, common = git(real, 'rev-parse', '--show-toplevel', '--git-common-dir').stdout.split(b'\n')[:2]
    if os.path.realpath(top) != real or os.path.realpath(os.path.join(real, common)) != ctx['common']:
        return reasons + ['its folder is not its own worktree: git in it reaches %s' % show(os.path.realpath(top))], None
    if reasons and not ctx['all']:
        return reasons, None
    branch = record.get('branch')
    if branch is None:
        return reasons + ['detached HEAD: remove it by hand (only a branch keeps its commits once it is gone)'], None
    if printable(real) is None or printable(short(branch)) is None:
        return reasons + ['its path or branch name is not printable UTF-8: the command that brings it back '
                          'could not be printed'], None
    facts = {'real': real, 'name': os.path.basename(real), 'head': record.get('HEAD', b''),
             'branch': branch, 'delete': [], 'identical': 0, 'disposable': 0, 'bytes': 0,
             'pin': [], 'saved': None, 'holders': {}}
    gitdir = facts['gitdir'] = git(real, 'rev-parse', '--absolute-git-dir').stdout.rstrip(b'\n')
    tracked = facts['tracked'] = set()
    seen = {}

    def finished():
        try:
            with open(os.path.join(gitdir, b'logs', b'HEAD'), 'rb') as handle:
                log = handle.read()
        except FileNotFoundError:
            log = b''
        if not made_here(log):
            return ['no commit was made in this worktree (its own HEAD reflog records none): a worker that '
                    'has not started, or one that only fast-forwarded']
        if git(real, 'merge-base', '--is-ancestor', facts['head'], ctx['main_ref'], codes=(0, 1)).returncode:
            return ['its branch is not merged: %s is not in %s' % (show(facts['head'][:12]), show(short(ctx['main_ref'])))]
        return []

    def quiet_gitdir():
        return too_recent(max(changed(info) for _, info, _, _ in walk(gitdir, mount_points(ctx['mountinfo']))), ctx, 'its git directory')

    def operations():
        found = [op for op in OPERATIONS if os.path.lexists(os.path.join(gitdir, op))]
        return ['an operation is in progress: %s' % names(found)] if found else []

    def idle():
        # Read afresh every time, never cached: a run audits worktree after worktree for minutes,
        # and remove() asks again right before it deletes.
        out = []
        if lock_held(gitdir):
            out.append('in use: the gate holds its lock (%s)' % show(os.path.join(gitdir, b'check.lock')))
        if facts['name'] in tmux_sessions():
            out.append('in use: a tmux session is named %s' % show(facts['name']))
        if not ctx['assume_idle']:
            try:
                cwds, ctx['unseen'], ctx['source'] = process_cwds(ctx['proc'])
            except Unproven as error:
                return out + ['cannot see which processes work in it (%s); if none does, run by hand: '
                              'scripts/clean_worktrees.sh --apply --assume-idle' % error]
            inside = sorted(pid.decode() for pid, cwd in cwds.items() if within(cwd, real))
            if inside:
                out.append('in use: process %s works inside it' % ', '.join(inside))
        return out

    def history():
        # Another ref backend keeps this worktree's refs where the walk below does not look.
        backend = git(real, 'config', '--get', 'extensions.refStorage', codes=(0, 1)).stdout.strip()
        if backend not in (b'', b'files'):
            return ['its refs are stored by the %s backend, which this script does not read' % show(backend)]
        config = os.path.join(gitdir, b'config.worktree')
        if os.path.exists(config) and os.path.getsize(config) > 0:
            return ['it has its own config (%s)' % show(config)]
        # Another object format is a KeyError: not proven, kept.
        hexlen = {b'sha1': 40, b'sha256': 64}[git(real, 'rev-parse', '--show-object-format').stdout.strip()]
        # Either case: git reads an id written in upper case too.
        token = re.compile(rb'(?<![0-9a-fA-F])[0-9a-fA-F]{%d}(?![0-9a-fA-F])' % hexlen)
        holders = facts['holders'] = {}
        facts['pin'] = []
        for rel, info, is_dir, mount in walk(gitdir, mount_points(ctx['mountinfo'])):
            # git removes its git directory recursively too.
            if mount:
                return ['its git directory holds a mount point: what git would delete under it is not the '
                        'worktree\'s: %s' % show(rel or b'. (the folder itself)')]
            if is_dir or rel in NO_HISTORY:
                continue
            if not stat.S_ISREG(info.st_mode):
                return ['its git directory holds %s, not a regular file' % show(rel)]
            try:
                with open(os.path.join(gitdir, rel), 'rb') as handle:
                    data = handle.read()
            except OSError as error:
                return ['cannot read %s in its git directory (%s)' % (show(rel), error.strerror)]
            if b'\0' in data:
                return ['its git directory holds %s, a binary file this script cannot read for ids' % show(rel)]
            # The same holder in any listing order: a ref before its reflog, then by name.
            for oid in token.findall(data):
                old = holders.get(oid.lower())
                if old is None or (rel.startswith(b'logs/'), rel) < (old.startswith(b'logs/'), old):
                    holders[oid.lower()] = rel
        if not holders:
            return []
        # Held: what the refs of the shared repository point at (main's branch, its branch,
        # refs/kit/saved/*), read from the main worktree, as this worktree's own refs
        # (refs/worktree/*, refs/bisect/*) go with it. No reflog: `git branch -d` deletes the
        # branch's, so an amended, reset or rebased-away tip is saved like any other. No
        # remote-tracking ref: a later `git fetch --prune` drops it. Nor main's own per-worktree
        # refs, which `git bisect reset` or a finished rebase there deletes.
        refs = git(ctx['main_root'], 'for-each-ref', '--format=%(objectname) %(refname)').stdout.split(b'\n')
        held = set(line.split(b' ')[0] for line in refs if line and not line.split(b' ')[1].startswith(
            (b'refs/remotes/', b'refs/worktree/', b'refs/bisect/', b'refs/rewritten/')))
        # Only an id git calls missing is dropped; every other goes to rev-list, which fails on
        # anything it cannot walk.
        kinds = dict(line.split(b' ', 1) for line in git(
            real, 'cat-file', '--batch-check=%(objectname) %(objecttype)',
            stdin=b''.join(oid + b'\n' for oid in sorted(holders))).stdout.split(b'\n') if line)
        # `rev-list --objects <tree> ^<commit>` lists a tree the commit holds too: for a tree or a
        # blob, held cannot be told from not held.
        plain = [oid for oid in sorted(holders) if kinds.get(oid) in (b'tree', b'blob')]
        if plain:
            return ['%s is a tree or blob id (%s): reachability is checked for commits only; check and remove it '
                    'by hand' % (show(plain[0][:12]), show(holders[plain[0]]))]
        present = [oid for oid in sorted(holders) if kinds.get(oid) != b'missing']
        listed = set(line.split(b' ')[0] for line in git(real, 'rev-list', '--objects', '--stdin', stdin=b''.join(
            oid + b'\n' for oid in present) + b''.join(b'^' + oid + b'\n' for oid in sorted(held))).stdout.split(b'\n'))
        loose = [oid for oid in present if oid in listed]
        # A commit nothing else holds is saved (remove() pins it to a ref) and covers what it
        # reaches; anything else not held keeps the worktree.
        other = [oid for oid in loose if kinds.get(oid) != b'commit']
        if other:
            return ['%s, a %s, is held only by its git directory (%s); check and remove it by hand'
                    % (show(other[0][:12]), show(kinds.get(other[0], b'?')), show(holders[other[0]]))]
        # Only the commits no other of them reaches: a pin holds what its commit reaches.
        facts['pin'] = sorted(git(real, 'merge-base', '--independent', *loose).stdout.split()) if loose else []
        # Not the branch name, which another worktree may reuse; its git directory's name with
        # every byte but a letter, a digit, - and _ percent-encoded, so no name is refused as a
        # ref, cut to 64 bytes so that the folder name stays under the 255 a file system allows,
        # and a hash of the whole name, which the log holds.
        base = os.path.basename(gitdir)
        name = re.sub(rb'[^A-Za-z0-9_-]', lambda m: b'%%%02X' % m.group()[0], base)[:64]
        facts['saved'] = b'refs/kit/saved/%s-%s-%s' % (name, hashlib.sha256(base).hexdigest()[:12].encode(), ctx['stamp'])
        return []

    def contents():
        out = []
        seen['status'] = untracked, ignored, changes = status(real)
        kinds = {}
        for kind, rel in changes:
            kinds.setdefault(kind, []).append(rel)
        for kind in sorted(kinds):
            out.append('tracked change, %s: %s' % (kind, names(kinds[kind])))
        if out and not ctx['all']:
            return out
        blobs, links, stages = [], [], []
        for field in git(real, 'ls-files', '-z', '-s').stdout.split(b'\0'):
            if not field:
                continue
            meta, _, rel = field.partition(b'\t')
            mode, oid, stage = meta.split(b' ')
            tracked.add(rel)
            if stage != b'0':
                stages.append(rel)
            elif mode == b'160000':
                links.append(rel)
            else:
                blobs.append((mode, oid, rel))
        if stages:
            out.append('an unresolved index: %s' % names(set(stages)))
        if links:
            out.append('a submodule, whose state this script cannot judge: %s' % names(links))
        if git(real, *STAT, 'diff-index', '--cached', '--quiet', 'HEAD', '--', codes=(0, 1)).returncode:
            out.append('its index differs from its HEAD commit (a staged change)')
        differ = differing(real, blobs)
        if differ:
            out.append('tracked file not byte for byte what its index records (an edit git\'s stat cache, a '
                       'filter or a line-ending conversion hides, or its executable bit): %s' % names(differ))
        return out

    def files():
        out = []
        untracked, ignored, _ = seen.get('status') or status(real)
        loose = [rel for rel in untracked if disposable(rel, ctx['disposable'])]
        if loose:
            out.append('untracked and not ignored inside a disposable folder (`git worktree remove` refuses '
                       'them; ignore that folder in .gitignore): %s' % names(loose))
        unique, odd, alias, nested, mounted, foreign, suggest, recent = [], [], [], [], [], [], set(), None
        # A mount point in it, or the folder itself: `git worktree remove` deletes what is under
        # it, which is not the worktree's (another device, or a folder bound there from elsewhere).
        ctx['mounts'] = mount_points(ctx['mountinfo'])
        # What each tracked path IS on disk: on a file system that ignores case or Unicode form
        # (macOS), a tracked `a` renamed `A` passes every check by its old name, and the walk
        # meets it under a name the index does not hold.
        ids = set((i.st_dev, i.st_ino) for i in (entry(real, rel) for rel in tracked) if i is not None)
        for rel, info, is_dir, mount in walk(real, ctx['mounts']):
            recent = max(recent or 0, changed(info))
            if mount:
                foreign.append(rel or b'. (the folder itself)')
                continue
            if not is_dir and fold(rel).startswith(fold(b'.claude/worktrees/')):
                nested.append(rel)
                continue
            if disposable(rel + b'/x' if is_dir else rel, ctx['disposable']):
                if not is_dir:
                    facts['bytes'] += info.st_size
                    facts['disposable'] += info.st_size
                continue
            if is_dir:
                continue
            facts['bytes'] += info.st_size
            if rel in tracked:
                continue
            if (info.st_dev, info.st_ino) in ids:
                alias.append(rel)
            elif not stat.S_ISREG(info.st_mode):
                odd.append(rel)
            elif not copy_in(ctx, real, rel):
                unique.append(rel)
                if rel in ignored and b'/' in rel:
                    suggest.add(rel.split(b'/')[0])
            elif below_mount(ctx, rel):
                mounted.append(rel)
            else:
                facts['identical'] += 1
                facts['delete'].append(rel)
        if foreign:
            out.append('holds a mount point: what git would delete under it is not the worktree\'s: %s' % names(foreign))
        if nested:
            out.append('inside .claude/worktrees of it, which this script does not judge: %s' % names(nested))
        if alias:
            out.append('a case alias of a tracked file, or another link to one (the same file on disk), under a name '
                       'the index does not hold: %s' % names(alias))
        if odd:
            out.append('not a regular file (a symlink, FIFO, socket, device or nested repository), outside '
                       'a disposable folder: %s' % names(odd))
        if unique:
            out.append('files with no identical copy in main, outside a disposable folder: %s' % names(unique))
        if mounted:
            out.append('its copy in main is below a mount point: a mount inside main is not main: %s' % names(mounted))
        if suggest:
            out.append('if these folders hold only build output, consider listing them in %s: %s'
                       % (show(DISPOSABLE_FILE), names(suggest)))
        return out + too_recent(recent, ctx, 'a file in it')

    for check in (finished, quiet_gitdir, operations, idle, history, contents, files):
        reasons.extend(check())  # an error is a keep: main() catches it
        if reasons and not ctx['all']:
            break
    facts['history'], facts['idle'] = history, idle  # remove() asks both again
    return reasons, facts


def saves(facts):
    """The report line naming the commits a removal saves (every one is in the log)."""
    pins = ['%d=%s (%s)' % (n, show(oid[:12]), show(facts['holders'][oid])) for n, oid in enumerate(facts['pin'], 1)]
    more = len(pins) - CAP
    return '         saves what only its git directory holds, as %s/<n>: %s%s' % (
        show(facts['saved']), ', '.join(pins[:CAP]), ' and %d more' % more if more > 0 else '')


def log_line(ctx, fields):
    """Append FIELDS, after the time, as one tab-separated line of the removal log, on disk when
    this returns; an OSError when it cannot."""
    with open(ctx['log'], 'ab') as log:
        if log.tell() == 0:
            log.write(LOG_HEADER.encode())
        log.write(('\t'.join([datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                               'run=%s' % ctx['run']] + fields)
                   + '\n').encode('utf-8', 'backslashreplace'))
        log.flush()
        os.fsync(log.fileno())


def remove(record, facts, ctx, shown, announce):
    """'removed', 'kept' (nothing changed but saved refs), or 'partly' (identical copies deleted,
    or `git worktree remove` failed, which may have deleted files first). The intent line is
    logged first, then ANNOUNCE (the lines about this removal) is printed; the outcome line is
    logged before anything about the outcome is printed, and the outcome is what happened, never
    whether a line could be printed. SIGNALS are caught meanwhile: one that comes stops it at the
    next step, reported like a failure."""
    saved = [b'%s/%d' % (facts['saved'], n) for n in range(1, len(facts['pin']) + 1)]
    try:
        log_line(ctx, ['intent', show(facts['real']), show(facts['branch']), show(facts['head']),
                       show(ctx['main_head']), 'gitdir=%s' % show(facts['gitdir']),
                       'identical_files=%d' % facts['identical'], 'disposable_bytes=%d' % facts['disposable']]
                 + ['saved=%s=%s' % (show(ref), show(oid)) for ref, oid in zip(saved, facts['pin'])]
                 + ['delete=%s' % show(rel) for rel in facts['delete']])
    except OSError as error:
        say('keep   %s' % show(shown))
        say('         - cannot write the removal log %s (%s): nothing is saved or deleted without its record'
            % (show(ctx['log']), error))
        return 'kept'
    for text in announce:
        say(text)
    deleted, failed = [], []
    caught = {number: signal.signal(number, lambda number, frame: STOP.append(number)) for number in SIGNALS}
    try:
        try:
            why = removal(record, facts, ctx, saved, deleted, failed)
        except Exception as error:  # a keep, like an error in the audit
            why = 'not proven: %s' % (error or type(error).__name__)
        outcome = 'removed' if why is None else 'partly' if deleted or failed else 'kept'
        try:
            log_line(ctx, ['outcome', show(facts['real']), 'removed' if why is None else 'possibly-modified' if failed
                           else 'partly-modified' if deleted else 'kept']
                     + ([' '.join(why.split())] if why else []) + ['deleted=%s' % show(rel) for rel in deleted])
        except OSError as error:
            # What happened stands; the run stops after this worktree and fails (main()).
            ctx['unlogged'] = True
            say('         cannot write the outcome to the removal log %s (%s); its intent line is there'
                % (show(ctx['log']), error))
        if outcome == 'removed':
            # The branch stays, so this brings back its files at their last commit; not the
            # worktree's ignored files, nor its reflogs.
            say('         this command, run in the main worktree, brings the worktree back:')
            say('           git worktree add %s %s' % (sh_word(facts['real']), sh_word(short(facts['branch']))))
        elif outcome == 'kept':
            say('         stopped: %s; nothing deleted, the worktree stays' % why)
        else:
            say('         stopped: %s' % why)
            if failed:
                possibly(facts, ctx)
            if deleted:
                say('         PARTLY MODIFIED: %d files git does not track were deleted from it, each with a '
                    'byte-identical copy at the same path in the main worktree, which brings it back:' % len(deleted))
                for rel in deleted:
                    say('           %s' % show(rel))
        return outcome
    finally:
        for number, handler in caught.items():
            signal.signal(number, handler)


def possibly(facts, ctx):
    """What a failed `git worktree remove` left (git deletes the folder file by file, then its git
    directory even when that failed), and how each kind of file it may have deleted comes back."""
    real = facts['real']
    try:
        registered = real in [os.path.realpath(r['worktree']) for r in worktrees(ctx['main_root'])]
    except Unproven:
        registered = False
    whole = registered and os.path.isdir(facts['gitdir']) and os.path.isfile(os.path.join(real, b'.git'))
    gone = sum(1 for rel in facts['tracked'] if not os.path.lexists(os.path.join(real, rel)))
    say('         POSSIBLY MODIFIED: `git worktree remove` failed and may have deleted part of it first. Now its '
        'folder %s; it is %s a registered worktree, its git directory is %s.'
        % ('is still there, %d of its %d tracked files gone' % (gone, len(facts['tracked']))
           if os.path.lexists(real) else 'is gone', 'still' if registered else 'no longer',
           'still there' if os.path.isdir(facts['gitdir']) else 'gone'))
    say('         Each file it may have deleted was proven: a tracked file was its commit %s on the branch, which '
        'this command, run in the main worktree, writes back%s:'
        % (show(facts['head'][:12]), '' if whole else ' once what is left of the folder is moved aside'))
    say('           ' + ('git -C %s restore -- .' % sh_word(real) if whole else 'git worktree add %s %s'
                         % (sh_word(real), sh_word(short(facts['branch'])))))
    say('         a file git does not track had a byte-identical copy at the same path in the main worktree; a file '
        'in a disposable folder is build output, which the build makes again.')


def removal(record, facts, ctx, saved, deleted, failed):
    """Save, check again, delete the identical copies git does not track, then let git remove it.
    None when removed, else why it stopped; DELETED lists what was deleted, FAILED is set when
    `git worktree remove` failed. It prints only the command that deletes the SAVED refs."""
    if saved:
        result = subprocess.run(['git', 'update-ref', '--stdin'], cwd=ctx['main_root'], env=ENV, capture_output=True,
                                input=b''.join(b'create %s %s\n' % pair for pair in zip(saved, facts['pin'])))
        if result.returncode != 0:  # one transaction: all of them or none
            return ('cannot save what only its git directory holds: `git update-ref --stdin` failed: %s'
                    % (show(result.stderr.strip()) or 'exit %d' % result.returncode))
        say('         to delete the saved refs once you no longer want them, run in the main worktree:')
        say("           git for-each-ref --format='delete %%(refname)' %s | git update-ref --stdin"
            % sh_word(facts['saved'] + b'/'))
    # Again, now: whether a process came in, and what it holds with the saved refs counted.
    again = facts['idle']() + facts['history']()
    if again or facts['pin']:
        return 'changed since its audit: %s' % '; '.join(again or ['it holds commits not saved'])
    for rel in facts['delete']:
        if STOP:
            return 'interrupted by signal %d' % STOP[0]
        try:
            os.unlink(os.path.join(facts['real'], rel))
        except OSError as error:
            return 'cannot delete the identical copy %s (%s)' % (show(rel), error)
        deleted.append(rel)
    again = facts['idle']()
    if again:
        return 'changed since its audit: %s' % '; '.join(again)
    if STOP:
        return 'interrupted by signal %d' % STOP[0]
    result = subprocess.run(['git', 'worktree', 'remove', record['worktree']], cwd=ctx['main_root'], env=ENV,
                            stdin=subprocess.DEVNULL, capture_output=True)
    if result.returncode != 0:
        failed.append(result.returncode)
        return 'git refused to remove it: %s' % (show(result.stderr.strip()) or 'exit %d' % result.returncode)
    return None


def main():
    global ENV
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--apply', action='store_true', help='remove; without it nothing is changed')
    parser.add_argument('--assume-idle', action='store_true',
                        help='where processes cannot be inspected (no /proc, no lsof), take it that none '
                             'works in a worktree')
    parser.add_argument('--all-reasons', action='store_true',
                        help='run every check on every worktree instead of stopping at the first reason to keep')
    parser.add_argument('--quiet', action='store_true',
                        help='print the removals and one summary line, not each kept worktree (the hook)')
    parser.add_argument('--only', metavar='NAME',
                        help='audit .claude/worktrees/NAME alone, the same way (close_worker.sh)')
    parser.add_argument('--no-quiet', action='store_true',
                        help='with --only: lift the quiet period for that worktree, every other check stays '
                             '(close_worker.sh, once the lead has ended its session)')
    args = parser.parse_args()
    if args.no_quiet and args.only is None:
        parser.error('--no-quiet is accepted only with --only: the post-merge hook never lifts the quiet period')
    if args.only is not None and (args.only in ('', '.', '..') or '/' in args.only):
        parser.error('--only takes the name of one folder under .claude/worktrees')
    # Native Windows reads the gate's lock and the processes' working directories its own way
    # (lock_held, windows_cwds). Any other host without fcntl has neither proof: one line,
    # nothing touched.
    if os.name != 'nt' and (os.name != 'posix' or importlib.util.find_spec('fcntl') is None):
        say('clean_worktrees: NOT RUN on this platform: liveness cannot be proven here (no /proc, '
            'no lsof); every worktree kept')
        return 0
    # CLEAN_WORKTREES_NOW, CLEAN_WORKTREES_PROC and CLEAN_WORKTREES_MOUNTINFO are for the tests:
    # a clock they can move instead of ageing files (a ctime cannot be set back), and a /proc and
    # a mount table they can build. Each is said on every run: exported by mistake, it would end
    # the quiet period, or hide a process or a mount, unseen.
    clock = os.environ.get('CLEAN_WORKTREES_NOW')
    for name, what in (('CLEAN_WORKTREES_NOW', 'the quiet period is measured against %s, not the clock'),
                       ('CLEAN_WORKTREES_PROC', 'processes are read from %s, not /proc'),
                       ('CLEAN_WORKTREES_MOUNTINFO', 'the mount table is read from %s, not /proc/self/mountinfo')):
        if os.environ.get(name):
            say('clean_worktrees: %s is set: %s' % (name, what % os.environ[name]))
    ENV = git_env()
    here = os.getcwdb()
    records = worktrees(here)
    if 'bare' in records[0]:
        raise Unproven('the main repository is bare; nothing here is the kit\'s to remove')
    if 'branch' not in records[0]:
        say('clean_worktrees: nothing removed: the main worktree\'s HEAD is detached, and a worktree is '
            'finished only once its branch is in the main worktree\'s branch')
        return
    main_root = os.path.realpath(records[0]['worktree'])
    common = os.path.realpath(git(here, 'rev-parse', '--git-common-dir').stdout.rstrip(b'\n'))
    entries, refused, quiet = read_disposable(main_root)
    ctx = {'main_root': main_root, 'home': os.path.join(main_root, b'.claude', b'worktrees'),
           'main_head': records[0].get('HEAD', b''), 'main_ref': records[0]['branch'], 'common': common,
           'own': os.path.realpath(git(here, 'rev-parse', '--show-toplevel').stdout.rstrip(b'\n')),
           'disposable': entries, 'quiet': quiet, 'unseen': None, 'source': None,
           'mountinfo': os.fsencode(os.environ.get('CLEAN_WORKTREES_MOUNTINFO', '/proc/self/mountinfo')),
           'stamp': datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ').encode(),
           'unlogged': False,
           'now': float(clock or time.time()),
           'proc': os.fsencode(os.environ.get('CLEAN_WORKTREES_PROC', '/proc')),
           'assume_idle': args.assume_idle, 'all': args.all_reasons, 'no_quiet': args.no_quiet,
           'log': os.path.join(common, b'kit-worktree-removals.log')}
    ctx['run'] = '%s-%d' % (ctx['stamp'].decode(), os.getpid())
    for line, why in refused:
        say('clean_worktrees: refused %s line %s %s' % (show(DISPOSABLE_FILE), show(line), why))
    if args.only is not None:
        only = os.path.join(ctx['home'], os.fsencode(args.only))
        records = [record for record in records if os.path.realpath(record['worktree']) == only]
        shown = show(os.path.join(b'.claude', b'worktrees', os.fsencode(args.only)))
        if not records:
            say('clean_worktrees: no worktree at %s' % shown)
        elif args.no_quiet:
            say('clean_worktrees: --no-quiet: the quiet period is not applied to %s' % shown)
    removed = kept = partly = freed = 0
    gone = []
    for record in records:
        shown = os.path.realpath(record['worktree'])
        if shown.startswith(main_root + os.sep.encode()):
            shown = shown[len(main_root) + 1:]
        try:
            reasons, facts = audit(record, ctx)
        except Exception as error:  # any error is a keep, never a crash halfway through a run
            reasons, facts = ['not proven: %s' % (error or type(error).__name__)], None
        if reasons:
            kept += 1
            if not args.quiet:
                say('keep   %s' % show(shown))
                for reason in reasons:
                    say('         - %s' % reason)
            continue
        announce = ['remove %s (branch %s, %d identical files, %d disposable bytes, %d bytes)'
                    % (show(shown), show(short(facts['branch'])), facts['identical'], facts['disposable'],
                       facts['bytes'])] + ([saves(facts)] if facts['pin'] else [])
        if args.apply:
            outcome = remove(record, facts, ctx, shown, announce)
        else:
            outcome = 'removed'
            for text in announce:
                say(text)
        if outcome == 'removed':
            removed += 1
            freed += facts['bytes']
            gone.append(short(facts['branch']))
        elif outcome == 'partly':
            partly += 1
        else:
            kept += 1
        if STOP:
            say('clean_worktrees: stopped by signal %d; the worktrees after this one were not looked at' % STOP[0])
            break
        if ctx['unlogged']:
            say('clean_worktrees: stopped: the outcome of the last removal could not be written to the removal log; '
                'the worktrees after it were not looked at')
            break
    if ctx['source'] and not args.quiet:
        say('clean_worktrees: processes listed by %s, %d could not be inspected (another user\'s, or not '
            'readable; lsof on macOS does not list another user\'s at all); the quiet period covers a '
            'worker this scan cannot see' % (ctx['source'], ctx['unseen']))
    elif ctx['source'] and removed:
        say('clean_worktrees: %d processes could not be inspected; the quiet period covers a worker this '
            'scan cannot see' % ctx['unseen'])
    if args.apply:
        say('clean_worktrees: removed %d, kept %d, %sfreed %d bytes; log: %s%s'
            % (removed, kept, 'PARTLY MODIFIED %d (above: what may be gone, and how it comes back), '
               % partly if partly else '', freed, show(ctx['log']),
               '; the reasons: scripts/clean_worktrees.sh' if args.quiet and kept else ''))
        if gone:
            say('clean_worktrees: branches kept, their worktrees removed: %s' % names(gone))
            say('clean_worktrees: to delete merged branches yourself: `git branch --merged %s` lists them, '
                '`git branch -d <name>` deletes one, and its reflog with it: the old tips a removal saved are '
                'kept by the refs under refs/kit/saved/' % sh_word(short(ctx['main_ref'])))
    else:
        say('clean_worktrees: dry run: would remove %d, keep %d, free %d bytes; to apply: '
            'scripts/clean_worktrees.sh --apply%s%s%s'
            % (removed, kept, freed, ' --assume-idle' if args.assume_idle else '',
               ' --only=' + sh_word(os.fsencode(args.only)) if args.only is not None else '',
               ' --no-quiet' if args.no_quiet else ''))
    return 1 if partly or STOP or ctx['unlogged'] else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Unproven, OSError, ValueError) as error:
        say('clean_worktrees: stopped, nothing further removed: %s' % error)
        sys.exit(1)
