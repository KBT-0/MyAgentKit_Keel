#!/usr/bin/env sh
# The kit uses the same canonical review implementation it installs into projects.
#
# The kit's own reviewer pins live here rather than in core/scripts/review.sh: that file is
# the TEMPLATE a project customises, so the kit must not smuggle its own model choices into
# what every project inherits.
kit=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd) || exit 2
export REVIEW_REPO_ROOT="$kit"
export REVIEW_DOCS="${REVIEW_DOCS:-core/AGENTS.md, core/docs/ARCHITECTURE.md, core/docs/REVIEW_GATE.md and CONTRIBUTING.md}"
# Pins are fixed snapshots and per reviewer: Codex's JSONL names no model, so the pin is the only
# record, and the vendors' id formats differ (platform.claude.com/docs/en/about-claude/models/
# model-ids-and-versions; learn.chatgpt.com/docs/non-interactive-mode). Critical work (WORKFLOW
# rule 7): set REVIEW_CLAUDE_MODEL to the strongest tier for that run. (B05 inv2#72/#73)
export REVIEW_CODEX_MODEL="${REVIEW_CODEX_MODEL:-gpt-6.1-sol}"
export REVIEW_CLAUDE_MODEL="${REVIEW_CLAUDE_MODEL:-claude-opus-5-5}"
exec sh "$kit/core/scripts/review.sh" "$@"
