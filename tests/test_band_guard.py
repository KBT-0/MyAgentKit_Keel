"""band_guard.py holds a session past its context band to the closing actions (PLAN.md item 2, owner 2026-11-09).

A worker stops at yellow (150k), a lead at red (200k); MYAGENTKIT_BAND moves the lines.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
HOOK = KIT / 'overlays/claude-code/files/.claude/hooks/band_guard.py'


class BandGuardTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.transcript = self.root / 'sess.jsonl'
        self.context(160_000)

    def context(self, tokens):
        self.transcript.write_text(json.dumps({'type': 'assistant', 'message': {'model': 'claude-opus-5-5', 'usage': {
            'input_tokens': 10, 'cache_read_input_tokens': tokens - 10, 'cache_creation_input_tokens': 0}}}) + '\n',
            encoding='utf-8')

    def hook(self, tool, tool_input, role='worker', band=None, **extra):
        env = {k: v for k, v in os.environ.items() if k not in ('MYAGENTKIT_ROLE', 'MYAGENTKIT_BAND', 'MYAGENTKIT_SESSION_ID')}
        env.update(CLAUDE_PROJECT_DIR=str(self.root), **({'MYAGENTKIT_ROLE': role} if role else {}),
                   **({'MYAGENTKIT_BAND': band} if band else {}))
        payload = dict({'hook_event_name': 'PreToolUse', 'transcript_path': str(self.transcript),
                        'tool_name': tool, 'tool_input': tool_input}, **extra)
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload).encode(), capture_output=True,
                                env=env, cwd=self.root, timeout=60)
        self.assertEqual((result.returncode, result.stderr), (0, b''))
        if not result.stdout.strip():
            return None
        out = json.loads(result.stdout)['hookSpecificOutput']
        self.assertEqual((out['hookEventName'], out['permissionDecision']), ('PreToolUse', 'deny'))
        return out['permissionDecisionReason']

    def test_past_the_band_a_source_edit_is_denied_with_the_band_and_size(self):
        reason = self.hook('Edit', {'file_path': str(self.root / 'src/a.py'), 'old_string': 'a', 'new_string': 'b'})
        self.assertIn('160k tokens, past the worker yellow line (150k)', reason)
        self.assertIn('Only commit and hand-off', reason)
        self.assertIsNotNone(self.hook('Bash', {'command': 'python3 -m pytest'}))
        self.assertIsNotNone(self.hook('Bash', {'command': 'echo x > src.py'}))

    def test_the_closing_set_runs_past_the_band(self):
        for command in ('git add -A && git commit -m "v0.16 x: y"', 'git status --short | head',
                        "python3 '/k/scripts/codex_worker.py' --publish RESULT-x.md.tmp RESULT-x.md"):
            with self.subTest(command=command):
                self.assertIsNone(self.hook('Bash', {'command': command}))
        for path in ('RESULT-x.md', 'RESULT-x.md.tmp', 'docs/STATE.md', '.myagentkit/v016/handoff-2026-11-09.md'):
            with self.subTest(path=path):
                self.assertIsNone(self.hook('Write', {'file_path': str(self.root / path), 'content': 'x'}))
        self.assertIsNone(self.hook('Read', {'file_path': str(self.root / 'src/a.py')}))
        self.assertIsNone(self.hook('Edit', {'file_path': 'src/a.py'}, agent_id='a1'))  # a sub-agent's own call

    def test_below_the_band_nothing_is_denied(self):
        self.context(149_000)
        self.assertIsNone(self.hook('Edit', {'file_path': str(self.root / 'src/a.py')}))
        self.assertIsNone(self.hook('Bash', {'command': 'rm -rf build'}))

    def test_the_band_variable_moves_the_line(self):
        self.context(90_000)
        self.assertIsNone(self.hook('Edit', {'file_path': 'src/a.py'}))
        self.assertIn('past the worker yellow line (80k)', self.hook('Edit', {'file_path': 'src/a.py'}, band='80,100,150'))
        self.assertIsNone(self.hook('Edit', {'file_path': 'src/a.py'}, role=None, band='80,100,150'))
        self.assertIsNone(self.hook('Edit', {'file_path': 'src/a.py'}, band='100,80,150'))  # not ascending: the default

    def test_a_worker_stops_at_yellow_a_lead_at_red(self):
        self.assertIsNotNone(self.hook('Edit', {'file_path': 'src/a.py'}))
        self.assertIsNone(self.hook('Edit', {'file_path': 'src/a.py'}, role=None))
        self.context(210_000)
        self.assertIn('past the lead red line (200k)', self.hook('Edit', {'file_path': 'src/a.py'}, role=None))

    def test_a_broken_transcript_blocks_nothing(self):
        self.transcript.unlink()
        self.assertIsNone(self.hook('Edit', {'file_path': 'src/a.py'}))


if __name__ == '__main__':
    unittest.main()
