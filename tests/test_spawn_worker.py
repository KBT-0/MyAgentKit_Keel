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

    def spawn(self, *args):
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}',
                   SPAWN_STATE=str(self.state))
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


if __name__ == '__main__':
    unittest.main()
