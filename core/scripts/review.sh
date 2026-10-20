#!/usr/bin/env sh
# {{PROJECT_NAME}} cross-model review wrapper.
#
# Runs a SECOND model over the current change set in a throwaway copy of the checkout, archives
# the raw output under docs/reviews/ together with the configuration that produced it, and
# prints it. The gate itself is docs/REVIEW_GATE.md; this script only collects the evidence.
#
# Usage: review.sh [--uncommitted | --base <ref> | --commit <sha>] [--reviewer codex|claude]
#                  [--fallback] [--backend NAME] [--allow-secret-file PATH]...
#                  [--kit-verified [--kit DIR]]
#        review.sh --self-test
#   default scope     --uncommitted (staged + unstaged + untracked) — the pre-commit case.
#   default reviewer  the one configured below during setup.
#   --fallback        if the reviewer cannot run (quota, rate limit, timeout, ...), let the OTHER
#                     configured model review once. Off by default: without it a reviewer that
#                     cannot run FAILS the review, it is never replaced. The substitute's
#                     evidence carries a FALLBACK REVIEWER line. A setup fault (authentication,
#                     sandbox, an unsupported CLI) never fails over; a used-up Codex quota
#                     switches to Claude even without it (docs/REVIEW_RUNNING.md).
#   --backend NAME    the Claude reviewer talks to the Anthropic-compatible endpoint that
#                     NAME.env names, with that file's model as the pin, and is recorded as
#                     reviewer claude@NAME (docs/REVIEW_RUNNING.md). The file lives outside the
#                     repository: $MYAGENTKIT_BACKENDS_DIR, else %APPDATA%\myagentkit\backends or
#                     ~/.config/myagentkit/backends; the old .myagentkit/backends/ is read too.
#   --allow-secret-file PATH  review a file that looks like a secret (.env, *.pem, *.key,
#                     .npmrc, .netrc, credentials*) knowingly; without it such a file in scope
#                     stops the review (claude_bridge.secret_like). Repeat it per path.
#   --kit-verified    with --commit and the Claude reviewer: a kit upgrade commit's files that are
#                     equal to the kit's own after git's line-ending normalisation (hash-object
#                     --path, in the kit clone ~/.myagentkit/kit, or --kit DIR) at a released kit
#                     commit are left out of the diff and listed as verified, not reviewed
#                     (docs/REVIEW_RUNNING.md, "Kit upgrade commits").
#
# THE KIT TAKES NO POSITION ON WHICH MODEL WRITES AND WHICH REVIEWS. The rule is that the
# AUTHOR never reviews its own patch and the REVIEWER is a different model — not that a
# particular vendor holds a particular role. Both directions run through this one script and
# publish the SAME evidence format, so records stay comparable when the roles swap.
# (Which direction a family may review is the lead's rule, docs/WORKFLOW.md "cross";
# this script runs every direction.)
#
# THE REVIEWER EXECUTES, NEVER IN THIS REPOSITORY. The adapter this script starts gives each
# reviewer attempt its own throwaway copy (`git archive` of the reviewed commit, of HEAD for a
# range, plus the uncommitted diff) as its working directory, tells it to run anything there,
# and removes the copy when the attempt ends, on a cancel too. The copy is made in the adapter, not here: this script `exec`s the
# adapter, whose signal handling owns a cancel, and the adapters are also called directly.
# Threat model, in short (in full: claude_bridge.py, throwaway_copy):
#   - Defended: what the reviewer runs in its working directory changes only the copy.
#   - Defended: the repository's path is not in the prompt or the reviewer's environment.
#   - Prevented: a shell write outside the copy and the temporary directories, and network
#     use. Codex's workspace-write sandbox blocks both; Claude's Bash runs in Claude Code's
#     own sandbox (macOS, Linux, WSL2), and a host where it cannot start fails the review. On
#     native Windows Claude Code has no sandbox, so the Claude reviewer gets no Bash there.
#   - Detected: a write that reaches the repository anyway fails the review (stale_checkout)
#     when it changes HEAD, the base, the index, a tracked file or an untracked file Git does
#     not ignore.
#   - ACCEPTED LIMIT: a reviewer that finds the repository by its absolute path can read it.
#   - ACCEPTED LIMIT: a reviewer's write that reaches a file Git ignores is not detected.
#   - ACCEPTED LIMIT: a Claude --commit review of a commit that is not HEAD
#     fingerprints the commit alone, so a write that reaches the repository is not detected.
#   - OUT OF SCOPE: a process that changes the tree, the index or the Git configuration
#     between two of this script's reads to hide a change (a filter attribute removed and
#     restored), and hostile files planted by anyone but the owner: either could edit this
#     script instead. An ordinary edit during a review fails it as stale_checkout.
#
# The sandbox is pinned HERE and in the adapters, not assumed of the CLI: the scope forms
# above, --reviewer, --fallback, --backend, --allow-secret-file, --kit-verified and --kit are the ONLY accepted arguments, and a backend
# never relaxes the sandbox flags. There is deliberately no pass-through for further flags —
# an agent must not be able to talk this script into a run outside the copy or with the
# sandbox off. "Please be careful" is not a guarantee when the caller is a model.
#
# The result is INPUT to a review decision the CALLING agent owns, never a verdict to relay
# verbatim (docs/REVIEW_RUNNING.md).
#
#   REVIEW_REVIEWER      override the configured reviewer for one run (codex | claude)
#   MYAGENTKIT_BACKEND   the backend for one run when --backend is not given
#   REVIEW_CODEX_MODEL   override the pinned Codex model for one run
#   REVIEW_CLAUDE_MODEL  override the pinned Claude model for one run
#   REVIEW_RISK      the brief's tier, low|medium|high; sets the default effort
#   REVIEW_EFFORT    reasoning effort low|medium|high (default: high when REVIEW_RISK=high, else medium)
#   REVIEW_FOCUS     portability | logic: one reviewer each on a high-tier change
#   REVIEW_TASK_FILE the brief the prompt quotes; its Owns: line bounds the diff (owns_check.py)
#   REVIEW_ROUND_EXCEPTION  the recorded reason for a third round under one label
#   REVIEW_SAME_TIER_EXCEPTION  the recorded reason the author's tier reviews (a plan with no
#                    tier above it; REVIEW_RISK=high and effort high only; one round per
#                    label and focus, a second is refused; docs/WORKFLOW.md)
#   MYAGENTKIT_AUTHOR_EFFORT  the author's effort (default: high); with MYAGENTKIT_AUTHOR the
#                    required review runs at it or above, high at most (docs/REVIEW_GATE.md, "Invariant")
#   REVIEW_TIMEOUT_SECONDS  wall clock per attempt (default: 2700, 3600 for high-effort Codex; at most 3600)
#   REVIEW_MAX_TURNS        Claude turns per attempt (default: 200, at most 500)
#   REVIEW_CLI_BIN   the Codex binary             (default: codex)
#   CLAUDE_CLI_BIN   the Claude binary            (default: claude)
set -u
# Windows installs Python as `python` or `py`: when `python3` is absent or does not run (a
# Store alias exits 9009), the scripts call the first of those that runs under the usual
# name. A function is enough for a call; an `exec` cannot run a function, so the exec sites
# use $kit_python, the resolved command.
if python3 -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python3
elif python -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python
else kit_python="py -3"; fi   # the launcher, told which Python: unquoted at every use
[ "$kit_python" = python3 ] || python3() { $kit_python "$@"; }
script_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
# CDPATH cleared: exported, it sent a relative REVIEW_REPO_ROOT into another tree with that name.
CDPATH= cd -- "${REVIEW_REPO_ROOT:-$script_dir/..}" || exit 2

