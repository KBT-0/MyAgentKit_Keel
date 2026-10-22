# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Portable offline CLI fixtures and explicit platform exclusions for review tests."""
import io
import os
from pathlib import Path
import shlex
import signal
import sys
import unittest

# A fallback named python or py may be the only Python command on PATH.
# A launcher sh and Python both read: sh runs `:` then execs the (quoted: a path with a
# space) interpreter on this file; Python sees a string literal and goes on.
PYTHON_SHEBANG = "#!/bin/sh\n''':'\nexec %s \"$0\" \"$@\"\n'''\n" % shlex.quote(sys.executable)
WINDOWS = os.name == 'nt'
# A case that needs a POSIX host (signal masks, process groups, FIFOs, sh shims on PATH) is
# skipped on native Windows with this reason; CI's Linux and macOS jobs run it.
def posix_only(test):
    wrapped = unittest.skipIf(WINDOWS, 'needs POSIX signals, groups or tools; CI runs it on Linux and macOS')(test)
    wrapped._kit_platform_skip = WINDOWS
    return wrapped


def test_cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from test_cases(item)
        else:
            yield item


def platform_skips(suite):
    return {test.id() for test in test_cases(suite)
            if getattr(getattr(test, test._testMethodName), '_kit_platform_skip', False)}



def fixture_source(path):
    """The script a python_cli() fixture runs (on Windows, the zip appended to its launcher)."""
    if not WINDOWS:
        return Path(path).read_text()
    import zipfile
    with zipfile.ZipFile(path) as script:
        return script.read('__main__.py').decode()


def send_cancel(sig):
    """Send this process a cancel. POSIX: to the process, as a terminal or `kill` does. Native
    Windows: os.kill is TerminateProcess there (a test run died with exit 15 and no output),
    while raise_signal reaches the installed handler, as a console Ctrl-C does."""
    if WINDOWS:
        signal.raise_signal(sig)
    else:
        os.kill(os.getpid(), sig)


WINDOWS_LF = ('import pathlib as _pathlib, sys as _sys\n'
              '_sys.stdout.reconfigure(newline="\\n"); _sys.stderr.reconfigure(newline="\\n")\n'
              '_write_text = _pathlib.Path.write_text\n'
              '_pathlib.Path.write_text = lambda self, data, encoding=None, errors=None, newline="\\n": '
              '_write_text(self, data, encoding, errors, newline)\n')


def python_cli(path, text):
    """Write a fixture CLI that runs `text` under this interpreter; return the path to launch.

    POSIX runs the PYTHON_SHEBANG launcher. Native Windows runs no shebang (every fixture
    exited 127 there), and a .cmd launcher hands its arguments to cmd.exe as shell: the
    fixture is `path`.exe, pip's console-script launcher with the script appended as a zip,
    which is how an installed Python CLI runs there.
    """
    path = Path(path)
    if not WINDOWS:
        path.write_text(text)
        path.chmod(0o755)
        return path
    import platform
    import zipfile
    import pip._vendor.distlib as distlib
    launcher = Path(distlib.__file__).parent / ('t64-arm.exe' if platform.machine() == 'ARM64' else ('t64.exe' if sys.maxsize > 2**32 else 't32.exe'))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as script:
        # The sh trampoline quotes a Windows interpreter path whose backslashes Python reads as
        # escapes. A real CLI writes LF there too; Python's text mode would write CRLF.
        script.writestr('__main__.py', WINDOWS_LF + text.removeprefix(PYTHON_SHEBANG))
    exe = path.with_name(path.name + '.exe')
    exe.write_bytes(launcher.read_bytes() + b'#!"%s"\r\n' % os.fsencode(sys.executable) + archive.getvalue())
    return exe

