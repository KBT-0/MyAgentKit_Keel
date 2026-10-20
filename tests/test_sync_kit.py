"""sync-kit.sh must not stamp a version whose ACTION items the owner has not confirmed."""
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ACTION = '- A rule moved. **ACTION:** copy it into your project-owned workflow.\n'
WINDOWS = os.name == 'nt'
# A folder spelled in another letter case is the same folder on Windows and macOS by default;
# where it is not (Linux), the tests that need that spelling are declared platform skips.
CASE_FOLDS = Path(tempfile.gettempdir().swapcase()).is_dir()


def not_on_windows(case, why):
    """True on native Windows, after the NOT RUN line the kit check collects (issue #56)."""
    if WINDOWS:
        sys.stderr.write('\nNOT RUN: %s (POSIX only: %s)\n' % (case, why))
    return WINDOWS


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



def textwrap_dedent_dev_setup():
    """Read DEV_SETUP's repair command, resolving its project path to the kit source."""
    section = (ROOT / 'core/docs/DEV_SETUP.md').read_text(encoding='utf-8')
    section = section.split('**Line endings.**', 1)[1].split('## 2.', 1)[0]
    script = re.search(r'`sh (scripts/[^`\s]+)`', section)[1]
    return 'sh ' + shlex.quote((ROOT / 'core' / script).as_posix())

