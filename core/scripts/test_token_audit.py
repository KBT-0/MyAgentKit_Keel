# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""token_audit.py must price requests, carry each item to the next compaction and count the #307 leaks."""
import json
import tempfile
import unittest
from pathlib import Path
import token_audit


def usage(cr, cw, out, w1h=None):
    return {'input_tokens': 0, 'output_tokens': out, 'cache_read_input_tokens': cr, 'cache_creation_input_tokens': cw,
            'cache_creation': {'ephemeral_1h_input_tokens': cw if w1h is None else w1h, 'ephemeral_5m_input_tokens': 0}}


def assistant(rid, use, tools=(), text=''):
    content = [{'type': 'text', 'text': text}] if text else []
    content += [{'type': 'tool_use', 'id': tid, 'name': name, 'input': inp} for tid, name, inp in tools]
    return {'type': 'assistant', 'uuid': 'a' + rid, 'requestId': rid, 'timestamp': '2026-10-24T10:00:00Z',
            'message': {'model': 'claude-opus-5-5', 'usage': use, 'content': content}}


def result(tid, text, uuid):
    return {'type': 'user', 'uuid': uuid, 'message': {'content': [{'type': 'tool_result', 'tool_use_id': tid, 'content': text}]}}


class TokenAuditTests(unittest.TestCase):
    def audit(self, records, name='abc.jsonl'):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_text(''.join(json.dumps(r) + '\n' for r in records))
            return token_audit.audit(path, set())

    def test_prices_requests_and_carries_items_to_the_next_compaction(self):
        big = 'x' * 2400  # 1000 tokens at 2.4 characters per token
        s = self.audit([
            {'type': 'user', 'uuid': 'u0', 'message': {'content': 'fix it'}},
            assistant('r1', usage(0, 10000, 100), [('t1', 'Read', {'file_path': '/p/a.py'})], text='Reading.'),
            result('t1', big, 'u1'),
            assistant('r2', usage(10000, 1100, 50), [('t2', 'Read', {'file_path': '/p/a.py'})]),
            result('t2', big, 'u2'),
            assistant('r3', usage(11100, 1050, 50)),
            {'type': 'system', 'subtype': 'compact_boundary', 'uuid': 'c1'},
            assistant('r4', usage(0, 3000, 10)),
        ])
        self.assertEqual(s['requests'], 4)
        self.assertEqual(s['compactions'], 1)
        # opus 5.5: $4/MTok input, 1h write 2x, read 0.05x, output $20/MTok
        expected = (21100 * 4 * 0.05 + 15150 * 4 * 2 + 210 * 20) / 1e6
        self.assertAlmostEqual(s['cost_usd'], expected, places=9)
        # the first read is re-read by r3 only (r4 is past the compaction); the second by nothing
        first, second = [c for c in s['top'] if c['source'] == 'tool:Read']
        self.assertEqual((first['tokens'], first['requests']), (1000, 2))
        self.assertAlmostEqual(first['usd'], 1000 * 4 * (2 + 1 * 0.05) / 1e6)
        self.assertEqual(second['requests'], 1)
        self.assertEqual(s['reads']['read'], 2)
        self.assertEqual(s['reads']['whole'], 2)
        self.assertEqual(s['reads']['reread'], 1)
        self.assertEqual(s['retries'], 1)
        self.assertEqual(s['narration_chars'], len('Reading.'))
        self.assertEqual(s['kind'], 'lead')

    def test_injections_bash_kinds_and_session_kinds(self):
        s = self.audit([
            {'type': 'user', 'uuid': 'u0', 'message': {'content': "Read '/w/x.brief.md' and follow it. Your result"}},
            {'type': 'attachment', 'uuid': 'h1', 'attachment': {'type': 'hook_additional_context', 'hookName': 'PostToolUse:Bash',
                                                                  'content': ['5 tool calls']},
             'rendered': [{'content': 'y' * 240}]},
            assistant('r1', usage(0, 5000, 10), [('t1', 'Bash', {'command': 'cd /p && sed -n 1,9p a.py'}),
                                                 ('t2', 'Bash', {'command': 'MYAGENTKIT_TEST_TIMEOUT_SCALE=3 python -m unittest x'})]),
            result('t1', 'z' * 24, 'u1'),
            result('t2', 'z' * 48000, 'u2'),
            assistant('r2', usage(5000, 100, 10)),
            assistant('r3', usage(5100, 100, 10)),
            assistant('r4', usage(5200, 100, 10)),
        ])
        self.assertEqual(s['kind'], 'worker')
        self.assertEqual(s['by_source']['inject:PostToolUse:Bash']['tokens'], 100)
        self.assertEqual(s['by_source']['bash:read']['n'], 1)
        self.assertEqual(s['by_source']['bash:test']['tokens'], 20000)
        self.assertEqual(s['reads']['big'], 1)
        self.assertEqual(token_audit.bash_kind('sleep 30; ls'), 'poll')
        self.assertEqual(token_audit.bash_kind('gh issue view 3'), 'gh')
        self.assertEqual(token_audit.bash_kind('sh scripts/spawn_worker.sh w'), 'kit-script')

    def test_flags_a_low_hit_rate_a_hot_read_and_an_always_loaded_edit(self):
        reads = [assistant(f'r{i}', usage(100, 5000, 10), [(f't{i}', 'Read', {'file_path': '/p/docs/STATE.md'})])
                 for i in range(3)]
        # #325: ranged reads before an Edit (leeway's STATE.md x8) are no hot read
        reads += [assistant(f'g{i}', usage(100, 5000, 10),
                            [(f't{i}', 'Read', {'file_path': '/p/docs/PLAN.md', 'offset': 9, 'limit': 8})])
                  for i in range(3, 6)]
        s = self.audit([rec for i, a in enumerate(reads) for rec in (a, result(f't{i}', 'x', f'u{i}'))] + [
            assistant('r8', usage(100, 5000, 10), [('t8', 'Edit', {'file_path': '/p/AGENTS.md'}),
                                                   ('t9', 'Write', {'file_path': '/p/src/AGENTS.py'})]),
        ] + [assistant(f'q{i}', usage(100, 5000, 10)) for i in range(6)])
        self.assertLess(s['hit_rate'], token_audit.HIT_FLOOR)
        self.assertEqual(s['hot_reads'], {'/p/docs/STATE.md': 3})
        self.assertEqual(s['always_edits'], ['/p/AGENTS.md'])
        table = token_audit.summary([s], 10)
        self.assertIn('| abc.jsonl | lead | 2% | STATE.md x3 | AGENTS.md |', table)

    def test_the_skill_listing_table_names_plugins_never_called(self):
        listing = '- ponytail:ponytail-audit: ' + 'a' * 94 + '\n- myagentkit:handoff: ' + 'b' * 70 + '\n- loop: c'
        s = self.audit([
            {'type': 'attachment', 'uuid': 'k1', 'attachment': {'type': 'skill_listing', 'content': listing}},
            assistant('r1', usage(0, 5000, 10), [('t1', 'Skill', {'skill': 'myagentkit:handoff'})]),
            result('t1', 'ok', 'u1'),
        ])
        typed = self.audit([  # r338: a slash command the owner typed is a call
            {'type': 'attachment', 'uuid': 'k1', 'attachment': {'type': 'skill_listing', 'content': listing}},
            {'type': 'user', 'uuid': 'u0', 'message': {'content': '<command-name>/ponytail:ponytail-audit</command-name>'}},
            assistant('r1', usage(0, 5000, 10)),
        ])
        self.assertIn('Never called: myagentkit. A plugin', token_audit.summary([typed], 10))
        table = token_audit.summary([s], 10)
        self.assertIn('| ponytail | 1 | 50 | 0 |', table)
        self.assertIn('| myagentkit | 1 | 38 | 1 |', table)
        self.assertIn('Never called: ponytail. A plugin', table)
        self.assertNotIn('Never called: myagentkit', table)

    def test_a_continued_transcript_does_not_count_its_parent_twice(self):
        parent = [assistant('r1', usage(0, 5000, 10)), assistant('r2', usage(5000, 100, 10))]
        with tempfile.TemporaryDirectory() as tmp:
            for name, records in (('p.jsonl', parent), ('c.jsonl', parent + [assistant('r3', usage(5100, 100, 10))])):
                (Path(tmp) / name).write_text(''.join(json.dumps(r) + '\n' for r in records))
            seen = set()
            p = token_audit.audit(Path(tmp) / 'p.jsonl', seen)
            c = token_audit.audit(Path(tmp) / 'c.jsonl', seen)
        self.assertEqual((p['requests'], c['requests']), (2, 1))


if __name__ == '__main__':
    unittest.main()
