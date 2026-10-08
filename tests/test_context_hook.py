"""The context hook must speak once per 50k step past 200k, choose nothing itself, and never block."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'overlays/claude-code/files/.claude/hooks/context_size.py'


def prompt(text='go'):
    return {'type': 'user', 'message': {'role': 'user', 'content': text}}


def tool_result():
    return {'type': 'user', 'message': {'role': 'user', 'content': [{'type': 'tool_result', 'content': 'ok'}]}}


def request(ctx):
    return {'type': 'assistant', 'message': {'model': 'claude-x', 'usage': {
        'input_tokens': 10, 'cache_read_input_tokens': ctx - 1010, 'cache_creation_input_tokens': 1000}}}


class ContextHookTests(unittest.TestCase):
    def run_hook(self, records, raw=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 's.jsonl'
            path.write_text(raw if raw is not None else ''.join(json.dumps(r) + '\n' for r in records))
            result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({'transcript_path': str(path)}),
                                    text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout

    def test_once_per_step_past_the_line(self):
        turns = [prompt(), request(150_000), prompt(), request(190_000), tool_result(), request(210_000)]
        said = self.run_hook(turns + [prompt()])  # the current prompt may already be in the file
        self.assertIn('Context is 210k tokens', said)
        self.assertIn('/compact', said)
        self.assertIn('hand-off', said)
        self.assertEqual(self.run_hook(turns), said)  # or not yet
        turns += [prompt(), request(240_000)]
        self.assertEqual(self.run_hook(turns + [prompt()]), '')  # same step: said already
        turns += [prompt(), request(255_000)]
        self.assertIn('Context is 255k tokens', self.run_hook(turns + [prompt()]))
        turns += [prompt(), request(60_000)]  # after /compact
        self.assertEqual(self.run_hook(turns + [prompt()]), '')

    def test_silent_below_the_line_and_on_a_broken_transcript(self):
        self.assertEqual(self.run_hook([prompt(), request(199_000)]), '')
        self.assertEqual(self.run_hook([], raw='not json\n{"type": "assistant", "message": 5}\n'), '')
        result = subprocess.run([sys.executable, str(HOOK)], input='{}', text=True, capture_output=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))


if __name__ == '__main__':
    unittest.main()
