#!/usr/bin/env python3
"""SubagentStart / SubagentHandback / SubagentStop (diff-reviewer): record the paths a diff review saw, for guard_risky_review.py.

The git folder's myagentkit-reviewed file holds {"head": HEAD, "paths": [...], "pending": {agent_id:
[...]}}. A review's start notes the paths changed against HEAD under its agent id; its stop moves
them into "paths", joined with an earlier record for the same HEAD; a reviewer that hands its report
back through the SubagentHandback tool (auto mode) is read there, from the tool's message, since its
stop's last_assistant_message is not the report (Claude Code hooks docs, SubagentStop). A file made
while the reviewer ran is not among them, so the guard asks for it again. A stop with no start note, or whose last
message does not open with an Accept verdict line (Accept, Accept with Manual Checks, or a PASS or
APPROVE some reviewers write) or lists an open Critical or High (one restated as fixed is not open, #345), records nothing: a reviewer that failed or was cut off, and a Reject, whose fix a
fresh review sees before the commit (owner 2026-10-25).
It only records and always exits 0: a SubagentStop hook's exit 2 would keep the reviewer running.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from guard_risky_review import changed, head, note_content, project_root, read_record, record_path  # noqa: E402

# A PASS only after "Verdict" (ctl10: "VERDICT: PASS"): a cut-off "Pass 1: reading the diff" is none.
VERDICT = re.compile(r"\W*(?:verdict\W*)?(?:accept|approve)\b|\W*verdict\W*pass\b", re.I)
HEADING = re.compile(r"\W*verdict\W*", re.I)
# A line that leads with Critical or High, after list, table and emphasis markup and labels such as
# "Issue #1 -", "Finding 1:", "H1 (", "Severity:" or a `path:line`; "High-severity" too, not "High-tier".
LABEL = r"(?:issue|finding|[a-z]?\d+|severity|`[^`\n]*`)"  # one way to split a line: no backtracking blow-up
# labricore A5: a bare path:line may lead once ("- src/x.ts:3 — High: ...")
# #345: an earlier round's finding restated as fixed ("- F1 (High), fixed. REPRODUCED.", "H2 (Critical) — resolved")
# is none: the disposition word comes right after the severity, at most after "now", "confirmed" or
# "verified", and ends there (a stop, a bracket, "in"/"by" a commit or test). "High: fixed offset 4 ...",
# "fixed-width", "not fixed" and "unresolved" still block.
FIXED = r"[^\w\n]*(?:(?:now|confirmed|verified)\s+)?(?:fixed|closed|resolved)(?:\s*(?:$|[.,;:)\]]|[—–]|\s-\s|\s(?:in|by|since|at)\s))"
BLOCKING = re.compile(r"^[^\w\n`]*(?:[\w\\-]*[./][\w./\\-]*:\d+[^\w\n`]+)?(?:%s[^\w\n`]+)*(?:critical|high)\b(?!-(?:tier|effort|risk)\b)(?!%s)"
                      % (LABEL, FIXED), re.I | re.M)


def accepted(message):
    """The verdict line comes first (diff-reviewer.md), after a bare "Verdict" heading at most; an Accept
    that lists a Critical or High reads as Reject (REVIEW_GATE.md, "Verdicts and who decides")."""
    lines = [line for line in message.splitlines() if line.strip()]
    if len(lines) > 1 and HEADING.fullmatch(lines[0]):
        lines = ["Verdict: " + lines[1]] + lines[2:]
    return bool(lines) and bool(VERDICT.match(lines[0])) and not BLOCKING.search(re.sub(r"[*_]", "", message))


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        if data.get("agent_type") != "diff-reviewer":
            return 0
        root = project_root(data)
        record = read_record(root)
        paths, pending = set(record.get("paths", [])), dict(record.get("pending", {}))
        agent = str(data.get("agent_id") or "")
        if data.get("hook_event_name") == "SubagentStart":
            pending[agent] = sorted(changed(root))
        else:
            handback = data.get("hook_event_name") == "PostToolUse"
            if handback or agent in pending:  # a stop after a hand-back finds its note gone
                report = ((data.get("tool_input") or {}).get("message") if handback
                          else data.get("last_assistant_message"))
                note = pending.pop(agent, [])
                if accepted(str(report or "")):
                    paths |= set(note)
                    note_content(root, note)  # a merge of this tree's commits passes elsewhere too
        with open(record_path(root), "w", encoding="utf-8") as f:
            json.dump({"head": head(root), "paths": sorted(paths), "pending": pending}, f)
    except Exception as error:  # a broken record only means the guard asks for the review again
        print("record_review: %s" % error, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
