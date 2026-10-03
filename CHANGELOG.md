# CHANGELOG

What changed in the kit, dated, newest first. `sync-kit.sh` prints the entries added since
a project's recorded kit version, so an entry must say what a project OWNER has to do —
not just what moved. Mark anything needing hand-application with **ACTION**.

Versions are `MAJOR.MINOR`. MINOR adds or refines; MAJOR changes a rule or a file layout in
a way that existing projects must reconcile by hand.

WHY an entry exists belongs in `RESEARCH_LOG.md`; this file records WHAT changed.

---

## v0.9 — 2026-10-03

Hardening from the unreported findings of two projects using the kit. `scripts/check.sh`,
`scripts/review.sh` and the review scripts are project-owned, so most items below need a
hand merge; `sync-kit.sh` now keeps listing them until you confirm (see "Sync stamp").

- **Gate lock (issues #19, #20, #11).** `scripts/check.sh` runs one gate per checkout at a
  time: it re-executes itself under a few lines of Python holding `fcntl.flock` on
  `<git dir>/check.lock`, and the gate and everything it starts keep the lock until the last
  of them exits. Nothing is reclaimed and no pid is trusted. A second run (Stop hook, commit
  hook, manual) waits with a NOTE every 30 s instead of sharing the build directory and
  reporting a false FAIL; INT/TERM stop the run after cleanup. The gate now needs `python3`.
  A build that leaves a compiler server or build daemon running holds the lock until it
  exits: turn that off in the build command.
  `GATE_LOCK_WAIT=<seconds>` bounds the wait: when it runs out the gate prints `NOT RUN [lock]`
  and exits 75 ("did not run", neither pass nor fail). `--self-test` no longer writes into
  the working tree: its injections come from outside it (`GATE_SELFTEST_EXTRA_FILE`), and the
  rule "a self-test case never changes a tracked file" is in check.sh and `docs/WORKFLOW.md`.
  A commit made during a long self-test now waits for it. **ACTION:** port into your
  project-owned `scripts/check.sh` the EXIT CODES and SELF-TEST CASE comments, the lock block,
  `cleanup` with its traps and the `GATE_SELFTEST_EXTRA_FILE` line; move any self-test case
  (your `boundary_selftests.sh` included) that writes into the tree to a place outside it.
  Re-sync `docs/WORKFLOW.md` if you own a modified copy. **ACTION:** Claude Code overlay: copy
  `.claude/hooks/gate_on_stop.sh` again from `overlays/claude-code/files/` (it sets
  `GATE_LOCK_WAIT=500` and reports exit 75 as "gate did not run") and re-fill its placeholders.
  A `.git/check.lock` directory left by a killed run of an unreleased build must be removed
  by hand.
- **The reviewer CLI on PATH wins over `~/.local/bin`.** `review.sh` used to put
  `~/.local/bin` FIRST when a `codex` lived there, so an old standalone build left behind
  shadowed the current binary and every review failed with "requires a newer version" while
  the same command worked at the prompt. It is now a fallback at the end of PATH; the
  regression builds both binaries. **ACTION:** in your project-owned `scripts/review.sh`,
  change the `PATH="$HOME/.local/bin:$PATH"` line to `PATH="$PATH:$HOME/.local/bin"`, and
  copy the synced `test_claude_bridge.py`.
- **Cross-model review round.** A second model's review of this version's diff found holes
  the first pass had left, fixed before release: two rounds on the gate lock ended in the
  kernel lock above, after a reclaim-by-rename still let three waiters race and a gate killed
  with SIGKILL leave its build running under a reclaimed lock (**ACTION:** copy the lock
  block and `cleanup()` from `core/scripts/check.sh` into your `scripts/check.sh`; delete a
  `.git/check.lock` symlink left by the older gate, the new one refuses it by name);
  `.githooks/commit-msg` cuts below a scissors line only when it is git's own editor header
  (a scissors line in a `-m` message is kept and checked) and rejects a commented-out
  trailer; `pre-commit` and `pre-merge-commit` report exit 75 as "did NOT RUN, commit
  blocked", never as FAILED; the review adapters keep the usage record of a review whose
  reference was deleted mid-run, and an unreadable or malformed usage record stops a
  labelled round instead of being skipped; `sync-kit.sh` refuses to stamp when its ACTION
  scan fails; `doctor.sh` no longer evaluates the `toolchain_path` line (`$NAME` and
  `${NAME}` only; other shell syntax is MISSING), finds the reviewer CLI with `review.sh`'s
  `~/.local/bin` fallback, and accepts a `grep` alias only with `--color`/`--colour`;
  `.githooks/commit-msg` fails closed on an `AGENTS.md` it cannot read, checks comment
  lines too (whether git keeps a `#` line depends on `commit.cleanup`, a `--cleanup` flag the
  hook cannot see, and `-m` versus the editor; a commented-out credit left by a squash is one
  line to delete), and rejects "Generated with GitHub Copilot" and "Generated with Google
  Gemini"; review rounds are carried only for the same resolved reference (`--commit HEAD`
  one commit later is another change), the same HEAD for `--commit` and `--uncommitted`, and
  only while the archive's sha256 matches its usage record, so rounds recorded by an older
  kit are refused and need a new task label (**ACTION:** copy `claude_bridge.py`,
  `codex_bridge.py`, `agent_usage.py` and `test_claude_bridge.py` from `core/scripts/` and the
  "stops (exit 2)" paragraph of `docs/REVIEW_GATE.md`); `doctor.sh` requires mode 100755 in the
  index for every hook and script (an untracked one is MISSING), skips the grep probe with a
  NOTE where `timeout` is absent, and reads the npm cache's third level; `spawn_worker.sh`
  starts in a checkout path containing an apostrophe (**ACTION:** copy it from the overlay).
