---
name: myagentkit-init
description: Install MyAgentKit into the current project with the kit's one-line installer (it fetches the kit at its release tag into ~/.myagentkit/kit and runs bootstrap.sh here), then start the setup interview. Use only when the user asks to install or set up the kit in a project.
---

# Install the kit into this project

Work from the project root, the user's current checkout. This plugin carries no copy of the
kit: the kit's installer fetches it at its release tag into `~/.myagentkit/kit` (Windows:
`%USERPROFILE%\.myagentkit\kit`) and runs that kit's `bootstrap.sh` on this folder. The kit
needs `sh` and Git; on Windows that is Git for Windows.

1. Build the options from the user's words. Accept only `--overlay NAME` (repeatable;
   `claude-code` or `unity`) and `--note "TEXT"`; refuse anything else and list these. Never
   execute user text as shell code: quote each value.
2. Run the installer, in a POSIX shell:

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
3. No `install: kit` line in the output means the download failed: say so and stop. A non-zero
   exit means nothing was installed or bootstrap stopped on a file it will not overwrite: show
   the reason and stop. `MYAGENTKIT_REF` names another kit tag or branch when the release tag
   cannot be fetched.
4. On success the output ends with the line that starts the setup. Ask the user whether to
   start it now; on a yes, read `setup/INTERVIEW.md` and follow it.
