"""The Stop hook must carry each gate outcome out as its own exit code and diagnostic."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
# The hook gates CLAUDE_PROJECT_DIR when it is set; a suite run from a Claude Code session
# would otherwise gate that session's project instead of each test's repository.
os.environ.pop('CLAUDE_PROJECT_DIR', None)
HOOK = ROOT / 'overlays/claude-code/files/.claude/hooks/gate_on_stop.sh'


def gated_repo(root, gate_body):
    """A repository with a staged gated change, a stub gate and the hook at root/hook.sh."""
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    (root / 'scripts').mkdir()
    (root / 'scripts/check.sh').write_text('#!/bin/sh\n' + gate_body, newline='\n')
    (root / 'scripts/check.sh').chmod(0o755)
    (root / 'src').mkdir()
    (root / 'src/app.py').write_text('dirty\n', newline='\n')
    subprocess.run(['git', 'add', 'src/app.py'], cwd=root, check=True)
    hook = root / 'hook.sh'
    hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                    .replace('{{GATED_FILE_PATTERN}}', r'\.py$'), newline='\n')
    return hook


def stop(hook, root, payload='{}'):
    return subprocess.run(['sh', str(hook)], cwd=root, input=payload, text=True, capture_output=True,
                          timeout=60)


class StopHookTests(unittest.TestCase):
    def test_an_ungated_turn_runs_no_gate_and_a_gated_one_waits_at_most_500_s(self):
        # Documentation and tooling turns skip the gate: a dirty file the pattern does not match
        # runs nothing. A matching one runs it with a lock wait below the hook's 600 s timeout.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, 'echo "${GATE_LOCK_WAIT-unset}" > gate-ran\nexit 1\n')
            hook.write_text(hook.read_text().replace(r'\.py$', r'\.c$'), newline='\n')
            env = {k: v for k, v in os.environ.items() if k != 'GATE_LOCK_WAIT'}
            run = lambda: subprocess.run(['sh', str(hook)], cwd=root, input='{}', text=True,
                                         capture_output=True, timeout=60, env=env)
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / 'gate-ran').exists(), 'an ungated turn ran the gate')
            (root / 'src/x.c').write_text('dirty\n', newline='\n')
            result = run()
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual((root / 'gate-ran').read_text().strip(), '500')

    def test_a_cd_into_another_checkout_still_gates_the_session_project(self):
        # Claude Code runs a hook in the current directory, which follows a `cd`: a lead that
        # cd'd into a clean worker worktree finished its turn with its own red change ungated.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, 'echo ran > gate-ran\nexit 1\n')
            worker = root / '.claude/worktrees/w1'
            worker.mkdir(parents=True)
            subprocess.run(['git', 'init', '-q', str(worker)], check=True)
            result = subprocess.run(['sh', str(hook)], cwd=worker, input='{}', text=True,
                                    capture_output=True, timeout=60,
                                    env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)))
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('GATE FAILED', result.stderr)
            self.assertTrue((root / 'gate-ran').exists())

    def test_pass_fail_and_not_run_each_reach_the_agent(self):
        # 75 is "the gate did not run": blocking, and never reported as a pass or a failure.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = root / 'gate_on_stop.sh'
            hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                            .replace('{{GATED_FILE_PATTERN}}', r'\.py$'), newline='\n')
            (root / 'scripts').mkdir()
            gate = root / 'scripts/check.sh'
            # A 150-line build tail before the last line: the hook once fed back only the last
            # 20 lines, so the agent never saw where a build failure started.
            gate.write_text('#!/bin/sh\necho "first line of the gate output"\n'
                            'i=0; while [ $i -lt 150 ]; do echo "build line $i"; i=$((i + 1)); done\n'
                            'echo "gate output, exit $STUB_RC"\nexit "$STUB_RC"\n', newline='\n')
            gate.chmod(0o755)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            (root / 'src').mkdir()
            (root / 'src/app.py').write_text('dirty\n', newline='\n')
            subprocess.run(['git', 'add', 'src/app.py'], cwd=root, check=True)  # a gated change
            for rc, code, said, unsaid in ((0, 0, None, 'GATE'), (1, 2, 'GATE FAILED', 'DID NOT RUN'),
                                           (75, 2, 'GATE DID NOT RUN', 'GATE FAILED')):
                with self.subTest(rc=rc):
                    result = subprocess.run(['sh', str(hook)], cwd=root, input='{}', text=True,
                                            capture_output=True, timeout=30,
                                            env=dict(os.environ, STUB_RC=str(rc)))
                    self.assertEqual(result.returncode, code, result.stderr)
                    if said:
                        self.assertIn(said, result.stderr)
                        self.assertIn('gate output, exit %d' % rc, result.stderr)
                        self.assertIn('first line of the gate output', result.stderr)
                        self.assertIn('build line 0\n', result.stderr)
                    else:
                        self.assertEqual(result.stdout + result.stderr, '')
                    self.assertNotIn(unsaid, result.stderr)
                    # A new tree each time: an unchanged one is not run again.
                    (root / 'src/app.py').write_text('dirty %d\n' % rc, newline='\n')

    def test_a_continued_stop_gates_a_changed_tree_and_ends_on_an_unchanged_one(self):
        # stop_hook_active once skipped every continued stop, so a fix made after a red gate
        # ended the turn unchecked; a block by plain_report.py did the same (#208).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, 'echo ran >> .git/gate-runs\necho "gate says red"\nexit 1\n')
            runs = lambda: (root / '.git/gate-runs').read_text().count('ran') if (root / '.git/gate-runs').exists() else 0
            # Another hook's block: this tree was never gated, so the gate runs.
            result = stop(hook, root, '{"stop_hook_active" : true}')
            self.assertEqual((result.returncode, runs()), (2, 1), result.stderr)
            # The agent changes nothing: the continued stop ends, the gate does not run.
            result = stop(hook, root, '{"stop_hook_active":true}')
            self.assertEqual((result.returncode, runs()), (0, 1), result.stderr)
            # The agent edits a gated file (staged or not, or a new untracked one): gated again.
            for edit in ('src/app.py', 'src/new.py'):
                (root / edit).write_text('fix attempt\n', newline='\n')
                result = stop(hook, root, '{"stop_hook_active":true}')
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('gate says red', result.stderr)
            self.assertEqual(runs(), 3)
            # A new turn on the unchanged red tree runs the gate again: a failure is never replayed.
            result = stop(hook, root)
            self.assertEqual((result.returncode, runs()), (2, 4), result.stderr)
            self.assertIn('gate says red', result.stderr)

    def test_a_continued_stop_ignores_a_file_outside_the_gated_code(self):
        # A background process that keeps writing a log made every continued stop a new tree,
        # so a red gate ran and blocked again up to the vendor's cap (round-1 review).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, 'echo ran >> .git/gate-runs\nexit 1\n')
            runs = lambda: (root / '.git/gate-runs').read_text().count('ran')
            self.assertEqual(stop(hook, root).returncode, 2)
            for line in ('one\n', 'two\n'):
                (root / 'server.log').write_text(line, newline='\n')
                result = stop(hook, root, '{"stop_hook_active":true}')
                self.assertEqual((result.returncode, runs()), (0, 1), result.stderr)
            (root / 'src/new.py').write_text('fix\n', newline='\n')
            self.assertEqual((stop(hook, root, '{"stop_hook_active":true}').returncode, runs()), (2, 2))

    def test_a_failure_is_run_again_on_a_new_turn(self):
        # A replayed failure blocked every new turn although the gate would now pass: a flaky
        # test, or a gate that regenerates a file and then fails (round-1 review).
        for gate in ('echo ran >> .git/gate-runs\n[ "$(grep -c ran .git/gate-runs)" -gt 1 ]\n',
                     'echo ran >> .git/gate-runs\n[ -e src/gen.py ] || { echo x > src/gen.py; echo stale; exit 1; }\n'):
            with self.subTest(gate=gate), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                hook = gated_repo(root, gate)
                runs = lambda: (root / '.git/gate-runs').read_text().count('ran')
                self.assertEqual(stop(hook, root).returncode, 2)
                self.assertEqual((stop(hook, root, '{"stop_hook_active":true}').returncode, runs()), (0, 1))
                result = stop(hook, root)
                self.assertEqual((result.returncode, runs()), (0, 2), result.stderr)

    def test_a_commit_names_a_new_tree(self):
        # check.sh reads HEAD's history (Done: trailers): a commit that leaves the index, the
        # diff and the untracked files as they were must not reuse a PASS (round-1 review).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, 'echo ran >> .git/gate-runs\n')
            git = lambda *a: subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                                             *a], cwd=root, check=True, capture_output=True)
            git('commit', '-q', '-m', 'base')
            (root / 'src/app.py').write_text('dirty again\n', newline='\n')
            runs = lambda: (root / '.git/gate-runs').read_text().count('ran')
            self.assertEqual((stop(hook, root).returncode, stop(hook, root).returncode, runs()), (0, 0, 1))
            git('commit', '-q', '--allow-empty', '-m', 'close', '-m', 'Done: K1')
            self.assertEqual((stop(hook, root).returncode, runs()), (0, 2))

    def test_a_tree_with_a_submodule_is_never_remembered(self):
        # Edits inside a submodule are not in the diff (one "-dirty" line, or nothing under
        # ignore=all): such a tree is never remembered as passed, so every new turn runs the
        # gate (round-1 review). The loop guard still sees the gated code: a continued stop
        # after an edit to it runs the gate (#208), one without an edit ends (round-2 review).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, 'echo ran >> .git/gate-runs\n[ ! -e .git/red ]\n')
            subprocess.run(['git', 'update-index', '--add', '--cacheinfo', '160000,%s,sub' % ('1' * 40)],
                           cwd=root, check=True)
            runs = lambda: (root / '.git/gate-runs').read_text().count('ran')
            self.assertEqual((stop(hook, root).returncode, stop(hook, root).returncode, runs()), (0, 0, 2))
            (root / '.git/red').write_text('', newline='\n')
            self.assertEqual((stop(hook, root).returncode, runs()), (2, 3))
            self.assertEqual((stop(hook, root, '{"stop_hook_active":true}').returncode, runs()), (0, 3))
            (root / 'src/app.py').write_text('fix attempt\n', newline='\n')
            self.assertEqual((stop(hook, root, '{"stop_hook_active":true}').returncode, runs()), (2, 4))
            self.assertEqual((stop(hook, root, '{"stop_hook_active":true}').returncode, runs()), (0, 4))

    def test_a_new_file_in_a_new_directory_is_gated(self):
        # `git status --porcelain` folds a new directory into `?? src/pkg/`, which the gated
        # pattern does not match: a turn that only added src/pkg/__init__.py ended ungated.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, 'echo ran >> .git/gate-runs\n')
            subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-q',
                            '-m', 'base'], cwd=root, check=True, capture_output=True)
            (root / 'src/pkg').mkdir()
            (root / 'src/pkg/__init__.py').write_text('', newline='\n')
            self.assertEqual(stop(hook, root).returncode, 0)
            self.assertTrue((root / '.git/gate-runs').exists(), 'a new file in a new directory ran no gate')

    def test_a_passed_tree_is_not_gated_again(self):
        # Stop fires after every reply: a dirty file ran a 217 s gate on each short answer (#81).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, 'echo ran >> .git/gate-runs\n[ ! -e touch-tree ] || cat .git/gate-runs > src/stamp.py\n')
            runs = lambda: (root / '.git/gate-runs').read_text().count('ran')
            for expected in (1, 1):
                result = stop(hook, root)
                self.assertEqual((result.returncode, result.stderr), (0, ''))
                self.assertEqual(runs(), expected)
            # Any content change counts, an untracked file's included.
            (root / 'src/new.py').write_text('a\n', newline='\n')
            self.assertEqual((stop(hook, root).returncode, runs()), (0, 2))
            (root / 'src/new.py').write_text('b\n', newline='\n')
            self.assertEqual((stop(hook, root).returncode, runs()), (0, 3))
            self.assertEqual((stop(hook, root).returncode, runs()), (0, 3))
            # A tree that changed while the gate ran is not the tree that passed.
            (root / 'touch-tree').write_text('', newline='\n')
            self.assertEqual((stop(hook, root).returncode, runs()), (0, 4))
            self.assertEqual((stop(hook, root).returncode, runs()), (0, 5))


if __name__ == '__main__':
    unittest.main()
