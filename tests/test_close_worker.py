"""close_worker.sh ends a worker's tmux session and removes its worktree through the audit.

tmux is a stub on PATH that records every call, so no real session is touched; the worktree
is a real one in a throwaway repository, and its removal is clean_worktrees.sh's own, every
proof included (no --assume-idle: the process listing is the host's). The clock is set two
hours ahead (CLEAN_WORKTREES_NOW), so the quiet period holds. No branch is ever deleted.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'overlays/claude-code/files/scripts/close_worker.sh'

# Sessions live in a file, one name per line; every call is logged. Every target is exact.
TMUX = r'''#!/usr/bin/env python3
import os, sys
st = os.environ['CLOSE_STATE']
args = sys.argv[1:]
with open(os.path.join(st, 'tmux.log'), 'a') as log:
    log.write(repr(args) + '\n')
path = os.path.join(st, 'sessions')
sessions = open(path).read().split() if os.path.exists(path) else []
if args[0] == 'list-sessions':
    if not sessions:
        sys.exit('no server running on /tmp/tmux-stub/default')
    print('\n'.join(sessions))
    sys.exit(0)
target = args[args.index('-t') + 1]
if not target.startswith('='):
    sys.exit('inexact target ' + target)
name = target[1:]
if name not in sessions:
    sys.exit("can't find session: " + name)
if args[0] == 'kill-session':
    sessions.remove(name)
    with open(path, 'w') as f:
        f.write('\n'.join(sessions))
'''


class CloseWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / 'bin').mkdir()
        (self.tmp / 'bin/tmux').write_text(TMUX)
        (self.tmp / 'bin/tmux').chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.tmp / 'bin') + os.pathsep + os.environ['PATH'],
                        CLOSE_STATE=str(self.tmp), CLEAN_WORKTREES_NOW=str(time.time() + 7200),
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', LC_ALL='C',
                        GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid',
                        GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='gc.auto', GIT_CONFIG_VALUE_0='0',
                        GIT_CONFIG_KEY_1='maintenance.auto', GIT_CONFIG_VALUE_1='false')
        for name in ('KIT_NO_WORKTREE_CLEANUP', 'CLEAN_WORKTREES_PROC', 'CLEAN_WORKTREES_MOUNTINFO', 'GIT_DIR',
                     'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'TMUX'):
            self.env.pop(name, None)
        self.main = self.tmp / 'main'
        self.main.mkdir()
        self.git('init', '-q')
        self.git('checkout', '-q', '-b', 'main')
        (self.main / '.gitignore').write_text('/.claude/worktrees/\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'base')

    def git(self, *args, cwd=None):
        result = subprocess.run(['git', *args], cwd=cwd or self.main, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def worker(self, name, session=True):
        """A finished worker as spawn_worker.sh --worktree leaves it: a merged commit, a session."""
        path = self.main / '.claude/worktrees' / name
        self.git('worktree', 'add', '-q', str(path), '-b', 'worktree-' + name)
        (path / (name + '.txt')).write_text(name + '\n')
        self.git('add', name + '.txt', cwd=path)
        self.git('commit', '-q', '-m', 'work in ' + name, cwd=path)
        self.git('merge', '-q', '--no-edit', 'worktree-' + name)
        if session:
            with open(self.tmp / 'sessions', 'a') as f:
                f.write(name + '\n')
        return path

    def close(self, *args, code=0):
        result = subprocess.run(['sh', str(SCRIPT), *args], cwd=self.main, env=self.env, capture_output=True)
        out = (result.stdout + result.stderr).decode('utf-8', 'replace')
        self.assertEqual(result.returncode, code, out)
        return out

    def calls(self):
        log = self.tmp / 'tmux.log'
        return log.read_text().splitlines() if log.exists() else []

    def sessions(self):
        path = self.tmp / 'sessions'
        return path.read_text().split() if path.exists() else []

    def test_the_session_is_ended_and_the_worktree_removed_through_the_audit_the_branch_kept(self):
        path = self.worker('w1')
        tip = self.git('rev-parse', 'worktree-w1')
        out = self.close('w1')
        self.assertIn("['kill-session', '-t', '=w1']", self.calls())
        self.assertEqual(self.sessions(), [])
        self.assertIn('close_worker: w1: tmux session ended; the terminal tab attached to it closes by itself\n', out)
        self.assertFalse(path.exists(), out)
        self.assertIn('remove .claude/worktrees/w1', out)
        log = (self.main / '.git/kit-worktree-removals.log').read_text().splitlines()
        self.assertEqual(log[-1].split('\t')[2:], ['outcome', os.path.realpath(path), 'removed'])
        self.assertIn('close_worker: w1: worktree removed through the audit', out)
        self.assertEqual(self.git('rev-parse', 'worktree-w1'), tip)
        self.assertIn('close_worker: w1: branch worktree-w1 is kept, never deleted here; ', out)
        self.assertIn('`git branch --merged` lists the merged branches', out)
        self.assertNotIn('FAILED', out)

    def test_a_missing_session_or_worktree_is_reported_not_an_error(self):
        out = self.close('nobody')
        self.assertIn('close_worker: nobody: no tmux session named nobody; nothing to end\n', out)
        self.assertIn('close_worker: nobody: no worktree at .claude/worktrees/nobody; nothing to remove\n', out)
        self.assertIn('close_worker: nobody: no branch worktree-nobody; nothing to keep\n', out)
        self.assertFalse([c for c in self.calls() if 'kill-session' in c])

    def test_a_worktree_the_audit_cannot_prove_is_kept_and_the_exit_is_1_with_the_reason(self):
        path = self.worker('w1')
        (path / 'notes.txt').write_text('not committed, no copy on main\n')
        out = self.close('w1', code=1)
        self.assertEqual(self.sessions(), [])
        self.assertTrue((path / 'notes.txt').is_file(), out)
        self.assertIn('keep   .claude/worktrees/w1', out)
        self.assertIn('close_worker: w1: worktree kept: ', out)
        last = out.rstrip('\n').split('\n')[-1]
        self.assertTrue(last.startswith('close_worker: FAILED: w1: worktree kept: '), out)
        self.assertIn('notes.txt', last)
        self.git('rev-parse', '--verify', 'worktree-w1')

    def test_a_dry_run_changes_nothing(self):
        path = self.worker('w1')
        out = self.close('--dry-run', 'w1')
        self.assertFalse([c for c in self.calls() if 'kill-session' in c], out)
        self.assertEqual(self.sessions(), ['w1'])
        self.assertTrue(path.is_dir())
        self.assertFalse((self.main / '.git/kit-worktree-removals.log').exists())
        self.assertIn('close_worker: w1: dry run: would end tmux session w1', out)
        self.assertIn('clean_worktrees: dry run:', out)
        self.assertIn('close_worker: dry run: nothing was changed', out)

    def test_a_bad_name_is_refused_before_any_tmux_call(self):
        for bad in ('w1\n', 'w\x1b[31m', 'a b', 'a/b', '../w1', '', '--apply', 'w;id'):
            with self.subTest(name=bad):
                out = self.close(bad, code=1)
                self.assertEqual(self.calls(), [])
                self.assertIn('close_worker: refused the name', out)
                self.assertNotIn('\x1b', out)
                self.assertFalse(any(ch < ' ' for ch in out.replace('\n', '')), repr(out))
                self.assertEqual(out.count('\n'), 2, out)

    def test_the_second_name_still_runs_when_the_first_fails(self):
        kept, done = self.worker('kept'), self.worker('done')
        (kept / 'notes.txt').write_text('uncommitted\n')
        out = self.close('bad name', 'kept', 'done', code=1)
        self.assertTrue(kept.is_dir())
        self.assertFalse(done.exists(), out)
        self.assertEqual(self.sessions(), [])
        self.assertIn('close_worker: kept: worktree kept: ', out)
        self.assertIn('close_worker: done: worktree removed through the audit', out)
        self.assertTrue(out.rstrip('\n').split('\n')[-1].startswith("close_worker: FAILED: refused the name 'bad name'"), out)


if __name__ == '__main__':
    unittest.main()
