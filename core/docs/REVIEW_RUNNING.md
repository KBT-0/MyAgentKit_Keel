# Running a review — for the caller

This file is for the session that requests a review: the AUTHOR or the lead. The reviewer
reads `docs/REVIEW_GATE.md`, which holds the contract, the priorities and the verdicts;
nothing in this file is part of its prompt.

## Running it

```
./scripts/review.sh [--uncommitted | --base <ref> | --commit <sha>] [--reviewer codex|claude] [--fallback]
```

It collects the change set with git, hands it to a read-only REVIEWER carrying the
priority order of `docs/REVIEW_GATE.md`, archives the report as evidence under
`docs/reviews/<UTC-timestamp>-<random>-<reviewer>-review.md` and prints it. Omitting
`--reviewer` uses the one configured during setup at the top of `scripts/review.sh`.

Diff collection disables Git text conversion and external diff commands so repository
configuration cannot replace source with a filtered rendering. The checkout fingerprint
also hashes readable source bytes independently of Git's change detection and binds the
resolved reference and collected diff. A moving base reference invalidates an in-flight
review. Commit scope uses the delta against the first parent, including merge commits.
Scopes containing assume-unchanged or skip-worktree index entries are rejected before
launch; clear those flags and use a complete checkout so Git can expose every source change.
Paths with an effective Git clean filter (a `filter` attribute whose driver has a `clean` or
`process` command) or the `ident` attribute are rejected the same way: Git converts
working-tree bytes before diffing them, so a filter could drop a file or single lines from
the reviewer's payload while the fingerprint still hashed the raw bytes. No Git flag turns
that conversion off for diff. A repository that relies on a filter (Git LFS included) reviews
by hand with the template below, or removes the attribute for the review.
Codex manual-check verdicts require a nonempty `## Manual checks` section describing the
remaining checks; an absent section or a placeholder such as `None` is invalid evidence.
The verdict declaration itself never counts as a manual check.

**The two directions are interchangeable, not merely both present.** Each archives the same
header table — reviewer, model, whether the model is attested, effort, sandbox, limits,
scope, reference, HEAD, checkout fingerprint, diff hash, status, failure kind — followed by
exactly one `VERDICT:` line, or none at all when the run failed. The renderer refuses a
header that has drifted, and refuses to print a verdict for a run that did not complete, so
"same format" is enforced rather than agreed.

**Both models are pinned by name, in both directions.** An unpinned run archives whatever
default the CLI happened to have that week, which no later record can be compared against;
the wrapper stops rather than record it. Claude's model is additionally ATTESTED — the
adapter matches the pin against the CLI's own `modelUsage` — while Codex publishes no model
identity in its output, so its record says the pin is requested but unattested. The
evidence says which of the two it is instead of implying a check that did not happen.

The script accepts no flags beyond those above: the reviewer is matched against a closed
list and arbitrary user flags are not passed through to the underlying CLI. Both adapters
require Python 3.10+ and do not resume an author session. Claude restricts source tools to
Read/Glob/Grep and disables customizations and MCP. Codex requests its read-only sandbox
and never-approve policy; it does not implement Claude's tool allowlist or customization
isolation. A shared evidence format does not imply identical permission mechanisms.

