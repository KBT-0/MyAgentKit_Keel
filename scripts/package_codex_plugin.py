#!/usr/bin/env python3
"""Build the plugin's standalone runtime from the one canonical core implementation."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/myagentkit"
MANIFEST = PLUGIN / ".codex-plugin/plugin.json"


def version(manifest):
    """The kit version plus a hash of the packaged content: Codex keys its plugin cache by the
    manifest's version, so a frozen one kept every install on its first build (#156). Line
    endings are hashed as LF, so a CRLF checkout of the skills gives the same version."""
    digest = hashlib.sha256()
    for path in sorted(p for p in PLUGIN.rglob("*") if p.is_file() and p != MANIFEST and "__pycache__" not in p.parts):
        digest.update(path.relative_to(PLUGIN).as_posix().encode() + b"\0")
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
