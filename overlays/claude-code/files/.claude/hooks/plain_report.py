#!/usr/bin/env python3
"""Stop: bounce a final message that names a session label the owner was never told about.

`docs/COMMUNICATION.md` ("Language and terms"): a task id, a round number or a verdict code
(`D-1`, `r2`, `Accept-MC`) never stands alone toward the owner. A written rule is forgotten
after a few turns; this hook is not. It reads the turn's final text from the hook input
(`last_assistant_message`), drops fenced blocks, backtick spans and words that are paths
(a `/` or `\\` in them), and exits 2 with the labels it found. A label in parentheses passes
once, beside its plain words ("the second review round (r2)"); a second one in parentheses
does not. The agent then rewrites the message in plain words.

Once per turn: `stop_hook_active` is true when the turn already continued because of a stop
hook, and the hook steps aside (Claude Code also caps consecutive blocks at eight). A worker
session started by `scripts/spawn_worker.sh` (MYAGENTKIT_ROLE=worker) writes for the lead and
is not checked. Silent on any error: a broken input must never hold a turn open.
"""
import json
import os
import re
import sys
from pathlib import Path

# Source: https://code.claude.com/docs/en/hooks (2026-10-15), B10 inv3#7.
# The vendor permits eight consecutive blocks. The kit deliberately stops at one;
# the real commit gate is pre-commit, rather than this communication reminder.
def task_patterns() -> tuple[str, str]:
    """Read the canonical grammar from the installed or source commit hook."""
    for parent in Path(__file__).resolve().parents:
        for relative in ('.githooks/commit-msg', 'core/.githooks/commit-msg'):
            source = parent / relative
            if source.is_file():
                body = source.read_text(encoding='utf-8')
                return tuple(re.search(r"^" + name + r"='([^']+)'$", body, re.M)[1]
                             for name in ('TASK_ID_PATTERN', 'TASK_ID_DIGIT_PATTERN'))
    raise FileNotFoundError('canonical commit-msg task grammar is missing')


# Projects extend the task grammar in commit-msg (B10 inv3/(f), inv2#151).
LABELS = (r'\bAccept-MC\b',)
# Any indent or blockquote marker: a fence inside a list item sits four or more spaces in.
# A backtick fence's info string has no backtick (CommonMark), so "```sh``` is" is a span.
FENCE = re.compile(r'[ \t>]*(`{3,}(?=[^`]*$)|~{3,}).*')
SPAN = re.compile(r'(`+)[^\n]*?(?<!`)\1(?!`)')
PARENS = re.compile(r'\([^()]*\)')


def without_code(text: str) -> str:
    """Drop fences closed by the same character and at least the opening length."""
    lines, opener = [], None
    for line in text.splitlines(keepends=True):
        match = FENCE.fullmatch(line.rstrip('\r\n'))
        if opener is None:
            if match:
                opener = match[1]
                lines.append(' ')
            else:
                lines.append(line)
        elif re.fullmatch(r'[ \t>]*' + re.escape(opener[0]) + '{' + str(len(opener)) + r',}[ \t]*',
                          line.rstrip('\r\n')):
            opener = None
    return SPAN.sub(' ', ''.join(lines))


def known_label(label: str) -> bool:
    root = Path(os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd())
    for name in ('STATE.md', 'BACKLOG.md'):
        try:
            body = (root / 'docs' / name).read_text(encoding='utf-8')
        except OSError:
            continue
        # An id leads an entry (list, heading or first table cell), or a plain "id:" line.
        # A mention in the entry's description never registers a label.
        token = r'(?:`|\*\*)?' + re.escape(label) + r'(?:`|\*\*)?(?![A-Za-z0-9_-])'
        entry = r'(?:[-*+]|[0-9]+[.)]|#{1,6})[ \t]+(?:\[[ xX]\][ \t]+)?|\|[ \t]*'
        if re.search(r'^[ \t]*(?:(?:' + entry + r')' + token + r'(?=[ \t:|]|$)|'
                     + token + r'[ \t]*:)', body, re.M | re.I):
            return True
    return False


def bare_labels(text: str) -> list[str]:
    task, digit = task_patterns()
    patterns = (rf'(?<![A-Za-z0-9_.-]){task}(?![A-Za-z0-9_-]|\.\d)', *LABELS)
    def is_label(label):
        if label == 'Accept-MC':
            return True
        if not re.search(digit, label):
            return False
        if known_label(label):
            return True  # the project may name any canonical task id, including long prefixes
        if re.fullmatch(r'[a-f0-9]{7,}', label):
            return False  # abbreviated git hashes are not session labels
        # Prose is not a commit trailer: a label has one letter before its first digit or dash
        # (K4, L1b, K7-a, D-5, v011-d5); UTF-8, SHA-256, win32, cp1252, Python3, IPv6 are words.
        if not re.match(r'[A-Za-z][^A-Za-z]', label):
            return False
        # Lowercase without a lettered dash part (x86, e2e, i18n, r2) counts only when the
        # project's STATE.md or BACKLOG.md names it.
        return label[0].isupper() or bool(re.search(r'-.*[A-Za-z]', label))

    prose = ' '.join(word for word in without_code(text).split() if '/' not in word and '\\' not in word)
    found, explained = [], []
    for pattern in patterns:
        for match in re.finditer(pattern, PARENS.sub(' ', prose)):
            if is_label(match.group()) and match.group() not in found:
                found.append(match.group())
        for part in PARENS.findall(prose):
            for match in re.finditer(pattern, part):
                if is_label(match.group()) and match.group() in explained and match.group() not in found:
                    found.append(match.group())
                explained.append(match.group())
    return found


def main() -> None:
    if os.environ.get('MYAGENTKIT_ROLE') == 'worker':
        return
    data = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    if data.get('stop_hook_active'):
        return
    found = bare_labels(data.get('last_assistant_message') or '')
    if not found:
        return
    print('BLOCKED: the message to the owner names a session label with no plain words beside it: %s. '
          'Say what each one is in the chat language ("the second review round"), keep the label '
          'in parentheses at most once and only if the owner meets it in a file, then send the '
          'message again (docs/COMMUNICATION.md, "Language and terms"; core/docs/ in the kit).'
          % ', '.join(found), file=sys.stderr)
    sys.exit(2)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - see the docstring
        pass