**Neither adapter can execute yet, although both prompts ask the reviewer to.** The prompt
asks for runs in a throwaway copy (`docs/REVIEW_GATE.md`, "The reviewer executes, in a
throwaway copy"). Claude's review tools are Read, Glob and Grep, so it runs nothing; adding
Bash to `--tools` with an allow rule (`dontAsk` refuses unapproved tools) would change that.
Codex runs commands in its `-s read-only` sandbox, but nothing can write, so `mktemp -d`
fails and no copy or suite can run. `-s workspace-write` allows writes to the workspace and
the temporary directory and still refuses network access. A write into the reviewed checkout
then fails the review as `stale_checkout`. Widening either adapter is an owner decision.
Until then, these reviewers mark findings REASONED and list the runs as NOT RUN with that
reason. The Claude Code overlay's `diff-reviewer` sub-agent has Bash and executes.
Reference reviews require matching clean checkout context. Both share scope collection and
checkout fingerprint validation, so a change while the reviewer runs invalidates its
result, and evidence is published exclusively before usage can say completed.

**Every round asks for the whole list, and a later round sees the earlier ones.** Both
adapters ask for every finding the pass can establish (`docs/REVIEW_GATE.md`, "Findings,
earlier rounds and dispositions"). When `MYAGENTKIT_TASK_ID` names the same task label as
earlier completed reviews, the prompt carries those reviews oldest first, exactly as archived
(their verdict lines rewritten as `Earlier verdict:`). `REVIEW_DISPOSITIONS=<file>` adds the
author's answer to each finding (fixed in a commit, disproved with evidence, deferred to the
owner) as claims to verify, because the author never approves its own work. The review
stops (exit 2) rather than carry a wrong record: when an earlier archive is missing, lies
outside `docs/reviews` or no longer matches the sha256 its usage record stored (an archive
edited after the reviewer wrote it), when an earlier round has another scope, a reference
that resolved to another commit (`--commit HEAD` one commit later is another change), another
HEAD for a `--commit` or `--uncommitted` round (an uncommitted diff committed since is
replaced by the next one), or for `--base` a head that is not an ancestor of the current HEAD
(a reused label from another change), or when the diff plus the carried rounds and
dispositions exceed the 400000-byte guard. A round recorded before these checks existed
carries neither the resolved reference nor the sha256 and is refused the same way. A fresh
label starts at round 1.

**The final Accept comes from one fresh full review under a NEW label.** Carried rounds and
dispositions help the loop converge, but they also steer the reviewer toward what was
already said. When the rounds under one label stop finding anything, run one more review
under a label never used before: it sees no earlier round and no disposition, and its
verdict is the one that closes the change.

**A checkout that changes while the review runs fails it with `stale_checkout`.** That is
correct, not a flake: the reviewer reads files while it runs, so its findings may describe a
tree that the archived diff and fingerprint do not. An edit, a new untracked file, a moved HEAD
or a moved base all count. Leave the checkout alone until `review.sh` exits — keep working in
another worktree — and run the review again.

`./scripts/review.sh --self-test` exercises both adapters' offline failure cases and is
included in `./scripts/check.sh --self-test`; these self-tests require Python 3.10+ for
both providers. Missing tests or missing completion evidence fail, and so does any one of
its suites running fewer than its minimum number of tests: a combined total let an emptied
suite hide behind a grown one. Exit 0 from a reviewer means collection
completed, not that the verdict is Accept. Missing final evidence fails closed.

**The output is unverified INPUT.** The requesting agent verifies every finding against the
code, drops what it disproves, keeps what it confirms, and owns the verdict. Relaying a
reviewer's verdict verbatim — in either direction — is a failed review. A confirmed
critical finding is a stop signal.

Reviews cost budget: {{OWNER_NAME}} must have asked in this session or explicitly authorized
a bounded automatic-review policy in the project's canonical instructions. Installing a
plugin or having the skill selected automatically does not grant spending permission.
The host must stop review-and-fix automation at its round limit and on unresolved owner
decisions. This is an agent instruction, not an adapter-enforced session counter or
authorization check. The adapter enforces per-invocation limits only. Automation never
authorizes a commit, push, deployment, or an author-only approval. The host is responsible
for choosing a different reviewing model; `--requester` is reported metadata, not attestation.

## Rounds, labels and designs

When the rounds start and what runs in parallel is the lead's part, in `docs/WORKFLOW.md`,
"Review rounds — early, inside the worker, in parallel". This section says how to run them.

- Review a design under its own label, such as `<feature>-design`, before any code exists.
  Commit the design on the feature's branch, so that every code round's diff carries it.
- In the code rounds, answer a finding inside one of the design's exclusions with that
  exclusion as its disposition ("deferred by decision", naming the design's section). Pass
  it in `REVIEW_DISPOSITIONS` from the second round on; the first round has no earlier round
  to attach it to, and the reviewer reads the exclusion in the diff.

## Unavailable reviewer

Reviews have no default monetary budget cap. Pass a supported monetary-cap option only
when the owner explicitly specifies one. This does not remove timeout, turn, output,
authorization, or provider-account limits; it does not authorize automatic retries.

If a reviewing CLI cannot finish because of quota, context exhaustion, timeout,
authentication, or missing final evidence, do not treat that failure as Accept. Both
adapters return a failure with a local usage record. Codex uses `REVIEW_TIMEOUT_SECONDS`
(1800 by default); Claude reviews use `--timeout` (1800 by default). Timeout stops the child process
group and preserves captured partial output. Through the wrapper, `REVIEW_TIMEOUT_SECONDS`
sets the timeout for each provider, with the same 1800-second default. This is a total
wall-clock deadline, not an idle timer: active work can continue beyond ten minutes, but
is still stopped at thirty minutes by default. Claude's final-JSON output does not provide
reliable startup/activity detection. With `--fallback`, two timed-out default
attempts can take about one hour plus local processing and quota-observation overhead. There is no purchase
of extra credits and no retry of the same provider.

**The requested reviewer is never silently replaced.** The reviewer is usually requested
because the other model wrote the patch, so a substitute can be the author reviewing its own
work under a record that looks valid. Without `--fallback` (dispatcher: `--allow-fallback`),
a reviewer that cannot run fails the review: nonzero exit, its `failure_kind`, and a
`FAIL [review]: requested reviewer ... did not produce a review` line. With `--fallback`,
the wrapper and bundled `review_dispatch.py` try the other configured model once after an
operational failure: quota, authentication, timeout, missing CLI, CLI error, context
exhaustion, turn/budget exhaustion, or output limit. The substitute's archived evidence
then opens with a `FALLBACK REVIEWER:` line naming the requested reviewer and its failure,
its usage record carries `review_fallback_from`, and the run prints a `FALLBACK [review]`
line. A CLI that rejects a flag the read-only run requires (`cli_unsupported`, typically an
outdated CLI) fails every run the same way; it is a setup fault, never routed to the other
reviewer even with `--fallback`, and the fix is upgrading the CLI, not dropping the flag. Both model pins remain owned
by project setup (`REVIEW_CLAUDE_MODEL` / `REVIEW_CODEX_MODEL` override them). An absent or
invalid alternate pin stops failover rather than choosing a model. Direct adapter calls
remain single-provider. A completed Reject or manual-check verdict is a result, not an
availability failure; it never triggers another provider. Invalid evidence, wrong model
attestation, invalid scope, missing guidance, changed checkout, and evidence/usage storage
failures stop the chain. The original scope is checked between attempts and at completion.

**Cancelling a review stops the reviewer.** Ctrl-C, SIGTERM and SIGHUP (a closed terminal
or a restarted host session) stop the reviewer's whole process group, record the attempt
as `cancelled` with its partial output in a usage record, and never fail over. That is
cancelling an active reviewer, or an attempt that failed anyway. A signal that lands while
an already completed review is being finalised (the closing quota read, the final snapshot,
the records) keeps it `completed` with its verdict: the paid result exists, and discarding
it would only buy the same review again. A SIGKILL to
the review process itself cannot be handled, and the wall-clock timeout lives in that process
(the supervisor), so it is lost with it: the reviewer then runs to its own end, bounded only
by its own CLI.

Each attempt retains separate evidence and usage. Immutable checkpoints under
`.myagentkit/usage/chains/<chain-id>-<attempt-count>.json` link the attempts; these are not
additional token records. The final `review dispatch:` JSON names the selected reviewer or
failure. At most two provider attempts occur per invocation. If both fail, leave review
pending and continue independent authorized work; never restart an exhausted chain
automatically. A review-and-fix round is separate from a provider attempt and may consume
two calls; hosts must account for that when applying task-level authorization.

If the fallback model authored any part of the patch, its findings are advisory only.
The host must check all patch authors before treating any completed result as independent
review; neither a new process nor automatic failover grants author-independent approval.

Record the affected task, evidence path, and pending review in current project state. Then
continue independent authorized implementation, tests, or documentation. When Claude was
providing an optional implementation proposal, the host can implement the task itself;
this is not independent review. Do not commit or push a protected diff before its required
review is satisfied. If no independent work remains, hand off the blocker instead of
waiting indefinitely. Accounting details live in `docs/USAGE.md`.

## Template to paste (tools without a wrapper)

```
You are the safety diff reviewer for {{PROJECT_NAME}}. You never change the reviewed
checkout: no file edits and no state-changing commands in it. Run the suite, the self-test
and your own reproductions in a throwaway copy, never with network access and never with a
paid model call; mark each finding REPRODUCED (with the command) or REASONED.

Read AGENTS.md, docs/ARCHITECTURE.md and docs/REVIEW_GATE.md, then review the diff below
in the REVIEW_GATE.md priority order. Grep the callers of every changed public member.

Report EVERY finding you can establish, not only the first few, ranked by severity. Start
each with its severity (Critical, High, Medium or Low), then the file, the line, why it is
wrong and how it fails concretely, so the calling agent can verify or disprove it
independently, and end it with "Fix sketch:" and a short fix direction (not a patch). In a
later round, paste the earlier rounds' findings and verdicts and the author's disposition of
each as claims to verify (a disproved finding counts only once checked against the code; a
deferred one stays open under Manual checks), and ask which are fixed before reviewing the
whole diff again; the final Accept comes from one fresh review with no earlier rounds. Finish with a line
"VERDICT: Accept" / "VERDICT: Accept with Manual Checks" / "VERDICT: Reject", followed by
any manual checks written as full sentences ready to paste into docs/STATE.md.

[DIFF HERE]
```
