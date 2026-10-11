"""spawn_codex.sh leaves sandboxed work uncommitted for the lead, records its session id,
and answers a stopped worker in that same session.

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
INSTRUCTION = ("Read %s and follow it. Write your result to %s. Leave all work uncommitted and ready for the lead; "
               "list the exact changed and added files in the result. The lead reviews the diff through the normal "
               "cross-review, then commits with the usual commit gate. Publish a finished result atomically: write a "
               "temporary file beside it, end with <!-- codex-worker: ready -->, then rename it to the result path. "
               "If a decision is needed, finish independent work "
               "and stop all jobs first, then write Kind: blocked and QUESTIONS in the result and publish the question "
               "atomically to %s using the same temporary-file, end-marker and rename protocol. "
               "End your turn immediately after publishing; the wrapper allows 10 seconds to flush before closing "
               "this worker. The lead answers by resuming this same session.")

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
    sys.exit(subprocess.run(['sh', '-c', args[-1]]).returncode)
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
                   CODEX_HOME=str(self.home), KIT_WT=str(self.bin / 'wt-tab'), KIT_PS=str(self.bin / 'ps-stub'), KIT_SESSION_WAIT='2', **extra)
        if tmux:
            (self.bin / 'uname').write_text('#!/bin/sh\necho Linux\n')
            (self.bin / 'uname').chmod(0o755)
        return subprocess.run(['sh', str(SCRIPT), *args], cwd=self.repo, env=env,
                              capture_output=True, text=True, timeout=60)

    def runs(self):
        path = self.state / 'codex.log'
        return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []

    def test_a_worker_starts_sandboxed_without_git_roots_and_its_session_recorded(self):
        result = self.spawn('w1', str(self.brief), '--model', 'gpt-x', '--effort', 'high', '--worktree')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tree = self.repo / '.claude/worktrees/w1'
        (run,) = self.runs()
        # Git metadata remains read-only even with --add-dir (issue #43); the lead commits.
        self.assertEqual(run['argv'], [INSTRUCTION % tuple(shq(self.win(p, '-m')) for p in (self.brief, tree / 'RESULT-w1.md', tree / 'QUESTION-w1.md')), '-m', 'gpt-x', '-c', 'model_reasoning_effort=high', '-s', 'workspace-write',
                                       '-a', 'never', '--no-daemon', '-C', self.win(tree)])
        self.assertEqual(Path(run['cwd']).resolve(), tree.resolve())
        branch = subprocess.run(['git', '-C', str(tree), 'branch', '--show-current'], capture_output=True, text=True)
        self.assertEqual(branch.stdout.strip(), 'worktree-w1')
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
        self.assertEqual(run['argv'][0], INSTRUCTION % tuple(shq(str(p)) for p in (self.brief, self.repo / 'RESULT-w6.md', self.repo / 'QUESTION-w6.md')))
        self.assertEqual(run['argv'][-2:], ['-C', str(self.repo)])
        self.assertEqual((self.repo / '.myagentkit/workers/w6.session').read_text().strip(), 'sess-0')
        # A tmux session of that name still running is never resumed beside.
        (self.state / 'live').write_text('')
        result = self.spawn('w6', str(self.brief), '--model', 'm', '--effort', 'high', '--resume', tmux=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("tmux session 'w6' still runs", result.stderr)

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
        self.assertIn('--wait', result.stdout)

    def test_tab_preserves_quick_exit_error(self):
        (self.bin / 'codex').write_text('#!/bin/sh\necho bad-model >&2\nexit 1\n')
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
                                cwd=self.repo, env=env, capture_output=True, text=True, timeout=45)
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertFalse(tree.exists())
        self.assertFalse(record.exists())
        self.assertEqual(self.spawn('w16', str(self.brief), *args).returncode, 0)


if __name__ == '__main__':
    unittest.main()
