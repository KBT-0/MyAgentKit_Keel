---
description: Install the kit into this project with the one-line installer, then start the setup interview
argument-hint: "[--overlay claude-code|unity]... [--note \"agenda\"]"
allowed-tools: Read, AskUserQuestion
---
# /myagentkit:init [--overlay NAME]... [--note "agenda"]

**Kit version.** This plugin is kit v0.11.0. Before anything else, read the project's
`docs/kit/.kit-version` (such as `0.10` or `0.12.1`). When it is there and names another
version, print one plain line and go on, never stop for it: both versions, which one is newer
(compared part by part as numbers, a missing part counting as 0:
0.12 is 0.12.0, and 0.9 is older than 0.11), and that `/myagentkit:sync` brings the project
to the kit's newest release; when the project is the newer one, update this plugin too. No
file, or the same version: no line. Nothing here uses the network.

Run from the project root, the owner's current checkout. The plugin carries no copy of the kit:
this runs the kit's installer (`install.sh` in the kit repository), which fetches the kit at its
release tag into `~/.myagentkit/kit` and runs that kit's `bootstrap.sh` on this folder.

1. Build the options from the raw arguments. Accept only `--overlay NAME` (repeatable; the
   kit has `claude-code` and `unity`) and `--note "TEXT"`; refuse anything else and list these.
   Never execute raw arguments as shell code: put each value in single quotes, a `'` inside
   written as `'\''`.
2. Ask first. Show the owner: the installer
   `https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh` downloads the kit
   from `https://github.com/KBT-0/MyAgentKit_Keel.git` at the release tag it names (or at
   `MYAGENTKIT_REF` when set) into the cache `~/.myagentkit/kit`, then installs it into this project
   (give its full path). Wait for the owner's yes in the chat, in every permission mode, bypass
   and allow rules included. No yes: run nothing.
3. Run, with the Bash tool (Git Bash on Windows):

   ```sh
   curl -fsSL https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh | sh -s -- OPTIONS
   ```

   It is not pre-approved on purpose: it downloads and runs code, and the permission prompt is
   the second gate. On a refusal, give the owner that command to run.
4. No `install: kit` line in the output means the download failed (curl printed why; the
   pipe still exits 0): say so and stop. Show the output. A non-zero exit means nothing was
   installed or bootstrap stopped on a file it will not overwrite: show the reason and stop.
   `MYAGENTKIT_REF` names another kit tag or branch when the release tag cannot be fetched.
5. On success the output ends with the line that starts the setup. Ask the owner whether to
   start it now; on a yes, read `setup/INTERVIEW.md` and follow it.

Raw arguments: `$ARGUMENTS`
