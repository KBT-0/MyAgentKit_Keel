#!/usr/bin/env python3
"""PostToolUse: after five tool calls with no visible line, remind the agent to say what it does.

`docs/COMMUNICATION.md` ("Progress"): one sentence at a finding, a turn or a block, never a
long silence. Anthropic measured that a reminder after about five silent steps halved the
share of tasks with long silences; the threshold is a starting value for this kit.

The hook counts the tool calls in the transcript since the agent's last non-empty text block
(or the last compaction) and adds one line of context each time that count passes a multiple
of STEP. Claude Code writes one record per content block, a parallel batch runs this hook once
per call, and a sub-agent's calls may see the lead's frozen transcript; so the count at the
last nudge is kept beside the transcript (`<session>.progress-step`, with the id of the record
the count started from) and the same count never nudges twice. A competing call stays silent.
The transcript may lag the turn by a record or two, so a nudge can come one call late.
At most three nudges are emitted per silent interval; text or compaction resets the limit.
It saves a byte offset on every call and reads at least everything appended since that offset,
so a large tool result cannot hide a visible line between calls. Silent on any error.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

# KARARLAR B08 inv1#253: Sonnet 5.5 prompting guide and Claude Code costs
# (2026-10-15): stop after the second or third reminder; five is a starting value.
MAX_NUDGES = 3
STEP = 5
RECOUNT = 512 * 1024  # re-read small transcripts; larger ones resume at the saved offset


def silent_calls(path: Path, saved: dict) -> tuple[int, object, int]:
    """Count from the beginning or a saved record boundary; never skip unread bytes."""
    with open(path, 'rb') as stream:
        stream.seek(0, 2)
        size = stream.tell()
        offset = saved.get('offset', 0)
        if offset > size:  # a truncated transcript starts over
            saved, offset = {}, 0
        start = offset if size > RECOUNT else 0
        stream.seek(start)
        lines = []
        while True:
            offset = stream.tell()
            line = stream.readline()
            if not line.endswith(b'\n'):
                break  # a partial record is read again on the next call
            lines.append(line.decode('utf-8', errors='replace'))
    total, mark = (saved['total'], saved['mark']) if start else (0, None)
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get('isSidechain'):
            continue
        if rec.get('type') == 'system' and rec.get('subtype') == 'compact_boundary':
            total, mark = 0, rec.get('uuid')
            continue
        content = (rec.get('message') or {}).get('content') if rec.get('type') == 'assistant' else None
        if not isinstance(content, list):
            continue
        if any(b.get('type') == 'text' and (b.get('text') or '').strip() for b in content if isinstance(b, dict)):
            total, mark = 0, rec.get('uuid')  # the owner saw a line; a tool call in the same record comes after it
        total += sum(1 for b in content if isinstance(b, dict) and b.get('type') == 'tool_use')
    return total, mark, offset


def main() -> None:
    transcript = Path(json.loads(sys.stdin.buffer.read().decode('utf-8'))['transcript_path'])
    state = transcript.with_suffix('.progress-step')
    # The context_size.py lock: closing the file releases it, even on a kill.
    with open(transcript.with_suffix('.progress-lock'), 'a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            saved = json.loads(state.read_text(encoding='utf-8'))
            said = saved['said']
            if (type(said) is not int or said < 0 or 'mark' not in saved
                    or any(type(saved.get(key)) is not int or saved[key] < 0 for key in ('offset', 'total'))):
                raise TypeError(saved)
            nudges = saved.get('nudges', min(said // STEP, MAX_NUDGES))
            if type(nudges) is not int or not 0 <= nudges <= MAX_NUDGES:
                raise TypeError(saved)
        except (OSError, ValueError, KeyError, TypeError):
            saved, said, nudges = {}, None, 0
        total, mark, offset = silent_calls(transcript, saved)
        if saved:
            if saved['mark'] != mark or said > total or saved['offset'] > offset:
                said, nudges = None, 0  # visible text, compaction or truncation starts a new count
        nudge = nudges < MAX_NUDGES and total // STEP > (said or 0) // STEP
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=state.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'said': total if nudge else (said or 0), 'mark': mark,
                       'nudges': nudges + int(nudge), 'total': total, 'offset': offset}, stream)
        try:
            os.replace(temporary, state)
        finally:
            temporary.unlink(missing_ok=True)
    if not nudge:
        return
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PostToolUse',
        'additionalContext': '%d tool calls since the owner last saw a line from you. Say in one plain '
                             'sentence, in the chat language, what you are doing now and what you found, '
                             'then continue (docs/COMMUNICATION.md, "Progress"; core/docs/ in the kit).' % total}}))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001 - see the docstring
        pass
