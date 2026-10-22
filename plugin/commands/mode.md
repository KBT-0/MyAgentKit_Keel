---
description: Show the working mode in force and the three modes, or switch to one by name and print its rules for the lead; autopilot and present switch the owner's presence
argument-hint: "[solo [\"family: X\"] | cross | saver \"low: X\" | autopilot | present]"
allowed-tools: Read, Grep, Bash(python scripts/working_mode.py:*), Bash(python3 scripts/working_mode.py:*), Bash(py -3 scripts/working_mode.py:*)
---
# /myagentkit:mode [name]

**Kit version.** This plugin is kit v0.12.1. Before anything else, read the project's
`docs/kit/.kit-version` (such as `0.10` or `0.12.1`). When it is there and names another
version, print one plain line and go on, never stop for it: both versions, which one is newer
(compared part by part as numbers, a missing part counting as 0:
0.12 is 0.12.0, and 0.9 is older than 0.11), and that `/myagentkit:sync` brings the project
to the kit's newest release; when the project is the newer one, update this plugin too. No
file, or the same version: no line. Nothing here uses the network.

The modes are defined in the project's `docs/WORKFLOW.md`, "Working modes, by name". Use
`python scripts/working_mode.py` (or `python3` / `py -3` on the host) from the project root.
The helper records the name in `.myagentkit/mode` (ignored by Git) and the "Working mode:"
line of `docs/STATE.md`, detects disagreement on reads, and prints the canonical rules. Both
files are shared across tools; STATE.md is committed with the next authorized commit. Do not
commit merely to switch modes. The project root must be the owner's current checkout.

STATE.md session edits follow `docs/AGENTS.md`, "STATE.md discipline" (a direct Read and Edit;
a shell write uses `--read-state`, edit the returned PATH, `--replace-state "PATH" --expect
SHA256`). Only a mode switch changes the "Working mode:" line; a mode name from before
v0.11 may become `solo`, `cross` or `saver` this way.

If the helper prints an ACTION, show it and stop.

**No argument.** Read the "Working mode:" line of `docs/STATE.md`. When there is none, the
mode is solo, the main mode; say that the line is missing. Print the mode in force, then
the three modes from the section's table, one line each: the name and who writes, reviews
and fixes the findings.

**A name.** Accept `solo`, `cross` or `saver`, or the presence switch `autopilot` or
`present`, in any case. Refuse any other name and list the five. The owner switches modes: switch only when the owner asks, never on your own
initiative. One standing exception, given by the owner when choosing saver: when the low
side's allowance has reset, return to the mode the note's `after:` names (`docs/WORKFLOW.md`,
"saver", Ends), in this session or a later one.

1. Run `python scripts/working_mode.py "<name>"` with the requested name as one quoted
   argument. saver names its low side in a second quoted argument, `"low: X"`, and solo may
   name its family, `"family: codex"` (none means claude), taken from the owner's words; cross
   takes no note. The helper refuses saver without it unless the STATE note already has
   that shape. With no argument, run the helper
   without a name. Never execute raw arguments as shell code. If the helper is missing,
   request the v0.11 core-script update.
2. Print the helper's output, the selected mode's subsection. These are your rules as the
   lead from now on.
3. For saver, add one line: it ends when the low side's allowance resets or the owner
   says otherwise, and then the mode its note's `after:` names returns without being asked.

**autopilot / present.** Not a mode: the owner's presence beside the mode in force
(`docs/WORKFLOW.md`, "autopilot, the owner-away switch"). Run the helper with the name and
no note. For `autopilot`, print its output whole: the rules, the checklist for the owner to
go through before leaving, and the `/goal` line the owner types (you cannot run it). The
owner may also turn it on in plain words; the lead then runs the same helper itself. For
`present`, do what its output says: the report, then the questions one by one with the
question tool.

Raw arguments: `$ARGUMENTS`
