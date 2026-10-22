"""The myagentkit-suggestion mod's own tests (plugin/tests/*.test.ts), run through `claude plugin test`.

The test runner is the claude CLI itself, so a host without it (CI) declares the skip and
check_kit's minimum for this suite drops to 0 there, the way validate_plugin prints NOT RUN."""
from pathlib import Path
import os
import shutil
import subprocess
import unittest

PLUGIN = Path(__file__).resolve().parents[1] / 'plugin'
CLAUDE = shutil.which('claude')
# The bound times MYAGENTKIT_TEST_TIMEOUT_SCALE: check_kit raises it while units run side by side.
SCALE = float(os.environ.get('MYAGENTKIT_TEST_TIMEOUT_SCALE', '1'))


class SuggestionModTests(unittest.TestCase):
    @unittest.skipIf(CLAUDE is None, 'NOT RUN: no claude CLI on PATH; `claude plugin test` in plugin/ runs the mod tests')
    def test_claude_plugin_test_passes(self):
        result = subprocess.run([CLAUDE, 'plugin', 'test'], cwd=PLUGIN, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=300 * SCALE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(' 0 fail', result.stdout)
    test_claude_plugin_test_passes._kit_platform_skip = CLAUDE is None


if __name__ == '__main__':
    unittest.main()
