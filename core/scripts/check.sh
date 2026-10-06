#!/usr/bin/env sh
# {{PROJECT_NAME}} quality gate — EVERY agent runs this before finishing a task.
# CI runs the SAME script. There is one definition of "green" in this repository, and it is
# here — which is NOT the same as a promise that local and CI always agree. Same script,
# different machine: file modes, installed tools and locale can all differ (docs/GOTCHAS.md
# has the exit-126 case that kept a pipeline red for weeks). Check the pipeline after
# pushing; do not infer it from a local pass.
#
# Usage: check.sh [--self-test | --for-commit]
#   default       run the gates
#   --self-test   prove the gates actually go RED (the block near the bottom)
#   --for-commit  what .githooks/pre-commit runs: the gates, without the build when the
#                 staged change is documentation only (section 4 decides; the flag only asks)
#
# ADDING A GATE: add the check, AND add a case to self_test(). A gate without a negative
# test has not been proven to fail — it has only been seen passing, which is not the same
# thing and never was. A gate that reads an override for its case adds that variable to the
# SELF-TEST SEAMS list below, or an exported copy of it turns the gate green in a normal run.
#
# EXIT CODES: 0 pass, 1 fail, 2 usage, 75 NOT RUN — another gate run held this checkout's
# lock for longer than GATE_LOCK_WAIT=<seconds> allowed (unset: wait without limit, which is
# what manual, CI and commit-hook runs want; the Stop hook sets about 500 so it answers
# before its own timeout kills it). A caller reports 75 as "gate did not run", never as a
# pass and never as a gate failure.
#
# A SELF-TEST CASE NEVER CHANGES A TRACKED FILE, and writes nothing else inside the working
# tree when it can avoid it. Point the gate at a synthetic file outside the tree through an
# self-test seam (GATE_SELFTEST_STATE_FILE, GATE_SELFTEST_EXTRA_FILE below; honoured only in the self-test's
# own nested runs, so the case passes it to expect_fail or expect_pass), or run the case against
# a disposable copy of the tree. A file injected into the tree is seen by a concurrent
# `git add -A` and by another session's edits, and a killed self-test leaves it behind. The
# gate lock below keeps other gate runs from seeing it; nothing else does. A case that must
# place a file where the project's own globs find it removes it, interrupted or not
# (scripts/boundary_selftests.sh shows how).
#
# EVERY CHECK BELOW MUST FAIL ON ABSENT EVIDENCE. A missing input file, a scanner that could
# not run, a command that was never configured: all FAIL. Silence is not success. Five
# separate paths in an earlier version of this script violated that rule and reported PASS
# while enforcing nothing; a cross-model review found them.
set -u
# Windows installs Python as `python` or `py`: when `python3` is absent, use the first of
# those that is Python 3.10 or newer, under the name the scripts call.
command -v python3 >/dev/null 2>&1 || python3() {
  if command -v python >/dev/null 2>&1; then python "$@"; else py -3 "$@"; fi
}
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

