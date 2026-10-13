"""spawn_worker.sh must hand every value to the worker intact, deliver the brief by path, and
build its worktree from the lead's current commit.

No live `claude` and no tmux server: both are stubs on PATH. The tmux stub runs the session
command with `sh -c`, the way tmux does, so a value that escapes its quoting runs here too.
No real terminal either: the launcher (KIT_WT), `osascript` and `uname` are stubs, and the
environment says WSL, so showing a session goes to the launcher stub, which marks it attached.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

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
    with open(started, 'a') as f:
        f.write(args[args.index('-s') + 1] + '\n')
    sys.exit(subprocess.run(['sh', '-c', args[-1]]).returncode)
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
    json.dump({'argv': sys.argv[1:], 'cwd': os.getcwd(),
               'env': {k: v for k, v in os.environ.items() if k.startswith('ANTHROPIC_') or
               k in os.environ.get('SPAWN_CONTROL_NAMES', '').split(',')}}, f)
'''


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


WINDOWS = os.name == 'nt'
# The cases that run on native Windows (issue #56). Every other case drives the tmux path,
# which native Windows never takes, through Python stubs whose `sh -c` command line Git for
# Windows parses again (an apostrophe is a quote there): there each prints NOT RUN.
ON_WINDOWS = {'test_backend_worker_clears_each_claude_credential_and_routing_control', 'test_backend_requires_nonempty_token_before_worker_launch',
              'test_backend_worker_refuses_claude_model_id',
              'test_backend_worker_refuses_case_variant_of_tracked_path', 'test_a_missing_or_failing_watcher_stops_the_spawn', 'test_a_worker_without_its_model_or_effort_is_refused',
              'test_missing_or_unreadable_brief_is_refused_before_any_session',
              'test_no_error_message_echoes_a_control_character',
              'test_on_native_windows_the_worker_opens_as_a_windows_terminal_tab',
              'test_a_backend_reaches_the_worker_quoted_on_both_paths',
              'test_backend_secrets_must_be_ignored_and_untracked',
              'test_backend_replaces_every_inherited_anthropic_variable',
              'test_backend_token_is_absent_from_recorded_launch_commands',
              'test_backend_duplicate_keys_cannot_empty_final_values',
              'test_backend_whitespace_lines_use_the_review_grammar',
              'test_backend_nul_and_nonregular_files_refuse_before_launch'}


def tmux_path_cases(cls):
    for name in [n for n in vars(cls) if n.startswith('test_') and n not in ON_WINDOWS and WINDOWS]:
        def not_run(self):
            sys.stderr.write('\nNOT RUN: %s (the tmux path, POSIX only)\n' % self.id())
        not_run.__name__ = name
        setattr(cls, name, not_run)
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
            (self.bin / name).write_text(body)
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
            folder = subprocess.run(['cygpath', '-u', os.path.realpath(path.parent)], capture_output=True,
                                    text=True, check=True).stdout.rstrip('\n')
            return folder + '/' + path.name
        return os.path.join(os.path.realpath(path.parent), path.name)

    def spawn(self, *args, choose=True, **extra):
        # PWD as a lead's shell exports it: with it, a plain `pwd` printed the symlinked spelling.
        env = dict(self.base_env(), PWD=str(self.cwd), **extra)
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
               and not k.startswith('ANTHROPIC_')}
        return dict(env, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}', SPAWN_STATE=str(self.state),
                    WSL_DISTRO_NAME='Test-1', KIT_WT=str(self.bin / 'wt-stub'))

    def launched(self):
        path = self.state / 'claude.json'
        return json.loads(path.read_text()) if path.exists() else None

    def tmux_log(self):
        path = self.state / 'tmux.log'
        return path.read_text() if path.exists() else ''

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

    def test_a_worker_without_its_model_or_effort_is_refused(self):
        # docs/WORKFLOW.md, "Model routing": neither is left to the user's default.
        for args, missing in ((('--effort', 'high'), '--model'), (('--model', 'm'), '--effort'), ((), '--model')):
            with self.subTest(args=args):
                result = self.spawn('w1', str(self.brief), *args, choose=False)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('spawn_worker: %s is required' % missing, result.stderr)
                self.assertIsNone(self.launched(), 'a worker started without its model or effort')
                self.assertEqual(self.tmux_log(), '')

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
        self.assertEqual(launched['argv'], [INSTRUCTION % shq(shown), '-n', 'w1', '--model', 'm', '--effort',
                                            'high', '--settings', settings, '--allowedTools', tools])
        self.assertEqual(Path(launched['cwd']).resolve(), self.cwd.resolve())
        self.assertEqual(self.tmux_log(), '')
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
        # The tab measures claude's own run, and waits for Enter after a quick end of any status.
        tab = json.loads((self.state / 'wt.json').read_text())[-1]
        self.assertIn('t=$(date +%s); claude ', tab)
        self.assertIn('press Enter to close', tab)

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
            self.assertEqual(launched['argv'][-6:], ['-n', 'w1', '--model', 'm', '--effort', 'high'])
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
        # A second spawn under the same name, once the session is closed, would reuse a stale
        # branch: refused by name.
        (self.state / 'tmux.log').unlink()
        (self.state / 'started').unlink()
        again = self.spawn('w3', str(self.brief), '--worktree')
        self.assertNotEqual(again.returncode, 0)
        self.assertIn('worktree-w3', again.stderr)
        self.assertNotIn('new-session', self.tmux_log())

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
        (scripts / 'spawn_worker.sh').write_text(SCRIPT.read_text())
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


if __name__ == '__main__':
    unittest.main()