class SyncKitTests(unittest.TestCase):
    def sync(self, tmp, entry, *flags, env=None):
        kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
        if not kit.exists():
            kit.mkdir()
            shutil.copyfile(ROOT / 'sync-kit.sh', kit / 'sync-kit.sh')
            # UTF-8: native Windows wrote cp1252 and mangled the dash of "**ACTION** — none".
            (kit / 'CHANGELOG.md').write_text('## v0.2\n\n' + entry + '\n## v0.1\n\n- First.\n', encoding='utf-8')
            (project / 'docs/kit').mkdir(parents=True)
            # Bytes: a stamp is LF, as sync-kit writes it. Text mode wrote CRLF on native Windows
            # outside the kit check (which forces LF), and a stamp left whole compared as changed.
            (project / 'docs/kit/.kit-version').write_bytes(b'0.1\n')
        result = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project), *flags],
                                capture_output=True, text=True, env=env)
        stamp = (project / 'docs/kit/.kit-version').read_text().strip()
        return result, stamp

    @staticmethod
    def tick(project, item=b''):
        """Tick the boxes of docs/kit/UPGRADE.md (only those holding `item`, when given)."""
        listing = Path(project) / 'docs/kit/UPGRADE.md'
        lines = listing.read_bytes().split(b'\n')
        listing.write_bytes(b'\n'.join(line.replace(b'- [ ] ', b'- [x] ', 1) if item in line else line
                                       for line in lines))

    def test_unconfirmed_action_keeps_the_stamp_and_reappears(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            listing = project / 'docs/kit/UPGRADE.md'
            for _ in range(2):
                result, stamp = self.sync(tmp, ACTION)
                self.assertEqual(stamp, '0.1', 'stamped past an unconfirmed ACTION')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('- [ ] v0.2: **ACTION:** copy it', listing.read_text(encoding='utf-8'))
                self.assertNotIn('already current', result.stdout)
            # One flag no longer confirms a list nobody ticked (#129).
            result, stamp = self.sync(tmp, ACTION, '--actions-applied')
            self.assertEqual((result.returncode, stamp), (2, '0.1'), result.stdout + result.stderr)
            self.assertIn('1 items in docs/kit/UPGRADE.md are not ticked', result.stdout)
            self.tick(project)
            # A checklist checked out or saved with CRLF keeps its ticks. Git for Windows' gawk
            # drops a CR on read, a POSIX awk does not: BINMODE keeps it for the checklist's read.
            listing.write_bytes(listing.read_bytes().replace(b'\n', b'\r\n'))
            shims = Path(tmp) / 'shims'
            shims.mkdir()
            (shims / 'awk').write_text('#!/bin/sh\nPATH=${PATH#*:}\n'
                                       'case "$*" in *ck=*) exec awk -v BINMODE=rw "$@" ;; esac\n'
                                       'exec awk "$@"\n', newline='\n')
            (shims / 'awk').chmod(0o755)
            env = dict(os.environ, PATH=str(shims) + os.pathsep + os.environ['PATH'])
            result, stamp = self.sync(tmp, ACTION, '--actions-applied', env=env)
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            self.assertFalse(listing.exists(), 'the checklist is deleted once the version is recorded')
            result, _ = self.sync(tmp, ACTION)
            self.assertIn('already current', result.stdout)
            self.assertNotIn('ACTION', result.stdout)

    def test_the_checklist_is_oldest_first_one_item_per_marker_and_keeps_its_ticks(self):
        # Printed newest first, an item marked "first" came 79 items late, and a second marker
        # in one paragraph was printed inside the item before it (#99). A session that applied
        # half the list left the next one the same full list (#129).
        entry = ('- Two steps. **ACTION:** merge the gate selector,\n  then check it.'
                 ' **ACTION:** push the kit.\n\n## v0.1.5\n\n- Older. **ACTION:** line endings first.\n')
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            result, _ = self.sync(tmp, entry, '--dry-run')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('  v0.1.5: **ACTION:** line endings first.\n'
                          '  v0.2: **ACTION:** merge the gate selector, then check it.\n'
                          '  v0.2: **ACTION:** push the kit.\n', result.stdout)
            self.assertFalse((project / 'docs/kit/UPGRADE.md').exists(), 'a dry run writes no checklist')
            self.sync(tmp, entry)
            self.tick(project, b'line endings')
            result, stamp = self.sync(tmp, entry)
            self.assertEqual((result.returncode, stamp), (2, '0.1'), result.stdout + result.stderr)
            self.assertIn('2 of them not ticked', result.stdout)
            listing = (project / 'docs/kit/UPGRADE.md').read_text(encoding='utf-8')
            self.assertIn('- [x] v0.1.5: **ACTION:** line endings first.', listing)
            self.assertIn('- [ ] v0.2: **ACTION:** push the kit.', listing)
            # No changelog slice: the run lists the checklist's place and its counts, no entry.
            self.assertNotIn('Two steps', result.stdout)

    def test_a_run_whose_reader_is_gone_still_records_the_version(self):
        # `sync-kit.sh . --actions-applied | head` died of SIGPIPE before the stamp and looked
        # like a success (#78): the report is printed once the run is done.
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            self.sync(tmp, '- A kit-owned file changed.\n', '--dry-run')
            (kit / 'core/scripts').mkdir(parents=True)
            for n in range(20):
                (kit / ('core/scripts/tool%d.sh' % n)).write_text('#!/bin/sh\n# KIT-OWNED: fixture\n')
            temp = Path(tmp) / 'temp'
            temp.mkdir()
            run = subprocess.Popen(['sh', str(kit / 'sync-kit.sh'), str(project), '--actions-applied'],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   env=dict(os.environ, TMPDIR=str(temp)))
            run.stdout.close()
            self.assertEqual(run.wait(timeout=120), 0)
            self.assertEqual((project / 'docs/kit/.kit-version').read_text().strip(), '0.2')
            self.assertTrue((project / 'scripts/tool19.sh').is_file())
            # The failed print of the held report ended the exit trap before its cleanup.
            self.assertEqual(list(temp.iterdir()), [], 'the held report was left behind')

    def test_the_help_ends_on_a_whole_sentence(self):
        help = subprocess.run(['sh', str(ROOT / 'sync-kit.sh'), '--help'], capture_output=True, text=True).stdout
        self.assertTrue(help.rstrip().endswith('.'), help.splitlines()[-1])

    def test_a_project_newer_than_the_kit_or_on_an_unknown_version_is_refused_unchanged(self):
        # Compared as strings, a project stamped 0.12 against a v0.11 kit clone had its hooks
        # rolled back and the older version recorded; an unknown one printed every item (#113).
        for have, needle in (('0.10', 'newer than this kit'), ('0.1.9', 'no version in'),
                             ('0.2.1', 'newer than this kit'), ('v0.1', 'no version')):
            with self.subTest(have=have), tempfile.TemporaryDirectory() as tmp:
                kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
                self.sync(tmp, ACTION, '--dry-run')
                (kit / 'core/scripts').mkdir(parents=True)
                (kit / 'core/scripts/doctor.sh').write_text('#!/bin/sh\n# KIT-OWNED: fixture\n')
                (project / 'docs/kit/.kit-version').write_bytes(have.encode() + b'\n')
                for flags in ((), ('--actions-applied',)):
                    result, stamp = self.sync(tmp, ACTION, *flags)
                    self.assertEqual((result.returncode, stamp), (1, have), result.stdout + result.stderr)
                    self.assertIn(needle, result.stderr)
                    self.assertFalse((project / 'scripts').exists(), 'copied before the version check')

    def test_the_same_version_still_refreshes_kit_owned_files(self):
        # "already current" compared only the version strings, so a kit-owned fix made inside
        # a release never reached a project synced earlier in it (#98).
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            self.sync(tmp, '- A change.\n', '--dry-run')
            (project / 'docs/kit/.kit-version').write_bytes(b'0.2\n')
            (kit / 'core/scripts').mkdir(parents=True)
            (kit / 'core/scripts/doctor.sh').write_text('#!/bin/sh\n# KIT-OWNED: fixture\necho fixed\n')
            (project / 'scripts').mkdir()
            (project / 'scripts/doctor.sh').write_text('#!/bin/sh\n# KIT-OWNED: fixture\n')
            result, stamp = self.sync(tmp, '- A change.\n')
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            self.assertIn('update:  scripts/doctor.sh', result.stdout)
            self.assertIn('echo fixed', (project / 'scripts/doctor.sh').read_text())

    def test_an_action_item_added_inside_a_version_is_pending_after_the_kit_commit(self):
        # A project synced partway through a release never saw the items the release gained
        # after its sync (#98). The kit commit of the last stamp tells them apart.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            first = '- Old. **ACTION:** the old step.\n'
            self.sync(tmp, first, '--dry-run')
            git = lambda *a: subprocess.run(['git', '-C', str(kit), *a], check=True, env=env,
                                            capture_output=True, text=True).stdout.strip()
            git('init', '-q')
            git('add', '-A')
            git('-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'one')
            (project / 'docs/kit/.kit-version').write_bytes(b'0.2\n')
            (project / 'docs/kit/.kit-commit').write_text(git('rev-parse', 'HEAD') + '\n')
            result, stamp = self.sync(tmp, first)
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            self.assertIn('already current', result.stdout)
            later = first + '- New. **ACTION:** the new step.\n'
            (kit / 'CHANGELOG.md').write_text('## v0.2\n\n' + later + '\n## v0.1\n\n- First.\n', encoding='utf-8')
            git('-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qam', 'two')
            result, stamp = self.sync(tmp, first)
            self.assertEqual((result.returncode, stamp), (2, '0.2'), result.stdout + result.stderr)
            listing = (project / 'docs/kit/UPGRADE.md').read_text(encoding='utf-8')
            self.assertIn('v0.2: **ACTION:** the new step.', listing)
            self.assertNotIn('the old step', listing)
            self.tick(project)
            result, _ = self.sync(tmp, first, '--actions-applied')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((project / 'docs/kit/.kit-commit').read_text().strip(), git('rev-parse', 'HEAD'))

    def test_an_unreleased_section_is_listed_as_its_version_and_stays_ticked_past_the_release(self):
        # A sync from the kit's master copied the unreleased kit-owned files and said "already
        # current", without the items they need: the "## Unreleased" heading was never read.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            self.sync(tmp, '- A change.\n', '--dry-run')
            git = lambda *a: subprocess.run(['git', '-C', str(kit), '-c', 'user.name=F', '-c', 'user.email=f@example.invalid',
                                             *a], check=True, env=env, capture_output=True, text=True).stdout.strip()
            git('init', '-q')
            git('add', '-A')
            git('commit', '-qm', 'v0.2')
            (project / 'docs/kit/.kit-version').write_bytes(b'0.2\n')
            (project / 'docs/kit/.kit-commit').write_text(git('rev-parse', 'HEAD') + '\n')
            log = (kit / 'CHANGELOG.md').read_text(encoding='utf-8')
            (kit / 'CHANGELOG.md').write_text('## Unreleased — v0.3\n\n- A new hook. **ACTION:** register it.\n\n' + log,
                                              encoding='utf-8')
            (kit / 'core/scripts').mkdir(parents=True)
            (kit / 'core/scripts/hook.sh').write_text('#!/bin/sh\n# KIT-OWNED: fixture\n')
            git('add', '-A')
            git('commit', '-qm', 'unreleased')
            result, stamp = self.sync(tmp, '', env=env)
            self.assertEqual((result.returncode, stamp), (2, '0.2'), result.stdout + result.stderr)
            self.assertNotIn('already current', result.stdout)
            self.assertIn('- [ ] v0.3: **ACTION:** register it.', (project / 'docs/kit/UPGRADE.md').read_text(encoding='utf-8'))
            self.tick(project)
            result, stamp = self.sync(tmp, '', '--actions-applied', env=env)
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            (kit / 'CHANGELOG.md').write_text((kit / 'CHANGELOG.md').read_text(encoding='utf-8').replace(
                '## Unreleased — v0.3', '## v0.3 — 2026-10-20'), encoding='utf-8')
            git('commit', '-qam', 'release')
            result, stamp = self.sync(tmp, '', env=env)
            self.assertEqual((result.returncode, stamp), (0, '0.3'), result.stdout + result.stderr)
            self.assertNotIn('register it', result.stdout)

    def test_an_uncommitted_edit_to_a_kit_owned_file_stops_the_sync(self):
        # The copy replaced a kit-owned file the owner had edited and not committed, with no
        # backup (#128). A staged edit stays in the index, and the copy goes ahead.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            self.sync(tmp, '- A change.\n', '--dry-run')
            (kit / 'core/scripts').mkdir(parents=True)
            (kit / 'core/scripts/doctor.sh').write_text('#!/bin/sh\n# KIT-OWNED: fixture\necho kit\n')
            (project / 'scripts').mkdir()
            doctor = project / 'scripts/doctor.sh'
            doctor.write_text('#!/bin/sh\n# KIT-OWNED: fixture\n')
            git = lambda *a: subprocess.run(['git', '-C', str(project), *a], check=True, env=env,
                                            capture_output=True, text=True)
            git('init', '-q')
            git('add', '-A')
            git('-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'one')
            doctor.write_text('#!/bin/sh\n# KIT-OWNED: fixture\necho tuned by hand\n')
            result, stamp = self.sync(tmp, '- A change.\n', env=env)
            self.assertEqual((result.returncode, stamp), (1, '0.1'), result.stdout + result.stderr)
            self.assertIn('conflict: scripts/doctor.sh (uncommitted edits', result.stdout)
            self.assertIn('tuned by hand', doctor.read_text())
            git('add', 'scripts/doctor.sh')
            result, stamp = self.sync(tmp, '- A change.\n', env=env)
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            self.assertIn('echo kit', doctor.read_text())

    def test_the_syncs_own_uncommitted_copies_are_no_edit_after_the_kit_moved(self):
        # A run that stopped at its ACTION items left its copies unstaged (a new one untracked);
        # once the kit moved, the next run read them as the owner's edits and stopped on them.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            self.sync(tmp, ACTION, '--dry-run')
            (kit / 'core/scripts').mkdir(parents=True)
            doctor, tool = kit / 'core/scripts/doctor.sh', kit / 'core/scripts/tool.sh'
            (project / 'scripts').mkdir()
            (project / 'scripts/doctor.sh').write_text('#!/bin/sh\n# KIT-OWNED: fixture\n')
            for repo in (kit, project):
                subprocess.run(['git', 'init', '-q', str(repo)], check=True, env=env)
            commit = lambda repo, *a: subprocess.run(
                ['git', '-C', str(repo), '-c', 'user.name=F', '-c', 'user.email=f@example.invalid',
                 'commit', '-q', *a], check=True, env=env, capture_output=True)
            subprocess.run(['git', '-C', str(project), 'add', '-A'], check=True, env=env)
            commit(project, '-m', 'one')
            for n in (1, 2):
                doctor.write_text('#!/bin/sh\n# KIT-OWNED: fixture\necho kit %d\n' % n)
                tool.write_text('#!/bin/sh\n# KIT-OWNED: fixture\necho tool %d\n' % n)
                subprocess.run(['git', '-C', str(kit), 'add', '-A'], check=True, env=env)
                commit(kit, '-m', 'kit %d' % n)
                result, stamp = self.sync(tmp, ACTION, env=env)
                self.assertEqual((result.returncode, stamp), (2, '0.1'), result.stdout + result.stderr)
                self.assertNotIn('conflict', result.stdout)
                self.assertIn('echo kit %d' % n, (project / 'scripts/doctor.sh').read_text())
                self.assertIn('echo tool %d' % n, (project / 'scripts/tool.sh').read_text())
            # An edit of the owner's is still one.
            (project / 'scripts/doctor.sh').write_text('#!/bin/sh\n# KIT-OWNED: fixture\necho tuned\n')
            doctor.write_text('#!/bin/sh\n# KIT-OWNED: fixture\necho kit 3\n')
            commit(kit, '-am', 'kit 3')
            result, stamp = self.sync(tmp, ACTION, env=env)
            self.assertEqual((result.returncode, stamp), (1, '0.1'), result.stdout + result.stderr)
            self.assertIn('conflict: scripts/doctor.sh (uncommitted edits', result.stdout)

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

    def test_colon_action_none_is_not_pending_but_real_actions_still_are(self):
        for entry, pending in (('**ACTION:** none.', False), ('**ACTION** — none', False),
                               ('**ACTION:** none. Copy the project rules.', True),
                               ('**ACTION:** nonetheless, copy the rules.', True)):
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as tmp:
                result, stamp = self.sync(tmp, '- A change. ' + entry + '\n')
                self.assertEqual((result.returncode, stamp), (2, '0.1') if pending else (0, '0.2'),
                                 result.stdout + result.stderr)

    def test_updating_describes_action_lines_without_promising_per_version_checklists(self):
        updating = ' '.join((ROOT / 'docs/UPDATING.md').read_text(encoding='utf-8').split())
        self.assertIn('sync-kit.sh . --dry-run', updating)
        self.assertNotIn('each version\'s entry ends with one ordered checklist', updating)

    def test_sync_preserves_project_owned_plain_report_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.sync(tmp, '- A change.\n', '--dry-run')
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            config = project / '.claude/plain_report_labels.json'
            config.parent.mkdir()
            body = '["\\\\bPR-\\\\d+\\\\b", "\\\\bREADY\\\\b"]\n'
            config.write_bytes(body.encode())
            source = kit / 'core/.githooks/commit-msg'
            source.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / 'core/.githooks/commit-msg', source)
            result, stamp = self.sync(tmp, '- A change.\n')
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            self.assertTrue((project / '.githooks/commit-msg').is_file())
            self.assertEqual(config.read_bytes(), body.encode())

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

    def test_the_gitattributes_is_project_owned_so_a_sync_keeps_merge_and_lfs_rules(self):
        # With a KIT-OWNED header the sync replaced a project's .gitattributes wholesale: its
        # Unity merge driver and LFS rules were gone. The file is project-owned now.
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            self.sync(tmp, '- A kit-owned file changed.\n', '--dry-run')
            (kit / 'core').mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'core/.gitattributes', kit / 'core/.gitattributes')
            own = '*.unity merge=unityyamlmerge\n*.png filter=lfs diff=lfs merge=lfs -text\n'
            (project / '.gitattributes').write_text(own)
            result, _ = self.sync(tmp, '', '--actions-applied')
            self.assertEqual((project / '.gitattributes').read_text(), own, result.stdout + result.stderr)
            self.assertNotIn('conflict: .gitattributes', result.stdout + result.stderr)
            self.assertNotIn('KIT-OWNED', (ROOT / 'core/.gitattributes').read_text())

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

    def test_a_project_reviewer_agent_beside_diff_reviewer_is_listed_and_left_alone(self):
        # The sync left a project's own reviewer agent beside the kit's diff-reviewer.md
        # without a word, and the lead could pick either (#161). A reviewer is named by its
        # front matter `name:`, read in subfolders too, after a BOM too; a worker that mentions
        # reviews in its description, or a "ui-preview", is not one. Where letter case folds,
        # Diff-Reviewer.md is the kit's own file, not a second one.
        agents = {'Diff-Reviewer.md' if CASE_FOLDS else 'diff-reviewer.md': '---\nname: diff-reviewer\n---\nkit\n',
                  'code-reviewer.md': '---\r\nname: Code-Reviewer\r\n---\r\nours\r\n',
                  'review/pr_reviewer.md': '﻿---\nname: "PR_Reviewer"\n---\n',
                  'ui-preview.md': '---\nname: ui-preview\n---\n',
                  'worker.md': '---\nname: worker\ndescription: a fresh session reviews the fix\n---\nname: review\n',
                  'notes.md': 'name: reviewer\n'}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'project/.claude/agents'
            (folder / 'review').mkdir(parents=True)
            for name, text in agents.items():
                (folder / name).write_bytes(text.encode())
            result, stamp = self.sync(tmp, '- A kit-owned file changed.\n')
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            listed = [line for line in result.stdout.splitlines() if '.claude/agents' in line]
            self.assertEqual(listed, ["  conflict: .claude/agents/%s (a second reviewer agent beside "
                                      "diff-reviewer.md: keep one of the two, the kit's docs/UPDATING.md)" % name
                                      for name in ('code-reviewer.md', 'review/pr_reviewer.md')])
            self.assertEqual({p.relative_to(folder).as_posix(): p.read_bytes().decode()
                              for p in folder.rglob('*.md')}, agents)
            # The owner kept their own: nothing is left to list.
            (folder / 'diff-reviewer.md').unlink()
            result, stamp = self.sync(tmp, '- A kit-owned file changed.\n')
            self.assertNotIn('.claude/agents', result.stdout)

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
            self.tick(project)
            result, stamp = self.sync(tmp, ACTION, '--actions-applied')
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            self.assertEqual((project / 'scripts/doctor.sh').read_text(), new)
        # The checklist says so before its first item, and item 5 says the stamp copies nothing new.
        checklist = (ROOT / 'CHANGELOG.md').read_text().split('### Upgrading a project from v0.9', 1)[1]
        intro, items = checklist.split('\n1. ', 1)
        self.assertIn('Start with `"$KIT/sync-kit.sh" .`', intro)
        self.assertIn('copies nothing new', items.split('\n5. ', 1)[1].split('\n## ', 1)[0])

    def test_the_behaviour_appendix_is_kit_owned_and_reaches_the_project_root(self):
        # spawn_worker.sh and claude_bridge.py read BEHAVIOUR.md at the project's root; a sync
        # installs it there and refreshes it, as it does every file with the KIT-OWNED header.
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            self.sync(tmp, ACTION, '--dry-run')
            (kit / 'core').mkdir()
            shutil.copyfile(ROOT / 'core/BEHAVIOUR.md', kit / 'core/BEHAVIOUR.md')
            result, _ = self.sync(tmp, ACTION)
            self.assertIn('new:     BEHAVIOUR.md', result.stdout, result.stdout + result.stderr)
            self.assertEqual((project / 'BEHAVIOUR.md').read_bytes(), (ROOT / 'core/BEHAVIOUR.md').read_bytes())

    def test_the_checklist_runs_kit_scripts_only_from_a_fresh_full_clone(self):
        # Its first command runs the kit's sync-kit.sh. A v0.9 kit clone made with
        # core.autocrlf=true keeps that script CRLF after a pull, so it cannot start; a shallow
        # clone lacks 00581dd, which item 3 merges from. The checklist and DEV_SETUP say so first.
        checklist = (ROOT / 'CHANGELOG.md').read_text().split('### Upgrading a project from v0.9', 1)[1]
        intro = ' '.join(checklist.split('\n1. ', 1)[0].split())
        self.assertIn('`KIT` is a fresh, full clone of the kit at v0.10 or later', intro)
        self.assertLess(intro.index('fresh, full clone'), intro.index('Start with'))
        setup = ' '.join((ROOT / 'core/docs/DEV_SETUP.md').read_text().split())
        self.assertIn('upgrade from a fresh, full clone of the kit', setup)

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
            # Named by its path; Git for Windows' sh spells the folder above the kit its own way.
            self.assertIn(str(src) if not WINDOWS else 'kit/overlays/o/files/scripts/tool.sh', result.stdout)
            self.assertNotIn('rerun the sync to install', result.stdout)
            self.assertNotIn('RETROFIT', result.stdout)

    def test_a_kit_owned_path_that_is_not_a_regular_file_is_a_conflict_unread(self):
        # `cmp` on a FIFO at a kit-owned path blocked forever, and a symlink to an identical
        # copy read as "same": anything but a regular file is a conflict, never read.
        rel = '.githooks/commit-msg'
        for kind in ('fifo', 'identical symlink'):
            if kind == 'fifo' and not_on_windows(self.id() + ' (fifo)', 'no FIFOs'):
                continue
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
            if case == 'fifo stamp' and not_on_windows(self.id() + ' (fifo stamp)', 'no FIFOs'):
                continue
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

    def test_a_written_hook_or_script_gets_the_executable_mode_in_the_git_index(self):
        # With core.fileMode=false (native Windows) the disk's chmod never reached the index:
        # a hook the sync wrote was committed at 100644 and a POSIX clone skipped it (#182).
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        hook, new, doc = '.githooks/commit-msg', 'scripts/doctor.sh', 'docs/COMMUNICATION.md'
        for sub in ('', 'app'):
            with self.subTest(subfolder=sub), tempfile.TemporaryDirectory() as tmp:
                kit, top = Path(tmp) / 'kit', Path(tmp) / 'project'
                self.sync(tmp, ACTION, '--dry-run')
                project = top / sub
                if sub:
                    shutil.move(str(top / 'docs'), str(Path(tmp) / 'docs'))
                    project.mkdir()
                    shutil.move(str(Path(tmp) / 'docs'), str(project / 'docs'))
                for rel in (hook, new, doc):
                    (kit / 'core' / rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / 'core' / rel, kit / 'core' / rel)
                (project / '.githooks').mkdir()
                (project / hook).write_text('# KIT-OWNED: old\n')
                git = lambda *a: subprocess.run(['git', *a], cwd=top, check=True, env=env,
                                                capture_output=True, text=True).stdout
                git('init', '-q')
                git('config', 'core.fileMode', 'false')
                git('add', '-A')
                old_blob = git('ls-files', '-s', sub + '/' + hook if sub else hook).split()[1]
                run = lambda *a: subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project), *a], env=env,
                                                capture_output=True, text=True, timeout=60)
                listed = lambda: {line.split('\t')[1]: line.split()[:2]
                                  for line in git('ls-files', '-s').splitlines()}
                prefix = sub + '/' if sub else ''
                # A run that stops on ACTION items stages nothing new (round 1).
                result = run()
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNotIn(prefix + new, listed())
                self.assertEqual(listed()[prefix + hook], ['100755', old_blob], 'staged bytes kept')
                self.tick(project)
                result = run('--actions-applied')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                staged = listed()
                self.assertEqual(staged[prefix + hook], ['100755', old_blob], 'staged bytes kept')
                self.assertNotIn(prefix + doc, staged, 'a doc is not staged')
                if sub:
                    self.assertNotIn(prefix + new, staged)
                    self.assertIn('git add --chmod=+x -- "%s"' % new, result.stdout)
                else:
                    self.assertEqual(staged[new][0], '100755')

    def test_merge_merges_only_what_the_kit_changed_and_lists_conflicts_by_line(self):
        # Merging project-owned docs whole, one agent each, read 8.3M cache tokens in one
        # upgrade (#184): the script merges, skips what the kit left alone, and names only the
        # conflict lines for a reader.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            self.sync(tmp, '- A change.\n', '--dry-run')
            files = {'docs/WORKFLOW.md': ('a\nb\nc\nd\ne\n', 'a\nB kit\nc\nd\ne\n', 'a\nb\nc\nd\nE mine\n'),
                     'docs/GOTCHAS.md': ('x\ny\n', 'x\nY kit\n', 'x\nY mine\n'),
                     'docs/STATE.md': ('same\n', 'same\n', 'mine\n'),
                     'docs/OLD.md': ('old\n', None, 'old\n'),
                     '.githooks/commit-msg': ('# KIT-OWNED: x\none\n', '# KIT-OWNED: x\ntwo\n',
                                              '# KIT-OWNED: x\r\none\r\n')}
            for rel, (base, _, mine) in files.items():
                (kit / 'core' / rel).parent.mkdir(parents=True, exist_ok=True)
                (kit / 'core' / rel).write_bytes(base.encode())
                if mine is not None:
                    (project / rel).parent.mkdir(parents=True, exist_ok=True)
                    (project / rel).write_bytes(mine.encode())
            git = lambda *a: subprocess.run(['git', '-C', str(kit), *a], check=True, env=env,
                                            capture_output=True, text=True).stdout.strip()
            git('init', '-q')
            git('add', '-A')
            git('-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'v0.1')
            base = git('rev-parse', 'HEAD')
            for rel, (_, now, _) in files.items():
                if now is not None:
                    (kit / 'core' / rel).write_bytes(now.encode())
            (kit / 'core/scripts').mkdir()
            (kit / 'core/scripts/new.sh').write_bytes(b'echo new\n')
            (kit / 'core/docs/OLD.md').unlink()
            run = lambda *a: subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project), *a], env=env,
                                            capture_output=True, text=True, timeout=60)
            result = run('--merge')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('pass --base <commit>', result.stderr)
            # A later base than the project's own: its kit-owned copies give it away, and a
            # merge from it would keep the old lines without a conflict.
            git('add', '-A')
            git('-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'v0.2')
            result = run('--merge', '--base', 'HEAD')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('did not come from it', result.stderr)
            self.assertIn('    .githooks/commit-msg', result.stderr)
            self.assertNotIn('docs/WORKFLOW.md', result.stderr)
            self.assertEqual((project / 'docs/WORKFLOW.md').read_bytes(), b'a\nb\nc\nd\nE mine\n')
            self.assertEqual((project / '.githooks/commit-msg').read_bytes(), b'# KIT-OWNED: x\r\none\r\n',
                             'a stopped --merge wrote nothing')
            result = run('--merge', '--base', base)
            out = result.stdout
            self.assertEqual(result.returncode, 2, out + result.stderr)
            self.assertEqual((project / 'docs/kit/.kit-version').read_text(), '0.1\n')
            self.assertEqual((project / 'docs/WORKFLOW.md').read_bytes(), b'a\nB kit\nc\nd\nE mine\n')
            self.assertIn('  merged:   docs/WORKFLOW.md', out)
            self.assertIn('  conflict: docs/GOTCHAS.md, lines 2-6', out)
            self.assertIn('Y mine', (project / 'docs/GOTCHAS.md').read_text())
            self.assertIn('  kit-new:  scripts/new.sh', out)
            self.assertIn('  kit-removed: docs/OLD.md', out)
            self.assertNotIn('docs/STATE.md', out)
            self.assertEqual((project / 'docs/STATE.md').read_bytes(), b'mine\n')
            self.assertNotIn('.githooks/commit-msg', out.split('PROJECT-OWNED')[1])
            # The recorded base is read without --base; a file still holding markers is refused.
            (project / 'docs/kit/.kit-commit').write_bytes(base.encode() + b'\n')
            result = run('--merge')
            self.assertIn('  unresolved: docs/GOTCHAS.md', result.stdout)
            # No stamp while a project-owned file holds markers: it moved the base past them (round 1).
            result = run()
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('    docs/GOTCHAS.md', result.stderr)
            self.assertEqual((project / 'docs/kit/.kit-version').read_text(), '0.1\n')
            self.assertEqual((project / 'docs/kit/.kit-commit').read_text().strip(), base)
            (project / 'docs/GOTCHAS.md').write_bytes(b'x\nY mine\n')
            result = run()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((project / 'docs/kit/.kit-commit').read_text().strip(), git('rev-parse', 'HEAD'))

    def merge_kit(self, tmp, entry, files):
        """A kit whose commits hold `files` {rel: (at base, at HEAD)}; returns (kit, project, base, env)."""
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
        self.sync(tmp, entry, '--dry-run')
        git = lambda *a: subprocess.run(['git', '-C', str(kit), *a], check=True, env=env,
                                        capture_output=True, text=True).stdout.strip()
        git('init', '-q')
        base = None
        for side in (0, 1):
            for rel, bodies in files.items():
                (kit / 'core' / rel).parent.mkdir(parents=True, exist_ok=True)
                (kit / 'core' / rel).write_bytes(bodies[side])
            git('add', '-A')
            git('-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'v0.%d' % (side + 1))
            base = base or git('rev-parse', 'HEAD')
        return kit, project, base, env

    def test_merge_reads_kit_blobs_and_keeps_a_crlf_project_copy_crlf(self):
        # With autocrlf the kit's working-tree docs are CRLF over LF blobs: compared with the base
        # blob, every doc read as kit-changed and every project line conflicted (round 1).
        with tempfile.TemporaryDirectory() as tmp:
            kit, project, base, env = self.merge_kit(tmp, '- A change.\n', {
                'docs/SAME.md': (b'one\ntwo\n', b'one\ntwo\n'),
                'docs/CHANGED.md': (b'a\nb\nc\n', b'a\nB kit\nc\n')})
            for rel in ('docs/SAME.md', 'docs/CHANGED.md'):
                body = (kit / 'core' / rel).read_bytes()
                (kit / 'core' / rel).write_bytes(body.replace(b'\n', b'\r\n'))
            (project / 'docs/SAME.md').write_bytes(b'one\r\ntwo\r\nmine\r\n')
            (project / 'docs/CHANGED.md').write_bytes(b'a\r\nb\r\nc\r\nmine\r\n')
            result = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project), '--merge', '--base', base],
                                    env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertNotIn('docs/SAME.md', result.stdout)
            self.assertEqual((project / 'docs/SAME.md').read_bytes(), b'one\r\ntwo\r\nmine\r\n')
            self.assertIn('  merged:   docs/CHANGED.md', result.stdout)
            self.assertEqual((project / 'docs/CHANGED.md').read_bytes(), b'a\r\nB kit\r\nc\r\nmine\r\n')

    def test_the_right_base_passes_after_tier_one_overwrote_the_kit_owned_files(self):
        # A plain sync before --merge, or a second --merge, had overwritten the kit-owned copies
        # the base is checked against, and the right base was refused (round 1).
        hook = '.githooks/commit-msg'
        for sequence in ('plain sync, then --merge', '--merge twice'):
            with self.subTest(sequence=sequence), tempfile.TemporaryDirectory() as tmp:
                kit, project, base, env = self.merge_kit(tmp, ACTION, {
                    hook: (b'# KIT-OWNED: x\none\n', b'# KIT-OWNED: x\ntwo\n'),
                    'docs/WORKFLOW.md': (b'a\nb\nc\nd\n', b'a\nB kit\nc\nd\n')})
                (project / '.githooks').mkdir()
                (project / hook).write_bytes(b'# KIT-OWNED: x\none\n')
                (project / 'docs/WORKFLOW.md').write_bytes(b'a\nb\nc\nd\nmine\n')
                for args in (['init', '-q'], ['add', '-A'],
                             ['-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'p']):
                    subprocess.run(['git', '-C', str(project), *args], check=True, env=env, capture_output=True)
                run = lambda *a: subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project), *a], env=env,
                                                capture_output=True, text=True, timeout=60)
                first = run() if sequence.startswith('plain') else run('--merge', '--base', base)
                self.assertEqual(first.returncode, 2, first.stdout + first.stderr)
                self.assertEqual((project / hook).read_bytes(), b'# KIT-OWNED: x\ntwo\n')
                result = run('--merge', '--base', base)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNotIn('did not come from it', result.stderr)
                self.assertEqual((project / 'docs/WORKFLOW.md').read_bytes(), b'a\nB kit\nc\nd\nmine\n')

    def test_the_right_base_passes_after_a_plain_sync_was_committed_and_a_later_one_is_still_refused(self):
        # The owner's manual check of #184: committing a plain sync's kit-owned copies before
        # --merge made the check read the later kit's copies, and the right base was refused.
        hook = '.githooks/commit-msg'
        with tempfile.TemporaryDirectory() as tmp:
            kit, project, base, env = self.merge_kit(tmp, ACTION, {
                hook: (b'# KIT-OWNED: x\none\n', b'# KIT-OWNED: x\ntwo\n'),
                'docs/WORKFLOW.md': (b'a\nb\nc\nd\n', b'a\nB kit\nc\nd\n')})
            (project / '.githooks').mkdir()
            (project / hook).write_bytes(b'# KIT-OWNED: x\none\n')
            (project / 'docs/WORKFLOW.md').write_bytes(b'a\nb\nc\nd\nmine\n')
            pgit = lambda *a: subprocess.run(['git', '-C', str(project), '-c', 'user.name=F', '-c',
                                              'user.email=f@example.invalid', *a], check=True, env=env,
                                             capture_output=True)
            for args in (['init', '-q'], ['add', '-A'], ['commit', '-qm', 'install']):
                pgit(*args)
            run = lambda *a: subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project), *a], env=env,
                                            capture_output=True, text=True, timeout=300)
            first = run()
            self.assertEqual(first.returncode, 2, first.stdout + first.stderr)
            pgit('commit', '-qam', 'kit-owned files of the plain sync')
            later = subprocess.run(['git', '-C', str(kit), 'rev-parse', 'HEAD'], check=True, env=env,
                                   capture_output=True, text=True).stdout.strip()
            result = run('--merge', '--base', later)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('did not come from it', result.stderr)
            result = run('--merge', '--base', base)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertNotIn('did not come from it', result.stderr)
            self.assertEqual((project / 'docs/WORKFLOW.md').read_bytes(), b'a\nB kit\nc\nd\nmine\n')

    def test_a_kit_inside_another_repository_records_no_kit_commit(self):
        # A vendored kit recorded the outer repository's HEAD as its own base (round 1).
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        with tempfile.TemporaryDirectory() as tmp:
            for args in (['init', '-q'], ['-c', 'user.name=F', '-c', 'user.email=f@example.invalid',
                                         'commit', '-q', '--allow-empty', '-m', 'outer']):
                subprocess.run(['git', '-C', tmp, *args], check=True, env=env, capture_output=True)
            result, stamp = self.sync(tmp, '- A change.\n', env=env)
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            self.assertFalse((Path(tmp) / 'project/docs/kit/.kit-commit').exists())

    def test_a_kit_path_spelled_in_another_case_still_records_the_kit_commit(self):
        # The owner's manual check of #184: own_repo compared `pwd -P` strings, which keep the
        # spelling given, so a kit run as c:/users/... (or from a `subst` drive) recorded no base.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        if not CASE_FOLDS:
            self.skipTest('a case-sensitive filesystem has no other spelling of the kit path')
        with tempfile.TemporaryDirectory() as tmp:
            self.sync(tmp, '- A change.\n', '--dry-run')
            kit = Path(tmp) / 'kit'
            git = lambda *a: subprocess.run(['git', '-C', str(kit), *a], check=True, env=env,
                                            capture_output=True, text=True).stdout.strip()
            git('init', '-q')
            git('-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-q', '--allow-empty', '-m', 'k')
            result = subprocess.run(['sh', str(kit / 'sync-kit.sh').swapcase(), str(Path(tmp) / 'project')],
                                    capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            recorded = Path(tmp) / 'project/docs/kit/.kit-commit'
            self.assertTrue(recorded.exists(), 'no kit commit recorded')
            self.assertEqual(recorded.read_text().strip(), git('rev-parse', 'HEAD'))
    test_a_kit_path_spelled_in_another_case_still_records_the_kit_commit._kit_platform_skip = \
        not CASE_FOLDS

    def test_a_recorded_kit_commit_prints_the_kit_verified_review_of_the_upgrade(self):
        # #114: the upgrade commit is too big for one review; the sync names the review that
        # verifies the kit-owned files by hash. A kit that records no commit names none.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        command = "./scripts/review.sh --reviewer claude --commit <upgrade commit> --kit-verified --kit '"
        with tempfile.TemporaryDirectory() as tmp:
            listing = Path(tmp) / 'project/docs/kit/UPGRADE.md'
            result, _ = self.sync(tmp, ACTION, env=env)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertNotIn('--kit-verified', listing.read_text(encoding='utf-8'))
            kit = Path(tmp) / 'kit'
            for args in (['init', '-q'], ['-c', 'user.name=F', '-c', 'user.email=f@example.invalid',
                                         'commit', '-q', '--allow-empty', '-m', 'k']):
                subprocess.run(['git', '-C', str(kit), *args], check=True, env=env, capture_output=True)
            result, _ = self.sync(tmp, ACTION, env=env)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn(command, listing.read_text(encoding='utf-8'))
            self.tick(Path(tmp) / 'project')
            result, stamp = self.sync(tmp, ACTION, '--actions-applied', env=env)
            self.assertEqual((result.returncode, stamp), (0, '0.2'), result.stdout + result.stderr)
            self.assertIn(command, result.stdout)
            self.assertTrue((Path(tmp) / 'project/docs/kit/.kit-commit').exists())

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
        for fn in ('blocked', 'perms', 'stage', 'put', 'reviewers'):
            with self.subTest(fn=fn):
                self.assertEqual(body('sync-kit.sh', fn), body('bootstrap.sh', fn))

    def test_bootstrap_and_sync_mark_the_same_files_executable_and_no_text_file(self):
        # `.claude/hooks/*` matched after_compact.txt, so bootstrap staged a text file at 100755
        # (#273). Each script's `executable` runs on the same paths.
        paths = ['.githooks/pre-commit', 'scripts/check.sh', '.claude/hooks/py.sh', '.claude/hooks/plain_report.py',
                 '.claude/hooks/after_compact.txt', 'scripts/usage_summary.py', 'docs/WORKFLOW.md']
        marked = {}
        for name, call in (('bootstrap.sh', 'executable "$rel"; [ -n "$executables" ]'), ('sync-kit.sh', 'executable')):
            text = (ROOT / name).read_text()
            start = text.index('\nexecutable() {')
            fn = text[start:text.index('\n}\n', start) + 3] if name == 'bootstrap.sh' else text[start:text.index('\n', start + 1)]
            script = fn + '\nfor rel in "$@"; do executables=""; if %s; then echo "$rel"; fi; done\n' % call
            marked[name] = subprocess.run(['sh', '-c', script, 'sh', *paths], capture_output=True, text=True,
                                          check=True).stdout.split()
        self.assertEqual(marked['bootstrap.sh'], ['.githooks/pre-commit', 'scripts/check.sh', '.claude/hooks/py.sh',
                                                  '.claude/hooks/plain_report.py'])
        self.assertEqual(marked['sync-kit.sh'], marked['bootstrap.sh'])

    def test_every_printed_action_item_of_the_real_changelog_is_whole(self):
        # The checklist printed only the physical line holding the marker, so an owner
        # confirming it read "one would be. **ACTION:** copy" and twice nothing at all.
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            kit.mkdir()
            for name in ('sync-kit.sh', 'CHANGELOG.md'):
                shutil.copyfile(ROOT / name, kit / name)
            (project / 'docs/kit').mkdir(parents=True)
            # The oldest version: the items of every later version are listed.
            (project / 'docs/kit/.kit-version').write_text('0.1\n')
            result = subprocess.run(['sh', str(kit / 'sync-kit.sh'), str(project), '--dry-run'],
                                    capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            checklist = result.stdout.split('ACTION items since v0.1')[1].split('sync-kit: dry run')[0]
            items = []
            for line in checklist.splitlines()[1:]:
                if line.strip():
                    self.assertTrue(line.startswith('  v'), line)
                    items.append(line.split(': ', 1)[1].strip())
            self.assertGreater(len(items), 10)
            # One item per marker: a marker inside another item's text is an item of its own (#99).
            # An "## Unreleased" section is listed too, as the version its heading names.
            listed = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8').split('\n## v0.1 ', 1)[0]
            listed = listed[re.search(r'\n## (v|Unreleased)', listed).start():]
            markers = len(re.findall(r'\*\*ACTION(?!\*\* \u2014 none\.?[ \t]*$|:\*\*[ \t]+none\.[ \t]*$)',
                                     listed, re.M))
            self.assertEqual(len(items), markers)
            self.assertFalse([item for item in items if item.count('**ACTION') != 1])
            for item in items:
                after = item.split('**ACTION', 1)[1].lstrip('*: ')
                self.assertTrue(after.strip(), 'nothing after the marker: ' + item)
                self.assertRegex(item, r'[.!?:;][`*)"]*$', 'cut mid-sentence: ' + item)

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
            if not_on_windows(self.id() + ' (a name holding a newline)', 'Windows file names hold no newline'):
                del scripts['scripts/two\nlines.sh']
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
            # core.symlinks: Git for Windows checks a tracked symlink out as a plain file without it.
            git(tmp, '-c', 'core.autocrlf=true', '-c', 'core.symlinks=true', 'clone', '-q', str(project), str(clone))
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

    def test_the_line_ending_action_stops_at_a_gitattributes_that_is_not_a_regular_file(self):
        # Appending through a symlinked .gitattributes changed a file outside the repository,
        # which Git does not read as the repository's attributes. A symlink or a folder there
        # stops the step before it writes or stages anything.
        import textwrap
        text = (ROOT / 'CHANGELOG.md').read_text()
        block = next(part for part in text.split('```sh\n')[1:]
                     if 'core/.gitattributes' in part.split('```')[0])
        snippet = textwrap.dedent(block.split('```')[0])
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', KIT=str(ROOT))
        for kind in ('symlink', 'dangling symlink', 'folder'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                project, outside = Path(tmp) / 'project', Path(tmp) / 'outside'
                (project / 'scripts').mkdir(parents=True)
                (project / 'scripts/check.sh').write_bytes(b'#!/bin/sh\r\necho check ran\r\n')
                subprocess.run(['git', 'init', '-q'], cwd=project, check=True, env=env)
                subprocess.run(['git', 'add', '-A'], cwd=project, check=True, env=env)
                if kind == 'folder':
                    (project / '.gitattributes').mkdir()
                else:
                    if kind == 'symlink':
                        outside.write_bytes(b'*.bin binary\n')
                    (project / '.gitattributes').symlink_to(outside)
                result = subprocess.run(['sh', '-c', snippet], cwd=project, capture_output=True, text=True, env=env)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('STOP: .gitattributes is a symlink or not a regular file', result.stderr)
                if kind == 'symlink':
                    self.assertEqual(outside.read_bytes(), b'*.bin binary\n')
                else:
                    self.assertFalse(outside.exists())
                self.assertEqual((project / 'scripts/check.sh').read_bytes(), b'#!/bin/sh\r\necho check ran\r\n')

    def test_the_merge_action_keeps_its_copies_outside_the_project_and_stops_without_the_base(self):
        # The v0.9 copies were written at fixed names in the project: an owner's file there was
        # truncated and deleted, a symlink there wrote outside the repository, and a kit clone
        # without the base commit (a shallow one) went on to the next file, leaving files unmerged.
        # merge-file wrote through an owner's symlink at a file it merges, and in place.
        import textwrap
        text = (ROOT / 'CHANGELOG.md').read_text()
        block = next(part for part in text.split('```sh\n')[1:] if 'git merge-file' in part.split('```')[0])
        snippet = textwrap.dedent(block.split('```')[0])
        self.assertIn('620f25e', snippet)
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        names = ('scripts/check.sh', 'docs/DEV_SETUP.md', 'docs/GOTCHAS.md')
        for case in ('merged', 'no base commit', 'a file missing at the base', 'a symlinked file'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                kit, project, outside = Path(tmp) / 'kit', Path(tmp) / 'project', Path(tmp) / 'outside'
                for name in names:
                    if case != 'a file missing at the base' or name != 'docs/DEV_SETUP.md':
                        (kit / 'core' / name).parent.mkdir(parents=True, exist_ok=True)
                        (kit / 'core' / name).write_text('one\ntwo\nthree\n')
                    (project / name).parent.mkdir(parents=True, exist_ok=True)
                    (project / name).write_text('one\ntwo\nthree\nmine\n')
                (project / 'scripts/check.sh').chmod(0o755)
                shared = Path(tmp) / 'shared'
                if case == 'a symlinked file':
                    shared.write_text('one\ntwo\nthree\nmine\n')
                    (project / 'docs/GOTCHAS.md').unlink()
                    (project / 'docs/GOTCHAS.md').symlink_to(shared)
                subprocess.run(['git', 'init', '-q'], cwd=kit, check=True, env=env)
                subprocess.run(['git', 'add', '-A'], cwd=kit, check=True, env=env)
                subprocess.run(['git', '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm',
                                'v0.9'], cwd=kit, check=True, env=env)
                base = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=kit, check=True, capture_output=True,
                                      text=True, env=env).stdout.strip()
                for name in names:
                    (kit / 'core' / name).write_text('zero\none\ntwo\nthree\n')
                # An owner's file and a symlink at the names the old step wrote and deleted.
                (project / 'scripts/check.sh.v0.9').write_text('owner\n')
                outside.write_text('outside\n')
                (project / 'docs/DEV_SETUP.md.v0.9').symlink_to(outside)
                run = snippet.replace('620f25e', 'deadbeef' if case == 'no base commit' else base)
                result = subprocess.run(['sh', '-c', run], cwd=project, capture_output=True, text=True,
                                        env=dict(env, KIT=str(kit)))
                self.assertEqual((project / 'scripts/check.sh.v0.9').read_text(), 'owner\n')
                self.assertEqual(outside.read_text(), 'outside\n')
                self.assertTrue((project / 'docs/DEV_SETUP.md.v0.9').is_symlink())
                merged = {name: (project / name).read_text() == 'zero\none\ntwo\nthree\nmine\n' for name in names}
                if case == 'merged':
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(set(merged.values()), {True})
                    if not not_on_windows(self.id() + ' (mode kept)', 'no executable bit'):
                        self.assertEqual((project / 'scripts/check.sh').stat().st_mode & 0o777, 0o755)
                    self.assertEqual(sorted(p.name for p in (project / 'scripts').iterdir()),
                                     ['check.sh', 'check.sh.v0.9'])
                    continue
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertIn('STOP:', result.stderr)
                self.assertEqual(merged, {'scripts/check.sh': case == 'a file missing at the base',
                                          'docs/DEV_SETUP.md': False, 'docs/GOTCHAS.md': False})
                if case == 'a symlinked file':
                    self.assertEqual(shared.read_text(), 'one\ntwo\nthree\nmine\n')
                    self.assertTrue((project / 'docs/GOTCHAS.md').is_symlink())

    def checklist_block(self, marker):
        import textwrap
        text = (ROOT / 'CHANGELOG.md').read_text()
        block = next(part for part in text.split('```sh\n')[1:] if marker in part.split('```')[0])
        return textwrap.dedent(block.split('```')[0])

    def linked_upgrade_folder(self, marker, names, folder):
        import shlex
        snippet = self.checklist_block(marker)
        with tempfile.TemporaryDirectory() as tmp:
            kit, project, shared = (Path(tmp) / name for name in ('kit', 'project', 'shared'))
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                       KIT=kit.as_posix())
            for name in names:
                for root, body in ((kit / 'core', b'kit\n'), (project, b'owner\n')):
                    (root / name).parent.mkdir(parents=True, exist_ok=True)
                    (root / name).write_bytes(body)
            for repo in (kit, project):
                subprocess.run(['git', 'init', '-q', str(repo)], check=True, env=env)
            subprocess.run(['git', '-C', str(kit), 'add', '.'], check=True, env=env)
            subprocess.run(['git', '-C', str(kit), '-c', 'user.name=F', '-c', 'user.email=f@f',
                            '-c', 'commit.gpgsign=false', 'commit', '-qm', 'base'], check=True, env=env)
            env['KIT_BASE'] = 'HEAD'
            for name in names:
                (kit / 'core' / name).write_bytes(b'new kit\n')
            (project / folder).rename(shared)
            if os.name == 'nt':
                subprocess.run(['cmd', '/c', 'mklink', '/J', str(project / folder), str(shared)],
                               check=True, capture_output=True)
                snippet = snippet.replace('python3', shlex.quote(Path(sys.executable).as_posix()))
            else:
                (project / folder).symlink_to(shared, target_is_directory=True)
            before = {p.name: p.read_bytes() for p in shared.iterdir()}
            result = subprocess.run(['sh', '-c', snippet], cwd=project, env=env,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('STOP:', result.stderr)
            self.assertIn(folder, result.stderr)
            self.assertEqual({p.name: p.read_bytes() for p in shared.iterdir()}, before)
            for name in names:
                self.assertEqual((project / name).read_bytes(), b'owner\n')

    def test_the_bridge_copy_stops_before_writing_below_a_linked_folder(self):
        self.linked_upgrade_folder('for f in claude_bridge.py',
                                   ('scripts/claude_bridge.py', 'scripts/test_claude_bridge.py'), 'scripts')

    def test_the_merge_stops_before_writing_below_any_linked_folder(self):
        for folder in ('scripts', 'docs'):
            with self.subTest(folder=folder):
                self.linked_upgrade_folder('git merge-file',
                                           ('scripts/check.sh', 'docs/DEV_SETUP.md', 'docs/GOTCHAS.md'), folder)

    def test_the_line_ending_action_stops_on_a_failed_file_list_or_a_leftover(self):
        # r8: a corrupt index failed both `git ls-files`, Python read an empty list and exited
        # 0, `xargs` ran `git add --renormalize --` with no path, and the step said nothing.
        # And a SIGKILL left a `.crlf-*` copy that a retry ignored and a commit could carry.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', KIT=str(ROOT))
        for snippet in (self.checklist_block('core/.gitattributes'),
                        textwrap_dedent_dev_setup()):
            for case in ('ls-files fails', 'a leftover copy'):
                with self.subTest(case=case, where='CHANGELOG' if 'KIT' in snippet else 'DEV_SETUP'), \
                        tempfile.TemporaryDirectory() as tmp:
                    project, stubs = Path(tmp) / 'project', Path(tmp) / 'bin'
                    (project / 'scripts').mkdir(parents=True)
                    stubs.mkdir()
                    script = project / 'scripts/check.sh'
                    script.write_bytes(b'#!/bin/sh\r\necho check ran\r\n')
                    subprocess.run(['git', 'init', '-q'], cwd=project, check=True, env=env)
                    subprocess.run(['git', 'add', '-A'], cwd=project, check=True, env=env)
                    subprocess.run(['git', '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit',
                                    '-qm', 'v0.9'], cwd=project, check=True, env=env)
                    run_env = env
                    if case == 'ls-files fails':
                        real = shutil.which('git')
                        (stubs / 'git').write_text('#!/bin/sh\ncase " $* " in *" ls-files -z "*) '
                                                   'echo "fatal: index file corrupt" >&2; exit 128 ;; esac\n'
                                                   'exec "%s" "$@"\n' % real)
                        (stubs / 'git').chmod(0o755)
                        run_env = dict(env, PATH=str(stubs) + os.pathsep + env['PATH'])
                    else:
                        (project / 'scripts/.crlf-a1b2').write_bytes(b'half\n')
                    result = subprocess.run(['sh', '-c', snippet], cwd=project, capture_output=True, text=True,
                                            env=run_env)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('git ls-files failed' if case == 'ls-files fails'
                                  else 'a killed run left scripts/.crlf-a1b2', result.stderr)
                    self.assertEqual(script.read_bytes(), b'#!/bin/sh\r\necho check ran\r\n')
                    self.assertFalse((project / '.gitattributes').exists(), result.stderr)
                    staged = subprocess.run(['git', 'diff', '--cached', '--name-only'], cwd=project,
                                            capture_output=True, text=True, env=env).stdout
                    self.assertEqual(staged, '')

    def test_fix_crlf_rewrites_scripts_and_every_hook_and_stages_them(self):
        # D07 inv3#82: the repair is a kit-owned script over '*.sh' and every file in .githooks,
        # a project's chained `<name>.project` hook included; another text file is left alone.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            files = {'scripts/check.sh': b'#!/bin/sh\r\necho check ran\r\n',
                     '.githooks/pre-commit.project': b'#!/bin/sh\r\necho mine ran\r\n',
                     'notes.txt': b'one\r\n'}
            for path, body in files.items():
                (project / path).parent.mkdir(parents=True, exist_ok=True)
                (project / path).write_bytes(body)
            git = lambda *args: subprocess.run(['git', '-c', 'core.autocrlf=false', *args], cwd=project,
                                               check=True, capture_output=True, env=env).stdout
            git('init', '-q')
            git('add', '-A')
            result = subprocess.run(['sh', '-c', textwrap_dedent_dev_setup()], cwd=project,
                                    capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for path in ('scripts/check.sh', '.githooks/pre-commit.project'):
                lf = files[path].replace(b'\r\n', b'\n')
                self.assertEqual((project / path).read_bytes(), lf, path)
                self.assertEqual(git('show', ':' + path), lf, path)
            self.assertEqual((project / 'notes.txt').read_bytes(), b'one\r\n')

    def test_fix_crlf_repairs_a_project_below_the_repository_top(self):
        # git ls-files names paths from the current folder, `git cat-file :<path>` from the top:
        # run in a subfolder, every CRLF script was refused as "has changes" and none repaired.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'sub/scripts/x.sh'
            script.parent.mkdir(parents=True)
            script.write_bytes(b'#!/bin/sh\r\ntrue\r\n')
            git = lambda *args: subprocess.run(['git', '-c', 'core.autocrlf=false', *args], cwd=tmp,
                                               check=True, capture_output=True, env=env).stdout
            git('init', '-q')
            git('add', '-A')
            git('-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'fixture')
            result = subprocess.run(['sh', '-c', textwrap_dedent_dev_setup()], cwd=script.parents[1],
                                    capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(script.read_bytes(), b'#!/bin/sh\ntrue\n')
            self.assertEqual(git('show', ':sub/scripts/x.sh'), b'#!/bin/sh\ntrue\n')

    def test_dev_setup_names_the_tested_repair_instead_of_embedding_a_program(self):
        section = (ROOT / 'core/docs/DEV_SETUP.md').read_text(encoding='utf-8')
        section = section.split('**Line endings.**', 1)[1].split('## 2.', 1)[0]
        self.assertIn('`sh scripts/fix_crlf.sh`', section)
        self.assertNotIn('```', section, 'DEV_SETUP must use the tested kit-owned repair')
        self.assertEqual(textwrap_dedent_dev_setup(),
                         'sh ' + shlex.quote((ROOT / 'core/scripts/fix_crlf.sh').as_posix()))

    def test_fix_crlf_does_not_stage_unrelated_lf_script_or_hook_edits(self):
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            paths = ('scripts/dirty.sh', '.githooks/pre-commit.project', 'scripts/repair.sh')
            for path in paths:
                (project / path).parent.mkdir(parents=True, exist_ok=True)
                (project / path).write_bytes(b'#!/bin/sh\r\ntrue\r\n' if path == paths[2]
                                            else b'#!/bin/sh\ntrue\n')
            git = lambda *args: subprocess.run(['git', '-c', 'core.autocrlf=false', *args], cwd=project,
                                               check=True, capture_output=True, env=env).stdout
            git('init', '-q')
            git('add', '-A')
            git('-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'fixture')
            for path in paths[:2]:
                (project / path).write_bytes(b'#!/bin/sh\necho owner-edit\n')
            (project / paths[2]).write_bytes(b'#!/bin/sh\r\ntrue\r\n')
            result = subprocess.run(['sh', '-c', textwrap_dedent_dev_setup()], cwd=project,
                                    capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(git('diff', '--cached', '--name-only').decode().splitlines(), [paths[2]])
            for path in paths[:2]:
                self.assertEqual(git('show', ':' + path), b'#!/bin/sh\ntrue\n')
                self.assertEqual((project / path).read_bytes(), b'#!/bin/sh\necho owner-edit\n')
            self.assertEqual((project / paths[2]).read_bytes(), b'#!/bin/sh\ntrue\n')

    def test_fix_crlf_refuses_a_crlf_script_with_an_unstaged_or_staged_edit_and_lists_what_it_staged(self):
        # #207: `git add --renormalize` staged the owner's work in progress in a CRLF script with
        # the line-ending fix, exit 0, and named no file. A checkout that is only CRLF over an LF
        # index (autocrlf) is no edit and is repaired.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        crlf, edit = b'#!/bin/sh\r\ntrue\r\n', b'#!/bin/sh\r\ntrue\r\necho WIP\r\n'
        for case in ('unstaged', 'staged', 'clean', 'index LF'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp)
                wip, other = project / 'scripts/wip.sh', project / '.githooks/my hook.project'
                for path in (wip, other):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'#!/bin/sh\ntrue\n' if case == 'index LF' else crlf)
                git = lambda *args: subprocess.run(['git', '-c', 'core.autocrlf=false', *args], cwd=project,
                                                   check=True, capture_output=True, env=env).stdout
                git('init', '-q')
                git('add', '-A')
                git('-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit', '-qm', 'fixture')
                if case == 'index LF':
                    wip.write_bytes(crlf)
                elif case != 'clean':
                    wip.write_bytes(edit)
                    if case == 'staged':
                        git('add', 'scripts/wip.sh')
                indexed = git('show', ':scripts/wip.sh')
                before = wip.read_bytes()
                result = subprocess.run(['sh', '-c', textwrap_dedent_dev_setup()], cwd=project,
                                        capture_output=True, text=True, env=env)
                if case in ('clean', 'index LF'):
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(wip.read_bytes(), b'#!/bin/sh\ntrue\n')
                    self.assertEqual(git('show', ':scripts/wip.sh'), b'#!/bin/sh\ntrue\n')
                    listed = ['scripts/wip.sh'] if case == 'index LF' else ['.githooks/my hook.project',
                                                                             'scripts/wip.sh']
                    self.assertEqual(result.stdout, 'Rewritten to LF and staged:\n'
                                     + ''.join('  %s\n' % name for name in listed))
                    continue
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('STOP: commit or stash the changes in these files first', result.stderr)
                self.assertIn('  scripts/wip.sh\n', result.stderr)
                self.assertNotIn('my hook', result.stderr)
                self.assertEqual(wip.read_bytes(), before)
                self.assertEqual(other.read_bytes(), crlf, 'nothing is rewritten before the refusal')
                self.assertEqual(git('show', ':scripts/wip.sh'), indexed)

    def test_fix_crlf_leaves_binary_hooks_and_scripts_unmodified_and_unstaged(self):
        # A tracked helper executable was corrupted and staged with every other hook.
        # Attributes can disable conversion even without NUL; forced text still cannot
        # make binary content safe to rewrite. Keep an unstaged owner edit, too.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        for path, attributes, body in (
                ('.githooks/helper.exe', b'*.exe binary\n', b'MZ\0one\r\ntwo\r\n'),
                ('.githooks/helper.exe', b'*.exe -text\n', b'one\r\ntwo\r\n'),
                ('.githooks/helper.exe', b'', b'MZ\0one\r\ntwo\r\n'),
                ('.githooks/helper.exe', b'* text eol=lf\n', b'MZ\0one\r\ntwo\r\n'),
                ('.githooks/helper.exe', b'* text=auto\n', b'MZ\0one\r\ntwo\r\n'),
                ('scripts/helper.sh', b'*.sh binary\n', b'one\r\ntwo\r\n')):
            with self.subTest(path=path, attributes=attributes), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp)
                binary = project / path
                binary.parent.mkdir(parents=True)
                binary.write_bytes(body)
                (project / '.gitattributes').write_bytes(attributes)
                text = project / '.githooks/pre-commit.project'
                text.parent.mkdir(parents=True, exist_ok=True)
                text.write_bytes(b'#!/bin/sh\r\necho hook\r\n')
                git = lambda *args: subprocess.run(
                    ['git', '-c', 'core.autocrlf=false', *args], cwd=project,
                    check=True, capture_output=True, env=env).stdout
                git('init', '-q')
                git('add', '-A')
                git('-c', 'user.name=F', '-c', 'user.email=f@example.invalid',
                    'commit', '-qm', 'fixture')
                indexed = git('show', ':' + path)
                binary.write_bytes(body + b'owner edit\r\n')
                result = subprocess.run(['sh', '-c', textwrap_dedent_dev_setup()], cwd=project,
                                        capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(binary.read_bytes(), body + b'owner edit\r\n')
                self.assertEqual(git('show', ':' + path), indexed, 'binary owner edit was staged')
                self.assertNotIn(path.encode(), git('diff', '--cached', '--name-only', '-z').split(b'\0'))
                self.assertIn('left alone, Git treats as binary', result.stderr)
                self.assertEqual(text.read_bytes(), b'#!/bin/sh\necho hook\n')
                self.assertEqual(git('show', ':.githooks/pre-commit.project'), text.read_bytes())

    def test_the_line_ending_repair_never_writes_below_a_linked_folder(self):
        # Codex review: only the leaf was checked, so with scripts/ a link to a shared folder the
        # repair rewrote the shared check.sh, outside the project, and exited 0.
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', KIT=str(ROOT))
        for snippet, where in ((self.checklist_block('core/.gitattributes'), 'CHANGELOG'),
                               (textwrap_dedent_dev_setup(), 'DEV_SETUP')):
            with self.subTest(where=where), tempfile.TemporaryDirectory() as tmp:
                project, shared = Path(tmp) / 'project', Path(tmp) / 'shared'
                (project / 'scripts').mkdir(parents=True)
                (project / 'scripts/check.sh').write_bytes(b'#!/bin/sh\necho check ran\n')
                subprocess.run(['git', 'init', '-q'], cwd=project, check=True, env=env)
                subprocess.run(['git', 'add', '-A'], cwd=project, check=True, env=env)
                subprocess.run(['git', '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit',
                                '-qm', 'v0.9'], cwd=project, check=True, env=env)
                shared.mkdir()
                (shared / 'check.sh').write_bytes(b'#!/bin/sh\r\necho shared\r\n')
                shutil.rmtree(project / 'scripts')
                (project / 'scripts').symlink_to(shared, target_is_directory=True)
                result = subprocess.run(['sh', '-c', snippet], cwd=project, capture_output=True, text=True,
                                        env=env)
                self.assertEqual((shared / 'check.sh').read_bytes(), b'#!/bin/sh\r\necho shared\r\n',
                                 result.stdout + result.stderr)
                self.assertIn('left alone, a link or not a regular file on its way', result.stderr)

    def test_the_merge_action_stops_on_a_leftover_or_a_temporary_folder_inside_the_project(self):
        # r8: a kill left `scripts/check.sh.XXXXXX` behind, which a retry ignored; with
        # TMPDIR=. the v0.9 copies and the merge result were written inside the project.
        snippet = self.checklist_block('git merge-file')
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        names = ('scripts/check.sh', 'docs/DEV_SETUP.md', 'docs/GOTCHAS.md')
        for case in ('a leftover', 'TMPDIR inside', 'TMPDIR honoured', 'TMPDIR ignored'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
                for name in names:
                    (kit / 'core' / name).parent.mkdir(parents=True, exist_ok=True)
                    (kit / 'core' / name).write_text('one\n')
                    (project / name).parent.mkdir(parents=True, exist_ok=True)
                    (project / name).write_text('one\nmine\n')
                for repo in (kit, project):
                    subprocess.run(['git', 'init', '-q'], cwd=repo, check=True, env=env)
                    subprocess.run(['git', 'add', '-A'], cwd=repo, check=True, env=env)
                    subprocess.run(['git', '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', 'commit',
                                    '-qm', 'v0.9'], cwd=repo, check=True, env=env)
                run_env = dict(env, KIT=str(kit), KIT_BASE='HEAD')
                if case == 'a leftover':
                    (project / 'scripts/.kit-merge-Ab12Cd').write_text('half\n')
                else:
                    run_env['TMPDIR'] = str(project)
                if case in ('TMPDIR honoured', 'TMPDIR ignored'):
                    shims = Path(tmp) / 'bin'
                    shims.mkdir()
                    outside = Path(tmp) / 'outside'
                    outside.mkdir()
                    # Both implementations run on every host, whatever its PATH supplies.
                    tmpdir = '"$TMPDIR"' if case == 'TMPDIR honoured' else shlex.quote(outside.as_posix())
                    real = shlex.quote(shutil.which('mktemp'))
                    (shims / 'mktemp').write_text('#!/bin/sh\nif [ "$#" -eq 1 ] && [ "$1" = -d ]; then\n'
                                                 '  exec %s -d %s/kit-probe.XXXXXX\nfi\nexec %s "$@"\n'
                                                 % (real, tmpdir, real))
                    (shims / 'mktemp').chmod(0o755)
                    run_env['PATH'] = str(shims) + os.pathsep + env['PATH']
                probe = subprocess.run(['sh', '-c', 't=$(mktemp -d) || exit 1; '
                                        'case "$(cd "$t" && pwd -P)/" in "$(pwd -P)/"*) echo inside ;; '
                                        '*) echo outside ;; esac; rmdir "$t"'],
                                       cwd=project, capture_output=True, text=True, env=run_env)
                self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
                if case in ('TMPDIR honoured', 'TMPDIR ignored'):
                    self.assertEqual(probe.stdout.strip(), 'inside' if case == 'TMPDIR honoured' else 'outside')
                result = subprocess.run(['sh', '-c', snippet], cwd=project, capture_output=True, text=True,
                                        env=run_env)
                untracked = lambda: subprocess.run(['git', 'ls-files', '--others'], cwd=project, capture_output=True,
                                                   text=True, env=env).stdout.split()
                if case != 'a leftover' and probe.stdout.strip() == 'outside':
                    # BSD and GNU mktemp differ even on one host: test the command on PATH.
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(untracked(), [])
                    continue
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('a killed run left scripts/.kit-merge-Ab12Cd' if case == 'a leftover'
                              else 'is inside the project (TMPDIR?)', result.stderr)
                self.assertEqual(untracked(), ['scripts/.kit-merge-Ab12Cd'] if case == 'a leftover' else [])
                for name in names:
                    self.assertEqual((project / name).read_text(), 'one\nmine\n')

    def test_the_bridge_copy_replaces_a_symlink_and_never_writes_through_it(self):
        # r8: a conventional `cp source destination` wrote into the link's target, outside the
        # project, passed against it locally and committed only the link.
        snippet = self.checklist_block('test_claude_bridge.py')
        env = dict(os.environ, KIT=str(ROOT))
        with tempfile.TemporaryDirectory() as tmp:
            project, outside = Path(tmp) / 'project', Path(tmp) / 'outside'
            (project / 'scripts').mkdir(parents=True)
            outside.mkdir()
            for name in ('claude_bridge.py', 'test_claude_bridge.py'):
                (outside / name).write_text('shared copy\n')
                (project / 'scripts' / name).symlink_to(outside / name)
            result = subprocess.run(['sh', '-c', snippet], cwd=project, capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name in ('claude_bridge.py', 'test_claude_bridge.py'):
                with self.subTest(name=name):
                    self.assertEqual((outside / name).read_text(), 'shared copy\n')
                    self.assertFalse((project / 'scripts' / name).is_symlink())
                    self.assertEqual((project / 'scripts' / name).read_bytes(),
                                     (ROOT / 'core/scripts' / name).read_bytes())
            self.assertEqual(sorted(p.name for p in (project / 'scripts').iterdir()),
                             ['claude_bridge.py', 'test_claude_bridge.py'])

    def test_the_line_ending_action_keeps_modes_and_stops_on_a_failed_rewrite(self):
        # The rewrite ignored a script Python could not rewrite, staged the rest and exited 0
        # with that script still CRLF; and it wrote in place, so a killed run left a script
        # half new. Each script is now replaced whole with its mode, and a failure stops the step.
        import textwrap
        if not_on_windows(self.id(), 'POSIX modes: no executable bit, no read-only folder'):
            return
        if os.geteuid() == 0:
            self.skipTest('root writes into a read-only folder')
        text = (ROOT / 'CHANGELOG.md').read_text()
        block = next(part for part in text.split('```sh\n')[1:]
                     if 'core/.gitattributes' in part.split('```')[0])
        snippet = textwrap.dedent(block.split('```')[0])
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', KIT=str(ROOT))
        for case in ('rewritten', 'read-only'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / 'project'
                (project / 'scripts').mkdir(parents=True)
                script = project / 'scripts/check.sh'
                script.write_bytes(b'#!/bin/sh\r\necho check ran\r\n')
                script.chmod(0o755)
                subprocess.run(['git', 'init', '-q'], cwd=project, check=True, env=env)
                subprocess.run(['git', 'add', '-A'], cwd=project, check=True, env=env)
                if case == 'read-only':
                    script.chmod(0o555)
                    (project / 'scripts').chmod(0o555)
                try:
                    result = subprocess.run(['sh', '-c', snippet], cwd=project, capture_output=True, text=True,
                                            env=env)
                finally:
                    (project / 'scripts').chmod(0o755)
                staged = subprocess.run(['git', 'diff', '--cached', '--name-only'], cwd=project, check=True,
                                        capture_output=True, text=True, env=env).stdout
                self.assertIn('scripts/check.sh', staged)
                if case == 'rewritten':
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(script.read_bytes(), b'#!/bin/sh\necho check ran\n')
                    self.assertEqual(script.stat().st_mode & 0o777, 0o755)
                    self.assertEqual(sorted(p.name for p in (project / 'scripts').iterdir()), ['check.sh'])
                    continue
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertIn('STOP: a script could not be rewritten', result.stderr)
                self.assertNotIn('.gitattributes', staged)
                self.assertEqual(script.read_bytes(), b'#!/bin/sh\r\necho check ran\r\n')

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
