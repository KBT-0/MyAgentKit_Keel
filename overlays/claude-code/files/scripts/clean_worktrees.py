#!/usr/bin/env python3
"""Remove the finished worktrees under .claude/worktrees, and only what is proven safe to lose.

Run through scripts/clean_worktrees.sh, which says why this exists. With no option it is a dry
run; --apply removes. A worktree is removed only when every check below is PROVEN; a check that
fails, errors, or meets output it does not know keeps the worktree, with the reason printed.

  a. a linked worktree of this repository, physically directly under
     <main worktree>/.claude/worktrees/, not the main worktree, not the one this runs in;
  b. not locked, not prunable, not missing;
  c. no merge, rebase, cherry-pick, revert or bisect in progress, no unresolved index;
  d. its HEAD is an ancestor of the main worktree's HEAD, and a checked-out branch's tip is
     that HEAD (a squash-merged or rebased branch is not: its commits are not in main);
  e. no tracked change, no index entry git would not report (skip-worktree, assume-unchanged),
     no submodule;
  f. every file git does not track is inside a directory .claude/worktree-disposable lists, or
     a regular file whose byte-identical copy is at the same path in the main worktree;
  g. not in use: no process has its working directory inside it, no tmux session has its
     name, the gate's lock in its git directory is not held.

The filesystem is walked on its own, never through a symlink, and every entry that is not
tracked must be accounted for: `git status` does not list a FIFO, a socket or a device, and
`git worktree remove` deletes them and every ignored file without asking.

Removal order: the log record (flushed), the untracked identical copies, `git worktree remove`
without --force (git's own check, independent of this one), `git branch -d` (never -D).
"""
import argparse
import datetime
import fcntl
import filecmp
import os
import shutil
import stat
import subprocess
import sys

DISPOSABLE_FILE = b'.claude/worktree-disposable'
# Places that hold work, refused as a disposable entry (the file's header says the same).
REFUSED = {b'.git', b'docs', b'.claude', b'.myagentkit', b'scripts'}
# Files and folders in a worktree's git directory while an operation is unfinished.
OPERATIONS = (b'MERGE_HEAD', b'CHERRY_PICK_HEAD', b'REVERT_HEAD', b'BISECT_START',
              b'rebase-merge', b'rebase-apply', b'sequencer')
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


def git(cwd, *args, codes=(0,)):
    result = subprocess.run(['git', '--no-optional-locks', *args], cwd=cwd, env=ENV,
                            stdin=subprocess.DEVNULL, capture_output=True)
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
    """The project's disposable entries, and the lines refused as entries."""
    try:
        with open(os.path.join(main_root, DISPOSABLE_FILE), 'rb') as handle:
            data = handle.read()
    except FileNotFoundError:
        return [], []
    entries, refused = [], []
    for line in data.split(b'\n'):
        line = line.strip()
        if not line or line.startswith(b'#'):
            continue
        entry = line.rstrip(b'/')
        parts = entry.split(b'/')
        # An absolute path has an empty first part.
        if (not entry or b'' in parts or b'.' in parts or b'..' in parts
                or REFUSED.intersection(parts)):
            refused.append(line)
        else:
            entries.append(entry)
    return entries, refused


def disposable(rel, entries):
    """Whether REL lies inside a disposable directory: a NAME entry matches any folder above it,
    a path entry matches its own subtree. A trailing '/' marks REL itself as a folder."""
    folder = rel.rpartition(b'/')[0]
    for entry in entries:
        if b'/' in entry:
            if (folder + b'/').startswith(entry + b'/'):
                return True
        elif entry in folder.split(b'/'):
            return True
    return False


def regular(root, rel):
    """Whether ROOT/REL is a regular file reached without a symlink on the way."""
    path = root
    parts = rel.split(b'/')
    for i, part in enumerate(parts):
        path = os.path.join(path, part)
        try:
            mode = os.lstat(path).st_mode
        except OSError:
            return False
        if not (stat.S_ISREG(mode) if i == len(parts) - 1 else stat.S_ISDIR(mode)):
            return False
    return True


def walk(root):
    """(rel, lstat) for every entry under ROOT that is not a folder, never through a symlink.
    The worktree's own `.git` file is git's, not content."""
    stack = [b'']
    while stack:
        folder = stack.pop()
        with os.scandir(os.path.join(root, folder) if folder else root) as entries:
            for entry in entries:
                rel = folder + b'/' + entry.name if folder else entry.name
                if rel == b'.git':
                    continue
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    stack.append(rel)
                else:
                    yield rel, info


