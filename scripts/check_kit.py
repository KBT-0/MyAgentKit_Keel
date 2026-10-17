#!/usr/bin/env python3
"""Offline kit acceptance: syntax, packaged source, regression tests, and bootstrap gates."""
import signal
import sys

# SIGTERM must unwind the runner and run atexit, including its private cache cleanup.
if __name__ == '__main__':
    if sys.version_info < (3, 11):
        raise SystemExit('KIT CHECK: FAIL - Python 3.11 or newer is required')

    def terminate(sig, frame):
        raise SystemExit(128 + sig)
    signal.signal(signal.SIGTERM, terminate)

import argparse
import ast
import atexit
import functools
try:
    import fcntl
except ImportError:  # Native Windows: the gate lock there is test_check_gate_windows's.
    fcntl = None
import json
import io
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, redirect_stdout
from threading import Lock

# Native Windows reads text in the ANSI code page, and the kit's files are UTF-8: the kit check
# and its units run in UTF-8 mode there. Only these processes do; the scripts under test run as
# a user's Python runs them.
if __name__ == '__main__' and os.name == 'nt' and not sys.flags.utf8_mode:
    raise SystemExit(subprocess.call([sys.executable, '-X', 'utf8', *sys.orig_argv[1:]]))
# The suites write their fixtures as the kit's own files are, with LF line ends. Native Windows
# writes text as CRLF, and a stub reading `exit 1\r` is another script: Path.write_text in the
# kit check's own processes keeps "\n" there. The scripts under test are not affected.
if os.name == 'nt':
    _write_text = Path.write_text

    def _lf_write_text(self, data, encoding=None, errors=None, newline='\n'):
        return _write_text(self, data, encoding, errors, newline)
    Path.write_text = _lf_write_text

# A module edited within the same second at the same size was read from its stale `.pyc`,
# even under `-B` (it stops writing, not reading). The kit check and every child it starts
# look for bytecode in a fresh folder of their own, so the tree's __pycache__ is never read.
# A unit inherits its parent's folder; the parent removes it at exit.
if __name__ == '__main__' and '--unit' not in sys.argv:
    _PYCACHE = tempfile.mkdtemp(prefix='myagentkit-pycache-')
    os.environ['PYTHONPYCACHEPREFIX'] = sys.pycache_prefix = _PYCACHE
    atexit.register(shutil.rmtree, _PYCACHE, True)

# A kit check started inside a hook, where git exports GIT_INDEX_FILE, or with GIT_DIR
# exported, ran every synthetic project's git against the caller's repository: a fixture's
# `git add -A` wrote the caller's index. Each variable that routes git to a repository (git's
# `rev-parse --local-env-vars`, and two it leaves out) is dropped here, for every unit and
# test. GIT_CONFIG* stays, as in the gate's own documentation-only check.
for _name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_IMPLICIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY',
              'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_COMMON_DIR', 'GIT_GRAFT_FILE', 'GIT_NO_REPLACE_OBJECTS',
              'GIT_REPLACE_REF_BASE', 'GIT_PREFIX', 'GIT_SHALLOW_FILE', 'GIT_INTERNAL_SUPER_PREFIX',
              'GIT_NAMESPACE', 'GIT_CEILING_DIRECTORIES', 'MYAGENTKIT_BACKEND'):
    os.environ.pop(_name, None)
# scripts/check.sh names a file to create once all units pass; popped here, so a
# nested kit check (a unit, a test) never creates it in the outer run's place.
_PASSED_FILE = os.environ.pop('KIT_CHECK_PASSED', None)

ROOT = Path(__file__).resolve().parents[1]
# The review self-test ships to projects with its own minimums; read them, never copy them.
BRIDGE_MINIMUMS = next(
    (ast.literal_eval(node.value)
     for node in ast.parse((ROOT / 'core/scripts/test_claude_bridge.py').read_text(encoding='utf-8')).body
     if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', None) == ('WINDOWS_SUITE_MINIMUMS' if os.name == 'nt' else 'SUITE_MINIMUMS')),
    None)
if BRIDGE_MINIMUMS is None:
    sys.exit('KIT CHECK: FAIL — SUITE_MINIMUMS not found in core/scripts/test_claude_bridge.py')
REQUIRED_SUITES = {
    'core/scripts': dict(BRIDGE_MINIMUMS, test_agent_cost=5, test_context_buckets=6, test_owns_check=4),
    # Each suite's current count: a minimum far below it (1 of 30) let a suite lose almost
    # every test with the kit check green. A new test raises its suite's number here.
    'tests': {'test_packaging': 1, 'test_bootstrap': 36, 'test_acceptance': 22,
              'test_review_upgrade': 4 if os.name == 'nt' else 5,
              'test_boundary_example': 2 if os.name == 'nt' else 3, 'test_scan_gate': 1,
              'test_check_gate': 24, 'test_check_gate_windows': 39 if os.name == 'nt' else 6,
              'test_boundary_restore': 35 if os.name == 'nt' else 40,
              'test_sync_kit': 33, 'test_doctor': 6, 'test_git_hooks': 31, 'test_stop_hook': 9, 'test_context_hook': 12, 'test_communication_hooks': 26, 'test_overlay_permissions': 8, 'test_guard_destructive_git': 26, 'test_guard_boundaries': 1, 'test_guard_private_email': 5,
              'test_spawn_worker': 46 if os.name == 'nt' else 66, 'test_spawn_codex': 54, 'test_codex_worker': 54, 'test_working_mode': 49, 'test_worker_visibility': 68, 'test_doc_pointers': 11,
              'test_usage_summary': 25, 'test_done_audits': 2,
              'test_kit_output': 1, 'test_kit_runner': 36, 'test_clean_worktrees': 138, 'test_clean_worktrees_windows': 12 if os.name == 'nt' else 0, 'test_close_worker_windows': 22,
              'test_review_windows': 22 if os.name == 'nt' else 0, 'test_claude_sandbox': 26, 'test_worker_paths_windows': 10,
              'test_close_worker': 28, 'test_python_fallback': 2, 'test_selftest_status': 11},
}
# Suites that do not run on native Windows, each with the reason. There each one prints one
# NOT RUN line and is not imported; CI's Linux and macOS jobs run every one of them. A suite
# ported to Windows leaves this list in the same change (issue #56).
NOT_ON_WINDOWS = {
    'core/scripts': {},
    'tests': {'test_check_gate': 'the flock gate lock; tests/test_check_gate_windows proves the Windows lock',
              'test_clean_worktrees': 'POSIX process liveness; tests/test_clean_worktrees_windows proves Windows'},
} if os.name == 'nt' else {}
# test_bootstrap passes on native Windows but starts thousands of processes there: measured
# 2026-10-16 on an i7-12700H (20 logical CPUs), Python 3.13, Git 2.47.1, alone: 36 tests in 1580 s.
# A local check leaves it to CI, whose Windows job runs it (CI is set there).
if NOT_ON_WINDOWS and not os.environ.get('CI'):
    NOT_ON_WINDOWS['tests']['test_bootstrap'] = "about 26 minutes on Windows; CI's Windows job runs it too"


# --timing: each phase's and each suite's seconds, and a suite's ten slowest tests.
TIMES, SLOWEST, _mark = [], [], [time.monotonic()]


def passed(message):
    """Print a phase's PASS line and record the seconds since the previous one."""
    print('PASS: ' + message)
    mark(message)


def mark(label):
    now = time.monotonic()
    TIMES.append((label[:60], now - _mark[0]))
    _mark[0] = now


class TimedResult(unittest.TextTestResult):
    def startTest(self, test):
        self._started = time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        SLOWEST.append((time.monotonic() - self._started, test.id()))


def discover(folder, leave_out=()):
    """The suite under `folder` and the number of tests in each of its modules; the modules
    named in `leave_out` are not imported. Nested test modules are refused before discovery."""
    folder = Path(folder)
    # Linked packages are not a layout the kit supports (whether unittest discovery follows
    # them is not documented): refuse them, rather than pass without running their tests.
    def unreadable(error):
        raise error

    for parent, directories, _ in os.walk(folder, onerror=unreadable):
        for path in [Path(parent), *(Path(parent) / name for name in directories)]:
            junction = getattr(path, 'is_junction', None)
            linked = (junction() if junction else
                      getattr(path.lstat(), 'st_reparse_tag', 0) in
                      (stat.IO_REPARSE_TAG_MOUNT_POINT, stat.IO_REPARSE_TAG_SYMLINK))
            if path.is_symlink() or linked:
                raise RuntimeError('linked test directories are not supported: '
                                   + path.relative_to(folder).as_posix())
    nested = sorted(path.relative_to(folder).as_posix() for path in folder.rglob('test_*.py')
                    if path.parent != folder)
    if nested:
        raise RuntimeError('nested test modules are not supported: ' + ', '.join(nested)
                           + '; move test_*.py files to the suite folder top level')
    patterns = {path.name for path in folder.glob('test_*.py') if path.stem not in leave_out}
    suite = unittest.TestSuite(unittest.TestLoader().discover(str(folder), pattern=pattern)
                               for pattern in sorted(patterns))

    def cases(node):
        for item in node:
            if isinstance(item, unittest.TestSuite):
                yield from cases(item)
            else:
                yield item

    counts = {}
    for test in cases(suite):
        module = test.id().split('.')[0]
        counts[module] = counts.get(module, 0) + 1
    return suite, counts


def _cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _cases(item)
        else:
            yield item


def run_tests(root, directory, required):
    """Require executed suite minimums; only declared platform exclusions may skip.

    A skipped test never counts toward a minimum: a run that skipped or collected nothing is
    no pass (pytest exits 5 when it collects nothing, docs.pytest.org/en/stable/reference/
    exit-codes.html; unittest keeps skips apart from success, TestResult.skipped). A declared
    platform skip says so in its NOT RUN line (issue #56)."""
    folder = root / directory
    for name in required:
        if not (folder / (name + '.py')).is_file():
            raise RuntimeError('missing required test suite: ' + name)
    reasons = NOT_ON_WINDOWS.get(directory, {})
    leave_out = {name for name in reasons if name in required}
    for name in sorted(leave_out):
        print("NOT RUN: %s/%s on native Windows (%s); CI's Linux and macOS jobs run it"
              % (directory, name, reasons[name]))
    required = {name: minimum for name, minimum in required.items() if name not in leave_out}
    suite, found = discover(folder, leave_out)
    counts = {name: found.get(name, 0) for name in required}
    for name, minimum in required.items():
        if counts[name] < minimum:
            raise RuntimeError('required test suite is incomplete: ' + name)
    allowed = {test.id() for test in _cases(suite)
               if getattr(getattr(test, test._testMethodName), '_kit_platform_skip', False)}
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=TimedResult).run(suite)
    unexpected = []
    for test, reason in result.skipped:
        if test.id() not in allowed:
            unexpected.append(test.id())
        else:
            name = test.id().split('.')[0]
            if name in counts:
                counts[name] -= 1
            print('NOT RUN: %s (%s)' % (test.id(), reason))
    insufficient = [name for name, minimum in required.items() if counts[name] < minimum]
    if not result.wasSuccessful() or unexpected or insufficient:
        raise RuntimeError('required tests failed or were skipped:\n' + output.getvalue())
    # A pass prints one line; the per-test lines were kilobytes nobody read. A failure above
    # carries the whole log, the passing tests included.
    passed('%s ran %d tests, each suite at or above its minimum (%s)'
           % (directory, result.testsRun - len(result.skipped),
              ', '.join('%s %d' % item for item in sorted(required.items()))))


