#!/usr/bin/env python3
"""Offline kit acceptance: syntax, packaged source, regression tests, and bootstrap gates."""
import argparse
import ast
import json
import io
import os
from pathlib import Path
import re
import shlex
import shutil
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
              'test_boundary_restore': 1, 'test_sync_kit': 2, 'test_doctor': 1,
              'test_git_hooks': 4},
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


# A gate run that waits forever (a lock never released) must fail here, not hang the kit check.
def run(args, cwd=ROOT, expected=0, reason=None, env=None, timeout=300):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env,
                            timeout=timeout)
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
            with tempfile.TemporaryDirectory(prefix="myagentkit-side-") as side:
                side = Path(side)
                # A normal run refuses the self-test seams, so these cases set the build command
                # the way a project does, in the copy's check.sh: it runs side/build.sh, which
                # each case rewrites. Restored below; a failure discards the whole copy.
                build = side / "build.sh"
                gate = project / "scripts/check.sh"
                original_gate = gate.read_text()
                configured = 'build_test_cmd="test -f scripts/claude_bridge.py"'
                if configured not in original_gate:
                    raise RuntimeError("the synthetic project's build command line was not found")
                gate.write_text(original_gate.replace(
                    configured, f'build_test_cmd="sh {shlex.quote(str(build))}"'))
                status = ["git", "status", "--porcelain", "--untracked-files=all"]
                before = run(status, project)
                # Every nested gate run records the tree through the build command, so a case
                # that writes into the tree and cleans up afterwards is still caught.
                log = side / "status.log"
                build.write_text(f'{{ git status --porcelain --untracked-files=all; echo ==; }} >> "{log}"\n')
                # GATE_LOCK_WAIT: a nested run that does not inherit the lock stops in seconds.
                print(run(["sh", "scripts/check.sh", "--self-test"], project,
                          env=dict(os.environ, GATE_LOCK_WAIT="5"), reason="SELF-TEST: PASS").strip())
                seen = log.read_text().split("==\n")[:-1]
                if not seen or any(s != before for s in seen) or run(status, project) != before:
                    raise RuntimeError("check.sh --self-test changed the working tree:\n"
                                       + "".join(s for s in seen if s != before))
                print("PASS: git status of the project is unchanged at every nested gate run and after --self-test")
                # Every self-test seam exported into a normal run fails it by name, including
                # an override that would turn a red build green.
                seams = {"GATE_BUILD_CMD_OVERRIDE": "true", "GATE_SELFTEST_STATE_FILE": "docs/STATE.md",
                         "GATE_SELFTEST_PROJECT_FILE": "docs/PROJECT.md",
                         "BOUNDARY_CHECKS_FILE": "scripts/boundary_checks.sh",
                         "BOUNDARY_SELFTESTS_FILE": "scripts/boundary_selftests.sh",
                         "GATE_SELFTEST_EXTRA_FILE": "docs/STATE.md",
                         "GATE_SELFTEST_BREAK_SCANNER": "1"}
                build.write_text("false\n")
                own_lock = os.path.realpath(project) + "/.git/check.lock"
                for name, value in seams.items():
                    refused = f"FAIL [env]: {name} is set; self-test overrides are not honoured"
                    for cmd in (["sh", "scripts/check.sh"], ["sh", "scripts/check.sh", "--self-test"]):
                        run(cmd, project, expected=1, reason=refused, timeout=60,
                            env=dict(os.environ, **{name: value}))
                    # A copied marker without the lock it names is no marker.
                    run(["sh", "scripts/check.sh"], project, expected=1, reason=refused, timeout=60,
                        env=dict(os.environ, GATE_SELFTEST_NESTED=str(os.getpid()),
                                 GATE_LOCK_HELD=own_lock, **{name: value}))
                print("PASS: every self-test override exported into a normal run fails it by name")
                # Two gate runs sharing one build directory: the second must wait, not race.
                build.write_text(f'mkdir "{side}/build" && sleep 2 && rmdir "{side}/build"\n')
                pair = [subprocess.Popen(["sh", "scripts/check.sh"], cwd=project,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True) for _ in range(2)]
                outputs = [p.communicate(timeout=60)[0] for p in pair]
                if (any(p.returncode or "CHECK: PASS" not in o for p, o in zip(pair, outputs))
                        or not any("NOTE [lock]" in o for o in outputs)):
                    raise RuntimeError("concurrent gate runs raced:\n" + "\n".join(outputs))
                print("PASS: two concurrent gate runs sharing a build directory both pass")
                build.write_text("true\n")
                # A holder killed without cleanup must not block every later run.
                dead = subprocess.Popen(["true"])
                dead.wait()
                lock = project / ".git/check.lock"
                os.symlink(str(dead.pid), lock)
                run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", timeout=60)
                # Two waiters on one dead holder: only one may reclaim. Shims make the race
                # certain: readlink holds each waiter until both have read the dead pid, and the
                # second waiter to touch the lock path (rm or mv) does so a second later, after
                # the first has reclaimed it and started.
                shims = side / "shims"
                shims.mkdir()
                for tool in ("readlink", "rm", "mv"):
                    real = shutil.which(tool)
                    if tool == "readlink":
                        body = (f'out=$("{real}" "$@") || exit\nprintf "%s\\n" "$out"\n'
                                f'[ "$out" = {dead.pid} ] || exit 0\nmkdir "{side}/read.$PPID" 2>/dev/null\n'
                                f'i=0; while [ "$(ls -d "{side}"/read.* | wc -l)" -lt 2 ] && [ $i -lt 50 ]; do\n'
                                f'  sleep 0.1; i=$((i + 1)); done\n')
                    else:
                        body = (f'for a; do [ "$a" != "{own_lock}" ] || {{ mkdir "{side}/first" 2>/dev/null || sleep 1; }}; done\n'
                                f'exec "{real}" "$@"\n')
                    (shims / tool).write_text("#!/bin/sh\n" + body)
                    (shims / tool).chmod(0o755)
                build.write_text(f'mkdir "{side}/build" && sleep 2 && rmdir "{side}/build"\n')
                os.symlink(str(dead.pid), lock)
                shimmed = dict(os.environ, PATH=str(shims) + os.pathsep + os.environ["PATH"])
                pair = [subprocess.Popen(["sh", "scripts/check.sh"], cwd=project, env=shimmed,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True) for _ in range(2)]
                outputs = [p.communicate(timeout=60)[0] for p in pair]
                if any(p.returncode or "CHECK: PASS" not in o for p, o in zip(pair, outputs)):
                    raise RuntimeError("two waiters reclaiming one stale lock ran together:\n"
                                       + "\n".join(outputs))
                build.write_text("true\n")
                # A pid reused by a process that is not a gate run (after a reboot, say) is stale too.
                other = subprocess.Popen(["sleep", "60"])
                try:
                    os.symlink(str(other.pid), lock)
                    run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", timeout=30,
                        env=dict(os.environ, GATE_LOCK_WAIT="3"))
                finally:
                    other.kill()
                    other.wait()
                print("PASS: a lock left by a killed gate run is reclaimed, by one waiter only,"
                      " and a pid now running something else does not hold it")
                # A live holder: a bounded wait gives up with its own code, and only a run
                # given this checkout's own lock path skips the lock. The holder looks like a
                # gate run; a live pid that is not one counts as stale.
                holder = subprocess.Popen(["sh", "-c", "sleep 60; :", "scripts/check.sh"])
                os.symlink(str(holder.pid), lock)
                try:
                    run(["sh", "scripts/check.sh"], project, expected=75, reason="NOT RUN [lock]",
                        env=dict(os.environ, GATE_LOCK_WAIT="2"), timeout=30)
                    run(["sh", "scripts/check.sh"], project, expected=75, reason="NOT RUN [lock]",
                        env=dict(os.environ, GATE_LOCK_WAIT="2",
                                 GATE_LOCK_HELD=str(side / "other-checkout.lock")), timeout=30)
                    out = run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", timeout=30,
                              env=dict(os.environ, GATE_LOCK_WAIT="2",
                                       GATE_LOCK_HELD=own_lock))
                    if "NOTE [lock]" in out:
                        raise RuntimeError("a run given its own lock path waited:\n" + out)
                    # A run whose lock was taken over (a stale-reclaim race) leaves it alone.
                    lock.unlink()
                    build.write_text(f"rm -f .git/check.lock && ln -s {os.getpid()} .git/check.lock\n")
                    run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", timeout=30)
                    if not lock.is_symlink():
                        raise RuntimeError("a gate run removed a lock another run held")
                finally:
                    lock.unlink(missing_ok=True)
                    holder.kill()
                    holder.wait()
                print("PASS: a bounded lock wait stops with NOT RUN; only the own lock path is"
                      " inherited; a run removes only its own lock")
                gate.write_text(original_gate)
            # The scanners read untracked files too (git ls-files --others), not only the index.
            marker = project / "untracked-marker.md"
            marker.write_text("{{SELF_TEST" + "_TOKEN}}\n")
            try:
                run(["sh", "scripts/check.sh"], project, expected=1, reason="CHECK: FAIL")
            finally:
                marker.unlink()
            print("PASS: an untracked file with an unfilled marker turns the gate red")
            # A tracked file deleted without `git rm` fails the gate under its own name,
            # not as a scanner that failed to run.
            gone = project / "deleted-unstaged.md"
            gone.write_text("tracked, then deleted without git rm\n")
            run(["git", "add", gone.name], project)
            gone.unlink()
            try:
                out = run(["sh", "scripts/check.sh"], project, expected=1,
                          reason="deleted-unstaged.md is tracked but missing")
                if "a scanner failed to run" in out:
                    raise RuntimeError("a deleted tracked file was reported as a scanner failure:\n" + out)
            finally:
                run(["git", "rm", "-q", "--cached", gone.name], project)
            # A directory symlink (a dependency directory linked into a fresh worktree) holds
            # nothing git tracks: the scan skips it with a line instead of failing on it.
            link = project / "node_modules"
            os.symlink("docs", link)
            try:
                run(["sh", "scripts/check.sh"], project, reason="NOTE [scan]: skipped node_modules")
            finally:
                link.unlink()
            print("PASS: a deleted tracked file is named, a directory symlink is skipped with a note")
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
            # An owner who allows AI credit has no rule line; the hook's case says it skipped.
            agents = project / "AGENTS.md"
            original_agents = agents.read_bytes()
            agents.write_text(original_agents.decode().replace("No AI attribution in git", "AI credit allowed"))
            out = run(["sh", "scripts/check.sh", "--self-test"], project, reason="SELF-TEST: PASS")
            if "skipped by owner choice" not in out:
                raise RuntimeError("the commit-msg case did not say it was skipped by owner choice:\n" + out)
            agents.write_bytes(original_agents)
            checks.write_bytes(original_checks)
            selftests.write_bytes(original_selftests)
            wrapper.write_bytes(original_wrapper)
            print("PASS: missing review tests, failed runner, absent completion evidence, an emptied "
                  "suite and boundary checks whose self-tests ran no case reject; an owner's AI-credit choice is a visible skip")
    print("KIT CHECK: PASS")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.TimeoutExpired) as error:
        print(f"KIT CHECK: FAIL — {error}", file=sys.stderr)
        raise SystemExit(1)
