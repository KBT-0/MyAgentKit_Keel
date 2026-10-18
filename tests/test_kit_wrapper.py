"""The kit check's wrapper compares HEAD, index, status and file contents at the end of its run.

A test that writes into the checkout fails a review running there as stale_checkout; the end
check cannot catch a non-ignored file a test writes and removes meanwhile.
"""
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', '-c', 'commit.gpgsign=false',
       '-c', 'core.hooksPath=/dev/null']


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')


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
            result = subprocess.run(['sh', str(kit / 'scripts/check.sh')], cwd=kit,
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
            result = subprocess.run(['sh', str(kit / 'scripts/check.sh')], cwd=kit,
                                    env=dict(os.environ, PATH=str(wrapped) + os.pathsep + os.environ['PATH']),
                                    capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=120)
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            # Once for the view before the run and once after it; the old loop made one per file.
            self.assertEqual(len(calls.read_text().split()), 2, out)

    def test_an_unopenable_path_or_short_hash_output_fails_by_path(self):
        # Run the wrapper's git_view itself: no kit check is needed.
        for script in ('scripts/check.sh',):
            source = (ROOT / script).read_text(encoding='utf-8')
            start = source.index('git_view() {')
            function = source[start:source.index('\n}', start)] + '\n}\n'
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

    def test_the_kit_check_fails_on_a_file_it_leaves_and_passes_an_ignored_one(self):
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
            for leave, expected in (('ignored-out/x', 0), ('leftover.txt', 1), ('tracked.txt', 1)):
                with self.subTest(leave=leave):
                    result = subprocess.run(['sh', str(kit / 'scripts/check.sh')], cwd=kit,
                                            env=dict(os.environ, LEAVE=str(kit / leave)),
                                            capture_output=True, text=True, encoding='utf-8',
                                            errors='replace', timeout=120)
                    out = result.stdout + result.stderr
                    self.assertEqual(result.returncode, expected, out)
                    if expected:
                        self.assertIn('KIT CHECK: FAIL — the kit check changed this checkout', out)
                    if leave == 'leftover.txt':
                        self.assertIn('    + ?? leftover.txt', out)
                    if leave == 'tracked.txt':
                        # Status says " M tracked.txt" before and after: only the hash differs.
                        self.assertRegex(out, r'    \+ [0-9a-f]{40,64} tracked\.txt')


if __name__ == '__main__':
    unittest.main()
