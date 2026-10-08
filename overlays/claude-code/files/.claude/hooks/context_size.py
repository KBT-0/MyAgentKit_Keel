#!/usr/bin/env python3
"""UserPromptSubmit: tell the agent when the session's context has grown past the hand-off line.

Every request re-sends the whole context, so a lead at 450k pays several times what a fresh
one at 60k pays, on every turn (`docs/WORKFLOW.md`, "Worker cost", rule 8). The context is the
last API request's input plus cache read plus cache write, read from the transcript.

Past LINE the hook adds one line to the agent's context, once per STEP: at 200k, 250k, 300k...
Which of /compact and a hand-off is cheaper depends on what STATE holds and where the work goes
next, which a hook cannot see, so the agent chooses and says so. Silent on any error: a broken
transcript must never block a prompt.
"""
import json
import sys

LINE = 200_000  # a fresh session (~60k) pays back a hand-off in under ten turns from here
STEP = 50_000


def band(ctx: int) -> int:
    return -1 if ctx < LINE else (ctx - LINE) // STEP


def is_prompt(rec: dict) -> bool:
    """A prompt the person typed, not a tool result or an injected meta record."""
    if rec.get('type') != 'user' or rec.get('isMeta') or rec.get('isSidechain'):
        return False
    content = (rec.get('message') or {}).get('content')
    return isinstance(content, str) or (isinstance(content, list) and not any(
        isinstance(c, dict) and c.get('type') == 'tool_result' for c in content))


def sizes(path: str) -> tuple[int, int]:
    """(context when the previous turn began, context now)."""
    last = anchor = 0
    pending = None
    with open(path, encoding='utf-8', errors='replace') as stream:
        for line in stream:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if is_prompt(rec):
                pending = last
                continue
            msg = rec.get('message') or {}
            usage = msg.get('usage')
            if rec.get('type') != 'assistant' or rec.get('isSidechain') or not usage or msg.get('model') == '<synthetic>':
                continue
            # The current prompt may already be written; the previous turn's anchor is the one
            # that some request followed.
            if pending is not None:
                anchor, pending = pending, None
            last = (usage.get('input_tokens', 0) + usage.get('cache_read_input_tokens', 0)
                    + usage.get('cache_creation_input_tokens', 0))
    return anchor, last


def main() -> None:
    anchor, ctx = sizes(json.load(sys.stdin)['transcript_path'])
    if band(ctx) > band(anchor):
        print(f'Context is {ctx // 1000}k tokens (line {LINE // 1000}k); every turn re-sends it. Before this '
              'task, recommend ONE to the owner in one line with this number and the reason: /compact '
              'when docs/STATE.md and the open operation files already hold what matters and the work '
              'in flight continues; a hand-off (update STATE, write the handoff, fresh session) when '
              'the work changes direction, a batch has just closed, or most of the context is detail '
              'of finished work. Neither is the default (docs/WORKFLOW.md, "Worker cost", rule 8).')


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001 - see the docstring
        pass
