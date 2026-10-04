"""Interrupt the shipped existing-file example: the checkout is never the one it changes."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


class BoundaryRestoreTests(unittest.TestCase):
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
            self.assertIn('resolves outside the disposable copy', result.stdout)
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
            scratch = Path(tmp) / 'scratch'
            scratch.mkdir()
            result = subprocess.run(['sh', str(root / 'scripts/check.sh'), '--self-test'], cwd=root,
                                    capture_output=True, text=True, timeout=30,
                                    env=dict(os.environ, TMPDIR=str(scratch)))
            self.assertFalse((root / 'built-here').exists(), 'the probe ran its gate in the checkout')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('is a symlink', result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)

    def fixture(self, tmp, gate_body, *init, names=()):
        example = '\n'.join(line[4:] for line in (Path(__file__).resolve().parents[1] /
                            'core/scripts/boundary_selftests.sh').read_text().splitlines()
                            if line.startswith('# | '))
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

    def test_a_linked_worktree_copy_cannot_stage_into_the_original_index(self):
        # cp -R copied a linked worktree's `.git` pointer file unchanged: git inside the copy
        # reported the copy as its top level but used the original's git directory, so a
        # gate that stages its inputs staged the injection into the original's index.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, 'git add src/domain/existing.py\n')
            linked = Path(tmp) / 'linked'
            git('worktree', 'add', '-q', str(linked))
            status = lambda: subprocess.run(['git', 'status', '--porcelain'], cwd=linked, check=True,
                                            capture_output=True, text=True).stdout
            before = status()
            scratch = Path(tmp) / 'scratch'
            scratch.mkdir()
            result = subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=linked,
                                    capture_output=True, text=True, timeout=30,
                                    env=dict(os.environ, TMPDIR=str(scratch)))
            self.assertEqual(status(), before, 'the copy staged into the original index')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)

    def test_a_linked_worktree_copy_keeps_head_history_and_index(self):
        # The copy's own repository was a fresh `git init`: a gate that needs HEAD, a tag or
        # the staged state passed in the linked worktree and failed the copy's baseline.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '[ "$(git rev-parse --verify HEAD)" = "$EXPECT_HEAD" ] || exit 1\n'
                                          'git describe --tags --exact-match >/dev/null 2>&1 || exit 1\n'
                                          '[ "$(git diff --cached --name-only)" = staged.txt ] || exit 1\n',
                                     names=('EXPECT_HEAD',))
            git('tag', 'v1')
            linked = Path(tmp) / 'linked'
            git('worktree', 'add', '-q', str(linked))
            (linked / 'staged.txt').write_text('staged only\n')
            subprocess.run(['git', 'add', 'staged.txt'], cwd=linked, check=True)
            head = git('rev-parse', 'HEAD').strip()
            scratch = Path(tmp) / 'scratch'
            scratch.mkdir()
            result = subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=linked,
                                    capture_output=True, text=True, timeout=30,
                                    env=dict(os.environ, TMPDIR=str(scratch), EXPECT_HEAD=head))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)

    def linked_self_test(self, tmp, git, **env):
        linked = Path(tmp) / 'linked'
        git('worktree', 'add', '-q', str(linked))
        (linked / 'staged.txt').write_text('staged only\n')
        subprocess.run(['git', 'add', 'staged.txt'], cwd=linked, check=True)
        scratch = Path(tmp) / 'scratch'
        scratch.mkdir()
        return linked, subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=linked,
                                      capture_output=True, text=True, timeout=30,
                                      env=dict(os.environ, TMPDIR=str(scratch), **env))

    def test_a_linked_worktree_copy_has_a_whole_index_under_split_index(self):
        # The copy took the linked worktree's index file alone: with core.splitIndex that file
        # names a shared index left in the original's git directory, the copy's index was
        # unreadable, and a gate that reads the index failed the copy's baseline.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, 'git ls-files -s >/dev/null || exit 1\n'
                                          '[ "$(git diff --cached --name-only)" = staged.txt ] || exit 1\n')
            git('config', 'core.splitIndex', 'true')
            linked, result = self.linked_self_test(tmp, git)
            gitdir = Path(subprocess.run(['git', 'rev-parse', '--absolute-git-dir'], cwd=linked, check=True,
                                         capture_output=True, text=True).stdout.strip())
            self.assertTrue(list(gitdir.glob('sharedindex.*')), 'the fixture wrote no split index')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)

    def test_a_linked_worktree_copy_keeps_a_sha256_object_format(self):
        # The copy was initialised in git's default format: a SHA-256 original's object IDs
        # could not be imported into a SHA-1 copy, and the probe refused a valid checkout.
        with tempfile.TemporaryDirectory() as tmp:
            try:
                root, git = self.fixture(tmp, '[ "$(git diff --cached --name-only)" = staged.txt ] || exit 1\n',
                                         '--object-format=sha256')
            except subprocess.CalledProcessError as error:
                sys.stderr.write('NOT RUN: this git cannot create a SHA-256 repository: %s\n'
                                 % (error.stderr or '').strip())
                self.skipTest('no SHA-256 repositories in this git')
            linked, result = self.linked_self_test(tmp, git, GIT_DEFAULT_HASH='sha1')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)

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
            self.assertIn('resolves outside the disposable copy', result.stdout)
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

    def test_a_failed_index_or_ref_read_is_refused_by_name(self):
        # The reconstruction piped the original's ls-files and for-each-ref into their
        # consumers: a failed producer gave an empty index or no refs, the later checks
        # still passed, and the probe ran against an incomplete snapshot.
        real_git = shutil.which('git')
        for producer, message in (('ls-files', "could not read the original's index (git ls-files)"),
                                  ('for-each-ref', "could not read the original's refs (git for-each-ref)")):
            with self.subTest(producer=producer), tempfile.TemporaryDirectory() as tmp:
                root, git = self.fixture(tmp, '')
                linked = Path(tmp) / 'linked'
                git('worktree', 'add', '-q', str(linked))
                shim = Path(tmp) / 'shim'
                shim.mkdir()
                (shim / 'git').write_text('#!/bin/sh\ncase " $* " in *" -C %s %s "*) exit 128 ;; esac\n'
                                          'exec %s "$@"\n' % (os.path.realpath(linked), producer, real_git))
                (shim / 'git').chmod(0o755)
                scratch = Path(tmp) / 'scratch'
                scratch.mkdir()
                result = subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=linked,
                                        capture_output=True, text=True, timeout=30,
                                        env=dict(os.environ, TMPDIR=str(scratch),
                                                 PATH='%s%s%s' % (shim, os.pathsep, os.environ['PATH'])))
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(message, result.stdout)
                self.assertNotIn('  ok   — ', result.stdout)

    def self_test(self, tmp, cwd, **env):
        scratch = Path(tmp) / 'scratch'
        scratch.mkdir()
        return subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=cwd, capture_output=True,
                              text=True, timeout=30, env=dict(os.environ, TMPDIR=str(scratch), **env))

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
            self.assertIn("the copy's git storage at .git/objects points outside the copy", result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)

    def test_a_linked_worktree_copy_keeps_the_local_configuration(self):
        # The copy's repository was a fresh `git init`: a gate that needs a locally configured
        # setting, in the repository's or the worktree's configuration, failed its baseline.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '[ "$(git config --get kit.required)" = yes ] || exit 1\n'
                                          '[ "$(git config --get kit.worktree)" = yes ] || exit 1\n')
            git('config', 'kit.required', 'yes')
            git('config', 'extensions.worktreeConfig', 'true')
            linked = Path(tmp) / 'linked'
            git('worktree', 'add', '-q', str(linked))
            subprocess.run(['git', 'config', '--worktree', 'kit.worktree', 'yes'], cwd=linked, check=True)
            result = self.self_test(tmp, linked)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)
            self.assertIn('NOTE — existing-file probe: extensions.worktreeconfig is not carried', result.stdout)

    def test_a_redirecting_configuration_key_is_not_carried(self):
        # Carrying the configuration must not carry a hooks path into the original.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '[ -z "$(git config --get core.hooksPath)" ] || exit 1\n')
            git('config', 'core.hooksPath', str(root / 'hooks'))
            linked, result = self.linked_self_test(tmp, git)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)
            self.assertIn('NOTE — existing-file probe: core.hookspath is not carried', result.stdout)

    def test_a_linked_worktree_copy_keeps_intent_to_add(self):
        # The index rebuilt from `ls-files -s` made an intent-to-add path an ordinary staged
        # empty blob: a gate checking the staged changes passed the original, failed the copy.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '[ "$(git diff --cached --name-only)" = "$EXPECT_CACHED" ] || exit 1\n',
                                     names=('EXPECT_CACHED',))
            linked = Path(tmp) / 'linked'
            git('worktree', 'add', '-q', str(linked))
            run = lambda *args: subprocess.run(['git', *args], cwd=linked, check=True,
                                               capture_output=True, text=True).stdout
            (linked / 'staged.txt').write_text('staged only\n')
            run('add', 'staged.txt')
            (linked / 'later.txt').write_text('intent to add\n')
            run('add', '-N', 'later.txt')
            expected = run('diff', '--cached', '--name-only').rstrip('\n')
            self.assertEqual(expected, 'staged.txt')
            result = self.self_test(tmp, linked, EXPECT_CACHED=expected)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  ok   — ', result.stdout)

    def test_an_unmerged_index_is_refused_by_name(self):
        # An index state the rebuild cannot reproduce faithfully is refused, not approximated.
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.fixture(tmp, '')
            ident = ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                     '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false']
            linked = Path(tmp) / 'linked'
            git('worktree', 'add', '-q', str(linked))
            (linked / 'src/domain/existing.py').write_text('linked side\n')
            subprocess.run(['git', *ident, 'commit', '-qam', 'linked'], cwd=linked, check=True)
            git('checkout', '-q', '-b', 'other')
            (root / 'src/domain/existing.py').write_text('other side\n')
            git(*ident, 'commit', '-qam', 'other')
            merge = subprocess.run(['git', *ident, 'merge', 'other'], cwd=linked, capture_output=True)
            self.assertNotEqual(merge.returncode, 0, 'the fixture merge did not conflict')
            result = self.self_test(tmp, linked)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('the original index has unmerged entries; the existing-file probe does not support them',
                          result.stdout)
            self.assertNotIn('  ok   — ', result.stdout)

if __name__ == '__main__':
    unittest.main()
