#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Remove the finished worktrees under .claude/worktrees, and only what is proven safe to lose.

Run through scripts/clean_worktrees.sh, which says why this exists. With no option it is a dry
run; --apply removes. It never deletes a branch: the branch keeps every commit it had whatever
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
     directory inside it (/proc on Linux, lsof elsewhere), no tmux session has its name, the
     gate's lock is free;
  f. nothing only its git directory holds: removal destroys that directory, so every object id
     in every file of it (both columns of every reflog line, every ref, every pseudo-ref, any
     file this script does not know), NO_HISTORY excepted, names an object reachable from the
     main branch (which holds its branch, by b), or no object at all; the files ref backend; no per-worktree
     config;
  g. tracked content, by bytes: no change `git status` reports with the stat settings forced to
     their defaults; the index equals HEAD's tree; every tracked path is, in the worktree,
     exactly the blob the index records (raw bytes, no filter or line-ending conversion, the
     same executable bit; a symlink's text); no unresolved entry, no submodule;
  h. every file git does not track is inside a directory .claude/worktree-disposable lists, or
     a regular file whose byte-identical copy is at the same path in the main worktree; nothing
     anywhere in it, disposable folders included, changed within quiet-minutes.

Proven: a, b, d, f, g, h's accounting. The quiet period (c, h) is a margin, not a proof: it
covers a worker whose process the scan in e cannot see. Not guarded, by the owner's decision:
a process that changes a worktree between its audit and its removal, files planted to attack
this script, and a SIGKILL between two removal steps. Lost with a removal and never restored:
the ignored files in disposable folders, and the worktree's own reflogs (every commit they name
is in its branch or main, by f).

The filesystem is walked on its own, never through a symlink, and every entry that is not
tracked must be accounted for: `git status` does not list a FIFO, a socket or a device, and
`git worktree remove` deletes them and every ignored file without asking.

