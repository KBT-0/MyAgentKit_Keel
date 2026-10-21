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
# `git diff` would not, each by itself: without --untracked-files=all a new directory is one
# `?? src/pkg/` line, which the pattern does not match. -z: plain porcelain quotes a name with
# a space or a non-ASCII letter, and the closing quote broke the pattern's `$` (#174).
gated_paths="{{GATED_PATHS}}"
gated_pattern="{{GATED_FILE_PATTERN}}"

# shellcheck disable=SC2086
if [ -z "$(git status --porcelain -z --untracked-files=all -- $gated_paths 2>/dev/null | tr '\0' '\n' | grep -E "$gated_pattern" || true)" ]; then
  exit 0
fi

# The last run, kept by content: Stop fires after every reply, and a dirty file once ran a
# 217 s gate on each short answer (#81). Two names, each a hash:
#   code  HEAD, the index, the unstaged diff, and the untracked files under the gated paths
#         that the gated pattern matches, with their content;
#   tree  the code plus every other untracked, not ignored file, with its content.
# A new turn skips the gate only on the tree that last passed. A failure is never replayed:
# its cause can lie outside the names (a flaky test, a tool installed since). A stop that
# continues a blocked turn (stop_hook_active) runs the gate only when the code changed since
# the last run: that is the loop guard, and a background process that keeps writing a log
# cannot defeat it (#208). The vendor's cap of 8 continuations resets at every tool call, so
# it is only a backstop.
# A tree that cannot be named ("-") is never remembered: every new turn runs the gate. That
# is a tree with a submodule (what changes inside one is not in the diff) or with an
# untracked path git quotes or cannot hash (a nested repository). Its code is still named,
# so a continued stop after a fix to the gated code still runs the gate (#208); edits inside
# a submodule do not change the code, so they cannot loop. With no code name, it ends.
# The state file in the git directory holds "<result> <code> <tree>".
# ponytail: ignored files and the environment are not in the names; a PASS stays until the
# tree changes. The commit hook runs the gate again, so the commit stays gated.
state=$(git rev-parse --git-path kit-stop-gate 2>/dev/null) || state=""
hashed() { printf '%s\n' "$1"; [ -z "$1" ] || printf '%s\n' "$1" | git hash-object --stdin-paths; }
names() {
  [ -n "$state" ] || return 1
  # shellcheck disable=SC2086
  code_untracked=$(git -c core.quotePath=false ls-files --others --exclude-standard -- $gated_paths | grep -E "$gated_pattern")
  { git rev-parse -q --verify HEAD || echo none; } > "$state.tree" &&
    git ls-files --stage >> "$state.tree" &&
    git diff --binary --no-ext-diff --no-textconv --no-color >> "$state.tree" &&
    hashed "$code_untracked" >> "$state.tree" && code=$(git hash-object -- "$state.tree") || return 1
  tree=-
  if ! git ls-files --stage | grep -q '^160000 ' &&
    untracked=$(git -c core.quotePath=false ls-files --others --exclude-standard) &&
    hashed "$untracked" >> "$state.tree"; then tree=$(git hash-object -- "$state.tree") || tree=-; fi
  printf '%s %s\n' "$code" "$tree"
}
now=$(names 2>/dev/null) || now=""
last="" last_code="" last_tree=""
[ -z "$now" ] || IFS=' ' read -r last last_code last_tree 2>/dev/null < "$state" || true
if [ -z "$now" ]; then
  [ "$continued" -eq 0 ] || exit 0
elif [ "$continued" -eq 1 ]; then
  [ "${now% *}" != "$last_code" ] || exit 0
elif [ "$last" = pass ] && [ "${now#* }" != - ] && [ "${now#* }" = "$last_tree" ]; then
  exit 0
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
# Kept under the names the run left. A PASS counts only for a tree that did not change while
# the gate ran; any other result counts for the loop guard alone.
after=$(names 2>/dev/null) || after=""
case $rc in 0) result=pass ;; 75) result=busy ;; *) result=fail ;; esac
[ "$rc" -ne 0 ] || [ "$after" = "$now" ] || result=ran
[ -z "$after" ] || printf '%s %s\n' "$result" "$after" > "$state"
[ "$rc" -eq 0 ] && exit 0

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
