# /unity rules

Read on top of the root `AGENTS.md`, never instead of it. The sources named in brackets are
listed with their URLs at the end of `docs/UNITY_SETUP.md`.

- **Game logic is NOT written here.** It is called from the pure core. MonoBehaviours stay
  thin: gather input, call core, present the result. A rule that lives in a MonoBehaviour is
  a rule the fast EditMode tests cannot reach. [Unity blog, "Humble Object"; Unity Manual,
  Assembly Definition importer, No Engine References]
- Assembly split and the reference whitelist: `docs/UNITY_SETUP.md`. The compiler enforces
  it; that is the point of splitting.
- `using {{NET_LIB}}` ONLY inside the adapter assembly. `scripts/check.sh` greps for
  violations once the check from `docs/UNITY_SETUP.md` §2 is pasted in. Swapping the networking library should touch exactly one assembly.
- Server build target is headless. [Unity Manual, Dedicated Server build] Strip client-only
  code with `#if UNITY_SERVER` [Unity Manual, Scripting symbol reference]. Where a whole
  assembly is client-only, prefer `defineConstraints: ["!UNITY_SERVER"]` on that assembly
  (the manual documents `!` negation, with `!ENABLE_IL2CPP` as its example; `!UNITY_SERVER`
  itself is this kit's inference from that rule and is not shown in the manual).
- **Ready-made third-party code (Asset Store packages, libraries you did not write) lives in
  host-side assemblies only (Client, Server, Net.Adapter) and never enters the pure core.**
  The core's asmdef has `noEngineReferences: true` and an empty `references` list.
  [Unity Manual, Assembly Definition importer]

## The Unity gate

**Unity-side work is not done until PlayMode tests pass.** Run `./scripts/unity_gate.sh`
(Unity Test Framework, EditMode + PlayMode in batchmode; needs Unity installed, and
`UNITY_PATH` set if `unity` is not on PATH).

It is separate from `./scripts/check.sh` on purpose: the fast gate runs on every commit, and
the batchmode run's cost scales with project size (editor start and import), so it is not
run on every commit. Both still apply: the fast one always, this one when you touched Unity.
[Unity Test Framework, "Running tests from the command line"; Unity Manual, "Editor command
line arguments"; GameCI test runner (runs both modes by default)]

**MCP is not a gate.** It needs a running editor and a connected client, so it is not a
repeatable one-command run. The gate is `scripts/unity_gate.sh`.

## Unity access tiers

Agents may work in Unity: through the editor's APIs, not by blind YAML edits.

**Tier 1: C# under `Assets/`.** Free, normal code rules. Auto Refresh imports a changed `.cs`
file when the editor regains focus, so editing one with the editor open is fine. A new `.cs`
file gets a `.meta` from Unity on the next refresh; commit them together. [Unity Manual,
Asset database refresh; Unity blog, "How to author Scenes and Prefabs with a focus on version
control": ".meta files should always be checked into version control"]

**Tier 2: scenes, prefabs and components VIA MCP.** Allowed. Unity performs the write through
its own APIs, so GUIDs and references stay consistent. Do not count on Undo: in MCP for
Unity v10.3.0 some edits are recorded as Undo steps (a prefab instantiate, a property
change), but deleting a GameObject, deleting or moving an asset, and editing a script are
not (checked in that version's source; no other server was checked). Git is the undo that
always works. Git sees a scene change only after the scene is saved.

**Tier 3: editor scripts that GENERATE assets** (prefab builders, importers, bakers):
PREFERRED for anything that must be reproducible. Such a script can be re-run in batchmode
(`-executeMethod`, Unity Manual, "Editor command line arguments") and the diff is the
generator's source. This is the kit's design preference, not a measured result.

**Tier 4: direct `.unity` / `.prefab` / `.asset` YAML editing.** Narrow use only.
- Allowed: a small surgical diff a human can read, one serialized value. After ANY direct
  YAML edit, open the project in the editor (or run `scripts/unity_gate.sh`) and check that
  no reference turned `None` or missing. (This check is taken from practitioner guides, not
  from Unity's manual, which neither allows nor forbids hand edits.)
- Forbidden: structural or hierarchy changes, anything touching GUIDs or fileIDs, ALL
  `.meta` GUID edits (the GUID lives in the `.meta` file, and references use it), bulk
  `ProjectSettings` rewrites. [Unity blog, version control; Unity Manual, "Format
  description" for the fileID links between objects in a file]

**Concurrency rule.** The editor and an agent must never write the same SERIALIZED files
(`.unity`, `.prefab`, `.asset`, `.meta`, `ProjectSettings/`) at once. Either the agent goes
through MCP, so the editor is the only writer, or the editor is closed while the agent edits
those files. Plain `.cs` edits are fine with the editor open (Tier 1). If the editor is open
with unsaved scene changes and you are about to write a scene file directly, STOP and say
so: the editor holds its own in-memory copy of an open scene, and a later save from the
editor can overwrite your edit. The gate has the same limit: batchmode cannot open a project
that an Editor has open. [Unity Manual, "Editor command line arguments"]

**Commit hygiene:** scene and prefab changes are committed SEPARATELY from code changes. A
mixed diff is hard to review: the YAML drowns the code. This is the small-diff principle of
`docs/research/ai-review-workflows.md` S3 applied to Unity; Unity itself recommends splitting
content across scenes and prefabs, not separate commits.

**Editor-only tooling stays editor-only.** An assembly under `Assets/Editor/` that references
an editor package does not compile without it. Nothing at runtime, and nothing in the pure
core, may depend on it. Give the Editor assembly an asmdef with Platforms set to Editor only.
[Unity Manual, "Special folders"; Assembly Definition importer, Platforms]

**Design principle: thin scenes.** A scene holds references and wiring; reusable content
lives in prefabs and, where it must be reproducible, comes from a generator. This keeps scene
diffs small and merge conflicts rare. [Unity blog, version control: prefabs mitigate
conflicts from complex scene edits]
