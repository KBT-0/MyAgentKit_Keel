"""sync-kit.sh must not stamp a version whose ACTION items the owner has not confirmed."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ACTION = '- A rule moved. **ACTION:** copy it into your project-owned workflow.\n'


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
        cases = (('core/.githooks/commit-msg', '.githooks', '.githooks/commit-msg (the symlink .githooks'),
                 ('overlays/o/files/scripts/tool.sh', 'scripts/tool.sh', 'scripts/tool.sh (the symlink scripts/tool.sh'))
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
