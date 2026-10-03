#!/usr/bin/env sh
# MyAgentKit_Keel — propagate kit updates into a project that already installed it.
#
# Usage: sync-kit.sh [TARGET_DIR] [--dry-run] [--actions-applied]
#
# Two tiers of ownership, and the line between them is drawn in the files themselves:
#
#   KIT-OWNED    the file carries a "KIT-OWNED" marker in its header. It holds no project
#                content, so this script overwrites it wholesale.
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
set -u

kit=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target="."
dry=0
applied=0

die() { echo "sync-kit: $1" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry=1; shift ;;
    --actions-applied) applied=1; shift ;;
    -h|--help) sed -n '2,23p' "$0"; exit 0 ;;
    -*)        die "unknown option: $1" ;;
    *)         target="$1"; shift ;;
  esac
done

target=$(CDPATH= cd -- "$target" 2>/dev/null && pwd) || die "no such directory"
[ "$target" = "$kit" ] && die "refusing to sync the kit with itself"

stamp="$target/docs/kit/.kit-version"
[ -f "$stamp" ] || die "$stamp not found — this project was not installed with bootstrap.sh"
have=$(tr -d '[:space:]' < "$stamp")
[ -n "$have" ] || die "$stamp is empty; refusing to guess which version this project has"

latest=$(sed -n 's/^## v\([0-9][0-9.]*\).*/\1/p' "$kit/CHANGELOG.md" | head -1)
[ -n "$latest" ] || die "cannot read a version from $kit/CHANGELOG.md"

work_list=$(mktemp) || { echo "sync-kit: cannot create a temp file" >&2; exit 1; }
pending=$(mktemp) || { rm -f "$work_list"; echo "sync-kit: cannot create a temp file" >&2; exit 1; }
trap 'rm -f "$work_list" "$pending"' EXIT INT TERM

echo "sync-kit: project has v$have, kit is v$latest"
if [ "$have" = "$latest" ]; then
  echo "sync-kit: already current. Nothing to do."
  exit 0
fi

# --- tier 1: overwrite the kit-owned files ------------------------------------------
echo
echo "KIT-OWNED files (overwritten):"
found=0
# Read the list line by line rather than through word splitting: a path containing a space
# would otherwise be torn into two nonexistent paths and silently skipped.
#
# The marker is matched ANCHORED at the start of a line, as a header comment. Matching the
# bare phrase anywhere once meant a document that merely MENTIONED "KIT-OWNED" in prose
# would have been silently overwritten wholesale.
grep -rlE '^(# |<!-- )KIT-OWNED:' "$kit/core" "$kit/setup" "$kit/overlays" 2>/dev/null \
  | sort > "$work_list"
while IFS= read -r src; do
  [ -n "$src" ] || continue
  overlay=0
  case "$src" in
    "$kit/core/"*)             rel=${src#"$kit/core/"} ;;
    "$kit/setup/"*)            rel="setup/${src#"$kit/setup/"}" ;;
    "$kit/overlays/"*/files/*) rel=${src#"$kit"/overlays/*/files/}; overlay=1 ;;
    *) continue ;;
  esac
  # An overlay file is synced only where it already exists: its presence is the only record
  # of whether the project took that overlay, and installing an overlay is bootstrap's job.
  if [ "$overlay" -eq 1 ] && [ ! -e "$target/$rel" ]; then
    continue
  fi
  found=1
  if [ ! -e "$target/$rel" ]; then
    echo "  new:     $rel"
  elif cmp -s "$src" "$target/$rel"; then
    echo "  same:    $rel"
    continue
  else
    echo "  update:  $rel"
  fi
  [ "$dry" -eq 1 ] && continue
  mkdir -p "$target/$(dirname "$rel")"
  cp "$src" "$target/$rel"
  case "$rel" in *.sh|.githooks/*) chmod +x "$target/$rel" ;; esac
done < "$work_list"
[ "$found" -eq 1 ] || echo "  (none)"

# --- tier 2: print what has to be applied by hand -----------------------------------
# Everything from the top of the changelog down to (but not including) the recorded
# version. If the recorded version is not in the changelog, print the lot and say so
# rather than printing nothing — an empty report would read as "no changes".
echo
echo "=============================================================================="
echo " Changelog since v$have — apply these to your PROJECT-OWNED files by hand"
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
  echo "(v$have is not in this changelog — printing all of it. Check that the recorded"
  echo " version is right.)"
  echo
  cat "$kit/CHANGELOG.md"
fi

# The ACTION items between the recorded version and the top (all of them if the recorded
# version is unknown), repeated as a checklist. Stamping past them unconfirmed once made the
# next run say "already current" while the hand edits had never been made.
awk -v want="v$have" '
  $1 == "##" && $2 == want { exit }
  /^## v/ { v = $2 }
  v && /\*\*ACTION/ { print "  " v ": " $0 }
' "$kit/CHANGELOG.md" > "$pending"

if [ -s "$pending" ]; then
  echo
  echo "ACTION items since v$have (the full entries are above):"
  cat "$pending"
fi

if [ "$dry" -eq 1 ]; then
  echo
  echo "sync-kit: dry run — nothing written, version left at v$have."
  exit 0
fi

if [ -s "$pending" ] && [ "$applied" -eq 0 ]; then
  echo
  echo "sync-kit: version left at v$have: the ACTION items above are not confirmed."
  echo "          Apply them, then rerun with --actions-applied to record v$latest."
  echo "          Until then every sync prints them again."
  exit 2
fi

printf '%s\n' "$latest" > "$stamp"
echo
echo "sync-kit: recorded v$latest."
echo "sync-kit: now run ./scripts/check.sh, and ./scripts/check.sh --self-test."
echo "          A sync that leaves the gate red or a gate unable to fail is not finished."
