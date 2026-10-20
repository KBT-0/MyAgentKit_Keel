#!/usr/bin/env python3
"""PreToolUse(Edit|Write|NotebookEdit): refuse an agent's write to a file whose name looks like a secret.

A secret an agent writes passes through its context and its transcript; the owner writes it from
the terminal instead (#297). The names are the review's (`core/scripts/claude_bridge.py`,
`secret_like`): `.env*`, `.dev.vars*`, `credentials*`, `*.pem`, `*.key`, `.npmrc`, `.netrc`, with
the templates `.env.example`, `.env.sample` and `.env.template` allowed. The predicate is copied,
not imported: the hooks use the stdlib alone and must run where `scripts/` is missing;
tests/test_guard_secret_files.py holds the two to one table. Only the basename counts, with a
Windows path's backslashes read as separators.

Left out: a write through the shell (`echo >> .env`, `cp`), a read of a secret file, and a
per-project allow list. Threat model: an agent's ACCIDENT; Claude Code's permissions and sandbox
are the boundary.

A matched path is refused (exit 2). Unreadable input passes with a note (exit 1), and the settings
entry has no `onFailure: block`: a guard that cannot read its input must not refuse every edit, as
guard_root_scan.py (#298, lead decision D1). Exit 2 blocks the call and returns the message to the
agent (Claude Code hook protocol).
"""
import json
import sys

SECRET_TEMPLATES = {".env.example", ".env.sample", ".env.template"}


def secret_like(name: str) -> bool:
    base = name.replace("\\", "/").rpartition("/")[2].lower()
    return (base not in SECRET_TEMPLATES and base.startswith((".env", ".dev.vars", "credentials"))
            or base.endswith((".pem", ".key")) or base in (".npmrc", ".netrc"))


if __name__ == "__main__":
    try:
        call = json.loads(sys.stdin.buffer.read().decode("utf-8")).get("tool_input") or {}
        path = call.get("file_path") or call.get("notebook_path") or ""
        if not isinstance(path, str):
            raise TypeError("the target path is not a string")
    except Exception as exc:  # fails open
        print("guard_secret_files.py could not read the hook input (%s); the call goes on. Report this to "
              "the owner." % exc, file=sys.stderr)
        sys.exit(1)
    if secret_like(path):
        print("BLOCKED: writing `%s` is refused: its name looks like a secret file (.env, .dev.vars, "
              "credentials, *.pem, *.key, .npmrc, .netrc), and a secret an agent writes passes through its "
              "context. Tell the owner what the file needs; the owner edits it from the terminal. A template "
              "(.env.example, .env.sample, .env.template) may be written." % path, file=sys.stderr)
        sys.exit(2)
