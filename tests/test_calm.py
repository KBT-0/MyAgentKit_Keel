"""core/scripts/calm.sh: a measurement waits for a calm machine (leeway field report 2026-10-26)."""
import os
import subprocess
import unittest
from pathlib import Path

CALM = Path(__file__).resolve().parents[1] / 'core/scripts/calm.sh'


def calm(**env):
    return subprocess.run(['sh', str(CALM)], capture_output=True, text=True, timeout=60,
                          env=dict(os.environ, **dict(dict(CALM_WAIT='0', CALM_HEAVY='no-such-heavy-job-x9'), **env)))


class CalmTests(unittest.TestCase):
    def test_the_load_decides_calm_or_not(self):
        result = calm(CALM_MAX_LOAD='100000')
        if not hasattr(os, 'getloadavg'):  # native Windows: no load average, said and passed
            self.assertIn('NOT MEASURED [calm]', result.stdout)
            return
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r'^CALM load1=[\d.]+ cores=\d+ heavy=none$')
        busy = calm(CALM_MAX_LOAD='0')
        self.assertEqual(busy.returncode, 1, busy.stdout + busy.stderr)
        self.assertRegex(busy.stdout, r'^NOT CALM load1=[\d.]+ cores=\d+ heavy=none after \d+ s$')

    def test_a_heavy_job_is_named_and_keeps_it_not_calm(self):
        if not hasattr(os, 'getloadavg'):
            self.assertIn('NOT MEASURED [calm]', calm().stdout)
            return
        # One process, no shell: a shell's orphaned child kept the test's output pipe open.
        job = subprocess.Popen(['sleep', '173'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            result = calm(CALM_MAX_LOAD='100000', CALM_HEAVY='sleep 173')
        finally:
            job.kill()
            job.wait()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('heavy=sleep 173 after', result.stdout)

    def test_the_quiet_window_is_held_refused_waited_and_released(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, CALM_WINDOW_FILE=os.path.join(tmp, 'w'), CALM_WAIT='0')
            run = lambda *a: subprocess.run(['sh', str(CALM), *a], capture_output=True, text=True,
                                            timeout=60, env=env)
            self.assertEqual(run('status').returncode, 1)
            self.assertEqual(run('window').returncode, 0)
            self.assertEqual(run('hold', 'x').returncode, 2)
            held = run('hold', '600', 'frame', 'bench')
            self.assertEqual(held.returncode, 0, held.stderr)
            status = run('status')
            self.assertEqual(status.returncode, 0)
            self.assertRegex(status.stdout, r'^held for \d+ s more: frame bench \(')
            self.assertIn('already held', run('hold', '60', 'other').stderr)
            self.assertIn('QUIET WINDOW still held', run('window').stdout)
            self.assertEqual(run('release').returncode, 0)
            self.assertEqual(run('status').returncode, 1)
            Path(tmp, 'w').write_text('1\nlong gone\n')  # an expired hold ends by itself
            self.assertEqual(run('status').returncode, 1)
            self.assertEqual(run('hold', '60', 'next').returncode, 0)


if __name__ == '__main__':
    unittest.main()
