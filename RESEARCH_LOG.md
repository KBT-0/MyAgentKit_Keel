# RESEARCH LOG

Two kinds of entry live here, and they are kept apart on purpose.

**Ecosystem findings** come from `setup/RESEARCH_PROTOCOL.md`, which runs at every
bootstrap and at every project's periodic audit. Each finding is recorded with its date,
what it would change, what it costs, and a verdict — **including rejections**, so the next
pass does not spend budget re-litigating a decision that was already made. A research pass
asks "what changed since the last dated entry below?", so the dates are load-bearing.

**Backflow findings** come from projects USING the kit (`setup/INTERVIEW.md` Phase 5,
and the audit question in `docs/UPDATING.md`). A project learns something the hard way, and
the lesson belongs in the kit rather than in that one project. This section is why the kit
is not a static template.

Nothing is written here as a summary of something else. If a finding changed the kit, the
change is in `CHANGELOG.md` and the rule is in the file it governs; this log records **why**,
which is the part that gets lost.

---

## Implementation observations

### 2026-09-06 — Review tests must survive project-owned model configuration

Adopting 0.7 into an existing project preserved its configured reviewer and named model pins.
Four shared tests then failed because they treated that configured wrapper as an untouched
empty-pin template. Fixture construction now resets only the three configuration values
in its temporary copy and requires each assignment to exist. Runtime and assertions remain
unchanged. The downstream project separately exercises its actual installed defaults and legacy override
precedence through an offline CLI. This separates template-contract tests from project
configuration tests without weakening either or invoking a real reviewer.

### 2026-09-06 — A passing destructive self-test can still lose owner content (#7)

A newly reported downstream failure saved a tracked file, injected a violation, and
deleted its backup through an inherited signal trap without restoring the source. This
is a scaffold/guidance gap, not a claim that the upstream example truncates tracked files.
The workflow now requires restoration of current uncommitted bytes before cleanup and
termination after signals. A separate subshell example isolates traps and backups;
normal exit, SIGINT and SIGTERM are checked for exact bytes, mode and cleanup. Disposable
snapshots remain the preferred option for destructive probes and uncatchable failures.

### 2026-09-06 — Final review and hosted CI exercised remaining edge cases

The second and final Astra review found two confirmed gaps in the preceding repairs.
Hashing a checkout does not prove it corresponds to a requested reference if index flags
hide changes that already exist. All review scopes now reject assume-unchanged and
skip-worktree entries before provider launch. A verdict inside an otherwise empty manual
section also passed; declarations are now excluded from the remaining-check content.
Both cases have failing-before/passing-after regressions. The review-round limit leaves
review of these final repairs pending alongside blocked Claude acceptance in issue #6.

The first hosted Linux run also exposed a negative test that hit an unreadable tracked
file before the intended missing-review-test gate. Its synthetic index now reflects the
deletion. Further direct reproduction showed BSD xargs concealed grep errors as exit 1,
while GNU xargs maps grep no-match to 123. The scanner preserves grep status inside each
batch and publishes explicit match/error markers; a regression executes the actual shipped
function with matches, no matches, missing files and mixed readable/missing input.

### 2026-09-06 — Git's rendered diff is not a complete checkout fingerprint

The requested Claude follow-up was blocked by an organization-level HTTP 403. The configured
Astra fallback completed a review and exposed four confirmed failures: text conversion
could hide changed source, direct adapters could accept a review after its base reference
moved, merge commits could appear empty, and Codex could return a manual-check verdict with
no checks. Each regression failed before its fix and passed afterward. Source snapshots
now disable diff drivers, hash readable bytes as well as the resolved reference and diff,
and use the first-parent delta for merges. Final-response validation requires actual manual
checks. Fallback findings are useful evidence, but do not satisfy the owner's pending
Claude review or establish independence for code co-authored by those models.

### 2026-09-06 — Transcript approval cannot replace the final-response contract (#5)

The regression now emits an actual Codex agent-message event saying Accept and a completed
turn, while deliberately producing no final-response file. The wrapper must fail with
invalid evidence, publish no verdict, and retain the transcript only in failed diagnostics.
This directly covers the issue's false-approval trigger alongside the existing empty,
malformed and conflicting final-response cases and valid verdict controls.

### 2026-09-06 — Failed evidence is useful without being the next review's input (#4)

A review interrupted after partial output must retain diagnostic/accounting evidence,
but that archive must not become a new source change or an accepting verdict. A consecutive
timeout/success regression now checks the failed file's bytes remain unchanged, its verdict
is absent, and both attempts see identical diff and checkout hashes. This exercises the
existing archive/exclusion contract directly instead of inferring it from separate tests.

### 2026-09-06 — Repository names do not identify plugin marketplaces (#3)

The official `openai/codex-plugin-cc` marketplace manifest declares `openai-codex`, verified
from its current repository contents. The setup interview previously asked the agent to
provide install commands without stating this mismatch. Both setup and the developer
guide now show the exact pair and explain what the name after `@` refers to, preventing
repeated registration attempts when installation fails on an invented marketplace name.

### 2026-09-06 — A negative test must identify the intended failing gate (#2)

The worked boundary example accepted any nonzero exit, including an already-red baseline
and unrelated build failures. An executable test of the shipped example reproduced both
false positives before the correction. The example now verifies a clean baseline, the
nonzero exit, and the boundary's own diagnostic together. A matching message with exit zero
also fails the test. The dotfile injection is an aid for common build globs, not a promise
that every tool ignores dotfiles; project include rules must still be checked.

### 2026-09-06 — The first setup commit must obey its own review rule (#1)

Phase 4 previously ordered a commit immediately after writing gates, contradicting the
constitution installed by the same interview. Setup now stages the intended files and
hands them to a fresh reviewer, recording any unavailable review or manual checks in
STATE.md. This prevents a new project from starting with an unreviewed gate merely because
it was created during setup. The general rule is unchanged; no setup exemption is added.

### 2026-09-06 — Green review tooling still hid five reproduced failures

A fresh owner-requested Astra review of the combined local change returned Reject despite
the existing acceptance suite passing. The host reproduced all five findings. Diagnostics
could be staged in projects missing the ignore rules while the review snapshot excluded
them. Successful `{}` output was misclassified as operational failure and launched a second
model. A valid Accept line followed by a malformed Reject line became an Accept report
after rendering removed the rejection. Deleting the packaging regression still left the
acceptance gate green, and the documented upgrade list omitted an imported runtime file.

The corrections check private storage before launch and again during publication, place
temporary raw archives under the ignored usage directory, classify malformed successful
envelopes as invalid evidence, count all verdict declarations before accepting one, and
require named test suites without skips. The upgrade test reads the canonical documentation
list so a missing companion cannot hide behind a separately maintained test fixture.
These are corrections to reproduced failures, not a new independent approval. The owner
explicitly authorized push with a fresh Claude review still pending; that task-specific
exception does not change the kit's general review policy.

### 2026-09-05 — Review deadline is not an activity detector

The owner objected to cancelling productive review at ten minutes and explicitly approved
a thirty-minute total deadline as the alternative to reliable startup detection. The
current Claude adapter requests final JSON, which may remain silent while the model is
working; silence alone cannot prove that a request has not started. The shared review
default is therefore 1800 seconds, still measured from process startup, with explicit
overrides preserved. This does not claim inactivity detection. Each failover attempt gets
its own deadline; proposals retain their separate default. A mocked-launch regression was
observed rejecting the old 600-second default on both direct adapters and both dispatcher
routes before the change, without waiting thirty minutes or calling a paid model.

### 2026-09-05 — Bounded operational reviewer failover

The owner requested automatic use of the other configured reviewer when the preferred
provider cannot complete, including subscription quota exhaustion. A single-provider
failure previously stopped evidence collection despite the other selected model being
available. Blindly trying another model for every nonzero exit would instead hide stale
scope, broken evidence, or persistence errors; switching after Reject would hunt for a
favorable verdict. The dispatcher therefore uses structured adapter outcomes, not prose
matching or exit status alone. It tries each provider at most once, preserves one original
scope, and stores separate per-attempt usage plus immutable chain checkpoints. A completed
Reject is terminal. An author-model fallback supplies advisory findings, not independent
approval. This is orchestration of existing CLIs, not a new provider API or quota estimate.

The offline quota regression was observed failing on the old wrapper (exit 5; no Codex
call) and passing after dispatch was introduced. No paid model invocation was needed to
prove the transition. Live subscription exhaustion and plugin rediscovery remain manual
checks, not claims established by fixtures.

## Last ecosystem research pass

**Never run.** The kit was extracted from a working project on 2026-07-26 without a
research pass of its own. The first `bootstrap.sh` run must therefore treat every
ecosystem claim in these files as unverified and run `setup/RESEARCH_PROTOCOL.md` from
scratch.

---

## Ecosystem findings

### 2026-09-05 — Correcting role-neutral workflow claims

The owner approved correcting three overstatements in the role-neutral handoff. A skill
calling a CLI and a command calling a CLI both delegate work; the missing capability is a
Codex proposal adapter, not Claude-host review delegation. A live synthetic smoke test
demonstrates integration, not acceptance of the actual implementation. Finally, neither
co-author can provide the independent review of their combined change, and creating a
local commit does not move the review requirement from before commit to before push.
The update instructions also distinguish automatic sync from manually adopting a new
project-owned wrapper. These are documentation corrections, not new delegation features.

The owner then selected Claude as the default reviewer because Astra now authors the work.
The default changes, not the available roles or the independent-review invariant. A fake-
CLI test was observed rejecting the old default before the change, then confirms the
Claude default and explicit Codex override. No monetary review cap is reintroduced.

### 2026-09-05 — Owner-selected review budget policy

The owner explicitly requested no default monetary cap for reviews and chose to start the
pending Claude review manually. Review invocations now omit the CLI budget flag unless a
cap is explicitly supplied. Existing timeout, turn, output, accounting, and authorization
controls remain; proposal defaults are unchanged. A fake-CLI regression first rejected
the previously injected default flag and then verified omitted and explicit-cap calls.

### 2026-09-05 — Codex-host Claude delegation — ACCEPTED for owner-requested implementation

This targeted implementation check is not a full ecosystem research pass. Current Codex
skills/plugins and Claude headless structured output allow the inverse of the kit's
original Claude-host/Codex-reviewer workflow without an MCP service or runtime SDK.
Sources checked: https://learn.chatgpt.com/docs/build-skills,
https://learn.chatgpt.com/docs/build-plugins, https://code.claude.com/docs/en/headless,
and https://code.claude.com/docs/en/cli-reference. Installed interfaces: Codex 0.153.4 and
Claude Code 2.1.261. The live review and execution limits are recorded in docs/ACCEPTANCE.md.

The implementation keeps Claude read-only and returns patch proposals to the Codex writer.
Unrestricted concurrent writers, a background daemon, and an unlimited fix loop were not
implemented: they need additional ownership, isolation, and spending controls. No new MCP
server or runtime third-party package is needed. Skill discovery does not authorize spend.

The old wrapper accepted transcript-only or conflicting verdict evidence. Regression tests
were first observed failing on both conditions, then passed after strict final-message
validation. A quoted second verdict is intentionally rejected as ambiguous, not resolved
by trusting the last line. Fresh review also exposed self-test environment leakage and
absent-test evidence; their fixes are regression-tested in temporary repositories.

The owner subsequently requested per-task usage history and useful continuation when a
child exhausts quota. The real failed Claude call had already consumed tokens and reported
API-equivalent cost, so success-only accounting would hide spend. Both directions now share
a bounded process runner and a local usage recorder. Timeout preserves partial output;
subscription percentages are not synthesized from token counts or public price tables.
The follow-up review found that usage could say completed before an archive write failed,
and the shell-owned Codex diff was not validated against later checkout state. Both adapters
now archive evidence before recording completion, and use the same snapshot implementation
for scope and staleness. Negative tests reproduce archive failure and checkout mutation.
Separate tests reject omitted kit architecture guidance and raw archives entering review
scope. Captured stdout/stderr now use bounded pipes: polling the size of temporary files
was not a hard disk bound, even when returned output was truncated correctly.
Running the new Python helpers also exposed an installer assumption: bootstrap copied local
bytecode alongside source, and the acceptance fixture then tried to decode it as text.
Bootstrap now skips Python bytecode; a synthetic binary-cache test was observed failing
before the correction and passes afterward. Bytecode is also ignored in both checkouts.
Official usage semantics were checked at https://learn.chatgpt.com/docs/pricing and
https://code.claude.com/docs/en/costs. Those values are not a per-call subscription debit.
Publishing raw account diagnostics was rejected; local ignored JSON retains the evidence,
while public acceptance notes carry only deliberately scrubbed conclusions.
The official Codex app-server `account/rateLimits/read` method provides supported account
window percentages and plan labels without starting a model turn. A live read succeeded;
the adapter uses bounded optional observations rather than scraping credentials or calling
undocumented endpoints. Before/after account observations are not per-invocation debits.

A live Codex run exposed a large-stdin deadlock in the new polling runner: after a short
`communicate()` timeout, retrying with no input could strand the unread remainder. A slow
child and a 200 KB input reproduced the failure before the fix. The shared runner now gives
the child a complete temporary stdin file and monitors its process, not partial pipe writes.

