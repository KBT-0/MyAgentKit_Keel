# Phases — what we are building now, and what we are deliberately not

Read every session: the CURRENT phase in full, every later phase in one line. When a phase
closes, its permanent findings move to their homes and its detail is deleted; the reasons
are in `docs/WORKFLOW.md`, "The state, backlog and phase files".

---

## Current phase: {{CURRENT_PHASE}}

**The question it answers:** {{PHASE_QUESTION}}

<!-- One sentence. What do we not know, or what risk are we retiring? If it cannot be put as
     a question, the phase is a wish list rather than a phase. -->

**In scope**

{{PHASE_IN_SCOPE}}

**NOT in scope — do not build these yet**

{{PHASE_OUT_OF_SCOPE}}

<!-- Spend as much effort here as on the list above. Each entry names the phase it belongs to
     instead, so "not yet" does not read as "never". An agent that finds itself needing
     something on this list STOPS and reports rather than quietly widening the phase. -->

**Done when**

{{PHASE_ACCEPTANCE}}

<!-- Commands or observations, never adjectives. "The simulation runs 100 days at seed 42
     with no price outside its declared band" is a criterion. "The economy feels balanced" is
     not — unless it names WHO decides and when, which makes a subjective criterion valid.
     An unowned subjective criterion is not a criterion. -->

---

## After this one

<!-- One line per phase, in order, and no more than a line. The question it will answer is
     enough; scope and criteria are written when it becomes current. Reordering this list is
     a decision and belongs in docs/PROJECT.md with its reasoning — this is the view, not the
     authority. -->

{{LATER_PHASES}}
