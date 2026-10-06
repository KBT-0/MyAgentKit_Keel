"""The kit check's own machinery: a PATH without named commands."""
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_kit', ROOT / 'scripts/check_kit.py')
check_kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_kit)


class KitRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_path_without_drops_only_the_named_commands(self):
        # A directory without them stays as it is; one with them becomes links to the rest.
        plain, mixed = self.tmp / 'plain', self.tmp / 'mixed'
        for directory in (plain, mixed):
            directory.mkdir()
        for path in (plain / 'kept', mixed / 'dropped', mixed / 'other'):
            path.write_text('#!/bin/sh\n')
            path.chmod(0o755)
        (mixed / 'dangling').symlink_to(self.tmp / 'absent')
        path = check_kit.path_without(os.pathsep.join((str(plain), str(mixed), str(self.tmp / 'none'))),
                                      lambda name: name == 'dropped', self.tmp / 'links')
        entries = path.split(os.pathsep)
        self.assertEqual(entries[0], str(plain))
        self.assertEqual(len(entries), 2)
        self.assertIsNone(shutil.which('dropped', path=path))
        self.assertEqual(os.path.realpath(shutil.which('other', path=path)), str((mixed / 'other').resolve()))
        self.assertEqual(sorted(os.listdir(entries[1])), ['other'])


if __name__ == '__main__':
    unittest.main()