---

## Backflow findings

### 2026-10-07 — the cross-model review of the native Windows change

The first version of the 2026-10-06 change (below) went to a cross-model review, which
rejected it with three High and five Medium findings. Each fix was written as a test first and
watched going red against that first version; then each new guard was deleted in turn and its
test watched going red again. `CHANGELOG.md` v0.10 records what changed.

**The nested-run proof compared a truncated file id.** The proof read the lock file's identity
from `os.stat`, `(st_dev, st_ino)`. Before Python 3.12, `st_ino` on Windows held 64 bits of the
file id, and Microsoft does not promise those are unique on ReFS. A writable handle on another
file whose truncated id matched passed while the real lock was held, and the seams turned on.
The proof now reads `FILE_ID_INFO` through `GetFileInformationByHandleEx` for the inherited
handle and for the lock path, and compares all 24 bytes (the volume serial and the 128-bit
id). When the volume gives none, the nested run fails `FAIL [lock]` by name: an identity that
cannot be read is not proven. The fresh open for writing must also fail with a sharing
violation (error 32), not any permission error, because a read-only lock file or an access
rule would refuse it with nothing holding the lock. The test fakes the truncated identity by
making `os.stat` report one `(st_dev, st_ino)` for every file and runs the gate's own proof
code, cut out of `check.sh`: red on the first version, green now. Another fakes a volume with
no `FILE_ID_INFO`.

**`cygpath` changed POSIX behaviour by being on PATH.** The lock path was converted whenever
`cygpath` existed. On Linux or macOS with a shim or a stray install, the converted `C:/` path
is relative to POSIX Python, so the nested run no longer knew its own lock. Only a host whose
`uname -s` names MSYS, MINGW or Cygwin converts it now. The new self-test case puts a fake
`cygpath` that records its call on PATH: on WSL it went red with the first version's line and
green with the fix.

**The Windows lock had no negative test a project receives.** Its cases lived in a kit-only
test file, and the reparse-point guard printed NOT RUN and passed on a host without the
symlink privilege, so deleting the guard left that host green. `check.sh --self-test` now runs
four Windows cases, each against a copy of the gate in a throwaway repository so its lock is
not the one the self-test holds: a writable handle on another file, a read-only handle on the
held lock file, a write handle while nothing holds the lock, and a reparse point at the lock
path. The reparse point is not a symlink: a reparse point with a non-Microsoft tag can be set
by any user on a file of their own (measured on Windows 11 without Developer Mode, where a
symlink failed with WinError 1314), and the guard tests the same attribute bit. Each of the
four guards was deleted in turn in a bootstrapped project, and only its own case went red. A
case that cannot run is a FAIL there, never a skip.

