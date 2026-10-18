#!/usr/bin/env sh
# Unity Test Framework gate — EditMode + PlayMode in batchmode.
#
# Separate from scripts/check.sh on purpose: that one runs on every commit and must stay
# fast, and a batchmode run's cost scales with project size (editor start and import). Run
# this when Unity-side work is finished, and on a schedule if CI can host it.
#
# Unity documents no common exit code contract for the components under test, so the verdict
# comes from the result file, never from the exit code. (Unity Test Framework, "Running tests
# from the command line"; the other flags below: Unity Manual, "Editor command line
# arguments"; running both modes together is also GameCI's default.)
#
# Its negative tests live in the kit's tests/test_unity_gate.py: stub editors that exit 0 with no
# results file, with a file that is not an NUnit document, and with every test skipped.
#
# Usage: unity_gate.sh
#   UNITY_PATH    the editor executable, if `unity` is not on PATH (docs/UNITY_SETUP.md §5)
#   UNITY_PROJECT the project folder (default: unity)
#
# CLOSE THE EDITOR FIRST. Unity cannot open a project in batch mode while an Editor has the
# same project open (Unity Manual, "Editor command line arguments").
set -u
CDPATH= cd -- "$(dirname "$0")/.."

project_dir="${UNITY_PROJECT:-unity}"
unity_bin="${UNITY_PATH:-unity}"
fail=0

