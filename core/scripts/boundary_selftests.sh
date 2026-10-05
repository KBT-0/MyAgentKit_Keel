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

# Existing-file probes run in a disposable copy of the checkout, never in the checkout: a
# self-test never changes a tracked file. An edit made in place and restored by traps was
# seen by a concurrent `git add -A`, and SIGKILL or a power loss, which run no trap, left it
# in the tree. The copy holds the current bytes, uncommitted edits included, and is deleted
# on exit and on INT/TERM; a SIGKILL leaves it in $TMPDIR, outside the checkout. The copy
# itself must lie outside the checkout (a TMPDIR set to the checkout put it, and a SIGKILL's
# leftovers, in the working tree). Every command that touches the copy, git and the copied
# gate alike, runs under probe_env, which passes ONLY the variables it names: removing
# variables one at a time missed each next one (an exported GIT_DIR built in the checkout;
# an exported GIT_OBJECT_DIRECTORY took the copy's `git add` into the original's object
# store). A gate that needs more variables gets them by adding NAME="$NAME" to probe_env.
# HOME is an empty directory in the copy and no system or global git configuration is read:
# with the real HOME, a global tar.<format>.command ran from a copied gate's `git archive`
# and wrote outside the copy. A tool that needs a cache directory gets its own variable
# (GRADLE_USER_HOME and the like) in probe_env, never the real HOME.
# The example supports a PLAIN repository only: a checkout whose `.git` is a file or a
# symlink (a linked worktree, a submodule, `--separate-git-dir`) is refused by name and
# reported NOT RUN, which fails the self-test: run it from the main checkout. Its copied
# pointer kept the original's git directory, so a gate that stages its inputs staged the
# injection into the original's index, and rebuilding such a repository inside the copy
# (refs, HEAD, index, object format, intent-to-add) took fourteen review rounds and still
# recreated symbolic refs as direct ones. A nested repository (a `.git` below the top level)
# is refused by name for the same reason.
# The copied .git/config is replaced by an allowlist of its settings plus the keys named in
# probe_config_keys: kept verbatim, it ran the original's core.hooksPath and a copied gate's
# `git archive` ran its tar.<format>.command, and a denylist of such keys had already missed
# the next one. Every other key gets a NOTE line, include.path and includeIf among them, and
# .git/config.worktree is removed. An allowlisted key is carried only when every value of it
# comes from the repository's own config file; one set in the worktree configuration or an
# included file fails the case by name, since flattening scopes and includes into one file
# changed what a gate's `git config <key> <value>` did. The values are added in order, and a
# valueless key is written as valueless: carried as the string `true`, an untyped read of it
# in the copy differed from the original's. The copy's .git/hooks starts empty: copied with
# the rest, the original's hooks ran from a copied gate's `git commit`.
# `cp -RP` keeps a symlink as a symlink (POSIX leaves a plain `cp -R` unspecified), and
# every symlink in the copy whose target resolves outside it is refused by name, wherever it
# is: checking only the target, the gate and the git storage let an unrelated `build ->
# <checkout>/out` take a baseline gate's build output into the checkout, as `.git/objects ->
# <store>` once took a copied gate's `git add`, and `src -> <checkout>/lib` the injection
# itself. The path to the target and to the gate runs through no symlink at all (an absolute
# link at the gate ran a gate that resolves its own location against the checkout), and both
# are written and run by their absolute paths (with CDPATH set, a relative write once missed
# the directory that was validated).
# The second run starts from a fresh copy; nothing the baseline run wrote exists in it. With
# one copy reused, three review rounds in a row found something the baseline left that acted
# in the second run (a hook in .git/hooks, a core.hooksPath, a .pth file in HOME that the
# second run's python3 executed), and each re-check added after the baseline was the next
# thing to bypass (a .git/config replaced by a link to /dev/zero hung the comparison). So the
# baseline's copy, its own HOME and TMPDIR inside, is deleted (one that cannot be deleted
# fails the case by name), and the same function makes the injected run a new one. Each copy
# is hashed as taken, before anything runs in it (every entry's path, type, executable bit and
# content, `.git` included; a FIFO, socket or device is refused by name): taken from the live
# checkout at two times, the second copy's gate need not be the one the baseline proved green,
# so copies that differ are reported NOT RUN. The runs
# still share PATH, which a baseline changes only through a writable PATH directory, outside
# the example's reach, and the checkout, which the example only reads. A folder the audit
# cannot read fails it by name (os.walk skips one), and its Python runs isolated (-I).
# Deleting a copy changes the mode of its folders only, never of a file, each set by name
# relative to its open parent without following a link: `chmod -R u+rwx` before `rm -rf`
# made a checkout file the baseline had hard-linked into its copy executable, and followed a
# temporary root the baseline had replaced with a symlink. `find -type d -exec chmod` is not
# enough, since chmod resolves the whole path again and a folder swapped for a link in between
# takes it outside. The root's device and inode are recorded when mktemp makes it; a root that
# is no longer that folder is refused by name, and nothing is deleted.
# Copying a large tree (dependencies, build output) costs time, twice: copy only what the
# gate reads if that is known, but never let the probe write into the checkout.
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
# |   probe_copy=
# |   probe_id=
# |   # Only folders of the copy are made writable (a read-only one, a module cache, survives
# |   # `rm -rf`), each by name relative to its open parent and never through a link; the root
# |   # must still be the folder mktemp made (device and inode), or nothing is deleted.
# |   probe_delete() {
# |     [ -z "$probe_copy" ] || {
# |       python3 -I -c '
# | import os, stat, sys
# | path, made = sys.argv[1], sys.argv[2]
# | def refuse(why):
# |     print("  FAIL — existing-file probe: " + why + "; deleted nothing.")
# |     sys.exit(1)
# | def writable(dir_fd, name, made=None):
# |     mode = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
# |     if made is not None and (not stat.S_ISDIR(mode.st_mode) or "%d %d" % (mode.st_dev, mode.st_ino) != made):
# |         refuse(path + " is no longer the directory made for the disposable copy")
# |     if not stat.S_ISDIR(mode.st_mode):
# |         return
# |     if mode.st_mode & 0o700 != 0o700:
# |         os.chmod(name, stat.S_IMODE(mode.st_mode) | 0o700, dir_fd=dir_fd, follow_symlinks=False)
# |     fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
# |     try:
# |         opened = os.fstat(fd)
# |         if made is not None and "%d %d" % (opened.st_dev, opened.st_ino) != made:
# |             refuse(path + " is no longer the directory made for the disposable copy")
# |         for entry in os.listdir(fd):
# |             writable(fd, entry)
# |     finally:
# |         os.close(fd)
# | try:
# |     writable(os.open(os.path.dirname(path), os.O_RDONLY | os.O_DIRECTORY), os.path.basename(path), made)
# | except (OSError, NotImplementedError) as error:
# |     refuse("could not make " + path + " deletable without following a link (" + str(error) + ")")
# | ' "$probe_copy" "$probe_id" && rm -rf "$probe_copy"
# |       probe_gone=$?
# |       probe_copy=
# |       return "$probe_gone"
# |     }
# |   }
# |   # A copy that could not be deleted fails the case, after a run that passed as well.
# |   trap 'probe_exit=$?; probe_delete || [ "$probe_exit" -ne 0 ] || exit 1' EXIT
# |   trap 'exit 130' INT
# |   trap 'exit 143' TERM
# |   probe_fail() { echo "  FAIL — existing-file probe: $*"; exit 1; }
# |   probe_skip() { echo "  NOT RUN — existing-file probe: $*"; exit 1; }
# |   # The copy's own empty HOME and TMPDIR, no system or global git configuration.
# |   probe_env() {
# |     env -i PATH="$PATH" LC_ALL=C HOME="$probe_copy/home" XDG_CONFIG_HOME="$probe_copy/home" \
# |       GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null TMPDIR="$probe_copy/tmp" "$@"
# |   }
# |   [ -d .git ] && [ ! -L .git ] && [ ! -e .git/commondir ] ||
# |     probe_skip "the checkout's .git is not a directory (a linked worktree, a submodule or a separate git directory); this example supports a plain repository only: run the self-test from the main checkout."
# |   probe_target=src/domain/existing.py
# |   probe_gate="$(basename "$(dirname "$0")")/${0##*/}"
# |   # Every symlink resolves inside the copy, no `.git` lies below the top level, and the path to
# |   # the target and to the gate runs through no symlink and ends at a regular file. Prints the
# |   # copy's digest as taken: every entry's path, type, executable bit and content, `.git` included.
# |   probe_audit() {
# |     probe_digest=$(probe_env python3 -I -c '
# | import hashlib, os, stat, sys
# | root = sys.argv[1]
# | digest = hashlib.sha256()
# | # Unreachable by construction (cp -RP fails first on what it cannot read); kept as the guard.
# | def unread(error):
# |     sys.exit("the audit could not read " + os.path.relpath(error.filename or root, root) + " (" + str(error.strerror or error) + ")")
# | try:
# |     for top, dirs, files in os.walk(root, onerror=unread):
# |         dirs.sort()
# |         for name in sorted(dirs + files):
# |             path = os.path.join(top, name)
# |             rel = os.path.relpath(path, root)
# |             if name == ".git" and top != root:
# |                 sys.exit("the checkout contains a nested repository or worktree at " + os.path.relpath(top, root))
# |             mode = os.lstat(path).st_mode
# |             content = hashlib.sha256()
# |             if stat.S_ISDIR(mode):
# |                 kind = b"d"
# |             elif stat.S_ISREG(mode):
# |                 kind = b"x" if mode & stat.S_IXUSR else b"f"
# |                 fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0))
# |                 with open(fd, "rb") as data:
# |                     if not stat.S_ISREG(os.fstat(fd).st_mode):
# |                         sys.exit(rel + " stopped being a regular file while the audit read it")
# |                     for chunk in iter(lambda: data.read(1 << 20), b""):
# |                         content.update(chunk)
# |             elif stat.S_ISLNK(mode):
# |                 kind = b"l"
# |                 content.update(os.fsencode(os.readlink(path)))
# |                 try:
# |                     real = os.path.realpath(path, strict=True)
# |                 except FileNotFoundError:
# |                     real = os.path.realpath(path)
# |                 if os.path.commonpath([root, real]) != root:
# |                     sys.exit(rel + " is a symlink that leads out of the disposable copy")
# |             else:
# |                 sys.exit(rel + " is not a regular file, a folder or a symlink (a FIFO, socket or device)")
# |             digest.update(os.fsencode(rel) + b"\0" + kind + content.hexdigest().encode() + b"\n")
# | except OSError as error:
# |     unread(error)
# | for rel in sys.argv[2:]:
# |     path = root
# |     for part in rel.split("/"):
# |         path = os.path.join(path, part)
# |         if os.path.islink(path):
# |             sys.exit(rel + " runs through a symlink at " + os.path.relpath(path, root))
# |     if not os.path.isfile(path):
# |         sys.exit(rel + " is not a regular file in the disposable copy")
# | print(digest.hexdigest())
# | ' "$probe_root" "$probe_target" "$probe_gate" 2>&1) ||
# |       probe_skip "${probe_digest:-could not search the disposable copy}; the existing-file probe does not support it."
# |   }
# |   probe_allowed="core.repositoryformatversion core.bare extensions.objectformat extensions.refstorage
# |     user.name user.email core.autocrlf core.eol core.safecrlf core.filemode core.ignorecase core.symlinks
# |     core.quotepath core.precomposeunicode core.whitespace core.abbrev init.defaultbranch $probe_config_keys"
# |   probe_noted=
# |   # Each run gets a copy of its own, made by this one function: the checkout's bytes in a fresh
# |   # directory, audited, with empty hooks and only the allowlisted settings.
# |   probe_fresh_copy() {
# |     probe_copy=$(mktemp -d) && probe_copy=$(CDPATH= cd -P "$probe_copy" && pwd -P) || exit 1
# |     probe_id=$(python3 -I -c 'import os, sys; made = os.lstat(sys.argv[1]); print(made.st_dev, made.st_ino)' \
# |       "$probe_copy") || exit 1
# |     case "$probe_copy/" in
# |       "$probe_checkout"/*) probe_fail "the disposable copy ($probe_copy) is inside the checkout; set TMPDIR outside it." ;;
# |     esac
# |     mkdir "$probe_copy/home" "$probe_copy/tmp" || exit 1
# |     cp -RP "$probe_checkout" "$probe_copy/checkout" && CDPATH= cd -P "$probe_copy/checkout" || exit 1
# |     probe_root=$(pwd -P) || exit 1
# |     probe_audit
# |     probe_env git -C "$probe_checkout" config --show-origin --includes --name-only --list > "$probe_copy/names" &&
# |       probe_env git -C "$probe_checkout" config --local --no-includes --show-origin --name-only --list > "$probe_copy/own" &&
# |       probe_env git -C "$probe_checkout" config --local --no-includes --list -z > "$probe_copy/config" ||
# |       probe_fail "could not read the original's configuration (git config); refusing to run."
# |     probe_own=$(LC_ALL=C awk -F '\t' 'NR == 1 { print $1 }' "$probe_copy/own") || exit 1
# |     PROBE_NOTED=$probe_noted PROBE_OWN=$probe_own PROBE_ALLOWED=$probe_allowed LC_ALL=C awk -F '\t' '
# |       BEGIN { n = split(ENVIRON["PROBE_ALLOWED"], k, " "); for (i = 1; i <= n; i++) allowed[k[i]] = 1 }
# |       !($2 in allowed) {
# |         if (ENVIRON["PROBE_NOTED"] == "" && !noted[$2]++)
# |           print "  NOTE — existing-file probe: " $2 " is not carried into the disposable copy; a setting your gate reads goes in probe_config_keys."
# |         next
# |       }
# |       $1 != ENVIRON["PROBE_OWN"] {
# |         print "  FAIL — existing-file probe: " $2 " is set in " $1 ", not in the repository'"'"'s own config file; set it there, or remove it from probe_config_keys."
# |         exit 1
# |       }' "$probe_copy/names" || exit 1
# |     probe_noted=1
# |     { rm -f .git/config.worktree .git/config && rm -rf .git/hooks && mkdir .git/hooks && : > .git/config &&
# |       probe_env PROBE_ALLOWED="$probe_allowed" xargs -0 sh -c '
# |         for probe_entry; do
# |           probe_key=$(printf "%s\n" "$probe_entry" | sed -n 1p) || exit 1
# |           probe_carry=
# |           for probe_allowed in $PROBE_ALLOWED; do [ "$probe_key" != "$probe_allowed" ] || probe_carry=1; done
# |           [ -n "$probe_carry" ] || continue
# |           if [ "$probe_entry" != "$probe_key" ]; then
# |             git config --file .git/config --add "$probe_key" "${probe_entry#"$probe_key"?}" || exit 1
# |           else
# |             # A valueless key (no newline in the entry) has no `git config` syntax: append it.
# |             probe_section=${probe_key%.*}
# |             case $probe_section in
# |               *.*) probe_sub=$(printf "%s\n" "${probe_section#*.}" | sed "s/[\\\\\"]/\\\\&/g") || exit 1
# |                    probe_section="${probe_section%%.*} \"$probe_sub\"" ;;
# |             esac
# |             printf "[%s]\n\t%s\n" "$probe_section" "${probe_key##*.}" >> .git/config || exit 1
# |           fi
# |         done' sh < "$probe_copy/config"; } ||
# |       probe_fail "could not carry the allowlisted settings into the disposable copy; refusing to run."
# |   }
# |   probe_fresh_copy
# |   probe_first=$probe_digest
# |   probe_env sh "$probe_root/$probe_gate" >/dev/null 2>&1 ||
# |     probe_fail "the baseline is already red; the injection would prove nothing."
# |   cd / && probe_delete ||
# |     probe_fail "could not delete the baseline run's copy; refusing to run."
# |   probe_fresh_copy
# |   [ "$probe_digest" = "$probe_first" ] ||
# |     probe_skip "the checkout changed between the two copies; run the self-test again."
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
