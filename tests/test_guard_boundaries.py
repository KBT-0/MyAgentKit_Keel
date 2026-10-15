"""guard_boundaries.py warns about a forbidden import whatever separator the path uses."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/hooks/guard_boundaries.py'
GUARD = '("/src/domain/", ".py", ("import web",), "the domain must not depend on the web layer"),'


class GuardBoundariesTests(unittest.TestCase):
    def test_a_windows_path_is_matched(self):
        # Native Windows sends `file_path` with backslashes; the fragment uses `/`.
        text = HOOK.read_text(encoding='utf-8')
        self.assertIn('"{{BOUNDARY_GUARDS}}",', text)
        with tempfile.TemporaryDirectory() as tmp:
            hook = Path(tmp) / 'guard_boundaries.py'
            hook.write_text(text.replace('"{{BOUNDARY_GUARDS}}",', GUARD), encoding='utf-8')
            for path in ('C:\\proj\\src\\domain\\x.py', '/proj/src/domain/x.py'):
                with self.subTest(path=path):
                    payload = {'tool_input': {'file_path': path, 'new_string': 'import web\n'}}
                    result = subprocess.run([sys.executable, str(hook)], input=json.dumps(payload).encode('utf-8'),
                                            capture_output=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('BOUNDARY VIOLATION', result.stdout.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
