"""The limit watchdog: a fake `claude` on PATH and a fake CLAUDE_CONFIG_DIR; no real session or timer."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'overlays/claude-code/files/scripts'
WATCHDOG = SCRIPTS / 'limit_watchdog.sh'
INSTALL = SCRIPTS / 'limit_watchdog_install.sh'
LIMIT_STOP = ROOT / 'core/scripts/limit_stop.py'
SINCE = '2026-11-09T01:00:00+03:00'
# The hosts the watchdog and the timer exist on; scripts/check_kit.py counts with the same tests.
FLOCK = bool(shutil.which('flock')) and os.name != 'nt'
LINUX = sys.platform.startswith('linux')
ORG = '11111111-2222-3333-4444-555555555555'
# The fake claude: `agents --json --all` prints $FAKE_AGENTS, anything else is a launch, logged one
# argument per line with a separator, and answered as the bg host does (exit $FAKE_RC).
FAKE_CLAUDE = r'''#!/bin/sh
if [ "${1:-}" = agents ]; then cat "$FAKE_AGENTS"; exit 0; fi
for a in "$@"; do printf '%s\n' "$a"; done >>"$FAKE_LAUNCHES"
printf '%s\n' '----' >>"$FAKE_LAUNCHES"
pwd >>"$FAKE_LAUNCHES.cwd"
if [ "${FAKE_RC:-0}" != 0 ]; then echo "Error: could not start"; exit "$FAKE_RC"; fi
# What a started bg daemon is: a process that outlives the launch, its output not on our pipe.
if [ -n "${FAKE_LINGER:-}" ]; then sleep 20 >/dev/null 2>&1 & echo "$!" >>"$FAKE_LINGER"; fi
echo "backgrounded · 1234abcd · lead"
'''
# The fake systemd-run: records its options and execs the command, as --scope does. First on PATH:
# the real user manager is never touched.
FAKE_SYSTEMD_RUN = r'''#!/bin/sh
for a in "$@"; do [ "$a" = -- ] && break; printf '%s\n' "$a"; done >>"$FAKE_SCOPE"
while [ "$1" != -- ]; do shift; done
shift
exec "$@"
'''


PROMPT = ('Read %s and follow it. The limit watchdog opened this session after a limit stop (docs/WORKFLOW.md, '
          '"The watchdog"); the master writer was released: run claim.')


@unittest.skipUnless(FLOCK, 'the watchdog needs flock(1) and a POSIX sh')
class LimitWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.project = self.tmp / 'proj'
        (self.project / 'docs').mkdir(parents=True)
        (self.project / 'docs/WORKFLOW.md').write_bytes((ROOT / 'core/docs/WORKFLOW.md').read_bytes())
        self.store = self.project / '.myagentkit'
        self.store.mkdir()
        self.autopilot(True)
        self.handoff = self.project / 'docs/HANDOFF-next.md'
        self.handoff.write_text('claude --model claude-opus-5-5 (effort: high, the next item)\n\n# Next\n',
                                encoding='utf-8')
        (self.store / 'handoff-pending').write_text('docs/HANDOFF-next.md abc1234\n', encoding='utf-8')
        self.config = self.tmp / 'config'
        self.config.mkdir()
        (self.config / '.claude.json').write_text(json.dumps({'oauthAccount': {'organizationUuid': ORG}}),
                                                  encoding='utf-8')
        self.limits(five=(100, time.time() + 3600))
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        for name, body in (('claude', FAKE_CLAUDE), ('systemd-run', FAKE_SYSTEMD_RUN)):
            (self.bin / name).write_text(body, encoding='utf-8')
            (self.bin / name).chmod(0o755)
        self.scope = self.tmp / 'scope'
        self.agents = self.tmp / 'agents.json'
        self.agents.write_text('[]', encoding='utf-8')
        self.launches = self.tmp / 'launches'
        self.env = dict(os.environ, PATH=os.pathsep.join([str(self.bin), os.environ['PATH']]),
                        CLAUDE_CONFIG_DIR=str(self.config), HOME=str(self.tmp / 'home'),
                        FAKE_AGENTS=str(self.agents), FAKE_LAUNCHES=str(self.launches), FAKE_SCOPE=str(self.scope))
        for key in ('CLAUDE_CODE_SESSION_ID', 'MYAGENTKIT_SESSION_ID', 'FAKE_RC'):
            self.env.pop(key, None)

    def autopilot(self, away):
        owner = 'away (autopilot since %s)' % SINCE if away else 'present'
        (self.project / 'docs/STATE.md').write_text('# State\n\n**Working mode:** solo\n**Owner:** %s\n\n---\n'
                                                    % owner, encoding='utf-8')
        (self.store / 'presence').write_text(('away %s\n' % SINCE) if away else 'present\n', encoding='utf-8')

    def limits(self, five=None, seven=None):
        data = {}
        for key, value in (('five_hour', five), ('seven_day', seven)):
            if value:
                data[key] = {'used_percentage': value[0], 'resets_at': int(value[1])}
        (self.config / 'rate-limits.json').write_text(json.dumps(data), encoding='utf-8')

    def marker(self, resets_at, org=ORG):
        """limit-stop as limit_stop.py writes it, after (newer than) handoff-pending; rate-limits.json as the
        stopped lead left it: the five-hour window full, resetting at RESETS_AT."""
        self.limits(five=(100, resets_at))
        os.utime(self.store / 'handoff-pending', (time.time() - 60, time.time() - 60))
        (self.store / 'limit-stop').write_text('%d %s %s\n' % (resets_at, org, self.handoff), encoding='utf-8')

    def run_watchdog(self, **extra):
        return subprocess.run(['sh', str(WATCHDOG), str(self.project)], capture_output=True, text=True,
                              encoding='utf-8', env=dict(self.env, **extra), timeout=120)

    def launched(self):
        """Each launch's argument list."""
        if not self.launches.exists():
            return []
        runs = self.launches.read_text(encoding='utf-8').split('----\n')
        return [run.splitlines() for run in runs if run]

    def log(self):
        path = self.store / 'limit-watchdog.log'
        return path.read_text(encoding='utf-8') if path.exists() else ''

    def test_no_marker_does_nothing_and_logs_nothing(self):
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.launched(), [])
        self.assertEqual(self.log(), '')

    def test_a_reset_still_ahead_does_nothing(self):
        self.marker(time.time() + 3600)
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.launched(), [])
        self.assertIn('skip: the limit resets at', self.log())
        self.assertTrue((self.store / 'limit-stop').exists())
        self.run_watchdog()
        self.assertEqual(self.log().count('skip:'), 1, 'a repeated reason is logged once: ' + self.log())

    def test_autopilot_off_does_nothing(self):
        self.marker(time.time() - 60)
        self.autopilot(False)
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.launched(), [])
        self.assertIn('skip: autopilot is off', self.log())

    def test_a_live_lead_does_nothing(self):
        self.marker(time.time() - 60)
        (self.store / 'master-writer').write_text('sess-1\nlead\n', encoding='utf-8')
        self.agents.write_text(json.dumps([{'sessionId': 'sess-1', 'kind': 'interactive', 'pid': 4242}]),
                               encoding='utf-8')
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.launched(), [])
        self.assertIn('skip: the lead sess-1 (master-writer) still runs', self.log())
        # A blocked background session with no process can be woken: it runs too.
        self.agents.write_text(json.dumps([{'sessionId': 'sess-1', 'kind': 'background', 'state': 'blocked'}]),
                               encoding='utf-8')
        self.run_watchdog()
        self.assertEqual(self.launched(), [])

    def test_every_condition_true_launches_exactly_one_lead(self):
        # The master writer names a session that has ended (done, no process): it is gone.
        (self.store / 'master-writer').write_text('sess-old\n', encoding='utf-8')
        self.agents.write_text(json.dumps([{'sessionId': 'sess-old', 'kind': 'background', 'state': 'done'}]),
                               encoding='utf-8')
        self.marker(time.time() - 60)
        result = self.run_watchdog(CLAUDE_CODE_SESSION_ID='the-callers-session')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.launched(), [[
            PROMPT % self.handoff, '--bg', '--model', 'claude-opus-5-5', '--effort', 'high',
            '--settings', '{"permissions":{"defaultMode":"auto"}}']])
        self.assertEqual(Path(self.tmp / 'launches.cwd').read_text(encoding='utf-8').strip(), str(self.project))
        self.assertFalse((self.store / 'limit-stop').exists())
        lines = self.log().splitlines()
        self.assertEqual(len(lines), 1, self.log())
        self.assertRegex(lines[0], r'^\S+ launched 1234abcd %s \(model claude-opus-5-5, effort high\)$'
                         % self.handoff)
        again = self.run_watchdog()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(len(self.launched()), 1, 'a second run launches nothing')

    def test_the_window_under_half_for_that_org_counts_as_the_reset(self):
        self.marker(time.time() + 3600)
        self.limits(five=(20, time.time() + 7200))
        (self.config / '.claude.json').write_text(json.dumps({'oauthAccount': {'organizationUuid': 'other'}}),
                                                  encoding='utf-8')
        self.run_watchdog()
        self.assertEqual(self.launched(), [], 'another org\'s window says nothing of the marker\'s')
        (self.config / '.claude.json').write_text(json.dumps({'oauthAccount': {'organizationUuid': ORG}}),
                                                  encoding='utf-8')
        self.run_watchdog()
        self.assertEqual(len(self.launched()), 1, self.log())

    def test_a_held_lock_does_nothing(self):
        # Imported here: native Windows has no fcntl, and a module-level import cost the
        # portable LimitStopTests their Windows run (CI run 43115553552).
        import fcntl
        self.marker(time.time() - 60)
        with open(self.store / 'limit-watchdog.lock', 'a') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.launched(), [])
        self.assertTrue((self.store / 'limit-stop').exists())
        self.assertIn('holds', self.log())

    def test_a_failed_launch_keeps_the_marker_and_is_never_retried(self):
        self.marker(time.time() - 60)
        result = self.run_watchdog(FAKE_RC='3')
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.store / 'limit-stop').exists())
        self.assertIn('launch failed: claude --bg exited 3', self.log())
        self.run_watchdog()
        self.assertEqual(len(self.launched()), 1, 'no retry for the same limit-stop')

    def test_a_handoff_newer_than_the_marker_or_without_a_model_does_nothing(self):
        self.marker(time.time() - 60)
        os.utime(self.store / 'handoff-pending', (time.time() + 5, time.time() + 5))
        self.run_watchdog()
        self.assertIn('newer than limit-stop', self.log())
        self.marker(time.time() - 60)
        self.handoff.write_text('# Hand-off\n', encoding='utf-8')
        self.run_watchdog()
        self.assertEqual(self.launched(), [])
        self.assertIn('names no model and effort', self.log())

    def test_a_window_at_its_cap_again_does_nothing(self):
        # The marker's reset has passed, but the same org's five-hour window is full again.
        self.marker(time.time() - 60)
        self.limits(five=(96, time.time() + 3600))
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.launched(), [])
        self.assertIn('five_hour window is at 96% again', self.log())
        self.assertTrue((self.store / 'limit-stop').exists())

    def test_a_marker_naming_another_handoff_does_nothing(self):
        self.marker(time.time() - 60)
        other = self.project / 'docs/HANDOFF-other.md'
        other.write_text(self.handoff.read_text(encoding='utf-8'), encoding='utf-8')
        (self.store / 'limit-stop').write_text('%d %s %s\n' % (time.time() - 60, ORG, other), encoding='utf-8')
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.launched(), [])
        self.assertIn('skip: limit-stop names %s and handoff-pending %s: not the same hand-off'
                      % (other, self.handoff), self.log())

    def test_a_process_the_launch_leaves_does_not_hold_the_lock(self):
        pids = self.tmp / 'linger.pids'
        self.addCleanup(self.end_lingering, pids)
        self.marker(time.time() - 60)
        self.run_watchdog(FAKE_LINGER=str(pids))
        self.assertEqual(len(self.launched()), 1, self.log())
        self.assertTrue(pids.exists(), 'the fake claude left no process')
        self.marker(time.time() - 60)
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('holds', self.log())
        self.assertEqual(len(self.launched()), 2, self.log())

    def end_lingering(self, pids):
        """Ends only the `sleep` this test's fake claude left, by the pid it recorded."""
        for pid in pids.read_text(encoding='utf-8').split() if pids.exists() else []:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass

    def test_the_launch_runs_in_its_own_scope(self):
        # Under a oneshot service a daemon the launch starts dies with the unit's cgroup otherwise.
        self.marker(time.time() - 60)
        result = self.run_watchdog()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.scope.read_text(encoding='utf-8').split(), ['--user', '--scope', '--collect', '--quiet'])
        self.assertEqual(len(self.launched()), 1, self.log())
        self.assertEqual(self.launched()[0][0], PROMPT % self.handoff)

    def test_no_systemd_run_is_a_plain_launch(self):
        # A PATH of only what the script needs: this host's real systemd-run is not on it.
        tools = self.tmp / 'tools'
        tools.mkdir()
        for name in ('sh', 'flock', 'python3', 'date', 'tr', 'tail', 'sed', 'cut', 'rm', 'cat', 'dirname', 'env'):
            (tools / name).symlink_to(shutil.which(name))
        (tools / 'claude').symlink_to(self.bin / 'claude')
        self.marker(time.time() - 60)
        result = self.run_watchdog(PATH=str(tools))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.launched()), 1, self.log())
        self.assertFalse(self.scope.exists())


class LimitStopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.project = self.tmp / 'proj'
        (self.project / '.myagentkit').mkdir(parents=True)
        self.config = self.tmp / 'config'
        self.config.mkdir()
        (self.config / '.claude.json').write_text(json.dumps({'oauthAccount': {'organizationUuid': ORG}}),
                                                  encoding='utf-8')
        (self.config / 'rate-limits.json').write_text(json.dumps({
            'five_hour': {'used_percentage': 100, 'resets_at': 1793000000},
            'seven_day': {'used_percentage': 40, 'resets_at': 1793500000}}), encoding='utf-8')
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.config), HOME=str(self.tmp / 'home'))

    def run_stop(self):
        return subprocess.run([sys.executable, str(LIMIT_STOP), '--project', str(self.project)], capture_output=True,
                              text=True, encoding='utf-8', env=self.env, timeout=60)

    def test_writes_the_reset_the_org_and_the_handoff(self):
        (self.project / 'HANDOFF.md').write_text('claude --model claude-opus-5-5 (effort: high)\n', encoding='utf-8')
        (self.project / '.myagentkit/handoff-pending').write_text('HANDOFF.md abc1234\n', encoding='utf-8')
        result = self.run_stop()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.project / '.myagentkit/limit-stop').read_text(encoding='utf-8'),
                         '1793000000 %s %s\n' % (ORG, self.project / 'HANDOFF.md'))

    def test_refuses_without_handoff_pending(self):
        result = self.run_stop()
        self.assertEqual(result.returncode, 1)
        self.assertIn('the hand-off comes first', result.stderr)
        self.assertFalse((self.project / '.myagentkit/limit-stop').exists())

    def test_a_seven_day_window_at_its_cap_gives_its_later_reset(self):
        (self.project / 'HANDOFF.md').write_text('claude --model claude-opus-5-5 (effort: high)\n', encoding='utf-8')
        (self.project / '.myagentkit/handoff-pending').write_text('HANDOFF.md abc1234\n', encoding='utf-8')
        (self.config / 'rate-limits.json').write_text(json.dumps({
            'five_hour': {'used_percentage': 60, 'resets_at': 1793000000},
            'seven_day': {'used_percentage': 98, 'resets_at': 1793500000}}), encoding='utf-8')
        result = self.run_stop()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.project / '.myagentkit/limit-stop').read_text(encoding='utf-8'),
                         '1793500000 %s %s\n' % (ORG, self.project / 'HANDOFF.md'))