SCALE = "MYAGENTKIT_TEST_TIMEOUT_SCALE"


def limit(seconds):
    """A wall-clock bound on a child, times SCALE: a slow host sets it, and run_units multiplies
    it by the units running at once (three units on one CPU each take about three times as long)."""
    return seconds * float(os.environ.get(SCALE, "1"))


def degree(cpus, units):
    """How many units run at once. On a 3-CPU runner three at once took 300 s each and timed out;
    one after another is what passed there. GitHub's standard runners: macOS 3 vCPU, Linux and
    Windows 2 (private repositories) or 4 (public) (docs.github.com/en/actions/reference/runners/
    github-hosted-runners, read 2026-10-15). The 4 and 8 thresholds are the kit's own choice."""
    return 1 if cpus < 4 else min(2, units) if cpus < 8 else units


# A gate run that waits forever (a lock never released) must fail here, not hang the kit check.
def run(args, cwd=ROOT, expected=0, reason=None, env=None, timeout=300, **popen):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env,
                            timeout=limit(timeout), **popen)
    output = result.stdout + result.stderr
    if result.returncode != expected or (reason and reason not in output):
        raise RuntimeError(f"{args}: expected exit {expected}, reason {reason!r}\n{output}")
    return output


def utf8_locale(have=None):
    """A UTF-8 locale this host has, chosen by its codeset; none is NOT RUN, never a pass.

    Four fixed names once counted: a host with only de_DE.UTF-8 failed acceptance. The
    tests use this one selection too. C.UTF-8 first when present, else the first in order.
    """
    if have is None:
        # Read as UTF-8, replacing what is not: one name holding a Latin-1 byte raised in a strict
        # decode instead of letting the other names be chosen from.
        have = run(["locale", "-a"], encoding="utf-8", errors="replace").split()
    found = sorted((not name.startswith("C."), name) for name in have
                   if re.fullmatch(r"[^.]+\.utf-?8(@.*)?", name, re.IGNORECASE))
    if not found:
        raise RuntimeError("NOT RUN: the locale cases need a UTF-8 locale and `locale -a` lists none: "
                           + " ".join(have))
    return found[0][1]


# The locale sensor (proposal D-1): suites that read or write files, parse text or compare
# identifiers, and run in seconds, again where the default encoding is not UTF-8 (the kit's own
# record: 91 locale-class incidents, RESEARCH_LOG 2026-10-13). A slow suite stays out; its text
# paths are here. The class is old: Turkish dotless i broke case folds in Java and .NET
# (bugs.openjdk.org/browse/JDK-4183880). PEP 597 makes an encoding-less call a warning, and
# PEP 686 turns UTF-8 mode on by default from Python 3.15: when the kit's floor reaches 3.15,
# review the Windows ANSI branch.
LOCALE_SUITES = ('test_working_mode', 'test_usage_summary', 'test_doc_pointers', 'test_kit_output',
                 'test_python_fallback', 'test_overlay_permissions', 'test_context_hook',
                 'test_communication_hooks', 'test_guard_destructive_git', 'test_guard_private_email',
                 'test_git_hooks')


def locale_matrix(folder=None, suites=LOCALE_SUITES, minimums=None):
    """Run each of `suites` again under each locale a reviewer kept finding bugs in; a red one fails.

    PYTHONUTF8=0 everywhere: Python turns UTF-8 mode on by itself under LC_ALL=C, which hid an
    encoding-less open(). An encoding-less open, read_text, write_text or text subprocess is an
    error too (EncodingWarning, PEP 597), so the sensor bites on Windows, whose ANSI code page
    (cp1252, or UTF-8 when the system option is on) decodes most bytes without complaint. A POSIX
    host also runs a Turkish UTF-8 locale (dotless i in a case fold) when it has one, NOT RUN
    when not. Skipped tests do not count toward a suite's minimum.
    """
    folder = Path(folder or ROOT / 'tests')
    minimums = minimums or REQUIRED_SUITES['tests']
    if os.name == 'nt':
        cases = [('the ANSI code page with EncodingWarning an error', {})]
    else:
        cases = [('LC_ALL=C', {'LC_ALL': 'C', 'LANG': 'C'})]
        turkish = sorted(name for name in run(['locale', '-a'], errors='replace').split()
                         if re.fullmatch(r'tr_TR\.utf-?8', name, re.IGNORECASE))
        if turkish:
            cases.append(('LC_ALL=' + turkish[0], {'LC_ALL': turkish[0], 'LANG': turkish[0]}))
        else:
            print('NOT RUN: the locale suites under tr_TR.UTF-8: `locale -a` lists no Turkish UTF-8 locale')
    for label, extra in cases:
        env = {key: value for key, value in os.environ.items()
               if key not in ('PYTHONIOENCODING', 'LC_CTYPE', 'LC_ALL', 'LANG')}
        env.update(extra, PYTHONUTF8='0', PYTHONWARNDEFAULTENCODING='1', PYTHONWARNINGS='error::EncodingWarning')
        for name in suites:
            result = subprocess.run([sys.executable, '-B', '-m', 'unittest', name], cwd=folder, env=env,
                                    capture_output=True, text=True, encoding='utf-8', errors='replace',
                                    timeout=limit(600))
            output = result.stdout + result.stderr
            ran = re.search(r'^Ran (\d+) tests?', output, re.M)
            skipped = re.search(r'^(?:OK|FAILED) \(.*skipped=(\d+)', output, re.M)
            count = int(ran.group(1)) - int(skipped.group(1) if skipped else 0) if ran else 0
            if result.returncode or count < minimums[name]:
                raise RuntimeError('%s failed under %s (%d tests run, %d required):\n%s'
                                   % (name, label, count, minimums[name], output))
    passed('the locale suites ran under %s' % ', '.join(label for label, _ in cases))


def path_without(path, drop, links):
    """`path` with every command whose name `drop` selects removed; the rest resolve as before.

    A directory holding such a command is replaced by a directory under `links` holding links
    to its other entries; every other directory stays as it is, its entries never stat'ed.
    Linking every entry of every directory took minutes on a WSL host whose PATH holds Windows
    directories, each entry a slow stat. os.path.exists, not Path.exists: on Python before
    3.12 the latter raised on an entry it may not stat (macOS /usr/sbin/weakpass_edit), and a
    dangling link is left out.
    """
    kept = []
    for number, directory in enumerate(path.split(os.pathsep)):
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        if not any(drop(name) for name in names):
            kept.append(directory)
            continue
        copy = Path(links) / str(number)
        copy.mkdir(parents=True)
        for name in names:
            source = os.path.join(directory, name)
            if not drop(name) and os.path.exists(source):
                os.symlink(os.path.realpath(source), copy / name)
        kept.append(str(copy))
    return os.pathsep.join(kept)