# SELF-TEST SEAMS are honoured ONLY in the self-test's own nested runs. Each one exists so a
# case can point a gate at a synthetic input, which means each one can also turn a gate green
# without its work: GATE_BUILD_CMD_OVERRIDE=true skips the build, GATE_SELFTEST_STATE_FILE reads another
# file, GATE_SELFTEST_HISTORY another repository's history, GATE_SELFTEST_COMMIT_REPO another
# repository's index for the documentation-only commit (section 4). The commit hook inherits the committer's environment, so a variable left exported in
# a profile or a CI step, or typed by an agent facing a red build, did exactly that. A run
# that finds one without the self-test's marker FAILS and names it; it does not unset it and
# carry on, because then the run that someone believed was overridden reports on something
# else. The marker is the lock holder's pid, which the holder writes into this checkout's lock
# file and clears when it exits; it is exported only by self_test(), and is believed only
# while the lock file names it AND this run inherited the lock itself (below). A gate killed
# with SIGKILL never clears its pid, so variables copied out of it named the lock file's pid
# exactly and an override passed without its build; a copied variable carries no descriptor.
# It stops an accidental export, not a deliberate forgery by someone who holds the lock.
# A NEW SEAM JOINS THIS LIST.
# GATE_LOCK_WAIT, GATE_LOCK_HELD and GATE_LOCK_FD are not seams: they change when a run
# starts, not what it checks.
lock_path=$(git rev-parse --git-path check.lock 2>/dev/null) || lock_path=.check.lock
case "$lock_path" in /*) ;; *) lock_path="$(pwd -P)/$lock_path" ;; esac
# A run that claims the lock (GATE_LOCK_HELD names this checkout's) proves it: the descriptor
# GATE_LOCK_FD it inherited is open on this lock file, the lock is held, so a fresh open of
# the file cannot take it, and that descriptor itself holds it: flock on it succeeds at once
# only on the open file description already holding the lock. A descriptor opened on the same
# file independently, while another gate holds it, would block. Otherwise it FAILS by name;
# it never skips the lock on a claim. The independent descriptor is open for writing: Linux's
# NFS client refuses an exclusive flock on a read-only one, and every fresh run failed here.
# A flock error other than "would block" is the file system, not the claim: FAIL [lock].
inherited=""
if [ "${GATE_LOCK_HELD:-}" = "$lock_path" ]; then
  lock_probe=0
  python3 -c '
import os, sys
try:
    import fcntl
except ImportError:
    print("FAIL [lock]: python3 has no fcntl module, which the gate lock needs; native Windows Python lacks it. Run the gate with a POSIX python3 (WSL, MSYS2, Cygwin).")
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
if [ -z "$inherited" ] || [ -z "${GATE_SELFTEST_NESTED:-}" ] ||
   [ "$(cat "$lock_path" 2>/dev/null)" != "$GATE_SELFTEST_NESTED" ]; then
  for seam in GATE_BUILD_CMD_OVERRIDE GATE_SELFTEST_STATE_FILE GATE_SELFTEST_PROJECT_FILE BOUNDARY_CHECKS_FILE \
              BOUNDARY_SELFTESTS_FILE GATE_SELFTEST_EXTRA_FILE GATE_SELFTEST_BREAK_SCANNER \
              GATE_SELFTEST_HISTORY GATE_SELFTEST_COMMIT_REPO; do
    eval "seam_value=\${$seam:-}"
    [ -z "$seam_value" ] || { echo "FAIL [env]: $seam is set; self-test overrides are not honoured outside --self-test"; fail=1; }
  done
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
# (docs/GOTCHAS.md); the waiting NOTE says how to find the holder. The lock needs Python's
# fcntl, which native Windows Python lacks: that is FAIL [lock] by name, not a traceback.
# The self-test holds the lock for its whole run, so no other gate sees a case mid-injection.
# Nested runs (the self-test's own `sh "$0"`, the commit hook it calls) inherit the lock:
# GATE_LOCK_HELD names the lock path, so a gate in another checkout started from the build
# command still takes its own lock, and GATE_LOCK_FD names the inherited descriptor, which
# the seam block checks before it believes the claim. The holder writes its pid, which after
# the exec is the gate's, into the lock file for the self-test marker (the seam block).
case "${GATE_LOCK_WAIT:-}" in
  *[!0-9]*) printf '%s\n' "FAIL [lock]: GATE_LOCK_WAIT must be a number of seconds, got '$GATE_LOCK_WAIT'."; exit 1 ;;
esac
if [ -z "$inherited" ]; then
  command -v python3 >/dev/null 2>&1 ||
    { echo "FAIL [lock]: python3 is not on PATH, and the gate lock is taken through it."; exit 1; }
  # Python ignores SIGPIPE and SIGXFSZ and catches SIGINT; the wait and the gate get back
  # what sh would have given them.
  # O_NOFOLLOW: a symlink here (the older lock's, left by a killed run) is refused by name.
  exec python3 -c '
import os, signal, sys, time
try:
    import fcntl
except ImportError:
    print("FAIL [lock]: python3 has no fcntl module, which the gate lock needs; native Windows Python lacks it. Run the gate with a POSIX python3 (WSL, MSYS2, Cygwin).", flush=True)
    sys.exit(1)
path, gate, wait, waited = sys.argv[1], sys.argv[2], os.environ.get("GATE_LOCK_WAIT", ""), 0
if signal.getsignal(signal.SIGINT) is signal.default_int_handler:
    signal.signal(signal.SIGINT, signal.SIG_DFL)
signal.signal(signal.SIGPIPE, signal.SIG_DFL)
signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
try:
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644)
except OSError as error:
    print("FAIL [lock]: cannot open %s as the gate lock (%s); if it is a symlink or a directory, delete it." % (path, error.strerror), flush=True)
    sys.exit(1)
while True:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        break
    except BlockingIOError:
        pass
    except OSError as error:
        print("FAIL [lock]: this file system does not support the gate lock (%s); the lock file is %s." % (error.strerror or error, path), flush=True)
        sys.exit(1)
    if wait and waited >= int(wait):
        print("NOT RUN [lock]: another gate run, or a process it started, has held %s for %ds; GATE_LOCK_WAIT=%s ran out." % (path, waited, wait), flush=True)
        sys.exit(75)
    if waited % 30 == 0:
        print("NOTE [lock]: another gate run, or a process it started, has held %s for %ds; waiting for it." % (path, waited), flush=True)
        if waited == 0:
            print("             To see the holder: fuser -v %s, or lsof %s. A server the build left running (a compiler\n"
                  "             server, a build daemon) holds it until that server exits: docs/GOTCHAS.md." % (path, path), flush=True)
    time.sleep(1)
    waited += 1
os.ftruncate(fd, 0)
os.write(fd, str(os.getpid()).encode())
# A copy that survives exec, above the fds sh scripts redirect; nested runs prove they hold it.
os.environ["GATE_LOCK_FD"] = str(fcntl.fcntl(fd, fcntl.F_DUPFD, 10))
os.environ["GATE_LOCK_HELD"] = path
os.execvp("sh", ["sh", gate] + sys.argv[3:])
' "$lock_path" "$gate" "$@"
fi

# Overridable so the self-test can point the state checks at a synthetic file, and at a
# history of its own (GATE_SELFTEST_HISTORY, section 2), instead of mutating the real ones.
# Only the self-test sets them (the seam block above).
GATE_SELFTEST_STATE_FILE="${GATE_SELFTEST_STATE_FILE:-docs/STATE.md}"

# Overridable so the self-test can prove these branches without mutating the repository.
# Only the self-test sets them (the seam block above).
BOUNDARY_CHECKS_FILE="${BOUNDARY_CHECKS_FILE:-scripts/boundary_checks.sh}"
BOUNDARY_SELFTESTS_FILE="${BOUNDARY_SELFTESTS_FILE:-scripts/boundary_selftests.sh}"

work=$(mktemp -d) || { echo "FAIL [gate]: cannot create a temp dir; refusing to run blind."; exit 1; }
# The run that took the lock clears the pid it wrote there, so the self-test marker ends with
# it (the seam block). The file itself stays: removing a flock file lets a waiter lock the
# removed file while the next run creates and locks a new one, and both run.
cleanup() {
  rm -rf "$work"
  [ "$(cat "$lock_path" 2>/dev/null)" != "$$" ] || : > "$lock_path"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
filelist="$work/files"

# lock_path is computed in the seam block above. The build/test command's full output goes
# beside the lock: outside the tree, one per checkout. Without git it goes to a temp file.
case "$lock_path" in
  */.check.lock) build_log=$(mktemp) || { echo "FAIL [gate]: cannot create a temp file; refusing to run blind."; exit 1; } ;;
  *) build_log="${lock_path%.lock}-build.log" ;;