- **Third cross-model round.** `scripts/check.sh`: a nested run must show it INHERITED the
  lock, not name it: the holder exports `GATE_LOCK_FD`, and a run whose `GATE_LOCK_HELD`
  names this checkout's lock proves that descriptor is open on the lock file and held before
  it skips the lock or honours a seam; otherwise `FAIL [env]` by name, so variables copied
  from a gate killed with SIGKILL no longer let a build override through. `toolchain_path`
  is applied before the lock resolves `python3`. **ACTION:** copy the toolchain block (now at
  the top), the seam block and the lock block from `core/scripts/check.sh`. `.githooks/
  commit-msg` cuts nothing below a scissors line (a `-m` message can reproduce git's whole
  header): a credit quoted in a `commit -v` diff is rejected and the message says to commit
  without `-v`; an alphanumeric `core.commentChar` counts as a comment prefix. A malformed
  usage record, or a completed review with no evidence, stops a labelled round, and the
  message says to move the record out of `.myagentkit/usage` (a new label does not help: the
  scan cannot tell whose round a file held until it parses). **ACTION:** copy
  `claude_bridge.py` and `test_claude_bridge.py`. `doctor.sh` bounds the grep probe's whole
  process tree (`setsid` where present), reports a probe that did not complete as a NOTE,
  and honours `REVIEW_REVIEWER`, `REVIEW_CLI_BIN` and `CLAUDE_CLI_BIN` like the wrapper. The
  Claude Code Stop hook's exit-75 path has a test. **ACTION:** if your
  `scripts/boundary_selftests.sh` copied the existing-file example, replace its `:` with an
  `echo "  ok   — <label>"` line, or the self-test reports "ran no case".
