#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Show or record the owner's working mode, or the owner's presence (autopilot, present),
using WORKFLOW.md as the rule source."""
import argparse
from contextlib import contextmanager, suppress
from datetime import datetime
import hashlib
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
# The three modes of v0.11: a few named modes the user switches, as Aider's chat modes and Roo
# Code's modes are (aider.chat/docs/usage/modes.html, roocodeinc.github.io/Roo-Code/basic-usage/using-modes).
# A project from before them records an older kit version (kit_version), and any other table is a
# defect. An old name is refused with the mapping, never migrated by guess (the kit's own choice).
MODES = ('solo', 'cross', 'saver')
OLD_MODES = {'claude-first', 'cross-performance', 'cross-saving', 'codex-first', 'claude-saver', 'codex-saver', 'claude-only'}
# The one mapping of the old names, printed wherever an old name is met (CHANGELOG.md says the same).
MAPPING = ('claude-only is solo; cross-performance, claude-first and codex-first are cross; cross-saving, '
           'claude-saver and codex-saver are saver with a (low: ...) note')
# The note a mode takes after its name in STATE.md (docs/WORKFLOW.md, "Working modes, by name"):
# solo may name its family (none means claude), saver must name the low side, cross takes none.
# saver also records the mode it interrupted, so the return to it survives a hand-off (a
# temporary mode that returns, as Aider's one-message switch does; the record that outlives the
# session is the kit's own). saver must name its side: which allowance runs low differs by side
# (Claude: session, weekly or a model's own limit, code.claude.com/docs/en/errors).
AFTER = re.compile(r', after: ((?:solo|cross)(?:, family: [^(),]+)?)$')
SIDES = {'solo': re.compile(r'family: [^(),]+'), 'saver': re.compile(r'low: [^(),]+(?:' + AFTER.pattern[:-1] + ')?')}
REQUIRED = {'saver'}
EXAMPLES = {'solo': 'family: codex', 'saver': 'low: claude'}
# The owner's presence (v0.13): a second switch beside the mode, never a fourth mode, since a
# mode says who writes and reviews and presence says whether the owner can answer
# (docs/WORKFLOW.md, "autopilot"). The STATE line and .myagentkit/presence, which the hooks
# read, follow the mode's rules: only the switch writes them, a read refuses a disagreement.
PRESENCE = ('autopilot', 'present')
OWNER_LINE = re.compile(r'^([^\S\r\n]*(?:[-*+][^\S\r\n]+)?\*\*Owner:\*\*[^\S\r\n]*)([^\r\n]*)(?=\r?$)', re.M)
AWAY = re.compile(r'away \(autopilot since (\S+)\)')
BACK = ('The owner is back. Before anything else: run `python scripts/autopilot_report.py` and finish the '
        'report from it (docs/AUTOPILOT.md); give it in two layers (docs/COMMUNICATION.md, "Handoff"); then '
        'ask its Questions one by one with AskUserQuestion, the recommended option first. An Issue draft is '
        'posted only on the owner\'s yes.')


def repairs_old_mode(old_lines, new_lines):
    """The one edit of the Working mode line that --replace-state accepts: a mode name from
    before v0.11 becomes one of the three, so the upgrade stays under the compare-and-swap rule."""
    if len(old_lines) != 1 or len(new_lines) != 1:
        return False
    old, new = STATE_LINE.match(old_lines[0]), STATE_LINE.match(new_lines[0])
    return (old is not None and new is not None
            and normalized(old[2].partition(' (')[0]) in OLD_MODES
            and normalized(new[2].partition(' (')[0]) in MODES)


def normalized(value):
    return value.replace('İ', 'I').replace('ı', 'i').casefold().strip()


def checked(project, relative):
    """PROJECT/RELATIVE, refused when a component below the root is a link. main() resolved the
    root once: macOS /tmp or a linked home is an ordinary way to name a project. On Windows only
    a name surrogate (a junction or symlink) redirects; a cloud-file placeholder does not."""
    path = project
    for part in Path(relative).parts:
        path /= part
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), 'st_reparse_tag', 0) & 0x20000000):
            raise ValueError('linked path refused: ' + str(path))
    return path


def prepared(project, path, data):
    """DATA in a new file for os.replace onto PATH. It is written in the ignored .myagentkit/ (the
    same volume: checked() refuses a linked folder), so a copy a killed run leaves is never beside
    STATE.md for `git add -A` to commit, and flushed to disk first, so a power loss after the
    rename cannot leave an empty STATE.md (#256)."""
    folder = checked(project, '.myagentkit')
    folder.mkdir(exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=folder)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    if path.exists():
        shutil.copymode(path, name)
    return Path(name)


@contextmanager
def switch_lock(project):
    path = checked(project, '.myagentkit/mode.lock')
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


# A line shaped like the key: after any Markdown line markers (bullet, number, quote, heading,
# table cell), bold, italic or plain, so one in another shape is still refused as unrecognized
# (v0.11); a sentence that mentions "the working mode: saver" is prose (#257). Each marker is
# one token the loop repeats (`#`, never `#+`): a nested `#+` backtracks exponentially on a line
# of many '#'.
MODE_KEY = re.compile(r'[^\S\r\n]*(?:(?:[-*+>|]|\d+[.)]|#)[^\S\r\n]*)*(?:\*\*|__|[*_])?working mode'
                      r'(?:\*\*|__|[*_])?[^\S\r\n]*:', re.I)


def mode_lines(text):
    return [line for line in text.splitlines() if MODE_KEY.match(line)]


def numbered(text):
    """The Working mode lines of TEXT with their line numbers, for a refusal."""
    return '; '.join('line %d: %s' % (n, line.strip()) for n, line in enumerate(text.splitlines(), 1)
                     if MODE_KEY.match(line))


def private(project, path):
    """PATH resolved, only inside the project's .myagentkit/ or the temporary folder (outside the
    project): /mode runs this helper unprompted, so a STATE operation reads and writes no other
    file, and a prepared copy never lands where `git add -A` commits it."""
    path = path.resolve()
    temporary = Path(tempfile.gettempdir()).resolve()
    if path.is_relative_to(project / '.myagentkit') or (path.is_relative_to(temporary)
                                                       and not path.is_relative_to(project)):
        return path
    raise ValueError('a prepared STATE.md file lives in .myagentkit/ or the temporary folder: ' + str(path))


def shown(path):
    """PATH for a message, its control bytes as `?`, as close_worker.sh prints its lines."""
    return re.sub(r'[\x00-\x1f\x7f]', '?', str(path))


# Why a compare-and-swap: two writers of one file lose an update unless the write checks what
# was read, as HTTP If-Match does (developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-Match);
# Claude Code's shared memory file loses updates this way (anthropics/claude-code#24130). Why
# mkstemp: it creates the file exclusively, readable by its creator only (docs.python.org/3/library/tempfile.html;
# CWE-377, insecure temporary file).
def read_state(project, out):
    """Create an exclusive per-edit snapshot with OUT as its prefix; return its path and hash.
    The snapshot is created in OUT's folder, so that folder is private too: OUT naming
    .myagentkit itself put the snapshot in the project root, where `git add -A` commits it."""
    data = checked(project, 'docs/STATE.md').read_bytes()
    folder = private(project, out.parent)
    folder.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=out.name + '-', dir=folder)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
    return Path(name), hashlib.sha256(data).hexdigest()


