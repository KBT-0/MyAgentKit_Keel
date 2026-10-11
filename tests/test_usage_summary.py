"""Summaries count completed review rounds once and read verdicts only from intact evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'core/scripts'))
import agent_usage  # noqa: E402

SCRIPT = ROOT / 'core/scripts/usage_summary.py'


class UsageSummaryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / '.gitignore').write_text('.myagentkit/\ndocs/reviews/\n')
        (self.repo / 'docs/reviews').mkdir(parents=True)

    def record(self, name, task, report=None, kind='review', callee='claude', model='opus',
               status='completed', reason=None, duration=1000, chain=''):
        """One record written by the adapters' own writer, so the schema is production's."""
        evidence = None
        if report is not None:
            evidence = self.repo / 'docs/reviews' / (name + '.md')
            evidence.write_bytes(report)
        with mock.patch.dict(os.environ, {'MYAGENTKIT_REVIEW_CHAIN_ID': chain}):
            path, _ = agent_usage.record(self.repo, callee, model, 'test', {'id': task, 'kind': kind},
                                         {'duration_ms': duration}, status, reason,
                                         evidence and str(evidence), report)
        return path

    def chain(self, chain_id, status, failure_kind=None):
        chains = self.repo / '.myagentkit/usage/chains'
        chains.mkdir(exist_ok=True)
        for number, value in enumerate(('pending', status)):
            (chains / f'{chain_id}-{number}.json').write_text(json.dumps(
                {'chain_id': chain_id, 'task_id': 'T', 'attempts': [{}] * number,
                 'status': value, 'failure_kind': failure_kind if number else None}))

    def summary(self, env=None):
        command = [sys.executable] + ([] if env else ['-I']) + [str(SCRIPT), '--repo', str(self.repo)]
        result = subprocess.run(command, capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_rounds_verdicts_and_groups(self):
        first = self.record('a', 'T1', b'| effort | high |\nVERDICT: Reject\n', chain='c1')
        self.chain('c1', 'completed')
        second = self.record('b', 'T1', b'| effort | medium |\nVERDICT: Accept\n', callee='codex',
                             model='sol', duration=2000)
        # Rounds follow recorded_at, never the file name or its random suffix.
        first.rename(first.with_name('z.json'))
        second.rename(second.with_name('a.json'))
        self.record('c', 'T1', b'VERDICT: Accept\n', status='failed', reason='quota', duration=500)
        self.record('d', 'T1', json.dumps({'mode': 'propose', 'effort': 'medium'}).encode(),
                    kind='propose', duration=300)
        self.record('e', 'T2', b'VERDICT: Accept\n', chain='c2')
        self.chain('c2', 'failed', 'stale_checkout')
        self.record('f', 'T2', b'VERDICT: Reject\n')
        (self.repo / 'docs/reviews/f.md').write_bytes(b'VERDICT: Accept\n')
        out = self.summary()
        for line in ('Task T1: invocations=4 rounds=2 duration=3.800s rejects=1',
                     '  round=1 kind=review callee=claude model=opus effort=high verdict=Reject duration=1.000s',
                     '  round=2 kind=review callee=codex model=sol effort=medium verdict=Accept duration=2.000s',
                     '  not a round kind=review callee=claude model=opus effort=unknown '
                     'verdict=none (failed/quota) duration=0.500s',
                     '  not a round kind=propose callee=claude model=opus effort=medium '
                     'verdict=none (no verdict line) duration=0.300s',
                     'Task T2: invocations=2 rounds=1 duration=2.000s rejects=0',
                     '  not a round kind=review callee=claude model=opus effort=unknown '
                     'verdict=none (chain failed/stale_checkout)',
                     '  round=1 kind=review callee=claude model=opus effort=unknown verdict=none (evidence mismatch)',
                     'Total: invocations=6 rounds=3 duration=5.800s rejects=1',
                     'Model opus / effort high: invocations=1 rounds=1 duration=1.000s rejects=1',
                     'Model sol / effort medium: invocations=1 rounds=1 duration=2.000s rejects=0'):
            self.assertIn(line, out)
        # chains/ snapshots are not records: read as records they would count as unreadable.
        self.assertNotIn('Unreadable', out)
        self.assertNotIn('Tier', out)

    def test_damaged_records_leave_the_rest_of_the_summary(self):
        self.record('g', 'T3', b'\xff\n| effort | high |\nVERDICT: Reject\n')
        usage = self.repo / '.myagentkit/usage'
        (usage / 'truncated.json').write_text('{"invocation_id": "x"')
        (usage / 'no-task.json').write_text(json.dumps({'invocation_id': 'y', 'task': None}))
        (usage / 'no-id.json').write_text(json.dumps({'task': {'id': 'T9', 'kind': 'review'}}))
        out = self.summary()
        self.assertIn('Task T3: invocations=1 rounds=1 duration=1.000s rejects=1', out)
        self.assertIn('effort=high verdict=Reject', out)
        self.assertIn('Unreadable records skipped: 3', out)
        self.assertNotIn('T9', out)

    def test_a_task_label_the_console_cannot_encode_is_escaped(self):
        self.record('h', 'fix→lexer', b'VERDICT: Accept\n')
        out = self.summary(dict(os.environ, PYTHONIOENCODING='ascii'))
        self.assertIn('Task fix\\u2192lexer: invocations=1 rounds=1', out)

    def test_bad_chain_id_and_evidence_path_are_damaged_records(self):
        self.record('healthy', 'healthy', b'VERDICT: Accept\n')
        path = self.record('bad', 'damaged', b'VERDICT: Reject\n')
        original = json.loads(path.read_text())
        for field, value in (('review_chain_id', ['c1']), ('evidence', 'bad\0path')):
            with self.subTest(field=field):
                path.write_text(json.dumps(dict(original, **{field: value})))
                out = self.summary()
                self.assertIn('Task healthy: invocations=1 rounds=1', out)
                self.assertIn('Unreadable records skipped: 1', out)
                self.assertNotIn('Task damaged:', out)

    def test_every_consumed_field_rejects_invalid_values(self):
        self.record('healthy', 'healthy', b'VERDICT: Accept\n')
        path = self.record('bad', 'damaged', b'VERDICT: Reject\n')
        original = json.loads(path.read_text())
        cases = [(field, []) for field in (
            'invocation_id', 'recorded_at', 'status', 'failure_kind', 'callee',
            'model_requested', 'review_chain_id', 'evidence', 'evidence_sha256', 'task')]
        cases += [('task', {'id': [], 'kind': 'review'}),
                  ('task', {'id': 'damaged', 'kind': []})]
        cases += [('duration_ms', value) for value in ([], '1000', True, -1, float('nan'), float('inf'), 10 ** 400)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                path.write_text(json.dumps(dict(original, **{field: value})))
                out = self.summary()
                self.assertIn('Task healthy: invocations=1 rounds=1', out)
                self.assertIn('Unreadable records skipped: 1', out)
                self.assertNotIn('Task damaged:', out)
                self.assertIn('Total: invocations=1 rounds=1 duration=1.000s rejects=0', out)

    def test_control_characters_in_task_labels_are_escaped(self):
        self.record('controls', 'fix\nTotal: forged\r\t\x1b[2J\x7f\x85', b'VERDICT: Accept\n')
        out = self.summary()
        self.assertIn('Task fix\\nTotal: forged\\r\\t\\x1b[2J\\x7f\\x85: invocations=1 rounds=1', out)
        self.assertEqual(sum(line.startswith('Total:') for line in out.splitlines()), 1)
        for control in ('\r', '\t', '\x1b', '\x7f', '\x85'):
            self.assertNotIn(control, out)


if __name__ == '__main__':
    unittest.main()
