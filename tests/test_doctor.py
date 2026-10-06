"""doctor.sh must go red on a machine trap and stay green on a ready synthetic machine."""
import ast
import importlib.util
import os
from pathlib import Path
import re
import select
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_kit', ROOT / 'scripts/check_kit.py')
check_kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_kit)


def review_runtime():
    """The modules scripts/review.sh runs: review_dispatch.py and what it imports, transitively."""
    scripts, todo, found = ROOT / 'core/scripts', ['review_dispatch'], set()
    while todo:
        name = todo.pop()
        if name in found or not (scripts / (name + '.py')).is_file():
            continue
        found.add(name)
        for node in ast.walk(ast.parse((scripts / (name + '.py')).read_text())):
            if isinstance(node, ast.Import):
                todo += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                todo.append(node.module)
    return {name + '.py' for name in found}


def alive(pid):
    # ps, not kill -0: a killed child not yet reaped is a zombie, and kill -0 still finds it.
    state = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True)
    return state.returncode == 0 and not state.stdout.strip().startswith('Z')


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
            # A controlled timeout, so the grep probe runs whether or not this host has one.
            # It enforces its seconds and kills only the command it ran: a stand-in that only
            # ran the command proved no bound at all, and one that cleaned up the command's
            # process group hid that doctor did not (a child the rc file left running).
            (bin_dir / 'timeout').write_text(
                '#!/usr/bin/env python3\n'
                'import subprocess, sys\n'
                'args = sys.argv[1:]\n'
                'while args[0].startswith("-"):\n'
                '    args = args[2:] if args[0] == "-k" else args[1:]\n'
                'child = subprocess.Popen(args[1:])\n'
                'try:\n'
                '    sys.exit(child.wait(timeout=float(args[0])))\n'
                'except subprocess.TimeoutExpired:\n'
                '    child.kill()\n'
                '    child.wait()\n'
                '    sys.exit(124)\n')
            (bin_dir / 'timeout').chmod(0o755)
            shell = bin_dir / 'fake-shell'
            # The common colour alias is harmless and must stay green.
            shell.write_text('#!/bin/sh\ncommand() { echo "grep is an alias for grep --color=auto"; }\neval "$2"\n')
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
            self.assertEqual(ready.stderr, '')

            # A hooks path of the project's own is not wired: the hook belongs beside the kit's.
            git('config', 'core.hooksPath', '.husky')
            unwired = doctor()
            self.assertNotEqual(unwired.returncode, 0)
            self.assertIn('.githooks/<name>.project', unwired.stdout)
            git('config', 'core.hooksPath', '.githooks')

    def test_the_required_review_files_match_what_review_sh_runs(self):
        # doctor.sh is copied into projects, where neither the packaging list nor the kit's
        # sources exist, so its list is kept by hand; this keeps it equal to the modules
        # review.sh imports and to the runtime the plugin packages.
        doctor = (ROOT / 'core/scripts/doctor.sh').read_text()
        listed = re.search(r'^for f in (scripts/check\.sh[^;]*);', doctor, re.M).group(1).split()
        listed = {f[len('scripts/'):] for f in listed if f.endswith('.py')}
        packaged = next(
            {element.value for element in node.elts}
            for node in ast.walk(ast.parse((ROOT / 'scripts/package_codex_plugin.py').read_text()))
            if isinstance(node, ast.List) and node.elts
            and all(isinstance(e, ast.Constant) and str(e.value).endswith('.py') for e in node.elts))
        self.assertEqual(listed, review_runtime())
        self.assertEqual(packaged, review_runtime())
