#!/usr/bin/env python3
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Close a worker after its decision; its result lists uncommitted files for the lead."""
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
import time


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
    return lambda: api.CloseHandle(handle)


def stop(child, close_tree=None):
    if close_tree:
        close_tree()
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def main():
    question = Path(sys.argv[1])
    if sys.argv[2] != '--' or len(sys.argv) < 4:
        raise ValueError('usage: codex_worker.py QUESTION_FILE -- COMMAND...')
    if question.exists():
        raise ValueError('question file already exists; answer with spawn_codex.sh --resume')
    # Git for Windows reparses bash -c's quoted command. Hand it a script file instead,
    # just as spawn_worker.sh does for Windows Terminal.
    command = sys.argv[3:]
    with tempfile.TemporaryDirectory(prefix='codex-worker-') as tmp:
        if os.name == 'nt' and len(command) == 3 and command[1] == '-c':
            script = Path(tmp) / 'worker.sh'
            script.write_text(command[2] + '\n', encoding='utf-8', newline='\n')
            command = [command[0], str(script)]
        if os.name == 'nt':
            child = subprocess.Popen(command)  # inherit the tab's terminal, including stdin
            return watch(child, question, windows_job(child))
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
            def close_tree():
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            return watch(child, question, close_tree)
        finally:
            if child is not None and child.poll() is None:
                child.kill()
                child.wait()
            if terminal is not None:
                os.tcsetpgrp(terminal, foreground)
            signal.signal(signal.SIGTTOU, previous)


def watch(child, question, close_tree):
    try:
        while child.poll() is None:
            if question.is_file() and question.stat().st_size:
                # Publish the file only after independent work and all jobs have stopped.
                stop(child, close_tree)
                close_tree = None
                print('codex_worker: decision recorded; answer in the same session with --resume', flush=True)
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
