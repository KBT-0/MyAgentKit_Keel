<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->

# DEV_SETUP — the kit's part

The kit's generic rules of `docs/DEV_SETUP.md`, under its headings. The project's file keeps
its placeholders, its owner's decisions and its own rules, and each heading there whose text
moved ends with a "Kit rules:" line naming the heading here. This file is the kit's, and a sync
replaces it. Generic rules live here by the owner's decision of 2026-10-22 (docsowned question
1, #94); the rule that a kit-owned file holds only reasons (`docs/WORKFLOW_RATIONALE.md`) is
`docs/WORKFLOW.md`'s alone. Do not edit it: a project that needs a different rule writes it in
`docs/DEV_SETUP.md`, the project-owned file, and the project file wins over this one.

## 3. The reviewing model — the Claude CLI alone is enough

This part follows the reviewing CLI and the optional second backend, which stay in
`docs/DEV_SETUP.md`, section 3.

**Optional: the vendor plugin for your host agent.**

Separate from the above, and NOT needed by `scripts/review.sh`. If your host agent has an
official plugin for the reviewing tool, it adds in-session commands without the copy-paste
loop. For Claude Code and Codex that is `openai/codex-plugin-cc`, which contributes:

- `/codex:review` — a Codex review against local git state.
- `/codex:adversarial-review` — a review that challenges the design, the tradeoffs and the
  assumptions rather than hunting implementation defects. Worth knowing separately: it asks
  a different question from the one `scripts/review.sh` asks, so it complements the gate
  instead of duplicating it.
- `/codex:rescue` — hand an investigation, or a fix you are stuck on, to a Codex subagent.
- `/codex:transfer` — move the whole session into a resumable Codex thread.

Installed with two slash commands **a human has to type** (an agent cannot invoke slash
commands):

```
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
```

The repository is `openai/codex-plugin-cc`, but its marketplace declares the name
`openai-codex`; `/plugin install` uses that declared name after `@`, not the repository
name (the marketplace name is the `name` in its `marketplace.json`:
code.claude.com/docs/en/plugin-marketplaces). The [official marketplace manifest](https://github.com/openai/codex-plugin-cc/blob/main/.claude-plugin/marketplace.json)
was checked on 2026-09-06. A successful marketplace-add message names the registered
marketplace; do not retry registration under an inferred repository name.

An agent can prepare the configuration for you and tell you what to type; the typing and the
restart are yours.

Two cautions if you install it:

- **Check which of its commands a MODEL can invoke.** If any are model-invocable, a session
  can spend the other tool's budget without you deciding to. Do not rely on a written rule
  alone: add a deny rule for its model-invocable commands to the project's permissions
  (`Skill(<name> *)`), or for the whole Skill tool, so the harness blocks the call
  (code.claude.com/docs/en/skills).
- **Leave any automatic review gate OFF.** The tempting setting makes the second model
  review every turn and block until fixes are applied. The plugin's README warns that it
  "can create a long-running Claude/Codex loop and may drain usage limits quickly" and to
  enable it "only when you plan to actively monitor the session". All review here is manually triggered — record that decision so nobody
  turns it on later as a convenience.

Tool names, install commands and flags all rot. `setup/RESEARCH_PROTOCOL.md` is what keeps
this section current; if it disagrees with reality, reality wins and this file is wrong.

## 4. Check the machine — every session start, every machine

```sh
./scripts/doctor.sh
```

It changes nothing in the project and prints one `MISSING: <what> — fix: <command>` line per
trap, then `DOCTOR: ready` or `DOCTOR: setup incomplete` (exit 1). It checks what made a gate
fail for reasons unrelated to the code in the projects using the kit: the executable bit on
the scripts and hooks (on disk and in the git index), `core.hooksPath`, the git identity,
Python 3.11+, the reviewing CLI `scripts/review.sh` calls (the Claude CLI in solo mode),
`tmux` when the worker script is
installed, the `node` a git hook resolves (nvm's default alias lives in the interactive
shell's rc file, so a hook never sees it), an npm cache owned by another user, and `grep`
shadowed by an alias or function in the interactive shell. To see that alias it starts your
interactive shell once (`$SHELL -ic`), so your rc files run, bounded to 5 s and skipped with a
NOTE where `timeout` is absent. It is not part of the gate and CI does not run it. When switching machines, this is the first command.
(The doctor pattern: `claude doctor` and `codex doctor`, code.claude.com/docs/en/cli-reference.)
