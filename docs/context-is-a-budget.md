# Every always-loaded file is a bill paid per session

Some files are read at the start of every session, in every tool: the constitution, the
architecture map, the state file, plus the description of every installed skill and the tool
catalogue of every enabled MCP server. Their combined size is a cost you pay before any work
happens — every session, forever, whether or not any of it turns out to be relevant.

This is not a readability preference dressed up in economics. It is the largest single cost
lever in a repeated-session workflow, and it is the one people never look at because it does
not appear on any one invoice line.

## Keep the prefix small, and change it deliberately

Cached input tokens are discounted heavily on the providers this kit assumes: the
always-loaded files are written to the cache once per session and read at a tenth of the
price or less on every turn after. The per-session bill is real but small. Measured on
2026-10-13 (first request of `claude -p`, see `RESEARCH_LOG.md`): the kit's 244-line
constitution cost 5.8k cache-write tokens per cold session and its 165-line successor 4.1k,
beside 16k written and 16k read for the prefix the owner does not control (system prompt,
tool catalogue, skill descriptions, user-level instructions).

The larger cost is adherence. Every vendor keeps the always-loaded file under about 200
lines because a long one makes the model skip the rules it contains. The map is short so
that it is followed, not so that it is cheap.

Two rules that feel unnatural and stand anyway:

- **Edit the constitution or the architecture map in their own task, not in passing.** Not
  because an edit breaks the cache: in Claude Code it does not, the file is read once at
  start and the edit is not even applied until `/clear`, `/compact` or a restart. A rule
  changed in passing is a rule nobody reviewed, and the session that changed it keeps
  running on the old text.
- **Batch documentation edits into their own task and their own session**, so the change
  lands once, reviewed, and every later session starts on the same text.

What does invalidate a running session's cache: changing the model or fast mode, adding or
removing an MCP server, denying a whole tool, compaction, and a Claude Code upgrade.

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

What an MCP server costs depends on the tool. In Claude Code its tools are deferred by
default: a session pays the tool names and the server's instructions, about a hundred
tokens per server, and a schema is loaded only when the tool is called. Behind an
`ANTHROPIC_BASE_URL` gateway, on a provider without tool search, and in Codex, the whole
catalogue is still injected into every request, and seven servers have cost a third of a
200k window. A skill costs its description in every session in every tool. And adding or
removing a server mid-session invalidates a running session's cache, which a skill does not.

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

## Compaction is a purchase too

The line is 200k tokens of context. Past it every request re-reads the whole window, and
the measured cost of a session grows faster than its window does, so a summary at the line
is cheaper than ten more turns at full size. But compaction itself re-reads the window
uncached, which is why the rule has three parts: compact only while the cache is warm; a
session resumed after more than an hour writes its summary into the handoff first, since
its next request is re-written at full price anyway; and when the work changes direction,
`/clear` with a handoff instead of a summary that carries finished detail. A Codex worker
sets `model_auto_compact_token_limit` to 200k–250k for the same line. The procedure, with
the measured numbers, is rule 8 of "Worker cost" in `core/docs/WORKFLOW.md`.

## The failure mode it prevents

A workflow that gets quietly more expensive and slower every month, as documents grow and
tools accumulate, until sessions are spending a large fraction of their budget on context
that had nothing to do with the task — and nobody can point to when it happened, because no
single addition was unreasonable.
