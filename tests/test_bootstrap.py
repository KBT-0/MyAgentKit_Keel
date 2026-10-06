"""Bootstrap must not distribute locally generated Python bytecode."""
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


def cut_short(shims, needle):
    # A `cat` on PATH that cuts the one write whose "SOURCE:FIRST LINE" matches the shell
    # pattern `needle` short: it writes part of it, leaves `fired` and fails. `put` writes
    # every content through `cat` (stdin is "-"), so this is the intended write, reached.
    shims.mkdir(exist_ok=True)
    real = shutil.which('cat')
    (shims / 'cat').write_text(
        '#!/bin/sh\n[ $# -gt 0 ] || exec "{real}"\nsrc=$1\n'
        'if [ "$src" = - ]; then src=$(mktemp "{shims}/in.XXXXXX") && "{real}" > "$src" || exit 1; fi\n'
        'case "$1:$(head -n 1 "$src")" in {needle}) printf "cut sh"; : > "{shims}/fired"; exit 1 ;; esac\n'
        'exec "{real}" "$src"\n'.format(real=real, shims=shims, needle=needle))
    (shims / 'cat').chmod(0o755)
    return dict(os.environ, PATH=str(shims) + os.pathsep + os.environ['PATH'])


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
        for tool, match in (('cat', 'commit-msg'), ('chmod', 'pre-commit'), ('mkdir', 'docs/audits')):
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

    def test_a_hook_without_the_executable_bit_is_repaired_on_every_run(self):
        # An identical file is passed over by the copy, so the executable bit must be enforced
        # apart from it: a hook copied before its chmod failed, or one the project holds
        # identical at mode 0644, would otherwise be recorded as installed while git skips it.
        root = Path(__file__).resolve().parents[1]
        rel = '.githooks/commit-msg'
        for case in ('chmod failed, then a retry', 'identical at 0644'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project, shims = Path(tmp) / 'project', Path(tmp) / 'shims'
                hook = project / rel
                if case == 'identical at 0644':
                    hook.parent.mkdir(parents=True)
                    shutil.copyfile(root / 'core' / rel, hook)
                    hook.chmod(0o644)
                else:
                    shims.mkdir()
                    (shims / 'chmod').write_text('#!/bin/sh\nexit 1\n')
                    (shims / 'chmod').chmod(0o755)
                    env = dict(os.environ, PATH=str(shims) + os.pathsep + os.environ['PATH'])
                    result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)], env=env,
                                            capture_output=True, text=True, timeout=60)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertFalse((project / 'docs/kit/.kit-version').exists(), 'stamped')
                result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)],
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(os.access(hook, os.X_OK), 'installed a hook git does not run')
                self.assertTrue((project / 'docs/kit/.kit-version').is_file())

    def test_a_write_that_fails_midway_leaves_the_destination_as_it_was(self):
        # The stamp and the note were written by redirection and each file by `cp` straight
        # onto the destination: a full disk left an empty stamp, which the next sync refuses,
        # or a copy cut short that the retry took for the owner's own file. The temporary had a
        # fixed name and an existing file there was written into: one hard-linked to the stamp
        # had the failed write empty the live stamp. A `cat` that cuts the one write short
        # stands in for the full disk; a file-size limit stopped the run before any of them.
        root = Path(__file__).resolve().parents[1]
        current = re.search(r'^## v([0-9][0-9.]*)', (root / 'CHANGELOG.md').read_text(), re.M).group(1)
        for case, rel, needle, flags in (
                ('copied file', '.githooks/commit-msg', '*/.githooks/commit-msg:*', ()),
                ('note', 'docs/kit/BOOTSTRAP_NOTE.md', '"-:# Bootstrap note"*', ('--note', 'new agenda')),
                ('stamp', 'docs/kit/.kit-version', '-:[0-9]*', ())):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project, shims = Path(tmp) / 'project', Path(tmp) / 'shims'
                dest = project / rel
                run = lambda *flags, env=None: subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project), *flags],
                                                              env=env, capture_output=True, text=True, timeout=60)
                project.mkdir()
                if case != 'copied file':
                    first = run('--note', 'old agenda')
                    self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
                if case == 'stamp':
                    dest.write_text('0.1\n')
                    os.link(dest, dest.parent / '.kit-version.kit-tmp')
                before = dest.read_bytes() if dest.exists() else None
                failed = run(*flags, env=cut_short(shims, needle))
                self.assertNotEqual(failed.returncode, 0, failed.stdout + failed.stderr)
                self.assertTrue((shims / 'fired').exists(), 'the write of %s was never reached' % rel)
                self.assertEqual(dest.read_bytes() if dest.exists() else None, before, 'cut short: ' + rel)
                self.assertEqual(list(project.rglob('.kit-tmp.*')), [], 'temporary left')
                again = run(*flags)
                self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
                self.assertEqual(self._listed(again.stdout), set(), 'a cut-short copy taken for the owner\'s file')
                if case == 'note':
                    self.assertIn('new agenda', dest.read_text())
                else:
                    self.assertEqual(dest.read_bytes(), (current + '\n').encode() if case == 'stamp'
                                     else (root / 'core' / rel).read_bytes())
                if case == 'stamp':
                    self.assertEqual((dest.parent / '.kit-version.kit-tmp').read_text(), '0.1\n')

    def test_a_failed_write_of_the_file_list_stops_before_anything_is_written(self):
        # The copy loop reads its file list from a temporary file; a write there that fails (a
        # file-size limit stands in for a full disk) must stop the run before it writes anything.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            project.mkdir()
            failed = subprocess.run(['sh', '-c', 'trap "" XFSZ; ulimit -f 0; exec sh "$0" "$@"',
                                     str(root / 'bootstrap.sh'), str(project)],
                                    capture_output=True, text=True, timeout=60)
            self.assertNotEqual(failed.returncode, 0, failed.stdout + failed.stderr)
            self.assertIn('before the version was recorded', failed.stderr)
            self.assertEqual(list(project.iterdir()), [], 'written before the stop')

    def test_a_finish_that_fails_after_wiring_the_hooks_puts_the_hooks_path_back(self):
        # core.hooksPath was set before the stamp was written: a read-only stamp, a full disk or
        # a signal there stopped the run with the project's own hooks path already replaced.
        # A shim stands in for each failure after the `git config`, so it holds for root too.
        # A signal right after the stamp's `mv` had the trap put the hooks path back under the
        # new stamp: the project was recorded as installed with its gates disconnected. A rerun
        # of the SAME version found its stamp already holding the version and took the failure
        # for the commit: the owner's hooks path stayed replaced.
        root = Path(__file__).resolve().parents[1]
        current = re.search(r'^## v([0-9][0-9.]*)', (root / 'CHANGELOG.md').read_text(), re.M).group(1)
        faults = {'signal': ('git', 'case "$*" in *"config core.hooksPath .githooks")\n'
                                    '  "%s" "$@"; rc=$?; kill -TERM "$PPID"; exit $rc ;; esac\n'),
                  'mv fails': ('mv', 'case "$*" in */.kit-version) exit 1 ;; esac\n'),
                  'signal after the mv': ('mv', 'case "$*" in */.kit-version)\n'
                                                '  "%s" "$@"; rc=$?; kill -TERM "$PPID"; exit $rc ;; esac\n')}
        for fault, (tool, body) in faults.items():
            for prior, start in (('custom-hooks', '0.1'), (None, '0.1'), ('custom-hooks', current)):
                with self.subTest(fault=fault, prior=prior, start=start), tempfile.TemporaryDirectory() as tmp:
                    project, shims = Path(tmp) / 'project', Path(tmp) / 'shims'
                    (project / 'docs/kit').mkdir(parents=True)
                    shims.mkdir()
                    subprocess.run(['git', 'init', '-q', str(project)], check=True)
                    if prior:
                        subprocess.run(['git', '-C', str(project), 'config', 'core.hooksPath', prior], check=True)
                    stamp = project / 'docs/kit/.kit-version'
                    stamp.write_text(start + '\n')
                    stamp.chmod(0o444)
                    real = shutil.which(tool)
                    (shims / tool).write_text('#!/bin/sh\n' + (body % real if '%s' in body else body) +
                                              'exec "%s" "$@"\n' % real)
                    (shims / tool).chmod(0o755)
                    env = dict(os.environ, PATH=str(shims) + os.pathsep + os.environ['PATH'])
                    result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)], env=env,
                                            capture_output=True, text=True, timeout=60)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(list((project / 'docs/kit').glob('*kit-tmp*')), [], 'temporary left')
                    state = (stamp.read_bytes() == (start + '\n').encode(), self._hooks_path(project))
                    if prior:
                        # A hooks path of the project's own stops the run before any wiring:
                        # no fault below is reached, the stamp and the path are as they were.
                        self.assertEqual(state, (True, prior), 'the project\'s hooks path was touched')
                        self.assertIn("core.hooksPath is '%s'" % prior, result.stderr)
                        continue
                    if fault == 'signal after the mv' and start == current:
                        self.assertEqual(state, (True, '.githooks'), 'recorded with the gates disconnected')
                        continue
                    if fault == 'signal after the mv':
                        self.assertIn(state, [(True, prior or ''), (False, '.githooks')],
                                      'stamped and hooks path not wired, or the reverse')
                        continue
                    self.assertEqual(state, (True, prior or ''), 'hooks path left replaced')
                    self.assertIn('core.hooksPath', result.stderr)

    def test_a_replaced_file_keeps_its_mode(self):
        # Each file was replaced by a sibling created under the umask: a note at 0600 became
        # 0644 on a rerun of --note, its agenda readable by every local user, and a file of the
        # project's replaced under --force lost its 0640. The mode is set before the content.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            project, shims, log = Path(tmp) / 'project', Path(tmp) / 'shims', Path(tmp) / 'log'
            note, stamp = project / 'docs/kit/BOOTSTRAP_NOTE.md', project / 'docs/kit/.kit-version'
            run = lambda *flags, env=None: subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project), *flags],
                                                          env=env, capture_output=True, text=True, timeout=60)
            project.mkdir()
            (project / 'AGENTS.md').write_text('mine\n')
            (project / 'AGENTS.md').chmod(0o640)
            first = run('--note', 'first agenda', '--force')
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            note.chmod(0o600)
            stamp.chmod(0o600)
            # Every write's content passes through `cat`: the shim records the temporary's mode
            # at that moment, before a byte is in it.
            shims.mkdir()
            (shims / 'cat').write_text('#!/bin/sh\nfor f in "%s"/.kit-tmp.*; do [ -e "$f" ] && ls -l "$f" >> "%s"; done\n'
                                       'exec "%s" "$@"\n' % (project / 'docs/kit', log, shutil.which('cat')))
            (shims / 'cat').chmod(0o755)
            env = dict(os.environ, PATH=str(shims) + os.pathsep + os.environ['PATH'])
            second = run('--note', 'second agenda', env=env)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn('second agenda', note.read_text())
            self.assertEqual((project / 'AGENTS.md').read_bytes(), (root / 'core/AGENTS.md').read_bytes())
            modes = {p: (project / p).stat().st_mode & 0o7777
                     for p in ('AGENTS.md', 'docs/kit/BOOTSTRAP_NOTE.md', 'docs/kit/.kit-version')}
            self.assertEqual(modes, {'AGENTS.md': 0o640, 'docs/kit/BOOTSTRAP_NOTE.md': 0o600,
                                     'docs/kit/.kit-version': 0o600})
            seen = log.read_text().splitlines() if log.exists() else []
            self.assertTrue(seen, 'no write into a temporary observed')
            for line in seen:
                self.assertTrue(line.startswith('-rw------- '), 'wider while written: ' + line)

    def test_a_new_file_takes_the_mode_the_umask_gives(self):
        # The mode a plain redirection or `cp` gives under the caller's umask, not a fixed one
        # and not the 0600 of a fresh temporary; a file executable in the kit stays executable.
        root = Path(__file__).resolve().parents[1]
        for mask in (0o077, 0o002):
            with self.subTest(umask=oct(mask)), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / 'project'
                result = subprocess.run(['sh', '-c', 'umask %03o; exec sh "$0" "$@"' % mask,
                                         str(root / 'bootstrap.sh'), str(project)],
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                mode = lambda p: p.stat().st_mode & 0o777
                self.assertEqual(mode(project / 'docs/kit/.kit-version'), 0o666 & ~mask)
                for rel in ('AGENTS.md', 'scripts/agent_cost.py'):
                    self.assertEqual(mode(project / rel), mode(root / 'core' / rel) & ~mask, rel)

    def test_a_file_at_an_old_temporary_name_or_a_leftover_is_the_owners(self):
        # Every write went through a fixed sibling, FILE.kit-tmp: an owner's file there was
        # overwritten and moved over FILE without --force, and a FIFO or folder there stopped the
        # run. A temporary is created fresh; one a stopped run left is named, never removed.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            kit_dir = project / 'docs/kit'
            (project / '.githooks').mkdir(parents=True)
            kit_dir.mkdir(parents=True)
            (project / '.githooks/commit-msg.kit-tmp').write_text('mine\n')
            os.mkfifo(kit_dir / 'BOOTSTRAP_NOTE.md.kit-tmp')
            (kit_dir / '.kit-version.kit-tmp').mkdir()
            (kit_dir / '.kit-tmp.Ab12Cd').write_text('left\n')
            result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project), '--note', 'n'],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((project / '.githooks/commit-msg.kit-tmp').read_text(), 'mine\n')
            self.assertEqual((project / '.githooks/commit-msg').read_bytes(),
                             (root / 'core/.githooks/commit-msg').read_bytes())
            self.assertTrue((kit_dir / 'BOOTSTRAP_NOTE.md.kit-tmp').is_fifo())
            self.assertTrue((kit_dir / '.kit-version.kit-tmp').is_dir())
            self.assertEqual((kit_dir / '.kit-tmp.Ab12Cd').read_text(), 'left\n')
            self.assertIn('docs/kit/.kit-tmp.Ab12Cd', result.stdout)

    def test_a_conflict_outside_the_gates_claims_no_missing_enforcement(self):
        # Every conflict was printed under "the gate files already existed" with the warning
        # that the enforcement was not installed, also for a symlinked docs/reviews with every
        # gate file installed.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            project, outside = Path(tmp) / 'project', Path(tmp) / 'outside'
            (project / 'docs').mkdir(parents=True)
            outside.mkdir()
            (project / 'docs/reviews').symlink_to(outside)
            result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('STOPPING: these destinations could not be written', result.stdout)
            self.assertIn('conflict: docs/reviews (symlink: docs/reviews)', result.stdout)
            for claim in ('gate files', 'enforcement', 'no-op'):
                self.assertNotIn(claim, result.stdout)

    def _listed(self, stdout):
        # The files a run reports as already existing: the indented paths under its header.
        return {line.strip() for line in stdout.splitlines() if line.startswith(' ' * 13)
                and line.strip() and ' ' not in line.strip()}

    def test_a_hooks_path_of_the_project_s_own_stops_the_install(self):
        # core.hooksPath=.husky was replaced by .githooks in silence: the project's hooks
        # stopped running. The install stops, names the path, and records no version.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            project.mkdir()
            subprocess.run(['git', 'init', '-q', str(project)], check=True)
            subprocess.run(['git', '-C', str(project), 'config', 'core.hooksPath', '.husky'], check=True)
            result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("core.hooksPath is '.husky'", result.stderr)
            self.assertEqual(subprocess.run(['git', '-C', str(project), 'config', 'core.hooksPath'],
                                            capture_output=True, text=True).stdout.strip(), '.husky')
            self.assertFalse((project / 'docs/kit/.kit-version').exists())

    def test_a_hooks_path_in_another_scope_stops_the_install_and_a_project_hook_runs_beside_the_kit_s(self):
        # The guard read only the local scope: with extensions.worktreeConfig and a worktree
        # core.hooksPath=.husky, the install recorded a version while git still ran .husky,
        # and a commit with unfilled placeholders went through. Now the effective path is
        # read, the wiring is verified as git sees it, and the one migration is named: the
        # project's hook moves beside the kit's as .githooks/<name>.project and runs first.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            project.mkdir()
            git = lambda *a: subprocess.run(['git', '-C', str(project), *a], capture_output=True, text=True)
            git('init', '-q')
            git('config', 'extensions.worktreeConfig', 'true')
            git('config', '--worktree', 'core.hooksPath', '.husky')
            (project / '.husky').mkdir()
            result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("core.hooksPath is '.husky'", result.stderr)
            self.assertIn('.githooks/<same name>.project', result.stderr)
            self.assertFalse((project / 'docs/kit/.kit-version').exists())
            self.assertEqual(git('config', '--get', 'core.hooksPath').stdout.strip(), '.husky')
            # The migration: the project's pre-commit becomes .githooks/pre-commit.project.
            git('config', '--worktree', '--unset', 'core.hooksPath')
            marker = project / 'project-hook-ran'
            own = project / '.githooks/pre-commit.project'
            own.write_text('#!/bin/sh\ntouch "%s"\nexit "${PROJECT_HOOK_EXIT:-0}"\n' % marker)
            own.chmod(0o755)
            result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(git('config', '--get', 'core.hooksPath').stdout.strip(), '.githooks')
            git('add', '-A')
            commit = lambda env=None: subprocess.run(
                ['git', '-C', str(project), '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Unfilled kit'],
                capture_output=True, text=True, env=env)
            # The project's hook ran first; the kit's gate still rejected the placeholders.
            rejected = commit()
            self.assertNotEqual(rejected.returncode, 0, rejected.stdout + rejected.stderr)
            self.assertTrue(marker.exists(), 'the project hook did not run')
            self.assertIn('placeholder', rejected.stdout + rejected.stderr)
            # A failing project hook is the commit's failure, before the gate runs.
            marker.unlink()
            rejected = commit(env=dict(os.environ, PROJECT_HOOK_EXIT='3'))
            self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
            self.assertNotIn('placeholder', rejected.stdout + rejected.stderr)
            # A global scope that wins over the local setting stops the wiring too.
            git('config', '--unset', 'core.hooksPath')
            home = Path(tmp) / 'home'
            home.mkdir()
            (home / '.gitconfig').write_text('[core]\n\thooksPath = /elsewhere/hooks\n')
            shutil.rmtree(project / 'docs/kit')
            env = dict(os.environ, HOME=str(home))
            result = subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('/elsewhere/hooks', result.stderr)
            self.assertFalse((project / 'docs/kit/.kit-version').exists())

    def test_a_hook_name_the_kit_does_not_ship_runs_from_githooks_and_a_project_pre_commit_gets_no_merge_flag(self):
        # The migration moves a pre-push into .githooks/pre-push, which git runs itself; and
        # pre-merge-commit's private --merge never reaches pre-commit.project (git passes
        # pre-commit no arguments). post-merge.project cannot veto a merge that is made.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            project.mkdir()
            git = lambda *a, **k: subprocess.run(['git', '-C', str(project), '-c', 'user.name=fixture',
                                                  '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', *a],
                                                 capture_output=True, text=True, **k)
            git('init', '-q')
            subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)], capture_output=True, text=True, check=True)
            self.assertIn('as .githooks/<same name> itself', '\n'.join(
                line for line in (root / 'bootstrap.sh').read_text().splitlines() if 'pre-push' in line))
            seen = project / 'seen'
            (project / '.githooks/pre-push').write_text('#!/bin/sh\necho pre-push >> "%s"\nexit 1\n' % seen)
            (project / '.githooks/pre-push').chmod(0o755)
            (project / '.githooks/pre-commit.project').write_text('#!/bin/sh\necho "pre-commit.project:$#:$*" >> "%s"\n' % seen)
            (project / '.githooks/pre-commit.project').chmod(0o755)
            (project / '.githooks/post-merge.project').write_text('#!/bin/sh\necho post-merge.project >> "%s"\nexit 9\n' % seen)
            (project / '.githooks/post-merge.project').chmod(0o755)
            # A gate that passes: the hooks' plumbing is what this test is about.
            (project / 'scripts/check.sh').write_text('#!/bin/sh\necho "CHECK: PASS"\n')
            git('add', '-A')
            self.assertEqual(git('commit', '-qm', 'base').returncode, 0)
            self.assertIn('pre-commit.project:0:', seen.read_text())
            # The merge path: pre-merge-commit runs pre-commit --merge, the project hook sees no flag.
            git('checkout', '-q', '-b', 'side')
            (project / 'side.txt').write_text('side\n')
            git('add', 'side.txt')
            git('commit', '-qm', 'side')
            git('checkout', '-q', '-')
            (project / 'main.txt').write_text('main\n')
            git('add', 'main.txt')
            git('commit', '-qm', 'main')
            merge = git('merge', '--no-ff', '-q', '-m', 'merge side', 'side')
            self.assertEqual(merge.returncode, 0, merge.stdout + merge.stderr)
            self.assertNotIn('--merge', seen.read_text())
            self.assertIn('post-merge.project', seen.read_text())
            self.assertIn('post-merge cannot veto', merge.stderr)
            # commit-msg.project vetoes a commit (with git's message file), pre-merge-commit.project
            # vetoes a merge commit: each is the operation's failure.
            (project / '.githooks/commit-msg.project').write_text('#!/bin/sh\necho "commit-msg.project:$1" >> "%s"\ngrep -q VETO "$1" && exit 4\nexit 0\n' % seen)
            (project / '.githooks/commit-msg.project').chmod(0o755)
            (project / 'veto.txt').write_text('v\n')
            git('add', 'veto.txt')
            vetoed = git('commit', '-qm', 'VETO this')
            self.assertNotEqual(vetoed.returncode, 0, vetoed.stdout + vetoed.stderr)
            self.assertIn('commit-msg.project:', seen.read_text())
            self.assertEqual(git('commit', '-qm', 'fine').returncode, 0)
            (project / '.githooks/pre-merge-commit.project').write_text('#!/bin/sh\necho pre-merge-commit.project >> "%s"\nexit 5\n' % seen)
            (project / '.githooks/pre-merge-commit.project').chmod(0o755)
            git('checkout', '-q', '-b', 'side2')
            (project / 'side2.txt').write_text('s2\n')
            git('add', 'side2.txt')
            git('commit', '-qm', 'side2')
            git('checkout', '-q', '-')
            (project / 'main2.txt').write_text('m2\n')
            git('add', 'main2.txt')
            git('commit', '-qm', 'main2')
            blocked = git('merge', '--no-ff', '-q', '-m', 'merge side2', 'side2')
            self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
            self.assertIn('pre-merge-commit.project', seen.read_text())
            git('merge', '--abort')
            (project / '.githooks/pre-merge-commit.project').unlink()
            (project / '.githooks/commit-msg.project').unlink()
            # A hook that finds its check by its own path keeps its place behind a one-line
            # wrapper, and its veto survives the migration.
            (project / '.husky').mkdir(exist_ok=True)
            (project / '.husky/check').write_text('#!/bin/sh\nexit 6\n')
            (project / '.husky/check').chmod(0o755)
            (project / '.husky/pre-commit').write_text('#!/bin/sh\nexec "$(dirname -- "$0")/check" "$@"\n')
            (project / '.husky/pre-commit').chmod(0o755)
            (project / '.githooks/pre-commit.project').write_text('#!/bin/sh\nexec "%s" "$@"\n' % (project / '.husky/pre-commit'))
            (project / '.githooks/pre-commit.project').chmod(0o755)
            (project / 'wrapped.txt').write_text('w\n')
            git('add', 'wrapped.txt')
            wrapped = git('commit', '-qm', 'through the wrapper')
            self.assertEqual(wrapped.returncode, 1, wrapped.stdout + wrapped.stderr)
            (project / '.githooks/pre-commit.project').unlink()
            self.assertIn("exec '", '\n'.join(line for line in (root / 'bootstrap.sh').read_text().splitlines() if 'its own path' in line))
            # git runs .githooks/pre-push itself, and its rejection stops the push.
            bare = Path(tmp) / 'bare.git'
            subprocess.run(['git', 'init', '-q', '--bare', str(bare)], check=True)
            push = git('push', '-q', str(bare), 'HEAD:refs/heads/main')
            self.assertNotEqual(push.returncode, 0, push.stdout + push.stderr)
            self.assertIn('pre-push', seen.read_text())

    def test_changelog_crlf_repair_runs_verbatim(self):
        root = Path(__file__).resolve().parents[1]
        item = (root / 'CHANGELOG.md').read_text().split('14. **ACTION:**', 1)[1].split('\n\n', 1)[0]
        commands = re.findall(r'`([^`]+)`', item)
        commands = [command for command in commands if command.startswith(('git ', 'rm '))]
        self.assertTrue(commands, item)
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            git = lambda *a: subprocess.run(['git', '-C', str(project), *a],
                                            capture_output=True, text=True, check=True)
            git('init', '-q')
            git('config', 'core.autocrlf', 'true')
            git('config', 'user.name', 'fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'commit.gpgsign', 'false')
            for directory in ('.githooks', 'scripts'):
                (project / directory).mkdir()
            # The real pre-commit (it is what breaks under CRLF) over a gate that passes:
            # the repair is what is tested here, not the gate's own checks.
            (project / '.githooks/pre-commit').write_bytes((root / 'core/.githooks/pre-commit').read_bytes().replace(b'\n', b'\r\n'))
            (project / 'scripts/check.sh').write_bytes(b'#!/bin/sh\r\necho "CHECK: PASS"\r\nexit 0\r\n')
            for name in ('.githooks/pre-commit', 'scripts/check.sh'):
                (project / name).chmod(0o755)
            # Seed an old CRLF index too, so omitting renormalisation cannot pass.
            git('-c', 'core.autocrlf=false', 'add', '.')
            git('commit', '-qm', 'Before LF attributes')
            shutil.rmtree(project / '.githooks')
            shutil.rmtree(project / 'scripts')
            git('checkout', '--', '.githooks', 'scripts')
            self.assertIn(b'\r\n', (project / '.githooks/pre-commit').read_bytes())
            # Hooks wired, as in a real project: a CRLF pre-commit cannot run, so the
            # attributes are only STAGED before the repair, and committed after it.
            git('config', 'core.hooksPath', '.githooks')
            (project / '.githooks/pre-commit').chmod(0o755)
            (project / 'scripts/local.sh').write_text('untracked\n')
            (project / '.gitignore').write_text('scripts/settings.local\n')
            (project / 'scripts/settings.local').write_text('ignored\n')
            git('add', '.gitignore')
            shutil.copyfile(root / 'core/.gitattributes', project / '.gitattributes')
            for command in commands:
                run = subprocess.run(['sh', '-c', command], cwd=project, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, command + '\n' + run.stdout + run.stderr)
            self.assertEqual(git('diff', '--cached', '--name-only', '--diff-filter=D').stdout, '')
            for name in ('.githooks/pre-commit', 'scripts/check.sh'):
                self.assertNotIn(b'\r', (project / name).read_bytes())
                indexed = subprocess.run(['git', '-C', str(project), 'show', ':' + name],
                                         capture_output=True, check=True).stdout
                self.assertNotIn(b'\r', indexed)
            self.assertEqual((project / 'scripts/local.sh').read_text(), 'untracked\n', 'an untracked file was lost')
            self.assertEqual((project / 'scripts/settings.local').read_text(), 'ignored\n', 'an ignored file was lost')
            self.assertEqual(git('log', '-1', '--format=%s').stdout.strip(), 'Renormalise the kit scripts')

    def test_the_hooks_and_scripts_stay_lf_under_autocrlf(self):
        # core.autocrlf=true gave a fresh checkout CRLF hooks (`#!/usr/bin/env sh\r`), and every
        # hook died before its first command: the kit ships a .gitattributes that pins them.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            project.mkdir()
            git = lambda *a: subprocess.run(['git', '-C', str(project), *a], capture_output=True, text=True, check=True)
            git('init', '-q')
            git('config', 'core.autocrlf', 'true')
            subprocess.run(['sh', str(root / 'bootstrap.sh'), str(project)], capture_output=True, text=True, check=True)
            self.assertTrue((project / '.gitattributes').exists())
            git('add', '-A')
            git('-c', 'user.name=a', '-c', 'user.email=a@b', 'commit', '-q', '--no-verify', '-m', 'kit')
            shutil.rmtree(project / '.githooks')
            git('checkout', '-q', '--', '.githooks', 'scripts')
            for name in ('.githooks/pre-commit', 'scripts/check.sh', 'scripts/claude_bridge.py'):
                self.assertNotIn(b'\r', (project / name).read_bytes(), name)

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
