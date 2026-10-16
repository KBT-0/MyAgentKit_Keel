# Pattern: the staged prototype

**The problem.** The project is large, unbuilt, and every part depends on every other. "Where
do we start" has no obvious answer, so the answer becomes "everywhere at once" — which for
an agent-written project means a lot of plausible code and nothing that runs.

## The shape

Split the build into a handful of STAGES. Each stage:

- has a **one-sentence goal** — what question it answers, or what risk it retires;
- names **what it deliberately does NOT do**, in as much detail as what it does;
- ends in **acceptance criteria someone can run**, not a feeling of completion;
- is independently useful, so stopping after any stage leaves something real.

The order is by RISK (a stage whose assumption cannot be tested before a dependency exists
waits for it; D10 inv3#164), not by dependency and certainly not by enthusiasm. The stage that
would hurt most if its assumption turned out wrong goes first, even when it is not the
foundation. A skeleton plus a gate usually comes before any feature work, because everything
after it lands on protected ground.
Sources (D10 inv3#164): the stage-2 report cites the
[spiral model](https://en.wikipedia.org/wiki/Spiral_model) from a search summary and
[Claude Code best practices](https://code.claude.com/docs/en/best-practices) for scope and runnable checks.

## Why the non-goals carry the weight

"Build the inventory system" gives an agent no edge to stop at, so it invents scope: it
adds persistence, a UI, an events system, and returns one monolithic untestable file that
touches five modules.

"Build the inventory grid placement rules. Do NOT add persistence, do NOT write UI, do NOT
add item freshness — those are separate stages" gives it the same task with a fence around
it. The fence is the useful half of the specification, and it is the half people skip.

## Acceptance criteria are commands, not adjectives

Bad: "the economy feels balanced." Good: "the simulation runs 100 days at seed 42 with no
price outside its declared band, total supply within bounds, and no route permanently
dominant."

Bad: "movement feels right." Good: "the owner plays it for ten minutes and says yes." That
one is subjective — and it is still a criterion, because it names WHO decides and WHEN. A
subjective criterion with an owner is fine; an unowned one is not a criterion.

The rule that makes the whole thing work: **an implementer's self-report is never
acceptance.** "Done, all tests pass" is a claim. The criterion is a command someone else can
run and get the same answer from.

## Keeping it honest

- Stages live in their own file with checkboxes, not in the cross-session state file. That
  file is for what is in flight now; a stage plan is a plan.
- When a stage closes, the state file is HARVESTED and PRUNED — the permanent lessons go to
  their real homes, the rest is deleted. Make that the last acceptance item of every stage,
  or it never happens.
- A stage that turns out to be wrong gets rewritten, not quietly extended. Extending is how
  a five-stage plan becomes a twelve-stage one that nobody reads.
- Record deviations as decisions. "We skipped X because Y" is worth keeping; discovering
  three months later that X was silently dropped is not.
