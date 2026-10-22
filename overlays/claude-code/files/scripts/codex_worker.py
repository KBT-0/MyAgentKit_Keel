#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Close a worker after a published decision or completed result; --wait notifies the lead
without a commit, also when the worker stopped without publishing (its exit record) or its
supervisor was killed (its lock on the .live record dropped). --publish TEMPORARY_FILE
DESTINATION is the worker's own last step: the rename, retried while Windows refuses it.
QUESTION [RESULT] --bg ID supervises a `claude --bg` session and ends it with `claude stop ID`;
--detach LOG ARGUMENTS... runs this script with ARGUMENTS outside the caller's session or job."""
import errno
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import signal
import sys
import tempfile
import time

READY = '<!-- codex-worker: ready -->'
REFUSALS = 50  # consecutive Windows refusals of one path a poller waits through, about five seconds
REFUSED = {}  # path: its consecutive refusals
SETTLED = 60  # seconds a changed file sits unchanged before --wait calls it NOT A RESULT
# A bound, not a measurement: the supervisor writes its .live record before it launches the worker,
# so a run with neither that record nor an exit record this long after its launch never started.
# Wide enough for a loaded Windows host, where the tab's shell and python can take minutes to start.
START = 300
STALE_LOCK = 600  # seconds an index.lock sits unchanged, with no gate running, before it counts as left behind
CHECKED = {}  # path: (id, size, mtime_ns) last read by not_a_result, and its verdict


def tolerated(path, error):
    """On Windows an open that meets a rename over the file is refused, and the next poll reads
    it. A refusal that lasts, a denied ACL or a lock held on, is an error, not an endless wait."""
    REFUSED[path] = REFUSED.get(path, 0) + 1
    if os.name != 'nt' or REFUSED[path] > REFUSALS:
        raise error


def renamed(source, target):
    """os.replace, retried for about two seconds on Windows: a rename over a file another process
    holds open, if only to stat it, is refused there, delete sharing included."""
    for attempt in range(100):
        try:
            return os.replace(source, target)
        except PermissionError:
            if os.name != 'nt' or attempt == 99:
                raise
            time.sleep(.02)


def decoded(data):
    """A result's or question's bytes as text, never a decode error (#169): UTF-16 by its BOM
    (PowerShell 5.1's Out-File or >), else UTF-8 with a BOM dropped (Set-Content -Encoding UTF8);
    bytes in another code page (cp1254 Set-Content) read as U+FFFD instead of ending the wait.
    Line ends become \\n as a text-mode read made them: a CRLF result keeps its content hash."""
    if data[:2] in (b'\xff\xfe', b'\xfe\xff'):
        text = data.decode('utf-16', 'replace')
    else:
        text = data.decode('utf-8-sig', 'replace')
    return text.replace('\r\n', '\n').replace('\r', '\n')


def published(path):
    """The text of a decision published with its end marker, '' without one, None when refused."""
    try:
        text = decoded(path.read_bytes()).strip()
    except FileNotFoundError:
        REFUSED.pop(path, None)
        return ''
    except PermissionError as error:
        tolerated(path, error)
        return None  # opened in the middle of a rename over it; the next poll reads it
    REFUSED.pop(path, None)
    return text if text.endswith(READY) else ''


def question_id(path):
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return info.st_ino, info.st_mtime_ns, info.st_size


def baseline(path, since):
    """The file id of a result published before this run, the launch's STALE: an in-place edit
    of it never counts as a new publication, only a rename over it (the atomic protocol) does.
    A follow-up wait's STALE is the reported result's content hash instead (result_kind)."""
    try:
        info = path.stat() if path else None
    except FileNotFoundError:
        return None
    # ponytail: a filesystem with no file ids (st_ino 0) falls back to the mtime check alone.
    return info.st_ino or None if info and info.st_mtime < since and published(path) else None


SEEN = {}  # result path: the id, size and time of its last read with that SINCE and STALE, and its kind


