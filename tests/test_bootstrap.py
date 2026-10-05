"""Bootstrap must not distribute locally generated Python bytecode."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class BootstrapTests(unittest.TestCase):
    def test_bytecode_is_not_installed(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            scripts = kit / 'core/scripts'
            (scripts / '__pycache__').mkdir(parents=True)
            (scripts / '__pycache__/helper.cpython-314.pyc').write_bytes(b'\xff\x00')
            (scripts / 'legacy.pyc').write_bytes(b'\xff\x00')
            (scripts / 'helper.py').write_text('"""Fixture source."""\n')
            shutil.copyfile(root / 'bootstrap.sh', kit / 'bootstrap.sh')
            (kit / 'CHANGELOG.md').write_text('## v0.7\n')
            result = subprocess.run(['sh', str(kit / 'bootstrap.sh'), str(project)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((project / 'scripts/helper.py').is_file())
            self.assertFalse(list(project.rglob('*.pyc')), 'Local bytecode entered the installed project')

    def test_a_kept_enforcement_file_stops_the_retrofit(self):
        # A retrofit that kept the repository's own (possibly no-op) gate or hook installed no
        # enforcement; the guard named check.sh and pre-commit only, so a kept pre-merge-commit
        # or commit-msg left clean merges or attribution unenforced while the version was stamped.
        root = Path(__file__).resolve().parents[1]
        for kept in ('scripts/check.sh', '.githooks/pre-commit', '.githooks/pre-merge-commit',
                     '.githooks/commit-msg'):
            with self.subTest(kept=kept), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / 'project'
                (project / kept).parent.mkdir(parents=True)
                (project / kept).write_text('#!/bin/sh\nexit 0\n')
                result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('STOPPING: the gate files already existed', result.stdout)
                self.assertFalse((project / 'docs/kit/.kit-version').exists())

    def test_a_gate_path_that_is_not_a_regular_file_stops_unread(self):
        # `cmp` on an existing FIFO at .githooks/commit-msg blocked forever, and a symlink
        # there was compared, or written through, by its target: anything but a regular file
        # is a conflict, never read or written, --force included.
        root = Path(__file__).resolve().parents[1]
        rel = '.githooks/commit-msg'
        for kind in ('fifo', 'identical symlink', 'dangling symlink', 'directory'):
            for force in ((), ('--force',)):
                with self.subTest(kind=kind, force=force), tempfile.TemporaryDirectory() as tmp:
                    project, outside = Path(tmp) / 'project', Path(tmp) / 'outside'
                    (project / '.githooks').mkdir(parents=True)
                    if kind == 'fifo':
                        os.mkfifo(project / rel)
                    elif kind == 'directory':
                        (project / rel).mkdir()
                    else:
                        if kind == 'identical symlink':
                            shutil.copyfile(root / 'core' / rel, outside)
                        (project / rel).symlink_to(outside)
                    result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project), *force],
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('conflict: ' + rel, result.stdout)
                    self.assertFalse((project / 'docs/kit/.kit-version').exists())
                    if kind == 'dangling symlink':
                        self.assertFalse(outside.exists(), 'written through a symlink')

    def test_a_symlinked_folder_in_the_target_is_never_read_or_written(self):
        # Only the last component of a destination was checked: with `.githooks` a symlink to
        # a folder outside the project, the kit's hooks were written there and the run passed.
        # Any symlink in a destination's path is a conflict for a gate (or the version stamp)
        # and a listed skip for any other file, never read or written, --force included.
        root = Path(__file__).resolve().parents[1]
        for folder, stops, needle in (('.githooks', True, 'conflict: .githooks/commit-msg (symlink: .githooks)'),
                                      ('docs', True, 'conflict: docs/kit/.kit-version (symlink: docs)'),
                                      ('setup', False, 'setup/INTERVIEW.md')):
            for force in ((), ('--force',)):
                with self.subTest(folder=folder, force=force), tempfile.TemporaryDirectory() as tmp:
                    project, outside = Path(tmp) / 'project', Path(tmp) / 'outside'
                    project.mkdir()
                    outside.mkdir()
                    (project / folder).symlink_to(outside)
                    result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project), *force],
                                            capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 1 if stops else 0, result.stdout + result.stderr)
                    self.assertIn(needle, result.stdout)
                    self.assertEqual(list(outside.iterdir()), [], 'written through a symlinked folder')
                    self.assertEqual((project / 'docs/kit/.kit-version').exists(), not stops)

    def _hooks_path(self, project):
        return subprocess.run(['git', '-C', str(project), 'config', '--local', '--get', 'core.hooksPath'],
                              capture_output=True, text=True).stdout.strip()

    def test_a_destination_that_cannot_be_written_stops_unopened(self):
        # A regular FILE at `.githooks` made every hook "absent": mkdir and cp failed unchecked,
        # and the run stamped the version and wired the hooks with no hook installed. A FIFO at
        # a file bootstrap GENERATES (the stamp, the --note file) only had the symlink check and
        # blocked forever when opened for writing; a folder there was an ignored write failure.
        root = Path(__file__).resolve().parents[1]
        for case, rel, make, flags, needle in (
                ('file for a folder', '.githooks', 'file', (), 'conflict: .githooks/commit-msg (not a folder: .githooks)'),
                ('fifo stamp', 'docs/kit/.kit-version', 'fifo', (), 'conflict: docs/kit/.kit-version (not a regular file)'),
                ('fifo note', 'docs/kit/BOOTSTRAP_NOTE.md', 'fifo', ('--note', 'n'),
                 'conflict: docs/kit/BOOTSTRAP_NOTE.md (not a regular file)'),
                ('folder stamp', 'docs/kit/.kit-version', 'dir', (), 'conflict: docs/kit/.kit-version (not a regular file)'),
                ('file for a created folder', 'docs/reviews', 'file', (), 'conflict: docs/reviews (not a folder)')):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / 'project'
                project.mkdir()
                subprocess.run(['git', 'init', '-q', str(project)], check=True)
                (project / rel).parent.mkdir(parents=True, exist_ok=True)
                {'file': lambda p: p.write_text('x\n'), 'fifo': os.mkfifo, 'dir': Path.mkdir}[make](project / rel)
                try:
                    result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project), *flags],
                                            capture_output=True, text=True, timeout=60)
                except subprocess.TimeoutExpired:
                    self.fail('blocked on ' + rel)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(needle, result.stdout)
                self.assertFalse((project / 'docs/kit/.kit-version').is_file(), 'stamped')
                self.assertEqual(self._hooks_path(project), '', 'hooks wired')

    def test_a_failed_write_stops_before_the_stamp_and_the_hooks(self):
        # Every mkdir, cp and chmod ran unchecked: one that failed (a full disk, a read-only
        # folder) left the install short while the version was stamped and the hooks wired.
        root = Path(__file__).resolve().parents[1]
        for tool, match in (('cp', 'commit-msg'), ('chmod', 'pre-commit'), ('mkdir', 'docs/audits')):
            with self.subTest(tool=tool), tempfile.TemporaryDirectory() as tmp:
                project, shims = Path(tmp) / 'project', Path(tmp) / 'shims'
                project.mkdir()
                shims.mkdir()
                subprocess.run(['git', 'init', '-q', str(project)], check=True)
                (shims / tool).write_text('#!/bin/sh\ncase "$*" in *%s*) exit 1 ;; esac\nexec "%s" "$@"\n'
                                          % (match, shutil.which(tool)))
                (shims / tool).chmod(0o755)
                env = dict(os.environ, PATH=str(shims) + os.pathsep + os.environ['PATH'])
                result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)], env=env,
                                        capture_output=True, text=True, timeout=60)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('before the version was recorded', result.stderr)
                self.assertFalse((project / 'docs/kit/.kit-version').exists(), 'stamped')
                self.assertEqual(self._hooks_path(project), '', 'hooks wired')

    def _listed(self, stdout):
        # The files a run reports as already existing: the indented paths under its header.
        return {line.strip() for line in stdout.splitlines() if line.startswith(' ' * 13)
                and line.strip() and ' ' not in line.strip()}

    def test_a_rerun_after_a_stop_names_only_the_differing_file(self):
        # The first run copies every other file before it stops, so a rerun that counted those
        # as conflicts stopped again on files the kit itself had put there: only --force got
        # through, and it overwrote the owner's kept hook.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            (project / '.githooks').mkdir(parents=True)
            (project / '.githooks/commit-msg').write_text('#!/bin/sh\nexit 0\n')
            run = lambda: subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)],
                                         capture_output=True, text=True)
            self.assertEqual(run().returncode, 1)
            second = run()
            self.assertEqual(second.returncode, 1, second.stdout + second.stderr)
            self.assertEqual(self._listed(second.stdout), {'.githooks/commit-msg'}, second.stdout)

    def test_a_resolved_stop_completes_without_force(self):
        # Moving the kept hook aside is the advice; the rerun must then finish without --force
        # and leave the owner's other files as they were.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            (project / '.githooks').mkdir(parents=True)
            (project / '.githooks/commit-msg').write_text('#!/bin/sh\nexit 0\n')
            (project / 'AGENTS.md').write_text('the owner\'s own\n')
            run = lambda: subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)],
                                         capture_output=True, text=True)
            self.assertEqual(run().returncode, 1)
            (project / '.githooks/commit-msg').rename(project / 'commit-msg.mine')
            second = run()
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertTrue((project / 'docs/kit/.kit-version').is_file())
            self.assertEqual((project / 'AGENTS.md').read_text(), 'the owner\'s own\n')
            self.assertEqual((project / 'commit-msg.mine').read_text(), '#!/bin/sh\nexit 0\n')
            self.assertEqual((project / '.githooks/commit-msg').read_bytes(),
                             (root / 'core/.githooks/commit-msg').read_bytes())
            self.assertEqual(self._listed(second.stdout), {'AGENTS.md'}, second.stdout)
