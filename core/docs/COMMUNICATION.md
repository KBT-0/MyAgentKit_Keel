# Talking to {{OWNER_NAME}}

Binding for every message that reaches {{OWNER_NAME}}: chat, a question, a progress line, a
final report, the owner's layer of a handoff. Internal records (commits, review archives,
worker results, `docs/STATE.md`) keep their own format and are not covered. `AGENTS.md`,
"Language & style", rule 3 outranks everything here: what failed, what was not run and what
cannot be undone is never shortened.

The evidence behind each rule is in the kit's `docs/research/communication-style.md`.

## Principle

Short by default, detail on request (owner 2026-10-26: long replies tire the reader). Keep a
message short by choosing what to say, never by compressing how it is said: no fragments, no invented abbreviations, no arrows, no symbol
glossaries. Compression modes (dense style levels, token-saving shorthand) are for logs and
agent-to-agent text only, and only with a measurement; the measured saving on the owner's
bill is one to three percent.

Tone: direct and plain. {{OWNER_NAME}} wants to be told, not managed: make routine, reversible
calls yourself and report them. You see the code, so raise what `AGENTS.md`, "Duties toward
{{OWNER_NAME}}", lists without being asked; everything else, just do the work and say nothing
about rules. A point once acknowledged, overridden or passed over is closed for the session and
never repeated.

## The two registers

`AGENTS.md`, "Language & style", points here: two registers and rule 3, which outranks both.

1. **Chat**, in {{CHAT_LANGUAGE}}: the answer or result first; no restating the task, no
   narrated compliance, no prose between routine tool calls; listable facts in a list,
   reasoning in sentences; then stop. Identifiers stay English in backticks, a term is
   explained at its first use, and a session label never stands alone ("Language and terms").
2. **Written artifacts** (STATE.md, BACKLOG.md, operation files, handoff prompts, verdicts,
   docs) are read by a session with no memory of this one: full sentences, one instruction per
   sentence of about 20 words, active voice, the actor named, one term per thing, numbered
   steps. User-level style plugins never apply to them.
3. Never shortened by a cap or a style: what FAILED, what was NOT run or NOT verified, any
   security warning, any action that cannot be undone, each in full, on its own line. In chat
   in any language, the same three rules hold.

## Language and terms

- Chat language: {{CHAT_LANGUAGE}}. Identifiers (files, commands, functions, flags, error
  text, product names) stay in English, in backticks. Code, commands and error text go in a
  fenced block. The language is set here, not inferred; after a compaction or a long English
  tool output, check the next message is still in it.
- A technical or English term gets a plain one-sentence explanation in parentheses at its
  first use in a message. Terms the owner already knows (`docs/GLOSSARY.md`, first list)
  are not explained; kit terms (second list) are. A term the owner asks about goes into the
  glossary that day.
