# Running a review — for the caller

For the session that requests a review. The reviewer reads `docs/REVIEW_GATE.md`; nothing
here is part of its prompt.

## Running it

```
./scripts/review.sh [--uncommitted | --base <ref> | --commit <sha>] [--reviewer codex|claude] [--fallback] [--backend NAME] [--allow-secret-file PATH]...
```

It runs the reviewer over the change set in a throwaway copy, archives the report under
`docs/reviews/` and prints it. In the background, run `review.sh` itself as the background command,
so its exit is the done signal (`docs/WORKFLOW.md`, "Worker cost", rule 4). A run started
detached (`nohup ... > LOG 2>&1 &`) is waited on through its log, never a pid, which a Windows
host's Git Bash cannot check: `until grep -q -e '^review dispatch: ' -e '^FAIL \[review\]: '
-e '^usage: ' -e '^Traceback ' LOG; do sleep 30; done` ends on the dispatcher's last line or a
refused or crashed run's own line. Mechanism and threat model: the header of `scripts/review.sh`
and `scripts/claude_bridge.py`, `throwaway_copy`; accounting: `docs/USAGE.md`; a second
backend (`--backend NAME`, reviewer `claude@NAME`): `docs/DEV_SETUP.md`. Its `NAME.env` lives
outside the repository, in `MYAGENTKIT_BACKENDS_DIR`, else `%APPDATA%\myagentkit\backends`
(Windows) or `~/.config/myagentkit/backends`; the old `.myagentkit/backends/` is still read,
with a note to move it (KARARLAR D09 inv2#80).

| Variable | Meaning |
|---|---|
| `MYAGENTKIT_TASK_ID` | the change's label; rounds under it carry the earlier ones, two at most (a review its dispatcher failed afterwards is carried but not counted: `docs/REVIEW_GATE.md`, "Rounds") |
| `REVIEW_DISPOSITIONS` | answers to every earlier round (round 1 by default), one line per finding: `fixed:` / `disproved:` / `deferred:` |
| `REVIEW_ROUND_EXCEPTION` | reason for a third round, kept in the record |
| `REVIEW_SAME_TIER_EXCEPTION` | reason the author's tier reviews a high-tier change on a plan with no tier above it (`REVIEW_RISK=high`, effort high), kept in the record; one round per label and focus (a round without a focus uses it for every focus), so a second round under it is refused, a substitute's included and `REVIEW_ROUND_EXCEPTION` notwithstanding (`docs/WORKFLOW.md`, "Model routing", rule 7) |
| `REVIEW_RISK` | `low` / `medium` / `high`, the brief's tier |
| `REVIEW_FOCUS` | `portability` or `logic`, one reviewer each on a high tier; each focus gets the label's two rounds; a review without a focus counts toward every focus |
| `REVIEW_TASK_FILE` | the brief the prompt quotes; a diff outside its `Owns:` line is refused. The brief may live in any checkout: the diff is the reviewed one's, the checkout `review.sh` runs in when that is a worktree of the script's repository (#302) |
| `REVIEW_EFFORT` | `low` / `medium` / `high`; default high on a high tier, else medium |
| `REVIEW_TIMEOUT_SECONDS` | per attempt, default 2700 (3600 for a high-effort Codex review), at most 3600 |
| `REVIEW_MAX_TURNS` | Claude turns per attempt |
| `REVIEW_SHADOW` | `1` measures a reviewer configuration, or runs a weaker tier's extra opinion; its verdict closes nothing |
| `REVIEW_CLAUDE_MODEL`, `REVIEW_CODEX_MODEL`, `MYAGENTKIT_BACKEND` | pins and backend for one run |

`MYAGENTKIT_AUTHOR` names the author's model (`claude-opus-5`, or `claude/claude-opus-5`):
a reviewer pin of the author's tier is refused with exit 2 before any model runs, and so is a
weaker tier of the author's family, whose review runs only as an extra opinion
(`REVIEW_SHADOW=1`); a substitute of either is blocked, and the chain and the usage record
carry it as `author`. With it `MYAGENTKIT_AUTHOR_EFFORT` names the author's effort, high when
unset; a review with no effort named runs at it (high at most), and one named below it is
refused (the effort rule is `docs/REVIEW_GATE.md`, "Invariant"); a shadow run closes nothing
and is not checked. When the author is its family's top tier and its
own tier reviews, the chain records the pair as `top_tier_review` and the usage record as
`author_effort`. Without `MYAGENTKIT_AUTHOR` the lead checks the author's model before launch
(`docs/REVIEW_GATE.md`, "Invariant").

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
round uses the `--base` of round 1, except that round 2 over the fix commits may take round 1's
head (or a commit above it on HEAD's line) as its `--base` and still counts as round 2. A
`--commit` or `--uncommitted` label continues the same way once HEAD is round 1's head or above
it (round 2 is the `--commit` of the fix commit); another base or change, a rebase or an amend
takes a new label. **A checkout
that changes during the review fails it with `stale_checkout`**, correctly, and that review is
no round: work in another worktree and run it again. The review looks at the checkout once a
minute and stops the reviewer at the first change it sees. A checkout that cannot be read after the
review fails it with `checkout_unverified`, and that completed review still counts as a round. **The output is unverified INPUT**: the requester verifies every
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
  acceptance gate run beside a review only when the memory budget permits (`docs/WORKFLOW.md`, "Worker
  cost", rule 6), each as its own background job. Source: KARARLAR D06 inv2#38; LLVM CMake
  job pools and RAM-per-job settings (https://llvm.org/docs/CMake.html); review ordering
  follows decision 9.
- A `review.sh` round a worker runs inside its own worktree reviews that worktree's diff and is
  recorded in the main checkout: its usage record and chain file in `.myagentkit/usage/`, its
  archive in `docs/reviews/`. The usage record's `task.tree` and the chain's `tree` name the
  tree the round read. The worker's report lists the round (`docs/WORKFLOW.md`, "Review inside
  the worker"). After the merge, the lead continues the worker's label in the main checkout
  with `--commit <merge or fix commit>`. That round continues an `--uncommitted` round when
  every file the earlier round reviewed is in the commit's diff (a moved file by its old and its
  new name) and the earlier HEAD is the commit's ancestor on HEAD's line; the chain records the
  step, from the newest such round, as `continues`. Both rounds count toward the label's two.
  Otherwise the round is refused, and the message names the files the commit lacks or the
  earlier HEAD it does not descend from. Nothing is copied between checkouts (#293). A record
  written before v0.13 inside a worktree that is removed since is read from a copy of its
  archive with the same name in the main checkout's `docs/reviews/` or `.myagentkit/usage/`;
  one line names the copy. `agent_usage.py` and `usage_summary.py` read the main checkout's
  records too when `--repo` names a linked worktree, and find such a copy.
- Nobody edits a tree under review; one run per reviewer per tree. Source: KARARLAR D06
  inv2#40; https://code.claude.com/docs/en/worktrees documents separate trees for parallel
  sessions.

## Kit upgrade commits

A project that needs a different rule writes it here, and this file wins over `docs/REVIEW_RUNNING_KIT.md`.
Kit rules: docs/REVIEW_RUNNING_KIT.md, "Kit upgrade commits".

## Unavailable reviewer

When Codex cannot review critical or high-tier work (its content classifier stopped it,
`content_flagged`), the strongest Claude tier the plan has reviews it in a fresh session,
at high effort, one round, never the author's session (`docs/WORKFLOW.md`, "Model routing", rule 7).

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

Kit rules: docs/REVIEW_RUNNING_KIT.md, "Template to paste (tools without a wrapper)".
