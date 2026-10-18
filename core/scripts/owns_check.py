"""Refuse a diff that changes a path outside the brief's Owns: line (docs/HANDOFF.md, "The brief").

usage: owns_check.py BRIEF [--uncommitted | --base REF | --commit SHA]

A brief without an Owns: line, or with more than one outside fenced code blocks, is an error
(exit 2). A pattern ending in '/' owns that folder; any other is a glob on the repository path
with git's rules: '*' and '?' stay inside one folder, '**/' matches zero or more folders and a
trailing '/**' everything below. docs/STATE.md and docs/BACKLOG.md are always allowed: every
worker records its state there. Exit 1 lists the paths outside; exit 2 is a usage or git error.
Run from the repository root (scripts/review.sh does).
"""
from fnmatch import fnmatchcase
from pathlib import Path
import re
import subprocess
import sys

ALWAYS = ('docs/STATE.md', 'docs/BACKLOG.md')
OWNS = re.compile(r'^[\s>*+-]*(?:\d+[.)]\s+)?(?:\*\*)?Owns:(?:\*\*)?(.*)$', re.M)
# A fence line (CommonMark): an opener may follow a list marker; group 1 is that marker.
FENCE = re.compile(r'[ \t>]*((?:[*+-]|\d+[.)])[ \t]+)?(`{3,}|~{3,})(.*)$')
WORKER_REPORT = re.compile(r'(?:RESULT|QUESTION)-[^/]+\.md')


def owned(brief):
    """The Owns: patterns of BRIEF, or None when it has no Owns: line.

    An example `Owns: *` in a code block above the real line won the first match and owned
    every path, so fenced blocks are skipped and a second line is refused, not guessed at.
    """
    lines = OWNS.findall(unfenced(Path(brief).read_text(encoding='utf-8'), brief))
    if not lines:
        return None
    if len(lines) > 1:
        raise ValueError('%d Owns: lines outside code blocks in %s; keep one' % (len(lines), brief))
    patterns = [p.strip().strip('`').replace('\\', '/') for p in lines[0].split(',')]
    return [p[2:] if p.startswith('./') else p for p in patterns if p]


def unfenced(text, brief):
    """TEXT without its fenced code blocks, paired as CommonMark pairs them.

    A fence opened after a list marker went unseen, so its closer paired as an opener and hid
    the real Owns: line; a line opening with inline ``code`` is no fence (a backtick fence's
    info string holds no backtick). An unclosed fence is refused: it hides the rest.
    """
    kept, fence = [], None
    for line in text.splitlines():
        match = FENCE.match(line)
        if fence:
            if (match and not match[1] and match[2][0] == fence[0] and len(match[2]) >= len(fence)
                    and not match[3].strip()):
                fence = None
        elif match and not (match[2][0] == '`' and '`' in match[3]):
            fence = match[2]
        else:
            kept.append(line)
    if fence:
        raise ValueError('an unclosed code fence in %s hides the lines after it; close it' % brief)
    return '\n'.join(kept)


def glob_match(parts, pattern):
    """Git's :(glob) rules on path segments. fnmatch alone let '*' cross '/' (`*.md` owned
    docs/DESIGN.md) and needed a folder for '**/' (`src/**/*.cpp` refused src/b.cpp)."""
    if not pattern:
        return not parts
    if pattern[0] == '**':
        if len(pattern) == 1:
            return bool(parts)
        return any(glob_match(parts[i:], pattern[1:]) for i in range(len(parts) + 1))
    return bool(parts) and fnmatchcase(parts[0], pattern[0]) and glob_match(parts[1:], pattern[1:])


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
    return sorted({path for path in paths if path not in ALWAYS and not WORKER_REPORT.fullmatch(path) and not any(
        path.startswith(p) if p.endswith('/') else glob_match(path.split('/'), p.split('/'))
        for p in patterns)})


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
            print('owns_check: no Owns: line was read from %s' % argv[0], file=sys.stderr)
            return 2
        if not patterns:
            print('owns_check: the Owns: line of %s names no path' % argv[0], file=sys.stderr)
            return 2
        stray = outside(changed(*argv[1:]), patterns)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
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
