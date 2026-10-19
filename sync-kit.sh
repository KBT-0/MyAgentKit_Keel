#!/usr/bin/env sh
# MyAgentKit_Keel — propagate kit updates into a project that already installed it.
#
# Usage: sync-kit.sh [TARGET_DIR] [--dry-run] [--actions-applied] [--merge [--base KIT_COMMIT]]
#
# --merge also merges the kit's changes into the project-owned files (git merge-file, from the
# kit commit recorded in docs/kit/.kit-commit or named with --base) and lists what is left.
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
# So a sync is: refresh the few generic files, then list the changelog's ACTION items added
# since your version so you can apply the rest deliberately. That second half is the real
# product. A tool that silently merged process rules into a working project would be worse
# than no tool at all.
#
# The recorded version (docs/kit/.kit-version) means "the owner has applied everything up to
# here", not "the files were copied". While an **ACTION** item is pending, the version stays
# put, the items are written oldest first to docs/kit/UPGRADE.md with a box each, and the exit
# status is 2. Tick each box as you apply its item, then rerun with --actions-applied: only
# when every box is ticked is the version recorded, and the checklist deleted.
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
merge=0
base_ref=""

die() { printf '%s\n' "sync-kit: $1" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry=1; shift ;;
    --actions-applied) applied=1; shift ;;
    --merge) merge=1; shift ;;
    --base) [ $# -ge 2 ] || die "--base needs a kit commit"; base_ref=$2; shift 2 ;;
    -h|--help) sed -n '2,29p' "$0"; exit 0 ;;
    -*)        die "unknown option: $1" ;;
    *)         target="$1"; shift ;;
  esac
done

target=$(CDPATH= cd -- "$target" 2>/dev/null && pwd) || die "no such directory"
[ "$merge" -eq 0 ] || [ "$dry" -eq 0 ] || die "--merge writes the project's files; run it without --dry-run"
[ -z "$base_ref" ] || [ "$merge" -eq 1 ] || die "--base is the base of --merge; pass both"
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

# own_repo — true when the kit folder is the top of a git clone of its own. A kit vendored or
# unpacked inside another repository answered with that repository's HEAD (round 1). Git
# answers, not two path strings: on Windows a kit path in another letter case or on a `subst`
# drive named the same folder, `pwd -P` kept the spelling, and no base was recorded.
own_repo() {
  _prefix=$(git -C "$kit" rev-parse --show-prefix 2>/dev/null) && [ -z "$_prefix" ]
}
# owned_list — the project-owned files of the kit's HEAD under core/ (no KIT-OWNED header), one
# path per line below core/, into $work_list. Read from the commit, never the working tree: a
# kit checked out with autocrlf has CRLF docs, and against the LF blob of the base every line
# read as changed (round 1).
owned_list() {
  git -C "$kit" -c core.quotePath=false grep -lE '^(# |<!-- )KIT-OWNED:' HEAD -- core |
    sed 's/^HEAD://' > "$copies.k"
  git -C "$kit" -c core.quotePath=false ls-tree -r --name-only HEAD -- core > "$work_list" &&
    grep -vxF -f "$copies.k" "$work_list" | sed 's|^core/||' > "$copies.k2" && mv -f "$copies.k2" "$work_list" ||
    die "cannot list the kit's project-owned files"
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
# The versions are compared by number, before a file is copied (#113). A project stamped newer
# than this kit (a second kit clone, not pulled) had its kit-owned hooks rolled back and the
# older version recorded as an upgrade; a version the changelog does not hold printed the
# whole changelog, every item since v0.1.
case "$have" in
  *[!0-9.]*|.*|*.|*..*) die "$stamp holds '$have', which is no version; write the version the project came from" ;;
esac
newer=$(awk -v a="$have" -v b="$latest" 'BEGIN { n = split(a, x, "."); m = split(b, y, ".")
  for (i = 1; i <= (n > m ? n : m); i++) if (x[i] + 0 != y[i] + 0) { print (x[i] + 0 > y[i] + 0); exit }
  print 0 }')
