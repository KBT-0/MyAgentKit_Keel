# A rule nothing enforces is a request

Write "the core layer must not import the engine" in a document and you have expressed a
preference. Write it as a grep that fails the build and you have expressed a rule.

The distinction sounds pedantic until you watch what happens over a few months. The
documented version holds while everyone is fresh and attentive. Then someone is finishing
something at the end of a long session, the import is the fastest way through, and the
comment says "temporary". Nothing objects. The build is green, the tests pass, the pull
request looks fine. The boundary is now gone, and nobody decided to remove it.

Agents make this faster, not slower. An agent reads the instruction file at the start of the
session and then works for an hour inside a context window that is filling up with code. The
rule was true in the first thousand tokens and is competing with fifty thousand tokens of
task by the end. Repeating the rule harder does not fix this. Making the build fail does.

## What this looks like in practice

- Every boundary that CAN be enforced by a compiler, a project reference whitelist, a type,
  a database constraint or a grep IS enforced that way. Prose is the fallback, not the plan.
  OpenAI's harness team works the same way: its real gate is custom linters and structural
  tests, not the written rules (`docs/research/agent-kits-in-practice.md`, §2.2, source 23).
- The enforcement lives in ONE script that CI, the pre-commit hook and every agent run. One
  definition of green. A local pass means a CI pass, or the arrangement is a lie.
- The gate is wired into git (`core.hooksPath`), so passing it does not depend on anyone
  remembering. The hook is the backstop; running it yourself is still the rule.
- **Where a boundary cannot be enforced, say so explicitly.** `docs/ARCHITECTURE.md` asks for
  the words "not enforced" against those. An honest gap gets closed eventually. A gap
  everyone assumes is covered never does.

## Where it is genuinely hard

Some rules resist mechanisation: "MonoBehaviours stay thin", "no god classes". (Even "one
task touches one module" has only a partial check: a brief's `Owns:` line, which
`scripts/owns_check.py` holds the diff to.) These stay in prose, and they decay — which is
why the periodic audit exists as a scheduled task rather than a good intention. The audit is where unenforceable
rules get checked by a human, on a cadence, instead of never.

Do not respond to this by inventing a fragile check. A grep that produces false positives
gets an escape hatch, the escape hatch gets used routinely, and you end up with a gate that
annoys people without protecting anything. A coarse check with an honest note about its
limits — and a reviewer duty to cover the gap — beats a clever one nobody trusts.

## The failure mode it prevents

Silent architectural decay: the codebase drifts away from its documented design one
reasonable exception at a time, nobody makes a decision to allow it, and by the time it is
visible the fix costs more than anyone will authorise. The document still describes a
system that no longer exists, which makes it worse than absent — new work is planned
against a fiction.
