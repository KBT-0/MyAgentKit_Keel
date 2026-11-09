#!/usr/bin/env python3
"""PreToolUse (every tool): past the session's context band, only the closing actions run.

The band (docs/WORKFLOW.md, "Worker cost", rule 8) only advised, and four field reports saw lead
sessions pass 200k every release (.myagentkit/field-2026-11-09; owner 2026-11-09, PLAN.md item 2:
"worker at 150k: only commit + hand-off; lead at 200k: hands off; the hook enforces"). A worker
(MYAGENTKIT_ROLE=worker, set by spawn_worker.sh, the discriminator every kit hook reads) is held at
yellow, a lead at red: context_size.enforced_at(). The thresholds are context_size.py's, so
`MYAGENTKIT_BAND=yellow,red,ceiling` (thousands, e.g. `80,100,150`) moves them here too. The size is
context_size.scan()'s, resumed from the offset its step file saved (read only; the PostToolUse
band check writes it).

Past the line every call is denied (permissionDecision deny, one line naming the band, the size
and what still runs) except the closing set: Read, Grep, Glob, ToolSearch and SendMessage (reading
and telling the lead close nothing); the diff-reviewer sub-agent (the review a commit needs); a
Bash or PowerShell command whose every part is git add, commit, status, diff or log, a read-only
command (guard_destructive_git.py's INERT list, with no file redirection), mktemp, or one of the
closing scripts in SCRIPTS (the publish, the marker release, the worker listing, the autopilot
report, the switch back to present, review.sh) or the project's gate, scripts/check.sh with any
flags (a green gate is the condition of the commit the band already allows: two measured runs were
denied it at yellow and never committed their green work, RESEARCH_LOG 2026-11-09 stopcut); and Write,
Edit or NotebookEdit of the result file (RESULT-* or QUESTION-*, or the path spawn_worker.sh recorded in .myagentkit/workers/
NAME.result-path, a temporary file beside it included), the hand-off (.myagentkit/handoff-pending,
.myagentkit/**/handoff-*.md, docs/HANDOFF.md), docs/STATE.md, PLAN.md, docs/worktree-notes/*.md,
.myagentkit/autopilot/*.md and a file under the temporary directory (a commit message for
`git commit -F`). ScheduleWakeup and Monitor stay denied: a wakeup goes on in the oversized
context. A sub-agent's own call
(agent_id) is not judged: its context is its own, and a running review is never cut off. A
compaction boundary resets the size, which lifts the band.

While the owner is away (autopilot) the lead's band still denies: the hand-off and the autopilot
report are written and the session idles; reopening a lead is the watchdog's job (PLAN.md item 5), not this hook's.
Silent on any error: a broken transcript must never block work, as in context_size.py.
"""
import itertools
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
READS = {'Read', 'Grep', 'Glob', 'ToolSearch', 'SendMessage'}
WRITES = {'Write', 'Edit', 'NotebookEdit'}
SHELLS = {'Bash', 'PowerShell'}
CLOSING_GIT = {'add', 'commit', 'status', 'diff', 'log'}
# A closing script and the first argument it must have ('' = any): core/docs/HANDOFF.md's steps,
# the autopilot report and the switch back (WORKFLOW.md, autopilot), the review a commit needs.
SCRIPTS = {'codex_worker.py': '--publish', 'master_writer.py': 'release', 'list_workers.sh': '',
           'watch_workers.sh': '--once', 'autopilot_report.py': '', 'working_mode.py': 'present',
           'review.sh': ''}
# The project's gate, by its folder and name (scripts/check.sh), any flags; a test command is work.
GATE = ('scripts', 'check.sh')
# A redirection that writes a file; `2>&1` and `>/dev/null` write none.
WRITES_FILE = re.compile(r'>(?!&\d|\s*/dev/null)')


