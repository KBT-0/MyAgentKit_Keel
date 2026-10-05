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
# it, and a SIGKILL's leftovers, in the working tree). Every command that touches the copy,
# git and the copied gate alike, runs under probe_env, which passes ONLY the variables it
# names: removing variables one at a time missed each next one (an exported GIT_DIR built in
# the checkout; an exported GIT_OBJECT_DIRECTORY took the copy's `git add` into the
# original's object store). A gate that needs more variables gets them by adding NAME="$NAME"
# to probe_env. Every resolving cd is `CDPATH= cd -P`, and the injection is written to the
# resolved, validated absolute path: with CDPATH set, `cd -P src/domain` validated a
# directory the relative write never reached, and the write followed a symlink into the
# checkout. The example supports a PLAIN repository only: a checkout whose `.git` is a file or
# a symlink (a linked worktree, a submodule, `--separate-git-dir`) is refused by name and
# reported NOT RUN, never passed. Its copied pointer kept the original's git directory, so a
# gate that stages its inputs staged the injection into the original's index, and rebuilding
# such a repository inside the copy (refs, HEAD, index, object format, intent-to-add) took
# fourteen review rounds and still recreated symbolic refs as direct ones. A nested repository
# (a `.git` below the top level) is refused by name for the same reason. The directories
# inside the copy's git storage were not checked: cp -R kept `.git/objects` as a symlink to
# the original's store and a copied gate's `git add` wrote there, so a file symlink in the git
# storage that resolves outside the copy fails the case by name. A directory symlink fails it
# whatever its target: find does not descend through one, so `.git/objects -> ../store` passed
# while an absolute link beneath `store` took the copy's writes outside it.
# Copying a large tree (dependencies, build output) costs time: copy only what the gate reads
# if that is known, but never let the probe write into the checkout.
#
# This worked example runs in a subshell so its traps do not replace the surrounding
# self-test traps. `$0` is the checkout's gate; the copy's own gate, at the same relative
# path, is the one it runs. Adapt the target and diagnostic to your gate.
#
# | if (
# |   # A setting your gate reads goes here by name, as `git config --list` prints it (section and
# |   # key in lower case), e.g. "kit.required"; never one that names a command or a path.
# |   probe_config_keys=""
# |   probe_checkout=$(pwd -P) || exit 1
# |   probe_copy=$(mktemp -d) || exit 1
# |   trap 'rm -rf "$probe_copy"' EXIT
# |   trap 'exit 130' INT
# |   trap 'exit 143' TERM
# |   probe_copy=$(CDPATH= cd -P "$probe_copy" && pwd -P) || exit 1
# |   case "$probe_copy/" in
# |     "$probe_checkout"/*) echo "  FAIL — existing-file probe: the disposable copy ($probe_copy) is inside the checkout; set TMPDIR outside it."
# |        exit 1 ;;
# |   esac
# |   probe_env() { env -i PATH="$PATH" HOME="$HOME" LC_ALL=C TMPDIR="${TMPDIR:-/tmp}" "$@"; }
# |   probe_fail() { echo "  FAIL — existing-file probe: $*"; exit 1; }
# |   probe_skip() { echo "  NOT RUN — existing-file probe: $*"; exit 1; }
# |   [ -d .git ] && [ ! -L .git ] && [ ! -e .git/commondir ] ||
# |     probe_skip "the checkout's .git is not a directory (a linked worktree, a submodule or a separate git directory); this example supports a plain repository only: run the self-test from the main checkout."
# |   cp -R . "$probe_copy/checkout" && CDPATH= cd -P "$probe_copy/checkout" || exit 1
# |   probe_root=$(pwd -P) || exit 1
# |   probe_nested=$(find . -path ./.git -prune -o -name .git -print) ||
# |     probe_fail "could not search the disposable copy for nested repositories; refusing to run."
# |   if [ -n "$probe_nested" ]; then
# |     probe_nested=$(printf '%s\n' "$probe_nested" | sed -n '1{s|^\./||;s|/\.git$||;p;}')
# |     probe_fail "the checkout contains a nested repository or worktree at $probe_nested; the existing-file probe does not support it."
# |   fi
# |   if probe_top=$(probe_env git rev-parse --show-toplevel 2>/dev/null); then
# |     [ "$(CDPATH= cd -P "$probe_top" && pwd -P)" = "$probe_root" ] ||
# |       probe_fail "git inside the disposable copy works on $probe_top; refusing to run."
# |     for probe_git in "$(probe_env git rev-parse --absolute-git-dir)" "$(probe_env git rev-parse --git-common-dir)"; do
# |       probe_git=$(CDPATH= cd -P "$probe_git" && pwd -P) || exit 1
# |       case "$probe_git/" in
# |         "$probe_root"/*) ;;
# |         *) probe_fail "the copy shares the original's git directory ($probe_git); refusing to run." ;;
# |       esac
# |       find "$probe_git" -type l > "$probe_copy/links" ||
# |         probe_fail "could not search the copy's git storage for symlinks; refusing to run."
# |       while IFS= read -r probe_link; do
# |         # find does not descend through a directory symlink, so nothing beneath one is checked.
# |         [ ! -d "$probe_link" ] ||
# |           probe_fail "the copy's git storage has a directory symlink at ${probe_link#"$probe_root"/}; the existing-file probe does not support it."
# |         probe_to=$(probe_target=$(readlink "$probe_link") && CDPATH= cd -P "$(dirname "$probe_link")" &&
# |           CDPATH= cd -P "$(dirname "$probe_target")" && [ ! -L "${probe_target##*/}" ] && pwd -P) || probe_to=
# |         case "$probe_to/" in
# |           "$probe_root"/*) ;;
# |           *) probe_fail "the copy's git storage at ${probe_link#"$probe_root"/} points outside the copy; refusing to run." ;;
# |         esac
# |       done < "$probe_copy/links"
# |     done
# |   fi
# |   # Resolved physically to an absolute path inside the copy, and never itself a symlink.
# |   probe_resolve() {
# |     probe_dir=$(CDPATH= cd -P "$(dirname "$1")" && pwd -P) || exit 1
# |     case "$probe_dir/" in
# |       "$probe_root"/*) ;;
# |       *) probe_fail "$1 resolves outside the disposable copy ($probe_dir); refusing to write." ;;
# |     esac
# |     probe_resolved=$probe_dir/${1##*/}
# |     [ ! -L "$probe_resolved" ] ||
# |       probe_fail "$1 is a symlink, which can lead out of the disposable copy; refusing to run."
# |   }
# |   probe_resolve src/domain/existing.py
# |   probe_target=$probe_resolved
# |   [ -f "$probe_target" ] || exit 1
# |   probe_resolve "$(basename "$(dirname "$0")")/${0##*/}"
# |   probe_gate=$probe_resolved
# |   probe_env sh "$probe_gate" >/dev/null 2>&1 || exit 1
# |   printf 'from myapp.web import router\n' > "$probe_target" || exit 1
# |   probe_status=0
# |   probe_output=$(probe_env sh "$probe_gate" 2>&1) || probe_status=$?
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