def result_kind(path, since=0, stale=None):
    """The kind of a result published in this run and its publication id; '' when absent.
    A launch's file id (an int STALE) suppresses that earlier result, edited in place too. A
    reported result's id (a str STALE) is the hash of its contents: other contents count as a
    new publication, by rename or by in-place rewrite, and a byte-identical one does not."""
    if path is None:
        return '', None
    try:
        info = path.stat()
        # Windows refuses a rename over a file held open, delete sharing included: a result
        # this poller has read is not opened again until its id, size or time changes.
        # ponytail: a same-size in-place edit within one timestamp tick is read at its next change.
        seen = SEEN.get(path)
        if seen and seen[0] == (info.st_ino, info.st_size, info.st_mtime_ns, since, stale):
            REFUSED.pop(path, None)
            return seen[1]
        with path.open('rb') as file:
            info = os.fstat(file.fileno())
            text = decoded(file.read()).strip()
    except FileNotFoundError:
        REFUSED.pop(path, None)
        return '', None
    except PermissionError as error:
        tolerated(path, error)
        return '', None  # opened in the middle of a rename over it; the next poll reads it
    REFUSED.pop(path, None)
    SEEN[path] = (info.st_ino, info.st_size, info.st_mtime_ns, since, stale), parse(text, info, since, stale)
    return SEEN[path][1]


def not_a_result(path, since, stale):
    """A file changed in this run, unchanged for SETTLED seconds, that is not in the result
    format: a free-form report. Without this the wait read it as unpublished forever. The age
    and the bytes judged come from one open file, and a file renamed over it while it was read
    is no verdict: a stat() and a later read paired a settled file's age with a fresh draft."""
    def settled(info):
        return since <= info.st_mtime <= time.time() - SETTLED and info.st_ino != stale
    identity = lambda info: (info.st_ino, info.st_size, info.st_mtime_ns)
    try:
        info = path.stat()
        if not settled(info):
            return False
        key = identity(info)
        if CHECKED.get(path, (None,))[0] != key:  # read once per change: Windows refuses a rename over an open file
            with path.open('rb') as file:
                info = os.fstat(file.fileno())
                text = decoded(file.read()).strip()
            key = identity(info)
            if not settled(info) or identity(path.stat()) != key:
                return False  # changed while read: the next poll reads it
            CHECKED[path] = key, not parse(text, info, 0, None)[0]
        return CHECKED[path][1]
    except OSError:
        return False


def parse(text, info, since, stale):
    if info.st_mtime < since or info.st_ino == stale or not text.endswith(READY):
        return '', None
    published_id = 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()
    if published_id == stale:
        return '', None
    lines = text.splitlines()
    if (len(lines) < 4 or not lines[1].startswith('Task: ')
            or not lines[2].startswith('Attempt: ') or not lines[2][9:].isdigit()
            or not lines[3].startswith('Remaining: ')):
        return '', None
    return {'Kind: completed': 'DONE', 'Kind: blocked': 'BLOCKED', 'Kind: handoff': 'HANDOFF',
            'Kind: progress': 'PROGRESS'}.get(lines[0], ''), published_id


def pin(path, stale):
    """Hold the stale result open for this process's life on POSIX: ext4 reuses a freed inode
    number at once, and a new result given it would read as the stale one. A held inode is never
    freed. NTFS ids carry a sequence number, and an open handle there blocks the publishing rename."""
    if os.name == 'nt' or not stale or path is None or isinstance(stale, str):
        return None
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return None
    if os.fstat(fd).st_ino != stale:
        os.close(fd)
        return None
    return fd


