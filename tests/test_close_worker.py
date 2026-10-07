"""close_worker.sh ends a worker's tmux session and removes its worktree through the audit.

tmux is a stub on PATH that records every call, so no real session is touched; the worktree
is a real one in a throwaway repository, and its removal is clean_worktrees.sh's own, every
proof included (no --assume-idle: the process listing is the host's). The clock is set two
hours ahead (CLEAN_WORKTREES_NOW), so the quiet period holds. No branch is ever deleted.
"""
import os
from pathlib import Path
import signal
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'overlays/claude-code/files/scripts/close_worker.sh'
PROC = os.path.exists('/proc/self/cwd')

# Sessions live in a file, one name per line; every call is logged. Every target is exact.
TMUX = r'''#!/usr/bin/env python3
import os, sys
st = os.environ['CLOSE_STATE']
args = sys.argv[1:]
with open(os.path.join(st, 'tmux.log'), 'a') as log:
    log.write(repr(args) + '\n')
if os.environ.get('CLOSE_TMUX_ERROR'):  # a server tmux cannot reach: no answer either way
    sys.exit(os.environ['CLOSE_TMUX_ERROR'])
killed = os.path.join(st, 'killed')
if os.environ.get('CLOSE_ERROR_AFTER_KILL') and os.path.exists(killed):  # unreachable once killed
    sys.exit(os.environ['CLOSE_ERROR_AFTER_KILL'])
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
# CLOSE_LINGER=N: a killed session is still found by the next N has-session calls.
linger = os.path.join(st, 'linger-' + name)
if name not in sessions:
    left = int(open(linger).read()) if os.path.exists(linger) else 0
    if args[0] == 'has-session' and left:
        with open(linger, 'w') as f:
            f.write(str(left - 1))
        sys.exit(0)
    # CLOSE_ABSENT: tmux's wording for an absent session, %s the name.
    sys.exit(os.environ.get('CLOSE_ABSENT', "can't find session: %s").replace('%s', name))
if args[0] == 'kill-session':
    open(killed, 'w').close()
    sessions.remove(name)
    with open(path, 'w') as f:
        f.write('\n'.join(sessions))
    with open(linger, 'w') as f:
        f.write(os.environ.get('CLOSE_LINGER', '0'))
'''

