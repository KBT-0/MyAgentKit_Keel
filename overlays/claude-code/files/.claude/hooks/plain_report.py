#!/usr/bin/env python3
"""Stop: bounce a final message that names a session label the owner was never told about.

`docs/COMMUNICATION.md` ("Language and terms"): a task id, a round number or a verdict code
(`D-1`, `r2`, `Accept-MC`) never stands alone toward the owner. A written rule is forgotten
after a few turns; this hook is not. It reads the turn's final text from the hook input
(`last_assistant_message`), drops fenced blocks, backtick spans and words that are paths
(a `\\`, or a `/` between parts that are not all ids: "N4/M2" is two ids, #210), and exits 2
with the labels it found. A backtick span that holds only a registered id is read as that id:
the backticks do not explain it. A label in parentheses passes once, beside its plain words
("the second review round (r2)"); a second one in parentheses does not. A compact id (K4, r2)
is a label only when it leads an entry in docs/STATE.md or docs/BACKLOG.md; the dashed shapes
(D-1) always are. Trade-offs, accepted: an unregistered sibling (B1 beside a registered B2)
passes, a word that matches a registered id or the dashed shape ("an M2 chip", "F-35") is
bounced, and an indented code block is read as prose. The Stop hook runs after the owner has
read the message, so the agent sends one short line that explains each label, never the whole
message again (#209). A project adds label shapes in `.claude/plain_report_labels.json`.

It also bounces a final message whose last line ends with a question, or that names a
question as open ("open question", "açık soru"), outside code (#289; `docs/COMMUNICATION.md`,
"Questions and approvals"): an owner's question goes through the question tool, and a call
to it never ends a turn, so a turn's final text holds no asked question. Under the autopilot
switch (context_size.away(): `.myagentkit/presence` says away) the message says to queue the
question in the report; otherwise it says what to do in either case, since an owner away
without that record is not visible to a hook. This check needs no commit-msg grammar: a
missing one turns off only the label check.

It also bounces a final message with no fenced block that names the hand-off when the turn
wrote a hand-off file (a Write or Edit of a file whose name, or whose folder's name, starts
with "handoff", as in handoff-65.md or docs/handoffs/, since the owner's last prompt, read from
the transcript's tail; a name that only holds the word, as a no-handoff-rule.md memory, is none;
a compaction's summary is no prompt; a worker's brief, result or question, before_compact.worker_file,
is none): the owner opens the next session and needs the
exact text to paste (`docs/COMMUNICATION.md`, "Handoff"). The trigger is that write, not the
message's wording, which no pattern reads reliably. Not under the autopilot switch: nobody
opens a session then. The hook runs after the owner has read the message, so the prompt
arrives as one more short message; the rule text asks for it in the first one.

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
        # The kit's source first: the kit root's .githooks/commit-msg is a wrapper that runs the
        # installed copy's (scripts/kit_hook.sh) and holds no grammar.
        for relative in ('core/.githooks/commit-msg', '.githooks/commit-msg'):
            source = parent / relative
            if source.is_file():
                body = source.read_text(encoding='utf-8')
                found = [re.search(r"^" + name + r"='([^']+)'$", body, re.M)
                         for name in ('TASK_ID_PATTERN', 'TASK_ID_DIGIT_PATTERN')]
                if all(found):  # a file without the grammar is no commit hook of the kit's: look further up
                    return tuple(m[1] for m in found)
    raise FileNotFoundError('canonical commit-msg task grammar is missing')


# Legacy local LABELS additions still work. Project patterns live in
# .claude/plain_report_labels.json (a JSON list of regular-expression strings), so a kit update
# of this file never carries them away.
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


HANDOFF = re.compile(r'hand-?off', re.I)
# A hand-off file's or folder's name starts with the word (handoff-65.md, docs/handoffs/); no-handoff-x.md is a note.
HANDOFF_NAME = re.compile(r'hand-?offs?(?![a-z])', re.I)
RULE_DOCS = {'HANDOFF.md', 'HANDOFF_KIT.md'}  # the kit's own rule docs: editing them hands nothing off
# shortcut: only the transcript's last 4 MB is read; a longer turn misses its hand-off write (no bounce), widen if seen.
TAIL = 4 * 1024 * 1024
# Harness notes (isMeta user records) that wake an idle session start a turn of their own; the rest
# (Stop hook feedback, an image, a skill body, the usage-limit grace note) arrive inside one.
# Prefixes as Claude Code 2.1.x writes them, counted in 60 of this machine's transcripts (review r328).
WAKES = ('Another Claude session sent a message', 'Your claude.ai usage limit has reset',
         '[Cross-session idle notice]', '[Earlier usage-limit notes no longer apply')


def split_fences(text: str) -> tuple[str, str]:
    """Text outside and inside fences closed by the same character and at least the opening length."""
    outside, inside, opener = [], [], None
    for line in text.splitlines(keepends=True):
        bare = line.rstrip('\r\n')
        if opener is None:
            match = FENCE.fullmatch(bare)
            if match:
                opener = match[1]
                outside.append(' ')
            else:
                outside.append(line)
        elif re.fullmatch(r'[ \t>]*' + re.escape(opener[0]) + '{' + str(len(opener)) + r',}[ \t]*', bare):
            opener = None
        else:
            inside.append(line)
    return ''.join(outside), ''.join(inside)


def without_code(text: str) -> str:
    return SPAN.sub(' ', split_fences(text)[0])


def worker_file(name: str) -> bool:
    """before_compact.worker_file, the hooks' one test for a worker's brief or result; False when it
    is not beside this file (an older sync: the write counts, as before)."""
    try:
        sys.dont_write_bytecode = True  # no untracked __pycache__ beside the synced hooks
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import before_compact
        return before_compact.worker_file(name)
    except Exception:  # noqa: BLE001 - an older or missing before_compact.py
        return False


def wrote_handoff(transcript) -> bool:
    """A Write or Edit of a file named handoff*, or of a Markdown file in a folder so named
    (docs/handoffs/), since the owner's last prompt or a wake-up, from the transcript's tail."""
    try:
        with open(transcript, 'rb') as file:
            file.seek(max(0, os.fstat(file.fileno()).st_size - TAIL))
            lines = file.read().splitlines()
    except (OSError, TypeError, ValueError):
        return False
    for raw in reversed(lines):
        try:
            record = json.loads(raw)
            content = record['message']['content']
        except (ValueError, KeyError, TypeError):
            continue
        blocks = content if isinstance(content, list) else []
        if record.get('isMeta') and record.get('type') == 'user' and (content if isinstance(content, str) else ''.join(
                b.get('text', '') for b in blocks if isinstance(b, dict))).lstrip().startswith(WAKES):
            return False  # a wake-up: the turn starts here, as at the owner's prompt
        if record.get('isCompactSummary') or record.get('isMeta'):
            continue  # a compaction's summary or a harness note inside the turn, not the owner's prompt
        if record.get('type') == 'user' and not any(isinstance(b, dict) and b.get('type') == 'tool_result'
                                                     for b in blocks):
            return False  # the owner's prompt: the turn starts here
        for block in blocks:
            if isinstance(block, dict) and block.get('type') == 'tool_use' \
                    and block.get('name') in ('Write', 'Edit', 'MultiEdit') \
                    and (path := Path(str((block.get('input') or {}).get('file_path', '')))).name not in RULE_DOCS \
                    and not worker_file(path.name) \
                    and (HANDOFF_NAME.match(path.name) or HANDOFF_NAME.match(path.parent.name) and path.suffix.lower() == '.md'):
                return True
    return False


def handoff_without_prompt(text: str, transcript) -> bool:
    """This turn wrote a hand-off file, and no fenced block in the final message names it."""
    return not HANDOFF.search(split_fences(text)[1]) and wrote_handoff(transcript)


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

    text = SPAN.sub(lambda m: m[0].strip('`') if m[0].strip('`').strip().lower() in registered else m[0], text)

    def words():
        for word in without_code(text).split():
            if '\\' in word or '/' in word and not all(
                    re.fullmatch(task, part) for part in word.strip('.,;:!?()').split('/')):
                continue  # a path
            yield word.replace('/', ' ')
    prose = ' '.join(words())
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


def away() -> bool:
    """context_size.away(), the hooks' one presence reader; False when it is not beside this file."""
    try:
        sys.dont_write_bytecode = True  # no untracked __pycache__ beside the synced hooks
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import context_size
        return context_size.away()
    except Exception:  # noqa: BLE001 - an older or missing context_size.py: the general message
        return False


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
    if unasked_question(text) and away():
        said.append('BLOCKED: the message ends with a question or names one as open, and the owner is away '
                    '(autopilot): nothing waits on a question. Queue it under Questions in the report '
                    '(.myagentkit/autopilot/<date>.md, docs/AUTOPILOT.md) with your recommendation, decide what the '
                    'rules settle, keep going, and say so in one line without a question mark (docs/WORKFLOW.md, '
                    '"autopilot, the owner-away switch").')
    elif unasked_question(text):
        said.append('BLOCKED: the message to the owner ends with a question or names one as open, in chat '
                    'text. While the owner is present, ask it with the question tool (AskUserQuestion: the '
                    'options, the recommended one first); while the owner is away, park it in docs/STATE.md or an '
                    'issue and say so in one line without a question mark. The owner has already read the '
                    'message: do not send it again (docs/COMMUNICATION.md, "Questions and approvals"; '
                    'core/docs/ in the kit).')
    if not away() and handoff_without_prompt(text, data.get('transcript_path')):
        said.append('BLOCKED: this turn wrote a hand-off file, and the message gives the owner no opening prompt. The owner '
                    'has already read the message: do not send it again. Send one short line and a fenced code block '
                    'with the exact text the owner pastes into the new session, in the chat language (the hand-off '
                    'file to read and "go on"), and the model to open it on (full model id), and close every '
                    'hand-off that way. If the turn only recorded progress in a hand-off file and proposes no hand-off, '
                    'say so in one line and give no prompt (docs/COMMUNICATION.md, "Handoff"; core/docs/ in the kit).')
    try:
        found = bare_labels(text)
    except Exception:  # noqa: BLE001 - no commit-msg grammar: only the label check is off
        found = []
    if found:
        said.append('BLOCKED: the message to the owner names a session label with no plain words beside it: %s. '
                    'The owner has already read the message: do not send it again. Send one short line that says '
                    'what each one is in the chat language, in this shape: %s. Write the next messages with the '
                    'plain words and the label in parentheses at most once; a backtick does not explain a label '
                    '(docs/COMMUNICATION.md, "Language and terms"; core/docs/ in the kit).'
                    % (', '.join(found), '; '.join('%s = <what it is>' % label for label in found)))
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