**Three ways a changed LFS file reached a review.** All three came from deciding which paths
are filtered by the current checkout alone. (1) An uncommitted review never looked at the
index: a different pointer staged for an LFS file, with the working file put back to HEAD's
content, passed every check, and the commit that followed carried an object nobody reviewed.
(2) A commit that deleted an LFS file, renamed it to a name the filter does not cover, or
removed its attribute while changing it, left no filtered path in the checkout, and the range
was reviewed from its pointer-side diff. (3) Raw bytes equal to HEAD's blob did not prove what
Git renders: with a clean driver configured after the commit (one that deletes a line), `git
diff HEAD` claimed a deletion the copied file did not show. The 2026-10-06 entry's sentence
that hiding "can only happen to a path whose raw bytes differ from what HEAD records" was
wrong for exactly this case. Now: the candidate names are the checkout, the index diff
against HEAD, the working-tree diff against HEAD and the reviewed range, deleted and
renamed-away names included; attributes are read in the working tree and, through a
throwaway index (`read-tree` then `check-attr --cached`, so no newer git is needed), at each
end of the range, HEAD for uncommitted work; a filtered name any of those diffs changes is
refused. A filtered path nothing changes passes only when HEAD records a canonical LFS
pointer, its raw bytes are that pointer or the content it names by sha256, and Git's rendered
diffs, which run the filter, do not name it. The rendered check and the pointer restriction
each have a case the other does not catch: a stat-clean file Git renders as unchanged, and a
pointer whose content matches while the configured driver renders something else. The test
fixtures name their driver `fakelfs`: a host's global `filter.lfs.process` from `git lfs
install` replaces a test's `filter.lfs.clean`, and the first run of the rendered case passed
for that reason alone.

**A second review pass** found three more gaps, each fixed with a case watched red first. A
`.gitattributes` rule staged together with the pointer it makes, while the working tree and
HEAD held neither, was filtered nowhere the bridge looked; the index's own attributes
(`check-attr --cached`) are now read too. The proof's "sharing violation, not any refusal"
condition had no case: a lock file made read-only refuses a fresh open with access denied
while a claimed writable handle on it still writes, and accepting any refusal turned that
claim into the lock. And several Windows guards were proven only in the kit's own test file,
which projects never receive: `--self-test` now also fakes a file id equal to the lock's in
its volume and first 64 bits (the proof's own code runs with GetFileInformationByHandleEx
replaced), fakes a volume with no `FILE_ID_INFO`, kills a gate with `kill -9`, and kills the
lock holder while its gate runs. In a bootstrapped project each guard was deleted in turn and
only its own case went red, with one exception: the killed-holder case cannot be isolated,
because a holder that does not hand its handle to the gate fails every gate run `FAIL [env]`
before any case runs. The upgrade checklist now lists the exact native Windows transcript,
`skip` lines included, so an owner can tell an expected line from a failure.

**A third review pass** found two cases that asserted less than their names. The killed-gate
case covered only the holder's signal branch: a holder that turned every ordinary status
below 256 into 0 still passed it, and a failing build then reached git as a pass. A new case
makes the gate copy exit 3 right after it takes the lock and requires the holder to exit 3;
with that branch broken it went red (and the broken holder also turned the whole self-test's
own exit status into 0 while it printed `SELF-TEST: FAIL`, which is why the case exists). The
no-`FILE_ID_INFO` case matched the diagnostic only, so a proof that printed it and then
trusted the claim anyway passed; it now also requires the proof to exit 3, and deleting that
`sys.exit(3)` turned it red.

**`review.sh` on native Windows: measured, not fixed.** The review asked for `agent_process.py`
to tolerate a missing `SIGHUP` so that the self-test's review case runs on native Windows. With
`SIGHUP` made optional, 121 of the 137 review tests still failed there (163 of the errors were
`pthread_sigmask`): the adapters block signals with `pthread_sigmask`, wait with `sigpending`
and `sigwait`, start the reviewer in its own session and kill its group with `killpg`, and the
tests create symlinks and FIFOs. The filter tests above passed there. A Windows design
(job objects, console control events) is its own task for review tooling, so v0.10 says in its
upgrade checklist that native Windows has partial acceptance and the full self-test runs from
WSL or another POSIX shell.

**The upgrade checklist stamped after its commit.** It said to commit and then run
`sync-kit.sh --actions-applied`, which writes the tracked `docs/kit/.kit-version`: the stamp
was left uncommitted and every other clone read v0.9. The stamp now comes before the one
upgrade commit. The release is v0.10, not v0.9.1: the changelog defines versions as
`MAJOR.MINOR`.

**A fourth review pass: a message is not an outcome.** Six of the Windows lock cases (another
file, read-only handle, nothing holding, read-only lock file, reparse point, killed holder)
matched their message and ignored the exit status. A guard that printed its refusal and then
carried on still passed: `cannot_open()` without its `sys.exit(1)` printed `FAIL [lock]` for
the reparse point and then ran the gate, and the wait without its `sys.exit(75)` printed
`NOT RUN [lock]` and then took the lock once the first gate ended. In the throwaway repository
the carried-on gate then failed on project files it lacked, so its status looked like a
refusal too. Each case now asserts its exit status (1, or 75 for the killed holder), the
gate's copy exits 0 right after it holds the lock, so carrying on past a guard is a pass that
fails the case, and a claimed run waits 2 s at most, so a lost claim refusal ends instead of
waiting forever. Proof, in a project bootstrapped on native Windows, each mutation on its own:
against v0.10's earlier self-test both mutations left every lock case `ok`; against this one
each turned exactly its own case red, and deleting the claim refusal's `fail=1` turned three
of the four claim cases red (the fourth, the read-only lock file, is refused by the lock open
itself).

**CRLF on a Windows clone.** Git for Windows installs with `core.autocrlf=true`, which checks
every text file out with CRLF; `sh` reads `#!/bin/sh<CR>` as a bad interpreter and
`set -eu<CR>` as an invalid option, so on such a clone the gate, the hooks, `doctor.sh` and
the kit's own `sync-kit.sh` could not start, and the upgrade checklist sent the owner to run
them. A `.gitattributes` rule `*.sh text eol=lf` (and one for each of the gate's hooks)
overrides autocrlf per path, so bootstrap installs one and the kit carries one. Proof: a bootstrapped
project and the kit itself, each committed and cloned with `core.autocrlf=true`, checked
their scripts and hooks out with CRLF without the rule and with LF with it (a Markdown file in
the same clone proves the conversion was in force). An existing clone does not heal on pull:
git does not check out again a file the pull did not change. So the upgrade's first item adds
the rule, rewrites each script and hook without CR, and then renormalizes the index. The order
matters: renormalized first, the rewritten files kept their CRLF size in the index's stat
data, and `git status` listed every one of them as modified with an empty diff (git treats a
size change as a change without reading the content). The test runs the checklist's own
snippet on a CRLF clone of a v0.9 project and was red without the rewrite, without the
renormalize, and with the first draft's order.

**`spawn_worker.sh` on native Windows.** The kit's copy knew only tmux and stopped with `tmux
is not installed`. A project that moved to Windows wrote its own Windows Terminal branch and
found two faults on its first run, each of which left the tab with an error and no worker: a
bare `bash` in a new tab is WSL's launcher (`WindowsApps\bash.exe`), and `wt.exe` splits its
command line at every `;`, quoted or not, which cut the instruction in two (`error
0x80070002`). The kit's branch runs Git Bash by its full Windows path and escapes every `;`
as `\;`. The test drives the branch through a launcher stub that splits and resolves the way
`wt.exe` does, with a `;` in the brief path and in a value: it was red against the tmux-only
script, with a bare `bash`, and with the escape removed. `doctor.sh` asked for tmux there,
which that host cannot run; it asks for `wt.exe` instead.

**The two Low findings, fixed.** The filter refusal's changed-name queries did not carry the
scope's exclusions, so a modified, filtered review archive refused a review whose scope never
held it; the queries now carry them (the new test errored on the earlier code). The refusal
said "the review changes it" also for a path the review does not change but that is not a
proven unchanged LFS file, and told the owner to remove an attribute a historical path no
longer had; it now says which of the two applies, and that the attribute is to be removed
only where the checkout still has it.

**A fifth review pass, on all of the above.** It rejected the round with three High and one
Medium finding, each fixed once more:

- *Bootstrap left a project's own `.gitattributes` alone.* An existing repository with owner
  rules kept them and got no line-ending rule at all, while bootstrap succeeded and stamped
  the version; `--force` would have replaced the owner's attributes whole. Bootstrap now
  appends the rules the file lacks, never replaces it, and adds nothing a second time; a
  `.gitattributes` it may not write (a symlink) stops it like a gate file. The clone test now
  also bootstraps a project with its own `.gitattributes`, twice, the second with `--force`;
  it was red against the earlier bootstrap.
- *The lock was picked by whether `import fcntl` worked.* Python searches the checkout and
  `PYTHONPATH` first, so a `fcntl.py` there sent native Windows down the POSIX path, and a
  stand-in that always "locked" let two gates run; a `secrets.py` or `ctypes.py` there ran
  inside the holder. The host (`os.name`) now picks the lock and both lock programs run with
  `python3 -I`. Two shipped cases: on every host a nested run with a stand-in `fcntl.py` on
  `PYTHONPATH` must pass without importing it (red on WSL with the probe's `-I` removed, and
  on native Windows with the earlier lock programs), and on native Windows the holder must
  import neither a stand-in `fcntl.py` nor `secrets.py` (red with the earlier programs, and
  with only the holder's `-I` removed). Two kit checks had simulated a Python without `fcntl`
  and a lockless or NFS file system with a `sitecustomize.py` on `PYTHONPATH`, which `-I` now
  ignores; the full kit check caught both, and they now put their stand-in into each `-c`
  program through a `python3` on `PATH`.
- *The CRLF rewrite trusted every path it was given.* The loop wrote through a temporary at
  a fixed name (an owner's `x.sh.lf` was overwritten and deleted), followed a tracked symlink
  out of the repository, deleted a lone CR along with the line ends, split names at a newline,
  and treated every file in `.githooks` as text. The snippet now reads `git ls-files -z`,
  rewrites regular files in place with Python, replacing only CRLF, and the rule names the
  gate's four hooks. Red against the earlier snippet: the newline name stayed CRLF, the lone
  CR was gone, and the file behind the symlink was rewritten.
- *`git add --renormalize .` restaged unrelated files* whose blobs predate an owner's text or
  filter rule, and they went into the upgrade commit. It now renormalizes only the files the
  rules name; the test holds a CRLF `notes.txt` under a later `*.txt text` rule, which the
  earlier snippet staged.

Two Low findings were fixed too: `doctor.sh` takes `KIT_WT` as `spawn_worker.sh` does, and
the overlay README and the script's header say what does not apply on native Windows.

**A sixth review pass** confirmed those fixes and left two findings.

- *Ctrl-C, the review said, reached the gate and its build as ignored,* because the holder set
  `SIGINT` to `SIG_IGN` before it started `sh`, and a Windows process's ignored Ctrl-C is
  inherited. Measured on Windows 11 with CPython 3.13 and Git for Windows' `sh`, it was not:
  CPython's `SIG_IGN` installs the C runtime's console handler, not the inherited
  `SetConsoleCtrlHandler(NULL, TRUE)` flag, and a native grandchild under a `SIG_IGN` parent
  was interrupted. Even that flag set in the holder did not reach the build, because `sh`
  starts with Ctrl-C enabled again. The holder now installs a handler that does nothing
  anyway, so the gate's behaviour no longer rests on either fact. The new self-test case gives
  a copy of the gate a hidden console of its own, with that console as `sh`'s input as a
  terminal window does, waits until its build (a native Python) sleeps, and sends
  `CTRL_C_EVENT` to that console, the event Ctrl-C raises there; a signal sent by pid reaches
  one process, not the console's. The gate must exit nonzero within 10 s, the build must have
  ended, and the next gate must take the lock. The case passed against `SIG_IGN`, against the
  flag set in the holder, against `trap '' INT` in the gate, and against a holder that starts
  `sh` in a new process group. It was red when the holder starts `sh` detached from the
  console: the gate ran on, the build ran on, and the next gate waited out its
  `GATE_LOCK_WAIT`. The process that runs the case clears an ignored Ctrl-C it may have
  inherited (an agent's shell had one), since a terminal's user has none.
- *The self-test's host check imported ambient Python customization.* It ran `python3 -c`, so a
  `sitecustomize.py` on `PYTHONPATH` that called the host POSIX, or stopped the interpreter,
  sent native Windows to the POSIX `skip` line, and all the Windows lock cases were bypassed
  with no `FAIL`; the case runner imported it too. Both now run `python3 -I`, and the self-test
  runs them beside a `sitecustomize.py` that marks its import and calls the host POSIX. On
  native Windows every case must run and the marker must not be written; where the cases are
  skipped, a written marker is a `FAIL`. Red with the host check's `-I` removed (the cases were
  skipped and the import failed the self-test) and with the runner's `-I` removed; the v0.10
  head beside the same `PYTHONPATH` printed the `skip` line and no `FAIL`.

### 2026-10-06 — native Windows: the gate lock, and Git LFS beside a review

A project moved from WSL to native Windows (Git for Windows' `sh`, CPython from python.org).
Every commit there was blocked, and `review.sh` refused every review. The kit's own note that
only Linux under WSL had ever been tested marked exactly where it broke. Each fix below was
written as a test first and watched going red against v0.9; then each guard was deleted in
turn and its test watched going red again. `CHANGELOG.md` v0.10 records what changed; the
cross-model review of this first version (2026-10-07, above) changed four parts of it.

#### The gate lock without fcntl

Windows Python has no `fcntl`, so v0.9's gate printed `FAIL [lock]` on every run. The fix
had to keep what the POSIX lock guarantees: the operating system releases the lock when its
holders die, nothing is reclaimed, no pid is trusted, a second run waits, and a nested run
proves it holds the lock rather than claiming it.

`msvcrt.locking` was rejected. Its byte-range lock belongs to the one process that took it,
and Windows releases it when that process ends. A gate whose holder was killed would let the
next gate build beside the build still running, the failure the v0.9 flock lock was built to
stop. The lock is a share mode instead: the holder opens the file for writing and shares it
for reading only, so Windows refuses every other open for writing while any handle of that
open exists. The holder makes its handle inheritable and runs the gate as its child; every
process the gate starts inherits the handle, and the lock lasts until the last of them exits.
A test kills the holder while its build runs, and two waiters still build one at a time; with
the handle kept from the children, both waiters failed on "File exists".

Measured on the host before the design was fixed: an inheritable Win32 handle keeps its
number through Git for Windows' `sh` and a nested `sh` into a native Python. `os.execv` on
Windows starts a new process and exits, so the holder cannot exec as on POSIX; it waits for
the gate and passes its status on. Git for Windows reports a child killed by signal N to
native Python as N << 8, and a native exit status of 2304 reaches `sh` as 0. Passed on as it
was, a gate killed with `kill -9` reported a pass; it now exits 128 + N.

The nested-run proof. A descriptor number does not cross from MSYS to native Python, so a
random token in the lock file was the first idea. A token alone has the weakness the third
cross-model round of v0.9 found in the pid: copied out of a killed gate whose build still
runs, it matches the file. The proof is the handle, which a copied variable cannot carry.
`GATE_LOCK_FD` holds the holder's handle number. A nested run accepts it only when that handle
is open in its own process on this lock file (volume and file id; since 2026-10-07 the whole
`FILE_ID_INFO`), can write (`fsync` needs
write access), and a fresh open for writing is refused. While the holder has the file open
without write sharing, no other handle with write access can be opened, so only the holder's
handle and its inherited copies pass all three. Three tests hand the gate a handle that fails
exactly one condition: one on another file, a read-only one on the lock file, and a write
handle that shares writing while nothing holds the lock. With its condition deleted, each
turned a red build green. The token stays as the self-test marker, the role the pid has on
POSIX: the gate cannot learn the holder's process id as its own `$$`.

Three smaller traps on the same host. A native program receives `/d/x` as `D:/x`, so
`GATE_LOCK_HELD` came back from Python in another form; the nested run did not know its own
lock and waited for itself. The lock path is now kept in the `C:/` form (`cygpath -m`, on a
host whose `uname -s` is MSYS, MINGW or Cygwin since 2026-10-07; first, wherever
it exists). Git for Windows prints a linked worktree's git path as `C:/...`, which the gate
read as relative. Output to a pipe is in the ANSI code page, and a path outside it (a user
name, or the U+F03A that cygpath makes of a colon) ended the waiting NOTE in a traceback.

Not proven here at first (proven since 2026-10-07 with a reparse point any user may set):
the refusal of a symlink at the lock path (creating one needs a privilege
the host lacks, and the test says NOT RUN), and the lock on macOS.

#### Git LFS and the filter refusal

v0.9 refused a review scope "with an effective clean or process filter". The check ran
`git check-attr filter` over every tracked and untracked file in the checkout, not over the
paths the review changes. It counted a driver as effective when any `filter.<driver>.clean`
or `.process` key is configured, and `git lfs install` writes both into the global
configuration. So in a repository with one LFS path anywhere, every review was refused, a
two-line code fix included.

Why the refusal exists (v0.9, #12): Git runs a clean filter on working-tree bytes before it
diffs them, so a filter can drop lines or a whole file from the reviewer's payload while the
fingerprint still hashes the raw bytes. (Corrected 2026-10-07: the next sentence is wrong
for a filter configured after the commit, and the proof below is now narrower.) That can only
happen to a path whose raw bytes differ
from what HEAD records. A filtered path therefore passes only with a proof, taken without
running any filter, that its working bytes are exactly what HEAD records: they equal the
blob's bytes (an unsmudged checkout), or the blob is a Git LFS pointer and the file has the
pointer's size and sha256. With that proof the working-tree diff has no change of that path
to omit, and the fingerprint, which hashes the same raw bytes, attests the state the reviewer
saw. The proof does not trust the filter's name or command: a driver called `lfs` that does
something else gains nothing, because only the raw file's sha256 is compared.

A filtered path the review changes stays refused. Uncommitted, its bytes differ from HEAD and
the proof fails. In a `--commit` or `--base` range the checkout matches HEAD, but the commit
diff names the path and would show its pointer, not its content. Excluding such paths and
naming them in the evidence was the alternative; code-only reviews did not need it, and it
would add a second kind of scope.

Proof: the new test is red on v0.9 (refused on an unchanged LFS file beside a code change).
Deleting the proof, the sha256 comparison, the blob-bytes case or the commit-range check each
turned it red. Against real git-lfs 3.7 under WSL: a code-only change beside a 200 KB `.tif`
was reviewable, a changed `.tif` was refused, a `--commit HEAD` that changed the `.tif` was
refused, and the next code-only commit was reviewable. Cost: each filtered path is read and
hashed once more per review.

#### What native Windows still breaks

Found while running the kit's own tests and acceptance on native Windows, and left for
separate work. The kit check imports `fcntl` at the top and cannot start. `agent_process.py`
reads `signal.SIGHUP`, so the review adapters fail on import, and with them the review case
of the gate's `--self-test`. Git for Windows' default `core.autocrlf=true` checks the kit's
scripts out with CRLF, which `sh` cannot run, and the kit ships no `.gitattributes` that
pins them to LF. (2026-10-07: v0.10 ships one; see the entry above.)

### 2026-10-03 — kit hardening from two projects' unreported findings

Two projects using the kit were mined for failures nobody had filed (their session
transcripts, gotcha files and review records). Their findings, filed as issues, and older open
issues were fixed by nine work packages in this version. Each fix below was written
as a test first and watched going red against the old code; where a test pins behaviour the
old code already had, it says so. The entries record why; `CHANGELOG.md` v0.9 records what.

#### Concurrent gate runs and in-tree self-test injection (#19, #20, #11)

Several sessions share one checkout, and the Stop hook, the commit hook and manual runs
overlap. Two runs shared a project's fixed build directory and one reported FAIL for a tree
that passes alone; a self-test's marker file written into the tree failed a concurrent gate
and a concurrent commit. The fix is a per-checkout lock (a lock rather than a per-run build
directory, because the build directory lives in the project's build command, out of the kit's
sight) and injection from outside the tree. Proof: the kit self-test records `git status`
from every nested gate run (red on the old injected file) and runs two gates over one build
directory (red: "File exists"). The first lock design passed its own tests and a fresh review
found five holes: an unbounded wait gets killed by the Stop hook's timeout with no result
(now bounded, exit 75); inheriting the lock had no red test (dropping the export hung the
kit check, so every gate call has a timeout and the self-test runs under a 5 s bound); a
1 s grace for an empty pid file reclaimed a live holder (the lock is now a symlink whose
target is the pid, which has no empty window); unconditional cleanup removed a lock a reclaim
race had handed on; a bare inheritance flag leaked into gates in other checkouts. A lock is
not tested until its release, its inheritance and a bounded wait each have a case that goes
red. Cost: a commit during a long self-test waits for it.

#### Scanner failures that were not scanner failures (#13, #14)

The scan list is tracked plus untracked non-ignored paths. Two ordinary states put a path
into it that grep cannot read as a file: a tracked file deleted with plain `rm`, and a
directory symlink (`node_modules` linked into a clean-checkout worktree, which
`node_modules/` does not ignore). Both ended in "a scanner failed to run", so the person
debugged the tooling instead of the tree. The gate now sorts the list first. A missing tracked
path still fails, because the commit may still carry it, but names itself and the fix; a
directory symlink holds nothing git tracks and is skipped with a line. A real grep failure
keeps its old message. Proof: both cases red on the old `check.sh` ("a scanner failed to
run"), and the second red again with only the #13 half applied.

#### Review tooling that failed open (#12, #9, #8)

(1) Automatic failover replaced the requested reviewer, often with the patch's author, while
the record still looked valid; an outdated CLI rejecting a sandbox flag triggered it on every
run. (2) Git applies clean filters before diffing, so the payload could omit lines the
fingerprint still hashed. (3) SIGTERM and SIGHUP skipped cleanup, so paid reviewer processes
kept running; a test-count guard and empty boundary self-tests also let a check that never ran
count as a pass. Failover is now opt-in and marked in the evidence, filtered scope is refused,
a cancel kills the reviewer's process group and records `cancelled`, and a suite with fewer
tests than its minimum fails. Proof, each red on the old code: the old failover exited 0; a
filtered scope raised nothing; the process group outlived SIGTERM and SIGHUP (orphans in `ps`)
and SIGINT left no usage record; an emptied suite and a boundary self-test that ran nothing
both printed PASS. The review round found that an unconditional handler overrode a signal the
caller had set to ignore, so a `nohup` review was cancelled when its terminal closed; the
handler is skipped for an ignored signal. Blocking signals around `Popen` was rejected: the
mask survives `exec`, so the reviewer CLI would start with them blocked. A signal inside
`Popen` itself, and SIGKILL, can still orphan the reviewer. The lesson: a substitute, a
rendering or a skipped run must never be evidence for the real thing.

#### A review loop that never converged (#18)

In a project using the kit one medium-size change went through more than ten cross-model
rounds, each a Reject with two or three new, mostly Medium findings, increasingly in code the
previous fix had written. The prompt asked for no exhaustive pass, no severity and no fix
direction, and each round was blind to the earlier ones, so disproved or deferred findings
came back. The prompt now asks for all three and carries earlier rounds from the reviewer's
own archive, not from the author. `stale_checkout` was examined and kept: a reviewer that
read a changing tree cannot be tied to its diff; only its message changed. The first cut
broke the review gate's invariant, which the fix review found: the author's disposition
"answered" a finding, so every finding could be marked deferred and the reviewer could
Accept. Dispositions are now claims to verify, a deferred finding blocks a plain Accept, and
the closing Accept comes from a fresh label with no carried context. Matching on the label
alone also let a reused label carry another change's rounds, so scope, reference and head
ancestry must match; the carried text counts toward the diff budget; carried verdict lines are
renamed so the exactly-one-verdict check cannot trip on an echo. Proof: each point red on the
old prompt or code, and the two pinned behaviours by mutation. The owner's idea that only High
and Critical findings should block from round three, with the reviewer's completeness claim
recorded, is a gate-policy and schema change and is not made here. Four live Claude checks
for #6 still await the owner (`docs/ACCEPTANCE.md`).

#### The sync stamp (#15)

`sync-kit.sh` stamped the new version right after printing the changelog, so the stamp meant
"files copied", not "hand edits applied". A project using the kit sat at v0.5 with the v0.6
and v0.7 ACTIONs never applied; a later sync to v0.8 stamped it current, and from then on the
sync said "already current" and the pending work was invisible. Now the stamp advances past a
version only when it has no ACTION items or the owner passes `--actions-applied`; until then
every sync reprints the items and exits 2. Chosen over a per-version applied marker checked
by the gate: one flag and the existing stamp need no new state file. Proof:
`tests/test_sync_kit.py` (red on the old script: stamp moved to 0.2 unconfirmed). A "none"
line must not count as pending, or every sync would block on it; that was a review nit.

#### Gates that did not gate, or hid their failure (#16, #24, #23)

(1) A clean `git merge` runs `pre-merge-commit`, not `pre-commit`, so two green branches
merged into a red tree that nothing gated; proved by a real merge in a synthetic repository.
(2) A project filtered its build output to lines matching "error"; that cut away the "In
function / required from / note:" lines, and a failure seen only in CI had to be fixed
without them. The kit's own script had never filtered; the filter was a local edit made for
quiet output. The kit now gives the quiet output itself (nothing on a pass; on a failure the
tail and the path of the full log, the whole log on CI where the file dies with the runner),
so nobody has a reason to filter. A deploy-shaped build command, a dry run included, was
refused by an agent permission layer and made the gate unrunnable for the agent; the kit now
says to keep it out. (3) The coding tool's default co-author trailer reached most of a
project's commits despite the owner's rule, and removing it meant rewriting history; a
document did not hold, so a hook does. The first hook matched tool names as substrings and
rejected humans ("Claude Monet", "Ana Raider", a domain containing "cursor"), missed newer
tools, `[bot]` and non-co-author forms, and read the `commit -v` diff that git strips only
after the hook. It now strips comments and the scissors section, rejects a name only when it
is wholly tool or model words, a vendor's address or a `[bot]`, and is the owner's choice,
keyed on the `AGENTS.md` rule line; a missing `AGENTS.md` is a broken setup, so the hook
stays on. Proof: sixteen hook cases red on the first cut, the merge, build-output and
owner-choice cases red on the old code. Open: the vendor-domain rule also rejects a human at
a vendor, and a custom `core.commentChar` is not handled.

#### Effort, STATE operation files, doctor.sh, closing a worker (#17, #21, #10, #30)

(1) Sub-agents silently inherit the lead's effort. A side-by-side comparison was skewed and
only grepping transcripts showed it, so agent definitions pin `effort:`. (2) `STATE.md`
reached 38 KB because a non-empty "Active work" kept the rot gate quiet, and a 10 KB cap then
fired three times in a day on one bullet; the answer is operation files with pointer lines,
not a byte cap (the kit gates on lines). (3) Gates failed for machine reasons: hooks path
unset, an older node on the hook PATH (nvm lives in rc files), missing exec bits. Each looked
like a code bug, so a read-only `doctor.sh` runs at session start. (4) A pilot worker sat idle
for 40 minutes after writing its result, because the idle notice also fires on background
parks; the result file is the end signal and the lead closes the session. Proof: each doctor
trap has an injected-trap test, red against a missing or sabotaged check, and the rot message
test red on the old text. The review found that `doctor.sh` read `toolchain_path` as text, so
the documented `"$HOME/..."` form gave a false MISSING (the line is now evaluated, and the
test uses the documented form); that a "read-only" check must not call `npm config get`,
which writes logs and directories; and that the interactive-shell probe needs a bounded wait.
Not tested: its node, npm and real-CLI branches.

#### Rules from the transcripts (#26, #27, #28, #31)

(1) Research sub-agents put the owner's e-mail into User-Agent headers, up to thirteen
requests each; personal data in a third party's logs cannot be recalled. (2) Worktree-isolated
workers lost about 177 turns in 40 transcripts to refused compound shell commands. (3) Eight
sub-agent writes of a report file were refused because rule 7 told them to write one, so the
report ended up in the final message anyway. (4) A gate failure that passed on re-run left no
trace in four recorded occurrences. The rules went into `WORKFLOW`, `HANDOFF`, `GOTCHAS` and
the worker definition, not `AGENTS.md`, which is always loaded. The doctor additions came
from the same projects: a checkout under `/mnt/<drive>` on WSL (CRLF scripts, Windows-native
binaries, a much slower gate) and `node_modules/` with a trailing slash not ignoring a
symlinked `node_modules`. Proof: the doctor traps red against the old script, each check
disabled in turn. The rules are text and have no test.

#### Self-test seams were a bypass (#25)

`check.sh` read override variables so its self-test could point gates at synthetic inputs,
and its comments said "nothing else sets it". Nothing enforced that:
`GATE_BUILD_CMD_OVERRIDE=true git commit` skipped the build and passed, and a state or
boundary file variable redirected or emptied a gate. A project using the kit found the same
in its own gate independently and recorded "Environment overrides must not disable mandatory
gates". The fix fails closed with the variable named, not a silent unset: a silent unset
leaves the person who exported it believing a run checked something it did not. Seams are
honoured only under a marker bound to the live lock holder, so a copied variable alone does
nothing; the review renamed the generic names with a `GATE_SELFTEST_` prefix. Rule: every
test seam is an input to the gate, so it either fails closed outside the test or it is a
bypass, and a new seam joins the list in the same change. Proof: each seam exported into a
normal run, a top-level `--self-test` and a run with a copied marker exits 1 with its name;
the old gate printed `CHECK: PASS` with the build set to `false`. Not shown going red: the
in-gate case on its own (the old code fails with `[build]`, not `[env]`). A deliberate forgery
of lock and marker still works.

#### Two lead fixes, and what is still open

`spawn_worker.sh` now `cd`s before starting the tool, because tmux hands a new session a stale
`PWD`, so the tool could start in a stale directory. `spawn_worker.sh --worktree` starting from a
stale base is still open (#32), as is the test that times out at 5 s under load (#29).

#### A fallback that became an override

The kit's own cross-model review failed twice with "the model requires a newer version of
Codex" on a machine whose CLI was current. The wrapper prepended `~/.local/bin` to PATH to
reach per-user installs from a non-login shell, and an old standalone build left there won
over the current binary. The failure text pointed at the model and the CLI version, not at
the path, so the first reading was "the pin is stale". Rule: a directory added for a tool
that MAY be missing goes to the end of PATH, never the front, and the message that names
a version is checked against `which -a`. Proof: a regression with a current fake on PATH
and a stale fake under `$HOME/.local/bin` fails on the old wrapper and passes on the new.

#### A second model on the hardened diff

A cross-model review of the whole v0.9 diff, run through the kit's own `review.sh`, came
back Reject with five High findings in code that eight fresh same-vendor reviews had already
passed: two waiters could both reclaim one stale gate lock and the late one deleted the lock
the early one had just taken; a pid reused after a reboot held the lock forever; the
commit-msg hook took an unreadable `AGENTS.md` for the owner allowing credit, stripped `#`
lines that git keeps under `-m` or `verbatim`, and missed vendor-prefixed "Generated with"
lines; review rounds matched on the literal reference text, so `--commit HEAD` carried one
commit's review into the next, and archives were trusted by location alone; `doctor.sh`
passed a script missing from the index and ran its shell probe unbounded without `timeout`.
A third round on the fixes found the reclaim-by-rename still let three waiters interleave,
a gate killed with SIGKILL left its build running under a reclaimed lock, a failed rename
spun past the wait bound, and pid identity rested on a command-line substring: every one
lived in reclaim code that existed only because a pid lock outlives its owner. The owner
chose to remove the cause: `flock(2)` through Python's `fcntl`, held by the gate and
inherited by every process it starts, released by the kernel when the last of them exits.
Proven red on the symlink lock (three waiters each failing on the shared build directory
behind a SIGKILLed gate) and green on flock. Known cost: a long-lived build server inherits
the lock. The same round found more fail-open paths that the earlier tests could not reach
because every test built only the passing shape: the hook cut at any scissors line though
git keeps one under `-m`, and matched trailers only at the start of a line though git keeps
`# Co-Authored-By:` under `-m`; both adapters re-resolved the reference after the paid run,
so a deleted branch lost the usage record; `prior_rounds()` skipped unreadable records;
`sync-kit.sh` read an awk failure as "no ACTION items"; `doctor.sh`, the read-only check, ran
`$(...)` from a configuration line through `eval`; `pre-commit` reported "did not run" as
"failed". Other fixes: the hook checks comment lines whatever git would do with
them (fail closed; the false positive, a commented-out credit left by a squash, is one line
to delete); rounds are bound to the resolved reference, the head and the archive's sha256.
Each was watched red first. Lesson: every check that compares by name (a reference string,
a path, a pid) needs the identity the name stood for when it was recorded; and a second
vendor's reading is not a formality, it found what five same-vendor rounds did not.

#### Third cross-model round: a pid was still being trusted

A gate killed with SIGKILL leaves its pid in the lock file; variables copied from it matched
that pid, so a build override reported PASS with no build. A claim to hold the lock now
needs the inherited descriptor, which a copied variable cannot carry (red: SIGKILL holder,
then a copied-variable run that passed). The scissors header could be reproduced with `-m`,
so the hook cuts nothing and takes the `commit -v` false positive, failing closed. The same
round found an alphanumeric comment character, malformed usage dicts, a `python3` that only
`toolchain_path` provides, a doctor probe whose grandchild held the pipe for a minute, and a
Stop-hook branch with no test; each has a test seen red on the old code. The round also
carried the previous round's findings into its prompt and returned a disposition table for
all fourteen: the carried-round path of issue #18 was proven on the kit's own review.

#### Fourth cross-model round: a guard right for the reported shape misses the next one

The fourth round (no High, eight Medium, two Low) was all residue of earlier fixes: the
hook handled `commentChar` but not `commentString`, `Key:` but not `Key :` or a folded
value; the sync's trap cleaned up but did not exit; the adapters hashed the archive by
reopening it. Two test-quality lessons came with it: a stand-in that does not enforce what
it replaces proves nothing (a `timeout` fixture that only ran its command), and an early
return under uid 0 is a silent pass; prefer a failure every uid hits (a directory where a
file is expected), and verify the tool's exit code rather than assuming it (GNU `grep -q`
returns 2 on a directory, not 1).

