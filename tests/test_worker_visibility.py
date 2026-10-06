"""watch_workers.sh must return when a session is gone or waits on a person, and only then.

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