def check_release(root):
    """The README's bold release line and the plugin manifest's version must name the newest
    version in the changelog (newest first: keepachangelog.com/en/2.0.0/).

    A remote marketplace keeps every user on the cached plugin until its manifest's version
    string changes (code.claude.com/docs/en/plugins-reference, `version`; plugins/loading,
    "Versions and updates"), and the kit's marketplace is the GitHub repository: the
    manifest carries the kit's MAJOR.MINOR as MAJOR.MINOR.PATCH (KARARLAR B11 inv3/(h),
    lead decision 4). The Codex manifest's generated version is not compared (decisions.md 3).
    """
    readme = re.search(r'^\*\*(v\d+\.\d+)\.\*\*', (root / 'README.md').read_text(encoding='utf-8'), re.M)
    changelog = re.search(r'^## (v\d+\.\d+)(?=\s|$)', (root / 'CHANGELOG.md').read_text(encoding='utf-8'), re.M)
    if not readme or not changelog or readme.group(1) != changelog.group(1):
        raise RuntimeError("README's bold version must match CHANGELOG's newest versioned heading")
    manifest = root / 'plugin/.claude-plugin/plugin.json'
    version = str(json.loads(manifest.read_text(encoding='utf-8')).get('version', ''))
    if not re.fullmatch(r'(\d+\.\d+)\.\d+', version) or 'v' + version.rsplit('.', 1)[0] != changelog.group(1):
        raise RuntimeError("plugin/.claude-plugin/plugin.json's version %r must be MAJOR.MINOR.PATCH with "
                           "CHANGELOG's newest version %s as MAJOR.MINOR" % (version, changelog.group(1)))


def validate_plugin(root):
    """The vendor's own validator over the Claude plugin, warnings as errors
    (code.claude.com/docs/en/plugins-reference, "Validate the manifest"; KARARLAR D08 inv2#178).
    Without the claude CLI on PATH (CI) it is NOT RUN, never a silent pass."""
    claude = shutil.which('claude')
    if not claude:
        print('NOT RUN: claude plugin validate plugin --strict (no claude CLI on PATH)')
        return
    run([claude, 'plugin', 'validate', 'plugin', '--strict'], cwd=root, encoding='utf-8', errors='replace')
    passed('claude plugin validate plugin --strict')


# A refusal a diff adds (proposal D-5): a raise, an exit with a nonzero status, die, a FAIL line.
GUARD = re.compile(r'\braise\s+\w|\bsys\.exit\(\s*[^0)\s]|\bexit\s+(?:[1-9]|"?\$)|\bdie\b|FAIL')


def untested_guards(root):
    """A NOTE, never a failure, for each refusal the change against upstream adds while no file
    under tests/ changes: which test fails if it is removed? Mutation-lite; staged and unstaged
    changes count, an untracked file does not (git diff does not list it; once added or
    committed it is noted on the next run). The owner's diff.noprefix, diff.mnemonicPrefix and core.quotePath do not
    change the paths read here. Informative, on the changed lines only, as Google's mutation
    testing shows surviving mutants in review without blocking (Petrović et al., Practical
    Mutation Testing at Scale). The regex is a proxy; a real mutation run on the changed lines
    is the upgrade path."""
    git = ['git', '-C', str(root), '-c', 'core.quotePath=false']
    found = subprocess.run(git + ['merge-base', 'HEAD', '@{upstream}'], capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
    if found.returncode != 0:
        print('NOT RUN: the killing-test note (no upstream branch to compare with)')
        return []
    base = found.stdout.strip()
    names = run(git + ['diff', '--name-only', '--no-renames', base], encoding='utf-8',
                errors='replace').splitlines()
    if any(name.startswith('tests/') for name in names):
        return []
    # A moved file adds no refusal: renames on, so its old lines are not shown as new.
    diff = run(git + ['diff', '-U0', '--no-color', '--no-ext-diff', '--no-textconv', '-M',
                      '--src-prefix=a/', '--dst-prefix=b/', base, '--', '.', ':(exclude)*.md'],
               encoding='utf-8', errors='replace')
    notes, path, number, hunk = [], None, 0, False
    for line in diff.splitlines():
        if line.startswith('diff --git '):
            path, hunk = None, False
        elif line.startswith('+++ ') and not hunk:
            # A header only before the file's first hunk: an added line `++ x` shows as `+++ x`.
            # A name with a space ends in a tab.
            path = line[6:].rstrip('\t') if line.startswith('+++ b/') else None
        elif line.startswith('@@'):
            number, hunk = int(re.search(r'\+(\d+)', line).group(1)), True
        elif line.startswith('+') and path:
            if GUARD.search(line):
                notes.append('NOTE [killing test]: %s:%d adds a refusal and no file under tests/ changed '
                             'against upstream; which test fails if it is removed?' % (path, number))
            number += 1
    for note in notes:
        print(note)
    return notes


def repository_files(root):
    """Tracked and untracked-but-not-ignored files, or plain files in a non-git fixture."""
    if (root / '.git').exists():
        listed = run(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others',
                      '--exclude-standard'], encoding='utf-8')
        candidates = (root / name for name in sorted(set(listed.split('\0'))) if name)
    else:
        candidates = (path for path in root.rglob('*') if '.git' not in path.parts)
    return [path for path in candidates if path.is_file()]


def check_syntax(root):
    """Parse the repo's .py files as Python 3.11 and its .sh files with `sh -n`.

    ast.parse alone used the host's grammar: syntax newer than 3.11 passed here and broke only
    on CI. feature_version is best effort (it rejects newer statements such as `type`,
    not every newer construct). `sh -n` is the host's sh, which is bash on many
    hosts: it proves the file parses, and a bashism that bash accepts passes; only dash
    (Ubuntu's sh, on CI) or a review catches that.
    """
    paths = repository_files(root)
    for path in paths:
        if path.suffix == '.py':
            try:
                ast.parse(path.read_text(encoding='utf-8'), filename=str(path), feature_version=(3, 11))
            except SyntaxError as error:
                raise RuntimeError("%s is not Python 3.11 syntax: %s" % (path, error)) from error
    bash_5_2()  # the lint's prerequisite, on every host, whether or not a file needs it
    for path in paths:
        if path.suffix == '.sh':
            # The lint first: macOS's sh rejects the form too, and the reason must name it there.
            try:
                # UTF-8, not the host's locale; newlines stay folded for an autocrlf checkout.
                lines = case_in_substitution(path.read_text(encoding='utf-8'))
            except RuntimeError as error:
                raise RuntimeError("%s: %s" % (path, error)) from error
            if lines:
                raise RuntimeError("%s: `case` inside $( ) on line %s: bash 3.2, macOS's sh, reads its "
                                   "pattern's `)` as the end of the $( ); move it out"
                                   % (path, lines[0]))
            run(["sh", "-n", str(path)])
    shell_portability(root)


# The shell sensor (proposal D-2). An `echo` argument that expands, or that reaches echo with a
# backslash: dash, Ubuntu's sh, reads the backslash as an escape, so a Windows path printed
# C:<newline>ew. mktemp -p/--suffix/--tmpdir are GNU-only and -t means another thing on macOS.
# Sources: POSIX echo (an operand with a backslash is implementation-defined; printf is advised:
# pubs.opengroup.org/onlinepubs/9699919799/utilities/echo.html), ShellCheck SC3037; the GNU/BSD
# mktemp difference (github.com/nushell/nushell/issues/10845).
ECHO_COMMAND = re.compile(r'(?:^|(?<=[;&|({`\s!]))echo(?=[\s;&|)`]|$)')
MKTEMP = re.compile(r'\bmktemp\b[^;|&\n]*\s(?:-[a-zA-Z]*[pt]|--suffix|--tmpdir)')
# A comment line, except the `# | ` example code boundary_selftests.sh ships and acceptance runs.
COMMENT = re.compile(r'^[ \t]*#(?! \|( |$)).*$', re.M)


def echo_hazard(text, i):
    """True when the echo whose arguments start at text[i] prints an expansion or a backslash.

    A small sh word reader: quotes, escapes and backslash-newline as sh reads them; the command
    ends at an unquoted newline, ; | & ) or `. A redirection and its target are not printed.
    """
    words, word, quote, target = [], None, None, False
    while i < len(text):
        c, nxt = text[i], text[i + 1:i + 2]
        if word is None and (quote or c not in ' \t'):
            word = {'hazard': False, 'redirect': target, 'operator_only': False}
            target = False
        if quote == "'":
            quote = None if c == "'" else quote
            word['hazard'] |= c == '\\'
        elif quote == '"':
            if c == '"':
                quote = None
            elif c == '\\':
                word['hazard'] |= nxt not in ('"', '$', '`', '\n')
                i += 1
            else:
                word['hazard'] |= c in '$`'
        elif c == '\\':
            if word is not None:
                word['hazard'] |= nxt == '\\'
            i += 2
            continue
        elif c in ' \t':
            if word is not None:
                words.append(word)
                target = word['redirect'] and word['operator_only']
                word = None
        elif c in '\n;|&)`':
            break
        elif c in '<>':
            # `>&2` names its target itself; a bare `>` takes the next word. What stands before
            # the operator (`"$x">&2`) is an argument; an fd number never sets hazard.
            if word['hazard'] and not word['redirect']:
                words.append(dict(word))
                word['hazard'] = False
            word['redirect'] = word['operator_only'] = True
            while text[i + 1:i + 2] in ('<', '>', '&', '|'):
                i += 1
                word['operator_only'] = text[i] != '&'
        else:
            word['operator_only'] = False
            word['hazard'] |= c == '$'
            if c in '\'"':
                quote, word['operator_only'] = c, False
        i += 1
    words.append(word or {'hazard': False, 'redirect': False})
    return any(w['hazard'] and not w['redirect'] for w in words)


