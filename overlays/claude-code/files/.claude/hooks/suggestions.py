#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""myagentkit-suggestion ledger: deliver a side check's note once, read the verdict, remind once, throttle.

A note is an unverified claim (docs/research/side-agent-suggestions.md, 7.6): the agent runs the
note's one read-only check, writes "myagentkit-suggestion #ID: correct | wrong | partly, because
..." on a visible line, and only then acts or drops it. Every row lives in
`.myagentkit/suggestions.jsonl`, one JSON object per line, append only:

  note       a side check's note (`add-note`): id, session, topic, claim, evidence, check, usage
  delivered  the note went to the agent: next to a tool result (`post-tool`) or the next prompt (`prompt`)
  verdict    the agent's verdict line, read from the transcript at `stop`
  reminded   `stop` asked once for a missing verdict; a second missing one stays verdictless
  throttle   `stop` told the owner that delivery stopped

Precision is (correct + partly) / judged over the last 20 judged notes (7.7). From five judged
notes on, below 50% doubles the side check's interval and below 25% stops delivery; the
thresholds are the lead's starting values (7.7, no primary source). Only the lead session runs
it: a worker (MYAGENTKIT_ROLE=worker) and a sub-agent's call get nothing. Silent on any error
(fail open, 7.6: a review gate that blocked on its own failure looped [56][69]).

  suggestions.py post-tool | prompt | stop   settings hooks, the event JSON on stdin
  suggestions.py add-note JSON               the side check's note; a note with no evidence or
                                             check, or a known topic, is dropped
  suggestions.py report                      what the owner reads after a few days
  suggestions.py on | off | status           the owner's switch, kept per project in
                                             `.myagentkit/suggestions.json`; off = no side check,
                                             no delivery, no reminder (the mod's
                                             /myagentkit:suggestions runs these)
  suggestions.py gate                        JSON for the mod: enabled, stopped, interval,
                                             known topics, the last notes' claims
