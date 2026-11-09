<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->
# Worker rules (the hard rules of AGENTS.md)

You are a worker: a lead session started you with a brief. These rules bind; the brief names
what to read and what you own. Everything else in `AGENTS.md` is the lead's, read by section
only when the brief or a rule below points there.

## What blocks a commit (violation = failed task)

- One change inside the brief's `Owns:` paths; more is a STOP. No drive-by refactors.
- A logic change brings its test. A test runs in its own command and is read before any commit:
  never `test; git commit`, never piped through a filter.
- The commit hook runs `./scripts/check.sh` and refuses a red commit; do not run the full gate
  by hand unless the brief says so. A commit whose output lacks `CHECK: PASS` ran no gate: say so.
- **Never `git commit --no-verify`** or another way past the gate. **No AI attribution in git**,
  by trailer or prose.
- A git command line holding `--out`, `--ext`, `--textc` or `--sub` is denied, a commit message
  included: write the message to a `mktemp` file in a step of its own, then `git commit -F FILE`.
- **No push, PR or remote update**, ever, from a worker.
- **Commit or stash BEFORE any command that discards work**, after `git status`; a recursive
  delete first proves it owns the folder (`docs/WORKFLOW.md`, "Destructive commands").
- **Never end running work** you did not start unless it is provably finished or hung
  (`docs/WORKFLOW.md`, "Ending running work").
- Docs, code, identifiers, comments and commits: English.

## Checks

- The brief's `Checks:` line is what you run on top of the commit hook, never instead of it:
  the cheapest check that proves the change (`docs/WORKFLOW.md`, "Model routing — by cost per
  task and by scarcity").
- A brief with a `NAME.checks` file: run `sh scripts/run_checks.sh /abs/path/NAME.checks` (the `Checks:` line names it by absolute path) once and read its
  result file once (`docs/HANDOFF.md`, "The brief").
- **Never report a verification you did not run**; say "not run". A required check that cannot
  run is a STOP.
- **Read narrow:** grep or a range first, never a whole log or a file over 300 lines.

## The result file and questions

- Your result file's first four lines are `Kind:`, `Task:`, `Attempt:`, `Remaining:`; its last
  line is the marker the brief's instruction names. Publish it whole with `codex_worker.py
  --publish`, as the instruction says; an unpublished result is never seen.
- **Ask the owner nothing** in your pane: nobody may be watching it. A decision you cannot make
  from the brief or these rules is a published `Kind: blocked` result and a QUESTION file; go on
  with what does not depend on it.
- The report is short (about 350 words); long output goes to a file.

## The context band

Plan the cut at 150k tokens; at the next clean stop past 200k commit the green work and publish
`Kind: handoff`; stop at 300k (`docs/WORKFLOW.md`, "Worker cost — waits and long lives are what
you pay for", rule 8).

## STOP (publish `Kind: blocked` with the question)

- A DECIDED item of `docs/PROJECT.md` would break, an OPEN one needs deciding, or the work
  needs something on the `docs/PHASES.md` out-of-scope list.
- A new dependency or MCP server is needed.
- A test would be deleted, skipped or weakened unasked, or a gate changed without a red proof
  (`docs/WORKFLOW.md`, "Writing a gate").

## Pointers (read only when the task needs it)

- Architecture boundaries and public contracts: `AGENTS.md`, "Architecture boundaries (most are
  also compiler/CI-enforced)".
- Risky areas and the review gate: `AGENTS.md`, "Review gate and validation honesty"; name a
  touched risky area once in the report.
- A bug of the same cause in a file you change: `AGENTS.md`, "Task discipline".
- Writing style and registers: `AGENTS.md`, "Language & style".
- Closing-summary notes: `AGENTS.md`, "MENTION ONCE — one line in your closing summary, never
  mid-work".
- A folder's own `AGENTS.md` / `README.md` is read before you edit that folder.
