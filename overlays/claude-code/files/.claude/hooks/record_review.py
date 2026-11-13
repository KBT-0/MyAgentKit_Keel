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
# hooka2: "New", "Open", "Remaining", "Reopened" or "Regression" before it too ("- New High: a.py:3"); hookb:
# also after up to three other words ("- Still open: High", "- One new High"), unless the first is a "no"
# ("No new Critical or High findings.").
LABEL = r"(?:issue|finding|[a-z]?_?\d+|severity|new|open|remaining|reopened|regression|`[^`\n]*`)"  # one way to split a line: no backtracking blow-up
STATE = r"(?:(?!(?:no|not|none|zero|without|nothing)\b)[^\W\d_][\w'-]*[^\w\n`]+){1,3}(?:new|open|remaining|reopened|regression)[^\w\n`]+"
# labricore A5: a bare path:line may lead once ("- src/x.ts:3 — High: ...")
LEAD = re.compile(r"^[^\w\n`]*(?:[\w\\-]*[./][\w./\\-]*:\d+[^\w\n`]+)?(?:%s)?(?:%s[^\w\n`]+)*(?:critical|high)\b(?!-(?:tier|effort|risk)\b)"
                  % (STATE, LABEL), re.I | re.M)
# #345: an earlier round's finding restated as fixed ("- F1 (High), fixed. REPRODUCED.", "H2 (Critical) — resolved")
# is none: the disposition word comes right after the severity, at most after "now", "confirmed" or "verified",
# and ends the finding (hooka2). After it, at most one of (hookb):
#   "in", "by", "since" or "at", then "this diff" (change, patch, commit, round) or one reference, "commit"
#   or "test" before it allowed: a reference holds a digit, one of _ / : ` \, or a dot inside it, so "fixed in
#   theory." and "closed by default" are open;
#   a colon and one clause of evidence naming a path:line ("fixed: the row is kept now (a.py:9).");
# then only punctuation other than "?" and REPRODUCED, VERIFIED or CONFIRMED, each with at most one
# parenthesised command, up to the line's end. A word that says it is not done (but, still, not, only,
# partly, except, fails, drops, ...) anywhere after the disposition keeps it open. A wrapped finding is read
# with its indented lines too. "fixed, but ...", "fixed in part; ...", "closed. <a new defect>", "resolved in
# the wrong order ...", a file "resolved.ts:12", "fixed-width", "not fixed" and "unresolved" still block.
DISPOSITION = re.compile(r"[^\w\n]*(?:(?:now|confirmed|verified)\s+)?(?:fixed|closed|resolved)\b", re.I)
REFERENCE = (r"(?:(?:this|the)\s+(?:diff|change|patch|commit|round)\b"
             r"|(?:(?:commit|test)\s+)?(?=[^\s,;]*?(?:\d|[_/:`\\]|\.\w))[^\s,;]{1,80})")
TAIL = r"(?:[^\w\n?]|\b(?:reproduced|verified|confirmed)\b(?:\s*\([^()\n]{1,300}\))?)*"
FIXED_BY = re.compile(r"(?:\s+(?:in|by|since|at)\s+%s)?%s" % (REFERENCE, TAIL), re.I)
FIXED_AS = re.compile(r":\s+(?P<evidence>[^\n]+?)%s" % TAIL, re.I)
SENTENCE = re.compile(r"[.;!?](?:\s|$)")
PATH_LINE = re.compile(r"\w\.\w+:\d+")
NOT_DONE = re.compile(r"\b(?:but|still|not|no|never|nor|except|only|partly|partial\w*|incomplete\w*|however|yet|"
                      r"though|although|again|unless|while|whereas|regress\w*|reopen\w*|fail\w*|broke\w*|break\w*|"
                      r"drop\w*|lost|lose\w*|wrong\w*|miss\w*|open\w*|new|another|\w+n't|defer\w*|wontfix|later|backlog|"
                      r"critical|high)\b", re.I)
# Continuation lines of a list item: indented, and no item of their own.
WRAPPED = re.compile(r"\n[ \t]+(?![-*+][ \t]|\d+[.)][ \t]|\|)(?=\S)")


def fixed(rest):
    """True when `rest`, what follows a leading Critical or High up to its line's end, restates it as fixed."""
    disposition = DISPOSITION.match(rest)
    if not disposition:
        return False
    after = rest[disposition.end():]
    if NOT_DONE.search(after):
        return False
    if FIXED_BY.fullmatch(after):
        return True
    clause = FIXED_AS.fullmatch(after)
    return bool(clause and not SENTENCE.search(clause.group("evidence")) and PATH_LINE.search(clause.group("evidence")))


def open_finding(text):
    """True when a line of `text` leads with a Critical or High that is not restated as fixed."""
    for lead in LEAD.finditer(text):
        end = text.find("\n", lead.end())
        if not fixed(text[lead.end():] if end < 0 else text[lead.end():end]):
            return True
    return False


def accepted(message):
    """The verdict line comes first (diff-reviewer.md), after a bare "Verdict" heading at most; an Accept
    that lists a Critical or High reads as Reject (REVIEW_GATE.md, "Verdicts and who decides")."""
    lines = [line for line in message.splitlines() if line.strip()]
    if len(lines) > 1 and HEADING.fullmatch(lines[0]):
        lines = ["Verdict: " + lines[1]] + lines[2:]
    if not (lines and VERDICT.match(lines[0])):
        return False
    # Emphasis markup, not an underscore inside a name (test_round).
    text = re.sub(r"\*+|(?<!\w)_+|_+(?!\w)", "", "\n".join(message.splitlines()))
    # Each line as written, and each finding with its wrapped lines (an indented "High:" stays a lead there).
    return not (open_finding(text) or open_finding(WRAPPED.sub(" ", text)))


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