def replace_state(project, source, expected):
    """Publish an edited snapshot only if STATE still matches it under the switch lock, then
    delete the snapshot. Its Working mode line stays the mode switch's. FILE is a regular file:
    the rename below moved a folder named instead (.myagentkit, the temporary folder) whole."""
    # Before the lock, which lives in .myagentkit/: FILE named .myagentkit itself is refused by name.
    if not stat.S_ISREG(os.lstat(source).st_mode):
        raise ValueError('a prepared STATE.md file is a regular file: ' + shown(source))
    try:  # failed restoration must keep the whole folder private
        parent = private(project, source.parent)
    except ValueError:
        raise ValueError("FILE's own folder must be inside .myagentkit/ or the temporary folder, as a failed "
                         'restoration keeps its draft there: ' + shown(source)) from None
    with switch_lock(project):
        state = checked(project, 'docs/STATE.md')
        current = state.read_bytes()
        actual = hashlib.sha256(current).hexdigest()
        if actual != expected.lower():
            raise ValueError('STATE.md sha256 mismatch: expected ' + expected + ', current ' + actual
                             + '; read it again with --read-state, redo the edit in that snapshot, and retry')
        folder = Path(tempfile.mkdtemp(prefix='.' + source.name + '-', dir=parent))
        owned = folder / 'snapshot'
        identity = pending = None
        published = False
        try:
            os.rename(source, owned)  # the destination is in this caller's fresh private directory
            identity = owned.lstat()
            if not stat.S_ISREG(identity.st_mode):  # swapped in after the check
                if stat.S_ISDIR(identity.st_mode):
                    os.rename(owned, source)  # no link restores a folder; this replaces only an empty one
                    identity = None
                raise ValueError('a prepared STATE.md file is a regular file: ' + shown(source))
            with owned.open('rb') as handle:
                identity = os.fstat(handle.fileno())
                data = handle.read()
            old_lines, new_lines = mode_lines(current.decode('utf-8')), mode_lines(data.decode('utf-8'))
            if old_lines != new_lines and not repairs_old_mode(old_lines, new_lines):
                raise ValueError('the edit changes the Working mode line of STATE.md (the edit has: %s); only a '
                                 'mode switch (working_mode.py NAME) changes it, together with .myagentkit/mode '
                                 '(the one exception: a mode name from before v0.11 may become solo, cross or '
                                 'saver)' % (numbered(data.decode('utf-8')) or 'none'))
            if [m[0] for m in OWNER_LINE.finditer(current.decode('utf-8'))] != \
                    [m[0] for m in OWNER_LINE.finditer(data.decode('utf-8'))]:
                raise ValueError('the edit changes the Owner line of STATE.md; only working_mode.py autopilot '
                                 'or present changes it, together with .myagentkit/presence')
            pending = prepared(project, state, data)
            os.replace(pending, state)
            published = True
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)
            with suppress(OSError):
                if identity is not None and os.path.samestat(identity, owned.lstat()):
                    if not published:
                        os.link(owned, source, follow_symlinks=False)  # restore without replacing a successor
                    owned.unlink()  # only the verified object, never the caller's reusable pathname
            try:
                folder.rmdir()
            except OSError:  # an unconsumed draft stays private for recovery, and says where
                print('mode: the unpublished snapshot is kept at ' + shown(owned), file=sys.stderr)


