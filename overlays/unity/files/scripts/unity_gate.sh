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
# Usage: unity_gate.sh [--self-test]
#   UNITY_PATH   the editor executable, if `unity` is not on PATH
#   UNITY_PROJECT the project folder (default: unity)
#
# CLOSE THE EDITOR FIRST. Unity cannot open a project in batch mode while an Editor has the
# same project open (Unity Manual, "Editor command line arguments").
set -u
# Resolve this script's own path BEFORE the cd below: the self-test re-invokes it, and a
# relative $0 stops pointing at the script once the working directory has changed.
self="$(CDPATH= cd -- "$(dirname "$0")" && pwd)/$(basename "$0")"
CDPATH= cd -- "$(dirname "$0")/.."

project_dir="${UNITY_PROJECT:-unity}"
unity_bin="${UNITY_PATH:-unity}"
fail=0

run_gate() {
  if ! command -v "$unity_bin" >/dev/null 2>&1; then
    echo "FAIL [unity]: Unity not found. Set UNITY_PATH to the editor executable."
    return 1
  fi

  mkdir -p "$project_dir/Logs"

  # Unity's manual does not say which directory a relative -logFile or -testResults path is
  # resolved against (it says only that -projectPath may be relative to the current working
  # directory), so pass absolute paths and treat a missing results file as FAIL: a gate that
  # trusts the exit code can report PASS for a run whose results landed somewhere nobody
  # looks. Paths are translated when a Windows .exe is driven from a POSIX shell.
  # (docs/GOTCHAS.md)
  proj=$(CDPATH= cd -- "$project_dir" && pwd)
  logs="$proj/Logs"
  case "$unity_bin" in
    *.exe)
      if ! command -v wslpath >/dev/null 2>&1; then
        echo "FAIL [unity]: a Windows Unity.exe needs wslpath to translate paths."
        return 1
      fi
      proj=$(wslpath -w "$proj" 2>/dev/null || printf '%s\n' "$proj")
      logs=$(wslpath -w "$logs" 2>/dev/null || printf '%s\n' "$logs")
      ;;
  esac

  cases=0
  for platform in EditMode PlayMode; do
    printf '%s\n' "unity: running $platform tests..."
    results="$project_dir/Logs/test-results-$platform.xml"
    rm -f "$results"
    # -nographics is the documented headless flag (Unity does not initialise the graphics
    # device); `-logFile -` sends the log to the console, which -nographics would otherwise
    # leave off. Unity's manual does not say whether PlayMode tests run under -nographics:
    # drop it if they fail to start. -quit is NOT added: the manual says that with -runTests
    # it makes the Editor quit before in-progress tests complete.
    "$unity_bin" -batchmode -nographics -runTests -projectPath "$proj" \
      -testPlatform "$platform" \
      -testResults "$logs/test-results-$platform.xml" \
      -logFile - || {
        printf '%s\n' "FAIL [unity]: $platform tests failed — see $results"
        fail=1
      }

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
    total=$(grep -c "<test-case " "$results" 2>/dev/null)
    skipped=$(grep -o 'result="Skipped"' "$results" 2>/dev/null | grep -c .)
    failed=$(grep -o 'result="Failed"' "$results" 2>/dev/null | grep -c .)
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
    fi
    cases=$((cases + executed))
  done

  # Zero tests on ONE platform is normal early on. Zero across BOTH means the tests stopped
  # running and nobody noticed, which is exactly what this catches.
  if [ "$cases" -eq 0 ]; then
    echo "FAIL [unity]: no test executed on either platform — check the test assembly and its constraints."
    fail=1
  fi

  return "$fail"
}

# --- negative test --------------------------------------------------------------------
# The interesting failure is not "Unity returned an error" — it is "Unity returned SUCCESS
# and produced nothing", which is how this gate silently passed for weeks once. That case
# needs no Unity install to reproduce: a stub that exits 0 and writes no results file.
self_test() {
  st_fail=0
  d=$(mktemp -d)

  # case: a run that exits clean and writes nothing at all. The self-test runs in a
  # temporary directory per run, as test frameworks do (pytest tmp_path:
  # docs.pytest.org/en/stable/how-to/tmp_path.html), and never touches the real project.
  make_stub() { printf '%s\n' '#!/bin/sh' "$2" > "$1"; chmod +x "$1"; }
  probe() {
    label="$1"; want="$2"; stub="$3"
    # A THROWAWAY project dir, not the real one: run_gate mkdirs Logs/ and the stubs write
    # result files, and an earlier version left that litter in the project tree.
    out=$(UNITY_PATH="$stub" UNITY_PROJECT="$d/proj" sh "$self" 2>&1)
    if [ $? -eq 0 ]; then
      printf '%s\n' "  FAIL — $label: the gate PASSED."
      st_fail=1
      return
    fi
    case "$out" in
      *"$want"*) printf '%s\n' "  ok   — $label" ;;
      *) printf '%s\n' "  FAIL — $label: it failed, but not for the expected reason ($want):"
         printf '%s\n' "$out" | tail -4 | sed 's/^/         /'
         st_fail=1 ;;
    esac
  }

  make_stub "$d/silent" 'exit 0'
  probe "rejects a clean exit that wrote no results file" "no results file" "$d/silent"

  # case: a file exists but is not an NUnit document — the shape a naive substring count
  # would happily accept.
  cat > "$d/fake" <<'STUB'
#!/bin/sh
for a in "$@"; do case "$prev" in -testResults) printf '<test-case />\n' > "$a";; esac; prev="$a"; done
exit 0
STUB
  chmod +x "$d/fake"
  probe "rejects a results file that is not an NUnit document" "not an NUnit result document" "$d/fake"

  # case: a well-formed document in which every test was SKIPPED. Skipped is not executed,
  # and this is what a misconfigured test assembly actually produces.
  cat > "$d/skipped" <<'STUB'
#!/bin/sh
for a in "$@"; do
  case "$prev" in
    -testResults) printf '<test-run><test-case name="a" result="Skipped" /></test-run>\n' > "$a";;
  esac
  prev="$a"
done
exit 0
STUB
  chmod +x "$d/skipped"
  probe "rejects a run in which every test was skipped" "no test executed" "$d/skipped"

  rm -rf "$d"
  if [ "$st_fail" -eq 0 ]; then
    echo "SELF-TEST: PASS — the gate rejects each successful-looking run with no real evidence."
    return 0
  fi
  echo "SELF-TEST: FAIL — the gate accepts a run that proved nothing."
  return 1
}

case "${1:-}" in
  "")          ;;
  --self-test) self_test; exit $? ;;
  *)           echo "usage: unity_gate.sh [--self-test]"; exit 2 ;;
esac

if run_gate; then
  echo "UNITY GATE: PASS"
else
  echo "UNITY GATE: FAIL"
  exit 1
fi
