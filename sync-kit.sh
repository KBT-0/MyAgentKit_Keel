#!/usr/bin/env sh
# MyAgentKit_Keel — propagate kit updates into a project that already installed it.
#
# Usage: sync-kit.sh [TARGET_DIR] [--dry-run] [--actions-applied]
#
# Two tiers of ownership, and the line between them is drawn in the files themselves:
#
#   KIT-OWNED    the file carries a "KIT-OWNED" marker in its header. It holds no project
#                content, so this script overwrites it wholesale. A file at that path in the
#                project WITHOUT the marker is the project's own: listed as a conflict, and
#                the sync stops before it copies anything or records a version.
#   PROJECT-OWNED  everything else. Never touched. Most of the kit is project-owned by
#                design — the constitution, the workflow, the gate and the boundary checks
#                are all customised during setup, and overwriting them would throw that away
#                (and re-introduce the placeholders).
#
# So a sync is: refresh the few generic files, then PRINT the changelog entries added since
# your version so you can apply the rest deliberately. That second half is the real product.
# A tool that silently merged process rules into a working project would be worse than no
# tool at all.
#
# The recorded version (docs/kit/.kit-version) means "the owner has applied everything up to
# here", not "the files were copied". While the printed entries hold an **ACTION** item, the
# version stays put, the items are printed again on every run, and the exit status is 2.
# Rerun with --actions-applied once you have applied them; only then is the version recorded.
#
# A failed write stops the run before the stamp (`set -e`, and the copy step names its file):
# a failed chmod was ignored and the version recorded over a hook that could not run.
#
# Threat model. The owner runs this in the owner's own project. It protects against its own
# failures and interruptions: a failed write, a full disk, INT, TERM or HUP part way, and a
# retry after any of them; and against honest mistakes in the tree: a file, folder, symlink or
# special file where it means to write is refused by name, never written through. By decision
# it does NOT protect against another process changing the tree while it runs (a checked path
# swapped between the check and the write), files placed in the project to attack it, or
# SIGKILL or power loss between two steps. Whoever can do the first two can write the same
# files directly.
set -eu

kit=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target="."
dry=0
applied=0

die() { printf '%s\n' "sync-kit: $1" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry=1; shift ;;
    --actions-applied) applied=1; shift ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    -*)        die "unknown option: $1" ;;
    *)         target="$1"; shift ;;
  esac
done

target=$(CDPATH= cd -- "$target" 2>/dev/null && pwd) || die "no such directory"
[ "$target" = "$kit" ] && die "refusing to sync the kit with itself"

# blocked REL [dir] — the one check for every path the sync reads or writes (the kit-owned
# files and the version stamp): prints why REL may not be used, nothing
# when it may. Every existing component below the target must be a real folder, and REL itself
# absent or a regular file (with `dir`, which only bootstrap.sh uses: absent or a real folder).
# What fails is not opened: `cmp` on a FIFO blocked forever; a symlink, or a symlinked
# folder above, carried the read or write outside the project; a file where a folder belongs
# failed the copy midway through the copies. The target itself may be a symlink: the owner
# named it. bootstrap.sh holds the same function; a test holds the two copies equal.
# The check runs BEFORE the write, not with it (the threat model above).
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

# perms FILE — FILE's permission bits in octal, read from `ls -l` (POSIX has no portable stat).
perms() {
  ls -ld -- "$1" | awk '{ m = 0; for (i = 2; i <= 10; i++) m = m * 2 + (substr($1, i, 1) !~ /[-ST]/); printf "%o\n", m }'
}

