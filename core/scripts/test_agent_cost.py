"""agent_cost.py must dedupe streamed records, attribute gap re-writes and count poll turns."""
import json
from pathlib import Path
import tempfile
import unittest
import agent_cost


def rec(ts, rid, usage, tools=(), model='claude-x'):
    content = [{'type': 'tool_use', 'id': 't' + n, 'name': n, 'input': i} for n, i in tools]
    return json.dumps({'type': 'assistant', 'timestamp': ts, 'requestId': rid,
                       'message': {'id': 'm' + rid, 'model': model, 'usage': usage, 'content': content}})


class AgentCostTests(unittest.TestCase):
    def test_table_from_a_synthetic_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / 'abc.jsonl'
            lead = [
                # one request streamed as two records: counted once, usage from the final record
                rec('2026-10-03T10:00:00Z', 'r1', {'input_tokens': 10, 'output_tokens': 1,
                    'cache_creation_input_tokens': 1000, 'cache_read_input_tokens': 0,
                    'cache_creation': {'ephemeral_5m_input_tokens': 0, 'ephemeral_1h_input_tokens': 1000}}),
                rec('2026-10-03T10:00:01Z', 'r1', {'input_tokens': 10, 'output_tokens': 5,
                    'cache_creation_input_tokens': 1000, 'cache_read_input_tokens': 0,
                    'cache_creation': {'ephemeral_5m_input_tokens': 0, 'ephemeral_1h_input_tokens': 1000}},
                    tools=[('Bash', {'command': 'sleep 30'})]),
                # within five minutes: incremental, and a real tool call
                rec('2026-10-03T10:02:00Z', 'r2', {'input_tokens': 5, 'output_tokens': 2,
                    'cache_creation_input_tokens': 50, 'cache_read_input_tokens': 1000},
                    tools=[('Read', {'file_path': 'x'})]),
                # after a ten-minute gap: a full re-write
                rec('2026-10-03T10:12:30Z', 'r3', {'input_tokens': 5, 'output_tokens': 2,
                    'cache_creation_input_tokens': 1055, 'cache_read_input_tokens': 0}),
                json.dumps({'type': 'user', 'message': {'content': 'ignored'}}),
                json.dumps({'type': 'assistant', 'message': {'model': '<synthetic>', 'usage': {}}}),
            ]
            session.write_text('\n'.join(lead) + '\n')
            sub = Path(tmp) / 'abc' / 'subagents'
            sub.mkdir(parents=True)
            (sub / 'agent-1.jsonl').write_text(rec('2026-10-03T10:03:00Z', 's1', {
                'input_tokens': 1, 'output_tokens': 1, 'cache_creation_input_tokens': 7,
                'cache_read_input_tokens': 3, 'cache_creation': {'ephemeral_5m_input_tokens': 7}},
                tools=[('TaskOutput', {})]) + '\n')
            (sub / 'agent-1.meta.json').write_text(json.dumps({'description': 'probe worker'}))

            agents = agent_cost.session_agents(session)
            self.assertEqual([n for n, _ in agents], ['LEAD', 'probe worker'])
            lead_summary = agent_cost.summarize('LEAD', agent_cost.requests(session))
            self.assertEqual(lead_summary['req'], 3)
            self.assertEqual(lead_summary['tool'], 2)
            self.assertEqual(lead_summary['cw'], 2105)
            self.assertEqual(lead_summary['cw_gap'], 1055)
            self.assertEqual(lead_summary['poll'], 1)
            self.assertEqual((lead_summary['w1h'], lead_summary['w5']), (1000, 0))
            self.assertEqual((lead_summary['ctx0'], lead_summary['ctxN']), (1010, 1060))
            worker = agent_cost.summarize('w', agent_cost.requests(agents[1][1]))
            self.assertEqual((worker['poll'], worker['w5'], worker['cw_gap']), (1, 7, 0))

            text = agent_cost.table([lead_summary, worker])
            self.assertIn('TOTAL requests 4', text)
            self.assertIn('after >5 min gaps 1.1k (50%)', text)
            self.assertIn('poll-only requests 2', text)

    def test_poll_detection_is_about_waiting_not_about_running_a_job(self):
        self.assertTrue(agent_cost.is_poll('Bash', {'command': 'while true; do sleep 20; done'}))
        self.assertTrue(agent_cost.is_poll('Bash', {'command': 'pgrep -x blender'}))
        self.assertTrue(agent_cost.is_poll('BashOutput', {}))
        self.assertFalse(agent_cost.is_poll('Bash', {'command': 'python3 generate.py --stage city'}))
        self.assertFalse(agent_cost.is_poll('Read', {'file_path': 'docs/STATE.md'}))
