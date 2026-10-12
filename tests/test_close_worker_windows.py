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
NO_EXCLUSIVE_RENAME = '''import ctypes, errno, glob, hashlib, os, re, stat, tempfile
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
    def test_archive_link_cleanup_preserves_a_new_report_at_the_source(self):
        racing = '''import sys
linking = os.link
def link(source, target, *args, **kwargs):
    linking(source, target, *args, **kwargs)
    if target == sys.argv[2]:
        fresh = sys.argv[1] + ".new"
        with open(fresh, "w") as file:
            file.write("new report\\n")
        os.replace(fresh, sys.argv[1])
os.link = link
'''
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'iş archive'
            folder.mkdir()
            source, target = folder / 'RESULT-w.md', folder / 'w.result.md'
            source.write_text('old report\n')
            moved = subprocess.run([sys.executable, '-I', '-c',
                                    NO_EXCLUSIVE_RENAME % ('EINVAL', True) + racing + move_report(),
                                    str(source), str(target)], capture_output=True, timeout=10)
            self.assertEqual(moved.returncode, 0, moved.stderr)
            self.assertEqual(moved.stdout.decode('utf-8').strip(), str(target))
            self.assertEqual(target.read_text(), 'old report\n')
            self.assertTrue(source.exists(), 'archive cleanup deleted the newer report')
            self.assertEqual(source.read_text(), 'new report\n')

    def test_no_link_fallback_refuses_instead_of_overwriting_a_replaced_claim(self):
        racing = '''import sys
opening = os.open
def open_claim(path, flags, *args, **kwargs):
    fd = opening(path, flags, *args, **kwargs)
    if path == sys.argv[2] and flags & os.O_EXCL:
        os.close(fd)
        fresh = path + ".new"
        with open(fresh, "w") as file:
            file.write("newer destination\\n")
        os.replace(fresh, path)
        fd = opening(path, os.O_WRONLY)
    return fd
os.open = open_claim
'''
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'RESULT-w.md', Path(tmp) / 'w.result.md'
            source.write_text('the report\n')
            moved = subprocess.run([sys.executable, '-I', '-c',
                                    NO_EXCLUSIVE_RENAME % ('EINVAL', True) + NO_HARD_LINKS + racing + move_report(),
                                    str(source), str(target)], capture_output=True, timeout=10)
            self.assertEqual(moved.returncode, 1, moved.stderr)
            self.assertIn(b'no-overwrite guarantee unavailable', moved.stderr)
            self.assertEqual(source.read_text(), 'the report\n')
            if target.exists():
                self.assertEqual(target.read_text(), 'newer destination\n')

    def test_an_interrupted_move_leaves_its_archive_and_a_private_link_and_a_retry_claims_nothing(self):
        # Killed after the archive link, before the private name's unlink: the state this move
        # really leaves. Forward-slash paths, as Git Bash passes them on native Windows.
        interrupted = '''import sys
linking, unlinking = os.link, os.unlink
archive_linked = False
def link(source, target, *args, **kwargs):
    global archive_linked
    linking(source, target, *args, **kwargs)
    if target == sys.argv[2]:
        archive_linked = True
def unlink(*args, **kwargs):
    if archive_linked:
        os._exit(73)
    return unlinking(*args, **kwargs)
os.link, os.unlink = link, unlink
'''
        with tempfile.TemporaryDirectory() as tmp:
            source, first, second = (Path(tmp) / name for name in ('RESULT-w.md', 'w.result.md', 'w.result-2.md'))
            source.write_text('the report\n')
            forced = NO_EXCLUSIVE_RENAME % ('EINVAL', True)
            moved = subprocess.run([sys.executable, '-I', '-c', forced + interrupted + move_report(),
                                    source.as_posix(), first.as_posix()], capture_output=True, timeout=10)
            self.assertEqual(moved.returncode, 73, moved.stderr)
            self.assertFalse(source.exists(), 'the report was not consumed before its archive link')
            self.assertEqual(first.read_text(), 'the report\n')
            private = list(Path(tmp).glob('.report-move-*/*'))
            self.assertEqual([path.name for path in private], ['report'])
            self.assertTrue(os.path.samestat(os.stat(private[0]), os.stat(first)),
                            'the private leftover is not the published archive')
            # A retried close finds no RESULT-w.md to move; a move of the gone source claims no number.
            retry = subprocess.run([sys.executable, '-I', '-c', forced + move_report(),
                                    source.as_posix(), second.as_posix()], capture_output=True, timeout=10)
            self.assertEqual(retry.returncode, 1, retry.stderr)
            self.assertFalse(second.exists())
            self.assertEqual(first.read_text(), 'the report\n')

    def test_only_the_same_object_reuses_an_archive_and_another_runs_identical_report_gets_its_own_number(self):
        # Both spellings: Git Bash passes C:/ paths, which a pattern over the full path never matched.
        for spelling in (Path.as_posix, str):
            for forced in (NO_EXCLUSIVE_RENAME % ('EINVAL', True), ''):
                for same_object in (True, False):
                    with self.subTest(spelling=spelling.__name__, forced=bool(forced), same_object=same_object), \
                            tempfile.TemporaryDirectory() as tmp:
                        source, first, second = (Path(tmp) / name for name in ('RESULT-w.md', 'w.result.md', 'w.result-2.md'))
                        first.write_text('the report\n')
                        if same_object:
                            os.link(first, source)  # an older link+unlink stopped after its publication
                        else:
                            source.write_text('the report\n')  # another run, the same bytes
                        moved = subprocess.run([sys.executable, '-I', '-c', forced + move_report(),
                                                spelling(source), spelling(second)], capture_output=True, timeout=10)
                        self.assertEqual(moved.returncode, 0, moved.stderr)
                        self.assertFalse(source.exists())
                        self.assertEqual(first.read_text(), 'the report\n')
                        if same_object:
                            self.assertEqual(moved.stdout.decode('utf-8').strip(), spelling(first))
                            self.assertFalse(second.exists(), 'a retry claimed a second number for one report')
                        else:
                            self.assertEqual(moved.stdout.decode('utf-8').strip(), spelling(second))
                            self.assertEqual(second.read_text(), 'the report\n')
                            self.assertFalse(os.path.samestat(os.stat(first), os.stat(second)))

    def test_an_archive_that_vanishes_or_cannot_be_read_is_not_a_duplicate(self):
        failing = '''import errno, os
