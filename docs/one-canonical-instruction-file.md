# Tool-specific instruction files are pointers, never copies

Every CLI agent wants its own instruction file. One reads `CLAUDE.md`, another `AGENTS.md`,
the next one something else. The obvious move is to keep a copy for each.

Do not. Two copies of a rule are two rules, and they diverge on the first edit — silently,
because nothing compares them. Six weeks later two tools are working the same repository
under different constitutions and the disagreement surfaces as a code review argument nobody
can resolve, since both sides can cite a file.

**One canonical file. Everything else is a one-line pointer to it.**

```
CLAUDE.md:  @AGENTS.md
```

Plus a comment saying "do not add content here". That comment earns its place: the file
looks empty and inviting, and the next agent will want to be helpful.

## Why AGENTS.md is the canonical one

It is the most widely adopted cross-tool convention, and it is not owned by a single vendor.
The specific choice matters less than the property: **the canonical file should be the one
most tools read natively, so the pointers are the exception rather than the rule.**

If your tools converge on something else later, move the content and leave a pointer behind.
The rule is one source, not one filename.

## What goes in it, and what does not

The canonical file is loaded at the start of every session, in every tool. That makes it
expensive (see [context-is-a-budget](context-is-a-budget.md)) and it makes it authoritative.
So:

- **In it:** rules that are always true. Boundaries, task discipline, review triggers, what
  to raise with the owner, how to write the state file.
- **Not in it:** anything volatile. Current status, what happened last session, a list of
  open bugs. Those go in the state file, which is read on demand and rewritten constantly.
  Volatile content in an always-loaded file also makes every session start on a different
  text, so no two sessions follow quite the same rules.
- **Not in it:** reference material. The trap log is referenced in one line and read when
  something behaves unexpectedly.

Per-folder `AGENTS.md` files follow the same discipline one level down: only what is true in
that folder and nowhere else. A rule repeated from the root is a rule that will drift from
the root.

## The failure mode it prevents

Two tools working the same repository under quietly different rules, and nobody noticing
until the merge — at which point both agents can cite a file, both are right, and the only
way to resolve it is to reconstruct which copy was edited when.
