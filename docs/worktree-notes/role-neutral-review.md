# Role-neutral review gate — state for the morning

Written by Claude Opus 5 on 2026-09-05. Baseline commit c358c917. Committed, NOT pushed,
as the owner asked.

## THIS WORK HAS NOT BEEN INDEPENDENTLY REVIEWED

I wrote it, so I cannot review it. `docs/REVIEW_GATE.md` calls almost all of it a risky
diff: it is gate code, review tooling and the check script. **Astra reviews it in the
morning, before any push.**

Run it from this checkout as:

```sh
./scripts/review.sh --commit HEAD --reviewer codex
```

## A complication worth reading before that review

The tree I started from already carried uncommitted work by Codex / GPT-6 Astra — the
Claude adapter, the Codex plugin, usage accounting — and `docs/worktree-notes/codex-claude-
bridge.md` records that this work was **awaiting a Claude review that never completed**
(the first attempt hit its 600-second limit with no output).

I was, in principle, the independent reviewer that note was waiting for. I am no longer:
I have edited that same code — the shared evidence renderer, both adapters, the wrapper and
the test file — so I am now a co-author of it, not an independent party.

**The practical consequence:** the pending Claude review of Codex's work is not merely still
pending, it is no longer obtainable from this session. Codex's work and mine are now one
diff, and one reviewer covers both — which has to be Astra, and which means Astra is partly
reviewing its own earlier work. That is a real weakening of the invariant. If it matters
enough, the honest fix is a third model on the combined diff; a fresh Claude session with no
memory of writing this would also be more independent than I am, though less so than a
different model. Owner's call.

## What changed

1. **`--reviewer codex|claude`** on `scripts/review.sh`. The default and both model pins are
   project-owned settings at the top of the script, filled during setup.
2. **One evidence format in both directions** — same header table, one `VERDICT:` line,
   `docs/reviews/<stamp>-<reviewer>-review.md`. Enforced by `agent_usage.report()`, which
   refuses a drifted header and refuses a verdict for a run that did not complete.
3. **Both models pinned by name**, wrapper refuses to run unpinned. Claude's pin is attested
   against `modelUsage`; Codex publishes no model identity, and the record says so.
4. **AUTHOR/REVIEWER as roles** in AGENTS.md, WORKFLOW.md, REVIEW_GATE.md; the interview now
   asks author, reviewer and scarce budget as three separate questions.
5. **`docs/delegation-is-not-symmetric.md`** — what in-session delegation exists in each
   direction, and why there is no `overlays/codex/`.

## Assumptions left standing

- `CODEX_MODEL` and `CLAUDE_MODEL` ship EMPTY in the template. Existing installs will stop
  with a clear message until setup fills them. That is deliberate and marked **ACTION** in
  the changelog, but it IS a breaking change for anyone who syncs — worth a second opinion
  on whether failing closed is right here.
- The kit's own `scripts/review.sh` pins `gpt-6-astra` and `claude-opus-5`. Both were live
  today. Neither is checked for continued existence.
- Reports written before today keep their old names. Nothing migrates them.
- Issues #4 and #5 look addressed by the evidence-ordering and one-verdict work now in this
  diff, but I did not verify them line by line against the issue text and did not close
  them. Issue #3 (marketplace name) is untouched.
- The pre-commit gate validates the working tree rather than the committed tree. Known,
  out of scope, untouched, still in RESEARCH_LOG.