#### Fifth cross-model round: new ground, not residue

The fifth round found two High paths nobody had looked at: a disposable copy of the checkout
made with `cp -R` keeps an absolute symlink, so a probe that checked only its last path
component wrote through it into the real checkout; and a clean filter whose command is a
single space is a valid shell no-op that `strip()` turned into "no filter". Both are the same
lesson as the lock: resolve the identity (the physical path, the configured key), never the
text. The round also showed a cancel arriving between a failed attempt and its quota read
could still trigger `--fallback`, and that the installer's collision guard had not learned
the two new hooks. Each fix was watched red first.

#### Sixth cross-model round: the first with no High

Six Medium findings, all at the seams of earlier fixes: a cancel that arrived during the
evidence or usage write kept the attempt's earlier failure kind, so `--fallback` could still
start a second paid reviewer; a lost archive turned the result into a failure but the
completed report, verdict included, was still printed; an empty task label was recorded as
an id that every later labelled review then rejected as damaged; the doctor read any
unrecognised `toolchain_path` line as empty and probed the wrong PATH; a probe's background
descendant outlived `timeout`. Each fix was watched red first.

#### Seventh cross-model round: assert the copy the reader uses

Two Medium findings, both real: the publication-time cancel of the previous round was
normalised only in the returned result while the persisted records, which the usage
reporter reads, still said `quota` (the test had checked only the chain); and the
descendant-death assertion encoded Linux behaviour as universal while doctor's own macOS
fallback contradicts it. Lesson: a test asserts the artefact the next reader consumes, and
a platform-dependent guarantee branches on the same capability probe the code uses, with
the other branch run on Linux by hiding the tool.

#### Eighth cross-model round: a fix's own temporary file

The previous round's relabel staged its replacement archive under a name the shipped ignore
rules did not match, so a crash between link and replace would have left private reviewer
output where `git add -A` picks it up; and its two writes had no order, so a failure between
them left the archive and the record disagreeing. Staging now lives in the ignored usage
directory that is already verified with `git check-ignore`, the record is written first, and
a failed archive replacement is reported as the hash mismatch that later rounds refuse.
Lesson: every file a fix creates, however briefly, is subject to the same privacy gate as the
file it replaces.