[ "$newer" = 0 ] ||
  die "this project has v$have, newer than this kit's v$latest; pull the kit, or run the clone the project came from. Nothing was changed."
awk -v want="v$have" '$1 == "##" && $2 == want { found = 1 } END { exit !found }' "$kit/CHANGELOG.md" ||
  die "v$have is no version in $kit/CHANGELOG.md; write the version the project came from into $stamp. Nothing was changed."

work_list=$(mktemp) || { echo "sync-kit: cannot create a temp file" >&2; exit 1; }
pending=$(mktemp) || { rm -f "$work_list"; echo "sync-kit: cannot create a temp file" >&2; exit 1; }
copies=$(mktemp) || { rm -f "$work_list" "$pending"; echo "sync-kit: cannot create a temp file" >&2; exit 1; }
# A signal handler that only cleaned up let the run resume with the pending list deleted,
# which reads as "no ACTION items" and stamped the version: a signal now ends the run.
mdir=""
out=$(mktemp) || { rm -f "$work_list" "$pending" "$copies"; echo "sync-kit: cannot create a temp file" >&2; exit 1; }
# The report is held in a file and printed when the run ends: printed as it went, a run piped
# to `head` died of SIGPIPE before the stamp, and looked like a success (#78). The exit trap
# prints it, past the stamp, and a reader that is gone by then costs nothing.
exec 3>&1 >"$out"
trap 'rm -f "$work_list" "$pending" "$copies" "$copies".* ${part:+"$part"}; [ -z "$mdir" ] || rm -rf "$mdir"
  trap "" PIPE; cat "$out" >&3 2>/dev/null || :; rm -f "$out"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# A temporary a stopped run left behind (`put` names them .kit-tmp.*) is not this run's to
# delete: it is named, for the owner to remove.
left=$(cd "$target" && find . -name .git -prune -o -type f -name '.kit-tmp.*' -print 2>/dev/null) || :
[ -z "$left" ] || printf '%s\n' "sync-kit: NOTE: temporaries a stopped run left behind; remove them:" "$left"

printf '%s\n' "sync-kit: project has v$have, kit is v$latest"
# The same version is synced all the same (#98): a release gains kit-owned fixes and ACTION
# items under its heading, and "already current" kept a project synced partway through it on
# the old hooks and without the new items.
repo_prefix=$(git -C "$target" rev-parse --show-prefix 2>/dev/null) && repo=1 || repo=""

