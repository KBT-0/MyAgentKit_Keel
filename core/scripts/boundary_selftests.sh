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
#   elif (
#     # A subshell, so these traps do not replace the self-test's: interrupted, the file goes too.
#     trap 'rm -f src/domain/.selftest.py' EXIT
#     trap 'exit 130' INT
#     trap 'exit 143' TERM
#     mkdir -p src/domain && printf 'from myapp.web import router\n' > src/domain/.selftest.py || exit 1
#     boundary_status=0
#     boundary_output=$(sh "$0" 2>&1) || boundary_status=$?
#     [ "$boundary_status" -ne 0 ] && printf '%s\n' "$boundary_output" |
#       grep -Fq 'FAIL [boundary]: the domain layer imports the web layer:'
#   ); then
#     echo "  ok   — domain/web boundary gate rejects a forbidden import"
#   else
#     boundary_status=$?
#     case $boundary_status in 130|143) exit "$boundary_status" ;; esac
#     echo "  FAIL — the injection did not produce the domain/web gate's failure."
#     st_fail=1
#   fi
#
# {{BOUNDARY_SELF_TESTS}}

# Existing-file probes run in a disposable copy of the checkout, never in the checkout:
# a self-test never changes a tracked file. An edit made in place and restored by traps was
# seen by a concurrent `git add -A`, and SIGKILL or a power loss, which run no trap, left it
# in the tree. The copy holds the current bytes, uncommitted edits included, and is deleted
# on exit and on INT/TERM; a SIGKILL leaves it in $TMPDIR, outside the checkout. The copy
# itself must lie outside the checkout (a TMPDIR set to the checkout put it, and a SIGKILL's
# leftovers, in the working tree). Every command that touches the copy, git and the copied
# gate alike, runs under probe_env, which passes ONLY the variables it names: removing
# variables one at a time missed each next one (an exported GIT_DIR built in the checkout; an
# exported GIT_OBJECT_DIRECTORY took the copy's `git add` into the original's object store).
# A gate that needs more variables gets them by adding NAME="$NAME" to probe_env. HOME is an
# empty directory in the copy and no system or global git configuration is read: with the real
# HOME, a global tar.<format>.command ran from a copied gate's `git archive` and wrote outside
# the copy. A tool that needs a cache directory gets its own variable (GRADLE_USER_HOME and the
# like) in probe_env, never the real HOME.
# The example supports a PLAIN repository only: a checkout whose `.git` is a file or a
# symlink (a linked worktree, a submodule, `--separate-git-dir`) is refused by name and
# reported NOT RUN, never passed. Its copied pointer kept the original's git directory, so a
# gate that stages its inputs staged the injection into the original's index, and rebuilding
# such a repository inside the copy (refs, HEAD, index, object format, intent-to-add) took
# fourteen review rounds and still recreated symbolic refs as direct ones. A nested repository
# (a `.git` below the top level) is refused by name for the same reason.
# The copied .git/config is replaced by an allowlist of its settings plus the keys named in
# probe_config_keys: kept verbatim, it ran the original's core.hooksPath and a copied gate's
# `git archive` ran its tar.<format>.command, and a denylist of such keys had already missed
# the next one. Every other key gets a NOTE line, include.path and includeIf among them, and
# .git/config.worktree is removed. An allowlisted key is carried only when every value of it
# comes from the repository's own config file; one set in the worktree configuration or an
# included file fails the case by name, since flattening scopes and includes into one file
# changed what a gate's `git config <key> <value>` did. The values are added in order, and a
# valueless key is written as valueless: carried as the string `true`, an untyped read of it
# in the copy differed from the original's.
# cp keeps a symlink as a symlink, and every symlink in the copy whose target resolves outside
# it is refused by name, wherever it is: checking only the target, the gate and the git
# storage let an unrelated `build -> <checkout>/out` take a baseline gate's build output into
# the checkout, as `.git/objects -> <store>` once took a copied gate's `git add`, and
# `src -> <checkout>/lib` the injection itself. The path to the target and to the gate runs
# through no symlink at all (an absolute link at the gate ran a gate that resolves its own
# location against the checkout), and both are written and run by their absolute paths
# (with CDPATH set, a relative write once missed the directory that was validated).
# The audit runs again after the baseline gate run and before the injection: checked only
# before it, a baseline that replaced src/domain or the gate with a symlink sent the injection,
# or the second run, out of the copy.
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
# |   # An empty HOME and no system or global git configuration: nothing but the copy's own is active.
# |   mkdir "$probe_copy/home" || exit 1
# |   probe_env() {
# |     env -i PATH="$PATH" LC_ALL=C HOME="$probe_copy/home" XDG_CONFIG_HOME="$probe_copy/home" \
# |       GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null TMPDIR="${TMPDIR:-/tmp}" "$@"
# |   }
# |   probe_fail() { echo "  FAIL — existing-file probe: $*"; exit 1; }
# |   probe_skip() { echo "  NOT RUN — existing-file probe: $*"; exit 1; }
# |   [ -d .git ] && [ ! -L .git ] && [ ! -e .git/commondir ] ||
# |     probe_skip "the checkout's .git is not a directory (a linked worktree, a submodule or a separate git directory); this example supports a plain repository only: run the self-test from the main checkout."
# |   cp -R . "$probe_copy/checkout" && CDPATH= cd -P "$probe_copy/checkout" || exit 1
# |   probe_root=$(pwd -P) || exit 1
# |   probe_target=src/domain/existing.py
# |   probe_gate="$(basename "$(dirname "$0")")/${0##*/}"
# |   # Every symlink resolves inside the copy, no `.git` lies below the top level, and the path to
# |   # the target and to the gate runs through no symlink and ends at a regular file.
# |   probe_audit() {
# |     probe_why=$(probe_env python3 -c '
# | import os, sys
# | root = sys.argv[1]
# | for top, dirs, files in os.walk(root):
# |     for name in dirs + files:
# |         path = os.path.join(top, name)
# |         if name == ".git" and top != root:
# |             sys.exit("the checkout contains a nested repository or worktree at " + os.path.relpath(top, root))
# |         if os.path.islink(path) and os.path.commonpath([root, os.path.realpath(path)]) != root:
# |             sys.exit(os.path.relpath(path, root) + " is a symlink that leads out of the disposable copy")
# | for rel in sys.argv[2:]:
# |     path = root
# |     for part in rel.split("/"):
# |         path = os.path.join(path, part)
# |         if os.path.islink(path):
# |             sys.exit(rel + " runs through a symlink at " + os.path.relpath(path, root))
# |     if not os.path.isfile(path):
# |         sys.exit(rel + " is not a regular file in the disposable copy")
# | ' "$probe_root" "$probe_target" "$probe_gate" 2>&1) ||
# |       probe_skip "${probe_why:-could not search the disposable copy}; the existing-file probe does not support it."
# |   }
# |   probe_audit
# |   probe_allowed="core.repositoryformatversion core.bare extensions.objectformat extensions.refstorage
# |     user.name user.email core.autocrlf core.eol core.safecrlf core.filemode core.ignorecase core.symlinks
# |     core.quotepath core.precomposeunicode core.whitespace core.abbrev init.defaultbranch $probe_config_keys"
# |   probe_env git -C "$probe_checkout" config --show-origin --includes --name-only --list > "$probe_copy/names" &&
# |     probe_env git -C "$probe_checkout" config --local --no-includes --show-origin --name-only --list > "$probe_copy/own" &&
# |     probe_env git -C "$probe_checkout" config --local --no-includes --list -z > "$probe_copy/config" ||
# |     probe_fail "could not read the original's configuration (git config); refusing to run."
# |   probe_own=$(LC_ALL=C awk -F '\t' 'NR == 1 { print $1 }' "$probe_copy/own") || exit 1
# |   PROBE_OWN=$probe_own PROBE_ALLOWED=$probe_allowed LC_ALL=C awk -F '\t' '
# |     BEGIN { n = split(ENVIRON["PROBE_ALLOWED"], k, " "); for (i = 1; i <= n; i++) allowed[k[i]] = 1 }
# |     !($2 in allowed) {
# |       if (!noted[$2]++)
# |         print "  NOTE — existing-file probe: " $2 " is not carried into the disposable copy; a setting your gate reads goes in probe_config_keys."
# |       next
# |     }
# |     $1 != ENVIRON["PROBE_OWN"] {
# |       print "  FAIL — existing-file probe: " $2 " is set in " $1 ", not in the repository'"'"'s own config file; set it there, or remove it from probe_config_keys."
# |       exit 1
# |     }' "$probe_copy/names" || exit 1
# |   { rm -f .git/config.worktree && : > .git/config &&
# |     probe_env PROBE_ALLOWED="$probe_allowed" xargs -0 sh -c '
# |       for probe_entry; do
# |         probe_key=$(printf "%s\n" "$probe_entry" | sed -n 1p) || exit 1
# |         probe_carry=
# |         for probe_allowed in $PROBE_ALLOWED; do [ "$probe_key" != "$probe_allowed" ] || probe_carry=1; done
# |         [ -n "$probe_carry" ] || continue
# |         if [ "$probe_entry" != "$probe_key" ]; then
# |           git config --file .git/config --add "$probe_key" "${probe_entry#"$probe_key"?}" || exit 1
# |         else
# |           # A valueless key (no newline in the entry) has no `git config` syntax: append it.
# |           probe_section=${probe_key%.*}
# |           case $probe_section in
# |             *.*) probe_sub=$(printf "%s\n" "${probe_section#*.}" | sed "s/[\\\\\"]/\\\\&/g") || exit 1
# |                  probe_section="${probe_section%%.*} \"$probe_sub\"" ;;
# |           esac
# |           printf "[%s]\n\t%s\n" "$probe_section" "${probe_key##*.}" >> .git/config || exit 1
# |         fi
# |       done' sh < "$probe_copy/config"; } ||
# |     probe_fail "could not carry the allowlisted settings into the disposable copy; refusing to run."
# |   probe_env sh "$probe_root/$probe_gate" >/dev/null 2>&1 ||
# |     probe_fail "the baseline is already red; the injection would prove nothing."
# |   probe_audit
# |   printf 'from myapp.web import router\n' > "$probe_root/$probe_target" || exit 1
# |   probe_status=0
# |   probe_output=$(probe_env sh "$probe_root/$probe_gate" 2>&1) || probe_status=$?
# |   [ "$probe_status" -ne 0 ] && printf '%s\n' "$probe_output" |
# |     grep -Fq 'FAIL [boundary]: the domain layer imports the web layer:' ||
# |     probe_fail "the injection did not produce the domain/web gate's failure."
# | ); then
# |   echo "  ok   — domain/web boundary gate rejects a forbidden import in an existing file"
# | else
# |   probe_case_status=$?
# |   case "$probe_case_status" in
# |     130|143) exit "$probe_case_status" ;;
# |     *) st_fail=1 ;;
# |   esac
# | fi