def lock(fd):
    """Lock FD's first byte without waiting; OSError while another process holds it. The
    operating system drops the lock however its holder ends, a closed tab or a hard kill too."""
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def shared_open(path, flags=os.O_RDONLY):
    """Open a protocol file with delete sharing on Windows so a held identity can be renamed."""
    if os.name != 'nt':
        return os.open(path, flags)
    import ctypes
    import msvcrt
    from ctypes import wintypes as w
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    api.CreateFileW.restype = w.HANDLE
    api.CloseHandle.argtypes = [w.HANDLE]
    access = 0x80000000 | (0x40000000 if flags & os.O_RDWR else 0)
    handle = api.CreateFileW(str(path), access, 7, None, 3, 0x80, None)  # share read/write/delete, OPEN_EXISTING
    if handle in (None, ctypes.c_void_p(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return msvcrt.open_osfhandle(handle, flags | os.O_BINARY)
    except BaseException:
        api.CloseHandle(handle)
        raise


def start_live(record):
    """Publish an already identified and locked supervisor record; delayed startup stays private."""
    live = Path(record).with_suffix('.live')
    live.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + live.name + '-', dir=live.parent)
    held = None
    try:
        with os.fdopen(fd, 'wb') as file:
            file.write(b'%d\n' % os.getpid())
        held = shared_open(Path(name), os.O_RDWR)
        for attempt in range(100):
            try:
                lock(held)
                break
            except OSError:
                if attempt == 99:
                    raise
                time.sleep(.01)
        renamed(name, live)  # a waiter's probe of the previous run's record holds it for a moment
        return held  # the process holds this descriptor for its whole life
    except BaseException:
        if held is not None:
            os.close(held)
        raise
    finally:
        Path(name).unlink(missing_ok=True)


def gone(live, since):
    """Whether the supervisor of this run, which locked LIVE when it started, has ended."""
    try:
        fd = shared_open(live)
    except FileNotFoundError:
        return False
    try:
        if os.fstat(fd).st_mtime < since:
            return False  # not started yet, or a previous run's
        lock(fd)
        ready = os.read(fd, 64)
        # An empty or malformed record is damaged, not evidence that its supervisor died.
        return (os.fstat(fd).st_mtime >= since and ready.endswith(b'\n')
                and ready[:-1].isdigit())  # startup publishes the PID and its held lock together
    except OSError:
        return False
    finally:
        os.close(fd)


def windows_job(child):
    """Own this child tree with a kill-on-close job; no global process listing or taskkill."""
    import ctypes
    from ctypes import wintypes as w
    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                    ('flags', w.DWORD), ('min_working', ctypes.c_size_t), ('max_working', ctypes.c_size_t),
                    ('active_limit', w.DWORD), ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
    class Info(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                    ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                    ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    api.CreateJobObjectW.restype = w.HANDLE
    api.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    api.CloseHandle.argtypes = [w.HANDLE]
    handle = api.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    info = Info()
    info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if (not api.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info))
            or (child.poll() is None and not api.AssignProcessToJobObject(handle, int(child._handle)))):
        error = ctypes.WinError(ctypes.get_last_error())
        api.CloseHandle(handle)
        child.kill()
        raise error
    def close(force=False):
        nonlocal handle
        if handle:
            api.CloseHandle(handle)
            handle = None
    return close


def resume_windows(child):
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('ntdll', use_last_error=True)
    api.NtResumeProcess.argtypes = [wintypes.HANDLE]
    if api.NtResumeProcess(int(child._handle)) != 0:
        raise OSError('cannot resume worker after job assignment')


