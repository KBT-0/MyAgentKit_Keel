"""The generated-plugin check must reject missing and stale runtime evidence."""
import json
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
                         "review_dispatch.py", "codex_quota.py", "working_mode.py"]:
                (source.parent / name).write_text("canonical companion\n")
            for manifest in ("plugin/.claude-plugin", "plugins/myagentkit/.codex-plugin"):
                (root / manifest).mkdir(parents=True)
                (root / manifest / "plugin.json").write_text('{"name": "myagentkit", "version": "0.12.0"}\n')
            command =[sys.executable, str(root / "scripts/package_codex_plugin.py"), "--check"]
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
                         "review_dispatch.py", "codex_quota.py", "working_mode.py"]:
                companion = target.parent / name
                original = companion.read_bytes()
                companion.unlink()
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, name)
                companion.write_text("stale companion\n")
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, name)
                companion.write_bytes(original)

    def test_the_codex_manifest_version_follows_the_kit_version_and_the_packaged_content(self):
        # #156: the version stayed 0.1.0+codex.20260906131755 for every release, and Codex keys
        # its plugin cache by it, so an installed plugin never saw a change.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "core/scripts", root / "core/scripts",
                            ignore=shutil.ignore_patterns("__pycache__"))
            (root / "scripts").mkdir()
            shutil.copyfile(ROOT / "scripts/package_codex_plugin.py", root / "scripts/package_codex_plugin.py")
            (root / "plugin/.claude-plugin").mkdir(parents=True)
            claude = root / "plugin/.claude-plugin/plugin.json"
            claude.write_text('{"name": "myagentkit", "version": "0.12.0"}\n')
            plugin = root / "plugins/myagentkit"
            (plugin / ".codex-plugin").mkdir(parents=True)
            manifest = plugin / ".codex-plugin/plugin.json"
            manifest.write_text('{\n  "name": "myagentkit",\n  "version": "0.1.0+codex.20260906131755",\n'
                                '  "skills": "./skills/"\n}\n')
            (plugin / "skills/s").mkdir(parents=True)
            skill = plugin / "skills/s/SKILL.md"
            skill.write_bytes(b"one\n")
            script = [sys.executable, str(root / "scripts/package_codex_plugin.py")]
            check = lambda: subprocess.run(script + ["--check"], capture_output=True, text=True)
            version = lambda: json.loads(manifest.read_text())["version"]
            self.assertEqual(check().returncode, 1)  # the frozen version is stale
            subprocess.run(script, check=True, capture_output=True)
            first = version()
            self.assertRegex(first, r"^0\.12\.0\+codex\.[0-9a-f]{12}$")
            self.assertEqual(json.loads(manifest.read_text())["skills"], "./skills/")
            self.assertEqual(check().returncode, 0, check().stderr)
            skill.write_bytes(b"one\r\n")  # a CRLF checkout of the same skill: the same version
            self.assertEqual(check().returncode, 0, check().stderr)
            skill.write_bytes(b"two\n")
            result = check()
            self.assertEqual(result.returncode, 1)
            self.assertIn("version", result.stderr)
            subprocess.run(script, check=True, capture_output=True)
            self.assertNotEqual(version(), first)
            claude.write_text('{"name": "myagentkit", "version": "0.13.0"}\n')
            self.assertEqual(check().returncode, 1)
            subprocess.run(script, check=True, capture_output=True)
            self.assertTrue(version().startswith("0.13.0+codex."))


if __name__ == "__main__":
    unittest.main()
