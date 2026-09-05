# MyAgentKit_Keel

A foundation for codebases written mostly by AI agents: rules that are **enforced rather
than requested**, memory that survives across tools and sessions, and a setup that
**researches its own ecosystem** instead of shipping advice that was true once. It is not a
template you copy and outgrow — installation is a conversation with an agent, and every
project that uses it can push what it learned back into the kit.

> **Status: v0.7 development — extracted from a codebase in active use.** `bootstrap.sh` produces a
> working skeleton in an empty directory, and each gate has a negative test that was
> observed making it fail. v0.1 was reviewed by two other models and **both returned
> Reject** — seventeen findings, then eleven more against the first round's fixes, because
> the fix for a fail-open scanner was itself fail-open. All are fixed and the reports are in
> [docs/reviews](docs/reviews/). Later versions carry their own review debt where it
> applies; [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md) records exactly what was executed and
> what was not.

Part of my `MyFramework` line of personal foundations — this is the AI-agent one.

## The problem

Codebases written by agents decay as they grow: the same system gets built twice because
nobody could find the first one, and each new session is a little less able to navigate
what the last one wrote. Rules written as prose erode, because nothing enforces them — an
instruction file is a request, and requests get skimmed. Memory fragments: chat history
does not cross sessions, and it certainly does not cross tools, so what the last session
learned is gone. And the tooling underneath all of this moves faster than any one person
can track, so a setup that was current in March is quietly stale by June.

None of that is fixed by a better prompt. It is fixed by structure.

## Core principles

- **Rules live in the compiler and CI, not in prose.** If a boundary matters, a script
  fails when it is crossed.
- **A gate is not finished until it has been proven to go RED**, and it ships with an
  automated negative test. A gate that has only ever been seen passing is an untested
  branch running on every commit.
- **One canonical instruction file.** Tool-specific files (`CLAUDE.md` and friends) are
  one-line pointers to it, never a second copy.
- **If it is not in the state file, it did not happen.** That file is the only cross-tool
  memory — and it is transient: permanent knowledge passes THROUGH it into a real home.
- **Knowledge has three horizons, so it has three files.** What the project IS and has
  decided (permanent), what we are building now and deliberately NOT building yet
  (episodic), and what is happening right now (momentary). Collapsing them is how a state
  file becomes a diary and a design document stops being true.
- **The author of a change never reviews it.** Review happens in a fresh session,
  preferably a different model, because the value of a second opinion is that it is
  decorrelated.
- **Small tasks, one module, a verifiable definition of done.** Validation is a gate you
  can run, never the implementer's self-report.
- **Every tool must earn its permanent context cost.** The default verdict on a new tool,
  server or dependency is *no*.
- **What a project learns flows back, if you want it to.** A foundation improves fastest
  from the projects that hit its edges — so one command sends a finding upstream, after
  showing you exactly what it would say. Opt-in, asked once at setup, never on the agent's
  own initiative.

## Quick start

```sh
git clone https://github.com/KBT-0/MyAgentKit_Keel.git
cd /path/to/your-project
/path/to/MyAgentKit_Keel/bootstrap.sh .                        # rules and gates
/path/to/MyAgentKit_Keel/bootstrap.sh . --overlay claude-code  # + hooks (recommended)
/path/to/MyAgentKit_Keel/bootstrap.sh . --overlay unity        # + engine layer, if it applies
```

Once per machine, if you use Claude Code, install the commands — **you** have to type these
two, an agent cannot invoke slash commands:

```
/plugin marketplace add KBT-0/MyAgentKit_Keel
/plugin install myagentkit@myagentkit
```

That adds `/myagentkit:cross-review`, `/myagentkit:handoff` and `/myagentkit:kit-feedback`,
at roughly 150 tokens of always-on cost. Then open your agent in the project and say:

> Read `setup/INTERVIEW.md` and start the setup.

