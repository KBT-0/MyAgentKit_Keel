"""spawn_worker.sh must hand every value to the worker intact, deliver the brief by path, and
build its worktree from the lead's current commit.

No live `claude` and no tmux server: both are stubs on PATH. The tmux stub accepts only
`sh SCRIPT` (two plain words, so tmux's fish default shell can parse it) and passes that
command to `sh -c` in the start directory, so unquoted path expansions run here too.
No real terminal either: the launcher (KIT_WT), `osascript` and `uname` are stubs, and the
environment says WSL, so showing a session goes to the launcher stub, which marks it attached.
"""
import json
import io
import os
from pathlib import Path
import shutil
import subprocess
import shutil
from contextlib import contextmanager
import sys
import tempfile
import unittest
from unittest.mock import patch

# Fixture supervisors must never inherit the live worker's records or lifecycle settings.
for _name in [n for n in os.environ if n.startswith('KIT_WORKER_')]:
    os.environ.pop(_name, None)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'overlays/claude-code/files/scripts/spawn_worker.sh'
PANES = ROOT / 'tests/fixtures/panes'
INSTRUCTION = ("Read %s and follow it. Do not ask questions in this pane: write a question into your "
               "result file and go on with what does not depend on it.")

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
started = os.path.join(state, 'started')
target = args[args.index('-t') + 1].lstrip('=').rstrip(':') if '-t' in args else ''
if cmd == 'has-session':
    sys.exit(0 if target in read(started).split('\n') and 'SPAWN_GONE' not in os.environ
             else "can't find session: " + target)
if cmd == 'list-clients':
    if os.path.exists(os.path.join(state, 'attached')):
        print('/dev/pts/9: w [120x30 xterm-256color] (attached,UTF-8)')
    sys.exit(0)
if cmd == 'new-session':
    # tmux's default shell may be fish: it must only see two plain words, `sh SCRIPT`.
    words = args[-1].split(' ')
    assert len(words) == 2 and words[0] == 'sh' and not set("'\";&|") & set(words[1]), args[-1]
    # The script removes itself when run: read it first, through sh (a Git Bash path).
    text = subprocess.run(['sh', '-c', 'cat "$1"', 'sh', words[1]], capture_output=True, text=True).stdout
    with open(os.path.join(state, 'tmux-script'), 'w') as g:
        g.write(text)
    with open(started, 'a') as f:
        f.write(args[args.index('-s') + 1] + '\n')
    directory = args[args.index('-c') + 1]
    if os.name == 'nt':
        directory = subprocess.run(['cygpath', '-m', directory], capture_output=True,
                                   text=True, check=True).stdout.rstrip('\n')
    sys.exit(subprocess.run(['sh', '-c', args[-1]], cwd=directory).returncode)
if cmd == 'capture-pane':
    if 'SPAWN_PANE' in os.environ:
        sys.stdout.write(read(os.environ['SPAWN_PANE']))
    else:
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
    json.dump({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'env_names': sorted(os.environ),
               'env': {k: v for k, v in os.environ.items() if k.startswith('ANTHROPIC_') or
               k in os.environ.get('SPAWN_CONTROL_NAMES', '').split(',')}}, f)
# SPAWN_PUBLISH: a worker that writes that text to SPAWN_PUBLISH_TO, then works on for
# SPAWN_LINGER seconds; the file `finished` says it was not ended meanwhile.
if os.environ.get('SPAWN_PUBLISH'):
    import time
    with open(os.environ['SPAWN_PUBLISH_TO'], 'w') as f:
        f.write(os.environ['SPAWN_PUBLISH'])
    time.sleep(float(os.environ['SPAWN_LINGER']))
    open(os.path.join(os.environ['SPAWN_STATE'], 'finished'), 'w').close()
'''


# The lead's Claude Code session markers: a claude that sees CLAUDE_CODE_CHILD_SESSION never
# registers as a peer. CLAUDE_CODE_EXECPATH names the binary and is kept.
MARKERS = {'CLAUDE_CODE_CHILD_SESSION', 'CLAUDECODE', 'CLAUDE_CODE_SESSION_ID', 'CLAUDE_PID',
           'CLAUDE_CODE_MESSAGING_SOCKET', 'CLAUDE_CODE_MESSAGING_TOKEN', 'CLAUDE_CODE_SESSION_ATTENDED',
           'CLAUDE_CODE_ENTRYPOINT'}
LEAD_ENV = dict.fromkeys(MARKERS | {'CLAUDE_CODE_EXECPATH'}, '1')

# The terminal launcher, named by KIT_WT and never *.exe: under WSL any file of that name is
# handed to Windows. It logs what it was asked to open; SPAWN_WT=fail is WSL interop down.
WT = r'''#!/usr/bin/env python3
import os, sys
state = os.environ['SPAWN_STATE']
with open(os.path.join(state, 'wt.log'), 'a') as log:
    log.write(repr(sys.argv[1:]) + '\n')
if os.environ.get('SPAWN_WT') == 'fail':
    sys.stderr.write('wt.exe: cannot execute binary file: Exec format error\n')
    sys.exit(126)
open(os.path.join(state, 'attached'), 'w').close()
'''

# Native Windows. cygpath -w as Git for Windows has it. The tab launcher (KIT_WT, as WT above)
# does what wt.exe does with its command line: a `;` not escaped as `\;` starts another
# subcommand, wherever it stands, and leaves the tab with an error; a double quote is dropped;
# a bare `bash` in the new tab is WSL's launcher. Each fails here by name. Otherwise it
# unescapes `\;`, adds the tab's script to wt.json and runs it with sh, as Git Bash would.
CYGPATH = r'''#!/usr/bin/env python3
import sys
assert sys.argv[1] in ('-w', '-m'), sys.argv
print('C:' + (sys.argv[2].replace('/', '\\') if sys.argv[1] == '-w' else sys.argv[2]))
'''

WT_TAB = r'''#!/usr/bin/env python3
import json, os, re, subprocess, sys
args = sys.argv[1:]
with open(os.path.join(os.environ['SPAWN_STATE'], 'wt.json'), 'w') as f:
    json.dump(args, f)
split = [a for a in args if re.search(r'(?<!\\);', a)]
if split:
    sys.exit('wt stub: the command line was split at a bare ; in %r' % split)
if any('"' in a for a in args):
    sys.exit('wt stub: wt.exe drops the double quotes in %r' % args)
args = [a.replace('\\;', ';') for a in args]
i = args.index('new-tab') + 1
while args[i].startswith('-'):
    i += 2
if not re.match(r'^[A-Za-z]:\\.*\\bash(\.exe)?$', args[i]):
    sys.exit('wt stub: the tab runs %r, not Git Bash by its full path' % args[i])
assert args[i + 1] == '-l', args
script = args[i + 2] if os.name == 'nt' else args[i + 2][2:].replace('\\', '/')
with open(script) as f:
    args.append(f.read())
with open(os.path.join(os.environ['SPAWN_STATE'], 'wt.json'), 'w') as f:
    json.dump(args, f)