lstating = os.lstat
def lstat(path, *args, **kwargs):
    if os.path.basename(path) == "w.result.md":
        raise %s(errno.%s, "the candidate")
    return lstating(path, *args, **kwargs)
os.lstat = lstat
'''
        for error in (('FileNotFoundError', 'ENOENT'), ('PermissionError', 'EACCES')):
            for forced in (NO_EXCLUSIVE_RENAME % ('EINVAL', True), ''):
                with self.subTest(error=error[0], forced=bool(forced)), tempfile.TemporaryDirectory() as tmp:
                    source, first, second = (Path(tmp) / name for name in ('RESULT-w.md', 'w.result.md', 'w.result-2.md'))
                    first.write_text('the report\n')
                    source.write_text('the report\n')
                    moved = subprocess.run([sys.executable, '-I', '-c', failing % error + forced + move_report(),
                                            str(source), str(second)], capture_output=True, timeout=10)
                    self.assertEqual(moved.returncode, 0, moved.stderr)
                    self.assertEqual(second.read_text(), 'the report\n')
                    self.assertFalse(source.exists())

    def test_a_report_kept_in_its_private_folder_is_named_without_control_bytes(self):
        racing = '''import sys
linking = os.link
def link(source, target, *args, **kwargs):
    if target == sys.argv[2]:
        with open(sys.argv[1], "w") as file:
            file.write("a newer report\\n")
        raise FileExistsError(errno.EEXIST, "the archive name was taken")
    return linking(source, target, *args, **kwargs)
os.link = link
'''
        with tempfile.TemporaryDirectory() as tmp:
            # Windows refuses control characters in a name; elsewhere one names the folder.
            folder = Path(tmp) / ('iş' if WINDOWS else 'iş\x1b]0;t\x07')
            folder.mkdir()
            source, target = folder / 'RESULT-w.md', folder / 'w.result.md'
            source.write_text('the report\n')
            moved = subprocess.run([sys.executable, '-I', '-c', NO_EXCLUSIVE_RENAME % ('EINVAL', True) + racing
                                    + move_report(), str(source), str(target)], capture_output=True, timeout=10)
            self.assertEqual(moved.returncode, 1, moved.stderr)
            kept = list(folder.glob('.report-move-*/report'))
            self.assertEqual(len(kept), 1, moved.stderr)
            self.assertEqual(kept[0].read_text(), 'the report\n')
            self.assertEqual(source.read_text(), 'a newer report\n')
            self.assertFalse(target.exists())
            shown = os.fsencode(kept[0]).replace(b'\x1b', b'?').replace(b'\x07', b'?')
            self.assertIn(b'owned report preserved at ' + shown + b'\n', moved.stderr)
            self.assertNotIn(b'\x1b', moved.stderr)

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
                if label == 'EINVAL and no hard links':
                    self.assertEqual(moved.returncode, 1, moved.stderr)
                    self.assertIn(b'no-overwrite guarantee unavailable', moved.stderr)
                    self.assertFalse(target.exists())
                    self.assertEqual(source.read_text(), 'the report\n')
                    continue
                self.assertEqual(moved.returncode, 0, moved.stderr)
                self.assertEqual(target.read_text(), 'the report\n')
                self.assertFalse(source.exists())

    def test_a_source_that_cannot_be_consumed_keeps_its_report_without_an_archive(self):
        # A read-only source folder refuses the private rename before archive publication.
        stuck = ('import sys\nrenaming = os.rename\ndef rename(path, *args, **kwargs):\n'
                 '    if path == sys.argv[1]:\n        raise PermissionError(errno.EACCES, "read-only folder")\n'
                 '    return renaming(path, *args, **kwargs)\nos.rename = rename\n')
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
