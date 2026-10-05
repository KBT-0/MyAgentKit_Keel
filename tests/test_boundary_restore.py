"""Interrupt the shipped existing-file example: the checkout is never the one it changes."""
import os
import shlex
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

# Seconds any wait here may take; MYAGENTKIT_TEST_TIMEOUT_SCALE multiplies it on a slow host.
DEADLINE = 30 * float(os.environ.get('MYAGENTKIT_TEST_TIMEOUT_SCALE', '1'))


def alive(pid):
    # ps, not kill -0: a killed child not yet reaped is a zombie, and kill -0 still finds it.
    state = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
    return state.returncode == 0 and not state.stdout.strip().startswith('Z')


class BoundaryRestoreTests(unittest.TestCase):
    def setUp(self):
        # A caller that ignores SIGINT (a `&` job of a non-interactive shell, nohup) passes that
        # on to every child, an ignored signal cannot be trapped, and the interrupted cases
        # failed only there. Each test starts from Python's own default, its children from SIG_DFL.
        self.addCleanup(signal.signal, signal.SIGINT, signal.signal(signal.SIGINT, signal.default_int_handler))

    def test_existing_file_example_runs_in_a_disposable_copy(self):
        # The example once overwrote the file in the checkout and restored it from traps:
        # a concurrent `git add -A` staged the injection, and SIGKILL left it there.
        template = (Path(__file__).resolve().parents[1] /
                    'core/scripts/boundary_selftests.sh').read_text()
        example = '\n'.join(line[4:] for line in template.splitlines() if line.startswith('# | '))
        self.assertTrue(example.strip(), 'missing executable existing-file example')
        # The copied gate sees only what probe_env names: a gate that needs more names it there.
        example = example.replace('LC_ALL=C ', 'LC_ALL=C READY="$READY" INTERRUPT="$INTERRUPT" ', 1)
        self.assertIn('INTERRUPT="$INTERRUPT"', example)
        for interruption in (None, signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
            with self.subTest(interruption=interruption), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / 'project'
                source = root / 'src/domain/existing.py'
                source.parent.mkdir(parents=True)
                source.write_bytes(b'committed original\n')
                (root / 'scripts').mkdir()
                gate = root / 'scripts/check.sh'
                gate.write_text('''#!/bin/sh
cd "$(dirname "$0")/.."
if [ "${1:-}" = --self-test ]; then
  work=$(mktemp -d)
  trap 'rm -rf "$work"' EXIT INT TERM
  st_fail=0
''' + example + '''
  : > "$CONTINUED"
  exit "$st_fail"
fi
grep -q 'myapp.web' src/domain/existing.py || exit 0
if [ "$INTERRUPT" = yes ]; then
  : > "$READY"
  while :; do sleep 1; done
fi
echo 'FAIL [boundary]: the domain layer imports the web layer:'
exit 1
''')
                git = lambda *args: subprocess.run(['git', *args], cwd=root, check=True,
                                                   capture_output=True, text=True).stdout
                git('init', '-q')
                git('add', '.')
                git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
                    'commit', '-qm', 'fixture')
                original = b'Uncommitted owner content.\nPreserve these exact bytes.\n'
                source.write_bytes(original)
                source.chmod(0o640)
                status = git('status', '--porcelain')
                scratch, ready, continued = (Path(tmp) / name for name in ('scratch', 'ready', 'continued'))
                scratch.mkdir()
                child = subprocess.Popen(['sh', str(gate), '--self-test'], cwd=root,
                                         env=dict(os.environ, TMPDIR=str(scratch), READY=str(ready),
                                                  CONTINUED=str(continued),
                                                  INTERRUPT='yes' if interruption else 'no'),
                                         start_new_session=True, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True)
                try:
                    if interruption:
                        deadline = time.monotonic() + DEADLINE
                        while not ready.exists() and time.monotonic() < deadline:
                            if child.poll() is not None:
                                break
                            time.sleep(0.01)
                        if not ready.exists():
                            self.stop(child, 'injection did not reach the gate')
                        # Mid-injection, the checkout is untouched: the copy took the edit.
                        self.assertEqual(source.read_bytes(), original)
                        os.killpg(child.pid, interruption)
                    done = self.finish(child)
                    stdout, stderr = done.stdout, done.stderr
                    self.assertEqual(child.returncode,
                                     -interruption if interruption == signal.SIGKILL
                                     else 128 + interruption if interruption else 0,
                                     stdout + stderr)
                    self.assertEqual(source.read_bytes(), original)
                    self.assertEqual(source.stat().st_mode & 0o777, 0o640)
                    self.assertEqual(git('status', '--porcelain'), status)
                    # Traps remove the copy; only SIGKILL leaves it, in TMPDIR, not the checkout.
                    if interruption != signal.SIGKILL:
                        self.assertEqual(list(scratch.iterdir()), [])
                    self.assertEqual(continued.exists(), interruption is None)
                    # check.sh --self-test counts a boundary self-test as run only by this line.
                    if interruption is None:
                        self.assertIn('\n  ok   — ', '\n' + stdout)
                finally:
                    if child.returncode is None:
                        self.reap(child)

    def test_a_symlinked_parent_cannot_carry_the_probe_into_the_checkout(self):
        # cp -R keeps an absolute symlink as a symlink, so a `src` linked to the checkout's
        # own `lib` put the copy's mutation target back in the checkout, and the probe
        # overwrote it there. Checking only the target's last component missed it.
        template = (Path(__file__).resolve().parents[1] /
                    'core/scripts/boundary_selftests.sh').read_text()
        example = '\n'.join(line[4:] for line in template.splitlines() if line.startswith('# | '))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project'
            real = root / 'lib/domain/existing.py'
            real.parent.mkdir(parents=True)
            original = b'Uncommitted owner content.\n'
            real.write_bytes(original)
            (root / 'src').symlink_to(root / 'lib')
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            (root / 'scripts').mkdir()
            gate = root / 'scripts/check.sh'
            gate.write_text('#!/bin/sh\ncd "$(dirname "$0")/.."\n'
                            'if [ "${1:-}" = --self-test ]; then\n  st_fail=0\n' + example +
                            '\n  exit "$st_fail"\nfi\n'
                            "grep -q 'myapp.web' src/domain/existing.py || exit 0\n"
                            "echo 'FAIL [boundary]: the domain layer imports the web layer:'\nexit 1\n")
            scratch = Path(tmp) / 'scratch'
            scratch.mkdir()
            result = self.run_gate(['sh', str(gate), '--self-test'], root,
                                   dict(os.environ, TMPDIR=str(scratch)))
            self.assertEqual(real.read_bytes(), original, 'the probe wrote into the checkout')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('src is a symlink that leads out of the disposable copy', result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)


    def test_a_symlinked_gate_cannot_run_the_probe_against_the_checkout(self):
        # Only the gate's parent directories were resolved: an absolute symlink at
        # scripts/check.sh survived the copy, and a gate that resolves its own physical
        # location ran its build in the checkout instead of the copy.
        template = (Path(__file__).resolve().parents[1] /
                    'core/scripts/boundary_selftests.sh').read_text()
        example = '\n'.join(line[4:] for line in template.splitlines() if line.startswith('# | '))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project'
            source = root / 'src/domain/existing.py'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'committed original\n')
            (root / 'tools').mkdir()
            real = root / 'tools/check.sh'
            real.write_text('#!/bin/sh\n'
                            'cd "$(dirname "$(python3 -c \'import os,sys; print(os.path.realpath(sys.argv[1]))\' "$0")")/.."\n'
                            'if [ "${1:-}" = --self-test ]; then\n  st_fail=0\n' + example +
                            '\n  exit "$st_fail"\nfi\n'
                            ': > built-here\n'
                            "grep -q 'myapp.web' src/domain/existing.py || exit 0\n"
                            "echo 'FAIL [boundary]: the domain layer imports the web layer:'\nexit 1\n")
            (root / 'scripts').mkdir()
            (root / 'scripts/check.sh').symlink_to(real)
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            scratch = Path(tmp) / 'scratch'
            scratch.mkdir()
            result = self.run_gate(['sh', str(root / 'scripts/check.sh'), '--self-test'], root,
                                   dict(os.environ, TMPDIR=str(scratch)))
            self.assertFalse((root / 'built-here').exists(), 'the probe ran its gate in the checkout')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('is a symlink', result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)

    def fixture(self, tmp, gate_body, *init, names=(), config_keys=None):
        example = '\n'.join(line[4:] for line in (Path(__file__).resolve().parents[1] /
                            'core/scripts/boundary_selftests.sh').read_text().splitlines()
                            if line.startswith('# | '))
        if config_keys is not None:
            # A setting the gate reads is carried only when the project names it.
            self.assertIn('probe_config_keys=""', example)
            example = example.replace('probe_config_keys=""', 'probe_config_keys="%s"' % config_keys, 1)
        # SCRATCH, the test's own directory outside the copies, holds what a gate records.
        extra = ''.join('%s="$%s" ' % (name, name) for name in ('SCRATCH',) + tuple(names))
        self.assertIn('LC_ALL=C ', example)
        example = example.replace('LC_ALL=C ', 'LC_ALL=C ' + extra, 1)
        root = Path(tmp) / 'project'
        (root / 'src/domain').mkdir(parents=True)
        (root / 'src/domain/existing.py').write_bytes(b'committed original\n')
        (root / 'scripts').mkdir()
        (root / 'scripts/check.sh').write_text(
            '#!/bin/sh\ncd "$(dirname "$0")/.."\n'
            'if [ "${1:-}" = --self-test ]; then\n  st_fail=0\n' + example +
            '\n  exit "$st_fail"\nfi\n' + gate_body +
            "grep -q 'myapp.web' src/domain/existing.py || exit 0\n"
            "echo 'FAIL [boundary]: the domain layer imports the web layer:'\nexit 1\n")
        git = lambda *args: subprocess.run(['git', *args], cwd=root, check=True,
                                           capture_output=True, text=True).stdout
        git('init', '-q', *init)
        git('add', '.')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
        return root, git

    def test_a_tmpdir_inside_the_checkout_is_refused(self):
        # The copy goes into TMPDIR (GNU mktemp -d honoured it; the template now names it): set to
        # the checkout, the copy went into the working tree, and a SIGKILL left it there.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '')
            status = git('status', '--porcelain', '--ignored')
            result = self.run_gate(['sh', 'scripts/check.sh', '--self-test'], root,
                                   dict(os.environ, TMPDIR=str(root)))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('the disposable copy', result.stdout)
            self.assertIn('is inside the checkout', result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)
            self.assertEqual(git('status', '--porcelain', '--ignored'), status)

    def test_an_inherited_git_dir_cannot_point_the_copy_at_the_checkout(self):
        # cd into the copy kept an exported GIT_DIR and GIT_WORK_TREE: a gate that finds its
        # root through git built in the checkout while both path guards passed.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, ': > "$(git rev-parse --show-toplevel)/built-here"\n')
            scratch = Path(tmp) / 'scratch'
            scratch.mkdir()
            result = self.run_gate(['sh', 'scripts/check.sh', '--self-test'], root,
                                   dict(os.environ, TMPDIR=str(scratch), GIT_DIR=str(root / '.git'),
                                        GIT_WORK_TREE=str(root)))
            self.assertFalse((root / 'built-here').exists(), 'the copy\'s gate built in the checkout')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)

    def test_a_checkout_that_is_not_a_plain_repository_is_not_run(self):
        # A `.git` that is a file or a symlink names a git directory outside the copy: the copied
        # pointer staged the injection into the original's index, and rebuilding that repository
        # inside the copy took fourteen review rounds. Such a checkout is refused by name.
        for shape in ('linked worktree', 'separate git directory', 'symlinked .git'):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as tmp:
                root, git = self.fixture(tmp, 'git add src/domain/existing.py\n')
                checkout = root
                if shape == 'linked worktree':
                    checkout = Path(tmp) / 'linked'
                    git('worktree', 'add', '-q', str(checkout))
                elif shape == 'separate git directory':
                    git('init', '-q', '--separate-git-dir', str(Path(tmp) / 'gitdir'))
                else:
                    (root / '.git').rename(Path(tmp) / 'gitdir')
                    (root / '.git').symlink_to(Path(tmp) / 'gitdir')
                status = lambda: subprocess.run(['git', 'status', '--porcelain'], cwd=checkout, check=True,
                                                capture_output=True, text=True).stdout
                before = status()
                result = self.self_test(tmp, checkout)
                self.assertEqual(status(), before, 'the copy staged into the original index')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("NOT RUN — existing-file probe: the checkout's .git is not a directory", result.stdout)
                self.assertIn('this example supports a plain repository only', result.stdout)
                self.assertNotIn('  ok   — ', result.stdout)

    def test_cdpath_cannot_carry_the_probe_into_the_checkout(self):
        # With CDPATH=safe, `cd -P src/domain` went to the copy's safe/src/domain and passed the
        # guard, while the write to the relative src/domain/existing.py followed `src`, a
        # symlink to the checkout's lib, and overwrote owner content there.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '')
            real = root / 'lib/domain/existing.py'
            real.parent.mkdir(parents=True)
            original = b'Uncommitted owner content.\n'
            real.write_bytes(original)
            for path in (root / 'src/domain/existing.py', root / 'src/domain'):
                path.unlink() if path.is_file() else path.rmdir()
            (root / 'src').rmdir()
            (root / 'src').symlink_to(root / 'lib')
            (root / 'safe/src/domain').mkdir(parents=True)
            # An absolute CDPATH into the copy: bash prints a relative CDPATH match, which
            # failed the old guard by accident. A fixed mktemp gives the copy a known path.
            copy = os.path.realpath(tmp) + '/scratch/copy'
            shim = Path(tmp) / 'shim'
            shim.mkdir()
            (shim / 'mktemp').write_text('#!/bin/sh\nmkdir "%s" && echo "%s"\n' % (copy, copy))
            (shim / 'mktemp').chmod(0o755)
            (Path(tmp) / 'scratch').mkdir()
            result = self.run_gate(['sh', str(root / 'scripts/check.sh'), '--self-test'], root,
                                   dict(os.environ, CDPATH=copy + '/checkout/safe',
                                        PATH='%s%s%s' % (shim, os.pathsep, os.environ['PATH'])))
            self.assertEqual(real.read_bytes(), original, 'the probe wrote into the checkout')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('src is a symlink that leads out of the disposable copy', result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)

    def test_a_nested_linked_worktree_is_refused_by_name(self):
        # Only the top level got its own repository: a linked worktree nested at src/domain kept
        # its pointer to the original's administrative directory, and a gate that ran
        # `git -C src/domain add` staged the injection into the original nested index.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, 'git -C src/domain add existing.py\n')
            other = Path(tmp) / 'other'
            other.mkdir()
            run = lambda *args, cwd=other: subprocess.run(['git', *args], cwd=cwd, check=True,
                                                          capture_output=True, text=True).stdout
            run('init', '-q')
            (other / 'existing.py').write_bytes(b'committed original\n')
            run('add', '.')
            run('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
            git('rm', '-rq', 'src/domain')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'nested')
            run('worktree', 'add', '-q', str(root / 'src/domain'))
            nested = root / 'src/domain'
            before = run('status', '--porcelain', cwd=nested)
            scratch = Path(tmp) / 'scratch'
            scratch.mkdir()
            result = self.run_gate(['sh', 'scripts/check.sh', '--self-test'], root,
                                   dict(os.environ, TMPDIR=str(scratch)))
            self.assertEqual(run('status', '--porcelain', cwd=nested), before,
                             'the copy staged into the original nested index')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('the checkout contains a nested repository or worktree at src/domain;'
                          ' the existing-file probe does not support it', result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)

    def test_an_exported_object_directory_cannot_take_the_copy_s_writes(self):
        # GIT_OBJECT_DIRECTORY survived the unset of four variables: a copied gate's `git add`
        # wrote the injection's objects into the original's object store.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, 'git add src/domain/existing.py || exit 1\n')
            objects = root / '.git/objects'
            count = lambda: len(list(objects.glob('[0-9a-f][0-9a-f]/*')))  # loose objects only
            before = count()
            scratch = Path(tmp) / 'scratch'
            scratch.mkdir()
            result = self.run_gate(['sh', 'scripts/check.sh', '--self-test'], root,
                                   dict(os.environ, TMPDIR=str(scratch), GIT_OBJECT_DIRECTORY=str(objects)))
            self.assertEqual(count(), before, 'the copy wrote objects into the original')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)

    def self_test(self, tmp, cwd, **env):
        scratch = Path(tmp) / 'scratch'
        scratch.mkdir()
        return self.run_gate(['sh', 'scripts/check.sh', '--self-test'], cwd,
                             dict(os.environ, **{'TMPDIR': str(scratch), 'SCRATCH': str(scratch), **env}))

    def run_gate(self, args, cwd, env):
        # Its own process group: a timeout kills every process the example started, not only sh.
        return self.finish(subprocess.Popen(args, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, start_new_session=True))

    def finish(self, child, limit=DEADLINE):
        # Each child runs in its own process group, so a deadline kills all it started.
        try:
            stdout, stderr = child.communicate(timeout=limit)
        except subprocess.TimeoutExpired:
            self.stop(child, 'the child did not end', limit)
        return subprocess.CompletedProcess(child.args, child.returncode, stdout, stderr)

    def stop(self, child, what, limit=DEADLINE):
        # The output's tail tells a real hang (where it stopped) from a slow host (cut short).
        stdout, stderr = self.reap(child)
        self.fail('%s within %g s (exit %s)\n--- stdout tail\n%s\n--- stderr tail\n%s'
                  % (what, limit, child.returncode, stdout[-2000:], stderr[-2000:]))

    def reap(self, child):
        # Kill the group whatever the leader's state: an exited leader can leave a descendant
        # holding the pipes. The pgid is the one start_new_session made (child.pid); it names no
        # other group, since an unreaped leader holds that pid and a reaped one leaves it held
        # by its group while any member lives; once the group is empty the kill finds nothing.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            return child.communicate(timeout=5)
        except subprocess.TimeoutExpired as late:
            # A process that left the group still holds a pipe: report what came before it.
            for pipe in (child.stdout, child.stderr):
                pipe.close()
            child.wait(timeout=5)
            return ((late.output or b'').decode(errors='replace'),
                    (late.stderr or b'').decode(errors='replace')
                    + '\n(output incomplete: a pipe stayed open after the group was killed)')

    def test_a_deadline_ends_a_descendant_that_outlives_its_leader(self):
        # The leader exits at once; its background descendant keeps the pipes and sleeps on.
        # A deadline killed the group only while the leader ran, then waited for the pipes forever.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        mark = Path(tmp.name) / 'held'

        def end_fixture():
            # Whatever the code under test did, even when the probe ran out of time: the group
            # the fixture recorded itself is ended here, so no sleep outlives a failing run.
            try:
                os.killpg(int(mark.read_text().split()[0]), signal.SIGKILL)
            except (FileNotFoundError, ProcessLookupError):
                pass
        self.addCleanup(end_fixture)
        # The marker (the group's id, then the descendant's pid) is the fixture's readiness: it
        # is awaited with the scalable deadline, and only then runs the short deadline under test.
        fixture = 'sleep 120 & echo "$$ $!" >"$0.part" && mv "$0.part" "$0"'
        probe = ('import os, subprocess, sys, time, test_boundary_restore as t\n'
                 'child = subprocess.Popen(["sh", "-c", %r, sys.argv[1]], text=True,\n'
                 '                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)\n'
                 'ready = time.monotonic() + t.DEADLINE\n'
                 'while not os.path.exists(sys.argv[1]) and time.monotonic() < ready:\n'
                 '    time.sleep(0.05)\n'
                 'try:\n'
                 '    t.BoundaryRestoreTests("run").finish(child, 0.5)\n'
                 'except AssertionError as failure:\n'
                 '    print(failure)\n' % fixture)
        # The probe's own limit keeps a hang a failure here, not a stalled suite.
        result = subprocess.run([sys.executable, '-c', probe, str(mark)], cwd=Path(__file__).resolve().parent,
                                capture_output=True, text=True, timeout=2 * DEADLINE)
        self.assertTrue(mark.is_file(), 'the fixture never became ready\n' + result.stdout + result.stderr)
        self.assertIn('the child did not end within 0.5 s', result.stdout, result.stderr)
        held = int(mark.read_text().split()[1])
        deadline = time.monotonic() + DEADLINE
        while time.monotonic() < deadline:
            if not alive(held):
                return
            time.sleep(0.05)
        self.fail('the descendant %d outlived the deadline' % held)

    def test_nothing_the_baseline_run_leaves_reaches_the_second_run(self):
        # With one copy reused for both runs, three review rounds in a row found something the
        # baseline left that acted in the second run, and each re-check added after the baseline
        # was bypassed by the next: a hook in .git/hooks, a core.hooksPath to a hook, a
        # .git/config.worktree, a .git/commondir naming hooks outside, a symlink swapped in for
        # the target or the gate, a .pth file in HOME that the gate's own `python3 -c` ran, a
        # gate rewritten in place, and a .git/config linked to /dev/zero that hung the check.
        # The second run starts from a fresh copy: each passes, and nothing outside is written.
        hook = "printf '#!/bin/sh\\n: > {escaped}\\n' > {hook} && chmod +x {hook}"
        leaves = {
            'hook': hook.replace('{hook}', '.git/hooks/post-index-change'),
            'hooks path': 'git config core.hooksPath .githooks && mkdir .githooks && ' +
                          hook.replace('{hook}', '.githooks/post-index-change'),
            'unrelated key': 'git config kit.unrelated yes',
            'config.worktree': "printf '[kit]\\n\\tunrelated = yes\\n' > .git/config.worktree",
            'commondir': 'cp -R .git "$TMPDIR/common" && ' + hook.replace('{hook}', '"$TMPDIR/common/hooks/post-index-change"') +
                         ' && printf "%s\\n" "$TMPDIR/common" > .git/commondir',
            'target out': 'mv src/domain src/was && ln -s "$OUTSIDE" src/domain',
            'gate out': 'mv scripts/check.sh scripts/was.sh && ln -s "$OUTSIDE/gate.sh" scripts/check.sh',
            'target inside': 'mv src/domain src/was && ln -s was src/domain',
            'python startup file': 'site=$(python3 -c "import site; print(site.getusersitepackages())") && '
                                   'mkdir -p "$site" && printf "%s\\n" {pth} > "$site/probe.pth"',
            'gate rewritten': "printf '%s\\n' ': > {escaped}' \"echo 'FAIL [boundary]: the domain layer imports"
                              " the web layer:'\" 'exit 1' > scripts/new.sh && mv scripts/new.sh scripts/check.sh",
            'config linked to /dev/zero': 'rm .git/config && ln -s /dev/zero .git/config',
        }
        for name, leave in leaves.items():
            with self.subTest(leave=name), tempfile.TemporaryDirectory() as tmp:
                escaped, outside = Path(tmp) / 'escaped', Path(tmp) / 'outside'
                outside.mkdir()
                (outside / 'existing.py').write_text('committed original\n')
                (outside / 'gate.sh').write_text(': > %s\n' % shlex.quote(str(escaped)) +
                                                 "echo 'FAIL [boundary]: the domain layer imports the web layer:'\n"
                                                 'exit 1\n')
                leave = leave.replace('{escaped}', shlex.quote(str(escaped))).replace(
                    '{pth}', shlex.quote('import os; open(%r, "w")' % str(escaped)))
                # Like the kit's gate, every run starts python3; only the baseline leaves something.
                root, git = self.fixture(tmp, 'python3 -c pass || exit 1\n'
                                              "grep -q 'myapp.web' src/domain/existing.py || { %s || exit 1; exit 0; }\n"
                                              'git add -A || exit 1\n' % leave, names=('OUTSIDE',))
                status = git('status', '--porcelain')
                result = self.self_test(tmp, root, OUTSIDE=str(outside))
                self.assertFalse(escaped.exists(), 'something the baseline left ran in the second run')
                self.assertEqual((outside / 'existing.py').read_text(), 'committed original\n',
                                 'the injection followed a symlink the baseline left')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('  ok   — ', result.stdout)
                self.assertEqual(git('status', '--porcelain'), status)

    def test_any_symlink_leaving_the_copy_is_refused_by_name(self):
        # Only the target, the gate and the git storage were checked: cp -R kept an unrelated
        # `build -> <checkout>/out`, and a baseline gate writing build/output wrote into the checkout.
        for name, link in (('absolute', None), ('relative', '../outside')):
            with self.subTest(link=name), tempfile.TemporaryDirectory() as tmp:
                root, git = self.fixture(tmp, ': > build/output || exit 1\n')
                (root / 'out').mkdir()
                (root / 'build').symlink_to(link or root / 'out')
                result = self.self_test(tmp, root)
                self.assertFalse((root / 'out/output').exists(), 'the copy wrote into the checkout')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('NOT RUN — existing-file probe: build is a symlink that leads out of the disposable'
                              ' copy', result.stdout)
                self.assertNotIn('  ok   — ', result.stdout)

    def test_global_git_configuration_is_not_active_in_the_copy(self):
        # probe_env kept the real HOME: a global tar.<format>.command (or hooks path, filter,
        # fsmonitor) ran from a copied gate's `git archive` and wrote outside the copy.
        for config in ('.gitconfig', '.config/git/config'):
            with self.subTest(config=config), tempfile.TemporaryDirectory() as tmp:
                root, git = self.fixture(tmp, 'git archive --format=tar.gz HEAD >/dev/null || exit 1\n')
                escaped = Path(tmp) / 'escaped'
                home = Path(tmp) / 'home'
                (home / config).parent.mkdir(parents=True, exist_ok=True)
                (home / config).write_text('[tar "tar.gz"]\n\tcommand = : > %s; gzip -cn\n' % shlex.quote(str(escaped)))
                result = self.self_test(tmp, root, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'))
                self.assertFalse(escaped.exists(), 'a global archive command ran outside the copy')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('  ok   — ', result.stdout)

    def test_the_probe_requires_a_green_baseline_and_its_own_diagnostic(self):
        # Deleting the baseline run or the diagnostic match left every copy test green: the
        # probe must prove the gate rejects THIS injection, not that the gate fails somehow.
        diagnostic = "echo 'FAIL [boundary]: the domain layer imports the web layer:'"
        injected = 'grep -q myapp.web src/domain/existing.py && '
        cases = {'baseline red': (diagnostic + '; exit 1\n', 'the baseline is already red'),
                 'wrong reason': (injected + "{ echo 'FAIL: unrelated build error'; exit 1; }\n",
                                  "the injection did not produce the domain/web gate's failure"),
                 'misleading success': (injected + '{ %s; exit 0; }\n' % diagnostic,
                                        "the injection did not produce the domain/web gate's failure")}
        for name, (body, message) in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                root, git = self.fixture(tmp, body)
                result = self.self_test(tmp, root)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('FAIL — existing-file probe: ' + message, result.stdout)
                self.assertNotIn('  ok   — ', result.stdout)

    def test_a_symlinked_object_store_cannot_take_the_copy_s_writes(self):
        # The containment check validated the git and common directories, not what lies in
        # them: cp -R kept `.git/objects` as an absolute symlink to the original's store, and a
        # copied gate's `git add` wrote the injected blob there.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, 'git add src/domain/existing.py || exit 1\n')
            store = Path(tmp) / 'store'
            (root / '.git/objects').rename(store)
            (root / '.git/objects').symlink_to(store)
            count = lambda: len(list(store.glob('[0-9a-f][0-9a-f]/*')))  # loose objects only
            before = count()
            result = self.self_test(tmp, root)
            self.assertEqual(count(), before, 'the copy wrote objects into the original')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('.git/objects is a symlink that leads out of the disposable copy', result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)

    def test_a_symlink_beneath_a_directory_symlink_is_refused_by_name(self):
        # `.git/objects -> ../store` resolved inside the copy and passed, but find does not
        # descend through it: an absolute link beneath `store` took the copy's `git add` into
        # an object fanout outside the copy. The whole copy is walked, so `store` is too.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, 'git add src/domain/existing.py || exit 1\n')
            blob = subprocess.run(['git', 'hash-object', '--stdin'], cwd=root, input='from myapp.web import router\n',
                                  check=True, capture_output=True, text=True).stdout.strip()
            store = root / 'store'
            (root / '.git/objects').rename(store)
            (root / '.git/objects').symlink_to('../store')
            fanout = Path(tmp) / 'fanout' / blob[:2]
            fanout.parent.mkdir()
            if (store / blob[:2]).exists():
                (store / blob[:2]).rename(fanout)
            else:
                fanout.mkdir()
            (store / blob[:2]).symlink_to(fanout)
            before = len(list(fanout.iterdir()))
            result = self.self_test(tmp, root)
            self.assertEqual(len(list(fanout.iterdir())), before, 'the copy wrote objects outside the copy')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('store/%s is a symlink that leads out of the disposable copy' % blob[:2], result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)

    def test_a_file_symlink_out_of_git_storage_is_refused_by_name(self):
        # A file symlink stays allowed only while it resolves inside the copy.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '')
            outside = Path(tmp) / 'description'
            outside.write_text('outside\n')
            (root / '.git/description').unlink()
            (root / '.git/description').symlink_to(outside)
            result = self.self_test(tmp, root)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('.git/description is a symlink that leads out of the disposable copy', result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)

    def test_a_named_local_setting_is_carried(self):
        # Only an allowlist is carried: a gate that needs a locally configured setting names it.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '[ "$(git config --get kit.required)" = yes ] || exit 1\n',
                                     config_keys='kit.required')
            git('config', 'kit.required', 'yes')
            git('config', 'extensions.worktreeConfig', 'true')
            result = self.self_test(tmp, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)
            self.assertIn('NOTE — existing-file probe: extensions.worktreeconfig is not carried', result.stdout)

    def test_a_redirecting_configuration_key_is_not_carried(self):
        # The plain copy kept the original's .git/config verbatim, hooks path included.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '[ -z "$(git config --get core.hooksPath)" ] || exit 1\n')
            git('config', 'core.hooksPath', str(root / 'hooks'))
            result = self.self_test(tmp, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)
            self.assertIn('NOTE — existing-file probe: core.hookspath is not carried', result.stdout)

    def test_an_archive_command_is_not_carried(self):
        # The plain copy kept tar.<format>.command verbatim (a denylist had missed it before): a
        # copied gate's `git archive` ran it, and a command that writes elsewhere escaped the copy.
        with tempfile.TemporaryDirectory() as tmp:
            escaped = Path(tmp) / 'escaped'
            root, git = self.fixture(tmp, 'git archive --format=tar.gz HEAD >/dev/null || exit 1\n')
            git('config', 'tar.tar.gz.command', ': > %s; gzip -cn' % shlex.quote(str(escaped)))
            result = self.self_test(tmp, root)
            self.assertFalse(escaped.exists(), 'the archive command ran outside the copy')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)
            self.assertIn('NOTE — existing-file probe: tar.tar.gz.command is not carried', result.stdout)

    def test_the_original_s_hooks_do_not_run_in_the_copy(self):
        # cp -RP copied .git/hooks with the rest, and the rebuilt configuration leaves git's
        # default hooks directory: a copied gate's `git commit` ran the original's pre-commit,
        # and a hook that writes elsewhere escaped the copy.
        # A `git add` ran post-index-change the same way.
        with tempfile.TemporaryDirectory() as tmp:
            escaped = Path(tmp) / 'escaped'
            root, git = self.fixture(tmp, 'git add -A || exit 1\n'
                                          'git -c user.name=g -c user.email=g@example.invalid -c commit.gpgsign=false'
                                          ' commit -q --allow-empty -m probe >/dev/null 2>&1 || exit 1\n')
            for hook in ('pre-commit', 'post-commit', 'post-index-change'):
                (root / '.git/hooks' / hook).write_text('#!/bin/sh\n: > %s\n' % shlex.quote(str(escaped)))
                (root / '.git/hooks' / hook).chmod(0o755)
            result = self.self_test(tmp, root)
            self.assertFalse(escaped.exists(), "the original's hook ran in the copy")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)

    def test_the_cleanup_changes_no_mode_and_deletes_only_through_the_directory_it_made(self):
        # Source-level, because the races cannot be timed from a test: a folder's chmod could be
        # turned into a hard-linked checkout file's, and `rm -rf` after a separate root check
        # deleted a root swapped in between. The example now has neither operation.
        example = (Path(__file__).resolve().parents[1] / 'core/scripts/boundary_selftests.sh').read_text()
        code = [line[4:] for line in example.splitlines()
                if line.startswith('# | ') and not line[4:].lstrip().startswith('#')]
        self.assertTrue(code)
        for line in code:
            self.assertNotRegex(line, r'chmod|\brm\s+-[A-Za-z]*[rR]', 'the example changes a mode or deletes by path')

    def test_cleanup_changes_no_mode_of_a_hard_linked_checkout_file(self):
        # The cleanup ran `chmod -R u+rwx` on the copy before `rm -rf`: a hard link the baseline
        # made to a checkout file got that file's mode changed. Deleting the link changes nothing
        # of the file it shares.
        with tempfile.TemporaryDirectory() as tmp:
            # The checkout and TMPDIR share one filesystem by construction, so the hard link is made.
            root, git = self.fixture(tmp, "grep -q 'myapp.web' src/domain/existing.py || "
                                          'ln "$ORIGIN/src/domain/existing.py" hard || exit 1\n', names=('ORIGIN',))
            original = root / 'src/domain/existing.py'
            original.chmod(0o640)
            before = original.lstat()
            result = self.self_test(tmp, root, ORIGIN=str(root))
            after = original.lstat()
            self.assertEqual(after.st_mode, before.st_mode, 'the cleanup changed a checkout file')
            self.assertEqual((after.st_ino, after.st_nlink), (before.st_ino, before.st_nlink))
            self.assertEqual(original.read_bytes(), b'committed original\n')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)

    def test_a_replaced_temporary_root_is_refused_by_name(self):
        # chmod -R walked a symlinked root's target outside the copy; a root that is no longer the
        # directory mktemp made, a link or another directory with content, is left as it is.
        for shape, replace in (('symlink', 'ln -s "$OUTSIDE" "$copy"'),
                               ('directory', 'mkdir "$copy" && echo replacement > "$copy/kept"')):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as tmp:
                outside = Path(tmp) / 'outside'
                (outside / 'sub').mkdir(parents=True)
                (outside / 'kept').write_text('outside\n')
                (outside / 'kept').chmod(0o600)
                (outside / 'sub').chmod(0o500)
                modes = lambda: [(path.name, path.lstat().st_mode) for path in (outside, outside / 'kept', outside / 'sub')]
                before = modes()
                root, git = self.fixture(tmp, "grep -q 'myapp.web' src/domain/existing.py || { copy=$(dirname \"$(pwd -P)\") && "
                                              'mv "$copy" "$copy.moved" && %s; } || exit 1\n' % replace,
                                         names=('OUTSIDE',))
                try:
                    result = self.self_test(tmp, root, OUTSIDE=str(outside))
                    self.assertEqual(modes(), before, 'the cleanup changed a mode outside the copy')
                finally:
                    (outside / 'sub').chmod(0o700)
                self.assertEqual((outside / 'kept').read_text(), 'outside\n')
                if shape == 'directory':
                    self.assertEqual([path.read_text() for path in Path(tmp, 'scratch').glob('*/kept')],
                                     ['replacement\n'], 'the replacement was deleted')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('is no longer the directory made for the disposable copy', result.stdout)
                self.assertIn('deleted nothing', result.stdout)
                self.assertNotIn('  ok   — ', result.stdout)

    def test_a_checkout_changed_between_the_copies_is_not_run(self):
        # Each run copied the live checkout: a gate changed between the copies to always print
        # the diagnostic and fail passed the probe with no green baseline. Here the baseline
        # itself rewrites the checkout's gate, the simplest synchronised change.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, "grep -q 'myapp.web' src/domain/existing.py || { printf '%s\\n' "
                                          "\"echo 'FAIL [boundary]: the domain layer imports the web layer:'\" 'exit 1' "
                                          '> "$ORIGIN/scripts/new.sh" && mv "$ORIGIN/scripts/new.sh" "$ORIGIN/scripts/check.sh"; '
                                          '} || exit 1\n', names=('ORIGIN',))
            result = self.self_test(tmp, root, ORIGIN=str(root))
            self.assertNotIn('the domain layer', (root / 'scripts/check.sh').read_text().split('\n')[1],
                             'the gate was not rewritten')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('NOT RUN — existing-file probe: the checkout, or its git index, changed between the two copies;'
                          ' run the self-test again', result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)

    def test_the_carried_configuration_is_the_copy_s_own(self):
        # After the second copy was hashed, its carried settings were read again from the live
        # checkout: a setting changed in between made the injected run print the diagnostic on
        # its own, with both digests equal. A git wrapper changes the checkout's setting just
        # before the second copy's configuration is read; the copy's own, as hashed, is carried.
        with tempfile.TemporaryDirectory() as tmp:
            # The gate never sees the injection: only kit.mode=fail makes it print the diagnostic.
            root, git = self.fixture(tmp, '[ "$(git config kit.mode)" != fail ] || '
                                          "{ echo 'FAIL [boundary]: the domain layer imports the web layer:'; exit 1; }\n"
                                          'exit 0\n', config_keys='kit.mode')
            git('config', 'kit.mode', 'pass')
            shim, first, second = (Path(tmp) / name for name in ('shim', 'first', 'second'))
            shim.mkdir()
            real = shlex.quote(shutil.which('git'))
            (shim / 'git').write_text(
                '#!/bin/sh\ncase " $* " in *" --list -z "*)\n'
                '  if [ -e %s ]; then [ -e %s ] || { : > %s && %s --git-dir=%s config kit.mode fail; } || exit 1\n'
                '  else : > %s; fi ;;\nesac\nexec %s "$@"\n'
                % (shlex.quote(str(first)), shlex.quote(str(second)), shlex.quote(str(second)), real,
                   shlex.quote(str(root / '.git')), shlex.quote(str(first)), real))
            (shim / 'git').chmod(0o755)
            result = self.self_test(tmp, root, PATH='%s%s%s' % (shim, os.pathsep, os.environ['PATH']))
            self.assertTrue(second.exists(), 'the wrapper did not change the checkout')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("FAIL — existing-file probe: the injection did not produce the domain/web gate's failure",
                          result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)

    def test_a_permission_change_between_the_copies_is_not_run(self):
        # The digest kept only the owner-execute bit: a checkout file changed from 0644 to 0444
        # between the copies went unnoticed, and a gate choosing its policy by `[ -w policy ]`
        # could print the diagnostic on its own in the second run.
        for shape, change in (('file', 'chmod 444 "$ORIGIN/policy"'), ('directory', 'chmod 555 "$ORIGIN/rules"')):
            with self.subTest(shape=shape), tempfile.TemporaryDirectory() as tmp:
                root, git = self.fixture(tmp, "grep -q 'myapp.web' src/domain/existing.py || { %s || exit 1; }\n" % change,
                                         names=('ORIGIN',))
                (root / 'policy').write_text('policy\n')
                (root / 'policy').chmod(0o644)
                (root / 'rules').mkdir(0o755)
                try:
                    result = self.self_test(tmp, root, ORIGIN=str(root))
                finally:
                    (root / 'rules').chmod(0o755)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('NOT RUN — existing-file probe: the checkout, or its git index, changed between the two'
                              ' copies; run the self-test again', result.stdout)
                self.assertNotIn('  ok   — ', result.stdout)

    def test_a_special_file_in_the_checkout_is_refused_by_name(self):
        # The digest reads regular files only: a FIFO would block the read, a device has no end.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '')
            os.mkfifo(root / 'pipe')
            result = self.self_test(tmp, root)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('NOT RUN — existing-file probe: pipe is not a regular file, a folder or a symlink',
                          result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)

    def test_a_relative_tmpdir_names_one_place_for_both_copies(self):
        # The second copy was made after `cd /`, where TMPDIR=../scratch named another directory.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '')
            result = self.self_test(tmp, root, TMPDIR='../scratch')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)
            self.assertEqual(list(Path(tmp, 'scratch').iterdir()), [], 'a copy was left behind')

    def test_the_copies_go_into_tmpdir_where_mktemp_ignores_it(self):
        # macOS `mktemp -d` with no template ignores TMPDIR and uses the user temp folder: both
        # copies landed outside the folder checked against the checkout. This mktemp does the same.
        with tempfile.TemporaryDirectory() as tmp:
            elsewhere, shim = Path(tmp) / 'elsewhere', Path(tmp) / 'shim'
            elsewhere.mkdir()
            shim.mkdir()
            (shim / 'mktemp').write_text('#!/bin/sh\ncase "$*" in ""|-d) TMPDIR="%s"; export TMPDIR ;; esac\n'
                                         'exec "%s" "$@"\n' % (elsewhere, shutil.which('mktemp')))
            (shim / 'mktemp').chmod(0o755)
            root, git = self.fixture(tmp, "grep -q 'myapp.web' src/domain/existing.py || "
                                          'pwd -P >> "$SCRATCH/where" || exit 1\n')
            result = self.self_test(tmp, root, PATH='%s%s%s' % (shim, os.pathsep, os.environ['PATH']))
            self.assertEqual(os.listdir(elsewhere), [], 'a copy was made outside TMPDIR')
            where = (Path(tmp) / 'scratch/where').read_text().splitlines()
            self.assertTrue(where)
            for line in where:
                self.assertTrue(line.startswith(os.path.realpath(Path(tmp, 'scratch')) + '/'), line)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)

    def test_a_folder_the_baseline_hides_goes_with_its_copy(self):
        # os.walk skips a folder it cannot read: a baseline that hid an outside symlink in one
        # passed the audit run again on its copy, and the next run made it readable and wrote
        # through it. Now the next run gets a fresh copy. The example changes no mode, so a
        # mode-000 or mode-444 folder the baseline left keeps its copy, and the case fails by name.
        deep = 'd' * 200
        hide = {'too long': ('i=0; while [ $i -lt 25 ]; do mkdir %s && cd %s || exit 1; i=$((i + 1)); done; '
                             'ln -s "$OUTSIDE" out' % (deep, deep),
                             'i=0; while [ $i -lt 25 ]; do cd %s || exit 0; i=$((i + 1)); done; '
                             ': > out/escaped' % deep),
                'mode 000': ('mkdir hidden && ln -s "$OUTSIDE" hidden/out && chmod 000 hidden',
                             'chmod 755 hidden && : > hidden/out/escaped'),
                'mode 444': ('mkdir hidden && ln -s "$OUTSIDE" hidden/out && chmod 444 hidden',
                             'chmod 755 hidden && : > hidden/out/escaped')}
        for name, (make, use) in hide.items():
            with self.subTest(hide=name), tempfile.TemporaryDirectory() as tmp:
                outside = Path(tmp) / 'outside'
                outside.mkdir()
                root, git = self.fixture(tmp, "if grep -q 'myapp.web' src/domain/existing.py; then (%s) 2>/dev/null; "
                                              'else (%s) || exit 1; fi\n' % (use, make),
                                         names=('OUTSIDE',))
                try:
                    result = self.self_test(tmp, root, OUTSIDE=str(outside))
                finally:
                    for left in Path(tmp, 'scratch').glob('*/checkout/hidden'):
                        left.chmod(0o755)
                self.assertFalse((outside / 'escaped').exists(), 'the second run wrote through a hidden symlink')
                self.assertEqual(list(outside.iterdir()), [], 'the cleanup touched something outside the copy')
                if name == 'too long':
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('  ok   — ', result.stdout)
                    self.assertEqual(list(Path(tmp, 'scratch').iterdir()), [], 'a copy was left behind')
                else:
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('FAIL — existing-file probe: could not delete the disposable copy at %s/'
                                  % os.path.realpath(Path(tmp, 'scratch')), result.stdout)
                    self.assertIn('; delete it yourself', result.stdout)
                    self.assertNotIn('  ok   — ', result.stdout)

    def test_a_carried_setting_can_be_reassigned_in_the_copy(self):
        # Replayed on top of an existing core.filemode, the copy held two values, and a gate's
        # `git config core.filemode false` failed there while it succeeded in the original.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, 'git config core.filemode false || exit 1\n')
            self.assertEqual(len(git('config', '--get-all', 'core.filemode').splitlines()), 1)
            result = self.self_test(tmp, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)

    def test_a_local_setting_reads_and_writes_as_in_the_original(self):
        # A valueless key carried as the string `true` read differently in the copy, and a value
        # flattened from another file turned a gate's `git config <key> <value>` into exit 5.
        # A key from the repository's own config file reads, and takes a write, as in the original.
        for name, setting, write in (('single', '\trequired = no\n', ''),
                                     ('valueless', '\trequired\n', ''),
                                     ('empty', '\trequired =\n', ''),
                                     ('two values', '\trequired = one\n\trequired = two\n', '--replace-all')):
            observe = ('{ git config --get-all kit.required; echo "status $?"; '
                       'git config --bool --get kit.required; echo "status $?"; '
                       'git config %s kit.required yes; echo "status $?"; '
                       'git config --get-all kit.required; echo "status $?"; } 2>/dev/null' % write)
            with self.subTest(setting=name), tempfile.TemporaryDirectory() as tmp:
                # The copy's gate records what it saw on its first (baseline) run only.
                root, git = self.fixture(tmp, '[ -e "$SCRATCH/observed" ] || %s > "$SCRATCH/observed"\n' % observe,
                                         config_keys='kit.required')
                with open(root / '.git/config', 'a') as config:
                    config.write('[kit]\n' + setting)
                result = self.self_test(tmp, root)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('  ok   — ', result.stdout)
                original = subprocess.run(['sh', '-c', observe], cwd=root, capture_output=True,
                                          text=True).stdout
                self.assertEqual((Path(tmp) / 'scratch/observed').read_text(), original)

    def test_a_carried_setting_from_the_worktree_configuration_is_refused_by_name(self):
        # A worktree-only key was moved into the copy's local file: a gate's `git config
        # core.filemode false` left the original's effective value true (the worktree file wins)
        # but made the copy's false. Set in both scopes it became two values and the write failed.
        for scopes in ('both', 'worktree'):
            with self.subTest(scopes=scopes), tempfile.TemporaryDirectory() as tmp:
                root, git = self.fixture(tmp, ': > "$SCRATCH/gate-ran"\n')
                git('config', 'extensions.worktreeConfig', 'true')
                if scopes == 'worktree':
                    git('config', '--unset', 'core.filemode')
                git('config', '--worktree', 'core.filemode', 'true')
                result = self.self_test(tmp, root)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("core.filemode is set in file:.git/config.worktree, not in the repository's own"
                              " config file; set it there, or remove it from probe_config_keys", result.stdout)
                self.assertNotIn('  ok   — ', result.stdout)
                # Refused before the copy got a repository: no carry, no gate run, nothing to diverge.
                self.assertFalse((Path(tmp) / 'scratch/gate-ran').exists(), 'the copy ran its gate')

    def assert_include_not_run(self, result, key):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('NOT RUN — existing-file probe: %s includes git configuration, which this example cannot'
                      " reproduce; put the settings the gate reads into the repository's own config file, or"
                      ' keep the include and do not use the existing-file example' % key, result.stdout)
        self.assertNotIn('  ok   — ', result.stdout)

    def test_any_include_is_not_run_by_name(self):
        # Flattened into the copy's local file, an included key changed what a gate's write did:
        # one file included twice gave two local values, and `git config kit.required yes`, which
        # succeeds in the original, exited 5 in the copy. Not allowlisted, it was only noted, and a
        # setting the gate reads but the project forgot to name ran the copies without it.
        for times, keys in ((1, 'kit.required'), (2, 'kit.required'), (1, None)):
            with self.subTest(times=times, keys=keys), tempfile.TemporaryDirectory() as tmp:
                root, git = self.fixture(tmp, '! git config --get kit.required >/dev/null || exit 1\n',
                                         config_keys=keys)
                included = Path(tmp) / 'included'
                included.write_text('[kit]\n\trequired = yes\n')
                for _ in range(times):
                    git('config', '--add', 'include.path', str(included))
                self.assert_include_not_run(self.self_test(tmp, root), 'include.path')

    def test_a_checkout_specific_include_that_turns_the_gate_off_is_not_run(self):
        # Read in the relocated copy, an includeIf "gitdir:<checkout>/.git" matched only in the
        # checkout: its kit.disabled=yes turned the real gate off, both copies ran with the gate on,
        # and the negative test passed for a gate that never runs in the checkout.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '[ "$(git config kit.disabled)" != yes ] || exit 0\n',
                                     config_keys='kit.disabled')
            included = Path(tmp) / 'included'
            included.write_text('[kit]\n\tdisabled = yes\n')
            key = 'includeif.gitdir:%s/.git.path' % root.resolve()
            git('config', key, str(included))
            self.assertEqual(git('config', 'kit.disabled'), 'yes\n', 'the include is not active in the checkout')
            self.assert_include_not_run(self.self_test(tmp, root), key)

    def test_an_include_is_not_run_whatever_its_condition(self):
        # The class is refused, not the conditions that match: a condition false in the checkout
        # today (a branch not checked out) is true after a `git switch`, and the worktree file
        # includes as the local one does.
        for scope in ('local', 'worktree'):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as tmp:
                root, git = self.fixture(tmp, '')
                git('config', 'extensions.worktreeConfig', 'true')
                git('config', '--' + scope, 'includeIf.onbranch:never-checked-out.path', str(Path(tmp) / 'absent'))
                self.assert_include_not_run(self.self_test(tmp, root), 'includeif.onbranch:never-checked-out.path')

    def test_a_named_setting_from_outside_the_repository_is_not_run_by_name(self):
        # The copies run with no system or global git configuration: a global kit.disabled=yes
        # turned the real gate off, both copies ran it on, and the case printed ok.
        for scope in ('global', 'system', 'command'):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as tmp:
                root, git = self.fixture(tmp, '[ "$(git config kit.disabled)" != yes ] || exit 0\n',
                                         config_keys='kit.disabled')
                setting = Path(tmp) / 'setting'
                setting.write_text('[kit]\n\tdisabled = yes\n')
                env = {'global': {'GIT_CONFIG_GLOBAL': str(setting)},
                       'system': {'GIT_CONFIG_SYSTEM': str(setting)},
                       'command': {'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'kit.disabled',
                                   'GIT_CONFIG_VALUE_0': 'yes'}}[scope]
                result = self.self_test(tmp, root, **env)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('NOT RUN — existing-file probe: kit.disabled has a value in the %s scope of the'
                              ' git configuration; the copies run without system and global git configuration:'
                              " set kit.disabled in the repository's own config file, or do not use the"
                              ' existing-file example' % scope, result.stdout)
                self.assertNotIn('  ok   — ', result.stdout)

    def test_a_named_setting_set_only_in_the_repository_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '[ "$(git config kit.disabled)" = no ] || exit 1\n',
                                     config_keys='kit.disabled')
            git('config', 'kit.disabled', 'no')
            result = self.self_test(tmp, root, GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)


if __name__ == '__main__':
    unittest.main()
