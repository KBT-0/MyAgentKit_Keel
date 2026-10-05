#!/usr/bin/env sh
# Unity Test Framework gate — EditMode + PlayMode in batchmode.
#
# Separate from scripts/check.sh on purpose: that one runs on every commit and must stay
# fast, and a batchmode run takes minutes per platform. Run this when Unity-side work is
# finished, and on a schedule if CI can host it.
#
# Usage: unity_gate.sh [--self-test]
#   UNITY_PATH   the editor executable, if `unity` is not on PATH
#   UNITY_PROJECT the project folder (default: unity)
#
# CLOSE THE EDITOR FIRST. Batchmode cannot open a project that already holds a lock file.
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

  mkdir -p "$project_dir/Logs"

  # Unity resolves a relative -testResults path against ITS OWN working directory, not this
  # shell's. The file then lands somewhere nobody looks, Unity still exits 0, and a gate
  # that trusts the exit code reports PASS for a run that executed nothing. So: absolute
  # paths, translated when a Windows .exe is driven from a POSIX shell. (docs/GOTCHAS.md)
  proj=$(CDPATH= cd -- "$project_dir" && pwd)
  logs="$proj/Logs"
  case "$unity_bin" in
    *.exe)
      if ! command -v wslpath >/dev/null 2>&1; then
        echo "FAIL [unity]: a Windows Unity.exe needs wslpath to translate paths."
        return 1
      fi
      proj=$(wslpath -w "$proj" 2>/dev/null || echo "$proj")
      logs=$(wslpath -w "$logs" 2>/dev/null || echo "$logs")
      ;;
  esac

  cases=0
  for platform in EditMode PlayMode; do
    echo "unity: running $platform tests..."
    results="$project_dir/Logs/test-results-$platform.xml"
    rm -f "$results"
    # -nographics is required on a headless machine; drop it if a test needs a real device.
    "$unity_bin" -batchmode -nographics -runTests -projectPath "$proj" \
      -testPlatform "$platform" \
      -testResults "$logs/test-results-$platform.xml" \
      -logFile - || {
        echo "FAIL [unity]: $platform tests failed — see $results"
        fail=1
      }

    # A gate must not pass on ABSENT evidence. Unity exits 0 for a run that executed
    # nothing, so the results file has to exist, be real, and be counted properly.
    if [ ! -f "$results" ]; then
      echo "FAIL [unity]: $platform produced no results file at $results — the run proved nothing."
      fail=1
      continue
    fi

    # It must actually look like an NUnit result document. A stub that writes any file
    # containing the substring we count would otherwise satisfy this gate without running
    # a single test.
    if ! grep -q "<test-run\|<test-results" "$results"; then
      echo "FAIL [unity]: $results is not an NUnit result document. Refusing to count it."
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
      *[!0-9]*|"") echo "FAIL [unity]: could not count test cases in $results."; fail=1; continue ;;
    esac
    executed=$((total - skipped))
    echo "unity: $platform — $total case(s), $skipped skipped, $failed failed, $executed executed."

    # Skipped is not executed. An all-skipped run is the absent-evidence case wearing a
    # results file, and it is what a misconfigured test assembly produces.
    if [ "$failed" -gt 0 ]; then
      echo "FAIL [unity]: $platform reports $failed failed test(s) — see $results"
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

  # case: a run that exits clean and writes nothing at all.
  make_stub() { printf '%s\n' '#!/bin/sh' "$2" > "$1"; chmod +x "$1"; }
  probe() {
    label="$1"; want="$2"; stub="$3"
    # A THROWAWAY project dir, not the real one: run_gate mkdirs Logs/ and the stubs write
    # result files, and an earlier version left that litter in the project tree.
    out=$(UNITY_PATH="$stub" UNITY_PROJECT="$d/proj" sh "$0" 2>&1)
    if [ $? -eq 0 ]; then
      echo "  FAIL — $label: the gate PASSED."
      st_fail=1
      return
    fi
    case "$out" in
      *"$want"*) echo "  ok   — $label" ;;
      *) echo "  FAIL — $label: it failed, but not for the expected reason ($want):"
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