#### Nine cross-model remediation rounds; the final full review is pending

The count: round 1 five High, round 2 one High, round 3 one High, round 4 none, round 5 two
High (new ground), rounds 6 and 7 Medium only, round 8 one High in the previous round's own
temporary file, round 9 Accept with Manual Checks and one Low. Every High after round 1 sat
inside a fix made for an earlier round. Rule kept from it: a fix round is reviewed again by
the other model before it ships, and the review budget (400000 bytes of diff plus carried
rounds) is met by reviewing the increment, never by skipping the round. Those increments are
remediation reviews, not the final acceptance: an increment cannot show that earlier changes
and later fixes work together. The fresh full review under a new label that REVIEW_GATE.md
requires is still PENDING. The full diff exceeds the 400000-byte budget, so it is to be split
into path groups, each reviewed under its own new label and recorded in `docs/reviews/`:
review tooling; gate scripts and hooks; docs and overlays.

#### Tenth cross-model round: report only what was observed

The cancel relabel's error reports only what was observed: whether the archive on disk
matches the usage record (with its sha256), does not match it, or could not be read, plus
the write's own error. Fault-injection tests cover a directory fsync failing after the
replacement and an unreadable archive. The acceptance notes count these incremental rounds
as remediation reviews; the final full review under a new label is recorded separately.

#### The final full review, first attempt: split by paths, and what that taught

The full diff exceeds the review budget, so it was split into three path groups, each on a
branch built from the base. The review-tooling group gave one High (a raising signal
handler has two blind windows: inside a constructor that has already forked, and in the
cleanup it triggers; `Path.glob()` hides permission errors) and two Medium, all fixed; the
gates and docs groups gave only artefacts, because each group's reviewer saw a tree missing
the other groups' files ("SUITE_MINIMUMS not found", "--allow-fallback unknown", "hooks
missing"). Rule: a split review splits a CONSISTENT tree by commits, never by paths; when
mechanically generated copies (the plugin runtime) push a diff over the budget, review the
tree with those copies reverted and let the parity check vouch for them.

#### The full review of the integrated tree, round 1

Reviewed as one consistent tree with the generated plugin copies reverted (parity by
`package_codex_plugin.py --check`), it returned Reject: one High, four Medium, one Low, all
fixed with negative tests watched red. Each finding had the same shape: a check that proved
a weaker fact than it claimed. The lock check proved someone held the lock, not this
descriptor; cleanup equated zero exit with completion before the response was read; the
probe guard resolved parents but not the gate itself; doctor trusted the shell's first
output line; the attribution check matched only an unquoted name. Rule: state exactly what a
check must prove about the object it was handed, and add the case where a neighbouring
object satisfies the weaker version.

#### The final full review, split by commit ranges

The whole diff no longer fits the review budget even with the generated copies reverted,
so it was reviewed as two consistent commit ranges: the intermediate tree and the current
one. The intermediate tree's fourteen findings were all fixed later in the second range
except two (a dangling symlink's link text, the only thing git tracks of it, was skipped by
the scanner; a WORKFLOW sentence still allowed in-place edits). The current tree's five
share a shape: a guard that held for the path its tests exercised while a neighbouring step
could still undo it: a result built before cleanup ignored a cancel noted during cleanup; a
disposable copy guarded against symlinks but not against `TMPDIR` inside the checkout nor an
inherited `GIT_DIR`; a parsed separator list was trusted without checking that `tr` ran;
`${VAR:-default}` read an empty override as unset while the adapters did not. Lesson: when a
guard names its inputs, list what else feeds the same step (cleanup, environment, a helper's
exit status, empty versus unset) and test one of each.

#### Range B, round 2: an ACTION is validated by assembling it

Four fail-open paths and one false claim. `readlink "$p"` took a link named `--version` as
an option, so its link text was never scanned (`./` is the POSIX-safe terminator); `git
config` read errors fell back to the default exactly like an absent key, and the default let
`Co-Authored-By=Claude` through (exit 1 is the only absent status); cumulative unfolding
matched an intermediate value of a folded human name (a whole-name rule may see only a
completed value); the changelog said later rounds refuse an archive a failed relabel could
not replace, but failed records were skipped before hashing. And the lock upgrade ACTION,
applied literally to the base version, left `$gate` unset so every commit stopped under
`set -u`: found only by assembling the upgrade from the text and running it. Rule: an
ACTION that moves code is validated that way before it ships.

#### Range B, round 3: the transition into cleanup

A raising cancel handler had one more window: between `finally` beginning and the
non-raising handlers being installed one signal at a time, a second SIGTERM escaped before
the group kill. The handler now raises once and notes thereafter, and cleanup disarms it
with a flag as its first statement, so nothing is swapped under a live signal. The same
round found the supervisor's hand-back to the adapter could drop a completed result, a
folded-trailer join crossing a blank line, `CDPATH=.` printing into the gate's own path, and
the symlink-text scan reporting under a temporary name that lost the `setup/` exemption.
Lesson: every handler switch is itself a window; switch state, not handlers.

#### Range B, round 4: the neighbour of every guard

Six findings of one shape. A copy of a linked worktree carried a `.git` pointer back to the
original's index. The Codex adapter's second handler switch was a swap under a live signal,
the very window round 3 had closed in the supervisor. The Claude adapter sampled
cancellation before its own output. Link text spanning a newline produced a line without
its path, which the `setup/` exemption then dropped. A failed append was ignored. Rule: a
value read to decide (a git dir, a cancel flag, a path prefix) is the last thing read before
the decision is handed over, and every write it depends on is checked.

#### Range B, round 6: a fix lands in one consumer, its peers keep the window

Three cancel windows were each closed at one site but not at its siblings: the Codex
adapter re-checked a late cancel for its returned result but not its records; the quota
reader lacked the signal block around `Popen` the reviewer supervisor had; the Claude
adapter corrected its result dict after printing a stale line. The linked-worktree copy had
traded one defect (staging into the original's index) for another (no HEAD, tags or index);
objects through alternates keep history without writing to the original. Rule: when a
protocol fix lands in one launcher or consumer, grep every peer for the same window.

#### Range B, round 7: the repository shapes a copy must survive

No High for the second round running. The late-cancel correction ran after the caller's
handlers came back, so a second cancel ended the adapter before its records were corrected;
a noting handler is now held through the relabel and the correction line. The disposable
copy copied a split index without its shared part and was initialised in the ambient object
format; it now takes the source format and rebuilds its index from the original's entries.
The hook gave `core.commentString` unconditional precedence where git takes whichever alias
was set last. Lesson: a helper that reproduces a git repository is tested against the
repository shapes git supports (linked worktree, split index, SHA-256), not only the default.

#### Range B, round 8: close the class, not the case

Two High and six Medium, and four of the nine were the disposable copy losing to its
environment one variable or one path at a time (`CDPATH` steering the path guard past a
symlink, a nested linked worktree keeping its git directory pointer, an exported
`GIT_OBJECT_DIRECTORY`, a failed pipeline producer). The fix replaces per-variable unsets
with an allowlisted environment, writes to the validated absolute path and refuses the
shapes the probe does not support. Handler restoration got the same treatment: blocking the
signals closes the whole window rather than re-guarding each step. Lesson: when a review
finds the third instance of one gap, close the class.

#### Range B, round 9: no High, and the owner keeps the copy

Four Medium. Three were more ways the disposable copy differed from or leaked into the
original: git storage reached through a symlink, local configuration lost on
reinitialising, index flags lost in the rebuild; each now has a regression that failed on
the old example. The fourth was a cancel landing between two samples of the same flag, fixed
by reconciling against the record on disk rather than the value in memory. The owner was
offered a smaller design for the copy (support a plain repository only and refuse the rest
by name, let git create the copy, or drop the example) and chose to keep patching it; the
example now refuses by name what it cannot reproduce.

#### Range C, round 1: findings only in the copy

Three Medium and one Low, all in the existing-file example; the adapters, the gate and the
hooks drew none. `find` does not descend through a directory symlink, so checking a
symlink's own target let a link beneath an inside-the-copy directory reach the original's
object store: the general fix is to refuse every directory symlink in git storage.
`diff-files --diff-filter=A` sees an intent-to-add entry only while its file exists, so the
full set comes from `diff-index --cached --ita-invisible-in-index`. Two refusal branches
added in the previous round had shipped without their negative tests; each guard was then
deleted in a copy of the script to watch its test go red.

#### Range C, round 2: six rounds on one example, then the classes

Six review rounds on the existing-file example had each found the next instance of a class
the previous patch handled one case at a time: one more variable, one more configuration
key, one more index state. This round closed each class at once: one helper for every read
of the original (its fsmonitor, hooks and optional locks off), an allowlist of carried
settings instead of a denylist, and a whole-index comparison that refuses what the rebuild
cannot reproduce. Rule: a denylist over an open set (git's configuration keys, its
environment variables, its index states) is the next finding waiting; name what is
supported and refuse the rest.

#### Range C, round 3: one setting, two values

Three Medium, all in the existing-file example. Merging two configuration scopes or files
into the copy's one local file turned a single setting into two values, so a gate's
`git config <key> <value>` that works in the original failed in the copy; the probe now
refuses a carried key that comes from more than one scope or file. Submodule ignore
settings hide gitlinks from plumbing diffs, so a count that subtracts a diff from the index
turns submodule ignoring off first. `--no-includes` had kept an allowlisted key out of the
copy when the original defined it in an include.

#### Range C, round 4: delete the emulation

Four rounds had found divergences caused by flattening git's configuration layers (local,
worktree, includes) into the copy's single local file; the previous round's own fix, reading
through includes, opened two more. The emulation is gone: a carried setting must come from
the repository's own config file, anything else is refused by name with advice the owner
can act on, and the example lost fourteen lines. The first run of this round also returned
"no actionable defects" but was recorded as a CLI failure because of unrelated stderr
noise, and was not counted; the rerun found the two configuration cases. Lesson: when each
fix to an emulation opens the next finding, refuse the unsupported shape instead.

#### Range C, round 5: Accept, no findings

The fifth round on the current tree returned Accept with Manual Checks and no findings at
any severity. The count for the whole hardening: ten rounds on the first full diff, one on
the intermediate tree, nine on range B (one void), five on range C (one not counted): the
last High was in range B round 8, the last finding outside the existing-file example in
range B round 9. What ended the stream in that example was not another patch but two
changes of approach: an allowlist in place of every denylist, and refusing by name what the
copy cannot reproduce in place of emulating it.

#### Four more reviewers on the accepted tree (2026-10-05)

The tree the fifth round accepted went to four more reviewers: Codex gpt-5.6-sol at maximum
effort, Claude Opus 5.5, Claude Fable 5.1 and the cloud review. Three said Reject: 6 High,
about 15 Medium, about 30 Low between them, with little overlap. An Accept from one reviewer
is a statement about that reviewer's reach, not about the tree; the reviewer that deleted
guards one by one found a class (negative tests that stay green without their guard) no
reading reviewer had reported. The fixes land in groups, recorded below.

#### Overlay group: quoting, the brief by path, the worktree (#32, #35)

`spawn_worker.sh` had escaped only the folder; every other value went into the session
command in bare single quotes. One helper now quotes all of them. A brief pasted as one
block, with no typed sentence, was taken by one model for content without an instruction
and the session sat idle for 35 minutes; the script now types one sentence naming the brief
by path. `--worktree` used the tool's `-w`, which branched from a stale base; the script
makes the worktree with git from the lead's current commit and refuses a leftover name.
Not run: a live session (the tests use stub `tmux` and `claude`), and a non-bash `/bin/sh`.

#### Fail-open and data-loss group

The one fail-open of the four reviews was a locale: `grep -I` in a UTF-8 locale calls a
line with an invalid byte binary and prints nothing, so the gate passed a marker it was
looking at. The gate and the commit-msg hook now run in C and hand the build its own locale
back. The sync had the guard bootstrap got in the fifth round, one script late: paths that
became kit-owned in v0.9 overwrote a project's own hooks. In the review runtime the worker
left the signal mask out of the guard switch on purpose (a handler raising just after the
block would leave the cancel signals blocked for the process; the switch is one attribute
store) and left one gap named: a signal between the last pending check and the unblock
reaches the caller's handler as a signal after the hand-back. Both are for the next
cross-model round to judge.

#### Existing-file example: plain repository only

A second model found four High in the example that five rounds of the first had accepted:
a symlink anywhere in the copy leading back into the checkout, a plain repository's config
copied verbatim (every configuration test had used a linked worktree), the real HOME and
global git configuration, and a baseline run that swaps the target for a link. The owner
reversed "keep patching": the example supports a plain repository only and refuses the
rest by name as NOT RUN, which fails the self-test. Cost, known and accepted: a project
that adopts the example cannot get a green `--self-test` inside a linked worktree, which
is where the kit's own workers run. The rebuild block and nineteen tests went; one audit of
the whole copy runs before and after the baseline. Not run: macOS/BSD, git older than
2.55, Python 3.10. Open at merge: the copy keeps the original's `.git/hooks` files.

#### Gate, scan and doctor group

