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
  push    `git push` commands; the owner judges which were not asked for
  fix     owner prompts carrying the hand mark `#fix`: the owner's explicit corrections
Then, for each compaction, the same counts over the 20 requests before and the 20 after.
Not counted: the chat language, identifiers in backticks and bare labels need a reader,
not a pattern. Cost: agent_cost.py.
"""
from __future__ import annotations
import collections
import json
from pathlib import Path
import sys

from agent_cost import project_folder

KINDS = ('route', 'attrib', 'push', 'fix')
BUCKETS = ('0-100k', '100-200k', '200-300k', '300-400k', '400k+')
SIGNS = {'route': 'this Agent call names no', 'attrib': 'crediting an AI tool'}
MARK = '#fix'
WINDOW = 20


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


def events(path: Path, since: str) -> list[tuple[str, int]]:
    """(kind, context) in transcript order; kind is 'request', 'compact' or one of KINDS."""
    out, ctx, seen = [], 0, set()
    with open(path, encoding='utf-8', errors='replace') as stream:
        for line in stream:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get('isSidechain') or str(rec.get('timestamp', '9')) < since:
                continue
            if rec.get('type') == 'system' and rec.get('subtype') == 'compact_boundary':
                ctx = 0
                out.append(('compact', 0))
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
                    rid = rec.get('requestId') or msg.get('id') or id(rec)
                    if rid not in seen:
                        seen.add(rid)
                        out.append(('request', ctx))
                for call in msg.get('content') or []:
                    if isinstance(call, dict) and call.get('type') == 'tool_use' and \
                            'git push' in str((call.get('input') or {}).get('command', '')):
                        out.append(('push', ctx))
            elif rec.get('type') == 'user':
                body = refusals(msg.get('content'))
                out += [(kind, ctx) for kind, sign in SIGNS.items() if sign in body]
                if not rec.get('isMeta') and not rec.get('isCompactSummary') and \
                        isinstance(msg.get('content'), str) and MARK in msg['content']:
                    out.append(('fix', ctx))
    return out


def window(evs: list[tuple[str, int]], start: int, step: int) -> collections.Counter:
    counts, i = collections.Counter(), start
    while 0 <= i < len(evs) and counts['request'] < WINDOW:
        if evs[i][0] == 'compact':
            break
        counts[evs[i][0]] += 1
        i += step
    return counts


def per100(n: int, requests: int) -> str:
    return f'{n} ({100 * n / requests:.1f})' if requests else str(n)


def report(sessions: list[Path], since: str) -> str:
    total = {b: collections.Counter() for b in BUCKETS}
    lines = []
    for session in sessions:
        evs = events(session, since)
        for kind, ctx in evs:
            total[bucket(ctx)][kind] += 1
        for n, i in enumerate((i for i, (kind, _) in enumerate(evs) if kind == 'compact'), 1):
            before, after = window(evs, i - 1, -1), window(evs, i + 1, 1)
            lines.append(f'{session.stem} compaction {n}{" (second or later)" if n > 1 else ""}: '
                         + '  '.join(f'{k} {before[k]}/{after[k]}' for k in KINDS)
                         + f'  (before/after, {before["request"]}/{after["request"]} requests)')
    head = f'{"bucket":<10}{"requests":>10}' + ''.join(f'{k:>14}' for k in KINDS)
    rows = [f'{b:<10}{c["request"]:>10}' + ''.join(f'{per100(c[k], c["request"]):>14}' for k in KINDS)
            for b, c in total.items()]
    return '\n'.join([head] + rows + ['count (per 100 requests)'] + (lines or ['no compaction']))


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
    sys.exit(main(sys.argv[1:]))
