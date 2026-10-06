# Pattern: orchestrating two or more CLI agents

**The problem.** You pay for two agents because they are good at different things and
because a second model catches what the first cannot see. Then you spend your day copying
text between three terminal windows: plan here, implement there, review in the third.

## The shape: official plumbing, your own thin policy layer

Two parts, and keeping them apart is the whole pattern.

**Plumbing — use the official integration.** If one vendor ships a plugin that calls the
other's CLI from inside a session, use it. It handles transport, sessions, resuming and
authentication, and when the CLI changes underneath, fixing it is their problem.

**Policy — write your own, thin.** What gets reviewed, by whom, when, with what instructions,
and what happens to the output: that is yours. It is fifty lines of shell plus a document.
Do not reimplement the plumbing's review command; CALL it and layer your protocol over it.

Concretely, that is `scripts/review.sh` (collect the diff, pin the sandbox, archive the report
with its configuration) plus `docs/REVIEW_GATE.md` (the priority order and the verdicts).
Neither knows anything about transport.

**Reject third-party orchestration frameworks that sit in the middle.** They own your policy
and depend on the plumbing, so you inherit two maintenance surfaces to avoid writing fifty
lines you understand.

## The rules that make it safe

**A second agent's output is untrusted INPUT to a decision the calling agent owns.** Never a
verdict to relay. Verify every finding against the code, drop what you disprove, keep what
you confirm, and say which is which. Pasting another model's verdict through unchecked is a
failed review in either direction — the false-clean is worse than the false-alarm.

**The human triggers every hop.** Check whether the plugin's commands are model-invocable.
Some are, which means a session can spend the other tool's budget and delegate work nobody
decided to delegate. If so, the project rule is: no session calls the other tool unless the
owner asked for it in that session. That is a rule you write down, not something the plugin
guarantees.

**Keep the automatic review gate OFF.** The tempting feature is a stop hook where agent B
reviews every turn of agent A and blocks until fixes are applied. The plugins' own
documentation warns that unattended loops burn usage limits fast. On a small budget it is
the wrong trade: all review manually triggered. Record the decision so nobody enables it
later as a convenience.

**Route by scarcity, not by capability.** Both budgets are finite and they are not equally
finite. Spend the scarce one on judgement — planning, architecture, contract design, the
final review of a risky diff. Spend the generous one on volume — bulk implementation of
well-specified tasks, mechanical refactors, first-pass review. Then note the caveat: the
more autonomous tool fills ambiguity by itself instead of asking, and the mitigation is a
sharper brief plus the gates, never trust.

## What actually makes this work

Not the plumbing. **Memory that survives the hop.** The receiving tool has no chat history:
if it is not in the handoff prompt or the state file, it does not exist. A cross-tool
workflow with tool-specific memory is a workflow that forgets at every boundary — and the
memory features each tool advertises are exactly the ones the other cannot read.

One canonical instruction file, one state file, one gate script that every tool runs. The
orchestration is the easy part.
