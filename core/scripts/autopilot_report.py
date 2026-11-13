#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Print the Done section of the autopilot report (docs/AUTOPILOT.md) from the records, never from
the lead's own account: the commits and merges since the stamp in .myagentkit/presence, the results
of the workers spawned since, and the latest session's cost line (agent_cost.py --latest).

Usage: autopilot_report.py [--project DIR]

The stamp is the one `working_mode.py autopilot` wrote (`away SINCE`); after `working_mode.py
present` the record keeps it with the return time (`present SINCE UNTIL`), so the report can be
made after the owner is back. A report built from git rather than the agent's self-report is the
practitioners' rule for unattended runs (the kit's docs/research/unattended-lead.md, 5.5).
"""
import argparse
from datetime import datetime
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from working_mode import presence_record  # noqa: E402


def stamps(project):
    """(since, until or None) from .myagentkit/presence, the main checkout's record in a linked worktree."""
    words = presence_record(project).read_text(encoding='utf-8').split()
    if len(words) < 2:
        raise ValueError('no autopilot stamp in .myagentkit/presence; working_mode.py autopilot writes it')
    return words[1], (words[2] if len(words) > 2 else None)


def commits(project, since, until):
    """One line per commit since SINCE, newest first; a commit with two parents is a merge."""
    args = ['git', '-C', str(project), 'log', '--since=' + since, '--format=%h%x09%p%x09%s']
    if until:
        args.append('--until=' + until)
    out = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', check=True).stdout
    for line in out.splitlines():
        sha, parents, subject = line.split('\t', 2)
        yield ('- merge ' if ' ' in parents else '- ') + sha + ' ' + subject


def results(project, since, until):
    """The four header lines of the result of each worker spawned in the absence (#316). The spawn
    records say who: spawn_worker.sh's NAME.result-path (its result's path) and spawn_codex.sh's
    NAME.session, rewritten at each spawn, and their NAME.closed-* forms close_worker.sh keeps with
    the same time. A result's own file time is never read: a checkout rewrites a committed one. Each
    is read where its record says, else where close_worker.sh moved it. Both are the main checkout's."""
    start = datetime.fromisoformat(since).timestamp()
    end = datetime.fromisoformat(until).timestamp() if until else float('inf')
    root = presence_record(project).parents[1]
    workers = root / '.myagentkit/workers'
    spawned = {}
    for kind in ('result-path', 'closed-result-path', 'session', 'closed-session'):
        for record in workers.glob('*.' + kind):
            name = record.name[:-len(kind) - 1]
            if '.' in name or not start <= record.stat().st_mtime <= end:
                continue
            told = record.read_text(encoding='utf-8', errors='replace').strip() if 'result' in kind else ''
            places = [root / told] if told else [root / '.claude/worktrees' / name / ('RESULT-%s.md' % name),
                                                 root / ('RESULT-%s.md' % name)]
            # close_worker.sh numbers a reused name's later results NAME.result-2.md, -3, ...: newest first.
            numbered = sorted((int(f.name[len(name) + 8:-3]), f) for f in workers.glob(name + '.result-*.md')
                              if f.name[len(name) + 8:-3].isdigit())
            spawned.setdefault(name, []).extend(places + [f for _, f in reversed(numbered)] +
                                                [workers / (name + '.result.md'), workers / ('RESULT-%s.md' % name)])
    for name in sorted(spawned):
        path = next((place for place in spawned[name] if place.is_file()), None)
        if path is None:
            yield '- %s: no result file' % name
            continue
        head = path.read_text(encoding='utf-8', errors='replace').splitlines()[:4]
        # resolve both: a record's absolute path may keep a symlinked prefix (macOS /var -> /private/var)
        real, base = path.resolve(), root.resolve()
        shown = real.relative_to(base).as_posix() if real.is_relative_to(base) else path.as_posix()
        yield '- ' + shown + ': ' + '; '.join(line.strip() for line in head)


def cost(project):
    """agent_cost.py's TOTAL line for the newest session transcript of PROJECT."""
    run = subprocess.run([sys.executable, str(Path(__file__).with_name('agent_cost.py')), '--latest', str(project)],
                         capture_output=True, text=True, encoding='utf-8', errors='replace')
    total = [line for line in run.stdout.splitlines() if line.startswith('TOTAL')]
    return total[-1] if total else 'not available (' + (run.stderr.strip() or 'no TOTAL line') + ')'


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--project', type=Path, default=Path.cwd())
    project = parser.parse_args().project.resolve()
    try:
        since, until = stamps(project)
        done = list(commits(project, since, until))
        workers = list(results(project, since, until))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, 'autopilot_report: %s\n' % error)
    print('## Done (since %s%s)\n' % (since, ', until ' + until if until else ''))
    print('Commits and merges (git log):\n' + ('\n'.join(done) or '- none'))
    print('\nWorker results:\n' + ('\n'.join(workers) or '- none'))
    print('\nCost: ' + cost(project))


if __name__ == '__main__':
    main()
