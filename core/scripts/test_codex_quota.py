"""Quota reads are optional, bounded, non-billing, and never a per-call debit estimate."""
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
import codex_quota
from review_test_support import python_cli, PYTHON_SHEBANG, posix_only

SERVER = PYTHON_SHEBANG + '''import json, pathlib, sys, time
for line in sys.stdin:
    message = json.loads(line)
    method = message['method']
    assert method in ('initialize', 'initialized', 'account/rateLimits/read')
    if method == 'initialize':
        print(json.dumps({'id': 1, 'result': {}}), flush=True)
    if method == 'account/rateLimits/read':
        case = pathlib.Path('case').read_text()
        if case == 'timeout': time.sleep(20)
        if case == 'error': print(json.dumps({'id': 2, 'error': {'message': 'unavailable'}}), flush=True)
        else:
            print(json.dumps({'id': 2, 'result': {'email': 'private@example.invalid',
                'accessToken': 'private-token', 'rateLimitsByLimitId': {'codex': {
                    'planType': 'pro', 'primary': {'usedPercent': 25, 'windowDurationMins': 300,
                                                 'resetsAt': 1800000000}, 'secondary': None}}}}), flush=True)
'''


class QuotaTests(unittest.TestCase):
    def test_reads_only_quota_methods_and_sanitizes_account_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            cli = python_cli(repo / 'codex', SERVER)
            (repo / 'case').write_text('success')
            result = codex_quota.snapshot(str(cli), repo, timeout=2)
            self.assertEqual(result['status'], 'available')
            self.assertEqual(result['buckets']['codex']['primary']['used_percent'], 25)
            self.assertNotIn('private', json.dumps(result))

    def test_unavailable_and_unresponsive_quota_reads_return_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            cli = python_cli(repo / 'codex', SERVER)
            for case in ('error', 'timeout'):
                (repo / 'case').write_text(case)
                result = codex_quota.snapshot(str(cli), repo, timeout=0.3)
                self.assertEqual(result['status'], 'unavailable')
                self.assertEqual(result['buckets'], {})

    def test_a_reader_that_exits_at_once_is_unavailable_not_an_exception(self):
        # The first write met a closed pipe and was caught, but its bytes stayed buffered:
        # stdin.close() in the cleanup flushed them again and raised BrokenPipeError out of
        # snapshot(). Here the app-server has exited before the first write, every time.
        import subprocess
        from unittest.mock import patch
        real_launch = codex_quota.launch

        def exited(*args, **kwargs):
            # Windows Popen starts suspended until launch() attaches the Job Object;
            # waiting inside Popen itself would wait forever before it can be resumed.
            proc = real_launch(*args, **kwargs)
            proc.wait()
            return proc

        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(codex_quota, 'launch', side_effect=exited):
            try:
                cli = python_cli(Path(tmp) / 'exited', PYTHON_SHEBANG + 'raise SystemExit(1)\n')
                result = codex_quota.snapshot(str(cli), Path(tmp), timeout=2)
            except OSError as error:
                self.fail('the quota read raised %r' % error)
        self.assertEqual(result['status'], 'unavailable')

    @posix_only
    def test_a_cancel_inside_the_launch_leaves_no_quota_reader_running(self):
        # The closing read runs under a raising cancel handler: a cancel after the app-server
        # existed but before Popen returned left no handle, and cleanup killed nothing.
        import os
        import signal
        import subprocess
        from unittest.mock import patch
        import agent_process
        real, pids = subprocess.Popen, []

        def launch(*args, **kwargs):
            if args[0][0] == '/bin/ps':
                return real(*args, **kwargs)  # macOS cleanup scan, not the quota reader
            proc = real(*args, **kwargs)
            pids.append(proc.pid)
            os.kill(os.getpid(), signal.SIGTERM)
            return proc

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            cli = python_cli(repo / 'codex', SERVER)
            (repo / 'case').write_text('timeout')
            try:
                with agent_process.OneShot(), patch.object(codex_quota.subprocess, 'Popen', side_effect=launch):
                    codex_quota.snapshot(str(cli), repo, timeout=2)
            except KeyboardInterrupt:
                pass
            self.assertEqual(len(pids), 1)
            try:
                left = os.waitpid(pids[0], os.WNOHANG)[0] == 0
            except ChildProcessError:
                left = False  # reaped by the cleanup
            if left:
                os.killpg(pids[0], signal.SIGKILL)
                os.waitpid(pids[0], 0)
            self.assertFalse(left, 'the quota reader outlived a cancel inside its launch')
            with self.assertRaises(ProcessLookupError):
                os.killpg(pids[0], 0)

    def test_invalid_percent_is_not_zero(self):
        for percent in (-1, True, float('nan'), '25'):
            buckets = codex_quota.sanitize({'rateLimits': {'primary': {'usedPercent': percent}}})
            self.assertIsNone(buckets['codex']['primary'])

    def test_only_a_window_or_credits_make_a_snapshot_available(self):
        # #279: null windows are no observation; an exhausted window above 100 is kept; a null
        # limitId is the codex bucket; credits are kept as numbers and flags only.
        empty = codex_quota.sanitize({'rateLimits': {'limitId': None, 'primary': None}})
        self.assertEqual(list(empty), ['codex'])
        self.assertFalse(codex_quota.has_reading(empty))
        over = codex_quota.sanitize({'rateLimits': {'primary': {'usedPercent': 100.5}}})
        self.assertEqual(over['codex']['primary']['used_percent'], 100.5)
        self.assertTrue(codex_quota.has_reading(over))
        credits = codex_quota.sanitize({'rateLimits': {'credits': {'balance': 12.5, 'hasCredits': True,
                                                                   'account': 'secret'}}})
        self.assertEqual(credits['codex']['credits'], {'balance': 12.5, 'hasCredits': True})
        self.assertTrue(codex_quota.has_reading(credits))


if __name__ == '__main__':
    unittest.main()
