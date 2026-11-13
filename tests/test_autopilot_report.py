"""The autopilot report's Done section comes from git and the result files, never from the lead's account."""
from datetime import datetime, timedelta
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'core/scripts/autopilot_report.py'


class AutopilotReportTests(unittest.TestCase):
    def git(self, *args, when=None):
        env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.com', GIT_COMMITTER_NAME='t',
                   GIT_COMMITTER_EMAIL='t@example.com')
        if when:
            env.update(GIT_AUTHOR_DATE=when.isoformat(), GIT_COMMITTER_DATE=when.isoformat())
        subprocess.run(['git', '-C', str(self.project), *args], check=True, capture_output=True, env=env)

    def test_done_lists_the_absences_commits_merges_results_and_cost(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        now = datetime.now().astimezone().replace(microsecond=0)
        since = now - timedelta(hours=1)
        self.git('init', '-q', '-b', 'main')
        self.git('commit', '-q', '--allow-empty', '-m', 'before the night', when=now - timedelta(hours=2))
        self.git('commit', '-q', '--allow-empty', '-m', 'night work')
        self.git('checkout', '-q', '-b', 'worker')
        self.git('commit', '-q', '--allow-empty', '-m', 'worker change')
        self.git('checkout', '-q', 'main')
        self.git('merge', '-q', '--no-ff', '-m', 'Merge the worker', 'worker')
        fresh = self.project / '.claude/worktrees/w1/RESULT-w1.md'
        fresh.parent.mkdir(parents=True)
        fresh.write_text('Kind: completed\nTask: w1\nAttempt: 1\nRemaining: none\nbody\n', encoding='utf-8')
        old = self.project / '.myagentkit/workers/RESULT-w0.md'
        old.parent.mkdir(parents=True)
        old.write_text('Kind: blocked\nTask: w0\nAttempt: 1\nRemaining: all\n', encoding='utf-8')
        spawn(self.project, 'w1', fresh)
        os.utime(spawn(self.project, 'w0', old), (since.timestamp() - 60,) * 2)
        presence = self.project / '.myagentkit/presence'
        for record in ('away %s\n' % since.isoformat(), 'present %s %s\n' % (since.isoformat(), (now + timedelta(minutes=5)).isoformat())):
            presence.write_text(record, encoding='utf-8')
            with self.subTest(record=record):
                result = subprocess.run([sys.executable, str(SCRIPT), '--project', str(self.project)],
                                        capture_output=True, text=True, encoding='utf-8', timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('## Done', result.stdout)
                self.assertIn('night work', result.stdout)
                self.assertIn('worker change', result.stdout)
                self.assertRegex(result.stdout, r'- merge [0-9a-f]+ Merge the worker')
                self.assertNotIn('before the night', result.stdout)
                self.assertIn('RESULT-w1.md: Kind: completed; Task: w1; Attempt: 1; Remaining: none', result.stdout)
                # The file name, not 'w0': macOS's temp folder (/var/folders/.../..._w0000gn/T) put
                # 'w0' in the cost line's path (CI run 43115553552).
                self.assertNotIn('RESULT-w0', result.stdout)
                self.assertIn('Cost:', result.stdout)
        presence.write_text('present\n', encoding='utf-8')
        result = subprocess.run([sys.executable, str(SCRIPT), '--project', str(self.project)],
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('working_mode.py autopilot', result.stderr)

    def test_a_linked_worktree_reads_the_main_checkouts_record(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name) / 'main'
        self.project.mkdir()
        since = datetime.now().astimezone().replace(microsecond=0) - timedelta(hours=1)
        self.git('init', '-q', '-b', 'main')
        self.git('commit', '-q', '--allow-empty', '-m', 'night work')
        self.git('worktree', 'add', '-q', str(Path(tmp.name) / 'wt'))
        (self.project / '.myagentkit').mkdir()
        (self.project / '.myagentkit/presence').write_text('away %s\n' % since.isoformat(), encoding='utf-8')
        # The workers' worktrees are the main checkout's (review f0563afda926, lead's Low), not the linked one's.
        result_file = self.project / '.claude/worktrees/w1/RESULT-w1.md'
        result_file.parent.mkdir(parents=True)
        result_file.write_text('Kind: completed\nTask: w\nAttempt: 1\nRemaining: none\n', encoding='utf-8')
        spawn(self.project, 'w1', result_file)
        result = subprocess.run([sys.executable, str(SCRIPT), '--project', str(Path(tmp.name) / 'wt')],
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('night work', result.stdout)
        self.assertIn('- .claude/worktrees/w1/RESULT-w1.md: Kind: completed', result.stdout)

    def test_a_committed_old_result_a_night_checkout_wrote_is_not_listed(self):
        # #334 (labricore): a sync worktree made in the absence wrote nine committed RESULT files.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        now = datetime.now().astimezone().replace(microsecond=0)
        since = now - timedelta(hours=1)
        self.git('init', '-q', '-b', 'main')
        (self.project / 'RESULT-old.md').write_text('Kind: completed\nTask: old\nAttempt: 1\nRemaining: none\n')
        self.git('add', 'RESULT-old.md')
        self.git('commit', '-q', '-m', 'old run', when=now - timedelta(days=3))
        self.git('worktree', 'add', '-q', str(self.project / '.claude/worktrees/sync'))
        night = self.project / '.claude/worktrees/w1/RESULT-w1.md'
        night.parent.mkdir(parents=True)
        night.write_text('Kind: completed\nTask: w1\nAttempt: 1\nRemaining: none\n')
        spawn(self.project, 'w1', night)
        (self.project / '.myagentkit/presence').write_text('away %s\n' % since.isoformat(), encoding='utf-8')
        result = subprocess.run([sys.executable, str(SCRIPT), '--project', str(self.project)],
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RESULT-w1.md', result.stdout)
        self.assertNotIn('RESULT-old.md', result.stdout)

    def test_the_results_are_the_spawned_workers_wherever_they_are_never_by_file_time(self):
        # #316 (2026-11-01): about 200 committed RESULT files a worktree checkout had rewritten
        # were listed, and the session's own results at the main root and in .myagentkit/workers/
        # were missed. The spawn records say whose result is listed, and where it is.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        since = datetime.now().astimezone().replace(microsecond=0) - timedelta(hours=1)
        self.git('init', '-q', '-b', 'main')
        self.git('commit', '-q', '--allow-empty', '-m', 'night work')
        head = 'Kind: completed\nTask: %s\nAttempt: 1\nRemaining: none\n'
        # A result the worker's brief put at the main checkout's root (spawn_worker.sh --result).
        (self.project / 'RESULT-root.md').write_text(head % 'root', encoding='utf-8')
        spawn(self.project, 'root', self.project / 'RESULT-root.md')
        # A closed worker: its worktree gone, its result moved under .myagentkit/workers/ and its
        # record kept as NAME.closed-result-path by close_worker.sh.
        workers = self.project / '.myagentkit/workers'
        (workers / 'gone.result.md').write_text(head % 'gone', encoding='utf-8')
        # A reused name (cifix15b review): its earlier runs' results stay, the newest is -10.md, not -9.md.
        (workers / 'again.result.md').write_text(head % 'again 1', encoding='utf-8')
        for n in (2, 9, 10):
            (workers / ('again.result-%d.md' % n)).write_text(head % ('again %d' % n), encoding='utf-8')
        (workers / 'again.closed-result-path').write_text(
            str(self.project / '.claude/worktrees/again/RESULT-again.md') + '\n', encoding='utf-8')
        (workers / 'gone.closed-result-path').write_text(
            str(self.project / '.claude/worktrees/gone/RESULT-gone.md') + '\n', encoding='utf-8')
        # The brief's fallback place, for a record whose path is another host's form.
        (workers / 'RESULT-other.md').write_text(head % 'other', encoding='utf-8')
        (workers / 'other.result-path').write_text('D:/elsewhere/RESULT-other.md\n', encoding='utf-8')
        # Results no spawn of the absence wrote, each with a fresh file time: a checkout's
        # untracked copy and one a worker spawned before the stamp left in its worktree.
        for name in ('copied', 'earlier'):
            path = self.project / '.claude/worktrees' / name / ('RESULT-%s.md' % name)
            path.parent.mkdir(parents=True)
            path.write_text(head % name, encoding='utf-8')
        os.utime(spawn(self.project, 'earlier', self.project / '.claude/worktrees/earlier/RESULT-earlier.md'),
                 (since.timestamp() - 60,) * 2)
        (self.project / '.myagentkit/presence').write_text('away %s\n' % since.isoformat(), encoding='utf-8')
        result = subprocess.run([sys.executable, str(SCRIPT), '--project', str(self.project)],
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('- RESULT-root.md: Kind: completed; Task: root;', result.stdout)
        self.assertIn('- .myagentkit/workers/gone.result.md: Kind: completed; Task: gone;', result.stdout)
        self.assertIn('- .myagentkit/workers/again.result-10.md: Kind: completed; Task: again 10;', result.stdout)
        self.assertEqual(result.stdout.count('again'), 2, result.stdout)
        self.assertIn('- .myagentkit/workers/RESULT-other.md: Kind: completed; Task: other;', result.stdout)
        self.assertNotIn('copied', result.stdout)
        self.assertNotIn('earlier', result.stdout)


def spawn(project, name, result):
    """spawn_worker.sh's record of a spawn: .myagentkit/workers/NAME.result-path names its result."""
    record = project / '.myagentkit/workers' / (name + '.result-path')
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(str(result) + '\n', encoding='utf-8')
    return record


if __name__ == '__main__':
    unittest.main()
