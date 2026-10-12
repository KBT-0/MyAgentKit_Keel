"""Worker scripts find their siblings with mixed Windows path separators; no live workers."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'overlays/claude-code/files/scripts'


class WorkerPathsOnWindows(unittest.TestCase):
    def setUp(self):
        if os.name != 'nt':
            return
        self.tmp = Path(tempfile.mkdtemp(prefix='kit-worker-paths-'))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.scripts = self.tmp / 'with space/scripts'
        self.scripts.mkdir(parents=True)
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'])
        self.stub(self.bin / 'python3', 'exec %s "$@"\n' % shlex.quote(sys.executable))

    @staticmethod
    def stub(path, body):
        path.write_text('#!/bin/sh\n' + body, encoding='utf-8', newline='\n')
        path.chmod(0o755)

    def paths(self, name):
        if os.name != 'nt':
            sys.stderr.write('\nNOT RUN: %s (native Windows only)\n' % self.id())
            return []
        target = self.scripts / name
        shutil.copyfile(SCRIPTS / name, target)
        forward = target.as_posix()
        return [forward[:3] + forward[3:].replace('/', '\\'), str(target), forward]

    def run_script(self, path, *args):
        return subprocess.run(['sh', path, *args], cwd=self.tmp, env=self.env,
                              capture_output=True, text=True, encoding='utf-8', timeout=20)

    def test_watch_finds_its_patterns(self):
        paths = self.paths('watch_workers.sh')
        if not paths:
            return
        shutil.copyfile(SCRIPTS / 'waiting_patterns.txt', self.scripts / 'waiting_patterns.txt')
        for path in paths:
            with self.subTest(path=path):
                result = self.run_script(path, '--list-patterns')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('KIND STATUS VERSION WHERE ERE', result.stdout)

    def test_watch_reads_a_tabs_state_file_in_place_of_a_pane(self):
        # A Windows Terminal tab has no pane to read: the state line the worker's hooks write
        # (spawn_worker.sh) is WAITING or IDLE, once each, and no tmux is needed.
        paths = self.paths('watch_workers.sh')
        if not paths:
            return
        shutil.copyfile(SCRIPTS / 'waiting_patterns.txt', self.scripts / 'waiting_patterns.txt')
        workers = self.tmp / '.myagentkit/workers'
        workers.mkdir(parents=True)
        for line, out in (('waiting permission 2026-10-12T10:00:00', 'WAITING: w1, on a permission prompt'),
                          ('waiting question 2026-10-12T10:01:00', 'WAITING: w1, on a question'),
                          ('idle 2026-10-12T10:05:00', 'IDLE: w1, its session stopped')):
            with self.subTest(line=line):
                (workers / 'w1.state').write_text(line + '\n', newline='\n')
                result = self.run_script(paths[0], '--once', 'w1')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(result.stdout.startswith('watch_workers: %s' % out), result.stdout)
                self.assertIn('(its state file: %s)' % line, result.stdout)
                self.assertEqual(self.run_script(paths[0], '--once', 'w1').stdout, '')

    def test_spawn_finds_its_watcher(self):
        paths = self.paths('spawn_worker.sh')
        if not paths:
            return
        # Reach the tmux branch under Git for Windows without starting a session or terminal.
        self.stub(self.bin / 'uname', 'echo Linux\n')
        self.stub(self.bin / 'claude', 'exit 99\n')
        self.stub(self.bin / 'tmux', '[ "$1" != has-session ]\n')
        self.stub(self.scripts / 'watch_workers.sh', 'echo "watch_workers: GONE: fixture"\n')
        brief = self.tmp / 'brief.md'
        brief.write_text('Fixture brief.\n')
        for path in paths:
            with self.subTest(path=path):
                result = self.run_script(path, 'fixture', str(brief), '--model', 'fixture', '--effort', 'low', '--batch')
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("session 'fixture' exited before its input line showed", result.stderr)

    def test_close_finds_its_auditor_without_ending_any_process(self):
        paths = self.paths('close_worker.sh')
        if not paths:
            return
        self.stub(self.bin / 'ps-fixture', 'exit 0\n')
        self.env['KIT_PS'] = str(self.bin / 'ps-fixture')
        self.stub(self.scripts / 'clean_worktrees.sh', 'echo "clean_worktrees: no worktree at fixture"\n')
        # A repository to close in: outside one, the close refuses before its auditor.
        subprocess.run(['git', 'init', '-q', str(self.tmp)], check=True, capture_output=True)
        for path in paths:
            with self.subTest(path=path):
                result = self.run_script(path, '--dry-run', 'fixture')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('fixture: no worktree at .claude/worktrees/fixture; nothing to remove', result.stdout)


if __name__ == '__main__':
    unittest.main()
