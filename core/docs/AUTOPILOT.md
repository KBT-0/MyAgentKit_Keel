<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->
# The autopilot report

The lead keeps one report per absence at `.myagentkit/autopilot/<date of the stamp>.md`
(ignored by Git; a new file each time, so no living file grows), copied from the template
below by the lead right after `working_mode.py autopilot`, and filled as the night goes,
never only at the end. The rules: "autopilot, the owner-away switch" in `docs/WORKFLOW.md`.
The morning: the lead runs `working_mode.py present`, then
`python3 scripts/autopilot_report.py` (`python` on native Windows), whose output is the Done
section, gives the report in two layers (`docs/COMMUNICATION.md`, "Handoff"), then asks
the Questions one by one with AskUserQuestion.

Done comes from git, never from the lead's own account. Every other line is short: a long
queue pushes the owner into approving in bulk.

```markdown
# Autopilot <since> – <until>

## Done
<!-- The autopilot_report.py output: commits and merges since the stamp, worker
     results, the cost line. Then one plain line per finished item of the list. -->

## My decisions
<!-- One per decision the rules let the lead take alone. -->
- **<decision>.** Options: <a>, <b>. Reason: <why>. Undo: <command or step>.

## Consults
<!-- One per proxy consult; the proxy's call, not the owner's approval. -->
- **<question>.** Proxy: <model, effort>. Its answer: <ranking, strongest objection>. What I
  did: <action>. Undo: <step>.

## Questions
<!-- Only what the owner alone can answer, most important first, each with a recommendation.
     Asked one by one with AskUserQuestion in the morning. -->
1. **<the decision as one sentence?>** Why it matters: <plain words>. Options: <a> /
   <b>. Recommendation: <a>, because <reason>. Waiting on it: <item or "nothing">.

## Parked
<!-- Items not done because they need the owner (the never list, a scope change). -->
- <item>: <why parked>, <what unblocks it>.

## Stalls
<!-- Time lost: a permission prompt nobody answered, a blocked action, a usage-limit wait,
     from the times on the progress lines. -->
- <from> – <to>: <cause>.

## Cost
<!-- The cost line from autopilot_report.py; /usage's Session block if the owner reads it. -->

## Remaining
<!-- What is left of the list, and the next step for each. -->

## Issue drafts
<!-- Never posted overnight; posted only on the owner's yes. -->
### <title>
<body, ready to post>
```
