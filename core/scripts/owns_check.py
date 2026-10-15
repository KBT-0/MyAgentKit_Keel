"""Refuse a diff that changes a path outside the brief's Owns: line (docs/HANDOFF.md, "The brief").

usage: owns_check.py BRIEF [--uncommitted | --base REF | --commit SHA]

A brief without an Owns: line checks nothing (exit 0). A pattern ending in '/' owns that folder;
any other is an fnmatch pattern on the repository path. docs/STATE.md and docs/BACKLOG.md are
always allowed: every worker records its state there. Exit 1 lists the paths outside; exit 2 is
a usage or git error. Run from the repository root (scripts/review.sh does).
"""
from fnmatch import fnmatchcase
from pathlib import Path
import re
import subprocess
import sys

ALWAYS = ('docs/STATE.md', 'docs/BACKLOG.md')
OWNS = re.compile(r'^[\s>*+-]*(?:\*\*)?Owns:(?:\*\*)?(.*)$', re.M)


def owned(brief):
    """The Owns: patterns of BRIEF, or None when it has no Owns: line."""
    match = OWNS.search(Path(brief).read_text(encoding='utf-8'))
    if not match:
        return None
    patterns = [p.strip().strip('`').replace('\\', '/') for p in match[1].split(',')]
    return [p[2:] if p.startswith('./') else p for p in patterns if p]


def git(*args):
    return [p for p in subprocess.run(('git',) + args, capture_output=True, check=True).stdout
            .decode('utf-8', 'surrogateescape').split('\0') if p]


def changed(scope, ref=None):
    """Every path the review of SCOPE would see changed, renames counted as delete plus add."""
    if scope == '--uncommitted':
        # -z porcelain: 'XY path' per entry; --no-renames keeps it one path per entry.
        return [entry[3:] for entry in git('status', '--porcelain', '-z', '-uall', '--no-renames')]
    if scope == '--base':
        # REF...HEAD, what the review diffs: `diff REF` hides an edit a diverged base also made.
        return (git('diff', '--name-only', '--no-renames', '-z', ref + '...HEAD')
                + git('ls-files', '--others', '--exclude-standard', '-z'))
    # The review diffs a commit against its first parent, merges included (claude_bridge.snapshot).
    parents = git('rev-list', '--parents', '-n', '1', ref)[0].split()[1:]
    if parents:
        return git('diff', '--name-only', '--no-renames', '-z', parents[0], ref)
    return git('diff-tree', '--no-commit-id', '--no-renames', '-r', '-z', '--root', '--name-only', ref)


def outside(paths, patterns):
    return sorted({path for path in paths if path not in ALWAYS and not any(
        path.startswith(p) if p.endswith('/') else fnmatchcase(path, p) for p in patterns)})


def main(argv):
    if len(argv) == 1:
        argv = argv + ['--uncommitted']
    if not (len(argv) == 2 and argv[1] == '--uncommitted'
            or len(argv) == 3 and argv[1] in ('--base', '--commit') and not argv[2].startswith('-')):
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    try:
        patterns = owned(argv[0])
        if patterns is None:
            return 0
        if not patterns:
            print('owns_check: the Owns: line of %s names no path' % argv[0], file=sys.stderr)
            return 2
        stray = outside(changed(*argv[1:]), patterns)
    except (OSError, UnicodeDecodeError, subprocess.CalledProcessError) as error:
        detail = getattr(error, 'stderr', b'') or b''
        print('owns_check: %s %s' % (error, detail.decode('utf-8', 'replace').strip()), file=sys.stderr)
        return 2
    if stray:
        print('owns_check: the diff changes paths outside the Owns: line of %s:' % argv[0], file=sys.stderr)
        print(''.join('  %s\n' % path for path in stray), end='', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
