#!/usr/bin/env sh
# The kit uses the same canonical review implementation it installs into projects.
#
# The kit's own reviewer pins live here rather than in core/scripts/review.sh: that file is
# the TEMPLATE a project customises, so the kit must not smuggle its own model choices into
# what every project inherits.
kit=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd) || exit 2
export REVIEW_REPO_ROOT="$kit"
export REVIEW_DOCS="${REVIEW_DOCS:-core/AGENTS.md, core/docs/ARCHITECTURE.md, core/docs/REVIEW_GATE.md and CONTRIBUTING.md}"
export REVIEW_CODEX_MODEL="${REVIEW_CODEX_MODEL:-gpt-6-astra}"
export REVIEW_CLAUDE_MODEL="${REVIEW_CLAUDE_MODEL:-claude-opus-5}"
exec sh "$kit/core/scripts/review.sh" "$@"