def status(path):
    """Untracked and ignored paths, and the tracked changes as (kind, path)."""
    out = git(path, '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false', 'status',
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


def processes_inside(real, proc, assume_idle):
    """A reason when a process works inside REAL, or when that cannot be checked here."""
    try:
        if os.readlink(os.path.join(proc, b'self', b'cwd')) != os.getcwdb():
            raise OSError('self')
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        if assume_idle:
            return []
        return ['cannot see which processes work in it (no /proc here); if none does, run by hand: '
                'scripts/clean_worktrees.sh --apply --assume-idle']
    inside = []
    for pid in pids:
        try:
            cwd = os.readlink(os.path.join(proc, pid, b'cwd'))
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            # Not counted: another user's process, or one of ours made non-dumpable (systemd
            # --user, ssh-agent). Every host has some, so requiring them kept every worktree.
            # The worker's own tooling (its shell, the agent CLI, a tmux pane) is readable.
            continue
        if cwd == real or cwd.startswith(real + b'/'):
            inside.append(pid.decode())
    return ['in use: process %s works inside it' % ', '.join(inside)] if inside else []


def tmux_sessions():
    exe = shutil.which('tmux')
    if not exe:
        return set()
    result = subprocess.run([exe, 'list-sessions', '-F', '#{session_name}'], capture_output=True,
                            stdin=subprocess.DEVNULL, env=dict(os.environ, LC_ALL='C'))
    if result.returncode == 0:
        return set(result.stdout.split(b'\n')) - {b''}
    if b'no server running' in result.stderr or b'error connecting to' in result.stderr:
        return set()
    raise Unproven('`tmux list-sessions` failed: %s' % show(result.stderr.strip()))


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


def audit(record, ctx):
    """(reasons to keep, facts for the removal). Empty reasons means every clause is proven."""
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
        return reasons + ['missing or prunable: its folder is gone; `git worktree prune` is the owner\'s call'], None
    facts = {'real': real, 'name': os.path.basename(real), 'head': record.get('HEAD', b''),
             'branch': record.get('branch'), 'delete': [], 'identical': 0, 'disposable': 0, 'bytes': 0}
    gitdir = git(real, 'rev-parse', '--absolute-git-dir').stdout.rstrip(b'\n')

    def clause(check):
        try:
            reasons.extend(check())
        except Exception as error:  # any error is a keep, never a crash halfway through a run
            reasons.append('not proven: %s' % error)

    def operations():
        found = [op for op in OPERATIONS if os.path.lexists(os.path.join(gitdir, op))]
        return ['an operation is in progress: %s' % names(found)] if found else []

    def merged():
        out = []
        head, branch = facts['head'], facts['branch']
        if branch is not None:
            tip = git(ctx['main_root'], 'rev-parse', '--verify', branch).stdout.strip()
            if tip != head:
                out.append('its branch %s points at %s, not at its HEAD %s'
                           % (show(branch), show(tip[:12]), show(head[:12])))
        code = git(ctx['main_root'], 'merge-base', '--is-ancestor', head, ctx['main_head'],
                   codes=(0, 1)).returncode
        if code == 1:
            out.append('HEAD %s is not in main: unmerged commits, or a squash-merged or rebased branch '
                       '(its own commits are not in main; check and remove it by hand)' % show(head[:12]))
        return out

    tracked = set()

    def index():
        out, odd, links, stages = [], [], [], []
        for field in git(real, 'ls-files', '-z', '-s', '-v').stdout.split(b'\0'):
            if not field:
                continue
            meta, _, rel = field.partition(b'\t')
            tag, mode, _, stage = meta.split(b' ')
            tracked.add(rel)
            if tag != b'H':
                odd.append(rel)
            if mode == b'160000':
                links.append(rel)
            if stage != b'0':
                stages.append(rel)
        if stages:
            out.append('an unresolved index: %s' % names(set(stages)))
        if odd:
            out.append('index entries git does not compare (skip-worktree or assume-unchanged): %s' % names(odd))
        if links:
            out.append('a submodule, whose state this script cannot judge: %s' % names(links))
        return out

    def files():
        out = []
        untracked, ignored, changes = status(real)
        kinds = {}
        for kind, rel in changes:
            kinds.setdefault(kind, []).append(rel)
        for kind in sorted(kinds):
            out.append('tracked change, %s: %s' % (kind, names(kinds[kind])))
        loose = [rel for rel in untracked if disposable(rel, ctx['disposable'])]
        if loose:
            out.append('untracked and not ignored inside a disposable folder (`git worktree remove` refuses '
                       'them; ignore that folder in .gitignore): %s' % names(loose))
        unique, odd, suggest = [], [], set()
        for rel, info in walk(real):
            facts['bytes'] += info.st_size
            if rel in tracked:
                continue
            if disposable(rel, ctx['disposable']):
                facts['disposable'] += info.st_size
            elif not stat.S_ISREG(info.st_mode):
                odd.append(rel)
            elif regular(ctx['main_root'], rel) and filecmp.cmp(
                    os.path.join(real, rel), os.path.join(ctx['main_root'], rel), shallow=False):
                facts['identical'] += 1
                if rel in untracked:
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
        return out

    def idle():
        out = processes_inside(real, ctx['proc'], ctx['assume_idle'])
        if facts['name'] in tmux_sessions():
            out.append('in use: a tmux session is named %s' % show(facts['name']))
        if lock_held(gitdir):
            out.append('in use: the gate holds its lock (%s)' % show(os.path.join(gitdir, b'check.lock')))
        return out

    for check in (operations, merged, index, files, idle):
        clause(check)
    return reasons, facts


def remove(record, facts, ctx):
    """Log, delete the identical untracked copies, then let git remove it. True when removed."""
    path, branch = record['worktree'], facts['branch']
    line = '\t'.join([datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                      show(facts['real']), show(branch) if branch else '(detached)', show(facts['head']),
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
    head = show(facts['head'])
    if branch:
        name = short(branch)
        result = subprocess.run(['git', 'branch', '-d', name], cwd=ctx['main_root'], env=ENV,
                                stdin=subprocess.DEVNULL, capture_output=True)
        if result.returncode != 0:
            print('         branch %s kept: git branch -d refused: %s' % (show(name), show(result.stderr.strip())))
        else:
            print('         recover the branch with: git branch %s %s (its commits are in main)' % (show(name), head))
    else:
        print('         detached HEAD %s; its commits are in main' % head)
    return True


def main():
    global ENV
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--apply', action='store_true', help='remove; without it nothing is changed')
    parser.add_argument('--assume-idle', action='store_true',
                        help='where processes cannot be inspected (no /proc), take it that none works in a worktree')
    args = parser.parse_args()
    ENV = git_env()
    here = os.getcwdb()
    records = worktrees(here)
    if 'bare' in records[0]:
        raise Unproven('the main repository is bare; nothing here is the kit\'s to remove')
    main_root = os.path.realpath(records[0]['worktree'])
    entries, refused = read_disposable(main_root)
    ctx = {'main_root': main_root, 'home': os.path.join(main_root, b'.claude', b'worktrees'),
           'main_head': records[0].get('HEAD', b''),
           'own': os.path.realpath(git(here, 'rev-parse', '--show-toplevel').stdout.rstrip(b'\n')),
           'disposable': entries, 'proc': os.fsencode(os.environ.get('CLEAN_WORKTREES_PROC', '/proc')),
           'assume_idle': args.assume_idle,
           'log': os.path.join(os.path.realpath(git(here, 'rev-parse', '--git-common-dir').stdout.rstrip(b'\n')),
                               b'kit-worktree-removals.log')}
    for line in refused:
        print('clean_worktrees: refused disposable entry %s (empty, absolute, "..", or a place that holds '
              'work: %s)' % (show(line), ', '.join(sorted(r.decode() for r in REFUSED))))
    removed = kept = freed = 0
    for record in records:
        shown = os.path.realpath(record['worktree'])
        if shown.startswith(main_root + b'/'):
            shown = shown[len(main_root) + 1:]
        try:
            reasons, facts = audit(record, ctx)
        except Exception as error:
            reasons, facts = ['not proven: %s' % error], None
        if reasons:
            kept += 1
            print('keep   %s' % show(shown))
            for reason in reasons:
                print('         - %s' % reason)
            continue
        print('remove %s (%s, %d identical files, %d disposable bytes, %d bytes)'
              % (show(shown), 'branch ' + show(short(facts['branch'])) if facts['branch'] else 'detached HEAD',
                 facts['identical'], facts['disposable'], facts['bytes']))
        if not args.apply:
            removed += 1
            freed += facts['bytes']
        elif remove(record, facts, ctx):
            removed += 1
            freed += facts['bytes']
        else:
            kept += 1
    if args.apply:
        print('clean_worktrees: removed %d, kept %d, freed %d bytes; log: %s'
              % (removed, kept, freed, show(ctx['log'])))
    else:
        print('clean_worktrees: dry run: would remove %d, keep %d, free %d bytes; to apply: '
              'scripts/clean_worktrees.sh --apply%s'
              % (removed, kept, freed, ' --assume-idle' if args.assume_idle else ''))


if __name__ == '__main__':
    try:
        main()
    except (Unproven, OSError) as error:
        print('clean_worktrees: stopped, nothing further removed: %s' % error)
        sys.exit(1)
