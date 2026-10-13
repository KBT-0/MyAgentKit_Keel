"""Worker scripts find their siblings with mixed Windows path separators; no live workers."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_spawn_worker import run_state_hook

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'overlays/claude-code/files/scripts'


class WorkerPathsOnWindows(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='kit-worker-paths-'))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.scripts = self.tmp / 'with space/scripts'
        self.scripts.mkdir(parents=True)
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'])
        if os.name == 'nt':
            self.stub(self.bin / 'python3', 'exec %s "$@"\n' % shlex.quote(sys.executable))
        else:  # the watcher's state-file tests run here too, as on Git for Windows
            self.stub(self.bin / 'uname', 'echo MINGW64_NT-10.0\n')

    @staticmethod
    def stub(path, body):
        path.write_text('#!/bin/sh\n' + body, encoding='utf-8', newline='\n')
        path.chmod(0o755)

    def paths(self, name, posix=False):
        if os.name != 'nt' and not posix:
            sys.stderr.write('\nNOT RUN: %s (native Windows only)\n' % self.id())
            return []
        target = self.scripts / name
        shutil.copyfile(SCRIPTS / name, target)
        forward = target.as_posix()
        if os.name != 'nt':
            return [str(target)]
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
        paths = self.paths('watch_workers.sh', posix=True)
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

    def test_two_stops_in_the_same_second_are_each_reported(self):
        paths = self.paths('watch_workers.sh', posix=True)
        if not paths:
            return
        shutil.copyfile(SCRIPTS / 'waiting_patterns.txt', self.scripts / 'waiting_patterns.txt')
        workers = self.tmp / '.myagentkit/workers'
        workers.mkdir(parents=True)
        with patch('time.strftime', return_value=' 2026-10-12T10:00:00'), \
                patch('time.time_ns', side_effect=[101, 102]):
            for event in ('101', '102'):
                run_state_hook(workers / 'w1.state', {'hook_event_name': 'Stop'})
                result = self.run_script(paths[0], '--once', 'w1')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('IDLE: w1', result.stdout)
                self.assertIn('2026-10-12T10:00:00', result.stdout)
                self.assertEqual(self.run_script(paths[0], '--once', 'w1').stdout, '')
        self.assertEqual((workers / 'w1.watch-state').read_text().strip(), 'idle 2026-10-12T10:00:00 102')

    def test_unreadable_or_invalid_state_is_an_observation_failure(self):
        paths = self.paths('watch_workers.sh', posix=True)
        if not paths:
            return
        shutil.copyfile(SCRIPTS / 'waiting_patterns.txt', self.scripts / 'waiting_patterns.txt')
        workers = self.tmp / '.myagentkit/workers'
        workers.mkdir(parents=True)
        state = workers / 'w1.state'
        absent = self.run_script(paths[0], '--once', 'w1')
        self.assertEqual(absent.returncode, 0, absent.stderr)
        self.assertEqual(absent.stdout, '')
        state.mkdir()
        result = self.run_script(paths[0], '--once', 'w1', 'w2')
        self.assertEqual(result.returncode, 3)
        self.assertIn('watch_workers: w1: state unreadable: not a regular file', result.stderr)
        self.assertIn('w1.state', result.stderr)
        self.assertIn('delete it', result.stderr)
        state.rmdir()
        for content in ('garbage\n', 'idle nonsense\n', 'idle 2026-10-12T10:00:00 1\ngarbage\n') + (
                ('idle 2026-10-12T10:00:00 1\r\n',) if os.name != 'nt' else ()):  # Git Bash's $(...) drops the CR
            with self.subTest(content=content):
                state.write_bytes(content.encode())
                result = self.run_script(paths[0], '--once', 'w1')
                self.assertEqual(result.returncode, 3)
                self.assertIn('watch_workers: w1: state unreadable: invalid state content', result.stderr)
                self.assertFalse((workers / 'w1.watch-state').exists())
        # No signal yet, not a failure: an old hook truncates the file before it writes.
        state.write_bytes(b'')
        result = self.run_script(paths[0], '--once', 'w1', 'w2')
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        # Blank lines after the line are harmless.
        (workers / 'w1.watch-state').unlink(missing_ok=True)
        state.write_bytes(b'idle 2026-10-12T10:00:00 1\n\n\n')
        result = self.run_script(paths[0], '--once', 'w1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('IDLE: w1', result.stdout)

    def test_legacy_input_is_idle_with_one_older_kit_notice(self):
        paths = self.paths('watch_workers.sh', posix=True)
        shutil.copyfile(SCRIPTS / 'waiting_patterns.txt', self.scripts / 'waiting_patterns.txt')
        workers = self.tmp / '.myagentkit/workers'
        workers.mkdir(parents=True)
        for event in ('', ' 1'):
            (workers / 'w1.state').write_bytes(('waiting input 2026-10-12T10:00:00' + event + '\n').encode())
            result = self.run_script(paths[0], '--once', 'w1')
            self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)
            self.assertNotIn('WAITING:', result.stdout)
            self.assertNotIn('IDLE:', result.stdout)
            if not event:
                self.assertIn('hook is from an older kit; re-spawn to install the current one', result.stdout)
            else:
                self.assertEqual(result.stdout, '')
            self.assertFalse((workers / 'w1.watch-state').exists())

    def test_state_is_read_once_before_size_and_content_checks(self):
        paths = self.paths('watch_workers.sh', posix=True)
        shutil.copyfile(SCRIPTS / 'waiting_patterns.txt', self.scripts / 'waiting_patterns.txt')
        workers = self.tmp / '.myagentkit/workers'
        workers.mkdir(parents=True)
        state = workers / 'w1.state'
        self.env['LIVE_STATE'] = state.as_posix()
        if os.name == 'nt':
            self.env['LIVE_STATE'] = subprocess.run(['cygpath', '-u', str(state)], check=True,
                                                    capture_output=True, text=True).stdout.strip()
        self.stub(self.bin / 'cat',
                  'for arg do\n  if [ "$arg" = "$LIVE_STATE" ]; then\n'
                  '    echo read >>"$LIVE_STATE.reads"\n  fi\ndone\nexec /bin/cat "$@"\n')
        self.stub(self.bin / 'wc',
                  'if [ "$1" = -c ]; then\n  : >"$LIVE_STATE"\nfi\nexec /usr/bin/wc "$@"\n')
        for content in (b'', b'idle 2026-10-12T10:00:00 1\n', b'\x00\x00'):
            with self.subTest(content=content):
                state.write_bytes(content)
                reads = workers / 'w1.state.reads'
                reads.unlink(missing_ok=True)
                result = self.run_script(paths[0], '--once', 'w1')
                if content == b'\x00\x00':
                    self.assertEqual(result.returncode, 3, result.stderr)
                    self.assertIn('invalid state content', result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual('IDLE: w1' in result.stdout, bool(content), result.stdout)
                self.assertEqual(reads.read_text().splitlines(), ['read'])

    def test_failed_live_open_is_captured_before_measurement(self):
        paths = self.paths('watch_workers.sh', posix=True)
        shutil.copyfile(SCRIPTS / 'waiting_patterns.txt', self.scripts / 'waiting_patterns.txt')
        workers = self.tmp / '.myagentkit/workers'
        workers.mkdir(parents=True)
        state = workers / 'w1.state'
        self.env['LIVE_STATE'] = state.as_posix()
        if os.name == 'nt':
            self.env['LIVE_STATE'] = subprocess.run(['cygpath', '-u', str(state)], check=True,
                                                    capture_output=True, text=True).stdout.strip()
        # Replace the checked regular file with a directory at its actual read.
        self.stub(self.bin / 'cat',
                  'for arg do\n  if [ "$arg" = "$LIVE_STATE" ]; then\n'
                  '    rm -f -- "$LIVE_STATE"\n    mkdir -- "$LIVE_STATE"\n'
                  '    echo read >>"$LIVE_STATE.reads"\n  fi\ndone\nexec /bin/cat "$@"\n')
        self.stub(self.bin / 'wc',
                  'if [ "$1" = -c ]; then\n  echo measured >>"$LIVE_STATE.measured"\nfi\n'
                  'exec /usr/bin/wc "$@"\n')
        for names in (('w1',), ('w2', 'w1')):
            with self.subTest(names=names):
                if state.is_dir():
                    state.rmdir()
                state.write_bytes(b'waiting permission 2026-10-12T10:00:00 1\n')
                (workers / 'w2.state').write_bytes(b'waiting question 2026-10-12T10:00:00 2\n')
                (workers / 'w1.state.reads').unlink(missing_ok=True)
                (workers / 'w1.state.measured').unlink(missing_ok=True)
                result = self.run_script(paths[0], '--once', *names)
                self.assertEqual((result.returncode, result.stdout), (3, ''), result.stderr)
                self.assertEqual(result.stderr.count('state unreadable:'), 1, result.stderr)
                self.assertTrue(result.stderr.startswith('watch_workers: w1: state unreadable:'), result.stderr)
                self.assertEqual((workers / 'w1.state.reads').read_text().splitlines(), ['read'])
                # w2 is measured once when present; the unreadable w1 is never measured.
                measured = workers / 'w1.state.measured'
                self.assertEqual(measured.read_text().splitlines() if measured.exists() else [],
                                 ['measured'] if 'w2' in names else [])
                self.assertFalse((workers / 'w1.watch-state').exists())
                self.assertFalse((workers / 'w2.watch-state').exists())

    def test_watch_refuses_a_session_name_outside_the_workers_folder(self):
        paths = self.paths('watch_workers.sh', posix=True)
        if not paths:
            return
        shutil.copyfile(SCRIPTS / 'waiting_patterns.txt', self.scripts / 'waiting_patterns.txt')
        workers = self.tmp / '.myagentkit/workers'
        workers.mkdir(parents=True)
        (workers.parent / 'victim.state').write_text('idle 2026-10-12T10:00:00 1\n')

        def snapshot():
            return {str(p.relative_to(self.tmp)): p.read_bytes() if p.is_file() else None
                    for p in self.tmp.rglob('*')}
        before = snapshot()
        for name in ('../victim', 'a/b', '-w', 'a b', '.'):
            with self.subTest(name=name):
                result = self.run_script(paths[0], '--once', '--', name)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('refused the session name', result.stderr)
                self.assertEqual(snapshot(), before)

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
