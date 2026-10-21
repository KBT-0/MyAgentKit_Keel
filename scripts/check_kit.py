#!/usr/bin/env python3
"""Offline kit acceptance: syntax, packaged source, regression tests, and bootstrap gates."""
import signal
import sys

# SIGTERM and SIGHUP (a closed terminal) must unwind the runner and run atexit, including its
# private cache cleanup, and stop the units: each leads its own session, so no signal to this
# group reaches them.
if __name__ == '__main__':
    if sys.version_info < (3, 11):
        raise SystemExit('KIT CHECK: FAIL - Python 3.11 or newer is required')

    def terminate(sig, frame):
        # A unit's group got the signal too. unittest records a SystemExit as a test error and
        # runs the next test, which starts new shells and git: a unit exits at once.
        if '--unit' in sys.argv:
            import os
            os._exit(128 + sig)
        raise SystemExit(128 + sig)
    signal.signal(signal.SIGTERM, terminate)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, terminate)

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
from contextlib import contextmanager
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
# test. GIT_CONFIG* is set below, not dropped.
for _name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_IMPLICIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY',
              'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_COMMON_DIR', 'GIT_GRAFT_FILE', 'GIT_NO_REPLACE_OBJECTS',
              'GIT_REPLACE_REF_BASE', 'GIT_PREFIX', 'GIT_SHALLOW_FILE', 'GIT_INTERNAL_SUPER_PREFIX',
              'GIT_NAMESPACE', 'GIT_CEILING_DIRECTORIES', 'MYAGENTKIT_BACKEND'):
    os.environ.pop(_name, None)
# Every git a unit or test runs ignores the developer's own global and system configuration (a
# core.hooksPath, commit.gpgsign, init.templateDir or core.autocrlf there hung or changed the
# fixtures, which CI never showed; issue #147). A test that needs a setting passes it itself.
os.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
# Windows names a long user's temp folder in its 8.3 form (C:\Users\RUNNER~1\...), but the kit's
# code resolves a path to the long form: a test that compares the two failed on such a host.
if os.name == 'nt':
    for _name in ('TEMP', 'TMP'):
        if _name in os.environ:
            os.environ[_name] = os.path.realpath(os.environ[_name])
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


