"""context_buckets.py must bucket by the last request's context, count only real refusals, and window compactions."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import context_buckets


def request(rid, ctx, command=None):
    content = [{'type': 'tool_use', 'id': 't' + rid, 'name': 'Bash', 'input': {'command': command}}] if command else []
    return {'type': 'assistant', 'timestamp': '2026-10-20T10:00:00Z', 'requestId': rid, 'message': {
        'model': 'claude-x', 'content': content, 'usage': {
            'input_tokens': 10, 'cache_read_input_tokens': ctx - 10, 'cache_creation_input_tokens': 0}}}


def result(body, error=True):
    return {'type': 'user', 'timestamp': '2026-10-20T10:00:00Z', 'message': {'content': [
        {'type': 'tool_result', 'tool_use_id': 't', 'is_error': error, 'content': body}]}}


def prompt(body, ts='2026-10-20T10:00:00Z'):
    return {'type': 'user', 'timestamp': ts, 'message': {'content': body}}


class ContextBucketsTests(unittest.TestCase):
    def run_on(self, records, *args):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / 's.jsonl'
            session.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                context_buckets.main(list(args) + [str(session)])
            return out.getvalue()

    def row(self, out, name):
        return next(line.split() for line in out.splitlines() if line.startswith(name + ' '))

    def test_buckets_and_real_refusals(self):
        out = self.run_on([
            prompt('old #fix', ts='2026-10-01T00:00:00Z'),  # before --since: dropped
            request('a', 50_000), request('a', 50_000),  # one request streamed twice
            result('PreToolUse hook: BLOCKED: this Agent call names no model'),
            result('a file quoting "this Agent call names no"', error=False),  # a read, not a refusal
            request('b', 250_000, 'git push origin master'),
            result('commit-msg: crediting an AI tool (above) is not allowed'),
            prompt('no, I said this already #fix'),
        ], '--since', '2026-10-10')
        self.assertEqual(self.row(out, '0-100k'), ['0-100k', '1', '1', '(100.0)', '0', '(0.0)', '0', '(0.0)', '0', '(0.0)', '0', '(0.0)'])
        self.assertEqual(self.row(out, '200-300k')[1:], ['1', '0', '(0.0)', '1', '(100.0)', '1', '(100.0)', '1', '(100.0)', '1', '(100.0)'])
        self.assertIn('no compaction', out)

    def test_compaction_windows_stop_at_twenty_requests(self):
        records = [request(str(i), 150_000) for i in range(25)] + [result('this Agent call names no effort')]
        records += [{'type': 'system', 'subtype': 'compact_boundary'}, request('x', 40_000), prompt('#fix')]
        records += [{'type': 'system', 'subtype': 'compact_boundary'}]
        out = self.run_on(records)
        self.assertIn('compaction 1: route 1/0  attrib 0/0  push 0/0  fix 0/1  phrase 0/0  (before/after, 20/1 requests)', out)
        self.assertIn('compaction 2 (second or later):', out)

    def test_final_request_refusals_are_included_in_both_directions(self):
        evs = [('request', 0)] * 20 + [('route', 0), ('fix', 0)]
        self.assertEqual(context_buckets.window(evs, 0, 1)['route'], 1)
        self.assertEqual(context_buckets.window(evs, 21, -1)['route'], 1)
        evs += [('request', 0), ('attrib', 0)]
        self.assertEqual(context_buckets.window(evs, 0, 1)['attrib'], 0)

    def test_five_and_thirty_request_slices_and_phrase_proxy(self):
        records = [{'type': 'system', 'subtype': 'compact_boundary'}]
        for i in range(31):
            records += [request(str(i), 40_000), prompt('No, I said keep it. #fix' if i == 4 else 'continue')]
        records += [prompt('I said this in a tool result')]
        records[-1]['isMeta'] = True
        out = self.run_on(records)
        self.assertIn('window 5:', out)
        self.assertIn('window 30:', out)
        self.assertIn('phrase', out)
        self.assertIn('informational', out)
        self.assertEqual(self.row(out, '0-100k')[-2:], ['1', '(3.2)'])
        self.assertIn('window 5: route 0/0  attrib 0/0  push 0/0  fix 0/1  phrase 0/1  (before/after, 0/5 requests)', out)
        self.assertIn('window 30: route 0/0  attrib 0/0  push 0/0  fix 0/1  phrase 0/1  (before/after, 0/30 requests)', out)

    def test_phrase_proxy_is_separate_and_ignores_metadata_and_tool_results(self):
        meta = prompt('You forgot the rule')
        meta['isMeta'] = True
        summary = prompt('That is wrong')
        summary['isCompactSummary'] = True
        out = self.run_on([request('p', 40_000), prompt('You forgot the rule'),
                           prompt('continue #fix'), meta, summary, result('I said keep it')])
        self.assertEqual(self.row(out, '0-100k')[-4:], ['1', '(100.0)', '1', '(100.0)'])

    def test_a_unicode_transcript_name_prints_on_a_legacy_stdout(self):
        # A Windows pipe is cp1252 unless UTF-8 mode is on: `session-İ.jsonl` raised there.
        import os, subprocess, sys
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / 'session-İ.jsonl'
            records = [request('a', 50_000), {'type': 'system', 'subtype': 'compact_boundary'}]
            session.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
            env = {k: v for k, v in os.environ.items() if k != 'PYTHONUTF8'}
            env['PYTHONIOENCODING'] = 'cp1252'
            run = subprocess.run([sys.executable, context_buckets.__file__, str(session)],
                                 capture_output=True, env=env, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr.decode('utf-8', 'replace'))
            self.assertIn('session-İ compaction 1', run.stdout.decode('utf-8'))

    def test_a_pasted_image_prompt_is_read_and_each_push_is_listed(self):
        # #251: a prompt with an image is a list of blocks; its #fix and phrase count.
        # #202: each push is listed with session, time and command for the owner to judge.
        pasted = prompt([{'type': 'image', 'source': {}}, {'type': 'text', 'text': 'you forgot it #fix'}])
        out = self.run_on([request('a', 250_000, 'git push origin master'), pasted])
        self.assertEqual(self.row(out, '200-300k')[-4:], ['1', '(100.0)', '1', '(100.0)'])
        self.assertIn('push s 2026-10-20T10:00:00Z 200-300k: git push origin master', out)
        self.assertIn('owner-judged', out)

    def test_records_a_continued_session_copies_count_once(self):
        # #253: a continued session's transcript repeats its parent's requests and compaction.
        boundary = {'type': 'system', 'subtype': 'compact_boundary', 'uuid': 'u1'}
        parent = [request('a', 50_000, 'git push'), boundary, request('b', 40_000)]
        child = [boundary, request('b', 40_000), request('c', 30_000)]
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name, records in (('a', parent), ('b', child)):
                paths.append(Path(tmp) / (name + '.jsonl'))
                paths[-1].write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
            report = context_buckets.report(paths, '')
            self.assertEqual(self.row(report, '0-100k')[:4], ['0-100k', '3', '0', '(0.0)'])
            self.assertEqual(self.row(report, '0-100k')[6:8], ['1', '(33.3)'])
            self.assertNotIn('b compaction', report)
            # Round 1: a copied request still sets the context, so a #fix after the resume
            # lands in its real bucket, not in 0-100k.
            for name, records in (('p', [dict(request('r', 250_000), uuid='u9')]),
                                  ('c', [dict(request('r', 250_000), uuid='u9'), dict(prompt('#fix'), uuid='u8')])):
                (Path(tmp) / (name + '.jsonl')).write_text(''.join(json.dumps(r) + '\n' for r in records),
                                                           encoding='utf-8')
            resumed = context_buckets.report([Path(tmp) / 'p.jsonl', Path(tmp) / 'c.jsonl'], '')
            self.assertEqual(self.row(resumed, '200-300k')[:2] + self.row(resumed, '200-300k')[8:10],
                             ['200-300k', '1', '1', '(100.0)'])
            import agent_cost
            seen = set()
            self.assertEqual(len(agent_cost.requests(paths[0], seen)), 2)
            self.assertEqual(len(agent_cost.requests(paths[1], seen)), 1)


if __name__ == '__main__':
    unittest.main()
