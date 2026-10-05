# Updating a project that already uses the kit

## Two tiers of ownership

**KIT-OWNED** files carry a marker in their header:

```
KIT-OWNED: do not edit locally; change it in the kit and re-sync.
```

They hold no project content, so `sync-kit.sh` overwrites them wholesale. Today that is a
short list: the three git hooks (`pre-commit`, `pre-merge-commit`, `commit-msg`),
`scripts/doctor.sh`, `scripts/agent_cost.py`, the module-rules template, and the two setup
documents.

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
2. Overwrites the kit-owned files, reporting each as new, updated or unchanged. A file at a
   kit-owned path WITHOUT the KIT-OWNED header is the project's own (a hook the project
   wrote before the kit owned that path): it is listed as `conflict:`, and the sync stops
   before it copies anything or records a version. Move yours aside, sync again, then carry
   what yours did into the project by hand (`docs/RETROFIT.md`).
3. **Prints every `CHANGELOG.md` entry added since your version.** This is the real product.
   From v0.9 on, each version's entry ends with one ordered checklist, "Upgrading a project
   from v<previous>": the files to copy whole, the project-owned files to merge, the lines
   to check and the commands to run, each named once and in its final state. Every item
   carries the **ACTION** marker, and the items are listed again at the end, each printed
   whole. Work through them top to bottom; when you skip versions, do the oldest version's
   items first.
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

Overlay files are installed once and then belong to the project: the sync updates one only
if it is kit-owned and the project already has it, and none is kit-owned today, so the
checklist names each overlay file that changed. Re-run `bootstrap.sh --overlay <name>` if
you want a new file from one: it adds what is missing, passes over files identical to the
kit's and lists the ones that differ without touching them.

## What the scripts protect against, and what they do not

The owner runs `sync-kit.sh` and `bootstrap.sh` in the owner's own project. They protect
against their own failures and interruptions (a failed write, a full disk, INT, TERM or HUP
part way, and a retry after any of them) and against honest mistakes in the tree: a file,
folder, symlink or special file where a script means to write is refused by name, never
written through. There is no rollback: files already copied stay copied when a later step
fails, each one whole, and the version is recorded last. By decision they do NOT protect
against another process changing the tree while they run, files placed in the project to
attack them, or SIGKILL or power loss between two steps; whoever can do the first two can
write the same files directly.

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
