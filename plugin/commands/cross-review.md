---
description: The review GATE (not a review command) — a second model reviews the change set read-only, then YOU verify every finding instead of relaying it
argument-hint: "[--uncommitted | --base <ref> | --commit <sha>] [--reviewer codex|claude]"
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, Bash(git:*), Bash(./scripts/review.sh:*), AskUserQuestion
---
# /myagentkit:cross-review [--uncommitted | --base \<ref\> | --commit \<sha\>] [--reviewer codex|claude]

The project owner must have asked for this in THIS session — it spends another tool's
budget. Agents do not spend it on their own.

**Needs a second CLI on the machine** — a DIFFERENT model from whichever one authored the
change. `scripts/review.sh` ships adapters for two, `--reviewer codex` and
`--reviewer claude`, and the project's configured default is at the top of that script.
**You may be the author here.** If this session wrote the diff, the reviewer must not be
your own model, whatever the default says. If the script reports the CLI is missing, do not work around it and do
NOT review the diff yourself instead — that defeats the entire point, since you may be the
author. Tell the owner it is not installed, offer to install it, and point at
`docs/DEV_SETUP.md` §3. The fallback meanwhile is the paste-by-hand template in
`docs/REVIEW_GATE.md`, run in a genuinely fresh session.

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

If the reviewer times out, hits quota/context limits, fails authentication, or returns no
valid final response, record its usage/evidence path and leave the review pending. Continue
other independent authorized work. Do not wait indefinitely, retry automatically, switch
models without authorization, or approve the patch yourself. The blocked review still
prevents committing or pushing its protected diff. If nothing independent remains, return
the blocker to the owner. `docs/USAGE.md` describes the local per-call accounting records.
