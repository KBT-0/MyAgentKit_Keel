#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Close a worker after a published decision or completed result; --wait notifies the lead
without a commit, also when the worker stopped without publishing (its exit record) or its
supervisor was killed (its lock on the .live record dropped)."""
import os
from pathlib import Path
import shlex
import subprocess
import signal
import sys
import tempfile
import time

READY = '<!-- codex-worker: ready -->'


def published(path):
    try:
        text = path.read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        return ''
    return text if text.endswith(READY) else ''


def question_id(path):
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return info.st_ino, info.st_mtime_ns, info.st_size


def baseline(path, since):
    """The file id of a result published before this run: an in-place edit of it never counts
    as a new publication, only a rename over it (the atomic protocol) does."""
    try:
        info = path.stat() if path else None
    except FileNotFoundError:
        return None
    # ponytail: a filesystem with no file ids (st_ino 0) falls back to the mtime check alone.
    return info.st_ino or None if info and info.st_mtime < since and published(path) else None


def result_kind(path, since=0, stale=None):
    """The kind of a result published in this run, and its file id; '' when there is none."""
    try:
        info = path.stat() if path else None
    except FileNotFoundError:
        return '', None
    if info is None or info.st_mtime < since or info.st_ino == stale:
        return '', None
    text = published(path)
    lines = text.splitlines()
    if (len(lines) < 4 or not lines[1].startswith('Task: ')
            or not lines[2].startswith('Attempt: ') or not lines[2][9:].isdigit()
            or not lines[3].startswith('Remaining: ')):
        return '', None
    return {'Kind: completed': 'DONE', 'Kind: blocked': 'BLOCKED', 'Kind: handoff': 'HANDOFF',
            'Kind: progress': 'PROGRESS'}.get(lines[0], ''), info.st_ino


def pin(path, stale):
    """Hold the stale result open for this process's life on POSIX: ext4 reuses a freed inode
    number at once, and a new result given it would read as the stale one. A held inode is never
    freed. NTFS ids carry a sequence number, and an open handle there blocks the publishing rename."""
    if os.name == 'nt' or not stale or path is None:
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


def gone(live, since):
    """Whether the supervisor of this run, which locked LIVE when it started, has ended."""
    try:
        if live.stat().st_mtime < since:
            return False  # not started yet, or a previous run's
        fd = os.open(live, os.O_RDONLY)
    except FileNotFoundError:
        return False
    try:
        lock(fd)
        ready = os.read(fd, 64)
        return (os.fstat(fd).st_mtime >= since and ready.endswith(b'\n')
                and ready[:-1].isdigit())  # the PID is published only after startup locks LIVE
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
            raise ValueError('usage: codex_worker.py --wait RESULT [--since START] [--stale FILE_ID] [--exit RECORD]')
        result, since = Path(sys.argv[2]), float(options.get('--since', 0))
        record = Path(options['--exit']) if '--exit' in options else None
        stale = int(options['--stale']) or None if '--stale' in options else baseline(result, since)
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
                    # ponytail: a filesystem without file ids (st_ino 0) reports this result again.
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
        Path(record).parent.mkdir(parents=True, exist_ok=True)
        live = os.open(Path(record).with_suffix('.live'), os.O_RDWR | os.O_CREAT)
        lock(live)
        os.ftruncate(live, 0)
        os.write(live, b'%d\n' % os.getpid())  # after the lock: its time marks this run
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


def watch(child, question, close_tree, result=None, stale=None, answered=None):
    ready_at = None
    noticed = ''
    ended = 'stopped by a signal or an error in its supervisor'
    try:
        grace = float(os.environ.get('KIT_WORKER_GRACE', '10'))
        if grace < 0:
            raise ValueError('KIT_WORKER_GRACE must be nonnegative seconds')
        since = float(os.environ.get('KIT_WORKER_STARTED', '0'))
        while child.poll() is None:
            # Only a decision or a completed result ends the worker: PROGRESS, HANDOFF and
            # BLOCKED leave it working, and --wait alone reports them.
            decision = published(question) and question_id(question) != answered
            notice = 'decision' if decision else result_kind(result, since, stale)[0]
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
        # Keep the answered decision as closure evidence until the resumed child succeeds.
        # A launch error, cancellation or failed CLI leaves it, and a new question stays too.
        if (answered is not None and ended in ('exit 0', 'DONE published')
                and question_id(question) == answered):
            question.unlink()
        # Every way out records why, a decision without a blocked result included: the record
        # lets --wait report it instead of waiting forever.
        record = os.environ.get('KIT_WORKER_EXIT')
        if record:
            Path(record).write_text('%s at %s\n' % (ended, time.strftime('%Y-%m-%dT%H:%M:%S')), encoding='utf-8')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit('codex_worker: ' + str(error))
