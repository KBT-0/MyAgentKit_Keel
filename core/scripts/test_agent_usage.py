"""Usage accounting and bounded-process regressions with no paid CLI calls."""
import json
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
import time
import unittest
import agent_process
import agent_usage
from review_test_support import posix_only, send_cancel


class UsageTests(unittest.TestCase):
    def test_posix_launch_markers_preserve_empty_and_nested_environments(self):
        import os
        from types import SimpleNamespace
        from unittest.mock import patch
        seen = []

        def popen(command, **kwargs):
            seen.append(kwargs['env'])
            return SimpleNamespace()
        with patch.object(agent_process, 'POSIX', True), patch('subprocess.Popen', side_effect=popen), \
                patch.dict(os.environ, {'KIT_ENV_PROBE': 'visible'}, clear=True):
            outer = agent_process.launch(['fixture'], None, env={})
            inner = agent_process.launch(['fixture'], None, env=seen[0])
        self.assertEqual(seen[0], {outer._kit_marker: '1'})
        self.assertEqual(seen[1], {outer._kit_marker: '1', inner._kit_marker: '1'})

    def test_marker_scan_matches_complete_environment_entries_on_both_backends(self):
        import io
        from types import SimpleNamespace
        from unittest.mock import patch
        marker = 'MYAGENTKIT_PROCESS_fixture'
        with patch('os.path.isdir', return_value=True), patch('os.listdir', return_value=['12', '13', 'self']), \
                patch('builtins.open', side_effect=[io.BytesIO((marker + '=1\0OTHER=x').encode()),
                                                   io.BytesIO((marker + '=10\0').encode())]):
            self.assertEqual(agent_process._marked(marker), [12])
        listing = (' 12 python ' + marker + '=1 OTHER=x\n 13 python ' + marker + '=10\n').encode()
        def ps(command, **kwargs):
            # A project's PATH shim must not be able to invent the processes cleanup kills.
            output = listing if command[0] == '/bin/ps' else ('999 shim ' + marker + '=1\n').encode()
            return SimpleNamespace(returncode=0, stdout=output)
        with patch('os.path.isdir', return_value=False), patch('subprocess.run', side_effect=ps):
            self.assertEqual(agent_process._marked(marker), [12])

    def test_marker_scan_keeps_continuation_lines_and_reports_a_failed_ps_once(self):
        # A raw newline in an exported bash function put the marker on a line that names no
        # process: int() raised out of stop_group, and run() raised instead of returning.
        import io
        from types import SimpleNamespace
        from unittest.mock import patch
        marker = 'MYAGENTKIT_PROCESS_abc'
        listing = (' 41 bash BASH_FUNC_f%%=() {  echo hi\n} ' + marker + '=1 OTHER=x\n'
                   ' 42 python ' + marker + '=1\n').encode()
        runs = [SimpleNamespace(returncode=0, stdout=listing)] + [SimpleNamespace(returncode=1, stdout=b'')] * 2
        with patch('os.path.isdir', return_value=False), patch('subprocess.run', side_effect=runs), \
                patch.object(agent_process, '_SCAN_UNAVAILABLE', []), \
                patch('sys.stderr', new_callable=io.StringIO) as stderr:
            self.assertEqual(agent_process._marked(marker), [41, 42])
            # A ps without -E (the BSDs) exits non-zero: no scan, said once, not "none found".
            self.assertEqual(agent_process._marked(marker), [])
            self.assertEqual(agent_process._marked(marker), [])
        self.assertEqual(stderr.getvalue().count('/bin/ps -E failed'), 1, stderr.getvalue())

    def test_the_marker_kill_spares_a_pid_reused_since_the_scan(self):
        # The scan found 41; before the kill it exited and its pid went to an unrelated
        # process. Through a pidfd the environment is read again first: a newcomer without
        # the marker is never signalled, a marked process is, through the pidfd only.
        from types import SimpleNamespace
        from unittest.mock import patch
        child = SimpleNamespace(returncode=0, _kit_marker='MYAGENTKIT_PROCESS_abc', wait=lambda: 0)
        for marked, expected in ((False, []), (True, [(99, 9)])):
            sent, killed, closed = [], [], []
            with self.subTest(marked=marked), patch.object(agent_process, 'POSIX', True), \
                    patch.object(agent_process, '_marked', side_effect=[[41], []]), \
                    patch.object(agent_process, '_holds', return_value=marked), \
                    patch('os.pidfd_open', create=True, return_value=99), patch('os.close', closed.append), \
                    patch('signal.pidfd_send_signal', create=True, side_effect=lambda *a: sent.append(a)), \
                    patch('signal.SIGKILL', 9, create=True), patch('os.kill', side_effect=lambda *a: killed.append(a)), \
                    patch('time.sleep'):
                agent_process.stop_group(child, 41)
                self.assertEqual((sent, killed, closed), (expected, [], [99]))

    def test_private_staging_and_publication_require_ignore_rules(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            ignore = repo / '.gitignore'
            ignore.write_text('/.myagentkit/\n/docs/reviews/*-review.md\n')
            report = repo / 'docs/reviews/fixture-review.md'
            original = tempfile.NamedTemporaryFile

            def capture(*args, **kwargs):
                stream = original(*args, **kwargs)
                result = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--quiet',
                                         stream.name])
                self.assertEqual(result.returncode, 0, 'temporary raw evidence must also be ignored')
                return stream

            with patch.object(agent_usage.tempfile, 'NamedTemporaryFile', side_effect=capture):
                agent_usage.write_evidence(repo, report, 'private output', private=True)
            ignore.write_text('')
            with self.assertRaisesRegex(ValueError, 'Git-ignored'):
                agent_usage.write_evidence(repo, report.with_name('new-review.md'), 'private', private=True)
            self.assertFalse(report.with_name('new-review.md').exists())

    def test_a_failed_replacement_leaves_no_stageable_private_file(self):
        # The cancel relabel staged its replacement as <archive>.cancel, a name no ignore rule
        # matches: a failure before os.replace left raw reviewer output for `git add -A`.
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / '.gitignore').write_text('/.myagentkit/\n/docs/reviews/*-review.md\n')
            report = repo / 'docs/reviews/fixture-review.md'
            agent_usage.write_evidence(repo, report, 'private output', private=True)
            staged, link = [], agent_usage.os.link

            def capture(source, target):
                staged.append(target)
                return link(source, target)

            with patch.object(agent_usage.os, 'link', side_effect=capture), \
                    patch.object(agent_usage.os, 'replace', side_effect=OSError('injected')), \
                    self.assertRaisesRegex(OSError, 'injected'):
                agent_usage.write_evidence(repo, report, 'cancelled output', private=True,
                                           replace=True)
            ignored = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--quiet', '--no-index',
                                      str(staged[0])], capture_output=True)
            self.assertEqual(ignored.returncode, 0, 'replacement staging must be Git-ignored')
            visible = subprocess.run(['git', '-C', str(repo), 'ls-files', '--others',
                                      '--exclude-standard'], capture_output=True, text=True)
            self.assertEqual(visible.stdout.split(), ['.gitignore'])
            self.assertEqual([p.name for p in (repo / '.myagentkit/usage').iterdir()], [],
                             'a failed replacement must remove its staging file')
            self.assertEqual(report.read_text(), 'private output')

    def test_a_cancel_relabel_with_the_archive_momentarily_absent_publishes_its_hash(self):
        # An archive absent when the relabel looked kept the record's old sha256 and was not
        # replaced: the record said cancelled, and the old quota archive put back later
        # matched it, so no integrity check saw the disagreement.
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / '.gitignore').write_text('/.myagentkit/\n/docs/reviews/*-review.md\n')
            report = repo / 'docs/reviews/fixture-review.md'
            old = b'| status | failed |\n| failure_kind | quota |\n'
            agent_usage.write_evidence(repo, report, old.decode(), private=True)
            path, _ = agent_usage.record(repo, 'codex', 'fixture', 'tester', {'id': 'fixture'},
                                         {'stdout': ''}, 'failed', 'quota', str(report), old)
            report.unlink()
            text = '| status | failed |\n| failure_kind | cancelled |\n'
            agent_usage.relabel_cancelled(repo, path, str(report), text)
            recorded = json.loads(path.read_text())['evidence_sha256']
            self.assertEqual(recorded, hashlib.sha256(text.encode()).hexdigest())
            self.assertEqual(report.read_text(), text)
            report.write_bytes(old)
            self.assertNotEqual(hashlib.sha256(report.read_bytes()).hexdigest(), recorded,
                                'the old quota archive matches a record that says cancelled')

    def test_private_storage_cannot_follow_an_in_repo_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / '.gitignore').write_text('/.myagentkit/\n')
            (repo / 'public').mkdir()
            (repo / '.myagentkit').mkdir()
            (repo / '.myagentkit/usage').symlink_to(repo / 'public', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlinked storage'):
                agent_usage.require_private_storage(repo)

    def test_evidence_cannot_overwrite_or_escape_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'repo'
            repo.mkdir()
            report = repo / 'docs/reviews/report.json'
            agent_usage.write_evidence(repo, report, 'first evidence')
            with self.assertRaises(FileExistsError):
                agent_usage.write_evidence(repo, report, 'replacement')
            self.assertEqual(report.read_text(), 'first evidence')
            (repo / 'outside').symlink_to(Path(tmp), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'inside the repository'):
                agent_usage.write_evidence(repo, repo / 'outside/leak.json', 'private')
            self.assertFalse((Path(tmp) / 'leak.json').exists())

    def test_excess_output_is_stopped_without_disk_capture(self):
        from unittest.mock import patch
        original = tempfile.TemporaryFile
        with patch.object(agent_process.tempfile, 'TemporaryFile', wraps=original) as temp_file:
            for fd in (1, 2):
                child = 'import os;\nwhile True: os.write(' + str(fd) + ', b"x" * 65536)'
                result = agent_process.run([sys.executable, '-c', child], '', Path.cwd(), 2)
                self.assertEqual(result['termination'], 'output_limit')
                self.assertLessEqual(len(result['stdout']), 8_000_000)
                self.assertLessEqual(len(result['stderr']), 8_000_000)
            self.assertEqual(temp_file.call_count, 2, 'Only stdin may use a temporary file')

    def test_large_prompt_reaches_a_slow_starting_child_without_deadlock(self):
        child = "import sys,time; time.sleep(0.3); print(len(sys.stdin.read()))"
        result = agent_process.run([sys.executable, "-c", child], "x" * 200000, Path.cwd(), 2)
        self.assertIsNone(result["termination"], result)
        self.assertEqual(result["stdout"].strip(), "200000")

    def test_unknown_usage_is_not_zero_or_a_subscription_estimate(self):
        value = agent_usage.normalize("codex", [], False)
        for key in ["input_tokens", "output_tokens", "api_cost_usd_reported",
                    "subscription_percent_consumed", "credits_used_reported"]:
            self.assertIsNone(value[key])
        for value in [-1, float("inf"), float("nan"), True, "12"]:
            self.assertIsNone(agent_usage.number(value))

    def test_codex_cache_and_reasoning_are_not_added_to_input_and_output(self):
        values = [{"type": "turn.completed", "usage": {"input_tokens": 100,
                   "cached_input_tokens": 90, "output_tokens": 20, "reasoning_output_tokens": 10}}]
        normalized = agent_usage.normalize("codex", values, True)
        self.assertEqual(normalized["input_tokens"], 100)
        self.assertEqual(normalized["output_tokens"], 20)
        self.assertEqual(normalized["reasoning_tokens"], 10)
        self.assertTrue(normalized["input_includes_cache"])

    def test_failure_classification_does_not_read_review_prose(self):
        execution = {"exit_code": 0, "termination": None}
        good = [{"type": "result", "subtype": "success", "is_error": False,
                 "result": "Review found a bug in quota handling and HTTP 429 tests"}]
        self.assertIsNone(agent_usage.failure("claude", execution, good))
        for message, expected in [("context window exceeded", "context_limit"),
                                  ("authentication failed", "authentication"),
                                  ("rate limit exceeded", "quota")]:
            self.assertEqual(agent_usage.failure("codex", execution,
                [{"type": "turn.failed", "error": {"message": message}}]), expected)

    def test_records_are_unique_and_report_filters_without_exposing_raw_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            execution = {"exit_code": 1, "stdout": "private transcript", "stderr": "", "duration_ms": 2}
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / '.gitignore').write_text('/.myagentkit/\n')
            one, _ = agent_usage.record(repo, "codex", "fixture", "claude/fixture", {"id": "one"},
                                       execution, "failed", "quota", None)
            two, _ = agent_usage.record(repo, "codex", "fixture", "claude/fixture", {"id": "two"},
                                       execution, "failed", "quota", None)
            self.assertNotEqual(one, two)
            result = subprocess.run([sys.executable, str(Path(agent_usage.__file__)), "--repo", tmp,
                                     "--task-id", "one", "--json"], capture_output=True, text=True, check=True)
            rows = json.loads(result.stdout)
            self.assertEqual(len(rows), 1)
            self.assertNotIn("private transcript", result.stdout)

    @posix_only
    def test_a_signal_the_caller_ignores_does_not_cancel_the_review(self):
        # nohup ignores SIGHUP and a background job ignores SIGINT; turning either back on
        # cancelled a nohup review the moment its terminal closed.
        import signal
        for sig in (signal.SIGHUP, signal.SIGINT):
            with self.subTest(sig=sig.name):
                previous = signal.signal(sig, signal.SIG_IGN)
                try:
                    child = 'kill -%s $PPID; echo done' % sig.name[3:]
                    result = agent_process.run(['sh', '-c', child], '', Path.cwd(), 5)
                finally:
                    signal.signal(sig, previous)
                self.assertIsNone(result['termination'], result)
                self.assertEqual(result['stdout'].strip(), 'done')

    def test_a_cancel_inside_popen_still_stops_the_reviewer(self):
        # A SIGTERM after Popen created the child but before it returned left no handle:
        # cleanup skipped the group kill while the result said cancelled.
        import os
        import signal
        from unittest.mock import patch
        real = subprocess.Popen
        for when in ('before', 'after'):
            with self.subTest(when=when):
                created = []

                def popen(*args, **kwargs):
                    if args[0][0] == '/bin/ps':
                        return real(*args, **kwargs)  # macOS cleanup scan, not the reviewer launch
                    if when == 'before':
                        send_cancel(signal.SIGTERM)
                    created.append(real(*args, **kwargs))
                    if when == 'after':
                        send_cancel(signal.SIGTERM)
                    return created[-1]

                try:
                    with patch.object(agent_process.subprocess, 'Popen', side_effect=popen):
                        result = agent_process.run([sys.executable, '-c', 'import time; time.sleep(10)'],
                                                   '', Path.cwd(), 5)
                finally:
                    for child in created:
                        if child.poll() is None:
                            child.kill()
                            child.wait()
                            self.fail('the reviewer outlived its cancelled run')
                self.assertEqual(result['termination'], 'cancelled', result)
                self.assertEqual(len(created), 1)
        # The cancel signals are blocked only around Popen in this process: the reviewer
        # starts with none of them blocked.
        if not agent_process.POSIX:
            return  # Windows recorder coverage above; only POSIX has a child signal mask.
        child = 'import signal; print(sorted(int(s) for s in signal.pthread_sigmask(signal.SIG_BLOCK, [])))'
        result = agent_process.run([sys.executable, '-c', child], '', Path.cwd(), 5)
        blocked = json.loads(result['stdout'])
        self.assertFalse({int(s) for s in agent_process.CANCEL_SIGNALS} & set(blocked), blocked)

    @posix_only
    def test_a_cancel_during_cleanup_is_noted_not_raised(self):
        # Raised there, it interrupted the group kill or the reap, and run() returned nothing
        # for the adapter to record.
        import os
        import signal
        from unittest.mock import patch
        real = os.killpg
        stop_self = 'import os,signal,time; os.kill(os.getppid(), signal.SIGTERM); time.sleep(10)'
        for name, child, expected in (('second cancel', stop_self, 'cancelled'),
                                      ('failed review', 'raise SystemExit(3)', 'cancelled'),
                                      ('completed review', 'print("done")', None)):
            with self.subTest(case=name):
                def killpg(pid, sig):
                    send_cancel(signal.SIGTERM)
                    real(pid, sig)
                try:
                    with patch.object(agent_process.os, 'killpg', side_effect=killpg):
                        result = agent_process.run([sys.executable, '-c', child], '', Path.cwd(), 5)
                except KeyboardInterrupt:
                    self.fail('a cancel during cleanup escaped run()')
                self.assertEqual(result['termination'], expected, result)
                self.assertIsNotNone(result['exit_code'], result)
                # A zero exit is not yet a completed review: the cancel is returned either way.
                self.assertTrue(result['cancelled'], result)

    @posix_only
    def test_a_cancel_as_cleanup_begins_is_noted_not_raised(self):
        # Cleanup swapped the raising handlers for noting ones one signal at a time: a cancel
        # before its own handler was swapped still raised, past the group kill and the reap.
        import os
        import signal
        from unittest.mock import patch
        real_popen, real_signal = subprocess.Popen, signal.signal
        stop_self = 'import os,signal,time; os.kill(os.getppid(), signal.SIGTERM); time.sleep(10)'
        for name, child, expected in (('second cancel', stop_self, 'cancelled'),
                                      ('first cancel', 'print("done")', None)):
            with self.subTest(case=name):
                created, sent = [], []

                def popen(*args, **kwargs):
                    if args[0][0] == '/bin/ps':
                        return real_popen(*args, **kwargs)  # macOS cleanup scan, not reviewer
                    created.append(real_popen(*args, **kwargs))
                    return created[-1]

                def install(sig, handler):
                    # The first handler change after the launch is where cleanup begins.
                    if created and not sent:
                        sent.append(sig)
                        send_cancel(signal.SIGTERM)
                    return real_signal(sig, handler)

                try:
                    with patch.object(agent_process.subprocess, 'Popen', side_effect=popen), \
                            patch.object(agent_process.signal, 'signal', side_effect=install):
                        result = agent_process.run([sys.executable, '-c', child], '', Path.cwd(), 5)
                except KeyboardInterrupt:
                    self.fail('a cancel as cleanup began escaped run()')
                finally:
                    for process in created:
                        if process.poll() is None:
                            process.kill()
                            process.wait()
                            self.fail('the reviewer outlived its cancelled run')
                self.assertTrue(sent)
                self.assertEqual(result['termination'], expected, result)
                self.assertTrue(result['cancelled'], result)

    @posix_only
    def test_a_cancel_at_any_line_after_a_completed_wait_keeps_the_review_completed(self):
        # The raising handler stayed armed into the cleanup: a cancel at a signal check before
        # the switch raised inside `finally`, past the group kill, the reap and the result,
        # and one just after a successful wait() turned a completed review into a cancel.
        # Each line boundary of the supervisor after the wait gets the guard's own handler
        # once, the way a signal arriving there would.
        import os
        import signal
        from unittest.mock import patch
        real_popen, code = subprocess.Popen, agent_process._supervise.__code__

        class Popen(real_popen):
            def wait(self, *args, **kwargs):
                value = super().wait(*args, **kwargs)
                waited.append(True)
                return value

        def tracer(frame, event, arg):
            if frame.f_code is not code:
                return None

            def line(frame, event, arg):
                if event == 'line' and waited:
                    seen.append(frame.f_lineno)
                    if len(seen) == target:
                        frame.f_locals['guard'](signal.SIGTERM, None)
                return line
            return line

        target, total = 0, None
        while total is None or target <= total:
            waited, seen, killed = [], [], []
            real_killpg = os.killpg
            with self.subTest(boundary=target), \
                    patch.object(agent_process.subprocess, 'Popen', Popen), \
                    patch.object(agent_process.os, 'killpg',
                                 side_effect=lambda pid, sig: (killed.append(pid), real_killpg(pid, sig))):
                sys.settrace(tracer)
                try:
                    result = agent_process.run([sys.executable, '-c', 'print("done")'], '', Path.cwd(), 5)
                except KeyboardInterrupt:
                    self.fail('a cancel at line %d after the wait escaped run()' % seen[-1])
                finally:
                    sys.settrace(None)
                # agent_process.stop_group: the group once, while its leader is still
                # unreaped (waited for with WNOWAIT); never again after the reap.
                self.assertEqual(killed and len(killed), 1, 'the group kill was skipped')
                self.assertEqual((result['exit_code'], result['termination']), (0, None), result)
                self.assertEqual(result['cancelled'], bool(target), result)
            total = len(seen) if total is None else total
            target += 1
        self.assertGreater(total, 3)

    def test_unavailable_child_is_a_returned_failure_not_an_exception(self):
        result = agent_process.run(["/nonexistent-myagentkit-cli"], "", Path.cwd(), 1)
        self.assertEqual(result["termination"], "unavailable")

    def test_usage_path_cannot_follow_a_symlink_outside_the_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, outside = root / "repo", root / "outside"
            repo.mkdir()
            outside.mkdir()
            (repo / ".myagentkit").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "inside the repository"):
                agent_usage.record(repo, "codex", "fixture", "claude/fixture", {"id": "fixture"},
                                   {"stdout": "", "exit_code": 1}, "failed", "quota", None)
            self.assertFalse((outside / "usage").exists())

    def test_a_cancel_right_after_the_reviewer_exited_keeps_the_review_completed(self):
        # The non-reaping wait leaves returncode unset: a cancel raised in the instant after
        # the exit was seen, before run() recorded it, read as a cancelled run (exit 0,
        # termination cancelled), and a completed review was classified failed. The exit is
        # what counts: run() looks again, without reaping, when a cancel arrives.
        from unittest.mock import patch
        real = agent_process._exited_unreaped
        calls = []

        def exit_seen_then_cancel(child, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                self.assertTrue(real(child, timeout))
                raise KeyboardInterrupt  # the cancel, raised inside the wait
            return real(child, timeout)
        with patch.object(agent_process, '_exited_unreaped', side_effect=exit_seen_then_cancel):
            result = agent_process.run([sys.executable, '-c', 'print("done")'], '', Path.cwd(), 5)
        self.assertEqual((result['exit_code'], result['termination']), (0, None), result)
        self.assertGreaterEqual(len(calls), 2, 'run() did not look again after the cancel')

    def test_timeout_stops_the_process_group_and_keeps_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            descendant = "import time,pathlib; time.sleep(2); pathlib.Path('escaped').write_text('bad')"
            parent = ("import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," +
                      repr(descendant) + "]); print('partial',flush=True); time.sleep(10)")
            result = agent_process.run([sys.executable, "-c", parent], "", repo, 1)
            self.assertEqual(result["termination"], "timeout")
            self.assertIn("partial", result["stdout"])
            time.sleep(1.2)
            self.assertFalse((repo / "escaped").exists())


if __name__ == "__main__":
    unittest.main()
