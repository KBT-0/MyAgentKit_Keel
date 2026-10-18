#!/usr/bin/env sh
# {{PROJECT_NAME}} quality gate — EVERY agent runs this before finishing a task.
# CI runs the SAME script. There is one definition of "green" in this repository, and it is
# here — which is NOT the same as a promise that local and CI always agree. Same script,
# different machine: file modes, installed tools and locale can all differ (docs/GOTCHAS.md
# has the exit-126 case that kept a pipeline red for weeks). Check the pipeline after
# pushing; do not infer it from a local pass. The git hooks are the local backstop, and a
# hook can be skipped (`--no-verify`); the check that holds is this gate in CI, set as a
# required status check on the protected branch (docs/DEV_SETUP.md; git-scm.com/docs/githooks,
# anthropics/claude-code#40117). CI runs it on every pull request with no path filter: a
# workflow skipped by path leaves a required check Pending (GitHub, "Troubleshooting required
# status checks"), and this script already decides what a documentation-only change skips.
#
# Usage: check.sh [--for-commit]
#   default       run the gates
#   --for-commit  what .githooks/pre-commit runs: the gates, without the build when the
#                 staged change is documentation only (section 4 decides; the flag only asks)
#
# ADDING A GATE: add the check, AND a fixture test for it in the project's test suite: a
# small input that breaks the rule must turn the check red with its own `FAIL [tag]` line,
# and a clean one must leave it green (docs/WORKFLOW.md, "Writing a gate"; Semgrep's
# ruleid/ok, semgrep.dev/docs/writing-rules/testing-rules). A gate without a negative test
# has not been proven to fail — it has only been seen passing, which is not the same thing.
# The fixture test never runs this whole gate or the build; the kit tests this file's own
# checks the same way (the kit's tests/test_gate_checks.py).
#
# EXIT CODES: 0 pass, 1 fail, 2 usage, 75 NOT RUN — another gate run held this checkout's
# lock for longer than GATE_LOCK_WAIT=<seconds> allowed (unset: wait without limit, which is
# what manual, CI and commit-hook runs want; the Stop hook sets about 500 so it answers
# before its own timeout kills it). A caller reports 75 as "gate did not run", never as a
# pass and never as a gate failure.
#
# EVERY CHECK BELOW MUST FAIL ON ABSENT EVIDENCE. A missing input file, a scanner that could
# not run, a command that was never configured: all FAIL. Silence is not success. Five
# separate paths in an earlier version of this script violated that rule and reported PASS
# while enforcing nothing; a cross-model review found them.
#
# THREAT MODEL. Defended: mistakes and accidents of the owner and the agents (a killed run,
# Ctrl-C, a leftover file, CRLF, an owner's symlink, a stale environment from a killed gate).
# Out of scope: a process changing the tree while the gate runs to fool it, and hostile files
# planted by anyone but the owner; either could edit this script instead.
set -u
# CDPATH cleared: exported, it made `cd scripts` print the directory into $gate, and the
# lock below re-ran a two-line file name instead of the gate. The path is LOGICAL (pwd, not
# pwd -P): the lock re-runs the gate by it, and the re-run cd's to its parent. With scripts/
# a symlink into a shared tree, the physical path made the re-run check and build that tree.
gate=$(CDPATH= cd -- "$(dirname "$0")" && pwd)/${0##*/}
CDPATH= cd -- "$(dirname "$0")/.."
fail=0

# Toolchains are commonly installed per-user and then missing from the PATH of git hooks
# and other non-login shells; without this the gate fails for the wrong reason. A VALUE, not
# a line of code — a placeholder that has to be replaced INSIDE a comment is a trap, because
# a half-finished edit leaves the code commented out and the gate silently toothless.
# Applied FIRST, before the lock below resolves python3: a python3 installed only here was
# not found, and a hook failed on a machine doctor.sh, which prepends it first, called ready.
# Example: "$HOME/.dotnet". Leave empty if nothing extra is needed.
toolchain_path="{{TOOLCHAIN_PATH_SETUP}}"
case "$toolchain_path" in
  ""|*"{{"*) ;;
  *) PATH="$toolchain_path:$PATH"; export PATH ;;
esac
# Resolved AFTER toolchain_path joined PATH: a python3 only there is the one a hook sees.
# Windows installs Python as `python` or `py`: when `python3` is absent or does not run (a
# Store alias exits 9009), the scripts call the first of those that runs under the usual
# name. A function is enough for a call; an `exec` cannot run a function, so the exec sites
# use $kit_python, the resolved command.
if python3 -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python3
elif python -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python
else kit_python="py -3"; fi   # the launcher, told which Python: unquoted at every use
[ "$kit_python" = python3 ] || python3() { $kit_python "$@"; }
$kit_python -I -c 'import sys; sys.exit(sys.version_info < (3, 11))' </dev/null >/dev/null 2>&1 ||
  { echo "FAIL [python]: Python 3.11 or newer is required (python3, python, py -3)." >&2; exit 1; }

