"""The shipped check.sh in a minimal configured project: scan list, lock and re-execution."""
import fcntl
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Assembled, never literal: the kit's own files carry no unfilled marker.
MARKER = '{{' + 'GATE_TEST_MARKER}}'
GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid']


def make_project(path):
    """A project the gate passes: every marker filled, the build is $GATE_TEST_BUILD."""
    (path / 'scripts').mkdir(parents=True)
    (path / 'docs').mkdir()
    text = (ROOT / 'core/scripts/check.sh').read_text()
    text = text.replace('{{TOOLCHAIN_PATH_SETUP}}', '').replace('{{BUILD_TEST_COMMAND}}',
                                                                'sh $GATE_TEST_BUILD')
    (path / 'scripts/check.sh').write_text(re.sub(r'\{\{[A-Z0-9_]+\}\}', 'fixture', text))
    (path / 'scripts/boundary_checks.sh').write_text('# The fixture has no boundaries.\n')
    (path / 'docs/STATE.md').write_text('# STATE\n\n## Active work\n')
    (path / 'docs/PROJECT.md').write_text('# PROJECT\n\n## Contents\n')
    subprocess.run(['git', 'init', '-q', str(path)], check=True)


def gate(cwd, build, timeout=60, args=(), pass_fds=(), **extra):
    """Run the gate in its own session; on timeout kill the whole session and return None."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('GATE_', 'BOUNDARY_')) and k != 'CDPATH'}
    env.update(GATE_TEST_BUILD=str(build), **extra)
    proc = subprocess.Popen(['sh', 'scripts/check.sh', *args], cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True, pass_fds=pass_fds)
    try:
        out = proc.communicate(timeout=timeout)[0]
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        return None, proc.communicate()[0]
    return proc.returncode, out


class CheckGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / 'project'
        make_project(self.project)
        self.build = self.tmp / 'build.sh'
        self.build.write_text('true\n')
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 0, out)

    def test_a_symlink_is_never_followed(self):
        # Git tracks a symlink's link text, never its target. A link to an existing file
        # outside the tree was followed by grep: its lines leaked into the scan, and a link
        # to a FIFO hung the gate.
        outside = self.tmp / 'outside'
        outside.mkdir()
        (outside / 'secret.md').write_text('outside the tree: ' + MARKER + '\n')
        os.mkfifo(outside / 'fifo')
        (self.project / 'ext-file').symlink_to(outside / 'secret.md')
        (self.project / 'ext-fifo').symlink_to(outside / 'fifo')
        try:
            code, out = gate(self.project, self.build, timeout=30)
        finally:
            # A grep left blocked on the FIFO's open gets end-of-file and exits.
            try:
                os.close(os.open(outside / 'fifo', os.O_WRONLY | os.O_NONBLOCK))
            except OSError:
                pass
        self.assertIsNotNone(code, 'the gate followed a symlink to a FIFO and hung:\n' + out)
        self.assertEqual(code, 0, out)
        self.assertNotIn('outside the tree', out)

    def test_a_path_that_is_not_a_regular_file_is_named(self):
        # A tracked file replaced by a FIFO hung grep; replaced by a directory it ended in
        # "a scanner failed to run". Each fails under its own name instead.
        for name, make in (('was-file-now-fifo', os.mkfifo), ('was-file-now-dir', os.mkdir)):
            with self.subTest(name=name):
                path = self.project / name
                path.write_text('tracked\n')
                subprocess.run(['git', 'add', name], cwd=self.project, check=True)
                path.unlink()
                make(path)
                try:
                    code, out = gate(self.project, self.build, timeout=30)
                finally:
                    subprocess.run(['git', 'update-index', '--force-remove', name], cwd=self.project,
                                   check=True)
                    path.rmdir() if path.is_dir() else path.unlink()
                self.assertIsNotNone(code, 'the gate hung on ' + name + ':\n' + out)
                self.assertEqual(code, 1, out)
                self.assertIn('FAIL [scan]: ' + name + ' is not a regular file', out)
                self.assertNotIn('a scanner failed to run', out)

    def test_a_submodule_is_skipped_by_name(self):
        # A gitlink is a tracked directory: grep exited 2 on it, and a project with a
        # submodule could never pass. Its files are another repository's: nothing inside is
        # scanned, the marker below included. An untracked repository inside the tree is
        # listed by git as "nested/" and is the same case.
        for name, track in (('vendor/lib', True), ('nested', False)):
            with self.subTest(name=name):
                inner = self.project / name
                subprocess.run(['git', 'init', '-q', str(inner)], check=True)
                (inner / 'inside.md').write_text(MARKER + '\n')
                subprocess.run(GIT + ['add', 'inside.md'], cwd=inner, check=True)
                subprocess.run(GIT + ['commit', '-q', '-m', 'inner'], cwd=inner, check=True)
                if track:
                    subprocess.run(GIT + ['add', name], cwd=self.project, check=True,
                                   capture_output=True)
                    staged = subprocess.run(['git', 'ls-files', '-s', name], cwd=self.project,
                                            capture_output=True, text=True, check=True).stdout
                    self.assertTrue(staged.startswith('160000 '), staged)
                code, out = gate(self.project, self.build)
                self.assertEqual(code, 0, out)
                self.assertIn('NOTE [scan]: skipped ' + name, out)
                self.assertNotIn('a scanner failed to run', out)

    def test_a_marker_that_does_not_name_the_live_holder_is_refused(self):
        # A process the gate's build starts inherits the lock's descriptor, so the descriptor
        # proof alone accepts it; only the marker check (it must be the holder's pid in the
        # lock file) keeps a stray GATE_SELFTEST_NESTED from turning on the seams there.
        self.build.write_text('GATE_SELFTEST_NESTED=1 GATE_BUILD_CMD_OVERRIDE=true sh scripts/check.sh\n')
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [env]: GATE_BUILD_CMD_OVERRIDE is set', out)

    def test_a_symlinked_scripts_directory_runs_the_gate_in_the_project(self):
        # The gate re-executed itself by its physical path: with scripts/ a symlink into a
        # shared tree, it then checked and built that tree instead of the project.
        shared = self.tmp / 'shared'
        (self.project / 'scripts').rename(shared)
        (self.project / 'scripts').symlink_to(shared)
        where = self.tmp / 'where'
        self.build.write_text('pwd -P > %s\n' % where)
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 0, out)
        self.assertEqual(where.read_text().strip(), str(self.project.resolve()))

    def test_python_without_fcntl_fails_the_lock_by_name(self):
        # Native Windows Python has no fcntl: the gate died with a traceback, read as a
        # failed gate. It names the cause instead, on both paths that take or probe the lock.
        # The lock programs run isolated (python3 -I), so a sitecustomize.py on PYTHONPATH no
        # longer reaches them: a python3 on PATH takes fcntl away inside each -c program instead.
        stub = self.tmp / 'no-fcntl'
        stub.mkdir()
        (stub / 'python3').write_text(
            '#!%s\nimport os, sys\nargs = sys.argv[1:]\n'
            'if "-c" in args:\n'
            '    at = args.index("-c") + 1\n'
            '    args[at] = "import sys\\nsys.modules[\'fcntl\'] = None\\n" + args[at]\n'
            'os.execv(%r, [%r] + args)\n' % (sys.executable, sys.executable, sys.executable))
        (stub / 'python3').chmod(0o755)
        lock = subprocess.run(['git', 'rev-parse', '--git-path', 'check.lock'], cwd=self.project,
                              capture_output=True, text=True, check=True).stdout.strip()
        lock = str((self.project / lock).resolve())
        for extra in ({}, {'GATE_LOCK_HELD': lock, 'GATE_LOCK_FD': '0'}):
            with self.subTest(extra=extra):
                code, out = gate(self.project, self.build, PATH=str(stub) + os.pathsep + os.environ['PATH'],
                                 **extra)
                self.assertEqual(code, 1, out)
                self.assertIn('FAIL [lock]: python3 has no fcntl module', out)
                self.assertNotIn('Traceback', out)
                self.assertNotIn('FAIL [env]', out)

    def test_a_held_lock_says_how_to_find_its_holder(self):
        # A build server the build command left running holds the lock for its whole idle
        # life, and the commit hook waits without bound: the NOTE names how to find it.
        lock = subprocess.run(['git', 'rev-parse', '--git-path', 'check.lock'], cwd=self.project,
                              capture_output=True, text=True, check=True).stdout.strip()
        lock = (self.project / lock).resolve()
        with open(lock, 'a') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            code, out = gate(self.project, self.build, GATE_LOCK_WAIT='1')
        self.assertEqual(code, 75, out)
        self.assertIn('fuser -v %s' % lock, out)
        self.assertIn('lsof %s' % lock, out)

    def lock_path(self):
        lock = subprocess.run(['git', 'rev-parse', '--git-path', 'check.lock'], cwd=self.project,
                              capture_output=True, text=True, check=True).stdout.strip()
        return (self.project / lock).resolve()

    def test_a_descriptor_open_on_another_file_is_not_the_lock(self):
        # GATE_LOCK_FD must be open on this checkout's lock file: a descriptor on any other
        # file takes its own flock at once, and with the lock held by another gate and the
        # marker copied, the seams then turned a red build green.
        lock = self.lock_path()
        self.build.write_text('false\n')
        with open(lock, 'a') as held, open(self.tmp / 'another-file', 'w') as other:
            fcntl.flock(held, fcntl.LOCK_EX)
            held.truncate(0)
            held.write(str(os.getpid()))
            held.flush()
            code, out = gate(self.project, self.build, pass_fds=(other.fileno(),),
                             GATE_LOCK_HELD=str(lock), GATE_LOCK_FD=str(other.fileno()),
                             GATE_SELFTEST_NESTED=str(os.getpid()), GATE_BUILD_CMD_OVERRIDE='true')
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL [env]: GATE_LOCK_HELD names this checkout's lock, but this run did not inherit", out)

    def test_a_link_text_that_cannot_be_read_fails_the_gate(self):
        # A symlink whose link text readlink could not read was named, and the gate passed
        # without scanning what git tracks for it.
        shim = self.tmp / 'shim'
        shim.mkdir()
        (shim / 'readlink').write_text('#!/bin/sh\nexit 1\n')
        (shim / 'readlink').chmod(0o755)
        (self.project / 'a-link').symlink_to('target.md')
        subprocess.run(['git', 'add', 'a-link'], cwd=self.project, check=True)
        code, out = gate(self.project, self.build,
                         PATH=str(shim) + os.pathsep + os.environ['PATH'])
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [scan]: cannot read the link text of the symlink a-link.', out)

    def selftest_ready(self):
        """The fixture project with what --self-test needs: hooks, review stub, rule line."""
        project = self.project
        shutil.copytree(ROOT / 'core/.githooks', project / '.githooks')
        (project / 'scripts/check.sh').chmod(0o755)
        (project / 'scripts/review.sh').write_text("echo 'REVIEW SELF-TEST: PASS'\n")
        (project / 'scripts/boundary_selftests.sh').write_text('# The fixture has no boundaries.\n')
        (project / 'AGENTS.md').write_text('- **No AI attribution in git.**\n')
        return project

    def test_the_self_test_never_writes_the_callers_index(self):
        # Inside a hook git exports GIT_INDEX_FILE. The self-test's throwaway repositories
        # inherited it, and their `git add -A` replaced the caller's staged content.
        project = self.selftest_ready()
        (project / 'staged.md').write_text('staged\n')
        subprocess.run(['git', 'add', 'staged.md'], cwd=project, check=True)
        staged = lambda: subprocess.run(['git', 'diff', '--cached', '--name-only'], cwd=project,
                                        capture_output=True, text=True, check=True).stdout
        before = staged()
        index = self.tmp / 'caller-index'
        shutil.copyfile(project / '.git/index', index)
        copy = index.read_bytes()
        code, out = gate(project, self.build, timeout=300, args=('--self-test',), GIT_INDEX_FILE=str(index))
        self.assertEqual(code, 0, out)
        self.assertEqual(index.read_bytes(), copy, 'the self-test wrote the index GIT_INDEX_FILE names')
        self.assertEqual(staged(), before)

    def test_the_self_test_reads_its_own_history_under_an_exported_git_dir(self):
        # An exported GIT_DIR sent the synthetic-history readers to the caller's repository,
        # which has no `Done: K4`: the closed-task cases failed on a green project.
        project = self.selftest_ready()
        code, out = gate(project, self.build, timeout=300, args=('--self-test',),
                         GIT_DIR=str(project / '.git'))
        self.assertEqual(code, 0, out)

    def test_the_off_switch_passes_its_own_self_test(self):
        # docs_only_skip_build=0 runs the build on a documentation-only commit; the self-test
        # demanded the skipped build anyway, so a correctly configured project could not pass.
        project = self.selftest_ready()
        script = project / 'scripts/check.sh'
        script.write_text(script.read_text().replace('\ndocs_only_skip_build=1\n', '\ndocs_only_skip_build=0\n'))
        code, out = gate(project, self.build, timeout=300, args=('--self-test',))
        self.assertEqual(code, 0, out)
        self.assertIn('ok   — docs_only_skip_build=0: a commit of two documents runs the build', out)

    def test_the_self_tests_hook_and_build_log_cases_go_red(self):
        # The self-test's own cases for a missing hook, a hook that passes a red gate, a
        # commit-msg hook that passes an AI trailer and a build log that is not kept could
        # each be deleted, and every kit test stayed green. Here each meets its failure.
        project = self.selftest_ready()
        code, out = gate(project, self.build, timeout=300, args=('--self-test',))
        self.assertEqual(code, 0, out)
        self.assertIn('SELF-TEST: PASS', out)
        (project / '.githooks/pre-merge-commit').unlink()
        (project / '.githooks/pre-commit').write_text('exit 0\n')
        (project / '.githooks/commit-msg').write_text('exit 0\n')
        text = (project / 'scripts/check.sh').read_text()
        kept = '*) build_log="${lock_path%.lock}-build.log" ;;'
        self.assertIn(kept, text)
        (project / 'scripts/check.sh').write_text(text.replace(kept, '*) build_log=$(mktemp) ;;'))
        code, out = gate(project, self.build, timeout=300, args=('--self-test',))
        self.assertEqual(code, 1, out)
        for line in ('FAIL — .githooks/pre-merge-commit is missing',
                     'FAIL — .githooks/pre-commit exited 0 while the gate was RED',
                     'FAIL — commit-msg hook accepted an AI co-author trailer',
                     'FAIL — commit-msg hook accepted Done: K4 while the staged STATE.md names K4 (rule line present)',
                     'FAIL — commit-msg hook accepted Done: K4 while the staged STATE.md names K4 (rule line absent)',
                     'FAIL — a build failure was not named, lost its diagnostic chain, left no full log'):
            self.assertIn(line, out)
        self.assertIn('SELF-TEST: FAIL', out)

    def test_a_task_a_done_trailer_closed_fails_the_state_check_by_name(self):
        # setUp already ran the gate green with no commit at all.
        git = lambda *args: subprocess.run(GIT + ['-c', 'core.hooksPath=/dev/null', *args], cwd=self.project,
                                           check=True, capture_output=True, text=True).stdout
        git('add', '-A')
        git('commit', '-q', '-m', 'close K4', '-m', 'Done: K4')
        closer = git('log', '-1', '--format=%h').strip()
        state = self.project / 'docs/STATE.md'
        for text in ('- K4b: another task\n', '- K4 sounds done\n'):
            state.write_text('# STATE\n\n## Active work\n' + text)
            code, out = gate(self.project, self.build)
            if 'K4b' in text:
                self.assertEqual(code, 0, out)
            else:
                self.assertEqual(code, 1, out)
                self.assertIn('FAIL [state]: docs/STATE.md:4 names K4, which commit %s closed' % closer, out)
        state.write_text('# STATE\n\n## Active work\n')
        (self.project / 'docs/BACKLOG.md').write_text('- K4 again\n')
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [state]: docs/BACKLOG.md:1 names K4', out)
        # A shallow clone sees only what it holds, and says so.
        (self.project / 'docs/BACKLOG.md').unlink()
        git('add', '-A')
        git('commit', '-q', '--allow-empty', '-m', 'second')
        clone = self.tmp / 'clone'
        subprocess.run(['git', 'clone', '-q', '--depth', '1', 'file://%s' % self.project, str(clone)],
                       check=True, capture_output=True)
        (clone / 'docs/STATE.md').write_text('# STATE\n\n## Active work\n- K4 is only in the history\n')
        code, out = gate(clone, self.build)
        self.assertEqual(code, 0, out)
        self.assertIn('NOTE [state]: a shallow clone', out)

    def test_a_done_id_closes_its_task_in_any_case(self):
        # `Done: k4` closed nothing while STATE.md named K4: ids are case-insensitive.
        git = lambda *args: subprocess.run(GIT + ['-c', 'core.hooksPath=/dev/null', *args], cwd=self.project,
                                           check=True, capture_output=True, text=True).stdout
        git('add', '-A')
        git('commit', '-q', '-m', 'close k4', '-m', 'Done: k4')
        closer = git('log', '-1', '--format=%h').strip()
        (self.project / 'docs/STATE.md').write_text('# STATE\n\n## Active work\n- K4 sounds done\n')
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL [state]: docs/STATE.md:4 names K4, which commit %s closed (Done: k4)' % closer, out)

    def test_the_hook_and_the_gate_close_the_same_ids(self):
        # One grammar: a Done: value, trimmed, is exactly one id; git unfolds a folded value
        # and matches the key in any case. The same messages go to the hook and to the gate.
        shutil.copytree(ROOT / 'core/.githooks', self.project / '.githooks')
        git = lambda *args: subprocess.run(GIT + ['-c', 'core.hooksPath=/dev/null', *args], cwd=self.project,
                                           check=True, capture_output=True, text=True).stdout
        ids = ['K%d' % n for n in range(1, 13)]
        state = self.project / 'docs/STATE.md'
        state.write_text('# STATE\n\n## Active work\n' + ''.join('- %s\n' % i for i in ids))
        git('add', '-A')
        trailers = ['Done: K1 K2', 'Done: K3, K4', 'Done:', 'Done:   ', 'Done: K5\n  K6',
                    'Done:\n  K7', 'done: K8', 'DONE: K9', 'Done: K10']
        msg = self.tmp / 'msg'
        hook, commits = {}, {}
        for trailer in trailers:
            msg.write_text('m\n\n' + trailer + '\n')
            out = subprocess.run(['sh', '.githooks/commit-msg', str(msg)], cwd=self.project,
                                 capture_output=True, text=True).stderr
            hook[trailer] = set(re.findall(r'closes (\S+) but', out))
            git('commit', '-q', '--allow-empty', '-F', str(msg))
            commits[git('log', '-1', '--format=%h').strip()] = trailer
        # A bad value next to a good one: the good one still closes its id.
        git('commit', '-q', '--allow-empty', '-m', 'm', '-m', 'Done: K11\nDone: K12 x')
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 1, out)
        closed = {}
        for name, commit in re.findall(r'names (\S+), which commit (\S+) closed', out):
            closed.setdefault(commits.get(commit, 'mixed'), set()).add(name)
        for trailer in trailers:
            self.assertEqual(hook[trailer], closed.get(trailer, set()), trailer + '\n' + out)
        self.assertEqual(closed['mixed'], {'K11'}, out)
        for value in ('K1 K2', 'K3, K4', '', 'K5 K6', 'K12 x'):
            self.assertIn('"Done: %s", which is not one task id' % value, out)

    def test_the_templates_name_no_id_the_docs_close(self):
        # The state templates' own prose named K4, so a project that kept it could not close
        # its real K4. Every id WORKFLOW.md's "Task ids" uses as an example is closed here.
        text = (ROOT / 'core/docs/WORKFLOW.md').read_text()
        section = text[text.index('## Task ids'):text.index('## Task sizing')]
        ids = sorted({w for w in re.split(r'[^A-Za-z0-9_-]+', section)
                      if re.fullmatch(r'[A-Za-z][A-Za-z0-9]*(-[A-Za-z0-9]+)?', w) and re.search(r'[0-9]', w)})
        self.assertIn('K4', ids)
        shutil.copytree(ROOT / 'core/.githooks', self.project / '.githooks')
        for name in ('STATE.md', 'BACKLOG.md'):
            template = (ROOT / 'core/docs' / name).read_text()
            (self.project / 'docs' / name).write_text(re.sub(r'\{\{[A-Z0-9_]+\}\}', 'fixture', template))
        msg = self.tmp / 'msg'
        msg.write_text('close the examples\n\n' + ''.join('Done: %s\n' % i for i in ids))
        subprocess.run(['git', 'add', '-A'], cwd=self.project, check=True)
        hook = subprocess.run(['sh', '.githooks/commit-msg', str(msg)], cwd=self.project,
                              capture_output=True, text=True)
        self.assertEqual(hook.returncode, 0, hook.stderr)
        subprocess.run(GIT + ['-c', 'core.hooksPath=/dev/null', 'commit', '-q', '-F', str(msg)],
                       cwd=self.project, check=True)
        code, out = gate(self.project, self.build)
        self.assertEqual(code, 0, out)

    def commit_fixture(self):
        """Commit the fixture, then make the build leave a mark and fail."""
        git = lambda *args: subprocess.run(GIT + ['-c', 'core.hooksPath=/dev/null', *args],
                                           cwd=self.project, check=True, capture_output=True)
        (self.project / 'code.c').write_text('int main(void) { return 0; }\n')
        git('add', '-A')
        git('commit', '-q', '-m', 'base')
        self.mark = self.tmp / 'built'
        self.build.write_text('echo ran > "%s"; exit 1\n' % self.mark)
        return git

    def gate_built(self, args=('--for-commit',)):
        """Run the gate; report whether the build ran."""
        if self.mark.exists():
            self.mark.unlink()
        code, out = gate(self.project, self.build, args=args)
        return code, out, self.mark.exists()

    def test_a_documentation_only_commit_skips_the_build_and_only_the_build(self):
        # A project's gate ran its full build for minutes on every commit that changed only
        # documentation. The build is skipped for such a commit, and the PASS line says so.
        git = self.commit_fixture()
        (self.project / 'docs/a.md').write_text('a\n')
        (self.project / 'b.md').write_text('b\n')
        git('add', 'docs/a.md', 'b.md')
        code, out, built = self.gate_built()
        self.assertFalse(built, out)
        self.assertEqual(code, 0, out)
        self.assertIn('CHECK: PASS (build not run: documentation-only commit, 2 files)', out)
        # Every other check still runs: a placeholder in a staged document fails the commit.
        (self.project / 'b.md').write_text('b ' + MARKER + '\n')
        git('add', 'b.md')
        code, out, built = self.gate_built()
        self.assertEqual(code, 1, out)
        self.assertIn(MARKER, out)
        self.assertFalse(built, out)
        self.assertNotIn('CHECK: PASS', out)

    def test_any_doubt_about_a_documentation_only_commit_runs_the_build(self):
        git = self.commit_fixture()
        cases = {
            'a document and a code file': lambda: (
                (self.project / 'code.c').write_text('int main(void) { return 1; }\n'),
                git('add', 'code.c')),
            'a code file renamed to .md': lambda: git('mv', 'code.c', 'code.md'),
            'a deleted code file': lambda: git('rm', '-q', 'code.c'),
            'a symlink named x.md': lambda: (
                (self.project / 'x.md').symlink_to('code.c'), git('add', 'x.md')),
            'an empty commit': lambda: None,
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                try:
                    change()
                    if name != 'an empty commit':
                        (self.project / 'notes.md').write_text('notes\n')
                        git('add', 'notes.md')
                    code, out, built = self.gate_built()
                finally:
                    git('reset', '-q', '--hard', 'HEAD')
                    git('clean', '-fdq')
                self.assertTrue(built, out)
                self.assertEqual(code, 1, out)
                self.assertNotIn('build not run', out)
        # A manual run, the Stop hook and the self-test never ask for the path.
        (self.project / 'notes.md').write_text('notes\n')
        git('add', 'notes.md')
        code, out, built = self.gate_built(args=())
        self.assertTrue(built, out)
        self.assertEqual(code, 1, out)

    def test_a_submodule_change_hidden_by_an_ignore_setting_runs_the_build(self):
        # `git diff` honours diff.ignoreSubmodules and a submodule's own `ignore = all`: a
        # staged submodule revision beside a document was classified documentation-only.
        git = self.commit_fixture()
        inner = self.project / 'vendor/lib'
        inner.mkdir(parents=True)
        inner_git = lambda *args: subprocess.run(GIT + ['-c', 'core.hooksPath=/dev/null', *args],
                                                 cwd=inner, check=True, capture_output=True)
        inner_git('init', '-q')
        inner_git('commit', '-q', '--allow-empty', '-m', 'one')
        (self.project / '.gitmodules').write_text('[submodule "lib"]\n\tpath = vendor/lib\n\turl = ./lib\n')
        git('add', '.gitmodules', 'vendor/lib')
        git('commit', '-q', '-m', 'submodule')
        inner_git('commit', '-q', '--allow-empty', '-m', 'two')
        global_config = self.tmp / 'gitconfig'
        global_config.write_text('[diff]\n\tignoreSubmodules = all\n')
        for name, extra, gitmodules in (
                ('diff.ignoreSubmodules=all, global', {'GIT_CONFIG_GLOBAL': str(global_config)}, ''),
                ('ignore = all on the submodule', {}, '\tignore = all\n')):
            with self.subTest(case=name):
                if gitmodules:
                    (self.project / '.gitmodules').write_text(
                        '[submodule "lib"]\n\tpath = vendor/lib\n\turl = ./lib\n' + gitmodules)
                    git('commit', '-q', '-am', 'ignore it')
                (self.project / 'notes.md').write_text('notes\n')
                # -f: `git add` itself skips a submodule whose ignore is all.
                git('add', '-f', 'notes.md', 'vendor/lib')
                staged = subprocess.run(['git', 'diff', '--cached', '--name-only', '--ignore-submodules=none'],
                                        cwd=self.project, capture_output=True, text=True, check=True).stdout
                self.assertIn('vendor/lib', staged)
                if self.mark.exists():
                    self.mark.unlink()
                code, out = gate(self.project, self.build, args=('--for-commit',), **extra)
                git('reset', '-q')
                self.assertTrue(self.mark.exists(), out)
                self.assertEqual(code, 1, out)
                self.assertNotIn('build not run', out)

    def test_the_off_switch_runs_the_build_on_a_documentation_only_commit(self):
        # A project whose build reads markdown (a documentation site) turns the path off.
        script = self.project / 'scripts/check.sh'
        text = script.read_text()
        self.assertIn('\ndocs_only_skip_build=1\n', text)
        script.write_text(text.replace('\ndocs_only_skip_build=1\n', '\ndocs_only_skip_build=0\n'))
        git = self.commit_fixture()
        (self.project / 'notes.md').write_text('notes\n')
        git('add', 'notes.md')
        code, out, built = self.gate_built()
        self.assertTrue(built, out)
        self.assertEqual(code, 1, out)

    def test_every_cd_ignores_cdpath(self):
        # An exported CDPATH turned `cd scripts` into another directory (and printed it):
        # doctor.sh then checked another tree, and review.sh could review one. Every cd in a
        # shipped shell script and hook clears it.
        shipped = [*sorted((ROOT / 'core/scripts').glob('*.sh')), *(ROOT / 'core/.githooks').iterdir(),
                   *sorted(ROOT.glob('overlays/*/files/**/*.sh'))]
        self.assertIn(ROOT / 'core/scripts/review.sh', shipped)
        self.assertIn(ROOT / 'overlays/unity/files/scripts/unity_gate.sh', shipped)
        self.assertIn(ROOT / 'overlays/claude-code/files/.claude/hooks/gate_on_stop.sh', shipped)
        found = []
        for path in shipped:
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if not line.lstrip().startswith('#') and re.search(r'(^|[;&|(`])\s*cd\s', line):
                    found.append('%s:%d: %s' % (path.relative_to(ROOT), number, line.strip()))
        self.assertEqual(found, [], 'a cd without CDPATH= in front')


if __name__ == '__main__':
    unittest.main()
