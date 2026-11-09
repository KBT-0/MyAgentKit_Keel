#!/usr/bin/env sh
# Kit source only, like scripts/check.sh; projects never get it. Installs the kit's own hooks into
# this repo like a project's, from a PINNED copy (PLAN item 11, owner 2026-11-10): the kit used to
# run its hooks from overlays/ directly, so a worker editing band_guard.py or check.sh was governed
# by the file it edited, and with no core.hooksPath its worktrees committed past no gate.
#
# Usage: sh scripts/install_self.sh      (the lead, once per main checkout, and after each move of
#                                          scripts/installed_ref; re-running it is harmless)
#
# - Reads the ref from scripts/installed_ref (one line: a tag or a commit; a release moves it,
#   CONTRIBUTING.md) and resolves it to a commit.
# - Makes .myagentkit/installed/<commit>/ in the MAIN checkout (.myagentkit/ is per checkout and
#   ignored; worktrees resolve the main one, scripts/kit_hook.sh) from that commit, laid out as a
#   project holds the files:
#     .claude/hooks/  <- overlays/claude-code/files/.claude/hooks/  every Claude Code hook settings.json runs
#     .githooks/      <- core/.githooks/                            the commit hook (and plain_report.py reads
#                                                                   commit-msg's task-id grammar from it)
#     scripts/        <- core/scripts/ and overlays/claude-code/files/scripts/   what a hook may load from a
#                                                                   project's scripts/ (model_check.py's
#                                                                   agent_cost.py); unused by the hooks the
#                                                                   kit runs today, kept so the copy is whole
#   then makes it read-only (chmod -R a-w): an edit there is refused, and the copy changes only by a
#   new ref. An existing copy of the same commit is kept, never rewritten.
# - Points .myagentkit/installed/current (a one-line file: a symlink fails on native Windows) at it.
# - Sets core.hooksPath to .githooks in the main checkout's config, which every worktree shares:
#   .githooks/* hand each git hook to the copy through scripts/kit_hook.sh.
# Older copies stay; remove one with chmod -R u+w DIR, then rm -r DIR.
set -eu
kit=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
cd "$kit"
common=$(git rev-parse --git-common-dir)
main=$(CDPATH= cd -- "$common/.." && pwd -P)
ref=$(sed -n '1s/[[:space:]]*$//p' scripts/installed_ref 2>/dev/null) || ref=
[ -n "$ref" ] || { echo "install_self.sh: scripts/installed_ref names no ref" >&2; exit 1; }
sha=$(git rev-parse --verify -q "$ref^{commit}") ||
  { printf '%s\n' "install_self.sh: '$ref' (scripts/installed_ref) is no commit in this repository; fetch its tag first" >&2; exit 1; }
inst=$main/.myagentkit/installed
dest=$inst/$sha
mkdir -p "$inst"
if [ ! -d "$dest" ]; then
  tmp=$inst/.tmp-$$
  rm -rf "$tmp"
  trap 'chmod -R u+w "$tmp" 2>/dev/null; rm -rf "$tmp"' EXIT
  for pair in overlays/claude-code/files/.claude/hooks:.claude/hooks core/.githooks:.githooks \
              core/scripts:scripts overlays/claude-code/files/scripts:scripts; do
    src=${pair%%:*} dst=${pair#*:}
    git cat-file -e "$sha:$src" 2>/dev/null || { printf '%s\n' "install_self.sh: $ref has no $src" >&2; exit 1; }
    mkdir -p "$tmp/$dst"
    # Through a file, not a pipe: a failed git archive must stop here, not leave a partial copy.
    # The whole commit with a path, never the subtree "$sha:$src": only then does the commit's root
    # .gitattributes apply, and with core.autocrlf=true (Git for Windows) a subtree archive gives
    # every hook CRLF, so py.sh dies on $'\r' and every hook blocks.
    git archive --format=tar -o "$tmp/part.tar" "$sha" -- "$src"
    mkdir "$tmp/part"
    (CDPATH= cd -- "$tmp/part" && tar -xf "$tmp/part.tar")
    cp -R "$tmp/part/$src/." "$tmp/$dst"
    rm -rf "$tmp/part" "$tmp/part.tar"
  done
  mv "$tmp" "$dest"
  trap - EXIT
fi
chmod -R a-w "$dest"
printf '%s\n' "$sha" > "$inst/current.tmp"
mv -f "$inst/current.tmp" "$inst/current"
git -C "$main" config core.hooksPath .githooks
[ -f "$main/.githooks/pre-commit" ] ||
  printf '%s\n' "install_self.sh: $main/.githooks/pre-commit is missing: merge the commit that brings .githooks/ first" >&2
printf '%s\n' "install_self.sh: installed $ref ($sha) read-only at $dest; core.hooksPath=.githooks"
printf '%s\n' "  hooks: $(cd "$dest/.claude/hooks" && ls | tr '\n' ' ')"
