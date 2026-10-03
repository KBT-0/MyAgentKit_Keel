"""Offline end-to-end evidence and permission regressions; never calls a paid CLI."""
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent_usage

ROOT = Path(__file__).resolve().parent
INHERITED_CONTROLS = ('REVIEW_DISPOSITIONS', 'MYAGENTKIT_TASK_ID', 'MYAGENTKIT_REVIEW_CHAIN_ID',
                      'MYAGENTKIT_REVIEW_ATTEMPT', 'MYAGENTKIT_REVIEW_FALLBACK_FROM',
                      'MYAGENTKIT_REQUESTER', 'CLAUDE_REVIEW_DOCS')
# Per suite, not a combined total: as one suite grew, an emptied neighbour could hide inside
# the sum and the self-test passed without running its checks. The kit gate reads this too.
SUITE_MINIMUMS = {'test_claude_bridge': 60, 'test_agent_usage': 12, 'test_codex_quota': 3}
BRIDGE = ROOT / "claude_bridge.py"
spec = importlib.util.spec_from_file_location("bridge", BRIDGE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

FIXTURE = '''#!/usr/bin/env python3
import json, os, pathlib, sys, time
args = sys.argv[1:]
assert args[args.index('--tools') + 1] == 'Read,Glob,Grep'
assert args[args.index('--permission-mode') + 1] == 'dontAsk'
assert '--safe-mode' in args and '--restricted' in args
assert '--strict-mcp-config' in args and '--no-session-persistence' in args
assert '--dangerously-skip-permissions' not in args
assert '--resume' not in args and '--continue' not in args
assert os.environ['MYAGENTKIT_DELEGATION_DEPTH'] == '1'
prompt = sys.stdin.read()
if os.environ.get('PROMPT_LOG'): pathlib.Path(os.environ['PROMPT_LOG']).write_text(prompt)
case = os.environ.get('FIXTURE_CASE', 'accept')
model = args[args.index('--model') + 1]
if case == 'unknown_flag': sys.stderr.write("error: unknown option '--restricted'\\n"); sys.exit(1)
if case == 'no_budget': assert '--max-budget-usd' not in args
if case == 'malformed_envelope': print('{}'); sys.exit(0)
if case == 'explicit_budget': assert args[args.index('--max-budget-usd') + 1] == '7.5'
value = {'verdict': 'Accept', 'findings': [], 'manual_checks': []}
result = {'type': 'result', 'subtype': 'success', 'is_error': False,
          'modelUsage': {model: {}}, 'structured_output': value}
result['usage'] = {'input_tokens': 7, 'cache_read_input_tokens': 100,
                   'cache_creation_input_tokens': 20, 'output_tokens': 11}
result['total_cost_usd'] = 0.123
if case == 'reject': value.update(verdict='Reject', findings=['file.py:1: concrete defect'])
if case == 'manual': value.update(verdict='Accept with Manual Checks', manual_checks=['Verify deployment.'])
if case == 'missing': result.pop('structured_output')
if case == 'transcript': print('VERDICT: Accept'); sys.exit(0)
if case == 'conflict': value['findings'] = ['Unresolved defect.']
if case == 'turns': result['subtype'] = 'error_max_turns'
if case == 'model': result['modelUsage'] = {'different-model': {}}
if case == 'error': result['is_error'] = True
if case == 'exit': print(json.dumps(result)); sys.exit(9)
if case == 'mutation': pathlib.Path('file.py').write_text('changed during review')
if case == 'kit_docs': assert 'core/docs/ARCHITECTURE.md' in prompt
if case == 'archive_failure':
    pathlib.Path('docs/reviews').rmdir()
    pathlib.Path('docs/reviews').write_text('blocked archive')
if case == 'timeout': time.sleep(20)
if case == 'partial_timeout': print(json.dumps(result), flush=True); time.sleep(20)
if case == 'quota':
    result.update(is_error=True, api_error_status=429, result='Session limit reached; resets later')
    print(json.dumps(result)); sys.exit(1)
if case in ('auth', 'context'):
    result.update(is_error=True, result='authentication failed' if case == 'auth' else 'context exhausted')
    print(json.dumps(result)); sys.exit(1)
if case == 'quota_mutation':
    pathlib.Path('file.py').write_text('changed while failing')
    result.update(is_error=True, api_error_status=429)
    print(json.dumps(result)); sys.exit(1)
if case == 'chain_failure':
    import shutil
    shutil.rmtree('.myagentkit/usage/chains')
    pathlib.Path('.myagentkit/usage/chains').write_text('blocked chain')
    result.update(is_error=True, api_error_status=429)
    print(json.dumps(result)); sys.exit(1)
if case == 'proposal':
    result['structured_output'] = {'summary': 'Proposed fix', 'patch': 'diff --git a/file.py b/file.py',
                                  'checks': ['NOT RUN: project gate'], 'questions': []}
if case == 'questions':
    result['structured_output'] = {'summary': 'Decision needed', 'patch': '', 'checks': [],
                                  'questions': ['Which public contract is intended?']}
print(json.dumps(result))
'''

HANGING_CLI = '''#!/usr/bin/env python3
import os, subprocess, sys, time
sys.stdin.read()
alive = os.open(os.environ['ALIVE_FIFO'], os.O_WRONLY)
subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], pass_fds=(alive,))
os.write(alive, b'started\\n')
time.sleep(60)
'''


def header_of(path):
    """Parse the shared evidence header table. Both reviewers must satisfy this reader."""
    rows = {}
    for line in Path(path).read_text().splitlines():
        if line.startswith("| ") and " | " in line[2:]:
            key, _, value = line.strip("| ").partition(" | ")
            rows[key.strip()] = value.strip()
    rows.pop("field", None)   # the table heading
    rows.pop("---", None)     # its separator row
    return rows


def verdicts_of(path):
    return [line for line in Path(path).read_text().splitlines() if line.startswith("VERDICT: ")]


class BridgeTests(unittest.TestCase):
    def test_review_timeout_defaults_and_explicit_overrides(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import agent_process
        import codex_bridge
        import review_dispatch

        class CapturedLaunch(RuntimeError):
            pass

        observed = []

        def capture(command, prompt, repo, timeout, into=None):
            observed.append(timeout)
            raise CapturedLaunch()  # No CLI or wall-clock wait is needed.

        cases = [(bridge.main, ['review'], None, 1800),
                 (bridge.main, ['review', '--timeout', '77'], None, 77),
                 (codex_bridge.main, ['--model', 'fixture-codex-model'], None, 1800),
                 (codex_bridge.main, ['--model', 'fixture-codex-model'], '88', 88),
                 (review_dispatch.main, ['--reviewer', 'claude'], None, 1800),
                 (review_dispatch.main, ['--reviewer', 'codex'], None, 1800),
                 (review_dispatch.main, ['--reviewer', 'claude'], '99', 99),
                 (review_dispatch.main, ['--reviewer', 'codex'], '99', 99)]
        for main, argv, override, expected in cases:
            with self.subTest(entry=main.__module__, args=argv, override=override):
                with patch.dict(os.environ, self.review_env(REVIEW_CLAUDE_MODEL='claude-opus-5',
                                                           REVIEW_CODEX_MODEL='fixture-codex-model')):
                    os.environ.pop('REVIEW_TIMEOUT_SECONDS', None)
                    if override is not None:
                        os.environ['REVIEW_TIMEOUT_SECONDS'] = override
                    with patch.object(agent_process, 'run', side_effect=capture), redirect_stdout(StringIO()):
                        with self.assertRaises(CapturedLaunch):
                            main([*argv, '--repo', str(self.repo)])
                    self.assertEqual(observed[-1], expected)

    def test_review_has_no_default_budget_but_honors_an_explicit_limit(self):
        for case, extra, expected in [('no_budget', [], None),
                                      ('explicit_budget', ['--max-budget-usd', '7.5'], 7.5)]:
            code, result = self.run_bridge(case, extra=extra)
            self.assertEqual(code, 0, result)
            self.assertIn(str(expected) if expected else "no cap",
                          header_of(result["evidence"])["limits"])
        for invalid in ['0', '-1', 'nan', 'inf']:
            code, result = self.run_bridge(extra=['--max-budget-usd', invalid])
            self.assertEqual(code, 2, result)

    def setUp(self):
        # run_bridge() and review_env() copy os.environ: history and chain controls exported
        # by the invoking shell (a review loop's dispositions and label) must not reach a
        # synthetic repository. A test that needs one passes it explicitly.
        from unittest.mock import patch
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for name in INHERITED_CONTROLS:
            os.environ.pop(name, None)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "project"
        self.repo.mkdir()
        self.fixture = self.root / "claude"
        self.fixture.write_text(FIXTURE)
        self.fixture.chmod(0o755)
        self.git("init", "-q")
        (self.repo / '.gitignore').write_bytes((ROOT.parent / '.gitignore').read_bytes())
        for name in ["AGENTS.md", "docs/PHASES.md", "docs/ARCHITECTURE.md", "docs/REVIEW_GATE.md"]:
            path = self.repo / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("Synthetic project guidance.\n")
        (self.repo / "file.py").write_text("original\n")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture")
        (self.repo / "file.py").write_text("changed\n")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def commit_fixture(self, message):
        self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-qm', message)

    def test_diff_drivers_cannot_hide_source_and_fingerprints_read_raw_bytes(self):
        source = self.repo / 'file.py'
        source.write_text('stable\nold\n')
        (self.repo / '.gitattributes').write_text('file.py diff=hide\n')
        self.commit_fixture('Diff driver fixture')
        self.git('config', 'diff.hide.textconv', 'head -n 1')
        source.write_text('stable\nNEW_SOURCE_CONTENT\n')
        (self.repo / 'visible.txt').write_text('visible change\n')
        self.assertIn('NEW_SOURCE_CONTENT', bridge.snapshot(self.repo, 'uncommitted', None)[2])
        self.git('config', '--unset', 'diff.hide.textconv')
        converter = self.root / 'external-diff'
        marker = self.root / 'external-called'
        converter.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nprintf "HIDDEN\\n"\n')
        converter.chmod(0o755)
        self.git('config', 'diff.hide.command', str(converter))
        self.assertIn('NEW_SOURCE_CONTENT', bridge.snapshot(self.repo, 'uncommitted', None)[2])
        self.assertFalse(marker.exists())
        self.git('update-index', '--assume-unchanged', 'file.py')
        with self.assertRaisesRegex(bridge.BridgeError, 'index flags'):
            bridge.snapshot(self.repo, 'uncommitted', None)

    def test_clean_filters_and_ident_cannot_hide_working_tree_source(self):
        # A clean filter rewrites working-tree bytes before Git diffs them, so the payload
        # lost the unsafe line (or file) while the fingerprint still hashed the raw bytes.
        (self.repo / 'file.py').write_text('SAFE\n')
        (self.repo / '.gitattributes').write_text('*.py filter=hide\n')
        self.commit_fixture('Clean filter fixture')
        (self.repo / 'file.py').write_text('SAFE\nUNSAFE_PARTIAL_HUNK\n')
        (self.repo / 'bypass.py').write_text('UNSAFE_WHOLE_FILE\n')
        (self.repo / 'visible.txt').write_text('visible change\n')
        diff = bridge.snapshot(self.repo, 'uncommitted', None)[2]
        self.assertIn('UNSAFE_PARTIAL_HUNK', diff)   # control: an unconfigured driver filters nothing
        self.assertIn('UNSAFE_WHOLE_FILE', diff)
        self.git('config', 'filter.hide.clean', "sed '/UNSAFE/d'")
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on bypass.py'):
            bridge.snapshot(self.repo, 'uncommitted', None)
        for provider, variable in (('claude', 'CLAUDE_CLI_BIN'), ('codex', 'REVIEW_CLI_BIN')):
            with self.subTest(provider=provider):
                result, chain = self.dispatch_result(provider, **{variable: str(self.root / 'NOT-LAUNCHED')})
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIsNone(chain)
                self.assertIn('clean filter or ident attribute', result.stdout)
        # A whitespace-only command is a shell no-op that empties the file for the diff: a
        # configured key is a filter whatever its value.
        self.git('config', 'filter.hide.clean', ' ')
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on bypass.py'):
            bridge.snapshot(self.repo, 'uncommitted', None)
        self.git('config', '--unset', 'filter.hide.clean')
        (self.repo / '.gitattributes').write_text('file.py ident\n')
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on file.py'):
            bridge.snapshot(self.repo, 'uncommitted', None)

    def test_direct_adapters_reject_a_base_ref_that_moves_during_review(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import codex_bridge
        original = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        self.commit_fixture('Intermediate revision')
        intermediate = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        (self.repo / 'file.py').write_text('final\n')
        self.commit_fixture('Reviewed revision')
        for main, args in ((bridge.main, ['review']),
                           (codex_bridge.main, ['--model', 'fixture-codex-model'])):
            self.git('update-ref', 'refs/heads/review-base', original)

            def execution(command, prompt, repo, timeout, into=None):
                self.git('update-ref', 'refs/heads/review-base', intermediate)
                if '-o' in command:
                    Path(command[command.index('-o') + 1]).write_text('VERDICT: Accept\n')
                    value = {'type': 'turn.completed', 'usage': {}}
                else:
                    value = {'type': 'result', 'subtype': 'success', 'is_error': False,
                             'modelUsage': {'claude-opus-5': {}}, 'structured_output':
                             {'verdict': 'Accept', 'findings': [], 'manual_checks': []}}
                return {'exit_code': 0, 'stdout': json.dumps(value), 'stderr': '',
                        'termination': None, 'duration_ms': 1}

            received = []
            with patch.dict(os.environ, self.review_env()), \
                    patch('agent_process.run', side_effect=execution), redirect_stdout(StringIO()):
                code = main([*args, '--repo', str(self.repo), '--base', 'review-base'], received.append)
            self.assertEqual(code, 5)
            self.assertEqual(received[0]['failure_kind'], 'stale_checkout')
            self.assertEqual(verdicts_of(received[0]['evidence']), [])

    def test_a_reference_deleted_during_review_keeps_its_usage_record(self):
        # The reviewer ran and was paid for: its record must survive the deleted reference
        # and name the commit that reference resolved to when the review started.
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import codex_bridge
        original = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        (self.repo / 'file.py').write_text('final\n')
        self.commit_fixture('Reviewed revision')
        for main, args in ((bridge.main, ['review']),
                           (codex_bridge.main, ['--model', 'fixture-codex-model'])):
            self.git('update-ref', 'refs/heads/review-base', original)

            def execution(command, prompt, repo, timeout, into=None):
                self.git('update-ref', '-d', 'refs/heads/review-base')
                if '-o' in command:
                    Path(command[command.index('-o') + 1]).write_text('VERDICT: Accept\n')
                    value = {'type': 'turn.completed', 'usage': {}}
                else:
                    value = {'type': 'result', 'subtype': 'success', 'is_error': False,
                             'modelUsage': {'claude-opus-5': {}}, 'structured_output':
                             {'verdict': 'Accept', 'findings': [], 'manual_checks': []}}
                return {'exit_code': 0, 'stdout': json.dumps(value), 'stderr': '',
                        'termination': None, 'duration_ms': 1}

            received = []
            with self.subTest(adapter='claude' if main is bridge.main else 'codex'), patch.dict(os.environ, self.review_env()), \
                    patch('agent_process.run', side_effect=execution), redirect_stdout(StringIO()):
                code = main([*args, '--repo', str(self.repo), '--base', 'review-base'], received.append)
                self.assertEqual(code, 5)
                self.assertEqual(received[0]['failure_kind'], 'stale_checkout')
                usage = json.loads(Path(received[0]['usage_record']).read_text())
                self.assertEqual(usage['task']['resolved'], original)

    def test_an_archive_gone_before_accounting_still_records_the_attempt(self):
        # record() reopened the archive to hash it, so an archive deleted in between aborted
        # the accounting of a paid run. The hash is of the bytes published; the attempt is
        # recorded as failed, evidence_unavailable.
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import codex_bridge
        publish = agent_usage.write_evidence

        def publish_then_lose(repo, path, text, **kwargs):
            publish(repo, path, text, **kwargs)
            if path.parent.name == 'reviews':
                path.unlink()

        for main, args in ((bridge.main, ['review']),
                           (codex_bridge.main, ['--model', 'fixture-codex-model'])):
            def execution(command, prompt, repo, timeout, into=None):
                if '-o' in command:
                    Path(command[command.index('-o') + 1]).write_text('VERDICT: Accept\n')
                    value = {'type': 'turn.completed', 'usage': {}}
                else:
                    value = {'type': 'result', 'subtype': 'success', 'is_error': False,
                             'modelUsage': {'claude-opus-5': {}}, 'structured_output':
                             {'verdict': 'Accept', 'findings': [], 'manual_checks': []}}
                return {'exit_code': 0, 'stdout': json.dumps(value), 'stderr': '',
                        'termination': None, 'duration_ms': 1}

            received, out = [], StringIO()
            with self.subTest(adapter='claude' if main is bridge.main else 'codex'), \
                    patch.dict(os.environ, self.review_env()), \
                    patch('agent_process.run', side_effect=execution), \
                    patch('agent_usage.write_evidence', side_effect=publish_then_lose), \
                    redirect_stdout(out):
                code = main([*args, '--repo', str(self.repo), '--uncommitted'], received.append)
                self.assertEqual(code, 5)
                # The Codex adapter printed the completed report, Accept and all, after its
                # accounting had already failed the attempt: contradictory evidence.
                self.assertNotRegex(out.getvalue(), '(?m)^VERDICT:')
                self.assertEqual(received[0]['failure_kind'], 'evidence_unavailable')
                usage = json.loads(Path(received[0]['usage_record']).read_text())
                self.assertEqual((usage['status'], usage['failure_kind']),
                                 ('failed', 'evidence_unavailable'))
                self.assertRegex(usage['evidence_sha256'], '^[0-9a-f]{64}$')

    def test_a_cancel_during_persistence_never_starts_the_fallback_reviewer(self):
        # Cancellation was checked before the evidence and usage writes, though the handler
        # kept noting signals through them: a quota-failed attempt cancelled during either
        # write kept its eligible failure, and --fallback launched the other paid reviewer.
        from contextlib import redirect_stdout
        from io import StringIO
        import signal
        from unittest.mock import patch
        import codex_bridge
        import review_dispatch
        publish, account = agent_usage.write_evidence, agent_usage.record

        def quota(command, prompt, repo, timeout, into=None):
            launched.append(command[0])
            value = ({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}
                     if '-o' in command else
                     {'type': 'result', 'subtype': 'success', 'is_error': True,
                      'api_error_status': 429, 'modelUsage': {'claude-opus-5': {}}})
            return {'exit_code': 1, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        def cancel_during_evidence(repo, path, text, **kwargs):
            if path.parent.name == 'reviews':
                os.kill(os.getpid(), signal.SIGTERM)
            return publish(repo, path, text, **kwargs)

        def cancel_during_record(*args, **kwargs):
            os.kill(os.getpid(), signal.SIGTERM)
            return account(*args, **kwargs)

        for primary in ('claude', 'codex'):
            for target, hook in (('agent_usage.write_evidence', cancel_during_evidence),
                                 ('agent_usage.record', cancel_during_record)):
                launched, out = [], StringIO()
                with self.subTest(primary=primary, during=target), \
                        patch.dict(os.environ, self.review_env()), \
                        patch('agent_process.run', side_effect=quota), patch(target, side_effect=hook), \
                        redirect_stdout(out):
                    code = review_dispatch.main(['--repo', str(self.repo), '--uncommitted',
                                                 '--reviewer', primary, '--allow-fallback',
                                                 '--claude-model', 'claude-opus-5',
                                                 '--codex-model', 'fixture-codex-model'])
                    self.assertEqual(len(launched), 1, 'a cancelled review launched the other '
                                     'reviewer:\n' + out.getvalue())
                    self.assertNotEqual(code, 0)
                    chain = json.loads(next(line.removeprefix('review dispatch: ') for line in
                                            out.getvalue().splitlines() if line.startswith('review dispatch: ')))
                    self.assertEqual(chain['failure_kind'], 'cancelled')
                    self.assertTrue(chain['attempts'][0]['cancelled'])
                    self.persisted_cancel(chain['attempts'][0])
                # Run directly there is no chain to keep the cancel: the records must.
                adapter = (bridge.main, ['review']) if primary == 'claude' else \
                    (codex_bridge.main, ['--model', 'fixture-codex-model'])
                received, launched = [], []
                with self.subTest(direct=primary, during=target), \
                        patch.dict(os.environ, self.review_env()), \
                        patch('agent_process.run', side_effect=quota), patch(target, side_effect=hook), \
                        redirect_stdout(StringIO()):
                    self.assertEqual(adapter[0]([*adapter[1], '--repo', str(self.repo), '--uncommitted'],
                                                received.append), 5)
                    self.assertTrue(received[0]['cancelled'])
                    self.persisted_cancel(received[0])

    def test_a_cancel_during_cleanup_of_a_zero_exit_failure_never_starts_the_fallback(self):
        # run() dropped a cancel noted during its cleanup when the child exited zero, before
        # either adapter had read the response: a zero-exit Claude result with is_error and
        # a 429 stayed a quota failure, and --fallback launched the other paid reviewer.
        from contextlib import redirect_stdout
        from io import StringIO
        import signal
        from unittest.mock import patch
        import agent_process
        import review_dispatch
        real_run, real_killpg = agent_process.run, os.killpg

        def quota(command, prompt, repo, timeout, into=None):
            launched.append(command[0])
            value = ({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}
                     if '-o' in command else
                     {'type': 'result', 'subtype': 'success', 'is_error': True,
                      'api_error_status': 429, 'modelUsage': {'claude-opus-5': {}}})
            return real_run([sys.executable, '-c', 'print(%r)' % json.dumps(value)], prompt, repo, timeout, into)

        def killpg(pid, sig):
            os.kill(os.getpid(), signal.SIGTERM)
            real_killpg(pid, sig)

        for primary in ('claude', 'codex'):
            launched, out = [], StringIO()
            with self.subTest(primary=primary), patch.dict(os.environ, self.review_env()), \
                    patch('agent_process.run', side_effect=quota), \
                    patch.object(agent_process.os, 'killpg', side_effect=killpg), redirect_stdout(out):
                code = review_dispatch.main(['--repo', str(self.repo), '--uncommitted',
                                             '--reviewer', primary, '--allow-fallback',
                                             '--claude-model', 'claude-opus-5',
                                             '--codex-model', 'fixture-codex-model'])
                self.assertEqual(len(launched), 1, 'a cancelled review launched the other '
                                 'reviewer:\n' + out.getvalue())
                self.assertNotEqual(code, 0)
                chain = json.loads(next(line.removeprefix('review dispatch: ') for line in
                                        out.getvalue().splitlines() if line.startswith('review dispatch: ')))
                self.assertEqual(chain['failure_kind'], 'cancelled')
                self.assertTrue(chain['attempts'][0]['cancelled'])
                self.persisted_cancel(chain['attempts'][0])

    def test_a_cancel_during_cleanup_after_a_launch_failure_never_starts_the_fallback(self):
        # A CLI that cannot be launched returned 'unavailable' before cleanup: a cancel noted
        # while the prompt file and the selector closed was dropped, and --fallback launched
        # the other paid reviewer after the cancel.
        from contextlib import redirect_stdout
        from io import StringIO
        import selectors
        import signal
        from unittest.mock import patch
        import agent_process
        import review_dispatch
        real_run = agent_process.run

        def absent(command, prompt, repo, timeout, into=None):
            launched.append(command[0])
            return real_run([str(self.root / 'absent-cli')], prompt, repo, timeout, into)

        class CancelOnClose(selectors.DefaultSelector):
            def close(self):
                os.kill(os.getpid(), signal.SIGTERM)
                super().close()

        for primary in ('claude', 'codex'):
            launched, out = [], StringIO()
            with self.subTest(primary=primary), patch.dict(os.environ, self.review_env()), \
                    patch('agent_process.run', side_effect=absent), \
                    patch.object(agent_process.selectors, 'DefaultSelector', CancelOnClose), \
                    redirect_stdout(out):
                code = review_dispatch.main(['--repo', str(self.repo), '--uncommitted',
                                             '--reviewer', primary, '--allow-fallback',
                                             '--claude-model', 'claude-opus-5',
                                             '--codex-model', 'fixture-codex-model'])
                self.assertEqual(len(launched), 1, 'a cancelled review launched the other '
                                 'reviewer:\n' + out.getvalue())
                self.assertNotEqual(code, 0)
                chain = json.loads(next(line.removeprefix('review dispatch: ') for line in
                                        out.getvalue().splitlines() if line.startswith('review dispatch: ')))
                self.assertEqual(chain['failure_kind'], 'cancelled')
                self.assertTrue(chain['attempts'][0]['cancelled'])

    def test_a_cancel_while_run_hands_back_keeps_the_completed_review(self):
        # run() put the adapter's raising handler back before it returned: a cancel during
        # that restore raised before the result was assigned, and a completed, possibly paid
        # review left neither evidence nor a usage record.
        from contextlib import redirect_stdout
        from io import StringIO
        import signal
        from unittest.mock import patch
        import agent_process
        import codex_bridge
        real_signal, raising = signal.signal, []

        def install(sig, handler):
            previous = real_signal(sig, handler)
            # The adapter's raising handler is the first on SIGTERM; the second time it goes
            # there is run() restoring it.
            if sig == signal.SIGTERM and isinstance(handler, agent_process.OneShot):
                if not raising or handler is raising[0]:
                    raising.append(handler)
                if len(raising) == 2 and handler is raising[0]:
                    os.kill(os.getpid(), signal.SIGTERM)
            return previous

        received = []
        with patch.dict(os.environ, self.review_env(REVIEW_CLI_BIN=str(self.build_fake_codex()))), \
                patch.object(agent_process.signal, 'signal', side_effect=install), redirect_stdout(StringIO()):
            try:
                code = codex_bridge.main(['--model', 'fixture-codex-model', '--repo', str(self.repo),
                                          '--uncommitted'], received.append)
            except KeyboardInterrupt:
                self.fail('a cancel while run() handed back its result lost the completed review')
        self.assertEqual(len(raising), 2)
        self.assertEqual(code, 0)
        self.assertEqual((received[0]['status'], received[0]['cancelled']), ('completed', True))
        self.assertEqual(json.loads(Path(received[0]['usage_record']).read_text())['status'], 'completed')
        self.assertTrue(Path(received[0]['evidence']).is_file())

    def test_a_cancel_while_codex_restores_its_handlers_is_persisted_for_a_failed_attempt(self):
        # The records were relabelled before the adapter put the caller's handlers back: a
        # SIGTERM noted during that restore reached only the returned result, and the usage
        # record and archive of a quota-failed attempt still said quota.
        from contextlib import redirect_stdout
        from io import StringIO
        import signal
        from unittest.mock import patch
        import agent_process
        import codex_bridge
        real_signal, fired = signal.signal, []

        def quota(command, prompt, repo, timeout, into=None):
            return {'exit_code': 1, 'stdout': json.dumps({'type': 'turn.failed',
                    'error': {'message': 'usage limit reached'}}), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        def install(sig, handler):
            # run() is replaced, so the only handler put back that is not the adapter's own
            # is its restore; SIGINT goes back first, SIGTERM still meets the noting guard.
            if sig == signal.SIGINT and not isinstance(handler, agent_process.OneShot) and not fired:
                fired.append(sig)
                os.kill(os.getpid(), signal.SIGTERM)
            return real_signal(sig, handler)

        received = []
        with patch.dict(os.environ, self.review_env()), patch('agent_process.run', side_effect=quota), \
                patch.object(agent_process.signal, 'signal', side_effect=install), redirect_stdout(StringIO()):
            code = codex_bridge.main(['--model', 'fixture-codex-model', '--repo', str(self.repo),
                                      '--uncommitted'], received.append)
        self.assertTrue(fired)
        self.assertEqual(code, 5)
        self.assertEqual((received[0]['failure_kind'], received[0]['cancelled']), ('cancelled', True))
        self.persisted_cancel(received[0])

    def test_a_cancel_while_codex_switches_to_noting_keeps_the_completed_review(self):
        # After run() returned, the adapter installed its noting handler one signal at a time:
        # a SIGTERM before the swap reached SIGTERM still met the raising handler, unwound the
        # adapter and deleted the final report before evidence or usage were written.
        from contextlib import redirect_stdout
        from io import StringIO
        import signal
        from unittest.mock import patch
        import agent_process
        import codex_bridge
        real_signal, real_run, returned, fired = signal.signal, agent_process.run, [], []

        def run(*args, **kwargs):
            try:
                return real_run(*args, **kwargs)
            finally:
                returned.append(True)

        def install(sig, handler):
            # The first handler change after run() has returned.
            if returned and not fired:
                fired.append(sig)
                os.kill(os.getpid(), signal.SIGTERM)
            return real_signal(sig, handler)

        received = []
        with patch.dict(os.environ, self.review_env(REVIEW_CLI_BIN=str(self.build_fake_codex()))), \
                patch.object(agent_process, 'run', side_effect=run), \
                patch.object(agent_process.signal, 'signal', side_effect=install), redirect_stdout(StringIO()):
            try:
                code = codex_bridge.main(['--model', 'fixture-codex-model', '--repo', str(self.repo),
                                          '--uncommitted'], received.append)
            except KeyboardInterrupt:
                self.fail('a cancel while the adapter switched to noting lost the completed review')
        self.assertTrue(fired)
        self.assertEqual(code, 0)
        self.assertEqual((received[0]['status'], received[0]['cancelled']), ('completed', True))
        self.assertEqual(json.loads(Path(received[0]['usage_record']).read_text())['status'], 'completed')
        self.assertTrue(Path(received[0]['evidence']).is_file())

    def test_a_cancel_during_the_claude_final_output_never_starts_the_fallback(self):
        # Cancellation was sampled before the result was printed, with the noting handler
        # still installed: a SIGTERM while the final output was blocked was noted too late,
        # the quota-failed attempt returned cancelled: false, and --fallback launched Codex.
        from contextlib import redirect_stdout
        from io import StringIO
        import signal
        from unittest.mock import patch
        import review_dispatch

        def quota(command, prompt, repo, timeout, into=None):
            launched.append(command[0])
            value = {'type': 'result', 'subtype': 'success', 'is_error': True,
                     'api_error_status': 429, 'modelUsage': {'claude-opus-5': {}}}
            return {'exit_code': 1, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        class Blocked(StringIO):
            def write(self, text):
                # The adapter's own result line: the dispatcher prints none starting so.
                if text.startswith('{"status": "failed"') and not fired:
                    fired.append(text)
                    os.kill(os.getpid(), signal.SIGTERM)
                return super().write(text)

        launched, fired, out = [], [], Blocked()
        with patch.dict(os.environ, self.review_env()), patch('agent_process.run', side_effect=quota), \
                redirect_stdout(out):
            code = review_dispatch.main(['--repo', str(self.repo), '--uncommitted', '--reviewer', 'claude',
                                         '--allow-fallback', '--claude-model', 'claude-opus-5',
                                         '--codex-model', 'fixture-codex-model'])
        self.assertTrue(fired)
        self.assertEqual(len(launched), 1, 'a cancelled review launched the other reviewer:\n' + out.getvalue())
        self.assertNotEqual(code, 0)
        chain = json.loads(next(line.removeprefix('review dispatch: ') for line in
                                out.getvalue().splitlines() if line.startswith('review dispatch: ')))
        self.assertEqual(chain['failure_kind'], 'cancelled')
        self.assertTrue(chain['attempts'][0]['cancelled'])
        self.persisted_cancel(chain['attempts'][0])
        # Run directly there is no dispatcher dict: what the adapter printed must say it, and
        # its last JSON line is the one that counts.
        launched, fired, out, received = [], [], Blocked(), []
        with patch.dict(os.environ, self.review_env()), patch('agent_process.run', side_effect=quota), \
                redirect_stdout(out):
            code = bridge.main(['review', '--repo', str(self.repo), '--uncommitted'], received.append)
        self.assertTrue(fired)
        self.assertEqual(code, 5)
        last = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertEqual((last['cancelled'], last['failure_kind']), (True, 'cancelled'), out.getvalue())
        self.persisted_cancel(received[0])

    def test_a_cancel_whose_archive_replacement_fails_is_still_recorded_and_returned(self):
        # The relabel replaced the archive before the usage record, so a failure between the
        # two left the archive saying cancelled and the record quota, and the Codex adapter
        # raised before delivering its result. The record is written first now: the archive
        # left behind fails its sha256, and a failed record is never carried to a later round.
        # The error reports what the archive bytes show, never which step failed: a directory
        # fsync can fail after the replacement landed, and an archive can be unreadable.
        from contextlib import redirect_stdout
        from io import StringIO
        import signal
        import stat
        from unittest.mock import patch
        import codex_bridge
        publish, account, sync = agent_usage.write_evidence, agent_usage.record, os.fsync

        def quota(command, prompt, repo, timeout, into=None):
            value = ({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}
                     if '-o' in command else
                     {'type': 'result', 'subtype': 'success', 'is_error': True,
                      'api_error_status': 429, 'modelUsage': {'claude-opus-5': {}}})
            return {'exit_code': 1, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        def cancel_during_record(*args, **kwargs):
            os.kill(os.getpid(), signal.SIGTERM)
            return account(*args, **kwargs)

        def replacement_fails(repo, path, text, **kwargs):
            raise OSError('injected archive replacement failure')

        def directory_fsync_fails(repo, path, text, **kwargs):
            def fsync(fd):
                if stat.S_ISDIR(os.fstat(fd).st_mode):
                    raise OSError('injected directory fsync failure')
                return sync(fd)
            with patch('os.fsync', side_effect=fsync):
                return publish(repo, path, text, **kwargs)

        def archive_vanishes(repo, path, text, **kwargs):
            path.unlink()
            raise OSError('injected archive removal')

        def hooked(fault):
            def hook(repo, path, text, **kwargs):
                if kwargs.get('replace') and path.parent.name == 'reviews':
                    return fault(repo, path, text, **kwargs)
                return publish(repo, path, text, **kwargs)
            return hook

        for fault in (replacement_fails, directory_fsync_fails, archive_vanishes):
            for main, args in ((bridge.main, ['review']),
                               (codex_bridge.main, ['--model', 'fixture-codex-model'])):
                received, out = [], StringIO()
                with self.subTest(fault=fault.__name__,
                                  adapter='claude' if main is bridge.main else 'codex'), \
                        patch.dict(os.environ, self.review_env()), \
                        patch('agent_process.run', side_effect=quota), \
                        patch('agent_usage.record', side_effect=cancel_during_record), \
                        patch('agent_usage.write_evidence', side_effect=hooked(fault)), \
                        redirect_stdout(out):
                    self.assertEqual(main([*args, '--repo', str(self.repo), '--uncommitted'],
                                          received.append), 5)
                    self.assertTrue(received[0]['cancelled'])
                    self.assertEqual(received[0]['failure_kind'], 'cancelled')
                    usage = json.loads(Path(received[0]['usage_record']).read_text())
                    self.assertEqual((usage['status'], usage['failure_kind']), ('failed', 'cancelled'))
                    evidence = Path(received[0]['evidence'])
                    if fault is archive_vanishes:
                        self.assertFalse(evidence.exists())
                        self.assertIn('the archive %s on disk could not be read (' % evidence,
                                      out.getvalue())
                        self.assertIn('; the write reported: injected archive removal', out.getvalue())
                    else:
                        archive = evidence.read_bytes()
                        replaced = fault is directory_fsync_fails
                        self.assertIn(b'| failure_kind | cancelled |' if replaced
                                      else b'| failure_kind | quota |', archive)
                        self.assertEqual(usage['evidence_sha256'] == hashlib.sha256(archive).hexdigest(),
                                         replaced)
                        self.assertIn('the usage record says cancelled; the archive %s on disk %s; '
                                      'the write reported: %s'
                                      % (evidence, 'matches the record (sha256 %s)'
                                         % usage['evidence_sha256'] if replaced
                                         else 'does not match the record',
                                         'injected directory fsync failure' if replaced
                                         else 'injected archive replacement failure'),
                                      out.getvalue())
                    # Fail closed: an archive the record does not match stops the next round.
                    rounds = lambda: bridge.prior_rounds(self.repo, usage['task']['id'], 'uncommitted',
                                                         None, usage['task']['head'], '')
                    if fault is replacement_fails:
                        with self.assertRaisesRegex(bridge.BridgeError, re.escape(str(evidence))):
                            rounds()
                        evidence.unlink()
                    else:
                        self.assertEqual(rounds(), '')

    def persisted_cancel(self, result):
        # The usage reporter reads the records, not the dispatcher's result: a cancel during
        # publication once left both saying quota.
        usage = json.loads(Path(result['usage_record']).read_text())
        self.assertEqual((usage['status'], usage['failure_kind']), ('failed', 'cancelled'))
        archive = Path(result['evidence']).read_bytes()
        self.assertIn(b'| status | failed |', archive)
        self.assertIn(b'| failure_kind | cancelled |', archive)
        self.assertEqual(usage['evidence_sha256'], hashlib.sha256(archive).hexdigest())

    def test_an_empty_task_label_is_unset_not_a_record_that_blocks_later_rounds(self):
        # The dispatcher kept an empty MYAGENTKIT_TASK_ID and the Codex adapter recorded it as
        # the id; every later labelled review then refused that record as damaged.
        for primary in ('codex', 'claude'):
            with self.subTest(primary=primary):
                case = {'CODEX_FIXTURE_CASE' if primary == 'codex' else 'FIXTURE_CASE': 'reject'}
                result, chain = self.dispatch_result(primary, fallback=False, MYAGENTKIT_TASK_ID='', **case)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                usage = json.loads(Path(chain['attempts'][0]['usage_record']).read_text())
                self.assertEqual(usage['task']['id'], 'review-' + chain['chain_id'])
                self.assertEqual(chain['task_id'], usage['task']['id'])
                later, _ = self.dispatch_result(primary, fallback=False, MYAGENTKIT_TASK_ID='later-' + primary)
                self.assertEqual(later.returncode, 0, later.stdout + later.stderr)
        # Run directly, the adapters use their own default label for an empty one.
        scripts = self.install_wrapper()
        direct = subprocess.run([sys.executable, '-B', str(scripts / 'codex_bridge.py'), '--repo',
                                 str(self.repo), '--model', 'fixture-codex-model', '--uncommitted'],
                                env=self.review_env(MYAGENTKIT_TASK_ID='', REVIEW_CLI_BIN=str(self.build_fake_codex())),
                                capture_output=True, text=True)
        self.assertEqual(direct.returncode, 0, direct.stdout)
        line = next(s for s in direct.stdout.splitlines() if s.startswith('review invocation: '))
        usage = json.loads(Path(json.loads(line.removeprefix('review invocation: '))['usage_record']).read_text())
        self.assertEqual(usage['task']['id'], 'review-uncommitted')
        code, result = self.run_bridge(env_extra={'MYAGENTKIT_TASK_ID': ''})
        self.assertEqual(code, 0, result)
        self.assertEqual(json.loads(Path(result['usage_record']).read_text())['task']['id'], 'review-uncommitted')
        # And no writer can produce one: record() refuses a task without a label.
        with self.assertRaises(ValueError):
            agent_usage.record(self.repo, 'codex', 'm', 'r', {'id': '', 'kind': 'review'},
                               {'stdout': ''}, 'failed', 'quota', None)

    def test_hidden_checkout_changes_reject_before_either_adapter_launches(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import codex_bridge
        import claude_bridge
        import review_dispatch
        self.commit_fixture('Reference review fixture')
        def execution(command, prompt, repo, timeout, into=None):
            if '-o' in command:
                Path(command[command.index('-o') + 1]).write_text('VERDICT: Accept\n')
                value = {'type': 'turn.completed', 'usage': {}}
            else:
                value = {'type': 'result', 'subtype': 'success', 'is_error': False,
                         'modelUsage': {'claude-opus-5': {}}, 'structured_output':
                         {'verdict': 'Accept', 'findings': [], 'manual_checks': []}}
            return {'exit_code': 0, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}
        for flag in ('assume-unchanged', 'skip-worktree'):
            self.git('update-index', '--' + flag, 'file.py')
            (self.repo / 'file.py').write_text('HIDDEN_CHECKOUT_CONTENT\n')
            self.assertEqual(self.git('diff', 'HEAD').stdout, b'')
            for scope in ('--commit', '--base', '--uncommitted'):
                args = [scope, 'HEAD^' if scope == '--base' else 'HEAD'] if scope != '--uncommitted' else [scope]
                for main, prefix in ((bridge.main, ['review']),
                                     (codex_bridge.main, ['--model', 'fixture-codex-model']),
                                     (review_dispatch.main, ['--claude-model', 'claude-opus-5'])):
                    with self.subTest(flag=flag, scope=scope, adapter=main.__module__), \
                            patch.dict(os.environ, self.review_env()), \
                            patch('agent_process.run', side_effect=execution) as launch, \
                            redirect_stdout(StringIO()) as output:
                        try:
                            code = main([*prefix, '--repo', str(self.repo), *args])
                        except (bridge.BridgeError, claude_bridge.BridgeError, ValueError) as error:
                            self.assertIn('index flags', str(error))
                        else:
                            self.assertNotEqual(code, 0, output.getvalue())
                            self.assertIn('index flags', output.getvalue())
                        launch.assert_not_called()
            self.git('update-index', '--no-' + flag, 'file.py')
            (self.repo / 'file.py').write_text('changed\n')

    def test_merge_commit_review_includes_the_resolution_against_first_parent(self):
        self.commit_fixture('Common base')
        main = self.git('symbolic-ref', '--short', 'HEAD').stdout.decode().strip()
        self.git('checkout', '-qb', 'feature')
        (self.repo / 'file.py').write_text('feature\n')
        self.commit_fixture('Feature side')
        self.git('checkout', '-q', main)
        (self.repo / 'file.py').write_text('main\n')
        self.commit_fixture('Main side')
        result = subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Fixture',
                                 '-c', 'user.email=fixture@example.invalid', 'merge', '--no-commit', 'feature'],
                                capture_output=True)
        self.assertEqual(result.returncode, 1)
        (self.repo / 'file.py').write_text('RESOLVED_MERGE_CONTENT\n')
        self.commit_fixture('Resolve merge')
        diff = bridge.snapshot(self.repo, 'commit', 'HEAD')[2]
        self.assertIn('RESOLVED_MERGE_CONTENT', diff)
        self.assertIn('-main', diff)

    def test_codex_manual_verdict_requires_actual_manual_checks(self):
        fake = self.root / 'codex-manual'
        fake.write_text('#!/usr/bin/env python3\nimport json,os,pathlib,sys\n'
                        'sys.stdin.read()\n'
                        'pathlib.Path(sys.argv[sys.argv.index("-o")+1]).write_text(os.environ["FINAL_RESPONSE"])\n'
                        'print(json.dumps({"type":"turn.completed","usage":{}}))\n')
        fake.chmod(0o755)
        for checks in ('', '## Manual checks\n', '## Manual checks\nNone.\n',
                       '## Manual checks\n- Verify the live deployment.\n'):
            with self.subTest(checks=checks):
                result = self.run_wrapper('--reviewer', 'codex', REVIEW_CLI_BIN=str(fake),
                                          REVIEW_CODEX_MODEL='fixture-codex-model',
                                          FINAL_RESPONSE='VERDICT: Accept with Manual Checks\n' + checks)
                self.assertEqual(result.returncode, 0 if 'Verify' in checks else 5,
                                 result.stdout + result.stderr)

    def test_a_verdict_inside_manual_checks_is_not_itself_a_check(self):
        fake = self.root / 'codex-manual-placement'
        fake.write_text('#!/usr/bin/env python3\nimport json,os,pathlib,sys\n'
                        'sys.stdin.read()\n'
                        'pathlib.Path(sys.argv[sys.argv.index("-o")+1]).write_text(os.environ["FINAL_RESPONSE"])\n'
                        'print(json.dumps({"type":"turn.completed","usage":{}}))\n')
        fake.chmod(0o755)
        for checks in ('', 'None.\n', '- Verify the live deployment.\n'):
            with self.subTest(checks=checks):
                result = self.run_wrapper('--reviewer', 'codex', REVIEW_CLI_BIN=str(fake),
                                          REVIEW_CODEX_MODEL='fixture-codex-model',
                                          FINAL_RESPONSE='## Manual checks\n' + checks +
                                          'VERDICT: Accept with Manual Checks\n')
                chain = json.loads(next(s.removeprefix('review dispatch: ') for s in
                                        result.stdout.splitlines() if s.startswith('review dispatch: ')))
                self.assertEqual(len(chain['attempts']), 1)
                if 'Verify' in checks:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                else:
                    self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
                    self.assertEqual(chain['failure_kind'], 'invalid_evidence')
                    self.assertEqual(verdicts_of(chain['attempts'][0]['evidence']), [])

    def run_bridge(self, case="accept", mode="review", extra=(), env_extra=None):
        env = dict(os.environ, CLAUDE_CLI_BIN=str(self.fixture), FIXTURE_CASE=case,
                   MYAGENTKIT_DELEGATION_DEPTH="0")
        env.update(env_extra or {})
        result = subprocess.run([sys.executable, "-B", str(BRIDGE), mode, "--repo", str(self.repo),
                                 *extra], env=env, capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def test_completed_reviews_keep_verdict_separate_from_process_success(self):
        for case, verdict in [("accept", "Accept"), ("reject", "Reject"), ("manual", "Accept with Manual Checks")]:
            with self.subTest(case=case):
                code, result = self.run_bridge(case)
                self.assertEqual(code, 0, result)
                self.assertEqual(result["result"]["verdict"], verdict)
                self.assertTrue(result["evidence"].endswith("-claude-review.md"), result)
                record = header_of(result["evidence"])
                self.assertEqual(record["status"], "completed")
                self.assertIn("Read,Glob,Grep", record["sandbox"])
                self.assertEqual(len(record["diff_sha256"]), 64)
                self.assertEqual(verdicts_of(result["evidence"]), ["VERDICT: " + verdict])

    def test_private_storage_is_required_before_any_provider_launch(self):
        from unittest.mock import patch
        import codex_bridge
        import review_dispatch
        from contextlib import redirect_stdout
        from io import StringIO

        for case in ('missing_ignore', 'tracked_usage', 'tracked_review', 'unignored_review'):
            with self.subTest(case=case):
                (self.repo / '.gitignore').write_bytes((ROOT.parent / '.gitignore').read_bytes())
                if case == 'missing_ignore':
                    (self.repo / '.gitignore').write_text('')
                elif case == 'unignored_review':
                    with (self.repo / '.gitignore').open('a') as stream:
                        stream.write('\n!/docs/reviews/*-review.md\n')
                else:
                    name = ('.myagentkit/usage/old.json' if case == 'tracked_usage' else
                            'docs/reviews/20260101T000000Z-000000000000-codex-review.md')
                    path = self.repo / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('Synthetic private diagnostic.\n')
                    self.git('add', '-f', name)
                for main, args in ((bridge.main, ['review']),
                                   (codex_bridge.main, ['--model', 'fixture-codex-model']),
                                   (review_dispatch.main, ['--claude-model', 'claude-opus-5'])):
                    with patch.dict(os.environ, self.review_env()), \
                            patch('agent_process.run', side_effect=AssertionError('provider launched before privacy check')) as launch, \
                            patch('codex_quota.snapshot') as quota, redirect_stdout(StringIO()):
                        try:
                            code = main([*args, '--repo', str(self.repo)])
                        except (ValueError, bridge.BridgeError):
                            code = 2
                        self.assertNotEqual(code, 0)
                        launch.assert_not_called()
                        quota.assert_not_called()
                if case.startswith('tracked_'):
                    self.git('rm', '-f', '--', name)

    def test_private_evidence_stays_out_of_git_add(self):
        code, result = self.run_bridge()
        self.assertEqual(code, 0, result)
        self.git('add', '.')
        staged = self.git('diff', '--cached', '--name-only').stdout.decode()
        self.assertNotIn('.myagentkit/', staged)
        self.assertNotIn('docs/reviews/', staged)

    def test_malformed_claude_envelope_never_triggers_failover(self):
        result, chain = self.dispatch_result(FIXTURE_CASE='malformed_envelope')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(len(chain['attempts']), 1)
        self.assertEqual(chain['failure_kind'], 'invalid_evidence')
        self.assertEqual(verdicts_of(chain['attempts'][0]['evidence']), [])

    def test_malformed_codex_verdict_never_becomes_accept(self):
        fake = self.root / 'codex-conflict'
        fake.write_text('#!/usr/bin/env python3\n'
                        'import json, os, pathlib, sys\n'
                        'sys.stdin.read()\n'
                        'pathlib.Path(sys.argv[sys.argv.index("-o") + 1]).write_text(os.environ["FINAL_RESPONSE"])\n'
                        'print(json.dumps({"type": "turn.completed", "usage": {}}))\n')
        fake.chmod(0o755)
        for final in ('VERDICT: Accept\nVERDICT: Reject — unresolved defect\n',
                      'VERDICT: Accept\n  VERDICT: Reject\n',
                      'VERDICT: Accept\nVERDICT: Unknown\n',
                      'VERDICT: Accept\nVERDICT:Reject\n'):
            with self.subTest(final=final):
                result = self.run_wrapper('--reviewer', 'codex', REVIEW_CLI_BIN=str(fake),
                                          REVIEW_CODEX_MODEL='fixture-codex-model', FINAL_RESPONSE=final)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                chain = json.loads(next(s.removeprefix('review dispatch: ') for s in
                                        result.stdout.splitlines() if s.startswith('review dispatch: ')))
                self.assertEqual(chain['failure_kind'], 'invalid_evidence')
                self.assertEqual(len(chain['attempts']), 1)
                self.assertEqual(verdicts_of(chain['attempts'][0]['evidence']), [])

    def test_transcript_accept_cannot_replace_a_missing_final_response(self):
        fake = self.root / 'codex-transcript'
        fake.write_text('#!/usr/bin/env python3\n'
                        'import json, sys\n'
                        'sys.stdin.read()\n'
                        'print(json.dumps({"type": "item.completed", "item": '
                        '{"type": "agent_message", "text": "VERDICT: Accept"}}))\n'
                        'print(json.dumps({"type": "turn.completed", "usage": {}}))\n')
        fake.chmod(0o755)
        result = self.run_wrapper('--reviewer', 'codex', REVIEW_CLI_BIN=str(fake),
                                  REVIEW_CODEX_MODEL='fixture-codex-model')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        chain = json.loads(next(s.removeprefix('review dispatch: ') for s in
                                result.stdout.splitlines() if s.startswith('review dispatch: ')))
        self.assertEqual(chain['failure_kind'], 'invalid_evidence')
        self.assertEqual(len(chain['attempts']), 1)
        attempt = chain['attempts'][0]
        self.assertEqual(verdicts_of(attempt['evidence']), [])
        usage = json.loads(Path(attempt['usage_record']).read_text())
        self.assertIn('VERDICT: Accept', usage['raw_stdout'])
        self.assertEqual(usage['status'], 'failed')

    def test_bad_cli_evidence_fails_with_its_reason(self):
        cases = {"missing": "structured final", "transcript": "Expecting value",
                 "conflict": "contradicts", "turns": "incomplete", "model": "modelUsage",
                 "error": "successful result", "exit": "exited 9", "mutation": "changed during"}
        for case, reason in cases.items():
            with self.subTest(case=case):
                code, result = self.run_bridge(case)
                self.assertEqual(code, 5, result)
                self.assertIn(reason, result["error"])
                self.assertEqual(header_of(result["evidence"])["status"], "failed")
                # A failed run that still printed a verdict would read as an approval.
                self.assertEqual(verdicts_of(result["evidence"]), [])

    def test_timeout_fails_and_archives_failure(self):
        code, result = self.run_bridge("timeout", extra=["--timeout", "1"])
        self.assertEqual(code, 5)
        self.assertIn("wall-clock", result["error"])
        self.assertTrue(Path(result["evidence"]).is_file())

    def test_empty_scope_and_missing_guidance_fail_before_cli(self):
        (self.repo / "file.py").write_text("original\n")
        code, result = self.run_bridge()
        self.assertEqual(code, 2)
        self.assertIn("empty diff", result["error"])
        (self.repo / "AGENTS.md").unlink()
        code, result = self.run_bridge()
        self.assertEqual(code, 2)
        self.assertIn("guidance is missing", result["error"])

    def test_nested_delegation_and_alias_are_rejected(self):
        code, result = self.run_bridge(env_extra={"MYAGENTKIT_DELEGATION_DEPTH": "1"})
        self.assertEqual(code, 2)
        self.assertIn("nested", result["error"])
        code, result = self.run_bridge(extra=["--model", "opus"])
        self.assertEqual(code, 2)
        self.assertIn("explicit", result["error"])

    def test_proposal_is_returned_but_never_applied(self):
        task = self.root / "handoff.md"
        task.write_text("Fix the named function only; propose tests and stop on ambiguity.")
        for case in ["proposal", "questions"]:
            code, result = self.run_bridge(case, "propose", ["--task-file", str(task)])
            self.assertEqual(code, 0, result)
            self.assertEqual((self.repo / "file.py").read_text(), "changed\n")
            self.assertIn("questions", result["result"])

    def test_base_commit_and_untracked_scopes(self):
        code, result = self.run_bridge(extra=["--commit", "HEAD"])
        self.assertEqual(code, 2)
        self.assertIn("clean checkout", result["error"])
        (self.repo / "file.py").write_text("original\n")
        code, result = self.run_bridge(extra=["--base", "HEAD"])
        self.assertEqual(code, 2)
        self.assertIn("empty diff", result["error"])
        code, result = self.run_bridge(extra=["--commit", "HEAD"])
        self.assertEqual(code, 0, result)
        (self.repo / "new file.txt").write_text("a new file\n")
        _, _, diff = bridge.snapshot(self.repo, "uncommitted", None)
        self.assertIn("new file.txt", diff)

    def test_archiving_does_not_recursively_expand_the_next_review(self):
        _, first = self.run_bridge()
        _, second = self.run_bridge()
        a = header_of(first["evidence"])
        b = header_of(second["evidence"])
        self.assertEqual(a["diff_sha256"], b["diff_sha256"])
        self.assertEqual(a["fingerprint"], b["fingerprint"])

    def test_interrupted_review_evidence_is_preserved_without_expanding_next_scope(self):
        code, failed = self.run_bridge('partial_timeout', extra=['--timeout', '1'])
        self.assertEqual(code, 5, failed)
        original = Path(failed['evidence']).read_bytes()
        self.assertEqual(verdicts_of(failed['evidence']), [])
        code, completed = self.run_bridge()
        self.assertEqual(code, 0, completed)
        self.assertEqual(Path(failed['evidence']).read_bytes(), original)
        self.assertEqual(header_of(failed['evidence'])['diff_sha256'],
                         header_of(completed['evidence'])['diff_sha256'])
        self.assertEqual(header_of(failed['evidence'])['fingerprint'],
                         header_of(completed['evidence'])['fingerprint'])

    def test_removing_legacy_archives_excludes_transcripts_but_keeps_summaries(self):
        archive = self.repo / 'docs/reviews/20260101T000000Z-master.md'
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text('PRIVATE_LEGACY_TRANSCRIPT\n')
        self.git('add', '-f', str(archive))
        commit = ('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                  '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-qm')
        self.git(*commit, 'Synthetic legacy archive')
        base = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        self.git('rm', '--cached', str(archive))
        summary = archive.with_name('20260101T000000Z-review-summary.md')
        summary.write_text('PUBLIC_REVIEW_SUMMARY\n')
        self.git('add', str(summary), 'file.py')
        diff = bridge.snapshot(self.repo, 'uncommitted', None)[2]
        self.assertNotIn('PRIVATE_LEGACY_TRANSCRIPT', diff)
        self.assertIn('PUBLIC_REVIEW_SUMMARY', diff)
        self.git(*commit, 'Untrack legacy evidence and publish summary')
        for scope, ref in (('base', base), ('commit', 'HEAD')):
            diff = bridge.snapshot(self.repo, scope, ref)[2]
            self.assertNotIn('PRIVATE_LEGACY_TRANSCRIPT', diff)
            self.assertIn('PUBLIC_REVIEW_SUMMARY', diff)
        self.assertEqual(archive.read_text(), 'PRIVATE_LEGACY_TRANSCRIPT\n')

    def test_proposal_needs_a_handoff(self):
        code, result = self.run_bridge(mode="propose")
        self.assertEqual(code, 2)
        self.assertIn("task-file", result["error"])

    def test_usage_and_quota_failure_are_recorded(self):
        code, result = self.run_bridge("quota", extra=["--requester", "codex/fixture"])
        self.assertEqual(code, 5, result)
        self.assertEqual(result["failure_kind"], "quota")
        record = json.loads(Path(result["usage_record"]).read_text())
        self.assertEqual(record["requester_reported"], "codex/fixture")
        self.assertEqual(record["usage"]["input_tokens"], 7)
        self.assertEqual(record["usage"]["api_cost_usd_reported"], 0.123)
        self.assertIsNone(record["usage"]["subscription_percent_consumed"])
        self.assertEqual(record["recovery"]["action"], "continue_independent_work")
        self.assertFalse(record["recovery"]["review_approved"])

    def test_timeout_keeps_partial_usage_and_raw_evidence(self):
        code, result = self.run_bridge("partial_timeout", extra=["--timeout", "1"])
        self.assertEqual(code, 5, result)
        usage = json.loads(Path(result["usage_record"]).read_text())
        self.assertIn('"total_cost_usd": 0.123', usage["raw_stdout"])
        self.assertEqual(usage["failure_kind"], "timeout")
        self.assertFalse(usage["usage"]["complete"])

    def test_custom_guidance_is_explicit_and_checked(self):
        code, result = self.run_bridge(env_extra={"CLAUDE_REVIEW_DOCS": '["AGENTS.md"]'},
                                       extra=["--requester", "codex/test-fixture"])
        self.assertEqual(code, 0, result)
        self.assertEqual(json.loads(Path(result["usage_record"]).read_text())["requester_reported"],
                         "codex/test-fixture")
        for docs in ['[]', '["../outside.md"]', '["absent.md"]', '{}']:
            code, result = self.run_bridge(env_extra={"CLAUDE_REVIEW_DOCS": docs})
            self.assertEqual(code, 2, result)

    def test_kit_layout_requires_architecture_guidance(self):
        (self.repo / 'AGENTS.md').unlink()
        (self.repo / 'core/docs').mkdir(parents=True)
        for name in ['CONTRIBUTING.md', 'core/AGENTS.md', 'core/docs/REVIEW_GATE.md']:
            (self.repo / name).write_text('Synthetic kit guidance.\n')
        code, result = self.run_bridge('kit_docs')
        self.assertEqual(code, 2, result)
        self.assertIn('core/docs/ARCHITECTURE.md', result['error'])
        (self.repo / 'core/docs/ARCHITECTURE.md').write_text('Synthetic architecture.\n')
        code, result = self.run_bridge('kit_docs')
        self.assertEqual(code, 0, result)

    def test_archive_failure_cannot_record_completed_usage(self):
        code, result = self.run_bridge('archive_failure')
        self.assertNotEqual(code, 0, result)
        self.assertEqual(result.get('failure_kind'), 'evidence_write_failed', result)
        usage = json.loads(Path(result['usage_record']).read_text())
        self.assertEqual(usage['status'], 'failed')
        self.assertIsNone(usage['evidence'])
        self.assertEqual(usage['usage']['input_tokens'], 7)

    def install_wrapper(self):
        scripts = self.repo / "scripts"
        if not scripts.exists():
            scripts.mkdir()
            # Installed projects own these three defaults. Exercise the template's
            # empty-pin cases in an explicit fixture without overwriting project config.
            wrapper = (ROOT / "review.sh").read_text()
            for name, value in (("DEFAULT_REVIEWER", "claude"),
                                ("CODEX_MODEL", ""), ("CLAUDE_MODEL", "")):
                wrapper, count = re.subn(r"^" + name + r"=.*$",
                                         name + '="' + value + '"', wrapper, flags=re.M)
                self.assertEqual(count, 1, "missing project configuration: " + name)
            (scripts / "review.sh").write_text(wrapper)
            for name in ["codex_bridge.py", "claude_bridge.py", "agent_process.py",
                         "agent_usage.py", "codex_quota.py", "review_dispatch.py"]:
                (scripts / name).write_bytes((ROOT / name).read_bytes())
        return scripts

    def review_env(self, **extra):
        # Both CLI binaries default to a path that does not exist. This suite promises never
        # to call a paid CLI, and a test that forgot to pass its fixture once reached the
        # real one through a shell default — so the harness fails to launch instead.
        absent = str(self.root / "NO-REAL-CLI-IN-TESTS")
        env = dict(os.environ, REVIEW_REPO_ROOT=str(self.repo), MYAGENTKIT_CAPTURE_QUOTA="0",
                   MYAGENTKIT_DELEGATION_DEPTH="0", REVIEW_TIMEOUT_SECONDS="30",
                   FIXTURE_CASE="accept", CLAUDE_CLI_BIN=absent, REVIEW_CLI_BIN=absent,
                   REVIEW_CLAUDE_MODEL="", REVIEW_CODEX_MODEL="", REVIEW_REVIEWER="",
                   REVIEW_DOCS="AGENTS.md, docs/ARCHITECTURE.md and docs/REVIEW_GATE.md")
        env.update(extra)
        return env

    def test_codex_wrapper_rejects_absent_and_conflicting_final_evidence(self):
        scripts = self.install_wrapper()
        fake = self.root / "codex"
        fake.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys, time
if '--version' in sys.argv: print('offline codex'); sys.exit(0)
prompt = sys.stdin.read()
assert 'PRIVATE_PREVIOUS_REVIEW' not in prompt
last = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])
case = os.environ['FIXTURE_CASE']
assert '--json' in sys.argv and '--ephemeral' in sys.argv
assert sys.argv[sys.argv.index('-s') + 1] == 'read-only'
if case == 'quota':
    print(json.dumps({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}})); sys.exit(1)
print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 100, 'cached_input_tokens': 90, 'output_tokens': 4}}), flush=True)
if case == 'timeout': time.sleep(20)
if case == 'conflicting': last.write_text('VERDICT: Accept\\nVERDICT: Reject\\n')
if case == 'empty': last.write_text('')
if case == 'garbage': last.write_text('Looks good to me, ship it.\\n')
if case == 'accept': last.write_text('VERDICT: Accept\\n')
if case == 'reject': last.write_text('## Findings\\n\\n- money.py:7 divides in floats.\\n\\nVERDICT: Reject\\n')
if case == 'mutation':
    pathlib.Path('file.py').write_text('mutated')
    last.write_text('VERDICT: Accept\\n')
if case == 'archive_failure':
    import shutil
    shutil.rmtree('docs/reviews')
    pathlib.Path('docs/reviews').write_text('blocked archive')
    last.write_text('VERDICT: Accept\\n')
''')
        fake.chmod(0o755)
        self.fake_codex = fake
        (self.repo / '.gitignore').write_bytes((ROOT.parent / '.gitignore').read_bytes())
        reviews = self.repo / 'docs/reviews'
        reviews.mkdir(exist_ok=True)
        private = reviews / '20260101T000000Z-main.md'
        private.write_text('PRIVATE_PREVIOUS_REVIEW')
        self.assertEqual(self.git('check-ignore', str(private)).returncode, 0)
        # Missing, empty, malformed and conflicting final responses must ALL fail closed,
        # whatever the transcript said; Accept and Reject are the passing controls.
        for case, expected in [("missing", 5), ("empty", 5), ("garbage", 5), ("conflicting", 5),
                               ("accept", 0), ("reject", 0), ("quota", 5), ("timeout", 5),
                               ("mutation", 5), ("archive_failure", 5)]:
            with self.subTest(case=case):
                env = self.review_env(REVIEW_CLI_BIN=str(fake), FIXTURE_CASE=case,
                           REVIEW_CODEX_MODEL="fixture-codex-model", REVIEW_REPO_ROOT=str(self.repo),
                           MYAGENTKIT_CAPTURE_QUOTA="0", MYAGENTKIT_DELEGATION_DEPTH="0",
                           REVIEW_TIMEOUT_SECONDS="1" if case == "timeout" else "30",
                           MYAGENTKIT_REQUESTER="claude/fixture", MYAGENTKIT_TASK_ID="fixture-review",
                           REVIEW_DOCS="AGENTS.md, docs/ARCHITECTURE.md and docs/REVIEW_GATE.md")
                result = subprocess.run(["sh", str(scripts / "review.sh"), "--uncommitted",
                                         "--reviewer", "codex"],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stdout)
                if case != 'archive_failure':
                    reports = list((self.repo / "docs/reviews").glob("*-codex-review.md"))
                    self.assertTrue(reports)
                    newest = max(reports, key=lambda path: path.stat().st_mtime)
                    self.assertEqual(header_of(newest)["model"], "fixture-codex-model")
                    self.assertEqual(verdicts_of(newest),
                                     ["VERDICT: " + case.title()] if expected == 0 else [])
                line = next(line.removeprefix("review invocation: ") for line in result.stdout.splitlines()
                            if line.startswith("review invocation: "))
                metadata = json.loads(line)
                usage = json.loads(Path(metadata["usage_record"]).read_text())
                self.assertEqual(usage["task"]["id"], "fixture-review")
                self.assertEqual(usage["requester_reported"], "claude/fixture")
                if case in ("quota", "timeout"):
                    self.assertEqual(usage["failure_kind"], case)
                if case in ('mutation', 'archive_failure'):
                    self.assertEqual(usage['status'], 'failed')
                    self.assertEqual(usage['failure_kind'], 'stale_checkout' if case == 'mutation' else 'evidence_write_failed')
                if case == "accept":
                    self.assertEqual(usage["usage"]["input_tokens"], 100)
                    self.assertEqual(usage["usage"]["cache_read_tokens"], 90)
                    self.assertTrue(usage["usage"]["input_includes_cache"])
                if expected:
                    self.assertIn("FAIL [review]", result.stdout)

    def build_fake_codex(self):
        """A Codex stand-in that returns one valid Accept; no paid CLI is ever called."""
        fake = self.root / "codex-accept"
        fake.write_text("#!/usr/bin/env python3\n"
                        "import json, os, pathlib, sys\n"
                        "prompt = sys.stdin.read()\n"
                        "if os.environ.get('PROMPT_LOG'): pathlib.Path(os.environ['PROMPT_LOG']).write_text(prompt)\n"
                        "case = os.environ.get('CODEX_FIXTURE_CASE', 'accept')\n"
                        "assert os.environ['MYAGENTKIT_DELEGATION_DEPTH'] == '1'\n"
                        "if case == 'unknown_flag':\n"
                        "    sys.stderr.write(\"error: unexpected argument '--ephemeral' found\\n\"); sys.exit(2)\n"
                        "if case == 'quota':\n"
                        "    print(json.dumps({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}})); sys.exit(1)\n"
                        "verdict = 'Reject' if case == 'reject' else 'Accept'\n"
                        "pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text("
                        "'## Findings\\n\\nFixture finding.\\n\\nVERDICT: ' + verdict + '\\n')\n"
                        "print(json.dumps({'type': 'turn.completed', 'usage': {}}))\n")
        fake.chmod(0o755)
        return fake

    def run_wrapper(self, *argv, **env_extra):
        scripts = self.install_wrapper()
        return subprocess.run(["sh", str(scripts / "review.sh"), *argv],
                              env=self.review_env(**env_extra), capture_output=True, text=True)

    def test_a_stale_per_user_codex_never_shadows_the_one_on_path(self):
        """~/.local/bin is a fallback for a non-login shell, not an override.

        A project's owner had an old standalone build left in ~/.local/bin and a current one
        on PATH; the wrapper put ~/.local/bin FIRST, so every review ran the old binary and
        failed with "requires a newer version" while `codex` at the prompt worked.
        """
        good = self.build_fake_codex()
        bin_dir = self.root / "good-bin"
        bin_dir.mkdir()
        (bin_dir / "codex").symlink_to(good)
        home = self.root / "home"
        stale = home / ".local" / "bin"
        stale.mkdir(parents=True)
        (stale / "codex").write_text("#!/bin/sh\necho 'stale standalone build' >&2; exit 1\n")
        (stale / "codex").chmod(0o755)
        result = self.run_wrapper("--uncommitted", "--reviewer", "codex",
                                  REVIEW_CLI_BIN="codex", HOME=str(home),
                                  PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
                                  REVIEW_CODEX_MODEL="fixture-codex-model")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("stale standalone build", result.stdout + result.stderr)

    def test_both_reviewers_publish_one_identical_evidence_format(self):
        """The hard requirement of a role-neutral kit: swapping roles keeps records comparable.

        Two reviewers that archived two shapes would force every later reader — and the
        self-test — to learn two formats, and no record could be lined up against the one
        that came before it when the roles swapped mid-project.
        """
        claude = self.run_wrapper("--uncommitted", "--reviewer", "claude",
                                  CLAUDE_CLI_BIN=str(self.fixture),
                                  REVIEW_CLAUDE_MODEL="claude-opus-5")
        self.assertEqual(claude.returncode, 0, claude.stdout + claude.stderr)
        codex = self.run_wrapper("--uncommitted", "--reviewer", "codex",
                                 REVIEW_CLI_BIN=str(self.build_fake_codex()),
                                 REVIEW_CODEX_MODEL="fixture-codex-model")
        self.assertEqual(codex.returncode, 0, codex.stdout + codex.stderr)

        reports = sorted((self.repo / "docs/reviews").glob("*-review.md"))
        self.assertEqual(len(reports), 2, reports)
        names = sorted(path.name.split("-", 2)[2] for path in reports)
        self.assertEqual(names, ["claude-review.md", "codex-review.md"])
        first, second = (header_of(path) for path in reports)
        self.assertEqual(list(first), list(agent_usage.REVIEW_FIELDS))
        self.assertEqual(list(first), list(second))
        for path in reports:
            self.assertEqual(verdicts_of(path), ["VERDICT: Accept"])
        self.assertEqual({first["reviewer"], second["reviewer"]}, {"claude", "codex"})
        # The pin is recorded in both directions; neither record may name a CLI default.
        self.assertEqual({first["model"], second["model"]},
                         {"claude-opus-5", "fixture-codex-model"})
        for header in (first, second):
            self.assertNotIn("default", header["model"].lower())

    def test_review_prompt_asks_for_every_finding_and_carries_earlier_rounds(self):
        # Without these asks each fresh pass reported a different top few, and a later round,
        # blind to the earlier ones, re-raised findings the author had disproved or deferred.
        log = self.root / 'prompt.txt'
        asks = ('EVERY finding', 'Critical, High, Medium or Low', 'Fix sketch:')
        task = {'PROMPT_LOG': str(log), 'MYAGENTKIT_TASK_ID': 'rounds-task'}
        code, first = self.run_bridge('reject', env_extra=task)
        self.assertEqual(code, 0, first)
        for ask in asks:
            self.assertIn(ask, log.read_text())
        self.assertNotIn('### Round 1', log.read_text())
        code, second = self.run_bridge('accept', env_extra=task)
        self.assertEqual(code, 0, second)
        self.assertIn('### Round 1', log.read_text())
        self.assertIn('file.py:1: concrete defect', log.read_text())
        self.assertIn('Earlier verdict: Reject', log.read_text())
        # Round 3 through the wrapper, by the other reviewer: both rounds, oldest first.
        notes = self.root / 'dispositions.md'
        notes.write_text('file.py:1 DISPROVED_BY_AUTHOR: the defect needs input the caller rejects.\n')
        result = self.run_wrapper('--reviewer', 'codex', REVIEW_CLI_BIN=str(self.build_fake_codex()),
                                  REVIEW_CODEX_MODEL='fixture-codex-model',
                                  REVIEW_DISPOSITIONS=str(notes), **task)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        prompt = log.read_text()
        for ask in asks:
            self.assertIn(ask, prompt)
        # Oldest first inside the round sections; the templates name every verdict too.
        rounds = re.split(r'^### Round \d+$', prompt.split('\nDiff:\n')[0], flags=re.M)
        self.assertEqual(len(rounds), 3, prompt)
        self.assertIn('Earlier verdict: Reject', rounds[1])
        self.assertIn('Earlier verdict: Accept\n', rounds[2])
        # A carried "VERDICT:" line, echoed by Codex, would break its exactly-one-verdict check.
        self.assertEqual(re.findall(r'^[ \t]*VERDICT[ \t]*:.*$', prompt, re.M), [])
        self.assertIn('DISPROVED_BY_AUTHOR', prompt)
        # Another task label carries nothing; dispositions with no earlier round are refused.
        code, other = self.run_bridge(env_extra=dict(task, MYAGENTKIT_TASK_ID='other-task'))
        self.assertEqual(code, 0, other)
        self.assertNotIn('### Round 1', log.read_text())
        code, refused = self.run_bridge(env_extra=dict(task, MYAGENTKIT_TASK_ID='new-task',
                                                       REVIEW_DISPOSITIONS=str(notes)))
        self.assertEqual(code, 2, refused)
        self.assertIn('no earlier completed review', refused['error'])
        # A lost round record stops the review instead of silently dropping that round.
        Path(first['evidence']).unlink()
        code, missing = self.run_bridge(env_extra=task)
        self.assertEqual(code, 2, missing)
        self.assertIn('earlier review evidence', missing['error'])
        # Through the wrapper both reviewers stop the same way, before any chain is recorded.
        for reviewer in ('claude', 'codex'):
            with self.subTest(reviewer=reviewer):
                result = self.run_wrapper('--reviewer', reviewer, CLAUDE_CLI_BIN=str(self.fixture),
                                          REVIEW_CLAUDE_MODEL='claude-opus-5',
                                          REVIEW_CLI_BIN=str(self.build_fake_codex()),
                                          REVIEW_CODEX_MODEL='fixture-codex-model', **task)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('FAIL [review]: earlier review evidence', result.stdout)

    def test_dispositions_are_claims_the_reviewer_verifies_not_settlements(self):
        # The author never approves its own work: a disproved finding counts only once the
        # reviewer has checked it, and a deferred one stays open, so it cannot end in Accept.
        log = self.root / 'prompt.txt'
        task = {'PROMPT_LOG': str(log), 'MYAGENTKIT_TASK_ID': 'claims-task'}
        self.assertEqual(self.run_bridge('reject', env_extra=task)[0], 0)
        notes = self.root / 'dispositions.md'
        notes.write_text('file.py:1 deferred to the owner.\n')
        code, result = self.run_bridge(env_extra=dict(task, REVIEW_DISPOSITIONS=str(notes)))
        self.assertEqual(code, 0, result)
        prompt = ' '.join(log.read_text().split())
        for wording in ("the author's claims to verify",
                        'counts only after you have checked it against the code',
                        'stays open: list it under Manual checks', 'never a plain Accept'):
            self.assertIn(wording, prompt)
        for wording in ("the author's disposition answers it", 'only with a new argument'):
            self.assertNotIn(wording, prompt)

    def test_earlier_rounds_must_be_the_same_change(self):
        # A reused label from another change must not carry that change's rounds.
        task = {'MYAGENTKIT_TASK_ID': 'reused-task'}
        code, first = self.run_bridge('reject', env_extra=task)
        self.assertEqual(code, 0, first)
        record = Path(first['usage_record'])
        original = json.loads(record.read_text())
        for field, value, named in (('scope', 'base', 'scope'), ('resolved', '1' * 40, 'reference'),
                                    ('head', '0' * 40, 'not HEAD')):
            with self.subTest(field=field):
                changed = json.loads(json.dumps(original))
                changed['task'][field] = value
                record.write_text(json.dumps(changed))
                code, refused = self.run_bridge(env_extra=task)
                self.assertEqual(code, 2, refused)
                self.assertIn(named, refused['error'])
                self.assertIn('new task label', refused['error'])
        record.write_text(json.dumps(original))
        self.assertEqual(self.run_bridge(env_extra=task)[0], 0)

    def test_a_damaged_usage_record_stops_a_labelled_round(self):
        # Skipping it would drop that round's findings unseen: the archive checks never run
        # on a record that was never read, or read as something other than a usage record.
        task = {'MYAGENTKIT_TASK_ID': 'damaged-task'}
        code, first = self.run_bridge('reject', env_extra=task)
        self.assertEqual(code, 0, first)
        record = Path(first['usage_record'])
        original = record.read_text()
        no_evidence = json.dumps(dict(json.loads(original), evidence=''))
        # Shaped like a record, but its fields cannot be trusted to say which task it was:
        # filtered as "another task" they dropped an earlier Reject unseen.
        weird_status = json.dumps(dict(json.loads(original), status='weird'))
        no_head = json.loads(original)
        del no_head['task']['head']
        for damage in ('{"task": ', '[]', '{}', '{"task": "review", "status": "completed"}',
                       '{"task": {}, "status": "completed"}', weird_status,
                       json.dumps(no_head), no_evidence, 'directory', 'mode 000'):
            with self.subTest(damage=damage):
                # A directory fails the read for every user, root included; mode 000 does not
                # stop root, so that variant says it did not run instead of passing silently.
                if damage == 'directory':
                    record.unlink()
                    record.mkdir()
                elif damage == 'mode 000':
                    if os.geteuid() == 0:
                        sys.stderr.write('NOT RUN: unreadable usage record (mode 000) under '
                                         'root; the directory case covers the read failure\n')
                        continue
                    record.chmod(0)
                else:
                    record.write_text(damage)
                try:
                    code, refused = self.run_bridge(env_extra=task)
                finally:
                    if record.is_dir():
                        record.rmdir()
                    else:
                        record.chmod(0o600)
                    record.write_text(original)
                self.assertEqual(code, 2, refused)
                self.assertIn(str(record), refused['error'])
                # Every labelled round reads every record, so a new label meets it again.
                self.assertIn('move it out of .myagentkit/usage', refused['error'])
        self.assertEqual(self.run_bridge(env_extra=task)[0], 0)

    def test_history_controls_exported_by_the_invoking_shell_do_not_reach_the_fixtures(self):
        # Self-tests run from a review loop that exported its dispositions and task label:
        # inherited, they made every fresh synthetic repository fail "no earlier completed
        # review" before its own assertions.
        notes = self.root / 'dispositions.md'
        notes.write_text('Finding 1: disproved.\n')
        result = subprocess.run(
            [sys.executable, '-B', '-m', 'unittest',
             'test_claude_bridge.BridgeTests.test_completed_reviews_keep_verdict_separate_from_process_success',
             'test_claude_bridge.BridgeTests.test_direct_adapters_reject_a_base_ref_that_moves_during_review'],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
            env=dict(os.environ, REVIEW_DISPOSITIONS=str(notes), MYAGENTKIT_TASK_ID='inherited-task'))
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    def test_an_unlistable_usage_directory_stops_a_labelled_round(self):
        # Path.glob() swallows a listing error: a usage directory the owner can write but not
        # list (mode 0300) read as "no earlier rounds" and the next round looked fresh.
        if os.geteuid() == 0:
            sys.stderr.write('NOT RUN: unlistable usage directory (mode 0300) under root\n')
            return
        task = {'MYAGENTKIT_TASK_ID': 'unlistable-task'}
        code, first = self.run_bridge('reject', env_extra=task)
        self.assertEqual(code, 0, first)
        usage = Path(first['usage_record']).parent
        usage.chmod(0o300)
        try:
            code, refused = self.run_bridge(env_extra=task)
        finally:
            usage.chmod(0o700)
        self.assertEqual(code, 2, refused)
        self.assertIn(str(usage), refused['error'])
        self.assertIn('cannot be listed', refused['error'])
        self.assertEqual(self.run_bridge(env_extra=task)[0], 0)

    def test_earlier_rounds_bind_the_change_not_the_reference_text(self):
        # "--commit HEAD" names a different commit once HEAD moves, and an --uncommitted diff
        # that was committed since is replaced by the next one: neither is the reviewed change.
        commit = lambda message: self.git(
            '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-qam', message)
        task = {'MYAGENTKIT_TASK_ID': 'replaced-task'}
        code, first = self.run_bridge('reject', env_extra=task)
        self.assertEqual(code, 0, first)
        commit('the reviewed diff')
        (self.repo / 'file.py').write_text('another change\n')
        code, refused = self.run_bridge(env_extra=task)
        self.assertEqual(code, 2, refused)
        self.assertIn('new task label', refused['error'])
        commit('A')
        task = {'MYAGENTKIT_TASK_ID': 'moving-task'}
        code, first = self.run_bridge('reject', extra=('--commit', 'HEAD'), env_extra=task)
        self.assertEqual(code, 0, first)
        (self.repo / 'file.py').write_text('B\n')
        commit('B')
        code, refused = self.run_bridge(extra=('--commit', 'HEAD'), env_extra=task)
        self.assertEqual(code, 2, refused)
        self.assertIn('new task label', refused['error'])

    def test_an_edited_earlier_round_is_refused(self):
        # The archive is owner-writable; a round edited after the reviewer wrote it is not its evidence.
        log = self.root / 'prompt.txt'
        task = {'PROMPT_LOG': str(log), 'MYAGENTKIT_TASK_ID': 'edited-task'}
        code, first = self.run_bridge('reject', env_extra=task)
        self.assertEqual(code, 0, first)
        evidence = Path(first['evidence'])
        evidence.write_text(evidence.read_text().replace('concrete defect', 'nothing to see'))
        code, refused = self.run_bridge(env_extra=task)
        self.assertEqual(code, 2, refused)
        self.assertIn('changed after it was archived', refused['error'])

    def test_carried_rounds_share_the_diff_budget(self):
        task = {'MYAGENTKIT_TASK_ID': 'budget-task'}
        self.assertEqual(self.run_bridge('reject', env_extra=task)[0], 0)
        notes = self.root / 'dispositions.md'
        notes.write_text('x' * 400_000)
        code, refused = self.run_bridge(env_extra=dict(task, REVIEW_DISPOSITIONS=str(notes)))
        self.assertEqual(code, 2, refused)
        self.assertIn('400000 bytes', refused['error'])
        self.assertIn('fresh MYAGENTKIT_TASK_ID', refused['error'])

    def test_failed_rounds_are_not_carried_and_outside_evidence_is_refused(self):
        log = self.root / 'prompt.txt'
        task = {'PROMPT_LOG': str(log), 'MYAGENTKIT_TASK_ID': 'record-task'}
        code, failed = self.run_bridge('turns', env_extra=task)
        self.assertEqual(code, 5, failed)
        self.assertTrue(failed['evidence'])
        self.assertEqual(self.run_bridge(env_extra=task)[0], 0)
        self.assertNotIn('### Round', log.read_text())
        # A failed round is not carried, but its archive is checked: one changed after the
        # record was written (a cancel relabel that could not replace it) stops the next round.
        evidence = Path(failed['evidence'])
        original = evidence.read_bytes()
        evidence.write_bytes(original + b'edited\n')
        code, refused = self.run_bridge(env_extra=task)
        self.assertEqual(code, 2, refused)
        self.assertIn(str(evidence), refused['error'])
        evidence.write_bytes(original)
        # A completed record whose evidence lies outside docs/reviews is not the reviewer's archive.
        outside = self.root / 'outside-review.md'
        outside.write_text('VERDICT: Accept\n')
        record = Path(self.run_bridge(env_extra=task)[1]['usage_record'])
        value = json.loads(record.read_text())
        value['evidence'] = str(outside)
        record.write_text(json.dumps(value))
        code, refused = self.run_bridge(env_extra=task)
        self.assertEqual(code, 2, refused)
        self.assertIn('earlier review evidence', refused['error'])

    def test_default_reviewer_is_claude_and_codex_remains_explicit(self):
        result = self.run_wrapper('--uncommitted', CLAUDE_CLI_BIN=str(self.fixture),
                                  REVIEW_CLAUDE_MODEL='claude-opus-5', REVIEW_REVIEWER='')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reports = list((self.repo / 'docs/reviews').glob('*-review.md'))
        self.assertEqual(len(reports), 1)
        self.assertEqual(header_of(reports[0])['reviewer'], 'claude')
        explicit = self.run_wrapper('--reviewer', 'codex', '--uncommitted',
                                    REVIEW_CLI_BIN=str(self.build_fake_codex()),
                                    REVIEW_CODEX_MODEL='fixture-codex-model')
        self.assertEqual(explicit.returncode, 0, explicit.stdout + explicit.stderr)
        self.assertEqual(len(list((self.repo / 'docs/reviews').glob('*-codex-review.md'))), 1)

    def test_unavailable_claude_uses_codex_only_with_fallback(self):
        result = self.run_wrapper('--uncommitted', '--fallback', FIXTURE_CASE='quota',
                                  CLAUDE_CLI_BIN=str(self.fixture),
                                  REVIEW_CLAUDE_MODEL='claude-opus-5',
                                  REVIEW_CODEX_MODEL='fixture-codex-model',
                                  REVIEW_CLI_BIN=str(self.build_fake_codex()))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reports = list((self.repo / 'docs/reviews').glob('*-review.md'))
        self.assertEqual(len(reports), 2)
        self.assertEqual({header_of(p)['status'] for p in reports}, {'failed', 'completed'})
        substitute = next(p for p in reports if header_of(p)['reviewer'] == 'codex')
        self.assertIn('FALLBACK REVIEWER: the requested reviewer claude (quota) did not complete',
                      substitute.read_text())
        self.assertIn('FALLBACK [review]: this review is by codex, not the requested claude',
                      result.stdout)

    def dispatch_result(self, primary='claude', fallback=True, **extra):
        env = dict(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLAUDE_MODEL='claude-opus-5',
                   REVIEW_CODEX_MODEL='fixture-codex-model', REVIEW_CLI_BIN=str(self.build_fake_codex()),
                   MYAGENTKIT_REQUESTER='codex/fixture-codex-model', MYAGENTKIT_TASK_ID='fallback-task')
        env.update(extra)
        result = self.run_wrapper('--reviewer', primary, *(['--fallback'] if fallback else []), **env)
        line = next((s.removeprefix('review dispatch: ') for s in result.stdout.splitlines()
                     if s.startswith('review dispatch: ')), None)
        return result, json.loads(line) if line else None

    def test_failover_preserves_pins_scope_usage_and_advisory_status(self):
        for primary in ('claude', 'codex'):
            result, chain = self.dispatch_result(primary, **(
                {'FIXTURE_CASE': 'quota'} if primary == 'claude' else {'CODEX_FIXTURE_CASE': 'quota'}))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(chain['attempts']), 2)
            self.assertEqual(chain['attempts'][0]['failure_kind'], 'quota')
            self.assertNotEqual(chain['selected_reviewer'], primary)
            self.assertFalse(chain['review_approved'])
            self.assertEqual(chain['independence'], 'host_must_check_all_patch_authors')
            self.assertEqual(json.loads(Path(chain['chain_record']).read_text()), chain)
            headers = [header_of(a['evidence']) for a in chain['attempts']]
            self.assertEqual(headers[0]['fingerprint'], headers[1]['fingerprint'])
            self.assertEqual(headers[0]['diff_sha256'], headers[1]['diff_sha256'])
            evidence = [Path(a['evidence']).read_text() for a in chain['attempts']]
            self.assertNotIn('FALLBACK REVIEWER', evidence[0])
            self.assertIn('FALLBACK REVIEWER: the requested reviewer %s (quota)' % primary, evidence[1])
            for i, attempt in enumerate(chain['attempts'], 1):
                usage = json.loads(Path(attempt['usage_record']).read_text())
                self.assertEqual(usage['review_fallback_from'], None if i == 1 else primary + ' (quota)')
                self.assertEqual(usage['review_chain_id'], chain['chain_id'])
                self.assertEqual(usage['review_attempt'], str(i))
                self.assertEqual(usage['task']['id'], 'fallback-task')
                self.assertEqual(usage['model_requested'], chain['configured_models'][attempt['reviewer']])
                self.assertEqual(usage['requester_reported'], 'codex/fixture-codex-model')

    def test_operational_failures_try_other_model_once(self):
        cases = {'auth': 'authentication', 'context': 'context_limit', 'turns': 'budget_or_turn_limit',
                 'timeout': 'timeout', 'exit': 'cli_error'}
        for case, kind in cases.items():
            with self.subTest(case=case):
                result, chain = self.dispatch_result(FIXTURE_CASE=case, REVIEW_TIMEOUT_SECONDS='1')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(chain['attempts'][0]['failure_kind'], kind)
                self.assertEqual(len(chain['attempts']), 2)
        for provider, variable in [('claude', 'CLAUDE_CLI_BIN'), ('codex', 'REVIEW_CLI_BIN')]:
            result, chain = self.dispatch_result(provider, **{variable: str(self.root / 'missing-cli')})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(chain['attempts'][0]['failure_kind'], 'unavailable')

    def test_a_requested_reviewer_is_never_replaced_without_fallback(self):
        # The requested reviewer is usually the model that did NOT write the patch. Swapping
        # it silently for the other one can mean the author reviewing itself under a valid-
        # looking record, so without --fallback an unavailable reviewer fails the review.
        for primary, case in (('claude', {'FIXTURE_CASE': 'quota'}),
                              ('codex', {'CODEX_FIXTURE_CASE': 'quota'})):
            with self.subTest(primary=primary):
                result, chain = self.dispatch_result(primary, fallback=False, **case)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual([a['reviewer'] for a in chain['attempts']], [primary])
                self.assertIn('not requested', chain['fallback_blocked'])
                self.assertIn('FAIL [review]: requested reviewer %s did not produce a review' % primary,
                              result.stdout)
        # A CLI that rejects a flag the read-only run needs fails the same way every time:
        # it is a setup fault, so not even --fallback routes around it.
        # Claude says "unknown option", Codex "unexpected argument": both are the setup fault.
        for primary, case in (('claude', {'FIXTURE_CASE': 'unknown_flag'}),
                              ('codex', {'CODEX_FIXTURE_CASE': 'unknown_flag'})):
            with self.subTest(primary=primary, unsupported=True):
                result, chain = self.dispatch_result(primary, **case)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual([a['reviewer'] for a in chain['attempts']], [primary])
                self.assertEqual(chain['failure_kind'], 'cli_unsupported')
                self.assertIn('upgrade the CLI', result.stdout)

    def test_cancelled_review_stops_the_reviewer_records_usage_and_never_fails_over(self):
        # SIGTERM and SIGHUP used to end the dispatcher without its cleanup, leaving the paid
        # reviewer's process group running; Ctrl-C lost the failed attempt's usage record.
        import select
        import signal
        import time
        hanging = self.root / 'hanging-cli'
        hanging.write_text(HANGING_CLI)
        hanging.chmod(0o755)
        for provider, sig in (('claude', signal.SIGINT), ('claude', signal.SIGTERM),
                              ('claude', signal.SIGHUP), ('codex', signal.SIGINT),
                              ('codex', signal.SIGTERM)):
            with self.subTest(provider=provider, sig=sig.name):
                fifo = self.root / ('alive-%s-%s' % (provider, sig.name))
                os.mkfifo(fifo)
                reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
                self.addCleanup(os.close, reader)
                scripts = self.install_wrapper()
                clis = dict(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLI_BIN=str(self.build_fake_codex()))
                clis['CLAUDE_CLI_BIN' if provider == 'claude' else 'REVIEW_CLI_BIN'] = str(hanging)
                env = self.review_env(ALIVE_FIFO=str(fifo), REVIEW_CLAUDE_MODEL='claude-opus-5',
                                      REVIEW_CODEX_MODEL='fixture-codex-model', **clis)
                review = subprocess.Popen(['sh', str(scripts / 'review.sh'), '--reviewer', provider, '--fallback'],
                                          env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                self.addCleanup(lambda p=review: p.poll() is None and p.kill())

                def read_until(done):
                    deadline, seen = time.monotonic() + 20, b''
                    while time.monotonic() < deadline:
                        select.select([reader], [], [], 0.2)
                        try:
                            chunk = os.read(reader, 64)
                        except BlockingIOError:
                            continue
                        seen += chunk
                        if done(seen, chunk):
                            return True
                        if not chunk:
                            if review.poll() is not None:
                                return False   # the review ended before its reviewer started
                            time.sleep(0.05)   # no writer has opened the FIFO yet
                    return False

                self.assertTrue(read_until(lambda seen, chunk: b'started' in seen), 'reviewer never started')
                review.send_signal(sig)
                output = review.communicate(timeout=30)[0]
                # EOF on the FIFO means no process still holds it: the CLI and its child are gone.
                self.assertTrue(read_until(lambda seen, chunk: chunk == b''),
                                'the reviewer process group outlived the cancelled review')
                self.assertNotEqual(review.returncode, 0, output)
                chain = json.loads(next(line.removeprefix('review dispatch: ') for line in output.splitlines()
                                        if line.startswith('review dispatch: ')))
                self.assertEqual([a['reviewer'] for a in chain['attempts']], [provider])
                self.assertEqual(chain['failure_kind'], 'cancelled')
                usage = json.loads(Path(chain['attempts'][0]['usage_record']).read_text())
                self.assertEqual((usage['status'], usage['failure_kind']), ('failed', 'cancelled'))
                self.assertEqual(verdicts_of(chain['attempts'][0]['evidence']), [])

    def test_a_cancel_during_the_closing_quota_read_keeps_the_completed_attempt(self):
        # The quota read after the review ran with the default handlers back in place, so a
        # SIGTERM there ended the adapter before the paid, completed review was recorded.
        # After a FAILED attempt the cancel was recorded only in the quota snapshot: the
        # attempt kept its eligible failure and --fallback launched the other paid reviewer.
        import select
        import signal
        import time
        reviewer = self.root / 'codex-slow-quota'
        reviewer.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys, time\n"
            "if sys.argv[1] == 'app-server':\n"
            "    seen = pathlib.Path(os.environ['QUOTA_SEEN'])\n"
            "    if not seen.exists():\n"
            "        seen.write_text('before')\n"
            "        sys.exit(0)\n"
            "    alive = os.open(os.environ['ALIVE_FIFO'], os.O_WRONLY)\n"
            "    os.write(alive, b'started\\n')\n"
            "    time.sleep(60)\n"
            "sys.stdin.read()\n"
            "if os.environ.get('FAIL_QUOTA'):\n"
            "    print(json.dumps({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}))\n"
            "    sys.exit(1)\n"
            "pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text("
            "'## Findings\\n\\nNone.\\n\\nVERDICT: Accept\\n')\n"
            "print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 3}}))\n")
        reviewer.chmod(0o755)
        second = self.root / 'claude-second'
        launched = self.root / 'second-launched'
        second.write_text('#!/bin/sh\n: > "%s"\nexit 1\n' % launched)
        second.chmod(0o755)
        scripts = self.install_wrapper()
        for failing in (False, True):
            with self.subTest(failing=failing):
                fifo = self.root / ('alive-quota-%s' % failing)
                os.mkfifo(fifo)
                reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
                self.addCleanup(os.close, reader)
                seen = self.root / ('quota-seen-%s' % failing)
                env = self.review_env(ALIVE_FIFO=str(fifo), QUOTA_SEEN=str(seen),
                                      MYAGENTKIT_CAPTURE_QUOTA='1', REVIEW_CLI_BIN=str(reviewer),
                                      REVIEW_CODEX_MODEL='fixture-codex-model',
                                      REVIEW_CLAUDE_MODEL='claude-opus-5', CLAUDE_CLI_BIN=str(second),
                                      FAIL_QUOTA='1' if failing else '')
                review = subprocess.Popen(['sh', str(scripts / 'review.sh'), '--reviewer', 'codex',
                                           '--fallback'],
                                          env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                self.addCleanup(lambda p=review: p.poll() is None and p.kill())

                def read_until(done):
                    deadline, seen = time.monotonic() + 20, b''
                    while time.monotonic() < deadline:
                        select.select([reader], [], [], 0.2)
                        try:
                            chunk = os.read(reader, 64)
                        except BlockingIOError:
                            continue
                        seen += chunk
                        if done(seen, chunk):
                            return True
                        if not chunk:
                            if review.poll() is not None:
                                return False
                            time.sleep(0.05)
                    return False

                self.assertTrue(read_until(lambda seen, chunk: b'started' in seen), 'quota read never started')
                review.send_signal(signal.SIGTERM)
                output = review.communicate(timeout=30)[0]
                self.assertTrue(read_until(lambda seen, chunk: chunk == b''),
                                'the quota reader outlived the cancel')
                self.assertFalse(launched.exists(), 'a cancelled review launched the other reviewer:\n' + output)
                line = next((line.removeprefix('review invocation: ') for line in output.splitlines()
                             if line.startswith('review invocation: ')), None)
                self.assertIsNotNone(line, output)
                usage = json.loads(Path(json.loads(line)['usage_record']).read_text())
                self.assertEqual((usage['status'], usage['failure_kind']),
                                 ('failed', 'cancelled') if failing else ('completed', None))
                self.assertEqual(usage['usage']['account_quota_snapshots']['after']['status'], 'cancelled')
                if not failing:
                    self.assertEqual(usage['usage']['input_tokens'], 3)
                else:
                    chain = json.loads(next(line.removeprefix('review dispatch: ') for line in output.splitlines()
                                            if line.startswith('review dispatch: ')))
                    self.assertEqual([a['reviewer'] for a in chain['attempts']], ['codex'])
                    self.assertEqual(chain['failure_kind'], 'cancelled')

    def test_a_cancel_during_the_claude_final_snapshot_keeps_the_usage_record(self):
        # The Claude adapter restored the default handlers when the reviewer exited, so a
        # SIGTERM while it hashed the checkout for the stale check ended it before the paid
        # review's evidence and usage were written. A fake git on PATH holds that snapshot.
        import select
        import shutil
        import signal
        import time
        fifo = self.root / 'alive-final'
        os.mkfifo(fifo)
        reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        self.addCleanup(os.close, reader)
        mark, tools = self.root / 'reviewer-ran', self.root / 'slow-git'
        tools.mkdir()
        (tools / 'git').write_text('#!/bin/sh\nif [ -e "%s" ] && mkdir "%s.once" 2>/dev/null; then\n'
                                   '  printf \'started\\n\' > "%s"\n  sleep 2\nfi\nexec "%s" "$@"\n'
                                   % (mark, mark, fifo, shutil.which('git')))
        (tools / 'git').chmod(0o755)
        reviewer = self.root / 'claude-marking'
        reviewer.write_text('#!/bin/sh\n: > "%s"\nexec "%s" "$@"\n' % (mark, self.fixture))
        reviewer.chmod(0o755)
        scripts = self.install_wrapper()
        env = self.review_env(CLAUDE_CLI_BIN=str(reviewer), REVIEW_CLAUDE_MODEL='claude-opus-5',
                              PATH=str(tools) + os.pathsep + os.environ['PATH'])
        review = subprocess.Popen(['sh', str(scripts / 'review.sh'), '--reviewer', 'claude'],
                                  env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(lambda: review.poll() is None and review.kill())
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and review.poll() is None:
            select.select([reader], [], [], 0.2)
            try:
                if b'started' in os.read(reader, 64):
                    break
            except BlockingIOError:
                pass
        else:
            self.fail('the final snapshot never started')
        review.send_signal(signal.SIGTERM)
        output = review.communicate(timeout=30)[0]
        chain = json.loads(next((line.removeprefix('review dispatch: ') for line in output.splitlines()
                                 if line.startswith('review dispatch: ')), 'null'))
        self.assertIsNotNone(chain, output)
        usage = json.loads(Path(chain['attempts'][0]['usage_record']).read_text())
        self.assertEqual((usage['status'], usage['failure_kind']), ('completed', None))

    def test_both_unavailable_stop_after_two_and_keep_review_pending(self):
        result, chain = self.dispatch_result(FIXTURE_CASE='quota', CODEX_FIXTURE_CASE='quota')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(chain['attempts']), 2)
        self.assertEqual(chain['status'], 'failed')
        self.assertFalse(chain['review_approved'])
        self.assertEqual(chain['recovery']['action'], 'continue_independent_work')
        for attempt in chain['attempts']:
            self.assertEqual(verdicts_of(attempt['evidence']), [])

    def test_completed_reject_or_manual_checks_never_trigger_failover(self):
        for case in ('reject', 'manual', 'no_budget'):
            result, chain = self.dispatch_result(FIXTURE_CASE=case)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(chain['attempts']), 1)
        result, chain = self.dispatch_result('codex', CODEX_FIXTURE_CASE='reject')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(chain['attempts']), 1)

    def test_invalid_evidence_or_changed_checkout_cannot_failover(self):
        for case in ('missing', 'model', 'mutation', 'quota_mutation'):
            result, chain = self.dispatch_result(FIXTURE_CASE=case)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(len(chain['attempts']), 1)
            self.assertIn(chain['failure_kind'], ('invalid_evidence', 'stale_checkout'))
            if 'mutation' in case:
                # Failing is right; a bare "stale_checkout" left the caller guessing what to change.
                self.assertEqual(chain['failure_kind'], 'stale_checkout')
                self.assertIn('the checkout changed while the review ran', result.stdout)

    def test_unconfigured_alternate_does_not_choose_a_default_model(self):
        result, chain = self.dispatch_result(FIXTURE_CASE='quota', REVIEW_CODEX_MODEL='')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(chain['attempts']), 1)
        self.assertIn('configured model pin', chain['fallback_blocked'])

    def test_chain_persistence_failure_prevents_second_model_call(self):
        result, chain = self.dispatch_result(FIXTURE_CASE='chain_failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(chain)
        self.assertFalse(list((self.repo / 'docs/reviews').glob('*-codex-review.md')))
        self.assertEqual(len(list((self.repo / '.myagentkit/usage').glob('*.json'))), 1)

    def test_evidence_persistence_failure_prevents_second_model_call(self):
        result, chain = self.dispatch_result(FIXTURE_CASE='archive_failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(chain['attempts']), 1)
        self.assertEqual(chain['failure_kind'], 'evidence_write_failed')

    def test_an_unpinned_model_is_refused_in_both_directions(self):
        # The shipped template pins NEITHER model: setup must answer both. This runs the
        # wrapper exactly as it ships, so the refusal is the out-of-the-box behaviour.
        for reviewer in ("codex", "claude"):
            with self.subTest(reviewer=reviewer):
                result = self.run_wrapper("--uncommitted", "--reviewer", reviewer)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("no model pinned for reviewer '%s'" % reviewer, result.stdout)
        # Defence in depth: the adapter refuses an empty pin even when called directly.
        scripts = self.install_wrapper()
        direct = subprocess.run([sys.executable, "-B", str(scripts / "codex_bridge.py"),
                                 "--repo", str(self.repo), "--model", "", "--uncommitted"],
                                env=self.review_env(), capture_output=True, text=True)
        self.assertEqual(direct.returncode, 5, direct.stdout)
        self.assertIn("--model must pin one model id", direct.stdout)

    def test_the_wrapper_accepts_no_reviewer_it_cannot_name(self):
        for argv in (["--uncommitted", "--reviewer", "gemini"],
                     ["--uncommitted", "--reviewer", "--dangerously-skip-permissions"]):
            with self.subTest(argv=argv):
                result = self.run_wrapper(*argv, REVIEW_CODEX_MODEL="fixture-codex-model")
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("--reviewer must be codex or claude", result.stdout)
        # No pass-through: an unknown flag is a usage error, never forwarded to a CLI.
        for argv in (["--uncommitted", "--sandbox", "danger-full-access"],
                     ["--reviewer"], ["--commit"], ["--uncommitted", "--uncommitted"]):
            with self.subTest(argv=argv):
                result = self.run_wrapper(*argv, REVIEW_CODEX_MODEL="fixture-codex-model")
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("usage: review.sh", result.stdout)

    def test_the_shared_renderer_refuses_a_drifted_header_or_a_verdict_without_a_run(self):
        """The format is enforced, not agreed. An adapter cannot quietly grow a column."""
        good = dict.fromkeys(agent_usage.REVIEW_FIELDS, "x")
        good["status"] = "completed"
        self.assertIn("VERDICT: Reject", agent_usage.report("S", good, "Reject", "body"))
        for header in [{k: v for k, v in good.items() if k != "scope"},
                       dict(good, extra="drifted"),
                       {k: good[k] for k in reversed(agent_usage.REVIEW_FIELDS)}]:
            with self.assertRaises(ValueError):
                agent_usage.report("S", header, "Accept", "body")
        with self.assertRaises(ValueError):
            agent_usage.report("S", dict(good, status="failed"), "Accept", "body")
        with self.assertRaises(ValueError):
            agent_usage.report("S", good, "Looks fine to me", "body")


if __name__ == "__main__":
    from test_agent_usage import UsageTests
    from test_codex_quota import QuotaTests
    suite = unittest.TestSuite()
    for case, name in ((BridgeTests, 'test_claude_bridge'), (UsageTests, 'test_agent_usage'),
                       (QuotaTests, 'test_codex_quota')):
        minimum = SUITE_MINIMUMS[name]
        tests = unittest.defaultTestLoader.loadTestsFromTestCase(case)
        if tests.countTestCases() < minimum:
            raise SystemExit("FAIL: %s has %d of at least %d tests; a suite that did not run is "
                             "not a pass" % (case.__name__, tests.countTestCases(), minimum))
        suite.addTests(tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped:
        raise SystemExit(1)
    print("REVIEW SELF-TEST: PASS")
