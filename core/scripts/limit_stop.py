#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Write .myagentkit/limit-stop: the lead stopped on a usage limit under autopilot.

Usage: limit_stop.py [--project DIR]   DIR: the lead's checkout, default the current folder

One line, `RESETS_AT_EPOCH ORG_UUID HANDOFF_PATH`, in the main checkout's .myagentkit (a
linked worktree's lead writes it there too, as it writes handoff-pending). RESETS_AT is the
reset of the window that stopped the lead, from Claude Code's rate-limits.json as
quota_snapshot.py reads it: the latest reset among the windows at the spawn refusal caps
(five_hour 95 %, seven_day 98 %), else five_hour's; ORG_UUID is `.claude.json`'s account
(`-` when unreadable). HANDOFF_PATH is the absolute path .myagentkit/handoff-pending names.
The hand-off comes first: without handoff-pending, or with one naming a missing file, it
refuses and writes nothing, and so does a rate-limits.json with no reset time. The timer's
scripts/limit_watchdog.sh reads the line (docs/WORKFLOW.md, "autopilot, the owner-away switch").
"""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quota_snapshot import snapshot  # noqa: E402
from working_mode import presence_record  # noqa: E402

# The caps spawn_worker.sh refuses a spawn at: a window there is the one that stopped the lead.
CAPS = (('five_hour', 95), ('seven_day', 98))


def number(value):
    return type(value) in (int, float)


def resets_at(limits):
    """The epoch the stopping window resets at, or None."""
    at_cap = [w['resets_at'] for key, cap in CAPS for w in [limits.get(key)]
              if isinstance(w, dict) and number(w.get('used_percentage')) and w['used_percentage'] >= cap
              and number(w.get('resets_at'))]
    if at_cap:
        return int(max(at_cap))
    five = limits.get('five_hour')
    return int(five['resets_at']) if isinstance(five, dict) and number(five.get('resets_at')) else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    args = parser.parse_args()
    store = presence_record(args.project.resolve()).parent
    main_checkout = store.parent
    pending = store / 'handoff-pending'
    try:
        words = pending.read_text(encoding='utf-8').split()
    except FileNotFoundError:
        words = None
    if not words:
        parser.exit(1, 'limit_stop: refused: no %s; the hand-off comes first (docs/HANDOFF.md: write the hand-off, '
                       'commit, write handoff-pending), then this\n' % pending)
    handoff = Path(words[0]) if Path(words[0]).is_absolute() else main_checkout / words[0]
    if not handoff.is_file():
        parser.exit(1, 'limit_stop: refused: handoff-pending names %s, which is not a file\n' % handoff)
    taken = snapshot('limit-stop', 'stop')
    reset = resets_at(taken)
    if reset is None:
        parser.exit(1, 'limit_stop: refused: rate-limits.json names no reset time, so no watchdog can tell when to '
                       'continue; the owner opens the next session\n')
    org = taken.get('org_uuid') or '-'
    if not isinstance(org, str) or not org.strip() or any(c.isspace() for c in org):
        org = '-'
    line = '%d %s %s\n' % (reset, org, handoff.resolve())
    marker = store / 'limit-stop'
    temporary = store / ('.limit-stop.%d' % os.getpid())
    temporary.write_text(line, encoding='utf-8')
    os.replace(temporary, marker)
    print('limit_stop: wrote %s: %s' % (marker, line.strip()))
    print('limit_stop: stop now; the watchdog timer (scripts/limit_watchdog_install.sh) opens the next lead after '
          'the reset while autopilot is on, or another account continues')


if __name__ == '__main__':
    try:
        main()
    except OSError as error:
        sys.exit('limit_stop: ' + str(error))
