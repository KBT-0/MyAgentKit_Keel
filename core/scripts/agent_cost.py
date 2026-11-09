#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Per-agent token accounting from Claude Code transcripts: what a session's workers cost.

Usage: agent_cost.py SESSION.jsonl [...]        one or more session transcripts
       agent_cost.py --latest [PROJECT_DIR]     the newest transcript under
                                               ~/.claude/projects/<encoded project dir>/
       agent_cost.py --by-task SESSION.jsonl|DIR [...]  one row per task: the sessions whose
                                               worker NAME (its .claude/worktrees/NAME folder,
                                               else its .myagentkit/workers/NAME.brief.md) shares a
                                               stem once a trailing -N, -fixN or -rN is cut; others are lead
       agent_cost.py --quota [quota.jsonl]      subscription percent per label, from
                                               quota_snapshot.py's start and end lines

Reads the session file and its `subagents/` folder, Workflow-tool agents in
`subagents/workflows/wf_<run>/` included. Assistant records sharing one
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
              TOTAL's "1h unused" sums the one-hour writes of agents with no gap over
              five minutes: the 2x write paid for a lifetime they never needed (#116).
  hit         cache-read share of all input (read / (read + write + uncached)). No alarm: a
              high hit rate hid the spend of every field report (v0.16 reset); cWrite>TTL and
              poll help investigate a low one.
  out         output tokens, priced above input: a reviewer or report writer
              spends here, not in the cache columns.
  cmp         compactions (`compact_boundary` records, the ones context_buckets.py
              reads): a sub-agent is compacted far below the lead's bands (#303).
  ctx0->max->ctxN  the context of the first request, the largest, and the last; the
              last is small after a compaction, so the peak is the one to read.
  model       the agent's answering model (its most frequent `model`), short form.
  $           list-price dollars at token_audit.py's PRICES; `?` for a model not in it.
              TOTAL adds $ per request and the largest context; it raises ALARM when an
              agent's context passed 150k or the session's $ passed MYAGENTKIT_SPEND_ALARM_USD
              (default 5).

Not covered: the permission classifier and other requests that never reach a transcript.
"""
from __future__ import annotations
import collections
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import token_audit

# Source: code.claude.com/docs/en/prompt-caching, checked 2026-10-16;
# KARARLAR B03 inv2/(h). The response's cache_creation buckets identify each write's TTL.
CACHE_TTLS = {'w5': 300, 'w1h': 3600}
# Waiting, not working: a sleep, a process probe, a shell wait loop, `tail -f`. A plain `tail`
# of a finished log or a Python run that happens to contain one of these words is work;
# the first version matched those too and over-counted a real worker's poll turns by 4x.
POLL = re.compile(r'(^|[;&|]\s*)(sleep|pgrep|wait)\b|\buntil\b.*;\s*do\b|\bwhile\b.*;\s*do\b|tail\s+-[a-zA-Z]*[fF]')
POLL_TOOLS = {'TaskOutput', 'BashOutput', 'Monitor'}
CTX_ALARM = 150_000
WORKTREE = re.compile(r'[/\\]\.claude[/\\]worktrees[/\\]([^/\\]+)')
BRIEF = re.compile(r"Read '[^']*[/\\]workers[/\\]([^/\\']+)\.brief\.md'")
STEM = re.compile(r'(-(\d+|fix\d*|r\d+))+$')


def is_poll(tool: str, inp) -> bool:
    if tool in POLL_TOOLS:
        return True
    return tool == 'Bash' and isinstance(inp, dict) and bool(POLL.search(inp.get('command', '')))


def requests(path: Path, seen: set | None = None, compactions: list | None = None) -> list[dict]:
    """Deduplicated API requests of one transcript, sorted by time. A request id already in
    `seen` (shared across the transcripts read together) is left out: a continued session's
    transcript copies its parent's requests, billed to the parent (#253). Each compaction
    boundary is added to `compactions`, a copied one (its uuid in `seen`) once."""
    reqs: dict = collections.OrderedDict()
    with open(path, errors='replace') as stream:
        for line in stream:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get('type') == 'system' and rec.get('subtype') == 'compact_boundary':
                if compactions is not None and ('uuid', rec.get('uuid')) not in (seen or ()):
                    compactions.append(rec.get('timestamp'))
                if seen is not None and rec.get('uuid'):
                    seen.add(('uuid', rec['uuid']))
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
    for key in [key for key in reqs if seen is not None and key in seen]:
        del reqs[key]
    if seen is not None:
        seen.update(reqs)
    for q in reqs.values():
        u = q['usage']
        cc = u.get('cache_creation') or {}
        rows.append({'t': datetime.fromisoformat(q['t'].replace('Z', '+00:00')) if q['t'] else None,
                     'model': q['model'], 'tools': q['tools'],
                     'inp': u.get('input_tokens', 0), 'out': u.get('output_tokens', 0),
                     'cr': u.get('cache_read_input_tokens', 0), 'cw': u.get('cache_creation_input_tokens', 0),
                     'w5': cc.get('ephemeral_5m_input_tokens', 0), 'w1h': cc.get('ephemeral_1h_input_tokens', 0)})
    # Untimed requests (a damaged or foreign record) sort first; an aware minimum, since a
    # naive one beside the aware timestamps raised TypeError (#255).
    rows.sort(key=lambda r: r['t'] or datetime.min.replace(tzinfo=timezone.utc))
    return rows


def summarize(name: str, rows: list[dict], compactions: int = 0) -> dict:
    gap_cw = polls = longest = 0
    prev = None
    for r in rows:
        if prev is not None and r['t']:
            gap = (r['t'] - prev).total_seconds()
            longest = max(longest, gap)
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
            'inp': sum(r['inp'] for r in rows), 'out': sum(r['out'] for r in rows),
            'cw_gap': gap_cw, 'poll': polls,
            'w1h': sum(r['w1h'] for r in rows), 'w5': sum(r['w5'] for r in rows),
            'w1h_unused': 0 if longest > CACHE_TTLS['w5'] else sum(r['w1h'] for r in rows),
            'cmp': compactions, 'ctx0': ctx(rows[0]) if rows else 0, 'ctxN': ctx(rows[-1]) if rows else 0,
            'ctxMax': max(map(ctx, rows), default=0),
            'models': sorted({str(r['model']) for r in rows}),
            'model': collections.Counter(r['model'] for r in rows).most_common(1)[0][0] if rows else None}


def short(model) -> str:
    return next((key for key in token_audit.PRICES if key in str(model)), '?')


def usd(s: dict) -> float | None:
    """List-price dollars of one summary; None for a model token_audit.PRICES does not hold."""
    if not s['req']:
        return 0.0
    prices = token_audit.PRICES.get(short(s['model']))
    return None if prices is None else sum(token_audit.cost_parts(prices, s['inp'], s['out'], s['cr'], s['cw'], s['w1h']).values())


def unpriced(summaries: list[dict]) -> list[str]:
    models = sorted({str(s['model']) for s in summaries if usd(s) is None})
    return [f'note: no price for model {m} in token_audit.PRICES; its $ is ? and left out of the sums' for m in models]


def session_agents(session: Path) -> list[tuple[str, Path]]:
    """The lead transcript plus every sub-agent transcript of the session."""
    out = [('LEAD', session)]
    folder = session.with_suffix('')
    # Workflow-tool agents sit one level deeper, in subagents/workflows/wf_<run>/ beside a
    # journal.jsonl that holds no requests (#172).
    for f in sorted(glob.glob(str(folder / 'subagents' / '**' / '*.jsonl'), recursive=True)):
        if os.path.basename(f) == 'journal.jsonl':
            continue
        meta = Path(f[:-6] + '.meta.json')
        name = os.path.basename(f)[:-6]
        if meta.exists():
            try:
                name = json.loads(meta.read_text(encoding="utf-8")).get('description') or name
            except ValueError:
                pass
        run = os.path.basename(os.path.dirname(f))
        if run.startswith('wf_'):
            name = f'{run} {name}'
        out.append((name[:40], Path(f)))
    return out


def fmt(n: int) -> str:
    return f'{n / 1e6:.2f}M' if n >= 1e6 else f'{n / 1e3:.1f}k'


def hit(s: dict) -> str:
    total = s['cr'] + s['cw'] + s['inp']
    return f'{100 * s["cr"] / total:.0f}%' if total else '-'


def table(summaries: list[dict]) -> str:
    head = f'{"agent":40} {"req":>4} {"tool":>4} {"cRead":>8} {"cWrite":>8} {"cWrite>TTL":>10} {"out":>8} {"poll":>4} {"1h/5m":>13} {"hit":>4} {"cmp":>3} {"ctx0":>6}->max->ctxN {"model":>6} {"$":>7}'
    lines = [head]
    for s in sorted(summaries, key=lambda s: -s['cr']):
        bucket = f'{fmt(s["w1h"])}/{fmt(s["w5"])}'
        lines.append(f'{s["agent"][:40]:40} {s["req"]:4} {s["tool"]:4} {fmt(s["cr"]):>8} {fmt(s["cw"]):>8} '
                     f'{fmt(s["cw_gap"]):>10} {fmt(s["out"]):>8} {s["poll"]:4} {bucket:>13} {hit(s):>4} {s["cmp"]:3} '
                     f'{fmt(s["ctx0"]):>6}->{fmt(s["ctxMax"])}->{fmt(s["ctxN"])} {short(s["model"]):>6} {money(usd(s)):>7}')
    tot = {k: sum(s[k] for s in summaries) for k in ('req', 'cr', 'cw', 'inp', 'out', 'cw_gap', 'poll', 'w1h_unused')}
    share = 100 * tot['cw_gap'] / tot['cw'] if tot['cw'] else 0
    lines.append(f'TOTAL requests {tot["req"]}  cRead {fmt(tot["cr"])}  cWrite {fmt(tot["cw"])}  '
                 f'after >TTL gaps {fmt(tot["cw_gap"])} ({share:.0f}%)  output {fmt(tot["out"])}  1h unused {fmt(tot["w1h_unused"])}  '
                 f'poll-only requests {tot["poll"]}  cache hit {hit(tot)}  '
                 f'{spend(summaries)}')
    return '\n'.join(lines + unpriced(summaries))


def money(value: float | None) -> str:
    return '?' if value is None else f'{value:.2f}'


def alarm_usd() -> float:
    try:
        return float(os.environ.get('MYAGENTKIT_SPEND_ALARM_USD') or 5)
    except ValueError:
        return 5.0


def spend(summaries: list[dict]) -> str:
    """$ and $ per request, the largest context, and the alarm: a context past 150k or $ past the threshold."""
    total = sum(usd(s) or 0 for s in summaries)
    reqs = sum(s['req'] for s in summaries if usd(s) is not None)  # an unpriced agent's requests would dilute it
    peak = max((s['ctxMax'] for s in summaries), default=0)
    line = f'$ {total:.2f} (${total / reqs if reqs else 0:.3f}/request)  max context {fmt(peak)}'
    over = [s['agent'] for s in summaries if s['ctxMax'] > CTX_ALARM]
    why = ([f'context past {fmt(CTX_ALARM)} ({", ".join(over)})'] if over else []) + \
          ([f'$ past {alarm_usd():g}'] if total > alarm_usd() else [])
    return line + ('  ALARM: ' + '; '.join(why) if why else '')


def task_of(session: Path) -> str:
    """The task of a session: its worker NAME's stem, from the first prompt's cwd or brief; 'lead' else."""
    with open(session, errors='replace') as stream:
        for line in stream:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get('type') != 'user' or rec.get('isMeta'):
                continue
            m = WORKTREE.search(str(rec.get('cwd') or '')) or \
                BRIEF.match(token_audit.text_of((rec.get('message') or {}).get('content')))
            return STEM.sub('', m.group(1)) or m.group(1) if m else 'lead'
    return 'lead'


def by_task(sessions: list[Path]) -> str:
    seen: set = set()
    tasks: dict = collections.defaultdict(lambda: {'n': 0, 'usd': 0.0, 'ctx': 0, 'models': set(), 'all': []})
    for session in sessions:
        summaries = [summarize(n, requests(p, seen)) for n, p in session_agents(session)]
        t = tasks[task_of(session)]
        t['n'] += 1
        t['usd'] += sum(usd(s) or 0 for s in summaries)
        t['ctx'] = max([t['ctx']] + [s['ctxMax'] for s in summaries])
        t['models'].update(short(s['model']) for s in summaries if s['req'])
        t['all'] += summaries
    lines = [f'{"task":40} {"sessions":>8} {"$":>8} {"max ctx":>8}  models']
    for name, t in sorted(tasks.items(), key=lambda kv: -kv[1]['usd']):
        lines.append(f'{name[:40]:40} {t["n"]:8} {t["usd"]:8.2f} {fmt(t["ctx"]):>8}  {",".join(sorted(t["models"])) or "-"}')
    lines.append(f'TOTAL tasks {len(tasks)}  sessions {sum(t["n"] for t in tasks.values())}  '
                 f'$ {sum(t["usd"] for t in tasks.values()):.2f}')
    return '\n'.join(lines + unpriced([s for t in tasks.values() for s in t['all']]))


def window_delta(start, end):
    """used_percentage end minus start; a window absent at the start was at 0, a changed reset time is 'reset'."""
    if not isinstance(end, dict):
        return None
    try:
        before = 0.0 if not isinstance(start, dict) else float(start['used_percentage'])
        after = float(end['used_percentage'])
    except (KeyError, TypeError, ValueError):
        return None
    if isinstance(start, dict) and start.get('resets_at') != end.get('resets_at'):
        return 'reset'
    return after - before


def quota(path: Path) -> str:
    """Per label the first start and the last end of quota_snapshot.py's lines, compared."""
    first, last, order = {}, {}, []
    with open(path, encoding='utf-8', errors='replace') as stream:
        for line in stream:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            label = str(rec.get('label'))
            if label not in order:
                order.append(label)
            if rec.get('phase') == 'start':
                first.setdefault(label, rec)
            elif rec.get('phase') == 'end':
                last[label] = rec
    show = lambda d: '-' if d is None else d if isinstance(d, str) else f'{d:+g}%'  # noqa: E731
    totals: dict = collections.defaultdict(lambda: [0.0, 0.0])
    lines = [f'{"label":40} {"5h":>7} {"7d":>7}  org']
    for label in order:
        a, b = first.get(label), last.get(label)
        if a is None or b is None:
            lines.append(f'{label[:40]:40} n/a (no {"start" if a is None else "end"} line)')
        elif a.get('org_uuid') != b.get('org_uuid'):
            lines.append(f'{label[:40]:40} switched {a.get("org_name")}\u2192{b.get("org_name")}')
        else:
            d5, d7 = window_delta(a.get('five_hour'), b.get('five_hour')), window_delta(a.get('seven_day'), b.get('seven_day'))
            lines.append(f'{label[:40]:40} {show(d5):>7} {show(d7):>7}  {b.get("org_name")}')
            for i, d in enumerate((d5, d7)):
                totals[str(b.get('org_name'))][i] += d if isinstance(d, float) else 0
    lines += [f'TOTAL {org}: 5h {show(d5)}  7d {show(d7)}' for org, (d5, d7) in totals.items()]
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
    if argv[0] == '--quota':
        path = Path(argv[1] if len(argv) > 1 else '.myagentkit/usage/quota.jsonl')
        if not path.is_file():
            raise SystemExit(f'agent_cost: no quota file: {path} (quota_snapshot.py writes it)')
        print(quota(path))
        return 0
    grouped = argv[0] == '--by-task'
    argv = argv[grouped:]
    if argv and argv[0] == '--latest':
        sessions = [latest_session(Path(argv[1] if len(argv) > 1 else '.'))]
    else:
        sessions = [f for a in argv for f in (sorted(Path(a).glob('*.jsonl')) if grouped and Path(a).is_dir() else [Path(a)])]
    for session in sessions:
        if not session.is_file():
            raise SystemExit(f'agent_cost: not a file: {session}')
    if grouped:
        print(by_task(sessions))
        return 0
    seen: set = set()
    for session in sessions:
        print(f'== {session}')
        summaries = []
        for name, path in session_agents(session):
            found: list = []
            summaries.append(summarize(name, requests(path, seen, found), len(found)))
        print(table(summaries))
    return 0


if __name__ == '__main__':
    # A Windows pipe is cp1252 unless UTF-8 mode is on: a worker description outside it raised.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    sys.exit(main(sys.argv[1:]))