# Native Windows: the session lister (KIT_PS) prints "<pid> <command line>" for each claude.exe,
# from the file `claude-procs` in the state folder; taskkill removes the pid it is given (its
# tree), and logs the call. CLOSE_PS_ERROR: a lister that cannot answer.
PS = r"""#!/usr/bin/env python3
import os, sys
if os.environ.get('CLOSE_PS_ERROR'):
    sys.exit(os.environ['CLOSE_PS_ERROR'])
path = os.path.join(os.environ['CLOSE_STATE'], 'claude-procs')
if os.path.exists(path):
    sys.stdout.write(open(path).read().replace('\n', '\r\n'))
"""
TASKKILL = r"""#!/usr/bin/env python3
import os, sys
st = os.environ['CLOSE_STATE']
with open(os.path.join(st, 'taskkill.log'), 'a') as log:
    log.write(repr(sys.argv[1:]) + '\n')
pid = sys.argv[sys.argv.index('/PID') + 1]
path = os.path.join(st, 'claude-procs')
if os.environ.get('CLOSE_TASKKILL_IGNORED'):
    sys.exit(0)
lines = open(path).read().splitlines() if os.path.exists(path) else []
open(path, 'w').write(''.join(line + '\n' for line in lines if line.split(' ')[0] != pid))
"""


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

    def close(self, *args, code=0, **extra):
        result = subprocess.run(['sh', str(SCRIPT), *args], cwd=self.main, env=dict(self.env, **extra),
                                capture_output=True)
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

    def windows(self, *procs):
        """Native Windows as close_worker.sh sees it: uname says MINGW, no tmux, PROCS (lines of
        "<pid> <command line>") the claude.exe processes running."""
        for name, body in (('uname', '#!/bin/sh\necho MINGW64_NT-10.0-26200\n'), ('ps-stub', PS),
                           ('taskkill', TASKKILL)):
            (self.tmp / 'bin' / name).write_text(body)
            (self.tmp / 'bin' / name).chmod(0o755)
        (self.tmp / 'claude-procs').write_text(''.join(line + '\n' for line in procs))
        return {'KIT_PS': str(self.tmp / 'bin/ps-stub')}

    def test_on_native_windows_the_claude_session_is_ended_and_the_worktree_removed(self):
        path = self.worker('w1', session=False)
        env = self.windows('100 C:\\npm\\claude.exe "Read \'b.md\' and follow it." -n w1 --model opus',
                           '200 C:\\npm\\claude.exe -n w10', '300 C:\\npm\\claude.exe --resume x')
        out = self.close('w1', **env)
        kills = (self.tmp / 'taskkill.log').read_text().splitlines()
        self.assertEqual(kills, ["['/PID', '100', '/T', '/F']"], out)
        self.assertIn('close_worker: w1: Claude Code session ended (process 100); its Windows Terminal tab '
                      'closes by itself\n', out)
        self.assertFalse(path.exists(), out)
        self.assertIn('close_worker: w1: worktree removed through the audit', out)
        # Only the audit lists tmux sessions (a tmux on PATH there would be one); no session is ended in it.
        self.assertEqual([c for c in self.calls() if 'list-sessions' not in c], [], 'tmux was used to end it')
        out = self.close('w1', **env)
        self.assertIn('close_worker: w1: no Claude Code session named w1 runs; nothing to end\n', out)

    def test_on_native_windows_a_session_that_survives_or_a_lister_that_fails_fails_the_close(self):
        path = self.worker('w1', session=False)
        env = self.windows('100 claude.exe -n w1')
        out = self.close('--dry-run', 'w1', **env)
        self.assertIn('close_worker: w1: dry run: would end the Claude Code session w1 (process 100', out)
        self.assertFalse((self.tmp / 'taskkill.log').exists(), out)
        out = self.close('w1', code=1, CLOSE_TASKKILL_IGNORED='1', **env)
        self.assertIn('close_worker: w1: the Claude Code session still runs after taskkill (process 100); its worktree is not touched', out)
        self.assertNotIn('clean_worktrees', out)
        self.assertTrue(path.is_dir(), out)
        out = self.close('w1', code=1, CLOSE_PS_ERROR='Get-CimInstance: access denied', **env)
        self.assertIn('close_worker: FAILED: w1: could not list the Claude Code sessions, so w1 may still run: '
                      'Get-CimInstance: access denied', out)

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

    def test_a_worktree_committed_a_moment_ago_is_removed_the_quiet_period_lifted(self):
        # The real clock: the worker's last commit is seconds old. The hook would keep it.
        path = self.worker('w1')
        now = {'CLEAN_WORKTREES_NOW': str(time.time())}
        out = self.close('--dry-run', 'w1', **now)
        self.assertIn('close_worker: w1: dry run: the removal would lift the quiet period for this worktree alone '
                      '(--no-quiet), every other proof stays', out)
        self.assertIn('--only=\'w1\' --no-quiet', out)
        out = self.close('w1', **now)
        self.assertIn('clean_worktrees: --no-quiet: the quiet period is not applied to .claude/worktrees/w1', out)
        self.assertFalse(path.exists(), out)
        self.git('rev-parse', '--verify', 'worktree-w1')

    def test_the_close_waits_for_a_lingering_session_and_its_processes_before_the_audit(self):
        path = self.worker('w1')
        # A process inside that exits by itself, after the session is gone, like the tool inside it.
        busy = subprocess.Popen(['sleep', '5'], cwd=path)
        self.addCleanup(busy.wait)
        self.addCleanup(lambda: busy.poll() is None and busy.send_signal(signal.SIGKILL))
        out = self.close('w1', CLOSE_LINGER='2', code=0 if PROC else 1)
        has = [c for c in self.calls() if c.startswith("['has-session'")]
        self.assertGreaterEqual(len(has), 4, out)  # before the kill, two lingering, one gone
        self.assertRegex(out, r'close_worker: w1: waited \d+ s for the tmux session to end')
        if PROC:  # /proc is polled: the audit runs once the process has exited
            self.assertIn('process %d inside its worktree to exit' % busy.pid, out)
            self.assertFalse(path.exists(), out)
        else:  # no /proc to poll (macOS): the audit's own listing sees the process and keeps it
            self.assertIn('in use: process', out)
            self.assertTrue(path.is_dir(), out)

    def test_a_tmux_that_cannot_answer_is_not_proof_of_absence(self):
        # Only "no such session or server" proves absence; a socket tmux cannot read may hold it.
        denied = 'error connecting to /tmp/tmux-1000/default (Permission denied)'
        path = self.worker('w1')
        for name in ('w1', 'nobody'):  # with a worktree, and without one: no audit then asks tmux again
            with self.subTest(name=name):
                out = self.close(name, code=1, CLOSE_TMUX_ERROR=denied)
                self.assertFalse([c for c in self.calls() if 'kill-session' in c], out)
                self.assertNotIn('no tmux session named', out)
                last = out.rstrip('\n').split('\n')[-1]
                self.assertEqual(last, 'close_worker: FAILED: %s: tmux could not say whether session %s exists, so it may '
                                 'still run: %s' % (name, name, denied), out)
        self.assertTrue(path.is_dir())

    def absent(self, wording):
        # Each wording tmux gives for an absent session or server is proof of absence: before
        # the kill (nothing to end) and after it (the wait ends at once).
        self.worker('w1', session=False)
        out = self.close('nobody', CLOSE_ABSENT=wording)
        self.assertIn('close_worker: nobody: no tmux session named nobody; nothing to end\n', out)
        with open(self.tmp / 'sessions', 'a') as f:
            f.write('w1\n')
        out = self.close('w1', CLOSE_ABSENT=wording)
        self.assertIn('close_worker: w1: tmux session ended', out)
        self.assertNotIn('waited', out)

    def test_absence_cant_find_session(self):
        self.absent("can't find session: %s")

    def test_absence_session_not_found(self):
        self.absent('session not found: %s')

    def test_absence_no_server_running(self):
        self.absent('no server running on /tmp/tmux-stub/default')

    def test_absence_no_sessions(self):
        self.absent('no sessions')

    def test_absence_no_socket_file(self):
        self.absent('error connecting to /tmp/tmux-stub/default (No such file or directory)')

    def test_a_tmux_that_stops_answering_after_the_kill_fails_the_close(self):
        # The kill succeeded, then no has-session could tell: the session was never seen to end.
        denied = 'error connecting to /tmp/tmux-1000/default (Permission denied)'
        with open(self.tmp / 'sessions', 'a') as f:
            f.write('w1\n')
        # The 15 one-second waits pass at once: a `sleep` that returns, first on PATH.
        (self.tmp / 'bin/sleep').write_text('#!/bin/sh\nexit 0\n')
        (self.tmp / 'bin/sleep').chmod(0o755)
        out = self.close('w1', code=1, CLOSE_ERROR_AFTER_KILL=denied)
        self.assertIn('close_worker: w1: no worktree at .claude/worktrees/w1; nothing to remove', out)
        self.assertEqual(out.rstrip('\n').split('\n')[-1], 'close_worker: FAILED: w1: could not establish that '
                         'the session ended: %s' % denied, out)

    def test_a_cleaner_that_exits_nonzero_fails_the_close_whatever_its_summary_says(self):
        # The cleaner exits 1 after a removal whose outcome line it could not write to its log.
        kit = self.tmp / 'kit'
        kit.mkdir()
        shutil.copy(SCRIPT, kit / 'close_worker.sh')
        (kit / 'clean_worktrees.sh').write_text('echo "clean_worktrees: removed 1, kept 0"\n'
                                                'echo "clean_worktrees: the outcome log could not be written"\nexit 1\n')
        result = subprocess.run(['sh', str(kit / 'close_worker.sh'), 'w1'], cwd=self.main, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout.rstrip('\n').split('\n')[-1], 'close_worker: FAILED: w1: clean_worktrees.sh '
                         'exited 1: clean_worktrees: the outcome log could not be written', result.stdout)

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