lock_path=$(git rev-parse --git-path check.lock 2>/dev/null) || lock_path=.check.lock
# Git for Windows prints a linked worktree's git path as C:/...; that is absolute too.
case "$lock_path" in /*|[A-Za-z]:/*) ;; *) lock_path="$(pwd -P)/$lock_path" ;; esac
# Git for Windows, MSYS2 and Cygwin: the path in the form a native program is handed (C:/...).
# A native python3 receives /c/... as C:/... and exports GATE_LOCK_HELD in that form, so a
# lock path kept as /c/... never matched its own nested runs, and each one waited for itself.
# Only on a host that names itself one of those: a cygpath that merely sits on a POSIX PATH (a
# shim, a stray install) turned the POSIX lock path into one Python read as relative.
case "$(uname -s 2>/dev/null)" in
  MSYS*|MINGW*|CYGWIN*) lock_path=$(cygpath -m "$lock_path") ;;
esac
# A run that claims the lock (GATE_LOCK_HELD names this checkout's) proves it: the descriptor
# GATE_LOCK_FD it inherited is open on this lock file, the lock is held, so a fresh open of
# the file cannot take it, and that descriptor itself holds it: flock on it succeeds at once
# only on the open file description already holding the lock. A descriptor opened on the same
# file independently, while another gate holds it, would block. Otherwise it FAILS by name;
# it never skips the lock on a claim. The independent descriptor is open for writing: Linux's
# NFS client refuses an exclusive flock on a read-only one, and every fresh run failed here.
# A flock error other than "would block" is the file system, not the claim: FAIL [lock].
# On native Windows GATE_LOCK_FD is the holder's Win32 handle (the lock below says why). It
# must be open in this process on this lock file with write access (FlushFileBuffers needs
# it), and a fresh open for writing must fail with a sharing violation. While the holder has
# the file open without write sharing, no other handle with write access can be opened, so
# only the holder's handle and the copies its descendants inherited pass all three. The number
# alone, copied into another process, names nothing there or something else. "This lock file"
# is the whole FILE_ID_INFO, the volume serial and the 128-bit file id: os.stat's st_ino held
# 64 bits of it before Python 3.12, which ReFS does not keep unique, so a writable handle on
# another file could match. A volume that gives no FILE_ID_INFO fails FAIL [lock]: unproven.
inherited=""
if [ "${GATE_LOCK_HELD:-}" = "$lock_path" ]; then
  lock_probe=0
  python3 -I -c '
import os, sys
if os.name == "nt":
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = (ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                                     ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p)
    kernel32.GetFileInformationByHandleEx.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong)
    kernel32.FlushFileBuffers.argtypes = kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    def file_id(handle):
        info = ctypes.create_string_buffer(24)
        return info.raw if kernel32.GetFileInformationByHandleEx(handle, 18, info, 24) else None
    def open_lock(access):
        # Shared every way, so only a holder that refuses writers can make it fail; a link as itself.
        handle = kernel32.CreateFileW(sys.argv[2], access, 7, None, 3, 0x02200000, None)
        return None if handle in (None, ctypes.c_void_p(-1).value) else handle
    try:
        held = int(sys.argv[1])
    except ValueError:
        sys.exit(1)
    lock = open_lock(0x80)
    if lock is None:
        sys.exit(1)
    lock_id, error = file_id(lock), ctypes.get_last_error()
    kernel32.CloseHandle(lock)
    if lock_id is None:
        print("FAIL [lock]: the volume holding %s gives it no stable file id (FILE_ID_INFO, Windows error %d), which a nested gate run needs to prove it holds the lock." % (sys.argv[2], error))
        sys.exit(3)
    if file_id(held) != lock_id or not kernel32.FlushFileBuffers(held):
        sys.exit(1)
    fresh = open_lock(0x40000000)
    if fresh is not None:
        kernel32.CloseHandle(fresh)
        sys.exit(1)
    sys.exit(0 if ctypes.get_last_error() == 32 else 1)
try:
    import fcntl
except ImportError:
    print("FAIL [lock]: python3 has no fcntl module, which the gate lock needs on this system.")
    sys.exit(3)
held, lock = os.fstat(int(sys.argv[1])), os.stat(sys.argv[2])
if (held.st_dev, held.st_ino) != (lock.st_dev, lock.st_ino):
    sys.exit(1)
other = os.open(sys.argv[2], os.O_RDWR)
try:
    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
    sys.exit(1)
except BlockingIOError:
    pass
except OSError as error:
    print("FAIL [lock]: this file system does not support the gate lock (%s); the lock file is %s." % (error.strerror or error, sys.argv[2]))
    sys.exit(3)
fcntl.flock(int(sys.argv[1]), fcntl.LOCK_EX | fcntl.LOCK_NB)
' "${GATE_LOCK_FD:-}" "$lock_path" 2>/dev/null || lock_probe=$?
  case "$lock_probe" in
    0) inherited=1 ;;
    3) fail=1 ;;
    *) echo "FAIL [env]: GATE_LOCK_HELD names this checkout's lock, but this run did not inherit the descriptor"
       echo "            holding it (GATE_LOCK_FD); a copied variable is not the lock. Unset GATE_LOCK_HELD and GATE_LOCK_FD."
       fail=1 ;;
  esac
fi
[ "$fail" -eq 0 ] || exit 1

# ONE GATE RUN PER CHECKOUT AT A TIME. The Stop hook, the commit hook and a manual run can
# start together, and a project's build command usually writes one fixed build directory:
# two runs sharing it configured, built and ran tests over each other and one reported FAIL
# for a tree that passes alone. A second run therefore WAITS here; it never fails for this.
# The lock is a kernel lock, flock(2) on the file at lock_path, taken by the few lines of
# Python below because POSIX sh has none; fcntl.flock is in Python's standard library on
# Linux and macOS alike. The holder then execs this script with the lock's descriptor left
# open, so the gate and every process it starts hold the lock, and the kernel releases it
# when the last of them exits. That is the point: a gate killed with SIGKILL keeps the lock
# for as long as the build it started still runs, so the next gate cannot build over it.
# Nothing is ever reclaimed and no pid is trusted; the symlink lock this replaces guessed
# staleness from pids, and let a third waiter, or a build left running, through. The cost:
# a build tool that leaves a server running after the build (a compiler server, a build
# daemon) holds the lock until that server exits, so such a build command turns it off
# (docs/GOTCHAS.md); the waiting NOTE says how to find the holder.
# NATIVE WINDOWS (Git for Windows' sh with a Windows python3) has no fcntl, and there the lock
# is the file opened for writing WITHOUT write sharing: Windows refuses every other open for
# writing while any handle of that open exists. The holder makes its handle inheritable and
# starts the gate as a child, so the gate and every process it starts that inherits handles
# hold the lock, and Windows closes the last handle when the last of them exits: the same
# guarantees as flock, a killed holder included (its build keeps the lock). It cannot exec
# (os.execv on Windows starts a new process and exits, so the caller would see the gate end
# at once): it waits for the gate and passes its exit status on. msvcrt.locking was not used:
# its byte-range lock belongs to the one process that took it, and Windows releases it when
# that process ends, while the build runs on. A python3 without fcntl elsewhere: FAIL [lock].
# Nested runs (a gate that a process of this gate starts in this checkout) inherit the lock:
# GATE_LOCK_HELD names the lock path, so a gate in another checkout started from the build
# command still takes its own lock, and GATE_LOCK_FD names the inherited descriptor, which
# the proof above checks before it believes the claim. Nothing is written into the lock file.
case "${GATE_LOCK_WAIT:-}" in
  *[!0-9]*) printf '%s\n' "FAIL [lock]: GATE_LOCK_WAIT must be a number of seconds, got '$GATE_LOCK_WAIT'."; exit 1 ;;
esac
if [ -z "$inherited" ]; then
  $kit_python -I -c '' </dev/null >/dev/null 2>&1 ||
    { echo "FAIL [lock]: no Python runs (python3, python, py -3), and the gate lock is taken through it."; exit 1; }
  # Python ignores SIGPIPE and SIGXFSZ and catches SIGINT; the wait and the gate get back
  # what sh would have given them.
  # O_NOFOLLOW: a symlink here (the older lock's, left by a killed run) is refused by name.
  # The host picks the lock (os.name), never whether `import fcntl` works, and both lock
  # programs run isolated (-I): a fcntl.py or ctypes.py in the checkout or on
  # PYTHONPATH was imported first, and a stand-in fcntl that always "locked" let two gates run.
  exec $kit_python -I -c '
import os, signal, sys, time
if os.name == "nt":
    fcntl = None
    # A pipe gets the ANSI code page: a path outside it (a user name, the U+F03A cygpath makes of a
    # colon) ended a NOTE or FAIL line in a UnicodeEncodeError traceback.
    sys.stdout.reconfigure(errors="backslashreplace")
else:
    try:
        import fcntl
    except ImportError:
        print("FAIL [lock]: python3 has no fcntl module, which the gate lock needs on this system.", flush=True)
        sys.exit(1)
path, gate, wait, waited, interrupted = sys.argv[1], sys.argv[2], os.environ.get("GATE_LOCK_WAIT", ""), 0, []
if signal.getsignal(signal.SIGINT) is signal.default_int_handler:
    signal.signal(signal.SIGINT, signal.SIG_DFL)
def cannot_open(reason):
    print("FAIL [lock]: cannot open %s as the gate lock (%s); if it is a symlink or a directory, delete it." % (path, reason), flush=True)
    sys.exit(1)
if fcntl:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644)
    except OSError as error:
        cannot_open(error.strerror)
    def take():
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False
        except OSError as error:
            print("FAIL [lock]: this file system does not support the gate lock (%s); the lock file is %s." % (error.strerror or error, path), flush=True)
            sys.exit(1)
    find = "fuser -v %s, or lsof %s" % (path, path)
else:
    import ctypes, msvcrt, subprocess
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = (ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                                     ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p)
    def take():
        global fd
        # Read and write, shared for reading only, created when absent, a link opened as itself.
        handle = kernel32.CreateFileW(path, 0xC0000000, 1, None, 4, 0x200080, None)
        if handle in (None, ctypes.c_void_p(-1).value):
            error = ctypes.get_last_error()
            if error == 32:
                return False
            cannot_open("Windows error %d" % error)
        fd = msvcrt.open_osfhandle(handle, os.O_RDWR)
        if os.fstat(fd).st_file_attributes & 0x400:
            cannot_open("a symlink or another reparse point")
        return True
    find = "Resource Monitor (resmon), CPU tab, Associated Handles, search for %s" % os.path.basename(path)
    # Ctrl-C: this process outlives it to pass on the status of the gate (the holder exits 130,
    # the build stops, the next gate takes the lock). The handler records it from here on: one
    # that came before the gate was created reached no gate, so the gate is not started and the
    # status is 130. A handler, not
    # SIG_IGN: on the hosts measured the two behave alike for the gate, since SIG_IGN in CPython
    # on Windows is not the inherited ignore flag and sh starts with Ctrl-C enabled.
    signal.signal(signal.SIGINT, lambda *_: interrupted.append(1))
while not take():
    if interrupted:
        sys.exit(130)
    if wait and waited >= int(wait):
        print("NOT RUN [lock]: another gate run, or a process it started, has held %s for %ds; GATE_LOCK_WAIT=%s ran out." % (path, waited, wait), flush=True)
        sys.exit(75)
    if waited % 30 == 0:
        print("NOTE [lock]: another gate run, or a process it started, has held %s for %ds; waiting for it." % (path, waited), flush=True)
        if waited == 0:
            print("             To see the holder: %s. A server the build left running (a compiler\n"
                  "             server, a build daemon) holds it until that server exits: docs/GOTCHAS.md." % find, flush=True)
    time.sleep(1)
    waited += 1
if fcntl:
    # A copy that survives exec, above the fds sh scripts redirect; nested runs prove they hold it.
    os.environ["GATE_LOCK_FD"] = str(fcntl.fcntl(fd, fcntl.F_DUPFD, 10))
    os.environ["GATE_LOCK_HELD"] = path
    os.execvp("sh", ["sh", gate] + sys.argv[3:])
# Native Windows: no exec (os.execv starts a new process and this one exits, so the caller
# would read the gate as finished), so this process waits for the gate and passes its status on.
os.set_handle_inheritable(msvcrt.get_osfhandle(fd), True)
os.environ["GATE_LOCK_FD"] = str(msvcrt.get_osfhandle(fd))
os.environ["GATE_LOCK_HELD"] = path
# The gate is created suspended and the Ctrl-C record is read only once it exists: read before
# the launch, a Ctrl-C between that read and the launch reached no gate, and the gate it then
# started ran its build to the end. Read after, every earlier Ctrl-C is seen and the suspended
# gate, which never ran a line, is killed; a later one reaches the gate through the console.
# GATE_LOCK_TEST_SIGINT_AT_LAUNCH raises a Ctrl-C right before the launch (how the kit tests
# this window); it can only stop a gate, never pass one, and says so when it is set.
if interrupted:
    status = 130
else:
    if os.environ.get("GATE_LOCK_TEST_SIGINT_AT_LAUNCH"):
        print("NOTE [lock]: GATE_LOCK_TEST_SIGINT_AT_LAUNCH is set: a Ctrl-C is raised as the gate starts.", flush=True)
        signal.raise_signal(signal.SIGINT)
    child = subprocess.Popen(["sh", gate] + sys.argv[3:], close_fds=False, creationflags=0x4)
    if interrupted or ctypes.WinDLL("ntdll").NtResumeProcess(ctypes.c_void_p(int(child._handle))) != 0:
        child.kill()
        child.wait()
        if not interrupted:
            print("FAIL [lock]: the gate was created but could not be started (NtResumeProcess).", flush=True)
        status = 130 if interrupted else 1
    else:
        status = child.wait()
# A Ctrl-C after the check below came after the gate ended: its status stands, as on POSIX.
if interrupted:
    sys.exit(130)
# Git for Windows hands native Python a child killed by signal N as N << 8, and sh would read
# only its low byte, 0: a killed gate passed. It becomes 128 + N; anything else unknown is 1.
sys.exit(status if 0 <= status < 256 else 128 + (status >> 8) if status & 255 == 0 and status < 32768 else 1)
' "$lock_path" "$gate" "$@"
fi

# The strong review cycle's cadence (section 2 says why): owner choices, not measured values.
STRONG_REVIEW_DAYS=10
STRONG_REVIEW_TASKS=20

work=$(mktemp -d) || { echo "FAIL [gate]: cannot create a temp dir; refusing to run blind."; exit 1; }
# The lock file itself stays: removing a flock file lets a waiter lock the removed file while
# the next run creates and locks a new one, and both run.
trap 'rm -rf "$work"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
filelist="$work/files"

# lock_path is computed near the top. The build/test command's full output goes
# beside the lock: outside the tree, one per checkout. Without git it goes to a temp file.
case "$lock_path" in
  */.check.lock) build_log=$(mktemp) || { echo "FAIL [gate]: cannot create a temp file; refusing to run blind."; exit 1; } ;;
  *) build_log="${lock_path%.lock}-build.log" ;;
