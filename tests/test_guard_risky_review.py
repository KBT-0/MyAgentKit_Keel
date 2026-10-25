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

    def event(self, name, agent='diff-reviewer', agent_id='a1', last='Verdict: Accept\n\nNo findings.'):
        return self.hook('record_review.py', {'hook_event_name': name, 'agent_type': agent, 'agent_id': agent_id,
                                              'last_assistant_message': last})

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

    def test_a_review_with_no_verdict_records_nothing(self):
        (self.root / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        for last in ('API Error: overloaded', 'placeholder', '', 'Verdict: Reject\n- High: x',
                     'Verdict: Reject\n\n- High: x\n\nAccept once the High is fixed.',
                     'Verdict: Accept\n\n- High: src/money/round.py:1 rounds down. REPRODUCED',
                     'Verdict: Accept\n\n1. High, REPRODUCED. x', 'Accept\nSeverity: Critical - x',
                     'Verdict: PASS\n- High: x', 'Verdict: Accept\nIssue #1 — High: x', 'Verdict: Accept\nFinding 1: High - x',
                     'Verdict: Accept\n- `a.py:3` — High: x', 'Verdict: Accept\n- H1 (High) x',
                     'Verdict: Accept\n| 1 | High | a.py:3 | x |', 'Verdict: Accept\n_High_ x',
                     'Verdict: Accept\n- High-severity: a.py:3 x', 'Verdict: Accept\n- Critical-path bug: a.py:3 x',
                     'Verdict: Accept\n- High: none of the callers check it, a.py:3', 'Pass 1: reading the diff'):
            with self.subTest(last=last):
                self.event('SubagentStart')
                self.event('SubagentStop', last=last)
                self.assertEqual(self.commit().returncode, 2)
        for last in ('VERDICT: APPROVE', '**Accept with Manual Checks**', '## Verdict\nAccept with Manual Checks\n- Medium: x',
                     'Verdict: PASS', 'VERDICT: PASS (no blocking findings, two Lows)', '## Verdict\nPASS',  # ctl10 run 2
                     'Verdict: Accept\n1. High-tier focus not run', 'Verdict: Accept\nNo Critical or High finding',
                     'Verdict: Accept\n' + 'finding 1 ' * 40 + 'x'):  # an ambiguous label split took 2**40 steps
            with self.subTest(last=last):
                self.event('SubagentStart', agent_id=last)
                self.event('SubagentStop', agent_id=last, last=last)
        self.assertEqual(self.commit().returncode, 0)

    def test_a_handed_back_report_is_read_from_the_tool(self):
        # auto mode: the report goes through SubagentHandback; the stop's last message is not the report
        (self.root / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        handback = {'hook_event_name': 'PostToolUse', 'agent_type': 'diff-reviewer', 'tool_name': 'SubagentHandback'}
        for agent_id, message in (('r1', 'Verdict: Reject\n- High: x'), ('r2', 'Verdict: Accept\n- High: x')):
            self.event('SubagentStart', agent_id=agent_id)
            self.hook('record_review.py', dict(handback, agent_id=agent_id, tool_input={'message': message}))
            self.event('SubagentStop', agent_id=agent_id, last='')
            self.assertEqual(self.commit().returncode, 2, message)
        self.event('SubagentStart', agent_id='r3')
        self.hook('record_review.py', dict(handback, agent_id='r3',
                                           tool_input={'message': 'Verdict: Accept with Manual Checks. No Critical or High.'}))
        self.event('SubagentStop', agent_id='r3', last='')  # the stop after it keeps the record
        self.assertEqual(self.commit().returncode, 0, self.commit().stderr)

    def test_a_completed_review_sh_review_counts(self):
        # review_dispatch.py writes the same record after a completed --uncommitted review
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core/scripts'))
        import review_dispatch
        (self.root / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        self.event('SubagentStart', agent_id='open')  # a diff-reviewer still running keeps its note
        review_dispatch.note_reviewed(self.root)
        self.assertEqual(self.commit().returncode, 0)
        self.event('SubagentStop', agent_id='open')
        self.assertEqual(self.commit().returncode, 0)
        accept, reject = {'result': {'verdict': 'Accept with Manual Checks'}}, {'result': {'verdict': 'Reject'}}
        self.assertTrue(review_dispatch.guard_counts('uncommitted', accept, {}))
        for scope, result, chain in (('uncommitted', reject, {}), ('uncommitted', {'status': 'completed'}, {}),
                                     ('uncommitted', accept, {'shadow': True}), ('base', accept, {})):
            self.assertFalse(review_dispatch.guard_counts(scope, result, chain), (scope, result, chain))

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
        handback = [e for e in settings['PostToolUse'] if 'record_review' in e['hooks'][0]['command']]
        self.assertEqual([e['matcher'] for e in handback], ['SubagentHandback'])
        for event in ('SubagentStart', 'SubagentStop'):
            record = [e for e in settings[event] if 'record_review' in e['hooks'][0]['command']]
            self.assertEqual([e['matcher'] for e in record], ['diff-reviewer'], event)


if __name__ == '__main__':
    unittest.main()
