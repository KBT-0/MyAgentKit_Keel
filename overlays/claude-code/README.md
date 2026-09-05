# Overlay: Claude Code

Install with `bootstrap.sh . --overlay claude-code`. This README is NOT copied — only
`files/` is.

**The commands live in the plugin, not here.** `/myagentkit:handoff`,
`/myagentkit:cross-review` and `/myagentkit:kit-feedback` are installed once per machine:

```
/plugin marketplace add KBT-0/MyAgentKit_Keel
/plugin install myagentkit@myagentkit
```

Those two lines are typed by a human — an agent cannot invoke slash commands. This overlay
is the part that has to be copied into each project instead, because every file in it is
project-specific.

## Why this split

A command is the same in every project, so it belongs in a versioned plugin you install once
and upgrade in place. The files below are not: they carry `{{PLACEHOLDERS}}` that the setup
interview fills with THIS project's boundaries, risky areas and gated paths. A plugin cannot
hold them, and copying a command into every project would mean fixing a bug in it once per
repository.

## What it adds

| File | What it is |
|---|---|
| `CLAUDE.md` | One-line pointer to `AGENTS.md`. Content never goes here |
| `.claude/settings.json` | Registers the three hooks below |
| `.claude/hooks/gate_on_stop.sh` | Runs the gate if a turn left the watched paths dirty — early feedback, never the rule |
| `.claude/hooks/guard_boundaries.py` | Flags a forbidden import the moment it is written, seconds instead of a commit |
| `.claude/hooks/guard_destructive_git.py` | Refuses `reset --hard`, `checkout --`, `clean -f`, `stash drop` and force pushes while the tree is dirty, and prints what would be lost |
| `.claude/agents/diff-reviewer.md` | Read-only review subagent carrying THIS project's risky areas and `docs/REVIEW_GATE.md` |

## Why this is an overlay and not part of the core

The kit's rules are tool-agnostic: `AGENTS.md`, the workflow, the review protocol, the state
file, `scripts/check.sh`, the git hook and CI all work under any CLI agent, or none.

These files do not. They are Claude Code's config format — its hook events, its subagent
definition. Shipping them in the core meant every project got a `.claude/` directory whether
or not anyone used that tool, and it let the kit imply a neutrality its automation did not
have. An engine is an overlay here; so is a host agent.

If you use a different tool, take the IDEAS: the hooks are worth reproducing, and the
commands are thin wrappers over `docs/HANDOFF.md` and `docs/REVIEW_GATE.md`, which are in
the core and readable by anything.

## What `/myagentkit:cross-review` needs

A SECOND CLI on the machine — a DIFFERENT model from the one authoring the change, in
whichever direction the project configured. `scripts/review.sh` ships adapters for two,
selected with `--reviewer codex` or `--reviewer claude`, and both archive the same evidence.
Install the other one and log in, or the command reports that it is missing and falls back to
the paste-by-hand template in `docs/REVIEW_GATE.md`.

This overlay is for Claude Code as the HOST, not for Claude Code as the author. A project
where Codex writes and Claude reviews still installs it if anyone opens Claude Code in the
repository. There is no `overlays/codex/`, and
[docs/delegation-is-not-symmetric.md](../../docs/delegation-is-not-symmetric.md) says why.

The vendor plugin (`openai/codex-plugin-cc`) is OPTIONAL and is not used by
`scripts/review.sh`; it adds in-session delegation commands, which the kit does not ship for
this direction. `docs/DEV_SETUP.md` §3 covers
both, including the two cautions worth reading before installing it.

Install it ALONGSIDE `/myagentkit:cross-review`, not instead of it. Its `/codex:review` is a
review TOOL — a second model over your git state, generic and fast. `/myagentkit:cross-review`
is the review GATE: it carries this project's own priority order, requires the caller to
verify each finding instead of relaying it, archives the report as evidence under
`docs/reviews/`, and ends in a verdict whose manual checks land in `docs/STATE.md` before the
commit. Different jobs. The kit README's "Recommended setup" section spells the difference
out.

## The hooks are not the gate

`.githooks/pre-commit` is. These fire earlier and only in one tool; they exist to shorten the
feedback loop, not to carry enforcement. Nothing here is load-bearing — deleting the whole
overlay leaves every rule intact and every gate running.
