"""The context hook must speak once per 50k step past 200k, choose nothing itself, and never block."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'overlays/claude-code/files'
HOOK = OVERLAY / '.claude/hooks/context_size.py'


def prompt(text='go'):
    return {'type': 'user', 'message': {'role': 'user', 'content': text}}


def request(ctx, read=None):
    return {'type': 'assistant', 'message': {'model': 'claude-x', 'usage': {
        'input_tokens': 10, 'cache_read_input_tokens': ctx - 1010 if read is None else read,
        'cache_creation_input_tokens': 1000}}}


class ContextHookTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.transcript = self.tmp / 'session-1.jsonl'
        self.env = dict(os.environ)

    def run_hook(self, records, raw=None, command=None, env=None):
        self.transcript.write_text(raw if raw is not None else ''.join(json.dumps(r) + '\n' for r in records))
        result = subprocess.run(command or [sys.executable, str(HOOK)],
                                input=json.dumps({'transcript_path': str(self.transcript)}),
                                text=True, capture_output=True, timeout=30, env=env or self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout

    def test_once_per_step_past_the_line(self):
        turns = [prompt(), request(150_000), prompt(), request(190_000), prompt(), request(210_000)]
        said = self.run_hook(turns + [prompt()])
        self.assertIn('Context is 210k tokens', said)
        self.assertIn('/compact', said)
        self.assertIn('hand-off', said)
        self.assertIn("closing summary", said)  # when AGENTS.md's MENTION ONCE list says
        self.assertEqual(self.run_hook(turns + [prompt(), prompt()]), '')  # a retry with no request
        turns += [prompt(), request(240_000)]
        self.assertEqual(self.run_hook(turns + [prompt()]), '')  # same step: said already
        turns += [prompt(), request(255_000)]
        self.assertIn('Context is 255k tokens', self.run_hook(turns + [prompt()]))
        # /compact: the boundary comes before any new request, and the old size is gone.
        turns += [prompt('/compact'), {'type': 'system', 'subtype': 'compact_boundary'},
                  {'type': 'user', 'isCompactSummary': True, 'message': {'content': 'summary'}}]
        self.assertEqual(self.run_hook(turns + [prompt()]), '')
        turns += [request(60_000), prompt(), request(205_000)]
        self.assertIn('Context is 205k tokens', self.run_hook(turns + [prompt()]))  # armed again

    def test_a_null_counter_is_zero(self):
        self.assertIn('Context is 210k tokens', self.run_hook([prompt(), {'type': 'assistant', 'message': {
            'model': 'claude-x', 'usage': {'input_tokens': 210_000, 'cache_read_input_tokens': None,
                                           'cache_creation_input_tokens': None}}}]))

    def test_silent_below_the_line_and_on_a_broken_transcript(self):
        self.assertEqual(self.run_hook([prompt(), request(199_000)]), '')
        self.assertEqual(self.run_hook([], raw='not json\n5\n{"type": "assistant", "message": 5}\n'), '')
        result = subprocess.run([sys.executable, str(HOOK)], input='{}', text=True, capture_output=True,
                                timeout=30, env=self.env)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

    def test_same_named_transcripts_keep_their_own_step(self):
        # Projects' transcripts share file names; the step one named must not silence another.
        other = self.tmp / 'other'
        other.mkdir()
        turns = [prompt(), request(210_000)]
        self.assertIn('Context is 210k tokens', self.run_hook(turns))
        self.transcript = other / self.transcript.name
        self.assertIn('Context is 210k tokens', self.run_hook(turns))


if __name__ == '__main__':
    unittest.main()
