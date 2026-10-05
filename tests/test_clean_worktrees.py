"""scripts/clean_worktrees.sh removes a merged worktree only when nothing in it can be lost.

Each check that keeps a worktree has a case here that builds the state it must catch, in a
throwaway repository; tmux is a stub on PATH, so a live session on the machine running the
tests changes nothing. A kept worktree must still be there, with its branch, and the report
must name the reason. Every run first ages the repository's files by two hours, so the quiet
period holds unless a case is about it.
"""
import ast
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'overlays/claude-code/files/scripts'
SCRIPT = SCRIPTS / 'clean_worktrees.sh'
HOOK = ROOT / 'core/.githooks/post-merge'
sys.path.insert(0, str(SCRIPTS))
import clean_worktrees  # noqa: E402

# Without /proc (macOS) the script asks lsof; most cases pass --assume-idle there so that they
# test their own clause. The cases about liveness run the real scan on every host.
PROC = os.path.exists('/proc/self/cwd')

TMUX = '''#!/bin/sh
if [ -n "${TMUX_STUB_FAIL:-}" ]; then echo "$TMUX_STUB_FAIL" >&2; exit 1; fi
if [ -f "$TMUX_STUB" ]; then cat "$TMUX_STUB"; exit 0; fi
echo "no server running on /tmp/tmux-stub/default" >&2
exit 1
'''
# Wraps the real git: prints what this git never does, or fails one subcommand. The script
# must keep, not guess.
SHIM = '''#!%s
import os, subprocess, sys
args, mode = sys.argv[1:], os.environ.get('SHIM', '')
if mode.startswith('fail:') and mode[5:] in args:
    sys.stderr.write('fatal: refused by the shim\\n')
    sys.exit(128)
result = subprocess.run([os.environ['REAL_GIT']] + args, stdout=subprocess.PIPE)
out = result.stdout
if mode == 'status' and 'status' in args:
    out += b'Z something new\\0'
if mode == 'list' and 'list' in args:
    out = out.replace(b'\\0\\0', b'\\0frobbed\\0\\0')
sys.stdout.buffer.write(out)
sys.exit(result.returncode)
''' % sys.executable

# `lsof -a -d cwd -F pn` as recorded. Linux lsof 4.98 (no f record; an unreadable cwd is named
# with its error); macOS lsof prints an `fcwd` record after each `p` and omits the processes of
# other users. The macOS sample follows the documented field format; it was not recorded here.
LSOF_LINUX = (b'p1\nn/proc/1/cwd (readlink: Permission denied)\n'
              b'p4242\nn/home/u/project/.claude/worktrees/w/src\n'
              b'p4243\nn/home/u/project\n'
              b'p77\nn/proc/77/cwd (stat: Permission denied)\n')
LSOF_MACOS = (b'p1\nfcwd\nn/\n'
              b'p501\nfcwd\nn/Users/u/project/.claude/worktrees/w\n'
              b'p502\nfcwd\n'
              b'p503\nfcwd\nn/private/var/folders/x/project\n')


class CleanWorktreesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.stubs = self.tmp / 'bin'
        self.stubs.mkdir()
        self.stub('tmux', TMUX)
        self.env = dict(os.environ, PATH=str(self.stubs) + os.pathsep + os.environ['PATH'],
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', LC_ALL='C',
                        GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid',
                        TMUX_STUB=str(self.tmp / 'sessions'),
                        # No detached auto-maintenance changing .git under a running case.
                        GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='gc.auto', GIT_CONFIG_VALUE_0='0',
                        GIT_CONFIG_KEY_1='maintenance.auto', GIT_CONFIG_VALUE_1='false')
        for name in ('KIT_NO_WORKTREE_CLEANUP', 'CLEAN_WORKTREES_PROC', 'TMUX_STUB_FAIL', 'GIT_DIR',
                     'GIT_WORK_TREE', 'GIT_INDEX_FILE'):
            self.env.pop(name, None)
        self.main = self.tmp / 'main'
        self.main.mkdir()
        self.git('init', '-q')
        self.git('checkout', '-q', '-b', 'main')
        (self.main / '.gitignore').write_text('build/\n*.log\n/.claude/worktrees/\n')
        (self.main / 'a').write_text('a\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'base')

    def stub(self, name, text):
        (self.stubs / name).write_text(text)
        (self.stubs / name).chmod(0o755)

    def git(self, *args, cwd=None, check=True, **extra):
        result = subprocess.run(['git', *args], cwd=cwd or self.main, env=dict(self.env, **extra),
                                capture_output=True)
        if check and result.returncode != 0:
            self.fail('git %s: %s' % (args, result.stderr.decode(errors='replace')))
        return result.stdout.decode(errors='replace').strip()

    def worktree(self, name, merge=True, commit=True, branch=None):
        """A worker's worktree as spawn_worker.sh makes it, with one commit, merged into main."""
        path = self.main / '.claude/worktrees' / name
        branch = branch or 'worktree-' + name
        self.git('worktree', 'add', '-q', str(path), '-b', branch)
        if commit:
            (path / (name + '.txt')).write_text(name + '\n')
            self.git('add', name + '.txt', cwd=path)
            self.git('commit', '-q', '-m', 'work in ' + name, cwd=path)
        if merge:
            self.git('merge', '-q', '--no-edit', branch)
        return path

    def age(self, seconds=7200):
        """Every file and folder of the repository and its worktrees, SECONDS older."""
        stamp = time.time() - seconds
        for folder, dirs, files in os.walk(bytes(self.main)):
            for name in [b''] + dirs + files:
                try:
                    os.utime(os.path.join(folder, name) if name else folder, (stamp, stamp), follow_symlinks=False)
                except FileNotFoundError:  # a lock file git just removed
                    pass

    def run_script(self, *args, cwd=None, idle=not PROC, age=True, **extra):
        if age:
            self.age()
        if idle:
            args += ('--assume-idle',)
        result = subprocess.run(['sh', str(SCRIPT), *args], cwd=cwd or self.main,
                                env=dict(self.env, **extra), capture_output=True)
        out = result.stdout.decode() + result.stderr.decode()
        self.assertEqual(result.returncode, 0, out)
        return out

    def merge_with_hook(self, branch, cwd=None, **extra):
        self.age()
        merge = subprocess.run(['git', 'merge', '--no-ff', '-m', 'merge', branch], cwd=cwd or self.main,
                               env=dict(self.env, **extra), capture_output=True, text=True)
        self.assertEqual(merge.returncode, 0, merge.stderr)
        return merge.stdout + merge.stderr

    def branch(self, name):
        return self.git('branch', '--list', 'worktree-' + name)

    def assertKept(self, path, out, *reasons):
        self.assertTrue(path.is_dir(), 'removed although it had to be kept:\n' + out)
        self.assertIn('keep   .claude/worktrees/' + path.name, out)
        for reason in reasons:
            self.assertIn(reason, out)

    def assertRemoved(self, path, out):
        self.assertFalse(path.exists(), 'kept although it was finished:\n' + out)
        self.assertIn('remove .claude/worktrees/' + path.name, out)

    def disposable(self, text):
        (self.main / '.claude').mkdir(exist_ok=True)
        (self.main / '.claude/worktree-disposable').write_text(text)

    def gitdir(self, path):
        return Path(self.git('rev-parse', '--absolute-git-dir', cwd=path))

    def recovery(self, out):
        lines = out.split('\n')
        return lines[lines.index('         branch deleted; this command, run in the main worktree, restores '
                                 'it at its last commit:') + 1]

    # --- removal, the log, the dry run ---------------------------------------------------

    def test_a_merged_clean_worktree_is_removed_logged_and_recoverable(self):
        path = self.worktree('done')
        tip = self.git('rev-parse', 'worktree-done')
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertEqual(self.branch('done'), '', out)
        self.assertEqual(self.recovery(out), "           git branch 'worktree-done' %s" % tip)
        self.assertIn('clean_worktrees: removed 1, kept 1', out)
        record = (self.main / '.git/kit-worktree-removals.log').read_text().split('\t')
        self.assertEqual(record[1:5], [os.path.realpath(path), 'refs/heads/worktree-done', tip, self.git('rev-parse', 'HEAD')])
        self.assertTrue(record[0].endswith('Z'))

    def test_the_recovery_line_is_one_shell_safe_command_that_restores_the_branch(self):
        for name, branch in (('semi', 'worktree-a;id;#'), ('quote', "worktree-it's")):
            with self.subTest(branch=branch):
                path = self.worktree(name, branch=branch)
                tip = self.git('rev-parse', branch)
                out = self.run_script('--apply')
                self.assertRemoved(path, out)
                command = self.recovery(out).strip()
                self.assertTrue(command.startswith('git branch ') and command.endswith(' ' + tip), command)
                ran = subprocess.run(['sh', '-c', command], cwd=self.main, env=self.env, capture_output=True, text=True)
                self.assertEqual(ran.returncode, 0, ran.stderr)
                self.assertNotIn('uid=', ran.stdout + ran.stderr)
                self.assertEqual(self.git('rev-parse', 'refs/heads/' + branch), tip)

    def test_a_dry_run_removes_nothing_and_prints_the_apply_command(self):
        path = self.worktree('done')
        out = self.run_script()
        self.assertTrue(path.is_dir())
        self.assertTrue(self.branch('done'))
        self.assertIn('remove .claude/worktrees/done', out)
        self.assertIn('to apply: scripts/clean_worktrees.sh --apply', out)
        self.assertFalse((self.main / '.git/kit-worktree-removals.log').exists())

    def test_the_log_record_is_written_before_anything_is_deleted_and_a_rerun_finishes(self):
        path = self.worktree('done')
        (self.main / 'sub').mkdir()
        (self.main / 'sub/report.md').write_text('archived\n')
        (path / 'sub').mkdir()
        (path / 'sub/report.md').write_text('archived\n')
        self.age()
        (path / 'sub').chmod(0o555)
        try:
            out = self.run_script('--apply', age=False)
        finally:
            (path / 'sub').chmod(0o755)
        self.assertIn('stopped: cannot delete the identical copy sub/report.md', out)
        self.assertNotIn('git refused', out)
        self.assertTrue((path / 'sub/report.md').is_file() and self.branch('done'), out)
        log = self.main / '.git/kit-worktree-removals.log'
        self.assertEqual(log.read_text().count('\n'), 1, 'no record before the first deletion')
        # The state an interrupt after the record leaves: the re-run removes it, logged again.
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertEqual(log.read_text().count('\n'), 2)

    def test_no_removal_without_its_log_record(self):
        path = self.worktree('done')
        (self.main / '.git/kit-worktree-removals.log').mkdir()
        out = self.run_script('--apply')
        self.assertIn('stopped: cannot write the removal log', out)
        self.assertTrue(path.is_dir() and self.branch('done'), out)

    def test_a_bare_main_repository_is_refused(self):
        bare = self.tmp / 'bare.git'
        self.git('clone', '-q', '--bare', str(self.main), str(bare))
        path = bare / '.claude/worktrees/w'
        self.git('worktree', 'add', '-q', str(path), '-b', 'worktree-w', cwd=bare)
        result = subprocess.run(['sh', str(SCRIPT), '--apply', '--assume-idle'], cwd=path, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('the main repository is bare', result.stdout)
        self.assertTrue(path.is_dir())

    def test_a_refused_branch_delete_is_reported_and_nothing_forced(self):
        self.git('branch', 'old')
        path = self.worktree('done')
        self.git('config', 'branch.worktree-done.remote', '.')
        self.git('config', 'branch.worktree-done.merge', 'refs/heads/old')
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertIn('branch worktree-done kept: git branch -d refused', out)
        self.assertTrue(self.branch('done'), out)

    def test_a_branch_checked_out_in_two_places_is_deleted_only_with_the_last(self):
        first = self.worktree('done')
        second = self.main / '.claude/worktrees/again'
        self.git('worktree', 'add', '-q', '-f', str(second), 'worktree-done')
        out = self.run_script('--apply')
        self.assertRemoved(first, out)
        self.assertRemoved(second, out)
        self.assertIn('branch worktree-done kept: git branch -d refused', out)
        self.assertEqual(self.branch('done'), '', out)

    def test_the_script_runs_no_forcing_or_pruning_command(self):
        tree = ast.parse((SCRIPTS / 'clean_worktrees.py').read_text())
        words = set()
        for call in ast.walk(tree):
            if isinstance(call, ast.Call):
                for node in ast.walk(ast.Module(body=[ast.Expr(a) for a in call.args], type_ignores=[])):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        words.add(node.value)
        self.assertIn('-d', words)  # the walk sees the argument lists
        for word in ('--force', '-f', '-D', '-ff', 'prune', 'clean', 'rm', '-rf'):
            self.assertNotIn(word, words)
        for shell in (SCRIPT, HOOK):
            code = [line for line in shell.read_text().split('\n') if not line.lstrip().startswith('#')]
            for word in ('rm ', '--force', 'prune', 'git clean', ' -D', 'branch -D'):
                self.assertFalse([line for line in code if word in line], (shell, word))

    # --- a: which worktrees are the script's at all ---------------------------------------

    def test_the_main_worktree_is_untouched(self):
        out = self.run_script('--apply')
        self.assertTrue((self.main / 'a').is_file())
        self.assertIn('keep   %s\n         - the main worktree' % os.path.realpath(self.main), out)

    def test_a_worktree_outside_claude_worktrees_is_untouched(self):
        outside, deeper = self.tmp / 'elsewhere', self.main / '.claude/worktrees/group/deeper'
        for path in (outside, deeper):
            self.git('worktree', 'add', '-q', '--detach', str(path))
        out = self.run_script('--apply')
        self.assertTrue(outside.is_dir() and deeper.is_dir(), out)
        self.assertEqual(out.count('not directly under .claude/worktrees'), 2, out)

    def test_the_worktree_the_script_runs_in_is_kept(self):
        path = self.worktree('done')
        out = self.run_script('--apply', cwd=path)
        self.assertKept(path, out, 'the worktree this script runs in')

    def test_a_locked_worktree_is_kept_and_its_first_reason_ends_the_audit(self):
        path = self.worktree('done', merge=False)
        self.git('worktree', 'lock', '--reason', 'kept on purpose', str(path))
        out = self.run_script('--apply')
        self.assertKept(path, out, 'locked (git worktree lock): kept on purpose')
        self.assertNotIn('is not in main', out)

    def test_a_locked_worktree_that_lost_its_git_file_or_its_folder(self):
        # A locked worktree is never reported prunable: the checks below catch it themselves.
        gone, moved = self.worktree('gone'), self.worktree('moved')
        for path in (gone, moved):
            self.git('worktree', 'lock', str(path))
        (gone / '.git').unlink()
        shutil.move(str(moved), str(self.tmp / 'moved'))
        out = self.run_script('--apply', '--all-reasons')
        self.assertKept(gone, out, 'its folder is not its own worktree')
        self.assertIn('keep   .claude/worktrees/moved\n         - locked (git worktree lock)\n'
                      '         - missing or prunable', out)

    def test_a_missing_worktree_is_kept_and_not_pruned(self):
        path = self.worktree('done')
        shutil.rmtree(path)
        out = self.run_script('--apply')
        self.assertIn('keep   .claude/worktrees/done\n         - missing or prunable', out)
        self.assertIn(str(path), self.git('worktree', 'list', '--porcelain'))
        self.assertTrue(self.branch('done'))

    def test_a_prunable_worktree_whose_folder_remains_is_kept(self):
        # Its .git file gone, the folder resolves to MAIN: every check would judge main.
        path = self.worktree('done')
        (path / '.git').unlink()
        (path / 'only-here.md').write_text('unique\n')
        out = self.run_script('--apply')
        self.assertKept(path, out, 'missing or prunable')
        self.assertTrue((path / 'only-here.md').is_file())

    def test_a_repository_made_in_a_worktree_folder_is_kept(self):
        path = self.worktree('done')
        (path / '.git').unlink()
        self.git('init', '-q', str(path))
        self.assertKept(path, self.run_script('--apply'), 'its folder is not its own worktree')

    # --- b: the worktree has ended --------------------------------------------------------------

    def test_a_fresh_worktree_with_no_commit_is_kept_after_a_merge(self):
        # Reproduced by a reviewer: a worker's fresh worktree was removed by the next merge.
        self.hooked()
        self.git('worktree', 'add', '-q', '.claude/worktrees/fresh', '-b', 'worktree-fresh')
        fresh = self.main / '.claude/worktrees/fresh'
        done = self.worktree('done', merge=False)
        out = self.merge_with_hook('worktree-done')
        self.assertTrue(fresh.is_dir(), out)
        self.assertFalse(done.exists(), out)
        self.assertKept(fresh, self.run_script(), 'no commits of its own')

    def test_a_detached_worktree_is_kept(self):
        path = self.main / '.claude/worktrees/detached'
        self.git('worktree', 'add', '-q', '--detach', str(path))
        self.assertKept(path, self.run_script('--apply'), 'detached HEAD: remove it by hand')

    def test_a_branch_without_a_reflog_from_its_creation_is_kept(self):
        path = self.worktree('nolog')
        (self.main / '.git/logs/refs/heads/worktree-nolog').unlink()
        self.assertKept(path, self.run_script('--apply'), 'its branch has no reflog')
        self.git('update-ref', '-m', 'made by hand', 'refs/heads/worktree-byhand', 'HEAD')
        other = self.main / '.claude/worktrees/byhand'
        self.git('worktree', 'add', '-q', str(other), 'worktree-byhand')
        self.git('commit', '-q', '--allow-empty', '-m', 'work', cwd=other)
        self.git('merge', '-q', 'worktree-byhand')
        self.assertKept(other, self.run_script('--apply'), 'does not begin where the branch was created')

    def test_a_non_utf8_branch_name_is_kept(self):
        self.git('worktree', 'add', '-q', str(self.main / '.claude/worktrees/odd'), '-b',
                 os.fsdecode(b'worktree-\xff'), check=False)
        if not (self.main / '.claude/worktrees/odd').is_dir():
            self.skipTest('this file system refuses a non-UTF-8 ref name (APFS)')
        path = self.main / '.claude/worktrees/odd'
        self.git('commit', '-q', '--allow-empty', '-m', 'work', cwd=path)
        self.git('merge', '-q', os.fsdecode(b'worktree-\xff'))
        self.assertKept(path, self.run_script('--apply'), 'its branch name is not UTF-8')

    # --- c: the quiet period ----------------------------------------------------------------------

    def test_a_recent_change_in_its_git_directory_or_its_files_keeps_it(self):
        path = self.worktree('done')
        gitdir = self.gitdir(path)
        (path / 'build').mkdir()
        (path / 'build/o').write_text('o\n')
        self.git('reset', '-q', 'HEAD', cwd=path)  # writes ORIG_HEAD
        self.disposable('build\n')
        recent = [gitdir / 'HEAD', gitdir / 'index', gitdir / 'logs/HEAD', gitdir / 'ORIG_HEAD',
                  self.main / '.git/logs/refs/heads/worktree-done', path / 'a', path]
        for touched in recent:
            with self.subTest(touched=touched):
                self.assertTrue(touched.exists(), touched)
                self.age()
                os.utime(touched, None)
                self.assertKept(path, self.run_script('--apply', age=False), 'quiet period: ',
                                'qualifies in 60 min (quiet-minutes=60, a margin, not a proof)')
        self.age()
        os.utime(path / 'build/o', None)  # inside a disposable folder: not counted, nor the folder
        (path / 'build/new.o').write_text('new\n')
        self.assertRemoved(path, self.run_script('--apply', age=False))

    def test_a_future_time_counts_as_recent(self):
        path = self.worktree('done')
        self.age()
        os.utime(path / 'a', (time.time() + 86400,) * 2)
        self.assertKept(path, self.run_script('--apply', age=False), 'quiet period: a file in it')

    def test_quiet_minutes_is_read_from_the_disposable_list_and_a_low_value_refused(self):
        path = self.worktree('done')
        self.disposable('quiet-minutes=15\n')
        self.age(60)
        out = self.run_script(age=False)
        self.assertKept(path, out, 'qualifies in 14 min (quiet-minutes=15')
        self.age(16 * 60)
        self.assertIn('remove .claude/worktrees/done', self.run_script(age=False))
        for line in ('quiet-minutes=5', 'quiet-minutes=x', 'quiet-minutes = 30', 'quiet-minutes=30x', 'quiet-minutes=9'):
            with self.subTest(line=line):
                self.disposable(line + '\n')
                self.age(16 * 60)
                out = self.run_script(age=False)
                self.assertIn('refused .claude/worktree-disposable line %s (quiet-minutes takes a whole '
                              'number of at least 10; 60 applies)' % line, out)
                self.assertKept(path, out, 'quiet-minutes=60')

    # --- d: nothing only it holds -------------------------------------------------------------

    def test_an_unmerged_commit_is_kept(self):
        path = self.worktree('done', merge=False)
        self.assertKept(path, self.run_script('--apply'), 'is not in main')

    def test_a_squash_merged_branch_is_kept(self):
        path = self.worktree('done', merge=False)
        self.git('merge', '-q', '--squash', 'worktree-done')
        self.git('commit', '-q', '-m', 'squashed')
        self.assertKept(path, self.run_script('--apply'), 'a squash-merged or rebased branch')

    def test_a_commit_dropped_by_a_reset_is_kept(self):
        # Reproduced by a reviewer: HEAD was in main, the dropped commit only in the reflogs.
        path = self.worktree('done')
        (path / 'later.txt').write_text('later\n')
        self.git('add', 'later.txt', cwd=path)
        self.git('commit', '-q', '-m', 'dropped', cwd=path)
        dropped = self.git('rev-parse', 'HEAD', cwd=path)
        self.git('reset', '-q', '--hard', 'HEAD~1', cwd=path)
        self.assertKept(path, self.run_script('--apply'), 'commit %s is not in main' % dropped[:12])
        log = self.gitdir(path) / 'logs/HEAD'
        log.write_text(log.read_text().split('\n')[0] + '\n')  # now only the branch's reflog names it
        self.assertKept(path, self.run_script('--apply'), 'commit %s is not in main' % dropped[:12])

    def test_a_detached_worktree_with_a_dropped_commit_names_it(self):
        path = self.main / '.claude/worktrees/detached'
        self.git('worktree', 'add', '-q', '--detach', str(path))
        self.git('commit', '-q', '--allow-empty', '-m', 'dropped', cwd=path)
        dropped = self.git('rev-parse', 'HEAD', cwd=path)
        self.git('checkout', '-q', 'HEAD~1', cwd=path)
        self.assertKept(path, self.run_script('--apply', '--all-reasons'), 'detached HEAD: remove it by hand',
                        'commit %s is not in main' % dropped[:12])

    def test_a_commit_held_only_by_a_worktree_ref_is_kept(self):
        for ref in ('refs/worktree/keep', 'refs/bisect/bad'):
            with self.subTest(ref=ref):
                path = self.worktree(ref.split('/')[1])
                tree = self.git('rev-parse', 'HEAD^{tree}', cwd=path)
                loose = self.git('commit-tree', tree, '-p', 'HEAD', '-m', 'only in a ref', cwd=path)
                self.git('update-ref', ref, loose, cwd=path)
                self.assertKept(path, self.run_script('--apply'), 'commit %s is not in main' % loose[:12])

    def test_a_worktree_without_a_head_reflog_is_kept(self):
        path = self.worktree('done')
        (self.gitdir(path) / 'logs/HEAD').unlink()
        self.assertKept(path, self.run_script('--apply'), 'its HEAD has no reflog')

    def test_a_head_no_reflog_names_is_still_checked(self):
        path = self.main / '.claude/worktrees/detached'
        self.git('worktree', 'add', '-q', '--detach', str(path))
        self.git('commit', '-q', '--allow-empty', '-m', 'unmerged', cwd=path)
        log = self.gitdir(path) / 'logs/HEAD'
        log.write_text(log.read_text().split('\n')[0] + '\n')  # the reflog names only the start
        self.assertKept(path, self.run_script('--apply', '--all-reasons'),
                        'commit %s is not in main' % self.git('rev-parse', 'HEAD', cwd=path)[:12])

    def test_a_worktree_config_is_kept(self):
        path = self.worktree('done')
        (self.gitdir(path) / 'config.worktree').write_text('[user]\n\tname = x\n')
        self.assertKept(path, self.run_script('--apply'), 'it has its own config')
        (self.gitdir(path) / 'config.worktree').write_text('')
        self.assertRemoved(path, self.run_script('--apply'))

    # --- e: an operation in progress ---------------------------------------------------------

    def test_a_rebase_or_bisect_in_progress_is_kept(self):
        rebase, bisect = self.worktree('rebase'), self.worktree('bisect')
        self.git('rebase', '--exec', 'false', 'HEAD~1', cwd=rebase, check=False)
        self.git('bisect', 'start', cwd=bisect)
        out = self.run_script('--apply', '--all-reasons')  # a rebase detaches HEAD, a reason found first
        self.assertKept(rebase, out, 'an operation is in progress: rebase-merge')
        self.assertKept(bisect, out, 'an operation is in progress: BISECT_START')

    def test_each_operation_marker_is_kept(self):
        path = self.worktree('done')
        for marker in ('CHERRY_PICK_HEAD', 'REVERT_HEAD', 'sequencer', 'MERGE_HEAD', 'rebase-apply'):
            with self.subTest(marker=marker):
                (self.gitdir(path) / marker).write_text('x\n')
                self.assertKept(path, self.run_script('--apply'), 'an operation is in progress: ' + marker)
                (self.gitdir(path) / marker).unlink()

    def test_a_merge_with_a_conflict_is_kept(self):
        path = self.worktree('done')
        self.git('checkout', '-q', '-b', 'side', 'HEAD~1', cwd=path)
        (path / 'a').write_text('side\n')
        self.git('commit', '-q', '-am', 'side', cwd=path)
        self.git('checkout', '-q', 'worktree-done', cwd=path)
        (path / 'a').write_text('mine\n')
        self.git('commit', '-q', '-am', 'mine', cwd=path)
        self.git('merge', 'side', cwd=path, check=False)
        out = self.run_script('--apply', '--all-reasons')
        self.assertKept(path, out, 'an operation is in progress: MERGE_HEAD', 'an unresolved index: a')

    # --- f: in use -----------------------------------------------------------------------------

    def test_a_process_working_inside_is_kept(self):
        path = self.worktree('done')
        (path / 'deep').mkdir()
        sleeper = subprocess.Popen(['sleep', '60'], cwd=path / 'deep')
        try:
            self.assertKept(path, self.run_script('--apply', idle=False), 'in use: process %d works inside it' % sleeper.pid)
            if PROC and shutil.which('lsof'):  # the lsof path, as on macOS
                self.assertKept(path, self.run_script('--apply', idle=False, CLEAN_WORKTREES_PROC=str(self.tmp / 'no-proc')),
                                'in use: process %d works inside it' % sleeper.pid)
        finally:
            sleeper.kill()
            sleeper.wait()
        self.assertRemoved(path, self.run_script('--apply', idle=False))

    def test_without_proc_and_lsof_it_is_kept_unless_assumed_idle(self):
        path = self.worktree('done')
        self.stub('lsof', '#!/bin/sh\necho "lsof: no permission" >&2\nexit 1\n')
        out = self.run_script('--apply', idle=False, CLEAN_WORKTREES_PROC=str(self.tmp / 'no-proc'))
        self.assertKept(path, out, 'cannot see which processes work in it (`lsof -a -d cwd -F pn` failed: lsof: no '
                        'permission)', 'scripts/clean_worktrees.sh --apply --assume-idle')
        out = self.run_script('--apply', idle=True, CLEAN_WORKTREES_PROC=str(self.tmp / 'no-proc'))
        self.assertRemoved(path, out)

    def test_a_proc_that_is_not_this_process_s_is_not_read(self):
        path = self.worktree('done')
        proc = self.tmp / 'proc'
        for pid, cwd in (('self', self.tmp), ('11', path)):
            (proc / pid).mkdir(parents=True)
            (proc / pid / 'cwd').symlink_to(os.path.realpath(cwd))
        self.stub('lsof', '#!/bin/sh\nexit 1\n')
        self.assertKept(path, self.run_script('--apply', idle=False, CLEAN_WORKTREES_PROC=str(proc)),
                        'cannot see which processes work in it (`lsof -a -d cwd -F pn` failed: exit 1)')

    def test_without_lsof_or_tmux_installed(self):
        path = self.worktree('done')
        bare = self.tmp / 'bare-bin'
        bare.mkdir()
        (bare / 'python3').symlink_to(sys.executable)
        for tool in ('git', 'sh', 'dirname'):
            (bare / tool).symlink_to(shutil.which(tool, path=self.env['PATH']))
        env = dict(PATH=str(bare), CLEAN_WORKTREES_PROC=str(self.tmp / 'no-proc'))
        self.assertKept(path, self.run_script('--apply', idle=False, **env),
                        'cannot see which processes work in it (no /proc and no lsof here)')
        self.assertRemoved(path, self.run_script('--apply', idle=True, **env))

    def test_an_unreadable_process_is_counted_and_reported_not_silently_skipped(self):
        path = self.worktree('done')
        proc = self.tmp / 'proc'
        real = os.path.realpath(path)
        for pid, cwd in (('self', os.path.realpath(self.main)), ('10', os.path.realpath(self.tmp)),
                         ('11', real + '/sub'), ('12', None), ('13', real), ('14', real + '-sibling')):
            (proc / pid).mkdir(parents=True)
            if cwd:
                (proc / pid / 'cwd').symlink_to(cwd)
        (proc / '12').chmod(0)
        try:
            out = self.run_script('--apply', idle=False, CLEAN_WORKTREES_PROC=str(proc))
        finally:
            (proc / '12').chmod(0o755)
        self.assertKept(path, out, 'in use: process 11, 13 works inside it\n')
        self.assertIn('clean_worktrees: 1 processes could not be inspected', out)
        self.assertNotIn('process 10', out)

    def test_the_lsof_parser_reads_both_platforms_and_refuses_the_unknown(self):
        cwds, unseen = clean_worktrees.parse_lsof(LSOF_LINUX)
        self.assertEqual(cwds, {b'4242': b'/home/u/project/.claude/worktrees/w/src', b'4243': b'/home/u/project'})
        self.assertEqual(unseen, 2)
        cwds, unseen = clean_worktrees.parse_lsof(LSOF_MACOS)
        self.assertEqual(cwds, {b'1': b'/', b'501': b'/Users/u/project/.claude/worktrees/w',
                                b'503': b'/private/var/folders/x/project'})
        self.assertEqual(unseen, 1)
        self.assertEqual(clean_worktrees.parse_lsof(b'p9\nnno path\n'), ({}, 1))
        for bad in (b'p1\ntREG\nn/\n', b'n/before-a-process\n', b'pabc\nn/\n', b'p1\nftxt\nn/\n', b'fcwd\np1\n'):
            with self.subTest(bad=bad):
                with self.assertRaises(clean_worktrees.Unproven):
                    clean_worktrees.parse_lsof(bad)

    def test_a_tmux_session_of_its_name_is_kept_and_only_no_server_proves_none(self):
        path = self.worktree('done')
        (self.tmp / 'sessions').write_text('lead\ndone\n')
        self.assertKept(path, self.run_script('--apply'), 'in use: a tmux session is named done')
        (self.tmp / 'sessions').write_text('lead\ndone-2\n')
        for error in ('server exited unexpectedly', 'error connecting to /tmp/tmux-1/default (Permission denied)',
                      'error connecting to /tmp/tmux-1/default (Connection refused)', ''):
            with self.subTest(error=error):
                out = self.run_script('--apply', TMUX_STUB_FAIL=error or ' ')
                self.assertKept(path, out, 'not proven: `tmux list-sessions` failed: ' + (error or 'exit 1'))
        out = self.run_script(TMUX_STUB_FAIL='error connecting to /tmp/tmux-1/default (No such file or directory)')
        self.assertIn('remove .claude/worktrees/done', out)
        (self.tmp / 'sessions').unlink()
        self.assertRemoved(path, self.run_script('--apply'))

    def test_a_held_gate_lock_is_kept(self):
        path = self.worktree('done')
        lock = self.gitdir(path) / 'check.lock'
        with open(lock, 'w') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            self.assertKept(path, self.run_script('--apply'), 'in use: the gate holds its lock')
        self.assertRemoved(path, self.run_script('--apply'))

    # --- g: the index and git filters ----------------------------------------------------------

    def tracked(self, change, reason, name='done'):
        path = self.worktree(name)
        change(path)
        self.assertKept(path, self.run_script('--apply'), reason)

    def test_a_staged_change_is_kept(self):
        def change(path):
            (path / 'a').write_text('staged\n')
            self.git('add', 'a', cwd=path)
        self.tracked(change, 'tracked change, staged: a')

    def test_a_modified_file_is_kept(self):
        self.tracked(lambda path: (path / 'a').write_text('changed\n'), 'tracked change, modified: a')

    def test_a_deleted_file_is_kept(self):
        self.tracked(lambda path: (path / 'a').unlink(), 'tracked change, deleted: a')

    def test_an_intent_to_add_is_kept(self):
        def change(path):
            (path / 'n').write_text('n\n')
            self.git('add', '-N', 'n', cwd=path)
        self.tracked(change, 'tracked change, intent-to-add: n')

    def test_an_assume_unchanged_or_skip_worktree_edit_git_does_not_report_is_kept(self):
        for flag in ('--assume-unchanged', '--skip-worktree'):
            with self.subTest(flag=flag):
                def change(path):
                    self.git('update-index', flag, 'a', cwd=path)
                    (path / 'a').write_text('hidden from git status\n')
                self.tracked(change, 'index entries git does not compare (skip-worktree or assume-unchanged): a',
                             name=flag.strip('-'))

    def test_a_submodule_is_kept(self):
        path = self.worktree('done', merge=False)
        head = self.git('rev-parse', 'HEAD')
        self.git('update-index', '--add', '--cacheinfo', '160000,%s,sub' % head, cwd=path)
        self.git('commit', '-q', '-m', 'a submodule', cwd=path)
        self.git('merge', '-q', 'worktree-done')
        self.assertKept(path, self.run_script('--apply'), 'a submodule, whose state this script cannot judge: sub')

    def test_a_clean_filter_that_hides_an_edit_is_kept(self):
        (self.main / '.gitattributes').write_text('notes.txt filter=strip\n')
        (self.main / 'notes.txt').write_text('public\n')
        (self.main / 'b').write_text('b\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'attributes')
        path = self.worktree('done')
        self.git('config', 'filter.strip.clean', "sed '/SECRET/d'")
        (path / 'notes.txt').write_text('public\nSECRET one\n')
        self.git('add', 'notes.txt', cwd=path)  # the filter strips the line: nothing to commit
        (path / 'notes.txt').write_text('public\nSECRET two\n')
        # The premise: git calls the edited file unchanged, so `git worktree remove` would delete it.
        self.assertEqual(self.git('status', '--porcelain', cwd=path), '')
        self.assertKept(path, self.run_script('--apply'), 'a tracked path has a clean or process filter or the '
                        'ident attribute, so git may call an edited file unchanged: notes.txt')
        self.assertIn('SECRET two', (path / 'notes.txt').read_text())
        self.git('config', '--unset', 'filter.strip.clean')
        self.git('config', 'filter.strip.process', ' ')  # a blank command still filters
        self.assertKept(path, self.run_script('--apply'), 'unchanged: notes.txt')
        self.git('config', '--unset', 'filter.strip.process')
        (path / 'notes.txt').write_text('public\n')
        (path / '.gitattributes').write_text('b ident\nnotes.txt filter=unconfigured\n')
        self.git('commit', '-q', '-am', 'ident', cwd=path)
        self.git('merge', '-q', 'worktree-done')
        self.assertKept(path, self.run_script('--apply'), 'unchanged: b')
        (path / '.gitattributes').write_text('notes.txt filter=unconfigured\n')
        self.git('commit', '-q', '-am', 'only an unconfigured driver', cwd=path)
        self.git('merge', '-q', 'worktree-done')
        self.assertRemoved(path, self.run_script('--apply'))

    # --- h: what git does not track ----------------------------------------------------------

    def test_an_untracked_unique_file_is_kept_and_named(self):
        path = self.worktree('done')
        (self.main / 'notes.md').write_text('main\n')
        (path / 'notes.md').write_text('mine\n')  # same name and size, other bytes
        (path / 'mine.md').write_text('only here\n')
        self.assertKept(path, self.run_script('--apply'),
                        'files with no identical copy in main, outside a disposable folder: mine.md, notes.md')

    def test_an_ignored_unique_file_outside_a_disposable_folder_is_kept(self):
        path = self.worktree('done')
        (path / 'build').mkdir()
        (path / 'build/out.o').write_text('object\n')
        (path / 'run.log').write_text('log\n')
        self.assertKept(path, self.run_script('--apply'), 'build/out.o, run.log',
                        'consider listing them in .claude/worktree-disposable: build')

    def test_an_identical_untracked_file_is_removed_with_the_worktree(self):
        path = self.worktree('done')
        (self.main / 'docs/reviews').mkdir(parents=True)
        (self.main / 'docs/reviews/r.md').write_bytes(b'report\n')
        (path / 'docs/reviews').mkdir(parents=True)
        (path / 'docs/reviews/r.md').write_bytes(b'report\n')
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertIn('1 identical files', out)
        self.assertEqual((self.main / 'docs/reviews/r.md').read_bytes(), b'report\n')

    def test_an_identical_copy_reached_through_a_symlink_in_main_does_not_count(self):
        path = self.worktree('done')
        (self.tmp / 'outside').mkdir()
        (self.tmp / 'outside/f').write_text('same\n')
        (self.main / 'linked').symlink_to(self.tmp / 'outside')
        (path / 'linked').mkdir()
        (path / 'linked/f').write_text('same\n')
        (self.main / 'g').symlink_to(self.tmp / 'outside/f')
        (path / 'g').write_text('same\n')
        self.assertKept(path, self.run_script('--apply'), 'no identical copy in main, outside a disposable folder: g, linked/f\n')

    def test_a_disposable_folder_with_content_is_removed(self):
        self.disposable('# build output\nbuild\n')
        path = self.worktree('done')
        (path / 'app/build/obj').mkdir(parents=True)
        (path / 'app/build/obj/out.o').write_bytes(b'x' * 1000)
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertIn('1000 disposable bytes', out)
        self.assertIn('disposable_bytes=1000', (self.main / '.git/kit-worktree-removals.log').read_text())

    def test_a_disposable_path_entry_matches_only_its_own_folder(self):
        # A NAME matches a folder, never a file's own name; a PATH matches from the root only,
        # folder by folder (app/build is not app/build2).
        self.disposable('app/build\nout.o\n')
        path = self.worktree('done')
        for folder in ('app/build', 'app/build2', 'other/build', 'deep/app/build'):
            (path / folder).mkdir(parents=True)
            (path / folder / 'out.o').write_text('o\n')
        self.assertKept(path, self.run_script('--apply'),
                        'disposable folder: app/build2/out.o, deep/app/build/out.o, other/build/out.o\n')

    def test_a_name_entry_does_not_reach_below_a_place_that_holds_work(self):
        self.disposable('build\n')
        path = self.worktree('done')
        for folder in ('docs/build', '.claude/build', 'scripts/x/build', '.myagentkit/build', 'ok/build'):
            (path / folder).mkdir(parents=True)
            (path / folder / 'f').write_text('f\n')
        self.assertKept(path, self.run_script('--apply'), '.claude/build/f, .myagentkit/build/f, docs/build/f, '
                        'scripts/x/build/f\n')

    def test_disposable_matching_folder_by_folder(self):
        for rel, entries, expected in (
                (b'app/build/x', [b'app/build'], True), (b'app/build2/x', [b'app/build'], False),
                (b'app/buildx', [b'app/build'], False), (b'xapp/build/x', [b'app/build'], False),
                (b'app/build', [b'app/build'], False), (b'a/build/b/x', [b'build'], True),
                (b'build', [b'build'], False), (b'docs/build/x', [b'build'], False),
                (b'a/build/docs/x', [b'build'], True), (b'.git/build/x', [b'build'], False),
                (b'a/b/c', [b'b', b'x/y'], True), (b'a/b/c', [], False)):
            with self.subTest(rel=rel, entries=entries):
                self.assertIs(clean_worktrees.disposable(rel, entries), expected)

    def test_untracked_unignored_content_in_a_disposable_folder_is_kept(self):
        self.disposable('cache\n')
        path = self.worktree('done')
        (path / 'cache').mkdir()
        (path / 'cache/f').write_text('f\n')
        self.assertKept(path, self.run_script('--apply'),
                        'untracked and not ignored inside a disposable folder (`git worktree remove` refuses them')

    def test_a_refused_disposable_entry_counts_for_nothing(self):
        self.disposable('docs\n/abs\n../up\nok/../docs\n.claude\nscripts/\na//b\n./c\n')
        path = self.worktree('done')
        (path / 'docs').mkdir()
        (path / 'docs/notes.md').write_text('work\n')
        out = self.run_script('--apply')
        self.assertKept(path, out, 'disposable folder: docs/notes.md')
        for entry in ('docs', '/abs', '../up', 'ok/../docs', '.claude', 'scripts/', 'a//b', './c'):
            self.assertIn('refused .claude/worktree-disposable line %s (empty, absolute' % entry, out)

    def test_a_symlink_is_kept(self):
        path = self.worktree('done')
        (path / 'link').symlink_to('a')
        self.assertKept(path, self.run_script('--apply'), 'not a regular file (a symlink, FIFO, socket, device or '
                        'nested repository), outside a disposable folder: link')

    def test_a_fifo_git_does_not_list_is_kept(self):
        path = self.worktree('done')
        os.mkfifo(path / 'pipe')
        self.assertKept(path, self.run_script('--apply'), 'outside a disposable folder: pipe')

    def test_a_nested_repository_is_kept(self):
        path = self.worktree('done')
        self.git('init', '-q', str(path / 'nested'))
        self.assertKept(path, self.run_script('--apply'), 'nested/.git/')

    def test_file_names_with_a_space_a_newline_and_a_non_utf8_byte(self):
        names = [b'with space', b'new\nline', b'bad\xffbyte']
        try:
            (self.tmp / os.fsdecode(b'bad\xffbyte')).write_bytes(b'')
        except OSError:  # a file system that stores names as UTF-8 only (APFS) refuses it
            names.pop()
        done, kept = self.worktree('done'), self.worktree('kept')
        for name in names:
            for root in (self.main, done):
                Path(os.fsdecode(bytes(root) + b'/' + name)).write_bytes(b'same\n')
            Path(os.fsdecode(bytes(kept) + b'/' + name)).write_bytes(b'unique\n')
        out = self.run_script('--apply')
        self.assertRemoved(done, out)
        self.assertIn('%d identical files' % len(names), out)
        self.assertKept(kept, out, 'new\\nline', 'with space')
        if len(names) == 3:
            self.assertIn('bad\\xffbyte', out)
        for name in names:
            self.assertTrue(os.path.lexists(bytes(self.main) + b'/' + name))

    def test_the_first_reason_stops_the_audit_and_all_reasons_runs_every_check(self):
        path = self.worktree('done', merge=False)
        (path / 'mine.md').write_text('only here\n')
        out = self.run_script('--apply')
        self.assertKept(path, out, 'is not in main')
        self.assertNotIn('mine.md', out)
        self.assertKept(path, self.run_script('--all-reasons'), 'is not in main', 'mine.md')

    # --- output git never prints, and a git that fails -----------------------------------------

    def test_unknown_output_or_a_failing_git_keeps(self):
        shims = self.tmp / 'shim'
        shims.mkdir()
        (shims / 'git').write_text(SHIM)
        (shims / 'git').chmod(0o755)
        path = self.worktree('done')
        env = dict(PATH=str(shims) + os.pathsep + self.env['PATH'], REAL_GIT=shutil.which('git', path=self.env['PATH']))
        for mode, reason in (('status', 'not proven: `git status` printed an entry this script does not know: Z something new'),
                             ('list', '`git worktree list` printed a field this script does not know: frobbed'),
                             ('fail:rev-list', 'not proven: `git rev-list --stdin` failed: fatal: refused by the shim'),
                             ('fail:reflog', 'not proven: `git reflog show --no-abbrev'),
                             ('fail:check-attr', 'not proven: `git check-attr'),
                             ('fail:for-each-ref', 'not proven: `git for-each-ref'),
                             ('fail:--absolute-git-dir', 'not proven: `git rev-parse --absolute-git-dir` failed'),
                             ('fail:remove', 'stopped: git refused to remove it: fatal: refused by the shim')):
            with self.subTest(mode=mode):
                out = self.run_script('--apply', SHIM=mode, **env)
                if mode == 'fail:remove':
                    out = out.replace('remove .claude/worktrees/done', 'keep   .claude/worktrees/done')
                    self.assertNotIn('git branch ', out)
                self.assertKept(path, out, reason)
                self.assertTrue(self.branch('done'), out)

    def test_a_git_dir_in_the_environment_does_not_hide_a_worktrees_own_index(self):
        # A hook in a linked worktree runs with GIT_DIR set. Inherited, it made `git -C <worktree>`
        # read main's index, where a deletion staged in the worktree does not exist.
        path = self.worktree('done')
        self.git('rm', '-q', '--cached', 'a', cwd=path)
        out = self.run_script('--apply', GIT_DIR=str(self.main / '.git'))
        self.assertKept(path, out, 'tracked change, staged: a')

    # --- the hook --------------------------------------------------------------------------------

    def hooked(self, script=True):
        """main with the hook, the script and the list committed, so every worktree carries them too."""
        (self.main / '.githooks').mkdir()
        shutil.copy(HOOK, self.main / '.githooks/post-merge')
        if script:
            (self.main / 'scripts').mkdir()
            for name in ('clean_worktrees.sh', 'clean_worktrees.py'):
                shutil.copy(SCRIPTS / name, self.main / 'scripts' / name)
            self.disposable('')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'hook')
        self.git('config', 'core.hooksPath', '.githooks')

    def test_the_hook_cleans_after_a_merge_in_the_main_worktree_and_prints_little(self):
        self.hooked()
        path = self.worktree('done', merge=False)
        kept = self.worktree('kept', merge=False)
        out = self.merge_with_hook('worktree-done')
        # git hands a hook's output to stderr; the hook runs the real process scan.
        self.assertRemoved(path, out)
        self.assertTrue(kept.is_dir())
        self.assertNotIn('keep   ', out)
        self.assertIn('clean_worktrees: removed 1, kept 2, freed', out)
        self.assertIn('; the reasons: scripts/clean_worktrees.sh', out)
        out = self.merge_with_hook('worktree-kept')
        self.assertEqual([line for line in out.split('\n') if 'clean_worktrees' in line],
                         [line for line in out.split('\n') if line.startswith('clean_worktrees: removed 1')], out)

    def test_the_hook_prints_one_line_when_nothing_is_removed(self):
        self.hooked()
        self.worktree('fresh', commit=False, merge=False)
        self.git('checkout', '-q', '-b', 'side')
        self.git('commit', '-q', '--allow-empty', '-m', 'side')
        self.git('checkout', '-q', 'main')
        out = self.merge_with_hook('side')
        lines = [line for line in out.split('\n') if line.startswith(('clean_worktrees', 'keep', 'remove', ' '))]
        self.assertEqual(len(lines), 1, out)
        self.assertTrue(lines[0].startswith('clean_worktrees: removed 0, kept 2'), out)

    def test_the_hook_without_the_overlay_says_so_once(self):
        self.hooked(script=False)
        for count in (1, 0):
            self.git('checkout', '-q', '-b', 'side%d' % count)
            self.git('commit', '-q', '--allow-empty', '-m', 'side')
            self.git('checkout', '-q', 'main')
            out = self.merge_with_hook('side%d' % count)
            self.assertEqual(out.count('post-merge: worktree clean-up is not installed'), count, out)

    def test_the_hook_does_nothing_after_a_merge_inside_a_linked_worktree(self):
        self.hooked()
        finished = self.worktree('finished')
        worker = self.worktree('worker', merge=False)
        self.git('commit', '-q', '--allow-empty', '-m', 'main moved')
        out = self.merge_with_hook('main', cwd=worker)
        self.assertNotIn('clean_worktrees', out)
        self.assertTrue(finished.is_dir())
        self.assertIn('remove .claude/worktrees/finished', self.run_script())

    def test_the_off_switch_stops_the_hook(self):
        self.hooked()
        path = self.worktree('done', merge=False)
        out = self.merge_with_hook('worktree-done', KIT_NO_WORKTREE_CLEANUP='1')
        self.assertTrue(path.is_dir())
        self.assertNotIn('clean_worktrees', out)

    def test_a_failing_script_leaves_the_merge_complete(self):
        self.hooked()
        path = self.worktree('done', merge=False)
        (self.main / 'scripts/clean_worktrees.sh').write_text('#!/bin/sh\nexit 3\n')
        out = self.merge_with_hook('worktree-done')
        self.assertIn('post-merge: scripts/clean_worktrees.sh stopped with an error', out)
        self.assertEqual(self.git('rev-parse', 'HEAD^2'), self.git('rev-parse', 'worktree-done'))
        self.assertTrue(path.is_dir())

    def test_bootstrap_installs_the_script_the_list_and_the_hook(self):
        project = self.tmp / 'project'
        result = subprocess.run(['sh', str(ROOT / 'bootstrap.sh'), str(project), '--overlay', 'claude-code'],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for rel in ('scripts/clean_worktrees.sh', '.githooks/post-merge'):
            self.assertTrue(os.access(project / rel, os.X_OK), rel)
        for rel in ('scripts/clean_worktrees.py', '.claude/worktree-disposable'):
            self.assertTrue((project / rel).is_file(), rel)


if __name__ == '__main__':
    unittest.main()
