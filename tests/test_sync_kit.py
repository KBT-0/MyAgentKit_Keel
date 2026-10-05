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
