"""agent_cost.py must dedupe streamed records, attribute gap re-writes and count poll turns."""
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock
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
            self.assertIn('after >TTL gaps 1.1k (50%)', text)
            self.assertIn('poll-only requests 2', text)
            # hit = read / (read + write + uncached): lead 1000/3125, worker 3/11, total 1003/3136
            self.assertEqual(agent_cost.hit(lead_summary), '32%')
            self.assertEqual(agent_cost.hit(worker), '27%')
            self.assertIn('cache hit 32% (alarm below 80%; owner\'s choice)', text)
            self.assertEqual(agent_cost.hit({'cr': 0, 'cw': 0, 'inp': 0}), '-')

    def test_gap_writes_follow_each_recorded_ttl_and_legacy_fallback(self):
        # KARARLAR B03 inv2/(h): mixed TTLs must not turn every >5m write into a miss.
        cases = [(300, 100, 0, 0, 0), (301, 100, 0, 0, 100),
                 (600, 100, 100, 0, 0), (3600, 100, 100, 0, 0),
                 (3601, 100, 100, 0, 100), (600, 120, 100, 20, 20),
                 (600, 100, 0, 100, 100)]
        from datetime import datetime, timedelta, timezone
        start = datetime(2026, 10, 3, tzinfo=timezone.utc)
        for gap, written, hour, five, expected in cases:
            with self.subTest(gap=gap, hour=hour, five=five):
                with tempfile.TemporaryDirectory() as tmp:
                    session = Path(tmp) / 'ttl.jsonl'
                    session.write_text('\n'.join([
                        rec(start.isoformat(), 'a', {'input_tokens': 1}),
                        rec((start + timedelta(seconds=gap)).isoformat(), 'b', {
                            'cache_creation_input_tokens': written,
                            'cache_creation': {'ephemeral_1h_input_tokens': hour,
                                               'ephemeral_5m_input_tokens': five}})]), encoding='utf-8')
                    result = agent_cost.summarize('worker', agent_cost.requests(session))
                    self.assertEqual(result['cw_gap'], expected)
                    self.assertIn('cWrite>TTL', agent_cost.table([result]))

    def test_one_hour_writes_without_a_long_gap_are_reported_unused(self):
        # #116: a sub-agent that never waits five minutes pays the 2x write for nothing.
        from datetime import datetime, timedelta, timezone
        start = datetime(2026, 10, 3, tzinfo=timezone.utc)
        for gap, unused in ((299, 700), (301, 0)):
            with self.subTest(gap=gap), tempfile.TemporaryDirectory() as tmp:
                session = Path(tmp) / 's.jsonl'
                session.write_text('\n'.join(
                    rec((start + timedelta(seconds=gap * i)).isoformat(), str(i), {
                        'cache_creation_input_tokens': 350, 'cache_creation': {'ephemeral_1h_input_tokens': 350}})
                    for i in range(2)), encoding='utf-8')
                result = agent_cost.summarize('explore', agent_cost.requests(session))
                self.assertEqual(result['w1h_unused'], unused)
                self.assertIn('1h unused %s' % agent_cost.fmt(unused), agent_cost.table([result]))

    def test_latest_finds_a_project_whose_path_has_an_underscore(self):
        # Claude Code encodes every non-alphanumeric character as '-'; --latest once encoded
        # only '/', and found nothing for a project folder named like project_leeway.
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'my_project.v2'
            project.mkdir()
            folder = Path(tmp) / 'home/.claude/projects' / re.sub(r'[^A-Za-z0-9]', '-', str(project.resolve()))
            folder.mkdir(parents=True)
            (folder / 'abc.jsonl').write_text('')
            self.assertNotIn('_', folder.name)
            with mock.patch.object(Path, 'home', return_value=Path(tmp) / 'home'):
                self.assertEqual(agent_cost.latest_session(project), folder / 'abc.jsonl')

    def test_poll_detection_is_about_waiting_not_about_running_a_job(self):
        self.assertTrue(agent_cost.is_poll('Bash', {'command': 'while true; do sleep 20; done'}))
        self.assertTrue(agent_cost.is_poll('Bash', {'command': 'pgrep -x blender'}))
        self.assertTrue(agent_cost.is_poll('BashOutput', {}))
        self.assertFalse(agent_cost.is_poll('Bash', {'command': 'python3 generate.py --stage city'}))
        self.assertFalse(agent_cost.is_poll('Read', {'file_path': 'docs/STATE.md'}))

    def test_a_unicode_worker_description_prints_on_a_legacy_stdout(self):
        # A Windows pipe is cp1252 unless UTF-8 mode is on: `İstanbul worker` raised there.
        import os, subprocess, sys
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / 'abc.jsonl'
            session.write_text(rec('2026-10-03T10:00:00Z', 'r1', {'input_tokens': 1, 'output_tokens': 1}) + '\n')
            sub = Path(tmp) / 'abc' / 'subagents'
            sub.mkdir(parents=True)
            (sub / 'agent-1.jsonl').write_text(rec('2026-10-03T10:01:00Z', 's1', {'input_tokens': 1}) + '\n')
            (sub / 'agent-1.meta.json').write_text(json.dumps({'description': 'İstanbul worker'}), encoding='utf-8')
            env = {k: v for k, v in os.environ.items() if k != 'PYTHONUTF8'}
            env['PYTHONIOENCODING'] = 'cp1252'
            run = subprocess.run([sys.executable, agent_cost.__file__, str(session)],
                                 capture_output=True, env=env, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr.decode('utf-8', 'replace'))
            self.assertIn('İstanbul worker', run.stdout.decode('utf-8'))
