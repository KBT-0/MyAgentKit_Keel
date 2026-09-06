"""Offline end-to-end evidence and permission regressions; never calls a paid CLI."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent_usage

ROOT = Path(__file__).resolve().parent
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
case = os.environ.get('FIXTURE_CASE', 'accept')
model = args[args.index('--model') + 1]
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

        def capture(command, prompt, repo, timeout):
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
            (scripts / "review.sh").write_bytes((ROOT / "review.sh").read_bytes())
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
                        "sys.stdin.read()\n"
                        "case = os.environ.get('CODEX_FIXTURE_CASE', 'accept')\n"
                        "assert os.environ['MYAGENTKIT_DELEGATION_DEPTH'] == '1'\n"
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

    def test_unavailable_claude_automatically_uses_selected_codex(self):
        result = self.run_wrapper('--uncommitted', FIXTURE_CASE='quota',
                                  CLAUDE_CLI_BIN=str(self.fixture),
                                  REVIEW_CLAUDE_MODEL='claude-opus-5',
                                  REVIEW_CODEX_MODEL='fixture-codex-model',
                                  REVIEW_CLI_BIN=str(self.build_fake_codex()))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reports = list((self.repo / 'docs/reviews').glob('*-review.md'))
        self.assertEqual(len(reports), 2)
        self.assertEqual({header_of(p)['status'] for p in reports}, {'failed', 'completed'})

    def dispatch_result(self, primary='claude', **extra):
        env = dict(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLAUDE_MODEL='claude-opus-5',
                   REVIEW_CODEX_MODEL='fixture-codex-model', REVIEW_CLI_BIN=str(self.build_fake_codex()),
                   MYAGENTKIT_REQUESTER='codex/fixture-codex-model', MYAGENTKIT_TASK_ID='fallback-task')
        env.update(extra)
        result = self.run_wrapper('--reviewer', primary, **env)
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
            for i, attempt in enumerate(chain['attempts'], 1):
                usage = json.loads(Path(attempt['usage_record']).read_text())
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
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BridgeTests)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(UsageTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(QuotaTests))
    if suite.countTestCases() < 51:
        raise SystemExit("FAIL: expected at least fifty-one review and usage regression tests")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped:
        raise SystemExit(1)
    print("REVIEW SELF-TEST: PASS")
