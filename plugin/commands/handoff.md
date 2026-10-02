---
description: Produce ONE self-contained implementation prompt to hand current work to another tool, model or session
argument-hint: "<target tool/model> <task summary>"
allowed-tools: Read, Glob, Grep, Bash(git:*), AskUserQuestion
---
# /myagentkit:handoff \<target\> \<task summary\>

Follow `docs/HANDOFF.md` (canonical, in the project) exactly: task and non-goals, file paths
verified to exist right now, restated constraints, acceptance criteria, routing check, a
verifiable Definition of Done, and the "if ambiguous, STOP and ask" rule.

If `docs/HANDOFF.md` is not present, this project was not set up with the kit. Say so and
use the seven-part structure below rather than inventing a format:

1. **Task** — one paragraph, exact scope, explicit non-goals ("do not touch X").
2. **Files** — full paths and member names, verified RIGHT NOW with grep or a read.
3. **Constraints** — the relevant `AGENTS.md` rules quoted verbatim. Never write "follow
   AGENTS.md": the target does not weigh a pointer the way it weighs a quoted rule.
4. **Acceptance** — what the diff must and must not contain, and which gate follows.
5. **Routing check** — does this task belong on the model it is being sent to? Judgement
   work to the strongest model, bulk mechanical work to the cheaper one. If the requested
   route violates that, say so instead of producing the prompt.
6. **Definition of Done** — the exact command or observation that proves it is finished.
   Not "it works". Something the implementer can run and the owner can re-run.
7. **If ambiguous: STOP and ask.** An unanswered question comes back as a question, never
   as a guess buried in the diff.

Verify every path and member name with grep or a read before writing it down. A path from
memory sends the implementer to the wrong place and the diff comes back there.

End with the reminder that updating `docs/STATE.md` at session end is the implementer's job.
Full sentences only — the target has no chat memory and no idea what you were doing.

If this handoff closes a working day, add the cost: `/cost` and the output of
`scripts/agent_cost.py --latest` next to the task count, so the next lead routes from a number.

Raw arguments: `$ARGUMENTS`
