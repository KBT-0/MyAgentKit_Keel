#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Claim, release or show the master writer: the one session the pre-commit and pre-merge-commit
hooks let commit or merge in the main checkout (docs/WORKFLOW.md, "Parallel work — worktree policy").
.myagentkit/master-writer holds its id; the **Master writer:** line of docs/STATE.md follows it."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from working_mode import STATE_LINE, checked, prepared, shown, switch_lock  # noqa: E402

LINE = re.compile(r'^([^\S\r\n]*(?:[-*+][^\S\r\n]+)?\*\*Master writer:\*\*[^\S\r\n]*)([^\r\n]*)(?=\r?$)', re.M)


def session():
    """What the hooks compare: Claude Code exports CLAUDE_CODE_SESSION_ID to every shell it runs."""
    return os.environ.get('MYAGENTKIT_SESSION_ID') or os.environ.get('CLAUDE_CODE_SESSION_ID') or ''


def session_name(me):
    """The name peers send to (SendMessage): MYAGENTKIT_SESSION_NAME, else this session's row in
    `claude agents --json --all`; '' when neither is readable."""
    name = os.environ.get('MYAGENTKIT_SESSION_NAME', '')
    if not name:
        try:
            rows = json.loads(subprocess.run([shutil.which('claude') or 'claude', 'agents', '--json', '--all'], capture_output=True,
                                             text=True, encoding='utf-8', timeout=20).stdout)
            name = next((str(r.get('name') or '') for r in rows if r.get('sessionId') == me), '')
        except (OSError, ValueError, AttributeError, TypeError, subprocess.SubprocessError):  # any JSON shape
            pass
    return name if re.fullmatch(r'[\w.-]+', name) else ''


def main_checkout(linked_ok=False):
    """The main checkout's root. From a linked worktree only when LINKED_OK (show): the hooks never
    refuse there, so a claim or a release there would mean nothing."""
    git = lambda *args: subprocess.run(['git', 'rev-parse', *args], capture_output=True, text=True,
                                       check=True).stdout.strip()
    try:
        root, here, common = git('--show-toplevel'), git('--absolute-git-dir'), git('--git-common-dir')
    except (OSError, subprocess.CalledProcessError):
        raise ValueError('not in a git checkout') from None
    if Path(here).resolve() == Path(common).resolve():
        return Path(root).resolve()
    if not linked_ok:
        raise ValueError('run it in the main checkout: a linked worktree has no master writer')
    return Path(common).resolve().parent


def write_state(project, value):
    """Set the **Master writer:** line, inserted after the Working mode line when there is none."""
    state = checked(project, 'docs/STATE.md')
    if not state.is_file():
        print('master-writer: no docs/STATE.md; the marker alone records it', file=sys.stderr)
        return
    text = state.read_bytes().decode('utf-8')
    found = LINE.findall(text)
    if len(found) > 1:
        raise ValueError('docs/STATE.md has %d **Master writer:** lines; keep one' % len(found))
    if found:
        text = LINE.sub(lambda m: m[1] + value, text)
    else:
        newline = '\r\n' if '\r\n' in text else '\n'
        line = '**Master writer:** ' + value + newline
        mode = STATE_LINE.search(text)
        end = len(text) if mode is None or text.find('\n', mode.end()) < 0 else text.find('\n', mode.end()) + 1
        text = text[:end] + ('' if not text[:end] or text[:end].endswith('\n') else newline) + line + text[end:]
    pending = prepared(project, state, text.encode('utf-8'))
    os.replace(pending, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('claim', 'release', 'show', 'status'), help='status = show')
    parser.add_argument('--force', action='store_true',
                        help="take over or clear another session's claim: only on the owner's word")
    args = parser.parse_args()
    args.action = 'show' if args.action == 'status' else args.action
    try:
        project = main_checkout(linked_ok=args.action == 'show')
        marker = checked(project, '.myagentkit/master-writer')
        # Line 1 is the id the hooks compare, line 2 the session's name for peers.
        lines = lambda: (marker.read_text(encoding='utf-8').splitlines() if marker.exists() else []) + ['', '']
        read = lambda: lines()[0].strip()
        me = session()
        if args.action == 'show':
            holder, name = read(), lines()[1].strip()
            print('Master writer: ' + (holder or 'none') + (' (session name ' + name + ')' if holder and name else '')
                  + (' (this session)' if holder and holder == me else ''))
            return
        with switch_lock(project):
            holder = read()
            if not me:
                raise ValueError('no session id: CLAUDE_CODE_SESSION_ID is unset; set MYAGENTKIT_SESSION_ID')
            if holder and holder != me and not args.force:
                raise ValueError('the master writer is ' + shown(holder) + ': ask it for MAIN CHECKOUT IDLE (it '
                                 'releases first), or pass --force on the owner\'s word')
            if args.action == 'claim':
                name = session_name(me)
                pending = prepared(project, marker, (me + '\n' + (name + '\n' if name else '')).encode('utf-8'))
                os.replace(pending, marker)
                write_state(project, me + ' (' + (name + ', ' if name else '') + 'claimed '
                            + datetime.date.today().isoformat() + ')')
                print('Master writer: ' + me + (' (session name ' + name + '): tell every peer lead and running worker '
                                                'of this project "new lead is ' + name + ', send merge requests there"'
                                                if name else ''))
            else:
                marker.unlink(missing_ok=True)
                write_state(project, 'none')
                print('Master writer: none')
    except (OSError, ValueError) as error:
        parser.exit(1, 'master-writer: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
