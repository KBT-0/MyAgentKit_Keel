#!/usr/bin/env sh
# {{PROJECT_NAME}} quality gate — EVERY agent runs this before finishing a task.
# CI runs the SAME script. There is one definition of "green" in this repository, and it is
# here — which is NOT the same as a promise that local and CI always agree. Same script,
# different machine: file modes, installed tools and locale can all differ (docs/GOTCHAS.md
# has the exit-126 case that kept a pipeline red for weeks). Check the pipeline after
# pushing; do not infer it from a local pass.
#
# Usage: check.sh [--self-test]
#   default      run the gates
#   --self-test  prove the gates actually go RED (the block near the bottom)
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
cd "$(dirname "$0")/.."
fail=0

# SELF-TEST SEAMS are honoured ONLY in the self-test's own nested runs. Each one exists so a
# case can point a gate at a synthetic input, which means each one can also turn a gate green
# without its work: GATE_BUILD_CMD_OVERRIDE=true skips the build, GATE_SELFTEST_STATE_FILE reads another
# file. The commit hook inherits the committer's environment, so a variable left exported in
# a profile or a CI step, or typed by an agent facing a red build, did exactly that. A run
# that finds one without the self-test's marker FAILS and names it; it does not unset it and
# carry on, because then the run that someone believed was overridden reports on something
# else. The marker is the lock holder's pid, exported only by self_test(), and is believed
# only while this checkout's lock is held by that pid: it stops an accidental export, not a
# deliberate forgery by someone who holds the lock. A NEW SEAM JOINS THIS LIST.
# GATE_LOCK_WAIT and GATE_LOCK_HELD are not seams: they change when a run starts, not what
# it checks.
lock_path=$(git rev-parse --git-path check.lock 2>/dev/null) || lock_path=.check.lock
case "$lock_path" in /*) ;; *) lock_path="$(pwd -P)/$lock_path" ;; esac
if [ -z "${GATE_SELFTEST_NESTED:-}" ] || [ "${GATE_LOCK_HELD:-}" != "$lock_path" ] ||
   [ "$(readlink "$lock_path" 2>/dev/null)" != "$GATE_SELFTEST_NESTED" ]; then
  for seam in GATE_BUILD_CMD_OVERRIDE GATE_SELFTEST_STATE_FILE GATE_SELFTEST_PROJECT_FILE BOUNDARY_CHECKS_FILE \
              BOUNDARY_SELFTESTS_FILE GATE_SELFTEST_EXTRA_FILE GATE_SELFTEST_BREAK_SCANNER; do
    eval "seam_value=\${$seam:-}"
    [ -z "$seam_value" ] || { echo "FAIL [env]: $seam is set; self-test overrides are not honoured outside --self-test"; fail=1; }
  done
  [ "$fail" -eq 0 ] || exit 1
fi

# Overridable so the self-test can point the rot gate at a synthetic file instead of
# mutating the real one. Only the self-test sets it (the seam block above).
GATE_SELFTEST_STATE_FILE="${GATE_SELFTEST_STATE_FILE:-docs/STATE.md}"

# Toolchains are commonly installed per-user and then missing from the PATH of git hooks
# and other non-login shells; without this the gate fails for the wrong reason. A VALUE, not
# a line of code — a placeholder that has to be replaced INSIDE a comment is a trap, because
# a half-finished edit leaves the code commented out and the gate silently toothless.
# Example: "$HOME/.dotnet". Leave empty if nothing extra is needed.
toolchain_path="{{TOOLCHAIN_PATH_SETUP}}"
case "$toolchain_path" in
  ""|*"{{"*) ;;
  *) PATH="$toolchain_path:$PATH"; export PATH ;;
esac

# Overridable so the self-test can prove these branches without mutating the repository.
# Only the self-test sets them (the seam block above).
BOUNDARY_CHECKS_FILE="${BOUNDARY_CHECKS_FILE:-scripts/boundary_checks.sh}"
BOUNDARY_SELFTESTS_FILE="${BOUNDARY_SELFTESTS_FILE:-scripts/boundary_selftests.sh}"

work=$(mktemp -d) || { echo "FAIL [gate]: cannot create a temp dir; refusing to run blind."; exit 1; }
lock=""
# Only our own lock: after a stale reclaim race another run may hold this path.
cleanup() {
  rm -rf "$work"
  [ -z "$lock" ] || [ "$(readlink "$lock" 2>/dev/null)" != "$$" ] || rm -f "$lock"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
filelist="$work/files"

# ONE GATE RUN PER CHECKOUT AT A TIME. The Stop hook, the commit hook and a manual run can
# start together, and a project's build command usually writes one fixed build directory:
# two runs sharing it configured, built and ran tests over each other and one reported FAIL
# for a tree that passes alone. A second run therefore WAITS here; it never fails for this.
# The self-test holds the lock for its whole run, so no other gate sees a case mid-injection.
# Nested runs (the self-test's own `sh "$0"`, the commit hook it calls) inherit the lock
# through GATE_LOCK_HELD, which names the lock path, so a gate in another checkout started
# from the build command still takes its own lock. The lock is a symlink whose target is the
# holder's pid: created in one atomic step, it is never seen without its owner.
case "${GATE_LOCK_WAIT:-}" in
  *[!0-9]*) echo "FAIL [lock]: GATE_LOCK_WAIT must be a number of seconds, got '$GATE_LOCK_WAIT'."; exit 1 ;;
esac
# lock_path is computed in the seam block above.
if [ "${GATE_LOCK_HELD:-}" != "$lock_path" ]; then
  # A directory here (hand-made, or a mkdir-style lock) would let `ln -s` succeed INSIDE it,
  # so every run would "take" the lock and none would release it.
  if [ -d "$lock_path" ]; then echo "FAIL [lock]: $lock_path is a directory, not a gate lock; delete it."; exit 1; fi
  waited=0
  until ln -s "$$" "$lock_path" 2>/dev/null; do
    holder=$(readlink "$lock_path" 2>/dev/null) || holder=""
    # A dead holder (killed, power loss) is stale. An empty holder means the lock vanished
    # between our attempt and the read; the next attempt settles it.
    # ponytail: two waiters reclaiming the same stale lock in the same second can both
    # run; a pid-checked rename would close that if it is ever seen.
    if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then
      echo "NOTE [lock]: removing a stale gate lock left by pid $holder, which no longer runs."
      rm -f "$lock_path"; continue
    fi
    if [ -n "${GATE_LOCK_WAIT:-}" ] && [ "$waited" -ge "$GATE_LOCK_WAIT" ]; then
      echo "NOT RUN [lock]: pid ${holder:-unknown} has held $lock_path for ${waited}s; GATE_LOCK_WAIT=$GATE_LOCK_WAIT ran out."
      exit 75
    fi
    [ $((waited % 30)) -ne 0 ] ||
      echo "NOTE [lock]: another gate run (pid ${holder:-unknown}) has held $lock_path for ${waited}s; waiting for it (if pid ${holder:-unknown} is not a gate run, remove $lock_path)."
    sleep 1; waited=$((waited + 1))
  done
  lock=$lock_path
  GATE_LOCK_HELD=$lock_path; export GATE_LOCK_HELD
fi

# ===========================================================================
# NEGATIVE TESTS — the gates must be proven to REJECT, not merely to accept.
# Run: ./scripts/check.sh --self-test   (deliberately NOT part of pre-commit;
# it invokes the whole gate a dozen times.)
#
# Read the final message carefully: it states what was PROVEN, and what it does not cover.
# An earlier version claimed "every gate was observed rejecting its failure case" while
# several gates had no case at all.
# ===========================================================================
self_test() {
  st_fail=0
  # Outside the tree, added to the scanners' input through a test switch (see the file
  # list below), so a concurrent `git add -A` or a killed self-test cannot leave it behind.
  inj="$work/injected.md"
  # The marker that lets this run's nested gates honour the seams (see the seam block).
  GATE_SELFTEST_NESTED=$(readlink "$lock_path"); export GATE_SELFTEST_NESTED

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

  # --- STATE.md rot gate, all four branches ---------------------------------
  rot="$work/rot.md"; live="$work/live.md"; noheading="$work/noheading.md"
  {
    echo "# STATE"; echo; echo "## Active work"
    echo "(nothing in flight — this hint line must NOT be counted as work)"; echo
    echo "## History"
    i=0; while [ "$i" -lt 250 ]; do echo "stale line $i"; i=$((i + 1)); done
  } > "$rot"
  {
    echo "# STATE"; echo; echo "## Active work"
    echo "(nothing in flight — this hint line must NOT be counted as work)"
    echo "- a genuine bullet: one task is in flight right now"; echo
    echo "## History"
    i=0; while [ "$i" -lt 250 ]; do echo "stale line $i"; i=$((i + 1)); done
  } > "$live"
  sed 's/^## Active work/## Current things/' "$rot" > "$noheading"

  expect_fail "rot gate rejects a long file nobody pruned after the work closed" GATE_SELFTEST_STATE_FILE="$rot"
  expect_pass "rot gate stays quiet while a real bullet is under 'Active work'" GATE_SELFTEST_STATE_FILE="$live"
  expect_fail "rot gate rejects a MISSING state file"        GATE_SELFTEST_STATE_FILE="$work/absent.md"
  expect_fail "rot gate rejects a renamed 'Active work' heading" GATE_SELFTEST_STATE_FILE="$noheading"

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
  # of code nobody tests and everybody assumes.
  hook=".githooks/pre-commit"
  if [ -f "$hook" ]; then
    if sh "$hook" >/dev/null 2>&1; then
      echo "  ok   — commit hook exits 0 on a green tree"
    else
      echo "  FAIL — commit hook rejected a GREEN tree; every commit would be blocked."
      st_fail=1
    fi
    if env GATE_SELFTEST_EXTRA_FILE="$inj" sh "$hook" >/dev/null 2>&1; then
      echo "  FAIL — commit hook exited 0 while the gate was RED. It is blocking nothing."
      st_fail=1
    else
      echo "  ok   — commit hook aborts the commit when the gate is red"
    fi
  else
    echo "  FAIL — $hook is missing: nothing enforces the gate at commit time."
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

case "${1:-}" in
  "")           ;;
  --self-test)  self_test; exit $? ;;
  *)            echo "usage: check.sh [--self-test]"; exit 2 ;;
esac

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
# named and FAILS the gate: the scan cannot vouch for a path the commit may still carry. A
# symlink to a directory (a dependency directory linked into a fresh worktree, which an
# ignore pattern with a trailing slash does not match) holds nothing git tracks: skipped,
# with a line.
if ! xargs -0 sh -c '
  scan_work=$1
  shift
  for p do
    if [ -L "$p" ] && [ -d "$p" ]; then
      printf "%s\n" "NOTE [scan]: skipped $p, a symlink to a directory; git tracks nothing inside it." >&3
      printf "%s\n" "             To ignore it, write it in .gitignore without a trailing slash." >&3
    elif [ -L "$p" ] && [ ! -e "$p" ]; then
      printf "%s\n" "NOTE [scan]: skipped $p, a symlink whose target is missing; git tracks only the link text." >&3
    elif [ ! -e "$p" ]; then
      printf "%s\n" "FAIL [scan]: $p is tracked but missing from the working tree (deleted, not staged)." >&3
      printf "%s\n" "             Run git rm -- \"$p\" to record the deletion, or git restore -- \"$p\"." >&3
      : > "$scan_work/scan_missing"
    else
      printf "%s\0" "$p"
    fi
  done
' sh "$work" < "$filelist" 3>&1 > "$filelist.kept"; then
  echo "FAIL [scan]: could not sort the file list; refusing to scan blind."
  exit 1
fi
mv "$filelist.kept" "$filelist"
[ ! -e "$work/scan_missing" ] || fail=1
if [ ! -s "$filelist" ]; then
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
  echo "$hits" | head -30
  [ "$(echo "$hits" | wc -l)" -gt 30 ] && echo "              ... and more"
  fail=1
fi

# ---------------------------------------------------------------------------
# 2) STATE.md rot
# ---------------------------------------------------------------------------
# Length alone is NOT the signal. A long state file is healthy in the middle of a long
# operation and rot the day after it closes; a fixed line limit cannot tell those apart.
# This can: an EMPTY "Active work" section means everything left in the file is history,
# and history belongs in git — once the permanent parts have been harvested into their real
# homes (AGENTS.md, "STATE.md discipline").
#
# A missing file or a renamed heading is a FAILURE, not a skip. Skipping there meant the
# whole gate could be disabled by deleting one file or editing one line.
if [ ! -f "$GATE_SELFTEST_STATE_FILE" ]; then
  echo "FAIL [state]: $GATE_SELFTEST_STATE_FILE does not exist. It is the cross-session memory and the"
  echo "              rot gate's only input; without it this check proves nothing."
  fail=1
elif ! grep -q "^## Active work" "$GATE_SELFTEST_STATE_FILE"; then
  echo "FAIL [state]: $GATE_SELFTEST_STATE_FILE has no '## Active work' heading, so the rot gate cannot"
  echo "              run. Restore the heading rather than removing the check."
  fail=1
else
  lines=$(wc -l < "$GATE_SELFTEST_STATE_FILE")
  # Count BULLETS, never lines. Prose under the heading is the section's own hint text and
  # must not read as work — it wraps, so any "skip the first line" filter silently counts
  # the second one and defeats the gate. That precise bug shipped once; hence the case in
  # self_test().
  active=$(awk '/^## Active work/{f=1;next} /^## /{f=0} f' "$GATE_SELFTEST_STATE_FILE" \
    | grep -c "^[[:space:]]*[-*][[:space:]]")
  if [ "$active" -eq 0 ] && [ "$lines" -gt 200 ]; then
    echo "FAIL [state]: $GATE_SELFTEST_STATE_FILE is $lines lines with an EMPTY 'Active work' section —"
    echo "              the operation closed but the file was never pruned. Harvest the"
    echo "              permanent parts (grep for [LESSON] / [GOTCHA]) into their homes,"
    echo "              then delete the rest: it is in git. Operation detail belongs in"
    echo "              docs/<OPERATION>.md, with one pointer line here (docs/STATE.md)."
    fail=1
  elif [ "$lines" -gt 400 ]; then
    echo "NOTE [state]: $GATE_SELFTEST_STATE_FILE is $lines lines with work still active. Move operation"
    echo "              detail into docs/<OPERATION>.md and keep one status line and a"
    echo "              pointer here; harvest as you go, so the prune is small later."
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
build_test_cmd="{{BUILD_TEST_COMMAND}}"
[ -n "${GATE_BUILD_CMD_OVERRIDE:-}" ] && build_test_cmd="$GATE_BUILD_CMD_OVERRIDE"
# Tested with its whitespace stripped: an all-blank command reaches `sh -c` as a no-op that
# exits 0, which is a green gate with no build — the unconfigured case wearing spaces.
case "$(printf '%s' "$build_test_cmd" | tr -d '[:space:]')" in
  *"{{"*|"")
    echo "FAIL [build]: no build/test command is configured in scripts/check.sh. Set one —"
    echo "              use 'true' explicitly if this project genuinely has nothing to run,"
    echo "              so that the choice is visible in the diff instead of implied."
    fail=1 ;;
  *)
    sh -c "$build_test_cmd" || fail=1 ;;
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

if [ "$fail" -eq 0 ]; then echo "CHECK: PASS"; else echo "CHECK: FAIL"; exit 1; fi
