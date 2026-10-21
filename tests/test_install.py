"""install.sh fetches the kit into the per-user cache and runs its bootstrap; a rerun reuses the
cache, and every failure stops before the project is touched."""
import base64
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

    def install(self, project, *args, ref='v-test', env=None, command=None, home=None):
        project.mkdir(exist_ok=True)
        env = dict(env or os.environ, HOME=str(home or self.home), MYAGENTKIT_REF=ref,
                   MYAGENTKIT_REPO=self.source.as_uri())
        return subprocess.run((command or ['sh', str(ROOT / 'install.sh')]) + list(args), cwd=project,
                              env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')

    def powershell(self, project, script, ref='v-test', env=None):
        """Runs `script` in Windows PowerShell, the Windows default (5.1), from `project`; the
        kit's own files stand in for every download (irm URL reads the file of that name here)."""
        shell = shutil.which('powershell') or shutil.which('pwsh')
        script = ("function Invoke-RestMethod($uri) { [IO.File]::ReadAllText((Join-Path '%s' ($uri -split '/')[-1])) }\n%s"
                  % (ROOT, script))
        encoded = base64.b64encode(script.encode('utf-16-le')).decode()
        return self.install(project, ref=ref, env=env,
                            command=[shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                     '-EncodedCommand', encoded])

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
        # The cache holds the release tags: review.sh --kit-verified asks it which v* tag holds the commit.
        tags = subprocess.run(['git', '-C', str(self.cache), 'tag', '--contains', head, '--list', 'v*'],
                              capture_output=True, text=True, encoding='utf-8', check=True).stdout.split()
        self.assertIn('v-test', tags)
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
        # sync-kit ran on this folder: a project never installed is refused by its own name.
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('synced/docs/kit/.kit-version not found', result.stderr)
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

    def test_a_cache_with_edits_to_the_kit_is_not_overwritten(self):
        home = Path(self.tmp.name) / 'edited-home'
        home.mkdir()
        self.install(self.project('edited-first'), '--help', home=home)
        readme = home / '.myagentkit/kit/README.md'
        readme.write_bytes(readme.read_bytes() + b'an edit\n')
        result = self.install(self.project('edited'), home=home)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('has edits to the kit', result.stderr)
        self.assertTrue(readme.read_bytes().endswith(b'an edit\n'))

    def test_a_bootstrap_that_finds_no_kit_file_stops_unrecorded(self):
        # A find that lists nothing, as Windows' FIND.EXE does for `find . -type f`.
        fake = Path(self.tmp.name) / 'no-find'
        fake.mkdir()
        (fake / 'find').write_text('#!/bin/sh\nexit 0\n', encoding='utf-8', newline='\n')
        (fake / 'find').chmod(0o755)
        project = self.project('nothing-found')
        result = self.install(project, env=dict(os.environ, PATH=str(fake) + os.pathsep + os.environ['PATH']))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('bootstrap: found no file under', result.stderr)
        self.assertFalse((project / 'docs/kit/.kit-version').exists())

    @unittest.skipUnless(WINDOWS, 'the PowerShell shim is the Windows front door')
    def test_the_powershell_shim_passes_a_quoted_argument_whole(self):
        # Windows PowerShell 5.1 split an argument with quotes and spaces on its way to sh.
        project = Path(self.tmp.name) / 'powershell'
        result = self.powershell(project, "& '%s' '--x \"b c\" d'; exit $LASTEXITCODE" % (ROOT / 'install.ps1'))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('install: kit v-test', result.stdout)
        self.assertIn('bootstrap: unknown option: --x "b c" d', result.stderr)
    test_the_powershell_shim_passes_a_quoted_argument_whole._kit_platform_skip = not WINDOWS

    @unittest.skipUnless(WINDOWS, 'the PowerShell shim is the Windows front door')
    def test_the_powershell_shim_takes_gits_own_sh_over_a_bare_one_on_path(self):
        # A bare usr\bin\sh.exe behind System32 ran the kit with FIND.EXE for find; Git's bin\sh.exe
        # puts its usr\bin first.
        git = Path(shutil.which('git'))
        root = next(folder for folder in git.parents if (folder / 'usr/bin/sh.exe').is_file())
        path = os.pathsep.join([str(Path(os.environ['SystemRoot']) / 'System32'), str(root / 'usr/bin'), str(git.parent)])
        project = self.project('powershell-path')
        result = self.powershell(project, "& '%s'; exit $LASTEXITCODE" % (ROOT / 'install.ps1'),
                                 env=dict(os.environ, PATH=path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((project / 'AGENTS.md').is_file(), result.stdout + result.stderr)
    test_the_powershell_shim_takes_gits_own_sh_over_a_bare_one_on_path._kit_platform_skip = not WINDOWS

    @unittest.skipUnless(WINDOWS, 'the PowerShell shim is the Windows front door')
    def test_irm_iex_leaves_the_callers_session_as_it_was(self):
        script = ("$ErrorActionPreference = 'Continue'\n[IO.File]::ReadAllText('%s') | Invoke-Expression\n"
                  "'after: {0} {1} {2}' -f $ErrorActionPreference, "
                  "[bool](Get-Variable sh, candidates, code -Scope Global -ErrorAction SilentlyContinue), $LASTEXITCODE"
                  % (ROOT / 'install.ps1'))
        result = self.powershell(Path(self.tmp.name) / 'powershell-iex', script, ref='v-no-such-tag')
        self.assertIn('after: Continue False 1', result.stdout, result.stdout + result.stderr)
    test_irm_iex_leaves_the_callers_session_as_it_was._kit_platform_skip = not WINDOWS

    def test_init_and_sync_ask_for_a_yes_before_they_run_the_installer(self):
        # Owner decision 62: every permission mode, so a bypass or an allow rule is no yes.
        for path in ('plugin/commands/init.md', 'plugin/commands/sync.md',
                     'plugins/myagentkit/skills/myagentkit-init/SKILL.md',
                     'plugins/myagentkit/skills/myagentkit-sync/SKILL.md'):
            with self.subTest(path=path):
                text = ' '.join((ROOT / path).read_text(encoding='utf-8').split())
                ask, run = text.index('2. Ask first.'), text.index('3. Run')
                self.assertLess(ask, run)
                for part in ('https://github.com/KBT-0/MyAgentKit_Keel.git', 'MYAGENTKIT_REF',
                             '~/.myagentkit/kit', 'give its full path', "yes in the chat, in every permission "
                             'mode, bypass and allow rules included. No yes: run nothing.'):
                    self.assertIn(part, text[ask:run])

    @unittest.skipUnless(WINDOWS, 'the PowerShell shim is the Windows front door')
    def test_the_codex_skills_powershell_form_returns_the_installers_exit_code(self):
        # An agent runs it through `powershell -Command`, whose exit is 0 when the last statement succeeded.
        for skill in ('myagentkit-init', 'myagentkit-sync'):
            with self.subTest(skill=skill):
                text = (ROOT / 'plugins/myagentkit/skills' / skill / 'SKILL.md').read_text(encoding='utf-8')
                form = re.search(r'```powershell\n\s*(.*?)\n\s*```', text, re.S)[1].replace('OPTIONS', "'--no-such-option'")
                result = self.powershell(Path(self.tmp.name) / ('powershell-' + skill), form)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('unknown option: --no-such-option', result.stderr)
    test_the_codex_skills_powershell_form_returns_the_installers_exit_code._kit_platform_skip = not WINDOWS


if __name__ == '__main__':
    unittest.main()
