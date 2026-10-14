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
        self.assertEqual(self.row(out, '0-100k'), ['0-100k', '1', '1', '(100.0)', '0', '(0.0)', '0', '(0.0)', '0', '(0.0)'])
        self.assertEqual(self.row(out, '200-300k')[1:], ['1', '0', '(0.0)', '1', '(100.0)', '1', '(100.0)', '1', '(100.0)'])
        self.assertIn('no compaction', out)

    def test_compaction_windows_stop_at_twenty_requests(self):
        records = [request(str(i), 150_000) for i in range(25)] + [result('this Agent call names no effort')]
        records += [{'type': 'system', 'subtype': 'compact_boundary'}, request('x', 40_000), prompt('#fix')]
        records += [{'type': 'system', 'subtype': 'compact_boundary'}]
        out = self.run_on(records)
        self.assertIn('compaction 1: route 1/0  attrib 0/0  push 0/0  fix 0/1  (before/after, 20/1 requests)', out)
        self.assertIn('compaction 2 (second or later):', out)


if __name__ == '__main__':
    unittest.main()