def child_env():
    """The supervisor's own settings never reach the worker: a codex_worker.py the worker starts
    (its test suite, a sub-worker) read KIT_WORKER_EXIT and wrote this run's exit record, and the
    lead's --wait --exit returned while the worker worked on (followups.md, 2026-10-16 20:51)."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith('KIT_WORKER_')}


def windows_child(command):
    child = subprocess.Popen(command, creationflags=0x4, env=child_env())  # CREATE_SUSPENDED
    close = None
    try:
        close = windows_job(child)
        resume_windows(child)
        return child, close
    except BaseException:
        stop(child, close)
        raise


def stop(child, close_tree=None):
    if close_tree:
        close_tree()
    try:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if close_tree:
                    close_tree(True)
                child.kill()
                child.wait()
    finally:
        # A leader that exits on SIGTERM can still leave descendants ignoring it.
        if close_tree:
            close_tree(True)


def posix_tree(pid, force=False):
    try:
        os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
    # macOS answers EPERM for a group whose members are all zombies (nothing left to stop), as
    # agent_process.stop_group reads it: a supervisor that stopped its worker then exited 1.
    except (ProcessLookupError, PermissionError):
        pass


BG_POLL = 5  # seconds between two `claude agents` reads of a background session: each starts the CLI


def claude(*args):
    """The claude CLI, quietly: from a detached supervisor on Windows it opens no console window."""
    path = shutil.which('claude')
    if not path:
        raise OSError('claude is not on PATH')
    return subprocess.run([path, *args], capture_output=True, encoding='utf-8', errors='replace',
                          stdin=subprocess.DEVNULL, creationflags=0x08000000 if os.name == 'nt' else 0)


def agents_row(session):
    """The row of background session SESSION (its short id), None when absent, False when the
    list cannot be read: no decision is taken on a failed read."""
    try:
        listed = claude('agents', '--json', '--all')  # without --all, done and stopped rows are left out
        rows = json.loads(listed.stdout) if listed.returncode == 0 else None
    except (OSError, ValueError):
        return False
    if not isinstance(rows, list):
        return False
    return next((row for row in rows if isinstance(row, dict) and row.get('id') == session), None)


class Background:
    """A `claude --bg` session in place of a child process: watch() and stop() take either.
    Claude Code's supervisor owns its process, so it ends with `claude stop ID`: by id, since
    names repeat, and never `claude daemon stop`, which ends every background session on the host
    (docs/research/worker-orchestration-spike.md, 6 and T4). It has ended once its row is gone, or
    shows no process in a state other than working or blocked, after its process was seen once (a
    resumed session's row reads done until the wake) or START seconds after the supervisor began."""
    def __init__(self, session):
        self.session, self.returncode, self.seen = session, None, False
        self.began, self.checked = time.monotonic(), None

    def poll(self):
        now = time.monotonic()
        if self.returncode is None and (self.checked is None or now - self.checked >= BG_POLL):
            self.checked = now
            row = agents_row(self.session)
            if row is not False:
                self.seen = self.seen or bool(row and row.get('pid'))
                live = row and (row.get('pid') or row.get('state') in ('working', 'blocked'))
                if not live and (self.seen or now - self.began > START):
                    self.returncode = 1 if not row or row.get('state') == 'failed' else 0
        return self.returncode

    def terminate(self):
        stopped = claude('stop', self.session)
        if stopped.returncode:
            print('codex_worker: claude stop %s failed (%s); close it with close_worker.sh'
                  % (self.session, (stopped.stderr or stopped.stdout).strip()), flush=True)
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    kill = terminate


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == '--wait':
        options = dict(zip(sys.argv[3::2], sys.argv[4::2]))
        # --since is required: without it an earlier run's complete result read as DONE at once (#191).
        if len(sys.argv) % 2 == 0 or set(options) - {'--since', '--exit', '--stale'} or '--since' not in options:
            raise ValueError('usage: codex_worker.py --wait RESULT --since START [--stale ID] [--exit RECORD]')
        result, since = Path(sys.argv[2]), float(options['--since'])
        record = Path(options['--exit']) if '--exit' in options else None
        stale = options.get('--stale')
        if stale is None:
            stale = baseline(result, since)
        elif ':' not in stale:
            stale = int(stale) or None
        elif not stale.startswith('sha256:'):
            stale = 'sha256:' + stale.partition(':')[2]  # INO:HASH, printed before the hash alone decided
        pin(result, stale)
        started = False  # this run's .live record seen: the wait is open-ended from then on
        while True:
            # Read first: what the supervisor published or recorded before it ended is seen below.
            ended = record is not None and gone(record.with_suffix('.live'), since)
            kind, published_id = result_kind(result, since, stale)
            if kind:
                print('codex_worker: ' + kind + ': ' + str(result), flush=True)
                if kind == 'HANDOFF':
                    print('codex_worker: its session ends on a handoff; continue it in its own session with '
                          '--resume (spawn_codex.sh or spawn_worker.sh), or start a fresh one from it', flush=True)
                if kind == 'PROGRESS':
                    # The worker goes on. The same wait with this result as the stale one reports the
                    # next; --since stays the run's start, which the .live and .exit records are read by.
                    again = [Path(sys.executable).as_posix(), Path(sys.argv[0]).absolute().as_posix(),
                             '--wait', sys.argv[2], '--since', options['--since'],
                             '--stale', str(published_id or 0)] + (['--exit', options['--exit']] if record else [])
                    print('codex_worker: the worker goes on; run as the next background command for its next '
                          'result: ' + ' '.join(map(shlex.quote, again)), flush=True)
                return 0
            try:
                if record and record.stat().st_mtime >= since:
                    print('codex_worker: EXITED (' + record.read_text(encoding='utf-8').strip()
                          + ') without publishing a new result: ' + str(result), flush=True)
                    return 0
            except FileNotFoundError:
                pass
            if not_a_result(result, since, stale):
                print('codex_worker: NOT A RESULT: ' + str(result) + ' changed in this run and sat unchanged '
                      + str(SETTLED) + ' s without the result header (Kind/Task/Attempt/Remaining) and '
                      + READY + '; read it by hand', flush=True)
                return 0
            if ended:
                print('codex_worker: EXITED (its supervisor ended without an exit record: its tab closed '
                      'or it was killed) without publishing a new result: ' + str(result), flush=True)
                return 0
            if record and not started and time.time() > since + START:
                # A failed `cd` or a python missing from the tab's login shell runs no supervisor,
                # which writes neither record: without this the wait never returned (#191).
                try:
                    started = record.with_suffix('.live').stat().st_mtime >= since
                except FileNotFoundError:
                    pass
                except OSError:
                    started = True  # a record that cannot be read is no proof it is missing
                if not started:
                    print('codex_worker: NOT STARTED: no supervisor record within %d s of the launch (its tab '
                          'or session failed before the supervisor ran: look at it; running the same wait '
                          'again is safe) and no new result: %s' % (START, result), flush=True)
                    return 0
            time.sleep(0.1)
    if sys.argv[1:2] == ['--publish']:
        # The worker's own last step: its finished temporary file renamed over the destination.
        if len(sys.argv) != 4:
            raise ValueError('usage: codex_worker.py --publish TEMPORARY_FILE DESTINATION')
        # A question without the marker never ended its session (bge2e): refused here, the worker sees why.
        if not decoded(Path(sys.argv[2]).read_bytes()).strip().endswith(READY):
            raise ValueError('%s: its last line is not %s; add it and publish again: without it the supervisor '
                             'never sees it' % (sys.argv[2], READY))
        try:
            renamed(sys.argv[2], sys.argv[3])
        except OSError as error:
            # A temporary file in %TEMP% (C:) for a result on D: (donemsg spike 3): [WinError 17].
            if error.errno != errno.EXDEV:
                raise
            raise ValueError('%s: it is on another drive than %s, and a rename cannot cross drives; put the '
                             'temporary file beside the destination (same drive) and publish again'
                             % (sys.argv[2], sys.argv[3])) from None
        return 0
    if sys.argv[1:2] == ['--detach']:
        # The bg host's supervisor (spawn_worker.sh) outlives the lead's shell call that started
        # it, as a tab's did: in a session of its own on POSIX; on Windows in a process group of
        # its own, out of the caller's job where the job allows it, with no console window.
        if len(sys.argv) < 4:
            raise ValueError('usage: codex_worker.py --detach LOG ARGUMENTS...')
        command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[3:]]
        with open(sys.argv[2], 'ab') as log:
            # Its folder is not the checkout, which Windows refuses to remove while a process is in
            # it (close_worker.sh's audit kept the worktree); KIT_WORKER_CHECKOUT names it for locks().
            options = dict(stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd=tempfile.gettempdir(),
                           env=dict(os.environ, KIT_WORKER_CHECKOUT=os.getcwd()))
            if os.name != 'nt':
                subprocess.Popen(command, start_new_session=True, **options)
                return 0
            flags = 0x08000000 | 0x200  # CREATE_NO_WINDOW, CREATE_NEW_PROCESS_GROUP
            try:
                subprocess.Popen(command, creationflags=flags | 0x01000000, **options)  # CREATE_BREAKAWAY_FROM_JOB
            except OSError:
                subprocess.Popen(command, creationflags=flags, **options)  # a job that forbids breakaway
        return 0
    record = os.environ.get('KIT_WORKER_EXIT')
    previous = question_id(Path(record)) if record else None
    try:
        return supervise()
    except BaseException as error:
        # A supervisor that fails before watch() records its end (a refused question, its live
        # record, its child) records it here: --wait would wait on the previous run's forever.
        if record and question_id(Path(record)) == previous:
            record_exit('supervisor failed to start (%s)' % type(error).__name__)
        raise


