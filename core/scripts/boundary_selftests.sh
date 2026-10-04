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
# checkout. A nested repository or linked worktree (a `.git` below the top level) keeps its
# pointer to the original's git directory, so the case fails by name on one. A linked
# worktree's `.git` is a pointer file, and the copied pointer kept the original's git
# directory: a gate that stages its inputs staged the injection into the original's index.
# Such a copy gets its own repository with the original's refs, HEAD and index, reading the
# original's objects read-only through alternates (a bare `git init` lost HEAD, tags and the
# staged state, and a gate that needs them failed the copy's baseline), and both the git
# directory and the common directory must resolve inside the copy, else the case fails by
# name. The repository takes the original's object format (a SHA-256 original's IDs did not
# fit a SHA-1 copy) and an index rebuilt from the original's entries: a copied index file left
# a split index's shared part behind, and the copy's index was unreadable. The original's
# entries and refs are read into files first and each read's status checked: piped, a failed
# read fed an empty index to a consumer that succeeded. Copying a large tree (dependencies,
# build output) costs time: copy only what the gate reads if that is known, but never let the
# probe write into the checkout.
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
# |   probe_copy=$(CDPATH= cd -P "$probe_copy" && pwd -P) || exit 1
# |   case "$probe_copy/" in
# |     "$probe_checkout"/*) echo "  FAIL — existing-file probe: the disposable copy ($probe_copy) is inside the checkout; set TMPDIR outside it."
# |        exit 1 ;;
# |   esac
# |   probe_env() { env -i PATH="$PATH" HOME="$HOME" LC_ALL=C TMPDIR="${TMPDIR:-/tmp}" "$@"; }
# |   probe_fail() { echo "  FAIL — existing-file probe: $*"; exit 1; }
# |   cp -R . "$probe_copy/checkout" && CDPATH= cd -P "$probe_copy/checkout" || exit 1
# |   probe_root=$(pwd -P) || exit 1
# |   probe_nested=$(find . -path ./.git -prune -o -name .git -print) ||
# |     probe_fail "could not search the disposable copy for nested repositories; refusing to run."
# |   if [ -n "$probe_nested" ]; then
# |     probe_nested=$(printf '%s\n' "$probe_nested" | sed -n '1{s|^\./||;s|/\.git$||;p;}')
# |     probe_fail "the checkout contains a nested repository or worktree at $probe_nested; the existing-file probe does not support it."
# |   fi
# |   if [ -L .git ] || [ -f .git ]; then
# |     probe_head=$(probe_env git -C "$probe_checkout" rev-parse -q --verify HEAD) || probe_head=
# |     probe_env git -C "$probe_checkout" for-each-ref --format='create %(refname) %(objectname)' > "$probe_copy/refs" ||
# |       probe_fail "could not read the original's refs (git for-each-ref); refusing to run."
# |     probe_env git -C "$probe_checkout" ls-files -s -z --full-name > "$probe_copy/index" ||
# |       probe_fail "could not read the original's index (git ls-files); refusing to run."
# |     { probe_from=$(CDPATH= cd -P "$probe_checkout" && CDPATH= cd -P "$(probe_env git rev-parse --git-common-dir)" && pwd -P) &&
# |       probe_format=$(probe_env git -C "$probe_checkout" rev-parse --show-object-format) &&
# |       rm -f .git && probe_env git init -q --object-format="$probe_format" &&
# |       printf '%s/objects\n' "$probe_from" > .git/objects/info/alternates &&
# |       probe_env git update-ref --stdin < "$probe_copy/refs" &&
# |       if probe_branch=$(probe_env git -C "$probe_checkout" symbolic-ref -q HEAD); then
# |         probe_env git symbolic-ref HEAD "$probe_branch"
# |       elif [ -n "$probe_head" ]; then
# |         probe_env git update-ref --no-deref HEAD "$probe_head"
# |       fi &&
# |       probe_env git update-index -z --index-info < "$probe_copy/index" &&
# |       { probe_env git update-index -q --refresh >/dev/null 2>&1 || :; } &&
# |       probe_env git ls-files -s >/dev/null &&
# |       [ "$(probe_env git rev-parse -q --verify HEAD)" = "$probe_head" ]; } ||
# |       probe_fail "could not give the disposable copy its own git repository with the original's HEAD, history and index; refusing to run."
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
