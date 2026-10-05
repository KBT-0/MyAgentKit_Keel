"""The shipped check.sh in a minimal configured project: scan list, lock and re-execution."""
import fcntl
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Assembled, never literal: the kit's own files carry no unfilled marker.
MARKER = '{{' + 'GATE_TEST_MARKER}}'
GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid']


def make_project(path):
    """A project the gate passes: every marker filled, the build is $GATE_TEST_BUILD."""
    (path / 'scripts').mkdir(parents=True)
    (path / 'docs').mkdir()
    text = (ROOT / 'core/scripts/check.sh').read_text()
    text = text.replace('{{TOOLCHAIN_PATH_SETUP}}', '').replace('{{BUILD_TEST_COMMAND}}',
                                                                'sh $GATE_TEST_BUILD')
    (path / 'scripts/check.sh').write_text(re.sub(r'\{\{[A-Z0-9_]+\}\}', 'fixture', text))
    (path / 'scripts/boundary_checks.sh').write_text('# The fixture has no boundaries.\n')
    (path / 'docs/STATE.md').write_text('# STATE\n\n## Active work\n')
    (path / 'docs/PROJECT.md').write_text('# PROJECT\n\n## Contents\n')
    subprocess.run(['git', 'init', '-q', str(path)], check=True)


def gate(cwd, build, timeout=60, **extra):
    """Run the gate in its own session; on timeout kill the whole session and return None."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('GATE_', 'BOUNDARY_')) and k != 'CDPATH'}
    env.update(GATE_TEST_BUILD=str(build), **extra)
    proc = subprocess.Popen(['sh', 'scripts/check.sh'], cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True)
    try:
        out = proc.communicate(timeout=timeout)[0]
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        return None, proc.communicate()[0]
    return proc.returncode, out


class CheckGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / 'project'
        make_project(self.project)
        self.build = self.tmp / 'build.sh'
        self.build.write_text('true\n')
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 0, out)

    def test_a_symlink_is_never_followed(self):
        # Git tracks a symlink's link text, never its target. A link to an existing file
        # outside the tree was followed by grep: its lines leaked into the scan, and a link
        # to a FIFO hung the gate.
        outside = self.tmp / 'outside'
        outside.mkdir()
        (outside / 'secret.md').write_text('outside the tree: ' + MARKER + '\n')
        os.mkfifo(outside / 'fifo')
        (self.project / 'ext-file').symlink_to(outside / 'secret.md')
        (self.project / 'ext-fifo').symlink_to(outside / 'fifo')
        try:
            code, out = gate(self.project, self.build, timeout=30)
        finally:
            # A grep left blocked on the FIFO's open gets end-of-file and exits.
            try:
                os.close(os.open(outside / 'fifo', os.O_WRONLY | os.O_NONBLOCK))
            except OSError:
                pass
        self.assertIsNotNone(code, 'the gate followed a symlink to a FIFO and hung:\n' + out)
        self.assertEqual(code, 0, out)
        self.assertNotIn('outside the tree', out)

    def test_a_path_that_is_not_a_regular_file_is_named(self):
        # A tracked file replaced by a FIFO hung grep; replaced by a directory it ended in
        # "a scanner failed to run". Each fails under its own name instead.
        for name, make in (('was-file-now-fifo', os.mkfifo), ('was-file-now-dir', os.mkdir)):
            with self.subTest(name=name):
                path = self.project / name
                path.write_text('tracked\n')
                subprocess.run(['git', 'add', name], cwd=self.project, check=True)
                path.unlink()
                make(path)
                try:
                    code, out = gate(self.project, self.build, timeout=30)
                finally:
                    subprocess.run(['git', 'update-index', '--force-remove', name], cwd=self.project,
                                   check=True)
                    path.rmdir() if path.is_dir() else path.unlink()
                self.assertIsNotNone(code, 'the gate hung on ' + name + ':\n' + out)
                self.assertEqual(code, 1, out)
                self.assertIn('FAIL [scan]: ' + name + ' is not a regular file', out)
                self.assertNotIn('a scanner failed to run', out)

    def test_a_submodule_is_skipped_by_name(self):
        # A gitlink is a tracked directory: grep exited 2 on it, and a project with a
        # submodule could never pass. Its files are another repository's: nothing inside is
        # scanned, the marker below included. An untracked repository inside the tree is
        # listed by git as "nested/" and is the same case.
        for name, track in (('vendor/lib', True), ('nested', False)):
            with self.subTest(name=name):
                inner = self.project / name
                subprocess.run(['git', 'init', '-q', str(inner)], check=True)
                (inner / 'inside.md').write_text(MARKER + '\n')
                subprocess.run(GIT + ['add', 'inside.md'], cwd=inner, check=True)
                subprocess.run(GIT + ['commit', '-q', '-m', 'inner'], cwd=inner, check=True)
                if track:
                    subprocess.run(GIT + ['add', name], cwd=self.project, check=True,
                                   capture_output=True)
                    staged = subprocess.run(['git', 'ls-files', '-s', name], cwd=self.project,
                                            capture_output=True, text=True, check=True).stdout
                    self.assertTrue(staged.startswith('160000 '), staged)
                code, out = gate(self.project, self.build)
                self.assertEqual(code, 0, out)
                self.assertIn('NOTE [scan]: skipped ' + name, out)
                self.assertNotIn('a scanner failed to run', out)

    def test_a_marker_that_does_not_name_the_live_holder_is_refused(self):
        # A process the gate's build starts inherits the lock's descriptor, so the descriptor
        # proof alone accepts it; only the marker check (it must be the holder's pid in the
        # lock file) keeps a stray GATE_SELFTEST_NESTED from turning on the seams there.
        self.build.write_text('GATE_SELFTEST_NESTED=1 GATE_BUILD_CMD_OVERRIDE=true sh scripts/check.sh\n')
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [env]: GATE_BUILD_CMD_OVERRIDE is set', out)

    def test_a_symlinked_scripts_directory_runs_the_gate_in_the_project(self):
        # The gate re-executed itself by its physical path: with scripts/ a symlink into a
        # shared tree, it then checked and built that tree instead of the project.
        shared = self.tmp / 'shared'
        (self.project / 'scripts').rename(shared)
        (self.project / 'scripts').symlink_to(shared)
        where = self.tmp / 'where'
        self.build.write_text('pwd -P > %s\n' % where)
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 0, out)
        self.assertEqual(where.read_text().strip(), str(self.project.resolve()))


if __name__ == '__main__':
    unittest.main()
