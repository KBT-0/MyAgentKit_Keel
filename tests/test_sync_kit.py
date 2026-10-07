"""sync-kit.sh must not stamp a version whose ACTION items the owner has not confirmed."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ACTION = '- A rule moved. **ACTION:** copy it into your project-owned workflow.\n'


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


class SyncKitTests(unittest.TestCase):
    def sync(self, tmp, entry, *flags, env=None):
        kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
        if not kit.exists():
            kit.mkdir()
            shutil.copyfile(ROOT / 'sync-kit.sh', kit / 'sync-kit.sh')
            (kit / 'CHANGELOG.md').write_text('## v0.2\n\n' + entry + '\n## v0.1\n\n- First.\n')
            (project / 'docs/kit').mkdir(parents=True)
            (project / 'docs/kit/.kit-version').write_text('0.1\n')
        result = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project), *flags],
                                capture_output=True, text=True, env=env)
        stamp = (project / 'docs/kit/.kit-version').read_text().strip()
        return result, stamp

    def test_unconfirmed_action_keeps_the_stamp_and_reappears(self):
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(2):
                result, stamp = self.sync(tmp, ACTION)
                self.assertEqual(stamp, '0.1', 'stamped past an unconfirmed ACTION')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('**ACTION:** copy it', result.stdout)
                self.assertNotIn('already current', result.stdout)
            result, stamp = self.sync(tmp, ACTION, '--actions-applied')
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            result, _ = self.sync(tmp, ACTION)
            self.assertIn('already current', result.stdout)
            self.assertNotIn('ACTION', result.stdout)

    def test_version_without_action_is_stamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, stamp = self.sync(tmp, '- A kit-owned file changed.\n')
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)

    def test_an_action_none_line_is_not_an_item(self):
        # A release with nothing to do by hand says so with "**ACTION** — none"; listed as an
        # item, it stopped the sync and left the version unstamped for nothing.
        with tempfile.TemporaryDirectory() as tmp:
            result, stamp = self.sync(tmp, '- A kit-owned file changed. **ACTION** \u2014 none\n')
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            self.assertNotIn('ACTION items since', result.stdout)

    def test_a_failed_action_scan_keeps_the_stamp(self):
        # An empty pending list from a scanner that died reads as "no ACTION items".
        with tempfile.TemporaryDirectory() as tmp:
            shims = Path(tmp) / 'shims'
            shims.mkdir()
            (shims / 'awk').write_text('#!/bin/sh\ncase "$*" in *ACTION*) exit 2 ;; esac\n'
                                       'exec "%s" "$@"\n' % shutil.which('awk'))
            (shims / 'awk').chmod(0o755)
            env = dict(os.environ, PATH=str(shims) + os.pathsep + os.environ['PATH'])
            result, stamp = self.sync(tmp, '- A kit-owned file changed.\n', env=env)
            self.assertEqual(stamp, '0.1', 'stamped after the ACTION scan failed')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('cannot scan the changelog for ACTION items', result.stderr)

    def test_a_project_owned_file_at_a_kit_owned_path_is_a_conflict_not_overwritten(self):
        # A path that became kit-owned in a later version held the project's own hook; the
        # sync replaced it with the kit's, reported "update:", and the project's own message
        # check was gone. A file without the KIT-OWNED header is the project's.
        owned = ('.githooks/commit-msg', '.githooks/pre-merge-commit', 'scripts/doctor.sh')
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            self.sync(tmp, '- A kit-owned file changed.\n', '--dry-run')
            for rel in owned + ('.githooks/pre-commit', 'scripts/agent_cost.py'):
                (kit / 'core' / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / 'core' / rel, kit / 'core' / rel)
            for rel in owned:
                (project / rel).parent.mkdir(parents=True, exist_ok=True)
                (project / rel).write_text('#!/bin/sh\n# the project\'s own %s\nexit 1\n' % rel)
            # A kit-owned copy that differs is still the kit's to update.
            (project / 'scripts/agent_cost.py').write_text('# KIT-OWNED: an older copy\n')
            for flags in ((), ('--actions-applied',)):
                with self.subTest(flags=flags):
                    result, stamp = self.sync(tmp, '- A kit-owned file changed.\n', *flags)
                    self.assertEqual(stamp, '0.1', 'stamped past a conflict')
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    for rel in owned:
                        self.assertIn('conflict: ' + rel, result.stdout)
                        self.assertIn("the project's own " + rel, (project / rel).read_text())
                    self.assertFalse((project / '.githooks/pre-commit').exists(), 'copied past a conflict')
                    self.assertIn('older copy', (project / 'scripts/agent_cost.py').read_text())
            for rel in owned:
                (project / rel).unlink()
            result, stamp = self.sync(tmp, '- A kit-owned file changed.\n')
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            self.assertEqual((project / 'scripts/agent_cost.py').read_bytes(),
                             (ROOT / 'core/scripts/agent_cost.py').read_bytes())

    def test_the_first_run_refreshes_kit_owned_files_before_the_actions_are_verified(self):
        # The v0.10 checklist verifies doctor.sh in item 4 and stamps in item 5. The run that
        # prints the checklist must already have installed the new kit-owned files, or item 4
        # proves the old doctor (on native Windows, one that asks for tmux) and item 5 installs
        # the new one after every check.
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            self.sync(tmp, ACTION, '--dry-run')
            new = '#!/bin/sh\n# KIT-OWNED: fixture\necho v0.2 doctor\n'
            (kit / 'core/scripts').mkdir(parents=True)
            (kit / 'core/scripts/doctor.sh').write_text(new)
            (project / 'scripts').mkdir()
            (project / 'scripts/doctor.sh').write_text('#!/bin/sh\n# KIT-OWNED: fixture\necho v0.1 doctor\n')
            result, stamp = self.sync(tmp, ACTION)
            self.assertEqual((result.returncode, stamp), (2, '0.1'), result.stdout + result.stderr)
            self.assertEqual((project / 'scripts/doctor.sh').read_text(), new)
            result, stamp = self.sync(tmp, ACTION, '--actions-applied')
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            self.assertEqual((project / 'scripts/doctor.sh').read_text(), new)
        # The checklist says so before its first item, and item 5 says the stamp copies nothing new.
        checklist = (ROOT / 'CHANGELOG.md').read_text().split('### Upgrading a project from v0.9', 1)[1]
        intro, items = checklist.split('\n1. ', 1)
        self.assertIn('Start with `"$KIT/sync-kit.sh" .`', intro)
        self.assertIn('copies nothing new', items.split('\n5. ', 1)[1].split('\n## ', 1)[0])

    def test_a_header_less_overlay_copy_is_told_to_take_the_kits_copy(self):
        # A v0.8 project's overlay script had no KIT-OWNED header. The stop message said to
        # rerun the sync to install the kit's file, which the sync never does for an overlay
        # file that is absent, and to carry what "yours" did into the project (RETROFIT).
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            self.sync(tmp, '- A kit-owned file changed.\n', '--dry-run')
            src = kit / 'overlays/o/files/scripts/tool.sh'
            src.parent.mkdir(parents=True)
            src.write_text('#!/bin/sh\n# KIT-OWNED: fixture\n')
            (project / 'scripts').mkdir()
            (project / 'scripts/tool.sh').write_text('#!/bin/sh\n# an earlier kit copy\n')
            result, stamp = self.sync(tmp, '- A kit-owned file changed.\n')
            self.assertEqual((result.returncode, stamp), (1, '0.1'), result.stdout + result.stderr)
            self.assertIn('conflict: scripts/tool.sh', result.stdout)
            self.assertIn("the kit's own file from an earlier version", result.stdout)
            self.assertIn(str(src), result.stdout)
            self.assertNotIn('rerun the sync to install', result.stdout)
            self.assertNotIn('RETROFIT', result.stdout)

    def test_a_kit_owned_path_that_is_not_a_regular_file_is_a_conflict_unread(self):
        # `cmp` on a FIFO at a kit-owned path blocked forever, and a symlink to an identical
        # copy read as "same": anything but a regular file is a conflict, never read.
        rel = '.githooks/commit-msg'
        for kind in ('fifo', 'identical symlink'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
                self.sync(tmp, '- A kit-owned file changed.\n', '--dry-run')
                (kit / 'core' / rel).parent.mkdir(parents=True)
                shutil.copyfile(ROOT / 'core' / rel, kit / 'core' / rel)
                (project / rel).parent.mkdir(parents=True)
                if kind == 'fifo':
                    os.mkfifo(project / rel)
                else:
                    shutil.copyfile(ROOT / 'core' / rel, Path(tmp) / 'outside')
                    (project / rel).symlink_to(Path(tmp) / 'outside')
                result = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project)],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('conflict: ' + rel, result.stdout)
                self.assertEqual((project / 'docs/kit/.kit-version').read_text(), '0.1\n')

    def test_a_symlinked_folder_or_a_dangling_overlay_link_is_a_conflict_untouched(self):
        # Only the last component was checked: with `.githooks` a symlink to a folder outside
        # the project, the kit's hook was listed "new:" and written there. And an overlay file
        # whose destination was a dangling symlink was skipped without a word (`-e` is false).
        cases = (('core/.githooks/commit-msg', '.githooks', '.githooks/commit-msg (symlink: .githooks'),
                 ('overlays/o/files/scripts/tool.sh', 'scripts/tool.sh', 'scripts/tool.sh (symlink: scripts/tool.sh'))
        for src, link, needle in cases:
            with self.subTest(link=link), tempfile.TemporaryDirectory() as tmp:
                kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
                outside = Path(tmp) / 'outside'
                self.sync(tmp, '- A kit-owned file changed.\n', '--dry-run')
                (kit / src).parent.mkdir(parents=True)
                (kit / src).write_text('#!/bin/sh\n# KIT-OWNED: fixture\n')
                (project / link).parent.mkdir(parents=True, exist_ok=True)
                if link == '.githooks':
                    outside.mkdir()
                (project / link).symlink_to(outside)
                result = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project), '--actions-applied'],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('conflict: ' + needle, result.stdout)
                self.assertEqual((project / 'docs/kit/.kit-version').read_text(), '0.1\n')
                self.assertEqual(list(outside.iterdir()) if outside.is_dir() else outside.exists(),
                                 [] if link == '.githooks' else False, 'written through a symlink')

    def test_a_destination_that_cannot_be_written_is_a_conflict_and_a_failed_write_keeps_the_stamp(self):
        # A regular FILE at `.githooks` made the hook "new:" and its copy failed midway through
        # the copies; a failed chmod was ignored and the version stamped over a hook that cannot
        # run; a FIFO or folder at the stamp read as "not installed with bootstrap.sh".
        rel = '.githooks/commit-msg'
        cases = (('file for a folder', 'conflict: .githooks/commit-msg (not a folder: .githooks,'),
                 ('fifo stamp', 'conflict: docs/kit/.kit-version (not a regular file)'),
                 ('folder stamp', 'conflict: docs/kit/.kit-version (not a regular file)'),
                 ('chmod fails', 'could not write .githooks/commit-msg; version left at v0.1'))
        for case, needle in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
                self.sync(tmp, '- A kit-owned file changed.\n', '--dry-run')
                (kit / 'core' / rel).parent.mkdir(parents=True)
                shutil.copyfile(ROOT / 'core' / rel, kit / 'core' / rel)
                env = None
                stamp = project / 'docs/kit/.kit-version'
                if case == 'file for a folder':
                    (project / '.githooks').write_text('x\n')
                elif case != 'chmod fails':
                    stamp.unlink()
                    os.mkfifo(stamp) if case == 'fifo stamp' else stamp.mkdir()
                else:
                    shims = Path(tmp) / 'shims'
                    shims.mkdir()
                    (shims / 'chmod').write_text('#!/bin/sh\nexit 1\n')
                    (shims / 'chmod').chmod(0o755)
                    env = dict(os.environ, PATH=str(shims) + os.pathsep + os.environ['PATH'])
                try:
                    result = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project)], env=env,
                                            capture_output=True, text=True, timeout=30)
                except subprocess.TimeoutExpired:
                    self.fail('blocked')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(needle, result.stdout + result.stderr)
                if stamp.is_file():
                    self.assertEqual(stamp.read_text(), '0.1\n')
                else:
                    self.assertTrue(stamp.is_fifo() or stamp.is_dir())

    def test_a_hook_without_the_executable_bit_is_never_same(self):
        # "same" was decided from the content alone: a hook copied before its chmod failed, or
        # one the project holds identical but at mode 0644, was passed over on the next run and
        # the version recorded over a hook git does not run.
        rel = '.githooks/commit-msg'
        for case in ('chmod failed, then a retry', 'identical at 0644'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
                self.sync(tmp, '- A kit-owned file changed.\n', '--dry-run')
                (kit / 'core' / rel).parent.mkdir(parents=True)
                shutil.copyfile(ROOT / 'core' / rel, kit / 'core' / rel)
                hook = project / rel
                if case == 'identical at 0644':
                    hook.parent.mkdir(parents=True)
                    shutil.copyfile(ROOT / 'core' / rel, hook)
                    hook.chmod(0o644)
                else:
                    shims = Path(tmp) / 'shims'
                    shims.mkdir()
                    (shims / 'chmod').write_text('#!/bin/sh\nexit 1\n')
                    (shims / 'chmod').chmod(0o755)
                    env = dict(os.environ, PATH=str(shims) + os.pathsep + os.environ['PATH'])
                    result = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project)], env=env,
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertEqual((project / 'docs/kit/.kit-version').read_text(), '0.1\n')
                result = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project)],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(os.access(hook, os.X_OK), 'version recorded over a hook git does not run')
                self.assertEqual((project / 'docs/kit/.kit-version').read_text(), '0.2\n')

    def test_a_write_that_fails_midway_leaves_the_old_file_whole(self):
        # The stamp was written by redirection, which empties the file before writing, and the
        # kit-owned files by `cp` over them: a full disk left an empty stamp (which the next sync
        # refuses) or a hook cut short. A `cat` that cuts the one write short stands in for the
        # full disk. A file at the old fixed temporary name, hard-linked to the stamp, was
        # written into: the failed write emptied the live stamp through it.
        rel = '.githooks/commit-msg'
        for case, needle in (('stamp', '-:[0-9]*'), ('kit-owned file', '*/.githooks/commit-msg:*'),
                             ('stamp hard-linked', '-:[0-9]*')):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                kit, project, shims = Path(tmp) / 'kit', Path(tmp) / 'project', Path(tmp) / 'shims'
                self.sync(tmp, '- A kit-owned file changed.\n', '--dry-run')
                old = b'#!/bin/sh\n# KIT-OWNED: an older copy\n'
                (kit / 'core' / rel).parent.mkdir(parents=True)
                shutil.copyfile(ROOT / 'core' / rel, kit / 'core' / rel)
                (project / rel).parent.mkdir(parents=True)
                (project / rel).write_bytes(old)
                if case == 'stamp hard-linked':
                    os.link(project / 'docs/kit/.kit-version', project / 'docs/kit/.kit-version.kit-tmp')
                result = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project)], env=cut_short(shims, needle),
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertTrue((shims / 'fired').exists(), 'the intended write was never reached')
                self.assertEqual((project / 'docs/kit/.kit-version').read_bytes(), b'0.1\n')
                if case == 'kit-owned file':
                    self.assertEqual((project / rel).read_bytes(), old, 'a hook cut short')
                self.assertEqual(sorted(p.name for p in project.rglob('.kit-tmp.*')), [], 'temporary left')
                again = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project)],
                                       capture_output=True, text=True, timeout=30)
                self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
                self.assertEqual((project / 'docs/kit/.kit-version').read_bytes(), b'0.2\n')
                self.assertEqual((project / rel).read_bytes(), (ROOT / 'core' / rel).read_bytes())

    def test_whatever_is_at_an_old_temporary_name_or_a_leftover_is_left_alone(self):
        # The stamp and the kit-owned files were written through a fixed sibling, FILE.kit-tmp:
        # an owner's file there was overwritten and removed, and a folder or symlink there
        # stopped the sync. A temporary is created fresh; one a stopped run left is named only.
        rel = '.githooks/commit-msg'
        for kind in ('file', 'folder', 'symlink', 'hard link to the stamp'):
            for where in ('docs/kit/.kit-version.kit-tmp', rel + '.kit-tmp'):
                with self.subTest(kind=kind, where=where), tempfile.TemporaryDirectory() as tmp:
                    kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
                    self.sync(tmp, '- A kit-owned file changed.\n', '--dry-run')
                    (kit / 'core' / rel).parent.mkdir(parents=True)
                    shutil.copyfile(ROOT / 'core' / rel, kit / 'core' / rel)
                    (project / where).parent.mkdir(parents=True, exist_ok=True)
                    leftover = project / 'docs/kit/.kit-tmp.Ab12Cd'
                    leftover.write_text('left\n')
                    if kind == 'file':
                        (project / where).write_text('mine\n')
                    elif kind == 'folder':
                        (project / where).mkdir()
                    elif kind == 'symlink':
                        (project / where).symlink_to(Path(tmp) / 'outside')
                    else:
                        os.link(project / 'docs/kit/.kit-version', project / where)
                    result = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project)],
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual((project / 'docs/kit/.kit-version').read_text(), '0.2\n')
                    self.assertEqual((project / rel).read_bytes(), (ROOT / 'core' / rel).read_bytes())
                    self.assertFalse((Path(tmp) / 'outside').exists(), 'written through a symlink')
                    self.assertEqual({'file': lambda p: p.read_text() == 'mine\n', 'folder': Path.is_dir,
                                      'symlink': Path.is_symlink,
                                      'hard link to the stamp': lambda p: p.read_text() == '0.1\n'}[kind](project / where),
                                     True, 'the owner\'s ' + kind + ' was changed')
                    self.assertEqual(leftover.read_text(), 'left\n')
                    self.assertIn('docs/kit/.kit-tmp.Ab12Cd', result.stdout)

    def test_the_path_check_and_the_writer_are_the_same_functions_in_bootstrap_and_sync(self):
        # bootstrap.sh and sync-kit.sh each hold `blocked`, the one check for every path they
        # write, and `put`, the one writer; two copies with nothing holding them equal drift,
        # and one script then writes where, or how, the other refuses.
        def body(name, fn):
            text = (ROOT / name).read_text()
            start = text.index('\n%s() {\n' % fn)
            return text[start:text.index('\n}\n', start) + 3]
        for fn in ('blocked', 'perms', 'stage', 'put'):
            with self.subTest(fn=fn):
                self.assertEqual(body('sync-kit.sh', fn), body('bootstrap.sh', fn))

    def test_every_printed_action_item_of_the_real_changelog_is_whole(self):
        # The checklist printed only the physical line holding the marker, so an owner
        # confirming it read "one would be. **ACTION:** copy" and twice nothing at all.
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            kit.mkdir()
            for name in ('sync-kit.sh', 'CHANGELOG.md'):
                shutil.copyfile(ROOT / name, kit / name)
            (project / 'docs/kit').mkdir(parents=True)
            # A version the changelog does not hold: every version's items are listed.
            (project / 'docs/kit/.kit-version').write_text('0.0\n')
            result = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project), '--dry-run'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            checklist = result.stdout.split('ACTION items since v0.0')[1].split('sync-kit: dry run')[0]
            items = []
            for line in checklist.splitlines()[1:]:
                if line.startswith('  v'):
                    items.append(line.split(': ', 1)[1].strip())
                elif line.strip():
                    self.assertTrue(items and line.startswith('      '), line)
                    items[-1] += ' ' + line.strip()
            self.assertGreater(len(items), 10)
            for item in items:
                after = item.split('**ACTION', 1)[1].lstrip('*: ')
                self.assertTrue(after.strip(), 'nothing after the marker: ' + item)
                self.assertRegex(item, r'[.!?:][`*)"]*$', 'cut mid-sentence: ' + item)

    def test_the_upgrade_checklist_reports_every_removed_line_of_the_project(self):
        # The removed-line filter `grep '^-[^-]'` skipped the diff's file headers and with them
        # every removed line that itself starts with a hyphen: a deleted Markdown rule
        # `- Require a licence check.` shows as `--` and was hidden. Run the real snippet.
        text = (ROOT / 'CHANGELOG.md').read_text()
        block = next(part for part in text.split('```sh\n')[1:] if 'kit-removed' in part.split('```')[0])
        snippet = '\n'.join(line.strip() for line in block.split('```')[0].splitlines())
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_PAGER='cat')
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            common = 'keep\nkit-line\n'
            for repo, path, body in ((kit, 'core/RULES.md', common),
                                     (project, 'RULES.md', '- bullet\n-- double\nplain\n' + common)):
                (repo / path).parent.mkdir(parents=True, exist_ok=True)
                (repo / path).write_text(body)
                for args in (('init', '-q'), ('add', '.'),
                             ('-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'base')):
                    subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, env=env)
                (repo / path).write_text('keep\n')
            base = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=kit, check=True, capture_output=True,
                                  text=True, env=env).stdout.strip()
            self.assertIn('5c80c36', snippet)
            result = subprocess.run(['sh', '-c', snippet.replace('5c80c36', base)], cwd=project, capture_output=True,
                                    text=True, env=dict(env, KIT=str(kit), f='RULES.md', src='core/RULES.md'))
            self.assertEqual(result.stdout.splitlines(), ['-- bullet', '--- double', '-plain'], result.stderr)

    def test_the_line_ending_action_makes_a_crlf_clone_runnable(self):
        # A v0.9 project cloned with Git for Windows' default core.autocrlf=true has CRLF
        # scripts and hooks, which sh cannot run. Run the real v0.10 snippet there: afterwards
        # each runs, the index holds LF (a script committed with CRLF is renormalized), and the
        # only other staged change is .gitattributes. It touches nothing else: not a file a
        # tracked symlink points to, not an owner's file at a temporary's name, not a lone CR,
        # not an unrelated file an older attribute would renormalize; and a name holding a
        # newline is fixed like any other.
        import textwrap
        text = (ROOT / 'CHANGELOG.md').read_text()
        block = next(part for part in text.split('```sh\n')[1:]
                     if 'core/.gitattributes' in part.split('```')[0])
        snippet = textwrap.dedent(block.split('```')[0])
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', KIT=str(ROOT))
        git = lambda repo, *args: subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True,
                                                 env=env).stdout
        commit = lambda message: git(project, '-c', 'user.name=F', '-c', 'user.email=f@example.invalid',
                                     'commit', '-qm', message)
        with tempfile.TemporaryDirectory() as tmp:
            project, clone, outside = Path(tmp) / 'project', Path(tmp) / 'clone', Path(tmp) / 'outside.sh'
            (project / 'scripts').mkdir(parents=True)
            (project / '.githooks').mkdir()
            scripts = {'scripts/check.sh': b'#!/bin/sh\nset -eu\necho check ran\n',
                       'scripts/old.sh': b'#!/bin/sh\r\nset -eu\r\necho old ran\r\n',
                       'scripts/two\nlines.sh': b'#!/bin/sh\necho two ran\n',
                       'scripts/lone.sh': b'#!/bin/sh\n# a lone \r stays\necho lone ran\n',
                       '.githooks/pre-commit': b'#!/bin/sh\nset -eu\necho hook ran\n'}
            for path, body in scripts.items():
                (project / path).write_bytes(body)
            (project / 'scripts/link.sh').symlink_to('../../outside.sh')
            outside.write_bytes(b'#!/bin/sh\r\necho outside\r\n')
            (project / 'notes.txt').write_bytes(b'one\r\ntwo\r\n')
            (project / '.gitattributes').write_bytes(b'*.bin binary')
            git(project, 'init', '-q')
            git(project, 'add', '-A')
            commit('v0.9')
            # A text rule added after notes.txt was committed with CRLF: renormalizing everything
            # would restage it.
            (project / '.gitattributes').write_bytes(b'*.bin binary\n*.txt text')
            git(project, 'add', '.gitattributes')
            commit('notes are text')
            self.assertIn(b'\r\n', git(project, 'show', 'HEAD:notes.txt'))
            git(tmp, '-c', 'core.autocrlf=true', 'clone', '-q', str(project), str(clone))
            git(clone, 'config', 'core.autocrlf', 'true')
            self.assertIn(b'\r\n', (clone / 'scripts/check.sh').read_bytes())
            (clone / 'scripts/check.sh.lf').write_bytes(b'mine\n')
            result = subprocess.run(['sh', '-c', snippet], cwd=clone, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for path, body in scripts.items():
                with self.subTest(path=path):
                    self.assertEqual((clone / path).read_bytes(), body.replace(b'\r\n', b'\n'))
                    self.assertEqual(git(clone, 'show', ':' + path), body.replace(b'\r\n', b'\n'))
                    ran = subprocess.run(['sh', path], cwd=clone, capture_output=True, text=True)
                    self.assertEqual(ran.returncode, 0, ran.stderr)
                    self.assertTrue(ran.stdout.endswith(' ran\n'), ran.stdout)
            self.assertEqual(outside.read_bytes(), b'#!/bin/sh\r\necho outside\r\n')
            self.assertTrue((clone / 'scripts/link.sh').is_symlink())
            self.assertEqual((clone / 'scripts/check.sh.lf').read_bytes(), b'mine\n')
            self.assertEqual(sorted(git(clone, 'diff', '--cached', '--name-only', '-z').split(b'\0')[:-1]),
                             [b'.gitattributes', b'scripts/old.sh'])
            self.assertIn(b'*.txt text\n', (clone / '.gitattributes').read_bytes())
            git = lambda repo, *args: subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True,
                                                     text=True, env=env).stdout
            self.assertEqual(git(clone, 'check-attr', 'eol', '--', 'scripts/check.sh', '.githooks/pre-commit'),
                             'scripts/check.sh: eol: lf\n.githooks/pre-commit: eol: lf\n')

    def test_a_signal_while_printing_the_checklist_keeps_the_stamp(self):
        # A handler that only cleaned up let the run resume with the pending list deleted,
        # which reads as "no ACTION items", and stamp the version.
        with tempfile.TemporaryDirectory() as tmp:
            shims = Path(tmp) / 'shims'
            shims.mkdir()
            (shims / 'cat').write_text('#!/bin/sh\nkill -TERM "$PPID"\nexec "%s" "$@"\n'
                                       % shutil.which('cat'))
            (shims / 'cat').chmod(0o755)
            env = dict(os.environ, PATH=str(shims) + os.pathsep + os.environ['PATH'])
            result, stamp = self.sync(tmp, ACTION, env=env)
            self.assertEqual(stamp, '0.1', 'stamped after SIGTERM during the checklist')
            self.assertEqual(result.returncode, 143, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
