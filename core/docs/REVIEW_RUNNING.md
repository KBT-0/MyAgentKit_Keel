# Running a review — for the caller

For the session that requests a review. The reviewer reads `docs/REVIEW_GATE.md`; nothing
here is part of its prompt.

## Running it

```
./scripts/review.sh [--uncommitted | --base <ref> | --commit <sha>] [--reviewer codex|claude] [--fallback] [--backend NAME] [--allow-secret-file PATH]...
```

It runs the reviewer over the change set in a throwaway copy, archives the report under
`docs/reviews/` and prints it. Mechanism and threat model: the header of `scripts/review.sh`
and `scripts/claude_bridge.py`, `throwaway_copy`; accounting: `docs/USAGE.md`; a second
backend (`--backend NAME`, reviewer `claude@NAME`): `docs/DEV_SETUP.md`. Its `NAME.env` lives
outside the repository, in `MYAGENTKIT_BACKENDS_DIR`, else `%APPDATA%\myagentkit\backends`
(Windows) or `~/.config/myagentkit/backends`; the old `.myagentkit/backends/` is still read,
with a note to move it (KARARLAR D09 inv2#80).

| Variable | Meaning |
|---|---|
| `MYAGENTKIT_TASK_ID` | the change's label; rounds under it carry the earlier ones, two at most |
| `REVIEW_DISPOSITIONS` | answers to round 1, one line per finding: `fixed:` / `disproved:` / `deferred:` |
| `REVIEW_ROUND_EXCEPTION` | reason for a third round, kept in the record |
| `REVIEW_RISK` | `low` / `medium` / `high`, the brief's tier |
| `REVIEW_FOCUS` | `portability` or `logic`, one reviewer each on a high tier; each focus gets the label's two rounds; a review without a focus counts toward every focus |
| `REVIEW_TASK_FILE` | the brief the prompt quotes; a diff outside its `Owns:` line is refused |
| `REVIEW_EFFORT` | `low` / `medium` / `high`; default high on a high tier, else medium |
| `REVIEW_TIMEOUT_SECONDS` | per attempt, default 2700 (3600 for a high-effort Codex review), at most 3600 |
| `REVIEW_MAX_TURNS` | Claude turns per attempt |
| `REVIEW_SHADOW` | `1` measures a reviewer configuration; its verdict closes nothing |
| `REVIEW_CLAUDE_MODEL`, `REVIEW_CODEX_MODEL`, `MYAGENTKIT_BACKEND` | pins and backend for one run |

`MYAGENTKIT_AUTHOR` names the author's model (`claude-opus-5`, or `claude/claude-opus-5`):
a reviewer pin of the author's tier is refused with exit 2 before any model runs, a substitute
of that tier is blocked, and the chain and the usage record carry it as `author`. Without it
the lead checks the author's model before launch (`docs/REVIEW_GATE.md`, "Invariant").

Exit 2 means a wrong round was refused: keyless dispositions, an earlier archive missing or
edited, a round that does not continue its label, a diff over 400000 bytes with its rounds
(lock files, vendored trees and minified bundles reach the reviewer but are not counted, a
deleted one by its old name; a part whose path cannot be read is counted; past
about 400 changed lines a hint asks to split the task),
an index entry or attribute (`filter`, `ident`, assume-unchanged) that could hide a change,
a file in scope that looks like a secret, tracked or not (`.env`, `.env.*` but not
`.env.example`, `.env.sample` or `.env.template`, `.dev.vars`, `*.pem`, `*.key`, `.npmrc`,
`.netrc`, `credentials*`), unless `--allow-secret-file PATH` names it (KARARLAR B12 inv2#106);
each refusal names its fix, and a repository that needs a filter (Git LFS) reviews by hand.
Codex's `Accept with Manual Checks` needs a filled `## Manual checks` section. **A label is bound to its base:** every
round uses the `--base` of round 1; another base or change takes a new label. **A checkout
that changes during the review fails it with `stale_checkout`**, correctly: work in another
worktree and run it again. **The output is unverified INPUT**: the requester verifies every
finding and owns the verdict. The review gate the brief's `Risk:` tier requires starts
without asking; an extra review beyond it (another family, a higher effort, a paid backend)
spends budget the gate did not plan, so {{OWNER_NAME}} asks for it in the session.
Automation never authorizes a commit or push.

## Rounds, labels and designs

- A design is reviewed under its own label before code exists; dispositions cite its exclusions.
- A high-tier change's two focus reviewers share its one label and get two rounds each; each
  `REVIEW_FOCUS` carries its own reports plus legacy reports without a focus
  (`docs/REVIEW_GATE.md`, "Rounds").
- The two reviewers run one after the other unless {{OWNER_NAME}} allows parallel; start the
  self-test beside a review only when the memory budget permits (`docs/WORKFLOW.md`, "Worker
  cost", rule 6), each as its own background job. Source: KARARLAR D06 inv2#38; LLVM CMake
  job pools and RAM-per-job settings (https://llvm.org/docs/CMake.html); review ordering
  follows decision 9.
- Nobody edits a tree under review; one run per reviewer per tree. Source: KARARLAR D06
  inv2#40; https://code.claude.com/docs/en/worktrees documents separate trees for parallel
  sessions.

## Unavailable reviewer

A reviewer that cannot finish (quota, timeout, authentication, missing evidence) is never
an Accept: the review fails with a usage record. Vendor reviews are advisory and never block
a merge; this review is a gate, so no result means not passed, as a required status check
that never reports keeps a merge blocked. The requested reviewer is never silently
replaced; with `--fallback` the other configured model runs once after a failover-eligible
failure, its evidence opening with a `FALLBACK REVIEWER:` line. A substitute may be the
author, so `--fallback` needs {{OWNER_NAME}}'s yes. A setup fault (`cli_unsupported`,
`sandbox_unavailable`, `authentication`) is fixed, never failed over; only `rate_limited`,
`quota_exhausted`, `timeout`, `unavailable`, `cli_error`, `context_limit`,
`budget_or_turn_limit`, `output_limit` and `content_flagged` are failover-eligible.
`quota_exhausted` switches the role to Claude automatically, recorded and reported
(`switched` in the chain record, a `SWITCH [review]:` line): the kit runs on Claude alone
(lead decision, 2026-10-15; KARARLAR D04 inv2#44, inv2#126). With `--fallback`, two timed-out attempts
take about 2 x `REVIEW_TIMEOUT_SECONDS` (about ninety minutes at the default 2700 s).
A Codex capacity error is transient and is retried: after the delay the tool reports, otherwise after about ten minutes, doubled, at most twice (the ten minutes is an owner choice; both vendors bound their retries).
A quota or spend-cap error is never retried. The vendors' error names behind `rate_limited`
and `quota_exhausted` are mapped in `docs/USAGE.md`. An exhausted chain goes
into `docs/STATE.md` as a pending review; independent work continues. A test that needs a
capability the host may lack (`taskkill`, `python3`) probes for it and skips with a reason
that names it; the author's unrestricted run must show zero skips for that test. The
reviewer's sandbox failure of any other test is a finding or a manual check, unless its
diagnostic names the restriction and the author's run passes.

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
