"""guard_risky_review.py refuses a commit of a risky path no diff review has seen (#307).

Two of ten headless kit runs committed a money-rounding fix without the review AGENTS.md
requires; record_review.py (SubagentStart and SubagentStop, diff-reviewer) is the review's trace.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOKS = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/hooks'


class RiskyReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        (self.root / 'scripts').mkdir()
        self.config('src/money/* scripts/check.sh')
        (self.root / 'src/money').mkdir(parents=True)
        (self.root / 'src/money/round.py').write_text('x = 1\n', encoding='utf-8')
        (self.root / 'notes.md').write_text('a\n', encoding='utf-8')
        self.git('add', '-A')
        self.git('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'start')

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True)

    def config(self, value):
        (self.root / 'scripts/gate_config.sh').write_text('risky_paths="%s"\n' % value, encoding='utf-8')

    def hook(self, name, payload):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
        return subprocess.run([sys.executable, str(HOOKS / name)], input=json.dumps(payload).encode(),
                              env=env, capture_output=True, timeout=60)

    def commit(self, command='git add -A && git commit -m "fix rounding"'):
        return self.hook('guard_risky_review.py', {'tool_name': 'Bash', 'tool_input': {'command': command}})

    def event(self, name, agent='diff-reviewer', agent_id='a1'):
        return self.hook('record_review.py', {'hook_event_name': name, 'agent_type': agent, 'agent_id': agent_id})

    def review(self, agent='diff-reviewer'):
        self.event('SubagentStart', agent)
        return self.event('SubagentStop', agent)

    def test_an_unreviewed_risky_change_is_refused_and_a_review_lets_it_pass(self):
        (self.root / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        refused = self.commit()
        self.assertEqual(refused.returncode, 2)
        self.assertIn('src/money/round.py', refused.stderr.decode())
        self.assertEqual(self.review('Explore').returncode, 0)  # another agent records nothing
        self.assertEqual(self.commit().returncode, 2)
        self.assertEqual(self.review().returncode, 0)
        # the author fixes the review's findings: the record still covers the path
        (self.root / 'src/money/round.py').write_text('x = 3\n', encoding='utf-8')
        self.assertEqual(self.commit().returncode, 0, self.commit().stderr)

    def test_a_new_risky_file_after_the_review_is_refused(self):
        (self.root / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        self.review()
        (self.root / 'src/money/tax.py').write_text('t = 1\n', encoding='utf-8')
        self.assertIn('src/money/tax.py', self.commit().stderr.decode())

    def test_a_file_made_while_the_reviewer_runs_is_refused(self):
        (self.root / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        self.event('SubagentStart')
        (self.root / 'src/money/tax.py').write_text('t = 1\n', encoding='utf-8')
        self.event('SubagentStop')
        refused = self.commit()
        self.assertEqual(refused.returncode, 2)
        self.assertIn('src/money/tax.py', refused.stderr.decode())
        self.assertNotIn('round.py', refused.stderr.decode())
        self.event('SubagentStop', agent_id='never-started')  # a stop with no start records nothing
        self.assertEqual(self.commit().returncode, 2)

    def test_a_rename_out_of_the_risky_folder_is_refused(self):
        self.git('mv', 'src/money/round.py', 'legacy.py')
        refused = self.commit()
        self.assertEqual(refused.returncode, 2)
        self.assertIn('src/money/round.py', refused.stderr.decode())

    def test_emptying_the_setting_does_not_free_its_own_commit(self):
        (self.root / 'src/money/round.py').write_text('x = 9\n', encoding='utf-8')
        self.config('')
        self.assertEqual(self.commit('git commit -am x').returncode, 2)

    def test_a_new_head_voids_the_old_record(self):
        (self.root / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        self.review()
        self.git('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qam', 'reviewed')
        (self.root / 'src/money/round.py').write_text('x = 4\n', encoding='utf-8')
        self.assertEqual(self.commit().returncode, 2)

    def test_safe_changes_and_other_commands_pass(self):
        (self.root / 'notes.md').write_text('b\n', encoding='utf-8')
        self.assertEqual(self.commit().returncode, 0)
        (self.root / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        self.assertEqual(self.commit('git status && git diff').returncode, 0)
        self.assertEqual(self.commit('git -c core.hooksPath=x commit -qam fix').returncode, 2)

    def test_an_empty_or_unfilled_setting_turns_it_off(self):
        (self.root / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        for value in ('', '{{RISKY_PATHS}}'):
            with self.subTest(value=value):
                self.config(value)
                self.git('add', 'scripts/gate_config.sh')
                self.git('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'off')
                self.assertEqual(self.commit().returncode, 0)

    def test_the_overlay_wires_both_hooks(self):
        settings = json.loads((HOOKS.parent / 'settings.json').read_text(encoding='utf-8'))['hooks']
        guard = [e for e in settings['PreToolUse'] if 'guard_risky_review' in e['hooks'][0]['command']]
        self.assertEqual([e['matcher'] for e in guard], ['Bash|PowerShell|Monitor'])
        for event in ('SubagentStart', 'SubagentStop'):
            record = [e for e in settings[event] if 'record_review' in e['hooks'][0]['command']]
            self.assertEqual([e['matcher'] for e in record], ['diff-reviewer'], event)


if __name__ == '__main__':
    unittest.main()
