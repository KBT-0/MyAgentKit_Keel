"""The Stop hook must carry each gate outcome out as its own exit code and diagnostic."""
import importlib.util
import os
import shlex
import shutil
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
# The hook gates CLAUDE_PROJECT_DIR when it is set; a suite run from a Claude Code session
# would otherwise gate that session's project instead of each test's repository.
os.environ.pop('CLAUDE_PROJECT_DIR', None)
HOOK = ROOT / 'overlays/claude-code/files/.claude/hooks/gate_on_stop.sh'


def gated_repo(root, gate_body):
    """A repository with a staged gated change, a stub gate and the hook at root/hook.sh."""
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    (root / 'scripts').mkdir()
    (root / 'scripts/check.sh').write_text('#!/bin/sh\n' + gate_body, newline='\n')
    (root / 'scripts/check.sh').chmod(0o755)
    (root / 'src').mkdir()
    (root / 'src/app.py').write_text('dirty\n', newline='\n')
    subprocess.run(['git', 'add', 'src/app.py'], cwd=root, check=True)
    hook = root / 'hook.sh'
    hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                    .replace('{{GATED_FILE_PATTERN}}', r'\.py$'), newline='\n')
    return hook


def stop(hook, root):
    return subprocess.run(['sh', str(hook)], cwd=root, input='{}', text=True, capture_output=True,
                          timeout=60)