# The base of --merge is checked before anything is written: a run that stops on it changes
# nothing.
if [ "$merge" -eq 1 ]; then
  named=$base_ref
  if [ -z "$base_ref" ]; then
    why=$(blocked docs/kit/.kit-commit)
    [ -n "$why" ] || [ ! -f "$target/docs/kit/.kit-commit" ] ||
      base_ref=$(tr -d '[:space:]' < "$target/docs/kit/.kit-commit")
  fi
  [ -n "$base_ref" ] ||
    die "--merge needs the kit commit this project's v$have came from: no docs/kit/.kit-commit, so pass --base <commit> (the changelog's upgrade section names the release commit)"
  own_repo || die "--merge reads the kit's history, and $kit is no git clone of its own"
  base=$(git -C "$kit" rev-parse -q --verify "$base_ref^{commit}") ||
    die "the kit has no commit $base_ref (a shallow clone?); clone the kit whole"
  mdir=$(mktemp -d) || die "cannot create a temp folder"
  # A base named by hand is checked against the project's kit-owned files as its last commit
  # holds them: the copies of the commit it came from. A later base reads the kit's fixes in
  # between as the project's edits and keeps the old lines, with no conflict to show. The
  # working copies were no proof: a plain sync before --merge, or a stopped --merge, had
  # already overwritten them, and the right base was refused (round 1). The commit is the one
  # that last changed the version stamp, whose copies came with that version: a plain sync's
  # copies committed after it are a later kit's, and the right base was refused again. Only a
  # file that commit does not hold is read from the working tree.
  if [ -n "$named" ]; then
    at=$(git -C "$target" log -1 --format=%H -- docs/kit/.kit-version 2>/dev/null) && [ -n "$at" ] || at=HEAD
    git -C "$kit" -c core.quotePath=false grep -lE '^(# |<!-- )KIT-OWNED:' "$base" -- core setup > "$work_list" ||
      [ $? -eq 1 ] || die "cannot list the kit-owned files at $base_ref"
    off=""
    while IFS= read -r f; do
      f=${f#"$base":}
      case "$f" in core/*) rel=${f#core/} ;; *) rel=$f ;; esac
      [ -z "$(blocked "$rel")" ] || continue
      if git -C "$target" show "$at:./$rel" > "$mdir/proj" 2>/dev/null; then :
      elif [ -f "$target/$rel" ]; then cat "$target/$rel" > "$mdir/proj"
      else continue; fi
      git -C "$kit" show "$base:$f" > "$mdir/kit" || die "cannot read $f at $base_ref"
      git diff --no-index --quiet --ignore-cr-at-eol -- "$mdir/kit" "$mdir/proj" || off="$off
    $rel"
    done < "$work_list"
    [ -z "$off" ] || die "the project's kit-owned files below differ from the kit's at $base_ref, so the project did not come from it, and a merge from it would drop the kit's changes since the real base without a conflict. Pass the commit it came from (git -C <kit> log --format=%h -- core/<file> lists the candidates):$off"
  fi
fi

# --- tier 1: overwrite the kit-owned files ------------------------------------------
echo
echo "KIT-OWNED files (overwritten):"
found=0
conflict=0
kit_conflict=0
dirty=0
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
    # An edit git does not hold (unstaged, or an untracked file) would be lost: the copy keeps
    # no backup (#128). A staged one stays in the index. Content the kit's own history holds is
    # no edit: an earlier run that stopped at its ACTION items wrote it, and the kit moved since.
    if [ -n "$repo" ] && git -C "$target" --literal-pathspecs status --porcelain -- "$rel" 2>/dev/null | grep -q '^.[^ ]' &&
      ! { own_repo && blob=$(git -C "$kit" hash-object --path="${src#"$kit/"}" -- "$target/$rel" 2>/dev/null) &&
          git -C "$kit" cat-file -e "$blob" 2>/dev/null; }; then
      printf '%s\n' "  conflict: $rel (uncommitted edits, which the copy would overwrite)"
      conflict=1
      dirty=1
      continue
    fi
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
  docs/RETROFIT.md). A hook of yours under .githooks only needs a new name: as
  .githooks/<same name>.project (executable, with a #! line) it keeps running, since the
  kit's hook runs it first with git's arguments.
EOF
  [ "$dirty" -eq 0 ] || cat <<EOF

  A kit-owned file listed holds uncommitted edits. Commit them (git keeps them, and the next
  sync replaces the file) or put the file back (git restore -- <file>; delete one git does not
  track), then sync again.
EOF
  [ -z "$overlay_fix" ] || cat <<EOF

  An overlay file listed is the kit's own file from an earlier version. Replace each one
  with the kit's current copy below, then sync again. A symlink or a symlinked folder on the
  way becomes a real file or folder first. The new copy is kit-owned and the next sync
  overwrites it: a project that must keep an edit records it in docs/GOTCHAS.md or puts it
  in a wrapper script of its own.$overlay_fix
EOF
  exit 1
fi
# exe FILE — the one place that decides which kit-owned files must be executable (the hooks
# and scripts git or a gate runs directly), for a copied file and an identical one alike. A
# hook git cannot run is skipped without a word, and a gate that cannot run is not there.
executable() { case "$rel" in *.sh|.githooks/*|.claude/hooks/*.py) return 0 ;; esac; return 1; }
exe() { ! executable || chmod +x "$1"; }
# The disk's executable bit does not reach git's index where core.fileMode is false (native
# Windows): a hook the sync wrote was committed at 100644, and a POSIX clone skips it (#182).
# As bootstrap.sh does: a tracked entry gets mode 100755 on the blob it has staged (its staged
# bytes stay as they were), a new file is staged with --chmod=+x at the repository top level
# and its command printed from a subfolder, an ignored file stays out of the index.
index_exe() {
  if indexed=$(git -C "$target" --literal-pathspecs ls-files -s --error-unmatch -- "$rel" 2>/dev/null); then
    mode=$(printf '%s\n' "$indexed" | awk '$3 == 0 { print $1 }')
    [ -n "$mode" ] || die "cannot set the index mode of an unmerged kit file: $rel; version left at v$have"
    case "$mode" in
      100644)
        blob=$(printf '%s\n' "$indexed" | awk '$3 == 0 { print $2 }')
        git -C "$target" update-index --cacheinfo "100755,$blob,$repo_prefix$rel" &&
          printf '%s\n' "  index:   $rel set to 100755" ;;
      100755) : ;;
      *) printf '%s\n' "  NOTE: keeping index mode $mode for $rel (not a regular file)" ;;
    esac
  elif ! git -C "$target" check-ignore -q -- "$rel"; then
    if [ -z "$repo_prefix" ]; then
      # Staged once the version is recorded, as bootstrap.sh does: a run that stops (ACTION
      # items, --merge) leaves nothing new in the owner's index (round 1).
      printf '%s\n' "$rel" >> "$copies.stage"
    else
      printf '%s\n' "  NOTE: $rel is not staged; from $target run:" \
        "    git add --chmod=+x -- \"$(printf '%s' "$rel" | sed 's/[\\"$`]/\\&/g')\""
    fi
  fi
}
if [ "$dry" -eq 0 ]; then
  while IFS= read -r src; do
    relpath "$src"
    { cmp -s "$src" "$target/$rel" || { mkdir -p "$target/$(dirname "$rel")" && put "$target/$rel" "$src"; }; } &&
      exe "$target/$rel" && { [ -z "$repo" ] || ! executable || index_exe; } ||
      die "could not write $rel; version left at v$have"
  done < "$copies"
fi

# --- tier 2: the checklist of what has to be applied by hand -------------------------
# items FILE INCL — FILE's ACTION items above the "## v$have" heading (with INCL=1, those of
# its own section too), one per line, "VERSION<tab>TEXT", the oldest version first, as
# UPDATING says to apply them: printed newest first, an item marked "first" came 79 items late
# (#99). The version is matched as an exact field, never a prefix ("## v0.1" is no "## v0.10").
# An item runs from its marker to the end of its list item or paragraph (a blank line, a
# heading or the next list item), joined into one line: printing only the marker's line cut
# items mid-sentence. A second marker inside that text starts an item of its own: it was
# printed as continuation text, and a gate merge read as part of a maintainer's push step.
# A "none" marker (**ACTION** — none, **ACTION:** none.) is no item. A "## Unreleased — vX"
# section is read as vX's: a sync from the kit's master copies its kit-owned files, and listed
# "already current" without the items they need. Named vX, a ticked item stays ticked past the
# release, when the heading becomes "## vX".
items() {
  awk -v want="v$have" -v incl="$2" '
    function add(s, g) { if (g != "") sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); if (s != "") cur = cur g s }
    function flush() { if (cur != "") { n++; txt[n] = cur; ver[n] = nv }; cur = ""; on = 0 }
    function take(s,    i, r, g) {
      g = " "
      while ((i = index(s, "**ACTION")) > 0) {
        if (on) add(substr(s, 1, i - 1), g)
        flush()
        r = substr(s, i)
        if (r ~ /^\*\*ACTION\*\* — none\.?[ \t]*$/ || r ~ /^\*\*ACTION:\*\*[ \t]+none\.[ \t]*$/) return
        on = 1; cur = "**ACTION"; s = substr(r, 9); g = ""
      }
      if (on) add(s, g)
    }
    { sub(/\r$/, "") }
    /^## (v|Unreleased)/ { flush(); if (last) exit; v = $2
      if (v == "Unreleased") v = match($0, /v[0-9][0-9.]*/) ? substr($0, RSTART, RLENGTH) : v
      if (v == want) { if (!incl) exit; last = 1 }; nv++; name[nv] = v; next }
    on && /[^ \t]/ && !/^#/ && !/^[ \t]*([-*]|[0-9]+\.)[ \t]/ { take($0); next }
    { flush() }
    nv { take($0) }
    END { flush(); for (k = nv; k >= 1; k--) for (i = 1; i <= n; i++) if (ver[i] == k) print name[k] "\t" txt[i] }
  ' "$1"
}
# The pending items. With the kit commit of the last stamp (docs/kit/.kit-commit) in the kit's
# history: every item of the changelog now, from v$have's own section up, that the changelog of
# that commit did not hold, so an item added under a version after the project took it is
# pending too (#98). Without it, the items of the versions above v$have. A scan that failed
# leaves the list empty, which reads as "no ACTION items": it stops the sync instead.
scanned=0
if own_repo && [ -z "$(blocked docs/kit/.kit-commit)" ] && [ -f "$target/docs/kit/.kit-commit" ]; then
  was=$(tr -d '[:space:]' < "$target/docs/kit/.kit-commit")
  if [ -n "$was" ] && git -C "$kit" show "$was:CHANGELOG.md" > "$copies.was" 2>/dev/null; then
    items "$copies.was" 1 > "$copies.old" && items "$kit/CHANGELOG.md" 1 > "$copies.now" &&
      { grep -vxF -f "$copies.old" "$copies.now" || [ $? -eq 1 ]; } > "$pending" && scanned=1 ||
      die "cannot scan the changelog for ACTION items; version left at v$have. Rerun once awk can read $kit/CHANGELOG.md."
  fi
