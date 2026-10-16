#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Per-agent token accounting from Claude Code transcripts: what a session's workers cost.

Usage: agent_cost.py SESSION.jsonl [...]        one or more session transcripts
       agent_cost.py --latest [PROJECT_DIR]     the newest transcript under
                                               ~/.claude/projects/<encoded project dir>/

Reads the session file and its `subagents/` folder. Assistant records sharing one
`requestId` are ONE API request (streaming writes several records); usage is taken from
the record with the largest output count. The columns that matter for routing, measured
in the kit's founding project (docs/WORKFLOW.md, "Worker cost"):

  cWrite>TTL  cache-write tokens after a gap longer than their recorded lifetime:
              `ephemeral_1h` writes use one hour, `ephemeral_5m` writes five minutes.
              Legacy writes without buckets assume five minutes. This is a gap
              diagnostic, not proof of why the cache missed.
  poll        requests whose every tool call only waited (sleep, pgrep, tail, a job
              output check): each one re-reads the whole context for nothing.
  1h/5m       which cache lifetime the agent's writes used (`ephemeral_1h` is the
              one-hour cache; a worker meant to run with it must show it here).
  hit         cache-read share of all input (read / (read + write + uncached)). The
              initial alarm is below 80% (owner's choice, KARARLAR B03 inv1#173).
              Compare the median of the kit's first ten workers as the baseline;
              cWrite>TTL and poll help investigate a low hit rate.

Not covered: the permission classifier and other requests that never reach a transcript.
"""
from __future__ import annotations
import collections
import glob
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Source: code.claude.com/docs/en/prompt-caching, checked 2026-10-16;
# KARARLAR B03 inv2/(h). The response's cache_creation buckets identify each write's TTL.
CACHE_TTLS = {'w5': 300, 'w1h': 3600}
# Waiting, not working: a sleep, a process probe, a shell wait loop, `tail -f`. A plain `tail`
# of a finished log or a Python run that happens to contain one of these words is work;
# the first version matched those too and over-counted a real worker's poll turns by 4x.
POLL = re.compile(r'(^|[;&|]\s*)(sleep|pgrep|wait)\b|\buntil\b.*;\s*do\b|\bwhile\b.*;\s*do\b|tail\s+-[a-zA-Z]*[fF]')
POLL_TOOLS = {'TaskOutput', 'BashOutput', 'Monitor'}


def is_poll(tool: str, inp) -> bool:
    if tool in POLL_TOOLS:
        return True
    return tool == 'Bash' and isinstance(inp, dict) and bool(POLL.search(inp.get('command', '')))


def requests(path: Path) -> list[dict]:
    """Deduplicated API requests of one transcript, sorted by time."""
    reqs: dict = collections.OrderedDict()
    with open(path, errors='replace') as stream:
        for line in stream:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            msg = rec.get('message') or {}
            if rec.get('type') != 'assistant' or msg.get('model') == '<synthetic>':
                continue
            key = rec.get('requestId') or msg.get('id')
            usage = msg.get('usage') or {}
            q = reqs.setdefault(key, {'t': rec.get('timestamp') or '', 'model': msg.get('model'),
                                      'usage': {}, 'tools': []})
            if usage.get('output_tokens', 0) >= q['usage'].get('output_tokens', 0):
                q['usage'] = usage
            for c in msg.get('content') or []:
                if isinstance(c, dict) and c.get('type') == 'tool_use':
                    q['tools'].append((c.get('name', '?'), c.get('input')))
    rows = []
    for q in reqs.values():
        u = q['usage']
        cc = u.get('cache_creation') or {}
        rows.append({'t': datetime.fromisoformat(q['t'].replace('Z', '+00:00')) if q['t'] else None,
                     'model': q['model'], 'tools': q['tools'],
                     'inp': u.get('input_tokens', 0), 'out': u.get('output_tokens', 0),
                     'cr': u.get('cache_read_input_tokens', 0), 'cw': u.get('cache_creation_input_tokens', 0),
                     'w5': cc.get('ephemeral_5m_input_tokens', 0), 'w1h': cc.get('ephemeral_1h_input_tokens', 0)})
    rows.sort(key=lambda r: r['t'] or datetime.min.replace(tzinfo=None))
    return rows


def summarize(name: str, rows: list[dict]) -> dict:
    gap_cw = polls = 0
    prev = None
    for r in rows:
        if prev is not None and r['t']:
            gap = (r['t'] - prev).total_seconds()
            gap_cw += sum(r[key] for key, ttl in CACHE_TTLS.items() if gap > ttl)
            # Old transcripts lack TTL buckets; keep their five-minute assumption explicit.
            if gap > CACHE_TTLS['w5']:
                gap_cw += max(0, r['cw'] - r['w5'] - r['w1h'])
        if r['tools'] and all(is_poll(t, i) for t, i in r['tools']):
            polls += 1
        prev = r['t'] or prev
    ctx = lambda r: r['inp'] + r['cr'] + r['cw']  # noqa: E731
    return {'agent': name, 'req': len(rows), 'tool': sum(len(r['tools']) for r in rows),
            'cr': sum(r['cr'] for r in rows), 'cw': sum(r['cw'] for r in rows),
            'inp': sum(r['inp'] for r in rows),
            'cw_gap': gap_cw, 'poll': polls,
            'w1h': sum(r['w1h'] for r in rows), 'w5': sum(r['w5'] for r in rows),
            'ctx0': ctx(rows[0]) if rows else 0, 'ctxN': ctx(rows[-1]) if rows else 0,
            'models': sorted({str(r['model']) for r in rows})}


def session_agents(session: Path) -> list[tuple[str, Path]]:
    """The lead transcript plus every sub-agent transcript of the session."""
    out = [('LEAD', session)]
    folder = session.with_suffix('')
    for f in sorted(glob.glob(str(folder / 'subagents' / '*.jsonl'))):
        meta = Path(f[:-6] + '.meta.json')
        name = os.path.basename(f)[:-6]
        if meta.exists():
            try:
                name = (json.loads(meta.read_text(encoding="utf-8")).get('description') or name)[:40]
            except ValueError:
                pass
        out.append((name, Path(f)))
    return out


def fmt(n: int) -> str:
    return f'{n / 1e6:.2f}M' if n >= 1e6 else f'{n / 1e3:.1f}k'


def hit(s: dict) -> str:
    total = s['cr'] + s['cw'] + s['inp']
    return f'{100 * s["cr"] / total:.0f}%' if total else '-'


def table(summaries: list[dict]) -> str:
    head = f'{"agent":40} {"req":>4} {"tool":>4} {"cRead":>8} {"cWrite":>8} {"cWrite>TTL":>10} {"poll":>4} {"1h/5m":>13} {"hit":>4} {"ctx0->ctxN":>14}'
    lines = [head]
    for s in sorted(summaries, key=lambda s: -s['cr']):
        bucket = f'{fmt(s["w1h"])}/{fmt(s["w5"])}'
        lines.append(f'{s["agent"][:40]:40} {s["req"]:4} {s["tool"]:4} {fmt(s["cr"]):>8} {fmt(s["cw"]):>8} '
                     f'{fmt(s["cw_gap"]):>10} {s["poll"]:4} {bucket:>13} {hit(s):>4} '
                     f'{fmt(s["ctx0"]):>6}->{fmt(s["ctxN"]):<6}')
    tot = {k: sum(s[k] for s in summaries) for k in ('req', 'cr', 'cw', 'inp', 'cw_gap', 'poll')}
    share = 100 * tot['cw_gap'] / tot['cw'] if tot['cw'] else 0
    lines.append(f'TOTAL requests {tot["req"]}  cRead {fmt(tot["cr"])}  cWrite {fmt(tot["cw"])}  '
                 f'after >TTL gaps {fmt(tot["cw_gap"])} ({share:.0f}%)  poll-only requests {tot["poll"]}  '
                 f'cache hit {hit(tot)} (alarm below 80%; owner\'s choice)')
    return '\n'.join(lines)


def project_folder(project_dir: Path) -> Path:
    # Claude Code turns every character but a letter or digit into '-': D:\_x and /a_b alike.
    encoded = re.sub(r'[^A-Za-z0-9]', '-', str(project_dir.resolve()))
    return Path.home() / '.claude' / 'projects' / encoded


def latest_session(project_dir: Path) -> Path:
    folder = project_folder(project_dir)
    files = sorted(folder.glob('*.jsonl'), key=lambda p: p.stat().st_mtime)
    if not files:
        raise SystemExit(f'agent_cost: no transcripts under {folder}')
    return files[-1]


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__.strip())
        return 2
    if argv[0] == '--latest':
        sessions = [latest_session(Path(argv[1] if len(argv) > 1 else '.'))]
    else:
        sessions = [Path(a) for a in argv]
    for session in sessions:
        if not session.is_file():
            raise SystemExit(f'agent_cost: not a file: {session}')
        print(f'== {session}')
        print(table([summarize(n, requests(p)) for n, p in session_agents(session)]))
    return 0


if __name__ == '__main__':
    # A Windows pipe is cp1252 unless UTF-8 mode is on: a worker description outside it raised.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    sys.exit(main(sys.argv[1:]))
