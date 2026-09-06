#!/usr/bin/env sh
# {{PROJECT_NAME}} cross-model review wrapper.
#
# Runs a SECOND model over the current change set in a read-only sandbox, archives the raw
# output under docs/reviews/ together with the configuration that produced it, and prints
# it. The gate itself is docs/REVIEW_GATE.md; this script only collects the evidence.
#
# Usage: review.sh [--uncommitted | --base <ref> | --commit <sha>] [--reviewer codex|claude]
#        review.sh --self-test
#   default scope     --uncommitted (staged + unstaged + untracked) — the pre-commit case.
#   default reviewer  the one configured below during setup.
#
# THE KIT TAKES NO POSITION ON WHICH MODEL WRITES AND WHICH REVIEWS. The rule is that the
# AUTHOR never reviews its own patch and the REVIEWER is a different model — not that a
# particular vendor holds a particular role. Both directions run through this one script and
# publish the SAME evidence format, so records stay comparable when the roles swap.
#
# Read-only is enforced HERE, not assumed of the CLI: the scope forms above and --reviewer
# are the ONLY accepted arguments and the sandbox is pinned. There is deliberately no
# pass-through for further flags — an agent must not be able to talk this script into a
# write-capable run. "Please be careful" is not a guarantee when the caller is a model.
#
# The result is INPUT to a review decision the CALLING agent owns, never a verdict to relay
# verbatim (docs/REVIEW_GATE.md).
#
#   REVIEW_REVIEWER      override the configured reviewer for one run (codex | claude)
#   REVIEW_CODEX_MODEL   override the pinned Codex model for one run
#   REVIEW_CLAUDE_MODEL  override the pinned Claude model for one run
#   REVIEW_EFFORT    reasoning effort             (default: high)
#   REVIEW_CLI_BIN   the Codex binary             (default: codex)
#   CLAUDE_CLI_BIN   the Claude binary            (default: claude)
set -u
script_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
cd "${REVIEW_REPO_ROOT:-$script_dir/..}" || exit 2

# ---------------------------------------------------------------------------------------
# PROJECT-OWNED CONFIGURATION. Set during setup; sync-kit.sh never overwrites this file.
#
# Both models are PINNED BY NAME, in both directions. An unpinned run records the reviewing
# CLI's own default, which is a moving target: two records made a month apart then claim the
# same provenance while naming no model that can be compared or reproduced. Codex emits no
# model identity in its JSON output, so there is nothing to fall back on and nothing to
# attest against — the pin is the only record there is, and an empty pin is a hard stop.
#
# BOTH ship empty on purpose. A kit that pre-filled one side would be quietly naming which
# vendor it expected in that role, and the setup interview would stop asking.
#
# The pins are per-reviewer rather than one shared REVIEW_MODEL: a single override would
# hand a Codex model id to Claude the moment the roles swapped, which is the exact failure
# this role-neutral wrapper exists to prevent.
DEFAULT_REVIEWER="claude"
CODEX_MODEL=""
CLAUDE_MODEL=""
# ---------------------------------------------------------------------------------------

usage() {
  echo "usage: review.sh [--uncommitted | --base <ref> | --commit <sha>] [--reviewer codex|claude]"
  echo "       review.sh --self-test"
  exit 2
}
die() { echo "FAIL [review]: $1"; exit 2; }

if [ "${1:-}" = "--self-test" ]; then
  [ $# -eq 1 ] || usage
  [ -s "$script_dir/test_claude_bridge.py" ] || die "review self-test file is missing or empty"
  test_log=$(mktemp) || die "cannot create self-test log"
  trap 'rm -f "$test_log"' EXIT HUP INT TERM
  if ! python3 -B "$script_dir/test_claude_bridge.py" > "$test_log" 2>&1; then
    cat "$test_log"
    die "review self-tests failed"
  fi
  cat "$test_log"
  grep -qx 'REVIEW SELF-TEST: PASS' "$test_log" || die "review self-tests produced no completion evidence"
  exit 0
fi

scope_flag="--uncommitted"
scope_arg=""
scope_seen=0
reviewer="${REVIEW_REVIEWER:-$DEFAULT_REVIEWER}"
while [ $# -gt 0 ]; do
  case "$1" in
    --uncommitted)
      [ "$scope_seen" -eq 0 ] || usage
      scope_seen=1; scope_flag="--uncommitted"; scope_arg=""; shift ;;
    --base|--commit)
      [ "$scope_seen" -eq 0 ] || usage
      [ $# -ge 2 ] || usage
      scope_seen=1; scope_flag="$1"; scope_arg="$2"
      case "$scope_arg" in -*|*" "*|"") usage ;; esac
      shift 2 ;;
    --reviewer)
      [ $# -ge 2 ] || usage
      reviewer="$2"; shift 2 ;;
    *) usage ;;
  esac
done

# The reviewer is matched against a closed list rather than passed through. A value that
# reaches a command line unchecked is how a scope flag becomes an argument injection.
case "$reviewer" in
  codex|claude) ;;
  *) die "--reviewer must be codex or claude (got '$reviewer')" ;;
esac

set -- "$scope_flag"
[ -n "$scope_arg" ] && set -- "$scope_flag" "$scope_arg"

# Reviewing CLIs are commonly per-user installs missing from a non-login shell's PATH.
[ -x "$HOME/.local/bin/codex" ] && { PATH="$HOME/.local/bin:$PATH"; export PATH; }

# The dispatcher makes at most one failover to the other configured pin. Each adapter
# retains its own evidence and usage; a completed Reject never triggers another call.
exec python3 -B "$script_dir/review_dispatch.py" --repo "$PWD" --reviewer "$reviewer" \
  --claude-model "${REVIEW_CLAUDE_MODEL:-$CLAUDE_MODEL}" \
  --codex-model "${REVIEW_CODEX_MODEL:-$CODEX_MODEL}" --effort "${REVIEW_EFFORT:-high}" "$@"
