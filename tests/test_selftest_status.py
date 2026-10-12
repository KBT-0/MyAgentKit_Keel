"""A self-test leaves the worktree's Git view as it found it: HEAD, the index, git status.

A review running in the same worktree fails as stale_checkout when one of them changes, and
the docs let the self-test share that worktree. So the project gate's self-test and the kit's
own wrapper compare the view before and after, and a difference fails the run by path.
Files Git ignores may change.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_check_gate_windows import environment, make_project  # noqa: E402

GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', '-c', 'commit.gpgsign=false',
       '-c', 'core.hooksPath=/dev/null']

LEAVES = ('mkdir -p ignored-out && : > ignored-out/build.txt\n'
          ': > leftover.txt\n'
          'echo three >> notes.md\n'
          "echo '  ok   — the fixture case ran'\n")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')


class ProjectSelfTestTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / 'project'
        make_project(self.project)
        shutil.copytree(ROOT / 'core/.githooks', self.project / '.githooks')
        write(self.project / 'scripts/review.sh', "echo 'REVIEW SELF-TEST: PASS'\n")
        write(self.project / 'scripts/boundary_selftests.sh', '# The fixture has no boundaries.\n')
        write(self.project / 'AGENTS.md', '- **No AI attribution in git.**\n')
        write(self.project / '.gitignore', 'ignored-out/\n')
        # A tracked file already modified before the run: status names it the same way after
        # another edit, so only the hash of `git diff --binary HEAD` sees that edit.
        write(self.project / 'notes.md', 'one\n')
        subprocess.run(GIT + ['add', 'notes.md'], cwd=self.project, check=True)
        subprocess.run(GIT + ['commit', '-qm', 'notes'], cwd=self.project, check=True)
        write(self.project / 'notes.md', 'two\n')
        self.build = self.tmp / 'build.sh'
        write(self.build, 'true\n')

    def self_test(self):
        result = subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=self.project,
                                env=environment(self.build), capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=900)
        return result.returncode, result.stdout + result.stderr

    def test_a_case_that_leaves_an_untracked_file_fails_the_self_test_by_path(self):
        code, out = self.self_test()
        self.assertEqual(code, 0, out)
        self.assertIn('ok   — the self-test left HEAD, the index, git status and the tracked changes as it found them', out)
        # A case that leaves a file Git does not ignore, beside one it ignores.
        write(self.project / 'scripts/boundary_selftests.sh', LEAVES)
        code, out = self.self_test()
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL — the self-test changed this worktree', out)
        self.assertIn('    + ?? leftover.txt', out)
        self.assertIn('    + diff ', out)
        self.assertNotIn('ignored-out', out)
        self.assertIn('SELF-TEST: FAIL', out)


class KitWrapperTests(unittest.TestCase):
    def test_the_kit_self_test_fails_on_a_file_it_leaves_and_passes_an_ignored_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / 'kit'
            (kit / 'scripts').mkdir(parents=True)
            shutil.copyfile(ROOT / 'scripts/check.sh', kit / 'scripts/check.sh')
            write(kit / '.gitignore', 'ignored-out/\n')
            write(kit / 'scripts/check_kit.py',
                  'import os, sys\nfrom pathlib import Path\n'
                  'Path(os.environ["LEAVE"]).parent.mkdir(exist_ok=True)\n'
                  'Path(os.environ["LEAVE"]).open("a").write("x")\n'
                  'Path(os.environ["KIT_CHECK_PASSED"]).touch()\n')
            subprocess.run(['git', 'init', '-q', str(kit)], check=True)
            write(kit / 'tracked.txt', 'one\n')
            subprocess.run(GIT + ['add', 'tracked.txt'], cwd=kit, check=True)
            subprocess.run(GIT + ['commit', '-qm', 'tracked'], cwd=kit, check=True)
            write(kit / 'tracked.txt', 'two\n')  # Modified before the run.
            for leave, args, expected in (('ignored-out/x', ['--self-test'], 0),
                                          ('leftover.txt', [], 0),
                                          ('leftover2.txt', ['--self-test'], 1),
                                          ('tracked.txt', ['--self-test'], 1)):
                with self.subTest(leave=leave, args=args):
                    result = subprocess.run(['sh', str(kit / 'scripts/check.sh'), *args], cwd=kit,
                                            env=dict(os.environ, LEAVE=str(kit / leave)),
                                            capture_output=True, text=True, encoding='utf-8',
                                            errors='replace', timeout=120)
                    out = result.stdout + result.stderr
                    self.assertEqual(result.returncode, expected, out)
                    if expected:
                        self.assertIn('KIT CHECK: FAIL — the self-test changed this checkout', out)
                    if leave == 'leftover2.txt':
                        self.assertIn('    + ?? leftover2.txt', out)
                        self.assertNotIn('leftover.txt\n', out.replace('leftover2.txt', ''))
                    if leave == 'tracked.txt':
                        # Status says " M tracked.txt" before and after: only the hash differs.
                        self.assertIn('    + diff ', out)
                        self.assertNotIn('tracked.txt', out)


if __name__ == '__main__':
    unittest.main()
