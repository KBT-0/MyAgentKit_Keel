---
name: myagentkit-mode
description: Show the working mode in force and the six MyAgentKit working modes, or switch to one by name (claude-first, cross-performance, cross-saving, codex-first, claude-saver, codex-saver) and print its rules for the lead. Use only when the user asks for the mode or names one.
---

# Show or switch the working mode

The modes are defined in the project's `docs/WORKFLOW.md`, "Working modes, by name". That
section is canonical; this skill only reads it and records the choice. The mode in force is
the "Working mode:" line of `docs/STATE.md`, the one cross-tool memory, so a Claude session
reads the same mode.

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

1. Set the "Working mode:" line of `docs/STATE.md` to the English name, keeping the rest of
   the line. When the file has no such line, add one below the first `---`:
   `**Working mode:** <name> (docs/WORKFLOW.md, "Working modes, by name").` Change nothing
   else in the file. Do not commit.
2. Print that mode's subsection from `docs/WORKFLOW.md` exactly as written, and for
   claude-saver or codex-saver also "The two saver modes", whose rules both bind. These are
   your rules as the lead from now on.
3. For a saver mode, add one line: it ends when the low side's allowance resets or the user
   says otherwise, and then cross-performance returns without being asked.
