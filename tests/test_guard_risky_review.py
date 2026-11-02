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
import time
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

    def hook(self, name, payload, **extra):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root), **extra)
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

    def test_a_worktree_session_is_judged_by_its_own_tree(self):
        # #317: the session started in the main checkout (CLAUDE_PROJECT_DIR) and works in a worktree (cwd)
        tree = self.root / 'wt'
        self.git('worktree', 'add', '-q', str(tree))
        (self.root / 'src/money/round.py').write_text('x = 9\n', encoding='utf-8')  # main's own dirty risky file
        (tree / 'notes.md').write_text('b\n', encoding='utf-8')
        commit = {'tool_name': 'Bash', 'tool_input': {'command': 'git commit -am notes'}, 'cwd': str(tree / 'src')}
        self.assertEqual(self.hook('guard_risky_review.py', commit).returncode, 0)
        (tree / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        refused = self.hook('guard_risky_review.py', commit)
        self.assertEqual(refused.returncode, 2)
        self.assertIn('src/money/round.py', refused.stderr.decode())
        for name in ('SubagentStart', 'SubagentStop'):
            self.hook('record_review.py', {'hook_event_name': name, 'agent_type': 'diff-reviewer', 'agent_id': 'a1',
                                           'last_assistant_message': 'Verdict: Accept\n\nNo findings.', 'cwd': str(tree)})
        self.assertEqual(self.hook('guard_risky_review.py', commit).returncode, 0)
        self.assertEqual(self.commit().returncode, 2)  # the main checkout's record is untouched
        # a commit into the main checkout from the worktree (-C) or from outside any work tree is judged by main
        for payload in ({'command': 'git -C "%s" commit -am x' % self.root, 'cwd': str(tree)},
                        {'command': 'git commit -am x', 'cwd': str(self.root.parent)},
                        {'command': 'git commit -am x', 'cwd': str(self.root / 'gone')}):
            call = {'tool_name': 'Bash', 'tool_input': {'command': payload['command']}, 'cwd': payload['cwd']}
            self.assertEqual(self.hook('guard_risky_review.py', call).returncode, 2, payload)
        # a -C value only the shell expands names the call's own tree, never the clean session folder (r2 Medium)
        self.git('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qam', 'main')  # main clean: only the worktree's unreviewed file can refuse
        (tree / 'src/money/tax.py').write_text('t = 1\n', encoding='utf-8')
        for command in ('git -C "$PWD" commit -am x', 'git -C "$(pwd)" commit -am x', 'git -C "$NOPE" commit -am x'):
            call = {'tool_name': 'Bash', 'tool_input': {'command': command}, 'cwd': str(tree)}
            self.assertEqual(self.hook('guard_risky_review.py', call).returncode, 2, command)

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
                     'Verdict: Accept\n' + 'finding 1 ' * 40 + 'x', 'Verdict: Accept\n' + '`` ' * 40 + 'x'):  # an ambiguous label split took 2**40 steps
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
        self.assertTrue(review_dispatch.guard_counts('base', accept, {}))  # labricore A1
        for scope, result, chain in (('uncommitted', reject, {}), ('uncommitted', {'status': 'completed'}, {}),
                                     ('uncommitted', accept, {'shadow': True})):
            self.assertFalse(review_dispatch.guard_counts(scope, result, chain), (scope, result, chain))

    def commit_in(self, tree, message):
        subprocess.run(['git', '-C', str(tree), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                        'commit', '-qam', message], check=True, capture_output=True)
        return subprocess.run(['git', '-C', str(tree), 'rev-parse', 'HEAD'], check=True, capture_output=True,
                              text=True).stdout.strip()

    def test_a_merge_of_a_branch_reviewed_with_commit_passes(self):
        # labricore A1: a worker branch in a real worktree, reviewed with --commit in two rounds (round 1's
        # file untouched by round 2), merged into the main checkout: the merge's commit passes
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core/scripts'))
        import review_dispatch
        tree = self.root / 'wt'
        self.git('worktree', 'add', '-q', '-b', 'w1', str(tree))
        (tree / 'scripts/check.sh').write_text('true\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(tree), 'add', 'scripts/check.sh'], check=True)
        first = self.commit_in(tree, 'round 1')
        (tree / 'src/money/round.py').write_text('x = 5\n', encoding='utf-8')
        second = self.commit_in(tree, 'round 2 fix')
        review_dispatch.note_reviewed(tree, 'commit', second, ['scripts/check.sh', 'src/money/round.py'])
        self.assertTrue(first)
        (self.root / 'notes.md').write_text('main moved\n', encoding='utf-8')
        self.commit_in(self.root, 'main')
        self.git('merge', '--no-ff', '--no-commit', 'w1')
        merge = 'git merge --no-ff --no-commit w1 && git commit -m merge'
        self.assertEqual(self.commit(merge).returncode, 0, self.commit(merge).stderr)
        # a risky file that differs from the reviewed content is refused
        (self.root / 'src/money/round.py').write_text('x = 6\n', encoding='utf-8')
        refused = self.commit(merge)
        self.assertEqual(refused.returncode, 2)
        self.assertIn('src/money/round.py', refused.stderr.decode())
        self.assertNotIn('scripts/check.sh', refused.stderr.decode())

    def test_a_diff_reviewer_accept_in_a_worktree_covers_its_merge(self):
        tree = self.root / 'wt'
        self.git('worktree', 'add', '-q', '-b', 'w2', str(tree))
        (tree / 'src/money/round.py').write_text('x = 7\n', encoding='utf-8')
        for name in ('SubagentStart', 'SubagentStop'):
            self.hook('record_review.py', {'hook_event_name': name, 'agent_type': 'diff-reviewer', 'agent_id': 'w',
                                           'cwd': str(tree), 'last_assistant_message': 'Verdict: Accept'})
        self.commit_in(tree, 'reviewed')
        self.git('merge', '--ff-only', 'w2')  # the record is the worktree's own HEAD; the content record is shared
        (self.root / 'src/money/round.py').write_text('x = 8\n', encoding='utf-8')
        self.assertEqual(self.commit().returncode, 2)
        (self.root / 'src/money/round.py').write_text('x = 7\n', encoding='utf-8')
        self.git('reset', '-q', '--hard', 'HEAD~1')
        (self.root / 'src/money/round.py').write_text('x = 7\n', encoding='utf-8')
        self.assertEqual(self.commit().returncode, 0, self.commit().stderr)

    def test_an_unresolvable_c_folder_is_refused(self):
        # labricore A4: $WT the hook cannot expand fell back to the session's tree and passed
        for command in ('git -C "$NO_SUCH_WT_VAR" commit -m x', 'git -C ~/no-such-wt-dir commit -m x'):
            with self.subTest(command=command):
                refused = self.commit(command)
                self.assertEqual(refused.returncode, 2)
                self.assertIn('-C folder', refused.stderr.decode())
        self.assertEqual(self.commit('git -C "%s" commit -m x' % self.root).returncode, 0)

    def test_git_exe_commit_is_seen(self):
        # labricore A7: native Windows spells it git.exe
        (self.root / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        self.assertEqual(self.commit('git.exe commit -am x').returncode, 2)

    def test_severity_forms(self):
        # labricore A5: a path-first High blocks; a "High-risk" line does not void an Accept
        sys.path.insert(0, str(HOOKS))
        import record_review
        self.assertFalse(record_review.accepted('Verdict: Accept\n- src/x.ts:3 \u2014 High: off by one'))
        self.assertTrue(record_review.accepted('Verdict: Accept\nHigh-risk paths: none touched.'))

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

    def test_a_read_only_git_line_naming_commit_passes(self):
        (self.root / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        for command in ('git show HEAD:docs/commit-style.md', 'git log -1 --format=%H  # the reviewed commit',
                        'git commit-tree HEAD^{tree}'):
            with self.subTest(command=command):
                self.assertEqual(self.commit(command).returncode, 0)
        self.assertEqual(self.commit('git -c user.name="A B" commit -qam fix').returncode, 2)
        started = time.monotonic()
        self.commit('git ' + ' -c ' * 3000 + 'x')
        self.assertLess(time.monotonic() - started, 30)  # leanrel: an overlapping option form backtracked for minutes

    def test_a_non_ascii_risky_path_under_a_c_locale(self):
        # leanrel High: a locale codec without the name's bytes crashed both hooks; every commit was refused
        name = os.path.join(str(self.root), 'src', 'money', 'の.py')
        # a POSIX test run under LC_ALL=C (check_kit's locale matrix) cannot encode the name: write the UTF-8 bytes
        with open(name if os.name == 'nt' else os.fsencode(str(self.root)) + '/src/money/の.py'.encode('utf-8'),
                  'wb') as f:
            f.write(b'n = 1\n')
        c_locale = dict(LC_ALL='C', LANG='C', PYTHONCOERCECLOCALE='0', PYTHONUTF8='0')
        refused = self.hook('guard_risky_review.py', {'tool_name': 'Bash', 'tool_input': {'command': 'git commit -am x'}},
                            **c_locale)
        self.assertEqual(refused.returncode, 2, refused.stderr)
        self.assertIn(b'BLOCKED', refused.stderr)
        for name in ('SubagentStart', 'SubagentStop'):
            self.hook('record_review.py', {'hook_event_name': name, 'agent_type': 'diff-reviewer', 'agent_id': 'a1',
                                           'last_assistant_message': 'Verdict: Accept'}, **c_locale)
        self.assertEqual(self.commit('git commit -am x').returncode, 0)

    def test_a_single_quoted_setting_is_read(self):
        (self.root / 'scripts/gate_config.sh').write_text("risky_paths='src/money/*'\n", encoding='utf-8')
        self.git('add', 'scripts/gate_config.sh')
        self.git('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'quoted')
        (self.root / 'src/money/round.py').write_text('x = 2\n', encoding='utf-8')
        self.assertEqual(self.commit().returncode, 2)

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
