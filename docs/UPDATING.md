# Updating a project that already uses the kit

## Two tiers of ownership

**KIT-OWNED** files carry a marker in their header:

```
KIT-OWNED: do not edit locally; change it in the kit and re-sync.
```

They hold no project content, so `sync-kit.sh` overwrites them wholesale. Today that is a
short list: the four git hooks (`pre-commit`, `pre-merge-commit`, `commit-msg`,
`post-merge`), `scripts/doctor.sh`, `scripts/fix_crlf.sh`, `scripts/agent_cost.py`,
`scripts/usage_summary.py`, `scripts/context_buckets.py`, `scripts/working_mode.py`,
`BEHAVIOUR.md`, the module-rules template, and the two setup documents
(`grep -rl '^# KIT-OWNED:\|^<!-- KIT-OWNED:' core setup` in the kit lists them).
A project's own machine checks, once in its own `scripts/doctor.sh`, move to
`scripts/doctor.project.sh`, which the kit's `doctor.sh` runs last.

The review adapters (`scripts/claude_bridge.py`, `scripts/codex_bridge.py`,
`scripts/review_dispatch.py` and the scripts they import) carry no marker yet, but each
upgrade's checklist replaces them whole too. A line a project adds to them, such as its own
check of a reviewer's final report, is lost at the next upgrade. The adapters have no
project hook for such a check today: send it upstream (`/myagentkit:kit-feedback`) so it
lands in the kit, and keep it as a marked patch with a `docs/STATE.md` line until then.

An upgrade that adds a Claude Code agent definition (`.claude/agents/*.md`) next to one the
project already has for the same job, such as its own reviewer beside `diff-reviewer.md`,
keeps one of the two (the overlay's README says how). bootstrap.sh and sync-kit.sh list such
a reviewer (front matter `name:` holding the word "review") as a conflict line; neither file is touched.

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

1. Reads `docs/kit/.kit-version`. Missing or empty is a hard stop — it will not guess. So is
   a version newer than the kit's (a second kit clone, not pulled: its older hooks would roll
   the project back) and a version the kit's changelog does not hold; the versions are
   compared by number, before anything is copied. The same version is synced all the same: a
   release gains kit-owned fixes and ACTION items while its number stays.
2. Overwrites the kit-owned files, reporting each as new, updated or unchanged. Each hook
   and script it writes also gets mode 100755 in the git index, since `core.fileMode=false`
   (native Windows) never carries the disk's bit there: a tracked one keeps its staged bytes,
   a new one is staged (from a subfolder install the command is printed instead). A file at a
   kit-owned path WITHOUT the KIT-OWNED header is the project's own (a hook the project
   wrote before the kit owned that path): it is listed as `conflict:`, and the sync stops
   before it copies anything or records a version. Move yours aside, sync again, then carry
   what yours did into the project by hand (`docs/RETROFIT.md`). A hook of yours under
   `.githooks` (a Git LFS `post-merge`) only needs a new name: as `.githooks/<same name>.project`
   (executable, with a `#!` line) it keeps running, since the kit's hook runs it first with
   git's arguments. A kit-owned file with an edit git does not hold (unstaged, or an untracked
   file) is a `conflict:` too, since the copy keeps no backup: commit the edit or restore the
   file, then sync again. Template and package tools
   leave that call to a person too (Copier marks conflicts for review before the commit;
   dpkg asks about a changed configuration file); the sync is stricter and writes nothing,
   because a half-merged hook can be a gate that silently does not run.
3. **Lists every ACTION item added since your version.** This is the real product. The
   changelog marks manual migration steps with **ACTION**: files to copy, project-owned rules
   to merge, lines to check and commands to run. Each marker is one item, the oldest version's
   first. `sync-kit.sh . --dry-run` prints them without writing anything; a normal sync writes
   them to `docs/kit/UPGRADE.md`, one box each, and prints only where they are and how many
   are open. Each item's whole entry is in the kit's `CHANGELOG.md`. The sync no longer prints
   the entries themselves: from v0.8 they came to 209 KB, seven times what an agent's shell
   tool shows, so the checklist at the end was cut off. With the kit commit of the last stamp
   (`docs/kit/.kit-commit`), an item added under a version after the project took it is listed
   too. An ACTION line saying only "none" is no item.
