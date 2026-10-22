# GOTCHAS — environment and tooling traps

**Not a session-start file.** It is referenced from `AGENTS.md` in one line and read when
something behaves unexpectedly — or before you spend an hour on a problem this project has
already paid for once. Keeping it off the every-session reading list is deliberate: it can
grow without costing anything per session.

Each entry: what happened, why it matters, what to do. Add one when a trap costs real time.
Delete one when the cause is gone for good — not when it merely feels old.

This is one of the permanent homes a `[GOTCHA]` line in `docs/STATE.md` gets moved into
before that line is deleted.

## Contents

A new entry adds its heading to this list.

- Uncommitted work is NOT in the reflog
- `.gitignore` — the LAST matching rule wins
- The executable bit has to be put in the git index by hand
- A fake-CLI test harness cannot catch what the real CLI rejects
- A tool's relative output path resolves against ITS working directory, not yours
- Waiting on your own process: `pgrep -f` and shell wait loops match themselves
- An agent puts the user's e-mail into a web request
- A red gate that passes on re-run is a finding, not a pass
- A checkout under `/mnt/<drive>` in WSL
- Under WSL, a file named `*.exe` runs on Windows
- A build server the gate started keeps the gate lock
- A worker spawned from a lead's shell inherits its child-session markers
- Background jobs die with the session and in a low-memory reap
- An incremental build misses its always-run inputs
- A timing taken on a busy machine is not a result
- PowerShell from the Microsoft Store leaves suspended processes behind
- A variable the session set does not reach the git hook
- A PowerShell probe whose Set-Location fails goes on in the current folder

---

The kit's entries are in `docs/GOTCHAS_KIT.md`, which a sync replaces; each heading below
points at its entry there. A project's own entry goes after them, whole, and adds its heading
to the Contents. A project that needs a different rule writes it here, and this file wins over
`docs/GOTCHAS_KIT.md`.

## Uncommitted work is NOT in the reflog

Kit rules: docs/GOTCHAS_KIT.md, "Uncommitted work is NOT in the reflog".

## `.gitignore` — the LAST matching rule wins

Kit rules: docs/GOTCHAS_KIT.md, "`.gitignore` — the LAST matching rule wins".

## The executable bit has to be put in the git index by hand

Kit rules: docs/GOTCHAS_KIT.md, "The executable bit has to be put in the git index by hand".

## A fake-CLI test harness cannot catch what the real CLI rejects

Kit rules: docs/GOTCHAS_KIT.md, "A fake-CLI test harness cannot catch what the real CLI rejects".

## A tool's relative output path resolves against ITS working directory, not yours

Kit rules: docs/GOTCHAS_KIT.md, "A tool's relative output path resolves against ITS working directory, not yours".

## Waiting on your own process: `pgrep -f` and shell wait loops match themselves

Kit rules: docs/GOTCHAS_KIT.md, "Waiting on your own process: `pgrep -f` and shell wait loops match themselves".

## An agent puts the user's e-mail into a web request

Kit rules: docs/GOTCHAS_KIT.md, "An agent puts the user's e-mail into a web request".

## A red gate that passes on re-run is a finding, not a pass

Kit rules: docs/GOTCHAS_KIT.md, "A red gate that passes on re-run is a finding, not a pass".

## A checkout under `/mnt/<drive>` in WSL

Kit rules: docs/GOTCHAS_KIT.md, "A checkout under `/mnt/<drive>` in WSL".

## Under WSL, a file named `*.exe` runs on Windows

Kit rules: docs/GOTCHAS_KIT.md, "Under WSL, a file named `*.exe` runs on Windows".

## A build server the gate started keeps the gate lock

Kit rules: docs/GOTCHAS_KIT.md, "A build server the gate started keeps the gate lock".

## A worker spawned from a lead's shell inherits its child-session markers

Kit rules: docs/GOTCHAS_KIT.md, "A worker spawned from a lead's shell inherits its child-session markers".

## Background jobs die with the session and in a low-memory reap

Kit rules: docs/GOTCHAS_KIT.md, "Background jobs die with the session and in a low-memory reap".

## An incremental build misses its always-run inputs

Kit rules: docs/GOTCHAS_KIT.md, "An incremental build misses its always-run inputs".

## A timing taken on a busy machine is not a result

Kit rules: docs/GOTCHAS_KIT.md, "A timing taken on a busy machine is not a result".

## PowerShell from the Microsoft Store leaves suspended processes behind

Kit rules: docs/GOTCHAS_KIT.md, "PowerShell from the Microsoft Store leaves suspended processes behind".

## A variable the session set does not reach the git hook

Kit rules: docs/GOTCHAS_KIT.md, "A variable the session set does not reach the git hook".

## A PowerShell probe whose Set-Location fails goes on in the current folder

Kit rules: docs/GOTCHAS_KIT.md, "A PowerShell probe whose Set-Location fails goes on in the current folder".
