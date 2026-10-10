"""Exercise the mode command against disposable project documents."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'core/scripts/working_mode.py'


class WorkingModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        (self.project / 'docs').mkdir()
        (self.project / 'docs/WORKFLOW.md').write_bytes((ROOT / 'core/docs/WORKFLOW.md').read_bytes())
        self.state = self.project / 'docs/STATE.md'
        self.state.write_text('# State\n\n---\n\nActive work stays here.\n', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def run_mode(self, *args):
        return subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPT), '--project', str(self.project), *args],
                              capture_output=True, text=True, encoding='utf-8', timeout=15)

    def test_show_defaults_without_writing_and_lists_all_six(self):
        before = self.state.read_bytes()
        result = self.run_mode()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Current mode: cross-performance', result.stdout)
        for name in ('claude-first', 'cross-performance', 'cross-saving', 'codex-first', 'claude-saver', 'codex-saver'):
            self.assertIn(name, result.stdout)
        self.assertEqual(self.state.read_bytes(), before)
        self.assertFalse((self.project / '.claude/mode').exists())

    def test_switch_records_both_files_preserves_state_and_prints_saver_rules(self):
        self.state.write_text('# State\n---\n**Working mode:** cross-performance (keep this note).\nActive work.\n', encoding='utf-8')
        result = self.run_mode('Claude Tasarruf Modu')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.project / '.claude/mode').read_text().strip(), 'claude-saver')
        self.assertEqual(self.state.read_text(), '# State\n---\n**Working mode:** claude-saver (keep this note).\nActive work.\n')
        self.assertIn('#### claude-saver', result.stdout)
        self.assertIn('#### The two saver modes', result.stdout)
        self.assertIn('allowance resets', result.stdout)
        self.assertIn('Current mode: claude-saver', self.run_mode().stdout)

    def test_every_mode_switches_and_missing_line_is_added(self):
        for mode in ('claude-first', 'cross-performance', 'cross-saving', 'codex-first', 'claude-saver', 'codex-saver'):
            result = self.run_mode(mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('**Working mode:** ' + mode, self.state.read_text())
            self.assertEqual((self.project / '.claude/mode').read_text().strip(), mode)
            self.assertIn('Active work stays here.', self.state.read_text())

    def test_codex_first_routes_implementation_and_review_fixes_to_codex(self):
        result = self.run_mode('Codex Öncelikli Mod')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Claude Opus lead plans, briefs, routes and reviews', result.stdout)
        self.assertIn('Codex workers write all implementation and all fixes', result.stdout)
        self.assertIn("including fixes of Claude's review findings", result.stdout)
        self.assertIn('too heavy or too important for Codex', result.stdout)
        self.assertIn('Codex reviews that work', result.stdout)
        self.assertNotIn('not yet confirmed', result.stdout)
        saver = self.run_mode('codex-saver')
        self.assertIn("Codex's allowance is low", saver.stdout)
        self.assertIn('Claude workers implement every errand and fix every finding', saver.stdout)

    def test_invalid_name_or_disagreeing_records_never_silently_switches(self):
        before = self.state.read_bytes()
        result = self.run_mode('unknown')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state.read_bytes(), before)
        self.assertEqual(self.run_mode('claude-first').returncode, 0)
        (self.project / '.claude/mode').write_text('codex-first\n')
        self.assertNotEqual(self.run_mode().returncode, 0)
        # An explicit owner choice repairs the disagreement.
        self.assertEqual(self.run_mode('cross-performance').returncode, 0)

    def test_old_workflow_and_missing_state_are_refused_without_writes(self):
        (self.project / 'docs/WORKFLOW.md').write_text('# Old workflow\n')
        self.assertNotEqual(self.run_mode('claude-first').returncode, 0)
        self.assertFalse((self.project / '.claude/mode').exists())
        (self.project / 'docs/WORKFLOW.md').write_bytes((ROOT / 'core/docs/WORKFLOW.md').read_bytes())
        self.state.unlink()
        self.assertNotEqual(self.run_mode('claude-first').returncode, 0)

    def test_linked_mode_directory_is_refused(self):
        target = self.project / 'elsewhere'
        target.mkdir()
        link = self.project / '.claude'
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], check=True, capture_output=True)
        else:
            link.symlink_to(target, target_is_directory=True)
        try:
            before = self.state.read_bytes()
            self.assertNotEqual(self.run_mode('codex-saver').returncode, 0)
            self.assertFalse((target / 'mode').exists())
            self.assertEqual(self.state.read_bytes(), before)
        finally:
            if os.name == 'nt':
                link.rmdir()
            else:
                link.unlink()


if __name__ == '__main__':
    unittest.main()
