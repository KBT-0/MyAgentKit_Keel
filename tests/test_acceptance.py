"""Acceptance must reject absent, empty, and skipped required regression suites."""
import contextlib
import importlib.util
import io
import os
import shutil
import shlex
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kit_acceptance', ROOT / 'scripts/check_kit.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class AcceptanceTests(unittest.TestCase):
    def test_gate_launchers_refuse_python_3_10_and_accept_3_11(self):
        for path, marker in (('scripts/check.sh', '# Help ends'),
                             ('core/scripts/check.sh', '# SELF-TEST SEAMS')):
            source = (ROOT / path).read_text(encoding='utf-8').split(marker, 1)[0]
            # Keep the isolated POSIX probe in this shell so the Python stubs survive.
            source = source.replace('if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi\n', '')
            for version, status in (((3, 10), 1), ((3, 11), 0)):
                with self.subTest(path=path, version=version):
                    prefix = 'import sys; sys.version_info = %r; ' % (version,)
                    functions = ('python3() { [ "$1" != -I ] || shift; %s -c %s"$2"; }; '
                                 'python() { python3 "$@"; };\n'
                                 % (shlex.quote(Path(sys.executable).as_posix()), shlex.quote(prefix)))
                    result = subprocess.run(['sh', '-c', functions + source,
                                             str(ROOT / path)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                    if status:
                        self.assertIn('Python 3.11 or newer', result.stdout + result.stderr)

    def test_direct_kit_check_refuses_python_3_10_before_loading_the_gate(self):
        command = ('import sys, runpy; sys.version_info = (3, 10); '
                   'runpy.run_path(sys.argv[1], run_name="__main__")')
        result = subprocess.run([sys.executable, '-I', '-c', command,
                                 str(ROOT / 'scripts/check_kit.py'), '--help'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('Python 3.11 or newer', result.stdout + result.stderr)

    def test_existing_file_python_launcher_preserves_paths_and_py3_arguments(self):
        example = '\n'.join(line[4:] for line in
            (ROOT / 'core/scripts/boundary_selftests.sh').read_text(encoding='utf-8').splitlines()
            if line.startswith('# | ')) + '\n'
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            (project / 'scripts').mkdir(parents=True)
            (project / 'src/domain').mkdir(parents=True)
            source = project / 'src/domain/existing.py'
            source.write_text('original\n', encoding='utf-8')
            tools = Path(tmp) / 'tools'
            tools.mkdir()
            spaced = tools / 'python with spaces'
            spaced.write_text('#!/bin/sh\nexec %s "$@"\n' % shlex.quote(Path(sys.executable).as_posix()),
                              encoding='utf-8')
            spaced.chmod(0o755)
            (tools / 'py').write_text('#!/bin/sh\n[ "$1" = -3 ] || exit 9\nshift\n'
                                      'exec %s "$@"\n' % shlex.quote(Path(sys.executable).as_posix()),
                                      encoding='utf-8')
            (tools / 'py').chmod(0o755)
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'])
            for launcher in (spaced.as_posix(), 'py -3'):
                with self.subTest(launcher=launcher):
                    # python3 is the enclosing gate's fallback function; probe_env
                    # must invoke the resolved executable, including its argument.
                    (project / 'scripts/check.sh').write_text(
                        'if [ "${1:-}" = --self-test ]; then\nst_fail=0\n'
                        'kit_python=%s\npython3() { %s "$@"; }\n' %
                        (shlex.quote(launcher), shlex.quote(Path(sys.executable).as_posix())) +
                        example + '\nexit "$st_fail"\nfi\n'
                        "grep -q myapp.web src/domain/existing.py || exit 0\n"
                        "echo 'FAIL [boundary]: the domain layer imports the web layer:'\nexit 1\n",
                        encoding='utf-8')
                    gate.run(['git', 'init', '-q'], project)
                    gate.run(['git', 'add', '.'], project)
                    before = gate.run(['git', 'status', '--porcelain'], project)
                    out = gate.run(['sh', 'scripts/check.sh', '--self-test'], project, env=env,
                                   reason='  ok   — domain/web boundary gate rejects')
                    self.assertNotIn('  FAIL — ', out)
                    self.assertEqual(source.read_text(encoding='utf-8'), 'original\n')
                    self.assertEqual(gate.run(['git', 'status', '--porcelain'], project), before)

    def test_existing_file_example_reports_a_red_baseline_and_never_counts_it(self):
        # Use the gate's own launcher selection, as WindowsBoundaryProbeTests does.
        check = (ROOT / 'core/scripts/check.sh').read_text(encoding='utf-8')
        start = check.index("if python3 -I -c '' </dev/null")
        resolve = check[start:check.index('\n', check.index('python3() { $kit_python "$@"; }'))]
        example = '\n'.join(line[4:] for line in
            (ROOT / 'core/scripts/boundary_selftests.sh').read_text(encoding='utf-8').splitlines()
            if line.startswith('# | ')) + '\n'
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            (project / 'scripts').mkdir(parents=True)
            (project / 'src/domain').mkdir(parents=True)
            source = project / 'src/domain/existing.py'
            source.write_text('original\n', encoding='utf-8')
            # A normal copied gate must explain its own failure. The probe must not
            # treat an unrelated failure as proof that the injected boundary works.
            # Use a supported python3-only host layout, independent of the caller's
            # Python aliases. The wrappers run the real utilities, not test doubles.
            tools = Path(tmp) / 'tools'
            tools.mkdir()
            shell = shutil.which('sh')
            for name in ('sh', 'env', 'git', 'uname', 'mktemp', 'cp', 'awk', 'sed',
                         'xargs', 'mkdir', 'mv', 'rm', 'cat', 'dirname', 'basename', 'ln', 'python3'):
                program = sys.executable if name == 'python3' else shutil.which(name)
                self.assertIsNotNone(program, name)
                wrapper = tools / name
                wrapper.write_text('#!/bin/sh\nexec %s "$@"\n' %
                                   shlex.quote(Path(program).as_posix()), encoding='utf-8')
                wrapper.chmod(0o755)
            env = dict(os.environ, PATH=str(tools))
            gate.run([shell, '-c', 'command -v python3 && ! command -v python && ! command -v py'],
                     project, env=env)
            (project / 'scripts/check.sh').write_text(
                'if [ "${1:-}" = --self-test ]; then\n'
                'st_fail=0\n' + resolve + '\n' +
                example + '\nexit "$st_fail"\nfi\n' +
                "echo 'FAIL [build]: diagnostic from the disposable baseline'\nexit 7\n",
                encoding='utf-8')
            gate.run(['git', 'init', '-q'], project)
            gate.run(['git', 'add', '.'], project)
            before = gate.run(['git', 'status', '--porcelain'], project)
            out = gate.run([shell, 'scripts/check.sh', '--self-test'], project, env=env,
                           expected=1, reason='the baseline is already red')
            self.assertIn('FAIL [build]: diagnostic from the disposable baseline', out)
            self.assertNotIn('  ok   — ', out)
            self.assertEqual(source.read_text(encoding='utf-8'), 'original\n')
            self.assertEqual(gate.run(['git', 'status', '--porcelain'], project), before)

    def test_required_suites_cannot_disappear_or_skip(self):
        for case in ('missing', 'empty', 'skipped', 'runtime_skip', 'pass'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'tests').mkdir()
                name = 'test_required_' + case
                if case != 'missing':
                    code = 'import unittest\n'
                    if case != 'empty':
                        code += 'class Required(unittest.TestCase):\n'
                        if case == 'skipped':
                            code += '    @unittest.skip("fixture skip")\n'
                        code += '    def test_protection(self):\n'
                        code += ('        self.skipTest("fixture skip")\n' if case == 'runtime_skip'
                                 else '        self.assertTrue(True)\n')
                    (root / 'tests' / (name + '.py')).write_text(code)
                if case == 'pass':
                    gate.run_tests(root, 'tests', {name: 1})
                else:
                    with self.assertRaisesRegex(RuntimeError, 'required|skipped'):
                        gate.run_tests(root, 'tests', {name: 1})

    def test_syntax_skips_ignored_python_shell_and_shebang_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate.run(['git', 'init', '-q'], root)
            (root / '.gitignore').write_text('ignored/\n', encoding='utf-8')
            ignored = root / 'ignored'
            ignored.mkdir()
            (ignored / 'bad.py').write_text('\ufeffbroken =\n', encoding='utf-8')
            (ignored / 'bad.sh').write_text('if then\n', encoding='utf-8')
            (ignored / 'hook').write_text('#!/bin/sh\necho "$x"\n', encoding='utf-8')
            gate.check_syntax(root)

    def test_syntax_checks_untracked_not_ignored_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate.run(['git', 'init', '-q'], root)
            source = root / 'new module.py'
            source.write_text('broken =\n', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'new module.py is not Python 3.11 syntax'):
                gate.check_syntax(root)

    def test_syntax_checks_tracked_shell_even_when_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate.run(['git', 'init', '-q'], root)
            (root / 'tracked.sh').write_text('if then\n', encoding='utf-8')
            gate.run(['git', 'add', 'tracked.sh'], root)
            (root / '.gitignore').write_text('*.sh\n', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'tracked.sh'):
                gate.check_syntax(root)

    def test_shell_sensor_checks_untracked_not_ignored_shebang_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate.run(['git', 'init', '-q'], root)
            (root / 'new hook').write_text('#!/bin/sh\necho "$x"\n', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'new hook:2: `echo` of an expansion'):
                gate.check_syntax(root)

    def test_python_newer_than_3_11_is_refused(self):
        # The parse used the host's grammar: syntax newer than 3.11, the oldest CI runs,
        # passed here and broke only on CI.
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'module.py'
            source.write_text('match value:\n    case 1:\n        pass\n')
            gate.check_syntax(Path(tmp))
            source.write_text('try:\n    pass\nexcept* ValueError:\n    pass\n')
            gate.check_syntax(Path(tmp))
            source.write_text('type Alias = int\n')
            with self.assertRaisesRegex(RuntimeError, 'is not Python 3.11 syntax'):
                gate.check_syntax(Path(tmp))

    def test_the_shell_lint_refuses_echo_of_a_variable_and_gnu_mktemp(self):
        refused = [r'echo "$x"', r'echo $x', r'x=1; echo "a $x b" >&2', r'echo -n "$x"',
                   r'echo -n -e "$x"', r'echo FAIL: "$x"', r'echo "a" "$x"', r'echo >&2 "$x"', r'echo "$x">&2',
                   r'x=`echo "$y"`', r'echo "$(cmd)"', r'echo \"in a string $x\"', 'echo \\\n  "$x"',
                   'echo "text \\\n$x"', r'echo "C:\new"', r"echo 'a\nb'", r'echo a\\b',
                   r'# |   probe_fail() { echo "  FAIL: $*"; exit 1; }',
                   r't=$(mktemp -p "$d")', r'mktemp --suffix .txt', r'mktemp --tmpdir x.XXXXXX',
                   r't=$(mktemp -dp "$d")', 'mktemp -d \\\n  -p "$d"', r'mktemp -t x']
        allowed = [r'# echo "$x"', r"echo '$x'", r'echo "no variable"', r"printf '%s\n' "'"$x"',
                   r'echo report > "$repo/x"', r'echo hi >&2', r'echo "a" 2>"$log"', r'echo a>"$log"', r'echo',
                   r'echo "\$HOME"', r'echo "a \"q\" b"', r'echo x; y="$z"',
                   r't=$(mktemp "${TMPDIR:-/tmp}/x.XXXXXX")', r'mktemp -d']
        for line in refused:
            with self.subTest(line=line):
                self.assertEqual([number for number, _ in gate.shell_lint(line + '\n')], [1])
        for line in allowed:
            with self.subTest(line=line):
                self.assertEqual(gate.shell_lint(line + '\n'), [])

    def test_a_refusal_added_without_a_test_change_gets_a_note(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
            root = Path(tmp)
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
            git = lambda *args: subprocess.run(['git', '-C', tmp, *args], env=env, check=True,
                                               capture_output=True)
            git('init', '-q', '-b', 'main')
            git('-c', 'user.name=t', '-c', 'user.email=t@x', 'commit', '-q', '--allow-empty', '-m', 'base')
            with unittest.mock.patch.dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1'):
                self.assertEqual(gate.untested_guards(root), [])
                self.assertIn('NOT RUN: the killing-test note', out.getvalue())
                git('branch', 'upstream')
                git('branch', '-q', '--set-upstream-to=upstream')
                (root / 'tool.py').write_text('x = 1\nif x:\n    raise ValueError(x)\nsys.exit(0)\n',
                                              encoding='utf-8')
                (root / 'gate.sh').write_text('[ -n "$x" ] || exit 2\n', encoding='utf-8')
                (root / 'README.md').write_text('raise ValueError\n', encoding='utf-8')
                git('add', '-A')
                notes = gate.untested_guards(root)
                self.assertEqual([note.split(' adds')[0] for note in notes],
                                 ['NOTE [killing test]: gate.sh:1', 'NOTE [killing test]: tool.py:3'])
                self.assertIn(notes[0], out.getvalue())
                (root / 'tests').mkdir()
                (root / 'tests/test_tool.py').write_text('', encoding='utf-8')
                git('add', '-A')
                self.assertEqual(gate.untested_guards(root), [])
        # The wiring: the kit check asks, not only this test.
        with unittest.mock.patch.object(gate, 'untested_guards') as asked, \
                unittest.mock.patch.object(gate, 'check_syntax'), \
                unittest.mock.patch.object(gate, 'run', return_value=''), \
                unittest.mock.patch.object(gate, 'run_units', return_value=False), \
                unittest.mock.patch.object(gate.sys, 'argv', ['check_kit.py']), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(), 1)
        asked.assert_called_once_with(gate.ROOT)

    def test_a_moved_file_and_the_owners_diff_config_change_no_note(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp)
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
            git = lambda *args: subprocess.run(['git', '-C', tmp, *args], env=env, check=True,
                                               capture_output=True)
            git('init', '-q', '-b', 'main')
            (root / 'tool.py').write_text('x = 1\nraise ValueError(x)\n', encoding='utf-8')
            git('add', '-A')
            git('-c', 'user.name=t', '-c', 'user.email=t@x', 'commit', '-q', '-m', 'base')
            git('branch', 'upstream')
            git('branch', '-q', '--set-upstream-to=upstream')
            with unittest.mock.patch.dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1'):
                # A move adds no refusal; its old lines are not new ones.
                git('mv', 'tool.py', 'moved.py')
                self.assertEqual(gate.untested_guards(root), [])
                # The owner's prefixes and quoting change no path; a name with a space ends in a tab.
                git('config', 'diff.noprefix', 'true')
                git('config', 'diff.mnemonicPrefix', 'true')
                utf8 = sys.getfilesystemencoding().lower().replace('-', '') == 'utf8'
                name = 'my tööl.sh' if utf8 else 'my tool.sh'
                (root / name).write_text('x=1\n[ -n "$x" ] || exit "$rc"\n', encoding='utf-8')
                git('add', '-A')
                self.assertEqual([note.split(' adds')[0] for note in gate.untested_guards(root)],
                                 ['NOTE [killing test]: %s:2' % name])

    def test_shell_portability_fails_on_a_lint_hit_and_on_a_bashism(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out, \
                unittest.mock.patch.dict(os.environ):
            # CI=true on GitHub's runners: the NOT RUN case below is a developer's host.
            os.environ.pop('CI', None)
            script = Path(tmp) / 'a.sh'
            script.write_text('#!/bin/sh\nx=1\nprintf \'%s\\n\' "$x"\n', encoding='utf-8')
            # A hook has no extension; its sh shebang brings it in, a bash one does not.
            (Path(tmp) / 'hook').write_text('#!/usr/bin/env sh\nprintf x\n', encoding='utf-8')
            (Path(tmp) / 'tool').write_text('#!/bin/bash\necho "$x"\n', encoding='utf-8')
            gate.shell_portability(Path(tmp))
            script.write_text('#!/bin/sh\nx=1\necho "$x"\n', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, r'a\.sh:3: `echo` of an expansion'):
                gate.shell_portability(Path(tmp))
            # The wiring: the kit check runs the sensor, not only this test.
            with self.assertRaisesRegex(RuntimeError, r'a\.sh:3: `echo` of an expansion'):
                gate.check_syntax(Path(tmp))
            script.write_text('#!/bin/sh\nx=1\nprintf x\n', encoding='utf-8')
            (Path(tmp) / 'hook').write_text('#!/usr/bin/env sh\nx=1\necho "$x"\n', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, r'hook:3: `echo` of an expansion'):
                gate.shell_portability(Path(tmp))
            (Path(tmp) / 'hook').unlink()
            script.write_text('#!/bin/sh\nx=1\nif [[ $x = 1 ]]; then :; fi\n', encoding='utf-8')
            if shutil.which('shellcheck'):
                # A developer's SHELLCHECK_OPTS (or rc file) cannot hide the code.
                with unittest.mock.patch.dict(os.environ, SHELLCHECK_OPTS='-S error -e SC3010'), \
                        self.assertRaisesRegex(RuntimeError, r'SC3010'):
                    gate.shell_portability(Path(tmp))
            with unittest.mock.patch.object(gate.shutil, 'which', return_value=None):
                gate.shell_portability(Path(tmp))
                self.assertIn('NOT RUN: shellcheck -s sh', out.getvalue())
                with unittest.mock.patch.dict(os.environ, CI='true'), \
                        unittest.mock.patch.object(gate.sys, 'platform', 'linux'), \
                        self.assertRaisesRegex(RuntimeError, 'shellcheck is not on PATH'):
                    gate.shell_portability(Path(tmp))

    def test_the_case_lint_passes_an_argument_case_on_this_host(self):
        # On Windows a bare `bash` is WSL's launcher, and a text pipe writes CRLF: either could make
        # this argument a finding. The bash used there is Git's, beside the gate's sh.
        self.assertEqual(gate.case_in_substitution('if :; then\n x=$(echo case)\nfi\n'), [])
        if os.name == 'nt':
            self.assertEqual(Path(gate.bash_5_2()).parent, Path(shutil.which('sh')).parent)

    def test_every_suite_is_required_at_its_current_count(self):
        # A minimum far below its suite (1 of 30 tests) let the suite lose almost every test
        # with the kit check still green: each minimum is the suite's count, and a new test
        # raises it in the same change.
        for directory, required in gate.REQUIRED_SUITES.items():
            with self.subTest(directory=directory):
                # On native Windows the suites not yet ported there are left out (issue #56).
                leave_out = set(gate.NOT_ON_WINDOWS.get(directory, {}))
                suite, found = gate.discover(ROOT / directory, leave_out)
                # Minimums describe executable coverage on this platform. A declared
                # POSIX exclusion is discovered on Windows but cannot count toward it.
                for test in gate._cases(suite):
                    if getattr(getattr(test, test._testMethodName), '_kit_platform_skip', False):
                        found[test.id().split('.')[0]] -= 1
                self.assertEqual({k: v for k, v in required.items() if k not in leave_out}, found)

    def test_a_utf8_locale_is_picked_by_its_codeset_and_none_is_not_run(self):
        # Only four locale names counted: a host with de_DE.UTF-8 alone failed acceptance.
        self.assertEqual(gate.utf8_locale(['C', 'POSIX', 'de_DE.UTF-8']), 'de_DE.UTF-8')
        self.assertEqual(gate.utf8_locale(['en_GB.iso885915', 'sr_RS.utf8@latin']), 'sr_RS.utf8@latin')
        self.assertEqual(gate.utf8_locale(['fr_FR.Utf-8', 'C.UTF-8']), 'C.UTF-8')
        with self.assertRaisesRegex(RuntimeError, 'NOT RUN'):
            gate.utf8_locale(['C', 'POSIX', 'en_US.iso885915', 'utf8'])

    def test_the_kit_check_never_reads_a_stale_pyc_from_the_tree(self):
        # A module edited within the same second at the same size was read from its stale
        # `.pyc`, even under `python3 -B` (-B stops writing, not reading). The top of the kit
        # check, run as a script up to `ROOT =`, must see the new source, and so must a child.
        import os
        import subprocess
        import sys
        top = (ROOT / 'scripts/check_kit.py').read_text().split('\nROOT =')[0]
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / 'stale_probe.py'
            # Without the prefix a kit check run hands its children, so the pyc lands in the tree.
            env = {k: v for k, v in os.environ.items() if k != 'PYTHONPYCACHEPREFIX'}
            module.write_text('X = 1\n')
            subprocess.run([sys.executable, '-c', 'import stale_probe'], cwd=tmp, env=env, check=True)
            stamp = module.stat().st_mtime_ns
            module.write_text('X = 2\n')
            os.utime(module, ns=(stamp, stamp))
            probe = [sys.executable, '-B', '-c', 'import stale_probe; print(stale_probe.X)']
            stale = subprocess.run(probe, cwd=tmp, env=env, capture_output=True, text=True)
            self.assertEqual(stale.stdout, '1\n', 'the stale-pyc condition was not produced')
            code = (top + '\nimport stale_probe, subprocess\nprint(stale_probe.X, sys.pycache_prefix, flush=True)\n'
                    'subprocess.run(%r, check=True)\n' % probe)
            seen = subprocess.run([sys.executable, '-B', '-c', code], cwd=tmp, env=env,
                                  capture_output=True, text=True)
            self.assertEqual(seen.returncode, 0, seen.stderr)
            first, child = seen.stdout.splitlines()
            value, folder = first.split(' ', 1)
            self.assertEqual((value, child), ('2', '2'), 'the kit check read the stale .pyc')
            self.assertFalse(os.path.exists(folder), 'the private pycache folder was left behind')

    def test_windows_self_test_rejects_failures_outside_case_lines(self):
        if os.name != 'nt':
            sys.stderr.write('\nNOT RUN: %s (native Windows only)\n' % self.id())
            return
        real_run = gate.run
        real_read = Path.read_text

        class SelfTestAccepted(AssertionError):
            pass

        for boundary in ("echo 'FAIL [boundary]: regression'; st_fail=1\n", 'st_fail=1\n', ':\n'):
            reached = []

            def read(path, *args, **kwargs):
                if reached and path.name == 'status.log':
                    raise SelfTestAccepted('the kit accepted the self-test exit status')
                return real_read(path, *args, **kwargs)

            def run(args, cwd=gate.ROOT, **kwargs):
                if reached:
                    raise SelfTestAccepted('the kit accepted the self-test exit status')
                if args == ['sh', 'scripts/check.sh', '--self-test']:
                    reached.append(True)
                    # Exercise the actual self-test tail, without running the unrelated,
                    # expensive earlier cases or the prohibited existing-file example.
                    gate = (cwd / 'scripts/check.sh').read_text()
                    # The review self-test now runs natively too. This regression tests
                    # boundary status propagation; acceptance separately runs the real
                    # review suite, so start after that unrelated, expensive suite.
                    start = gate.index('  if [ -f "$BOUNDARY_SELFTESTS_FILE" ]; then')
                    tail = gate[start:gate.index('\n}\n', start)]
                    script = cwd / '.git/tail.sh'
                    script.write_text('work=$(mktemp -d)\ntrap \'rm -rf "$work"\' EXIT\n'
                                      'BOUNDARY_CHECKS_FILE=scripts/boundary_checks.sh\n'
                                      'BOUNDARY_SELFTESTS_FILE=scripts/boundary_selftests.sh\n'
                                      'self_test() {\nst_fail=0\n' + tail + '\n}\nself_test\n')
                    (cwd / 'scripts/boundary_selftests.sh').write_text(boundary)
                    return real_run(['sh', str(script)], cwd, **kwargs)
                return real_run(args, cwd, **kwargs)

            with self.subTest(boundary=boundary), unittest.mock.patch.object(gate, 'run', side_effect=run), \
                    unittest.mock.patch.object(Path, 'read_text', read), \
                    contextlib.redirect_stdout(io.StringIO()):
                if boundary == ':\n':
                    with self.assertRaises(SelfTestAccepted):
                        gate.acceptance(True)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'SELF-TEST: FAIL'):
                        gate.acceptance(True)
                self.assertEqual(reached, [True])

    def test_the_wrapper_fails_a_run_that_exits_0_without_its_pass_line(self):
        # A self-test once exited 0 without printing KIT CHECK: PASS, and the caller saw a pass.
        for case, body in (('silent', 'exit 0\n'), ('passed', ': > "$KIT_CHECK_PASSED"\n'),
                           ('failed', 'exit 3\n')):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'scripts').mkdir()
                shutil.copy(ROOT / 'scripts/check.sh', root / 'scripts/check.sh')
                (root / 'bin').mkdir()
                for name in ('python3', 'python'):
                    (root / 'bin' / name).write_text('#!/bin/sh\ncase \"$*\" in *version_info*) exit 0 ;; esac\n' + body)
                    (root / 'bin' / name).chmod(0o755)
                result = subprocess.run(['sh', 'scripts/check.sh'], cwd=root, capture_output=True, text=True,
                                        env=dict(os.environ, PATH=str(root / 'bin') + os.pathsep + os.environ['PATH']))
                self.assertEqual(result.returncode, {'silent': 1, 'passed': 0, 'failed': 3}[case],
                                 result.stdout + result.stderr)
                self.assertEqual('without reaching its PASS line' in result.stderr, case == 'silent')

    def test_packaging_suite_is_required_by_the_real_gate(self):
        self.assertGreaterEqual(gate.REQUIRED_SUITES['tests']['test_packaging'], 1)

    def test_the_record_marks_covered_limitations_superseded_and_names_real_tests(self):
        # The record still listed the Popen-window orphan and a syntax-only Stop hook check as
        # current after both had regressions, and readers could not tell history from a gap.
        import re
        record = (ROOT / 'docs/ACCEPTANCE.md').read_text()
        for bullet in re.split(r'\n- ', record):
            if 'inside `Popen`' in bullet or 'exit-75' in bullet:
                self.assertIn('Superseded', bullet, bullet)
        cited = re.findall(r'`([\w/]+\.py)`\s*\(`(test_\w+)`\)', record)
        self.assertTrue(cited, 'the superseded statements name no covering test')
        for path, name in cited:
            self.assertIn('def %s(' % name, (ROOT / path).read_text(), path)