def kit_version(project):
    """The kit version the project's sync recorded (docs/kit/.kit-version, written by bootstrap.sh
    and sync-kit.sh) as (major, minor), or None without one. A migration tool reads the version it
    recorded, as Alembic and Flyway do, never the shape of a document (KARARLAR D10 inv2#136)."""
    stamp = checked(project, 'docs/kit/.kit-version')
    if not stamp.is_file():
        return None
    text = stamp.read_text(encoding='utf-8').strip()
    match = re.fullmatch(r'(\d+)\.(\d+)(?:\.\d+)?', text)  # a patch release adds .PATCH
    if match is None:
        raise ValueError('unreadable kit version in docs/kit/.kit-version: ' + shown(text))
    return int(match[1]), int(match[2])


def mode(project, choice=None, sides=None):
    version = kit_version(project)
    if version is not None and version < (0, 11):
        print('ACTION: this project records kit v%d.%d (docs/kit/.kit-version), before the three working '
              'modes (solo, cross, saver) of v0.11, so no mode was shown or switched. Run the kit\'s '
              'sync-kit.sh and apply its v0.11 ACTION items (kit CHANGELOG.md, v0.11): replace the "Working '
              'modes, by name" section of docs/WORKFLOW.md with the kit\'s, and set the STATE.md line to the '
              'matching mode (%s); then run this again.' % (version + (MAPPING,)))
        if choice is not None:
            raise ValueError('no mode was switched: the project predates the three modes')
        return
    # Read before the lock is created: a switch never writes WORKFLOW.md.
    workflow = checked(project, 'docs/WORKFLOW.md').read_text(encoding='utf-8')
    if '### Working modes, by name' not in workflow:
        raise ValueError('WORKFLOW.md has no "Working modes, by name" section')
    section = workflow.split('### Working modes, by name', 1)[1].split('\n## ', 1)[0]
    rows = re.findall(r'^\| `([a-z-]+)` \|([^\n]+)$', section, re.M)
    names = [name for name, _ in rows]
    if tuple(names) != MODES:
        raise ValueError('WORKFLOW.md must define the three modes solo, cross and saver')
    if choice is None:
        return working_mode(project, section, rows)
    with switch_lock(project):
        if normalized(choice) in PRESENCE:
            if sides is not None:
                raise ValueError(normalized(choice) + ' takes no note')
            return switch_presence(project, section, normalized(choice))
        return working_mode(project, section, rows, choice, sides)


