# UNITY_SETUP.md — assembly layout, core wiring, VCS settings, MCP scope

Do this before writing Unity gameplay or networking code. An agent cannot create the Unity
project — {{OWNER_NAME}} owns that in Unity Hub. Everything below is what turns the
architecture boundaries into things the compiler enforces.

Claims here name their source in brackets; the URLs are in "Sources" at the end. Where a
sentence is the kit's own inference or preference, it says so.

## 1. Version control settings (do these first)

- **Edit → Project Settings → Editor → Asset Serialization → Mode: Force Text.** This is
  Unity's default, so the task is to keep it. Switching to binary removes the mergeability
  of scenes and prefabs, and a binary scene is an opaque blob in review. [Unity Manual,
  Editor settings; Unity blog, version control]
- **Edit → Project Settings → Version Control → Mode: Visible meta files.** Also Unity's
  default; keep it. `.meta` files hold the GUIDs that link assets together, and they are
  repository content: commit them, always. [Unity Manual, Version control integrations;
  Unity blog, version control]
- **Wire UnityYAMLMerge** (Smart Merge). It ships with the editor. Unity recommends using it
  as the default merge tool for all YAML files. [Unity blog, version control] Unity's manual
  sets it up as a git **mergetool**, which you run by hand after a conflict:

  ```
  [merge]
      tool = unityyamlmerge
  [mergetool "unityyamlmerge"]
      trustExitCode = false
      cmd = '<path to UnityYAMLMerge>' merge -p "$BASE" "$REMOTE" "$LOCAL" "$MERGED"
  ```

  (`<path to UnityYAMLMerge>` is under the editor's `Tools` folder on Windows and under
  `Helpers` inside `Unity.app` on macOS. [Unity Manual, Smart Merge])

  To have git call it by itself on a scene conflict you need a `[merge "unityyamlmerge"]`
  *driver* plus `*.unity merge=unityyamlmerge` and `*.prefab merge=unityyamlmerge` lines in
  `.gitattributes`. Unity's manual documents only the mergetool setup, not the driver, so
  build the driver command from the mergetool arguments above and try it on a throwaway
  merge before you rely on it. (A driver is not the same thing as a mergetool.)

## 2. Assembly layout (one asmdef per module)

One folder per assembly under `Assets/`, each with its own `.asmdef`. The names mirror the
module map in `docs/ARCHITECTURE.md`.

```
Assets/
  Client/            {{ASM_PREFIX}}.Client.asmdef
  Server/            {{ASM_PREFIX}}.Server.asmdef
  Shared/            {{ASM_PREFIX}}.Shared.asmdef
  Net/Adapter/       {{ASM_PREFIX}}.Net.Adapter.asmdef
```

### Reference whitelist — the boundary, enforced by the compiler

| Assembly | May reference | Must NOT reference |
|---|---|---|
| `{{ASM_PREFIX}}.Shared` | the pure core, Unity engine | Client, Server, {{NET_LIB}} |
| `{{ASM_PREFIX}}.Net.Adapter` | the pure core, Shared, **{{NET_LIB}}** | Client, Server |
| `{{ASM_PREFIX}}.Server` | the pure core, Shared, Net.Adapter | Client |
| `{{ASM_PREFIX}}.Client` | the pure core, Shared, Net.Adapter | Server |

Code in one assembly can use another's types only through an explicit reference in the
asmdef, and two assemblies cannot reference each other. [Unity Manual, Assembly definition
referencing] That is why the whitelist is a compiler matter, not a convention.

Two holes to close, or the compiler does not enforce what the table says:

- **Precompiled DLLs.** By default an asmdef references ALL precompiled assemblies in the
  project; only `overrideReferences: true` narrows that to the DLLs listed in the asmdef's
  `precompiledReferences`. [Unity Manual, Assembly Definition importer, Override References]
  So if {{NET_LIB}} is a precompiled DLL (under `Plugins/`, not an asmdef package), set
  `overrideReferences: true` on every assembly and list the DLL only in the adapter's
  `precompiledReferences`. Otherwise Unity references it from every assembly, and only the
  grep below stands guard. If it is an asmdef package, the table holds as written.