fi
[ "$scanned" -eq 1 ] || items "$kit/CHANGELOG.md" 0 > "$pending" ||
  die "cannot scan the changelog for ACTION items; version left at v$have. Rerun once awk can read $kit/CHANGELOG.md."

# The checklist, one box per item: a session that applied half the list and then compacted or
# handed off left the next one the same full list, and one flag confirmed it all (#129). Ticks
# are kept by an item's text across runs, so an item the kit added or reworded since comes back
# open. The full entries stay in the kit's changelog: printed whole on every run, they made a
# v0.8 upgrade print 209 KB, seven times what an agent's shell tool shows (#99).
list=docs/kit/UPGRADE.md
render() {
  awk -v ck="$1" -v from="$have" -v to="$latest" -v src="$kit/CHANGELOG.md" '
    FILENAME == ck { sub(/\r$/, ""); if (sub(/^- \[[xX]\] /, "")) done[$0] = 1; next }
    !head { head = 1
      print "# Upgrade checklist, v" from " to v" to; print ""
      print "Written by sync-kit.sh, one box per ACTION item, the oldest version first. Apply each item"
      print "and tick its box (- [x]) when it is done; each one'\''s whole entry is in " src "."
      print "Then rerun sync-kit.sh with --actions-applied: it records v" to " only when every box is"
      print "ticked, and deletes this file."; print "" }
    { i = index($0, "\t"); t = substr($0, 1, i - 1) ": " substr($0, i + 1); print "- [" (t in done ? "x" : " ") "] " t }
  ' "$1" "$pending"
}
echo
if [ ! -s "$pending" ]; then
  [ "$have" != "$latest" ] || echo "sync-kit: already current: nothing new to apply by hand since the last sync."