Removal order: the log record (flushed), the identical copies git does not track, `git worktree
remove` without --force (git's own check, independent of this one).
"""
import argparse
import datetime
import fcntl
import filecmp
import os
import re
import shutil
import stat
import subprocess
import sys
import time

DISPOSABLE_FILE = b'.claude/worktree-disposable'
# Places that hold work: refused as a disposable entry, and a NAME entry does not match below them.
REFUSED = {b'.git', b'docs', b'.claude', b'.myagentkit', b'scripts'}
# Files and folders in a worktree's git directory while an operation is unfinished.
OPERATIONS = (b'MERGE_HEAD', b'CHERRY_PICK_HEAD', b'REVERT_HEAD', b'BISECT_START',
              b'rebase-merge', b'rebase-apply', b'sequencer')
# HEAD reflog subjects git writes when it made a NEW commit in that worktree: commit (also
# amend, initial, and merge: a conflicted merge concluded by `git commit`), cherry-pick,
# revert, am, and a rebase step that wrote a commit. Not counted: a fast-forward (checkout,
# reset, `merge: Fast-forward`, `cherry-pick: fast-forward`, a rebase that only moved), and a
# merge made by `git merge` or `git pull` alone, which joins work made elsewhere.
WORK = re.compile(rb'(commit( \([a-z]+\))?|cherry-pick|revert|am|rebase \((pick|reword|squash|fixup|continue)\)): ')
# Top-level files of a worktree's git directory that hold no history (f): index, the tracked
# state g verifies by bytes (and binary); check-build.log, the gate's build output, which may
# print any id. Every other file is scanned, the ones that hold no id at all included.
NO_HISTORY = {b'index', b'check-build.log'}
# The warnings lsof prints on stderr when one file system cannot be read; its listing of the
# rest stands (lsof(8), "can't stat()"). Any other stderr line makes a non-zero exit a failure.
LSOF_WARNINGS = re.compile(rb"lsof: WARNING: can't stat\(\) [^\n]*|\s*Output information may be incomplete\.")
QUIET_DEFAULT, QUIET_MIN = 60, 10
CAP = 5


class Unproven(Exception):
    """A check could not be completed; the worktree is kept with this text as its reason."""


def show(path):
    """A path as one printable line: a newline, a control byte or a non-UTF-8 byte escaped."""
    return ''.join(c if c.isprintable() else repr(c)[1:-1] for c in path.decode('utf-8', 'backslashreplace'))


def names(paths):
    paths = sorted(paths)
    more = len(paths) - CAP
    return ', '.join(show(p) for p in paths[:CAP]) + (' and %d more' % more if more > 0 else '')


def short(ref):
    return ref[len(b'refs/heads/'):] if ref.startswith(b'refs/heads/') else ref


def sh_quote(text):
    """TEXT as one word for a POSIX shell: in '...', each ' inside written as '\\''."""
    return "'" + text.replace("'", "'\\''") + "'"


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
STAT = ('-c', 'core.checkStat=default', '-c', 'core.trustctime=true', '-c', 'core.fileMode=true')


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
    """The project's disposable entries, the lines refused, and the quiet period in minutes."""
    try:
        with open(os.path.join(main_root, DISPOSABLE_FILE), 'rb') as handle:
            data = handle.read()
    except FileNotFoundError:
        return [], [], QUIET_DEFAULT
    entries, refused, quiet = [], [], QUIET_DEFAULT
    for line in data.split(b'\n'):
        line = line.strip()
        if not line or line.startswith(b'#'):
            continue
        if line.startswith(b'quiet-minutes'):
            value = re.fullmatch(rb'quiet-minutes=(\d{1,6})', line)
            if value and int(value.group(1)) >= QUIET_MIN:
                quiet = int(value.group(1))
            else:
                refused.append((line, 'quiet-minutes takes a whole number of at least %d; %d applies'
                                % (QUIET_MIN, QUIET_DEFAULT)))
            continue
        entry = line.rstrip(b'/')
        parts = entry.split(b'/')
        # An absolute path has an empty first part.
        if (b'' in parts or b'.' in parts or b'..' in parts
                or REFUSED.intersection(parts)):
            refused.append((line, 'empty, absolute, "..", or a place that holds work: %s'
                            % ', '.join(sorted(r.decode() for r in REFUSED))))
        else:
            entries.append(entry)
    return entries, refused, quiet


def disposable(rel, entries):
    """Whether REL lies inside a disposable directory, compared folder by folder: a NAME entry
    matches a folder of that name with no place that holds work (REFUSED) above it; a PATH
    entry matches its own subtree from the root."""
    folders = rel.split(b'/')[:-1]
    for entry in entries:
        if b'/' in entry:
            parts = entry.split(b'/')
            if folders[:len(parts)] == parts:
                return True
            continue
        for folder in folders:
            if folder in REFUSED:
                break
            if folder == entry:
                return True
    return False


def entry(root, rel):
    """The lstat of ROOT/REL reached through folders only (no symlink on the way), or None."""
    path = root
    parts = rel.split(b'/')
    for part in parts[:-1]:
        path = os.path.join(path, part)
        try:
            if not stat.S_ISDIR(os.lstat(path).st_mode):
                return None
        except OSError:
            return None
    try:
        return os.lstat(os.path.join(path, parts[-1]))
    except OSError:
        return None


def copy_in(main_root, real, rel):
    """Whether MAIN_ROOT holds a regular file at REL, reached without a symlink, with the bytes of REAL/REL."""
    info = entry(main_root, rel)
    return (info is not None and stat.S_ISREG(info.st_mode)
            and filecmp.cmp(os.path.join(real, rel), os.path.join(main_root, rel), shallow=False))


def walk(root):
    """(rel, lstat, is a folder) for every entry under ROOT, the root itself as b'', never
    through a symlink. The worktree's own `.git` file is git's, not content."""
    yield b'', os.lstat(root), True
    stack = [b'']
    while stack:
        folder = stack.pop()
        with os.scandir(os.path.join(root, folder) if folder else root) as entries:
            for item in entries:
                rel = folder + b'/' + item.name if folder else item.name
                if rel == b'.git':
                    continue
                info = item.stat(follow_symlinks=False)
                is_dir = stat.S_ISDIR(info.st_mode)
                if is_dir:
                    stack.append(rel)
                yield rel, info, is_dir


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
            and bool(info.st_mode & stat.S_IXUSR) == (mode == b'100755'))
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


