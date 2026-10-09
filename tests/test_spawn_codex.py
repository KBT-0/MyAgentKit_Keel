"""spawn_codex.sh must start Codex sandboxed with the repository's git directory writable, record
its session id, and answer a stopped worker in that same session.

No live `codex`, tmux or terminal: each is a stub on PATH. The codex stub writes a session the
way Codex 0.162 does ($CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl, a `session_meta` first
line), and the terminal stub runs the tab's script as Windows Terminal would.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_spawn_worker import WT_TAB, shq

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'overlays/claude-code/files/scripts/spawn_codex.sh'
WINDOWS = os.name == 'nt'
INSTRUCTION = ("Read %s and follow it. Do not ask questions in this pane: write a question into your "
               "result file and go on with what does not depend on it.")

CODEX = r'''#!/usr/bin/env python3
import json, os, sys
state, args = os.environ['SPAWN_STATE'], sys.argv[1:]
with open(os.path.join(state, 'codex.log'), 'a') as log:
    log.write(json.dumps({'argv': args, 'cwd': os.getcwd()}) + '\n')
if args[0] != 'resume' and 'CODEX_SILENT' not in os.environ:
    folder = os.path.join(os.environ['CODEX_HOME'], 'sessions', '2026', '10', '09')
    os.makedirs(folder, exist_ok=True)
    sid = 'sess-%d' % len(os.listdir(folder))
    with open(os.path.join(folder, 'rollout-2026-10-09T10-00-00-%s.jsonl' % sid), 'w') as f:
        f.write(json.dumps({'type': 'session_meta', 'payload': {'id': sid, 'cwd': args[args.index('-C') + 1]}}) + '\n')
        f.write(json.dumps({'type': 'response_item', 'payload': {'content': [{'text': args[0]}]}}) + '\n')
'''

# cygpath as Git for Windows has it, for the POSIX hosts that stand in for Windows here.
CYGPATH = r'''#!/usr/bin/env python3
import sys
print('C:' + sys.argv[2].replace('/', '\\') if sys.argv[1] == '-w' else sys.argv[2])
'''

TMUX = r'''#!/usr/bin/env python3
import os, subprocess, sys
state, args = os.environ['SPAWN_STATE'], sys.argv[1:]
with open(os.path.join(state, 'tmux.log'), 'a') as log:
    log.write(repr(args) + '\n')
if args[0] == 'has-session':
    sys.exit(0 if os.path.exists(os.path.join(state, 'live')) else 1)
if args[0] == 'new-session':
    sys.exit(subprocess.run(['sh', '-c', args[-1]]).returncode)
'''


class SpawnCodexTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.state, self.bin, self.repo, self.home = (self.tmp / n for n in ('state', 'bin', 'repo', 'codex-home'))
        for folder in (self.state, self.bin, self.repo, self.home):
            folder.mkdir()
        stubs = {'codex': CODEX, 'tmux': TMUX, 'wt-tab': WT_TAB, 'sleep': '#!/bin/sh\nexit 0\n',
                 'show_workers': '#!/bin/sh\nexit 0\n', 'ps-stub': '#!/bin/sh\ncat "$SPAWN_STATE/ps" 2>/dev/null\nexit 0\n'}
        if not WINDOWS:
            stubs.update(cygpath=CYGPATH, uname='#!/bin/sh\necho MINGW64_NT-10.0-26200\n')
        for name, body in stubs.items():
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        git = lambda *a: subprocess.run(['git', *a], cwd=self.repo, check=True, capture_output=True)
        git('init', '-q')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty', '-m', 'a')
        # A `;` (a new-tab separator for wt.exe) and an apostrophe (a shell quote) in the path.
        self.brief = self.tmp / "brief; it's.md"
        self.brief.write_text('A brief.\n')

    def tearDown(self):
        self._tmp.cleanup()

    def win(self, path, flag='-w'):
        if WINDOWS:
            return subprocess.run(['cygpath', flag, str(path)], capture_output=True, text=True,
                                  check=True).stdout.rstrip('\n')
        return 'C:' + str(path).replace('/', '\\') if flag == '-w' else str(path)

    def spawn(self, *args, tmux=False, **extra):
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}', SPAWN_STATE=str(self.state),
                   CODEX_HOME=str(self.home), KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=str(self.bin / 'ps-stub'), **extra)
        if tmux:
            (self.bin / 'uname').write_text('#!/bin/sh\necho Linux\n')
            (self.bin / 'uname').chmod(0o755)
        return subprocess.run(['sh', str(SCRIPT), *args], cwd=self.repo, env=env,
                              capture_output=True, text=True, timeout=60)

    def runs(self):
        path = self.state / 'codex.log'
        return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []

    def test_a_worker_starts_sandboxed_with_the_git_directory_writable_and_its_session_recorded(self):
        result = self.spawn('w1', str(self.brief), '--model', 'gpt-x', '--effort', 'high', '--worktree')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tree = self.repo / '.claude/worktrees/w1'
        (run,) = self.runs()
        # The instruction first; the sandbox with no prompts; the common .git, which holds the
        # worktree's own git directory, its objects and refs, writable (issue #43).
        self.assertEqual(run['argv'], [INSTRUCTION % shq(self.win(self.brief, '-m')), '-m', 'gpt-x', '-c', 'model_reasoning_effort=high', '-s', 'workspace-write',
                                       '-a', 'never', '--add-dir', self.win(self.repo / '.git'), '-C', self.win(tree)])
        self.assertEqual(Path(run['cwd']).resolve(), tree.resolve())
        branch = subprocess.run(['git', '-C', str(tree), 'branch', '--show-current'], capture_output=True, text=True)
        self.assertEqual(branch.stdout.strip(), 'worktree-w1')
        # The tab's script ends with `exit 0` and is deleted.
        tab = json.loads((self.state / 'wt.json').read_text())
        self.assertTrue(tab[-1].endswith('\nexit 0\n'), tab[-1])
        # The id is recorded in the worktree's own git directory, never as a file in the worktree.
        record = self.repo / '.git/worktrees/w1/codex-session-w1'
        self.assertEqual(record.read_text().strip(), 'sess-0')
        self.assertIn('session sess-0 recorded', result.stdout)
        self.assertIn('--worktree --resume', result.stdout)
        self.assertIn('the lead commits its work (issue #43)', result.stdout)
        self.assertEqual(subprocess.run(['git', '-C', str(tree), 'status', '--porcelain'], capture_output=True,
                                        text=True).stdout, '')

    def test_a_stopped_worker_is_answered_in_its_own_session(self):
        self.assertEqual(self.spawn('w2', str(self.brief), '--model', 'm', '--effort', 'high').returncode, 0)
        answer = self.tmp / 'answer.md'
        answer.write_text('Take option B.\n')
        # While its session still runs in this folder, a resume (or a second spawn) is refused.
        (self.state / 'ps').write_text('41 codex.exe -s workspace-write -C %s "Read ..."\r\n' % self.win(self.repo))
        refused = self.spawn('w2', str(answer), '--model', 'm', '--effort', 'high', '--resume')
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn('already runs in', refused.stderr)
        self.assertIn('(process 41)', refused.stderr)
        self.assertEqual(len(self.runs()), 1)
        # A folder that only starts with this one's name is another worker's.
        (self.state / 'ps').write_text('42 codex.exe -C %s-two "Read ..."\r\n' % self.win(self.repo))
        result = self.spawn('w2', str(answer), '--model', 'm', '--effort', 'high', '--resume')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run = self.runs()[-1]
        # The recorded id, without searching: `codex resume <id> <answer instruction>`.
        self.assertEqual(run['argv'][:2], ['resume', 'sess-0'])
        self.assertIn(self.win(answer, '-m'), run['argv'][2])
        self.assertEqual(run['argv'][-2:], ['-C', self.win(self.repo)])
        # An id named on the command line wins.
        result = self.spawn('w2', str(answer), '--resume', 'other-id', '--model', 'm', '--effort', 'high')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.runs()[-1]['argv'][:2], ['resume', 'other-id'])

    def test_resume_without_a_recorded_session_is_refused(self):
        result = self.spawn('w3', str(self.brief), '--model', 'm', '--effort', 'high', '--resume')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('no session id recorded', result.stderr)
        self.assertEqual(self.runs(), [])

    def test_a_session_that_never_shows_is_reported_not_recorded(self):
        result = self.spawn('w4', str(self.brief), '--model', 'm', '--effort', 'high', CODEX_SILENT='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('WARNING: no Codex session', result.stdout)
        self.assertFalse((self.repo / '.git/codex-session-w4').exists())

    def test_a_worker_without_its_model_or_effort_or_brief_is_refused(self):
        for args, message in ((('--effort', 'high'), '--model is required'), (('--model', 'm'), '--effort is required'),
                              (('--model', 'm', '--effort', 'high', '--x\x1b[2J'), 'unknown option')):
            with self.subTest(args=args):
                result = self.spawn('w5', str(self.brief), *args)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(message, result.stderr)
                self.assertNotIn('\x1b', result.stderr)
        result = self.spawn('w5', str(self.tmp / 'absent.md'), '--model', 'm', '--effort', 'high')
        self.assertIn('brief file not found', result.stderr)
        result = self.spawn('w\x1b5', str(self.brief), '--model', 'm', '--effort', 'high')
        self.assertIn('control character', result.stderr)
        self.assertEqual(self.runs(), [])

    def test_elsewhere_the_worker_is_a_tmux_session(self):
        if WINDOWS:
            # Native Windows never takes the tmux path, and its paths do not reach it.
            sys.stderr.write('\nNOT RUN: %s (the tmux path, POSIX only)\n' % self.id())
            return
        result = self.spawn('w6', str(self.brief), '--model', 'm', '--effort', 'high', tmux=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("'new-session', '-d', '-s', 'w6'", (self.state / 'tmux.log').read_text())
        run = self.runs()[0]
        self.assertEqual(run['argv'][0], INSTRUCTION % shq(str(self.brief)))
        self.assertEqual(run['argv'][-2:], ['-C', str(self.repo)])
        self.assertEqual((self.repo / '.git/codex-session-w6').read_text().strip(), 'sess-0')
        # A tmux session of that name still running is never resumed beside.
        (self.state / 'live').write_text('')
        result = self.spawn('w6', str(self.brief), '--model', 'm', '--effort', 'high', '--resume', tmux=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("tmux session 'w6' still runs", result.stderr)


if __name__ == '__main__':
    unittest.main()
