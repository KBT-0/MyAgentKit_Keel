"""show_workers.sh must open every named session in one window or say how to attach by hand,
and watch_workers.sh must return when a session is gone or waits on a person, and only then.

No real terminal, no tmux server, no `claude`: tmux, the Windows Terminal launcher (KIT_WT,
never a file named *.exe: under WSL such a file is handed to Windows), osascript and uname
are stubs on PATH. The panes are real captures (tests/fixtures/panes/, see the README there).
"""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_close_worker import CLAUDE, agent  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'overlays/claude-code/files/scripts'
SHOW, WATCH, LIST = SCRIPTS / 'show_workers.sh', SCRIPTS / 'watch_workers.sh', SCRIPTS / 'list_workers.sh'
PANES = ROOT / 'tests/fixtures/panes'
DIALOGS = {'trust.txt': 'the folder-trust dialog', 'permission.txt': 'a permission prompt',
           'question.txt': 'a question'}
WORKING = ('idle.txt', 'working.txt', 'working-auto.txt', 'quoted-output.txt')

# Every target must be exact (`=NAME`): a prefix match reached another project's session.
TMUX = r'''#!/usr/bin/env python3
import os, sys
st = os.environ['VIS_STATE']
args = sys.argv[1:]
with open(os.path.join(st, 'tmux.log'), 'a') as log:
    log.write(repr(args) + '\n')
target = args[args.index('-t') + 1] if '-t' in args else ''
if target and not target.startswith('='):
    sys.exit('inexact target ' + target)
name = target[1:].rstrip(':')
sessions = os.environ.get('VIS_SESSIONS', '').split()
if args[0] == 'has-session':
    # A socket tmux cannot read: no answer either way.
    if os.path.exists(os.path.join(st, 'denied-' + name)):
        sys.exit('error connecting to /tmp/tmux-1000/default (Permission denied)')
    if name in sessions and not os.path.exists(os.path.join(st, 'gone-' + name)):
        sys.exit(0)
    sys.exit("can't find session: " + name)
if args[0] == 'list-clients':
    if name in os.environ.get('VIS_ATTACHED', '').split() or os.path.exists(os.path.join(st, 'attached-' + name)):
        print('/dev/pts/9: %s [120x30 xterm-256color] (attached,UTF-8)' % name)
    sys.exit(0 if name in sessions else 1)
# The watcher's once-markers are user options of the session: they end with it.
if args[0] in ('set-option', 'show-options'):
    if name not in sessions or os.path.exists(os.path.join(st, 'gone-' + name)):
        sys.exit("can't find session: " + name)
    opt = os.path.join(st, 'opt-%s-%s' % (name, args[-2] if args[0] == 'set-option' else args[-1]))
    if args[0] == 'set-option':
        with open(opt, 'w') as f:
            f.write(args[-1])
    elif os.path.exists(opt):
        with open(opt) as f:
            print(f.read())
    sys.exit(0)
if args[0] == 'capture-pane':
    if name in os.environ.get('VIS_CAPTURE_FAIL_FOR', name).split() and os.environ.get('VIS_CAPTURE_FAIL'):
        if os.environ.get('VIS_CAPTURE_FAIL') in ('ended', 'denied'):  # ended, or unreachable, during it
            open(os.path.join(st, os.environ['VIS_CAPTURE_FAIL'].replace('ended', 'gone') + '-' + name), 'w').close()
        sys.exit("can't find pane: " + name)
    pane = os.environ['VIS_PANE']
    if os.path.exists(os.path.join(st, 'slept')):
        pane = os.environ.get('VIS_PANE_LATER', pane)
    with open(pane, 'rb') as f:
        sys.stdout.buffer.write(f.read())
'''

# A launcher (wt or osascript): logs its argv and attaches a client to each session it names,
# the way a terminal tab running `tmux attach -t =NAME` would.
LAUNCHER = r'''#!/usr/bin/env python3
import os, re, sys, time
st = os.environ['VIS_STATE']
mode = os.environ.get('VIS_MODE', 'ok')
with open(os.path.join(st, os.path.basename(sys.argv[0]) + '.log'), 'a') as log:
    log.write(repr(sys.argv[1:]) + '\n')
if mode == 'enoexec':
    sys.stderr.write('wt.exe: cannot execute binary file: Exec format error\n')
    sys.exit(1)
if mode == 'hang':
    time.sleep(60)
if mode == 'hang-term':
    import signal
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(60)
names = re.findall(r"=([A-Za-z0-9_-]+)", ' '.join(sys.argv[1:]))
for n in names[:1] if mode == 'partial' else names:
    open(os.path.join(st, 'attached-' + n), 'w').close()
'''


def shq(value):
    return "'" + value.replace("'", "'\\''") + "'"


_POSIX = {}


def posix(path):
    """The path as the scripts print it. Native Windows (Git Bash) maps the temp folder to /tmp
    and C:\\x to /c/x, the form `command -v` and PATH lookups give; elsewhere the path as is."""
    path = str(path)
    if os.name != 'nt':
        return path
    if path not in _POSIX:
        _POSIX[path] = subprocess.run(['sh', '-c', 'cygpath -u "$0"', path], capture_output=True,
                                      text=True, check=True).stdout.strip()
    return _POSIX[path]


def sh_argv(script, args, env, redirect=''):
    """`sh SCRIPT ARGS...`. On native Windows the command line is re-parsed by the MSYS runtime
    (a single quote quotes, a newline splits an argument, an empty one can vanish), so an odd
    argument would reach the script changed: the arguments travel in the environment, quoted.
    REDIRECT is a shell redirection of the script's output (native Windows only)."""
    if os.name != 'nt':
        return ['sh', str(script), *args]
    env['VIS_ARGV'] = ' '.join(map(shq, args))
    return ['sh', '-c', 'eval "set -- $VIS_ARGV"; exec sh "$0" "$@"' + redirect, str(script)]


# run_script(stdout=DEV_FULL): the script's stdout is a device that refuses every write. Native
# Windows has no such file for Python to open, but Git Bash has /dev/full, so the shell opens it.
DEV_FULL = object()
HAS_DEV_FULL = os.name == 'nt' or os.path.exists('/dev/full')


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        # Named through a symlink, as macOS names every temp folder.
        (tmp / 'real').mkdir()
        (tmp / 'via').symlink_to(tmp / 'real')
        self.tmp = tmp / 'via'
        self.state, self.bin, self.cwd = self.tmp / 'state', self.tmp / 'bin', self.tmp / 'my proj!'
        for folder in (self.state, self.bin, self.cwd):
            folder.mkdir()
        for name, body in (('tmux', TMUX), ('wt-stub', LAUNCHER), ('osascript', LAUNCHER),
                           ('uname', '#!/bin/sh\necho "${VIS_UNAME:-Linux}"\n')):
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)

    def tearDown(self):
        self._tmp.cleanup()

    def run_script(self, script, *args, path_first=(), stdout=None, **extra):
        env = {k: v for k, v in os.environ.items()
               if k not in ('WSL_DISTRO_NAME', 'TERM_PROGRAM', 'TMUX', 'TMUX_PANE', 'KIT_WT', 'DISPLAY',
                            'WAYLAND_DISPLAY', 'TERMINAL')}
        path = os.pathsep.join([*map(str, path_first), str(self.bin), os.environ['PATH']])
        env.update(PATH=path, VIS_STATE=str(self.state), KIT_WT=posix(self.bin / 'wt-stub'), **extra)
        redirect = ''
        if stdout is DEV_FULL and os.name == 'nt':
            stdout, redirect = None, ' >/dev/full'
        elif stdout is DEV_FULL:
            stdout = open('/dev/full', 'w')
            self.addCleanup(stdout.close)
        argv = sh_argv(script, args, env, redirect)
        if stdout is not None:
            return subprocess.run(argv, cwd=self.cwd, env=env, stdout=stdout,
                                  stderr=subprocess.PIPE, text=True, encoding='utf-8', timeout=60)
        return subprocess.run(argv, cwd=self.cwd, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)

    def tmux_record(self, name):
        # The record a tmux spawn leaves in its checkout: without one, a name tmux does not know
        # is a usage error, never GONE (a bg worker spawned elsewhere is no tmux session either).
        workers = self.cwd / '.myagentkit' / 'workers'
        workers.mkdir(parents=True, exist_ok=True)
        (workers / (name + '.host')).write_text('tmux\n')
        exclude = self.cwd / '.git' / 'info' / 'exclude'
        if exclude.exists() and '.myagentkit/' not in exclude.read_text():
            exclude.write_text(exclude.read_text() + '\n.myagentkit/\n')

    def log(self, name):
        path = self.state / (name + '.log')
        return path.read_text(encoding='utf-8') if path.exists() else ''

    def full_buffer(self):
        # A `tr` first on PATH whose write into a regular file fails: the watcher's report
        # buffer is one, its stdout and stderr here are pipes.
        folder = self.tmp / 'full'
        folder.mkdir(exist_ok=True)
        (folder / 'tr').write_text('#!/bin/sh\nif [ -f /dev/stdout ]; then echo "tr: write error: No space left '
                                   'on device" >&2; exit 1; fi\nexec %s "$@"\n' % shq(shutil.which('tr')))
        (folder / 'tr').chmod(0o755)
        return [folder]

    def failing_tr(self, when):
        # A `tr` first on PATH that fails only one write into a regular file: the one for which
        # the shell test `when` holds; $in is its input.
        folder = self.tmp / 'failing'
        folder.mkdir(exist_ok=True)
        (folder / 'tr').write_text('#!/bin/sh\nreal=%s\n[ -f /dev/stdout ] || exec "$real" "$@"\n'
                                   'in=$(cat; echo .); in=${in%%.}\nif %s; then echo "tr: write error" >&2; '
                                   'exit 1; fi\nprintf %%s "$in" | "$real" "$@"\n'
                                   % (shq(shutil.which('tr')), when))
        (folder / 'tr').chmod(0o755)
        return [folder]


