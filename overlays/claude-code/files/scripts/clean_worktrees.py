#!/usr/bin/env python3
"""Remove the finished worktrees under .claude/worktrees, and only what is proven safe to lose.

Run through scripts/clean_worktrees.sh, which says why this exists. With no option it is a dry
run; --apply removes. A worktree is removed only when every check below holds; a check that
fails, errors, or meets output it does not know keeps the worktree, with the reason printed.
The checks run cheapest first and stop at the first reason to keep (--all-reasons runs them
all):

  a. a linked worktree of this repository, physically directly under
     <main worktree>/.claude/worktrees/, not the main worktree, not the one this runs in, its
     folder its own worktree (not missing, not prunable), not locked;
  b. ended: its branch moved since it was created (the branch's reflog says so: a fresh
     worktree nobody committed in is a worker that may not have started), not detached;
  c. quiet: nothing in its git directory (HEAD, index, logs, ORIG_HEAD, the branch's reflog)
     changed in the last quiet-minutes (60 unless .claude/worktree-disposable says otherwise);
  d. nothing only it holds: every commit named by its HEAD reflog, its branch and that
     branch's reflog, its refs/worktree/* and refs/bisect/* is in main's HEAD; no per-worktree
     config;
  e. no merge, rebase, cherry-pick, revert, bisect or sequencer in progress;
  f. not in use: no process this user can inspect has its working directory inside it (/proc
     on Linux, lsof elsewhere), no tmux session has its name, the gate's lock is free;
  g. no unresolved index, no index entry git would not compare (skip-worktree,
     assume-unchanged), no submodule, no tracked path with a clean or process filter or the
     ident attribute (git would call an edited file clean);
  h. no tracked change; every file git does not track is inside a directory
     .claude/worktree-disposable lists, or a regular file whose byte-identical copy is at the
     same path in the main worktree; nothing outside the disposable folders changed in the
     last quiet-minutes.

Proven: a, b, d, e, g, h. The quiet period (c, h) is a margin, not a proof: it covers a worker
whose process the scan in f cannot see. Not guarded, by the owner's decision: a process that
changes a worktree between its audit and its removal, files planted to attack this script,
and a SIGKILL between two removal steps.

The filesystem is walked on its own, never through a symlink, and every entry that is not
tracked must be accounted for: `git status` does not list a FIFO, a socket or a device, and
`git worktree remove` deletes them and every ignored file without asking.

Removal order: the log record (flushed), the identical copies git does not track, `git worktree remove`
without --force (git's own check, independent of this one), `git branch -d` (never -D).
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
    """(rel, lstat, is a folder) for every entry under ROOT, the root itself as b'', never
    through a symlink. The worktree's own `.git` file is git's, not content."""
    yield b'', os.lstat(root), True
    stack = [b'']
    while stack:
        folder = stack.pop()
        with os.scandir(os.path.join(root, folder) if folder else root) as entries:
            for entry in entries:
                rel = folder + b'/' + entry.name if folder else entry.name
                if rel == b'.git':
                    continue
                info = entry.stat(follow_symlinks=False)
                is_dir = stat.S_ISDIR(info.st_mode)
                if is_dir:
                    stack.append(rel)
                yield rel, info, is_dir


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


def process_cwds(proc):
    """{pid: cwd} of every process this user can inspect, and how many it could not. Linux
    reads /proc; a host without it (macOS) asks lsof. Neither working is Unproven."""
    try:
        usable = os.readlink(os.path.join(proc, b'self', b'cwd')) == os.getcwdb()
        pids = [p for p in os.listdir(proc) if p.isdigit()] if usable else None
    except OSError:
        pids = None
    if pids is None:
        exe = shutil.which('lsof')
        if not exe:
            raise Unproven('no /proc and no lsof here')
        result = subprocess.run([exe, '-a', '-d', 'cwd', '-F', 'pn'], capture_output=True,
                                stdin=subprocess.DEVNULL, env=dict(os.environ, LC_ALL='C'))
        if result.returncode != 0:
            raise Unproven('`lsof -a -d cwd -F pn` failed: %s'
                           % (show(result.stderr.strip()) or 'exit %d' % result.returncode))
        return parse_lsof(result.stdout)
    cwds, unseen = {}, 0
    for pid in pids:
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


def newest(paths):
    """The newest modification time among PATHS and, for a folder, everything below it."""
    found = None
    for path in paths:
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            continue
        found = max(found or info.st_mtime, info.st_mtime)
        if stat.S_ISDIR(info.st_mode):
            for _, info, _ in walk(path):
                found = max(found, info.st_mtime)
    return found


def too_recent(mtime, ctx, what):
    """A reason when MTIME lies within the quiet period (a time in the future counts)."""
    if mtime is None or mtime + ctx['quiet'] * 60 <= ctx['now']:
        return []
    left = mtime + ctx['quiet'] * 60 - ctx['now']
    return ['quiet period: %s changed %d min ago; it qualifies in %d min (quiet-minutes=%d, a margin, '
            'not a proof)' % (what, max(0, ctx['now'] - mtime) // 60, -(-left // 60), ctx['quiet'])]


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
    facts = {'real': real, 'name': os.path.basename(real), 'head': record.get('HEAD', b''),
             'branch': record.get('branch'), 'delete': [], 'identical': 0, 'disposable': 0, 'bytes': 0,
             'reflog': []}
    gitdir = git(real, 'rev-parse', '--absolute-git-dir').stdout.rstrip(b'\n')
    tracked = set()

    def ended():
        branch = facts['branch']
        if branch is None:
            return ['detached HEAD: remove it by hand (only a branch\'s reflog proves work was done in it)']
        try:
            short(branch).decode('utf-8')
        except UnicodeDecodeError:
            return ['its branch name is not UTF-8: no recovery line could be printed for it']
        lines = git(ctx['main_root'], 'reflog', 'show', '--no-abbrev', '--format=%H%x09%gs', branch,
                    '--').stdout.split(b'\n')
        log = [line.partition(b'\t') for line in lines if line]
        facts['reflog'] = [entry[0] for entry in log]
        if not log:
            return ['its branch has no reflog: work done in it is not proven']
        start, _, subject = log[-1]
        if not subject.startswith(b'branch: Created from'):
            return ['its branch\'s reflog does not begin where the branch was created (expired or '
                    'rewritten): work done in it is not proven']
        if all(entry[0] == start for entry in log):
            return ['no commits of its own: its branch has not moved since it was created (a worker '
                    'that has not started, or is still working)']
        return []

    def quiet_gitdir():
        found = [os.path.join(gitdir, name) for name in (b'HEAD', b'index', b'logs', b'ORIG_HEAD')]
        if facts['branch']:
            found.append(os.path.join(ctx['common'], b'logs', facts['branch']))
        return too_recent(newest(found), ctx, 'its git directory')

    def merged():
        out = []
        # Without its own reflog, `reflog show HEAD` falls back to the branch's: ask first.
        if git(real, 'reflog', 'exists', 'HEAD', codes=(0, 1)).returncode:
            out.append('its HEAD has no reflog: what it pointed at is not proven')
        named = list(facts['reflog'])
        named += git(real, 'reflog', 'show', '--no-abbrev', '--format=%H', 'HEAD', '--').stdout.split()
        named += git(real, 'for-each-ref', '--format=%(objectname)', 'refs/worktree/', 'refs/bisect/').stdout.split()
        named.append(facts['head'])  # a checked-out branch's tip is this HEAD
        loose = git(ctx['main_root'], 'rev-list', '--stdin',
                    stdin=b'\n'.join(sorted(set(named)) + [b'^' + ctx['main_head']]) + b'\n').stdout.split()
        if loose:
            out.append('commit %s is not in main (named by its HEAD, its branch, their reflogs or its '
                       'refs; a reset, a dropped commit, a squash-merged or rebased branch): check and '
                       'remove it by hand' % show(loose[0][:12]))
        config = os.path.join(gitdir, b'config.worktree')
        if os.path.exists(config) and os.path.getsize(config) > 0:
            out.append('it has its own config (%s)' % show(config))
        return out

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
                cwds, ctx['unseen'] = cached(ctx, 'proc', lambda: process_cwds(ctx['proc']))
            except Unproven as error:
                return out + ['cannot see which processes work in it (%s); if none does, run by hand: '
                              'scripts/clean_worktrees.sh --apply --assume-idle' % error]
            inside = sorted(pid.decode() for pid, cwd in cwds.items() if cwd == real or cwd.startswith(real + b'/'))
            if inside:
                out.append('in use: process %s works inside it' % ', '.join(inside))
        return out

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
        # The same definition as the review adapter (core/scripts/claude_bridge.py): any
        # configured clean or process key is a filter, whatever its value, and git compares
        # the filtered bytes, so an edit the filter strips is "clean" to status and remove.
        drivers = set()
        for entry in git(real, 'config', '-z', '--get-regexp', r'^filter\..*\.(clean|process)$',
                         codes=(0, 1)).stdout.split(b'\0'):
            if entry:
                key = entry.partition(b'\n')[0]
                drivers.add(key[len(b'filter.'):key.rindex(b'.')])
        fields = git(real, 'check-attr', '-z', '--stdin', 'filter', 'ident',
                     stdin=b''.join(rel + b'\0' for rel in sorted(tracked))).stdout.split(b'\0')
        for name, attribute, value in zip(fields[0::3], fields[1::3], fields[2::3]):
            if (attribute == b'filter' and value in drivers) or (attribute == b'ident' and value == b'set'):
                out.append('a tracked path has a clean or process filter or the ident attribute, so git '
                           'may call an edited file unchanged: %s' % show(name))
                break
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
        unique, odd, suggest, recent = [], [], set(), None
        for rel, info, is_dir in walk(real):
            if disposable(rel + b'/x' if is_dir else rel, ctx['disposable']):
                if not is_dir:
                    facts['bytes'] += info.st_size
                    facts['disposable'] += info.st_size
                continue
            recent = max(recent or info.st_mtime, info.st_mtime)
            if is_dir:
                continue
            facts['bytes'] += info.st_size
            if rel in tracked:
                continue
            if not stat.S_ISREG(info.st_mode):
                odd.append(rel)
            elif regular(ctx['main_root'], rel) and filecmp.cmp(
                    os.path.join(real, rel), os.path.join(ctx['main_root'], rel), shallow=False):
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

    for check in (ended, quiet_gitdir, merged, operations, idle, index, files):
        try:
            reasons.extend(check())
        except Exception as error:  # any error is a keep, never a crash halfway through a run
            reasons.append('not proven: %s' % error)
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
    name = short(branch)
    result = subprocess.run(['git', 'branch', '-d', name], cwd=ctx['main_root'], env=ENV,
                            stdin=subprocess.DEVNULL, capture_output=True)
    if result.returncode != 0:
        print('         branch %s kept: git branch -d refused: %s' % (show(name), show(result.stderr.strip())))
    else:
        # Every commit it named is in main (clause d), so this restores the branch at its last
        # commit; not the worktree's ignored files, nor the branch's reflog.
        print('         branch deleted; this command, run in the main worktree, restores it at its last commit:')
        print('           git branch %s %s' % (sh_quote(name.decode('utf-8')), show(facts['head'])))
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
    main_root = os.path.realpath(records[0]['worktree'])
    entries, refused, quiet = read_disposable(main_root)
    common = os.path.realpath(git(here, 'rev-parse', '--git-common-dir').stdout.rstrip(b'\n'))
    ctx = {'main_root': main_root, 'home': os.path.join(main_root, b'.claude', b'worktrees'),
           'main_head': records[0].get('HEAD', b''), 'common': common,
           'own': os.path.realpath(git(here, 'rev-parse', '--show-toplevel').stdout.rstrip(b'\n')),
           'disposable': entries, 'quiet': quiet, 'now': time.time(), 'cache': {}, 'unseen': None,
           'proc': os.fsencode(os.environ.get('CLEAN_WORKTREES_PROC', '/proc')),
           'assume_idle': args.assume_idle, 'all': args.all_reasons,
           'log': os.path.join(common, b'kit-worktree-removals.log')}
    for line, why in refused:
        print('clean_worktrees: refused %s line %s (%s)' % (show(DISPOSABLE_FILE), show(line), why))
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
        else:
            kept += 1
    if ctx['unseen'] and not args.quiet:
        print('clean_worktrees: %d processes could not be inspected (another user\'s, or not readable); '
              'the quiet period covers a worker this scan cannot see' % ctx['unseen'])
    if args.apply:
        print('clean_worktrees: removed %d, kept %d, freed %d bytes; log: %s%s'
              % (removed, kept, freed, show(ctx['log']),
                 '; the reasons: scripts/clean_worktrees.sh' if args.quiet and kept else ''))
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
