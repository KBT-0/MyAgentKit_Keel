"""Exercise the mode command against disposable project documents."""
import os
import hashlib
import importlib.util
import io
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'core/scripts/working_mode.py'
PLUGIN = ROOT / 'plugins/myagentkit/scripts/working_mode.py'
MODES = ('solo', 'cross', 'saver')
# saver must name its low side (owner decision 2026-10-13); the helper supplies the example note.
SIDES = {'saver': 'low: claude'}


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

    def run_mode(self, *args, cwd=None, env=None):
        if len(args) == 1 and args[0].casefold() in SIDES:
            args = (args[0], SIDES[args[0].casefold()])
        return subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPT), '--project', str(self.project), *args],
                              capture_output=True, text=True, encoding='utf-8', timeout=15, cwd=cwd or self.project,
                              env=env)

    def module(self):
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        return loaded

    def temporary(self, folder):
        """An environment whose temporary folder is FOLDER, never the user's own."""
        return dict(os.environ, TMPDIR=str(folder), TEMP=str(folder), TMP=str(folder))

    def snapshot(self, name='STATE.edit.md'):
        """--read-state into the project's private folder: the snapshot's path and its sha256."""
        path = self.project / '.myagentkit' / name
        result = self.run_mode('--read-state', str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        sha, _, printed = result.stdout.strip().partition(' ')
        return Path(printed) if printed else path, sha

    def test_read_state_never_truncates_an_existing_hard_link(self):
        victim = self.project / 'build.py'
        victim.write_bytes(b'keep this script\n')
        requested = self.project / '.myagentkit/STATE.edit.md'
        requested.parent.mkdir()
        os.link(victim, requested)
        snapshot, sha = self.snapshot()
        self.assertEqual(victim.read_bytes(), b'keep this script\n')
        self.assertNotEqual(snapshot, requested)
        self.assertEqual(snapshot.read_bytes(), self.state.read_bytes())
        self.assertEqual(sha, hashlib.sha256(self.state.read_bytes()).hexdigest())

    def test_two_reads_own_distinct_snapshots_and_keep_the_first_draft(self):
        before = self.state.read_bytes()
        first, sha = self.snapshot()
        first.write_bytes(before + b'Writer A task.\n')
        second, second_sha = self.snapshot()
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), before + b'Writer A task.\n')
        self.assertEqual(second.read_bytes(), before)
        self.assertEqual(sha, second_sha)
        result = self.run_mode('--replace-state', str(first), '--expect', sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state.read_bytes(), before + b'Writer A task.\n')
        self.assertTrue(second.exists())

    def test_snapshot_cleanup_preserves_a_successor_at_the_supplied_name(self):
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        snapshot, sha = self.snapshot()
        edited = snapshot.read_bytes() + b'Writer A task.\n'
        snapshot.write_bytes(edited)
        replace = os.replace
        def publishing(source, target):
            replace(source, target)
            if target == self.state:
                successor = snapshot.with_suffix('.new')
                successor.write_bytes(b'Writer B draft.\n')
                replace(successor, snapshot)
        with mock.patch.object(worker.os, 'replace', publishing):
            worker.replace_state(self.project, snapshot, sha)
        self.assertEqual(self.state.read_bytes(), edited)
        self.assertTrue(snapshot.exists(), 'cleanup deleted the successor snapshot')
        self.assertEqual(snapshot.read_bytes(), b'Writer B draft.\n')

    def test_snapshot_cleanup_deletes_only_the_object_read_by_fstat(self):
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        snapshot, sha = self.snapshot()
        opening, replace, reads = Path.open, os.replace, []
        def opened(path, mode='r', *args, **kwargs):
            if mode == 'rb' and path != self.state:
                reads.append(path)
            return opening(path, mode, *args, **kwargs)
        def publishing(source, target):
            replace(source, target)
            if target == self.state:
                self.assertEqual(len(reads), 1)
                fresh = reads[0].with_suffix('.new')
                fresh.write_bytes(b'A successor at the consumed name.\n')
                replace(fresh, reads[0])
        with mock.patch.object(worker.os, 'replace', publishing), mock.patch.object(Path, 'open', opened), \
                mock.patch('sys.stderr', new=io.StringIO()) as errors:
            worker.replace_state(self.project, snapshot, sha)
        self.assertEqual(reads[0].read_bytes(), b'A successor at the consumed name.\n')
        self.assertIn('kept at ' + str(reads[0]), errors.getvalue())

    def test_show_defaults_without_writing_and_lists_all_three(self):
        before = self.state.read_bytes()
        result = self.run_mode()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Current mode: solo', result.stdout)
        for name in MODES:
            self.assertIn(name, result.stdout)
        self.assertEqual(self.state.read_bytes(), before)
        self.assertFalse((self.project / '.claude/mode').exists())

    def test_switch_records_both_files_preserves_state_and_prints_saver_rules(self):
        self.state.write_text('# State\n---\n**Working mode:** solo (keep this note).\nActive work.\n', encoding='utf-8')
        result = self.run_mode('Saver')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.project / '.claude/mode').read_text(encoding='utf-8').strip(), 'saver')
        self.assertEqual(self.state.read_text(encoding='utf-8'), '# State\n---\n**Working mode:** saver (low: claude, after: solo).\nActive work.\n')
        self.assertIn('#### saver', result.stdout)
        self.assertNotIn('#### solo', result.stdout)
        self.assertIn('allowance resets', result.stdout)
        self.assertIn('Current mode: saver (returns to solo)', self.run_mode().stdout)

    def test_saver_records_the_mode_it_interrupted_and_solo_gets_its_family_back(self):
        # Only the lead's session knew which mode saver interrupted: a hand-off or a compaction
        # lost it, and a Codex-family solo came back as a Claude one.
        self.state.write_text('**Working mode:** solo (family: codex).\n', encoding='utf-8')
        self.assertEqual(self.run_mode('saver', 'low: codex').returncode, 0)
        self.assertEqual(self.state.read_text(encoding='utf-8'),
                         '**Working mode:** saver (low: codex, after: solo, family: codex).\n')
        self.assertIn('Current mode: saver (returns to solo, family: codex)', self.run_mode().stdout)
        # A second saver switch changes the low side and keeps what it interrupted.
        self.assertEqual(self.run_mode('saver', 'low: claude').returncode, 0)
        self.assertIn('saver (low: claude, after: solo, family: codex).', self.state.read_text(encoding='utf-8'))
        self.assertEqual(self.run_mode('solo').returncode, 0)
        self.assertEqual(self.state.read_text(encoding='utf-8'), '**Working mode:** solo (family: codex).\n')
        for mode, line in (('cross', 'cross\n'), ('solo', 'solo\n')):
            with self.subTest(mode=mode):
                self.state.write_text('**Working mode:** %s' % line, encoding='utf-8')
                self.assertEqual(self.run_mode(mode).returncode, 0)
                self.assertEqual(self.run_mode('saver').returncode, 0)
                self.assertIn('saver (low: claude, after: %s)' % mode, self.state.read_text(encoding='utf-8'))
                self.assertEqual(self.run_mode(mode).returncode, 0)
                self.assertEqual(self.state.read_text(encoding='utf-8'), '**Working mode:** ' + line)
        # The owner may name the return by hand, and a note naming another mode is refused.
        self.assertEqual(self.run_mode('saver', 'low: claude, after: cross').returncode, 0)
        self.assertIn('saver (low: claude, after: cross)', self.state.read_text(encoding='utf-8'))
        self.assertNotEqual(self.run_mode('saver', 'low: claude, after: saver').returncode, 0)

    def test_every_mode_switches_and_missing_line_is_added(self):
        for mode in MODES:
            result = self.run_mode(mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('**Working mode:** ' + mode, self.state.read_text(encoding='utf-8'))
            self.assertEqual((self.project / '.claude/mode').read_text(encoding='utf-8').strip(), mode)
            self.assertIn('Active work stays here.', self.state.read_text(encoding='utf-8'))

    def test_a_missing_line_is_added_with_the_note_the_switch_names(self):
        # The added line had a fixed text: STATE never said who writes, and a bare switch
        # later refused the kept note.
        pointer = ' (docs/WORKFLOW.md, "Working modes, by name").'
        for args, line in ((('saver',), 'saver (low: claude, after: solo).'),(('solo', 'family: codex'), 'solo (family: codex).'),
                           (('cross',), 'cross' + pointer), (('solo',), 'solo' + pointer)):
            with self.subTest(args=args):
                self.state.write_text('# State\n---\nActive.\n', encoding='utf-8')
                self.assertEqual(self.run_mode(*args).returncode, 0)
                self.assertIn('**Working mode:** ' + line, self.state.read_text(encoding='utf-8'))
                self.assertEqual(self.run_mode(args[0].title()).returncode, 0)
                self.assertIn('**Working mode:** ' + line, self.state.read_text(encoding='utf-8'))

    def test_cross_routes_each_task_by_fit_and_reviews_by_the_direction_rule(self):
        result = self.run_mode('CROSS')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Current mode: cross', result.stdout)
        self.assertIn('the family that did not write a change reviews it, at every tier', result.stdout)
        self.assertIn("Codex reviews what Claude\n  wrote, a low-tier change's light pass included, one pass, report only, at medium effort", result.stdout)
        self.assertIn('agents.max_concurrent_threads_per_session=2', result.stdout)
        self.assertNotIn('#### saver', result.stdout)
        saver = self.run_mode('saver')
        self.assertIn("One side's allowance is low", saver.stdout)
        self.assertIn('the side that is not low implements every errand and fixes every finding', saver.stdout)
        self.assertIn('the low side reviews within a small budget', saver.stdout)
        self.assertIn("it goes to the other side only with the owner's yes", saver.stdout)

    def test_an_old_state_mode_name_is_refused_with_the_mapping_not_mapped(self):
        self.state.write_text('**Working mode:** codex-first (set by hand).\n', encoding='utf-8')
        for args in ((), ('solo',)):
            result = self.run_mode(*args)
            self.assertEqual(result.returncode, 1)
            self.assertIn('invalid STATE.md working mode: codex-first; it is a mode name from before v0.11', result.stderr)
            # One mapping, every old name in it, and the sanctioned repair path named.
            self.assertIn('--replace-state', result.stderr)
            self.assertIn('claude-only is solo; cross-performance, claude-first and codex-first are cross', result.stderr)
            self.assertIn('cross-saving, claude-saver and codex-saver are saver with a (low: ...) note', result.stderr)
        self.assertIn('codex-first', self.state.read_text(encoding='utf-8'))
        self.assertFalse((self.project / '.claude/mode').exists())

    def test_an_old_state_mode_name_is_repaired_only_through_replace_state(self):
        # The compare-and-swap rule had no sanctioned path for the v0.11 upgrade: the switch
        # refused the old name and --replace-state refused any change to the line.
        self.state.write_text('# State\n---\n**Working mode:** cross-saving (x).\nActive.\n', encoding='utf-8')
        snapshot, sha = self.snapshot()
        snapshot.write_bytes(snapshot.read_bytes().replace(b'cross-saving (x)', b'saver (low: codex)'))
        result = self.run_mode('--replace-state', str(snapshot), '--expect', sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('**Working mode:** saver (low: codex).', self.state.read_text(encoding='utf-8'))
        self.assertIn('Current mode: saver', self.run_mode().stdout)
        # Only that repair: a new name to a new name, or an old name to another old name, is refused.
        for old, new in ((b'saver (low: codex)', b'cross (low: codex)'),):
            snapshot, sha = self.snapshot()
            snapshot.write_bytes(snapshot.read_bytes().replace(old, new))
            self.assertNotEqual(self.run_mode('--replace-state', str(snapshot), '--expect', sha).returncode, 0)
        self.state.write_text('**Working mode:** codex-first (x).\n', encoding='utf-8')
        snapshot, sha = self.snapshot()
        snapshot.write_bytes(b'**Working mode:** claude-first (x).\n')
        self.assertNotEqual(self.run_mode('--replace-state', str(snapshot), '--expect', sha).returncode, 0)
        self.assertIn('codex-first', self.state.read_text(encoding='utf-8'))

    def test_the_shipped_state_template_switches_whole_and_a_wrapped_note_is_refused(self):
        # The template's note once wrapped onto a second line: STATE_LINE read the first line
        # only, the sides switch replaced that half and left the tail as an orphan fragment.
        template = (ROOT / 'core/docs/STATE.md').read_bytes()
        self.state.write_bytes(template)
        for mode in ('cross', 'saver', 'solo'):
            self.assertEqual(self.run_mode(mode).returncode, 0, mode)
            text = self.state.read_text(encoding='utf-8')
            self.assertNotIn('names another', text)
            self.assertEqual(text.count('('), text.count(')'), text)
        self.assertEqual(self.state.read_bytes(), template.replace(
            b'solo (`docs/WORKFLOW.md`, "Working modes, by name"; `/myagentkit:mode` switches it).', b'solo'))
        wrapped = ('**Working mode:** solo (`docs/WORKFLOW.md`, "Working modes, by name"; the owner\n'
                   'names another, and `/myagentkit:mode` sets it).\n')
        for mode in ('cross', 'solo'):
            self.state.write_text(wrapped, encoding='utf-8')
            result = self.run_mode(mode)
            self.assertEqual(result.returncode, 1, mode)
            self.assertIn('wraps onto the next line', result.stderr)
            self.assertEqual(self.state.read_text(encoding='utf-8'), wrapped)
        self.assertIn('Current mode: solo', self.run_mode().stdout)

    def test_saver_needs_its_note_solo_may_name_its_family_and_cross_takes_none(self):
        # A saver→cross switch kept `(low: claude)`, a note cross does not take; the default
        # solo line's pointer note was kept the same way. Now the note is set, never carried.
        self.state.write_text('**Working mode:** saver (low: claude).\n', encoding='utf-8')
        for args, error in ((('saver', 'family: codex'), 'takes its note'),
                            (('solo', 'low: claude'), 'takes its note'), (('cross', 'low: claude'), 'cross takes no note'),
                            (('cross', 'family: codex'), 'cross takes no note')):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPT), '--project', str(self.project),
                                         *args], capture_output=True, text=True, encoding='utf-8', timeout=15)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(error, result.stderr)
                self.assertIn('(low: claude).', self.state.read_text(encoding='utf-8'))
        self.assertEqual(self.run_mode('solo', '(family: codex)').returncode, 0)
        self.assertIn('**Working mode:** solo (family: codex).', self.state.read_text(encoding='utf-8'))
        self.assertEqual(self.run_mode('cross').returncode, 0)
        self.assertEqual(self.state.read_text(encoding='utf-8'), '**Working mode:** cross\n')
        # saver keeps a low note of the right shape, but from cross a bare saver names no low side.
        bare = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPT), '--project', str(self.project), 'saver'],
                              capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(bare.returncode, 1, bare.stdout)
        self.assertIn('takes its note', bare.stderr)
        self.assertEqual(self.state.read_text(encoding='utf-8'), '**Working mode:** cross\n')
        self.assertEqual(self.run_mode('saver').returncode, 0)
        self.assertIn('**Working mode:** saver (low: claude, after: cross)', self.state.read_text(encoding='utf-8'))
        self.assertEqual(self.run_mode('solo').returncode, 0)
        self.assertEqual(self.state.read_text(encoding='utf-8'), '**Working mode:** solo\n')
        # A note of the right shape is kept, and a note that is not a mode note stays with solo and cross.
        self.state.write_text('**Working mode:** solo (family: codex).\n', encoding='utf-8')
        self.assertEqual(self.run_mode('solo').returncode, 0)
        self.assertIn('solo (family: codex).', self.state.read_text(encoding='utf-8'))
        for mode in ('solo', 'cross'):
            self.state.write_text('**Working mode:** solo (docs/WORKFLOW.md, "Working modes, by name").\n', encoding='utf-8')
            self.assertEqual(self.run_mode(mode).returncode, 0)
            self.assertIn(mode + ' (docs/WORKFLOW.md, "Working modes, by name").', self.state.read_text(encoding='utf-8'))
            self.assertEqual(self.run_mode('solo').returncode, 0)

    def test_invalid_name_or_disagreeing_records_never_silently_switches(self):
        before = self.state.read_bytes()
        result = self.run_mode('unknown')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state.read_bytes(), before)
        self.assertEqual(self.run_mode('cross').returncode, 0)
        (self.project / '.claude/mode').write_text('saver\n', encoding='utf-8')
        self.assertNotEqual(self.run_mode().returncode, 0)
        # An explicit owner choice repairs the disagreement.
        self.assertEqual(self.run_mode('solo').returncode, 0)

    def test_old_workflow_and_missing_state_are_refused_without_writes(self):
        (self.project / 'docs/WORKFLOW.md').write_text('# Old workflow\n', encoding='utf-8')
        self.assertNotEqual(self.run_mode('cross').returncode, 0)
        self.assertFalse((self.project / '.claude/mode').exists())
        (self.project / 'docs/WORKFLOW.md').write_bytes((ROOT / 'core/docs/WORKFLOW.md').read_bytes())
        self.state.unlink()
        self.assertNotEqual(self.run_mode('cross').returncode, 0)

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
            self.assertNotEqual(self.run_mode('saver').returncode, 0)
            self.assertFalse((target / 'mode').exists())
            self.assertEqual(self.state.read_bytes(), before)
        finally:
            if os.name == 'nt':
                link.rmdir()
            else:
                link.unlink()

    def test_state_accepts_case_without_adding_a_line(self):
        for value in ('Saver', 'SAVER'):
            self.state.write_text('**Working mode:** ' + value + ' (manual).\n', encoding='utf-8')
            self.assertIn('Current mode: saver', self.run_mode().stdout)
            self.assertEqual(self.run_mode('cross').returncode, 0)
            text = self.state.read_text(encoding='utf-8')
            self.assertEqual(text.count('**Working mode:**'), 1)
            self.assertIn('cross (manual).', text)
            (self.project / '.claude/mode').unlink()

    def test_list_item_and_indented_state_lines_are_read_and_switched_in_place(self):
        for line in ('- **Working mode:** saver (set by hand).', '  **Working mode:** Saver'):
            with self.subTest(line=line):
                self.state.write_text('# State\n---\n' + line + '\nActive.\n', encoding='utf-8')
                self.assertIn('Current mode: saver', self.run_mode().stdout)
                self.assertEqual(self.run_mode('cross').returncode, 0)
                text = self.state.read_text(encoding='utf-8')
                self.assertEqual(text.count('Working mode:'), 1, text)
                self.assertIn(line.split('**Working mode:**')[0] + '**Working mode:** cross', text)
                (self.project / '.claude/mode').unlink()

    def test_unknown_and_duplicate_state_lines_are_refused_before_writes(self):
        for text in ('**Working mode:** mystery\n',
                     '**Working mode:** saver\n**Working mode:** Cross\n',
                     '- **Working mode:** saver\n**Working mode:** cross\n',
                     'Working mode: saver\n', '> **Working mode:** saver\n'):
            self.state.write_text(text, encoding='utf-8')
            for args in ((), ('cross',)):
                result = self.run_mode(*args)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(self.state.read_text(encoding='utf-8'), text)
            self.assertFalse((self.project / '.claude/mode').exists())

    def test_a_mode_has_its_english_name_only(self):
        # The owner named the modes solo, cross and saver; the Turkish names left every surface
        # (KARARLAR B06 inv3#178). A name the helper does not know is refused, never mapped.
        self.assertIn('Current mode: solo', self.run_mode('SOLO').stdout)
        for name in ('Tek Model Modu', 'TEK MODEL MODU', 'Çapraz Mod', 'Tasarruf Modu'):
            with self.subTest(name=name):
                before = self.state.read_bytes()
                result = self.run_mode(name)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn('unknown mode; choose solo, cross, saver', result.stderr)
                self.assertEqual(self.state.read_bytes(), before)
        self.state.write_text('**Working mode:** Tasarruf Modu (manual).\n', encoding='utf-8')
        result = self.run_mode()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('invalid STATE.md working mode: Tasarruf Modu', result.stderr)

    def test_cp1252_pipe_switch_prints_utf8_rules_after_writes(self):
        workflow = self.project / 'docs/WORKFLOW.md'
        # A heading may carry a note after the name, as the v0.11 drafts' headings did.
        workflow.write_text(workflow.read_text(encoding='utf-8').replace(
            '#### cross\n', '#### cross (işi ağır)\n'), encoding='utf-8')
        code = ('import sys,runpy; sys.stdout.reconfigure(encoding="cp1252"); '
                'sys.argv=[%r,"--project",%r,"cross"]; runpy.run_path(%r,run_name="__main__")') % (
                    str(SCRIPT), str(self.project), str(SCRIPT))
        result = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('işi ağır', result.stdout.decode('utf-8'))
        self.assertEqual((self.project / '.claude/mode').read_text(encoding='utf-8').strip(), 'cross')

    def test_atomic_replacement_copies_original_permissions(self):
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import shutil
        with mock.patch.object(shutil, 'copymode', wraps=shutil.copymode) as copy:
            with mock.patch('sys.stdout', new=io.StringIO()):
                module.mode(self.project, 'cross')
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
                competitors.append(self.run_mode('saver'))
        with mock.patch.object(module.os, 'replace', side_effect=interrupted), \
                mock.patch('sys.stdout', new=io.StringIO()):
            module.mode(self.project, 'cross')
        self.assertNotEqual(competitors[0].returncode, 0, 'overlapping switch was allowed')
        self.assertIn('mode switch in progress', competitors[0].stderr)
        self.assertIn('Current mode: cross', self.run_mode().stdout)
        self.assertEqual(self.run_mode('saver').returncode, 0, 'switch lock was not released')

    def test_state_edit_during_preparation_is_refused_without_losing_work(self):
        self.assertEqual(self.run_mode('solo').returncode, 0)
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
                module.mode(self.project, 'cross')
        self.assertEqual(self.state.read_bytes(), concurrent)
        self.assertEqual((self.project / '.claude/mode').read_text(encoding='utf-8').strip(), 'solo')
        self.assertEqual(self.run_mode('saver').returncode, 0)

    def test_failed_record_replace_does_not_roll_back_an_independent_state_edit(self):
        self.assertEqual(self.run_mode('solo').returncode, 0)
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
                module.mode(self.project, 'cross')
        self.assertEqual(self.state.read_bytes(), concurrent[0])
        self.assertIn('disagree', self.run_mode().stderr)

    def test_rollback_cancellation_never_truncates_state(self):
        self.assertEqual(self.run_mode('solo').returncode, 0)
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
                module.mode(self.project, 'cross')
        self.assertEqual(self.state.read_bytes(), published[0])
        self.assertIn(b'Active work stays here.', self.state.read_bytes())
        self.assertNotEqual(self.state.read_bytes(), before)
        self.assertIn('disagree', self.run_mode().stderr)
        self.assertEqual(self.run_mode('saver').returncode, 0)

    def test_a_root_named_through_a_link_is_resolved_once_and_written_where_it_leads(self):
        # macOS /tmp and a linked home are ordinary ways to name a project; links below it are not.
        link = self.project / 'linked-project'
        if os.name == 'nt':
            subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(self.project)],
                           check=True, capture_output=True)
        else:
            link.symlink_to(self.project, target_is_directory=True)
        child = self.project / 'child'
        (child / 'docs').mkdir(parents=True)
        (child / 'docs/STATE.md').write_bytes(self.state.read_bytes())
        (child / 'docs/WORKFLOW.md').write_bytes((self.project / 'docs/WORKFLOW.md').read_bytes())
        try:
            for root, real in ((link, self.project), (link / 'child', child)):
                with self.subTest(root=root):
                    result = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPT), '--project',
                                             str(root), 'cross'], capture_output=True, text=True,
                                            encoding='utf-8', timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('**Working mode:** cross', (real / 'docs/STATE.md').read_text(encoding='utf-8'))
                    self.assertEqual((real / '.claude/mode').read_text(encoding='utf-8').strip(), 'cross')
        finally:
            if os.name == 'nt':
                link.rmdir()
            else:
                link.unlink()

    def test_only_a_name_surrogate_reparse_point_is_refused(self):
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        docs, lstat = self.project / 'docs', Path.lstat
        # A cloud-file placeholder (IO_REPARSE_TAG_CLOUD_1) is no link; a junction (MOUNT_POINT) is.
        for tag, refused in ((0x9000101A, False), (0xA0000003, True)):
            with self.subTest(tag=hex(tag)):
                def fake(path, *args, **kwargs):
                    if path != docs:
                        return lstat(path, *args, **kwargs)
                    return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_reparse_tag=tag,
                                           st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
                with mock.patch.object(Path, 'lstat', fake), mock.patch('sys.stdout', new=io.StringIO()):
                    if refused:
                        with self.assertRaisesRegex(ValueError, 'linked path refused'):
                            module.mode(self.project, 'saver', SIDES['saver'])
                    else:
                        module.mode(self.project, 'cross')
                        self.assertEqual((self.project / '.claude/mode').read_text(encoding='utf-8').strip(), 'cross')
        self.assertIn('**Working mode:** cross', self.state.read_text(encoding='utf-8'))

    def test_a_project_below_v0_11_is_named_by_its_kit_version_not_by_its_table(self):
        # The helper once recognized a pre-v0.11 project by counting the rows of WORKFLOW.md's
        # mode table, a proxy (KARARLAR D10 inv2#136): it reads the version the sync recorded.
        workflow = self.project / 'docs/WORKFLOW.md'
        current = workflow.read_bytes()
        lines = current.decode('utf-8').split('\n')
        old = ['| `%s` | Old | - | - | - |' % name for name in
               ('claude-first', 'cross-performance', 'cross-saving', 'codex-first', 'claude-saver', 'codex-saver')]
        start = next(i for i, l in enumerate(lines) if l.startswith('| `solo` |'))
        six = '\n'.join(lines[:start] + old + lines[start + 3:]).encode('utf-8')
        stamp = self.project / 'docs/kit/.kit-version'
        stamp.parent.mkdir()
        before = self.state.read_bytes()
        # Below 0.11 (0.9 too: the comparison is numeric), whatever the table: a show succeeds,
        # a requested switch that did not happen fails, and neither creates the lock.
        for version, table in (('0.10', current), ('0.10', six), ('0.9\n', current)):
            stamp.write_text(version, encoding='utf-8')
            workflow.write_bytes(table)
            for args, status in (((), 0), (('cross',), 1)):
                with self.subTest(version=version, rows=table.count(b'| `'), args=args):
                    result = subprocess.run([sys.executable, '-X', 'utf8', str(PLUGIN), '--project', str(self.project),
                                             *args], capture_output=True, text=True, encoding='utf-8', timeout=15)
                    self.assertEqual(result.returncode, status, result.stderr)
                    self.assertIn('ACTION: this project records kit v' + version.strip() + ' (docs/kit/.kit-version)', result.stdout)
                    self.assertIn('sync-kit.sh', result.stdout)
                    self.assertEqual(self.state.read_bytes(), before)
                    self.assertFalse((self.project / '.claude').exists())
        # At 0.11 or later, or with no recorded version, an old or incomplete table is a defect,
        # refused as one; the table's rows never decide the version.
        misspelled = current.replace(b'| `saver` |', b'| `savr` |')
        for version, table in (('0.11', six), ('1.0', misspelled), (None, six)):
            if version is None:
                stamp.unlink()
            else:
                stamp.write_text(version, encoding='utf-8')
            workflow.write_bytes(table)
            for args in ((), ('saver',)):
                with self.subTest(version=version, args=args):
                    result = self.run_mode(*args)
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertNotIn('ACTION', result.stdout)
                    self.assertIn('must define the three modes', result.stderr)
                    self.assertFalse((self.project / '.claude').exists())
        stamp.write_text('v0.11-beta', encoding='utf-8')
        workflow.write_bytes(current)
        result = self.run_mode('cross')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('unreadable kit version in docs/kit/.kit-version', result.stderr)
        self.assertFalse((self.project / '.claude').exists())
        stamp.write_text('0.11\n', encoding='utf-8')
        self.assertEqual(self.run_mode('cross').returncode, 0)

    def test_interrupted_switch_reports_repair_and_releases_the_lock(self):
        self.assertEqual(self.run_mode('solo').returncode, 0)
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
                module.mode(self.project, 'cross')
        result = self.run_mode()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('.claude/mode and STATE.md disagree', result.stderr)
        self.assertIn('choose a mode explicitly to repair', result.stderr)
        self.assertEqual(self.run_mode('saver').returncode, 0)
        self.assertIn('Current mode: saver', self.run_mode().stdout)

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
                del Path.is_junction  # Python 3.11 has no such API.
                with self.assertRaisesRegex(ValueError, 'linked path refused'):
                    module.mode(self.project, 'saver', SIDES['saver'])
            self.assertFalse((target / 'mode').exists())
            self.assertEqual(self.state.read_bytes(), before)
        finally:
            link.rmdir()

    def test_solo_reviews_with_another_tier_of_the_same_family_and_no_second_vendor(self):
        result = self.run_mode('solo')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Current mode: solo', result.stdout)
        self.assertIn('the author and the reviewer are different tiers', result.stdout)
        self.assertIn('fresh\n  bridged session with no shared context', result.stdout)
        self.assertIn('REVIEW_CLAUDE_MODEL', result.stdout)
        self.assertIn("A second session of the author's own tier\n  is never the review", result.stdout)
        self.assertIn('no second vendor runs', result.stdout)
        self.assertNotIn('#### saver', result.stdout)
        self.assertNotIn('#### cross', result.stdout)

    def test_read_state_writes_the_snapshot_with_its_sha_without_a_lock(self):
        before = b'# State\r\nAn active task.\r\n'
        self.state.write_bytes(before)
        snapshot, sha = self.snapshot()
        self.assertEqual(sha, hashlib.sha256(before).hexdigest())
        self.assertEqual(snapshot.read_bytes(), before)
        self.assertEqual(self.state.read_bytes(), before)
        self.assertFalse((self.project / '.claude').exists())

    def test_a_snapshot_read_before_a_concurrent_edit_is_refused_and_a_late_read_keeps_that_edit(self):
        # Writer 1 read STATE at its session start; writer 2 then publishes Task B.
        stale = self.state.read_bytes()
        early, early_sha = self.snapshot('writer-1.md')
        theirs, sha = self.snapshot('writer-2.md')
        theirs.write_bytes(theirs.read_bytes() + b'Task B.\n')
        self.assertEqual(self.run_mode('--replace-state', str(theirs), '--expect', sha).returncode, 0)
        # No hash comes apart from its bytes: a stale copy hashed late cannot pass.
        hashing = self.run_mode('--state-sha')
        self.assertEqual(hashing.returncode, 2, hashing.stdout)
        early.write_bytes(stale + b'Task C.\n')
        refused = self.run_mode('--replace-state', str(early), '--expect', early_sha)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('STATE.md sha256 mismatch', refused.stderr)
        self.assertIn(b'Task B.', self.state.read_bytes())
        # Read late, the snapshot it edits already holds Task B.
        late, late_sha = self.snapshot('writer-1.md')
        late.write_bytes(late.read_bytes() + b'Task C.\n')
        self.assertEqual(self.run_mode('--replace-state', str(late), '--expect', late_sha).returncode, 0)
        self.assertEqual(self.state.read_bytes(), stale + b'Task B.\nTask C.\n')

    def test_an_edit_that_changes_the_working_mode_line_is_refused(self):
        self.assertEqual(self.run_mode('solo').returncode, 0)
        before = self.state.read_bytes()
        for edited in (before.replace(b'solo', b'cross'),
                       b''.join(line for line in before.splitlines(True) if b'Working mode' not in line)):
            with self.subTest(edited=edited):
                snapshot, sha = self.snapshot()
                snapshot.write_bytes(edited)
                result = self.run_mode('--replace-state', str(snapshot), '--expect', sha)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Working mode line', result.stderr)
                self.assertIn('mode switch', result.stderr)
                self.assertEqual(self.state.read_bytes(), before)
        self.assertIn('Current mode: solo', self.run_mode().stdout)

    def test_state_operations_stay_in_the_project_and_its_private_folder(self):
        before = self.state.read_bytes()
        secret = self.project / 'secret.txt'
        secret.write_bytes(b'not for STATE\n')
        sha = hashlib.sha256(before).hexdigest()
        outside = Path(self.tmp.name).resolve().parent
        for args, cwd in ((('--replace-state', str(secret), '--expect', sha), None),
                          (('--read-state', str(self.project / 'docs/copy.md')), None),
                          (('--read-state', str(self.project / '.myagentkit/x.md')), outside)):
            with self.subTest(args=args, cwd=cwd):
                result = self.run_mode(*args, cwd=cwd)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('mode: ', result.stderr)
                self.assertEqual(self.state.read_bytes(), before)
        self.assertFalse((self.project / 'docs/copy.md').exists())
        self.assertFalse((self.project / '.myagentkit/x.md').exists())
        # A snapshot in the temporary folder outside the project works and is gone once published.
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder) / 'STATE.edit.md'
            read = self.run_mode('--read-state', str(snapshot))
            self.assertEqual(read.returncode, 0, read.stderr)
            sha, printed = read.stdout.strip().split(' ', 1)
            snapshot = Path(printed)
            snapshot.write_bytes(before + b'A new task.\n')
            result = self.run_mode('--replace-state', str(snapshot), '--expect', sha)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(snapshot.exists(), 'the published snapshot was left behind')
        self.assertEqual(self.state.read_bytes(), before + b'A new task.\n')

    def test_replace_state_refuses_a_folder_and_moves_nothing(self):
        before = self.state.read_bytes()
        sha = hashlib.sha256(before).hexdigest()
        private = self.project / '.myagentkit'
        (private / 'workers').mkdir(parents=True)
        (private / 'workers/w.session').write_text('session\n', encoding='utf-8')
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            fake = Path(folder).resolve()
            (fake / 'mine.txt').write_text('the user\'s file\n', encoding='utf-8')
            for target in (private, private / 'workers', fake):
                with self.subTest(target=target.name):
                    result = self.run_mode('--replace-state', str(target), '--expect', sha, env=self.temporary(fake))
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('a prepared STATE.md file is a regular file', result.stderr)
            self.assertEqual((fake / 'mine.txt').read_text(encoding='utf-8'), 'the user\'s file\n')
            self.assertEqual([p.name for p in fake.parent.iterdir() if p.name.startswith('.' + fake.name)], [])
        self.assertEqual((private / 'workers/w.session').read_text(encoding='utf-8'), 'session\n')
        self.assertLessEqual({p.name for p in self.project.iterdir()}, {'.claude', '.myagentkit', 'docs'})
        self.assertEqual([p.name for p in private.iterdir()], ['workers'])
        self.assertEqual(self.state.read_bytes(), before)

    def test_a_folder_swapped_in_after_the_check_goes_back_and_nothing_is_published(self):
        worker = self.module()
        before = self.state.read_bytes()
        snapshot, sha = self.snapshot()
        renaming = os.rename
        def swapped(source, target):
            if Path(target).name == 'snapshot':
                Path(source).unlink()
                Path(source).mkdir()
                (Path(source) / 'keep.txt').write_text('keep\n', encoding='utf-8')
            renaming(source, target)
        with mock.patch.object(worker.os, 'rename', swapped):
            with self.assertRaisesRegex(ValueError, 'regular file'):
                worker.replace_state(self.project, snapshot, sha)
        self.assertEqual((snapshot / 'keep.txt').read_text(encoding='utf-8'), 'keep\n')
        self.assertEqual([p.name for p in snapshot.parent.iterdir()], [snapshot.name])
        self.assertEqual(self.state.read_bytes(), before)

    def test_failed_folder_restoration_cannot_leave_private_contents_visible_to_git(self):
        worker = self.module()
        before = self.state.read_bytes()
        sha = hashlib.sha256(before).hexdigest()
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True, capture_output=True)
        (self.project / '.gitignore').write_text('/.myagentkit/\n/.claude/\n', encoding='utf-8')
        source = self.project / '.myagentkit'
        source.write_bytes(before)  # a regular FILE named after the private directory
        source = worker.private(self.project, source)
        initially_visible = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'], cwd=self.project,
                                           check=True, capture_output=True, text=True, encoding='utf-8').stdout.splitlines()
        renaming = os.rename
        consumed = []
        def swapped(path, target):
            if Path(path) == source:
                source.unlink()
                source.mkdir()
                (source / 'w.session').write_text('private session\n', encoding='utf-8')
                renaming(path, target)
                consumed.append(Path(target))
                source.mkdir()
                (source / 'successor').write_text('keep the successor\n', encoding='utf-8')
            else:
                renaming(path, target)  # restoration cannot replace the nonempty successor
        with mock.patch.object(worker.os, 'rename', swapped), mock.patch('sys.stderr', io.StringIO()):
            with self.assertRaises((ValueError, OSError)):
                worker.replace_state(self.project, source, sha)
        visible = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'], cwd=self.project,
                                 check=True, capture_output=True, text=True, encoding='utf-8').stdout.splitlines()
        self.assertEqual(sorted(visible), sorted(initially_visible),
                         'a failed recovery exposed private contents to git')
        self.assertEqual(consumed, [], 'the recovery parent must be private before consuming FILE')
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(self.state.read_bytes(), before)

    def test_a_file_whose_folder_is_not_private_is_named_in_the_refusal(self):
        worker = self.module()
        sha = hashlib.sha256(self.state.read_bytes()).hexdigest()
        source = self.project / '.myagentkit'
        source.write_bytes(self.state.read_bytes())  # private itself, its folder the project root
        result = self.run_mode('--replace-state', str(source), '--expect', sha)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FILE's own folder must be inside .myagentkit/ or the temporary folder", result.stderr)
        self.assertIn(worker.shown(source.resolve()), result.stderr)
        self.assertTrue(source.is_file())

    def test_failed_folder_restoration_keeps_its_recovery_inside_the_private_parent(self):
        worker = self.module()
        before = self.state.read_bytes()
        source, sha = self.snapshot()
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True, capture_output=True)
        (self.project / '.gitignore').write_text('/.myagentkit/\n/.claude/\n', encoding='utf-8')
        renaming = os.rename
        def swapped(path, target):
            if Path(path) == source:
                source.unlink()
                source.mkdir()
                (source / 'w.session').write_text('private session\n', encoding='utf-8')
                renaming(path, target)
                source.mkdir()
                (source / 'successor').write_text('keep the successor\n', encoding='utf-8')
            else:
                renaming(path, target)
        errors = io.StringIO()
        with mock.patch.object(worker.os, 'rename', swapped), mock.patch('sys.stderr', errors):
            with self.assertRaises(OSError):
                worker.replace_state(self.project, source, sha)
        kept = Path(errors.getvalue().split(' kept at ', 1)[1].strip())
        self.assertTrue(kept.is_relative_to(self.project / '.myagentkit'))
        self.assertEqual((kept / 'w.session').read_text(encoding='utf-8'), 'private session\n')
        self.assertEqual((source / 'successor').read_text(encoding='utf-8'), 'keep the successor\n')
        visible = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'], cwd=self.project,
                                 check=True, capture_output=True, text=True, encoding='utf-8').stdout.splitlines()
        self.assertEqual(sorted(visible), ['.gitignore', 'docs/STATE.md', 'docs/WORKFLOW.md'])
        self.assertEqual(self.state.read_bytes(), before)

    def test_read_state_refuses_a_folder_as_out_and_writes_nothing_outside(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder).resolve()
            env = self.temporary(fake)
            # .myagentkit not there yet: the snapshot would land beside it, in the project root.
            for out in ('.myagentkit/', '.myagentkit', str(fake), str(fake) + os.sep):
                with self.subTest(out=out):
                    result = self.run_mode('--read-state', out, env=env)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('mode: ', result.stderr)
            self.assertFalse((self.project / '.myagentkit').exists())
            (self.project / '.myagentkit').mkdir()
            for out in ('.myagentkit', '.myagentkit' + os.sep, str(self.project / '.myagentkit')):
                with self.subTest(out=out):
                    result = self.run_mode('--read-state', out, env=env)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn('never a folder', result.stderr)
            self.assertEqual([p.name for p in fake.parent.iterdir() if p.name.startswith(fake.name + '-')], [])
            self.assertEqual(list(fake.iterdir()), [])
        self.assertEqual(sorted(p.name for p in self.project.iterdir()), ['.myagentkit', 'docs'])
        self.assertEqual(list((self.project / '.myagentkit').iterdir()), [])

    def test_a_refused_edit_that_cannot_go_back_names_where_its_draft_is_kept(self):
        self.assertEqual(self.run_mode('solo').returncode, 0)
        worker = self.module()
        snapshot, sha = self.snapshot()
        edited = snapshot.read_bytes().replace(b'solo', b'cross')
        snapshot.write_bytes(edited)
        renaming = os.rename
        def rename(source, target):
            renaming(source, target)
            if Path(source) == snapshot:
                snapshot.write_bytes(b'A successor draft.\n')  # so the exclusive link back is refused
        errors = io.StringIO()
        with mock.patch.object(worker.os, 'rename', rename), mock.patch('sys.stderr', errors):
            with self.assertRaisesRegex(ValueError, 'Working mode line'):
                worker.replace_state(self.project, snapshot, sha)
        self.assertIn('mode: the unpublished snapshot is kept at ', errors.getvalue())
        kept = Path(errors.getvalue().split(' kept at ', 1)[1].strip())
        self.assertEqual(kept.read_bytes(), edited)
        self.assertEqual(snapshot.read_bytes(), b'A successor draft.\n')
        self.assertEqual(worker.shown('a\x1b]0;t\x07b\nc'), 'a?]0;t?b?c')

    def test_state_cas_refuses_a_wrong_expectation_without_publishing(self):
        before = self.state.read_bytes()
        proposed = self.project / '.myagentkit/replacement.md'
        proposed.parent.mkdir()
        proposed.write_bytes(b'A different task.\n')
        result = self.run_mode('--replace-state', str(proposed), '--expect', '0' * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('STATE.md sha256 mismatch', result.stderr)
        self.assertIn('--read-state', result.stderr)
        self.assertIn('retry', result.stderr)
        self.assertEqual(self.state.read_bytes(), before)
        self.assertEqual(proposed.read_bytes(), b'A different task.\n')
        self.assertEqual(list(self.state.parent.glob('.STATE.md-*')), [])
        self.assertFalse((self.project / '.claude/mode').exists())

    def test_state_cas_keeps_permissions_and_replaces_complete_bytes(self):
        self.state.chmod(0o666 if os.name == 'nt' else 0o640)
        permissions = stat.S_IMODE(self.state.stat().st_mode)
        before = self.state.read_bytes()
        proposed, sha = self.snapshot()
        proposed.write_bytes(before + b'A new active task.\r\n')
        result = self.run_mode('--replace-state', str(proposed), '--expect', sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state.read_bytes(), before + b'A new active task.\r\n')
        self.assertFalse(proposed.exists())
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), permissions)
        self.assertEqual(list(self.state.parent.glob('.STATE.md-*')), [])
        self.assertFalse((self.project / '.claude/mode').exists())

    def state_writer_race(self, rollback):
        self.assertEqual(self.run_mode('solo').returncode, 0)
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        proposed = self.project / '.myagentkit/replacement.md'
        proposed.parent.mkdir()
        reading, replacing = Path.read_bytes, os.replace
        checks, refusals, snapshots = [], [], []
        def checked(path):
            contents = reading(path)
            if path == self.state:
                checks.append(contents)
                # The publication probe runs after the snapshot recheck; the rollback probe
                # runs after the rollback guard read. Both still hold the switch lock.
                if len(checks) == (3 if rollback else 2):
                    snapshots.append(contents)
                    proposed.write_bytes(contents + b'An independent active task.\n')
                    refusals.append(self.run_mode('--replace-state', str(proposed), '--expect',
                                                  hashlib.sha256(contents).hexdigest()))
            return contents
        def replace(source, target):
            if rollback and target.name == 'mode':
                raise OSError('record replacement failed')
            replacing(source, target)
        with mock.patch.object(Path, 'read_bytes', checked), \
                mock.patch.object(worker.os, 'replace', replace), mock.patch('sys.stdout', new=io.StringIO()):
            if rollback:
                with self.assertRaisesRegex(OSError, 'record replacement failed'):
                    worker.mode(self.project, 'cross')
            else:
                worker.mode(self.project, 'cross')
        self.assertEqual(len(refusals), 1, 'the intended STATE race was not scheduled')
        self.assertNotEqual(refusals[0].returncode, 0)
        self.assertIn('mode switch in progress', refusals[0].stderr)
        # A stale retry cannot overwrite the switch (or its rollback). Re-read and redo.
        refused = self.run_mode('--replace-state', str(proposed), '--expect',
                                hashlib.sha256(snapshots[0]).hexdigest())
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('STATE.md sha256 mismatch', refused.stderr)
        current = self.state.read_bytes()
        proposed.write_bytes(current + b'An independent active task.\n')
        retry = self.run_mode('--replace-state', str(proposed), '--expect', hashlib.sha256(current).hexdigest())
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertEqual(self.state.read_bytes(), current + b'An independent active task.\n')
        self.assertIn('Current mode: ' + ('solo' if rollback else 'cross'),
                      self.run_mode().stdout)

    def test_state_race_refuses_the_writer_then_preserves_its_retried_edit(self):
        self.state_writer_race(rollback=False)

    def test_rollback_race_refuses_the_writer_then_preserves_its_retried_edit(self):
        self.state_writer_race(rollback=True)

    def test_state_cas_and_mode_switch_share_the_lock_in_both_directions(self):
        spec = importlib.util.spec_from_file_location('working_mode', SCRIPT)
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        proposed = self.project / '.myagentkit/replacement.md'
        proposed.parent.mkdir()
        before = self.state.read_bytes()
        proposed.write_bytes(before + b'An independent active task.\n')
        replace, attempts = os.replace, []
        def publishing(source, target):
            if target == self.state:
                self.assertEqual(self.state.read_bytes(), before, 'STATE was truncated before publication')
                attempts.append(self.run_mode('cross'))
            replace(source, target)
        with mock.patch.object(worker.os, 'replace', publishing), \
                mock.patch.object(worker.Path, 'cwd', return_value=self.project), \
                mock.patch('sys.argv', [str(SCRIPT), '--project', str(self.project), '--replace-state',
                                        str(proposed), '--expect', hashlib.sha256(before).hexdigest()]):
            worker.main()
        self.assertEqual(len(attempts), 1)
        self.assertNotEqual(attempts[0].returncode, 0)
        self.assertIn('mode switch in progress', attempts[0].stderr)
        self.assertEqual(self.run_mode('cross').returncode, 0)
        self.assertIn(b'An independent active task.', self.state.read_bytes())


if __name__ == '__main__':
    unittest.main()