The scan had dropped directory and dangling links but kept a link to a regular file, and
grep followed it; now only regular files reach grep and a gitlink is a named case. The
doctor's required-file list is still kept by hand (a project has nowhere to read it from),
held equal by a kit test to what `review_dispatch.py` imports and to the plugin's parity
list. `--exclude` was left off the grep-alias allowlist on evidence: GNU grep 3.12 skips an
excluded file even when it is named on the command line. Not run: a real Windows Python
(the missing `fcntl` is a stub), macOS/BSD, dash as `sh`.

#### Guards without a killing test

One reviewer deleted guards one at a time and listed those whose negative test stayed
green: the code was right and nothing kept it right. Twenty-two now have a case watched red
with the guard removed. One clause the report called redundant was deleted
(`review_dispatch.py`); the other was kept and pinned by a test, because its job (no new
CLI process after a cancel) is not what the report took it for. The first self-test of this
group failed on its own doing, a suite minimum hard-coded in `check_kit.py`; the minimums
now equal the counts and a test holds them equal. Cost: `test_doctor` takes about six
minutes on a WSL host whose PATH includes Windows directories.

#### Cross-model round d1 on the five groups: Reject

Codex gpt-6-astra on `3536cb7..31c8f7a`: one High (the copy kept `.git/hooks`, already in
the running group's brief), five Medium, one Low. Three of the Medium were in the
`spawn_worker.sh` rewrite of the same day (CDPATH in the brief path, a file name ending in
a newline, a relative `--settings` file after the change of directory) and one in the
grep-alias allowance, where a whitespace split accepted `--exclude-dir=x>/dev/null`. Each
first cut of a fix again drew findings its author's tests did not.

#### Cross-model round d2: Reject, and equality in place of a list

Round d2 on `31c8f7a..1afba49`: one High, one Medium. The High was the third hook route in
the example in one day (the configured path, then the default directory, then a path the
baseline itself configures). The fix stops naming hook routes: the copy's `.git/config`
after the baseline must equal, byte for byte, what the example wrote, and no other
configuration source may have appeared. Checked with git: under the probe's environment
only `.git/config` is read. The worker also found, unasked, that the audit's own `python3`
ran a `.pth` file a baseline left in the copy's HOME; it now runs with `-I`. Cost: a gate
that writes git configuration during its run cannot use the example.

#### One upgrade checklist, proved by using it

Two reviewers found the v0.9 ACTION items could not be followed: fifty lines, cut
mid-sentence, superseding each other. The section is now final-state bullets and one
twelve-item checklist. The proof was to use it: a project bootstrapped from the v0.8
commit, synced and upgraded by the list alone, compared equal (`diff -r`) to a fresh
bootstrap from master. Not covered by that run: a project with its own boundary checks, an
adapted existing-file example, or old usage records, which is what both real projects are.

#### Cross-model round d3: Reject, and a fresh copy in place of re-checks

Round d3 on `1afba49..62d2988`: one High, two Medium, one Low. The High was the fourth of
one class in a day: something the baseline gate run leaves in the copy acts in the injected
run (this time a `.pth` in the copy's HOME, run by the gate's own Python). The equality
check added one round earlier had itself opened a Medium (a config file swapped for a link
to `/dev/zero` hung the read). The owner chose to keep the example. The class is closed by
construction instead of by checks: the baseline runs in one copy, which is deleted, and the
injection goes into a fresh one. Every after-baseline check was deleted, the earlier
attack cases now pass as ordinary runs, and the cost is a second copy of the tree. Lesson,
again: when each check on shared state opens the next finding, stop sharing the state.
The checklist finding was confirmed by doing it: with "take the kit's side" a project's own
licence check vanished and its gate still passed; the list now says both sides survive and
prints the lines a merge removed.

#### Cross-model round d4: Reject, on what the fresh copy opened

Round d4 on `62d2988..d826ccd`: one High, two Medium, one Low, three of them opened by the
previous round's redesign: the cleanup's `chmod -R` followed a hard link and a swapped root
out of the copy; two copies of a live checkout need not be the same tree; a relative
TMPDIR resolved differently after `cd /`. Fixes: modes only on the copy's folders, by name
from an open parent, with the root's device and inode checked; a sha256 of each copy as
taken, equal or NOT RUN; TMPDIR resolved once. Known side effect: another session's
`git status` rewriting `.git/index` between the copies also gives NOT RUN. The fourth was
the checklist's own diagnostic hiding a removed Markdown bullet. Counts for the day's
rounds: 7, 2, 4, 4, a High in each, three of the four opened by the round before.

#### Cross-model round d5: Reject, and removing what races

Round d5 on `d826ccd..ed29079`: two High, two Medium, all four in the existing-file example
and nothing anywhere else. Both High were races on the previous round's guards (a check,
then a concurrent swap, then the act). The rule for the fix: remove the operation that
races. The permission repair is gone (the example changes no mode; a copy it cannot delete
fails the case by name), deletion runs from the open, identity-checked folder with no
`rm -r` on a path, the carried settings come from the copy so the live checkout is read
once per copy, and the hash covers full permission bits. Left open and named: a background
process a baseline gate leaves running is contained by nothing here; an allowlisted key
set only through `includeIf "gitdir:<checkout>"` is no longer refused, it is not carried
(with a NOTE). Counts: 7, 2, 4, 4, 4.

#### Cross-model round d6: Reject, a regression the lead let through, and a disposition

Round d6 on `ed29079..4baf4e0`: one High, one Medium, both in the example. The High was a
regression the previous round's worker had named in its report ("not done": a setting
supplied through `includeIf "gitdir:<checkout>"` is no longer refused, only not carried)
and the lead merged without having it fixed; the reviewer showed why it matters (the
setting can turn the real gate off while the copies run it on). Lesson for the lead: a
"not done" in a worker's report is a finding, not a footnote. Fix: every include is refused
by name, whatever its condition. The Medium (an empty directory swapped into the copy's
temporary name between the identity check and the final `rmdir` gets removed) the owner
chose to answer by disposition, not by code: only an empty directory at the example's own
temporary name can be removed, nothing with content; the comment that claimed more was
corrected. Counts: 7, 2, 4, 4, 4, 2.

#### Round d7 accepts; the closing review under a new label rejects

Round d7, carrying d6 and the author's dispositions, was an Accept with Manual Checks: the
High confirmed fixed, the cleanup limit kept open as a limit. The closing review, a new
label over the whole of `3536cb7..77377f4` with no earlier round in its prompt, was a
Reject: one High and two Medium that seven incremental rounds had not raised, plus the
known limit. The High was the mirror of d6's: the copies run without global git
configuration, so a gate setting that lives there is on in the real checkout and off in
the copies. The two Medium were outside the example (a FIFO at a bootstrap destination
hangs `cmp`; control bytes in a brief path reach the terminal). This is the reason the
review gate asks for the fresh label: rounds that carry their history converge on that
history. The fixing worker listed five things it noticed and left; this time each was
treated as a finding: three fixed by a further worker (a symlinked folder on the way to a
destination, a dangling link skipped silently, a raw path printed before its check), two
accepted with reasons (the scope check covers only the keys the owner names, since a global
`user.name` would refuse every run; a FIFO as the live `.git/config` blocks every git
command, the gate included). Named and left by that worker: the window between the symlink
check and the copy; bootstrap's STOPPING header says "the gate files" for a `docs/` path.

#### Round close-2: Reject, and the setup scripts take the example's place

Round close-2 on `77377f4..42e5a19`: one High, three Medium, one Low, none in the example
and all in what the two merges before it had touched. Three small steps had each added one
guard at one more call site of `bootstrap.sh` and `sync-kit.sh`; the reviewer found the
call sites still without one (the files bootstrap generates, a regular file where a folder
belongs) and, underneath, that both scripts ran without `set -e`: a failed `mkdir` or `cp`
was ignored and the version stamped. One function now judges every path either script
writes, both run with `set -eu`, and the stamp is the last write. The check-then-copy
window was not closed, by the lead's decision in line with the owner's on the cleanup
limit: the scripts' comments now say the check runs before the write and guards against
nothing that changes the tree meanwhile. Named and left by the worker: that function
exists twice with no test holding the copies equal; test names still say "never read or
written". Rounds of the day: 7, 2, 4, 4, 4, 2, Accept (carried), 4, 5: the findings follow
the last fix from file to file, which is what a diff-scoped review does.

#### Round close-3: Reject, on runs that fail part way

Round close-3 on `42e5a19..68e9ae5`: one High, two Medium, all three the same shape and all
opened by the round before (stopping on a failed write made "what does the retry do" a
question): a hook left at 0644 by a failed `chmod` compared `same` on the retry and the
version advanced; the stamp was truncated before it was written; the hooks path was changed
before the last write that could fail. Fixes: the executable bit is part of "same", every
file goes through a sibling moved over it, the finish is ordered and undone on failure. The
worker was asked to walk every write with "the run dies here; what does a retry do" and
found one more itself (a copy cut short taken for the owner's file). Left and named: SIGKILL
or power loss between `git config` and the stamp's `mv` loses the old hooks path.

#### Round close-4: Reject, and the owner sets a threat model and a stopping rule

Round close-4 on `68e9ae5..2f2ef6b`: two High, one Medium, one Low, every one in what the
round before had added (the fixed-name temporary, the finish trap, and the lead's own
CHANGELOG sentence claiming a rollback that does not exist). Eleven rounds in the day: 7,
2, 4, 4, 4, 2, Accept (carried), 4, 5, 3, 4. A diff-scoped reviewer asked for every finding
will find some in any new mechanism, and each fix was a new mechanism. The owner decided:
these four are fixed (fresh `mktemp` temporaries, one write helper that sets the mode
first, the stamp's move as the commit point read from disk), `bootstrap.sh` and
`sync-kit.sh` state a threat model (own failures, interruptions, retries and honest
mistakes in the tree: yes; another process changing the tree, planted files, SIGKILL
between steps: no), and the loop ends with the next round that has no High outside that
model; findings inside it are answered by disposition and recorded as accepted limits.
Lesson: write the threat model before the first hardening round, not after the eleventh;
without one, "close the class" has no edge.

#### Round close-5: no High, and the loop ends by the owner's rule

Round close-5 on `2f2ef6b..1a13854`: Reject with two Medium and no High, so by the owner's
rule the review loop ended there. Both findings were inside what the scripts promise and
were fixed, not accepted: on a re-run at the same version the stamp on disk already held
the version and was taken for this run's commit (the commit is now this run's own
temporary moved into place); and two partial-write tests had gone hollow one round
earlier, failing on bootstrap's file list before any write they named (they now cut short
the named write, prove it was reached, and were mutation-checked). These two fixes were
not reviewed by anyone but their author. Twelve rounds in the day: 7, 2, 4, 4, 4, 2, Accept
(carried), 4, 5, 3, 4, 2. What the day did not establish: one fresh review of the whole
`3536cb7..master` diff in a single prompt (it grew past the 400000-byte budget), any run
on macOS/BSD, with dash as `sh`, on Python 3.10, or a live tmux and Claude session.

#### The four issues left open "on purpose"

Issues #29, #34, #36 and #37 had been carried as open on purpose from one handoff to the
next without a reason anyone could state; the owner asked why, and there was none. Fixed in
one round. Two things the fixes showed: #34's own diagnosis was wrong (the completed review
was failed by `error` events in the stream for a reconnect it recovered from, not by
stderr text; the stderr-only case passes on the old code), and #29 could not be made to
fail again (80 busy loops and six parallel copies of the suite: the old 5 s code passed
every time), so its fix is a wider, scalable deadline with the child's output on expiry,
not a reproduced red. Not reviewed by anyone but the author, by the owner's stopping rule.

#### Back to review after the "last" fixes, and one contradiction in a record

The owner asked whether the fixes merged after the loop ended had gone back to review;
they had not, and the lead had read the stopping rule as leave to skip it. Round close-6
on `1a13854..2b1f73a` (the close-5 fixes and the four issues): Reject, no High, one Medium,
a regression in the #29 fix itself (the deadline's cleanup killed the process group only
while its leader ran). Fixed. Lesson: a stopping rule ends the hunt for new classes; it
does not excuse unreviewed code. Separately a worker had noticed that the Claude adapter
returned `completed` together with `failure_kind: quota` for a success envelope carrying
`api_error_status: 429`, and the dispatcher took it for a finished review. The CLI's own
source settled the reading: the status is set from the last assistant message only, so a
status that is not null means the turn ended on an API error; there is no recovered case
as with Codex. The adapter now fails such an envelope, and a test holds both adapters to
"completed if and only if the failure kind is null".

#### A size limit on STATE.md was a proxy; the causes were a backlog and narrated work

A project had added a 10 KB limit on `docs/STATE.md` to its own gate and hit it four times
in one session, with the file parked a few hundred bytes under it. The owner's judgement:
a size limit is no answer to "finished tasks are sometimes not deleted". Reading that file
gave two causes a byte count sees neither of: 53 of its 125 lines were a backlog (next and
parked tasks) that nothing ever shrinks, and its live bullets narrated completed, committed
work. The kit's own rot rule (long file with an empty "Active work") never fired there
either, because something is always active. Now: the backlog has its own file, read when a
task is chosen; a task id closed by a `Done:` trailer may not be named in either file, at
commit time and in the gate; every length limit is gone. Scope, stated before building: a
housekeeping aid for honest sessions, not a control against evasion.

