---
description: Send something you learned back to MyAgentKit_Keel as a GitHub issue or pull request — the kit improves from the projects using it
argument-hint: "[what you learned, or leave empty to use the current conversation]"
allowed-tools: Read, Glob, Grep, Bash(gh auth status), Bash(git status), Bash(git diff), Bash(git diff --stat), AskUserQuestion
---
# /myagentkit:kit-feedback [what you learned]

**Kit version.** This plugin is kit v0.11.0. Before anything else, read the project's
`docs/kit/.kit-version` (such as `0.10` or `0.12.1`). When it is there and names another
version, print one plain line and go on, never stop for it: both versions, which one is newer
(compared part by part as numbers, a missing part counting as 0:
0.12 is 0.12.0, and 0.9 is older than 0.11), and that `/myagentkit:sync` brings the project
to the kit's newest release; when the project is the newer one, update this plugin too. No
file, or the same version: no line. Nothing here uses the network.

Upstream is `https://github.com/KBT-0/MyAgentKit_Keel`. A kit that only its author edits goes
stale in exactly the places its author does not work; this command is how a project that
learned something the hard way pays it back.

**Publishing is the point and the risk.** A GitHub issue or PR is PUBLIC and may be cached
or indexed even if deleted later. Nothing leaves this machine without the owner reading the
exact text first and saying yes: in the chat each time, or, where the project recorded a
standing approval (§4), in advance, with the full text printed before it is sent. There is no "obviously fine" case.

## 1. Work out what the finding actually is

From `$ARGUMENTS`, or from what just happened in this conversation. State it in one sentence
before going further, and get it confirmed — if you have misread the complaint, everything
below is wasted.

Then decide whether it belongs upstream at all. It does when it is about **the kit**: a rule
that was missing, a gate that was fail-open, a placeholder whose instructions were
ambiguous, a setup question the interview should have asked, a document that contradicted
itself, a script that broke on this platform. It does NOT when it only makes sense given
this project's domain. Say so plainly and stop rather than filing noise upstream — a rejected
contribution costs the maintainer more than it costs you (generated contributions now flood
maintainers: ghostty-org/ghostty CONTRIBUTING.md ties pull requests to an accepted issue;
"Defending Open Source from AI Slop", EuroPython 2026).

Then search the kit's issues, open and closed, before drafting anything:

```sh
gh issue list --repo KBT-0/MyAgentKit_Keel --state all --limit 20 --search "<keywords>"
```