def supervise():
    # QUESTION [RESULT] --bg ID supervises a `claude --bg` session that is already running.
    background = len(sys.argv) in (4, 5) and sys.argv[-2] == '--bg' and '--' not in sys.argv[2:4]
    if not background and (len(sys.argv) < 4 or '--' not in sys.argv[2:4]):
        raise ValueError('usage: codex_worker.py QUESTION_FILE [RESULT_FILE] -- COMMAND... '
                         '| QUESTION_FILE [RESULT_FILE] --bg SESSION_ID')
    question = Path(sys.argv[1])
    separator = len(sys.argv) - 2 if background else sys.argv.index('--')
    result = Path(sys.argv[2]) if separator == 3 else None
    answered = question_id(question)
    if answered is not None and os.environ.get('KIT_WORKER_RESUME') != '1':
        raise ValueError('question file already exists; answer it with --resume (spawn_codex.sh or spawn_worker.sh)')
    since = float(os.environ.get('KIT_WORKER_STARTED', '0'))
    stale = (int(os.environ['KIT_WORKER_STALE']) or None if 'KIT_WORKER_STALE' in os.environ
             else baseline(result, since))
    pin(result, stale)
    record = os.environ.get('KIT_WORKER_EXIT')
    if record:
        # Locked for this process's whole life, however it ends: --wait reads a dropped lock as a
        # supervisor that could not write its exit record (a closed tab, taskkill /F, SIGKILL).
        live = start_live(record)
    if background:
        return watch(Background(sys.argv[-1]), question, None, result, stale, answered)
    # Git for Windows reparses bash -c's quoted command. Hand it a script file instead,
    # just as spawn_worker.sh does for Windows Terminal.
    command = sys.argv[separator + 1:]
    with tempfile.TemporaryDirectory(prefix='codex-worker-') as tmp:
        if os.name == 'nt' and len(command) == 3 and command[1] == '-c':
            script = Path(tmp) / 'worker.sh'
            script.write_text(command[2] + '\n', encoding='utf-8', newline='\n')
            command = [command[0], str(script)]
        if os.name == 'nt':
            child, close = windows_child(command)  # inherit the tab's terminal, including stdin
            return watch(child, question, close, result, stale, answered)
        # A CLI installed through npm has a shim and a native child. Own their process group
        # while keeping the controlling terminal, so /dev/tty and interactive input work.
        terminal = sys.stdin.fileno() if sys.stdin.isatty() else None
        foreground = os.tcgetpgrp(terminal) if terminal is not None else None
        previous = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
        child = None
        handlers = {}
        cancelled = None
        supervising = False
        def terminate(sig, frame):
            nonlocal cancelled
            cancelled = sig
            if supervising:
                raise SystemExit(128 + sig)
        try:
            for sig in (signal.SIGTERM, signal.SIGHUP):
                handlers[sig] = signal.signal(sig, terminate)
            child = subprocess.Popen(command, preexec_fn=os.setpgrp, env=child_env())
            def close_tree(force=False):
                posix_tree(child.pid, force)
            supervising = True
            if cancelled is not None:
                raise SystemExit(128 + cancelled)
            if terminal is not None:
                os.tcsetpgrp(terminal, child.pid)
                os.killpg(child.pid, signal.SIGCONT)
            return watch(child, question, close_tree, result, stale, answered)
        finally:
            supervising = False
            if child is not None:
                stop(child, lambda force=False: posix_tree(child.pid, force))
            if terminal is not None:
                os.tcsetpgrp(terminal, foreground)
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
            signal.signal(signal.SIGTTOU, previous)


