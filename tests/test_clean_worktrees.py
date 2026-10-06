"""scripts/clean_worktrees.sh removes a finished worktree only when nothing in it can be lost.

Each check that keeps a worktree has a case here that builds the state it must catch, in a
throwaway repository; tmux is a stub on PATH, so a live session on the machine running the
tests changes nothing. A kept worktree must still be there, and the report must name the
reason; no branch is ever deleted. The script's clock is set two hours ahead
(CLEAN_WORKTREES_NOW), so the quiet period holds unless a case is about it: a ctime cannot be
set back, so the clock moves instead of the files.
"""
import ast
import fcntl
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unicodedata
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'overlays/claude-code/files/scripts'
SCRIPT = SCRIPTS / 'clean_worktrees.sh'
HOOK = ROOT / 'core/.githooks/post-merge'
sys.path.insert(0, str(SCRIPTS))
import clean_worktrees  # noqa: E402

# Without /proc (macOS) the script asks lsof; most cases pass --assume-idle there so that they
# test their own clause. The cases about liveness run the real listing on every host.
PROC = os.path.exists('/proc/self/cwd')

TMUX = '''#!/bin/sh
if [ -n "${TMUX_STUB_FAIL:-}" ]; then echo "$TMUX_STUB_FAIL" >&2; exit 1; fi
if [ -f "$TMUX_STUB" ]; then cat "$TMUX_STUB"; exit 0; fi
echo "no server running on /tmp/tmux-stub/default" >&2
exit 1
'''
# Wraps the real git: prints what this git never does, or fails one subcommand. The script
# must keep, not guess.
SHIM = '''#!%s
import os, shutil, subprocess, sys
args, mode = sys.argv[1:], os.environ.get('SHIM', '')
if mode.startswith('fail:') and mode[5:] in args:
    sys.stderr.write('fatal: refused by the shim\\n')
    sys.exit(128)
if mode == 'format' and '--show-object-format' in args:
    sys.stdout.write('sha3\\n')
    sys.exit(0)
if mode == 'version' and args == ['--version']:
    sys.stdout.write('git version 2.35.8\\n')
    sys.exit(0)
if mode == 'halfremove' and args[:2] == ['worktree', 'remove']:
    # What git does when it cannot delete a file: some files gone, its git directory gone anyway.
    gitdir = subprocess.run([os.environ['REAL_GIT'], 'rev-parse', '--absolute-git-dir'], cwd=args[-1],
                            stdout=subprocess.PIPE).stdout.strip()
    os.unlink(os.path.join(args[-1], 'done.txt'))
    shutil.rmtree(gitdir)
    sys.stderr.write('error: failed to delete a file of the shim\\n')
    sys.exit(1)
if mode == 'reftable' and 'extensions.refStorage' in args:
    sys.stdout.write('reftable\\n')
    sys.exit(0)
if not (mode == 'status' and 'status' in args or mode in ('list', 'branch') and 'list' in args):
    os.execv(os.environ['REAL_GIT'], ['git'] + args)  # a stream such as `cat-file --batch` passes through
result = subprocess.run([os.environ['REAL_GIT']] + args, stdout=subprocess.PIPE)
out = result.stdout
if mode == 'status' and 'status' in args:
    out += b'Z something new\\0'
if mode == 'list' and 'list' in args:
    out = out.replace(b'\\0\\0', b'\\0frobbed\\0\\0')
if mode == 'branch' and 'list' in args:
    out = out.replace(b'branch refs/heads/worktree-done\\0', b'branch refs/heads/worktree-\\xff\\0')
sys.stdout.buffer.write(out)
sys.exit(result.returncode)
''' % sys.executable
# Patches for the script run in a Python of its own (CleanWorktreesTests.driver), which sees the
# case's strings as `values`. An error injected where permissions cannot make one, as root ignores
# them: a deletion refused, a file that cannot be read (in a path holding values[0]).
FAIL_UNLINK = ('real_unlink = os.unlink\n'
               'def unlink(path, *a, **k):\n'
               '    if os.fsencode(values[0]) in os.fsencode(path):\n'
               '        raise PermissionError(13, "Permission denied", path)\n'
               '    return real_unlink(path, *a, **k)\n'
               'os.unlink = unlink\n')
FAIL_OPEN = ('def failing(path, *a, **k):\n'
             '    if os.fsencode(values[0]) in os.fsencode(path):\n'
             '        raise PermissionError(13, "Permission denied", path)\n'
             '    return open(path, *a, **k)\n'
             'c.open = failing\n')
# A mount without mounting: each path in values on a device of its own.
FOREIGN = ('real_lstat = os.lstat\n'
           'class Other:\n'
           '    def __init__(self, info):\n'
           '        self.info, self.st_dev = info, info.st_dev + 1\n'
           '    def __getattr__(self, name):\n'
           '        return getattr(self.info, name)\n'
           'def lstat(path, *a, **k):\n'
           '    info = real_lstat(path, *a, **k)\n'
           '    return Other(info) if os.fsencode(path) in set(map(os.fsencode, values)) else info\n'
           'os.lstat = lstat\n')

# lsof stubs: $PPID is the script, which runs lsof in its own working directory.
LSOF_ME = 'printf "p%s\\nn%s\\n" "$PPID" "$(pwd -P)"\n'
WARNING = ('echo "lsof: WARNING: can\'t stat() fuse.gvfsd-fuse file system /run/user/1000/gvfs" >&2\n'
           'echo "      Output information may be incomplete." >&2\n')

# `lsof -a -d cwd -F pn` as recorded. Linux lsof 4.98 (no f record; an unreadable cwd is named
# with its error); macOS lsof prints an `fcwd` record after each `p` and omits the processes of
# other users. The macOS sample follows the documented field format; the real listing runs in
# test_a_process_working_inside_is_kept_by_the_real_listing on every CI host.
LSOF_LINUX = (b'p1\nn/proc/1/cwd (readlink: Permission denied)\n'
              b'p4242\nn/home/u/project/.claude/worktrees/w/src\n'
              b'p4243\nn/home/u/project\n'
              b'p77\nn/proc/77/cwd (stat: Permission denied)\n')
LSOF_MACOS = (b'p1\nfcwd\nn/\n'
              b'p501\nfcwd\nn/Users/u/project/.claude/worktrees/w\n'
              b'p502\nfcwd\n'
              b'p503\nfcwd\nn/private/var/folders/x/project\n')


class CleanWorktreesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.stubs = self.tmp / 'bin'
        self.stubs.mkdir()
        self.stub('tmux', TMUX)
        self.now = time.time() + 7200
        self.env = dict(os.environ, PATH=str(self.stubs) + os.pathsep + os.environ['PATH'],
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', LC_ALL='C',
                        GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid',
                        TMUX_STUB=str(self.tmp / 'sessions'), CLEAN_WORKTREES_NOW=str(self.now),
                        # No detached auto-maintenance changing .git under a running case.
                        GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='gc.auto', GIT_CONFIG_VALUE_0='0',
                        GIT_CONFIG_KEY_1='maintenance.auto', GIT_CONFIG_VALUE_1='false')
        for name in ('KIT_NO_WORKTREE_CLEANUP', 'CLEAN_WORKTREES_PROC', 'CLEAN_WORKTREES_MOUNTINFO', 'TMUX_STUB_FAIL', 'GIT_DIR',
                     'GIT_WORK_TREE', 'GIT_INDEX_FILE'):
            self.env.pop(name, None)
        self.main = self.tmp / 'main'
        self.main.mkdir()
        self.git('init', '-q')
        self.git('checkout', '-q', '-b', 'main')
        (self.main / '.gitignore').write_text('build/\n*.log\n/.claude/worktrees/\n')
        (self.main / 'a').write_text('a\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'base')

    def stub(self, name, text):
        (self.stubs / name).write_text(text)
        (self.stubs / name).chmod(0o755)

    def git(self, *args, cwd=None, check=True, **extra):
        result = subprocess.run(['git', *args], cwd=cwd or self.main, env=dict(self.env, **extra),
                                capture_output=True)
        if check and result.returncode != 0:
            self.fail('git %s: %s' % (args, result.stderr.decode(errors='replace')))
        return result.stdout.decode(errors='replace').strip()

    def worktree(self, name, merge=True, commit=True, branch=None):
        """A worker's worktree as spawn_worker.sh makes it, with one commit, merged into main."""
        path = self.main / '.claude/worktrees' / name
        branch = branch or 'worktree-' + name
        self.git('worktree', 'add', '-q', str(path), '-b', branch)
        if commit:
            (path / (name + '.txt')).write_text(name + '\n')
            self.git('add', name + '.txt', cwd=path)
            self.git('commit', '-q', '-m', 'work in ' + name, cwd=path)
        if merge:
            self.git('merge', '-q', '--no-edit', branch, KIT_NO_WORKTREE_CLEANUP='1')
        return path

    def recent(self, path):
        """PATH changed a minute before the script's clock."""
        os.utime(path, (self.now - 60,) * 2, follow_symlinks=False)

    def run_script(self, *args, cwd=None, idle=not PROC, proc=None, code=0, **extra):
        if idle:
            args += ('--assume-idle',)
        command = ['sh', str(SCRIPT), *args]
        if proc:
            # A /proc the case builds, holding the script's own process: `exec` keeps the pid
            # through sh and python3.
            extra['CLEAN_WORKTREES_PROC'] = str(proc)
            command = ['sh', '-c', 'mkdir -p "$0/$$" && ln -s "$(pwd -P)" "$0/$$/cwd" && exec "$@"', str(proc)] + command
        result = subprocess.run(command, cwd=cwd or self.main, env=dict(self.env, **extra), capture_output=True)
        out = result.stdout.decode() + result.stderr.decode()
        self.assertEqual(result.returncode, code, out)
        return out

    def merge_with_hook(self, branch, *flags, cwd=None, **extra):
        merge = subprocess.run(['git', 'merge', *(flags or ('--no-ff',)), '-m', 'merge', branch],
                               cwd=cwd or self.main, env=dict(self.env, **extra), capture_output=True, text=True)
        self.assertEqual(merge.returncode, 0, merge.stderr)
        # The test clock's notice, said on every run of the script, is not the hook's output.
        return re.sub(r'clean_worktrees: CLEAN_WORKTREES_NOW is set[^\n]*\n', '', merge.stdout + merge.stderr, count=1)

    def branch(self, name):
        return self.git('branch', '--list', 'worktree-' + name)

    def assertKept(self, path, out, *reasons):
        self.assertTrue(path.is_dir(), 'removed although it had to be kept:\n' + out)
        self.assertIn('keep   .claude/worktrees/' + path.name, out)
        for reason in reasons:
            self.assertIn(reason, out)

    def assertRemoved(self, path, out):
        self.assertFalse(path.exists(), 'kept although it was finished:\n' + out)
        self.assertIn('remove .claude/worktrees/' + path.name, out)

    def disposable(self, text):
        (self.main / '.claude').mkdir(exist_ok=True)
        (self.main / '.claude/worktree-disposable').write_text(text)

    def gitdir(self, path):
        return Path(self.git('rev-parse', '--absolute-git-dir', cwd=path))

    def loose(self, path):
        """A commit on top of PATH's HEAD that no branch holds."""
        return self.git('commit-tree', self.git('rev-parse', 'HEAD^{tree}', cwd=path), '-p', 'HEAD',
                        '-m', 'only here', cwd=path)

    def restore(self, out):
        lines = out.split('\n')
        return lines[lines.index('         this command, run in the main worktree, brings the worktree back:') + 1]

    def driver(self, patch, *values):
        """The command that runs the script (--apply --assume-idle) after PATCH, Python that sees
        VALUES as `values` and the script's module as `c`."""
        return [sys.executable, '-c', 'import os, sys\nsys.path.insert(0, sys.argv[1])\nimport clean_worktrees as c\n'
                'values = sys.argv[2:]\n' + patch + 'sys.argv = ["clean_worktrees", "--apply", "--assume-idle"]\n'
                'sys.exit(c.main())\n', str(SCRIPTS), *values]

    def drive(self, patch, *values, code=0):
        result = subprocess.run(self.driver(patch, *values), cwd=self.main, env=self.env, capture_output=True, text=True)
        out = result.stdout + result.stderr
        self.assertEqual(result.returncode, code, out)
        return out

    def failures(self):
        """How a case makes a step fail: by permissions, which root ignores, and injected, for
        any user."""
        return ('injected',) if os.geteuid() == 0 else ('permissions', 'injected')

    def fail_deletion(self, how, folder, code=0):
        """The script with every deletion in FOLDER refused."""
        if how == 'injected':
            return self.drive(FAIL_UNLINK, '/%s/' % folder.name, code=code)
        folder.chmod(0o555)
        try:
            return self.run_script('--apply', code=code)
        finally:
            if folder.exists():
                folder.chmod(0o755)

    def mountinfo(self, *paths):
        """A mount table that lists PATHS (bytes) after the root, escaped as Linux writes them."""
        table = self.tmp / 'mountinfo'
        lines = [b'1 0 8:1 / / rw - ext4 /dev/root rw']
        for n, path in enumerate(paths, 2):
            path = re.sub(rb'[ \t\n\\]', lambda m: b'\\%03o' % m.group()[0], path)
            lines.append(b'%d 1 0:%d / %s rw - tmpfs none rw' % (n, n, path))
        table.write_bytes(b'\n'.join(lines) + b'\n')
        return str(table)

    def in_namespace(self, mount, *args):
        """The script (--apply --assume-idle) after the shell command MOUNT ($1, $2...: ARGS) in a
        mount namespace of its own; None, with one line said, where this host lets no user make
        one: the cases that inject the device or the mount table are the ones that run everywhere."""
        if subprocess.run(['unshare', '-rm', 'true'], capture_output=True).returncode if shutil.which('unshare') else 1:
            sys.stderr.write('\n[mount namespace] not run: no unprivileged mount namespace here\n')
            return None
        ran = subprocess.run(['unshare', '-rm', 'sh', '-c', mount + ' && exec sh "$0" --apply --assume-idle', str(SCRIPT),
                              *map(str, args)], cwd=self.main, env=self.env, capture_output=True, text=True)
        out = ran.stdout + ran.stderr
        self.assertEqual(ran.returncode, 0, out)
        return out

    # --- removal, the log, the dry run, no branch deleted ------------------------------------

    def test_a_merged_clean_worktree_is_removed_logged_and_its_branch_kept(self):
        path = self.worktree('done')
        tip = self.git('rev-parse', 'worktree-done')
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertEqual(self.git('rev-parse', 'worktree-done'), tip, out)
        self.assertEqual(self.restore(out), "           git worktree add '%s' 'worktree-done'" % os.path.realpath(path))
        self.assertIn('clean_worktrees: removed 1, kept 1', out)
        self.assertTrue(out.rstrip('\n').endswith(
            'clean_worktrees: branches kept, their worktrees removed: worktree-done\n'
            'clean_worktrees: to delete merged branches yourself: `git branch --merged \'main\'` lists them, '
            '`git branch -d <name>` deletes one, and its reflog with it: the old tips a removal saved are kept by '
            'the refs under refs/kit/saved/'), out)
        lines = (self.main / '.git/kit-worktree-removals.log').read_text().split('\n')
        self.assertEqual(lines[0] + '\n', clean_worktrees.LOG_HEADER)
        self.assertTrue(lines[0].endswith('; in every name ' + clean_worktrees.ESCAPING))
        record = lines[1].split('\t')
        self.assertEqual(lines[3:], [''])
        self.assertEqual(record[2:7], ['intent', os.path.realpath(path), 'refs/heads/worktree-done', tip,
                                       self.git('rev-parse', 'HEAD')])
        self.assertTrue(record[0].endswith('Z'))
        # Both lines carry the run's id, which pairs them: its UTC time and its process id.
        self.assertRegex(record[1], r'^run=\d{8}T\d{6}Z-\d+$')
        self.assertEqual(lines[2].split('\t')[1:], [record[1], 'outcome', os.path.realpath(path), 'removed'])

    def test_the_restore_line_is_one_shell_safe_command_that_brings_the_worktree_back(self):
        for name, branch in (('semi', 'worktree-a;id;#'), ("it's", "worktree-it's")):
            with self.subTest(branch=branch):
                path = self.worktree(name, branch=branch)
                out = self.run_script('--apply')
                self.assertRemoved(path, out)
                command = self.restore(out).strip()
                ran = subprocess.run(['sh', '-c', command], cwd=self.main, env=self.env, capture_output=True, text=True)
                self.assertEqual(ran.returncode, 0, ran.stderr)
                self.assertNotIn('uid=', ran.stdout + ran.stderr)
                self.assertEqual(self.git('symbolic-ref', 'HEAD', cwd=path), 'refs/heads/' + branch)
                self.assertTrue((path / (name + '.txt')).is_file())

    def test_the_branch_listing_command_is_shell_safe(self):
        self.git('branch', '-m', 'main;id')
        path = self.worktree('done')
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        command = re.search(r'`(git branch --merged [^`]*)` lists them', out).group(1)
        self.assertEqual(command, "git branch --merged 'main;id'")
        ran = subprocess.run(['sh', '-c', command], cwd=self.main, env=self.env, capture_output=True, text=True)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertNotIn('uid=', ran.stdout + ran.stderr)
        self.assertIn('worktree-done', ran.stdout)

    def test_a_dry_run_removes_nothing_and_prints_the_apply_command(self):
        path = self.worktree('done')
        out = self.run_script()
        self.assertTrue(path.is_dir())
        self.assertIn('remove .claude/worktrees/done', out)
        self.assertIn('to apply: scripts/clean_worktrees.sh --apply', out)
        self.assertFalse((self.main / '.git/kit-worktree-removals.log').exists())

    def test_only_audits_and_removes_the_one_named_worktree(self):
        # close_worker.sh closes one worker: the audit is the same, the others are not looked at.
        one, other = self.worktree('one'), self.worktree('other')
        out = self.run_script('--only=one')
        self.assertIn('remove .claude/worktrees/one', out)
        self.assertNotIn('worktrees/other', out)
        self.assertIn("to apply: scripts/clean_worktrees.sh --apply --only='one'", out)
        out = self.run_script('--apply', '--only=one')
        self.assertRemoved(one, out)
        self.assertTrue(other.is_dir(), out)
        self.assertNotIn('worktrees/other', out)
        self.assertIn('clean_worktrees: removed 1, kept 0', out)
        self.git('rev-parse', '--verify', 'worktree-one')
        (other / 'dirty.txt').write_text('not committed\n')
        out = self.run_script('--apply', '--only=other')
        self.assertKept(other, out, 'dirty.txt')
        out = self.run_script('--apply', '--only=gone')
        self.assertIn('clean_worktrees: no worktree at .claude/worktrees/gone\n', out)
        self.assertIn('clean_worktrees: removed 0, kept 0', out)
        for bad in ('', '.', '..', '../main', 'a/b'):
            with self.subTest(name=bad):
                out = self.run_script('--apply', '--only=' + bad, code=2)
                self.assertIn('--only takes the name of one folder under .claude/worktrees', out)
        self.assertTrue(other.is_dir())

    def test_no_quiet_lifts_the_quiet_period_for_the_one_named_worktree_and_nothing_else(self):
        # close_worker.sh: the lead has just ended the session and decided the work is finished.
        out = self.run_script('--apply', '--no-quiet', code=2)
        self.assertIn('--no-quiet is accepted only with --only', out)
        fresh, other = self.worktree('fresh'), self.worktree('other')
        self.recent(fresh / 'fresh.txt')
        self.recent(other / 'other.txt')
        out = self.run_script('--only=fresh')
        self.assertKept(fresh, out, 'quiet period: a file in it changed 1 min ago')
        out = self.run_script('--only=fresh', '--no-quiet')
        self.assertIn("to apply: scripts/clean_worktrees.sh --apply --only='fresh' --no-quiet", out)
        out = self.run_script('--apply', '--only=fresh', '--no-quiet')
        self.assertIn('clean_worktrees: --no-quiet: the quiet period is not applied to .claude/worktrees/fresh\n', out)
        self.assertRemoved(fresh, out)
        self.assertTrue(other.is_dir())
        # Every other proof stands: an uncommitted file, a process working inside.
        (other / 'notes.txt').write_text('uncommitted\n')
        out = self.run_script('--apply', '--only=other', '--no-quiet')
        self.assertKept(other, out, 'notes.txt')
        (other / 'notes.txt').unlink()
        busy = subprocess.Popen(['sleep', '30'], cwd=other)
        self.addCleanup(busy.wait)
        self.addCleanup(busy.kill)
        out = self.run_script('--apply', '--only=other', '--no-quiet', idle=False)
        self.assertKept(other, out, 'in use: process %d works inside it' % busy.pid)

    def test_the_log_record_is_written_before_anything_is_deleted_and_a_rerun_finishes(self):
        (self.main / 'sub').mkdir()
        (self.main / 'sub/report.md').write_text('archived\n')
        log = self.main / '.git/kit-worktree-removals.log'
        for how in self.failures():
            with self.subTest(how=how):
                log.unlink(missing_ok=True)
                path = self.worktree('done-' + how)
                (path / 'sub').mkdir()
                (path / 'sub/report.md').write_text('archived\n')
                out = self.fail_deletion(how, path / 'sub')
                self.assertIn('stopped: cannot delete the identical copy sub/report.md', out)
                self.assertNotIn('git refused', out)
                self.assertTrue((path / 'sub/report.md').is_file(), out)
                self.assertEqual(log.read_text().count('\tintent\t'), 1, 'no record before the first deletion')
                self.assertTrue(log.read_text().endswith('\tkept\tcannot delete the identical copy sub/report.md '
                                                         '([Errno 13] Permission denied: %r)\n'
                                                         % os.path.join(os.fsencode(os.path.realpath(path)), b'sub/report.md')),
                                log.read_text())
                # The state an interrupt after the record leaves: the re-run removes it, logged again.
                out = self.run_script('--apply')
                self.assertRemoved(path, out)
                self.assertEqual(log.read_text().count('\n'), 5)
                self.assertEqual(log.read_text().count(clean_worktrees.LOG_HEADER), 1)

    def test_a_failure_after_a_deletion_says_what_was_deleted_and_fails(self):
        (self.main / 'sub').mkdir()
        (self.main / 'sub/report.md').write_text('archived\n')
        (self.main / 'report.md').write_text('top\n')
        for how in self.failures():
            with self.subTest(how=how):
                path = self.worktree('done-' + how)
                (path / 'sub').mkdir()
                (path / 'sub/report.md').write_text('archived\n')
                (path / 'report.md').write_text('top\n')
                out = self.fail_deletion(how, path / 'sub', code=1)
                self.assertIn('stopped: cannot delete the identical copy sub/report.md', out)
                self.assertIn('         PARTLY MODIFIED: 1 files git does not track were deleted from it, each with a '
                              'byte-identical copy at the same path in the main worktree, which brings it back:\n'
                              '           report.md\n', out)
                self.assertIn('clean_worktrees: removed 0, kept 1, PARTLY MODIFIED 1', out)
                self.assertFalse((path / 'report.md').exists())
                self.assertTrue((path / 'sub/report.md').is_file())
                # The record written first names every file about to be deleted.
                log = (self.main / '.git/kit-worktree-removals.log').read_text()
                self.assertIn('\tidentical_files=2\tdisposable_bytes=0\tdelete=report.md\tdelete=sub/report.md\n', log)
                self.assertRegex(log, r'\toutcome\t[^\t]*/%s\tpartly-modified\tcannot delete the identical copy '
                                 r'sub/report\.md [^\t]*\tdeleted=report\.md\n$' % path.name)
                # What is left holds: a re-run removes it.
                self.assertRemoved(path, self.run_script('--apply'))

    def test_a_git_worktree_remove_that_fails_halfway_is_reported_possibly_modified(self):
        # git deletes the folder's files until one fails, then its git directory anyway, and
        # exits non-zero; the shim does that for any user (root deletes from a read-only folder).
        path = self.worktree('done')
        out = self.run_script('--apply', code=1, SHIM='halfremove', **self.shim())
        self.assertIn('stopped: git refused to remove it: error: failed to delete a file of the shim\n', out)
        self.assertNotIn('nothing deleted', out)
        self.assertIn('         POSSIBLY MODIFIED: `git worktree remove` failed and may have deleted part of it first. '
                      'Now its folder is still there, 1 of its 3 tracked files gone; it is no longer a registered '
                      'worktree, its git directory is gone.', out)
        self.assertIn('writes back once what is left of the folder is moved aside:\n'
                      "           git worktree add '%s' 'worktree-done'\n" % os.path.realpath(path), out)
        self.assertIn('clean_worktrees: removed 0, kept 1, PARTLY MODIFIED 1', out)
        self.assertEqual(self.branch('done'), 'worktree-done')
        # The printed recovery works.
        path.rename(self.tmp / 'aside')
        self.git('worktree', 'add', '-q', os.path.realpath(path), 'worktree-done')
        self.assertEqual((path / 'done.txt').read_text(), 'done\n')

    def test_a_tracked_file_git_cannot_delete_is_reported_possibly_modified(self):
        # The real git where it fails: a tracked file in a folder its user cannot write. Root
        # deletes it all the same, so the shim plays git's part too, as in the case above.
        for how in self.failures():
            with self.subTest(how=how):
                name = 'done' if how == 'injected' else 'held'  # the shim deletes done.txt
                path, kept = self.worktree(name), name + '.kept'
                (path / 'sub').mkdir(exist_ok=True)
                (path / 'sub' / kept).write_text('kept\n')
                self.git('add', 'sub/' + kept, cwd=path)
                self.git('commit', '-q', '-m', 'more', cwd=path)
                self.git('merge', '-q', '--no-edit', 'worktree-' + name, KIT_NO_WORKTREE_CLEANUP='1')
                if how == 'permissions':
                    (path / 'sub').chmod(0o555)
                    try:
                        out = self.run_script('--apply', code=1)
                    finally:
                        if (path / 'sub').exists():
                            (path / 'sub').chmod(0o755)
                    self.assertIn("stopped: git refused to remove it: error: failed to delete '", out)
                    self.assertTrue((path / 'sub' / kept).is_file(), out)
                else:
                    out = self.run_script('--apply', code=1, SHIM='halfremove', **self.shim())
                    self.assertIn('stopped: git refused to remove it: error: failed to delete a file of the shim\n', out)
                self.assertIn('         POSSIBLY MODIFIED: `git worktree remove` failed and may have deleted part of it '
                              'first. Now its folder is still there, ', out)
                self.assertIn('it is no longer a registered worktree, its git directory is gone.', out)
                self.assertIn('clean_worktrees: removed 0, kept 1, PARTLY MODIFIED 1', out)
                self.assertRegex((self.main / '.git/kit-worktree-removals.log').read_text(),
                                 r'\toutcome\t[^\t]*/%s\tpossibly-modified\tgit refused to remove it: [^\t]*\n$' % name)
                path.rename(self.tmp / ('aside-' + name))
                self.git('worktree', 'add', '-q', os.path.realpath(path), 'worktree-' + name)
                self.assertEqual((path / 'sub' / kept).read_text(), 'kept\n')
                self.git('worktree', 'remove', str(path))  # out of the next case's run

    def test_a_copy_deleted_before_a_failed_git_worktree_remove_is_possibly_modified(self):
        # Opus: when both happened, git may have deleted more than the copies; that wins.
        path = self.worktree('done')
        for root in (self.main, path):
            (root / 'r.md').write_text('same\n')
        out = self.run_script('--apply', code=1, SHIM='fail:remove', **self.shim())
        self.assertIn('POSSIBLY MODIFIED: `git worktree remove` failed', out)
        self.assertIn('PARTLY MODIFIED: 1 files git does not track were deleted from it', out)
        self.assertTrue((self.main / '.git/kit-worktree-removals.log').read_text().endswith(
            '\toutcome\t%s\tpossibly-modified\tgit refused to remove it: fatal: refused by the shim\tdeleted=r.md\n'
            % os.path.realpath(path)))

    def test_an_output_it_cannot_encode_changes_no_outcome(self):
        # Reproduced by a reviewer: under an ASCII stdout, the recovery line for a main folder
        # with a non-ASCII name raised after `git worktree remove`, and the report said "nothing
        # deleted, the worktree stays" of a worktree that was gone. A second reviewer: the
        # command then printed held \xNN inside quotes, which a shell takes literally. Every
        # printed command is run here and must reach the original names.
        self.main.rename(self.tmp / 'mäin')
        self.main = self.tmp / 'mäin'
        self.git('branch', '-m', 'mäin')
        path = self.worktree('done', branch='worktree-dö')
        out = self.run_script('--apply', '--quiet', PYTHONIOENCODING='ascii')
        self.assertRemoved(path, out)
        self.assertNotIn('nothing deleted', out)
        self.assertTrue(out.isascii(), out)
        self.assertIn('(branch worktree-d\\xc3\\xb6, ', out)
        self.assertIn('clean_worktrees: removed 1, kept 1', out)
        self.assertRegex((self.main / '.git/kit-worktree-removals.log').read_text(), r'\toutcome\t[^\t]*\tremoved\n$')
        for command in (self.restore(out).strip(),
                        re.search(r'`(git branch --merged [^`]*)` lists them', out).group(1)):
            ran = subprocess.run(['sh', '-c', command], cwd=self.main, env=self.env, capture_output=True)
            self.assertEqual(ran.returncode, 0, (command, ran.stderr))
        self.assertEqual(self.git('symbolic-ref', 'HEAD', cwd=path), 'refs/heads/worktree-dö')
        self.assertTrue((path / 'done.txt').is_file())
        self.assertIn(b'worktree-d\xc3\xb6', ran.stdout)
        # The POSSIBLY MODIFIED report's command, when the git directory is gone.
        self.git('commit', '-q', '--allow-empty', '-m', 'later', cwd=path)
        self.git('merge', '-q', '--no-edit', 'worktree-dö', KIT_NO_WORKTREE_CLEANUP='1')
        out = self.run_script('--apply', code=1, SHIM='halfremove', PYTHONIOENCODING='ascii', **self.shim())
        self.assertIn('POSSIBLY MODIFIED', out)
        path.rename(self.tmp / 'aside')
        command = out.split('writes back once what is left of the folder is moved aside:\n')[1].split('\n')[0]
        ran = subprocess.run(['sh', '-c', command], cwd=self.main, env=self.env, capture_output=True)
        self.assertEqual(ran.returncode, 0, (command, ran.stderr))
        self.assertEqual((path / 'done.txt').read_text(), 'done\n')
        # And when the worktree is whole: `git -C <path> restore`.
        self.git('commit', '-q', '--allow-empty', '-m', 'again', cwd=path)
        self.git('merge', '-q', '--no-edit', 'worktree-dö', KIT_NO_WORKTREE_CLEANUP='1')
        out = self.run_script('--apply', code=1, SHIM='fail:remove', PYTHONIOENCODING='ascii', **self.shim())
        command = out.split('writes back:\n')[1].split('\n')[0]
        self.assertIn(' restore -- .', command)
        (path / 'done.txt').unlink()
        ran = subprocess.run(['sh', '-c', command], cwd=self.main, env=self.env, capture_output=True)
        self.assertEqual(ran.returncode, 0, (command, ran.stderr))
        self.assertEqual((path / 'done.txt').read_text(), 'done\n')

    def test_a_shell_word_reads_back_to_its_bytes(self):
        names = [b'plain', b"it's", b'a;id;#', b'-n', b'%s%%', b'back\\slash', b'caf\xc3\xa9', b'\xff\x01 x',
                 b'$(id)', b'"q"', b'tab\tend', b'\x017\xc3\xa90', b'-\xc3\xa9', bytes(range(1, 10)) + bytes(range(11, 256))]
        for name in names:
            with self.subTest(name=name):
                word = clean_worktrees.sh_word(name)
                self.assertTrue(word.isascii() and word.isprintable(), word)
                ran = subprocess.run(['sh', '-c', 'printf %%s %s' % word], capture_output=True)
                self.assertEqual(ran.stdout, name, word)
        self.assertEqual(clean_worktrees.sh_word(b"it's"), "'it'\\''s'")

    def run_closed(self, code, command=None):
        """The script (or COMMAND) with its stdout a pipe nobody reads any more, as after a hang-up."""
        read, write = os.pipe()
        os.close(read)
        try:
            result = subprocess.run(command or ['sh', str(SCRIPT), '--apply', '--assume-idle'], cwd=self.main,
                                    env=self.env, stdout=write, stderr=subprocess.PIPE)
        finally:
            os.close(write)
        self.assertEqual(result.returncode, code, result.stderr)
        self.assertEqual(result.stderr, b'')

    def test_a_closed_stdout_stops_neither_the_removal_nor_its_exit_status(self):
        # Reproduced by a reviewer: SIGHUP left the PARTLY MODIFIED report raising
        # BrokenPipeError, and the script exited 120 after deleting a file.
        (self.main / 'sub').mkdir()
        (self.main / 'sub/report.md').write_text('archived\n')
        (self.main / 'report.md').write_text('top\n')
        log = self.main / '.git/kit-worktree-removals.log'
        for how in self.failures():
            with self.subTest(how=how):
                log.unlink(missing_ok=True)
                path = self.worktree('done-' + how)
                self.git('update-ref', 'refs/worktree/keep', self.loose(path), cwd=path)
                (path / 'sub').mkdir()
                (path / 'sub/report.md').write_text('archived\n')
                (path / 'report.md').write_text('top\n')
                if how == 'injected':
                    self.run_closed(1, self.driver(FAIL_UNLINK, '/sub/'))
                else:
                    (path / 'sub').chmod(0o555)
                    try:
                        self.run_closed(1)
                    finally:
                        if (path / 'sub').exists():
                            (path / 'sub').chmod(0o755)
                self.assertFalse((path / 'report.md').exists())
                self.assertIn('\tdelete=report.md\tdelete=sub/report.md\n', log.read_text())
                self.assertEqual(log.read_text().count('\tsaved=refs/kit/saved/done-'), 1)
                self.run_closed(0)
                self.assertFalse(path.exists())
                self.assertEqual(log.read_text().count('\n'), 5)

    def test_a_stdout_closed_from_the_start_stops_nothing(self):
        # Reproduced by a reviewer: started with `>&-`, Python has no sys.stdout and the first
        # line printed raised AttributeError.
        path = self.worktree('done')
        ran = subprocess.run(['sh', '-c', 'exec sh "$0" --apply --assume-idle >&-', str(SCRIPT)], cwd=self.main,
                             env=self.env, capture_output=True)
        self.assertEqual((ran.returncode, ran.stderr), (0, b''))
        self.assertFalse(path.exists())
        self.assertRegex((self.main / '.git/kit-worktree-removals.log').read_text(), r'\toutcome\t[^\t]*\tremoved\n$')
        # The other ways a stdout cannot be written: a closed file object, and one whose
        # descriptor cannot be replaced by /dev/null.
        class Broken:
            encoding = 'ascii'

            class buffer:
                def write(data):
                    raise OSError(5, 'injected')

            def fileno():
                return 1 << 30
        closed = open(os.devnull, 'w')
        closed.close()
        saved, before = sys.stdout, len(os.listdir('/dev/fd'))
        try:
            for stdout in (None, closed, Broken):
                sys.stdout = stdout
                clean_worktrees.say('x')
        finally:
            sys.stdout = saved
        # Opus: the descriptor opened on /dev/null was left open when it could not replace stdout.
        self.assertEqual(len(os.listdir('/dev/fd')), before)

    def test_every_line_about_a_removal_comes_after_its_log_line(self):
        # Each line is printed with the number of intent and outcome lines the log held then: a
        # hung-up terminal must never leave saved refs, a deletion or a removal with no record.
        log = self.main / '.git/kit-worktree-removals.log'
        driver = ('import sys\nsys.path.insert(0, sys.argv[1])\nimport clean_worktrees as c\nsay, log = c.say, sys.argv[2]\n'
                  'def check(text):\n'
                  '    try:\n        kinds = [line.split("\\t")[2:3] for line in open(log) if line[:1] != "#"]\n'
                  '    except OSError:\n        kinds = []\n'
                  '    say("%d %d " % (kinds.count(["intent"]), kinds.count(["outcome"])) + text)\n'
                  'c.say = check\nsys.argv = ["clean_worktrees", "--apply", "--assume-idle"]\nsys.exit(c.main())\n')

        def run(code, *expected):
            result = subprocess.run([sys.executable, '-c', driver, str(SCRIPTS), str(log)], cwd=self.main,
                                    env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            lines = result.stdout.split('\n')
            for text in expected:
                self.assertEqual(len([line for line in lines if line.startswith(text)]), 1, (text, result.stdout))
        path = self.worktree('done')
        self.git('update-ref', 'refs/worktree/keep', self.loose(path), cwd=path)
        run(0, '1 0 remove .claude/worktrees/done (', '1 0          saves what only its git directory holds',
            '1 0          to delete the saved refs once you no longer want them',
            '1 1          this command, run in the main worktree, brings the worktree back:', '1 1            git worktree add')
        self.assertFalse(path.exists())
        # A stop after a deletion: the outcome is logged before the report of it.
        path = self.worktree('late')
        for root in (self.main, path):
            (root / 'r.md').write_text('same\n')
        self.trigger(self.tmp / 'proc', 3, then='  kill -TERM $PPID\n')
        run(1, '2 1 remove .claude/worktrees/late (', '2 2          stopped: interrupted by signal 15',
            '2 2          PARTLY MODIFIED: 1 files', '2 2            r.md')
        self.assertTrue(path.is_dir())

    def test_a_signal_during_the_removal_is_reported_and_a_rerun_finishes(self):
        # tmux is asked a second time right before the first deletion, a third time after the
        # deletions, right before `git worktree remove`: its parent is the script.
        for name, sig, at in (('term', 'TERM', 3), ('int', 'INT', 3), ('first', 'TERM', 2)):
            with self.subTest(sig=sig, at=at):
                path = self.worktree(name)
                for root in (self.main, path):
                    (root / 'r.md').write_text('same\n')
                (self.tmp / 'tmux-calls').unlink(missing_ok=True)
                self.trigger(self.tmp / 'proc', at, then='  kill -%s $PPID\n' % sig)
                out = self.run_script('--apply', code=1)
                self.assertIn('stopped: interrupted by signal', out)
                self.assertIn('clean_worktrees: stopped by signal', out)
                self.assertTrue(path.is_dir(), out)
                self.assertIs((path / 'r.md').exists(), at == 2, out)
                if at == 3:
                    self.assertIn('PARTLY MODIFIED: 1 files git does not track were deleted from it', out)
                    self.assertIn('\n           r.md\n', out)
                else:
                    self.assertIn('nothing deleted, the worktree stays', out)
                self.stub('tmux', TMUX)
                self.assertRemoved(path, self.run_script('--apply'))
        # The audit stays interruptible: a signal while the next worktree is audited (tmux's
        # fourth call) ends the run by that signal.
        paths = [self.worktree('one'), self.worktree('two')]
        (self.tmp / 'tmux-calls').unlink(missing_ok=True)
        self.trigger(self.tmp / 'proc', 4, then='  kill -TERM $PPID\n')
        self.run_script('--apply', code=-signal.SIGTERM)
        self.assertEqual(sorted(p.is_dir() for p in paths), [False, True])

    def trigger(self, proc, at, *paths, then=''):
        """A tmux that, from its AT-th call on, puts a process working in each of PATHS into
        PROC and runs THEN: the script asks tmux right before it reads the process listing."""
        count = self.tmp / 'tmux-calls'
        starts = then + ''.join('  mkdir -p %s/990%d; [ -L %s/990%d/cwd ] || ln -s %s %s/990%d/cwd\n'
                         % (proc, i, proc, i, os.path.realpath(p), proc, i) for i, p in enumerate(paths))
        self.stub('tmux', '#!/bin/sh\nn=$(($(cat %s 2>/dev/null || echo 0) + 1))\necho $n > %s\n'
                  'if [ $n -ge %d ]; then\n%sfi\necho "no server running on /tmp/x" >&2\nexit 1\n'
                  % (count, count, at, starts))

    def test_the_process_listing_is_read_afresh_for_each_worktree(self):
        # Reproduced by a reviewer: one listing per run judged a worktree audited minutes later.
        one, two = self.worktree('one'), self.worktree('two')
        proc = self.tmp / 'proc'
        self.trigger(proc, 2, one, two)
        out = self.run_script(idle=False, proc=proc)
        self.assertEqual(out.count('remove .claude/worktrees/'), 1, out)
        self.assertEqual(len(re.findall(r'in use: process 990\d works inside it', out)), 1, out)

    def test_a_process_that_starts_after_the_audit_stops_the_removal(self):
        # Asked again before the first deletion, and again right before `git worktree remove`.
        for at, code in ((2, 0), (3, 1)):
            with self.subTest(at=at):
                path = self.worktree('w%d' % at)
                (self.main / 'r.md').write_text('same\n')
                (path / 'r.md').write_text('same\n')
                proc = self.tmp / ('proc%d' % at)
                (self.tmp / 'tmux-calls').unlink(missing_ok=True)
                self.trigger(proc, at, path)
                out = self.run_script('--apply', idle=False, proc=proc, code=code)
                self.assertTrue(path.is_dir(), out)
                self.assertIn('stopped: changed since its audit: in use: process 9900 works inside it', out)
                self.assertIs((path / 'r.md').exists(), at == 2, out)
                self.assertIs('PARTLY MODIFIED: 1 files' in out, at == 3, out)
                self.git('worktree', 'lock', str(path))  # out of the next run before it asks tmux

    def test_a_commit_named_after_the_audit_stops_the_removal(self):
        path = self.worktree('done')
        late = self.loose(path)
        self.trigger(self.tmp / 'proc', 2, then='  echo %s > %s/LATE\n' % (late, self.gitdir(path)))
        out = self.run_script('--apply', idle=False, proc=self.tmp / 'proc')
        self.assertIn('stopped: changed since its audit: it holds commits not saved; nothing deleted', out)
        self.assertTrue(path.is_dir(), out)

    def test_no_removal_without_its_log_record(self):
        path = self.worktree('done')
        self.git('update-ref', 'refs/worktree/keep', self.loose(path), cwd=path)
        (self.main / '.git/kit-worktree-removals.log').mkdir()
        out = self.run_script('--apply')
        self.assertKept(path, out, 'cannot write the removal log %s/.git/kit-worktree-removals.log' % os.path.realpath(self.main),
                        ': nothing is saved or deleted without its record')
        self.assertNotIn('remove .claude', out)
        self.assertEqual(self.git('for-each-ref', 'refs/kit/'), '')

    def test_an_outcome_that_cannot_be_logged_stops_the_run_and_fails(self):
        # Codex: a failed outcome write (or its fsync) was swallowed, further worktrees were
        # removed, and the run exited 0. The removal stands; the run stops there and fails.
        driver = ('import os, sys\nsys.path.insert(0, sys.argv[1])\nimport clean_worktrees as c\n'
                  'mode, real_line, real_sync, calls = sys.argv[2], c.log_line, os.fsync, []\n'
                  'def line(ctx, fields):\n'
                  '    if mode == "write" and fields[0] == "outcome":\n'
                  '        raise OSError(5, "injected")\n'
                  '    return real_line(ctx, fields)\n'
                  'def sync(fd):\n'
                  '    calls.append(fd)\n'
                  '    if mode == "fsync" and len(calls) == 2:\n'
                  '        raise OSError(5, "injected")\n'
                  '    return real_sync(fd)\n'
                  'c.log_line, os.fsync = line, sync\n'
                  'sys.argv = ["clean_worktrees", "--apply", "--assume-idle"]\nsys.exit(c.main())\n')
        for mode in ('write', 'fsync'):
            with self.subTest(mode=mode):
                paths = [self.worktree(mode + '1'), self.worktree(mode + '2')]
                result = subprocess.run([sys.executable, '-c', driver, str(SCRIPTS), mode], cwd=self.main,
                                        env=self.env, capture_output=True, text=True)
                out = result.stdout + result.stderr
                self.assertEqual(result.returncode, 1, out)
                self.assertEqual(sorted(p.exists() for p in paths), [False, True], out)
                self.assertEqual(out.count('remove .claude/worktrees/'), 1, out)
                self.assertIn('cannot write the outcome to the removal log', out)
                self.assertIn('brings the worktree back:', out)
                self.assertIn('clean_worktrees: stopped: the outcome of the last removal could not be written to the '
                              'removal log; the worktrees after it were not looked at', out)
                self.assertIn('clean_worktrees: removed 1, kept 1', out)
                for path in paths:
                    if path.exists():
                        self.git('worktree', 'lock', str(path))

    def test_a_bare_main_repository_is_refused(self):
        bare = self.tmp / 'bare.git'
        self.git('clone', '-q', '--bare', str(self.main), str(bare))
        path = bare / '.claude/worktrees/w'
        self.git('worktree', 'add', '-q', str(path), '-b', 'worktree-w', cwd=bare)
        result = subprocess.run(['sh', str(SCRIPT), '--apply', '--assume-idle'], cwd=path, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('the main repository is bare', result.stdout)
        self.assertTrue(path.is_dir())

    def test_the_script_deletes_no_branch_and_runs_no_forcing_or_pruning_command(self):
        tree = ast.parse((SCRIPTS / 'clean_worktrees.py').read_text())
        words, calls = set(), []
        for call in ast.walk(tree):
            if isinstance(call, ast.Call):
                found = {node.value for node in ast.walk(ast.Module(body=[ast.Expr(a) for a in call.args], type_ignores=[]))
                         if isinstance(node, ast.Constant) and isinstance(node.value, str)}
                words |= found
                calls.append(found)
        self.assertIn('worktree', words)  # the walk sees the argument lists
        self.assertIn({'git', 'worktree', 'remove'}, [c & {'git', 'worktree', 'remove'} for c in calls])
        for found in calls:
            self.assertFalse('branch' in found and found & {'-d', '-D', '--delete', '-m', '-M', '-f'}, found)
            self.assertNotIn('reflog', found)
            # Refs are only ever created: `update-ref --stdin` reads `create` lines alone.
            self.assertFalse('update-ref' in found and found - {'git'} != {'update-ref', '--stdin'}, found)
        self.assertEqual(re.findall(r"b'(\w+) %s %s", (SCRIPTS / 'clean_worktrees.py').read_text()), ['create'])
        for word in ('--force', '-D', '-ff', 'prune', 'clean', 'rm', '-rf'):
            self.assertNotIn(word, words)
        for shell in (SCRIPT, HOOK):
            code = [line for line in shell.read_text().split('\n') if not line.lstrip().startswith('#')]
            for word in ('rm ', '--force', 'prune', 'git clean', ' -D', 'branch -d', 'branch -D', 'branch --delete'):
                self.assertFalse([line for line in code if word in line], (shell, word))

    def test_an_undone_merge_still_finds_the_worker_s_commits_in_its_branch(self):
        # Reproduced by a reviewer: the hook removed the worktree and deleted the branch, the
        # owner undid the merge, and no ref held the worker's commits.
        self.hooked()
        path = self.worktree('w', merge=False)
        tip = self.git('rev-parse', 'worktree-w')
        out = self.merge_with_hook('worktree-w')
        self.assertFalse(path.exists(), out)
        self.git('reset', '-q', '--hard', 'HEAD~1')
        self.assertNotEqual(self.git('for-each-ref', '--contains', tip), '', out)

    # --- a: which worktrees are the script's at all -------------------------------------------

    def test_the_main_worktree_is_untouched(self):
        out = self.run_script('--apply')
        self.assertTrue((self.main / 'a').is_file())
        self.assertIn('keep   %s\n         - the main worktree' % os.path.realpath(self.main), out)

    def test_a_worktree_outside_claude_worktrees_is_untouched(self):
        outside, deeper = self.tmp / 'elsewhere', self.main / '.claude/worktrees/group/deeper'
        for path in (outside, deeper):
            self.git('worktree', 'add', '-q', '--detach', str(path))
        out = self.run_script('--apply')
        self.assertTrue(outside.is_dir() and deeper.is_dir(), out)
        self.assertEqual(out.count('not directly under .claude/worktrees'), 2, out)

    def test_the_worktree_the_script_runs_in_is_kept(self):
        path = self.worktree('done')
        out = self.run_script('--apply', cwd=path)
        self.assertKept(path, out, 'the worktree this script runs in')

    def test_a_locked_worktree_is_kept_and_its_first_reason_ends_the_audit(self):
        path = self.worktree('done', merge=False)
        self.git('worktree', 'lock', '--reason', 'kept on purpose', str(path))
        out = self.run_script('--apply')
        self.assertKept(path, out, 'locked (git worktree lock): kept on purpose')
        self.assertNotIn('not merged', out)

    def test_a_locked_worktree_that_lost_its_git_file_or_its_folder(self):
        # A locked worktree is never reported prunable: the checks below catch it themselves.
        gone, moved = self.worktree('gone'), self.worktree('moved')
        for path in (gone, moved):
            self.git('worktree', 'lock', str(path))
        (gone / '.git').unlink()
        shutil.move(str(moved), str(self.tmp / 'moved'))
        out = self.run_script('--apply', '--all-reasons')
        self.assertKept(gone, out, 'its folder is not its own worktree')
        self.assertIn('keep   .claude/worktrees/moved\n         - locked (git worktree lock)\n'
                      '         - missing or prunable', out)

    def test_a_missing_worktree_is_kept_and_not_pruned(self):
        path = self.worktree('done')
        shutil.rmtree(path)
        out = self.run_script('--apply')
        self.assertIn('keep   .claude/worktrees/done\n         - missing or prunable', out)
        self.assertIn(str(path), self.git('worktree', 'list', '--porcelain'))

    def test_a_prunable_worktree_whose_folder_remains_is_kept(self):
        # Its .git file gone, the folder resolves to MAIN: every check would judge main.
        path = self.worktree('done')
        (path / '.git').unlink()
        (path / 'only-here.md').write_text('unique\n')
        out = self.run_script('--apply')
        self.assertKept(path, out, 'missing or prunable')
        self.assertTrue((path / 'only-here.md').is_file())

    def test_a_repository_made_in_a_worktree_folder_is_kept(self):
        path = self.worktree('done')
        (path / '.git').unlink()
        self.git('init', '-q', str(path))
        self.assertKept(path, self.run_script('--apply'), 'its folder is not its own worktree')

    def test_a_branch_or_path_that_cannot_be_printed_is_kept(self):
        # Through a git that reports the branch with a byte that is not UTF-8, on every file
        # system; then for real where the file system takes such a name (APFS refuses it).
        reason = 'its path or branch name is not printable UTF-8: the command that brings it back could not be printed'
        path = self.worktree('done')
        out = self.run_script('--apply', SHIM='branch', **self.shim())
        self.assertKept(path, out, reason)
        self.git('worktree', 'add', '-q', str(self.main / '.claude/worktrees/odd'), '-b',
                 os.fsdecode(b'worktree-\xff'), check=False)
        odd = self.main / '.claude/worktrees/odd'
        if odd.is_dir():
            self.git('commit', '-q', '--allow-empty', '-m', 'work', cwd=odd)
            self.git('merge', '-q', os.fsdecode(b'worktree-\xff'))
            self.assertKept(odd, self.run_script('--apply'), reason)
        line = self.main / '.claude/worktrees' / 'new\nline'
        self.git('worktree', 'add', '-q', str(line), '-b', 'worktree-newline')
        self.assertIn(reason, self.run_script('--apply'))
        self.assertTrue(line.is_dir())

    # --- b: finished: a commit made in it, and merged into the main branch -----------------

    def test_the_main_worktree_on_a_detached_head_removes_nothing(self):
        # Reproduced by a reviewer: merged into a detached HEAD, the hook removed the worktree
        # and its branch; back on main, no ref held the worker's commits.
        self.hooked()
        path = self.worktree('w', merge=False)
        tip = self.git('rev-parse', 'worktree-w')
        self.git('checkout', '-q', '--detach')
        out = self.merge_with_hook('worktree-w', '--no-edit')
        self.git('checkout', '-q', 'main')
        self.assertTrue(path.is_dir(), out)
        self.assertNotEqual(self.git('for-each-ref', '--contains', tip), '', out)
        self.assertIn("clean_worktrees: nothing removed: the main worktree's HEAD is detached", out)
        self.git('checkout', '-q', '--detach')
        self.assertEqual(self.run_script('--apply').strip().split('\n')[1:],
                         ["clean_worktrees: nothing removed: the main worktree's HEAD is detached, and a "
                          "worktree is finished only once its branch is in the main worktree's branch"])

    def test_merged_means_in_the_main_branch_not_in_its_head(self):
        path = self.worktree('done', merge=False)
        self.git('worktree', 'add', '-q', '--detach', str(self.tmp / 'other'))
        self.git('merge', '-q', '--no-edit', 'worktree-done', cwd=self.tmp / 'other')
        self.assertKept(path, self.run_script('--apply'), 'its branch is not merged')

    def test_a_fresh_worktree_with_no_commit_is_kept_after_a_merge(self):
        # Reproduced by a reviewer: a worker's fresh worktree was removed by the next merge.
        self.hooked()
        self.git('worktree', 'add', '-q', '.claude/worktrees/fresh', '-b', 'worktree-fresh')
        fresh = self.main / '.claude/worktrees/fresh'
        done = self.worktree('done', merge=False)
        out = self.merge_with_hook('worktree-done')
        self.assertTrue(fresh.is_dir(), out)
        self.assertFalse(done.exists(), out)
        self.assertKept(fresh, self.run_script(), 'no commit was made in this worktree')

    def test_a_merged_branch_given_a_new_worktree_is_kept(self):
        # Reproduced by a reviewer: the BRANCH's reflog had moved before the worktree existed.
        first = self.worktree('feat')
        self.git('worktree', 'remove', str(first))
        again = self.main / '.claude/worktrees/again'
        self.git('worktree', 'add', '-q', str(again), 'worktree-feat')
        self.git('branch', '-c', 'worktree-feat', 'worktree-copy')
        copy = self.main / '.claude/worktrees/copy'
        self.git('worktree', 'add', '-q', str(copy), 'worktree-copy')
        out = self.run_script('--apply')
        self.assertKept(again, out, 'no commit was made in this worktree')
        self.assertKept(copy, out)

    def test_a_worker_that_only_fast_forwarded_or_merged_is_kept(self):
        # Reproduced by a reviewer: a fast-forward moved the branch with no work done there.
        ff = self.worktree('ff', commit=False, merge=False)
        merged = self.worktree('merged', commit=False, merge=False)
        self.git('commit', '-q', '--allow-empty', '-m', 'main moved')
        self.git('merge', '-q', 'main', cwd=ff)
        self.git('commit', '-q', '--allow-empty', '-m', 'unrelated', cwd=self.main)
        # A commit made elsewhere, which the worker only merges.
        self.git('branch', 'side', self.git('commit-tree', 'HEAD^{tree}', '-p', 'HEAD~1', '-m', 'side'))
        self.git('merge', '-q', '--no-ff', '--no-edit', 'side', cwd=merged)
        self.git('merge', '-q', '--no-edit', 'worktree-merged')
        out = self.run_script('--apply')
        self.assertKept(ff, out, 'no commit was made in this worktree')
        self.assertKept(merged, out)

    def test_which_reflog_subjects_count_as_a_commit_made_here(self):
        # Every subject read from what this git really writes; one case per operation.
        path = self.worktree('w', merge=False)
        run = lambda *args, **extra: self.git(*args, cwd=path, check=False, **extra)  # noqa: E731
        run('checkout', '-q', '-b', 'side')
        for name in ('s', 't', 'u'):
            (path / name).write_text(name + '\n')
            run('add', name)
            run('commit', '-q', '-m', name)
        run('checkout', '-q', 'worktree-w')
        run('commit', '-q', '--amend', '-m', 'amended')
        run('cherry-pick', 'side~2')
        run('revert', '--no-edit', 'HEAD')
        run('reset', '-q', '--hard', 'side~3')
        run('cherry-pick', '--ff', 'side~2')
        run('merge', '-q', '--ff-only', 'side')
        run('rebase', '-q', '--force-rebase', 'HEAD~2')
        run('rebase', '-q', 'HEAD~1')
        run('rebase', '-q', '-i', '--force-rebase', 'HEAD~3', GIT_EDITOR='true',
            GIT_SEQUENCE_EDITOR="sed -i.bak -e '1s/^pick/reword/' -e '2s/^pick/squash/' -e '3s/^pick/fixup/'")
        run('format-patch', '-q', '-1', 'side', '-o', str(self.tmp / 'patch'))
        run('reset', '-q', '--hard', 'side~1')
        run('am', '-q', *[str(p) for p in (self.tmp / 'patch').iterdir()])
        (path / 'a').write_text('mine\n')
        run('commit', '-q', '-am', 'mine')
        run('checkout', '-q', '-b', 'other', 'HEAD~1')
        (path / 'a').write_text('theirs\n')
        run('commit', '-q', '-am', 'theirs')
        run('merge', 'worktree-w')
        (path / 'a').write_text('both\n')
        run('add', 'a')
        run('commit', '-q', '--no-edit')
        run('checkout', '-q', 'worktree-w')
        run('rebase', 'other^1')
        (path / 'a').write_text('again\n')
        run('add', 'a')
        run('rebase', '--continue', GIT_EDITOR='true')
        run('checkout', '-q', '-b', 'extra', 'HEAD~1')
        (path / 'x').write_text('x\n')
        run('add', 'x')
        run('commit', '-q', '-m', 'x')
        run('checkout', '-q', 'worktree-w')
        run('merge', '-q', '--no-ff', '--no-edit', 'extra')
        # A conflicted cherry-pick concluded by `git commit`.
        run('checkout', '-q', '-b', 'pick', 'HEAD~1')
        (path / 'a').write_text('picked\n')
        run('commit', '-q', '-am', 'to pick')
        run('checkout', '-q', 'worktree-w')
        (path / 'a').write_text('conflicting\n')
        run('commit', '-q', '-am', 'conflicting')
        run('cherry-pick', 'pick')
        (path / 'a').write_text('resolved\n')
        run('add', 'a')
        run('commit', '-q', '--no-edit')
        # `git pull` with no argument: a fast-forward, then a merge, neither made here.
        run('checkout', '-q', '-b', 'ahead')
        run('commit', '-q', '--allow-empty', '-m', 'ahead')
        run('checkout', '-q', 'worktree-w')
        run('config', 'branch.worktree-w.remote', '.')
        run('config', 'branch.worktree-w.merge', 'refs/heads/ahead')
        run('config', 'pull.rebase', 'false')
        run('pull')
        run('checkout', '-q', 'ahead')
        run('commit', '-q', '--allow-empty', '-m', 'ahead again')
        run('checkout', '-q', 'worktree-w')
        run('commit', '-q', '--allow-empty', '-m', 'diverge')
        run('pull', GIT_MERGE_AUTOEDIT='no')
        counted = ('commit:', 'commit (amend):', 'commit (merge):', 'commit (cherry-pick):', 'cherry-pick: s', 'revert:',
                   'rebase (pick):', 'rebase (reword):', 'rebase (squash):', 'rebase (fixup):', 'rebase (continue):', 'am:')
        not_counted = ('reset:', 'checkout:', 'cherry-pick: fast-forward', 'merge side: Fast-forward', 'rebase (start):',
                       'rebase (finish):', 'merge extra: Merge made by', 'pull: Fast-forward', 'pull: Merge made by')
        seen = set()
        for line in (self.gitdir(path) / 'logs/HEAD').read_bytes().split(b'\n')[1:-1]:
            subject = line.partition(b'\t')[2].decode()
            kind = [p for p in counted + not_counted if subject.startswith(p)]
            self.assertEqual(len(kind), 1, subject)
            seen.add(kind[0])
            with self.subTest(subject=subject):
                self.assertIs(clean_worktrees.made_here(line), kind[0] in counted)
        self.assertEqual(seen, set(counted + not_counted))
        self.assertFalse(clean_worktrees.made_here(b''))

    def test_a_worktree_without_its_own_head_reflog_is_kept(self):
        path = self.worktree('done')
        (self.gitdir(path) / 'logs/HEAD').unlink()
        self.assertKept(path, self.run_script('--apply'), 'no commit was made in this worktree')

    def test_a_detached_worktree_is_kept(self):
        path = self.main / '.claude/worktrees/detached'
        self.git('worktree', 'add', '-q', '--detach', str(path))
        self.assertKept(path, self.run_script('--apply'), 'detached HEAD: remove it by hand')

    def test_an_unmerged_or_squash_merged_branch_is_kept(self):
        path = self.worktree('done', merge=False)
        self.assertKept(path, self.run_script('--apply'), 'its branch is not merged')
        self.git('merge', '-q', '--squash', 'worktree-done')
        self.git('commit', '-q', '-m', 'squashed')
        self.assertKept(path, self.run_script('--apply'), 'its branch is not merged')

    # --- c and h: the quiet period ----------------------------------------------------------

    def test_a_recent_change_anywhere_in_its_git_directory_or_its_files_keeps_it(self):
        path = self.worktree('done')
        gitdir = self.gitdir(path)
        (path / 'build').mkdir()
        (path / 'build/o').write_text('o\n')
        self.git('reset', '-q', 'HEAD', cwd=path)  # writes ORIG_HEAD
        for name in ('FETCH_HEAD', 'check-build.log'):
            (gitdir / name).write_text('\n')
        self.disposable('build\n')
        for touched in (gitdir / 'HEAD', gitdir / 'index', gitdir / 'logs/HEAD', gitdir / 'ORIG_HEAD',
                        gitdir / 'FETCH_HEAD', gitdir / 'check-build.log', gitdir, path / 'a', path,
                        path / 'build/o', path / 'build'):
            with self.subTest(touched=touched):
                self.recent(touched)
                self.assertKept(path, self.run_script('--apply'), 'quiet period: ',
                                'qualifies in 59 min (quiet-minutes=60, a margin, not a proof)')
                os.utime(touched, (self.now - 7200,) * 2, follow_symlinks=False)
        self.assertRemoved(path, self.run_script('--apply'))

    def test_a_ctime_counts_when_the_mtime_was_kept(self):
        path = self.worktree('done')
        for target in (path / 'a', self.gitdir(path) / 'HEAD'):
            with self.subTest(target=target):
                for folder, dirs, files in os.walk(path):
                    for name in [''] + dirs + files:
                        os.utime(os.path.join(folder, name), (time.time() - 7200,) * 2, follow_symlinks=False)
                for folder, dirs, files in os.walk(self.gitdir(path)):
                    for name in [''] + dirs + files:
                        os.utime(os.path.join(folder, name), (time.time() - 7200,) * 2, follow_symlinks=False)
                # Every mtime two hours old, every ctime from just now: ten minutes on, the
                # ctime is within the period.
                out = self.run_script(CLEAN_WORKTREES_NOW=str(time.time() + 600))
                self.assertKept(path, out, 'quiet period: ')
        self.assertIn('remove .claude/worktrees/done', self.run_script())

    def test_a_set_test_clock_is_announced_on_every_run(self):
        # The clock is for the tests; exported by mistake it would silently end the quiet period.
        self.worktree('done')
        line = 'clean_worktrees: CLEAN_WORKTREES_NOW is set: the quiet period is measured against %s, not the clock' % self.now
        self.assertIn(line + '\n', self.run_script('--apply', '--quiet'))
        self.env.pop('CLEAN_WORKTREES_NOW')
        self.assertNotIn('CLEAN_WORKTREES_NOW', self.run_script('--apply', '--quiet'))
        # So are the /proc and the mount table: by mistake, they would hide a process or a mount.
        table, proc = self.mountinfo(), str(self.tmp / 'no-proc')
        out = self.run_script('--apply', '--quiet', idle=True, CLEAN_WORKTREES_MOUNTINFO=table, CLEAN_WORKTREES_PROC=proc)
        self.assertIn('clean_worktrees: CLEAN_WORKTREES_PROC is set: processes are read from %s, not /proc\n' % proc, out)
        self.assertIn('clean_worktrees: CLEAN_WORKTREES_MOUNTINFO is set: the mount table is read from %s, not '
                      '/proc/self/mountinfo\n' % table, out)
        self.assertNotIn(' is set: ', self.run_script('--apply', '--quiet'))

    def test_a_future_time_counts_as_recent(self):
        path = self.worktree('done')
        os.utime(path / 'a', (self.now + 86400,) * 2)
        self.assertKept(path, self.run_script('--apply'), 'quiet period: a file in it')

    def test_quiet_minutes_is_read_from_the_disposable_list_and_a_low_value_refused(self):
        path = self.worktree('done')
        self.disposable('quiet-minutes=15\n')
        out = self.run_script(CLEAN_WORKTREES_NOW=str(time.time() + 60))
        self.assertKept(path, out, 'qualifies in 14 min (quiet-minutes=15')
        self.assertIn('remove .claude/worktrees/done', self.run_script(CLEAN_WORKTREES_NOW=str(time.time() + 16 * 60)))
        # A duplicate or an invalid setting refuses the whole list (fail closed): a valid value
        # before an invalid one once stayed in force under a warning that said 60 applied.
        (path / 'build').mkdir()
        (path / 'build/o').write_text('o\n')
        for text, line in (('quiet-minutes=5', 'quiet-minutes=5'), ('quiet-minutes=x', 'quiet-minutes=x'),
                           ('quiet-minutes = 30', 'quiet-minutes = 30'), ('quiet-minutes=30x', 'quiet-minutes=30x'),
                           ('quiet-minutes=9', 'quiet-minutes=9'), ('quiet-minutes=10\nquiet-minutes=x', 'quiet-minutes=x'),
                           ('quiet-minutes=10\nquiet-minutes=10', 'quiet-minutes=10')):
            with self.subTest(text=text):
                self.disposable('build\n' + text + '\n')
                out = self.run_script(CLEAN_WORKTREES_NOW=str(time.time() + 16 * 60))
                self.assertIn('refused .claude/worktree-disposable line %s (a quiet-minutes line twice, or not a '
                              'whole number of at least 10): the whole list is refused, nothing is disposable and '
                              'quiet-minutes=60 applies\n' % line, out)
                self.assertEqual(out.count('clean_worktrees: refused'), 1, out)
                self.assertKept(path, out, 'quiet-minutes=60')
                out = self.run_script('--all-reasons', CLEAN_WORKTREES_NOW=str(time.time() + 16 * 60))
                self.assertKept(path, out, 'no identical copy in main, outside a disposable folder: build/o')

    def test_a_run_changes_no_time_it_reads_and_two_runs_agree(self):
        path = self.worktree('done')
        (path / 'mine.md').write_text('only here\n')

        def times():
            return {(root, rel): (info.st_mtime_ns, info.st_ctime_ns)
                    for root in (bytes(path), bytes(self.gitdir(path)))
                    for rel, info, _, _ in clean_worktrees.walk(root)}
        before = times()
        self.run_script('--all-reasons', idle=False)
        self.assertEqual(times(), before)
        # The count of processes it could not inspect is the host's, not the audit's: another
        # job starting or ending one between the runs changed it (a red that passed on re-run).
        # A /proc of the case's own, one more unreadable process on the second run.
        proc = self.tmp / 'proc'
        runs = []
        for pid in ('90001', '90002'):
            (proc / pid).mkdir(parents=True)
            (proc / pid / 'cwd').write_text('not a link\n')
            runs.append(self.run_script('--all-reasons', idle=False, proc=proc))
        self.assertIn(', 1 could not be inspected', runs[0])
        self.assertIn(', 2 could not be inspected', runs[1])
        self.assertEqual(*(re.sub(r'\d+ (processes )?could not be inspected', 'N could not be inspected', out)
                           for out in runs))

    # --- d: an operation in progress -------------------------------------------------------

    def test_a_rebase_or_bisect_in_progress_is_kept(self):
        rebase, bisect = self.worktree('rebase'), self.worktree('bisect')
        self.git('rebase', '--exec', 'false', 'HEAD~1', cwd=rebase, check=False)
        self.git('bisect', 'start', cwd=bisect)
        out = self.run_script('--apply')
        self.assertKept(rebase, out, 'detached HEAD')  # a rebase detaches HEAD
        self.assertKept(bisect, out, 'an operation is in progress: BISECT_START')

    def test_each_operation_marker_is_kept(self):
        path = self.worktree('done')
        for marker in ('CHERRY_PICK_HEAD', 'REVERT_HEAD', 'sequencer', 'MERGE_HEAD', 'rebase-apply', 'rebase-merge'):
            with self.subTest(marker=marker):
                (self.gitdir(path) / marker).write_text('x\n')
                self.assertKept(path, self.run_script('--apply'), 'an operation is in progress: ' + marker)
                (self.gitdir(path) / marker).unlink()

    def test_a_merge_with_a_conflict_is_kept(self):
        path = self.worktree('done')
        self.git('checkout', '-q', '-b', 'side', 'HEAD~1', cwd=path)
        (path / 'a').write_text('side\n')
        self.git('commit', '-q', '-am', 'side', cwd=path)
        self.git('checkout', '-q', 'worktree-done', cwd=path)
        (path / 'a').write_text('mine\n')
        self.git('commit', '-q', '-am', 'mine', cwd=path)
        self.git('merge', '-q', 'side', cwd=path, check=False)
        out = self.run_script('--apply', '--all-reasons')
        self.assertKept(path, out, 'an operation is in progress: MERGE_HEAD', 'tracked change, unmerged: a',
                        'an unresolved index: a')

    # --- e: in use -------------------------------------------------------------------------

    def test_a_process_working_inside_is_kept_by_the_real_listing(self):
        path = self.worktree('done')
        (path / 'deep').mkdir()
        sleeper = subprocess.Popen(['sleep', '60'], cwd=path / 'deep')
        try:
            out = self.run_script('--apply', idle=False)
            # What this host really did, for the CI log of each platform.
            listed = [line for line in out.split('\n') if line.startswith('clean_worktrees: processes listed by')]
            sys.stderr.write('\n[liveness on %s] %s\n' % (sys.platform, listed[0] if listed else out))
            self.assertKept(path, out, 'in use: process %d works inside it' % sleeper.pid)
            self.assertEqual(len(listed), 1, out)
            self.assertTrue(listed[0].startswith('clean_worktrees: processes listed by %s'
                                                 % ('/proc' if PROC else 'lsof (exit ')), out)
            if PROC and shutil.which('lsof'):  # the lsof path, as on macOS
                out = self.run_script('--apply', idle=False, CLEAN_WORKTREES_PROC=str(self.tmp / 'no-proc'))
                # Exit 1 is accepted only with lsof's own warnings on stderr; either way the
                # worker must be seen.
                self.assertKept(path, out, 'in use: process %d works inside it' % sleeper.pid)
                self.assertRegex(out, r'clean_worktrees: processes listed by lsof \(exit [01]\)')
        finally:
            sleeper.kill()
            sleeper.wait()
        self.assertRemoved(path, self.run_script('--apply', idle=False))

    def test_without_proc_and_lsof_it_is_kept_unless_assumed_idle(self):
        path = self.worktree('done')
        self.stub('lsof', '#!/bin/sh\necho "lsof: no permission" >&2\nexit 1\n')
        out = self.run_script('--apply', idle=False, CLEAN_WORKTREES_PROC=str(self.tmp / 'no-proc'))
        self.assertKept(path, out, 'cannot see which processes work in it (no /proc (No such file or directory); '
                        '`lsof -a -d cwd -F pn` failed (exit 1): lsof: no permission)',
                        'scripts/clean_worktrees.sh --apply --assume-idle')
        out = self.run_script('--apply', idle=True, CLEAN_WORKTREES_PROC=str(self.tmp / 'no-proc'))
        self.assertRemoved(path, out)

    def test_lsof_is_trusted_only_when_it_shows_this_script_and_warns_only_as_documented(self):
        path = self.worktree('done')
        noproc = dict(idle=False, CLEAN_WORKTREES_PROC=str(self.tmp / 'no-proc'))
        inside = 'printf "p99999\\nn%s\\n"\n' % os.path.realpath(path)
        for stub, reason in (
                (LSOF_ME + inside + WARNING + 'exit 1\n', 'in use: process 99999 works inside it'),
                (LSOF_ME + inside + 'exit 1\n', 'in use: process 99999 works inside it'),
                (LSOF_ME + inside + WARNING + 'echo "lsof: something else" >&2\nexit 1\n',
                 '`lsof -a -d cwd -F pn` failed (exit 1): lsof: something else'),
                # Codex: a listing cut short by a signal, or any status but 0 and 1, after it
                # printed this script and nothing on stderr, is no listing.
                (LSOF_ME + 'kill -KILL $$\n' + inside, '`lsof -a -d cwd -F pn` failed (exit -9): nothing on stderr'),
                (LSOF_ME + WARNING + 'exit 2\n', '`lsof -a -d cwd -F pn` failed (exit 2): nothing on stderr'),
                ('printf "p1\\nn/\\n"\n' + inside, '`lsof -a -d cwd -F pn` (exit 0) does not show this process'),
                ('printf "p%s\\nn/elsewhere\\n" "$PPID"\n', '(exit 0) does not show this process'),
                (LSOF_ME + 'printf "tREG\\n"\n', '`lsof` printed a record this script does not know: tREG')):
            with self.subTest(stub=stub):
                self.stub('lsof', '#!/bin/sh\n' + stub)
                self.assertKept(path, self.run_script('--apply', **noproc), reason)
        self.stub('lsof', '#!/bin/sh\n' + LSOF_ME + WARNING + 'exit 1\n')
        out = self.run_script('--apply', **noproc)
        self.assertRemoved(path, out)
        self.assertIn('clean_worktrees: processes listed by lsof (exit 1), 0 could not be inspected', out)

    def test_a_proc_that_does_not_show_this_script_is_not_trusted(self):
        path = self.worktree('done')
        proc = self.tmp / 'proc'
        (proc / '11').mkdir(parents=True)
        (proc / '11/cwd').symlink_to(os.path.realpath(path))
        self.stub('lsof', '#!/bin/sh\nexit 1\n')
        out = self.run_script('--apply', idle=False, CLEAN_WORKTREES_PROC=str(proc))
        self.assertKept(path, out, 'cannot see which processes work in it (/proc does not show this process; '
                        '`lsof -a -d cwd -F pn` (exit 1) does not show this process with its working directory)')

    def test_without_lsof_or_tmux_installed(self):
        path = self.worktree('done')
        bare = self.tmp / 'bare-bin'
        bare.mkdir()
        (bare / 'python3').symlink_to(sys.executable)
        for tool in ('git', 'sh', 'dirname'):
            (bare / tool).symlink_to(shutil.which(tool, path=self.env['PATH']))
        env = dict(PATH=str(bare), CLEAN_WORKTREES_PROC=str(self.tmp / 'no-proc'))
        self.assertKept(path, self.run_script('--apply', idle=False, **env), ', and no lsof here)')
        self.assertRemoved(path, self.run_script('--apply', idle=True, **env))

    def test_an_unreadable_process_is_counted_and_reported_not_silently_skipped(self):
        # Unreadable by its mode, which root ignores, and, for any user, a cwd that is no link.
        for how in self.failures():
            with self.subTest(how=how):
                path = self.worktree('done-' + how)
                proc = self.tmp / ('proc-' + how)
                real = os.path.realpath(path)
                for pid, cwd in (('10', os.path.realpath(self.tmp)), ('11', real + '/sub'), ('12', None), ('13', real),
                                 ('14', real + '-sibling')):
                    (proc / pid).mkdir(parents=True)
                    if cwd:
                        (proc / pid / 'cwd').symlink_to(cwd)
                if how == 'injected':
                    (proc / '12/cwd').write_text('')
                else:
                    (proc / '12').chmod(0)
                try:
                    out = self.run_script('--apply', idle=False, proc=proc)
                    self.assertKept(path, out, 'in use: process 11, 13 works inside it\n')
                    self.assertIn('clean_worktrees: processes listed by /proc, 1 could not be inspected', out)
                    self.assertNotIn('process 10', out)
                    shutil.rmtree(proc / '11')
                    shutil.rmtree(proc / '13')
                    for child in proc.iterdir():  # the previous run's own entry
                        if child.name not in ('10', '12', '14'):
                            shutil.rmtree(child)
                    out = self.run_script('--apply', '--quiet', idle=False, proc=proc)
                finally:
                    (proc / '12').chmod(0o755)
                self.assertRemoved(path, out)
                self.assertIn('clean_worktrees: 1 processes could not be inspected', out)

    def test_a_worktree_named_like_an_lsof_error_is_seen_in_use(self):
        # Reproduced by a reviewer: a cwd ending in " (stat: x)" was read as lsof's unreadable
        # cwd, and a worktree of that name with a process inside was removed.
        path = self.worktree('w (stat: x)', branch='worktree-w-stat')
        sleeper = subprocess.Popen(['sleep', '60'], cwd=path)
        try:
            out = self.run_script('--apply', idle=False, CLEAN_WORKTREES_PROC='/nonexistent')
            self.assertKept(path, out, 'in use: process %d works inside it' % sleeper.pid
                            if shutil.which('lsof', path=self.env['PATH']) else ', and no lsof here)')
        finally:
            sleeper.kill()
            sleeper.wait()
        # Only Linux lsof's own form counts as unreadable, and its name is a cwd all the same.
        cwds, unseen = clean_worktrees.parse_lsof(b'p5\nn/r/.claude/worktrees/w (stat: x)\n'
                                                  b'p6\nn/proc/6/cwd (stat: Permission denied)\n'
                                                  b'p7\nn/proc/7/cwd (readlink: x) (stat: y)\n')
        self.assertEqual(cwds, {b'5': b'/r/.claude/worktrees/w (stat: x)', b'6': b'/proc/6/cwd (stat: Permission denied)',
                                b'7': b'/proc/7/cwd (readlink: x) (stat: y)'})
        self.assertEqual(unseen, 1)

    def test_the_lsof_parser_reads_both_platforms_and_refuses_the_unknown(self):
        cwds, unseen = clean_worktrees.parse_lsof(LSOF_LINUX)
        self.assertEqual(cwds, {b'4242': b'/home/u/project/.claude/worktrees/w/src', b'4243': b'/home/u/project',
                                b'1': b'/proc/1/cwd (readlink: Permission denied)',
                                b'77': b'/proc/77/cwd (stat: Permission denied)'})
        self.assertEqual(unseen, 2)
        cwds, unseen = clean_worktrees.parse_lsof(LSOF_MACOS)
        self.assertEqual(cwds, {b'1': b'/', b'501': b'/Users/u/project/.claude/worktrees/w',
                                b'503': b'/private/var/folders/x/project'})
        self.assertEqual(unseen, 1)
        self.assertEqual(clean_worktrees.parse_lsof(b'p9\nnno path\n'), ({}, 1))
        for bad in (b'p1\ntREG\nn/\n', b'n/before-a-process\n', b'pabc\nn/\n', b'p1\nftxt\nn/\n', b'fcwd\np1\n'):
            with self.subTest(bad=bad):
                with self.assertRaises(clean_worktrees.Unproven):
                    clean_worktrees.parse_lsof(bad)

    def test_lsof_names_are_read_back_to_their_bytes_or_the_listing_is_not_proven(self):
        # Under LC_ALL=C, lsof 4.98 here wrote café as caf\xc3\xa9, a backslash as \\, a tab as
        # \t, and the byte 0x01 as ^A, which a name holding "^A" reads as too.
        cafe = 'café'.encode()
        for raw, name in ((b'/w/caf\\xc3\\xa9', b'/w/' + cafe), (b'/w/caf\\303\\251', b'/w/' + cafe),
                          (b'/w/' + cafe, b'/w/' + cafe), (b'/w/a\\\\b', b'/w/a\\b'), (b'/w/a\\\\x41', b'/w/a\\x41'),
                          (b'/w/a\\\\\\\\', b'/w/a\\\\'), (b'/w/n\\nl\\tt\\r\\b\\f', b'/w/n\nl\tt\r\b\f'),
                          (b'/w/s p\\x20', b'/w/s p ')):
            with self.subTest(raw=raw):
                self.assertEqual(clean_worktrees.parse_lsof(b'p1\nn' + raw + b'\n'), ({b'1': name}, 0))
        for bad in (b'/w/x^Ay', b'/w/^', b'/w/a\\qb', b'/w/end\\', b'/w/\\x4', b'/w/\\400', b'/w/\\\\\\'):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(clean_worktrees.Unproven, 'a name this script cannot read back exactly'):
                    clean_worktrees.parse_lsof(b'p1\nn' + bad + b'\n')

    def test_a_process_in_a_worktree_with_a_non_ascii_name_is_found(self):
        # Reproduced by a reviewer: lsof escaped café, the listing still found the script in its
        # ASCII folder, and a worktree in use was removed. Both listings here, as on macOS.
        path = self.worktree('café')
        sleeper = subprocess.Popen(['sleep', '60'], cwd=path)
        try:
            if shutil.which('lsof'):  # what this host's lsof prints, for the CI log
                raw = subprocess.run(['lsof', '-a', '-d', 'cwd', '-F', 'pn', '-p', str(sleeper.pid)],
                                     env=self.env, capture_output=True).stdout
                sys.stderr.write('\n[lsof on %s, LC_ALL=C, a cwd named café] %r\n' % (sys.platform, raw))
            for extra in [{}] + ([{'CLEAN_WORKTREES_PROC': str(self.tmp / 'no-proc')}]
                                 if PROC and shutil.which('lsof') else []):
                with self.subTest(**extra):
                    out = self.run_script('--apply', idle=False, **extra)
                    self.assertKept(path, out, 'in use: process %d works inside it' % sleeper.pid)
        finally:
            sleeper.kill()
            sleeper.wait()
        self.assertRemoved(path, self.run_script('--apply', idle=False))

    def test_a_working_directory_is_matched_as_macos_matches_names(self):
        # macOS ignores case, and HFS+ stores é decomposed while git keeps it composed.
        path = self.worktree('café')
        proc = self.tmp / 'proc'
        real = os.path.realpath(path)
        for pid, cwd in (('9901', real.upper()), ('9902', unicodedata.normalize('NFD', real) + '/sub'),
                         ('9903', real + 'x')):
            (proc / pid).mkdir(parents=True)
            (proc / pid / 'cwd').symlink_to(cwd)
        self.assertKept(path, self.run_script('--apply', idle=False, proc=proc), 'in use: process 9901, 9902 works inside it\n')

    def test_a_tmux_session_of_its_name_is_kept_and_only_no_server_proves_none(self):
        path = self.worktree('done')
        (self.tmp / 'sessions').write_text('lead\ndone\n')
        self.assertKept(path, self.run_script('--apply'), 'in use: a tmux session is named done')
        (self.tmp / 'sessions').write_text('lead\ndone-2\n')
        for error in ('server exited unexpectedly', 'error connecting to /tmp/tmux-1/default (Permission denied)',
                      'error connecting to /tmp/tmux-1/default (Connection refused)', ''):
            with self.subTest(error=error):
                out = self.run_script('--apply', TMUX_STUB_FAIL=error or ' ')
                self.assertKept(path, out, 'not proven: `tmux list-sessions` failed: ' + (error or 'exit 1'))
        out = self.run_script(TMUX_STUB_FAIL='error connecting to /tmp/tmux-1/default (No such file or directory)')
        self.assertIn('remove .claude/worktrees/done', out)
        (self.tmp / 'sessions').unlink()
        self.assertRemoved(path, self.run_script('--apply'))

    def test_a_held_gate_lock_is_kept(self):
        path = self.worktree('done')
        lock = self.gitdir(path) / 'check.lock'
        with open(lock, 'w') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            self.assertKept(path, self.run_script('--apply'), 'in use: the gate holds its lock')
        self.assertRemoved(path, self.run_script('--apply'))

    # --- f: nothing only its git directory holds ------------------------------------------

    def saved(self, out):
        """The ref prefix a removal saved commits under, from its report."""
        return re.search(r'saves what only its git directory holds, as (refs/kit/saved/[^ ]+)/<n>: ', out).group(1)

    def test_an_amended_reset_or_rebased_away_commit_is_saved_and_outlives_its_branch(self):
        # Reproduced by a reviewer: counted as held by its branch's reflog, the old tip was lost
        # once the owner followed the printed `git branch -d`, which deletes that reflog.
        for name, rewrite in (('amend', ('commit', '-q', '--amend', '-m', 'amended')),
                              ('reset', ('reset', '-q', '--hard', 'HEAD~1')),
                              ('rebase', ('rebase', '-q', '--force-rebase', 'HEAD~1'))):
            with self.subTest(name=name):  # a committer date of its own: a new id within the same second
                path = self.worktree(name, merge=False)
                (path / 'later.txt').write_text(name + '\n')
                self.git('add', 'later.txt', cwd=path)
                self.git('commit', '-q', '-m', 'dropped', cwd=path)
                dropped = self.git('rev-parse', 'HEAD', cwd=path)
                self.git(*rewrite, cwd=path, GIT_COMMITTER_DATE='2001-01-01T00:00:00Z')
                self.git('merge', '-q', '--no-edit', 'worktree-' + name, KIT_NO_WORKTREE_CLEANUP='1')
                self.assertNotEqual(self.git('rev-parse', 'HEAD', cwd=path), dropped)
                self.assertIn(dropped, (self.main / '.git/logs/refs/heads' / ('worktree-' + name)).read_text())
                out = self.run_script('--apply')
                self.assertRemoved(path, out)
                self.assertIn('=%s (' % dropped[:12], out)
                self.assertIn(dropped, self.git('rev-list', '--glob=' + self.saved(out) + '/*'))
                self.git('branch', '-d', 'worktree-' + name)
                self.git('reflog', 'expire', '--expire=now', '--expire-unreachable=now', '--all')
                self.git('gc', '-q', '--prune=now')
                self.assertEqual(self.git('cat-file', '-t', dropped), 'commit')

    def test_intermediate_commits_of_a_squash_are_saved_and_survive_gc(self):
        path = self.worktree('squash', merge=False)
        for name in ('s', 't'):
            (path / name).write_text(name + '\n')
            self.git('add', name, cwd=path)
            self.git('commit', '-q', '-m', name, cwd=path)
        self.git('rebase', '-q', '-i', '--force-rebase', 'HEAD~3', cwd=path, GIT_EDITOR='true',
                 GIT_SEQUENCE_EDITOR="sed -i.bak -e '3s/^pick/squash/'", GIT_COMMITTER_DATE='2001-01-01T00:00:00Z')
        # The commit the first step rewrote, before the squash: only its HEAD reflog names it.
        log = (self.gitdir(path) / 'logs/HEAD').read_text()
        step = re.findall(r' ([0-9a-f]{40}) [^\n]*\trebase \(pick\): s\n', log)[-1]
        self.assertNotIn(step, (self.main / '.git/logs/refs/heads/worktree-squash').read_text())
        self.git('merge', '-q', '--no-edit', 'worktree-squash', KIT_NO_WORKTREE_CLEANUP='1')
        dry = self.run_script()
        self.assertIn('=%s (logs/HEAD)' % step[:12], dry)
        self.assertEqual(self.git('for-each-ref', 'refs/kit/'), '', 'a dry run saves nothing')
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        prefix = self.saved(out)
        self.assertTrue(prefix.startswith('refs/kit/saved/squash-'), out)
        self.assertIn(step, self.git('rev-list', '--glob=' + prefix + '/*'))
        self.assertNotEqual(self.git('for-each-ref', '--contains', step, prefix + '/'), '')
        record = (self.main / '.git/kit-worktree-removals.log').read_text()
        self.assertRegex(record, r'\tsaved=%s/\d+=%s' % (re.escape(prefix), step))
        self.git('reflog', 'expire', '--expire=now', '--expire-unreachable=now', '--all')
        self.git('gc', '-q', '--prune=now')
        self.assertEqual(self.git('cat-file', '-t', step), 'commit')

    def test_the_command_that_deletes_the_saved_refs_works_and_is_quoted(self):
        path = self.worktree("it's", merge=False)
        self.git('update-ref', 'refs/worktree/keep', self.loose(path), cwd=path)
        self.git('merge', '-q', '--no-edit', "worktree-it's", KIT_NO_WORKTREE_CLEANUP='1')
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        prefix = self.saved(out)
        lines = out.split('\n')
        command = lines[lines.index('         to delete the saved refs once you no longer want them, run in the main '
                                    'worktree:') + 1].strip()
        self.assertEqual(command, "git for-each-ref --format='delete %%(refname)' %s | git update-ref --stdin"
                         % clean_worktrees.sh_quote(prefix + '/'))
        self.git('update-ref', 'refs/kit/saved/other/1', 'HEAD')
        ran = subprocess.run(['sh', '-c', command], cwd=self.main, env=self.env, capture_output=True, text=True)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertEqual(self.git('for-each-ref', '--format=%(refname)', 'refs/kit/'), 'refs/kit/saved/other/1')
        self.assertEqual(self.branch("it's"), "worktree-it's")

    def test_a_failed_save_keeps_it_and_deletes_nothing(self):
        path = self.worktree('done')
        loose = self.loose(path)
        self.git('update-ref', 'refs/worktree/keep', loose, cwd=path)
        (self.main / 'r.md').write_text('same\n')
        (path / 'r.md').write_text('same\n')
        out = self.run_script('--apply', SHIM='fail:update-ref', **self.shim())
        self.assertIn('stopped: cannot save what only its git directory holds: `git update-ref --stdin` failed: '
                      'fatal: refused by the shim; nothing deleted, the worktree stays', out)
        self.assertTrue((path / 'r.md').is_file())
        self.assertIn('clean_worktrees: removed 0, kept 2', out)
        self.assertRegex((self.main / '.git/kit-worktree-removals.log').read_text(),
                         r'\tintent\t[^\n]*\tsaved=refs/kit/saved/done-[^\n]*\n[^\t]*\t[^\t]*\toutcome\t[^\t]*\tkept\t'
                         r'cannot save what only its git directory holds: [^\t]*\n$')
        self.assertEqual(self.git('for-each-ref', 'refs/kit/'), '')

    def test_a_commit_held_only_by_a_worktree_ref_or_its_reflog_is_saved(self):
        for ref, holder in (('refs/worktree/keep', 'refs/worktree/keep'), ('refs/bisect/bad', 'refs/bisect/bad'),
                            ('refs/rewritten/saved', 'refs/rewritten/saved'),
                            ('refs/worktree/moved', 'logs/refs/worktree/moved')):
            with self.subTest(ref=ref):
                path = self.worktree(ref.split('/')[-1])
                loose = self.loose(path)
                self.git('update-ref', '--create-reflog', ref, loose, cwd=path)
                if holder.startswith('logs/'):
                    self.git('update-ref', ref, 'HEAD', cwd=path)  # now only its reflog names it
                out = self.run_script('--apply')
                self.assertRemoved(path, out)
                self.assertIn('=%s (%s)' % (loose[:12], holder), out)
                self.assertIn(loose, self.git('rev-list', '--glob=' + self.saved(out) + '/*'))

    def test_a_commit_only_in_the_old_id_column_of_a_reflog_is_saved(self):
        # Reproduced by a reviewer: `reflog delete` without --rewrite left the commit only as
        # the OLD id of the next entry.
        path = self.worktree('done')
        self.git('checkout', '-q', '--detach', cwd=path)
        self.git('commit', '-q', '--allow-empty', '-m', 'detached work', cwd=path)
        loose = self.git('rev-parse', 'HEAD', cwd=path)
        self.git('checkout', '-q', 'worktree-done', cwd=path)
        self.git('reflog', 'delete', 'HEAD@{1}', cwd=path)
        log = self.gitdir(path) / 'logs/HEAD'
        text = log.read_text().replace('moving from %s to' % loose, 'moving from elsewhere to')
        log.write_text(text)
        self.assertEqual(text.count(loose), 1)
        self.assertTrue(re.search(r'\n%s [0-9a-f]{40} ' % loose, text), text)
        self.assertIn('=%s (logs/HEAD)' % loose[:12], self.run_script())

    def test_any_file_of_its_git_directory_is_read_for_ids(self):
        path = self.worktree('done')
        gitdir = self.gitdir(path)
        loose = self.loose(path)
        for name, text in (('SOMETHING_HEAD', 'x %s y\n' % loose), ('ORIG_HEAD', loose + '\n'),
                           # Upper case only: git reads an id in either case.
                           ('deep/state', loose.upper() + '\n'), ('MIXED', loose[:20].upper() + loose[20:] + '\n')):
            with self.subTest(name=name):
                (gitdir / name).parent.mkdir(exist_ok=True)
                (gitdir / name).write_text(text)
                self.assertIn('=%s (%s)' % (loose[:12], name), self.run_script())
                (gitdir / name).unlink()
        # An id that names no object, one embedded in a longer hex run, and the gate's build
        # log, which may print any id: none of them is saved.
        (gitdir / 'NOTE').write_text('%s\n%sab\n%sAB\nF%s\n' % ('1' * 40, loose, loose, loose))
        (gitdir / 'check-build.log').write_text(loose + '\n')
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertNotIn('saves what', out)

    def test_a_tag_only_its_git_directory_holds_keeps_it(self):
        path = self.worktree('done')
        tag = subprocess.run(['git', 'hash-object', '-t', 'tag', '-w', '--stdin'], cwd=path, env=self.env,
                             input=('object %s\ntype commit\ntag t\ntagger t <t@example.invalid> 0 +0000\n\nt\n'
                                    % self.loose(path)).encode(), capture_output=True).stdout.decode().strip()
        (self.gitdir(path) / 'TAGGED').write_text(tag + '\n')
        self.assertKept(path, self.run_script('--apply'), '%s, a tag, is held only by its git directory (TAGGED)'
                        % tag[:12])

    def test_an_id_a_reflog_names_holds_nothing(self):
        # Reproduced by a reviewer: an id in a reflog message was counted as held. No reflog
        # holds anything: `git branch -d` deletes the branch's, and gc keeps no message.
        path = self.worktree('done')
        loose = self.loose(path)
        self.git('update-ref', 'refs/worktree/keep', loose, cwd=path)
        head = self.git('rev-parse', 'HEAD')
        with (self.main / '.git/logs/refs/heads/worktree-done').open('a') as log:
            log.write('%s %s t <t@example.invalid> 0 +0000\tmerge %s: noted\n' % (head, head, loose))
            log.write('%s %s t <t@example.invalid> 0 +0000\tcolumns\n' % (loose, head))
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertIn('=%s (refs/worktree/keep)' % loose[:12], out)
        self.assertIn(loose, self.git('rev-list', '--glob=' + self.saved(out) + '/*'))

    def test_a_commit_only_fetch_head_names_is_saved(self):
        other = self.tmp / 'other'
        self.git('clone', '-q', str(self.main), str(other))
        self.git('commit', '-q', '--allow-empty', '-m', 'fetched', cwd=other)
        fetched = self.git('rev-parse', 'HEAD', cwd=other)
        path = self.worktree('done')
        self.git('fetch', '-q', str(other), 'HEAD', cwd=path)
        self.assertIn(fetched, (self.gitdir(path) / 'FETCH_HEAD').read_text())
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertIn('=%s (FETCH_HEAD)' % fetched[:12], out)
        self.assertIn(fetched, self.git('rev-list', '--glob=' + self.saved(out) + '/*'))

    def test_a_commit_only_a_remote_tracking_ref_holds_is_saved(self):
        # A later `git fetch --prune` drops a remote-tracking ref: it holds nothing.
        path = self.worktree('done')
        loose = self.loose(path)
        self.git('update-ref', 'refs/remotes/origin/gone', loose)
        self.git('update-ref', 'refs/worktree/keep', loose, cwd=path)
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertIn(loose, self.git('rev-list', '--glob=' + self.saved(out) + '/*'))

    def test_only_the_commits_no_other_saved_one_reaches_are_pinned(self):
        path = self.worktree('done')
        one = self.loose(path)
        two = self.git('commit-tree', self.git('rev-parse', 'HEAD^{tree}', cwd=path), '-p', one, '-m', 'two', cwd=path)
        self.git('update-ref', 'refs/worktree/one', one, cwd=path)
        self.git('update-ref', 'refs/worktree/two', two, cwd=path)
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        prefix = self.saved(out)
        self.assertEqual(self.git('for-each-ref', '--format=%(refname) %(objectname)', prefix + '/'),
                         '%s/1 %s' % (prefix, two))
        self.assertIn(one, self.git('rev-list', '--glob=' + prefix + '/*'))

    def test_a_git_directory_name_git_refuses_as_a_ref_is_percent_encoded(self):
        # git names a worktree's git directory after its folder; an older git, or a hand, can
        # leave a name with a space or "..", which `update-ref` refuses: kept for ever.
        path = self.worktree('done')
        odd = self.gitdir(path).parent / 'a b..c%'
        self.gitdir(path).rename(odd)
        (path / '.git').write_text('gitdir: %s\n' % odd)
        loose = self.loose(path)
        self.git('update-ref', 'refs/worktree/keep', loose, cwd=path)
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        prefix = self.saved(out)
        self.assertTrue(prefix.startswith('refs/kit/saved/a%20b%2E%2Ec%25-'), out)
        self.assertIn(loose, self.git('rev-list', '--glob=' + prefix + '/*'))

    def test_a_long_git_directory_name_is_cut_and_told_apart_by_a_hash(self):
        # Reproduced by a reviewer: 100 times é, percent-encoded, is 600 bytes, over the 255 of
        # one path component: `update-ref` failed on every run, and it was kept for ever.
        prefixes = []
        for name, count in (('one', 100), ('two', 101)):
            path = self.worktree(name)
            odd = self.gitdir(path).parent / ('é' * count)
            self.gitdir(path).rename(odd)
            (path / '.git').write_text('gitdir: %s\n' % odd)
            loose = self.loose(path)
            self.git('update-ref', 'refs/worktree/keep', loose, cwd=path)
            out = self.run_script('--apply')
            self.assertRemoved(path, out)
            prefixes.append(self.saved(out))
            self.assertRegex(prefixes[-1], r'^refs/kit/saved/(%C3%A9){10}%C3%-[0-9a-f]{12}-\d{8}T\d{6}Z$')
            self.assertIn(loose, self.git('rev-list', '--glob=' + prefixes[-1] + '/*'))
            self.assertIn('\tgitdir=%s\t' % odd, (self.main / '.git/kit-worktree-removals.log').read_text())
        self.assertNotEqual(prefixes[0][:-17], prefixes[1][:-17])

    def test_a_tree_or_blob_id_keeps_it_with_the_honest_reason(self):
        # `rev-list --objects <tree> ^main` lists a tree main holds too: for a tree or a blob it
        # cannot tell, so neither is called "not held".
        path = self.worktree('done')
        blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], cwd=path, env=self.env, input=b'only here\n',
                              capture_output=True).stdout.decode().strip()
        for name, oid in (('BLOB', blob), ('TREE', self.git('rev-parse', 'HEAD^{tree}')),
                          ('MAINBLOB', self.git('rev-parse', 'HEAD:a'))):
            with self.subTest(name=name):
                (self.gitdir(path) / name).write_text(oid + '\n')
                self.assertKept(path, self.run_script('--apply'), '%s is a tree or blob id (%s): reachability is '
                                'checked for commits only; check and remove it by hand' % (oid[:12], name))
                (self.gitdir(path) / name).unlink()

    def test_a_git_directory_file_it_cannot_read_keeps_it(self):
        path = self.worktree('done')
        gitdir = self.gitdir(path)
        (gitdir / 'blob').write_bytes(b'ab\0cd')
        self.assertKept(path, self.run_script('--apply'), 'its git directory holds blob, a binary file')
        (gitdir / 'blob').unlink()
        os.mkfifo(gitdir / 'pipe')
        self.assertKept(path, self.run_script('--apply'), 'its git directory holds pipe, not a regular file')
        (gitdir / 'pipe').unlink()
        (gitdir / 'secret').write_text('x\n')
        for how in self.failures():
            with self.subTest(how=how):
                if how == 'injected':
                    out = self.drive(FAIL_OPEN, '/secret')
                else:
                    (gitdir / 'secret').chmod(0)  # root reads it anyway
                    try:
                        out = self.run_script('--apply')
                    finally:
                        (gitdir / 'secret').chmod(0o644)
                self.assertKept(path, out, 'cannot read secret in its git directory (Permission denied)')

    def test_another_ref_backend_or_a_worktree_config_is_kept(self):
        path = self.worktree('done')
        # Through a git that answers for it: a repository of format 0 refuses the setting.
        self.assertKept(path, self.run_script('--apply', SHIM='reftable', **self.shim()),
                        'its refs are stored by the reftable backend')
        (self.gitdir(path) / 'config.worktree').write_text('[user]\n\tname = x\n')
        self.assertKept(path, self.run_script('--apply'), 'it has its own config')
        (self.gitdir(path) / 'config.worktree').write_text('')
        self.assertRemoved(path, self.run_script('--apply'))

    # --- g: tracked content, by bytes --------------------------------------------------------

    def tracked(self, change, *reasons, name='done', flags=('--all-reasons',)):
        path = self.worktree(name)
        change(path)
        self.assertKept(path, self.run_script('--apply', *flags), *reasons)
        return path

    def test_a_staged_change_is_kept(self):
        def change(path):
            (path / 'a').write_text('staged\n')
            self.git('add', 'a', cwd=path)
        self.tracked(change, 'tracked change, staged: a', 'its index differs from its HEAD commit')

    def test_a_modified_or_deleted_file_is_kept(self):
        self.tracked(lambda path: (path / 'a').write_text('changed\n'), 'tracked change, modified: a',
                     'not byte for byte what its index records')
        self.tracked(lambda path: (path / 'a').unlink(), 'tracked change, deleted: a', 'its executable bit): a',
                     name='gone')

        def folder(path):
            (path / 'a').unlink()
            (path / 'a').mkdir()
        self.tracked(folder, 'its executable bit): a', name='folder')

        def link(path):
            (path / 'a').unlink()
            (self.tmp / 'same').write_text('a\n')
            (path / 'a').symlink_to(self.tmp / 'same')  # the same bytes, but not a regular file
        self.tracked(link, 'its executable bit): a', name='link')


    def test_a_tracked_file_reached_through_a_symlinked_folder_is_not_the_tracked_file(self):
        (self.main / 'sub').mkdir()
        (self.main / 'sub/f').write_text('f\n')
        self.git('add', 'sub/f')
        self.git('commit', '-q', '-m', 'sub')

        def change(path):
            os.rename(path / 'sub', self.tmp / 'sub')  # the same bytes, now behind a symlink
            (path / 'sub').symlink_to(self.tmp / 'sub')
        self.tracked(change, 'its executable bit): sub/f')

    def test_an_executable_swapped_for_a_symlink_to_the_same_bytes_is_kept(self):
        # A symlink carries every permission bit, so only "not a regular file" tells it apart.
        (self.main / 'run.sh').write_text('#!/bin/sh\n')
        (self.main / 'run.sh').chmod(0o755)
        self.git('add', 'run.sh')
        self.git('commit', '-q', '-m', 'run')

        def change(path):
            (path / 'run.sh').unlink()
            (self.tmp / 'run.sh').write_text('#!/bin/sh\n')
            (path / 'run.sh').symlink_to(self.tmp / 'run.sh')
        self.tracked(change, 'its executable bit): run.sh')

    def test_an_intent_to_add_is_kept(self):
        def change(path):
            (path / 'n').write_text('')
            self.git('add', '-N', 'n', cwd=path)
        self.tracked(change, 'tracked change, intent-to-add: n', flags=())

    def test_an_edit_git_s_stat_cache_hides_is_kept(self):
        # Reproduced by a reviewer: same size, mtime put back, core.checkStat=minimal and
        # core.trustctime=false: `git status` and `git worktree remove` both called it clean.
        def change(path):
            self.git('config', 'core.checkStat', 'minimal')
            self.git('config', 'core.trustctime', 'false')
            old = time.time() - 3600
            os.utime(path / 'a', (old, old))
            self.git('update-index', '--refresh', cwd=path)
            (path / 'a').write_text('b\n')
            os.utime(path / 'a', (old, old))
            self.assertEqual(self.git('status', '--porcelain', cwd=path), '')
        # `git status` with the stat settings forced back misses it too when the edit falls in
        # the second the index was refreshed in (git compares whole seconds): the bytes catch it.
        path = self.tracked(change, 'not byte for byte what its index records', flags=())
        self.assertEqual((path / 'a').read_text(), 'b\n')

    def test_a_mode_only_or_line_ending_only_change_is_kept(self):
        def mode(path):
            self.git('config', 'core.fileMode', 'false')
            (path / 'a').chmod(0o755)
            self.assertEqual(self.git('status', '--porcelain', cwd=path), '')
        self.tracked(mode, 'tracked change, modified: a', 'its executable bit): a', name='mode')
        self.git('config', '--unset', 'core.fileMode')

        def crlf(path):
            self.git('config', 'core.autocrlf', 'input')
            (path / 'a').write_bytes(b'a\r\n')
            self.git('add', 'a', cwd=path)  # the index takes it as unchanged: git converts to a\n
            self.assertEqual(self.git('status', '--porcelain', cwd=path), '')
        self.tracked(crlf, 'not byte for byte what its index records', name='crlf', flags=())

    def test_an_assume_unchanged_or_skip_worktree_edit_git_does_not_report_is_kept(self):
        for flag in ('--assume-unchanged', '--skip-worktree'):
            with self.subTest(flag=flag):
                def change(path):
                    self.git('update-index', flag, 'a', cwd=path)
                    (path / 'a').write_text('hidden from git status\n')
                self.tracked(change, 'not byte for byte what its index records', name=flag.strip('-'), flags=())

    def test_a_clean_filter_that_hides_an_edit_is_kept(self):
        (self.main / '.gitattributes').write_text('notes.txt filter=strip\n')
        (self.main / 'notes.txt').write_text('public\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'attributes')
        path = self.worktree('done')
        self.git('config', 'filter.strip.clean', "sed '/SECRET/d'")
        (path / 'notes.txt').write_text('public\nSECRET one\n')
        self.git('add', 'notes.txt', cwd=path)  # the filter strips the line: nothing to commit
        (path / 'notes.txt').write_text('public\nSECRET two\n')
        # The premise: git calls the edited file unchanged, so `git worktree remove` would delete it.
        self.assertEqual(self.git('status', '--porcelain', cwd=path), '')
        self.assertKept(path, self.run_script('--apply'), 'not byte for byte what its index records (an edit '
                        'git\'s stat cache, a filter or a line-ending conversion hides, or its executable bit): notes.txt')
        self.assertIn('SECRET two', (path / 'notes.txt').read_text())
        (path / 'notes.txt').write_text('public\n')
        self.git('add', 'notes.txt', cwd=path)
        self.assertRemoved(path, self.run_script('--apply'))

    def test_a_tracked_symlink_is_compared_by_its_text(self):
        (self.main / 'link').symlink_to('a')
        self.git('add', 'link')
        self.git('commit', '-q', '-m', 'link')
        path = self.worktree('done')
        (path / 'link').unlink()
        (path / 'link').symlink_to('elsewhere')
        self.assertKept(path, self.run_script('--apply', '--all-reasons'), 'not byte for byte what its index records'
                        ' (an edit git\'s stat cache, a filter or a line-ending conversion hides, or its executable bit): link')
        (path / 'link').unlink()
        (path / 'link').symlink_to('a')
        self.assertRemoved(path, self.run_script('--apply'))

    def test_a_submodule_or_an_unknown_index_mode_is_kept(self):
        path = self.worktree('done', merge=False)
        head = self.git('rev-parse', 'HEAD')
        self.git('update-index', '--add', '--cacheinfo', '160000,%s,sub' % head, cwd=path)
        self.git('commit', '-q', '-m', 'a submodule', cwd=path)
        self.git('merge', '-q', 'worktree-done')
        self.assertKept(path, self.run_script('--apply', '--all-reasons'), 'a submodule, whose state this script cannot judge: sub')

    # --- h: what git does not track ----------------------------------------------------------

    def test_an_untracked_unique_file_is_kept_and_named(self):
        path = self.worktree('done')
        (self.main / 'notes.md').write_text('main\n')
        (path / 'notes.md').write_text('mine\n')  # same name and size, other bytes
        (path / 'mine.md').write_text('only here\n')
        self.assertKept(path, self.run_script('--apply'),
                        'files with no identical copy in main, outside a disposable folder: mine.md, notes.md')

    def test_an_ignored_unique_file_outside_a_disposable_folder_is_kept(self):
        path = self.worktree('done')
        (path / 'build').mkdir()
        (path / 'build/out.o').write_text('object\n')
        (path / 'run.log').write_text('log\n')
        self.assertKept(path, self.run_script('--apply'), 'build/out.o, run.log',
                        'consider listing them in .claude/worktree-disposable: build')

    def test_an_identical_untracked_file_is_removed_with_the_worktree(self):
        path = self.worktree('done')
        (self.main / 'docs/reviews').mkdir(parents=True)
        (self.main / 'docs/reviews/r.md').write_bytes(b'report\n')
        (path / 'docs/reviews').mkdir(parents=True)
        (path / 'docs/reviews/r.md').write_bytes(b'report\n')
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertIn('1 identical files', out)
        self.assertIn('clean_worktrees: removed 1, kept 1, freed', out)
        self.assertEqual((self.main / 'docs/reviews/r.md').read_bytes(), b'report\n')
        # Reproduced by two reviewers: a removal that deleted an identical copy first was logged
        # partly-modified. It is removed; the copies it deleted stay listed.
        self.assertTrue((self.main / '.git/kit-worktree-removals.log').read_text().endswith(
            '\toutcome\t%s\tremoved\tdeleted=docs/reviews/r.md\n' % os.path.realpath(path)))

    def test_an_identical_copy_reached_through_a_symlink_in_main_does_not_count(self):
        path = self.worktree('done')
        (self.tmp / 'outside').mkdir()
        (self.tmp / 'outside/f').write_text('same\n')
        (self.main / 'linked').symlink_to(self.tmp / 'outside')
        (path / 'linked').mkdir()
        (path / 'linked/f').write_text('same\n')
        (self.main / 'g').symlink_to(self.tmp / 'outside/f')
        (path / 'g').write_text('same\n')
        self.assertKept(path, self.run_script('--apply'), 'no identical copy in main, outside a disposable folder: g, linked/f\n')

    def test_each_log_line_is_on_disk_before_it_is_reported(self):
        log, synced = self.tmp / 'removals.log', []
        real = os.fsync
        clean_worktrees.os.fsync = lambda fd: synced.append(os.fstat(fd).st_size) or real(fd)
        try:
            clean_worktrees.log_line({'log': os.fsencode(log), 'run': 'r'}, ['intent', 'x'])
            clean_worktrees.log_line({'log': os.fsencode(log), 'run': 'r'}, ['outcome', 'x', 'removed'])
        finally:
            clean_worktrees.os.fsync = real
        lines = log.read_bytes().split(b'\n')
        self.assertEqual(synced, [len(lines[0]) + len(lines[1]) + 2, log.stat().st_size])

    def test_the_worktree_s_own_file_seen_from_main_is_no_copy(self):
        # Reproduced by a reviewer: a worktree folder bind-mounted into main made main's "copy"
        # the worktree's own file; it was deleted as an identical copy, and both were gone. A
        # hard link is the same file without a mount; a mount inside main is not main.
        path = self.worktree('done')
        (path / 'notes').mkdir()
        (path / 'notes/x').write_text('precious\n')
        (self.main / 'notes').mkdir()
        os.link(path / 'notes/x', self.main / 'notes/x')
        self.assertKept(path, self.run_script('--apply'), 'no identical copy in main, outside a disposable folder: notes/x\n')
        self.assertEqual((path / 'notes/x').read_text(), 'precious\n')
        os.unlink(self.main / 'notes/x')
        # On real mounts, where this host lets a user make them; the cases after this one inject
        # the device and the mount table on every host.
        below = 'its copy in main is below a mount point: a mount inside main is not main: notes/x\n'
        for mount, reason in (
                ('mount --bind "$1/notes" "$2/notes"', 'no identical copy in main, outside a disposable folder: notes/x\n'),
                ('mount -t tmpfs none "$2/notes" && echo precious > "$2/notes/x"', below),
                ('mkdir "$2/t" && mount -t tmpfs none "$2/t" && echo precious > "$2/t/x" && : > "$2/notes/x" && '
                 'mount --bind "$2/t/x" "$2/notes/x"', below),
                ('mount -t tmpfs none "$2/notes" && : > "$2/notes/x" && echo precious > "$2/u" && '
                 'mount --bind "$2/u" "$2/notes/x"', below)):
            out = self.in_namespace(mount, path, self.main)
            if out is None:
                break
            with self.subTest(mount=mount):
                self.assertKept(path, out, reason)
                self.assertEqual((path / 'notes/x').read_text(), 'precious\n')

    def test_a_mount_point_inside_a_worktree_keeps_it(self):
        # Codex: a folder bound into a disposable folder from elsewhere was deleted by git's
        # recursive remove. Any mount point inside a worktree keeps it, seen by its device, or by
        # the mount table (a bind mount on the same device; Linux only).
        self.disposable('build\n')
        path = self.worktree('done')
        (path / 'build/obj').mkdir(parents=True)
        (path / 'build/obj/out.o').write_text('o\n')
        real = os.path.realpath(path)
        reason = "holds a mount point: what git would delete under it is not the worktree's: "
        self.assertKept(path, self.run_script('--apply', CLEAN_WORKTREES_MOUNTINFO=self.mountinfo(os.fsencode(real) + b'/build')),
                        reason + 'build\n')
        # Only the mount point is named, not each entry under it.
        self.assertKept(path, self.drive(FOREIGN, real + '/build/obj', real + '/build/obj/out.o'), reason + 'build/obj\n')
        external = self.tmp / 'external'
        external.mkdir()
        (external / 'precious').write_text('precious\n')
        for mount, where in (('mount --bind "$1" "$2/build"', 'build\n'),
                             ('mount -t tmpfs none "$2/build/obj" && echo o > "$2/build/obj/o"', 'build/obj\n')):
            out = self.in_namespace(mount, external, path)
            if out is None:
                break
            with self.subTest(mount=mount):
                self.assertKept(path, out, reason + where)
        self.assertEqual((external / 'precious').read_text(), 'precious\n')
        self.assertRemoved(path, self.run_script('--apply'))

    def test_a_worktree_mounted_at_its_own_folder_is_kept(self):
        # Codex and a reviewer, reproduced: a tmpfs on the worktree's folder itself; git deleted
        # what was on it, then failed. Its folder in the mount table, or on another device than
        # .claude/worktrees, keeps it.
        path = self.worktree('done')
        real = os.path.realpath(path)
        reason = "holds a mount point: what git would delete under it is not the worktree's: . (the folder itself)\n"
        self.assertKept(path, self.run_script('--apply', CLEAN_WORKTREES_MOUNTINFO=self.mountinfo(os.fsencode(real))), reason)
        self.assertKept(path, self.drive(FOREIGN, real), reason)
        self.assertRemoved(path, self.run_script('--apply'))

    def test_a_mount_point_in_its_git_directory_keeps_it(self):
        # Codex: git removes the worktree's git directory recursively too; an outside folder bound
        # at <git dir>/archive, holding text with no object id, passed and was deleted.
        path = self.worktree('done')
        gitdir = self.gitdir(path)
        (gitdir / 'archive').mkdir()
        (gitdir / 'archive/precious.txt').write_text('precious\n')
        reason = "its git directory holds a mount point: what git would delete under it is not the worktree's: "
        for where, table in (('archive\n', os.fsencode(gitdir / 'archive')), ('. (the folder itself)\n', os.fsencode(gitdir))):
            with self.subTest(table=table):
                self.assertKept(path, self.run_script('--apply', CLEAN_WORKTREES_MOUNTINFO=self.mountinfo(table)),
                                reason + where)
        for where, foreign in (('archive\n', gitdir / 'archive'), ('. (the folder itself)\n', gitdir)):
            with self.subTest(device=foreign):
                self.assertKept(path, self.drive(FOREIGN, str(foreign)), reason + where)
        external = self.tmp / 'external'
        external.mkdir()
        (external / 'precious.txt').write_text('precious\n')
        out = self.in_namespace('mount --bind "$1" "$2/archive"', external, gitdir)
        if out is not None:
            self.assertKept(path, out, reason + 'archive\n')
        self.assertEqual((external / 'precious.txt').read_text(), 'precious\n')
        # Without a mount, plain text in its git directory holds nothing, and goes with it.
        self.assertRemoved(path, self.run_script('--apply'))

    def test_the_quiet_check_does_not_walk_into_a_mount_in_its_git_directory(self):
        # Codex: the quiet check walked the git directory without the mount table, so a bind
        # mount on the same device under it was read in full before the worktree was kept.
        path = self.worktree('done')
        archive = Path(os.path.realpath(self.gitdir(path))) / 'archive'
        (archive / 'deep').mkdir(parents=True)
        (archive / 'deep/f').write_text('f\n')
        scan = ('real_scandir = os.scandir\n'
                'def scandir(path):\n'
                '    if os.fsencode(path).startswith(os.fsencode(values[0])):\n'
                '        sys.stderr.write("scanned inside the mount: %s\\n" % os.fsdecode(path))\n'
                '        os._exit(9)\n'
                '    return real_scandir(path)\n'
                'os.scandir = scandir\n')
        self.env = dict(self.env, CLEAN_WORKTREES_MOUNTINFO=self.mountinfo(os.fsencode(archive)))
        self.assertKept(path, self.drive(scan, str(archive)), "its git directory holds a mount point: what git "
                        "would delete under it is not the worktree's: archive\n")

    def test_a_mount_at_its_own_git_file_keeps_it(self):
        # A reviewer, reproduced: a mount at <worktree>/.git was skipped as git's own file; git
        # deleted the tracked files and its git directory, then failed (EBUSY).
        path = self.worktree('done')
        real = os.fsencode(os.path.realpath(path))
        self.assertKept(path, self.run_script('--apply', CLEAN_WORKTREES_MOUNTINFO=self.mountinfo(real + b'/.git')),
                        "holds a mount point: what git would delete under it is not the worktree's: .git\n")
        self.assertRemoved(path, self.run_script('--apply'))

    def test_the_walk_does_not_go_into_a_mount_point(self):
        # A reviewer: a mount is counted, never walked; a whole disk under one is not read.
        root = self.tmp / 'root'
        (root / 'disk/deep').mkdir(parents=True)
        (root / 'disk/deep/f').write_text('f\n')
        (root / 'keep').write_text('k\n')
        expected = {b'': False, b'disk': True, b'keep': False}
        seen = {rel: mount for rel, _, _, mount in clean_worktrees.walk(os.fsencode(root), {os.fsencode(root / 'disk')})}
        self.assertEqual(seen, expected)
        real = os.lstat

        def lstat(path, *a, **k):
            info = real(path, *a, **k)
            if os.fsencode(path) != os.fsencode(root / 'disk'):
                return info
            return os.stat_result(tuple(info[:2]) + (info.st_dev + 1,) + tuple(info[3:10]))
        clean_worktrees.os.lstat = lstat
        try:
            seen = {rel: mount for rel, _, _, mount in clean_worktrees.walk(os.fsencode(root))}
        finally:
            clean_worktrees.os.lstat = real
        self.assertEqual(seen, expected)

    def test_a_copy_in_main_below_a_mount_point_is_no_archive(self):
        # Codex: a sibling's disposable folder bound onto main's docs/reviews passed for the
        # archive, and both copies went. A copy at or below a mount point in main is no archive.
        path = self.worktree('done')
        for root in (self.main, path):
            (root / 'docs/reviews').mkdir(parents=True)
            (root / 'docs/reviews/r.md').write_text('report\n')
        main = os.path.realpath(self.main)
        reason = 'its copy in main is below a mount point: a mount inside main is not main: docs/reviews/r.md\n'
        for rel in ('/docs', '/docs/reviews', '/docs/reviews/r.md'):
            with self.subTest(table=rel):
                self.assertKept(path, self.run_script('--apply', CLEAN_WORKTREES_MOUNTINFO=self.mountinfo(os.fsencode(main + rel))),
                                reason)
            with self.subTest(device=rel):
                self.assertKept(path, self.drive(FOREIGN, main + rel), reason)
        # Codex's case on real mounts: a sibling's disposable build bound onto docs/reviews.
        self.disposable('build\n')
        sibling = self.worktree('sibling')
        (sibling / 'build').mkdir()
        (sibling / 'build/r.md').write_text('report\n')
        (self.main / 'docs/reviews/r.md').unlink()
        out = self.in_namespace('mount --bind "$1/build" "$2/docs/reviews"', sibling, self.main)
        if out is not None:
            self.assertKept(path, out, reason)
        self.assertEqual((path / 'docs/reviews/r.md').read_text(), 'report\n')
        (self.main / 'docs/reviews/r.md').write_text('report\n')
        self.assertRemoved(path, self.run_script('--apply'))

    def test_the_mount_table_is_read_back_to_its_bytes_and_the_unknown_refused(self):
        table = self.tmp / 'table'
        table.write_bytes(b'1 0 8:1 / / rw - ext4 /dev/root rw\n22 1 0:5 / /a\\040b\\134c\\011d\\012e rw - tmpfs none rw\n')
        self.assertEqual(clean_worktrees.mount_points(os.fsencode(table)), {b'/', b'/a b\\c\td\ne'})
        for line in (b'1 0 8:1 /\n', b'1 0 8:1 / relative rw - ext4 /dev/root rw\n'):
            with self.subTest(line=line):
                table.write_bytes(line)
                with self.assertRaisesRegex(clean_worktrees.Unproven, 'a line this script does not know'):
                    clean_worktrees.mount_points(os.fsencode(table))
        # No mount table: on Linux a bind mount could not be seen; elsewhere there is none.
        path = self.worktree('done')
        out = self.run_script('--apply', CLEAN_WORKTREES_MOUNTINFO=str(self.tmp / 'none'))
        if sys.platform.startswith('linux'):
            self.assertKept(path, out, 'no mount table %s: a bind mount could not be seen' % (self.tmp / 'none'))
        else:
            self.assertRemoved(path, out)

    def test_a_copy_inside_a_worktree_is_no_archive(self):
        # Reproduced by a reviewer: the "copy in main" of W/.claude/worktrees/a/build/r.log is
        # W's own disposable build/r.log, and of W/.claude/worktrees/b/build/r.log a sibling's:
        # both copies went, one with W, one with the sibling.
        self.disposable('build\n')
        path, sibling = self.worktree('a'), self.worktree('b')
        for root in (path, path / '.claude/worktrees/a', path / '.claude/worktrees/b', sibling):
            (root / 'build').mkdir(parents=True)
            (root / 'build/r.log').write_text('same\n')
        out = self.run_script('--apply')
        self.assertKept(path, out, 'inside .claude/worktrees of it, which this script does not judge: '
                        '.claude/worktrees/a/build/r.log, .claude/worktrees/b/build/r.log\n')
        self.assertRemoved(sibling, out)
        for rel in ('build/r.log', '.claude/worktrees/a/build/r.log', '.claude/worktrees/b/build/r.log'):
            self.assertEqual((path / rel).read_text(), 'same\n', rel)
        # Below the name check: a copy reached through main's .claude/worktrees never counts.
        main = os.fsencode(os.path.realpath(self.main))
        ctx = {'main_root': main, 'home': main + b'/.claude/worktrees'}
        (self.main / 'build').mkdir()
        (self.main / 'build/r.log').write_text('same\n')
        real = os.fsencode(os.path.realpath(path))
        self.assertTrue(clean_worktrees.copy_in(ctx, real, b'build/r.log'))
        self.assertFalse(clean_worktrees.copy_in(ctx, real, b'.claude/worktrees/a/build/r.log'))

    def test_a_disposable_folder_with_content_is_removed(self):
        self.disposable('# build output\nbuild\n')
        path = self.worktree('done')
        (path / 'app/build/obj').mkdir(parents=True)
        (path / 'app/build/obj/out.o').write_bytes(b'x' * 1000)
        out = self.run_script('--apply')
        self.assertRemoved(path, out)
        self.assertIn('1000 disposable bytes', out)
        self.assertIn('disposable_bytes=1000', (self.main / '.git/kit-worktree-removals.log').read_text())

    def test_a_disposable_path_entry_matches_only_its_own_folder(self):
        # A NAME matches a folder, never a file's own name; a PATH matches from the root only,
        # folder by folder (app/build is not app/build2).
        self.disposable('app/build\nout.o\n')
        path = self.worktree('done')
        for folder in ('app/build', 'app/build2', 'other/build', 'deep/app/build'):
            (path / folder).mkdir(parents=True)
            (path / folder / 'out.o').write_text('o\n')
        self.assertKept(path, self.run_script('--apply'),
                        'disposable folder: app/build2/out.o, deep/app/build/out.o, other/build/out.o\n')

    def test_a_name_entry_does_not_reach_below_a_place_that_holds_work(self):
        self.disposable('build\n')
        path = self.worktree('done')
        for folder in ('docs/build', '.claude/build', 'scripts/x/build', '.myagentkit/build', 'ok/build'):
            (path / folder).mkdir(parents=True)
            (path / folder / 'f').write_text('f\n')
        self.assertKept(path, self.run_script('--apply'), '.claude/build/f, .myagentkit/build/f, docs/build/f, '
                        'scripts/x/build/f\n')

    def test_disposable_matching_folder_by_folder(self):
        for rel, entries, expected in (
                (b'app/build/x', [b'app/build'], True), (b'app/build2/x', [b'app/build'], False),
                (b'app/buildx', [b'app/build'], False), (b'xapp/build/x', [b'app/build'], False),
                (b'app/build', [b'app/build'], False), (b'a/build/b/x', [b'build'], True),
                (b'build', [b'build'], False), (b'docs/build/x', [b'build'], False),
                (b'a/build/docs/x', [b'build'], True), (b'.git/build/x', [b'build'], False),
                (b'a/b/c', [b'b', b'x/y'], True), (b'a/b/c', [], False)):
            with self.subTest(rel=rel, entries=entries):
                self.assertIs(clean_worktrees.disposable(rel, entries), expected)
        # Case: a place that holds work under any spelling, an entry byte for byte (either only
        # ever keeps more).
        for rel, entries in ((b'Docs/build/x', [b'build']), (b'a/BUILD/x', [b'build']), (b'a/Build/x', [b'build']),
                             (b'App/Build/x', [b'app/build']), (b'.GIT/build/x', [b'build']),
                             # A long s folds to s (`scripts`) under casefold, not under lower.
                             (b'\xc5\xbfcripts/build/x', [b'build'])):
            with self.subTest(rel=rel, entries=entries):
                self.assertIs(clean_worktrees.disposable(rel, entries), False)

    def test_places_that_hold_work_are_folded_and_entries_exact_on_every_file_system(self):
        # Codex and a reviewer, reproduced: with a case-sensitive git directory and a checkout
        # that ignores case, a probe of the git directory compared exactly, `Docs` passed for
        # another folder than the protected `docs`, and the unique `Docs/build/report.md` went
        # as disposable `build`. No probe now: the same answer on every file system.
        self.disposable('build\ncache\n.CLAUDE/x\nDOCS\n')
        path = self.worktree('done')
        (path / 'Docs').mkdir()
        (path / 'Docs/readme').write_text('r\n')
        self.git('add', 'Docs/readme', cwd=path)
        self.git('commit', '-q', '-m', 'docs', cwd=path)
        self.git('merge', '-q', '--no-edit', 'worktree-done', KIT_NO_WORKTREE_CLEANUP='1')
        for rel in ('Docs/build/report.md', '.Claude/Worktrees/x/f', 'CACHE/f', 'x/Build/o'):
            (path / rel).parent.mkdir(parents=True, exist_ok=True)
            (path / rel).write_text('unique\n')
        out = self.run_script('--apply')
        self.assertKept(path, out, 'refused .claude/worktree-disposable line .CLAUDE/x (empty',
                        'refused .claude/worktree-disposable line DOCS (empty',
                        'inside .claude/worktrees of it, which this script does not judge: .Claude/Worktrees/x/f\n',
                        'files with no identical copy in main, outside a disposable folder: CACHE/f, '
                        'Docs/build/report.md, x/Build/o\n')
        self.assertNotIn('untracked and not ignored inside a disposable folder', out)
        self.assertEqual((path / 'Docs/build/report.md').read_text(), 'unique\n')

    def test_untracked_unignored_content_in_a_disposable_folder_is_kept(self):
        self.disposable('cache\n')
        path = self.worktree('done')
        (path / 'cache').mkdir()
        (path / 'cache/f').write_text('f\n')
        self.assertKept(path, self.run_script('--apply'),
                        'untracked and not ignored inside a disposable folder (`git worktree remove` refuses them')

    def test_a_refused_disposable_entry_counts_for_nothing(self):
        self.disposable('docs\n/abs\n../up\nok/../docs\n.claude\nscripts/\na//b\n./c\n')
        path = self.worktree('done')
        (path / 'docs').mkdir()
        (path / 'docs/notes.md').write_text('work\n')
        out = self.run_script('--apply')
        self.assertKept(path, out, 'disposable folder: docs/notes.md')
        for entry in ('docs', '/abs', '../up', 'ok/../docs', '.claude', 'scripts/', 'a//b', './c'):
            self.assertIn('refused .claude/worktree-disposable line %s (empty, absolute' % entry, out)

    def test_a_tracked_file_under_another_name_is_kept_and_never_deleted(self):
        # Reproduced by a reviewer on a case-insensitive file system (macOS): tracked `a` renamed
        # `A` passed every check by its old name; `A` was then deleted as main's identical copy,
        # and git refused the removal of a worktree now missing a tracked file.
        path = self.worktree('done')
        (self.tmp / 'probe').write_text('')
        if (self.tmp / 'PROBE').exists():
            os.rename(path / 'a', path / 'A')
            how = 'real: a case-only rename, this file system ignores case'
        else:
            os.link(path / 'a', path / 'A')
            (self.main / 'A').write_text('a\n')
            how = 'emulated: a hard link to the tracked file, this file system is case-sensitive'
        sys.stderr.write('\n[case alias on %s] %s\n' % (sys.platform, how))
        out = self.run_script('--apply', '--all-reasons')
        self.assertKept(path, out, 'a case alias of a tracked file, or another link to one (the same file on disk), '
                        'under a name the index does not hold: A\n')
        self.assertNotIn('identical files', out)
        self.assertTrue((path / 'A').is_file())

    def test_every_printed_name_reads_back_to_its_bytes(self):
        def back(text):
            parts = re.split(r'(\\\\|\\n|\\x[0-9a-f]{2})', text)
            return b''.join((b'\\' if p == '\\\\' else b'\n' if p == '\\n' else bytes([int(p[2:], 16)]))
                            if i % 2 else p.encode() for i, p in enumerate(parts))
        names = ([bytes([b]) for b in range(256)] + ['café \u0085x\t'.encode(), b'a\\nb', b'\\\\x41',
                 b'new\nline', b'new\\nline', b'bad\xffbyte', b'bad\\xffbyte', b'caf\xc3\xa9\xe9'])
        shown = [clean_worktrees.show(name) for name in names]
        for name, text in zip(names, shown):
            with self.subTest(name=name):
                self.assertEqual(back(text), name)
                self.assertNotIn('\n', text)
                self.assertTrue(text.isprintable(), text)
        self.assertEqual(len(set(shown)), len(names))

    def test_a_symlink_is_kept(self):
        path = self.worktree('done')
        (path / 'link').symlink_to('a')
        self.assertKept(path, self.run_script('--apply'), 'not a regular file (a symlink, FIFO, socket, device or '
                        'nested repository), outside a disposable folder: link')

    def test_a_fifo_git_does_not_list_is_kept(self):
        path = self.worktree('done')
        os.mkfifo(path / 'pipe')
        self.assertKept(path, self.run_script('--apply'), 'outside a disposable folder: pipe')

    def test_a_nested_repository_is_kept(self):
        path = self.worktree('done')
        self.git('init', '-q', str(path / 'nested'))
        self.assertKept(path, self.run_script('--apply'), 'nested/.git/')

    def test_file_names_with_a_space_a_newline_and_a_non_utf8_byte(self):
        names = [b'with space', b'new\nline', b'bad\xffbyte']
        try:
            (self.tmp / os.fsdecode(b'bad\xffbyte')).write_bytes(b'')
        except OSError:  # a file system that stores names as UTF-8 only (APFS) refuses it
            names.pop()
        done, kept = self.worktree('done'), self.worktree('kept')
        for name in names:
            for root in (self.main, done):
                Path(os.fsdecode(bytes(root) + b'/' + name)).write_bytes(b'same\n')
            Path(os.fsdecode(bytes(kept) + b'/' + name)).write_bytes(b'unique\n')
        out = self.run_script('--apply')
        self.assertRemoved(done, out)
        self.assertIn('%d identical files' % len(names), out)
        self.assertKept(kept, out, 'new\\nline', 'with space')
        if len(names) == 3:
            self.assertIn('bad\\xffbyte', out)
        for name in names:
            self.assertTrue(os.path.lexists(bytes(self.main) + b'/' + name))

    def test_the_first_reason_stops_the_audit_and_all_reasons_runs_every_check(self):
        path = self.worktree('done', merge=False)
        (path / 'mine.md').write_text('only here\n')
        out = self.run_script('--apply')
        self.assertKept(path, out, 'its branch is not merged')
        self.assertNotIn('mine.md', out)
        self.assertKept(path, self.run_script('--all-reasons'), 'its branch is not merged', 'mine.md')

    # --- output git never prints, and a git that fails --------------------------------------

    def shim(self):
        shims = self.tmp / 'shim'
        if not shims.is_dir():
            shims.mkdir()
            (shims / 'git').write_text(SHIM)
            (shims / 'git').chmod(0o755)
        return dict(PATH=str(shims) + os.pathsep + self.env['PATH'], REAL_GIT=shutil.which('git', path=self.env['PATH']))

    def test_unknown_output_or_a_failing_git_keeps(self):
        path = self.worktree('done')
        for mode, reason in (('status', 'not proven: `git status` printed an entry this script does not know: Z something new'),
                             ('list', '`git worktree list` printed a field this script does not know: frobbed'),
                             ('fail:merge-base', 'not proven: `git merge-base --is-ancestor'),
                             ('fail:rev-list', 'not proven: `git rev-list --objects --stdin` failed: fatal: refused by the shim'),
                             ('fail:--batch-check=%(objectname) %(objecttype)', 'not proven: `git cat-file --batch-check'),
                             ('fail:--show-object-format', 'not proven: `git rev-parse --show-object-format` failed'),
                             ('format', "not proven: b'sha3'"),
                             ('fail:--batch', 'not proven: `git cat-file --batch` printed  for '),
                             ('fail:ls-files', 'not proven: `git ls-files'),
                             ('fail:diff-index', 'not proven: `git -c core.checkStat=default'),
                             ('fail:--absolute-git-dir', 'not proven: `git rev-parse --absolute-git-dir` failed'),
                             ('fail:remove', 'stopped: git refused to remove it: fatal: refused by the shim')):
            with self.subTest(mode=mode):
                out = self.run_script('--apply', SHIM=mode, code=int(mode == 'fail:remove'), **self.shim())
                if mode == 'fail:remove':
                    self.assertIn('POSSIBLY MODIFIED', out)
                    self.assertIn("git -C '%s' restore -- ." % os.path.realpath(path), out)
                    out = out.replace('remove .claude/worktrees/done', 'keep   .claude/worktrees/done')
                    self.assertNotIn('git worktree add', out)
                self.assertKept(path, out, reason)

    def test_a_git_dir_in_the_environment_does_not_hide_a_worktrees_own_index(self):
        # A hook in a linked worktree runs with GIT_DIR set. Inherited, it made `git -C <worktree>`
        # read main's index, where a deletion staged in the worktree does not exist.
        path = self.worktree('done')
        self.git('rm', '-q', '--cached', 'a', cwd=path)
        out = self.run_script('--apply', GIT_DIR=str(self.main / '.git'))
        self.assertKept(path, out, 'tracked change, staged: a')

    # --- the hook --------------------------------------------------------------------------------

    def hooked(self, script=True):
        """main with the hook, the script and the list committed, so every worktree carries them too."""
        (self.main / '.githooks').mkdir()
        shutil.copy(HOOK, self.main / '.githooks/post-merge')
        if script:
            (self.main / 'scripts').mkdir()
            for name in ('clean_worktrees.sh', 'clean_worktrees.py'):
                shutil.copy(SCRIPTS / name, self.main / 'scripts' / name)
            self.disposable('')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'hook')
        self.git('config', 'core.hooksPath', '.githooks')

    def test_the_hook_cleans_after_a_merge_in_the_main_worktree_and_prints_little(self):
        self.hooked()
        path = self.worktree('done', merge=False)
        kept = self.worktree('kept', merge=False)
        out = self.merge_with_hook('worktree-done')
        # git hands a hook's output to stderr; the hook runs the real process scan.
        self.assertRemoved(path, out)
        self.assertTrue(kept.is_dir())
        self.assertNotIn('keep   ', out)
        self.assertIn('clean_worktrees: removed 1, kept 2, freed', out)
        self.assertIn('; the reasons: scripts/clean_worktrees.sh', out)
        out = self.merge_with_hook('worktree-kept')
        lines = [line for line in out.split('\n') if 'clean_worktrees' in line]
        expected = ('processes could not be inspected', 'removed 1, kept 1',
                    'branches kept, their worktrees removed: worktree-kept', 'to delete merged branches yourself')
        self.assertEqual(len(lines), len(expected), out)
        for line, part in zip(lines, expected):
            self.assertIn(part, line, out)

    def test_the_hook_prints_one_line_when_nothing_is_removed(self):
        self.hooked()
        self.worktree('fresh', commit=False, merge=False)
        self.git('checkout', '-q', '-b', 'side')
        self.git('commit', '-q', '--allow-empty', '-m', 'side')
        self.git('checkout', '-q', 'main')
        out = self.merge_with_hook('side')
        lines = [line for line in out.split('\n') if line.startswith(('clean_worktrees', 'keep', 'remove', ' '))]
        self.assertEqual(len(lines), 1, out)
        self.assertTrue(lines[0].startswith('clean_worktrees: removed 0, kept 2'), out)

    def test_the_hook_without_the_overlay_says_so_once(self):
        self.hooked(script=False)
        for count in (1, 0):
            self.git('checkout', '-q', '-b', 'side%d' % count)
            self.git('commit', '-q', '--allow-empty', '-m', 'side')
            self.git('checkout', '-q', 'main')
            out = self.merge_with_hook('side%d' % count)
            self.assertEqual(out.count('post-merge: worktree clean-up is not installed'), count, out)

    def test_the_hook_says_once_that_git_is_too_old(self):
        # Below 2.36 git has no `worktree list --porcelain -z`: the script stopped with an
        # error after every merge.
        self.hooked()
        path = self.worktree('done')
        for count in (1, 0):
            run = subprocess.run(['sh', '.githooks/post-merge'], cwd=self.main, capture_output=True, text=True,
                                 env=dict(self.env, SHIM='version', **self.shim()))
            self.assertEqual(run.returncode, 0)
            self.assertEqual(run.stdout + run.stderr, count * (
                'post-merge: worktree clean-up needs git 2.36 or newer, and this is git 2.35.8; finished '
                'worktrees stay. Said once.\n'))
        self.assertTrue(path.is_dir())

    def test_the_hook_does_nothing_after_a_merge_inside_a_linked_worktree(self):
        self.hooked()
        finished = self.worktree('finished')
        worker = self.worktree('worker', merge=False)
        self.git('commit', '-q', '--allow-empty', '-m', 'main moved')
        out = self.merge_with_hook('main', cwd=worker)
        self.assertNotIn('clean_worktrees', out)
        self.assertTrue(finished.is_dir())
        self.assertIn('remove .claude/worktrees/finished', self.run_script())

    def test_the_off_switch_stops_the_hook(self):
        self.hooked()
        path = self.worktree('done', merge=False)
        out = self.merge_with_hook('worktree-done', KIT_NO_WORKTREE_CLEANUP='1')
        self.assertTrue(path.is_dir())
        self.assertNotIn('clean_worktrees', out)

    def test_a_failing_script_leaves_the_merge_complete(self):
        self.hooked()
        path = self.worktree('done', merge=False)
        (self.main / 'scripts/clean_worktrees.sh').write_text('#!/bin/sh\nexit 3\n')
        out = self.merge_with_hook('worktree-done')
        self.assertIn('post-merge: scripts/clean_worktrees.sh stopped with an error', out)
        self.assertEqual(self.git('rev-parse', 'HEAD^2'), self.git('rev-parse', 'worktree-done'))
        self.assertTrue(path.is_dir())

    def test_bootstrap_installs_the_script_the_list_and_the_hook(self):
        project = self.tmp / 'project'
        result = subprocess.run(['sh', str(ROOT / 'bootstrap.sh'), str(project), '--overlay', 'claude-code'],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for rel in ('scripts/clean_worktrees.sh', '.githooks/post-merge'):
            self.assertTrue(os.access(project / rel, os.X_OK), rel)
        for rel in ('scripts/clean_worktrees.py', '.claude/worktree-disposable'):
            self.assertTrue((project / rel).is_file(), rel)
        for rel in ('scripts/clean_worktrees.sh', 'scripts/clean_worktrees.py'):
            self.assertRegex((project / rel).read_text().split('\n')[1], r'^# KIT-OWNED: ', rel)


if __name__ == '__main__':
    unittest.main()
