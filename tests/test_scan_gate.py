"""Run the shipped scanner against real grep/xargs outcomes on each CI platform."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class ScanGateTests(unittest.TestCase):
    def test_scanner_distinguishes_matches_absence_and_real_errors(self):
        source = Path(__file__).resolve().parents[1] / 'core/scripts/check.sh'
        function = re.search(r'^scan_grep\(\) \{\n.*?^\}', source.read_text(), re.M | re.S).group()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '-v').write_text('ordinary content\nMATCH\n')
            (root / 'plain').write_text('ordinary content\n')
            for names, expected, failure in ((['-v'], 0, False), (['plain'], 1, False),
                                              (['missing'], 2, True),
                                              (['-v', 'missing'], 2, True)):
                with self.subTest(names=names):
                    flag = root / 'scan_failed'
                    flag.unlink(missing_ok=True)
                    (root / 'files').write_bytes(b'\0'.join(n.encode() for n in names) + b'\0')
                    script = ('work=$PWD\nfilelist=$PWD/files\n' + function +
                              '\nscan_grep MATCH\n')
                    result = subprocess.run(['sh', '-c', script], cwd=root,
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                    self.assertEqual(flag.exists(), failure)
                    if expected == 0:
                        self.assertIn('-v:2:MATCH', result.stdout)


if __name__ == '__main__':
    unittest.main()
