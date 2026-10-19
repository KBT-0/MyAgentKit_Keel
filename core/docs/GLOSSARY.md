# Glossary

Two lists, read by an agent when it writes to {{OWNER_NAME}} (`docs/COMMUNICATION.md`,
"Language and terms"); never loaded automatically. The first list comes from the setup
interview and grows whenever the owner says a term needs no explanation; the second grows
whenever the owner asks what a term means.

## Terms {{OWNER_NAME}} knows (not explained)

{{KNOWN_TERMS}}

## Kit terms (explained at first use in a message)

- **brief**: the written task prompt a worker receives (`docs/HANDOFF.md`).
- **compaction**: the tool summarising a long conversation to free space; details are lost.
- **critical work**: architecture, a gate's or the review tooling's design, or a security
  boundary; a mark beside the risk tier, `Risk: <tier> (critical)`, with its own author and
  reviewer rule
  (`docs/WORKFLOW.md`, "Model routing", rule 7).
- **context**: everything the model reads on each request; it grows all session and is paid
  for on every turn.
- **dogfood**: using a new kit release in real project work, with extra care, before it is trusted.
- **effort**: the model's thinking-depth setting (low, medium, high).
- **gate**: an automatic check that must pass before a commit or merge (`scripts/check.sh`).
- **handoff**: the note one session leaves so the next can continue without chat memory.
- **hook**: a small program the tool runs by itself on an event, such as before a tool call
  or when the agent finishes a turn; the agent cannot forget it.
- **label**: the name of one review series; at most two rounds per label.
- **lead / worker**: the session talking to the owner, and a session or sub-agent it starts
  for one task.
- **review round**: one pass of a fresh reviewer over a change, with its findings.
- **review tooling**: the code that runs a review (`scripts/review.sh`, the review bridges
  and dispatcher, a reviewer's agent definition).
- **risk tier**: low, medium or high, the brief's `Risk:` line; it names the review a change
  gets (`docs/REVIEW_GATE.md`, "Risk tiers").
- **route**: the brief's `Route:` line, the task's shape: `quick`, `build` or `deep`
  (`docs/WORKFLOW.md`, "Model routing").
- **sensor**: a deterministic check added to the gate for a class of bug reviewers kept
  finding.
- **state helper**: `scripts/working_mode.py --read-state` / `--replace-state`, the
  compare-and-swap way a shell write changes `docs/STATE.md` (`docs/AGENTS.md`).
- **token**: the unit the model counts text in and is billed by, roughly a word fragment.
- **worktree**: a second checkout of the same repository in another folder, so two tasks do
  not touch the same files.
