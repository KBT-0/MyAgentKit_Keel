---
description: Install the kit into this project with the one-line installer, then start the setup interview
argument-hint: "[--overlay claude-code|unity]... [--note \"agenda\"]"
allowed-tools: Read, AskUserQuestion
---
# /myagentkit:init [--overlay NAME]... [--note "agenda"]

Run from the project root, the owner's current checkout. The plugin carries no copy of the kit:
this runs the kit's installer (`install.sh` in the kit repository), which fetches the kit at its
release tag into `~/.myagentkit/kit` and runs that kit's `bootstrap.sh` on this folder.

1. Build the options from the raw arguments. Accept only `--overlay NAME` (repeatable; the
   kit has `claude-code` and `unity`) and `--note "TEXT"`; refuse anything else and list these.
   Never execute raw arguments as shell code: put each value in single quotes, a `'` inside
   written as `'\''`.
2. Run, with the Bash tool (Git Bash on Windows):

   ```sh
   curl -fsSL https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh | sh -s -- OPTIONS
   ```

   It is not pre-approved on purpose: it downloads and runs code, and the permission prompt is
   the owner's gate. On a refusal, give the owner that command to run.
3. No `install: kit` line in the output means the download failed (curl printed why; the
   pipe still exits 0): say so and stop. Show the output. A non-zero exit means nothing was
   installed or bootstrap stopped on a file it will not overwrite: show the reason and stop.
   `MYAGENTKIT_REF` names another kit tag or branch when the release tag cannot be fetched.
4. On success the output ends with the line that starts the setup. Ask the owner whether to
   start it now; on a yes, read `setup/INTERVIEW.md` and follow it.

Raw arguments: `$ARGUMENTS`
