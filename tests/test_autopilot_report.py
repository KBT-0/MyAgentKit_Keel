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
        os.utime(old, (since.timestamp() - 60,) * 2)
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
                self.assertNotIn('w0', result.stdout)
                self.assertIn('Cost:', result.stdout)
        presence.write_text('present\n', encoding='utf-8')
        result = subprocess.run([sys.executable, str(SCRIPT), '--project', str(self.project)],
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('working_mode.py autopilot', result.stderr)


if __name__ == '__main__':
    unittest.main()
