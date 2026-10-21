---
name: myagentkit-sync
description: Bring the newest MyAgentKit release into the current project with the kit's installer in sync mode (it updates ~/.myagentkit/kit to the release tag and runs sync-kit.sh here). Use only when the user asks to sync or update the kit in a project.
---

# Sync the kit into this project

**Kit version.** This plugin is kit v0.12.0. Before anything else, read the project's
`docs/kit/.kit-version` (such as `0.10` or `0.12.1`). When it is there and names another
version, print one plain line and go on, never stop for it: both versions, which one is newer
(compared part by part as numbers, a missing part counting as 0:
0.12 is 0.12.0, and 0.9 is older than 0.11), and that the `myagentkit-sync` skill brings the project
to the kit's newest release; when the project is the newer one, update this plugin too. No
file, or the same version: no line. Nothing here uses the network.

Work from the project root, the user's current checkout. This plugin carries no copy of the
kit: the kit's installer, in sync mode, updates the cached kit in `~/.myagentkit/kit`
(Windows: `%USERPROFILE%\.myagentkit\kit`) to its release tag and runs that kit's
`sync-kit.sh` on this folder.

1. Accept only `--dry-run`, `--merge` and `--actions-applied`; refuse anything else and list
   these. Pass `--actions-applied` only when the user said the ACTION items are applied.
2. Ask first. Show the user: the installer
   `https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh` downloads the kit
   from `https://github.com/KBT-0/MyAgentKit_Keel.git` at the release tag it names (or at
   `MYAGENTKIT_REF` when set) into the cache `~/.myagentkit/kit`, then syncs it into this project
   (give its full path). Wait for the user's yes in the chat, in every permission mode, bypass
   and allow rules included. No yes: run nothing.
3. Run the installer, in a POSIX shell:

   ```sh
   curl -fsSL https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh | sh -s -- sync OPTIONS
   ```

   in PowerShell:

   ```powershell
   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.ps1))) sync OPTIONS; exit $LASTEXITCODE
   ```

   It needs the network and writes outside the project (the cache), so the sandbox may refuse
   it or ask for approval. When it cannot run here, give the user the command to run and stop;
   do not try to work around the sandbox.
4. No `install: kit` line in the output means the download failed: say so and stop. Show the
   output and the **ACTION** items it wrote to `docs/kit/UPGRADE.md`: they are the product, so
   do not summarise them away. Without `--merge`, exit 2 means **ACTION** items are open and the
   version stays put: list them and apply them only on the user's go-ahead, then run this again
   with `--actions-applied`. With `--merge`, exit 2 is its normal end: the kit's changes are
   merged into the project-owned files and the version stays put; show each merged file's diff
   (`git diff`), resolve each conflict it lists on the user's go-ahead, then run this again with
   `--actions-applied` and without `--merge`. Exit 1 means nothing was synced: show the reason and stop.
