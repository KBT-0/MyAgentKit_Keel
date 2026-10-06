# When a worker session ends, continues, hands off or is reused — options and costs

Status: a design note for a decision, not a rule. Nothing here is implemented. The owner's
instruction (2026-10-06): the three questions below are not black and white; a finished
session may be worth keeping for a task that fits what it already holds, a handoff may cost
more than a compaction, and the answers are to be weighed by cost, reviewed by a second
model, and only then decided. The facts used are the kit's own measurements
(`docs/worker-cost-setups.md`, `RESEARCH_LOG.md` 2026-10-03); example figures are marked.

## The cost facts the answers rest on

- A request re-reads the session's whole context. With the one-hour cache it is a cache
  read (list price about one tenth of a fresh input token); after a gap longer than the
  cache lifetime the next request writes the whole context again (about 1.25 times input).
  `docs/worker-cost-setups.md` measured the setups; the rule in WORKFLOW follows from it.
- The always-loaded prefix of a session is about 6,400 tokens today (AGENTS.md, PHASES,
  STATE, ARCHITECTURE; measured 2026-10-06, bytes divided by four); a brief and the files a
  task reads add tens of thousands. Call the context a fresh session must build before it is
  useful P (example: 30k).
- A session that has worked for a while holds context C (example: 113k, read from a real
  status bar that day) and pays C per request while it lives, whether or not the next task
  needs what C holds.

## Question 1: close a finished worker, or reuse it for the next task?

Per request, a reused session costs C and a fresh one costs P plus what the new task reads.
Reuse is cheaper only when the new task would have to rebuild most of C anyway: the same
files, the same branch area, the same unfinished thread. When the next task is elsewhere,
every one of its requests drags C along for nothing; at the example figures that is four
times the cost of a fresh start from the second request on.

The cache lifetime changes the answer again. A session that has sat idle for more than the
cache lifetime (one hour) has lost its warmth: its next request writes all of C again. After
that gap, reuse saves only the tool calls that would re-read the files, not the tokens.

What the lead can observe without guessing: the worker's own context figure (its status bar
shows it), the time since its last request, and whether the next task's files and branch are
the ones the worker already holds.

Options:
- 1a. Close at merge, always (automatic). Simplest; pays P again for every follow-up,
  including a revision of the same change that arrives an hour later.
- 1b. Reuse when the next task is the same thread, else close (the lead decides per task,
  with the three observables above; a default rule: reuse if C is under about three times P
  and the session was active within the cache lifetime and the next task names the same
  files; otherwise close). Closing is explicit: `close_worker.sh NAME` ends the tmux session
  (its terminal tab closes by itself) and removes the worktree through the audited path;
  the branch is never deleted automatically (see the worktree clean-up note).
- 1c. Never close automatically; the owner closes by hand. What happens today; it is what
  left 39 worktrees behind.
Recommendation to weigh: 1b, with 1a as the fallback when the lead has no next task for the
worker and the session has been idle past the cache lifetime (then nothing warm is lost).

## Question 2: when a session's context grows, hand off to a fresh session or compact?

Both read the whole context once to produce a summary. A compaction is automatic, keeps the
session, its tab and its worktree, and the summary is the tool's; a handoff is written by
the worker to the kit's handoff shape (`docs/HANDOFF.md`), reviewed by the lead, and starts
a fresh session that pays P plus the handoff. The handoff's advantage is control over what
survives; its cost is the fresh start and the lead's attention. Compaction's advantage is
that it costs nothing to arrange; its risk is that what it drops is not chosen by anyone,
and the kit cannot see it.

The threshold is not a fixed percentage. What matters is the work still to come: a session
at 60 percent with two short steps left should finish; one at 60 percent with a long
operation ahead pays 60 percent of its window on every remaining request. So the rule needs
an estimate of remaining work, which only the worker has.

Options:
- 2a. A fixed threshold (60 percent of the window) at which the watcher tells the session
  to write its handoff and stop. Predictable; wrong for a session that is nearly done.
- 2b. The watcher reports the figure past a warning line (say 50 percent) and the worker's
  result-file template asks for "remaining work" in one line; the lead decides per case:
  finish, compact, or hand off. Costs the lead one decision; makes the choice visible.
- 2c. Leave it to the tool's compaction. Cheapest to run; the kit loses its handoff shape at
  the moment it matters most.
Recommendation to weigh: 2b, with the brief telling a worker that notices a compaction to
write its handoff section into its result file at once (compaction is a signal, not a
secret).

## Question 3: what "done" is

An idle notice fires when a session waits on its own background job, not only when its work
is finished; re-subscribing while it is idle fires again at once. The done signal must be the
committed result file: the file exists, the tree is clean, and the file is in the last commit.
The idle notice stays as a hint. This is not grey; it is proposed as a rule.

## Question 4: questions a worker leaves for the owner

A worker that cannot ask in its own pane writes its questions into its result file under one
fixed heading ("## Open questions for {{OWNER_NAME}}", one numbered question per item, each
with its options). The lead asks them at once, one at a time, and records each answer and
its general rule in the permanent home. The watcher that sees the result file land reports
the count and the text, so a question cannot wait on the lead's attention. Proposed as a
rule.

## Question 5: "the expensive step once" against a gate that builds on every commit

The kit now says a worker runs the cheapest proof that shows its change and the integrating
session runs the expensive step once. But the commit hook runs `check.sh`, which runs the
project's build command, on every commit a worker makes. The rule therefore holds only when
the gate's build command IS the cheap proof and the expensive step (a package, a pipeline, a
full rebuild) is an integration step outside the gate. A project whose `build_test_cmd` is
itself the forty-minute step gets no benefit until it moves that step out. The kit should say
so plainly in the setup interview and in WORKFLOW: the gate's build is the proof a commit
must pass; integration steps are not in it.

## What a second model should attack

- Whether 1b's default rule (three times P, cache lifetime, same files) is sound or needs a
  measurement first, and what observable replaces "same files" when the lead cannot tell.
- Whether 2b's "remaining work" line is something a worker can estimate honestly.
- Whether an automatic close on merge (1a) can ever destroy something the audited worktree
  removal does not already protect.
- Whether the watcher reading a status bar is a dependable source for the context figure.