def owner(project, state):
    """(stamp, line, record words): the autopilot stamp of STATE's one Owner line (None for
    present or no line), its match, and the words of .myagentkit/presence (none: present)."""
    found = list(OWNER_LINE.finditer(state))
    if len(found) > 1:
        raise ValueError('STATE.md has more than one Owner line: ' + '; '.join(m[0].strip() for m in found))
    line = found[0] if found else None
    value = line[2].strip().rstrip('.') if line else 'present'
    away = AWAY.fullmatch(value)
    if away is None and value != 'present':
        raise ValueError('unrecognized STATE.md Owner line (only working_mode.py autopilot or present writes it): '
                         + line[0].strip())
    record = checked(project, '.myagentkit/presence')
    words = record.read_text(encoding='utf-8').split() if record.exists() else ['present']
    return (away[1] if away else None), line, words


def switch_presence(project, section, choice):
    """Write STATE's Owner line and .myagentkit/presence together, as a mode switch writes its two."""
    rules = re.search(r'^#### autopilot(?![\w-]).*?(?=^#### |\Z)', section, re.M | re.S)
    if rules is None:
        raise ValueError('WORKFLOW.md has no autopilot rules ("#### autopilot" under "Working modes, by '
                         'name"); sync the kit (v0.13) and run this again')
    state_path = checked(project, 'docs/STATE.md')
    state_bytes = state_path.read_bytes()
    state = state_bytes.decode('utf-8')
    stamp, line, words = owner(project, state)
    record = checked(project, '.myagentkit/presence')
    now = datetime.now().astimezone().isoformat(timespec='seconds')
    # A second switch keeps the first stamp, so the report covers the whole absence; the return
    # keeps it too, with the time of the return, for scripts/autopilot_report.py.
    since = stamp or (words[1] if words[0] == 'away' and len(words) > 1 else None)
    if choice == 'autopilot':
        since = stamp or now
        value, text = 'away (autopilot since %s)' % since, 'away %s\n' % since
    else:
        value, text = 'present', 'present%s\n' % (' %s %s' % (since, now) if since else '')
    newline = '\r\n' if '\r\n' in state else '\n'
    if line is not None:
        updated = state[:line.start(2)] + value + state[line.end(2):]
    else:
        # Under the Working mode line, else where a mode switch adds its line.
        after = STATE_LINE.search(state) or re.search(r'^---\r?$', state, re.M)
        position = state.find('\n', after.end()) + 1 if after else len(state)
        position = position or len(state)
        updated = (state[:position] + ('' if position == 0 or state[:position].endswith('\n') else newline)
                   + '**Owner:** ' + value + newline + state[position:])
    publish(project, state_path, state_bytes, updated.encode('utf-8'), record, text)
    print('Owner: ' + value + '\n')
    if choice == 'present':
        print(BACK)
        return
    print(rules[0].strip() + '\n\nThe owner types this line before leaving (a slash command; the lead cannot run '
          'it):\n/goal every item in the autopilot list of docs/STATE.md is done or parked with a reason, and '
          'the report .myagentkit/autopilot/%s.md is written' % since[:10])