- **Fourth cross-model round (issue #33).** `sync-kit.sh` exits on INT/TERM instead of
  stamping. The review adapters treat a usage record with a bad status or task fields as an
  integrity failure, hash the evidence bytes they publish (a lost archive is recorded as
  `evidence_unavailable`, never as no record), and a Codex cancel during the closing quota
  read keeps the record. `.githooks/commit-msg` checks `Key : value` spacing and folded
  trailers, honours `core.commentString` over `core.commentChar`, and treats a directory at
  `AGENTS.md` as unreadable. `doctor.sh` reports an unset variable inside `toolchain_path`.
  The existing-file boundary example runs in a disposable copy of the checkout. **ACTION:**
  copy `claude_bridge.py`, `codex_bridge.py`, `agent_usage.py` and `agent_process.py` from
  `core/scripts/`; replace the existing-file example in your `scripts/boundary_selftests.sh`
  and merge the "disposable copy" bullet into `docs/WORKFLOW.md`.
- **Scan failures that were not scanner failures (issues #13, #14).** A tracked file deleted
  without `git rm` now fails `[scan]` under its own name with the command that fixes it, and
  every other scan still runs. A symlink to a directory (for example `node_modules` linked
  into a throwaway worktree) is skipped with a `NOTE [scan]` line instead of failing the scan.
  A real grep failure keeps its old message. `docs/GOTCHAS.md` describes the NOTE.
  **ACTION:** copy the scan-list block from `core/scripts/check.sh` into your `scripts/check.sh`
  (keep your filled placeholders); copy `core/docs/GOTCHAS.md` if your project syncs it.
- **Review tooling fails closed (issues #12, #9, #8).** A named reviewer is never silently
  replaced: `review.sh` fails when the requested reviewer cannot run, and `--fallback`
  (dispatcher `--allow-fallback`) allows one substitute whose evidence opens with
  `FALLBACK REVIEWER:`. A CLI that rejects a required flag (`cli_unsupported`, Claude or Codex)
  never fails over. Scope with an effective Git clean/process filter or `ident` is refused
  before launch, since the filtered diff can omit lines the fingerprint hashed. Ctrl-C,
  SIGTERM and SIGHUP now kill the reviewer's process group and record `cancelled`; a signal
  the caller set to ignore (`nohup`, a background job) stays ignored. The review self-test has
  a minimum test count per suite, and `check.sh --self-test` fails when `boundary_checks.sh`
  has checks but the boundary self-tests printed no case. **ACTION:** none of these scripts is
  kit-owned, so copy the review tooling as one set into `scripts/`: `agent_process.py`,
  `agent_usage.py`, `claude_bridge.py`, `codex_bridge.py`, `review_dispatch.py`,
  `test_agent_usage.py`, `test_claude_bridge.py`; add the `--fallback` case to your
  `scripts/review.sh` (pass `$fallback` to the dispatcher; core has it) and the boundary
  self-test hunk to your `scripts/check.sh`. **ACTION:** automation that relied on automatic
  failover must now pass `--fallback`. **ACTION:** each `boundary_selftests.sh` case must print
  `  ok   — <label>`. **ACTION:** a repository with Git LFS, a clean filter or `ident` in the
  review scope cannot use `review.sh`; use the manual template in `docs/REVIEW_GATE.md`.
- **Review rounds converge (issue #18).** Both reviewers are asked for every finding, a
  severity (Critical, High, Medium, Low) on each, and a fix sketch. With the same
  `MYAGENTKIT_TASK_ID` a later round's prompt carries the earlier completed reviews from the
  reviewer's own archive, plus `REVIEW_DISPOSITIONS=<file>` for the author's answers. A
  disposition is a claim the reviewer verifies, never a settlement: a deferred finding stays
  open under Manual checks, and the closing Accept comes from one fresh review under a new
  label. Carried rounds must share scope and reference with the new review and have an
  ancestor head (a rebase, an amend or a `--commit` round with another head is refused and
  the message says to use a new label), count toward the 400000-byte diff budget, and
  show their verdicts as `Earlier verdict:`. A missing earlier archive exits 2 for both
  reviewers. `stale_checkout` still fails the review, and now says why and what to do.
  **ACTION:** copy the review tooling set named in the previous bullet; add the two new
  "Running it" paragraphs and the template change from `core/docs/REVIEW_GATE.md` to your
  project-owned `docs/REVIEW_GATE.md`.
- **Sync stamp (issue #15).** `sync-kit.sh` records a new kit version only after its ACTION
  items are confirmed. It lists the pending ACTION lines as a checklist after the full
  entries on every run, leaves `docs/kit/.kit-version` unchanged and exits 2 until you rerun
  with `--actions-applied`; a line of the form `**ACTION** — none` is not an item. Versions without
  ACTION items are stamped as before. `docs/UPDATING.md` and the README describe it.
  **ACTION:** a script of yours that runs `sync-kit.sh` must expect exit 2 while items are
  pending. If a project was stamped past versions whose ACTIONs it never applied, set
  `docs/kit/.kit-version` back to the last version really applied and sync again.
- **Commit gates (issues #16, #24, #23).** `.githooks/pre-merge-commit` (new, kit-owned)
  runs the gate for the commit a clean `git merge` creates, where git does not run
  pre-commit; git older than 2.24 has no such hook and leaves merges ungated
  (`docs/DEV_SETUP.md` says so). The `check.sh` build step is quiet on a pass; on failure it
  prints `FAIL [build]`, the last 150 lines (the whole log when `CI` is set) and the path of
  the full log, never a filtered subset. Keep deploy-shaped steps, dry runs included, out of
  the build command. `.githooks/commit-msg` (new, kit-owned) rejects an AI credit in a
  `Co-Authored-By`, `Signed-off-by` or `Assisted-by` trailer or a "Generated with" line, only
  when the whole trailer name is a tool or model, the address is a vendor's or a `[bot]`;
  human names that contain a tool's pass. Nothing below a `commit -v` scissors line is cut: a
  credit quoted in that diff is rejected too, and the way past it is to commit without -v.
  The rule "No AI attribution in git" in `AGENTS.md` is the owner's switch: without that line the hook
  gives way (a missing `AGENTS.md` keeps it on), and the setup interview asks. **ACTION:** copy
  the rule bullet and the extended hook sentence from `core/AGENTS.md` into your `AGENTS.md`;
  to allow AI credit, delete the rule line there. **ACTION:** copy the `build_log=` line, the
  build section and the new self-test cases (hooks loop, commit-msg, build failure output)
  from `core/scripts/check.sh` into your `scripts/check.sh`, and remove any `grep error`
  filter from your build command. Optional: the `docs/DEV_SETUP.md` and `setup/INTERVIEW.md`
  sentences.
- **Effort, STATE operation files, doctor.sh, closing a worker (issues #17, #21, #10, #30).**
  Delegated agents run at a stated effort: `worker.md` gets `effort: {{WORKER_EFFORT}}`
  (filled at interview question 8), `diff-reviewer.md` gets `effort: high`, and WORKFLOW and
  HANDOFF say the brief names model and effort and the lead verifies both in the transcript.
  `docs/STATE.md` keeps a status line and a pointer; operation detail and worker results go
  to `docs/<OPERATION>.md`, and both rot-gate messages name it. `scripts/doctor.sh` (new,
  kit-owned) is a read-only machine check with one MISSING line per trap: exec bits, hooks
  path, git identity, Python 3.10+, the default reviewer CLI, tmux, the `node` a git hook
  resolves against `toolchain_path` and `.nvmrc`, the npm cache owner, a shadowed `grep`, a
  checkout under `/mnt/<drive>` on WSL, CRLF in a script, and an unignored `node_modules`
  symlink. A spawned worker session is closed by the lead once it has read the result file;
  `spawn_worker.sh` prints the command. **ACTION:** add `effort:` to both files in your
  `.claude/agents/`, fill `WORKER_EFFORT` and restart Claude Code. **ACTION:** copy the changed
  paragraphs into `docs/STATE.md`, `docs/HANDOFF.md` and the "STATE.md discipline" in
  `AGENTS.md`, and the two message lines into `scripts/check.sh`. **ACTION:** add reading-order
  step 0 (`scripts/doctor.sh`) to `AGENTS.md` and `docs/DEV_SETUP.md` §4. **ACTION:** copy
  `spawn_worker.sh` and the overlay README bullet, and add the closing line to your briefs. In a
  project whose `.gitignore` says `node_modules/` and that symlinks `node_modules`, write
  `node_modules` without the slash.
- **Rules (issues #26, #27, #28, #31).** A web request carries no personal data
  (`docs/WORKFLOW.md` "Web requests carry no personal data", HANDOFF brief item 3,
  `docs/GOTCHAS.md`). A sub-agent returns its report as its final message; only a spawned
  session writes a result file (WORKFLOW rule 7). Worktree-isolated agents run plain commands,
  one per call, and put compound work in a script file (`worker.md`, overlay README). A red
  gate that passes on re-run is recorded, not retried away (WORKFLOW, GOTCHAS). **ACTION:** copy
  the new WORKFLOW section, rule 7's sentences, the HANDOFF sentence and the GOTCHAS entries into
  your project-owned docs, the `worker.md` bullets into `.claude/agents/worker.md`, and name a
  generic User-Agent in every brief that sends an agent to the web.
- **Self-test seams are not a bypass (issue #25).** `check.sh` used to honour its self-test
  overrides in every run, so one exported variable could skip the build or point a gate at
  another file and still print `CHECK: PASS`. They are now `GATE_BUILD_CMD_OVERRIDE`,
  `GATE_SELFTEST_STATE_FILE`, `GATE_SELFTEST_PROJECT_FILE`, `BOUNDARY_CHECKS_FILE`,
  `BOUNDARY_SELFTESTS_FILE`, `GATE_SELFTEST_EXTRA_FILE` and `GATE_SELFTEST_BREAK_SCANNER`, and
  only the self-test's nested runs honour them (they carry `GATE_SELFTEST_NESTED`, which must
  match the live lock holder). Any other run prints `FAIL [env]: <name> is set; ...` and exits
  1. `STATE_FILE` and `PROJECT_FILE` were renamed. **ACTION:** merge into your `scripts/check.sh`
  the SELF-TEST SEAMS block after `fail=0`, the `GATE_SELFTEST_NESTED` export at the top of
  `self_test()` and the "seam outside the self-test" case; add any override variable your own
  boundary checks read to the list; unset these variables where a shell profile or CI step
  exports them.
- **Worker spawning (found while applying the above).** `spawn_worker.sh` now
  `cd`s into the folder before starting the tool, because tmux hands a new session a stale
  `PWD`. Still open: `spawn_worker.sh --worktree` starts from a stale base (issue #32); branch
  the worktree from the commit you mean, not from the default. **ACTION:** copy
  `spawn_worker.sh` (same copy as above).

## v0.8 — 2026-10-03

- **Worker cost (issue #22).** A measured rule set for routing workers lands in the
  `docs/WORKFLOW.md` template as the section "Worker cost — waits and long lives are what
  you pay for": a worker's cache must outlive its waits and it never polls, a review-fix
  round goes to a fresh worker, about 150 requests per worker, the lead does not poll,
  mechanical work to the cheaper model, short reports, cost read at the end of the day. The
  reasoning and the numbers are in `RESEARCH_LOG.md`. **ACTION:** copy the section into your
  project-owned `docs/WORKFLOW.md` (before "Token economics").
- `scripts/agent_cost.py` (kit-owned, synced): per-agent requests, cache read, cache write,
  cache write after gaps over five minutes, poll-only turns and the cache lifetime used,
  from a Claude Code session transcript and its sub-agents. `docs/HANDOFF.md` and the
  handoff command now ask for its table plus the tool's cost screen in an end-of-day
  handoff. **ACTION:** add the end-of-day paragraph to your project-owned `docs/HANDOFF.md`.
- Claude Code overlay: `.claude/agents/worker.md`, a worker definition with
  `experimental.cacheTtl: 1h`, `maxTurns: 150` and the worker rules in its body (placeholders
  `{{WORKER_MODEL}}`, `{{LONG_JOBS}}`), and `scripts/spawn_worker.sh`, which opens a separate
  worker session in tmux and pastes a brief file into it after the TUI is up. The overlay
  README documents the placeholders and the pitfalls. **ACTION:** overlays are not synced;
  copy both files from `overlays/claude-code/files/` by hand, fill the two placeholders, and
  restart any running session before spawning the worker.
- `docs/worker-cost-setups.md`: the six measured setups with their figures, a "which setup,
  when" table for projects that cannot use the first choice (the one-hour cache ignored, no
  tmux, CI, a different host), and the alternatives the research pass rejected with their
  evidence. The WORKFLOW template's rule 1 points at it for the fallback.
- The first real-task measurement is in `docs/worker-cost-setups.md`; `agent_cost.py`'s poll
  detector no longer counts a Python run or a plain `tail` as waiting; `spawn_worker.sh` takes
  `--effort`; the overlay README records that the idle notice fires on every background park.
- `setup/INTERVIEW.md` asks question 8, "Will workers run jobs longer than five minutes?",
  and fills or deletes the worker files from the answer. It also asks what a worker must know
  before running those jobs, and the overlay README says to settle the permission mode of
  spawned sessions with the owner first (both were found missing when the founding project
  took this version).
- `docs/GOTCHAS.md` template: `pgrep -f` and shell wait loops match their own command line.
  **ACTION:** add the entry to your project-owned `docs/GOTCHAS.md` if your agents wait on
  processes.

## v0.7 — 2026-09-05 (unreleased)

- Downstream adoption exposed four review self-tests that assumed installed projects still
  used the template's empty model pins and Claude default. The fixture now explicitly sets
  those defaults in its temporary copy; project settings are preserved. **ACTION:** copy
  the updated `test_claude_bridge.py` with the complete companion set when upgrading.

- **Issue #7:** existing-file negative tests must restore current bytes and mode before
  deleting backups, including on EXIT/INT/TERM. A separate scaffold example isolates
  traps and terminates after signals; its regression preserves uncommitted content.
  **ACTION:** prefer disposable snapshots, or update project-owned destructive probes
  with restoration registered before mutation and interruption tests.

- The final review exposed initially hidden index changes and a verdict-only manual-check
  section. Review now rejects assume-unchanged/skip-worktree entries before model launch
  and excludes verdict declarations from manual-check validation. **ACTION:** upgrade the
  complete review runtime; clear such index flags before reviewing a complete checkout.

- The platform matrix exposed scanner exit-code differences between GNU and BSD xargs.
  The scanner now preserves each grep batch's match/no-match/error outcome explicitly.
  Real missing-file errors fail on both platforms. **ACTION:** take the updated project-owned
  `scripts/check.sh` scanner carefully, retaining your configured gates and build command.

- A follow-up review exposed four additional scope/evidence failures. Git diff drivers
  are disabled, raw checkout bytes and resolved references enter the fingerprint, merge
  commits are reviewed against their first parent, and Codex manual-check verdicts require
  actual checks. All four fixes have failing-before/passing-after regressions.
  **ACTION:** copy the complete review runtime/test companion list and repackage the plugin.

- The kit's own four legacy raw review archives are now untracked and preserved locally.
  Reference and commit reviews exclude removed legacy transcripts while keeping scrubbed
  summaries in scope. **ACTION:** use the same preserve-and-untrack migration for old
  project archives; historical Git commits are not rewritten by this change.

- The kit-source CI runs the full offline acceptance suite on Linux/macOS with Python
  3.10 and 3.14. Action revisions are pinned and jobs have read-only repository access.
  This does not run paid model calls or change installed projects' CI templates.

- **Issue #5:** an explicit transcript-Accept/no-final-response regression verifies that
  transcript text remains diagnostic only. Missing, empty, malformed and conflicting final
  responses are rejected by the wrapper. **ACTION:** take the complete review runtime/tests.

- **Issue #4:** a timeout-then-success regression proves failed evidence stays immutable,
  carries no verdict, and does not change the next review's diff or checkout fingerprint.
  **ACTION:** keep failed diagnostics locally; upgrade the adapters and ignore rules rather
  than deleting immutable reports to repair review scope.

- **Issue #3:** the interview now gives both vendor-plugin install commands explicitly
  and explains repository versus marketplace names. **ACTION:** use `codex@openai-codex`,
  matching the official marketplace manifest, rather than deriving the name from the repo.

- **Issue #2:** the boundary self-test example requires a green baseline and both a
  nonzero exit and the boundary's own diagnostic. An executable regression rejects
  unrelated failures and misleading success output. **ACTION:** adapt the example when
  maintaining project-owned boundary tests; generic exit-only gate cases remain explicit.

- **Issue #1:** setup now stages the foundation and hands it to fresh review before the
  first commit. The closing report identifies pending review explicitly. **ACTION:**
  use the updated setup interview; initial gate code has no implicit review exemption.

- **2026-09-06 review fixes:** model calls now require ignored, untracked private storage;
  malformed successful Claude envelopes stop without failover; malformed or conflicting
  Codex verdict declarations fail evidence validation. Kit acceptance requires the named
  regression suites and rejects skips. The existing-project companion list is canonical
  in `core/docs/DEV_SETUP.md` and has an upgrade regression. **ACTION:** copy that complete
  list, merge the ignore rules, and preserve/untrack any previously tracked raw diagnostics.
  The owner authorized committing and pushing these repairs with Claude review explicitly
  pending. This is not a review approval; see `docs/worktree-notes/role-neutral-review.md`.

- Review attempts now default to 30 minutes rather than 10, in both directions and in
  direct adapters. Explicit timeouts are preserved. This remains a total wall-clock limit,
  not an inactivity detector; two fallback attempts can take about an hour. Claude proposal
  defaults are unchanged. **ACTION:** upgrade the companion Python runtime files and
  repackage the Codex plugin after source review; existing explicit overrides still win.

- Owner-selected reviewer default is Claude. Reviews automatically fail over once to the
  other configured model on operational unavailability, in both directions. Each attempt
  retains its own evidence and usage, linked by immutable chain checkpoints. Completed
  Reject results, invalid evidence, stale scope, and storage failures never trigger failover.
  Author-model fallback findings remain advisory, not independent review approval.
  No default review monetary cap is added. **ACTION:** manually upgrade project-owned
  `review.sh` and its companion Python files, including `review_dispatch.py`; keep existing
  model pins. Sync does not overwrite those files. Repackage and reinstall the Codex plugin
  after source review to use the updated skill and bundled dispatcher.

**The kit no longer has an opinion about which model writes and which reviews.** The rule
was always "the author never reviews its own patch, and the reviewer is a different model".
The tooling did not say that: `review.sh` was pinned to Codex, and the documents described
Claude as the author. A real project ran out of the author's budget and swapped the roles;
the kit did not support the arrangement it had been claiming to require.

- `./scripts/review.sh [scope] --reviewer codex|claude` runs either direction. The default
  is the one configured at the top of the script, and the script accepts nothing else — the
  reviewer name is matched against a closed list and no flag is passed through to a CLI.
- **Both directions publish ONE evidence format**: the same header table, exactly one
  `VERDICT:` line (or none when the run failed), and the same
  `docs/reviews/<stamp>-<reviewer>-review.md` naming. The renderer refuses a header that has
  drifted and refuses a verdict for a run that did not complete, so this is enforced rather
  than agreed. Records made before and after a role swap can be compared.
- **Both models are pinned by name and the wrapper refuses to run unpinned.** A record that
  said "CLI default" named nothing a later review could be compared against. Claude's pin is
  additionally ATTESTED against the CLI's own `modelUsage`; Codex publishes no model identity
  in its output, so its record says the pin is requested and unattested. The evidence states
  which of the two it is.
- `AGENTS.md`, `WORKFLOW.md` and `REVIEW_GATE.md` now name AUTHOR and REVIEWER as roles and
  say the roles are expected to swap with the budget.
- The setup interview asks three separate questions — which model authors, which reviews,
  and which budget is scarce — instead of asking about budget and assuming the rest.
- New `docs/delegation-is-not-symmetric.md` records what in-session delegation actually
  exists in each direction, and why there is no `overlays/codex/`. Nothing was written from
  an inferred schema.

**ACTION — existing projects.** `scripts/review.sh` and the adapter Python files beside it
are PROJECT-OWNED: `sync-kit.sh` will not touch them, by design. To take this change:

Sync alone does not replace an existing wrapper or empty its model pins. The new pin
requirement applies to new installations and to projects that manually adopt this wrapper.

1. Copy `core/scripts/review.sh` over your own, then re-apply any local edits.
2. Copy every runtime and test companion in the canonical upgrade list in
   [core/docs/DEV_SETUP.md](core/docs/DEV_SETUP.md#3-the-second-model--only-if-you-want-cross-model-review).
3. **Fill in `DEFAULT_REVIEWER`, `CODEX_MODEL` and `CLAUDE_MODEL` at the top of
   `scripts/review.sh`.** Both model pins ship EMPTY and the wrapper stops until they are
   set. This is deliberate: an unpinned reviewer archives whatever its CLI defaulted to.
4. Run `./scripts/check.sh --self-test` and `./scripts/review.sh --self-test`.

Older reports named `<stamp>-<branch>.md` or `<stamp>-codex.md` are left alone; they stay
readable, they are simply not in the new shape.

Clarifications: both hosts can delegate reviews through the shipped command/skill entry
points; only structured implementation-proposal support is asymmetric. Synthetic live
checks are integration evidence, not independent acceptance of the implementation. For a
co-authored change, use a reviewer that did not author any part of the combined diff.

The owner selected Claude as the default reviewer for the Astra-author workflow. The
shipped wrapper now defaults to Claude; explicit `--reviewer codex` and per-project setup
remain available. Existing project-owned wrappers still require a manual settings update.

Codex can host the cross-model workflow through the MyAgentKit Codex plugin.

- Two skills request fresh Claude review-and-fix and implementation proposals. Codex remains
  the writer. Both support explicit and implicit discovery; spending still needs authorization.
- The Claude adapter restricts tools, disables customizations/MCP, pins the model, bounds
  execution, and archives structured results with source hashes. Stale or absent evidence fails.
- The wrapper gained a Claude adapter beside the Codex one; the kit-root wrapper now
  delegates to the core implementation rather than carrying a second copy. Codex collection
  rejects absent and conflicting final verdicts. (Reviewer selection and model pinning were
  reworked later in this same release — see the role-neutrality entry above for the shape
  that actually ships.)
- The new kit-source `scripts/check.sh` runs packaging drift, adapter regressions, and
  bootstrapped-project acceptance. Its self-test proves existing and new rejection paths.
- Both CLI directions now have bounded process execution and local per-invocation usage
  records, including partial/failing calls. Caller/task labels make review rounds comparable.
  Missing subscription percentages remain unknown, not inferred from tokens or API dollars.
- Quota, context exhaustion, timeout, and invalid replies stop the delegation loop while
  the host continues independent authorized work. Required review still blocks its protected
  commit/push. No automatic retry, credit purchase, or silent model fallback was added.
- Codex calls also capture bounded official account-quota observations before/after work,
  including the reported plan and window percentages. These are not per-call consumption
  claims. `MYAGENTKIT_CAPTURE_QUOTA=0` disables the optional reads.
- Both reviewers now capture and validate the same checkout snapshot, reject stale or
  mismatched reference context, and persist immutable evidence before reporting completed
  usage. Output capture uses bounded pipes rather than unbounded temporary output files.
- Bootstrapped projects ignore raw review archives; deliberately scrubbed summaries remain
  versionable. Claude's kit-layout guidance includes the architecture document.
- Bootstrap excludes locally generated Python bytecode from installed project files.
- Reviews no longer impose a default monetary cap. Claude's `--max-budget-usd` is sent
  only when explicitly supplied; timeout/turn/output protections remain unchanged.

**ACTION:** existing projects must hand-merge the project-owned review/check scripts and
review policy, and copy the Python runtime/test companions listed in
`core/docs/DEV_SETUP.md`. Merge the private usage and raw archive ignore rules from
`core/.gitignore`, and add `core/docs/USAGE.md`. Do not
overwrite customized project gates. Codex plugin installation is separate; see
`docs/CODEX.md`. Live validation and review debt are recorded in `docs/ACCEPTANCE.md`.
Python 3.10+ is now required for both live providers and their self-tests. Missing test
files and missing completion evidence fail closed. Runtime updates require rebuilding and
reinstalling the Codex plugin; Claude's cross-review command also carries recovery guidance.

## v0.6 — 2026-07-27

Renamed: **MyAgentKit → MyAgentKit_Keel**. A keel is a ship's backbone and the first part
laid down — "laying the keel" is the moment construction begins — which is what a project
foundation is for. It also carries the sense in "on an even keel": the thing that keeps a
project stable rather than the thing that moves it.

- The repository is now `KBT-0/MyAgentKit_Keel`. GitHub redirects the old path, so existing
  clones and marketplace entries keep working; the install lines in the README are updated
  to the new one.
- **The plugin is deliberately NOT renamed.** It stays `myagentkit`, so `/myagentkit:handoff`,
  `/myagentkit:cross-review` and `/myagentkit:kit-feedback` are exactly what they were. A
  command a person has learned to type is a bad thing to rename for cosmetic reasons.
- Archived review reports under `docs/reviews/` are left untouched. They are dated evidence
  of what was said at the time, and evidence is not edited afterwards — including for a
  rename.

**ACTION** — none required. If you cloned by URL, `git remote set-url origin
git@github.com:KBT-0/MyAgentKit_Keel.git` avoids relying on the redirect.

## v0.5 — 2026-07-27

Sending findings upstream becomes opt-in, asked once, and the README stops describing an
overlay that no longer exists.

- **New placeholder `{{KIT_FEEDBACK_RULE}}` in the constitution.** Setup Phase 0.5 now asks
  whether the agent should ever offer to send kit findings upstream, and fills the
  placeholder with one of two whole bullets: the offer rule, or an instruction never to raise
  it. A no is therefore structural — the clause is simply absent from that project's
  constitution — instead of a preference every future session has to be told again.
- **The offer is separated from the learning.** Research passes, audits and trap logging run
  unchanged whatever the answer; they write to the project's own docs and always did. Only
  the outward-facing offer is gated. `setup/RESEARCH_PROTOCOL.md` checks the constitution
  before offering, and `INTERVIEW.md` Phase 5 is skipped outright on a no.
- **Tone.** The two sentences that leaned on obligation — "this is not a courtesy" and "a
  complaint that stays in a chat log improves nothing" — are gone. The mechanism is worth
  explaining; it is not worth guilting somebody into.
- **README corrections.** The overlay no longer claims to hold skills and commands (commands
  are the plugin; there are no skills), the status block tracks the real version, and the
  platform claim now says Linux native and WSL, naming macOS/BSD as the untested surface and
  the GNU `grep`/`sed` assumptions as where they would break first.

**ACTION** — existing projects: `AGENTS.md` is project-owned and is never overwritten, so
`sync-kit.sh` will not add this. Decide the question yourself and paste the matching bullet
from `setup/INTERVIEW.md` Phase 0.5 into the MENTION ONCE list, replacing the old
kit-feedback bullet if it is there. Doing nothing leaves the v0.4 behaviour, which is the
offer being made.

## v0.4 — 2026-07-27

A guard against the failure that produced it. During this kit's own development a
`git reset --hard`, run to drop a throwaway commit, destroyed uncommitted work — including a
review record the owner had written by hand, which git could not recover because the reflog
holds commits and nothing else.

- **`overlays/claude-code/files/.claude/hooks/guard_destructive_git.py`** blocks
  `reset --hard`, `checkout --`, `restore`, `clean -f`, `stash drop` and force pushes while
  the tree is dirty, printing the file list that would have been lost. `stash push`, `commit`
  and `--force-with-lease` pass through — the recoverable ways to do the same jobs.
- **The constitution** gains the rule for tools without the hook: commit or stash first,
  every time, and check `git status` rather than trusting that the tree is clean.
- **`core/docs/GOTCHAS.md`** carries the reasoning; `RESEARCH_LOG.md` finding #11 carries
  the general form, which is not about git: an agent's cleanup is the most dangerous thing it
  does, because attention has already moved to the next task.

**ACTION** — projects on v0.3 that took the claude-code overlay: copy the new hook in and add
the `PreToolUse` block to `.claude/settings.json` (see `overlays/claude-code/files/`).
Projects using another tool get the constitution rule and nothing enforcing it, which is
worth knowing rather than assuming.

## v0.3 — 2026-07-27

Project knowledge gets its own layer. Until now the kit had a slot for a design document
(`{{DESIGN_DOC}}`, a path the project supplied) and nothing at all for "what are we building
right now, and what are we deliberately not building yet". Both are shipped files now.

- **`docs/PROJECT.md`** replaces the `{{DESIGN_DOC}}` placeholder. Same role — permanent
  decisions, DECIDED/OPEN tagging, design authority — but a real file at a fixed path, so
  two placeholders disappear and the constitution stops pointing at something that might not
  exist. It is NOT in the reading order: sections are numbered, listed in a Contents, and
  cited by number rather than quoted.
- **`docs/PHASES.md`** is new and read every session. Current phase in full, later phases
  one line each, and — the half that earns its place — what is explicitly OUT of scope until
  later. Promoted from `patterns/staged-prototype.md`, which stays as the long-form
  reasoning.
- **An agent may add OPEN items to PROJECT.md freely and may NEVER mark anything DECIDED.**
  When the owner appears to settle something in conversation, it is recorded as OPEN with a
  note and a question. A wrongly captured question costs a minute; a wrongly promoted
  decision is invisible, binding, and compounds.
- **`scripts/check.sh` fails when a numbered PROJECT.md section is missing from its
  Contents.** Selective reading is what keeps that file affordable as it grows, and it only
  works while the Contents is complete. Four self-test cases, sixteen in total now.
- **No ROADMAP.md**, considered and rejected — the reasoning is in
  `docs/knowledge-has-three-horizons.md` along with the permanent / episodic / momentary
  split the three files implement.

**ACTION** — projects on v0.2 must add both files: copy `core/docs/PROJECT.md` and
`core/docs/PHASES.md` in and fill them. Add **`docs/PHASES.md` to the reading order** in
`AGENTS.md`, as the step after the constitution. Do NOT put `docs/PROJECT.md` in the reading
order — it is read by section, on demand; putting it there is the cost this release exists
to avoid. A project with an existing design document under another name (`GDD.md`,
`SPEC.md`) either renames it or makes `docs/PROJECT.md` the file that owns the Contents;
two canonical design documents is the duplicate-authority problem this release exists to
avoid. The gate FAILS until `docs/PROJECT.md` exists, which is deliberate.

## v0.2 — 2026-07-26

The three commands moved out of the Claude Code overlay into a proper plugin, and the kit
gained a way to be maintained by the projects using it rather than only by its author.

- **Commands are now a Claude Code plugin**, installed once per machine instead of copied
  into every project: `/myagentkit:cross-review`, `/myagentkit:handoff` and the new
  `/myagentkit:kit-feedback`. Namespacing comes from the plugin, which also ends the risk of
  a bare `handoff` or `cross-review` colliding silently with something else.
- **`/myagentkit:kit-feedback`** sends a finding upstream as a GitHub issue or pull request.
  It scrubs the project out of the text, shows the exact body, and sends nothing without an
  explicit yes.
- **Two places now offer it unprompted:** the end of an ecosystem research pass
  (`setup/RESEARCH_PROTOCOL.md`) and the audit's backflow question
  (`core/docs/WORKFLOW.md`). A third lives in the constitution's MENTION ONCE list, for when
  the foundation itself misbehaves during ordinary work.
- **`CONTRIBUTING.md`** is the same process by hand, with what belongs upstream and what
  does not, the privacy rules, and the requirement that a gate change carries its negative
  test.

**ACTION** — install the plugin (`/plugin marketplace add KBT-0/MyAgentKit_Keel`, then
`/plugin install myagentkit@myagentkit`), then delete `.claude/skills/handoff` and
`.claude/skills/cross-review` from projects installed with v0.1. They are superseded;
leaving them means two copies of the same command, one of which no longer receives fixes.

## v0.1 — 2026-07-26

First extraction. The kit's Layer 1 (universal core), the Unity overlay and the optional
patterns were taken from a Unity + .NET multiplayer codebase written almost entirely by CLI
agents. Nothing here was designed in the abstract; every rule was paid for by real work.

Founding content, with the failure each rule prevents recorded in `RESEARCH_LOG.md`
(Backflow findings, 2026-07-26):

- Gates must be proven RED before they count, and each ships with an automated negative
  test — `core/scripts/check.sh --self-test`.
- Gates, CI and review tooling are a permanent risky area in every project's review gate.
- The cross-session state file is transient: completed work is deleted, permanent findings
  are tagged `[LESSON]` / `[GOTCHA]` and routed to a permanent home before deletion, and
  the rot gate keys on an empty "Active work" section rather than a line count.
- CLI output parsing strips ANSI escapes and never writes an extracted field as silently
  blank.
- Always-loaded documents are a recurring token bill and are kept small and stable.

Reviewed before release by TWO other models, read-only, both returning **Reject** — the
second one reviewing the first one's fixes:

- Codex CLI (gpt-5.6-sol): **seventeen findings**, five of them fail-open paths in the gates.
  Consequences worth naming: `.claude/` moved out of `core/` into `overlays/claude-code/`,
  and `scripts/review.sh` now states that it targets the Codex CLI's interface rather than
  implying vendor neutrality. Reasoning in `RESEARCH_LOG.md` backflow finding #6.
- Claude Fable 5, on the fixed tree: **eleven findings, two critical.** The remediation for
  the scanner had reintroduced the fail-open shape it fixed (`exit` inside a command
  substitution kills only the subshell), and the editor-side boundary hook read a payload
  field no tool sends, so everything written through Edit passed uninspected. Reasoning in
  backflow finding #7 — which is why `docs/REVIEW_GATE.md` now says a Reject is not closed
  by its own fixes.

Both reports are archived under `docs/reviews/` as evidence. `docs/ACCEPTANCE.md` lists what
was executed and what was not.

The first backflow from a project arrived the same day: applying these findings back to the
founding project uncovered a gate aimed at two directories that did not exist yet, which had
therefore reported PASS without reading a line since it was written. `boundary_checks.sh` and
the audit checklist now cover it (`RESEARCH_LOG.md` backflow finding #8).

**ACTION** — none. There is no earlier version to upgrade from.
