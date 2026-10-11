#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Summarize the recorded review and proposal invocations by task and by model and effort.

Only the review adapters write records, so worker and sub-agent errands are not counted here.
A round is a completed review attempt whose dispatch chain, when it has one, also completed.
A verdict is read only from an archive whose bytes still match the record's sha256.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys


def evidence_fields(repo, record):
    """Effort and verdict from the archive, or why it has none."""
    effort, path = 'unknown', record.get('evidence')
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
        except ValueError:
            proposal = None
        if isinstance(proposal, dict) and isinstance(proposal.get('effort'), str):
            effort = proposal['effort']
    match = re.search(r'^\| effort \| (.*?) \|$', content, re.M)
    if match:
        effort = match[1]
    match = re.search(r'^VERDICT: (Accept with Manual Checks|Accept|Reject)[ \t]*$', content, re.M)
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
                status = '%s/%s' % (chain['status'], chain.get('failure_kind') or '-')
            except (OSError, ValueError, TypeError, KeyError):
                status = 'unreadable'
        cache[chain_id] = status
    return cache[chain_id]


def totals(rows):
    durations = [row['duration_ms'] for row in rows if isinstance(row.get('duration_ms'), (int, float))]
    missing = len(rows) - len(durations)
    return (f'invocations={len(rows)} rounds={sum(row["round"] for row in rows)}'
            f' duration={sum(durations) / 1000:.3f}s'
            + (f' (+{missing} unknown)' if missing else '')
            + f' rejects={sum(row["verdict"] == "Reject" for row in rows)}')


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
        except (OSError, ValueError):
            record = None
        if (not isinstance(record, dict) or not isinstance(record.get('invocation_id'), str)
                or not isinstance(record.get('task'), dict)):
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
        record.update(effort=effort, verdict=verdict, why=why,
                      round=completed and record['task'].get('kind') == 'review')
        rows.append(record)
    rows.sort(key=lambda row: (str(row.get('recorded_at')), row['invocation_id']))
    if not rows:
        print('No recorded invocations. This does not mean zero historical usage.')
    tasks, groups = defaultdict(list), defaultdict(list)
    for record in rows:
        tasks[str(record['task'].get('id') or 'unknown')].append(record)
        groups[f'Model {record.get("model_requested", "unknown")} / effort {record["effort"]}'].append(record)
    for task, records in sorted(tasks.items()):
        print(f'Task {task}: {totals(records)}')
        number = 0
        for record in records:
            number += record['round']
            duration = record.get('duration_ms')
            duration = f'{duration / 1000:.3f}s' if isinstance(duration, (int, float)) else 'unknown'
            verdict = record['verdict'] or f'none ({record["why"] or "no verdict line"})'
            print(f'  {f"round={number}" if record["round"] else "not a round"}'
                  f' kind={record["task"].get("kind", "unknown")} callee={record.get("callee", "unknown")}'
                  f' model={record.get("model_requested", "unknown")} effort={record["effort"]}'
                  f' verdict={verdict} duration={duration}')
    if rows:
        print(f'Total: {totals(rows)}')
    for group, records in sorted(groups.items()):
        print(f'{group}: {totals(records)}')
    if unreadable:
        print(f'Unreadable records skipped: {unreadable}')


if __name__ == '__main__':
    main()
