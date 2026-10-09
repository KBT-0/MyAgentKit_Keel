"""The Claude reviewer's shell is sandboxed or absent, and its scratch folders never pile up.

Issue #39. Every case here runs on every host the kit supports, native Windows included: the
paid CLI is never started (agent_process.run is replaced in process), so the command the
adapter would run, its working directory and the records it writes are what is checked.
"""
import argparse
import contextlib
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

    def test_a_scratch_folder_a_killed_adapter_left_is_swept_and_a_live_one_kept(self):
        old = time.time() - claude_bridge.STALE_SCRATCH_SECONDS - 60
        stale, live = self.temp / 'myagentkit-review-stale', self.temp / 'myagentkit-review-live'
        (stale / 'src').mkdir(parents=True)
        (stale / 'src' / 'secret.py').write_text('source\n')
        live.mkdir()
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
        for path in (stale, other, plain, outside):
            os.utime(path, (old, old))
        if link and os.utime in os.supports_follow_symlinks:
            os.utime(link, (old, old), follow_symlinks=False)
        with claude_bridge.scratch('myagentkit-review-') as made:
            self.assertTrue(Path(made).is_dir())
        self.assertFalse(stale.exists(), 'a dead adapter\'s copy stayed behind')
        self.assertTrue(live.is_dir(), 'a live review\'s folder was removed')
        self.assertTrue(other.is_dir(), 'another adapter\'s folder was removed')
        self.assertTrue(plain.is_file())
        self.assertTrue((outside / 'keep.txt').is_file(), 'the sweep followed a symlink')
        if link:
            self.assertTrue(os.path.lexists(link))


if __name__ == '__main__':
    unittest.main()
