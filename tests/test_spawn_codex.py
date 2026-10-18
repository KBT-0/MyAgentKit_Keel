"""spawn_codex.sh leaves sandboxed work uncommitted for the lead, records its session id,
and answers a stopped worker in that same session.

No live `codex`, tmux or terminal: each is a stub on PATH. The codex stub writes a session the
way Codex 0.162 does ($CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl, a `session_meta` first
line), and the terminal stub runs the tab's script as Windows Terminal would.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

import test_spawn_worker
from test_spawn_worker import MARKERS, WT_TAB, shq

# Every bound here times MYAGENTKIT_TEST_TIMEOUT_SCALE: check_kit raises it while units run
# side by side, and a fixed 60 s or 20 s ran out on a loaded host (#146).
SCALE = float(os.environ.get('MYAGENTKIT_TEST_TIMEOUT_SCALE', '1'))

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'overlays/claude-code/files/scripts/spawn_codex.sh'
WINDOWS = os.name == 'nt'
# Run inside a Codex worker, the suite inherits its supervisor's KIT_WORKER_* settings; a
# fixture supervisor must never write the caller's records. A case sets its own explicitly.
for _name in [n for n in os.environ if n.startswith('KIT_WORKER_')]:
    del os.environ[_name]
INSTRUCTION = ("Read %s and follow it. The brief carries its Route: quick|build|deep · Risk: low|medium|high "
               "· Checks: ... line; run the checks it names. Write your result to %s. Leave all work uncommitted and ready for the lead; "
               "list the exact changed and added files in the result. The result's first four lines are "
               "Kind: completed (or Kind: blocked, Kind: handoff, Kind: progress), Task: THE TASK, Attempt: N and "
               "Remaining: WHAT IS LEFT; without them the wrapper never sees the result and keeps this worker open. "
               "The lead reviews the diff through the normal "
               "cross-review, then commits with the usual commit gate. Publish a finished result atomically: write a "
               "temporary file beside it, end with <!-- codex-worker: ready -->, then rename it to the result path "
               "with %s --publish TEMPORARY_FILE DESTINATION, which retries a rename Windows refuses while a poll "
               "reads the file. "
               "If a decision is needed, finish independent work "
               "and stop all jobs first, then write Kind: blocked and QUESTIONS in the result; "
               "publish the blocked result atomically using the same temporary-file, end-marker and rename protocol "
               "before publishing the question atomically to %s using that protocol too. "
               "End your turn immediately after publishing; the wrapper allows 10 seconds to flush before closing "
               "this worker. The lead answers by resuming this same session.")

CODEX = r'''#!/usr/bin/env python3
import json, os, sys
state, args = os.environ['SPAWN_STATE'], sys.argv[1:]
with open(os.path.join(state, 'codex.log'), 'a') as log:
    log.write(json.dumps({'argv': args, 'cwd': os.getcwd(), 'env': sorted(os.environ)}) + '\n')
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

# Retain the Windows command in the tab log, but execute its host Bash in the POSIX stand-in.
CODEX_TAB = WT_TAB.replace(
    "sys.exit(subprocess.run(['sh', script], stdin=subprocess.DEVNULL).returncode)",
    r'''if os.name != 'nt':
    with open(script, 'w') as f:
        f.write(re.sub(r"-- '([A-Za-z]:\\[^']*\\bash(?:\.exe)?)' -c",
                      lambda m: "-- '" + m[1][2:].replace('\\', '/') + "' -c", args[-1]))
sys.exit(subprocess.run(['sh', script], stdin=subprocess.DEVNULL).returncode)''')


TMUX = r'''#!/usr/bin/env python3
import os, subprocess, sys
state, args = os.environ['SPAWN_STATE'], sys.argv[1:]
with open(os.path.join(state, 'tmux.log'), 'a') as log:
    log.write(repr(args) + '\n')
if args[0] == 'has-session':
    sys.exit(0 if os.path.exists(os.path.join(state, 'live')) else 1)
if args[0] == 'new-session':
    # tmux's default shell may be fish: it must only see two plain words, `sh SCRIPT`.
    words = args[-1].split(' ')
    assert len(words) == 2 and words[0] == 'sh' and not set("'\";&|") & set(words[1]), args[-1]
    # The script removes itself when run: read it first, through sh (a Git Bash path).
    text = subprocess.run(['sh', '-c', 'cat "$1"', 'sh', words[1]], capture_output=True, text=True).stdout
    with open(os.path.join(state, 'tmux-script'), 'w') as g:
        g.write(text)
    # The accepted session must be visible to the launcher's ownership confirmation.
    open(os.path.join(state, 'live'), 'w').close()
    directory = args[args.index('-c') + 1]
    if os.name == 'nt':
        directory = subprocess.run(['cygpath', '-m', directory], capture_output=True,
                                   text=True, check=True).stdout.rstrip('\n')
    sys.exit(subprocess.run(['sh', '-c', args[-1]], cwd=directory).returncode)
'''


class SpawnCodexTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.state, self.bin, self.repo, self.home = (self.tmp / n for n in ('state', 'bin', 'repo', 'codex-home'))
        for folder in (self.state, self.bin, self.repo, self.home):
            folder.mkdir()
        stubs = {'codex': CODEX, 'tmux': TMUX, 'wt-tab': CODEX_TAB, 'sleep': '#!/bin/sh\nexit 0\n',
                 'show_workers': '#!/bin/sh\nexit 0\n', 'ps-stub': '#!/bin/sh\ncat "$SPAWN_STATE/ps" 2>/dev/null\nexit 0\n'}
        if not WINDOWS:
            stubs.update(cygpath=CYGPATH, uname='#!/bin/sh\necho MINGW64_NT-10.0-26200\n')
        if WINDOWS:
            # Native Windows' python3 may be an inaccessible WindowsApps alias, and the stubs'
            # shebang names it: every stub runs on this runner's interpreter instead.
            stubs['python3'] = '#!/bin/sh\nexec ' + shq(sys.executable.replace('\\', '/')) + ' "$@"\n'
        for name, body in stubs.items():
            (self.bin / name).write_text(body, newline='\n')
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
                   CODEX_HOME=str(self.home), KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=str(self.bin / 'ps-stub'), KIT_SESSION_WAIT='2', **dict.fromkeys(MARKERS, '1'), CLAUDE_CODE_EXECPATH='x', **extra)
        if tmux:
            (self.bin / 'uname').write_text('#!/bin/sh\necho Linux\n', newline='\n')
            (self.bin / 'uname').chmod(0o755)
        return subprocess.run(['sh', str(SCRIPT), *args], cwd=self.repo, env=env,
                              capture_output=True, text=True, timeout=60 * SCALE)

    def publisher(self, stdout):
        """The interpreter and codex_worker.py as spawn names them, read from its printed wait command."""
        line = next(l for l in stdout.splitlines() if 'for the uncommitted handoff: ' in l)
        return line.partition('for the uncommitted handoff: ')[2].partition(' --wait ')[0]

    def runs(self):
        path = self.state / 'codex.log'
        return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []

    def test_a_worker_starts_sandboxed_without_git_roots_and_its_session_recorded(self):
        result = self.spawn('w1', str(self.brief), '--model', 'gpt-x', '--effort', 'high', '--worktree')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tree = self.repo / '.claude/worktrees/w1'
        (run,) = self.runs()
        # A worker is no child of the lead's Claude Code session; the binary's name is kept.
        self.assertFalse(MARKERS & set(run['env']), run['env'])
        self.assertIn('CLAUDE_CODE_EXECPATH', run['env'])
        # Git metadata remains read-only even with --add-dir (issue #43); the lead commits.
        brief, cresult, cquestion = (shq(self.win(p, '-m')) for p in (self.brief, tree / 'RESULT-w1.md', tree / 'QUESTION-w1.md'))
        self.assertEqual(run['argv'], [INSTRUCTION % (brief, cresult, self.publisher(result.stdout), cquestion), '-m', 'gpt-x', '-c', 'model_reasoning_effort=high',
                                       '-c', 'agents.max_concurrent_threads_per_session=2', '-s', 'workspace-write',
                                       '-a', 'never', '--no-daemon', '-C', self.win(tree)])
        self.assertEqual(Path(run['cwd']).resolve(), tree.resolve())
        branch = subprocess.run(['git', '-C', str(tree), 'branch', '--show-current'], capture_output=True, text=True)
        self.assertEqual(branch.stdout.strip(), 'worktree-w1')
        # Locked until close_worker.sh: the audit never removes a locked worktree.
        self.assertEqual(self.lock(tree), 'kit worker w1')
        # The spend line comes before the start (issue #68).
        self.assertIn("spawn_codex: about to run 'w1': model gpt-x, effort high\n", result.stdout)
        # The tab's script ends with `exit 0` and is deleted.
        tab = json.loads((self.state / 'wt.json').read_text())
        self.assertTrue(tab[-1].endswith('\nexit 0\n'), tab[-1])
        # The spawning checkout owns the record; the worker sandbox need not write it.
        record = self.repo / '.myagentkit/workers/w1.session'
        self.assertEqual(record.read_text().strip(), 'sess-0')
        self.assertIn('session sess-0 recorded', result.stdout)
        self.assertIn('--worktree', result.stdout)
        self.assertIn('--resume', result.stdout)
        self.assertIn('leave all work uncommitted', result.stdout)
        self.assertNotIn('--add-dir', run['argv'])
        self.assertIn(self.win(tree / 'QUESTION-w1.md', '-m'), run['argv'][0])

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
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('no Codex session', result.stderr)
        self.assertFalse((self.repo / '.myagentkit/workers/w4.session').exists())
        # The worker runs anyway: the lead still gets its wait command and the resume form.
        self.assertIn('background command for the uncommitted handoff: ', result.stdout)
        self.assertIn('--resume SESSION_ID', result.stderr)

    def test_a_session_whose_decision_record_fails_says_what_is_left(self):
        # NAME.session written, then NAME.question refused (a folder in its place): the message
        # said "nothing is recorded" while the session record stayed.
        records = self.repo / '.myagentkit/workers'
        (records / 'w5.question').mkdir(parents=True)
        result = self.spawn('w5', str(self.brief), '--model', 'm', '--effort', 'high')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertNotIn('nothing is recorded', result.stderr)
        self.assertEqual((records / 'w5.session').read_text().strip(), 'sess-0')
        self.assertIn('session sess-0 was found', result.stderr)
        self.assertIn('left: ' + str(records / 'w5.session').replace('\\', '/'), result.stderr.replace('\\', '/'))
        self.assertIn("--resume 'sess-0'", result.stderr)

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
        # tmux got `sh SCRIPT`; the script carries the env -u prefix and the quoted command.
        script = (self.state / 'tmux-script').read_text()
        self.assertIn('exec env -u CLAUDE_CODE_CHILD_SESSION ', script)
        self.assertIn(' -- sh -c ', script)
        run = self.runs()[0]
        self.assertEqual(run['argv'][0], INSTRUCTION % (shq(str(self.brief)), shq(str(self.repo / 'RESULT-w6.md')),
                                                        self.publisher(result.stdout), shq(str(self.repo / 'QUESTION-w6.md'))))
        self.assertEqual(run['argv'][-2:], ['-C', str(self.repo)])
        self.assertFalse(MARKERS & set(run['env']), run['env'])
        self.assertEqual((self.repo / '.myagentkit/workers/w6.session').read_text().strip(), 'sess-0')
        # A tmux session of that name still running is never resumed beside.
        (self.state / 'live').write_text('')
        result = self.spawn('w6', str(self.brief), '--model', 'm', '--effort', 'high', '--resume', tmux=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("tmux session 'w6' still runs", result.stderr)

    def test_unsafe_tmpdir_is_refused_before_tmux_can_expand_it(self):
        if WINDOWS:
            sys.stderr.write('\nNOT RUN: %s (the tmux path, POSIX only)\n' % self.id())
            return
        for folder in ('temp$(touch INJECTED)', 'temp`touch INJECTED`', 'temp$REVIEW_SEGMENT'):
            with self.subTest(folder=folder):
                tmpdir = self.tmp / folder
                tmpdir.mkdir()
                result = self.spawn('unsafe-temp', str(self.brief), '--model', 'm', '--effort', 'high',
                                    tmux=True, TMPDIR=str(tmpdir))
                self.assertFalse((self.repo / 'INJECTED').exists(), 'TMPDIR ran as shell code')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('TMPDIR', result.stderr)
                self.assertNotIn("'new-session'", (self.state / 'tmux.log').read_text())
                self.assertEqual(self.runs(), [])
                self.assertEqual(list(tmpdir.iterdir()), [], 'the refused script was left behind')

    def test_tmpdir_with_a_space_is_refused_by_name(self):
        if WINDOWS:
            sys.stderr.write('\nNOT RUN: %s (the tmux path, POSIX only)\n' % self.id())
            return
        tmpdir = self.tmp / 'temp space'
        tmpdir.mkdir()
        result = self.spawn('spaced-temp', str(self.brief), '--model', 'm', '--effort', 'high',
                            tmux=True, TMPDIR=str(tmpdir))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('TMPDIR', result.stderr)
        self.assertNotIn("'new-session'", (self.state / 'tmux.log').read_text())
        self.assertEqual(self.runs(), [])
        self.assertEqual(list(tmpdir.iterdir()), [])

    def test_refused_tmpdir_with_worktree_leaves_no_worktree_or_branch(self):
        if WINDOWS:
            sys.stderr.write('\nNOT RUN: %s (the tmux path, POSIX only)\n' % self.id())
            return
        tmpdir = self.tmp / 'refused temp'
        tmpdir.mkdir()
        result = self.spawn('refused-temp', str(self.brief), '--model', 'm', '--effort', 'high',
                            '--worktree', tmux=True, TMPDIR=str(tmpdir))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('TMPDIR', result.stderr)
        self.assertFalse((self.repo / '.claude/worktrees/refused-temp').exists())
        trees = subprocess.run(['git', 'worktree', 'list', '--porcelain'], cwd=self.repo,
                               capture_output=True, text=True, check=True).stdout
        self.assertNotIn('refused-temp', trees)
        branches = subprocess.run(['git', 'branch', '--list', 'worktree-refused-temp'], cwd=self.repo,
                                  capture_output=True, text=True, check=True).stdout
        self.assertEqual(branches, '')
        self.assertEqual(list(tmpdir.iterdir()), [])

    def test_term_after_tmux_accepts_preserves_the_panes_script(self):
        (self.bin / 'tmux').write_text(test_spawn_worker.ACCEPT_THEN_TERM, newline='\n')
        tmpdir = self.tmp / 'session-temp'
        tmpdir.mkdir()
        result = self.spawn('accepted', str(self.brief), '--model', 'm', '--effort', 'high',
                            tmux=True, TMPDIR=str(tmpdir))
        self.assertEqual(result.returncode, 143, result.stdout + result.stderr)
        self.assertEqual(len(list(tmpdir.iterdir())), 1, 'parent deleted the accepted script')
        lock = self.repo / '.myagentkit/workers/spawn.lock'
        self.assertTrue((lock / 'accepted').exists(), 'accepted launch lost its recovery reservation')
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}',
                   SPAWN_STATE=str(self.state), CODEX_HOME=str(self.home))
        pane = subprocess.run(['sh', '-c', (self.state / 'accepted').read_text()], cwd=self.repo,
                              env=env, capture_output=True, text=True, timeout=20 * SCALE)
        self.assertEqual(pane.returncode, 0, pane.stdout + pane.stderr)
        self.assertEqual(len(self.runs()), 1, 'the delayed pane could not start')
        self.assertEqual(list(tmpdir.iterdir()), [])

    def test_unlink_failure_does_not_prevent_reservation_release(self):
        (self.bin / 'rm').write_text('#!/bin/sh\necho injected-unlink-failure >&2\nexit 1\n', newline='\n')
        (self.bin / 'rm').chmod(0o755)
        tmpdir = self.tmp / 'session-temp'
        tmpdir.mkdir()
        result = self.spawn('unlink', str(self.brief), '--model', 'm', '--effort', 'high',
                            '--result', '../outside.md', tmux=True, TMPDIR=str(tmpdir))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('injected-unlink-failure', result.stderr)
        self.assertEqual(len(list(tmpdir.iterdir())), 1, 'unlink failure was not exercised')
        self.assertFalse((self.repo / '.myagentkit/workers/spawn.lock').exists())
        self.assertEqual(self.runs(), [])

    def test_dash_term_before_launch_removes_script_and_reservation(self):
        if WINDOWS or not shutil.which('dash'):  # Fedora, Arch and FreeBSD ship no dash
            sys.stderr.write('\nNOT RUN: %s (dash signal handling, POSIX with dash only)\n' % self.id())
            return
        (self.bin / 'uname').write_text('#!/bin/sh\necho Linux\n', newline='\n')
        (self.bin / 'python3').write_text(test_spawn_worker.PRELAUNCH_TERM, newline='\n')
        (self.bin / 'python3').chmod(0o755)
        tmpdir = self.tmp / 'session-temp'
        tmpdir.mkdir()
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}',
                   SPAWN_STATE=str(self.state), CODEX_HOME=str(self.home), TMPDIR=str(tmpdir))
        result = test_spawn_worker.run_with_launcher_pid('dash', SCRIPT, ['interrupted', str(self.brief),
                                 '--model', 'm', '--effort', 'high'], cwd=self.repo, env=env,
                                capture_output=True, text=True, timeout=20 * SCALE)
        self.assertEqual(result.returncode, 143, result.stdout + result.stderr)
        self.assertEqual(list(tmpdir.iterdir()), [])
        self.assertFalse((self.repo / '.myagentkit/workers/spawn.lock').exists())
        self.assertEqual(self.runs(), [])

    def test_int_before_tmux_creates_session_removes_script_and_reservation(self):
        (self.bin / 'uname').write_text('#!/bin/sh\necho Linux\n', newline='\n')
        (self.bin / 'tmux').write_text(test_spawn_worker.FAIL_THEN_INT, newline='\n')
        tmpdir = self.tmp / 'session-temp'
        tmpdir.mkdir()
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}',
                   SPAWN_STATE=str(self.state), CODEX_HOME=str(self.home), TMPDIR=str(tmpdir))
        result = test_spawn_worker.run_with_launcher_pid('sh', SCRIPT, ['interrupted', str(self.brief),
                                 '--model', 'm', '--effort', 'high'], cwd=self.repo, env=env,
                                capture_output=True, text=True, timeout=60 * SCALE)
        self.assertEqual(result.returncode, 130, result.stdout + result.stderr)
        self.assertEqual(list(tmpdir.iterdir()), [])
        self.assertFalse((self.repo / '.myagentkit/workers/spawn.lock').exists())
        self.assertEqual(self.runs(), [])

    def test_two_signals_never_remove_a_replacement_reservation(self):
        (self.bin / 'uname').write_text('#!/bin/sh\necho Linux\n', newline='\n')
        (self.bin / 'rmdir').write_text('''#!/bin/sh
for path do :; done
case "$path" in */spawn.lock)
  echo release >> "$SPAWN_STATE/cleanup.log"
  /bin/rmdir "$@" || exit 1
  /bin/mkdir "$path"
  if [ "$(wc -l < "$SPAWN_STATE/cleanup.log")" -eq 1 ]; then
    kill -INT "$(cat "$SPAWN_STATE/launcher.pid")"
    kill -TERM "$(cat "$SPAWN_STATE/launcher.pid")"
  fi
  ;; *) /bin/rmdir "$@" ;;
esac
''', newline='\n')
        (self.bin / 'rmdir').chmod(0o755)
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}',
                   SPAWN_STATE=str(self.state), CODEX_HOME=str(self.home))
        result = test_spawn_worker.run_with_launcher_pid('sh', SCRIPT, ['interrupted', str(self.brief),
                                 '--model', 'm', '--effort', 'high', '--result', '../outside.md'],
                                cwd=self.repo, env=env, capture_output=True, text=True, timeout=60 * SCALE)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.state / 'cleanup.log').read_text().splitlines(), ['release'])
        self.assertTrue((self.repo / '.myagentkit/workers/spawn.lock').is_dir())

    def test_cleanup_does_not_release_another_spawners_reservation(self):
        # Replace ownership while validation is interrupted; cleanup must leave the new lock alone.
        (self.bin / 'uname').write_text('#!/bin/sh\necho Linux\n', newline='\n')
        (self.bin / 'rmdir').write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$SPAWN_STATE/rmdir.log"\n/bin/rmdir "$@"\n',
                                     newline='\n')
        (self.bin / 'rmdir').chmod(0o755)
        (self.bin / 'python3').write_text('''#!/bin/sh
lock="$PWD/.myagentkit/workers/spawn.lock"
/bin/rmdir "$lock"/.owner-*
/bin/mkdir "$lock/.owner-other"
kill -TERM "$(cat "$SPAWN_STATE/launcher.pid")"
exit 1
''', newline='\n')
        (self.bin / 'python3').chmod(0o755)
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}',
                   SPAWN_STATE=str(self.state), CODEX_HOME=str(self.home))
        result = test_spawn_worker.run_with_launcher_pid('sh', SCRIPT, ['interrupted', str(self.brief),
                                 '--model', 'm', '--effort', 'high'], cwd=self.repo, env=env,
                                capture_output=True, text=True, timeout=60 * SCALE)
        self.assertEqual(result.returncode, 143, result.stdout + result.stderr)
        self.assertEqual([p.name for p in (self.repo / '.myagentkit/workers/spawn.lock').iterdir()],
                         ['.owner-other'])
        self.assertFalse((self.state / 'rmdir.log').exists(), 'cleanup tried to release another owner\'s lock')

    def test_later_validation_failure_removes_the_reserved_session_script(self):
        if WINDOWS:
            sys.stderr.write('\nNOT RUN: %s (the tmux path, POSIX only)\n' % self.id())
            return
        tmpdir = self.tmp / 'session-temp'
        tmpdir.mkdir()
        result = self.spawn('late-failure', str(self.brief), '--model', 'm', '--effort', 'high',
                            '--result', '../outside.md', tmux=True, TMPDIR=str(tmpdir))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('invalid result path', result.stderr)
        self.assertEqual(list(tmpdir.iterdir()), [], 'the reserved script was left behind')

    def test_relative_tmpdir_launches_in_a_worktree_with_an_absolute_script_path(self):
        if WINDOWS:
            sys.stderr.write('\nNOT RUN: %s (the tmux path, POSIX only)\n' % self.id())
            return
        tmpdir = self.tmp / 'session-temp'
        tmpdir.mkdir()
        result = self.spawn('relative-temp', str(self.brief), '--model', 'm', '--effort', 'high',
                            '--worktree', tmux=True, TMPDIR='../session-temp')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(Path(self.runs()[0]['cwd']).resolve(),
                         (self.repo / '.claude/worktrees/relative-temp').resolve())
        self.assertIn('sh ' + str(tmpdir) + '/', (self.state / 'tmux.log').read_text())
        self.assertEqual(list(tmpdir.iterdir()), [], 'the launched script did not remove itself')

    def test_an_unsafe_name_or_control_byte_in_model_is_refused_before_launch(self):
        for name, model, effort in (('../escape', 'm', 'high'), ('a/b', 'm', 'high'),
                                    ('w7', 'm\x1b', 'high'), ('w7', 'm', 'bad\nvalue')):
            result = self.spawn(name, str(self.brief), '--model', model, '--effort', effort)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(self.runs(), [])

    def test_a_question_file_blocks_a_fresh_replacement(self):
        question = self.repo / 'QUESTION-w8.md'
        question.write_text('Choose A or B.\n')
        result = self.spawn('w8', str(self.brief), '--model', 'm', '--effort', 'high')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('--resume', result.stderr)
        self.assertEqual(self.runs(), [])

    def test_empty_session_record_is_refused_without_opening_a_picker(self):
        record = self.repo / '.myagentkit/workers/w9.session'
        record.parent.mkdir(parents=True)
        record.write_text('')
        result = self.spawn('w9', str(self.brief), '--resume', '--model', 'm', '--effort', 'high')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('session id is empty', result.stderr)
        self.assertEqual(self.runs(), [])

    def test_custom_result_sidecars_are_reused_on_resume(self):
        result_file = self.repo / "custom; it's.md"
        args = ('--model', 'm', '--effort', 'high', '--result', str(result_file))
        result = self.spawn('w10', str(self.brief), *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = self.repo / '.myagentkit/workers/w10.session'
        question = Path(str(result_file) + '.question.md')
        self.assertEqual(record.read_text().strip(), 'sess-0')
        self.assertIn(shq(self.win(question, '-m')), self.runs()[0]['argv'][0])
        question.write_text('Choose A or B.\n')
        result = self.spawn('w10', str(self.brief), *args, '--resume')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.runs()[-1]['argv'][:2], ['resume', 'sess-0'])
        self.assertFalse(question.exists())

    def test_a_unicode_result_path_is_accepted(self):
        # Python's own -I ignores PYTHONUTF8: a cp1252 stdout could not print this path.
        result_file = self.repo / 'report-Ş-😀.md'
        result = self.spawn('w19', str(self.brief), '--model', 'm', '--effort', 'high', '--result', str(result_file))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(self.win(result_file, '-m'), self.runs()[0]['argv'][0])

    def test_record_only_refuses_fresh_replacement(self):
        record = self.repo / '.myagentkit/workers/w11.session'
        record.parent.mkdir(parents=True)
        record.write_text('saved-session\n')
        result = self.spawn('w11', str(self.brief), '--model', 'm', '--effort', 'high')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('answer it with --resume', result.stderr)
        self.assertEqual(self.runs(), [])

    def test_result_outside_worker_or_non_markdown_is_refused(self):
        for result_path in (self.tmp / 'outside.md', self.repo / 'x.txt'):
            result = self.spawn('w12', str(self.brief), '--model', 'm', '--effort', 'high',
                                '--result', str(result_path))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(self.runs(), [])

    def test_default_result_uses_repository_top_from_subfolder(self):
        sub = self.repo / 'sub'
        sub.mkdir()
        original = self.repo
        self.repo = sub
        try:
            result = self.spawn('w13', str(self.brief), '--model', 'm', '--effort', 'high')
        finally:
            self.repo = original
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(shq(self.win(original / 'RESULT-w13.md', '-m')), self.runs()[0]['argv'][0])
        self.assertEqual(Path(self.runs()[0]['cwd']).resolve(), original.resolve())

    def test_question_instruction_requires_atomic_publish_end_marker_and_grace(self):
        result = self.spawn('w14', str(self.brief), '--model', 'm', '--effort', 'high')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        prompt = self.runs()[0]['argv'][0]
        self.assertIn('atomically', prompt)
        self.assertIn('<!-- codex-worker: ready -->', prompt)
        self.assertIn('publish the blocked result atomically using the same temporary-file, end-marker and rename protocol before publishing the question', prompt)
        self.assertIn('--wait', result.stdout)
        # The stub Codex ended on its own: the wrapper left the exit record --wait watches.
        exited = self.repo / '.myagentkit/workers/w14.exit'
        self.assertIn('--exit ' + shq(self.win(exited, '-m')), result.stdout)
        self.assertTrue(exited.read_text().startswith('exit 0'), exited)

    def test_a_published_completed_result_ends_the_worker_and_its_tab_exits_0(self):
        # Owner 2026-10-16: finished worker tabs stayed open for hours. The worker publishes a
        # completed result and stays at its prompt, as the Codex TUI does; the wrapper ends it and
        # the tab's script ends with exit 0, on which Windows Terminal closes the tab (closeOnExit
        # "automatic", its default, is "graceful" for a process it launched itself).
        (self.bin / 'codex').write_text(CODEX + r'''
if args[0] != 'resume':
    import time
    from pathlib import Path
    target = Path(args[args.index('-C') + 1]) / 'RESULT-w30.md'
    if os.name != 'nt':
        target = Path(args[args.index('-C') + 1][2:].replace('\\', '/')) / 'RESULT-w30.md'
    temporary = target.with_name(target.name + '.tmp')
    temporary.write_text('Kind: completed\nTask: t\nAttempt: 1\nRemaining: none\n<!-- codex-worker: ready -->\n')
    os.replace(temporary, target)
    time.sleep(120)
''', newline='\n')
        started = time.monotonic()
        result = self.spawn('w30', str(self.brief), '--model', 'm', '--effort', 'high', KIT_WORKER_GRACE='0')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertLess(time.monotonic() - started, 60, 'the worker ran on after its completed result')
        self.assertIn('DONE: uncommitted result ready for the lead', result.stdout)
        self.assertTrue((self.repo / '.myagentkit/workers/w30.exit').read_text().startswith('DONE published'))
        tab = json.loads((self.state / 'wt.json').read_text())
        self.assertTrue(tab[-1].endswith('\nexit 0\n'), tab[-1])

    def test_the_instruction_names_the_result_header_the_wrapper_needs(self):
        # b2fix2 (2026-10-16) published `Kind: completed` and the end marker without the Task,
        # Attempt and Remaining lines: the wrapper never saw DONE and its tab stayed for hours.
        result = self.spawn('w31', str(self.brief), '--model', 'm', '--effort', 'high')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        prompt = self.runs()[0]['argv'][0]
        for line in ('Kind: completed', 'Task: ', 'Attempt: N', 'Remaining: '):
            self.assertIn(line, prompt)

    def test_tab_preserves_quick_exit_error(self):
        (self.bin / 'codex').write_text('#!/bin/sh\necho bad-model >&2\nexit 1\n', newline='\n')
        result = self.spawn('w15', str(self.brief), '--model', 'm', '--effort', 'high')
        self.assertEqual(result.returncode, 1)
        self.assertIn('bad-model', result.stderr)
        self.assertIn('press Enter to close', result.stdout)

    def test_worker_uses_absolute_git_bash(self):
        result = self.spawn('w17', str(self.brief), '--model', 'm', '--effort', 'high')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tab = json.loads((self.state / 'wt.json').read_text())[-1]
        self.assertNotIn('-- bash -c', tab)
        self.assertRegex(tab, r"-- '[A-Za-z]:\\[^']*bash(?:\.exe)?' -c")

    def test_sidecars_do_not_ignore_project_questions_or_accept_txt_results(self):
        (self.repo / '.gitignore').write_bytes((ROOT / 'core/.gitignore').read_bytes())
        for path, ignored in (('QUESTION-w.md', True), ('docs/QUESTION-design.md', False),
                              ('.myagentkit/workers/w.session', True), ('custom.md.question.md', True)):
            result = subprocess.run(['git', 'check-ignore', '--no-index', path], cwd=self.repo,
                                    capture_output=True)
            self.assertEqual(result.returncode == 0, ignored, path)

    def test_close_removes_lead_record_and_allows_name_reuse(self):
        args = ('--model', 'm', '--effort', 'high')
        result = self.spawn('w16', str(self.brief), *args, '--worktree')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tree = self.repo / '.claude/worktrees/w16'
        record = self.repo / '.myagentkit/workers/w16.session'
        self.assertTrue(record.exists(), 'session must be stored outside the worker tree')
        self.assertFalse((tree / 'RESULT-w16.session').exists())
        git = lambda *a: subprocess.run(['git', *a], cwd=self.repo, check=True, capture_output=True)
        git('-C', str(tree), '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit',
            '--allow-empty', '-m', 'worker complete')
        git('merge', '--ff-only', 'worktree-w16')
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}',
                   SPAWN_STATE=str(self.state), KIT_PS=str(self.bin / 'ps-stub'))
        closed = subprocess.run(['sh', str(SCRIPT.with_name('close_worker.sh')), 'w16'],
                                cwd=self.repo, env=env, capture_output=True, text=True, timeout=45 * SCALE)
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertFalse(tree.exists())
        self.assertFalse(record.exists())
        self.assertFalse(record.with_suffix('.exit').exists())
        self.assertEqual(self.spawn('w16', str(self.brief), *args).returncode, 0)

    @staticmethod
    def lock(tree):
        """The worktree's lock reason, or None when it is not locked."""
        gitdir = subprocess.run(['git', '-C', str(tree), 'rev-parse', '--absolute-git-dir'],
                                capture_output=True, text=True, check=True).stdout.strip()
        locked = Path(gitdir, 'locked')
        return locked.read_text().rstrip('\n') if locked.exists() else None

    def close(self, name, **extra):
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}',
                   SPAWN_STATE=str(self.state), KIT_PS=str(self.bin / 'ps-stub'), **extra)
        return subprocess.run(['sh', str(SCRIPT.with_name('close_worker.sh')), name],
                              cwd=self.repo, env=env, capture_output=True, text=True, timeout=45 * SCALE)

    def test_close_ends_the_codex_session_in_its_own_worktree_on_windows(self):
        # Owner 2026-10-16: a close that refused while Codex ran left its tab open for hours.
        result = self.spawn('w18', str(self.brief), '--model', 'm', '--effort', 'high', '--worktree')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tree = self.repo / '.claude/worktrees/w18'
        record = self.repo / '.myagentkit/workers/w18.session'
        # Finished and merged: only the running session keeps the audit from removing it.
        git = lambda *a: subprocess.run(['git', *a], cwd=self.repo, check=True, capture_output=True)
        git('-C', str(tree), '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--allow-empty', '-m', 'done')
        git('merge', '--ff-only', 'worktree-w18')
        # Native Windows: no tmux and no Claude Code session named w18, only its codex.exe.
        (self.state / 'ps').write_text('4242 "C:\\codex\\codex.exe" resume sess-0 -C %s\r\n' % self.win(tree))
        (self.bin / 'taskkill').write_text('#!/bin/sh\necho "$*" >> "$SPAWN_STATE/taskkill.log"\n'
                                           '[ -n "${SPAWN_KILL_IGNORED:-}" ] || : > "$SPAWN_STATE/ps"\n', newline='\n')
        (self.bin / 'taskkill').chmod(0o755)
        dry = subprocess.run(['sh', str(SCRIPT.with_name('close_worker.sh')), '--dry-run', 'w18'], cwd=self.repo,
                             env=dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}',
                                      SPAWN_STATE=str(self.state), KIT_PS=str(self.bin / 'ps-stub')),
                             capture_output=True, text=True, timeout=45 * SCALE)
        self.assertIn('dry run: would end the Codex session in', dry.stdout, dry.stdout + dry.stderr)
        self.assertFalse((self.state / 'taskkill.log').exists())
        # A session taskkill cannot end keeps everything, its resume id first.
        session = record.read_text().strip()
        closed = self.close('w18', SPAWN_KILL_IGNORED='1')
        self.assertEqual(closed.returncode, 1, closed.stdout + closed.stderr)
        self.assertIn('the Codex session still runs after taskkill (process 4242)', closed.stdout)
        self.assertTrue(record.exists(), 'the only resume id of a running session was deleted')
        self.assertEqual(self.lock(tree), 'kit worker w18', 'a running worker lost its lock')
        closed = self.close('w18')
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertIn('/PID 4242 /T /F', (self.state / 'taskkill.log').read_text())
        self.assertIn('Codex session ended (process 4242', closed.stdout)
        self.assertIn('codex resume ' + session, closed.stdout)
        self.assertFalse(record.exists())
        self.assertFalse(tree.exists())

    def test_close_never_ends_a_session_whose_prompt_names_the_worker_folder(self):
        # Codex r1 (fix56): the lead's quoted prompt held `-C <worker folder>`; a text match on the
        # command line taskkilled the lead. Only the parsed -C argument names a session's folder.
        result = self.spawn('w18', str(self.brief), '--model', 'm', '--effort', 'high', '--worktree')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tree = self.repo / '.claude/worktrees/w18'
        git = lambda *a: subprocess.run(['git', *a], cwd=self.repo, check=True, capture_output=True)
        git('-C', str(tree), '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--allow-empty', '-m', 'done')
        git('merge', '--ff-only', 'worktree-w18')
        (self.state / 'ps').write_text(
            '4141 "C:\\codex\\codex.exe" "close it: codex -C %s now" -C %s\r\n'
            '4242 "C:\\codex\\codex.exe" resume sess-0 -C "%s"\r\n' % (self.win(tree), self.win(self.repo), self.win(tree)))
        (self.bin / 'taskkill').write_text('#!/bin/sh\necho "$*" >> "$SPAWN_STATE/taskkill.log"\n'
                                           'grep -v "^$2 " "$SPAWN_STATE/ps" > "$SPAWN_STATE/ps.new"\n'
                                           'mv "$SPAWN_STATE/ps.new" "$SPAWN_STATE/ps"\n', newline='\n')
        (self.bin / 'taskkill').chmod(0o755)
        closed = self.close('w18')
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertEqual((self.state / 'taskkill.log').read_text().splitlines(), ['/PID 4242 /T /F'], closed.stdout)
        self.assertIn('4141 ', (self.state / 'ps').read_text())

    def test_close_keeps_the_record_of_a_kept_worktree(self):
        result = self.spawn('w19', str(self.brief), '--model', 'm', '--effort', 'high', '--worktree')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tree = self.repo / '.claude/worktrees/w19'
        (tree / 'unfinished.txt').write_text('work in progress\n')
        closed = self.close('w19')
        self.assertEqual(closed.returncode, 1, closed.stdout + closed.stderr)
        self.assertIn('worktree kept', closed.stdout)
        self.assertTrue(tree.exists())
        self.assertTrue((self.repo / '.myagentkit/workers/w19.session').exists(),
                        'a kept, possibly unfinished worker lost its resume id')
        # A closed worker leaves no locked worktree: the audit after a later merge decides.
        self.assertIsNone(self.lock(tree))

    def test_a_resumed_worktree_worker_is_locked_again(self):
        # #240: close_worker.sh unlocks the worktree and keeps it resumable; the resumed run then
        # worked unlocked, and the post-merge close loop, which needs the lock, never closed it.
        args = ('w30', str(self.brief), '--model', 'm', '--effort', 'high', '--worktree')
        self.assertEqual(self.spawn(*args).returncode, 0)
        tree = self.repo / '.claude/worktrees/w30'
        subprocess.run(['git', 'worktree', 'unlock', str(tree)], cwd=self.repo, check=True)
        result = self.spawn(*args, '--resume')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.lock(tree), 'kit worker w30')

    def test_invalid_result_does_not_create_a_worktree_or_branch_and_retry_succeeds(self):
        (self.repo / 'docs').mkdir()
        (self.repo / 'docs/readme.md').write_text('tracked folder\n')
        for args in (('add', 'docs'), ('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'docs')):
            subprocess.run(['git', *args], cwd=self.repo, check=True, capture_output=True)
        args = ('w20', str(self.brief), '--model', 'm', '--effort', 'high', '--worktree')
        for path in (str(self.tmp / 'outside.md'), 'x.txt', 'missing/result.md'):
            result = self.spawn(*args, '--result', path)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertFalse((self.repo / '.claude/worktrees/w20').exists())
            branch = subprocess.run(['git', 'show-ref', '--verify', '--quiet', 'refs/heads/worktree-w20'],
                                    cwd=self.repo)
            self.assertNotEqual(branch.returncode, 0)
            self.assertEqual(self.runs(), [])
        result = self.spawn(*args, '--result', 'docs/result.md')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_spawn_that_fails_after_its_worktree_and_before_its_launch_leaves_neither(self):
        # Ultrareview part 5 #8: a spawn that died after `git worktree add` (here: no terminal to
        # open the tab in) left the worktree locked and its branch behind for good.
        args = ('w21', str(self.brief), '--model', 'm', '--effort', 'high', '--worktree')
        terminal = self.bin / 'wt-tab'
        terminal.rename(self.tmp / 'wt-tab')  # spawn() names it: gone from PATH, no tab opens
        result = self.spawn(*args)
        (self.tmp / 'wt-tab').rename(terminal)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('is not on PATH', result.stderr)
        self.assertIn('removed the unused worktree', result.stderr)
        self.assertFalse((self.repo / '.claude/worktrees/w21').exists())
        branch = subprocess.run(['git', 'show-ref', '--verify', '--quiet', 'refs/heads/worktree-w21'], cwd=self.repo)
        self.assertNotEqual(branch.returncode, 0)
        self.assertEqual(self.runs(), [])
        result = self.spawn(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_spawn_that_loses_the_race_for_its_name_leaves_the_other_spawns_worktree(self):
        # Codex review r2 (Critical): another spawn of the same name made the worktree between the
        # last absence check and `git worktree add`; this spawn's cleanup removed it.
        extra = test_spawn_worker.racing_git(self.bin)
        result = self.spawn('w24', str(self.brief), '--model', 'm', '--effort', 'high', '--worktree', **extra)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        tree = self.repo / '.claude/worktrees/w24'
        self.assertEqual((tree / 'other-session.txt').read_text().strip(), 'other session', result.stderr)
        branch = subprocess.run(['git', 'show-ref', '--verify', '--quiet', 'refs/heads/worktree-w24'], cwd=self.repo)
        self.assertEqual(branch.returncode, 0)
        self.assertNotIn('removed the unused worktree', result.stderr)
        self.assertEqual(self.runs(), [])

    def test_a_spawn_whose_worktree_add_fails_after_making_it_leaves_neither(self):
        # Codex review r1 (High): a failing post-checkout hook makes `git worktree add` exit non-zero
        # with the worktree and branch already made.
        hook = self.repo / '.git/hooks/post-checkout'
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(test_spawn_worker.FAILING_POST_CHECKOUT, newline='\n')
        hook.chmod(0o755)
        args = ('w22', str(self.brief), '--model', 'm', '--effort', 'high', '--worktree')
        result = self.spawn(*args)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('git worktree add failed', result.stderr)
        self.assertFalse((self.repo / '.claude/worktrees/w22').exists(), result.stderr)
        branch = subprocess.run(['git', 'show-ref', '--verify', '--quiet', 'refs/heads/worktree-w22'], cwd=self.repo)
        self.assertNotEqual(branch.returncode, 0)
        self.assertEqual(self.runs(), [])
        hook.unlink()
        result = self.spawn(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_tmux_session_that_ran_and_ended_at_once_keeps_its_worktree(self):
        # Codex review r1 (Critical): a session that started and ended before the has-session check
        # left the launch unmarked, and the cleanup force-removed a worktree a session wrote into.
        (self.bin / 'tmux').write_text(test_spawn_worker.GONE_AT_ONCE, newline='\n')
        result = self.spawn('w23', str(self.brief), '--model', 'm', '--effort', 'high', '--worktree', tmux=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        tree = self.repo / '.claude/worktrees/w23'
        self.assertEqual((tree / 'made-by-session.txt').read_text(), 'session output\n', result.stderr)
        branch = subprocess.run(['git', 'show-ref', '--verify', '--quiet', 'refs/heads/worktree-w23'], cwd=self.repo)
        self.assertEqual(branch.returncode, 0)

    def test_close_without_worktree_keeps_a_live_codex_workers_record(self):
        result = self.spawn('w21', str(self.brief), '--model', 'm', '--effort', 'high')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = self.repo / '.myagentkit/workers/w21.session'
        exited = record.with_suffix('.exit')
        before = record.read_bytes(), exited.read_bytes()
        (self.state / 'ps').write_text('4242 "C:\\codex\\codex.exe" resume sess-0 -C %s\r\n' % self.win(self.repo))
        closed = self.close('w21')
        self.assertEqual(closed.returncode, 1, closed.stdout + closed.stderr)
        self.assertIn('a Codex session still runs', closed.stdout)
        self.assertEqual((record.read_bytes(), exited.read_bytes()), before)
        (self.state / 'ps').write_text('')
        closed = self.close('w21')
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertFalse(record.exists())
        self.assertFalse(exited.exists())

    def test_concurrent_spawns_reserve_the_name_and_checkout_until_recorded(self):
        # Hold the first launch after the process check, before its session is visible.
        gate = self.bin / 'wt-tab'
        gate.write_text(CODEX_TAB.replace('args = sys.argv[1:]', '''args = sys.argv[1:]
import pathlib, time
state = pathlib.Path(os.environ['SPAWN_STATE'])
if os.environ.get('SPAWN_HOLD'):
    (state / 'launching').touch()
    while not (state / 'release').exists(): time.sleep(.05)'''), newline='\n')
        args = ('w22', str(self.brief), '--model', 'm', '--effort', 'high')
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.spawn, *args, SPAWN_HOLD='1')
            try:
                deadline = time.monotonic() + 20
                while not (self.state / 'launching').exists():
                    self.assertFalse(first.done(), first.result() if first.done() else 'launch pending')
                    self.assertLess(time.monotonic(), deadline, 'first launch never reached the terminal')
                    time.sleep(.05)
                second = pool.submit(self.spawn, *args)
                refused = second.result(timeout=15 * SCALE)
                self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
                self.assertIn('spawn in progress', refused.stderr)
                # A second name in the same checkout must not bypass the reservation either.
                refused = self.spawn('w23', str(self.brief), '--model', 'm', '--effort', 'high')
                self.assertNotEqual(refused.returncode, 0, refused.stdout + refused.stderr)
                self.assertIn('spawn in progress', refused.stderr)
            finally:
                (self.state / 'release').touch()
            started = first.result(timeout=30 * SCALE)
        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
        self.assertEqual(len(self.runs()), 1)
        self.assertEqual((self.repo / '.myagentkit/workers/w22.session').read_text().strip(), 'sess-0')
        resumed = self.spawn(*args, '--resume')
        self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)

    def test_printed_resume_command_quotes_the_model_and_round_trips(self):
        marker = self.repo / 'injected'
        model = "m'; : ' value; touch injected; #"
        result = self.spawn('w24', str(self.brief), '--model', model, '--effort', 'high')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        line = next(line for line in result.stdout.splitlines() if 'scripts/spawn_codex.sh w24 ANSWER_FILE ' in line)
        command = line.split(': scripts/spawn_codex.sh ', 1)[1]
        # Execute the printed command with an argv logger in place of the script.
        logger = self.bin / 'argv.py'
        logger.write_text('import json,sys; print(json.dumps(sys.argv[1:]))\n', newline='\n')
        printed = subprocess.run(['sh', '-c', shq(sys.executable.replace('\\', '/')) + ' '
                                  + shq(str(logger).replace('\\', '/')) + ' ' + command],
                                 cwd=self.repo, capture_output=True, text=True, timeout=10 * SCALE)
        self.assertEqual(printed.returncode, 0, printed.stderr)
        self.assertFalse(marker.exists(), 'following the printed command executed the model as shell code')
        argv = json.loads(printed.stdout)
        self.assertEqual(argv[argv.index('--model') + 1], model)
        self.assertEqual(argv[-2:], ['--resume', 'sess-0'])

    def test_printed_late_wait_reuses_identity_captured_before_launch(self):
        result_file = self.repo / 'RESULT-w25.md'
        result_file.write_text('Kind: blocked\nTask: old\nAttempt: 1\nRemaining: decision\n'
                               '<!-- codex-worker: ready -->')
        os.utime(result_file, (time.time() - 60, time.time() - 60))
        (self.bin / 'codex').write_text(CODEX + '''
from pathlib import Path
p = Path(os.environ['RESULT_EDIT'])
p.write_text(p.read_text().replace('Kind: blocked', 'Kind: completed'))
''', newline='\n')
        started = self.spawn('w25', str(self.brief), '--model', 'm', '--effort', 'high',
                             RESULT_EDIT=str(result_file))
        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
        command = next(line.partition('handoff: ')[2] for line in started.stdout.splitlines()
                       if 'background command for the uncommitted handoff: ' in line)
        waited = subprocess.run(['sh', '-c', command], cwd=self.repo, capture_output=True,
                                env=dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH']),
                                text=True, timeout=15 * SCALE)
        self.assertEqual(waited.returncode, 0, waited.stdout + waited.stderr)
        self.assertIn('EXITED', waited.stdout)
        self.assertNotIn('DONE', waited.stdout)

    def test_close_moves_the_uncommitted_default_result_so_the_finished_worktree_goes(self):
        args = ('--model', 'm', '--effort', 'high')
        self.assertEqual(self.spawn('w26', str(self.brief), *args, '--worktree').returncode, 0)
        tree = self.repo / '.claude/worktrees/w26'
        (tree / 'feature.txt').write_bytes(b'work\n')
        report = 'Kind: completed\nTask: t\nAttempt: 1\nRemaining: none\nChanged: feature.txt\n'
        (tree / 'RESULT-w26.md').write_text(report)
        # The lead commits exactly the files the result lists, then merges.
        git = lambda *a: subprocess.run(['git', *a], cwd=self.repo, check=True, capture_output=True)
        git('-C', str(tree), 'add', 'feature.txt')
        git('-C', str(tree), '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'feature')
        git('merge', '-q', '--ff-only', 'worktree-w26')
        closed = self.close('w26')
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertFalse(tree.exists(), 'the result sidecar kept a finished, merged worktree')
        self.assertEqual((self.repo / '.myagentkit/workers/w26.result.md').read_text(), report)
        self.assertFalse((self.repo / '.myagentkit/workers/w26.session').exists())

    def test_close_refuses_while_a_decision_waits_for_its_answer(self):
        args = ('--model', 'm', '--effort', 'high')
        custom = self.repo / 'custom.md'
        for name, extra, question in (('w27', (), self.repo / 'QUESTION-w27.md'),
                                      ('w28', ('--result', str(custom)), Path(str(custom) + '.question.md'))):
            with self.subTest(name=name):
                started = self.spawn(name, str(self.brief), *args, *extra)
                self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
                question.write_text('Choose A or B.\n<!-- codex-worker: ready -->')
                closed = self.close(name)
                self.assertEqual(closed.returncode, 1, closed.stdout + closed.stderr)
                self.assertIn('a decision waits for its answer', closed.stdout)
                self.assertTrue((self.repo / ('.myagentkit/workers/%s.session' % name)).exists(),
                                'the close stranded an unanswered decision without its session id')
                resumed = self.spawn(name, str(self.brief), *args, *extra, '--resume')
                self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)

    def test_failed_resume_launch_preserves_the_unanswered_decision(self):
        if WINDOWS:
            # Native helpers keep this launch-failure test independent of MSYS mkdir's
            # sandbox-denied ancestor probes and the inaccessible WindowsApps aliases.
            python = shq(sys.executable.replace('\\', '/'))
            for name in ('python', 'python3'):
                (self.bin / name).write_text('#!/bin/sh\nexec ' + python + ' "$@"\n', newline='\n')
            mkdir = ('import pathlib,sys; a=sys.argv[1:]; '
                     '[pathlib.Path(p).mkdir(parents="-p" in a,exist_ok="-p" in a) '
                     'for p in a if p not in ("-p","--")]')
            (self.bin / 'mkdir').write_text('#!/bin/sh\nexec ' + python + ' -c ' + shq(mkdir) + ' "$@"\n', newline='\n')
        for posix in (False, True):
            with self.subTest(posix=posix):
                name = 'failed-posix' if posix else 'failed-tab'
                record = self.repo / ('.myagentkit/workers/%s.session' % name)
                record.parent.mkdir(parents=True, exist_ok=True)
                record.write_text('saved-session\n')
                question = self.repo / ('QUESTION-%s.md' % name)
                before = b'Choose A or B.\n<!-- codex-worker: ready -->'
                question.write_bytes(before)
                launcher = self.bin / ('tmux' if posix else 'wt-tab')
                launcher.write_text('#!/bin/sh\nexit 1\n', newline='\n')
                result = self.spawn(name, str(self.brief), '--model', 'm', '--effort', 'high',
                                    '--resume', tmux=posix)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('could not', result.stderr)
                self.assertEqual(self.runs(), [])
                self.assertTrue(question.exists(), 'a failed launch consumed its unanswered decision')
                self.assertEqual(question.read_bytes(), before)
                self.assertEqual(record.read_text().strip(), 'saved-session')
                closed = self.close(name)
                self.assertEqual(closed.returncode, 1, closed.stdout + closed.stderr)
                self.assertIn('a decision waits for its answer', closed.stdout)
                self.assertTrue(record.exists(), 'a failed resume lost its closure evidence')

    def test_the_printed_resume_takes_over_the_reservation_of_an_unrecorded_launch(self):
        args = ('--model', 'm', '--effort', 'high')
        lost = self.spawn('u1', str(self.brief), *args, CODEX_SILENT='1')
        self.assertEqual(lost.returncode, 1, lost.stdout + lost.stderr)
        lock = self.repo / '.myagentkit/workers/spawn.lock'
        self.assertTrue((lock / 'u1').exists(), 'the kept reservation must name its launch')
        self.assertIn('rm -r -- ', lost.stderr)
        # Every other spawn in the checkout is refused with the recovery, a resume of another name too.
        for other in (('u2', str(self.brief), *args), ('u2', str(self.brief), *args, '--resume', 'x')):
            refused = self.spawn(*other)
            self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
            self.assertIn('an unrecorded launch at', refused.stderr)
            self.assertIn('--resume SESSION_ID, which records it and takes the reservation over', refused.stderr)
        line = next(line for line in lost.stderr.splitlines() if ': scripts/spawn_codex.sh u1 ANSWER_FILE ' in line)
        command = line.split(': scripts/spawn_codex.sh ', 1)[1]
        logger = self.bin / 'argv.py'
        logger.write_text('import json,sys; print(json.dumps(sys.argv[1:]))\n', newline='\n')
        printed = subprocess.run(['sh', '-c', shq(sys.executable.replace('\\', '/')) + ' '
                                  + shq(str(logger).replace('\\', '/')) + ' ' + command],
                                 cwd=self.repo, capture_output=True, text=True, timeout=10 * SCALE)
        self.assertEqual(printed.returncode, 0, printed.stderr)
        answer = self.tmp / 'answer.md'
        answer.write_text('Take option B.\n')
        argv = [{'ANSWER_FILE': str(answer), 'SESSION_ID': 'sess-found'}.get(a, a) for a in json.loads(printed.stdout)]
        # While the launch still runs, the take-over is refused and the reservation stays with it.
        (self.state / 'ps').write_text('41 codex.exe -C %s "Read ..."\r\n' % self.win(self.repo))
        refused = self.spawn(*argv)
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        self.assertIn('already runs in', refused.stderr)
        self.assertTrue((lock / 'u1').exists(), 'a refused take-over dropped the reservation')
        (self.state / 'ps').write_text('')
        resumed = self.spawn(*argv)
        self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
        self.assertEqual(self.runs()[-1]['argv'][:2], ['resume', 'sess-found'])
        self.assertEqual((self.repo / '.myagentkit/workers/u1.session').read_text().strip(), 'sess-found')
        self.assertFalse(lock.exists(), 'the recorded launch kept the reservation')
        started = self.spawn('u2', str(self.brief), *args)
        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)

    def test_a_kept_worktree_keeps_its_result_and_an_earlier_report_is_never_replaced(self):
        args = ('--model', 'm', '--effort', 'high')
        self.assertEqual(self.spawn('w29', str(self.brief), *args, '--worktree').returncode, 0)
        tree = self.repo / '.claude/worktrees/w29'
        earlier = self.repo / '.myagentkit/workers/w29.result.md'
        earlier.write_text("an earlier run's report\n")
        (tree / 'feature.txt').write_bytes(b'work\n')
        report = 'Kind: completed\nTask: t\nAttempt: 1\nRemaining: none\nChanged: feature.txt\n'
        (tree / 'RESULT-w29.md').write_text(report)
        # A premature close, before the lead committed the listed files: the report stays with the work.
        closed = self.close('w29')
        self.assertEqual(closed.returncode, 1, closed.stdout + closed.stderr)
        self.assertIn('worktree kept', closed.stdout)
        self.assertEqual((tree / 'RESULT-w29.md').read_text(), report)
        self.assertEqual(earlier.read_text(), "an earlier run's report\n")
        git = lambda *a: subprocess.run(['git', *a], cwd=self.repo, check=True, capture_output=True)
        git('-C', str(tree), 'add', 'feature.txt')
        git('-C', str(tree), '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'feature')
        git('merge', '-q', '--ff-only', 'worktree-w29')
        closed = self.close('w29')
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertFalse(tree.exists())
        self.assertEqual(earlier.read_text(), "an earlier run's report\n")
        self.assertEqual((self.repo / '.myagentkit/workers/w29.result-2.md').read_text(), report)

    def test_both_printed_reservation_recoveries_quote_a_single_deletion_operand(self):
        spaced = self.repo.with_name('repo space')
        self.repo.rename(spaced)
        self.repo = spaced
        args = ('--model', 'm', '--effort', 'high')
        lost = self.spawn('quoted', str(self.brief), *args, CODEX_SILENT='1')
        refused = self.spawn('other', str(self.brief), *args)
        lock = self.repo / '.myagentkit/workers/spawn.lock'
        logger = self.bin / 'argv.py'
        logger.write_text('import json,sys; print(json.dumps(sys.argv[1:]))\n', newline='\n')
        for output in (lost, refused):
            with self.subTest(stderr=output.stderr):
                self.assertEqual(output.returncode, 1, output.stdout + output.stderr)
                operands = next(line.partition('release it: rm -r -- ')[2]
                                for line in output.stderr.splitlines() if 'release it: rm -r -- ' in line)
                # Log argv instead of invoking the destructive recovery command.
                printed = subprocess.run(['sh', '-c', shq(sys.executable.replace('\\', '/')) + ' '
                                          + shq(str(logger).replace('\\', '/')) + ' ' + operands],
                                         cwd=self.repo, capture_output=True, text=True, timeout=10 * SCALE)
                self.assertEqual(printed.returncode, 0, printed.stderr)
                self.assertEqual(json.loads(printed.stdout), [self.win(lock, '-m')])
                self.assertTrue(lock.exists())

    def test_close_atomically_claims_the_archive_when_a_report_arrives_after_the_name_check(self):
        report = self.repo / 'RESULT-race.md'
        report.write_text('the report being closed\n')
        saved = self.repo / '.myagentkit/workers/race.result.md'
        hook = self.bin / 'mkdir-hook.py'
        hook.write_text('''import pathlib,sys
args = sys.argv[1:]
for arg in args:
    if arg not in ('-p', '--'):
        pathlib.Path(arg).mkdir(parents='-p' in args, exist_ok='-p' in args)
pathlib.Path(%r).write_text('a concurrently published report\\n')
''' % str(saved), newline='\n')
        (self.bin / 'mkdir').write_text('#!/bin/sh\nexec ' + shq(sys.executable.replace('\\', '/'))
                                      + ' ' + shq(str(hook).replace('\\', '/')) + ' "$@"\n', newline='\n')
        (self.bin / 'mkdir').chmod(0o755)
        closed = self.close('race')
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertEqual(saved.read_text(), 'a concurrently published report\n')
        self.assertEqual(saved.with_name('race.result-2.md').read_text(), 'the report being closed\n')
        self.assertFalse(report.exists())

    def test_close_restores_both_reports_when_the_kept_worktree_publishes_a_new_result(self):
        tree = self.repo / '.claude/worktrees/restore'
        subprocess.run(['git', 'worktree', 'add', '-q', str(tree), '-b', 'worktree-restore'],
                       cwd=self.repo, check=True, capture_output=True)
        report = tree / 'RESULT-restore.md'
        report.write_text('the saved report\n')
        # The audit keeps the worktree and schedules a publication immediately before restore.
        kit = self.tmp / 'close-scripts'
        kit.mkdir()
        script = kit / 'close_worker.sh'
        script.write_bytes(SCRIPT.with_name('close_worker.sh').read_bytes())
        publish = 'from pathlib import Path; Path(%r).write_text("a newer report\\n")' % str(report)
        (kit / 'clean_worktrees.sh').write_text('#!/bin/sh\n' + shq(sys.executable.replace('\\', '/'))
                                               + ' -c ' + shq(publish)
                                               + "\necho 'clean_worktrees: kept 1, removed 0'\nexit 1\n", newline='\n')
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}',
                   SPAWN_STATE=str(self.state), KIT_PS=str(self.bin / 'ps-stub'))
        closed = subprocess.run(['sh', str(script), 'restore'], cwd=self.repo, env=env,
                                capture_output=True, text=True, timeout=45 * SCALE)
        self.assertEqual(closed.returncode, 1, closed.stdout + closed.stderr)
        self.assertEqual(report.read_text(), 'a newer report\n')
        restored = list(tree.glob('RESULT-restore-restored*.md'))
        self.assertEqual(len(restored), 1, closed.stdout + closed.stderr)
        self.assertEqual(restored[0].read_text(), 'the saved report\n')
        self.assertIn('newer RESULT-restore.md kept', closed.stdout)
        self.assertIn(restored[0].name, closed.stdout)

    def test_a_move_that_took_the_report_and_failed_keeps_the_worktree_without_the_audit(self):
        tree = self.repo / '.claude/worktrees/taken'
        subprocess.run(['git', 'worktree', 'add', '-q', str(tree), '-b', 'worktree-taken'],
                       cwd=self.repo, check=True, capture_output=True)
        (tree / 'RESULT-taken.md').write_text('the report\n')
        kit = self.tmp / 'close-scripts'
        kit.mkdir()
        # The helper dies with the report in its private folder, before any archive holds it.
        killed = ('source, target = sys.argv[1:]\n'
                  'folder = os.path.join(os.path.dirname(target), ".report-move-killed")\n'
                  'os.mkdir(folder)\nos.rename(source, os.path.join(folder, "report"))\nos._exit(137)\n')
        script = SCRIPT.with_name('close_worker.sh').read_text(encoding='utf-8')
        self.assertIn('source, target = sys.argv[1:]\n', script)
        (kit / 'close_worker.sh').write_text(script.replace('source, target = sys.argv[1:]\n', killed, 1),
                                            encoding='utf-8', newline='\n')
        audited = self.tmp / 'audited'
        (kit / 'clean_worktrees.sh').write_text('#!/bin/sh\n: > ' + shq(audited.as_posix())
                                               + "\necho 'clean_worktrees: removed 1, kept 0'\n", newline='\n')
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}{os.environ["PATH"]}',
                   SPAWN_STATE=str(self.state), KIT_PS=str(self.bin / 'ps-stub'))
        closed = subprocess.run(['sh', str(kit / 'close_worker.sh'), 'taken'], cwd=self.repo, env=env,
                                capture_output=True, text=True, timeout=45 * SCALE)
        self.assertEqual(closed.returncode, 1, closed.stdout + closed.stderr)
        self.assertIn('could not move its result RESULT-taken.md', closed.stdout)
        self.assertIn('the audit did not run, so a worktree stays', closed.stdout)
        self.assertIn('.report-move-* folder in ', closed.stdout)
        self.assertFalse(audited.exists(), 'the audit ran while the report sat only in a private folder')
        self.assertTrue(tree.exists())
        self.assertEqual((self.repo / '.myagentkit/workers/.report-move-killed/report').read_text(), 'the report\n')

    def test_a_resumed_worker_that_published_and_then_failed_can_be_closed(self):
        # The reproduced sequence: the resumed session publishes progress, then its CLI exits 1.
        for name, after in (('ran-on', 'time.sleep(.5); '), ('ended-at-once', '')):
            with self.subTest(name=name):
                question, result = self.repo / ('QUESTION-%s.md' % name), self.repo / ('RESULT-%s.md' % name)
                question.write_text('Choose A or B.\n<!-- codex-worker: ready -->')
                code = ('from pathlib import Path; import os,time; p=Path(%r); '
                        'p.write_text("Kind: progress\\nTask: t\\nAttempt: 2\\nRemaining: x\\n'
                        '<!-- codex-worker: ready -->"); os.replace(p,%r); %sraise SystemExit(1)') % (
                            str(result) + '.tmp', str(result), after)
                worker = subprocess.run([sys.executable, str(SCRIPT.with_name('codex_worker.py')), str(question),
                                         str(result), '--', sys.executable, '-c', code], capture_output=True,
                                        text=True, timeout=30 * SCALE, env=dict(os.environ, KIT_WORKER_RESUME='1',
                                                                        KIT_WORKER_GRACE='0'))
                self.assertEqual(worker.returncode, 1, worker.stderr)
                self.assertFalse(question.exists(), 'the answered decision outlived the session that took it')
                closed = self.close(name)
                self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
                self.assertNotIn('a decision waits for its answer', closed.stdout)

    def test_the_suite_never_writes_the_exit_record_of_the_worker_it_runs_in(self):
        # Inside a Codex worker the suite inherits KIT_WORKER_EXIT: a fixture supervisor wrote
        # it, and the lead's waiter reported EXITED while that worker still ran.
        record = self.tmp / 'caller.exit'
        run = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()),
                              'SpawnCodexTests.test_a_resumed_worker_that_published_and_then_failed_can_be_closed'],
                             capture_output=True, text=True, timeout=120 * SCALE,
                             env=dict(os.environ, KIT_WORKER_EXIT=str(record)))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(record.exists(), "a fixture wrote the calling worker's exit record")

    def test_close_numbers_a_new_report_above_every_earlier_one(self):
        workers = self.repo / '.myagentkit/workers'
        workers.mkdir(parents=True)
        # The first report was deleted; the newest earlier one is -2.
        (workers / 'gap.result-2.md').write_text('the newest earlier report\n')
        (self.repo / 'RESULT-gap.md').write_text('the report being closed\n')
        closed = self.close('gap')
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertFalse((workers / 'gap.result.md').exists(), 'a newer report took a lower number')
        self.assertEqual((workers / 'gap.result-2.md').read_text(), 'the newest earlier report\n')
        self.assertEqual((workers / 'gap.result-3.md').read_text(), 'the report being closed\n')