4. Records the new version — but only when there are no ACTION items, or every box in
   `docs/kit/UPGRADE.md` is ticked. Tick a box (`- [x]`) as you apply its item: a session
   that stops half way, compacts or hands off leaves the next one the boxes still open. A
   rerun keeps the ticks (an item the kit added or reworded comes back open). Then:

   ```sh
   /path/to/kit/sync-kit.sh . --actions-applied
   ```

   It records the version and deletes the checklist; while a box is open it exits 2. The
   report is printed when the run ends, so a run piped to `head` still records the version.
   **Edits to `.claude/settings.json` are the owner's.** Claude Code's auto mode refuses an
   agent's write to its own settings as self-modification, so an item that registers a hook
   or changes a permission is prepared by the agent (the merged file beside it, or the entry
   to add) and applied and committed by the owner. Commit it: a worktree worker runs the
   committed `settings.json`, not the lead's working copy.

   The recorded version therefore means "everything up to here was applied", not "the
   files were copied". Stamping first once let a project skip two versions of hand edits
   and then read "already current". Migration tools work the same way: Rails records a
   migration's version only after it ran and stops while one is pending, Copier runs a
   migration only for the versions it crosses, and `cruft check` exits non-zero on an
   out-of-date project. The kit keeps a checklist a person reads instead of automated
   migrations ("Two tiers of ownership" above: a silent merge of process rules is worse
   than none).

**Merging the project-owned files.** `sync-kit.sh . --merge` also merges the kit's changes
into the project-owned files with `git merge-file`: the project's copy, the kit's copy at the
base commit, the kit's copy now. A file the kit did not change since the base is not opened.
A clean merge is written and listed as `merged:`. A conflicted one is written with its markers
and listed with the line ranges of its conflicts, so a reader opens only those lines, never the
whole file. Files the kit added since the base are listed as `kit-new:` for the changelog to
decide. The base is the kit commit recorded in `docs/kit/.kit-commit`, which every sync that
records a version writes. A project synced before v0.12 has no record yet, so it passes
`--base <commit>` once: the release commit that the changelog's upgrade section names. Use
the commit the project really came from, because a later commit makes the kit's own changes in
between read as the project's, and they are dropped without a conflict. So a base passed with
`--base` is checked first against the project's kit-owned files as the project's last commit
that changed `docs/kit/.kit-version` holds them, which are that commit's copies (line endings
aside), even after a plain sync's copies were committed. If any of them differs, the run stops before it writes anything
and names those files. A rerun merges against the same base again, so a kit change you rejected comes back: reject a
kit hunk only after the last `--merge` run. Both kit sides are read from the kit's commits, never
its working tree, and a CRLF project file is merged as LF and written back as CRLF. Files the
kit removed or renamed since the base are listed as `kit-removed:`. A `--merge` run never
records the version, and no sync records it while a project-owned file still holds conflict
markers. Read each merged
file's `git diff`, resolve the listed conflicts, then rerun with `--actions-applied`. One
upgrade that instead merged five docs whole, one agent per doc, read 8.3M cache tokens (#184).
On the kit's own history, v0.8 to v0.12, the conflict regions of the same docs and `check.sh`
come to about 14% of one read of the whole files.

Then run `./scripts/check.sh`. The project's own fixture tests for its boundary checks run
inside it, in the build command (WORKFLOW, "Writing a gate"). A sync that leaves the gate red,
or leaves a check without its fixture test, is not finished.

Overlay files are installed once and then belong to the project: the sync updates one only
if it is kit-owned and the project already has it, and installs a kit-owned one the project
lacks only when the project has another kit-owned file of that overlay (a new worker script
such as `list_workers.sh`, which the synced watch and close scripts call). The kit-owned ones are the Claude Code
overlay's worker scripts (`spawn_worker.sh`, `spawn_codex.sh`, `codex_worker.py`, `show_workers.sh`, `watch_workers.sh`,
`waiting_patterns.txt`, `close_worker.sh`, `list_workers.sh`) and its clean-up scripts (`clean_worktrees.sh`,
`clean_worktrees.py`); the checklist names each other overlay file that changed. Re-run `bootstrap.sh --overlay <name>` if
you want a new file from one: it adds what is missing, passes over files identical to the
kit's and lists the ones that differ without touching them; only `--force` overwrites (as
Copier's `skip_if_exists` and dpkg's kept configuration file: a tool never overwrites the
user's change by default). On an installed project the rerun keeps `docs/kit/.kit-version`
and `docs/kit/.kit-commit` as they are, since the version is the sync's to record, and a gate
file the setup changed is left alone, not a stop. The presence of an overlay file is the record that the project
took that overlay; Copier and cruft keep that record in a file of answers instead
(`.copier-answers.yml`, `.cruft.json`), which the kit would only need if a deleted overlay
file ever had to be told apart from a declined one.

