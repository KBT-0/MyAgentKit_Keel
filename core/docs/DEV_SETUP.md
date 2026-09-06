# Dev setup — per clone

Things git cannot carry inside a commit. Run them once in every fresh clone, on every
machine — and note that a Windows shell and a WSL shell on the same box count as two
separate setups.

## 1. Wire the commit gate

```sh
git config core.hooksPath .githooks
```

`.githooks/pre-commit` runs `./scripts/check.sh` and aborts the commit when it fails.
`core.hooksPath` is local configuration, not repository content, so **a clone without this
line has NO gate** — the commit succeeds and CI catches the problem later, if at all.

Verify it is live:

```sh
git config core.hooksPath        # -> .githooks
```

`git commit --no-verify` skips the gate. That hatch exists for {{OWNER_NAME}}'s WIP commits.
Agents must not use it (`AGENTS.md`).

## 2. Toolchain on PATH

`check.sh` needs {{TOOLCHAIN}}. Per-user installs are the usual trap here: they work in your
interactive shell and are missing from the non-login shell a git hook runs in, so the gate
fails for a reason that has nothing to do with the code.

{{TOOLCHAIN_SETUP_NOTES}}

If the gate fails with "command not found", that is this — not a broken build.

## 3. The second model — only if you want cross-model review

`docs/REVIEW_GATE.md` asks for risky diffs to be reviewed by a DIFFERENT model in a fresh
session. `scripts/review.sh` automates that, and it needs a second CLI on this machine.

**Ask your agent to set this up for you.** It can install the CLI and check the wiring; the
parts it cannot do are called out below. Nothing here is required to write code — the gate,
the hooks and CI all work without it. Skip it and the review protocol becomes the
paste-the-template-by-hand version in `docs/REVIEW_GATE.md`, which is a real fallback, not a
consolation prize.

**Required: the reviewing CLI itself.**

`scripts/review.sh` uses the project's configured default reviewer and pinned models.
For the Codex direction (`codex exec -s read-only …`), check:

```sh
command -v codex          # already there?
```

If not, install it and log in. Point the script
somewhere else with `REVIEW_CLI_BIN`, but note that only swaps the BINARY — a CLI with a
different flag interface needs a matching adapter. For Claude Code, the kit ships one:
use `./scripts/review.sh --uncommitted --reviewer claude`. This requires Python 3.10+
and an installed, authenticated Claude CLI. `CLAUDE_CLI_BIN` selects that binary; the
adapter pins read tools and structured output. The Codex-host plugin also supports
`$myagentkit-review` and `$myagentkit-delegate` after installation from the kit marketplace.
Python 3.10+ is also required by `scripts/review.sh --self-test` and the review tests included
in `scripts/check.sh --self-test`, even when Codex is the only reviewing CLI.
Both live adapters now require Python as well, to bound the child process and preserve usage
on failure. The following is the canonical companion list for an existing-project upgrade.
Copy every listed file from the kit's `core/scripts/` into your project's `scripts/`
alongside the updated `review.sh`; reapply the project's default reviewer and model pins.

<!-- REVIEW_COMPANIONS_START -->

`review_dispatch.py`, `claude_bridge.py`,
`codex_bridge.py`, `agent_process.py`, `agent_usage.py`, `test_claude_bridge.py`, and
`test_agent_usage.py`, plus `codex_quota.py` and `test_codex_quota.py`.

<!-- REVIEW_COMPANIONS_END -->

Merge `.myagentkit/`
into the root ignore rules. Also merge the raw review/handoff archive exclusions and final
summary re-include from the kit's `core/.gitignore`. The adapters refuse to launch if
private storage is not ignored or raw records are already tracked. Preserve any existing
records locally before removing them from Git's index; never delete them as part of an
upgrade. Private storage cannot use symlinked directories. See `docs/USAGE.md`.

Verify it end to end before trusting it — one real invocation, on a small diff:

```sh
./scripts/review.sh --uncommitted
```

A stub or a dry run does not count. A wrapper validated only against a fake CLI is a wrapper
that has never met the real contract (`docs/GOTCHAS.md`).

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
name. The [official marketplace manifest](https://github.com/openai/codex-plugin-cc/blob/main/.claude-plugin/marketplace.json)
was checked on 2026-09-06. A successful marketplace-add message names the registered
marketplace; do not retry registration under an inferred repository name.

An agent can prepare the configuration for you and tell you what to type; the typing and the
restart are yours.

Two cautions if you install it:

- **Check which of its commands a MODEL can invoke.** If any are model-invocable, a session
  can spend the other tool's budget without you deciding to. Write the project rule down:
  no session calls the second tool unless you asked for it in that session.
- **Leave any automatic review gate OFF.** The tempting setting makes the second model
  review every turn and block until fixes are applied. Unattended agent-to-agent loops burn
  a budget fast. All review here is manually triggered — record that decision so nobody
  turns it on later as a convenience.

Tool names, install commands and flags all rot. `setup/RESEARCH_PROTOCOL.md` is what keeps
this section current; if it disagrees with reality, reality wins and this file is wrong.

## 4. Prove the gate actually works

Once, on a fresh clone:

```sh
./scripts/check.sh --self-test
```

It injects each gate's failure condition and asserts the gate rejects it. A green
`CHECK: PASS` tells you the tree is clean; only the self-test tells you the gate could have
told you otherwise.

{{PROJECT_SETUP_STEPS}}
