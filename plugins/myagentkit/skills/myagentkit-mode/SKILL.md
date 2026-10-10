---
name: myagentkit-mode
description: Show the working mode in force and the six MyAgentKit working modes, or switch to one by name (claude-first, cross-performance, cross-saving, codex-first, claude-saver, codex-saver) and print its rules for the lead. Use only when the user asks for the mode or names one.
---

# Show or switch the working mode

The modes are defined in the project's `docs/WORKFLOW.md`, "Working modes, by name". Use
`python scripts/working_mode.py` (or `python3` / `py -3` on the host) from the project root.
If the project lacks that helper, use this plugin's `scripts/working_mode.py` (two directories
above this skill) with `--project <absolute project root>`. The helper records the English
name in `.claude/mode` and the "Working mode:" line of `docs/STATE.md`, detects disagreement
on reads, and prints the canonical rules. Both records are shared across tools. Do not commit.

If `docs/WORKFLOW.md` has no "Working modes, by name" section, the project predates the kit's
v0.11. Say so, name the kit's `CHANGELOG.md` entry for v0.11, and stop.

**No mode named.** Read the "Working mode:" line of `docs/STATE.md`. When there is none, the
mode is cross-performance, the main mode; say that the line is missing. Print the mode in
force, then the six modes from the section's table, one line each: the English name, the
Turkish name, and who writes, reviews and fixes the findings.

**A mode named.** Accept the English name or the Turkish one:
Claude Öncelikli Mod, Çapraz Performans Modu, Çapraz Tasarruf Modu, Codex Öncelikli Mod,
Claude Tasarruf Modu, Codex Tasarruf Modu. Refuse any other name and list the six. The
user switches modes; switch only when the user asked for it in this session.

1. Run the helper with the requested name as one quoted argument. With no mode named,
   run it without a name. Never execute user text as shell code.
2. Print the helper's output, including the selected mode's subsection and, for a saver,
   "The two saver modes". These are your rules as the lead from now on.
3. For a saver mode, add one line: it ends when the low side's allowance resets or the user
   says otherwise, and then cross-performance returns without being asked.