# put DEST [SRC] — the one writer: DEST gets SRC's content (stdin without SRC) whole or not at
# all, through a temporary that `mv` moves over it. A redirection or `cp` empties DEST before
# writing, so a full disk left an empty stamp or a gate cut short. The temporary is created
# fresh by `mktemp` (exclusively, never an existing file) in DEST's folder: a fixed name
# trusted what was there, so a hard link to the stamp had a failed write empty the stamp and an
# owner's file at that name was overwritten. `part` names it for the exit trap, which removes
# only that. It carries DEST's own mode, or for a new file the mode a plain `cp` (or
# redirection) gives under the umask, set before a byte is written: a temporary made under the
# umask turned a 0600 note into 0644. It is opened before the chmod, so a mode without write
# permission still takes the content. `stage` is all of it but the `mv`.
stage() {
  if [ -e "$1" ]; then _m=$(perms "$1")
  elif [ -n "${2:-}" ]; then _m=$(perms "$2")
  else _m=666; fi
  [ -e "$1" ] || _m=$(printf '%o' $(( 0$_m & ~0$(umask) )))
  part=$(mktemp "${1%/*}/.kit-tmp.XXXXXX") &&
    { chmod "$_m" "$part" && cat "${2:--}"; } > "$part"
}
put() {
  stage "$@" && mv -f "$part" "$1" && part=""
}

why=$(blocked docs/kit/.kit-version)
[ -z "$why" ] || die "conflict: docs/kit/.kit-version ($why); the version is not read or written there"
stamp="$target/docs/kit/.kit-version"
part=""
[ -f "$stamp" ] || die "$stamp not found — this project was not installed with bootstrap.sh"
have=$(tr -d '[:space:]' < "$stamp")
[ -n "$have" ] || die "$stamp is empty; refusing to guess which version this project has"

latest=$(sed -n 's/^## v\([0-9][0-9.]*\).*/\1/p' "$kit/CHANGELOG.md" | head -1)
[ -n "$latest" ] || die "cannot read a version from $kit/CHANGELOG.md"

work_list=$(mktemp) || { echo "sync-kit: cannot create a temp file" >&2; exit 1; }
pending=$(mktemp) || { rm -f "$work_list"; echo "sync-kit: cannot create a temp file" >&2; exit 1; }
copies=$(mktemp) || { rm -f "$work_list" "$pending"; echo "sync-kit: cannot create a temp file" >&2; exit 1; }
# A signal handler that only cleaned up let the run resume with the pending list deleted,
# which reads as "no ACTION items" and stamped the version: a signal now ends the run.
trap 'rm -f "$work_list" "$pending" "$copies" ${part:+"$part"}' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# A temporary a stopped run left behind (`put` names them .kit-tmp.*) is not this run's to
# delete: it is named, for the owner to remove.
left=$(cd "$target" && find . -name .git -prune -o -type f -name '.kit-tmp.*' -print 2>/dev/null) || :
[ -z "$left" ] || printf '%s\n' "sync-kit: NOTE: temporaries a stopped run left behind; remove them:" "$left"

printf '%s\n' "sync-kit: project has v$have, kit is v$latest"
if [ "$have" = "$latest" ]; then
  echo "sync-kit: already current. Nothing to do."
  exit 0
fi

# --- tier 1: overwrite the kit-owned files ------------------------------------------
echo
echo "KIT-OWNED files (overwritten):"
found=0
conflict=0
kit_conflict=0
overlay_fix=''
# Read the list line by line rather than through word splitting: a path containing a space
# would otherwise be torn into two nonexistent paths and silently skipped.
#
# The marker is matched ANCHORED at the start of a line, as a header comment. Matching the
# bare phrase anywhere once meant a document that merely MENTIONED "KIT-OWNED" in prose
# would have been silently overwritten wholesale.
grep -rlE '^(# |<!-- )KIT-OWNED:' "$kit/core" "$kit/setup" "$kit/overlays" 2>/dev/null \
  | sort > "$work_list"
