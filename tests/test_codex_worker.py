"""A decision sidecar ends the interactive worker without losing its session."""
from pathlib import Path
import importlib.util
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
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

    def test_live_record_cannot_report_exit_before_startup_lock(self):
        worker = module()
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / 'w.exit'
            live = record.with_suffix('.live')
            since = time.time()
            observations, descriptors = [], []
            locking, opening = worker.lock, os.open
            def opened(*args, **kwargs):
                fd = opening(*args, **kwargs)
                if args[0] == live and args[1] & os.O_CREAT:
                    descriptors.append(fd)
                return fd
            def starting(fd):
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
                for fd in descriptors:
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


if __name__ == '__main__':
    unittest.main()