For the review gate you also want a SECOND model on the machine — see
[Recommended setup](#recommended-setup-either-host-an-independent-second-opinion).
The setup interview will ask, and can install it for you.

`bootstrap.sh` copies files and configures git hooks. It does not ask you anything and it
does not fill anything in — that is the interview's job, because the decisions it needs
(what is risky here, which boundaries must be enforced, what the gates are) cannot be
answered by a script. Pass `--note "..."` to leave an agenda the interview must address.

## What's in the box

| Path | What it does |
|---|---|
| `bootstrap.sh` | Mechanical install: copy, mkdir, wire the git hooks path, record the kit version |
| `setup/INTERVIEW.md` | The real entry point — a conversational setup an agent runs with you |
| `setup/RESEARCH_PROTOCOL.md` | How the agent researches the current tooling ecosystem before advising you |
| `core/` | The universal layer: constitution, the three knowledge files (PROJECT / PHASES / STATE), architecture map, workflow, review gate, handoff template, gates, hooks |
| `overlays/` | Optional layers, added and never assumed: `unity` for the engine (assembly layout, the batchmode test gate, and a default MCP server — CoplayDev's tool-agnostic `MCP for Unity` — with the scoping traps that cost real time to find), `claude-code` for that tool's project-local hooks and review subagent |
| `plugin/` | The Claude Code plugin: the three `/myagentkit:*` commands. Installed once per machine, not copied per project |
| `plugins/myagentkit/` | The Codex plugin: Claude review-and-fix and implementation-proposal skills, with a bundled read-only adapter |
| `.agents/plugins/marketplace.json` | The local Codex marketplace catalog; install from the kit repository root |
| `patterns/` | Optional reading — the reasoning behind specific hard-won designs. Not copied by default |
| `docs/` | Long-form rationale: why each rule exists, and the failure mode it prevents |
| `sync-kit.sh` | Propagate kit updates into a project that already installed it |
| `RESEARCH_LOG.md` | Dated findings with verdicts — including rejections, so they are not re-litigated |
| `CONTRIBUTING.md` | How a project using the kit sends what it learned back |

## Recommended setup: either host, an independent second opinion

The kit's central review rule is that **the author of a change never reviews it**, and that
the value of a second opinion is that it is *decorrelated* — a different model, not the same
one asked twice. That needs two CLIs.

**Which one you put in the driver's seat matters much less than having two.** The pairing
below is the one this was built and used on, and it is a recommendation rather than a
requirement; swap either side and every rule and gate still works.

**Keep the host that suits the work.** Claude Code was the original main agent and remains
supported. Codex can now call Claude without leaving its session too. The previous claim
that only one direction could do this is no longer accurate. This integration does not
establish which model is better at managing or implementing a particular project.

With Claude Code you get:

- **`/myagentkit:cross-review`** (plugin) — the review gate as a command. This is the kit's
  own, and the section below explains why it is not the same thing as a review command.
- **`/myagentkit:handoff`** (plugin) — turns the current work into ONE self-contained prompt
  for another tool, model or session, so nothing depends on chat history the next reader
  cannot see.
- **A read-only `diff-reviewer` subagent** (overlay) — the review protocol without a second
  CLI, for when you want a fresh reviewing session rather than a fresh vendor.
- **Three editor-side hooks** (overlay) — a boundary guard that fires the moment a forbidden
  import is written, a refusal to run destructive git commands over uncommitted work, and
  the gate on every turn end. None is load-bearing; they shorten the feedback loop from
  "next commit" to "next second".

**Add the Codex CLI as the second model.** `scripts/review.sh` shells out to it and needs
only the `codex` binary — no plugin. Optionally add **OpenAI's `codex` plugin**
(`/plugin install codex@openai-codex`), which contributes `/codex:review`,
`/codex:adversarial-review` (challenges the design and the tradeoffs, not just the defects),
`/codex:rescue` for handing an investigation or a stuck fix to a Codex subagent, and
`/codex:transfer` to move the session into a resumable Codex thread.

### `/myagentkit:cross-review` and `/codex:review` are not the same thing

Install both. They answer different questions, and the difference is the whole point of the
gate.

**`/codex:review` is a review tool.** It runs a second model over your git state and hands
you its findings. Fast, generic, useful, and it knows nothing about your project.

**`/myagentkit:cross-review` is the review gate protocol**, which uses a second model as one input.
Four things it does that a review command does not:

1. **It makes you verify.** The reviewer's output is treated as *untrusted input*, never a
   verdict. The calling agent has to check every finding against the code, drop what it
   disproves, keep what it confirms, and say which is which — relaying a verdict unchecked
   is a failed review **in either direction**, including a relayed Accept. This is the
   load-bearing rule, and it is the one a generic review command cannot enforce, because it
   has no opinion about what you do with its output.
2. **It carries YOUR project's priorities.** The prompt is built from `docs/REVIEW_GATE.md`:
   your risky areas, your design authority, your worst failure mode reviewed first. A
   generic reviewer does not know that money paths in your codebase are more dangerous than
   everything else in it.
3. **It archives evidence.** Every run writes
   `docs/reviews/<UTC-timestamp>-<random>-<reviewer>-review.md` recording which model
   reviewed and whether that model is attested, reasoning effort, sandbox mode, limits,
   scope, HEAD, the checkout fingerprint and the diff hash — and that file is never edited
   afterwards. Both reviewers write the SAME format, so a project that swaps the author and
   reviewer roles can still line its records up. Six weeks later "was this reviewed, by what, at what
   setting?" is answerable instead of remembered.
4. **It ends in a verdict that goes somewhere.** `Accept` / `Accept with Manual Checks` /
   `Reject`, with any manual checks written into `docs/STATE.md` as full sentences *before*
   the commit — so an unverifiable claim becomes a standing obligation rather than a
   sentence in a chat log.

It also refuses to fail open: read-only is pinned in the wrapper rather than trusted to the
CLI, the three scope flags are the only arguments accepted (an agent cannot talk it into a
write-capable run), an empty change set exits nonzero instead of reporting a passed review,
and a report with no verdict line is a failure rather than a success.

Practically: reach for `/codex:review` or `/codex:adversarial-review` whenever you want
another pair of eyes. Use `/myagentkit:cross-review` when the gate applies — risky diffs, and every
change to a gate.

### Codex as the host

Install the kit's Codex plugin from the local checkout, then start a new thread:

```sh
codex plugin marketplace add /absolute/path/to/MyAgentKit_Keel
codex plugin add myagentkit@personal
```

Use `$myagentkit-review`, `$myagentkit-delegate`, `/skills`, or a direct request such as
"Ask Claude to review this and fix confirmed findings." These are native Codex skills,
not Claude-style custom slash commands. Review manages a bounded verification, repair,
and fresh re-review loop. Delegation returns a patch for Codex to inspect and integrate,
not a second unrestricted writer. Automatic invocation requires explicit spending
authorization. See [Codex setup and limits](docs/CODEX.md) before installation.

## What is a recommendation, and what is a requirement

Two different claims live in this repository, and conflating them would be the kind of
overclaiming it tells you to avoid.

**The rules are tool-agnostic.** `AGENTS.md`, the workflow, the review protocol, the state
file, `scripts/check.sh`, the git hook and CI make no assumption about which agent you run,
or whether you run one at all.

**The shipped automation is not.** It was written for the pair above:

- Claude Code's project-local hooks and its `diff-reviewer` subagent live in
  `overlays/claude-code/` — an overlay you take deliberately, not part of the core. The
  three `/myagentkit:*` commands are not there; they are a plugin, installed once per
  machine and upgraded in place.
- `scripts/review.sh --reviewer codex|claude` runs either direction; the default is a
  project setting, not a kit opinion. Both pin their model by name and refuse to run
  unpinned. Neither a successful subprocess nor a confident transcript is treated as
  approval.

Using neither costs you the editor-side hooks and live CLI review automation. The rules
remain usable with manual review; the offline acceptance and review self-tests require
Python 3.10+, Git, and a POSIX shell, but no authenticated AI CLI.

Additional CLI adapters remain welcome. Preserve scoped read access, independent sessions,
durable final evidence, fail-closed behavior, negative tests, and a real invocation proving
the CLI contract. Supporting another binary does not mean accepting another CLI's flags.

## How updates work

Files are one of two kinds. **Kit-owned** files carry a header saying so; `sync-kit.sh`
overwrites them wholesale. **Project-owned** files — the constitution, the workflow, the
check script, the reviewer definition — are customised per project and are never
overwritten. After overwriting, `sync-kit.sh` prints the `CHANGELOG.md` entries added since
your recorded version, so you can hand-apply the rest deliberately.

Updates also flow the other way. Every project using the kit asks one question in its
periodic audit: *did we learn anything this cycle that belongs in the kit rather than
here?* If yes, the kit changes first, then the project syncs. That is why
`RESEARCH_LOG.md` exists.

## The kit is supposed to outgrow me

A foundation written once by one person goes stale exactly where that person does not work.
Mine is a Unity and .NET shape; if the kit only ever sees that, its advice about everything
else decays quietly and nobody finds out.

Two separate things follow from that, and it is worth not confusing them.

**The kit keeps learning in your project, always.** The ecosystem research at install, the
periodic audit, the traps a real session walks into and writes down — that is how the
foundation stays current for *you*, and it runs regardless of anything below. It writes to
your own `RESEARCH_LOG.md` and your own docs. Nothing about it points outward.

**Sending any of it upstream is opt-in, and the setup interview asks once.** The question is
whether you want the agent to *offer* — "some of this looks like it belongs in the kit
rather than here, want me to send it?" — or to stay quiet about it and leave the choice to
you. Say no and the clause never enters your constitution, so no future session raises it
again. `/myagentkit:kit-feedback` still works whenever you want it; declining the offer is
not declining the door.

If you leave the offer on, it stays a light touch: once per research pass, once when
something about the foundation itself misbehaved — a gate that failed open, a rule that did
not survive real work, an ambiguous instruction. Not once per finding, and never twice for
the same one.

Whichever way you answer, `/myagentkit:kit-feedback` behaves the same when you run it: it
decides issue or PR, **strips your project out of the text**, shows you the exact body, and
sends nothing until you say yes. Because it publishes to a public repository, three things
it will never do are send anything you have not read, include your paths, names or code, or
act on its own initiative.

Doing it by hand is fine too — [CONTRIBUTING.md](CONTRIBUTING.md) is the same process
written out, including what belongs here and what does not.

Most useful thing to send, if you are looking for one: **a platform I cannot test.** These
scripts run on Linux, native and under WSL. macOS and BSD are untested — the scripts are
POSIX `sh`, but in places they assume GNU `grep` and `sed` behaviour, which is exactly where
they would break first.

## Where this came from

Six years of shipping games, across several engines, with the depth in Unity and .NET. Long
enough to have watched codebases rot for reasons that had nothing to do with the language,
and to know which practices survive contact with a deadline and which ones are read once and
never again.

The last year of that went into a narrower question: how to work with CLI agents without
paying the compounding cost they impose — the second implementation of a system nobody could
find, the rule that erodes because nothing enforces it, the context that dies with the
session. This kit is what came out of it. The year supplied the AI-specific parts; the six
before it supplied the judgement about which of them were worth enforcing.

Nothing here was designed in the abstract: every rule is in the kit because something broke
without it. The founding lessons — including three gates that reported PASS while protecting
nothing — are written up in `RESEARCH_LOG.md` with the failure each one prevents.

MIT licensed.
