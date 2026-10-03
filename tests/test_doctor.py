"""doctor.sh must go red on a machine trap and stay green on a ready synthetic machine."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DoctorTests(unittest.TestCase):
    def test_each_injected_trap_turns_doctor_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            project, bin_dir, home = tmp / 'project', tmp / 'bin', tmp / 'home'
            bin_dir.mkdir(); home.mkdir()
            subprocess.run(['sh', str(ROOT / 'bootstrap.sh'), str(project), '--overlay', 'claude-code'],
                           check=True, capture_output=True)
            # Stubs for the tools a ready machine has; the test must not depend on this one.
            for tool in ('claude', 'codex', 'tmux'):
                (bin_dir / tool).write_text('#!/bin/sh\nexit 0\n')
                (bin_dir / tool).chmod(0o755)
            # A controlled timeout, so the grep probe runs whether or not this host has one;
            # doctor calls it as `timeout --foreground -k 1 5 <command>`.
            (bin_dir / 'timeout').write_text('#!/bin/sh\nshift 4\nexec "$@"\n')
            (bin_dir / 'timeout').chmod(0o755)
            shell = bin_dir / 'fake-shell'
            # The common colour alias is harmless and must stay green.
            shell.write_text('#!/bin/sh\necho "grep is an alias for grep --color=auto"\n')
            shell.chmod(0o755)
            env = {k: v for k, v in os.environ.items() if not k.lower().startswith('npm_config_')}
            env.update(HOME=str(home), SHELL=str(shell), GIT_CONFIG_NOSYSTEM='1',
                       PATH=str(bin_dir) + os.pathsep + os.environ['PATH'])
            git = lambda *a: subprocess.run(['git', *a], cwd=project, env=env, check=True)
            git('init', '-q')
            git('config', 'user.name', 'fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'core.hooksPath', '.githooks')
            git('add', '-A')
            doctor = lambda: subprocess.run(['sh', 'scripts/doctor.sh'], cwd=project, env=env,
                                            capture_output=True, text=True)

            ready = doctor()
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            self.assertIn('DOCTOR: ready', ready.stdout)

            hook = project / '.claude/hooks/gate_on_stop.sh'
            hook.chmod(0o644)
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: .claude/hooks/gate_on_stop.sh is not executable', red.stdout)
            hook.chmod(0o755)

            # Executable on disk but not in the index: the next clone does not have it at all.
            git('rm', '-q', '--cached', '.claude/hooks/gate_on_stop.sh')
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: .claude/hooks/gate_on_stop.sh is not in the git index', red.stdout)
            self.assertEqual(red.stdout.count('MISSING:'), 1, red.stdout)
            git('add', '.claude/hooks/gate_on_stop.sh')

            # Without `timeout` (stock macOS) an rc file that waits on the terminal would hang
            # the probe, and with it every session start: the probe is skipped and says so.
            no_timeout = tmp / 'no-timeout-bin'
            no_timeout.mkdir()
            for directory in env['PATH'].split(os.pathsep):
                if os.path.isdir(directory):
                    for name in os.listdir(directory):
                        if name != 'timeout' and not (no_timeout / name).exists():
                            (no_timeout / name).symlink_to(Path(directory) / name)
            shell.write_text('#!/bin/sh\nsleep 60\n')
            try:
                skipped = subprocess.run(['sh', 'scripts/doctor.sh'], cwd=project, capture_output=True,
                                         text=True, env=dict(env, PATH=str(no_timeout)), timeout=20)
            except subprocess.TimeoutExpired:
                self.fail('doctor.sh ran the shell probe without a time limit')
            self.assertEqual(skipped.returncode, 0, skipped.stdout + skipped.stderr)
            self.assertIn('NOTE: grep probe skipped, no timeout on this machine', skipped.stdout)

            shell.write_text('#!/bin/sh\necho "grep is an alias for ugrep"\n')
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: grep is shadowed', red.stdout)
            self.assertEqual(red.stdout.count('MISSING:'), 1, red.stdout)
            # Only colour options are harmless; an alias that changes what matches is not.
            shell.write_text('#!/bin/sh\necho "grep is an alias for grep -v"\n')
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: grep is shadowed', red.stdout)
            shell.write_text("#!/bin/sh\necho \"grep is aliased to \\`grep --colour=auto'\"\n")
            ready = doctor()
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            shell.write_text('#!/bin/sh\necho "grep is an alias for grep --color=auto"\n')

            git('config', '--unset', 'core.hooksPath')
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: the commit gate is not wired (core.hooksPath)', red.stdout)
            git('config', 'core.hooksPath', '.githooks')

            # A checkout on a Windows drive under WSL. The path and /proc/version are injected
            # (DOCTOR_CHECKOUT, DOCTOR_PROC_VERSION) because this machine may be neither.
            wsl = tmp / 'proc_version'
            wsl.write_text('Linux version 5.15.0-microsoft-standard-WSL2 (root@build) #1 SMP\n')
            native = tmp / 'proc_version_native'
            native.write_text('Linux version 6.1.0-generic (root@build) #1 SMP\n')
            env.update(DOCTOR_CHECKOUT='/mnt/c/work/project', DOCTOR_PROC_VERSION=str(wsl))
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: the checkout /mnt/c/work/project is on a Windows drive', red.stdout)
            self.assertEqual(red.stdout.count('MISSING:'), 1, red.stdout)
            env['DOCTOR_PROC_VERSION'] = str(native)  # same path on a real Linux box is fine
            ready = doctor()
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            env['DOCTOR_PROC_VERSION'] = str(wsl)
            env['DOCTOR_CHECKOUT'] = '/home/me/work/project'  # WSL, but on the Linux side
            ready = doctor()
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            del env['DOCTOR_CHECKOUT'], env['DOCTOR_PROC_VERSION']

            # A script converted to CRLF (autocrlf on a Windows checkout) dies in sh.
            check = project / 'scripts/check.sh'
            lf = check.read_bytes()
            check.write_bytes(lf.replace(b'\n', b'\r\n'))
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: scripts/check.sh has CRLF line endings', red.stdout)
            self.assertEqual(red.stdout.count('MISSING:'), 1, red.stdout)
            check.write_bytes(lf)

            # node_modules as a symlink: "node_modules/" matches directories only, so git
            # lists the symlink as untracked and the gate's scanners fail on it (issue 14).
            (tmp / 'deps').mkdir()
            (project / 'node_modules').symlink_to(tmp / 'deps')
            ignore = project / '.gitignore'
            ignore_before = ignore.read_text()
            ignore.write_text(ignore_before + '\nnode_modules/\n')
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: node_modules is a symlink that .gitignore does not ignore', red.stdout)
            self.assertEqual(red.stdout.count('MISSING:'), 1, red.stdout)
            ignore.write_text(ignore_before + '\nnode_modules\n')
            ready = doctor()
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            ignore.write_text(ignore_before)
            (project / 'node_modules').unlink()

            # Drop the stub and every PATH entry holding a real reviewer CLI on this machine.
            full_path = env['PATH']
            (bin_dir / 'claude').unlink()
            env['PATH'] = os.pathsep.join(d for d in full_path.split(os.pathsep)
                                          if d and not (Path(d) / 'claude').exists())
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn("MISSING: the second CLI 'claude'", red.stdout)
            env['PATH'] = full_path
            (bin_dir / 'claude').write_text('#!/bin/sh\nexit 0\n')
            (bin_dir / 'claude').chmod(0o755)

            # Codex installed only in ~/.local/bin, off PATH: review.sh falls back to it, so
            # doctor must find it the same way.
            review = project / 'scripts/review.sh'
            review_before = review.read_text()
            review.write_text(review_before.replace('DEFAULT_REVIEWER="claude"', 'DEFAULT_REVIEWER="codex"'))
            (bin_dir / 'codex').rename(tmp / 'codex')
            env['PATH'] = os.pathsep.join(d for d in full_path.split(os.pathsep)
                                          if d and not (Path(d) / 'codex').exists())
            red = doctor()
            self.assertIn("MISSING: the second CLI 'codex'", red.stdout)
            (home / '.local/bin').mkdir(parents=True)
            (tmp / 'codex').rename(home / '.local/bin/codex')
            ready = doctor()
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            env['PATH'] = full_path
            review.write_text(review_before)

            # check.sh's own example form: "$HOME/..." must be expanded, as check.sh's sh does.
            (home / 'tc').mkdir()
            (home / 'tc' / 'node').write_text('#!/bin/sh\necho v97.1.0\n')
            (home / 'tc' / 'node').chmod(0o755)
            check = project / 'scripts/check.sh'
            check.write_text(check.read_text().replace(
                'toolchain_path="{{TOOLCHAIN_PATH_SETUP}}"', 'toolchain_path="$HOME/tc"'))
            (project / '.nvmrc').write_text('97\n')
            ready = doctor()
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            self.assertIn('DOCTOR: ready', ready.stdout)

            (project / '.nvmrc').write_text('v96.0.0\n')
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: a git hook resolves node v97.1.0, .nvmrc wants 96', red.stdout)
            (project / '.nvmrc').unlink()

            # doctor reads the line, it does not run it: shell syntax is reported, not executed.
            canary = tmp / 'canary'
            check.write_text(check.read_text().replace(
                'toolchain_path="$HOME/tc"', 'toolchain_path="$(touch %s; printf /usr/bin)"' % canary))
            red = doctor()
            self.assertFalse(canary.exists(), 'doctor.sh executed the toolchain_path line')
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: toolchain_path uses shell syntax doctor does not evaluate; set a plain path',
                          red.stdout)