esac

# ===========================================================================
# NEGATIVE TESTS — the gates must be proven to REJECT, not merely to accept.
# Run: ./scripts/check.sh --self-test   (deliberately NOT part of pre-commit;
# it invokes the whole gate a dozen times.)
#
# Read the final message carefully: it states what was PROVEN, and what it does not cover.
# An earlier version claimed "every gate was observed rejecting its failure case" while
# several gates had no case at all.
# ===========================================================================
# The self-test's throwaway repositories are never the caller's. Inside a hook git exports
# GIT_INDEX_FILE, and a caller may export GIT_DIR or GIT_OBJECT_DIRECTORY: inherited, a
# fixture's `git add -A` replaced the caller's staged content, and the synthetic-history
# readers (section 2) read the caller's history. fixture_env, called first in a subshell,
# unsets each variable that routes git to a repository: git's own list (`git rev-parse
# --local-env-vars`), the main ones again in case that fails, and two it leaves out.
# GIT_CONFIG* stays, as the gate's own documentation-only check keeps it.
fixture_env() {
  for v in $(git rev-parse --local-env-vars 2>/dev/null) GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE \
      GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_NAMESPACE GIT_CEILING_DIRECTORIES; do
    case $v in GIT_CONFIG*) ;; *) unset "$v" ;; esac
  done
}

