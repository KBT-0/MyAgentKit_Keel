---
description: Produce ONE self-contained implementation prompt to hand current work to another tool, model or session
argument-hint: "<target tool/model> <task summary>"
allowed-tools: Read, Glob, Grep, Bash(python scripts/agent_cost.py --latest), Bash(python3 scripts/agent_cost.py --latest), Bash(py -3 scripts/agent_cost.py --latest), AskUserQuestion
---
# /myagentkit:handoff \<target\> \<task summary\>

**Kit version.** This plugin is kit v0.12.0. Before anything else, read the project's
`docs/kit/.kit-version` (such as `0.10` or `0.12.1`). When it is there and names another
version, print one plain line and go on, never stop for it: both versions, which one is newer
(compared part by part as numbers, a missing part counting as 0:
0.12 is 0.12.0, and 0.9 is older than 0.11), and that `/myagentkit:sync` brings the project
to the kit's newest release; when the project is the newer one, update this plugin too. No
file, or the same version: no line. Nothing here uses the network.

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
7. **If ambiguous: STOP and ask.** Do not assume, do not invent scope, do not widen the task
   to make an unclear part fit. An unanswered question comes back as a question, not as a
   guess buried in the diff. A spawned session has nobody to ask in its pane: it finishes
   what does not depend on the answer, writes `Kind: blocked` and the question into its
   result file, and publishes the question last. The answer comes into that same session,
   never a fresh one, and a cut-off session is resumed the same way (`docs/WORKFLOW.md`,
   "Worker cost").

Verify every path and member name with grep or a read before writing it down. A path from
memory sends the implementer to the wrong place and the diff comes back there.

End with the reminder that updating `docs/STATE.md` at session end is the implementer's job.
Full sentences only — the target has no chat memory and no idea what you were doing.

If this handoff closes a working day, add the cost next to the task count, so the next lead
routes from a number: the output of `python scripts/agent_cost.py --latest` (`python3` or
`py -3` where that is the interpreter's name), and the Session block of `/usage`. `/usage` is
a built-in command only the owner can run: ask the owner to paste it, and write
`/usage: NOT RUN` when no figure came; never write a figure you did not read.

Raw arguments: `$ARGUMENTS`
