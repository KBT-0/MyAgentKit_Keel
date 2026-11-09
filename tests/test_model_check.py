"""model_check.py tells the lead when a sub-agent was answered by another model than the one asked (#342).

The field case: `model: fable` on an account without Fable credits ran on claude-opus-5-5 with no error.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
HOOK = KIT / 'overlays/claude-code/files/.claude/hooks/model_check.py'


class ModelCheckTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'project/scripts').mkdir(parents=True)
        (self.root / 'project/scripts/agent_cost.py').symlink_to(KIT / 'core/scripts/agent_cost.py')
        (self.root / 'project/scripts/token_audit.py').symlink_to(KIT / 'core/scripts/token_audit.py')
        self.lead = self.root / 'projects/sess.jsonl'
        self.agent = self.root / 'projects/sess/subagents/agent-a1.jsonl'
        self.agent.parent.mkdir(parents=True)
        self.lead.write_text('', encoding='utf-8')

    def subagent(self, answers, asked=None, prompt='Review the design.'):
        rows = [{'type': 'user', 'message': {'role': 'user', 'content': prompt}}]
        rows += [{'type': 'assistant', 'requestId': 'r%d' % i, 'timestamp': '2026-11-09T10:00:0%dZ' % i,
                  'message': {'model': model, 'usage': {'output_tokens': 1}}} for i, model in enumerate(answers)]
        self.agent.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        if asked:
            self.agent.with_suffix('.meta.json').write_text(
                json.dumps({'model': asked, 'description': 'design consult'}), encoding='utf-8')

    def hook(self, event, **extra):
        payload = dict({'hook_event_name': event, 'transcript_path': str(self.lead)}, **extra)
        if event == 'SubagentStop':
            payload.update(agent_id='a1', agent_type='general-purpose', agent_transcript_path=str(self.agent))
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload).encode(), capture_output=True,
                                env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root / 'project')), timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b'')
        return json.loads(result.stdout) if result.stdout.strip() else None

    def test_a_fable_call_answered_by_opus_reaches_the_owner_and_then_the_lead_once(self):
        self.subagent(['claude-opus-5-5', '<synthetic>', 'claude-opus-5-5'], asked='fable')
        shown = self.hook('SubagentStop')
        self.assertIn('MODEL_FALLBACK: asked fable, answered by claude-opus-5-5 (2 of 2 requests)', shown['systemMessage'])
        self.assertIsNone(self.hook('PostToolUse', agent_id='a2', tool_name='Read'))  # a sub-agent's tool call
        told = self.hook('PostToolUse', tool_name='Read')['hookSpecificOutput']
        self.assertEqual(told['hookEventName'], 'PostToolUse')
        self.assertIn("'design consult'", told['additionalContext'])
        self.assertIsNone(self.hook('Stop'))  # taken once

    def test_a_matching_answer_and_a_call_that_asks_no_family_are_silent(self):
        self.subagent(['claude-fable-5-1'], asked='fable')
        self.assertIsNone(self.hook('SubagentStop'))
        self.subagent(['claude-opus-5-5'], asked='inherit')
        self.assertIsNone(self.hook('SubagentStop'))
        self.assertIsNone(self.hook('Stop'))

    def test_a_fable_consult_line_asks_fable_without_a_meta_file(self):
        self.subagent(['claude-sonnet-5-5'], prompt='Fable consult: read-only design question\nRead x.')
        self.assertIn('asked fable, answered by claude-sonnet-5-5', self.hook('SubagentStop')['systemMessage'])
        self.assertIn('MODEL_FALLBACK', self.hook('Stop')['hookSpecificOutput']['additionalContext'])


if __name__ == '__main__':
    unittest.main()