def working_mode(project, section, rows, choice=None, sides=None):
    # A mode has its English name only (owner, KARARLAR B06 inv3#178); case does not matter.
    aliases = {normalized(name): name for name, _ in rows}
    state_path = checked(project, 'docs/STATE.md')
    state_bytes = state_path.read_bytes()
    state = state_bytes.decode('utf-8')
    matches = list(STATE_LINE.finditer(state))
    mentions = mode_lines(state)
    if len(mentions) > 1:
        raise ValueError('STATE.md has more than one Working mode line: ' + numbered(state))
    if mentions and not matches:
        raise ValueError('unrecognized STATE.md Working mode line (write it as **Working mode:** NAME): '
                         + mentions[0].strip())
    current = 'solo'
    note = ''
    if matches:
        value, separator, suffix = matches[0][2].partition(' (')
        current = aliases.get(normalized(value))
        if current is None:
            hint = ''
            if normalized(value) in OLD_MODES:
                hint = ('; it is a mode name from before v0.11: repair the line through --read-state and '
                        '--replace-state (the one edit of that line they accept; ' + MAPPING +
                        '), then run this again')
            raise ValueError('invalid STATE.md working mode: ' + value + hint)
        note = separator + suffix
    # The record lives in the tool-neutral, ignored private store: under .claude/ it gave every
    # project a Claude Code folder, overlay or not, and a file nobody said to commit (#272).
    record = checked(project, '.myagentkit/mode')
    if choice is None:
        if record.exists() and record.read_text(encoding='utf-8').strip() != current:
            raise ValueError('.myagentkit/mode and STATE.md disagree; choose a mode explicitly to repair them')
        stamp, _, words = owner(project, state)
        if (words[:2] != ['away', stamp]) if stamp else (words[0] != 'present'):
            raise ValueError('.myagentkit/presence and the STATE.md Owner line disagree; switch autopilot or '
                             'present explicitly to repair them')
        back = AFTER.search(note.strip(' ().')) if current == 'saver' else None
        print('Current mode: ' + current + ('' if matches else ' (STATE.md line missing; main mode)')
              + (' (returns to ' + back[1] + ')' if back else ''))
        print('Owner: ' + ('away (autopilot since %s)' % stamp if stamp else 'present'))
        for name, cells in rows:
            print(name + ' |' + cells)
        return
    selected = aliases.get(normalized(choice))
    if selected is None:
        raise ValueError('unknown mode; choose ' + ', '.join(name for name, _ in rows))
    # Validate and extract the rules before making either edit.
    def rules(name):
        match = re.search(r'^#### ' + re.escape(name) + r'(?![\w-])[^\n]*\n.*?(?=^#### |\Z)', section, re.M | re.S)
        if match is None:
            raise ValueError('missing mode rules: ' + name)
        return match[0].strip()
    output = rules(selected)
    # saver names its low side and solo may name its family; a switch sets the note from the
    # argument or keeps one of the right shape, never a stale one. cross takes no note.
    shape = SIDES.get(selected)
    # The line is one physical line: a note wrapped onto the next line (the v0.11 template
    # before a601395 did) would be cut in half, its tail left as an orphan.
    if note.count('(') != note.count(')'):
        raise ValueError('the STATE.md Working mode note wraps onto the next line; put the whole line '
                         'on one line (--read-state / --replace-state keeps the note) and run this again')
    old = note.strip(' ().')
    given = (sides if sides is not None else old).strip(' ().')
    # A switch to saver appends the mode it leaves (a solo family with it); leaving saver for
    # solo brings that family back, unless the switch names another note.
    back = AFTER.search(old) if current == 'saver' else None
    if selected == 'saver' and shape.fullmatch(given) and not AFTER.search(given):
        if back:
            given += back[0]
        elif current != 'saver':
            given += ', after: ' + current + (', ' + old if current == 'solo' and SIDES['solo'].fullmatch(old) else '')
    elif selected == 'solo' and sides is None and back and back[1].startswith('solo, '):
        given = back[1][len('solo, '):]
    named = bool(shape and shape.fullmatch(given))
    if named:
        note = ' (' + given + ')' + ('.' if note.rstrip().endswith('.') else '')
    elif shape and (selected in REQUIRED or sides is not None):
        raise ValueError('a switch to %s takes its note: working_mode.py %s "%s"'
                         % (selected, selected, EXAMPLES[selected]))
    elif sides is not None:
        raise ValueError('%s takes no note' % selected)
    elif any(s.fullmatch(given) for s in SIDES.values()):
        note = ''
    if matches:
        updated = STATE_LINE.sub(lambda m: m[1] + selected + note, state)
    else:
        newline = '\r\n' if '\r\n' in state else '\n'
        # The sides a switch names are the note; without it, STATE never said who writes.
        line = '**Working mode:** ' + selected + (note.rstrip('.') + '.' if named else
                                                  ' (docs/WORKFLOW.md, "Working modes, by name").') + newline
        separator = re.search(r'^---\r?\n', state, re.M)
        position = separator.end() if separator else len(state)
        updated = state[:position] + ('' if position == 0 or state[:position].endswith('\n') else newline) + line + state[position:]
    publish(project, state_path, state_bytes, updated.encode('utf-8'), record, selected + '\n')
    print('Current mode: ' + selected + '\n\n' + output)


