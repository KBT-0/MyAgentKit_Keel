#!/usr/bin/env python3
"""SessionStart (clear, startup): point the fresh context at the hand-off the last lead wrote.

The one-key hand-off (docs/research/context-hygiene.md, Bulgu 7 and Öneri 1; owner, 2026-11-03):
the lead commits its hand-off file, writes `.myagentkit/handoff-pending` with one line,
`HANDOFF_PATH COMMIT`, and the owner types `/clear` in the same terminal, with no new window or
model id to type (docs/HANDOFF.md). This hook then adds one line to the new context: read the
file first. The marker is one-shot: it is deleted once the line is given, so no later start
repeats it. On a tree with uncommitted changes (`git status --porcelain` not empty, or git
cannot say) the line says so and the marker stays, for the session to delete once it has
checked them. The git facts are the session's own checkout (the input's `cwd`, a linked
worktree included, as before_compact.py reads them); the marker is in the main checkout's
`.myagentkit`, where the lead writes it from any of its trees. A worker session
(MYAGENTKIT_ROLE=worker) is skipped: the hand-off is the lead's, and a worker sharing the main
checkout must neither read it nor delete its marker. Work still running in the old session is not checked here: the transcript a
`/clear` starts is a new one, and the lead writes the marker only once the no-handoff rule
let it hand off (context_size.py's band line names the running jobs). Any other source
(`resume`, `compact`) and any error are silent: a broken marker never stops a session start.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

MARKER = '.myagentkit/handoff-pending'


def git(here: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(['git', '-C', str(here), *args], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=20)


def main_checkout(here: Path) -> Path:
    """The main checkout of HERE's repository (HERE itself outside a linked worktree)."""
    try:
        common = git(here, 'rev-parse', '--git-common-dir')
    except (OSError, subprocess.SubprocessError):
        return here
    # Made absolute here, not with --path-format (Git 2.31+): relative output is relative to HERE.
    folder = (here / common.stdout.strip()).resolve() if common.returncode == 0 and common.stdout.strip() else None
    return folder.parent if folder is not None and folder.name == '.git' else here


def line(here: Path, source) -> str:
    if source not in ('clear', 'startup') or os.environ.get('MYAGENTKIT_ROLE') == 'worker':
        return ''
    marker = main_checkout(here) / MARKER
    try:
        words = marker.read_text(encoding='utf-8').split()
    except (OSError, ValueError):
        return ''
    if not words:
        return ''
    path, commit = words[0], words[1] if len(words) > 1 else 'an unnamed commit'
    try:
        status = git(here, 'status', '--porcelain')
        dirty = status.returncode != 0 or bool(status.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        dirty = True
    if dirty:
        return (f'Read {path} first (written at {commit}), but the tree is not clean: run `git status` and '
                'tell the owner what is uncommitted before you continue from its Next; delete '
                f'{MARKER} once that is settled (docs/HANDOFF.md).')
    marker.unlink()
    return f'Read {path} first (written at {commit}); then continue from its Next.'


def main() -> None:
    data = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    data = data if isinstance(data, dict) else {}
    said = line(Path(data.get('cwd') or os.environ.get('CLAUDE_PROJECT_DIR') or '.'), data.get('source'))
    if said:
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': said}}))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001 - see the docstring
        pass
    sys.exit(0)