# ---------------------------------------------------------------------------------------
# PROJECT-OWNED CONFIGURATION. Set during setup; sync-kit.sh never overwrites this file.
#
# Pins are fixed snapshots and per reviewer: Codex's JSONL names no model, so the pin is the only
# record, and the vendors' id formats differ (platform.claude.com/docs/en/about-claude/models/model-ids-and-versions;
# learn.chatgpt.com/docs/non-interactive-mode). Critical work (WORKFLOW rule 7): set
# REVIEW_CLAUDE_MODEL to the strongest tier for that run.
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
  echo "usage: review.sh [--uncommitted | --base <ref> | --commit <sha>] [--reviewer codex|claude] [--fallback] [--backend NAME] [--allow-secret-file PATH]... [--kit-verified [--kit DIR]]"
  echo "       review.sh --self-test"
  exit 2
}
die() { printf '%s\n' "FAIL [review]: $1"; exit 2; }

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
  # No completion line = no pass: an empty run is a failure (pytest exit code 5,
  # docs.pytest.org/en/stable/reference/exit-codes.html; jest --passWithNoTests is opt-in, jestjs.io/docs/cli).
  grep -qx 'REVIEW SELF-TEST: PASS' "$test_log" || die "review self-tests produced no completion evidence"
  exit 0
