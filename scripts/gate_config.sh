# The kit repo's own values, for the kit's hooks only (PLAN item 11, owner 2026-11-10). Projects get
# core/scripts/gate_config.sh, the template; this file is kit source and never synced.
#
# What reads it here: guard_risky_review.py (risky_paths), run from the installed copy through
# scripts/kit_hook.sh. Nothing else in the kit sources it, so the template's other values are absent
# on purpose:
# - toolchain_path, build_test_cmd, docs_only_skip_build, docs_always_build, build_cache_inputs,
#   cache_days, module_roots, STRONG_REVIEW_DAYS, STRONG_REVIEW_TASKS, STATE_MAX_LINES: read by
#   core/scripts/check.sh, the projects' gate. The kit's gate is scripts/check.sh (check_kit.py),
#   which the commit hook runs and which reads none of them.
# - DEFAULT_REVIEWER, CODEX_MODEL, CLAUDE_MODEL: read by core/scripts/review.sh from the
#   gate_config.sh beside it, core/scripts/gate_config.sh; the kit's scripts/review.sh sets its
#   models through REVIEW_* instead. doctor.sh reads DEFAULT_REVIEWER but is not run on the kit.

# The kit's high row: hooks, gates, review and worker tooling, and the wiring that runs them (the
# kit has no money path). A Claude Code commit that changes one waits for a diff review
# (guard_risky_review.py; docs/REVIEW_GATE.md, "Risk tiers", class 2).
risky_paths="overlays/claude-code/files/.claude/hooks/* core/.githooks/* core/scripts/check.sh core/scripts/gate_config.sh core/scripts/doctor.sh core/scripts/review.sh overlays/claude-code/files/scripts/spawn_worker.sh overlays/claude-code/files/scripts/watch_workers.sh overlays/claude-code/files/scripts/close_worker.sh overlays/claude-code/files/.claude/agents/diff-reviewer.md overlays/claude-code/files/.claude/settings.json core/scripts/master_writer.py plugins/myagentkit/hooks/* plugins/myagentkit/scripts/* scripts/check.sh scripts/check_kit.py scripts/review.sh scripts/install_self.sh scripts/kit_hook.sh scripts/installed_ref scripts/gate_config.sh scripts/project_validation.py .githooks/* .github/workflows/* .claude/settings.json"
