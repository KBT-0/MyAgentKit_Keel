"""The Claude reviewer's shell is sandboxed or absent, and its scratch folders never pile up.

Issue #39. Every case here runs on every host the kit supports, native Windows included: the
paid CLI is never started (agent_process.run is replaced in process), so the command the
adapter would run, its working directory and the records it writes are what is checked.
"""
import argparse
import contextlib
import errno
import io
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'core/scripts'))
import claude_bridge  # noqa: E402
import codex_bridge  # noqa: E402

MODEL = 'claude-fixture'


def envelope(mode):
    value = ({'verdict': 'Accept', 'findings': [], 'manual_checks': []} if mode == 'review' else
             {'summary': 'A fix', 'patch': 'diff --git a/a.txt b/a.txt', 'checks': [], 'questions': []})
    return json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False,
                       'modelUsage': {MODEL: {}}, 'structured_output': value})


class ClaudeSandboxTests(unittest.TestCase):
    def setUp(self):
        # A private temporary directory: the sweep and the scratch folders are observed here,
        # never among another session's live reviews.
        self.tmp = Path(tempfile.mkdtemp(prefix='kit-sandbox-test-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.temp = self.tmp / 'temp'
        self.temp.mkdir()
        patcher = patch.object(tempfile, 'tempdir', str(self.temp))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repo = self.tmp / 'repo'
        self.repo.mkdir()
        git = lambda *a: subprocess.run(['git', '-C', str(self.repo), *a], check=True, capture_output=True)
        git('init', '-q')
        git('config', 'core.autocrlf', 'false')
        shutil.copyfile(ROOT / 'core/.gitignore', self.repo / '.gitignore')
        (self.repo / 'README.md').write_text('rules\n')
        (self.repo / 'a.txt').write_text('one\n')
        git('add', '.')
        git('-c', 'user.name=t', '-c', 'user.email=t@t.invalid', '-c', 'core.hooksPath=/dev/null',
            'commit', '-qm', 'one')
        (self.repo / 'a.txt').write_text('two\n')
        (self.repo / 'task.md').write_text('Change a.txt.\n')
        environment = patch.dict(os.environ, CLAUDE_REVIEW_DOCS='["README.md"]', REVIEW_DOCS='README.md',
                                 MYAGENTKIT_DELEGATION_DEPTH='0', MYAGENTKIT_TASK_ID='',
                                 MYAGENTKIT_CAPTURE_QUOTA='0', CLAUDE_CLI_BIN='claude')
        environment.start()
        self.addCleanup(environment.stop)

    def bridge(self, mode, run=None):
        """claude_bridge.main in process, with `run` standing in for the CLI; returns its
        exit code, its result and every launch as (command, working directory, prompt)."""
        launches, results = [], []

        def fake(command, prompt, workdir, timeout, **kw):
            launches.append((command, Path(workdir), prompt,
                             sorted(name for name in os.listdir(self.temp) if name.startswith('myagentkit-'))))
            return {'exit_code': 0, 'stdout': envelope(mode), 'stderr': '', 'termination': None,
                    'cancelled': False, 'duration_ms': 1}
        argv = [mode, '--repo', str(self.repo), '--model', MODEL, '--effort', 'low', '--uncommitted']
        if mode == 'propose':
            argv += ['--task-file', str(self.repo / 'task.md')]
        with patch.object(claude_bridge.agent_process, 'run', run or fake),                 contextlib.redirect_stdout(io.StringIO()):
            code = claude_bridge.main(argv, results.append)
        return code, results[-1] if results else None, launches

    def review(self, bridge, run=None):
        if bridge is claude_bridge:
            return self.bridge('review', run=run)[:2]
        results = []

        def fake(command, *a, **k):
            Path(command[command.index('-o') + 1]).write_text('VERDICT: Accept\n', newline='\n')
            return {'exit_code': 0, 'stdout': '{"type":"turn.completed"}\n', 'stderr': '',
                    'termination': None, 'cancelled': False, 'duration_ms': 1}
        with patch.object(codex_bridge.agent_process, 'run', run or fake), \
                contextlib.redirect_stdout(io.StringIO()):
            code = codex_bridge.main(['--repo', str(self.repo), '--model', 'fixture-codex',
                                      '--uncommitted'], results.append)
        return code, results[-1] if results else None

    def lock_refusal(self, error):
        return patch('msvcrt.locking' if os.name == 'nt' else 'fcntl.flock', side_effect=error)

    def assert_run_os_error_is_recorded(self, bridge):
        # The real run(), failing before its launch: a full TMPDIR. Nothing ran, so the
        # evidence never says the reviewer ran.
        def broken(*a, **k):
            with patch.object(claude_bridge.agent_process.tempfile, 'TemporaryFile',
                              side_effect=OSError(errno.ENOSPC, 'temporary directory full')):
                return real_run(*a, **k)
        real_run = claude_bridge.agent_process.run
        code, result = self.review(bridge, run=broken)
        self.assertEqual(code, 5, result)
        self.assertEqual((result['status'], result['failure_kind']), ('failed', 'run_failed'))
        evidence = Path(result['evidence']).read_text()
        self.assertIn('run_failed', evidence)
        self.assertIn('did not start', evidence)
        self.assertNotIn('ran, then', evidence)
        self.assertNotIn('never ran', evidence)
        record = json.loads(Path(result['usage_record']).read_text())
        self.assertEqual((record['status'], record['failure_kind']), ('failed', 'run_failed'))
        self.assertIn('temporary directory full', record['raw_stderr'])
        self.assertFalse(result['cancelled'])
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_claude_run_os_error_is_recorded_as_run_failed(self):
        self.assert_run_os_error_is_recorded(claude_bridge)

    def test_codex_run_os_error_is_recorded_as_run_failed(self):
        self.assert_run_os_error_is_recorded(codex_bridge)

    def assert_launch_and_prompt_close_errors_are_recorded(self, bridge):
        real_run = bridge.agent_process.run
        temporary_file = tempfile.TemporaryFile

        @contextlib.contextmanager
        def broken_close():
            with temporary_file() as stream:
                yield stream
            raise OSError(errno.EIO, 'prompt close failed')

        def broken(*a, **k):
            with patch.object(bridge.agent_process, 'launch',
                              side_effect=FileNotFoundError('reviewer executable missing')), \
                    patch.object(tempfile, 'TemporaryFile', broken_close):
                return real_run(*a, **k)
        code, result = self.review(bridge, run=broken)
        self.assertEqual((code, result['status'], result['failure_kind']), (5, 'failed', 'run_failed'))
        evidence = Path(result['evidence']).read_text()
        self.assertIn('did not start', evidence)
        self.assertNotIn('ran, then', evidence)
        record = json.loads(Path(result['usage_record']).read_text())
        self.assertEqual((record['status'], record['failure_kind']), ('failed', 'run_failed'))
        self.assertIn('reviewer executable missing', record['raw_stderr'])
        self.assertIn('prompt close failed', record['raw_stderr'])
        self.assertFalse(result['cancelled'])
        self.assertEqual(list(self.temp.iterdir()), [])

    def test_claude_launch_and_prompt_close_errors_do_not_claim_a_run(self):
        self.assert_launch_and_prompt_close_errors_are_recorded(claude_bridge)

    def test_codex_launch_and_prompt_close_errors_do_not_claim_a_run(self):
        self.assert_launch_and_prompt_close_errors_are_recorded(codex_bridge)

    def test_a_run_failed_archive_keeps_only_the_tail_of_stderr(self):
        # Codex once appended the whole stderr (up to 8 MB) to the reviewer's own text.
        def launched_then_broken(command, prompt, workdir, timeout, into, **k):
            into.update(launched=True, exit_code=None, stdout='', stderr='x' * 100_000 + 'END',
                        termination=None, cancelled=False, duration_ms=1)
            raise OSError(errno.EIO, 'supervision broke')
        for bridge in (claude_bridge, codex_bridge):
            with self.subTest(reviewer=bridge.__name__):
                code, result = self.review(bridge, run=launched_then_broken)
                self.assertEqual((code, result['failure_kind']), (5, 'run_failed'), result)
                evidence = Path(result['evidence']).read_text()
                self.assertIn('ran, then its supervision failed', evidence)
                self.assertIn('supervision broke', evidence)
                self.assertLess(len(evidence), 20_000)
                record = json.loads(Path(result['usage_record']).read_text())
                self.assertIn('x' * 100_000 + 'END', record['raw_stderr'])

    def test_scratch_setup_errors_are_recorded_and_leave_no_folder_or_lock(self):
        never = lambda *a, **k: self.fail('the reviewer ran without its copy')
        for bridge in (claude_bridge, codex_bridge):
            for fault in ('mkdtemp', 'lock'):
                with self.subTest(reviewer=bridge.__name__, fault=fault):
                    error = OSError(errno.EACCES, 'scratch setup denied')
                    if fault == 'mkdtemp':
                        original = tempfile.mkdtemp

                        def denied(*a, **k):
                            if k.get('prefix', '').startswith('myagentkit-'):
                                raise error
                            return original(*a, **k)
                        refusal = patch.object(tempfile, 'mkdtemp', side_effect=denied)
                    else:
                        refusal = self.lock_refusal(error)
                    with refusal:
                        code, result = self.review(bridge, run=never)
                    self.assertEqual(code, 5, result)
                    self.assertEqual(result['failure_kind'], 'copy_failed')
                    self.assertTrue(Path(result['evidence']).is_file())
                    record = json.loads(Path(result['usage_record']).read_text())
                    self.assertEqual(record['failure_kind'], 'copy_failed')
                    self.assertEqual(list(self.temp.iterdir()), [], 'scratch setup leaked')

    def test_a_temp_filesystem_that_refuses_locks_fails_the_review_with_a_record(self):
        # The owner's decision (2026-10-11): no age-only fallback; macOS refuses with ENOTSUP.
        refusals = {errno.ENOLCK, errno.EOPNOTSUPP, errno.ENOSYS, getattr(errno, 'ENOTSUP', errno.ENOLCK)}
        never = lambda *a, **k: self.fail('the reviewer ran without a lifetime lock')
        for bridge in (claude_bridge, codex_bridge):
            for refused in sorted(refusals):
                with self.subTest(reviewer=bridge.__name__, errno=refused), \
                        self.lock_refusal(OSError(refused, 'no locks')):
                    code, result = self.review(bridge, run=never)
                self.assertEqual(code, 5, result)
                self.assertEqual(result['failure_kind'], 'copy_failed')
                record = json.loads(Path(result['usage_record']).read_text())
                self.assertEqual(record['failure_kind'], 'copy_failed')
                self.assertIn('set TMPDIR to a filesystem with lock support', record['raw_stderr'])
                self.assertEqual(list(self.temp.iterdir()), [])

    def test_lockless_scratch_folders_are_never_made_or_swept_by_age(self):
        old = time.time() - claude_bridge.STALE_SCRATCH_SECONDS - 60
        for prefix in ('myagentkit-review-', 'myagentkit-codex-'):
            with self.subTest(prefix=prefix):
                folder = self.temp / (prefix + 'old')
                folder.mkdir()
                with claude_bridge.scratch_lock(str(folder), create=True):
                    pass
                os.utime(folder, (old, old))
                with self.lock_refusal(OSError(errno.ENOLCK, 'no locks')):
                    with self.assertRaises(OSError) as refused:
                        with claude_bridge.scratch(prefix):
                            self.fail('a scratch folder was made without its lock')
                self.assertIn('lock support', str(refused.exception))
                self.assertTrue(folder.is_dir(), 'an old copy was swept by age alone')
                self.assertEqual(sorted(p.name for p in self.temp.iterdir()),
                                 sorted([folder.name, folder.name + '.lock']))
                shutil.rmtree(folder)
                os.unlink(str(folder) + '.lock')

    def test_a_foreign_marker_is_kept_and_another_folder_picked(self):
        original = claude_bridge.scratch_lock
        planted = []

        def planting(times):
            def lock(path, create=False):
                if create and len(planted) < times:
                    # Another account creates the marker between mkdtemp and the O_EXCL open.
                    Path(path + '.lock').write_text('foreign marker')
                    planted.append(Path(path + '.lock'))
                return original(path, create)
            return lock
        for times, code_wanted in ((1, 0), (claude_bridge.SCRATCH_ATTEMPTS, 5)):
            for bridge in (claude_bridge, codex_bridge):
                with self.subTest(collisions=times, reviewer=bridge.__name__):
                    planted.clear()
                    with patch.object(claude_bridge, 'scratch_lock', planting(times)):
                        code, result = self.review(bridge)
                    self.assertEqual(code, code_wanted, result)
                    if code_wanted:
                        self.assertEqual(result['failure_kind'], 'copy_failed')
                    self.assertEqual(len(planted), times)
                    for marker in planted:
                        self.assertEqual(marker.read_text(), 'foreign marker', 'a foreign marker was removed')
                        marker.unlink()
                    self.assertEqual(list(self.temp.iterdir()), [], 'scratch setup leaked')

    def test_cli_readiness_has_one_probe_budget_and_a_clean_missing_line(self):
        clock = [0.0]
        timeouts = []

        def hung(command, timeout, **kw):
            timeouts.append(timeout)
            clock[0] += timeout
            raise subprocess.TimeoutExpired(command, timeout)
        paths = os.pathsep.join('dir%d' % n for n in range(5))
        with patch.object(claude_bridge.shutil, 'which', side_effect=lambda name, path: path + '-cli'), \
                patch.object(claude_bridge.time, 'monotonic', lambda: clock[0]), \
                patch.object(claude_bridge.subprocess, 'run', side_effect=hung):
            self.assertIn('timed out', claude_bridge.cli_readiness({'PATH': paths}))
        self.assertLessEqual(sum(timeouts), claude_bridge.PROBE_BUDGET_SECONDS)
        with patch.object(claude_bridge.shutil, 'which', return_value='broken-cli'), \
                patch.object(claude_bridge.subprocess, 'run', side_effect=OSError('bad | pipe\nnext line')):
            problem = claude_bridge.cli_readiness({'CLAUDE_CLI_BIN': 'broken-cli', 'PATH': ''})
        what, fix = problem.split('|', 1)
        self.assertNotIn('\n', problem)
        self.assertIn('bad', what)
        self.assertIn('next line', what)
        self.assertIn('reinstall', fix)

    def test_cli_readiness_names_a_candidate_the_budget_cut_short(self):
        # A first claude hangs 60 seconds; the second answers in 40 but has 30 left. It is
        # named, never hidden behind 'check claude --help'.
        clock = [0.0]

        def slow(command, timeout, **kw):
            needed = 1000 if command[0] == 'hung-cli' else 40
            clock[0] += min(timeout, needed)
            raise subprocess.TimeoutExpired(command, timeout)
        with patch.object(claude_bridge.shutil, 'which',
                          side_effect=lambda name, path: 'slow-cli' if path == 'slow' else 'hung-cli'),                 patch.object(claude_bridge.time, 'monotonic', lambda: clock[0]),                 patch.object(claude_bridge.subprocess, 'run', side_effect=slow):
            problem = claude_bridge.cli_readiness({'PATH': os.pathsep.join(['hung', 'slow'])})
        self.assertIn('slow-cli', problem.split('|', 1)[1])

    def test_cli_readiness_probes_each_path_only_once(self):
        paths = os.pathsep.join(['first', 'later', 'later'])
        with patch.object(claude_bridge.shutil, 'which',
                          side_effect=lambda name, path: 'later-cli' if path == 'later' else 'hung-cli'), \
                patch.object(claude_bridge.subprocess, 'run',
                             side_effect=subprocess.TimeoutExpired('cli', 60)) as run:
            self.assertIn('timed out', claude_bridge.cli_readiness({'PATH': paths}))
        self.assertEqual([call.args[0] for call in run.call_args_list],
                         [['hung-cli', '--help'], ['later-cli', '--help']])

    def test_sweep_keeps_a_young_folder_with_an_unheld_lock(self):
        folder = self.temp / 'myagentkit-review-young'
        folder.mkdir()
        with claude_bridge.scratch_lock(str(folder), create=True):
            pass
        claude_bridge.sweep('myagentkit-review-')
        self.assertTrue(folder.is_dir(), 'the sweep removed a copy before its lock was acquired')
        self.assertTrue(Path(str(folder) + '.lock').is_file())

    def test_sweep_removes_only_old_unheld_orphan_lock_files(self):
        old = time.time() - claude_bridge.STALE_SCRATCH_SECONDS - 60
        orphan = self.temp / 'myagentkit-review-orphan'
        held = self.temp / 'myagentkit-review-held'
        young = self.temp / 'myagentkit-review-young.lock'
        young.write_bytes(b'0')
        with claude_bridge.scratch_lock(str(orphan), create=True):
            pass
        os.utime(str(orphan) + '.lock', (old, old))
        with claude_bridge.scratch_lock(str(held), create=True):
            os.utime(str(held) + '.lock', (old, old))
            claude_bridge.sweep('myagentkit-review-')
            self.assertFalse(Path(str(orphan) + '.lock').exists())
            self.assertTrue(Path(str(held) + '.lock').is_file(), 'a held orphan lock was removed')
            self.assertTrue(young.is_file(), 'a young orphan lock was removed')
        claude_bridge.sweep('myagentkit-review-')
        self.assertFalse(Path(str(held) + '.lock').exists())

    def test_the_review_command_sandboxes_bash_or_offers_none(self):
        for sandboxed in (True, False):
            for mode in ('review', 'propose'):
                with self.subTest(sandboxed=sandboxed, mode=mode):
                    args = argparse.Namespace(mode=mode, model=MODEL, effort='low', max_turns=5,
                                              max_budget_usd=None)
                    command, tools = claude_bridge.claude_command('claude', args, sandboxed)
                    offered = command[command.index('--tools') + 1]
                    self.assertEqual(offered, ','.join(tools))
                    self.assertIn('--restricted', command)
                    if mode == 'review' and sandboxed:
                        self.assertEqual(offered, 'Read,Glob,Grep,Bash')
                        settings = json.loads(command[command.index('--settings') + 1])['sandbox']
                        self.assertIs(settings['enabled'], True)
                        self.assertIs(settings['failIfUnavailable'], True)
                        self.assertIs(settings['allowUnsandboxedCommands'], False)
                        self.assertEqual(settings['network'], {'allowedDomains': [], 'strictAllowlist': True})
                        self.assertNotIn('filesystem', settings)  # writes: the copy and the temp dir only
                    else:
                        # No host without a sandbox, and no proposal, is offered a shell.
                        self.assertEqual(offered, 'Read,Glob,Grep')
                        self.assertNotIn('Bash', ' '.join(command))
                        self.assertNotIn('--settings', command)

    def test_a_review_on_this_host_gets_a_sandboxed_shell_or_none(self):
        code, result, launches = self.bridge('review')
        self.assertEqual(code, 0, result)
        [(command, workdir, prompt, _)] = launches
        self.assertFalse(workdir.resolve().is_relative_to(self.repo.resolve()))
        header = Path(result['evidence']).read_text()
        if os.name == 'posix':
            self.assertIn('--settings', command)
            self.assertIn('run anything inside this copy', prompt)
            self.assertIn('Claude Code Bash sandbox', header)
        else:
            self.assertEqual(command[command.index('--tools') + 1], 'Read,Glob,Grep')
            self.assertNotIn('Bash', ' '.join(command))
            self.assertNotIn('run anything', prompt)
            self.assertIn('You have no shell on this host', prompt)
            self.assertIn('no Bash: native Windows', header)

    def test_a_proposal_makes_no_scratch_folder(self):
        code, result, launches = self.bridge('propose')
        self.assertEqual(code, 0, result)
        [(_, workdir, _, scratch)] = launches
        self.assertEqual(workdir, self.repo)
        self.assertEqual(scratch, [])

    def test_a_copy_that_cannot_be_made_is_a_recorded_failure_for_either_reviewer(self):
        def broken(*args, **kwargs):
            raise claude_bridge.BridgeError('the copy for the reviewer differs from the checkout at a.txt')
        never = lambda *a, **k: self.fail('the reviewer ran without its copy')
        with patch.object(claude_bridge, 'throwaway_copy', broken):
            code, result, _ = self.bridge('review', run=never)
        self.assertEqual(code, 5, result)
        self.assertEqual(result['failure_kind'], 'copy_failed')
        self.assertIn('differs from the checkout', result['error'])
        record = json.loads(Path(result['usage_record']).read_text())
        self.assertEqual((record['status'], record['failure_kind']), ('failed', 'copy_failed'))
        results = []
        with patch.object(codex_bridge, 'throwaway_copy', broken), \
                patch.object(codex_bridge.agent_process, 'run', never),                 contextlib.redirect_stdout(io.StringIO()):
            code = codex_bridge.main(['--repo', str(self.repo), '--model', 'fixture-codex',
                                      '--uncommitted'], results.append)
        self.assertEqual(code, 5)
        self.assertEqual(results[-1]['failure_kind'], 'copy_failed')
        self.assertTrue(Path(results[-1]['usage_record']).is_file())

    def test_a_sandbox_that_cannot_start_is_a_setup_fault_never_a_fallback(self):
        # Claude Code's own words when failIfUnavailable stops it (seen live on native Windows).
        stderr = ('\nError: sandbox required but unavailable: sandbox is enabled but the Windows '
                  'sandbox is not active on this session (feature gate off)\n  '
                  'sandbox.failIfUnavailable is set — refusing to start without a working sandbox.\n')
        stopped = lambda *a, **k: {'exit_code': 1, 'stdout': '', 'stderr': stderr, 'termination': None,
                                   'cancelled': False, 'duration_ms': 1}
        code, result, _ = self.bridge('review', run=stopped)
        self.assertEqual(code, 5, result)
        self.assertEqual(result['failure_kind'], 'sandbox_unavailable')
        import review_dispatch
        self.assertNotIn('sandbox_unavailable', review_dispatch.UNAVAILABLE)

    def test_copy_os_errors_are_recorded_for_both_reviewers(self):
        never = lambda *a, **k: self.fail('the reviewer ran without its copy')
        for error in (FileNotFoundError('tar is missing'), PermissionError('copy is denied')):
            for bridge in (claude_bridge, codex_bridge):
                with self.subTest(error=type(error).__name__, reviewer=bridge.__name__):
                    results = []
                    with patch.object(bridge, 'throwaway_copy', side_effect=error), \
                            patch.object(bridge.agent_process, 'run', never), \
                            contextlib.redirect_stdout(io.StringIO()):
                        if bridge is claude_bridge:
                            code, result, _ = self.bridge('review', run=never)
                        else:
                            code = bridge.main(['--repo', str(self.repo), '--model', 'fixture-codex',
                                                '--uncommitted'], results.append)
                            result = results[-1] if results else None
                    self.assertEqual(code, 5, result)
                    self.assertEqual(result['failure_kind'], 'copy_failed')
                    evidence = Path(result['evidence']).read_text()
                    self.assertIn('copy_failed', evidence)
                    record = json.loads(Path(result['usage_record']).read_text())
                    self.assertEqual((record['status'], record['failure_kind']), ('failed', 'copy_failed'))
                    self.assertIn(str(error), record['raw_stderr'])
                    self.assertNotIn('copy_failed', __import__('review_dispatch').UNAVAILABLE)

    def test_cli_readiness_reports_help_launch_failure(self):
        with patch.object(claude_bridge.shutil, 'which', return_value='broken-cli'), \
                patch.object(claude_bridge.subprocess, 'run', side_effect=OSError('invalid executable')):
            problem = claude_bridge.cli_readiness({'CLAUDE_CLI_BIN': 'broken-cli', 'PATH': ''})
        self.assertIsNotNone(problem)
        self.assertIn('cannot launch', problem)
        self.assertIn('invalid executable', problem)
        self.assertIn('|', problem)
        fix = problem.split('|', 1)[1]
        self.assertIn('reinstall', fix)
        self.assertIn('working executable', fix)
        self.assertNotIn('claude update', fix)

    def test_cli_readiness_reports_help_timeout(self):
        with patch.object(claude_bridge.shutil, 'which', return_value='hung-cli'), \
                patch.object(claude_bridge.subprocess, 'run',
                             side_effect=subprocess.TimeoutExpired('hung-cli', 60)):
            problem = claude_bridge.cli_readiness({'CLAUDE_CLI_BIN': 'hung-cli', 'PATH': ''})
        self.assertIsNotNone(problem)
        self.assertIn('timed out', problem)
        self.assertIn('|', problem)
        fix = problem.split('|', 1)[1]
        self.assertIn('first-run', fix)
        self.assertIn('retry', fix)
        self.assertNotIn('claude update', fix)

    def test_sweep_keeps_a_live_copy_with_an_old_directory_timestamp(self):
        old = time.time() - claude_bridge.STALE_SCRATCH_SECONDS - 60
        for prefix in ('myagentkit-review-', 'myagentkit-codex-'):
            with self.subTest(prefix=prefix), claude_bridge.scratch(prefix) as live:
                (Path(live) / 'source.txt').write_text('keep\n')
                # Archive extraction can restore this timestamp while the review runs.
                os.utime(live, (old, old))
                command = ('import sys, tempfile; sys.path.insert(0, sys.argv[1]); '
                           'import claude_bridge; tempfile.tempdir = sys.argv[2]; '
                           'claude_bridge.sweep(sys.argv[3])')
                subprocess.run([sys.executable, '-B', '-c', command, str(ROOT / 'core/scripts'),
                                str(self.temp), prefix], check=True, capture_output=True, timeout=10)
                self.assertTrue(Path(live).is_dir(), 'another process swept a live review')
                with claude_bridge.scratch(prefix):
                    self.assertTrue((Path(live) / 'source.txt').is_file(), 'a live copy was swept')
            self.assertFalse(Path(live).exists())

    def test_a_scratch_folder_a_killed_adapter_left_is_swept_and_a_live_one_kept(self):
        old = time.time() - claude_bridge.STALE_SCRATCH_SECONDS - 60
        command = ('import os, sys, tempfile; sys.path.insert(0, sys.argv[1]); '
                   'import claude_bridge; tempfile.tempdir = sys.argv[2]; '
                   'context = claude_bridge.scratch("myagentkit-review-"); '
                   'print(context.__enter__(), flush=True); os._exit(0)')
        dead = subprocess.run([sys.executable, '-B', '-c', command, str(ROOT / 'core/scripts'),
                               str(self.temp)], check=True, capture_output=True, text=True, timeout=10)
        stale, live = Path(dead.stdout.strip()), self.temp / 'myagentkit-review-live'
        (stale / 'src').mkdir()
        (stale / 'src' / 'secret.py').write_text('source\n')
        live.mkdir()
        legacy = self.temp / 'myagentkit-review-unmarked'
        legacy.mkdir()
        other = self.temp / 'myagentkit-codex-stale'
        other.mkdir()
        plain = self.temp / 'myagentkit-review-file'
        plain.write_text('not a folder\n')
        outside = self.tmp / 'outside'
        outside.mkdir()
        (outside / 'keep.txt').write_text('keep\n')
        link = self.temp / 'myagentkit-review-link'
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError:
            link = None  # Windows without the symlink privilege
        for path in (stale, legacy, other, plain, outside):
            os.utime(path, (old, old))
        if link and os.utime in os.supports_follow_symlinks:
            os.utime(link, (old, old), follow_symlinks=False)
        with claude_bridge.scratch('myagentkit-review-') as made:
            self.assertTrue(Path(made).is_dir())
        self.assertFalse(stale.exists(), 'a dead adapter\'s copy stayed behind')
        self.assertFalse(Path(str(stale) + '.lock').exists())
        self.assertTrue(legacy.is_dir(), 'age alone cannot prove an unmarked copy is dead')
        self.assertTrue(live.is_dir(), 'a live review\'s folder was removed')
        self.assertTrue(other.is_dir(), 'another adapter\'s folder was removed')
        self.assertTrue(plain.is_file())
        self.assertTrue((outside / 'keep.txt').is_file(), 'the sweep followed a symlink')
        if link:
            self.assertTrue(os.path.lexists(link))


if __name__ == '__main__':
    unittest.main()
