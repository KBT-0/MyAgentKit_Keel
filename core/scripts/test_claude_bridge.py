"""Offline end-to-end evidence and permission regressions; never calls a paid CLI."""
import hashlib
import importlib.util
import io
import json
import os
import re
from pathlib import Path
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
INHERITED_CONTROLS = ('REVIEW_DISPOSITIONS', 'MYAGENTKIT_TASK_ID', 'MYAGENTKIT_REVIEW_CHAIN_ID',
                      'MYAGENTKIT_REVIEW_ATTEMPT', 'MYAGENTKIT_REVIEW_FALLBACK_FROM',
                      'MYAGENTKIT_REQUESTER', 'CLAUDE_REVIEW_DOCS')
# Per suite, not a combined total: as one suite grew, an emptied neighbour could hide inside
# the sum and the self-test passed without running its checks. Each is the suite's current
# count, so a suite that loses a test fails too; a new test raises it. The kit gate reads this.
SUITE_MINIMUMS = {'test_claude_bridge': 126, 'test_agent_usage': 20, 'test_codex_quota': 5}
BRIDGE = ROOT / "claude_bridge.py"
spec = importlib.util.spec_from_file_location("bridge", BRIDGE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

# A fallback named python or py may be the only Python command on PATH.
# A launcher sh and Python both read: sh runs `:` then execs the (quoted: a path with a
# space) interpreter on this file; Python sees a string literal and goes on.
PYTHON_SHEBANG = "#!/bin/sh\n''':'\nexec %s \"$0\" \"$@\"\n'''\n" % shlex.quote(sys.executable)

FIXTURE = PYTHON_SHEBANG + '''import json, os, pathlib, sys, time
args = sys.argv[1:]
# A review executes in the throwaway copy; a proposal stays read-only.
review = 'verdict' in args[args.index('--json-schema') + 1]
assert args[args.index('--tools') + 1] == ('Read,Glob,Grep,Bash' if review else 'Read,Glob,Grep')
assert (args[args.index('--allowed-tools') + 1] == 'Bash') if review else '--allowed-tools' not in args
assert args[args.index('--permission-mode') + 1] == 'dontAsk'
assert '--safe-mode' in args and '--restricted' in args
assert '--strict-mcp-config' in args and '--no-session-persistence' in args
assert '--dangerously-skip-permissions' not in args
assert '--resume' not in args and '--continue' not in args
assert os.environ['MYAGENTKIT_DELEGATION_DEPTH'] == '1'
prompt = sys.stdin.read()
if os.environ.get('PROMPT_LOG'): pathlib.Path(os.environ['PROMPT_LOG']).write_text(prompt)
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
if case == 'conflict': value['findings'] = ['Unresolved defect.']
if case == 'turns': result['subtype'] = 'error_max_turns'
if case == 'model': result['modelUsage'] = {'different-model': {}}
if case == 'error': result['is_error'] = True
# A valid review in an envelope that also names an API error status on its final result.
if case.startswith('api_'): result['api_error_status'] = int(case[4:])
if case == 'exit': print(json.dumps(result)); sys.exit(9)
if case == 'mutation': (repo / 'file.py').write_text('changed during review')
if case == 'kit_docs': assert 'core/docs/ARCHITECTURE.md' in prompt
if case == 'archive_failure':
    (repo / 'docs/reviews').rmdir()
    (repo / 'docs/reviews').write_text('blocked archive')
if case == 'timeout': time.sleep(20)
if case == 'partial_timeout': print(json.dumps(result), flush=True); time.sleep(20)
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


def run_quietly(suite, out=sys.stdout):
    """Run a suite; print its whole log only on a failure or a skip, else one summary line.

    The per-test lines of a passing run were about 17 KB in every gate self-test, read by the
    agent that ran it. A failing run still prints every line, the passing ones included.
    """
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped:
        out.write(log.getvalue())
        return False
    out.write("Ran %d tests: OK\n" % result.testsRun)
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


class BridgeTests(unittest.TestCase):
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

        def capture(command, prompt, repo, timeout, into=None, noted=None):
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
                    # Freeze preparation time here to check the exact configured budget;
                    # the shared-deadline regression below measures real elapsed time.
                    with patch.object(agent_process, 'run', side_effect=capture), \
                            patch('time.monotonic', return_value=1000.0), redirect_stdout(StringIO()):
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
        (self.repo / '.gitattributes').write_text('file.py ident\n')
        with self.assertRaisesRegex(bridge.BridgeError, 'clean filter or ident attribute on file.py'):
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
        self.git('config', 'filter.lfs.clean', '"%s" "%s"' % (sys.executable, clean))
        (self.repo / '.gitattributes').write_text('*.bin filter=lfs\n')
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

            def execution(command, prompt, repo, timeout, into=None, noted=None):
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

            def execution(command, prompt, repo, timeout, into=None, noted=None):
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
        (shim / 'git').write_text(
            '#!/bin/sh\n"%s" "$@"; status=$?\ncase "$*" in *"--verify review-base^{commit}"*)\n'
            '  [ -e "%s" ] || { : > "%s"; "%s" -C "%s" update-ref refs/heads/review-base %s; } ;;\n'
            'esac\nexit $status\n' % (real, moved, moved, real, self.repo, intermediate))
        (shim / 'git').chmod(0o755)
        for main, args in ((bridge.main, ['review']),
                           (codex_bridge.main, ['--model', 'fixture-codex-model'])):
            label = 'moving-base-' + ('claude' if main is bridge.main else 'codex')
            prompts = []

            def execution(command, prompt, repo, timeout, into=None, noted=None):
                prompts.append(prompt)
                if '-o' in command:
                    Path(command[command.index('-o') + 1]).write_text('VERDICT: Accept\n')
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
            def execution(command, prompt, repo, timeout, into=None, noted=None):
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

        def quota(command, prompt, repo, timeout, into=None, noted=None):
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

        def quota(command, prompt, repo, timeout, into=None, noted=None):
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
            os.kill(os.getpid(), signal.SIGTERM)
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

        def absent(command, prompt, repo, timeout, into=None, noted=None):
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

    def test_a_cancel_before_runs_guard_never_launches_the_claude_reviewer(self):
        # The adapter's noting handler is up before run() arms its own guard: a cancel in
        # between was noted, the paid reviewer launched anyway and ran to its end.
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import agent_process
        real_run, launched = agent_process.run, self.root / 'launched'

        def run(*args, **kwargs):
            os.kill(os.getpid(), signal.SIGTERM)
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
                os.kill(os.getpid(), sig)
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

        def quota(command, prompt, repo, timeout, into=None, noted=None):
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

        def quota(command, prompt, repo, timeout, into=None, noted=None):
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
                os.kill(os.getpid(), signal.SIGTERM)
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

        def cancelled(command, prompt, repo, timeout, into=None, noted=None):
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
                    os.kill(os.getpid(), signal.SIGTERM)
                return dict.__getitem__(self, key)

        def quota(command, prompt, repo, timeout, into=None, noted=None):
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
                os.kill(os.getpid(), signal.SIGTERM)
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

        def quota(command, prompt, repo, timeout, into=None, noted=None):
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

        def quota(command, prompt, repo, timeout, into=None, noted=None):
            value = ({'type': 'turn.failed', 'error': {'message': 'usage limit reached'}}
                     if '-o' in command else
                     {'type': 'result', 'subtype': 'success', 'is_error': True,
                      'api_error_status': 429, 'modelUsage': {'claude-opus-5': {}}})
            return {'exit_code': 1, 'stdout': json.dumps(value), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        def second_cancel(*args, **kwargs):
            fired.append('relabel')
            os.kill(os.getpid(), signal.SIGTERM)
            return relabel(*args, **kwargs)

        class Blocked(StringIO):
            def write(self, text):
                # Either adapter: the first cancel while its result line is written. A cancel
                # while the handlers go back has its own test.
                if text.startswith(('{"status": "failed"', 'review invocation: ')) and not fired:
                    fired.append('print')
                    os.kill(os.getpid(), signal.SIGTERM)
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

        def quota(command, prompt, repo, timeout, into=None, noted=None):
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
                os.kill(os.getpid(), signal.SIGTERM)
            elif sig == signal.SIGTERM and handler is caller and fired == ['first']:
                fired.append('second')
                os.kill(os.getpid(), signal.SIGTERM)
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

        def quota(command, prompt, repo, timeout, into=None, noted=None):
            launched.append(command[0])
            return {'exit_code': 1, 'stdout': json.dumps({'type': 'turn.failed',
                    'error': {'message': 'usage limit reached'}}), 'stderr': '',
                    'termination': None, 'duration_ms': 1}

        class Blocked(StringIO):
            def write(self, text):
                if text.startswith('review invocation: ') and not fired:
                    fired.append(text)
                    os.kill(os.getpid(), signal.SIGTERM)
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

        def quota(command, prompt, repo, timeout, into=None, noted=None):
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
        def execution(command, prompt, repo, timeout, into=None, noted=None):
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
        fake.write_text(PYTHON_SHEBANG + 'import json,os,pathlib,sys\n'
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
        fake.write_text(PYTHON_SHEBANG + 'import json,os,pathlib,sys\n'
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
                self.assertIn("throwaway copy", record["sandbox"])
                self.assertIn("Read,Glob,Grep,Bash", record["sandbox"])
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
        fake.write_text(PYTHON_SHEBANG +
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
        fake.write_text(PYTHON_SHEBANG +
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

    def test_an_api_error_status_on_the_final_result_fails_the_review(self):
        # An exit-0 success envelope with a valid Accept and api_error_status 429 was recorded
        # completed AND quota, and the dispatcher took it as a finished review. The CLI copies
        # that status from the message that ended the turn, never from an error it retried
        # through, so its presence is a failure, whatever the text holds. "error" is is_error
        # with a valid verdict; "accept" is the clean completion.
        for case, kind in (('api_429', 'quota'), ('api_401', 'invalid_evidence'),
                           ('api_500', 'invalid_evidence'), ('api_529', 'invalid_evidence'),
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
                  'api_429': 'quota', 'api_500': 'invalid_evidence', 'quota': 'quota',
                  'archive_failure': 'evidence_write_failed', 'auth': 'authentication',
                  'context': 'context_limit', 'conflict': 'invalid_evidence', 'error': 'cli_error',
                  'exit': 'cli_error', 'malformed_envelope': 'invalid_evidence',
                  'missing': 'invalid_evidence', 'model': 'invalid_evidence',
                  'transcript': 'invalid_evidence', 'mutation': 'stale_checkout',
                  'partial_timeout': 'timeout', 'timeout': 'timeout',
                  'turns': 'budget_or_turn_limit', 'unknown_flag': 'cli_unsupported'}
        codex = {'accept': None, 'reject': None, 'mcp': None, 'mcp_reconnect': None,
                 'quota': 'quota', 'mcp_quota': 'quota', 'mcp_exit': 'cli_error',
                 'mcp_no_completion': 'cli_error', 'mcp_no_verdict': 'cli_error',
                 'mcp_two_verdicts': 'cli_error', 'mcp_failed_turn': 'cli_error',
                 'unknown_flag': 'cli_unsupported'}
        # Only the dispatcher writes the chain and fails a quota on a changed checkout: the
        # attempt's own record, then what the chain says (None: no chain was written).
        dispatched = {'chain_failure': ('quota', None), 'quota_mutation': ('quota', 'stale_checkout')}
        self.assertLessEqual(set(re.findall(r"case == '(\w+)'", FIXTURE)), set(claude) | set(dispatched))
        self.assertLessEqual(set(re.findall(r"case == '(\w+)'", self.build_fake_codex().read_text())),
                             set(codex))
        task = self.root / 'handoff.md'
        task.write_text('Propose a fix and stop on ambiguity.\n')
        env = dict(os.environ, MYAGENTKIT_DELEGATION_DEPTH='0', MYAGENTKIT_CAPTURE_QUOTA='0',
                   REVIEW_TIMEOUT_SECONDS='2', REVIEW_CLI_BIN=str(self.build_fake_codex()),
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
                    command = [sys.executable, '-B', str(BRIDGE), mode, '--repo', str(repo), '--timeout', '2',
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
        diff = bridge.snapshot(self.repo, "uncommitted", None)[2]
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
        fake.write_text(PYTHON_SHEBANG + '''import json, os, pathlib, sys, time
if '--version' in sys.argv: print('offline codex'); sys.exit(0)
prompt = sys.stdin.read()
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
        fake.write_text(PYTHON_SHEBANG +
                        "import json, os, pathlib, sys\n"
                        "prompt = sys.stdin.read()\n"
                        "if os.environ.get('PROMPT_LOG'): pathlib.Path(os.environ['PROMPT_LOG']).write_text(prompt)\n"
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
                        "(stream disconnected before completion)'}))\n"
                        "if case == 'mcp_quota':\n"
                        "    print(json.dumps({'type': 'error', 'message': 'usage limit reached'})); sys.exit(0)\n"
                        "verdict = 'Reject' if case == 'reject' else 'Accept'\n"
                        "text = '## Findings\\n\\nFixture finding.\\n\\nVERDICT: ' + verdict + '\\n'\n"
                        "text = {'mcp_no_verdict': '## Findings\\n\\nFixture finding.\\n',\n"
                        "        'mcp_two_verdicts': text + 'VERDICT: Reject\\n'}.get(case, text)\n"
                        "pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text(text)\n"
                        "if case == 'mcp_failed_turn': print(json.dumps({'type': 'turn.failed', 'error': {}}))\n"
                        "if case != 'mcp_no_completion': print(json.dumps({'type': 'turn.completed', 'usage': {}}))\n"
                        "if case == 'mcp_exit': sys.exit(1)\n")
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
        # A reviewer told not to run tests sent every finding back unreproduced, and a worker then
        # spent a round reproducing it; one that executed in a throwaway copy found decisive defects.
        # The bridged reviewers now execute, in a throwaway copy the adapter made: the ask is
        # unconditional, and the prompt never names the reviewed repository's path.
        asks = ('EVERY finding', 'Critical, High, Medium or Low', 'Fix sketch:',
                'You are in a throwaway copy', 'run anything inside this copy',
                'Run the suite and reproductions', 'REPRODUCED',
                'if a run is impossible, mark it REASONED', 'NOT RUN', 'Never use the network')
        forbidden = ('Do not run tests', 'run code', 'SHOULD run', 'worktree add --detach',
                     'If your tools can execute', 'edit files in this checkout',
                     'never change the reviewed checkout', str(self.repo))
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
        for words in forbidden:
            self.assertNotIn(words, prompt)
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

    def test_the_reviewer_executes_in_a_throwaway_copy_removed_afterwards(self):
        # The reviewers may now run anything, so they never run in the reviewed repository: each
        # attempt gets a copy of HEAD plus the uncommitted diff, removed when the attempt ends.
        (self.repo / 'new file.txt').write_text('an untracked file\n')
        # An owner's diff.noprefix must not break the diff applied to the copy.
        self.git('config', 'diff.noprefix', 'true')
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
        head_file = self.git('show', 'HEAD:file.py').stdout.decode()
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
                budgets = []

                def slow_copy(*args, **kwargs):
                    time.sleep(1.3)
                    return real_copy(*args, **kwargs)

                def slow_reviewer(command, prompt, repo, timeout, **kwargs):
                    budgets.append(timeout)
                    return real_run([sys.executable, '-c',
                                     'import sys, time; sys.stdin.read(); time.sleep(1.3)'],
                                    prompt, repo, timeout, **kwargs)

                received = []
                with patch.dict(os.environ, self.review_env(REVIEW_TIMEOUT_SECONDS='2')), \
                        patch.object(module, 'throwaway_copy', side_effect=slow_copy), \
                        patch('agent_process.run', side_effect=slow_reviewer), \
                        redirect_stdout(io.StringIO()):
                    started = time.monotonic()
                    module.main([*args, '--repo', str(self.repo)], received.append)
                    elapsed = time.monotonic() - started
                self.assertEqual(len(budgets), 1, received)
                self.assertGreater(budgets[0], 0)
                self.assertLess(budgets[0], 0.8)
                # The budget above is the proof of the shared deadline; the wall time only
                # rules out two full timeouts in a row (3.3 s), with room for a slow runner.
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
                        inject = target in command
                        child = real_popen([str(stub)] if inject else command, *args, **kwargs)
                        children.append(child)
                        if inject:
                            until = time.monotonic() + 5
                            while not pid_file.exists() and time.monotonic() < until:
                                time.sleep(0.01)
                            self.assertTrue(pid_file.exists(), 'stub did not start')
                            # Deliver inside Popen, before its caller has assigned the handle.
                            os.kill(os.getpid(), sig)
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

    def test_missing_tar_reaps_the_already_started_archive(self):
        from unittest.mock import patch
        import claude_bridge
        real_popen = subprocess.Popen
        children = []

        def launch(command, *args, **kwargs):
            if command[0] == 'tar':
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
                    os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                child.stdout.close()

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
        (bin_dir / 'tar').write_text('#!/bin/sh\ncat > /dev/null\nsleep 5\n')
        (bin_dir / 'tar').chmod(0o755)
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
            os.kill(os.getpid(), signal.SIGTERM)  # pending while blocked, raised after the reaps
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
            self.assertNotEqual(code, 0)
            self.assertIn('inside the reviewed repository', json.dumps(result))
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
                os.kill(os.getpid(), signal.SIGTERM)  # pending while blocked
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
        command = 'mkdir -p ' + refused['error'].rsplit('mkdir -p ', 1)[1]
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

    def test_a_completed_codex_review_is_not_failed_by_noise_it_recovered_from(self):
        # A review that exited 0, closed its stream with turn.completed and gave one verdict was
        # recorded cli_error: the stream carried a reconnect error event the CLI recovered from,
        # while its own MCP client logged a transport failure on stderr. Both are kept in the
        # usage record; a failure of the structured outcome itself still fails as before.
        for case, kind in (('mcp', None), ('mcp_reconnect', None), ('mcp_exit', 'cli_error'),
                           ('mcp_no_completion', 'cli_error'), ('mcp_no_verdict', 'cli_error'),
                           ('mcp_two_verdicts', 'cli_error'), ('mcp_failed_turn', 'cli_error'),
                           ('mcp_quota', 'quota'), ('unknown_flag', 'cli_unsupported')):
            with self.subTest(case=case):
                result, chain = self.dispatch_result('codex', fallback=False, CODEX_FIXTURE_CASE=case,
                                                     MYAGENTKIT_TASK_ID='noise-' + case)
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
        self.assertEqual((chain['status'], chain['failure_kind']), ('failed', 'quota'))
        self.assertEqual([a['reviewer'] for a in chain['attempts']], ['claude'])
        self.assertIn('not requested', chain['fallback_blocked'])
        self.assertNotIn('selected_reviewer', chain)
        self.assertEqual(chain['recovery']['action'], 'continue_independent_work')
        # With --fallback, quota is an unavailable reviewer like any other: Codex runs once.
        result, chain = self.dispatch_result(FIXTURE_CASE='api_429', MYAGENTKIT_TASK_ID='api-fallback')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual([(a['reviewer'], a['status'], a['failure_kind']) for a in chain['attempts']],
                         [('claude', 'failed', 'quota'), ('codex', 'completed', None)])
        self.assertEqual(chain['selected_reviewer'], 'codex')
        self.assertFalse(chain['review_approved'])

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
            for posix in (True, False):
                del seen[:]
                with patch.object(agent_process, 'POSIX', posix), patch('subprocess.Popen', fake), \
                        patch('os.killpg', absent), \
                        patch('signal.pthread_sigmask', absent if not posix else signal.pthread_sigmask):
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
                     '    delattr(signal, name)\n'
                     'del os.killpg\n'
                     'sys.modules["fcntl"] = None\n'
                     'os.name = "nt"\n'
                     'sys.path.insert(0, sys.argv[1])\n'
                     'import agent_process, claude_bridge, codex_bridge, codex_quota, review_dispatch\n'
                     'print(agent_process.POSIX, [s.name for s in agent_process.CANCEL_SIGNALS])\n'
                     'print(agent_process.block_cancels())\n')
        result = subprocess.run([sys.executable, '-c', simulated, str(ROOT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "False ['SIGINT', 'SIGTERM']\nNone\n", result.stderr)

    def test_posix_only_process_calls_are_made_only_in_the_agent_process_seam(self):
        # Every launch, block and group kill of the review tooling goes through agent_process's
        # seam, which alone knows the platform; a direct call elsewhere breaks native Windows.
        import ast
        seam = {'block_cancels', 'restore_mask', 'pending', 'launch', 'stop_group'}
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
    if not run_quietly(suite):
        raise SystemExit(1)
    print("Suite minimums met: " + ", ".join("%s %d" % item for item in sorted(SUITE_MINIMUMS.items())))
    print("REVIEW SELF-TEST: PASS")
