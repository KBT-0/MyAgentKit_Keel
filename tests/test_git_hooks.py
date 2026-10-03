"""Git itself must call the shipped hooks: on a clean merge commit and on every commit message."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GitHookTests(unittest.TestCase):
    def repo(self, tmp):
        root = Path(tmp)
        shutil.copytree(ROOT / 'core/.githooks', root / '.githooks')
        (root / 'scripts').mkdir()
        # A stub gate: each branch alone is green, the two together are red.
        (root / 'scripts/check.sh').write_text(
            'echo ran >> .git/gate-runs\n[ ! -e a ] || [ ! -e b ] || { echo "CHECK: FAIL"; exit 1; }\n')
        (root / 'scripts/check.sh').chmod(0o755)
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        git = lambda *args, check=True: subprocess.run(
            ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
             '-c', 'core.hooksPath=.githooks', *args],
            cwd=root, env=env, capture_output=True, text=True, check=check)
        git('init', '-q', '-b', 'main')
        git('add', '-A')
        git('commit', '-q', '-m', 'base')
        return root, git

    def test_a_clean_merge_into_a_red_tree_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            for branch in ('a', 'b'):
                git('checkout', '-q', '-b', branch, 'main')
                (root / branch).write_text(branch + '\n')
                git('add', branch)
                git('commit', '-q', '-m', 'add ' + branch)
            git('checkout', '-q', 'a')
            runs = (root / '.git/gate-runs').read_text().count('ran')
            merge = git('merge', '-q', '--no-edit', 'b', check=False)
            self.assertNotEqual(merge.returncode, 0, 'a clean merge into a red tree was committed')
            self.assertGreater((root / '.git/gate-runs').read_text().count('ran'), runs)
            self.assertEqual(git('rev-list', '--count', 'HEAD').stdout.strip(), '2')

    def test_an_ai_co_author_trailer_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, git = self.repo(tmp)
            for trailer, allowed in (('Co-Authored-By: Claude <noreply@anthropic.com>', False),
                                     ('co-authored-by: GitHub Copilot <copilot@github.com>', False),
                                     ('Co-authored-by: A Person <person@example.invalid>', True)):
                with self.subTest(trailer=trailer):
                    (root / 'c').write_text(trailer + '\n')
                    git('add', 'c')
                    result = git('commit', '-q', '-m', 'change c', '-m', trailer, check=False)
                    self.assertEqual(result.returncode == 0, allowed, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
