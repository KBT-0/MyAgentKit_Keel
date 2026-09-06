"""Execute the shipped boundary-test example against real and misleading gate failures."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BoundaryExampleTests(unittest.TestCase):
    def test_example_requires_a_green_baseline_and_the_intended_failure(self):
        template = (ROOT / 'core/scripts/boundary_selftests.sh').read_text()
        example = '\n'.join(line[4:] for line in template.splitlines() if line.startswith('#   '))
        self.assertTrue(example.strip())
        for case in ('intended', 'baseline_red', 'wrong_reason', 'missing_gate', 'misleading_success'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                gate = root / 'check.sh'
                gate.write_text('''#!/bin/sh
if [ "${1:-}" = --self-test ]; then
  st_fail=0
''' + example + '''
  exit "$st_fail"
fi
[ "$CASE" != baseline_red ] || { echo 'FAIL: unrelated baseline'; exit 1; }
[ -f src/domain/.selftest.py ] || exit 0
case "$CASE" in
  intended) echo 'FAIL [boundary]: the domain layer imports the web layer:'; exit 1 ;;
  wrong_reason) echo 'FAIL: unrelated build error'; exit 1 ;;
  misleading_success) echo 'FAIL [boundary]: the domain layer imports the web layer:'; exit 0 ;;
  missing_gate) exit 0 ;;
esac
''')
                result = subprocess.run(['sh', str(gate), '--self-test'], cwd=root,
                                        env=dict(os.environ, CASE=case), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0 if case == 'intended' else 1,
                                 result.stdout + result.stderr)
                self.assertFalse((root / 'src/domain/.selftest.py').exists())
