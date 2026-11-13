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
        self.tmpdir = self.root / 'tmp'  # the hook's temporary directory; the rest of root is not one
        self.tmpdir.mkdir()
        self.context(160_000)

    def context(self, tokens):
        self.transcript.write_text(json.dumps({'type': 'assistant', 'message': {'model': 'claude-opus-5-5', 'usage': {
            'input_tokens': 10, 'cache_read_input_tokens': tokens - 10, 'cache_creation_input_tokens': 0}}}) + '\n',
            encoding='utf-8')

    def hook(self, tool, tool_input, role='worker', band=None, **extra):
        env = {k: v for k, v in os.environ.items() if k not in ('MYAGENTKIT_ROLE', 'MYAGENTKIT_BAND', 'MYAGENTKIT_SESSION_ID')}
        env.update(CLAUDE_PROJECT_DIR=str(self.root), TMPDIR=str(self.tmpdir), **({'MYAGENTKIT_ROLE': role} if role else {}),
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

    def test_a_command_that_writes_a_file_stays_denied_past_the_band(self):
        # hookb review High: mkdir, touch and tee joined the destructive-git guard's INERT list; they write files.
        for command in ('cat notes.md | tee src/app.py', "tee src/app.py <<'EOF'\nx\nEOF", 'echo x | tee -a docs/PROJECT.md',
                        'mkdir -p src/new && touch src/new/a.py'):
            with self.subTest(command=command):
                self.assertIsNotNone(self.hook('Bash', {'command': command}))

    def test_the_hand_off_autopilot_review_and_commit_message_steps_run_past_the_band(self):
        # Round-1 review of the hardband change: steps the kit's docs prescribe for closing a session.
        for command in ("py -3 'C:/k/scripts/codex_worker.py' --publish RESULT-a.md.tmp RESULT-a.md",
                        'python3 scripts/master_writer.py release', 'scripts/list_workers.sh',
                        'sh scripts/list_workers.sh', 'scripts/watch_workers.sh --once',
                        'python3 scripts/autopilot_report.py', 'python3 scripts/working_mode.py present',
                        'scripts/review.sh', 'sh scripts/review.sh --tier session', 'mktemp', 'msg=$(mktemp)'):
            with self.subTest(command=command):
                self.assertIsNone(self.hook('Bash', {'command': command}))
        for path in ('.myagentkit/autopilot/2026-11-09.md', 'docs/worktree-notes/feat.md', 'tmp/msg.txt'):
            with self.subTest(path=path):
                self.assertIsNone(self.hook('Write', {'file_path': str(self.root / path), 'content': 'x'}))
        self.assertIsNone(self.hook('Agent', {'subagent_type': 'diff-reviewer', 'prompt': 'review'}))

    def test_the_gate_runs_past_the_band_and_a_test_command_does_not(self):
        # RESEARCH_LOG 2026-11-09 stopcut: two runs were denied scripts/check.sh at yellow and never committed.
        for command in ('sh scripts/check.sh', './scripts/check.sh', 'bash scripts/check.sh --fast',
                        'cd /w/proj && sh scripts/check.sh', 'GATE_LOCK_WAIT=5 sh ./scripts/check.sh 2>&1 | tail -20'):
            with self.subTest(command=command):
                self.assertIsNone(self.hook('Bash', {'command': command}))
        for command in ('sh scripts/check.sh && python3 x.py', 'npm test', 'sh check.sh', 'sh tools/check.sh',
                        'sh scripts/check.sh > gate.log'):
            with self.subTest(command=command):
                self.assertIsNotNone(self.hook('Bash', {'command': command}))
        self.assertIn('the gate (scripts/check.sh)', self.hook('Bash', {'command': 'npm test'}))

    def test_claim_a_plain_agent_and_a_wakeup_stay_denied_past_the_band(self):
        for command in ('python3 scripts/master_writer.py claim', 'scripts/watch_workers.sh',
                        'python3 scripts/working_mode.py autopilot', 'python3 -c 1 scripts/review.sh'):
            with self.subTest(command=command):
                self.assertIsNotNone(self.hook('Bash', {'command': command}))
        self.assertIsNotNone(self.hook('Agent', {'subagent_type': 'general-purpose', 'prompt': 'x'}))
        self.assertIsNotNone(self.hook('Agent', {'prompt': 'x'}))
        self.assertIsNotNone(self.hook('ScheduleWakeup', {'delaySeconds': 600}))
        self.assertIsNotNone(self.hook('Monitor', {'command': 'true'}))
        self.assertIsNotNone(self.hook('Write', {'file_path': str(self.root / 'docs/worktree-notes/a.py'), 'content': 'x'}))

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