self_test() {
  st_fail=0
  # Outside the tree, added to the scanners' input through a test switch (see the file
  # list below), so a concurrent `git add -A` or a killed self-test cannot leave it behind.
  inj="$work/injected.md"
  # The marker that lets this run's nested gates honour the seams (see the seam block).
  GATE_SELFTEST_NESTED=$(cat "$lock_path"); export GATE_SELFTEST_NESTED
  # The throwaway repositories below are never the caller's: every git call and hook run on a
  # fixture runs in a subshell that calls fixture_env first (defined above self_test).

  # A red tree cannot prove that a gate turns red: everything would "fail correctly".
  if ! baseline=$(sh "$0" 2>&1); then
    echo "SELF-TEST INCONCLUSIVE: the baseline gate run exited nonzero on this tree."
    echo "  Every case below would then pass for the wrong reason. Note that this only"
    echo "  tells you the command failed, not why — the output was:"
    printf '%s\n' "$baseline" | sed 's/^/    /' | tail -12
    return 2
  fi
  echo "self-test: baseline is green; injecting failures..."

  # helper: run the gate with an injected condition, expect FAILURE.
  # usage: expect_fail "<label>" env=val ... -- (command run via env)
  expect_fail() {
    label="$1"; shift
    if env "$@" sh "$0" >/dev/null 2>&1; then
      echo "  FAIL — $label: the gate stayed GREEN with its failure condition present."
      st_fail=1
    else
      echo "  ok   — $label"
    fi
  }
  expect_pass() {
    label="$1"; shift
    if env "$@" sh "$0" >/dev/null 2>&1; then
      echo "  ok   — $label"
    else
      echo "  FAIL — $label: the gate fired when it should have stayed quiet (false positive)."
      st_fail=1
    fi
  }

  # --- placeholder gate -----------------------------------------------------
  # The token is assembled at runtime on purpose: written literally, it would sit in this
  # file and the placeholder gate would flag its own source forever.
  printf 'injected by check.sh --self-test: %s%s\n' '{{SELF_TEST' '_TOKEN}}' > "$inj"
  expect_fail "placeholder gate rejects an unfilled marker" GATE_SELFTEST_EXTRA_FILE="$inj"

  # ...and does NOT fire on the two paths that carry markers forever by design.
  expect_pass "placeholder gate ignores setup/ and the module template"

  # --- STATE.md: present, with its heading, and never measured ---------------
  long="$work/long.md"; noheading="$work/noheading.md"
  {
    echo "# STATE"; echo; echo "## Active work"; echo
    echo "## Notes"
    i=0; while [ "$i" -lt 500 ]; do echo "line $i"; i=$((i + 1)); done
  } > "$long"
  sed 's/^## Active work/## Current things/' "$long" > "$noheading"

  expect_pass "state gate does not measure length: a long file with nothing active passes" GATE_SELFTEST_STATE_FILE="$long"
  expect_fail "state gate rejects a MISSING state file"        GATE_SELFTEST_STATE_FILE="$work/absent.md"
  expect_fail "state gate rejects a renamed 'Active work' heading" GATE_SELFTEST_STATE_FILE="$noheading"

  # --- a finished task still named in the state files -----------------------
  # A history of its own, outside the tree, whose one commit closed K4; and one with none.
  hist="$work/history"; fresh="$work/fresh"
  ( fixture_env; git init -q "$hist" && git init -q "$fresh" &&
    git -C "$hist" -c user.name=t -c user.email=t@example.invalid -c core.hooksPath=/dev/null \
        -c commit.gpgsign=false commit -q --allow-empty -m 'close K4' -m 'Done: K4' ) ||
    { echo "  FAIL — could not build the synthetic history for the Done: cases"; st_fail=1; }
  mkdir "$work/closed" "$work/other" "$work/backlog"
  printf '# STATE\n\n## Active work\n- K4: still listed\n' > "$work/closed/STATE.md"
  printf '# STATE\n\n## Active work\n- K4b: another task\n' > "$work/other/STATE.md"
  printf '# STATE\n\n## Active work\n' > "$work/backlog/STATE.md"
  printf '# BACKLOG\n\n- K4 again\n' > "$work/backlog/BACKLOG.md"
  expect_fail "state gate rejects a task a Done: trailer closed that STATE.md still names" \
    GATE_SELFTEST_STATE_FILE="$work/closed/STATE.md" GATE_SELFTEST_HISTORY="$hist"
  expect_fail "state gate rejects a closed task that BACKLOG.md still names" \
    GATE_SELFTEST_STATE_FILE="$work/backlog/STATE.md" GATE_SELFTEST_HISTORY="$hist"
  expect_pass "state gate does not read K4b as the closed K4" \
    GATE_SELFTEST_STATE_FILE="$work/other/STATE.md" GATE_SELFTEST_HISTORY="$hist"
  expect_pass "state gate passes a repository with no commit yet" \
    GATE_SELFTEST_STATE_FILE="$work/closed/STATE.md" GATE_SELFTEST_HISTORY="$fresh"

  # --- the gates that used to be skippable ----------------------------------
  expect_fail "boundary checks missing is a FAILURE, not a skip" \
    BOUNDARY_CHECKS_FILE="$work/absent.sh"
  expect_fail "an unconfigured build/test command is a FAILURE, not a warning" \
    GATE_BUILD_CMD_OVERRIDE=" "
  expect_fail "a failing build/test command fails the gate" \
    GATE_BUILD_CMD_OVERRIDE="false"
  expect_fail "an all-whitespace build/test command is unconfigured, not a no-op" \
    GATE_BUILD_CMD_OVERRIDE="  "

  # --- a seam outside the self-test ---------------------------------------------
  # Without the marker, an exported override fails the run by name instead of turning a red
  # build green.
  if (unset GATE_SELFTEST_NESTED; GATE_BUILD_CMD_OVERRIDE=false sh "$0" 2>&1) |
     grep -q '^FAIL \[env\]: GATE_BUILD_CMD_OVERRIDE is set'; then
    echo "  ok   — an override exported outside --self-test fails the gate by name"
  else
    echo "  FAIL — an override exported outside --self-test was honoured, not refused."
    st_fail=1
  fi

  # --- PROJECT.md navigability ------------------------------------------------
  proj_ok="$work/project_ok.md"; proj_bad="$work/project_bad.md"; proj_young="$work/project_young.md"
  {
    echo "# PROJECT"; echo; echo "## Contents"; echo
    echo "- 1. What this project is"; echo "- 2. Money"; echo
    echo "## 1. What this project is"; echo "a line"; echo
    echo "## 2. Money"; echo "another line"
  } > "$proj_ok"
  # Section 2 exists but was never added to the Contents — the drift this gate catches.
  sed '/- 2\. Money/d' "$proj_ok" > "$proj_bad"
  { echo "# PROJECT"; echo; echo "## Contents"; echo; echo "(nothing decided yet)"; } > "$proj_young"

  # A section number that is a PREFIX of a listed one. Under a substring match "1. Money"
  # is found inside the Contents entry "11. Money" and the gate goes green on an unlisted
  # section — which is what it did until the match was anchored.
  {
    echo "# PROJECT"; echo; echo "## Contents"; echo; echo "- 11. Money"; echo
    echo "## 1. Money"; echo "unlisted"; echo; echo "## 11. Money"; echo "listed"
  } > "$work/project_prefix.md"

  expect_pass "PROJECT gate accepts a file whose Contents lists every section" GATE_SELFTEST_PROJECT_FILE="$proj_ok"
  expect_fail "PROJECT gate rejects a section missing from the Contents"       GATE_SELFTEST_PROJECT_FILE="$proj_bad"
  expect_fail "PROJECT gate is not fooled by a section number that prefixes another" \
    GATE_SELFTEST_PROJECT_FILE="$work/project_prefix.md"
  expect_fail "PROJECT gate rejects a MISSING project file"                    GATE_SELFTEST_PROJECT_FILE="$work/absent.md"
  expect_pass "PROJECT gate stays quiet on a young file with no sections yet"  GATE_SELFTEST_PROJECT_FILE="$proj_young"

  # --- the commit hook --------------------------------------------------------
  # The hook is the gate that actually holds, for every tool, and until now nothing proved
  # it carries a red gate out to a nonzero exit. It is four lines, which is exactly the kind
  # of code nobody tests and everybody assumes. A clean `git merge` runs pre-merge-commit,
  # not pre-commit, for the merge commit it creates: two green branches can merge into a red
  # tree, so that hook is held to the same two cases.
  for hook in .githooks/pre-commit .githooks/pre-merge-commit; do
    if [ ! -f "$hook" ]; then
      echo "  FAIL — $hook is missing: nothing enforces the gate on those commits."
      st_fail=1
    elif ! sh "$hook" >/dev/null 2>&1; then
      echo "  FAIL — $hook rejected a GREEN tree; every such commit would be blocked."
      st_fail=1
    elif env GATE_SELFTEST_EXTRA_FILE="$inj" sh "$hook" >/dev/null 2>&1; then
      echo "  FAIL — $hook exited 0 while the gate was RED. It is blocking nothing."
      st_fail=1
    else
      echo "  ok   — $hook passes a green tree and aborts on a red one"
    fi
  done

  # --- the commit message hook --------------------------------------------------
  # A coding tool's default instruction adds an AI co-author trailer to every commit; a rule
  # in AGENTS.md alone did not stop it. A human co-author must still get through, even one
  # whose name contains a tool's. Without the rule line in AGENTS.md the hook gives way, and
  # this case says so out loud: an owner who allows AI credit drops the line (setup
  # interview), and a project synced from before v0.9 has not added it yet. The skip names
  # the missing line, never a choice nobody may have made.
  printf 'change\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n' > "$work/msg_ai"
  printf 'change\n\nCo-authored-by: Claude Monet <person@example.invalid>\n' > "$work/msg_human"
  if [ -f AGENTS.md ] && ! grep -q 'No AI attribution in git' AGENTS.md; then
    echo "  skip — commit-msg hook: off, AGENTS.md has no 'No AI attribution in git' rule line (the owner allows"
    echo "         AI credit, or the line was never added after a sync); the hook passes every message."
  elif [ ! -f .githooks/commit-msg ]; then
    echo "  FAIL — .githooks/commit-msg is missing: nothing rejects an AI co-author trailer."
    st_fail=1
  elif sh .githooks/commit-msg "$work/msg_ai" >/dev/null 2>&1; then
    echo "  FAIL — commit-msg hook accepted an AI co-author trailer."
    st_fail=1
  elif ! sh .githooks/commit-msg "$work/msg_human" >/dev/null 2>&1; then
    echo "  FAIL — commit-msg hook rejected a human co-author (false positive)."
    st_fail=1
  else
    echo "  ok   — commit-msg hook rejects an AI co-author trailer and keeps a human one"
  fi
  # A "Done: K4" trailer while the STATE.md this commit records still names K4 is refused,
  # whatever AGENTS.md says about attribution: the two checks are separate. The hook reads
  # the index, so the case stages its files in a throwaway repository, never in this one.
  if [ ! -f .githooks/commit-msg ]; then
    echo "  FAIL — .githooks/commit-msg is missing: nothing rejects a Done: trailer for a task still listed."
    st_fail=1
  else
    msg_hook="$(pwd)/.githooks/commit-msg"; done_repo="$work/done-repo"
    printf 'close K4\n\nDone: K4\n' > "$work/msg_done"
    ( fixture_env; git init -q "$done_repo" ) && mkdir "$done_repo/docs" ||
      { echo "  FAIL — could not build the throwaway repository for the Done: hook cases"; st_fail=1; }
    for rule in present absent; do
      if [ "$rule" = present ]; then echo '- **No AI attribution in git.**'; else echo 'AI tools may be credited.'; fi > "$done_repo/AGENTS.md"
      printf '# STATE\n\n## Active work\n- K4: still listed\n' > "$done_repo/docs/STATE.md"
      ( fixture_env; git -C "$done_repo" add -A )
      if (fixture_env; CDPATH= cd -- "$done_repo" && sh "$msg_hook" "$work/msg_done") >/dev/null 2>&1; then
        echo "  FAIL — commit-msg hook accepted Done: K4 while the staged STATE.md names K4 (rule line $rule)"
        st_fail=1; continue
      fi
      printf '# STATE\n\n## Active work\n' > "$done_repo/docs/STATE.md"
      ( fixture_env; git -C "$done_repo" add -A )
      if (fixture_env; CDPATH= cd -- "$done_repo" && sh "$msg_hook" "$work/msg_done") >/dev/null 2>&1; then
        echo "  ok   — commit-msg hook refuses Done: K4 until the staged STATE.md drops it (rule line $rule)"
      else
        echo "  FAIL — commit-msg hook rejected Done: K4 after the line was deleted (rule line $rule; false positive)"
        st_fail=1
      fi
    done
  fi

  # --- build failure output -----------------------------------------------------
  # The lines that locate a compile error ("In function", "required from", "note:") come
  # before and around the "error:" line. A gate that printed only lines matching "error"
  # hid them, and a CI-only failure had to be fixed blind. The failure must be named, its
  # chain must reach the output, and the whole log must be kept. On CI the log in .git
  # vanishes with the runner, so there the whole log is printed instead of the tail.
  build_fail='i=0; while [ $i -lt 300 ]; do echo "build line $i"; i=$((i + 1)); done
    echo "src/x.c: In function f:"; echo "src/x.c:3:5: error: bad"; echo "src/x.c:2:1: note: declared here"; exit 1'
  out=$(env CI= GATE_BUILD_CMD_OVERRIDE="$build_fail" sh "$0" 2>&1)
  ci_out=$(env CI=true GATE_BUILD_CMD_OVERRIDE="$build_fail" sh "$0" 2>&1)
  if printf '%s\n' "$out" | grep -q '^FAIL \[build\]' &&
     printf '%s\n' "$out" | grep -q 'In function f:' &&
     printf '%s\n' "$out" | grep -q 'note: declared here' &&
     ! printf '%s\n' "$out" | grep -q '^build line 0$' &&
     printf '%s\n' "$ci_out" | grep -q '^build line 0$' &&
     grep -q '^build line 0$' "$build_log" 2>/dev/null; then
    echo "  ok   — a build failure is named, shows its diagnostic chain, keeps the full log, and prints it on CI"
  else
    echo "  FAIL — a build failure was not named, lost its diagnostic chain, left no full log, or hid it on CI."
    st_fail=1
  fi

  # --- a documentation-only commit skips the build, and only the build ------------
  # The decision reads a throwaway repository's index (GATE_SELFTEST_COMMIT_REPO), never this
  # one's. The build is `false` throughout, so a run that reached it fails.
  docs_repo="$work/docs-commit"
  if ( fixture_env; git init -q "$docs_repo" && printf 'int x;\n' > "$docs_repo/code.c" &&
     git -C "$docs_repo" add code.c &&
     git -C "$docs_repo" -c user.name=t -c user.email=t@example.invalid -c core.hooksPath=/dev/null \
         -c commit.gpgsign=false commit -q -m base &&
     printf 'a\n' > "$docs_repo/a.md" && printf 'b\n' > "$docs_repo/b.md" &&
     git -C "$docs_repo" add a.md b.md ); then
    out=$(env GATE_SELFTEST_COMMIT_REPO="$docs_repo" GATE_BUILD_CMD_OVERRIDE=false sh "$0" --for-commit 2>&1)
    # The case asserts what the switch beside build_test_cmd selects, read from this file by
    # the shell itself: with docs_only_skip_build=0 the skipped build was demanded anyway.
    eval "$(grep '^docs_only_skip_build=' "$0" | head -n 1)"
    if [ "${docs_only_skip_build:-}" != 1 ]; then
      if printf '%s\n' "$out" | grep -q '^FAIL \[build\]' && ! printf '%s\n' "$out" | grep -q 'build not run'; then
        echo "  ok   — docs_only_skip_build=$docs_only_skip_build: a commit of two documents runs the build"
      else
        echo "  FAIL — docs_only_skip_build=$docs_only_skip_build, and a commit of two documents skipped the build."
        st_fail=1
      fi
    elif printf '%s\n' "$out" | grep -qx 'CHECK: PASS (build not run: documentation-only commit, 2 files)'; then
      echo "  ok   — a commit of two documents skips the build and says so in the PASS line"
    else
      echo "  FAIL — a commit of two documents ran the build, or passed without saying it skipped it."
      st_fail=1
    fi
    if env GATE_SELFTEST_COMMIT_REPO="$docs_repo" GATE_BUILD_CMD_OVERRIDE=false sh "$0" >/dev/null 2>&1; then
      echo "  FAIL — a manual run with only documents staged skipped the build."
      st_fail=1
    else
      echo "  ok   — a manual run with only documents staged still runs the build"
    fi
    if env GATE_SELFTEST_COMMIT_REPO="$docs_repo" GATE_BUILD_CMD_OVERRIDE=true GATE_SELFTEST_EXTRA_FILE="$inj" \
         sh "$0" --for-commit >/dev/null 2>&1; then
      echo "  FAIL — a documentation-only commit skipped the placeholder scan as well as the build."
      st_fail=1
    else
      echo "  ok   — a documentation-only commit still fails an unfilled placeholder"
    fi
    printf 'int y;\n' > "$docs_repo/code.c" && ( fixture_env; git -C "$docs_repo" add code.c )
    if env GATE_SELFTEST_COMMIT_REPO="$docs_repo" GATE_BUILD_CMD_OVERRIDE=false sh "$0" --for-commit >/dev/null 2>&1; then
      echo "  FAIL — a commit of documents and a code file skipped the build."
      st_fail=1
    else
      echo "  ok   — a commit of documents and a code file runs the build"
    fi
  else
    echo "  FAIL — could not build the throwaway repository for the documentation-only cases"
    st_fail=1
  fi

  # --- scanner integrity ------------------------------------------------------
  # The switch makes scan_grep report failure the way a broken grep would. This proves the
  # flag-file plumbing end to end — a failed scan cannot end in CHECK: PASS — though not a
  # genuine grep crash.
  expect_fail "a failed scanner cannot report a clean scan" GATE_SELFTEST_BREAK_SCANNER=1

  # --- project boundary self-tests ------------------------------------------
  # One case per check in the boundary checks file. Sourced, so it can set st_fail.
  # Its ABSENCE is a failure: a boundary check with no negative test has not been tested.
  review_test_log=$(mktemp) || return 1
  if ! sh scripts/review.sh --self-test > "$review_test_log" 2>&1 ||
     ! grep -qx 'REVIEW SELF-TEST: PASS' "$review_test_log"; then
    echo "  FAIL — review adapter negative tests failed or did not run"
    st_fail=1
  fi
  cat "$review_test_log"
  rm -f "$review_test_log"

  if [ -f "$BOUNDARY_SELFTESTS_FILE" ]; then
    # Sourced with its output captured (still this shell, so st_fail carries over): a
    # boundary checks file with real checks whose self-test file ran NO case was skipped,
    # and a skipped self-test is not a pass.
    . "./$BOUNDARY_SELFTESTS_FILE" > "$work/boundary_selftests.out"
    cat "$work/boundary_selftests.out"
    if grep -v '^[[:space:]]*#' "$BOUNDARY_CHECKS_FILE" 2>/dev/null | grep -q '[^[:space:]]' &&
       ! grep -q '^  ok   — ' "$work/boundary_selftests.out"; then
      echo "  FAIL — $BOUNDARY_CHECKS_FILE has checks but $BOUNDARY_SELFTESTS_FILE ran no case"
      echo "         (none printed '  ok   — <label>'). A self-test that did not run is not a pass."
      st_fail=1
    fi
  else
    echo "  FAIL — $BOUNDARY_SELFTESTS_FILE is missing: the project's boundary checks have"
    echo "         no negative tests, so they have never been observed rejecting anything."
    st_fail=1
  fi

  echo
  if [ "$st_fail" -eq 0 ]; then
    echo "SELF-TEST: PASS — each case above was observed making the gate exit nonzero."
    echo "  Exit-only generic cases do not prove which check caused failure. The worked"
    echo "  boundary example also requires its own diagnostic. The scanner case breaks the"
    echo "  scanner through a test switch, not by making grep itself crash."
    return 0
  fi
  echo "SELF-TEST: FAIL — a gate did not behave as claimed. It is protecting nothing."
  return 1
}

