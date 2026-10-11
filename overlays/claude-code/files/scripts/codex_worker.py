#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Close a worker after a published handoff; --wait notifies the lead without a commit."""
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


def result_kind(path, since=0):
    if path:
        try:
            if path.stat().st_mtime < since:
                return ''
        except FileNotFoundError:
            return ''
    text = published(path) if path else ''
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
    if len(sys.argv) in (3, 5) and sys.argv[1] == '--wait':
        result = Path(sys.argv[2])
        since = float(sys.argv[4]) if len(sys.argv) == 5 and sys.argv[3] == '--since' else 0
        while not (kind := result_kind(result, since)):
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
            return watch(child, question, close, result)
        # A CLI installed through npm has a shim and a native child. Own their process group
        # while keeping the controlling terminal, so /dev/tty and interactive input work.
        terminal = sys.stdin.fileno() if sys.stdin.isatty() else None
        foreground = os.tcgetpgrp(terminal) if terminal is not None else None
        previous = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
        child = None
        try:
            child = subprocess.Popen(command, preexec_fn=os.setpgrp)
            if terminal is not None:
                os.tcsetpgrp(terminal, child.pid)
                os.killpg(child.pid, signal.SIGCONT)
            def close_tree(force=False):
                posix_tree(child.pid, force)
            return watch(child, question, close_tree, result)
        finally:
            if child is not None and child.poll() is None:
                child.kill()
                child.wait()
            if terminal is not None:
                os.tcsetpgrp(terminal, foreground)
            signal.signal(signal.SIGTTOU, previous)


def watch(child, question, close_tree, result=None):
    ready_at = None
    noticed = ''
    try:
        grace = float(os.environ.get('KIT_WORKER_GRACE', '10'))
        if grace < 0:
            raise ValueError('KIT_WORKER_GRACE must be nonnegative seconds')
        since = float(os.environ.get('KIT_WORKER_STARTED', '0'))
        while child.poll() is None:
            notice = 'decision' if published(question) else result_kind(result, since)
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
        return child.returncode
    finally:
        stop(child, close_tree)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit('codex_worker: ' + str(error))