esac

for_commit="" pass_note=""
case "${1:-}" in
  "")           ;;
  --for-commit) for_commit=1 ;;
  *)            echo "usage: check.sh [--for-commit]"; exit 2 ;;
esac

# Every scan, filter and boundary check below reads text in the C locale. In a UTF-8 locale
# GNU grep takes a line holding a byte that is not valid UTF-8 (a Latin-1 comment, a legacy
# string literal, a symlink target) as binary: `grep -I` skipped the file, a plain grep
# printed "binary file matches" on stderr and nothing on stdout, and `.` stopped at the byte.
# A placeholder on such a line passed the gate, and so did a boundary hit piped through
# `grep '^src/domain/'`. In C every byte is a character. The build/test command alone gets
# the caller's locale back (section 4): compilers and test runners read sources by locale.
caller_lc_all=${LC_ALL-} caller_lc_all_set=${LC_ALL+1}
LC_ALL=C; export LC_ALL

# ---------------------------------------------------------------------------
# The scanners' shared input: every tracked file plus every untracked one git does not
# ignore, NUL-separated so that newlines and spaces in names survive.
#
# Collected ONCE, into a file, and its failure is FATAL. An earlier version ran the
# producer inside a pipeline ending in `|| true`, so a failed `git ls-files` was
# indistinguishable from "no matches" and the gate went green while scanning nothing.
# ---------------------------------------------------------------------------
if git rev-parse --git-dir >/dev/null 2>&1; then
  if ! git ls-files -z --cached --others --exclude-standard > "$filelist"; then
    echo "FAIL [scan]: git ls-files failed — the scanners below cannot see the tree,"
    echo "             so their silence would mean nothing. Fix this first."
    exit 1
  fi
else
  if ! find . -path ./.git -prune -o -type f -print0 > "$filelist"; then
    echo "FAIL [scan]: find failed — the scanners below cannot see the tree."
    exit 1
  fi
