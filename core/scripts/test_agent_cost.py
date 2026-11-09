# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""agent_cost.py must dedupe streamed records, attribute gap re-writes and count poll turns."""
import io
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
            self.assertIn('cache hit 32%  $ ', text)
            self.assertNotIn('alarm below', text)
            self.assertEqual(agent_cost.hit({'cr': 0, 'cw': 0, 'inp': 0}), '-')

    def test_workflow_agents_are_listed_with_their_run_and_the_journal_is_skipped(self):
        # #172: the Workflow tool writes its agents to subagents/workflows/wf_<run>/.
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / 'abc.jsonl'
            session.write_text('')
            run = Path(tmp) / 'abc' / 'subagents' / 'workflows' / 'wf_42'
            run.mkdir(parents=True)
            (run / 'agent-9.jsonl').write_text('')
            (run / 'agent-9.meta.json').write_text(json.dumps({'description': 'audit'}))
            (run / 'journal.jsonl').write_text('')
            (run.parents[1] / 'agent-1.jsonl').write_text('')
            self.assertEqual([n for n, _ in agent_cost.session_agents(session)], ['LEAD', 'agent-1', 'wf_42 audit'])

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

    def test_output_tokens_are_shown_and_an_untimed_request_does_not_crash(self):
        # #254: output tokens are summed per agent and in TOTAL; #255: one request without a
        # timestamp sorted with a naive minimum beside aware timestamps raised TypeError.
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / 'b.jsonl'
            session.write_text(
                '{"type":"assistant","timestamp":"2026-10-01T10:00:00.000Z","requestId":"r1","message":'
                '{"id":"m1","model":"claude-opus","usage":{"input_tokens":10,"output_tokens":1500}}}\n'
                '{"type":"assistant","requestId":"r2","message":{"id":"m2","model":"claude-opus",'
                '"usage":{"input_tokens":10,"output_tokens":500}}}\n', encoding='utf-8')
            rows = agent_cost.requests(session)
            self.assertEqual([r['t'] is None for r in rows], [True, False])
            text = agent_cost.table([agent_cost.summarize('LEAD', rows)])
            self.assertIn(' out ', text.splitlines()[0])
            self.assertIn('output 2.0k', text)

    def test_compactions_are_counted_per_agent_and_a_copied_one_once(self):
        # #303: two workers handed off at their second compaction near 80k, and the table did
        # not show it; a continued session's transcript copies the parent's boundary (#253).
        boundary = json.dumps({'type': 'system', 'subtype': 'compact_boundary', 'uuid': 'u1',
                               'timestamp': '2026-10-03T10:01:00Z'})
        second = json.dumps({'type': 'system', 'subtype': 'compact_boundary', 'uuid': 'u2'})
        with tempfile.TemporaryDirectory() as tmp:
            twice, never, child = (Path(tmp) / n for n in ('a.jsonl', 'b.jsonl', 'c.jsonl'))
            twice.write_text('\n'.join([rec('2026-10-03T10:00:00Z', 'r1', {'input_tokens': 1}), boundary,
                                        rec('2026-10-03T10:02:00Z', 'r2', {'input_tokens': 1}), second]),
                             encoding='utf-8')
            never.write_text(rec('2026-10-03T10:00:00Z', 'r3', {'input_tokens': 1}), encoding='utf-8')
            child.write_text('\n'.join([boundary, rec('2026-10-03T10:03:00Z', 'r4', {'input_tokens': 1})]),
                             encoding='utf-8')
            seen, counts = set(), []
            for path in (twice, never, child):
                found = []
                rows = agent_cost.requests(path, seen, found)
                counts.append(agent_cost.summarize(path.stem, rows, len(found))['cmp'])
            self.assertEqual(counts, [2, 0, 0])
            table = agent_cost.table([agent_cost.summarize('w', rows, 2)])
            self.assertIn(' cmp ', table.splitlines()[0])
            self.assertRegex(table.splitlines()[1], r'^w\s+1\s+0\s.*\s2\s')

    def test_the_peak_context_is_the_largest_request_not_the_last(self):
        # #303: ctxN is the last request's context, small after a compaction; the issue read
        # it as the maximum. The peak is shown beside it.
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / 's.jsonl'
            session.write_text('\n'.join(
                rec(f'2026-10-03T10:0{i}:00Z', str(i), {'input_tokens': 1, 'cache_read_input_tokens': n})
                for i, n in enumerate((49_000, 79_800, 12_000))), encoding='utf-8')
            result = agent_cost.summarize('w', agent_cost.requests(session))
            self.assertEqual((result['ctx0'], result['ctxMax'], result['ctxN']), (49_001, 79_801, 12_001))
            self.assertIn('49.0k->79.8k->12.0k', agent_cost.table([result]))

    def two_requests(self, path, model='claude-opus-5-5', read=1000, cwd=None, prompt=None):
        """The smallest fixture: a user prompt and two requests (1h write, then a read)."""
        lines = [json.dumps({'type': 'user', 'cwd': cwd or '/p', 'message': {'content': prompt or 'go'}})]
        lines += [rec('2026-10-03T10:00:00Z', 'a' + path.stem, {'input_tokens': 10, 'output_tokens': 100,
                      'cache_creation_input_tokens': 1000, 'cache_creation': {'ephemeral_1h_input_tokens': 1000}}, model=model),
                  rec('2026-10-03T10:01:00Z', 'b' + path.stem, {'input_tokens': 10, 'output_tokens': 100,
                      'cache_read_input_tokens': read}, model=model)]
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def test_dollars_and_the_answering_model_per_row_and_in_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            known, unknown = Path(tmp) / 'k.jsonl', Path(tmp) / 'u.jsonl'
            self.two_requests(known)
            self.two_requests(unknown, model='claude-mystery-1')
            a = agent_cost.summarize('LEAD', agent_cost.requests(known))
            b = agent_cost.summarize('w', agent_cost.requests(unknown))
            # opus: 20 uncached x $4, 200 out x $20, 1000 read x $4 x 0.05, 1000 1h write x $4 x 2 per MTok
            expected = (20 * 4 + 200 * 20 + 1000 * 4 * 0.05 + 1000 * 4 * 2) / 1e6
            self.assertAlmostEqual(agent_cost.usd(a), expected)
            self.assertIsNone(agent_cost.usd(b))
            text = agent_cost.table([a, b])
            self.assertTrue(text.splitlines()[0].endswith(' model       $'))
            self.assertRegex(text, r'\nLEAD .*\s+opus\s+0\.01\n')
            self.assertRegex(text, r'\nw .*\s+\?\s+\?\n')
            self.assertIn('$ 0.01 ($0.006/request)  max context 1.0k', text)
            self.assertIn('note: no price for model claude-mystery-1', text.splitlines()[-1])

    def test_the_alarm_is_a_context_past_150k_or_spend_past_the_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 's.jsonl'
            self.two_requests(path, read=151_000)
            s = agent_cost.summarize('LEAD', agent_cost.requests(path))
            with mock.patch.dict('os.environ', {'MYAGENTKIT_SPEND_ALARM_USD': '100'}):
                self.assertIn('ALARM: context past 150.0k (LEAD)', agent_cost.table([s]))
            with mock.patch.dict('os.environ', {'MYAGENTKIT_SPEND_ALARM_USD': '0.001'}):
                self.assertIn('; $ past 0.001', agent_cost.table([s]))
            self.two_requests(path)
            small = agent_cost.summarize('LEAD', agent_cost.requests(path))
            with mock.patch.dict('os.environ', {'MYAGENTKIT_SPEND_ALARM_USD': 'not a number'}):
                self.assertNotIn('ALARM', agent_cost.table([small]))

    def test_by_task_joins_a_workers_numbered_and_fix_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            for stem, cwd, prompt in (('a', '/r/.claude/worktrees/vis', None), ('b', '/r/.claude/worktrees/vis-2', None),
                                      ('c', '/r', "Read '/r/.myagentkit/workers/vis-fix2.brief.md' and follow it."),
                                      ('d', '/r', None)):
                self.two_requests(Path(tmp) / (stem + '.jsonl'), cwd=cwd, prompt=prompt)
            out = io.StringIO()
            with mock.patch('sys.stdout', out):
                self.assertEqual(agent_cost.main(['--by-task', tmp]), 0)
            lines = out.getvalue().splitlines()
            self.assertRegex(lines[1], r'^vis\s+3\s+0\.04\s+1\.0k  opus$')
            self.assertRegex(lines[2], r'^lead\s+1\s')
            self.assertEqual(lines[3], 'TOTAL tasks 2  sessions 4  $ 0.05')

    def test_quota_deltas_per_label_a_switch_and_a_missing_end(self):
        def line(label, phase, org, five, seven):
            return json.dumps({'ts': 't', 'label': label, 'phase': phase, 'org_uuid': org, 'org_name': org.upper(),
                               'five_hour': five and {'used_percentage': five, 'resets_at': 1},
                               'seven_day': {'used_percentage': seven, 'resets_at': 9}})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'quota.jsonl'
            path.write_text('\n'.join([line('vis', 'start', 'a', None, 8), line('sw', 'start', 'a', 10, 8),
                                        line('vis', 'end', 'a', 12, 9), line('sw', 'end', 'b', 1, 1),
                                        line('gone', 'start', 'a', 3, 3)]) + '\n', encoding='utf-8')
            self.assertEqual([l.split() for l in agent_cost.quota(path).splitlines()[1:]],
                             [['vis', '+12%', '+1%', 'A'], ['sw', 'switched', 'A\u2192B'],
                              ['gone', 'n/a', '(no', 'end', 'line)'], ['TOTAL', 'A:', '5h', '+12%', '7d', '+1%']])

    def test_quota_snapshot_appends_one_line_and_never_fails(self):
        import os, subprocess, sys
        script = Path(agent_cost.__file__).with_name('quota_snapshot.py')
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / 'cfg'
            cfg.mkdir()
            (cfg / 'rate-limits.json').write_text(json.dumps({'seven_day': {'used_percentage': 8, 'resets_at': 5}}))
            (cfg / '.claude.json').write_text(json.dumps({'oauthAccount': {'organizationUuid': 'o1', 'organizationName': 'Org'}}))
            env = dict(os.environ, CLAUDE_CONFIG_DIR=str(cfg))
            usage = Path(tmp) / 'usage'
            run = lambda *a, stdin='': subprocess.run([sys.executable, str(script), *a, '--dir', str(usage)],  # noqa: E731
                                                      input=stdin, capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(run('vis', 'start').returncode, 0)
            self.assertEqual(run('-', 'end', stdin='{"session_id": "s1"}').returncode, 0)
            rows = [json.loads(l) for l in (usage / 'quota.jsonl').read_text().splitlines()]
            self.assertEqual([(r['label'], r['phase'], r['org_uuid'], r['org_name'], r['five_hour'], r['seven_day'])
                              for r in rows], [('vis', 'start', 'o1', 'Org', None, {'used_percentage': 8, 'resets_at': 5}),
                                               ('s1', 'end', 'o1', 'Org', None, {'used_percentage': 8, 'resets_at': 5})])
            bad = run('vis', 'middle')
            self.assertEqual((bad.returncode, len(bad.stderr.splitlines())), (0, 1))
            (cfg / 'rate-limits.json').write_text('{broken')
            self.assertEqual(run('vis', 'end').returncode, 0)
            self.assertIsNone(json.loads((usage / 'quota.jsonl').read_text().splitlines()[-1])['seven_day'])


if __name__ == '__main__':
    unittest.main()
