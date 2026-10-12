#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Close a worker after a published decision or completed result; --wait notifies the lead
without a commit, also when the worker stopped without publishing (its exit record) or its
supervisor was killed (its lock on the .live record dropped). --publish TEMPORARY_FILE
DESTINATION is the worker's own last step: the rename, retried while Windows refuses it."""
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
import signal
import sys
import tempfile
import time

READY = '<!-- codex-worker: ready -->'
REFUSALS = 50  # consecutive Windows refusals of one path a poller waits through, about five seconds
REFUSED = {}  # path: its consecutive refusals


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


def published(path):
    """The text of a decision published with its end marker, '' without one, None when refused."""
    try:
        text = path.read_text(encoding='utf-8').strip()
    except FileNotFoundError:
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
            return seen[1]
        with path.open(encoding='utf-8') as file:
            info = os.fstat(file.fileno())
            text = file.read().strip()
    except FileNotFoundError:
        return '', None
    except PermissionError as error:
        tolerated(path, error)
        return '', None  # opened in the middle of a rename over it; the next poll reads it
    REFUSED.pop(path, None)
    SEEN[path] = (info.st_ino, info.st_size, info.st_mtime_ns, since, stale), parse(text, info, since, stale)
    return SEEN[path][1]


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


def windows_child(command):
    child = subprocess.Popen(command, creationflags=0x4)  # CREATE_SUSPENDED
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
    except ProcessLookupError:
        pass


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == '--wait':
        options = dict(zip(sys.argv[3::2], sys.argv[4::2]))
        if len(sys.argv) % 2 == 0 or set(options) - {'--since', '--exit', '--stale'}:
            raise ValueError('usage: codex_worker.py --wait RESULT [--since START] [--stale ID] [--exit RECORD]')
        result, since = Path(sys.argv[2]), float(options.get('--since', 0))
        record = Path(options['--exit']) if '--exit' in options else None
        stale = options.get('--stale')
        if stale is None:
            stale = baseline(result, since)
        elif ':' not in stale:
            stale = int(stale) or None
        elif not stale.startswith('sha256:'):
            stale = 'sha256:' + stale.partition(':')[2]  # INO:HASH, printed before the hash alone decided
        pin(result, stale)
        while True:
            # Read first: what the supervisor published or recorded before it ended is seen below.
            ended = record is not None and gone(record.with_suffix('.live'), since)
            kind, published_id = result_kind(result, since, stale)
            if kind:
                print('codex_worker: ' + kind + ': ' + str(result), flush=True)
                if kind in ('PROGRESS', 'HANDOFF'):
                    # The worker goes on. The same wait with this result as the stale one reports the
                    # next; --since stays the run's start, which the .live and .exit records are read by.
                    again = [Path(sys.executable).as_posix(), Path(sys.argv[0]).absolute().as_posix(),
                             '--wait', sys.argv[2], '--since', options.get('--since', '0'),
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
            if ended:
                print('codex_worker: EXITED (its supervisor ended without an exit record: its tab closed '
                      'or it was killed) without publishing a new result: ' + str(result), flush=True)
                return 0
            time.sleep(0.1)
    if sys.argv[1:2] == ['--publish']:
        # The worker's own last step: its finished temporary file renamed over the destination.
        if len(sys.argv) != 4:
            raise ValueError('usage: codex_worker.py --publish TEMPORARY_FILE DESTINATION')
        renamed(sys.argv[2], sys.argv[3])
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
    if len(sys.argv) < 4 or '--' not in sys.argv[2:4]:
        raise ValueError('usage: codex_worker.py QUESTION_FILE [RESULT_FILE] -- COMMAND...')
    question = Path(sys.argv[1])
    separator = sys.argv.index('--')
    result = Path(sys.argv[2]) if separator == 3 else None
    answered = question_id(question)
    if answered is not None and os.environ.get('KIT_WORKER_RESUME') != '1':
        raise ValueError('question file already exists; answer with spawn_codex.sh --resume')
    since = float(os.environ.get('KIT_WORKER_STARTED', '0'))
    stale = (int(os.environ['KIT_WORKER_STALE']) or None if 'KIT_WORKER_STALE' in os.environ
             else baseline(result, since))
    pin(result, stale)
    record = os.environ.get('KIT_WORKER_EXIT')
    if record:
        # Locked for this process's whole life, however it ends: --wait reads a dropped lock as a
        # supervisor that could not write its exit record (a closed tab, taskkill /F, SIGKILL).
        live = start_live(record)
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
            child = subprocess.Popen(command, preexec_fn=os.setpgrp)
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


def watch(child, question, close_tree, result=None, stale=None, answered=None):
    ready_at = None
    noticed = ''
    asked = None, ''  # the id of the last new question read, and its published text
    ended = 'stopped by a signal or an error in its supervisor'
    since = float(os.environ.get('KIT_WORKER_STARTED', '0'))  # main() parsed it already
    try:
        grace = float(os.environ.get('KIT_WORKER_GRACE', '10'))
        if grace < 0:
            raise ValueError('KIT_WORKER_GRACE must be nonnegative seconds')
        while child.poll() is None:
            kind = result_kind(result, since, stale)[0]
            # A valid new result shows observable acceptance. Survival alone cannot distinguish
            # a resumed session that took its answer from one that will fail without doing so.
            if answered is not None and kind:
                answered = consume(question, answered)
            # Only a decision or a completed result ends the worker: PROGRESS, HANDOFF and
            # BLOCKED leave it working, and --wait alone reports them.
            # The id first: the answered question is never opened, and a new one only after its id,
            # size or time changed, as a result: Windows refuses a rename over a file held open.
            identity = question_id(question)
            if identity not in (answered, asked[0]):
                text = published(question)
                asked = (None if text is None else identity), text or ''
            decision = identity != answered and asked[1]
            notice = 'decision' if decision else kind
            notice = notice if notice in ('decision', 'DONE') else ''
            if notice != noticed:
                ready_at = time.monotonic() if notice else None
                noticed = notice
            if ready_at is not None and time.monotonic() - ready_at >= grace:
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
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit('codex_worker: ' + str(error))
