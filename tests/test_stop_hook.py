"""The Stop hook must carry each gate outcome out as its own exit code and diagnostic."""
import importlib.util
import os
import shlex
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'overlays/claude-code/files/.claude/hooks/gate_on_stop.sh'


def gated_repo(root, gate_body):
    """A repository with a staged gated change, a stub gate and the hook at root/hook.sh."""
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    (root / 'scripts').mkdir()
    (root / 'scripts/check.sh').write_text('#!/bin/sh\n' + gate_body)
    (root / 'scripts/check.sh').chmod(0o755)
    (root / 'src').mkdir()
    (root / 'src/app.py').write_text('dirty\n')
    subprocess.run(['git', 'add', 'src/app.py'], cwd=root, check=True)
    hook = root / 'hook.sh'
    hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                    .replace('{{GATED_FILE_PATTERN}}', r'\.py$'))
    return hook


def stop(hook, root):
    return subprocess.run(['sh', str(hook)], cwd=root, input='{}', text=True, capture_output=True,
                          timeout=60)


class StopHookTests(unittest.TestCase):
    def test_file_names_alone_never_skip_the_gate(self):
        # A fresh `.selftest.*` (a tool's log) skipped a red gate; a tracked `.selftest.yml`
        # with an old mtime blocked every Stop as "GATE DID NOT RUN", and touched, skipped it.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hook = gated_repo(root, 'echo ran > gate-ran\nexit 1\n')
            (root / 'docs').mkdir()
            (root / 'docs/.selftest.log').write_text('log\n')
            tracked = root / '.selftest.yml'
            tracked.write_text('tracked: yes\n')
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
            for lock, marker, held, code, said, wait in (
                    ('1234', '1234', True, 0, 'NOTE [Stop hook]: skipping the gate', '0'),
                    # A killed self-test's marker, the lock free: the gate runs at once.
                    ('1234', '1234', False, 2, 'GATE FAILED', '0'),
                    # Another gate holds the lock and rewrote it: the old marker is not believed.
                    ('5678', '1234', True, 2, 'GATE DID NOT RUN', '500'),
                    ('', '', True, 2, 'GATE DID NOT RUN', '500')):
                with self.subTest(lock=lock, marker=marker, held=held):
                    (root / '.git/check.lock').write_text(lock)
                    (root / '.git/check-selftest').write_text(marker)
                    if held:
                        (root / 'held').write_text('')
                    result = stop(hook, root)
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertIn(said, result.stderr)
                    self.assertEqual((root / 'gate-wait').read_text().strip(), wait)
                    if held:
                        (root / 'held').unlink()

    def test_the_gate_self_test_marks_itself_live_for_the_hook(self):
        # The real check.sh: its self-test's baseline build runs the hook, as a Stop in this
        # checkout would while the self-test holds the lock; the marker is gone once it ends.
        spec = importlib.util.spec_from_file_location('check_gate', ROOT / 'tests/test_check_gate.py')
        check_gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check_gate)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            project = tmp / 'project'
            check_gate.make_project(project)
            (project / 'src').mkdir()
            (project / 'src/app.py').write_text('x = 1\n')
            subprocess.run(['git', 'add', 'src/app.py'], cwd=project, check=True)
            hook = tmp / 'hook.sh'
            hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                            .replace('{{GATED_FILE_PATTERN}}', r'\.py$'))
            out, rc = tmp / 'hook.out', tmp / 'hook.rc'
            build = tmp / 'build.sh'
            # The hook gets a short wait: without the marker it would wait for the self-test,
            # which waits for this build. The lock variables are the build's, never a Stop's.
            build.write_text(
                '[ -f .git/check-selftest ] || exit 0\n'
                '(unset GATE_LOCK_HELD GATE_LOCK_FD GATE_SELFTEST_NESTED; echo "{}" |'
                ' GATE_LOCK_WAIT=3 sh %s > %s 2>&1; echo $? > %s)\nexit 1\n'
                % (shlex.quote(hook.as_posix()), shlex.quote(out.as_posix()), shlex.quote(rc.as_posix())))
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
            (root / 'src/app.py').write_text('dirty\n')
            hook = root / 'hook.sh'
            hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                            .replace('{{GATED_FILE_PATTERN}}', r'\.c$'))
            shim = root / 'bin'
            shim.mkdir()
            (shim / 'git').write_text('#!/bin/sh\ncase " $* " in *" --git-path "*) echo looked > looked ;; esac\n'
                                      'exec %s "$@"\n' % shlex.quote(shutil.which('git')))
            (shim / 'git').chmod(0o755)
            result = subprocess.run(['sh', str(hook)], cwd=root, input='{}', text=True,
                                    capture_output=True, timeout=30,
                                    env=dict(os.environ, PATH=str(shim) + os.pathsep + os.environ['PATH']))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / 'looked').exists())

    def test_worker_and_ignored_sentinels_do_not_skip_the_leads_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            (root / '.gitignore').write_text('node_modules/\n')
            worker = root / '.claude/worktrees/w1'
            worker.mkdir(parents=True)
            subprocess.run(['git', 'init', '-q', str(worker)], check=True)
            (root / 'scripts').mkdir()
            (root / 'scripts/check.sh').write_text('#!/bin/sh\necho ran > gate-ran\nexit 1\n')
            (root / 'scripts/check.sh').chmod(0o755)
            hook = root / 'hook.sh'
            hook.write_text(HOOK.read_text().replace('{{GATED_PATHS}}', 'src')
                            .replace('{{GATED_FILE_PATTERN}}', r'\.py$'))
            (root / 'src').mkdir()
            (root / 'src/app.py').write_text('dirty\n')
            subprocess.run(['git', 'add', 'src/app.py'], cwd=root, check=True)
            for name in ('.claude/worktrees/w1/src/.selftest.py',
                         '.claude/worktrees/w1/CMakeLists.txt.selftest-backup',
                         'node_modules/pkg/.selftest.js'):
                with self.subTest(sentinel=name):
                    sentinel = root / name
                    sentinel.parent.mkdir(parents=True, exist_ok=True)
                    sentinel.write_text('injection\n')
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
                            .replace('{{GATED_FILE_PATTERN}}', r'\.py$'))
            (root / 'scripts').mkdir()
            gate = root / 'scripts/check.sh'
            # A 150-line build tail before the last line: the hook once fed back only the last
            # 20 lines, so the agent never saw where a build failure started.
            gate.write_text('#!/bin/sh\necho "first line of the gate output"\n'
                            'i=0; while [ $i -lt 150 ]; do echo "build line $i"; i=$((i + 1)); done\n'
                            'echo "gate output, exit $STUB_RC"\nexit "$STUB_RC"\n')
            gate.chmod(0o755)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            (root / 'src').mkdir()
            (root / 'src/app.py').write_text('dirty\n')
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
