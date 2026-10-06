"""show_workers.sh must open every named session in one window or say how to attach by hand,
and watch_workers.sh must return when a session is gone or waits on a person, and only then.

No real terminal, no tmux server, no `claude`: tmux, the Windows Terminal launcher (KIT_WT,
never a file named *.exe: under WSL such a file is handed to Windows), osascript and uname
are stubs on PATH. The panes are real captures (tests/fixtures/panes/, see the README there).
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'overlays/claude-code/files/scripts'
SHOW, WATCH = SCRIPTS / 'show_workers.sh', SCRIPTS / 'watch_workers.sh'
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
    sys.exit(0 if name in sessions else 1)
if args[0] == 'list-clients':
    if name in os.environ.get('VIS_ATTACHED', '').split() or os.path.exists(os.path.join(st, 'attached-' + name)):
        print('/dev/pts/9: %s [120x30 xterm-256color] (attached,UTF-8)' % name)
    sys.exit(0 if name in sessions else 1)
if args[0] == 'capture-pane':
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
names = re.findall(r"=([A-Za-z0-9_-]+)", ' '.join(sys.argv[1:]))
for n in names[:1] if mode == 'partial' else names:
    open(os.path.join(st, 'attached-' + n), 'w').close()
'''


def shq(value):
    return "'" + value.replace("'", "'\\''") + "'"


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

    def run_script(self, script, *args, path_first=(), **extra):
        env = {k: v for k, v in os.environ.items()
               if k not in ('WSL_DISTRO_NAME', 'TERM_PROGRAM', 'TMUX', 'TMUX_PANE', 'KIT_WT')}
        path = os.pathsep.join([*map(str, path_first), str(self.bin), os.environ['PATH']])
        env.update(PATH=path, VIS_STATE=str(self.state), KIT_WT=str(self.bin / 'wt-stub'), **extra)
        return subprocess.run(['sh', str(script), *args], cwd=self.cwd, env=env, capture_output=True,
                              text=True, timeout=60)

    def log(self, name):
        path = self.state / (name + '.log')
        return path.read_text() if path.exists() else ''


class ShowTests(Base):
    WSL = dict(WSL_DISTRO_NAME='Test-1', VIS_SESSIONS='a b-2 c_3')

    def wt_line(self, window, *names):
        args = [str(self.bin / 'wt-stub'), '-w', window]
        for i, n in enumerate(names):
            args += [';'] if i else []
            args += ['new-tab', '--title', n, 'wsl.exe', '-d', 'Test-1', '--exec', str(self.bin / 'tmux'),
                     'attach', '-t', '=' + n]
        return 'cd %s && %s' % (shq(str(self.bin)), ' '.join(map(shq, args)))

    def osa_line(self, app, *names):
        cmd = lambda n: '"exec %s attach -t %s"' % (shq(str(self.bin / 'tmux')), shq('=' + n))
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
                self.assertEqual(result.stdout, self.wt_line('kit-my_proj_', *names) + '\n')
                self.assertEqual(self.log('wt-stub'), '', '--print ran the launcher')

    def test_the_window_is_named_after_the_project_from_anywhere_in_it(self):
        # One fixed name per project, so a later call adds its tabs to the same window: from a
        # subfolder and from a worktree it is still the main checkout's folder.
        git = lambda *a: subprocess.run(['git', *a], cwd=self.cwd, check=True, capture_output=True)
        git('init', '-q')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'a')
        git('worktree', 'add', '-q', '.claude/worktrees/w', '-b', 'worktree-w')
        (self.cwd / 'sub').mkdir()
        for where in ('.', 'sub', '.claude/worktrees/w'):
            with self.subTest(where=where):
                env = dict(os.environ, PATH=os.pathsep.join([str(self.bin), os.environ['PATH']]),
                           VIS_STATE=str(self.state), KIT_WT=str(self.bin / 'wt-stub'), **self.WSL)
                result = subprocess.run(['sh', str(SHOW), '--print', 'a'], cwd=self.cwd / where, env=env,
                                        capture_output=True, text=True, timeout=60)
                self.assertIn("'-w' 'kit-my_proj_'", result.stdout, result.stderr)

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

    def test_a_launcher_that_hangs_is_bounded(self):
        start = time.monotonic()
        result = self.run_script(SHOW, 'a', VIS_MODE='hang', **self.WSL)
        self.assertLess(time.monotonic() - start, 20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('did not return within 5 s', result.stdout)
        self.assertIn('attach by hand: tmux attach -t a', result.stdout)


class WatchTests(Base):
    def watch(self, *args, pane='idle.txt', **extra):
        extra.setdefault('VIS_SESSIONS', 'w1')
        return self.run_script(WATCH, *args, VIS_PANE=str(PANES / pane), **extra)

    def test_a_gone_session_is_reported(self):
        for args in (('--once', 'w1', 'gone'), ('w1', 'gone')):
            with self.subTest(args=args):
                result = self.watch(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('GONE: gone', result.stdout)
                self.assertNotIn('w1', result.stdout.replace('GONE: gone', ''))

    def test_every_real_dialog_capture_is_waiting_with_the_session_named(self):
        for pane, what in DIALOGS.items():
            with self.subTest(pane=pane):
                result = self.watch('w1', pane=pane)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('WAITING: w1, on %s (rule VERIFIED, Claude Code 2.1.285)' % what, result.stdout)
                self.assertIn('  | ', result.stdout)

    def test_working_and_idle_panes_give_nothing(self):
        # quoted-output.txt: the worker's OUTPUT quotes a permission prompt and a question's
        # key hint higher up; a phrase match anywhere called that waiting.
        for pane in WORKING:
            with self.subTest(pane=pane):
                result = self.watch('--once', 'w1', pane=pane)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))

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

    def test_the_pattern_table_lists_every_rule_with_its_flag(self):
        result = self.run_script(WATCH, '--list-patterns')
        self.assertEqual(result.returncode, 0, result.stderr)
        rules = [line for line in (SCRIPTS / 'waiting_patterns.txt').read_text().splitlines()
                 if line.strip() and not line.startswith('#')]
        self.assertEqual(len(result.stdout.splitlines()), len(rules) + 1)
        for rule in rules:
            self.assertRegex(rule.split()[1], '^(VERIFIED|UNVERIFIED)$')
            self.assertIn(rule, result.stdout)
        # A VERIFIED rule names the version its capture came from, and that capture is here.
        verified = [rule.split() for rule in rules if rule.split()[1] == 'VERIFIED']
        self.assertEqual({r[0] for r in verified}, {'trust', 'permission', 'question'})
        self.assertTrue(all(r[2] == '2.1.285' for r in verified))


if __name__ == '__main__':
    unittest.main()
