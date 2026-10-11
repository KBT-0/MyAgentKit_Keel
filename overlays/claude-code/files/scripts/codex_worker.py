#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Close a worker after a published decision or completed result; --wait notifies the lead
without a commit, also when the worker ended without publishing (its exit record)."""
import os
from pathlib import Path
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
    try:
        info = path.stat() if path else None
    except FileNotFoundError:
        return ''
    if info is None or info.st_mtime < since or info.st_ino == stale:
        return ''
    text = published(path)
    lines = text.splitlines()
    if (len(lines) < 4 or not lines[1].startswith('Task: ')
            or not lines[2].startswith('Attempt: ') or not lines[2][9:].isdigit()
            or not lines[3].startswith('Remaining: ')):
        return ''
    return {'Kind: completed': 'DONE', 'Kind: blocked': 'BLOCKED',
            'Kind: handoff': 'HANDOFF', 'Kind: progress': 'PROGRESS'}.get(lines[0], '')


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
        while not (kind := result_kind(result, since, stale)):
            try:
                if record and record.stat().st_mtime >= since:
                    print('codex_worker: EXITED (' + record.read_text(encoding='utf-8').strip()
                          + ') without publishing a new result: ' + str(result), flush=True)
                    return 0
            except FileNotFoundError:
                pass
            time.sleep(0.1)
        print('codex_worker: ' + kind + ': ' + str(result), flush=True)
        return 0
    if len(sys.argv) < 4 or '--' not in sys.argv[2:4]:
        raise ValueError('usage: codex_worker.py QUESTION_FILE [RESULT_FILE] -- COMMAND...')
    question = Path(sys.argv[1])
    separator = sys.argv.index('--')
    result = Path(sys.argv[2]) if separator == 3 else None
    if question.exists():
        raise ValueError('question file already exists; answer with spawn_codex.sh --resume')
    since = float(os.environ.get('KIT_WORKER_STARTED', '0'))
    stale = (int(os.environ['KIT_WORKER_STALE']) or None if 'KIT_WORKER_STALE' in os.environ
             else baseline(result, since))
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
            return watch(child, question, close, result, stale)
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
            return watch(child, question, close_tree, result, stale)
        finally:
            supervising = False
            if child is not None:
                stop(child, lambda force=False: posix_tree(child.pid, force))
            if terminal is not None:
                os.tcsetpgrp(terminal, foreground)
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
            signal.signal(signal.SIGTTOU, previous)


def watch(child, question, close_tree, result=None, stale=None):
    ready_at = None
    noticed = ''
    try:
        grace = float(os.environ.get('KIT_WORKER_GRACE', '10'))
        if grace < 0:
            raise ValueError('KIT_WORKER_GRACE must be nonnegative seconds')
        since = float(os.environ.get('KIT_WORKER_STARTED', '0'))
        while child.poll() is None:
            # Only a decision or a completed result ends the worker: PROGRESS, HANDOFF and
            # BLOCKED leave it working, and --wait alone reports them.
            notice = 'decision' if published(question) else result_kind(result, since, stale)
            notice = notice if notice in ('decision', 'DONE') else ''
            if notice != noticed:
                ready_at = time.monotonic() if notice else None
                noticed = notice
            if ready_at is not None and time.monotonic() - ready_at >= grace:
                stop(child, close_tree)
                close_tree = None
                if noticed == 'decision':
                    print('codex_worker: decision recorded; answer in the same session with --resume', flush=True)
                else:
                    print('codex_worker: ' + noticed + ': uncommitted result ready for the lead', flush=True)
                return 0
            time.sleep(0.1)
        # It ended on its own: the exit record lets --wait report it instead of waiting forever.
        record = os.environ.get('KIT_WORKER_EXIT')
        if record:
            Path(record).parent.mkdir(parents=True, exist_ok=True)
            Path(record).write_text('exit %d at %s\n' % (child.returncode, time.strftime('%Y-%m-%dT%H:%M:%S')),
                                    encoding='utf-8')
        return child.returncode
    finally:
        stop(child, close_tree)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit('codex_worker: ' + str(error))