sys.exit(subprocess.run(['sh', script], stdin=subprocess.DEVNULL).returncode)
'''

# Steps of the spawn are instant; show_workers.sh's 5-second launch bound is a real wait.
SLEEP = '#!/bin/sh\n[ "$1" != 5 ] || exec /bin/sleep 5\nexit 0\n'


def shq(value):
    return "'" + value.replace("'", "'\\''") + "'"


@contextmanager
def safe_tmux_scratch(checkout=ROOT):
    """Use physical allowlisted scratch paths, independently of checkout spelling."""
    allowed = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./-'
    def safe(folder):
        return all(c in allowed for c in SpawnWorkerTests.physical(Path(folder) / 'run.sh'))
    folder = tempfile.mkdtemp(prefix='kit-tmux-')
    if not safe(folder):
        shutil.rmtree(folder)
        folder = None
        for base in (checkout,):
            if not safe(base):
                continue
            base.mkdir(parents=True, exist_ok=True)
            candidate = tempfile.mkdtemp(prefix='kit-tmux-', dir=base)
            if safe(candidate):
                folder = candidate
                break
            shutil.rmtree(candidate)
        if folder is None:
            raise AssertionError('Cannot allocate tmux fixture: system temp and scratch fallbacks are outside the path allowlist')
    try:
        yield folder
    finally:
        shutil.rmtree(folder)

# The stub accepts a launch, signals its parent, and leaves consumption to the test.
ACCEPT_THEN_TERM = '#!/bin/sh\nif [ "$1" = has-session ]; then [ -f "$SPAWN_STATE/accepted" ]; exit $?; fi\n[ "$1" = new-session ] || exit 1\nfor arg do command=$arg; done\nprintf "%s\\n" "$command" > "$SPAWN_STATE/accepted"\nkill -TERM "$PPID"\n/bin/sleep .1\nexit 0\n'
# Interrupt after mktemp, during validation, before any launch has been accepted.
PRELAUNCH_TERM = '#!/bin/sh\nkill -TERM "$(cat "$SPAWN_STATE/launcher.pid")"\n/bin/sleep .1\nexit 1\n'
FAIL_THEN_INT = '#!/bin/sh\n[ "$1" = new-session ] || exit 1\nkill -INT "$(cat "$SPAWN_STATE/launcher.pid")"\nkill -INT "$$"\nexit 1\n'


def run_with_launcher_pid(shell, script, args, **kwargs):
    # $$ is the launcher's shell pid even when the signaller runs in a command substitution.
    return subprocess.run([shell, '-c', 'printf "%s\\n" "$$" > "$SPAWN_STATE/launcher.pid"; . "$0"',
                           str(script).replace('\\', '/'), *args], **kwargs)


WINDOWS = os.name == 'nt'
# The cases that run on native Windows (issue #56). Every other case drives the tmux path,
# which native Windows never takes, through Python stubs whose `sh -c` command line Git for
# Windows parses again (an apostrophe is a quote there): declare those platform skips.
ON_WINDOWS = {'test_a_backend_reaches_the_worker_quoted_on_both_paths',
              'test_a_worker_worktree_is_locked_from_spawn',
              'test_a_worker_is_resumed_through_the_kit_under_its_name',
              'test_a_missing_or_failing_watcher_stops_the_spawn',
              'test_a_worker_without_its_model_or_effort_is_refused',
              'test_backend_duplicate_keys_cannot_empty_final_values',
              'test_backend_nul_and_nonregular_files_refuse_before_launch',
              'test_backend_replaces_every_inherited_anthropic_variable',
              'test_backend_requires_nonempty_token_before_worker_launch',
              'test_backend_secrets_must_be_ignored_and_untracked',
              'test_backend_token_is_absent_from_recorded_launch_commands',
              'test_backend_whitespace_lines_use_the_review_grammar',
              'test_backend_worker_clears_each_claude_credential_and_routing_control',
              'test_backend_worker_refuses_case_variant_of_tracked_path',
              'test_backend_worker_refuses_claude_model_id',
              'test_int_before_tmux_creates_session_removes_script',
              'test_missing_or_unreadable_brief_is_refused_before_any_session',
              'test_native_windows_generated_path_boundary',
              'test_no_error_message_echoes_a_control_character',
              'test_on_native_windows_the_worker_gets_state_hooks_and_keeps_its_own',
              'test_on_native_windows_the_worker_opens_as_a_windows_terminal_tab',
              'test_term_after_tmux_accepts_preserves_the_panes_script',
              'test_the_printed_resume_restores_the_launch',
              'test_a_worker_that_publishes_its_result_ends_and_its_tab_closes',
              'test_the_behaviour_appendix_reaches_the_worker_unless_turned_off',
              'test_two_signals_do_not_repeat_cleanup',
              'test_unsafe_names_are_refused_without_changing_worker_files',
              'test_worker_name_boundary_fits_every_generated_filename'}
ON_WINDOWS.update({'test_copied_hooks_allow_done_without_hiding_other_changes',
                   'test_worktree_accepts_backslash_windows_settings',
                   'test_worktree_inherits_untracked_project_hooks',
                   'test_worktree_keeps_tracked_project_hooks_without_copying_them',
                   'test_worktree_inherits_untracked_hooks_and_bom_settings',
                   'test_worktree_accepts_absolute_windows_settings',
                   'test_bad_settings_leave_no_worktree_or_branch',
                   'test_copied_hooks_never_hide_the_leads_own_files',
                   'test_a_spawn_that_fails_before_its_launch_leaves_no_worktree_or_branch',
                   'test_a_spawn_that_fails_after_its_launch_keeps_the_worktree_and_says_how_to_remove_it',
                   'test_plain_tmux_spawn_clears_stale_state_before_readiness'})


def tmux_path_cases(cls):
    for name in [n for n in vars(cls) if n.startswith('test_') and n not in ON_WINDOWS and WINDOWS]:
        test = unittest.skip('the tmux path, POSIX only')(getattr(cls, name))
        test._kit_platform_skip = True
        setattr(cls, name, test)
    return cls


@tmux_path_cases
class SpawnWorkerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # The caller's folder is named through a symlink, as macOS names every temp folder
        # (/var -> /private/var): every path handed on must be the physical one, by construction.
        (self.tmp / 'real').mkdir()
        (self.tmp / 'via').symlink_to(self.tmp / 'real')
        self.state, self.bin, self.cwd = self.tmp / 'state', self.tmp / 'bin', self.tmp / 'via' / "lead's dir"
        for folder in (self.state, self.bin, self.cwd):
            folder.mkdir()
        for name, body in (('tmux', TMUX), ('claude', CLAUDE), ('sleep', SLEEP), ('wt-stub', WT),
                           ('osascript', '#!/bin/sh\nexit 1\n'), ('uname', '#!/bin/sh\necho Linux\n')):
            # UTF-8: the tmux stub holds the prompt arrow, which cp1252 (native Windows) cannot write.
            (self.bin / name).write_text(body, encoding='utf-8')
            (self.bin / name).chmod(0o755)
        if WINDOWS:
            # Native Windows' python3 may be an inaccessible WindowsApps alias. Every
            # shebang fixture uses this runner's interpreter, never a host alias.
            (self.bin / 'python3').write_text('#!/bin/sh\nexec ' +
                                            shq(sys.executable.replace('\\', '/')) + ' "$@"\n')
            (self.bin / 'python3').chmod(0o755)
        self.brief = self.cwd / "it's the brief.md"
        self.brief.write_text('Line one of the brief.\nLine two.\n')

    def tearDown(self):
        self._tmp.cleanup()

    @staticmethod
    def physical(path):
        # What the script hands on: the folder resolved (`pwd -P`), the file name as given.
        # Git for Windows' `pwd -P` spells the folder its own way (/tmp/..., /c/...).
        if WINDOWS:
            # MSYS must receive literal path characters, including dollar signs and backquotes.
            env = dict(os.environ, SPAWN_PHYSICAL_DIR=os.path.realpath(path.parent))
            folder = subprocess.run(['sh', '-c', 'cygpath -u "$SPAWN_PHYSICAL_DIR"'], env=env,
                                    capture_output=True, text=True, check=True).stdout.rstrip('\n')
            return folder + '/' + path.name
        return os.path.join(os.path.realpath(path.parent), path.name)

    def spawn(self, *args, choose=True, **extra):
        # PWD as a lead's shell exports it: with it, a plain `pwd` printed the symlinked spelling.
        env = dict(self.base_env(), PWD=str(self.cwd))
        env.update(extra)
        for name in [name for name, value in env.items() if value is None]:
            env.pop(name)
        # The lead chooses model and effort for every worker; a case that is not about them
        # passes both. choose=False sends the arguments exactly as given.
        if choose:
            args += tuple(a for flag, value in (('--model', 'm'), ('--effort', 'high'))
                          if flag not in args for a in (flag, value))
        return subprocess.run(['sh', str(getattr(self, 'script', SCRIPT)), *args], cwd=self.cwd, env=env,
                              capture_output=True, text=True, timeout=60)

    def base_env(self):
        # Never the host's terminal: the WSL name is the test's own, so wt.exe is the stub.
        env = {k: v for k, v in os.environ.items() if k not in ('TERM_PROGRAM', 'TMUX', 'TMUX_PANE')
               and not k.startswith(('ANTHROPIC_', 'KIT_WORKER_'))}
        return dict(env, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}', SPAWN_STATE=str(self.state),
                    WSL_DISTRO_NAME='Test-1', KIT_WT=str(self.bin / 'wt-stub'), **LEAD_ENV)

    def launched(self):
        path = self.state / 'claude.json'
        return json.loads(path.read_text()) if path.exists() else None

    def tmux_log(self):
        path = self.state / 'tmux.log'
        return path.read_text() if path.exists() else ''

    def test_term_after_tmux_accepts_preserves_the_panes_script(self):
        (self.bin / 'tmux').write_text(ACCEPT_THEN_TERM, newline='\n')
        tmpdir = self.tmp / 'session-temp'
        tmpdir.mkdir()
        result = self.spawn('accepted', str(self.brief), TMPDIR=str(tmpdir))
        self.assertEqual(len(list(tmpdir.iterdir())), 1, 'parent deleted the accepted script')
        self.assertEqual(result.returncode, 143, result.stdout + result.stderr)
        pane = subprocess.run(['sh', '-c', (self.state / 'accepted').read_text()],
                              cwd=self.cwd, env=self.base_env(), capture_output=True, text=True, timeout=20)
        self.assertEqual(pane.returncode, 0, pane.stdout + pane.stderr)
        self.assertIsNotNone(self.launched(), 'the delayed pane could not start')
        self.assertEqual(list(tmpdir.iterdir()), [])

    def test_dash_term_before_launch_removes_the_reserved_script(self):
        if not shutil.which('dash'):  # Fedora, Arch and FreeBSD ship none
            sys.stderr.write('\nNOT RUN: %s (no dash on this host)\n' % self.id())
            return
        # Keep an extra parent between git's signaller and the command-substitution shell.
        (self.bin / 'git').write_text('#!/bin/sh\nsh -c ' + shq(PRELAUNCH_TERM) + '\nexit 1\n', newline='\n')
        (self.bin / 'git').chmod(0o755)
        tmpdir = self.tmp / 'session-temp'
        tmpdir.mkdir()
        result = run_with_launcher_pid('dash', SCRIPT, ['interrupted', str(self.brief),
                                 '--model', 'm', '--effort', 'high', '--worktree'],
                                cwd=self.cwd, env=dict(self.base_env(), TMPDIR=str(tmpdir)),
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 143, result.stdout + result.stderr)
        self.assertEqual(list(tmpdir.iterdir()), [])
        self.assertIsNone(self.launched())

    def test_int_before_tmux_creates_session_removes_script(self):
        (self.bin / 'tmux').write_text(FAIL_THEN_INT, newline='\n')
        tmpdir = self.tmp / 'session-temp'
        tmpdir.mkdir()
        result = run_with_launcher_pid('sh', SCRIPT, ['interrupted', str(self.brief),
                                      '--model', 'm', '--effort', 'high'], cwd=self.cwd,
                                      env=dict(self.base_env(), TMPDIR=str(tmpdir)),
                                      capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 130, result.stdout + result.stderr)
        self.assertEqual(list(tmpdir.iterdir()), [])
        self.assertIsNone(self.launched())

    def test_two_signals_do_not_repeat_cleanup(self):
        (self.bin / 'git').write_text(PRELAUNCH_TERM, newline='\n')
        (self.bin / 'git').chmod(0o755)
        (self.bin / 'rm').write_text('''#!/bin/sh
echo unlink >> "$SPAWN_STATE/cleanup.log"
/bin/rm "$@"
if [ "$(wc -l < "$SPAWN_STATE/cleanup.log")" -eq 1 ]; then
  kill -INT "$(cat "$SPAWN_STATE/launcher.pid")"
  kill -TERM "$(cat "$SPAWN_STATE/launcher.pid")"