#### Writing rules: no controlled-language standard and no terse-style skill, a few rules of our own

The owner asked whether the kit should make agents write to ASD-STE100 or use a
"caveman" terse-output skill, both proposed online as cures for long answers. A sourced
survey (sources read by a research agent, nine of them through search summaries only, none
re-verified by the lead) said neither as a package. The standard was built for
comprehension by non-native readers, not brevity; the one careful public test found
shorter sentences but no reliable drop in words, and naming the standard in a prompt cost
one model 7 of 24 facts. The terse skill's third-party measurement on coding tasks was 8.5
percent fewer output tokens, its author's own table shows one plain sentence gets nearly
all of that, and its rules exempt everything persistent, which is most of what this kit
writes. Output is a small share of an agent session's cost; the lever is context. What
carried over is structural and stated in the kit's own words: two registers (chat: answer
first; artifacts read cold: full sentences, one instruction each, one term per thing) and
a rule above both that failures, unrun checks, security warnings and irreversible actions
are never shortened. The instructions are unenforced: nothing measures whether agents
follow them.

#### The first CI run of v0.9: red on all four jobs

Nothing of v0.9 had been pushed, so CI last ran on v0.8. Pushed to a branch behind a draft
pull request, the tree that passed the kit check on the development machine a dozen times
that day failed on all four jobs: one boundary case on both Ubuntu jobs, and on macOS that
case in another form, two path comparisons (`/var` against `/private/var`), a doctor test
reading an unreadable tool, and a cleanup test in which the replacement directory's content
was gone. Twelve review rounds by a reviewer that runs no tests, and a self-test run on one
machine, had recorded "NOT RUN: macOS, dash, Python 3.10" each time and moved on. Lesson:
a platform the kit claims is a platform it is run on before anything is called accepted;
"not run" repeated ten times is a finding, not a footnote.

#### A day of leeway's lead: four shape-independent causes and a hybrid

A project's lead spent ten hours in the one-lead-with-sub-agents shape and the owner called
it slow and expensive. Its own account named five causes; four of them had nothing to do
with the shape: every worker built the whole package and the lead built it again; one
machine-wide lock queued the "parallel" workers; a fresh worker per review round re-read
100 to 250 thousand tokens to change a few lines; and the gate built on every
documentation commit. The fifth, the lead idling and waking its whole context at every
hand-back, is the shape's. The owner decided for the kit, not for the project: cheapest
proof per worker and the expensive step once at integration; the same worker for a small
fix round; "no review needed" stated as explicitly as "needed"; a documentation-only
commit that skips the build; no parallel work that ends in one resource; a hybrid with a
threshold (an hour or a second review round means a separate session). He declined one
relayed item: "from the second round only High or Critical block". The 2026-10-03
comparison is now described for what it measured: cost per worker on one task with one
long wait, nothing about wall-clock, throughput or the lead.

#### Reviews take too long: the owner refused "review less"

Asked for a way out of seven-hour review loops, the lead first proposed one reviewer by
default and a round budget. The owner rejected that outright: if reviews take too long,
the answer is not fewer reviews. The levers that remain all cut waiting, not coverage: the
review moves inside the worker's warm context (a separate session runs a fresh reviewer on
its own diff before reporting); reviewers execute in a throwaway copy and say REPRODUCED or
REASONED (the read-only reviewer's findings needed a worker to reproduce them, and some
were false; the reviewer that executed was decisive); a new mechanism gets a design review
before code (the lifecycle note took two fifteen-minute rounds; code rounds took hours);
the week's finding classes become an attack list for reviewers and a pre-report checklist
for workers; the self-test and both reviewers start together under one label; and the kit
check itself fell from eight minutes to under two by running its units at once and not
walking Windows directories on every PATH lookup. Still open: the Codex sandbox is pinned
read-only on purpose, so that reviewer cannot execute until the owner widens it.

#### Lifecycle of a worker session: decided by cost, consulted with a second model

Three relayed requests (close a finished session automatically; hand off at a context
threshold; "done" means a committed result file) were, in the owner's words, grey. A design
note with the costs was consulted twice with Codex, which corrected it: the one-hour cache
writes at 2x, not 1.25x; the comparison is over the whole next task (warm 0.1 C per request
against a cold write of 2 P then 0.1 P per request: at C 113k and P 30k they cross near
seven requests, so a short follow-up is cheaper in the old session and a long one fresh);
and a committed result file is also where progress, blocked states and questions go, so
"done" needs a kind. Decisions: the lead chooses reuse or close per task from the context
figure, the idle time and the expected length; the watcher warns past half the window and
the lead chooses finish, compact or hand off; a result file carries a kind
(completed/blocked/handoff/progress), a task id and an attempt; questions sit under one
heading and are asked at once.

#### The first CI runs of v0.9, and what each taught

Run one, red on all four jobs (Apple `mktemp` ignores TMPDIR without a template; `/var`
against `/private/var`; dash `cd` past PATH_MAX; `Path.exists` raising on EACCES before
Python 3.12). Run two, green. Run three, red on three: `cut -c` counts bytes on coreutils
before 9.8 and cut a box-drawing character in half (invisible here, where cut 9.10 counts
characters), and the parallel kit check on a three-CPU macOS runner pushed one phase past
its fixed 300-second timeout. Run four, green. Each red was a platform fact the development
machine could not show; none was a logic error. The rule "a claimed platform is run before
acceptance" now stands in the kit because of these four runs.

#### Worktree clean-up: eleven rounds, two reviewers, and what each round taught