def shell_lint(text):
    """(line, reason) for each place in a POSIX sh script the kit's own shell rules refuse."""
    text = COMMENT.sub('', text)
    line_of = lambda position: text.count('\n', 0, position) + 1
    found = [(line_of(m.start()), "`echo` of an expansion or a backslash: dash reads a backslash as "
                                  "an escape; use printf '%s\\n'")
             for m in ECHO_COMMAND.finditer(text) if echo_hazard(text, m.end())]
    # Two characters for the two of a backslash-newline: positions, and so line numbers, hold.
    joined = text.replace('\\\n', '  ')
    found += [(line_of(m.start()), '`mktemp -p/-t/--suffix/--tmpdir`: GNU-only, or -t means '
                                   'another thing on macOS')
              for m in MKTEMP.finditer(joined)]
    return sorted(found)


def shell_scripts(root):
    """The repo's .sh files and files whose first line runs sh (hooks have no extension).
    Ignored evidence and worktree copies are excluded; new, non-ignored scripts count."""
    found = []
    for path in repository_files(root):
        if path.suffix == '.sh':
            found.append(path)
        elif path.is_file() and not path.is_symlink():
            with path.open('rb') as handle:
                if re.match(rb'#!.*[/ ]sh(?:\s|$)', handle.readline(200)):
                    found.append(path)
    return found


def shell_portability(root):
    """The kit's shell lint and `shellcheck -s sh` over the repo's non-ignored sh scripts.

    shellcheck fails only on SC3xxx (undefined in POSIX sh, a bashism) and on errors; its
    warnings and notes stay a reviewer's. It reads no rc file and no SHELLCHECK_OPTS, so a
    developer's settings cannot hide a code. Without shellcheck the check is NOT RUN, except
    on CI's Linux job, whose image has it, where its absence fails.
    """
    paths = shell_scripts(root)
    found = ['%s:%d: %s' % (path.relative_to(root).as_posix(), number, reason)
             for path in paths for number, reason in shell_lint(path.read_text(encoding='utf-8'))]
    if found:
        raise RuntimeError('shell lint:\n' + '\n'.join(found))
    tool = shutil.which('shellcheck')
    if not tool:
        if os.environ.get('CI') and sys.platform.startswith('linux'):
            raise RuntimeError('shellcheck is not on PATH; CI\'s Linux image has it')
        print('NOT RUN: shellcheck -s sh (not installed); CI\'s Linux job runs it')
        return
    if not paths:
        return
    env = {k: v for k, v in os.environ.items() if k != 'SHELLCHECK_OPTS'}
    result = subprocess.run([tool, '--norc', '-s', 'sh', '-f', 'gcc', *map(str, paths)], capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=limit(300), env=env)
    refused = [line for line in result.stdout.splitlines()
               if ': error:' in line or re.search(r'\[SC3\d{3}\]$', line)]
    if refused or result.returncode not in (0, 1):
        raise RuntimeError('shellcheck -s sh: a bashism or an error:\n'
                           + '\n'.join(refused or [result.stdout + result.stderr]))


@functools.lru_cache(maxsize=None)
def bash_5_2():
    """The bash the case lint parses with, found once: 5.2 or later, the first bash whose -n
    parses what is inside $( ); 3.2 to 5.1 keep it as text and report no error there. On
    native Windows only Git's bash beside the gate's sh: a bare `bash` is WSL's launcher."""
    if os.name == "nt":
        sh = shutil.which("sh")
        tried = [str(Path(sh).with_name("bash.exe"))] if sh else []
    else:
        tried = [path for path in (shutil.which("bash"), "/opt/homebrew/bin/bash", "/usr/local/bin/bash") if path]
    for path in tried:
        try:
            version = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10,
                                     env=dict(os.environ, LC_ALL="C", LANG="C")).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        found = re.search(r",\s*\S+\s+(\d+)\.(\d+)", version)
        if found and (int(found[1]), int(found[2])) >= (5, 2):
            return path
    raise RuntimeError("the kit check's case lint needs bash 5.2 or later (macOS: brew install bash); "
                       "tried: %s" % (", ".join(tried) or "no bash, no sh on PATH"))


def case_in_substitution(text):
    """The lines where a `case` starts inside $( ). bash 3.2, macOS's sh, does not parse it, and
    the `sh -n` of a host with a newer shell passes it: one did, and only macOS CI failed.

    The scan locates unquoted candidates; bash 5.2+ (bash_5_2) parses the file, then for each
    candidate a copy with that `case` replaced by `esac`. A command's `case` so replaced breaks
    the grammar; an argument or an arithmetic variable does not. No copy is executed. A file
    that does not parse as it is fails with bash's own reason, so does a `$((` opening a
    substitution whose pattern's `)` ends it. Covered shapes: function f case -> finding;
    echo if case / echo -n case / echo $(x) case -> argument.
    Arithmetic is checked too, because `$((` can open a substitution containing a subshell.
    A file without a candidate starts no process."""
    candidates, stack, heredocs, i, line = [], [], [], 0, 1
    while i < len(text):
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            for strip, word in heredocs:  # Each body ends at a line that is its word alone.
                while i < len(text):
                    end = text.find("\n", i)
                    end = len(text) if end < 0 else end
                    body, i, line = text[i:end], end + 1, line + 1
                    if (body.lstrip("\t") if strip else body) == word:
                        break
            heredocs = []
        elif c == "\\":
            line += text[i + 1:i + 2] == "\n"
            i += 2
        elif text.startswith("$((", i):  # arithmetic: one entry per parenthesis, so `))` closes it
            stack += ["A", "A"]
            i += 3
        elif stack and stack[-1] == '"':
            if c == '"':
                stack.pop()
            elif text.startswith("$(", i):
                stack.append("$")
                i += 1
            i += 1
        elif c == "'":
            end = text.find("'", i + 1)
            end = len(text) if end < 0 else end
            line += text.count("\n", i, end)
            i = end + 1
        elif c == "#" and (i == 0 or text[i - 1] in " \t\n;"):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
        else:
            # Treat `<<` as a shift in $((; Bash resolves an ambiguous arithmetic opener below.
            arithmetic = next((s for s in reversed(stack) if s in "$A"), "") == "A"
            here = not arithmetic and re.match(r"<<(-?)[ \t]*['\"]?([A-Za-z0-9_]+)['\"]?", text[i:i + 80])
            word = (re.match(r"case(?=$|[ \t\n;&|(){}])", text[i:i + 5])
                    and (i == 0 or text[i - 1] in " \t\n;&|(){}"))
            if here:
                heredocs.append((here.group(1) == "-", here.group(2)))
                i += here.end()
                continue
            if word and any(s in "$A" for s in stack):
                candidates.append((i, line))
            if c == '"':
                stack.append('"')
            elif text.startswith("$(", i):
                stack.append("$")
                i += 1
            elif c == "(":
                stack.append("(")
            elif c == ")" and stack:
                stack.pop()
            i += 1
    if not candidates:
        return []
    bash = bash_5_2()

    def parse(source):
        # Bytes: a text pipe on Windows writes CRLF; bash must read the file's own bytes.
        try:
            return subprocess.run([bash, "--posix", "-n"], input=source.encode(),
                                  capture_output=True, timeout=10, env=dict(os.environ, LC_ALL="C", LANG="C"))
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError("cannot run %s --posix -n: %s" % (bash, error)) from error

    original = parse(text)
    if original.returncode:
        raise RuntimeError("bash --posix -n rejects the file as it is, before any `case` is "
                           "classified: %s" % original.stderr.decode(errors="replace").strip())
    return [line for i, line in candidates if parse(text[:i] + "esac" + text[i + 4:]).returncode]


