#!/usr/bin/env python3
"""PreCompact: write what a lossy summary must not lose, from git, for the SessionStart(compact) hook to print.

An autopilot session cannot hand off or be reopened by the owner, so it compacts at the
autoCompactWindow (450k) and goes on (owner 2026-10-26, handoff-48 item 10). The summary is the
model's own and may drop facts; this note holds the ones git knows: branch, HEAD, the files
changed and not committed, the last commits, and the newest hand-off file. PreCompact is the last
point before the summary (code.claude.com/docs/en/hooks; input: trigger, custom_instructions,
verified in Claude Code 2.1.310). The old note is deleted first, so a failed write leaves no
stale note to be printed, and the SessionStart command deletes the note it printed, so a hook
that never ran (no Python: py.sh exits 1) cannot bring back the last one. It writes nothing to stdout and always exits 0: exit 2 would block the
compaction.
"""
import json
import os
from datetime import datetime
from pathlib import Path
import subprocess
import sys

NOTE = '.myagentkit/compact-note.md'
STATUS_LINES = 30


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=20)
    return result.stdout.rstrip('\n') if result.returncode == 0 else ''


def newest_handoff(root: Path) -> str:
    patterns = ('docs/handoffs/*.md', '.myagentkit/handoff*.md', '.myagentkit/*/handoff*.md')
    found = [p for pattern in patterns for p in root.glob(pattern)]
    return str(max(found, key=lambda p: p.stat().st_mtime).relative_to(root)) if found else 'none found'


def note(root: Path, trigger: str) -> str:
    status = git(root, 'status', '--short').splitlines()
    if len(status) > STATUS_LINES:
        status = status[:STATUS_LINES] + ['... and %d more' % (len(status) - STATUS_LINES)]
    return '\n'.join([
        'Facts from git, written just before the compaction (%s, %s); they outrank the summary:'
        % (trigger or 'auto', datetime.now().astimezone().isoformat(timespec='seconds')),
        '- branch: %s, HEAD %s' % (git(root, 'branch', '--show-current') or '(detached)',
                                   git(root, 'log', '-1', '--format=%h %s') or '(no commit)'),
        '- newest hand-off file: %s (update it before the next step)' % newest_handoff(root),
        '- not committed:' + ('\n  ' + '\n  '.join(status) if status else ' nothing'),
        '- last commits:\n  ' + '\n  '.join(git(root, 'log', '-5', '--format=%h %s').splitlines() or ['none']),
    ]) + '\n'


def main() -> None:
    try:
        data = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    except ValueError:  # an unreadable input still gets a fresh note, never the last one
        data = {}
    data = data if isinstance(data, dict) else {}
    root = Path(os.environ.get('CLAUDE_PROJECT_DIR') or data.get('cwd') or '.')
    path = root / NOTE
    path.unlink(missing_ok=True)
    text = note(root, str(data.get('trigger') or ''))
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:  # noqa: BLE001 - a missing note never stops a compaction
        print('before_compact: %s' % error, file=sys.stderr)
    sys.exit(0)
