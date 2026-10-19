"""guard_boundaries.py warns about a forbidden import whatever separator the path uses."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/.claude/hooks/guard_boundaries.py'
GUARD = '("/src/domain/", ".py", ("import web",), "the domain must not depend on the web layer"),'


class GuardBoundariesTests(unittest.TestCase):
    def setUp(self):
        text = HOOK.read_text(encoding='utf-8')
        self.assertIn('"{{BOUNDARY_GUARDS}}",', text)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.hook = Path(tmp.name) / 'guard_boundaries.py'
        self.hook.write_text(text.replace('"{{BOUNDARY_GUARDS}}",', GUARD), encoding='utf-8')

    def warns(self, tool_input, platform=None):
        # PLATFORM (os.name, sys.platform) runs the hook as if on that host.
        command = [sys.executable, str(self.hook)] if platform is None else [
            sys.executable, '-c', 'import os, runpy, sys; os.name, sys.platform = sys.argv[1:3]; '
            'runpy.run_path(sys.argv[3], run_name="__main__")', *platform, str(self.hook)]
        result = subprocess.run(command, input=json.dumps({'tool_input': tool_input}).encode('utf-8'),
                                capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return 'BOUNDARY VIOLATION' in result.stdout.decode('utf-8')

    def test_a_windows_path_is_matched(self):
        # Native Windows sends `file_path` with backslashes; the fragment uses `/`.
        for path in ('C:\\proj\\src\\domain\\x.py', '/proj/src/domain/x.py'):
            with self.subTest(path=path):
                self.assertTrue(self.warns({'file_path': path, 'new_string': 'import web\n'}))

    def test_each_tool_field_is_read_and_only_the_guarded_files_warn(self):
        # A drift in one tool's field name made the hook inert for that tool; a lost path or
        # suffix filter warned on every file (#265). NotebookEdit was never read (#264).
        self.assertTrue(self.warns({'file_path': '/p/src/domain/x.py', 'content': 'import web\n'}))
        self.assertTrue(self.warns({'notebook_path': '/p/src/domain/n.ipynb', 'new_source': 'import web\n'}))
        for tool_input in ({'file_path': '/p/src/web/x.py', 'content': 'import web\n'},
                           {'file_path': '/p/src/domain/x.txt', 'new_string': 'import web\n'},
                           {'file_path': '/p/src/domain/x.py', 'content': 'import os\n'}):
            with self.subTest(tool_input=tool_input):
                self.assertFalse(self.warns(tool_input))

    def test_a_case_variant_path_warns_on_windows_and_macos_only(self):
        # The Windows filesystem ignores case: src\Domain\a.PY is the guarded file (#264); a
        # default macOS volume (APFS) ignores case too, a Linux one does not.
        for platform, folds in ((('nt', 'win32'), True), (('posix', 'darwin'), True), (('posix', 'linux'), False)):
            for path in ('C:\\p\\src\\Domain\\a.py', '/p/src/domain/a.PY'):
                with self.subTest(platform=platform, path=path):
                    self.assertEqual(self.warns({'file_path': path, 'content': 'import web\n'}, platform), folds)


if __name__ == '__main__':
    unittest.main()
