"""doctor.sh must go red on a machine trap and stay green on a ready synthetic machine."""
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


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
            # A fresh directory of links to the resolved executables: a dangling link or a
            # repeated PATH entry on the host must not break the fixture.
            dangling = tmp / 'dangling-bin'
            dangling.mkdir()
            (dangling / 'tmux').symlink_to(tmp / 'absent')

            def path_without(tool):
                links = tmp / ('no-%s-bin' % tool)
                links.mkdir()
                for directory in [str(dangling), *env['PATH'].split(os.pathsep) * 2]:
                    if os.path.isdir(directory):
                        for name in os.listdir(directory):
                            source = Path(directory) / name
                            if name != tool and source.exists() and not os.path.lexists(links / name):
                                (links / name).symlink_to(source.resolve())
                return str(links)
            no_timeout = path_without('timeout')
            shell.write_text('#!/bin/sh\nsleep 60\n')
            try:
                skipped = subprocess.run(['sh', 'scripts/doctor.sh'], cwd=project, capture_output=True,
                                         text=True, env=dict(env, PATH=no_timeout), timeout=20)
            except subprocess.TimeoutExpired:
                self.fail('doctor.sh ran the shell probe without a time limit')
            self.assertEqual(skipped.returncode, 0, skipped.stdout + skipped.stderr)
            self.assertIn('NOTE: grep probe skipped, no timeout on this machine', skipped.stdout)

            # An rc file that leaves a child holding the probe's output, and a probe that
            # fails: doctor returns within its bound and says the probe did not complete. The
            # child is gone when doctor exits: `timeout` ends when its own child does, so a
            # child started in the background outlived the probe until doctor killed its group.
            # Without setsid (stock macOS) that child is documented to survive, with a NOTE;
            # either way the fixture kills what is left itself.
            pid_file = tmp / 'sleep.pid'

            def reap():
                if pid_file.exists():
                    try:
                        os.kill(int(pid_file.read_text()), signal.SIGKILL)
                    except (ProcessLookupError, ValueError):
                        pass
                    pid_file.unlink()

            no_setsid_path = path_without('setsid')
            for fixture_path in (env['PATH'], no_setsid_path):
                group_kill = shutil.which('setsid', path=fixture_path) is not None
                for rc_file in ('sleep 60 &\necho $! > %s\n' % pid_file, 'exit 3\n'):
                    shell.write_text('#!/bin/sh\n' + rc_file)
                    with self.subTest(setsid=group_kill, rc_file=rc_file):
                        try:
                            probed = subprocess.run(['sh', 'scripts/doctor.sh'], cwd=project,
                                                    env=dict(env, PATH=fixture_path),
                                                    capture_output=True, text=True, timeout=20)
                            if pid_file.exists() and group_kill:
                                self.assertFalse(alive(int(pid_file.read_text())),
                                                 'a child the rc file started outlived doctor.sh')
                        except subprocess.TimeoutExpired:
                            self.fail('a child of the shell probe held doctor.sh past its bound')
                        finally:
                            reap()
                        self.assertEqual(probed.returncode, 0, probed.stdout + probed.stderr)
                        self.assertIn('NOTE: grep probe did not complete', probed.stdout)
                        if not group_kill:
                            self.assertIn('NOTE: no setsid on this machine', probed.stdout)

            # An rc file blocked in the foreground: doctor returns within the probe's bound,
            # and the blocked command is gone by then (where setsid exists), not left for this
            # test to kill. It holds a FIFO open, so end-of-file there means no process still
            # runs it. The shell waits on it rather than running it directly, so its pid is
            # known to reap().
            fifo = tmp / 'rc-alive'
            os.mkfifo(fifo)
            reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
            self.addCleanup(os.close, reader)
            shell.write_text('#!/bin/sh\nexec 3>%s\necho started >&3\nsleep 60 &\necho $! > %s\nwait\n'
                             % (fifo, pid_file))
            started = time.monotonic()
            try:
                try:
                    probed = subprocess.run(['sh', 'scripts/doctor.sh'], cwd=project, env=env,
                                            capture_output=True, text=True, timeout=30)
                except subprocess.TimeoutExpired:
                    self.fail('a foreground-blocked rc file held doctor.sh past its bound')
                self.assertLess(time.monotonic() - started, 15, 'the probe bound is 5 s plus 1 s to kill')
                self.assertIn('NOTE: grep probe did not complete', probed.stdout)
                self.assertEqual(os.read(reader, 64), b'started\n')
                if shutil.which('setsid', path=env['PATH']):
                    gone = select.select([reader], [], [], 5)[0] and os.read(reader, 64) == b''
                    self.assertTrue(gone, 'the blocked rc command outlived the probe')
                else:
                    self.assertIn('NOTE: no setsid on this machine', probed.stdout)
            finally:
                reap()

            # Without setsid the probe has no process group of its own to clean up, so a
            # child the rc file left running is not stopped: doctor says so.
            shell.write_text('#!/bin/sh\necho "grep is an alias for grep --color=auto"\n')
            no_setsid = subprocess.run(['sh', 'scripts/doctor.sh'], cwd=project, capture_output=True,
                                       text=True, env=dict(env, PATH=no_setsid_path), timeout=20)
            self.assertEqual(no_setsid.returncode, 0, no_setsid.stdout + no_setsid.stderr)
            self.assertIn('NOTE: no setsid on this machine', no_setsid.stdout)

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

            # An explicit executable, as the wrapper and adapters take it: REVIEW_REVIEWER
            # picks the reviewer, REVIEW_CLI_BIN or CLAUDE_CLI_BIN names its binary off PATH.
            (bin_dir / 'claude').unlink()
            stub = tmp / 'stub-cli'
            (home / '.local/bin/codex').rename(stub)
            env['PATH'] = os.pathsep.join(d for d in full_path.split(os.pathsep) if d and not
                                          ((Path(d) / 'claude').exists() or (Path(d) / 'codex').exists()))
            for extra, missing in (({'REVIEW_REVIEWER': 'codex', 'REVIEW_CLI_BIN': str(stub)}, None),
                                   ({'CLAUDE_CLI_BIN': str(stub)}, None),
                                   ({'REVIEW_REVIEWER': 'codex', 'REVIEW_CLI_BIN': str(tmp / 'absent')},
                                    "MISSING: the second CLI '%s'" % (tmp / 'absent'))):
                with self.subTest(extra=extra):
                    result = subprocess.run(['sh', 'scripts/doctor.sh'], cwd=project, text=True,
                                            capture_output=True, env=dict(env, **extra))
                    if missing:
                        self.assertEqual(result.returncode, 1, result.stdout)
                        self.assertIn(missing, result.stdout)
                    else:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
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

            # An unset variable is a missing configuration, as check.sh's `set -u` stops on it;
            # an explicitly empty one is the owner's choice of no toolchain directory.
            check.write_text(check.read_text().replace(
                'toolchain_path="$(touch %s; printf /usr/bin)"' % canary,
                'toolchain_path="${DOCTOR_TEST_TOOLCHAIN}/bin"'))
            env.pop('DOCTOR_TEST_TOOLCHAIN', None)
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: toolchain_path refers to $DOCTOR_TEST_TOOLCHAIN, which is not set',
                          red.stdout)
            self.assertEqual(red.stdout.count('MISSING:'), 1, red.stdout)
            ready = subprocess.run(['sh', 'scripts/doctor.sh'], cwd=project, capture_output=True,
                                   text=True, env=dict(env, DOCTOR_TEST_TOOLCHAIN=''))
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            check.write_text(check.read_text().replace(
                'toolchain_path="${DOCTOR_TEST_TOOLCHAIN}/bin"', 'toolchain_path="{{TOOLCHAIN_PATH_SETUP}}"'))

            # A line doctor cannot read is not an empty one: `toolchain_path="..." # note` was
            # read as no toolchain, and doctor probed a PATH the gate never uses.
            line = 'toolchain_path="{{TOOLCHAIN_PATH_SETUP}}"'
            for form in ('toolchain_path="%s/tc" # build tools' % home,
                         "toolchain_path='%s/tc'" % home, 'toolchain_path=%s/tc' % home,
                         '  toolchain_path="%s/tc"' % home):
                with self.subTest(form=form):
                    check.write_text(check.read_text().replace(line, form))
                    red = doctor()
                    self.assertEqual(red.returncode, 1, red.stdout)
                    self.assertIn('MISSING: toolchain_path line not in the supported form '
                                  'toolchain_path="..."; doctor cannot see the gate\'s PATH', red.stdout)
                    self.assertEqual(red.stdout.count('MISSING:'), 1, red.stdout)
                    check.write_text(check.read_text().replace(form, line))
            # Explicitly empty is the owner's choice; no line at all is said, not a fault.
            check.write_text(check.read_text().replace(line, 'toolchain_path=""'))
            ready = doctor()
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            self.assertNotIn('toolchain_path', ready.stdout)
            check.write_text(check.read_text().replace('toolchain_path=""\n', ''))
            ready = doctor()
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            self.assertIn('NOTE: scripts/check.sh has no toolchain_path line', ready.stdout)
            check.write_text(check.read_text().replace('case "$toolchain_path" in', line + '\ncase "$toolchain_path" in', 1))
            self.assertIn(line, check.read_text())

            # The review entry point: a deleted review.sh, or one whose reviewer doctor cannot
            # read, skipped the reviewer check and reported a machine ready without it.
            review.unlink()
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: scripts/review.sh does not exist', red.stdout)
            self.assertEqual(red.stdout.count('MISSING:'), 1, red.stdout)
            for broken in (review_before.replace('DEFAULT_REVIEWER="claude"\n', ''),
                           review_before.replace('DEFAULT_REVIEWER="claude"', 'DEFAULT_REVIEWER=claude')):
                review.write_text(broken)
                review.chmod(0o755)
                red = doctor()
                self.assertEqual(red.returncode, 1, red.stdout)
                self.assertIn('MISSING: scripts/review.sh names no reviewer doctor can read', red.stdout)
                self.assertEqual(red.stdout.count('MISSING:'), 1, red.stdout)
            review.write_text(review_before)

            # A required hook that does not exist: the loop below skipped what was not there,
            # and the wiring check reads only core.hooksPath, so ordinary commits went ungated.
            pre_commit = project / '.githooks/pre-commit'
            pre_commit_bytes = pre_commit.read_bytes()
            pre_commit.unlink()
            red = doctor()
            self.assertEqual(red.returncode, 1, red.stdout)
            self.assertIn('MISSING: .githooks/pre-commit does not exist', red.stdout)
            self.assertEqual(red.stdout.count('MISSING:'), 1, red.stdout)
            pre_commit.write_bytes(pre_commit_bytes)
            pre_commit.chmod(0o755)

            # Node as the gate resolves it: a hook inherits its caller's PATH (check.sh adds
            # only toolchain_path in front). The probe once used a login-less PATH instead and
            # read a system Node the gate never ran, in both directions. A fake getconf gives
            # that login-less probe a system directory this test controls.
            (project / '.nvmrc').write_text('22\n')
            system, inherited, conf = tmp / 'system-bin', tmp / 'inherited-bin', tmp / 'conf-bin'
            for directory in (system, inherited, conf):
                directory.mkdir()
            (conf / 'getconf').write_text('#!/bin/sh\necho %s:/usr/bin:/bin\n' % system)
            for system_node, inherited_node, expect in (('v22.1.0', 'v18.2.0', 'MISSING'),
                                                        ('v18.2.0', 'v22.1.0', 'ready')):
                with self.subTest(system=system_node, inherited=inherited_node):
                    for directory, version in ((system, system_node), (inherited, inherited_node)):
                        (directory / 'node').write_text('#!/bin/sh\necho %s\n' % version)
                    for tool in (conf / 'getconf', system / 'node', inherited / 'node'):
                        tool.chmod(0o755)
                    result = subprocess.run(['sh', 'scripts/doctor.sh'], cwd=project, capture_output=True,
                                            text=True, env=dict(env, PATH=os.pathsep.join(
                                                (str(inherited), str(conf), env['PATH']))))
                    if expect == 'MISSING':
                        self.assertEqual(result.returncode, 1, result.stdout)
                        self.assertIn('MISSING: a git hook resolves node v18.2.0, .nvmrc wants 22',
                                      result.stdout)
                        self.assertEqual(result.stdout.count('MISSING:'), 1, result.stdout)
                    else:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('NOTE: a hook started from a login-less shell would see node %s'
                                  % system_node, result.stdout)
            (project / '.nvmrc').unlink()