class StopHookTests(unittest.TestCase):
    def test_a_dead_self_test_with_a_surviving_build_does_not_skip(self):
        # The real self-test publishes the marker; its baseline build keeps the lock after
        # that self-test shell is killed. The Stop hook must report NOT RUN, never skip.
        spec = importlib.util.spec_from_file_location('gate_fixture', ROOT / 'tests' /
                                                     ('test_check_gate_windows.py' if os.name == 'nt'
                                                      else 'test_check_gate.py'))
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            project = tmp / 'project'
            fixture.make_project(project)
            (project / 'src').mkdir()
            (project / 'src/app.py').write_text('dirty\n', newline='\n')
            subprocess.run(['git', 'add', 'src/app.py'], cwd=project, check=True)
            hook = tmp / 'hook.sh'
            hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                            .replace('{{GATED_FILE_PATTERN}}', r'\.py$'), newline='\n')
            build = tmp / 'build.sh'
            # Published whole: a redirect creates READY before it fills it.
            build.write_text('cat .git/check-selftest > "$READY.tmp" && mv "$READY.tmp" "$READY"\n'
                             'while [ ! -f "$RELEASE" ]; do sleep 0.1; done\nexit 1\n', newline='\n')
            ready, release = tmp / 'ready', tmp / 'release'
            env = {k: v for k, v in os.environ.items() if not k.startswith(('GATE_', 'BOUNDARY_'))}
            env.update(GATE_TEST_BUILD=build.as_posix(), READY=ready.as_posix(), RELEASE=release.as_posix())
            proc = subprocess.Popen(['sh', 'scripts/check.sh', '--self-test'], cwd=project, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 30
                while not ready.exists():
                    self.assertIsNone(proc.poll(), 'self-test ended before starting its build')
                    self.assertLess(time.monotonic(), deadline, 'baseline build never started')
                    time.sleep(0.1)
                marker = ready.read_text().split()
                # Before the fix the Windows marker is only a token: find the self-test shell
                # (the holder's direct child) through the same native process enumeration.
                if os.name == 'nt':
                    # Kill the wrapper too: otherwise it clears the token when the shell ends.
                    for victim in fixture.lock_holder(proc.pid):
                        fixture.kill_process(victim)
                    proc.wait(timeout=15)
                else:
                    import signal
                    os.kill(int(marker[0]), signal.SIGKILL)
                    # Left unreaped, as under $(...) while the build holds the pipe: a zombie,
                    # which kill -0 still finds.
                    deadline = time.monotonic() + 15
                    while not subprocess.run(['ps', '-o', 'stat=', '-p', marker[0]], capture_output=True,
                                             text=True).stdout.strip().startswith('Z'):
                        self.assertLess(time.monotonic(), deadline, 'the killed self-test never became a zombie')
                        time.sleep(0.1)
                result = subprocess.run(['sh', str(hook)], cwd=project, env=dict(env, GATE_LOCK_WAIT='1'),
                                        input='{}', capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('GATE DID NOT RUN', result.stderr)
                self.assertNotIn('skipping the gate', result.stderr)
            finally:
                release.touch()
                proc.wait(timeout=30)
                # Wait for the inherited lock to close before deleting the fixture.
                subprocess.run(['sh', 'scripts/check.sh'], cwd=project,
                               env=dict(env, GATE_LOCK_WAIT='10'), capture_output=True, timeout=30)

    def test_file_names_alone_never_skip_the_gate(self):
        # A fresh `.selftest.*` (a tool's log) skipped a red gate; a tracked `.selftest.yml`
        # with an old mtime blocked every Stop as "GATE DID NOT RUN", and touched, skipped it.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, 'echo ran > gate-ran\nexit 1\n')
            (root / 'docs').mkdir()
            (root / 'docs/.selftest.log').write_text('log\n', newline='\n')
            tracked = root / '.selftest.yml'
            tracked.write_text('tracked: yes\n', newline='\n')
            subprocess.run(['git', 'add', '.selftest.yml'], cwd=root, check=True)
            for when in ((1, 1), None):
                with self.subTest(mtime=when):
                    os.utime(tracked, when)
                    result = stop(hook, root)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn('GATE FAILED', result.stderr)
                    self.assertNotIn('DID NOT RUN', result.stderr)
                    self.assertTrue((root / 'gate-ran').exists())
                    (root / 'gate-ran').unlink()

    def test_only_a_live_self_test_marker_skips_the_gate(self):
        # The stub gate says 75 while `held` exists, as check.sh does when GATE_LOCK_WAIT runs out.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, 'echo "$GATE_LOCK_WAIT" > gate-wait\n[ ! -f held ] || exit 75\nexit 1\n')
            live = subprocess.Popen(['sh', '-c', 'echo $$; read answer'], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, text=True)
            self.addCleanup(live.wait)
            self.addCleanup(live.communicate, '\n')
            pid = live.stdout.readline().strip()
            for lock, marker, held, code, said, wait in (
                    ('1234', pid + ' 1234\n', True, 0, 'NOTE [Stop hook]: skipping the gate', '0'),
                    # A killed self-test's marker, the lock free: the gate runs at once.
                    ('1234', pid + ' 1234\n', False, 2, 'GATE FAILED', '0'),
                    # Another gate holds the lock and rewrote it: the old marker is not believed.
                    ('5678', pid + ' 1234\n', True, 2, 'GATE DID NOT RUN', '500'),
                    ('1234', '1234', True, 2, 'GATE DID NOT RUN', '500'),
                    ('1234', '0 1234\n', True, 2, 'GATE DID NOT RUN', '500'),
                    ('1234', '00 1234\n', True, 2, 'GATE DID NOT RUN', '500'),
                    ('', '', True, 2, 'GATE DID NOT RUN', '500')):
                with self.subTest(lock=lock, marker=marker, held=held):
                    (root / '.git/check.lock').write_text(lock, newline='\n')
                    (root / '.git/check-selftest').write_text(marker, newline='\n')
                    if held:
                        (root / 'held').write_text('', newline='\n')
                    result = stop(hook, root)
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertIn(said, result.stderr)
                    self.assertEqual((root / 'gate-wait').read_text().strip(), wait)
                    if held:
                        (root / 'held').unlink()

    def test_a_zombie_self_test_shell_does_not_skip(self):
        # A killed self-test shell its parent has not reaped is a zombie, which kill -0 still
        # finds; ps names that state (a stub here, answering as Linux and macOS do).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, '[ ! -f held ] || exit 75\nexit 1\n')
            live = subprocess.Popen(['sh', '-c', 'echo $$; read answer'], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, text=True)
            self.addCleanup(live.wait)
            self.addCleanup(live.communicate, '\n')
            (root / '.git/check.lock').write_text('1234', newline='\n')
            (root / '.git/check-selftest').write_text(live.stdout.readline().strip() + ' 1234\n', newline='\n')
            (root / 'held').write_text('', newline='\n')
            shim = root / 'bin'
            shim.mkdir()
            (shim / 'ps').write_text('#!/bin/sh\necho "Z+"\n', newline='\n')
            (shim / 'ps').chmod(0o755)
            result = subprocess.run(['sh', str(hook)], cwd=root, input='{}', text=True, capture_output=True,
                                    timeout=60, env=dict(os.environ, GATE_LOCK_WAIT='1',
                                                         PATH=str(shim) + os.pathsep + os.environ['PATH']))
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('GATE DID NOT RUN', result.stderr)

    def test_the_gate_self_test_marks_itself_live_for_the_hook(self):
        # The real check.sh: its self-test's baseline build runs the hook, as a Stop in this
        # checkout would while the self-test holds the lock; the marker is gone once it ends.
        spec = importlib.util.spec_from_file_location('check_gate', ROOT / 'tests' /
                                                     ('test_check_gate_windows.py' if os.name == 'nt'
                                                      else 'test_check_gate.py'))
        check_gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check_gate)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            project = tmp / 'project'
            check_gate.make_project(project)
            (project / 'src').mkdir()
            (project / 'src/app.py').write_text('x = 1\n', newline='\n')
            subprocess.run(['git', 'add', 'src/app.py'], cwd=project, check=True)
            hook = tmp / 'hook.sh'
            hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                            .replace('{{GATED_FILE_PATTERN}}', r'\.py$'), newline='\n')
            out, rc = tmp / 'hook.out', tmp / 'hook.rc'
            build = tmp / 'build.sh'
            # The hook gets a short wait: without the marker it would wait for the self-test,
            # which waits for this build. The lock variables are the build's, never a Stop's.
            build.write_text(
                '[ -f .git/check-selftest ] || exit 0\n'
                '(unset GATE_LOCK_HELD GATE_LOCK_FD GATE_SELFTEST_NESTED; echo "{}" |'
                ' GATE_LOCK_WAIT=3 sh %s > %s 2>&1; echo $? > %s)\nexit 1\n'
                % (shlex.quote(hook.as_posix()), shlex.quote(out.as_posix()), shlex.quote(rc.as_posix())), newline='\n')
            env = dict({k: v for k, v in os.environ.items() if not k.startswith(('GATE_', 'BOUNDARY_'))},
                       GATE_TEST_BUILD=build.as_posix())
            result = subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=project, env=env,
                                    text=True, capture_output=True, timeout=300)
            self.assertIn('SELF-TEST INCONCLUSIVE', result.stdout, result.stdout + result.stderr)
            self.assertEqual(rc.read_text().strip(), '0', out.read_text())
            self.assertIn('NOTE [Stop hook]: skipping the gate', out.read_text())
            self.assertFalse((project / '.git/check-selftest').exists())

    def test_ungated_turn_does_not_look_for_a_self_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            (root / 'src').mkdir()
            (root / 'src/app.py').write_text('dirty\n', newline='\n')
            hook = root / 'hook.sh'
            hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                            .replace('{{GATED_FILE_PATTERN}}', r'\.c$'), newline='\n')
            shim = root / 'bin'
            shim.mkdir()
            (shim / 'git').write_text('#!/bin/sh\ncase " $* " in *" --git-path "*) echo looked > looked ;; esac\n'
                                      'exec %s "$@"\n' % shlex.quote(shutil.which('git')), newline='\n')
            (shim / 'git').chmod(0o755)
            result = subprocess.run(['sh', str(hook)], cwd=root, input='{}', text=True,
                                    capture_output=True, timeout=30,
                                    env=dict(os.environ, PATH=str(shim) + os.pathsep + os.environ['PATH']))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / 'looked').exists())

    def test_a_cd_into_another_checkout_still_gates_the_session_project(self):
        # Claude Code runs a hook in the current directory, which follows a `cd`: a lead that
        # cd'd into a clean worker worktree finished its turn with its own red change ungated.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, 'echo ran > gate-ran\nexit 1\n')
            worker = root / '.claude/worktrees/w1'
            worker.mkdir(parents=True)
            subprocess.run(['git', 'init', '-q', str(worker)], check=True)
            result = subprocess.run(['sh', str(hook)], cwd=worker, input='{}', text=True,
                                    capture_output=True, timeout=60,
                                    env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)))
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('GATE FAILED', result.stderr)
            self.assertTrue((root / 'gate-ran').exists())

    def test_worker_and_ignored_sentinels_do_not_skip_the_leads_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            (root / '.gitignore').write_text('node_modules/\n', newline='\n')
            worker = root / '.claude/worktrees/w1'
            worker.mkdir(parents=True)
            subprocess.run(['git', 'init', '-q', str(worker)], check=True)
            (root / 'scripts').mkdir()
            (root / 'scripts/check.sh').write_text('#!/bin/sh\necho ran > gate-ran\nexit 1\n', newline='\n')
            (root / 'scripts/check.sh').chmod(0o755)
            hook = root / 'hook.sh'
            hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                            .replace('{{GATED_FILE_PATTERN}}', r'\.py$'), newline='\n')
            (root / 'src').mkdir()
            (root / 'src/app.py').write_text('dirty\n', newline='\n')
            subprocess.run(['git', 'add', 'src/app.py'], cwd=root, check=True)
            for name in ('.claude/worktrees/w1/src/.selftest.py',
                         '.claude/worktrees/w1/CMakeLists.txt.selftest-backup',
                         'node_modules/pkg/.selftest.js'):
                with self.subTest(sentinel=name):
                    sentinel = root / name
                    sentinel.parent.mkdir(parents=True, exist_ok=True)
                    sentinel.write_text('injection\n', newline='\n')
                    result = subprocess.run(['sh', str(hook)], cwd=root, input='{}', text=True,
                                            capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertTrue((root / 'gate-ran').exists())
                    (root / 'gate-ran').unlink()
                    sentinel.unlink()

    def test_pass_fail_and_not_run_each_reach_the_agent(self):
        # 75 is "the gate did not run": blocking, and never reported as a pass or a failure.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = root / 'gate_on_stop.sh'
            hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                            .replace('{{GATED_FILE_PATTERN}}', r'\.py$'), newline='\n')
            (root / 'scripts').mkdir()
            gate = root / 'scripts/check.sh'
            # A 150-line build tail before the last line: the hook once fed back only the last
            # 20 lines, so the agent never saw where a build failure started.
            gate.write_text('#!/bin/sh\necho "first line of the gate output"\n'
                            'i=0; while [ $i -lt 150 ]; do echo "build line $i"; i=$((i + 1)); done\n'
                            'echo "gate output, exit $STUB_RC"\nexit "$STUB_RC"\n', newline='\n')
            gate.chmod(0o755)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            (root / 'src').mkdir()
            (root / 'src/app.py').write_text('dirty\n', newline='\n')
            subprocess.run(['git', 'add', 'src/app.py'], cwd=root, check=True)  # a gated change
            for rc, code, said, unsaid in ((0, 0, None, 'GATE'), (1, 2, 'GATE FAILED', 'DID NOT RUN'),
                                           (75, 2, 'GATE DID NOT RUN', 'GATE FAILED')):
                with self.subTest(rc=rc):
                    result = subprocess.run(['sh', str(hook)], cwd=root, input='{}', text=True,
                                            capture_output=True, timeout=30,
                                            env=dict(os.environ, STUB_RC=str(rc)))
                    self.assertEqual(result.returncode, code, result.stderr)
                    if said:
                        self.assertIn(said, result.stderr)
                        self.assertIn('gate output, exit %d' % rc, result.stderr)
                        self.assertIn('first line of the gate output', result.stderr)
                        self.assertIn('build line 0\n', result.stderr)
                    else:
                        self.assertEqual(result.stdout + result.stderr, '')
                    self.assertNotIn(unsaid, result.stderr)
            # A turn the hook already continued is let go, or the session loops forever.
            result = subprocess.run(['sh', str(hook)], cwd=root, input='{"stop_hook_active": true}',
                                    text=True, capture_output=True, timeout=30,
                                    env=dict(os.environ, STUB_RC='1'))
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