def publish(project, state_path, state_bytes, updated_bytes, record, text):
    """STATE.md as UPDATED_BYTES and RECORD as TEXT, both or neither: STATE must still be
    STATE_BYTES, and a failed record write puts STATE back unless another writer changed it."""
    record.parent.mkdir(exist_ok=True)
    pending = []
    try:
        pending.append(prepared(project, state_path, updated_bytes))
        pending.append(prepared(project, record, text.encode('utf-8')))
        pending.append(prepared(project, state_path, state_bytes))
        if state_path.read_bytes() != state_bytes:
            raise ValueError('STATE.md changed during the mode switch; retry with the current document')
        os.replace(pending[0], state_path)
        try:
            os.replace(pending[1], record)
        except OSError:
            if state_path.read_bytes() == updated_bytes:
                os.replace(pending[2], state_path)
            raise
    finally:
        for path in pending:
            path.unlink(missing_ok=True)


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', nargs='?', help='solo, cross or saver; or autopilot or present (the presence switch)')
    parser.add_argument('sides', nargs='?', metavar='SIDES',
                        help='the note after the name: "family: X" for solo (default claude), "low: X" for saver')
    parser.add_argument('--project', type=Path, default=Path.cwd())
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument('--read-state', metavar='OUT',  # a string: a trailing separator names a folder
                            help='create a per-edit STATE.md snapshot with prefix OUT (in .myagentkit/ or the temporary folder); print SHA256 PATH')
    operations.add_argument('--replace-state', type=Path, metavar='FILE',
                            help='atomically publish the edited snapshot FILE, then delete it')
    parser.add_argument('--expect', metavar='SHA256', help='the sha256 --read-state printed for that snapshot')
    args = parser.parse_args()
    if args.name is not None and (args.read_state is not None or args.replace_state is not None
                                  or args.expect is not None):
        parser.error('a mode name cannot be combined with STATE operations')
    if args.replace_state is not None:
        if args.expect is None or re.fullmatch(r'[0-9a-fA-F]{64}', args.expect) is None:
            parser.error('--replace-state requires --expect with a 64-digit sha256')
    elif args.expect is not None:
        parser.error('--expect requires --replace-state')
    try:
        project = args.project.resolve()
        if (args.read_state, args.replace_state) != (None, None) and project != Path.cwd().resolve():
            raise ValueError('STATE operations run in the project root, without another --project')
        if args.read_state is not None:
            if args.read_state.endswith(('/', os.sep)) or Path(args.read_state).is_dir():
                raise ValueError('OUT is the snapshot name prefix, never a folder: ' + shown(args.read_state))
            snapshot, sha = read_state(project, private(project, Path(args.read_state)))
            print(sha + ' ' + str(snapshot))
        elif args.replace_state is not None:
            replace_state(project, private(project, args.replace_state), args.expect)
        else:
            if args.sides is not None and args.name is None:
                parser.error('SIDES needs a mode name')
            mode(project, args.name, args.sides)
    except (OSError, ValueError) as error:
        parser.exit(1, 'mode: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
