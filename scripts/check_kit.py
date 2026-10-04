#!/usr/bin/env python3
"""Offline kit acceptance: syntax, packaged source, regression tests, and bootstrap gates."""
import argparse
import ast
import fcntl
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
import time
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
              'test_boundary_restore': 1, 'test_sync_kit': 3, 'test_doctor': 1,
              'test_git_hooks': 8, 'test_stop_hook': 1},
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
def run(args, cwd=ROOT, expected=0, reason=None, env=None, timeout=300, **popen):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env,
                            timeout=timeout, **popen)
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
        # With CDPATH exported, `cd scripts` printed the directory into the gate's own path,
        # and the gate re-ran a two-line file name instead of its checks.
        run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", env=dict(os.environ, CDPATH="."))
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
                # The marker a self-test run exports dies with that run: copied out of a finished
                # run, it is refused like any other.
                build.write_text(f'cat .git/check.lock > "{side}/holder"\n')
                run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", timeout=60)
                marker = (side / "holder").read_text()
                if not marker.isdigit():
                    raise RuntimeError(f"the lock file did not name its holder: {marker!r}")
                run(["sh", "scripts/check.sh"], project, expected=1, timeout=60,
                    reason="FAIL [env]: GATE_BUILD_CMD_OVERRIDE is set",
                    env=dict(os.environ, GATE_SELFTEST_NESTED=marker,
                             GATE_LOCK_HELD=own_lock, GATE_BUILD_CMD_OVERRIDE="true"))
                print("PASS: a self-test marker copied out of a finished run is refused")
                # A gate killed with SIGKILL never clears its pid from the lock file. Once its
                # build has exited too, nobody holds the lock, and variables copied out of the
                # killed run name it exactly: refused, never honoured as a self-test's seams.
                build.write_text(f'cat .git/check.lock > "{side}/holder"\n'
                                 f'echo "$GATE_LOCK_FD" > "{side}/fd.tmp"\nmv "{side}/fd.tmp" "{side}/fd"\n'
                                 'sleep 1\n')
                killed = subprocess.Popen(["sh", "scripts/check.sh"], cwd=project,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic() + 60
                while not (side / "fd").exists():
                    if killed.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("the gate to be killed never started its build")
                    time.sleep(0.1)
                killed.kill()
                killed.wait()
                with open(project / ".git/check.lock") as probe:
                    while True:
                        try:
                            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            if time.monotonic() > deadline:
                                raise RuntimeError("the killed gate's build never released the lock")
                            time.sleep(0.1)
                marker = (side / "holder").read_text()
                if (project / ".git/check.lock").read_text() != marker:
                    raise RuntimeError("the killed gate's pid was not left in the lock file")
                build.write_text("false\n")
                run(["sh", "scripts/check.sh"], project, expected=1, timeout=60,
                    reason="FAIL [env]: GATE_BUILD_CMD_OVERRIDE is set",
                    env=dict(os.environ, GATE_SELFTEST_NESTED=marker, GATE_LOCK_HELD=own_lock,
                             GATE_LOCK_FD=(side / "fd").read_text().strip(),
                             GATE_BUILD_CMD_OVERRIDE="true"))
                print("PASS: variables copied out of a gate killed with SIGKILL are refused")
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
                # A gate killed with SIGKILL while its build runs: the build keeps the lock, and
                # none of three waiters builds until it exits. The build directory is the proof:
                # a waiter whose build overlapped the orphaned one fails on "File exists".
                build.write_text(f'mkdir "{side}/build" || exit 1\nsleep "${{HOLD:-1}}"\n'
                                 f'rmdir "{side}/build"\n')
                killed = subprocess.Popen(["sh", "scripts/check.sh"], cwd=project,
                                          env=dict(os.environ, HOLD="6"),
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic() + 60
                while not (side / "build").is_dir():
                    if killed.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("the gate to be killed never started its build")
                    time.sleep(0.1)
                killed.kill()
                killed.wait()
                waiters = [subprocess.Popen(["sh", "scripts/check.sh"], cwd=project,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            text=True) for _ in range(3)]
                outputs = [p.communicate(timeout=120)[0] for p in waiters]
                if any(p.returncode or "CHECK: PASS" not in o for p, o in zip(waiters, outputs)):
                    raise RuntimeError("a waiter built beside the build of a killed gate, or beside"
                                       " another waiter:\n" + "\n".join(outputs))
                print("PASS: a gate killed with SIGKILL holds the lock until its build exits;"
                      " three waiters then run one at a time")
                # A file at the lock path that is not a lock (the symlink an older check.sh left
                # behind when killed) is refused by name, never followed or replaced.
                lock = project / ".git/check.lock"
                lock.unlink(missing_ok=True)
                os.symlink("12345", lock)
                try:
                    run(["sh", "scripts/check.sh"], project, expected=1, timeout=30,
                        reason="FAIL [lock]: cannot open")
                finally:
                    lock.unlink(missing_ok=True)
                # A live holder: a bounded wait gives up with its own code, and only a run
                # given this checkout's own lock path skips the lock.
                build.write_text("true\n")
                with open(lock, "a") as held:
                    fcntl.flock(held, fcntl.LOCK_EX)
                    run(["sh", "scripts/check.sh"], project, expected=75, reason="NOT RUN [lock]",
                        env=dict(os.environ, GATE_LOCK_WAIT="2"), timeout=30)
                    run(["sh", "scripts/check.sh"], project, expected=75, reason="NOT RUN [lock]",
                        env=dict(os.environ, GATE_LOCK_WAIT="2",
                                 GATE_LOCK_HELD=str(side / "other-checkout.lock")), timeout=30)
                    # The own lock path is inherited only with the descriptor that holds it.
                    run(["sh", "scripts/check.sh"], project, expected=1, timeout=30,
                        reason="FAIL [env]: GATE_LOCK_HELD",
                        env=dict(os.environ, GATE_LOCK_WAIT="2", GATE_LOCK_HELD=own_lock))
                    out = run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", timeout=30,
                              pass_fds=(held.fileno(),),
                              env=dict(os.environ, GATE_LOCK_WAIT="2", GATE_LOCK_HELD=own_lock,
                                       GATE_LOCK_FD=str(held.fileno())))
                    if "NOTE [lock]" in out:
                        raise RuntimeError("a run given its own lock path waited:\n" + out)
                    # A descriptor opened independently on the same file, with the holder's pid
                    # copied, is not the lock: the holder's description holds it, this one does not.
                    held.truncate(0)
                    held.write(str(os.getpid()))
                    held.flush()
                    with open(lock) as other:
                        run(["sh", "scripts/check.sh"], project, expected=1, timeout=30,
                            reason="FAIL [env]: GATE_LOCK_HELD", pass_fds=(other.fileno(),),
                            env=dict(os.environ, GATE_LOCK_WAIT="2", GATE_LOCK_HELD=own_lock,
                                     GATE_LOCK_FD=str(other.fileno()),
                                     GATE_SELFTEST_NESTED=str(os.getpid()),
                                     GATE_BUILD_CMD_OVERRIDE="true"))
                print("PASS: a symlink at the lock path is refused; a bounded lock wait stops with"
                      " NOT RUN; only the own lock path, with the descriptor holding it, is inherited, never"
                      " an independently opened one")
                # Linux's NFS client takes an exclusive flock only on a descriptor open for
                # writing: the inheritance probe opened its own read-only, and every fresh run
                # failed FAIL [env]. A sitecustomize refuses such a flock as NFS does, then
                # every flock (the probe's, then the first one) as a lockless file system does.
                fake = side / "fake-flock"
                fake.mkdir()
                (fake / "sitecustomize.py").write_text(
                    "import errno, fcntl, os\n"
                    "real, mode = fcntl.flock, os.environ.get('FAKE_FLOCK')\n"
                    "def flock(fd, op):\n"
                    "    fd = fd if isinstance(fd, int) else fd.fileno()\n"
                    "    if mode == 'nfs' and op & fcntl.LOCK_EX and (\n"
                    "            fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY):\n"
                    "        raise OSError(errno.EBADF, os.strerror(errno.EBADF))\n"
                    "    if mode == 'none' or (mode == 'none-held' and 'GATE_LOCK_HELD' in os.environ):\n"
                    "        raise OSError(errno.ENOLCK, os.strerror(errno.ENOLCK))\n"
                    "    return real(fd, op)\n"
                    "fcntl.flock = flock\n")
                run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", timeout=60,
                    env=dict(os.environ, PYTHONPATH=str(fake), FAKE_FLOCK="nfs"))
                for mode in ("none-held", "none"):
                    out = run(["sh", "scripts/check.sh"], project, expected=1, timeout=30,
                              reason="FAIL [lock]: this file system does not support the gate lock (",
                              env=dict(os.environ, PYTHONPATH=str(fake), FAKE_FLOCK=mode))
                    if "FAIL [env]" in out:
                        raise RuntimeError("a lockless file system was reported as an environment fault:\n" + out)
                print("PASS: a lock that needs a writable descriptor (NFS) is taken; a file system"
                      " without locks fails FAIL [lock] by name")
                # python3 only in the configured toolchain directory, as a hook sees a Python
                # installed per user: the lock, which is taken through python3, still finds it.
                tc, no_python = side / "tc", side / "no-python"
                tc.mkdir(); no_python.mkdir()
                (tc / "python3").symlink_to(sys.executable)
                for directory in os.environ["PATH"].split(os.pathsep):
                    if os.path.isdir(directory):
                        for name in os.listdir(directory):
                            source = Path(directory) / name
                            if (not name.startswith("python") and source.exists()
                                    and not os.path.lexists(no_python / name)):
                                (no_python / name).symlink_to(source.resolve())
                if 'toolchain_path=""' not in gate.read_text():
                    raise RuntimeError("the synthetic project's toolchain_path line was not found")
                gate.write_text(gate.read_text().replace('toolchain_path=""', f'toolchain_path="{tc}"'))
                run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", timeout=60,
                    env=dict(os.environ, PATH=str(no_python)))
                print("PASS: a python3 found only through toolchain_path takes the gate lock")
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
            # Git tracks a symlink's link text: a dangling link whose text holds an unfilled
            # marker was skipped whole and passed the setup gate. Assembled, never literal.
            # A link named like an option was read as one: "readlink --version" printed the
            # version and the marker in the link text passed.
            for name in ("config-link", "--version"):
                link = project / name
                os.symlink("{{" + "CONFIG_DIR}}/config.json", link)
                run(["git", "add", "--", name], project)
                try:
                    run(["sh", "scripts/check.sh"], project, expected=1,
                        reason="symlink " + name + " -> {{" + "CONFIG_DIR}}/config.json")
                finally:
                    run(["git", "rm", "-q", "--cached", "--", name], project)
                    link.unlink()
            # A link is reported under its own path, so setup/ stays exempt: aggregated under
            # a temporary file's name, an exempt setup/ link failed the gate beside a real one.
            (project / "setup").mkdir(exist_ok=True)
            links = ("setup/example-link", "config-link")
            for name in links:
                os.symlink("{{" + "CONFIG_DIR}}/config.json", project / name)
            run(["git", "add", "--", *links], project)
            try:
                out = run(["sh", "scripts/check.sh"], project, expected=1,
                          reason="config-link:1:symlink config-link -> {{" + "CONFIG_DIR}}")
                if "symlink setup/example-link ->" in out:
                    raise RuntimeError("an exempt setup/ symlink failed the setup gate:\n" + out)
            finally:
                run(["git", "rm", "-q", "--cached", "--", *links], project)
                for name in links:
                    (project / name).unlink()
            # Link text holding a newline was written as two lines, the second without the
            # link's path: a non-exempt link whose text went on to "setup/" and a marker had
            # that line removed by the setup/ exemption and passed, and an exempt setup/ link
            # with a marker on its second line failed. Every newline is now written as \n.
            marker = "{{" + "CONFIG_DIR}}"
            for name, target, expected, reason in (
                    ("multi-link", "missing\nsetup/" + marker, 1,
                     "multi-link:1:symlink multi-link -> missing\\nsetup/" + marker),
                    ("setup/multi-link", "missing\n" + marker, 0, None)):
                os.symlink(target, project / name)
                run(["git", "add", "--", name], project)
                try:
                    run(["sh", "scripts/check.sh"], project, expected=expected, reason=reason)
                finally:
                    run(["git", "rm", "-q", "--cached", "--", name], project)
                    (project / name).unlink()
            # A failed append of link text (a full disk, a lost permission) was ignored: the
            # link's marker went unscanned and the gate could pass. Here a stand-in readlink
            # puts a directory where the second link's text is appended.
            with tempfile.TemporaryDirectory(prefix="myagentkit-side-") as side:
                shim, scratch = Path(side) / "bin", Path(side) / "tmp"
                shim.mkdir()
                scratch.mkdir()
                (shim / "readlink").write_text(
                    "#!/bin/sh\n"
                    "for d in \"$TMPDIR\"/*/; do\n"
                    "  if [ -f \"$d/symlink-text\" ]; then rm -f \"$d/symlink-text\" && mkdir \"$d/symlink-text\"; fi\n"
                    "done\n"
                    "exec " + shutil.which("readlink") + " \"$@\"\n")
                (shim / "readlink").chmod(0o755)
                links = ("a-link", "b-link")
                for name in links:
                    os.symlink(marker + "/" + name, project / name)
                run(["git", "add", "--", *links], project)
                try:
                    run(["sh", "scripts/check.sh"], project, expected=1,
                        reason="could not sort the file list; refusing to scan blind",
                        env=dict(os.environ, TMPDIR=str(scratch),
                                 PATH=str(shim) + os.pathsep + os.environ["PATH"]))
                finally:
                    run(["git", "rm", "-q", "--cached", "--", *links], project)
                    for name in links:
                        (project / name).unlink()
            print("PASS: a deleted tracked file is named, a directory symlink is skipped with a note,"
                  " a symlink's link text is scanned under its own path")
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
            # The shipped existing-file example, run by the enclosing self-test against a check
            # it can trip: it counts as a case only by printing its ok line.
            src = project / "src"
            if src.exists():
                raise RuntimeError("the synthetic project already has src/")
            (src / "domain").mkdir(parents=True)
            (src / "domain/existing.py").write_text("original\n")
            # Tracked, so the case can show the example leaves the checkout's status unchanged.
            run(["git", "add", "src"], project)
            checks.write_text("! grep -q myapp.web src/domain/existing.py ||\n"
                              "  { echo 'FAIL [boundary]: the domain layer imports the web layer:'; fail=1; }\n")
            example = (ROOT / "core/scripts/boundary_selftests.sh").read_text().splitlines()
            selftests.write_text("\n".join(line[4:] for line in example if line.startswith("# | ")) + "\n")
            # An owner who allows AI credit has no rule line; the hook's case says it skipped.
            agents = project / "AGENTS.md"
            original_agents = agents.read_bytes()
            agents.write_text(original_agents.decode().replace("No AI attribution in git", "AI credit allowed"))
            status = run(["git", "status", "--porcelain"], project)
            out = run(["sh", "scripts/check.sh", "--self-test"], project, reason="SELF-TEST: PASS")
            if "skipped by owner choice" not in out:
                raise RuntimeError("the commit-msg case did not say it was skipped by owner choice:\n" + out)
            if "  ok   — domain/web boundary gate rejects a forbidden import in an existing file" not in out:
                raise RuntimeError("the existing-file boundary example did not run as a case:\n" + out)
            if (src / "domain/existing.py").read_text() != "original\n":
                raise RuntimeError("the existing-file boundary example changed its target in the checkout")
            if run(["git", "status", "--porcelain"], project) != status:
                raise RuntimeError("the existing-file boundary example changed the checkout's git status")
            run(["git", "rm", "-r", "-q", "--cached", "src"], project)
            shutil.rmtree(src)
            agents.write_bytes(original_agents)
            checks.write_bytes(original_checks)
            selftests.write_bytes(original_selftests)
            wrapper.write_bytes(original_wrapper)
            print("PASS: missing review tests, failed runner, absent completion evidence, an emptied "
                  "suite and boundary checks whose self-tests ran no case reject; the existing-file example "
                  "runs as a case; an owner's AI-credit choice is a visible skip")
    print("KIT CHECK: PASS")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.TimeoutExpired) as error:
        print(f"KIT CHECK: FAIL — {error}", file=sys.stderr)
        raise SystemExit(1)
