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
| `.claude/agents/worker.md` | Implementation worker with a one-hour prompt cache and a 150-turn cap, for tasks that run jobs longer than five minutes (`docs/WORKFLOW.md`, "Worker cost") |
| `scripts/spawn_worker.sh` | Opens a SEPARATE worker session in tmux and hands it a brief file; the lead then subscribes for its idle notice instead of polling |

## Placeholders this overlay brings

| Placeholder | What goes in |
|---|---|
| `{{WORKER_MODEL}}` | The author model from the interview (`sonnet`, `opus`, or a full model id) |
| `{{LONG_JOBS}}` | The project's jobs that run longer than a few minutes, by name, as the interview's question 8 recorded them |
| `{{WORKER_EFFORT}}` | The worker's reasoning effort (`low`, `medium`, `high`), as the interview's question 8 recorded it: `high` when the worker's tasks bear design, lower when they are mechanical |

`diff-reviewer.md` ships with `effort: high` and no placeholder: reviews run at high effort.

If the project has no such jobs, delete both files instead of filling them.

## Worker sessions — what cost a session each before it was written down

- **Separate sessions and one-hour sub-agents cost the same.** Both were measured against a
  sub-agent with the default five-minute cache on the same task; both avoid the re-writes.
  Choose by visibility: a tmux session can be watched and survives the lead ending.
- **A new `.claude/agents/*.md` file is not loaded by a running session.** Restart the
  session (or spawn the worker from a session started after the file existed) and verify in
  the worker's transcript that its cache writes are `ephemeral_1h`, which
  `scripts/agent_cost.py` prints in its `1h/5m` column. The one-hour cache is ignored while
  the account runs on usage credits.
- **The prompt must never follow a variadic flag.** `claude --allowedTools A,B "prompt"`
  reads the prompt as one more tool name and opens idle at an empty input line.
  `spawn_worker.sh` pastes the brief after the TUI is up for that reason.
- **A standalone `sleep` in a Bash tool call is refused by the tool**, so a worker cannot
  even wait badly; it starts the job in the background and is re-invoked when it exits.
- **`pgrep -f` matches its own command line** (`docs/GOTCHAS.md`).
- **An untrusted folder blocks a spawned session in the trust dialog.** Open the folder once
  by hand before the first spawn; the script reports the dialog instead of waiting.
- **Decide the permission mode of spawned sessions with the owner before the first one.** A
  permission prompt stalls an unattended session, and an agent never widens permissions on
  its own. In the founding project the owner chose the same auto mode the lead sessions use,
  with the project hooks active and no allow-list; a narrow `--allowed-tools` list is the
  alternative where the owner wants it, at the price of a stall on any command outside it.
- **The worker definition's body carries the project's job rules**, not only the kit's: the
  lock that serialises heavy jobs, the memory ceiling, the environment variable a worktree
  needs. The interview's question 8 asks for them; without them the first worker learns them
  from a crash.
- **The idle notice fires every time the worker parks on a background job**, not only at
  the end: a session whose turn ended with a job running is "idle" to the harness, and the
  same notice was delivered three times for one pilot. Subscribe once, and have the brief
  end with a result FILE (plus, if the lead wants a push, one message from the worker);
  re-subscribing on every notice is a poll loop in disguise.
- **A sub-agent inherits its lead session's effort unless its definition sets `effort:`**,
  and nothing in its output says so: a side-by-side comparison ran two sub-agents at the
  lead's medium against a high-effort run of another CLI, and the skew surfaced only in the
  transcripts. Both definitions here set it. A spawned session takes the user's default
  effort instead; pass `--effort` to the spawn script. `scripts/agent_cost.py` does not show
  effort, so verify it after the run by grepping the transcript for `"effort"`.
- **A spawned session does not end when its task does.** A pilot worker wrote its result
  file and then sat idle in tmux for 40 minutes until it was killed by hand, and the idle
  notice cannot tell that apart from a park on a background job (above). The LEAD closes
  it: read the result file, then `tmux kill-session -t NAME`. The brief says so, and
  `spawn_worker.sh` prints the line when it starts the session.
- **Every message to an idle session is a full-context turn.** Ask the brief for a result
  FILE, subscribe once with `notify_when_idle`, and read the file.

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
