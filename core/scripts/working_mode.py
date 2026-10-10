#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Show or record the owner's working mode, using WORKFLOW.md as the rule source."""
import argparse
import os
from pathlib import Path
import re
import tempfile

STATE_LINE = re.compile(r'^(\*\*Working mode:\*\*[^\S\r\n]*)([a-z-]+)([^\r\n]*)(?=\r?$)', re.M)


def checked(project, relative):
    path = project
    for part in Path(relative).parts:
        path /= part
        if path.is_symlink() or (path.exists() and getattr(path, 'is_junction', lambda: False)()):
            raise ValueError('linked path refused: ' + relative)
    return path


def prepared(path, data):
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
    return Path(name)


def mode(project, choice=None):
    workflow = checked(project, 'docs/WORKFLOW.md').read_text(encoding='utf-8')
    if '### Working modes, by name' not in workflow:
        raise ValueError('project predates v0.11 working modes; see the kit CHANGELOG.md')
    section = workflow.split('### Working modes, by name', 1)[1].split('\n## ', 1)[0]
    rows = re.findall(r'^\| `([a-z-]+)` \| ([^|]+) \| ([^\n]+)$', section, re.M)
    if len(rows) != 6 or len({name for name, _, _ in rows}) != 6:
        raise ValueError('WORKFLOW.md must define all six modes')
    aliases = {alias.casefold(): name for name, label, _ in rows
               for alias in (name, label.removesuffix(' (main mode)').strip())}
    state_path = checked(project, 'docs/STATE.md')
    state_bytes = state_path.read_bytes()
    state = state_bytes.decode('utf-8')
    matches = list(STATE_LINE.finditer(state))
    if len(matches) > 1:
        raise ValueError('STATE.md has more than one Working mode line')
    record = checked(project, '.claude/mode')
    if choice is None:
        current = matches[0][2] if matches else 'cross-performance'
        if current not in aliases:
            raise ValueError('invalid STATE.md working mode: ' + current)
        if record.exists() and record.read_text(encoding='utf-8').strip() != current:
            raise ValueError('.claude/mode and STATE.md disagree; choose a mode explicitly to repair them')
        print('Current mode: ' + current + ('' if matches else ' (STATE.md line missing; main mode)'))
        for name, label, rules in rows:
            print(name + ' — ' + label + ' | ' + rules)
        return
    selected = aliases.get(choice.casefold())
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
        updated = STATE_LINE.sub(lambda m: m[1] + selected + m[3], state)
    else:
        newline = '\r\n' if '\r\n' in state else '\n'
        line = '**Working mode:** ' + selected + ' (docs/WORKFLOW.md, "Working modes, by name").' + newline
        separator = re.search(r'^---\r?\n', state, re.M)
        position = separator.end() if separator else len(state)
        updated = state[:position] + ('' if position == 0 or state[:position].endswith('\n') else newline) + line + state[position:]
    record.parent.mkdir(exist_ok=True)
    pending = []
    try:
        pending.append(prepared(state_path, updated.encode('utf-8')))
        pending.append(prepared(record, (selected + '\n').encode('utf-8')))
        os.replace(pending[0], state_path)
        try:
            os.replace(pending[1], record)
        except OSError:
            state_path.write_bytes(state_bytes)
            raise
    finally:
        for path in pending:
            path.unlink(missing_ok=True)
    print('Current mode: ' + selected + '\n\n' + output)


def main():
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
