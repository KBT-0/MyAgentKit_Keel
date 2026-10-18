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


def stop(hook, root):
    return subprocess.run(['sh', str(hook)], cwd=root, input='{}', text=True, capture_output=True,
                          timeout=60)


class StopHookTests(unittest.TestCase):
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
            # A turn the hook already continued is let go, or the session loops forever.
            result = subprocess.run(['sh', str(hook)], cwd=root, input='{"stop_hook_active": true}',
                                    text=True, capture_output=True, timeout=30,
                                    env=dict(os.environ, STUB_RC='1'))
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
