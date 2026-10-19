---
description: Bring the kit's newest release into this project with sync-kit.sh, through the one-line installer
argument-hint: "[--dry-run] [--merge] [--actions-applied]"
allowed-tools: Read, AskUserQuestion
---
# /myagentkit:sync [--dry-run] [--merge] [--actions-applied]

Run from the project root, the owner's current checkout. The plugin carries no copy of the kit:
this runs the kit's installer in sync mode, which updates the cached kit in `~/.myagentkit/kit`
to its release tag and runs that kit's `sync-kit.sh` on this folder.

1. Accept only `--dry-run`, `--merge` and `--actions-applied`; refuse anything else and list
   these. Pass `--actions-applied` only when the owner said the ACTION items are applied.
2. Run, with the Bash tool (Git Bash on Windows):

   ```sh
   curl -fsSL https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh | sh -s -- sync OPTIONS
   ```

   It is not pre-approved on purpose: it downloads and runs code, and the permission prompt is
   the owner's gate. On a refusal, give the owner that command to run.
3. No `install: kit` line in the output means the download failed (curl printed why; the
   pipe still exits 0): say so and stop. Show the output: the changelog entries since the
   project's version are the product, so do not summarise them away. Without `--merge`, exit 2 means **ACTION** items are open and
   the version stays put: list them and apply them only on the owner's go-ahead, then run this
   again with `--actions-applied`. With `--merge`, exit 2 is its normal end: the kit's changes
   are merged into the project-owned files and the version stays put; show each merged file's
   diff (`git diff`), resolve each conflict it lists on the owner's go-ahead, then run this again
   with `--actions-applied` and without `--merge`. Exit 1 means nothing was synced: show the reason and stop.

Raw arguments: `$ARGUMENTS`
