# When a worker session ends, continues, hands off or is reused — options and costs

Status: decided by the owner on 2026-10-06 after two consultation rounds with a second
model (evidence in `docs/reviews/`, label `v09-lifecycle-design`): question 1 option 1b,
question 2 option 2b, questions 3 and 4 as rules, question 5 as stated. The note stays as the
record of the costs and the options; the rules go into WORKFLOW, HANDOFF and the worker
scripts. Nothing here was implemented when it was written. The owner's
instruction (2026-10-06): the three questions below are not black and white; a finished
session may be worth keeping for a task that fits what it already holds, a handoff may cost
more than a compaction, and the answers are to be weighed by cost, reviewed by a second
model, and only then decided. The facts used are the kit's own measurements
(`docs/worker-cost-setups.md`, `RESEARCH_LOG.md` 2026-10-03); example figures are marked.

## The cost facts the answers rest on

- A request re-reads the session's whole context. With the one-hour cache it is a cache
  read (list price about one tenth of a fresh input token); after a gap longer than the
  cache lifetime the next request writes the whole context again, at about 2 times input
  for the one-hour cache (1.25 times for the five-minute cache). The figures are
  `docs/worker-cost-setups.md`'s, measured on Claude Code with the Claude plan it names; the
  rule in WORKFLOW follows from them.
- The always-loaded prefix of a session is about 6,400 tokens today (AGENTS.md, PHASES,
  STATE, ARCHITECTURE; measured 2026-10-06, bytes divided by four); a brief and the files a
  task reads add tens of thousands. Call the context a fresh session must build before it is
  useful P (example: 30k).
- A session that has worked for a while holds context C (example: 113k, read from a real
  status bar that day) and pays C per request while it lives, whether or not the next task
  needs what C holds.

## Question 1: close a finished worker, or reuse it for the next task?

The comparison is over the WHOLE next task, not per request. Let the next task take n
requests. A reused warm session pays about 0.1 C per request (plus its own growth): about
0.1 C n. A fresh session pays one cold write of P at 2 P, then about 0.1 P per request:
about 2 P + 0.1 P (n - 1), plus whatever of C it has to read again because the task needs it.
At the example figures (C 113k, P 30k) the two cross at about seven requests: a SHORT
follow-up is cheaper in the old session even when most of C is irrelevant, because the cold
write of a fresh start outweighs a few requests of dead weight; a LONG task is cheaper fresh.
When the next task needs part of C, count that part into the fresh session's context (it
reads it again) and compare the same way: the crossover moves later, but a long enough task
still favours a fresh start, because the fresh session carries only what the task needs and
the old one carries everything. There is no length at which reuse wins unconditionally.
This is arithmetic on list prices, not a measurement; the kit has not measured a follow-up
task both ways.

The cache lifetime changes the answer again. A session that has sat idle for more than the
cache lifetime (one hour) has lost its warmth: its next request writes all of C again. After
that gap, reuse saves only the tool calls that would re-read the files, not the tokens.

What the lead can observe without guessing: the worker's own context figure (its status bar
shows it), the time since its last request, and whether the next task's files and branch are
the ones the worker already holds.

Options:
- 1a. Close at merge, always (automatic). Simplest; pays P again for every follow-up,
  including a revision of the same change that arrives an hour later.
- 1b. Reuse or close per task, decided by the lead from the three observables above and
  the expected length of the next task. Unvalidated heuristic to start from, to be replaced
  by the measurement in passing that WORKFLOW already announces: reuse when the session was
  active within the cache lifetime AND (the next task is short, a handful of requests, OR it
  needs most of what the session holds); close when the session is cold (idle past the
  lifetime: nothing warm is lost) or the next task is long and elsewhere. Closing is explicit: `close_worker.sh NAME` ends the tmux session
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
is finished; re-subscribing while it is idle fires again at once. The done signal must be a
committed result file, but a result file is also where a worker writes progress, a blocked
state, a handoff (question 2) and open questions (question 4): a committed report with a
clean tree is not by itself "done". So the result file carries one KIND line, fixed
vocabulary: `completed`, `blocked`, `handoff`, `progress`; the watcher and the lead treat only
`completed` as done; the file names the task id and the attempt it reports on, so a result
left by an earlier task of a reused session is never taken for the current one. The idle
notice stays as a hint. Proposed as a rule.

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
project's build command, on every commit a worker makes that touches more than
documentation (a documentation-only commit skips the build since today). The rule therefore holds only when
the gate's build command IS the cheap proof and the expensive step (a package, a pipeline, a
full rebuild) is an integration step outside the gate. A project whose `build_test_cmd` is
itself the forty-minute step gets no benefit until it moves that step out. The kit should say
so plainly in the setup interview and in WORKFLOW: the gate's build is the proof a commit
must pass; integration steps are not in it.

## What a second model should attack

- Whether 1b's heuristic (warm within the cache lifetime, and a short next task or one that
  needs most of the held context) is sound or needs a measurement first, and what observable
  replaces "needs most of the held context" when the lead cannot tell.
- Whether 2b's "remaining work" line is something a worker can estimate honestly.
- Whether an automatic close on merge (1a) can ever destroy something the audited worktree
  removal does not already protect.
- Whether the watcher reading a status bar is a dependable source for the context figure.