- **Loose scripts.** Scripts outside any asmdef compile into the predefined assembly
  (Assembly-CSharp), and the predefined assemblies reference every assembly that has
  Auto Referenced on. [Unity Manual, Assembly definitions intro; Assembly definition
  referencing; Assembly Definition importer, Auto Referenced] So set `autoReferenced: false`
  on Client, Server and Net.Adapter, and keep every script under an asmdef folder. (That the
  whitelist then binds loose scripts is this kit's inference from those pages; it has not
  been tried in a Unity version.)

**{{NET_LIB}} is imported ONLY inside the adapter assembly.** Keep the folder name
recognisable, because the grep gate below keys on the path. Swapping the networking library
should then touch exactly one assembly — that is the entire reason for this split.

If the project is Unity all the way down, with no pure core, skip this section and §3
(the assembly split and the core wiring) and keep the rest (see `overlays/unity/README.md`, "What this overlay assumes").

### The matching gate

Add to `scripts/boundary_checks.sh`:

```sh
hits=$(scan_grep 'using {{NET_LIB}}' | grep '^unity/' | grep -v 'Net/Adapter')
if [ -n "$hits" ]; then
  echo "FAIL [boundary]: {{NET_LIB}} outside the adapter assembly:"
  echo "$hits"
  fail=1
fi
```

And its negative test, in `scripts/boundary_selftests.sh` — not optional:

```sh
# Nothing is written into the checkout: the import sits in a file outside the tree, scanned
# as if it were unity/Assets/Client/Injected.cs. expect_fail (scripts/check.sh) requires a
# nonzero exit AND this check's own FAIL line; the self-test already proved the baseline green.
printf 'using {{NET_LIB}};\n' > "$work/net-import.cs"
expect_fail "{{NET_LIB}} confinement gate rejects an import outside the adapter" \
  'FAIL [boundary]: {{NET_LIB}} outside the adapter assembly:' \
  GATE_SELFTEST_EXTRA_FILE="$work/net-import.cs" GATE_SELFTEST_EXTRA_PATH=unity/Assets/Client/Injected.cs
```

## 3. Consuming the pure core from Unity

The core is engine-free C# living outside the Unity project. Wire it as a **local UPM
package** rather than copying sources:

1. Add a `package.json` beside the core, once. Only `name` and `version` are required;
   `displayName` and `description` are recommended, and `name` is a reverse domain name such
   as `com.you.core`. [Unity Manual, Package manifest]

   ```json
   {
     "name": "{{CORE_PACKAGE_NAME}}",
     "version": "0.0.1",
     "displayName": "Core",
     "description": "Pure C# logic. No Unity."
   }
   ```

2. Give the core an `.asmdef` with `"noEngineReferences": true` and an EMPTY `references`
   list (and, if the project holds precompiled DLLs, `overrideReferences: true` with no
   precompiled references listed), and reference it from `{{ASM_PREFIX}}.Shared`.
   Third-party and Asset Store code never enters the core. [Unity Manual, Assembly
   Definition importer]

3. Register it in `Packages/manifest.json` with a path RELATIVE TO THE `Packages/` FOLDER
   (not the project root) and forward slashes. [Unity Manual, Install a UPM package from a
   local folder] `{{CORE_PATH}}` below is that path, for example `../../core` for a `core/`
   folder two levels above `Packages/`:

   ```json
   "{{CORE_PACKAGE_NAME}}": "file:{{CORE_PATH}}"
   ```

`"noEngineReferences": true` is the load-bearing line: with it, Unity does not add references
to `UnityEngine` or `UnityEditor` when it compiles the core. [Unity Manual, Assembly
Definition importer] If Unity ever needs an engine reference inside the core, the boundary is
being violated — fix the layout, do not add the reference.

## 4. MCP — how agents reach the editor

Agents drive the editor through an MCP server (the access tiers are in `unity/AGENTS.md`).
The server is ultimately {{OWNER_NAME}}'s call, but this overlay ships a default rather than
an empty decision.

**Default: CoplayDev's [`MCP for Unity`](https://github.com/CoplayDev/unity-mcp) (MIT).** Its
README lists Claude Desktop and Claude Code, Cursor, VS Code, Windsurf, Cline and Gemini CLI
among the clients it configures, and needs Python 3.10+ (via `uv`). [CoplayDev README] That
keeps the project from being bound to one vendor's editor or account. It is a default, not a
verdict; the alternatives trade differently:

