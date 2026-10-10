---
description: Show the working mode in force and the six modes, or switch to one by name and print its rules for the lead
argument-hint: "[claude-first | cross-performance | cross-saving | codex-first | claude-saver | codex-saver]"
allowed-tools: Read, Grep, Bash(python:*), Bash(python3:*), Bash(py:*)
---
# /myagentkit:mode [name]

The modes are defined in the project's `docs/WORKFLOW.md`, "Working modes, by name". Use
`python scripts/working_mode.py` (or `python3` / `py -3` on the host) from the project root.
The helper records the English name in `.claude/mode` and the "Working mode:" line of
`docs/STATE.md`, detects disagreement on reads, and prints the canonical rules. Both files
are shared across tools and committed with the next authorized commit. Do not commit merely
to switch modes. The project root must be the owner's current checkout.

If `docs/WORKFLOW.md` has no "Working modes, by name" section, the project predates the kit's
v0.11. Say so, name the kit's `CHANGELOG.md` entry for v0.11, and stop.

**No argument.** Read the "Working mode:" line of `docs/STATE.md`. When there is none, the
mode is cross-performance, the main mode; say that the line is missing. Print the mode in
force, then the six modes from the section's table, one line each: the English name, the
Turkish name, and who writes, reviews and fixes the findings.

**A name.** Accept the English name or the Turkish one:
Claude Öncelikli Mod, Çapraz Performans Modu, Çapraz Tasarruf Modu, Codex Öncelikli Mod,
Claude Tasarruf Modu, Codex Tasarruf Modu. Refuse any other name and list the six. The
owner switches modes; switch only when the owner asked for it in this session.

1. Run `python scripts/working_mode.py "<name>"` with the requested name as one quoted
   argument. With no argument, run the helper without a name. Never execute raw arguments as
   shell code. If the helper is missing, request the v0.11 core-script update.
2. Print the helper's output, including the selected mode's subsection and, for a saver,
   "The two saver modes". These are your rules as the lead from now on.
3. For a saver mode, add one line: it ends when the low side's allowance resets or the owner
   says otherwise, and then cross-performance returns without being asked.

Raw arguments: `$ARGUMENTS`