fi

scope_flag="--uncommitted"
scope_arg=""
scope_seen=0
fallback=""
reviewer="${REVIEW_REVIEWER:-$DEFAULT_REVIEWER}"
backend="${MYAGENTKIT_BACKEND:-}"
kit_verified=0
kit=""
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
    --fallback)
      fallback="--allow-fallback"; shift ;;
    --backend)
      [ $# -ge 2 ] || usage
      backend="$2"; shift 2 ;;
    --allow-secret-file)
      [ $# -ge 2 ] || usage
      case "$2" in -*|"") usage ;; esac
      case "$2" in *"
"*) usage ;; esac
      secret_files="${secret_files:-}$2
"; shift 2 ;;
    --kit-verified)
      kit_verified=1; shift ;;
    --kit)
      [ $# -ge 2 ] || usage
      case "$2" in -*|"") usage ;; esac
      kit="$2"; shift 2 ;;
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
# A brief's Owns: line names the paths its worker may change (docs/HANDOFF.md, "The brief");
# in cross mode the two sides never share a file, so a diff outside them is not reviewed.
if [ -n "${REVIEW_TASK_FILE:-}" ]; then
  python3 -B "$script_dir/owns_check.py" "$REVIEW_TASK_FILE" "$@" ||
    die "the diff leaves the brief's Owns: paths, or they could not be checked (above)"
fi
# After owns_check, which parses only the scope flags; the dispatcher refuses the rest of a misuse.
[ "$kit_verified" -eq 0 ] || [ "$scope_flag" = --commit ] || usage
[ -z "$kit" ] || [ "$kit_verified" -eq 1 ] || usage
[ "$kit_verified" -eq 0 ] || set -- "$@" --kit-verified
[ -z "$kit" ] || set -- "$@" --kit "$kit"
# The dispatcher checks the name and reads the file; without a backend its argv is unchanged.
if [ -n "$backend" ] && [ "$reviewer" = codex ]; then
  printf '%s\n' 'review: --backend is ignored for --reviewer codex' >&2
elif [ -n "$backend" ]; then
  set -- "$@" --backend "$backend"
fi

# Reviewing CLIs are commonly per-user installs missing from a non-login shell's PATH: a
# fallback, never first. An old standalone build left in ~/.local/bin once shadowed the
# current binary on PATH and every review failed with "requires a newer version".
[ -x "$HOME/.local/bin/codex" ] && { PATH="$PATH:$HOME/.local/bin"; export PATH; }

# Without REVIEW_EFFORT the dispatcher's default follows REVIEW_RISK (docs/REVIEW_GATE.md, "Risk tiers").
[ -n "${REVIEW_EFFORT:-}" ] && set -- --effort "$REVIEW_EFFORT" "$@"
# Each secret-looking path the owner reviews knowingly, one argument each (a path may hold a space).
if [ -n "${secret_files:-}" ]; then
  while IFS= read -r secret; do
    [ -n "$secret" ] && set -- "$@" --allow-secret-file "$secret"
  done <<EOF
$secret_files
EOF
fi
# Only with --fallback does the dispatcher make one failover to the other configured pin.
# Each adapter retains its own evidence and usage; a completed Reject never triggers another call.
exec $kit_python -B "$script_dir/review_dispatch.py" --repo "$PWD" --reviewer "$reviewer" $fallback \
  --claude-model "${REVIEW_CLAUDE_MODEL:-$CLAUDE_MODEL}" \
  --codex-model "${REVIEW_CODEX_MODEL:-$CODEX_MODEL}" "$@"
