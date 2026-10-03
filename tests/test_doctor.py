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

            shell.write_text('#!/bin/sh\necho "grep is an alias for ugrep"\n')
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: grep is shadowed', red.stdout)
            self.assertEqual(red.stdout.count('MISSING:'), 1, red.stdout)
            shell.write_text('#!/bin/sh\necho "grep is an alias for grep --color=auto"\n')

            git('config', '--unset', 'core.hooksPath')
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: the commit gate is not wired (core.hooksPath)', red.stdout)
            git('config', 'core.hooksPath', '.githooks')

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
