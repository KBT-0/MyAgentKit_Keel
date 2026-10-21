---
description: Bring the kit's newest release into this project with sync-kit.sh, through the one-line installer
argument-hint: "[--dry-run] [--merge] [--actions-applied]"
allowed-tools: Read, AskUserQuestion
---
# /myagentkit:sync [--dry-run] [--merge] [--actions-applied]

**Kit version.** This plugin is kit v0.12.1. Before anything else, read the project's
`docs/kit/.kit-version` (such as `0.10` or `0.12.1`). When it is there and names another
version, print one plain line and go on, never stop for it: both versions, which one is newer
(compared part by part as numbers, a missing part counting as 0:
0.12 is 0.12.0, and 0.9 is older than 0.11), and that `/myagentkit:sync` brings the project
to the kit's newest release; when the project is the newer one, update this plugin too. No
file, or the same version: no line. Nothing here uses the network.

Run from the project root, the owner's current checkout. The plugin carries no copy of the kit:
this runs the kit's installer in sync mode, which updates the cached kit in `~/.myagentkit/kit`
to its release tag and runs that kit's `sync-kit.sh` on this folder.

1. Accept only `--dry-run`, `--merge` and `--actions-applied`; refuse anything else and list
   these. Pass `--actions-applied` only when the owner said the ACTION items are applied.
2. Ask first. Show the owner: the installer
   `https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh` downloads the kit
   from `https://github.com/KBT-0/MyAgentKit_Keel.git` at the release tag it names (or at
   `MYAGENTKIT_REF` when set) into the cache `~/.myagentkit/kit`, then syncs it into this project
   (give its full path). Wait for the owner's yes in the chat, in every permission mode, bypass
   and allow rules included. No yes: run nothing.
3. Run, with the Bash tool (Git Bash on Windows):

   ```sh
   curl -fsSL https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh | sh -s -- sync OPTIONS
   ```

   It is not pre-approved on purpose (the `allowed-tools` line lists only what runs without a
   prompt, not every tool this command uses): it downloads and runs code, and the permission
   prompt is the second gate. On a refusal, give the owner that command to run.
4. No `install: kit` line in the output means the download failed (curl printed why; the
   pipe still exits 0): say so and stop. Show the output and the **ACTION** items it wrote to
   `docs/kit/UPGRADE.md`: they are the product, so do not summarise them away. Without `--merge`, exit 2 means **ACTION** items are open and
   the version stays put: list them and apply them only on the owner's go-ahead, then run this
   again with `--actions-applied`. With `--merge`, exit 2 is its normal end: the kit's changes
   are merged into the project-owned files and the version stays put; show each merged file's
   diff (`git diff`), resolve each conflict it lists on the owner's go-ahead, then run this again
   with `--actions-applied` and without `--merge`. Exit 1 means nothing was synced: show the reason and stop.

Raw arguments: `$ARGUMENTS`
