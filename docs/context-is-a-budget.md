# Every always-loaded file is a bill paid per session

Some files are read at the start of every session, in every tool: the constitution, the
architecture map, the state file, plus the description of every installed skill and the tool
catalogue of every enabled MCP server. Their combined size is a cost you pay before any work
happens — every session, forever, whether or not any of it turns out to be relevant.

This is not a readability preference dressed up in economics. It is the largest single cost
lever in a repeated-session workflow, and it is the one people never look at because it does
not appear on any one invoice line.

## Keep the prefix small AND stable

Cached input tokens are discounted heavily on the providers this kit assumes. That discount
applies to a STABLE prefix — and every edit to an always-loaded file invalidates the cache
for every session after it.

Two consequences that feel unnatural and are worth following anyway:

- **Do not edit the constitution or the architecture map in the middle of a session** unless
  the task IS that document. A one-line clarification, made in passing, costs the cache.
- **Batch documentation edits into their own task and their own session.** Then the
  invalidation happens once, deliberately.

And keep the volatile things out of the stable files: current status belongs in the state
file, which is read on demand and expected to churn.

## Tiering, rather than deleting

The answer is not to write less down. It is to be deliberate about what loads when:

| Tier | Examples | Rule |
|---|---|---|
| Every session | constitution, architecture map, state file | Small, stable, always true |
| On demand | trap log, setup docs, patterns, long-form rationale | Referenced in one line; read when relevant |
| Never loaded | git history, archived review reports | Evidence, not context |

The trap log is the clearest case. It grew to eighteen entries in the founding project and
costs nothing per session, because the constitution mentions it in a single line — "read it
when something behaves unexpectedly". Had it been in the reading order, that same content
would be a tax on every task that never touches it.

## Tools have to earn their place

An MCP server injects its entire tool catalogue into every request whether or not you call a
tool. A skill costs its description in every session. A dozen of each is thousands of tokens
before anyone types anything.

Hence the default verdict of REJECT in `setup/RESEARCH_PROTOCOL.md`, and hence a new server
needing the same approval as a new dependency. The question is never "is this useful?" —
almost everything is somewhat useful. It is "is this worth paying for on every turn,
including the turns that have nothing to do with it?"

Most custom servers also lose to a plain CLI the agent already has. `git`, `grep`, `jq` and
the build tool cost zero permanent context and are more reliable.

## The other side of the ledger

Output is a bill too, paid per turn: restating the task, narrating compliance, summarising
your own summary. Hence the first writing register in `AGENTS.md` ("Language & style"):
the answer first, then stop.

But **written artifacts are the exact opposite** and the distinction is not negotiable. The
state file, handoff prompts and review reports are always full explicit sentences, because
the next reader is a tool with no context and no idea what shorthand you had in mind. Terse
where it is repeated; complete where it is the only record.

## The failure mode it prevents

A workflow that gets quietly more expensive and slower every month, as documents grow and
tools accumulate, until sessions are spending a large fraction of their budget on context
that had nothing to do with the task — and nobody can point to when it happened, because no
single addition was unreasonable.
