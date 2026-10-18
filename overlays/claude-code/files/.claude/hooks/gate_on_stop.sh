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
# The tool sets stop_hook_active when this stop continues a turn a Stop hook blocked: this
# one, or another in the group (plain_report.py). Skipping every such stop let a fix made
# after a red gate end the turn unchecked (#208); it is used only as the loop guard below.
continued=0
if printf '%s' "$input" | grep -qE '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then continued=1; fi

# Claude Code runs a hook in the current directory, which follows a `cd`; CLAUDE_PROJECT_DIR
# stays at the session's root (code.claude.com/docs/en/hooks).
root=$(git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --show-toplevel 2>/dev/null) || exit 0
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

# The last result, kept per tree: Stop fires after every reply, and a dirty file once ran a
# 217 s gate on each short answer (#81). The tree is named by its content: the index, the
# unstaged diff and every untracked, not ignored file with its content, so any edit runs the
# gate again. The state file in the git directory holds "<result> <tree>", then a failed
# run's output. A tree that cannot be named (a quoted or unreadable untracked path) is
# never remembered: every stop runs the gate.
# ponytail: ignored files and the environment are not in the tree's name; a PASS stays until
# the tree changes. The commit hook runs the gate again, so the commit stays gated.
state=$(git rev-parse --git-path kit-stop-gate 2>/dev/null) || state=""
tree_name() {
  [ -n "$state" ] || return 1
  untracked=$(git -c core.quotePath=false ls-files --others --exclude-standard) &&
    { git ls-files --stage && git diff --binary --no-ext-diff --no-textconv --no-color &&
      printf '%s\n' "$untracked" &&
      if [ -n "$untracked" ]; then printf '%s\n' "$untracked" | git hash-object --stdin-paths; fi
    } > "$state.tree" && git hash-object -- "$state.tree"
}
failed() {
  echo "" >&2
  echo "GATE FAILED (Stop hook): the gated paths have uncommitted changes and ./scripts/check.sh is red$1." >&2
  echo "Fix the cause before finishing the task (AGENTS.md). Do not report the gate as passing." >&2
  exit 2
}
now=$(tree_name 2>/dev/null) || now=""
last="" last_tree=""
[ -z "$now" ] || IFS=' ' read -r last last_tree 2>/dev/null < "$state" || true
if [ -n "$now" ] && [ "$now" = "$last_tree" ]; then
  [ "$last" != pass ] || exit 0
  # The loop guard: a turn this hook continued, on the tree it already judged, ends. The
  # vendor's cap of 8 continuations resets at every tool call, so it is only a backstop.
  [ "$continued" -eq 0 ] || exit 0
  # A new turn on a tree that failed: blocked again with that run's output, without a re-run.
  if [ "$last" = fail ]; then
    tail -n +2 -- "$state" >&2
    failed " (this tree's last run, above; it has not changed since)"
  fi
elif [ -z "$now" ] && [ "$continued" -eq 1 ]; then
  exit 0  # Nothing to compare: the stop a block continued ends, or the session would loop.
fi

gate_wait="${GATE_LOCK_WAIT:-500}"

# The gate's opt-in build cache (build_cache_inputs in scripts/check.sh) can also skip the
# build of a run, only one that passed on the same inputs, and the gate then says "cached PASS".
# The gate waits for another gate run in this checkout. The wait is bounded below the hook's
# timeout (600 s in settings.json): a killed hook returns nothing, and its gate would still
# start later. Exit 75 is that bound running out — the gate did not run, it did not fail.
# The bound covers only the wait: a gate that takes longer than the remaining 100 s still
# hits the hook timeout, so keep the hook's gate short.
out=$(GATE_LOCK_WAIT="$gate_wait" ./scripts/check.sh 2>&1)
rc=$?
# Kept under the tree as the run left it. A PASS counts only for a tree that did not change
# while the gate ran; a failure or a gate that did not run counts for the loop guard alone.
after=$(tree_name 2>/dev/null) || after=""
case $rc in 0) result=pass ;; 75) result=busy ;; *) result=fail ;; esac
[ "$rc" -ne 0 ] || [ "$after" = "$now" ] || result=ran
if [ -n "$after" ]; then
  { printf '%s %s\n' "$result" "$after"; [ "$result" != fail ] || printf '%s\n' "$out"; } > "$state"
fi
[ "$rc" -eq 0 ] && exit 0

printf '%s\n' "$out" >&2
if [ "$rc" -eq 75 ]; then
  echo "" >&2
  echo "GATE DID NOT RUN (Stop hook): another gate run held this checkout's lock past the wait." >&2
  echo "Run ./scripts/check.sh yourself before finishing; do not report the gate as passing or failing." >&2
  exit 2
fi
failed ""
