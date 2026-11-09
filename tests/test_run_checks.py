"""core/scripts/run_checks.sh: a brief's checks run without a model, one result file read once
(pipeline field report 2026-11-09, proposal 5; PLAN.md item 5)."""
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

RUN_CHECKS = Path(__file__).resolve().parents[1] / 'core/scripts/run_checks.sh'


class RunChecksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def checks(self, text, name='task.checks'):
        path = self.cwd / name
        path.write_text(text, encoding='utf-8')
        return path

    def run_checks(self, *args, env=None):
        return subprocess.run(['sh', str(RUN_CHECKS), *map(str, args)], cwd=self.cwd, capture_output=True,
                              text=True, timeout=60, env=env)

    def start(self, *args, env=None):
        return subprocess.Popen(['sh', str(RUN_CHECKS), *map(str, args)], cwd=self.cwd, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def wait_for(self, path, text):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if path.exists() and text in path.read_text(encoding='utf-8'):
                return
            time.sleep(0.05)
        self.fail('%s never showed %r' % (path, text))

    def test_a_passing_list_writes_one_line_per_command_and_exits_0(self):
        self.checks('# the brief\'s checks\n\necho one\n   \n  printf "two\\n"\r\n')
        done = self.run_checks('task.checks')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        result = self.cwd / '.myagentkit/checks/task.checks.result.md'
        self.assertEqual(done.stdout, 'PASS 2/2: .myagentkit/checks/task.checks.result.md\n')
        lines = result.read_text(encoding='utf-8').splitlines()
        self.assertEqual(lines[0], 'PASS 2/2')
        self.assertRegex(lines[1], r'^PASS 0 \d+s echo one$')
        self.assertRegex(lines[2], r'^PASS 0 \d+s printf "two\\n"$')
        self.assertEqual(len(lines), 3)
        log = Path(str(result) + '.log').read_text(encoding='utf-8')
        self.assertIn('one\n', log)
        self.assertIn('two\n', log)

    def test_a_failing_list_names_the_failure_with_its_last_20_lines(self):
        self.checks('true\nfor i in $(seq 1 30); do echo line$i; done; exit 3\n')
        done = self.run_checks('task.checks', '--out', 'out/r.md')
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        lines = (self.cwd / 'out/r.md').read_text(encoding='utf-8').splitlines()
        self.assertEqual(lines[0], 'FAIL 1/2')
        self.assertRegex(lines[1], r'^PASS 0 \d+s true$')
        self.assertRegex(lines[2], r'^FAIL 3 \d+s for i in ')
        self.assertEqual(lines[3:], ['    line%d' % i for i in range(11, 31)])
        log = (self.cwd / 'out/r.md.log').read_text(encoding='utf-8')
        self.assertIn('line1\n', log)  # the full output is in the log

    def test_usage_and_an_empty_list_exit_2_and_write_no_result(self):
        self.assertEqual(self.run_checks().returncode, 2)
        self.assertEqual(self.run_checks('missing.checks').returncode, 2)
        self.checks('# nothing\n\n')
        self.assertEqual(self.run_checks('task.checks', '--out', 'r.md').returncode, 2)
        self.assertFalse((self.cwd / 'r.md').exists())

    def assert_one_run_at_a_time(self, env=None):
        self.checks('sleep 2\n')
        result = self.cwd / 'r.md'
        result.write_text('PASS 9/9 from an earlier run\n', encoding='utf-8')
        first = self.start('task.checks', '--out', 'r.md', env=env)
        try:
            self.wait_for(self.cwd / 'r.md.log', '=== sleep 2')
            # Atomic: while the run goes on there is no result, neither a partial one nor the old one.
            self.assertFalse(result.exists())
            second = self.run_checks('task.checks', '--out', 'r.md', env=env)
            self.assertEqual(second.returncode, 75, second.stdout + second.stderr)
            self.assertEqual(second.stdout, 'running: r.md\n')
            self.assertFalse(result.exists())
        finally:
            out, err = first.communicate(timeout=60)
        self.assertEqual(first.returncode, 0, out + err)
        self.assertEqual(result.read_text(encoding='utf-8').splitlines()[0], 'PASS 1/1')

    def test_a_second_run_exits_75_while_the_first_holds_the_lock(self):
        self.assert_one_run_at_a_time()

    @unittest.skipIf(os.name == 'nt', 'the PATH below is built from POSIX tools')
    def test_without_flock1_python_holds_the_lock(self):
        # macOS has no flock(1): the Python holder takes the lock there.
        tools = Path(self.tmp.name) / 'bin'
        tools.mkdir()
        for name in ('sh', 'python3', 'date', 'cat', 'tail', 'sed', 'mkdir', 'mktemp', 'rm', 'mv',
                     'dirname', 'basename', 'sleep', 'uname'):
            found = shutil.which(name)
            self.assertIsNotNone(found, name)
            os.symlink(found, tools / name)
        env = dict(os.environ, PATH=str(tools))
        probe = subprocess.run(['sh', '-c', 'command -v flock || echo none'], env=env, capture_output=True, text=True)
        self.assertEqual(probe.stdout, 'none\n')
        self.assert_one_run_at_a_time(env=env)

    def test_a_server_a_check_leaves_running_does_not_hold_the_lock(self):
        self.checks('sleep 30 >/dev/null 2>&1 & echo $! > server.pid\n')
        first = self.run_checks('task.checks', '--out', 'r.md')
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        try:
            again = self.run_checks('task.checks', '--out', 'r.md')
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        finally:
            os.kill(int((self.cwd / 'server.pid').read_text()), 15)


if __name__ == '__main__':
    unittest.main()
