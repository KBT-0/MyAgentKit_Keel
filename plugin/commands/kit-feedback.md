---
description: Send something you learned back to MyAgentKit_Keel as a GitHub issue or pull request — the kit improves from the projects using it
argument-hint: "[what you learned, or leave empty to use the current conversation]"
allowed-tools: Read, Glob, Grep, Bash(gh auth status), Bash(git status), Bash(git diff), Bash(git diff --stat), AskUserQuestion
---
# /myagentkit:kit-feedback [what you learned]

Upstream is `https://github.com/KBT-0/MyAgentKit_Keel`. A kit that only its author edits goes
stale in exactly the places its author does not work; this command is how a project that
learned something the hard way pays it back.

**Publishing is the point and the risk.** A GitHub issue or PR is PUBLIC and may be cached
or indexed even if deleted later. Nothing leaves this machine without the owner reading the
exact text first and saying yes. There is no "obviously fine" case.

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

## 2. Decide the shape

- **Issue** — a problem, a question, or a suggestion you are not implementing. Cheap, and
  the right default when you are unsure.
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

Print the FULL body you intend to send — title and text, exactly as it will appear — and
ask for explicit approval. Not "shall I proceed": show the artifact. The owner may edit it,
narrow it, or drop it.

If `gh` is not installed or not authenticated (`gh auth status`), say so and offer the body
as text for them to paste by hand. Do not attempt another route.

## 5. Send

The send command is not pre-approved on purpose; the permission prompt is the second gate.
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
directory, fill it, and check that `./scripts/check.sh` and `./scripts/check.sh --self-test`
both pass. A contribution that breaks the gate is the one thing this kit cannot accept.

Report the URL back. If the owner declines, say the finding stays local and note it in
`docs/STATE.md` so the next audit can reconsider it — a declined contribution is a decision,
not a dead end.

Raw arguments: `$ARGUMENTS`