elif [ "$dry" -eq 1 ]; then
  printf '%s\n' "ACTION items since v$have, oldest first (a real run writes them to $list):"
  render /dev/null | sed -n 's/^- \[ \] /  /p'
else
  why=$(blocked "$list")
  [ -z "$why" ] || die "conflict: $list ($why); the checklist is not written there. Version left at v$have."
  if [ -f "$target/$list" ]; then render "$target/$list"; else render /dev/null; fi > "$copies.list" &&
    put "$target/$list" "$copies.list" || die "could not write $list; version left at v$have"
  total=$(grep -c '^- \[[ x]\] ' "$copies.list") || :
  unticked=$(grep -c '^- \[ \] ' "$copies.list") || :
  printf '%s\n' "sync-kit: $total ACTION items since v$have, oldest first, are in $list; $unticked of them not ticked."
fi

# --- tier 3, with --merge: the kit's changes merged into the project-owned files ---------
# Each project-owned file of the kit's HEAD under core/ that the kit changed since the base
# commit is merged with `git merge-file` (the project's copy, the kit's blob at the base, the
# kit's blob at HEAD) and written whole with its mode; a file the kit did not change is not
# opened. Both kit sides are blobs, never the kit's working tree (an autocrlf checkout made
# every line differ), and a CRLF project copy is merged as LF and written back as CRLF.
# Left for a person or an agent are the conflict regions alone, printed by line. One upgrade
# that merged five docs whole, one agent each, read 8.3M cache tokens (#184); the conflict
# regions of a v0.8 -> v0.12 merge of the same docs and check.sh measured 14% of one read of
# the whole files. The base is the kit commit the project's version came from: a later one
# reads the kit's own changes in between as the project's. This run never records the
# version: the merged files are read first (git diff), their conflicts resolved, then
# --actions-applied records it.
if [ "$merge" -eq 1 ]; then
  owned_list
  cr=$(printf '\r')
  echo
  printf '%s\n' "PROJECT-OWNED files, the kit's changes since ${base%"${base#???????}"} merged in:"
  open=0
  while IFS= read -r rel; do
    why=$(blocked "$rel")
    if [ -n "$why" ]; then
      printf '%s\n' "  skipped:  $rel ($why); merge it by hand"; open=1; continue
    fi
    if ! git -C "$kit" show "$base:core/$rel" > "$mdir/base" 2>/dev/null; then
      if [ -e "$target/$rel" ]; then
        printf '%s\n' "  no base:  $rel (the kit had no such file at the base); merge it by hand"; open=1
      else
        printf '%s\n' "  kit-new:  $rel (not in the project; the changelog says whether to copy it)"
      fi
      continue
    fi
    git -C "$kit" show "HEAD:core/$rel" > "$mdir/now" || die "cannot read core/$rel in the kit"
    # Removed by the project, or not changed by the kit: nothing to merge.
    [ -e "$target/$rel" ] && ! cmp -s "$mdir/base" "$mdir/now" || continue
    if grep -q '^<<<<<<< ' "$target/$rel"; then
      printf '%s\n' "  unresolved: $rel (conflict markers of an earlier merge); resolve them first"; open=1; continue
    fi
    tr -d '\r' < "$target/$rel" > "$mdir/ours" || die "cannot read $rel"
    rc=0
    git merge-file -p -L project -L "kit base" -L "kit v$latest" \
      "$mdir/ours" "$mdir/base" "$mdir/now" > "$mdir/merged" || rc=$?
    [ "$rc" -lt 128 ] || die "could not merge $rel; it and the files after it are unchanged"
    # ponytail: CRLF is decided by the file's first line ending, as editors do; a mixed file comes back all CRLF.
    if head -n 1 "$target/$rel" | od -An -c | grep -q '\\r'; then
      sed "s/\$/$cr/" "$mdir/merged" > "$mdir/out" || die "cannot write $rel"
    else
      mv -f "$mdir/merged" "$mdir/out"
    fi
    put "$target/$rel" "$mdir/out" || die "could not write $rel; it and the files after it are unchanged"
    if [ "$rc" -eq 0 ]; then
      printf '%s\n' "  merged:   $rel"
    else
      open=1
      printf '%s\n' "  conflict: $rel, lines $(awk '/^<<<<<<< /{s=NR} /^>>>>>>> /{printf "%s%d-%d", c, s, NR; c=", "}' "$target/$rel")"
    fi
  done < "$work_list"
  git -C "$kit" -c core.quotePath=false diff --name-only --no-renames --diff-filter=D "$base" HEAD -- core > "$work_list" ||
    die "cannot list the files the kit removed"
  while IFS= read -r f; do
    printf '%s\n' "  kit-removed: ${f#core/} (the kit deleted or renamed it since the base; the changelog says what to do)"
  done < "$work_list"
  echo
  printf '%s\n' "sync-kit: version left at v$have. Read each merged file's diff (git diff) and account for"
  echo "          every removed line; resolve each conflict listed (read only those lines);"
  printf '%s\n' "          then rerun with --actions-applied, without --merge, to record v$latest."
  [ "$open" -eq 0 ] || echo "          Files are listed above as conflict, unresolved, skipped or no base."
  exit 2
fi

if [ "$dry" -eq 1 ]; then
  echo
  printf '%s\n' "sync-kit: dry run — nothing written, version left at v$have."
  exit 0
fi

if [ -s "$pending" ] && { [ "$applied" -eq 0 ] || [ "$unticked" -ne 0 ]; }; then
  echo
  if [ "$applied" -eq 1 ]; then
    printf '%s\n' "sync-kit: version left at v$have: $unticked items in $list are not ticked."
  else
    printf '%s\n' "sync-kit: version left at v$have: the ACTION items are not confirmed."
  fi
  printf '%s\n' "          Apply each item in $list and tick its box, then rerun with" \
    "          --actions-applied to record v$latest. Until then every sync lists them again."
  exit 2
fi

# The kit commit this version came from, the base of the next --merge (none from a kit that is
# no git clone of its own; that --merge is given --base). A merge leaves conflict markers for
# the owner: a stamp over them recorded the version and moved the base while a project-owned
# file still held both sides (round 1), so it waits until none is left.
commit=""
if own_repo && commit=$(git -C "$kit" rev-parse -q --verify HEAD); then
  owned_list
  marked=""
  while IFS= read -r rel; do
    [ -z "$(blocked "$rel")" ] && [ -f "$target/$rel" ] || continue
    if grep -qE '^(<<<<<<<|>>>>>>>)( |$)' "$target/$rel"; then marked="$marked
    $rel"; fi
  done < "$work_list"
  [ -z "$marked" ] || die "conflict markers are left in these files; resolve them, then rerun. Version left at v$have:$marked"
  why=$(blocked docs/kit/.kit-commit)
  if [ -n "$why" ]; then
    printf '%s\n' "sync-kit: NOTE: docs/kit/.kit-commit not recorded ($why)"
  else
    put "$target/docs/kit/.kit-commit" <<EOF || die "could not write docs/kit/.kit-commit; version left at v$have"
$commit
EOF
  fi
fi
put "$stamp" <<EOF || die "could not write $stamp; version left at v$have"
$latest
EOF
echo
printf '%s\n' "sync-kit: recorded v$latest."
[ -n "$(blocked "$list")" ] || [ ! -f "$target/$list" ] || rm -f "$target/$list" ||
  printf '%s\n' "sync-kit: NOTE: $list is done; remove it"
if [ -s "$copies.stage" ]; then
  while IFS= read -r rel; do
    if git -C "$target" add --chmod=+x -- "$rel"; then
      printf '%s\n' "sync-kit: staged $rel (100755)"
    else
      printf '%s\n' "sync-kit: NOTE: $rel was not staged; run: git add --chmod=+x -- \"$rel\""
    fi
  done < "$copies.stage"
fi
echo "sync-kit: now run ./scripts/check.sh. A sync that leaves the gate red is not finished."
