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
#   --force      overwrite files that already exist and differ (default: skip and report)
#
# Existing files are SKIPPED by default so this is safe to run inside a project that is
# already under way — a retrofit is incremental, never a big bang. A file byte-identical to
# the kit's is what an earlier run copied, not a conflict, so a re-run after a STOP names
# only the files that still differ.
#
# A failed write stops the run (`set -e`): with only `set -u`, a failed mkdir, cp or chmod
# was ignored and the version was stamped and the hooks wired over a short install.
set -eu

kit=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target="."
note=""
force=0
overlays=""
said=""

die() { said=1; echo "bootstrap: $1" >&2; exit 1; }

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
target=$(CDPATH= cd -- "$target" && pwd) || die "cannot enter $target"
[ "$target" = "$kit" ] && die "refusing to install the kit into itself"

# The version a project records is the one thing sync-kit.sh has to trust later, so read it
# from the changelog and STOP if it is not there. A blank version silently disables every
# future sync — absent evidence is a failure, not a default.
version=$(sed -n 's/^## v\([0-9][0-9.]*\).*/\1/p' "$kit/CHANGELOG.md" 2>/dev/null | head -1)
[ -n "$version" ] || die "cannot read a version from $kit/CHANGELOG.md — refusing to record a blank one"

skiplist=$(mktemp) || die "cannot create a temp file"
# A stop that `set -e` made says so: the failing command named its path, this says what it means.
trap 'rc=$?; rm -f "$skiplist"; [ "$rc" -eq 0 ] || [ -n "$said" ] ||
  echo "bootstrap: stopped by the failure above, before the version was recorded" >&2' EXIT

