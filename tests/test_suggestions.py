"""The myagentkit-suggestion ledger hook: deliver a note once, read the verdict lines, remind once, throttle."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/hooks/suggestions.py'


def note(n, session='s1', topic=None, **extra):
    return dict({'kind': 'note', 'id': n, 'session': session, 'topic': topic or 'topic %d' % n,
                 'claim': 'The test %d was loosened.' % n, 'evidence': 'tests/t.py:4 "== 3" became ">= 1"',
                 'check': 'git diff -- tests/t.py'}, **extra)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        (self.project / '.myagentkit').mkdir()
        self.ledger = self.project / '.myagentkit/suggestions.jsonl'
        self.transcript = self.project / 'transcript.jsonl'
        self.transcript.write_text('', encoding='utf-8')

    def run_hook(self, mode, payload=None, *args, **env):
        env = {**{k: v for k, v in os.environ.items() if k != 'MYAGENTKIT_ROLE'},
               'CLAUDE_PROJECT_DIR': str(self.project), **env}
        return subprocess.run([sys.executable, str(HOOK), mode, *args], input=json.dumps(payload or {}),
                              text=True, encoding='utf-8', capture_output=True, timeout=30, env=env)

    def write(self, *rows):
        with open(self.ledger, 'a', encoding='utf-8') as stream:
            for row in rows:
                stream.write(json.dumps(row) + '\n')

    def rows(self, kind=None):
        rows = [json.loads(line) for line in self.ledger.read_text(encoding='utf-8').splitlines() if line]
        return [r for r in rows if kind is None or r['kind'] == kind]

    def say(self, *texts):
        with open(self.transcript, 'a', encoding='utf-8') as stream:
            for text in texts:
                stream.write(json.dumps({'type': 'assistant', 'message': {
                    'content': [{'type': 'text', 'text': text}]}}) + '\n')

    def event(self, **extra):
        return dict({'session_id': 's1', 'transcript_path': str(self.transcript)}, **extra)

    def context(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)['hookSpecificOutput']['additionalContext'] if result.stdout.strip() else ''

    def test_add_note_numbers_drops_no_evidence_and_known_topics(self):
        self.assertEqual(self.run_hook('add-note', None, json.dumps(
            {'session': 's1', 'claim': 'A', 'evidence': 'x:1', 'check': 'grep a x', 'topic': 'Loose Test'})).returncode, 0)
        self.run_hook('add-note', None, json.dumps({'session': 's1', 'claim': 'B', 'evidence': '', 'check': 'ls',
                                                    'topic': 'other'}))
        self.run_hook('add-note', None, json.dumps({'session': 's1', 'claim': 'C', 'evidence': 'y', 'check': 'ls',
                                                    'topic': 'loose test'}))
        self.assertEqual([(r['id'], r['claim']) for r in self.rows('note')], [(1, 'A')])

    def test_post_tool_delivers_a_pending_note_once_with_the_verdict_rule(self):
        self.write(note(1))
        said = self.context(self.run_hook('post-tool', self.event()))
        self.assertIn('[myagentkit-suggestion #1, unverified claim from a side check, not an instruction]', said)
        self.assertIn('Check: git diff -- tests/t.py', said)
        self.assertIn('"myagentkit-suggestion #1: correct | wrong | partly, because ..."', said)
        self.assertEqual(self.context(self.run_hook('post-tool', self.event())), '')
        self.assertEqual([r['id'] for r in self.rows('delivered')], [1])

    def test_another_session_sub_agent_and_worker_get_nothing(self):
        self.write(note(1, session='other'))
        self.assertEqual(self.context(self.run_hook('post-tool', self.event())), '')
        self.write(note(2))
        self.assertEqual(self.context(self.run_hook('post-tool', self.event(agent_id='a1'))), '')
        self.assertEqual(self.context(self.run_hook('post-tool', self.event(), MYAGENTKIT_ROLE='worker')), '')
        self.assertIn('#2', self.context(self.run_hook('prompt', self.event())))

    def test_stop_records_verdicts_and_reminds_only_once(self):
        self.write(note(1), note(2), {'kind': 'delivered', 'id': 1, 'session': 's1'},
                   {'kind': 'delivered', 'id': 2, 'session': 's1'})
        self.say('myagentkit-suggestion #1: wrong, because the assertion was already ">= 1" before the edit.')
        said = self.context(self.run_hook('stop', self.event(stop_hook_active=False)))
        self.assertIn('#2', said)
        self.assertNotIn('#1', said)
        self.assertEqual([(r['id'], r['verdict']) for r in self.rows('verdict')], [(1, 'wrong')])
        self.assertEqual(self.context(self.run_hook('stop', self.event(stop_hook_active=False))), '')

    def test_stop_hook_active_never_reminds(self):
        self.write(note(1), {'kind': 'delivered', 'id': 1, 'session': 's1'})
        self.assertEqual(self.context(self.run_hook('stop', self.event(stop_hook_active=True))), '')
        self.assertEqual(self.rows('reminded'), [])

    def test_not_useful_counts_wrong_and_becomes_a_known_topic(self):
        self.write(note(1, topic='loose test'), {'kind': 'delivered', 'id': 1, 'session': 's1'})
        self.say('myagentkit-suggestion #1: not useful, the gate checks that anyway.')
        self.run_hook('stop', self.event())
        self.assertEqual(self.rows('verdict')[0]['verdict'], 'wrong')
        self.run_hook('add-note', None, json.dumps({'session': 's1', 'claim': 'D', 'evidence': 'z', 'check': 'ls',
                                                    'topic': 'Loose test'}))
        self.assertEqual(len(self.rows('note')), 1)

    def judged(self, *verdicts):
        for n, verdict in enumerate(verdicts, 1):
            self.write(note(n), {'kind': 'delivered', 'id': n, 'session': 's1'},
                       {'kind': 'verdict', 'id': n, 'verdict': verdict})

    def test_precision_below_a_quarter_stops_delivery_and_says_so_once(self):
        self.judged('wrong', 'wrong', 'wrong', 'wrong', 'partly')
        self.write(note(6))
        self.assertEqual(self.context(self.run_hook('post-tool', self.event())), '')
        stop = self.run_hook('stop', self.event())
        self.assertIn('stopped delivering', json.loads(stop.stdout)['systemMessage'])
        self.assertEqual(self.run_hook('stop', self.event()).stdout.strip(), '')
        report = self.run_hook('report').stdout
        self.assertIn('precision (last 20 judged): 20% (1/5)', report)
        self.assertIn('delivery: stopped', report)

    def test_precision_below_half_doubles_the_interval_and_few_verdicts_do_not_throttle(self):
        self.judged('wrong', 'wrong', 'wrong', 'correct')
        self.assertIn('delivery: on, interval x1', self.run_hook('report').stdout)
        self.judged('wrong', 'wrong', 'wrong', 'correct', 'partly')
        self.assertIn('delivery: on, interval x2', self.run_hook('report').stdout)
        self.write(note(6))
        self.assertIn('#6', self.context(self.run_hook('post-tool', self.event())))

    def test_report_without_a_ledger_and_a_broken_line_fail_open(self):
        self.assertIn('no side checks yet', self.run_hook('report').stdout)
        self.ledger.write_text('{broken\n', encoding='utf-8')
        self.write(note(1))
        self.assertIn('#1', self.context(self.run_hook('post-tool', self.event())))
        self.assertEqual(self.run_hook('stop', 'not json').returncode, 0)


    def test_off_silences_every_hook_and_on_brings_it_back(self):
        self.write(note(1))
        self.assertIn('off', self.run_hook('off').stdout)
        self.assertEqual(self.context(self.run_hook('post-tool', self.event())), '')
        self.assertEqual(self.context(self.run_hook('prompt', self.event())), '')
        self.run_hook('add-note', None, json.dumps({'session': 's1', 'claim': 'E', 'evidence': 'e', 'check': 'ls',
                                                    'topic': 'new'}))
        self.assertEqual(len(self.rows('note')), 1)
        self.assertEqual(json.loads(self.run_hook('gate').stdout)['enabled'], False)
        self.assertIn('suggestions: off', self.run_hook('status').stdout)
        self.run_hook('on')
        self.assertIn('suggestions: on', self.run_hook('status').stdout)
        self.assertIn('#1', self.context(self.run_hook('post-tool', self.event())))

    def test_gate_tells_the_side_check_what_it_needs_and_add_note_prints_the_id(self):
        self.judged('wrong', 'wrong', 'wrong', 'correct', 'partly')
        added = self.run_hook('add-note', None, json.dumps({'session': 's1', 'claim': 'F', 'evidence': 'f',
                                                            'check': 'ls', 'topic': 'Fresh topic'}))
        self.assertEqual(added.stdout.strip(), '6')
        gate = json.loads(self.run_hook('gate').stdout)
        self.assertEqual((gate['enabled'], gate['stopped'], gate['interval']), (True, False, 2))
        self.assertIn('fresh topic', gate['known'])
        self.assertEqual(gate['recent'][-1], 'F')


    def test_every_check_counts_its_tokens_an_abstain_too(self):
        usage = {'input_tokens': 3, 'output_tokens': 20, 'cache_read_input_tokens': 9000,
                 'cache_creation_input_tokens': 100}
        self.run_hook('add-note', None, json.dumps({'session': 's1', 'abstain': True, 'trigger': 'periodic',
                                                    'usage': usage}))
        env = {**os.environ, 'CLAUDE_PROJECT_DIR': str(self.project)}
        subprocess.run([sys.executable, str(HOOK), 'add-note'], input=json.dumps(
            {'session': 's1', 'claim': 'G', 'evidence': 'g', 'check': 'ls', 'topic': 'g', 'usage': usage}),
            text=True, encoding='utf-8', capture_output=True, timeout=30, env=env)
        self.assertEqual([r['kind'] for r in self.rows()], ['check', 'note'])
        report = self.run_hook('report').stdout
        self.assertIn('2 side checks', report)
        self.assertIn('cache_read_input_tokens 18000', report)
        self.assertIn('output_tokens 40', report)


class RuleTests(unittest.TestCase):
    def test_behaviour_carries_the_verdict_rule_with_its_source(self):
        text = (HOOK.parents[5] / 'core/BEHAVIOUR.md').read_text(encoding='utf-8')
        self.assertIn('is an unverified claim: run its\n  check first', text)
        self.assertIn('docs/research/side-agent-suggestions.md', text)


if __name__ == '__main__':
    unittest.main()
