#!/usr/bin/env sh
# MyAgentKit_Keel — mechanical install. Copy, mkdir, wire the hooks path, record the version.
#
# It asks NOTHING and fills NOTHING in. Every decision the kit needs — what is risky here,
# which boundaries must be enforced, what the gates are — is made in a conversation with an
# agent afterwards (setup/INTERVIEW.md), because a script cannot ask a follow-up question
# and a form filled in blindly produces rules nobody believes.
#
# Usage: bootstrap.sh [TARGET_DIR] [--overlay NAME]... [--note "..."] [--force]
#
#   TARGET_DIR   where to install (default: the current directory)
#   --overlay    add a per-stack overlay, e.g. --overlay unity. Repeatable.
#   --note       an agenda for the setup conversation; written to
#                docs/kit/BOOTSTRAP_NOTE.md and read in Phase 0 of the interview.
#   --force      overwrite files that already exist (default: skip them and report)
#
# Existing files are SKIPPED by default so this is safe to run inside a project that is
# already under way — a retrofit is incremental, never a big bang.
set -u

kit=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target="."
note=""
force=0
overlays=""

die() { echo "bootstrap: $1" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --overlay) [ $# -ge 2 ] || die "--overlay needs a name"; overlays="$overlays $2"; shift 2 ;;
    --note)    [ $# -ge 2 ] || die "--note needs a value";   note="$2";              shift 2 ;;
    --force)   force=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    -*)        die "unknown option: $1" ;;
    *)         target="$1"; shift ;;
  esac
done

[ -d "$target" ] || mkdir -p "$target" || die "cannot create $target"
target=$(CDPATH= cd -- "$target" && pwd)
[ "$target" = "$kit" ] && die "refusing to install the kit into itself"

# The version a project records is the one thing sync-kit.sh has to trust later, so read it
# from the changelog and STOP if it is not there. A blank version silently disables every
# future sync — absent evidence is a failure, not a default.
version=$(sed -n 's/^## v\([0-9][0-9.]*\).*/\1/p' "$kit/CHANGELOG.md" 2>/dev/null | head -1)
[ -n "$version" ] || die "cannot read a version from $kit/CHANGELOG.md — refusing to record a blank one"

skiplist=$(mktemp)
trap 'rm -f "$skiplist"' EXIT

# copy_tree SRC [DEST_PREFIX] — copies SRC's contents into the target, optionally under a
# subdirectory. Existing files are recorded and left alone unless --force.
copy_tree() {
  src="$1"
  prefix="${2:-}"
  [ -d "$src" ] || return 0
  # The loop below reads one filename per LINE, so a name containing a newline would be
  # torn in two and copied wrong — refuse it outright. The kit controls its own tree, so
  # this only ever fires on a corrupted or hand-mangled checkout.
  if find "$src" -name "$(printf '*\n*')" 2>/dev/null | grep -q .; then
    die "a filename under $src contains a newline; refusing to copy blind"
  fi
  ( cd "$src" && find . -type f -print ) | sed 's|^\./||' | while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    # Running Python tooling must not change the installed skeleton with local bytecode.
    case "$rel" in __pycache__/*|*/__pycache__/*|*.pyc|*.pyo) continue ;; esac
    dest="${prefix:+$prefix/}$rel"
    if [ -e "$target/$dest" ] && [ "$force" -eq 0 ]; then
      echo "$dest" >> "$skiplist"
      continue
    fi
    mkdir -p "$target/$(dirname "$dest")"
    cp "$src/$rel" "$target/$dest"
  done
}

echo "bootstrap: installing MyAgentKit_Keel v$version into $target"

copy_tree "$kit/core"
copy_tree "$kit/setup" "setup"

for name in $overlays; do
  [ -d "$kit/overlays/$name/files" ] || die "no such overlay: $name (looked in $kit/overlays/$name/files)"
  echo "bootstrap: overlay '$name'"
  copy_tree "$kit/overlays/$name/files"
done

mkdir -p "$target/docs/reviews" "$target/docs/audits" \
         "$target/docs/worktree-notes" "$target/docs/spikes" "$target/docs/kit"

# The executable bit does not survive every filesystem, and a gate that cannot run is a
# gate that is not there. CI dies on this with exit 126 (docs/GOTCHAS.md).
for f in "$target"/scripts/*.sh "$target"/.githooks/* "$target"/.claude/hooks/*; do
  [ -f "$f" ] && chmod +x "$f"
done

if [ -s "$skiplist" ]; then
  echo
  echo "bootstrap: $(wc -l < "$skiplist") file(s) already existed and were left alone:"
  sed 's/^/             /' "$skiplist"
  echo "           Merge by hand, or re-run with --force to overwrite."
fi

# A retrofit that skipped the ENFORCEMENT files installed no enforcement, and saying so in
# a list the reader skims is not enough: the installer would report success while the
# repository's existing (possibly no-op) gate stays in place. That is the fail-open shape
# this kit exists to prevent, so it is a hard stop rather than a note.
#
# The stop comes BEFORE the version stamp, the note and the hooks wiring: an earlier
# version stamped .kit-version first and then refused — after which sync-kit.sh greeted the
# gateless project with "already current. Nothing to do."
if grep -qE '^(scripts/check\.sh|\.githooks/pre-commit)$' "$skiplist" 2>/dev/null; then
  cat <<'EOF'

STOPPING: the gate files already existed and were NOT replaced.

  scripts/check.sh and .githooks/pre-commit are the enforcement. Whatever is in this
  repository now is what will run — and if it is a no-op, this install just gave you the
  paperwork of a gate with none of the gate.

  Decide deliberately, then re-run:
    - keep yours:      merge the kit's checks into your script by hand (docs/RETROFIT.md)
    - take the kit's:  re-run with --force, then re-add your own checks
  Either way, finish with:  ./scripts/check.sh --self-test
EOF
  exit 1
fi

printf '%s\n' "$version" > "$target/docs/kit/.kit-version"

if [ -n "$note" ]; then
  {
    echo "# Bootstrap note — the owner's agenda for this setup"
    echo
    echo "Written by \`bootstrap.sh --note\` on $(date -u +%Y-%m-%d). The setup interview"
    echo "reads this in Phase 0 and must address it explicitly rather than working around it."
    echo
    printf '%s\n' "$note"
  } > "$target/docs/kit/BOOTSTRAP_NOTE.md"
  echo "bootstrap: wrote docs/kit/BOOTSTRAP_NOTE.md"
fi

if git -C "$target" rev-parse --git-dir >/dev/null 2>&1; then
  git -C "$target" config core.hooksPath .githooks
  echo "bootstrap: wired core.hooksPath -> .githooks"
else
  echo "bootstrap: NOT a git repository yet. After 'git init', run:"
  echo "             git config core.hooksPath .githooks"
  echo "           Without it there is no commit gate (docs/DEV_SETUP.md)."
fi

cat <<'EOF'

Foundation copied. Now open your CLI agent here and say:

  "Read setup/INTERVIEW.md and start the setup."

Nothing is configured yet, and ./scripts/check.sh will FAIL until the interview fills in
the placeholders. That failure is the point: it is the gate telling you the truth about a
project that has not been set up.
EOF
