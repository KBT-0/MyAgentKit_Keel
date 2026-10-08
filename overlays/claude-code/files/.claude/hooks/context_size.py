#!/usr/bin/env python3
"""UserPromptSubmit: tell the agent when the session's context has grown past the hand-off line.

Every request re-sends the whole context, so a lead at 450k pays several times what a fresh
one at 60k pays, on every turn (`docs/WORKFLOW.md`, "Worker cost", rule 8). The context is the
last API request's input plus cache read plus cache write, read from the transcript; a
compaction boundary resets it until the next request.

Past LINE the hook adds one line to the agent's context, once per STEP: at 200k, 250k, 300k...
The last step it named is kept beside the transcript (`<session>.context-step`, in the
user's own Claude folder, not a shared temporary one), so a retried prompt or one that
reached no request does not repeat it, and a smaller context (after /compact) arms it
again. Which of /compact and a hand-off is cheaper depends on what STATE holds and where the
work goes next, which a hook cannot see, so the agent chooses and says so. Silent on any
error: a broken transcript must never block a prompt.
"""
import json
from pathlib import Path
import sys

LINE = 200_000  # a fresh session (~60k) pays back a hand-off in under ten turns from here
STEP = 50_000


def band(ctx: int) -> int:
    return -1 if ctx < LINE else (ctx - LINE) // STEP


def context(path: Path) -> int:
    """The last request's context, or 0 when a compaction came after it."""
    last = 0
    with open(path, encoding='utf-8', errors='replace') as stream:
        for line in stream:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get('type') == 'system' and rec.get('subtype') == 'compact_boundary':
                last = 0
                continue
            msg = rec.get('message')
            usage = msg.get('usage') if isinstance(msg, dict) else None
            if rec.get('type') != 'assistant' or rec.get('isSidechain') or not isinstance(usage, dict) \
                    or msg.get('model') == '<synthetic>':
                continue
            # The API may send null for a counter it did not use.
            last = sum(usage.get(k) or 0 for k in
                       ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'))
    return last


def main() -> None:
    transcript = Path(json.load(sys.stdin)['transcript_path'])
    ctx = context(transcript)
    state = transcript.with_suffix('.context-step')
    try:
        said = int(state.read_text())
    except (OSError, ValueError):
        said = -1
    now = band(ctx)
    if now != said:
        state.write_text(str(now))
    if now > said:
        print(f'Context is {ctx // 1000}k tokens (line {LINE // 1000}k); every turn re-sends it. In this '
              "turn's closing summary, recommend ONE to the owner in one line with this number and the "
              'reason: /compact when docs/STATE.md and the open operation files already hold what '
              'matters and the work in flight continues; a hand-off (update STATE, write the handoff, '
              'fresh session) when the work changes direction, a batch has just closed, or most of '
              'the context is detail of finished work. Neither is the default (docs/WORKFLOW.md, '
              '"Worker cost", rule 8).')


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001 - see the docstring
        pass
