"""The shipped boundary example tests a NEW file in a disposable copy, never in the checkout.

The in-tree new-file example wrote its injection into the checkout as a file Git does not
ignore: a review running there meanwhile failed as stale_checkout, a concurrent `git add -A`
staged it, and a SIGKILL left it behind (KARARLAR B02 inv2#39). One probe now serves a new
file and an existing one, and only its copy outside the checkout ever holds the injection.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'core/scripts'))
from review_test_support import posix_only  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_boundary_restore  # noqa: E402  (its module setup: the python3 shim on Windows)
# Seconds any wait here may take; MYAGENTKIT_TEST_TIMEOUT_SCALE multiplies it on a slow host.
DEADLINE = 30 * float(os.environ.get('MYAGENTKIT_TEST_TIMEOUT_SCALE', '1'))


def setUpModule():
    test_boundary_restore.setUpModule()


class BoundaryExampleTests(unittest.TestCase):
    def test_a_new_file_case_runs_in_the_disposable_copy(self):
        example = '\n'.join(line[4:] for line in (ROOT / 'core/scripts/boundary_selftests.sh')
                            .read_text(encoding='utf-8').splitlines() if line.startswith('# | '))
        target = 'probe_target=src/domain/existing.py'
        self.assertIn(target, example)
        example = example.replace(target, 'probe_target=src/domain/new.py', 1)
        example = example.replace('LC_ALL=C ', 'LC_ALL=C CHECKOUT="$CHECKOUT" ', 1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'project'
            (root / 'scripts').mkdir(parents=True)
            seen = Path(tmp) / 'seen'
            # The injected run records whether the checkout itself holds the new file.
            (root / 'scripts/check.sh').write_text(
                '#!/bin/sh\ncd "$(dirname "$0")/.."\n'
                'if [ "${1:-}" = --self-test ]; then\n  st_fail=0\n' + example +
                '\n  exit "$st_fail"\nfi\n'
                '[ -f src/domain/new.py ] || exit 0\n'
                '[ -e "$CHECKOUT/src/domain/new.py" ] && echo present > "%s" || echo absent > "%s"\n'
                "grep -q 'myapp.web' src/domain/new.py || exit 0\n"
                "echo 'FAIL [boundary]: the domain layer imports the web layer:'\nexit 1\n"
                % (seen.as_posix(), seen.as_posix()), encoding='utf-8', newline='\n')
            git = lambda *args: subprocess.run(['git', *args], cwd=root, check=True,
                                               capture_output=True, text=True).stdout
            git('init', '-q')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
            status = git('status', '--porcelain', '--untracked-files=all', '--ignored')
            scratch = Path(tmp) / 'scratch'
            scratch.mkdir()
            child = subprocess.Popen(['sh', 'scripts/check.sh', '--self-test'], cwd=root,
                                     env=dict(os.environ, TMPDIR=str(scratch), CHECKOUT=root.as_posix()),
                                     encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     start_new_session=True)
            try:
                stdout, stderr = child.communicate(timeout=4 * DEADLINE)
            except subprocess.TimeoutExpired:
                child.kill()
                stdout, stderr = child.communicate()
            self.assertEqual(child.returncode, 0, stdout + stderr)
            self.assertIn('\n  ok   — ', '\n' + stdout)
            self.assertEqual(seen.read_text().strip(), 'absent', 'the injection reached the checkout')
            self.assertFalse((root / 'src').exists())
            self.assertEqual(git('status', '--porcelain', '--untracked-files=all', '--ignored'), status)
            self.assertEqual(list(scratch.iterdir()), [])

    def test_no_example_writes_its_injection_into_the_checkout(self):
        # The in-tree example's own lines: a self-test built from them could not share a
        # review's worktree, which is the rule this example now makes unnecessary.
        template = (ROOT / 'core/scripts/boundary_selftests.sh').read_text(encoding='utf-8')
        self.assertNotIn('.selftest.py', template)

    @posix_only
    def test_the_interrupted_cases_pass_under_a_caller_that_ignores_sigint(self):
        # A `&` job of a non-interactive shell, or nohup, starts with SIGINT ignored, which a
        # shell cannot trap: the interrupted case failed only there, as a timeout.
        child = subprocess.Popen(
            [sys.executable, '-m', 'unittest',
             'test_boundary_restore.BoundaryRestoreTests.test_an_interrupted_existing_file_example_leaves_the_checkout_untouched'],
            cwd=Path(__file__).resolve().parent, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True, preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN))
        try:
            _, stderr = child.communicate(timeout=12 * DEADLINE)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            _, stderr = child.communicate()
        self.assertEqual(child.returncode, 0, stderr[-3000:])


if __name__ == '__main__':
    unittest.main()
