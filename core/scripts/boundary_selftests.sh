# Negative tests for scripts/boundary_checks.sh — SOURCED by check.sh --self-test.
#
# One case per check. First require a green baseline, then construct the violation,
# require both a nonzero exit and this check's specific diagnostic, and clean up.
# Set `st_fail=1` when a gate did not reject what it claims to reject. An unrelated
# failure or a diagnostic printed by a command that succeeded is not a passing test.
# Print exactly `  ok   — <label>` for each case that passed: while boundary_checks.sh holds
# any check, check.sh --self-test FAILS a file here that printed no such line, because a
# self-test that ran nothing would otherwise count as a pass.
#
# `sh "$0"` re-runs the gate without the self-test flag, so it exits nonzero on a violation.
#
# REPLACE THIS WHOLE FILE alongside scripts/boundary_checks.sh.
#
# Worked example, matching the example check:
# The dot-prefixed injection is intended to avoid common build/lint include globs.
# Verify your project's actual include rules; dotfiles are not universally excluded.
#
#   if ! sh "$0" >/dev/null 2>&1; then
#     echo "  FAIL — domain/web baseline is already red; the injection would prove nothing."
#     st_fail=1
#   elif [ -e src/domain/.selftest.py ] || [ -L src/domain/.selftest.py ]; then
#     echo "  FAIL — the injection path already exists; refusing to overwrite owner content."
#     st_fail=1
#   else
#     mkdir -p src/domain && printf 'from myapp.web import router\n' > src/domain/.selftest.py
#     boundary_status=0
#     boundary_output=$(sh "$0" 2>&1) || boundary_status=$?
#     if [ "$boundary_status" -ne 0 ] && printf '%s\n' "$boundary_output" |
#         grep -Fq 'FAIL [boundary]: the domain layer imports the web layer:'; then
#       echo "  ok   — domain/web boundary gate rejects a forbidden import"
#     else
#       echo "  FAIL — the injection did not produce the domain/web gate's failure."
#       st_fail=1
#     fi
#     rm -f src/domain/.selftest.py
#   fi
#
# {{BOUNDARY_SELF_TESTS}}

# Existing-file probes run in a disposable copy of the checkout, never in the checkout:
# a self-test never changes a tracked file. An edit made in place and restored by traps was
# seen by a concurrent `git add -A`, and SIGKILL or a power loss, which run no trap, left it
# in the tree. The copy holds the current bytes, uncommitted edits included, and is deleted
# on exit and on INT/TERM; a SIGKILL leaves it in $TMPDIR, outside the checkout. cp -R keeps
# a symlink as a symlink, so a symlinked parent directory (src -> the checkout's lib) once
# took the write back into the checkout: the target and the gate are resolved physically
# and must lie inside the copy, and neither may itself be a symlink (an absolute one at the
# gate ran a gate that resolves its own location against the checkout), else the case fails
# by name. The copy itself must lie outside the checkout (a TMPDIR set to the checkout put
# it, and a SIGKILL's leftovers, in the working tree), and git inside it must work on the
# copy: an exported GIT_DIR and GIT_WORK_TREE made a gate that finds its root with
# `git rev-parse --show-toplevel` build in the checkout. A linked worktree's `.git` is a
# pointer file, and the copied pointer kept the original's git directory: a gate that stages
# its inputs staged the injection into the original's index. Such a copy gets its own
# repository (git init, then git add -A), and both the git directory and the common directory
# must resolve inside the copy, else the case fails by name. Copying a
# large tree (dependencies, build output) costs time: copy only what the gate reads if that
# is known, but never let the probe write into the checkout.
#
# This worked example runs in a subshell so its traps do not replace the surrounding
# self-test traps. `$0` is the checkout's gate; the copy's own gate, at the same relative
# path, is the one it runs. Adapt the target and diagnostic to your gate.
#
# | if (
# |   probe_checkout=$(pwd -P) || exit 1
# |   probe_copy=$(mktemp -d) || exit 1
# |   trap 'rm -rf "$probe_copy"' EXIT
# |   trap 'exit 130' INT
# |   trap 'exit 143' TERM
# |   probe_copy=$(cd -P "$probe_copy" && pwd -P) || exit 1
# |   case "$probe_copy/" in
# |     "$probe_checkout"/*) echo "  FAIL — existing-file probe: the disposable copy ($probe_copy) is inside the checkout; set TMPDIR outside it."
# |        exit 1 ;;
# |   esac
# |   cp -R . "$probe_copy/checkout" && cd "$probe_copy/checkout" || exit 1
# |   unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR
# |   probe_gate=$PWD/$(basename "$(dirname "$0")")/${0##*/}
# |   probe_target=src/domain/existing.py
# |   [ -f "$probe_target" ] && [ ! -L "$probe_target" ] || exit 1
# |   probe_root=$(pwd -P) || exit 1
# |   if [ -L .git ] || [ -f .git ]; then
# |     rm -f .git && git init -q && git add -A || {
# |       echo "  FAIL — existing-file probe: could not give the disposable copy its own git repository; refusing to run."
# |       exit 1
# |     }
# |   fi
# |   if probe_top=$(git rev-parse --show-toplevel 2>/dev/null); then
# |     if [ "$(cd -P "$probe_top" && pwd -P)" != "$probe_root" ]; then
# |       echo "  FAIL — existing-file probe: git inside the disposable copy works on $probe_top; refusing to run."
# |       exit 1
# |     fi
# |     for probe_git in "$(git rev-parse --absolute-git-dir)" "$(git rev-parse --git-common-dir)"; do
# |       probe_git=$(cd -P "$probe_git" && pwd -P) || exit 1
# |       case "$probe_git/" in
# |         "$probe_root"/*) ;;
# |         *) echo "  FAIL — existing-file probe: the copy shares the original's git directory ($probe_git); refusing to run."
# |            exit 1 ;;
# |       esac
# |     done
# |   fi
# |   for probe_path in "$probe_target" "$probe_gate"; do
# |     if [ -L "$probe_path" ]; then
# |       echo "  FAIL — existing-file probe: $probe_path is a symlink, which can lead out of the disposable copy; refusing to run."
# |       exit 1
# |     fi
# |     probe_dir=$(cd -P "$(dirname "$probe_path")" && pwd -P) || exit 1
# |     case "$probe_dir/" in
# |       "$probe_root"/*) ;;
# |       *) echo "  FAIL — existing-file probe: $probe_path resolves outside the disposable copy ($probe_dir); refusing to write."
# |          exit 1 ;;
# |     esac
# |   done
# |   sh "$probe_gate" >/dev/null 2>&1 || exit 1
# |   printf 'from myapp.web import router\n' > "$probe_target" || exit 1
# |   probe_status=0
# |   probe_output=$(sh "$probe_gate" 2>&1) || probe_status=$?
# |   [ "$probe_status" -ne 0 ] && printf '%s\n' "$probe_output" |
# |     grep -Fq 'FAIL [boundary]: the domain layer imports the web layer:'
# | ); then
# |   echo "  ok   — domain/web boundary gate rejects a forbidden import in an existing file"
# | else
# |   probe_case_status=$?
# |   case "$probe_case_status" in
# |     130|143) exit "$probe_case_status" ;;
# |     *) st_fail=1 ;;
# |   esac
# | fi