for_commit="" pass_note=""
case "${1:-}" in
  "")           ;;
  --self-test)  self_test; exit $? ;;
  --for-commit) for_commit=1 ;;
  *)            echo "usage: check.sh [--self-test | --for-commit]"; exit 2 ;;
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
      elif [ ! -e "$p" ]; then
        printf "%s\n" "NOTE [scan]: skipped $p, a symlink whose target is missing; its link text is scanned instead." >&3
      fi
    elif [ -f "$p" ]; then
      printf "%s\0" "$p"
    elif [ -d "$p" ] && { case "$p" in */) true ;; *) false ;; esac ||
                          [ "$(git ls-files -s -- ":(literal)$p" | cut -c1-6)" = 160000 ]; }; then
      printf "%s\n" "NOTE [scan]: skipped $p, a submodule or a repository inside this one; its files belong to that repository." >&3
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
# Test switch: the self-test's injected file lives outside the tree and joins the scan here.
[ -z "${GATE_SELFTEST_EXTRA_FILE:-}" ] || printf '%s\0' "$GATE_SELFTEST_EXTRA_FILE" >> "$filelist"

# scan_grep <extended-regex> — prints path:line:text for every match.
# Returns 0 on match, 1 on no match. When grep itself FAILS, it drops a flag file that the
# main shell checks before the final verdict. The flag, not an exit, is deliberate: callers
# run this inside command substitutions, where `exit` terminates only the SUBSHELL — an
# earlier version "exited fatally" from inside `$(...)` and the gate sailed on to PASS.
# A file crosses that boundary; nothing a caller does can turn a failed scan into a clean one.
scan_grep() {
  if [ -n "${GATE_SELFTEST_BREAK_SCANNER:-}" ]; then
    : > "$work/scan_failed"
    return 2
  fi
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
if [ ! -f "$GATE_SELFTEST_STATE_FILE" ]; then
  echo "FAIL [state]: $GATE_SELFTEST_STATE_FILE does not exist. It is the cross-session memory; without it"
  echo "              this check proves nothing."
  fail=1
elif ! grep -q "^## Active work" "$GATE_SELFTEST_STATE_FILE"; then
  echo "FAIL [state]: $GATE_SELFTEST_STATE_FILE has no '## Active work' heading. Restore the heading"
  echo "              rather than removing the check."
  fail=1
fi

# Finished work. The commit that finishes a task says so with a "Done: <id>" trailer
# (docs/WORKFLOW.md, "Task ids"), and every id that a commit reachable from HEAD closed must
# be gone from the state file and from the BACKLOG.md beside it, which may be absent (a
# project may keep its backlog elsewhere). The commit-msg hook checks the closing commit;
# this also catches a line written back later, or a commit the hook never saw. Git's own
# trailer parser reads the history (%(trailers:key=...,unfold), git 2.22 or later). A
# mention is the id as a whole token in any case: closing K3 does not match K3b or K3-a, and
# "Done: k3" closes K3 (it once passed while STATE.md named K3). No repository,
# or no commit yet: nothing has been closed, and nothing is checked. A shallow clone holds
# part of the history: a NOTE says so, and the part it holds is checked.
history_repo="${GATE_SELFTEST_HISTORY:-.}"
# The self-test's synthetic history is read with no inherited GIT_DIR routing it elsewhere.
hgit() {
  if [ -n "${GATE_SELFTEST_HISTORY:-}" ]; then ( fixture_env; git -C "$history_repo" "$@" )
  else git -C "$history_repo" "$@"; fi
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
    for f in "$GATE_SELFTEST_STATE_FILE" "$(dirname "$GATE_SELFTEST_STATE_FILE")/BACKLOG.md"; do
      [ ! -f "$f" ] || awk -v closed="$work/done-ids" '
        FILENAME == closed {
          if (sub(/^@/, "")) commit = $0
          else if (!(tolower($0) in by)) { by[tolower($0)] = commit; as[tolower($0)] = $0 }
          next
        }
        { n = split($0, word, /[^A-Za-z0-9_-]+/)
          for (i = 1; i <= n; i++) if ((key = tolower(word[i])) in by) {
            printf "FAIL [state]: %s:%d names %s, which commit %s closed (Done: %s).\n", FILENAME, FNR, word[i], by[key], as[key]
            found = 1
          } }
        END { if (found) print "              Delete the line (the history is in git); a task needed again gets a new id."
              exit found }' "$work/done-ids" "$f" || fail=1
    done
  else
    echo "FAIL [state]: git log could not list the Done: trailers, so finished tasks were not checked."
    fail=1
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
GATE_SELFTEST_PROJECT_FILE="${GATE_SELFTEST_PROJECT_FILE:-docs/PROJECT.md}"
if [ ! -f "$GATE_SELFTEST_PROJECT_FILE" ]; then
  echo "FAIL [project]: $GATE_SELFTEST_PROJECT_FILE does not exist. It is where permanent decisions live;"
  echo "                without it they end up in docs/STATE.md and are pruned away."
  fail=1
elif ! grep -q "^## Contents" "$GATE_SELFTEST_PROJECT_FILE"; then
  echo "FAIL [project]: $GATE_SELFTEST_PROJECT_FILE has no '## Contents' section, so it cannot be read"
  echo "                selectively and every reader will load the whole file."
  fail=1
else
  # Headings first, then the Contents block, then the set difference. Compared on the
  # heading TEXT rather than on a link target, because the text is what a human maintains.
  # Entries are normalised to bare heading text — list marker, link syntax and trailing
  # space removed — so that a Contents written as "- 1. Money" or "- [1. Money](#money)"
  # both compare equal to the heading "## 1. Money".
  awk '/^## Contents/{f=1;next} /^## /{f=0} f' "$GATE_SELFTEST_PROJECT_FILE" \
    | sed -e 's/^[[:space:]]*[-*][[:space:]]*//' \
          -e 's/^\[//' -e 's/\](#[^)]*)[[:space:]]*$//' \
          -e 's/[[:space:]]*$//' > "$work/toc"
  missing=""
  sed -n 's/^## \([0-9][0-9.]*\.\{0,1\}[[:space:]].*\)$/\1/p' "$GATE_SELFTEST_PROJECT_FILE" > "$work/heads"
  while IFS= read -r h; do
    [ -n "$h" ] || continue
    # -x anchors to the WHOLE line and -F takes the pattern literally. Without -x this was a
    # substring test, and "1. Money" matched inside the Contents entry "11. Money" — so an
    # unlisted section 1 passed the gate while the gate was reporting on section 11.
    grep -qxF -- "$h" "$work/toc" || missing="$missing
  - $h"
  done < "$work/heads"
  if [ -n "$missing" ]; then
    echo "FAIL [project]: $GATE_SELFTEST_PROJECT_FILE has numbered sections missing from its Contents:$missing"
    echo "                Add them, or renumber. Citations elsewhere point at these numbers."
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
if [ -f "$BOUNDARY_CHECKS_FILE" ]; then
  . "./$BOUNDARY_CHECKS_FILE"
else
  echo "FAIL [boundary]: $BOUNDARY_CHECKS_FILE is missing. Boundary enforcement is not"
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
[ -n "${GATE_BUILD_CMD_OVERRIDE:-}" ] && build_test_cmd="$GATE_BUILD_CMD_OVERRIDE"
# A commit that changes only documentation skips the build/test command, and nothing else:
# every scan and check above has run. A project's gate built for minutes on every such commit.
# 1: on. 0: off, for a project whose build reads markdown (a documentation site, doc tests).
docs_only_skip_build=1
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
import os, subprocess, sys
repo, env = sys.argv[1], dict(os.environ)
if repo != ".":
    env = {k: v for k, v in env.items() if not k.startswith("GIT_") or k.startswith("GIT_CONFIG")}
def git(*args):
    return subprocess.run(("git",) + args, cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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
' "${GATE_SELFTEST_COMMIT_REPO:-.}" 2>/dev/null) || docs_only=""
      case "$docs_only" in ""|0|*[!0-9]*) docs_only="" ;; esac
    fi
    if [ -n "$docs_only" ]; then
      if [ "$docs_only" = 1 ]; then unit=file; else unit=files; fi
      pass_note=" (build not run: documentation-only commit, $docs_only $unit)"
      echo "NOTE [build]: not run: every path this commit changes is documentation ($docs_only $unit)."
    else
      # Quiet when it passes; on failure the summary line, then the TAIL, never a filter. The
      # lines that locate a compile error ("In function", "required from", "note:") do not
      # match "error", and a gate that printed only matching lines sent a CI-only failure out
      # with its location cut away. The whole output stays in $build_log for a local run. On CI
      # that file vanishes with the runner and the first error of a long chain sits above any
      # tail, so CI prints the whole log.
      # ponytail: a fixed tail; raise build_tail if your diagnostic chains run longer.
      build_tail=150
      ( if [ -n "$caller_lc_all_set" ]; then LC_ALL=$caller_lc_all; else unset LC_ALL; fi
        exec sh -c "$build_test_cmd" ) > "$build_log" 2>&1
      rc=$?
      if [ "$rc" -ne 0 ] && [ -n "${CI:-}" ]; then
        echo "FAIL [build]: the build/test command exited $rc. Its whole output follows (CI)."
        cat "$build_log"
        fail=1
      elif [ "$rc" -ne 0 ]; then
        echo "FAIL [build]: the build/test command exited $rc. Its last $build_tail lines follow;"
        echo "              the whole output is in $build_log"
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

if [ "$fail" -eq 0 ]; then echo "CHECK: PASS${pass_note:-}"; else echo "CHECK: FAIL"; exit 1; fi
