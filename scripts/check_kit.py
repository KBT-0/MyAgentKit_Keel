#!/usr/bin/env python3
"""Offline kit acceptance: syntax, packaged source, regression tests, and bootstrap gates."""
import argparse
import ast
import json
import io
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SUITES = {
    'core/scripts': {'test_claude_bridge': 38, 'test_agent_usage': 12, 'test_codex_quota': 3},
    'tests': {'test_packaging': 1, 'test_bootstrap': 1, 'test_acceptance': 2,
              'test_review_upgrade': 1, 'test_boundary_example': 1},
}


def run_tests(root, directory, required):
    """Require named regression suites to execute; absence and skips are failures."""
    folder = root / directory
    for name in required:
        if not (folder / (name + '.py')).is_file():
            raise RuntimeError('missing required test suite: ' + name)
    suite = unittest.TestLoader().discover(str(folder), pattern='test_*.py')

    def cases(node):
        for item in node:
            if isinstance(item, unittest.TestSuite):
                yield from cases(item)
            else:
                yield item

    counts = dict.fromkeys(required, 0)
    for test in cases(suite):
        module = test.id().split('.')[0]
        if module in counts:
            counts[module] += 1
    for name, minimum in required.items():
        if counts[name] < minimum:
            raise RuntimeError('required test suite is incomplete: ' + name)
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped:
        raise RuntimeError('required tests failed or were skipped:\n' + output.getvalue())
    print(output.getvalue().strip())


def run(args, cwd=ROOT, expected=0, reason=None):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    if result.returncode != expected or (reason and reason not in output):
        raise RuntimeError(f"{args}: expected exit {expected}, reason {reason!r}\n{output}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    for path in ROOT.rglob("*.py"):
        if ".git" not in path.parts:
            ast.parse(path.read_text(), filename=str(path))
    for path in ROOT.rglob("*.sh"):
        if ".git" not in path.parts:
            run(["sh", "-n", str(path)])
    manifest = json.loads((ROOT / "plugins/myagentkit/.codex-plugin/plugin.json").read_text())
    if manifest["name"] != "myagentkit" or manifest["skills"] != "./skills/":
        raise RuntimeError("plugin manifest does not expose the expected package")
    print(run([sys.executable, "scripts/package_codex_plugin.py", "--check"]).strip())
    for directory, required in REQUIRED_SUITES.items():
        run_tests(ROOT, directory, required)
    with tempfile.TemporaryDirectory(prefix="myagentkit-acceptance-") as tmp:
        project = Path(tmp)
        run(["sh", str(ROOT / "bootstrap.sh"), str(project)])
        run(["git", "init", "-q"], project)
        output = run(["sh", "scripts/check.sh"], project, expected=1)
        if "FAIL" not in output:
            raise RuntimeError("fresh bootstrap did not reject absent configuration")
        # Synthetic acceptance only; real project setup still belongs to the interview.
        for path in project.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "setup" in path.parts:
                continue
            text = path.read_text()
            text = text.replace("{{BUILD_TEST_COMMAND}}", "test -f scripts/claude_bridge.py")
            text = text.replace("{{TOOLCHAIN_PATH_SETUP}}", "")
            text = re.sub(r"\{\{[A-Z0-9_]+\}\}", "fixture", text)
            path.write_text(text)
        (project / "scripts/boundary_checks.sh").write_text("# Synthetic project has no domain boundaries.\n")
        (project / "scripts/boundary_selftests.sh").write_text("# Domain gates are project-specific.\n")
        run(["git", "add", "."], project)
        run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS")
        print("PASS: bootstrap rejects missing setup and accepts the configured synthetic project")
        if args.self_test:
            print(run(["sh", "scripts/check.sh", "--self-test"], project,
                      reason="SELF-TEST: PASS").strip())
            tests = project / "scripts/test_claude_bridge.py"
            original_tests = tests.read_bytes()
            tests.unlink()
            run(["sh", "scripts/check.sh", "--self-test"], project, expected=1,
                reason="review self-test file is missing or empty")
            tests.write_bytes(original_tests)
            wrapper = project / "scripts/review.sh"
            original_wrapper = wrapper.read_bytes()
            for stub in ["exit 1\n", "exit 0\n"]:
                wrapper.write_text(stub)
                run(["sh", "scripts/check.sh", "--self-test"], project, expected=1,
                    reason="review adapter negative tests failed or did not run")
            wrapper.write_bytes(original_wrapper)
            print("PASS: missing review tests, failed runner, and absent completion evidence reject")
    print("KIT CHECK: PASS")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"KIT CHECK: FAIL — {error}", file=sys.stderr)
        raise SystemExit(1)