fi
# Paths grep cannot read as files are sorted out here, each under its real cause, instead of
# surfacing later as "a scanner failed to run". A tracked file deleted without `git rm` is
# named and FAILS the gate: the scan cannot vouch for a path the commit may still carry.
# Only a regular file reaches grep (an allowlist): anything else is named here.
# A SYMLINK IS NEVER FOLLOWED. What git tracks of a symlink is its link text, read here
# without following the link and scanned as a line of its own; the link then leaves the file
# list, whatever it points at. grep once followed a link to an existing file: a file outside
# the tree leaked its lines into the scan, and a link to a FIFO hung the gate. A dangling
# link whose text held a setup marker was once skipped whole, and the marker passed. A link
# to a directory (a dependency directory linked into a fresh worktree, which an ignore
# pattern with a trailing slash does not match) and a dangling link each get a line. The
# path goes to readlink behind "./": a link named "--version" was read as the option.
# A submodule (a gitlink, mode 160000) and a repository inside this one (git lists it as
# "dir/") are directories whose files belong to another repository: skipped with a line,
# nothing inside scanned. grep exited 2 on them and the gate could never pass. Any other
# path that is not a regular file (a tracked file replaced by a directory or a FIFO) FAILS
# by name: grep hung on the FIFO and called the directory a scanner failure.
# Each line carries the link's own path in grep's "path:line:" form, and scan_grep prints it
# as is: reported under the temporary file's name, a link in the exempt setup/ failed the gate.
# One line per link, every newline in it written as \n: link text that went on over a newline
# to "setup/" and a marker put that marker on a line of its own, which the setup/ exemption
# removed. A failed append is fatal: ignored, the link's text went unscanned and the gate
# could pass.
escape_lines='NR > 1 { printf "\\n" } { printf "%s", $0 } END { print "" }'
if ! xargs -0 sh -c '
  scan_work=$1
  escape_lines=$2
  shift 2
  for p do
    p=${p#./}  # the find fallback names ./src/a, git names src/a: every reader gets the git form
    if [ -L "$p" ]; then
      if t=$(readlink "./$p"); then
        printf "%s:1:symlink %s -> %s\n" "$p" "$p" "$t" | awk "$escape_lines" >> "$scan_work/symlink-text" || {
          printf "%s\n" "FAIL [scan]: could not record the link text of the symlink $p." >&3
          exit 1
        }
      else
        printf "%s\n" "FAIL [scan]: cannot read the link text of the symlink $p." >&3
        : > "$scan_work/scan_missing"
      fi
    fi
    if [ -L "$p" ]; then
      if [ -d "$p" ]; then
        printf "%s\n" "NOTE [scan]: skipped $p, a symlink to a directory; git tracks nothing inside it." >&3
        printf "%s\n" "             To ignore it, write it in .gitignore without a trailing slash." >&3
        : > "$scan_work/scan_unhashed"
      elif [ ! -e "$p" ]; then
        printf "%s\n" "NOTE [scan]: skipped $p, a symlink whose target is missing; its link text is scanned instead." >&3
      fi
    elif [ -f "$p" ]; then
      # grep reads a bare "-" as stdin even after "--": a marker in a file named "-" passed.
      case $p in -*) printf "./%s\0" "$p" ;; *) printf "%s\0" "$p" ;; esac
    elif [ -d "$p" ] && { case "$p" in */) true ;; *) false ;; esac ||
                          [ "$(git ls-files -s -- ":(literal)$p" | cut -c1-6)" = 160000 ]; }; then
      printf "%s\n" "NOTE [scan]: skipped $p, a submodule or a repository inside this one; its files belong to that repository." >&3
      : > "$scan_work/scan_unhashed"
    elif [ ! -e "$p" ]; then
      printf "%s\n" "FAIL [scan]: $p is tracked but missing from the working tree (deleted, not staged)." >&3
      printf "%s\n" "             Run git rm -- \"$p\" to record the deletion, or git restore -- \"$p\"." >&3
      : > "$scan_work/scan_missing"
    else
      printf "%s\n" "FAIL [scan]: $p is not a regular file (a directory, FIFO, socket or device where git expects a file)." >&3
      printf "%s\n" "             The scan cannot read it; restore the file or record the change with git." >&3
      : > "$scan_work/scan_missing"
    fi
  done
' sh "$work" "$escape_lines" < "$filelist" 3>&1 > "$filelist.kept"; then
  echo "FAIL [scan]: could not sort the file list; refusing to scan blind."
  exit 1
fi
mv "$filelist.kept" "$filelist"
[ ! -e "$work/scan_missing" ] || fail=1
if [ ! -s "$filelist" ] && [ ! -s "$work/symlink-text" ]; then
  echo "FAIL [scan]: the file list is EMPTY. A scan over nothing always passes, which is"
  echo "             exactly the failure this gate exists to prevent."
  exit 1
fi
# scan_grep <extended-regex> — prints path:line:text for every match.
# Returns 0 on match, 1 on no match. When grep itself FAILS, it drops a flag file that the
# main shell checks before the final verdict. The flag, not an exit, is deliberate: callers
# run this inside command substitutions, where `exit` terminates only the SUBSHELL — an
# earlier version "exited fatally" from inside `$(...)` and the gate sailed on to PASS.
# A file crosses that boundary; nothing a caller does can turn a failed scan into a clean one.
scan_grep() {
  # -e keeps a pattern starting with "-" from being read as an option; -- ends the option
  # list so a file literally named "-v" is scanned instead of parsed. /dev/null guarantees
  # at least one file argument, so grep never falls back to stdin and always prints names.
  # GNU xargs maps grep's no-match exit to 123; BSD xargs maps several command
  # failures to 1. Preserve grep's meaning inside each batch before xargs maps it.
  rm -f "$work/scan_matched"
  xargs -0 sh -c '
    pattern=$1
    scan_work=$2
    shift 2
    grep -InE -e "$pattern" -- /dev/null "$@"
    case "$?" in
      0) : > "$scan_work/scan_matched" ;;
      1) ;;
      *) : > "$scan_work/scan_failed" ;;
    esac
    exit 0
  ' sh "$1" "$work" < "$filelist" 2>/dev/null
  st=$?
  [ "$st" -eq 0 ] || : > "$work/scan_failed"
  if [ -e "$work/symlink-text" ]; then
    grep -hE -e "$1" -- "$work/symlink-text"
    case "$?" in
      0) : > "$work/scan_matched" ;;
      1) ;;
      *) : > "$work/scan_failed" ;;
    esac
  fi
  [ ! -e "$work/scan_failed" ] || return 2
  [ -e "$work/scan_matched" ]
}

# ---------------------------------------------------------------------------
# 1) Setup completeness — unfilled placeholders
# ---------------------------------------------------------------------------
# The kit ships double-brace markers for everything the setup interview must decide. While
# any survive, this project has not been set up and every rule below is a half-written
# sentence. That is a FAIL, not a warning.
#
# Two paths are EXEMPT because they carry markers on purpose, forever:
#   setup/                       the interview documents every marker by name
#   MODULE_AGENTS_TEMPLATE.md    a template that is COPIED per module, never filled in place
# Without these exemptions a correctly configured project can never go green — which is
# exactly what happened, and neither file is something the owner may simply delete, because
# sync-kit.sh restores both.
hits=$(scan_grep '\{\{[A-Z0-9_]+\}\}' | grep -Ev '^(setup/|MODULE_AGENTS_TEMPLATE\.md:)' || true)
if [ -n "$hits" ]; then
  echo "FAIL [setup]: unfilled placeholder markers remain — run setup/INTERVIEW.md:"
  printf '%s\n' "$hits" | head -30
  [ "$(printf '%s\n' "$hits" | wc -l)" -gt 30 ] && echo "              ... and more"
  fail=1
fi