def parse_lsof(out):
    """{pid: cwd} and the number of processes listed without a readable cwd, from the output
    of `lsof -a -d cwd -F pn`: a `p<pid>` record per process, then its `n<path>` record (macOS
    lsof also prints an `fcwd` record between them). Linux lsof names an unreadable cwd as
    `<proc path> (readlink: <error>)`; a name that is not an absolute path counts the same."""
    cwds, pids, pid = {}, [], None
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
            if value.startswith(b'/') and not re.search(rb' \((readlink|stat): [^)]*\)$', value):
                cwds[pid] = value
        else:
            raise Unproven('`lsof` printed a record this script does not know: %s' % show(line[:40]))
    return cwds, sum(1 for p in pids if p not in cwds)


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


def process_cwds(proc):
    """({pid: cwd}, how many processes could not be inspected, where the listing came from).
    /proc where it lists this process with its own working directory, else lsof on the same
    terms: a listing in which this script cannot find itself does not match this platform, and
    is not proven."""
    me, here = str(os.getpid()).encode(), os.getcwdb()

    def sees_me(cwds):
        return me in cwds and os.path.realpath(cwds[me]) == os.path.realpath(here)

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
    if result.returncode != 0 and errors:
        raise Unproven('%s; `lsof -a -d cwd -F pn` failed (exit %d): %s'
                       % ('; '.join(tried), result.returncode, show(errors[0])))
    cwds, unseen = parse_lsof(result.stdout)
    if not sees_me(cwds):
        raise Unproven('%s; `lsof -a -d cwd -F pn` (exit %d) does not show this process with its working directory'
                       % ('; '.join(tried), result.returncode))
    return cwds, unseen, 'lsof (exit %d)' % result.returncode


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


def cached(ctx, key, compute):
    """COMPUTE() once per run; an Unproven result is kept and raised again for every worktree."""
    if key not in ctx['cache']:
        try:
            ctx['cache'][key] = (compute(), None)
        except Unproven as error:
            ctx['cache'][key] = (None, error)
    value, error = ctx['cache'][key]
    if error:
        raise error
    return value


