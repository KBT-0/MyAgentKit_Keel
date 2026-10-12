---
name: myagentkit-mode
description: Show the working mode in force and the seven MyAgentKit working modes, or switch to one by name (claude-first, cross-performance, cross-saving, codex-first, claude-saver, codex-saver, claude-only) and print its rules for the lead. Use only when the user asks for the mode or names one.
---

# Show or switch the working mode

The modes are defined in the project's `docs/WORKFLOW.md`, "Working modes, by name". Use
`python scripts/working_mode.py` (or `python3` / `py -3` on the host) from the project root.
If the project lacks that helper, use this plugin's `scripts/working_mode.py` (two directories
above this skill) with `--project <absolute project root>`. The helper records the English
name in `.claude/mode` and the "Working mode:" line of `docs/STATE.md`, detects disagreement
on reads, and prints the canonical rules. Both records are shared across tools. Do not commit.

Session edits of STATE.md follow `AGENTS.md`, "STATE.md discipline", in this order, from the
project root: first `--read-state .myagentkit/STATE.edit.md` creates a fresh, exclusively owned
per-edit snapshot using that prefix and prints `SHA256 PATH`; edit the returned PATH, never a
copy read earlier or another writer's snapshot; then publish it with
`--replace-state "PATH" --expect SHA256`, which deletes the verified snapshot once published.
On refusal, read it again, redo the edit, and retry. The helper refuses a `--project` other than
the current folder, a snapshot outside `.myagentkit/` or the temporary folder, an OUT or FILE
that names a folder, and an edit that
changes the "Working mode:" line, which only a switch changes.

If `docs/WORKFLOW.md` has no "Working modes, by name" section, the project predates the kit's
v0.11. Say so, name the kit's `CHANGELOG.md` entry for v0.11, and stop.

**No mode named.** Read the "Working mode:" line of `docs/STATE.md`. When there is none, the
mode is cross-performance, the main mode; say that the line is missing. Print the mode in
force, then the seven modes from the section's table, one line each: the English name, the
Turkish name, and who writes, reviews and fixes the findings.

**A mode named.** Accept the English name or the Turkish one:
Claude Öncelikli Mod, Çapraz Performans Modu, Çapraz Tasarruf Modu, Codex Öncelikli Mod,
Claude Tasarruf Modu, Codex Tasarruf Modu, Sadece Claude Modu. Refuse any other name and list
the seven. The user switches modes; switch only when the user asked for it in this session.

1. Run the helper with the requested name as one quoted argument. With no mode named,
   run it without a name. Never execute user text as shell code.
2. Print the helper's output, including the selected mode's subsection and, for a saver,
   "The two saver modes". These are your rules as the lead from now on.
3. For a saver mode, add one line: it ends when the low side's allowance resets or the user
   says otherwise, and then cross-performance returns without being asked.