A project had 39 merged worktrees and 34 GB behind it; the owner wanted them removed
automatically, "with no loss". The feature went through eleven fix rounds, each reviewed by
Codex and by a fresh Opus reviewer that reproduced its findings in throwaway repositories.
The design moved under review: "finished" stopped meaning the absence of a liveness signal
and became a commit made in the worktree plus a merge into main's BRANCH (a merge on a
detached main, later undone, had left a worker's commits in no ref); the script stopped
deleting branches at all (the branch keeps the commits whatever happens to main); "nothing
reachable only from here" became a scan of every file of the private git directory, both
reflog columns, with every loose commit saved under `refs/kit/saved/` before removal (the
owner's choice over "keep forever" and over "ignore reflog leftovers"); tracked content
stopped trusting git's stat cache and is compared by bytes; mount points anywhere in the
worktree, its git directory or on an archive copy's path keep the worktree; a case probe was
deleted in favour of always folding the protected names; `lsof` output is trusted only when
it shows the script itself and is read back exactly. Three rounds were spent on list-shaped
rules that the next reviewer extended (ref namespaces, four files of the git dir, device
checks); each was replaced by a rule over the whole class. One reviewer's experiment ran in
the real repository after a failed `cd`; it undid its refs, and every later brief says
`cd ... || exit 1`. The closing round: Codex with no code finding, Opus "approve with nits",
130 tests, 79 guards each with a killing test.

#### The review gate held on the kit's own hardening

Five of the nine work packages (the gate lock, both review-tooling packages, the commit gates
and doctor.sh) needed a second review round (doctor.sh a short third one, for a `timeout`
that stopped an interactive shell), and each first review found a real hole in the first cut: the five lock holes above, the dispositions that let a reviewer Accept with
everything deferred, the substring match that rejected humans, the false node MISSING and the
ignored-signal override. The four others (the scan, the sync stamp, the rules, the seams)
were accepted in one round, with nits applied by the lead afterwards. None of the five was
found by its author's tests. This is the invariant the review gate exists for, observed on
the kit's own changes: the author's green self-test did not stand in for a fresh reviewer.

### 2026-10-03 — Worker cost is waits times context, not output size (#22)

A project using the kit ran one lead session with background sub-agent workers for eleven
hours at 336 USD, 87 percent of it the workers. Counting the transcripts request by request
(1,824 requests, deduplicated by request id) gave the shape: 87 percent of all cache-write
tokens followed a gap of more than five minutes, which is a sub-agent's prompt-cache
lifetime (a main conversation gets an hour); one worker resumed for three review rounds grew
from 36k to 711k tokens of context over 377 requests and was 38 percent of all cache read;
15 percent of all cache read went to turns that only waited; all tool output together was
about one million tokens. The earlier guess that output size was the lever was wrong.

A controlled experiment then ran the same task in six setups. A sub-agent blocking on a
400-second job re-wrote its whole context after every wait (the baseline). A background job
with automatic re-invocation changed nothing (+12 percent), because the wait still outlived
the five-minute cache. A separate session and a sub-agent with the one-hour cache both
avoided the re-writes at the same cost (−36 to −38 percent on a 100k context, limited by the
one-hour cache's doubled write rate on the first load). Splitting waits under five minutes
also avoided them (−52 percent at that small context) but pays a full context read per poll,
so it loses at real worker sizes.

The six setups, their figures, and which one to take when the first choice is unavailable
are kept in `docs/worker-cost-setups.md`, together with the alternatives the research pass
saw and did not take. Hence the rule set in the WORKFLOW template, the worker definition and the spawn script in
the Claude Code overlay, the analyser, the interview question and the handoff line. Projected
on the measured session, the cache lifetime alone removes about a third of the worker cost;
with fresh workers capped at about 150 requests, 45 to 50 percent. The first real-task
measurement (a separate session against a comparable sub-agent, same task, same model) is in
`docs/worker-cost-setups.md`: gap re-writes fell from 49 to 1 percent of cache write, cost
came out level because the task had a single wait over five minutes and the session's larger
starting context ate the gain, so the one-hour sub-agent is the cheaper of the two equals.
Not explained: about a third of the cost screen's cache-read volume appeared in no
transcript (the permission classifier is the candidate).

Rejected on the way, with no measured benefit for this cost shape: output compressors,
memory plugins, keep-alive plugins, terse-output packs, spec kits and knowledge-graph tools.

### 2026-07-26 — from the founding project (the codebase this kit was extracted from)

A Unity + .NET multiplayer game written almost entirely by CLI agents (Claude Code and
Codex). The findings below are what it paid for in real budget and real broken gates. They
are the kit's founding content, not later additions.

#### 1. Gates tend to fail OPEN, and a fail-open gate is worse than no gate — ACCEPTED

Three of that project's three gates were fail-open when first written, and every one of
them printed PASS while protecting nothing:

- The cross-model review script exited 0 when `git` produced no change set, so "nothing to
  review" and "the diff could not be collected" looked identical.
- The engine test gate wrote its results file to a path resolved against the ENGINE's
  working directory, not the shell's. The file landed where nobody looked, the engine
  exited 0 for a run that executed zero tests, and the gate reported PASS.
- The state-file rot gate counted every non-blank line under a heading as "active work",
  including the heading's own placeholder hint, so its condition could never be true.

The failure mode is identical in all three: the gate was verified GREEN and never verified
RED. Nobody had ever seen it fail. A gate that has only been observed passing is an
untested branch that runs in production on every commit.

What went into the kit: the rule that **a gate is not finished until it has been proven to
go RED**, and — because a one-off manual proof rots the moment the script changes — the
requirement that every gate ships with an automated NEGATIVE TEST that constructs the
failure condition and asserts the gate rejects it. `core/scripts/check.sh --self-test` is
the worked example.

#### 2. Gates, CI and review tooling are themselves a high-risk area — ACCEPTED

A broken gate disables every other protection SILENTLY. That makes gate code the single
highest-leverage place a defect can land: one wrong line there costs more than a wrong line
almost anywhere else, and it costs it invisibly, for as long as nobody looks.

The observation that proved it: **the session that wrote a gate could not validate its own
gate.** It ran the script, saw PASS, and reported the gate as working — while the gate was
structurally incapable of failing. A fresh reviewing session found it in minutes. That is
the review-gate invariant ("the author of a change never reviews it") demonstrated on the
review machinery itself.

What went into the kit: `core/docs/REVIEW_GATE.md` lists **gates, CI configuration, check
scripts and review tooling** as a PERMANENT risky area, present in every project regardless
of what that project does. It is the one entry in that list that is not a placeholder.

#### 3. The cross-session state file bloats, and pruning it destroys permanent knowledge — ACCEPTED

That project's `STATE.md` reached 906 lines / roughly 18K tokens — a bill paid at the start
of every session, in every tool. Two independent causes:

- **Completed work accumulated as a diary.** Items were marked DONE instead of deleted, so
  the file grew monotonically and the reader had to skim history to find the present.
- **Permanent lessons had nowhere else to live.** This is the dangerous one. Pruning a
  transient file buries permanent knowledge in the git history, where nobody looks for it.
  Git is an audit trail, not a knowledge base: "why is this rule here" is not a question
  anyone answers with `git log -p`.

What went into the kit, as four separate mechanisms because they fail separately:

- **The routing rule.** Before deleting a line, ask: *is this still true next month?* If
  yes, it must have a permanent home BEFORE it leaves. Homes: a design decision → the
  design document; a module or boundary → the architecture map; a process or gate
  constraint → the workflow doc; an environment or tooling trap → `GOTCHAS.md`. Permanent
  knowledge is never written INTO the state file; it passes THROUGH it.
- **Tagging at write time.** A line worth keeping is prefixed `[LESSON]` or `[GOTCHA]` the
  moment it is written. Harvesting is then a `grep`, not a re-read of the whole file — and
  the tag doubles as a flag meaning "this line may not be deleted until it has a home".
- **The template rule.** Completed work is DELETED, not marked DONE; the dates live in git.
  A multi-item operation tracks its progress in its OWN file with checkboxes, not as a
  growing list in the state file.
- **The gate, deliberately WITHOUT a fixed line limit.** Length alone is the wrong signal:
  1000 lines is healthy in the middle of a long operation and rot the day after it closes.
  The script can tell the two apart — it FAILS when the "Active work" section is empty
  while the file is still long, and stays quiet (or emits an informational note) while work
  is genuinely in flight. Note that this very parser was finding #1's third fail-open gate:
  it must count STRUCTURAL MARKERS (bullets), never lines, and must ignore placeholder and
  hint prose. It ships with a negative test.
- **The ritual.** The last acceptance item of every multi-item operation is *"the state
  file has been harvested and pruned"*.

#### 4. Parsing CLI output: strip ANSI, and never pass an empty field silently — ACCEPTED

The review wrapper extracted the run's token usage by grepping the CLI transcript. It
silently produced nothing, because the CLI wraps that phrase in ANSI colour codes — the
archived report recorded `tokens used<ESC>[0m` with no number, and nobody noticed, because
an empty field looks like a field.

What went into the kit: `core/scripts/review.sh` strips ANSI escapes before matching, and
an extracted field that comes out empty is REPORTED as not found rather than written as
blank. Same shape as finding #1 — absent evidence must be visible, not silent.

#### 5. A placeholder inside a comment is a fail-open gate waiting to happen — ACCEPTED

Found by the kit's own first end-to-end run, not by a project using it. `scripts/check.sh`
carried a `# {{BOUNDARY_CHECKS}}` line meant to be replaced in place. The first fill
substituted the marker but left the leading `#` on the first line, so the entire boundary
check sat inside a comment. The gate reported `CHECK: PASS`, enforcing nothing — finding #1
reproduced, in the very script written to prevent it, within an hour of writing it.

That is the useful part: the trap is not a lapse of care, it is a property of the design.
Any "replace this marked line with code" instruction can be half-followed, and a half-
followed edit to a gate fails silently by default.

What went into the kit: the checks and their negative tests live in their own sourced files
(`scripts/boundary_checks.sh`, `scripts/boundary_selftests.sh`), replaced WHOLE. When the
unit of replacement is a file rather than a line, the mistake is not available. Where a
placeholder must stay inline it is now a VALUE in a quoted string, never a statement.

#### 6. A gate's author cannot find its fail-open paths — ACCEPTED

The strongest evidence in this log, because it happened to this kit rather than to the
project it came from. v0.1 was written in one session, its gates were exercised, its
negative tests passed, and it was published with an acceptance record. A cross-model review
then returned **Reject** with seventeen findings, five of which were fail-open paths in the
gates themselves.

The two that matter most were invisible from the inside:

- **A bootstrapped project could never go green.** The placeholder scan flagged markers in
  `setup/INTERVIEW.md` and the module template — two files that carry them on purpose,
  forever, and that `sync-kit.sh` restores if deleted. The author's own acceptance test had
  missed it because that test deleted `setup/` before running the gate. **The verification
  was shaped by the same assumption as the defect.**
- **A failing file-listing became "no matches".** The producer sat on the non-final side of
  a pipeline ending in `|| true`, so a failed `git ls-files` was indistinguishable from a
  clean scan, and the gate went green having scanned nothing. This is finding #1 of this log
  reappearing inside the script written to prevent finding #1.

What went into the kit: the fixes, each with a negative test; `docs/ACCEPTANCE.md` rewritten
to separate what was executed from what was not; and the review report archived under
`docs/reviews/` as evidence rather than summarised.

What is worth keeping beyond the fixes: **an author's negative tests inherit the author's
blind spot.** They prove the failures you thought of. A second model is not a formality on
top of them — it is the only thing that finds the failure mode you designed your test
around. Reviewing gate code by a fresh session is now a permanent, non-placeholder entry in
`core/docs/REVIEW_GATE.md`; this is the third time in two repositories that the rule has
been earned rather than assumed.

#### 7. A review's FIXES are unreviewed code, and they fail the same way — ACCEPTED

Finding #6 ended with seventeen findings fixed and the kit published. A third model then
reviewed the FIXED tree and returned Reject again — eleven findings, two critical. The one
that matters:

Round 1's most serious finding was a scanner whose failure was indistinguishable from a
clean scan, because the producer sat in a pipeline ending `|| true`. The fix introduced
`scan_or_die`, which printed a diagnostic and called `exit 1` on a failed scan. It was
called as `hits=$(scan_or_die … | grep -Ev … || true)`.

`exit` inside a command substitution terminates the SUBSHELL. The diagnostic printed, the
subshell died, the main script carried on and reached `CHECK: PASS`. The fix for the
fail-open scanner was a fail-open scanner. Worse, the repository had by then written the
claim down in two places — the self-test's closing message and the acceptance record both
said the path was "enforced by construction" — so the false belief was now documented,
which is how it survives.

The general shape, and the reason this is a finding rather than a bug report:

- **A fix is written under time pressure, by the party who just accepted the criticism, and
  it is the least reviewed code in the repository.** Everyone's attention is on whether the
  original finding was real. Nobody asks whether the patch is.
- **Fixes cluster in exactly the code that was already subtle enough to get wrong once.**
  The second attempt is not safer than the first; it is written in the same place, by the
  same author, against the same blind spot.
- **A remediation commit tends to be self-certifying.** It ships alongside a document
  asserting the problem is now solved, and that document is what the next reader trusts
  instead of the code.

What went into the kit: `core/docs/REVIEW_GATE.md` states that **fixes made in response to a
review are themselves subject to the gate** — a Reject is not closed by the fixes, only by a
fresh pass over them — and that a claim of "enforced by construction" is a claim requiring a
negative test like any other. Where a construction genuinely cannot be tested, the acceptance
record says so instead of asserting the guarantee.

The mechanical lesson is worth its own line, because it is invisible and general: **in POSIX
shell, a failure signal that must escape a command substitution cannot be an `exit` or a
variable — it has to be a side effect on the filesystem.** The kit's scanner now drops a flag
file, checked by the main shell after every scan has run.

#### 8. A gate aimed at a path that does not exist is worse than no gate — ACCEPTED

Found by applying this kit's own review findings back to the project it came from, which is
the backflow loop working as intended — though in the wrong order: the fix landed in the
project first and reached the kit afterwards, which is exactly the drift `docs/UPDATING.md`
warns against.

That project's highest-risk check guards its money modules against floating-point
arithmetic:

```sh
hits=$(grep -rn --include="*.cs" -E "float|double" \
  shared/Core.Economy shared/Core.Trade 2>/dev/null | grep -v "// non-monetary:" || true)
```

Neither directory exists yet — that work is scheduled, not started. `grep` exits 2,
`2>/dev/null` hides the reason, `|| true` converts the failure into success, `hits` is
empty, and the most important gate in a project about a player-driven economy had been
printing PASS without reading one line, for its entire existence. Confirmed directly before
anything was changed: exit status 2, no output.

Two distinct traps, and the second is the one worth carrying:

- **A scanner pointed at a missing path is indistinguishable from a scanner that found
  nothing.** Only the exit status separates them, and `|| true` throws it away. This is
  finding #1's shape once more, arriving through a construct that reads as defensive.
- **A gate written ahead of the code it guards accrues the CREDIBILITY of a gate while
  doing nothing.** Everyone can see the check in the script, so nobody re-derives whether
  it fires. When the module finally lands — quite possibly under a slightly different name,
  because names change between planning and building — nothing announces that the gate
  missed it. The gate's silence is identical before and after.

What went into the kit: `core/scripts/boundary_checks.sh` tells the author to declare the
guarded paths in a variable, to check that at least one of them EXISTS, and to print an
explicit dormant notice when none do, rather than scanning nothing quietly. Absent evidence
must be visible — the same rule as finding #1, applied to the target of a scan rather than
to its result. The periodic-audit checklist gained the matching question: *does any gate
guard a path that no longer exists?*

#### 9. Non-goals need a home that is read every session — ACCEPTED

The founding project grew a document the kit had never shipped: a per-stage scope file
listing, for each stage, the question it answers, what to build, what NOT to build yet, and
how to tell it was done. Nobody planned it. It appeared because the work needed it, which is
the strongest signal available that a document belongs in the foundation.

What it prevents is the most expensive habit an agent has. "Build the inventory system"
gives an agent no edge to stop at, so it invents scope — persistence, a UI, an event system,
one monolithic file across five modules. "Build the grid placement rules; do NOT add
persistence, do NOT write UI, those are later phases" is the same task with a fence around
it. The non-goals are the useful half of a specification and the half everyone skips.

The reason it needs its OWN file rather than a section somewhere: non-goals only work if
they are in front of the agent before it starts. Put them in the design document and they
are not read (that file is deliberately not in the reading order). Put them in the state
file and they are deleted the moment the current task closes, so the next session re-invents
the same scope.

What went into the kit: `core/docs/PHASES.md`, read every session, holding the current phase
in full and later phases at one line each. Detail for a distant phase is aspiration, and
aspiration in an always-loaded file is a bill with nothing behind it.

This also settled the shape of the layer above it. Knowledge has three horizons, not two —
permanent (`PROJECT.md`, superseded but never deleted), episodic (`PHASES.md`, deleted after
harvest when a phase closes) and momentary (`STATE.md`). A separate ROADMAP file was
proposed and rejected: "offline support in v2" is both a decision and a plan, so a roadmap
document creates a seam with no clear side and the item gets written twice or lost. The long
view is one line per future phase at the bottom of PHASES.md. Full reasoning in
`docs/knowledge-has-three-horizons.md`.

#### 10. A living document an agent may write to needs an asymmetric permission — ACCEPTED

The appealing version of a project document is one the agent keeps current from
conversation. The dangerous version is the same sentence, and the difference is entirely in
what the agent is allowed to write.

An agent recording decisions autonomously will eventually promote a musing to a settled
decision, do it silently, and every session afterwards will treat it as law — while the
constitution's hardest rule says agents implement and do not design. The file meant to hold
the owner's decisions becomes where the agent's inferences accumulate, indistinguishable
from the real ones.

What went into the kit, as a deliberately asymmetric rule: **an agent may add OPEN items
freely and may never mark anything DECIDED.** Hearing what sounds like a decision, it
records it as OPEN with a note that the owner appeared to settle it, and asks.

The asymmetry is the point. A wrongly captured question is noise somebody deletes in a
minute. A wrongly promoted decision is invisible, binding on every future session, and
compounds — nobody re-reads a DECIDED item to ask whether it was ever really decided.

#### 11. Uncommitted work has no undo, and an agent will eventually take some — ACCEPTED

The reflog records COMMITS. `git reset --hard`, `checkout --`, `restore`, `clean -f` and
`stash drop` discard the working tree, and anything never committed is then gone with no
message, no trace, and a `git status` that looks clean afterwards.

It happened during this kit's own development, which is the only reason it is written down
rather than assumed. A `git reset --hard HEAD~1`, run to remove a throwaway test commit,
also took a set of uncommitted gate fixes and — worse — a long review record the owner had
written BY HAND and not yet committed. The fixes were re-typed from context. His paragraph
was unrecoverable from git and had to be reconstructed from a chat transcript.

Three things make this specifically an agent failure rather than a git one:

- **The command was correct for its stated purpose.** Removing a test commit is exactly what
  `reset --hard` does. Nothing about the invocation looked wrong.
- **The agent believed the tree was clean**, because it was thinking about its own work and
  had not looked at `git status`. The owner's edit was invisible to it.
- **The loss is silent.** No error, no warning, no diff. It surfaced only when the owner went
  looking for something he had written and found it missing.

What went into the kit: the rule in the constitution (commit or stash first, every time,
especially when sure), the reasoning in `GOTCHAS.md`, and — because a rule an agent promises
to remember is worth nothing here — a mechanism.
`overlays/claude-code/files/.claude/hooks/guard_destructive_git.py` blocks all of these
commands while the tree is dirty and prints the file list that would have been destroyed. It
allows `stash push`, `commit` and `--force-with-lease`, which are the recoverable ways to do
the same jobs.

The general lesson is not about git. **An agent's cleanup is the most dangerous thing it
does**, because it is the one action taken while attention has already moved to the next
task, and it is the one place where "I was sure" replaces looking.

#### 12. Every-session files are a recurring bill, not a style preference — ACCEPTED

Cached input tokens are discounted heavily, which makes the always-loaded prefix — the
constitution, the architecture map, the state file — the largest single cost lever in a
repeated-session workflow. Size there is money, and editing one of those files mid-session
invalidates the cache for every session after it.

What went into the kit: `core/docs/WORKFLOW.md` states the rule (keep always-loaded docs
small and stable, batch documentation edits into their own session, volatile state goes in
the on-demand state file), and the kit's own core files are kept short for the same reason.
`GOTCHAS.md` is explicitly NOT a session-start file — it is referenced from the
constitution in one line and read only when something behaves unexpectedly.
