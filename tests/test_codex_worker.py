"""A decision sidecar ends the interactive worker without losing its session."""
from pathlib import Path
import importlib.util
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files/scripts/codex_worker.py'
READY = '<!-- codex-worker: ready -->'


def module():
    spec = importlib.util.spec_from_file_location('codex_worker', SCRIPT)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class CodexWorkerTests(unittest.TestCase):
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

    def test_normal_exit_status_is_preserved_and_no_question_is_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            question = Path(tmp) / 'QUESTION-w.md'
            result = subprocess.run([sys.executable, str(SCRIPT), str(question), '--', sys.executable, '-c', 'raise SystemExit(7)'],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertFalse(question.exists())


if __name__ == '__main__':
    unittest.main()
