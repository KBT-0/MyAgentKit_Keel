#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Where a Claude Code session's tokens go: the #307 leakage audit, re-runnable before and after a fix.

Usage: token_audit.py [--since DAYS] [--json OUT] [--top N] [--by-day] PATH [...]
       PATH is a transcript folder (~/.claude/projects/<encoded dir>) or one SESSION.jsonl;
       its sub-agent transcripts (`<session>/subagents/`) are read with it.
       token_audit.py --usage DIR [...]   review/bridge records (.myagentkit/usage/*.json)
       --by-day prints one row per local day of session start (sessions, requests, $) instead of the summary.

Per transcript (lead, worker = a session in a `.claude/worktrees/` folder, sub-agent by its
agentType) it counts what agent_cost.py counts (deduplicated requests, cache read/write,
output, context peak, compactions) and adds where the context came from:

  carried     an item's tokens times the requests that re-read it before the next compaction,
              priced at the model's cache-read rate, plus its one write: what a tool result or an
              injected reminder really cost, not just its size.
  reads       Read calls, whole-file ones (no offset/limit), re-reads of a path read before,
              and Bash `cat FILE` whole-file reads.
  big         tool results over BIG characters (unbounded logs, test output, listings).
  junk        reads or results of paths a task never needs (lockfiles, node_modules, build,
              the generated plugin copy of core/scripts).
  retries     a tool call identical to an earlier one in the same transcript.
  inject      text the harness or a hook added: SessionStart output, hook additionalContext,
              skill and agent listings, CLAUDE.md/memory, by source.
  narration   characters of the assistant's own text (not tool input, not thinking).
  flags       a cache hit rate under HIT_FLOOR, a path read 3+ times, an edit of an always-loaded
              file (CLAUDE.md, AGENTS.md, MEMORY.md, .claude/settings or rules) inside the session.

A later `credential_org` record with another uuid is an account switch (a /login in the shared ~/.claude): per session `org`,
`switches`, `switch_tokens` and `switch_usd` (the next request's cache write, which the new account's cache must redo).

Tokens of a text are its characters / CHARS_PER_TOKEN (calibrated in
.myagentkit/v014/tokaudit/BASELINE.md); request usage is the API's own count.
Prices: list price per MTok, Anthropic pricing page via docs/research/token-optimization.md
section 4; the Fable rates reproduce a review record's api_cost_usd_reported to the cent.
"""
from __future__ import annotations
import argparse
import collections
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

CHARS_PER_TOKEN = 2.4
BIG = 20000
# $/MTok input, output, cache-read multiplier. Writes: 1.25x (5 min), 2x (1 h).
PRICES = {'opus': (4.0, 20.0, 0.05), 'sonnet': (2.0, 10.0, 0.05), 'haiku': (0.10, 0.50, 0.10),
          'fable': (10.0, 50.0, 0.025)}
JUNK = re.compile(r'(^|/)(node_modules|dist|build|\.venv|__pycache__|\.git)/|(package-lock\.json|yarn\.lock|'
                  r'pnpm-lock\.yaml|uv\.lock|poetry\.lock|Cargo\.lock)$|\.(png|jpe?g|gif|ico|min\.js|map)$|'
                  r'plugins/myagentkit/scripts/')
# Cache hit rate below which a session is flagged: practitioner rule of thumb (>80 % healthy,
# <60 % a problem: Zivtech's Claude Code health benchmarks, not measured); FLAG_MIN skips short probes.
HIT_FLOOR, FLAG_MIN = 0.6, 10
ALWAYS = re.compile(r'(^|[/\\])(CLAUDE|AGENTS|MEMORY)\.md$|'
                    r'[/\\]\.claude[/\\](settings(\.local)?\.json$|rules[/\\])')
CAT = re.compile(r'^\s*cat\s+(?:--\s+)?([^\s|<>;&]+)\s*$')


POLL = re.compile(r'(^|[;&|]\s*)(sleep|pgrep|wait)\b|\buntil\b.*;\s*do\b|tail\s+-[a-zA-Z]*[fF]')
LEAD = re.compile(r'^\s*((cd|set|export)\s+[^;&|]*(&&|;)\s*|[A-Z_][A-Z0-9_]*=\S*\s+)*')
WORDS = {'read': {'cat', 'head', 'tail', 'sed', 'less', 'type', 'Get-Content', 'nl', 'wc', 'awk'},
         'search': {'grep', 'rg', 'find', 'ls', 'bfs', 'fd', 'Select-String', 'Get-ChildItem', 'tree'},
         'vcs': {'g' + 'it'}, 'gh': {'gh'}}
RUNS = [('test', re.compile(r'unittest|pytest|check(_kit)?\.(sh|py)|ctest|npm (run )?test|cargo test|\btest_\w+\.py')),
        ('kit-script', re.compile(r'spawn_worker|spawn_codex|review\.sh|close_worker|codex_worker|agent_cost|'
                                  r'context_buckets|working_mode|clean_worktrees|usage_summary|review_dispatch|'
                                  r'claude_bridge|doctor\.sh|sync-kit')),
        ('build', re.compile(r'\b(cmake|make|ninja|msbuild|dotnet build|npm run build|cargo build)\b'))]


def bash_kind(command: str) -> str:
    """By the first command after any `cd X &&` and VAR=value prefix: a `sed -n` of a kit
    script is a read, a unittest run of one is a test."""
    if POLL.search(command):
        return 'poll'
    head = LEAD.sub('', command, count=1)
    word = (head.split() or [''])[0].rsplit('/', 1)[-1]
    for name, words in WORDS.items():
        if word in words:
            return name
    for name, pattern in RUNS:
        if pattern.search(head):
            return name
    return 'python' if word.startswith('python') or word == 'py' else 'other'


def price(model) -> tuple:
    for key, value in PRICES.items():
        if key in str(model):
            return value
    return PRICES['opus']


def cost_parts(prices: tuple, inp: int, out: int, cr: int, cw: int, w1h: int) -> dict:
    """$ by part at list price per MTok; a cache write is 2x for one hour, 1.25x for five minutes."""
    p_in, p_out, p_read = prices
    return {'uncached': inp * p_in / 1e6, 'output': out * p_out / 1e6, 'read': cr * p_in * p_read / 1e6,
            'write': (w1h * 2 + (cw - w1h) * 1.25) * p_in / 1e6}


def toks(chars: int) -> int:
    return int(chars / CHARS_PER_TOKEN)


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(text_of(c.get('text', c.get('content', ''))) if isinstance(c, dict) else str(c)
                       for c in content)
    return ''


def kind_of(path: Path) -> str:
    if path.parent.name == 'subagents':
        meta = path.with_suffix('.meta.json')
        try:
            return 'sub:' + json.loads(meta.read_text()).get('agentType', '?')
        except (OSError, ValueError):
            return 'sub:?'
    return 'worker' if '-claude-worktrees-' in path.parent.name else 'lead'


def audit(path: Path, seen: set) -> dict:
    """One transcript. `seen` (shared) drops records a continued session copied from its parent."""
    reqs = collections.OrderedDict()
    items = []          # (source, label, chars, request index when it entered the context)
    compactions = []    # request index of each compaction
    tool_names = {}     # tool_use_id -> (name, input)
    tools = collections.defaultdict(lambda: [0, 0])
    reads = collections.Counter()
    read_paths = collections.Counter()
    hot = collections.Counter()  # whole reads only: a ranged Read before an Edit is the cheap rule (#325)
    calls = collections.Counter()
    org, switch_at = None, collections.Counter()  # org: the last account uuid seen; switch_at: next request index -> switches
    out = {'file': str(path), 'kind': kind_of(path), 'system_chars': 0, 'tools_chars': 0,
           'narration_chars': 0, 'text_blocks': 0, 'agent_calls': 0, 'agent_result_chars': 0,
           'skill_calls': collections.Counter(), 'retries': 0, 'retry_chars': 0, 'errors': 0,
           'copied': 0, 'entrypoint': None, 'prompt': None, 'org': None,
           'instruction_files': {}, 'skill_listing': {}, 'always_edits': []}
    with open(path, errors='replace') as stream:
        for line in stream:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            uuid = rec.get('uuid')
            if uuid and ('uuid', uuid) in seen:
                out['copied'] += 1
                continue
            if uuid:
                seen.add(('uuid', uuid))
            kind = rec.get('type')
            out['entrypoint'] = out['entrypoint'] or rec.get('entrypoint')
            if kind == 'user' and out['prompt'] is None and not rec.get('isMeta'):
                text = text_of((rec.get('message') or {}).get('content'))
                out['prompt'] = text[:160] if text else None
            if kind == 'user':  # a slash command the owner typed is a call too (r338)
                typed = re.search(r'<command-name>/?([^<\s]+)</command-name>', text_of((rec.get('message') or {}).get('content')))
                if typed:
                    out['skill_calls'][typed.group(1)] += 1
            if kind == 'api-request-shape' and not out['tools_chars']:
                shape = rec.get('shape') or {}
                out['system_chars'] = sum(len(s.get('text', '')) for s in shape.get('system') or [])
                out['tools_chars'] = len(json.dumps(shape.get('tools') or [], ensure_ascii=False))
            elif kind == 'system' and rec.get('subtype') == 'compact_boundary':
                compactions.append(len(reqs))
            elif kind == 'attachment':
                att = rec.get('attachment') or {}
                if att.get('type') == 'credential_org' and att.get('organizationUuid'):
                    out['org'] = out['org'] or att['organizationUuid']
                    if org not in (None, att['organizationUuid']):
                        switch_at[len(reqs)] += 1
                    org = att['organizationUuid']
                rendered = sum(len(text_of(r.get('content'))) for r in rec.get('rendered') or [])
                if rendered:
                    source = att.get('hookName') or att.get('type', '?')
                    sample = text_of(att.get('content') or att.get('text') or '')[:70]
                    items.append(('inject', source + ' | ' + sample, rendered, len(reqs)))
                for f in att.get('files') or [] if att.get('type') == 'instructions' else []:
                    name = re.sub(r'.*[/\\](?=[^/\\]+[/\\][^/\\]+$)', '', str(f.get('path')))
                    out['instruction_files'][name] = max(out['instruction_files'].get(name, 0), len(f.get('content') or ''))
                if att.get('type') == 'skill_listing':
                    for entry in re.split(r'\n(?=- )', att.get('content') or ''):
                        name = entry[2:].split(': ', 1)[0]
                        owner = name.split(':')[0] if ':' in name else 'user/bundled'
                        out['skill_listing'][owner] = out['skill_listing'].get(owner, 0) + len(entry)
            elif kind == 'assistant':
                msg = rec.get('message') or {}
                if msg.get('model') == '<synthetic>':
                    continue
                key = rec.get('requestId') or msg.get('id')
                if ('req', key) in seen and key not in reqs:
                    continue
                seen.add(('req', key))
                q = reqs.setdefault(key, {'model': msg.get('model'), 'usage': {}, 't': rec.get('timestamp')})
                usage = msg.get('usage') or {}
                if usage.get('output_tokens', 0) >= q['usage'].get('output_tokens', 0):
                    q['usage'] = usage
                for c in msg.get('content') or []:
                    if not isinstance(c, dict):
                        continue
                    if c.get('type') == 'text':
                        out['narration_chars'] += len(c.get('text', ''))
                        out['text_blocks'] += 1
                    elif c.get('type') == 'tool_use':
                        name, inp = c.get('name', '?'), c.get('input') or {}
                        tool_names[c.get('id')] = (name, inp)
                        sig = json.dumps([name, inp], sort_keys=True)
                        calls[sig] += 1
                        if calls[sig] > 1 and name not in ('TaskOutput', 'Monitor'):
                            out['retries'] += 1
                        if name in ('Edit', 'Write', 'MultiEdit', 'NotebookEdit') and \
                                ALWAYS.search(str(inp.get('file_path') or inp.get('notebook_path') or '')):
                            out['always_edits'].append(inp.get('file_path') or inp.get('notebook_path'))
                        if name == 'Agent':
                            out['agent_calls'] += 1
                        elif name == 'Skill':
                            out['skill_calls'][inp.get('skill', '?')] += 1
            elif kind == 'user':
                content = (rec.get('message') or {}).get('content')
                for c in content if isinstance(content, list) else []:
                    if not isinstance(c, dict) or c.get('type') != 'tool_result':
                        continue
                    name, inp = tool_names.get(c.get('tool_use_id'), ('?', {}))
                    size = len(text_of(c.get('content')))
                    tools[name][0] += 1
                    tools[name][1] += size
                    out['errors'] += bool(c.get('is_error'))
                    if calls.get(json.dumps([name, inp], sort_keys=True), 0) > 1 and name not in ('TaskOutput', 'Monitor'):
                        out['retry_chars'] += size
                    target = ''
                    if name == 'Read':
                        target = inp.get('file_path', '')
                        reads['read'] += 1
                        whole = 'offset' not in inp and 'limit' not in inp
                        reads['whole'] += whole
                        reads['whole_chars'] += size if whole else 0
                        reads['whole_big'] += whole and size > 12000
                        hot[target] += whole
                        read_paths[target] += 1
                        if read_paths[target] > 1:
                            reads['reread'] += 1
                            reads['reread_chars'] += size
                    elif name == 'Bash':
                        m = CAT.match(inp.get('command', ''))
                        if m:
                            target = m.group(1)
                            reads['bash_cat'] += 1
                            reads['bash_cat_chars'] += size
                            hot[target] += 1
                            read_paths[target] += 1
                            if read_paths[target] > 1:
                                reads['reread'] += 1
                                reads['reread_chars'] += size
                    if JUNK.search(target or inp.get('path') or inp.get('pattern') or ''):
                        reads['junk'] += 1
                        reads['junk_chars'] += size
                    if size > BIG:
                        reads['big'] += 1
                        reads['big_chars'] += size
                    if name == 'Agent':
                        out['agent_result_chars'] += size
                    label = name + ' ' + (target or str(inp.get('command') or inp.get('pattern')
                                                        or inp.get('description') or '')[:300])
                    if re.search(r'tool-results|[/\\]tasks[/\\][^/\\]+\.output$', target):
                        reads['spill'] += 1
                        reads['spill_chars'] += size
                    source = 'bash:' + bash_kind(inp.get('command', '')) if name in ('Bash', 'PowerShell') else 'tool:' + name
                    items.append((source, label, size, len(reqs)))
    rows = [{'model': q['model'], 'inp': q['usage'].get('input_tokens', 0), 'out': q['usage'].get('output_tokens', 0),
             'cr': q['usage'].get('cache_read_input_tokens', 0), 'cw': q['usage'].get('cache_creation_input_tokens', 0),
             'w1h': (q['usage'].get('cache_creation') or {}).get('ephemeral_1h_input_tokens', 0), 't': q['t']}
            for q in reqs.values()]
    model = collections.Counter(r['model'] for r in rows).most_common(1)[0][0] if rows else None
    p_in, p_out, p_read = price(model)
    parts = cost_parts((p_in, p_out, p_read), *(sum(r[k] for r in rows) for k in ('inp', 'out', 'cr', 'cw', 'w1h')))
    cost = sum(parts.values())
    # A switch's rewrite is the cache write of the next request (once, whatever the switches before it).
    switched = [r for i, r in enumerate(rows) if i in switch_at]
    switch_usd = sum(cost_parts(price(r['model']), 0, 0, 0, r['cw'], r['w1h'])['write'] for r in switched)
    ctx = [r['inp'] + r['cr'] + r['cw'] for r in rows]
    write = 2.0 if sum(r['w1h'] for r in rows) * 2 > sum(r['cw'] for r in rows) else 1.25
    ends = sorted(compactions) + [len(rows)]
    # The fixed prefix (system prompt, tool schemas, whatever no record shows) and the assistant's
    # own output, both re-read like any item; an item's characters are measured, these are counted.
    first = sum(chars for _, _, chars, at in items if at == 0)
    rest = max(0, ctx[0] - toks(first)) if ctx else 0
    # A continued or resumed session starts with its parent's history: that part is 'inherited'.
    base = min(rest, toks(out['system_chars'] + out['tools_chars']) or 45000)
    fixed = [('base', 'system prompt + tool schemas', base * CHARS_PER_TOKEN, 0),
             ('inherited', 'history a resumed or continued session starts with', (rest - base) * CHARS_PER_TOKEN, 0)]
    fixed += [('assistant', 'own output', r['out'] * CHARS_PER_TOKEN, i + 1) for i, r in enumerate(rows[:-1])]
    # Calibration: context growth between two requests minus the earlier output, against the
    # characters that entered in between (no compaction between them).
    entered = collections.Counter()
    for _, _, chars, at in items:
        entered[at] += chars
    pairs = [k for k in range(1, len(rows)) if not any(k - 1 < c <= k for c in compactions)]
    out['calib_chars'] = sum(entered[k] for k in pairs)
    out['calib_tokens'] = sum(ctx[k] - ctx[k - 1] - rows[k - 1]['out'] for k in pairs)
    carried = []
    items = fixed + items
    for source, label, chars, at in items:
        end = next(e for e in ends if e >= at)
        cached = max(0, end - at - 1)
        dollars = toks(chars) * p_in * (write + cached * p_read) / 1e6
        carried.append({'source': source, 'label': label, 'tokens': toks(chars), 'requests': end - at, 'usd': dollars})
    by_source = collections.defaultdict(lambda: {'n': 0, 'tokens': 0, 'usd': 0.0})
    for c in carried:
        key = c['source'] if c['source'] != 'inject' else 'inject:' + c['label'].split(' | ')[0]
        by_source[key]['n'] += 1
        by_source[key]['tokens'] += c['tokens']
        by_source[key]['usd'] += c['usd']
    prompt = out['prompt'] or ''
    if out['kind'] == 'lead' and prompt.startswith('[Workflow harness'):
        out['kind'] = 'workflow'
    elif out['kind'] == 'lead' and re.match(r"Read '[^']*(\.brief\.md' and follow it|' and follow it\. Your result file is )", prompt):
        out['kind'] = 'worker'
    elif out['kind'] == 'lead' and len(rows) <= 3:
        out['kind'] = 'probe'
    out.update({'model': model, 'requests': len(rows), 'cost_usd': cost,
                'switches': sum(switch_at.values()), 'switch_tokens': sum(r['cw'] for r in switched),
                'switch_usd': switch_usd,
                'cost_parts': parts, 'w1h': sum(r['w1h'] for r in rows),
                'inp': sum(r['inp'] for r in rows), 'out': sum(r['out'] for r in rows),
                'cr': sum(r['cr'] for r in rows), 'cw': sum(r['cw'] for r in rows),
                'hit_rate': sum(r['cr'] for r in rows) / max(1, sum(r['cr'] + r['cw'] + r['inp'] for r in rows)),
                'hot_reads': {p: n for p, n in hot.items() if n >= 3},
                'ctx0': ctx[0] if ctx else 0, 'ctx_max': max(ctx, default=0), 'compactions': len(compactions),
                'start': rows[0]['t'] if rows else None,
                'tools': {k: v for k, v in tools.items()}, 'reads': dict(reads),
                'skill_calls': dict(out['skill_calls']), 'by_source': dict(by_source),
                'items': carried,
                'top': sorted((c for c in carried if c['source'] not in ('base', 'inherited', 'assistant')),
                              key=lambda c: -c['usd'])[:15],
                'injection_samples': sorted({c['label'] for c in carried if c['source'] == 'inject'})[:40]})
    return out


def transcripts(paths: list[Path], since: float) -> list[Path]:
    found = []
    for path in paths:
        files = [path] if path.is_file() else sorted(path.glob('*.jsonl')) + sorted(path.glob('*/subagents/**/*.jsonl'))
        found += [f for f in files if f.stat().st_mtime >= since]
    return sorted(found, key=lambda f: f.stat().st_mtime)


def usage_records(dirs: list[Path], since: float) -> list[dict]:
    rows = []
    for d in dirs:
        for f in sorted(d.glob('*.json')):
            try:
                rec = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            # recorded_at, not the file's mtime: a copied usage folder has the copy's mtime.
            stamp = rec.get('recorded_at')
            if stamp and datetime.fromisoformat(stamp).timestamp() < since:
                continue
            u = rec.get('usage') or {}
            rows.append({'file': str(f), 'callee': rec.get('callee'), 'model': rec.get('model_requested'),
                         'kind': (rec.get('task') or {}).get('kind'), 'status': rec.get('status'),
                         'inp': u.get('input_tokens') or 0, 'out': u.get('output_tokens') or 0,
                         'cr': u.get('cache_read_tokens') or 0, 'cw': u.get('cache_creation_tokens') or 0,
                         'usd': u.get('api_cost_usd_reported') or 0.0, 'ms': rec.get('duration_ms') or 0})
    return rows


def summary(sessions: list[dict], top: int) -> str:
    groups = collections.defaultdict(list)
    for s in sessions:
        groups['sub' if s['kind'].startswith('sub:') else s['kind']].append(s)
    lines = ['| type | sessions | requests | cost $ | output | ctx0 median | ctx max median | compactions |',
             '|---|---|---|---|---|---|---|---|']
    for kind, rows in sorted(groups.items()):
        med = lambda key: sorted(r[key] for r in rows)[len(rows) // 2]  # noqa: E731
        lines.append(f"| {kind} | {len(rows)} | {sum(r['requests'] for r in rows)} | "
                     f"{sum(r['cost_usd'] for r in rows):.2f} | {sum(r['out'] for r in rows)} | {med('ctx0')} | "
                     f"{med('ctx_max')} | {sum(r['compactions'] for r in rows)} |")
    sources = collections.defaultdict(lambda: [0, 0, 0.0])
    for s in sessions:
        for key, v in s['by_source'].items():
            sources[key][0] += v['n']
            sources[key][1] += v['tokens']
            sources[key][2] += v['usd']
    lines += ['', '| carried source | items | tokens | carried $ |', '|---|---|---|---|']
    for key, (n, t, usd) in sorted(sources.items(), key=lambda kv: -kv[1][2])[:top * 2]:
        lines.append(f'| {key} | {n} | {t} | {usd:.2f} |')
    switches = [s for s in sessions if s['switches']]
    if switches:
        lines += ['', f"Account switches: {sum(s['switches'] for s in switches)} in {len(switches)} sessions, "
                      f"{sum(s['switch_tokens'] for s in switches)} tokens rewritten, ${sum(s['switch_usd'] for s in switches):.2f} "
                      "(each switch rewrites every running session's context; a session over 150k hands off first: "
                      'docs/WORKFLOW.md, "Worker cost", rule 8).']
    # #338: every enabled plugin's skills are listed in every session, worker and sub-agent.
    listed = collections.defaultdict(lambda: [0, 0, 0])
    for s in sessions:
        for owner, chars in s['skill_listing'].items():
            listed[owner][0] += 1
            listed[owner][1] += toks(chars)
        for name, n in s['skill_calls'].items():
            listed[name.split(':')[0] if ':' in name else 'user/bundled'][2] += n
    if listed:
        lines += ['', '| skill listing owner | sessions | listed tokens | calls |', '|---|---|---|---|']
        lines += [f'| {o} | {n} | {t} | {c} |' for o, (n, t, c) in sorted(listed.items(), key=lambda kv: -kv[1][1])]
        idle = [o for o, (n, _, c) in listed.items() if n and not c and o != 'user/bundled']
        if idle:
            # Measured on Claude Code 2.1.316: skillOverrides hides a bundled or user skill, not a plugin's.
            lines += ['', 'Never called: ' + ', '.join(sorted(idle)) + '. A plugin this project does not need: '
                      '"NAME@MARKETPLACE": false under enabledPlugins in .claude/settings.json (lead, workers '
                      'and sub-agents); a bundled or user skill: "NAME": "off" under skillOverrides.']
    steps = sorted((dict(c, file=Path(s['file']).name, kind=s['kind']) for s in sessions for c in s['top']),
                   key=lambda c: -c['usd'])[:top]
    lines += ['', '| # | step | kind | tokens | re-read by | carried $ |', '|---|---|---|---|---|---|']
    lines += [f"| {i} | {c['label'][:80]} | {c['kind']} | {c['tokens']} | {c['requests']} | {c['usd']:.2f} |"
              for i, c in enumerate(steps, 1)]
    flagged = [(Path(s['file']).name, s) for s in sessions
               if (s['requests'] >= FLAG_MIN and s['hit_rate'] < HIT_FLOOR) or s['hot_reads'] or s['always_edits']]
    if flagged:
        lines += ['', '| flagged session | kind | cache hit | read 3+ times | always-loaded edits |', '|---|---|---|---|---|']
        lines += [f"| {name} | {s['kind']} | {s['hit_rate']:.0%} | "
                  f"{', '.join(f'{Path(p).name} x{n}' for p, n in sorted(s['hot_reads'].items(), key=lambda kv: -kv[1])[:5])} | "
                  f"{', '.join(Path(p).name for p in s['always_edits'][:5])} |" for name, s in flagged[:top]]
    return '\n'.join(lines)


def by_day(sessions: list[dict]) -> str:
    """One row per local calendar day of a transcript's first request; sub-agents add requests and $, not sessions."""
    days = collections.defaultdict(lambda: [0, 0, 0.0])
    for s in sessions:
        day = datetime.fromisoformat(s['start'].replace('Z', '+00:00')).astimezone().date().isoformat() if s['start'] else '?'
        days[day][0] += not s['kind'].startswith('sub:')
        days[day][1] += s['requests']
        days[day][2] += s['cost_usd']
    lines = ['| day | sessions | requests | cost $ |', '|---|---|---|---|']
    lines += [f'| {d} | {n} | {r} | {usd:.2f} |' for d, (n, r, usd) in sorted(days.items())]
    return '\n'.join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('paths', nargs='*', type=Path)
    parser.add_argument('--since', type=float, default=14.0, help='days back by file mtime (default 14)')
    parser.add_argument('--usage', type=Path, action='append', default=[])
    parser.add_argument('--json', type=Path)
    parser.add_argument('--top', type=int, default=10)
    parser.add_argument('--items', type=Path, help='every carried item, one JSON line each')
    parser.add_argument('--by-day', action='store_true', help='one row per day of session start instead of the summary')
    args = parser.parse_args(argv)
    since = time.time() - args.since * 86400
    seen: set = set()
    sessions = [audit(f, seen) for f in transcripts(args.paths, since)]
    sessions = [s for s in sessions if s['requests']]
    reviews = usage_records(args.usage, since)
    if args.items:
        with open(args.items, 'w') as stream:
            for s in sessions:
                for c in s['items']:
                    stream.write(json.dumps(dict(c, kind=s['kind'], file=s['file'])) + '\n')
    for s in sessions:
        del s['items']
    if args.json:
        args.json.write_text(json.dumps({'sessions': sessions, 'usage': reviews}, indent=1, default=str))
    if sessions:
        print(by_day(sessions) if args.by_day else summary(sessions, args.top))
    if reviews:
        by = collections.defaultdict(lambda: [0, 0.0, 0])
        for r in reviews:
            key = f"{r['kind']} {r['callee']} {r['model']}"
            by[key][0] += 1
            by[key][1] += r['usd']
            by[key][2] += r['out']
        print('\n| usage record | n | reported $ | output |\n|---|---|---|---|')
        for key, (n, usd, o) in sorted(by.items(), key=lambda kv: -kv[1][1]):
            print(f'| {key} | {n} | {usd:.2f} | {o} |')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
