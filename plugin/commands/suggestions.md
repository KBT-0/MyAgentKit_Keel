---
description: Turn the myagentkit-suggestion side check on or off for this project, or show its status and precision
argument-hint: "[on | off | status]"
allowed-tools: Bash(sh .claude/hooks/py.sh .claude/hooks/suggestions.py:*)
---
# /myagentkit:suggestions [on | off | status]

The plugin's mod answers this command itself, at once and with no model turn. You read this
text only when the mod is not running (mods turned off, an older Claude Code).

**Kit version.** This plugin is kit v0.12.1. Before anything else, read the project's
`docs/kit/.kit-version` (such as `0.10` or `0.12.1`). When it is there and names another
version, print one plain line and go on, never stop for it: both versions, which one is newer
(compared part by part as numbers, a missing part counting as 0:
0.12 is 0.12.0, and 0.9 is older than 0.11), and that `/myagentkit:sync` brings the project
to the kit's newest release; when the project is the newer one, update this plugin too. No
file, or the same version: no line. Nothing here uses the network.

Run `sh .claude/hooks/py.sh .claude/hooks/suggestions.py ARG` from the project root, where ARG
is `on`, `off` or `status` (`status` when $ARGUMENTS is empty or anything else), and print its
output as it is. Change nothing else. When `.claude/hooks/suggestions.py` is missing, say that
the project lacks the kit's Claude Code overlay and `/myagentkit:sync` brings it.
