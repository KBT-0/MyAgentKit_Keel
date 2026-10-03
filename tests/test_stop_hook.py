"""The Stop hook must carry each gate outcome out as its own exit code and diagnostic."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'overlays/claude-code/files/.claude/hooks/gate_on_stop.sh'


class StopHookTests(unittest.TestCase):
    def test_pass_fail_and_not_run_each_reach_the_agent(self):
        # 75 is "the gate did not run": blocking, and never reported as a pass or a failure.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = root / 'gate_on_stop.sh'
            hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                            .replace('{{GATED_FILE_PATTERN}}', r'\.py$'))
            (root / 'scripts').mkdir()
            gate = root / 'scripts/check.sh'
            gate.write_text('#!/bin/sh\necho "gate output, exit $STUB_RC"\nexit "$STUB_RC"\n')
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
                    self.assertNotIn(unsaid, result.stderr)
            # A turn the hook already continued is let go, or the session loops forever.
            result = subprocess.run(['sh', str(hook)], cwd=root, input='{"stop_hook_active": true}',
                                    text=True, capture_output=True, timeout=30,
                                    env=dict(os.environ, STUB_RC='1'))
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