## What the scripts protect against, and what they do not

The owner runs `sync-kit.sh` and `bootstrap.sh` in the owner's own project. They protect
against their own failures and interruptions (a failed write, a full disk, INT, TERM or HUP
part way, and a retry after any of them) and against honest mistakes in the tree: a file,
folder, symlink or special file where a script means to write is refused by name, never
written through (CWE-59, link following: installers are among its real cases), and so is a
file name holding a line break, which a line-reading loop cannot carry (Wheeler, "Filenames
and Pathnames in Shell": forbidding it is the simple safe choice). There is no rollback: files already copied stay copied when a later step
fails, each one whole, and the version is recorded last. By decision they do NOT protect
against another process changing the tree while they run, files placed in the project to
attack them, or SIGKILL or power loss between two steps; whoever can do the first two can
write the same files directly.

### The gate, `review.sh` and the upgrade checklists

The gate (`scripts/check.sh` and its lock), `scripts/review.sh` and the
checklists in `CHANGELOG.md` share one threat model. A project has one owner, who works with
agents. The threat model was written in v0.10 after six review rounds in which each fix
exposed an "adjacent path"; a finding outside it is answered with this section, not a fix
(`docs/REVIEW_GATE.md`, "Rounds").

- **In scope: mistakes and accidents of the owner and the agents.** A killed process or a
  Ctrl-C at any point. A file left behind by a killed run. A CRLF checkout. A symlink the
  owner made where a script reads or writes. A shallow clone. A run from the wrong shell or
  Python (WSL against native Windows, a stray module on `PYTHONPATH`). A stale environment
  copied from a killed gate. Each one either works or stops with a message that names it. An
  interrupted or killed gate never reports a pass, and it leaves the lock to the next run. A
  Ctrl-C that comes after the gate has ended interrupted nothing, so the gate's own status
  stands, as it does on POSIX once the gate has exited. A review whose checkout changed
  while it ran is discarded (`stale_checkout`).
- **Out of scope: an adversary acting while a gate or a review runs.** This is a process that
  changes the tree, the index or the Git configuration between two of a script's reads. The
  reason: the same process could edit the gate or the review script itself. Example (review
  round r6 of v0.10, finding 1): an attribute that removes a path's filter while `review.sh`
  collects its filtered paths, restored before the diff, could hide an LFS path's raw change
  from the reviewer. It is recorded as out of scope, not fixed. An ordinary edit made while a
  review runs is still caught, by the checkout fingerprint.
- **Out of scope: hostile files planted in the project by anyone other than the owner.** The
  reason: whoever can write the tree can also edit the gate, the hooks and the review script.
  Defending those scripts against the tree they live in defends nothing.

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
