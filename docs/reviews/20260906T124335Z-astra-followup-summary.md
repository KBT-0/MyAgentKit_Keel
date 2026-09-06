# Issue follow-up review — 2026-09-06

Scope: the combined delta from `c358c917` to `4c40c5b`. The owner authorized
repairs, individual issue closure, commits and pushes with Claude review pending.

The requested pinned Claude review failed with HTTP 403 because the organization
has disabled subscription access for Claude Code. It produced no verdict, no model
usage attestation and no token usage. Authentication was not changed and the failed
provider was not retried. The automatic configured fallback requested `gpt-6-astra`
with high effort and the standard 1800-second deadline, returning **Reject**.
Neither co-author's review establishes independent approval of the combined change.

## Verified findings and repairs

1. **Confirmed, P1:** Git text conversion and external diff drivers could hide source
   changes and preserve the old fingerprint. Collection now disables both drivers,
   and fingerprints include readable source bytes independently of Git index flags.
2. **Confirmed, P2:** direct adapters missed movement of the selected base reference.
   The fingerprint now includes the resolved reference and collected review diff.
3. **Confirmed, P2:** Codex accepted manual-check verdicts without actionable checks.
   Validation now requires the explicit manual-check section and rejects empty and
   placeholder-only sections.
4. **Confirmed, P2:** merge commits appeared empty. Commit scope now compares HEAD
   against its first parent, retaining merge conflict resolutions in the review.

All four regressions failed on the previous runtime and passed after these fixes.
The full `./scripts/check.sh --self-test` passed with 57 runtime tests, six kit
tests, and installed core negative gates. The second, final review remains pending.

## Local diagnostic references

Raw reports and CLI output remain ignored and local; no transcript is published here.
Claude: `20260906T124331Z-ee4018030205-claude-review.md`, usage
`20260906T124334Z-5db5c2313630.json`. Astra:
`20260906T124335Z-bf36fc107452-codex-review.md`, usage
`20260906T124657Z-f688dcb5ca71.json`. Chain:
`8e4f11600726462083558f04677cc237-2.json`.

## Outstanding checks

The owner-requested Claude review and live proposal/permission probes require restored
Claude access. Linux/macOS and Python validation, plugin reinstallation and discovery,
and the isolated existing-project upgrade will be recorded separately after execution.

The blocked Claude-specific work is tracked in [issue #6](https://github.com/KBT-0/MyAgentKit_Keel/issues/6).
