"""A self-test compares HEAD, index, status and file contents at the end of its run.

A self-test may share a review's worktree only when every case writes nothing but files Git
ignores: its end check cannot catch a non-ignored file a case writes and removes meanwhile.
"""
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_check_gate_windows import environment, make_project  # noqa: E402

GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', '-c', 'commit.gpgsign=false',
       '-c', 'core.hooksPath=/dev/null']

LEAVES = ('mkdir -p ignored-out && : > ignored-out/build.txt\n'
          ': > leftover.txt\n'
          'echo three >> notes.md\n'
          'echo changed >> existing.txt\n'
          "echo '  ok   — the fixture case ran'\n")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')


class ProjectSelfTestTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / 'project'
        make_project(self.project)
        shutil.copytree(ROOT / 'core/.githooks', self.project / '.githooks')
        write(self.project / 'scripts/review.sh', "echo 'REVIEW SELF-TEST: PASS'\n")
        write(self.project / 'scripts/boundary_selftests.sh', '# The fixture has no boundaries.\n')
        write(self.project / 'AGENTS.md', '- **No AI attribution in git.**\n')
        write(self.project / '.gitignore', 'ignored-out/\n')
        # A tracked file already modified before the run: status names it the same way after
        # another edit, so its content hash must see that edit and name the path.
        write(self.project / 'notes.md', 'one\n')
        subprocess.run(GIT + ['add', 'notes.md'], cwd=self.project, check=True)
        subprocess.run(GIT + ['commit', '-qm', 'notes'], cwd=self.project, check=True)
        write(self.project / 'notes.md', 'two\n')
        write(self.project / 'existing.txt', 'before\n')
        self.build = self.tmp / 'build.sh'
        write(self.build, 'true\n')

    def self_test(self):
        result = subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=self.project,
                                env=environment(self.build), capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=900)
        return result.returncode, result.stdout + result.stderr

    def test_shellcheck_drops_ambient_options(self):
        tools = self.tmp / 'bin'
        tools.mkdir()
        calls = self.tmp / 'shellcheck-env'
        write(tools / 'shellcheck', '#!/bin/sh\n'
              'printf "%s\\n" "${SHELLCHECK_OPTS-}" >> "%s"\n' % ('%s', calls.as_posix()) +
              '[ -n "${SHELLCHECK_OPTS-}" ] && exit 0\n'
              'printf "fixture.sh:1:1: note: Double quote [SC2086]\\n"\nexit 1\n')
        (tools / 'shellcheck').chmod(0o755)
        env = environment(self.build, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                          SHELLCHECK_OPTS='--severity=error')
        result = subprocess.run(['sh', 'scripts/check.sh'], cwd=self.project, env=env,
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertTrue(calls.exists(), result.stdout + result.stderr)
        self.assertEqual(calls.read_text(encoding='utf-8'), '\n', result.stdout + result.stderr)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('FAIL [shellcheck]', result.stdout)
        self.assertIn('[SC2086]', result.stdout)

    def test_shellcheck_runs_normally_and_only_in_its_own_nested_case(self):
        # Count actual process launches with a lint test double. The injected unquoted
        # file still has to turn its dedicated case red; other nested cases need no lint.
        tools = self.tmp / 'bin'
        tools.mkdir()
        calls = self.tmp / 'shellcheck-calls'
        write(tools / 'shellcheck', '#!/bin/sh\n'
              'printf "pass\\n" >> "%s"\n' % calls.as_posix() +
              'for f do\ncase "$f" in */unquoted.sh)\n'
              'printf "%s:3:6: note: Double quote [SC2086]\\n" "$f"; exit 1;;\nesac\ndone\n')
        (tools / 'shellcheck').chmod(0o755)
        env = environment(self.build, PATH=str(tools) + os.pathsep + os.environ['PATH'])
        for marker in ('', 'a-copied-marker'):
            result = subprocess.run(['sh', 'scripts/check.sh'], cwd=self.project,
                                    env=dict(env, GATE_SELFTEST_NESTED=marker),
                                    capture_output=True, text=True, encoding='utf-8', timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(calls.read_text(encoding='utf-8').splitlines()), 2)
        calls.write_text('', encoding='utf-8')
        result = subprocess.run(['sh', 'scripts/check.sh', '--self-test'], cwd=self.project,
                                env=env, capture_output=True, text=True, encoding='utf-8', timeout=900)
        out = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, out)
        self.assertIn('an unquoted expansion in a shell script fails the gate (ShellCheck SC2086)', out)
        self.assertEqual(len(calls.read_text(encoding='utf-8').splitlines()), 1,
                         'unrelated nested gate runs must skip ShellCheck')

    def test_a_case_that_leaves_an_untracked_file_fails_the_self_test_by_path(self):
        code, out = self.self_test()
        self.assertEqual(code, 0, out)
        self.assertIn('ok   — the self-test left HEAD, the index, git status and the tracked changes as it found them', out)
        # A case that leaves a file Git does not ignore, beside one it ignores.
        write(self.project / 'scripts/boundary_selftests.sh', LEAVES)
        code, out = self.self_test()
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL — the self-test changed this worktree', out)
        self.assertIn('another process edited the checkout meanwhile', out)
        self.assertIn('    + ?? leftover.txt', out)
        self.assertRegex(out, r'    \+ [0-9a-f]{40,64} notes\.md')
        self.assertRegex(out, r'    \+ [0-9a-f]{40,64} existing\.txt')
        self.assertNotIn('ignored-out', out)
        self.assertIn('SELF-TEST: FAIL', out)

    def counting_build(self):
        runs = self.tmp / 'build-runs'
        write(self.build, 'echo run >> "%s"\n' % runs.as_posix())
        return lambda: len(runs.read_text(encoding='utf-8').splitlines()) if runs.exists() else 0

    def test_the_real_build_runs_once_and_a_scoped_check_is_proven_without_a_copy(self):
        # #80: each nested case ran the project's build, even after its injected failure had
        # failed it; a 3.5-minute build made the self-test three hours. Only the baseline builds.
        # #126: worked example A proves a path-scoped scan_grep check with a synthetic file
        # scanned under an in-tree path: nothing is written into the tree, nothing is copied.
        builds = self.counting_build()
        example = '\n'.join(line[4:] for line in (ROOT / 'core/scripts/boundary_selftests.sh')
                            .read_text(encoding='utf-8').splitlines() if line.startswith('# > '))
        self.assertIn('GATE_SELFTEST_EXTRA_PATH=src/domain/', example)
        check = ("hits=$(scan_grep 'from myapp\\.web' | grep '^src/domain/')\n"
                 'if [ -n "$hits" ]; then\n'
                 '  echo "FAIL [boundary]: the domain layer imports the web layer:"\n'
                 '  echo "$hits"\n  fail=1\nfi\n')
        write(self.project / 'scripts/boundary_checks.sh', check)
        write(self.project / 'scripts/boundary_selftests.sh', example + '\n')
        code, out = self.self_test()
        self.assertEqual(code, 0, out)
        self.assertEqual(builds(), 1, out)
        self.assertIn('ok   — domain/web boundary gate rejects a forbidden import in a new file', out)
        self.assertIn('ok   — the build cache skips a build that passed on the same files and inputs', out)
        self.assertIn('ok   — a synthetic file scanned as an in-tree path is reported under that path', out)
        self.assertNotIn('NOTE — scripts/boundary_checks.sh sets fail=1', out)
        self.assertFalse((self.project / 'src').exists())
        # The same check scoped to another folder never sees the injection: the case goes red.
        write(self.project / 'scripts/boundary_checks.sh', check.replace("'^src/domain/'", "'^src/other/'"))
        code, out = self.self_test()
        self.assertEqual(code, 1, out)
        self.assertIn('FAIL — domain/web boundary gate rejects a forbidden import in a new file: '
                      'the gate stayed GREEN', out)

    def test_expect_fail_needs_the_checks_own_line_and_a_busy_lock_is_not_run(self):
        # #110: any nonzero exit counted as the check firing, a lock timeout (75) included.
        write(self.project / 'scripts/boundary_checks.sh', ': || fail=1\n: || fail=1\n')
        write(self.project / 'scripts/boundary_selftests.sh',
              "expect_fail 'wrong line' 'FAIL [boundary]: never printed' GATE_SELFTEST_EXTRA_FILE=\"$inj\"\n"
              "expect_fail 'busy lock' 'FAIL [setup]' GATE_LOCK_HELD= GATE_LOCK_WAIT=1\n"
              "expect_fail 'right line' 'FAIL [setup]: unfilled placeholder markers remain' "
              "GATE_SELFTEST_EXTRA_FILE=\"$inj\"\n")
        code, out = self.self_test()
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL — wrong line: the gate exited 1 without the diagnostic 'FAIL [boundary]: never printed'", out)
        self.assertIn('NOT RUN — busy lock: the gate lock was not free (exit 75)', out)
        self.assertIn('ok   — right line', out)
        # Two `fail=1` lines, one case that passed: told, not failed.
        self.assertIn('NOTE — scripts/boundary_checks.sh sets fail=1 in 2 places', out)

    def test_a_red_baseline_is_inconclusive_with_its_own_exit_code(self):
        # #152: 2 meant both a usage error and a red baseline.
        write(self.build, 'exit 1\n')
        code, out = self.self_test()
        self.assertEqual(code, 3, out)
        self.assertIn('SELF-TEST INCONCLUSIVE', out)
        result = subprocess.run(['sh', 'scripts/check.sh', '--no-such-flag'], cwd=self.project,
                                env=environment(self.build), capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_the_build_cache_skips_only_a_build_that_passed_on_the_same_inputs(self):
        # #82: the worker, the Stop hook and the commit hook each built the same files.
        builds = self.counting_build()
        script = self.project / 'scripts/check.sh'
        text = script.read_text(encoding='utf-8')

        def gate(**extra):
            result = subprocess.run(['sh', 'scripts/check.sh'], cwd=self.project, env=environment(self.build, **extra),
                                    capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            return out, builds()

        for _ in range(2):
            out, _ = gate()
        self.assertEqual(builds(), 2, 'no build_cache_inputs, no cache:\n' + out)
        self.assertIn('\nbuild_cache_inputs=""\n', text)
        write(script, text.replace('\nbuild_cache_inputs=""\n', '\nbuild_cache_inputs=\'echo "tool ${FIXTURE_TOOL-1}"\'\n'))
        steps = ((dict(), 3, False), (dict(), 3, True),                          # recorded, then cached
                 (dict(FIXTURE_TOOL='2'), 4, False), (dict(FIXTURE_TOOL='2'), 4, True),  # an input changed
                 ('edit', 5, False), (dict(FIXTURE_TOOL='2'), 5, True),           # an untracked file changed
                 ('new', 6, False), (dict(FIXTURE_TOOL='2'), 6, True),            # a new untracked file
                 (dict(FIXTURE_TOOL='2', CI='true'), 7, False),                   # CI never reads it
                 (dict(FIXTURE_TOOL='2', GATE_CACHE='off'), 8, False))
        cached_line = re.compile(r'^NOTE \[build\]: not run: cached PASS [0-9a-f]{12} from \d{4}-\d\d-\d\dT', re.M)
        for extra, want, cached in steps:
            with self.subTest(extra=extra, want=want):
                if extra == 'edit':
                    write(self.project / 'existing.txt', 'after\n')
                    extra = dict(FIXTURE_TOOL='2')
                if extra == 'new':
                    write(self.project / 'docs' / 'read-by-a-test.md', 'new\n')
                    extra = dict(FIXTURE_TOOL='2')
                out, count = gate(**extra)
                self.assertEqual(count, want, out)
                self.assertEqual(bool(cached_line.search(out)), cached, out)
                self.assertEqual('CHECK: PASS (build not run: cached PASS ' in out, cached, out)
        # An entry another version of the gate wrote is deleted, even under the current key.
        cache = Path(subprocess.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'], cwd=self.project,
                                    capture_output=True, text=True, check=True).stdout.strip()) / 'check-cache'
        entries = list(cache.iterdir())
        self.assertTrue(entries)
        for entry in entries:
            write(entry, 'an older gate\n')
        out, count = gate(FIXTURE_TOOL='2')
        self.assertEqual(count, 9, out)
        self.assertTrue(all(e.read_text().strip() != 'an older gate' for e in cache.iterdir()), out)
        # A build that changes a listed file while it runs: the key computed after it differs
        # from the one before, so nothing is recorded. With the file put back (the key before
        # that build again), the next run still builds.
        runs = self.tmp / 'build-runs'
        write(self.build, 'echo run >> "%s"\necho more >> existing.txt\n' % runs.as_posix())
        out, count = gate(FIXTURE_TOOL='3')
        self.assertEqual(count, 10, out)
        write(self.project / 'existing.txt', 'after\n')
        write(self.build, 'echo run >> "%s"\n' % runs.as_posix())
        out, count = gate(FIXTURE_TOOL='3')
        self.assertEqual(count, 11, out)
        self.assertNotIn('cached PASS', out)
        write(script, text.replace('\nbuild_cache_inputs=""\n', '\nbuild_cache_inputs=false\n'))
        for want in (12, 13):
            out, count = gate()
            self.assertEqual(count, want, out)
        self.assertIn('NOTE [build]: build_cache_inputs failed, so the build is not cached', out)


class KitWrapperTests(unittest.TestCase):
    def assert_content_edit_fails(self, tracked, name='existing file.txt'):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / 'kit'
            (kit / 'scripts').mkdir(parents=True)
            shutil.copyfile(ROOT / 'scripts/check.sh', kit / 'scripts/check.sh')
            write(kit / 'scripts/check_kit.py',
                  'import os\nfrom pathlib import Path\n'
                  'p = Path(%r)\ns = p.stat()\n' % name +
                  'p.write_bytes(b"after!\\n")\n'
                  'os.utime(p, ns=(s.st_atime_ns, s.st_mtime_ns))\n'
                  'Path(os.environ["KIT_CHECK_PASSED"]).touch()\n')
            subprocess.run(['git', 'init', '-q', str(kit)], check=True)
            subprocess.run(['git', 'config', 'core.autocrlf', 'false'], cwd=kit, check=True)
            write(kit / name, 'before\n')
            if tracked:
                subprocess.run(['git', 'config', 'core.trustctime', 'false'], cwd=kit, check=True)
                subprocess.run(['git', 'config', 'core.checkStat', 'minimal'], cwd=kit, check=True)
                subprocess.run(GIT + ['add', name], cwd=kit, check=True)
                subprocess.run(GIT + ['commit', '-qm', 'tracked'], cwd=kit, check=True)
                # Avoid Git's racy-index timestamp window; keep the same indexed mtime on edit.
                stamp = 1_600_000_000_000_000_000
                os.utime(kit / name, ns=(stamp, stamp))
                subprocess.run(['git', 'update-index', '--refresh'], cwd=kit, check=True)
            before = subprocess.run(['git', 'status', '--porcelain'], cwd=kit,
                                    capture_output=True, check=True).stdout
            result = subprocess.run(['sh', str(kit / 'scripts/check.sh'), '--self-test'], cwd=kit,
                                    capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=120)
            after = subprocess.run(['git', 'status', '--porcelain'], cwd=kit,
                                   capture_output=True, check=True).stdout
            self.assertEqual(before, after)
            if tracked:
                self.assertEqual(subprocess.run(['git', 'diff', '--binary', 'HEAD'], cwd=kit,
                                               capture_output=True, check=True).stdout, b'')
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1, out)
            self.assertIn('KIT CHECK: FAIL', out)
            self.assertRegex(out, r'    \+ [0-9a-f]{40,64} ' + re.escape(name))
            self.assertIn('another process edited the checkout meanwhile', out)

    def test_an_existing_untracked_file_edited_in_place_fails_by_path(self):
        self.assert_content_edit_fails(tracked=False)

    def test_a_tracked_edit_hidden_by_restored_mtime_fails_by_path(self):
        self.assert_content_edit_fails(tracked=True)

    def test_a_non_ascii_name_edited_in_place_fails_by_path(self):
        # Git prints such a name C-quoted by default, and hash-object does not unquote it: the
        # old per-file loop hashed nothing, before and after, so the edit went unseen.
        self.assert_content_edit_fails(tracked=False, name='ä.txt')
        self.assert_content_edit_fails(tracked=True, name='ä.txt')

    def test_the_tree_is_hashed_by_one_git_hash_object_call_per_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit, wrapped, calls = Path(tmp) / 'kit', Path(tmp) / 'bin', Path(tmp) / 'calls.log'
            (kit / 'scripts').mkdir(parents=True)
            shutil.copyfile(ROOT / 'scripts/check.sh', kit / 'scripts/check.sh')
            write(kit / 'scripts/check_kit.py',
                  'import os\nfrom pathlib import Path\nPath(os.environ["KIT_CHECK_PASSED"]).touch()\n')
            subprocess.run(['git', 'init', '-q', str(kit)], check=True)
            for number in range(30):
                write(kit / ('file %d.txt' % number), 'x\n')
            subprocess.run(GIT + ['add', 'file 1*.txt'], cwd=kit, check=True)
            # An indexed file deleted from disk must not shift the hashes onto the wrong names.
            (kit / 'file 10.txt').unlink()
            # git, counting its hash-object calls and then running the real one.
            write(wrapped / 'git',
                  '#!/bin/sh\nfor a; do [ "$a" = hash-object ] && echo x >> "%s"; done\nexec "%s" "$@"\n'
                  % (calls.as_posix(), Path(shutil.which('git')).as_posix()))
            os.chmod(wrapped / 'git', 0o755)
            result = subprocess.run(['sh', str(kit / 'scripts/check.sh'), '--self-test'], cwd=kit,
                                    env=dict(os.environ, PATH=str(wrapped) + os.pathsep + os.environ['PATH']),
                                    capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=120)
            out = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, out)
            # Once for the view before the run and once after it; the old loop made one per file.
            self.assertEqual(len(calls.read_text().split()), 2, out)

    def test_an_unopenable_path_or_short_hash_output_fails_by_path(self):
        # Run each shipped git_view itself: no gate or plugin generation is needed.
        for script in ('scripts/check.sh', 'core/scripts/check.sh'):
            source = (ROOT / script).read_text(encoding='utf-8')
            start = source.index('git_view() {')
            end = source.index('\n}', start) if script == 'scripts/check.sh' else source.index('\n  }', start)
            function = source[start:end] + '\n}\n'
            for case in ('directory', 'short-output'):
                with self.subTest(script=script, case=case), tempfile.TemporaryDirectory() as tmp:
                    kit, scratch = Path(tmp) / 'kit', Path(tmp) / 'scratch'
                    kit.mkdir()
                    scratch.mkdir()
                    subprocess.run(['git', 'init', '-q', str(kit)], check=True)
                    write(kit / 'a.txt', 'first\n')
                    write(kit / 'b.txt', 'second\n')
                    real_git = Path(shutil.which('git')).as_posix()
                    inject = ('rm a.txt && mkdir a.txt' if case == 'directory' else
                              'IFS= read -r first; printf "%%s\\n" "$first" | "%s" "$@"; return 0' % real_git)
                    wrapper = ('git() {\nif [ "$1" = hash-object ]; then\n%s\nfi\n'
                               '"%s" "$@"\n}\n' % (inject, real_git))
                    runner = scratch / 'run.sh'
                    write(runner, 'set -eu\nwork="%s"\npassed="$work"\n' % scratch.as_posix() +
                          wrapper + function +
                          'git_view "$work" > "$work/view" 2>&1 || { cat "$work/view"; exit 1; }\n')
                    result = subprocess.run(['sh', str(runner)], cwd=kit, capture_output=True,
                                            text=True, encoding='utf-8', errors='replace', timeout=30)
                    out = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 1, out)
                    missing = 'a.txt' if case == 'directory' else 'b.txt'
                    self.assertIn('could not hash %s; the tree check is incomplete' % missing, out)

    def test_every_self_test_seam_carries_the_prefix_the_gate_refuses(self):
        # The gate refuses GATE_SELFTEST_* outside the self-test by prefix (KARARLAR D03
        # inv2#161): a seam without it would pass an exported copy into a normal run.
        source = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
        read = set(re.findall(r'\$\{([A-Z][A-Z0-9_]*)[:+-]', source))
        legacy = {'GATE_BUILD_CMD_OVERRIDE', 'BOUNDARY_CHECKS_FILE', 'BOUNDARY_SELFTESTS_FILE'}
        # Not seams: they change when a run starts or what CI prints, not what it checks; the
        # marker; the caller's locale; the lock case script's own fixture variables. GATE_CACHE=off
        # only forces a full build, it never skips one.
        other = {'CI', 'GATE_CACHE', 'GATE_LOCK_FD', 'GATE_LOCK_HELD', 'GATE_LOCK_WAIT', 'GATE_SELFTEST_NESTED', 'LC_ALL'}
        unprefixed = sorted(name for name in read - legacy - other
                            if not name.startswith(('GATE_SELFTEST_', 'LOCKCASE_')))
        self.assertEqual(unprefixed, [], 'a seam without the GATE_SELFTEST_ prefix')
        for name in legacy:
            self.assertIn(name, read)
            self.assertRegex(source, r'for seam in [^\n]*%s' % name)

    def test_an_inherited_work_variable_never_chooses_the_scratch_folder(self):
        # An exported `work` once named the folder git_view wrote and deleted git-paths* in
        # (round-3 Codex Critical): the scratch folder is the caller's argument, nothing else.
        source = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
        start = source.index('git_view() {')
        function = source[start:source.index('\n  }', start)] + '\n}\n'
        with tempfile.TemporaryDirectory() as tmp:
            kit, scratch, decoy = Path(tmp) / 'kit', Path(tmp) / 'scratch', Path(tmp) / 'decoy'
            for folder in (kit, scratch, decoy):
                folder.mkdir()
            subprocess.run(['git', 'init', '-q', str(kit)], check=True)
            write(kit / 'a.txt', 'first\n')
            for name in ('git-paths', 'git-paths.hashes', 'git-paths.errors'):
                write(decoy / name, 'owner data\n')
            runner = scratch / 'run.sh'
            write(runner, 'set -eu\n' + function + 'git_view "%s" > "%s/view"\n'
                  % (scratch.as_posix(), scratch.as_posix()))
            result = subprocess.run(['sh', str(runner)], cwd=kit, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=30,
                                    env=dict(os.environ, work=decoy.as_posix()))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('a.txt', (scratch / 'view').read_text(encoding='utf-8'))
            for name in ('git-paths', 'git-paths.hashes', 'git-paths.errors'):
                self.assertEqual((decoy / name).read_text(encoding='utf-8'), 'owner data\n')

    def test_the_kit_self_test_fails_on_a_file_it_leaves_and_passes_an_ignored_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / 'kit'
            (kit / 'scripts').mkdir(parents=True)
            shutil.copyfile(ROOT / 'scripts/check.sh', kit / 'scripts/check.sh')
            write(kit / '.gitignore', 'ignored-out/\n')
            write(kit / 'scripts/check_kit.py',
                  'import os, sys\nfrom pathlib import Path\n'
                  'Path(os.environ["LEAVE"]).parent.mkdir(exist_ok=True)\n'
                  'Path(os.environ["LEAVE"]).open("a").write("x")\n'
                  'Path(os.environ["KIT_CHECK_PASSED"]).touch()\n')
            subprocess.run(['git', 'init', '-q', str(kit)], check=True)
            write(kit / 'tracked.txt', 'one\n')
            subprocess.run(GIT + ['add', 'tracked.txt'], cwd=kit, check=True)
            subprocess.run(GIT + ['commit', '-qm', 'tracked'], cwd=kit, check=True)
            write(kit / 'tracked.txt', 'two\n')  # Modified before the run.
            for leave, args, expected in (('ignored-out/x', ['--self-test'], 0),
                                          ('leftover.txt', [], 0),
                                          ('leftover2.txt', ['--self-test'], 1),
                                          ('tracked.txt', ['--self-test'], 1)):
                with self.subTest(leave=leave, args=args):
                    result = subprocess.run(['sh', str(kit / 'scripts/check.sh'), *args], cwd=kit,
                                            env=dict(os.environ, LEAVE=str(kit / leave)),
                                            capture_output=True, text=True, encoding='utf-8',
                                            errors='replace', timeout=120)
                    out = result.stdout + result.stderr
                    self.assertEqual(result.returncode, expected, out)
                    if expected:
                        self.assertIn('KIT CHECK: FAIL — the self-test changed this checkout', out)
                    if leave == 'leftover2.txt':
                        self.assertIn('    + ?? leftover2.txt', out)
                        self.assertNotIn('leftover.txt\n', out.replace('leftover2.txt', ''))
                    if leave == 'tracked.txt':
                        # Status says " M tracked.txt" before and after: only the hash differs.
                        self.assertRegex(out, r'    \+ [0-9a-f]{40,64} tracked\.txt')


if __name__ == '__main__':
    unittest.main()
