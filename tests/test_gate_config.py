"""The kit's scripts are KIT-OWNED and read the project's values from scripts/gate_config.sh (#94)."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MARKER = re.compile(r'^(# |<!-- )KIT-OWNED:', re.M)
# The project's own files among the scripts: its values, its boundary checks, its check of a
# reviewer's final report. Every other script holds no project content.
PROJECT_OWNED = {'boundary_checks.sh', 'gate_config.sh', 'project_validation.py'}


class GateConfigTests(unittest.TestCase):
    def test_every_script_but_the_projects_own_is_kit_owned_and_holds_no_marker(self):
        # The issue's repro loop: an unmarked kit script is never refreshed by a sync. A
        # kit-owned file is never filled in, so a {{...}} marker in one could never be set.
        unmarked, filled = [], []
        for path in sorted(p for p in (ROOT / 'core/scripts').iterdir() if p.is_file()):
            text = path.read_text(encoding='utf-8')
            if path.name in PROJECT_OWNED:
                self.assertIsNone(MARKER.search(text), path.name)
            elif not MARKER.search(text):
                unmarked.append(path.name)
            elif re.search(r'\{\{[A-Z0-9_]+\}\}', text):
                filled.append(path.name)
        self.assertEqual((unmarked, filled), ([], []))

    def test_the_gate_and_the_review_wrapper_refuse_to_run_without_gate_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / 'scripts').mkdir()
            for name in ('check.sh', 'review.sh'):
                shutil.copyfile(ROOT / 'core/scripts' / name, project / 'scripts' / name)
            subprocess.run(['git', 'init', '-q', str(project)], check=True)
            for name, code in (('check.sh', 1), ('review.sh', 2)):
                with self.subTest(script=name):
                    result = subprocess.run(['sh', 'scripts/' + name], cwd=project, capture_output=True,
                                            text=True, timeout=120)
                    self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                    self.assertIn("scripts/gate_config.sh is missing; copy the kit's core/scripts/gate_config.sh",
                                  result.stdout)

    def test_the_sync_moves_exactly_the_values_the_template_holds(self):
        # sync-kit.sh carries these values out of a project's old check.sh and review.sh into
        # gate_config.sh; a value the template gained or lost would be dropped on the way.
        sync = (ROOT / 'sync-kit.sh').read_text(encoding='utf-8')
        moved = set()
        for name in ('check.sh', 'review.sh'):
            names = re.search(r'^    scripts/%s\) echo \'([A-Za-z_|]+)\' ;;$' % re.escape(name), sync, re.M)
            self.assertIsNotNone(names, name)
            moved |= set(names[1].split('|'))
        template = (ROOT / 'core/scripts/gate_config.sh').read_text(encoding='utf-8')
        self.assertEqual(moved, set(re.findall(r'^([A-Za-z_]+)=', template, re.M)))
        # Each has its default in the script that reads it, set before the file is sourced.
        gate = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
        review = (ROOT / 'core/scripts/review.sh').read_text(encoding='utf-8')
        defaults = gate.split('[ -f scripts/gate_config.sh ]', 1)[0] + review.split('[ -f "$script_dir/gate_config.sh" ]', 1)[0]
        for name in moved:
            self.assertRegex(defaults, r'(^|\s)%s=' % name)


if __name__ == '__main__':
    unittest.main()