def acceptance(self_test):
    """Bootstrap a synthetic project, prove its gates pass, and with self_test, prove them red.

    Each gate comes with cases that must fail and cases that must pass, as rule checkers test
    their rules (Semgrep's ruleid/ok, semgrep.dev/docs/writing-rules/testing-rules;
    docs/gates-must-be-proven-red.md)."""
    with tempfile.TemporaryDirectory(prefix="myagentkit-acceptance-") as tmp:
        project = Path(tmp)
        run(["sh", str(ROOT / "bootstrap.sh"), str(project)])
        run(["git", "init", "-q"], project)
        if not (project / "docs/BACKLOG.md").is_file():
            raise RuntimeError("bootstrap did not deliver the docs/BACKLOG.md template")
        output = run(["sh", "scripts/check.sh"], project, expected=1)
        if "FAIL" not in output:
            raise RuntimeError("fresh bootstrap did not reject absent configuration")
        # Synthetic acceptance only; real project setup still belongs to the interview.
        for path in project.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "setup" in path.parts:
                continue
            text = path.read_text(encoding='utf-8')
            text = text.replace("{{BUILD_TEST_COMMAND}}", "test -f scripts/claude_bridge.py")
            text = text.replace("{{TOOLCHAIN_PATH_SETUP}}", "")
            text = re.sub(r"\{\{[A-Z0-9_]+\}\}", "fixture", text)
            path.write_text(text, encoding='utf-8')
        (project / "scripts/boundary_checks.sh").write_text("# Synthetic project has no domain boundaries.\n", encoding='utf-8')
        (project / "scripts/boundary_selftests.sh").write_text("# Domain gates are project-specific.\n", encoding='utf-8')
        run(["git", "add", "."], project)
        run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS")
        # With CDPATH exported, `cd scripts` printed the directory into the gate's own path,
        # and the gate re-ran a two-line file name instead of its checks.
        run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", env=dict(os.environ, CDPATH="."))
        passed("bootstrap rejects missing setup and accepts the configured synthetic project")
        if self_test:
            with tempfile.TemporaryDirectory(prefix="myagentkit-side-") as side:
                side = Path(side)
                # A normal run refuses the self-test seams, so these cases set the build command
                # the way a project does, in the copy's check.sh: it runs side/build.sh, which
                # each case rewrites. Restored below; a failure discards the whole copy.
                build = side / "build.sh"
                gate = project / "scripts/check.sh"
                original_gate = gate.read_text(encoding='utf-8')
                configured = 'build_test_cmd="test -f scripts/claude_bridge.py"'
                if configured not in original_gate:
                    raise RuntimeError("the synthetic project's build command line was not found")
                fixture_gate = original_gate.replace(
                    configured, f'build_test_cmd="sh {shlex.quote(str(build))}"')
                gate.write_text(fixture_gate, encoding='utf-8')
                status = ["git", "status", "--porcelain", "--untracked-files=all"]
                before = run(status, project)
                # Every nested gate run records the tree through the build command, so a case
                # that writes into the tree and cleans up afterwards is still caught.
                log = side / "status.log"
                build.write_text(f'{{ git status --porcelain --untracked-files=all; echo ==; }} >> "{log}"\n', encoding='utf-8')
                # GATE_LOCK_WAIT: a nested run that does not inherit the lock stops in seconds.
                print(run(["sh", "scripts/check.sh", "--self-test"], project,
                          env=dict(os.environ, GATE_LOCK_WAIT="5"), reason="SELF-TEST: PASS",
                          # Real native review fixtures and Git startup take much longer
                          # than POSIX here. Keep a bound, scaled with concurrent units.
                          # D08 inv2#181: measured 2026-10-16 on an i7-12700H (20 logical CPUs):
                          # nested run 1357-1563 s serial; acceptance unit 1410 s with four
                          # units in parallel. Owner raised the Windows bound to 1800 s
                          # (close-out decisions.md 30a); POSIX stays at 300 s.
                          timeout=1800 if os.name == "nt" else 300).strip())
                seen = log.read_text(encoding='utf-8').split("==\n")[:-1]
                if not seen or any(s != before for s in seen) or run(status, project) != before:
                    raise RuntimeError("check.sh --self-test changed the working tree:\n"
                                       + "".join(s for s in seen if s != before))
                passed("git status of the project is unchanged at every nested gate run and after --self-test")
                # Every self-test seam exported into a normal run fails it by name, including
                # an override that would turn a red build green.
                seams = {"GATE_BUILD_CMD_OVERRIDE": "true", "GATE_SELFTEST_STATE_FILE": "docs/STATE.md",
                         "GATE_SELFTEST_PROJECT_FILE": "docs/PROJECT.md",
                         "BOUNDARY_CHECKS_FILE": "scripts/boundary_checks.sh",
                         "BOUNDARY_SELFTESTS_FILE": "scripts/boundary_selftests.sh",
                         "GATE_SELFTEST_EXTRA_FILE": "docs/STATE.md",
                         "GATE_SELFTEST_BREAK_SCANNER": "1", "GATE_SELFTEST_HISTORY": "."}
                build.write_text("false\n", encoding='utf-8')
                own_lock = os.path.realpath(project) + "/.git/check.lock"
                for name, value in seams.items():
                    refused = f"FAIL [env]: {name} is set; self-test overrides are not honoured"
                    for cmd in (["sh", "scripts/check.sh"], ["sh", "scripts/check.sh", "--self-test"]):
                        run(cmd, project, expected=1, reason=refused, timeout=60,
                            env=dict(os.environ, **{name: value}))
                    # A copied marker without the lock it names is no marker.
                    run(["sh", "scripts/check.sh"], project, expected=1, reason=refused, timeout=60,
                        env=dict(os.environ, GATE_SELFTEST_NESTED=str(os.getpid()),
                                 GATE_LOCK_HELD=own_lock, **{name: value}))
                passed("every self-test override exported into a normal run fails it by name")
                # The marker a self-test run exports dies with that run: copied out of a finished
                # run, it is refused like any other.
                build.write_text(f'cat .git/check.lock > "{side}/holder"\n', encoding='utf-8')
                run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", timeout=60)
                marker = (side / "holder").read_text(encoding='utf-8')
                # The holder's pid on POSIX; a random token on native Windows.
                if not (re.fullmatch("[0-9a-f]{32}", marker) if os.name == "nt" else marker.isdigit()):
                    raise RuntimeError(f"the lock file did not name its holder: {marker!r}")
                run(["sh", "scripts/check.sh"], project, expected=1, timeout=60,
                    reason="FAIL [env]: GATE_BUILD_CMD_OVERRIDE is set",
                    env=dict(os.environ, GATE_SELFTEST_NESTED=marker,
                             GATE_LOCK_HELD=own_lock, GATE_BUILD_CMD_OVERRIDE="true"))
                passed("a self-test marker copied out of a finished run is refused")
                if fcntl is None:
                    print("NOT RUN: the POSIX gate-lock cases (native Windows; tests/test_check_gate_windows"
                          " proves the gate lock there)")
                else:
                    posix_lock_cases(project, side, build, own_lock, gate)
                gate.write_text(original_gate, encoding='utf-8')
            # The scanners read untracked files too (git ls-files --others), not only the index.
            marker = project / "untracked-marker.md"
            marker.write_text("{{SELF_TEST" + "_TOKEN}}\n", encoding='utf-8')
            try:
                run(["sh", "scripts/check.sh"], project, expected=1, reason="CHECK: FAIL")
            finally:
                marker.unlink()
            passed("an untracked file with an unfilled marker turns the gate red")
            # A tracked file deleted without `git rm` fails the gate under its own name,
            # not as a scanner that failed to run.
            gone = project / "deleted-unstaged.md"
            gone.write_text("tracked, then deleted without git rm\n", encoding='utf-8')
            run(["git", "add", gone.name], project)
            gone.unlink()
            try:
                out = run(["sh", "scripts/check.sh"], project, expected=1,
                          reason="deleted-unstaged.md is tracked but missing")
                if "a scanner failed to run" in out:
                    raise RuntimeError("a deleted tracked file was reported as a scanner failure:\n" + out)
            finally:
                run(["git", "rm", "-q", "--cached", gone.name], project)
            # A directory symlink (a dependency directory linked into a fresh worktree) holds
            # nothing git tracks: the scan skips it with a line instead of failing on it.
            link = project / "node_modules"
            os.symlink("docs", link)
            try:
                run(["sh", "scripts/check.sh"], project, reason="NOTE [scan]: skipped node_modules")
            finally:
                link.unlink()
            # Git tracks a symlink's link text: a dangling link whose text holds an unfilled
            # marker was skipped whole and passed the setup gate. Assembled, never literal.
            # A link named like an option was read as one: "readlink --version" printed the
            # version and the marker in the link text passed.
            for name in ("config-link", "--version"):
                link = project / name
                os.symlink("{{" + "CONFIG_DIR}}/config.json", link)
                run(["git", "add", "--", name], project)
                try:
                    run(["sh", "scripts/check.sh"], project, expected=1,
                        reason="symlink " + name + " -> {{" + "CONFIG_DIR}}/config.json")
                finally:
                    run(["git", "rm", "-q", "--cached", "--", name], project)
                    link.unlink()
            # A link is reported under its own path, so setup/ stays exempt: aggregated under
            # a temporary file's name, an exempt setup/ link failed the gate beside a real one.
            (project / "setup").mkdir(exist_ok=True)
            links = ("setup/example-link", "config-link")
            for name in links:
                os.symlink("{{" + "CONFIG_DIR}}/config.json", project / name)
            run(["git", "add", "--", *links], project)
            try:
                out = run(["sh", "scripts/check.sh"], project, expected=1,
                          reason="config-link:1:symlink config-link -> {{" + "CONFIG_DIR}}")
                if "symlink setup/example-link ->" in out:
                    raise RuntimeError("an exempt setup/ symlink failed the setup gate:\n" + out)
            finally:
                run(["git", "rm", "-q", "--cached", "--", *links], project)
                for name in links:
                    (project / name).unlink()
            # Link text holding a newline was written as two lines, the second without the
            # link's path: a non-exempt link whose text went on to "setup/" and a marker had
            # that line removed by the setup/ exemption and passed, and an exempt setup/ link
            # with a marker on its second line failed. Every newline is now written as \n.
            marker = "{{" + "CONFIG_DIR}}"
            for name, target, expected, reason in (
                    ("multi-link", "missing\nsetup/" + marker, 1,
                     "multi-link:1:symlink multi-link -> missing\\nsetup/" + marker),
                    ("setup/multi-link", "missing\n" + marker, 0, None)):
                os.symlink(target, project / name)
                run(["git", "add", "--", name], project)
                try:
                    run(["sh", "scripts/check.sh"], project, expected=expected, reason=reason)
                finally:
                    run(["git", "rm", "-q", "--cached", "--", name], project)
                    (project / name).unlink()
            # In a UTF-8 locale grep took a line with a non-UTF-8 byte as binary and printed
            # nothing: a marker on a Latin-1 line, in a file or in a link's text, passed.
            utf8 = utf8_locale()
            latin = {"LC_ALL": utf8, "LANG": utf8}
            text = b"caf\xe9/{{" + b"CONFIG_DIR}}"
            for name, make in (("latin.md", lambda path: path.write_bytes(text + b"\n")),
                               ("latin-link", lambda path: os.symlink(text, bytes(path)))):
                if name == "latin-link" and os.name == "nt":
                    print("NOT RUN: a symlink whose text is not UTF-8 (native Windows stores link text as UTF-16)")
                    continue
                make(project / name)
                run(["git", "add", "--", name], project)
                try:
                    run(["sh", "scripts/check.sh"], project, expected=1,
                        reason=name + ":1:", env=dict(os.environ, **latin), errors="replace")
                finally:
                    run(["git", "rm", "-q", "--cached", "--", name], project)
                    (project / name).unlink()
            # The build/test command alone gets the caller's locale back, set or unset.
            gate = project / "scripts/check.sh"
            original_gate = gate.read_text(encoding='utf-8')
            gate.write_text(original_gate.replace('build_test_cmd="test -f scripts/claude_bridge.py"',
                                                  'build_test_cmd=\'[ "${LC_ALL-unset}" = "$EXPECT_LC" ]\''), encoding='utf-8')
            try:
                for value in (utf8, None):
                    env = {k: v for k, v in os.environ.items() if k != "LC_ALL"}
                    env["EXPECT_LC"] = value or "unset"
                    if value:
                        env["LC_ALL"] = value
                    run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", env=env)
            finally:
                gate.write_text(original_gate, encoding='utf-8')
            passed("a marker on a non-UTF-8 line or link fails the gate in a UTF-8 locale; the build keeps the caller's locale")
            # A failed append of link text (a full disk, a lost permission) was ignored: the
            # link's marker went unscanned and the gate could pass. Here a stand-in readlink
            # puts a directory where the second link's text is appended.
            with tempfile.TemporaryDirectory(prefix="myagentkit-side-") as side:
                shim = Path(side) / "bin"
                shim.mkdir()
                # The gate's folders are found through the mktemp that made them, never by where
                # TMPDIR points: macOS mktemp without a template ignores TMPDIR (it takes the user
                # temp folder), so a search of TMPDIR found nothing there. This mktemp does the same.
                made = shlex.quote(str(Path(side) / "made"))
                (Path(side) / "elsewhere").mkdir()
                (shim / "mktemp").write_text(
                    "#!/bin/sh\n"
                    "case \"$*\" in \"\"|-d) TMPDIR=" + shlex.quote(str(Path(side) / "elsewhere")) + "; export TMPDIR ;; esac\n"
                    "d=$(" + shlex.quote(shutil.which("mktemp")) + " \"$@\") && printf '%s\\n' \"$d\" >> " + made + " && printf '%s\\n' \"$d\"\n", encoding='utf-8')
                (shim / "mktemp").chmod(0o755)
                (shim / "readlink").write_text(
                    "#!/bin/sh\n"
                    "while IFS= read -r d; do\n"
                    "  if [ -f \"$d/symlink-text\" ]; then rm -f \"$d/symlink-text\" && mkdir \"$d/symlink-text\"; fi\n"
                    "done < " + made + "\n"
                    "exec " + shlex.quote(shutil.which("readlink")) + " \"$@\"\n", encoding='utf-8')
                (shim / "readlink").chmod(0o755)
                links = ("a-link", "b-link")
                for name in links:
                    os.symlink(marker + "/" + name, project / name)
                run(["git", "add", "--", *links], project)
                try:
                    run(["sh", "scripts/check.sh"], project, expected=1,
                        reason="could not sort the file list; refusing to scan blind",
                        env=dict(os.environ, PATH=str(shim) + os.pathsep + os.environ["PATH"]))
                finally:
                    run(["git", "rm", "-q", "--cached", "--", *links], project)
                    for name in links:
                        (project / name).unlink()
            passed("a deleted tracked file is named, a directory symlink is skipped with a note,"
                  " a symlink's link text is scanned under its own path")
            tests = project / "scripts/test_claude_bridge.py"
            original_tests = tests.read_bytes()
            tests.unlink()
            # Remove the missing file from the synthetic index too, so this case
            # reaches review-test absence instead of the earlier unreadable-file gate.
            run(["git", "add", "-u", "--", "scripts/test_claude_bridge.py"], project)
            run(["sh", "scripts/check.sh", "--self-test"], project, expected=1,
                reason="review self-test file is missing or empty")
            tests.write_bytes(original_tests)
            run(["git", "add", "scripts/test_claude_bridge.py"], project)
            wrapper = project / "scripts/review.sh"
            original_wrapper = wrapper.read_bytes()
            for stub in ["exit 1\n", "exit 0\n"]:
                wrapper.write_text(stub, encoding='utf-8')
                run(["sh", "scripts/check.sh", "--self-test"], project, expected=1,
                    reason="review adapter negative tests failed or did not run")
            wrapper.write_bytes(original_wrapper)
            # One emptied suite must fail on its own, not hide inside a combined test total.
            quota_tests = project / "scripts/test_codex_quota.py"
            original_quota = quota_tests.read_bytes()
            quota_tests.write_text("import unittest\nclass QuotaTests(unittest.TestCase):\n    pass\n", encoding='utf-8')
            run(["sh", "scripts/review.sh", "--self-test"], project, expected=2,
                reason="QuotaTests has 0 of at least %d tests" % BRIDGE_MINIMUMS["test_codex_quota"])
            quota_tests.write_bytes(original_quota)
            # Boundary checks whose self-test file runs no case are skipped, not passed. The
            # stubbed review run keeps this case to the boundary branch alone.
            wrapper.write_text("echo 'REVIEW SELF-TEST: PASS'\n", encoding='utf-8')
            checks = project / "scripts/boundary_checks.sh"
            selftests = project / "scripts/boundary_selftests.sh"
            original_checks, original_selftests = checks.read_bytes(), selftests.read_bytes()
            checks.write_text(": synthetic boundary check\n", encoding='utf-8')
            run(["sh", "scripts/check.sh", "--self-test"], project, expected=1, reason="ran no case")
            # The shipped existing-file example, run by the enclosing self-test against a check
            # it can trip: it counts as a case only by printing its ok line.
            src = project / "src"
            if src.exists():
                raise RuntimeError("the synthetic project already has src/")
            (src / "domain").mkdir(parents=True)
            (src / "domain/existing.py").write_text("original\n", encoding='utf-8')
            # Tracked, so the case can show the example leaves the checkout's status unchanged.
            run(["git", "add", "src"], project)
            checks.write_text("! grep -q myapp.web src/domain/existing.py ||\n"
                              "  { echo 'FAIL [boundary]: the domain layer imports the web layer:'; fail=1; }\n",
                              newline="\n", encoding='utf-8')
            example = (ROOT / "core/scripts/boundary_selftests.sh").read_text(encoding="utf-8").splitlines()
            # LF and UTF-8 on every host: Windows Python writes CRLF by default, which sh misreads.
            selftests.write_text("\n".join(line[4:] for line in example if line.startswith("# | ")) + "\n",
                                 encoding="utf-8", newline="\n")
            # Without the rule line (an owner who allows AI credit, or a sync that has not added
            # it yet) the hook's case says it is off and why, never that an owner chose it.
            agents = project / "AGENTS.md"
            original_agents = agents.read_bytes()
            agents.write_bytes(original_agents.replace(b"No AI attribution in git", b"AI credit allowed"))
            status = run(["git", "status", "--porcelain"], project)
            out = run(["sh", "scripts/check.sh", "--self-test"], project, reason="SELF-TEST: PASS")
            if "commit-msg hook: off, AGENTS.md has no 'No AI attribution in git' rule line" not in out:
                raise RuntimeError("the commit-msg case did not say the rule line is missing:\n" + out)
            if "  ok   — domain/web boundary gate rejects a forbidden import in an existing file" not in out:
                raise RuntimeError("the existing-file boundary example did not run as a case:\n" + out)
            if (src / "domain/existing.py").read_text(encoding='utf-8') != "original\n":
                raise RuntimeError("the existing-file boundary example changed its target in the checkout")
            if run(["git", "status", "--porcelain"], project) != status:
                raise RuntimeError("the existing-file boundary example changed the checkout's git status")
            run(["git", "rm", "-r", "-q", "--cached", "src"], project)
            shutil.rmtree(src)
            agents.write_bytes(original_agents)
            checks.write_bytes(original_checks)
            selftests.write_bytes(original_selftests)
            wrapper.write_bytes(original_wrapper)
            passed("missing review tests, failed runner, absent completion evidence, an emptied "
                  "suite and boundary checks whose self-tests ran no case reject; the existing-file example "
                  "runs as a case; a missing attribution rule line is a visible skip")