class ShowTests(Base):
    WSL = dict(WSL_DISTRO_NAME='Test-1', VIS_SESSIONS='a b-2 c_3')

    def wt_line(self, window, *names):
        args = [posix(self.bin / 'wt-stub'), '-w', window]
        for i, n in enumerate(names):
            args += [';'] if i else []
            args += ['new-tab', '--title', n, 'wsl.exe', '-d', 'Test-1', '--exec', posix(self.bin / 'tmux'),
                     'attach', '-t', '=' + n]
        return 'cd %s && %s' % (shq(posix(self.bin)), ' '.join(map(shq, args)))

    def osa_line(self, app, *names):
        cmd = lambda n: '"exec %s attach -t %s"' % (shq(posix(self.bin / 'tmux')), shq('=' + n))
        if app == 'iTerm':
            lines = ['tell application "iTerm"', 'activate', 'set w to (create window with default profile)']
            for i, n in enumerate(names):
                lines += ['tell w to create tab with default profile'] if i else []
                lines += ['tell current session of w to write text ' + cmd(n)]
        else:
            lines = ['tell application "Terminal"', 'activate'] + ['do script ' + cmd(n) for n in names]
        args = ['osascript']
        for line in lines + ['end tell']:
            args += ['-e', line]
        return "cd '/' && " + ' '.join(map(shq, args))

    def test_wsl_print_opens_one_window_with_a_tab_per_session(self):
        for names in (('a',), ('a', 'b-2', 'c_3')):
            with self.subTest(names=names):
                result = self.run_script(SHOW, '--print', *names, **self.WSL)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, self.wt_line('0', *names) + '\n')
                self.assertEqual(self.log('wt-stub'), '', '--print ran the launcher')

    def test_the_tabs_open_in_the_window_used_last_from_anywhere_in_the_project(self):
        # `-w 0`, the lead's own window: a window named after the project opened a second one.
        # From a subfolder and from a worktree it is the same.
        git = lambda *a: subprocess.run(['git', *a], cwd=self.cwd, check=True, capture_output=True)
        git('init', '-q')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'a')
        git('worktree', 'add', '-q', '.claude/worktrees/w', '-b', 'worktree-w')
        (self.cwd / 'sub').mkdir()
        for where in ('.', 'sub', '.claude/worktrees/w'):
            with self.subTest(where=where):
                env = dict(os.environ, PATH=os.pathsep.join([str(self.bin), os.environ['PATH']]),
                           VIS_STATE=str(self.state), KIT_WT=posix(self.bin / 'wt-stub'), **self.WSL)
                result = subprocess.run(['sh', str(SHOW), '--print', 'a'], cwd=self.cwd / where, env=env,
                                        capture_output=True, text=True, encoding='utf-8', timeout=60)
                self.assertIn("'-w' '0' 'new-tab'", result.stdout, result.stderr)

    def test_macos_print_uses_iterm_tabs_or_terminal_windows(self):
        for app, term in (('iTerm', 'iTerm.app'), ('Terminal', 'Apple_Terminal')):
            for names in (('a',), ('a', 'b-2', 'c_3')):
                with self.subTest(app=app, names=names):
                    result = self.run_script(SHOW, '--print', *names, VIS_UNAME='Darwin', TERM_PROGRAM=term,
                                             VIS_SESSIONS='a b-2 c_3')
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.splitlines()[-1], self.osa_line(app, *names))
                    self.assertEqual(self.log('osascript'), '')
        self.assertIn('one window per session', result.stdout)

    def test_elsewhere_it_opens_nothing_and_prints_the_attach_lines(self):
        for extra in ({}, {'--print': 1}):
            with self.subTest(print=bool(extra)):
                result = self.run_script(SHOW, *extra, 'a', 'b-2', VIS_SESSIONS='a b-2')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('attach by hand: tmux attach -t a\n', result.stdout)
                self.assertIn('attach by hand: tmux attach -t b-2\n', result.stdout)
                self.assertEqual(self.log('wt-stub') + self.log('osascript'), '')

    def test_a_missing_session_is_refused_by_name_and_nothing_opens(self):
        result = self.run_script(SHOW, 'a', 'nosuch', **self.WSL)
        self.assertEqual(result.returncode, 1)
        self.assertIn('nosuch', result.stderr)
        self.assertEqual(self.log('wt-stub'), '')

    def test_an_odd_session_name_is_refused_before_anything(self):
        # `;` would start a second Windows Terminal subcommand; quotes end an AppleScript string.
        for name in ('a;b', "a'b", 'a"b', 'a b', 'a.b', '', 'a\x1b[2J'):
            with self.subTest(name=name):
                result = self.run_script(SHOW, name, **self.WSL)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn('refused session name', result.stderr)
                self.assertNotIn('\x1b', result.stderr)
                self.assertEqual(self.log('wt-stub') + self.log('tmux'), '')

    def test_an_attached_session_is_skipped_so_repeating_opens_no_second_tab(self):
        result = self.run_script(SHOW, 'a', 'b-2', VIS_ATTACHED='a', **self.WSL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('a already has a terminal attached', result.stdout)
        self.assertNotIn("'=a'", self.log('wt-stub'))
        self.assertIn("'=b-2'", self.log('wt-stub'))
        self.assertIn('shown: b-2', result.stdout)
        launches = self.log('wt-stub')
        result = self.run_script(SHOW, 'a', 'b-2', VIS_ATTACHED='a', **self.WSL)
        self.assertEqual(self.log('wt-stub'), launches, 'a second call opened another tab')
        self.assertIn('b-2 already has a terminal attached', result.stdout)

    def test_a_session_counts_as_shown_only_once_a_client_attached(self):
        result = self.run_script(SHOW, 'a', 'b-2', 'c_3', **self.WSL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log('wt-stub').count('\n'), 1, 'one launch for the whole batch')
        for n in ('a', 'b-2', 'c_3'):
            self.assertIn('shown: %s\n' % n, result.stdout)
        # The launcher returned but only the first tab attached: the others get their line.
        for f in self.state.glob('attached-*'):
            f.unlink()
        result = self.run_script(SHOW, 'a', 'b-2', **self.WSL, VIS_MODE='partial')
        self.assertIn('shown: a\n', result.stdout)
        self.assertIn('no terminal attached to b-2 within 8 s; attach by hand: tmux attach -t b-2', result.stdout)

    def test_macos_launch_is_proved_the_same_way(self):
        result = self.run_script(SHOW, 'a', VIS_UNAME='Darwin', TERM_PROGRAM='iTerm.app', VIS_SESSIONS='a')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('shown: a', result.stdout)
        self.assertIn("'tell application \"iTerm\"'", self.log('osascript'))

    def test_wsl_interop_down_is_one_line_and_the_attach_lines(self):
        result = self.run_script(SHOW, 'a', 'b-2', VIS_MODE='enoexec', **self.WSL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('WSL interop is down', result.stdout)
        self.assertIn('attach by hand: tmux attach -t b-2', result.stdout)

    def test_a_launcher_that_ignores_sigterm_is_killed(self):
        # One SIGTERM and an endless wait: a launcher that ignores it hung the spawn with it.
        start = time.monotonic()
        result = self.run_script(SHOW, 'a', VIS_MODE='hang-term', **self.WSL)
        self.assertLess(time.monotonic() - start, 20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('did not return within 5 s', result.stdout)
        self.assertIn('attach by hand: tmux attach -t a', result.stdout)

    def test_a_linux_desktop_opens_its_terminal_and_a_headless_host_attaches_by_hand(self):
        # x-terminal-emulator is the launcher stub: it attaches the session it names (#238).
        (self.bin / 'x-terminal-emulator').write_text(LAUNCHER)
        (self.bin / 'x-terminal-emulator').chmod(0o755)
        result = self.run_script(SHOW, 'a', 'b-2', VIS_SESSIONS='a b-2', DISPLAY=':0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('shown: a\n', result.stdout)
        self.assertIn('shown: b-2\n', result.stdout)
        # One window per session; native Windows hands the stub tmux's path in its own form.
        launches = sorted(self.log('x-terminal-emulator').splitlines())
        self.assertEqual(len(launches), 2, launches)
        for line, n in zip(launches, ('a', 'b-2')):
            self.assertRegex(line, r"^\['-e', '[^']*/bin/tmux', 'attach', '-t', '=%s'\]$" % n)
        for f in self.state.glob('attached-*'):
            f.unlink()
        (self.state / 'x-terminal-emulator.log').unlink()
        result = self.run_script(SHOW, 'a', VIS_SESSIONS='a')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('attach by hand: tmux attach -t a\n', result.stdout)
        self.assertEqual(self.log('x-terminal-emulator'), '')

    def test_a_launcher_that_hangs_is_bounded(self):
        start = time.monotonic()
        result = self.run_script(SHOW, 'a', VIS_MODE='hang', **self.WSL)
        self.assertLess(time.monotonic() - start, 20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('did not return within 5 s', result.stdout)
        self.assertIn('attach by hand: tmux attach -t a', result.stdout)


class WatchTests(Base):
    def test_legacy_idle_does_not_hide_a_current_wait(self):
        workers = self.cwd / '.myagentkit/workers'
        workers.mkdir(parents=True)
        legacy = workers / 'w1.state'
        legacy.write_bytes(b'waiting input 2026-10-12T10:00:00\n')
        (workers / 'w2.state').write_bytes(b'waiting permission 2026-10-13T10:00:00 2\n')
        result = self.watch('--once', 'w1', 'w2', VIS_UNAME='MINGW64_NT-10.0')
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)
        self.assertNotIn('WAITING: w1', result.stdout)
        self.assertNotIn('IDLE: w1', result.stdout)
        self.assertIn('WAITING: w2, on a permission prompt', result.stdout)
        self.assertEqual(result.stdout.count('w1: its state hook is from an older kit'), 1)
        self.assertIn('re-spawn to install the current one', result.stdout)
        self.assertFalse((workers / 'w1.watch-state').exists())
        self.assertEqual(self.watch('--once', 'w1', 'w2', VIS_UNAME='MINGW64_NT-10.0').stdout, '')
        legacy.write_bytes(b'waiting input 2026-10-13T10:00:01 3\n')
        result = self.watch('--once', 'w1', 'w2', VIS_UNAME='MINGW64_NT-10.0')
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)
        self.assertEqual(result.stdout, '')

    def test_nul_only_state_is_an_observation_failure(self):
        workers = self.cwd / '.myagentkit/workers'
        workers.mkdir(parents=True)
        state = workers / 'w1.state'
        state.write_bytes(b'')
        result = self.watch('--once', 'w1', VIS_UNAME='MINGW64_NT-10.0')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        state.write_bytes(b'\x00\x00')
        result = self.watch('--once', 'w1', VIS_UNAME='MINGW64_NT-10.0')
        self.assertEqual((result.returncode, result.stdout), (3, ''), result.stderr)
        self.assertIn('state unreadable: invalid state content', result.stderr)
        self.assertIn('w1.state', result.stderr)
        self.assertFalse((workers / 'w1.watch-state').exists())

    def watch(self, *args, pane='idle.txt', **extra):
        extra.setdefault('VIS_SESSIONS', 'w1')
        return self.run_script(WATCH, *args, VIS_PANE=str(PANES / pane), **extra)

    def test_a_gone_session_is_reported(self):
        self.tmux_record('gone')
        for args in (('--once', 'w1', 'gone'), ('w1', 'gone')):
            with self.subTest(args=args):
                result = self.watch(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('GONE: gone', result.stdout)
                self.assertNotIn('w1', result.stdout.replace('GONE: gone', ''))

    def test_every_real_dialog_capture_is_waiting_with_the_session_named(self):
        # LC_ALL=C too: there `cut -c` counts bytes (and in every locale on coreutils before
        # 9.8), and a cut through a box-drawing character printed bytes that are not UTF-8.
        # text=True decodes strictly: the pane lines must come back cut on a character boundary.
        for pane, what in DIALOGS.items():
            for locale in ({}, {'LC_ALL': 'C', 'LANG': 'C'}):
                with self.subTest(pane=pane, locale=locale):
                    result = self.watch('w1', pane=pane, **locale)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('WAITING: w1, on %s (rule VERIFIED, Claude Code 2.1.285)' % what,
                                  result.stdout)
                    self.assertIn('  | ', result.stdout)
                    longest = max(len(line.encode()) for line in result.stdout.splitlines())
                    self.assertLessEqual(longest, len('  | ') + 200)

    def test_working_and_idle_panes_give_nothing(self):
        # quoted-output.txt: the worker's OUTPUT quotes a permission prompt and a question's
        # key hint higher up; a phrase match anywhere called that waiting.
        for pane in WORKING:
            with self.subTest(pane=pane):
                result = self.watch('--once', 'w1', pane=pane)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

    def test_a_failed_capture_is_an_observation_failure_never_idle(self):
        # The session exists but its pane cannot be read: the empty capture read as idle, and
        # a permission prompt nobody could see was reported as nothing waiting.
        for args in (('--once', 'w1'), ('--max-minutes', '0', 'w1')):
            with self.subTest(args=args):
                result = self.watch(*args, VIS_CAPTURE_FAIL='1')
                self.assertEqual(result.returncode, 3, result.stdout)
                self.assertIn("watch_workers: w1: capture failed: can't find pane: w1", result.stderr)
                self.assertEqual(result.stdout, '')

    def test_a_session_that_ended_during_the_capture_is_gone_not_a_failure(self):
        result = self.watch('--once', 'w1', VIS_CAPTURE_FAIL='ended')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'watch_workers: GONE: w1 (the tmux session no longer exists: '
                         'read its result file)\n')
        self.assertEqual(result.stderr, '')

    def test_a_tmux_that_cannot_answer_is_not_proof_of_absence(self):
        # Only the wordings for an absent session or server mean GONE; a socket tmux cannot
        # read may still hold the session: after a failed capture, and before any capture.
        denied = 'error connecting to /tmp/tmux-1000/default (Permission denied)'
        for before in (False, True):
            with self.subTest(before=before):
                if before:
                    (self.state / 'denied-w1').touch()
                result = self.watch('--once', 'w1', VIS_CAPTURE_FAIL='denied')
                self.assertEqual(result.returncode, 3, result.stdout)
                self.assertNotIn('GONE', result.stdout)
                self.assertIn('watch_workers: w1: capture failed: ', result.stderr)
                # After a failed capture the retry's words are the reason, not the capture's.
                self.assertIn(denied, result.stderr)
                self.assertNotIn("can't find pane", result.stderr)

    def test_the_absence_wordings_are_those_of_close_worker(self):
        lists = []
        for script in (WATCH, SCRIPTS / 'close_worker.sh'):
            lines = [line.strip() for line in script.read_text(encoding='utf-8').splitlines() if line.strip().endswith(') return 1 ;;')]
            lists.append(lines)
        self.assertEqual(len(lists[0]), 2, lists)
        self.assertEqual(lists[0], lists[1])

    def test_a_newline_in_a_name_or_a_result_mapping_is_refused(self):
        # The mappings are joined by newlines: `w1=docs/a<LF>w1=docs/b.md` announced docs/b.md.
        for args in (('--result', 'w1=docs/a\nw1=docs/b.md', 'w1'), ('w1\nw2',)):
            with self.subTest(args=args):
                result = self.watch('--once', *args)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn('contains a control character or a newline', result.stderr)
                self.assertEqual(result.stdout, '')

    def test_the_watch_window_ends_quietly(self):
        result = self.watch('--max-minutes', '0', 'w1', pane='working.txt')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'watch_workers: nothing was waiting on a person within 0 minute(s): w1\n')

    def test_it_sleeps_the_interval_then_reports_what_changed(self):
        sleeper = self.tmp / 'sleeper'
        sleeper.mkdir()
        (sleeper / 'sleep').write_text('#!/bin/sh\necho "$1" >> "$VIS_STATE/slept"\n')
        (sleeper / 'sleep').chmod(0o755)
        result = self.watch('w1', pane='working.txt', path_first=[sleeper],
                            VIS_PANE_LATER=str(PANES / 'permission.txt'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / 'slept').read_text(), '45\n')
        self.assertIn('WAITING: w1, on a permission prompt', result.stdout)

    def test_the_interval_has_a_floor(self):
        result = self.watch('--interval', '9', 'w1')
        self.assertEqual(result.returncode, 2)
        self.assertIn('floor of 10 seconds', result.stderr)
        result = self.watch('--interval', '10', '--max-minutes', '0', 'w1')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_control_byte_from_the_pane_is_printed(self):
        lines = (PANES / 'permission.txt').read_bytes().split(b'\n')
        at = max(i for i, line in enumerate(lines) if b'Do you want' in line)
        lines[at] = b'\x1b[31m Do you want\x07 to proceed?\r\x1b]0;title\x07'
        pane = self.tmp / 'pane.txt'
        pane.write_bytes(b'\n'.join(lines))
        result = self.run_script(WATCH, 'w1', VIS_SESSIONS='w1', VIS_PANE=str(pane))
        self.assertIn('WAITING: w1, on a permission prompt', result.stdout)
        self.assertIn('Do you want to proceed?', result.stdout)
        self.assertIsNone(re.search(r'[\x00-\x09\x0b-\x1f\x7f]', result.stdout + result.stderr))

    def test_the_other_question_hints_are_a_question(self):
        # The several-questions and editor forms of the hint, read from the 2.1.302 bundle, so
        # written here: tests/fixtures/panes holds real captures only (#237).
        for hint in ('Enter to select · Tab/Arrow keys to navigate · Esc to cancel',
                     'Enter to select · ↑/↓ to navigate · ctrl+g to edit in Vim · Esc to cancel'):
            with self.subTest(hint=hint):
                pane = self.tmp / 'pane.txt'
                pane.write_text(' Which name?\n\n❯ 1. Keep it\n  2. Rename it\n  3. Type something.\n\n'
                                + hint + '\n', encoding='utf-8')
                result = self.run_script(WATCH, '--once', 'w1', VIS_SESSIONS='w1', VIS_PANE=str(pane))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('WAITING: w1, on a question (rule UNVERIFIED, Claude Code 2.1.302)', result.stdout)

    def test_idle_says_the_worker_may_be_parked_on_its_own_background_job(self):
        # The Stop hook writes idle at every turn end, a park on a background job too (#186).
        workers = self.cwd / '.myagentkit/workers'
        workers.mkdir(parents=True)
        (workers / 'w1.state').write_bytes(b'idle 2026-10-18T10:00:00 1\n')
        result = self.watch('--once', 'w1', VIS_UNAME='MINGW64_NT-10.0')
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)
        self.assertEqual(result.stdout.splitlines()[0],
                         'watch_workers: IDLE: w1, its session stopped: a question in its tab, a usage limit or '
                         'an error, or a park on its own background job (it goes on by itself when the job ends), '
                         'with no new result report (its state file: idle 2026-10-18T10:00:00 1)')

    def test_a_windows_worker_whose_supervisor_ended_is_gone_once(self):
        # Its exit record, or its .live record whose lock dropped (a closed tab, a kill) (#185).
        workers = self.cwd / '.myagentkit/workers'
        workers.mkdir(parents=True)
        win = dict(VIS_UNAME='MINGW64_NT-10.0')
        live = workers / 'w1.live'
        live.write_bytes(b'123\n')
        # Held as codex_worker.py's supervisor holds it: nothing to report.
        hold = ('import importlib.util, os, sys, time\nfrom pathlib import Path\n'
                'spec = importlib.util.spec_from_file_location("cw", sys.argv[1])\n'
                'cw = importlib.util.module_from_spec(spec); spec.loader.exec_module(cw)\n'
                'cw.lock(cw.shared_open(Path(sys.argv[2]), os.O_RDWR)); print("locked", flush=True); time.sleep(60)\n')
        helper = subprocess.Popen([sys.executable, '-c', hold, str(SCRIPTS / 'codex_worker.py'), str(live)],
                                  stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(helper.stdout.readline(), 'locked\n')
            result = self.watch('--once', 'w1', **win)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        finally:
            helper.kill()
            helper.wait()
            helper.stdout.close()
        dropped = ('watch_workers: GONE: w1, its supervisor ended without an exit record (its tab closed or it '
                   'was killed): read its result file\n')
        self.assertEqual(self.watch('--once', 'w1', **win).stdout, dropped)
        self.assertEqual(self.watch('--once', 'w1', **win).stdout, '')
        (workers / 'w1.exit').write_text('claude exited 1 at 2026-10-18T10:00:00\n')
        result = self.watch('--once', 'w1', **win)
        self.assertEqual((result.returncode, result.stdout), (0, 'watch_workers: GONE: w1, its session ended '
                         '(claude exited 1 at 2026-10-18T10:00:00): read its result file\n'), result.stderr)
        self.assertEqual(self.watch('--once', 'w1', **win).stdout, '')

    def test_the_default_window_is_55_minutes(self):
        # Under the one-hour prompt cache: a quiet window's wake reads the lead's cache (#187).
        # `date` gives the start, then one second past 55 minutes, then past 110.
        clock = self.tmp / 'clock'
        clock.mkdir()
        (clock / 'date').write_text('#!/bin/sh\nn=$(cat "$VIS_STATE/dates" 2>/dev/null || echo 0)\n'
                                    'echo $((n + 1)) >"$VIS_STATE/dates"\n'
                                    'case $n in 0) echo 1000 ;; 1) echo 4301 ;; *) echo 7601 ;; esac\n')
        (clock / 'sleep').write_text('#!/bin/sh\n:\n')
        for stub in ('date', 'sleep'):
            (clock / stub).chmod(0o755)
        result = self.watch('w1', pane='working.txt', path_first=[clock])
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)
        self.assertEqual(result.stdout, 'watch_workers: nothing was waiting on a person within 55 minute(s): w1\n')

    def test_the_pattern_table_lists_every_rule_with_its_flag(self):
        result = self.run_script(WATCH, '--list-patterns')
        self.assertEqual(result.returncode, 0, result.stderr)
        rules = [line for line in (SCRIPTS / 'waiting_patterns.txt').read_text(encoding='utf-8').splitlines()
                 if line.strip() and not line.startswith('#')]
        self.assertEqual(len(result.stdout.splitlines()), len(rules) + 1)
        for rule in rules:
            self.assertRegex(rule.split()[1], '^(VERIFIED|UNVERIFIED)$')
            self.assertIn(rule, result.stdout)
        # A VERIFIED rule names the version its capture came from, and that capture is here.
        verified = [rule.split() for rule in rules if rule.split()[1] == 'VERIFIED']
        self.assertEqual({r[0] for r in verified}, {'trust', 'permission', 'question', 'context'})
        self.assertTrue(all(r[2] == '2.1.285' for r in verified))


HEAD = 'Kind: %s\nTask: T-7\nAttempt: 2\nRemaining: %s\n'
READY = '\n<!-- codex-worker: ready -->\n'
IDLE = ('watch_workers: IDLE: w1, its background session aaaa0001 is done with no new result report and its '
        'process still idles: a question in its view, a usage limit or an error, or a park on its own background '
        'job (it goes on by itself when the job ends): claude attach aaaa0001\n')
STATUS = '58k/1.0M'  # in the real status line of working-auto.txt


class ResultTests(Base):
    """The result file's head (docs/HANDOFF.md) is read once it is committed on a clean tree."""

    def setUp(self):
        super().setUp()
        self.git('init', '-q')
        self.git('commit', '-q', '--allow-empty', '-m', 'a')
        self.file = self.cwd / 'docs' / 'w1.md'
        self.file.parent.mkdir()

    def git(self, *args):
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *args], cwd=self.cwd,
                       check=True, capture_output=True)

    def commit(self, data):
        self.file.write_bytes(data if isinstance(data, bytes) else data.encode())
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'r')

    def watch(self, *args, **extra):
        return self.run_script(WATCH, '--once', '--result', 'w1=docs/w1.md', *args, 'w1',
                               VIS_SESSIONS='w1', VIS_PANE=str(PANES / 'working-auto.txt'), **extra)

    def test_each_kind_is_reported_and_only_completed_is_done(self):
        for kind, word in (('completed', 'DONE'), ('blocked', 'BLOCKED'), ('handoff', 'HANDOFF'),
                           ('progress', 'PROGRESS')):
            with self.subTest(kind=kind):
                self.commit(HEAD % (kind, 'none') + '\nbody\n')
                result = self.watch()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, 'watch_workers: %s: w1, task T-7, attempt 2, remaining: '
                                 'none (result file docs/w1.md)\n' % word)

    def test_a_gone_session_still_reports_its_result(self):
        # The supervisor ends a finished worker's session ten seconds after its result: the
        # next poll found it GONE and never read the result (#294).
        self.commit(HEAD % ('completed', 'none') + '\n<!-- codex-worker: ready -->\n')
        result = self.run_script(WATCH, '--once', '--result', 'w1=docs/w1.md', 'w1', VIS_SESSIONS='')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'watch_workers: GONE: w1 (the tmux session no longer exists: '
                         'read its result file)\nwatch_workers: DONE: w1, task T-7, attempt 2, remaining: '
                         'none (result file docs/w1.md)\n')

    def test_a_result_reported_while_live_is_not_reported_again_once_gone(self):
        # The once-marker lived on the tmux session only: once it ended, the same DONE came back
        # on every later run (#294). The marker file under .myagentkit/workers/ outlives it.
        (self.cwd / '.git' / 'info' / 'exclude').write_text('.myagentkit/\n')
        (self.cwd / '.myagentkit' / 'workers').mkdir(parents=True)
        self.tmux_record('w1')
        self.commit(HEAD % ('completed', 'none'))
        self.assertIn('DONE: w1', self.watch().stdout)
        result = self.run_script(WATCH, '--once', '--result', 'w1=docs/w1.md', 'w1', VIS_SESSIONS='')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'watch_workers: GONE: w1 (the tmux session no longer exists: '
                         'read its result file)\n')

    def test_a_result_counts_only_committed_on_a_clean_tree_and_once(self):
        self.file.write_text(HEAD % ('completed', 'none'))
        self.assertEqual(self.watch().stdout, '', 'an uncommitted file was read')
        self.commit(HEAD % ('completed', 'none'))
        (self.cwd / 'stray').write_text('x')
        self.assertEqual(self.watch().stdout, '', 'a dirty tree was read')
        (self.cwd / 'stray').unlink()
        self.assertIn('DONE: w1', self.watch().stdout)
        self.assertEqual(self.watch().stdout, '', 'the same version was reported twice')
        self.commit(HEAD % ('completed', 'none') + 'more\n')
        self.assertIn('DONE: w1', self.watch().stdout)

    def test_the_committed_blob_is_read_never_the_working_file(self):
        # A working file changed after the clean-tree check was read in place of the commit.
        # assume-unchanged hides the change from that check the same way, deterministically.
        self.commit(HEAD % ('progress', 'two steps'))
        self.git('update-index', '--assume-unchanged', 'docs/w1.md')
        self.file.write_text(HEAD % ('completed', 'none'))
        out = self.watch().stdout
        self.assertEqual(out, 'watch_workers: PROGRESS: w1, task T-7, attempt 2, remaining: two steps '
                         '(result file docs/w1.md)\n')

    def test_a_committed_symlink_is_never_a_result(self):
        # A committed link to a report outside the tree passed `-f` and the clean-tree check.
        outside = self.tmp / 'outside.md'
        outside.write_text(HEAD % ('completed', 'none'))
        self.file.symlink_to(outside)
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'r')
        out = self.watch().stdout
        self.assertEqual(out, 'watch_workers: MALFORMED: w1, result file docs/w1.md: it is not a regular file '
                         'in HEAD (mode 120000); not done\n')

    def git_wrapper(self, body):
        # A `git` first on PATH: `body` runs before the real git, with $real naming it.
        folder = self.tmp / 'gitwrap'
        folder.mkdir()
        real = shutil.which('git')
        (folder / 'git').write_text('#!/bin/sh\nreal=%s\nst=%s\n%s\nexec "$real" "$@"\n'
                                    % (shq(real), shq(str(self.state)), body))
        (folder / 'git').chmod(0o755)
        return [folder]

    def test_a_failed_blob_read_is_read_again_on_the_next_run(self):
        # The once-marker was stored before the read: one failed `cat-file` hid the result forever.
        self.commit(HEAD % ('completed', 'none'))
        first = self.git_wrapper('case " $* " in *" cat-file "*) [ -e "$st/catfailed" ] || '
                                 '{ : >"$st/catfailed"; echo "fatal: cannot read" >&2; exit 128; } ;; esac')
        result = self.watch(path_first=first)
        self.assertEqual((result.returncode, result.stdout), (3, ''), 'a failed read was reported')
        self.assertIn('DONE: w1', self.watch(path_first=first).stdout)

    def test_a_tree_that_cannot_be_read_ends_the_run_like_a_failed_capture(self):
        self.commit(HEAD % ('completed', 'none'))
        always = self.git_wrapper('case " $* " in *" ls-tree "*) echo "fatal: bad tree" >&2; exit 128 ;; esac')
        for _ in range(2):
            result = self.watch(path_first=always)
            self.assertEqual((result.returncode, result.stdout), (3, ''))
            self.assertIn('could not read the tree of', result.stderr)
            self.assertIn('fatal: bad tree', result.stderr)
        self.assertIn('DONE: w1', self.watch().stdout)

    def test_a_blob_that_cannot_be_read_ends_the_run_like_a_failed_capture(self):
        self.commit(HEAD % ('completed', 'none'))
        blob = subprocess.run(['git', 'rev-parse', 'HEAD:docs/w1.md'], cwd=self.cwd, capture_output=True,
                              text=True, check=True).stdout.strip()
        always = self.git_wrapper('case " $* " in *" cat-file "*) echo "fatal: cannot read" >&2; exit 128 ;; esac')
        for _ in range(2):
            result = self.watch(path_first=always)
            self.assertEqual((result.returncode, result.stdout), (3, ''))
            self.assertEqual(result.stderr, 'watch_workers: w1: could not read the committed result %s: '
                             'fatal: cannot read \n' % blob)

    def test_a_failed_capture_of_one_session_consumes_no_result_of_another(self):
        # A run that exits 3 is rerun: a DONE it printed, with its marker stored, was lost.
        self.commit(HEAD % ('completed', 'none'))
        args = ('--once', '--result', 'w2=docs/w1.md', 'w1', 'w2')
        env = dict(VIS_SESSIONS='w1 w2', VIS_PANE=str(PANES / 'working-auto.txt'))
        result = self.run_script(WATCH, *args, VIS_CAPTURE_FAIL='1', VIS_CAPTURE_FAIL_FOR='w1', **env)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertNotIn('DONE', result.stdout)
        self.assertIn('watch_workers: w1: capture failed', result.stderr)
        result = self.run_script(WATCH, *args, **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('watch_workers: DONE: w2, task T-7', result.stdout)

    def test_a_head_that_moves_during_the_check_reports_nothing(self):
        # The entry was read at one commit and the tree's cleanliness at the next: an obsolete
        # completion was reported after a progress result had replaced it.
        self.commit(HEAD % ('completed', 'none'))
        first = self.git_wrapper(
            'case " $* " in *" status "*) [ -e "$st/moved" ] || { : >"$st/moved"; '
            'printf "Kind: progress\\nTask: T-7\\nAttempt: 2\\nRemaining: more\\n" >docs/w1.md; '
            '"$real" -c user.name=t -c user.email=t@t commit -q -m p -- docs/w1.md; } ;; esac')
        self.assertEqual(self.watch(path_first=first).stdout, '', 'a result of an older commit was reported')
        self.assertIn('PROGRESS: w1', self.watch(path_first=first).stdout)

    def test_a_session_named_twice_is_reported_once(self):
        # The once-marker is stored after the run: the second name read none and reported again.
        self.commit(HEAD % ('completed', 'none'))
        result = self.watch('w1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('DONE: w1'), 1, result.stdout)

    def test_a_report_that_cannot_be_written_ends_the_run_and_is_written_again(self):
        # A failed write into the report buffer returned success and stored the once-marker
        # of a report nobody saw; it ends the run like a failed capture.
        self.commit(HEAD % ('completed', 'none'))
        result = self.watch(path_first=self.full_buffer())
        self.assertEqual((result.returncode, result.stdout), (3, ''), result.stderr)
        self.assertIn('watch_workers: w1: could not write its report: ', result.stderr)
        self.assertIn('DONE: w1', self.watch().stdout)

    def test_a_failed_write_of_the_questions_buffer_is_rerun(self):
        # The questions' buffer failed unseen: the run reported DONE, stored the marker, and
        # the questions were never asked.
        self.commit(HEAD % ('completed', 'none') + '\n## Open questions for Ada\n1. Approve?\n')
        result = self.watch(path_first=self.failing_tr('[ "$1" = -d ]'))
        self.assertEqual((result.returncode, result.stdout), (3, ''), result.stderr)
        self.assertIn('watch_workers: w1: could not write its report: ', result.stderr)
        self.assertIn('QUESTIONS: w1, 1 question for Ada', self.watch().stdout)

    def test_a_failed_write_of_the_question_lines_is_rerun(self):
        self.commit(HEAD % ('completed', 'none') + '\n## Open questions for Ada\n1. Approve?\n')
        result = self.watch(path_first=self.failing_tr('case $in in "  | "*) true ;; *) false ;; esac'))
        self.assertEqual((result.returncode, result.stdout), (3, ''), result.stderr)
        self.assertIn('watch_workers: w1: could not write its report: ', result.stderr)
        self.assertIn('  | 1. Approve?', self.watch().stdout)

    def test_a_report_that_stdout_refuses_exits_3(self):
        if not HAS_DEV_FULL:
            self.skipTest('no /dev/full on this host: a report refused by stdout is not tested')
        self.tmux_record('w1')
        self.commit(HEAD % ('completed', 'none'))
        for sessions, pane, word in (('w1', 'working-auto.txt', 'DONE'), ('', 'working-auto.txt', 'GONE'),
                                     ('w1', 'permission.txt', 'WAITING')):
            with self.subTest(word=word):
                result = self.run_script(WATCH, '--once', '--result', 'w1=docs/w1.md', 'w1', stdout=DEV_FULL,
                                         VIS_SESSIONS=sessions, VIS_PANE=str(PANES / pane))
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertIn('could not write its report', result.stderr)
        self.assertIn('DONE: w1', self.watch().stdout, 'the refused report was marked as said')
    test_a_report_that_stdout_refuses_exits_3._kit_platform_skip = not HAS_DEV_FULL

    def test_a_failed_write_of_the_waiting_pane_lines_exits_3(self):
        # Only the pane lines fail: the lines around them were written.
        with open(self.tmp / 'stdout', 'w') as out:
            result = self.run_script(WATCH, '--once', 'w1', stdout=out, VIS_SESSIONS='w1',
                                     VIS_PANE=str(PANES / 'permission.txt'),
                                     path_first=self.failing_tr('case $in in "  | "*) true ;; *) false ;; esac'))
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn('watch_workers: w1: could not write its report', result.stderr)

    def test_the_watcher_restarted_after_progress_reaches_done(self):
        # The lead restarts the watcher after every report but DONE and GONE while work
        # remains: the second run, after a PROGRESS report, still reports the completion.
        self.commit(HEAD % ('progress', 'two steps'))
        self.assertIn('PROGRESS: w1', self.watch().stdout)
        self.commit(HEAD % ('completed', 'none'))
        result = self.run_script(WATCH, '--max-minutes', '1', '--result', 'w1=docs/w1.md', 'w1',
                                 VIS_SESSIONS='w1', VIS_PANE=str(PANES / 'working-auto.txt'))
        self.assertTrue(result.stdout.startswith('watch_workers: DONE: w1'), result.stdout)

    def test_an_uncommitted_default_result_of_this_run_is_read_once(self):
        # The kit's default RESULT-NAME.md is never committed (#167): it is read from the working
        # file once this run published it, newer than NAME.result-path and with the ready marker.
        workers = self.cwd / '.myagentkit/workers'
        workers.mkdir(parents=True)
        start = workers / 'w1.result-path'
        start.write_text('RESULT-w1.md\n')
        then = time.time() - 60
        os.utime(start, (then, then))
        report, outside = self.cwd / 'RESULT-w1.md', self.tmp / 'outside.md'
        ready = (HEAD % ('completed', 'none') + '\nbody\n<!-- codex-worker: ready -->\r\n\n').encode()
        done = 'watch_workers: DONE: w1, task T-7, attempt 2, remaining: none (result file RESULT-w1.md)\n'
        for platform in ({}, {'VIS_UNAME': 'MINGW64_NT-10.0'}):
            with self.subTest(platform=platform):
                for f in [*workers.glob('w1.watch-*'), *self.state.glob('opt-*'), report]:
                    f.unlink(missing_ok=True)
                watch = lambda: self.run_script(WATCH, '--once', '--result', 'w1=RESULT-w1.md', 'w1', VIS_SESSIONS='w1',
                                                VIS_PANE=str(PANES / 'working-auto.txt'), **platform)
                report.write_text(HEAD % ('completed', 'none'))
                self.assertEqual(watch().stdout, '', 'a result without the ready marker was read')
                report.write_bytes(ready)
                os.utime(report, (then - 30, then - 30))
                self.assertEqual(watch().stdout, '', "an earlier run's result was read")
                report.unlink()
                outside.write_bytes(ready)
                report.symlink_to(outside)
                self.assertEqual(watch().stdout, '', 'a symlink was read')
                report.unlink()
                report.write_bytes(ready)
                if platform:  # its stop wrote idle: the result is reported instead of IDLE
                    (workers / 'w1.state').write_bytes(b'idle 2026-10-18T10:00:00 1\n')
                result = watch()
                self.assertEqual((result.returncode, result.stdout), (0, done), result.stderr)
                if not platform:
                    self.assertEqual(watch().stdout, '', 'the same result was reported twice')

    def elsewhere(self):
        # 2026-10-21: a worker spawned inside its worktree keeps its records there; watched from
        # the main checkout it found none and said nothing, forever, while its result was ready.
        other = self.tmp / 'wt-w1'
        self.git('worktree', 'add', '-q', str(other))
        (other / '.myagentkit/workers').mkdir(parents=True)
        (other / '.myagentkit/workers/w1.result-path').write_text('RESULT-w1.md\n')
        return other

    def test_a_name_with_no_record_here_and_no_session_is_a_usage_error(self):
        self.elsewhere()
        # tmux saying "no such session" proves nothing for a name spawned elsewhere (a bg worker).
        for platform in ({'VIS_UNAME': 'MINGW64_NT-10.0'}, {'VIS_SESSIONS': ''}):
            for args in (('--once',), ('--interval', '10', '--max-minutes', '0')):
                with self.subTest(platform=platform, args=args):
                    result = self.run_script(WATCH, *args, 'w1', **platform)
                    self.assertEqual((result.returncode, result.stdout), (2, ''), result.stderr)
                    self.assertIn('w1: no record of it in ', result.stderr)
                    self.assertIn('/.myagentkit/workers and no session of that name: run the watch from the '
                                  'checkout it was spawned in (', result.stderr)
                    self.assertIn('/wt-w1)', result.stderr)

    def test_an_explicit_ready_result_wins_with_no_record_here(self):
        report = self.elsewhere() / 'RESULT-w1.md'
        report.write_text(HEAD % ('completed', 'none') + '\n<!-- codex-worker: ready -->\n')
        path = posix(report)
        done = 'watch_workers: DONE: w1, task T-7, attempt 2, remaining: none (result file %s)\n' % path
        for platform, out in (({'VIS_UNAME': 'MINGW64_NT-10.0'}, done),
                              ({'VIS_SESSIONS': ''}, 'watch_workers: GONE: w1 (the tmux session no longer '
                               'exists: read its result file)\n' + done)):
            with self.subTest(platform=platform):
                result = self.run_script(WATCH, '--once', '--result', 'w1=' + path, 'w1', **platform)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, out, ''))

    def published(self, data):
        # An uncommitted docs/w1.md this run published: newer than NAME.result-path.
        start = self.cwd / '.myagentkit/workers/w1.result-path'
        start.parent.mkdir(parents=True, exist_ok=True)
        start.write_text('docs/w1.md\n')
        then = time.time() - 60
        os.utime(start, (then, then))
        self.file.write_bytes(data)

    def test_a_bom_result_is_done_as_codex_worker_reads_it(self):
        # A UTF-8 BOM (PowerShell 5.1 Set-Content -Encoding UTF8) was MALFORMED here but DONE
        # for codex_worker.py; both the working file and the committed blob are read the same way.
        done = 'watch_workers: DONE: w1, task T-7, attempt 2, remaining: none (result file docs/w1.md)\n'
        data = b'\xef\xbb\xbf' + (HEAD % ('completed', 'none') + '\n<!-- codex-worker: ready -->\n').encode()
        self.published(data)
        self.assertEqual(self.watch().stdout, done, 'the uncommitted BOM result')
        self.commit(data + b'more\n')
        self.assertEqual(self.watch().stdout, done, 'the committed BOM result')

    def test_a_crlf_result_committed_later_is_not_reported_again(self):
        # Under core.autocrlf=true the committed blob is LF: the once-marker of the uncommitted
        # CRLF file must be the blob git stores, or the commit reports the same result twice.
        self.git('config', 'core.autocrlf', 'true')
        data = (HEAD % ('completed', 'none') + '\n<!-- codex-worker: ready -->\n').replace('\n', '\r\n').encode()
        self.published(data)
        self.assertIn('DONE: w1', self.watch().stdout)
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'r')
        self.assertEqual(self.watch().stdout, '', 'the same result was reported again after its commit')

    def test_a_malformed_head_is_never_done(self):
        for head, why in (('', 'line 1'), ('Kind: finished\nTask: T\nAttempt: 1\nRemaining: none\n', 'line 1'),
                          ('# Result\n' + HEAD % ('completed', 'none'), 'line 1'),
                          ('Kind: completed\nTask: \nAttempt: 1\nRemaining: none\n', 'line 2'),
                          ('Kind: completed\nTask: T\nAttempt: two\nRemaining: none\n', 'line 3'),
                          ('Kind: completed\nTask: T\nAttempt: 1\n\nbody\n', 'line 4')):
            with self.subTest(head=head):
                self.commit(head + 'x\n')
                out = self.watch().stdout
                self.assertTrue(out.startswith('watch_workers: MALFORMED: w1, result file docs/w1.md: ' + why), out)
                self.assertIn('not done', out)
                self.assertNotIn('DONE', out)

    def test_open_questions_are_reported_first_with_their_text(self):
        long = 'Qq' + 'ü' * 300 + '?'
        body = (HEAD % ('progress', 'two steps') + '\nbody\n\n## Open questions for Ada\n\n'
                '1. Keep the old name?\n   a) yes\n   b) no, rename it\n'
                '2. Which default?\n   a) über-safe \u2014 slower\n   b) fast\n'
                '3. ' + long + '\n   a) yes\x1b[2J\n\n## Not run / not verified\n\nnone\n')
        for locale in ({}, {'LC_ALL': 'C', 'LANG': 'C'}):
            with self.subTest(locale=locale):
                self.commit(body + str(locale))
                result = self.watch(**locale)
                lines = result.stdout.splitlines()
                self.assertEqual(lines[0], 'watch_workers: QUESTIONS: w1, 3 questions for Ada (Kind: progress, '
                                 'task T-7, attempt 2, remaining: two steps)')
                for text in ('  | 1. Keep the old name?', '  |    b) no, rename it', '  | 2. Which default?',
                             '  |    a) über-safe \u2014 slower', '  |    a) yes[2J'):
                    self.assertIn(text, lines)
                third = [line for line in lines if line.startswith('  | 3. ')][0]
                self.assertTrue(long.startswith(third[len('  | 3. '):]), third)
                self.assertLessEqual(len(third.encode()), len('  | ') + 200)
                self.assertNotIn('none', result.stdout.replace('Not run', ''))
                self.assertIsNone(re.search(r'[\x00-\x09\x0b-\x1f\x7f]', result.stdout))

    def test_the_result_lookup_parses_in_bash_3_2(self):
        # macOS's sh, bash 3.2, refused the lookup's `case` inside $( ), which every shell the
        # kit's `sh -n` ran here accepted: the kit's own check finds that construct.
        spec = importlib.util.spec_from_file_location('kit_check', ROOT / 'scripts/check_kit.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        self.assertEqual(gate.case_in_substitution(WATCH.read_text(encoding='utf-8')), [])
        before = ('result() {\n  f=$(printf \'%s\\n\' "$results" | while IFS= read -r r; do\n'
                  '    case $r in "$1="*) printf \'%s\\n\' "${r#"$1="}" ;; esac\n  done | tail -n 1)\n}\n')
        self.assertEqual(gate.case_in_substitution(before), [3])
        # Quoted, commented or in a here-document, the word is not a `case`.
        self.assertEqual(gate.case_in_substitution('x=$(echo "case a" \'case b\') # $( case\n'
                                                   'cat <<-E\n\t$(case\n\tE\n'), [])
        # An argument is not a command: `case` counts only where a command starts.
        self.assertEqual(gate.case_in_substitution('x=$(echo case value)\n'), [])
        self.assertEqual(gate.case_in_substitution('x=$(true && case a in a) :;; esac)\n'), [1])
        self.assertEqual(gate.case_in_substitution('x=$(if :; then case a in a) :;; esac; fi)\n'), [1])
        # The shell parser recognizes arguments even after reserved words or substitutions.
        for text in ('x=$(echo if case value)\n', 'x=$(echo time case a)\n', 'x=$(echo ! case a)\n',
                     'x=$(echo then do case a)\n', 'x=$(echo $(x) case a)\n'):
            with self.subTest(text=text):
                self.assertEqual(gate.case_in_substitution(text), [])
        for text in ('x=$(echo case value)\n', 'x=$(printf case)\n', 'x=$(printf \\\n  case a)\n'):
            with self.subTest(text=text):
                self.assertEqual(gate.case_in_substitution(text), [])
        self.assertEqual(gate.case_in_substitution('x=$(if ! case a in a) :;; esac; then :; fi)\n'), [1])
        self.assertEqual(gate.case_in_substitution('x=$(\n  time case a in a) :;; esac)\n'), [2])
        # Every keyword after which a command starts, each in a command that parses.
        for start, end in (('if', '; then :; fi'), ('while', '; do :; done'), ('until', '; do :; done'),
                           ('!', ''), ('time', ''), ('if :; then :; elif', '; then :; fi'),
                           ('if :; then', '; fi'), ('while :; do', '; done'), ('if :; then :; else', '; fi')):
            with self.subTest(start=start):
                self.assertEqual(gate.case_in_substitution('x=$(%s case a in a) :;; esac%s)\n' % (start, end)),
                                 [1])
        # A $( ) inside $(( )) is still a substitution, and its `case` still counts.
        self.assertEqual(gate.case_in_substitution('n=$(( $(case a in a) echo 1;; esac) + 1 ))\n'), [1])
        self.assertEqual(gate.case_in_substitution('n=$(( (1 << 2) + $(echo 1) ))\nf=$(case x in x) :;; esac)\n'),
                         [2])
        # A shift in $(( )) is not a here-document: the next line is still read.
        self.assertEqual(gate.case_in_substitution('n=$((1 << 2)) m="$((n << 1))"\n'
                                                   'f=$(case x in x) echo ok;; esac)\n'), [2])

    def test_a_keyword_after_a_closed_group_or_a_loop_name_opens_a_command(self):
        # These `case`s are commands, and the lint missed them: a keyword after `)` or `}`, and
        # `do` after `for NAME [in WORDS]`, are in command position.
        spec = importlib.util.spec_from_file_location('kit_check', ROOT / 'scripts/check_kit.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        # Each in a command that parses: a fixture bash rejects as it is raises (CaseLintTests).
        for start, end in (('if (:) then', '; fi'), ('if { :; } then', '; fi'), ('while (:) do', '; done'),
                           ('if :; then (:) else', '; fi'), ('for i do', '; done'), ('for i in a b; do', '; done'),
                           ('select i in a; do', '; done'), ('select i do', '; done')):
            with self.subTest(start=start):
                self.assertEqual(gate.case_in_substitution('x=$(%s case a in a) :;; esac%s)\n' % (start, end)),
                                 [1])
        # Every command form a grammar walk missed in review remains a finding.
        for start, end in (('if (:)then', '; fi'), ('if if :; then :; fi then', '; fi'),
                           ('while for i in a; do :; done do', '; done'), ('f()', ''), ('coproc', ''),
                           ('f() {', '; }')):
            with self.subTest(start=start):
                self.assertEqual(gate.case_in_substitution('x=$(%s case a in a) :;; esac%s)\n' % (start, end)),
                                 [1])

    def test_a_case_right_after_a_function_header_is_flagged(self):
        spec = importlib.util.spec_from_file_location('kit_check', ROOT / 'scripts/check_kit.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        self.assertEqual(gate.case_in_substitution('x=$(f()case a in a) :;; esac)\n'), [1])

    def test_a_word_that_contains_case_is_not_a_case(self):
        spec = importlib.util.spec_from_file_location('kit_check', ROOT / 'scripts/check_kit.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        for text in ("x=$(echo test-case value)\n", "x=$(cat dir/case a)\n", "x=$(echo a.case b)\n"):
            self.assertEqual(gate.case_in_substitution(text), [], text)

    def test_a_case_on_the_line_after_a_command_is_a_finding(self):
        spec = importlib.util.spec_from_file_location('kit_check', ROOT / 'scripts/check_kit.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        # A newline ends the command before it: `$(echo before\ncase ...)` is flagged.
        self.assertEqual(gate.case_in_substitution("x=$(echo before\ncase x in x) echo after;; esac)\n"), [2])
        self.assertEqual(gate.case_in_substitution("x=$(echo before \\\ncase x)\n"), [])
        # Continued, `case x in x)` is an argument whose `)` ends the $( ): bash rejects the file.
        with self.assertRaisesRegex(RuntimeError, "rejects the file as it is.*`;;'"):
            gate.case_in_substitution("x=$(echo before \\\ncase x in x) :;; esac)\n")

    def test_the_kit_check_rejects_a_case_inside_a_substitution(self):
        # The scan alone is not the gate: check_syntax must run it and stop on it.
        spec = importlib.util.spec_from_file_location('kit_check', ROOT / 'scripts/check_kit.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        (self.tmp / 'bad.sh').write_text('#!/bin/sh\nn=$((1 << 2))\nf=$(case x in x) echo ok;; esac)\n')
        # macOS's sh rejects the file itself; the named reason must still be the lint's. An `sh`
        # that fails every `-n` stands in for it, so every host sees what macOS sees.
        stub = self.tmp / 'stub-sh'
        stub.mkdir()
        (stub / 'sh').write_text('#!/bin/sh\necho "syntax error near unexpected token" >&2\nexit 2\n')
        (stub / 'sh').chmod(0o755)
        path = os.environ['PATH']
        os.environ['PATH'] = '%s%s%s' % (stub, os.pathsep, path)
        try:
            with self.assertRaisesRegex(RuntimeError, r'bad\.sh: `case` inside \$\( \) on line 3: bash 3\.2'):
                gate.check_syntax(self.tmp)
        finally:
            os.environ['PATH'] = path


class CaseLintTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('kit_check', ROOT / 'scripts/check_kit.py')
        self.gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.gate)

    def test_a_function_body_is_a_finding_and_an_arithmetic_looking_one_fails(self):
        self.assertEqual(self.gate.case_in_substitution('x=$(function f case a in a) :;; esac)\n'), [1])
        # In an arithmetic-looking $(( even bash 5.2 reads the pattern's `)` as the end: it fails.
        with self.assertRaisesRegex(RuntimeError, 'rejects the file as it is'):
            self.gate.case_in_substitution('x=$((:)then case a in a) :;; esac)\n')

    def test_reserved_option_and_substitution_arguments_are_not_findings(self):
        for text in ('x=$(echo if case value)\n', 'x=$(echo -n case)\n',
                     'x=$(echo $(x) case)\n', 'x=$(echo -n case value)\n',
                     'x=$(echo $(x) case value)\n'):
            with self.subTest(text=text):
                self.assertEqual(self.gate.case_in_substitution(text), [])
        self.assertEqual(self.gate.case_in_substitution('n=$((case + 1))\n'), [])

    def test_a_file_bash_rejects_fails_with_bashs_reason_not_a_case_finding(self):
        # A `then` without `if`, here or far from the argument `case`, is the reason; never the case.
        for text in ('x=$(echo case; then)\n', 'y=$(f; then case)\n', 'f() { :; }\nx=$(echo case)\nthen\n'):
            with self.subTest(text=text):
                with self.assertRaisesRegex(RuntimeError, "rejects the file as it is.*unexpected token `then'"):
                    self.gate.case_in_substitution(text)

    def test_a_localized_bash_version_is_accepted_but_4_4_is_rejected(self):
        with unittest.mock.patch.dict(os.environ, LC_ALL='es_ES.UTF-8', LANG='es_ES.UTF-8'), \
                unittest.mock.patch.object(self.gate.shutil, 'which', return_value='/stub/sh'):
            for version in ('5.2.15', '4.4.23'):
                self.gate.bash_5_2.cache_clear()
                banner = subprocess.CompletedProcess([], 0, 'GNU bash, versión %s(1)-release\n' % version, '')
                with self.subTest(version=version), \
                        unittest.mock.patch.object(self.gate.subprocess, 'run', return_value=banner) as probe:
                    if version.startswith('5.2'):
                        self.assertTrue(self.gate.bash_5_2())
                    else:
                        with self.assertRaisesRegex(RuntimeError, r'needs bash 5\.2 or later'):
                            self.gate.bash_5_2()
                    for call in probe.call_args_list:
                        self.assertEqual(call.args[0][1:], ['--version'])
                        self.assertEqual(call.kwargs['env']['LC_ALL'], 'C')
                        self.assertEqual(call.kwargs['env']['LANG'], 'C')
            self.assertEqual(os.environ['LC_ALL'], 'es_ES.UTF-8')
            self.assertEqual(os.environ['LANG'], 'es_ES.UTF-8')

    def test_a_french_syntax_diagnostic_is_reported_and_the_file_is_rejected(self):
        reason = "erreur de syntaxe près du symbole inattendu « then »"
        rejected = subprocess.CompletedProcess([], 2, b'', reason.encode('utf-8'))
        with unittest.mock.patch.dict(os.environ, LC_ALL='fr_FR.UTF-8', LANG='fr_FR.UTF-8'), \
                unittest.mock.patch.object(self.gate, 'bash_5_2', return_value='/stub/bash'), \
                unittest.mock.patch.object(self.gate.subprocess, 'run', return_value=rejected) as parser:
            with self.assertRaisesRegex(RuntimeError, 'bash --posix -n rejects the file as it is') as error:
                self.gate.case_in_substitution('x=$(echo case; then)\n')
            self.assertIn(reason, str(error.exception))
            parser.assert_called_once()
            self.assertEqual(parser.call_args.args[0], ['/stub/bash', '--posix', '-n'])
            self.assertEqual(parser.call_args.kwargs['env']['LC_ALL'], 'C')
            self.assertEqual(parser.call_args.kwargs['env']['LANG'], 'C')
            self.assertEqual(os.environ['LC_ALL'], 'fr_FR.UTF-8')
            self.assertEqual(os.environ['LANG'], 'fr_FR.UTF-8')

    def test_a_bash_that_cannot_start_or_is_too_old_fails_by_name(self):
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(self.gate, 'bash_5_2', return_value=os.path.join(tmp, 'no-bash')):
            with self.assertRaisesRegex(RuntimeError, 'cannot run .*no-bash --posix -n'):
                self.gate.case_in_substitution('x=$(echo case)\n')
        old = subprocess.CompletedProcess([], 0, 'GNU bash, version 3.2.57(1)-release\n', '')
        with unittest.mock.patch.object(self.gate.subprocess, 'run', return_value=old):
            with self.assertRaisesRegex(RuntimeError, r'needs bash 5\.2 or later \(macOS: brew install bash\); tried: '):
                self.gate.bash_5_2()
        # No candidate, no process: the lookup is not even reached.
        with unittest.mock.patch.object(self.gate, 'bash_5_2', side_effect=AssertionError('started bash')):
            self.assertEqual(self.gate.case_in_substitution('x=$(echo esac)\ncase a in a) :;; esac\n'), [])

    def test_the_lint_prerequisite_is_checked_even_when_no_file_needs_it(self):
        # bash_5_2() runs on every host before the first file: a missing bash fails the syntax
        # check on a tree whose scripts hold no `case` inside $( ) at all.
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'plain.sh').write_text('echo plain\n')
            with unittest.mock.patch.object(self.gate, 'bash_5_2', side_effect=RuntimeError('needs bash 5.2 or later')):
                with self.assertRaisesRegex(RuntimeError, r'needs bash 5\.2 or later'):
                    self.gate.check_syntax(Path(tmp))

    def test_every_kit_shell_script_passes_the_case_lint(self):
        for path in self.gate.repository_files(ROOT):
            if path.suffix.lower() == '.sh':
                with self.subTest(path=path.relative_to(ROOT)):
                    self.assertEqual(self.gate.case_in_substitution(path.read_text(encoding='utf-8')), [])

    def test_case_lint_ignores_worker_copies_but_rejects_a_kit_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root / '.gitignore').write_text('.claude/worktrees/\n', encoding='utf-8')
            kit = root / 'kit.sh'
            kit.write_text('#!/bin/sh\necho clean\n', encoding='utf-8')
            subprocess.run(['git', '-C', str(root), 'add', '.gitignore', 'kit.sh'], check=True)
            worker = root / '.claude/worktrees/stale/core/scripts/check.sh'
            worker.parent.mkdir(parents=True)
            bad = '#!/bin/sh\nx=$(case x in x) echo stale;; esac)\n'
            worker.write_text(bad, encoding='utf-8')
            # Invoke the same scan without an active unittest outcome, so its assertion
            # propagates to this test instead of being swallowed as a nested subtest.
            scan = type(self)('test_every_kit_shell_script_passes_the_case_lint')
            scan.gate = self.gate
            with unittest.mock.patch.dict(globals(), ROOT=root):
                scan.test_every_kit_shell_script_passes_the_case_lint()
                kit.write_text(bad, encoding='utf-8')
                with self.assertRaises(AssertionError):
                    scan.test_every_kit_shell_script_passes_the_case_lint()


class ContextTests(Base):
    """The context figure is read from the status line, past a warning line, once per session."""

    def watch(self, status, *args, drop=False, quote=None, after=(), path_first=()):
        text = (PANES / 'working-auto.txt').read_text(encoding='utf-8')
        self.assertIn(STATUS, text)
        lines = [line for line in text.replace(STATUS, status).splitlines() if not (drop and '│' in line)]
        lines = ([quote] if quote else []) + lines + list(after)
        pane = self.tmp / 'pane.txt'
        pane.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return self.run_script(WATCH, *args, 'w1', VIS_SESSIONS='w1', VIS_PANE=str(pane), LC_ALL='C',
                               path_first=path_first)

    def test_the_figure_is_reported_past_the_warning_line(self):
        # The line is the smaller of an absolute count (default 200k, the lead's band) and a
        # share of the window (default 50%): a bare number is a share, as before.
        for status, args, out, line in (
                ('58k/1.0M', ('--context-warn', '50'), '', ''),
                ('58k/1.0M', ('--context-warn', '5'), '58k/1.0M is 5%', '50k'),
                ('113k/1.0M', ('--context-warn', '50'), '', ''),
                ('113k/1.0M', ('--context-warn', '10%'), '113k/1.0M is 11%', '100k'),
                ('1.2M/1.0M', ('--context-warn', '50'), '1.2M/1.0M is 120%', '200k'),
                ('36k/200k', ('--context-warn', '17'), '36k/200k is 18%', '34k'),
                # The default: 200k on a 1M window (50% would be 500k, past the 400k ceiling),
                # half of a 200k window.
                ('250k/1.0M', (), '250k/1.0M is 25%', '200k'),
                ('120k/200k', (), '120k/200k is 60%', '100k'),
                ('190k/1.0M', (), '', ''),
                # An absolute line replaces the 200k; the share still applies.
                ('250k/1.0M', ('--context-warn', '300k'), '', ''),
                ('120k/1.0M', ('--context-warn', '100k'), '120k/1.0M is 12%', '100k'),
                ('120k/200k', ('--context-warn', '300k'), '120k/200k is 60%', '100k')):
            with self.subTest(status=status, args=args):
                for f in self.state.glob('opt-*'):
                    f.unlink()
                result = self.watch(status, '--once', *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                if out:
                    self.assertEqual(result.stdout, 'watch_workers: CONTEXT: w1, %s of its context window, past its '
                                     '%s warning line (finish, compact or hand off: read its Remaining: line; '
                                     'docs/WORKFLOW.md, "Worker cost", rule 8)\n' % (out, line))
                else:
                    self.assertEqual(result.stdout, '')

    def test_a_context_warning_value_is_a_count_or_a_share(self):
        for value in ('k', '%', '20x', '1.5k', '-3', ''):
            with self.subTest(value=value):
                result = self.watch(STATUS, '--once', '--context-warn', value)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('--context-warn takes NNNk (tokens) or NN% (of the window)', result.stderr)

    def test_a_leading_zero_is_decimal_not_octal(self):
        # Shell arithmetic reads 08 as a bad octal number and the script died after the value
        # had passed the digit check (Codex review of batch 6, finding 2).
        result = self.watch('120k/1.0M', '--once', '--context-warn', '080k')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('past its 80k warning line', result.stdout)
        for f in self.state.glob('opt-*'):
            f.unlink()
        result = self.watch('120k/1.0M', '--once', '--context-warn', '09%')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('past its 90k warning line', result.stdout)
        for args in (('--once', '--max-minutes', '08'), ('--max-minutes', '0', '--interval', '019')):
            with self.subTest(args=args):
                result = self.watch(STATUS, *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, '')

    def test_a_figure_in_the_output_is_not_the_status_line(self):
        # Output quoting `800k/1.0M` gave a false 80% warning and set the once-marker that
        # then hid a real warning. Only the status line's figure counts.
        quote = '  the report said 800k/1.0M of context was used'
        self.assertEqual(self.watch(STATUS, '--once', quote=quote).stdout, '')
        result = self.watch('', '--max-minutes', '0', quote=quote)
        self.assertEqual(result.stdout, 'watch_workers: CONTEXT: w1, no context figure: its status line '
                         'is unparsable (said once; nothing is guessed)\n'
                         'watch_workers: nothing was waiting on a person within 0 minute(s): w1\n')
        self.assertIn('CONTEXT: w1, 1.2M/1.0M', self.watch('1.2M/1.0M', '--once', quote=quote).stdout)

    def test_a_quoted_status_line_is_not_the_status_row(self):
        # Output quoting a whole status line, below the real row or with no real row at all,
        # was read as the status line: a false warning and the 'over' marker for good. Only the
        # row under the input box's bottom rule counts.
        quoted = '  ⎿  📁a-worker │ 💰$9.10 │ Opus 5.5 900k/1.0M high'
        for case in ({'after': (quoted, '  the end of the output')}, {'quote': quoted, 'drop': True}):
            with self.subTest(case=case):
                result = self.watch(STATUS, '--once', **case)
                self.assertEqual((result.returncode, result.stdout), (0, ''), result.stderr)
                self.assertFalse((self.state / 'opt-w1-@kit_watch_context').exists())
        self.assertIn('CONTEXT: w1, 1.2M/1.0M', self.watch('1.2M/1.0M', '--once', quote=quoted).stdout)
        self.assertEqual((self.state / 'opt-w1-@kit_watch_context').read_text(), 'over')

    def test_the_warning_fires_once_per_session(self):
        self.assertIn('CONTEXT: w1, 1.2M/1.0M', self.watch('1.2M/1.0M', '--once').stdout)
        self.assertEqual(self.watch('1.2M/1.0M', '--once').stdout, '')
        result = self.watch('1.2M/1.0M', '--max-minutes', '0')
        self.assertTrue(result.stdout.startswith('watch_workers: nothing was waiting'), result.stdout)

    def test_a_warning_that_cannot_be_written_ends_the_run_and_is_written_again(self):
        for args in (('--once',), ('--max-minutes', '0')):
            with self.subTest(args=args):
                for f in self.state.glob('opt-*'):
                    f.unlink()
                status = '1.2M/1.0M' if args == ('--once',) else ''
                result = self.watch(status or STATUS, *args, drop=not status, path_first=self.full_buffer())
                self.assertEqual((result.returncode, result.stdout), (3, ''), result.stderr)
                self.assertIn('watch_workers: w1: could not write its report: ', result.stderr)
                self.assertIn('CONTEXT: w1, ', self.watch(status or STATUS, *args, drop=not status).stdout)

    def test_the_same_session_twice_warns_once(self):
        result = self.watch('1.2M/1.0M', '--once', 'w1')
        self.assertEqual(result.stdout.count('CONTEXT: w1'), 1, result.stdout)

    def test_a_missing_or_unparsable_status_line_is_said_once_and_never_guessed(self):
        for status, drop, what in (('', True, 'absent'), ('58/1.0M', False, 'unparsable'),
                                   ('58k/0k', False, 'unparsable')):
            with self.subTest(status=status, drop=drop):
                for f in self.state.glob('opt-*'):
                    f.unlink()
                # --once is spawn_worker.sh's start-up check, before the status line is drawn.
                self.assertEqual(self.watch(status or STATUS, '--once', drop=drop).stdout, '')
                # The note ends no watch (#188): the window-end line follows it.
                result = self.watch(status or STATUS, '--max-minutes', '0', drop=drop)
                self.assertEqual(result.stdout, 'watch_workers: CONTEXT: w1, no context figure: its status line '
                                 'is %s (said once; nothing is guessed)\n'
                                 'watch_workers: nothing was waiting on a person within 0 minute(s): w1\n' % what)
                result = self.watch(status or STATUS, '--max-minutes', '0', drop=drop)
                self.assertTrue(result.stdout.startswith('watch_workers: nothing was waiting'), result.stdout)
                # A figure that appears later past the line is still reported.
                self.assertIn('CONTEXT: w1, 1.2M/1.0M', self.watch('1.2M/1.0M', '--once').stdout)


class BackgroundTests(Base):
    """A Claude Code background session (NAME.host bg) is watched, shown and listed through
    `claude agents --json --all`, a stub on PATH (tests/test_close_worker.py, CLAUDE); no tmux."""

    def setUp(self):
        super().setUp()
        (self.bin / 'claude').write_text(CLAUDE)
        (self.bin / 'claude').chmod(0o755)
        self.workers = self.cwd / '.myagentkit/workers'
        self.workers.mkdir(parents=True)
        # A checkout: the watcher reads a result only in one (HEAD tells committed from not).
        for args in (('init', '-q'), ('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'a')):
            subprocess.run(['git', *args], cwd=self.cwd, check=True, capture_output=True)

    def spawned(self, name, id='aaaa0001', host='bg', age=120):
        """A worker as spawn_worker.sh records it, AGE seconds ago."""
        (self.workers / (name + '.host')).write_text(host + '\n')
        for record, text in (('.id', id), ('.result-path', 'RESULT-%s.md' % name)):
            if text:
                (self.workers / (name + record)).write_text(text + '\n')
                then = time.time() - age
                os.utime(self.workers / (name + record), (then, then))

    def rows(self, *rows):
        (self.state / 'agents.json').write_text(json.dumps(list(rows)))

    def run_bg(self, script, *args, **extra):
        extra.setdefault('VIS_SESSIONS', '')
        return self.run_script(script, *args, AGENTS_FILE=str(self.state / 'agents.json'), **extra)

    def watch(self, *args, **extra):
        return self.run_bg(WATCH, '--once', '--result', 'w1=RESULT-w1.md', *args, 'w1', **extra)

    def test_a_blocked_session_is_waiting_with_what_it_waits_for_once_per_wait(self):
        self.spawned('w1')
        blocked = agent('aaaa0001', 'w1', self.cwd, 'blocked', pid=28288, status='waiting',
                        waitingFor='permission prompt')
        self.rows(blocked)
        waiting = ('watch_workers: WAITING: w1, waiting for: permission prompt (background session aaaa0001, '
                   'state blocked)\n  look at it: claude attach aaaa0001   (claude agents lists every session)\n')
        result = self.watch()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, waiting, ''))
        self.assertEqual(self.watch().stdout, '', 'the same wait was reported twice')
        self.rows(agent('aaaa0001', 'w1', self.cwd, 'working', pid=28288, status='busy'))
        self.assertEqual(self.watch().stdout, '')
        self.rows(blocked)
        self.assertEqual(self.watch().stdout, waiting, 'a new wait after work was not reported')
        self.assertEqual(self.log('tmux'), '', 'tmux was asked about a background session')

    def test_an_ended_or_removed_session_is_gone_unless_its_result_says_more(self):
        self.spawned('w1')
        self.rows(agent('aaaa0001', 'w1', self.cwd, 'done', pid=28256, status='idle'))
        result = self.watch()
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)
        # done with a live process is a turn end, as the tab path's IDLE: the lead re-arms after it.
        self.assertEqual(result.stdout, IDLE)
        self.assertEqual(self.watch().stdout, '')
        for state in ('stopped', 'failed'):
            self.rows(agent('aaaa0001', 'w1', self.cwd, state))
            self.assertEqual(self.watch().stdout, 'watch_workers: GONE: w1, its background session aaaa0001 is %s '
                             'with no new result report: read its result file\n' % state)
        self.rows()
        self.assertEqual(self.watch().stdout, 'watch_workers: GONE: w1, its background session aaaa0001 is no longer '
                         'listed (claude agents --all): read its result file\n')
        # A result wins over any state: DONE alone, no GONE.
        (self.cwd / 'RESULT-w1.md').write_text(HEAD % ('completed', 'none') + '\n<!-- codex-worker: ready -->\n')
        self.rows(agent('aaaa0001', 'w1', self.cwd, 'stopped'))
        (self.workers / 'w1.watch-bg').unlink()
        self.assertEqual(self.watch().stdout, 'watch_workers: DONE: w1, task T-7, attempt 2, remaining: none '
                         '(result file RESULT-w1.md)\n')

    def test_a_session_just_spawned_and_not_yet_listed_is_not_gone(self):
        # The spike saw no row for the first seconds after the launch.
        self.spawned('w1', age=0)
        self.rows()
        self.assertEqual(self.watch().stdout, '')

    def test_a_question_file_wins_over_the_state(self):
        self.spawned('w1')
        self.rows(agent('aaaa0001', 'w1', self.cwd, 'done'))
        (self.cwd / 'QUESTION-w1.md').write_text('A or B?\n' + READY)
        result = self.watch()
        self.assertTrue(result.stdout.startswith('watch_workers: QUESTION: w1, a decision waits in '), result.stdout)
        self.assertTrue(result.stdout.endswith('/QUESTION-w1.md: read it and answer it\n'), result.stdout)
        self.assertEqual(self.watch().stdout, '')

    def test_the_question_is_read_in_the_workers_folder_and_only_once_published(self):
        # The supervisor, the worker's instruction and close_worker.sh put QUESTION-NAME.md in the
        # worker's folder (.claude/worktrees/NAME, else the checkout), never beside a --result
        # elsewhere; a draft without the end marker is no question yet, and ends no session.
        self.spawned('w1')
        tree = self.cwd / '.claude/worktrees/w1'
        tree.mkdir(parents=True)
        self.rows(agent('aaaa0001', 'w1', tree, 'stopped'))
        (tree / 'QUESTION-w1.md').write_text('A or B?\n')
        watch = lambda: self.run_bg(WATCH, '--once', '--result', 'w1=sub/R.md', 'w1')
        self.assertIn('GONE: w1', watch().stdout, 'a draft question hid a session that ended')
        (self.workers / 'w1.watch-bg').unlink()
        (tree / 'QUESTION-w1.md').write_text('A or B?\n' + READY)
        result = watch()
        self.assertTrue(result.stdout.startswith('watch_workers: QUESTION: w1, a decision waits in '), result.stdout)
        self.assertTrue(result.stdout.endswith('/.claude/worktrees/w1/QUESTION-w1.md: read it and answer it\n'),
                        result.stdout)
        self.assertEqual(watch().stdout, '', 'a published question ended the session by design: no GONE')

    def test_a_linked_worktree_leads_worker_is_found_in_the_main_checkouts_worktrees(self):
        # spawn_worker.sh puts the worktree of a lead working in a linked worktree in the main
        # checkout's .claude/worktrees (bgbrief): its row and its question are looked for there.
        main = self.cwd
        lead, tree = main / '.claude/worktrees/lead', main / '.claude/worktrees/w1'
        for path, branch in ((lead, 'worktree-lead'), (tree, 'worktree-w1')):
            subprocess.run(['git', 'worktree', 'add', '-q', str(path), '-b', branch], cwd=main, check=True,
                           capture_output=True)
        self.cwd, self.workers = lead, lead / '.myagentkit/workers'
        self.workers.mkdir(parents=True)
        self.spawned('w1')
        self.rows(agent('aaaa0001', 'w1', tree, 'stopped'))
        row = self.run_bg(LIST, '--row', 'w1')
        self.assertEqual(row.stdout.split('\t')[3:4], ['y'], row.stdout + row.stderr)
        (tree / 'QUESTION-w1.md').write_text('A or B?\n' + READY)
        result = self.watch()
        self.assertTrue(result.stdout.endswith('/.claude/worktrees/w1/QUESTION-w1.md: read it and answer it\n'),
                        result.stdout + result.stderr)

    def test_a_report_ends_the_background_watch_loop(self):
        # bg() left the loop's own w at 1 after a WAITING or GONE, so found was never set and the
        # background watch ran to --max-minutes after its report.
        self.spawned('w1')
        for row, said in ((agent('aaaa0001', 'w1', self.cwd, 'blocked', pid=1), 'WAITING: w1'),
                          (agent('aaaa0001', 'w1', self.cwd, 'stopped'), 'GONE: w1'),
                          (agent('aaaa0001', 'w1', self.cwd, 'done', pid=1), 'IDLE: w1')):
            with self.subTest(said=said):
                self.rows(row)
                result = self.run_bg(WATCH, '--max-minutes', '0', '--result', 'w1=RESULT-w1.md', 'w1')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(said, result.stdout)
                self.assertNotIn('nothing was waiting', result.stdout)

    def test_only_a_published_final_result_hides_the_sessions_end(self):
        # The supervisor stops a session only on a decision, DONE or HANDOFF (codex_worker.py):
        # a draft or a blocked result leaves it running, so its idle or end is still said.
        self.spawned('w1')
        self.rows(agent('aaaa0001', 'w1', self.cwd, 'done', pid=1))
        (self.cwd / 'RESULT-w1.md').write_text(HEAD % ('completed', 'none'))
        self.assertEqual(self.watch().stdout, IDLE, 'a draft result hid an idle session')
        (self.cwd / 'RESULT-w1.md').write_text(HEAD % ('blocked', 'a decision') + READY)
        self.assertIn('BLOCKED: w1', self.watch().stdout)
        self.rows(agent('aaaa0001', 'w1', self.cwd, 'failed'))
        self.assertIn('GONE: w1, its background session aaaa0001 is failed', self.watch().stdout,
                      'a blocked result hid a session that ended')
        (self.cwd / 'RESULT-w1.md').write_text(HEAD % ('handoff', 'the lead') + READY)
        self.assertIn('HANDOFF: w1', self.watch().stdout)
        self.rows(agent('aaaa0001', 'w1', self.cwd, 'stopped'))
        self.assertEqual(self.watch().stdout, '')

    def test_a_list_that_cannot_be_read_is_an_observation_failure(self):
        self.spawned('w1')
        self.rows()
        result = self.watch(AGENTS_ERROR='connect ECONNREFUSED')
        self.assertEqual((result.returncode, result.stdout), (3, ''), result.stderr)
        self.assertIn('watch_workers: w1: could not list the background sessions: ', result.stderr)
        self.assertIn('connect ECONNREFUSED', result.stderr)

    def test_a_blocked_session_that_names_nothing_is_waiting_all_the_same(self):
        # POSIX spike: blocked may come with no waitingFor.
        self.spawned('w1')
        self.rows(agent('aaaa0001', 'w1', self.cwd, 'blocked', pid=28288))
        self.assertEqual(self.watch().stdout, 'watch_workers: WAITING: w1, waiting for: no reason given (background '
                         'session aaaa0001, state blocked)\n  look at it: claude attach aaaa0001   (claude agents lists '
                         'every session)\n')

    def test_a_question_or_a_final_result_ends_the_session_without_a_gone(self):
        # The supervisor stops a session 10 s after its question or final result: no GONE then.
        self.spawned('w1')
        (self.cwd / 'QUESTION-w1.md').write_text('A or B?\n' + READY)
        self.rows(agent('aaaa0001', 'w1', self.cwd, 'working', pid=1))
        self.assertIn('QUESTION: w1', self.watch().stdout)
        self.rows(agent('aaaa0001', 'w1', self.cwd, 'stopped'))
        self.assertEqual(self.watch().stdout, '')
        (self.cwd / 'QUESTION-w1.md').unlink()
        (self.cwd / 'RESULT-w1.md').write_text(HEAD % ('progress', 'more') + '\n<!-- codex-worker: ready -->\n')
        self.assertIn('PROGRESS: w1', self.watch().stdout)
        self.assertIn('GONE: w1, its background session aaaa0001 is stopped', self.watch().stdout,
                      'a progress result hid a session that ended')

    def test_a_session_started_on_the_other_host_is_reported_once_and_listed_as_elsewhere(self):
        # The native-Windows and the WSL lists are disjoint (POSIX spike, 9): no row is no proof.
        self.spawned('w1')
        other, word = ('/mnt/d/p/RESULT-w1.md', 'posix') if os.name == 'nt' else ('D:/p/RESULT-w1.md', 'windows')
        (self.workers / 'w1.result-path').write_text(other + '\n')
        self.rows()
        result = self.watch(AGENTS_ERROR='not this host')
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)
        self.assertEqual(result.stdout, 'watch_workers: ELSEWHERE: w1, its background session was started on %s, '
                         'whose session list this host cannot see: watch it there\n' % word)
        self.assertEqual(self.watch().stdout, '')
        self.assertIn('w1\tbg\taaaa0001\telsewhere:%s\t-\tn' % word, self.run_bg(LIST).stdout)

    def test_show_prints_the_attach_line_and_opens_nothing(self):
        self.spawned('w1')
        result = self.run_bg(SHOW, 'w1', WSL_DISTRO_NAME='Test-1')
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)
        self.assertEqual(result.stdout, 'show_workers: w1 runs in the background: claude attach aaaa0001   '
                         '(claude agents lists every session; nothing opened)\n')
        self.assertEqual(self.log('wt-stub') + self.log('tmux'), '')
        # Spawned on the other host: its attach fails here ('No job matching'), so none is printed.
        other, word = ('/mnt/d/p/RESULT-w1.md', 'posix') if os.name == 'nt' else ('D:/p/RESULT-w1.md', 'windows')
        (self.workers / 'w1.result-path').write_text(other + '\n')
        result = self.run_bg(SHOW, 'w1', WSL_DISTRO_NAME='Test-1')
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)
        self.assertEqual(result.stdout, 'show_workers: w1 runs in the background on %s, whose sessions this host '
                         'cannot see: claude attach aaaa0001 there   (nothing opened)\n' % word)

    def test_a_notice_on_the_listers_stderr_is_not_part_of_the_list(self):
        self.spawned('w1')
        self.rows(agent('aaaa0001', 'w1', self.cwd, 'blocked', pid=1, waitingFor='permission prompt'))
        result = self.watch(AGENTS_NOTICE='Update available: run claude update')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('WAITING: w1, waiting for: permission prompt', result.stdout)
        self.assertIn('w1\tbg\taaaa0001\tblocked\tpermission prompt\tn',
                      self.run_bg(LIST, AGENTS_NOTICE='Update available').stdout)

    def test_the_list_has_one_line_per_worker_of_this_checkout(self):
        self.spawned('w1')
        self.spawned('w2', id='bbbb0002')
        self.spawned('t1', id=None, host='tmux')
        (self.workers / 'c1.session').write_text('sid\n')
        (self.cwd / 'RESULT-w2.md').write_text('x\n')
        self.rows(agent('aaaa0001', 'w1', self.cwd, 'blocked', pid=1, waitingFor='permission prompt'),
                  agent('cccc0003', 'w2', self.cwd, 'working', pid=2))
        result = self.run_bg(LIST, VIS_SESSIONS='t1')
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)
        self.assertEqual(result.stdout.splitlines(), [
            'NAME\tHOST\tID\tSTATE\tWAITING-FOR\tRESULT', 'c1\t-\t-\t-\t-\tn', 't1\ttmux\t-\trunning\t-\tn',
            'w1\tbg\taaaa0001\tblocked\tpermission prompt\tn', 'w2\tbg\tbbbb0002\tabsent\t-\ty'])
        result = self.run_bg(LIST, AGENTS_ERROR='boom')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('list_workers: claude agents --json --all failed: boom', result.stderr)
        self.assertIn('w1\tbg\taaaa0001\t?\t-\tn', result.stdout)


if __name__ == '__main__':
    unittest.main()
