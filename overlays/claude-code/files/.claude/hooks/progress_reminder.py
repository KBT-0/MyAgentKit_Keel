#!/usr/bin/env python3
"""PostToolUse: after five tool calls with no visible line, remind the agent to say what it does.

`docs/COMMUNICATION.md` ("Progress"): one sentence at a finding, a turn or a block, never a
long silence. Anthropic measured that a reminder after about five silent steps halved the
share of tasks with long silences; the threshold is a starting value for this kit.

The hook counts the tool calls in the transcript since the agent's last non-empty text block
and adds one line of context when a tool batch crosses a multiple of STEP (a parallel batch
may jump from four to seven). No state file: the transcript is the state. It reads only the
tail of the transcript, because it runs on every tool call. Silent on any error.
"""
import json
import sys

STEP = 5
TAIL = 512 * 1024  # bytes; a turn with five tool calls fits many times over


def silent_calls(path: str) -> tuple[int, int]:
    """Tool calls since the last visible text, and how many came in the last assistant record."""
    with open(path, 'rb') as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - TAIL))
        lines = stream.read().decode('utf-8', errors='replace').splitlines()
    if size > TAIL:
        lines = lines[1:]  # the first line is cut
    total = last = 0
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get('type') != 'assistant' or rec.get('isSidechain'):
            continue
        content = (rec.get('message') or {}).get('content')
        if not isinstance(content, list):
            continue
        if any(b.get('type') == 'text' and (b.get('text') or '').strip() for b in content if isinstance(b, dict)):
            total = 0  # the owner saw a line; a tool call in the same record comes after it
        last = sum(1 for b in content if isinstance(b, dict) and b.get('type') == 'tool_use')
        total += last
    return total, last


def main() -> None:
    data = json.load(sys.stdin)
    total, last = silent_calls(data['transcript_path'])
    if total >= STEP and total // STEP > (total - last) // STEP:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'PostToolUse',
            'additionalContext': '%d tool calls since the owner last saw a line from you. Say in one plain '
                                 'sentence, in the chat language, what you are doing now and what you found, '
                                 'then continue (docs/COMMUNICATION.md, "Progress").' % total}}))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001 - see the docstring
        pass
