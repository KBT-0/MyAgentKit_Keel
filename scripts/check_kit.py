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
# The review self-test ships to projects with its own minimums; read them, never copy them.
BRIDGE_MINIMUMS = next(
    (ast.literal_eval(node.value)
     for node in ast.parse((ROOT / 'core/scripts/test_claude_bridge.py').read_text()).body
     if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', None) == 'SUITE_MINIMUMS'),
    None)
if BRIDGE_MINIMUMS is None:
    sys.exit('KIT CHECK: FAIL — SUITE_MINIMUMS not found in core/scripts/test_claude_bridge.py')
REQUIRED_SUITES = {
    'core/scripts': dict(BRIDGE_MINIMUMS, test_agent_cost=2),
    'tests': {'test_packaging': 1, 'test_bootstrap': 1, 'test_acceptance': 2,
              'test_review_upgrade': 1, 'test_boundary_example': 1, 'test_scan_gate': 1,
              'test_boundary_restore': 1, 'test_sync_kit': 2, 'test_doctor': 1},
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
        # The rot gate's message must name where operation detail goes instead.
        state = project / "docs/STATE.md"
        original_state = state.read_bytes()
        state.write_text("# STATE\n\n## Active work\n\n" + "closed work\n" * 250)
        run(["sh", "scripts/check.sh"], project, expected=1, reason="docs/<OPERATION>.md")
        state.write_bytes(original_state)
        print("PASS: bootstrap rejects missing setup and accepts the configured synthetic project")
        if args.self_test:
            print(run(["sh", "scripts/check.sh", "--self-test"], project,
                      reason="SELF-TEST: PASS").strip())
            tests = project / "scripts/test_claude_bridge.py"
            original_tests = tests.read_bytes()
            tests.unlink()
            # Remove the missing file from the synthetic index too, so this case
            # reaches review-test absence instead of the earlier unreadable-file gate.
            run(["git", "add", "-u", "--", "scripts/test_claude_bridge.py"], project)
            run(["sh", "scripts/check.sh", "--self-test"], project, expected=1,
                reason="review self-test file is missing or empty")
            tests.write_bytes(original_tests)
            run(["git", "add", "scripts/test_claude_bridge.py"], project)
            wrapper = project / "scripts/review.sh"
            original_wrapper = wrapper.read_bytes()
            for stub in ["exit 1\n", "exit 0\n"]:
                wrapper.write_text(stub)
                run(["sh", "scripts/check.sh", "--self-test"], project, expected=1,
                    reason="review adapter negative tests failed or did not run")
            wrapper.write_bytes(original_wrapper)
            # One emptied suite must fail on its own, not hide inside a combined test total.
            quota_tests = project / "scripts/test_codex_quota.py"
            original_quota = quota_tests.read_bytes()
            quota_tests.write_text("import unittest\nclass QuotaTests(unittest.TestCase):\n    pass\n")
            run(["sh", "scripts/review.sh", "--self-test"], project, expected=2,
                reason="QuotaTests has 0 of at least 3 tests")
            quota_tests.write_bytes(original_quota)
            # Boundary checks whose self-test file runs no case are skipped, not passed. The
            # stubbed review run keeps this case to the boundary branch alone.
            wrapper.write_text("echo 'REVIEW SELF-TEST: PASS'\n")
            checks = project / "scripts/boundary_checks.sh"
            selftests = project / "scripts/boundary_selftests.sh"
            original_checks, original_selftests = checks.read_bytes(), selftests.read_bytes()
            checks.write_text(": synthetic boundary check\n")
            run(["sh", "scripts/check.sh", "--self-test"], project, expected=1, reason="ran no case")
            selftests.write_text("echo '  ok   — synthetic boundary case'\n")
            run(["sh", "scripts/check.sh", "--self-test"], project, reason="SELF-TEST: PASS")
            checks.write_bytes(original_checks)
            selftests.write_bytes(original_selftests)
            wrapper.write_bytes(original_wrapper)
            print("PASS: missing review tests, failed runner, absent completion evidence, an emptied "
                  "suite and boundary checks whose self-tests ran no case reject")
    print("KIT CHECK: PASS")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f"KIT CHECK: FAIL — {error}", file=sys.stderr)
        raise SystemExit(1)