def too_recent(when, ctx, what):
    """A reason when WHEN lies within the quiet period (a time in the future counts)."""
    if when is None or when + ctx['quiet'] * 60 <= ctx['now']:
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
             'branch': branch, 'delete': [], 'identical': 0, 'disposable': 0, 'bytes': 0}
    gitdir = git(real, 'rev-parse', '--absolute-git-dir').stdout.rstrip(b'\n')
    tracked, seen = set(), {}

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
        return too_recent(max(changed(info) for _, info, _ in walk(gitdir)), ctx, 'its git directory')

    def operations():
        found = [op for op in OPERATIONS if os.path.lexists(os.path.join(gitdir, op))]
        return ['an operation is in progress: %s' % names(found)] if found else []

    def idle():
        out = []
        if lock_held(gitdir):
            out.append('in use: the gate holds its lock (%s)' % show(os.path.join(gitdir, b'check.lock')))
        if facts['name'] in cached(ctx, 'tmux', tmux_sessions):
            out.append('in use: a tmux session is named %s' % show(facts['name']))
        if not ctx['assume_idle']:
            try:
                cwds, ctx['unseen'], ctx['source'] = cached(ctx, 'proc', lambda: process_cwds(ctx['proc']))
            except Unproven as error:
                return out + ['cannot see which processes work in it (%s); if none does, run by hand: '
                              'scripts/clean_worktrees.sh --apply --assume-idle' % error]
            inside = sorted(pid.decode() for pid, cwd in cwds.items() if cwd == real or cwd.startswith(real + b'/'))
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
        token = re.compile(rb'(?<![0-9a-fA-F])[0-9a-f]{%d}(?![0-9a-fA-F])' % hexlen)
        holders = {}
        for rel, info, is_dir in walk(gitdir):
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
            for oid in token.findall(data):
                holders.setdefault(oid, rel)
        if not holders:
            return []
        # Only an id git calls missing is dropped; every other goes to rev-list, which fails on
        # anything it cannot walk.
        missing = set(git(real, 'cat-file', '--batch-check=%(objectname) %(objecttype)',
                          stdin=b''.join(oid + b'\n' for oid in sorted(holders))).stdout.split(b'\n'))
        present = [oid for oid in sorted(holders) if oid + b' missing' not in missing]
        # Its branch is in the main branch (b), so what main holds covers both.
        loose = git(real, 'rev-list', '--objects', '--stdin', stdin=b''.join(
            oid + b'\n' for oid in present) + b'^' + ctx['main_ref'] + b'\n').stdout.split()
        if loose:
            return ['%s is held only by its git directory (%s): it is not in %s; check and remove it by '
                    'hand' % (show(loose[0][:12]), show(holders.get(loose[0], b'an object it names')),
                              show(short(ctx['main_ref'])))]
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
        unique, odd, suggest, recent = [], [], set(), None
        for rel, info, is_dir in walk(real):
            recent = max(recent or 0, changed(info))
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
            if not stat.S_ISREG(info.st_mode):
                odd.append(rel)
            elif copy_in(ctx['main_root'], real, rel):
                facts['identical'] += 1
                facts['delete'].append(rel)
            else:
                unique.append(rel)
                if rel in ignored and b'/' in rel:
                    suggest.add(rel.split(b'/')[0])
        if odd:
            out.append('not a regular file (a symlink, FIFO, socket, device or nested repository), outside '
                       'a disposable folder: %s' % names(odd))
        if unique:
            out.append('files with no identical copy in main, outside a disposable folder: %s' % names(unique))
        if suggest:
            out.append('if these folders hold only build output, consider listing them in %s: %s'
                       % (show(DISPOSABLE_FILE), names(suggest)))
        return out + too_recent(recent, ctx, 'a file in it')

    for check in (finished, quiet_gitdir, operations, idle, history, contents, files):
        reasons.extend(check())  # an error is a keep: main() catches it
        if reasons and not ctx['all']:
            break
    return reasons, facts


