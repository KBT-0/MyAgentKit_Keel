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
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_close_worker import HOLD_WINDOWS as HOLD, PS, SCRIPT  # noqa: E402

WINDOWS = os.name == 'nt'


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
    def close_fixture(self, interruption):
        """Real worktree and removal audit, with only the archive interruption injected."""
        tmp = Path(tempfile.mkdtemp(prefix='kit-close-recovery-')).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        main, kit, bin_dir = (tmp / name for name in ('main', 'scripts', 'bin'))
        for path in (main, kit, bin_dir):
            path.mkdir()
        python = shlex.quote(Path(sys.executable).as_posix())
        # Native mkdir avoids Git Bash's sandbox directory-creation denial in this fixture.
        mkdir = bin_dir / 'mkdir.py'
        mkdir.write_text('import pathlib, sys\nfor arg in sys.argv[1:]:\n'
                         '    if arg not in ("-p", "--"):\n'
                         '        pathlib.Path(arg).mkdir(parents=True, exist_ok=True)\n')
        stubs = {'mkdir': '#!/bin/sh\nexec ' + python + ' ' + shlex.quote(mkdir.as_posix()) + ' "$@"\n',
                 'ps-stub': '#!/bin/sh\nexit 0\n',
                 'tmux': '#!/bin/sh\necho "no server running" >&2\nexit 1\n'}
        for name, body in stubs.items():
            path = bin_dir / name
            path.write_text(body, newline='\n')
            path.chmod(0o755)
        env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + str(Path(sys.executable).parent)
                   + os.pathsep + os.environ['PATH'], KIT_PS=shlex.quote((bin_dir / 'ps-stub').as_posix()),
                   PYTHONUTF8='1', CLEAN_WORKTREES_NOW=str(time.time() + 7200),
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                   GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                   GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid',
                   GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.autocrlf', GIT_CONFIG_VALUE_0='false')
        for key in ('KIT_NO_WORKTREE_CLEANUP', 'CLEAN_WORKTREES_PROC', 'CLEAN_WORKTREES_MOUNTINFO',
                    'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'TMUX'):
            env.pop(key, None)
        def git(*args, cwd=main):
            result = subprocess.run(['git', *args], cwd=cwd, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        git('init', '-q', '-b', 'main')
        (main / '.gitignore').write_text('/.claude/worktrees/\n/.myagentkit/\n')
        git('add', '-A')
        git('commit', '-q', '-m', 'base')
        tree = main / '.claude/worktrees/taken'
        git('worktree', 'add', '-q', str(tree), '-b', 'worktree-taken')
        (tree / 'finished.txt').write_text('finished work\n')
        git('add', 'finished.txt', cwd=tree)
        git('commit', '-q', '-m', 'finished work', cwd=tree)
        git('merge', '-q', '--no-edit', 'worktree-taken')
        records = main / '.myagentkit/workers'
        records.mkdir(parents=True)
        (records / 'taken.session').write_text('the session\n')
        (tree / 'RESULT-taken.md').write_text('the report\n')
        script = kit / 'close_worker.sh'
        original = SCRIPT.read_text(encoding='utf-8')
        start = 'source, target = sys.argv[1:]\n'
        self.assertIn(start, original)
        script.write_text(original.replace(start, start + interruption, 1), encoding='utf-8', newline='\n')
        audited = tmp / 'audited'
        (kit / 'clean_worktrees.sh').write_text('#!/bin/sh\n: > ' + shlex.quote(audited.as_posix())
                                               + '\nexec sh ' + shlex.quote(SCRIPT.with_name('clean_worktrees.sh').as_posix())
                                               + ' "$@"\n', newline='\n')
        def close(*args):
            result = subprocess.run(['sh', str(script), *args, 'taken'], cwd=main, env=env,
                                    capture_output=True, text=True, encoding='utf-8', timeout=45)
            return result.returncode, result.stdout + result.stderr
        return tree, records, script, audited, close

    def test_two_closes_preserve_an_unpublished_report_until_recovery(self):
        interrupted = ('folder = os.path.join(os.path.dirname(target), ".report-move-killed")\n'
                       'os.mkdir(folder)\nos.rename(source, os.path.join(folder, "report"))\nos._exit(73)\n')
        tree, records, script, audited, close = self.close_fixture(interrupted)
        code, out = close()
        self.assertEqual(code, 1, out)
        self.assertFalse(audited.exists(), out)
        owned = records / '.report-move-killed/report'
        self.assertEqual(owned.read_text(), 'the report\n')
        self.assertTrue(tree.exists())
        self.assertTrue((records / 'taken.session').exists())
        script.write_bytes(SCRIPT.read_bytes())  # the next close has no injected failure
        code, out = close()
        self.assertEqual(code, 1, out)
        self.assertFalse(audited.exists(), 'the second close audited an unrecovered report: ' + out)
        self.assertTrue(tree.exists())
        self.assertEqual((records / 'taken.session').read_text(), 'the session\n')
        self.assertEqual(owned.read_text(), 'the report\n')
        marker = records / 'taken.report-move'
        self.assertTrue(marker.exists())
        self.assertIn('unfinished report move', out)
        self.assertIn('the session is not ended', out)
        # The recorded paths on lines of their own: a newline shown as ? glued them together.
        self.assertIn('close_worker: taken: recorded source: ', out)
        self.assertIn('close_worker: taken: recorded target: ', out)
        self.assertNotIn('?target', out)
        code, out = close('--dry-run')
        self.assertEqual(code, 1, out)
        self.assertFalse(audited.exists())
        self.assertTrue(marker.exists())
        # The printed recovery protocol: recover the report, then release its marker.
        owned.rename(tree / 'RESULT-taken.md')
        marker.unlink()
        code, out = close()
        self.assertEqual(code, 0, out)
        self.assertTrue(audited.exists(), out)
        self.assertFalse(tree.exists(), out)
        self.assertFalse((records / 'taken.session').exists())
        self.assertFalse(marker.exists())
        self.assertEqual((records / 'taken.result.md').read_text(), 'the report\n')

    # Restoration only: its target is the report's name in the worktree.
    RESTORING = 'if os.path.basename(target) == "RESULT-taken.md":\n'
    REFUSED = ('    def refused(*args, **kwargs):\n'
               '        raise PermissionError(errno.EACCES, "a sharing violation")\n'
               '    os.name, os.rename = "nt", refused\n')
    SURVIVOR_AUDIT = "#!/bin/sh\n: > %s\necho 'clean_worktrees: removed 1, kept 0'\n"

    def test_a_move_refused_before_consumption_leaves_no_marker_and_the_next_close_runs(self):
        # Owner decision: a refusal that moved nothing keeps the worktree but blocks no later close.
        tree, records, script, audited, close = self.close_fixture(
            'if os.path.basename(target) == "taken.result.md":\n' + self.REFUSED)
        code, out = close()
        self.assertEqual(code, 1, out)
        self.assertIn('nothing moved, the report stays in the worktree', out)
        self.assertFalse(audited.exists(), out)
        self.assertEqual((tree / 'RESULT-taken.md').read_text(), 'the report\n')
        self.assertFalse((records / 'taken.report-move').exists(), out)
        self.assertEqual(list(records.glob('.report-move-*')), [])
        self.assertEqual((records / 'taken.session').read_text(), 'the session\n')
        script.write_bytes(SCRIPT.read_bytes())
        code, out = close()
        self.assertEqual(code, 0, out)
        self.assertTrue(audited.exists(), out)
        self.assertFalse(tree.exists(), out)
        self.assertEqual((records / 'taken.result.md').read_text(), 'the report\n')

    def test_an_interrupted_restoration_keeps_its_marker_and_the_session_record(self):
        killed = ('    folder = os.path.join(os.path.dirname(target), ".report-move-killed")\n'
                  '    os.mkdir(folder)\n    os.rename(source, os.path.join(folder, "report"))\n    os._exit(73)\n')
        tree, records, script, audited, close = self.close_fixture(self.RESTORING + killed)
        (tree / 'draft.txt').write_text('uncommitted work keeps the worktree\n')
        code, out = close()
        self.assertEqual(code, 1, out)
        self.assertTrue(audited.exists(), out)
        self.assertIn('could not move its result back', out)
        self.assertEqual((tree / '.report-move-killed/report').read_text(), 'the report\n')
        self.assertTrue((records / 'taken.report-move').exists(), 'the restoration ran without its marker')
        self.assertEqual((records / 'taken.session').read_text(), 'the session\n')
        script.write_bytes(SCRIPT.read_bytes())
        audited.unlink()
        code, out = close()
        self.assertEqual(code, 1, out)
        self.assertIn('unfinished report move', out)
        self.assertFalse(audited.exists(), out)
        self.assertEqual((records / 'taken.session').read_text(), 'the session\n')

    def test_a_restoration_refused_before_consumption_keeps_the_session_record(self):
        # The audit said removed yet the folder stayed: only the failed restoration keeps the
        # session record, as the refusal cleared its marker.
        tree, records, script, audited, close = self.close_fixture(self.RESTORING + self.REFUSED)
        (script.parent / 'clean_worktrees.sh').write_text(self.SURVIVOR_AUDIT % shlex.quote(audited.as_posix()),
                                                         newline='\n')
        code, out = close()
        self.assertEqual(code, 1, out)
        self.assertIn('could not move its result back', out)
        self.assertEqual((records / 'taken.result.md').read_text(), 'the report\n')
        self.assertFalse((records / 'taken.report-move').exists(), out)
        self.assertEqual((records / 'taken.session').read_text(), 'the session\n')

    def test_a_marker_left_after_a_publication_keeps_the_session_record_or_is_named_stale(self):
        real_rm = '[ -x /usr/bin/rm ] && exec /usr/bin/rm "$@"; exec /bin/rm "$@"\n'
        for status in (0, 1):
            with self.subTest(rm_status=status):
                tree, records, script, audited, close = self.close_fixture('')
                stub = script.parent.parent / 'bin/rm'
                stub.write_text('#!/bin/sh\ncase "$*" in *report-move*) exit %d ;; esac\n' % status + real_rm,
                                newline='\n')
                stub.chmod(0o755)
                code, out = close()
                self.assertEqual((records / 'taken.result.md').read_text(), 'the report\n')
                self.assertTrue((records / 'taken.report-move').exists())
                self.assertEqual((records / 'taken.session').read_text(), 'the session\n',
                                 'session records went while a report-move marker remained: ' + out)
                if status:
                    # Published: the recovery names the archive and the stale marker only.
                    self.assertEqual(code, 1, out)
                    self.assertIn('.myagentkit/workers/taken.result.md, but ', out)
                    self.assertIn('only that marker is stale', out)
                    self.assertNotIn('publication of RESULT-taken.md failed', out)
                    self.assertFalse(audited.exists(), out)

    def test_a_records_folder_that_cannot_be_made_skips_the_audit(self):
        tree, records, script, audited, close = self.close_fixture('')
        (script.parent.parent / 'bin/mkdir').write_text('#!/bin/sh\nexit 1\n', newline='\n')
        code, out = close()
        self.assertEqual(code, 1, out)
        self.assertFalse(audited.exists(), 'the audit ran though the report could not be archived: ' + out)
        self.assertEqual((tree / 'RESULT-taken.md').read_text(), 'the report\n')
        self.assertEqual((records / 'taken.session').read_text(), 'the session\n')

    def test_an_empty_directory_successor_does_not_prove_report_restoration(self):
        interrupted = ('folder = os.path.join(os.path.dirname(target), ".report-move-failed")\n'
                       'os.mkdir(folder)\nos.rename(source, os.path.join(folder, "report"))\n'
                       'os.mkdir(source)\nos._exit(1)\n')
        tree, records, _, audited, close = self.close_fixture(interrupted)
        code, out = close()
        self.assertEqual(code, 1, out)
        self.assertFalse(audited.exists(), 'the audit ran despite failed report publication: ' + out)
        self.assertTrue((tree / 'RESULT-taken.md').is_dir())
        self.assertEqual((records / 'taken.session').read_text(), 'the session\n')
        self.assertEqual((records / '.report-move-failed/report').read_text(), 'the report\n')

    def test_denied_archive_listing_still_allows_exclusive_publication(self):
        denied = '''import errno, os
def listdir(*args, **kwargs):
    raise PermissionError(errno.EACCES, "directory enumeration denied")
os.listdir = listdir
'''
        for forced in ('', NO_EXCLUSIVE_RENAME % ('EINVAL', True)):
            with self.subTest(fallback=bool(forced)), tempfile.TemporaryDirectory() as tmp:
                source, first, target = (Path(tmp) / name for name in ('RESULT-w.md', 'w.result.md', 'w.result-2.md'))
                first.write_text('earlier report\n')
                source.write_text('the report\n')
                command = [sys.executable, '-I', '-c', forced + denied + move_report(), str(source), str(target)]
                moved = subprocess.run(command, capture_output=True, timeout=10)
                self.assertEqual(moved.returncode, 0, moved.stderr)
                self.assertEqual(target.read_text(), 'the report\n')
                self.assertEqual(first.read_text(), 'earlier report\n')
                self.assertFalse(source.exists())
                source.write_text('another report\n')
                collision = subprocess.run(command, capture_output=True, timeout=10)
                self.assertEqual(collision.returncode, 2, collision.stderr)
                self.assertEqual(target.read_text(), 'the report\n')
                self.assertEqual(source.read_text(), 'another report\n')

    def test_an_archive_collision_with_failed_restoration_is_not_retryable(self):
        refused = '''import sys
linking = os.link
def link(source, target, *args, **kwargs):
    if target == sys.argv[2]:
        raise FileExistsError(errno.EEXIST, "archive collision")
    if target == sys.argv[1]:
        raise PermissionError(errno.EACCES, "restoration denied")
    return linking(source, target, *args, **kwargs)
os.link = link
'''
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / 'RESULT-w.md', Path(tmp) / 'w.result.md'
            source.write_text('the report\n')
            moved = subprocess.run([sys.executable, '-I', '-c', NO_EXCLUSIVE_RENAME % ('EINVAL', True)
                                    + refused + move_report(), str(source), str(target)],
                                   capture_output=True, timeout=10)
            self.assertEqual(moved.returncode, 1, moved.stderr)
            self.assertFalse(source.exists())
            self.assertFalse(target.exists())
            kept = list(Path(tmp).glob('.report-move-*/report'))
            self.assertEqual(len(kept), 1)
            self.assertEqual(kept[0].read_text(), 'the report\n')

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
            self.assertEqual(moved.returncode, 3, moved.stderr)
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
            self.assertEqual(retry.returncode, 3, retry.stderr)
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
                    self.assertEqual(moved.returncode, 3, moved.stderr)
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
            self.assertEqual(moved.returncode, 3, moved.stderr)
            self.assertRegex(moved.stderr, rb'^\[Errno \d+\] read-only folder')
            self.assertEqual(source.read_text(), 'the report\n')
            self.assertFalse(target.exists(), 'the report was left under both names')

    def test_a_failed_archive_move_prints_only_its_errno_and_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            # An escape sequence in the path: Windows refuses such a name, POSIX finds none.
            source = Path(tmp) / 'gone\x1b]0;title\x07.md'
            moved = subprocess.run([sys.executable, '-I', '-c', move_report(), str(source),
                                    str(Path(tmp) / 'w.result.md')], capture_output=True, timeout=10)
            self.assertEqual(moved.returncode, 3, moved.stderr)
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

    def test_an_empty_question_record_keeps_the_session_record(self):
        # An interrupted launch wrote NAME.session, then left NAME.question empty: the close
        # must not read that as "no decision" and delete the only way to answer it.
        if not WINDOWS:
            sys.stderr.write('\nNOT RUN: %s (native Windows only)\n' % self.id())
            return
        tmp = Path(tempfile.mkdtemp(prefix='kit-close-win-'))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / 'bin').mkdir()
        (tmp / 'bin' / 'ps-stub').write_text(PS)
        env = dict(os.environ, CLOSE_STATE=str(tmp), PYTHONUTF8='1', GIT_CONFIG_GLOBAL=os.devnull,
                   KIT_PS='python ' + str(tmp / 'bin/ps-stub').replace('\\', '/'), GIT_CONFIG_NOSYSTEM='1')
        main = tmp / 'main'
        main.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=main, env=env, check=True)
        records = main / '.myagentkit/workers'
        records.mkdir(parents=True)
        (records / 'w2.session').write_text('sess-0\n')
        (records / 'w2.question').write_text('')
        (main / 'QUESTION-w2.md').write_text('A or B?\n')
        result = subprocess.run(['sh', str(SCRIPT), 'w2'], cwd=main, env=env, capture_output=True)
        out = (result.stdout + result.stderr).decode('utf-8', 'replace')
        self.assertEqual(result.returncode, 1, out)
        self.assertTrue((records / 'w2.session').exists(), out)


if __name__ == '__main__':
    unittest.main()
