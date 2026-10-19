#!/usr/bin/env python3
"""PostToolUse(Edit|Write|NotebookEdit): warn about a forbidden import the moment it is written.

It sees Edit, Write and NotebookEdit only: a write through the shell (sed, a here-document, a script run by
Bash or PowerShell) names no file to the hook, so it gets no early warning here (#151); the gate
below still catches it. A notebook cell (NotebookEdit) is checked against the ".py" entries: a
Jupyter cell is Python code, and an ".ipynb" path never ended in ".py", so it went unchecked
(#264). On Windows and macOS the path and the suffix match in any case, as their default
filesystems (NTFS, APFS) do.

It warns after the write; scripts/check.sh is the gate (a PostToolUse hook cannot block, the
tool already ran: https://code.claude.com/docs/en/hooks).

CI catches it too. This hook only shortens the feedback loop from "next commit" to "next
second", which is the difference between a one-line fix and an argument with a rebase.

Configured by the setup interview: one entry per enforced boundary, mirroring the greps in
scripts/check.sh. If the two disagree, scripts/check.sh is the authority — it is what CI
runs, and this file is convenience for a single tool.
"""
import json
import os
import sys

# (path fragment, file suffix, forbidden tokens, message)
BOUNDARIES = [
    # ("/src/domain/", ".py", ("from myapp.web", "import myapp.web"),
    #  "the domain layer must not depend on the delivery layer"),
    "{{BOUNDARY_GUARDS}}",
]
# The marker above is a LIVE list element, not a comment, on purpose: the setup interview
# replaces the string with real tuples (or with nothing, for a project with no guardable
# boundary). A marker in a comment can be half-filled — token replaced, "#" kept — leaving
# an empty list that guards nothing while looking configured. As a string it is instead
# caught below, loudly, on every edit until setup finishes.

data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
tool_input = data.get("tool_input", {})
# Native Windows sends the path with backslashes; the fragments use "/" (hooks reference).
path = (tool_input.get("file_path") or tool_input.get("notebook_path") or "").replace("\\", "/")
# Write sends `content`; Edit sends `new_string`. An earlier version read `new_str` — a
# field no tool sends — so everything written through Edit went uninspected while the hook
# looked installed. If these names drift, this hook is inert again: verify them against the
# tool's actual schema, not from memory. NotebookEdit sends `notebook_path` and `new_source`.
content = "".join(tool_input.get(k) or "" for k in ("content", "new_string", "new_source"))
fold = str.casefold if os.name == "nt" or sys.platform == "darwin" else str

unconfigured = [b for b in BOUNDARIES if isinstance(b, str)]
if unconfigured:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": (
            "guard_boundaries.py is UNCONFIGURED: its BOUNDARIES list still holds the "
            "setup placeholder, so no boundary is being guarded. Finish setup/INTERVIEW.md "
            "(scripts/check.sh is failing on the same marker)."
        ),
    }}))
    sys.exit(0)

for fragment, suffix, tokens, why in BOUNDARIES:
    suffixes = (suffix, ".ipynb") if suffix == ".py" else (suffix,)
    if fold(fragment) not in fold(path) or not fold(path).endswith(tuple(map(fold, suffixes))):
        continue
    hits = [t for t in tokens if t in content]
    if not hits:
        continue
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": (
            f"BOUNDARY VIOLATION in {path}: {hits} — {why}. "
            f"This will not survive CI (scripts/check.sh). Fix it now, before the next edit "
            f"builds on top of it."
        ),
    }}))
    break