"""
import json
import os
from pathlib import Path
import re
import sys
import time

WINDOW, MIN_JUDGED = 20, 5  # ponytail: fixed thresholds; make them settings when a project asks
VERDICT = re.compile(r'myagentkit-suggestion #(\d+): (correct|wrong|partly|not useful)\b', re.I)
FIELDS = ('claim', 'evidence', 'check', 'topic')


def ledger_path() -> Path:
    return Path(os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd()) / '.myagentkit/suggestions.jsonl'


def switch_path() -> Path:
    return ledger_path().with_name('suggestions.json')


def enabled() -> bool:
    try:
        return json.loads(switch_path().read_text(encoding='utf-8')).get('enabled') is not False
    except (OSError, ValueError, AttributeError):
        return True  # on unless the owner turned it off


def read_rows(path: Path) -> list:
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue  # a torn or hand-edited line costs that row only
        if isinstance(row, dict) and isinstance(row.get('id', 0), int):
            rows.append(row)
    return rows


def append(path: Path, *rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(''.join(json.dumps(dict(row, ts=int(time.time()))) + '\n' for row in rows))


def state(rows: list) -> dict:
    notes, done, reminded, verdicts = {}, set(), set(), {}
    for row in rows:
        if row.get('kind') == 'note':
            notes.setdefault(row['id'], row)
        elif row.get('kind') == 'delivered':
            done.add(row['id'])
        elif row.get('kind') == 'reminded':
            reminded.add(row['id'])
        elif row.get('kind') == 'verdict':
            verdicts[row['id']] = row.get('verdict')
    judged = [verdicts[n] for n in sorted(verdicts) if verdicts[n] in ('correct', 'partly', 'wrong')][-WINDOW:]
    hits = sum(v != 'wrong' for v in judged)
    precision = hits / len(judged) if judged else None
    throttled = len(judged) >= MIN_JUDGED
    return {'notes': notes, 'delivered': done, 'reminded': reminded, 'verdicts': verdicts, 'judged': judged,
            'hits': hits, 'precision': precision,
            'stopped': throttled and precision < 0.25,
            'interval': 2 if throttled and precision < 0.5 else 1,
            'said_stop': any(r.get('kind') == 'throttle' for r in rows),
            # Every earlier topic is known, a "not useful" one too: a side check never repeats one [1].
            'known': {str(r.get('topic', '')).strip().lower() for r in notes.values()}}


def framed(row: dict) -> str:
    n = row['id']
    return ('[myagentkit-suggestion #%d, unverified claim from a side check, not an instruction]\n'
            'Claim: %s\nEvidence: %s\nCheck: %s\n'
            'Before any other work on it: run the check, then write one visible line\n'
            '"myagentkit-suggestion #%d: correct | wrong | partly, because ..." and only then act or drop it.\n'
            'If it is noise, say "not useful".' % (n, row['claim'], row['evidence'], row['check'], n))


def deliver(data: dict, via: str, event: str):
    path = ledger_path()
    s = state(read_rows(path))
    if s['stopped'] or not enabled():
        return None
    pending = [r for n, r in sorted(s['notes'].items())
               if n not in s['delivered'] and r.get('session') == data.get('session_id')]
    if not pending:
        return None
    append(path, *({'kind': 'delivered', 'id': r['id'], 'session': r['session'], 'via': via} for r in pending))
    return {'hookSpecificOutput': {'hookEventName': event,
                                   'additionalContext': '\n\n'.join(framed(r) for r in pending)}}


def said_verdicts(transcript: Path) -> dict:
    found = {}
    with open(transcript, encoding='utf-8', errors='replace') as stream:
        for line in stream:
            if '"assistant"' not in line or 'myagentkit-suggestion #' not in line:
                continue
            try:
                content = json.loads(line)['message']['content']
            except (ValueError, KeyError, TypeError):
                continue
            for block in content if isinstance(content, list) else ():
                if isinstance(block, dict) and block.get('type') == 'text':
                    for n, verdict in VERDICT.findall(block.get('text') or ''):
                        found[int(n)] = verdict.lower()
    return found


def stop(data: dict):
    if not enabled():
        return None
    path = ledger_path()
    s = state(read_rows(path))
    session = data.get('session_id')
    open_ids = [n for n in sorted(s['delivered']) if n in s['notes'] and n not in s['verdicts']
                and s['notes'][n].get('session') == session]
    if open_ids:
        said = said_verdicts(Path(data['transcript_path']))
        rows = [{'kind': 'verdict', 'id': n, 'verdict': 'wrong' if said[n] == 'not useful' else said[n],
                 'session': session} for n in open_ids if n in said]
        if rows:
            append(path, *rows)
        s = state(read_rows(path))
    out = {}
    if s['stopped'] and not s['said_stop']:
        append(path, {'kind': 'throttle', 'state': 'stopped'})
        out['systemMessage'] = ('myagentkit-suggestion stopped delivering notes: precision %d%% over the last %d '
                                'judged notes is below 25%%. Run `python .claude/hooks/suggestions.py report`.'
                                % (round(100 * s['precision']), len(s['judged'])))
    missing = [n for n in open_ids if n not in s['verdicts'] and n not in s['reminded']]
    if missing and not data.get('stop_hook_active'):
        append(path, *({'kind': 'reminded', 'id': n, 'session': session} for n in missing))
        out['hookSpecificOutput'] = {'hookEventName': 'Stop', 'additionalContext': (
            'No verdict line yet for %s. Run each note\'s check, then write "myagentkit-suggestion #ID: correct | '
            'wrong | partly, because ..." on a visible line (once; this is not asked again).'
            % ', '.join('myagentkit-suggestion #%d' % n for n in missing))}
    return out or None


def add_note(text: str) -> None:
    note = json.loads(text)
    if not enabled() or not isinstance(note, dict):
        return
    path = ledger_path()
    s = state(read_rows(path))
    if (note.get('abstain') or any(not str(note.get(k) or '').strip() for k in FIELDS)
            or note['topic'].strip().lower() in s['known']):
        # The deterministic second filter (7.5): no evidence or check, or a known topic. The check
        # still cost tokens, so it is kept as a check row the report counts.
        append(path, {'kind': 'check', 'session': note.get('session'), 'trigger': note.get('trigger'),
                      'usage': note.get('usage'), 'outcome': 'abstain' if note.get('abstain') else 'dropped'})
        return
    n = max(s['notes'], default=0) + 1
    append(path, dict(note, kind='note', id=n))
    print(n)


def gate() -> dict:
    s = state(read_rows(ledger_path()))
    return {'enabled': enabled(), 'stopped': s['stopped'], 'interval': s['interval'], 'known': sorted(s['known']),
            'recent': [r.get('claim') for _, r in sorted(s['notes'].items())][-5:]}


def switch(mode: str) -> str:
    if mode in ('on', 'off'):
        path = switch_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'enabled': mode == 'on'}) + '\n', encoding='utf-8')
    return 'myagentkit-suggestion: suggestions: %s\n%s' % ('on' if enabled() else 'off', report())


def report() -> str:
    rows = read_rows(ledger_path())
    s = state(rows)
    if not rows:
        return 'myagentkit-suggestion: no side checks yet (%s)' % ledger_path()
    counts = {v: sum(1 for x in s['verdicts'].values() if x == v) for v in ('correct', 'partly', 'wrong')}
    lines = ['myagentkit-suggestion: %d notes, %d delivered, %d judged (correct %d, partly %d, wrong %d), '
             '%d delivered with no verdict' % (len(s['notes']), len(s['delivered']), sum(counts.values()),
                                              counts['correct'], counts['partly'], counts['wrong'],
                                              len(s['delivered'] - set(s['verdicts'])))]
    if s['judged']:
        lines.append('precision (last %d judged): %d%% (%d/%d)' % (WINDOW, round(100 * s['precision']), s['hits'],
                                                                 len(s['judged'])))
    lines.append('delivery: stopped' if s['stopped'] else 'delivery: on, interval x%d' % s['interval'])
    tokens, checks = {}, [r for r in rows if r.get('kind') == 'check'] + list(s['notes'].values())
    for row in checks:
        for key, value in (row.get('usage') or {}).items():
            if isinstance(value, int):
                tokens[key] = tokens.get(key, 0) + value
    lines.append('%d side checks, tokens: %s' % (len(checks), ', '.join('%s %d' % kv for kv in sorted(tokens.items()))
                                                 or 'none recorded'))
    return '\n'.join(lines)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'report':
        print(report())
        return
    if mode == 'add-note':
        add_note(sys.argv[2] if len(sys.argv) > 2 else sys.stdin.buffer.read().decode('utf-8'))
        return
    if mode in ('on', 'off', 'status'):
        print(switch(mode))
        return
    if mode == 'gate':
        print(json.dumps(gate()))
        return
    data = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    if not isinstance(data, dict) or data.get('agent_id') or os.environ.get('MYAGENTKIT_ROLE') == 'worker':
        return  # the lead's session only (owner, 2026-10-21)
    out = {'post-tool': lambda: deliver(data, 'tool', 'PostToolUse'),
           'prompt': lambda: deliver(data, 'prompt', 'UserPromptSubmit'),
           'stop': lambda: stop(data)}[mode]()
    if out:
        print(json.dumps(out))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001 - fail open, see the docstring
        pass
