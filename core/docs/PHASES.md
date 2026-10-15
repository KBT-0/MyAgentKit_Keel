# Phases — what we are building now, and what we are deliberately not

Read every session: the CURRENT phase in full, every later phase in one line. When a phase
closes, its permanent findings move to their homes and its detail is deleted; its history
stays in git (other kits archive a finished plan instead; this one harvests and deletes). The
reasons are in `docs/WORKFLOW.md`, "The state, backlog and phase files".

---

## Current phase: {{CURRENT_PHASE}}

**What it must find out:** {{PHASE_QUESTION}}

<!-- State what the phase must find out or which risk it retires, in one sentence (a
     question is a good form, not a requirement). If it cannot be put in one sentence, split
     the phase. A kit choice; no study measured it. -->

**In scope**

{{PHASE_IN_SCOPE}}

**NOT in scope — do not build these yet**

{{PHASE_OUT_OF_SCOPE}}

<!-- Spend as much effort here as on the list above. Each entry names the phase it belongs to
     instead, so "not yet" does not read as "never". An agent that finds itself needing
     something on this list STOPS and reports rather than quietly widening the phase.
     Sources: non-goals in Google design docs (industrialempathy.com/posts/design-docs-at-google);
     GitHub Spec Kit, spec-driven.md; Anthropic's prompting guide on overeagerness. Naming
     the phase each entry belongs to is the kit's addition. -->

**Done when**

{{PHASE_ACCEPTANCE}}

<!-- Commands or observations, never adjectives. "The simulation runs 100 days at seed 42
     with no price outside its declared band" is a criterion. "The economy feels balanced" is
     not — unless it names WHO decides and when, which makes a subjective criterion valid.
     An unowned subjective criterion is not a criterion. -->

---

## After this one

<!-- One line per phase, in order, and no more than a line. What it will find out is
     enough; scope and criteria are written when it becomes current. Reordering this list is
     a decision and belongs in docs/PROJECT.md with its reasoning — this is the view, not the
     authority. Sources: rolling-wave planning (detail when a stage becomes near); an
     architecture decision record is superseded, not edited (Nygard, cognitect.com 2011). -->

{{LATER_PHASES}}
