# Contributing

This kit is meant to improve from the projects using it, not only from its author. A
foundation written once by one person goes stale precisely where that person does not work,
and the projects that hit its edges are the only ones who can see where those edges are.

So contributions are not a courtesy here. They are the maintenance model.

## The easy path

If you installed the plugin, your agent can do all of this for you:

```
/myagentkit:kit-feedback
```

It works out whether the finding belongs upstream, picks issue or PR, **scrubs your project
out of the text**, shows you the exact body, and sends nothing until you say yes. Everything
below is the same process by hand.

## What belongs here, and what does not

**Send it** when the finding is about the KIT:

- A gate that turned out to be fail-open, or that could not be made to go red.
- A rule that did not survive contact with real work.
- A placeholder whose instructions were ambiguous, or a setup question the interview should
  have asked and did not.
- A document that contradicts another document, or itself.
- A script that broke on your platform — macOS, BSD, Windows, a different shell. This one is
  especially wanted: a passing development-host run can still hide a platform regression.
- An ecosystem claim that has gone stale. Tool names, flags and install commands rot fast.

**Keep it local** when it only makes sense given your domain. A rule about your game's
economy, your compliance regime or your deployment target belongs in your project's own
documents. A rejected contribution costs the maintainer more than it costs you, so filtering
is part of contributing.

Not sure? Open an issue. That is what they are cheap for.

## Before you open a pull request

**A change to a gate must add its negative test.** This is the kit's founding rule and there
is no exception to it: a gate that has only been seen passing is an untested branch that
runs on every commit. If your PR touches `check.sh`, a boundary check, `review.sh` or CI, it
adds the case to `--self-test` that constructs the failure and asserts the gate rejects it —
and you should have watched it go red before and green after.

**Every change cites its source.** The kit gathers what people, AI vendors and the projects
using it have learned about building software with AI, and stays current with it; nothing
in it is made up on the spot. A rule, a workflow step, a default or a decision you add,
change or delete names its source, in the commit message and in its `RESEARCH_LOG.md` entry:

- a numbered finding of a report in [`docs/research/`](docs/research/README.md), by file and
  finding;
- an official vendor document (Anthropic, OpenAI, the tool's own docs), by URL and date;
- a lesson a project paid for, by its `RESEARCH_LOG.md` entry or issue.

When no source covers the point, research comes first: a new report in `docs/research/`
with graded sources, and a row in its README. When the research settles nothing, the
maintainer decides with the evidence on the table, and the entry says it was a judgement.
A typo or a broken link needs no source.

The same holds before the change: a proposal to the maintainer names the source of each
recommended option, or says it has none and that research comes first. Two places that
contradict each other are settled by research, not by picking a side: the side picked is a
rule. A document that describes the code wrongly is no typo either when the code's own
value has no source (`the doc should match the code` is not one).

Add the finding to `RESEARCH_LOG.md` with the failure it prevents, and a line to
`CHANGELOG.md` with what changed. A rule that arrives without its reason is a rule the next
reader deletes, and they will be right to.

An older `CHANGELOG.md` entry that a later release made wrong gets a one-line pointer to the
entry that replaced it, and the old text stays: a release's record is history, and a reader
of the old entry needs to find what changed it (an architecture decision record is linked to
the one that supersedes it, never edited: martinfowler.com/bliki/ArchitectureDecisionRecord.html;
KARARLAR B11 inv3/(l)). An entry made wrong within the same, unreleased version is deleted
instead (owner decision, v0.11).

For a release, match README's bold version and the `version` in
`plugin/.claude-plugin/plugin.json` to the newest versioned heading in `CHANGELOG.md`: v0.11 is
`0.11.0`, and a patch release raises the third number. The kit check compares all three. The
plugin is installed from this repository's marketplace, and an installed plugin is not updated
until its version string changes (code.claude.com/docs/en/plugins-reference, `version`;
code.claude.com/docs/en/plugins/loading, "Versions and updates").

**Run the kit's own acceptance:**

```sh
tmp=$(mktemp -d) && ./bootstrap.sh "$tmp" && cd "$tmp" && git init -q && git add -A
./scripts/check.sh                # expect FAIL: markers remain, no build command
# fill the placeholders and write the two boundary files, then:
./scripts/check.sh                # expect PASS
./scripts/check.sh --self-test    # expect every case observed going red
```

A contribution that leaves the gate red, or leaves a gate that can no longer fail, is the
one thing this kit cannot take.

## Privacy — read this before pasting anything

An issue or a PR is PUBLIC, and may be cached or indexed even if you delete it later.
Whatever you send is about the kit, so nothing about your project needs to come along.
Strip:

- Absolute paths, home directories, machine and user names
- Project, company, product and internal codenames; colleague names
- Code from your codebase — write a minimal synthetic reproduction instead
- Private repository URLs, ticket links, dashboards, hostnames, and anything resembling a
  token or key

Then read it back once as a stranger and ask what it tells you about your work. If the
answer is anything, scrub again.

## Style

The kit's documents are written in full, explicit sentences, in English, and they state the
failure a rule prevents rather than only the rule. Match that. If you are adding a rule, the
sentence that matters most is the one describing what went wrong without it.

Commit messages describe what changed and why in plain language. No AI attribution trailers.
