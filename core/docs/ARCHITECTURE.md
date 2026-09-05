# Architecture Map

This file answers one question: **"where does X live?"** If an agent cannot orient itself
with this file in two minutes, fix THIS FILE — not the code. It is read at the start of
every session, so it stays short and stable.

It is also the reason this project does not need a code-search or embedding tool: the module
table IS the navigation. If agents start failing to find things through it, the first
reading of that signal is architectural decay, not a missing tool.

## Runtime topology

{{RUNTIME_TOPOLOGY}}

<!-- A small diagram plus one line per process: what it is, and what authority it has.
     "Which component is allowed to decide X?" must be answerable from this section. -->

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
public API, its own tests. Modules see each other ONLY through public contracts.

{{MODULE_MAP}}

<!-- One table per top-level area. Columns: Module | Responsibility | (optional) the design
     document section it implements. One line each — this is a map, not documentation. -->

## Boundary enforcement (rule ≠ advice)

For each boundary below, state WHAT enforces it — and write "not enforced" where nothing
does. A boundary enforced only by prose is a request, and requests decay; the point of this
section is to make that distinction visible rather than to imply it away. An honest gap gets
closed. A gap everyone assumes is covered does not.

{{BOUNDARY_ENFORCEMENT}}

<!-- Numbered list. For each: the rule, and WHAT enforces it — a compiler error, a project
     reference whitelist, a grep in scripts/check.sh. If nothing enforces it, write "not
     enforced" rather than implying otherwise; an honest gap can be closed, a fictional
     gate cannot. -->

## Contract change procedure

A task that wants to change a module's public API: (1) proposes the change in that module's
README, (2) lists the affected modules, (3) applies it after {{OWNER_NAME}}'s approval.

Contracts change rarely. If they change often, the module boundary is in the wrong place —
report that rather than absorbing the churn.