def remove(record, facts, ctx):
    """Log, delete the identical copies git does not track, then let git remove it. True when removed."""
    path, branch = record['worktree'], facts['branch']
    line = '\t'.join([datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                      show(facts['real']), show(branch), show(facts['head']),
                      show(ctx['main_head']), 'identical_files=%d' % facts['identical'],
                      'disposable_bytes=%d' % facts['disposable']]) + '\n'
    try:
        with open(ctx['log'], 'ab') as log:
            log.write(line.encode())
            log.flush()
            os.fsync(log.fileno())
    except OSError as error:
        print('         stopped: cannot write the removal log %s (%s); nothing deleted' % (show(ctx['log']), error))
        return False
    for rel in facts['delete']:
        try:
            os.unlink(os.path.join(facts['real'], rel))
        except OSError as error:
            print('         stopped: cannot delete the identical copy %s (%s); the worktree stays' % (show(rel), error))
            return False
    result = subprocess.run(['git', 'worktree', 'remove', path], cwd=ctx['main_root'], env=ENV,
                            stdin=subprocess.DEVNULL, capture_output=True)
    if result.returncode != 0:
        print('         stopped: git refused to remove it: %s' % show(result.stderr.strip()))
        return False
    # The branch stays, so this brings back its files at their last commit; not the worktree's
    # ignored files, nor its reflogs.
    print('         this command, run in the main worktree, brings the worktree back:')
    print('           git worktree add %s %s' % (sh_quote(printable(facts['real'])), sh_quote(printable(short(branch)))))
    return True


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
    args = parser.parse_args()
    ENV = git_env()
    here = os.getcwdb()
    records = worktrees(here)
    if 'bare' in records[0]:
        raise Unproven('the main repository is bare; nothing here is the kit\'s to remove')
    if 'branch' not in records[0]:
        print('clean_worktrees: nothing removed: the main worktree\'s HEAD is detached, and a worktree is '
              'finished only once its branch is in the main worktree\'s branch')
        return
    main_root = os.path.realpath(records[0]['worktree'])
    entries, refused, quiet = read_disposable(main_root)
    common = os.path.realpath(git(here, 'rev-parse', '--git-common-dir').stdout.rstrip(b'\n'))
    # CLEAN_WORKTREES_NOW and CLEAN_WORKTREES_PROC are for the tests: a clock they can move
    # instead of ageing files (a ctime cannot be set back), and a /proc they can build.
    ctx = {'main_root': main_root, 'home': os.path.join(main_root, b'.claude', b'worktrees'),
           'main_head': records[0].get('HEAD', b''), 'main_ref': records[0]['branch'], 'common': common,
           'own': os.path.realpath(git(here, 'rev-parse', '--show-toplevel').stdout.rstrip(b'\n')),
           'disposable': entries, 'quiet': quiet, 'cache': {}, 'unseen': None, 'source': None,
           'now': float(os.environ.get('CLEAN_WORKTREES_NOW') or time.time()),
           'proc': os.fsencode(os.environ.get('CLEAN_WORKTREES_PROC', '/proc')),
           'assume_idle': args.assume_idle, 'all': args.all_reasons,
           'log': os.path.join(common, b'kit-worktree-removals.log')}
    for line, why in refused:
        print('clean_worktrees: refused %s line %s (%s)' % (show(DISPOSABLE_FILE), show(line), why))
    removed = kept = freed = 0
    gone = []
    for record in records:
        shown = os.path.realpath(record['worktree'])
        if shown.startswith(main_root + b'/'):
            shown = shown[len(main_root) + 1:]
        try:
            reasons, facts = audit(record, ctx)
        except Exception as error:  # any error is a keep, never a crash halfway through a run
            reasons, facts = ['not proven: %s' % (error or type(error).__name__)], None
        if reasons:
            kept += 1
            if not args.quiet:
                print('keep   %s' % show(shown))
                for reason in reasons:
                    print('         - %s' % reason)
            continue
        print('remove %s (branch %s, %d identical files, %d disposable bytes, %d bytes)'
              % (show(shown), show(short(facts['branch'])), facts['identical'], facts['disposable'], facts['bytes']))
        if not args.apply:
            removed += 1
            freed += facts['bytes']
        elif remove(record, facts, ctx):
            removed += 1
            freed += facts['bytes']
            gone.append(short(facts['branch']))
        else:
            kept += 1
    if ctx['source'] and not args.quiet:
        print('clean_worktrees: processes listed by %s, %d could not be inspected (another user\'s, or not '
              'readable; lsof on macOS does not list another user\'s at all); the quiet period covers a '
              'worker this scan cannot see' % (ctx['source'], ctx['unseen']))
    elif ctx['source'] and removed:
        print('clean_worktrees: %d processes could not be inspected; the quiet period covers a worker this '
              'scan cannot see' % ctx['unseen'])
    if args.apply:
        print('clean_worktrees: removed %d, kept %d, freed %d bytes; log: %s%s'
              % (removed, kept, freed, show(ctx['log']),
                 '; the reasons: scripts/clean_worktrees.sh' if args.quiet and kept else ''))
        if gone:
            print('clean_worktrees: branches kept, their worktrees removed: %s' % names(gone))
            print('clean_worktrees: to delete merged branches yourself: `git branch --merged %s` lists them, '
                  '`git branch -d <name>` deletes one' % show(short(ctx['main_ref'])))
    else:
        print('clean_worktrees: dry run: would remove %d, keep %d, free %d bytes; to apply: '
              'scripts/clean_worktrees.sh --apply%s'
              % (removed, kept, freed, ' --assume-idle' if args.assume_idle else ''))


if __name__ == '__main__':
    try:
        main()
    except (Unproven, OSError, ValueError) as error:
        print('clean_worktrees: stopped, nothing further removed: %s' % error)
        sys.exit(1)
