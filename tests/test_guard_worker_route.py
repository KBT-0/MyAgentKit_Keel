"""guard_worker_route.py routes a sub-agent that would wait on a long job to spawn_worker.sh.

A sub-agent runs on the five-minute cache, so a wait past five minutes re-writes its whole
context: $100 of Keel's re-writes in 14 days, all background Agent calls such as "Fix round-3
review gate findings" and "Merge three branches" (#307 baseline, docs/WORKFLOW.md "Worker cost"
rule 1). The model and effort checks live in test_overlay_permissions.py.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/hooks/guard_worker_route.py'


def run(tool_input, tool='Agent'):
    payload = json.dumps({'tool_name': tool, 'tool_input': tool_input})
    return subprocess.run([sys.executable, str(HOOK)], input=payload.encode(), capture_output=True, timeout=60)


class LongWaitRouteTests(unittest.TestCase):
    def test_a_sub_agent_that_names_a_long_job_is_refused(self):
        for tool, call in [
            ('Agent', {'description': 'Fix round-3 review gate findings', 'prompt': 'Fix them and commit.'}),
            ('Agent', {'description': 'v012 ci worker', 'prompt': 'Make the CI green.'}),
            ('Task', {'description': 'Merge three branches', 'prompt': 'Merge a, b and c into master.'}),
            ('Agent', {'description': 'x', 'prompt': 'Run gh run watch 123 and report.'}),
            ('Agent', {'description': 'x', 'prompt': 'Run scripts/check.sh, then report.'}),
            ('Agent', {'subagent_type': 'fork', 'description': 'x', 'prompt': 'Wait for the review.sh round.'}),
        ]:
            with self.subTest(call=call):
                result = run(dict(call, model='claude-opus-5-5', effort='high'), tool)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(b'spawn_worker.sh', result.stderr)
                self.assertIn(b'No long wait:', result.stderr)

    def test_a_short_errand_or_one_that_says_it_will_not_wait_passes(self):
        for call in [
            {'description': 'Find the callers', 'prompt': 'List every caller of frontmatter().'},
            {'description': 'Gate review', 'prompt': 'Read the diff.\nNo long wait: reads one diff, runs nothing.'},
            {'description': 'Integration test', 'prompt': 'Count the cicd folders in navigation.'},
            # An inner diff-reviewer's prompt cites the review protocol by its file name.
            {'subagent_type': 'diff-reviewer', 'description': 'Inner review round 1',
             'prompt': 'Review the diff against docs/REVIEW_GATE.md, "What a reviewer attacks first".'},
        ]:
            with self.subTest(call=call):
                result = run(dict(call, model='claude-opus-5-5', effort='high'))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_other_tools_pass(self):
        self.assertEqual(run({'command': 'gh run watch 1'}, 'Bash').returncode, 0)


if __name__ == '__main__':
    unittest.main()
