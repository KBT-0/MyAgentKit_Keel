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
  especially wanted: only Linux under WSL has ever been tested.
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

**A behavioural change carries its reasoning.** Add the finding to `RESEARCH_LOG.md` with
the failure it prevents, and a line to `CHANGELOG.md` with what changed. A rule that arrives
without its reason is a rule the next reader deletes, and they will be right to.

For a release, match README's bold version to the newest versioned heading in `CHANGELOG.md`.

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