- IvanMurzak's `Unity-MCP` (Apache-2.0): runs inside a compiled game as well, and needs an
  agent that supports Skills or dynamic MCP tool updates. [IvanMurzak README]
- Unity's own MCP server: needs Unity 6 (6000.0) or later with the AI Assistant package, a
  project connected to Unity Cloud, and an active Unity AI trial or subscription, and was in
  open beta when we read it. [Unity blog, Unity AI MCP]

Pick by those constraints. (We name no version numbers here; they go stale.)

```
Unity → Package Manager → Add package from git URL:
  https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#<release-tag>
then: Window → MCP for Unity → Configure All Detected Clients
```

**Pin a release tag, never `#main`.** `#main` follows the default branch, so reinstalling
pulls whatever it points to that day; branches and tags can point to different commits over
time. [Unity Manual, Git dependencies] Bumping the pin is a deliberate task, not a side
effect of someone reinstalling. Take the newest release from the tag list rather than copying
a version out of this document. Commit `Packages/packages-lock.json`, which records the
resolved commit of a Git dependency [Unity Manual, Lock files], and for the strictest pin use
a full commit hash, because a tag can be moved and Unity does not accept a shortened SHA-1.
[Unity Manual, Git dependencies]

**Verify the catalogue against the version you actually installed.** The tool groups are
where the surprises live, and a server's tool list changes between releases. Do this after
any bump.

### Scope: decide it, then enforce it in the right place

Reasonable defaults for what an agent may drive (the kit's choice; no source recommends a
permission list):

- **In scope:** scene and GameObject operations, component add/remove and serialized value
  edits, prefab create/instantiate/apply, script editing, and read-only introspection.
  Introspection especially: a hierarchy report is usually much smaller than scene YAML
  dumped into context. (One third-party benchmark of a synthetic 250-object scene measured
  about 99% fewer tokens with a hierarchy report; its author warns that this does not hold
  for every scene. Measure your own. [Unity MCP Efficient listing])
- **Out of scope:** destructive project-wide operations, `ProjectSettings` rewrites, render
  pipeline or quality changes, package install/removal, `.meta` and GUID edits, and builds.

**Two findings that cost real time, both worth checking against whatever server you pick.**
Both were re-checked against MCP for Unity v10.3.0 (2026-10-04); the server may have changed
since.

1. **Tool groups do not match your scope list.** In MCP for Unity v10.3.0, `manage_packages`,
   `manage_build`, `manage_graphics`, `manage_physics`, `manage_asset` (which deletes and
   moves assets) and `execute_menu_item` (blocklist: `File/Quit` only, so any other menu
   item runs) are all in the default `core` group, which the server's Tool Groups page
   describes as "always on". [CoplayDev v10.3.0 source; MCP for Unity, Tool Groups] The
   names are reassuring; the groupings are not. Read the tool catalogue yourself rather than
   trusting the group labels. (The server's SECURITY.md treats actions that change the Unity
   project as out of its scope, because that is the product's purpose.)
2. **A per-tool deny list in the MCP CLIENT is bypassable.** `batch_execute` runs a list of
   calls editor-side and checks only the editor's own enabled-tools state per call; it never
   sees the client's permission list. [CoplayDev v10.3.0 source, `BatchExecute.cs`] Claude
   Code's MCP permission rules match a server and tool name (`mcp__server__tool`), so
   calls inside a batch reach the client as one `batch_execute` call. [Claude Code,
   Permissions] **Enforce scope in the editor's own tools window (Window → MCP for Unity →
   Tools), not in the client config.** If you must also enforce it in the client, deny
   `batch_execute` itself, not only the tools you fear. Note that the server's `manage_tools`
   meta-tool can switch groups on from a session. [MCP for Unity, Tool Groups]

Whatever cannot be enforced by mechanism is out of scope BY RULE, which means a review of
any MCP-driven change has to look for it. Say so explicitly rather than implying the
checkbox covered it.

### MCP is not a gate, and its cost depends on the client

It needs a running editor and a connected client, so it is not a repeatable one-command run;
the gate is `scripts/unity_gate.sh`.

