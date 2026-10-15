"""A self-test compares HEAD, index, status and file contents at the end of its run.

A self-test may share a review's worktree only when every case writes nothing but files Git
ignores: its end check cannot catch a non-ignored file a case writes and removes meanwhile.
"""
import os
import re
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
          'echo changed >> existing.txt\n'
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
        # another edit, so its content hash must see that edit and name the path.
        write(self.project / 'notes.md', 'one\n')
        subprocess.run(GIT + ['add', 'notes.md'], cwd=self.project, check=True)
        subprocess.run(GIT + ['commit', '-qm', 'notes'], cwd=self.project, check=True)
        write(self.project / 'notes.md', 'two\n')
        write(self.project / 'existing.txt', 'before\n')
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
        self.assertIn('another process edited the checkout meanwhile', out)
        self.assertIn('    + ?? leftover.txt', out)
        self.assertRegex(out, r'    \+ [0-9a-f]{40,64} notes\.md')
        self.assertRegex(out, r'    \+ [0-9a-f]{40,64} existing\.txt')
        self.assertNotIn('ignored-out', out)
        self.assertIn('SELF-TEST: FAIL', out)


class KitWrapperTests(unittest.TestCase):
    def assert_content_edit_fails(self, tracked, name='existing file.txt'):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / 'kit'
            (kit / 'scripts').mkdir(parents=True)
            shutil.copyfile(ROOT / 'scripts/check.sh', kit / 'scripts/check.sh')
            write(kit / 'scripts/check_kit.py',
                  'import os\nfrom pathlib import Path\n'
                  'p = Path(%r)\ns = p.stat()\n' % name +
                  'p.write_bytes(b"after!\\n")\n'
                  'os.utime(p, ns=(s.st_atime_ns, s.st_mtime_ns))\n'
                  'Path(os.environ["KIT_CHECK_PASSED"]).touch()\n')
            subprocess.run(['git', 'init', '-q', str(kit)], check=True)
            subprocess.run(['git', 'config', 'core.autocrlf', 'false'], cwd=kit, check=True)
            write(kit / name, 'before\n')
            if tracked:
                subprocess.run(['git', 'config', 'core.trustctime', 'false'], cwd=kit, check=True)
                subprocess.run(['git', 'config', 'core.checkStat', 'minimal'], cwd=kit, check=True)
                subprocess.run(GIT + ['add', name], cwd=kit, check=True)
                subprocess.run(GIT + ['commit', '-qm', 'tracked'], cwd=kit, check=True)
                # Avoid Git's racy-index timestamp window; keep the same indexed mtime on edit.
                stamp = 1_600_000_000_000_000_000
                os.utime(kit / name, ns=(stamp, stamp))
                subprocess.run(['git', 'update-index', '--refresh'], cwd=kit, check=True)
            before = subprocess.run(['git', 'status', '--porcelain'], cwd=kit,
                                    capture_output=True, check=True).stdout
            result = subprocess.run(['sh', str(kit / 'scripts/check.sh'), '--self-test'], cwd=kit,
                                    capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=120)
            after = subprocess.run(['git', 'status', '--porcelain'], cwd=kit,
                                   capture_output=True, check=True).stdout
            self.assertEqual(before, after)
            if tracked:
                self.assertEqual(subprocess.run(['git', 'diff', '--binary', 'HEAD'], cwd=kit,
                                               capture_output=True, check=True).stdout, b'')
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1, out)
            self.assertIn('KIT CHECK: FAIL', out)
            self.assertRegex(out, r'    \+ [0-9a-f]{40,64} ' + re.escape(name))
            self.assertIn('another process edited the checkout meanwhile', out)

    def test_an_existing_untracked_file_edited_in_place_fails_by_path(self):
        self.assert_content_edit_fails(tracked=False)

    def test_a_tracked_edit_hidden_by_restored_mtime_fails_by_path(self):
        self.assert_content_edit_fails(tracked=True)

    def test_a_non_ascii_name_edited_in_place_fails_by_path(self):
        # Git prints such a name C-quoted by default, and hash-object does not unquote it: the
        # old per-file loop hashed nothing, before and after, so the edit went unseen.
        self.assert_content_edit_fails(tracked=False, name='ä.txt')
        self.assert_content_edit_fails(tracked=True, name='ä.txt')

    def test_the_tree_is_hashed_by_one_git_hash_object_call_per_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit, wrapped, calls = Path(tmp) / 'kit', Path(tmp) / 'bin', Path(tmp) / 'calls.log'
            (kit / 'scripts').mkdir(parents=True)
            shutil.copyfile(ROOT / 'scripts/check.sh', kit / 'scripts/check.sh')
            write(kit / 'scripts/check_kit.py',
                  'import os\nfrom pathlib import Path\nPath(os.environ["KIT_CHECK_PASSED"]).touch()\n')
            subprocess.run(['git', 'init', '-q', str(kit)], check=True)
            for number in range(30):
                write(kit / ('file %d.txt' % number), 'x\n')
            subprocess.run(GIT + ['add', 'file 1*.txt'], cwd=kit, check=True)
            # An indexed file deleted from disk must not shift the hashes onto the wrong names.
            (kit / 'file 10.txt').unlink()
            # git, counting its hash-object calls and then running the real one.
            write(wrapped / 'git',
                  '#!/bin/sh\nfor a; do [ "$a" = hash-object ] && echo x >> "%s"; done\nexec "%s" "$@"\n'
                  % (calls.as_posix(), Path(shutil.which('git')).as_posix()))
            os.chmod(wrapped / 'git', 0o755)
            result = subprocess.run(['sh', str(kit / 'scripts/check.sh'), '--self-test'], cwd=kit,
                                    env=dict(os.environ, PATH=str(wrapped) + os.pathsep + os.environ['PATH']),
                                    capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=120)
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            # Once for the view before the run and once after it; the old loop made one per file.
            self.assertEqual(len(calls.read_text().split()), 2, out)

    def test_an_unopenable_path_or_short_hash_output_fails_by_path(self):
        # Run each shipped git_view itself: no gate or plugin generation is needed.
        for script in ('scripts/check.sh', 'core/scripts/check.sh'):
            source = (ROOT / script).read_text(encoding='utf-8')
            start = source.index('git_view() {')
            end = source.index('\n}', start) if script == 'scripts/check.sh' else source.index('\n  }', start)
            function = source[start:end] + '\n}\n'
            for case in ('directory', 'short-output'):
                with self.subTest(script=script, case=case), tempfile.TemporaryDirectory() as tmp:
                    kit, scratch = Path(tmp) / 'kit', Path(tmp) / 'scratch'
                    kit.mkdir()
                    scratch.mkdir()
                    subprocess.run(['git', 'init', '-q', str(kit)], check=True)
                    write(kit / 'a.txt', 'first\n')
                    write(kit / 'b.txt', 'second\n')
                    real_git = Path(shutil.which('git')).as_posix()
                    inject = ('rm a.txt && mkdir a.txt' if case == 'directory' else
                              'IFS= read -r first; printf "%%s\\n" "$first" | "%s" "$@"; return 0' % real_git)
                    wrapper = ('git() {\nif [ "$1" = hash-object ]; then\n%s\nfi\n'
                               '"%s" "$@"\n}\n' % (inject, real_git))
                    runner = scratch / 'run.sh'
                    write(runner, 'set -eu\nwork="%s"\npassed="$work"\n' % scratch.as_posix() +
                          wrapper + function +
                          'git_view "$work" > "$work/view" 2>&1 || { cat "$work/view"; exit 1; }\n')
                    result = subprocess.run(['sh', str(runner)], cwd=kit, capture_output=True,
                                            text=True, encoding='utf-8', errors='replace', timeout=30)
                    out = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 1, out)
                    missing = 'a.txt' if case == 'directory' else 'b.txt'
                    self.assertIn('could not hash %s; the tree check is incomplete' % missing, out)

    def test_an_inherited_work_variable_never_chooses_the_scratch_folder(self):
        # An exported `work` once named the folder git_view wrote and deleted git-paths* in
        # (round-3 Codex Critical): the scratch folder is the caller's argument, nothing else.
        source = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
        start = source.index('git_view() {')
        function = source[start:source.index('\n  }', start)] + '\n}\n'
        with tempfile.TemporaryDirectory() as tmp:
            kit, scratch, decoy = Path(tmp) / 'kit', Path(tmp) / 'scratch', Path(tmp) / 'decoy'
            for folder in (kit, scratch, decoy):
                folder.mkdir()
            subprocess.run(['git', 'init', '-q', str(kit)], check=True)
            write(kit / 'a.txt', 'first\n')
            for name in ('git-paths', 'git-paths.hashes', 'git-paths.errors'):
                write(decoy / name, 'owner data\n')
            runner = scratch / 'run.sh'
            write(runner, 'set -eu\n' + function + 'git_view "%s" > "%s/view"\n'
                  % (scratch.as_posix(), scratch.as_posix()))
            result = subprocess.run(['sh', str(runner)], cwd=kit, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=30,
                                    env=dict(os.environ, work=decoy.as_posix()))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('a.txt', (scratch / 'view').read_text(encoding='utf-8'))
            for name in ('git-paths', 'git-paths.hashes', 'git-paths.errors'):
                self.assertEqual((decoy / name).read_text(encoding='utf-8'), 'owner data\n')

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
                        self.assertRegex(out, r'    \+ [0-9a-f]{40,64} tracked\.txt')


if __name__ == '__main__':
    unittest.main()