# blocked REL [dir] — the one check for every path bootstrap writes or creates (copied files,
# the files it generates, the folders it makes): prints why REL may not be written, nothing
# when it may. Every existing component below the target must be a real folder, and REL
# itself absent or a regular file (with `dir`: absent or a real folder). What fails is never
# opened: `cmp` on a FIFO, or writing to one, blocked forever; a symlink, or a symlinked folder
# above, carried the read or write outside the project; a file where a folder belongs made
# every mkdir and cp under it fail. The target itself may be a symlink: the owner named it.
blocked() {
  _rest=$1; _p=""
  while :; do
    _p=${_p:+$_p/}${_rest%%/*}
    case "$_rest" in */*) _rest=${_rest#*/} ;; *) break ;; esac
    if [ -L "$target/$_p" ]; then printf 'symlink: %s\n' "$_p"; return 0; fi
    if [ -e "$target/$_p" ] && [ ! -d "$target/$_p" ]; then printf 'not a folder: %s\n' "$_p"; return 0; fi
  done
  if [ -L "$target/$_p" ]; then printf 'symlink: %s\n' "$_p"
  elif [ ! -e "$target/$_p" ]; then :
  elif [ "${2:-}" = dir ]; then [ -d "$target/$_p" ] || echo 'not a folder'
  else [ -f "$target/$_p" ] || echo 'not a regular file'
  fi
}

# copy_tree SRC [DEST_PREFIX] — copies SRC's contents into the target, optionally under a
# subdirectory. Existing files that differ are recorded and left alone unless --force;
# identical ones are passed over (an earlier run put them there).
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
    # Only a destination `blocked` passes is compared or replaced; anything else is listed, unread.
    if [ -n "$(blocked "$dest")" ]; then
      echo "$dest" >> "$skiplist"
      continue
    fi
    if [ -e "$target/$dest" ] && [ "$force" -eq 0 ]; then
      cmp -s "$src/$rel" "$target/$dest" && continue
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

# The folders and files bootstrap makes itself pass the same check: one it may not write is
# a conflict that stops the run, like a kept gate, and is never created or opened. The files
# are written only after the stop below.
own="docs/reviews docs/audits docs/worktree-notes docs/spikes docs/kit docs/kit/.kit-version"
[ -z "$note" ] || own="$own docs/kit/BOOTSTRAP_NOTE.md"
stops=""
for d in $own; do
  case "$d" in docs/kit/*) kind=file ;; *) kind=dir ;; esac
  why=$(blocked "$d" "$kind")
  if [ -n "$why" ]; then
    stops="$stops$d ($why)
"
  elif [ "$kind" = dir ]; then
    mkdir -p "$target/$d"
  fi
done

# The executable bit does not survive every filesystem, and a gate that cannot run is a
# gate that is not there. CI dies on this with exit 126 (docs/GOTCHAS.md). Only on what
# `blocked` passes: chmod through a symlink changes the file it points to, outside the project.
for f in "$target"/scripts/*.sh "$target"/.githooks/* "$target"/.claude/hooks/*; do
  if [ -e "$f" ] && [ -z "$(blocked "${f#"$target"/}")" ]; then chmod +x "$f"; fi
done

if [ -s "$skiplist" ]; then
  echo
  echo "bootstrap: $(wc -l < "$skiplist") file(s) already existed, differ from the kit's, and were left alone:"
  sed 's/^/             /' "$skiplist"
  echo "           Merge the kit's content into each by hand, or move it aside and re-run;"
  echo "           --force overwrites each one that is a regular file, never a symlink,"
  echo "           folder or special file."
fi

# A retrofit that skipped the ENFORCEMENT files installed no enforcement, and saying so in
# a list the reader skims is not enough: the installer would report success while the
# repository's existing (possibly no-op) gate stays in place. That is the fail-open shape
# this kit exists to prevent, so it is a hard stop rather than a note.
#
# The stop comes BEFORE the version stamp, the note and the hooks wiring: an earlier
# version stamped .kit-version first and then refused — after which sync-kit.sh greeted the
# gateless project with "already current. Nothing to do."
gates=$(grep -E '^(scripts/check\.sh|\.githooks/(pre-commit|pre-merge-commit|commit-msg))$' "$skiplist" 2>/dev/null |
  while IFS= read -r g; do why=$(blocked "$g"); printf '%s%s\n' "$g" "${why:+ ($why)}"; done)
# Two lists: only a gate conflict means missing enforcement; a folder or file bootstrap makes
# itself (docs/reviews, the stamp) is a plain destination that could not be written.
if [ -n "$gates" ]; then
  echo
  echo "STOPPING: the gate files already existed, differ from the kit's, and were NOT replaced:"
  printf '%s\n' "$gates" | sed 's/^/  conflict: /'
  cat <<'EOF'

  They are the enforcement. Whatever is in this repository now is what will run — and if
  it is a no-op, this install just gave you the paperwork of a gate with none of the gate.

  For each one: move yours aside, re-run to install the kit's file (files an earlier run
  copied are identical and pass), then carry what yours did into it by hand (docs/RETROFIT.md).
  --force instead overwrites EVERY differing regular file listed above, not only these;
  a symlink, folder or special file at such a path, or a symlink or a file in its path,
  is never replaced: move it aside.
  Finish with:  ./scripts/check.sh --self-test
EOF
fi
if [ -n "$stops" ]; then
  echo
  echo "STOPPING: these destinations could not be written:"
  printf '%s' "$stops" | sed 's/^/  conflict: /'
  echo "  Move each one, or what is in its path, aside and re-run."
fi
if [ -n "$gates$stops" ]; then
  said=1
  echo
  echo "bootstrap: the version was not recorded and core.hooksPath was not set."
  exit 1
fi

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

# The stamp is the LAST write, so it records only an install whose every write succeeded:
# sync-kit.sh trusts it, and a stamp over a short install answers "already current".
printf '%s\n' "$version" > "$target/docs/kit/.kit-version"

cat <<'EOF'

Foundation copied. Now open your CLI agent here and say:

  "Read setup/INTERVIEW.md and start the setup."

Nothing is configured yet, and ./scripts/check.sh will FAIL until the interview fills in
the placeholders. That failure is the point: it is the gate telling you the truth about a
project that has not been set up.
EOF
