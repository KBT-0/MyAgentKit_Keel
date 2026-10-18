#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""The lead's errors by context size: the data that tests the context band.

Usage: context_buckets.py [--since YYYY-MM-DD] [PROJECT_DIR | SESSION.jsonl ...]

With no session file, reads every transcript under ~/.claude/projects/<encoded project
dir>/ (the current directory by default); --since drops records before that day. The
band (docs/WORKFLOW.md, "Worker cost", rule 8) and the decision rule this feeds are in
docs/ACCEPTANCE.md of the kit. The context is read as the context hook reads it: the
last request's input plus cache read plus cache write, zero after a compaction.

Counted per bucket (0-100k, 100-200k, 200-300k, 300-400k, 400k+), per 100 lead requests:
  route   worker-route hook refusals (an Agent call without a model or an effort)
  attrib  commit-msg refusals of an AI-attribution trailer
  push    `git push` commands, each listed with its session, time and command; the owner
          marks which were not asked for, and only those are errors
  fix     owner prompts carrying the hand mark `#fix`: the owner's explicit corrections
  phrase  informational phrase-matched correction proxy beside the explicit mark
Then, for each compaction, report 20 requests before/after plus 5- and 30-request cuts.
Not counted: the chat language, identifiers in backticks and bare labels need a reader,
not a pattern. Cost: agent_cost.py.
"""
from __future__ import annotations
import collections
import json
import re
from pathlib import Path
import sys

from agent_cost import project_folder

KINDS = ('route', 'attrib', 'push', 'fix', 'phrase')
BUCKETS = ('0-100k', '100-200k', '200-300k', '300-400k', '400k+')
SIGNS = {'route': 'this Agent call names no', 'attrib': 'crediting an AI tool'}
MARK = '#fix'
# B07 inv2#131: the 20-request window and 5-/30-request cuts are the kit's own
# diagnostic choices, not measured thresholds.
WINDOW = 20
SLICES = (5, 30)
# B07 inv2#132: informational proxy, never a gate or a replacement for #fix.
# These English/Turkish phrases are a heuristic, not a measured classifier.
CORRECTION = re.compile(r"\b(?:no[,!]?\s+i\s+said|i\s+(?:already\s+)?(?:said|asked)|"
                        r"that(?:'s| is)\s+(?:wrong|incorrect)|you\s+(?:forgot|ignored)|"
                        r"hayır|yanlış|söylemiştim|demiştim)\b", re.I)


def bucket(ctx: int) -> str:
    return BUCKETS[min(ctx // 100_000, 4)]


def text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(text(c.get('text')) for c in content if isinstance(c, dict))
    return ''


def refusals(content) -> str:
    """The failed tool results' text: a refusal fails its call, a file that quotes one does not."""
    if not isinstance(content, list):
        return ''
    return '\n'.join(text(c.get('content')) for c in content if isinstance(c, dict)
                     and c.get('type') == 'tool_result' and c.get('is_error'))


