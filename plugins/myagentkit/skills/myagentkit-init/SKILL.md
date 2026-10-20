---
name: myagentkit-init
description: Install MyAgentKit into the current project with the kit's one-line installer (it fetches the kit at its release tag into ~/.myagentkit/kit and runs bootstrap.sh here), then start the setup interview. Use only when the user asks to install or set up the kit in a project.
---

# Install the kit into this project

**Kit version.** This plugin is kit v0.11. Before anything else, read the project's
`docs/kit/.kit-version` (MAJOR.MINOR, such as `0.10`). When it is there and names another
version, print one plain line and go on, never stop for it: both versions, which one is newer
(compared as numbers: 0.9 is older than 0.11), and that the `myagentkit-sync` skill brings the project
to the kit's newest release; when the project is the newer one, update this plugin too. No
file, or the same version: no line. Nothing here uses the network.

Work from the project root, the user's current checkout. This plugin carries no copy of the
kit: the kit's installer fetches it at its release tag into `~/.myagentkit/kit` (Windows:
`%USERPROFILE%\.myagentkit\kit`) and runs that kit's `bootstrap.sh` on this folder. The kit
needs `sh` and Git; on Windows that is Git for Windows.

1. Build the options from the user's words. Accept only `--overlay NAME` (repeatable;
   `claude-code` or `unity`) and `--note "TEXT"`; refuse anything else and list these. Never
   execute user text as shell code: quote each value.
2. Ask first. Show the user: the installer
   `https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh` downloads the kit
   from `https://github.com/KBT-0/MyAgentKit_Keel.git` at the release tag it names (or at
   `MYAGENTKIT_REF` when set) into the cache `~/.myagentkit/kit`, then installs it into this project
   (give its full path). Wait for the user's yes in the chat, in every permission mode, bypass
   and allow rules included. No yes: run nothing.
3. Run the installer, in a POSIX shell:

   ```sh
   curl -fsSL https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.sh | sh -s -- OPTIONS
   ```

   in PowerShell:

   ```powershell
   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/KBT-0/MyAgentKit_Keel/master/install.ps1))) OPTIONS; exit $LASTEXITCODE
   ```

   It needs the network and writes outside the project (the cache), so the sandbox may refuse
   it or ask for approval. When it cannot run here, give the user the command to run and stop;
   do not try to work around the sandbox.
4. No `install: kit` line in the output means the download failed: say so and stop. A non-zero
   exit means nothing was installed or bootstrap stopped on a file it will not overwrite: show
   the reason and stop. `MYAGENTKIT_REF` names another kit tag or branch when the release tag
   cannot be fetched.
5. On success the output ends with the line that starts the setup. Ask the user whether to
   start it now; on a yes, read `setup/INTERVIEW.md` and follow it.