class TmuxStubTests(unittest.TestCase):
    def test_tmux_stub_reparses_the_final_command_in_the_start_directory(self):
        # A checkout with spaces must not force a skip when system scratch is safe.
        codex_root, worker_root = ROOT, test_spawn_worker.ROOT
        with test_spawn_worker.safe_tmux_scratch() as scratch, \
                patch('tempfile.tempdir', scratch), \
                patch(__name__ + '.ROOT', codex_root / 'checkout space'), \
                patch.object(test_spawn_worker, 'ROOT', worker_root / 'checkout space'), \
                test_spawn_worker.safe_tmux_scratch() as folder:
            state = Path(folder)
            for segment in ('literal$REVIEW_SEGMENT', 'literal$($REVIEW_PAYLOAD)',
                            'literal`$REVIEW_BACKQUOTE`'):
                with self.subTest(segment=segment):
                    script = state / segment / 'run.sh'
                    script.parent.mkdir()
                    script.write_text('exit 0\n', newline='\n')
                    command = 'sh ' + test_spawn_worker.SpawnWorkerTests.physical(script)
                    result = subprocess.run([sys.executable, '-c', TMUX, 'new-session', '-d',
                                             '-s', 'stub', '-c', str(state), '-x', '200', '-y', '50', command],
                                            env=dict(os.environ, SPAWN_STATE=str(state), REVIEW_SEGMENT='expanded',
                                                     REVIEW_PAYLOAD='touch INJECTED', REVIEW_BACKQUOTE='touch BACKQUOTED'),
                                            capture_output=True, text=True, timeout=10 * SCALE)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('literal', result.stderr)
                    self.assertNotIn(segment, result.stderr, 'the stub bypassed shell expansion')
            self.assertTrue((state / 'INJECTED').exists(), 'the stub did not run command substitution')
            self.assertTrue((state / 'BACKQUOTED').exists(), 'the stub did not run backquotes')


if __name__ == '__main__':
    unittest.main()