def posix_lock_cases(project, side, build, own_lock, gate):
    """The gate lock's POSIX cases (flock): a killed holder, waiters, a symlink at the lock path,
    a bounded wait, an inherited descriptor, NFS and lockless file systems, a toolchain python3."""
    # A gate killed with SIGKILL never clears its pid from the lock file. Once its
    # build has exited too, nobody holds the lock, and variables copied out of the
    # killed run name it exactly: refused, never honoured as a self-test's seams.
    build.write_text(f'cat .git/check.lock > "{side}/holder"\n'
                     f'echo "$GATE_LOCK_FD" > "{side}/fd.tmp"\nmv "{side}/fd.tmp" "{side}/fd"\n'
                     'sleep 1\n', encoding='utf-8')
    killed = subprocess.Popen(["sh", "scripts/check.sh"], cwd=project,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + limit(60)
    while not (side / "fd").exists():
        if killed.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("the gate to be killed never started its build")
        time.sleep(0.1)
    killed.kill()
    killed.wait()
    with open(project / ".git/check.lock") as probe:
        while True:
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise RuntimeError("the killed gate's build never released the lock")
                time.sleep(0.1)
    marker = (side / "holder").read_text(encoding='utf-8')
    if (project / ".git/check.lock").read_text(encoding='utf-8') != marker:
        raise RuntimeError("the killed gate's pid was not left in the lock file")
    build.write_text("false\n", encoding='utf-8')
    run(["sh", "scripts/check.sh"], project, expected=1, timeout=60,
        reason="FAIL [env]: GATE_BUILD_CMD_OVERRIDE is set",
        env=dict(os.environ, GATE_SELFTEST_NESTED=marker, GATE_LOCK_HELD=own_lock,
                 GATE_LOCK_FD=(side / "fd").read_text(encoding='utf-8').strip(),
                 GATE_BUILD_CMD_OVERRIDE="true"))
    passed("variables copied out of a gate killed with SIGKILL are refused")
    # Two gate runs sharing one build directory: the second must wait, not race.
    build.write_text(f'mkdir "{side}/build" && sleep 2 && rmdir "{side}/build"\n', encoding='utf-8')
    pair = [subprocess.Popen(["sh", "scripts/check.sh"], cwd=project,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True) for _ in range(2)]
    outputs = [p.communicate(timeout=limit(60))[0] for p in pair]
    if (any(p.returncode or "CHECK: PASS" not in o for p, o in zip(pair, outputs))
            or not any("NOTE [lock]" in o for o in outputs)):
        raise RuntimeError("concurrent gate runs raced:\n" + "\n".join(outputs))
    passed("two concurrent gate runs sharing a build directory both pass")
    # A gate killed with SIGKILL while its build runs: the build keeps the lock, and
    # none of three waiters builds until it exits. The build directory is the proof:
    # a waiter whose build overlapped the orphaned one fails on "File exists".
    build.write_text(f'mkdir "{side}/build" || exit 1\nsleep "${{HOLD:-1}}"\n'
                     f'rmdir "{side}/build"\n', encoding='utf-8')
    killed = subprocess.Popen(["sh", "scripts/check.sh"], cwd=project,
                              env=dict(os.environ, HOLD="6"),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + limit(60)
    while not (side / "build").is_dir():
        if killed.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError("the gate to be killed never started its build")
        time.sleep(0.1)
    killed.kill()
    killed.wait()
    waiters = [subprocess.Popen(["sh", "scripts/check.sh"], cwd=project,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True) for _ in range(3)]
    outputs = [p.communicate(timeout=limit(120))[0] for p in waiters]
    if any(p.returncode or "CHECK: PASS" not in o for p, o in zip(waiters, outputs)):
        raise RuntimeError("a waiter built beside the build of a killed gate, or beside"
                           " another waiter:\n" + "\n".join(outputs))
    passed("a gate killed with SIGKILL holds the lock until its build exits;"
          " three waiters then run one at a time")
    # A file at the lock path that is not a lock (the symlink an older check.sh left
    # behind when killed) is refused by name, never followed or replaced.
    lock = project / ".git/check.lock"
    lock.unlink(missing_ok=True)
    os.symlink("12345", lock)
    try:
        run(["sh", "scripts/check.sh"], project, expected=1, timeout=30,
            reason="FAIL [lock]: cannot open")
    finally:
        lock.unlink(missing_ok=True)
    # A live holder: a bounded wait gives up with its own code, and only a run
    # given this checkout's own lock path skips the lock.
    build.write_text("true\n", encoding='utf-8')
    with open(lock, "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        run(["sh", "scripts/check.sh"], project, expected=75, reason="NOT RUN [lock]",
            env=dict(os.environ, GATE_LOCK_WAIT="2"), timeout=30)
        run(["sh", "scripts/check.sh"], project, expected=75, reason="NOT RUN [lock]",
            env=dict(os.environ, GATE_LOCK_WAIT="2",
                     GATE_LOCK_HELD=str(side / "other-checkout.lock")), timeout=30)
        # The own lock path is inherited only with the descriptor that holds it.
        run(["sh", "scripts/check.sh"], project, expected=1, timeout=30,
            reason="FAIL [env]: GATE_LOCK_HELD",
            env=dict(os.environ, GATE_LOCK_WAIT="2", GATE_LOCK_HELD=own_lock))
        out = run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", timeout=30,
                  pass_fds=(held.fileno(),),
                  env=dict(os.environ, GATE_LOCK_WAIT="2", GATE_LOCK_HELD=own_lock,
                           GATE_LOCK_FD=str(held.fileno())))
        if "NOTE [lock]" in out:
            raise RuntimeError("a run given its own lock path waited:\n" + out)
        # A descriptor opened independently on the same file, with the holder's pid
        # copied, is not the lock: the holder's description holds it, this one does not.
        held.truncate(0)
        held.write(str(os.getpid()))
        held.flush()
        with open(lock) as other:
            run(["sh", "scripts/check.sh"], project, expected=1, timeout=30,
                reason="FAIL [env]: GATE_LOCK_HELD", pass_fds=(other.fileno(),),
                env=dict(os.environ, GATE_LOCK_WAIT="2", GATE_LOCK_HELD=own_lock,
                         GATE_LOCK_FD=str(other.fileno()),
                         GATE_SELFTEST_NESTED=str(os.getpid()),
                         GATE_BUILD_CMD_OVERRIDE="true"))
    passed("a symlink at the lock path is refused; a bounded lock wait stops with"
          " NOT RUN; only the own lock path, with the descriptor holding it, is inherited, never"
          " an independently opened one")
    # Linux's NFS client takes an exclusive flock only on a descriptor open for
    # writing: the inheritance probe opened its own read-only, and every fresh run
    # failed FAIL [env]. A stand-in flock refuses such a flock as NFS does, then
    # every flock (the probe's, then the first one) as a lockless file system does.
    # The lock programs run isolated (python3 -I), so a sitecustomize no longer
    # reaches them: a python3 on PATH puts the stand-in at the top of each -c program.
    fake = side / "fake-flock"
    fake.mkdir()
    prelude = (
        "def _fake_flock():\n"
        "    import errno, fcntl, os\n"
        "    real, mode = fcntl.flock, os.environ.get('FAKE_FLOCK')\n"
        "    def flock(fd, op):\n"
        "        fd = fd if isinstance(fd, int) else fd.fileno()\n"
        "        if mode == 'nfs' and op & fcntl.LOCK_EX and (\n"
        "                fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY):\n"
        "            raise OSError(errno.EBADF, os.strerror(errno.EBADF))\n"
        "        if mode == 'none' or (mode == 'none-held' and 'GATE_LOCK_HELD' in os.environ):\n"
        "            raise OSError(errno.ENOLCK, os.strerror(errno.ENOLCK))\n"
        "        return real(fd, op)\n"
        "    fcntl.flock = flock\n"
        "_fake_flock()\n")
    (fake / "python3").write_text(
        "#!%s\nimport os, sys\nargs = sys.argv[1:]\n"
        "if '-c' in args:\n"
        "    args[args.index('-c') + 1] = %r + args[args.index('-c') + 1]\n"
        "os.execv(%r, [%r] + args)\n" % (sys.executable, prelude, sys.executable, sys.executable), encoding='utf-8')
    (fake / "python3").chmod(0o755)
    fake_path = str(fake) + os.pathsep + os.environ["PATH"]
    run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", timeout=60,
        env=dict(os.environ, PATH=fake_path, FAKE_FLOCK="nfs"))
    for mode in ("none-held", "none"):
        out = run(["sh", "scripts/check.sh"], project, expected=1, timeout=30,
                  reason="FAIL [lock]: this file system does not support the gate lock (",
                  env=dict(os.environ, PATH=fake_path, FAKE_FLOCK=mode))
        if "FAIL [env]" in out:
            raise RuntimeError("a lockless file system was reported as an environment fault:\n" + out)
    passed("a lock that needs a writable descriptor (NFS) is taken; a file system"
          " without locks fails FAIL [lock] by name")
    # python3 only in the configured toolchain directory, as a hook sees a Python
    # installed per user: the lock, which is taken through python3, still finds it.
    tc = side / "tc"
    tc.mkdir()
    (tc / "python3").symlink_to(sys.executable)
    no_python = path_without(os.environ["PATH"], lambda name: name.startswith("python"),
                             side / "no-python")
    if shutil.which("python3", path=no_python):
        raise RuntimeError("the PATH without python3 still finds one")
    if 'toolchain_path=""' not in gate.read_text(encoding='utf-8'):
        raise RuntimeError("the synthetic project's toolchain_path line was not found")
    gate.write_text(gate.read_text(encoding='utf-8').replace('toolchain_path=""', f'toolchain_path="{tc}"'), encoding='utf-8')
    run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", timeout=60,
        env=dict(os.environ, PATH=no_python))
    passed("a python3 found only through toolchain_path takes the gate lock")


