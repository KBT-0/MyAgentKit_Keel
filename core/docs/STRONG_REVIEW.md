# STRONG_REVIEW.md — the strong review cycle's open list

What the next strong review answers, and the findings of earlier cycles that are not closed
yet (`docs/WORKFLOW.md`, "The strong review cycle"). Each finding keeps the task id its report
gave it, with the triage mark beside it. A closed id is deleted from this file and from every
report in the same commit, which carries `Done: <id>`; `.githooks/commit-msg` and
`./scripts/check.sh` refuse the id while any of them still names it. A hook, not a written
reminder, because a hook runs every time and an instruction is advice (Claude Code best
practices, https://code.claude.com/docs/en/best-practices, "Set up hooks").

The cycle runs at least every `STRONG_REVIEW_DAYS` days (10) or after `STRONG_REVIEW_TASKS`
closed tasks (20), whichever comes first; `./scripts/check.sh` reminds when either is passed.
The numbers are an owner's choice, not a measured cadence (`docs/WORKFLOW.md`, "The strong
review cycle").

---

## Questions for the next cycle

## Open findings (id — report — accepted | parked)
