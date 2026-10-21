"""The myagentkit-suggestion mod's own tests (plugin/tests/*.test.ts), run through `claude plugin test`."""
from pathlib import Path
import shutil
import subprocess
import unittest

PLUGIN = Path(__file__).resolve().parents[1] / 'plugin'


class SuggestionModTests(unittest.TestCase):
    def test_claude_plugin_test_passes(self):
        claude = shutil.which('claude')
        if claude is None:
            self.skipTest('NOT RUN: no claude CLI on PATH; `claude plugin test plugin` runs the mod tests')
        result = subprocess.run([claude, 'plugin', 'test'], cwd=PLUGIN, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(' 0 fail', result.stdout)


if __name__ == '__main__':
    unittest.main()
