"""The one-key hand-off: after /clear (or a new start) the hook points at the pending hand-off once."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

OVERLAY = Path(__file__).resolve().parents[1] / 'overlays/claude-code/files'
HOOK = OVERLAY / '.claude/hooks/handoff_pending.py'


class HandoffPendingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        git = ['git', '-C', str(self.tmp), '-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false']
        subprocess.run(git + ['init', '-q'], check=True)
        (self.tmp / '.gitignore').write_text('.myagentkit/\n.claude/\n', encoding='utf-8')
        subprocess.run(git + ['add', '.gitignore'], check=True)
        subprocess.run(git + ['commit', '-q', '-m', 'first'], check=True)
        (self.tmp / '.myagentkit').mkdir()
        self.marker = self.tmp / '.myagentkit/handoff-pending'
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_hook(self, source, cwd=None, **extra):
        # A worker running this suite carries MYAGENTKIT_ROLE=worker; the hook skips workers.
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_') and k != 'MYAGENTKIT_ROLE'}
        env.update(CLAUDE_PROJECT_DIR=str(self.tmp), **extra)
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({'source': source, 'cwd': str(cwd or self.tmp)}),
                                capture_output=True, text=True, encoding='utf-8', env=env, timeout=30)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        if not result.stdout:
            return ''
        out = json.loads(result.stdout)['hookSpecificOutput']
        self.assertEqual(out['hookEventName'], 'SessionStart')
        return out['additionalContext']

    def test_a_clean_tree_gets_the_line_once_after_clear_or_startup(self):
        for source in ('clear', 'startup'):
            with self.subTest(source=source):
                self.marker.write_text('.myagentkit/v1/handoff-7.md abc1234\n', encoding='utf-8')
                self.assertEqual(self.run_hook(source), 'Read .myagentkit/v1/handoff-7.md first (written at abc1234); '
                                                        'then continue from its Next.')
                self.assertFalse(self.marker.exists())
                self.assertEqual(self.run_hook(source), '')  # one-shot: no loop

    def test_a_dirty_tree_says_so_and_keeps_the_marker(self):
        self.marker.write_text('docs/handoffs/h.md abc1234\n', encoding='utf-8')
        (self.tmp / 'new.txt').write_text('x', encoding='utf-8')
        said = self.run_hook('clear')
        self.assertIn('Read docs/handoffs/h.md first (written at abc1234), but the tree is not clean', said)
        self.assertIn('delete .myagentkit/handoff-pending once that is settled', said)
        self.assertTrue(self.marker.exists())

    def test_a_lead_in_a_linked_worktree_is_judged_by_its_own_tree(self):
        # r2 Medium: the main checkout was judged, so a dirty worktree read clean and lost the marker.
        tree = self.tmp / '.claude/worktrees/lead'
        subprocess.run(['git', '-C', str(self.tmp), 'worktree', 'add', '-q', str(tree), '-b', 'lead'], check=True)
        (tree / 'work.txt').write_text('x', encoding='utf-8')
        self.marker.write_text('h.md abc1234\n', encoding='utf-8')
        self.assertIn('but the tree is not clean', self.run_hook('clear', cwd=tree))
        self.assertTrue(self.marker.exists())
        (tree / 'work.txt').unlink()
        self.assertEqual(self.run_hook('clear', cwd=tree), 'Read h.md first (written at abc1234); then continue from its Next.')
        self.assertFalse(self.marker.exists())

    def test_a_worker_session_neither_reads_nor_deletes_the_lead_marker(self):
        self.marker.write_text('h.md abc1234\n', encoding='utf-8')
        self.assertEqual(self.run_hook('startup', MYAGENTKIT_ROLE='worker'), '')
        self.assertTrue(self.marker.exists())

    def test_no_marker_or_another_source_is_silent(self):
        self.assertEqual(self.run_hook('clear'), '')
        self.marker.write_text('', encoding='utf-8')
        self.assertEqual(self.run_hook('clear'), '')
        self.marker.write_text('h.md abc\n', encoding='utf-8')
        for source in ('resume', 'compact', None):
            with self.subTest(source=source):
                self.assertEqual(self.run_hook(source), '')
                self.assertTrue(self.marker.exists())

    def test_the_overlay_registers_it_for_clear_and_startup(self):
        settings = json.loads((OVERLAY / '.claude/settings.json').read_text(encoding='utf-8'))
        entries = [e for e in settings['hooks']['SessionStart'] if 'handoff_pending.py' in json.dumps(e)]
        self.assertEqual([e['matcher'] for e in entries], ['clear|startup'])


if __name__ == '__main__':
    unittest.main()
