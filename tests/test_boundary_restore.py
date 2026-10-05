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
                                         stderr=subprocess.PIPE)
                try:
                    if interruption:
                        deadline = time.monotonic() + 5
                        while not ready.exists() and time.monotonic() < deadline:
                            if child.poll() is not None:
                                break
                            time.sleep(0.01)
                        self.assertTrue(ready.exists(), 'injection did not reach the gate')
                        # Mid-injection, the checkout is untouched: the copy took the edit.
                        self.assertEqual(source.read_bytes(), original)
                        os.killpg(child.pid, interruption)
                    stdout, stderr = child.communicate(timeout=5)
                    self.assertEqual(child.returncode,
                                     -interruption if interruption == signal.SIGKILL
                                     else 128 + interruption if interruption else 0,
                                     (stdout + stderr).decode(errors='replace'))
                    self.assertEqual(source.read_bytes(), original)
                    self.assertEqual(source.stat().st_mode & 0o777, 0o640)
                    self.assertEqual(git('status', '--porcelain'), status)
                    # Traps remove the copy; only SIGKILL leaves it, in TMPDIR, not the checkout.
                    if interruption != signal.SIGKILL:
                        self.assertEqual(list(scratch.iterdir()), [])
                    self.assertEqual(continued.exists(), interruption is None)
                    # check.sh --self-test counts a boundary self-test as run only by this line.
                    if interruption is None:
                        self.assertIn('\n  ok   — ', '\n' + stdout.decode())
                finally:
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGKILL)
                    child.communicate()

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
            result = subprocess.run(['sh', str(gate), '--self-test'], cwd=root, capture_output=True,
                                    text=True, timeout=30, env=dict(os.environ, TMPDIR=str(scratch)))
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
            result = subprocess.run(['sh', str(root / 'scripts/check.sh'), '--self-test'], cwd=root,
                                    capture_output=True, text=True, timeout=30,
                                    env=dict(os.environ, TMPDIR=str(scratch)))
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
        extra = ''.join('%s="$%s" ' % (name, name) for name in names)
        if extra:
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
        # mktemp -d honours TMPDIR: set to the checkout, the copy went into the working tree,
        # and a SIGKILL left it there.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '')
            status = git('status', '--porcelain', '--ignored')
            result = subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=root, capture_output=True,
                                    text=True, timeout=30, env=dict(os.environ, TMPDIR=str(root)))
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
            result = subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=root, capture_output=True,
                                    text=True, timeout=30,
                                    env=dict(os.environ, TMPDIR=str(scratch), GIT_DIR=str(root / '.git'),
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
            result = subprocess.run(['sh', str(root / 'scripts/check.sh'), '--self-test'], cwd=root,
                                    capture_output=True, text=True, timeout=30,
                                    env=dict(os.environ, CDPATH=copy + '/checkout/safe',
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
            result = subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=root, capture_output=True,
                                    text=True, timeout=30, env=dict(os.environ, TMPDIR=str(scratch)))
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
            result = subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=root, capture_output=True,
                                    text=True, timeout=30,
                                    env=dict(os.environ, TMPDIR=str(scratch), GIT_OBJECT_DIRECTORY=str(objects)))
            self.assertEqual(count(), before, 'the copy wrote objects into the original')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)

    def self_test(self, tmp, cwd, **env):
        scratch = Path(tmp) / 'scratch'
        scratch.mkdir()
        return subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=cwd, capture_output=True,
                              text=True, timeout=30, env=dict(os.environ, TMPDIR=str(scratch), **env))

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

    def test_a_baseline_that_swaps_in_a_symlink_is_refused_by_name(self):
        # The target and the gate were validated before the baseline gate ran: a baseline that
        # replaced src/domain or the gate with a symlink sent the injection, or the second run,
        # out of the copy.
        swaps = {'target out': ('mv src/domain src/was && ln -s "$OUTSIDE" src/domain',
                                'src/domain is a symlink that leads out of the disposable copy'),
                 'gate out': ('mv scripts/check.sh scripts/was.sh && ln -s "$OUTSIDE/gate.sh" scripts/check.sh',
                              'scripts/check.sh is a symlink that leads out of the disposable copy'),
                 'target inside': ('mv src/domain src/was && ln -s was src/domain',
                                   'src/domain/existing.py runs through a symlink at src/domain')}
        for name, (swap, message) in swaps.items():
            with self.subTest(swap=name), tempfile.TemporaryDirectory() as tmp:
                outside = Path(tmp) / 'outside'
                outside.mkdir()
                (outside / 'existing.py').write_text('committed original\n')
                (outside / 'gate.sh').write_text(': > "$OUTSIDE/ran"\n'
                                                 "echo 'FAIL [boundary]: the domain layer imports the web layer:'\n"
                                                 'exit 1\n')
                root, git = self.fixture(tmp, '[ -e "$TMPDIR/swapped" ] || { : > "$TMPDIR/swapped"; %s; }\n' % swap,
                                         names=('OUTSIDE',))
                result = self.self_test(tmp, root, OUTSIDE=str(outside))
                self.assertEqual((outside / 'existing.py').read_text(), 'committed original\n',
                                 'the injection followed the swapped symlink')
                self.assertFalse((outside / 'ran').exists(), 'the second run ran the swapped gate')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('NOT RUN — existing-file probe: ' + message, result.stdout)
                self.assertNotIn('  ok   — ', result.stdout)

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
                root, git = self.fixture(tmp, '[ -e "$TMPDIR/observed" ] || %s > "$TMPDIR/observed"\n' % observe,
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
                root, git = self.fixture(tmp, ': > "$TMPDIR/gate-ran"\n')
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

    def test_an_allowlisted_setting_from_an_include_is_refused_by_name(self):
        # Flattened into the copy's local file, an included key changed what a gate's write did:
        # one file included twice gave two local values, and `git config kit.required yes`, which
        # succeeds in the original, exited 5 in the copy. Not allowlisted, it is only noted.
        for times, keys in ((1, 'kit.required'), (2, 'kit.required'), (1, None)):
            with self.subTest(times=times, keys=keys), tempfile.TemporaryDirectory() as tmp:
                root, git = self.fixture(tmp, '! git config --get kit.required >/dev/null || exit 1\n',
                                         config_keys=keys)
                included = Path(tmp) / 'included'
                included.write_text('[kit]\n\trequired = yes\n')
                for _ in range(times):
                    git('config', '--add', 'include.path', str(included))
                result = self.self_test(tmp, root)
                if keys:
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("kit.required is set in file:%s, not in the repository's own config file;"
                                  " set it there, or remove it from probe_config_keys" % included, result.stdout)
                    self.assertNotIn('  ok   — ', result.stdout)
                else:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('  ok   — ', result.stdout)
                    self.assertIn('NOTE — existing-file probe: kit.required is not carried', result.stdout)
                    self.assertIn('NOTE — existing-file probe: include.path is not carried', result.stdout)


if __name__ == '__main__':
    unittest.main()