def consume(question, answered):
    """Remove the answered decision unless a new one replaced it. Returns None once done, and
    ANSWERED while the file cannot go yet (open elsewhere on Windows): the caller retries.
    Hold the answered inode, rename the path aside, then verify before unlinking only the
    temporary name. If publication wins the rename race, restore its question without replacing
    a later publication. A second publication keeps the displaced question at the temporary name."""
    fd, directory, aside = None, None, None
    try:
        fd = shared_open(question)
        info = os.fstat(fd)
        identity = info.st_ino, info.st_mtime_ns, info.st_size
        if identity != answered:
            return None
        directory = Path(tempfile.mkdtemp(prefix='.' + question.name + '-consume-', dir=question.parent))
        aside = directory / question.name
        os.rename(question, aside)
        if question_id(aside) != identity:
            try:
                os.link(aside, question)  # atomic restoration, refusing to overwrite a later publication
            except FileExistsError:
                print('codex_worker: concurrent question preserved at ' + str(aside), file=sys.stderr, flush=True)
                return None
        aside.unlink()
    except FileNotFoundError:
        return None
    except OSError:
        if aside is not None and aside.exists():
            try:
                os.link(aside, question)
            except FileExistsError:
                pass
            except OSError:
                print('codex_worker: question recovery required at ' + str(aside), file=sys.stderr, flush=True)
        return answered
    finally:
        if fd is not None:
            os.close(fd)
        if directory is not None:
            try:
                directory.rmdir()
            except OSError:
                pass  # a question which could not be deleted or restored remains recoverable
    return None


