#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Show or record the owner's working mode, using WORKFLOW.md as the rule source."""
import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

# The accepted shapes: the bold key, optionally indented or as a list item. Any other line that
# mentions the key is refused, never taken for a missing line.
STATE_LINE = re.compile(r'^([^\S\r\n]*(?:[-*+][^\S\r\n]+)?\*\*Working mode:\*\*[^\S\r\n]*)([^\r\n]*)(?=\r?$)', re.M)


def normalized(value):
    return value.replace('İ', 'I').replace('ı', 'i').casefold().strip()


def checked(project, relative):
    project = project.absolute()
    path = Path(project.anchor)
    for part in (*project.parts[1:], *Path(relative).parts):
        path /= part
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), 'st_file_attributes', 0)
                                 & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('linked path refused: ' + str(path))
    return path


def prepared(path, data):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
    if path.exists():
        shutil.copymode(path, name)
    return Path(name)


@contextmanager
def switch_lock(project):
    path = checked(project, '.claude/mode.lock')
    path.parent.mkdir(exist_ok=True)
    with path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            if not path.stat().st_size:
                handle.write(b'\0')
                handle.flush()
            handle.seek(0)
            acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(handle, fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as error:
            raise ValueError('mode switch in progress; retry when it ends') from error
        try:
            yield
        finally:
            handle.seek(0)
            release()


def mode(project, choice=None):
    if choice is None:
        return working_mode(project)
    with switch_lock(project):
        return working_mode(project, choice)


def working_mode(project, choice=None):
    workflow = checked(project, 'docs/WORKFLOW.md').read_text(encoding='utf-8')
    if '### Working modes, by name' not in workflow:
        raise ValueError('project predates v0.11 working modes; see the kit CHANGELOG.md')
    section = workflow.split('### Working modes, by name', 1)[1].split('\n## ', 1)[0]
    rows = re.findall(r'^\| `([a-z-]+)` \| ([^|]+) \| ([^\n]+)$', section, re.M)
    if len(rows) != 7 or len({name for name, _, _ in rows}) != 7:
        raise ValueError('WORKFLOW.md must define all seven modes')
    aliases = {normalized(alias): name for name, label, _ in rows
               for alias in (name, label.removesuffix(' (main mode)').strip())}
    state_path = checked(project, 'docs/STATE.md')
    state_bytes = state_path.read_bytes()
    state = state_bytes.decode('utf-8')
    matches = list(STATE_LINE.finditer(state))
    mentions = [line for line in state.splitlines() if 'working mode:' in line.casefold()]
    if len(mentions) > 1:
        raise ValueError('STATE.md has more than one Working mode line')
    if mentions and not matches:
        raise ValueError('unrecognized STATE.md Working mode line (write it as **Working mode:** NAME): '
                         + mentions[0].strip())
    current = 'cross-performance'
    note = ''
    if matches:
        value, separator, suffix = matches[0][2].partition(' (')
        current = aliases.get(normalized(value))
        if current is None:
            raise ValueError('invalid STATE.md working mode: ' + value)
        note = separator + suffix
    record = checked(project, '.claude/mode')
    if choice is None:
        if record.exists() and record.read_text(encoding='utf-8').strip() != current:
            raise ValueError('.claude/mode and STATE.md disagree; choose a mode explicitly to repair them')
        print('Current mode: ' + current + ('' if matches else ' (STATE.md line missing; main mode)'))
        for name, label, rules in rows:
            print(name + ' — ' + label + ' | ' + rules)
        return
    selected = aliases.get(normalized(choice))
    if selected is None:
        raise ValueError('unknown mode; choose ' + ', '.join(name for name, _, _ in rows))
    # Validate and extract the rules before making either edit.
    def rules(heading):
        match = re.search(r'^#### ' + re.escape(heading) + r'[^\n]*\n.*?(?=^#### |\Z)', section, re.M | re.S)
        if match is None:
            raise ValueError('missing mode rules: ' + heading)
        return match[0].strip()
    output = rules(selected + ' (')
    if selected in ('claude-saver', 'codex-saver'):
        output += '\n\n' + rules('The two saver modes')
    if matches:
        updated = STATE_LINE.sub(lambda m: m[1] + selected + note, state)
    else:
        newline = '\r\n' if '\r\n' in state else '\n'
        line = '**Working mode:** ' + selected + ' (docs/WORKFLOW.md, "Working modes, by name").' + newline
        separator = re.search(r'^---\r?\n', state, re.M)
        position = separator.end() if separator else len(state)
        updated = state[:position] + ('' if position == 0 or state[:position].endswith('\n') else newline) + line + state[position:]
    record.parent.mkdir(exist_ok=True)
    updated_bytes = updated.encode('utf-8')
    pending = []
    try:
        pending.append(prepared(state_path, updated_bytes))
        pending.append(prepared(record, (selected + '\n').encode('utf-8')))
        if state_path.read_bytes() != state_bytes:
            raise ValueError('STATE.md changed during the mode switch; retry with the current document')
        os.replace(pending[0], state_path)
        try:
            os.replace(pending[1], record)
        except OSError:
            if state_path.read_bytes() == updated_bytes:
                state_path.write_bytes(state_bytes)
            raise
    finally:
        for path in pending:
            path.unlink(missing_ok=True)
    print('Current mode: ' + selected + '\n\n' + output)


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', nargs='?')
    parser.add_argument('--project', type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        mode(args.project.absolute(), args.name)
    except (OSError, ValueError) as error:
        parser.exit(1, 'mode: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
