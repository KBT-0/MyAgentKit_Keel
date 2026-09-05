# The roles swap; the plumbing under them does not

The kit's review rule names two roles, AUTHOR and REVIEWER, and refuses to name a vendor for
either. `./scripts/review.sh --reviewer codex|claude` makes that real: both directions run,
both archive one evidence format, both pin their model by name.

That symmetry stops at the review gate. **In-session delegation — one agent asking another
for work without leaving its own session — is not equally available in both directions**, and
it is not something the kit can fix. This page records what is actually there, so nobody
plans around a capability that does not exist.

## What each direction can do

| | Claude Code as host | Codex as host |
|---|---|---|
| Run the review gate on the other model | yes — `./scripts/review.sh --reviewer codex` | yes — `./scripts/review.sh --reviewer claude` |
| Same evidence format, same verdict contract | yes | yes |
| In-session delegation, shipped by the kit | **no** | yes — the Codex plugin's `myagentkit-review` and `myagentkit-delegate` skills |
| In-session delegation, from the vendor | via the OPTIONAL `openai/codex-plugin-cc` plugin | not applicable |
| Ask the other model to PROPOSE a patch | only by running `claude_bridge.py propose` as a command | yes — `myagentkit-delegate` |

Read the middle rows together. Both hosts can *review* through the same script; that is the
part the kit guarantees and the part the gate depends on. What differs is how conversational
the request is allowed to be.

**From Codex, the kit ships the delegation itself.** `plugins/myagentkit` installs two Codex
skills that call the Claude adapter directly, so "ask Claude to review this and fix what it
confirms" is a sentence in the session rather than a command line. `docs/CODEX.md` covers
installation and the authorization rules.

**From Claude Code, the kit ships no equivalent.** `/myagentkit:cross-review` is a command
that runs the review script; it is not Claude delegating a task to Codex in conversation.
The nearest thing is a vendor plugin the kit neither ships nor requires, and it is optional
precisely because the gate does not depend on it.

## Why the kit does not close the gap

Because closing it would mean writing an adapter for an interface the other vendor owns and
changes. The kit already carries two, and each one cost a live validation run to trust. A
third path — a conversational Claude-to-Codex delegation with its own failure modes, its own
budget accounting and its own evidence — would be a third thing to keep honest, in exchange
for convenience the script already provides less prettily.

The asymmetry is also smaller than it looks. Delegation is a convenience; the REVIEW is the
rule, and the review runs identically from both sides.

## The overlay asymmetry, and why there is no `codex` overlay

`overlays/claude-code/` exists. There is deliberately no `overlays/codex/`, and the reason is
worth stating rather than leaving as an apparent gap:

- **The canonical-file pointer is not needed.** The overlay's `CLAUDE.md` is a one-line
  pointer to `AGENTS.md` because Claude Code does not read `AGENTS.md` natively. Codex does.
  Codex is a large part of *why* `AGENTS.md` is the canonical file
  ([one-canonical-instruction-file](one-canonical-instruction-file.md)). An `overlays/codex/`
  holding a pointer would be a copy of the canonical file's name pointing at itself — the
  exact duplication that page forbids. **Already consistent; nothing added.**
- **The hooks are not portable, and were not invented.** The rest of the Claude Code overlay
  is hook scripts and a subagent definition in Claude Code's own config format. Codex has a
  hook mechanism — the CLI carries a trust flag for it — but this kit has not verified its
  event names or its configuration schema, and an overlay written from an inferred schema
  would ship a gate that silently never fires. That is the fail-open shape the kit exists to
  prevent, so nothing was written. **Genuine gap, deliberately left open and labelled.**

Nothing in the overlay is load-bearing in either case: `.githooks/pre-commit` and
`scripts/check.sh` are the enforcement, they are tool-agnostic, and they run under both hosts.
A Codex-hosted project is missing early feedback, not a gate.

## What was verified, and when

Checked on 2026-09-05 on one machine, with Codex CLI and Claude Code 2.1.261 installed:

- Both review directions completed live against the same commit and produced reports with an
  identical header field list and exactly one verdict line each.
- `codex exec --json` emits no model identity in its output. That is why a Codex review
  records its model as a requested pin and says so, while Claude's is matched against the
  CLI's own `modelUsage` and recorded as attested. Both are pinned; only one is attestable.
- NOT verified: Codex's hook event names and schema, and the availability of
  `openai/codex-plugin-cc`. Neither claim is relied on above.

## The failure mode it prevents

Planning a workflow around a delegation path that does not exist — and discovering it at the
moment the budget forced the roles to swap, which is the worst possible time to find out that
"the other direction works too" was only ever true of the review script.
