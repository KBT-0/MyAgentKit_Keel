#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Summarize the recorded review and proposal invocations by task and by model and effort.

Only the review adapters write records, so worker and sub-agent errands are not counted here.
A round is a completed review attempt whose dispatch chain, when it has one, also completed;
a shadow run (REVIEW_SHADOW=1) is listed apart and is no round. A verdict is read only from
an archive whose bytes still match the record's sha256; the findings are counted from it.
The author's dispositions carried by a round answer the earlier rounds under its label, so
their counts are credited to those rounds' configurations, split by the findings each round
listed, as author-claimed acceptance: accepted = fixed + deferred, out of fixed + disproved +
deferred. The author rates, the next round's reviewer verifies, and the owner decides what
the rate means (docs/USAGE.md).
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

CLAIM_KEYS = ('fixed', 'disproved', 'deferred')


def valid_record(record):
    """Validate every consumed field before a damaged record can affect healthy rows."""
    if (not isinstance(record, dict) or not isinstance(record.get('invocation_id'), str)
            or not isinstance(record.get('task'), dict)):
        return False
    for fields, value in ((('recorded_at', 'status', 'failure_kind', 'callee', 'model_requested',
                            'review_chain_id', 'evidence', 'evidence_sha256', 'backend'), record),
                          (('id', 'kind', 'behaviour', 'shadow'), record['task'])):
        if any(value.get(field) is not None and not isinstance(value[field], str) for field in fields):
            return False
    claims = record['task'].get('dispositions')
    if claims is not None and not (isinstance(claims, dict) and all(
            type(claims.get(key)) is int and claims[key] >= 0 for key in CLAIM_KEYS)):
        return False
    duration = record.get('duration_ms')
    return ('\0' not in (record.get('evidence') or '')
            and (duration is None or (type(duration) in (int, float)
                                     and 0 <= duration <= sys.float_info.max)))


def evidence_fields(repo, record):
    """Effort, verdict and finding count from the archive, or why it has no verdict."""
    effort, path = 'unknown', record.get('evidence')
    record['findings'] = 0
    if not isinstance(path, str) or not path:
        return effort, None, None
    path = Path(path)
    if not path.is_absolute():
        path = repo / path
    try:
        data = path.read_bytes()
    except OSError:
        return effort, None, 'evidence missing'
    if hashlib.sha256(data).hexdigest() != record.get('evidence_sha256'):
        return effort, None, 'evidence mismatch'
    content = data.decode('utf-8', 'replace')
    if content.lstrip().startswith('{'):
        try:
            proposal = json.loads(content)
        except Exception:  # RecursionError on deep nesting is damage too
            proposal = None
        if isinstance(proposal, dict) and isinstance(proposal.get('effort'), str):
            effort = proposal['effort']
    match = re.search(r'^\| effort \| (.*?) \|$', content, re.M)
    if match:
        effort = match[1]
    match = re.search(r'^VERDICT: (Accept with Manual Checks|Accept|Reject)[ \t]*$', content, re.M)
    # One severity-first top-level item per finding under the Findings heading (REVIEW_PROMPT asks
    # both reviewers for exactly that; the same forms as claude_bridge.FINDING_ITEM, which the
    # Codex Accept check reads), so a continuation bullet or a note is not a finding.
    findings = re.search(r'^(?:#{2,6}[ \t]+|\*\*)Findings(?:\*\*)?[ \t]*:?[ \t]*$(.*?)(?=^#{1,2} |\Z)',
                         content, re.M | re.S)
    record['findings'] = len(re.findall(r'^(?:[-*]|\d+\.|#{1,6})[ \t]+\**(?:Critical|High|Medium|Low)\b',
                                        findings[1], re.M | re.I)) if findings else 0
    return effort, match and match[1], None


def chain_status(usage, chain_id, cache):
    """The status of the chain's last checkpoint: the dispatcher can fail a completed attempt."""
    if chain_id not in cache:
        checkpoints = []
        for path in (usage / 'chains').glob('*.json'):
            name, _, number = path.stem.rpartition('-')
            if name == chain_id and number.isdigit():
                checkpoints.append((int(number), path))
        status = 'missing'
        if checkpoints:
            try:
                chain = json.loads(max(checkpoints)[1].read_text(encoding='utf-8'))
                if (not isinstance(chain, dict) or not isinstance(chain.get('status'), str)
                        or (chain.get('failure_kind') is not None
                            and not isinstance(chain['failure_kind'], str))):
                    raise ValueError('invalid chain fields')
                status = '%s/%s' % (chain['status'], chain.get('failure_kind') or '-')
            except Exception:  # RecursionError on deep nesting is damage too
                status = 'unreadable'
        cache[chain_id] = status
    return cache[chain_id]


def printable(value):
    """Escape control characters so a recorded value cannot rewrite or forge terminal lines."""
    return ''.join(char if char != '\\' and (char == ' ' or char.isprintable())
                   else char.encode('unicode_escape').decode('ascii') for char in str(value))


