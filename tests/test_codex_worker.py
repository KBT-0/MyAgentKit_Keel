"""A decision sidecar ends the interactive worker without losing its session."""
from pathlib import Path
import hashlib
import importlib.util
import io
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/scripts/codex_worker.py'
# Run inside a Codex worker, the suite inherits its supervisor's KIT_WORKER_* settings; a
# fixture supervisor must never write the caller's records. A case sets its own explicitly.
for _name in [n for n in os.environ if n.startswith('KIT_WORKER_')]:
    del os.environ[_name]
READY = '<!-- codex-worker: ready -->'


def module():
    spec = importlib.util.spec_from_file_location('codex_worker', SCRIPT)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class CodexWorkerTests(unittest.TestCase):
    def test_cached_successes_reset_isolated_windows_refusals(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / 'result.md'
            result.write_text('Kind: completed\nTask: w\nAttempt: 1\nRemaining: none\n' + READY)
            expected = worker.result_kind(result)
            self.assertEqual(expected[0], 'DONE')
            stat = Path.stat
            def refused(path, *args, **kwargs):
                if path == result:
                    raise PermissionError('sharing violation')
                return stat(path, *args, **kwargs)
            with mock.patch.object(worker.os, 'name', 'nt'), \
                    mock.patch.object(Path, 'open', side_effect=AssertionError('cached poll reopened result')):
                for _ in range(worker.REFUSALS + 1):
                    with mock.patch.object(Path, 'stat', refused):
                        self.assertEqual(worker.result_kind(result), ('', None))
                    self.assertEqual(worker.result_kind(result), expected)
                    self.assertNotIn(result, worker.REFUSED, 'successful cached poll retained a refusal')

    def run_worker(self, question, code, result=None):
        args = [str(question)] + ([str(result)] if result else [])
        return subprocess.run([sys.executable, str(SCRIPT), *args, '--', sys.executable, '-c', code],
                              capture_output=True, text=True, timeout=15,
                              env=dict(os.environ, KIT_WORKER_GRACE='0.5'))

    def test_a_decision_closes_descendants_as_well_as_the_cli_shim(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, started, escaped = (Path(tmp) / name for name in ('QUESTION-w.md', 'started', 'escaped'))
            grandchild = ('from pathlib import Path; import time; Path(%r).write_text("ready"); '
                          'time.sleep(2); Path(%r).write_text("orphan survived")') % (str(started), str(escaped))
            parent = ('from pathlib import Path; import subprocess,sys,time; '
                      'subprocess.Popen([sys.executable,"-c",%r]); '
                      '\nwhile not Path(%r).exists(): time.sleep(.05)\n'
                      'Path(%r).write_text("Choose A or B.\\n<!-- codex-worker: ready -->"); time.sleep(30)') % (grandchild, str(started), str(question))
            result = self.run_worker(question, parent)
            self.assertEqual(result.returncode, 0, result.stderr)
            time.sleep(2.2)
            self.assertFalse(escaped.exists(), 'the CLI child outlived its stopped worker')

    def test_a_completed_result_waits_for_a_git_operation_in_the_worker_checkout(self):
        # A Claude worker commits after it wrote its result; ending it mid-commit, or mid-gate
        # (check.sh holds check.lock), orphans that run, as close_worker.sh refuses to (fix56).
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['git', 'init', '-q', tmp], check=True)
            lock = Path(tmp) / '.git/index.lock'
            lock.write_text('')
            result, unlocked = Path(tmp) / 'RESULT-w.md', Path(tmp) / 'unlocked'
            code = ('from pathlib import Path; import time; Path(%r).write_text(%r); time.sleep(1.5); '
                    'Path(%r).unlink(); Path(%r).write_text("x"); time.sleep(30)') % (
                str(result), 'Kind: completed\nTask: w\nAttempt: 1\nRemaining: none\n' + READY, str(lock), str(unlocked))
            started = time.monotonic()
            done = subprocess.run([sys.executable, str(SCRIPT), str(Path(tmp) / 'QUESTION-w.md'), str(result), '--',
                                   sys.executable, '-c', code], capture_output=True, text=True, timeout=20, cwd=tmp,
                                  env=dict(os.environ, KIT_WORKER_GRACE='0.2'))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(unlocked.exists(), 'the worker was ended while a git operation held its index.lock')
            self.assertLess(time.monotonic() - started, 15)

    def test_question_stops_the_process_and_preserves_the_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            question = Path(tmp) / 'QUESTION-w.md'
            code = 'from pathlib import Path; import time; Path(%r).write_text("Choose A or B.\\n<!-- codex-worker: ready -->"); time.sleep(30)' % str(question)
            started = time.monotonic()
            result = self.run_worker(question, code)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(time.monotonic() - started, 10)
            self.assertEqual(question.read_text(), 'Choose A or B.\n' + READY)

    def test_partial_question_is_not_a_signal_and_turn_gets_grace(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, flushed = (Path(tmp) / name for name in ('q.md', 'flushed'))
            code = ('from pathlib import Path; import time,os; q=Path(%r); '
                    'q.write_text("partial"); time.sleep(.3); '
                    'p=q.with_suffix(".tmp"); p.write_text("full question\\n%s"); os.replace(p,q); '
                    'time.sleep(.25); Path(%r).write_text("turn flushed"); time.sleep(30)') % (
                        str(question), READY, str(flushed))
            result = self.run_worker(question, code)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(question.read_text(), 'full question\n' + READY)
            self.assertTrue(flushed.exists(), 'the final tool output must have time to flush')

    def test_existing_question_is_refused_without_starting_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, started = Path(tmp) / 'q.md', Path(tmp) / 'started'
            question.write_text('old question')
            result = self.run_worker(question, 'from pathlib import Path; Path(%r).touch()' % str(started))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('question file already exists', result.stderr)
            self.assertFalse(started.exists())

    def test_uncommitted_completed_result_closes_worker_and_background_wait_reports_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, result = Path(tmp) / 'q.md', Path(tmp) / 'result.md'
            waiter = subprocess.Popen([sys.executable, str(SCRIPT), '--wait', str(result)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                result.write_text('Kind: completed\nTask: w\nAttempt: 1\nRemaining: none\n')
                time.sleep(.25)
                self.assertIsNone(waiter.poll(), 'an incomplete result is not a handoff')
                code = ('from pathlib import Path; import time; p=Path(%r); '
                        'p.write_text(p.read_text()+"\\n%s\\n"); time.sleep(30)') % (str(result), READY)
                worker = self.run_worker(question, code, result)
                self.assertEqual(worker.returncode, 0, worker.stderr)
                self.assertIn('DONE', worker.stdout)
                out, err = waiter.communicate(timeout=5)
                self.assertEqual(waiter.returncode, 0, err)
                self.assertIn('DONE', out)
            finally:
                if waiter.poll() is None:
                    waiter.kill()
                    waiter.communicate()

    def test_tree_escalation_includes_descendants_after_leader_exits(self):
        worker = module()
        child = mock.Mock()
        child.poll.return_value = 0
        tree = mock.Mock()
        worker.stop(child, tree)
        self.assertIn(mock.call(True), tree.call_args_list)

    def test_ready_blocked_result_before_question_unblocks_the_leads_waiter(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, result = Path(tmp) / 'q.md', Path(tmp) / 'result.md'
            waiter = subprocess.Popen([sys.executable, str(SCRIPT), '--wait', str(result)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                code = ('from pathlib import Path; import os,time; p=Path(%r); '
                        'p.write_text("Kind: blocked\\nTask: t\\nAttempt: 1\\nRemaining: decision\\n'
                        'QUESTIONS: A or B?\\n%s"); os.replace(p,%r); '
                        'p=Path(%r); p.write_text("A or B?\\n%s"); os.replace(p,%r); time.sleep(30)') % (
                            str(result) + '.tmp', READY, str(result), str(question) + '.tmp', READY, str(question))
                worker = self.run_worker(question, code, result)
                self.assertEqual(worker.returncode, 0, worker.stderr)
                self.assertIn('decision recorded', worker.stdout)
                out, err = waiter.communicate(timeout=5)
                self.assertEqual(waiter.returncode, 0, err)
                self.assertIn('BLOCKED', out)
                self.assertIn(READY, result.read_text())
            finally:
                if waiter.poll() is None:
                    waiter.kill()
                    waiter.communicate()

    def test_windows_child_is_suspended_until_job_assignment(self):
        worker = module()
        events = []
        child = mock.Mock()
        def popen(command, **kwargs):
            self.assertTrue(kwargs.get('creationflags', 0) & 4, 'child must start suspended')
            events.append('spawn')
            return child
        with mock.patch.object(worker.subprocess, 'Popen', side_effect=popen), \
                mock.patch.object(worker, 'windows_job', side_effect=lambda c: events.append('assign') or mock.Mock()), \
                mock.patch.object(worker, 'resume_windows', create=True, side_effect=lambda c: events.append('resume')):
            worker.windows_child(['fake'])
        self.assertEqual(events, ['spawn', 'assign', 'resume'])

    def test_posix_escalation_signals_the_group_with_sigkill(self):
        worker = module()
        child = mock.Mock(pid=123)
        child.poll.return_value = 0
        with mock.patch.object(worker.os, 'killpg', create=True) as kill, \
                mock.patch.object(worker.signal, 'SIGKILL', 9, create=True):
            worker.stop(child, lambda force=False: worker.posix_tree(child.pid, force))
        self.assertEqual(kill.call_args_list, [mock.call(123, signal.SIGTERM), mock.call(123, 9)])

    def test_old_completed_result_cannot_stop_a_reused_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, result, flushed = (Path(tmp) / n for n in ('q.md', 'result.md', 'flushed'))
            result.write_text('Kind: completed\nTask: old\nAttempt: 1\nRemaining: none\n' + READY)
            since = str(time.time() + 1)
            waiter = subprocess.Popen([sys.executable, str(SCRIPT), '--wait', str(result), '--since', since],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                # A fresh result is published by a rename, as the protocol says.
                code = ('from pathlib import Path; import os,time; time.sleep(1.25); '
                        'Path(%r).write_text("new turn"); Path(%r).write_text('
                        '"Kind: completed\\nTask: new\\nAttempt: 1\\nRemaining: none\\n%s"); '
                        'os.replace(%r, %r); time.sleep(30)') % (
                            str(flushed), str(result) + '.tmp', READY, str(result) + '.tmp', str(result))
                worker = subprocess.run([sys.executable, str(SCRIPT), str(question), str(result), '--',
                                         sys.executable, '-c', code], capture_output=True, text=True, timeout=15,
                                        env=dict(os.environ, KIT_WORKER_GRACE='0.5', KIT_WORKER_STARTED=since))
                self.assertEqual(worker.returncode, 0, worker.stderr)
                self.assertTrue(flushed.exists(), 'a previous task result must not close the new turn')
                out, err = waiter.communicate(timeout=5)
                self.assertEqual(waiter.returncode, 0, err)
                self.assertIn('DONE', out)
            finally:
                if waiter.poll() is None:
                    waiter.kill()
                    waiter.communicate()

    def test_progress_result_leaves_the_worker_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, result, working = (Path(tmp) / n for n in ('q.md', 'result.md', 'working'))
            code = ('from pathlib import Path; import time; Path(%r).write_text('
                    '"Kind: progress\\nTask: t\\nAttempt: 1\\nRemaining: two steps\\n%s"); '
                    'time.sleep(1.5); Path(%r).write_text("still working")') % (str(result), READY, str(working))
            worker = self.run_worker(question, code, result)
            self.assertEqual(worker.returncode, 0, worker.stderr)
            self.assertTrue(working.exists(), 'a PROGRESS result closed a worker that was still working')
            self.assertNotIn('result ready for the lead', worker.stdout)

    def test_resumed_in_place_edit_of_an_old_result_neither_closes_nor_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, result, flushed, record = (Path(tmp) / n for n in ('q.md', 'result.md', 'flushed', 'w.exit'))
            result.write_text('Kind: blocked\nTask: t\nAttempt: 1\nRemaining: a decision\n' + READY)
            os.utime(result, (time.time() - 60, time.time() - 60))
            since = str(time.time())
            waiter = subprocess.Popen([sys.executable, str(SCRIPT), '--wait', str(result), '--since', since,
                                       '--exit', str(record)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                # The resumed session edits its old result in place: not a new publication.
                code = ('from pathlib import Path; import time; p=Path(%r); '
                        'p.write_text(p.read_text().replace("Kind: blocked", "Kind: completed")); '
                        'time.sleep(1.5); Path(%r).write_text("flushed")') % (str(result), str(flushed))
                worker = subprocess.run([sys.executable, str(SCRIPT), str(question), str(result), '--',
                                         sys.executable, '-c', code], capture_output=True, text=True, timeout=15,
                                        env=dict(os.environ, KIT_WORKER_GRACE='0.5', KIT_WORKER_STARTED=since,
                                                 KIT_WORKER_EXIT=str(record)))
                self.assertEqual(worker.returncode, 0, worker.stderr)
                self.assertTrue(flushed.exists(), 'an in-place edit of an old result closed the resumed worker')
                out, err = waiter.communicate(timeout=5)
                self.assertEqual(waiter.returncode, 0, err)
                self.assertIn('EXITED (exit 0', out)
                self.assertNotIn('DONE', out)
            finally:
                if waiter.poll() is None:
                    waiter.kill()
                    waiter.communicate()

    def test_wait_reports_a_worker_that_ended_without_publishing(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, result, record = Path(tmp) / 'q.md', Path(tmp) / 'result.md', Path(tmp) / 'workers/w.exit'
            code = 'from pathlib import Path; Path(%r).write_text("Kind: completed\\nTask: t\\n"); raise SystemExit(3)' % str(result)
            worker = subprocess.run([sys.executable, str(SCRIPT), str(question), str(result), '--',
                                     sys.executable, '-c', code], capture_output=True, text=True, timeout=15,
                                    env=dict(os.environ, KIT_WORKER_EXIT=str(record)))
            self.assertEqual(worker.returncode, 3, worker.stderr)
            waiter = subprocess.run([sys.executable, str(SCRIPT), '--wait', str(result), '--since', '0',
                                     '--exit', str(record)], capture_output=True, text=True, timeout=10)
            self.assertEqual(waiter.returncode, 0, waiter.stderr)
            self.assertIn('EXITED (exit 3', waiter.stdout)

    def test_wait_reports_a_settled_file_that_is_not_a_result(self):
        # v0.11: a free-form report (no header, no ready marker) kept the wait silent forever.
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'report.md'
            report.write_text('# Batch report\n\nAll done.\n', encoding='utf-8')
            settled = time.time() - 120
            os.utime(report, (settled, settled))
            waiter = subprocess.run([sys.executable, str(SCRIPT), '--wait', str(report), '--since', str(settled - 1)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(waiter.returncode, 0, waiter.stderr)
            self.assertIn('NOT A RESULT: ' + str(report), waiter.stdout)

    def test_a_draft_renamed_over_a_settled_result_while_checked_is_no_verdict(self):
        # Codex r1 (fix56): stat() then read_text() paired the settled file's age with the bytes
        # of a fresh draft renamed over it in between, and called the draft NOT A RESULT.
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result, draft = Path(tmp) / 'result.md', Path(tmp) / 'draft.md'
            text = 'Kind: progress\nTask: w\nAttempt: 1\nRemaining: more\n' + READY
            result.write_text(text, encoding='utf-8')
            settled = time.time() - 120
            os.utime(result, (settled, settled))
            stale = 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()
            stat, raced = Path.stat, []
            def racing(path, *args, **kwargs):
                info = stat(path, *args, **kwargs)
                if path == result and not raced:
                    raced.append(1)
                    draft.write_text('# half written', encoding='utf-8')
                    os.replace(draft, result)
                return info
            with mock.patch.object(Path, 'stat', racing):
                self.assertFalse(worker.not_a_result(result, settled - 1, stale))
            self.assertTrue(raced)
            self.assertFalse(worker.not_a_result(result, settled - 1, stale), 'a fresh draft is no verdict')

    def test_wait_stays_quiet_on_a_fresh_draft_and_on_the_stale_result(self):
        # A draft still being written, and the reported result a follow-up wait names by its
        # hash, are not alarms however long they sit.
        with tempfile.TemporaryDirectory() as tmp:
            draft, old = Path(tmp) / 'draft.md', Path(tmp) / 'old.md'
            draft.write_text('# half written', encoding='utf-8')
            text = 'Kind: progress\nTask: w\nAttempt: 1\nRemaining: more\n' + READY
            old.write_text(text, encoding='utf-8')
            settled = time.time() - 120
            os.utime(old, (settled, settled))
            stale = 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()
            for args in (['--wait', str(draft), '--since', '0'],
                         ['--wait', str(old), '--since', str(settled - 1), '--stale', stale]):
                with self.assertRaises(subprocess.TimeoutExpired):
                    subprocess.run([sys.executable, str(SCRIPT)] + args, capture_output=True, timeout=2)

    def test_wait_reports_a_unicode_result_path_on_a_legacy_stdout(self):
        # A Windows pipe is cp1252 unless UTF-8 mode is on; the lead must still see DONE.
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / 'report-Ş-😀.md'
            result.write_text('Kind: completed\nTask: w\nAttempt: 1\nRemaining: none\n' + READY, encoding='utf-8')
            env = {k: v for k, v in os.environ.items() if k not in ('PYTHONUTF8', 'PYTHONIOENCODING')}
            waiter = subprocess.run([sys.executable, str(SCRIPT), '--wait', str(result), '--since', '0'],
                                    capture_output=True, timeout=10, env=env)
            self.assertEqual(waiter.returncode, 0, waiter.stderr)
            self.assertIn('DONE: ' + str(result), waiter.stdout.decode('utf-8'))

    def test_wait_ends_on_a_decision_published_without_a_blocked_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, result, record = (Path(tmp) / n for n in ('q.md', 'result.md', 'w.exit'))
            since = str(time.time())
            # The model forgot the blocked result: only the question is published.
            code = ('from pathlib import Path; import os,time; p=Path(%r); p.write_text("A or B?\\n%s"); '
                    'os.replace(p,%r); time.sleep(30)') % (str(question) + '.tmp', READY, str(question))
            worker = subprocess.run([sys.executable, str(SCRIPT), str(question), str(result), '--',
                                     sys.executable, '-c', code], capture_output=True, text=True, timeout=15,
                                    env=dict(os.environ, KIT_WORKER_GRACE='0.5', KIT_WORKER_STARTED=since,
                                             KIT_WORKER_EXIT=str(record)))
            self.assertEqual(worker.returncode, 0, worker.stderr)
            self.assertIn('decision recorded', worker.stdout)
            waiter = subprocess.run([sys.executable, str(SCRIPT), '--wait', str(result), '--since', since,
                                     '--exit', str(record)], capture_output=True, text=True, timeout=10)
            self.assertEqual(waiter.returncode, 0, waiter.stderr)
            self.assertIn('EXITED (decision', waiter.stdout)

    def test_wait_ends_when_the_supervisor_is_killed_before_any_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, result, record, pid = (Path(tmp) / n for n in ('q.md', 'result.md', 'w.exit', 'pid'))
            since = str(time.time())
            code = 'import os,time; from pathlib import Path; Path(%r).write_text(str(os.getpid())); time.sleep(30)' % str(pid)
            # No pipes: on POSIX the killed supervisor's worker lives on, and would hold them open.
            supervisor = subprocess.Popen([sys.executable, str(SCRIPT), str(question), str(result), '--',
                                           sys.executable, '-c', code], stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL,
                                          env=dict(os.environ, KIT_WORKER_STARTED=since, KIT_WORKER_EXIT=str(record)))
            waiter = subprocess.Popen([sys.executable, str(SCRIPT), '--wait', str(result), '--since', since,
                                       '--exit', str(record)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 10
                while not pid.exists():
                    self.assertIsNone(supervisor.poll(), 'the supervisor ended before its worker started')
                    self.assertLess(time.monotonic(), deadline, 'the worker never started')
                    time.sleep(.05)
                time.sleep(.5)
                self.assertIsNone(waiter.poll(), 'a running worker was reported as ended')
                # A closed tab or a hard kill (taskkill /F, SIGKILL): no handler runs, no record is written.
                supervisor.kill()
                supervisor.wait()
                out, err = waiter.communicate(timeout=10)
                self.assertEqual(waiter.returncode, 0, err)
                self.assertIn('EXITED', out)
                self.assertFalse(record.exists())
            finally:
                for process in (supervisor, waiter):
                    if process.poll() is None:
                        process.kill()
                    process.communicate()
                if os.name != 'nt' and pid.exists():
                    module().posix_tree(int(pid.read_text()), True)

    def test_wait_ignores_an_exit_record_from_before_its_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, record = Path(tmp) / 'result.md', Path(tmp) / 'w.exit'
            # A resumed worker: the previous run's records stay, and spawn does not delete them.
            record.write_text('exit 0 at an earlier run\n')
            record.with_suffix('.live').write_text('4242\n')
            for old in (record, record.with_suffix('.live')):
                os.utime(old, (time.time() - 60, time.time() - 60))
            waiter = subprocess.Popen([sys.executable, str(SCRIPT), '--wait', str(result), '--since', str(time.time()),
                                       '--exit', str(record)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                time.sleep(.75)
                self.assertIsNone(waiter.poll(), "a previous run's exit record ended the wait of a resumed worker")
                fresh = result.with_suffix('.tmp')
                fresh.write_text('Kind: completed\nTask: t\nAttempt: 2\nRemaining: none\n' + READY)
                os.replace(fresh, result)
                out, err = waiter.communicate(timeout=5)
                self.assertEqual(waiter.returncode, 0, err)
                self.assertIn('DONE', out)
            finally:
                if waiter.poll() is None:
                    waiter.kill()
                    waiter.communicate()

    def test_late_wait_uses_launch_identity_after_an_in_place_edit(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result, record = Path(tmp) / 'result.md', Path(tmp) / 'w.exit'
            result.write_text('Kind: blocked\nTask: old\nAttempt: 1\nRemaining: decision\n' + READY)
            os.utime(result, (time.time() - 60, time.time() - 60))
            since = time.time()
            stale = worker.baseline(result, since)
            self.assertIsNotNone(stale)
            result.write_text(result.read_text().replace('Kind: blocked', 'Kind: completed'))
            record.write_text('exit 0\n')
            args = [sys.executable, str(SCRIPT), '--wait', str(result), '--since', str(since),
                    '--stale', str(stale), '--exit', str(record)]
            waiter = subprocess.run(args, capture_output=True, text=True, timeout=10)
            self.assertEqual(waiter.returncode, 0, waiter.stderr)
            self.assertIn('EXITED', waiter.stdout)
            self.assertNotIn('DONE', waiter.stdout)
            fresh = result.with_suffix('.tmp')
            fresh.write_bytes(result.read_bytes())
            os.replace(fresh, result)
            waiter = subprocess.run(args, capture_output=True, text=True, timeout=10)
            self.assertEqual(waiter.returncode, 0, waiter.stderr)
            self.assertIn('DONE', waiter.stdout)

    def test_posix_termination_unwinds_cleanup_and_restores_signal_handlers(self):
        for sig in (signal.SIGTERM, getattr(signal, 'SIGHUP', 1)):
            with self.subTest(sig=sig), tempfile.TemporaryDirectory() as tmp:
                worker = module()
                child = mock.Mock(pid=123, returncode=None)
                child.poll.side_effect = lambda: child.returncode
                child.terminate.side_effect = lambda: setattr(child, 'returncode', -sig)
                handlers = {}
                previous = mock.Mock()
                def install(sig, handler):
                    old = handlers.get(sig, previous)
                    handlers[sig] = handler
                    return old
                def interrupt(*args):
                    self.assertIn(sig, handlers, 'termination has no cleanup handler')
                    handlers[sig](sig, None)
                with mock.patch.object(worker, 'os', SimpleNamespace(name='posix', environ={},
                                       setpgrp=mock.Mock(), killpg=mock.Mock())), \
                        mock.patch.object(worker.signal, 'SIGTTOU', 22, create=True), \
                        mock.patch.object(worker.signal, 'SIGHUP', 1, create=True), \
                        mock.patch.object(worker.signal, 'SIGKILL', 9, create=True), \
                        mock.patch.object(worker.signal, 'signal', side_effect=install), \
                        mock.patch.object(worker.subprocess, 'Popen', return_value=child), \
                        mock.patch.object(worker.time, 'sleep', side_effect=interrupt), \
                        mock.patch('sys.stdin') as stdin, \
                        mock.patch('sys.argv', ['codex_worker.py', str(Path(tmp) / 'q.md'), '--', 'fake']):
                    stdin.isatty.return_value = False
                    with self.assertRaises(SystemExit) as ended:
                        worker.main()
                    self.assertEqual(ended.exception.code, 128 + sig)
                    worker.os.killpg.assert_any_call(123, signal.SIGTERM)
                    worker.os.killpg.assert_any_call(123, 9)
                    child.wait.assert_called()
                    self.assertIs(handlers[sig], previous)

    def test_posix_signals_stop_the_live_worker_group(self):
        if os.name == 'nt':
            sys.stderr.write('\nNOT RUN: %s (live POSIX signals)\n' % self.id())
            return
        for sig in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(sig=sig), tempfile.TemporaryDirectory() as tmp:
                started, escaped = Path(tmp) / 'started', Path(tmp) / 'escaped'
                grandchild = ('import signal,time; from pathlib import Path; '
                              'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
                              'Path(%r).touch(); time.sleep(2); Path(%r).touch()') % (str(started), str(escaped))
                parent = ('import os,subprocess,sys,time; from pathlib import Path; '
                          'Path(%r).write_text(str(os.getpid())); '
                          'subprocess.Popen([sys.executable,"-c",%r]); time.sleep(30)') % (
                              str(Path(tmp) / 'pid'), grandchild)
                supervisor = subprocess.Popen([sys.executable, str(SCRIPT), str(Path(tmp) / 'q.md'), '--',
                                               sys.executable, '-c', parent], stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE, text=True)
                try:
                    deadline = time.monotonic() + 10
                    while not started.exists():
                        self.assertIsNone(supervisor.poll())
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(.05)
                    supervisor.send_signal(sig)
                    out, err = supervisor.communicate(timeout=15)
                    self.assertEqual(supervisor.returncode, 128 + sig, out + err)
                    time.sleep(2.2)
                    self.assertFalse(escaped.exists(), 'a descendant outlived supervisor cancellation')
                finally:
                    if supervisor.poll() is None:
                        supervisor.kill()
                    supervisor.communicate()
                    pid = Path(tmp) / 'pid'
                    if pid.exists():
                        module().posix_tree(int(pid.read_text()), True)

    def test_normal_exit_status_is_preserved_and_no_question_is_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            question = Path(tmp) / 'QUESTION-w.md'
            result = subprocess.run([sys.executable, str(SCRIPT), str(question), '--', sys.executable, '-c', 'raise SystemExit(7)'],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertFalse(question.exists())

    def test_the_suite_never_writes_the_exit_record_of_the_worker_it_runs_in(self):
        # Inside a Codex worker the suite inherits KIT_WORKER_EXIT: a fixture that wrote it
        # made the lead's waiter report EXITED while that worker still ran.
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / 'caller.exit'
            run = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()),
                                  'CodexWorkerTests.test_normal_exit_status_is_preserved_and_no_question_is_invented'],
                                 capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, KIT_WORKER_EXIT=str(record)))
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertFalse(record.exists(), 'a fixture wrote the calling worker\'s exit record')

    def test_resume_keeps_the_question_when_the_child_fails_to_start(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            question = Path(tmp) / 'q.md'
            before = b'Choose A or B.\n<!-- codex-worker: ready -->'
            question.write_bytes(before)
            with mock.patch.dict(os.environ, KIT_WORKER_RESUME='1'), \
                    mock.patch.object(worker, 'os', SimpleNamespace(name='nt', environ=os.environ)), \
                    mock.patch.object(worker, 'windows_child', side_effect=OSError('launch failed')) as launch, \
                    mock.patch('sys.argv', ['codex_worker.py', str(question), '--', 'missing-cli']):
                with self.assertRaisesRegex(OSError, 'launch failed'):
                    worker.main()
            launch.assert_called_once()
            self.assertEqual(question.read_bytes(), before)

    def test_resume_consumes_the_old_question_only_after_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            question = Path(tmp) / 'q.md'
            before = b'Choose A or B.\n<!-- codex-worker: ready -->'
            for status in (7, 0):
                with self.subTest(status=status):
                    question.write_bytes(before)
                    code = 'import time; time.sleep(.4); raise SystemExit(%d)' % status
                    result = subprocess.run([sys.executable, str(SCRIPT), str(question), '--',
                                             sys.executable, '-c', code], capture_output=True, text=True,
                                            timeout=10, env=dict(os.environ, KIT_WORKER_GRACE='0',
                                                                 KIT_WORKER_RESUME='1'))
                    self.assertEqual(result.returncode, status, result.stderr)
                    self.assertEqual(question.exists(), status != 0)
                    if status:
                        self.assertEqual(question.read_bytes(), before)

    def test_publication_between_the_consumption_check_and_removal_is_preserved(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            question, fresh = Path(tmp) / 'q.md', Path(tmp) / 'fresh.md'
            question.write_text('The answered question.\n' + READY)
            fresh.write_text('A new unanswered question.\n' + READY)
            answered = worker.question_id(question)
            unlinking, renaming = Path.unlink, os.rename
            publications = []
            def publish():
                if publications:
                    return
                publications.append(True)
                if os.name == 'nt':
                    # A delete-sharing reader permits moving the old file aside on Windows.
                    renaming(question, question.with_suffix('.old'))
                os.replace(fresh, question)
            def unlink(path, *args, **kwargs):
                if path == question:
                    publish()
                return unlinking(path, *args, **kwargs)
            def rename(source, target, *args, **kwargs):
                if Path(source) == question:
                    publish()
                return renaming(source, target, *args, **kwargs)
            with mock.patch.object(Path, 'unlink', unlink), mock.patch.object(worker.os, 'rename', rename):
                self.assertIsNone(worker.consume(question, answered))
            self.assertEqual(publications, [True], 'the publication race was not scheduled')
            self.assertTrue(question.exists(), 'consumption removed the new unanswered question')
            self.assertEqual(question.read_text(), 'A new unanswered question.\n' + READY)

    def test_consumption_leaves_a_new_question_that_replaced_the_answered_one(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            question, fresh = Path(tmp) / 'q.md', Path(tmp) / 'fresh.md'
            question.write_text('The answered question.\n' + READY)
            answered = worker.question_id(question)
            # The resumed session published its blocked result, then a new question, before this poll.
            fresh.write_text('A new unanswered question.\n' + READY)
            os.replace(fresh, question)
            self.assertIsNone(worker.consume(question, answered))
            self.assertEqual(question.read_text(), 'A new unanswered question.\n' + READY)

    def test_a_slow_failed_resume_keeps_its_unaccepted_question(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            question = Path(tmp) / 'q.md'
            before = b'Choose A or B.\n<!-- codex-worker: ready -->'
            question.write_bytes(before)
            child = mock.Mock(returncode=1)
            child.poll.side_effect = [None, None, 1]
            clock = [0.0]
            def advance(seconds):
                clock[0] += 11.0
            with mock.patch.object(worker.time, 'monotonic', lambda: clock[0]), \
                    mock.patch.object(worker.time, 'sleep', advance), mock.patch.object(worker, 'stop'):
                self.assertEqual(worker.watch(child, question, None, answered=worker.question_id(question)), 1)
            self.assertGreater(clock[0], 10, 'the child never passed the old acceptance timeout')
            self.assertTrue(question.exists(), 'survival was mistaken for answer acceptance')
            self.assertEqual(question.read_bytes(), before)

    def test_any_valid_new_result_accepts_the_answer_while_the_child_runs(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            question, result = Path(tmp) / 'q.md', Path(tmp) / 'result.md'
            for kind in ('progress', 'handoff', 'blocked', 'completed'):
                with self.subTest(kind=kind):
                    result.unlink(missing_ok=True)
                    question.write_text('The answered question.\n' + READY)
                    child = mock.Mock(returncode=7)
                    child.poll.side_effect = [None, None, 7]
                    publications = []
                    def publish(seconds):
                        if not publications:
                            publications.append(True)
                            result.write_text('Kind: %s\nTask: t\nAttempt: 1\nRemaining: x\n%s' % (kind, READY))
                        else:
                            self.assertFalse(question.exists(), 'acceptance must be observed before child exit')
                    with mock.patch.dict(os.environ, KIT_WORKER_GRACE='10000', KIT_WORKER_STARTED='0'), \
                            mock.patch.object(worker.time, 'sleep', publish), mock.patch.object(worker, 'stop'):
                        self.assertEqual(worker.watch(child, question, None, result=result,
                                                       answered=worker.question_id(question)), 7)
                    self.assertFalse(question.exists())

    def test_live_record_cannot_report_exit_before_startup_lock(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / 'w.exit'
            live = record.with_suffix('.live')
            since = time.time() - 60
            observations, descriptors = [], []
            locking, opening = worker.lock, os.open
            def opened(*args, **kwargs):
                fd = opening(*args, **kwargs)
                if args[0] == live and args[1] & os.O_CREAT:
                    descriptors.append(fd)
                return fd
            def starting(fd):
                descriptors.append(fd)
                if live.exists():
                    os.utime(live, (since + 1, since + 1))  # paused longer than the old five-second deadline
                with mock.patch.object(worker, 'lock', locking):
                    observations.append(worker.gone(live, since))
                locking(fd)
            try:
                with mock.patch.dict(os.environ, KIT_WORKER_EXIT=str(record)), \
                        mock.patch.object(worker.os, 'open', side_effect=opened), \
                        mock.patch.object(worker, 'lock', side_effect=starting), \
                        mock.patch.object(worker, 'windows_child', side_effect=OSError('stop after startup')), \
                        mock.patch('sys.argv', ['codex_worker.py', str(Path(tmp) / 'q.md'), '--', 'missing-cli']):
                    # This host's child path is irrelevant to the creation-to-lock interval.
                    if os.name == 'nt':
                        with self.assertRaisesRegex(OSError, 'stop after startup'):
                            worker.main()
                    else:
                        with mock.patch.object(worker.subprocess, 'Popen', side_effect=OSError('stop after startup')):
                            with self.assertRaisesRegex(OSError, 'stop after startup'):
                                worker.main()
                self.assertEqual(observations, [False], 'an unlocked, unready file ended the waiter')
                self.assertFalse(worker.gone(live, since), 'the running supervisor was reported as ended')
            finally:
                for fd in set(descriptors):
                    os.close(fd)
            self.assertTrue(worker.gone(live, since), 'a ready supervisor with a dropped lock must be reported')

    def test_resume_preserves_a_new_question_even_with_the_same_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            question = Path(tmp) / 'q.md'
            before = b'Choose A or B.\n<!-- codex-worker: ready -->'
            question.write_bytes(before)
            code = ('from pathlib import Path; import os,time; q=Path(%r); p=q.with_suffix(".tmp"); '
                    'p.write_bytes(q.read_bytes()); os.replace(p,q); time.sleep(30)') % str(question)
            result = subprocess.run([sys.executable, str(SCRIPT), str(question), '--',
                                     sys.executable, '-c', code], capture_output=True, text=True,
                                    timeout=10, env=dict(os.environ, KIT_WORKER_GRACE='0',
                                                         KIT_WORKER_RESUME='1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('decision recorded', result.stdout)
            self.assertEqual(question.read_bytes(), before)

    def test_wait_after_progress_prints_the_follow_up_that_reports_the_completed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            question, result, record = (Path(tmp) / n for n in ('q.md', 'result.md', 'w.exit'))
            since = str(time.time())
            code = ('from pathlib import Path; import os,time\n'
                    'def publish(kind):\n'
                    '    p = Path(%r); p.write_text("Kind: " + kind + "\\nTask: t\\nAttempt: 1\\nRemaining: x\\n" + %r)\n'
                    '    os.replace(p, %r)\n'
                    'publish("progress"); time.sleep(3); publish("completed"); time.sleep(30)\n') % (
                        str(result) + '.tmp', READY, str(result))
            supervisor = subprocess.Popen([sys.executable, str(SCRIPT), str(question), str(result), '--',
                                           sys.executable, '-c', code], stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True,
                                          env=dict(os.environ, KIT_WORKER_GRACE='0.5', KIT_WORKER_STARTED=since,
                                                   KIT_WORKER_EXIT=str(record)))
            try:
                first = subprocess.run([sys.executable, str(SCRIPT), '--wait', str(result), '--since', since,
                                        '--exit', str(record)], capture_output=True, text=True, timeout=10)
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertIn('PROGRESS', first.stdout)
                command = next(line.partition('next result: ')[2] for line in first.stdout.splitlines()
                               if 'next result: ' in line)
                argv = shlex.split(command)
                self.assertEqual(argv[argv.index('--since') + 1], since, 'the .live and .exit records are read by the start')
                # The printed follow-up, run by a shell as the lead runs it, waits for the worker's next
                # result instead of repeating this one.
                again = subprocess.run(['sh', '-c', command], capture_output=True, text=True, timeout=15)
                self.assertEqual(again.returncode, 0, again.stderr)
                self.assertIn('DONE', again.stdout)
                self.assertNotIn('PROGRESS', again.stdout)
                out, err = supervisor.communicate(timeout=15)
                self.assertEqual(supervisor.returncode, 0, err)
                self.assertIn('DONE', out)
            finally:
                if supervisor.poll() is None:
                    supervisor.kill()
                supervisor.communicate()

    def test_the_stale_result_stays_allocated_while_supervisor_and_waiter_run(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / 'result.md'
            result.write_text('Kind: blocked\nTask: old\nAttempt: 1\nRemaining: decision\n' + READY)
            stale = result.stat().st_ino
            held = worker.pin(result, stale)
            if os.name == 'nt':
                # NTFS ids carry a sequence number; a held handle would block the publishing rename.
                self.assertIsNone(held)
                sys.stderr.write('\nNOT RUN: %s (POSIX inode reuse)\n' % self.id())
                return
            try:
                result.unlink()
                fresh = result.with_suffix('.tmp')
                fresh.write_text('Kind: completed\nTask: new\nAttempt: 1\nRemaining: none\n' + READY)
                os.replace(fresh, result)
                self.assertNotEqual(result.stat().st_ino, stale, 'a new result was given the held inode number')
                self.assertEqual(os.fstat(held).st_ino, stale)
            finally:
                os.close(held)
            if not Path('/proc/self/fd').is_dir():
                sys.stderr.write('\nNOT RUN: %s (supervisor and waiter descriptors need /proc)\n' % self.id())
                return
            stale = result.stat().st_ino
            key = (result.stat().st_dev, stale)
            def holds(pid):
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    for fd in Path('/proc/%d/fd' % pid).iterdir():
                        try:
                            info = os.stat(fd)
                        except OSError:
                            continue
                        if (info.st_dev, info.st_ino) == key:
                            return True
                    time.sleep(.05)
                return False
            since = str(time.time())
            supervisor = subprocess.Popen([sys.executable, str(SCRIPT), str(Path(tmp) / 'q.md'), str(result), '--',
                                           sys.executable, '-c', 'import time; time.sleep(30)'],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                          env=dict(os.environ, KIT_WORKER_STARTED=since, KIT_WORKER_STALE=str(stale)))
            waiter = subprocess.Popen([sys.executable, str(SCRIPT), '--wait', str(result), '--since', since,
                                       '--stale', str(stale)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                self.assertTrue(holds(supervisor.pid), 'the supervisor let the stale result be freed')
                self.assertTrue(holds(waiter.pid), 'the waiter let the stale result be freed')
            finally:
                supervisor.terminate()
                waiter.kill()
                for process in (supervisor, waiter):
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

    def test_result_identity_and_contents_share_a_descriptor_during_a_publication(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result, fresh = Path(tmp) / 'result.md', Path(tmp) / 'fresh.md'
            result.write_text('Kind: progress\nTask: t\nAttempt: 1\nRemaining: work\n' + READY)
            expected = module().result_kind(result)  # another poller: this one has read nothing yet
            fresh.write_text('Kind: handoff\nTask: t\nAttempt: 1\nRemaining: review\n' + READY)
            fstat, opening = os.fstat, Path.open
            renamed = []
            def publish(info):
                if not renamed:
                    if os.name == 'nt':
                        # Windows can rename a shared-delete file but refuses replacing it open.
                        result.rename(result.with_suffix('.old'))
                    os.replace(fresh, result)
                    renamed.append(True)
                return info
            def opened(path, *args, **kwargs):
                if os.name != 'nt' or path != result:
                    return opening(path, *args, **kwargs)
                # Allow the real scheduled rename while the reader holds the old Windows file.
                import ctypes
                import msvcrt
                api = ctypes.WinDLL('kernel32', use_last_error=True)
                api.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                                           ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
                api.CreateFileW.restype = ctypes.c_void_p
                handle = api.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x80, None)
                self.assertNotIn(handle, (None, ctypes.c_void_p(-1).value), ctypes.get_last_error())
                return open(msvcrt.open_osfhandle(handle, os.O_RDONLY), *args, **kwargs)
            with mock.patch.object(worker.os, 'fstat', lambda fd: publish(fstat(fd))), \
                    mock.patch.object(Path, 'open', opened):
                observed = worker.result_kind(result)
            self.assertEqual(renamed, [True], 'the publication was not scheduled between metadata and read')
            self.assertEqual(observed, expected, 'new contents were paired with the preceding result identity')
            self.assertEqual(worker.result_kind(result)[0], 'HANDOFF')

    def test_a_follow_up_wait_reports_other_contents_on_a_recycled_inode(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result, record = Path(tmp) / 'result.md', Path(tmp) / 'w.exit'
            record.write_text('exit 0\n')
            stat, fstat = Path.stat, os.fstat
            def reused(info):
                return SimpleNamespace(st_ino=41, st_mtime=info.st_mtime, st_mtime_ns=info.st_mtime_ns,
                                       st_size=info.st_size)
            def wait(argv):
                output = io.StringIO()
                with mock.patch('sys.argv', argv), mock.patch('sys.stdout', output):
                    self.assertEqual(worker.main(), 0)
                return output.getvalue()
            def follow_up(output):
                command = next(line.partition('next result: ')[2] for line in output.splitlines()
                               if 'next result: ' in line)
                return shlex.split(command)[1:]
            args = [str(SCRIPT), '--wait', str(result), '--stale', '0', '--exit', str(record)]
            with mock.patch.object(Path, 'stat', lambda path, *a, **k: reused(stat(path, *a, **k))), \
                    mock.patch.object(worker.os, 'fstat', lambda fd: reused(fstat(fd))), \
                    mock.patch.object(worker, 'pin'):
                for kind, notice in (('progress', 'PROGRESS'), ('handoff', 'HANDOFF'), ('completed', 'DONE')):
                    fresh = result.with_suffix('.tmp')
                    fresh.write_text('Kind: %s\nTask: t\nAttempt: 1\nRemaining: x\n%s' % (kind, READY))
                    os.replace(fresh, result)
                    output = wait(args)
                    self.assertIn('codex_worker: ' + notice + ': ', output)
                    if notice != 'DONE':
                        args = follow_up(output)
                        unchanged = wait(args)
                        self.assertIn('EXITED', unchanged)
                        self.assertNotIn('codex_worker: ' + notice + ': ', unchanged)


    def test_a_follow_up_wait_counts_other_contents_by_rename_or_rewrite_and_never_the_same_bytes(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result, fresh = Path(tmp) / 'result.md', Path(tmp) / 'fresh.md'
            progress = 'Kind: progress\nTask: t\nAttempt: 1\nRemaining: x\n' + READY
            result.write_text(progress)
            kind, reported = worker.result_kind(result)
            self.assertEqual(kind, 'PROGRESS')
            fresh.write_text(progress)
            os.replace(fresh, result)
            self.assertEqual(worker.result_kind(result, 0, reported), ('', None), 'the same bytes, renamed, were new')
            result.write_text(progress.replace('Kind: progress', 'Kind: completed'))
            self.assertEqual(worker.result_kind(result, 0, reported)[0], 'DONE', 'an in-place rewrite was missed')
            fresh.write_text(progress.replace('Kind: progress', 'Kind: handoff'))
            os.replace(fresh, result)
            self.assertEqual(worker.result_kind(result, 0, reported)[0], 'HANDOFF', 'a renamed result was missed')

    def test_a_poller_opens_a_result_it_read_again_only_after_it_changed(self):
        # Windows refuses a rename over a file any process holds open, delete sharing included.
        # Its stat still opens the file for a moment: the publisher's retry covers that
        # (test_a_publication_retries_a_rename_windows_refuses_while_a_poll_holds_the_result).
        pollers = module(), module()
        with tempfile.TemporaryDirectory() as tmp:
            result, fresh = Path(tmp) / 'result.md', Path(tmp) / 'fresh.md'
            fstat, pending = os.fstat, []
            def publish():
                if pending:
                    os.replace(pending.pop(), result)
            result.write_text('Kind: progress\nTask: t\nAttempt: 1\nRemaining: x\n' + READY)
            # A poller calls fstat only while it holds the result open.
            with mock.patch.object(os, 'fstat', lambda fd: publish() or fstat(fd)):
                for attempt, (kind, notice) in enumerate((('handoff', 'HANDOFF'), ('progress', 'PROGRESS'),
                                                          ('blocked', 'BLOCKED'), ('completed', 'DONE')), 2):
                    for poller in pollers:
                        self.assertTrue(poller.result_kind(result)[0])
                    fresh.write_text('Kind: %s\nTask: t\nAttempt: %d\nRemaining: x\n%s' % (kind, attempt, READY))
                    pending.append(fresh)
                    # The worker's rename lands inside this poll of a result the poller already read,
                    # while it holds the file if it ever does, else just after it.
                    pollers[attempt % 2].result_kind(result)
                    publish()
                    for poller in pollers:
                        self.assertEqual(poller.result_kind(result)[0], notice)

    def test_a_poll_that_opens_the_result_during_a_rename_over_it_reads_it_at_the_next(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / 'result.md'
            result.write_text('Kind: completed\nTask: t\nAttempt: 1\nRemaining: none\n' + READY)
            with mock.patch.object(Path, 'open', side_effect=PermissionError(13, 'Permission denied')):
                if os.name == 'nt':
                    # Windows refuses an open while a rename replaces the file: no supervisor crash.
                    self.assertEqual(worker.result_kind(result), ('', None))
                else:
                    with self.assertRaises(PermissionError):  # a real permission problem stays an error
                        worker.result_kind(result)
            self.assertEqual(worker.result_kind(result)[0], 'DONE')

    def test_the_answered_question_is_never_read_and_a_read_during_a_rename_is_retried(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            question, fresh = Path(tmp) / 'q.md', Path(tmp) / 'fresh.md'
            question.write_text('The answered question.\n' + READY)
            answered = worker.question_id(question)
            fresh.write_text('A new question.\n' + READY)
            child = mock.Mock(returncode=None)
            child.poll.return_value = None
            reading, reads, renaming = Path.read_text, [], []
            def read(path, *args, **kwargs):
                if path == question:
                    reads.append(worker.question_id(path))
                    if renaming:
                        renaming.pop()
                        raise PermissionError(13, 'Permission denied')  # Windows: met the rename
                return reading(path, *args, **kwargs)
            def publish(seconds):
                if fresh.exists():
                    os.replace(fresh, question)
                    renaming.append(True)
            with mock.patch.dict(os.environ, KIT_WORKER_GRACE='0'), mock.patch.object(Path, 'read_text', read), \
                    mock.patch.object(worker.time, 'sleep', publish), mock.patch.object(worker, 'stop'):
                if os.name == 'nt':
                    self.assertEqual(worker.watch(child, question, None, answered=answered), 0)
                else:
                    with self.assertRaises(PermissionError):  # a real permission problem stays an error
                        worker.watch(child, question, None, answered=answered)
            self.assertTrue(reads, 'the new question was never read')
            self.assertNotIn(answered, reads, 'the answered question was opened while unchanged')
            self.assertEqual(question.read_text(), 'A new question.\n' + READY)

    def test_an_empty_unlocked_live_record_is_damaged_and_does_not_end_the_wait(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result, record = Path(tmp) / 'result.md', Path(tmp) / 'w.exit'
            live = record.with_suffix('.live')
            # An empty file cannot establish startup identity, however old it becomes.
            live.write_bytes(b'')
            since = time.time() - 30
            self.assertFalse(worker.gone(live, since), 'a supervisor still starting was reported as ended')
            os.utime(live, (since + 1, since + 1))
            self.assertFalse(worker.gone(live, since), 'a damaged record was treated as proof of death')
            waiter = subprocess.Popen([sys.executable, str(SCRIPT), '--wait', str(result), '--since', str(since),
                                      '--exit', str(record)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    waiter.communicate(timeout=.4)
                self.assertIsNone(waiter.poll(), 'the waiter unsubscribed from a potentially live supervisor')
            finally:
                waiter.kill()
                waiter.communicate()

    def test_the_supervisor_retries_its_lock_while_a_waiter_probes_it(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / 'w.live'
            opening, locking = os.open, worker.lock
            descriptors, probes = [], []
            def opened(*args, **kwargs):
                fd = opening(*args, **kwargs)
                if args[0] == live and args[1] & os.O_CREAT:
                    descriptors.append(fd)
                return fd
            def probed(fd):
                descriptors.append(fd)
                if not probes:
                    probes.append(fd)
                    raise OSError('held by a waiter probe')
                locking(fd)
            try:
                with mock.patch.dict(os.environ, KIT_WORKER_EXIT=str(live.with_suffix('.exit'))), \
                        mock.patch.object(worker.os, 'open', side_effect=opened), \
                        mock.patch.object(worker, 'lock', side_effect=probed), \
                        mock.patch.object(worker, 'windows_child', side_effect=OSError('stop after startup')), \
                        mock.patch.object(worker.subprocess, 'Popen', side_effect=OSError('stop after startup')), \
                        mock.patch('sys.argv', ['codex_worker.py', str(Path(tmp) / 'q.md'), '--', 'missing-cli']):
                    with self.assertRaisesRegex(OSError, 'stop after startup'):
                        worker.main()
            finally:
                for fd in set(descriptors):
                    os.close(fd)
            self.assertEqual(live.read_bytes().strip(), b'%d' % os.getpid(), 'the startup lock was not retried')

    def test_the_exit_record_and_status_survive_a_question_that_cannot_be_removed(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            question, record = Path(tmp) / 'q.md', Path(tmp) / 'w.exit'
            question.write_text('Choose A or B.\n' + READY)
            child = mock.Mock(returncode=0)
            child.poll.return_value = 0
            with mock.patch.dict(os.environ, KIT_WORKER_EXIT=str(record)), \
                    mock.patch.object(Path, 'unlink', side_effect=PermissionError('open in another program')):
                self.assertEqual(worker.watch(child, question, None, answered=worker.question_id(question)), 0)
            self.assertIn('exit 0 at ', record.read_text())
            self.assertTrue(question.exists())

    def test_a_resumed_supervisor_publishes_its_live_record_while_a_waiter_probes_the_old_one(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / 'w.exit'
            live = record.with_suffix('.live')
            live.write_bytes(b'4242\n')  # the previous run's record, which the lead's waiter opens
            probe = worker.shared_open(live)  # as gone() opens it, delete sharing included
            if os.name == 'nt':
                other = Path(tmp) / 'other'
                other.write_bytes(b'x')
                with self.assertRaises(PermissionError):  # the refusal the startup waits through is real
                    os.replace(other, live)
            else:
                sys.stderr.write('\nNOT RUN: %s (the Windows rename refusal)\n' % self.id())
            closing = threading.Timer(.3, os.close, [probe])
            closing.start()
            try:
                held = worker.start_live(record)
            finally:
                closing.join()
            os.close(held)
            self.assertEqual(live.read_bytes(), b'%d\n' % os.getpid())

    def test_a_supervisor_that_fails_to_start_records_it_and_the_wait_ends(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result, record = Path(tmp) / 'result.md', Path(tmp) / 'w.exit'
            live = record.with_suffix('.live')
            live.write_bytes(b'4242\n')  # the previous run's, from before this run started
            os.utime(live, (time.time() - 60, time.time() - 60))
            since = str(time.time() - 1)
            replacing = os.replace
            def refused(source, target):
                if Path(target) == live:
                    raise PermissionError(13, 'held open by a waiter')  # every attempt
                return replacing(source, target)
            with mock.patch.dict(os.environ, KIT_WORKER_EXIT=str(record), KIT_WORKER_STARTED=since), \
                    mock.patch.object(worker.os, 'replace', refused), mock.patch.object(worker.time, 'sleep'), \
                    mock.patch('sys.argv', ['codex_worker.py', str(Path(tmp) / 'q.md'), str(result), '--', 'missing-cli']):
                with self.assertRaises(PermissionError):
                    worker.main()
            self.assertIn('supervisor failed to start (PermissionError)', record.read_text())
            # Without the record the wait hangs: the stale live record predates the run.
            waiter = subprocess.run([sys.executable, str(SCRIPT), '--wait', str(result), '--since', since,
                                     '--exit', str(record)], capture_output=True, text=True, timeout=10)
            self.assertEqual(waiter.returncode, 0, waiter.stderr)
            self.assertIn('EXITED (supervisor failed to start', waiter.stdout)

    def test_a_publication_retries_a_rename_windows_refuses_while_a_poll_holds_the_result(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result, fresh = Path(tmp) / 'result.md', Path(tmp) / 'fresh.md'
            result.write_text('Kind: progress\nTask: t\nAttempt: 1\nRemaining: x\n' + READY)
            fresh.write_text('Kind: handoff\nTask: t\nAttempt: 2\nRemaining: review\n' + READY)
            replacing, attempts = os.replace, []
            def counted(source, target):
                attempts.append(target)
                return replacing(source, target)
            poll = worker.shared_open(result)  # a stat or a read of the result, delete sharing included
            closing = threading.Timer(.3, os.close, [poll])
            closing.start()
            try:
                with mock.patch.object(worker.os, 'replace', counted):
                    worker.renamed(fresh, result)
            finally:
                closing.join()
            self.assertEqual(worker.result_kind(result)[0], 'HANDOFF')
            if os.name == 'nt':
                self.assertGreater(len(attempts), 1, 'the held result did not refuse the rename')
            else:
                sys.stderr.write('\nNOT RUN: %s (the Windows rename refusal)\n' % self.id())
            # The worker's instruction runs the same step from its own shell.
            fresh.write_text('Kind: completed\nTask: t\nAttempt: 3\nRemaining: none\n' + READY)
            published = subprocess.run([sys.executable, str(SCRIPT), '--publish', str(fresh), str(result)],
                                       capture_output=True, text=True, timeout=10)
            self.assertEqual(published.returncode, 0, published.stderr)
            self.assertFalse(fresh.exists())
            self.assertEqual(module().result_kind(result)[0], 'DONE')

    def test_an_unchanged_new_question_is_read_once_and_a_changed_one_again(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            question = Path(tmp) / 'q.md'
            question.write_text('A question still being written.')  # no end marker yet
            polls = iter([None] * 10)
            child = mock.Mock(returncode=0)
            child.poll.side_effect = lambda: next(polls, 0)
            reading, reads, sleeps = Path.read_text, [], []
            def read(path, *args, **kwargs):
                if path == question:
                    reads.append(path)
                return reading(path, *args, **kwargs)
            def sleep(seconds):
                sleeps.append(seconds)
                if len(sleeps) == 5:
                    question.write_text('A question.\n' + READY)
            with mock.patch.dict(os.environ, KIT_WORKER_GRACE='0'), mock.patch.object(Path, 'read_text', read), \
                    mock.patch.object(worker.time, 'sleep', sleep), mock.patch.object(worker, 'stop'), \
                    mock.patch('sys.stdout', new=io.StringIO()) as output:
                self.assertEqual(worker.watch(child, question, None), 0)
            self.assertIn('decision recorded', output.getvalue())
            self.assertEqual(len(reads), 2, 'an unchanged question was opened on every poll')

    def test_a_lasting_windows_refusal_is_an_error_not_an_endless_wait(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result, question = Path(tmp) / 'result.md', Path(tmp) / 'q.md'
            result.write_text('Kind: completed\nTask: t\nAttempt: 1\nRemaining: none\n' + READY)
            question.write_text('A question.\n' + READY)
            denied = PermissionError(13, 'Access is denied')  # an ACL denial, or a lock that stays
            for read, path, refused in ((worker.result_kind, result, ('', None)), (worker.published, question, None)):
                with self.subTest(read=read.__name__):
                    with mock.patch.object(Path, 'open', side_effect=denied), \
                            mock.patch.object(Path, 'read_text', side_effect=denied):
                        if os.name != 'nt':
                            with self.assertRaises(PermissionError):
                                read(path)
                            continue
                        for _ in range(worker.REFUSALS - 1):
                            self.assertEqual(read(path), refused)
                    self.assertTrue(read(path))  # a read that succeeds starts the count again
                    path.write_text(path.read_text() + '\n')  # changed, so a poll opens it again
                    with mock.patch.object(Path, 'open', side_effect=denied), \
                            mock.patch.object(Path, 'read_text', side_effect=denied):
                        for _ in range(worker.REFUSALS):
                            self.assertEqual(read(path), refused)
                        with self.assertRaises(PermissionError, msg='a lasting refusal was waited on forever'):
                            read(path)

    def test_an_absent_file_resets_the_refusal_count_and_only_an_unbroken_run_of_refusals_raises(self):
        worker = module()
        denied, absent = PermissionError(13, 'sharing violation'), FileNotFoundError(2, 'not published yet')
        with tempfile.TemporaryDirectory() as tmp:
            for read, method, refused, missing in ((worker.result_kind, 'stat', ('', None), ('', None)),
                                                   (worker.published, 'read_text', None, '')):
                path = Path(tmp) / (read.__name__ + '.md')
                with self.subTest(read=read.__name__), mock.patch.object(worker.os, 'name', 'nt'):
                    with mock.patch.object(Path, method, side_effect=[denied, absent] * (worker.REFUSALS + 1)):
                        for _ in range(worker.REFUSALS + 1):
                            self.assertEqual(read(path), refused)
                            self.assertEqual(read(path), missing)
                    with mock.patch.object(Path, method, side_effect=denied):
                        for _ in range(worker.REFUSALS):
                            self.assertEqual(read(path), refused)
                        with self.assertRaises(PermissionError, msg='a lasting refusal was waited on forever'):
                            read(path)

    def test_a_follow_up_printed_with_a_legacy_stale_id_compares_its_hash(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            result, record = Path(tmp) / 'result.md', Path(tmp) / 'w.exit'
            text = 'Kind: progress\nTask: t\nAttempt: 1\nRemaining: x\n' + READY
            result.write_text(text)
            record.write_text('exit 0\n')
            # The INO:HASH form a follow-up printed before the content hash alone decided.
            legacy = '%d:%s' % (result.stat().st_ino, hashlib.sha256(text.encode('utf-8')).hexdigest())
            output = io.StringIO()
            with mock.patch('sys.argv', [str(SCRIPT), '--wait', str(result), '--since', '0', '--stale', legacy,
                                         '--exit', str(record)]), mock.patch('sys.stdout', output):
                self.assertEqual(worker.main(), 0)
            self.assertIn('EXITED', output.getvalue())
            self.assertNotIn('PROGRESS', output.getvalue(), 'the reported result was reported again')


if __name__ == '__main__':
    unittest.main()
