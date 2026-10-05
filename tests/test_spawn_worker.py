"""spawn_worker.sh must hand every value to the worker intact, deliver the brief by path, and
build its worktree from the lead's current commit.

No live `claude` and no tmux server: both are stubs on PATH. The tmux stub runs the session
command with `sh -c`, the way tmux does, so a value that escapes its quoting runs here too.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'overlays/claude-code/files/scripts/spawn_worker.sh'

TMUX = r'''#!/usr/bin/env python3
import os, subprocess, sys
state = os.environ['SPAWN_STATE']
args = sys.argv[1:]
with open(os.path.join(state, 'tmux.log'), 'a') as log:
    log.write(repr(args) + '\n')
typed = os.path.join(state, 'typed')
def read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ''
def append(text):
    with open(typed, 'a') as f:
        f.write(text)
cmd = args[0]
if cmd == 'has-session':
    sys.exit(1)
if cmd == 'new-session':
    sys.exit(subprocess.run(['sh', '-c', args[-1]]).returncode)
if cmd == 'capture-pane':
    print('\n❯ ' + read(typed))
elif cmd == 'load-buffer':
    with open(os.path.join(state, 'buffer'), 'w') as f:
        f.write(read(args[-1]))
elif cmd == 'paste-buffer':
    # The TUI shows a multi-line paste as a placeholder; the text itself is what Enter sends.
    text = read(os.path.join(state, 'buffer'))
    with open(os.path.join(state, 'pasted'), 'w') as f:
        f.write(text)
    append('[Pasted text #1 +%d lines]' % text.count('\n') if '\n' in text else text)
elif cmd == 'send-keys':
    rest = args[1:]
    literal = '-l' in rest
    keys = [a for i, a in enumerate(rest) if a not in ('-t', '-l') and (i == 0 or rest[i - 1] != '-t')]
    for key in keys:
        if key == 'Enter' and not literal:
            with open(os.path.join(state, 'submitted'), 'a') as f:
                f.write(read(os.path.join(state, 'pasted')) or read(typed))
                f.write('\n')
            open(typed, 'w').close()
            open(os.path.join(state, 'pasted'), 'w').close()
        else:
            append(key)
'''

CLAUDE = r'''#!/usr/bin/env python3
import json, os, sys
with open(os.path.join(os.environ['SPAWN_STATE'], 'claude.json'), 'w') as f:
    json.dump({'argv': sys.argv[1:], 'cwd': os.getcwd()}, f)
'''


def shq(value):
    return "'" + value.replace("'", "'\\''") + "'"


class SpawnWorkerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.state, self.bin, self.cwd = self.tmp / 'state', self.tmp / 'bin', self.tmp / "lead's dir"
        for folder in (self.state, self.bin, self.cwd):
            folder.mkdir()
        for name, body in (('tmux', TMUX), ('claude', CLAUDE), ('sleep', '#!/bin/sh\nexit 0\n')):
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        self.brief = self.cwd / "it's the brief.md"
        self.brief.write_text('Line one of the brief.\nLine two.\n')

    def tearDown(self):
        self._tmp.cleanup()

    def spawn(self, *args, **extra):
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}',
                   SPAWN_STATE=str(self.state), **extra)
        return subprocess.run(['sh', str(SCRIPT), *args], cwd=self.cwd, env=env,
                              capture_output=True, text=True, timeout=60)

    def launched(self):
        path = self.state / 'claude.json'
        return json.loads(path.read_text()) if path.exists() else None

    def tmux_log(self):
        path = self.state / 'tmux.log'
        return path.read_text() if path.exists() else ''

    def test_values_with_apostrophes_arrive_intact_and_run_nothing(self):
        marker = self.tmp / 'injected'
        # Each value holds an even number of apostrophes, so under unescaped quoting every
        # $(...) lands outside quotes and runs; escaped, each arrives as written.
        name = "o'brien's"
        settings = json.dumps({'note': f"'$(touch {marker})'"})
        model, effort = "m'x'", f"high'$(touch {marker})'"
        tools = "Bash(echo 'a b'),Read"
        result = self.spawn(name, str(self.brief), '--model', model, '--effort', effort,
                            '--settings', settings, '--allowed-tools', tools)
        self.assertFalse(marker.exists(), 'an interpolated value ran as shell')
        launched = self.launched()
        self.assertIsNotNone(launched, result.stderr)
        self.assertEqual(launched['argv'], ['-n', name, '--model', model, '--effort', effort,
                                            '--settings', settings, '--allowedTools', tools])
        self.assertEqual(Path(launched['cwd']).resolve(), self.cwd.resolve())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_brief_is_delivered_by_path_as_one_typed_instruction(self):
        result = self.spawn('w1', str(self.brief))
        self.assertEqual(result.returncode, 0, result.stderr)
        submitted = (self.state / 'submitted').read_text().splitlines()
        self.assertEqual(submitted[0], f'Read {shq(str(self.brief))} and follow it.')
        self.assertNotIn('Line one of the brief', (self.state / 'submitted').read_text())

    def assert_refused(self, brief):
        result = self.spawn('w2', str(brief))
        self.assertNotEqual(result.returncode, 0, brief)
        self.assertIn(str(brief), result.stderr)
        self.assertNotIn('new-session', self.tmux_log(), brief)

    def test_missing_or_unreadable_brief_is_refused_before_any_session(self):
        # A directory is no brief for any user, root included.
        (self.cwd / 'a-directory.md').mkdir()
        for brief in (self.cwd / 'absent.md', self.cwd / 'a-directory.md'):
            with self.subTest(brief=brief.name):
                self.assert_refused(brief)

    def test_a_brief_without_read_permission_is_refused(self):
        # Root reads a mode-000 file: there this case cannot run, and a case that cannot run
        # is reported as a skip, which the kit check refuses, never as a pass.
        if os.geteuid() == 0:
            self.skipTest('root reads a mode-000 file; run the kit check as an ordinary user')
        self.brief.chmod(0)
        self.assert_refused(self.brief)

    def test_a_relative_brief_resolves_here_whatever_cdpath_says(self):
        # With CDPATH exported, `cd briefs` went to another briefs/ and printed it: the path
        # took a newline and a valid brief was refused, or another folder's brief was named.
        (self.cwd / 'briefs').mkdir()
        (self.cwd / 'briefs/task.md').write_text('here\n')
        (self.tmp / 'elsewhere/briefs').mkdir(parents=True)
        (self.tmp / 'elsewhere/briefs/task.md').write_text('elsewhere\n')
        result = self.spawn('w4', 'briefs/task.md', CDPATH=str(self.tmp / 'elsewhere'))
        self.assertEqual(result.returncode, 0, result.stderr)
        submitted = (self.state / 'submitted').read_text().splitlines()
        self.assertEqual(submitted[0], 'Read %s and follow it.' % shq(str(self.cwd / 'briefs/task.md')))

    def test_a_brief_name_ending_in_a_newline_is_refused(self):
        # $(basename ...) stripped the trailing newline: "task.md<newline>" was checked and
        # "task.md", another file, was handed to the worker.
        (self.cwd / 'task.md').write_text('the other brief\n')
        (self.cwd / 'task.md\n').write_text('the checked brief\n')
        for brief in (self.cwd / 'task.md\n', 'task.md\n'):
            with self.subTest(brief=str(brief)):
                result = self.spawn('w5', str(brief))
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertIn('newline', result.stderr)
                self.assertNotIn('new-session', self.tmux_log())

    def test_a_control_character_in_the_brief_path_or_the_name_is_refused(self):
        # Only LF was refused: `tmux send-keys -l` typed a carriage return in the brief path
        # into the TUI, which submitted the instruction early (ESC edits it, and so on).
        for label, char in (('CR', '\r'), ('ESC', '\x1b'), ('TAB', '\t'), ('DEL', '\x7f')):
            brief = self.cwd / ('task%s.md' % char)
            brief.write_text('a brief\n')
            folder = self.cwd / ('in%sside' % char)
            folder.mkdir()
            (folder / 'task.md').write_text('a brief\n')
            for case, name, path in (('brief', 'w9', str(brief)), ('relative brief', 'w9', brief.name),
                                     ('folder', 'w9', str(folder / 'task.md')),
                                     ('name', 'w%s9' % char, str(self.brief))):
                with self.subTest(char=label, case=case):
                    if (self.state / 'tmux.log').exists():
                        (self.state / 'tmux.log').unlink()
                    result = self.spawn(name, path)
                    self.assertNotEqual(result.returncode, 0, result.stderr)
                    self.assertIn('control character', result.stderr)
                    self.assertNotIn('new-session', self.tmux_log())
        # The caller's own folder holding one is refused too: the resolved path carries it.
        cwd = self.tmp / 'lead\rdir'
        cwd.mkdir()
        (cwd / 'task.md').write_text('a brief\n')
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}', SPAWN_STATE=str(self.state))
        result = subprocess.run(['sh', str(SCRIPT), 'w9', 'task.md'], cwd=cwd, env=env,
                                capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn('control character', result.stderr)
        self.assertNotIn('new-session', self.tmux_log())

    def test_no_error_message_echoes_a_control_character(self):
        # "brief file not found" ran before the control-character check and printed the raw
        # path, ESC included, to the lead's terminal; so did "unknown option" and --settings.
        cases = (('missing brief', ('w10', str(self.cwd / 'absent\x1b[2J.md'))),
                 ('missing name', ('w\x1b[2J', str(self.cwd / 'absent.md'))),
                 ('unknown option', ('w11', str(self.brief), '--x\x1b[2J')),
                 ('settings', ('w12', str(self.brief), '--worktree', '--settings', 'a\x1b[2J.json')))
        for case, args in cases:
            with self.subTest(case=case):
                result = self.spawn(*args)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertNotIn('\x1b', result.stdout + result.stderr)
                self.assertNotIn('new-session', self.tmux_log())
        self.assertIn('control character', self.spawn(*cases[0][1]).stderr)

    def test_no_message_turns_a_backslash_in_a_value_into_an_escape(self):
        # `echo` interprets backslash escapes in some shells (dash, macOS sh): a brief named
        # with the literal characters \033[2J passed the control-byte check and the SUCCESS
        # message put an ESC sequence on the lead's terminal. bash with xpg_echo behaves so.
        brief = self.cwd / 'task\\033[2J.md'
        brief.write_text('a brief\n')
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}', SPAWN_STATE=str(self.state))
        result = subprocess.run(['bash', '-O', 'xpg_echo', str(SCRIPT), 'w\\033[2J', str(brief)], cwd=self.cwd,
                                env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(brief), result.stdout)
        self.assertNotIn('\x1b', result.stdout + result.stderr)
        # The same holds in every shell only if no echo prints a value: none in these scripts.
        for script in (SCRIPT, ROOT / 'bootstrap.sh', ROOT / 'sync-kit.sh'):
            for n, line in enumerate(script.read_text().splitlines(), 1):
                code = line.split('#', 1)[0] if line.lstrip().startswith('#') else line
                self.assertNotRegex(code, r'\becho\b[^|;&]*\$', '%s:%d' % (script.name, n))

    def test_a_relative_settings_file_resolves_against_the_caller_with_a_worktree(self):
        # The worktree is entered before the tool starts: a relative --settings file then
        # named the worktree's copy (absent when untracked, or another tracked file).
        git = lambda *a: subprocess.run(['git', *a], cwd=self.cwd, check=True, capture_output=True)
        git('init', '-q')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'a')
        (self.cwd / 'local.json').write_text('{}\n')
        inline = '{"model": "x"}'
        for name, value, expect in (('w6', 'local.json', str(self.cwd / 'local.json')),
                                    ('w7', inline, inline)):
            with self.subTest(settings=value):
                result = self.spawn(name, str(self.brief), '--worktree', '--settings', value)
                self.assertEqual(result.returncode, 0, result.stderr)
                argv = self.launched()['argv']
                self.assertEqual(argv[argv.index('--settings') + 1], expect)
        # A relative value that is neither inline JSON nor a file here could name a tracked
        # file in the worktree: refused by name before any session.
        (self.state / 'tmux.log').unlink()
        result = self.spawn('w8', str(self.brief), '--worktree', '--settings', 'absent.json')
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn('absent.json', result.stderr)
        self.assertNotIn('new-session', self.tmux_log())

    def test_inline_settings_with_leading_whitespace_arrive_unchanged(self):
        # Only a first byte of `{` counted as inline JSON: with --worktree, ' {"model": "x"}'
        # was taken for a relative file name and the worker never started.
        git = lambda *a: subprocess.run(['git', *a], cwd=self.cwd, check=True, capture_output=True)
        git('init', '-q')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'a')
        n = 0
        for lead in (' ', '\t', '\n', '\r', '\r\n', ' \t\r\n '):
            for worktree in ((), ('--worktree',)):
                n += 1
                value = lead + '{"model": "x"}'
                with self.subTest(lead=lead, worktree=bool(worktree)):
                    result = self.spawn('ws%d' % n, str(self.brief), *worktree, '--settings', value)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    argv = self.launched()['argv']
                    self.assertEqual(argv[argv.index('--settings') + 1], value)
        # Whitespace alone is no JSON: with --worktree it is still refused before any session.
        (self.state / 'tmux.log').unlink()
        result = self.spawn('ws0', str(self.brief), '--worktree', '--settings', ' \t')
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('new-session', self.tmux_log())

    def test_worktree_is_built_from_the_leads_current_commit(self):
        git = lambda *a: subprocess.run(['git', *a], cwd=self.cwd, check=True, capture_output=True,
                                        text=True).stdout.strip()
        git('init', '-q')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'a')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'b')
        head = git('rev-parse', 'HEAD')
        result = self.spawn('w3', str(self.brief), '--worktree')
        self.assertEqual(result.returncode, 0, result.stderr)
        tree = self.cwd / '.claude/worktrees/w3'
        launched = self.launched()
        self.assertNotIn('-w', launched['argv'])
        self.assertEqual(Path(launched['cwd']).resolve(), tree.resolve())
        self.assertEqual(git('-C', str(tree), 'rev-parse', 'HEAD'), head)
        self.assertEqual(git('-C', str(tree), 'branch', '--show-current'), 'worktree-w3')
        # A second spawn under the same name would reuse a stale branch: refused by name.
        (self.state / 'tmux.log').unlink()
        again = self.spawn('w3', str(self.brief), '--worktree')
        self.assertNotEqual(again.returncode, 0)
        self.assertIn('worktree-w3', again.stderr)
        self.assertNotIn('new-session', self.tmux_log())


if __name__ == '__main__':
    unittest.main()
