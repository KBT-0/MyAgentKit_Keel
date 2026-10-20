#!/usr/bin/env python3
"""Build the plugin's standalone runtime from the one canonical core implementation."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/myagentkit"
MANIFEST = PLUGIN / ".codex-plugin/plugin.json"
STAMP = re.compile(rb"This plugin is kit v\d+(?:\.\d+)+\.")


def stamped():
    """Each Claude command and Codex skill names the plugin's kit version, which it compares with
    the project's docs/kit/.kit-version (#156): (path, its bytes, its bytes stamped) per file."""
    kit = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    line = b"This plugin is kit v%s." % kit.encode()
    for path in sorted((ROOT / "plugin/commands").glob("*.md")) + sorted(PLUGIN.glob("skills/*/SKILL.md")):
        data = path.read_bytes()
        yield path, data, STAMP.sub(line, data)


def version(manifest):
    """The kit version plus a hash of the packaged content: Codex keys its plugin cache by the
    manifest's version, so a frozen one kept every install on its first build (#156). Line
    endings are hashed as LF, so a CRLF checkout of the skills gives the same version. Only the
    files git tracks are hashed, sorted as case-sensitive POSIX names, so every host agrees: a
    Windows Path sorts without case, and an untracked .DS_Store or *.orig lives on one host."""
    listed = subprocess.run(["git", "ls-files", "-z", "--", "."], cwd=PLUGIN,
                            capture_output=True, check=True).stdout.decode("utf-8")
    digest = hashlib.sha256()
    for name in sorted(filter(None, listed.split("\0"))):
        path = PLUGIN / name
        if path == MANIFEST or not path.is_file():
            continue
        digest.update(name.encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    rest = {key: value for key, value in manifest.items() if key != "version"}
    digest.update(json.dumps(rest, sort_keys=True).encode())
    kit = json.loads((ROOT / "plugin/.claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    return "%s+codex.%s" % (kit, digest.hexdigest()[:12])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name in ["claude_bridge.py", "codex_bridge.py", "review_dispatch.py",
                 "codex_quota.py", "agent_process.py", "agent_usage.py", "working_mode.py"]:
        source = ROOT / "core/scripts" / name
        target = PLUGIN / "scripts" / name
        if args.check:
            if not target.is_file() or source.read_bytes() != target.read_bytes():
                raise SystemExit("FAIL: packaged runtime is missing or stale; run scripts/package_codex_plugin.py")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    for path, data, new in stamped():
        if new == data:
            continue
        if args.check:
            raise SystemExit("FAIL: %s names another kit version than the plugin; run "
                             "scripts/package_codex_plugin.py" % path.relative_to(ROOT).as_posix())
        path.write_bytes(new)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    stamp = version(manifest)
    if args.check:
        if manifest.get("version") != stamp:
            raise SystemExit("FAIL: the Codex plugin version %r is stale (the content gives %r); run "
                             "scripts/package_codex_plugin.py" % (manifest.get("version"), stamp))
    elif manifest.get("version") != stamp:
        manifest["version"] = stamp
        MANIFEST.write_bytes((json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print("PASS: packaged runtime matches canonical core" if args.check else "Built plugin runtime")


if __name__ == "__main__":
    main()
