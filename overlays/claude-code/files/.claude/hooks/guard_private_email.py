#!/usr/bin/env python3
"""PreToolUse(WebFetch|WebSearch|Bash): refuse a web request that carries the owner's e-mail.

Research sub-agents once put the owner's address into User-Agent headers, up to thirteen
requests each (RESEARCH_LOG.md, "Rules from the transcripts"); a third party's logs cannot be
recalled. The written rule (`docs/WORKFLOW.md`, "Web requests carry no personal data") is
advice; a hook runs every time (https://code.claude.com/docs/en/hooks-guide). An API that
wants contact details gets the project's "Web contact" from `docs/PROJECT.md`, never a
person's own address (owner decision 2026-10-15).

The addresses are git's `user.email` (every scope) and any listed, comma-separated, in
MYAGENTKIT_PRIVATE_EMAILS: the Claude account's address can differ from git's.
ponytail: a Bash command counts as a web request when it names a URL or a web client (curl,
wget, gh, Invoke-WebRequest/RestMethod); a script that reads the address from a file is not
seen. Add a client to WEB when one shows.

Exit 2 blocks the call and returns the message to the agent (Claude Code hook protocol).
"""
import json
import os
import re
import subprocess
import sys

WEB = re.compile(r"https?://|\b(curl|wget|gh|Invoke-WebRequest|Invoke-RestMethod|iwr|irm)\b", re.I)

try:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    tool, call = data.get("tool_name"), data.get("tool_input") or {}
    text = {"WebFetch": call.get("url"), "WebSearch": call.get("query"), "Bash": call.get("command")}.get(tool) or ""
except Exception as exc:
    print(f"BLOCKED: guard_private_email.py could not read the hook input ({exc}). Report this "
          "to the owner.", file=sys.stderr)
    sys.exit(2)
if tool == "Bash" and not WEB.search(text):
    sys.exit(0)

try:
    configured = subprocess.run(["git", "config", "--get-all", "user.email"], capture_output=True,
                                encoding="utf-8", errors="replace", timeout=10).stdout.split()
except Exception:
    configured = []  # no git: the environment list still applies
emails = {e.strip().lower() for e in configured + os.environ.get("MYAGENTKIT_PRIVATE_EMAILS", "").split(",")}
text = text.lower()
if any(e and (e in text or e.replace("@", "%40") in text) for e in emails):
    print("BLOCKED: this web request carries the owner's e-mail address, which must never reach "
          "a third party. Remove it. If the API needs contact details, use the \"Web contact\" "
          "line in docs/PROJECT.md; if that is empty, ask the owner once and record the answer "
          "there.", file=sys.stderr)
    sys.exit(2)
