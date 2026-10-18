#!/usr/bin/env python3
"""UserPromptSubmit: tell the agent when the session's context has grown past the hand-off line.

progress_reminder.py (PostToolUse) runs the same check through `notice()`, so a long autonomous
turn meets the band when it crosses it, not at the owner's next prompt (#138). Both share the
step file, so each step is named once. A large transcript is read from the byte offset the
last check saved (progress_reminder.py's method): a full read of 33 MB took 0.9 s.

Every request re-sends the whole context, and accuracy falls as it grows (`docs/WORKFLOW.md`,
"Worker cost", rule 8: a band, yellow at 200k, red at 300k, ceiling at 400k). The context is
the last API request's input plus cache read plus cache write, read from the transcript; a
compaction boundary resets it until the next request.

Past LINE the hook adds one line to the agent's context, once per STEP: at 200k, 250k, 300k...,
opening with the band the size is in.
The last step it named is kept beside the transcript (`<session>.context-step`, in the
user's own Claude folder, not a shared temporary one), so a retried prompt or one that
reached no request does not repeat it. A compaction boundary arms it again; a smaller
context alone does not. Which of /compact and a hand-off is cheaper depends on what STATE
holds and where the work goes next, which a hook cannot see, so the agent chooses and says
so; after a compaction it can only be a hand-off, since a second summary drifts. Silent on any error: a broken transcript must never block a prompt.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

LINE = 200_000  # yellow: plan the cut
RED = 300_000  # cut at the next clean stop
CEILING = 400_000  # stop now
STEP = 50_000
RECOUNT = 512 * 1024  # re-read small transcripts; larger ones resume at the saved offset
BANDS = ((CEILING, 'ceiling (400k): stop now and secure the work (commit, STATE, handoff) '
                   'without waiting for a clean stop'),
         (RED, 'red (300k): cut at the next clean stop; start no new round'),
         (LINE, 'yellow (200k): plan the cut; start no new round, let the running batch finish, '
                'commit, and keep docs/STATE.md and the handoff current'))
COMPACT = ("/compact keep the open decisions, the binding rules, the changed files, the next step "
           "and the owner's words verbatim")


def band(ctx: int) -> int:
    return -1 if ctx < LINE else (ctx - LINE) // STEP


def band_word(ctx: int) -> str:
    """The watcher's label uses the notice's thresholds and words."""
    return next((text.split()[0] for floor, text in BANDS if ctx >= floor), '')


def context(path: Path, *, require_request: bool = False) -> tuple[int, int]:
    """The last request's context (0 after a boundary), and the compaction count."""
    last, compactions, known, _ = scan(Path(path))
    if require_request and not known:
        raise ValueError('no request or compaction boundary in transcript')
    return last, compactions


def scan(path: Path, saved: dict | None = None) -> tuple[int, int, bool, int]:
    """(last, compactions, known, offset): from the start, or from a saved record boundary."""
    with open(path, 'rb') as stream:
        size = stream.seek(0, 2)
        start = (saved or {}).get('offset', 0)
        if start > size or size <= RECOUNT:
            start = 0  # a small or truncated transcript is read again whole
        last, compactions, known = (saved['last'], saved['compactions'], saved['known']) if start else (0, 0, False)
        offset = stream.seek(start)
        for raw in stream:
            if not raw.endswith(b'\n'):
                break  # a partial record is read again on the next call
            offset += len(raw)
            line = raw.decode('utf-8', errors='replace')
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get('type') == 'system' and rec.get('subtype') == 'compact_boundary':
                last = 0
                compactions += 1
                known = True
                continue
            msg = rec.get('message')
            usage = msg.get('usage') if isinstance(msg, dict) else None
            if rec.get('type') != 'assistant' or rec.get('isSidechain') or not isinstance(usage, dict) \
                    or msg.get('model') == '<synthetic>':
                continue
            # The API may send null for a counter it did not use.
            last = sum(usage.get(k) or 0 for k in
                       ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'))
            known = True
    return last, compactions, known, offset


def notice(transcript: Path) -> str:
    """The band line once per step, else ''."""
    state = transcript.with_suffix('.context-step')
    # A competing prompt stays silent. Closing the file releases the lock, even on a kill.
    # Keep the lock file: unlinking it lets overlapping prompts lock different files.
    with open(transcript.with_suffix('.context-lock'), 'a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            saved = json.loads(state.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            saved = None
        resume = saved if (isinstance(saved, dict) and type(saved.get('known')) is bool and all(
            type(saved.get(key)) is int and saved[key] >= 0 for key in ('offset', 'last', 'compactions'))) else None
        ctx, compactions, known, offset = scan(transcript, resume)
        # Before the step became a record the state held only an integer step.
        legacy = type(saved) is int
        try:
            said, previous = (saved, compactions) if legacy else (saved['step'], saved['compactions'])
            # Any other type (null, "0", true) is a missing file: compared, it raised and silenced the hook.
            if type(said) is not int or type(previous) is not int:
                raise TypeError(said, previous)
        except (KeyError, TypeError):
            said, previous = -1, 0
        if previous != compactions:
            said = -1
        now = band(ctx)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=state.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'step': max(now, said), 'compactions': compactions, 'offset': offset, 'last': ctx,
                       'known': known}, stream)
        try:
            os.replace(temporary, state)
        finally:
            temporary.unlink(missing_ok=True)
    if now <= said:
        return ''
    if compactions:
        advice = ('This session was compacted already, and a summary of a summary drifts: in this '
                  "turn's closing summary, recommend a hand-off (update STATE, write the handoff, "
                  'fresh session) to the owner in one line with this number, never a second /compact')
    else:
        advice = ("In this turn's closing summary, recommend ONE to the owner in one line with this "
                  'number and the reason: /compact when docs/STATE.md and the open operation files '
                  'already hold what matters and the work in flight continues, never bare but as '
                  f'"{COMPACT}"; a hand-off (update STATE, write the handoff, fresh session) when the '
                  'work changes direction, a batch has just closed, or most of the context is detail '
                  'of finished work. Neither is the default')
    return (f'Context is {ctx // 1000}k tokens, ' + next(text for floor, text in BANDS if ctx >= floor)
            + '. Every turn re-sends it, and accuracy falls as it grows. ' + advice
            + ' (docs/WORKFLOW.md, "Worker cost", rule 8).')


def main() -> None:
    said = notice(Path(json.loads(sys.stdin.buffer.read().decode('utf-8'))['transcript_path']))
    if said:
        print(said)


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--line']:
            print(LINE)
        elif len(sys.argv) == 3 and sys.argv[1] == '--band':
            print(band_word(int(sys.argv[2])))
        else:
            main()
    except Exception:  # noqa: BLE001 - see the docstring
        pass
