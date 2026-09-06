# Codex-host Claude bridge — continuation pointer

Updated by Codex / GPT-6 Astra on 2026-09-05. The initial bridge and subsequent role-neutral
changes are combined in local commit 7882a5a60e14bcce98c37275bcfbdc988cca96bf.

Current review and repair state is maintained in
[role-neutral-review.md](role-neutral-review.md). The owner now authorizes push after the five
confirmed repairs, with a fresh Claude review explicitly pending. Both Astra and Opus
have authored parts of the combined implementation; the current note records that context
and the scope of the requested follow-up review.

The user's policy remains: reviews have no default monetary cap; usage and timeout
accounting remain enabled. Commit authorship belongs to the owner, without AI trailers.
The installed Codex plugin has not been refreshed by this documentation task. A successful
live proposal smoke test and discovery in a new host conversation remain unverified.
Historical evidence and its limitations are recorded in docs/ACCEPTANCE.md.
