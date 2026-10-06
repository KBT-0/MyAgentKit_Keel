# MyAgentKit_Keel

A foundation for codebases that AI agents write and maintain. It installs rules that a
script enforces, one memory file that every tool and session reads, a review gate that a
second model runs, and a way to spawn, watch and close worker sessions without losing
work. Every project of mine is built on it, and what a project learns can flow back.

**v0.9.** The kit's own check (`./scripts/check.sh --self-test`) runs on Ubuntu and macOS
with Python 3.10 and 3.14 in CI, and every gate in it has a negative test that was watched
going red. Each version was reviewed by two models that did not write it, and the raw
reports are kept in [docs/reviews](docs/reviews/). [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)
says what was executed and what was not.

## What it solves

A codebase written by agents decays in four ways, and a better prompt fixes none of them.

| Failure | What the kit does instead |
|---|---|
| A rule written as prose erodes; an instruction file is a request. | A rule lives in `scripts/check.sh` and the git hooks. Crossing it fails the commit. Every gate ships with a test that proves it can fail. |
| Memory dies with the session and never crosses tools. | `docs/STATE.md` is the only cross-tool memory. If it is not there, it did not happen. Knowledge has three horizons and three files: `PROJECT.md` (decided), `PHASES.md` + `BACKLOG.md` (now and parked), `STATE.md` (this moment). |
| The author reviews its own change. | Review is a gate run by a fresh session, by default a different model, in a throwaway copy where it can execute. Its output is evidence to verify, never a verdict to relay. |
| Delegated work is invisible until it is wrong. | A spawned worker is a visible terminal tab, watched by a script that reports when it waits on a person, asks a question, or finishes; its worktree is removed after the merge only when nothing in it can be lost. |

## Install

```sh
git clone https://github.com/KBT-0/MyAgentKit_Keel.git
cd /path/to/your-project
/path/to/MyAgentKit_Keel/bootstrap.sh .                        # rules, gates, hooks
/path/to/MyAgentKit_Keel/bootstrap.sh . --overlay claude-code  # + worker and review tooling for Claude Code
/path/to/MyAgentKit_Keel/bootstrap.sh . --overlay unity        # + the engine layer, if it applies
```

`bootstrap.sh` copies files, wires `.githooks`, records the kit version, and asks nothing.
It skips a file that already exists, so it is safe inside a project under way. The
decisions the kit needs are made in a conversation: open your agent in the project and say

> Read `setup/INTERVIEW.md` and start the setup.

The interview fills every `{{PLACEHOLDER}}` with an answer you gave. `scripts/check.sh`
fails while any placeholder survives. Pass `--note "..."` to `bootstrap.sh` to leave an
agenda the interview must address.

**Once per machine.** The review gate wants a second model on the machine: with Claude
Code as the host, install the Codex CLI; with Codex as the host, install Claude Code. The
interview asks and can install it. With Claude Code, you type these two (an agent cannot):

```
/plugin marketplace add KBT-0/MyAgentKit_Keel
/plugin install myagentkit@myagentkit
```

That adds `/myagentkit:cross-review`, `/myagentkit:handoff` and `/myagentkit:kit-feedback`.
With Codex as the host:

```sh
codex plugin marketplace add /absolute/path/to/MyAgentKit_Keel
codex plugin add myagentkit@personal
```

That adds the `$myagentkit-review` and `$myagentkit-delegate` skills
([docs/CODEX.md](docs/CODEX.md) has the limits).

## What a project gets

| File | Role |
|---|---|
| `AGENTS.md` | The constitution. Every agent reads it first, every session. `CLAUDE.md` and friends are one-line pointers to it. |
| `docs/PROJECT.md` | Design authority: what the project is and every decision, each DECIDED or OPEN. An agent never marks DECIDED on its own. |
| `docs/PHASES.md`, `docs/BACKLOG.md` | What is being built now, what is out of scope, the next and parked tasks with ids. |
| `docs/STATE.md` | Cross-session work state. A commit's `Done: <id>` trailer closes a task; the gate refuses a commit that leaves a closed task open. |
| `docs/ARCHITECTURE.md`, `docs/GOTCHAS.md` | The module map with its boundaries; the traps the project already paid for. |
| `docs/WORKFLOW.md` | How a task runs: the cheapest proof, when a worker is worth its cost, review rounds, the lead's steps, the worker lifecycle. |
| `docs/REVIEW_GATE.md`, `docs/REVIEW_RUNNING.md` | What a review must attack first and how a verdict is reached; how a review is run. |
| `docs/HANDOFF.md` | One self-contained brief for another tool, model or session, and the result file it writes back. |
| `scripts/check.sh` | The gate. CI runs the same script. `--self-test` proves every gate goes red. A documentation-only commit skips the build. |
| `scripts/review.sh` | The cross-model review: a second model in a throwaway copy, with archived evidence. |
| `scripts/doctor.sh` | A machine check at session start: what is missing, and the fix for each. |
| `scripts/boundary_checks.sh` | The import and dependency boundaries, each with a self-test. |
| `.githooks/` | `pre-commit`, `commit-msg`, `pre-merge-commit`, `post-merge`: the gate, the trailer grammar, the full gate before a merge, the worktree clean-up after one. |

