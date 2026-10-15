# Architecture Map

This file answers **"where does X live?"** It holds boundaries, invariants and who may decide
what, not a description of each file, and agents read it to orient (`AGENTS.md`, reading
order), so it stays short: aim for about 100 lines. If an agent cannot orient with it, look
at this file first; the cause may also be a missing module README. (Sources: matklad,
https://matklad.github.io/2021/02/06/ARCHITECTURE.md.html: keep it short, name invariants and
boundaries; Claude Code memory, https://code.claude.com/docs/en/memory: an instruction file
under 200 lines.)

## Runtime topology

{{RUNTIME_TOPOLOGY}}

<!-- A small diagram plus one line per process: what it is, and what authority it has.
     "Which component is allowed to decide X?" must be answerable from this section.
     Sources: matklad (invariants and boundaries code cannot show); Claude Code best
     practices, https://code.claude.com/docs/en/best-practices ("architectural decisions
     specific to your project"). -->

## Repository layout

```
{{REPO_LAYOUT}}
```

Two documentation subdirectories exist for process output rather than design:

- `docs/reviews/` — raw review-gate output, one file per review
  (`<UTC-timestamp>-<random>-<reviewer>-review.md`), recording the reviewing model and
  whether it is attested, reasoning effort, sandbox mode, limits, scope and base ref.
  Every reviewer writes the same header table and one verdict line, so the records stay
  comparable when the author and reviewer roles swap. Written by the review wrapper and
  never edited afterwards: it is evidence, not a document.
- `docs/worktree-notes/` — progress notes from sessions working on a branch or in a
  worktree, one file per branch, so `docs/STATE.md` never becomes a merge conflict. The
  integrating session folds a note into STATE.md at merge time and deletes it.

## Module map

Each module: its own folder, its own project/build unit, its own README summarising its
public API, its own tests (a kit choice; no study measured this layout). Modules see each
other ONLY through public contracts.

{{MODULE_MAP}}

<!-- One table per top-level area. Columns: Module | Responsibility | (optional) the design
     document section it implements. One line each — this is a map, not documentation; a
     module's detail lives in its own folder (its AGENTS.md and README), read when work
     there needs it, not here on every read (Claude Code best practices: no file-by-file
     descriptions in an instruction file). -->

## Boundary enforcement (rule ≠ advice)

For each boundary below, state WHAT enforces it — and write "not enforced" where nothing
does. A boundary enforced only by prose is a request, and requests decay; the point of this
section is to make that distinction visible rather than to imply it away. An honest gap gets
closed. A gap everyone assumes is covered does not.

{{BOUNDARY_ENFORCEMENT}}

<!-- Numbered list. For each: the rule, and WHAT enforces it — a compiler error, a project
     reference whitelist, a grep in scripts/check.sh. If nothing enforces it, write "not
     enforced" rather than implying otherwise; an honest gap can be closed, a fictional
     gate cannot. Source: OpenAI's harness team enforces its architecture with linters and
     structural tests, not prose (the kit's docs/research/agent-kits-in-practice.md, §2.2);
     the reasoning: the kit's docs/rules-that-enforce.md. -->

## Contract change procedure

A task that wants to change a module's public API: (1) proposes the change in that module's
README; (2) finds the affected modules mechanically (builds or runs the tests of every
module that depends on it, searches for the changed symbol) and lists what it found;
(3) applies it after {{OWNER_NAME}}'s approval. Step 2 is a check, not a reading of the
contract: users come to rely on behaviour no contract promises (Hyrum's Law,
https://www.hyrumslaw.com/), and consumer-driven contract tests find them by running them
(Pact, https://docs.pact.io/).

If a contract changes often, report it: the boundary may be in the wrong place.
