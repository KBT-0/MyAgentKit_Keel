"""The two communication hooks: bounce a bare label once, nudge after five silent calls, never block a turn."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOKS = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/hooks'


def run(hook, payload):
    return subprocess.run([sys.executable, str(HOOKS / hook)], input=payload, text=True, encoding='utf-8',
                          capture_output=True, timeout=30)


def assistant(*blocks):
    return {'type': 'assistant', 'message': {'content': list(blocks)}}


def tool(name='Read'):
    return {'type': 'tool_use', 'name': name, 'input': {}}


def text(s='Found it.'):
    return {'type': 'text', 'text': s}


class PlainReportTests(unittest.TestCase):
    def stop(self, message, active=False):
        return run('plain_report.py', json.dumps({'last_assistant_message': message, 'stop_hook_active': active}))

    def test_a_bare_label_is_bounced_with_every_label_named_once(self):
        result = self.stop('D-5 review done, r2 clean, r2 archived: Accept-MC. D-5 next.')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('BLOCKED', result.stderr)
        self.assertIn('D-5, r2, Accept-MC', result.stderr)
        self.assertIn('docs/COMMUNICATION.md', result.stderr)

    def test_labels_inside_code_paths_versions_and_hashes_pass(self):
        for message in ('The archive is `docs/reviews/r2-D-5.md`.',
                        'Run:\n```\nREVIEW_LABEL=v011-d5 sh review.sh  # r2\n```\nthen stop.',
                        'master is at a62e282, v0.11, issue #75; the `Accept-MC` verdict is in the file.',
                        'İkinci inceleme turu temiz; kabul, iki küçük not ile.',
                        ''):
            with self.subTest(message=message):
                result = self.stop(message)
                self.assertEqual((result.returncode, result.stderr), (0, ''), message)

    def test_a_continued_turn_is_not_bounced_again(self):
        result = self.stop('D-5 is still here.', active=True)
        self.assertEqual((result.returncode, result.stderr), (0, ''))

    def test_a_broken_input_never_holds_the_turn(self):
        for payload in ('', 'not json', '{"last_assistant_message": 5}'):
            with self.subTest(payload=payload):
                self.assertEqual(run('plain_report.py', payload).returncode, 0)


class ProgressReminderTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.transcript = Path(tmp.name) / 'session.jsonl'

    def nudge(self, records, raw=None):
        self.transcript.write_text(raw if raw is not None else ''.join(json.dumps(r) + '\n' for r in records),
                                   encoding='utf-8')
        result = run('progress_reminder.py', json.dumps({'transcript_path': str(self.transcript)}))
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        if not result.stdout:
            return None
        return json.loads(result.stdout)['hookSpecificOutput']

    def test_the_fifth_silent_call_nudges_once_and_a_visible_line_resets(self):
        calls = [assistant(tool()) for _ in range(4)]
        self.assertIsNone(self.nudge(calls))
        said = self.nudge(calls + [assistant(tool())])
        self.assertEqual(said['hookEventName'], 'PostToolUse')
        self.assertIn('5 tool calls', said['additionalContext'])
        self.assertIn('docs/COMMUNICATION.md', said['additionalContext'])
        calls += [assistant(tool()), assistant(tool())]  # 6 and 7: already said
        self.assertIsNone(self.nudge(calls))
        calls += [assistant(text(), tool())]  # a visible line: the count restarts
        self.assertIsNone(self.nudge(calls + [assistant(tool()) for _ in range(3)]))
        self.assertIn('5 tool calls', self.nudge(calls + [assistant(tool()) for _ in range(4)])['additionalContext'])

    def test_a_parallel_batch_that_jumps_over_the_threshold_still_nudges_once(self):
        calls = [assistant(tool()) for _ in range(4)] + [assistant(tool(), tool(), tool())]
        self.assertIn('7 tool calls', self.nudge(calls)['additionalContext'])
        self.assertIsNone(self.nudge(calls + [assistant(tool())]))  # 8
        self.assertIn('10 tool calls', self.nudge(calls + [assistant(tool(), tool(), tool())])['additionalContext'])

    def test_thinking_sidechains_and_empty_text_do_not_count_as_visible(self):
        calls = [assistant({'type': 'thinking', 'thinking': 'hm'}, tool()), assistant(text('  '), tool()),
                 {'type': 'assistant', 'isSidechain': True, 'message': {'content': [text('worker talk')]}},
                 assistant(tool()), assistant(tool())]
        self.assertIsNone(self.nudge(calls))
        self.assertIn('5 tool calls', self.nudge(calls + [assistant(tool())])['additionalContext'])

    def test_only_the_tail_of_a_large_transcript_is_read(self):
        padding = json.dumps({'type': 'user', 'message': {'content': 'x' * 10_000}}) + '\n'
        raw = padding * 120 + ''.join(json.dumps(assistant(tool())) + '\n' for _ in range(5))
        self.assertIn('5 tool calls', self.nudge(None, raw=raw)['additionalContext'])
        raw = padding * 120 + json.dumps(assistant(text())) + '\n' + ''.join(json.dumps(assistant(tool())) + '\n' for _ in range(4))
        self.assertIsNone(self.nudge(None, raw=raw))

    def test_a_missing_or_broken_transcript_never_blocks(self):
        result = run('progress_reminder.py', json.dumps({'transcript_path': str(self.transcript / 'missing')}))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        self.assertIsNone(self.nudge(None, raw='{broken\n' * 3))
        self.assertEqual(run('progress_reminder.py', '').returncode, 0)


if __name__ == '__main__':
    unittest.main()