run_gate() {
  if ! command -v "$unity_bin" >/dev/null 2>&1; then
    echo "FAIL [unity]: Unity not found. Set UNITY_PATH to the editor executable."
    return 1
  fi
  # A folder without ProjectSettings is no Unity project: Logs was once made in a folder that
  # did not exist, and the editor pointed at it (#175).
  if [ ! -d "$project_dir/ProjectSettings" ]; then
    printf '%s\n' "FAIL [unity]: $project_dir is not a Unity project (no ProjectSettings folder). Set UNITY_PROJECT to the project folder."
    return 1
  fi

  mkdir -p "$project_dir/Logs"

  # Unity's manual does not say which directory a relative -logFile or -testResults path is
  # resolved against (it says only that -projectPath may be relative to the current working
  # directory), so pass absolute paths and treat a missing results file as FAIL: a gate that
  # trusts the exit code can report PASS for a run whose results landed somewhere nobody
  # looks. Paths are translated when a Windows editor is driven from a POSIX shell.
  # (docs/GOTCHAS.md) On Git for Windows, MSYS2 and Cygwin the editor is a Windows program
  # however it is spelled (Unity.exe or Unity): cygpath, as the kit's other scripts do, and
  # only where the host's own uname says so, as in check.sh. WSL runs a Windows editor only by
  # its .exe name, and translates with wslpath. wslpath alone refused Unity.exe on Git Bash (#175).
  proj=$(CDPATH= cd -- "$project_dir" && pwd)
  logs="$proj/Logs"
  case "$(uname -s 2>/dev/null)" in
    MSYS*|MINGW*|CYGWIN*)
      { proj=$(cygpath -m "$proj") && logs=$(cygpath -m "$logs"); } || {
        printf '%s\n' "FAIL [unity]: cygpath cannot convert $proj for the Windows editor."
        return 1
      } ;;
    *) case "$unity_bin" in
         *.exe)
           if ! command -v wslpath >/dev/null 2>&1; then
             echo "FAIL [unity]: a Windows Unity.exe needs wslpath to translate paths."
             return 1
           fi
           proj=$(wslpath -w "$proj" 2>/dev/null || printf '%s\n' "$proj")
           logs=$(wslpath -w "$logs" 2>/dev/null || printf '%s\n' "$logs")
           ;;
       esac ;;
  esac

  cases=0
  for platform in EditMode PlayMode; do
    printf '%s\n' "unity: running $platform tests..."
    results="$project_dir/Logs/test-results-$platform.xml"
    errors="$project_dir/Logs/unity-$platform.stderr"
    rm -f "$results"
    # -nographics is the documented headless flag (Unity does not initialise the graphics
    # device); `-logFile -` sends the log to the console, which -nographics would otherwise
    # leave off. Unity's manual does not say whether PlayMode tests run under -nographics:
    # drop it if they fail to start. -quit is NOT added: the manual says that with -runTests
    # it makes the Editor quit before in-progress tests complete.
    # stderr is kept, then shown: Unity's separate command-line tool, also named `unity` and
    # first on PATH on some machines, answers "error: unknown option '-batchmode'" there, which
    # is the wrong program, not failed tests (#175). Read after the run, not probed before it:
    # the editor opens a window on a probe, and a wrapper script cannot be told from the
    # editor by its path.
    "$unity_bin" -batchmode -nographics -runTests -projectPath "$proj" \
      -testPlatform "$platform" \
      -testResults "$logs/test-results-$platform.xml" \
      -logFile - 2>"$errors"
    code=$?
    cat "$errors" >&2
    if [ "$code" -ne 0 ]; then
      if grep -q "unknown option '-batchmode'" "$errors"; then
        printf '%s\n' "FAIL [unity]: $unity_bin is not the Unity Editor (it rejected -batchmode; Unity's separate CLI is also named unity). Set UNITY_PATH to the editor executable (docs/UNITY_SETUP.md §5)."
        return 1
      fi
      printf '%s\n' "FAIL [unity]: $platform tests failed — see $results"
      fail=1
    fi

    # A gate must not pass on ABSENT evidence. A run that executed nothing can still exit 0
    # (the exit code is not a contract, see the header), so the results file has to exist,
    # be real, and be counted properly.
    if [ ! -f "$results" ]; then
      printf '%s\n' "FAIL [unity]: $platform produced no results file at $results — the run proved nothing."
      fail=1
      continue
    fi

    # It must actually look like an NUnit result document. A stub that writes any file
    # containing the substring we count would otherwise satisfy this gate without running
    # a single test.
    if ! grep -q "<test-run\|<test-results" "$results"; then
      printf '%s\n' "FAIL [unity]: $results is not an NUnit result document. Refusing to count it."
      fail=1
      continue
    fi

    # `grep -c` prints 0 AND returns 1 when nothing matches, so a `|| echo 0` fallback
    # appends a SECOND zero and the arithmetic below dies with "Illegal number" — before
    # ever reaching the zero-test diagnostic. Take the count and validate it instead.
    # Count only <test-case> tags: NUnit also puts result="Skipped" or "Failed" on the
    # enclosing <test-suite> and <test-run>, and counting those drove `executed` negative,
    # past the zero-test check below (#166). The lines are joined first: a tag may carry its
    # result= on a later line.
    tags=$(tr '\r\n\t' '   ' < "$results" | grep -o '<test-case [^>]*' 2>/dev/null)
    total=$(printf '%s\n' "$tags" | grep -c '<test-case ')
    skipped=$(printf '%s\n' "$tags" | grep -c 'result="Skipped"')
    failed=$(printf '%s\n' "$tags" | grep -c 'result="Failed"')
    case "$total$skipped$failed" in
      *[!0-9]*|"") printf '%s\n' "FAIL [unity]: could not count test cases in $results."; fail=1; continue ;;
    esac
    executed=$((total - skipped))
    printf '%s\n' "unity: $platform — $total case(s), $skipped skipped, $failed failed, $executed executed."

    # Skipped is not executed. An all-skipped run is the absent-evidence case wearing a
    # results file, and it is what a misconfigured test assembly produces.
    if [ "$failed" -gt 0 ]; then
      printf '%s\n' "FAIL [unity]: $platform reports $failed failed test(s) — see $results"
      fail=1
    elif grep -q 'result="Failed"' "$results"; then
      # Every case passed but a suite or the run failed, such as a OneTimeTearDown that threw.
      printf '%s\n' "FAIL [unity]: $platform reports a failed suite or run — see $results"
      fail=1
    fi
    cases=$((cases + executed))
  done

  # Zero tests on ONE platform is normal early on. Zero across BOTH means the tests stopped
  # running and nobody noticed, which is exactly what this catches.
  if [ "$cases" -le 0 ]; then
    echo "FAIL [unity]: no test executed on either platform — check the test assembly and its constraints."
    fail=1
  fi

  return "$fail"
}

case "${1:-}" in
  "") ;;
  *)  echo "usage: unity_gate.sh"; exit 2 ;;
esac

if run_gate; then
  echo "UNITY GATE: PASS"
else
  echo "UNITY GATE: FAIL"
  exit 1
fi