relpath() {
  overlay=0
  case "$1" in
    "$kit/core/"*)             rel=${1#"$kit/core/"} ;;
    "$kit/setup/"*)            rel="setup/${1#"$kit/setup/"}" ;;
    "$kit/overlays/"*/files/*) rel=${1#"$kit"/overlays/*/files/}; overlay=1 ;;
    *) return 1 ;;
  esac
}
while IFS= read -r src; do
  [ -n "$src" ] || continue
  relpath "$src" || continue
  why=$(blocked "$rel")
  # An overlay file is synced only where it already exists: its presence is the only record
  # of whether the project took that overlay, and installing an overlay is bootstrap's job.
  # A symlink in its path is no absence: a dangling one fails `-e` and was skipped without a
  # word, and a symlinked folder had the kit's file written through it outside the project.
  if [ "$overlay" -eq 1 ] && [ ! -e "$target/$rel" ]; then
    case "$why" in "symlink: "*) ;; *) continue ;; esac
  fi
  found=1
  if [ -n "$why" ]; then
    printf '%s\n' "  conflict: $rel ($why, so it is the project's)"
    conflict=1
    if [ "$overlay" -eq 1 ]; then overlay_fix="$overlay_fix
    $src -> $rel"; else kit_conflict=1; fi
    continue
  elif [ ! -e "$target/$rel" ]; then
    printf '%s\n' "  new:     $rel"
  elif cmp -s "$src" "$target/$rel"; then
    # Listed for the copy step all the same: same content is not the same file while the
    # executable bit is missing (a chmod that failed on an earlier run), and that step sets it.
    printf '%s\n' "  same:    $rel"
  elif grep -qE '^(# |<!-- )KIT-OWNED:' "$target/$rel" 2>/dev/null; then
    printf '%s\n' "  update:  $rel"
  elif [ "$overlay" -eq 1 ]; then
    # An overlay file without the header is the kit's own copy from before the header (a
    # v0.8 spawn_worker.sh): the sync never installs an absent overlay file, so it is
    # replaced by hand, never moved aside, and there is nothing of the project to retrofit.
    printf '%s\n' "  conflict: $rel (the kit's own file from an earlier version, without the KIT-OWNED header)"
    conflict=1
    overlay_fix="$overlay_fix
    $src -> $rel"
    continue
  else
    # No KIT-OWNED header: the project's own file at a path the kit now owns (a project's
    # own commit-msg hook once, replaced by the kit's that passed every message). Listed,
    # never overwritten; nothing else is copied either, so the sync is all or nothing.
    printf '%s\n' "  conflict: $rel (exists without the KIT-OWNED header, so it is the project's)"
    conflict=1
    kit_conflict=1
    continue
  fi
  printf '%s\n' "$src" >> "$copies" || die "cannot record $rel for copying; version left at v$have"
done < "$work_list"
[ "$found" -eq 1 ] || echo "  (none)"
if [ "$conflict" -eq 1 ] && [ "$dry" -eq 0 ]; then
  cat <<EOF

STOPPING: the files listed as conflict stand at paths the kit owns now. Nothing was copied
and the version stays at v$have.
EOF
  [ "$kit_conflict" -eq 0 ] || cat <<EOF

  A core or setup file listed is project-owned (no KIT-OWNED header, not a regular file, or
  a symlink or a file in its path). For each one: move yours aside, rerun the sync to install
  the kit's file, then carry what yours did into the project's own files by hand (the kit's
  docs/RETROFIT.md).
EOF
  [ -z "$overlay_fix" ] || cat <<EOF

  An overlay file listed is the kit's own file from an earlier version. Replace each one
  with the kit's current copy below, then sync again. A symlink or a symlinked folder on the
  way becomes a real file or folder first. A project that edited its copy carries those
  edits into the new copy by hand.$overlay_fix
EOF
  exit 1