# ---------------------------------------------------------------------------
# 2) STATE.md: present, and free of finished tasks
# ---------------------------------------------------------------------------
# Its LENGTH is not checked. A line or size limit cannot tell a live line from a finished
# one: a project that added a size limit hit it four times in one session, while half the
# file was a backlog and much of the rest narrated work already in git. The backlog now has
# its own file (docs/BACKLOG.md), and finished work is caught by name, below.
#
# A missing file or a renamed heading is a FAILURE, not a skip. Skipping there meant the
# whole check could be disabled by deleting one file or editing one line.
if [ ! -f docs/STATE.md ]; then
  echo "FAIL [state]: docs/STATE.md does not exist. It is the cross-session memory; without it"
  echo "              this check proves nothing."
  fail=1
elif ! grep -q "^## Active work" docs/STATE.md; then
  echo "FAIL [state]: docs/STATE.md has no '## Active work' heading. Restore the heading"
  echo "              rather than removing the check."
  fail=1
fi

# Finished work. The commit that finishes a task says so with a "Done: <id>" trailer
# (docs/WORKFLOW.md, "Task ids"), and every id that a commit reachable from HEAD closed must
# be gone from the state file and from the BACKLOG.md beside it, which may be absent (a
# project may keep its backlog elsewhere), and from the strong review cycle's list and
# reports. Historical audit mentions are advisory, so an upgrade does not fail on old reports
# (B11 inv1#118 A; Martini, Besker and Bosch 2018;
# code.claude.com/docs/en/best-practices, "Set up hooks"). The commit-msg hook checks the closing commit;
# this also catches a line written back later, or a commit the hook never saw. Git's own
# trailer parser reads the history (%(trailers:key=...,unfold), git 2.22 or later). A
# mention is the id as a whole token in any case: closing K3 does not match K3b or K3-a, and
# "Done: k3" closes K3 (it once passed while STATE.md named K3). No repository,
# or no commit yet: nothing has been closed, and nothing is checked. A shallow clone holds
# part of the history: a NOTE says so, and the part it holds is checked.
# Colour-free whatever the user's config says (color.ui or color.diff = always): the gate parses
# what these helpers print, and an escape code before "-" hid a deleted line (b7 review, round 1).
nocolor="-c color.ui=never -c color.diff=never"
hgit() {
  # shellcheck disable=SC2086 # nocolor holds two -c options: split on purpose
  git $nocolor "$@"
}
if hgit rev-parse -q --verify HEAD >/dev/null 2>&1; then
  [ "$(hgit rev-parse --is-shallow-repository)" != true ] ||
    echo "NOTE [state]: a shallow clone; only the Done: trailers of the commits it holds are checked."
  # One grammar with the hook: git matches the key in any case and unfolds a folded value,
  # and the value, trimmed, is exactly one id. A value that is not one (the hook bypassed, or
  # older than it) closes nothing, and a NOTE names it; every well-formed one still counts.
  if hgit log --format='@%h%n%(trailers:key=Done,unfold)' HEAD > "$work/done-trailers" &&
     awk -v out="$work/done-ids" '
       /^@/ { commit = substr($0, 2); print > out; next }
       /./ { id = $0; sub(/^[^:]*:[ \t]*/, "", id); sub(/[ \t]+$/, "", id)
             if (id ~ /^[A-Za-z][A-Za-z0-9]*(-[A-Za-z0-9]+)?$/ && id ~ /[0-9]/) print id > out
             else printf "NOTE [state]: commit %s has \"Done: %s\", which is not one task id; it closes nothing.\n", commit, id }
       END { close(out) }' "$work/done-trailers"; then
    for f in docs/STATE.md docs/BACKLOG.md docs/STRONG_REVIEW.md docs/reviews/strong-*.md docs/audits/*.md; do
      level=FAIL
      case "$f" in docs/audits/*.md) level=NOTE ;; esac
      [ ! -f "$f" ] || awk -v closed="$work/done-ids" -v level="$level" '
        FILENAME == closed {
          if (sub(/^@/, "")) commit = $0
          else if (!(tolower($0) in by)) { by[tolower($0)] = commit; as[tolower($0)] = $0 }
          next
        }
        { n = split($0, word, /[^A-Za-z0-9_-]+/)
          for (i = 1; i <= n; i++) if ((key = tolower(word[i])) in by) {
            printf "%s [state]: %s:%d names %s, which commit %s closed (Done: %s).\n", level, FILENAME, FNR, word[i], by[key], as[key]
            found = 1
          } }
        END { if (found) print "              Delete the line (the history is in git); a task needed again gets a new id."
              exit (found && level == "FAIL") }' "$work/done-ids" "$f" || fail=1
    done
  else
    echo "FAIL [state]: git log could not list the Done: trailers, so finished tasks were not checked."
    fail=1
  fi
fi

# A [LESSON] or [GOTCHA] line in docs/STATE.md may not be deleted until it has a
# permanent home (docs/AGENTS.md). Written only, the rule held nowhere: a commit that deletes
# such a line from STATE.md and adds no line to any other file is told so, never failed, since
# the home may be a later commit (owner decision 2026-10-15, KARARLAR D05 inv1#76, lead
# decision 7; RL 2026-10-03: a rule without a mechanism did not hold). Only the commit hook's
# run (--for-commit) has a commit to read: the staged diff against HEAD.
if [ -n "$for_commit" ]; then
  dropped=$(hgit diff --cached --no-renames --no-ext-diff -U0 HEAD -- docs/STATE.md 2>/dev/null |
            grep -v '^--- ' | grep -E '^-.*\[(LESSON|GOTCHA)\]')
  if [ -n "$dropped" ] &&
     ! hgit diff --cached --no-renames --no-ext-diff -U0 HEAD -- . ':(exclude)docs/STATE.md' 2>/dev/null |
       grep -v '^+++ ' | grep -q '^+.'; then
    echo "NOTE [state]: this commit deletes a tagged line from docs/STATE.md and adds nothing to any other"
    echo "             file. A [LESSON] or [GOTCHA] line keeps until it has a permanent home (docs/AGENTS.md):"
    printf '%s\n' "$dropped" | sed 's/^-/               /' | head -10
  fi
fi

# The strong review cycle runs at least every STRONG_REVIEW_DAYS days or after
# STRONG_REVIEW_TASKS closed tasks, whichever comes first, and its reminder must not depend on
# anyone remembering it (docs/WORKFLOW.md, "The strong review cycle"). Both are owner choices,
# not a measured cadence: 10 days is the owner's request (v0.10, issue #61), 20 tasks the
# figure already proposed for the audit (KARARLAR B11 inv1#119, inv2#152). A project that keeps
# docs/STRONG_REVIEW.md is told, never failed, when either is reached. The date is the commit
# that added the newest docs/reviews/strong-*.md, so a report deleted once its last item closed
# still counts; the tasks are the Done: trailers of the commits after it. A shallow clone may
# not hold it. The two values are set near the top.
strong_list=docs/STRONG_REVIEW.md
strong_rule="at least every $STRONG_REVIEW_DAYS days or after $STRONG_REVIEW_TASKS closed tasks, whichever comes first"
if [ -f "$strong_list" ] && hgit rev-parse -q --verify HEAD >/dev/null 2>&1; then
  # No wildcard pathspec (GIT_LITERAL_PATHSPECS would turn it off), no rename detection (a
  # new report beside a deleted one reads as a rename), no signature text in the output.
  added=$(hgit -c core.quotePath=false log --no-renames --no-show-signature --diff-filter=A \
            --format='@%ct %H' --name-only HEAD -- docs/reviews 2>/dev/null |
          awk '/^@/ { t = substr($0, 2); next } /^docs\/reviews\/strong-[^\/]*\.md$/ { print t; exit }')
  if [ -z "$added" ]; then
    echo "NOTE [strong-review]: no strong review report yet (docs/reviews/strong-*.md); the cycle runs"
    printf '%s\n' "                      $strong_rule (docs/WORKFLOW.md, \"The strong review cycle\")."
  else
    added_commit=${added#* }; added=${added%% *}
    # The ids the state parser above accepted (done-ids), of the commits after the report: a
    # malformed Done: value closes nothing there, so it is no closed task here (b7 review, round 1).
    hgit log --no-show-signature --format=%h "$added_commit..HEAD" > "$work/strong-range" 2>/dev/null
    closed=$(awk -v range="$work/strong-range" '
      FILENAME == range { keep[$0]; next }
      /^@/ { on = substr($0, 2) in keep; next }
      on { n++ }
      END { print n + 0 }' "$work/strong-range" "$work/done-ids" 2>/dev/null)
    closed=${closed:-0}
    days=$(( ($(date +%s) - added) / 86400 ))
    if [ $(( $(date +%s) - added )) -gt $(( STRONG_REVIEW_DAYS * 86400 )) ] || [ "$closed" -ge "$STRONG_REVIEW_TASKS" ]; then
      printf '%s\n' "NOTE [strong-review]: the newest strong review report was added $days days ago, and $closed tasks"
      printf '%s\n' "                      closed since; the cycle is due: it runs $strong_rule"
      echo "                      (docs/WORKFLOW.md, \"The strong review cycle\")."
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 2b) PROJECT.md navigability
# ---------------------------------------------------------------------------
# docs/PROJECT.md grows for the life of the project, so it is NOT in the session reading
# order — agents read the section they need through its Contents and cite it by number.
# That only works while the Contents is complete, and a table of contents nobody maintains
# is worse than none: it stops being navigation and becomes a false claim about the file's
# shape, which is exactly when someone gives up and loads the whole file instead.
#
# So this is mechanical rather than a rule in prose: every "## N." heading must appear in
# the Contents section. A file with no numbered sections yet is fine — that is a young
# project, not a broken one.
if [ ! -f docs/PROJECT.md ]; then
  echo "FAIL [project]: docs/PROJECT.md does not exist. It is where permanent decisions live;"
  echo "                without it they end up in docs/STATE.md and are pruned away."
  fail=1
elif ! grep -q "^## Contents" docs/PROJECT.md; then
  echo "FAIL [project]: docs/PROJECT.md has no '## Contents' section, so it cannot be read"
  echo "                selectively and every reader will load the whole file."
  fail=1
else
  # Headings first, then the Contents block, then the set difference. Compared on the
  # heading TEXT rather than on a link target, because the text is what a human maintains.
  # Entries are normalised to bare heading text — list marker, link syntax and trailing
  # space removed — so that a Contents written as "- 1. Money" or "- [1. Money](#money)"
  # both compare equal to the heading "## 1. Money".
  awk '/^## Contents/{f=1;next} /^## /{f=0} f' docs/PROJECT.md \
    | sed -e 's/^[[:space:]]*[-*][[:space:]]*//' \
          -e 's/^\[//' -e 's/\](#[^)]*)[[:space:]]*$//' \
          -e 's/[[:space:]]*$//' > "$work/toc"
  missing=""
  sed -n 's/^## \([0-9][0-9.]*\.\{0,1\}[[:space:]].*\)$/\1/p' docs/PROJECT.md > "$work/heads"
  while IFS= read -r h; do
    [ -n "$h" ] || continue
    # -x anchors to the WHOLE line and -F takes the pattern literally. Without -x this was a
    # substring test, and "1. Money" matched inside the Contents entry "11. Money" — so an
    # unlisted section 1 passed the gate while the gate was reporting on section 11.
    grep -qxF -- "$h" "$work/toc" || missing="$missing
  - $h"
  done < "$work/heads"
  if [ -n "$missing" ]; then
    printf '%s\n' "FAIL [project]: docs/PROJECT.md has numbered sections missing from its Contents:$missing"
    echo "                Add them, or renumber. Citations elsewhere point at these numbers."
    fail=1
  fi
fi

# ---------------------------------------------------------------------------
# 2c) ARCHITECTURE.md names every module folder
# ---------------------------------------------------------------------------
# The map is coarse and an agent finds code by searching, but a module the map does not name
# is one an agent may rebuild beside it ("NEVER rewrite a system you could not find"). Prefer
# a check to a promise (KARARLAR B10 inv1#239): every direct subfolder of a module root that
# holds a file in the scan list must be named, as a whole entry, in the "## Module map" section
# of docs/ARCHITECTURE.md. module_roots is a VALUE: the folders whose subfolders are modules,
# space-separated, e.g. "src packages". Empty, nothing is checked and a NOTE says so: a
# single-module project has no module folders. A root with no file at all FAILS: a check over a
# missing folder finds nothing, which looks like a clean result.
module_roots=""
architecture_file=docs/ARCHITECTURE.md
if [ -z "$module_roots" ]; then
  echo "NOTE [architecture]: module_roots is empty in scripts/check.sh; no module folder is checked against"
  echo "                     the module map in docs/ARCHITECTURE.md."
elif ! grep -q '^## Module map' "$architecture_file" 2>/dev/null; then
  printf '%s\n' "FAIL [architecture]: $architecture_file has no '## Module map' section, so module_roots cannot be checked."
  fail=1
else
  # Split Markdown table cells, code spans and list-entry colons; keep dots and hyphens
  # inside names. grep -w would count api-gateway as naming api, or core.utils as core.
  awk '/^## Module map/ { f = 1; next } /^## / { f = 0 }
       f { gsub(/[`|:]/, " "); for (i = 1; i <= NF; i++) print $i }' "$architecture_file" > "$work/module-map"
  for root in $module_roots; do
    case "$root" in .) prefix="" ;; *) prefix="${root%/}/" ;; esac
    tr '\0' '\n' < "$filelist" | awk -v p="$prefix" '
      index($0, p) == 1 { rest = substr($0, length(p) + 1); j = index(rest, "/"); found = 1
                          if (j > 1) print substr(rest, 1, j - 1) }
      END { exit !found }' > "$work/modules" || {
      printf '%s\n' "FAIL [architecture]: the module root $root in scripts/check.sh holds no file the gate sees."
      fail=1; continue; }
    sort -u "$work/modules" | while IFS= read -r module; do
      grep -qxF -- "$module" "$work/module-map" || {
        printf '%s\n' "FAIL [architecture]: $prefix$module is a module folder that the '## Module map' of $architecture_file does not name."
        echo "                     Add its line in the same task (one line: module, responsibility)."
        : > "$work/module-unnamed"; }
    done
  done
  # The loop above runs in a pipeline's subshell: a file carries its verdict out.
  [ ! -e "$work/module-unnamed" ] || fail=1
fi

# ---------------------------------------------------------------------------
# 2d) ShellCheck
# ---------------------------------------------------------------------------
# Two classes a static rule sees left the review's attack list for this step
# (docs/REVIEW_GATE.md): SC2028, echo with a backslash, and SC2086, an unquoted expansion.
# ShellCheck's errors fail too; its other warnings stay a reviewer's. A deliberate word split
# carries `# shellcheck disable=SC2086` and its reason on the line above. Without shellcheck the
# step is NOT RUN, as the kit's own check is (KARARLAR D04 inv2#26; shellcheck.net/wiki/SC2086).
select_shellcheck_files() {
  while IFS= read -r f; do
    case "$f" in
      *.sh) printf '%s\n' "$f" ;;
      .githooks/*)
        # ShellCheck supports sh/bash/dash/ksh; other hook languages stay out (SC1071).
        [ -f "$f" ] && [ ! -L "$f" ] && head -n 1 "$f" | grep -Eq '^#!.*[/ ](sh|bash|dash|ksh)([[:space:]]|$)' && printf '%s\n' "$f" ;;
    esac
  done
}
if ! command -v shellcheck >/dev/null 2>&1; then
  echo "NOT RUN [shellcheck]: shellcheck is not installed; SC2028, SC2086 and its errors are left to review."
else
  shell_files=$(tr '\0' '\n' < "$filelist" | select_shellcheck_files)
  sc_status=0
  if [ -n "$shell_files" ]; then
    # Newline-separated names are safe: the gate refuses names holding newlines (#41).
    ( IFS='
'; set -f; set --
      for f in $shell_files; do [ -f "$f" ] && set -- "$@" "$f"; done
      [ "$#" -eq 0 ] || SHELLCHECK_OPTS= shellcheck --norc -e SC2148 -f gcc -- "$@" ) > "$work/shellcheck" 2>&1 || sc_status=$?
  fi
  if [ "$sc_status" -gt 1 ]; then
    printf '%s\n' "FAIL [shellcheck]: shellcheck could not check the shell scripts (exit $sc_status):"
    sed 's/^/  /' "$work/shellcheck"
    fail=1
  elif grep -E ': error:|\[SC(2028|2086)\]$' "$work/shellcheck" > "$work/shellcheck-refused" 2>/dev/null; then
    echo "FAIL [shellcheck]: an error, an echo with a backslash (SC2028) or an unquoted expansion (SC2086):"
    sed 's/^/  /' "$work/shellcheck-refused"
    fail=1
  fi
fi

# ---------------------------------------------------------------------------
# 3) PROJECT BOUNDARY CHECKS
# ---------------------------------------------------------------------------
# The checks live in their OWN FILE, sourced here, and that is deliberate. An earlier
# version had a commented-out placeholder line to be replaced in place — and the first
# person to fill it left the leading "#" on the first line, so the whole check sat inside a
# comment and the gate silently enforced nothing. When the unit of replacement is a whole
# file, that mistake is not available.
#
# A MISSING file is a FAIL. It used to be skipped, which meant deleting one file removed
# every boundary check without a word.
if [ -f scripts/boundary_checks.sh ]; then
  . ./scripts/boundary_checks.sh
else
  echo "FAIL [boundary]: scripts/boundary_checks.sh is missing. Boundary enforcement is not"
  echo "                 optional; if this project genuinely has no enforceable boundary,"
  echo "                 say so IN that file rather than deleting it."
  fail=1
fi

# ---------------------------------------------------------------------------
# 4) Build & tests
# ---------------------------------------------------------------------------
# An unconfigured command is a FAIL, not a warning. "No build or test command" is the
# absent-evidence case: the gate would be reporting that nothing failed, having run nothing.
#
# Keep deploy-shaped steps out of this command, dry runs included. An agent's permission
# layer refused to run a gate whose command ended in a deploy tool's --dry-run, read as a
# production deploy, so the agent could not run the gate it is required to run. Validate
# deploy configuration in its own CI step, or document an allow rule for that exact command.
build_test_cmd="{{BUILD_TEST_COMMAND}}"
# A commit that changes only documentation skips the build/test command, and nothing else:
# every scan and check above has run. A project's gate built for minutes on every such commit.
# 1: on. 0: off, for a project whose build reads markdown (a documentation site, doc tests).
docs_only_skip_build=1
# BUILD CACHE. One change ran the same build three or four times on the same files: the
# worker, the Stop hook, the commit hook, the merge hook (#82). A build that passed is recorded
# under a key, and a later run whose key matches skips the build and says so in its PASS line;
# every other check above still runs. The key is a SHA-256 over every path
# `git ls-files --cached --others --exclude-standard` names (path, content and executable bit
# read from disk, symlink text: uncommitted edits, a new untracked file, CMakeLists, tests and
# documents all count, not only what a check scans), this gate script itself, the build
# command, the caller's LC_ALL and the output of build_cache_inputs. An entry another version
# of the gate wrote is deleted. build_cache_inputs is a VALUE: a command that prints whatever
# else the build depends on, which the tree does not hold. Starters, keep the ones your build
# uses (a missing tool fails the command, and a failing command means no cache):
#   cmake --version; ninja --version
#   cl 2>&1 | head -n 1                     # the MSVC banner (compiler version)
#   python --version; python -m pip freeze | sha256sum
#   blender --version
#   git lfs ls-files -l                     # LFS objects by id
#   echo "CC=$CC CXX=$CXX"                  # environment the build reads
# Unity: ProjectSettings/ProjectVersion.txt and Packages/packages-lock.json are tracked, so
# already in the key; Library/ is a cache Unity rebuilds and stays out.
# Ignored files (fetched dependencies, a build folder) and environment variables are NOT in the
# key unless this command prints them. Empty, there is no cache: an input nobody fingerprinted
# would otherwise pass on a stale result. Use "true" for a build that reads nothing but the
# tree. The cache is never read on CI, nor when the
# command fails, the tree holds a submodule, a nested repository or a symlink to a folder (its
# files are not hashed), outside Git, or with GATE_CACHE=off. A cached run prints
# "NOTE [build]: not run: cached PASS <key> from <date>" and its PASS line says so too, so a
# report can never claim a build that did not run. Entries sit in the repository's common git
# folder (shared by its worktrees: the key names content, not a checkout) and expire after
# cache_days days.
build_cache_inputs=""
cache_days=7
cache_dir="" cache_record=""
if [ -n "${CI:-}" ] || [ "${GATE_CACHE:-}" = off ]; then
  :
else
  case "$lock_path" in
    */.check.lock) ;;
    *) cache_common=$(git rev-parse --git-common-dir 2>/dev/null) && cache_dir="$cache_common/check-cache" ;;
  esac
fi
[ -n "$build_cache_inputs" ] && [ ! -e "$work/scan_unhashed" ] || cache_dir=""
# build_cache_key: prints "hit <key> <date>" when cache_dir holds an entry for the key younger
# than cache_days, else "miss <key> -", and deletes the older entries and those another gate
# version wrote (an entry holds its gate's hash); fails when an input cannot be read. Python, not find(1): on native Windows a PATH can name Windows' own FIND.EXE first.
build_cache_key() {
  inputs=$( ( if [ -n "$caller_lc_all_set" ]; then LC_ALL=$caller_lc_all; else unset LC_ALL; fi
              exec sh -c "$build_cache_inputs" ) 2>&1 ) || {
    printf '%s\n' "NOTE [build]: build_cache_inputs failed, so the build is not cached: $build_cache_inputs" >&2; return 1; }
  printf '%s\0%s\0%s' "$build_test_cmd" "${caller_lc_all_set:+set:$caller_lc_all}" "$inputs" |
    python3 -I -c '
import hashlib, os, sys, time
gate = hashlib.sha256(open(sys.argv[5], "rb").read()).hexdigest()
key = hashlib.sha256(b"keel build cache 2\0" + gate.encode() + b"\0" + sys.stdin.buffer.read() + b"\0")
for path in sorted(p for p in open(sys.argv[1], "rb").read().split(b"\0") if p):
    content = hashlib.sha256()
    with open(os.fsdecode(path), "rb") as data:
        for chunk in iter(lambda: data.read(1 << 20), b""):
            content.update(chunk)
    executable = b"x" if os.stat(os.fsdecode(path)).st_mode & 0o111 else b"-"
    key.update(path + b"\0" + executable + content.digest())
if os.path.exists(sys.argv[2]):
    key.update(b"symlinks\0" + open(sys.argv[2], "rb").read())
key, found, now = key.hexdigest(), "miss -", time.time()
if os.path.isdir(sys.argv[3]):
    for name in os.listdir(sys.argv[3]):
        entry = os.path.join(sys.argv[3], name)
        try:  # a gate in another worktree may delete it first
            mtime = os.stat(entry).st_mtime
            if now - mtime > float(sys.argv[4]) * 86400 or open(entry).read().strip() != gate:
                os.remove(entry)
            elif name == key:
                found = "hit " + time.strftime("%Y-%m-%dT%H:%M", time.localtime(mtime))
        except (OSError, UnicodeDecodeError):
            pass
print(found.split()[0], key, found.split()[1])
' "$filelist" "$work/symlink-text" "$cache_dir" "$cache_days" "$0"
}
# Tested with its whitespace stripped: an all-blank command reaches `sh -c` as a no-op that
# exits 0, which is a green gate with no build — the unconfigured case wearing spaces.
case "$(printf '%s' "$build_test_cmd" | tr -d '[:space:]')" in
  *"{{"*|"")
    echo "FAIL [build]: no build/test command is configured in scripts/check.sh. Set one —"
    echo "              use 'true' explicitly if this project genuinely has nothing to run,"
    echo "              so that the choice is visible in the diff instead of implied."
    fail=1 ;;
  *)
    # The path is taken only when .githooks/pre-commit asks (--for-commit) and the INDEX shows
    # a documentation-only change; the caller cannot declare one. Documentation-only: at least
    # one change against HEAD, renames off (a code file renamed to .md is a deletion of code),
    # every path ending in .md, and each added, modified or deleted entry a regular file
    # (mode 100644 or 100755: a symlink or a submodule is not documentation). Submodules are
    # never ignored here: diff.ignoreSubmodules=all, or a submodule's own `ignore = all`, hid a
    # staged submodule revision, and the document beside it skipped the build. Any doubt runs
    # the build: no HEAD yet, a merge in progress, a git error, an entry that does not parse.
    # The diff is against HEAD, which for an amend is the tree being amended: the build last
    # vouched for HEAD, and the commit differs from it only by these documents. A clean
    # `git merge` never comes here: pre-merge-commit asks for the full gate.
    docs_only=""
    if [ -n "$for_commit" ] && [ "$docs_only_skip_build" = 1 ]; then
      docs_only=$(python3 -c '
import subprocess, sys
def git(*args):
    return subprocess.run(("git",) + args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
if git("rev-parse", "-q", "--verify", "HEAD").returncode != 0:
    sys.exit(1)
if git("rev-parse", "-q", "--verify", "MERGE_HEAD").returncode != 1:
    sys.exit(1)
diff = git("diff", "--cached", "--raw", "--no-renames", "--ignore-submodules=none", "-z", "HEAD", "--")
fields = diff.stdout.split(b"\0")
if diff.returncode != 0 or fields.pop() != b"" or not fields or len(fields) % 2:
    sys.exit(1)
regular = (b"100644", b"100755")
for meta, path in zip(fields[0::2], fields[1::2]):
    parts = meta.split(b" ")
    if len(parts) != 5 or parts[0][:1] != b":" or not path.endswith(b".md"):
        sys.exit(1)
    old, new, status = parts[0][1:], parts[1], parts[4]
    if not ((status == b"A" and new in regular) or (status == b"D" and old in regular) or
            (status == b"M" and old in regular and new in regular)):
        sys.exit(1)
print(len(fields) // 2)
' 2>/dev/null) || docs_only=""
      case "$docs_only" in ""|0|*[!0-9]*) docs_only="" ;; esac
    fi
    if [ -n "$docs_only" ]; then
      if [ "$docs_only" = 1 ]; then unit=file; else unit=files; fi
      pass_note=" (build not run: documentation-only commit, $docs_only $unit)"
      printf '%s\n' "NOTE [build]: not run: every path this commit changes is documentation ($docs_only $unit)."
    else
      # Quiet when it passes; on failure the summary line, then the TAIL, never a filter. The
      # lines that locate a compile error ("In function", "required from", "note:") do not
      # match "error", and a gate that printed only matching lines sent a CI-only failure out
      # with its location cut away. The whole output stays in $build_log for a local run. On CI
      # that file vanishes with the runner and the first error of a long chain sits above any
      # tail, so CI prints the whole log.
      # ponytail: a fixed tail; raise build_tail if your diagnostic chains run longer.
      # 150 lines: about the 10000 characters a tool result shows whole; Claude Code cuts a Bash
      # result at 30000 characters (BASH_MAX_OUTPUT_LENGTH, code.claude.com/docs/en/settings).
      build_tail=150
      cache_key=""
      [ -z "$cache_dir" ] || cache_key=$(build_cache_key) || cache_key=""
      cache_found=${cache_key%% *} cache_key=${cache_key#* } cache_date=${cache_key#* } cache_key=${cache_key%% *}
      if [ "$cache_found" = hit ]; then
        cache_short=$(printf '%.12s' "$cache_key")
        pass_note=" (build not run: cached PASS $cache_short from $cache_date)"
        printf '%s\n' "NOTE [build]: not run: cached PASS $cache_short from $cache_date (same files, gate and build inputs)."
        echo "             GATE_CACHE=off runs it anyway."
        rc=0
      else
        ( if [ -n "$caller_lc_all_set" ]; then LC_ALL=$caller_lc_all; else unset LC_ALL; fi
          exec sh -c "$build_test_cmd" ) > "$build_log" 2>&1
        rc=$?
        # Recorded only if the files are the same after the build as before it: an edit made
        # while it ran would otherwise be recorded as built.
        # Recorded only when the key computed again after the build equals the one before it.
        cache_after=""
        [ "$rc" -ne 0 ] || [ -z "$cache_key" ] || cache_after=$(build_cache_key) || cache_after=""
        cache_after=${cache_after#* }
        if [ -n "$cache_key" ] && [ "${cache_after%% *}" = "$cache_key" ]; then
          cache_record=$cache_key
        fi
      fi
      if [ "$rc" -ne 0 ] && [ -n "${CI:-}" ]; then
        printf '%s\n' "FAIL [build]: the build/test command exited $rc. Its whole output follows (CI)."
        cat "$build_log"
        fail=1
      elif [ "$rc" -ne 0 ]; then
        printf '%s\n' "FAIL [build]: the build/test command exited $rc. Its last $build_tail lines follow;"
        printf '%s\n' "              the whole output is in $build_log"
        tail -n "$build_tail" "$build_log"
        fail=1
      fi
    fi ;;
esac

# ---------------------------------------------------------------------------
# 5) Scanner integrity — LAST, so it covers every scan above, including the project's own
# boundary checks. The flag file is the one failure signal that survives a command
# substitution (see scan_grep); checking it here is what makes `$(scan_grep …)` safe to
# write in boundary_checks.sh.
# ---------------------------------------------------------------------------
if [ -e "$work/scan_failed" ]; then
  echo "FAIL [scan]: a scanner failed to run somewhere above. Any clean result it appeared"
  echo "             to produce is void — a scan that did not happen finds nothing."
  fail=1
fi

if [ "$fail" -ne 0 ]; then echo "CHECK: FAIL"; exit 1; fi
# The build cache (section 4) records a build only for a run that passed. A record that cannot be
# written costs the next run its build, nothing else.
if [ -n "$cache_record" ]; then
  { mkdir -p "$cache_dir" &&
    python3 -I -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$0" \
      > "$cache_dir/$cache_record"; } 2>/dev/null || :
fi
printf '%s\n' "CHECK: PASS${pass_note:-}"
