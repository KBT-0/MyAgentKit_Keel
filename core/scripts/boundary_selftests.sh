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
# read fed an empty index to a consumer that succeeded. The rebuilt index keeps intent-to-add
# (`git add -N`), read with `git diff-files --diff-filter=A`: rebuilt from `ls-files -s` alone,
# such a path became a staged empty blob and a gate checking the staged changes rejected the
# copy. diff-files misses an intent-to-add path whose file was deleted, which then became a
# staged empty blob all the same: every intent-to-add entry is counted with
# `diff-index --cached --ita-invisible-in-index`, and one diff-files did not report is refused
# by name, as are unmerged, skip-worktree and assume-unchanged entries. The copy
# carries the original's local configuration, and its worktree configuration when
# extensions.worktreeConfig is on (a gate needing a locally configured setting failed the
# copy's baseline), except keys that redirect storage or execution (hooks path, editors,
# drivers, filters, includes, aliases, credentials, URL rewrites), each dropped with a NOTE
# line. A valueless key is appended to the copy's config file as valueless: carried as the
# string `true`, an untyped read of it in the copy differed from the original's. The directories inside the copy's git storage were not checked: cp -R kept
# `.git/objects` as a symlink to the original's store and a copied gate's `git add` wrote
# there, so a file symlink in the git storage that resolves outside the copy fails the case by
# name. A directory symlink fails it whatever its target: find does not descend through one, so
# `.git/objects -> ../store` passed while an absolute link beneath `store` took the copy's
# writes outside it. The original's objects stay reachable only through the alternates file.
# Copying a large tree (dependencies, build output) costs time: copy only what the gate reads
# if that is known, but never let the probe write into the checkout.
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
# |     # ls-files -v tags: M unmerged, S skip-worktree, lower case assume-unchanged.
# |     probe_env git -C "$probe_checkout" ls-files -v > "$probe_copy/flags" ||
# |       probe_fail "could not read the original's index flags (git ls-files -v); refusing to run."
# |     ! grep -q '^[Mm] ' "$probe_copy/flags" ||
# |       probe_fail "the original index has unmerged entries; the existing-file probe does not support them."
# |     ! grep -q '^[Ss] ' "$probe_copy/flags" ||
# |       probe_fail "the original index has skip-worktree entries; the existing-file probe does not support them."
# |     ! grep -q '^[a-z] ' "$probe_copy/flags" ||
# |       probe_fail "the original index has assume-unchanged entries; the existing-file probe does not support them."
# |     probe_env git -C "$probe_checkout" diff-files --diff-filter=A --name-only -z > "$probe_copy/ita" ||
# |       probe_fail "could not read the original's intent-to-add entries (git diff-files); refusing to run."
# |     # Every intent-to-add entry, whatever its working tree: those --ita-invisible-in-index hides.
# |     probe_env git -C "$probe_checkout" ls-files > "$probe_copy/paths" &&
# |       probe_empty=$(probe_env git -C "$probe_checkout" hash-object -t tree /dev/null) &&
# |       probe_env git -C "$probe_checkout" diff-index --cached --ita-invisible-in-index --name-only "$probe_empty" > "$probe_copy/visible" ||
# |       probe_fail "could not count the original's intent-to-add entries (git diff-index); refusing to run."
# |     [ $(( $(wc -l < "$probe_copy/paths") - $(wc -l < "$probe_copy/visible") )) -eq $(( $(tr -cd '\000' < "$probe_copy/ita" | wc -c) )) ] ||
# |       probe_fail "the original index has an intent-to-add entry whose file is missing from the working tree; the existing-file probe does not support it."
# |     probe_env git -C "$probe_checkout" config --local --no-includes --list -z > "$probe_copy/config" ||
# |       probe_fail "could not read the original's configuration (git config --local); refusing to run."
# |     if [ "$(probe_env git -C "$probe_checkout" config --bool extensions.worktreeConfig)" = true ]; then
# |       probe_env git -C "$probe_checkout" config --worktree --no-includes --list -z >> "$probe_copy/config" ||
# |         probe_fail "could not read the original's worktree configuration (git config --worktree); refusing to run."
# |     fi
# |     { probe_from=$(CDPATH= cd -P "$probe_checkout" && CDPATH= cd -P "$(probe_env git rev-parse --git-common-dir)" && pwd -P) &&
# |       probe_format=$(probe_env git -C "$probe_checkout" rev-parse --show-object-format) &&
# |       rm -f .git && probe_env git init -q --object-format="$probe_format" &&
# |       probe_env xargs -0 sh -c '
# |         for probe_entry; do
# |           probe_key=$(printf "%s\n" "$probe_entry" | sed -n 1p) || exit 1
# |           case $probe_key in
# |             core.worktree|core.hookspath|core.fsmonitor|core.sshcommand|core.gitproxy|core.editor|\
# |             core.pager|core.askpass|core.alternaterefscommand|sequence.editor|gpg.program|gpg.*.program|\
# |             pager.*|include.path|includeif.*.path|alias.*|filter.*|diff.external|diff.*.command|\
# |             diff.*.textconv|merge.*.driver|credential.*|url.*.insteadof|url.*.pushinsteadof|\
# |             remote.*.uploadpack|remote.*.receivepack|extensions.worktreeconfig)
# |               echo "  NOTE — existing-file probe: $probe_key is not carried into the disposable copy: it can redirect storage or execution outside it." ;;
# |             core.repositoryformatversion|core.bare|extensions.*) ;;
# |             *) if [ "$probe_entry" != "$probe_key" ]; then
# |                  git config --add "$probe_key" "${probe_entry#"$probe_key"?}" || exit 1
# |                else
# |                  # A valueless key (no newline in the entry) has no `git config` syntax: append it.
# |                  probe_section=${probe_key%.*}
# |                  case $probe_section in
# |                    *.*) probe_sub=$(printf "%s\n" "${probe_section#*.}" | sed "s/[\\\\\"]/\\\\&/g") || exit 1
# |                         probe_section="${probe_section%%.*} \"$probe_sub\"" ;;
# |                  esac
# |                  printf "[%s]\n\t%s\n" "$probe_section" "${probe_key##*.}" >> .git/config || exit 1
# |                fi ;;
# |           esac
# |         done' sh < "$probe_copy/config" &&
# |       printf '%s/objects\n' "$probe_from" > .git/objects/info/alternates &&
# |       probe_env git update-ref --stdin < "$probe_copy/refs" &&
# |       if probe_branch=$(probe_env git -C "$probe_checkout" symbolic-ref -q HEAD); then
# |         probe_env git symbolic-ref HEAD "$probe_branch"
# |       elif [ -n "$probe_head" ]; then
# |         probe_env git update-ref --no-deref HEAD "$probe_head"
# |       fi &&
# |       probe_env git update-index -z --index-info < "$probe_copy/index" &&
# |       probe_env git update-index -z --force-remove --stdin < "$probe_copy/ita" &&
# |       { [ ! -s "$probe_copy/ita" ] ||
# |         probe_env git --literal-pathspecs add -f -N --pathspec-from-file="$probe_copy/ita" --pathspec-file-nul; } &&
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