On cost: in Claude Code an MCP server is cheap by default. With tool search, which is on by
default, only tool names and server instructions load at session start; schemas load when
needed. [Claude Code, MCP] The whole catalogue is paid up front only where tool search is
off: a custom `ANTHROPIC_BASE_URL` on a non-first-party host, `ENABLE_TOOL_SEARCH=false`, or
a model older than Opus 4 or Sonnet 4. [Claude Code, MCP] Clients without tool search (for
example some gateways) load every enabled server's schemas up front; for MCP for Unity's
full set that was on the order of 20k tokens in one third-party estimate (48 tools in v10.1.0,
about 23,000 tokens at four characters per token, a context-size figure rather than a bill).
[Unity MCP Efficient listing] The server's `core` group is always on, so scope it with the
Tools window, and still enable the server for Unity-touching work only and switch it off
afterwards: a server is a trust boundary (it runs code and feeds the model text), and changing
tool definitions mid-session invalidates the prompt cache. [Anthropic, Prompt caching] The
single kit rule on MCP servers is in `docs/WORKFLOW.md`, "MCP hygiene"; this section does not
restate it.

## Done when

- The assemblies above exist with the reference whitelist applied.
- The core is referenced from `{{ASM_PREFIX}}.Shared` and compiles inside Unity.
- `./scripts/check.sh` passes, and `./scripts/check.sh --self-test` shows the
  {{NET_LIB}}-confinement gate going red.
- `./scripts/unity_gate.sh` runs and reports a nonzero executed-test count.

## Sources

Read 2026-10-15. Unity Manual pages are under `https://docs.unity3d.com/Manual/` unless a
full URL is given.

- Unity blog, "Unit testing part 2: Unit testing MonoBehaviours" (Humble Object):
  https://unity.com/blog/technology/unit-testing-part-2-unit-testing-monobehaviours
- Unity blog, "How to author Scenes and Prefabs with a focus on version control":
  https://unity.com/blog/author-scenes-and-prefabs-with-verson-control
- Unity blog, "Unity AI Open Beta: How to get started with MCP":
  https://unity.com/blog/unity-ai-mcp-how-to-get-started
- Assembly Definition importer (No Engine References, Override References, Define
  Constraints, Auto Referenced, Platforms):
  https://docs.unity.com/en-us/engine/6000.0/manual/programming-environment/script-compilation/assembly-definition-files/class-assembly-definition-importer
- Assembly definition referencing: `assembly-definitions-referencing.html`
- Assembly definitions intro: `assembly-definitions-intro.html`
- Dedicated Server build: `dedicated-server-build.html`
- Scripting symbol reference: `scripting-symbol-reference.html`
- Special folders: `SpecialFolders.html`
- Asset database refresh: `AssetDatabaseRefreshing.html`
- Format description (YAML, fileID): `FormatDescription.html`
- Editor settings (Asset Serialization): `class-EditorManager.html`
- Version control integrations: `Versioncontrolintegration.html`
- Smart Merge: `SmartMerge.html`
- Package manifest (package.json): `upm-manifestPkg.html`
- Install a UPM package from a local folder: `upm-localpath.html`
- Git dependencies: `upm-git.html`; Lock files: `upm-conflicts-auto.html`
- Editor command line arguments: `EditorCommandLineArguments.html`
- Unity Test Framework 1.4, "Running tests from the command line":
  https://docs.unity3d.com/Packages/com.unity.test-framework@1.4/manual/reference-command-line.html
- GameCI test runner: https://game.ci/docs/github/test-runner/
- CoplayDev/unity-mcp README, tag v10.3.0 source (`BatchExecute.cs`, `ExecuteMenuItem.cs`,
  `ManagePackages.cs`, `ManageBuild.cs`, `ManageAsset.cs`, `ManageScript.cs`,
  `McpForUnityToolAttribute.cs`) and SECURITY.md: https://github.com/CoplayDev/unity-mcp
- MCP for Unity, Tool Groups: https://coplaydev.github.io/unity-mcp/guides/tool-groups
- IvanMurzak/Unity-MCP README: https://github.com/IvanMurzak/Unity-MCP
- "Unity MCP Efficient" listing (third party, self-promoting, v10.1.0 measurement):
  https://glama.ai/mcp/servers/ia088l2cr7
- Claude Code, MCP: https://code.claude.com/docs/en/mcp; Permissions:
  https://code.claude.com/docs/en/permissions
- Anthropic, Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- The kit's `docs/research/ai-review-workflows.md` S3 (small diffs), cited in `unity/AGENTS.md`.
