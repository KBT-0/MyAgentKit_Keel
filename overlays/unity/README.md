# Overlay: Unity

Install with `bootstrap.sh . --overlay unity`. This README is NOT copied — only `files/` is.

## What it adds

| File | What it is |
|---|---|
| `unity/AGENTS.md` | Folder rules: the four access tiers, the concurrency rule, commit hygiene, thin scenes |
| `unity/CLAUDE.md` | Pointer |
| `docs/UNITY_SETUP.md` | Assembly layout, consuming a pure core from Unity, VCS settings, and the MCP server: which one, how to pin it, and how to scope what an agent may drive |
| `scripts/unity_gate.sh` | The Unity Test Framework gate, batchmode, with its evidence checks |
| `docs/kit/unity.gitignore-fragment` | `.gitignore` rules to append by hand |

## Why the Unity gate is a separate script

`scripts/check.sh` stays fast and Unity-free: it runs on every commit through the pre-commit
hook, and a Unity batchmode run's cost scales with project size (editor start and import), so
it is not run on every commit. The Unity gate is opt-in and runs when Unity-side work is
finished, or on a schedule. (Sources: `docs/UNITY_SETUP.md`, "Sources".)

It is also deliberately not wired into `check.sh`, so installing this overlay does not
require editing a project-owned file. Ordinary work is unaffected by an overlay you took.

## Two things to do by hand after installing

1. **Append the gitignore fragment.** `bootstrap.sh` copies files; it does not merge into an
   existing `.gitignore`. Paste the fragment into the "Stack-specific rules" section — and
   keep the re-include block at the very END of the file, because git applies the LAST
   matching rule.
2. **Add the boundary check.** The networking library confinement (only the adapter assembly
   may import it) belongs in `scripts/boundary_checks.sh`, with its fixture test beside the
   file's example test. `docs/UNITY_SETUP.md` gives both, ready to paste.

## The MCP server it defaults to

`docs/UNITY_SETUP.md` names one default, CoplayDev's
[`MCP for Unity`](https://github.com/CoplayDev/unity-mcp) (MIT), and lists the alternatives
with their constraints: IvanMurzak's `Unity-MCP` (Apache-2.0, runs in a compiled game too)
and Unity's own server (Unity 6 or later, Unity Cloud, a Unity AI subscription, open beta
when read). A default you can override beats an empty decision. The default configures
whichever MCP clients it detects instead of binding the project to one vendor's editor.

Two findings are worth reading even if you pick a different server, because both cost real
time to discover and both were re-checked against MCP for Unity v10.3.0 (2026-10-04): the
always-on `core` tool group contains destructive operations the group labels do not suggest,
and **a per-tool deny list in the MCP client is bypassable** through the server's batch tool,
so scope has to be enforced in the editor's own tools window. MCP is also not a gate: it
needs a running editor and a connected client, so it is not a repeatable one-command run.

## What this overlay assumes

That the project keeps its game logic in a pure, engine-free core and treats Unity as one
consumer of it. If the project is Unity all the way down, delete §2 and §3 of
`docs/UNITY_SETUP.md` (the assembly split and the core wiring), but keep §1 (version control settings), §4 (MCP scope), the
`unity/AGENTS.md` rules, the gate and the gitignore fragment: none of them depends on a core.