def size(transcript: Path) -> int:
    import context_size
    try:
        saved = json.loads(transcript.with_suffix('.context-step').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        saved = None
    return context_size.scan(transcript, context_size.resumable(saved))[0]


def recorded_result() -> str:
    """The result path spawn_worker.sh recorded for this worker, '' when none."""
    import context_size
    name = os.environ.get('MYAGENTKIT_SESSION_ID', '').removeprefix('worker-')
    root = Path(os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd())
    for folder in (context_size.main_checkout(root), root):
        try:
            return (folder / f'.myagentkit/workers/{name}.result-path').read_text(encoding='utf-8').strip()
        except (OSError, TypeError, ValueError):
            continue
    return ''


def closing_file(path: str) -> bool:
    parts = PurePosixPath(path.replace('\\', '/')).parts
    name = parts[-1] if parts else ''
    if name.startswith(('RESULT-', 'QUESTION-')) or name == 'PLAN.md' or parts[-2:] in (
            ('docs', 'HANDOFF.md'), ('docs', 'STATE.md'), ('.myagentkit', 'handoff-pending')):
        return True
    if '.myagentkit' in parts[:-1] and re.fullmatch(r'handoff-.*\.md', name):
        return True
    if name.endswith('.md') and parts[-3:-1] in (('docs', 'worktree-notes'), ('.myagentkit', 'autopilot')):
        return True
    try:
        if Path(path).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
            return True  # gettempdir() reads $TMPDIR first
    except (OSError, ValueError):
        pass
    result = recorded_result() if os.environ.get('MYAGENTKIT_ROLE') == 'worker' else ''
    # The publish step's temporary file stands beside the result, its name starting with the result's.
    return bool(result) and PurePosixPath(path.replace('\\', '/')).as_posix().startswith(result.replace('\\', '/'))


def closing_script(words: list) -> bool:
    """`[python3 | py -3 | sh] PATH/SCRIPT ARG ...` where SCRIPT's first argument is the one SCRIPTS names,
    or `[sh | bash] [PATH/]scripts/check.sh ARG ...`, the gate."""
    import guard_destructive_git as g
    name = g.base(words[0])
    if name == 'py' and len(words) > 1 and words[1].startswith('-'):
        words = words[2:]  # the Windows launcher's version flag, spawn_worker.sh's kit_python
    elif g.interpreter(name) or name in ('py', 'sh', 'bash'):
        words = words[1:]
    if words and PurePosixPath(words[0].replace('\\', '/')).parts[-2:] == GATE:
        return True
    if not words or g.base(words[0]) not in SCRIPTS:
        return False
    want = SCRIPTS[g.base(words[0])]
    return not want or words[1:2] == [want]


def closing_command(command: str, depth: int = 0) -> bool:
    """Every part of the line is a closing git verb, a read-only command or the result's publish."""
    import guard_destructive_git as g
    text, bodies = g.strip_heredocs(command)
    if depth > 3 or any(shell for shell, _ in bodies):
        return False  # a body a shell runs
    for inner in g.substitutions(text):
        if not closing_command(inner, depth + 1):
            return False
    flat = text
    while (cut := re.sub(r'\$\([^()]*\)|`[^`]*`', 'x', flat)) != flat:  # innermost first, already judged
        flat = cut
    blank = g.unquoted(flat)
    if blank is None or WRITES_FILE.search(blank):
        return False
    for seg in g.segments(text, strict=True):
        words = list(itertools.dropwhile(lambda w: w in g.KEYWORDS or re.match(r'[A-Za-z_]\w*=', w), seg))
        if not words:
            continue
        name = g.base(words[0])
        if name == 'git':
            git = g.Git(words[1:], {}, [None])
            # -c may name a program git runs (a pager, a diff driver); --output writes a file.
            if git.configs or git.sub not in CLOSING_GIT or any(a.startswith('--out') for a in git.args):
                return False
        elif closing_script(words):
            continue
        elif name not in g.INERT | {'mktemp'}:
            return False
    return True


def closing(tool: str, inp: dict) -> bool:
    if tool in READS:
        return True
    if tool in ('Agent', 'Task'):
        return inp.get('subagent_type') == 'diff-reviewer'
    if tool in WRITES:
        path = inp.get('file_path') or inp.get('notebook_path')
        return isinstance(path, str) and closing_file(path)
    if tool in SHELLS:
        command = inp.get('command')
        if not isinstance(command, str):
            return False
        if tool == 'PowerShell':
            import guard_destructive_git as g
            if '`' in command:
                return False  # PowerShell's escape: the line reads otherwise
            command = g.powershell(command)
        try:
            return closing_command(command)
        except Exception:  # noqa: BLE001 - unreadable as shell: not a closing command
            return False
    return False


def main() -> None:
    data = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    if data.get('agent_id'):
        return
    sys.path.insert(0, str(HERE))
    import context_size
    tool, inp = data.get('tool_name'), data.get('tool_input')
    if tool in READS:
        return
    ctx, line = size(Path(data['transcript_path'])), context_size.enforced_at()
    if ctx < line or closing(str(tool), inp if isinstance(inp, dict) else {}):
        return
    worker = os.environ.get('MYAGENTKIT_ROLE') == 'worker'
    reason = (f'Denied by the context band: {ctx // 1000}k tokens, past the '
              f"{'worker' if worker else 'lead'} {'yellow' if worker else 'red'} line ({line // 1000}k). "
              'Only commit and hand-off run now: git add, commit, status, diff and log; writing the result '
              'file (RESULT-*, QUESTION-*), the hand-off (.myagentkit/handoff-pending, .myagentkit/**/handoff-*.md, '
              'docs/HANDOFF.md), docs/STATE.md, PLAN.md, docs/worktree-notes/*.md, .myagentkit/autopilot/*.md; '
              'the gate (scripts/check.sh), the diff-reviewer and scripts/review.sh; master_writer.py release, '
              'list_workers.sh, '
              'autopilot_report.py, working_mode.py present; Read, Grep, Glob. '
              + ('Commit green work and publish a Kind: handoff result' if worker else
                 'Commit, update docs/STATE.md, write the hand-off and its marker, then stop for /clear')
              + ' (docs/WORKFLOW.md, "Worker cost", rule 8).')
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                             'permissionDecisionReason': reason}}))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001 - see the docstring
        pass
