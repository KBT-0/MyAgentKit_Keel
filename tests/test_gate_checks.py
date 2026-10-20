"""One fixture test per check of the shipped gate: a breaking input turns it red with its own line.

These replace the gate's whole-gate --self-test (owner decision 2026-10-18). A check is fed a
small fixture project, as rule checkers test their rules (Semgrep's ruleid/ok, ESLint's
RuleTester valid/invalid cases): the breaking input must fail with the check's own diagnostic,
the clean one must pass. The build is a one-line stub; no case runs a real build
(docs/research/kit-self-checks.md, findings 1 and 2). Checks already proven elsewhere:
Done: trailers and audits (test_check_gate_windows GateRuleTests, test_done_audits), the module
map, ShellCheck selection and the strong review task count (GateRuleTests), the commit hooks
(test_git_hooks), the documentation-only commit (test_check_gate), the lock (test_check_gate,
test_check_gate_windows, the acceptance unit).
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_check_gate_windows import environment, make_project  # noqa: E402

GIT = ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', '-c', 'commit.gpgsign=false',
       '-c', 'core.hooksPath=/dev/null']
# Assembled, never literal: the kit's own files carry no unfilled marker.
MARKER = '{{' + 'GATE_TEST_MARKER}}'


def symlinks_work():
    """Windows makes a symlink only in Developer Mode or for an administrator."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.symlink(tmp, os.path.join(tmp, 'link'))
        except (OSError, NotImplementedError):
            return False
    return True


SYMLINKS = symlinks_work()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')


class GateCheckTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / 'project'
        make_project(self.project)
        self.build = self.tmp / 'build.sh'
        write(self.build, 'true\n')

    def gate(self, **extra):
        result = subprocess.run(['sh', 'scripts/check.sh'], cwd=self.project, env=environment(self.build, **extra),
                                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
        return result.returncode, result.stdout + result.stderr

    def assert_red(self, line, **extra):
        code, out = self.gate(**extra)
        self.assertEqual(code, 1, out)
        self.assertIn(line, out)
        self.assertIn('CHECK: FAIL', out)
        return out

    def assert_green(self, **extra):
        code, out = self.gate(**extra)
        self.assertEqual(code, 0, out)
        self.assertIn('CHECK: PASS', out)
        return out

    def set_gate_line(self, old, new):
        script = self.project / 'scripts/check.sh'
        text = script.read_text(encoding='utf-8')
        self.assertIn(old, text)
        write(script, text.replace(old, new, 1))

    def test_an_unfilled_marker_fails_except_in_setup_and_the_module_template(self):
        write(self.project / 'docs/note.md', 'text ' + MARKER + '\n')
        self.assert_red('FAIL [setup]: unfilled placeholder markers remain')
        self.assertIn('docs/note.md:1:text ' + MARKER, self.gate()[1])
        (self.project / 'docs/note.md').unlink()
        write(self.project / 'setup/note.md', MARKER + '\n')
        write(self.project / 'MODULE_AGENTS_TEMPLATE.md', MARKER + '\n')
        self.assert_green()

    def test_the_state_file_must_exist_with_its_heading_and_is_never_measured(self):
        state = self.project / 'docs/STATE.md'
        write(state, '# STATE\n\n## Active work\n\n## Notes\n' + ''.join('line %d\n' % i for i in range(500)))
        self.assert_green()
        write(state, '# STATE\n\n## Current things\n')
        self.assert_red("FAIL [state]: docs/STATE.md has no '## Active work' heading")
        state.unlink()
        self.assert_red('FAIL [state]: docs/STATE.md does not exist')

    def test_the_project_file_contents_must_list_every_numbered_section(self):
        project = self.project / 'docs/PROJECT.md'
        listed = '# PROJECT\n\n## Contents\n\n- 1. What this is\n- 2. Money\n\n## 1. What this is\na\n\n## 2. Money\nb\n'
        write(project, listed)
        self.assert_green()
        write(project, '# PROJECT\n\n## Contents\n\n(nothing decided yet)\n')
        self.assert_green()
        write(project, listed.replace('- 2. Money\n', ''))
        out = self.assert_red('FAIL [project]: docs/PROJECT.md has numbered sections missing from its Contents:')
        self.assertIn('  - 2. Money', out)
        # Under a substring match "1. Money" was found inside the entry "11. Money".
        write(project, '# PROJECT\n\n## Contents\n\n- 11. Money\n\n## 1. Money\nx\n\n## 11. Money\ny\n')
        self.assert_red('FAIL [project]: docs/PROJECT.md has numbered sections missing')
        write(project, '# PROJECT\n\n## 1. Money\n')
        self.assert_red("FAIL [project]: docs/PROJECT.md has no '## Contents' section")
        project.unlink()
        self.assert_red('FAIL [project]: docs/PROJECT.md does not exist')

    def test_an_agents_chain_codex_loads_fails_over_24_kib_only_where_codex_is_in_use(self):
        # #143: Codex drops what passes 32 KiB of the joined AGENTS.md chain without a word.
        write(self.project / 'AGENTS.md', 'r' * 16000 + '\n')
        write(self.project / 'docs/AGENTS.md', 'd' * 8000 + '\n')
        self.assertNotIn('[agents-size]', self.assert_green())
        write(self.project / 'docs/game/AGENTS.md', 'g' * 600 + '\n')  # 16001 + 8001 + 601 bytes
        out = self.assert_green()  # no Codex named in scripts/review.sh
        self.assertIn('NOTE [agents-size]', out)
        write(self.project / 'scripts/review.sh', 'DEFAULT_REVIEWER="claude"\nCODEX_MODEL="gpt-5.5"\n')
        out = self.assert_red('FAIL [agents-size]')
        self.assertIn('  - docs/game/AGENTS.md: 24603 bytes', out)
        self.assertNotIn('  - docs/AGENTS.md:', out)
        # Round-1 review: Codex as the default reviewer is in use without a model pin; Claude as
        # the reviewer with no Codex pin is not (lead decision: a NOTE).
        write(self.project / 'scripts/review.sh', 'DEFAULT_REVIEWER="codex"\nCODEX_MODEL=""\n')
        self.assert_red('FAIL [agents-size]')
        write(self.project / 'scripts/review.sh', 'DEFAULT_REVIEWER="claude"\nCODEX_MODEL=""\n')
        self.assertIn('NOTE [agents-size]', self.assert_green())
        (self.project / 'docs/game/AGENTS.md').unlink()
        self.assert_green()

    def test_an_agents_chain_under_a_folder_that_starts_with_a_dash_counts_the_root_once(self):
        # Round-1 review of #143: the file list's ./ before `-notes` read as a folder, and the
        # root AGENTS.md counted twice.
        write(self.project / 'scripts/review.sh', 'CODEX_MODEL="x"\n')
        write(self.project / 'AGENTS.md', 'r' * 13000 + '\n')
        write(self.project / '-notes/AGENTS.md', 'n' * 99 + '\n')
        self.assertNotIn('[agents-size]', self.assert_green())
        write(self.project / '-notes/AGENTS.md', 'n' * 11999 + '\n')
        self.assertIn('  - -notes/AGENTS.md: 25001 bytes', self.assert_red('FAIL [agents-size]'))

    def test_a_missing_boundary_checks_file_fails(self):
        (self.project / 'scripts/boundary_checks.sh').unlink()
        self.assert_red('FAIL [boundary]: scripts/boundary_checks.sh is missing')

    def test_an_unset_blank_or_failing_build_command_fails(self):
        write(self.build, 'exit 1\n')
        self.assert_red('FAIL [build]: the build/test command exited 1')
        configured = 'build_test_cmd="sh $GATE_TEST_BUILD"'
        for blank in ('""', '"  "'):
            with self.subTest(command=blank):
                self.set_gate_line(configured, 'build_test_cmd=' + blank)
                self.assert_red('FAIL [build]: no build/test command is configured')
                configured = 'build_test_cmd=' + blank

    def test_a_build_failure_shows_its_chain_keeps_the_log_and_prints_all_on_ci(self):
        # The lines that locate a compile error come before and around "error:"; a gate that
        # printed only lines matching "error" hid them, and a CI-only failure was fixed blind.
        write(self.build, 'i=0; while [ $i -lt 300 ]; do printf "build line %s\\n" "$i"; i=$((i + 1)); done\n'
                          'echo "src/x.c: In function f:"; echo "src/x.c:3:5: error: bad"\n'
                          'echo "src/x.c:2:1: note: declared here"; exit 1\n')
        out = self.assert_red('FAIL [build]: the build/test command exited 1', CI='')
        self.assertIn('In function f:', out)
        self.assertIn('note: declared here', out)
        self.assertNotIn('\nbuild line 0\n', out)
        log = self.project / '.git/check-build.log'
        self.assertIn('build line 0\n', log.read_text(encoding='utf-8'))
        out = self.assert_red('FAIL [build]: the build/test command exited 1. Its whole output follows (CI).', CI='true')
        self.assertIn('\nbuild line 0\n', out)

    def test_a_scanner_that_fails_cannot_end_in_a_pass(self):
        # A grep that crashes inside a command substitution once let the gate sail on to PASS.
        real = subprocess.run(['sh', '-c', 'command -v grep'], capture_output=True, text=True,
                              check=True).stdout.strip()
        shim = self.tmp / 'bin'
        write(shim / 'grep', '#!/bin/sh\nfor a; do [ "$a" = -InE ] && exit 2; done\nexec "%s" "$@"\n' % real)
        (shim / 'grep').chmod(0o755)
        out = self.assert_red('FAIL [scan]: a scanner failed to run somewhere above',
                              PATH=str(shim) + os.pathsep + os.environ['PATH'])
        self.assertNotIn('CHECK: PASS', out)

    def test_the_strong_review_reminder_names_a_missing_or_old_report_and_is_quiet_otherwise(self):
        write(self.project / 'docs/STRONG_REVIEW.md', '# STRONG_REVIEW\n')
        subprocess.run(GIT + ['add', '-A'], cwd=self.project, check=True)
        subprocess.run(GIT + ['commit', '-qm', 'base'], cwd=self.project, check=True)
        out = self.assert_green()
        self.assertIn('NOTE [strong-review]: no strong review report yet', out)
        write(self.project / 'docs/reviews/strong-2026-01-01-model.md', 'report\n')
        subprocess.run(GIT + ['add', '-A'], cwd=self.project, check=True)
        old = '@%d +0000' % (time.time() - 30 * 86400)
        subprocess.run(GIT + ['commit', '-qm', 'strong review'], cwd=self.project, check=True,
                       env=dict(os.environ, GIT_COMMITTER_DATE=old))
        out = self.assert_green()
        self.assertIn('NOTE [strong-review]: the newest strong review report was added 30 days ago', out)
        write(self.project / 'docs/reviews/strong-2026-02-01-model.md', 'report\n')
        subprocess.run(GIT + ['add', '-A'], cwd=self.project, check=True)
        subprocess.run(GIT + ['commit', '-qm', 'strong review again'], cwd=self.project, check=True)
        self.assertNotIn('NOTE [strong-review]', self.assert_green())

    def test_shellcheck_drops_ambient_options(self):
        tools = self.tmp / 'bin'
        calls = self.tmp / 'shellcheck-env'
        write(tools / 'shellcheck', '#!/bin/sh\n'
              'printf "%s\\n" "${SHELLCHECK_OPTS-}" >> "%s"\n' % ('%s', calls.as_posix()) +
              '[ -n "${SHELLCHECK_OPTS-}" ] && exit 0\n'
              'printf "fixture.sh:1:1: note: Double quote [SC2086]\\n"\nexit 1\n')
        (tools / 'shellcheck').chmod(0o755)
        out = self.assert_red('FAIL [shellcheck]', PATH=str(tools) + os.pathsep + os.environ['PATH'],
                              SHELLCHECK_OPTS='--severity=error')
        self.assertEqual(calls.read_text(encoding='utf-8'), '\n', out)
        self.assertIn('[SC2086]', out)

    def test_the_boundary_fixture_test_example_proves_the_example_check(self):
        # The fixture test boundary_checks.sh shows a project, run against its own example check:
        # green as shipped, red when the check stops seeing the forbidden import.
        template = (ROOT / 'core/scripts/boundary_checks.sh').read_text(encoding='utf-8')
        example = '\n'.join(line[4:] for line in template.splitlines() if line.startswith('# > ')) + '\n'
        check = '\n'.join(line[4:] for line in template.split('# Worked example', 1)[1].split('\n#\n')[1]
                          .splitlines()) + '\n'
        self.assertIn("scan_grep 'from myapp\\.web' | grep '^src/domain/'", check)
        write(self.project / 'tests/boundary_checks_test.sh', example)
        for scope, code, line in (("'^src/domain/'", 0, None),
                                  ("'^src/other/'", 1, 'FAIL: src/domain/order.py should turn the check red')):
            with self.subTest(scope=scope):
                write(self.project / 'scripts/boundary_checks.sh', check.replace("'^src/domain/'", scope))
                # System32 first on native Windows: a find(1) in the example met FIND.EXE there.
                path = os.environ['PATH'] if os.name != 'nt' else r'C:\Windows\System32;' + os.environ['PATH']
                result = subprocess.run(['sh', 'tests/boundary_checks_test.sh'], cwd=self.project, capture_output=True,
                                        text=True, encoding='utf-8', errors='replace', timeout=60,
                                        env=dict(os.environ, PATH=path))
                out = result.stdout + result.stderr
                self.assertEqual(result.returncode, code, out)
                if line:
                    self.assertIn(line, out)
        self.assertEqual(sorted(p.name for p in self.project.iterdir()), ['.git', 'docs', 'scripts', 'tests'])
        # The example check itself passes the real gate on a clean tree and fails a real import.
        write(self.project / 'scripts/boundary_checks.sh', check)
        (self.project / 'tests/boundary_checks_test.sh').unlink()
        self.assert_green()
        write(self.project / 'src/domain/order.py', 'from myapp.web import router\n')
        self.assert_red('FAIL [boundary]: the domain layer imports the web layer:')


class BuildCacheTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / 'project'
        make_project(self.project)
        write(self.project / 'existing.txt', 'before\n')
        self.build = self.tmp / 'build.sh'

    def counting_build(self):
        runs = self.tmp / 'build-runs'
        write(self.build, 'echo run >> "%s"\n' % runs.as_posix())
        return lambda: len(runs.read_text(encoding='utf-8').splitlines()) if runs.exists() else 0

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

    @unittest.skipUnless(SYMLINKS, 'this host may not make symlinks (Windows without Developer Mode or '
                                   'administrator rights)')
    def test_a_link_to_a_file_the_key_does_not_hash_turns_the_cache_off(self):
        # A link to a file is hashed by its text: with cfg.h -> a file outside the tree, an edit
        # there that broke the build left the key unchanged and the next run passed from cache.
        builds = self.counting_build()
        write(self.build, self.build.read_text(encoding='utf-8') + 'grep -q ok cfg.h\n')
        script = self.project / 'scripts/check.sh'
        write(script, script.read_text(encoding='utf-8').replace('\nbuild_cache_inputs=""\n', '\nbuild_cache_inputs=true\n'))
        write(self.project / '.gitignore', 'out/\n')
        outside = self.tmp / 'outside.h'
        for target, cached in ((outside, False), (self.project / 'out/cfg.h', False),
                               (self.project / 'include/cfg.h', True)):
            with self.subTest(target=target.name, folder=target.parent.name):
                write(target, 'ok\n')
                link = self.project / 'cfg.h'
                if os.path.lexists(link):
                    link.unlink()
                os.symlink(target, link)
                before = builds()
                for _ in range(2):
                    result = subprocess.run(['sh', 'scripts/check.sh'], cwd=self.project, env=environment(self.build),
                                            capture_output=True, text=True, encoding='utf-8', errors='replace',
                                            timeout=120)
                    out = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 0, out)
                self.assertEqual(builds() - before, 1 if cached else 2, out)
                self.assertEqual('is a symlink to a file outside the tree or in an ignored folder' in out, not cached, out)
                write(target, 'bad\n')
                result = subprocess.run(['sh', 'scripts/check.sh'], cwd=self.project, env=environment(self.build),
                                        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
    # Declared, so the kit check prints its NOT RUN line and does not count it (issue #56).
    test_a_link_to_a_file_the_key_does_not_hash_turns_the_cache_off._kit_platform_skip = not SYMLINKS


if __name__ == '__main__':
    unittest.main()
