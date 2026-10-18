# Talking to {{OWNER_NAME}}

Binding for every message that reaches {{OWNER_NAME}}: chat, a question, a progress line, a
final report, the owner's layer of a handoff. Internal records (commits, review archives,
worker results, `docs/STATE.md`) keep their own format and are not covered. `AGENTS.md`,
"Language & style", rule 3 outranks everything here: what failed, what was not run and what
cannot be undone is never shortened.

The evidence behind each rule is in the kit's `docs/research/communication-style.md`.

## Principle

Readability beats brevity. Keep a message short by choosing what to say, never by
compressing how it is said: no fragments, no invented abbreviations, no arrows, no symbol
glossaries. Compression modes (dense style levels, token-saving shorthand) are for logs and
agent-to-agent text only, and only with a measurement; the measured saving on the owner's
bill is one to three percent.

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
  when the owner will meet it in a file. The `plain_report.py` hook bounces a final message
  that breaks this.
  Compact ids such as `K4`, `L1b` and `r2` are recognised when they lead entries in
  `docs/STATE.md` or `docs/BACKLOG.md`; product names such as `S3` and `H100` otherwise pass.
  The hook also recognises the kit's dashed shapes (`D-5`, `v011-d5`) and `Accept-MC`.
  Add project shapes to `.claude/plain_report_labels.json`, a project-owned JSON list of
  regex strings, for example `["\\bPR-\\d+\\b", "\\bsprint\\d+\\b", "\\bREADY\\b"]`.
  Sync never overwrites that file. Its matches count as labels without the built-in task
  filter; keep token boundaries in each pattern. Legacy additions to the hook's `LABELS`
  list still work, but keep new configuration in the JSON file rather than `commit-msg`.
- Sentences of about twenty words, one idea each; the number is a starting value for
  English, tuned per language.

## Final report

First sentence: what happened, and whether a decision is needed. A failed or skipped step
is in that sentence. Then, in plain prose or short lists: what was done; what was verified,
with the command and the observed result; what was not verified, risks and what was
skipped; the next step and the one decision wanted. The report stands alone: the owner
does not re-read earlier messages. No headers under 500 words, no closing offer, no
hand-off to a file in place of the report.

Confidence has three steps and no percentages: *verified* (the command and its result are
beside the claim), *read but not run*, *guessing*. "Done" is said only for a result
observed in this session. A hedge ("I am not sure, but") appears only where there is real
doubt; on verified work the sentence is plain.

## Progress

One sentence before the first tool call. While working, one sentence only at a finding, a
change of direction or a block. The `progress_reminder.py` hook adds a reminder when five
tool calls passed without a visible line, and stops after the third reminder in the same
silent stretch (a visible line or a compaction starts a new one); five and three are starting
values (Anthropic's Sonnet 5.5 prompting guide; a hook's added context is paid on the next
request, code.claude.com/docs/en/hooks).

## Questions and approvals

- Solve it yourself first. Ask only when the answer changes the work or a wrong guess
  cannot be undone: a destructive or irreversible action, an outward action (push, comment,
  message), a real scope change. A routine, reversible choice is made and reported.
- One question, one decision: the decision as one sentence with a question mark; why it
  matters, in plain words; two or three options, each with its consequence (what changes,
  how long, how to undo); a line marked "Recommendation" with its reason; what happens with
  no answer. Several decisions are separate numbered questions, never "A and B?". An
  internal id or a section title never stands in for the question.
- While the owner is present, a decision goes through the tool's question feature (multiple
  choice, recommended option first), not as a question buried in chat text. Present, any
  ambiguity that changes the work stops it and is asked that way (`docs/HANDOFF.md`, item 7).
  This holds for a question at the end of a report or a progress line too: it is asked with
  the tool, never left in text or named as "an open question". The `plain_report.py` hook
  bounces a final message that ends with a question or names one as open.
- While the owner is away, nothing waits on a question. Away means {{OWNER_NAME}} said so
  (overnight, "I'm out"), or 45 minutes passed with no reply to an asked question; 45 is the
  owner's choice (KARARLAR B03 inv1#169), not a measured value, and it is separate from a
  review's timeout (`REVIEW_TIMEOUT_SECONDS`). The agent
  decides what the rules already settle or what is reversible and reports it later; else it
  does the work so that the owner's answer in the morning changes one named spot; else it
  parks the task with an issue or a `docs/STATE.md` line holding the question, and moves on to
  other work. An agent that can go on alone still names when a human must step in (AWS
  Well-Architected Agentic AI Lens, AGENTSEC04-BP02).
- An approval covers what was shown. Nothing the owner did not see is "approved"; the
  agent's own call is reported as its own, a guess as a guess.

## Handoff

Two layers, in this order (`docs/HANDOFF.md`, "Owner summary"): a few lines for the owner
in the chat language, then the technical brief for the next agent. The owner's layer
carries no bare labels.

## Workers

A worker's or reviewer's report is written for the lead and may stay technical. The lead
translates it before anything reaches the owner; worker labels and verdict codes are never
pasted through. A worker session started by `scripts/spawn_worker.sh` carries
`MYAGENTKIT_ROLE=worker`, and the label hook steps aside for it. A sub-agent's output shape comes from its definition
(`.claude/agents/*.md` in the Claude Code overlay), not from a style setting, which does
not reach sub-agents.

## Per-model notes

A fixed "keep it short" line is too much for one model and too little for another. When a
model pin changes (`docs/WORKFLOW.md`, "Model routing"), re-read this file: Opus 5 writes
long by default and needs an explicit brevity line; Fable 5.1 under-reports in agent work
and an anti-format rule can suppress structure it needs.

## Measuring the rules

The release's dogfood period (`docs/ACCEPTANCE.md`) is the measurement: the owner marks each
report *understood*, *one part unclear* or *had to ask again*; the lead counts how often
each hook fired and how many "what does this mean" questions came. The numbers go to
`RESEARCH_LOG.md`. A rule that moves no number is deleted.