@unittest.skipUnless(LINUX, 'the installer writes a systemd user timer: Linux only')
class InstallTests(unittest.TestCase):
    def test_install_writes_the_units_and_uninstall_removes_them(self):
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp, True)
        project, bin_dir, calls = tmp / 'my proj', tmp / 'bin', tmp / 'systemctl.log'
        project.mkdir()
        bin_dir.mkdir()
        # A fake systemctl, first on PATH: the real user manager is never touched.
        for name, body in (('systemctl', 'printf "%%s\\n" "$*" >>"%s"' % calls), ('claude', 'exit 0')):
            (bin_dir / name).write_text('#!/bin/sh\n%s\n' % body, encoding='utf-8')
            (bin_dir / name).chmod(0o755)
        env = dict(os.environ, HOME=str(tmp / 'home'), XDG_CONFIG_HOME=str(tmp / 'xdg'),
                   PATH=os.pathsep.join([str(bin_dir), os.environ['PATH']]), CLAUDE_CONFIG_DIR=str(tmp / 'acct'))
        run = lambda *args: subprocess.run(['sh', str(INSTALL), str(project), *args], capture_output=True, text=True,
                                           encoding='utf-8', env=env, timeout=60)
        result = run()
        self.assertEqual(result.returncode, 0, result.stderr)
        units = tmp / 'xdg/systemd/user'
        timer = (units / 'myagentkit-watchdog@.timer').read_text(encoding='utf-8')
        self.assertIn('OnUnitActiveSec=10min', timer)
        self.assertIn('OnBootSec=2min', timer)
        dropins = list(units.glob('myagentkit-watchdog@*.service.d/project.conf'))
        self.assertEqual(len(dropins), 1, dropins)
        conf = dropins[0].read_text(encoding='utf-8')
        self.assertIn('Environment="MYAGENTKIT_PROJECT=%s"' % project, conf)
        self.assertIn('Environment="MYAGENTKIT_WATCHDOG=%s"' % WATCHDOG, conf)
        self.assertIn('Environment="CLAUDE_CONFIG_DIR=%s"' % (tmp / 'acct'), conf)
        # The launched lead and its workers inherit this PATH: the installer's own, whole.
        self.assertIn('Environment="PATH=%s"\n' % env['PATH'], conf)
        instance = dropins[0].parent.name[:-len('.service.d')]
        self.assertIn('--user enable --now %s.timer' % instance, calls.read_text(encoding='utf-8'))
        other = tmp / 'elsewhere/my proj'
        other.mkdir(parents=True)
        clash = subprocess.run(['sh', str(INSTALL), str(other)], capture_output=True, text=True, encoding='utf-8',
                               env=env, timeout=60)
        self.assertEqual(clash.returncode, 1)
        self.assertIn('is installed for %s' % project, clash.stderr)
        result = run('--uninstall')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in units.iterdir()), [])
        self.assertIn('--user disable --now %s.timer' % instance, calls.read_text(encoding='utf-8'))


# Declared platform skips (scripts/check_kit.py, run_tests): macOS has no flock(1), and only Linux
# has the systemd user timer (launchd is not built).
for case, runs in ((LimitWatchdogTests, FLOCK), (InstallTests, LINUX)):
    for attribute in dir(case):
        if attribute.startswith('test_'):
            getattr(case, attribute)._kit_platform_skip = not runs
del case, runs, attribute  # a module-level TestCase name is collected twice


if __name__ == '__main__':
    unittest.main()
