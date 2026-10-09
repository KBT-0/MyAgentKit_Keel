"""The Stop hook must carry each gate outcome out as its own exit code and diagnostic."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'overlays/claude-code/files/.claude/hooks/gate_on_stop.sh'


class StopHookTests(unittest.TestCase):
    def test_a_self_test_sentinel_skips_the_gate_with_a_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            (root / 'scripts').mkdir()
            gate = root / 'scripts/check.sh'
            gate.write_text('#!/bin/sh\necho ran > gate-ran\nexit 1\n')
            gate.chmod(0o755)
            hook = root / 'gate_on_stop.sh'
            hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                            .replace('{{GATED_FILE_PATTERN}}', r'\.py$'))
            (root / 'src/domain').mkdir(parents=True)
            (root / 'src/app.py').write_text('dirty\n')
            subprocess.run(['git', 'add', 'src/app.py'], cwd=root, check=True)
            for name in ('CMakeLists.txt.selftest-backup', 'src/domain/.selftest.py'):
                with self.subTest(sentinel=name):
                    sentinel = root / name
                    sentinel.write_text('injection\n')
                    result = subprocess.run(['sh', str(hook)], cwd=root, input='{}', text=True,
                                            capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('NOTE [Stop hook]: skipping the gate', result.stderr)
                    self.assertIn(name, result.stderr)
                    self.assertFalse((root / 'gate-ran').exists())
                    sentinel.unlink()
            result = subprocess.run(['sh', str(hook)], cwd=root, input='{}', text=True,
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertTrue((root / 'gate-ran').exists())

    def test_pass_fail_and_not_run_each_reach_the_agent(self):
        # 75 is "the gate did not run": blocking, and never reported as a pass or a failure.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = root / 'gate_on_stop.sh'
            hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                            .replace('{{GATED_FILE_PATTERN}}', r'\.py$'))
            (root / 'scripts').mkdir()
            gate = root / 'scripts/check.sh'
            # A 150-line build tail before the last line: the hook once fed back only the last
            # 20 lines, so the agent never saw where a build failure started.
            gate.write_text('#!/bin/sh\necho "first line of the gate output"\n'
                            'i=0; while [ $i -lt 150 ]; do echo "build line $i"; i=$((i + 1)); done\n'
                            'echo "gate output, exit $STUB_RC"\nexit "$STUB_RC"\n')
            gate.chmod(0o755)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            (root / 'src').mkdir()
            (root / 'src/app.py').write_text('dirty\n')
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
