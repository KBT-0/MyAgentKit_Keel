# Updating a project that already uses the kit

## Two tiers of ownership

**KIT-OWNED** files carry a marker in their header:

```
KIT-OWNED: do not edit locally; change it in the kit and re-sync.
```

They hold no project content, so `sync-kit.sh` overwrites them wholesale. Today that is a
short list: the pre-commit hook, the module-rules template, the handoff skill, and the two
setup documents.

**PROJECT-OWNED** is everything else, and that is most of the kit: the constitution, the
workflow, the review gate, the architecture map, the check script, the boundary checks and
their negative tests. All of them were customised during setup. Overwriting them would
discard that work and re-introduce the placeholders — the gate would go red on a project
that was fine a minute earlier.

This split is deliberately conservative. A tool that silently merged process rules into a
working repository would be worse than no tool: you would stop reading what it did, which is
exactly the habit the review gate exists to prevent.

## What a sync actually does

```sh
/path/to/kit/sync-kit.sh .            # or --dry-run first
```

1. Reads `docs/kit/.kit-version`. Missing or empty is a hard stop — it will not guess.
2. Overwrites the kit-owned files, reporting each as new, updated or unchanged.
3. **Prints every `CHANGELOG.md` entry added since your version.** This is the real product.
   Entries marked **ACTION** need a hand edit in a project-owned file; they are listed again
   at the end as a checklist.
4. Records the new version — but only when there are no ACTION items, or you confirmed
   them. With ACTION items pending, the version stays where it was and the script exits 2,
   so the next sync prints the same entries and checklist again. Apply the items, then:

   ```sh
   /path/to/kit/sync-kit.sh . --actions-applied
   ```

   The recorded version therefore means "everything up to here was applied", not "the
   files were copied". Stamping first once let a project skip two versions of hand edits
   and then read "already current".

Then run `./scripts/check.sh` and `./scripts/check.sh --self-test`. A sync that leaves the
gate red, or leaves a gate that can no longer fail, is not finished.

Overlays are not synced. They are installed once and then belong to the project; re-run
`bootstrap.sh --overlay <name>` if you want a new file from one, and note that it skips
anything you already have.

## Backflow — the other direction

Updates are supposed to flow both ways, and the direction from a project back into the kit
is the one that decays if nothing schedules it.

Every project using the kit adds one question to its periodic audit:

> "Did we learn anything this cycle that belongs in the kit rather than only here?"

If yes: **change the kit FIRST, then sync.** Fixing it locally and meaning to upstream it
later is how a kit and its projects drift apart — the local fix works, so the upstream one
never happens, and the next project inherits the original problem.

Record the answer either way, including "nothing this cycle", in that audit file. An
unrecorded "nothing" is indistinguishable from nobody having asked.

Things that belong upstream: a rule you had to invent because the kit lacked it, a
placeholder whose instructions were ambiguous, a gate that turned out to be fail-open, a
question the setup interview should have asked and did not. Things that do not: anything
that only makes sense given your domain.

Every accepted backflow gets an entry in `RESEARCH_LOG.md` with the failure it prevents, and
a line in `CHANGELOG.md`. A rule that arrives without its reason is a rule the next reader
deletes.
