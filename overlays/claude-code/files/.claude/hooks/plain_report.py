#!/usr/bin/env python3
"""Stop: bounce a final message that names a session label the owner was never told about.

`docs/COMMUNICATION.md` ("Language and terms"): a task id, a round number or a verdict code
(`D-1`, `r2`, `Accept-MC`) never stands alone toward the owner. A written rule is forgotten
after a few turns; this hook is not. It reads the turn's final text from the hook input
(`last_assistant_message`), drops fenced blocks and backtick spans, and exits 2 with the
labels it found. The agent then rewrites the message in plain words.

Once per turn: `stop_hook_active` is true when the turn already continued because of a stop
hook, and the hook steps aside (Claude Code also caps consecutive blocks at eight). Silent
on any error: a broken input must never hold a turn open.
"""
import json
import re
import sys

# The kit's own label shapes. A project adds its own here; the interview says so.
LABELS = (
    r'\b[A-Z]-\d+\b',          # task ids: D-1, N-3
    r'\br\d+\b',               # review rounds: r2
    r'\bAccept-MC\b',          # verdict codes
)
CODE = re.compile(r'```.*?```|`[^`\n]*`', re.S)


def bare_labels(text: str) -> list[str]:
    prose = CODE.sub(' ', text)
    found = []
    for pattern in LABELS:
        for match in re.finditer(pattern, prose):
            if match.group() not in found:
                found.append(match.group())
    return found


def main() -> None:
    data = json.load(sys.stdin)
    if data.get('stop_hook_active'):
        return
    found = bare_labels(data.get('last_assistant_message') or '')
    if not found:
        return
    print('BLOCKED: the message to the owner names a session label with no plain words beside it: %s. '
          'Say what each one is in the chat language ("the second review round"), keep the label '
          'in parentheses at most once and only if the owner meets it in a file, then send the '
          'message again (docs/COMMUNICATION.md, "Language and terms").' % ', '.join(found),
          file=sys.stderr)
    sys.exit(2)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - see the docstring
        pass