fi
# exe FILE — the one place that decides which kit-owned files must be executable (the hooks
# and scripts git or a gate runs directly), for a copied file and an identical one alike. A
# hook git cannot run is skipped without a word, and a gate that cannot run is not there.
exe() { case "$rel" in *.sh|.githooks/*|.claude/hooks/*) chmod +x "$1" ;; esac; }
if [ "$dry" -eq 0 ]; then
  while IFS= read -r src; do
    relpath "$src"
    { cmp -s "$src" "$target/$rel" || { mkdir -p "$target/$(dirname "$rel")" && put "$target/$rel" "$src"; }; } &&
      exe "$target/$rel" || die "could not write $rel; version left at v$have"
  done < "$copies"
fi

# --- tier 2: print what has to be applied by hand -----------------------------------
# Everything from the top of the changelog down to (but not including) the recorded
# version. If the recorded version is not in the changelog, print the lot and say so
# rather than printing nothing — an empty report would read as "no changes".
echo
echo "=============================================================================="
printf '%s\n' " Changelog since v$have — apply these to your PROJECT-OWNED files by hand"
echo "=============================================================================="
# The recorded version is matched as an exact FIELD, never as a prefix: `index()` against
# "## v0.1" also matched "## v0.10", so the slice stopped at the wrong heading and printed
# an empty report — which reads as "no changes". (`\b` was no fix either; it is a GNU grep
# extension, not POSIX.)
if awk -v want="v$have" '$1 == "##" && $2 == want { found = 1 } END { exit !found }' \
    "$kit/CHANGELOG.md"; then
  awk -v want="v$have" '
    $1 == "##" && $2 == want { exit }
    /^## v/ { p = 1 }
    p
  ' "$kit/CHANGELOG.md"
else
  printf '%s\n' "(v$have is not in this changelog — printing all of it. Check that the recorded"
  echo " version is right.)"
  echo
  cat "$kit/CHANGELOG.md"
fi

# The ACTION items between the recorded version and the top (all of them if the recorded
# version is unknown), repeated as a checklist. Stamping past them unconfirmed once made the
# next run say "already current" while the hand edits had never been made. A scan that
# failed leaves the list empty, which reads as "no ACTION items": it stops the sync instead.
#
# Each item is printed from its marker to the end of its list item or paragraph (up to a
# blank line, a heading or the next list item): printing only the marker's own line cut
# items mid-sentence.
awk -v want="v$have" '
  $1 == "##" && $2 == want { exit }
  /^## v/ { v = $2; item = 0; next }
  item && /[^ \t]/ && !/^#/ && !/^[ \t]*([-*]|[0-9]+\.)[ \t]/ {
    sub(/^[ \t]+/, ""); print "      " $0; next
  }
  { item = 0 }
  v && /\*\*ACTION/ && !/\*\*ACTION\*\* — none/ {
    print "  " v ": " substr($0, index($0, "**ACTION")); item = 1
  }
' "$kit/CHANGELOG.md" > "$pending" ||
  die "cannot scan the changelog for ACTION items; version left at v$have. Rerun once awk can read $kit/CHANGELOG.md."

if [ -s "$pending" ]; then
  echo
  printf '%s\n' "ACTION items since v$have (the full entries are above):"
  cat "$pending"
fi

if [ "$dry" -eq 1 ]; then
  echo
  printf '%s\n' "sync-kit: dry run — nothing written, version left at v$have."
  exit 0
fi

if [ -s "$pending" ] && [ "$applied" -eq 0 ]; then
  echo
  printf '%s\n' "sync-kit: version left at v$have: the ACTION items above are not confirmed."
  printf '%s\n' "          Apply them, then rerun with --actions-applied to record v$latest."
  echo "          Until then every sync prints them again."
  exit 2
fi

put "$stamp" <<EOF || die "could not write $stamp; version left at v$have"
$latest
EOF
echo
printf '%s\n' "sync-kit: recorded v$latest."
echo "sync-kit: now run ./scripts/check.sh, and ./scripts/check.sh --self-test."
echo "          A sync that leaves the gate red or a gate unable to fail is not finished."
