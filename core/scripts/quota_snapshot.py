#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Append one subscription-quota snapshot: what a task cost in percent of the plan's windows.

Usage: quota_snapshot.py LABEL PHASE [--dir DIR]   DIR: $CLAUDE_PROJECT_DIR/.myagentkit/usage, else ./.myagentkit/usage
       LABEL  a worker NAME, or `-` for a hook: the session_id of the JSON on stdin, else "lead"
       PHASE  start or end

Appends {ts, label, phase, org_uuid, org_name, five_hour, seven_day} as one line to
DIR/quota.jsonl. The windows are Claude Code's own `rate-limits.json` keys copied as they
are (`five_hour` is there only while that window runs), the organisation is `.claude.json`'s
oauthAccount: limits are per organisation, and the owner switches accounts. Both files are
under CLAUDE_CONFIG_DIR when it is set, else ~/.claude and ~/.claude.json. No network.
agent_cost.py --quota compares each label's start and end. It never fails its caller (a spawn,
a close, a hook): any error is one stderr line and exit 0.
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        print(f'quota_snapshot: cannot read {path}: {error}', file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def snapshot(label: str, phase: str) -> dict:
    config = os.environ.get('CLAUDE_CONFIG_DIR')
    folder = Path(config) if config else Path.home() / '.claude'
    limits = read_json(folder / 'rate-limits.json')
    account = read_json(folder / '.claude.json' if config else Path.home() / '.claude.json').get('oauthAccount') or {}
    return {'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'label': label, 'phase': phase,
            'org_uuid': account.get('organizationUuid'), 'org_name': account.get('organizationName'),
            'five_hour': limits.get('five_hour'), 'seven_day': limits.get('seven_day')}


def main(argv: list[str]) -> int:
    # A hook runs in the folder a `cd` left; CLAUDE_PROJECT_DIR stays at the session's root.
    folder = Path(os.environ.get('CLAUDE_PROJECT_DIR') or '.') / '.myagentkit' / 'usage'
    if len(argv) == 4 and argv[2] == '--dir':
        folder, argv = Path(argv[3]), argv[:2]
    if len(argv) != 2 or argv[1] not in ('start', 'end'):
        raise ValueError('usage: quota_snapshot.py LABEL start|end [--dir DIR]')
    label = argv[0]
    if label == '-':
        try:
            label = json.loads(sys.stdin.read() or '{}').get('session_id') or 'lead'
        except (ValueError, AttributeError):
            label = 'lead'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(folder / 'quota.jsonl', 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(snapshot(str(label), argv[1]), ensure_ascii=False) + '\n')
    return 0


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Exception as error:  # noqa: BLE001 - a snapshot must never fail its caller
        print(f'quota_snapshot: {error}', file=sys.stderr)
    sys.exit(0)