FAILURES = (OSError, ValueError, RuntimeError, KeyError, subprocess.TimeoutExpired)


def unit(name, self_test, timing_file=None):
    """Run one unit in this process; 0 on a pass, 1 with the error printed on a failure."""
    try:
        if name == "acceptance":
            acceptance(self_test)
        elif name == "locale":
            locale_matrix()
        else:
            run_tests(ROOT, name, REQUIRED_SUITES[name])
        # The completion line run_units requires: a unit that exited 0 before this point (a
        # test module calling os._exit(0) while it was discovered) did not finish its checks.
        # An exit code alone is no evidence of a finished run (pytest's exit code 5; Claude Code
        # best practices, "Give Claude a way to verify its work").
        print("UNIT DONE: " + name, flush=True)
        return 0
    except FAILURES as error:
        print(f"KIT CHECK: FAIL — {error}", file=sys.stderr)
        return 1
    finally:
        if timing_file:
            rows = ["%7.1f s    %s" % (seconds, label) for label, seconds in TIMES]
            rows += ["%7.1f s    test %s" % item for item in sorted(SLOWEST, reverse=True)[:10]]
            Path(timing_file).write_text("".join(row + "\n" for row in rows), encoding='utf-8')


def run_units(units, timing=False, parallel=None, said=()):
    """Run the (name, command) units, `parallel` at once (default all); print each unit's whole
    output in the given order. Each unit's timeouts scale by `parallel` (see limit()). `said`:
    the NOT RUN lines the checks before the units printed, repeated under the summary first.

    The units share no state: every suite and the acceptance phases work in temporary
    directories of their own, and each synthetic project has its own .git and so its own
    gate lock. A unit's output is printed only when it and every unit before it have ended,
    so the order does not depend on which finishes first. True when every unit passed.
    """
    children, cancelled, lock = [], False, Lock()

    @contextmanager
    def stop_units():
        nonlocal cancelled
        try:
            yield
        finally:
            # The wrapper signals the whole group. Stop queued units too, and a child that
            # started just after that signal, before the executor waits for its workers.
            with lock:
                cancelled = True
                for child in children:
                    if child.poll() is None:
                        try:
                            child.terminate()
                        except ProcessLookupError:
                            pass
            pool.shutdown(wait=True, cancel_futures=True)

    def one(name, command, timing_file):
        started = time.monotonic()
        if timing_file:
            command = command + ["--timing-file", timing_file]
        with lock:
            if cancelled:
                return 1, '', time.monotonic() - started
            child = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, env=env,
                                     stderr=subprocess.STDOUT, text=True, errors="replace")
            children.append(child)
        with child:
            output = child.communicate()[0]
        return child.returncode, output, time.monotonic() - started

    parallel = parallel or len(units)
    env = dict(os.environ, **{SCALE: str(float(os.environ.get(SCALE, "1")) * parallel)})
    with tempfile.TemporaryDirectory(prefix="myagentkit-timing-") as times, \
            ThreadPoolExecutor(max_workers=parallel) as pool, stop_units():
        files = [os.path.join(times, str(number)) if timing else None for number in range(len(units))]
        futures = [pool.submit(one, name, command, timing_file)
                   for (name, command), timing_file in zip(units, files)]
        summary, failed, not_run = [], [], list(said)
        for (name, _), future, timing_file in zip(units, futures, files):
            code, output, seconds = future.result()
            if not code and "UNIT DONE: " + name not in output.splitlines():
                code, output = 1, output + ("KIT CHECK: FAIL — unit %s exited 0 without its completion line "
                                            "(UNIT DONE: %s): it ended before its checks finished\n" % (name, name))
            sys.stdout.write(output)
            sys.stdout.flush()
            # A test that cannot run on this host says so in one "NOT RUN:" line and passes;
            # repeated under the summary, the end of the output names what this host did not run.
            not_run += [line for line in output.splitlines() if line.startswith("NOT RUN:")]
            if code:
                failed.append(name)
            summary.append("%7.1f s  %s%s" % (seconds, name, " (FAILED)" if code else ""))
            if timing_file and os.path.exists(timing_file):
                summary += Path(timing_file).read_text(encoding='utf-8').splitlines()
    if timing:
        print("TIMING (each unit's wall clock; under it, its phases and ten slowest tests):")
        print("\n".join(summary))
    else:
        print("\n".join("TIME: " + row.strip() for row in summary))
    if not_run:
        print("\n".join(not_run))
    if failed:
        print("KIT CHECK: FAIL — %d of %d units failed: %s" % (len(failed), len(units), ", ".join(failed)),
              file=sys.stderr)
    return not failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--timing", action="store_true",
                        help="print each unit's, phase's and slowest test's seconds at the end")
    parser.add_argument("--unit", help=argparse.SUPPRESS)
    parser.add_argument("--timing-file", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.unit:
        return unit(args.unit, args.self_test, args.timing_file)
    started = time.monotonic()
    units = [*REQUIRED_SUITES, "acceptance", "locale"]
    cpus = os.cpu_count() or 1
    parallel = degree(cpus, len(units))
    print("KIT CHECK: %d of %d units at once (%d CPUs)" % (parallel, len(units), cpus))
    # Their NOT RUN lines (shellcheck, the killing-test note) are repeated under the summary too.
    early = io.StringIO()
    try:
        with redirect_stdout(early):
            check_syntax(ROOT)
            check_release(ROOT)
            untested_guards(ROOT)
            validate_plugin(ROOT)
    finally:
        sys.stdout.write(early.getvalue())
    said = [line for line in early.getvalue().splitlines() if line.startswith("NOT RUN:")]
    manifest = json.loads((ROOT / "plugins/myagentkit/.codex-plugin/plugin.json").read_text(encoding='utf-8'))
    # The name and skills path Codex's plugin scaffold writes; Codex documents no validator
    # (developers.openai.com/codex/plugins/build/, read 2026-10-15).
    if manifest["name"] != "myagentkit" or manifest["skills"] != "./skills/":
        raise RuntimeError("Codex plugin manifest does not expose the expected package")
    print(run([sys.executable, "scripts/package_codex_plugin.py", "--check"]).strip())
    # -u: a unit's error, on stderr, lands after what it printed before failing.
    command = [sys.executable, "-B", "-u", str(Path(__file__).resolve())] + ["--self-test"] * args.self_test
    if not run_units([(name, command + ["--unit", name]) for name in units], args.timing, parallel, said=said):
        return 1
    print("TIME: %.1f s in all" % (time.monotonic() - started))
    if _PASSED_FILE:
        marker = Path(_PASSED_FILE)
        # A long native self-test outlived its empty temporary marker directory. Recover
        # that one directory, and write its completion evidence before printing PASS:
        # an unwritable marker or a file in the directory's place still fails the check.
        marker.parent.mkdir(exist_ok=True)
        marker.touch()
    print("KIT CHECK: PASS", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FAILURES as error:
        print(f"KIT CHECK: FAIL — {error}", file=sys.stderr)
        raise SystemExit(1)
