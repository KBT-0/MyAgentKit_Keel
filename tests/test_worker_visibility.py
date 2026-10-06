"""show_workers.sh must open every named session in one window or say how to attach by hand,
and watch_workers.sh must return when a session is gone or waits on a person, and only then.

No real terminal, no tmux server, no `claude`: tmux, the Windows Terminal launcher (KIT_WT,
never a file named *.exe: under WSL such a file is handed to Windows), osascript and uname
are stubs on PATH. The panes are real captures (tests/fixtures/panes/, see the README there).
"""
import importlib.util
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
# The watcher's once-markers are user options of the session.
if args[0] in ('set-option', 'show-options'):
    opt = os.path.join(st, 'opt-%s-%s' % (name, args[-2] if args[0] == 'set-option' else args[-1]))
    if args[0] == 'set-option':
        with open(opt, 'w') as f:
            f.write(args[-1])
    elif os.path.exists(opt):
        with open(opt) as f:
            print(f.read())
    sys.exit(0)
if args[0] == 'capture-pane':
    if os.environ.get('VIS_CAPTURE_FAIL'):
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

    def test_a_launcher_that_ignores_sigterm_is_killed(self):
        # One SIGTERM and an endless wait: a launcher that ignores it hung the spawn with it.
        start = time.monotonic()
        result = self.run_script(SHOW, 'a', VIS_MODE='hang-term', **self.WSL)
        self.assertLess(time.monotonic() - start, 20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('did not return within 5 s', result.stdout)
        self.assertIn('attach by hand: tmux attach -t a', result.stdout)

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
        self.assertEqual({r[0] for r in verified}, {'trust', 'permission', 'question', 'context'})
        self.assertTrue(all(r[2] == '2.1.285' for r in verified))


HEAD = 'Kind: %s\nTask: T-7\nAttempt: 2\nRemaining: %s\n'
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

    def test_the_watcher_restarted_after_progress_reaches_done(self):
        # The lead restarts the watcher after every report but DONE and GONE while work
        # remains: the second run, after a PROGRESS report, still reports the completion.
        self.commit(HEAD % ('progress', 'two steps'))
        self.assertIn('PROGRESS: w1', self.watch().stdout)
        self.commit(HEAD % ('completed', 'none'))
        result = self.run_script(WATCH, '--max-minutes', '1', '--result', 'w1=docs/w1.md', 'w1',
                                 VIS_SESSIONS='w1', VIS_PANE=str(PANES / 'working-auto.txt'))
        self.assertTrue(result.stdout.startswith('watch_workers: DONE: w1'), result.stdout)

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
        self.assertEqual(gate.case_in_substitution(WATCH.read_text()), [])
        before = ('result() {\n  f=$(printf \'%s\\n\' "$results" | while IFS= read -r r; do\n'
                  '    case $r in "$1="*) printf \'%s\\n\' "${r#"$1="}" ;; esac\n  done | tail -n 1)\n}\n')
        self.assertEqual(gate.case_in_substitution(before), [3])
        # Quoted, commented or in a here-document, the word is not a `case`.
        self.assertEqual(gate.case_in_substitution('x=$(echo "case a" \'case b\') # $( case\n'
                                                   'cat <<-E\n\t$(case\n\tE\n'), [])
        # An argument is not a command: `case` counts only where a command starts.
        self.assertEqual(gate.case_in_substitution('x=$(echo case value)\ny=$(f; then case)\n'), [])
        self.assertEqual(gate.case_in_substitution('x=$(true && case a in a) :;; esac)\n'), [1])
        self.assertEqual(gate.case_in_substitution('x=$(if :; then case a in a) :;; esac; fi)\n'), [1])
        # A shift in $(( )) is not a here-document: the next line is still read.
        self.assertEqual(gate.case_in_substitution('n=$((1 << 2)) m="$((n << 1))"\n'
                                                   'f=$(case x in x) echo ok;; esac)\n'), [2])

    def test_the_kit_check_rejects_a_case_inside_a_substitution(self):
        # The scan alone is not the gate: check_syntax must run it and stop on it.
        spec = importlib.util.spec_from_file_location('kit_check', ROOT / 'scripts/check_kit.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        (self.tmp / 'bad.sh').write_text('#!/bin/sh\nn=$((1 << 2))\nf=$(case x in x) echo ok;; esac)\n')
        with self.assertRaisesRegex(RuntimeError, r'bad\.sh: `case` inside \$\( \) on line 3: bash 3\.2'):
            gate.check_syntax(self.tmp)


class ContextTests(Base):
    """The context figure is read from the status line, past a warning line, once per session."""

    def watch(self, status, *args, drop=False, quote=None):
        text = (PANES / 'working-auto.txt').read_text()
        self.assertIn(STATUS, text)
        lines = [line for line in text.replace(STATUS, status).splitlines() if not (drop and '│' in line)]
        lines = ([quote] if quote else []) + lines
        pane = self.tmp / 'pane.txt'
        pane.write_text('\n'.join(lines) + '\n')
        return self.run_script(WATCH, *args, 'w1', VIS_SESSIONS='w1', VIS_PANE=str(pane), LC_ALL='C')

    def test_the_figure_is_reported_past_the_warning_line(self):
        for status, warn, out in (('58k/1.0M', '50', ''), ('58k/1.0M', '5', '58k/1.0M is 5%'),
                                  ('113k/1.0M', '50', ''), ('113k/1.0M', '10', '113k/1.0M is 11%'),
                                  ('1.2M/1.0M', '50', '1.2M/1.0M is 120%'), ('36k/200k', '17', '36k/200k is 18%')):
            with self.subTest(status=status, warn=warn):
                for f in self.state.glob('opt-*'):
                    f.unlink()
                result = self.watch(status, '--once', '--context-warn', warn)
                self.assertEqual(result.returncode, 0, result.stderr)
                if out:
                    self.assertEqual(result.stdout, 'watch_workers: CONTEXT: w1, %s of its context window, past the '
                                     '%s%% warning line (finish, compact or hand off: read its Remaining: line)\n'
                                     % (out, warn))
                else:
                    self.assertEqual(result.stdout, '')

    def test_a_figure_in_the_output_is_not_the_status_line(self):
        # Output quoting `800k/1.0M` gave a false 80% warning and set the once-marker that
        # then hid a real warning. Only the status line's figure counts.
        quote = '  the report said 800k/1.0M of context was used'
        self.assertEqual(self.watch(STATUS, '--once', quote=quote).stdout, '')
        result = self.watch('', '--max-minutes', '0', quote=quote)
        self.assertEqual(result.stdout, 'watch_workers: CONTEXT: w1, no context figure: its status line '
                         'is unparsable (said once; nothing is guessed)\n')
        self.assertIn('CONTEXT: w1, 1.2M/1.0M', self.watch('1.2M/1.0M', '--once', quote=quote).stdout)

    def test_the_warning_fires_once_per_session(self):
        self.assertIn('CONTEXT: w1, 1.2M/1.0M', self.watch('1.2M/1.0M', '--once').stdout)
        self.assertEqual(self.watch('1.2M/1.0M', '--once').stdout, '')
        result = self.watch('1.2M/1.0M', '--max-minutes', '0')
        self.assertTrue(result.stdout.startswith('watch_workers: nothing was waiting'), result.stdout)

    def test_a_missing_or_unparsable_status_line_is_said_once_and_never_guessed(self):
        for status, drop, what in (('', True, 'absent'), ('58/1.0M', False, 'unparsable'),
                                   ('58k/0k', False, 'unparsable')):
            with self.subTest(status=status, drop=drop):
                for f in self.state.glob('opt-*'):
                    f.unlink()
                # --once is spawn_worker.sh's start-up check, before the status line is drawn.
                self.assertEqual(self.watch(status or STATUS, '--once', drop=drop).stdout, '')
                result = self.watch(status or STATUS, '--max-minutes', '0', drop=drop)
                self.assertEqual(result.stdout, 'watch_workers: CONTEXT: w1, no context figure: its status line '
                                 'is %s (said once; nothing is guessed)\n' % what)
                result = self.watch(status or STATUS, '--max-minutes', '0', drop=drop)
                self.assertTrue(result.stdout.startswith('watch_workers: nothing was waiting'), result.stdout)
                # A figure that appears later past the line is still reported.
                self.assertIn('CONTEXT: w1, 1.2M/1.0M', self.watch('1.2M/1.0M', '--once').stdout)


if __name__ == '__main__':
    unittest.main()
