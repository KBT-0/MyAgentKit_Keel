<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->

# REVIEW_RUNNING — the kit's part

The kit's generic rules of `docs/REVIEW_RUNNING.md`, under its headings. The project's file
keeps its placeholders, its owner's decisions and its own rules, and each heading there whose
text moved ends with a "Kit rules:" line naming the heading here. This file is the kit's, and a
sync replaces it. Generic rules live here by the owner's decision of 2026-10-22 (docsowned
question 1, #94); the rule that a kit-owned file holds only reasons
(`docs/WORKFLOW_RATIONALE.md`) is `docs/WORKFLOW.md`'s alone. Do not edit it: a project that
needs a different rule writes it in `docs/REVIEW_RUNNING.md`, the project-owned file, and the
project file wins over this one.

## Kit upgrade commits

A sync's upgrade commit is usually too big for one review (#114). After committing it, run the
line `sync-kit.sh` prints: `./scripts/review.sh --reviewer claude --commit <upgrade commit>
--kit-verified --kit '<kit>' --kit-commit <sha>` (`--kit` defaults to `~/.myagentkit/kit`;
Claude reviewer only). An upgrade of several commits takes `--base <ref>` in place of
`--commit`. **Verified by hash, not reviewed:** a changed file with the `KIT-OWNED` header, with
the kit's mode and no mode change, that is equal to the kit's file after git's line-ending
normalisation (`hash-object --path` in the kit clone) at the kit commit: `--kit-commit`'s full
id, the one the sync copied, else the one `docs/kit/.kit-commit` records in the reviewed commit.
`--kit-commit` is what lets an upgrade be reviewed while its ACTION items are pending: the sync
writes `.kit-commit` only with the version, so not while an ACTION item is pending (#305). That kit commit
must be on a release tag `v*` of the kit clone and descend from the one the diff's start (the
parent, or the merge base for `--base`) records and the one the reviewed commit records (no
downgrade). **Reviewed:** everything else, the project-owned files and merges and every
kit-owned file the project edited. No kit commit, a kit clone without it, an untagged kit
commit, a downgrade, a differing file or mode, or a changed path below a kit file's path
verifies nothing for it, and it stays in the diff. Line-ending churn is checked over every changed file, the
verified ones too. The verified list (path, blob, kit commit) is in the review evidence and the
chain record. A commit that is not HEAD is reviewed from an archive of it ("past mode"); a
`--commit HEAD` still needs a clean checkout. Limits: `BEHAVIOUR.md` is read from the working
tree, so an appendix edited since the commit fails the review (`unsafe_behaviour_appendix` or
`stale_checkout`); review the upgrade before editing it. Accepted: a past commit's review
fingerprints that commit only, decided once when the review starts, so an edit to the working
tree or a checkout during it does not fail it.

## Template to paste (tools without a wrapper)

Run the reviewer in a throwaway copy of the checkout, never in the checkout itself. Paste
`REVIEW_PROMPT` from `scripts/claude_bridge.py` with its `%s` replaced by `AGENTS.md,
docs/ARCHITECTURE.md and docs/REVIEW_GATE.md`, then `REVIEW_RUNS` from the same file, then
this, then the diff:

```text
Write exactly one line: VERDICT: Accept / VERDICT: Accept with Manual Checks / VERDICT: Reject.
Put the findings under a '## Findings' heading, one '- ' list item per finding that starts
with its severity, and the manual checks under a '## Manual checks' heading.
```