def totals(rows):
    durations = [row['duration_ms'] for row in rows if isinstance(row.get('duration_ms'), (int, float))]
    missing = len(rows) - len(durations)
    rounds = sum(row['round'] for row in rows)
    # Findings per measured run: every round, and every completed shadow run in its own group.
    runs = sum(row['measured'] for row in rows)
    findings = sum(row['findings'] for row in rows if row['measured'])
    accepted = sum(row['accepted'] for row in rows)
    claimed = sum(row['claimed'] for row in rows)
    return (f'invocations={len(rows)} rounds={rounds}'
            f' duration={sum(duration / 1000 for duration in durations):.3f}s'
            + (f' (+{missing} unknown)' if missing else '')
            + f' rejects={sum(row["verdict"] == "Reject" for row in rows)}'
            + f' findings={findings}'
            + (f' per_round={findings / runs:.1f}' if runs else '')
            # Author-claimed: fixed + deferred over every answered finding of these rounds.
            + (f' accepted={accepted:.3g}/{claimed:.3g} ({accepted / claimed:.2f}, author-claimed)'
               if claimed else ''))


def main():
    sys.stdout.reconfigure(errors='backslashreplace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    args = parser.parse_args()
    usage = args.repo / '.myagentkit/usage'
    rows, unreadable, chains = [], 0, {}
    # Not recursive: chains/ holds successive dispatch snapshots, not more paid invocations.
    for path in usage.glob('*.json'):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
        except Exception:  # RecursionError on deep nesting is damage too
            record = None
        if not valid_record(record):
            unreadable += 1
            continue
        effort, verdict, why = evidence_fields(args.repo, record)
        completed = record.get('status') == 'completed'
        if not completed:
            verdict, why = None, '%s/%s' % (record.get('status'), record.get('failure_kind') or '-')
        chain = record.get('review_chain_id')
        if completed and chain:
            status = chain_status(usage, chain, chains)
            if status.split('/')[0] != 'completed':
                completed, verdict, why = False, None, 'chain ' + status
        shadow = record['task'].get('shadow') == 'yes'
        measured = completed and record['task'].get('kind') == 'review'
        record.update(effort=effort, verdict=verdict, why=why, shadow=shadow, accepted=0, claimed=0,
                      measured=measured, round=measured and not shadow)
        rows.append(record)
    rows.sort(key=lambda row: (str(row.get('recorded_at')), row['invocation_id']))
    if not rows:
        print('No recorded invocations. This does not mean zero historical usage.')
    tasks, groups, behaviours = defaultdict(list), defaultdict(list), defaultdict(list)
    for record in rows:
        tasks[str(record['task'].get('id') or 'unknown')].append(record)
        # A missing, null or empty value and the label 'unknown' are one group: equal printed
        # labels always mean one group, and 'unknown' is reserved for a missing value.
        for key in ('model_requested', 'callee', 'effort'):
            record[key] = record.get(key) or 'unknown'
        record['task']['kind'] = record['task'].get('kind') or 'unknown'
        # A backend is its own group: one model name may be served by two endpoints.
        groups[(record['model_requested'], record['effort'], record.get('backend') or None,
                record['shadow'])].append(record)
        # BEHAVIOUR.md on or off for the reviewer (claude_bridge.py): the A/B's comparison.
        behaviours[record['task'].get('behaviour') or 'unknown'].append(record)
    for records in tasks.values():
        # The dispositions a round carries answer the earlier rounds under the same label
        # (the reviewer saw them all), so the answers are split over those rounds by the
        # findings each listed; rounds that listed none share nothing, and when none did,
        # the last round takes the answers. Only a round credits: a failed attempt, its
        # fallback and a shadow run carry the same file and would credit the answers again.
        earlier = []
        for record in records:
            claims = record['task'].get('dispositions')
            if claims and earlier and record['round']:
                weights = [round_['findings'] for round_ in earlier]
                if not sum(weights):
                    weights = [0] * (len(earlier) - 1) + [1]
                good, total = claims['fixed'] + claims['deferred'], sum(claims[key] for key in CLAIM_KEYS)
                for round_, weight in zip(earlier, weights):
                    round_['accepted'] += good * weight / sum(weights)
                    round_['claimed'] += total * weight / sum(weights)
            if record['round']:
                earlier.append(record)
    for task, records in sorted(tasks.items()):
        print(f'Task {printable(task)}: {totals(records)}')
        number = 0
        for record in records:
            number += record['round']
            duration = record.get('duration_ms')
            duration = f'{duration / 1000:.3f}s' if isinstance(duration, (int, float)) else 'unknown'
            verdict = record['verdict'] or f'none ({printable(record["why"] or "no verdict line")})'
            if record['shadow']:
                verdict += ' (shadow)'
            print(f'  {f"round={number}" if record["round"] else "not a round"}'
                  f' kind={printable(record["task"]["kind"])}'
                  f' callee={printable(record["callee"])}'
                  f' model={printable(record["model_requested"])}'
                  + (f' backend={printable(record["backend"])}' if record.get('backend') else '') +
                  f' effort={printable(record["effort"])} verdict={verdict} duration={duration}')
    if rows:
        print(f'Total: {totals(rows)}')
    for (model, effort, backend, shadow), records in sorted(groups.items(), key=lambda item: tuple(map(str, item[0]))):
        print(f'Model {printable(model)} / effort {printable(effort)}'
              + (f' / backend {printable(backend)}' if backend else '')
              + (' / shadow' if shadow else '') + f': {totals(records)}')
    for behaviour, records in sorted(behaviours.items()):
        print(f'Behaviour {printable(behaviour)}: {totals(records)}')
    if unreadable:
        print(f'Unreadable records skipped: {unreadable}')


if __name__ == '__main__':
    main()
