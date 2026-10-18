#!/usr/bin/env python3
"""PreToolUse(WebFetch|WebSearch|Bash|PowerShell|Monitor): refuse a web request that carries the owner's e-mail.

Research sub-agents once put the owner's address into User-Agent headers, up to thirteen
requests each (RESEARCH_LOG.md, "Rules from the transcripts"); a third party's logs cannot be
recalled. The written rule (`docs/WORKFLOW.md`, "Web requests carry no personal data") is
advice; a hook runs every time (https://code.claude.com/docs/en/hooks-guide). An API that
wants contact details gets the project's "Web contact" from `docs/PROJECT.md`, never a
person's own address (owner decision 2026-10-15).

The addresses are git's `user.email` (every scope), read in the project ($CLAUDE_PROJECT_DIR)
and in the hook's own folder, so a per-project identity counts wherever the shell last changed
directory (#211), and any listed, comma-separated, in MYAGENTKIT_PRIVATE_EMAILS: the Claude account's address can differ from git's. The request is
URL-decoded until it stops changing and case-folded before the match. A web command that
names the address list or git's `user.email`, or runs what prints an address at run time (`git
log/show/whatchanged` without `--oneline`, the `oneline`/`reference` format or a custom format
(the other built-ins, `--format=fuller` and the like, print addresses), a `%ae`/`%ce` or
`%(authoremail)` placeholder, `git var`, `git config -l/--list/--get-regexp/list/get --regexp`, `env`, `printenv`, PowerShell's `env:` drive) is
refused too: the shell would put it in after this check (#212). If the addresses cannot be read, the request is refused (fail closed).
A command (any tool's `tool_input.command`: Bash, PowerShell, Monitor) counts as a web request
when it names a URL (http, ws) or a web client; Monitor's `ws.url` is read too (#213).
ponytail: a script that reads the address from a file is not seen. Add a client to WEB, or a
reader to SOURCES, when one shows.

Exit 2 blocks the call and returns the message to the agent (Claude Code hook protocol).
"""
import json
import os
import re
import subprocess
import sys
from urllib.parse import unquote

WEB = re.compile(r"(?:https?|wss?)://|\b(curl|wget|gh|Invoke-WebRequest|Invoke-RestMethod|iwr|irm)\b", re.I)
SOURCES = re.compile(
    r"MYAGENTKIT_PRIVATE_EMAILS|user\.email|(?:--format|--pretty)[= ][^|;&)]*%[ac]e"
    r"|%\((?:author|committer|tagger)email"
    # A global option's value may be quoted with a space in it (`-C 'C:/My Work/repo'`).
    r"|\bgit\s+(?:-[Cc]\s+(?:'[^']*'|\"[^\"]*\"|\S+)\s+|-\S+\s+)*"
    r"(?:var\b|config\b[^|;&)]*\s(?:-l|--list|--get-regexp|--regexp|list)\b"
    # Safe formats print no address: --oneline, the built-ins oneline and reference, and a custom
    # format (format:, tformat:, or any text with a % placeholder; %ae/%ce are caught above).
    r"|(?:log|show|whatchanged)\b(?![^|;&)]*(?:--oneline|--(?:format|pretty)="
    r"(?:['\"]?(?:oneline|reference|t?format:)|'[^']*%|\"[^\"]*%|[^\s'\"|;&)]*%))))"
    r"|\bprintenv\b|(?:^|[;&|(]\s*)env\s*(?:$|[|;&)>])|\b(?:Get-ChildItem|gci|ls|dir)\s+env:", re.I)
ADVICE = ("If the API needs contact details, use the \"Web contact\" line in docs/PROJECT.md; if "
          "that is empty, ask the owner once and record the answer there.")


def block(message):
    print("BLOCKED: " + message, file=sys.stderr)
    sys.exit(2)


try:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    call = data.get("tool_input") or {}
    ws = call.get("ws") if isinstance(call.get("ws"), dict) else {}
    shell = isinstance(call.get("command"), str)  # Bash, PowerShell, Monitor: the matcher picks them
    text = " ".join(v for v in (call.get("url"), call.get("query"), call.get("command"), ws.get("url"))
                    if isinstance(v, str))
except Exception as exc:
    block(f"guard_private_email.py could not read the hook input ({exc}). Report this to the owner.")
if shell and not WEB.search(text):
    sys.exit(0)
if shell and SOURCES.search(text):
    block("this web command reads or prints the owner's e-mail address (MYAGENTKIT_PRIVATE_EMAILS, "
          "git's user.email, a commit's author, the environment); the shell would put it into the request. " + ADVICE)

found = ""
try:
    for where in dict.fromkeys([os.environ.get("CLAUDE_PROJECT_DIR") or None, None]):
        read = subprocess.run(["git", "config", "--get-all", "user.email"], capture_output=True, cwd=where,
                              encoding="utf-8", errors="replace", timeout=10)
        if read.returncode not in (0, 1):  # 1: no address configured
            raise RuntimeError(read.stderr.strip() or "exit %d" % read.returncode)
        found += read.stdout + "\n"
except Exception as exc:
    block(f"guard_private_email.py could not read the owner's address from git ({exc}), so it "
          "cannot tell whether this request carries it. Report this to the owner.")
emails = {e.strip().casefold() for e in found.split() + os.environ.get("MYAGENTKIT_PRIVATE_EMAILS", "").split(",")}
for _ in range(10):  # %2540 -> %40 -> @
    decoded = unquote(text)
    if decoded == text:
        break
    text = decoded
text = text.casefold()
if any(e and e in text for e in emails):
    block("this web request carries the owner's e-mail address, which must never reach a third "
          "party. Remove it. " + ADVICE)
