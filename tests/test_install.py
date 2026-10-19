"""install.sh fetches the kit into the per-user cache and runs its bootstrap; a rerun reuses the
cache, and every failure stops before the project is touched."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == 'nt'


def tree(folder):
    """Every file under `folder` but .git, with its bytes."""
    return {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob('*')
            if path.is_file() and '.git' not in path.relative_to(folder).parts}


class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A local clone of the kit stands in for GitHub; file:// is git's network transport.
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        base = Path(cls.tmp.name)
        cls.source, cls.home = base / 'source', base / 'home'
        cls.home.mkdir()
        subprocess.run(['git', 'clone', '-q', str(ROOT), str(cls.source)], check=True)
        subprocess.run(['git', '-C', str(cls.source), 'tag', 'v-test'], check=True)
        cls.cache = cls.home / '.myagentkit/kit'

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def install(self, project, *args, ref='v-test', env=None, command=None):
        project.mkdir(exist_ok=True)
        env = dict(env or os.environ, HOME=str(self.home), MYAGENTKIT_REF=ref,
                   MYAGENTKIT_REPO=self.source.as_uri())
        return subprocess.run((command or ['sh', str(ROOT / 'install.sh')]) + list(args), cwd=project,
                              env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')

    def project(self, name):
        project = Path(self.tmp.name) / name
        project.mkdir()
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        return project

    def test_install_then_a_rerun_reuses_the_cache_and_leaves_the_project_as_it_was(self):
        project = self.project('installed')
        result = self.install(project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Read setup/INTERVIEW.md and start the setup.', result.stdout)
        head = subprocess.run(['git', '-C', str(self.source), 'rev-parse', 'v-test^{commit}'], capture_output=True,
                              text=True, encoding='utf-8', check=True).stdout.strip()
        self.assertEqual((project / 'docs/kit/.kit-commit').read_text(encoding='utf-8').strip(), head)
        before = tree(project)
        marker = self.cache / '.git/not-cloned-again'
        marker.write_text('', encoding='utf-8')
        result = self.install(project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(marker.exists(), 'the rerun cloned the kit again')
        self.assertEqual(tree(project), before)

    def test_sync_moves_the_cache_to_the_new_ref_and_runs_sync_kit(self):
        project = self.project('synced')
        subprocess.run(['git', '-C', str(self.source), '-c', 'user.name=t', '-c', 'user.email=t@example.com',
                        'commit', '-q', '--allow-empty', '-m', 'next'], check=True)
        subprocess.run(['git', '-C', str(self.source), 'tag', 'v-next'], check=True)
        result = self.install(project, 'sync', '--dry-run', ref='v-next')
        self.assertIn('sync-kit:', result.stderr + result.stdout)
        heads = [subprocess.run(['git', '-C', str(folder), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                                encoding='utf-8', check=True).stdout for folder in (self.cache, self.source)]
        self.assertEqual(heads[0], heads[1])

    def test_a_missing_ref_fails_and_leaves_the_project_untouched(self):
        project = Path(self.tmp.name) / 'missing-ref'
        result = self.install(project, ref='v-no-such-tag')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('install: cannot fetch v-no-such-tag', result.stderr)
        self.assertEqual(list(project.iterdir()), [])

    def test_no_git_stops_before_the_cache_or_the_project(self):
        project, empty = Path(self.tmp.name) / 'no-git', Path(self.tmp.name) / 'empty-path'
        home = Path(self.tmp.name) / 'no-git-home'
        for folder in (project, empty, home):
            folder.mkdir()
        # sh by its full path, so PATH can hold nothing, git included.
        result = subprocess.run([shutil.which('sh'), str(ROOT / 'install.sh')], cwd=project,
                                env=dict(os.environ, PATH=str(empty), HOME=str(home)),
                                capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('install: git is missing', result.stderr)
        self.assertEqual((list(project.iterdir()), list(home.iterdir())), ([], []))

    def test_the_pinned_release_is_the_changelog_version(self):
        # The release steps raise it with the other version strings (CONTRIBUTING.md); a tag v<this>
        # is pushed with the release, or every install from the default fails to fetch.
        pinned = re.search(r'(?m)^version=(\S+)$', (ROOT / 'install.sh').read_text(encoding='utf-8'))[1]
        changelog = re.search(r'(?m)^## v(\d+\.\d+)(?=\s|$)', (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8'))[1]
        self.assertEqual(pinned, changelog)

    @unittest.skipUnless(WINDOWS, 'the PowerShell shim is the Windows front door')
    def test_the_powershell_shim_finds_sh_and_passes_the_arguments_through(self):
        shell = shutil.which('pwsh') or shutil.which('powershell')
        project = Path(self.tmp.name) / 'powershell'
        result = self.install(project, '--overlay', command=[shell, '-NoProfile', '-File', str(ROOT / 'install.ps1')])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('install: kit v-test', result.stdout)
        self.assertIn('bootstrap: --overlay needs a name', result.stderr)


if __name__ == '__main__':
    unittest.main()
