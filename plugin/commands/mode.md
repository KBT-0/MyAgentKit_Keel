---
description: Show the working mode in force and the three modes, or switch to one by name and print its rules for the lead
argument-hint: "[solo [\"family: X\"] | cross | saver \"low: X\"]"
allowed-tools: Read, Grep, Bash(python scripts/working_mode.py:*), Bash(python3 scripts/working_mode.py:*), Bash(py -3 scripts/working_mode.py:*)
---
# /myagentkit:mode [name]

The modes are defined in the project's `docs/WORKFLOW.md`, "Working modes, by name". Use
`python scripts/working_mode.py` (or `python3` / `py -3` on the host) from the project root.
The helper records the name in `.claude/mode` and the "Working mode:" line of
`docs/STATE.md`, detects disagreement on reads, and prints the canonical rules. Both files
are shared across tools and committed with the next authorized commit. Do not commit merely
to switch modes. The project root must be the owner's current checkout.

STATE.md session edits follow `docs/AGENTS.md`, "STATE.md discipline", in its order
(`--read-state`, edit the returned PATH, `--replace-state "PATH" --expect SHA256`; on refusal,
read it again). Only a mode switch changes the "Working mode:" line; a mode name from before
v0.11 may become `solo`, `cross` or `saver` this way.

If the helper prints an ACTION, show it and stop.

**No argument.** Read the "Working mode:" line of `docs/STATE.md`. When there is none, the
mode is solo, the main mode; say that the line is missing. Print the mode in force, then
the three modes from the section's table, one line each: the name and who writes, reviews
and fixes the findings.

**A name.** Accept `solo`, `cross` or `saver`, in any case. Refuse any other name and list
the three. The owner switches modes: switch only when the owner asks, never on your own
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

Raw arguments: `$ARGUMENTS`
