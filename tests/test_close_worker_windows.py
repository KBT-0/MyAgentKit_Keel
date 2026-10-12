"""close_worker.sh on native Windows ends no worker whose gate holds its lock.

The gate's lock there is check.lock opened for writing without write sharing (check.sh); the
close probes it by opening it for writing. Here a child holds it exactly so, the Claude Code
session is a stand-in (KIT_PS), and every close is a dry run: the real taskkill.exe wins
over a stub on PATH, and the check runs before the dry run is decided. That case runs only on
native Windows; elsewhere it prints a NOT RUN line and passes (tests/test_close_worker proves
the flock lock and index.lock). The archive cases run the script's own code on every host.
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


# Forces the archive move's POSIX path on every host, its exclusive rename failing as one the
# filesystem (EINVAL), the kernel (ENOSYS) or the libc (no symbol) lacks.
NO_EXCLUSIVE_RENAME = '''import ctypes, errno, os
def primitive(*args):
    ctypes.set_errno(errno.%s)
    return -1
class Library:
    def __init__(self, *args, **kwargs):
        if %r:
            self.renameat2 = self.renamex_np = primitive
ctypes.CDLL = Library
os.name = "posix"
'''
NO_HARD_LINKS = '''def link(*args, **kwargs):
    raise OSError(errno.EPERM, "no hard links here")
os.link = link
'''


def move_report():
    """The archive move's Python code, exactly as close_worker.sh runs it."""
    script = SCRIPT.read_text(encoding='utf-8')
    return script.split("move_report() {\n  $kit_python -I -c '", 1)[1].split("' \"$1\" \"$2\"\n}", 1)[0]


class CloseWorkerOnWindows(unittest.TestCase):
    def test_the_archive_move_never_overwrites_where_no_exclusive_rename_exists(self):
        cases = {'EINVAL': NO_EXCLUSIVE_RENAME % ('EINVAL', True),
                 'ENOSYS': NO_EXCLUSIVE_RENAME % ('ENOSYS', True),
                 'no such symbol': NO_EXCLUSIVE_RENAME % ('EINVAL', False),
                 'EINVAL and no hard links': NO_EXCLUSIVE_RENAME % ('EINVAL', True) + NO_HARD_LINKS}
        for label, forced in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                source, target = Path(tmp) / 'RESULT-w.md', Path(tmp) / 'w.result.md'
                source.write_text('the report\n')
                target.write_text('an earlier report\n')
                move = [sys.executable, '-I', '-c', forced + move_report(), str(source), str(target)]
                moved = subprocess.run(move, capture_output=True, timeout=10)
                self.assertEqual(moved.returncode, 2, moved.stderr)
                self.assertEqual(target.read_text(), 'an earlier report\n')
                self.assertEqual(source.read_text(), 'the report\n')
                target.unlink()
                moved = subprocess.run(move, capture_output=True, timeout=10)
                self.assertEqual(moved.returncode, 0, moved.stderr)
                self.assertEqual(target.read_text(), 'the report\n')
                self.assertFalse(source.exists())

    def test_a_linked_claim_whose_source_cannot_go_is_taken_back(self):
        # The hard-link fallback is two steps: a source that cannot be unlinked (a read-only
        # folder) leaves the report under one name, never under both for a retry to archive twice.
        stuck = ('import sys\nunlinking = os.unlink\ndef unlink(path, *args, **kwargs):\n'
                 '    if path == sys.argv[1]:\n        raise PermissionError(errno.EACCES, "read-only folder")\n'
                 '    unlinking(path, *args, **kwargs)\nos.unlink = unlink\n')
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'RESULT-w.md', Path(tmp) / 'w.result.md'
            source.write_text('the report\n')
            move = [sys.executable, '-I', '-c', NO_EXCLUSIVE_RENAME % ('EINVAL', True) + stuck + move_report(),
                    str(source), str(target)]
            moved = subprocess.run(move, capture_output=True, timeout=10)
            self.assertEqual(moved.returncode, 1, moved.stderr)
            self.assertRegex(moved.stderr, rb'^\[Errno \d+\] read-only folder')
            self.assertEqual(source.read_text(), 'the report\n')
            self.assertFalse(target.exists(), 'the report was left under both names')

    def test_a_failed_archive_move_prints_only_its_errno_and_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            # An escape sequence in the path: Windows refuses such a name, POSIX finds none.
            source = Path(tmp) / 'gone\x1b]0;title\x07.md'
            moved = subprocess.run([sys.executable, '-I', '-c', move_report(), str(source),
                                    str(Path(tmp) / 'w.result.md')], capture_output=True, timeout=10)
            self.assertEqual(moved.returncode, 1, moved.stderr)
            self.assertNotIn(b'\x1b', moved.stderr)
            self.assertNotIn(b'gone', moved.stderr)
            self.assertRegex(moved.stderr, rb'^\[Errno \d+\] ')

    def test_archive_suffix_overflow_names_are_not_numbers(self):
        # Run the actual archive-selection block on every host. No session, audit or process
        # stub is needed to exercise the shell arithmetic that runs on native Windows too.
        script = SCRIPT.read_text(encoding='utf-8')
        selection = script.split('    n=0; [ ! -e "$record.result.md" ] || n=1\n', 1)[1]
        selection = 'n=0; [ ! -e "$record.result.md" ] || n=1\n' + selection.split('    if [ -n "$dry" ];', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / 'overflow'
            for suffix in ('9223372036854775807', '9999999999', '12x', '-7', '01'):
                Path(str(record) + '.result-' + suffix + '.md').write_text('An earlier report.\n')
            command = ['sh', '-c', 'record=$1\n' + selection + '\nprintf "%s\\n" "$saved"\n',
                       'sh', record.as_posix()]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), record.as_posix() + '.result.md')
            Path(str(record) + '.result-999999999.md').write_text('The highest valid suffix.\n')
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), record.as_posix() + '.result-1000000000.md')

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
