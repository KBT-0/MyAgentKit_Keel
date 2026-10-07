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
        copy = self.tmp / 'copy'
        copy.mkdir()
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
