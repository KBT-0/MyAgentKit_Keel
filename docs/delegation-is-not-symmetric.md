# Review delegation is symmetric; proposal support is not

The kit names AUTHOR and REVIEWER as roles, not vendors. Both hosts can start an external
reviewer from their own session, read its result, and verify the findings. A command that
calls a script and a skill that calls a script are both host-managed delegation; neither
becomes a persistent background coordinator merely because its entry point has a different
name.

## What the kit ships

| Capability | Claude Code as host | Codex as host |
|---|---|---|
| Delegate a review to the other tool | `/myagentkit:cross-review --reviewer codex` | `myagentkit-review`, or `./scripts/review.sh --reviewer claude` |
| Read the result in the requesting session | The command runs the wrapper and instructs the host to verify findings | The skill runs the adapter and instructs the host to verify findings |
| Guided implementation and fresh re-review | The command requires fresh review of fixes; implementation needs separate authorization | The review skill includes an authorized, bounded repair loop |
| Request a structured implementation proposal from the other tool | No Codex proposal adapter is currently shipped | `myagentkit-delegate` calls Claude's `propose` mode |

The actual gap is a shipped Codex proposal interface and equivalent host guidance, not an
inability of Claude Code to launch Codex. `claude_bridge.py propose` always calls Claude;
running it from Claude Code does not turn it into a Claude-to-Codex proposal path.
`codex_bridge.py` currently collects reviews, not structured implementation proposals.

The Codex plugin's skills and the Claude plugin's command are different discovery surfaces.
Their underlying work is an external CLI invocation with bounded execution and local
evidence/accounting. The author remains responsible for scope, authorization, verifying
findings, and any permitted edits. Review-only authorization does not authorize repairs.

An optional vendor integration is not required to delegate a review through this kit.
Additional proposal support could be implemented using a deliberately scoped adapter and
tests; it is not a platform impossibility. No such implementation is claimed by this change.

## Why there is no Codex overlay

The absence of `overlays/codex/` is separate from review delegation:

- Codex reads the canonical `AGENTS.md`; adding a same-name pointer is unnecessary.
  The Claude overlay's `CLAUDE.md` points to that canonical file.
- The existing Claude overlay contains tool-specific hooks and agent configuration.
  Equivalent Codex hook events and configuration were not validated by this work, so no
  hook overlay was implemented or claimed to work.

The shared checks and Git hooks remain independent of either overlay. A Git hook is active
only when it is actually installed and configured in that checkout. Optional tool hooks are
early feedback, not a substitute for the review gate or proof that a commit was reviewed.

## Evidence and limits

The dated live integration runs in `docs/ACCEPTANCE.md` used one small synthetic diff.
They demonstrate that both call paths completed and produced comparable report headers.
They do not establish that the combined kit change was independently reviewed, that either
model reliably detects every seeded defect, or that differing verdicts imply review quality.

The Codex adapter records a requested model pin without claiming model identity attestation.
The Claude adapter additionally checks the CLI's `modelUsage`. This distinction describes
adapter evidence, not an independent verification of the serving infrastructure.

Hook schemas and optional vendor-plugin availability remain outside this implementation's
verified surface. Do not infer a working integration from their mention in historical notes.
