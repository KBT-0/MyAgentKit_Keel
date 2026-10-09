---
description: Show the working mode in force and the six modes, or switch to one by name and print its rules for the lead
argument-hint: "[claude-first | cross-performance | cross-saving | codex-first | claude-saver | codex-saver]"
allowed-tools: Read, Grep, Edit
---
# /myagentkit:mode [name]

The modes are defined in the project's `docs/WORKFLOW.md`, "Working modes, by name". That
section is canonical; this command only reads it and records the choice. The mode in force is
the "Working mode:" line of `docs/STATE.md`, the one cross-tool memory, so a Codex session
reads the same mode. There is no second record to drift from it.

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

1. Set the "Working mode:" line of `docs/STATE.md` to the English name, keeping the rest of
   the line. When the file has no such line, add one below the first `---`:
   `**Working mode:** <name> (docs/WORKFLOW.md, "Working modes, by name").` Change nothing
   else in the file. The edit is committed with the next commit, like any STATE.md change.
2. Print that mode's subsection from `docs/WORKFLOW.md` exactly as written, and for
   claude-saver or codex-saver also "The two saver modes", whose rules both bind. These are
   your rules as the lead from now on.
3. For a saver mode, add one line: it ends when the low side's allowance resets or the owner
   says otherwise, and then cross-performance returns without being asked.

Raw arguments: `$ARGUMENTS`
