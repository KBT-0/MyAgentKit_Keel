# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
"""Offline end-to-end evidence and permission regressions; never calls a paid CLI."""
import hashlib
import importlib.util
import io
import json
import os
import re
from pathlib import Path
from contextlib import ExitStack
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent_usage

ROOT = Path(__file__).resolve().parent
# The ignore rules the fixtures need (the kit's own file, trimmed to its private-store rules). A
# fixture never copies the PROJECT's .gitignore: a project that ignores .env hid the secret-file
# fixtures' planted files, and the kit's secret tests failed in it (issue #91).
IGNORE_RULES = b'''.DS_Store
Thumbs.db
desktop.ini
__pycache__/
*.py[cod]
.claude/worktrees/
/QUESTION-*.md
*.md.question.md
/.[Mm][Yy][Aa][Gg][Ee][Nn][Tt][Kk][Ii][Tt]/
/.myagentkit/backends/
/docs/reviews/????????T??????Z-*.md
/docs/handoffs/*-claude-propose.json
/docs/reviews/*-claude-review.json
*/settings.local.json
!/docs/reviews/*-summary.md
'''
INHERITED_CONTROLS = ('REVIEW_DISPOSITIONS', 'REVIEW_SHADOW', 'MYAGENTKIT_TASK_ID', 'MYAGENTKIT_REVIEW_CHAIN_ID',
                      'MYAGENTKIT_REVIEW_ATTEMPT', 'MYAGENTKIT_REVIEW_FALLBACK_FROM',
                      'MYAGENTKIT_REQUESTER', 'CLAUDE_REVIEW_DOCS', 'MYAGENTKIT_NO_BEHAVIOUR', 'MYAGENTKIT_BACKEND',
                      # The lead's author claim: an exported one refused the fixtures' reviewer pin.
                      'MYAGENTKIT_AUTHOR', 'MYAGENTKIT_AUTHOR_EFFORT', 'REVIEW_SAME_TIER_EXCEPTION', 'MYAGENTKIT_ALLOW_SECRET_FILES',
                      # Set by the dispatcher for a reviewer under the exception: its own test run
                      # marked the fixture rounds and refused their second one.
                      'MYAGENTKIT_REVIEW_SAME_TIER',
                      # A worker's brief: review.sh checked every fixture diff against its Owns: line.
                      'REVIEW_TASK_FILE',
                      # A review loop's tier, focus and effort: REVIEW_RISK=high changed the default
                      # effort the effort tests assert. A test that needs one passes it.
                      'REVIEW_RISK', 'REVIEW_FOCUS', 'REVIEW_EFFORT')
# Per suite, not a combined total: as one suite grew, an emptied neighbour could hide inside
# the sum and the self-test passed without running its checks. Each is the suite's current
# count, so a suite that loses a test fails too; a new test raises it. The kit gate reads this.
SUITE_MINIMUMS = {'test_claude_bridge': 283, 'test_agent_usage': 39, 'test_codex_quota': 6}
# These are executed cases, excluding only the explicitly declared POSIX exclusions.
WINDOWS_SUITE_MINIMUMS = {'test_claude_bridge': 256, 'test_agent_usage': 35, 'test_codex_quota': 5}
BRIDGE = ROOT / "claude_bridge.py"
spec = importlib.util.spec_from_file_location("bridge", BRIDGE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

from review_test_support import (PYTHON_SHEBANG, WINDOWS, fixture_source, send_cancel,
                                 python_cli, posix_only, platform_skips, test_cases)

FIXTURE = PYTHON_SHEBANG + '''import json, os, pathlib, sys, time
args = sys.argv[1:]
# A review executes in the throwaway copy; a proposal stays read-only.
review = 'verdict' in args[args.index('--json-schema') + 1]
# The review's Bash runs only in Claude Code's sandbox, which refuses to start without one;
# native Windows has no such sandbox, so a review there gets no Bash at all.
bash = review and os.name == 'posix'
assert args[args.index('--tools') + 1] == ('Read,Glob,Grep,Bash' if bash else 'Read,Glob,Grep')
assert (args[args.index('--allowed-tools') + 1] == 'Bash') if bash else '--allowed-tools' not in args
assert (json.loads(args[args.index('--settings') + 1])['sandbox']['failIfUnavailable'] is True) if bash else 'sandbox' not in json.loads(args[args.index('--settings') + 1])
assert args[args.index('--permission-mode') + 1] == 'dontAsk'
assert '--safe-mode' in args and '--restricted' in args
assert '--strict-mcp-config' in args and '--no-session-persistence' in args
assert '--dangerously-skip-permissions' not in args
assert '--resume' not in args and '--continue' not in args
assert os.environ['MYAGENTKIT_DELEGATION_DEPTH'] == '1'
prompt = sys.stdin.buffer.read().decode('utf-8')  # the bridge sends UTF-8
if os.environ.get('PROMPT_LOG'): pathlib.Path(os.environ['PROMPT_LOG']).write_text(prompt, encoding='utf-8')
if os.environ.get('FIXTURE_UNLINK'): pathlib.Path(os.environ['FIXTURE_UNLINK']).unlink()
if os.environ.get('ENV_LOG'): pathlib.Path(os.environ['ENV_LOG']).write_text(json.dumps(
    {k: v for k, v in os.environ.items() if k.startswith('ANTHROPIC_')}))
case = os.environ.get('FIXTURE_CASE', 'accept')
# The real repository, reached by its absolute path: what a reviewer escaping its copy does.
repo = pathlib.Path(os.environ.get('FIXTURE_REPO', '.'))
if os.environ.get('CWD_LOG'):
    pathlib.Path('reviewer-wrote.txt').write_text('written by the reviewer')
    pathlib.Path(os.environ['CWD_LOG']).write_text(json.dumps(
        {'cwd': os.getcwd(), 'file': pathlib.Path('file.py').read_text(),
         'new': pathlib.Path('new file.txt').read_text() if pathlib.Path('new file.txt').exists() else None,
         'leaks': sorted(k for k, v in os.environ.items() if k != 'FIXTURE_REPO' and str(repo) in v)}))
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
if case == 'conflict': value['verdict'] = 'Reject'
if case == 'turns': result['subtype'] = 'error_max_turns'
if case == 'model': result['modelUsage'] = {'different-model': {}}
if case == 'error': result['is_error'] = True
# A valid review in an envelope that also names an API error status on its final result.
if case.startswith('api_'): result['api_error_status'] = int(case[4:])
if case == 'exit': print(json.dumps(result)); sys.exit(9)
if case == 'mutation': (repo / 'file.py').write_text('changed during review')
if os.environ.get('APPENDIX_LOG'):
    pathlib.Path(os.environ['APPENDIX_LOG']).write_text(
        pathlib.Path('BEHAVIOUR.md').read_bytes().hex())
if case == 'behaviour_mutation': (repo / 'BEHAVIOUR.md').write_bytes(b'changed during review\\n')
if case == 'kit_docs': assert 'core/docs/ARCHITECTURE.md' in prompt
if case == 'archive_failure':
    (repo / 'docs/reviews').rmdir()
    (repo / 'docs/reviews').write_text('blocked archive')
if case == 'timeout': time.sleep(20)
if case == 'partial_timeout': print(json.dumps(result), flush=True); time.sleep(120)
if case == 'quota':
    result.update(is_error=True, api_error_status=429, result='Session limit reached; resets later')
    print(json.dumps(result)); sys.exit(1)
if case in ('auth', 'context'):
    result.update(is_error=True, result='authentication failed' if case == 'auth' else 'context exhausted')
    print(json.dumps(result)); sys.exit(1)
if case == 'quota_mutation':
    (repo / 'file.py').write_text('changed while failing')
    result.update(is_error=True, api_error_status=429)
    print(json.dumps(result)); sys.exit(1)
if case == 'chain_failure':
    import shutil
    shutil.rmtree(repo / '.myagentkit/usage/chains')
    (repo / '.myagentkit/usage/chains').write_text('blocked chain')
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

HANGING_CLI = PYTHON_SHEBANG + '''import os, pathlib, subprocess, sys, time
sys.stdin.read()
if os.environ.get('CWD_LOG'): pathlib.Path(os.environ['CWD_LOG']).write_text(os.getcwd())
alive = os.open(os.environ['ALIVE_FIFO'], os.O_WRONLY)
subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], pass_fds=(alive,))
os.write(alive, b'started\\n')
time.sleep(60)
'''


def run_quietly(suite, out=sys.stdout, minimum=0):
    """Run a suite; print its whole log on failure, declared skips and a summary otherwise.

    The per-test lines of a passing run were about 17 KB in every gate run, read by the
    agent that ran it. A failing run still prints every line, the passing ones included.
    """
    allowed = platform_skips(suite)
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    executed = result.testsRun - len(result.skipped)
    unexpected = [test.id() for test, _ in result.skipped if test.id() not in allowed]
    if not result.wasSuccessful() or unexpected or executed < minimum:
        out.write(log.getvalue())
        out.write('Executed %d tests; minimum %d; unexpected skips %r\n' % (executed, minimum, unexpected))
        return False
    for test, reason in result.skipped:
        out.write('NOT RUN: %s (%s)\n' % (test.id(), reason))
    out.write("Ran %d tests: OK\n" % executed)
    return True


def run_review_shard(manifest, report):
    """Run one assigned list in this fresh interpreter and report every started case."""
    ids = json.loads(Path(manifest).read_text(encoding='utf-8'))
    suite = unittest.defaultTestLoader.loadTestsFromNames(ids)
    if not ids or len(set(ids)) != len(ids) or [test.id() for test in test_cases(suite)] != ids:
        raise SystemExit('FAIL: invalid review shard manifest')

    class RecordedResult(unittest.TextTestResult):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.ids = []

        def startTest(self, test):
            self.ids.append(test.id())
            super().startTest(test)

    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(suite)
    Path(report).write_text(json.dumps(dict(ids=result.ids,
        executed=result.testsRun - len(result.skipped),
        skipped=[(test.id(), reason) for test, reason in result.skipped],
        successful=result.wasSuccessful())), encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


def keep_output_writable(stream):
    """A failing shard's output holds characters (U+FFFD) a console code page such as cp1252
    cannot encode: the write raised and hid the failure it was reporting (issue #163)."""
    reconfigure = getattr(stream, 'reconfigure', None)
    if reconfigure:
        reconfigure(errors='replace')


def run_review_shards(suite, out=sys.stdout, minimum=0, timeout=None):
    """Run alternating sorted IDs in two processes; require complete, unique coverage."""
    import agent_process
    ids = sorted(test.id() for test in test_cases(suite))
    allowed = platform_skips(suite)
    if len(ids) < 2 or len(set(ids)) != len(ids):
        out.write('FAIL: review shards require at least two unique test IDs\n')
        return False
    shards = [ids[::2], ids[1::2]]
    with tempfile.TemporaryDirectory(prefix='review-shards-') as tmp:
        folder = Path(tmp)
        for index, assigned in enumerate(shards):
            (folder / ('%d-input.json' % index)).write_text(json.dumps(assigned), encoding='utf-8')

        # The parent owns both handles. Threaded supervisors cannot receive its SIGINT,
        # and executor shutdown would wait for their entire timeout before re-raising it.
        with ExitStack() as streams:
            children, outputs, exited = [], [], []
            seconds = (1200 if WINDOWS else 300) * float(os.environ.get('MYAGENTKIT_TEST_TIMEOUT_SCALE', '1'))
            deadline = time.monotonic() + (seconds if timeout is None else timeout)
            try:
                for index in range(2):
                    stdout = streams.enter_context(tempfile.TemporaryFile())
                    stderr = streams.enter_context(tempfile.TemporaryFile())
                    outputs.append((stdout, stderr))
                    command = [sys.executable, '-B', str(Path(__file__).resolve()), '--review-shard',
                               str(folder / ('%d-input.json' % index)), str(folder / ('%d-result.json' % index))]
                    mask = agent_process.block_cancels()
                    try:
                        children.append(agent_process.launch(command, mask, cwd=ROOT,
                                        stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr))
                    finally:
                        agent_process.restore_mask(mask)
                for child in children:
                    # Poll the seam's non-reaping wait so Python can deliver a parent cancel
                    # on Windows too; files keep either shard's output from blocking a pipe.
                    while not agent_process._exited_unreaped(child, 0.1):
                        if time.monotonic() >= deadline:
                            exited.append(False)
                            break
                    else:
                        exited.append(True)
            finally:
                mask = agent_process.block_cancels()
                try:
                    # ExitStack attempts both tree cleanups even if one cleanup raises.
                    with ExitStack() as cleanup:
                        for child in children:
                            cleanup.callback(agent_process.stop_group, child, child.pid)
                finally:
                    agent_process.restore_mask(mask)
            results = []
            for child, (stdout, stderr), done in zip(children, outputs, exited):
                stdout.seek(0)
                stderr.seek(0)
                results.append(dict(exit_code=child.returncode, termination=None if done else 'timeout',
                                    stdout=stdout.read().decode(errors='replace'),
                                    stderr=stderr.read().decode(errors='replace')))
        executed, seen, skipped = 0, [], []
        try:
            for index, (assigned, result) in enumerate(zip(shards, results)):
                if result['exit_code'] != 0 or result['termination'] or result.get('cancelled'):
                    raise ValueError('shard %d exited %r (%s)' %
                                     (index + 1, result['exit_code'], result['termination']))
                report = json.loads((folder / ('%d-result.json' % index)).read_text(encoding='utf-8'))
                reported = report['ids']
                excluded = [item[0] for item in report['skipped']]
                if reported != assigned or len(set(reported)) != len(reported):
                    raise ValueError('shard %d lost or duplicated test IDs' % (index + 1))
                if (len(set(excluded)) != len(excluded) or not set(excluded) <= allowed & set(assigned)
                        or report['executed'] != len(reported) - len(excluded)
                        or report['executed'] <= 0 or report['successful'] is not True):
                    raise ValueError('shard %d has invalid executed counts, skips or success' % (index + 1))
                seen.extend(reported)
                executed += report['executed']
                skipped.extend(report['skipped'])
            if len(set(seen)) != len(ids) or sorted(seen) != ids or executed < minimum:
                raise ValueError('executed %d tests; minimum %d; coverage must be complete and unique' %
                                 (executed, minimum))
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            for result in results:
                out.write(result['stdout'] + result['stderr'])
            out.write('FAIL: review shards: %s\n' % error)
            return False
    for test_id, reason in skipped:
        out.write('NOT RUN: %s (%s)\n' % (test_id, reason))
    out.write('Ran %d tests: OK (two review shards)\n' % executed)
    return True


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


class ReviewPreflightTests(unittest.TestCase):
    def test_shard_deadline_scales_with_the_test_timeout_environment(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        base = 1200 if WINDOWS else 300
        suite = unittest.TestSuite([BridgeTests('test_unreadable_diff_paths_stay_in_the_budget'),
                                   BridgeTests('test_a_deleted_file_is_budgeted_by_its_old_path')])

        def launch(command, mask, **kwargs):
            ids = json.loads(Path(command[-2]).read_text())
            Path(command[-1]).write_text(json.dumps(dict(ids=ids, executed=len(ids),
                                                       skipped=[], successful=True)))
            return SimpleNamespace(pid=123, returncode=0)

        out = io.StringIO()
        with patch.dict(os.environ, MYAGENTKIT_TEST_TIMEOUT_SCALE='2'), \
                patch('agent_process.launch', side_effect=launch), \
                patch('agent_process.stop_group'), \
                patch('agent_process._exited_unreaped', side_effect=[False, True, True]), \
                patch.object(time, 'monotonic', side_effect=[0, base + 1]):
            self.assertTrue(run_review_shards(suite, out=out), out.getvalue())

    def setUp(self):
        from unittest.mock import patch
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        # A review loop's shell exports these; they must not reach the fixtures (as in BridgeTests).
        for name in INHERITED_CONTROLS:
            os.environ.pop(name, None)

    def git(self, repo, *args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True).stdout

    def commit(self, repo):
        self.git(repo, 'add', '.')
        self.git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')

    def project(self, tmp):
        repo = Path(tmp)
        (repo / 'scripts').mkdir()
        shutil.copyfile(ROOT / 'review.sh', repo / 'scripts/review.sh')
        shutil.copyfile(ROOT / 'gate_config.sh', repo / 'scripts/gate_config.sh')
        shutil.copyfile(ROOT / 'owns_check.py', repo / 'scripts/owns_check.py')
        (repo / '.gitignore').write_bytes(IGNORE_RULES)
        # Only the paid adapter boundary is replaced. The wrapper, dispatcher, snapshot,
        # scope validation and chain storage all run their shipped implementations.
        (repo / 'scripts/review_dispatch.py').write_text('''import os, sys
sys.path.insert(0, %r)
import review_dispatch as dispatch
def adapter(provider, args, report):
    print('REVIEWER RAN: ' + provider, flush=True)
    quota = os.environ.get('STUB_QUOTA') == provider
    report({'status': 'failed' if quota else 'completed',
            'failure_kind': 'quota_exhausted' if quota else None, 'evidence': 'fixture', 'usage_record': 'fixture'})
    return 5 if quota else 0
dispatch.claude_bridge.main = lambda args, report, claims=None: adapter('claude', args, report)
dispatch.codex_bridge.main = lambda args, report, claims=None: adapter('codex', args, report)
try:
    raise SystemExit(dispatch.main())
except ValueError as error:
    print('FAIL [review]: ' + str(error))
    raise SystemExit(2)
''' % str(ROOT))
        self.git(repo, 'init', '-q')
        self.git(repo, 'config', 'core.autocrlf', 'false')
        (repo / 'line ends [1].txt').write_bytes(b'one\ntwo\n')
        (repo / 'real.txt').write_bytes(b'original\n')
        self.commit(repo)
        return repo

    def review(self, repo, *args, **extra):
        env = dict(os.environ, REVIEW_REPO_ROOT=str(repo), REVIEW_CODEX_MODEL='codex-fixture',
                   REVIEW_CLAUDE_MODEL='claude-fixture', REVIEW_EFFORT='medium',
                   MYAGENTKIT_DELEGATION_DEPTH='0', MYAGENTKIT_TASK_ID='', STUB_QUOTA='',
                   PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'])
        env.update(extra)
        # A hang guard, times the scale: an unscaled 30 s ran out on a loaded host (v0.12.1).
        return subprocess.run(['sh', str(repo / 'scripts/review.sh'), *args], env=env, text=True,
                              capture_output=True,
                              timeout=30 * float(os.environ.get('MYAGENTKIT_TEST_TIMEOUT_SCALE', '1')))

    def test_each_reviewer_prints_model_and_effort_before_running(self):
        for primary in ('codex', 'claude'):
            with self.subTest(primary=primary), tempfile.TemporaryDirectory() as tmp:
                repo = self.project(tmp)
                (repo / 'real.txt').write_bytes(b'changed\n')
                result = self.review(repo, '--reviewer', primary, '--fallback', STUB_QUOTA=primary,
                                     MYAGENTKIT_AUTHOR='claude-sonnet-5' if primary == 'claude' else 'gpt-5.5',
                                     MYAGENTKIT_AUTHOR_EFFORT='low')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                for provider, model in (('codex', 'codex-fixture'), ('claude', 'claude-fixture')):
                    spend = 'REVIEW [about to run]: %s model %s, effort medium' % (provider, model)
                    self.assertIn(spend, result.stdout)
                    self.assertLess(result.stdout.index(spend), result.stdout.index('REVIEWER RAN: ' + provider))

    def test_a_diff_outside_the_brief_owns_paths_reaches_no_reviewer(self):
        # cross mode: the two sides never share a file, and nothing checked a worker's diff
        # against the paths its brief gave it (docs/WORKFLOW.md, "cross").
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as briefs:
            repo = self.project(tmp)
            (repo / 'real.txt').write_bytes(b'changed\n')
            brief = Path(briefs) / 'brief.md'
            for owns, code in (('Owns: real.txt', 0), ('Owns: src/', 2), ('No paths named.', 2)):
                with self.subTest(owns=owns):
                    brief.write_text('Task: fixture.\n' + owns + '\n')
                    result = self.review(repo, '--reviewer', 'claude', REVIEW_TASK_FILE=str(brief))
                    self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                    self.assertEqual('REVIEWER RAN: claude' in result.stdout, code == 0, result.stdout)
                    if code:
                        self.assertIn("FAIL [review]: the diff leaves the brief's Owns: paths", result.stdout)
                        if owns.startswith('Owns:'):
                            self.assertIn('  real.txt\n', result.stderr)
                        else:
                            self.assertIn('no Owns: line was read from ' + str(brief), result.stderr)

    def test_line_ending_only_files_fail_before_any_reviewer_in_the_selected_scope(self):
        for scope in ('unstaged', 'staged', 'base', 'commit', 'outside scope', 'real edit'):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as tmp:
                repo = self.project(tmp)
                base = self.git(repo, 'rev-parse', 'HEAD').decode().strip()
                (repo / 'line ends [1].txt').write_bytes(b'one\ntwo\r\n')
                (repo / 'real.txt').write_bytes(b'changed\n')
                args = []
                if scope == 'real edit':
                    (repo / 'line ends [1].txt').write_bytes(b'one\nchanged\r\n')
                if scope == 'staged':
                    self.git(repo, 'add', '.')
                elif scope in ('base', 'commit', 'outside scope'):
                    self.commit(repo)
                    args = ['--base', base] if scope == 'base' else ['--commit', 'HEAD']
                    if scope == 'outside scope':
                        (repo / 'real.txt').write_bytes(b'another real edit\n')
                        self.commit(repo)
                result = self.review(repo, '--reviewer', 'codex', '--fallback', *args)
                if scope in ('outside scope', 'real edit'):
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('REVIEWER RAN: codex', result.stdout)
                else:
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn("line-ending-only churn in 'line ends [1].txt'", result.stdout)
                    self.assertIn('restore its line endings before review', result.stdout)
                    self.assertNotIn('REVIEWER RAN:', result.stdout)
                    self.assertNotIn('REVIEW [about to run]:', result.stdout)

    def test_mixed_line_ending_churn_is_refused_in_every_scope(self):
        for scope in ('unstaged', 'staged', 'base', 'commit'):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as tmp:
                repo = self.project(tmp)
                path = repo / 'line ends [1].txt'
                lines = [str(i).encode() for i in range(200)]
                path.write_bytes(b'\n'.join(lines) + b'\n')
                self.commit(repo)
                base = self.git(repo, 'rev-parse', 'HEAD').decode().strip()
                lines[100] = b'edited'
                path.write_bytes(b'\r\n'.join(lines) + b'\r\n')
                args = []
                if scope == 'staged':
                    self.git(repo, 'add', '.')
                elif scope in ('base', 'commit'):
                    self.commit(repo)
                    args = ['--base', base] if scope == 'base' else ['--commit', 'HEAD']
                result = self.review(repo, *args)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('line-ending churn', result.stdout)
                self.assertIn('REVIEW_ALLOW_EOL_ONLY=1', result.stdout)
                self.assertNotIn('REVIEWER RAN:', result.stdout)

    def test_line_ending_refusal_assertion_detects_a_premature_announcement(self):
        from unittest.mock import patch

        case = ReviewPreflightTests('test_line_ending_only_files_fail_before_any_reviewer_in_the_selected_scope')
        review = case.review

        def premature(*args, **kwargs):
            result = review(*args, **kwargs)
            if result.returncode == 2:
                result.stdout = 'REVIEW [about to run]: codex model fixture-codex, effort medium\n' + result.stdout
            return result

        observed = unittest.TestResult()
        with patch.object(case, 'review', side_effect=premature):
            case.run(observed)
        self.assertFalse(observed.errors, observed.errors)
        self.assertEqual(len(observed.failures), 4, observed.failures)
        self.assertTrue(all('REVIEW [about to run]:' in failure for _, failure in observed.failures))

    def test_deliberate_normalization_requires_an_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.project(tmp)
            (repo / 'line ends [1].txt').write_bytes(b'one\r\ntwo\r\n')
            for allow, expected in (('', 2), ('0', 2), ('yes', 2), ('1', 0)):
                with self.subTest(allow=allow):
                    result = self.review(repo, REVIEW_ALLOW_EOL_ONLY=allow)
                    self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                    if expected:
                        self.assertIn('REVIEW_ALLOW_EOL_ONLY=1', result.stdout)
                        self.assertNotIn('REVIEWER RAN:', result.stdout)
                    else:
                        self.assertIn('REVIEWER RAN:', result.stdout)

    def test_line_ending_preflight_uses_two_diffs_for_many_files(self):
        from unittest.mock import patch
        import review_dispatch

        with tempfile.TemporaryDirectory() as tmp:
            repo = self.project(tmp)
            for i in range(50):
                (repo / ('file-%d.txt' % i)).write_bytes(b'old\n')
            self.commit(repo)
            for i in range(50):
                (repo / ('file-%d.txt' % i)).write_bytes(b'changed\n')
            diff = self.git(repo, 'diff', 'HEAD').decode()
            with patch.object(review_dispatch.claude_bridge, 'git', wraps=bridge.git) as calls:
                review_dispatch.reject_line_ending_churn(repo, 'uncommitted', None, diff)
            diffs = [call for call in calls.call_args_list if call.args[1] == 'diff']
            self.assertEqual(len(diffs), 2)
            self.assertTrue(all('--numstat' in call.args and '-z' in call.args for call in diffs))

    def test_line_ending_ratio_is_refused_just_above_two_to_one(self):
        # Each changed line counts 2 (deleted and added): total = 2 * (edits + CR-only lines)
        # and real = 2 * edits, so CR-only lines equal to edits sit exactly at 2:1.
        import review_dispatch

        for cr_only, refused in ((2, False), (3, True)):
            with self.subTest(cr_only=cr_only), tempfile.TemporaryDirectory() as tmp:
                repo = self.project(tmp)
                path = repo / 'line ends [1].txt'
                lines = [str(i).encode() for i in range(20)]
                path.write_bytes(b''.join(line + b'\n' for line in lines))
                self.commit(repo)
                ends = [b'\n'] * 20
                lines[2], lines[10] = b'edited', b'edited too'
                for i in (5, 15, 18)[:cr_only]:
                    ends[i] = b'\r\n'
                path.write_bytes(b''.join(map(bytes.__add__, lines, ends)))
                diff = self.git(repo, 'diff', 'HEAD').decode()
                if refused:
                    with self.assertRaisesRegex(ValueError, 'line-ending churn'):
                        review_dispatch.reject_line_ending_churn(repo, 'uncommitted', None, diff)
                else:
                    review_dispatch.reject_line_ending_churn(repo, 'uncommitted', None, diff)

    def test_an_adapter_preflight_failure_follows_the_about_to_run_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.project(tmp)
            stub = repo / 'scripts/review_dispatch.py'
            stub.write_text(stub.read_text().replace(
                "print('REVIEWER RAN: ' + provider, flush=True)",
                "raise ValueError('tmpdir preflight refused')"))
            (repo / 'real.txt').write_bytes(b'changed\n')
            result = self.review(repo)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('tmpdir preflight refused', result.stdout)
            self.assertIn('REVIEW [about to run]:', result.stdout)


class BridgeTests(unittest.TestCase):
    @staticmethod
    def continuation_review_cases():
        # The same complete reports exercise the Codex adapter and structured validation.
        # Every dangerous line follows a Low, also outside the Findings section.
        for section in ('', '## Notes\n- Low: file.py:2 another minor note.\n'):
            for severity in ('High', 'Critical'):
                for form in ('  ### Issue 1: {severity}: file.py:1 drops records.',
                             '\t### **Issue 1: {severity}** — file.py:1 drops records.',
                             '    - {severity}: file.py:1 drops records.',
                             '\t2. **{severity}** — file.py:1 drops records.',
                             '  **{severity}:** file.py:1 drops records.',
                             '    - ### Issue 1: **{severity}** | file.py:1 drops records.',
                             '  ### **2. {severity}** - file.py:1 drops records.',
                             '  3) __{severity}__ / file.py:1 drops records.',
                             '  **3.** __{severity}__: file.py:1 drops records.',
                             '\u00a0\u00a0### Issue 1: {severity}: file.py:1 drops records.',
                             '\u2003{severity}: file.py:1 drops records.'):
                    line = form.format(severity=severity)
                    yield '- Low: file.py:2 minor note.\n' + section + line, line, False
            for line in ('  ### **NOT RUN:** Windows deployment.',
                         '\t- NOT RUN: Windows deployment.',
                         '    2. **Could not verify** Windows deployment.',
                         '  __Windows deployment could not be verified.__',
                         '  - **NOT** **RUN**: Windows deployment.',
                         '  __Could__ __not__ __verify__ Windows deployment.',
                         '  VERDICT: Accept; NOT RUN: Windows deployment.'):
                yield '- Low: file.py:2 minor note.\n' + section + line, line, False
        for body in ('Low: file.py:2 minor note.\n  ordinary continuation.',
                     'Pre-existing: file.py:1 unrelated issue.\n  ordinary continuation.',
                     'No findings established in this diff.',
                     'Low: file.py:2 minor note.\n## Testing\nThe focused checks passed.',
                     'Low: file.py:2 minor note.\n## Notes\n- Pre-existing: file.py:1 unrelated issue.'):
            yield body, '', True

    def test_severity_lines_start_independent_findings_after_a_low(self):
        for body, line, clean in self.continuation_review_cases():
            findings, checks = bridge.review_parts('## Findings\n' + body)
            with self.subTest(body=body):
                if clean:
                    self.assertTrue(bridge.accept_allows(findings))
                    self.assertEqual(checks, [])
                elif bridge.UNVERIFIED.search(line.replace('*', '').replace('_', '')):
                    self.assertIn(line, checks)
                else:
                    self.assertIn(bridge.review_item(line), findings)
                    self.assertFalse(bridge.accept_allows(findings))

    def test_codex_accept_cannot_hide_severity_or_checks_in_low_continuations(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import codex_bridge

        def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            # LF bytes matter: a CRLF verdict could fail for an unrelated reason.
            Path(command[command.index('-o') + 1]).write_bytes(final.encode('utf-8'))
            return dict(exit_code=0, stdout=json.dumps({'type': 'turn.completed', 'usage': {}}),
                        stderr='', termination=None, duration_ms=1)

        cases = [(body, clean) for body, _, clean in self.continuation_review_cases()]
        cases.append(('No findings\n  established in this diff.', True))
        # Each form against the verdict rule itself; the whole adapter runs once each way, for
        # its record and evidence (a run per form took minutes and proved the same rule).
        whole = [next(case for case in cases if case[1]), next(case for case in cases if not case[1])]
        for body, clean in cases:
            final = '## Findings\n' + body + '\n## Manual checks\nNone.\nVERDICT: Accept\n'
            with self.subTest(body=body):
                self.assertEqual(codex_bridge.verdict_refused(final), not clean)
        for body, clean in whole:
            final = '## Findings\n' + body + '\n## Manual checks\nNone.\nVERDICT: Accept\n'
            received, out = [], io.StringIO()
            with self.subTest(body=body), patch.dict(os.environ, self.review_env()), \
                    patch('agent_process.run', side_effect=execution) as run, redirect_stdout(out):
                code = codex_bridge.main(['--repo', str(self.repo), '--model', 'codex-fixture-model',
                                          '--uncommitted'], received.append)
                run.assert_called_once()
                # #120: a contradicted Accept completes as the stricter verdict, never as Accept.
                self.assertEqual(code, 0, out.getvalue())
                self.assertEqual(received[-1]['status'], 'completed')
                self.assertEqual(received[-1]['failure_kind'], None)
                self.assertEqual(verdicts_of(received[-1]['evidence']) == ['VERDICT: Accept'], clean)

    def test_codex_failed_turn_message_reaches_the_evidence(self):
        # #292: a refused model's turn.failed message lived only in the usage record's raw stdout.
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import codex_bridge
        message = "The 'x' model is not supported when using Codex with a ChatGPT account."

        def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            return dict(exit_code=1, stdout=json.dumps({'type': 'turn.failed', 'error': {'message': message}}),
                        stderr='', termination=None, duration_ms=1)

        received = []
        with patch.dict(os.environ, self.review_env()), patch('agent_process.run', side_effect=execution), \
                redirect_stdout(io.StringIO()):
            codex_bridge.main(['--repo', str(self.repo), '--model', 'x', '--uncommitted'], received.append)
        self.assertEqual((received[-1]['status'], received[-1]['failure_kind']), ('failed', 'cli_error'))
        self.assertIn('## Failure\n\nCodex reported: ' + message,
                      Path(received[-1]['evidence']).read_text(encoding='utf-8'))

    def codex_evidence(self, run, *patches):
        from contextlib import ExitStack, redirect_stdout
        from unittest.mock import patch
        import codex_bridge
        received = []
        with ExitStack() as stack:
            for each in (patch.dict(os.environ, self.review_env()), patch('agent_process.run', side_effect=run),
                         redirect_stdout(io.StringIO()), *patches):
                stack.enter_context(each)
            codex_bridge.main(['--repo', str(self.repo), '--model', 'x', '--uncommitted'], received.append)
        return received[-1], Path(received[-1]['evidence']).read_text(encoding='utf-8')

    def test_codex_recovered_error_is_not_blamed_for_a_later_failure(self):
        # A reconnect Codex recovered from did not fail the run: a stale checkout must not end
        # its evidence with "Codex reported: Reconnecting...".
        from unittest.mock import patch
        import codex_bridge
        stream = '\n'.join(json.dumps(v) for v in ({'type': 'error', 'message': 'Reconnecting... 1/5'},
                                                   {'type': 'turn.completed'}))

        def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            return dict(exit_code=0, stdout=stream, stderr='', termination=None, duration_ms=1)

        result, evidence = self.codex_evidence(
            execution, patch.object(codex_bridge, 'recheck', return_value=(None, 'changed')))
        self.assertEqual(result['failure_kind'], 'stale_checkout')
        self.assertNotIn('Codex reported', evidence)

    def test_codex_failure_text_of_its_own_wins_and_reported_text_is_capped(self):
        # A run_failed run keeps its own supervision text, not the stream's turn.failed message.
        failed = json.dumps({'type': 'turn.failed', 'error': {'message': 'turn broke'}})

        def broken(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            return dict(exit_code=None, stdout=failed, stderr='supervisor broke', termination='run_failed',
                        launched=True, duration_ms=1)

        result, evidence = self.codex_evidence(broken)
        self.assertEqual(result['failure_kind'], 'run_failed')
        self.assertIn('supervisor broke', evidence)
        self.assertNotIn('Codex reported', evidence)

        # A long message keeps only its last 4000 characters.
        long = 'A' * 100 + 'B' * 4000

        def refused(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            return dict(exit_code=1, stdout=json.dumps({'type': 'turn.failed', 'error': {'message': long}}),
                        stderr='', termination=None, duration_ms=1)

        result, evidence = self.codex_evidence(refused)
        self.assertIn('Codex reported: ' + 'B' * 4000, evidence)
        self.assertNotIn('A', evidence.split('Codex reported: ', 1)[1])

    def test_codex_does_not_load_the_copys_agents_md_as_instructions(self):
        # #117: Codex loads the root AGENTS.md as instructions; the prompt already names it as
        # evidence to read, so the lead's constitution reached the reviewer twice, once as orders.
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import codex_bridge
        commands = []

        def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            commands.append(command)
            Path(command[command.index('-o') + 1]).write_bytes(b'VERDICT: Accept\n')
            return dict(exit_code=0, stdout=json.dumps({'type': 'turn.completed', 'usage': {}}),
                        stderr='', termination=None, duration_ms=1)

        with patch.dict(os.environ, self.review_env()), patch('agent_process.run', side_effect=execution), \
                redirect_stdout(io.StringIO()):
            codex_bridge.main(['--repo', str(self.repo), '--model', 'codex-fixture-model', '--uncommitted'], [].append)
        command = commands[0]
        self.assertEqual(command[command.index('project_doc_max_bytes=0') - 1], '-c')

    def test_structured_accept_cannot_hide_severity_or_checks_in_low_continuations(self):
        for body, _, clean in self.continuation_review_cases():
            value = dict(verdict='Accept', findings=[body], manual_checks=[])
            envelope = dict(type='result', subtype='success', is_error=False,
                            modelUsage={'claude-opus-5': {}}, structured_output=value)
            with self.subTest(body=body):
                if clean:
                    self.assertEqual(bridge.validate(envelope, 'review', 'claude-opus-5'), value)
                else:
                    self.assertNotEqual(bridge.validate(envelope, 'review', 'claude-opus-5')['verdict'], 'Accept')

    def test_codex_accept_cannot_drop_a_finding_or_manual_check_in_a_peer_heading(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import codex_bridge

        def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            Path(command[command.index('-o') + 1]).write_bytes(final.encode('utf-8'))
            return dict(exit_code=0, stdout=json.dumps({'type': 'turn.completed', 'usage': {}}),
                        stderr='', termination=None, duration_ms=1)

        for heading in ('## Testing', '## 1. High: file.py:1 drops records.',
                        '## **2. Critical:** file.py:1 bypasses the gate.',
                        '## NOT RUN', '## NOT RUN: Windows deployment could not be verified.',
                        '## Could not verify Windows deployment.',
                        '## Notes\n1. High: file.py:1 drops records.',
                        '## Summary\nNOT RUN: Windows deployment.'):
            final = '## Findings\nNone.\n## Manual checks\nNone.\n' + heading + '\nVERDICT: Accept\n'
            received, out = [], io.StringIO()
            with self.subTest(heading=heading), patch.dict(os.environ, self.review_env()), \
                    patch('agent_process.run', side_effect=execution) as run, redirect_stdout(out):
                code = codex_bridge.main(['--repo', str(self.repo), '--model', 'codex-fixture-model',
                                          '--uncommitted'], received.append)
                run.assert_called_once()
                self.assertEqual(code, 0, out.getvalue())
                # #120: the hidden High reads as Reject, the hidden check as Accept with Manual Checks.
                expected = ('Accept' if heading == '## Testing' else
                            'Reject' if re.search('High|Critical', heading) else 'Accept with Manual Checks')
                self.assertEqual(verdicts_of(received[-1]['evidence']), ['VERDICT: ' + expected])

    def test_structured_accept_cannot_hide_heading_findings_or_unverified_checks(self):
        for heading in ('## 1. High: file.py:1 drops records.',
                        '## **2. Critical:** file.py:1 bypasses the gate.',
                        '## NOT RUN', '## NOT RUN: Windows deployment could not be verified.',
                        '## Could not verify Windows deployment.',
                        '## Notes\n1. High: file.py:1 drops records.',
                        '## Summary\nNOT RUN: Windows deployment.'):
            # A structured Low item may contain continuation text and additional headings.
            # Its first word must not hide a later High or an unverified check.
            for field, item in (('findings', heading), ('manual_checks', heading),
                                ('findings', 'Low: a note.\n' + heading)):
                value = dict(verdict='Accept', findings=[], manual_checks=[])
                value[field] = [item]
                envelope = dict(type='result', subtype='success', is_error=False,
                                modelUsage={'claude-opus-5': {}}, structured_output=value)
                with self.subTest(field=field, item=item):
                    # #120: a High reads as Reject, among the findings or the checks, as the
                    # Codex text does (test above); anything else as a check (rsel).
                    self.assertEqual(bridge.validate(envelope, 'review', 'claude-opus-5')['verdict'],
                                     'Reject' if re.search('High|Critical', item) else 'Accept with Manual Checks')

    def test_fallback_uses_the_resolved_backend_model_family_and_refuses_unknowns(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import review_dispatch
        folder = self.root / 'user-backends'
        folder.mkdir()

        def unavailable(args, report, claims=None):
            report(dict(status='failed', failure_kind='quota_exhausted', evidence='fixture', usage_record='fixture'))
            return 5

        def completed(args, report, claims=None):
            report(dict(status='completed', failure_kind=None, evidence='fixture', usage_record='fixture'))
            return 0

        for author, model, allowed in (('codex/gpt-6', 'gpt-6', False),
                                       ('codex/gpt-6', 'openai/gpt-6', False),
                                       ('codex/gpt-6', 'unknown-model', False),
                                       ('codex/gpt-6', 'claude-opus-5', True),
                                       ('claude/claude-sonnet-5', 'gpt-6', True)):
            (folder / 'openai.env').write_text('ANTHROPIC_BASE_URL=https://backend.invalid/api\n'
                                              'ANTHROPIC_AUTH_TOKEN=fixture-token\nANTHROPIC_MODEL=' + model + '\n')
            out = io.StringIO()
            with self.subTest(author=author, model=model), \
                    patch.dict(os.environ, self.review_env(MYAGENTKIT_AUTHOR=author, MYAGENTKIT_AUTHOR_EFFORT='low')), \
                    patch.object(review_dispatch.codex_bridge, 'main', side_effect=unavailable), \
                    patch.object(review_dispatch.claude_bridge, 'main', side_effect=completed) as fallback, \
                    redirect_stdout(out):
                code = review_dispatch.main(['--repo', str(self.repo), '--reviewer', 'codex',
                                             '--codex-model', 'codex-fixture-model', '--backend', 'openai'])
                chain = json.loads(out.getvalue().split('review dispatch: ', 1)[1].splitlines()[0])
                self.assertEqual(code, 0 if allowed else 5, out.getvalue())
                self.assertEqual(fallback.call_count, int(allowed))
                self.assertEqual(len(chain['attempts']), 2 if allowed else 1)
                if not allowed:
                    # #225: the author's tier is refused, a model of no known family stays unknown.
                    self.assertIn('unknown family' if model == 'unknown-model' else "the author's tier",
                                  chain['fallback_blocked'])
                    self.assertNotIn('selected_reviewer', chain)
        # #181: an author that names no model tier is refused before any reviewer runs.
        with patch.dict(os.environ, self.review_env(MYAGENTKIT_AUTHOR='unknown-author')), \
                patch.object(review_dispatch.codex_bridge, 'main', side_effect=unavailable) as primary, \
                self.assertRaisesRegex(ValueError, 'names no model tier'):
            review_dispatch.main(['--repo', str(self.repo), '--reviewer', 'codex',
                                  '--codex-model', 'codex-fixture-model', '--backend', 'openai'])
        self.assertEqual(primary.call_count, 0)

    def test_noise_cannot_bypass_the_total_review_payload_cap(self):
        for name in ('package-lock.json', 'vendor/lib.py', 'app.min.js'):
            path = self.repo / name
            path.parent.mkdir(exist_ok=True)
            path.write_text('x' * 410_000 + '\n')
            with self.subTest(name=name), self.assertRaisesRegex(bridge.BridgeError, '400000 bytes'):
                bridge.snapshot(self.repo, 'uncommitted', None)
            path.unlink()

    def test_clean_review_placeholders_and_bold_pre_existing_forms(self):
        for sentence in ('No issues found.', 'None required.', 'Nothing to check.'):
            with self.subTest(sentence=sentence):
                findings, checks = bridge.review_parts('## Findings\nNo issues found.\n'
                                                       '## Manual checks\n' + sentence)
                self.assertTrue(bridge.accept_allows(findings))
                self.assertEqual(checks, [])
        for item in ('**Pre-existing:** x.py:1 elsewhere.', '- **Pre-existing:** x.py:1 elsewhere.'):
            with self.subTest(item=item):
                self.assertTrue(bridge.accept_allows([item]))
        self.assertFalse(bridge.accept_allows(['**Pre-existing:**']))
        self.assertFalse(bridge.placeholder('None required. Verify deployment.'))

    def test_peer_headings_end_sections_without_hiding_findings_or_not_run_checks(self):
        prefix = '## Findings\nNone.\n## Manual checks\nNone.\n'
        findings, checks = bridge.review_parts(prefix + '## Testing\nThe focused command passed.\nVERDICT: Accept')
        self.assertTrue(bridge.accept_allows(findings))
        self.assertEqual(checks, [])
        for extra in ('## Not run\nThe Windows suite: no host.',
                      '## Testing\nNOT RUN: the Windows suite, no host.'):
            with self.subTest(extra=extra):
                self.assertTrue(bridge.review_parts(prefix + extra)[1])
        findings, checks = bridge.review_parts(prefix + '## Other\n- High: x.py:1 drops records.')
        self.assertFalse(bridge.accept_allows(findings))
        findings, checks = bridge.review_parts(prefix + '### Verify deployment before release.')
        self.assertTrue(checks)

    def test_structured_manual_placeholders_match_the_text_parser(self):
        for item in ('None.', '- None.', 'N/A', 'Not applicable.', 'None required.'):
            value = dict(verdict='Accept', findings=[], manual_checks=[item])
            envelope = dict(type='result', subtype='success', is_error=False,
                            modelUsage={'claude-opus-5': {}}, structured_output=value)
            with self.subTest(item=item):
                self.assertEqual(bridge.review_parts('## Manual checks\n' + item)[1], [])
                self.assertEqual(bridge.validate(envelope, 'review', 'claude-opus-5')['manual_checks'], [])
        value = dict(verdict='Accept with Manual Checks', findings=[], manual_checks=['None.'])
        envelope['structured_output'] = value
        with self.assertRaisesRegex(bridge.BridgeError, 'no manual checks'):
            bridge.validate(envelope, 'review', 'claude-opus-5')
        value['verdict'] = 'Accept'
        for item in ('Not run', '## NOT RUN', 'NOT RUN: verify deployment on Windows.'):
            value['manual_checks'] = [item]
            with self.subTest(item=item):
                self.assertEqual(bridge.validate(envelope, 'review', 'claude-opus-5')['verdict'],
                                 'Accept with Manual Checks')

    def test_secret_refusal_only_checks_changed_paths_and_lists_every_hit(self):
        for name in ('.env', 'site.key'):
            (self.repo / name).write_text('private\n')
        self.commit_fixture('Existing secret names')
        (self.repo / 'file.py').write_text('another change\n')
        bridge.snapshot(self.repo, 'uncommitted', None)
        for name in ('.env', 'site.key'):
            (self.repo / name).write_text('changed private\n')
        with self.assertRaises(bridge.BridgeError) as caught:
            bridge.snapshot(self.repo, 'uncommitted', None)
        self.assertIn('--allow-secret-file .env', str(caught.exception))
        self.assertIn('--allow-secret-file site.key', str(caught.exception))

    def test_quota_fallback_refuses_an_unknown_author(self):
        # #225: the author's tier is refused, not its family (test_a_substitute_of_the_author_tier_
        # is_blocked); another Claude tier switches (test_a_used_up_codex_quota_switches_...).
        result, chain = self.dispatch_result('codex', fallback=False, CODEX_FIXTURE_CASE='quota',
                                             MYAGENTKIT_AUTHOR='')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(chain['attempts']), 1)
        self.assertIn('author', chain['fallback_blocked'])

    def test_provider_retry_above_the_wait_cap_stops_without_sleeping(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import review_dispatch

        def unavailable(command, report, claims=None):
            report(dict(status='failed', failure_kind='rate_limited', evidence='fixture',
                        usage_record='fixture', retry_after=5400))
            return 5

        out = io.StringIO()
        with patch.dict(os.environ, self.review_env()), \
                patch.object(review_dispatch.codex_bridge, 'main', side_effect=unavailable) as call, \
                patch.object(review_dispatch, 'sleep') as sleep, redirect_stdout(out):
            code = review_dispatch.main(['--repo', str(self.repo), '--uncommitted', '--reviewer', 'codex',
                                         '--codex-model', 'fixture-codex-model'])
        self.assertEqual(code, 5, out.getvalue())
        self.assertEqual(call.call_count, 1)
        sleep.assert_not_called()
        self.assertIn('5400', out.getvalue())
        self.assertIn('retry', out.getvalue().lower())

    def test_review_and_proposal_share_the_verification_rule(self):
        expected = ('Never claim a run you did not make. An OPEN product decision is a question '
                    'for the owner, not a finding.')
        task = self.root / 'verification-task.md'
        task.write_text('Propose a small correction.\n', encoding='utf-8')
        log = self.root / 'verification-prompt.txt'
        for mode, case in (('review', 'accept'), ('propose', 'proposal')):
            with self.subTest(mode=mode):
                code, result = self.run_bridge(case, mode, ['--task-file', str(task)],
                                               {'PROMPT_LOG': str(log)})
                self.assertEqual(code, 0, result)
                self.assertEqual(log.read_text(encoding='utf-8').count(expected), 1)
        self.assertEqual(bridge.VERIFICATION_RULE.strip(), expected)

    def test_an_inherited_backend_cannot_change_a_synthetic_review(self):
        from unittest.mock import patch
        # Run the real setUp with an inherited selector, as a shell launching this suite does.
        with patch.dict(os.environ, MYAGENTKIT_BACKEND='absent-in-synthetic-repo'):
            case = BridgeTests('test_default_reviewer_is_claude_and_codex_remains_explicit')
            result = unittest.TestResult()
            case.run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)

    def test_backend_secrets_must_be_ignored_and_untracked_before_review(self):
        token = 'backend-private-test-token'
        self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n'
                          'ANTHROPIC_AUTH_TOKEN=' + token + '\n')
        path = '.myagentkit/backends/glm.env'
        for tracked in (False, True):
            with self.subTest(tracked=tracked):
                (self.repo / '.gitignore').write_text('/.myagentkit/usage/\n/docs/reviews/\n')
                if tracked:
                    self.git('add', '-f', path)
                    (self.repo / '.gitignore').write_text('/.myagentkit/\n/docs/reviews/\n')
                log = self.root / 'secret-prompt.txt'
                result = self.run_wrapper('--uncommitted', '--backend', 'glm',
                                          CLAUDE_CLI_BIN=str(self.fixture), PROMPT_LOG=str(log))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('must be Git-ignored and untracked', result.stdout)
                self.assertNotIn(token, result.stdout + result.stderr)
                self.assertFalse(log.exists(), 'backend secret reached the reviewer')
                self.assertFalse((self.repo / '.myagentkit/usage').exists())
        # Untracking a previously committed backend must not review its token as deleted text.
        self.commit_fixture('Historical backend fixture')
        reference = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        self.git('rm', '--cached', path)
        self.assertNotIn(token, bridge.snapshot(self.repo, 'uncommitted', None)[2])
        self.commit_fixture('Untrack backend fixture')
        self.assertNotIn(token, bridge.snapshot(self.repo, 'commit', 'HEAD')[2])
        (self.repo / 'file.py').write_text('after backend cleanup\n')
        self.commit_fixture('Visible change fixture')
        for scope, ref in (('base', reference), ('commit', 'HEAD')):
            self.assertNotIn(token, bridge.snapshot(self.repo, scope, ref)[2])

    def test_a_backend_in_another_case_stays_out_of_every_review_scope(self):
        # Windows and macOS fold case: `.MYAGENTKIT/Backends/` is the backend store. Untracked
        # where no ignore rule matched it (core.ignorecase false), or deleted in the reviewed
        # commit, a case-sensitive exclusion put its token in the diff.
        token = 'backend-private-case-token'
        name = '.MYAGENTKIT/Backends/glm.env'
        self.git('config', 'core.ignorecase', 'false')
        path = self.repo / name
        path.parent.mkdir(parents=True)
        path.write_text('ANTHROPIC_AUTH_TOKEN=' + token + '\n')
        self.assertNotIn(token, bridge.snapshot(self.repo, 'uncommitted', None)[2])
        self.git('config', 'core.ignorecase', 'true')
        self.git('add', '-f', '--', name)
        self.commit_fixture('Historical backend fixture')
        self.git('rm', '--cached', '-q', '--', name)
        self.commit_fixture('Untrack backend fixture')
        self.assertNotIn(token, bridge.snapshot(self.repo, 'commit', 'HEAD')[2])

    def test_backend_clears_each_claude_credential_and_routing_control(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import review_dispatch
        self.backend_file(''.join('%s=%s\n' % item for item in self.BACKEND.items()))
        # Independent of the production list: deleting any entry must fail its subtest.
        keys = (
            'CLAUDE_CODE_API_BASE_URL',
            'CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR',
            'CLAUDE_CODE_API_KEY_HELPER_TTL_MS',
            'CLAUDE_CODE_ARTIFACTS_API_BASE_URL',
            'CLAUDE_CODE_ARTIFACTS_API_TOKEN',
            'CLAUDE_CODE_ARTIFACT_ASSET_BASE_URL',
            'CLAUDE_CODE_ARTIFACT_LIVE_BASE_URL',
            'CLAUDE_CODE_ARTIFACT_SYNC_BASE_URL',
            'CLAUDE_CODE_ARTIFACT_VIEWER_BASE_URL',
            'CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL',
            'CLAUDE_CODE_AUTO_MODE_MODEL',
            'CLAUDE_CODE_AWS_CHAIN_RESOLVE_TIMEOUT_MS',
            'CLAUDE_CODE_BG_CLASSIFIER_MODEL',
            'CLAUDE_CODE_CLIENT_CERT',
            'CLAUDE_CODE_CLIENT_KEY',
            'CLAUDE_CODE_CLIENT_KEY_PASSPHRASE',
            'CLAUDE_CODE_CUSTOM_OAUTH_URL',
            'CLAUDE_CODE_DESIGN_OAUTH_CLIENT_ID',
            'CLAUDE_CODE_DISABLE_AUTH_REFRESH_LOCK',
            'CLAUDE_CODE_ENABLE_PROXY_AUTH_HELPER',
            'CLAUDE_CODE_GATEWAY_HINT_HEADERS',
            'CLAUDE_CODE_GATEWAY_TOKEN',
            'CLAUDE_CODE_GATEWAY_TOKEN_FILE_DESCRIPTOR',
            'CLAUDE_CODE_GB_BASE_URL',
            'CLAUDE_CODE_HFI_BEARER_TOKEN',
            'CLAUDE_CODE_HOST_AUTH_ENV_VAR',
            'CLAUDE_CODE_HOST_AUTH_REFRESH_TIMEOUT_MS',
            'CLAUDE_CODE_HOST_GATEWAY_LINEAGE',
            'CLAUDE_CODE_HOST_HTTP_PROXY_PORT',
            'CLAUDE_CODE_HOST_SOCKS_PROXY_PORT',
            'CLAUDE_CODE_HTTPS_PROXY',
            'CLAUDE_CODE_HTTP_PROXY',
            'CLAUDE_CODE_MCP_SERVE_AUTH_TOKEN',
            'CLAUDE_CODE_MEMORY_API_BASE_URL',
            'CLAUDE_CODE_MEMORY_API_TOKEN',
            'CLAUDE_CODE_MESSAGING_TOKEN',
            'CLAUDE_CODE_METRICS_ENDPOINT',
            'CLAUDE_CODE_MODEL_CATALOG_URL',
            'CLAUDE_CODE_OAUTH_CLIENT_ID',
            'CLAUDE_CODE_OAUTH_REFRESH_TOKEN',
            'CLAUDE_CODE_OAUTH_SCOPES',
            'CLAUDE_CODE_OAUTH_TOKEN',
            'CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR',
            'CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST',
            'CLAUDE_CODE_PROXY_AUTHENTICATE',
            'CLAUDE_CODE_PROXY_AUTH_HELPER_TTL_MS',
            'CLAUDE_CODE_PROXY_HOST',
            'CLAUDE_CODE_PROXY_RESOLVES_HOSTS',
            'CLAUDE_CODE_PROXY_URL',
            'CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH',
            'CLAUDE_CODE_SDK_HAS_OAUTH_REFRESH',
            'CLAUDE_CODE_SESSION_ACCESS_TOKEN',
            'CLAUDE_CODE_SKIP_ANTHROPIC_AWS_AUTH',
            'CLAUDE_CODE_SKIP_ANTHROPIC_GOOGLE_CLOUD_AUTH',
            'CLAUDE_CODE_SKIP_AWS_CRED_CACHE',
            'CLAUDE_CODE_SKIP_BEDROCK_AUTH',
            'CLAUDE_CODE_SKIP_FOUNDRY_AUTH',
            'CLAUDE_CODE_SKIP_MANTLE_AUTH',
            'CLAUDE_CODE_SKIP_VERTEX_AUTH',
            'CLAUDE_CODE_SLACK_TAG_TOKEN',
            'CLAUDE_CODE_SUBAGENT_MODEL',
            'CLAUDE_CODE_SUBAGENT_MODEL_FORCE',
            'CLAUDE_CODE_USE_ANTHROPIC_AWS',
            'CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD',
            'CLAUDE_CODE_USE_BEDROCK',
            'CLAUDE_CODE_USE_CCR_V',
            'CLAUDE_CODE_USE_FOUNDRY',
            'CLAUDE_CODE_USE_GATEWAY',
            'CLAUDE_CODE_USE_MANTLE',
            'CLAUDE_CODE_USE_VERTEX',
            'CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR',
            'CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL',
        )
        with patch.dict(os.environ, self.review_env(), clear=True):
            os.environ.update(dict.fromkeys(keys, 'lead-control'))
            def launch(argv, report, claims=None):
                for key in keys:
                    with self.subTest(key=key):
                        self.assertFalse(key in os.environ, key + " remained inherited")
                self.assertEqual(os.environ['ANTHROPIC_AUTH_TOKEN'], self.BACKEND['ANTHROPIC_AUTH_TOKEN'])
                report({'status': 'completed'})
                return 0
            with patch.object(review_dispatch.claude_bridge, 'main', launch), redirect_stdout(io.StringIO()):
                self.assertEqual(review_dispatch.main(['--repo', str(self.repo), '--uncommitted',
                                                       '--backend', 'glm']), 0)
            for key in keys:
                with self.subTest(restored=key):
                    self.assertEqual(os.environ.get(key), 'lead-control')

    def test_backend_requires_a_nonempty_token(self):
        import review_dispatch
        for token in ('', 'ANTHROPIC_AUTH_TOKEN=\n', 'ANTHROPIC_AUTH_TOKEN=   \n'):
            with self.subTest(token=token):
                self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n' + token)
                with self.assertRaisesRegex(ValueError, 'sets no ANTHROPIC_AUTH_TOKEN'):
                    review_dispatch.load_backend(self.repo, 'glm')

    def test_backend_rejects_unsafe_model_ids(self):
        import review_dispatch
        for model in ('-x', 'x|y', 'x\x1b[2J', 'x y'):
            with self.subTest(model=model):
                self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_AUTH_TOKEN=fixture\n'
                                  + 'ANTHROPIC_MODEL=' + model + '\n')
                with self.assertRaisesRegex(ValueError, 'sets no model'):
                    review_dispatch.load_backend(self.repo, 'glm')
        for model in ('glm-x', 'org/model:version@1.2_3'):
            self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_AUTH_TOKEN=fixture\n'
                              + 'ANTHROPIC_MODEL=' + model + '\n')
            self.assertEqual(review_dispatch.load_backend(self.repo, 'glm')[1], model)

    def test_backend_case_variant_of_tracked_path_is_refused(self):
        import review_dispatch
        self.backend_file(''.join('%s=%s\n' % item for item in self.BACKEND.items()))
        self.git('add', '-f', '.myagentkit/backends/glm.env')
        with self.assertRaisesRegex(ValueError, 'Git-ignored and untracked'):
            review_dispatch.load_backend(self.repo, 'GLM')
        # As on a case-sensitive filesystem (Linux), where GLM.env does not exist: still tracked.
        from unittest.mock import patch
        lexists = os.path.lexists
        exact = lambda path: lexists(path) and Path(path).name in os.listdir(Path(path).parent)
        with patch.object(review_dispatch.os.path, 'lexists', exact),                 self.assertRaisesRegex(ValueError, 'Git-ignored and untracked'):
            review_dispatch.load_backend(self.repo, 'GLM')

    @posix_only
    def test_backend_nofollow_refuses_a_swapped_symlink(self):
        from unittest.mock import patch
        import review_dispatch
        self.backend_file(''.join('%s=%s\n' % item for item in self.BACKEND.items()))
        path = self.repo / '.myagentkit/backends/glm.env'
        target = self.repo / 'tracked.env'
        path.rename(target)
        self.git('add', 'tracked.env')
        path.symlink_to(target)
        # Simulate replacing the regular leaf after the preliminary checks.
        with patch.object(Path, 'is_symlink', return_value=False):
            with self.assertRaisesRegex(ValueError, 'cannot be read'):
                review_dispatch.load_backend(self.repo, 'glm')

    @posix_only
    def test_backend_nonblock_refuses_a_swapped_fifo(self):
        self.backend_file('')
        path = self.repo / '.myagentkit/backends/glm.env'
        path.unlink()
        os.mkfifo(path)
        code = ('from pathlib import Path; from unittest.mock import patch; import review_dispatch; '
                'p=patch("review_dispatch.os.path.isfile", return_value=True); p.start(); '
                'review_dispatch.load_backend(Path(' + repr(str(self.repo)) + '), "glm")')
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('regular file', result.stderr)

    def test_direct_backend_label_requires_an_endpoint(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        for mode in ('review', 'propose'):
            with self.subTest(mode=mode), patch.dict(os.environ, self.review_env(), clear=True):
                os.environ.pop('ANTHROPIC_BASE_URL', None)
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(bridge.main([mode, '--repo', str(self.repo), '--backend', 'glm',
                                                  '--model', 'claude-opus-5']), 2)
                self.assertIn('--backend requires ANTHROPIC_BASE_URL', out.getvalue())

    def test_codex_wrapper_ignores_requested_backend(self):
        for flags, exported in ((('--backend', 'missing'), ''), ((), 'missing')):
            with self.subTest(flags=flags):
                result = self.run_wrapper('--uncommitted', '--reviewer', 'codex', *flags,
                                          MYAGENTKIT_BACKEND=exported, REVIEW_CODEX_MODEL='fixture-codex-model',
                                          REVIEW_CLI_BIN=str(self.build_fake_codex()))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stderr.count('--backend is ignored for --reviewer codex'), 1)
                self.assertNotIn('claude@', result.stdout)

    def test_backend_reviewer_identity_reaches_evidence_and_fallback_banner(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        args = SimpleNamespace(backend='glm', model='glm-fixture', effort='high',
                               timeout=30, max_turns=2, max_budget_usd=None)
        with patch.dict(os.environ, MYAGENTKIT_REVIEW_FALLBACK_FROM='codex'):
            body = bridge.render('s', {'status': 'completed', 'tools': ['Read'], 'scope': 'uncommitted',
                                       'reference': None, 'head': 'head', 'fingerprint': 'fingerprint',
                                       'diff_sha256': 'diffsha', 'result': {'verdict': 'Accept',
                                       'findings': [], 'manual_checks': []}}, args)
        self.assertIn('| reviewer | claude@glm |', body)
        self.assertIn('| model_attested | no (requested, unattested', body)
        self.assertIn('this claude@glm review ran', body)
        self.assertIn('Check that claude@glm did not author', body)
        # Only a completed review without a backend is attested; a failed run never is.
        for backend, status, attested in ((None, 'completed', 'yes (CLI modelUsage)'),
                                          (None, 'failed', 'no (run did not complete)'),
                                          ('glm', 'failed', 'no (run did not complete)')):
            with self.subTest(backend=backend, status=status):
                body = bridge.render('s', {'status': status, 'tools': ['Read'], 'scope': 'uncommitted',
                                           'reference': None, 'head': 'head', 'fingerprint': 'fingerprint',
                                           'diff_sha256': 'diffsha', 'error': 'cli failed',
                                           'failure_kind': 'cli_error', 'result': {'verdict': 'Accept',
                                           'findings': [], 'manual_checks': []}},
                                     SimpleNamespace(**dict(vars(args), backend=backend)))
                self.assertIn('| model_attested | %s |' % attested, body)

    def test_claude_settings_deny_relative_and_absolute_backend_reads(self):
        from types import SimpleNamespace
        args = SimpleNamespace(repo=self.repo, mode='review', model='claude-opus-5', effort='high',
                               max_turns=2, max_budget_usd=None)
        private = str((self.repo / '.myagentkit/backends').resolve()).replace('\\', '/')
        for sandboxed in (False, True):
            with self.subTest(sandboxed=sandboxed):
                command, _ = bridge.claude_command('claude', args, sandboxed)
                settings = json.loads(command[command.index('--settings') + 1])
                self.assertIn('Read(.myagentkit/backends/**)', settings['permissions']['deny'])
                self.assertIn('Read(//' + private.lstrip('/') + '/**)', settings['permissions']['deny'])
                if sandboxed:
                    self.assertIn(private, settings['sandbox']['filesystem']['denyRead'])
                    self.assertIn('.myagentkit/backends', settings['sandbox']['filesystem']['denyRead'])

    def test_backend_final_values_cannot_be_emptied_by_duplicate_keys(self):
        import review_dispatch
        for key, reason in (('ANTHROPIC_BASE_URL', 'sets no ANTHROPIC_BASE_URL'),
                            ('ANTHROPIC_MODEL', 'sets no model')):
            with self.subTest(key=key):
                self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n'
                                  + key + '=\n')
                with self.assertRaisesRegex(ValueError, reason):
                    review_dispatch.load_backend(self.repo, 'glm')

    def test_backend_reads_require_a_regular_file_and_are_bounded(self):
        import review_dispatch
        self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n')
        path = self.repo / '.myagentkit/backends/glm.env'
        path.unlink()
        path.mkdir()
        with self.assertRaisesRegex(ValueError, 'regular file'):
            review_dispatch.load_backend(self.repo, 'glm')
        path.rmdir()
        path.write_bytes(b'#' + b'x' * 65536)
        with self.assertRaisesRegex(ValueError, 'too large'):
            review_dispatch.load_backend(self.repo, 'glm')

    def test_backend_opened_descriptor_must_be_regular(self):
        from unittest.mock import patch
        import stat
        import review_dispatch
        self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n')
        with patch.object(review_dispatch.os, 'fstat', return_value=type('Stat', (), {'st_mode': stat.S_IFIFO})()):
            with self.assertRaisesRegex(ValueError, 'regular file'):
                review_dispatch.load_backend(self.repo, 'glm')

    @posix_only
    def test_a_backend_fifo_is_refused_without_waiting_for_a_writer(self):
        self.backend_file('')
        path = self.repo / '.myagentkit/backends/glm.env'
        path.unlink()
        os.mkfifo(path)
        scripts = self.install_wrapper()
        # A real subprocess deadline prevents the negative test itself from hanging.
        result = subprocess.run(['sh', str(scripts / 'review.sh'), '--uncommitted', '--backend', 'glm'],
                                env=self.review_env(REVIEW_TIMEOUT_SECONDS='1'), capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('regular file', result.stdout)

    def test_backend_nul_values_fail_before_mutation_or_a_chain(self):
        from unittest.mock import patch
        import review_dispatch
        self.backend_file('ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-x\n'
                          'ANTHROPIC_AUTH_TOKEN=tokenword\x00value\n')
        with patch.dict(os.environ, self.review_env(ANTHROPIC_API_KEY='inherited-key')), \
                patch.object(review_dispatch.claude_bridge, 'main') as launch:
            before = dict(os.environ)
            with self.assertRaises(ValueError) as error:
                review_dispatch.main(['--repo', str(self.repo), '--uncommitted', '--backend', 'glm'])
            self.assertTrue(dict(os.environ) == before, 'backend rejection mutated the environment')
            # Not 'private': the message names the file, and macOS's temp folder is /private/var.
            self.assertNotIn('tokenword', str(error.exception))
            launch.assert_not_called()
        self.assertFalse((self.repo / '.myagentkit/usage').exists())

    def test_backend_whitespace_lines_share_the_worker_grammar(self):
        import review_dispatch
        self.backend_file(' \t\r\n  # ignored comment\r\n' +
                          ''.join('  %s=%s  \r\n' % item for item in self.BACKEND.items()))
        self.assertEqual(review_dispatch.load_backend(self.repo, 'glm'), (self.BACKEND, 'glm-fixture'))

    def test_direct_claude_limits_are_validated_per_mode(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import agent_process

        class CapturedPreparation(RuntimeError):
            pass

        for mode, timeout, turns in [('propose', 3600, 100),
                                     ('review', agent_process.MAX_REVIEW_TIMEOUT, agent_process.MAX_REVIEW_TURNS)]:
            for option, maximum in [('--timeout', timeout), ('--max-turns', turns)]:
                for value in (-1, 0, 1, maximum, maximum + 1):
                    with self.subTest(mode=mode, option=option, value=value):
                        out = io.StringIO()
                        with patch.dict(os.environ, self.review_env()), redirect_stdout(out), \
                                patch.object(bridge, 'git', side_effect=CapturedPreparation) as prepare, \
                                patch.object(agent_process, 'run') as run, patch.object(agent_process, 'launch') as launch:
                            args = [mode, '--repo', str(self.repo), option, str(value)]
                            if 1 <= value <= maximum:
                                with self.assertRaises(CapturedPreparation):
                                    bridge.main(args)
                            else:
                                self.assertEqual(bridge.main(args), 2)
                                self.assertIn('timeout must be 1..%d seconds and max-turns 1..%d'
                                              % (timeout, turns), out.getvalue())
                                prepare.assert_not_called()
                            run.assert_not_called()
                            launch.assert_not_called()

    def test_only_declared_platform_skips_are_allowed_and_never_count_as_executed(self):
        class Probe(unittest.TestCase):
            def test_passes(self):
                pass

            @unittest.skip('platform probe')
            def test_platform(self):
                pass

            @unittest.skip('unexpected missing coverage')
            def test_unexpected(self):
                pass
        Probe.test_platform._kit_platform_skip = True
        out = io.StringIO()
        self.assertTrue(run_quietly(unittest.TestSuite([Probe('test_passes'), Probe('test_platform')]),
                                   out, minimum=1))
        self.assertIn('NOT RUN:', out.getvalue())
        self.assertFalse(run_quietly(unittest.TestSuite([Probe('test_passes'), Probe('test_platform')]),
                                    io.StringIO(), minimum=2))
        self.assertFalse(run_quietly(unittest.TestSuite([Probe('test_passes'), Probe('test_unexpected')]),
                                    io.StringIO(), minimum=1))

    def test_a_passing_run_prints_a_summary_and_a_failing_run_its_whole_log(self):
        class Probe(unittest.TestCase):
            def test_passes(self):
                pass

            def test_fails(self):
                self.fail("probe failure message")
        out = io.StringIO()
        self.assertTrue(run_quietly(unittest.TestSuite([Probe("test_passes")]), out))
        self.assertEqual(out.getvalue(), "Ran 1 tests: OK\n")
        out = io.StringIO()
        self.assertFalse(run_quietly(unittest.TestSuite([Probe("test_passes"), Probe("test_fails")]), out))
        self.assertIn("test_passes", out.getvalue())
        self.assertIn("... ok", out.getvalue())
        self.assertIn("probe failure message", out.getvalue())
        self.assertIn("FAILED (failures=1)", out.getvalue())

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

        def capture(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            observed.append(timeout)
            raise CapturedLaunch()  # No CLI or wall-clock wait is needed.

        default = agent_process.DEFAULT_REVIEW_TIMEOUT
        self.assertGreaterEqual(default, 2700)  # 1800 killed real high-effort reviews
        cases = [(bridge.main, ['review'], None, default),
                 (bridge.main, ['review', '--timeout', '77'], None, 77),
                 (codex_bridge.main, ['--model', 'fixture-codex-model'], None, default),
                 (codex_bridge.main, ['--model', 'fixture-codex-model'], '88', 88),
                 (codex_bridge.main, ['--model', 'fixture-codex-model'], '3600', 3600),
                 (review_dispatch.main, ['--reviewer', 'claude'], None, default),
                 (review_dispatch.main, ['--reviewer', 'codex'], None, default),
                 (review_dispatch.main, ['--reviewer', 'claude'], '3600', 3600),
                 (review_dispatch.main, ['--reviewer', 'claude'], '99', 99),
                 (review_dispatch.main, ['--reviewer', 'codex'], '99', 99)]
        # KARARLAR B03 inv2#31: a high-effort Codex review ran 37-58 minutes (RL 2026-10-13), so
        # its default is the maximum; a Claude review and an explicit value keep theirs.
        cases += [(codex_bridge.main, ['--model', 'fixture-codex-model', '--effort', 'high'], None, 3600),
                  (codex_bridge.main, ['--model', 'fixture-codex-model', '--effort', 'high'], '88', 88),
                  (review_dispatch.main, ['--reviewer', 'codex', '--effort', 'high'], None, 3600),
                  (review_dispatch.main, ['--reviewer', 'claude', '--effort', 'high'], None, default)]
        for main, argv, override, expected in cases:
            with self.subTest(entry=main.__module__, args=argv, override=override):
                with patch.dict(os.environ, self.review_env(REVIEW_CLAUDE_MODEL='claude-opus-5',
                                                           REVIEW_CODEX_MODEL='fixture-codex-model')):
                    os.environ.pop('REVIEW_TIMEOUT_SECONDS', None)
                    if override is not None:
                        os.environ['REVIEW_TIMEOUT_SECONDS'] = override
                    # Freeze preparation time here to check the exact configured budget;
                    # the shared-deadline regression below measures real elapsed time.
                    with patch.object(agent_process, 'run', side_effect=capture), \
                            patch('time.monotonic', return_value=1000.0), redirect_stdout(StringIO()):
                        with self.assertRaises(CapturedLaunch):
                            main([*argv, '--repo', str(self.repo)])
                    self.assertEqual(observed[-1], expected)

    def test_review_turn_limit_default_override_and_bounds(self):
        # Three high-effort reviews died on the old 12-turn cap: the review default must leave
        # room, REVIEW_MAX_TURNS must reach the Claude CLI, and out-of-range values must fail
        # before any model is called.
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import agent_process
        import review_dispatch

        class CapturedLaunch(RuntimeError):
            pass

        observed = []

        def capture(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            observed.append(command[command.index('--max-turns') + 1])
            raise CapturedLaunch()

        self.assertGreaterEqual(agent_process.DEFAULT_REVIEW_TURNS, 100)
        for main, argv, override, expected in [
                (bridge.main, ['review'], None, str(agent_process.DEFAULT_REVIEW_TURNS)),
                (bridge.main, ['review', '--max-turns', '300'], None, '300'),
                (review_dispatch.main, ['--reviewer', 'claude'], None, str(agent_process.DEFAULT_REVIEW_TURNS)),
                (review_dispatch.main, ['--reviewer', 'claude'], '450', '450')]:
            with self.subTest(entry=main.__module__, args=argv, override=override):
                with patch.dict(os.environ, self.review_env(REVIEW_CLAUDE_MODEL='claude-opus-5')):
                    os.environ.pop('REVIEW_MAX_TURNS', None)
                    if override is not None:
                        os.environ['REVIEW_MAX_TURNS'] = override
                    with patch.object(agent_process, 'run', side_effect=capture), redirect_stdout(StringIO()):
                        with self.assertRaises(CapturedLaunch):
                            main([*argv, '--repo', str(self.repo)])
                    self.assertEqual(observed[-1], expected)
        for bad in ('0', str(agent_process.MAX_REVIEW_TURNS + 1)):
            with self.subTest(bad_turns=bad):
                with patch.dict(os.environ, self.review_env(REVIEW_CLAUDE_MODEL='claude-opus-5', REVIEW_MAX_TURNS=bad)),                         patch.object(agent_process, 'run', side_effect=capture):
                    with self.assertRaisesRegex(ValueError, 'REVIEW_MAX_TURNS'):
                        review_dispatch.main(['--reviewer', 'claude', '--repo', str(self.repo)])
        for bad in ('0', str(agent_process.MAX_REVIEW_TIMEOUT + 1)):
            with self.subTest(bad_timeout=bad):
                with patch.dict(os.environ, self.review_env(REVIEW_CLAUDE_MODEL='claude-opus-5', REVIEW_TIMEOUT_SECONDS=bad)),                         patch.object(agent_process, 'run', side_effect=capture):
                    with self.assertRaisesRegex(ValueError, 'REVIEW_TIMEOUT_SECONDS'):
                        review_dispatch.main(['--reviewer', 'claude', '--repo', str(self.repo)])

    def test_direct_entries_reject_out_of_range_limits_before_launch(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import agent_process
        import codex_bridge

        for option, maximum in (('--timeout', agent_process.MAX_REVIEW_TIMEOUT),
                                ('--max-turns', agent_process.MAX_REVIEW_TURNS)):
            for bad in (-1, 0, maximum + 1):
                with self.subTest(entry='claude', option=option, bad=bad):
                    out = io.StringIO()
                    with patch.dict(os.environ, self.review_env()), redirect_stdout(out), \
                            patch.object(agent_process, 'run', side_effect=AssertionError('launch')) as run, \
                            patch.object(agent_process, 'launch', side_effect=AssertionError('launch')) as launch:
                        self.assertEqual(bridge.main(['review', '--repo', str(self.repo), option, str(bad)]), 2)
                        self.assertIn('timeout must be 1..', out.getvalue())
                        run.assert_not_called()
                        launch.assert_not_called()
        for bad in (-1, 0, agent_process.MAX_REVIEW_TIMEOUT + 1):
            with self.subTest(entry='codex', bad=bad):
                with patch.dict(os.environ, self.review_env(REVIEW_TIMEOUT_SECONDS=str(bad))), \
                        patch.object(agent_process, 'run', side_effect=AssertionError('launch')) as run, \
                        patch.object(agent_process, 'launch', side_effect=AssertionError('launch')) as launch:
                    with self.assertRaisesRegex(ValueError, 'REVIEW_TIMEOUT_SECONDS'):
                        codex_bridge.main(['--repo', str(self.repo), '--model', 'fixture-codex-model'])
                    run.assert_not_called()
                    launch.assert_not_called()
        for bad in (-1, 0, agent_process.MAX_REVIEW_TIMEOUT + 1, float('inf'), float('nan')):
            with self.subTest(entry='process', bad=bad):
                with patch.object(agent_process, 'launch', side_effect=AssertionError('launch')) as launch:
                    with self.assertRaisesRegex(ValueError, 'timeout must be greater than zero'):
                        agent_process.run(['fixture'], 'prompt', self.repo, bad)
                    launch.assert_not_called()

    def test_dispatch_validates_turns_only_when_claude_is_allowed(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import review_dispatch

        def complete(argv, report, claims=None):
            report({'status': 'completed', 'failure_kind': None})
            return 0

        for reviewer, fallback in (('codex', False), ('codex', True), ('claude', False), ('claude', True)):
            for bad in ('-1', '0', '501', 'invalid'):
                with self.subTest(reviewer=reviewer, fallback=fallback, bad=bad):
                    with patch.dict(os.environ, self.review_env(REVIEW_MAX_TURNS=bad)), \
                            patch.object(review_dispatch.claude_bridge, 'main', side_effect=complete) as claude, \
                            patch.object(review_dispatch.codex_bridge, 'main', side_effect=complete) as codex, \
                            redirect_stdout(io.StringIO()):
                        argv = ['--repo', str(self.repo), '--reviewer', reviewer,
                                '--claude-model', 'claude-fixture', '--codex-model', 'fixture-codex']
                        if fallback:
                            argv.append('--allow-fallback')
                        if reviewer == 'claude' or fallback:
                            with self.assertRaises(ValueError):
                                review_dispatch.main(argv)
                            codex.assert_not_called()
                        else:
                            self.assertEqual(review_dispatch.main(argv), 0)
                            codex.assert_called_once()
                        claude.assert_not_called()

    def test_fallback_duration_matches_default_attempt_budgets(self):
        import agent_process
        guide = (ROOT.parent / 'docs/REVIEW_RUNNING.md').read_text()
        duration = re.search(r'two timed-out attempts\s+take about 2 x `REVIEW_TIMEOUT_SECONDS`\s+'
                             r'\(about (\w+) minutes at the default (\d+) s\)', guide)
        self.assertIsNotNone(duration)
        self.assertEqual(int(duration[2]), agent_process.DEFAULT_REVIEW_TIMEOUT)
        self.assertEqual({'sixty': 60, 'ninety': 90}[duration[1]] * 60,
                         2 * agent_process.DEFAULT_REVIEW_TIMEOUT)

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
        # A caller that ignores SIGINT (a `&` job of a non-interactive shell, nohup) passes that
        # on, the adapters keep an ignored SIGINT ignored (hold()), and the cancel cases failed
        # only there. Each test starts from Python's own default, its children from SIG_DFL.
        self.addCleanup(signal.signal, signal.SIGINT, signal.signal(signal.SIGINT, signal.default_int_handler))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "project"
        self.repo.mkdir()
        os.environ['FIXTURE_REPO'] = str(self.repo)
        # The user's own backend folder is never read by a test (KARARLAR D09 inv2#80).
        os.environ['MYAGENTKIT_BACKENDS_DIR'] = str(self.root / 'user-backends')
        self.fixture = self.root / "claude"
        self.fixture = python_cli(self.fixture, FIXTURE)
        self.git("init", "-q")
        # Git for Windows turns autocrlf on system-wide: archive and checkout bytes then differ.
        self.git("config", "core.autocrlf", "false")
        (self.repo / '.gitignore').write_bytes(IGNORE_RULES)
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

    def test_a_repository_without_a_commit_is_refused_with_the_setup_route(self):
        # A first setup reviews on an unborn HEAD: a bare rev-parse died with "ambiguous
        # argument 'HEAD'" and named no way on (#176).
        unborn = self.root / 'unborn'
        subprocess.run(['git', 'init', '-q', str(unborn)], check=True, capture_output=True)
        (unborn / 'file.py').write_text('new\n')
        subprocess.run(['git', '-C', str(unborn), 'add', '.'], check=True, capture_output=True)
        with self.assertRaises(bridge.BridgeError) as caught:
            bridge.snapshot(unborn, 'uncommitted', None)
        self.assertIn('HEAD names no commit (a new repository or an orphan branch)', str(caught.exception))
        self.assertIn('setup/INTERVIEW.md, Phase 4 step 6', str(caught.exception))
        # An orphan branch in a repository with commits: the same refusal, not "no commit yet".
        self.git('checkout', '-q', '--orphan', 'fresh')
        with self.assertRaises(bridge.BridgeError) as caught:
            bridge.snapshot(self.repo, 'uncommitted', None)
        self.assertIn('HEAD names no commit (a new repository or an orphan branch)', str(caught.exception))

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
        # A named filter on a changed path refuses it even with no driver configured here: the
        # next machine may configure one (a fresh machine's LFS, r8). With none, nothing is hidden.
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on bypass.py'):
            bridge.snapshot(self.repo, 'uncommitted', None)
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
        (self.repo / 'bypass.py').unlink()
        (self.repo / '.gitattributes').write_text('file.py ident\n')
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on file.py'):
            bridge.snapshot(self.repo, 'uncommitted', None)

    def test_an_untracked_filtered_addition_is_refused_without_a_driver(self):
        from unittest.mock import patch
        environment = patch.dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        environment.start()
        self.addCleanup(environment.stop)
        (self.repo / '.gitattributes').write_text('*.bin filter=lfs\n')
        self.commit_fixture('Named filter without a driver')
        configured = subprocess.run(['git', '-C', str(self.repo), 'config', '--get-regexp',
                                     r'^filter\..*\.(clean|process)$'], capture_output=True)
        self.assertEqual(configured.returncode, 1, configured.stdout)
        (self.repo / 'asset.bin').write_bytes(b'version https://git-lfs.github.com/spec/v1\n'
                                             b'oid sha256:' + b'a' * 64 + b'\nsize 42\n')
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on asset.bin'):
            bridge.snapshot(self.repo, 'uncommitted', None)

    def test_an_lfs_file_the_review_does_not_change_is_no_refusal(self):
        # Git LFS sets filter.lfs.clean in the global config, and every LFS file in the
        # checkout refused every review, a code-only one included. A file whose raw bytes are
        # proven to be what HEAD records gives a filter nothing to hide; a changed one does.
        clean = self.root / 'lfs-clean.py'
        clean.write_text(  # git-lfs clean: content to a pointer; a pointer passes through
            'import hashlib, sys\ndata = sys.stdin.buffer.read()\n'
            'if not data.startswith(b"version https://git-lfs"):\n'
            '    data = b"version https://git-lfs.github.com/spec/v1\\noid sha256:%s\\nsize %d\\n" % (\n'
            '        hashlib.sha256(data).hexdigest().encode(), len(data))\n'
            'sys.stdout.buffer.write(data)\n')
        # A host's filter.lfs.process overrides our clean command. Use our own driver,
        # as lfs_fixture() does, so the test never invokes the installed Git LFS CLI.
        self.git('config', 'filter.fakelfs.clean', '"%s" "%s"' % (sys.executable, clean))
        (self.repo / '.gitattributes').write_text('*.bin filter=fakelfs\n')
        asset, pointer = self.repo / 'asset.bin', self.repo / 'unsmudged.bin'
        asset.write_bytes(b'large binary content\n')
        pointer.write_bytes(b'other binary content\n')
        self.commit_fixture('LFS fixture')
        self.assertTrue(self.git('cat-file', 'blob', 'HEAD:asset.bin').stdout.startswith(b'version https://'))
        # A checkout made with GIT_LFS_SKIP_SMUDGE holds the pointer itself: the blob's bytes.
        pointer.write_bytes(self.git('cat-file', 'blob', 'HEAD:unsmudged.bin').stdout)
        (self.repo / 'file.py').write_text('CODE_ONLY_CHANGE\n')
        diff = bridge.snapshot(self.repo, 'uncommitted', None)[2]
        self.assertIn('CODE_ONLY_CHANGE', diff)
        self.assertNotIn('.bin', diff)
        # Changed content of the same size: the size matches the pointer, the sha256 does not.
        asset.write_bytes(b'LARGE BINARY CONTENT\n')
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on asset.bin, '
                                    '.* and the review changes it'):
            bridge.snapshot(self.repo, 'uncommitted', None)
        asset.write_bytes(b'large binary content\n')
        pointer.write_bytes(b'other binary content\n')
        self.commit_fixture('Code only')
        self.assertIn('CODE_ONLY_CHANGE', bridge.snapshot(self.repo, 'commit', 'HEAD')[2])
        # A commit that changes the LFS file shows its pointer, not its content: refused, though
        # the checkout matches HEAD.
        asset.write_bytes(b'new binary content\n')
        self.commit_fixture('Asset change')
        for scope, reference in (('commit', 'HEAD'), ('base', 'HEAD~1')):
            with self.subTest(scope=scope):
                with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on asset.bin'):
                    bridge.snapshot(self.repo, scope, reference)

    def lfs_fixture(self):
        """Commit asset.bin through a git-lfs-like clean filter (content to a pointer); return its path.
        The driver is not named lfs: a host's global filter.lfs.process (git lfs install) would
        replace its clean command, and the proof does not read the driver's name."""
        clean = self.root / 'lfs-clean.py'
        clean.write_text(
            'import hashlib, sys\ndata = sys.stdin.buffer.read()\n'
            'if not data.startswith(b"version https://git-lfs"):\n'
            '    data = b"version https://git-lfs.github.com/spec/v1\\noid sha256:%s\\nsize %d\\n" % (\n'
            '        hashlib.sha256(data).hexdigest().encode(), len(data))\n'
            'sys.stdout.buffer.write(data)\n')
        self.git('config', 'filter.fakelfs.clean', '"%s" "%s"' % (sys.executable, clean))
        (self.repo / '.gitattributes').write_text('*.bin filter=fakelfs\n')
        asset = self.repo / 'asset.bin'
        asset.write_bytes(b'large binary content\n')
        self.commit_fixture('LFS fixture')
        self.assertTrue(self.git('cat-file', 'blob', 'HEAD:asset.bin').stdout.startswith(b'version https://'))
        return asset

    def test_an_lfs_file_changed_after_its_proof_is_refused(self):
        # Proven unchanged, then replaced before the diff and the fingerprint read it (an
        # editor's save, a build): both saw the new bytes, agreed, and the change was reviewed.
        from unittest.mock import patch
        asset = self.lfs_fixture()
        (self.repo / 'file.py').write_text('CODE_ONLY_CHANGE\n')
        real, calls = bridge.committed_as_is, []

        def proven_then_replaced(repo, head, name):
            proven = real(repo, head, name)
            if not calls:
                asset.write_bytes(b'replaced after the proof\n')
            calls.append(name)
            return proven
        with patch.object(bridge, 'committed_as_is', proven_then_replaced):
            with self.assertRaisesRegex(bridge.BridgeError, 'attribute on asset.bin, which changed while the '
                                        'review was being prepared'):
                bridge.snapshot(self.repo, 'uncommitted', None)
        self.assertEqual(calls[0], b'asset.bin')

    def test_the_payload_never_runs_the_filter_of_a_proven_lfs_file(self):
        # A clean driver whose answer changes between calls (here: only while the payload diff
        # runs) said "unchanged" to every check and put its other answer in the reviewer's diff.
        from unittest.mock import patch
        asset = self.lfs_fixture()
        marker = self.root / 'odd-answer'
        clean = self.root / 'lfs-clean.py'
        clean.write_text(clean.read_text() + 'import os\nif os.path.exists(%r):\n'
                         '    sys.stdout.buffer.write(b"ODD_FILTER_ANSWER\\n")\n' % str(marker))
        stamp = asset.stat().st_mtime + 10
        os.utime(asset, (stamp, stamp))
        (self.repo / 'file.py').write_text('CODE_ONLY_CHANGE\n')
        real = bridge.git

        def odd_during_payload(repo, *args, **kwargs):
            payload = args[:1] == ('diff',) and '--binary' in args
            if payload:
                marker.touch()
            try:
                return real(repo, *args, **kwargs)
            finally:
                if payload and marker.exists():
                    marker.unlink()
        with patch.object(bridge, 'git', odd_during_payload):
            diff = bridge.snapshot(self.repo, 'uncommitted', None)[2]
        self.assertIn('CODE_ONLY_CHANGE', diff)
        self.assertNotIn('asset.bin', diff)

    def test_an_lfs_change_only_the_index_holds_is_refused(self):
        # A different pointer staged for asset.bin, the working file put back to HEAD's content:
        # the working tree proves nothing changed, `git diff HEAD` shows nothing, and the commit
        # that follows carries an LFS object the reviewer never saw.
        asset = self.lfs_fixture()
        (self.repo / 'file.py').write_text('CODE_ONLY_CHANGE\n')
        self.assertIn('CODE_ONLY_CHANGE', bridge.snapshot(self.repo, 'uncommitted', None)[2])
        asset.write_bytes(b'staged other content\n')
        self.git('add', 'asset.bin')
        asset.write_bytes(b'large binary content\n')
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on asset.bin'):
            bridge.snapshot(self.repo, 'uncommitted', None)
        # A staged deletion leaves no file and no index entry to look at.
        self.git('reset', '-q', 'HEAD', '--', 'asset.bin')
        self.git('rm', '-q', 'asset.bin')
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on asset.bin'):
            bridge.snapshot(self.repo, 'uncommitted', None)

    def test_an_lfs_change_is_refused_when_this_machine_configures_no_lfs_driver(self):
        # A fresh machine: .gitattributes names the filter, no filter.<driver>.clean or .process
        # is configured. A different pointer staged, the working file put back to HEAD's, a
        # code change beside it: `git diff HEAD` shows the restored bytes, the next commit the
        # staged pointer. For each side of the range, the named filter alone refuses it.
        asset = self.lfs_fixture()
        self.git('config', '--unset', 'filter.fakelfs.clean')
        pointer = asset.read_bytes()
        other = (b'version https://git-lfs.github.com/spec/v1\noid sha256:' + b'a' * 64 + b'\nsize 5\n')
        asset.write_bytes(other)
        self.git('add', 'asset.bin')
        asset.write_bytes(pointer)
        (self.repo / 'file.py').write_text('CODE_ONLY_CHANGE\n')
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on asset.bin'):
            bridge.snapshot(self.repo, 'uncommitted', None)
        asset.write_bytes(other)
        self.commit_fixture('Other pointer, no driver configured')
        for scope, reference in (('commit', 'HEAD'), ('base', 'HEAD~1')):
            with self.subTest(scope=scope):
                with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on asset.bin'):
                    bridge.snapshot(self.repo, scope, reference)
        # An LFS file the review leaves alone still passes on its proof.
        (self.repo / 'file.py').write_text('ANOTHER_CODE_CHANGE\n')
        self.assertIn('ANOTHER_CODE_CHANGE', bridge.snapshot(self.repo, 'uncommitted', None)[2])

    def test_an_lfs_rule_and_object_only_the_index_holds_are_refused(self):
        # The attribute is staged too: a filter rule for *.bin and the pointer it makes are in
        # the index, while the working tree and HEAD both hold neither. Read in the working tree
        # and at HEAD, asset.bin was not filtered, and the commit that follows was never seen.
        attributes, asset = self.repo / '.gitattributes', self.repo / 'asset.bin'
        attributes.write_text('*.txt text\n')
        asset.write_bytes(b'plain binary content\n')
        self.commit_fixture('Unfiltered asset')
        clean = self.root / 'lfs-clean.py'
        clean.write_text(
            'import hashlib, sys\ndata = sys.stdin.buffer.read()\n'
            'sys.stdout.buffer.write(b"version https://git-lfs.github.com/spec/v1\\noid sha256:%s\\nsize %d\\n" % (\n'
            '    hashlib.sha256(data).hexdigest().encode(), len(data)))\n')
        self.git('config', 'filter.fakelfs.clean', '"%s" "%s"' % (sys.executable, clean))
        attributes.write_text('*.txt text\n*.bin filter=fakelfs\n')
        asset.write_bytes(b'unseen staged content\n')
        self.git('add', '.gitattributes', 'asset.bin')
        self.assertTrue(self.git('show', ':asset.bin').stdout.startswith(b'version https://'))
        attributes.write_text('*.txt text\n')
        asset.write_bytes(b'plain binary content\n')
        (self.repo / 'file.py').write_text('CODE_ONLY_CHANGE\n')
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on asset.bin'):
            bridge.snapshot(self.repo, 'uncommitted', None)

    def test_a_range_that_deletes_renames_or_unfilters_an_lfs_file_is_refused(self):
        # The filtered paths were read from the current checkout only: a commit that deleted
        # asset.bin, renamed it out of the filter, or dropped its attribute while changing it,
        # left no filtered path behind, and its pointer-side diff was reviewed as the change.
        self.lfs_fixture()
        changes = {
            'deleted': lambda: self.git('rm', '-q', 'asset.bin'),
            'renamed out of the filter': lambda: self.git('mv', 'asset.bin', 'asset.dat'),
            'attribute removed while changed': lambda: (
                (self.repo / '.gitattributes').write_text(''),
                (self.repo / 'asset.bin').write_bytes(b'new content, no longer filtered\n')),
        }
        for change, apply in changes.items():
            apply()
            self.commit_fixture(change)
            for scope, reference in (('commit', 'HEAD'), ('base', 'HEAD~1')):
                with self.subTest(change=change, scope=scope):
                    with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on asset.bin'):
                        bridge.snapshot(self.repo, scope, reference)
            self.git('reset', '-q', '--hard', 'HEAD~1')

    def test_a_filtered_file_whose_rendered_diff_disagrees_with_its_bytes_is_refused(self):
        # Raw bytes equal to HEAD's did not prove what Git renders: a clean driver configured
        # after the commit drops SECRET, and `git diff HEAD` claims the line was deleted while
        # the copy the reviewer reads still holds it.
        secret = self.repo / 'secret.txt'
        secret.write_text('SECRET\nkeep\n')
        (self.repo / '.gitattributes').write_text('secret.txt filter=strip\n')
        self.commit_fixture('Unfiltered at commit time')
        os.utime(secret, (time.time() - 100, time.time() - 100))
        self.git('update-index', '--refresh')
        self.git('config', 'filter.strip.clean', "sed '/SECRET/d'")
        (self.repo / 'file.py').write_text('CODE_ONLY_CHANGE\n')
        # Untouched since then, the file is clean by Git's stat cache and no diff names it. Raw
        # bytes equal to a blob prove nothing about a filter; only an LFS pointer's sha256 does.
        self.assertNotIn(b'secret.txt', self.git('diff', '--name-only', 'HEAD').stdout)
        # The review does not change it, and the refusal says why it is refused all the same.
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on secret.txt, '
                                    '.* and it is not a Git LFS file left unchanged since HEAD'):
            bridge.snapshot(self.repo, 'uncommitted', None)
        secret.write_text('SECRET\nkeep\n')
        os.utime(secret, (time.time() + 10, time.time() + 10))
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on secret.txt'):
            bridge.snapshot(self.repo, 'uncommitted', None)
        # An LFS pointer whose content the working file matches by sha256, while the configured
        # driver renders something else: the rendered diff names the file, so it is refused.
        secret.unlink()
        (self.repo / '.gitattributes').write_text('')
        self.commit_fixture('No secret')
        asset = self.lfs_fixture()
        self.git('config', 'filter.fakelfs.clean', 'cat')
        asset.write_bytes(b'large binary content\n')
        os.utime(asset, (time.time() + 20, time.time() + 20))
        self.assertIn(b'asset.bin', self.git('diff', '--name-only', 'HEAD').stdout)
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on asset.bin'):
            bridge.snapshot(self.repo, 'uncommitted', None)

    def test_a_filtered_review_archive_the_scope_excludes_refuses_nothing(self):
        # The scope leaves review archives out, but the names the filter refusal checked did
        # not: a modified, filtered archive refused a review whose scope never held it. Archives
        # are ignored now; one an older version committed is tracked all the same.
        archive = self.repo / 'docs/reviews/20260101T000000Z-codex-review.md'
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text('first review\n')
        (self.repo / '.gitattributes').write_text('docs/reviews/*.md filter=strip\n')
        self.git('add', '-f', str(archive))
        self.commit_fixture('Filtered archive')
        self.assertIn(b'docs/reviews/', self.git('ls-files').stdout)
        self.git('config', 'filter.strip.clean', 'cat')
        archive.write_text('second review\n')
        (self.repo / 'file.py').write_text('CODE_ONLY_CHANGE\n')
        diff = bridge.snapshot(self.repo, 'uncommitted', None)[2]
        self.assertIn('CODE_ONLY_CHANGE', diff)
        self.assertNotIn('second review', diff)

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

            def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
                self.git('update-ref', 'refs/heads/review-base', intermediate)
                if '-o' in command:
                    Path(command[command.index('-o') + 1]).write_bytes(b'VERDICT: Accept\n')
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

            def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
                self.git('update-ref', '-d', 'refs/heads/review-base')
                if '-o' in command:
                    Path(command[command.index('-o') + 1]).write_bytes(b'VERDICT: Accept\n')
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

    def test_one_review_resolves_its_base_reference_once(self):
        # Resolved three times in one review (the diff, the usage record, the carried-round
        # check), a reference moved in between gave a diff against one commit, a record keyed
        # to another and a carried round refused against the second.
        from contextlib import redirect_stdout
        from io import StringIO
        import shutil
        from unittest.mock import patch
        import codex_bridge
        original = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        (self.repo / 'intermediate.txt').write_text('INTERMEDIATE_CHANGE\n')
        self.commit_fixture('Intermediate revision')
        intermediate = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        (self.repo / 'file.py').write_text('final\n')
        self.commit_fixture('Reviewed revision')
        # A git that moves the reference right after the review's first resolve of it, once.
        shim, moved, real = self.root / 'shim', self.root / 'moved', shutil.which('git')
        shim.mkdir()
        python_cli(shim / 'git', PYTHON_SHEBANG +
                   'import pathlib, subprocess, sys\n'
                   'real, moved, repo, intermediate = %r\n'
                   'status = subprocess.run([real, *sys.argv[1:]]).returncode\n'
                   'moved = pathlib.Path(moved)\n'
                   'if "--verify review-base^{commit}" in " ".join(sys.argv[1:]) and not moved.exists():\n'
                   '    moved.touch()\n'
                   '    subprocess.run([real, "-C", repo, "update-ref", "refs/heads/review-base", intermediate],\n'
                   '                   check=True)\n'
                   'raise SystemExit(status)\n' % ((real, str(moved), str(self.repo), intermediate),))
        for main, args in ((bridge.main, ['review']),
                           (codex_bridge.main, ['--model', 'fixture-codex-model'])):
            label = 'moving-base-' + ('claude' if main is bridge.main else 'codex')
            prompts = []

            def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
                prompts.append(prompt)
                if '-o' in command:
                    Path(command[command.index('-o') + 1]).write_bytes(b'VERDICT: Accept\n')
                    value = {'type': 'turn.completed', 'usage': {}}
                else:
                    value = {'type': 'result', 'subtype': 'success', 'is_error': False,
                             'modelUsage': {'claude-opus-5': {}}, 'structured_output':
                             {'verdict': 'Accept', 'findings': [], 'manual_checks': []}}
                return {'exit_code': 0, 'stdout': json.dumps(value), 'stderr': '',
                        'termination': None, 'duration_ms': 1}

            with self.subTest(label=label):
                self.git('update-ref', 'refs/heads/review-base', original)
                moved.unlink(missing_ok=True)
                received = []
                # Round one, nothing moves; round two, the reference moves after its first resolve.
                for path in (os.environ['PATH'], str(shim) + os.pathsep + os.environ['PATH']):
                    with patch.dict(os.environ, self.review_env(MYAGENTKIT_TASK_ID=label, PATH=path)), \
                            patch('agent_process.run', side_effect=execution), redirect_stdout(StringIO()):
                        main([*args, '--repo', str(self.repo), '--base', 'review-base'], received.append)
                self.assertTrue(moved.exists(), 'the reference never moved')
                self.assertEqual(received[0]['status'], 'completed', received[0])
                # The diff, the carried round and the record all use the commit resolved first.
                self.assertIn('INTERMEDIATE_CHANGE', prompts[1])
                self.assertIn('This is review round 2', prompts[1])
                usage = json.loads(Path(received[1]['usage_record']).read_text())
                self.assertEqual(usage['task']['resolved'], original)
                # The reference did move during the review: the result is stale, as before.
                self.assertEqual(received[1]['failure_kind'], 'stale_checkout')

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
            def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
                if '-o' in command:
                    Path(command[command.index('-o') + 1]).write_bytes(b'VERDICT: Accept\n')
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

        def quota(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            launched.append(command[0])
            value = ({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}
                     if '-o' in command else
                     {'type': 'result', 'subtype': 'success', 'is_error': True,
                      'api_error_status': 429, 'modelUsage': {'claude-opus-5': {}}})
            return {'exit_code': 1, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        def cancel_during_evidence(repo, path, text, **kwargs):
            if path.parent.name == 'reviews':
                send_cancel(signal.SIGTERM)
            return publish(repo, path, text, **kwargs)

        def cancel_during_record(*args, **kwargs):
            send_cancel(signal.SIGTERM)
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

    @posix_only
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

        def quota(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            launched.append(command[0])
            value = ({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}
                     if '-o' in command else
                     {'type': 'result', 'subtype': 'success', 'is_error': True,
                      'api_error_status': 429, 'modelUsage': {'claude-opus-5': {}}})
            # Inject during reviewer cleanup only; preparation also kills its process groups.
            with patch.object(agent_process.os, 'killpg', side_effect=killpg):
                return real_run([sys.executable, '-c', 'print(%r)' % json.dumps(value)],
                                prompt, repo, timeout, into)

        def killpg(pid, sig):
            send_cancel(signal.SIGTERM)
            real_killpg(pid, sig)

        for primary in ('claude', 'codex'):
            launched, out = [], StringIO()
            with self.subTest(primary=primary), patch.dict(os.environ, self.review_env()), \
                    patch('agent_process.run', side_effect=quota), redirect_stdout(out):
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

    @posix_only
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

        def absent(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            launched.append(command[0])
            return real_run([str(self.root / 'absent-cli')], prompt, repo, timeout, into)

        class CancelOnClose(selectors.DefaultSelector):
            def close(self):
                send_cancel(signal.SIGTERM)
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

    def test_a_cancel_before_runs_guard_never_launches_the_claude_reviewer(self):
        # The adapter's noting handler is up before run() arms its own guard: a cancel in
        # between was noted, the paid reviewer launched anyway and ran to its end.
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import agent_process
        real_run, launched = agent_process.run, self.root / 'launched'

        def run(*args, **kwargs):
            send_cancel(signal.SIGTERM)
            return real_run(*args, **kwargs)

        received = []
        with patch.dict(os.environ, self.review_env(CLAUDE_CLI_BIN=str(self.fixture),
                                                    PROMPT_LOG=str(launched))), \
                patch.object(agent_process, 'run', side_effect=run), redirect_stdout(StringIO()):
            code = bridge.main(['review', '--repo', str(self.repo), '--uncommitted'], received.append)
        self.assertFalse(launched.exists(), 'a cancel noted before the launch did not stop it')
        self.assertEqual(code, 5)
        self.assertEqual((received[0]['failure_kind'], received[0]['cancelled']), ('cancelled', True))
        self.persisted_cancel(received[0])

    @posix_only  # Needs a signal mask during the individual handler restores.
    def test_a_guard_hands_every_handler_back_and_notes_a_cancel_meanwhile(self):
        # OneShot.__exit__ restored the handlers one at a time: a cancel after the first restore
        # met the caller's raising handler there, and the other signals stayed routed to the
        # inner guard, whose notes nobody reads; a later cancel on one of them was lost. Now
        # every handler goes back, and a cancel meanwhile is the guard's, returned by run().
        from unittest.mock import patch
        import agent_process
        real_signal, fired = signal.signal, []
        outer, inner = agent_process.OneShot(), agent_process.OneShot()

        def install(sig, handler):
            previous = real_signal(sig, handler)
            if handler is outer and not fired:
                fired.append(sig)
                send_cancel(sig)
            return previous

        with outer:
            inner.armed = False
            try:
                with patch.object(agent_process.signal, 'signal', side_effect=install):
                    with inner:
                        pass
            except KeyboardInterrupt:
                self.fail('a cancel while the guard handed back raised out of it')
            routed = {sig: signal.getsignal(sig) for sig in inner.previous}
        self.assertTrue(fired)
        self.assertEqual((inner.noted, outer.noted), (fired, []))
        self.assertTrue(all(handler is outer for handler in routed.values()), routed)

    @posix_only  # Injects inside a POSIX masked restore, rather than Windows settlement.
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
                    send_cancel(signal.SIGTERM)
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

    @posix_only
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
        caller_int = signal.getsignal(signal.SIGINT)

        def quota(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            return {'exit_code': 1, 'stdout': json.dumps({'type': 'turn.failed',
                    'error': {'message': 'usage limit reached'}}), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        def install(sig, handler):
            # run() is replaced, so the only handler put back that is not the adapter's own
            # is its restore; SIGINT goes back first, SIGTERM still meets the noting guard.
            if sig == signal.SIGINT and handler is caller_int and not fired:
                fired.append(sig)
                send_cancel(signal.SIGTERM)
            return real_signal(sig, handler)

        class CallerCancel(Exception):
            pass

        def caller(signum, frame):
            raise CallerCancel

        # Held while the handlers go back, the cancel reaches the caller's own handler once
        # the records say cancelled; a caller default would end the test run there.
        received, caught = [], []
        previous = real_signal(signal.SIGTERM, caller)
        try:
            with patch.dict(os.environ, self.review_env()), patch('agent_process.run', side_effect=quota), \
                    patch.object(agent_process.signal, 'signal', side_effect=install), redirect_stdout(StringIO()):
                try:
                    codex_bridge.main(['--model', 'fixture-codex-model', '--repo', str(self.repo),
                                       '--uncommitted'], received.append)
                except CallerCancel:
                    caught.append(True)
        finally:
            real_signal(signal.SIGTERM, previous)
        self.assertTrue(fired)
        self.assertEqual(caught, [True])
        self.assertEqual((received[0]['failure_kind'], received[0]['cancelled']), ('cancelled', True))
        self.persisted_cancel(received[0])

    @posix_only
    def test_a_cancel_after_the_hand_back_sample_is_persisted_before_the_caller_gets_it(self):
        # handing_back() sampled the pending cancels once: one arriving after that sample,
        # while the adapter still held the signals, reached the caller's handler with the
        # usage record and archive of a quota-failed attempt still saying quota.
        from contextlib import redirect_stdout
        from io import StringIO
        import signal
        from unittest.mock import patch
        import agent_process
        import codex_bridge
        real_pending = signal.sigpending

        def quota(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            value = ({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}
                     if '-o' in command else
                     {'type': 'result', 'subtype': 'success', 'is_error': True,
                      'api_error_status': 429, 'modelUsage': {'claude-opus-5': {}}})
            return {'exit_code': 1, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        def pending():
            value = real_pending()
            if not fired:
                fired.append(True)
                send_cancel(signal.SIGTERM)
            return value

        class CallerCancel(Exception):
            pass

        def caller(signum, frame):
            raise CallerCancel

        for name, adapter in (('claude', (bridge.main, ['review'])),
                              ('codex', (codex_bridge.main, ['--model', 'fixture-codex-model']))):
            fired, received, caught = [], [], []
            previous = signal.signal(signal.SIGTERM, caller)
            try:
                with self.subTest(adapter=name), patch.dict(os.environ, self.review_env()), \
                        patch('agent_process.run', side_effect=quota), \
                        patch.object(agent_process.signal, 'sigpending', side_effect=pending), \
                        redirect_stdout(StringIO()):
                    try:
                        adapter[0]([*adapter[1], '--repo', str(self.repo), '--uncommitted'],
                                   received.append)
                    except CallerCancel:
                        caught.append(True)
                    self.assertTrue(fired)
                    self.assertEqual(caught, [True])
                    self.assertEqual((received[0]['failure_kind'], received[0]['cancelled']),
                                     ('cancelled', True))
                    self.persisted_cancel(received[0])
            finally:
                signal.signal(signal.SIGTERM, previous)

    def test_a_cancelled_codex_review_starts_no_closing_quota_read(self):
        # The closing quota read starts another CLI process for up to five seconds: after a
        # cancel the adapter stops instead, and records the read as skipped.
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import codex_bridge
        import codex_quota
        reads, received = [], []

        def snapshot(cli, repo, timeout=5):
            reads.append(cli)
            return {'status': 'unavailable', 'buckets': {}}

        def cancelled(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            return {'exit_code': None, 'stdout': '', 'stderr': '', 'termination': 'cancelled',
                    'cancelled': True, 'duration_ms': 1}

        with patch.dict(os.environ, self.review_env(MYAGENTKIT_CAPTURE_QUOTA='1')), \
                patch.object(codex_quota, 'snapshot', side_effect=snapshot), \
                patch('agent_process.run', side_effect=cancelled), redirect_stdout(StringIO()):
            codex_bridge.main(['--model', 'fixture-codex-model', '--repo', str(self.repo),
                               '--uncommitted'], received.append)
        self.assertEqual(len(reads), 1)
        usage = json.loads(Path(received[0]['usage_record']).read_text())
        self.assertEqual(usage['usage']['account_quota_snapshots']['after'],
                         {'status': 'skipped: review cancelled'})

    def test_a_quota_read_that_raises_still_records_the_completed_review(self):
        # The closing quota read raised (BrokenPipeError from a reader that exited at once),
        # the adapter caught only a cancel there, and a completed, paid review ended with no
        # evidence and no usage record. Any error of the optional read is "unavailable".
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import codex_bridge
        import codex_quota
        for error in (BrokenPipeError(32, 'Broken pipe'), RuntimeError('unexpected')):
            reads, received = [], []

            def snapshot(cli, repo, timeout=5):
                reads.append(cli)
                if len(reads) == 2:
                    raise error
                return {'status': 'unavailable', 'buckets': {}}

            with self.subTest(error=repr(error)), \
                    patch.dict(os.environ, self.review_env(REVIEW_CLI_BIN=str(self.build_fake_codex()),
                                                           MYAGENTKIT_CAPTURE_QUOTA='1')), \
                    patch.object(codex_quota, 'snapshot', side_effect=snapshot), redirect_stdout(StringIO()):
                code = codex_bridge.main(['--model', 'fixture-codex-model', '--repo', str(self.repo),
                                          '--uncommitted'], received.append)
                self.assertEqual(len(reads), 2)
                self.assertEqual((code, received[0]['status']), (0, 'completed'))
                self.assertTrue(Path(received[0]['evidence']).is_file())
                usage = json.loads(Path(received[0]['usage_record']).read_text())
                self.assertEqual(usage['status'], 'completed')
                self.assertEqual(usage['usage']['account_quota_snapshots']['after']['status'], 'unavailable')

    def test_a_cancel_between_the_codex_persist_and_result_samples_is_persisted(self):
        # The persistence check and the returned flag were two samples: a cancel noted between
        # them returned cancelled while the usage record and archive kept quota, and the final
        # correction skipped the repair because the result already said cancelled.
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import signal
        import agent_usage
        import codex_bridge
        recorded, fired = [], []

        class Execution(dict):
            # The first termination read after the record is the persistence sample: the cancel
            # lands after that sample has read the noting guard, before the result is built.
            def __getitem__(self, key):
                if key == 'termination' and recorded and not fired:
                    fired.append(True)
                    send_cancel(signal.SIGTERM)
                return dict.__getitem__(self, key)

        def quota(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            return Execution({'exit_code': 1, 'stdout': json.dumps({'type': 'turn.failed',
                              'error': {'message': 'usage limit reached'}}), 'stderr': '',
                              'termination': None, 'duration_ms': 1})

        record = agent_usage.record

        def recording(*args, **kwargs):
            value = record(*args, **kwargs)
            recorded.append(True)
            return value

        received = []
        with patch.dict(os.environ, self.review_env()), patch('agent_process.run', side_effect=quota), \
                patch.object(agent_usage, 'record', side_effect=recording), redirect_stdout(StringIO()):
            codex_bridge.main(['--model', 'fixture-codex-model', '--repo', str(self.repo),
                               '--uncommitted'], received.append)
        self.assertTrue(fired)
        self.assertEqual((received[0]['failure_kind'], received[0]['cancelled']), ('cancelled', True))
        self.persisted_cancel(received[0])

    @posix_only  # Windows installs a recorder at this point, before restoring the caller.
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
            # The first handler change after run() has returned: since the guard stays up to
            # the last line, that is the hand-back to the caller's handlers.
            if returned and not fired:
                fired.append(sig)
                send_cancel(signal.SIGTERM)
            return real_signal(sig, handler)

        class CallerCancel(Exception):
            pass

        def caller(signum, frame):
            raise CallerCancel

        received, caught = [], []
        previous = real_signal(signal.SIGTERM, caller)
        try:
            with patch.dict(os.environ, self.review_env(REVIEW_CLI_BIN=str(self.build_fake_codex()))), \
                    patch.object(agent_process, 'run', side_effect=run), \
                    patch.object(agent_process.signal, 'signal', side_effect=install), redirect_stdout(StringIO()):
                try:
                    codex_bridge.main(['--model', 'fixture-codex-model', '--repo', str(self.repo),
                                       '--uncommitted'], received.append)
                except KeyboardInterrupt:
                    self.fail('a cancel while the adapter switched to noting lost the completed review')
                except CallerCancel:
                    caught.append(True)
        finally:
            real_signal(signal.SIGTERM, previous)
        self.assertTrue(fired)
        self.assertEqual(caught, [True])
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

        def quota(command, prompt, repo, timeout, into=None, noted=None, watch=None):
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
                    send_cancel(signal.SIGTERM)
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

    def test_a_second_cancel_during_the_late_relabel_is_noted_by_either_adapter(self):
        # Both adapters put the caller's handlers back before persisting a late cancel: a
        # second one during the relabel met those handlers and ended the adapter before its
        # records, and the last line printed said cancelled: false over a quota failure.
        from contextlib import redirect_stdout
        from io import StringIO
        import signal
        from unittest.mock import patch
        import agent_process
        import codex_bridge
        real_signal, relabel = signal.signal, agent_usage.relabel_cancelled

        class CallerCancel(Exception):
            pass

        def caller(signum, frame):
            raise CallerCancel

        def quota(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            value = ({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}
                     if '-o' in command else
                     {'type': 'result', 'subtype': 'success', 'is_error': True,
                      'api_error_status': 429, 'modelUsage': {'claude-opus-5': {}}})
            return {'exit_code': 1, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        def second_cancel(*args, **kwargs):
            fired.append('relabel')
            send_cancel(signal.SIGTERM)
            return relabel(*args, **kwargs)

        class Blocked(StringIO):
            def write(self, text):
                # Either adapter: the first cancel while its result line is written. A cancel
                # while the handlers go back has its own test.
                if text.startswith(('{"status": "failed"', 'review invocation: ')) and not fired:
                    fired.append('print')
                    send_cancel(signal.SIGTERM)
                return super().write(text)

        for name, main, args, hooks in (
                ('claude', bridge.main, ['review', '--repo', str(self.repo), '--uncommitted'], ()),
                ('codex', codex_bridge.main, ['--model', 'fixture-codex-model', '--repo', str(self.repo),
                                              '--uncommitted'], ())):
            with self.subTest(adapter=name):
                fired, out, received = [], Blocked(), []
                previous = real_signal(signal.SIGTERM, caller)
                try:
                    with patch.dict(os.environ, self.review_env()), \
                            patch('agent_process.run', side_effect=quota), \
                            patch.object(agent_usage, 'relabel_cancelled', side_effect=second_cancel), \
                            redirect_stdout(out):
                        for hook in hooks:
                            hook.start()
                        try:
                            code = main(args, received.append)
                        except CallerCancel:
                            self.fail('a second cancel during the relabel ended the adapter')
                        finally:
                            for hook in hooks:
                                hook.stop()
                finally:
                    real_signal(signal.SIGTERM, previous)
                self.assertEqual(fired[1:], ['relabel'], fired)
                self.assertEqual(code, 5)
                self.persisted_cancel(received[0])
                last = out.getvalue().strip().splitlines()
                last = json.loads(next(line.removeprefix('review invocation: ') for line in reversed(last)
                                       if line.startswith(('{', 'review invocation: '))))
                self.assertEqual((last['cancelled'], last['failure_kind']), (True, 'cancelled'), out.getvalue())

    @posix_only  # Cancels after Windows' final settlement sample are explicitly excluded.
    def test_a_second_cancel_inside_the_handler_restoration_leaves_the_records_cancelled(self):
        # A first SIGTERM was noted while the adapter put the caller's SIGINT back; with the
        # caller's SIGTERM handler back, a second one ended the adapter before the late
        # correction, and the records of a quota-failed attempt still said quota.
        from contextlib import redirect_stdout
        from io import StringIO
        import signal
        from unittest.mock import patch
        import agent_process
        import codex_bridge
        real_signal = signal.signal

        class CallerCancel(Exception):
            pass

        def caller(signum, frame):
            raise CallerCancel

        def quota(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            value = ({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}
                     if '-o' in command else
                     {'type': 'result', 'subtype': 'success', 'is_error': True,
                      'api_error_status': 429, 'modelUsage': {'claude-opus-5': {}}})
            return {'exit_code': 1, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        def install(sig, handler):
            previous = real_signal(sig, handler)
            if sig == signal.SIGINT and handler is signal.default_int_handler and not fired:
                fired.append('first')
                send_cancel(signal.SIGTERM)
            elif sig == signal.SIGTERM and handler is caller and fired == ['first']:
                fired.append('second')
                send_cancel(signal.SIGTERM)
            return previous

        for name, main, args in (
                ('claude', bridge.main, ['review', '--repo', str(self.repo), '--uncommitted']),
                ('codex', codex_bridge.main, ['--model', 'fixture-codex-model', '--repo', str(self.repo),
                                              '--uncommitted'])):
            with self.subTest(adapter=name):
                fired, out, received, caught = [], StringIO(), [], []
                previous = real_signal(signal.SIGTERM, caller)
                try:
                    with patch.dict(os.environ, self.review_env()), \
                            patch('agent_process.run', side_effect=quota), \
                            patch.object(agent_process.signal, 'signal', side_effect=install), \
                            redirect_stdout(out):
                        try:
                            main(args, received.append)
                        except CallerCancel:
                            caught.append(True)
                finally:
                    real_signal(signal.SIGTERM, previous)
                self.assertEqual(fired, ['first', 'second'])
                self.persisted_cancel(received[0])
                last = out.getvalue().strip().splitlines()
                last = json.loads(next(line.removeprefix('review invocation: ') for line in reversed(last)
                                       if line.startswith(('{', 'review invocation: '))))
                self.assertEqual((last['cancelled'], last['failure_kind']), (True, 'cancelled'), out.getvalue())
                # Held while the records were corrected, the cancel still reaches the caller's handler.
                self.assertEqual(caught, [True])

    def test_a_cancel_while_the_codex_result_prints_still_reaches_the_dispatcher_checkpoint(self):
        # The Codex guard was gone before its result lines printed: a SIGTERM while stdout was
        # blocked ended the adapter, the failed attempt stayed quota, and the dispatcher never
        # wrote its final checkpoint.
        from contextlib import redirect_stdout
        from io import StringIO
        import signal
        import review_dispatch

        class CallerCancel(Exception):
            pass

        def caller(signum, frame):
            raise CallerCancel

        def quota(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            launched.append(command[0])
            return {'exit_code': 1, 'stdout': json.dumps({'type': 'turn.failed',
                    'error': {'message': 'usage limit reached'}}), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        class Blocked(StringIO):
            def write(self, text):
                if text.startswith('review invocation: ') and not fired:
                    fired.append(text)
                    send_cancel(signal.SIGTERM)
                return super().write(text)

        from unittest.mock import patch
        launched, fired, out = [], [], Blocked()
        previous = signal.signal(signal.SIGTERM, caller)
        try:
            with patch.dict(os.environ, self.review_env()), patch('agent_process.run', side_effect=quota), \
                    redirect_stdout(out):
                try:
                    code = review_dispatch.main(['--repo', str(self.repo), '--uncommitted', '--reviewer', 'codex',
                                                 '--allow-fallback', '--claude-model', 'claude-opus-5',
                                                 '--codex-model', 'fixture-codex-model'])
                except CallerCancel:
                    self.fail('a cancel while the Codex result printed ended the adapter:\n' + out.getvalue())
        finally:
            signal.signal(signal.SIGTERM, previous)
        self.assertTrue(fired)
        self.assertEqual(len(launched), 1, 'a cancelled review launched the other reviewer:\n' + out.getvalue())
        self.assertNotEqual(code, 0)
        chain = json.loads(next(line.removeprefix('review dispatch: ') for line in
                                out.getvalue().splitlines() if line.startswith('review dispatch: ')))
        self.assertEqual(chain['failure_kind'], 'cancelled')
        self.assertTrue(chain['attempts'][0]['cancelled'])
        self.persisted_cancel(chain['attempts'][0])

    def test_a_cancel_while_an_unverified_result_prints_keeps_its_completed_record(self):
        # rcode r2: the Claude adapter's late correction relabelled a checkout_unverified result
        # cancelled, and its completed record with it, so the paid round stopped counting; the
        # Codex adapter kept the record. Both keep it now and only mark the result cancelled.
        from contextlib import redirect_stdout
        from io import StringIO
        import signal
        from unittest.mock import patch
        import agent_process
        import claude_bridge
        import codex_bridge
        run = agent_process.run
        # The Codex adapter reads the checkout through claude_bridge, not this suite's copy.
        for name, main, args, line, module in (
                ('claude', bridge.main, ['review'], '{', bridge),
                ('codex', codex_bridge.main, ['--model', 'fixture-codex-model'], 'review invocation: ',
                 claude_bridge)):
            with self.subTest(adapter=name):
                ran, fired, received, snapshot = [], [], [], module.snapshot

                def look(*args):
                    if ran:
                        raise module.GitFailed('git diff failed: index cannot be read')
                    return snapshot(*args)

                def review(*args, **kwargs):
                    ran.append(True)
                    return run(*args, **kwargs)

                class Blocked(StringIO):
                    def write(self, text):
                        if text.startswith(line) and not fired:
                            fired.append(text)
                            send_cancel(signal.SIGTERM)
                        return super().write(text)

                out = Blocked()
                env = self.review_env(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLI_BIN=str(self.build_fake_codex()))
                with patch.dict(os.environ, env), patch.object(module, 'snapshot', look), \
                        patch.object(agent_process, 'run', review), redirect_stdout(out):
                    code = main([*args, '--repo', str(self.repo), '--uncommitted'], received.append)
                self.assertTrue(fired)
                self.assertEqual(code, 5, out.getvalue())
                self.assertEqual((received[0]['failure_kind'], received[0]['cancelled']),
                                 ('checkout_unverified', True), out.getvalue())
                usage = json.loads(Path(received[0]['usage_record']).read_text())
                self.assertEqual((usage['status'], usage['failure_kind']), ('completed', None))

    def test_a_review_stops_at_the_next_look_once_the_checkout_changed(self):
        # #118: the checkout was read only after the reviewer exited, so a stale review ran to
        # its end and was paid for. run() looks every WATCH_SECONDS and stops it on a change.
        from unittest.mock import patch
        import agent_process
        looks = []

        def watch():
            looks.append(True)
            return len(looks) == 2

        with patch.object(agent_process, 'WATCH_SECONDS', 0):
            result = agent_process.run([sys.executable, '-c', 'import time; time.sleep(60)'], '',
                                       self.root, 30, watch=watch)
        self.assertEqual((result['termination'], len(looks)), ('stale_checkout', 2))
        self.assertLess(result['duration_ms'], 20000)

    def test_a_slow_look_waits_its_interval_and_never_runs_past_the_deadline(self):
        # rpipe review Low: the interval ran from a look's start, so a look as slow as it ran back
        # to back, and a look begun near the deadline ran the reviewer past it. Looks of 3 s every
        # 2 s with an 8 s limit: one at 2 s (ends 5 s), the next due at 7 s would end past 8 s.
        from unittest.mock import patch
        import agent_process
        looks = []

        def watch():
            looks.append(True)
            time.sleep(3)
            return False

        with patch.object(agent_process, 'WATCH_SECONDS', 2):
            result = agent_process.run([sys.executable, '-c', 'import time; time.sleep(60)'], '',
                                       self.root, 8, watch=watch)
        self.assertEqual((result['termination'], len(looks)), ('timeout', 1))
        self.assertLess(result['duration_ms'], 9500)

    def test_both_adapters_stop_a_review_whose_checkout_changed_during_it(self):
        # #118: each adapter hands run() a look at the checkout; a change seen there stops the
        # reviewer, and the review fails as stale_checkout without waiting for its end.
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import agent_process
        import codex_bridge
        for name, main, args in (('claude', bridge.main, ['review']),
                                 ('codex', codex_bridge.main, ['--model', 'fixture-codex-model'])):
            with self.subTest(adapter=name):
                (self.repo / 'file.py').write_text('changed\n')
                looks, received = [], []

                def stopped(command, prompt, repo, timeout, into=None, noted=None, watch=None):
                    looks.append(watch())
                    (self.repo / 'file.py').write_text('edited during the review\n')
                    looks.append(watch())
                    return {'launched': True, 'exit_code': None, 'stdout': '', 'stderr': '',
                            'termination': 'stale_checkout', 'cancelled': False, 'duration_ms': 1}

                env = self.review_env(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLI_BIN=str(self.build_fake_codex()))
                with patch.dict(os.environ, env), patch.object(agent_process, 'run', stopped), \
                        redirect_stdout(StringIO()):
                    main([*args, '--repo', str(self.repo), '--uncommitted'], received.append)
                self.assertEqual(looks, [False, True])
                self.assertEqual((received[0]['status'], received[0]['failure_kind']),
                                 ('failed', 'stale_checkout'), received[0])
                if name == 'claude':
                    # A launched run's stop is named as such, never "Claude never ran".
                    self.assertIn('the reviewer was stopped early', received[0]['error'])

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

        def quota(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            value = ({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}
                     if '-o' in command else
                     {'type': 'result', 'subtype': 'success', 'is_error': True,
                      'api_error_status': 429, 'modelUsage': {'claude-opus-5': {}}})
            return {'exit_code': 1, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        def cancel_during_record(*args, **kwargs):
            send_cancel(signal.SIGTERM)
            return account(*args, **kwargs)

        def replacement_fails(repo, path, text, **kwargs):
            raise OSError('injected archive replacement failure')

        def directory_fsync_fails(repo, path, text, **kwargs):
            if WINDOWS:
                # Windows has no directory fsync. Inject the same post-replacement error
                # after the real publication, preserving the landed-bytes/hash oracle.
                publish(repo, path, text, **kwargs)
                raise OSError('injected directory fsync failure')
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
                    # Claude embeds this diagnostic in JSON; Codex prints it as plain text.
                    shown = json.dumps(str(evidence))[1:-1] if main is bridge.main else str(evidence)
                    if fault is archive_vanishes:
                        self.assertFalse(evidence.exists())
                        self.assertIn('the archive %s on disk could not be read (' % shown,
                                      out.getvalue())
                        self.assertIn('; the write reported: injected archive removal', out.getvalue())
                    else:
                        archive = evidence.read_bytes()
                        replaced = fault is directory_fsync_fails
                        self.assertIn(b'| failure_kind | cancelled |' if replaced
                                      else b'| failure_kind | %s |' % (b'rate_limited' if main is bridge.main
                                                                        else b'quota_exhausted'), archive)
                        self.assertEqual(usage['evidence_sha256'] == hashlib.sha256(archive).hexdigest(),
                                         replaced)
                        self.assertIn('the usage record says cancelled; the archive %s on disk %s; '
                                      'the write reported: %s'
                                      % (shown, 'matches the record (sha256 %s)'
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
                        self.assertEqual(rounds()[0], '')

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

    def test_a_failure_after_the_adapter_handed_over_its_result_keeps_that_result(self):
        # Issue #71: a completed Codex review (evidence and usage record both said completed)
        # was reported as adapter_error, because printing the review raised after the result
        # was handed over and the dispatcher replaced it. A checkout changed meanwhile is still
        # stale_checkout, named as such, never adapter_error. The adapter's NOTE goes to stderr,
        # captured here: uncaptured, it looked like a real cp1252 failure in the suite's log.
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import review_dispatch

        def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            if '-o' in command:
                Path(command[command.index('-o') + 1]).write_bytes(b'Low: A \xe2\x86\x92 B.\n\nVERDICT: Accept\n')
                value = {'type': 'turn.completed', 'usage': {}}
            else:
                value = {'type': 'result', 'subtype': 'success', 'is_error': False,
                         'modelUsage': {'claude-opus-5': {}}, 'structured_output':
                         {'verdict': 'Accept', 'findings': [], 'manual_checks': []}}
            return {'exit_code': 0, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        class Console(StringIO):
            # A console that cannot print the handed-over result: the first write naming the
            # evidence comes after the adapter's sink, in both adapters.
            def write(self, text):
                if '"evidence"' in text and not failed:
                    failed.append(text)
                    if change:
                        (repo / 'file.py').write_text('changed after the adapter check\n')
                    raise UnicodeEncodeError('cp1252', '→', 0, 1, 'character maps to <undefined>')
                return super().write(text)

        repo = self.repo
        for reviewer in ('codex', 'claude'):
            for change in (False, True):
                failed, out, err = [], Console(), StringIO()
                with self.subTest(reviewer=reviewer, checkout_changed=change), \
                        patch.dict(os.environ, self.review_env()), \
                        patch('agent_process.run', side_effect=execution), redirect_stdout(out), \
                        redirect_stderr(err):
                    code = review_dispatch.main(['--repo', str(repo), '--uncommitted', '--reviewer', reviewer,
                                                 '--claude-model', 'claude-opus-5',
                                                 '--codex-model', 'fixture-codex-model'])
                    self.assertTrue(failed)
                    chain = json.loads(next(line.removeprefix('review dispatch: ') for line in
                                            out.getvalue().splitlines() if line.startswith('review dispatch: ')))
                    attempt = chain['attempts'][0]
                    self.assertEqual((attempt['status'], attempt['failure_kind']), ('completed', None))
                    self.assertEqual(verdicts_of(attempt['evidence']), ['VERDICT: Accept'])
                    if change:
                        (repo / 'file.py').write_text('changed\n')
                        self.assertEqual(code, 5)
                        self.assertEqual(chain['failure_kind'], 'stale_checkout', out.getvalue())
                        self.assertIn('the checkout changed while the review ran', out.getvalue())
                        # The docs' terms: an ignored file never fails a review.
                        self.assertIn('a new untracked file Git does not ignore', out.getvalue())
                        # The chain failed: the NOTE must not say the result stands.
                        self.assertNotIn('the result stands', out.getvalue())
                        self.assertIn('the checkout changed, so the chain failed', out.getvalue())
                    else:
                        self.assertEqual(code, 0, out.getvalue())
                        self.assertEqual((chain['status'], chain['selected_reviewer']), ('completed', reviewer))
                        self.assertIn('the result stands as recorded in', out.getvalue())
                    self.assertIn('cp1252', attempt['error_after_result'])
                    self.assertIn('failed after it handed over its result', err.getvalue())

    def test_persistent_stdout_failure_does_not_lose_the_completed_dispatch_attempt(self):
        from contextlib import redirect_stderr, redirect_stdout
        from unittest.mock import patch
        import review_dispatch

        def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            if '-o' in command:
                Path(command[command.index('-o') + 1]).write_bytes(b'VERDICT: Accept\n')
                value = {'type': 'turn.completed', 'usage': {}}
            else:
                value = {'type': 'result', 'subtype': 'success', 'is_error': False,
                         'modelUsage': {'claude-opus-5': {}}, 'structured_output':
                         {'verdict': 'Accept', 'findings': [], 'manual_checks': []}}
            return {'exit_code': 0, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        class Console(io.StringIO):
            broken = False

            def write(self, text):
                self.broken |= '"evidence"' in text
                if self.broken:
                    raise BrokenPipeError('reader closed stdout permanently')
                return super().write(text)

        for reviewer in ('claude', 'codex'):
            with self.subTest(reviewer=reviewer), patch.dict(os.environ, self.review_env()), \
                    patch('agent_process.run', side_effect=execution), redirect_stdout(Console()), \
                    redirect_stderr(io.StringIO()):
                # A permanently closed console can still raise, but its disk result must stand.
                try:
                    review_dispatch.main(['--repo', str(self.repo), '--uncommitted', '--reviewer', reviewer,
                                          '--claude-model', 'claude-opus-5',
                                          '--codex-model', 'fixture-codex-model'])
                except BrokenPipeError:
                    pass
                records = self.repo / '.myagentkit/usage/chains'
                chain_id = os.environ['MYAGENTKIT_REVIEW_CHAIN_ID']
                chain = json.loads((records / (chain_id + '-1.json')).read_text())
                self.assertEqual(chain['status'], 'completed', chain)
                self.assertEqual(len(chain['attempts']), 1)
                attempt = chain['attempts'][0]
                self.assertEqual((attempt['status'], attempt['failure_kind']), ('completed', None))
                self.assertIn('permanently', attempt['error_after_result'])
                usage = json.loads(Path(attempt['usage_record']).read_text())
                self.assertEqual(usage['status'], 'completed')
                self.assertEqual(verdicts_of(attempt['evidence']), ['VERDICT: Accept'])

    def assert_closed_pipe_keeps_adapter_status(self, provider):
        scripts = self.install_wrapper()
        args = ['review', '--model', 'claude-opus-5'] if provider == 'claude' else ['--model', 'fixture-codex-model']
        source = ('import sys\nsys.path.insert(0, sys.argv[1])\n'
                  'sys.stdin.read(1)\nimport ' + provider + '_bridge as adapter\n'
                  'adapter.utf8_output()\nraise SystemExit(adapter.main(sys.argv[2:]))\n')
        for case, expected in (('accept', 0), ('quota', 5)):
            label = 'closed-pipe-' + provider + '-' + case
            env = self.review_env(MYAGENTKIT_TASK_ID=label, CLAUDE_CLI_BIN=str(self.fixture),
                                  REVIEW_CLI_BIN=str(self.build_fake_codex()), FIXTURE_CASE=case,
                                  CODEX_FIXTURE_CASE=case)
            with self.subTest(case=case), subprocess.Popen(
                    [sys.executable, '-X', 'utf8', '-B', '-c', source, str(scripts), *args,
                     '--repo', str(self.repo), '--uncommitted'], env=env,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
                # Close the real reader before allowing the adapter to run, with buffering enabled.
                proc.stdout.close()
                proc.stdout = None
                try:
                    _, err = proc.communicate(input=b'x', timeout=90)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                    self.fail('closed-pipe adapter did not finish')
                records = [json.loads(p.read_text()) for p in (self.repo / '.myagentkit/usage').glob('*.json')]
                usage = next(r for r in records if r['task']['id'] == label)
                self.assertEqual(usage['status'], 'completed' if expected == 0 else 'failed')
                self.assertTrue(Path(usage['evidence']).is_file())
                self.assertEqual(proc.returncode, expected, err.decode('utf-8', errors='replace'))
                self.assertNotIn(b'Exception ignored', err)

    def test_claude_direct_adapter_keeps_recorded_status_with_a_real_closed_pipe(self):
        self.assert_closed_pipe_keeps_adapter_status('claude')

    def test_codex_direct_adapter_keeps_recorded_status_with_a_real_closed_pipe(self):
        self.assert_closed_pipe_keeps_adapter_status('codex')

    def test_an_adapter_run_directly_keeps_its_handed_over_status_after_a_later_failure(self):
        # Run directly, the Claude adapter caught a failure after its result was recorded and
        # handed over (printing it), printed a "failed" line after the "completed" one and
        # exited 2; the Codex adapter raised it, and its caller printed FAIL and exited 5.
        # The handed-over status decides; the failure is a NOTE on stderr.
        from contextlib import nullcontext, redirect_stderr, redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import codex_bridge

        write_evidence = agent_usage.write_evidence

        def archive_failure(repo, path, *args, **kwargs):
            if Path(path).suffix == '.md':
                raise OSError('archive unavailable')
            return write_evidence(repo, path, *args, **kwargs)

        def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            if '-o' in command:
                Path(command[command.index('-o') + 1]).write_bytes(b'VERDICT: Accept\n')
                return {'exit_code': 1 if case == 'failed' else 0,
                        'stdout': 'quota exceeded' if case == 'failed' else json.dumps({'type': 'turn.completed', 'usage': {}}),
                        'stderr': '', 'termination': None, 'duration_ms': 1}
            value = {'type': 'result', 'subtype': 'success', 'is_error': False,
                     'modelUsage': {'claude-opus-5': {}}, 'structured_output':
                     {'verdict': 'Accept', 'findings': [], 'manual_checks': []}}
            if case == 'failed':
                value.update(is_error=True, api_error_status=429)
            return {'exit_code': 1 if case == 'failed' else 0, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        class Console(StringIO):
            def write(self, text):
                if '"evidence"' in text and not failed:
                    failed.append(text)
                    raise UnicodeEncodeError('cp1252', '→', 0, 1, 'character maps to <undefined>')
                return super().write(text)

        for case in ('completed', 'failed', 'evidence-not-written'):
            for name, main, prefix in (('claude', bridge.main, ['review']),
                                       ('codex', codex_bridge.main, ['--model', 'fixture-codex-model'])):
                failed, out, err, received = [], Console(), StringIO(), []
                archive = (patch('agent_usage.write_evidence', side_effect=archive_failure)
                           if case == 'evidence-not-written' else nullcontext())
                with self.subTest(adapter=name, case=case), patch.dict(os.environ, self.review_env()), \
                        patch('agent_process.run', side_effect=execution), archive, \
                        redirect_stdout(out), redirect_stderr(err):
                    code = main([*prefix, '--repo', str(self.repo), '--uncommitted'], received.append)
                    self.assertTrue(failed)
                    self.assertEqual(code, 0 if case == 'completed' else 5, out.getvalue() + err.getvalue())
                    if case == 'completed':
                        self.assertNotIn('"failed"', out.getvalue())
                        self.assertNotIn('FAIL', out.getvalue())
                    self.assertEqual(received[0]['status'], 'completed' if case == 'completed' else 'failed')
                    self.assertIn('cp1252', received[0]['error_after_result'])
                    self.assertIn('NOTE [review]: %s failed after it handed over its result' % name, err.getvalue())
                    if case == 'evidence-not-written':
                        self.assertIsNone(received[0]['evidence'])
                        self.assertIn('evidence was not written', err.getvalue())
                        self.assertNotIn('None', err.getvalue())
                    else:
                        self.assertIn(received[0]['evidence'], err.getvalue())
                        self.assertIn('its %s result is recorded in' % case, err.getvalue())

    def test_hidden_checkout_changes_reject_before_either_adapter_launches(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import codex_bridge
        import claude_bridge
        import review_dispatch
        self.commit_fixture('Reference review fixture')
        def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            if '-o' in command:
                Path(command[command.index('-o') + 1]).write_bytes(b'VERDICT: Accept\n')
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
        fake = python_cli(fake, PYTHON_SHEBANG + 'import json,os,pathlib,sys\n'
                        'sys.stdin.read()\n'
                        'pathlib.Path(sys.argv[sys.argv.index("-o")+1]).write_text(os.environ["FINAL_RESPONSE"])\n'
                        'print(json.dumps({"type":"turn.completed","usage":{}}))\n')
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
        fake = python_cli(fake, PYTHON_SHEBANG + 'import json,os,pathlib,sys\n'
                        'sys.stdin.read()\n'
                        'pathlib.Path(sys.argv[sys.argv.index("-o")+1]).write_text(os.environ["FINAL_RESPONSE"])\n'
                        'print(json.dumps({"type":"turn.completed","usage":{}}))\n')
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

    def run_bridge(self, case="accept", mode="review", extra=(), env_extra=None, repo=None):
        env = dict(os.environ, CLAUDE_CLI_BIN=str(self.fixture), FIXTURE_CASE=case,
                   MYAGENTKIT_DELEGATION_DEPTH="0")
        env.update(env_extra or {})
        result = subprocess.run([sys.executable, "-B", str(BRIDGE), mode, "--repo", str(repo or self.repo),
                                 *extra], env=env, capture_output=True, text=True)
        self.stderr = result.stderr
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
                self.assertIn("throwaway copy", record["sandbox"])
                # Native Windows has no Bash sandbox, so its reviewer reads only.
                self.assertIn("no Bash" if WINDOWS else "Read,Glob,Grep,Bash", record["sandbox"])
                self.assertEqual(len(record["diff_sha256"]), 64)
                self.assertEqual(verdicts_of(result["evidence"]), ["VERDICT: " + verdict])

    def test_private_storage_is_required_before_any_provider_launch(self):
        from unittest.mock import patch
        import codex_bridge
        import review_dispatch
        from contextlib import redirect_stdout
        from io import StringIO

        # tracked_backend_case: Windows and macOS fold case, so the store in another case is the
        # store; a case-sensitive pathspec once sent its credential to the reviewer.
        for case in ('missing_ignore', 'tracked_usage', 'tracked_review', 'unignored_review',
                     'unignored_backend', 'tracked_backend', 'tracked_backend_case'):
            with self.subTest(case=case):
                (self.repo / '.gitignore').write_bytes(IGNORE_RULES)
                if case == 'missing_ignore':
                    (self.repo / '.gitignore').write_text('')
                elif case == 'unignored_review':
                    with (self.repo / '.gitignore').open('a') as stream:
                        stream.write('\n!/docs/reviews/*-review.md\n')
                elif case == 'unignored_backend':
                    ignore = (self.repo / '.gitignore').read_text()
                    # Preserve LF bytes: a CRLF blank rule made this Windows fixture
                    # ignore the backend too, so it did not represent exposed storage.
                    (self.repo / '.gitignore').write_bytes(
                        ignore.replace('/.myagentkit/\n', '/.myagentkit/usage/\n')
                        .replace('/.[Mm][Yy][Aa][Gg][Ee][Nn][Tt][Kk][Ii][Tt]/\n', '/.myagentkit/usage/\n')
                        .replace('/.myagentkit/backends/\n', '').encode('utf-8'))
                else:
                    name = ('.myagentkit/usage/old.json' if case == 'tracked_usage' else
                            '.myagentkit/backends/glm.env' if case == 'tracked_backend' else
                            '.MYAGENTKIT/Backends/glm.env' if case == 'tracked_backend_case' else
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

    def test_a_review_whose_text_leaves_the_console_code_page_completes(self):
        # Redirected on native Windows, the dispatcher's stdout used the ANSI code page: a
        # completed review with an arrow in its text raised while printing, and was lost as
        # adapter_error. (setUp restores the environment.)
        os.environ.pop('PYTHONIOENCODING', None)
        os.environ.pop('PYTHONUTF8', None)
        fake = python_cli(self.root / 'codex-arrow', PYTHON_SHEBANG +
                          'import json, pathlib, sys\n'
                          'sys.stdin.read()\n'
                          'pathlib.Path(sys.argv[sys.argv.index("-o") + 1]).write_text('
                          '"## Findings\\n\\nLow: A \\u2192 B.\\n\\nVERDICT: Accept\\n", encoding="utf-8")\n'
                          'print(json.dumps({"type": "turn.completed", "usage": {}}))\n')
        result = self.run_wrapper('--reviewer', 'codex', REVIEW_CLI_BIN=str(fake),
                                  REVIEW_CODEX_MODEL='fixture-codex-model')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('adapter_error', result.stdout)

    def test_utf8_output_escapes_what_it_cannot_encode_and_skips_a_missing_stream(self):
        # A bare encoding reset the error handler to strict: a lone surrogate (a non-UTF-8 path)
        # then raised while printing, the same lost review. pythonw has no stdout at all.
        import io
        from unittest.mock import patch
        stderr = io.TextIOWrapper(io.BytesIO(), encoding='ascii', errors='backslashreplace')
        with patch.object(sys, 'stdout', None), patch.object(sys, 'stderr', stderr):
            bridge.utf8_output()
            print('A → B \udcff', file=stderr)
        stderr.flush()
        self.assertIn('A → B \\udcff'.encode(), stderr.buffer.getvalue())

    def test_malformed_codex_verdict_never_becomes_accept(self):
        fake = self.root / 'codex-conflict'
        fake = python_cli(fake, PYTHON_SHEBANG +
                        'import json, os, pathlib, sys\n'
                        'sys.stdin.read()\n'
                        'pathlib.Path(sys.argv[sys.argv.index("-o") + 1]).write_text(os.environ["FINAL_RESPONSE"])\n'
                        'print(json.dumps({"type": "turn.completed", "usage": {}}))\n')
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

    def test_codex_accept_reads_top_level_findings_in_every_form_the_prompt_allows(self):
        # The first Codex Accept check took every bullet at any indent as a finding (a clean
        # review's `- None.` and a nested continuation bullet failed a paid Accept) and read
        # only `- ` items under `## Findings` (a numbered or sub-heading High under `### Findings`
        # was accepted). Both parsers now read the forms usage_summary.py counts.
        fake = python_cli(self.root / 'codex-forms', PYTHON_SHEBANG +
                          'import json, os, pathlib, sys\n'
                          'sys.stdin.read()\n'
                          'pathlib.Path(sys.argv[sys.argv.index("-o") + 1]).write_text(os.environ["FINAL_RESPONSE"])\n'
                          'print(json.dumps({"type": "turn.completed", "usage": {}}))\n')
        completes = ('## Findings\n\n- None.\n\nVERDICT: Accept\n',
                     '## Findings\n\n- No findings\n\nVERDICT: Accept\n',
                     '## Findings\n\n- Low: x.py:1 a note.\n  - REASONED: the command.\n\nVERDICT: Accept\n',
                     '## Findings\n\n- **Low** x.py:1 bold severity.\n- Pre-existing: elsewhere.\n\nVERDICT: Accept\n',
                     '## Findings\n\n1. Low: x.py:1 numbered.\n\nVERDICT: Accept\n')
        completes += ('## Findings\n\n- None.\n\n### Manual checks\n\n- None.\n\n### Notes\n\n- Read only.\n\nVERDICT: Accept\n',)
        refused = ('## Findings\n\n1. High: x.py:1 numbered.\n\nVERDICT: Accept\n',
                   '### Findings\n\n### High: x.py:1 a sub-heading.\n\nVERDICT: Accept\n',
                   '**Findings**\n\n- High: x.py:1 under a bold heading.\n\nVERDICT: Accept\n',
                   '**Findings:**\n\n- High: x.py:1 colon inside the bold.\n\nVERDICT: Accept\n',
                   '# Findings\n\n- High: x.py:1 under a level-one heading.\n\nVERDICT: Accept\n',
                   'Findings:\n\n- High: x.py:1 under a plain heading.\n\nVERDICT: Accept\n',
                   '## Findings\n\n- **Medium** x.py:1 bold.\n\nVERDICT: Accept\n',
                   '## Findings\n\n* High: x.py:1 a star item.\n\nVERDICT: Accept\n')
        # Round 3: a heading in other markup ended the section before its finding, and a
        # paragraph finding (Codex's usual form) was no item, so each Accept completed.
        refused += ('## Findings\n\n### **High**\n\nx.py:1 a bold sub-heading.\n\nVERDICT: Accept\n',
                    '## Findings\n\n### *High*: x.py:1 an italic sub-heading.\n\nVERDICT: Accept\n',
                    '## Findings\n\n#### __Medium__ x.py:1 a deeper heading.\n\nVERDICT: Accept\n',
                    '## **Findings:**\n\n- High: x.py:1 a bold heading with a colon.\n\nVERDICT: Accept\n',
                    '## Findings\n\n**High — x.py:1.** A bold paragraph.\n\nVERDICT: Accept\n',
                    '## Findings\n\nHigh: x.py:1 a plain paragraph.\n\nVERDICT: Accept\n',
                    '## Findings\n\n- None.\n  - Medium: x.py:1 nested under a placeholder.\n\nVERDICT: Accept\n',
                    '## Findings\n\n- None.\n\n### Round 2 notes\n\n- High: x.py:1 under an unknown heading.\n\n'
                    'VERDICT: Accept\n',
                    # fix4 review: a placeholder counts only as a whole block, continuation joined.
                    '## Findings\n\nNo findings\nwere resolved: x.py:1 still drops records.\n\nVERDICT: Accept\n',
                    '## Findings\n\n- None.\n  x.py:1 still drops records.\n\nVERDICT: Accept\n')
        # fix4 notes: Codex's real clean-review prose completes; a Reject must name a finding,
        # as claude_bridge.validate() requires ("Reject has no findings").
        completes += ('## Findings\n\nNo findings established in this diff.\n\nVERDICT: Accept\n',
                      '## Findings\n\nNo qualifying defects found.\n\nVERDICT: Accept\n')
        refused += ('## Findings\n\n- None.\n\nVERDICT: Reject\n',
                    '## Findings\n\nNo qualifying defects found.\n\nVERDICT: Reject\n',
                    '## Findings\n\n- Low-level: High defect in x.py:1.\n\nVERDICT: Accept\n')
        completes += ('## Findings\n\nNone.\n\n## Verdict\n\nVERDICT: Accept\n',
                      '## **Findings**\n\n**Low** — x.py:1 a bold paragraph.\n\nVERDICT: Accept\n',
                      '## Findings\n\nLow: x.py:1 a note that\nwraps onto a second line.\n\nVERDICT: Accept\n')
        import codex_bridge
        for final, completed in [(f, True) for f in completes] + [(f, False) for f in refused]:
            with self.subTest(final=final):
                self.assertEqual(codex_bridge.verdict_refused(final), not completed)
        # The whole wrapper once each way: the rule decides its exit and chain record. A
        # contradicted Accept now completes as the stricter verdict (#120), so the refused run
        # is a Reject that names no finding.
        for final, completed in ((completes[0], True), (next(f for f in refused if 'VERDICT: Reject' in f), False)):
            with self.subTest(final=final):
                result = self.run_wrapper('--reviewer', 'codex', REVIEW_CLI_BIN=str(fake),
                                          REVIEW_CODEX_MODEL='fixture-codex-model', FINAL_RESPONSE=final)
                chain = json.loads(next(s.removeprefix('review dispatch: ') for s in
                                        result.stdout.splitlines() if s.startswith('review dispatch: ')))
                self.assertEqual(result.returncode == 0, completed, result.stdout + result.stderr)
                self.assertEqual(chain['failure_kind'], None if completed else 'invalid_evidence')

    def test_codex_accept_with_a_manual_check_is_read_as_on_the_claude_side(self):
        # Round 3: the manual checks were read only for the other verdict, so an Accept that
        # kept a check passed as a plain Accept. Since #120 (owner decision 59 A) both adapters
        # read it as Accept with Manual Checks, the first check naming the correction, and a
        # High among the checks as Reject (rsel); claude_bridge.validate() reads it the same.
        fake = python_cli(self.root / 'codex-accept-manual', PYTHON_SHEBANG +
                          'import json, os, pathlib, sys\n'
                          'sys.stdin.read()\n'
                          'pathlib.Path(sys.argv[sys.argv.index("-o") + 1]).write_text(os.environ["FINAL_RESPONSE"])\n'
                          'print(json.dumps({"type": "turn.completed", "usage": {}}))\n')
        for final, verdict in (
                ('## Findings\n\n- None.\n\n## Manual checks\n\n- Verify deployment before release.\n\n'
                 'VERDICT: Accept\n', 'Accept with Manual Checks'),
                ('## Findings\n\n- None.\n\n**Manual checks:**\n\nVerify deployment before release.\n\n'
                 'VERDICT: Accept\n', 'Accept with Manual Checks'),
                # fix4 review: a check written as a heading is still a check.
                ('## Findings\n\n- None.\n\n## Manual checks\n\n### Verify deployment before release.\n\n'
                 'VERDICT: Accept\n', 'Accept with Manual Checks'),
                # rvfix: the paid review put a NOT RUN paragraph after a clean placeholder.
                ('VERDICT: Accept\n\n## Findings\n\n- None.\n\n## Manual checks\n\nNone.\n\n'
                 '`tests/test_python_fallback.py`: both tests passed. The blocking assertion proves '
                 'the Python fallback reaches `plain_report`; the copied grammar matches the installed project layout.\n\n'
                 'NOT RUN: Git comparison; this archive has no Git metadata. '
                 'Reviewed the supplied diff against checkout files.\n', 'Accept with Manual Checks'),
                ('VERDICT: Accept\n\n## Findings\n\n- None.\n\n## Manual checks\n\nNone.\n\n'
                 'I could not verify the Git comparison because this archive has no Git metadata.\n', 'Accept with Manual Checks'),
                ('VERDICT: Accept with Manual Checks\n\n## Findings\n\n- None.\n\n## Manual checks\n\n'
                 'NOT RUN: Git comparison; this archive has no Git metadata.\n', 'Accept with Manual Checks'),
                ('VERDICT: Accept with Manual Checks\n\n## Findings\n\n- None.\n\n## Manual checks\n\n'
                 'I could not verify the Git comparison because this archive has no Git metadata.\n', 'Accept with Manual Checks'),
                ('VERDICT: Accept\n\n## Findings\n\n- None.\n\n## Manual checks\n\nNone.\n', 'Accept'),
                ('## Findings\n\n- None.\n\n## Manual checks\n\n- None.\n\nVERDICT: Accept\n', 'Accept'),
                ('## Findings\n\n- None.\n\n## Manual checks\n\n- High: x.py:1 drops records.\n\nVERDICT: Accept\n',
                 'Reject')):
            with self.subTest(final=final):
                result = self.run_wrapper('--reviewer', 'codex', REVIEW_CLI_BIN=str(fake),
                                          REVIEW_CODEX_MODEL='fixture-codex-model', FINAL_RESPONSE=final)
                chain = json.loads(next(s.removeprefix('review dispatch: ') for s in
                                        result.stdout.splitlines() if s.startswith('review dispatch: ')))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(chain['failure_kind'], None)
                self.assertEqual(verdicts_of(chain['attempts'][0]['evidence']), ['VERDICT: ' + verdict])

    def test_default_effort_follows_the_tier_and_xhigh_is_no_review_choice(self):
        # review.sh computed the tier default alone: the plugin's direct dispatcher command and
        # both adapters ran every review at high. The default now lives in claude_bridge.
        fake = python_cli(self.root / 'codex-effort', PYTHON_SHEBANG +
                          'import json, pathlib, sys\n'
                          'sys.stdin.read()\n'
                          'pathlib.Path(sys.argv[sys.argv.index("-o") + 1]).write_text("VERDICT: Accept\\n")\n'
                          'print(json.dumps({"type": "turn.completed", "usage": {}}))\n')
        env = dict(REVIEW_CLI_BIN=str(fake), REVIEW_CODEX_MODEL='fixture-codex-model')
        for extra, effort in (({}, 'medium'), ({'REVIEW_RISK': 'low'}, 'medium'),
                              ({'REVIEW_RISK': 'high'}, 'high'), ({'REVIEW_RISK': 'high', 'REVIEW_EFFORT': 'low'}, 'low')):
            with self.subTest(extra=extra):
                result = self.run_wrapper('--reviewer', 'codex', **env, **extra)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('REVIEW [about to run]: codex model fixture-codex-model, effort ' + effort, result.stdout)
                self.assertEqual(header_of(json.loads(next(
                    s.removeprefix('review dispatch: ') for s in result.stdout.splitlines()
                    if s.startswith('review dispatch: ')))['attempts'][0]['evidence'])['effort'], effort)
        for effort in ('xhigh', 'max'):
            with self.subTest(effort=effort):
                result = self.run_wrapper('--reviewer', 'codex', REVIEW_EFFORT=effort, **env)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('invalid choice', result.stderr)
                self.assertNotIn('review dispatch: ', result.stdout)
        for script in (BRIDGE, ROOT / 'codex_bridge.py'):
            with self.subTest(script=script.name):
                result = subprocess.run([sys.executable, '-B', str(script), *(['review'] if script is BRIDGE else []),
                                         '--repo', str(self.repo), '--effort', 'xhigh', '--uncommitted'],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('invalid choice', result.stderr)

    def test_transcript_accept_cannot_replace_a_missing_final_response(self):
        fake = self.root / 'codex-transcript'
        fake = python_cli(fake, PYTHON_SHEBANG +
                        'import json, sys\n'
                        'sys.stdin.read()\n'
                        'print(json.dumps({"type": "item.completed", "item": '
                        '{"type": "agent_message", "text": "VERDICT: Accept"}}))\n'
                        'print(json.dumps({"type": "turn.completed", "usage": {}}))\n')
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
                 "conflict": "has no findings", "turns": "incomplete", "model": "modelUsage",
                 "error": "successful result", "exit": "exited 9", "mutation": "changed during"}
        for case, reason in cases.items():
            with self.subTest(case=case):
                code, result = self.run_bridge(case)
                self.assertEqual(code, 5, result)
                self.assertIn(reason, result["error"])
                self.assertEqual(header_of(result["evidence"])["status"], "failed")
                # A failed run that still printed a verdict would read as an approval.
                self.assertEqual(verdicts_of(result["evidence"]), [])

    def test_an_api_error_status_on_the_final_result_fails_the_review(self):
        # An exit-0 success envelope with a valid Accept and api_error_status 429 was recorded
        # completed AND quota, and the dispatcher took it as a finished review. The CLI copies
        # that status from the message that ended the turn, never from an error it retried
        # through, so its presence is a failure, whatever the text holds. "error" is is_error
        # with a valid verdict; "accept" is the clean completion.
        for case, kind in (('api_429', 'rate_limited'), ('api_401', 'invalid_evidence'),
                           ('api_500', 'invalid_evidence'), ('api_529', 'rate_limited'),
                           ('error', 'cli_error'), ('accept', None)):
            with self.subTest(case=case):
                code, result = self.run_bridge(case)
                self.assertEqual((code, result['status'], result['failure_kind']),
                                 (0, 'completed', None) if kind is None else (5, 'failed', kind))
                self.assertEqual(header_of(result['evidence'])['status'], result['status'])
                self.assertEqual(verdicts_of(result['evidence']), [] if kind else ['VERDICT: Accept'])
                usage = json.loads(Path(result['usage_record']).read_text())
                self.assertEqual((usage['status'], usage['failure_kind']), (result['status'], kind))
                if case.startswith('api_'):
                    self.assertIn('"api_error_status": ' + case[4:], usage['raw_stdout'])

    def test_a_record_is_completed_exactly_when_it_names_no_failure(self):
        # Every outcome either fake CLI can produce, each in its own fresh copy of the repository
        # and configured for the outcome it is named for. Sharing one repository, several cases
        # fell into a fixture failure and passed as cli_error without reaching their own path.
        claude = {'accept': None, 'reject': None, 'manual': None, 'no_budget': None,
                  'explicit_budget': None, 'kit_docs': None, 'proposal': None, 'questions': None,
                  'api_429': 'rate_limited', 'api_500': 'invalid_evidence', 'quota': 'quota_exhausted',
                  'archive_failure': 'evidence_write_failed', 'auth': 'authentication',
                  'context': 'context_limit', 'conflict': 'invalid_evidence', 'error': 'cli_error',
                  'exit': 'cli_error', 'malformed_envelope': 'invalid_evidence',
                  'missing': 'invalid_evidence', 'model': 'invalid_evidence',
                  'transcript': 'invalid_evidence', 'mutation': 'stale_checkout',
                  'behaviour_mutation': 'stale_checkout',
                  'partial_timeout': 'timeout', 'timeout': 'timeout',
                  'turns': 'budget_or_turn_limit', 'unknown_flag': 'cli_unsupported'}
        codex = {'accept': None, 'reject': None, 'mcp': None, 'mcp_reconnect': None,
                 'quota': 'quota_exhausted', 'mcp_quota': 'quota_exhausted', 'mcp_exit': 'cli_error',
                 'mcp_no_completion': 'cli_error', 'mcp_no_verdict': 'invalid_evidence',
                 'mcp_429_no_verdict': 'invalid_evidence',
                 'mcp_two_verdicts': 'invalid_evidence', 'mcp_failed_turn': 'cli_error',
                 'unknown_flag': 'cli_unsupported'}
        # Only the dispatcher writes the chain and fails a quota on a changed checkout: the
        # attempt's own record, then what the chain says (None: no chain was written).
        dispatched = {'chain_failure': ('rate_limited', None), 'quota_mutation': ('rate_limited', 'stale_checkout')}
        self.assertLessEqual(set(re.findall(r"case == '(\w+)'", FIXTURE)), set(claude) | set(dispatched))
        self.assertLessEqual(set(re.findall(r"case == '(\w+)'", fixture_source(self.build_fake_codex()))),
                             set(codex))
        task = self.root / 'handoff.md'
        task.write_text('Propose a fix and stop on ambiguity.\n')
        # A 2 s bound only where the outcome is the timeout (its fixture sleeps 20 s). Every case
        # got 2 s once, and on a loaded host the copy and the fake CLI's start outlasted it: an
        # accept or a cli_error ended as 'timeout' (seen at 10 units at once, #95).
        env = dict(os.environ, MYAGENTKIT_DELEGATION_DEPTH='0', MYAGENTKIT_CAPTURE_QUOTA='0',
                   REVIEW_TIMEOUT_SECONDS='120', REVIEW_CLI_BIN=str(self.build_fake_codex()),
                   REVIEW_DOCS='AGENTS.md, docs/ARCHITECTURE.md and docs/REVIEW_GATE.md')
        pristine = self.repo
        runs = [('claude', case, kind) for case, kind in claude.items()]
        runs += [('codex', case, kind) for case, kind in codex.items()]
        runs += [('dispatch', case, kinds) for case, kinds in dispatched.items()]
        for adapter, case, kind in runs:
            with self.subTest(adapter=adapter, case=case):
                self.repo = repo = self.root / 'repos' / (adapter + '-' + case)
                shutil.copytree(pristine, repo, symlinks=True)
                if adapter == 'dispatch':
                    run, chain = self.dispatch_result(FIXTURE_CASE=case, FIXTURE_REPO=str(repo))
                    records = list(repo.glob('.myagentkit/usage/*.json'))
                    self.assertEqual(len(records), 1, run.stdout + run.stderr)
                    usage = json.loads(records[0].read_text())
                    self.assertEqual(usage['status'] == 'completed', usage['failure_kind'] is None, usage)
                    self.assertEqual((usage['status'], usage['failure_kind'], chain and chain['failure_kind']),
                                     ('failed',) + kind, run.stdout + run.stderr)
                    continue
                if adapter == 'codex':
                    command = [sys.executable, '-B', str(ROOT / 'codex_bridge.py'), '--repo', str(repo),
                               '--model', 'fixture-codex-model', '--uncommitted']
                    extra = {'CODEX_FIXTURE_CASE': case}
                else:
                    mode = 'propose' if case in ('proposal', 'questions') else 'review'
                    command = [sys.executable, '-B', str(BRIDGE), mode, '--repo', str(repo),
                               '--timeout', '2' if kind == 'timeout' else '120',
                               *(['--task-file', str(task)] if mode == 'propose' else []),
                               *(['--max-budget-usd', '7.5'] if case == 'explicit_budget' else [])]
                    extra = {'CLAUDE_CLI_BIN': str(self.fixture), 'FIXTURE_CASE': case}
                if case == 'kit_docs':  # the kit's own layout, whose guidance the prompt must name
                    (repo / 'AGENTS.md').unlink()
                    (repo / 'core/docs').mkdir(parents=True)
                    for name in ('CONTRIBUTING.md', 'core/AGENTS.md', 'core/docs/REVIEW_GATE.md',
                                 'core/docs/ARCHITECTURE.md'):
                        (repo / name).write_text('Synthetic kit guidance.\n')
                run = subprocess.run(command, env=dict(env, FIXTURE_REPO=str(repo), **extra),
                                     capture_output=True, text=True)
                lines = [line.removeprefix('review invocation: ') for line in run.stdout.splitlines()
                         if line.startswith(('{', 'review invocation: {'))]
                result = json.loads(lines[-1])
                self.assertEqual(result['status'] == 'completed', result['failure_kind'] is None, result)
                self.assertEqual((result['status'], result['failure_kind']),
                                 ('completed' if kind is None else 'failed', kind), result)
                self.assertEqual(run.returncode == 0, result['status'] == 'completed', result)
                if result.get('usage_record'):
                    usage = json.loads(Path(result['usage_record']).read_text())
                    self.assertEqual((usage['status'], usage['failure_kind']),
                                     (result['status'], result['failure_kind']))

    def test_a_plain_accept_may_carry_lows_and_pre_existing_items_only(self):
        # Owner decision 2026-10-13 (E): a Low or an item outside the diff does not block Accept;
        # anything Medium or above still contradicts it (the same rule in codex_bridge).
        # A bold or dash-prefixed severity is the same item (the Codex parser read it so, the
        # Claude parser refused it: a paid Accept lost to Markdown); a placeholder is no finding.
        for findings, allowed in (([], True), (['Low: a note'], True), (['Pre-existing: elsewhere'], True),
                                  (['Low: a', 'Pre-existing: b'], True), (['Medium: a defect'], False),
                                  (['Lowly: not a severity'], False), (['High: wrong'], False),
                                  (['**Low** a.py:1 bold'], True), (['- Low: a dash item'], True),
                                  (['- **Low**: both'], True), (['None.'], True), (['- No findings'], True),
                                  (['**High** a.py:1 bold'], False), (['- Medium: a dash item'], False),
                                  (['Nonexistent file: a defect'], False),
                                  # REVIEW_PROMPT asks for "plus N similar" past five Lows.
                                  (['Low: a', 'Plus 3 similar Low findings.'], True), (['- Plus 3 similar.'], True),
                                  (['No qualifying findings.'], True), (['High: a', 'Plus 2 similar'], False),
                                  (['Plus 3 similar, and High: y is broken'], False),
                                  # fix4 notes: "Low-level" is no severity, an empty Pre-existing
                                  # is no item, and real Codex prose for a clean review is.
                                  (['Low-level: High defect in x.py:1'], False), (['Pre-existing:'], False),
                                  (['No findings established in this diff.'], True),
                                  (['No qualifying defects found.'], True),
                                  (['No defects were found in the diff.'], True),
                                  (['No findings established, but x.py:1 drops records.'], False)):
            with self.subTest(findings=findings):
                value = {'verdict': 'Accept', 'findings': findings, 'manual_checks': []}
                envelope = {'type': 'result', 'subtype': 'success', 'is_error': False,
                            'modelUsage': {'claude-opus-5': {}}, 'structured_output': value}
                if allowed:
                    self.assertEqual(bridge.validate(envelope, 'review', 'claude-opus-5'), value)
                else:
                    # #120: read as the stricter verdict, not refused.
                    self.assertNotEqual(bridge.validate(envelope, 'review', 'claude-opus-5')['verdict'], 'Accept')

    def test_a_contradicted_accept_is_read_as_the_stricter_verdict(self):
        # #120, owner decision 59 A: refused, a whole paid review was lost to its own lists. A
        # blocking item naming Critical or High makes it Reject; any other item or check makes it
        # Accept with Manual Checks, the item kept as a check; the first check names the correction.
        import codex_bridge
        note = 'The reviewer wrote Accept; the bridge read it as %s'
        for findings, checks, verdict, moved in (
                (['High: x.py:1 drops records.'], [], 'Reject', []),
                (['**Critical** x.py:1 bypasses the gate.', 'Low: a note'], [], 'Reject', []),
                (['Medium: x.py:1 a defect.'], [], 'Accept with Manual Checks', ['Medium: x.py:1 a defect.']),
                ([], ['NOT RUN: the Windows suite.'], 'Accept with Manual Checks', ['NOT RUN: the Windows suite.']),
                (['Low: a note', 'NOT RUN: the deployment.'], [], 'Accept with Manual Checks',
                 ['NOT RUN: the deployment.']),
                # rsel: the leading severity decides, never the word high or critical in the text.
                (['Medium: x.py:1 the high-effort timeout is not applied.'], [], 'Accept with Manual Checks',
                 ['Medium: x.py:1 the high-effort timeout is not applied.']),
                (['NOT RUN: the high-tier focus run.'], [], 'Accept with Manual Checks',
                 ['NOT RUN: the high-tier focus run.']),
                (['Pre-existing (Critical): x.py:1 an old bypass.'], [], 'Accept with Manual Checks',
                 ['Pre-existing (Critical): x.py:1 an old bypass.']),
                (['High-level: x.py:1 a note.'], [], 'Accept with Manual Checks', ['High-level: x.py:1 a note.']),
                # rsel3: the forms finding_start() reads as findings lead with their severity too; a
                # check whose first word only looks like one (no separator follows) is no finding.
                (['Issue 1: High — x.py:1 drops records.'], [], 'Reject', []),
                (['### Issue 3: High — x.py:1 drops records.'], [], 'Reject', []),
                (['[High] x.py:1 drops records.'], [], 'Reject', []),
                (['**[High]** x.py:1 drops records.'], [], 'Reject', []),
                (['Severity: High — x.py:1 drops records.'], [], 'Reject', []),
                ([], ['High availability: confirm failover on staging.'], 'Accept with Manual Checks',
                 ['High availability: confirm failover on staging.']),
                ([], ['Critical path: time the deploy.'], 'Accept with Manual Checks',
                 ['Critical path: time the deploy.']),
                # rsel4: REVIEW_PROMPT asks for the severity, then the file and line; a `(` or a
                # path/location token after the severity makes it a finding, a plain word does not.
                (['High x.py:1 drops records.'], [], 'Reject', []),
                (['High (x.py:1): drops records.'], [], 'Reject', []),
                (['Critical (data loss) x.py:1 bypasses the gate.'], [], 'Reject', []),
                (['High core/x drops records.'], [], 'Reject', []),
                (['High C:\\x drops records.'], [], 'Reject', []),
                (['High line:12 drops records.'], [], 'Reject', []),
                # fullrev-review M: a comma or one word before the path, or `High severity:`.
                (['High, x.py:12 drops records.'], [], 'Reject', []),
                (['High in x.py:12 drops records.'], [], 'Reject', []),
                (['High severity: x.py:12 drops records.'], [], 'Reject', []),
                ([], ['High availability of the api: confirm failover.'], 'Accept with Manual Checks',
                 ['High availability of the api: confirm failover.']),
                ([], ['High availability confirm failover on staging.'], 'Accept with Manual Checks',
                 ['High availability confirm failover on staging.'])):
            value = {'verdict': 'Accept', 'findings': findings, 'manual_checks': checks}
            envelope = {'type': 'result', 'subtype': 'success', 'is_error': False,
                        'modelUsage': {'claude-opus-5': {}}, 'structured_output': value}
            with self.subTest(findings=findings, checks=checks):
                result = bridge.validate(envelope, 'review', 'claude-opus-5')
                self.assertEqual(result['verdict'], verdict)
                self.assertEqual(result['findings'], findings)
                self.assertTrue(result['manual_checks'][0].startswith(note % verdict), result)
                self.assertEqual(result['manual_checks'][1:], moved)
                final = codex_bridge.corrected('## Findings\n\n' + ''.join('- %s\n' % f for f in findings or ['None.'])
                                               + '\n## Manual checks\n\n' + ''.join('- %s\n' % c for c in checks or ['None.'])
                                               + '\nVERDICT: Accept\n')
                self.assertEqual(re.findall(codex_bridge.VERDICT, final, re.M), [verdict])
                self.assertIn('- ' + note % verdict, final)
                self.assertFalse(codex_bridge.verdict_refused(final), final)
        # The Codex text form with no manual checks section (rsel4).
        final = codex_bridge.corrected('## Findings\n\n- High x.py:1 drops records.\n\nVERDICT: Accept')
        self.assertEqual(re.findall(codex_bridge.VERDICT, final, re.M), ['Reject'])
        # A Reject that names no finding stays refused: there is no stricter reading of it.
        envelope['structured_output'] = {'verdict': 'Reject', 'findings': ['None.'], 'manual_checks': []}
        with self.assertRaisesRegex(bridge.BridgeError, 'Reject has no findings'):
            bridge.validate(envelope, 'review', 'claude-opus-5')
        self.assertTrue(codex_bridge.verdict_refused(codex_bridge.corrected('## Findings\n\nNone.\n\nVERDICT: Reject\n')))

    def test_the_pin_is_attested_by_its_exact_id_or_a_dated_one_only(self):
        # Matched as a prefix, the usage key claude-opus-5-5, another model, attested the pin
        # claude-opus-5. Only the pinned id itself, or it with a -YYYYMMDD date, attests it.
        value = {'verdict': 'Accept', 'findings': [], 'manual_checks': []}
        for key, attested in (('claude-opus-5', True), ('claude-opus-5-20261001', True),
                              ('claude-opus-5-5', False), ('claude-opus-5-5-20261001', False),
                              ('claude-opus-5-2026100', False), ('claude-opus-5-20261001x', False)):
            with self.subTest(key=key):
                envelope = {'type': 'result', 'subtype': 'success', 'is_error': False,
                            'modelUsage': {key: {}}, 'structured_output': value}
                if attested:
                    self.assertEqual(bridge.validate(envelope, 'review', 'claude-opus-5'), value)
                else:
                    with self.assertRaisesRegex(bridge.BridgeError, 'modelUsage'):
                        bridge.validate(envelope, 'review', 'claude-opus-5')

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
        # KARARLAR D07 inv3#103: every moving alias of the Claude CLI's --model is refused.
        for alias in ("opus", "sonnet", "haiku", "opusplan", "default", "best"):
            with self.subTest(alias=alias):
                code, result = self.run_bridge(extra=["--model", alias])
                self.assertEqual(code, 2)
                self.assertIn("explicit", result["error"])
        import review_dispatch
        self.assertFalse(review_dispatch.pin_valid("claude", "sonnet"))
        self.assertTrue(review_dispatch.pin_valid("claude", "claude-sonnet-5"))

    def test_an_empty_diff_is_empty_output_and_a_binary_or_mode_change_is_not(self):
        # KARARLAR D04 inv2#85: "empty" means the diff text is empty; a change git shows only as
        # a binary patch or a mode line still reaches the reviewer.
        (self.repo / "file.py").write_text("original\n")
        self.assertEqual(bridge.snapshot(self.repo, "uncommitted", None)[2].strip(), "")
        (self.repo / "data.bin").write_bytes(b"\x00\x01binary\x00")
        self.git("add", "data.bin")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "commit", "-qm", "binary")
        (self.repo / "data.bin").write_bytes(b"\x00\x02binary changed\x00")
        self.assertIn("data.bin", bridge.snapshot(self.repo, "uncommitted", None)[2])
        self.git("checkout", "--", "data.bin")
        self.git("update-index", "--chmod=+x", "file.py")
        # The snapshot diffs the working file against HEAD: with core.fileMode=true (ext4, APFS)
        # the file itself needs the bit, or the index-only change shows nowhere (issue #92).
        os.chmod(self.repo / "file.py", 0o755)
        diff = bridge.snapshot(self.repo, "uncommitted", None)[2]
        self.assertIn("new mode 100755", diff)

    def test_a_shard_report_survives_a_console_that_cannot_encode_it(self):
        console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        keep_output_writable(console)
        console.write("shard output \N{REPLACEMENT CHARACTER} and \N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}\n")  # raised UnicodeEncodeError before the fix
        console.flush()

    def test_fixtures_never_copy_the_projects_ignore_file(self):
        # A project that ignores .env hid the planted secret files of the fixtures (issue #91).
        source = Path(__file__).read_text(encoding="utf-8")
        self.assertNotIn("ROOT.parent / " + "'.gitignore'", source.split("def test_fixtures_never_copy", 1)[0])

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
        diff = bridge.snapshot(self.repo, "uncommitted", None)[2]
        self.assertIn("new file.txt", diff)

    def test_a_past_commit_on_a_dirty_tree_is_reviewed_from_its_archive(self):
        # #114 (lead decision 3): --commit names a commit that is not HEAD, on a dirty tree; the
        # reviewer gets that commit's archive and diff, and the fingerprint is the commit's.
        self.commit_fixture('Commit A')
        past = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        (self.repo / 'file.py').write_text('later\n')
        self.commit_fixture('Commit B')
        (self.repo / 'file.py').write_text('dirty\n')
        cwd_log, prompt_log = self.root / 'cwd.json', self.root / 'prompt.txt'
        code, result = self.run_bridge(extra=['--commit', past],
                                       env_extra={'CWD_LOG': str(cwd_log), 'PROMPT_LOG': str(prompt_log)})
        self.assertEqual(code, 0, result)
        self.assertEqual(json.loads(cwd_log.read_text())['file'], 'changed\n')
        diff = prompt_log.read_text(encoding='utf-8').partition('\nDiff:\n')[2]
        self.assertIn('+changed', diff)
        self.assertNotIn('later', diff)
        self.assertNotIn('dirty', diff)
        # The fingerprint is the commit's: a later edit of the tree does not change it.
        first = bridge.snapshot(self.repo, 'commit', past, past_ok=True)
        (self.repo / 'file.py').write_text('dirtier\n')
        self.assertEqual(bridge.snapshot(self.repo, 'commit', past, past_ok=True)[1], first[1])
        with self.assertRaises(bridge.BridgeError):
            bridge.snapshot(self.repo, 'commit', past)

    KIT_SECTION = ("## Kit-verified files (equal to the kit's file after git's line-ending normalisation, "
                   "hash-object --path; not reviewed)")

    def kit_git(self, kit, *args, stdin=None):
        return subprocess.run(['git', '-C', str(kit), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                               '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', *args],
                              check=True, capture_output=True, input=stdin).stdout.decode().strip()

    def kit_upgrade(self, edit='', crlf=False, record=True, tag=True, executable=False, nest=False):
        """#114: a kit clone with core/x.sh (KIT-OWNED) and core/plain.txt (no marker), its commit
        on tag v1 (`tag`), and a project commit that copies both (x.sh plus `edit`), records the
        kit commit (or `record`) and changes file.py. `nest`: the kit is a folder of a repository."""
        kit = self.root / 'kit'
        kit.mkdir()
        self.kit_git(kit, 'init', '-q')
        self.kit_git(kit, 'config', 'core.autocrlf', 'true' if crlf else 'false')
        if nest:
            kit = kit / 'sub'
        (kit / 'core').mkdir(parents=True)
        source = '# KIT-OWNED: do not edit locally\necho kit\n'
        (kit / 'core/x.sh').write_bytes(source.encode())
        (kit / 'core/plain.txt').write_bytes(b'plain\n')
        self.kit_git(kit, 'add', '.')
        if executable:
            self.kit_git(kit, 'update-index', '--chmod=+x', 'core/x.sh')
        self.kit_git(kit, 'commit', '-qm', 'kit')
        if tag:
            self.kit_git(kit, 'tag', 'v1.0.0')
        kit_commit = self.kit_git(kit, 'rev-parse', 'HEAD')
        data = source + edit
        (self.repo / 'x.sh').write_bytes((data.replace('\n', '\r\n') if crlf else data).encode())
        (self.repo / 'plain.txt').write_bytes(b'plain\n')
        if record:
            (self.repo / 'docs/kit').mkdir(parents=True)
            (self.repo / 'docs/kit/.kit-commit').write_text((kit_commit if record is True else record) + '\n')
        if executable:
            os.chmod(self.repo / 'x.sh', 0o755)
            self.git('add', 'x.sh')
            self.git('update-index', '--chmod=+x', 'x.sh')
        # A --commit HEAD review needs a clean tree: the wrapper run_wrapper installs is ignored.
        with (self.repo / '.git/info/exclude').open('a') as exclude:
            exclude.write('/scripts/\n')
        self.commit_fixture('Kit upgrade')
        return kit, kit_commit

    def test_a_kit_upgrade_commit_reviews_only_the_project_files(self):
        # #114 (lead decisions 1, 2): a kit-owned file equal to the kit's blob leaves the diff and
        # is named as verified by hash in the prompt, the evidence and the chain record.
        kit, kit_commit = self.kit_upgrade()
        blob = self.git('rev-parse', 'HEAD:x.sh').stdout.decode().strip()
        log = self.root / 'prompt.txt'
        code, result = self.run_bridge(extra=['--commit', 'HEAD', '--kit-verified', str(kit)],
                                       env_extra={'PROMPT_LOG': str(log)})
        self.assertEqual(code, 0, result)
        prompt = log.read_text(encoding='utf-8')
        diff = prompt.partition('\nDiff:\n')[2]
        self.assertIn('+changed', diff)
        self.assertNotIn('x.sh', diff)
        # Equal to a kit file but without the KIT-OWNED header: reviewed.
        self.assertIn('+plain', diff)
        self.assertIn('Verified by hash, not reviewed: these changed paths are equal to the kit\'s file after '
                      'git\'s line-ending normalisation (hash-object --path) at kit commit %s' % kit_commit, prompt)
        self.assertIn('\n  x.sh (blob %s)\n' % blob, prompt)
        self.assertIn(self.KIT_SECTION + '\n\n- x.sh, blob %s, kit commit %s\n'
                      % (blob, kit_commit), Path(result['evidence']).read_text(encoding='utf-8'))
        result, chain = self.dispatch_result(fallback=False, args=('--commit', 'HEAD', '--kit-verified', '--kit', str(kit)))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(chain['kit_verified'], [{'path': 'x.sh', 'blob': blob, 'kit_commit': kit_commit}])
        self.assertIn('- x.sh, blob %s' % blob, Path(chain['attempts'][0]['evidence']).read_text(encoding='utf-8'))
        # The list is bound to the commit's blobs.
        with self.assertRaises(bridge.BridgeError) as caught:
            bridge.snapshot(self.repo, 'commit', 'HEAD', True, [dict(chain['kit_verified'][0], blob='0' * 40)])
        self.assertIn('the kit-verified files are not the blobs of commit', str(caught.exception))

    def test_a_kit_owned_file_the_project_edited_stays_in_the_diff(self):
        kit, _ = self.kit_upgrade(edit='echo local\n')
        log = self.root / 'prompt.txt'
        code, result = self.run_bridge(extra=['--commit', 'HEAD', '--kit-verified', str(kit)],
                                       env_extra={'PROMPT_LOG': str(log)})
        self.assertEqual(code, 0, result)
        prompt = log.read_text(encoding='utf-8')
        self.assertIn('+echo local', prompt.partition('\nDiff:\n')[2])
        self.assertNotIn('Verified by hash', prompt)
        self.assertIn(self.KIT_SECTION + '\n\nNone.\n',
                      Path(result['evidence']).read_text(encoding='utf-8'))

    def test_an_unknown_or_missing_kit_commit_verifies_nothing(self):
        from contextlib import redirect_stderr
        kit, _ = self.kit_upgrade(record='1' * 40)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(bridge.kit_verified(self.repo, 'HEAD', kit), [])
        self.assertIn('NOTE [review]: --kit-verified verified no file: the kit clone %s lacks kit commit %s'
                      % (kit, '1' * 40), err.getvalue())
        self.git('rm', '-q', 'docs/kit/.kit-commit')
        self.commit_fixture('No kit commit')
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(bridge.kit_verified(self.repo, 'HEAD', kit), [])
        self.assertIn('records no kit commit in docs/kit/.kit-commit; every changed file is reviewed', err.getvalue())

    def test_a_crlf_checkout_of_a_kit_file_verifies(self):
        # sync-kit.sh's hash-object --path rule: the kit clone's line-ending settings normalise it.
        kit, kit_commit = self.kit_upgrade(crlf=True)
        blob = self.git('rev-parse', 'HEAD:x.sh').stdout.decode().strip()
        self.assertIn(b'\r\n', self.git('cat-file', 'blob', blob).stdout)
        self.assertEqual(bridge.kit_verified(self.repo, 'HEAD', kit),
                         [{'path': 'x.sh', 'blob': blob, 'kit_commit': kit_commit}])

    def test_line_ending_churn_of_a_kit_verified_file_is_still_refused(self):
        # kitv4 item 4: x.sh verifies through the kit clone's normalisation, but the commit turns
        # its LF into CRLF; the churn check reads every changed file, not the trimmed diff.
        kit, _ = self.kit_upgrade(crlf=True)
        for data, edit in ((b'# KIT-OWNED: do not edit locally\necho kit\n', 'lf\n'),
                           (b'# KIT-OWNED: do not edit locally\r\necho kit\r\n', 'crlf\n')):
            (self.repo / 'x.sh').write_bytes(data)
            (self.repo / 'file.py').write_text(edit)
            self.commit_fixture('Line endings')
        self.assertEqual([entry['path'] for entry in bridge.kit_verified(self.repo, 'HEAD', kit)], ['x.sh'])
        result, _ = self.dispatch_result(fallback=False, args=('--commit', 'HEAD', '--kit-verified', '--kit', str(kit)))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("line-ending-only churn in 'x.sh'", result.stdout + result.stderr)

    def test_a_mode_change_of_a_kit_owned_file_stays_in_the_diff(self):
        # kitv4 item 1: the mode must be the kit's and unchanged against the parent.
        kit, _ = self.kit_upgrade(executable=True)
        self.assertEqual([entry['path'] for entry in bridge.kit_verified(self.repo, 'HEAD', kit)], ['x.sh'])
        self.git('update-index', '--chmod=-x', 'x.sh')
        os.chmod(self.repo / 'x.sh', 0o644)
        (self.repo / 'file.py').write_text('mode\n')
        self.commit_fixture('Lose the exec bit')
        self.assertEqual(bridge.kit_verified(self.repo, 'HEAD', kit), [])
        log = self.root / 'prompt.txt'
        code, result = self.run_bridge(extra=['--commit', 'HEAD', '--kit-verified', str(kit)],
                                       env_extra={'PROMPT_LOG': str(log)})
        self.assertEqual(code, 0, result)
        self.assertIn('old mode 100755', log.read_text(encoding='utf-8').partition('\nDiff:\n')[2])
        # Added with a mode the kit does not have.
        self.git('rm', '-q', '--cached', 'x.sh')
        self.kit_git(self.repo, 'commit', '-qm', 'Remove x.sh')
        self.git('add', 'x.sh')
        self.commit_fixture('Add x.sh as 100644')
        self.assertEqual(self.git('ls-tree', 'HEAD', 'x.sh').stdout.decode().split()[0], '100644')
        self.assertEqual(bridge.kit_verified(self.repo, 'HEAD', kit), [])
        # Back to the kit's 100755: the mode is the kit's, but the commit changes it.
        self.git('update-index', '--chmod=+x', 'x.sh')
        os.chmod(self.repo / 'x.sh', 0o755)
        (self.repo / 'file.py').write_text('mode again\n')
        self.commit_fixture('Gain the exec bit')
        self.assertEqual(self.git('ls-tree', 'HEAD', 'x.sh').stdout.decode().split()[0], '100755')
        self.assertEqual(bridge.kit_verified(self.repo, 'HEAD', kit), [])

    def test_kit_verified_refuses_a_kit_folder_of_another_repository(self):
        # kitv4 item 2: sync-kit.sh's own_repo rule.
        from contextlib import redirect_stderr
        kit, _ = self.kit_upgrade(nest=True)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(bridge.kit_verified(self.repo, 'HEAD', kit), [])
        self.assertIn('is no git clone of its own', err.getvalue())

    def test_kit_verified_leaves_a_symlink_and_a_path_over_a_directory_in_the_diff(self):
        # kitv4 items 2 and 3: a symlink equal to the kit's symlink; a kit file that replaces a
        # directory, whose deletions its exclusion pathspec would hide.
        kit, _ = self.kit_upgrade()
        link = '# KIT-OWNED: do not edit locally\n'.encode()
        blob = self.kit_git(kit, 'hash-object', '-w', '--stdin', stdin=link)
        self.kit_git(kit, 'update-index', '--add', '--cacheinfo', '120000,%s,core/link' % blob)
        self.kit_git(kit, 'commit', '-qm', 'link')
        self.kit_git(kit, 'tag', 'v1.1.0')
        self.kit_git(self.repo, 'hash-object', '-w', '--stdin', stdin=link)
        self.git('update-index', '--add', '--cacheinfo', '120000,%s,link' % blob)
        (self.repo / 'docs/kit/.kit-commit').write_text(self.kit_git(kit, 'rev-parse', 'HEAD') + '\n')
        self.git('add', 'docs/kit/.kit-commit')
        self.kit_git(self.repo, 'commit', '-qm', 'Symlink')
        self.assertEqual(bridge.kit_verified(self.repo, 'HEAD', kit), [])
        self.git('rm', '-q', '--cached', 'link')
        self.git('rm', '-q', 'x.sh')
        (self.repo / 'x.sh').mkdir()
        (self.repo / 'x.sh/inner.txt').write_text('inner\n')
        self.commit_fixture('A directory')
        shutil.rmtree(self.repo / 'x.sh')
        (self.repo / 'x.sh').write_bytes(b'# KIT-OWNED: do not edit locally\necho kit\n')
        self.commit_fixture('The kit file over the directory')
        self.assertEqual(bridge.kit_verified(self.repo, 'HEAD', kit), [])

    def test_kit_verified_needs_a_released_kit_commit_and_no_downgrade(self):
        # kitv4 items 6 and 7 (lead decisions 6, 7).
        from contextlib import redirect_stderr
        kit, kit_commit = self.kit_upgrade(tag=False)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(bridge.kit_verified(self.repo, 'HEAD', kit), [])
        self.assertIn('kit commit %s is on no release tag v*' % kit_commit, err.getvalue())
        self.kit_git(kit, 'tag', 'v1.0.0', kit_commit)
        (kit / 'core/x.sh').write_bytes(b'# KIT-OWNED: do not edit locally\necho kit 2\n')
        self.kit_git(kit, 'commit', '-qam', 'kit 2')
        self.kit_git(kit, 'tag', 'v2.0.0')
        newer = self.kit_git(kit, 'rev-parse', 'HEAD')
        for recorded, text, expected in ((newer, b'echo kit 2', ['x.sh']), (kit_commit, b'echo kit', [])):
            (self.repo / 'x.sh').write_bytes(b'# KIT-OWNED: do not edit locally\n%s\n' % text)
            (self.repo / 'docs/kit/.kit-commit').write_text(recorded + '\n')
            self.commit_fixture('Kit at ' + recorded)
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual([entry['path'] for entry in bridge.kit_verified(self.repo, 'HEAD', kit)], expected)
        self.assertIn('kit commit %s does not descend from %s' % (kit_commit, newer), err.getvalue())

    def test_a_past_commit_review_keeps_its_mode_when_the_checkout_moves_onto_it(self):
        # kitv4 item 8: past mode is decided by the first snapshot; a recheck after the owner
        # stashed the tree and checked the reviewed commit out keeps the commit's fingerprint.
        self.commit_fixture('Commit A')
        past = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        (self.repo / 'file.py').write_text('later\n')
        self.commit_fixture('Commit B')
        (self.repo / 'file.py').write_text('dirty\n')
        first = bridge.snapshot(self.repo, 'commit', past, True)
        self.git('stash', '-q')
        self.git('checkout', '-q', past)
        self.assertEqual(bridge.recheck(self.repo, 'commit', past, True, None, True)[1], first[1])
        self.assertNotEqual(bridge.recheck(self.repo, 'commit', past, True)[1], first[1])

    def test_the_diff_limit_refusal_names_its_size_and_largest_files(self):
        (self.repo / 'big.txt').write_text('x' * 99 + '\n' * 1 + ('y' * 99 + '\n') * 4500)
        with self.assertRaises(bridge.BridgeError) as caught:
            bridge.snapshot(self.repo, 'uncommitted', None)
        message = str(caught.exception)
        self.assertRegex(message, r'diff is \d+ bytes, over the limit of 400000 bytes')
        self.assertRegex(message, r'the largest: big\.txt \(\d+ bytes\), file\.py \(\d+ bytes\); split the task')

    def test_kit_verified_needs_a_claude_commit_review(self):
        import review_dispatch
        for argv, why in ((['--reviewer', 'codex', '--commit', 'HEAD', '--kit-verified'], '--reviewer claude'),
                          (['--uncommitted', '--kit-verified'], 'a --commit only'),
                          (['--commit', 'HEAD', '--kit', str(self.root)], 'for --kit-verified only')):
            with self.subTest(argv=argv), self.assertRaises(ValueError) as caught:
                review_dispatch.main(['--repo', str(self.repo), *argv])
            self.assertIn(why, str(caught.exception))
        # The wrapper's own guards answer with its usage line, before the dispatcher.
        for argv in (('--kit-verified',), ('--commit', 'HEAD', '--kit', str(self.root))):
            with self.subTest(argv=argv):
                result = self.run_wrapper(*argv)
                self.assertEqual(result.returncode, 2)
                self.assertIn('usage: review.sh', result.stdout)
        # A Claude attempt that cannot run does not fall back to Codex, which has no kit-verified diff.
        kit, _ = self.kit_upgrade()
        result, chain = self.dispatch_result(args=('--commit', 'HEAD', '--kit-verified', '--kit', str(kit)),
                                             FIXTURE_CASE='quota')
        self.assertEqual(len(chain['attempts']), 1, result.stdout + result.stderr)
        self.assertIn('--kit-verified is reviewed by Claude only', chain['fallback_blocked'])

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
        self.assertEqual(result["failure_kind"], "quota_exhausted")
        record = json.loads(Path(result["usage_record"]).read_text())
        self.assertEqual(record["requester_reported"], "codex/fixture")
        self.assertEqual(record["usage"]["input_tokens"], 7)
        self.assertEqual(record["usage"]["api_cost_usd_reported"], 0.123)
        self.assertIsNone(record["usage"]["subscription_percent_consumed"])
        self.assertEqual(record["recovery"]["action"], "continue_independent_work")
        self.assertFalse(record["recovery"]["review_approved"])

    def assert_supervision_os_error_keeps_usage(self, provider, fault):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import errno
        import agent_process
        import claude_bridge
        import codex_bridge
        module = claude_bridge if provider == 'claude' else codex_bridge
        output = (json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False,
                             'total_cost_usd': 0.123, 'usage': {'input_tokens': 7}})
                  if provider == 'claude' else
                  json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 7}}))
        real_run = agent_process.run
        real_stop = agent_process.stop_group

        def broken_cleanup(*args):
            real_stop(*args)
            raise OSError(errno.EIO, 'cleanup EIO')

        def reviewer(command, prompt, repo, timeout, **kwargs):
            if '--json' not in command and '--output-format' not in command:
                return real_run(command, prompt, repo, timeout, **kwargs)
            failure = (patch.object(agent_process, '_exited_unreaped',
                                    side_effect=OSError(errno.EIO, 'supervision EIO'))
                       if fault == 'supervision' else
                       patch.object(agent_process, 'stop_group', side_effect=broken_cleanup))
            with failure:
                return real_run([sys.executable, '-B', '-c',
                                 'import sys; sys.stdin.read(); print(' + repr(output) + ')'],
                                prompt, repo, timeout, **kwargs)

        results = []
        args = ['review'] if provider == 'claude' else ['--model', 'fixture-codex-model']
        with patch.dict(os.environ, self.review_env(MYAGENTKIT_CAPTURE_QUOTA='0')), \
                patch.object(agent_process, 'run', side_effect=reviewer), \
                redirect_stdout(io.StringIO()):
            code = module.main([*args, '--repo', str(self.repo)], results.append)
        self.assertEqual(code, 5)
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result['failure_kind'], 'run_failed')
        evidence = Path(result['evidence']).read_text()
        self.assertIn('supervision failed', evidence)
        self.assertNotIn('never ran', evidence)
        record = json.loads(Path(result['usage_record']).read_text())
        self.assertEqual((record['status'], record['failure_kind']), ('failed', 'run_failed'))
        self.assertEqual(record['usage']['input_tokens'], 7)
        self.assertIn(output, record['raw_stdout'])
        self.assertIn(fault + ' EIO', record['raw_stderr'])
        self.assertGreater(record['duration_ms'], 0)
        if provider == 'claude':
            self.assertEqual(record['usage']['api_cost_usd_reported'], 0.123)

    def test_claude_supervision_os_error_keeps_partial_usage_and_evidence(self):
        for fault in ('supervision', 'cleanup'):
            with self.subTest(fault=fault):
                self.assert_supervision_os_error_keeps_usage('claude', fault)

    def test_codex_supervision_os_error_keeps_partial_usage_and_evidence(self):
        for fault in ('supervision', 'cleanup'):
            with self.subTest(fault=fault):
                self.assert_supervision_os_error_keeps_usage('codex', fault)

    def test_timeout_keeps_partial_usage_and_raw_evidence(self):
        # The limit covers the throwaway copy and the fake's start: one second under a loaded
        # slow tier stopped the fake before it printed (399 ms left it, exit 1, no output).
        seconds = str(round(3 * float(os.environ.get('MYAGENTKIT_TEST_TIMEOUT_SCALE', '1'))))
        code, result = self.run_bridge("partial_timeout", extra=["--timeout", seconds])
        self.assertEqual(code, 5, result)
        usage = json.loads(Path(result["usage_record"]).read_text())
        self.assertIn('"total_cost_usd": 0.123', usage["raw_stdout"],
                      {k: usage.get(k) for k in ("duration_ms", "exit_code", "raw_stderr")})
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
            # Installed projects own these three defaults, in gate_config.sh (#94). Exercise the
            # template's empty-pin cases in an explicit fixture without overwriting project config.
            config = (ROOT / "gate_config.sh").read_text()
            for name, value in (("DEFAULT_REVIEWER", "claude"),
                                ("CODEX_MODEL", ""), ("CLAUDE_MODEL", "")):
                config, count = re.subn(r"^" + name + r"=.*$",
                                        name + '="' + value + '"', config, flags=re.M)
                self.assertEqual(count, 1, "missing project configuration: " + name)
            (scripts / "gate_config.sh").write_bytes(config.encode())
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
        fake = python_cli(fake, PYTHON_SHEBANG + '''import json, os, pathlib, sys, time
if '--version' in sys.argv: print('offline codex'); sys.exit(0)
prompt = sys.stdin.buffer.read().decode('utf-8')  # the bridge sends UTF-8
assert 'PRIVATE_PREVIOUS_REVIEW' not in prompt
last = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])
case = os.environ['FIXTURE_CASE']
assert '--json' in sys.argv and '--ephemeral' in sys.argv
assert sys.argv[sys.argv.index('-s') + 1] == 'workspace-write'
assert '--skip-git-repo-check' in sys.argv and 'sandbox_workspace_write.network_access=false' in sys.argv
repo = pathlib.Path(os.environ['FIXTURE_REPO'])
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
    (repo / 'file.py').write_text('mutated')
    last.write_text('VERDICT: Accept\\n')
if case == 'archive_failure':
    import shutil
    shutil.rmtree(repo / 'docs/reviews')
    (repo / 'docs/reviews').write_text('blocked archive')
    last.write_text('VERDICT: Accept\\n')
''')
        self.fake_codex = fake
        (self.repo / '.gitignore').write_bytes(IGNORE_RULES)
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
                           REVIEW_ROUND_EXCEPTION="fixture: every case runs under one label",
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
                    # KARARLAR D04 inv2#126: a used-up quota is quota_exhausted, not a bare quota.
                    self.assertEqual(usage["failure_kind"], 'quota_exhausted' if case == 'quota' else case)
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
        fake = python_cli(fake, PYTHON_SHEBANG +
                        "import json, os, pathlib, sys\n"
                        "prompt = sys.stdin.buffer.read().decode('utf-8')\n"
                        "if os.environ.get('PROMPT_LOG'): pathlib.Path(os.environ['PROMPT_LOG']).write_text(prompt, encoding='utf-8')\n"
                        "case = os.environ.get('CODEX_FIXTURE_CASE', 'accept')\n"
                        "assert os.environ['MYAGENTKIT_DELEGATION_DEPTH'] == '1'\n"
                        "if os.environ.get('CWD_LOG'):\n"
                        "    pathlib.Path('reviewer-wrote.txt').write_text('written by the reviewer')\n"
                        "    new = pathlib.Path('new file.txt')\n"
                        "    pathlib.Path(os.environ['CWD_LOG']).write_text(json.dumps({'cwd': os.getcwd(), "
                        "'file': pathlib.Path('file.py').read_text(), "
                        "'new': new.read_text() if new.exists() else None, 'leaks': sorted(k for k, v in "
                        "os.environ.items() if k != 'FIXTURE_REPO' and os.environ['FIXTURE_REPO'] in v)}))\n"
                        "if case == 'unknown_flag':\n"
                        "    sys.stderr.write(\"error: unexpected argument '--ephemeral' found\\n\"); sys.exit(2)\n"
                        "if case == 'quota':\n"
                        "    print(json.dumps({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}})); sys.exit(1)\n"
                        # The CLI's own MCP client failing on stderr, and a reconnect it
                        # recovered from in the stream, around an otherwise normal review.
                        "if case.startswith('mcp'):\n"
                        "    sys.stderr.write('ERROR rmcp::transport::worker: worker quit with fatal: "
                        "Transport channel closed\\n')\n"
                        "if case.startswith('mcp_'):\n"
                        "    print(json.dumps({'type': 'error', 'message': 'Reconnecting... 2/5 "
                        "(stream disconnected before completion' + (': 429 Too Many Requests' "
                        "if case == 'mcp_429_no_verdict' else '') + ')'}))\n"
                        "if case == 'mcp_quota':\n"
                        "    print(json.dumps({'type': 'error', 'message': 'usage limit reached'})); sys.exit(0)\n"
                        "verdict = 'Reject' if case == 'reject' else 'Accept'\n"
                        "text = '## Findings\\n\\nLow: fixture finding.\\n\\nVERDICT: ' + verdict + '\\n'\n"
                        "text = {'mcp_no_verdict': '## Findings\\n\\nLow: fixture finding.\\n',\n"
                        "        'mcp_429_no_verdict': '## Findings\\n\\nLow: fixture finding.\\n',\n"
                        "        'mcp_two_verdicts': text + 'VERDICT: Reject\\n'}.get(case, text)\n"
                        "pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text(text)\n"
                        "if case == 'mcp_failed_turn': print(json.dumps({'type': 'turn.failed', 'error': {}}))\n"
                        "if case != 'mcp_no_completion': print(json.dumps({'type': 'turn.completed', 'usage': {}}))\n"
                        "if case == 'mcp_exit': sys.exit(1)\n")
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
        # PATHEXT lookup on native Windows needs the executable extension.
        shutil.copyfile(good, bin_dir / ('codex.exe' if WINDOWS else 'codex'))
        (bin_dir / ('codex.exe' if WINDOWS else 'codex')).chmod(0o755)
        home = self.root / "home"
        stale = home / ".local" / "bin"
        stale.mkdir(parents=True)
        python_cli(stale / 'codex', PYTHON_SHEBANG +
                   "import sys\nprint('stale standalone build', file=sys.stderr)\nraise SystemExit(1)\n")
        result = self.run_wrapper("--uncommitted", "--reviewer", "codex",
                                  REVIEW_CLI_BIN="codex", HOME=str(home),
                                  PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
                                  REVIEW_CODEX_MODEL="fixture-codex-model")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("stale standalone build", result.stdout + result.stderr)

    def test_both_reviewers_publish_one_identical_evidence_format(self):
        """The hard requirement of a role-neutral kit: swapping roles keeps records comparable.

        Two reviewers that archived two shapes would force every later reader — and the
        review suite — to learn two formats, and no record could be lined up against the one
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
        # A reviewer told not to run tests sent every finding back unreproduced, and a worker then
        # spent a round reproducing it; one that executed in a throwaway copy found decisive defects.
        # The bridged reviewers now execute, in a throwaway copy the adapter made: the ask is
        # unconditional, and the prompt never names the reviewed repository's path.
        # Native Windows has no Bash sandbox: there the reviewer reads and reasons instead.
        # The shared prompt (owner decision 2026-10-13, E): a threshold instead of EVERY finding,
        # no fix sketch, a clean review is valid, Pre-existing items stay out of the verdict.
        # Owner decision 2026-10-13: a Lows-only review is a plain Accept (accept_allows, GATE:
        # a Low goes to the backlog), so the verdict rule no longer sends a Low to manual checks.
        # KARARLAR B01-2 inv2#25: a doubt with no file, line and trigger is no finding, even in
        # the first priority; it goes under Manual checks for the owner.
        asks = ('A clean review is a valid result', 'Severity, for this project', 'Pre-existing:',
                'is no finding: write it under Manual checks',
                'at most five Low', 'You are in a throwaway copy', 'NOT RUN', 'Never use the network',
                'Accept with Manual Checks when a Medium, a deferred finding or a first-priority doubt remains',
                'Accept otherwise, Lows and Pre-existing items included') + (
                    ('You have no shell on this host', 'mark each finding REASONED') if WINDOWS else
                    ('run anything inside this copy', 'Run the reproductions here', 'REPRODUCED',
                     'if a run is impossible, mark it REASONED'))
        forbidden = ('Do not run tests', 'run code', 'SHOULD run', 'worktree add --detach',
                     'If your tools can execute', 'edit files in this checkout',
                     'never change the reviewed checkout', 'Fix sketch:', 'EVERY finding', str(self.repo),
                     'a Medium, a Low', 'which is Medium')
        # The direct adapter's --task-file audit (the review SKILL documents it) silently lost
        # its brief when the review branch took its Task block from REVIEW_TASK_FILE alone.
        brief = self.root / 'brief.md'
        brief.write_text('Audit brief: the money path rounds half up.\n')
        code, audited = self.run_bridge(extra=['--task-file', str(brief)], env_extra={'PROMPT_LOG': str(log)})
        self.assertEqual(code, 0, audited)
        self.assertIn('Task:\nAudit brief: the money path rounds half up.\n', log.read_text())
        task = {'PROMPT_LOG': str(log), 'MYAGENTKIT_TASK_ID': 'rounds-task'}
        code, first = self.run_bridge('reject', env_extra=task)
        self.assertEqual(code, 0, first)
        for ask in asks:
            self.assertIn(ask, log.read_text())
        for words in forbidden:
            self.assertNotIn(words, log.read_text())
        self.assertNotIn('### Round 1', log.read_text())
        code, second = self.run_bridge('accept', env_extra=task)
        self.assertEqual(code, 0, second)
        self.assertIn('### Round 1', log.read_text())
        self.assertIn('file.py:1: concrete defect', log.read_text())
        self.assertIn('Earlier verdict: Reject', log.read_text())
        # Round 3 through the wrapper, by the other reviewer: both rounds, oldest first. Two
        # rounds are the limit under one label; a third needs its reason, kept in the record.
        notes = self.root / 'dispositions.md'
        notes.write_text('file.py:1 disproved: the defect needs input the caller rejects.\n')
        refused = self.run_wrapper('--reviewer', 'codex', REVIEW_CLI_BIN=str(self.build_fake_codex()),
                                   REVIEW_CODEX_MODEL='fixture-codex-model',
                                   REVIEW_DISPOSITIONS=str(notes), **task)
        self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
        self.assertIn('REVIEW_ROUND_EXCEPTION', refused.stdout + refused.stderr)
        result = self.run_wrapper('--reviewer', 'codex', REVIEW_CLI_BIN=str(self.build_fake_codex()),
                                  REVIEW_CODEX_MODEL='fixture-codex-model',
                                  REVIEW_DISPOSITIONS=str(notes),
                                  REVIEW_ROUND_EXCEPTION='fixture: a third round', **task)
        chain = json.loads(result.stdout.split('review dispatch: ', 1)[1].splitlines()[0])
        third = json.loads(Path(chain['attempts'][-1]['usage_record']).read_text())
        self.assertEqual(third['task']['round_exception'], 'fixture: a third round')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        prompt = log.read_text()
        for ask in asks:
            self.assertIn(ask, prompt)
        for words in forbidden:
            self.assertNotIn(words, prompt)
        # Oldest first inside the round sections; the templates name every verdict too.
        rounds = re.split(r'^### Round \d+$', prompt.split('\nDiff:\n')[0], flags=re.M)
        self.assertEqual(len(rounds), 3, prompt)
        self.assertIn('Earlier verdict: Reject', rounds[1])
        self.assertIn('Earlier verdict: Accept\n', rounds[2])
        # A carried "VERDICT:" line, echoed by Codex, would break its exactly-one-verdict check.
        self.assertEqual(re.findall(r'^[ \t]*VERDICT[ \t]*:.*$', prompt, re.M), [])
        self.assertIn('disproved: the defect needs input', prompt)
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

    def test_the_reviewer_executes_in_a_throwaway_copy_removed_afterwards(self):
        # The reviewers may now run anything, so they never run in the reviewed repository: each
        # attempt gets a copy of HEAD plus the uncommitted diff, removed when the attempt ends.
        (self.repo / 'new file.txt').write_text('an untracked file\n')
        # An owner's diff.noprefix must not break the diff applied to the copy, nor color.ui=always
        # put ANSI escapes into it (rsel3).
        self.git('config', 'diff.noprefix', 'true')
        self.git('config', 'color.ui', 'always')
        log = self.root / 'cwd.json'
        self.install_wrapper()
        status = self.git('status', '--porcelain').stdout
        runs = {'claude': lambda: self.run_bridge(env_extra={'CWD_LOG': str(log)}),
                'codex': lambda: self.run_wrapper('--reviewer', 'codex', CWD_LOG=str(log),
                                                  REVIEW_CLI_BIN=str(self.build_fake_codex()),
                                                  REVIEW_CODEX_MODEL='fixture-codex-model')}
        for reviewer, run in runs.items():
            with self.subTest(reviewer=reviewer, scope='uncommitted'):
                outcome = run()
                ok = outcome[0] == 0 if reviewer == 'claude' else outcome.returncode == 0
                self.assertTrue(ok, outcome)
                seen = json.loads(log.read_text())
                copy = Path(seen['cwd'])
                self.assertFalse(copy.resolve().is_relative_to(self.repo.resolve()), copy)
                self.assertFalse(copy.exists(), 'the copy outlived the review')
                # HEAD with the uncommitted diff applied, the untracked file included.
                self.assertEqual((seen['file'], seen['new']), ('changed\n', 'an untracked file\n'))
                # Nor does its environment name the repository (PWD, REVIEW_REPO_ROOT, GIT_*).
                self.assertEqual(seen['leaks'], [])
                # What the reviewer wrote stayed in its copy.
                self.assertFalse((self.repo / 'reviewer-wrote.txt').exists())
                self.assertEqual(self.git('status', '--porcelain').stdout, status)
                evidence = (outcome[1]['evidence'] if reviewer == 'claude' else
                            max((self.repo / 'docs/reviews').glob('*-codex-review.md'),
                                key=lambda path: path.stat().st_mtime))
                self.assertIn('throwaway copy', header_of(evidence)['sandbox'])
                if reviewer == 'codex':
                    self.assertEqual(header_of(evidence)['sandbox'], 'workspace-write (throwaway copy)')
        # A clean --commit review gets the archive of HEAD itself: one file compared.
        (self.repo / 'new file.txt').unlink()
        self.commit_fixture('Commit the change')
        # The fixture reads in text mode: a CRLF that Windows wrote into the commit reads as LF.
        head_file = self.git('show', 'HEAD:file.py').stdout.decode().replace('\r\n', '\n')
        for reviewer in ('claude', 'codex'):
            with self.subTest(reviewer=reviewer, scope='commit'):
                if reviewer == 'claude':
                    code, result = self.run_bridge(extra=['--commit', 'HEAD'], env_extra={'CWD_LOG': str(log)})
                    self.assertEqual(code, 0, result)
                else:
                    result = self.run_wrapper('--commit', 'HEAD', '--reviewer', 'codex', CWD_LOG=str(log),
                                              REVIEW_CLI_BIN=str(self.build_fake_codex()),
                                              REVIEW_CODEX_MODEL='fixture-codex-model')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                seen = json.loads(log.read_text())
                self.assertEqual((seen['file'], seen['new']), (head_file, None))
                self.assertFalse(Path(seen['cwd']).exists())

    def test_the_copy_holds_the_checkout_bytes_whatever_git_would_hide(self):
        import claude_bridge
        # The copy is built from the working tree's bytes, not from a patch: git's stat cache
        # (core.trustctime=false, core.checkStat=minimal, a same-size edit with its mtime put
        # back) and apply.whitespace=fix would otherwise give the reviewer other source.
        self.git('config', 'core.trustctime', 'false')
        self.git('config', 'core.checkStat', 'minimal')
        self.git('config', 'apply.whitespace', 'fix')
        target = self.repo / 'file.py'
        stat = target.stat()
        self.git('status')  # refresh the index's stat data
        tampered = target.read_bytes().replace(b'changed', b'TAMPERD')
        self.assertEqual(len(tampered), len(target.read_bytes()))
        target.write_bytes(tampered)
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        (self.repo / 'spaces.py').write_bytes(b'S = """a line with trailing spaces   \nx"""\n')
        copy = Path(tempfile.mkdtemp(dir=self.root))
        head = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        claude_bridge.throwaway_copy(self.repo, head, '', copy)
        self.assertEqual((copy / 'file.py').read_bytes(), tampered)
        self.assertEqual((copy / 'spaces.py').read_bytes(), (self.repo / 'spaces.py').read_bytes())
        # What the working tree deleted is gone from the copy.
        (self.repo / 'spaces.py').unlink()
        (self.repo / 'file.py').unlink()
        copy2 = Path(tempfile.mkdtemp(dir=self.root))
        claude_bridge.throwaway_copy(self.repo, head, '', copy2)
        self.assertFalse((copy2 / 'file.py').exists())
        self.assertFalse((copy2 / 'spaces.py').exists())

    def test_copy_never_writes_through_an_archived_symlink_parent(self):
        import claude_bridge
        outside = self.root / 'outside'
        outside.mkdir()
        sentinel = outside / 'sentinel'
        sentinel.write_bytes(b'external original')
        link = self.repo / 'parent'
        link.symlink_to(outside, target_is_directory=True)
        self.commit_fixture('Track a directory symlink')
        link.unlink()
        link.mkdir()
        (link / 'sentinel').write_bytes(b'checkout replacement')
        self.git('add', 'parent')
        copy = Path(tempfile.mkdtemp(dir=self.root))
        claude_bridge.throwaway_copy(self.repo, 'HEAD', '', copy)
        self.assertEqual(sentinel.read_bytes(), b'external original')
        self.assertFalse((copy / 'parent').is_symlink())
        self.assertEqual((copy / 'parent/sentinel').read_bytes(), b'checkout replacement')

    def test_copy_removes_staged_deletions(self):
        import claude_bridge
        self.git('rm', '-f', 'file.py')
        copy = Path(tempfile.mkdtemp(dir=self.root))
        claude_bridge.throwaway_copy(self.repo, 'HEAD', '', copy)
        self.assertFalse((copy / 'file.py').exists())

    def check_directory_replacement(self, symlink):
        import claude_bridge
        directory = self.repo / 'directory'
        directory.mkdir()
        (directory / 'old').write_bytes(b'old')
        self.commit_fixture('Track a directory')
        shutil.rmtree(directory)
        if symlink:
            directory.symlink_to('file.py')
        else:
            directory.write_bytes(b'replacement')
        # Both unstaged and staged replacements must have exactly the checkout's types.
        for staged in (False, True):
            with self.subTest(staged=staged):
                if staged:
                    self.git('add', '-A')
                copy = Path(tempfile.mkdtemp(dir=self.root))
                claude_bridge.throwaway_copy(self.repo, 'HEAD', '', copy)
                target = copy / 'directory'
                self.assertEqual(target.is_symlink(), symlink)
                if symlink:
                    self.assertEqual(os.readlink(target), 'file.py')
                else:
                    self.assertEqual(target.read_bytes(), b'replacement')

    def test_copy_handles_directory_to_file(self):
        self.check_directory_replacement(False)

    def test_copy_handles_directory_to_symlink(self):
        self.check_directory_replacement(True)

    @posix_only
    def test_copy_compares_large_unchanged_files_with_bounded_memory(self):
        # Only the child is constrained: the suite runner may already exceed this limit.
        asset = self.repo / 'large.bin'
        with asset.open('wb') as stream:
            chunk = b'x' * (1024 * 1024)
            for _ in range(48):
                stream.write(chunk)
        self.commit_fixture('Track a large unchanged asset')
        (self.repo / 'file.py').write_bytes(b'small edit')
        copy = Path(tempfile.mkdtemp(dir=self.root))
        script = '''
import resource, sys
from pathlib import Path
import claude_bridge
try:
    resource.setrlimit(resource.RLIMIT_AS, (100 * 1024 * 1024, 100 * 1024 * 1024))
except (ValueError, OSError):
    # macOS refuses to lower RLIMIT_AS: said, and the process ends with 0 through no
    # interpreter teardown (which failed under the limit once set partway).
    sys.stdout.write("NOT RUN: the address-space limit cannot be lowered on this host (macOS)\\n")
    sys.stdout.flush()
    import os
    os._exit(0)
claude_bridge.throwaway_copy(Path(sys.argv[1]), 'HEAD', '', Path(sys.argv[2]))
'''
        result = subprocess.run([sys.executable, '-B', '-c', script, str(self.repo), str(copy)],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        if 'NOT RUN:' in result.stdout + result.stderr:
            print((result.stdout + result.stderr).strip())
            return
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with asset.open('rb') as source, (copy / 'large.bin').open('rb') as target:
            while True:
                chunk = source.read(64 * 1024)
                self.assertEqual(target.read(64 * 1024), chunk)
                if not chunk:
                    break

    def test_copy_and_reviewer_share_one_total_timeout(self):
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import agent_process
        import claude_bridge
        import codex_bridge
        real_copy, real_run = claude_bridge.throwaway_copy, agent_process.run
        for module, args in ((claude_bridge, ['review', '--timeout', '2']),
                             (codex_bridge, ['--model', 'fixture-codex-model'])):
            with self.subTest(reviewer=module.__name__):
                # Exercise the real pinned archive before this controlled deadline probe.
                # Native Git can itself exhaust the 0.7 s left by the injected delay;
                # the separate archive-deadline tests cover that preparation-only failure.
                head, _, diff, _ = bridge.snapshot(self.repo, 'uncommitted', None)
                prepared = self.root / ('prepared-' + module.__name__)
                prepared.mkdir()
                real_copy(self.repo, head, diff, prepared)
                budgets = []
                timed_region = []

                def slow_copy(repo, copied_head, copied_diff, destination, **kwargs):
                    # The repository as main resolved it (macOS's /var is /private/var).
                    self.assertEqual((repo, copied_head, copied_diff), (self.repo.resolve(), head, diff))
                    timed_region.append(time.monotonic())
                    time.sleep(1.3)
                    shutil.copytree(prepared, destination, symlinks=True, dirs_exist_ok=True)

                def slow_reviewer(command, prompt, repo, timeout, **kwargs):
                    budgets.append(timeout)
                    try:
                        return real_run([sys.executable, '-c',
                                         'import sys, time; sys.stdin.read(); time.sleep(1.3)'],
                                        prompt, repo, timeout, **kwargs)
                    finally:
                        timed_region.append(time.monotonic())

                received = []
                with patch.dict(os.environ, self.review_env(REVIEW_TIMEOUT_SECONDS='2')), \
                        patch.object(module, 'throwaway_copy', side_effect=slow_copy), \
                        patch('agent_process.run', side_effect=slow_reviewer), \
                        redirect_stdout(io.StringIO()):
                    module.main([*args, '--repo', str(self.repo)], received.append)
                self.assertEqual(len(timed_region), 2, received)
                elapsed = timed_region[1] - timed_region[0]
                self.assertEqual(len(budgets), 1, received)
                self.assertGreater(budgets[0], 0)
                self.assertLess(budgets[0], 0.8)
                # The budget above is the proof of the shared deadline; the wall time only
                # rules out two full timeouts in a row (3.3 s), with room for a slow runner.
                # Git preflight and final accounting are outside that deadline, and native
                # Windows Git can take seconds there: time only the copy/reviewer region.
                self.assertLess(elapsed, 3.2)
                self.assertEqual(received[0]['failure_kind'], 'timeout', received)

    def test_copy_accepts_a_symlinked_tmpdir_but_refuses_destination_symlinks(self):
        from unittest.mock import patch
        import claude_bridge
        actual = self.root / 'actual-tmp'
        actual.mkdir()
        alias = self.root / 'linked-tmp'
        alias.symlink_to(actual, target_is_directory=True)
        with patch.dict(os.environ, TMPDIR=str(alias)), patch.object(tempfile, 'tempdir', None):
            for diff in ('', None):
                with self.subTest(diff=diff), tempfile.TemporaryDirectory() as tmp:
                    self.assertEqual(Path(tmp).parent, alias)
                    copy = Path(tmp) / 'copy'
                    copy.mkdir()
                    claude_bridge.throwaway_copy(self.repo, 'HEAD', diff, copy)
                    expected = ((self.repo / 'file.py').read_bytes() if diff is not None
                                else self.git('show', 'HEAD:file.py').stdout)
                    self.assertEqual((copy / 'file.py').read_bytes(), expected)
                    outside = Path(tmp) / 'outside'
                    outside.mkdir()
                    destination = Path(tmp) / 'destination'
                    destination.symlink_to(outside, target_is_directory=True)
                    with self.assertRaises(claude_bridge.BridgeError):
                        claude_bridge.throwaway_copy(self.repo, 'HEAD', diff, destination)
                    destination.unlink()
                    destination.mkdir()
                    (destination / 'inside').symlink_to(outside, target_is_directory=True)
                    with self.assertRaises(claude_bridge.BridgeError):
                        claude_bridge.throwaway_copy(self.repo, 'HEAD', diff, destination)
                    self.assertEqual(list(outside.iterdir()), [])

    @posix_only
    def test_copy_cancel_during_each_launch_reaps_the_child(self):
        from unittest.mock import patch
        import claude_bridge

        class Cancelled(Exception):
            pass

        def cancel(signum, frame):
            raise Cancelled()

        stub = self.root / 'tar'
        pid_file = self.root / 'launch.pid'
        stub.write_text('#!%s\nimport os, time\nfrom pathlib import Path\n'
                        'Path(%r).write_text(str(os.getpid()))\ntime.sleep(60)\n'
                        % (sys.executable, str(pid_file)))
        stub.chmod(0o755)
        real_popen = subprocess.Popen
        for target in ('archive', 'tar', 'ls-files'):
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                with self.subTest(target=target, signal=sig):
                    children = []
                    pid_file.unlink(missing_ok=True)

                    def launch(command, *args, **kwargs):
                        if command[0] == '/bin/ps':
                            return real_popen(command, *args, **kwargs)  # macOS cleanup scan
                        inject = target in command
                        child = real_popen([str(stub)] if inject else command, *args, **kwargs)
                        children.append(child)
                        if inject:
                            until = time.monotonic() + 5
                            while not pid_file.exists() and time.monotonic() < until:
                                time.sleep(0.01)
                            self.assertTrue(pid_file.exists(), 'stub did not start')
                            # Deliver inside Popen, before its caller has assigned the handle.
                            send_cancel(sig)
                        return child

                    previous = signal.signal(sig, cancel)
                    try:
                        copy = Path(tempfile.mkdtemp(dir=self.root))
                        with patch('claude_bridge.subprocess.Popen', side_effect=launch):
                            with self.assertRaises(Cancelled):
                                claude_bridge.throwaway_copy(
                                    self.repo, 'HEAD', '' if target == 'ls-files' else None, copy)
                        pid = int(pid_file.read_text())
                        with self.assertRaises(ProcessLookupError, msg='launch leaked a child'):
                            os.kill(pid, 0)
                        for child in children:
                            for stream in (child.stdin, child.stdout, child.stderr):
                                if stream is not None:
                                    self.assertTrue(stream.closed)
                    finally:
                        signal.signal(sig, previous)
                        for child in children:
                            try:
                                os.killpg(child.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            child.wait()
                            for stream in (child.stdin, child.stdout, child.stderr):
                                if stream is not None:
                                    stream.close()

    @posix_only
    def test_copy_deadline_kills_descendants_after_tar_exits(self):
        from unittest.mock import patch
        import claude_bridge
        bin_dir = self.root / 'exiting-tar'
        bin_dir.mkdir()
        pid_file = self.root / 'grandchild.pid'
        stub = bin_dir / 'tar'
        stub.write_text('#!%s\nimport subprocess, sys\nfrom pathlib import Path\n'
                        'sys.stdin.buffer.read()\n'
                        'child = subprocess.Popen([sys.executable, "-c", '
                        '"import time; time.sleep(60)"])\n'
                        'Path(%r).write_text(str(child.pid))\n'
                        % (sys.executable, str(pid_file)))
        stub.chmod(0o755)
        copy = Path(tempfile.mkdtemp(dir=self.root))
        try:
            with patch.dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH']):
                started = time.monotonic()
                with self.assertRaisesRegex(claude_bridge.BridgeError, 'wall-clock limit'):
                    claude_bridge.throwaway_copy(self.repo, 'HEAD', None, copy, timeout=0.5)
                self.assertLess(time.monotonic() - started, 3)
            pid = int(pid_file.read_text())
            until = time.monotonic() + 3
            while time.monotonic() < until:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.01)
            with self.assertRaises(ProcessLookupError, msg='tar descendant survived the deadline'):
                os.kill(pid, 0)
        finally:
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @posix_only
    def test_a_tar_that_stops_reading_at_the_archive_end_is_no_copy_failure(self):
        # macOS's bsdtar exits 0 at the end-of-archive blocks, before git has written the zero
        # padding of its last record: git died of SIGPIPE, and the review failed copy_failed.
        from unittest.mock import patch
        import claude_bridge
        (self.repo / 'large.bin').write_bytes(b'x' * (1 << 20))  # past any pipe buffer
        self.commit_fixture('large')
        real_popen = subprocess.Popen
        for code in (0, 1):
            def launch(command, *args, **kwargs):
                if Path(command[0]).name == 'tar':
                    command = ['sh', '-c', 'exec 0<&-; exit %d' % code]  # done reading, as bsdtar
                return real_popen(command, *args, **kwargs)

            copy = Path(tempfile.mkdtemp(dir=self.root))
            with self.subTest(tar_exit=code), patch('claude_bridge.subprocess.Popen', side_effect=launch):
                if code:
                    # A tar that fails is still the copy's failure, git's SIGPIPE named with it.
                    with self.assertRaisesRegex(claude_bridge.BridgeError, 'git archive exited -%d' % signal.SIGPIPE):
                        claude_bridge.throwaway_copy(self.repo, 'HEAD', None, copy)
                else:
                    claude_bridge.throwaway_copy(self.repo, 'HEAD', None, copy)

    def test_missing_tar_reaps_the_already_started_archive(self):
        from unittest.mock import patch
        import claude_bridge
        real_popen = subprocess.Popen
        children = []

        def launch(command, *args, **kwargs):
            if command[0] == '/bin/ps':
                return real_popen(command, *args, **kwargs)  # macOS cleanup scan, not archive
            if Path(command[0]).name.lower() in ('tar', 'tar.exe'):
                raise FileNotFoundError('tar is unavailable')
            child = real_popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                               *args, **kwargs)
            children.append(child)
            return child

        copy = Path(tempfile.mkdtemp(dir=self.root))
        try:
            with patch('claude_bridge.subprocess.Popen', side_effect=launch):
                with self.assertRaises(FileNotFoundError):
                    claude_bridge.throwaway_copy(self.repo, 'HEAD', None, copy)
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].poll(), 'archive survived the failed tar launch')
            self.assertTrue(children[0].stdout.closed)
        finally:
            for child in children:
                if child.poll() is None:
                    import agent_process
                    agent_process.stop_group(child, child.pid)
                child.wait()
                child.stdout.close()

    @posix_only
    def test_the_copy_is_bounded_and_cancellable(self):
        import claude_bridge
        # A stalled extraction ends at the wall-clock bound or at a noted cancel, and no child
        # of the copy outlives it.
        bin_dir = self.root / 'slowbin'
        bin_dir.mkdir(exist_ok=True)
        pid_file = self.root / 'sleeper.pid'
        (bin_dir / 'tar').write_text('#!/bin/sh\ncat > /dev/null\nsleep 30 &\necho $! > %s\nwait\n'
                                     % pid_file)
        (bin_dir / 'tar').chmod(0o755)
        head = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        old_path = os.environ['PATH']
        os.environ['PATH'] = str(bin_dir) + os.pathsep + old_path
        try:
            for name, cancelled, timeout in (('bound', [], 0.3), ('cancel', [15], 30)):
                with self.subTest(name):
                    copy = Path(tempfile.mkdtemp(dir=self.root))
                    started = time.monotonic()
                    with self.assertRaises(claude_bridge.BridgeError) as ctx:
                        claude_bridge.throwaway_copy(self.repo, head, None, copy,
                                                     cancelled=cancelled, timeout=timeout)
                    self.assertLess(time.monotonic() - started, 5)
                    self.assertIn('stopped', str(ctx.exception))
                    sleeper = int(pid_file.read_text())
                    time.sleep(0.1)
                    with self.assertRaises(ProcessLookupError, msg='a child of the copy outlived it'):
                        os.kill(sleeper, 0)
        finally:
            os.environ['PATH'] = old_path

    def test_a_content_flag_is_its_own_failure_kind_not_authentication(self):
        # Codex's "flagged for possible cybersecurity risk ... authorized security work" message
        # was read as an authentication fault ("auth" in the text).
        import agent_usage
        values = [{"type": "turn.failed", "error": {"message": "This content was flagged for possible "
                   "cybersecurity risk. If you're doing authorized security work, apply for access."}}]
        self.assertEqual(agent_usage.failure("codex", {"exit_code": 0, "stderr": ""}, values), "content_flagged")
        # A connection or login "refused" is not a content flag.
        for text in ("Connection refused (os error 111)", "Login refused: authentication failed (401)"):
            bad = [{"type": "turn.failed", "error": {"message": text}}]
            self.assertNotEqual(agent_usage.failure("codex", {"exit_code": 1, "stderr": ""}, bad), "content_flagged")
        # And it is an availability failure: --fallback may try the other reviewer.
        import review_dispatch
        self.assertIn("content_flagged", review_dispatch.UNAVAILABLE)

    def test_a_preparation_that_uses_up_the_deadline_is_recorded_as_a_timeout(self):
        # The copy's time counts against the review's bound; running out there is a timeout
        # failure with a record, not an adapter error without one.
        bin_dir = self.root / 'slowbin2'
        bin_dir.mkdir(exist_ok=True)
        python_cli(bin_dir / 'tar', PYTHON_SHEBANG +
                   'import sys, time\nsys.stdin.buffer.read()\ntime.sleep(5)\n')
        self.install_wrapper()
        self.commit_fixture('A clean HEAD')
        old_path = os.environ['PATH']
        os.environ['PATH'] = str(bin_dir) + os.pathsep + old_path
        try:
            code, result = self.run_bridge(extra=['--commit', 'HEAD', '--timeout', '1'])
            self.assertNotEqual(code, 0)
            self.assertEqual(result.get('failure_kind'), 'timeout', result)
            self.assertTrue(result.get('usage_record'), result)
            outcome = self.run_wrapper('--commit', 'HEAD', '--reviewer', 'codex',
                                       REVIEW_CLI_BIN=str(self.build_fake_codex()),
                                       REVIEW_CODEX_MODEL='fixture-codex-model', REVIEW_TIMEOUT_SECONDS='1')
            self.assertNotEqual(outcome.returncode, 0)
            self.assertIn('"failure_kind": "timeout"', outcome.stdout + outcome.stderr)
        finally:
            os.environ['PATH'] = old_path

    @posix_only
    def test_a_cancel_during_cleanup_still_reaps_the_extraction(self):
        # A raising cancel handler armed, and the cancel delivered DURING the first reap (sent
        # by the first kill itself): without the blocked mask the raise skipped the second
        # reap and the extraction survived. Both the archive path and the listing path.
        import claude_bridge
        import agent_process
        from unittest.mock import patch
        bin_dir = self.root / 'slowbin3'
        bin_dir.mkdir(exist_ok=True)
        pid_file = self.root / 'child.pid'
        (bin_dir / 'tar').write_text('#!/bin/sh\necho $$ > %s\ncat > /dev/null\nsleep 30\n' % pid_file)
        (bin_dir / 'tar').chmod(0o755)
        real_git = shutil.which('git')
        (bin_dir / 'git').write_text('#!/bin/sh\ncase " $* " in *" ls-files "*) echo $$ > %s; sleep 30 ;; esac\n'
                                     'exec %s "$@"\n' % (pid_file, real_git))
        (bin_dir / 'git').chmod(0o755)
        head = subprocess.run([real_git, '-C', str(self.repo), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True).stdout.strip()
        real_killpg = os.killpg

        def killpg_then_cancel(pgid, sig):
            real_killpg(pgid, sig)
            send_cancel(signal.SIGTERM)  # pending while blocked, raised after the reaps
        old_path = os.environ['PATH']
        os.environ['PATH'] = str(bin_dir) + os.pathsep + old_path
        try:
            for name, diff in (('archive', None), ('listing', '')):
                with self.subTest(name):
                    pid_file.unlink(missing_ok=True)
                    guard = agent_process.OneShot()
                    previous = agent_process.hold(guard)
                    try:
                        copy = Path(tempfile.mkdtemp(dir=self.root))
                        with patch.object(claude_bridge.os, 'killpg', killpg_then_cancel):
                            with self.assertRaises(BaseException) as ctx:
                                claude_bridge.throwaway_copy(self.repo, head, diff, copy, timeout=0.3)
                        self.assertNotIsInstance(ctx.exception, claude_bridge.BridgeError,
                                                 'the cancel was never raised: %s' % ctx.exception)
                    finally:
                        agent_process.restore(previous)
                    time.sleep(0.2)
                    child = int(pid_file.read_text())
                    with self.assertRaises(ProcessLookupError, msg='a child outlived the cancel during cleanup'):
                        os.kill(child, 0)
        finally:
            os.environ['PATH'] = old_path

    def test_a_temporary_directory_inside_the_repository_is_refused_and_git_is_fenced(self):
        # A copy made under a TMPDIR inside the checkout has the repository above it: a
        # `git reset --hard` in the copy reset the owner's work. Both adapters refuse such a
        # TMPDIR before the copy is made, and the reviewer's git is fenced at the copy's parent.
        import claude_bridge
        inside = self.repo / 'build' / 'tmp'
        inside.mkdir(parents=True)
        with (self.repo / '.gitignore').open('a') as ignore:
            ignore.write('build/\n')
        self.install_wrapper()
        self.commit_fixture('A clean HEAD')
        (self.repo / 'file.py').write_text('uncommitted work\n')
        old = os.environ.get('TMPDIR')
        os.environ['TMPDIR'] = str(inside)
        tempfile.tempdir = None
        try:
            with self.assertRaises(claude_bridge.BridgeError) as ctx:
                claude_bridge.review_tmpdir(self.repo)
            self.assertIn('inside the reviewed repository', str(ctx.exception))
            code, result = self.run_bridge()
            # Recorded since v0.11: evidence and a usage record, as a copy that was never made.
            self.assertEqual((code, result['failure_kind']), (5, 'copy_failed'), result)
            self.assertIn('inside the reviewed repository', result['error'])
            self.assertTrue(Path(result['usage_record']).is_file())
            outcome = self.run_wrapper('--reviewer', 'codex', REVIEW_CLI_BIN=str(self.build_fake_codex()),
                                       REVIEW_CODEX_MODEL='fixture-codex-model', TMPDIR=str(inside))
            self.assertNotEqual(outcome.returncode, 0)
            self.assertIn('inside the reviewed repository', outcome.stdout + outcome.stderr)
        finally:
            if old is None:
                os.environ.pop('TMPDIR', None)
            else:
                os.environ['TMPDIR'] = old
            tempfile.tempdir = None
        self.assertEqual((self.repo / 'file.py').read_text(), 'uncommitted work\n')
        # The fence: a git run by the reviewer in a copy that sits inside some checkout finds
        # no repository (GIT_CEILING_DIRECTORIES at the copy's parent).
        import agent_process
        copy = self.repo / 'build' / 'copy'
        copy.mkdir()
        execution = agent_process.run(['git', 'rev-parse', '--show-toplevel'], '', copy, 30)
        self.assertNotEqual(execution['exit_code'], 0, execution)

    def committed_probe(self, smudge):
        # A committed file whose smudge filter runs when git archive writes it, as LFS's does.
        (self.repo / '.gitattributes').write_text('probe.txt filter=probe\n')
        (self.repo / 'probe.txt').write_text('stored\n')
        self.commit_fixture('probe')
        self.git('config', 'filter.probe.smudge', smudge)
        self.git('config', 'filter.probe.required', 'true')
        return Path(tempfile.mkdtemp(dir=self.root))

    def test_a_failed_git_archive_names_git_s_message_first(self):
        # #246: git archive's stderr went to DEVNULL, so a failed LFS smudge read as a tar error.
        import claude_bridge
        copy = self.committed_probe('echo probe smudge failed >&2; exit 1')
        with self.assertRaises(claude_bridge.BridgeError) as caught:
            claude_bridge.throwaway_copy(self.repo, 'HEAD', None, copy)
        message = str(caught.exception)
        self.assertIn('probe smudge failed', message)
        self.assertRegex(message, r'^could not copy HEAD for the reviewer: git archive exited \d+: ')

    def test_a_committed_copy_follows_the_owners_git_lfs_skip_smudge(self):
        # #247 (lead decision): the committed copy keeps the checkout's LFS form, so the owner's
        # GIT_LFS_SKIP_SMUDGE=1 reaches git archive; dropped, every review fetched LFS objects.
        import claude_bridge
        from unittest.mock import patch
        copy = self.committed_probe('printf "skip=%s" "$GIT_LFS_SKIP_SMUDGE"')
        with patch.dict(os.environ, GIT_LFS_SKIP_SMUDGE='1'):
            claude_bridge.throwaway_copy(self.repo, 'HEAD', None, copy)
        self.assertEqual((copy / 'probe.txt').read_text(), 'skip=1')

    def test_tar_reads_no_option_from_the_environment_and_a_proposal_ignores_tmpdir(self):
        import claude_bridge
        self.install_wrapper()
        self.commit_fixture('A clean HEAD')
        head = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        os.environ['TAR_OPTIONS'] = '--exclude=file.py'
        try:
            copy = Path(tempfile.mkdtemp(dir=self.root))
            claude_bridge.throwaway_copy(self.repo, head, None, copy)
            self.assertTrue((copy / 'file.py').exists(), 'TAR_OPTIONS dropped a source file from the copy')
        finally:
            del os.environ['TAR_OPTIONS']
        # A proposal runs in the checkout and makes no copy: a TMPDIR inside the repository
        # is no reason to refuse it.
        inside = self.repo / 'build' / 'tmp'
        inside.mkdir(parents=True)
        with (self.repo / '.gitignore').open('a') as ignore:
            ignore.write('build/\n')
        self.commit_fixture('Ignore build')
        old = os.environ.get('TMPDIR')
        os.environ['TMPDIR'] = str(inside)
        tempfile.tempdir = None
        try:
            code, result = self.run_bridge(extra=['--mode', 'propose', '--commit', 'HEAD'])
            self.assertNotIn('inside the reviewed repository', json.dumps(result))
            # The attribute reads of a snapshot write nothing under that TMPDIR either (r8): the
            # index each one reads a commit into is seen while it is in use, not after.
            from unittest.mock import patch
            import claude_bridge
            real, indexes = claude_bridge.git, []

            def recording(repo, *args, **kwargs):
                if args[:1] == ('read-tree',):
                    indexes.append(Path(kwargs['env']['GIT_INDEX_FILE']).resolve())
                return real(repo, *args, **kwargs)
            with patch.object(claude_bridge, 'git', recording):
                for scope, reference in (('uncommitted', None), ('commit', 'HEAD'), ('base', 'HEAD~1')):
                    claude_bridge.snapshot(self.repo, scope, reference)
            self.assertTrue(indexes)
            for index in indexes:
                self.assertNotIn(inside.resolve(), index.parents, index)
                self.assertIn((self.repo / '.git').resolve(), index.parents, index)
        finally:
            if old is None:
                os.environ.pop('TMPDIR', None)
            else:
                os.environ['TMPDIR'] = old
            tempfile.tempdir = None

    def test_a_staging_change_by_the_reviewer_makes_the_review_stale(self):
        # The fingerprint covered the working files and HEAD, not the index: a reviewer's
        # `git reset --mixed` unstaged the owner's work and the review still completed.
        import claude_bridge
        (self.repo / 'file.py').write_text('staged\n')
        self.git('add', 'file.py')
        before = claude_bridge.snapshot(self.repo, 'uncommitted', None)[1]
        self.git('reset', '-q', '--mixed', 'HEAD')
        self.assertEqual((self.repo / 'file.py').read_text(), 'staged\n')
        after = claude_bridge.snapshot(self.repo, 'uncommitted', None)[1]
        self.assertNotEqual(before, after, 'an index-only change left the fingerprint unchanged')
        # And the reviewer's environment names the repository through no variable at all,
        # CLAUDE_PROJECT_DIR included.
        import agent_process
        os.environ['CLAUDE_PROJECT_DIR'] = str(self.repo)
        os.environ['REVIEW_DISPOSITIONS'] = str(self.repo / 'docs/dispositions.md')
        try:
            execution = agent_process.run(['sh', '-c', 'env'], '', self.root, 30)
        finally:
            del os.environ['CLAUDE_PROJECT_DIR']
            del os.environ['REVIEW_DISPOSITIONS']
        self.assertNotIn('CLAUDE_PROJECT_DIR', execution['stdout'])
        self.assertNotIn('REVIEW_DISPOSITIONS', execution['stdout'])

    def test_a_sparse_checkout_is_reviewable_and_a_present_skip_worktree_file_is_not(self):
        # A sparse checkout marks every path outside its cone skip-worktree, so every such
        # repository was refused. An ABSENT skip-worktree file can hide no change; a PRESENT
        # one still can and is still refused.
        import claude_bridge
        (self.repo / 'src').mkdir(exist_ok=True)
        (self.repo / 'src/a.txt').write_text('a\n')
        self.commit_fixture('A tree with two folders')
        self.git('sparse-checkout', 'set', 'docs')
        self.assertFalse((self.repo / 'src/a.txt').exists())
        (self.repo / 'docs').mkdir(exist_ok=True)
        (self.repo / 'docs/new.md').write_text('new\n')
        head, fingerprint, diff, _ = claude_bridge.snapshot(self.repo, 'uncommitted', None)
        self.assertIn('docs/new.md', diff)
        self.assertNotIn('src/a.txt', diff)
        self.git('sparse-checkout', 'disable')
        self.git('update-index', '--skip-worktree', 'src/a.txt')
        (self.repo / 'src/a.txt').write_text('HIDDEN\n')
        with self.assertRaises(claude_bridge.BridgeError):
            claude_bridge.snapshot(self.repo, 'uncommitted', None)
        # Outside sparse mode an ABSENT skip-marked file is a deletion the diff would not
        # show: refused as well.
        (self.repo / 'src/a.txt').unlink()
        with self.assertRaises(claude_bridge.BridgeError):
            claude_bridge.snapshot(self.repo, 'uncommitted', None)

    def test_a_skip_worktree_file_deleted_inside_the_sparse_rules_is_refused(self):
        # Issue #53 (REPRODUCED): with sparse mode on, every absent skip-marked file was
        # tolerated, so a file inside the cone marked by hand and deleted was a deletion the
        # diff omitted. Only a path the sparse rules exclude may be absent, in cone mode and
        # non-cone mode alike; without `check-rules` (Git before 2.41) the scope is refused.
        import claude_bridge
        from unittest.mock import patch
        (self.repo / 'src').mkdir(exist_ok=True)
        (self.repo / 'src/a.txt').write_text('a\n')
        (self.repo / 'docs/kept.md').write_text('kept\n')
        self.commit_fixture('A tree with two folders')
        # The real-Git subtests need `check-rules` (Git 2.41); the usage line names it when present.
        usage = subprocess.run(['git', 'sparse-checkout', '-h'], capture_output=True, text=True)
        if 'check-rules' in usage.stdout + usage.stderr:
            for rules in (['docs'], ['--no-cone', '/*', '!/src/']):
                with self.subTest(rules=rules):
                    self.git('sparse-checkout', 'set', *rules)
                    self.assertFalse((self.repo / 'src/a.txt').exists())
                    claude_bridge.snapshot(self.repo, 'uncommitted', None)
                    self.git('update-index', '--skip-worktree', 'docs/kept.md')
                    (self.repo / 'docs/kept.md').unlink()
                    with self.assertRaisesRegex(claude_bridge.BridgeError, 'inside the sparse-checkout rules.*docs/kept.md'):
                        claude_bridge.snapshot(self.repo, 'uncommitted', None)
                    self.git('update-index', '--no-skip-worktree', 'docs/kept.md')
                    self.git('checkout', '--', 'docs/kept.md')
        else:
            sys.stderr.write('\nNOT RUN: %s, the real-Git subtests (this Git has no `sparse-checkout '
                             'check-rules`; it needs Git 2.41 or later)\n' % self.id())
            self.git('sparse-checkout', 'set', 'docs')
        real = claude_bridge.git

        def old_git(repo, *args, **kwargs):
            if args[:2] == ('sparse-checkout', 'check-rules'):
                raise claude_bridge.BridgeError("git sparse-checkout failed: error: unknown subcommand: `check-rules'")
            return real(repo, *args, **kwargs)
        with patch.object(claude_bridge, 'git', old_git), \
                self.assertRaisesRegex(claude_bridge.BridgeError, r'Git 2\.41 or later'):
            claude_bridge.snapshot(self.repo, 'uncommitted', None)
        self.git('sparse-checkout', 'disable')

    @posix_only
    def test_fixture_launchers_run_under_an_interpreter_path_with_a_space(self):
        # A shebang cannot quote: an interpreter under a directory with a space never ran
        # the fixtures. The launcher is sh, which execs the quoted path.
        with tempfile.TemporaryDirectory() as tmp:
            link_dir = Path(tmp) / 'review python env'
            link_dir.mkdir()
            link = link_dir / 'python'
            os.symlink(sys.executable, link)
            script = Path(tmp) / 'fixture'
            script.write_text(("#!/bin/sh\n\'\'\':\'\nexec %s \"$0\" \"$@\"\n\'\'\'\n" % shlex.quote(str(link)))
                              + 'import sys\nprint("ran under", sys.executable)\n')
            script.chmod(0o755)
            result = subprocess.run([str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('ran under', result.stdout)
            self.assertTrue(PYTHON_SHEBANG.startswith('#!/bin/sh\n'), PYTHON_SHEBANG)

    @posix_only
    def test_sparse_mode_is_read_through_git_s_boolean_and_a_cancel_during_reap_orphans_nothing(self):
        import claude_bridge
        import agent_process
        from unittest.mock import patch
        (self.repo / 'src').mkdir(exist_ok=True)
        (self.repo / 'src/a.txt').write_text('a\n')
        self.commit_fixture('Two folders')
        self.git('sparse-checkout', 'set', 'docs')
        self.git('config', 'core.sparseCheckout', 'yes')  # git reads yes/on/1 as true
        (self.repo / 'docs').mkdir(exist_ok=True)
        (self.repo / 'docs/new.md').write_text('new\n')
        head, _, diff, _ = claude_bridge.snapshot(self.repo, 'uncommitted', None)
        self.assertIn('docs/new.md', diff)
        self.git('sparse-checkout', 'disable')
        # A cancel SENT during the first helper's stop (a raising guard armed, as the Codex
        # adapter's) is delivered only once both helpers are stopped and reaped: the two
        # reaps run under one blocked mask, and the mark is set after the stop.
        pid_file = self.root / 'desc.pid'
        bin_dir = self.root / 'bin-reap'
        bin_dir.mkdir()
        (bin_dir / 'tar').write_text('#!/bin/sh\ncat > /dev/null\n(sleep 30 & echo $! > %s; wait)\n' % pid_file)
        (bin_dir / 'tar').chmod(0o755)
        real_stop = agent_process.stop_group
        state = {'sent': False}

        def stop_then_cancel(child, pgid):
            real_stop(child, pgid)
            if not state['sent']:
                state['sent'] = True
                send_cancel(signal.SIGTERM)  # pending while blocked
        old_path = os.environ['PATH']
        os.environ['PATH'] = str(bin_dir) + os.pathsep + old_path
        guard = agent_process.OneShot()
        previous = agent_process.hold(guard)
        try:
            copy = Path(tempfile.mkdtemp(dir=self.root))
            with patch.object(agent_process, 'stop_group', side_effect=stop_then_cancel):
                with self.assertRaises(KeyboardInterrupt):
                    claude_bridge.throwaway_copy(self.repo, head, None, copy, timeout=5)
            time.sleep(0.2)
            descendant = int(pid_file.read_text())
            with self.assertRaises(ProcessLookupError, msg='a descendant outlived the cancelled reap'):
                os.kill(descendant, 0)
        finally:
            agent_process.restore(previous)
            os.environ['PATH'] = old_path

    def test_dispositions_are_claims_the_reviewer_verifies_not_settlements(self):
        # The author never approves its own work: a disproved finding counts only once the
        # reviewer has checked it, and a deferred one stays open, so it cannot end in Accept.
        log = self.root / 'prompt.txt'
        task = {'PROMPT_LOG': str(log), 'MYAGENTKIT_TASK_ID': 'claims-task'}
        self.assertEqual(self.run_bridge('reject', env_extra=task)[0], 0)
        notes = self.root / 'dispositions.md'
        # UTF-8 whatever the host's code page: the bridge once read it in cp1252 and refused.
        notes.write_text('file.py:1 deferred: to the owner (Şimdi ❌).\n', encoding='utf-8')
        code, result = self.run_bridge(env_extra=dict(task, REVIEW_DISPOSITIONS=str(notes)))
        self.assertEqual(code, 0, result)
        prompt = ' '.join(log.read_text(encoding='utf-8').split())
        self.assertIn('Şimdi ❌', prompt)
        for wording in ("the author's claims to verify",
                        'counts only after you have checked it against the code',
                        'Report new Critical or High findings only',
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
                                    ('head', '0' * 40, 'not an ancestor of HEAD')):
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
                       json.dumps(no_head), no_evidence, 'directory'):
            with self.subTest(damage=damage):
                # A directory fails the read for every user, root included. Mode 000 does not
                # stop root, and a case that cannot run under root is not a pass there.
                if damage == 'directory':
                    record.unlink()
                    record.mkdir()
                else:
                    record.write_text(damage)
                try:
                    code, refused = self.run_bridge(env_extra=task)
                finally:
                    if record.is_dir():
                        record.rmdir()
                    record.write_text(original)
                self.assertEqual(code, 2, refused)
                self.assertIn(str(record), refused['error'])
                # Every labelled round reads every record, so a new label meets it again.
                self.assertIn('set it aside', refused['error'])
        self.assertEqual(self.run_bridge(env_extra=task)[0], 0)

    def test_a_legacy_record_with_an_empty_task_id_is_set_aside_by_the_command_named(self):
        # v0.7 and v0.8 recorded "id": "" when MYAGENTKIT_TASK_ID was exported empty. v0.9
        # refuses such a record as damaged, and since every wrapper run is labelled, every
        # review stopped after the upgrade. The refusal stays; its message is the way out.
        code, first = self.run_bridge('reject', env_extra={'MYAGENTKIT_TASK_ID': 'old-task'})
        self.assertEqual(code, 0, first)
        record = Path(first['usage_record'])
        legacy = json.loads(record.read_text())
        legacy['task']['id'] = ''
        legacy['task'].pop('resolved', None)
        record.write_text(json.dumps(legacy))
        task = {'MYAGENTKIT_TASK_ID': 'new-task'}
        code, refused = self.run_bridge(env_extra=task)
        self.assertEqual(code, 2, refused)
        self.assertIn(str(record), refused['error'])
        self.assertIn('v0.7 or v0.8', refused['error'])
        command = refused['error'].rsplit('): ', 1)[1]
        subprocess.run(['sh', '-c', command], check=True)
        self.assertFalse(record.exists())
        self.assertTrue((self.repo / '.myagentkit/usage-set-aside' / record.name).is_file())
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

    @posix_only
    def test_the_cancel_cases_pass_under_a_caller_that_ignores_sigint(self):
        # Started as a `&` job of a non-interactive shell or under nohup, the self-test
        # inherited an ignored SIGINT and these cases failed, pointing at the review tooling
        # rather than at the caller. They run here under exactly such a caller.
        result = subprocess.run(
            [sys.executable, '-B', '-m', 'unittest',
             'test_claude_bridge.BridgeTests.test_cancelled_review_stops_the_reviewer_records_usage_and_never_fails_over',
             'test_claude_bridge.BridgeTests.test_a_cancel_while_codex_restores_its_handlers_is_persisted_for_a_failed_attempt',
             'test_claude_bridge.BridgeTests.test_a_second_cancel_inside_the_handler_restoration_leaves_the_records_cancelled'],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN))
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])

    def test_an_unlistable_usage_directory_stops_a_labelled_round(self):
        # Path.glob() swallows a listing error: a usage directory the owner can write but not
        # list (mode 0300) read as "no earlier rounds" and the next round looked fresh. Mode
        # 0300 does not stop root, so the listing fails here the way it does for every user:
        # a file where the directory is expected.
        task = {'MYAGENTKIT_TASK_ID': 'unlistable-task'}
        code, first = self.run_bridge('reject', env_extra=task)
        self.assertEqual(code, 0, first)
        usage = Path(first['usage_record']).parent
        kept = usage.with_name('usage.kept')
        usage.rename(kept)
        usage.write_text('not a directory\n')
        try:
            code, refused = self.run_bridge(env_extra=task)
        finally:
            usage.unlink()
            kept.rename(usage)
        self.assertEqual(code, 2, refused)
        self.assertIn(str(usage), refused['error'])
        self.assertIn('cannot be listed', refused['error'])
        self.assertEqual(self.run_bridge(env_extra=task)[0], 0)

    def test_a_label_continues_over_a_fix_commit_in_every_scope(self):
        # #119: a --commit or --uncommitted round 2 over the fix commit was refused as "another
        # change", so the lead took a new label and the count restarted. Like --base, a round on
        # top of the earlier round's head continues the label, and the third is refused; an
        # amend leaves the earlier head off HEAD's line and still needs a new label.
        commit = lambda *args: self.git(
            '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-qa', *args)
        for scope in (('--uncommitted',), ('--commit', 'HEAD')):
            with self.subTest(scope=scope):
                task = {'MYAGENTKIT_TASK_ID': 'fix-%s-task' % scope[0].strip('-')}
                if scope[0] == '--commit':
                    commit('-m', 'A')
                code, first = self.run_bridge('reject', extra=scope, env_extra=task)
                self.assertEqual(code, 0, first)
                for text in ('fixed', 'fixed again'):
                    if scope[0] == '--uncommitted':
                        commit('-m', 'reviewed')
                    (self.repo / 'file.py').write_text(text)
                    if scope[0] == '--commit':
                        commit('-m', 'fix')
                    code, result = self.run_bridge(extra=scope, env_extra=task)
                    if text == 'fixed':
                        self.assertEqual(code, 0, result)
                self.assertEqual(code, 2, result)
                self.assertIn('already has 2 completed rounds', result['error'])
        task = {'MYAGENTKIT_TASK_ID': 'amended-task'}
        code, first = self.run_bridge('reject', extra=('--commit', 'HEAD'), env_extra=task)
        self.assertEqual(code, 0, first)
        (self.repo / 'file.py').write_text('amended')
        commit('--amend', '-m', 'amended')
        code, refused = self.run_bridge(extra=('--commit', 'HEAD'), env_extra=task)
        self.assertEqual(code, 2, refused)
        self.assertIn('new task label', refused['error'])

    def linked_worktree(self):
        # A worker's worktree as spawn_worker.sh makes it: inside the main checkout, ignored there.
        self.git('checkout', '--', 'file.py')
        linked = self.repo / '.claude/worktrees/worker'
        self.git('worktree', 'add', '-q', str(linked), '-b', 'worktree-worker')
        return linked

    def commit_in(self, tree, *args):
        subprocess.run(['git', '-C', str(tree), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                        '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-q', *args],
                       check=True, capture_output=True)

    def test_a_round_in_a_linked_worktree_is_recorded_in_the_main_checkout(self):
        # #293: a worker's round in its worktree left its records there, where the lead's
        # checkout never read them and `git worktree remove` deleted them.
        linked = self.linked_worktree()
        (linked / 'file.py').write_text('worker change\n')
        main = self.repo.resolve()
        code, result = self.run_bridge('reject', env_extra={'MYAGENTKIT_TASK_ID': 'linked-task'}, repo=linked)
        self.assertEqual(code, 0, result)
        self.assertEqual(Path(result['evidence']).parent, main / 'docs/reviews')
        self.assertEqual(Path(result['usage_record']).parent, main / '.myagentkit/usage')
        record = json.loads(Path(result['usage_record']).read_text(encoding='utf-8'))
        self.assertEqual(record['task']['tree'], str(linked.resolve()))
        self.assertEqual(record['task']['files'], ['file.py'])
        self.assertFalse((linked / '.myagentkit').exists())
        self.assertFalse((linked / 'docs/reviews').exists())
        dispatched = subprocess.run(
            [sys.executable, '-B', str(ROOT / 'review_dispatch.py'), '--repo', str(linked), '--reviewer', 'claude',
             '--claude-model', 'claude-opus-5', '--uncommitted'],
            env=self.review_env(CLAUDE_CLI_BIN=str(self.fixture), MYAGENTKIT_TASK_ID='linked-dispatch'),
            capture_output=True, text=True)
        self.assertEqual(dispatched.returncode, 0, dispatched.stdout + dispatched.stderr)
        chain = json.loads(next(line.removeprefix('review dispatch: ') for line in dispatched.stdout.splitlines()
                                if line.startswith('review dispatch: ')))
        self.assertEqual(Path(chain['chain_record']).parent, main / '.myagentkit/usage/chains')
        self.assertEqual(chain['tree'], str(linked.resolve()))
        self.assertFalse((linked / '.myagentkit').exists())

    def test_a_commit_round_continues_an_uncommitted_round_once_its_files_are_committed(self):
        # #293: round 1 --uncommitted in the worker's worktree, the fix merged, round 2 --commit of
        # the merge in the main checkout under the same label was refused ("use a new task label").
        # It continues when every file round 1 reviewed is in the commit's diff; else it is refused
        # with the files that are not.
        linked = self.linked_worktree()
        merge = lambda message: subprocess.run(
            ['git', '-C', str(self.repo), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
             '-c', 'core.hooksPath=/dev/null', 'merge', '-q', '--no-ff', '-m', message, 'worktree-worker'],
            check=True, capture_output=True)
        partial = {'MYAGENTKIT_TASK_ID': 'partial-task'}
        (linked / 'file.py').write_text('first\n')
        (linked / 'other.py').write_text('left out\n')
        code, first = self.run_bridge('reject', env_extra=partial, repo=linked)
        self.assertEqual(code, 0, first)
        subprocess.run(['git', '-C', str(linked), 'add', 'file.py'], check=True, capture_output=True)
        self.commit_in(linked, '-m', 'file only')
        merge('merge file only')
        code, refused = self.run_bridge(extra=('--commit', 'HEAD'), env_extra=partial)
        self.assertEqual(code, 2, refused)
        self.assertIn('other.py', refused['error'])
        self.assertIn('new task label', refused['error'])
        (linked / 'other.py').unlink()
        task = {'MYAGENTKIT_TASK_ID': 'merged-task'}
        (linked / 'file.py').write_text('second\n')
        code, first = self.run_bridge('reject', env_extra=task, repo=linked)
        self.assertEqual(code, 0, first)
        round_one = json.loads(Path(first['usage_record']).read_text(encoding='utf-8'))['task']['head']
        (linked / 'file.py').write_text('second, fixed\n')
        self.commit_in(linked, '-am', 'fix')
        merge('merge fix')
        merged = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        code, second = self.run_bridge(extra=('--commit', 'HEAD'), env_extra=task)
        self.assertEqual(code, 0, second)
        record = json.loads(Path(second['usage_record']).read_text(encoding='utf-8'))
        self.assertEqual(record['task']['continues'], {'scope': 'uncommitted', 'tree': str(linked.resolve()),
                                                       'head': round_one, 'commit': merged})
        self.assertIn('continues its --uncommitted round', self.stderr)

    def test_evidence_left_in_a_removed_worktree_is_read_from_its_copy_in_the_main_checkout(self):
        # #293: a record written before v0.13 in a worktree names its archive there; after the
        # worktree is removed, the copy under the main checkout is read, by its name.
        task = {'MYAGENTKIT_TASK_ID': 'removed-task', 'REVIEW_ROUND_EXCEPTION': 'fixture: several reads'}
        code, first = self.run_bridge('reject', env_extra=task)
        self.assertEqual(code, 0, first)
        archive = Path(first['evidence'])
        record = Path(first['usage_record'])
        value = json.loads(record.read_text(encoding='utf-8'))
        value['evidence'] = str(self.root / 'removed-worktree/docs/reviews' / archive.name)
        record.write_text(json.dumps(value), encoding='utf-8')
        code, result = self.run_bridge(env_extra=task)
        self.assertEqual(code, 0, result)
        self.assertIn('using its copy %s' % archive.resolve(), self.stderr)
        usage_copy = record.parent / archive.name
        archive.rename(usage_copy)
        code, result = self.run_bridge(env_extra=task)
        self.assertEqual(code, 0, result)
        self.assertIn('using its copy %s' % usage_copy.resolve(), self.stderr)
        usage_copy.unlink()
        code, refused = self.run_bridge(env_extra=task)
        self.assertEqual(code, 2, refused)
        self.assertIn('is missing', refused['error'])

    def test_a_carried_base_round_must_be_an_ancestor_of_head(self):
        # A --base round is carried while the branch grows on top of it; after a rebase or an
        # amend its head is no ancestor of HEAD, and its findings are about another change.
        commit = lambda *args: self.git(
            '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-qa', *args)
        self.git('branch', 'review-base')
        commit('-m', 'X')
        task, base = {'MYAGENTKIT_TASK_ID': 'base-task'}, ('--base', 'review-base')
        code, first = self.run_bridge('reject', extra=base, env_extra=task)
        self.assertEqual(code, 0, first)
        (self.repo / 'file.py').write_text('Y\n')
        commit('-m', 'Y')
        code, carried = self.run_bridge(extra=base, env_extra=task)
        self.assertEqual(code, 0, carried)
        commit('--amend', '-m', 'Y amended')
        code, refused = self.run_bridge(extra=base, env_extra=task)
        self.assertEqual(code, 2, refused)
        self.assertIn('not an ancestor of HEAD', refused['error'])

    def test_a_round_two_over_the_fix_commits_keeps_the_label_and_the_count(self):
        # Lead-found: round 2 with --base at round 1's head (the fix commits only) was refused
        # under the round-1 label, so leads took a new label, and that restarted the count.
        commit = lambda *args: self.git(
            '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-qa', *args)
        head = lambda: self.git('rev-parse', 'HEAD').stdout.decode().strip()
        self.git('branch', 'review-base')
        commit('-m', 'X')
        task = {'MYAGENTKIT_TASK_ID': 'fix-task'}
        code, first = self.run_bridge('reject', extra=('--base', 'review-base'), env_extra=task)
        self.assertEqual(code, 0, first)
        round_one = head()
        (self.repo / 'file.py').write_text('fixed\n')
        commit('-m', 'fix')
        code, second = self.run_bridge(extra=('--base', round_one), env_extra=task)
        self.assertEqual(code, 0, second)
        round_two = head()
        (self.repo / 'file.py').write_text('fixed again\n')
        commit('-m', 'fix again')
        code, third = self.run_bridge(extra=('--base', round_two), env_extra=task)
        self.assertEqual(code, 2, third)
        self.assertIn('fix-task already has 2 completed rounds', third['error'])

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
        notes.write_text('deferred: ' + 'x' * 400_000)
        code, refused = self.run_bridge(env_extra=dict(task, REVIEW_DISPOSITIONS=str(notes)))
        self.assertEqual(code, 2, refused)
        self.assertIn('400000 bytes', refused['error'])
        self.assertIn('fresh MYAGENTKIT_TASK_ID', refused['error'])

    def test_renamed_source_cannot_borrow_a_vendor_path_from_the_old_name(self):
        old = self.repo / 'old b/vendor/lib.py'
        old.parent.mkdir(parents=True)
        old.write_text('x' * 410_000 + '\nold\n')
        self.commit_fixture('Ambiguous old pathname')
        new = self.repo / 'src/big.py'
        new.parent.mkdir()
        old.rename(new)
        new.write_text('x' * 410_000 + '\nnew\n')
        self.git('add', '-A')
        diff = self.git('diff', '--cached').stdout
        self.assertGreater(bridge.budgeted(diff)[0], bridge.DIFF_LIMIT)
        with self.assertRaisesRegex(bridge.BridgeError, '400000 bytes'):
            bridge.snapshot(self.repo, 'uncommitted', None)

    def test_unreadable_diff_paths_stay_in_the_budget(self):
        for header in (b'diff --git a/old b/vendor/lib.py b/src/real.py',
                       b'diff --git a/vendor/lib.py b/vendor/lib.py'):
            diff = header + b'\n@@ -1 +1 @@\n-old\n+new\n'
            with self.subTest(header=header):
                self.assertEqual(bridge.budgeted(diff), (len(diff), 2))

    def test_a_deleted_file_is_budgeted_by_its_old_path(self):
        # A deletion has "+++ /dev/null": its path comes from "--- a/", so a deleted vendored
        # file spends no budget while a deleted source file still does.
        for name, refused in (('vendor/lib.js', False), ('src/big.py', True)):
            with self.subTest(name=name):
                path = self.repo / name
                path.parent.mkdir(exist_ok=True)
                path.write_text('x' * 410_000 + '\n')
                self.commit_fixture('Add ' + name)
                self.git('rm', '-q', name)
                diff = self.git('diff', '--cached').stdout
                self.assertIn(b'+++ /dev/null', diff)
                if not refused:
                    self.assertEqual(bridge.budgeted(diff), (0, 0))
                with self.assertRaisesRegex(bridge.BridgeError, '400000 bytes'):
                    bridge.snapshot(self.repo, 'uncommitted', None)
                self.commit_fixture('Remove ' + name)

    def test_author_documentation_describes_the_author_tier_refusal(self):
        # KARARLAR B01 (1): the docs say what review_dispatch now does with MYAGENTKIT_AUTHOR.
        gate = ' '.join((ROOT.parent / 'docs/REVIEW_GATE.md').read_text(encoding='utf-8').split())
        running = ' '.join((ROOT.parent / 'docs/REVIEW_RUNNING.md').read_text(encoding='utf-8').split())
        self.assertIn("`scripts/review.sh` then refuses a reviewer pin of the author's tier", gate)
        self.assertNotIn("does not exclude the author's tier automatically", gate)
        self.assertIn("a reviewer pin of the author's tier is refused with exit 2", running)
        self.assertNotIn('`MYAGENTKIT_AUTHOR` is not read or recorded', running)

    def test_capacity_documentation_says_what_the_dispatcher_retries(self):
        # KARARLAR B01 (6): the sentence batch 3 took out until the retry existed (RESULT-b3fix.md).
        import review_dispatch
        running = ' '.join((ROOT.parent / 'docs/REVIEW_RUNNING.md').read_text(encoding='utf-8').split())
        self.assertIn('A Codex capacity error is transient and is retried: after the delay the tool '
                      'reports, otherwise after about ten minutes, doubled, at most twice', running)
        self.assertIn('A quota or spend-cap error is never retried', running)
        self.assertNotIn('The dispatcher does not retry that reviewer automatically', running)
        self.assertEqual((review_dispatch.CAPACITY_RETRY_SECONDS, review_dispatch.CAPACITY_RETRIES), (600, 2))
        self.assertIn('`authentication`) is fixed, never failed over', running)

    def test_unsetting_focus_cannot_open_a_third_round(self):
        # After logic r1 and r2, an unset focus takes the highest count, so leaving the focus out
        # never opens a fresh budget; a new named focus starts its own count (#102, test below).
        from unittest.mock import patch
        task = {'MYAGENTKIT_TASK_ID': 'focus-limit', 'REVIEW_FOCUS': 'logic'}
        for _ in range(2):
            code, result = self.run_bridge('reject', env_extra=task)
            self.assertEqual(code, 0, result)
        head = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        for focus in (None, 'logic'):
            with self.subTest(focus=focus), patch.dict(os.environ):
                os.environ.pop('REVIEW_FOCUS', None)
                if focus:
                    os.environ['REVIEW_FOCUS'] = focus
                with self.assertRaisesRegex(bridge.BridgeError, 'REVIEW_ROUND_EXCEPTION'):
                    bridge.prior_rounds(self.repo, task['MYAGENTKIT_TASK_ID'], 'uncommitted', None, head, '')
                os.environ['REVIEW_ROUND_EXCEPTION'] = 'Owner requested another pass'
                carried, measured = bridge.prior_rounds(self.repo, task['MYAGENTKIT_TASK_ID'], 'uncommitted',
                                                        None, head, '')
                self.assertEqual('### Round ' in carried, focus == 'logic')
                self.assertEqual(measured['round_exception'], 'Owner requested another pass')

    def test_a_new_focus_after_another_used_both_rounds_starts_its_own_count(self):
        # #102/#248 (owner decision 67): the high tier's sequential order, logic r1, logic r2,
        # then portability, gives portability its own round 1 and round 2; its third is refused.
        log = self.root / 'prompt.txt'
        base = {'PROMPT_LOG': str(log), 'MYAGENTKIT_TASK_ID': 'sequential-focus'}
        logic, portability = dict(base, REVIEW_FOCUS='logic'), dict(base, REVIEW_FOCUS='portability')
        for _ in range(2):
            code, result = self.run_bridge('reject', env_extra=logic)
            self.assertEqual(code, 0, result)
        code, first = self.run_bridge('reject', env_extra=portability)
        self.assertEqual(code, 0, first)
        self.assertNotIn('### Round', log.read_text())
        code, second = self.run_bridge('accept', env_extra=portability)
        self.assertEqual(code, 0, second)
        self.assertIn('This is review round 2', log.read_text())
        self.assertEqual(log.read_text().count('### Round '), 1, log.read_text())
        code, refused = self.run_bridge(env_extra=portability)
        self.assertEqual(code, 2, refused)
        self.assertIn('REVIEW_ROUND_EXCEPTION', refused['error'])
        # A made-up focus name opens no fresh budget: only the named foci exist.
        code, refused = self.run_bridge(env_extra=dict(base, REVIEW_FOCUS='logic-2'))
        self.assertEqual(code, 2, refused)
        self.assertIn('REVIEW_FOCUS must be one of', refused['error'])

    def test_legacy_rounds_are_carried_and_counted_when_focus_is_added(self):
        # A round without a focus counts toward every focus, a new one included (#248 case 3).
        log = self.root / 'prompt.txt'
        task = {'MYAGENTKIT_TASK_ID': 'legacy-focus', 'PROMPT_LOG': str(log)}
        self.assertEqual(self.run_bridge('reject', env_extra=task)[0], 0)
        code, result = self.run_bridge('accept', env_extra=dict(task, REVIEW_FOCUS='logic'))
        self.assertEqual(code, 0, result)
        self.assertIn('### Round 1', log.read_text())
        self.assertIn('concrete defect', log.read_text())
        code, result = self.run_bridge('accept', env_extra=dict(task, REVIEW_FOCUS='portability'))
        self.assertEqual(code, 0, result)
        self.assertIn('This is review round 2', log.read_text())
        self.assertEqual(log.read_text().count('### Round '), 1, log.read_text())
        code, result = self.run_bridge(env_extra=dict(task, REVIEW_FOCUS='portability'))
        self.assertEqual(code, 2, result)
        self.assertIn('REVIEW_ROUND_EXCEPTION', result['error'])

    def test_lock_and_vendored_files_spend_no_split_hint_but_obey_the_byte_cap(self):
        # Noise spends no split hint, but every byte sent to the reviewer obeys the hard cap.
        (self.repo / 'package-lock.json').write_text('{"x": "' + 'y' * 410_000 + '"}\n')
        code, result = self.run_bridge()
        self.assertEqual(code, 2, result)
        self.assertIn('400000 bytes', result['error'])
        (self.repo / 'package-lock.json').unlink()
        (self.repo / 'big.py').write_text('z' * 410_000 + '\n')
        code, refused = self.run_bridge()
        self.assertEqual(code, 2, refused)
        self.assertIn('400000 bytes', refused['error'])
        noise = (b'diff --git a/vendor/lib.py b/vendor/lib.py\n+++ b/vendor/lib.py\n@@ -0,0 +1 @@\n+v\n'
                 b'diff --git "a/x y/yarn.lock" "b/x y/yarn.lock"\n+++ "b/x y/yarn.lock"\n@@ -1 +1 @@\n-a\n+b\n')
        code_part = b'diff --git a/file.py b/file.py\n@@ -1 +1 @@\n-original\n+changed\n'
        self.assertEqual(bridge.budgeted(noise + code_part), (len(code_part), 2))

    def test_a_large_diff_gets_a_split_hint_once_before_the_hard_limit(self):
        # KARARLAR B02 inv2#34: a soft "split the task" hint before the byte refusal, printed once
        # per review: by the dispatcher's preflight or a direct adapter, not again inside a chain.
        from contextlib import redirect_stderr
        head = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        big = 'diff --git a/file.py b/file.py\n@@ -0,0 +1,401 @@\n' + '+x\n' * 401
        lock = 'diff --git a/Cargo.lock b/Cargo.lock\n+++ b/Cargo.lock\n@@ -0,0 +1,900 @@\n' + '+x\n' * 900
        for diff, chain, hinted in ((big, None, True), (big, 'a-chain', False), (lock, None, False),
                                    (big[:200], None, False)):
            with self.subTest(diff=diff[:40], chain=chain):
                os.environ.pop('MYAGENTKIT_REVIEW_CHAIN_ID', None)
                if chain:
                    os.environ['MYAGENTKIT_REVIEW_CHAIN_ID'] = chain
                err = io.StringIO()
                with redirect_stderr(err):
                    self.assertEqual(bridge.prior_rounds(self.repo, None, 'uncommitted', None, head, diff)[0], '')
                self.assertEqual('split the task' in err.getvalue(), hinted, err.getvalue())

    def test_both_reviewers_read_one_list(self):
        # KARARLAR B01 inv2#112/#120: one reading list, one constant, for both reviewers;
        # docs/PROJECT.md and docs/PHASES.md join it only for a change to design or phases.
        names = {}
        for adapter in ('claude', 'codex'):
            log = self.root / (adapter + '-prompt.txt')
            if adapter == 'claude':
                code, result = self.run_bridge(env_extra={'PROMPT_LOG': str(log)})
                self.assertEqual(code, 0, result)
            else:
                run = subprocess.run(
                    [sys.executable, '-B', str(ROOT / 'codex_bridge.py'), '--repo', str(self.repo),
                     '--model', 'fixture-codex-model', '--uncommitted'],
                    env=dict(os.environ, REVIEW_CLI_BIN=str(self.build_fake_codex()), PROMPT_LOG=str(log),
                             MYAGENTKIT_DELEGATION_DEPTH='0'), capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            prompt = log.read_text(encoding='utf-8')
            names[adapter] = re.split(r',\s*|\s+and\s+', re.search(r'Read (.*?) first', prompt).group(1))
            self.assertIn('docs/PROJECT.md and docs/PHASES.md', prompt)
        self.assertEqual(names['claude'], list(bridge.REVIEW_DOCS))
        self.assertEqual(names['codex'], names['claude'])

    def test_focus_reviewers_each_get_two_rounds_but_carry_only_their_own_reports(self):
        # KARARLAR B02 inv2#10: rounds count per REVIEW_FOCUS, so a high-tier change's logic and
        # portability reviewers each get round 1 and round 2; a third of either, or an unfocused
        # review after that, needs REVIEW_ROUND_EXCEPTION.
        log = self.root / 'prompt.txt'
        base = {'PROMPT_LOG': str(log), 'MYAGENTKIT_TASK_ID': 'focus-task'}
        logic, portability = dict(base, REVIEW_FOCUS='logic'), dict(base, REVIEW_FOCUS='portability')
        code, first = self.run_bridge('reject', env_extra=logic)
        self.assertEqual(code, 0, first)
        self.assertEqual(json.loads(Path(first['usage_record']).read_text())['task']['focus'], 'logic')
        self.assertEqual(self.run_bridge('reject', env_extra=portability)[0], 0)
        self.assertNotIn('### Round', log.read_text())
        for focus in (logic, portability):
            code, second = self.run_bridge('accept', env_extra=focus)
            self.assertEqual(code, 0, second)
            self.assertEqual(log.read_text().count('### Round '), 1, log.read_text())
            self.assertIn('This is review round 2', log.read_text())
        for env in (logic, portability, base):
            code, refused = self.run_bridge(env_extra=env)
            self.assertEqual(code, 2, refused)
            self.assertIn('REVIEW_ROUND_EXCEPTION', refused['error'])
        exception = {'REVIEW_ROUND_EXCEPTION': 'Owner requested focus follow-up'}
        code, third = self.run_bridge('accept', env_extra=dict(logic, **exception))
        self.assertEqual(code, 0, third)
        self.assertEqual(log.read_text().count('### Round '), 2, log.read_text())
        self.assertIn('This is review round 3', log.read_text())

    def test_dispositions_without_a_key_are_refused_before_any_model_runs(self):
        # Item F: the usage summary counts the author's answers, so a file that answers no
        # finding with fixed: / disproved: / deferred: is refused (exit 2), not silently zero.
        task = {'MYAGENTKIT_TASK_ID': 'keyless-task'}
        self.assertEqual(self.run_bridge('reject', env_extra=task)[0], 0)
        notes = self.root / 'dispositions.md'
        notes.write_text('file.py:1 was fixed in the last commit; file.py:9 is deferred.\n')
        before = set((self.repo / '.myagentkit/usage').glob('*.json'))
        code, refused = self.run_bridge(env_extra=dict(task, REVIEW_DISPOSITIONS=str(notes)))
        self.assertEqual(code, 2, refused)
        self.assertIn('fixed:, disproved: or deferred: key', refused['error'])
        self.assertEqual(set((self.repo / '.myagentkit/usage').glob('*.json')), before)

    def test_disposition_counts_are_recorded_with_the_round_that_carries_them(self):
        # The record keeps the author's counts (case-insensitive keys, one per finding) and
        # a round without dispositions has no such field, so older records read the same.
        task = {'MYAGENTKIT_TASK_ID': 'counted-task'}
        code, first = self.run_bridge('reject', env_extra=task)
        self.assertEqual(code, 0, first)
        self.assertNotIn('dispositions', json.loads(Path(first['usage_record']).read_text())['task'])
        notes = self.root / 'dispositions.md'
        notes.write_text('- High a.py:1: Fixed: abc123\n- Low b.py:2: disproved: the guard at line 4\n'
                         '- Low c.py:3: deferred: #12\n- Low d.py:4: fixed:abc123\n')
        code, second = self.run_bridge(env_extra=dict(task, REVIEW_DISPOSITIONS=str(notes)))
        self.assertEqual(code, 0, second)
        usage = json.loads(Path(second['usage_record']).read_text())
        self.assertEqual(usage['task']['dispositions'], {'fixed': 2, 'disproved': 1, 'deferred': 1})
        self.assertNotIn('shadow', usage['task'])

    def test_the_dispositions_file_is_read_once_before_the_model_runs(self):
        # A paid review whose dispositions file vanished meanwhile still gets its record, with
        # the counts of the bytes the reviewer was shown: nothing reads the file afterwards.
        task = {'MYAGENTKIT_TASK_ID': 'vanishing-task'}
        self.assertEqual(self.run_bridge('reject', env_extra=task)[0], 0)
        notes = self.root / 'dispositions.md'
        notes.write_text('- a.py:1 fixed: abc123\n- b.py:2 deferred: #3\n')
        code, result = self.run_bridge(env_extra=dict(task, REVIEW_DISPOSITIONS=str(notes),
                                                      FIXTURE_UNLINK=str(notes)))
        self.assertEqual(code, 0, result)
        self.assertFalse(notes.exists())
        self.assertEqual(result['status'], 'completed')
        usage = json.loads(Path(result['usage_record']).read_text())
        self.assertEqual(usage['task']['dispositions'], {'fixed': 1, 'disproved': 0, 'deferred': 1})

    def test_codex_records_carry_the_dispositions_and_the_shadow_flag_too(self):
        # The Codex adapter records the same measurement fields as Claude's: without this,
        # dropping **MEASURED from its record would pass every Claude-fixture test.
        usage = self.repo / '.myagentkit/usage'
        def newest():
            # By the recorded time: names share a second and a random suffix decides between them.
            records = [json.loads(p.read_text()) for p in usage.glob('*.json')]
            return max(records, key=lambda r: r['recorded_at'])
        env = dict(REVIEW_CODEX_MODEL='fixture-codex-model', REVIEW_CLI_BIN=str(self.build_fake_codex()),
                   MYAGENTKIT_TASK_ID='codex-measured',
                   REVIEW_ROUND_EXCEPTION='fixture: the measured rounds exceed two')
        result = self.run_wrapper('--uncommitted', '--reviewer', 'codex', **env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        first = newest()
        self.assertEqual(first['callee'], 'codex')
        self.assertNotIn('dispositions', first['task'])
        notes = self.root / 'codex-dispositions.md'
        notes.write_text('- a.py:1 fixed: abc\n- b.py:2 disproved: the guard\n- c.py:3 deferred: #4\n')
        result = self.run_wrapper('--uncommitted', '--reviewer', 'codex', REVIEW_DISPOSITIONS=str(notes), **env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        second = newest()
        self.assertEqual(second['task']['dispositions'], {'fixed': 1, 'disproved': 1, 'deferred': 1})
        self.assertNotIn('shadow', second['task'])
        result = self.run_wrapper('--uncommitted', '--reviewer', 'codex', REVIEW_SHADOW='1', **env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        third = newest()
        self.assertEqual(third['task']['shadow'], 'yes')
        self.assertIn('SHADOW REVIEW: this run measures a reviewer configuration',
                      Path(third['evidence']).read_text())

    def test_a_proposal_is_not_measured(self):
        # Only review rounds are measured: a proposal with the variables still exported
        # records neither field and is not refused by a keyless file.
        notes = self.root / 'dispositions.md'
        notes.write_text('nothing answered here\n')
        handoff = self.root / 'handoff.md'
        handoff.write_text('Fix the named function only.')
        code, result = self.run_bridge('proposal', 'propose', ['--task-file', str(handoff)],
                                       env_extra={'REVIEW_DISPOSITIONS': str(notes), 'REVIEW_SHADOW': '1'})
        self.assertEqual(code, 0, result)
        task = json.loads(Path(result['usage_record']).read_text())['task']
        self.assertNotIn('dispositions', task)
        self.assertNotIn('shadow', task)

    def test_a_proposal_keeps_the_documented_high_effort(self):
        # The tier default is the review's: a proposal without --effort ran at medium while
        # the myagentkit-delegate skill, its only caller, documents high.
        handoff = self.root / 'handoff.md'
        handoff.write_text('Fix the named function only.')
        code, result = self.run_bridge('proposal', 'propose', ['--task-file', str(handoff)])
        self.assertEqual(code, 0, result)
        self.assertEqual(json.loads(Path(result['evidence']).read_text())['effort'], 'high')

    def test_a_shadow_review_says_so_in_its_evidence_and_record(self):
        # REVIEW_SHADOW=1 measures a configuration: the archive carries the banner above the
        # findings, the record's task says shadow, and the verdict line is still exactly one.
        code, result = self.run_bridge('reject', env_extra={'REVIEW_SHADOW': '1'})
        self.assertEqual(code, 0, result)
        evidence = Path(result['evidence']).read_text()
        self.assertIn('SHADOW REVIEW: this run measures a reviewer configuration', evidence)
        self.assertEqual(evidence.count('\nVERDICT: '), 1)
        self.assertEqual(json.loads(Path(result['usage_record']).read_text())['task']['shadow'], 'yes')
        code, plain = self.run_bridge('reject', env_extra={'REVIEW_SHADOW': '0'})
        self.assertEqual(code, 0, plain)
        self.assertNotIn('SHADOW REVIEW', Path(plain['evidence']).read_text())
        # A shadow run under a label is no round of the change: the next real review under
        # that label carries no earlier round from it, and the reviewer never sees the flag.
        log = self.root / 'prompt.txt'
        task = {'MYAGENTKIT_TASK_ID': 'shadowed-task'}
        self.assertEqual(self.run_bridge('reject', env_extra=dict(task, REVIEW_SHADOW='1'))[0], 0)
        code, real = self.run_bridge(env_extra=dict(task, PROMPT_LOG=str(log)))
        self.assertEqual(code, 0, real)
        self.assertNotIn('Round 1', log.read_text())
        self.assertNotIn('shadow', json.loads(Path(real['usage_record']).read_text())['task'])

    def test_the_behaviour_appendix_follows_the_fixed_prompt_and_the_record_says_on_or_off(self):
        # Issue #74: the kit's BEHAVIOUR.md (core/BEHAVIOUR.md in the kit itself) reaches the
        # reviewer after its fixed rules; MYAGENTKIT_NO_BEHAVIOUR=1 leaves it out, and the usage
        # record names the side for usage_summary.py's A/B.
        log = self.root / 'prompt.txt'
        (self.repo / 'core').mkdir()
        (self.repo / 'core/BEHAVIOUR.md').write_text('Lead with the answer, synthetic.\n')
        # Committed, so the text reaches the prompt only as the appendix, never through the diff.
        self.commit_fixture('behaviour')
        (self.repo / 'file.py').write_text('changed again\n')
        for env, side in (({}, 'on'), ({'MYAGENTKIT_NO_BEHAVIOUR': '1'}, 'off')):
            with self.subTest(side=side):
                code, result = self.run_bridge(env_extra=dict(env, PROMPT_LOG=str(log)))
                self.assertEqual(code, 0, result)
                prompt = log.read_text()
                if side == 'on':
                    self.assertIn('runs the full suite.\nLead with the answer, synthetic.\n', prompt)
                else:
                    self.assertNotIn('Lead with the answer', prompt)
                usage = json.loads(Path(result['usage_record']).read_text())
                self.assertEqual(usage['task']['behaviour'], side)

    def test_a_reviewer_gets_the_appendix_without_author_only_lines_and_the_binding_names_it(self):
        # #228: a reviewer cannot act on the author's rules, so a review gets the appendix
        # without the bullets marked author-only (a wrapped one whole); the recorded hash and the
        # fingerprint name those bytes. A proposal (an author run) still gets the whole file.
        body = (b'- Lead with the answer.\n- Design before code. <!-- author-only -->\n'
                b'- One test per change,\n  wrapped over two lines. <!-- author-only -->\n- Stay terse.\n')
        variant = b'- Lead with the answer.\n- Stay terse.\n'
        self.assertEqual(bridge.reviewer_appendix(body), variant)
        self.assertEqual(bridge.reviewer_appendix(body.replace(b'\n', b'\r\n')), variant.replace(b'\n', b'\r\n'))
        self.git('config', 'core.autocrlf', 'false')
        (self.repo / 'BEHAVIOUR.md').write_bytes(body)
        self.commit_fixture('marked appendix')
        (self.repo / 'file.py').write_text('changed again\n')
        log = self.root / 'prompt.txt'
        code, result = self.run_bridge(env_extra={'PROMPT_LOG': str(log)})
        self.assertEqual(code, 0, result)
        prompt = log.read_text()
        self.assertIn('- Lead with the answer.\n- Stay terse.\n', prompt)
        self.assertNotIn('Design before code', prompt)
        self.assertNotIn('wrapped over two lines', prompt)
        digest = hashlib.sha256(variant).hexdigest()
        self.assertEqual(header_of(result['evidence'])['behaviour_sha256'], digest)
        self.assertEqual(json.loads(Path(result['usage_record']).read_text())['task']['behaviour_sha256'], digest)
        checkout = bridge.snapshot(self.repo, 'uncommitted', None, True)[1]
        self.assertEqual(result['fingerprint'], hashlib.sha256(
            checkout.encode() + b'\0behaviour\0BEHAVIOUR.md\0' + variant).hexdigest())
        handoff = self.root / 'handoff.md'
        handoff.write_text('Fix the named function only.')
        code, result = self.run_bridge('proposal', 'propose', ['--task-file', str(handoff)],
                                       env_extra={'PROMPT_LOG': str(log)})
        self.assertEqual(code, 0, result)
        self.assertIn(body.decode(), log.read_text())
        self.assertEqual(json.loads(Path(result['usage_record']).read_text())['task']['behaviour_sha256'],
                         hashlib.sha256(body).hexdigest())

    def test_an_escaping_behaviour_symlink_never_discloses_external_bytes(self):
        marker = 'PRIVATE_APPENDIX_MARKER_OUTSIDE_SNAPSHOT'
        external = self.root / 'private.txt'
        external.write_text(marker)
        (self.repo / 'BEHAVIOUR.md').symlink_to(external)
        log = self.root / 'prompt.txt'
        code, result = self.run_bridge(env_extra={'PROMPT_LOG': str(log)})
        self.assertNotEqual(code, 0, result)
        self.assertEqual(result['failure_kind'], 'unsafe_behaviour_appendix')
        self.assertNotIn(marker, log.read_text() if log.exists() else '')
        self.assertNotIn(marker, Path(result['evidence']).read_text())

    def test_a_behaviour_appendix_must_be_a_regular_file_even_inside_the_snapshot(self):
        appendix = self.repo / 'BEHAVIOUR.md'
        appendix.mkdir()
        code, result = self.run_bridge()
        self.assertNotEqual(code, 0, result)
        self.assertEqual(result['failure_kind'], 'unsafe_behaviour_appendix')
        appendix.rmdir()
        appendix.symlink_to(self.repo / 'file.py')
        code, result = self.run_bridge()
        self.assertNotEqual(code, 0, result)
        self.assertEqual(result['failure_kind'], 'unsafe_behaviour_appendix')

    def test_ignored_behaviour_bytes_are_in_the_copy_hash_and_staleness_check(self):
        with (self.repo / '.gitignore').open('a') as stream:
            stream.write('\n/BEHAVIOUR.md\n')
        self.commit_fixture('ignored appendix')
        appendix = self.repo / 'BEHAVIOUR.md'
        log, copy_log = self.root / 'prompt.txt', self.root / 'appendix.txt'
        env = {'PROMPT_LOG': str(log), 'APPENDIX_LOG': str(copy_log)}
        fingerprints = []
        for body in (b'Ignored appendix A.\r\n', b'Ignored appendix B.\r\n'):
            appendix.write_bytes(body)
            code, result = self.run_bridge(extra=['--commit', 'HEAD'], env_extra=env)
            self.assertEqual(code, 0, result)
            self.assertEqual(bytes.fromhex(copy_log.read_text()), body)
            self.assertIn(body.decode().strip(), log.read_text())
            digest = hashlib.sha256(body).hexdigest()
            self.assertEqual(header_of(result['evidence'])['behaviour_sha256'], digest)
            usage = json.loads(Path(result['usage_record']).read_text())
            self.assertEqual(usage['task']['behaviour_sha256'], digest)
            self.assertEqual(usage['task']['behaviour'], 'on')
            fingerprints.append(result['fingerprint'])
        self.assertNotEqual(*fingerprints)

    def test_a_tracked_appendix_reviews_under_autocrlf_and_hashes_the_copy_bytes(self):
        # Git for Windows turns autocrlf on: git archive then writes the tracked appendix with
        # CRLF while the checkout keeps LF. The review must not call that stale; the recorded
        # hash is of the bytes the reviewer saw. Seen live on the kit's own checkout.
        body = b'Tracked appendix line.\n'
        (self.repo / 'BEHAVIOUR.md').write_bytes(body)
        self.commit_fixture('tracked appendix')
        self.git('config', 'core.autocrlf', 'true')
        copy_log = self.root / 'appendix.txt'
        code, result = self.run_bridge(extra=['--commit', 'HEAD'], env_extra={'APPENDIX_LOG': str(copy_log)})
        self.assertEqual(code, 0, result)
        seen = bytes.fromhex(copy_log.read_text())
        self.assertEqual(seen, b'Tracked appendix line.\r\n')  # the conversion really happened
        self.assertEqual(header_of(result['evidence'])['behaviour_sha256'], hashlib.sha256(seen).hexdigest())
        self.assertEqual((self.repo / 'BEHAVIOUR.md').read_bytes(), body)
        # The fingerprint hashes eol-normalised bytes: the same state without autocrlf agrees.
        self.git('config', 'core.autocrlf', 'false')
        self.assertEqual(self.run_bridge(extra=['--commit', 'HEAD'])[1]['fingerprint'], result['fingerprint'])

    def test_a_tracked_appendix_whose_archive_differs_beyond_line_endings_is_stale(self):
        # export-subst expands a placeholder only in the archive: the reviewer would read an
        # appendix the owner never saw. Only line endings are tolerated; this fails closed.
        (self.repo / 'BEHAVIOUR.md').write_bytes(b'Rules for $Format:%H$\n')
        (self.repo / '.gitattributes').write_text('BEHAVIOUR.md export-subst\n')
        self.commit_fixture('expanding appendix')
        code, result = self.run_bridge(extra=['--commit', 'HEAD'])
        self.assertEqual(code, 5, result)
        self.assertEqual(result['failure_kind'], 'stale_checkout')

    def test_an_ignored_behaviour_change_during_commit_review_is_stale(self):
        with (self.repo / '.gitignore').open('a') as stream:
            stream.write('\n/BEHAVIOUR.md\n')
        self.commit_fixture('ignored appendix mutation')
        body = b'Original ignored appendix.\r\n'
        (self.repo / 'BEHAVIOUR.md').write_bytes(body)
        digest = hashlib.sha256(body).hexdigest()
        code, result = self.run_bridge('behaviour_mutation', extra=['--commit', 'HEAD'])
        self.assertEqual(code, 5, result)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['failure_kind'], 'stale_checkout')
        self.assertEqual(header_of(result['evidence'])['behaviour_sha256'], digest)

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

    def test_a_round_whose_chain_failed_is_carried_but_not_counted(self):
        # #258: the dispatcher can fail a chain (stale_checkout) after the adapter recorded a
        # completed review. Only the checkpoint written after that same attempt, saying failed,
        # takes it out of the count; it is still carried. Anything unclear counts (fail closed).
        log = self.root / 'prompt.txt'
        chains = self.repo / '.myagentkit/usage/chains'
        chains.mkdir(parents=True)
        failed_after = {'status': 'failed', 'failure_kind': 'stale_checkout', 'checkout_changed': True,
                        'attempts': [{'status': 'completed'}]}
        cases = (
            ('stale', {'-1': failed_after}, False),
            # a dispatcher killed after the review finished: only its pending checkpoint
            ('killed', {'-0': {'status': 'pending', 'failure_kind': None, 'attempts': []}}, True),
            # an earlier attempt failed, the record is attempt 2, its checkpoint never written
            ('retried', {'-1': {'status': 'failed', 'failure_kind': 'rate_limited',
                                'attempts': [{'status': 'failed'}]}}, True),
            ('damaged', {'-1': '{'}, True),
            # the checkout could not be read after the review: no change is proven, it counts
            ('unverified', {'-1': {'status': 'failed', 'failure_kind': 'checkout_unverified',
                                   'checkout_unverified': 'denied', 'attempts': [{'status': 'completed'}]}}, True))
        for label, checkpoints, counted in cases:
            with self.subTest(label=label):
                task = {'PROMPT_LOG': str(log), 'MYAGENTKIT_TASK_ID': 'chain-' + label}
                for chain in ('a', 'b'):
                    chain = label + chain
                    attempt = '2' if label == 'retried' else '1'
                    code, _ = self.run_bridge('reject', env_extra=dict(
                        task, MYAGENTKIT_REVIEW_CHAIN_ID=chain, MYAGENTKIT_REVIEW_ATTEMPT=attempt))
                    self.assertEqual(code, 0)
                    for suffix, value in checkpoints.items():
                        (chains / (chain + suffix + '.json')).write_text(
                            value if isinstance(value, str) else json.dumps(value))
                code, result = self.run_bridge(env_extra=task)
                if counted:
                    self.assertEqual(code, 2, result)
                    self.assertIn('already has 2 completed rounds', result['error'])
                else:
                    self.assertEqual(code, 0, result)
                    self.assertIn('This is review round 1', log.read_text())
                    self.assertIn('### Round 2', log.read_text())  # both stale rounds carried

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

    def test_the_projects_validation_seam_fails_a_final_report_in_each_adapter(self):
        # #87: a project's own check of the final report lived as a patch inside the adapters,
        # and every sync dropped it. scripts/project_validation.py beside them is the seam:
        # absent, the review passes as before; a reason fails it as invalid_evidence:<reason>.
        runs = {'claude': dict(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLAUDE_MODEL='claude-opus-5'),
                'codex': dict(REVIEW_CLI_BIN=str(self.build_fake_codex()), REVIEW_CODEX_MODEL='fixture-codex-model')}
        for provider, env in runs.items():
            with self.subTest(provider=provider):
                seam = self.install_wrapper() / 'project_validation.py'
                if seam.exists():
                    seam.unlink()
                passed = self.run_wrapper('--reviewer', provider, '--uncommitted', MYAGENTKIT_TASK_ID='seam-' + provider, **env)
                self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
                seam.write_text('def validate_final_message(text):\n'
                                '    assert "VERDICT" in text or "Accept" in text, text\n'
                                '    return "non-Latin letters"\n')
                failed = self.run_wrapper('--reviewer', provider, '--uncommitted', MYAGENTKIT_TASK_ID='seam2-' + provider, **env)
                self.assertNotEqual(failed.returncode, 0, failed.stdout)
                chain = json.loads(next(s.removeprefix('review dispatch: ') for s in
                                        failed.stdout.splitlines() if s.startswith('review dispatch: ')))
                self.assertEqual(chain['failure_kind'], 'invalid_evidence:non-Latin letters', failed.stdout)
                self.assertEqual(verdicts_of(chain['attempts'][0]['evidence']), [])

    BACKEND = {'ANTHROPIC_BASE_URL': 'https://backend.invalid/api', 'ANTHROPIC_AUTH_TOKEN': 'tok=en',
               'ANTHROPIC_DEFAULT_OPUS_MODEL': 'glm-fixture'}

    def backend_file(self, text):
        # The tests own every ANTHROPIC_* variable: one from the host would change what the CLI sees.
        for key in [key for key in os.environ if key.startswith('ANTHROPIC_')]:
            del os.environ[key]
        path = self.repo / '.myagentkit/backends/glm.env'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_a_backend_review_runs_on_its_endpoint_and_records_its_model(self):
        # The file's variables reach the CLI in place of the inherited ones; its model is the pin
        # the CLI's modelUsage attests; the review is by another identity, claude@glm. The flag
        # wins over MYAGENTKIT_BACKEND, which names a file that does not exist.
        self.backend_file('# GLM\n' + ''.join('%s=%s\n' % item for item in self.BACKEND.items()))
        log = self.root / 'env.json'
        for args, chosen in ((['--backend', 'glm'], 'missing'), ([], 'glm')):
            with self.subTest(args=args):
                result = self.run_wrapper('--uncommitted', *args, CLAUDE_CLI_BIN=str(self.fixture),
                                          REVIEW_CLAUDE_MODEL='claude-opus-5', ENV_LOG=str(log),
                                          ANTHROPIC_API_KEY='lead-key', MYAGENTKIT_BACKEND=chosen)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(log.read_text()), self.BACKEND)
                # The wrapper's default effort is medium; REVIEW_RISK=high raises it (review.sh).
                self.assertIn('REVIEW [about to run]: claude@glm model glm-fixture, effort medium', result.stdout)
                self.assertNotIn('tok=en', result.stdout)
                chain = json.loads(next(line.removeprefix('review dispatch: ') for line in result.stdout.splitlines()
                                        if line.startswith('review dispatch: ')))
                self.assertEqual((chain['requested_reviewer'], chain['selected_reviewer']), ('claude@glm', 'claude@glm'))
                usage = json.loads(Path(chain['attempts'][0]['usage_record']).read_text())
                self.assertEqual((usage['backend'], usage['model_requested']), ('glm', 'glm-fixture'))
                self.assertEqual(header_of(chain['attempts'][0]['evidence'])['model'],
                                 'backend glm, model glm-fixture')

    def test_a_backend_without_its_endpoint_or_model_refuses_before_launch(self):
        log = self.root / 'env.json'
        for name, text, reason in (
                ('glm', 'ANTHROPIC_DEFAULT_OPUS_MODEL=glm-fixture\n', 'sets no ANTHROPIC_BASE_URL'),
                ('glm', 'ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_DEFAULT_SONNET_MODEL=x\n', 'sets no model'),
                ('glm', 'ANTHROPIC_BASE_URL=https://backend.invalid\nANTHROPIC_MODEL=glm-fixture\n'
                        'ANTHROPIC_API_KEY=secret-value\n', 'line 3 of'),
                ('absent', '', 'is not in the backend folder'),
                ('../glm', '', 'backend name must be')):
            with self.subTest(name=name, reason=reason):
                self.backend_file(text)
                result = self.run_wrapper('--uncommitted', '--backend', name, CLAUDE_CLI_BIN=str(self.fixture),
                                          REVIEW_CLAUDE_MODEL='claude-opus-5', ENV_LOG=str(log))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('FAIL [review]: ', result.stdout)
                self.assertIn(reason, result.stdout)
                self.assertNotIn('secret-value', result.stdout)
                self.assertFalse(log.exists(), 'the reviewer launched')
                self.assertFalse((self.repo / '.myagentkit/usage').exists(), 'a chain was recorded')

    def test_without_a_backend_the_claude_review_is_unchanged(self):
        self.backend_file(''.join('%s=%s\n' % item for item in self.BACKEND.items()))
        log = self.root / 'env.json'
        result = self.run_wrapper('--uncommitted', CLAUDE_CLI_BIN=str(self.fixture), MYAGENTKIT_BACKEND='',
                                  REVIEW_CLAUDE_MODEL='claude-opus-5', ENV_LOG=str(log), ANTHROPIC_API_KEY='lead-key')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(log.read_text()), {'ANTHROPIC_API_KEY': 'lead-key'})
        chain = json.loads(next(line.removeprefix('review dispatch: ') for line in result.stdout.splitlines()
                                if line.startswith('review dispatch: ')))
        self.assertEqual(chain['requested_reviewer'], 'claude')
        self.assertNotIn('backend', json.loads(Path(chain['attempts'][0]['usage_record']).read_text()))
        self.assertEqual(header_of(chain['attempts'][0]['evidence'])['model'], 'claude-opus-5')

    def test_the_backend_environment_lives_only_through_its_claude_attempt(self):
        # A Codex fallback after a backend attempt, and the dispatcher after both, see the
        # inherited environment again, never the backend's token.
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import review_dispatch
        self.backend_file(''.join('%s=%s\n' % item for item in self.BACKEND.items()))
        seen = {}

        def adapter(name):
            def main(argv, report, claims=None):
                seen[name] = {k: v for k, v in os.environ.items() if k.startswith('ANTHROPIC_')}
                report({'status': 'failed', 'failure_kind': 'quota_exhausted', 'evidence': 'e', 'usage_record': 'u'})
                return 5
            return main
        with patch.dict(os.environ, self.review_env(ANTHROPIC_API_KEY='lead-key',
                                                   MYAGENTKIT_AUTHOR='claude/claude-sonnet-5',
                                                   MYAGENTKIT_AUTHOR_EFFORT='low')), \
                patch.object(review_dispatch.claude_bridge, 'main', adapter('claude')), \
                patch.object(review_dispatch.codex_bridge, 'main', adapter('codex')), redirect_stdout(io.StringIO()):
            review_dispatch.main(['--repo', str(self.repo), '--uncommitted', '--reviewer', 'claude',
                                  '--allow-fallback', '--backend', 'glm', '--claude-model', 'claude-opus-5',
                                  '--codex-model', 'codex-fixture-model'])
            after = {k: v for k, v in os.environ.items() if k.startswith('ANTHROPIC_')}
        self.assertEqual(seen, {'claude': self.BACKEND, 'codex': {'ANTHROPIC_API_KEY': 'lead-key'}})
        self.assertEqual(after, {'ANTHROPIC_API_KEY': 'lead-key'})
        # Even a partial environment update failure must run the restoration guard.
        update = os.environ.update

        def partial_update(values):
            if values == self.BACKEND:
                update({'ANTHROPIC_BASE_URL': values['ANTHROPIC_BASE_URL']})
                raise ValueError('injected environment update failure')
            update(values)

        with patch.dict(os.environ, self.review_env(ANTHROPIC_API_KEY='lead-key')), \
                patch.object(os.environ, 'update', side_effect=partial_update), \
                patch.object(review_dispatch.claude_bridge, 'main') as launch, redirect_stdout(io.StringIO()):
            self.assertEqual(review_dispatch.main(['--repo', str(self.repo), '--uncommitted', '--backend', 'glm']), 5)
            self.assertEqual({k: v for k, v in os.environ.items() if k.startswith('ANTHROPIC_')},
                             {'ANTHROPIC_API_KEY': 'lead-key'})
            launch.assert_not_called()

    def test_unavailable_claude_uses_codex_only_with_fallback(self):
        result = self.run_wrapper('--uncommitted', '--fallback', FIXTURE_CASE='quota',
                                  MYAGENTKIT_AUTHOR='claude-sonnet-5', MYAGENTKIT_AUTHOR_EFFORT='low',
                                  CLAUDE_CLI_BIN=str(self.fixture),
                                  REVIEW_CLAUDE_MODEL='claude-opus-5',
                                  REVIEW_CODEX_MODEL='codex-fixture-model',
                                  REVIEW_CLI_BIN=str(self.build_fake_codex()))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reports = list((self.repo / 'docs/reviews').glob('*-review.md'))
        self.assertEqual(len(reports), 2)
        self.assertEqual({header_of(p)['status'] for p in reports}, {'failed', 'completed'})
        substitute = next(p for p in reports if header_of(p)['reviewer'] == 'codex')
        self.assertIn('FALLBACK REVIEWER: the requested reviewer claude (quota_exhausted) did not complete',
                      substitute.read_text())
        self.assertIn('FALLBACK [review]: this review is by codex, not the requested claude',
                      result.stdout)

    def dispatch_result(self, primary='claude', fallback=True, args=(), **extra):
        env = dict(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLAUDE_MODEL='claude-opus-5',
                   REVIEW_CODEX_MODEL='codex-fixture-model', REVIEW_CLI_BIN=str(self.build_fake_codex()),
                   MYAGENTKIT_REQUESTER='codex/fixture-codex-model', MYAGENTKIT_TASK_ID='fallback-task',
                   MYAGENTKIT_AUTHOR='claude-sonnet-5' if primary == 'claude' else 'gpt-5.5',
                   MYAGENTKIT_AUTHOR_EFFORT='low',
                   REVIEW_ROUND_EXCEPTION='fixture: the chain tests run more than two rounds')
        env.update(extra)
        result = self.run_wrapper('--reviewer', primary, *(['--fallback'] if fallback else []), *args, **env)
        line = next((s.removeprefix('review dispatch: ') for s in result.stdout.splitlines()
                     if s.startswith('review dispatch: ')), None)
        return result, json.loads(line) if line else None

    def test_failover_preserves_pins_scope_usage_and_advisory_status(self):
        for primary in ('claude', 'codex'):
            result, chain = self.dispatch_result(primary, **(
                {'FIXTURE_CASE': 'quota'} if primary == 'claude' else {'CODEX_FIXTURE_CASE': 'quota'}))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(chain['attempts']), 2)
            self.assertEqual(chain['attempts'][0]['failure_kind'], 'quota_exhausted')
            self.assertNotEqual(chain['selected_reviewer'], primary)
            self.assertFalse(chain['review_approved'])
            self.assertEqual(chain['independence'], 'host_must_check_all_patch_authors')
            self.assertEqual(json.loads(Path(chain['chain_record']).read_text()), chain)
            headers = [header_of(a['evidence']) for a in chain['attempts']]
            self.assertEqual(headers[0]['fingerprint'], headers[1]['fingerprint'])
            self.assertEqual(headers[0]['diff_sha256'], headers[1]['diff_sha256'])
            evidence = [Path(a['evidence']).read_text() for a in chain['attempts']]
            self.assertNotIn('FALLBACK REVIEWER', evidence[0])
            self.assertIn('FALLBACK REVIEWER: the requested reviewer %s (quota_exhausted)' % primary, evidence[1])
            for i, attempt in enumerate(chain['attempts'], 1):
                usage = json.loads(Path(attempt['usage_record']).read_text())
                self.assertEqual(usage['review_fallback_from'], None if i == 1 else primary + ' (quota_exhausted)')
                self.assertEqual(usage['review_chain_id'], chain['chain_id'])
                self.assertEqual(usage['review_attempt'], str(i))
                self.assertEqual(usage['task']['id'], 'fallback-task')
                self.assertEqual(usage['model_requested'], chain['configured_models'][attempt['reviewer']])
                self.assertEqual(usage['requester_reported'], 'codex/fixture-codex-model')

    def test_operational_failures_try_other_model_once(self):
        cases = {'context': 'context_limit', 'turns': 'budget_or_turn_limit',
                 'timeout': 'timeout', 'exit': 'cli_error'}
        for case, kind in cases.items():
            with self.subTest(case=case):
                # A native fixture's interpreter startup can exceed one second under load.
                # The stalled fixture sleeps 20 s: a 5 s bound still proves real timeout
                # failover, while allowing the immediate fallback reviewer to finish.
                result, chain = self.dispatch_result(FIXTURE_CASE=case,
                                                     REVIEW_TIMEOUT_SECONDS='5' if WINDOWS else '1')
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
                              ('codex', {'CODEX_FIXTURE_CASE': 'mcp_exit'})):
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

    def test_a_completed_codex_review_is_not_failed_by_noise_it_recovered_from(self):
        # A review that exited 0, closed its stream with turn.completed and gave one verdict was
        # recorded cli_error: the stream carried a reconnect error event the CLI recovered from,
        # while its own MCP client logged a transport failure on stderr. Both are kept in the
        # usage record; a failure of the structured outcome itself fails with its own kind, so a
        # missing verdict stays invalid_evidence and is not retried or failed over (#180).
        for case, kind in (('mcp', None), ('mcp_reconnect', None), ('mcp_exit', 'cli_error'),
                           ('mcp_no_completion', 'cli_error'), ('mcp_no_verdict', 'invalid_evidence'),
                           ('mcp_two_verdicts', 'invalid_evidence'), ('mcp_failed_turn', 'cli_error'),
                           ('mcp_quota', 'quota_exhausted'), ('unknown_flag', 'cli_unsupported')):
            with self.subTest(case=case):
                # No Claude pin: a used-up Codex quota would switch the review to Claude (decision 7).
                result, chain = self.dispatch_result('codex', fallback=False, CODEX_FIXTURE_CASE=case,
                                                     MYAGENTKIT_TASK_ID='noise-' + case, REVIEW_CLAUDE_MODEL='')
                attempt = chain['attempts'][0]
                self.assertEqual(attempt['failure_kind'], kind, result.stdout)
                self.assertEqual(result.returncode, 0 if kind is None else 5, result.stdout)
                self.assertEqual(verdicts_of(attempt['evidence']), [] if kind else ['VERDICT: Accept'])
                usage = json.loads(Path(attempt['usage_record']).read_text())
                self.assertEqual(usage['status'], 'failed' if kind else 'completed')
                if case.startswith('mcp'):
                    self.assertIn('Transport channel closed', usage['raw_stderr'])

    def test_a_quota_status_on_a_valid_claude_review_is_a_quota_failure_for_the_dispatcher(self):
        # It once ended the chain as a completed review by claude whose failure_kind was quota.
        result, chain = self.dispatch_result(fallback=False, FIXTURE_CASE='api_429')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual((chain['status'], chain['failure_kind']), ('failed', 'rate_limited'))
        self.assertEqual([a['reviewer'] for a in chain['attempts']], ['claude'])
        self.assertIn('not requested', chain['fallback_blocked'])
        self.assertNotIn('selected_reviewer', chain)
        self.assertEqual(chain['recovery']['action'], 'continue_independent_work')
        # With --fallback, quota is an unavailable reviewer like any other: Codex runs once.
        result, chain = self.dispatch_result(FIXTURE_CASE='api_429', MYAGENTKIT_TASK_ID='api-fallback')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual([(a['reviewer'], a['status'], a['failure_kind']) for a in chain['attempts']],
                         [('claude', 'failed', 'rate_limited'), ('codex', 'completed', None)])
        self.assertEqual(chain['selected_reviewer'], 'codex')
        self.assertFalse(chain['review_approved'])

    @posix_only
    def test_cancelled_review_stops_the_reviewer_records_usage_and_never_fails_over(self):
        # SIGTERM and SIGHUP used to end the dispatcher without its cleanup, leaving the paid
        # reviewer's process group running; Ctrl-C lost the failed attempt's usage record.
        import select
        import signal
        import time
        hanging = self.root / 'hanging-cli'
        hanging = python_cli(hanging, HANGING_CLI)
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
                cwd_log = self.root / ('cwd-%s-%s' % (provider, sig.name))
                env = self.review_env(ALIVE_FIFO=str(fifo), REVIEW_CLAUDE_MODEL='claude-opus-5',
                                      REVIEW_CODEX_MODEL='fixture-codex-model',
                                      CWD_LOG=str(cwd_log), **clis)
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
                # The cancelled reviewer ran in a throwaway copy, and the cancel removed it.
                copy = Path(cwd_log.read_text())
                self.assertNotEqual(copy.resolve(), self.repo.resolve())
                self.assertFalse(copy.exists(), 'a cancelled review left its copy behind')
                self.assertNotEqual(review.returncode, 0, output)
                chain = json.loads(next(line.removeprefix('review dispatch: ') for line in output.splitlines()
                                        if line.startswith('review dispatch: ')))
                self.assertEqual([a['reviewer'] for a in chain['attempts']], [provider])
                self.assertEqual(chain['failure_kind'], 'cancelled')
                usage = json.loads(Path(chain['attempts'][0]['usage_record']).read_text())
                self.assertEqual((usage['status'], usage['failure_kind']), ('failed', 'cancelled'))
                self.assertEqual(verdicts_of(chain['attempts'][0]['evidence']), [])

    @posix_only
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
            PYTHON_SHEBANG +
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

    @posix_only
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

    # --- native Windows Python: one platform seam in agent_process ----------------------------

    def test_off_posix_every_launch_takes_a_new_process_group_and_no_posix_keyword(self):
        # Windows rejects preexec_fn and start_new_session; each launch of the review tooling goes
        # through agent_process.launch, which passes CREATE_NEW_PROCESS_GROUP there instead.
        from unittest.mock import patch
        import agent_process
        import codex_quota
        seen = []

        def fake(command, **kw):
            seen.append(kw)
            raise OSError(2, 'fixture: no such program')

        def absent(*args, **kw):
            raise AssertionError('a POSIX-only call was made off POSIX')

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # The POSIX half needs a signal mask, which native Windows lacks.
            for posix in (False,) if WINDOWS else (True, False):
                del seen[:]
                with patch.object(agent_process, 'POSIX', posix), patch('subprocess.Popen', fake), \
                        patch('os.killpg', absent, create=True), \
                        patch('signal.pthread_sigmask', absent if not posix else signal.pthread_sigmask,
                              create=True):
                    self.assertEqual(agent_process.run(['fixture'], 'p', tmp, 5)['termination'], 'unavailable')
                    self.assertEqual(codex_quota.snapshot('fixture', tmp)['status'], 'unavailable')
                    for diff in (None, ''):
                        copy = tmp / ('copy-%s-%s' % (posix, diff is None))
                        copy.mkdir()
                        with self.assertRaises(OSError):
                            bridge.throwaway_copy(tmp, 'HEAD', diff, copy)
                self.assertEqual(len(seen), 4, seen)
                for kw in seen:
                    with self.subTest(posix=posix, kw=sorted(kw)):
                        if posix:
                            self.assertIs(kw['start_new_session'], True)
                            self.assertTrue(callable(kw['preexec_fn']))
                            self.assertNotIn('creationflags', kw)
                        else:
                            self.assertNotIn('preexec_fn', kw)
                            self.assertNotIn('start_new_session', kw)
                            # CREATE_NEW_PROCESS_GROUP, suspended until it joins its job object
                            self.assertEqual(kw['creationflags'], 0x200 | 0x4)

    @posix_only
    def test_stop_group_never_signals_a_reaped_pid(self):
        # A reviewer that ended normally was reaped by run(); stop_group then signalled its
        # pid anyway, which a later process may already own.
        import agent_process
        from unittest.mock import patch
        child = subprocess.Popen(['sh', '-c', 'exit 0'], start_new_session=True)
        child.wait()
        with patch.object(agent_process.os, 'kill') as kill, patch.object(agent_process.os, 'killpg'):
            agent_process.stop_group(child, child.pid)
        self.assertEqual(kill.call_count, 0, 'a reaped pid was signalled')

    def run_with_a_setsid_grandchild(self, timeout, cancel_after_start):
        """Run a reviewer with a detached descendant; return (result, descendant pid)."""
        import agent_process
        import threading
        pid_file = self.root / 'grandchild.pid'
        reviewer = self.root / 'setsid-reviewer.py'
        reviewer.write_text('import subprocess, sys, time\n'
                            'subprocess.Popen([sys.executable, "-c", "import os, sys, time; '
                            'open(sys.argv[1], \'w\').write(str(os.getpid())); time.sleep(120)", sys.argv[1]], '
                            'start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, '
                            'stderr=subprocess.DEVNULL)\n'
                            'time.sleep(120)\n')

        finished = threading.Event()

        def started():
            deadline = time.monotonic() + 20
            while not (pid_file.exists() and pid_file.read_text()) and time.monotonic() < deadline:
                if finished.wait(0.05):
                    return
            if cancel_after_start and not finished.is_set() and pid_file.exists() and pid_file.read_text():
                send_cancel(signal.SIGTERM)
        watcher = threading.Thread(target=started, daemon=True)
        watcher.start()
        try:
            result = agent_process.run([sys.executable, '-I', str(reviewer), str(pid_file)], '', self.root, timeout)
        finally:
            finished.set()
            watcher.join()
        self.assertTrue(pid_file.exists() and pid_file.read_text(), 'the grandchild never started')
        return result, int(pid_file.read_text())

    def assert_gone(self, pid):
        """A zombie is gone too: an orphan's reaper may be slow, and it runs nothing."""
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True).stdout
            if not state.strip() or state.strip().startswith('Z'):
                return
            time.sleep(0.1)
        os.kill(pid, signal.SIGKILL)
        self.fail('the setsid grandchild %d outlived the stopped review' % pid)

    @posix_only
    def test_a_cancel_stops_a_descendant_that_left_the_process_group(self):
        # killpg reaches the reviewer's group only: a descendant that called setsid ran on
        # after the review was cancelled.
        result, pid = self.run_with_a_setsid_grandchild(60, cancel_after_start=True)
        self.assert_gone(pid)
        self.assertEqual(result['termination'], 'cancelled', result)

    @posix_only
    def test_a_timeout_stops_a_descendant_that_left_the_process_group(self):
        result, pid = self.run_with_a_setsid_grandchild(3, cancel_after_start=False)
        self.assert_gone(pid)
        self.assertEqual(result['termination'], 'timeout', result)

    @posix_only
    def test_off_posix_stop_group_runs_taskkill_on_the_tree_and_never_killpg(self):
        from unittest.mock import patch
        import agent_process

        def absent(*args, **kw):
            raise AssertionError('os.killpg was called off POSIX')

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            log = tmp / 'taskkill.log'
            # A stand-in taskkill: records its arguments, then kills /PID's process (or fails).
            (tmp / 'taskkill').write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TASKKILL_LOG"\n'
                                          '[ -z "${TASKKILL_FAIL:-}" ] || exit 128\nkill -9 "$4"\n')
            (tmp / 'taskkill').chmod(0o755)
            for fail in ('', '1'):
                with self.subTest(taskkill_fails=bool(fail)):
                    log.write_text('')
                    child = subprocess.Popen(['sleep', '30'])
                    try:
                        with patch.object(agent_process, 'POSIX', False), patch('os.killpg', absent), \
                                patch.dict(os.environ, PATH=str(tmp) + os.pathsep + os.environ['PATH'],
                                           TASKKILL_LOG=str(log), TASKKILL_FAIL=fail):
                            agent_process.stop_group(child, child.pid)
                        # Stopped and reaped: by taskkill, or by child.kill() when taskkill failed.
                        self.assertEqual(child.returncode, -signal.SIGKILL)
                        self.assertEqual(log.read_text(), '/T /F /PID %d\n' % child.pid)
                    finally:
                        if child.returncode is None:
                            child.kill()
                            child.wait()

    def test_the_review_modules_import_where_posix_only_signals_do_not_exist(self):
        # Native Windows Python has no SIGHUP, SIGKILL, pthread_sigmask, sigpending, os.killpg or
        # fcntl: CANCEL_SIGNALS once named SIGHUP at module level, and the import raised.
        simulated = ('import os, signal, sys, selectors, shutil, subprocess, tempfile, threading\n'
                     'for name in ("SIGHUP", "SIGKILL", "pthread_sigmask", "sigpending", "sigwait"):\n'
                     '    signal.__dict__.pop(name, None)\n'  # native Windows lacks them already
                     'os.__dict__.pop("killpg", None)\n'
                     'sys.modules["fcntl"] = None\n'
                     'os.name = "nt"\n'
                     'sys.path.insert(0, sys.argv[1])\n'
                     'import agent_process, claude_bridge, codex_bridge, codex_quota, review_dispatch\n'
                     'print(agent_process.POSIX, [s.name for s in agent_process.CANCEL_SIGNALS])\n'
                     # Off POSIX the cancels are held by a recorder for the block, then restored.
                     'mask = agent_process.block_cancels()\n'
                     'print(signal.getsignal(signal.SIGINT) is not signal.default_int_handler)\n'
                     'agent_process.restore_mask(mask)\n'
                     'print(signal.getsignal(signal.SIGINT) is signal.default_int_handler)\n')
        result = subprocess.run([sys.executable, '-c', simulated, str(ROOT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "False ['SIGINT', 'SIGTERM']\nTrue\nTrue\n", result.stderr)

    def test_posix_only_process_calls_are_made_only_in_the_agent_process_seam(self):
        # Every launch, block and group kill of the review tooling goes through agent_process's
        # seam, which alone knows the platform; a direct call elsewhere breaks native Windows.
        import ast
        seam = {'block_cancels', 'restore_mask', 'pending', 'launch', 'stop_group', 'lock_file'}
        attributes = {'killpg', 'pthread_sigmask', 'sigpending', 'SIGHUP', 'SIGKILL'}
        keywords = {'preexec_fn', 'start_new_session'}
        offenders = []
        for name in ('agent_process', 'claude_bridge', 'codex_bridge', 'codex_quota', 'review_dispatch'):
            tree = ast.parse((ROOT / (name + '.py')).read_text())
            allowed = set()
            if name == 'agent_process':
                defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
                for node in tree.body:
                    if isinstance(node, ast.FunctionDef) and node.name in seam:
                        allowed.update(range(node.lineno, node.end_lineno + 1))
            for node in ast.walk(tree):
                hit = (isinstance(node, ast.Attribute) and node.attr in attributes
                       or isinstance(node, ast.keyword) and node.arg in keywords
                       or isinstance(node, ast.Import) and any(a.name == 'fcntl' for a in node.names)
                       or isinstance(node, ast.ImportFrom) and node.module == 'fcntl')
                if hit and node.lineno not in allowed:
                    offenders.append('%s.py:%d' % (name, node.lineno))
        self.assertEqual(offenders, [])
        self.assertEqual(seam - defined, set())

    # v0.11 close-out batch 4 (BACKLOG item F; KARARLAR B01, B12, D04, D07, D09).

    def test_the_dispositions_are_read_once_per_review_and_handed_to_each_attempt(self):
        # BACKLOG item F: each attempt read the file again, so a fallback attempt after the file
        # changed or vanished saw other claims than the first attempt, or failed as adapter_error.
        label = 'read-once-task'
        self.assertEqual(self.run_bridge('reject', env_extra={'MYAGENTKIT_TASK_ID': label})[0], 0)
        notes = self.root / 'once-dispositions.md'
        notes.write_text('- file.py:1 disproved: the caller rejects that input\n')
        log = self.root / 'codex-prompt.txt'
        result, chain = self.dispatch_result('claude', MYAGENTKIT_TASK_ID=label, FIXTURE_CASE='quota',
                                             FIXTURE_UNLINK=str(notes), REVIEW_DISPOSITIONS=str(notes),
                                             PROMPT_LOG=str(log))
        self.assertFalse(notes.exists())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([a['reviewer'] for a in chain['attempts']], ['claude', 'codex'])
        self.assertIn('disproved: the caller rejects that input', log.read_text(encoding='utf-8'))
        usage = json.loads(Path(chain['attempts'][-1]['usage_record']).read_text())
        self.assertEqual(usage['task']['dispositions'], {'fixed': 0, 'disproved': 1, 'deferred': 0})

    def test_an_unreadable_dispositions_file_stops_the_review_with_one_message(self):
        # BACKLOG item F: a missing or non-UTF-8 REVIEW_DISPOSITIONS raised a raw OSError or
        # UnicodeDecodeError (a traceback) before the "no earlier rounds" message.
        head = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        bad = self.root / 'latin1.md'
        bad.write_bytes(b'- file.py:1 fixed: caf\xe9\n')
        for path in (self.root / 'absent.md', bad):
            with self.subTest(path=path.name):
                os.environ['REVIEW_DISPOSITIONS'] = str(path)
                with self.assertRaisesRegex(bridge.BridgeError, 'REVIEW_DISPOSITIONS .* cannot be read'):
                    bridge.prior_rounds(self.repo, 'unreadable-task', 'uncommitted', None, head, 'x')
                result = self.run_wrapper('--uncommitted', CLAUDE_CLI_BIN=str(self.fixture),
                                          REVIEW_CLAUDE_MODEL='claude-opus-5',
                                          MYAGENTKIT_TASK_ID='unreadable-task', REVIEW_DISPOSITIONS=str(path))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('FAIL [review]: REVIEW_DISPOSITIONS', result.stdout)
                self.assertNotIn('Traceback', result.stdout + result.stderr)

    def test_prior_rounds_returns_the_measured_fields_and_keeps_no_module_state(self):
        # BACKLOG item F (AGENTS.md: no static mutable state): MEASURED was a module dict that
        # prior_rounds() filled and the record read, so one review's fields could reach another.
        head = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        os.environ.update(REVIEW_SHADOW='1', REVIEW_FOCUS='logic')
        carried, measured = bridge.prior_rounds(self.repo, 'measured-task', 'uncommitted', None, head, 'x')
        # The tree read and the diff's files ride along since #293.
        self.assertEqual((carried, measured), ('', {'shadow': 'yes', 'focus': 'logic', 'tree': str(self.repo.resolve()),
                                                    'files': []}))
        self.assertFalse(hasattr(bridge, 'MEASURED'))

    def test_a_shadow_review_is_marked_in_the_chain_and_on_the_console(self):
        # BACKLOG item F: the chain record and the result line did not mark a shadow review, and
        # a REVIEW_SHADOW left exported silently turned every later review into one.
        env = dict(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLAUDE_MODEL='claude-opus-5')
        result = self.run_wrapper('--uncommitted', REVIEW_SHADOW='1', **env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        chain = json.loads(result.stdout.split('review dispatch: ', 1)[1].splitlines()[0])
        self.assertIs(chain['shadow'], True)
        self.assertIn('REVIEW [shadow]:', result.stdout)
        self.assertIn('unset REVIEW_SHADOW', result.stdout)
        result = self.run_wrapper('--uncommitted', **env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        chain = json.loads(result.stdout.split('review dispatch: ', 1)[1].splitlines()[0])
        self.assertNotIn('shadow', chain)
        self.assertNotIn('REVIEW [shadow]', result.stdout)

    def test_the_author_tier_never_reviews_and_the_record_names_the_author(self):
        # KARARLAR B01 (1): review.sh's default excludes the author's tier. With MYAGENTKIT_AUTHOR
        # naming the tier the selected reviewer would run, the review is refused before any
        # model or record; another tier runs, and the chain and the usage record name the author.
        env = dict(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLAUDE_MODEL='claude-opus-5')
        for author in ('claude-opus-5', 'claude/claude-opus-5-5', 'CLAUDE-OPUS-5-20261001'):
            with self.subTest(author=author):
                result = self.run_wrapper('--uncommitted', MYAGENTKIT_AUTHOR=author, **env)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('the author never reviews its own patch', result.stdout)
                self.assertIn('docs/REVIEW_GATE.md', result.stdout)
                self.assertFalse((self.repo / '.myagentkit/usage').exists())
        result = self.run_wrapper('--uncommitted', MYAGENTKIT_AUTHOR='claude-sonnet-5', MYAGENTKIT_AUTHOR_EFFORT='low', **env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        chain = json.loads(result.stdout.split('review dispatch: ', 1)[1].splitlines()[0])
        self.assertEqual(chain['author'], 'claude-sonnet-5')
        usage = json.loads(Path(chain['attempts'][0]['usage_record']).read_text())
        self.assertEqual(usage['task']['author'], 'claude-sonnet-5')
        # Without the variable nothing changes: no author field, the lead's check stands.
        result = self.run_wrapper('--uncommitted', **env)
        chain = json.loads(result.stdout.split('review dispatch: ', 1)[1].splitlines()[0])
        self.assertNotIn('author', chain)
        self.assertNotIn('author', json.loads(Path(chain['attempts'][0]['usage_record']).read_text())['task'])

    def test_the_reviewer_is_at_least_the_author_tier_and_the_top_tier_reviews_its_own(self):
        # #290, owner decision 63: a weaker tier is refused as the required review, the refusal
        # naming the allowed pins; the top tier's own review runs in a fresh session at the
        # author's effort or above and is recorded; a lower tier runs only as a shadow opinion.
        fable = dict(CLAUDE_CLI_BIN=str(self.fixture), MYAGENTKIT_AUTHOR='claude-fable-5-1')
        for extra, named in ((dict(REVIEW_CLAUDE_MODEL='claude-opus-5-5', MYAGENTKIT_AUTHOR_EFFORT='high'),
                              'Pin claude-fable at claude-fable-5-1\'s effort or above'),
                             (dict(REVIEW_CLAUDE_MODEL='claude-sonnet-5', MYAGENTKIT_AUTHOR='claude-opus-5'),
                              'Pin claude-fable,'),
                             # Owner decision 66: an unnamed author effort counts as high.
                             (dict(REVIEW_CLAUDE_MODEL='claude-fable-5-1', REVIEW_EFFORT='medium'),
                              "review effort medium is below author claude-fable-5-1's effort high"),
                             (dict(REVIEW_CLAUDE_MODEL='claude-fable-5-1', MYAGENTKIT_AUTHOR_EFFORT='high',
                                   REVIEW_EFFORT='medium'), 'review effort medium is below'),
                             (dict(REVIEW_CLAUDE_MODEL='claude-fable-5-1', MYAGENTKIT_AUTHOR_EFFORT='xhigh',
                                   REVIEW_EFFORT='medium'), 'at high for an author above it'),
                             # Owner decision 65: the effort floor holds for every required review;
                             # decision 66: unnamed, the author's effort is high.
                             (dict(REVIEW_CLAUDE_MODEL='claude-fable-5-1', MYAGENTKIT_AUTHOR='claude-opus-5-5',
                                   MYAGENTKIT_AUTHOR_EFFORT='high', REVIEW_EFFORT='low'),
                              "review effort low is below author claude-opus-5-5's effort high"),
                             (dict(REVIEW_CLAUDE_MODEL='claude-fable-5-1', MYAGENTKIT_AUTHOR='claude-opus-5-5',
                                   REVIEW_EFFORT='medium'),
                              "review effort medium is below author claude-opus-5-5's effort high")):
            with self.subTest(extra=extra):
                result = self.run_wrapper('--uncommitted', **dict(fable, **extra))
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(named, result.stdout)
                self.assertFalse((self.repo / '.myagentkit/usage').exists())
        result = self.run_wrapper('--uncommitted', REVIEW_CLAUDE_MODEL='claude-fable-5-1',
                                  MYAGENTKIT_AUTHOR_EFFORT='medium', REVIEW_EFFORT='high', **fable)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('REVIEW [top tier]:', result.stdout)
        chain = json.loads(result.stdout.split('review dispatch: ', 1)[1].splitlines()[0])
        self.assertEqual(chain['top_tier_review'], {'author_effort': 'medium', 'effort': 'high'})
        self.assertNotIn('same_tier_exception', chain)
        usage = json.loads(Path(chain['attempts'][0]['usage_record']).read_text())
        self.assertEqual((usage['task']['author'], usage['task']['author_effort']), ('claude-fable-5-1', 'medium'))
        # Owner decision 64: the requirement is capped at high, so an xhigh or max author's own tier
        # at high is the required review.
        for author_effort in ('xhigh', 'max'):
            result = self.run_wrapper('--uncommitted', REVIEW_CLAUDE_MODEL='claude-fable-5-1', REVIEW_EFFORT='high',
                                      MYAGENTKIT_AUTHOR_EFFORT=author_effort, MYAGENTKIT_TASK_ID='top-' + author_effort,
                                      **fable)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            chain = json.loads(result.stdout.split('review dispatch: ', 1)[1].splitlines()[0])
            self.assertEqual(chain['top_tier_review'], {'author_effort': author_effort, 'effort': 'high'})
        # Owner decision 66: with the author's effort unnamed and no review effort named, the
        # required review runs at high, not refused; for a top-tier author too.
        for author, label in (('claude-opus-5-5', 'unnamed-opus'), ('claude-fable-5-1', 'unnamed-fable')):
            result = self.run_wrapper('--uncommitted', REVIEW_CLAUDE_MODEL='claude-fable-5-1',
                                      MYAGENTKIT_TASK_ID=label, **dict(fable, MYAGENTKIT_AUTHOR=author))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('REVIEW [about to run]: claude model claude-fable-5-1, effort high', result.stdout)
            chain = json.loads(result.stdout.split('review dispatch: ', 1)[1].splitlines()[0])
            self.assertEqual(chain.get('top_tier_review'), {'author_effort': 'high', 'effort': 'high'}
                             if author == 'claude-fable-5-1' else None)
        result = self.run_wrapper('--uncommitted', REVIEW_CLAUDE_MODEL='claude-opus-5-5', REVIEW_SHADOW='1',
                                  MYAGENTKIT_TASK_ID='extra-opinion', **fable)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIs(json.loads(result.stdout.split('review dispatch: ', 1)[1].splitlines()[0])['shadow'], True)

    def test_a_substitute_stands_to_the_author_as_the_primary_does(self):
        # #290: the quota switch to Claude is blocked for a weaker tier than the author's, and the
        # top tier's own substitute runs at the author's effort or above, recorded.
        fable = dict(CODEX_FIXTURE_CASE='quota', MYAGENTKIT_AUTHOR='claude-fable-5-1', MYAGENTKIT_AUTHOR_EFFORT='high',
                     REVIEW_EFFORT='high')
        result, chain = self.dispatch_result('codex', fallback=False, MYAGENTKIT_TASK_ID='sub-below', **fable)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual([a['reviewer'] for a in chain['attempts']], ['codex'])
        self.assertIn('a weaker tier than author claude-fable-5-1', chain['fallback_blocked'])
        result, chain = self.dispatch_result('codex', fallback=False, MYAGENTKIT_TASK_ID='sub-top',
                                             REVIEW_CLAUDE_MODEL='claude-fable-5-1', **fable)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([a['reviewer'] for a in chain['attempts']], ['codex', 'claude'])
        self.assertEqual(chain['top_tier_review'], {'author_effort': 'high', 'effort': 'high'})
        self.assertIn('REVIEW [top tier]:', result.stdout)
        # rsel3: a top-tier substitute below the author's effort (named, or unnamed and so high,
        # decision 66) is blocked with its reason, never run. Only a shadow primary reaches it:
        # decision 65 refuses a required primary at that effort before it runs.
        for label, extra in (('sub-top-unset', dict(MYAGENTKIT_AUTHOR_EFFORT='', REVIEW_EFFORT='medium',
                                                    REVIEW_SHADOW='1')),
                             ('sub-top-medium', dict(REVIEW_EFFORT='medium', REVIEW_SHADOW='1'))):
            with self.subTest(label=label):
                result, chain = self.dispatch_result('codex', fallback=False, MYAGENTKIT_TASK_ID=label,
                                                     REVIEW_CLAUDE_MODEL='claude-fable-5-1', **dict(fable, **extra))
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn('Traceback', result.stdout + result.stderr)
                self.assertEqual([a['reviewer'] for a in chain['attempts']], ['codex'])
                self.assertIn('review effort medium is below', chain['fallback_blocked'])
                self.assertNotIn('top_tier_review', chain)
        # rsel3: when the top tier's own review fails and the other family substitutes, the record
        # describes the substitute, not the failed primary.
        result, chain = self.dispatch_result('claude', MYAGENTKIT_TASK_ID='sub-other', REVIEW_CLAUDE_MODEL='claude-fable-5-1',
                                             **dict(fable, FIXTURE_CASE='quota', CODEX_FIXTURE_CASE='accept'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([a['reviewer'] for a in chain['attempts']], ['claude', 'codex'])
        self.assertNotIn('top_tier_review', chain)

    def test_one_ladder_tier_in_any_version_is_one_tier(self):
        # Owner decision 65: gpt-6-astra and gpt-6.1-astra are one tier, so the top tier's effort
        # floor and the same-tier refusal hold across a version bump; Claude ids go by family name.
        from unittest.mock import patch
        import review_dispatch
        with patch.dict(os.environ, MYAGENTKIT_AUTHOR_EFFORT='high'):
            self.assertEqual(review_dispatch.tier('gpt-6.1-astra'), review_dispatch.tier('openai/gpt-6-astra'))
            self.assertEqual(review_dispatch.tier('gpt-5.5'), 'gpt-5.5')
            self.assertEqual(review_dispatch.judge('gpt-6.1-astra', 'gpt-6-astra', 'high'), ('top', None))
            kind, why = review_dispatch.judge('gpt-6.1-astra', 'gpt-6-astra', 'low')
            self.assertEqual(kind, 'top')
            self.assertIn('review effort low is below', why)
            self.assertEqual(review_dispatch.judge('gpt-6-sol', 'gpt-6.1-sol', 'high')[0], 'same')
            self.assertEqual(review_dispatch.judge('claude-opus-5', 'claude-opus-5-5', 'high')[0], 'same')
            self.assertEqual(review_dispatch.judge('gpt-6-astra', 'gpt-6.1-sol', 'high'), (None, None))

    def test_a_substitute_of_the_author_tier_is_blocked(self):
        # KARARLAR B01 (1) with lead decision 7: a used-up Codex quota switches to Claude, but never
        # to the author's family; --fallback is blocked the same way.
        for fallback in (False, True):
            with self.subTest(fallback=fallback):
                result, chain = self.dispatch_result('codex', fallback=fallback, CODEX_FIXTURE_CASE='quota',
                                                     MYAGENTKIT_AUTHOR='claude-opus-5',
                                                     MYAGENTKIT_TASK_ID='author-sub-%s' % fallback)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual([a['reviewer'] for a in chain['attempts']], ['codex'])
                self.assertIn("the author's tier", chain['fallback_blocked'])

    def test_author_aliases_resolve_to_their_tier_and_a_bare_family_is_refused(self):
        # #181: an alias or a vendor-prefixed id of the pinned tier is refused like the id; a
        # value naming no model tier is refused too, since it compared equal to no pin.
        env = dict(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLAUDE_MODEL='claude-opus-5')
        for author in ('opus', 'Opus 5.5', 'claude/opus', 'us.anthropic.claude-opus-5-v1:0'):
            with self.subTest(author=author):
                result = self.run_wrapper('--uncommitted', MYAGENTKIT_AUTHOR=author, **env)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('the author never reviews its own patch', result.stdout)
        for author in ('claude', 'anthropic', 'claude-code', 'codex', 'openai', 'claude/fixture-author',
                       'claude-cli', 'claude-desktop', 'claude-agent'):
            with self.subTest(author=author):
                result = self.run_wrapper('--uncommitted', MYAGENTKIT_AUTHOR=author, **env)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('names no model tier', result.stdout)
        self.assertFalse((self.repo / '.myagentkit/usage').exists())
        # A Codex id inside a longer value is that id's tier, so the author's own Codex pin is refused.
        import review_dispatch
        for author in ('codex gpt-5.5', 'gpt-5.5 xhigh', 'openai/gpt-5.5', 'GPT-5.5'):
            with self.subTest(author=author):
                self.assertEqual(review_dispatch.author_tier(author), review_dispatch.tier('gpt-5.5'))

    def test_the_same_tier_exception_runs_only_for_a_named_high_tier_review(self):
        # #179: the owner's exception (a plan with no tier above the author's) is named in the
        # run, high tier and high effort only, and recorded in the chain.
        env = dict(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLAUDE_MODEL='claude-opus-5',
                   MYAGENTKIT_AUTHOR='claude-opus-5-5', REVIEW_SAME_TIER_EXCEPTION='plan without Fable')
        for extra in ({}, {'REVIEW_RISK': 'high', 'REVIEW_EFFORT': 'medium'}):
            with self.subTest(extra=extra):
                result = self.run_wrapper('--uncommitted', **env, **extra)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('for a high-tier change only', result.stdout)
        result = self.run_wrapper('--uncommitted', REVIEW_RISK='high', **env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('REVIEW [same tier]:', result.stdout)
        chain = json.loads(result.stdout.split('review dispatch: ', 1)[1].splitlines()[0])
        self.assertEqual(chain['same_tier_exception'], 'plan without Fable')

    def test_a_substitute_of_the_author_tier_runs_under_the_exception_recorded_and_printed(self):
        # #179 r1: the quota switch and --fallback to the author's tier run under the exception,
        # so the chain records it and the console says so, as for the primary reviewer.
        for fallback, case in ((False, 'quota'), (True, 'mcp_exit')):
            with self.subTest(fallback=fallback):
                result, chain = self.dispatch_result('codex', fallback=fallback, CODEX_FIXTURE_CASE=case,
                                                     MYAGENTKIT_AUTHOR='claude-opus-5-5', REVIEW_RISK='high',
                                                     REVIEW_SAME_TIER_EXCEPTION='plan without Fable',
                                                     MYAGENTKIT_TASK_ID='same-sub-%s' % fallback)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual([a['reviewer'] for a in chain['attempts']], ['codex', 'claude'])
                self.assertEqual(chain['same_tier_exception'], 'plan without Fable')
                self.assertIn('REVIEW [same tier]: author claude-opus-5-5 and reviewer claude model '
                              'claude-opus-5', result.stdout)

    def test_the_same_tier_exception_is_one_round_per_label(self):
        # Owner decision 2026-10-19 (docs/WORKFLOW.md, "Model routing", rule 7: "one round"): a
        # second round under the exception for the label is refused, for the requested reviewer
        # and a quota-switch substitute alike, REVIEW_ROUND_EXCEPTION (set by dispatch_result) too.
        # Another tier still reviews the fix under the label.
        refused = 'already had its round under REVIEW_SAME_TIER_EXCEPTION'
        exception = dict(MYAGENTKIT_AUTHOR='claude-opus-5-5', REVIEW_RISK='high',
                         REVIEW_SAME_TIER_EXCEPTION='plan without Fable', MYAGENTKIT_TASK_ID='same-once')
        result, chain = self.dispatch_result('claude', fallback=False, **exception)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        usage = json.loads(Path(chain['attempts'][0]['usage_record']).read_text())
        self.assertEqual(usage['task']['same_tier_exception'], 'plan without Fable')
        result, chain = self.dispatch_result('claude', fallback=False, **exception)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIsNone(chain)
        self.assertIn(refused, result.stdout)
        result, chain = self.dispatch_result('codex', fallback=False, CODEX_FIXTURE_CASE='quota', **exception)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual([a['reviewer'] for a in chain['attempts']], ['codex'])
        self.assertIn(refused, chain['fallback_blocked'])
        self.assertNotIn('same_tier_exception', chain)
        result, chain = self.dispatch_result('codex', fallback=False, **exception)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        usage = json.loads(Path(chain['attempts'][0]['usage_record']).read_text())
        self.assertNotIn('same_tier_exception', usage['task'])

    def test_the_same_tier_exception_is_one_round_per_label_and_focus(self):
        # Owner decision 56 (2026-10-19), rtier review r1 High: a round under the exception counts
        # for its own focus, one without a focus for every focus. The two focus reviewers run under
        # it one after the other or in parallel; a second round of either, or a run without a
        # focus, is refused. A round the 98591eb dispatcher marked only in its chain checkpoint
        # counts too.
        from unittest.mock import patch
        refused = 'already had its round under REVIEW_SAME_TIER_EXCEPTION'
        head = self.git('rev-parse', 'HEAD').stdout.decode().strip()

        def preflight(label, focus):  # the dispatcher's check before an attempt under the exception
            with patch.dict(os.environ, {bridge.SAME_TIER_ENV: 'plan without Fable'}):
                os.environ.pop('REVIEW_FOCUS', None)
                if focus:
                    os.environ['REVIEW_FOCUS'] = focus
                bridge.prior_rounds(self.repo, label, 'uncommitted', None, head, '')
        marked = {bridge.SAME_TIER_ENV: 'plan without Fable', 'MYAGENTKIT_TASK_ID': 'same-focus'}
        preflight('same-focus', 'logic')  # in parallel, both pass before either round is recorded
        preflight('same-focus', 'portability')
        for focus in ('logic', 'portability'):
            code, result = self.run_bridge('reject', env_extra=dict(marked, REVIEW_FOCUS=focus))
            self.assertEqual(code, 0, result)
        for focus in ('logic', 'portability', None):
            with self.subTest(focus=focus), self.assertRaisesRegex(bridge.BridgeError, refused):
                preflight('same-focus', focus)
        code, result = self.run_bridge('reject', env_extra=dict(marked, MYAGENTKIT_TASK_ID='same-plain'))
        self.assertEqual(code, 0, result)
        with self.assertRaisesRegex(bridge.BridgeError, refused):
            preflight('same-plain', 'logic')
        legacy = dict(MYAGENTKIT_TASK_ID='same-legacy', MYAGENTKIT_REVIEW_CHAIN_ID='legacy',
                      MYAGENTKIT_REVIEW_ATTEMPT='1')
        code, result = self.run_bridge('reject', env_extra=legacy)
        self.assertEqual(code, 0, result)
        preflight('same-legacy', None)
        (self.repo / '.myagentkit/usage/chains').mkdir(exist_ok=True)
        (self.repo / '.myagentkit/usage/chains/legacy-1.json').write_text(json.dumps(
            {'status': 'completed', 'attempts': [{'status': 'completed'}],
             'same_tier_exception': 'plan without Fable'}), encoding='utf-8')
        with self.assertRaisesRegex(bridge.BridgeError, refused):
            preflight('same-legacy', None)

    def test_a_focus_without_its_exception_round_takes_a_substitute_of_the_author_tier(self):
        # rtier review r1 Medium: logic used its round under the exception and portability did
        # not, so portability's quota switch to the author's tier runs; its next substitute
        # (--fallback this time) is refused.
        refused = 'already had its round under REVIEW_SAME_TIER_EXCEPTION'
        exception = dict(MYAGENTKIT_AUTHOR='claude-opus-5-5', REVIEW_RISK='high',
                         REVIEW_SAME_TIER_EXCEPTION='plan without Fable', MYAGENTKIT_TASK_ID='same-medium')
        result, chain = self.dispatch_result('claude', fallback=False, REVIEW_FOCUS='logic', **exception)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result, chain = self.dispatch_result('codex', fallback=False, REVIEW_FOCUS='portability', **exception)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result, chain = self.dispatch_result('codex', fallback=False, CODEX_FIXTURE_CASE='quota',
                                             REVIEW_FOCUS='portability', **exception)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([a['reviewer'] for a in chain['attempts']], ['codex', 'claude'])
        self.assertEqual(chain['same_tier_exception'], 'plan without Fable')
        result, chain = self.dispatch_result('codex', fallback=True, CODEX_FIXTURE_CASE='mcp_exit',
                                             REVIEW_FOCUS='portability', **exception)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual([a['reviewer'] for a in chain['attempts']], ['codex'])
        self.assertIn(refused, chain['fallback_blocked'])

    def test_a_used_up_codex_quota_switches_to_another_tier_of_a_claude_author(self):
        # #225: the switch checks the tier, so a Claude author's review goes to another Claude
        # tier; an unknown author blocks it, and the hint names MYAGENTKIT_AUTHOR, not --fallback.
        result, chain = self.dispatch_result('codex', fallback=False, CODEX_FIXTURE_CASE='quota',
                                             MYAGENTKIT_AUTHOR='claude-sonnet-5', MYAGENTKIT_TASK_ID='switch-sonnet')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([a['reviewer'] for a in chain['attempts']], ['codex', 'claude'])
        result, chain = self.dispatch_result('codex', fallback=False, CODEX_FIXTURE_CASE='quota',
                                             MYAGENTKIT_AUTHOR='', MYAGENTKIT_TASK_ID='switch-unknown')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual([a['reviewer'] for a in chain['attempts']], ['codex'])
        self.assertIn('set MYAGENTKIT_AUTHOR', chain['fallback_blocked'])
        self.assertIn('after fixing what blocked the substitute', result.stdout)
        self.assertNotIn('--fallback on the other', result.stdout)

    def test_an_unreadable_checkout_after_a_review_fails_the_chain_without_calling_it_changed(self):
        # Lead-found (#258 follow-up): once the reviewer ran, every look at the checkout (the
        # adapter's and the dispatcher's) fails. A failed read proves no change: the chain fails as
        # checkout_unverified, the record stays completed and the round counts. A refusal (a dirty
        # tree for a reference review) proves a change: stale_checkout, round not counted.
        import contextlib
        import review_dispatch as dispatch
        from unittest.mock import patch
        bridge = dispatch.claude_bridge
        snapshot, run = bridge.snapshot, dispatch.agent_process.run
        cases = [(provider, error, kind, {}) for provider in ('claude', 'codex') for error, kind in (
            (bridge.GitFailed('git diff failed: index cannot be read'), 'checkout_unverified'),
            (bridge.BridgeError('reference reviews require a clean checkout; use --uncommitted'),
             'stale_checkout'))]
        # rtier review r1: under the same-tier exception that round was the label's one, so the
        # FAIL line names the next reviewer, not a rerun the tooling refuses.
        cases.append(('claude', bridge.GitFailed('git diff failed: index cannot be read'), 'checkout_unverified',
                      dict(MYAGENTKIT_AUTHOR='claude-opus-5-5', REVIEW_RISK='high',
                           REVIEW_SAME_TIER_EXCEPTION='plan without Fable')))
        for provider, error, kind, exception in cases:
            with self.subTest(provider=provider, kind=kind, exception=bool(exception)):
                ran = []

                def look(*args):
                    if ran:
                        raise error
                    return snapshot(*args)

                def review(*args, **kwargs):
                    ran.append(True)
                    return run(*args, **kwargs)
                env = self.review_env(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLAUDE_MODEL='claude-opus-5',
                                      REVIEW_CLI_BIN=str(self.build_fake_codex()), REVIEW_CODEX_MODEL='gpt-5.5',
                                      MYAGENTKIT_TASK_ID='unread-%s-%s-%s' % (provider, kind, bool(exception)),
                                      **exception)
                out = io.StringIO()
                with patch.dict(os.environ, env, clear=True), patch.object(bridge, 'snapshot', look), \
                        patch.object(dispatch.agent_process, 'run', review), contextlib.redirect_stdout(out):
                    code = dispatch.main(['--repo', str(self.repo), '--reviewer', provider, '--uncommitted'])
                self.assertEqual(code, 5, out.getvalue())
                chain = json.loads(out.getvalue().split('review dispatch: ', 1)[1].splitlines()[0])
                self.assertEqual(chain['failure_kind'], kind)
                record = json.loads(Path(chain['attempts'][-1]['usage_record']).read_text(encoding='utf-8'))
                counted = bridge.chain_failure(self.repo / '.myagentkit/usage', chain['chain_id'],
                                               record['review_attempt']) is None
                if kind == 'checkout_unverified':
                    self.assertNotIn('checkout_changed', chain)
                    self.assertEqual(record['status'], 'completed')
                    self.assertTrue(counted)
                    self.assertIn('still counts as a round', out.getvalue())
                    self.assertIn('index cannot be read', out.getvalue())
                    self.assertEqual('then run the review again' in out.getvalue(), not exception)
                    self.assertEqual("the other family or the owner's diff read" in out.getvalue(),
                                     bool(exception))
                else:
                    self.assertIs(chain.get('checkout_changed'), True)
                    self.assertNotIn('checkout_unverified', chain)

    def test_a_secret_looking_file_in_scope_stops_the_review_unless_allowed_by_name(self):
        # KARARLAR B12 inv2#106: tracked or not, a file that looks like a secret is in the copy the
        # reviewer reads and in the diff it is sent, so the review is refused before any model
        # runs; the owner adds it to .gitignore or names it with --allow-secret-file PATH.
        env = dict(CLAUDE_CLI_BIN=str(self.fixture), REVIEW_CLAUDE_MODEL='claude-opus-5')
        for name in ('.env', 'config/.env.production', '.dev.vars', 'deploy/server.pem', 'tls/site.key',
                     '.npmrc', '.netrc', 'aws/credentials', 'credentials.json'):
            for tracked in (False, True):
                with self.subTest(name=name, tracked=tracked):
                    path = self.repo / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('TOKEN=private-value\n')
                    if tracked:
                        self.git('add', '--', name)
                    result = self.run_wrapper('--uncommitted', **env)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn('looks like a secret file', result.stdout)
                    self.assertIn('--allow-secret-file ' + name, result.stdout)
                    self.assertFalse((self.repo / '.myagentkit/usage').exists())
                    allowed = self.run_wrapper('--uncommitted', '--allow-secret-file', name, **env)
                    self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
                    if tracked:
                        self.git('rm', '-q', '--cached', '--', name)
                    path.unlink()
                    shutil.rmtree(self.repo / '.myagentkit/usage', ignore_errors=True)
        # One flag names one path: a line break inside it (the dispatcher and the adapters are
        # called directly too, past the shell wrapper) widened one allowance to two secrets
        # (batch 4 round-1 Critical).
        import claude_bridge
        import review_dispatch
        (self.repo / '.env').write_text('TOKEN=private-value\n')
        (self.repo / 'site.key').write_text('KEY=private-value\n')
        for joined in ('.env\nsite.key', '.env\rsite.key', '.env\0site.key'):
            with self.subTest(joined=joined):
                with self.assertRaisesRegex(ValueError, 'one path per --allow-secret-file'):
                    claude_bridge.allow_secret_files([joined])
                with self.assertRaisesRegex(ValueError, 'one path per --allow-secret-file'):
                    review_dispatch.main(['--repo', str(self.repo), '--uncommitted', '--reviewer', 'claude',
                                          '--allow-secret-file', joined])
                self.assertFalse((self.repo / '.myagentkit/usage').exists())
        (self.repo / '.env').unlink()
        (self.repo / 'site.key').unlink()
        # A template is no secret, and a committed one stays reviewable.
        for name in ('.env.example', '.env.sample', '.env.template'):
            (self.repo / name).write_text('TOKEN=\n')
        result = self.run_wrapper('--uncommitted', **env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_backend_files_live_outside_the_repository_by_default(self):
        # KARARLAR D09 inv2#80 and LIDER 10: a checkout can never provide or change a backend file,
        # so it lives in MYAGENTKIT_BACKENDS_DIR (else the user's config folder); the old
        # .myagentkit/backends/ is still read during the move, with a note.
        import review_dispatch
        for key in [key for key in os.environ if key.startswith('ANTHROPIC_')]:
            del os.environ[key]
        text = ''.join('%s=%s\n' % item for item in self.BACKEND.items())
        user = self.root / 'user-backends'
        user.mkdir()
        (user / 'glm.env').write_text(text)
        log = self.root / 'env.json'
        result = self.run_wrapper('--uncommitted', '--backend', 'glm', CLAUDE_CLI_BIN=str(self.fixture),
                                  REVIEW_CLAUDE_MODEL='claude-opus-5', ENV_LOG=str(log))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(log.read_text()), self.BACKEND)
        self.assertNotIn('NOTE [review]: backend glm is read from', result.stdout + result.stderr)
        self.assertEqual(review_dispatch.load_backend(self.repo, 'glm')[1], 'glm-fixture')
        # The old place, while the new one has no file: read, with the move named.
        (user / 'glm.env').unlink()
        self.backend_file(text)
        result = self.run_wrapper('--uncommitted', '--backend', 'glm', CLAUDE_CLI_BIN=str(self.fixture),
                                  REVIEW_CLAUDE_MODEL='claude-opus-5', ENV_LOG=str(log))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('NOTE [review]: backend glm is read from', result.stdout + result.stderr)
        self.assertIn(str(user), result.stdout + result.stderr)
        # A backend folder inside the checkout is the checkout providing the file: refused.
        os.environ['MYAGENTKIT_BACKENDS_DIR'] = str(self.repo / 'private')
        with self.assertRaisesRegex(ValueError, 'outside the repository'):
            review_dispatch.load_backend(self.repo, 'glm')
        # The reviewer is denied the folder by its absolute path, as the old one.
        from types import SimpleNamespace
        os.environ['MYAGENTKIT_BACKENDS_DIR'] = str(user)
        args = SimpleNamespace(repo=self.repo, mode='review', model='claude-opus-5', effort='high',
                               max_turns=2, max_budget_usd=None)
        folder = str(user.resolve()).replace('\\', '/')
        for sandboxed in (False, True):
            with self.subTest(sandboxed=sandboxed):
                command, _ = bridge.claude_command('claude', args, sandboxed)
                settings = json.loads(command[command.index('--settings') + 1])
                self.assertIn('Read(//' + folder.lstrip('/') + '/**)', settings['permissions']['deny'])
                if sandboxed:
                    self.assertIn(folder, settings['sandbox']['filesystem']['denyRead'])

    def test_a_quoted_backend_value_is_unquoted_and_a_missing_file_names_the_backend_folder(self):
        # #277: a dotenv-style quoted value kept its quotes (the token reached the endpoint with
        # them, a quoted model read as "no model"); a missing file named only the old place.
        import review_dispatch
        user = self.root / 'quoted-backends'
        user.mkdir()
        (user / 'q.env').write_text('ANTHROPIC_BASE_URL="https://x"\nANTHROPIC_AUTH_TOKEN=\'sk-1\'\n'
                                    'ANTHROPIC_MODEL="glm-4"\n')
        os.environ['MYAGENTKIT_BACKENDS_DIR'] = str(user)
        env, model = review_dispatch.load_backend(self.repo, 'q')
        self.assertEqual((env['ANTHROPIC_BASE_URL'], env['ANTHROPIC_AUTH_TOKEN'], model), ('https://x', 'sk-1', 'glm-4'))
        with self.assertRaises(ValueError) as caught:
            review_dispatch.load_backend(self.repo, 'missing')
        self.assertIn(str(user), str(caught.exception))
        self.assertIn('is not in the backend folder', str(caught.exception))
        self.assertNotIn('Git-ignored', str(caught.exception))

    def test_the_codex_prompt_names_the_clean_review_form_the_parser_accepts(self):
        # fix4 notes: make prompt and allowlist agree, so a clean paid review is not lost as
        # invalid_evidence for prose the parser does not read as a placeholder.
        for reviewer in ('claude', 'codex'):
            with self.subTest(reviewer=reviewer):
                log = self.root / (reviewer + '-prompt.txt')
                result = self.run_wrapper('--uncommitted', '--reviewer', reviewer,
                                          CLAUDE_CLI_BIN=str(self.fixture),
                                          REVIEW_CLI_BIN=str(self.build_fake_codex()),
                                          REVIEW_CLAUDE_MODEL='claude-opus-5',
                                          REVIEW_CODEX_MODEL='fixture-codex-model', PROMPT_LOG=str(log))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                prompt = log.read_text(encoding='utf-8')
                if reviewer == 'codex':
                    self.assertIn("With no finding, write the one item '- None.' under '## Findings'", prompt)
                self.assertIn('A NOT RUN or "could not verify" line is a manual check', prompt)
                self.assertIn("put it under '## Manual checks' and use Accept with Manual Checks", prompt)
                self.assertIn("For a plain Accept, write None. under '## Manual checks' and nothing after it.", prompt)
        self.assertTrue(bridge.accept_allows(['- None.']))

    def test_the_reviewer_runs_only_the_narrow_test_never_the_full_suite(self):
        # Owner decision 2026-10-16: reviewers that ran the 30-minute full suite in their copy
        # took 40-60 minutes (one cut at the 3600 s cap); told not to, a review took 2.5 minutes.
        # The lead's gate runs the full suite once (ai-review-workflows.md 1.7 [22], 1.4 [7]).
        line = ("Do not run the project's full suite (scripts/check.sh, check_kit or a "
                "whole test run); run only the narrow test that proves or disproves a finding. The "
                "lead's gate runs the full suite.")
        self.assertIn(line, bridge.REVIEW_PROMPT)
        for text in (bridge.REVIEW_RUNS, bridge.REVIEW_READS):
            self.assertNotIn('the suite', text)

    def test_a_reviewer_with_a_shell_is_told_what_its_copy_lacks(self):
        # #122: the copy holds no file Git ignores and the reviewer has no network, so a build
        # that needs a build tree, a dependency or a venv cannot run; told nothing, reviewers
        # spent turns on builds that could not succeed.
        self.assertIn("The copy holds no files Git ignores (build tree, installed dependencies, "
                      "virtual environment) and has no network: a check that needs them is NOT RUN; "
                      "do not build or download them.", bridge.REVIEW_RUNS)

    def test_a_setup_fault_or_failed_authentication_never_fails_over(self):
        # KARARLAR D04 inv2#44: a setup fault (authentication among them) is fixed, never failed
        # over: the other reviewer would only hide it, and it fails the same way next time.
        for case in ('auth', 'unknown_flag'):
            with self.subTest(case=case):
                result, chain = self.dispatch_result(FIXTURE_CASE=case, MYAGENTKIT_TASK_ID='setup-' + case)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual([a['reviewer'] for a in chain['attempts']], ['claude'])
                self.assertIn(chain['failure_kind'], ('authentication', 'cli_unsupported'))
        import review_dispatch
        self.assertEqual(review_dispatch.UNAVAILABLE, {
            'rate_limited', 'quota_exhausted', 'timeout', 'unavailable', 'cli_error', 'context_limit',
            'budget_or_turn_limit', 'output_limit', 'content_flagged'})

    def test_an_exhausted_codex_quota_switches_the_review_to_claude(self):
        # Lead decision of 2026-10-15 (the single-model mandate): quota_exhausted switches the
        # role to Claude automatically, recorded and reported; no --fallback is needed for it.
        result, chain = self.dispatch_result('codex', fallback=False, CODEX_FIXTURE_CASE='quota')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([(a['reviewer'], a['failure_kind']) for a in chain['attempts']],
                         [('codex', 'quota_exhausted'), ('claude', None)])
        self.assertEqual(chain['selected_reviewer'], 'claude')
        self.assertIn('quota_exhausted', chain['switched'])
        self.assertIn('SWITCH [review]: codex quota is exhausted', result.stdout)
        # #121: the record written before the switch says it follows; the last one names none.
        first = Path(chain['chain_record']).with_name(Path(chain['chain_record']).name.replace('-2.json', '-1.json'))
        self.assertEqual(json.loads(first.read_text())['next_attempt'], {'reviewer': 'claude', 'why': 'quota switch'})
        self.assertNotIn('next_attempt', chain)
        self.assertIn('FALLBACK REVIEWER: the requested reviewer codex (quota_exhausted)',
                      Path(chain['attempts'][1]['evidence']).read_text())
        # Claude's own exhausted quota switches nothing: without --fallback the review fails.
        result, chain = self.dispatch_result('claude', fallback=False, FIXTURE_CASE='quota',
                                             MYAGENTKIT_TASK_ID='claude-exhausted')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual([a['reviewer'] for a in chain['attempts']], ['claude'])
        self.assertIn('quota is exhausted', result.stdout)

    def test_a_codex_capacity_error_is_retried_twice_with_a_doubling_delay(self):
        # KARARLAR B01 (6) inv2#46: a Codex capacity error passes; it is retried after the delay
        # the tool reports, else after about ten minutes, doubled, at most twice. A quota is not.
        from contextlib import redirect_stdout
        from unittest.mock import patch
        import review_dispatch

        def execution(command, prompt, repo, timeout, into=None, noted=None, watch=None):
            calls.append(1)
            if len(calls) <= failures:
                message = 'Selected model is at capacity.' + hint
                return {'exit_code': 1, 'stdout': json.dumps({'type': 'turn.failed', 'error': {'message': message}}),
                        'stderr': '', 'termination': None, 'duration_ms': 1}
            Path(command[command.index('-o') + 1]).write_bytes(b'## Findings\n\n- None.\n\nVERDICT: Accept\n')
            return {'exit_code': 0, 'stdout': json.dumps({'type': 'turn.completed', 'usage': {}}),
                    'stderr': '', 'termination': None, 'duration_ms': 1}

        for failures, hint, waits, status in ((1, '', [600], 'completed'),
                                              (2, ' Please try again in 30 seconds.', [30, 60], 'completed'),
                                              (3, '', [600, 1200], 'failed'),
                                              # "0 seconds" is a delay, not a missing one (batch 4 r1 High).
                                              (1, ' Please try again in 0 seconds.', [0], 'completed')):
            calls, slept, flags, pending, out = [], [], [], [], io.StringIO()

            def sleep(delay):
                # #280: the checkpoint written before the wait says a retry follows.
                slept.append(delay)
                chain_id = os.environ['MYAGENTKIT_REVIEW_CHAIN_ID']
                newest = max((self.repo / '.myagentkit/usage/chains').glob(chain_id + '-*.json'),
                             key=lambda path: int(path.stem.rpartition('-')[2]))
                record = json.loads(newest.read_text())
                flags.append(record['recovery']['automatic_retry'])
                # #121: the record also names the attempt that follows and when.
                pending.append(record['next_attempt']['reviewer'] == 'codex'
                               and 'rate_limited retry' in record['next_attempt']['why']
                               and bool(record['next_attempt']['not_before']))

            with self.subTest(failures=failures, hint=hint), patch.dict(os.environ, self.review_env(
                    MYAGENTKIT_TASK_ID='capacity-%d' % failures,
                    REVIEW_ROUND_EXCEPTION='fixture: retries are rounds of one label')), \
                    patch('agent_process.run', side_effect=execution), \
                    patch.object(review_dispatch, 'sleep', side_effect=sleep), redirect_stdout(out):
                code = review_dispatch.main(['--repo', str(self.repo), '--uncommitted', '--reviewer', 'codex',
                                             '--claude-model', 'claude-opus-5', '--codex-model', 'fixture-codex-model'])
                chain = json.loads(out.getvalue().split('review dispatch: ', 1)[1].splitlines()[0])
                self.assertEqual(slept, waits)
                self.assertEqual(flags, [True] * len(waits))
                self.assertEqual(pending, [True] * len(waits))
                self.assertNotIn('next_attempt', chain)
                self.assertIs(chain['recovery']['automatic_retry'], False)
                self.assertEqual(len(calls), len(waits) + 1)
                self.assertEqual([a['reviewer'] for a in chain['attempts']], ['codex'] * len(calls))
                self.assertEqual(chain['status'], status, out.getvalue())
                self.assertEqual(code, 0 if status == 'completed' else 5)
                self.assertIn('RETRY [review]: codex is at capacity (rate_limited)', out.getvalue())


if __name__ == "__main__":
    if sys.argv[1:2] == ['--review-shard']:
        raise SystemExit(run_review_shard(*sys.argv[2:]))
    keep_output_writable(sys.stdout)
    keep_output_writable(sys.stderr)
    from test_agent_usage import UsageTests
    from test_codex_quota import QuotaTests
    minimums =WINDOWS_SUITE_MINIMUMS if WINDOWS else SUITE_MINIMUMS
    suites = []
    for case, name in ((BridgeTests, 'test_claude_bridge'), (UsageTests, 'test_agent_usage'),
                       (QuotaTests, 'test_codex_quota')):
        minimum = minimums[name]
        tests = unittest.defaultTestLoader.loadTestsFromTestCase(case)
        if name == 'test_claude_bridge':
            tests.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(ReviewPreflightTests))
        if tests.countTestCases() < minimum:
            raise SystemExit("FAIL: %s has %d of at least %d tests; a suite that did not run is "
                             "not a pass" % (case.__name__, tests.countTestCases(), minimum))
        suites.append((tests, minimum))
    # Refuse an absent companion before spending time on the other suites. Acceptance
    # empties a companion deliberately; it must reach that failure within its time limit.
    for index, (tests, minimum) in enumerate(suites):
        runner = run_review_shards if index == 0 else run_quietly
        if not runner(tests, minimum=minimum):
            raise SystemExit(1)
    print("Suite minimums met: " + ", ".join("%s %d" % item for item in sorted(minimums.items())))
    print("REVIEW SELF-TEST: PASS")
