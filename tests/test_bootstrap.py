"""Bootstrap must not distribute locally generated Python bytecode."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class BootstrapTests(unittest.TestCase):
    def test_bytecode_is_not_installed(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            kit, project = Path(tmp) / 'kit', Path(tmp) / 'project'
            scripts = kit / 'core/scripts'
            (scripts / '__pycache__').mkdir(parents=True)
            (scripts / '__pycache__/helper.cpython-314.pyc').write_bytes(b'\xff\x00')
            (scripts / 'legacy.pyc').write_bytes(b'\xff\x00')
            (scripts / 'helper.py').write_text('"""Fixture source."""\n')
            shutil.copyfile(root / 'bootstrap.sh', kit / 'bootstrap.sh')
            (kit / 'CHANGELOG.md').write_text('## v0.7\n')
            result = subprocess.run(['sh', str(kit / 'bootstrap.sh'), str(project)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((project / 'scripts/helper.py').is_file())
            self.assertFalse(list(project.rglob('*.pyc')), 'Local bytecode entered the installed project')
