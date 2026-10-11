#!/usr/bin/env python3
"""Summarize local invocations by task and tier without counting chain checkpoints twice."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re


def evidence_fields(repo, record):
    """Read review headers or the Claude proposal's JSON evidence."""
    effort = record.get('effort') or record.get('task', {}).get('effort') or 'unknown'
    verdict = None
    path = record.get('evidence')
    if path:
        path = Path(path)
        if not path.is_absolute():
            path = repo / path
        try:
            content = path.read_text(encoding='utf-8')
        except OSError:
            content = ''
        if content.lstrip().startswith('{'):
            try:
                proposal = json.loads(content)
            except json.JSONDecodeError:
                proposal = {}
            effort = proposal.get('effort') or effort
        match = re.search(r'^\| effort \| (.*?) \|$', content, re.M)
        if match:
            effort = match[1]
        match = re.search(r'^VERDICT: (Accept with Manual Checks|Accept|Reject)[ \t]*$', content, re.M)
        if match and record.get('status') == 'completed':
            verdict = match[1]
    return effort, verdict


def totals(rows):
    durations = [row['duration_ms'] for row in rows if isinstance(row.get('duration_ms'), (int, float))]
    missing = len(rows) - len(durations)
    return (f'rounds={len(rows)} duration={sum(durations) / 1000:.3f}s'
            + (f' (+{missing} unknown)' if missing else '')
            + f' rejects={sum(row["verdict"] == "Reject" for row in rows)}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    args = parser.parse_args()
    tasks, groups, rows = defaultdict(list), defaultdict(list), []
    # chains/ contains successive dispatch snapshots, not additional paid invocations.
    for path in sorted((args.repo / '.myagentkit/usage').glob('*.json')):
        record = json.loads(path.read_text(encoding='utf-8'))
        if not record.get('invocation_id'):
            continue
        effort, verdict = evidence_fields(args.repo, record)
        record.update(effort=effort, verdict=verdict)
        task = record.get('task', {})
        tasks[task.get('id') or 'unknown'].append(record)
        tier = task.get('tier') or record.get('tier')
        group = f'Tier {tier}' if tier else f'Model {record.get("model_requested", "unknown")} / effort {effort}'
        groups[group].append(record)
        rows.append(record)
    if not rows:
        print('No recorded invocations. This does not mean zero historical usage.')
        return
    for task, records in sorted(tasks.items()):
        print(f'Task {task}: {totals(records)}')
        for index, record in enumerate(records, 1):
            duration = record.get('duration_ms')
            duration = f'{duration / 1000:.3f}s' if isinstance(duration, (int, float)) else 'unknown'
            verdict = record['verdict'] or f'none ({record.get("status", "unknown")}/{record.get("failure_kind") or "unknown"})'
            print(f'  round={index} reviewer={record.get("callee", "unknown")} '
                  f'model={record.get("model_requested", "unknown")} effort={record["effort"]} '
                  f'verdict={verdict} duration={duration}')
    print(f'Total: {totals(rows)}')
    for group, records in sorted(groups.items()):
        print(f'{group}: {totals(records)}')


if __name__ == '__main__':
    main()
