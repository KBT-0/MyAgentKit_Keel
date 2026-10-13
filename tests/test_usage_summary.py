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
               status='completed', reason=None, duration=1000, chain='', behaviour=None, backend=None,
               dispositions=None, shadow=None):
        """One record written by the adapters' own writer, so the schema is production's."""
        evidence = None
        if report is not None:
            evidence = self.repo / 'docs/reviews' / (name + '.md')
            evidence.write_bytes(report)
        with mock.patch.dict(os.environ, {'MYAGENTKIT_REVIEW_CHAIN_ID': chain}):
            path, _ = agent_usage.record(self.repo, callee, model, 'test',
                                         {'id': task, 'kind': kind, **({'behaviour': behaviour} if behaviour else {}),
                                          **({'dispositions': dispositions} if dispositions else {}),
                                          **({'shadow': shadow} if shadow else {})},
                                         {'duration_ms': duration}, status, reason,
                                         evidence and str(evidence), report, backend=backend)
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

    def test_rounds_and_rejects_are_totalled_by_behaviour_appendix(self):
        # The A/B of issue #74: the same totals with BEHAVIOUR.md on and off; a record from
        # before the field (or from Codex) is unknown, never counted as either side.
        self.record('a', 'T', b'VERDICT: Reject\n', behaviour='on')
        self.record('b', 'T', b'VERDICT: Accept\n', behaviour='off', duration=2000)
        self.record('c', 'T', b'VERDICT: Accept\n', duration=3000)
        out = self.summary()
        for line in ('Behaviour on: invocations=1 rounds=1 duration=1.000s rejects=1',
                     'Behaviour off: invocations=1 rounds=1 duration=2.000s rejects=0',
                     'Behaviour unknown: invocations=1 rounds=1 duration=3.000s rejects=0'):
            self.assertIn(line, out)

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

    def test_deeply_nested_json_is_damaged_not_fatal(self):
        nested = '[' * 100000 + ']' * 100000
        for site in ('record', 'chain', 'evidence'):
            with self.subTest(site=site):
                self.setUp()
                self.record('healthy', 'healthy', b'VERDICT: Accept\n')
                if site == 'record':
                    (self.repo / '.myagentkit/usage/deep.json').write_text(nested)
                elif site == 'chain':
                    self.record('deep', 'deep', b'VERDICT: Accept\n', chain='c1')
                    self.chain('c1', 'completed')
                    (self.repo / '.myagentkit/usage/chains/c1-2.json').write_text(nested)
                else:
                    self.record('deep', 'deep', ('{"effort": %s}' % nested).encode())
                out = self.summary()
                self.assertIn('Task healthy: invocations=1 rounds=1', out)
                self.assertIn({'record': 'Unreadable records skipped: 1',
                               'chain': 'verdict=none (chain unreadable)',
                               'evidence': 'Task deep: invocations=1 rounds=1'}[site], out)

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
            'model_requested', 'review_chain_id', 'evidence', 'evidence_sha256', 'backend', 'task')]
        cases += [('task', {'id': [], 'kind': 'review'}),
                  ('task', {'id': 'damaged', 'kind': []}),
                  ('task', {'id': 'damaged', 'kind': 'review', 'behaviour': []})]
        cases += [('duration_ms', value) for value in ([], '1000', True, -1, float('nan'), float('inf'), 10 ** 400)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                path.write_text(json.dumps(dict(original, **{field: value})))
                out = self.summary()
                self.assertIn('Task healthy: invocations=1 rounds=1', out)
                self.assertIn('Unreadable records skipped: 1', out)
                self.assertNotIn('Task damaged:', out)
                self.assertIn('Total: invocations=1 rounds=1 duration=1.000s rejects=0', out)

    def test_a_backend_is_shown_and_grouped_only_when_recorded(self):
        # One model name served by two endpoints: the backend keeps their numbers apart.
        self.record('a', 'T', b'| effort | high |\nVERDICT: Accept\n', model='glm-x', backend='glm')
        self.record('b', 'T', b'| effort | high |\nVERDICT: Reject\n', model='glm-x')
        out = self.summary()
        self.assertIn(' callee=claude model=glm-x backend=glm effort=high verdict=Accept ', out)
        self.assertIn(' callee=claude model=glm-x effort=high verdict=Reject ', out)
        self.assertIn('Model glm-x / effort high / backend glm: invocations=1 rounds=1 '
                      'duration=1.000s rejects=0', out)
        self.assertIn('Model glm-x / effort high: invocations=1 rounds=1 duration=1.000s rejects=1', out)
        self.assertEqual(out.count('backend'), 2)

    def test_control_and_literal_escape_values_have_distinct_groups(self):
        for name, value in (('control', '\x1b'), ('literal', r'\x1b')):
            self.record(name, 'T', json.dumps({'effort': value}).encode(), model=value)
        out = self.summary()
        self.assertIn('Total: invocations=2 rounds=2', out)
        groups = [line for line in out.splitlines() if line.startswith('Model ')]
        self.assertEqual(len(groups), 2)
        for value in (r'\x1b', r'\\x1b'):
            self.assertTrue(any(line.startswith(f'Model {value} / effort {value}: invocations=1 '
                                                'rounds=1 duration=1.000s rejects=0') for line in groups), groups)

    def test_dispositions_are_credited_to_the_round_they_answer(self):
        # Round 2 carries the author's answers to round 1's findings: the counts belong to
        # round 1's configuration (opus/high), and the rate says it is the author's claim.
        self.record('a', 'T', b'| effort | high |\nVERDICT: Reject\n\n## Findings\n\n- High x\n- **Low** y\n'
                    b'- a continuation bullet, no severity\n- low z\n\n## Manual checks\n\n- High: not a finding\n')
        self.record('b', 'T', b'| effort | medium |\nVERDICT: Accept\n\n## Findings\n\nNone.\n',
                    callee='codex', model='sol', duration=2000,
                    dispositions={'fixed': 1, 'disproved': 1, 'deferred': 1})
        out = self.summary()
        self.assertIn('Task T: invocations=2 rounds=2 duration=3.000s rejects=1 findings=3 per_round=1.5 '
                      'accepted=2/3 (0.67, author-claimed)', out)
        self.assertIn('Model opus / effort high: invocations=1 rounds=1 duration=1.000s rejects=1 '
                      'findings=3 per_round=3.0 accepted=2/3 (0.67, author-claimed)', out)
        self.assertIn('Model sol / effort medium: invocations=1 rounds=1 duration=2.000s rejects=0 '
                      'findings=0 per_round=0.0\n', out)

    def test_only_a_round_credits_the_round_before_it(self):
        # A failed attempt, its fallback and a shadow run carry the same file: one credit.
        self.record('a', 'T', b'VERDICT: Reject\n')
        claims = {'fixed': 2, 'disproved': 1, 'deferred': 0}
        self.record('b', 'T', None, status='failed', reason='timeout', dispositions=claims)
        self.record('c', 'T', b'VERDICT: Accept\n', shadow='yes', dispositions=claims)
        self.record('d', 'T', b'VERDICT: Accept\n', callee='codex', model='sol', dispositions=claims)
        out = self.summary()
        self.assertIn('accepted=2/3 (0.67, author-claimed)', out)
        self.assertNotIn('accepted=4/6', out)
        self.assertNotIn('accepted=6/9', out)

    def test_answers_are_split_over_the_rounds_they_refer_to(self):
        # Round 3 answers rounds 1 and 2 together: the credit follows the findings each
        # round listed, so Codex's five and Claude's two are rated apart.
        self.record('a', 'T', b'| effort | high |\nVERDICT: Reject\n\n## Findings\n\n- High a\n- High b\n'
                    b'- Medium c\n- Low d\n- Low e\n', callee='codex', model='sol')
        self.record('b', 'T', b'| effort | medium |\nVERDICT: Reject\n\n## Findings\n\n- Medium f\n- Low g\n',
                    duration=2000)
        self.record('c', 'T', b'| effort | medium |\nVERDICT: Accept\n', duration=3000,
                    dispositions={'fixed': 6, 'disproved': 1, 'deferred': 0})
        out = self.summary()
        self.assertIn('Model sol / effort high: invocations=1 rounds=1 duration=1.000s rejects=1 '
                      'findings=5 per_round=5.0 accepted=4.29/5 (0.86, author-claimed)', out)
        self.assertIn('Model opus / effort medium: invocations=2 rounds=2 duration=5.000s rejects=1 '
                      'findings=2 per_round=1.0 accepted=1.71/2 (0.86, author-claimed)', out)
        self.assertIn('Task T: invocations=3 rounds=3 duration=6.000s rejects=2 findings=7 per_round=2.3 '
                      'accepted=6/7 (0.86, author-claimed)', out)

    def test_dispositions_without_an_earlier_round_credit_nothing(self):
        # A first round carrying dispositions (another label's rounds) credits no one.
        self.record('a', 'T', b'VERDICT: Accept\n', dispositions={'fixed': 2, 'disproved': 0, 'deferred': 0})
        self.record('b', 'T', b'VERDICT: Accept\n', dispositions={'fixed': 'two', 'disproved': 0, 'deferred': 0})
        out = self.summary()
        self.assertNotIn('accepted=', out)
        self.assertIn('Unreadable records skipped: 1', out)

    def test_a_shadow_run_is_listed_apart_and_is_no_round(self):
        # REVIEW_SHADOW=1 measures a configuration: its verdict is shown, never a round, and
        # its group stands apart from the same model and effort run for real.
        self.record('a', 'T', b'| effort | low |\nVERDICT: Reject\n\n## Findings\n\n- High x\n- Medium y\n',
                    model='sonnet', shadow='yes')
        self.record('b', 'T', b'| effort | low |\nVERDICT: Accept\n', model='sonnet', duration=2000)
        out = self.summary()
        self.assertIn('  not a round kind=review callee=claude model=sonnet effort=low verdict=Reject (shadow)', out)
        self.assertIn('Task T: invocations=2 rounds=1 duration=3.000s rejects=1', out)
        self.assertIn('Model sonnet / effort low / shadow: invocations=1 rounds=0 duration=1.000s rejects=1 '
                      'findings=2 per_round=2.0', out)
        self.assertIn('Model sonnet / effort low: invocations=1 rounds=1 duration=2.000s rejects=0', out)

    def test_null_model_is_unknown_and_not_the_label_none(self):
        self.record('a', 'T1', b'VERDICT: Accept\n', model=None)
        self.record('b', 'T1', b'VERDICT: Accept\n', model='None')
        self.record('c', 'T1', b'VERDICT: Accept\n', model='unknown')
        self.record('d', 'T1', b'| effort |  |\nVERDICT: Accept\n', callee=None, kind=None)
        out = self.summary()
        self.assertIn('Model None / effort unknown: invocations=1 ', out)
        self.assertIn('Model unknown / effort unknown: invocations=2 ', out)
        self.assertIn('Model opus / effort unknown: invocations=1 ', out)
        self.assertIn(' kind=unknown callee=unknown model=opus effort=unknown ', out)
        self.assertEqual(out.count('Model None'), 1)
        self.assertNotIn('=None', out.replace('model=None', ''))

    def test_control_characters_in_task_labels_are_escaped(self):
        self.record('controls', 'fix\nTotal: forged\r\t\x1b[2J\x7f\x85', b'VERDICT: Accept\n')
        self.record('model', 'model', b'| effort | x\x1b[2J\x0bTotal: forged |\nVERDICT: Accept\n',
                    model='m\x1b[31m\nTotal: forged', kind='k\x1b[2J', callee='c\x1b[0m')
        out = self.summary()
        self.assertIn('model=m\\x1b[31m\\nTotal: forged effort=x\\x1b[2J\\x0bTotal: forged', out)
        self.assertIn('Model m\\x1b[31m\\nTotal: forged / effort x\\x1b[2J\\x0bTotal: forged:', out)
        self.assertIn('Task fix\\nTotal: forged\\r\\t\\x1b[2J\\x7f\\x85: invocations=1 rounds=1', out)
        self.assertEqual(sum(line.startswith('Total:') for line in out.splitlines()), 1)
        for control in ('\r', '\t', '\x1b', '\x7f', '\x85'):
            self.assertNotIn(control, out)


if __name__ == '__main__':
    unittest.main()
