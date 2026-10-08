"""close_worker.sh on native Windows ends no worker whose gate holds its lock.

The gate's lock there is check.lock opened for writing without write sharing (check.sh); the
close probes it by opening it for writing. Here a child holds it exactly so, the Claude Code
session is a stand-in (KIT_PS), and every close is a dry run: the real taskkill.exe wins
over a stub on PATH, and the check runs before the dry run is decided. Every case runs only on
native Windows; elsewhere each one prints a NOT RUN line and passes (tests/test_close_worker proves
the flock lock and index.lock).
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_close_worker import PS, SCRIPT  # noqa: E402

WINDOWS = os.name == 'nt'
HOLD = r'''import ctypes, sys, time
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.CreateFileW.restype = ctypes.c_void_p
k.CreateFileW.argtypes = (ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                          ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p)
# As check.sh takes it: read and write, shared for reading only.
h = k.CreateFileW(sys.argv[1], 0xC0000000, 1, None, 4, 0x200080, None)
assert h not in (None, ctypes.c_void_p(-1).value), ctypes.get_last_error()
print("held", flush=True)
time.sleep(60)
'''


class CloseWorkerOnWindows(unittest.TestCase):
    def test_a_worker_whose_gate_holds_its_lock_is_not_ended(self):
        if not WINDOWS:
            sys.stderr.write('\nNOT RUN: %s (native Windows only)\n' % self.id())
            return
        tmp = Path(tempfile.mkdtemp(prefix='kit-close-win-'))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / 'bin').mkdir()
        for name, body in (('ps-stub', PS),):
            (tmp / 'bin' / name).write_text(body)
        env = dict(os.environ, PATH=str(tmp / 'bin') + os.pathsep + os.environ['PATH'], CLOSE_STATE=str(tmp),
                   KIT_PS='python ' + str(tmp / 'bin/ps-stub').replace('\\', '/'), PYTHONUTF8='1',
                   CLEAN_WORKTREES_NOW=str(time.time() + 7200), GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_CONFIG_NOSYSTEM='1', GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                   GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid',
                   GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.autocrlf', GIT_CONFIG_VALUE_0='false')
        main = tmp / 'main'
        main.mkdir()

        def git(*args, cwd=main):
            result = subprocess.run(['git', *args], cwd=cwd, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

        git('init', '-q', '-b', 'main')
        (main / '.gitignore').write_text('/.claude/worktrees/\n')
        git('add', '-A')
        git('commit', '-q', '-m', 'base')
        path = main / '.claude/worktrees/w1'
        git('worktree', 'add', '-q', str(path), '-b', 'worktree-w1')
        (tmp / 'claude-procs').write_text('100 C:\\npm\\claude.exe "Read b.md and follow it." -n w1\n')
        lock = git('rev-parse', '--path-format=absolute', '--git-path', 'check.lock', cwd=path)
        holder = subprocess.Popen([sys.executable, '-c', HOLD, lock], stdout=subprocess.PIPE, text=True)
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline(), 'held\n')

        def close():
            # A dry run: a close the check did not stop must never reach the real taskkill.exe.
            result = subprocess.run(['sh', str(SCRIPT), '--dry-run', 'w1'], cwd=main, env=env, capture_output=True)
            return result.returncode, (result.stdout + result.stderr).decode('utf-8', 'replace')

        code, out = close()
        self.assertEqual(code, 1, out)
        self.assertIn('close_worker: w1: a gate (check.sh) holds ', out)
        self.assertTrue(path.exists(), out)
        holder.kill()
        holder.wait()
        # The gate over, nothing stops the close. A dry run says so and ends nothing: the real
        # taskkill.exe comes before any stub on Git for Windows' PATH.
        result = subprocess.run(['sh', str(SCRIPT), '--dry-run', 'w1'], cwd=main, env=env, capture_output=True)
        out = (result.stdout + result.stderr).decode('utf-8', 'replace')
        self.assertIn('close_worker: w1: dry run: would end the Claude Code session w1 (process 100', out)
        self.assertNotIn('holds', out)

if __name__ == '__main__':
    unittest.main()