def record_exit(ended):
    """Record why the supervisor ended, so --wait reports it instead of waiting forever."""
    record = os.environ.get('KIT_WORKER_EXIT')
    if record:
        Path(record).write_text('%s at %s\n' % (ended, time.strftime('%Y-%m-%dT%H:%M:%S')), encoding='utf-8')


def locks():
    """index.lock and check.lock of the checkout this supervisor runs in (KIT_WORKER_CHECKOUT for a
    detached one); none outside git. Git prints UTF-8 paths: read as the locale (cp1252 without
    UTF-8 mode), a Unicode checkout's lock path is wrong and its lock never seen."""
    paths = []
    checkout = os.environ.get('KIT_WORKER_CHECKOUT', '.')
    for name in ('index.lock', 'check.lock'):
        try:
            paths.append(Path(subprocess.run(['git', '-C', checkout, 'rev-parse', '--path-format=absolute', '--git-path', name],
                                             capture_output=True, encoding='utf-8', check=True).stdout.strip()))
        except (OSError, subprocess.CalledProcessError):
            return []
    return paths


def busy(paths):
    """Whether a git operation (index.lock) or a gate (check.sh holds check.lock) runs in the
    worker's checkout, by close_worker.sh's rules: ending the worker then orphans that run.
    A lock that cannot be checked counts as held. An index.lock unchanged for STALE_LOCK seconds
    while no gate holds check.lock is one a killed git left behind: it is reported and no longer
    waited on (ultrareview part 6 #5: the tab stayed open forever). A gate in a commit hook holds
    check.lock, so it is waited on however long it runs. ponytail: another commit hook that runs
    longer than STALE_LOCK without the gate is not waited on; raise STALE_LOCK if one does."""
    index = None
    for path in paths:
        if path.name == 'index.lock':
            index = path
            continue
        try:
            if os.name == 'nt':
                open(path, 'r+').close()  # refused while a gate holds it: no write sharing
            else:
                import fcntl
                with open(path, 'a') as file:
                    fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except FileNotFoundError:
            pass
        except OSError:
            return True
    if index is None:
        return False
    try:
        age = time.time() - index.stat().st_mtime
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if age < STALE_LOCK:
        return True
    print('codex_worker: %s has not changed for %d min and no gate runs: a stale lock a killed git left '
          'behind; the worker ends anyway. Remove it before the next git command there' % (index, age // 60),
          flush=True)
    return False


def watch(child, question, close_tree, result=None, stale=None, answered=None):
    ready_at = None
    latched = None  # result and question ids seen when grace passed
    checkout = None  # its lock paths, asked of git once a result or a decision is ready
    noticed = ''
    asked = None, ''  # the id of the last new question read, and its published text
    ended = 'stopped by a signal or an error in its supervisor'
    since = float(os.environ.get('KIT_WORKER_STARTED', '0'))  # main() parsed it already
    try:
        grace = float(os.environ.get('KIT_WORKER_GRACE', '10'))
        if grace < 0:
            raise ValueError('KIT_WORKER_GRACE must be nonnegative seconds')
        while child.poll() is None:
            kind, result_id = result_kind(result, since, stale)
            # A valid new result shows observable acceptance. Survival alone cannot distinguish
            # a resumed session that took its answer from one that will fail without doing so.
            if answered is not None and kind:
                answered = consume(question, answered)
            # A decision, a completed result or a handoff ends the worker: PROGRESS and BLOCKED
            # leave it working, and --wait alone reports them. A handoff with only the lead's work
            # left kept its tab open, and spawn_codex.sh refused --resume while it ran (followups.md,
            # py311 Codex tab); its conversation stays resumable once the session ended.
            # The id first: the answered question is never opened, and a new one only after its id,
            # size or time changed, as a result: Windows refuses a rename over a file held open.
            identity = question_id(question)
            if identity not in (answered, asked[0]):
                text = published(question)
                asked = (None if text is None else identity), text or ''
            decision = identity != answered and asked[1]
            notice = 'decision' if decision else kind
            notice = notice if notice in ('decision', 'DONE', 'HANDOFF') else ''
            # After grace, the lead may move the publication while its gate still runs.
            # Keep the close pending if it disappears; only a new publication replaces it.
            # A standing result seen with a decision is not new when that decision moves.
            if notice != noticed and (latched is None or (decision and identity != latched[1])
                                      or (kind and result_id != latched[0])):
                ready_at = time.monotonic() if notice else None
                noticed = notice
                latched = None
            if ready_at is not None and time.monotonic() - ready_at >= grace:
                if latched is None:
                    latched = result_id, identity
                if checkout is None:
                    checkout = locks()
                if busy(checkout):
                    time.sleep(0.5)  # a commit or a gate after the result: the worker ends after it
                    continue
                stop(child, close_tree)
                close_tree = None
                ended = noticed + ' published'
                if noticed == 'decision':
                    print('codex_worker: decision recorded; answer in the same session with --resume', flush=True)
                else:
                    print('codex_worker: ' + noticed + ': uncommitted result ready for the lead', flush=True)
                return 0
            time.sleep(0.1)
        ended = 'exit %d' % child.returncode
        return child.returncode
    finally:
        stop(child, close_tree)
        # Every way out records why, a decision without a blocked result included: the record
        # lets --wait report it instead of waiting forever.
        record_exit(ended)
        # A launch error, or a cancellation or failed CLI before the session took its answer,
        # keeps the answered decision for the retry; a new question stays too. Never changes the result.
        try:
            if answered is not None and (ended == 'exit 0' or result_kind(result, since, stale)[0]):
                consume(question, answered)
        except (OSError, ValueError):
            pass


if __name__ == '__main__':
    # A Windows pipe is cp1252 unless UTF-8 mode is on: a Unicode result path must still print.
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit('codex_worker: ' + str(error))