def symlinks_work():
    """Windows makes a symlink only in Developer Mode or for an administrator. The same probe as
    tests/test_gate_checks.py, whose link test is a declared skip where this is False."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.symlink(tmp, os.path.join(tmp, 'link'))
        except (OSError, NotImplementedError):
            return False
    return True


def case_folds():
    """A folder spelled in another letter case is the same folder (Windows, macOS by default).
    The same probe as tests/test_sync_kit.py and tests/test_bootstrap.py, whose case tests are
    declared skips where not."""
    return Path(tempfile.gettempdir().swapcase()).is_dir()


REQUIRED_SUITES = {
    'core/scripts': dict(BRIDGE_MINIMUMS, test_agent_cost=8, test_context_buckets=8, test_owns_check=9),
    # Each suite's current count: a minimum far below it (1 of 30) let a suite lose almost
    # every test with the kit check green. A new test raises its suite's number here.
    'tests': {'test_packaging': 3, 'test_bootstrap': 42 if case_folds() else 41, 'test_acceptance': 20,
              'test_review_upgrade': 5 if os.name == 'nt' else 6,
              'test_scan_gate': 1, 'test_gate_checks': 15 if symlinks_work() else 14, 'test_unity_gate': 13, 'test_kit_wrapper': 6,
              'test_check_gate': 20, 'test_check_gate_windows': 37 if os.name == 'nt' else 13,
              'test_check_gate_windows_harness': 3 if os.name == 'nt' else 0,
              'test_sync_kit': 60 if case_folds() else 59, 'test_doctor': 13, 'test_git_hooks': 37, 'test_stop_hook': 12, 'test_context_hook': 14, 'test_communication_hooks': 37, 'test_suggestions': 13, 'test_suggestion_mod': 1, 'test_overlay_permissions': 12, 'test_guard_destructive_git': 67 if os.name == 'nt' else 66, 'test_guard_boundaries': 3, 'test_guard_private_email': 11, 'test_guard_root_scan': 3, 'test_guard_secret_files': 3,
              'test_spawn_worker': 78 if os.name == 'nt' else 98, 'test_spawn_codex': 53 if os.name == 'nt' else 60 if shutil.which('dash') else 59,
              # The same conditions as the suites' declared skips (dash, /proc, /dev/full), not the platform.
              'test_codex_worker': 66 if os.name == 'nt' else 68 if Path('/proc/self/fd').is_dir() else 67, 'test_working_mode': 52,
              'test_worker_visibility': 96 if os.name == 'nt' or os.path.exists('/dev/full') else 95, 'test_doc_pointers': 28,
              'test_usage_summary': 33, 'test_done_audits': 2,
              'test_kit_output': 3, 'test_kit_runner': 48, 'test_clean_worktrees': 144, 'test_clean_worktrees_windows': 21 if os.name == 'nt' else 0, 'test_close_worker_windows': 22,
              'test_review_windows': 22 if os.name == 'nt' else 0, 'test_claude_sandbox': 28, 'test_worker_paths_windows': 10 if os.name == 'nt' else 7,
              'test_close_worker': 52 if os.name == 'nt' else 51, 'test_python_fallback': 3,
              'test_install': 12 if os.name == 'nt' else 8},
}
# Suites that do not run on native Windows, each with the reason. There each one prints one
# NOT RUN line and is not imported; CI's Linux and macOS jobs run every one of them. A suite
# ported to Windows leaves this list in the same change (issue #56).
NOT_ON_WINDOWS = {
    'core/scripts': {},
    'tests': {'test_check_gate': 'the flock gate lock; tests/test_check_gate_windows proves the Windows lock',
              'test_clean_worktrees': 'POSIX process liveness; tests/test_clean_worktrees_windows proves Windows'},
} if os.name == 'nt' else {}
# Modules too long for one unit, each run as that many units (#146). A module name is unique
# across the folders. ponytail: hand-set from measured seconds; a slow module added later only
# lengthens the run until it is listed here.
SHARDS = {'test_claude_bridge': 8, 'test_bootstrap': 4, 'test_gate_checks': 3, 'test_check_gate_windows': 3,
          'test_git_hooks': 3}
# Two tiers (docs/research/kit-self-checks.md, findings 6 and 7: a commit stage of about ten
# minutes, the long suites in a second stage). The fast tier is the default run, for every
# change and before a push; `--slow` runs the slow tier alone, `--all` both (CI runs the two as
# parallel jobs; a release runs both). Each unit is in exactly one tier: these slow units
# (a module name, every shard of it, "acceptance", or one unit by its full name), every other
# unit fast. Measured in .myagentkit/v012/reports/tiers.md and reports/ckfix.md: close_worker
# (40 tests, about 12 s each) and the unsharded locale/test_git_hooks passed the 480 s cap.
# Unsharded modules that start right after the shards (their locale suites too): queued last, a
# 240-280 s unit alone set the fast tier's tail (measured in the tiers report).
LONG = ('test_sync_kit', 'test_guard_destructive_git', 'test_claude_sandbox',
        'test_close_worker_windows', 'test_worker_paths_windows', 'test_review_upgrade')
SLOW = {'acceptance', 'test_bootstrap', 'test_claude_bridge', 'test_spawn_worker', 'test_spawn_codex',
        'test_worker_visibility', 'test_doctor', 'test_close_worker', 'locale/test_git_hooks',
        'test_install'}
# Each tier's time budget (finding 8, Bazel's test-size timeouts): (per-unit cap, whole-tier
# cap) in seconds, times SCALE on a slow host. A unit over its cap is stopped and fails; a tier
# over its cap fails; each is named with its seconds. The measured times and headroom are in
# the tiers report.
CAPS = {'fast': (480, 600), 'slow': (3000, 3600)}


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
            # Python 3.11 has no Path.is_junction, and only Windows' stat names the tags: a
            # POSIX 3.11 run that read them directly failed before any suite ran (#96).
            linked = (junction() if junction else
                      getattr(path.lstat(), 'st_reparse_tag', 0) in
                      # The stat constants exist only on Windows; elsewhere the winnt.h numbers.
                      (getattr(stat, 'IO_REPARSE_TAG_MOUNT_POINT', 0xA0000003),
                       getattr(stat, 'IO_REPARSE_TAG_SYMLINK', 0xA000000C)))
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
    counts = {}
    for test in _cases(suite):
        module = test.id().split('.')[0]
        counts[module] = counts.get(module, 0) + 1
    return suite, counts


def _cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _cases(item)
        else:
            yield item


def run_tests(root, directory, required, shard=None):
    """Require executed suite minimums; only declared platform exclusions may skip.

    A skipped test never counts toward a minimum: a run that skipped or collected nothing is
    no pass (pytest exits 5 when it collects nothing, docs.pytest.org/en/stable/reference/
    exit-codes.html; unittest keeps skips apart from success, TestResult.skipped). A declared
    platform skip says so in its NOT RUN line (issue #56), and never counts, whether or not it
    skips here. `shard`, (index, total): the module's count is checked whole, and its tests
    index, index + total, ... run, so one long module spreads over `total` units (#146)."""
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
    # Only the required modules are imported: a unit names one module (main refuses a module
    # without a count), so one folder's modules run in units at once, none running another's.
    suite, found = discover(folder, {path.stem for path in folder.glob('test_*.py')} - set(required))
    allowed = {test.id() for test in _cases(suite)
               if getattr(getattr(test, test._testMethodName), '_kit_platform_skip', False)}
    counts = {name: found.get(name, 0) - sum(test.split('.')[0] == name for test in allowed) for name in required}
    for name, minimum in required.items():
        if counts[name] < minimum:
            raise RuntimeError('required test suite is incomplete: %s (%d tests that can run here, %d required)'
                               % (name, counts[name], minimum))
    if shard:
        suite = unittest.TestSuite(list(_cases(suite))[shard[0]::shard[1]])
    output = io.StringIO()
    # Verbosity 1: a failure shows its FAIL and ERROR blocks and the count, not a line for each
    # passing test (a red CI job once carried about 45k tokens of those lines, #111).
    result = unittest.TextTestRunner(stream=output, verbosity=1, resultclass=TimedResult).run(suite)
    unexpected = [test.id() for test, _ in result.skipped if test.id() not in allowed]
    for test, reason in result.skipped:
        if test.id() in allowed:
            print('NOT RUN: %s (%s)' % (test.id(), reason))
    if not result.wasSuccessful() or unexpected:
        raise RuntimeError('required tests failed or were skipped:\n' + output.getvalue()
                           + ''.join('skipped without a platform declaration: %s\n' % name
                                     for name in unexpected))
    # A pass prints one line, a failure only what failed: the per-test lines were kilobytes nobody read.
    # The skip count rides on this line: a passing test prints NOT RUN lines of its own too.
    passed('%s ran %d tests%s, each suite at or above its minimum (%s)'
           % (directory, result.testsRun - len(result.skipped),
              ' (%d declared platform skips)' % len(result.skipped) if result.skipped else '',
              ', '.join('%s %d' % item for item in sorted(required.items()))))


SCALE = "MYAGENTKIT_TEST_TIMEOUT_SCALE"


def limit(seconds):
    """A wall-clock bound on a child, times SCALE: a slow host sets it, and run_units multiplies
    it by the units running at once, at most 4 (three units on one CPU each take about three
    times as long)."""
    return seconds * float(os.environ.get(SCALE, "1"))


def degree(cpus, units):
    """How many units run at once. On a 3-CPU runner three at once took 300 s each and timed out;
    one after another is what passed there. GitHub's standard runners: macOS 3 vCPU, Linux and
    Windows 2 (private repositories) or 4 (public) (docs.github.com/en/actions/reference/runners/
    github-hosted-runners, read 2026-10-15). From 4 CPUs, one unit per two CPUs: a unit's tests
    start shells and git, more processes than the one CPU each (the 4 and the half are the kit's
    own choice; measured in #146)."""
    return 1 if cpus < 4 else min(units, max(2, cpus // 2))


# A gate run that waits forever (a lock never released) must fail here, not hang the kit check.
# Output is read as UTF-8 unless a caller says otherwise: a test file run without UTF-8 mode
# (not under the kit check) read "—" in the ANSI code page and failed a passing check (#275).
def run(args, cwd=ROOT, expected=0, reason=None, env=None, timeout=300, **popen):
    popen = dict({'encoding': 'utf-8', 'errors': 'replace'}, **popen)
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
    readme = re.search(r'^\*\*(v\d+\.\d+(?:\.\d+)?)\.\*\*', (root / 'README.md').read_text(encoding='utf-8'), re.M)
    changelog = re.search(r'^## (v\d+\.\d+(?:\.\d+)?)(?=\s|$)', (root / 'CHANGELOG.md').read_text(encoding='utf-8'), re.M)
    if not readme or not changelog or readme.group(1) != changelog.group(1):
        raise RuntimeError("README's bold version must match CHANGELOG's newest versioned heading")
    manifest = root / 'plugin/.claude-plugin/plugin.json'
    version = str(json.loads(manifest.read_text(encoding='utf-8')).get('version', ''))
    # A patch release's heading names all three numbers, and the manifest the same three.
    if (not re.fullmatch(r'\d+\.\d+\.\d+', version)
            or changelog.group(1) not in ('v' + version, 'v' + version.rsplit('.', 1)[0])):
        raise RuntimeError("plugin/.claude-plugin/plugin.json's version %r must be MAJOR.MINOR.PATCH with "
                           "CHANGELOG's newest version %s as MAJOR.MINOR, or as all three for a patch release"
                           % (version, changelog.group(1)))


def check_actions(root):
    """Every project-owned kit file changed since the last release tag is named in an ACTION
    item of CHANGELOG's newest version (#134). sync-kit.sh never copies a file under core/,
    setup/ or overlays/ without its KIT-OWNED header, so a fix there reaches a project only
    through an ACTION item. Changes since the tag include uncommitted ones; a removed file
    counts as project-owned. Without a v* tag (a shallow CI checkout has none) it is NOT RUN."""
    git = ['git', '-C', str(root), '-c', 'core.quotePath=false']
    found = subprocess.run(git + ['describe', '--tags', '--abbrev=0', '--match', 'v[0-9]*.[0-9]*'],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
    if found.returncode:
        print('NOT RUN: the ACTION check for project-owned kit files (no v* release tag)')
        return
    tag = found.stdout.strip()
    # stdout alone: run() adds stderr, where git writes its line-ending warnings. A failed diff
    # is a FAIL line, not a traceback.
    diff = subprocess.run(git + ['diff', '--name-only', '--no-renames', tag, '--', 'core', 'setup', 'overlays'],
                          capture_output=True, text=True, encoding='utf-8', errors='replace')
    if diff.returncode:
        raise RuntimeError('git diff against %s failed: %s' % (tag, diff.stderr.strip()))
    names = diff.stdout.splitlines()
    owned = [name for name in names if not (root / name).is_file() or not re.search(
        r'^(# |<!-- )KIT-OWNED:', (root / name).read_text(encoding='utf-8', errors='replace'), re.M)]
    if not owned:
        return
    # After a release tag the next cycle's items sit under "## Unreleased" until its release.
    newest = re.search(r'^## (Unreleased\b[^\n]*|v\d+\.\d+(?:\.\d+)?)(?=\s|$)(.*?)(?=^## v|\Z)',
                       (root / 'CHANGELOG.md').read_text(encoding='utf-8'), re.M | re.S)
    if not newest or re.match(r'v\d+\.\d+(?:\.\d+)?', tag).group() == newest.group(1):
        raise RuntimeError('project-owned kit files changed since %s, and CHANGELOG has no newer version '
                           'for their ACTION items: %s' % (tag, ', '.join(owned)))
    # An item runs from its **ACTION to the end of its bullet.
    actions = ' '.join(item[item.index('**ACTION'):] for item in re.split(r'\n(?=- |\n)', newest.group(2))
                       if '**ACTION' in item)
    # ponytail: a file's base name anywhere in that text counts; match whole paths if a
    # shared name (README.md, AGENTS.md) ever lets a change through.
    missing = [name for name in owned if name.rsplit('/', 1)[-1] not in actions]
    if missing:
        raise RuntimeError('project-owned kit files changed since %s with no ACTION item naming them under '
                           'CHANGELOG %s: %s' % (tag, newest.group(1), ', '.join(missing)))
    passed('every project-owned kit file changed since %s is named in an ACTION item' % tag)


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
        if path.suffix.lower() == '.py':
            try:
                ast.parse(path.read_text(encoding='utf-8'), filename=str(path), feature_version=(3, 11))
            except SyntaxError as error:
                raise RuntimeError("%s is not Python 3.11 syntax: %s" % (path, error)) from error
    bash_5_2()  # the lint's prerequisite, on every host, whether or not a file needs it
    for path in paths:
        if path.suffix.lower() == '.sh':
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
# A comment line, except the `# > ` example fixture test boundary_checks.sh ships and a test runs.
COMMENT = re.compile(r'^[ \t]*#(?! >( |$)).*$', re.M)


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
        if path.suffix.lower() == '.sh':
            found.append(path)
        elif path.is_file() and not path.is_symlink():
            with path.open('rb') as handle:
                if re.match(rb'#!.*[/ ]sh(?:\s|$)', handle.readline(200)):
                    found.append(path)
    return found


def shell_portability(root):
    """The kit's shell lint and `shellcheck -s sh` over the repo's non-ignored sh scripts.

    shellcheck fails on SC3xxx (undefined in POSIX sh, a bashism), on errors, and on SC2028 and
    SC2086, which a project's gate refuses in every shell file, the kit's installed ones too
    (core/scripts/check.sh); its other warnings and notes stay a reviewer's. It reads no rc file and no SHELLCHECK_OPTS, so a
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
               if ': error:' in line or re.search(r'\[SC(3\d{3}|2028|2086)\]$', line)]
    if refused or result.returncode not in (0, 1):
        raise RuntimeError('shellcheck -s sh: a bashism, an error, SC2028 or SC2086:\n'
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
                                     encoding="utf-8", errors="replace",
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


def acceptance():
    """Bootstrap a synthetic project, prove its gate passes, and prove the cases that need a
    whole bootstrapped project red: the lock, the scan of untracked files, deleted files and
    symlinks, the locale. Each check's own red case is a fixture test (tests/test_gate_checks.py;
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
        run(["git", "add", "."], project)
        run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS")
        # With CDPATH exported, `cd scripts` printed the directory into the gate's own path,
        # and the gate re-ran a two-line file name instead of its checks.
        run(["sh", "scripts/check.sh"], project, reason="CHECK: PASS", env=dict(os.environ, CDPATH="."))
        passed("bootstrap rejects missing setup and accepts the configured synthetic project")
        with tempfile.TemporaryDirectory(prefix="myagentkit-side-") as side:
            side = Path(side)
            # The lock cases set the build command the way a project does, in the copy's
            # check.sh: it runs side/build.sh, which each case rewrites. Restored below.
            build = side / "build.sh"
            gate = project / "scripts/check.sh"
            original_gate = gate.read_text(encoding='utf-8')
            configured = 'build_test_cmd="test -f scripts/claude_bridge.py"'
            if configured not in original_gate:
                raise RuntimeError("the synthetic project's build command line was not found")
            gate.write_text(original_gate.replace(
                configured, f'build_test_cmd="sh {shlex.quote(str(build))}"'), encoding='utf-8')
            own_lock = os.path.realpath(project) + "/.git/check.lock"
            if fcntl is None:
                print("NOT RUN: the POSIX gate-lock cases (native Windows; tests/test_check_gate_windows"
                      " proves the gate lock there)")
            else:
                posix_lock_cases(project, side, build, own_lock, gate)
            gate.write_text(original_gate, encoding='utf-8')
        # The scanners read untracked files too (git ls-files --others), not only the index.
        marker = project / "untracked-marker.md"
        marker.write_text("{{UNTRACKED" + "_MARKER}}\n", encoding='utf-8')
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
        # The review suite a project runs (scripts/review.sh --self-test) refuses a missing test
        # file and a suite emptied on its own, not hidden inside a combined test total.
        tests = project / "scripts/test_claude_bridge.py"
        original_tests = tests.read_bytes()
        tests.unlink()
        run(["sh", "scripts/review.sh", "--self-test"], project, expected=2,
            reason="review self-test file is missing or empty")
        tests.write_bytes(original_tests)
        quota_tests = project / "scripts/test_codex_quota.py"
        original_quota = quota_tests.read_bytes()
        quota_tests.write_text("import unittest\nclass QuotaTests(unittest.TestCase):\n    pass\n", encoding='utf-8')
        run(["sh", "scripts/review.sh", "--self-test"], project, expected=2,
            reason="QuotaTests has 0 of at least %d tests" % BRIDGE_MINIMUMS["test_codex_quota"])
        quota_tests.write_bytes(original_quota)
        passed("the review suite refuses a missing test file and an emptied suite")


def posix_lock_cases(project, side, build, own_lock, gate):
    """The gate lock's POSIX cases (flock): a killed holder, waiters, a symlink at the lock path,
    a bounded wait, an inherited descriptor, NFS and lockless file systems, a toolchain python3."""
    # Once a gate killed with SIGKILL and its build have exited, nobody holds the lock, and
    # the lock variables copied out of the killed run are refused: a copy is not the lock.
    build.write_text(f'echo "$GATE_LOCK_FD" > "{side}/fd.tmp"\nmv "{side}/fd.tmp" "{side}/fd"\n'
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
    run(["sh", "scripts/check.sh"], project, expected=1, timeout=60,
        reason="FAIL [env]: GATE_LOCK_HELD names this checkout's lock, but this run did not inherit",
        env=dict(os.environ, GATE_LOCK_HELD=own_lock,
                 GATE_LOCK_FD=(side / "fd").read_text(encoding='utf-8').strip()))
    passed("variables copied out of a gate killed with SIGKILL are refused")
    # Two gate runs sharing one build directory: the second must wait, not race.
    build.write_text(f'mkdir "{side}/build" && sleep 2 && rmdir "{side}/build"\n', encoding='utf-8')
    pair = [subprocess.Popen(["sh", "scripts/check.sh"], cwd=project,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace") for _ in range(2)]
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
                                text=True, encoding="utf-8", errors="replace") for _ in range(3)]
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
        # A descriptor opened independently on the same file is not the lock: the
        # holder's description holds it, this one does not.
        with open(lock) as other:
            run(["sh", "scripts/check.sh"], project, expected=1, timeout=30,
                reason="FAIL [env]: GATE_LOCK_HELD", pass_fds=(other.fileno(),),
                env=dict(os.environ, GATE_LOCK_WAIT="2", GATE_LOCK_HELD=own_lock,
                         GATE_LOCK_FD=str(other.fileno())))
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
        "_fake_flock()\n"
        # A nested run calls the holder's GATE_PYTHON, its sys.executable (#249): named as this
        # stand-in, the nested proof meets the same flock (it passed through the real one).
        "import sys as _sys; _sys.executable = %r\n" % str(fake / "python3"))
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


def structure():
    """The structural checks, a fast-tier unit beside the suites, never a serial step before
    them (#146). Their NOT RUN lines (shellcheck, the killing-test note) are repeated under the
    summary, as every unit's are."""
    check_syntax(ROOT)
    check_release(ROOT)
    check_actions(ROOT)
    untested_guards(ROOT)
    validate_plugin(ROOT)
    manifest = json.loads((ROOT / "plugins/myagentkit/.codex-plugin/plugin.json").read_text(encoding='utf-8'))
    # The name and skills path Codex's plugin scaffold writes; Codex documents no validator
    # (developers.openai.com/codex/plugins/build/, read 2026-10-15).
    if manifest["name"] != "myagentkit" or manifest["skills"] != "./skills/":
        raise RuntimeError("Codex plugin manifest does not expose the expected package")
    print(run([sys.executable, "scripts/package_codex_plugin.py", "--check"]).strip())


def unit(name, timing_file=None):
    """Run one unit in this process; 0 on a pass, 1 with the error printed on a failure."""
    try:
        # A unit is a whole folder of REQUIRED_SUITES, one of its modules ("tests/test_x"), one
        # shard of a module in SHARDS ("tests/test_x@1"), acceptance, the locale matrix, or one
        # suite of it ("locale/test_x").
        directory, _, module = name.rpartition("/")
        module, _, index = module.partition("@")
        if name == "structure":
            structure()
        elif name == "acceptance":
            acceptance()
        elif name == "locale":
            locale_matrix()
        elif directory == "locale":
            locale_matrix(suites=(module,))
        elif name in REQUIRED_SUITES:
            run_tests(ROOT, name, REQUIRED_SUITES[name])
        else:
            run_tests(ROOT, directory, {module: REQUIRED_SUITES[directory][module]},
                      (int(index), SHARDS[module]) if index else None)
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


def signal_unit(child, sig):
    """Signal a unit's whole process group (POSIX: each unit leads its own session). The unit
    is not reaped yet, so its group id is still its own."""
    try:
        os.killpg(child.pid, sig)
    except ProcessLookupError:
        pass


def stop_tree(child):
    """Kill a unit and every process below it: a shell or git it started keeps the output pipe
    open, and reading it would wait for them. Windows stops the tree, POSIX the unit's group.
    ponytail: a descendant that left the group (setsid) is waited for at most 30 s, then its
    output is dropped."""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(child.pid)], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        signal_unit(child, signal.SIGKILL)
    if child.poll() is None:
        child.kill()


def run_units(units, timing=False, parallel=None, said=(), caps=None, deadline=None, left_out=0):
    """Run the (name, command) units, `parallel` at once (default all); print each unit's whole
    output in the given order. Each unit's timeouts scale by `parallel` (see limit()). `said`:
    the NOT RUN lines the checks before the units printed, repeated under the summary first.
    `caps`: each unit's wall-clock cap in seconds; a unit still running at its cap is stopped
    and fails with its name and seconds (#146, run_units had no bound of its own).
    `deadline`: the tier budget's end (time.monotonic()); a unit still running then is stopped
    and named, and a unit queued after it does not start, so a CI job's timeout never cancels
    the run before it says what ran over.
    `left_out`: the tests of the suites that do not run on this host, counted by their
    REQUIRED_SUITES number, for the NOT RUN total under the summary (#231).

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
            # The wrapper signals the runner's group, which no unit is in (each leads its own
            # session): pass it on to each unit's group. Stop queued units too, and a child that
            # started just after that signal, before the executor waits for its workers.
            with lock:
                cancelled = True
                for child in children:
                    if child.poll() is None:
                        if os.name == 'nt':
                            stop_tree(child)
                        else:
                            signal_unit(child, signal.SIGTERM)
            pool.shutdown(wait=True, cancel_futures=True)

    def one(name, command, timing_file, cap):
        started = time.monotonic()
        if timing_file:
            command = command + ["--timing-file", timing_file]
        with lock:
            if cancelled:
                return 1, '', time.monotonic() - started
            if deadline is not None and started >= deadline:
                return 1, "KIT CHECK: FAIL — unit %s did not start: the tier's budget ran out\n" % name, 0.0
            # Its own session: a cap or a cancel stops the unit's test processes with it.
            child = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, env=env, start_new_session=True,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            children.append(child)
        left = None if deadline is None else max(deadline - started, 0)
        budget_first = left is not None and (cap is None or left < cap)
        with child:
            try:
                output = child.communicate(timeout=left if budget_first else cap)[0]
            except subprocess.TimeoutExpired:
                stop_tree(child)
                try:
                    output = child.communicate(timeout=30)[0]
                except subprocess.TimeoutExpired:
                    output = ''
                why = ("was still running when the tier's budget ran out" if budget_first
                       else "ran over its cap of %.0f s" % cap)
                return 1, output + ("KIT CHECK: FAIL — unit %s %s and was stopped at %.0f s\n"
                                    % (name, why, time.monotonic() - started)), time.monotonic() - started
        return child.returncode, output, time.monotonic() - started

    parallel = parallel or len(units)
    # Capped at 4: under load a unit ran 1.2-1.7x slower (#146), and 10x at 20 CPUs let a hung
    # acceptance phase (1800 s) run for five hours before it failed.
    env = dict(os.environ, **{SCALE: str(float(os.environ.get(SCALE, "1")) * min(parallel, 4))})
    with tempfile.TemporaryDirectory(prefix="myagentkit-timing-") as times, \
            ThreadPoolExecutor(max_workers=parallel) as pool, stop_units():
        files = [os.path.join(times, str(number)) if timing else None for number in range(len(units))]
        futures = [pool.submit(one, name, command, timing_file, cap)
                   for (name, command), timing_file, cap in zip(units, files, caps or [None] * len(units))]
        summary, failed, not_run, ran, skipped = [], [], list(said), 0, 0
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
            # run_tests' PASS line counts the tests that ran and its declared platform skips; a
            # passing test's own "NOT RUN: <test id> (<reason>)" line is no skip (it ran).
            for count, skips in re.findall(r"^PASS: \S+ ran (\d+) tests(?: \((\d+) declared platform skips\))?",
                                           output, re.M):
                ran, skipped = ran + int(count), skipped + int(skips or 0)
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
    # The share of the suites a local pass covers, in one line: the per-test lines above are
    # easy to scroll past. Only after a full pass: a failed unit printed no count.
    if ran and not failed:
        print("NOT RUN: %d of %d tests of this run's suites on this platform (%d declared platform skips, "
              "%d in suites that do not run here, counted by their REQUIRED_SUITES number)"
              % (skipped + left_out, ran + skipped + left_out, skipped, left_out))
    if failed:
        print("KIT CHECK: FAIL — %d of %d units failed: %s" % (len(failed), len(units), ", ".join(failed)),
              file=sys.stderr)
    return not failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timing", action="store_true",
                        help="print each unit's, phase's and slowest test's seconds at the end")
    tier = parser.add_mutually_exclusive_group()
    tier.add_argument("--slow", action="store_true",
                      help="run the slow tier alone (bootstrap, acceptance, the review bridge, doctor, worker-spawn and close_worker suites, the locale run of test_git_hooks)")
    tier.add_argument("--all", action="store_true", help="run the fast and the slow tier (a release)")
    parser.add_argument("--unit", help=argparse.SUPPRESS)
    parser.add_argument("--timing-file", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.unit:
        return unit(args.unit, args.timing_file)
    started = time.monotonic()
    # One unit per test module and per locale suite, so the slowest module, not a folder of
    # them run one after another, sets the wall time (#146): 3358 s for tests/ on Windows CI.
    # The sharded modules start first, right after acceptance: they are the longest units, and a
    # long unit queued last sets the wall time alone.
    # "structure" first: the structural checks run as a unit beside the suites, not before them.
    units, rest, not_here = ["structure", "acceptance"], [], []
    for directory, required in REQUIRED_SUITES.items():
        uncounted = sorted({path.stem for path in (ROOT / directory).glob("test_*.py")} - set(required))
        if uncounted:
            raise RuntimeError("%s: no count in REQUIRED_SUITES for %s" % (directory, ", ".join(uncounted)))
        reasons = NOT_ON_WINDOWS.get(directory, {})
        # A module that does not run on this host gets its NOT RUN line, not a unit that
        # passed with "ran 0 tests".
        not_here += ["NOT RUN: %s/%s on native Windows (%s); CI's Linux and macOS jobs run it"
                     % (directory, name, reasons[name]) for name in required if name in reasons]
        for name in required:
            if name not in reasons:
                (units if name in SHARDS else rest).extend(
                    directory + "/" + name + suffix
                    for suffix in (["@%d" % index for index in range(SHARDS[name])] if name in SHARDS else [""]))
    units += rest
    units += ["locale/" + name for name in LOCALE_SUITES]
    module = lambda name: name.rpartition("/")[2].partition("@")[0]
    stale = SLOW - {module(name) for name in units} - set(units) - {name for required in NOT_ON_WINDOWS.values() for name in required}
    if stale:
        raise RuntimeError("SLOW names no unit of the kit check: " + ", ".join(sorted(stale)))
    units.sort(key=lambda name: (name not in ("structure", "acceptance"), module(name) not in SHARDS,
                                 module(name) not in LONG))
    tiers = ["fast", "slow"] if args.all else ["slow"] if args.slow else ["fast"]
    tier_of = lambda name: "slow" if module(name) in SLOW or name in SLOW else "fast"
    units = [name for name in units if tier_of(name) in tiers]
    host = float(os.environ.get(SCALE, "1"))
    budget = sum(CAPS[name][1] for name in tiers) * host
    cpus = os.cpu_count() or 1
    parallel = degree(cpus, len(units))
    print("KIT CHECK: %s tier, %d of %d units at once (%d CPUs), %.0f s budget"
          % (" and ".join(tiers), parallel, len(units), cpus, budget))
    for line in not_here:
        print(line)
    # -u: a unit's error, on stderr, lands after what it printed before failing.
    command = [sys.executable, "-B", "-u", str(Path(__file__).resolve())]
    left_out = sum(REQUIRED_SUITES[directory][name] for directory, reasons in NOT_ON_WINDOWS.items()
                   for name in reasons if tier_of(name) in tiers)
    passed = run_units([(name, command + ["--unit", name]) for name in units], args.timing, parallel, said=not_here,
                       caps=[CAPS[tier_of(name)][0] * host for name in units], deadline=started + budget,
                       left_out=left_out)
    seconds = time.monotonic() - started
    if passed:
        print("TIME: %.1f s in all" % seconds)
    if seconds > budget:
        print("KIT CHECK: FAIL — the %s tier took %.0f s, over its budget of %.0f s; move a slow unit to the "
              "slow tier or make it faster" % (" and ".join(tiers), seconds, budget), file=sys.stderr)
        return 1
    if not passed:
        return 1
    if _PASSED_FILE:
        marker = Path(_PASSED_FILE)
        # A long native kit check outlived its empty temporary marker directory. Recover
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
