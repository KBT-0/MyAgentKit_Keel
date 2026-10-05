"""scripts/clean_worktrees.sh removes a merged worktree only when nothing in it can be lost.

Each check that keeps a worktree has a case here that builds the state it must catch, in a
throwaway repository; tmux is a stub on PATH, so a live session on the machine running the
tests changes nothing. A kept worktree must still be there, with its branch, and the report
must name the reason.
"""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'overlays/claude-code/files/scripts'
SCRIPT = SCRIPTS / 'clean_worktrees.sh'
HOOK = ROOT / 'core/.githooks/post-merge'
# Without /proc (macOS) every worktree is kept unless --assume-idle is given; the cases below
# pass it there, except the ones about that check.
PROC = os.path.exists('/proc/self/cwd')

TMUX = '''#!/bin/sh
if [ -n "${TMUX_STUB_FAIL:-}" ]; then echo "server exited unexpectedly" >&2; exit 1; fi
if [ -f "$TMUX_STUB" ]; then cat "$TMUX_STUB"; exit 0; fi
echo "no server running on /tmp/tmux-stub/default" >&2
exit 1
'''
# Wraps the real git to print what this git never does: the script must keep, not guess.
SHIM = '''#!%s
import os, subprocess, sys
args, mode = sys.argv[1:], os.environ.get('SHIM', '')
if mode == 'merge-base' and 'merge-base' in args or mode == 'remove' and 'remove' in args:
    sys.stderr.write('fatal: refused by the shim\\n')
    sys.exit(128)
if mode == 'tip' and '--verify' in args and any(a.startswith('refs/heads/') for a in args):
    print('0' * 40)
    sys.exit(0)
result = subprocess.run([os.environ['REAL_GIT']] + args, stdout=subprocess.PIPE)
out = result.stdout
if mode == 'status' and 'status' in args:
    out += b'Z something new\\0'
if mode == 'list' and 'list' in args:
    out = out.replace(b'\\0\\0', b'\\0frobbed\\0\\0')
sys.stdout.buffer.write(out)
sys.exit(result.returncode)
''' % sys.executable


class CleanWorktreesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        stubs = self.tmp / 'bin'
        stubs.mkdir()
        (stubs / 'tmux').write_text(TMUX)
        (stubs / 'tmux').chmod(0o755)
        self.env = dict(os.environ, PATH=str(stubs) + os.pathsep + os.environ['PATH'],
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', LC_ALL='C',
                        GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid',
                        TMUX_STUB=str(self.tmp / 'sessions'))
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

    def git(self, *args, cwd=None, check=True, **extra):
        result = subprocess.run(['git', *args], cwd=cwd or self.main, env=dict(self.env, **extra),
                                capture_output=True)
        if check and result.returncode != 0:
            self.fail('git %s: %s' % (args, result.stderr.decode(errors='replace')))
        return result.stdout.decode(errors='replace').strip()

    def worktree(self, name, merge=True, commit=True):
        """A worker's worktree as spawn_worker.sh makes it, with one commit, merged into main."""
        path = self.main / '.claude/worktrees' / name
        self.git('worktree', 'add', '-q', str(path), '-b', 'worktree-' + name)
        if commit:
            (path / (name + '.txt')).write_text(name + '\n')
            self.git('add', name + '.txt', cwd=path)
            self.git('commit', '-q', '-m', 'work in ' + name, cwd=path)
        if merge:
            self.git('merge', '-q', '--no-edit', 'worktree-' + name)
        return path

    def run_script(self, *args, cwd=None, idle=not PROC, **extra):
        if idle:
            args += ('--assume-idle',)
        result = subprocess.run(['sh', str(SCRIPT), *args], cwd=cwd or self.main,
                                env=dict(self.env, **extra), capture_output=True)
        out = result.stdout.decode() + result.stderr.decode()
        self.assertEqual(result.returncode, 0, out)
        return out

    def branch(self, name):
        return self.git('branch', '--list', 'worktree-' + name)

    def assertKept(self, path, out, *reasons):
        self.assertTrue(path.is_dir(), 'removed although it had to be kept:\n' + out)
        self.assertTrue(self.branch(path.name), 'its branch is gone:\n' + out)
        self.assertIn('keep   .claude/worktrees/' + path.name, out)
        for reason in reasons:
            self.assertIn(reason, out)

    def assertRemoved(self, path, out):
        self.assertFalse(path.exists(), 'kept although it was finished:\n' + out)
        self.assertIn('remove .claude/worktrees/' + path.name, out)

    def disposable(self, text):
        (self.main / '.claude').mkdir(exist_ok=True)
        (self.main / '.claude/worktree-disposable').write_text(text)

    # --- removal, the log, the dry run ---------------------------------------------------

    def test_a_merged_clean_worktree_is_removed_logged_and_recoverable(self):
        path = self.worktree('done')
        tip = self.git('rev-parse', 'worktree-done')
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertEqual(self.branch('done'), '', out)
        self.assertIn('recover the branch with: git branch worktree-done %s' % tip, out)
        self.assertIn('clean_worktrees: removed 1, kept 1', out)
        record = (self.main / '.git/kit-worktree-removals.log').read_text().split('\t')
        self.assertEqual(record[1:5], [os.path.realpath(path), 'refs/heads/worktree-done', tip, self.git('rev-parse', 'HEAD')])
        self.assertTrue(record[0].endswith('Z'))
        self.git('branch', 'worktree-done', tip)

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
        (path / 'sub').chmod(0o555)
        try:
            out = self.run_script('--apply')
        finally:
            (path / 'sub').chmod(0o755)
        self.assertIn('stopped: cannot delete the identical copy sub/report.md', out)
        self.assertTrue((path / 'sub/report.md').is_file() and self.branch('done'), out)
        log = self.main / '.git/kit-worktree-removals.log'
        self.assertEqual(log.read_text().count('\n'), 1, 'no record before the first deletion')
        # The state an interrupt after the record leaves: the re-run removes it, logged again.
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertEqual(log.read_text().count('\n'), 2)

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

    # --- b: locked, missing ----------------------------------------------------------------

    def test_a_locked_worktree_is_kept(self):
        path = self.worktree('done')
        self.git('worktree', 'lock', '--reason', 'kept on purpose', str(path))
        self.assertKept(path, self.run_script('--apply'), 'locked (git worktree lock): kept on purpose')

    def test_a_missing_worktree_is_kept_and_not_pruned(self):
        path = self.worktree('done')
        shutil.rmtree(path)
        out = self.run_script('--apply')
        self.assertIn('keep   .claude/worktrees/done\n         - missing or prunable', out)
        self.assertIn(str(path), self.git('worktree', 'list', '--porcelain'))
        self.assertTrue(self.branch('done'))

    # --- c: an operation in progress ---------------------------------------------------------

    def test_a_rebase_or_bisect_in_progress_is_kept(self):
        rebase, bisect = self.worktree('rebase'), self.worktree('bisect')
        self.git('rebase', '--exec', 'false', 'HEAD~1', cwd=rebase, check=False)
        self.git('bisect', 'start', cwd=bisect)
        out = self.run_script('--apply')
        self.assertKept(rebase, out, 'an operation is in progress: rebase-merge')
        self.assertKept(bisect, out, 'an operation is in progress: BISECT_START')

    def test_a_merge_with_a_conflict_is_kept(self):
        path = self.worktree('done')
        self.git('checkout', '-q', '-b', 'side', 'HEAD~1', cwd=path)
        (path / 'a').write_text('side\n')
        self.git('commit', '-q', '-am', 'side', cwd=path)
        self.git('checkout', '-q', 'worktree-done', cwd=path)
        (path / 'a').write_text('mine\n')
        self.git('commit', '-q', '-am', 'mine', cwd=path)
        self.git('merge', 'side', cwd=path, check=False)
        out = self.run_script('--apply')
        self.assertKept(path, out, 'an operation is in progress: MERGE_HEAD', 'an unresolved index: a')

    # --- d: merged into main -----------------------------------------------------------------

    def test_an_unmerged_commit_is_kept(self):
        path = self.worktree('done', merge=False)
        self.assertKept(path, self.run_script('--apply'), 'is not in main: unmerged commits')

    def test_a_squash_merged_branch_is_kept(self):
        path = self.worktree('done', merge=False)
        self.git('merge', '-q', '--squash', 'worktree-done')
        self.git('commit', '-q', '-m', 'squashed')
        self.assertKept(path, self.run_script('--apply'), 'a squash-merged or rebased branch')

    def test_a_detached_head_is_removed_when_merged_and_kept_when_not(self):
        merged, unmerged = self.main / '.claude/worktrees/merged', self.main / '.claude/worktrees/unmerged'
        self.git('worktree', 'add', '-q', '--detach', str(merged))
        self.git('worktree', 'add', '-q', '--detach', str(unmerged))
        (unmerged / 'n').write_text('n\n')
        self.git('add', 'n', cwd=unmerged)
        self.git('commit', '-q', '-m', 'detached work', cwd=unmerged)
        out = self.run_script('--apply')
        self.assertRemoved(merged, out)
        self.assertIn('detached HEAD %s; its commits are in main' % self.git('rev-parse', 'HEAD'), out)
        self.assertTrue(unmerged.is_dir(), out)
        self.assertIn('keep   .claude/worktrees/unmerged\n         - HEAD', out)

    # --- e: tracked state ----------------------------------------------------------------------

    def tracked(self, change, reason):
        path = self.worktree('done')
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

    def test_an_assume_unchanged_edit_git_does_not_report_is_kept(self):
        def change(path):
            self.git('update-index', '--assume-unchanged', 'a', cwd=path)
            (path / 'a').write_text('hidden from git status\n')
        self.tracked(change, 'index entries git does not compare (skip-worktree or assume-unchanged): a')

    def test_a_submodule_is_kept(self):
        path = self.worktree('done', merge=False)
        head = self.git('rev-parse', 'HEAD')
        self.git('update-index', '--add', '--cacheinfo', '160000,%s,sub' % head, cwd=path)
        self.git('commit', '-q', '-m', 'a submodule', cwd=path)
        self.git('merge', '-q', 'worktree-done')
        self.assertKept(path, self.run_script('--apply'), 'a submodule, whose state this script cannot judge: sub')

    # --- f: what git does not track ----------------------------------------------------------

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
        self.assertKept(path, self.run_script('--apply'), 'no identical copy in main, outside a disposable folder: linked/f')

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
        # A NAME matches a folder, never a file's own name; a PATH matches from the root only.
        self.disposable('app/build\nout.o\n')
        path = self.worktree('done')
        for folder in ('app/build', 'other/build', 'deep/app/build'):
            (path / folder).mkdir(parents=True)
            (path / folder / 'out.o').write_text('o\n')
        self.assertKept(path, self.run_script('--apply'),
                        'disposable folder: deep/app/build/out.o, other/build/out.o\n')

    def test_untracked_unignored_content_in_a_disposable_folder_is_kept(self):
        self.disposable('cache\n')
        path = self.worktree('done')
        (path / 'cache').mkdir()
        (path / 'cache/f').write_text('f\n')
        self.assertKept(path, self.run_script('--apply'),
                        'untracked and not ignored inside a disposable folder (`git worktree remove` refuses them')

    def test_a_refused_disposable_entry_counts_for_nothing(self):
        self.disposable('docs\n/abs\n../up\nok/../docs\n.claude\nscripts/\n')
        path = self.worktree('done')
        (path / 'docs').mkdir()
        (path / 'docs/notes.md').write_text('work\n')
        out = self.run_script('--apply')
        self.assertKept(path, out, 'disposable folder: docs/notes.md')
        for entry in ('docs', '/abs', '../up', 'ok/../docs', '.claude', 'scripts/'):
            self.assertIn('refused disposable entry %s (' % entry, out)

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

    # --- g: in use -----------------------------------------------------------------------------

    def test_a_process_working_inside_is_kept(self):
        path = self.worktree('done')
        (path / 'deep').mkdir()
        sleeper = subprocess.Popen(['sleep', '60'], cwd=path / 'deep')
        try:
            self.assertKept(path, self.run_script('--apply', idle=False),
                            'in use: process %d works inside it' % sleeper.pid if PROC
                            else 'cannot see which processes work in it (no /proc here)')
        finally:
            sleeper.kill()
            sleeper.wait()
        self.assertRemoved(path, self.run_script('--apply'))

    def test_without_proc_it_is_kept_unless_assumed_idle(self):
        path = self.worktree('done')
        out = self.run_script('--apply', idle=False, CLEAN_WORKTREES_PROC=str(self.tmp / 'no-proc'))
        self.assertKept(path, out, 'scripts/clean_worktrees.sh --apply --assume-idle')
        out = self.run_script('--apply', idle=True, CLEAN_WORKTREES_PROC=str(self.tmp / 'no-proc'))
        self.assertRemoved(path, out)

    def test_a_tmux_session_of_its_name_is_kept(self):
        path = self.worktree('done')
        (self.tmp / 'sessions').write_text('lead\ndone\n')
        self.assertKept(path, self.run_script('--apply'), 'in use: a tmux session is named done')
        (self.tmp / 'sessions').write_text('lead\ndone-2\n')
        self.assertKept(path, self.run_script('--apply', TMUX_STUB_FAIL='1'),
                        'not proven: `tmux list-sessions` failed: server exited unexpectedly')
        self.assertRemoved(path, self.run_script('--apply'))

    def test_a_held_gate_lock_is_kept(self):
        path = self.worktree('done')
        lock = Path(self.git('rev-parse', '--absolute-git-dir', cwd=path)) / 'check.lock'
        with open(lock, 'w') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            self.assertKept(path, self.run_script('--apply'), 'in use: the gate holds its lock')
        self.assertRemoved(path, self.run_script('--apply'))

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
                             ('merge-base', 'not proven: `git merge-base --is-ancestor'),
                             ('tip', 'its branch refs/heads/worktree-done points at 000000000000'),
                             ('remove', 'stopped: git refused to remove it: fatal: refused by the shim')):
            with self.subTest(mode=mode):
                out = self.run_script('--apply', SHIM=mode, **env)
                if mode == 'remove':
                    out = out.replace('remove .claude/worktrees/done', 'keep   .claude/worktrees/done')
                    self.assertNotIn('recover the branch', out)
                self.assertKept(path, out, reason)

    def test_a_git_dir_in_the_environment_does_not_hide_a_worktrees_own_index(self):
        # A hook in a linked worktree runs with GIT_DIR set. Inherited, it made `git -C <worktree>`
        # read main's index, where a deletion staged in the worktree does not exist.
        path = self.worktree('done')
        self.git('rm', '-q', '--cached', 'a', cwd=path)
        out = self.run_script('--apply', GIT_DIR=str(self.main / '.git'))
        self.assertKept(path, out, 'tracked change, staged: a')

    # --- the hook --------------------------------------------------------------------------------

    def hooked(self):
        """main with the hook and the script committed, so every worktree carries them too."""
        (self.main / '.githooks').mkdir()
        shutil.copy(HOOK, self.main / '.githooks/post-merge')
        (self.main / 'scripts').mkdir()
        for name in ('clean_worktrees.sh', 'clean_worktrees.py'):
            shutil.copy(SCRIPTS / name, self.main / 'scripts' / name)
        self.git('add', '.githooks', 'scripts')
        self.git('commit', '-q', '-m', 'hook')
        self.git('config', 'core.hooksPath', '.githooks')

    def test_the_hook_cleans_after_a_merge_in_the_main_worktree(self):
        self.hooked()
        path = self.worktree('done', merge=False)
        merge = subprocess.run(['git', 'merge', '--no-ff', '-m', 'merge', 'worktree-done'], cwd=self.main,
                               env=self.env, capture_output=True, text=True)
        self.assertEqual(merge.returncode, 0, merge.stderr)
        # git hands a hook's output to stderr. Without /proc the hook keeps it, and says how to
        # run the script by hand.
        if PROC:
            self.assertRemoved(path, merge.stderr)
            self.assertIn('clean_worktrees: removed 1', merge.stderr)
        else:
            self.assertIn('--apply --assume-idle', merge.stderr)

    def test_the_hook_does_nothing_after_a_merge_inside_a_linked_worktree(self):
        self.hooked()
        finished = self.worktree('finished', commit=False)
        worker = self.worktree('worker', merge=False)
        self.git('commit', '-q', '--allow-empty', '-m', 'main moved')
        merge = subprocess.run(['git', 'merge', '--no-ff', '-m', 'merge main', 'main'], cwd=worker,
                               env=self.env, capture_output=True, text=True)
        self.assertEqual(merge.returncode, 0, merge.stderr)
        self.assertNotIn('clean_worktrees', merge.stdout + merge.stderr)
        self.assertTrue(finished.is_dir())
        self.assertIn('remove .claude/worktrees/finished', self.run_script())

    def test_the_off_switch_stops_the_hook(self):
        self.hooked()
        path = self.worktree('done', merge=False)
        merge = subprocess.run(['git', 'merge', '--no-ff', '-m', 'merge', 'worktree-done'], cwd=self.main,
                               env=dict(self.env, KIT_NO_WORKTREE_CLEANUP='1'), capture_output=True, text=True)
        self.assertEqual(merge.returncode, 0, merge.stderr)
        self.assertTrue(path.is_dir())
        self.assertNotIn('clean_worktrees', merge.stdout + merge.stderr)

    def test_a_failing_script_leaves_the_merge_complete(self):
        self.hooked()
        path = self.worktree('done', merge=False)
        (self.main / 'scripts/clean_worktrees.sh').write_text('#!/bin/sh\nexit 3\n')
        merge = subprocess.run(['git', 'merge', '--no-ff', '-m', 'merge', 'worktree-done'], cwd=self.main,
                               env=self.env, capture_output=True, text=True)
        self.assertEqual(merge.returncode, 0, merge.stderr)
        self.assertIn('post-merge: scripts/clean_worktrees.sh stopped with an error', merge.stderr)
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