The `claude-code` overlay adds `scripts/spawn_worker.sh`, `show_workers.sh`,
`watch_workers.sh`, `close_worker.sh` and `clean_worktrees.sh`, the `diff-reviewer` and
`worker` sub-agents, and three editor-side hooks (a boundary guard as you type, a refusal
of destructive git over uncommitted work, the gate at every turn end). The hooks shorten
the loop; the gate does not depend on them.

## How work runs

1. A session starts with `./scripts/doctor.sh`, then `AGENTS.md`, `PHASES.md`, `STATE.md`.
2. A task is small, in one module, with a definition of done that a gate can check.
3. The lead does a short task itself. A task that will take about an hour or more than one
   review round goes to a worker: a fresh session with a brief, in its own worktree, in a
   visible tab. The worker reviews its own diff with fresh reviewers before it reports, and
   writes a result file whose first lines say `Kind`, `Task`, `Attempt`, `Remaining`.
4. The watcher reports `DONE`, `BLOCKED`, `HANDOFF`, `PROGRESS`, a question, or a prompt
   that waits on a person. The lead merges, folds the docs, and closes the worker.
5. A risky diff, and every change to a gate, goes through `scripts/review.sh`. The reviewer
   runs the suite and its reproductions in a throwaway copy and marks each finding
   `REPRODUCED` or `REASONED`. The calling agent verifies every finding against the code and
   writes the verdict and any manual checks into `STATE.md` before the commit.
6. `post-merge` removes a finished worker's worktree when its commits are in the main branch,
   nothing in it differs from the index, it has been quiet for an hour, and no process has it
   open. A loose commit is saved under `refs/kit/saved/` first. A branch is never deleted.

## The review gate

`scripts/review.sh --base <ref> | --commit <sha> | --uncommitted [--reviewer codex|claude]`
runs the second model and writes
`docs/reviews/<UTC-timestamp>-<id>-<reviewer>-review.md`: which model, whether it attested
its identity, effort, sandbox, limits, scope, HEAD, the checkout fingerprint (working tree
and index) and the diff hash. The file is never edited afterwards.

It fails closed. The reviewer works in a copy the adapter builds from the checkout's bytes
under one deadline; a write that reaches the repository fails the review as
`stale_checkout`; the three scope flags are the only arguments; an empty change set, a
missing verdict line, an unpinned model, or a provider's content classifier stopping the
run is a failure, never a pass. A reviewer's `Reject` is input to the calling agent's own
decision, and a relayed verdict in either direction is a failed review.

## Updates

A file is kit-owned (it carries a `KIT-OWNED` header; `sync-kit.sh` overwrites it) or
project-owned (customised at setup; never overwritten). `sync-kit.sh` refreshes the
kit-owned files, prints the `CHANGELOG.md` entries since the project's recorded version
with their **ACTION** items as one ordered checklist, and records the new version only after
`--actions-applied`. A project file at a path the kit has since made kit-owned stops the
sync as a `conflict:` before anything is copied.

## Requirements

POSIX `sh`, git (2.36 or newer for the worktree clean-up), Python 3.10 or newer for the
review tooling and the kit's own tests. Ubuntu and macOS are in CI. The kit is developed under WSL,
where the owner also runs it with Windows Terminal tabs (on native Windows Python the kit's tooling imports,
but a review run, the gate lock and the worktree clean-up need a POSIX host). One AI CLI runs the project; a second one runs
the review gate. Without either, the rules, the gate and the hooks still work.

## Feedback upstream

The kit improves fastest from the projects that hit its edges. The setup interview asks
once whether the agent may offer to send a finding upstream; `/myagentkit:kit-feedback`
strips the project out of the text, shows the exact body, and sends nothing until you say
yes. [CONTRIBUTING.md](CONTRIBUTING.md) is the same process by hand, and
`RESEARCH_LOG.md` holds every dated finding with its verdict, rejections included.

## Repository map

| Path | What it is |
|---|---|
| `bootstrap.sh`, `sync-kit.sh` | Install into a project; propagate a kit update into one. |
| `setup/` | The interview an agent runs with you, and the research protocol it follows. |
| `core/` | What every project receives: the constitution, the docs, the gate, the hooks, the review tooling. |
| `overlays/` | Optional layers: `claude-code` (workers, sub-agents, hooks), `unity` (assembly layout, the batchmode test gate, an MCP server). |
| `plugin/`, `plugins/myagentkit/` | The Claude Code plugin and the Codex plugin, installed once per machine. |
| `patterns/` | Optional reading on specific designs. |
| `docs/` | The rationale for each rule, the acceptance record, the review archive. |
| `scripts/`, `tests/` | The kit's own check and its test suites. |
| `CHANGELOG.md`, `RESEARCH_LOG.md`, `CONTRIBUTING.md` | What changed and how to upgrade; why; how to send something back. |

## Origin

Every rule here is in the kit because something broke without it; the failures are
written up in `RESEARCH_LOG.md`.

MIT licensed.
