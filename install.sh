#!/usr/bin/env sh
# MyAgentKit_Keel — the one-line front door. Fetch the kit at its release tag into a per-user
# cache, then run that kit's bootstrap.sh on the current directory (or, in sync mode, its
# sync-kit.sh). Everything the install does is bootstrap's; this only saves the clone.
#
# Usage, from the project root:
#   curl -fsSL https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh | sh
#   curl -fsSL .../install.sh | sh -s -- --overlay claude-code     # bootstrap's options pass through
#   curl -fsSL .../install.sh | sh -s -- sync [--merge]            # sync-kit's options pass through
#
#   MYAGENTKIT_REF   the kit tag or branch to fetch (default: this release's tag, v$version)
#   MYAGENTKIT_REPO  the kit repository (default: the GitHub one; a file:// URL for tests)
#
# The cache is ~/.myagentkit/kit, one clone with full history: sync-kit.sh --merge reads the
# kit commit a project was installed from. A rerun fetches into it and never clones twice.
# Every failure (git missing, no network, no such ref) stops before the project is touched.
set -eu

# The kit release this installer pins; the release steps raise it (CONTRIBUTING.md).
version=0.11
repo=${MYAGENTKIT_REPO:-https://github.com/KBT-0/MyAgentKit_Keel.git}
ref=${MYAGENTKIT_REF:-v$version}
kit=$HOME/.myagentkit/kit

die() { printf '%s\n' "install: $1" >&2; exit 1; }

run=bootstrap.sh
if [ "${1:-}" = sync ]; then run=sync-kit.sh; shift; fi

command -v git >/dev/null 2>&1 || die "git is missing: install Git (on Windows, Git for Windows) and rerun; nothing was changed"

if [ ! -d "$kit/.git" ]; then
  [ ! -e "$kit" ] || [ -z "$(ls -A "$kit" 2>/dev/null)" ] ||
    die "$kit exists and is no git clone: move it away and rerun; nothing was changed"
  { mkdir -p "$kit" && git init -q "$kit"; } || die "cannot create the kit cache $kit; nothing was changed"
fi
git -C "$kit" fetch -q "$repo" "$ref" ||
  die "cannot fetch $ref from $repo (no network, or no such tag or branch); set MYAGENTKIT_REF to another; nothing was changed"
git -C "$kit" -c advice.detachedHead=false checkout -q --force --detach FETCH_HEAD ||
  die "cannot check out $ref in $kit; nothing was changed"
printf '%s\n' "install: kit $ref ($(git -C "$kit" rev-parse --short HEAD)) in $kit"

exec sh "$kit/$run" "$PWD" "$@"
