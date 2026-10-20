"""The generated-plugin check must reject missing and stale runtime evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENV = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}


def track(root):
    """The packager hashes only what git tracks: make the temp kit a repository holding every file."""
    subprocess.run(["git", "init", "-q", str(root)], check=True, env=ENV)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, env=ENV)


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
            track(root)
            command =[sys.executable, str(root / "scripts/package_codex_plugin.py"), "--check"]
            target = root / "plugins/myagentkit/scripts/claude_bridge.py"
            for case in ["missing", "stale"]:
                if case == "stale":
                    target.parent.mkdir(parents=True)
                    target.write_text("old runtime\n")
                result = subprocess.run(command, capture_output=True, text=True, env=ENV)
                self.assertEqual(result.returncode, 1)
                self.assertIn("missing or stale", result.stderr)
            subprocess.run(command[:-1], check=True, capture_output=True, env=ENV)
            result = subprocess.run(command, capture_output=True, text=True, env=ENV)
            self.assertEqual(result.returncode, 0)
            self.assertIn("matches canonical", result.stdout)
            for name in ["agent_process.py", "agent_usage.py", "codex_bridge.py",
                         "review_dispatch.py", "codex_quota.py", "working_mode.py"]:
                companion = target.parent / name
                original = companion.read_bytes()
                companion.unlink()
                result = subprocess.run(command, capture_output=True, text=True, env=ENV)
                self.assertEqual(result.returncode, 1, name)
                companion.write_text("stale companion\n")
                result = subprocess.run(command, capture_output=True, text=True, env=ENV)
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
            (plugin / "skills/s/agents").mkdir()
            (plugin / "skills/s/agents/openai.yaml").write_bytes(b"agent\n")
            track(root)
            script = [sys.executable, str(root / "scripts/package_codex_plugin.py")]
            check = lambda: subprocess.run(script + ["--check"], capture_output=True, text=True, env=ENV)
            version = lambda: json.loads(manifest.read_text())["version"]
            self.assertEqual(check().returncode, 1)  # the frozen version is stale
            subprocess.run(script, check=True, capture_output=True, env=ENV)
            first = version()
            self.assertRegex(first, r"^0\.12\.0\+codex\.[0-9a-f]{12}$")
            self.assertEqual(json.loads(manifest.read_text())["skills"], "./skills/")
            self.assertEqual(check().returncode, 0, check().stderr)
            # Every host hashes the same files in the same order: case-sensitive POSIX names
            # (SKILL.md before agents/, which a Windows Path sorts the other way), git's files only.
            digest = hashlib.sha256()
            for name in ["skills/s/SKILL.md", "skills/s/agents/openai.yaml"]:
                digest.update(name.encode() + b"\0" + (plugin / name).read_bytes() + b"\0")
            digest.update(b'{"name": "myagentkit", "skills": "./skills/"}')
            self.assertEqual(first, "0.12.0+codex." + digest.hexdigest()[:12])
            (plugin / "skills/s/.DS_Store").write_bytes(b"finder\n")  # untracked: not the plugin's
            self.assertEqual(check().returncode, 0, check().stderr)
            skill.write_bytes(b"one\r\n")  # a CRLF checkout of the same skill: the same version
            self.assertEqual(check().returncode, 0, check().stderr)
            skill.write_bytes(b"two\n")
            result = check()
            self.assertEqual(result.returncode, 1)
            self.assertIn("version", result.stderr)
            subprocess.run(script, check=True, capture_output=True, env=ENV)
            self.assertNotEqual(version(), first)
            claude.write_text('{"name": "myagentkit", "version": "0.13.0"}\n')
            self.assertEqual(check().returncode, 1)
            subprocess.run(script, check=True, capture_output=True, env=ENV)
            self.assertTrue(version().startswith("0.13.0+codex."))
            # #156: each command and skill names the plugin's kit version, stamped with it.
            command = root / "plugin/commands/mode.md"
            command.parent.mkdir()
            command.write_bytes(b"# mode\r\n\r\nThis plugin is kit v0.1. Read docs/kit/.kit-version.\r\n")
            skill.write_bytes(b"This plugin is kit v0.12.\n")
            result = check()
            self.assertEqual(result.returncode, 1)
            self.assertIn("plugin/commands/mode.md names another kit version", result.stderr)
            subprocess.run(script, check=True, capture_output=True, env=ENV)
            self.assertEqual(command.read_bytes(), b"# mode\r\n\r\nThis plugin is kit v0.13.0. Read docs/kit/.kit-version.\r\n")
            self.assertEqual(skill.read_bytes(), b"This plugin is kit v0.13.0.\n")
            self.assertEqual(check().returncode, 0, check().stderr)
            # Round-1 review: a patch release's project records 0.13.1 (bootstrap.sh reads
            # `## v0.13.1`), and a stamp cut to 0.13 called the same version another.
            claude.write_text('{"name": "myagentkit", "version": "0.13.1"}\n')
            self.assertIn("plugin/commands/mode.md names another kit version", check().stderr)
            subprocess.run(script, check=True, capture_output=True, env=ENV)
            self.assertEqual(skill.read_bytes(), b"This plugin is kit v0.13.1.\n")
            self.assertEqual(check().returncode, 0, check().stderr)

    def test_every_command_and_skill_compares_the_projects_kit_version_with_its_own(self):
        # #156: one user-level plugin serves projects synced at other kit versions, unsaid.
        kit = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
        own = "This plugin is kit v%s." % kit
        files = sorted((ROOT / "plugin/commands").glob("*.md")) + sorted(ROOT.glob("plugins/myagentkit/skills/*/SKILL.md"))
        self.assertGreaterEqual(len(files), 11)
        for path in files:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                text = " ".join(path.read_text(encoding="utf-8").split())
                self.assertEqual(text.count("This plugin is kit v"), 1)
                self.assertIn(own, text)
                self.assertIn("`docs/kit/.kit-version`", text)
                self.assertIn("never stop for it", text)
                # The project's 0.12 and the stamp's 0.12.0 are one version, as are 0.12.1 and 0.12.1.
                self.assertIn("(such as `0.10` or `0.12.1`)", text)
                self.assertIn("compared part by part as numbers, a missing part counting as 0: 0.12 is 0.12.0", text)
                self.assertIn("`/myagentkit:sync`" if path.parent.name == "commands" else "`myagentkit-sync` skill", text)


if __name__ == "__main__":
    unittest.main()
