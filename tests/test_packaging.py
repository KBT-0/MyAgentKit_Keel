"""The generated-plugin check must reject missing and stale runtime evidence."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_missing_stale_and_matching_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "core/scripts").mkdir(parents=True)
            shutil.copyfile(ROOT / "scripts/package_codex_plugin.py", root / "scripts/package_codex_plugin.py")
            source = root / "core/scripts/claude_bridge.py"
            source.write_text("canonical runtime\n")
            for name in ["agent_process.py", "agent_usage.py", "codex_bridge.py",
                         "review_dispatch.py", "codex_quota.py"]:
                (source.parent / name).write_text("canonical companion\n")
            command = [sys.executable, str(root / "scripts/package_codex_plugin.py"), "--check"]
            target = root / "plugins/myagentkit/scripts/claude_bridge.py"
            for case in ["missing", "stale"]:
                if case == "stale":
                    target.parent.mkdir(parents=True)
                    target.write_text("old runtime\n")
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("missing or stale", result.stderr)
            subprocess.run(command[:-1], check=True, capture_output=True)
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("matches canonical", result.stdout)
            for name in ["agent_process.py", "agent_usage.py", "codex_bridge.py",
                         "review_dispatch.py", "codex_quota.py"]:
                companion = target.parent / name
                original = companion.read_bytes()
                companion.unlink()
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, name)
                companion.write_text("stale companion\n")
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, name)
                companion.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
