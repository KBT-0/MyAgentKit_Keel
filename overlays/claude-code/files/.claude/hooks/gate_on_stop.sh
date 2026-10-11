#!/usr/bin/env sh
# Stop hook (one tool only): if the turn left the gated paths dirty, run the project gate
# before the agent is allowed to finish. Early feedback, not the rule — .githooks/pre-commit
# is the gate that actually holds, for every tool.
#
# Costs nothing when it passes: no model tokens, a silent exit. On failure it returns the
# gate's whole output (exit 2 = blocking), which is the only case where the agent spends
# tokens on it. Only the last 20 lines once went back, and the gate prints a build failure's
# diagnostic chain before a long tail: the agent saw the tail and not where it started.
set -u

input=$(cat)

# The tool sets stop_hook_active when the turn was already continued by this hook. Without
# this guard the session loops forever.
case "$input" in
  *'"stop_hook_active":true'*|*'"stop_hook_active": true'*) exit 0 ;;
esac

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
CDPATH= cd -- "$root" || exit 0

# Only work in these paths needs the gate; documentation and tooling turns skip it, which is
# why the hook is cheap in practice. Untracked files count — `git status` reports them where
# `git diff` would not.
gated_paths="{{GATED_PATHS}}"
gated_pattern="{{GATED_FILE_PATTERN}}"

# shellcheck disable=SC2086
if [ -z "$(git status --porcelain -- $gated_paths 2>/dev/null | grep -E "$gated_pattern" || true)" ]; then
  exit 0
fi

# A self-test may inject files into the gated paths while it holds this checkout's gate lock.
# File names prove nothing (a tool's .selftest.log, a tracked file); the evidence is
# check-selftest beside the lock: check.sh --self-test writes its shell pid and lock token
# there and removes it when it ends. The shell must still be alive: build descendants can
# hold the lock after the self-test dies. A matching token and a held lock (75) then let the
# hook step aside; a free lock runs the gate now.
lock=$(git rev-parse --git-path check.lock 2>/dev/null)
selftest_live() {
  IFS=' ' read -r pid marker extra 2>/dev/null < "${lock%.lock}-selftest" || return 1
  case "$pid" in ''|0*|*[!0-9]*) return 1 ;; esac
  [ -n "$marker" ] && [ -z "$extra" ] && kill -0 "$pid" 2>/dev/null &&
    [ "$marker" = "$(cat "$lock" 2>/dev/null)" ]
}
gate_wait="${GATE_LOCK_WAIT:-500}"
! selftest_live || gate_wait=0

# No result caching, on purpose: a cache that says PASS for a tree that has since changed is
# worse than a ten-second gate.
# The gate waits for another gate run in this checkout. The wait is bounded below the hook's
# timeout (600 s in settings.json): a killed hook returns nothing, and its gate would still
# start later. Exit 75 is that bound running out — the gate did not run, it did not fail.
# The bound covers only the wait: a gate that takes longer than the remaining 100 s still
# hits the hook timeout, so keep the hook's gate short (the full self-test is not for hooks).
out=$(GATE_LOCK_WAIT="$gate_wait" ./scripts/check.sh 2>&1)
rc=$?
[ "$rc" -eq 0 ] && exit 0
if [ "$rc" -eq 75 ] && [ "$gate_wait" = 0 ] && selftest_live; then
  echo "NOTE [Stop hook]: skipping the gate while ./scripts/check.sh --self-test holds this checkout's lock." >&2
  exit 0
fi

printf '%s\n' "$out" >&2
echo "" >&2
if [ "$rc" -eq 75 ]; then
  echo "GATE DID NOT RUN (Stop hook): another gate run held this checkout's lock past the wait." >&2
  echo "Run ./scripts/check.sh yourself before finishing; do not report the gate as passing or failing." >&2
  exit 2
fi
echo "GATE FAILED (Stop hook): the gated paths have uncommitted changes and ./scripts/check.sh is red." >&2
echo "Fix the cause before finishing the task (AGENTS.md). Do not report the gate as passing." >&2
exit 2