fi
exit 0
''', newline='\n')
        (self.bin / 'rm').chmod(0o755)
        tmpdir = self.tmp / 'session-temp'
        tmpdir.mkdir()
        result = run_with_launcher_pid('sh', SCRIPT, ['interrupted', str(self.brief),
                                      '--model', 'm', '--effort', 'high', '--worktree'], cwd=self.cwd,
                                      env=dict(self.base_env(), TMPDIR=str(tmpdir)),
                                      capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.state / 'cleanup.log').read_text().splitlines(), ['unlink'])
        self.assertEqual(list(tmpdir.iterdir()), [])

    def test_unsafe_tmpdir_is_refused_before_tmux_can_expand_it(self):
        for folder in ('temp$(touch INJECTED)', 'temp`touch INJECTED`', 'temp$REVIEW_SEGMENT'):
            with self.subTest(folder=folder):
                tmpdir = self.tmp / folder
                tmpdir.mkdir()
                result = self.spawn('unsafe-temp', str(self.brief), TMPDIR=str(tmpdir))
                self.assertFalse((self.cwd / 'INJECTED').exists(), 'TMPDIR ran as shell code')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('TMPDIR', result.stderr)
                self.assertNotIn("'new-session'", self.tmux_log())
                self.assertIsNone(self.launched())
                self.assertEqual(list(tmpdir.iterdir()), [], 'the refused script was left behind')

    def test_tmpdir_with_a_space_is_refused_by_name(self):
        tmpdir = self.tmp / 'temp space'
        tmpdir.mkdir()
        result = self.spawn('spaced-temp', str(self.brief), TMPDIR=str(tmpdir))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('TMPDIR', result.stderr)
        self.assertNotIn("'new-session'", self.tmux_log())
        self.assertIsNone(self.launched())
        self.assertEqual(list(tmpdir.iterdir()), [])

    def test_refused_tmpdir_with_worktree_leaves_no_worktree_or_branch(self):
        subprocess.run(['git', 'init', '-q'], cwd=self.cwd, check=True, capture_output=True)
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q',
                        '--allow-empty', '-m', 'base'], cwd=self.cwd, check=True, capture_output=True)
        tmpdir = self.tmp / 'refused temp'
        tmpdir.mkdir()
        result = self.spawn('refused-temp', str(self.brief), '--worktree', TMPDIR=str(tmpdir))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('TMPDIR', result.stderr)
        self.assertFalse((self.cwd / '.claude/worktrees/refused-temp').exists())
        trees = subprocess.run(['git', 'worktree', 'list', '--porcelain'], cwd=self.cwd,
                               capture_output=True, text=True, check=True).stdout
        self.assertNotIn('refused-temp', trees)
        branches = subprocess.run(['git', 'branch', '--list', 'worktree-refused-temp'], cwd=self.cwd,
                                  capture_output=True, text=True, check=True).stdout
        self.assertEqual(branches, '')
        self.assertEqual(list(tmpdir.iterdir()), [])

    def test_later_validation_failure_removes_the_reserved_session_script(self):
        tmpdir = self.tmp / 'session-temp'
        tmpdir.mkdir()
        result = self.spawn('late-failure', str(self.brief), '--settings', 'absent.json', '--worktree', TMPDIR=str(tmpdir))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('--settings is neither', result.stderr)
        self.assertEqual(list(tmpdir.iterdir()), [], 'the reserved script was left behind')

    def test_relative_tmpdir_launches_in_a_worktree_with_an_absolute_script_path(self):
        subprocess.run(['git', 'init', '-q'], cwd=self.cwd, check=True, capture_output=True)
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q',
                        '--allow-empty', '-m', 'base'], cwd=self.cwd, check=True, capture_output=True)
        tmpdir = self.cwd.parent / 'session-temp'
        tmpdir.mkdir()
        result = self.spawn('relative-temp', str(self.brief), '--worktree', TMPDIR='../session-temp')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(Path(self.launched()['cwd']).resolve(),
                         (self.cwd / '.claude/worktrees/relative-temp').resolve())
        self.assertIn('sh ' + str(tmpdir.resolve()) + '/', self.tmux_log())
        self.assertEqual(list(tmpdir.iterdir()), [], 'the launched script did not remove itself')
    def backend_file(self, text):
        # Exercise the installed layout: the overlay worker and review companions share scripts/.
        scripts = self.cwd / 'scripts'
        if not scripts.exists():
            shutil.copytree(SCRIPT.parent, scripts)
            for source in (ROOT / 'core/scripts').glob('*.py'):
                if not source.name.startswith('test_'):
                    shutil.copyfile(source, scripts / source.name)
            self.script = scripts / SCRIPT.name
            subprocess.run(['git', 'init', '-q', str(self.cwd)], check=True, capture_output=True)
            (self.cwd / '.gitignore').write_bytes((ROOT / 'core/.gitignore').read_bytes())
        path = self.cwd / '.myagentkit/backends/glm.env'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode('utf-8'))
        return path

    def backend_paths(self):
        if not WINDOWS:
            (self.bin / 'uname').write_text('#!/bin/sh\necho Linux\n')
            yield {}
        for name, body in (('uname', '#!/bin/sh\necho MINGW64_NT-10.0-26200\n'), ('cygpath', CYGPATH),
                           ('wt-tab', WT_TAB), ('ps-stub', '#!/bin/sh\n[ ! -f "$SPAWN_STATE/claude.json" ] || '
                                                          'printf "8 claude.exe -n w1\\r\\n"\n')):
            if WINDOWS and name == 'cygpath':
                continue
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        config = self.tmp / 'config'
        (config / 'sessions').mkdir(parents=True, exist_ok=True)
        (config / 'sessions/8.json').write_text('{}')
        yield dict(KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=str(self.bin / 'ps-stub'),
                   CLAUDE_CONFIG_DIR=str(config))

    def test_backend_secrets_must_be_ignored_and_untracked(self):
        token = 'backend-private-test-token'
        self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n'
                          'ANTHROPIC_AUTH_TOKEN=' + token + '\n')
        for tracked in (False, True):
            (self.cwd / '.gitignore').write_text('/.myagentkit/usage/\n')
            if tracked:
                subprocess.run(['git', '-C', str(self.cwd), 'add', '-f', '.myagentkit/backends/glm.env'],
                               check=True, capture_output=True)
                (self.cwd / '.gitignore').write_text('/.myagentkit/\n')
            for tab in self.backend_paths():
                result = self.spawn('w1', str(self.brief), '--backend', 'glm', **tab)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('must be Git-ignored and untracked', result.stderr)
                self.assertNotIn(token, result.stdout + result.stderr)
                self.assertIsNone(self.launched())
                self.assertNotIn('new-session', self.tmux_log())
                self.assertFalse((self.state / 'wt.json').exists())

    def test_backend_worker_clears_each_claude_credential_and_routing_control(self):
        self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n'
                          'ANTHROPIC_AUTH_TOKEN=fixture\n')
        # Independent of the production list, including on Windows.
        keys = (
            'CLAUDE_CODE_API_BASE_URL',
            'CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR',
            'CLAUDE_CODE_API_KEY_HELPER_TTL_MS',
            'CLAUDE_CODE_ARTIFACTS_API_BASE_URL',
            'CLAUDE_CODE_ARTIFACTS_API_TOKEN',
            'CLAUDE_CODE_ARTIFACT_ASSET_BASE_URL',
            'CLAUDE_CODE_ARTIFACT_LIVE_BASE_URL',
            'CLAUDE_CODE_ARTIFACT_SYNC_BASE_URL',
            'CLAUDE_CODE_ARTIFACT_VIEWER_BASE_URL',
            'CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL',
            'CLAUDE_CODE_AUTO_MODE_MODEL',
            'CLAUDE_CODE_AWS_CHAIN_RESOLVE_TIMEOUT_MS',
            'CLAUDE_CODE_BG_CLASSIFIER_MODEL',
            'CLAUDE_CODE_CLIENT_CERT',
            'CLAUDE_CODE_CLIENT_KEY',
            'CLAUDE_CODE_CLIENT_KEY_PASSPHRASE',
            'CLAUDE_CODE_CUSTOM_OAUTH_URL',
            'CLAUDE_CODE_DESIGN_OAUTH_CLIENT_ID',
            'CLAUDE_CODE_DISABLE_AUTH_REFRESH_LOCK',
            'CLAUDE_CODE_ENABLE_PROXY_AUTH_HELPER',
            'CLAUDE_CODE_GATEWAY_HINT_HEADERS',
            'CLAUDE_CODE_GATEWAY_TOKEN',
            'CLAUDE_CODE_GATEWAY_TOKEN_FILE_DESCRIPTOR',
            'CLAUDE_CODE_GB_BASE_URL',
            'CLAUDE_CODE_HFI_BEARER_TOKEN',
            'CLAUDE_CODE_HOST_AUTH_ENV_VAR',
            'CLAUDE_CODE_HOST_AUTH_REFRESH_TIMEOUT_MS',
            'CLAUDE_CODE_HOST_GATEWAY_LINEAGE',
            'CLAUDE_CODE_HOST_HTTP_PROXY_PORT',
            'CLAUDE_CODE_HOST_SOCKS_PROXY_PORT',
            'CLAUDE_CODE_HTTPS_PROXY',
            'CLAUDE_CODE_HTTP_PROXY',
            'CLAUDE_CODE_MCP_SERVE_AUTH_TOKEN',
            'CLAUDE_CODE_MEMORY_API_BASE_URL',
            'CLAUDE_CODE_MEMORY_API_TOKEN',
            'CLAUDE_CODE_MESSAGING_TOKEN',
            'CLAUDE_CODE_METRICS_ENDPOINT',
            'CLAUDE_CODE_MODEL_CATALOG_URL',
            'CLAUDE_CODE_OAUTH_CLIENT_ID',
            'CLAUDE_CODE_OAUTH_REFRESH_TOKEN',
            'CLAUDE_CODE_OAUTH_SCOPES',
            'CLAUDE_CODE_OAUTH_TOKEN',
            'CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR',
            'CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST',
            'CLAUDE_CODE_PROXY_AUTHENTICATE',
            'CLAUDE_CODE_PROXY_AUTH_HELPER_TTL_MS',
            'CLAUDE_CODE_PROXY_HOST',
            'CLAUDE_CODE_PROXY_RESOLVES_HOSTS',
            'CLAUDE_CODE_PROXY_URL',
            'CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH',
            'CLAUDE_CODE_SDK_HAS_OAUTH_REFRESH',
            'CLAUDE_CODE_SESSION_ACCESS_TOKEN',
            'CLAUDE_CODE_SKIP_ANTHROPIC_AWS_AUTH',
            'CLAUDE_CODE_SKIP_ANTHROPIC_GOOGLE_CLOUD_AUTH',
            'CLAUDE_CODE_SKIP_AWS_CRED_CACHE',
            'CLAUDE_CODE_SKIP_BEDROCK_AUTH',
            'CLAUDE_CODE_SKIP_FOUNDRY_AUTH',
            'CLAUDE_CODE_SKIP_MANTLE_AUTH',
            'CLAUDE_CODE_SKIP_VERTEX_AUTH',
            'CLAUDE_CODE_SLACK_TAG_TOKEN',
            'CLAUDE_CODE_SUBAGENT_MODEL',
            'CLAUDE_CODE_SUBAGENT_MODEL_FORCE',
            'CLAUDE_CODE_USE_ANTHROPIC_AWS',
            'CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD',
            'CLAUDE_CODE_USE_BEDROCK',
            'CLAUDE_CODE_USE_CCR_V',
            'CLAUDE_CODE_USE_FOUNDRY',
            'CLAUDE_CODE_USE_GATEWAY',
            'CLAUDE_CODE_USE_MANTLE',
            'CLAUDE_CODE_USE_VERTEX',
            'CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR',
            'CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL',
        )
        for tab in self.backend_paths():
            result = self.spawn('w1', str(self.brief), '--backend', 'glm', **tab,
                                SPAWN_CONTROL_NAMES=','.join(keys), **dict.fromkeys(keys, 'lead-control'))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for key in keys:
                with self.subTest(key=key, tab=bool(tab)):
                    self.assertNotIn(key, self.launched()['env'])
            (self.state / 'claude.json').unlink()

    def test_backend_requires_nonempty_token_before_worker_launch(self):
        for token in ('', 'ANTHROPIC_AUTH_TOKEN=\n'):
            self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n' + token)
            for tab in self.backend_paths():
                result = self.spawn('w1', str(self.brief), '--backend', 'glm', **tab)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('sets no ANTHROPIC_AUTH_TOKEN', result.stderr)
                self.assertIsNone(self.launched())

    def test_backend_worker_refuses_claude_model_id(self):
        self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n'
                          'ANTHROPIC_AUTH_TOKEN=fixture\n')
        for tab in self.backend_paths():
            result = self.spawn('w1', str(self.brief), '--model', 'claude-opus-5', '--backend', 'glm', **tab)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('not a claude- model', result.stderr)
            self.assertIsNone(self.launched())

    def test_backend_worker_refuses_case_variant_of_tracked_path(self):
        self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n'
                          'ANTHROPIC_AUTH_TOKEN=fixture\n')
        subprocess.run(['git', '-C', str(self.cwd), 'add', '-f', '.myagentkit/backends/glm.env'],
                       check=True, capture_output=True)
        for tab in self.backend_paths():
            result = self.spawn('w1', str(self.brief), '--backend', 'GLM', **tab)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('Git-ignored and untracked', result.stderr)
            self.assertIsNone(self.launched())

    def test_backend_replaces_every_inherited_anthropic_variable(self):
        expected = {'ANTHROPIC_BASE_URL': 'https://backend.invalid', 'ANTHROPIC_MODEL': 'glm-x',
                    'ANTHROPIC_AUTH_TOKEN': 'backend-token'}
        self.backend_file(''.join('%s=%s\n' % item for item in expected.items()))
        inherited = {'ANTHROPIC_API_KEY': 'lead-key', 'ANTHROPIC_CUSTOM_HEADERS': 'lead-header',
                     'ANTHROPIC_DEFAULT_SONNET_MODEL': 'lead-model', 'ANTHROPIC_FUTURE_SETTING': 'lead-value',
                     'ANTHROPIC_mixed_case': 'lead-mixed-case',
                     **({'Anthropic_Api_Key': 'lead-lower-prefix'} if WINDOWS else {})}
        for tab in self.backend_paths():
            result = self.spawn('w1', str(self.brief), '--backend', 'glm', **tab, **inherited)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.launched()['env'], expected)
            (self.state / 'claude.json').unlink()

        # If env cannot supply raw names, the child must refuse rather than keep credentials.
        real_env = shutil.which('env').replace('\\', '/')
        (self.bin / 'env').write_text('#!/bin/sh\n[ "$1" != -0 ] || exit 1\nexec ' + shq(real_env) + ' "$@"\n')
        (self.bin / 'env').chmod(0o755)
        result = self.spawn('w1', str(self.brief), '--backend', 'glm', **tab, **inherited)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('cannot read the child environment names', result.stderr)
        self.assertIsNone(self.launched())

    def test_backend_token_is_absent_from_recorded_launch_commands(self):
        token = 'launch-record-secret-token'
        self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n'
                          'ANTHROPIC_AUTH_TOKEN=' + token + '\n')
        for tab in self.backend_paths():
            result = self.spawn('w1', str(self.brief), '--backend', 'glm', **tab)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.launched()['env']['ANTHROPIC_AUTH_TOKEN'], token)
            recorded = self.tmux_log()
            if tab:
                recorded += (self.state / 'wt.json').read_text()
            self.assertNotIn(token, recorded + result.stdout + result.stderr)
            (self.state / 'claude.json').unlink()

    def test_a_worker_that_publishes_its_result_ends_and_its_tab_closes(self):
        # Owner 2026-10-16: a Claude worker's session and tab close when it publishes Kind:
        # completed, as a Codex worker's do (codex_worker.py), not only at the merge. A progress
        # result or a free-form file never ends it. The tab's script then runs on to `exit 0`.
        report = self.tmp / 'report.md'
        done = 'Kind: completed\nTask: t\nAttempt: 1\nRemaining: none\n<!-- codex-worker: ready -->\n'
        for tab in self.backend_paths():
            for text, ends in ((done, True), (done.replace('completed', 'progress'), False), ('# notes\n', False)):
                with self.subTest(windows=bool(tab), text=text[:15]):
                    for path in (self.state / 'finished', self.state / 'claude.json', report):
                        path.unlink(missing_ok=True)
                    result = self.spawn('w1', str(self.brief), '--result', str(report), **tab, SPAWN_PUBLISH=text,
                                        SPAWN_PUBLISH_TO=str(report), SPAWN_LINGER='4', KIT_WORKER_GRACE='0.2')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual((self.state / 'finished').exists(), not ends, result.stdout + result.stderr)
                    # Codex r2 (fix56): a publication within ten seconds is no failed start; the
                    # tab closes instead of waiting for Enter (this stub's closed stdin hid it).
                    self.assertEqual('press Enter to close' in result.stdout + result.stderr, bool(tab) and not ends,
                                     result.stdout + result.stderr)
                    if tab:
                        self.assertTrue(json.loads((self.state / 'wt.json').read_text())[-1].endswith('\nexit 0\n'))
        # The result path is recorded: close_worker.sh --finished reads it after a merge.
        (record,) = (self.tmp / 'real').rglob('w1.result-path')
        self.assertTrue(record.read_text().strip().endswith('/report.md'), record.read_text())

    def test_the_printed_resume_restores_the_launch(self):
        # Codex r1 (fix56): the printed resume dropped --backend; followed, the worker went on
        # against the default provider without its endpoint, model mapping or settings.
        self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n'
                          'ANTHROPIC_AUTH_TOKEN=fixture\n')
        settings, tools = '{"permissions": {"defaultMode": "auto"}}', 'Bash(git status:*)'
        for tab in self.backend_paths():
            result = self.spawn('w1', str(self.brief), '--backend', 'glm', '--model', 'glm-x',
                                '--settings', settings, '--allowed-tools', tools, '--result', 'report.md', **tab)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            line = next(l for l in result.stdout.splitlines() if 'to answer it in its own session' in l)
            for words in ("--model 'glm-x'", "--backend 'glm'", '--settings ' + shq(settings),
                          '--allowed-tools ' + shq(tools), "--result 'report.md'"):
                self.assertIn(words, line)
            (self.state / 'claude.json').unlink()

    def test_backend_duplicate_keys_cannot_empty_final_values(self):
        for key, reason in (('ANTHROPIC_BASE_URL', 'sets no ANTHROPIC_BASE_URL'),
                            ('ANTHROPIC_MODEL', 'sets no model')):
            self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n'
                              + key + '=\n')
            for tab in self.backend_paths():
                result = self.spawn('w1', str(self.brief), '--backend', 'glm', **tab)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(reason, result.stderr)
                self.assertIsNone(self.launched())

    def test_backend_whitespace_lines_use_the_review_grammar(self):
        expected = {'ANTHROPIC_BASE_URL': 'https://backend.invalid', 'ANTHROPIC_MODEL': 'glm-x',
                    'ANTHROPIC_AUTH_TOKEN': 'backend-token'}
        self.backend_file(' \t\r\n  # ignored comment\r\n' +
                          ''.join('  %s=%s  \r\n' % item for item in expected.items()))
        for tab in self.backend_paths():
            result = self.spawn('w1', str(self.brief), '--backend', 'glm', **tab)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.launched()['env'], expected)
            (self.state / 'claude.json').unlink()

    def test_backend_nul_and_nonregular_files_refuse_before_launch(self):
        path = self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n'
                                 'ANTHROPIC_AUTH_TOKEN=private\x00value\n')
        for tab in self.backend_paths():
            result = self.spawn('w1', str(self.brief), '--backend', 'glm', **tab)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn('private', result.stdout + result.stderr)
            self.assertIsNone(self.launched())
        path.unlink()
        path.mkdir()
        for tab in self.backend_paths():
            result = self.spawn('w1', str(self.brief), '--backend', 'glm', **tab)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('regular file', result.stderr)
            self.assertIsNone(self.launched())

    def test_values_with_apostrophes_arrive_intact_and_run_nothing(self):
        marker = self.tmp / 'injected'
        # Each value holds an even number of apostrophes, so under unescaped quoting every
        # $(...) lands outside quotes and runs; escaped, each arrives as written.
        name = "obrien"
        settings = json.dumps({'note': f"'$(touch {marker})'"})
        model, effort = "m'x'", f"high'$(touch {marker})'"
        tools = "Bash(echo 'a b'),Read"
        result = self.spawn(name, str(self.brief), '--model', model, '--effort', effort,
                            '--settings', settings, '--allowed-tools', tools)
        self.assertFalse(marker.exists(), 'an interpolated value ran as shell')
        launched = self.launched()
        self.assertIsNotNone(launched, result.stderr)
        self.assertEqual(launched['argv'], ['-n', name, '--model', model, '--effort', effort,
                                            '--settings', settings, '--allowedTools', tools,
                                            '--disallowedTools', 'AskUserQuestion'])
        self.assertEqual(Path(launched['cwd']).resolve(), self.cwd.resolve())
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_worker_without_its_model_or_effort_is_refused(self):
        # docs/WORKFLOW.md, "Model routing": neither is left to the user's default.
        for args, missing in ((('--effort', 'high'), '--model'), (('--model', 'm'), '--effort'), ((), '--model')):
            with self.subTest(args=args):
                result = self.spawn('w1', str(self.brief), *args, choose=False)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('spawn_worker: %s is required' % missing, result.stderr)
                self.assertIsNone(self.launched(), 'a worker started without its model or effort')
                self.assertEqual(self.tmux_log(), '')

    def test_unsafe_names_are_refused_without_changing_worker_files(self):
        (self.bin / 'uname').write_text('#!/bin/sh\necho MINGW64_NT-10.0\n')
        (self.bin / 'ps-empty').write_text('#!/bin/sh\nexit 0\n')
        (self.bin / 'ps-empty').chmod(0o755)
        (self.bin / 'wt-refuse').write_text('#!/bin/sh\nexit 99\n')
        (self.bin / 'wt-refuse').chmod(0o755)
        workers = self.cwd / '.myagentkit/workers'
        workers.mkdir(parents=True)
        for path in (workers / 'w1.state', workers / 'w1.watch-state',
                     workers.parent / 'victim.settings.json'):
            path.write_bytes(b'keep this\n')
        def snapshot():
            return {str(p.relative_to(workers.parent)): p.read_bytes() if p.is_file() else None
                    for p in workers.parent.rglob('*')}
        before = snapshot()
        for name in ('../victim', r'..\victim', 'a/b', "o'brien", '-bad', ''):
            with self.subTest(name=name):
                result = self.spawn(name, str(self.brief), KIT_PS=str(self.bin / 'ps-empty'),
                                    KIT_WT=str(self.bin / 'wt-refuse'))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('refused the worker name', result.stderr)
                self.assertEqual(snapshot(), before)
                self.assertIsNone(self.launched())

    def test_worker_name_boundary_fits_every_generated_filename(self):
        # Exercise the filename rule everywhere, independently of Windows' tighter path rule.
        result = self.spawn('w' * 241, str(self.brief), choose=False)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('refused the worker name', result.stderr)
        self.assertIn('255 bytes', result.stderr)
        self.assertFalse((self.cwd / '.myagentkit/workers').exists())
        result = self.spawn('w' * 240, str(self.brief), choose=False)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('--model is required', result.stderr)
        if WINDOWS:
            return  # the full-path test below publishes the hook's file on Windows
        workers = self.cwd / '.myagentkit/workers'
        workers.mkdir(parents=True)
        name = 'w' * 240
        state = workers / (name + '.state')
        replace = os.replace
        def publish(source, target):
            self.assertEqual(len(os.fsencode(Path(source).name)), 255)
            replace(source, target)
        with patch('os.replace', side_effect=publish):
            run_state_hook(state, {'hook_event_name': 'Stop'})
        self.assertTrue(state.read_text().startswith('idle '))

    def test_native_windows_generated_path_boundary(self):
        (self.bin / 'uname').write_text('#!/bin/sh\necho MINGW64_NT-10.0\n')
        (self.bin / 'ps-empty').write_text('#!/bin/sh\nexit 0\n')
        (self.bin / 'ps-empty').chmod(0o755)
        (self.bin / 'wt-refuse').write_text('#!/bin/sh\nexit 99\n')
        (self.bin / 'wt-refuse').chmod(0o755)
        if not WINDOWS:
            (self.bin / 'cygpath').write_text(CYGPATH)
            (self.bin / 'cygpath').chmod(0o755)
        workers = self.cwd / '.myagentkit/workers'
        # Pass the hook its actual physical path, as spawn does after cygpath conversion.
        workers = Path(os.path.realpath(workers))
        # Measure the same physical, native spelling that the hook uses.
        if WINDOWS:
            native = Path(os.path.realpath(workers)).as_posix()
        else:
            native = 'C:' + os.path.realpath(workers)
        name = 'w' * (259 - len(native + '/.state.XXXXXXXX'))
        self.assertGreater(len(name), 0)
        self.assertLessEqual(len(name), 240)
        result = self.spawn(name + 'w', str(self.brief), KIT_PS=str(self.bin / 'ps-empty'),
                            KIT_WT=str(self.bin / 'wt-refuse'))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('259 characters', result.stderr)
        for remedy in ('shorter name', 'shorter checkout path', 'LongPathsEnabled'):
            self.assertIn(remedy, result.stderr)
        self.assertFalse(workers.exists(), 'an overlong path changed worker files')
        result = self.spawn(name, str(self.brief), KIT_PS=str(self.bin / 'ps-empty'),
                            KIT_WT=str(self.bin / 'wt-refuse'))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('could not open a tab', result.stderr)
        self.assertTrue((workers / (name + '.settings.json')).is_file())
        state = workers / (name + '.state')
        replace = os.replace
        def publish(source, target):
            source_path = Path(source).as_posix()
            if not WINDOWS:
                source_path = 'C:' + os.path.realpath(source_path)
            self.assertEqual(len(source_path), 259)
            self.assertLessEqual(len(os.fsencode(Path(source).name)), 255)
            replace(source, target)
        with patch('os.replace', side_effect=publish):
            run_state_hook(state, {'hook_event_name': 'Stop'})
        self.assertTrue(state.read_text().startswith('idle '))
        self.assertEqual(sorted(p.name for p in workers.iterdir()),
                         sorted([name + '.state', name + '.settings.json', name + '.result-path']))

    def test_brief_is_delivered_by_path_as_one_typed_instruction(self):
        result = self.spawn('w1', str(self.brief))
        self.assertEqual(result.returncode, 0, result.stderr)
        # Two sentences, ONE submitted line: the second keeps questions out of the pane.
        submitted = (self.state / 'submitted').read_text().splitlines()
        self.assertEqual(submitted, [INSTRUCTION % shq(self.physical(self.brief))])
        self.assertNotIn('Line one of the brief', (self.state / 'submitted').read_text())

    def test_on_native_windows_the_worker_opens_as_a_windows_terminal_tab(self):
        # No tmux there: the instruction is the session's first prompt, ahead of the variadic
        # --allowedTools, and the tab is the session's only view. A `;` in the brief path and
        # in a value proves the launcher is never handed a bare one.
        # On native Windows the real cygpath answers.
        for name, body in (('uname', '#!/bin/sh\necho MINGW64_NT-10.0-26200\n'), ('cygpath', CYGPATH),
                           ('wt-tab', WT_TAB)):
            if WINDOWS and name == 'cygpath':
                continue
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        brief = self.cwd / 'brief; part two.md'
        brief.write_text('A brief.\n')
        tools = 'Read,Bash(a; b)'
        # w2 always runs; w1 and w3 run once the claude stub has started.
        (self.bin / 'ps-stub').write_text('#!/bin/sh\nprintf "7 claude.exe -n w2\\r\\n"\n[ ! -f "$SPAWN_STATE/claude.json" ] || '
                                          'printf "8 claude.exe -n w1\\r\\n9 claude.exe -n w3\\r\\n"\n')
        (self.bin / 'ps-stub').chmod(0o755)
        ps = str(self.bin / 'ps-stub')
        config = self.tmp / 'config'
        (config / 'sessions').mkdir(parents=True)
        settings = '{"permissions": {"defaultMode": "auto"}}'
        result = self.spawn('w1', str(brief), '--model', 'm', '--settings', settings, '--allowed-tools', tools,
                            KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=ps, CLAUDE_CONFIG_DIR=str(config))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Windows Terminal tab', result.stdout)
        # The spend line comes before the start (issue #68).
        self.assertIn("spawn_worker: about to run 'w1': model m, effort high\n", result.stdout)
        # Not registered as a peer (no sessions/8.json): the lead is told it will hear nothing.
        self.assertIn("WARNING: 'w1' (process 8) is not registered as a peer session", result.stdout)
        self.assertIn('scripts/close_worker.sh w1', result.stdout)
        # The tab ends with `exit 0`, never as claude's own exit: Windows Terminal keeps a tab whose
        # command ended nonzero open, as claude does when close_worker.sh ends it. The script the
        # tab ran is deleted.
        tab = json.loads((self.state / 'wt.json').read_text())
        self.assertTrue(tab[-1].endswith('\nexit 0\n'), tab[-1])
        self.assertNotIn('exec claude', tab[-1])
        self.assertFalse(Path(tab[-2] if WINDOWS else tab[-2][2:].replace('\\', '/')).exists())
        # A name a running session already has is refused before any tab opens.
        (self.state / 'wt.json').unlink()
        result = self.spawn('w2', str(brief), KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=ps)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("a Claude Code session named 'w2' already runs (process 7)", result.stderr)
        self.assertFalse((self.state / 'wt.json').exists(), 'a tab opened for a name already running')
        launched = self.launched()
        self.assertIsNotNone(launched, result.stderr)
        # The brief by Windows' spelling of its path, which the worker's tools know.
        shown = (subprocess.run(['cygpath', '-m', self.physical(brief)], capture_output=True, text=True,
                                check=True).stdout.rstrip('\n') if WINDOWS else 'C:' + self.physical(brief))
        # --settings is the owner's settings with the worker's state hooks added (the next case).
        argv = launched['argv']
        merged = json.loads(Path(self.windows_path(argv[8])).read_text())
        self.assertEqual(merged['permissions'], {'defaultMode': 'auto'})
        self.assertEqual(argv[:8] + argv[9:], [INSTRUCTION % shq(shown), '-n', 'w1', '--model', 'm', '--effort',
                                               'high', '--settings', '--allowedTools', tools,
                                               '--disallowedTools', 'AskUserQuestion'])
        self.assertEqual(Path(launched['cwd']).resolve(), self.cwd.resolve())
        self.assertEqual(self.tmux_log(), '')
        # A worker is no child of the lead: the lead's session markers never reach it.
        self.assertFalse(MARKERS & set(launched['env_names']), launched['env_names'])
        self.assertIn('CLAUDE_CODE_EXECPATH', launched['env_names'])
        # Its cache outlives its waits (docs/WORKFLOW.md, "Worker cost", rule 1).
        self.assertIn('CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL', launched['env_names'])
        # Its report is for the lead: the plain-words Stop hook steps aside.
        self.assertIn('MYAGENTKIT_ROLE', launched['env_names'])
        self.assertFalse((self.state / 'wt.log').exists(), 'the tab was shown a second time')
        # Registered (sessions/9.json): the lead is told to subscribe, and no warning.
        (self.state / 'claude.json').unlink()
        (config / 'sessions' / '9.json').write_text('{}')
        result = self.spawn('w3', str(brief), KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=ps, CLAUDE_CONFIG_DIR=str(config))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("'w3' is a peer session (process 9)", result.stdout)
        self.assertNotIn('WARNING', result.stdout)
        # No process of that name appears: the spawn fails and says the tab shows why.
        (self.state / 'claude.json').unlink()
        result = self.spawn('w4', str(brief), KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=ps, CLAUDE_CONFIG_DIR=str(config))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("no Claude Code session named 'w4' started within 30 s", result.stderr)
        # A worker seen once and then gone did not start: the spawn fails, not "started".
        (self.bin / 'ps-once').write_text('#!/bin/sh\n[ -f "$SPAWN_STATE/claude.json" ] || exit 0\n'
                                          'n=$(cat "$SPAWN_STATE/n" 2>/dev/null || echo 0); echo $((n + 1)) > "$SPAWN_STATE/n"\n'
                                          '[ "$n" -ne 0 ] || printf "10 claude.exe -n w5\\r\\n"\n')
        (self.bin / 'ps-once').chmod(0o755)
        (self.state / 'claude.json').unlink(missing_ok=True)
        result = self.spawn('w5', str(brief), KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=str(self.bin / 'ps-once'),
                            CLAUDE_CONFIG_DIR=str(config))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("the Claude Code session 'w5' ended right after it started", result.stderr)
        self.assertNotIn('started with', result.stdout)
        # The tab measures claude's own run, under its supervisor, and waits for Enter after a
        # quick end of any status.
        tab = json.loads((self.state / 'wt.json').read_text())[-1]
        self.assertRegex(tab, r"t=\$\(date \+%s\); KIT_WORKER_EXIT='[^']*\.exit' KIT_WORKER_STARTED='[0-9.]+' \S+ '[^']*/codex_worker\.py' ")
        self.assertIn("-c 'exec env -u CLAUDE_CODE_CHILD_SESSION ", tab)
        self.assertIn('press Enter to close', tab)

    def windows_path(self, path):
        # A path as the cygpath stub gives it (C: + the POSIX path), or the real one on Windows.
        return path if WINDOWS else path[2:]

    def worktree_hooks(self, tracked, hooks_tracked=True, bom=False, absolute=False):
        # Exercise both tracked hooks with untracked settings and native project loading.
        git = lambda *a: subprocess.run(['git', *a], cwd=self.cwd, check=True, capture_output=True)
        git('init', '-q')
        project = self.cwd / '.claude'
        project.mkdir()
        shutil.copytree(ROOT / 'overlays/claude-code/files/.claude/hooks', project / 'hooks')
        hooks = json.loads((ROOT / 'overlays/claude-code/files/.claude/settings.json').read_text())['hooks']
        source = {'hooks': hooks, 'permissions': {'allow': ['Bash(project-command)']},
                  'env': {'PROJECT_SETTING': 'kept'}}
        settings = project / 'settings.json'
        settings.write_text(json.dumps(source), encoding='utf-8-sig' if bom else 'utf-8')
        (self.cwd / 'seed').write_text('seed')
        git('add', 'seed')
        if hooks_tracked:
            git('add', '.claude/hooks')
        if tracked:
            git('add', '.claude/settings.json')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'project hooks')
        committed_hooks = {p.name: p.read_bytes() for p in (project / 'hooks').iterdir() if p.is_file()}
        if hooks_tracked:
            with (project / 'hooks/context_size.py').open('a', encoding='utf-8') as stream:
                stream.write('\n# An uncommitted lead edit must not replace the worker commit.\n')
        owner = {'permissions': {'allow': ['Bash(owner-command)']},
                 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'echo owner-hook'}]}]}}
        (self.cwd / 'own.json').write_text(json.dumps(owner))
        extra = {}
        if WINDOWS:
            for name, body in (('uname', '#!/bin/sh\necho MINGW64_NT\n'), ('wt-tab', WT_TAB),
                               ('ps-stub', '#!/bin/sh\n[ ! -f "$SPAWN_STATE/claude.json" ] || printf "8 claude.exe -n w1\\n"\n')):
                (self.bin / name).write_text(body, newline='\n')
                (self.bin / name).chmod(0o755)
            (self.tmp / 'config/sessions').mkdir(parents=True)
            (self.tmp / 'config/sessions/8.json').write_text('{}')
            extra = dict(KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=str(self.bin / 'ps-stub'),
                         CLAUDE_CONFIG_DIR=str(self.tmp / 'config'))
        own = str((self.cwd / 'own.json').resolve()).replace('\\', '/') if absolute else 'own.json'
        if absolute == 'backslash':
            own = own.replace('/', '\\')
        result = self.spawn('w1', str(self.brief), '--worktree', '--settings', own, **extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tree = self.cwd / '.claude/worktrees/w1'
        generated = json.loads((self.cwd / '.myagentkit/workers/w1.settings.json').read_text())
        if tracked:
            self.assertEqual(json.loads((tree / '.claude/settings.json').read_text()), source)
            self.assertNotIn('UserPromptSubmit', generated['hooks'], 'tracked project hooks would run twice')
            effective = hooks
        else:
            self.assertFalse((tree / '.claude/settings.json').exists())
            for event, entries in hooks.items():
                for entry in entries:
                    self.assertIn(entry, generated['hooks'][event])
            self.assertEqual(generated['permissions']['allow'], ['Bash(project-command)', 'Bash(owner-command)'])
            self.assertEqual(generated['env']['PROJECT_SETTING'], 'kept')
            effective = generated['hooks']
        self.assertIn(owner['hooks']['Stop'][0], generated['hooks']['Stop'])
        self.assertEqual(json.loads(settings.read_text(encoding='utf-8-sig')), source, 'spawn changed the lead settings')
        for hook_file in (project / 'hooks').iterdir():
            if hook_file.is_file():
                expected = committed_hooks[hook_file.name] if hooks_tracked else hook_file.read_bytes()
                actual = (tree / '.claude/hooks' / hook_file.name).read_bytes()
                if hooks_tracked:  # Git's checkout may convert LF to CRLF.
                    self.assertEqual(actual.replace(b'\r\n', b'\n'), expected.replace(b'\r\n', b'\n'))
                else:
                    self.assertEqual(actual, expected)
        transcript = self.tmp / 'request.jsonl'
        transcript.write_text(json.dumps({'type': 'assistant', 'message': {'usage': {'input_tokens': 250001}}}) + '\n')
        env = dict(self.base_env(), CLAUDE_PROJECT_DIR=str(tree).replace('\\', '/'))
        for event, expected in (('UserPromptSubmit', '250k'), ('SessionStart', '')):
            command = effective[event][0]['hooks'][0]['command']
            run = subprocess.run(['sh', '-c', command], cwd=tree, env=env,
                                 input=json.dumps({'transcript_path': str(transcript)}),
                                 capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(run.stdout, event)
            self.assertIn(expected, run.stdout)
        telemetry = generated['hooks']['Stop'][-1]['hooks'][0]['command']
        run = subprocess.run(['sh', '-c', telemetry], cwd=tree, env=env,
                             input=json.dumps({'hook_event_name': 'Stop', 'transcript_path': str(transcript)}),
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('context_tokens=250001', (self.cwd / '.myagentkit/workers/w1.state').read_text())

    def test_worktree_inherits_untracked_project_hooks(self):
        self.worktree_hooks(tracked=False, hooks_tracked=False)

    def test_copied_hooks_allow_done_without_hiding_other_changes(self):
        self.worktree_hooks(tracked=False, hooks_tracked=False)
        tree = self.cwd / '.claude/worktrees/w1'
        report = tree / 'RESULT-w1.md'
        report.write_text('Kind: completed\nTask: w1\nAttempt: 1\nRemaining: none\n')
        def git(*args):
            return subprocess.run(['git', *args], cwd=tree, check=True, capture_output=True, text=True).stdout
        git('add', 'RESULT-w1.md', 'seed')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'worker result')
        def watch():
            run = subprocess.run(['sh', str(SCRIPT.with_name('watch_workers.sh')), '--once',
                                  '--result', 'w1=' + report.as_posix(), 'w1'], cwd=self.cwd,
                                 env=self.base_env(), capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            return run.stdout
        # Unrelated untracked hooks and tracked edits still block DONE.
        extra = tree / '.claude/hooks/new-project-hook.py'
        extra.write_text('# project work\n')
        self.assertNotIn('DONE:', watch())
        extra.unlink()
        (tree / 'seed').write_text('changed\n')
        self.assertNotIn('DONE:', watch())
        (tree / 'seed').write_text('seed')
        self.assertIn('DONE: w1', watch(), git('status', '--porcelain'))
        self.assertEqual(git('status', '--porcelain'), '')

    def test_copied_hooks_never_hide_the_leads_own_files(self):
        # Fable final review 1: the copies were listed in info/exclude, which a linked worktree
        # shares with the main checkout, so the lead's own untracked hooks were ignored there
        # (git status, add -A and the gate's file list skipped them), one more entry per spawn.
        self.worktree_hooks(tracked=False, hooks_tracked=False)
        main = lambda *a: subprocess.run(['git', *a], cwd=self.cwd, capture_output=True, text=True)
        common = Path(main('rev-parse', '--path-format=absolute', '--git-common-dir').stdout.strip())
        exclude = common / 'info/exclude'
        self.assertNotIn('.claude/hooks', exclude.read_text() if exclude.exists() else '')
        self.assertNotEqual(main('check-ignore', '-q', '.claude/hooks/context_size.py').returncode, 0,
                            'the lead\'s own hook is ignored in the main checkout')
        self.assertIn('?? .claude/hooks/context_size.py',
                      main('status', '--porcelain', '--untracked-files=all').stdout)
        # The worker's own checkout still shows nothing it did not make.
        tree = self.cwd / '.claude/worktrees/w1'
        self.assertEqual(subprocess.run(['git', 'status', '--porcelain'], cwd=tree, capture_output=True,
                                        text=True).stdout, '')

    @unittest.skipUnless(WINDOWS, 'Windows drive-letter path syntax')
    def test_worktree_accepts_backslash_windows_settings(self):
        self.worktree_hooks(tracked=False, absolute='backslash')
    test_worktree_accepts_backslash_windows_settings._kit_platform_skip = not WINDOWS

    def test_worktree_keeps_tracked_project_hooks_without_copying_them(self):
        self.worktree_hooks(tracked=True)

    def test_worktree_inherits_untracked_hooks_and_bom_settings(self):
        self.worktree_hooks(tracked=False, hooks_tracked=False, bom=True)

    def test_worktree_accepts_absolute_windows_settings(self):
        self.worktree_hooks(tracked=False, absolute=True)

    def tmux_checkout(self):
        # Keep the launch command free of apostrophes on Git for Windows too.
        self.cwd = self.tmp / 'tmux-lead'
        self.cwd.mkdir()
        self.brief = self.cwd / 'brief.md'
        self.brief.write_text('brief')
        subprocess.run(['git', 'init', '-q'], cwd=self.cwd, check=True, capture_output=True)
        subprocess.run(['git', 'add', 'brief.md'], cwd=self.cwd, check=True, capture_output=True)
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'seed'],
                       cwd=self.cwd, check=True, capture_output=True)

    def test_bad_settings_leave_no_worktree_or_branch(self):
        self.tmux_checkout()
        project = self.cwd / '.claude'
        project.mkdir()
        with safe_tmux_scratch() as scratch:
            for i, (source, owner) in enumerate((('broken', '{}'), ('[]', '{}'), ('{}', '[]'), ('{}', 'broken'))):
                with self.subTest(project=source, owner=owner):
                    name = 'w1-' + str(i)
                    (project / 'settings.json').write_text(source)
                    (self.cwd / 'own.json').write_text(owner)
                    result = self.spawn(name, str(self.brief), '--worktree', '--settings', 'own.json', TMPDIR=scratch)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertFalse((project / 'worktrees' / name).exists(), result.stderr)
                    branch = subprocess.run(['git', 'show-ref', '--verify', '--quiet', 'refs/heads/worktree-' + name],
                                            cwd=self.cwd)
                    self.assertNotEqual(branch.returncode, 0)
                    self.assertIsNone(self.launched())

    def test_plain_tmux_spawn_clears_stale_state_before_readiness(self):
        self.tmux_checkout()
        workers = self.cwd / '.myagentkit/workers'
        workers.mkdir(parents=True)
        (workers / 'w1.state').write_text('idle 2026-10-16T12:00:00 1 context_tokens=314000\n')
        (workers / 'w1.watch-state-context').write_text('red\n')
        with safe_tmux_scratch() as scratch:
            result = self.spawn('w1', str(self.brief), '--batch', TMPDIR=scratch)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((workers / 'w1.state').exists())
        self.assertFalse((workers / 'w1.watch-state-context').exists())
        self.assertIn('Read ', (self.state / 'submitted').read_text())

    def test_on_native_windows_the_worker_gets_state_hooks_and_keeps_its_own(self):
        # Nothing reads a Windows Terminal tab: a Notification and a Stop hook keep the worker's
        # state line for watch_workers.sh. The owner's settings and hooks stay as they were.
        for name, body in (('uname', '#!/bin/sh\necho MINGW64_NT-10.0-26200\n'), ('cygpath', CYGPATH),
                           ('wt-tab', WT_TAB)):
            if WINDOWS and name == 'cygpath':
                continue
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        (self.bin / 'ps-stub').write_text('#!/bin/sh\n[ ! -f "$SPAWN_STATE/claude.json" ] || '
                                          'printf "8 claude.exe -n w1\\r\\n"\n')
        (self.bin / 'ps-stub').chmod(0o755)
        mine = {'hooks': [{'type': 'command', 'command': 'echo mine'}]}
        (self.cwd / 'own.json').write_text(json.dumps({'model': 'x', 'hooks': {'Stop': [mine]}}))
        workers = Path(os.path.realpath(self.cwd)) / '.myagentkit/workers'
        workers.mkdir(parents=True)
        (workers / 'w1.watch-state').write_text('idle from an earlier worker\n')
        (workers / 'w1.state.tmpleft').write_text('a hook that died\n')
        # Registered as a peer (sessions/8.json), so the spawn does not wait 30 s for it.
        (self.tmp / 'config/sessions').mkdir(parents=True)
        (self.tmp / 'config/sessions/8.json').write_text('{}')
        result = self.spawn('w1', str(self.brief), '--settings', 'own.json', KIT_WT=str(self.bin / 'wt-tab'),
                            KIT_PS=str(self.bin / 'ps-stub'), CLAUDE_CONFIG_DIR=str(self.tmp / 'config'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        argv = self.launched()['argv']
        settings = Path(self.windows_path(argv[argv.index('--settings') + 1]))
        self.assertEqual(settings, workers / 'w1.settings.json')
        merged = json.loads(settings.read_text())
        self.assertEqual(merged['model'], 'x')
        self.assertEqual(len(merged['hooks']['Stop']), 2)
        self.assertEqual(merged['hooks']['Stop'][0], mine)
        hook = merged['hooks']['Stop'][1]['hooks'][0]['command']
        self.assertEqual(merged['hooks']['Notification'], [{'hooks': [{'type': 'command', 'command': hook}]}])
        self.assertIn('w1.state', hook)
        self.assertFalse((workers / 'w1.watch-state').exists(), "an earlier worker's once-marker was kept")
        self.assertFalse((workers / 'w1.state.tmpleft').exists(), "an earlier hook's temporary file was kept")
        if not WINDOWS:
            return  # the hook names C:/... paths of the cygpath stub
        for payload, line in (({'hook_event_name': 'Notification', 'notification_type': 'permission_prompt'}, 'waiting permission '),
                              ({'hook_event_name': 'Notification', 'notification_type': 'elicitation_dialog'}, 'waiting question '),
                              ({'hook_event_name': 'Stop'}, 'idle ')):
            with self.subTest(payload=payload):
                (workers / 'w1.state').unlink(missing_ok=True)
                run = subprocess.run(['sh', '-c', hook], input=json.dumps(payload),
                                     env=self.base_env(), capture_output=True, text=True, timeout=30)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertTrue((workers / 'w1.state').read_text().startswith(line))

    def test_the_behaviour_appendix_reaches_the_worker_unless_turned_off(self):
        # Issue #74: BEHAVIOUR.md in the lead's folder (core/BEHAVIOUR.md in the kit itself) is
        # the worker's appended system prompt, by its file flag; MYAGENTKIT_NO_BEHAVIOUR=1 is the
        # A/B's other side. Driven through the Windows tab, the path every host can run.
        for name, body in (('uname', '#!/bin/sh\necho MINGW64_NT-10.0-26200\n'), ('cygpath', CYGPATH),
                           ('wt-tab', WT_TAB)):
            if not (WINDOWS and name == 'cygpath'):
                (self.bin / name).write_text(body)
                (self.bin / name).chmod(0o755)
        (self.bin / 'ps-stub').write_text('#!/bin/sh\n[ ! -f "$SPAWN_STATE/claude.json" ] || printf "8 claude.exe -n wb\\r\\n"\n')
        (self.bin / 'ps-stub').chmod(0o755)
        config = self.tmp / 'config'
        (config / 'sessions').mkdir(parents=True)
        (config / 'sessions' / '8.json').write_text('{}')
        (self.cwd / 'core').mkdir()
        behaviour = self.cwd / 'core' / 'BEHAVIOUR.md'
        behaviour.write_text('Lead with the answer.\n')
        shown = (subprocess.run(['cygpath', '-m', self.physical(behaviour)], capture_output=True, text=True,
                                check=True).stdout.rstrip('\n') if WINDOWS else 'C:' + self.physical(behaviour))
        for env, appended in (({'MYAGENTKIT_NO_BEHAVIOUR': None}, ['--append-system-prompt-file', shown]),
                              ({'MYAGENTKIT_NO_BEHAVIOUR': '1'}, [])):
            with self.subTest(env=env):
                (self.state / 'claude.json').unlink(missing_ok=True)
                result = self.spawn('wb', str(self.brief), KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=str(self.bin / 'ps-stub'),
                                    CLAUDE_CONFIG_DIR=str(config), **env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('behaviour appendix: ' + (shown if appended else 'off'), result.stdout)
                # On native Windows the worker also gets the merged --settings file (the state hooks).
                argv = self.launched()['argv'][1:]
                self.assertEqual(argv[6], '--settings')
                self.assertEqual(argv[:6] + argv[8:], ['-n', 'wb', '--model', 'm', '--effort', 'high', *appended,
                                                       '--disallowedTools', 'AskUserQuestion'])

    def test_the_displayed_behaviour_path_has_no_terminal_control_bytes(self):
        self.cwd = self.tmp / 'lead\x1b[2J\tdir'
        self.cwd.mkdir()
        (self.cwd / 'BEHAVIOUR.md').write_text('An appendix.\n')
        # The brief lives outside the control-bearing folder, so its input validation passes.
        result = self.spawn('wc', str(self.brief), '--batch', MYAGENTKIT_NO_BEHAVIOUR='')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        line = next(line for line in result.stdout.splitlines() if 'behaviour appendix:' in line)
        self.assertNotRegex(line, r'[\x00-\x1f\x7f]')
        self.assertIn('lead?[2J?dir/BEHAVIOUR.md', line)
        # Display sanitization must preserve the actual path handed to Claude.
        self.assertIn(self.physical(self.cwd / 'BEHAVIOUR.md'), self.launched()['argv'])

    def test_a_backend_reaches_the_worker_quoted_on_both_paths(self):
        # The file's variables reach claude's environment intact, CRLF line ends included, and
        # a value that would end its quoting runs nothing. The tmux path runs on POSIX only.
        marker = self.tmp / 'injected'
        token = "to'k$(touch %s)'en" % marker
        backend = self.backend_file('# GLM\r\nANTHROPIC_BASE_URL=https://backend.invalid\r\nANTHROPIC_AUTH_TOKEN=%s\r\n'
                                    'ANTHROPIC_DEFAULT_OPUS_MODEL=glm-x' % token)
        expected = {'ANTHROPIC_BASE_URL': 'https://backend.invalid', 'ANTHROPIC_AUTH_TOKEN': token,
                    'ANTHROPIC_DEFAULT_OPUS_MODEL': 'glm-x'}

        def check(result):
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            launched = self.launched()
            self.assertEqual({k: launched['env'].get(k) for k in expected}, expected)
            # On the Windows tab path the worker also gets the merged --settings file (state hooks).
            argv = launched['argv']
            if '--settings' in argv:
                at = argv.index('--settings')
                argv = argv[:at] + argv[at + 2:]
            self.assertEqual(argv[-8:], ['-n', 'w1', '--model', 'm', '--effort', 'high',
                                         '--disallowedTools', 'AskUserQuestion'])
            self.assertFalse(marker.exists(), 'a backend value ran as shell')
            self.assertNotIn(token, result.stdout + result.stderr)
            (self.state / 'claude.json').unlink()
        if not WINDOWS:
            check(self.spawn('w1', str(self.brief), '--backend', 'glm'))
        for name, body in (('uname', '#!/bin/sh\necho MINGW64_NT-10.0-26200\n'), ('cygpath', CYGPATH),
                           ('wt-tab', WT_TAB), ('ps-stub', '#!/bin/sh\n[ ! -f "$SPAWN_STATE/claude.json" ] || '
                                                          'printf "8 claude.exe -n w1\\r\\n"\n')):
            if WINDOWS and name == 'cygpath':
                continue
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        config = self.tmp / 'config'
        (config / 'sessions').mkdir(parents=True)
        (config / 'sessions' / '8.json').write_text('{}')
        tab = dict(KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=str(self.bin / 'ps-stub'), CLAUDE_CONFIG_DIR=str(config))
        check(self.spawn('w1', str(self.brief), '--backend', 'glm', **tab))
        # A file without the endpoint is refused before any session, and prints no value.
        backend.write_text('ANTHROPIC_AUTH_TOKEN=%s\n' % token)
        result = self.spawn('w1', str(self.brief), '--backend', 'glm', **tab)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('sets no ANTHROPIC_BASE_URL', result.stderr)
        self.assertNotIn(token, result.stderr)
        self.assertIsNone(self.launched())


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
        self.assertEqual(submitted[0], INSTRUCTION % shq(self.physical(self.cwd / 'briefs/task.md')))

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
        result = subprocess.run(['sh', str(SCRIPT), 'w9', 'task.md'], cwd=cwd, env=self.base_env(),
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
        result = subprocess.run(['bash', '-O', 'xpg_echo', str(SCRIPT), 'w\\033[2J', str(brief),
                                 '--model', 'm', '--effort', 'high'], cwd=self.cwd,
                                env=self.base_env(), capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.physical(brief), result.stdout)
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
        for name, value, expect in (('w6', 'local.json', self.physical(self.cwd / 'local.json')),
                                    ('w7', inline, inline)):
            with self.subTest(settings=value):
                result = self.spawn(name, str(self.brief), '--worktree', '--settings', value)
                self.assertEqual(result.returncode, 0, result.stderr)
                argv = self.launched()['argv']
                merged = json.loads(Path(argv[argv.index('--settings') + 1]).read_text())
                owner = json.loads(value) if value == inline else json.loads((self.cwd / value).read_text())
                for key, setting in owner.items():
                    self.assertEqual(merged[key], setting)
                self.assertIn('Stop', merged['hooks'])
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
                    actual = argv[argv.index('--settings') + 1]
                    if worktree:
                        self.assertEqual(json.loads(Path(actual).read_text())['model'], 'x')
                    else:
                        self.assertEqual(actual, value)
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
        # A second spawn under the same name, once the session is closed, would reuse a stale
        # branch: refused by name.
        (self.state / 'tmux.log').unlink()
        (self.state / 'started').unlink()
        again = self.spawn('w3', str(self.brief), '--worktree')
        self.assertNotEqual(again.returncode, 0)
        self.assertIn('worktree-w3', again.stderr)
        self.assertNotIn('new-session', self.tmux_log())

    def test_a_worker_worktree_is_locked_from_spawn(self):
        # The audit never removes a locked worktree (clean_worktrees.py, check a); close_worker.sh
        # unlocks it. Run on the native Windows path, with a long name for Windows' path limits.
        for name, body in (('uname', '#!/bin/sh\necho MINGW64_NT-10.0-26200\n'), ('cygpath', CYGPATH),
                           ('wt-tab', WT_TAB),
                           ('ps-stub', '#!/bin/sh\n[ ! -f "$SPAWN_STATE/claude.json" ] || '
                                       'printf "8 claude.exe -n %s\\r\\n" "$(cat "$SPAWN_STATE/name")"\n')):
            if WINDOWS and name == 'cygpath':
                continue
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        git = lambda *a: subprocess.run(['git', *a], cwd=self.cwd, check=True, capture_output=True,
                                        text=True).stdout.strip()
        git('init', '-q')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'a')
        # Keep room for Git's worktree metadata when the test runner's temp root is long.
        capacity = max(2, 200 - len(str(self.cwd.resolve() / '.claude/worktrees')) - 1)
        for name in ('lk', 'l' * min(100, capacity)):
            with self.subTest(length=len(name)):
                (self.state / 'name').write_text(name)
                (self.state / 'claude.json').unlink(missing_ok=True)
                result = self.spawn(name, str(self.brief), '--worktree', KIT_WT=str(self.bin / 'wt-tab'),
                                    KIT_PS=str(self.bin / 'ps-stub'))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                gitdir = git('-C', str(self.cwd / '.claude/worktrees' / name), 'rev-parse', '--absolute-git-dir')
                self.assertEqual(Path(gitdir, 'locked').read_text().rstrip('\n'), 'kit worker ' + name)

    def native_checkout(self, sessions=True):
        # The native Windows path on any host, in a fresh repository; SESSIONS: the lister
        # reports the worker's claude once it ran, else never.
        ps = ('#!/bin/sh\n[ ! -f "$SPAWN_STATE/claude.json" ] || printf "8 claude.exe -n fw\\r\\n"\n'
              if sessions else '#!/bin/sh\nexit 0\n')
        for name, body in (('uname', '#!/bin/sh\necho MINGW64_NT-10.0-26200\n'), ('cygpath', CYGPATH),
                           ('wt-tab', WT_TAB), ('ps-stub', ps)):
            if WINDOWS and name == 'cygpath':
                continue
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        git = lambda *a: subprocess.run(['git', *a], cwd=self.cwd, capture_output=True, text=True)
        git('init', '-q')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'a')
        return git

    def test_a_spawn_that_fails_before_its_launch_leaves_no_worktree_or_branch(self):
        # Ultrareview part 5 #8: a spawn that died after `git worktree add` left the worktree
        # locked and its branch behind. The audit never removes a locked worktree, nor one no
        # worker committed in, and the name could not be spawned again.
        git = self.native_checkout()
        tree = self.cwd / '.claude/worktrees/fw'
        failed = self.spawn('fw', str(self.brief), '--worktree', KIT_WT=str(self.bin / 'no-such-terminal'),
                            KIT_PS=str(self.bin / 'ps-stub'))
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        self.assertIn('is not on PATH', failed.stderr)
        self.assertIn('removed the unused worktree', failed.stderr)
        self.assertFalse(tree.exists(), failed.stderr)
        self.assertNotEqual(git('show-ref', '--verify', '--quiet', 'refs/heads/worktree-fw').returncode, 0)
        self.assertNotIn('worktrees/fw', git('worktree', 'list', '--porcelain').stdout)
        again = self.spawn('fw', str(self.brief), '--worktree', KIT_WT=str(self.bin / 'wt-tab'),
                           KIT_PS=str(self.bin / 'ps-stub'))
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertTrue(tree.is_dir())

    def test_a_spawn_that_fails_after_its_launch_keeps_the_worktree_and_says_how_to_remove_it(self):
        # Its session may still run there (a tab waiting on Enter, a slow start): never removed
        # under it, but the lead is told how, since the audit keeps a worktree nobody worked in.
        git = self.native_checkout(sessions=False)
        tree = self.cwd / '.claude/worktrees/fw'
        failed = self.spawn('fw', str(self.brief), '--worktree', KIT_WT=str(self.bin / 'wt-tab'),
                            KIT_PS=str(self.bin / 'ps-stub'))
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        self.assertIn('started within 30 s', failed.stderr)
        self.assertTrue(tree.is_dir())
        self.assertEqual(git('show-ref', '--verify', '--quiet', 'refs/heads/worktree-fw').returncode, 0)
        self.assertIn('scripts/close_worker.sh fw', failed.stderr)
        self.assertIn('git worktree remove --force', failed.stderr)
        self.assertIn('git branch -D worktree-fw', failed.stderr)

    def test_a_worker_is_resumed_through_the_kit_under_its_name(self):
        # 2026-10-16: the lead resumed a worker by hand (`wt -w 0 nt ... claude --resume ID`); that tab
        # had no name, nothing could close it, and the lead ended it with Stop-Process. Resumed
        # through the kit, the session keeps `-n NAME`, so close_worker.sh finds and ends it.
        for name, body in (('uname', '#!/bin/sh\necho MINGW64_NT-10.0-26200\n'), ('cygpath', CYGPATH),
                           ('wt-tab', WT_TAB),
                           ('ps-stub', '#!/bin/sh\n[ ! -f "$SPAWN_STATE/claude.json" ] || printf "8 claude.exe -n rw\\r\\n"\n')):
            if WINDOWS and name == 'cygpath':
                continue
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        git = lambda *a: subprocess.run(['git', *a], cwd=self.cwd, check=True, capture_output=True,
                                        text=True).stdout.strip()
        git('init', '-q')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'a')
        config = self.tmp / 'config'
        (config / 'sessions').mkdir(parents=True)
        (config / 'sessions' / '8.json').write_text('{"sessionId": "sid-1", "name": "rw"}')
        env = dict(KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=str(self.bin / 'ps-stub'), CLAUDE_CONFIG_DIR=str(config))
        result = self.spawn('rw', str(self.brief), '--worktree', **env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # The spawn names the id a resume needs.
        self.assertRegex(result.stdout, r'scripts/spawn_worker.sh rw ANSWER_FILE --model .* --worktree --resume sid-1\n')
        tree = self.cwd / '.claude/worktrees/rw'
        git('worktree', 'unlock', str(tree))
        (self.state / 'claude.json').unlink()
        answer = self.cwd / 'answer.md'
        answer.write_text('Go on with A.\n')
        # A resume without the id, or of a worktree that is not there, is refused before any tab.
        for args, words in ((('--worktree', '--resume'), '--resume needs the session id'),
                            (('--resume', '--worktree'), '--resume needs the session id'),
                            (('--worktree', '--resume', 'sid-1'), None)):
            with self.subTest(args=args):
                name = 'gone' if words is None else 'rw'
                (self.state / 'wt.json').unlink(missing_ok=True)
                result = self.spawn(name, str(answer), *args, **env)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(words or '--resume --worktree: no worktree at', result.stderr)
                self.assertFalse((self.state / 'wt.json').exists())
        result = self.spawn('rw', str(answer), '--worktree', '--resume', 'sid-1', **env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        argv = self.launched()['argv']
        self.assertEqual(argv[1:5], ['-n', 'rw', '--resume', 'sid-1'])
        self.assertIn('answer.md', argv[0])
        self.assertEqual(Path(self.launched()['cwd']).resolve(), tree.resolve())
        # Locked again for its new run: the audit never removes it under the session.
        gitdir = git('-C', str(tree), 'rev-parse', '--absolute-git-dir')
        self.assertEqual(Path(gitdir, 'locked').read_text().rstrip('\n'), 'kit worker rw')

    def test_the_tmux_worker_does_not_inherit_the_leads_session_markers(self):
        result = self.spawn('w1', str(self.brief))
        self.assertEqual(result.returncode, 0, result.stderr)
        script = (self.state / 'tmux-script').read_text()
        self.assertIn('exec env -u CLAUDE_CODE_CHILD_SESSION ', script)
        self.assertIn(' claude ', script)
        env = self.launched()['env_names']
        self.assertFalse(MARKERS & set(env), env)
        self.assertIn('CLAUDE_CODE_EXECPATH', env)
        self.assertIn('CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL', env)
        self.assertIn('MYAGENTKIT_ROLE', env)

    def test_a_started_worker_is_shown_unless_batch(self):
        # A session nobody sees can wait on a dialog for hours: it opens in a terminal tab
        # by default, after its brief landed; --batch leaves that to one show of the batch.
        result = self.spawn('w1', str(self.brief))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.state / 'submitted').exists())
        self.assertIn("'new-tab'", (self.state / 'wt.log').read_text())
        self.assertIn("'=w1'", (self.state / 'wt.log').read_text())
        self.assertIn('show_workers: shown: w1', result.stdout)
        # The two hints name the scripts that watch and close this worker, by its name.
        self.assertIn('close it: scripts/close_worker.sh w1\n', result.stdout)
        self.assertIn('scripts/watch_workers.sh --result w1=PATH w1 ', result.stdout)
        (self.state / 'wt.log').unlink()
        result = self.spawn('w2', str(self.brief), '--batch')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.state / 'wt.log').exists(), 'a --batch worker was shown on its own')
        self.assertIn('show_workers.sh NAME1 NAME2', result.stdout)

    def test_a_failing_show_does_not_fail_the_spawn(self):
        # The worker is running: a terminal that cannot open (WSL interop down) costs a line.
        result = self.spawn('w1', str(self.brief), SPAWN_WT='fail')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.state / 'submitted').exists())
        self.assertIn('attach by hand: tmux attach -t w1', result.stdout)

    def test_a_dialog_or_an_exit_at_start_up_stops_the_spawn_by_the_shared_rules(self):
        # The trust dialog is recognised by the watcher's rules, from a real capture; its
        # option line starts with the same arrow as the input line, so it is checked first.
        result = self.spawn('w1', str(self.brief), SPAWN_PANE=str(PANES / 'trust.txt'))
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn('trust dialog', result.stderr)
        self.assertNotIn("'-l'", self.tmux_log())
        # A session that exited during start-up is reported at once, not after 60 seconds.
        result = self.spawn('w2', str(self.brief), SPAWN_GONE='1')
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn('exited before its input line showed', result.stderr)

    def test_a_missing_or_failing_watcher_stops_the_spawn(self):
        # The start-up check's exit status was discarded, and a missing watcher's shell error
        # did not match `watch_workers:`: the brief was typed with no dialog check at all.
        scripts = self.tmp / 'scripts'
        scripts.mkdir()
        (scripts / 'spawn_worker.sh').write_bytes(SCRIPT.read_bytes())
        shutil.copyfile(SCRIPT.with_name('codex_worker.py'), scripts / 'codex_worker.py')  # the session's supervisor
        for body in (None, 'echo "it broke"; exit 1\n'):
            with self.subTest(watcher=body):
                if body:
                    (scripts / 'watch_workers.sh').write_text(body)
                env = dict(self.base_env(), PWD=str(self.cwd))
                result = subprocess.run(['sh', str(scripts / 'spawn_worker.sh'), 'w%d' % bool(body), str(self.brief),
                                         '--model', 'm', '--effort', 'high'],
                                        cwd=self.cwd, env=env, capture_output=True, text=True, timeout=60)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("cannot check session 'w%d': the watcher exited " % bool(body), result.stderr)
                self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
                self.assertNotIn("'-l'", self.tmux_log())


def run_state_hook(state, payload):
    # Execute the exact inline Python carried in --settings, without a live worker.
    code = SCRIPT.read_text(encoding='utf-8').split("hook=$kit_python' -I -c '$(q '", 1)[1].split("')' ", 1)[0]
    with patch.object(sys, 'argv', ['hook', str(state), str(SCRIPT.parent.parent / '.claude/hooks/context_size.py')]), \
            patch.object(sys, 'stdin', io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode()))):
        exec(compile(code, str(SCRIPT), 'exec'), {})


class WorkerStateHookTests(unittest.TestCase):
    def test_tmux_context_notices_once_per_band_and_respects_override(self):
        with tempfile.TemporaryDirectory(prefix='tmux-context-') as tmp:
            repo = Path(tmp)
            subprocess.run(['git', 'init', '-q'], cwd=repo, check=True, capture_output=True)
            workers, bin_dir = repo / '.myagentkit/workers', repo / 'bin'
            workers.mkdir(parents=True)
            bin_dir.mkdir()
            pane_file = repo / 'pane.txt'
            pane_file.write_text((PANES / 'working-auto.txt').read_text(encoding='utf-8'), encoding='utf-8')
            pane = str(pane_file).replace('\\', '/')
            tmux = ('#!/bin/sh\ncase $1 in\nhas-session) exit 0 ;;\n'
                    'show-options) cat "$WATCH_MARK" 2>/dev/null ;;\n'
                    'set-option) for v do :; done; printf "%s\\n" "$v" > "$WATCH_MARK" ;;\n'
                    'capture-pane) cat ' + shq(pane) + ' ;;\n*) exit 1 ;;\nesac\n')
            for name, body in (('uname', '#!/bin/sh\necho Linux\n'), ('tmux', tmux),
                               ('python3', '#!/bin/sh\nexec ' + shq(sys.executable.replace('\\', '/')) + ' "$@"\n')):
                (bin_dir / name).write_text(body, newline='\n')
                (bin_dir / name).chmod(0o755)
            env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'],
                       WATCH_MARK=str(repo / 'mark').replace('\\', '/'))
            def watch(count, *options):
                (workers / 'w1.state').write_text(f'idle 2026-10-16T12:00:00 {count} context_tokens={count}\n')
                result = subprocess.run(['sh', str(SCRIPT.with_name('watch_workers.sh')), '--once', *options, 'w1'],
                                        cwd=repo, env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout
            for count, notice in ((200000, True), (250000, False), (300000, True),
                                  (315000, False), (250001, False), (400000, True), (401000, False)):
                with self.subTest(count=count):
                    self.assertEqual('CONTEXT:' in watch(count), notice)
            (repo / 'mark').unlink(missing_ok=True)
            self.assertEqual(watch(250000, '--context-warn', '300k'), '')
            self.assertIn('red', watch(310000, '--context-warn', '300k'))
            (repo / 'mark').unlink(missing_ok=True)
            self.assertEqual(watch(90000, '--context-warn', '10%'), '')
            self.assertIn('CONTEXT:', watch(110000, '--context-warn', '10%'))
            (repo / 'mark').unlink(missing_ok=True)
            original = (PANES / 'working-auto.txt').read_text(encoding='utf-8')
            pane_file.write_text(original.replace('58k/1.0M', '350k/1.0M'), encoding='utf-8')
            self.assertIn('CONTEXT:', watch(150000))
            self.assertEqual(watch(350001), '', 'snapshot repeats the pane band')
            self.assertEqual(watch(150000), '', 'pane repeats its own band')
            (repo / 'mark').unlink(missing_ok=True)
            (workers / 'w1.state').unlink()
            run = subprocess.run(['sh', str(SCRIPT.with_name('watch_workers.sh')), '--once', 'w1'],
                                 cwd=repo, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('CONTEXT:', run.stdout)
            self.assertEqual(watch(350002), '', 'snapshot shares the pane band without a prior state')
            (repo / 'mark').unlink(missing_ok=True)
            pane_file.write_text('No status window figure\n', encoding='utf-8')
            self.assertEqual(watch(310000, '--context-warn', '10%'), '')
            self.assertIn('CONTEXT:', watch(310000, '--context-warn', '300k'))

    def test_the_watcher_keeps_the_default_line_when_the_hook_cannot_answer(self):
        # Ultrareview part 7 #1: a project's v0.10 context_size.py (sync never updates it) cannot
        # answer --line, and with no Python nothing can: the watcher died, and with it every tmux
        # spawn before its brief was typed. It keeps the built-in 200k line instead.
        old_hook = 'import json, sys\ntry:\n    json.load(sys.stdin)\nexcept Exception:\n    pass\n'
        no_python = '#!/bin/sh\nprintf "%s\\n" "no Python found" >&2\nexit 1\n'
        for case, hook, launcher in (('old hook', old_hook, None), ('no Python', None, no_python)):
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix='old-hook-') as tmp:
                repo = Path(tmp)
                subprocess.run(['git', 'init', '-q'], cwd=repo, check=True, capture_output=True)
                scripts, hooks, bin_dir = repo / 'kit/scripts', repo / 'kit/.claude/hooks', repo / 'bin'
                for folder in (scripts, hooks, bin_dir):
                    folder.mkdir(parents=True)
                for name in ('watch_workers.sh', 'waiting_patterns.txt'):
                    shutil.copyfile(SCRIPT.with_name(name), scripts / name)
                (hooks / 'py.sh').write_text(launcher or (SCRIPT.parent.parent / '.claude/hooks/py.sh').read_text(),
                                             newline='\n')
                if hook:
                    (hooks / 'context_size.py').write_text(hook)
                pane_file = repo / 'pane.txt'
                pane_file.write_text((PANES / 'working-auto.txt').read_text(encoding='utf-8')
                                     .replace('58k/1.0M', '250k/1.0M'), encoding='utf-8')
                tmux = ('#!/bin/sh\ncase $1 in has-session|show-options|set-option) exit 0 ;; '
                        'capture-pane) cat ' + shq(str(pane_file).replace('\\', '/')) + ' ;; *) exit 1 ;; esac\n')
                for name, body in (('uname', '#!/bin/sh\necho Linux\n'), ('tmux', tmux),
                                   ('python3', '#!/bin/sh\nexec ' + shq(sys.executable.replace('\\', '/')) + ' "$@"\n')):
                    (bin_dir / name).write_text(body, newline='\n')
                    (bin_dir / name).chmod(0o755)
                env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'])
                result = subprocess.run(['sh', str(scripts / 'watch_workers.sh'), '--once', 'w1'], cwd=repo, env=env,
                                        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('CONTEXT: w1, 250k/1.0M', result.stdout)
                self.assertIn('past its 200k warning line', result.stdout)

    def test_tmux_watcher_reports_the_hook_context_when_the_pane_is_below_the_band(self):
        with tempfile.TemporaryDirectory(prefix='tmux context ') as tmp:
            repo = Path(tmp)
            subprocess.run(['git', 'init', '-q'], cwd=repo, check=True, capture_output=True)
            workers, bin_dir = repo / '.myagentkit/workers', repo / 'bin'
            workers.mkdir(parents=True)
            bin_dir.mkdir()
            (workers / 'w1.state').write_text('idle 2026-10-16T12:00:00 1 context_tokens=314000\n')
            pane = str(PANES / 'working-auto.txt').replace('\\', '/')
            for name, body in (('uname', '#!/bin/sh\necho Linux\n'),
                               ('python3', '#!/bin/sh\nexec ' + shq(sys.executable.replace('\\', '/')) + ' "$@"\n'),
                               ('tmux', '#!/bin/sh\ncase $1 in has-session|show-options|set-option) exit 0 ;; '
                                'capture-pane) cat ' + shq(pane) + ' ;; *) exit 1 ;; esac\n')):
                (bin_dir / name).write_text(body, newline='\n')
                (bin_dir / name).chmod(0o755)
            env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'])
            result = subprocess.run(['sh', str(SCRIPT.with_name('watch_workers.sh')), '--once', 'w1'],
                                    cwd=repo, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('CONTEXT: w1', result.stdout)
            self.assertIn('314000 tokens, red', result.stdout)

    def test_state_context_uses_the_last_request_and_resets_at_compaction(self):
        with tempfile.TemporaryDirectory(prefix='worker context ') as tmp:
            state, transcript = Path(tmp) / 'w1.state', Path(tmp) / 'session.jsonl'
            records = [dict(type='assistant', message={'usage': {'input_tokens': 999999}}),
                       dict(type='assistant', message={'usage': dict(input_tokens=11,
                            cache_read_input_tokens=210000, cache_creation_input_tokens=7000)}),
                       dict(type='assistant', isSidechain=True, message={'usage': {'input_tokens': 999999}}),
                       dict(type='assistant', message={'model': '<synthetic>', 'usage': {'input_tokens': 999999}})]
            for event in ('Stop', 'Notification'):
                for boundary, expected in ((False, 217011), (True, 0), ('zero', 0)):
                    with self.subTest(event=event, boundary=boundary):
                        data = records + ([dict(type='system', subtype='compact_boundary')] if boundary else [])
                        if boundary == 'zero':
                            data = [dict(type='assistant', message={'usage': {'input_tokens': 0}})]
                        transcript.write_text(''.join(json.dumps(row) + '\n' for row in data))
                        run_state_hook(state, dict(hook_event_name=event, notification_type='permission_prompt',
                                                  transcript_path=str(transcript)))
                        self.assertTrue(state.read_text().strip().endswith(' context_tokens=' + str(expected)), state.read_text())

    def test_missing_or_broken_transcript_never_loses_the_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, transcript = Path(tmp) / 'w1.state', Path(tmp) / 'session.jsonl'
            for data in (None, 'not json\n', *(json.dumps({'type': 'assistant', 'message': {'usage': {'input_tokens': value}}})
                                              for value in ('bad', -1, 1.5))):
                with self.subTest(data=data):
                    if data is not None:
                        transcript.write_text(data)
                    run_state_hook(state, dict(hook_event_name='Stop', transcript_path=str(transcript)))
                    self.assertTrue(state.read_text().startswith('idle '))
                    self.assertNotIn('context_tokens=', state.read_text())

    def test_watcher_reports_context_bands_beside_the_state(self):
        with tempfile.TemporaryDirectory(prefix='watch context ') as tmp:
            repo = Path(tmp)
            workers, bin_dir = repo / '.myagentkit/workers', repo / 'bin'
            workers.mkdir(parents=True)
            bin_dir.mkdir()
            subprocess.run(['git', 'init', '-q'], cwd=repo, check=True, capture_output=True)
            for name, body in (('uname', '#!/bin/sh\necho MINGW64_NT\n'),
                               ('python3', '#!/bin/sh\nexec ' + shq(sys.executable.replace('\\', '/')) + ' "$@"\n')):
                (bin_dir / name).write_text(body, newline='\n')
                (bin_dir / name).chmod(0o755)
            env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'])
            for count, band in ((199999, ''), (200000, 'yellow'), (299999, 'yellow'),
                                (300000, 'red'), (399999, 'red'), (400000, 'ceiling')):
                for state in ('idle', 'waiting permission'):
                    with self.subTest(count=count, state=state):
                        (workers / 'w1.state').write_text(f'{state} 2026-10-16T12:00:00 {count} context_tokens={count}\n')
                        result = subprocess.run(['sh', str(SCRIPT.with_name('watch_workers.sh')), '--once', 'w1'],
                                                cwd=repo, env=env, capture_output=True, text=True, timeout=30)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn('context_tokens=' + str(count), result.stdout)
                        self.assertIn(band, result.stdout)
                        if not band:
                            for word in ('yellow', 'red', 'ceiling'):
                                self.assertNotIn(word, result.stdout)

    def test_notification_types_are_classified_from_a_fresh_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'w1.state'
            cases = [({'notification_type': kind, 'message': 'question permission approval'}, expected)
                     for kind, expected in (('permission_prompt', 'waiting permission'),
                                            ('elicitation_dialog', 'waiting question'),
                                            ('idle_prompt', None),
                                            ('auth_success', None), ('other', None), ('', None))]
            cases += [({'message': message}, expected) for message, expected in
                      (('a question', 'waiting question'), ('permission needed', 'waiting permission'),
                       ('Claude is waiting for your input', None),
                       ('approval needed', 'waiting permission'), ('unrelated', None))]
            for payload, expected in cases:
                with self.subTest(payload=payload):
                    state.unlink(missing_ok=True)
                    run_state_hook(state, dict(payload, hook_event_name='Notification'))
                    if expected is None:
                        self.assertFalse(state.exists())
                    else:
                        self.assertTrue(state.read_text().startswith(expected + ' '))

    def test_crash_after_temp_write_preserves_previous_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'w1.state'
            previous = b'waiting permission 2026-10-12T10:00:00 1\n'
            state.write_bytes(previous)
            def crash(source, target):
                self.assertEqual(Path(source).parent, state.parent)
                self.assertEqual(Path(target), state)
                self.assertTrue(Path(source).read_text().startswith('idle '))
                raise RuntimeError('crash before publication')
            with patch('os.replace', side_effect=crash), self.assertRaisesRegex(RuntimeError, 'crash'):
                run_state_hook(state, {'hook_event_name': 'Stop'})
            self.assertEqual(state.read_bytes(), previous)
            self.assertEqual([p.name for p in state.parent.iterdir()], ['w1.state'], 'the temporary file was left behind')

    def test_temporary_file_is_named_after_the_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'w1.state'
            def look(source, target):
                self.assertTrue(Path(source).name.startswith('w1.state.'))
                raise RuntimeError('stop')
            with patch('os.replace', side_effect=look), self.assertRaises(RuntimeError):
                run_state_hook(state, {'hook_event_name': 'Stop'})


class TmuxStubTests(unittest.TestCase):
    def test_unsafe_system_temp_uses_the_original_checkout_fallback(self):
        with safe_tmux_scratch() as checkout:
            unsafe = Path(checkout) / 'temp space'
            unsafe.mkdir()
            with patch('tempfile.tempdir', str(unsafe)), \
                    patch(__name__ + '.ROOT', Path(checkout) / 'checkout space'), \
                    safe_tmux_scratch(checkout=Path(checkout)) as folder:
                self.assertEqual(Path(folder).parent, Path(checkout))
            self.assertEqual(list(unsafe.iterdir()), [])

    def test_tmux_stub_reparses_the_final_command_in_the_start_directory(self):
        # A checkout with spaces must not force a skip when system scratch is safe.
        with safe_tmux_scratch() as scratch, patch('tempfile.tempdir', scratch), \
                patch(__name__ + '.ROOT', ROOT / 'checkout space'), safe_tmux_scratch() as folder:
            state = Path(folder)
            for segment in ('literal$REVIEW_SEGMENT', 'literal$($REVIEW_PAYLOAD)',
                            'literal`$REVIEW_BACKQUOTE`'):
                with self.subTest(segment=segment):
                    script = state / segment / 'run.sh'
                    script.parent.mkdir()
                    script.write_text('exit 0\n', newline='\n')
                    command = 'sh ' + SpawnWorkerTests.physical(script)
                    result = subprocess.run([sys.executable, '-c', TMUX, 'new-session', '-d',
                                             '-s', 'stub', '-c', str(state), '-x', '200', '-y', '50', command],
                                            env=dict(os.environ, SPAWN_STATE=str(state), REVIEW_SEGMENT='expanded',
                                                     REVIEW_PAYLOAD='touch INJECTED', REVIEW_BACKQUOTE='touch BACKQUOTED'),
                                            capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('literal', result.stderr)
                    self.assertNotIn(segment, result.stderr, 'the stub bypassed shell expansion')
            self.assertTrue((state / 'INJECTED').exists(), 'the stub did not run command substitution')
            self.assertTrue((state / 'BACKQUOTED').exists(), 'the stub did not run backquotes')


if __name__ == '__main__':
    unittest.main()