The keywords are kit terms only (a kit file, script, rule or section name), never a name
from this project: the search is a request to GitHub. It is not pre-approved on purpose, so
the permission prompt shows the owner the words before they leave the machine; the search
stays one approval away. Run two or three searches with
different terms. When an issue matches, propose a comment on it, with the new evidence,
instead of a new issue; an open duplicate splits the evidence for one defect in two (the
tracker already held #88 and #141 for one defect).

## 1b. Batch, do not trickle

One issue per AREA (one script, one doc, one gate) per session, never one per finding: a
sweep of one-finding issues costs the maintainer a triage step each and hides that a whole
area is weak.

- Collect findings during the session and file them at its end. A finding the owner hands
  this command mid-session is filed now, not put off: the area's other collected findings go
  into the same issue, and a later one in that area becomes a comment on it. Each finding is ONE
  `- [ ]` line: the kit file, the symptom, how to repeat it. A line without a repro is cut;
  each line closes on its own, no prose spanning lines.
- At most about 10 lines and 6000 characters per issue; more in one area, split by sub-area.
  Title: `<area>: N findings (<short theme>)`.
- One dedupe search round (§1) per area before drafting; a line that matches an existing
  issue becomes a comment on it instead.
- A separate issue only for a security problem, a blocker that stops the project today, or
  a finding for another area or owner.

## 2. Decide the shape

- **Issue** — a problem, a question, or a suggestion you are not implementing: one batch
  issue per area (§1b). Cheap, and the right default when you are unsure.
- **Pull request** — you have an actual fix and the issue for it has been opened first (an
  issue the maintainer has not yet looked at is not a green light for a large PR; Ghostty's
  CONTRIBUTING.md). A small fix may go straight to a PR. A PR requires that the change also carry its
  reasoning: the kit's own rule is that a rule arriving without the failure it prevents is a
  rule the next reader deletes. So a PR touching behaviour also updates `RESEARCH_LOG.md`
  with the finding, and `CHANGELOG.md` with what changed.
  **A PR that changes a gate must add its negative test.** No exceptions — that is the
  kit's founding rule and a PR that skips it will be rejected.

Ask the owner which one, with a recommendation.

## 3. SCRUB — do this before showing anything

The finding is about the kit. Everything specific to this project is both irrelevant
upstream and the owner's private business.

Run a mechanical pass first: replace the absolute paths, the user and machine name, e-mail
addresses and anything that looks like a token with placeholders; then do the read-through
for what a pattern cannot see (project names, business terms, code). A pattern finds only the
kinds of data it knows; a reader misses the routine leaks a pattern would catch (OWASP LLM02,
CWE-532). Remove:

- Absolute paths, home directories, machine and user names.
- The project's name, company name, product names, internal codenames, colleague names.
- Code from this codebase. If an example is genuinely needed, write a MINIMAL synthetic one
  that reproduces the same shape — `src/domain`, `myapp.web`, `foo()`.
- URLs to private repositories, tickets, dashboards, and anything resembling a credential,
  token, key or internal hostname.

Keep: the kit file involved, what you expected, what happened, and — most valuable — how to
reproduce it from a fresh `bootstrap.sh`.

Then re-read the scrubbed text once as if you were a stranger, and ask what it tells you
about the owner's work. If the answer is anything at all, scrub again.

## 4. Show it, then ask

Print the FULL body you intend to send — title and text, exactly as it will appear; once
per batch, never per finding. Then read the `kit_feedback:` line of `AGENTS.md` (the owner's
answer at setup, INTERVIEW Phase 0.5). No line, any other value, or two `kit_feedback:` lines
that disagree mean `ask-each-time`:

- `ask-each-time`: ask for explicit approval. Not "shall I proceed": show the artifact. The
  owner may edit it, narrow it, or drop it.
- `standing-approval`: the owner approved sending in advance; go on to §5 with the printed
  body. The send command's permission prompt shows only the body file's path, and does not
  ask at all under `bypassPermissions` or an allow rule for `gh`, so the printed text is
  what the owner approves.

If `gh` is not installed or not authenticated (`gh auth status`), say so and offer the body
as text for them to paste by hand. Do not attempt another route.

## 5. Send

The send command is not pre-approved on purpose; the permission prompt is the second gate
under `ask-each-time`. Under `standing-approval` it may not ask at all (§4), so the printed
body is the owner's one gate there.
Only exact read-only command forms are in this command's `allowed-tools`; other arguments
require a prompt. A pre-approved tool runs
without a prompt (code.claude.com/docs/en/skills, `allowed-tools`), and a yes in the chat is
no permission boundary.

**Issue:**

```sh
gh issue create --repo KBT-0/MyAgentKit_Keel --title "<title>" --body-file <file>
```

**Pull request** — never push to upstream directly; fork:

```sh
gh repo fork KBT-0/MyAgentKit_Keel --clone --remote=false   # once
# in the fork: branch, make the change, run the kit's own checks, commit
gh pr create --repo KBT-0/MyAgentKit_Keel --title "<title>" --body-file <file>
```

Before opening a PR, run the kit's own acceptance from the fork — bootstrap into a temp
directory, fill it, and check that `./scripts/check.sh` passes in it and in the kit
(`sh scripts/check.sh`). A contribution that breaks the gate is the one thing this kit cannot accept.

Report the URL back. If the owner declines, say the finding stays local and note it in
`docs/STATE.md` so the next audit can reconsider it — a declined contribution is a decision,
not a dead end.

Raw arguments: `$ARGUMENTS`
