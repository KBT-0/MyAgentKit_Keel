"""The review run on native Windows: agent_process supervises a reviewer without select().

Native Windows Python has no select() on a pipe and no process group to kill. There the
reviewer starts suspended, joins a Job Object of its own and only then runs; its pipes are
read by one thread each; stopping it terminates the job, which reaches a descendant that
outlived the reviewer and still holds a pipe, and a supervisor that dies takes the job down.
Every case here runs only on native Windows; elsewhere each prints a NOT RUN line and passes.
"""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'core/scripts'))
import agent_process  # noqa: E402
import codex_quota  # noqa: E402

WINDOWS = os.name == 'nt'


def windows_only(test):
    def run(self):
        if not WINDOWS:
            sys.stderr.write('\nNOT RUN: %s (native Windows only)\n' % self.id())
            return
        return test(self)
    run.__name__, run.__doc__ = test.__name__, test.__doc__
    return run


def alive(pid):
    """True while the process `pid` runs (SYNCHRONIZE handle, not yet signalled)."""
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel32.OpenProcess(0x00100000, False, pid)
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)


def gone_within(pid, seconds=10):
    deadline = time.monotonic() + seconds
    while alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.1)
    return True


class ReviewOnWindows(unittest.TestCase):
    def setUp(self):
        if not WINDOWS:
            return
        self.tmp = Path(tempfile.mkdtemp(prefix='kit-review-win-'))
        self.addCleanup(lambda: subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', str(self.tmp)],
                                               capture_output=True))

    def script(self, name, body):
        path = self.tmp / name
        path.write_text(body)
        return [sys.executable, '-I', str(path)]

    @windows_only
    def test_prompt_in_output_out_exit_status_kept(self):
        command = self.script('echo.py', 'import sys\ndata = sys.stdin.read()\n'
                                         'print(data.upper()); print("err", file=sys.stderr)\nsys.exit(3)\n')
        result = agent_process.run(command, 'a prompt', self.tmp, 20)
        self.assertEqual(result['exit_code'], 3)
        self.assertIn('A PROMPT', result['stdout'])
        self.assertIn('err', result['stderr'])
        self.assertIsNone(result['termination'])
        self.assertFalse(result['cancelled'])

    @windows_only
    def test_a_descendant_holding_the_pipe_is_stopped_at_the_deadline(self):
        # The reviewer exits at once; its child keeps stdout open and sleeps. Read to EOF, the
        # run waits for the deadline; then the job is terminated, the descendant with it.
        marker = self.tmp / 'grandchild.pid'
        command = self.script('parent.py', (
            'import subprocess, sys\n'
            'child = subprocess.Popen([sys.executable, "-c", "import os, sys, time; '
            'open(sys.argv[1], \'w\').write(str(os.getpid())); time.sleep(120)", sys.argv[1]])\n'
            'print("started", flush=True)\n') )
        command.append(str(marker))
        started = time.monotonic()
        result = agent_process.run(command, '', self.tmp, 4)
        self.assertEqual(result['termination'], 'timeout')
        self.assertIn('started', result['stdout'])
        self.assertLess(time.monotonic() - started, 15)
        pid = int(marker.read_text())
        self.assertTrue(gone_within(pid), 'the descendant outlived the stopped review')

    @windows_only
    def test_output_past_the_limit_stops_the_reviewer(self):
        command = self.script('flood.py', 'import sys\nwhile True:\n    sys.stdout.write("x" * 65536)\n')
        result = agent_process.run(command, '', self.tmp, 60)
        self.assertEqual(result['termination'], 'output_limit')
        self.assertEqual(len(result['stdout']), 8_000_000)

    @windows_only
    def test_a_killed_supervisor_takes_its_reviewer_with_it(self):
        # The job is killed when its last handle closes: the supervisor's, at its death.
        marker = self.tmp / 'reviewer.pid'
        reviewer = self.script('reviewer.py', 'import os, sys, time\n'
                                              'open(sys.argv[1], "w").write(str(os.getpid()))\n'
                                              'time.sleep(120)\n') + [str(marker)]
        supervisor = subprocess.Popen([sys.executable, '-I', '-c', (
            'import sys; from pathlib import Path\n'
            'sys.path.insert(0, sys.argv[1]); import agent_process\n'
            'agent_process.run(sys.argv[3:], "", Path(sys.argv[2]), 120)\n'),
            str(ROOT / 'core/scripts'), str(self.tmp), *reviewer])
        deadline = time.monotonic() + 20
        while not marker.exists() or not marker.read_text():
            self.assertLess(time.monotonic(), deadline, 'the reviewer never started')
            time.sleep(0.1)
        pid = int(marker.read_text())
        self.assertTrue(alive(pid))
        supervisor.kill()
        supervisor.wait()
        self.assertTrue(gone_within(pid), 'the reviewer outlived its killed supervisor')

    @windows_only
    def test_a_cli_installed_as_a_cmd_file_is_launched_by_its_bare_name(self):
        # npm installs codex and claude as codex.cmd and claude.cmd. CreateProcess adds only
        # .exe to a bare name, so the first real review on native Windows exited 127.
        bin_dir = self.tmp / 'bin'
        bin_dir.mkdir()
        script = self.tmp / 'cli.py'
        script.write_text('import sys\nprint("cli ran", sys.argv[1:], sys.stdin.read())\n')
        (bin_dir / 'fakecli.cmd').write_text('@"%s" -I "%s" %%*\r\n' % (sys.executable, script))
        path = str(bin_dir) + os.pathsep + os.environ['PATH']
        old = os.environ['PATH']
        os.environ['PATH'] = path
        try:
            result = agent_process.run(['fakecli', 'exec', '--json'], 'the prompt', self.tmp, 30)
        finally:
            os.environ['PATH'] = old
        self.assertEqual(result['exit_code'], 0, result)
        self.assertIn("cli ran ['exec', '--json'] the prompt", result['stdout'])

    @windows_only
    def test_a_batch_cli_is_never_handed_an_argument_cmd_would_run(self):
        # cmd.exe reads a .cmd's command line as shell, and Popen does not escape `&` for it:
        # `a&echo>injected.txt` ran echo (BatBadBut). Refused before anything starts.
        launcher = self.tmp / 'fakecli.cmd'
        launcher.write_text('@echo ran %*\r\n')
        for arg in ('a&echo>injected.txt', 'x|more', '%PATH%', 'say "hi"'):
            with self.subTest(arg=arg):
                result = agent_process.run([str(launcher), arg], '', self.tmp, 30)
                self.assertEqual(result['termination'], 'unavailable', result)
                self.assertIn('batch file', result['stderr'])
        self.assertFalse((self.tmp / 'injected.txt').exists())
        result = agent_process.run([str(launcher), 'plain', 'C:\\with space\\x'], '', self.tmp, 30)
        self.assertEqual(result['exit_code'], 0, result)
        self.assertIn('ran plain', result['stdout'])

    @windows_only
    def test_a_batch_cli_path_is_never_expanded_by_cmd(self):
        from unittest.mock import patch
        launcher = self.tmp / '%REVIEW_TEST_EXPANSION%.cmd'
        launcher.write_text('@echo literal launcher\r\n')
        (self.tmp / 'other.cmd').write_text('@echo expanded launcher\r\n')
        with patch.dict(os.environ, REVIEW_TEST_EXPANSION='other'):
            for command in ([str(launcher)], [launcher.stem]):
                with self.subTest(command=command), patch.dict(os.environ, PATH=str(self.tmp)):
                    result = agent_process.run(command, '', self.tmp, 30)
                    self.assertEqual(result['termination'], 'unavailable', result)
                    self.assertIn('batch file', result['stderr'])
                    self.assertNotIn('launcher', result['stdout'])

    @windows_only
    def test_a_ctrl_c_as_the_launch_returns_stops_the_reviewer(self):
        # A Ctrl-C after the reviewer existed and before run() held its handle raised past the
        # cleanup that stops it: run() said cancelled while the reviewer ran on.
        import signal
        from unittest.mock import patch
        marker = self.tmp / 'reviewer.pid'
        command = self.script('sleeper.py', 'import os, sys, time\n'
                                            'open(sys.argv[1], "w").write(str(os.getpid()))\n'
                                            'time.sleep(120)\n') + [str(marker)]
        real = agent_process.launch

        def interrupted(*args, **kwargs):
            child = real(*args, **kwargs)
            deadline = time.monotonic() + 20  # the reviewer is running, then the Ctrl-C comes
            while not (marker.exists() and marker.read_text()) and time.monotonic() < deadline:
                time.sleep(0.05)
            signal.raise_signal(signal.SIGINT)
            return child
        with patch.object(agent_process, 'launch', interrupted):
            result = agent_process.run(command, '', self.tmp, 60)
        self.assertEqual(result['termination'], 'cancelled', result)
        self.assertTrue(result['cancelled'])
        self.assertTrue(marker.exists() and marker.read_text(), 'the reviewer never ran')
        self.assertTrue(gone_within(int(marker.read_text())), 'the reviewer ran on after the cancel')

    @windows_only
    def test_a_ctrl_c_during_settlement_is_persisted_before_handing_back(self):
        import signal
        record = self.tmp / 'failure.json'
        forwarded, samples = [], []
        previous = agent_process.hold(lambda sig, frame: forwarded.append(sig))
        caller = {sig: signal.getsignal(sig) for sig in previous}

        def settle(held):
            samples.append(set(held))
            record.write_text(json.dumps({'termination': 'cancelled' if held else 'quota',
                                          'cancelled': bool(held)}))
            self.assertEqual(forwarded, [])
            if len(samples) == 1:
                signal.raise_signal(signal.SIGINT)

        try:
            agent_process.handing_back(caller, settle)
            self.assertEqual(json.loads(record.read_text()), {'termination': 'cancelled', 'cancelled': True})
            self.assertEqual(samples, [set(), {signal.SIGINT}])
            self.assertEqual(forwarded, [signal.SIGINT])
            for sig, handler in caller.items():
                self.assertIs(signal.getsignal(sig), handler)
        finally:
            agent_process.restore(previous)

    @windows_only
    def test_a_second_cancel_during_restoration_sees_settled_records(self):
        self.cancel_at_hand_back('restoration')

    @windows_only
    def test_a_second_cancel_during_persistence_cannot_interrupt_settlement(self):
        self.cancel_at_hand_back('persistence')

    def cancel_at_hand_back(self, second_cancel):
        import contextlib
        import io
        import signal
        from unittest.mock import patch
        import agent_usage
        import codex_bridge
        repo = self.tmp / 'repo'
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        (repo / 'guidance.md').write_text('Fixture guidance.\n')
        (repo / '.gitignore').write_text('.myagentkit/\ndocs/reviews/\n')
        subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t',
                        'commit', '-qm', 'base'], check=True, capture_output=True)
        (repo / 'guidance.md').write_text('Changed guidance.\n')
        result, forwarded, samples, fired = [], [], [], []
        real_signal, real_pending = signal.signal, agent_process.pending
        real_hand_back = agent_process.handing_back
        real_relabel = agent_usage.relabel_cancelled

        class CallerCancel(Exception):
            pass

        def caller(sig, frame):
            # The caller must see the correction already persisted when the signal arrives.
            forwarded.append((sig, result[0].copy(),
                              json.loads(Path(result[0]['usage_record']).read_text())))
            raise CallerCancel

        previous = agent_process.hold(caller)

        def pending():
            held = real_pending()
            samples.append(set(held))
            if len(samples) == 2:
                # The recorder receives this after the loop's empty sample, before any
                # handler swap. It must be settled before a caller can raise or terminate.
                signal.raise_signal(signal.SIGTERM)
            return held

        def hand_back(previous, settle):
            with patch.object(agent_process, 'pending', side_effect=pending):
                real_hand_back(previous, settle)

        def install(sig, handler):
            if second_cancel == 'restoration' and sig == signal.SIGTERM and handler is caller and not fired:
                fired.append(True)
                # SIGINT is already restored; its raising caller must see the first cancel
                # persisted, and cleanup must still restore SIGTERM.
                signal.raise_signal(signal.SIGINT)
            return real_signal(sig, handler)

        def relabel(*args, **kwargs):
            if second_cancel == 'persistence' and not fired:
                fired.append(True)
                signal.raise_signal(signal.SIGINT)
            return real_relabel(*args, **kwargs)

        quota = {'exit_code': 1, 'stdout': json.dumps({'type': 'turn.failed',
                 'error': {'message': 'usage limit reached'}}), 'stderr': '',
                 'termination': None, 'cancelled': False, 'duration_ms': 1}
        try:
            output = io.StringIO()
            with patch.dict(os.environ, REVIEW_DOCS='guidance.md', MYAGENTKIT_CAPTURE_QUOTA='0',
                            MYAGENTKIT_DELEGATION_DEPTH='0'), \
                    patch.object(agent_process, 'run', return_value=quota), \
                    patch.object(agent_process, 'handing_back', side_effect=hand_back), \
                    patch.object(agent_usage, 'relabel_cancelled', side_effect=relabel), \
                    patch.object(signal, 'signal', side_effect=install), contextlib.redirect_stdout(output), \
                    self.assertRaises(CallerCancel):
                codex_bridge.main(['--repo', str(repo), '--model', 'fixture', '--uncommitted'], result.append)
            self.assertTrue(forwarded)
            for sig, seen_result, usage in forwarded:
                self.assertEqual((seen_result['failure_kind'], seen_result['cancelled']), ('cancelled', True))
                self.assertEqual(usage['failure_kind'], 'cancelled')
            self.assertEqual(fired, [True])
            published = [json.loads(line.removeprefix('review invocation: '))
                         for line in output.getvalue().splitlines() if line.startswith('review invocation: ')]
            self.assertEqual((published[-1]['failure_kind'], published[-1]['cancelled']), ('cancelled', True))
            self.assertIn('| failure_kind | cancelled |', Path(result[0]['evidence']).read_text())
            for sig in previous:
                self.assertIs(signal.getsignal(sig), caller)
        finally:
            agent_process.restore(previous)

    @windows_only
    def test_a_raising_caller_during_restoration_leaves_no_recorder(self):
        import signal
        from unittest.mock import patch
        real_signal, seen = signal.signal, []

        class CallerCancel(Exception):
            pass

        def caller(sig, frame):
            seen.append(sig)
            raise CallerCancel

        previous = agent_process.hold(caller)
        caller_handlers = {sig: signal.getsignal(sig) for sig in previous}
        agent_process.hold(lambda sig, frame: None)  # the adapter's handlers
        fired = []

        def install(sig, handler):
            old = real_signal(sig, handler)
            if sig == signal.SIGINT and handler is caller and not fired:
                fired.append(True)
                signal.raise_signal(signal.SIGINT)
            return old

        try:
            with patch.object(signal, 'signal', side_effect=install), self.assertRaises(CallerCancel):
                agent_process.handing_back(caller_handlers, lambda held: None)
            self.assertEqual(fired, [True])
            with self.assertRaises(CallerCancel):
                signal.raise_signal(signal.SIGTERM)
            self.assertEqual(seen, [signal.SIGINT, signal.SIGTERM])
            for sig, handler in caller_handlers.items():
                self.assertIs(signal.getsignal(sig), handler)
        finally:
            agent_process.restore(previous)

    @windows_only
    def test_a_failure_before_the_first_sample_is_the_error_raised(self):
        # The restoration's clean-up compared what it held with the last sample; with no sample
        # taken yet it raised TypeError and hid the failure itself.
        from unittest.mock import patch

        class Unread(Exception):
            pass

        previous = agent_process.hold(lambda sig, frame: None)
        caller_handlers = dict(previous)
        agent_process.hold(lambda sig, frame: None)  # the adapter's handlers
        try:
            with patch.object(agent_process, 'pending', side_effect=Unread), self.assertRaises(Unread):
                agent_process.handing_back(caller_handlers, lambda held: None)
        finally:
            agent_process.restore(previous)

    @windows_only
    def test_a_scratch_folder_that_cannot_be_removed_never_raises(self):
        # The Codex sandbox writes under another account; a folder this user cannot remove
        # made TemporaryDirectory raise even with ignore_cleanup_errors, and the review was lost.
        import claude_bridge
        user = os.environ['USERNAME']
        with claude_bridge.scratch('kit-scratch-') as path:
            locked = Path(path) / 'locked'
            (locked / 'inner').mkdir(parents=True)
            (locked / 'inner' / 'x.pyc').write_bytes(b'x')
            denied = subprocess.run(['icacls', str(locked), '/deny', '%s:(OI)(CI)F' % user],
                                    capture_output=True, text=True)
            self.assertEqual(denied.returncode, 0, denied.stdout + denied.stderr)
        self.addCleanup(lambda: subprocess.run(['icacls', str(locked), '/remove:d', user], capture_output=True))
        self.addCleanup(lambda: subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', path], capture_output=True))

    @windows_only
    def test_a_guard_inside_an_outer_block_leaves_the_outer_cancel_alone(self):
        # Lead review of the r2 fix: with pending() reading the recorder, a guard leaving inside
        # an outer block found the outer recorder's Ctrl-C and called signal.sigwait, which
        # Windows lacks (AttributeError). The outer cancel is the outer block's to hand on.
        import signal
        mask = agent_process.block_cancels()
        try:
            signal.raise_signal(signal.SIGINT)
            with agent_process.OneShot() as guard:
                pass
            self.assertEqual(guard.noted, [])
        finally:
            with self.assertRaises(KeyboardInterrupt):
                agent_process.restore_mask(mask)
                time.sleep(0.1)  # the handed-on Ctrl-C is raised here at the latest

    @windows_only
    def test_a_missing_reviewer_is_unavailable(self):
        result = agent_process.run([str(self.tmp / 'no-such-cli.exe')], '', self.tmp, 10)
        self.assertEqual(result['termination'], 'unavailable')
        self.assertEqual(result['exit_code'], 127)

    @windows_only
    def test_the_reviewers_copy_is_made_from_the_commit(self):
        # git archive piped into tar: both preparation children are read without select().
        import claude_bridge
        repo = self.tmp / 'repo'
        repo.mkdir()
        git = lambda *a: subprocess.run(['git', '-C', str(repo), *a], check=True, capture_output=True,
                                        text=True).stdout.strip()
        git('init', '-q')
        (repo / 'a.txt').write_text('committed\n')
        git('add', 'a.txt')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'one')
        # A path holding `\\tmp` and `\\new`: Git for Windows' GNU tar read them as escapes.
        copy = self.tmp / 'tmp' / 'new'
        copy.mkdir(parents=True)
        claude_bridge.throwaway_copy(repo, git('rev-parse', 'HEAD'), None, copy, timeout=60)
        self.assertEqual((copy / 'a.txt').read_bytes().replace(b'\r\n', b'\n'), b'committed\n')

    @windows_only
    def test_review_evidence_is_published_and_replaced(self):
        # The first review run on native Windows stopped with PermissionError: the evidence
        # writer opened the folder to fsync it, which Windows refuses.
        import agent_usage
        repo = self.tmp / 'repo'
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        (repo / '.gitignore').write_text('.myagentkit/\n')
        record = repo / '.myagentkit/usage/chains/attempt-1.json'
        agent_usage.write_evidence(repo, record, 'first', private=True)
        self.assertEqual(record.read_text(), 'first')
        agent_usage.write_evidence(repo, record, 'second', private=True, replace=True)
        self.assertEqual(record.read_text(), 'second')
        self.assertEqual(sorted(p.name for p in record.parent.iterdir()), ['attempt-1.json'])

    @windows_only
    def test_the_quota_reader_reads_its_answer_through_a_pipe(self):
        # A stand-in `codex app-server --stdio`: answers initialize, then the rate limits.
        server = self.tmp / 'codex.py'
        server.write_text(
            'import json, sys\n'
            'for line in sys.stdin:\n'
            '    msg = json.loads(line)\n'
            '    if msg.get("id") == 1:\n'
            '        print(json.dumps({"id": 1, "result": {}}), flush=True)\n'
            '    elif msg.get("id") == 2:\n'
            '        print(json.dumps({"id": 2, "result": {"rateLimits": {"limitId": "codex", '
            '"primary": {"usedPercent": 12}}}}), flush=True)\n')
        launcher = self.tmp / 'codex.bat'
        launcher.write_text('@"%s" -I "%s" %%*\r\n' % (sys.executable, server))
        snapshot = codex_quota.snapshot(str(launcher), self.tmp, timeout=20)
        self.assertEqual(snapshot['status'], 'available', json.dumps(snapshot))


if __name__ == '__main__':
    unittest.main()
