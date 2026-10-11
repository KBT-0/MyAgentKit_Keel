"""Summaries count invocations once, including failures and dispatch fallback attempts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UsageSummaryTests(unittest.TestCase):
    def test_records_chains_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            usage = repo / '.myagentkit/usage'
            (usage / 'chains').mkdir(parents=True)
            rows = [
                ('a', 'T1', 'claude', 'opus', 'high', 'Reject', 1000, 'gate'),
                ('b', 'T1', 'codex', 'sol', 'medium', 'Accept', 2000, None),
                ('c', 'T2', 'codex', 'sol', None, None, 500, 'mechanical'),
            ]
            for invocation, task, reviewer, model, effort, verdict, duration, tier in rows:
                evidence = repo / (invocation + '.md')
                if verdict:
                    evidence.write_text(f'| effort | {effort} |\nVERDICT: {verdict}\n', encoding='utf-8')
                record = dict(invocation_id=invocation, task={'id': task, 'tier': tier},
                              callee=reviewer, model_requested=model, duration_ms=duration,
                              evidence=str(evidence), status='completed' if verdict else 'failed',
                              failure_kind=None if verdict else 'quota')
                (usage / (invocation + '.json')).write_text(json.dumps(record), encoding='utf-8')
            for checkpoint in range(3):
                (usage / 'chains' / f'chain-{checkpoint}.json').write_text(
                    json.dumps({'chain_id': 'chain', 'task_id': 'T1', 'attempts': rows[:checkpoint]}))
            result = subprocess.run([sys.executable, '-I', str(ROOT / 'core/scripts/usage_summary.py'),
                                     '--repo', str(repo)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for line in ('Task T1: rounds=2', 'claude model=opus effort=high verdict=Reject duration=1.000s',
                         'codex model=sol effort=medium verdict=Accept duration=2.000s',
                         'Task T2: rounds=1', 'effort=unknown verdict=none (failed/quota)',
                         'Total: rounds=3 duration=3.500s rejects=1',
                         'Tier gate: rounds=1', 'Model sol / effort medium: rounds=1',
                         'Tier mechanical: rounds=1'):
                self.assertIn(line, result.stdout)
            # Proposal evidence is JSON rather than the reviews' Markdown header table.
            (repo / 'c.md').write_text(json.dumps({'mode': 'propose', 'effort': 'medium'}), encoding='utf-8')
            result = subprocess.run([sys.executable, '-I', str(ROOT / 'core/scripts/usage_summary.py'),
                                     '--repo', str(repo)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('model=sol effort=medium verdict=none (failed/quota)', result.stdout)


if __name__ == '__main__':
    unittest.main()