def events(path: Path, since: str, seen: set | None = None,
           pushes: list | None = None) -> list[tuple[str, int]]:
    """(kind, context) in transcript order; kind is 'request', 'compact' or one of KINDS.

    `seen` is shared across the files read together: a continued session's transcript copies
    the parent's records (same uuid, requestId and tool_use id), counted once (#253). Each
    push is added to `pushes` as (session, timestamp, context, command) for the owner (#202)."""
    out, ctx = [], 0
    seen = set() if seen is None else seen
    with open(path, encoding='utf-8', errors='replace') as stream:
        for line in stream:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get('isSidechain') or str(rec.get('timestamp', '9')) < since:
                continue
            copied = rec.get('uuid') and ('uuid', rec['uuid']) in seen
            if rec.get('uuid'):
                seen.add(('uuid', rec['uuid']))
            if rec.get('type') == 'system' and rec.get('subtype') == 'compact_boundary':
                ctx = 0
                if not copied:
                    out.append(('compact', 0))
                continue
            if copied:
                continue
            msg = rec.get('message')
            if not isinstance(msg, dict):
                continue
            if rec.get('type') == 'assistant' and msg.get('model') != '<synthetic>':
                usage = msg.get('usage')
                if isinstance(usage, dict):
                    ctx = sum(usage.get(k) or 0 for k in
                              ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'))
                    # Streaming writes one request as several records.
                    rid = ('request', rec.get('requestId') or msg.get('id') or id(rec))
                    if rid not in seen:
                        seen.add(rid)
                        out.append(('request', ctx))
                for call in msg.get('content') or []:
                    command = str((call.get('input') or {}).get('command', '')) if isinstance(call, dict) else ''
                    if call_id := isinstance(call, dict) and call.get('id'):
                        if ('tool', call_id) in seen:
                            continue
                        seen.add(('tool', call_id))
                    if isinstance(call, dict) and call.get('type') == 'tool_use' and 'git push' in command:
                        out.append(('push', ctx))
                        if pushes is not None:
                            pushes.append((path.stem, str(rec.get('timestamp', '?')), ctx, ' '.join(command.split())))
            elif rec.get('type') == 'user':
                body = refusals(msg.get('content'))
                out += [(kind, ctx) for kind, sign in SIGNS.items() if sign in body]
                # A prompt with a pasted image is a list of blocks; text() reads only their
                # text fields, never a tool result's nested content (#251).
                said = text(msg.get('content'))
                if not rec.get('isMeta') and not rec.get('isCompactSummary') and MARK in said:
                    out.append(('fix', ctx))
                if not rec.get('isMeta') and not rec.get('isCompactSummary') and CORRECTION.search(said):
                    out.append(('phrase', ctx))
    return out


def window(evs: list[tuple[str, int]], start: int, step: int, limit: int = WINDOW) -> collections.Counter:
    counts, i = collections.Counter(), start
    while 0 <= i < len(evs):
        kind = evs[i][0]
        if kind == 'compact' or (kind == 'request' and counts['request'] >= limit):
            break
        counts[kind] += 1
        i += step
        # Backward, results precede their request. Forward, include the last
        # request's results before stopping at the next request (BACKLOG B13).
        if step < 0 and counts['request'] >= limit:
            break
    return counts


def per100(n: int, requests: int) -> str:
    return f'{n} ({100 * n / requests:.1f})' if requests else str(n)


def report(sessions: list[Path], since: str) -> str:
    total = {b: collections.Counter() for b in BUCKETS}
    lines, seen, pushes = [], set(), []
    for session in sessions:
        evs = events(session, since, seen, pushes)
        for kind, ctx in evs:
            total[bucket(ctx)][kind] += 1
        for n, i in enumerate((i for i, (kind, _) in enumerate(evs) if kind == 'compact'), 1):
            for size in (WINDOW, *SLICES):
                before, after = window(evs, i - 1, -1, size), window(evs, i + 1, 1, size)
                cut = '' if size == WINDOW else f' window {size}'
                lines.append(f'{session.stem} compaction {n}{" (second or later)" if n > 1 else ""}{cut}: '
                             + '  '.join(f'{k} {before[k]}/{after[k]}' for k in KINDS)
                             + f'  (before/after, {before["request"]}/{after["request"]} requests)')
    head = f'{"bucket":<10}{"requests":>10}' + ''.join(f'{k:>14}' for k in KINDS)
    rows = [f'{b:<10}{c["request"]:>10}' + ''.join(f'{per100(c[k], c["request"]):>14}' for k in KINDS)
            for b, c in total.items()]
    # Every push is listed, so the owner can mark the ones nobody asked for; until then push
    # is no error count for the decision rule (#202).
    listed = [f'push {stem} {when} {bucket(ctx)}: {command[:160]}' for stem, when, ctx, command in pushes]
    return '\n'.join([head] + rows + ['count (per 100 requests); phrase is an informational correction proxy;'
                                      ' push counts every git push and is owner-judged: no error count'
                                      ' until the owner marks the unasked ones listed below']
                     + (lines or ['no compaction']) + listed)


def main(argv: list[str]) -> int:
    if argv[:1] in (['-h'], ['--help']):
        print(__doc__.strip())
        return 2
    since = ''
    if argv[:1] == ['--since']:
        if len(argv) < 2:
            raise SystemExit('context_buckets: --since needs a date')
        since, argv = argv[1], argv[2:]
    if argv and all(a.endswith('.jsonl') for a in argv):
        sessions = [Path(a) for a in argv]
    else:
        folder = project_folder(Path(argv[0] if argv else '.'))
        sessions = sorted(folder.glob('*.jsonl'))
        if not sessions:
            raise SystemExit(f'context_buckets: no transcripts under {folder}')
    for session in sessions:
        if not session.is_file():
            raise SystemExit(f'context_buckets: not a file: {session}')
    print(report(sessions, since))
    return 0


if __name__ == '__main__':
    # A Windows pipe is cp1252 unless UTF-8 mode is on: a transcript name outside it raised.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    sys.exit(main(sys.argv[1:]))
