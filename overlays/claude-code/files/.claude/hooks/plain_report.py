#!/usr/bin/env python3
"""Stop: bounce a final message that names a session label the owner was never told about.

`docs/COMMUNICATION.md` ("Language and terms"): a task id, a round number or a verdict code
(`D-1`, `r2`, `Accept-MC`) never stands alone toward the owner. A written rule is forgotten
after a few turns; this hook is not. It reads the turn's final text from the hook input
(`last_assistant_message`), drops fenced blocks, backtick spans and words that are paths
(a `/` or `\\` in them), and exits 2 with the labels it found. A label in parentheses passes
once, beside its plain words ("the second review round (r2)"); a second one in parentheses
does not. The agent then rewrites the message in plain words.

It also bounces a final message whose last line ends with a question, or that names a
question as open ("open question", "açık soru"), outside code (#289; `docs/COMMUNICATION.md`,
"Questions and approvals"): an owner's question goes through the question tool, and a call
to it never ends a turn, so a turn's final text holds no asked question. The hook cannot see
whether the owner is present; the message it prints says what to do in either case. This
check needs no commit-msg grammar: a missing one turns off only the label check.

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


# Legacy local LABELS additions still work. New project patterns live outside synced hooks
# in .claude/plain_report_labels.json (a JSON list of regular-expression strings).
LABELS = (r'\bAccept-MC\b',)
# Any indent or blockquote marker: a fence inside a list item sits four or more spaces in.
# A backtick fence's info string has no backtick (CommonMark), so "```sh``` is" is a span.
FENCE = re.compile(r'[ \t>]*(`{3,}(?=[^`]*$)|~{3,}).*')
SPAN = re.compile(r'(`+)[^\n]*?(?<!`)\1(?!`)')
PARENS = re.compile(r'\([^()]*\)')
# "soru" but never "sorun" (a problem): "Açık sorun yok." is no question.
OPEN_QUESTION = re.compile(r'\bopen questions?\b|\bquestions? (?:is |are |remains? |still )+open\b'
                           r'|\baçık (?:bir )?soru(?!n)|\bsoru(?:lar)?(?:ı|ım)? (?:hâlâ |hala )?açık', re.I)
NO_OPEN_QUESTION = re.compile(r'\bno (?:more )?open questions?\b|\bopen questions?\W*(?:none|no)\b'
                              r'|\bno questions? (?:is |are |remains? )*open\b'
                              r'|\ball (?:the )?open questions? (?:are |were |have been )*(?:answered|closed|resolved)\b'
                              r'|\baçık (?:bir )?soru(?!n)\w*\W*(?:yok|kalmadı)', re.I)


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


def known_labels() -> set[str]:
    """Read registered entry ids once for this message, not once for each candidate."""
    root = Path(os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd())
    labels = set()
    token = r'(?:`|\*\*)?([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)?)(?:`|\*\*)?(?![A-Za-z0-9_-])'
    entry = r'(?:[-*+]|[0-9]+[.)]|#{1,6})[ \t]+(?:\[[ xX]\][ \t]+)?|\|[ \t]*'
    for name in ('STATE.md', 'BACKLOG.md'):
        try:
            body = (root / 'docs' / name).read_text(encoding='utf-8')
        except OSError:
            continue
        # An id leads an entry (list, heading or first table cell), or a plain "id:" line.
        # A mention in the entry's description never registers a label.
        for match in re.finditer(r'^[ \t]*(?:(?:' + entry + r')' + token + r'(?=[ \t:|]|$)|'
                                 + token + r'[ \t]*:)', body, re.M | re.I):
            labels.add((match[1] or match[2]).lower())
    return labels


def project_patterns() -> list[str]:
    """Load project-owned label shapes without editing a kit-owned commit hook."""
    root = Path(os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd())
    try:
        patterns = json.loads((root / '.claude/plain_report_labels.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    if not isinstance(patterns, list):
        return []
    valid = []
    for pattern in patterns:
        if isinstance(pattern, str):
            try:
                re.compile(pattern)
            except Exception:  # A bad project regex (including OverflowError) must not disable built-ins.
                continue
            valid.append(pattern)
    return valid


def bare_labels(text: str) -> list[str]:
    task, digit = task_patterns()
    registered = known_labels()
    patterns = ((rf'(?<![A-Za-z0-9_.-]){task}(?![A-Za-z0-9_-]|\.\d)', False),
                *((pattern, True) for pattern in (*LABELS, *project_patterns())))
    def is_label(label):
        if label == 'Accept-MC':
            return True
        if not re.search(digit, label):
            return False
        if label.lower() in registered:
            return True  # the project may name any canonical task id, including long prefixes
        if re.fullmatch(r'[a-f0-9]{7,}', label):
            return False  # abbreviated git hashes are not session labels
        # Only the kit's dashed review/worker shapes are inferred without registration.
        # Compact task ids (K4, L1b, r2) must head a project entry, just like P0 or H100.
        return bool(re.fullmatch(r'(?:[A-Z]-[0-9]+|v[0-9]+-[a-z][0-9]+)', label))

    prose = ' '.join(word for word in without_code(text).split() if '/' not in word and '\\' not in word)
    found = []
    for pattern, explicit in patterns:
        explained = []  # Overlapping task and project patterns must not count one mention twice.
        start = len(found)
        try:
            for match in re.finditer(pattern, PARENS.sub(' ', prose)):
                if (explicit or is_label(match.group())) and match.group() not in found:
                    found.append(match.group())
            for part in PARENS.findall(prose):
                for match in re.finditer(pattern, part):
                    if (explicit or is_label(match.group())) and match.group() in explained and match.group() not in found:
                        found.append(match.group())
                    explained.append(match.group())
        except Exception:
            if not explicit:
                raise
            del found[start:]  # Discard this project pattern's partial results, keeping earlier checks.
    return found


def unasked_question(text: str) -> bool:
    prose = without_code(text)
    lines = [line for line in prose.splitlines() if line.strip()]
    # The last line ends with ? or ？ followed only by marks, emoji or spaces.
    return bool(lines and re.search(r'[?？][^\w?？]*$', lines[-1])) \
        or bool(OPEN_QUESTION.search(NO_OPEN_QUESTION.sub(' ', prose)))


def main() -> None:
    if os.environ.get('MYAGENTKIT_ROLE') == 'worker':
        return
    data = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    if data.get('stop_hook_active'):
        return
    text = data.get('last_assistant_message') or ''
    said = []
    if unasked_question(text):
        said.append('BLOCKED: the message to the owner ends with a question or names one as open, in chat '
                    'text. While the owner is present, ask it with the question tool (AskUserQuestion: the '
                    'options, the recommended one first) and drop it from the text; while the owner is away, '
                    'park it in docs/STATE.md or an issue and say so without a question mark. Then send the '
                    'message again (docs/COMMUNICATION.md, "Questions and approvals"; core/docs/ in the kit).')
    try:
        found = bare_labels(text)
    except Exception:  # noqa: BLE001 - no commit-msg grammar: only the label check is off
        found = []
    if found:
        said.append('BLOCKED: the message to the owner names a session label with no plain words beside it: %s. '
                    'Say what each one is in the chat language ("the second review round"), keep the label '
                    'in parentheses at most once and only if the owner meets it in a file, then send the '
                    'message again (docs/COMMUNICATION.md, "Language and terms"; core/docs/ in the kit).'
                    % ', '.join(found))
    if said:
        print('\n'.join(said), file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - see the docstring
        pass
