#!/usr/bin/env python3
"""Build the plugin's standalone runtime from the one canonical core implementation."""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name in ["claude_bridge.py", "codex_bridge.py", "review_dispatch.py",
                 "codex_quota.py", "agent_process.py", "agent_usage.py"]:
        source = ROOT / "core/scripts" / name
        target = ROOT / "plugins/myagentkit/scripts" / name
        if args.check:
            if not target.is_file() or source.read_bytes() != target.read_bytes():
                raise SystemExit("FAIL: packaged runtime is missing or stale; run scripts/package_codex_plugin.py")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    print("PASS: packaged runtime matches canonical core" if args.check else "Built plugin runtime")


if __name__ == "__main__":
    main()
