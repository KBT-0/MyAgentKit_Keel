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
#                content, so this script overwrites it wholesale. A file there WITHOUT the
#                marker is the project's own, a conflict that stops the sync before it copies
#                anything, unless it is the kit's unmodified copy, adopted (docs/UPDATING.md).
#   PROJECT-OWNED  everything else. Never touched. Most of the kit is project-owned by
#                design — the constitution, the workflow, the gate's values, the boundary checks
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

# The project's own reviewer agents beside the kit's diff-reviewer.md: two definitions for one
# job leave the lead to pick either (#161). Listed for the owner, never moved or overwritten.
# Which one it is the line says, not the script: a domain reviewer for one tree is no duplicate.
# A reviewer is a .md under .claude/agents, subfolders too (Claude Code reads the folder
# recursively and knows an agent by its front matter `name:` alone,
# code.claude.com/docs/en/sub-agents), whose `name:` holds "review" as a word start (reviewer,
# code-review, pr_reviewer; not ui-preview).
# The description is not read: workers and planners name reviews in passing. A UTF-8 BOM before
# the front matter is accepted. The kit's own file is matched in any letter case: on Windows and
# macOS Diff-Reviewer.md is the same file.
reviewers() {
  [ -f "$target/.claude/agents/diff-reviewer.md" ] || return 0
  find "$target/.claude/agents" -type f -name '*.md' 2>/dev/null | sort | while IFS= read -r _f; do
    _r=.claude/agents/${_f#"$target/.claude/agents/"}
    case $(printf '%s' "$_r" | tr 'A-Z' 'a-z') in .claude/agents/diff-reviewer.md) continue ;; esac
    LC_ALL=C awk 'NR == 1 { sub(/^\357\273\277/, "") }
         NR == 1 && !/^---[ \t\r]*$/ { exit }
         NR > 1 && /^---/ { exit }
         NR > 1 && /^name:/ { if (tolower(substr($0, 6)) ~ /(^|[^a-z])review/) found = 1; exit }
         END { exit !found }' "$_f" &&
      printf '%s\n' "  reviewer: $_r (beside diff-reviewer.md: a duplicate of its whole-diff review keeps one of the two; a domain reviewer, scoped to one tree or concern, stays, its description naming that scope; the kit's docs/UPDATING.md)"
  done || :
  return 0
}

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
# owned_list — the project-owned files of the kit's HEAD under core/ and overlays/ (no
# KIT-OWNED header), one kit path per line, into $work_list; owned_rel maps each to the project.
# Read from the commit, never the working tree: a kit checked out with autocrlf has CRLF docs,
# and against the LF blob of the base every line read as changed (round 1).
owned_list() {
  git -C "$kit" -c core.quotePath=false grep -lE '^(# |<!-- )KIT-OWNED:' HEAD -- core overlays |
    sed 's/^HEAD://' > "$copies.k"
  git -C "$kit" -c core.quotePath=false ls-tree -r --name-only HEAD -- core overlays > "$work_list" &&
    { grep -vxF -f "$copies.k" "$work_list" || [ $? -eq 1 ]; } > "$copies.k2" && mv -f "$copies.k2" "$work_list" ||
    die "cannot list the kit's project-owned files"
}
# owned_rel KPATH — sets rel, the project's path of the kit path KPATH; false for an overlay the
# project did not take ($taken) and an overlay's own README. Read core/ alone, --merge left
# an overlay's project-owned hooks (context_size.py) on the old copy without a word (labricore C1).
owned_rel() {
  case "$1" in
    core/*) rel=${1#core/} ;;
    overlays/*/files/*)
      rel=${1#overlays/*/files/} _o=${1#overlays/}
      case "$taken" in *" ${_o%%/*} "*) ;; *) return 1 ;; esac ;;
    *) return 1 ;;
  esac
}
# value_names REL — the project values a script held in place before it was kit-owned (#94),
# which scripts/gate_config.sh holds now: an alternation for awk, empty for any other file.
value_names() {
  case "$1" in
    scripts/check.sh) echo 'toolchain_path|build_test_cmd|docs_only_skip_build|docs_always_build|build_cache_inputs|cache_days|module_roots|STRONG_REVIEW_DAYS|STRONG_REVIEW_TASKS' ;;
    scripts/review.sh) echo 'DEFAULT_REVIEWER|CODEX_MODEL|CLAUDE_MODEL' ;;
  esac
}
# plain FILE NAMES LINE2 VALUES — FILE as the kit's copy reads without a project's values, to
# compare: its CRs dropped, each NAME=... line cut to NAME=, each `# read-only:` line left out
# (both with NAMES only), and a line 2 that is LINE2 with a name where LINE2 holds
# {{PROJECT_NAME}} read as LINE2. What it sets aside is appended to VALUES, the name as "@name X".
# ponytail: a value continued over several lines reads as an edit, so that copy stays a conflict.
plain() {
  tr -d '\r' < "$1" | awk -v names="$2" -v base="$3" -v values="$4" '
    BEGIN { i = index(base, "{{PROJECT_NAME}}"); pre = substr(base, 1, i - 1); suf = substr(base, i + 16)
            if (names != "") names = "^(" names ")=" }
    NR == 2 && i && index($0, pre) == 1 && length($0) >= length(pre suf) &&
      substr($0, length($0) - length(suf) + 1) == suf {
      print "@name " substr($0, length(pre) + 1, length($0) - length(pre suf)) >> values; print base; next }
    names != "" && $0 ~ names { print >> values; sub(/=.*/, "="); print; next }
    names != "" && /^# read-only:/ { print >> values; next }
    { print }'
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
    die "the kit at $kit has no commit $base_ref: a shallow clone, or a kit older than the one this project came from (the installer's cache fetches one release); clone the kit whole at the release you sync to"
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

# The kit commit the project's copies came from, to adopt a copy made before its file was
# kit-owned (#94): the base --merge reads (docs/kit/.kit-commit, or --base), else the release
# tag the stamp names. None found, such a copy stays a conflict.
adopt_base=""
if own_repo; then
  recorded_base=""
  [ -n "$(blocked docs/kit/.kit-commit)" ] || [ ! -f "$target/docs/kit/.kit-commit" ] ||
    recorded_base=$(tr -d '[:space:]' < "$target/docs/kit/.kit-commit")
  for c in ${base:-} $recorded_base "v$have"; do
    adopt_base=$(git -C "$kit" rev-parse -q --verify "$c^{commit}" 2>/dev/null) && break || adopt_base=""
  done
fi
: > "$copies.values"

# --- tier 1: overwrite the kit-owned files ------------------------------------------
echo
echo "KIT-OWNED files (overwritten):"
found=0
conflict=0
kit_conflict=0
dirty=0
held=0
overlay_fix=''
# Read the list line by line rather than through word splitting: a path containing a space
# would otherwise be torn into two nonexistent paths and silently skipped.
#
# The marker is matched ANCHORED at the start of a line, as a header comment. Matching the
# bare phrase anywhere once meant a document that merely MENTIONED "KIT-OWNED" in prose
# would have been silently overwritten wholesale.
# -I: a kit clone that ran its tests holds __pycache__/*.pyc, whose bytes can carry the marker (#330).
grep -rlIE '^(# |<!-- )KIT-OWNED:' "$kit/core" "$kit/setup" "$kit/overlays" 2>/dev/null \
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
# The overlays the project took: the presence of their files is the only record of it, so an
# overlay with at least one of its kit-owned files in the project counts as taken, and so does
# one with a file of it below a folder of its own: the unity overlay holds no kit-owned file
# and its project-owned ones were never merged (review High). A root file or one under .claude/
# (a project's own CLAUDE.md, settings.json) is no record of an overlay.
{ [ ! -d "$kit/overlays" ] || find "$kit/overlays" -type f; } > "$copies.o" || die "cannot list the kit's overlays"
taken=" "
while IFS= read -r src; do
  relpath "$src" && [ "$overlay" -eq 1 ] && [ -e "$target/$rel" ] || continue
  case "$rel" in .claude/*) ;; */*) o=${src#"$kit/overlays/"}; taken="$taken${o%%/*} "; continue ;; esac
  grep -qxF -- "$src" "$work_list" || continue
  o=${src#"$kit/overlays/"}; taken="$taken${o%%/*} "
done < "$copies.o"
while IFS= read -r src; do
  [ -n "$src" ] || continue
  relpath "$src" || continue
  why=$(blocked "$rel")
  # An absent overlay file is installed only in a project that took its overlay: a new
  # kit-owned script there (v0.12's list_workers.sh, which the synced watch and close scripts
  # call) arrives with the sync. Installing an overlay itself is bootstrap's job.
  # A symlink in its path is no absence: a dangling one fails `-e` and was skipped without a
  # word, and a symlinked folder had the kit's file written through it outside the project.
  if [ "$overlay" -eq 1 ] && [ ! -e "$target/$rel" ]; then
    o=${src#"$kit/overlays/"}
    case "$why" in "symlink: "*) ;; *) case "$taken" in *" ${o%%/*} "*) ;; *) continue ;; esac ;; esac
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
    # Unless it is the kit's own copy from before the header (#94): equal to the kit's at the
    # base once line endings and, for check.sh and review.sh, the project's values are set
    # aside. It is adopted, and those values go to scripts/gate_config.sh.
    kpath=${src#"$kit/"} names=$(value_names "$rel")
    # An uncommitted value edit in check.sh or review.sh is refused as at a kit-owned file: git
    # holds no copy of it, should the values not reach scripts/gate_config.sh.
    if [ -n "$names" ] && [ -n "$repo" ] &&
      git -C "$target" --literal-pathspecs status --porcelain -- "$rel" 2>/dev/null | grep -q '^.[^ ]'; then
      printf '%s
' "  conflict: $rel (uncommitted edits, which the copy would overwrite)"
      conflict=1
      dirty=1
      continue
    fi
    : > "$copies.v"
    adopted=0
    if [ -n "$adopt_base" ] && git -C "$kit" show "$adopt_base:$kpath" > "$copies.base" 2>/dev/null; then
      line2=$(sed -n 2p "$copies.base" | tr -d '\r')
      plain "$copies.base" "$names" "$line2" /dev/null > "$copies.b" &&
        plain "$target/$rel" "$names" "$line2" "$copies.v" > "$copies.p" ||
        die "cannot compare $rel with the kit's copy; version left at v$have"
      if cmp -s "$copies.b" "$copies.p"; then
        adopted=1
        if [ -s "$copies.v" ]; then
          cat "$copies.v" >> "$copies.values" || die "cannot record the values of $rel; version left at v$have"
          printf '%s\n' "  adopted: $rel (unmodified copy; its values go to scripts/gate_config.sh)"
        else
          printf '%s\n' "  adopted: $rel (unmodified copy)"
        fi
      else
        short=${adopt_base%"${adopt_base#???????}"}
        printf '%s\n' "  conflict: $rel (exists without the KIT-OWNED header and differs from the kit's copy at $short, so it holds the project's edits; see them: git -C '$(printf '%s\n' "$kit" | sed "s/'/'\\\\''/g")' show $short:$kpath | diff - $rel)"
      fi
    else
      printf '%s\n' "  conflict: $rel (exists without the KIT-OWNED header, so it is the project's)"
      [ -z "$names" ] || plain "$target/$rel" "$names" "" "$copies.v" > /dev/null ||
        die "cannot read the values of $rel; version left at v$have"
    fi
    if [ "$adopted" -eq 0 ]; then
      # labricore C4: a conflicted check.sh or review.sh writes no gate_config.sh, so the values
      # it holds are printed for the owner to carry over. Written, they would break the
      # all-or-nothing stop, and an edited copy's values may be the edit itself.
      if [ -s "$copies.v" ]; then
        printf '%s\n' "          its values, for scripts/gate_config.sh:"
        sed 's/^@name /# project name: /; s/^/            /' "$copies.v"
        held=1
      fi
      conflict=1
      kit_conflict=1
      continue
    fi
  fi
  printf '%s\n' "$src" >> "$copies" || die "cannot record $rel for copying; version left at v$have"
done < "$work_list"
[ "$found" -eq 1 ] || echo "  (none)"
# The values of the adopted check.sh and review.sh, written into the kit's gate_config.sh
# template, become the project's scripts/gate_config.sh: where there is none, or where it is
# still that template, unfilled. One of the project's own is kept, and the values are printed
# for the owner to compare.
config=""
if [ -s "$copies.values" ]; then
  awk -v values="$copies.values" '
    BEGIN { while ((getline l < values) > 0) {
              if (l ~ /^@name /) name = substr(l, 7)
              else if (l ~ /^# read-only:/) ro = ro l "\n"
              else { k = l; sub(/=.*/, "", k); val[k] = l } } }
    NR == 1 && name != "" && (i = index($0, "{{PROJECT_NAME}}")) { $0 = substr($0, 1, i - 1) name substr($0, i + 16) }
    /^# read-only:/ && ro != "" { if (!shown) printf "%s", ro; shown = 1; next }
    { k = $0; if (sub(/=.*/, "", k) && k in val) { print val[k]; next }; print }
  ' "$kit/core/scripts/gate_config.sh" > "$copies.config" || die "cannot write the project's values; version left at v$have"
  why=$(blocked scripts/gate_config.sh)
  if [ -n "$why" ]; then
    printf '%s\n' "  conflict: scripts/gate_config.sh ($why; the adopted scripts' values go there)"
    conflict=1
    kit_conflict=1
  elif [ ! -e "$target/scripts/gate_config.sh" ] || grep -qE '\{\{[A-Z0-9_]+\}\}' "$target/scripts/gate_config.sh"; then
    printf '%s\n' "  new:     scripts/gate_config.sh (project-owned: the values the adopted scripts held)"
    config=1
  else
    printf '%s\n' "  NOTE: scripts/gate_config.sh is the project's own and was kept; the adopted scripts held these" \
      "        values, compare them with it:"
    grep -v '^@name ' "$copies.values" | sed 's/^/          /'
  fi
fi
listed=$(reviewers)
[ -z "$listed" ] || printf '\nReviewer agents (listed, not a stop):\n%s\n' "$listed"
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
  kit's hook runs it first with git's arguments. A kit script you edited (its line shows the
  edit) keeps no edit of yours: a value of check.sh or review.sh goes into
  scripts/gate_config.sh, a check of a reviewer's final report into scripts/project_validation.py,
  a gate step into scripts/check.project.sh, a self-test suite into
  scripts/review_selftest.project.sh (the kit's docs/UPDATING.md), anything else upstream
  (/myagentkit:kit-feedback).
EOF
  [ "$held" -eq 0 ] || cat <<EOF

  No scripts/gate_config.sh is written while check.sh or review.sh is a conflict: the values
  listed under its line go there. Once yours is moved aside, $(if [ -s "$copies.values" ]; then
  echo "the rerun writes it from the adopted scripts' values; add the listed ones to it by hand."
else
  echo "the rerun adopts nothing, so copy
  the kit's core/scripts/gate_config.sh to scripts/gate_config.sh and set them by hand."
fi)
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
  # The values first: a run cut off in the copy loop below leaves the kit's check.sh beside
  # them, never without them (a rerun finds that check.sh the kit's and records no values).
  [ -z "$config" ] || put "$target/scripts/gate_config.sh" "$copies.config" ||
    die "could not write scripts/gate_config.sh; version left at v$have"
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
# The upgrade commit is too big for one review (#114): the kit-owned files equal to the kit's
# are verified by hash and only the rest is reviewed. A kit that records no commit verifies none.
# The line names the kit commit copied: with ACTION items pending, docs/kit/.kit-commit is not
# written yet and the upgrade is reviewed before them (#305).
review=""
own_repo && review="./scripts/review.sh --reviewer claude --commit <upgrade commit> --kit-verified --kit '$(printf '%s\n' "$kit" | sed "s/'/'\\\\''/g")'" &&
  copied=$(git -C "$kit" rev-parse -q --verify HEAD) && review="$review --kit-commit $copied"
render() {
  # The review line through the environment: -v reads its '\'' as an escape.
  review="$review" awk -v ck="$1" -v from="$have" -v to="$latest" -v src="$kit/CHANGELOG.md" '
    FILENAME == ck { sub(/\r$/, ""); if (sub(/^- \[[xX]\] /, "")) done[$0] = 1; next }
    !head { head = 1
      print "# Upgrade checklist, v" from " to v" to; print ""
      print "Written by sync-kit.sh, one box per ACTION item, the oldest version first. Apply each item"
      print "and tick its box (- [x]) when it is done; each one'\''s whole entry is in " src "."
      print "Then rerun sync-kit.sh with --actions-applied: it records v" to " only when every box is"
      print "ticked, and deletes this file."
      print "A hook an item adds runs only in a session started after it (#321): the commit that adds it"
      print "is not guarded by it, so restart the session before relying on it."
      review = ENVIRON["review"]
      if (review != "") print "Commit the upgrade, then review that commit: " review " (see docs/REVIEW_RUNNING.md)."
      print "" }
    { i = index($0, "\t"); t = substr($0, 1, i - 1) ": " substr($0, i + 1); print "- [" (t in done ? "x" : " ") "] " t }
  ' "$1" "$pending"
}
# #318: the gate's agents-size check (24576 bytes, check.sh 2c2) failed a sync's first commit: said here, before
# the ACTION and --merge exits below. shortcut: the root AGENTS.md alone; check.sh still measures every chain.
if [ -f "$target/AGENTS.md" ]; then
  size=$(wc -c < "$target/AGENTS.md" | tr -d " ")
  [ "$size" -lt 24576 ] ||
    printf '%s\n' "sync-kit: NOTE: AGENTS.md is $size bytes, not under the gate's 24576 (check.sh agents-size): move what only some tasks need into a doc the reading order points to before the commit."
fi
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
# Each project-owned file of the kit's HEAD under core/, and under the overlays the project
# took, that the kit changed since the base commit is merged with `git merge-file` (the project's copy, the kit's blob at the base, the
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
# learn KITFILE < PROJECTFILE — appends to $mdir/cands "NAME<tab>VALUE" for each placeholder of
# the kit's text at the base whose line the project's copy holds filled: the same line around
# it, found once, or for a placeholder alone on its line the project's lines between the same
# neighbouring lines (a multi-line value, its lines joined by \037).
learn() {
  awk -v cands="$mdir/cands" '
    function one(name, v) { if (v != "" && v !~ /[{][{]|[}][}]/) print name "\t" v >> cands }
    FILENAME == ARGV[1] { b[++nb] = $0; next }
    { p[++np] = $0 }
    END {
      for (i = 1; i <= nb; i++) {
        l = b[i]
        if (!match(l, /[{][{][A-Z0-9_]+[}][}]/)) continue
        name = substr(l, RSTART + 2, RLENGTH - 4); pre = substr(l, 1, RSTART - 1); suf = substr(l, RSTART + RLENGTH)
        if (index(suf, "{{")) continue
        hit = 0
        if (pre suf == "") {
          for (a = i - 1; a > 0 && b[a] ~ /^[ \t]*$/; a--) ;
          for (z = i + 1; z <= nb && b[z] ~ /^[ \t]*$/; z++) ;
          if (a < 1 || z > nb || index(b[a] b[z], "{{")) continue
          for (j = 1; j <= np; j++) if (p[j] == b[a]) { hit++; at = j }
          if (hit != 1) continue
          for (k = at + 1; k <= np && p[k] != b[z]; k++) ;
          if (k > np) continue
          for (s = at + 1; s < k && p[s] ~ /^[ \t]*$/; s++) ;
          for (e = k - 1; e >= s && p[e] ~ /^[ \t]*$/; e--) ;
          v = ""; for (k = s; k <= e; k++) v = v (k > s ? "\037" : "") p[k]
          one(name, v); continue
        }
        # A short context ("{{OWNER_NAME}}:") matches lines that are no fill of it.
        if (length(pre suf) < 8) continue
        for (j = 1; j <= np; j++) {
          q = p[j]
          if (length(q) > length(pre suf) && substr(q, 1, length(pre)) == pre &&
              substr(q, length(q) - length(suf) + 1) == suf) { hit++; v = substr(q, length(pre) + 1, length(q) - length(pre suf)) }
        }
        if (hit == 1) one(name, v)
      }
    }' "$1" -
}
# fill OURS < MERGED — MERGED with each placeholder the project's copy OURS does not hold
# filled from $mdir/values (the value found most often); one left unfilled goes to $mdir/left
# as "{{NAME}} line N (why)". A placeholder OURS still holds is the project's own, left to it,
# and listed only on a line OURS does not hold (a new kit line, review Low).
fill() {
  : > "$mdir/left"
  awk -v vals="$mdir/values" -v ours="$1" -v left="$mdir/left" '
    function names(s) { while (match(s, /[{][{][A-Z0-9_]+[}][}]/)) { mine[substr(s, RSTART + 2, RLENGTH - 4)] = 1; s = substr(s, RSTART + RLENGTH) } }
    BEGIN { while ((getline l < vals) > 0) { t = index(l, "\t"); val[substr(l, 1, t - 1)] = substr(l, t + 1) }
            while ((getline l < ours) > 0) { names(l); had[l] = 1 } }
    { s = $0; o = ""
      if (s ~ /^[{][{][A-Z0-9_]+[}][}]$/) {
        n = substr(s, 3, length(s) - 4)
        if ((n in val) && !(n in mine)) { k = split(val[n], v, "\037"); for (i = 1; i <= k; i++) print v[i]; out += k; next }
      }
      while (match(s, /[{][{][A-Z0-9_]+[}][}]/)) {
        n = substr(s, RSTART + 2, RLENGTH - 4)
        if ((n in val) && !(n in mine) && !index(val[n], "\037")) r = val[n]
        else {
          r = substr(s, RSTART, RLENGTH)
          why = (n in mine) ? "unfilled in the project\047s copy too" : (n in val) ? "its value spans lines" : "no value in the project\047s files"
          if (!(n in mine) || !($0 in had)) printf "%s{{%s}} line %d (%s)", (c++ ? ", " : ""), n, out + 1, why > left
        }
        o = o substr(s, 1, RSTART - 1) r; s = substr(s, RSTART + RLENGTH)
      }
      print o s; out++ }'
}
if [ "$merge" -eq 1 ]; then
  owned_list
  cr=$(printf '\r')
  # The placeholders the project filled at setup, read from its copies against the kit's at
  # the base: merged kit text brought {{OWNER_NAME}} back into ten places (labricore C2, L5).
  : > "$mdir/cands"
  while IFS= read -r kp; do
    owned_rel "$kp" && [ -z "$(blocked "$rel")" ] && [ -f "$target/$rel" ] || continue
    git -C "$kit" show "$base:$kp" 2>/dev/null | tr -d '\r' > "$mdir/base"
    grep -q '{{[A-Z0-9_]*}}' "$mdir/base" || continue
    tr -d '\r' < "$target/$rel" | learn "$mdir/base" || die "cannot read the placeholders of $rel"
  done < "$work_list"
  sort "$mdir/cands" | uniq -c | sort -k1,1nr -k2 |
    awk '{ sub(/^ *[0-9]+ /, ""); n = substr($0, 1, index($0, "\t") - 1); if (!(n in seen)) { seen[n] = 1; print } }' > "$mdir/values" ||
    die "cannot read the project's placeholder values"
  # Every line of the kit's files at the base and now, and with the project's values filled in:
  # what a conflict's project side holds beyond them is the project's own.
  { git -C "$kit" -c grep.lineNumber=false -c grep.column=false grep -h -I -e '' "$base" -- core overlays &&
    git -C "$kit" -c grep.lineNumber=false -c grep.column=false grep -h -I -e '' HEAD -- core overlays; } > "$mdir/kitraw" &&
    fill /dev/null < "$mdir/kitraw" | cat "$mdir/kitraw" - > "$mdir/kitlines" || die "cannot read the kit's files"
  echo
  printf '%s\n' "PROJECT-OWNED files, the kit's changes since ${base%"${base#???????}"} merged in:"
  open=0
  while IFS= read -r kp; do
    owned_rel "$kp" || continue
    # Written by tier 1 from the adopted scripts' values: the project's, with nothing to merge.
    [ "$rel" != scripts/gate_config.sh ] || [ -z "$config" ] || continue
    why=$(blocked "$rel")
    if [ -n "$why" ]; then
      printf '%s\n' "  skipped:  $rel ($why); merge it by hand"; open=1; continue
    fi
    if ! git -C "$kit" show "$base:$kp" > "$mdir/base" 2>/dev/null; then
      if [ -e "$target/$rel" ]; then
        printf '%s\n' "  no base:  $rel (the kit had no such file at the base); merge it by hand"; open=1
      else
        printf '%s\n' "  kit-new:  $rel (not in the project; the changelog says whether to copy it)"
      fi
      continue
    fi
    git -C "$kit" show "HEAD:$kp" > "$mdir/now" || die "cannot read $kp in the kit"
    # Not changed by the kit: nothing to merge.
    ! cmp -s "$mdir/base" "$mdir/now" || continue
    if [ ! -e "$target/$rel" ]; then
      printf '%s\n' "  absent:   $rel (not in the project; the kit changed it since the base, the changelog says whether to copy it)"
      continue
    fi
    if grep -q '^<<<<<<< ' "$target/$rel"; then
      printf '%s\n' "  unresolved: $rel (conflict markers of an earlier merge); resolve them first"; open=1; continue
    fi
    # The owner's file: an agent's write to it is refused, and conflict markers in it leave
    # Claude Code with no hook (review Medium). The kit's change is shown, not merged.
    if [ "$rel" = .claude/settings.json ]; then
      printf '%s\n' "  by hand:  $rel (the owner's file, not merged; the kit's change: git -C '$(printf '%s\n' "$kit" | sed "s/'/'\\\\''/g")' diff ${base%"${base#???????}"} HEAD -- $kp)"
      open=1; continue
    fi
    tr -d '\r' < "$target/$rel" > "$mdir/ours" || die "cannot read $rel"
    rc=0 union="" added=0
    # #330: a kit change that only appends merges as a union, the kit's lines after the project's own: labricore's
    # GOTCHAS.md, which ends in the project's entries, showed a 5-line kit append as a conflict of 400 project lines.
    # Only where every conflict is two insertions at one point (an empty base side in diff3): a project that edited
    # or deleted the base's tail keeps its conflict, or the union would bring the old lines back (review rlight High).
    if head -c "$(wc -c < "$mdir/base")" "$mdir/now" | cmp -s - "$mdir/base" &&
      git merge-file --diff3 -p "$mdir/ours" "$mdir/base" "$mdir/now" |
        awk '/^\|\|\|\|\|\|\| /{b=1;n=0;next} /^=======$/{if(b&&n)bad=1;b=0;next} b{n++} END{exit bad}'; then
      union=--union added=$(( $(wc -l < "$mdir/now") - $(wc -l < "$mdir/base") ))
    fi
    git merge-file $union -p -L project -L "kit base" -L "kit v$latest" \
      "$mdir/ours" "$mdir/base" "$mdir/now" > "$mdir/merged" || rc=$?
    [ "$rc" -lt 128 ] || die "could not merge $rel; it and the files after it are unchanged"
    fill "$mdir/ours" < "$mdir/merged" > "$mdir/filled" && mv -f "$mdir/filled" "$mdir/merged" ||
      die "could not fill the placeholders of $rel; it and the files after it are unchanged"
    # ponytail: CRLF is decided by the file's first line ending, as editors do; a mixed file comes back all CRLF.
    if head -n 1 "$target/$rel" | od -An -c | grep -q '\\r'; then
      sed "s/\$/$cr/" "$mdir/merged" > "$mdir/out" || die "cannot write $rel"
    else
      mv -f "$mdir/merged" "$mdir/out"
    fi
    put "$target/$rel" "$mdir/out" || die "could not write $rel; it and the files after it are unchanged"
    if [ "$rc" -eq 0 ] && [ -n "$union" ]; then
      printf '%s\n' "  merged:   $rel (the kit appended $added lines; they follow the project's own)"
    elif [ "$rc" -eq 0 ]; then
      printf '%s\n' "  merged:   $rel"
    else
      open=1
      # Per conflict, the project side's lines no kit file holds: the project's own content to
      # keep, beside kit text it still has or moved (leeway L4).
      printf '%s\n' "  conflict: $rel, lines $(awk '
        function trim(s) { gsub(/^[ \t\r]+|[ \t\r]+$/, "", s); return s }
        function flush() { if (b) own = own (own != "" ? ", " : "") (b == e ? b : b "-" e); b = 0 }
        FILENAME == ARGV[1] { if ((l = trim($0)) != "") kit[l] = 1; next }
        /^<<<<<<< / { s = FNR; side = 1; own = ""; b = 0; next }
        side && (/^=======\r?$/ || /^[|][|][|][|][|][|][|] /) { side = 0; next }
        /^>>>>>>> / { flush(); printf "%s%d-%d", c, s, FNR; if (own != "") printf " (project-only %s)", own; c = ", "; side = 0; next }
        side && (l = trim($0)) != "" && !(l in kit) { if (b && FNR == e + 1) e = FNR; else { flush(); b = e = FNR } }
      ' "$mdir/kitlines" "$target/$rel")"
    fi
    if [ -s "$mdir/left" ]; then
      printf '%s\n' "  placeholder: $rel: $(cat "$mdir/left"); fill by hand"
      open=1
    fi
  done < "$work_list"
  git -C "$kit" -c core.quotePath=false diff --name-only --no-renames --diff-filter=D "$base" HEAD -- core overlays > "$work_list" ||
    die "cannot list the files the kit removed"
  while IFS= read -r f; do
    owned_rel "$f" || continue
    printf '%s\n' "  kit-removed: $rel (the kit deleted or renamed it since the base; the changelog says what to do)"
  done < "$work_list"
  echo
  printf '%s\n' "sync-kit: version left at v$have. Read each merged file's diff (git diff) and account for"
  echo "          every removed line; resolve each conflict listed (read only those lines);"
  # #319: a project paragraph that restated an old rule survived beside the kit's new Invariant.
  echo "          a paragraph only your copy has is kept as it was: check those beside a changed rule;"
  printf '%s\n' "          then rerun with --actions-applied, without --merge, to record v$latest."
  [ "$open" -eq 0 ] || echo "          Files are listed above as conflict, placeholder, unresolved, skipped, by hand or no base."
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
commit="" recorded=0
if own_repo && commit=$(git -C "$kit" rev-parse -q --verify HEAD); then
  owned_list
  marked=""
  while IFS= read -r kp; do
    owned_rel "$kp" && [ -z "$(blocked "$rel")" ] && [ -f "$target/$rel" ] || continue
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
    recorded=1
  fi
fi
put "$stamp" <<EOF || die "could not write $stamp; version left at v$have"
$latest
EOF
echo
printf '%s\n' "sync-kit: recorded v$latest."
[ "$recorded" -eq 0 ] || printf '%s\n' "sync-kit: commit the upgrade, then review that commit:" "          $review" \
  "          (kit-owned files equal to the kit's are verified by hash, the rest is reviewed; docs/REVIEW_RUNNING.md)"
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
