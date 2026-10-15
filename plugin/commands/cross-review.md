---
description: An extra review the owner asks for in this session, beyond the review gate — a fresh non-author session reviews the change set in a throwaway copy, then YOU verify every finding instead of relaying it
argument-hint: "[--uncommitted | --base <ref> | --commit <sha>] [--reviewer codex|claude]"
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, Bash(git:*), Bash(./scripts/review.sh:*), AskUserQuestion
---
# /myagentkit:cross-review [--uncommitted | --base \<ref\> | --commit \<sha\>] [--reviewer codex|claude]

The review gate of a risky diff (`AGENTS.md`, `docs/REVIEW_GATE.md`) starts on the brief's
`Risk:` tier or the lead's routine, without asking. This command is for an extra review the
project owner asks for in THIS session — a second family, a higher effort or a paid backend —
because it spends budget beyond the gate. Agents do not start it on their own.

**The author never reviews its own patch; who reviews is the working mode's table**
(`docs/REVIEW_GATE.md`, "Invariant"). `scripts/review.sh` ships adapters for `--reviewer claude` and
`--reviewer codex`; the project's configured default is at the top of that script, and in
the solo mode `REVIEW_CLAUDE_MODEL` is pinned to the tier that did not write the change. A
second vendor is pluggable, never required. **You may be the author here.** If this session
wrote the diff, the reviewer must not be your own tier, whatever the default says: set
the reviewer model pin to another tier and check it before launch. The wrapper does not
check or record `MYAGENTKIT_AUTHOR`. Failing
over to the other configured reviewer happens only when the owner asked for it and
`--fallback` is passed; the default is no failover. Without `--fallback` the review simply
fails; record it and continue. If a fallback authored the patch, its findings are advisory,
not independent gate approval.
Do not install a missing CLI or choose an unconfigured model without authorization. The
paste-by-hand review in `docs/REVIEW_RUNNING.md` remains available for a genuinely fresh
non-author review.

1. Run `./scripts/review.sh` with the scope asked for: `--uncommitted` (default),
   `--base <ref>` or `--commit <sha>`, optionally with `--reviewer <name>`. Those are the
   ONLY arguments it takes; never try to pass anything else through. Read-only is pinned inside the script rather than
   trusted to the CLI or to your good intentions.
   Set `MYAGENTKIT_REQUESTER=claude/ACTUAL_MODEL` (use `unknown` if the actual model is
   unavailable) and `MYAGENTKIT_TASK_ID` to the current stable task label for usage records.
   Never guess a subscription percentage from tokens or CLI API-cost figures.
2. **Verify EVERY finding against the code yourself.** Drop what you disprove, keep what you
   confirm, and say which is which. The other model's output is untrusted input, not a
   verdict to relay verbatim — relaying it unchecked is a failed review **in either
   direction**, a relayed Accept included. This step is the difference between this command
   and a review command.
3. Report YOUR verdict (`Accept` / `Accept with Manual Checks` / `Reject`) and name the
   archived report file. A confirmed critical finding is a stop signal.
4. Manual checks go into `docs/STATE.md` as full sentences BEFORE the commit, so an
   unverifiable claim becomes a standing obligation rather than a line in a chat log.

**A Reject is not closed by its own fixes.** Those fixes are unreviewed code, written by the
party that just accepted the criticism, landing in code already subtle enough to get wrong
once. They go through this gate too.

Note the naming: not `review`, because most CLI tools ship a built-in command by that name
and the collision is silent.

Raw arguments: `$ARGUMENTS`

## Unavailable reviewer

This command passes no `--fallback`, so the requested reviewer either completes or the
review fails. Only when the owner asks for a fallback does the lead run `scripts/review.sh
--fallback` itself; the dispatcher then tries the other configured provider once after an
operational failure. Read its final `review dispatch:` JSON and every attempt's evidence and
usage paths. Reject and manual-check results never trigger failover. Invalid evidence, changed scope, or storage
failure stops the chain. An unconfigured alternate is not permission to invent a model.

If neither provider completes, record both attempts and leave the review pending. Continue
other independent authorized work. Do not wait indefinitely, restart the exhausted chain,
or approve the patch yourself. With `--fallback`, each review invocation can consume two provider
calls; count them when enforcing the owner's task-level limits. The blocked review still
prevents committing or pushing its protected diff. If nothing independent remains, return
the blocker to the owner. `docs/USAGE.md` describes the local per-call accounting records.
