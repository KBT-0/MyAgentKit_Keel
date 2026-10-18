# Research — the kit's bibliography

The kit collects what people, AI vendors and our own projects have learned about building
software with AI agents, and keeps itself current with it. Every rule, workflow and
decision in the kit stands on a source (`CONTRIBUTING.md`, "Every change cites its source"),
and the reports below are where most of those sources live. Read them to see why the kit
works the way it does; cite them, by file and finding number, when you change it.

Reports are written in Turkish (the owner's language); identifiers and quotes stay in their
original language. Each report grades its sources (vendor document, paper, blog, forum,
secondary copy) and marks inference apart from evidence. Lessons learned in projects that
use the kit are recorded in `RESEARCH_LOG.md`, the third kind of source.

| Report | Question | Date | Sources | Decisions it backs |
|---|---|---|---|---|
| [ai-review-workflows](ai-review-workflows.md) | How do practitioners review AI-written changes, and what does each practice cost? | 2026-10-13 | 70 | The v0.11 review overhaul: risk tiers, one pass per round, two rounds at most, a single model by default (`docs/v011-overhaul-proposal.md`, items A–L and Q) |
| [token-optimization](token-optimization.md) | What do prompt caching, quotas and context cost, and which savings were measured? | 2026-10-13 | 56 | WORKFLOW "Worker cost" and "Token economics"; the short `AGENTS.md` (proposal items M–O) |
| [agent-kits-in-practice](agent-kits-in-practice.md) | How are comparable agent-development kits used, and what do they do differently? | 2026-10-13 | 73 | Token and context savings (proposal items M–O); the cache hit target in `agent_cost.py` |
| [review-prompts-and-rules](review-prompts-and-rules.md) | Do the kit's reviewer prompt and rule files match published practice? | 2026-10-13 | 24 (via its two companions) | The reviewer prompt and the 89-rule keep/merge/delete list (proposal items E and P) |
| [review-prompts-sources](review-prompts-sources.md) | Companion: published reviewer prompts and rule files, quoted verbatim | 2026-10-13 | 24 | Evidence for the report above |
| [review-rules-inventory](review-rules-inventory.md) | Companion: every review rule the kit gave, with copies and conflicts | 2026-10-13 | the kit itself | Evidence for the report above |
| [communication-style](communication-style.md) | How should an AI agent talk to the person it works for? | 2026-10-14 | 101 | `core/docs/COMMUNICATION.md`, `GLOSSARY.md`, the two communication hooks (proposal item R) |
| [kit-self-checks](kit-self-checks.md) | Is a whole-gate self-test supported, and how do template/kit projects size, tier and budget their own test suites? | 2026-10-18 | 46 | The v0.12 split of `check_kit` into a fast and a slow tier, removal of the project gate's `--self-test`, the test-time budget (owner rule of 2026-10-18) |
| [context-limit](context-limit.md) | At what context size should a lead session hand off or compact? | 2026-10-14 | 47 | The context band in WORKFLOW "Worker cost" rule 8 |
| [claude-lead-codex](claude-lead-codex.md) | How do people run a second model (Codex) beside a Claude lead: routing, cross review, cost, failures? | 2026-10-14 | 57 | The cross working mode and the `Owns:` check (WORKFLOW "Working modes, by name"); Model routing rule 7 |

A new report goes in this folder and gets a row here; `tests/test_doc_pointers.py` fails
when a report has no row.
