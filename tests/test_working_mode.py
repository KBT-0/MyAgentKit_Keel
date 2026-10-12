"""Exercise the mode command against disposable project documents."""
import os
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'core/scripts/working_mode.py'
MODES = ('claude-first', 'cross-performance', 'cross-saving', 'codex-first', 'claude-saver', 'codex-saver', 'claude-only')


class WorkingModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name).resolve()
        (self.project / 'docs').mkdir()
        (self.project / 'docs/WORKFLOW.md').write_bytes((ROOT / 'core/docs/WORKFLOW.md').read_bytes())
        self.state = self.project / 'docs/STATE.md'
        self.state.write_text('# State\n\n---\n\nActive work stays here.\n', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def run_mode(self, *args):
        return subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPT), '--project', str(self.project), *args],
                              capture_output=True, text=True, encoding='utf-8', timeout=15)

    def test_show_defaults_without_writing_and_lists_all_seven(self):
        before = self.state.read_bytes()
        result = self.run_mode()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Current mode: cross-performance', result.stdout)
        for name in MODES:
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
        for mode in MODES:
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
        self.assertIn("that Opus worker fixes Codex's findings on it, so no model reviews its own fix", result.stdout)
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

    def test_state_accepts_case_and_turkish_labels_without_adding_a_line(self):
        for value in ('Codex-first', 'Codex Öncelikli Mod'):
            self.state.write_text('**Working mode:** ' + value + ' (manual).\n', encoding='utf-8')
            self.assertIn('Current mode: codex-first', self.run_mode().stdout)
            self.assertEqual(self.run_mode('claude-first').returncode, 0)
            text = self.state.read_text(encoding='utf-8')
            self.assertEqual(text.count('**Working mode:**'), 1)
            self.assertIn('claude-first (manual)', text)
            (self.project / '.claude/mode').unlink()

    def test_list_item_and_indented_state_lines_are_read_and_switched_in_place(self):
        for line in ('- **Working mode:** codex-first (set by hand).', '  **Working mode:** Codex-first'):
            with self.subTest(line=line):
                self.state.write_text('# State\n---\n' + line + '\nActive.\n', encoding='utf-8')
                self.assertIn('Current mode: codex-first', self.run_mode().stdout)
                self.assertEqual(self.run_mode('claude-first').returncode, 0)
                text = self.state.read_text(encoding='utf-8')
                self.assertEqual(text.count('Working mode:'), 1, text)
                self.assertIn(line.split('**Working mode:**')[0] + '**Working mode:** claude-first', text)
                (self.project / '.claude/mode').unlink()

    def test_unknown_and_duplicate_state_lines_are_refused_before_writes(self):
        for text in ('**Working mode:** mystery\n',
                     '**Working mode:** codex-first\n**Working mode:** Claude-first\n',
                     '- **Working mode:** codex-first\n**Working mode:** claude-first\n',
                     'Working mode: codex-first\n', '> **Working mode:** codex-first\n'):
            self.state.write_text(text, encoding='utf-8')
            for args in ((), ('claude-first',)):
                result = self.run_mode(*args)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(self.state.read_text(encoding='utf-8'), text)
            self.assertFalse((self.project / '.claude/mode').exists())

    def test_uppercase_turkish_dotted_i_label(self):
        result = self.run_mode('CLAUDE ÖNCELİKLİ MOD')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Current mode: claude-first', result.stdout)

    def test_cp1252_pipe_switch_prints_utf8_rules_after_writes(self):
        workflow = self.project / 'docs/WORKFLOW.md'
        workflow.write_text(workflow.read_text(encoding='utf-8').replace(
            '#### claude-first (', '#### claude-first (işi ağır: '), encoding='utf-8')
        code = ('import sys,runpy; sys.stdout.reconfigure(encoding="cp1252"); '
                'sys.argv=[%r,"--project",%r,"claude-first"]; runpy.run_path(%r,run_name="__main__")') % (
                    str(SCRIPT), str(self.project), str(SCRIPT))
        result = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('işi ağır', result.stdout.decode('utf-8'))
        self.assertEqual((self.project / '.claude/mode').read_text().strip(), 'claude-first')

    def test_atomic_replacement_copies_original_permissions(self):
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import shutil
        with mock.patch.object(shutil, 'copymode', wraps=shutil.copymode) as copy:
            with mock.patch('sys.stdout', new=io.StringIO()):
                module.mode(self.project, 'claude-first')
            self.assertTrue(any(call.args[0] == self.state for call in copy.call_args_list),
                            'STATE replacement must inherit its original permissions')

    def test_overlapping_switch_is_refused_while_both_records_are_replaced(self):
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        replace = os.replace
        competitors = []
        def interrupted(source, target):
            replace(source, target)
            if target == self.state:
                competitors.append(self.run_mode('codex-first'))
        with mock.patch.object(module.os, 'replace', side_effect=interrupted), \
                mock.patch('sys.stdout', new=io.StringIO()):
            module.mode(self.project, 'claude-first')
        self.assertNotEqual(competitors[0].returncode, 0, 'overlapping switch was allowed')
        self.assertIn('mode switch in progress', competitors[0].stderr)
        self.assertIn('Current mode: claude-first', self.run_mode().stdout)
        self.assertEqual(self.run_mode('codex-first').returncode, 0, 'switch lock was not released')

    def test_state_edit_during_preparation_is_refused_without_losing_work(self):
        self.assertEqual(self.run_mode('cross-performance').returncode, 0)
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        before = self.state.read_bytes()
        concurrent = before + b'An independently added task.\n'
        prepare = module.prepared
        def interrupted(path, data):
            pending = prepare(path, data)
            if path.name == 'mode':
                self.state.write_bytes(concurrent)
            return pending
        with mock.patch.object(module, 'prepared', side_effect=interrupted), \
                mock.patch('sys.stdout', new=io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'STATE.md changed'):
                module.mode(self.project, 'claude-first')
        self.assertEqual(self.state.read_bytes(), concurrent)
        self.assertEqual((self.project / '.claude/mode').read_text().strip(), 'cross-performance')
        self.assertEqual(self.run_mode('codex-first').returncode, 0)

    def test_failed_record_replace_does_not_roll_back_an_independent_state_edit(self):
        self.assertEqual(self.run_mode('cross-performance').returncode, 0)
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        replace = os.replace
        concurrent = []
        def interrupted(source, target):
            if target.name == 'mode':
                concurrent.append(self.state.read_bytes() + b'Another active task.\n')
                self.state.write_bytes(concurrent[0])
                raise OSError('record replacement failed')
            replace(source, target)
        with mock.patch.object(module.os, 'replace', side_effect=interrupted):
            with self.assertRaises(OSError):
                module.mode(self.project, 'claude-first')
        self.assertEqual(self.state.read_bytes(), concurrent[0])
        self.assertIn('disagree', self.run_mode().stderr)

    def test_state_writers_share_the_switch_lock_after_both_comparisons(self):
        self.assertEqual(self.run_mode('cross-performance').returncode, 0)
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        read = Path.read_bytes
        attempts = []
        reads = []
        command = ('from pathlib import Path; p=Path(%r); '
                   'p.write_bytes(p.read_bytes()+b"An independently added task.\\n")') % str(self.state)
        def interrupted(path):
            data = read(path)
            if path == self.state:
                reads.append(data)
                if len(reads) >= 2:
                    attempts.append(self.run_mode('--edit-state', sys.executable, '-c', command))
            return data
        replace = os.replace
        def failed(source, target):
            if target.name == 'mode':
                raise OSError('record replacement failed')
            replace(source, target)
        with mock.patch.object(Path, 'read_bytes', interrupted), \
                mock.patch.object(module.os, 'replace', side_effect=failed):
            with self.assertRaises(OSError):
                module.mode(self.project, 'claude-first')
        self.assertGreaterEqual(len(attempts), 2, 'both comparison windows must be exercised')
        for attempt in attempts:
            self.assertNotEqual(attempt.returncode, 0)
            self.assertIn('mode switch in progress', attempt.stderr)
        edited = self.run_mode('--edit-state', sys.executable, '-c', command)
        self.assertEqual(edited.returncode, 0, edited.stderr)
        self.assertIn('An independently added task.', self.state.read_text())
        self.assertIn('Current mode: cross-performance', self.run_mode().stdout)

    def test_rollback_cancellation_never_truncates_state(self):
        self.assertEqual(self.run_mode('cross-performance').returncode, 0)
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        before = self.state.read_bytes()
        replace, opening = os.replace, Path.open
        published = []
        def interrupted(source, target):
            if target.name == 'mode':
                raise OSError('record replacement failed')
            if target == self.state and published:
                raise KeyboardInterrupt()  # cancel before an atomic rollback publication
            replace(source, target)
            if target == self.state:
                published.append(self.state.read_bytes())
        def cancelled_open(path, mode='r', *args, **kwargs):
            handle = opening(path, mode, *args, **kwargs)
            if path == self.state and mode == 'wb':
                handle.close()  # the old rollback has already truncated STATE
                raise KeyboardInterrupt()
            return handle
        with mock.patch.object(module.os, 'replace', side_effect=interrupted), \
                mock.patch.object(Path, 'open', cancelled_open):
            with self.assertRaises(KeyboardInterrupt):
                module.mode(self.project, 'claude-first')
        self.assertEqual(self.state.read_bytes(), published[0])
        self.assertIn(b'Active work stays here.', self.state.read_bytes())
        self.assertNotEqual(self.state.read_bytes(), before)
        self.assertIn('disagree', self.run_mode().stderr)
        self.assertEqual(self.run_mode('codex-first').returncode, 0)

    def test_state_editor_holds_the_lock_and_propagates_its_exit_status(self):
        self.assertEqual(self.run_mode('cross-performance').returncode, 0)
        command = ('import subprocess,sys; from pathlib import Path; '
                   'p=Path(%r); before=p.read_bytes(); '
                   'r=subprocess.run([sys.executable,%r,"--project",%r,"claude-first"],'
                   'capture_output=True,text=True); sys.stderr.write(r.stderr); '
                   'p.write_bytes(before+b"Another active task.\\n"); sys.exit(7)') % (
                       str(self.state), str(SCRIPT), str(self.project))
        result = self.run_mode('--edit-state', sys.executable, '-c', command)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn('mode switch in progress', result.stderr)
        self.assertIn('Another active task.', self.state.read_text())
        self.assertIn('Current mode: cross-performance', self.run_mode().stdout)
        self.assertEqual(self.run_mode('claude-first').returncode, 0, 'the editor kept its lock')

    def test_project_root_and_ancestor_links_are_refused_before_lock_creation(self):
        link = self.project / 'linked-project'
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(self.project)],
                           check=True, capture_output=True)
        else:
            link.symlink_to(self.project, target_is_directory=True)
        before = self.state.read_bytes()
        try:
            for root in (link, link / 'child'):
                with self.subTest(root=root):
                    if root.name == 'child':
                        child = self.project / 'child'
                        (child / 'docs').mkdir(parents=True)
                        (child / 'docs/STATE.md').write_bytes(before)
                        (child / 'docs/WORKFLOW.md').write_bytes((self.project / 'docs/WORKFLOW.md').read_bytes())
                    state = root / 'docs/STATE.md'
                    result = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPT), '--project',
                                             str(root), 'claude-first'], capture_output=True, text=True,
                                            encoding='utf-8', timeout=15)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertIn('linked path refused', result.stderr)
                    self.assertEqual(state.read_bytes(), before)
                    self.assertFalse((root / '.claude').exists(), 'the refusal must precede lock creation')
            self.assertEqual(self.state.read_bytes(), before)
        finally:
            if os.name == 'nt':
                link.rmdir()
            else:
                link.unlink()

    def test_interrupted_switch_reports_repair_and_releases_the_lock(self):
        self.assertEqual(self.run_mode('cross-performance').returncode, 0)
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        replace = os.replace
        def interrupted(source, target):
            if target.name == 'mode':
                raise KeyboardInterrupt()
            replace(source, target)
        with mock.patch.object(module.os, 'replace', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                module.mode(self.project, 'claude-first')
        result = self.run_mode()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('.claude/mode and STATE.md disagree', result.stderr)
        self.assertIn('choose a mode explicitly to repair', result.stderr)
        self.assertEqual(self.run_mode('codex-first').returncode, 0)
        self.assertIn('Current mode: codex-first', self.run_mode().stdout)

    def test_junction_is_refused_without_the_python_312_path_api(self):
        if os.name != 'nt':
            sys.stderr.write('\nNOT RUN: %s (native Windows junction)\n' % self.id())
            return
        target = self.project / 'elsewhere'
        target.mkdir()
        link = self.project / '.claude'
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], check=True, capture_output=True)
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        before = self.state.read_bytes()
        try:
            with mock.patch.object(Path, 'is_junction', create=True), \
                    mock.patch('sys.stdout', new=io.StringIO()):
                del Path.is_junction  # Python 3.10/3.11 have no such API.
                with self.assertRaisesRegex(ValueError, 'linked path refused'):
                    module.mode(self.project, 'codex-first')
            self.assertFalse((target / 'mode').exists())
            self.assertEqual(self.state.read_bytes(), before)
        finally:
            link.rmdir()

    def test_claude_only_reviews_with_another_claude_tier_and_no_codex(self):
        result = self.run_mode('Sadece Claude Modu')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Current mode: claude-only', result.stdout)
        self.assertIn('different Claude tiers', result.stdout)
        self.assertIn('fresh bridged session with no shared context', result.stdout)
        self.assertIn('REVIEW_CLAUDE_MODEL', result.stdout)
        self.assertIn('no Codex worker and no Codex review', result.stdout)
        self.assertIn('Cross review stays mandatory', result.stdout)
        self.assertNotIn('The two saver modes', result.stdout)
        # codex-saver stays its own mode: Codex still reviews there.
        self.assertIn('Codex reviews within a small budget', self.run_mode('codex-saver').stdout)

    def test_codex_saver_has_no_codex_lead_or_worker(self):
        result = self.run_mode('codex-saver')
        self.assertIn('no Codex worker; Codex reviews only', result.stdout)
        self.assertNotIn('a Codex lead', result.stdout)
        self.assertIn('Claude leads in both saver modes', result.stdout)


if __name__ == '__main__':
    unittest.main()
