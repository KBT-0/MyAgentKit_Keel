# The author of a change never reviews it

An agent that has just written a patch is the worst possible reviewer of it. Not because it
is careless — because it is inside the assumption. The reasoning that produced the bug is
still in its context, still looking correct, and asking it to check its own work mostly
produces a confident restatement of the same reasoning.

So: **review happens in a FRESH session, never on the author's own model.** Who takes it is
the working mode's call (`core/docs/REVIEW_GATE.md`, "Invariant"): another tier of the same
family in solo, the other family in cross.

Fresh matters because a new session reads the diff as evidence rather than as a memory.
Another model matters too: two agents of the same model share their blind spots, so running
three of them gives one opinion with error bars, not three opinions. A second family is
welcome, never required: it reduces correlated blind spots but does not remove them, and the
one controlled measurement found the direction asymmetric (`docs/research/claude-lead-codex.md`,
finding 4). No published measurement says how much another tier of the same family adds, so
every review record names the author's and the reviewer's model, and the kit compares them.

## The cleanest evidence for this rule

While building this kit, a session wrote a quality gate, ran it, saw `PASS`, and reported
the gate as working. The gate was structurally incapable of failing — its condition could
never be true. A fresh session found it in minutes.

The author was not sloppy. The author was verifying against the same mental model that
produced the defect, and that model said the gate was fine. No amount of care fixes that,
because care is applied through the model.

## What does not count as review

- **A passing compile.** It proves the code is well-formed.
- **Green tests.** Necessary, not sufficient — and if the diff touched the tests, they are
  part of what needs reviewing, not evidence about it.
- **The implementer's self-report.** "Done, 0 errors, all checks pass" is a claim. The whole
  point of the gate is to not take claims.
- **Relaying another model's verdict.** This one catches people out, because it *feels* like
  review. Another agent's output is unverified INPUT to a decision the calling agent owns:
  verify each finding against the code, drop what you disprove, keep what you confirm, and
  say which is which. Passing a verdict through unchecked is a failed review in either
  direction — and the false clean is the expensive one.

## Never report a verification you did not run

The rule that holds the rest together. If a check could not be executed, the words are "not
run" — not "should pass", not silence.

The temptation is strongest exactly where it is most damaging: at the end of a long task,
with everything else green, when the missing check is the slow one. A single fabricated
"verified" makes every other report in the file worthless, because the reader can no longer
tell which ones were real.

## Keeping it affordable

Review costs budget, so its depth follows the risk tier: one light pass for a low-risk
change, one reviewer for a medium one, two for the areas the owner named and for gates, CI
and check scripts in every project. The review a change's tier requires starts without
asking; that is what the owner approved with the task. An extra review beyond it (another
family, a higher effort, a paid backend) is the owner's call in the session, never an
agent's own initiative.

## The failure mode it prevents

A defect that passes every check because the same reasoning wrote the code and the check —
and a review process that produces confident approvals which mean nothing, so the first real
failure arrives with no warning and a paper trail full of green ticks.