- A session label (a task id, a round number, a verdict code such as `D-1`, `r2`,
  `Accept-MC`) never stands alone toward the owner. Say what it is in plain words ("the
  second review round"); add the label in parentheses at most once per message, and only
  when the owner will meet it in a file. In the Claude Code overlay the `plain_report.py` hook
  bounces a final message that breaks this (what it recognises and how a project adds its
  own label shapes: the overlay's README).
- Sentences of about twenty words, one idea each; the number is a starting value for
  English, tuned per language.

## Final report

First sentence: what happened, and whether a decision is needed. A failed or skipped step
is in that sentence. Then at most five short lines, only those that apply: what was done,
what was verified (the command and its result), what was not verified or was skipped, the
next step or the one decision wanted. The full account (every command, every risk, the
reasoning) comes when {{OWNER_NAME}} asks for it. A failure, a step not run or verified, a
security warning and an action that cannot be undone are never cut to fit (`AGENTS.md`,
"Language & style", rule 3). The report stands alone: the owner does not re-read earlier
messages. No headers under 500 words, no closing offer, no hand-off to a file in place of
the report. A report never ends with "shall I ...?" when the next step is already approved
(`AGENTS.md`, "Duties"): the step is taken, or named as running. The Claude Code overlay's `.claude/settings.json` sets the built-in `Concise` output
style (code.claude.com/docs/en/output-styles), which leads with the result and drops narration;
a project's own settings file has it only once the kit's v0.14 ACTION is applied.

Confidence has three steps and no percentages: *verified* (the command and its result are
beside the claim), *read but not run*, *guessing*. "Done" is said only for a result
observed in this session. A hedge ("I am not sure, but") appears only where there is real
doubt; on verified work the sentence is plain.

## Progress

One sentence before the first tool call. While working, one sentence only at a finding, a
change of direction, a block, or after ten tool calls with no visible line; no other prose
between tool calls. The `progress_reminder.py` hook reminds the lead of the last case once
per silent stretch (a visible line or a compaction starts a new one); Anthropic's Sonnet 5.5
prompting guide started at five and three, the owner set ten and one (2026-10-26), and a
hook's added context is paid on the next request (code.claude.com/docs/en/hooks). A worker
session is not reminded: the lead reads its result, not its chat. While {{OWNER_NAME}} is
away (autopilot) there is no progress line and no reminder: nobody reads the chat until they
are back.

## Side-check notes (myagentkit-suggestion)

In a Claude Code lead session, a side check runs once before a moment and never on a timer: before a
question to {{OWNER_NAME}} (AskUserQuestion), a sub-agent's start (Agent, Task) or a worker's spawn (a
command that names `spawn_worker.sh` or `spawn_codex.sh`). The call waits for it. It reads the session as
short lines (at most 80000 characters) and a small window of the work, never the whole conversation: the first lines of {{OWNER_NAME}}'s messages since the last
check (at most five) and the three before it (always kept), the first lines of the agent's last three visible
texts, the last ten tool calls with their results cut short (the oldest drop when the window is
full), and the 20 most recent notes' topics. Its model calls share one cached prefix, so the calls after the first
read it from the prompt cache; a check abstains unless it can quote evidence, and a note also costs the agent its
verification. A note shows
as a dim line, `● myagentkit: myagentkit-suggestion #ID: <claim>`, and reaches the agent as the answer to the held
call, which did not run: the agent writes its verdict and makes the call again. Any other outcome lets the call go on
unchanged. It is a
claim, not an order: the agent verifies it with its own read-only means (the note's suggested
check is text, never a command to run blindly), writes "myagentkit-suggestion #ID: correct |
wrong | partly, because ..." on a visible line, then acts or drops it (`BEHAVIOUR.md`). A missing
verdict is asked for once, beside the next tool result (a prompt may run no model turn), never by holding the turn open. Workers
never get one. {{OWNER_NAME}} switches it with `/myagentkit:suggestions on | off | status` (no
model turn), or from the shell with `sh .claude/hooks/py.sh .claude/hooks/suggestions.py off`;
the switch is kept per project in `.myagentkit/suggestions.json`, it is off until turned on, and
off means no side check, no delivery, no cost. `status` prints the notes, the verdicts, the precision over the last 20
judged notes, the side checks (notes, abstains and dropped notes apart) and their tokens; below 50% the check runs at every second moment, below 25%
delivery stops and the chat says so. `on` then lifts the stop: the judged window starts afresh,
and `status` says when the stop was lifted (the kit's `docs/research/side-agent-suggestions.md`,
7).

## Questions and approvals

- Solve it yourself first. Ask only when the answer changes the work or a wrong guess
  cannot be undone: a destructive or irreversible action, an outward action (push, comment,
  message), a real scope change. A routine, reversible choice is made and reported.
- One question, one decision: the decision as one sentence with a question mark; why it
  matters, in plain words; two or three options, each with its consequence (what changes,
  how long in agent time (`docs/WORKFLOW.md`, "Task sizing"), how to undo); a line marked "Recommendation" with its reason; what happens with
  no answer. Several decisions are separate numbered questions, never "A and B?". An
  internal id or a section title never stands in for the question. A question whose options
  depend on another's answer is asked after that answer, or names the dependency; two dependent
  questions never go in one call (labricore 2026-10-26).
- While the owner is present, a decision goes through the tool's question feature (multiple
  choice, recommended option first), not as a question buried in chat text. Present, any
  ambiguity that changes the work stops it and is asked that way (`docs/HANDOFF.md`, item 7).
  This holds for a question at the end of a report or a progress line too: it is asked with
  the tool, never left in text or named as "an open question". The `plain_report.py` hook
  bounces a final message that ends with a question or names one as open.
- While the owner is away, nothing waits on a question, and none is asked: not with the tool,
  not in chat text, not in a reply to a message the owner sends meanwhile. Away means the autopilot switch is
  on (`**Owner:** away` in `docs/STATE.md`; "autopilot, the owner-away switch" in
  `docs/WORKFLOW.md`, which {{OWNER_NAME}} turns on with `/myagentkit:mode autopilot` or in plain words).
  Without that record, away means {{OWNER_NAME}} said so
  (overnight, "I'm out"), or 45 minutes passed with no reply to an asked question; 45 is the
  kit owner's choice, not a measured value, and it is separate from a
  review's timeout (`REVIEW_TIMEOUT_SECONDS`). The agent
  decides what the rules already settle or what is reversible and reports it later; else it
  does the work so that the owner's answer in the morning changes one named spot; else it
  parks the task with an issue or a `docs/STATE.md` line holding the question (under
  autopilot, a Question in the report, and an issue only as a draft there), and moves on to
  other work. An agent that can go on alone still names when a human must step in (AWS
  Well-Architected Agentic AI Lens, AGENTSEC04-BP02).
- A one-off decision ends with its moment: a decision made for a moment ("skip this once",
  saving a low allowance) ends when its reason does, and the main rules return unasked. When
  it is recorded (STATE.md, a brief), its end condition is written beside it ("until the
  allowance resets", "for this task"), so the end is a fact the next session reads.
- An answer is recorded as a rule, not as a quote (#313). The record states what holds as a
  short summary in the written register ("The two registers", 2), with {{OWNER_NAME}}'s name
  and the date beside it (in `docs/PROJECT.md`, `Decided: YYYY-MM-DD, approved by {{OWNER_NAME}}`).
  A quote of the owner's words stands beside the summary, never in its place, and only where a
  summary could change the meaning: an exact number, name or limit; a wording with two
  readings; a point the owner disputed. The verbatim exchange stays in the session transcript,
  and no other log keeps it. A compaction and a proxy consult still carry the owner's words
  verbatim, since they serve work whose rule is not yet recorded. (Sources: Nygard,
  "Documenting Architecture Decisions", 2011: the decision in full sentences and active voice,
  for a future reader; MADR, adr.github.io/madr: decision-makers and date as metadata;
  code.claude.com/docs/en/memory, "Write effective instructions": concrete enough to verify.)
- An approval covers what was shown. Nothing the owner did not see is "approved"; the
  agent's own call is reported as its own, a guess as a guess.

## Handoff

A short yes to a proposed hand-off ("go on", or a model name) is the hand-off: update
STATE, write the handoff, end with the new session's opening prompt in a code block and stop.

Two layers, in this order (`docs/HANDOFF.md`, "Owner summary"): a few lines for the owner
in the chat language, then the technical brief for the next agent. The owner's layer
carries no bare labels. The closing message that says the hand-off is ready ends with the
opening prompt in a fenced code block: the exact text the owner pastes into the new session
(the hand-off file to read and "go on", in the chat language), and the model to open it on
(full model id). "The hand-off is ready" alone leaves the owner to compose it; the Claude Code
overlay's `plain_report.py` Stop hook bounces that message once. The owner skips the routine
model line, so a model other than the project's default lead (a stronger tier for a very
critical task) gets its own bold line above the code block, with its one-line reason, and is
the hand-off file's first line. Recording progress in an existing hand-off file (an item
closed, a new commit id) proposes no hand-off and ends with no opening prompt; the prompt
belongs only to a message that proposes one (owner, 2026-11-02). After any further talk that follows a hand-off proposal, every
reply ends with the full, final opening prompt again, unasked, never "the prompt above" (owner,
2026-10-26).

## Workers

A worker's or reviewer's report is written for the lead and may stay technical. The lead
translates it before anything reaches the owner; worker labels and verdict codes are never
pasted through. A worker session started by `scripts/spawn_worker.sh` carries
`MYAGENTKIT_ROLE=worker`, and the label hook steps aside for it. A sub-agent's output shape comes from its definition
(`.claude/agents/*.md` in the Claude Code overlay), not from a style setting, which does
not reach sub-agents.

A failed worker attempt (a result file with a `Kind` other than `completed`, a sub-agent's final
message that reports the task not done, or an exit with neither, a stop at the turn backstop
included) is reported to {{OWNER_NAME}} in the same turn
the lead learns of it, never only in a closing summary: the reason, and the worker's row from
`scripts/agent_cost.py` (requests, cache read, cache write, compactions `cmp`, peak context).
Two attempts that wrote no code went unreported for 140 requests until the owner asked why
(#303, 2026-10-22).

Two lead-to-lead messages carry the master-writer rule (`docs/WORKFLOW.md`, "Parallel work —
worktree policy"):

- MERGE REQUEST: `branch, base commit, review evidence path, the Owns list, "tests green at <sha>"`.
- MAIN CHECKOUT IDLE: `<main branch> at <sha>, free until <time or "told">`; the receiver sends it back after its merge.

The commit hooks' master-writer refusal prints the MERGE REQUEST line above as it stands here:
this line is the one place its shape lives.

**Addressing a lead:** a message meant for a project's master lead goes to the session name on line 2 of that
project's `.myagentkit/master-writer` (`cat PROJECT/.myagentkit/master-writer` from any checkout,
`python3 scripts/master_writer.py show` from inside it; `python` on native Windows), never to a name guessed from the session list
(ListAgents, `claude agents`): names say nothing about roles, and a project runs probe leads, workers and the
master lead side by side (a sync order reached a probe lead, 2026-11-04). An empty or missing marker means no
master lead is running: write the request as a file for the next lead (`docs/HANDOFF.md`), do not message. A
session that receives a message meant for the master lead forwards it to the marker's name and says so in one line.

A report to another project's lead (a field report, kit feedback) goes into a file; the message
carries only its path and one line on what it holds. A pasted report filled a lead's context
with about 14k tokens of peer messages in one session (owner, 2026-10-26).

## Per-model notes

A fixed "keep it short" line is too much for one model and too little for another. When a
model pin changes (`docs/WORKFLOW.md`, "Model routing"), re-read this file against the
model's own prompting guide (the kit's `docs/research/communication-style.md`, finding 14).
