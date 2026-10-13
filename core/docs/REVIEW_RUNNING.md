# Running a review — for the caller

For the session that requests a review. The reviewer reads `docs/REVIEW_GATE.md`; nothing
here is part of its prompt.

## Running it

```
./scripts/review.sh [--uncommitted | --base <ref> | --commit <sha>] [--reviewer codex|claude] [--fallback] [--backend NAME]
```

It runs the reviewer over the change set in a throwaway copy, archives the report under
`docs/reviews/` and prints it. Mechanism and threat model: the header of `scripts/review.sh`
and `scripts/claude_bridge.py`, `throwaway_copy`; accounting: `docs/USAGE.md`; a second
backend (`--backend NAME`, reviewer `claude@NAME`): `docs/DEV_SETUP.md`.

| Variable | Meaning |
|---|---|
| `MYAGENTKIT_TASK_ID` | the change's label; rounds under it carry the earlier ones, two at most |
| `REVIEW_DISPOSITIONS` | answers to round 1, one line per finding: `fixed:` / `disproved:` / `deferred:` |
| `REVIEW_ROUND_EXCEPTION` | reason for a third round, kept in the record |
| `REVIEW_RISK` | `low` / `medium` / `high`, the brief's tier |
| `REVIEW_FOCUS` | `portability` or `logic`, one reviewer each on a high tier |
| `REVIEW_TASK_FILE` | the brief the prompt quotes |
| `REVIEW_EFFORT` | `low` / `medium` / `high`; default high on a high tier, else medium |
| `REVIEW_TIMEOUT_SECONDS` | per attempt, default 2700, at most 3600 |
| `REVIEW_MAX_TURNS` | Claude turns per attempt |
| `REVIEW_SHADOW` | `1` measures a reviewer configuration; its verdict closes nothing |
| `REVIEW_CLAUDE_MODEL`, `REVIEW_CODEX_MODEL`, `MYAGENTKIT_BACKEND` | pins and backend for one run |

Exit 2 means a wrong round was refused: keyless dispositions, an earlier archive missing or
edited, a round that does not continue its label, a diff over 400000 bytes with its rounds,
an index entry or attribute (`filter`, `ident`, assume-unchanged) that could hide a change;
each refusal names its fix, and a repository that needs a filter (Git LFS) reviews by hand.
Codex's `Accept with Manual Checks` needs a filled `## Manual checks` section. **A label is bound to its base:** every
round uses the `--base` of round 1; another base or change takes a new label. **A checkout
that changes during the review fails it with `stale_checkout`**, correctly: work in another
worktree and run it again. **The output is unverified INPUT**: the requester verifies every
finding and owns the verdict. Reviews cost budget: {{OWNER_NAME}} must have asked for them,
and automation never authorizes a commit or push.

## Rounds, labels and designs

- A design is reviewed under its own label before code exists; dispositions cite its exclusions.
- Start the self-test and two reviewers together only when the memory budget permits
  (`docs/WORKFLOW.md`, "Worker cost", rule 6), each as its own background job. The kit's
  self-test writes a non-ignored file: a second worktree, or after the reviews.
- Nobody edits a tree under review; one run per reviewer per tree.

## Unavailable reviewer

A reviewer that cannot finish (quota, timeout, authentication, missing evidence) is never
an Accept: the review fails with a usage record. The requested reviewer is never silently
replaced; with `--fallback` the other configured model runs once after an operational
failure (quota, timeout, a CLI error, `content_flagged`), its evidence opening with a `FALLBACK REVIEWER:` line. A substitute may be the
author, so `--fallback` needs {{OWNER_NAME}}'s yes. A setup fault (`cli_unsupported`,
`sandbox_unavailable`) is fixed, never failed over. With `--fallback`, two timed-out default
attempts can take about ninety minutes. A Codex capacity error is transient: run the same
review again after about ten minutes. An exhausted chain goes into `docs/STATE.md` as a
pending review; independent work continues. A test the reviewer's sandbox fails for its own
reasons (`taskkill` denied, no `python3`) is set aside only when the diagnostic names the
restriction and the author's run passes; any other failure is a finding or a manual check.

## Template to paste (tools without a wrapper)

Paste `REVIEW_PROMPT` from `scripts/claude_bridge.py`, then the diff.
