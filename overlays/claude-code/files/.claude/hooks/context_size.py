#!/usr/bin/env python3
"""UserPromptSubmit: tell the agent when the session's context has grown past the hand-off line.

progress_reminder.py (PostToolUse) runs the same check through `notice()`, so a long autonomous
turn meets the band when it crosses it, not at the owner's next prompt (#138). Both share the
step file, so each step is named once. A large transcript is read from the byte offset the
last check saved (progress_reminder.py's method): a full read of 33 MB took 0.9 s.

Every request re-sends the whole context, and accuracy falls as it grows (`docs/WORKFLOW.md`,
"Worker cost", rule 8: a band, yellow at 200k, red at 300k, ceiling at 400k). The context is
the last API request's input plus cache read plus cache write, read from the transcript; a
compaction boundary resets it until the next request.

Past LINE the hook adds one line to the agent's context, once per STEP: at 200k, 250k, 300k...,
opening with the band the size is in.
The last step it named is kept beside the transcript (`<session>.context-step`, in the
user's own Claude folder, not a shared temporary one), so a retried prompt or one that
reached no request does not repeat it. A compaction boundary arms it again; a smaller
context alone does not. Which of /compact and a hand-off is cheaper depends on what STATE
holds and where the work goes next, which a hook cannot see, so the agent chooses and says
so; after a compaction it can only be a hand-off, since a second summary drifts. Silent on any error: a broken transcript must never block a prompt.

While the owner is away (`.myagentkit/presence` says `away`, written by `working_mode.py
autopilot`; `away()` is the one reader the hooks share), the band line says to update the
hand-off file and keep going instead, since nobody is there to take a recommendation and a
second compaction is no stop then; and each prompt tells the lead how to judge it, since only
an owner message that says or implies the return ends the autopilot (docs/WORKFLOW.md,
"autopilot, the owner-away switch").

While work started inside this session still runs (a background Bash task, an async sub-agent:
started by a tool result's `backgroundTaskId` or `agentId`, ended by its `<task-id>` notification
or a TaskStop), the band line says the hand-off is blocked and names the jobs instead of offering
it (owner, 2026-10-26: finish the work, or wait and tell the owner when the hand-off is ready).
A worker in its own session does not block: the next lead's announcement reaches it, so the
background command that only watches its result (spawn_worker.sh's printed until-loop, a
watch_workers.sh call) is no job here either. The jobs survive a compaction, so the running list
and the labels of the calls still waiting for their result are kept in the step file and carried
across one. A job that died with an ended session gets no notification (a resumed session
appends to the same transcript): the line says a TaskStop clears it, and a job older than a day
is dropped, as the kit's own watch gives up after 24 h. The field shapes were read from real
transcripts of Claude Code 2.1.x on 2026-10-26 (.myagentkit/v014/nohandoff-dispositions.md).
"""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

LINE = 200_000  # yellow: plan the cut
RED = 300_000  # cut at the next clean stop
CEILING = 400_000  # stop now
STEP = 50_000
RECOUNT = 512 * 1024  # re-read small transcripts; larger ones resume at the saved offset
BANDS = ((CEILING, 'ceiling (400k): stop now and secure the work (commit, STATE, handoff) '
                   'without waiting for a clean stop'),
         (RED, 'red (300k): cut at the next clean stop; start no new round'),
         (LINE, 'yellow (200k): plan the cut; start no new round, let the running batch finish, '
                'commit, and keep docs/STATE.md and the handoff current'))
COMPACT = ("/compact keep the open decisions, the binding rules, the changed files, the next step "
           "and the owner's words verbatim")
AUTOPILOT = 'docs/WORKFLOW.md, "autopilot, the owner-away switch"'
TASK_ID = re.compile(r'<task-id>([^<\s]+)</task-id>')
# A background command that only waits for a worker's result: the worker runs in its own session.
WATCH = re.compile(r'codex-worker: ready|watch_workers\.sh|codex_worker\.py\s+--wait')
JOB_LIFE = 24 * 3600  # seconds; a job with no end record this old is taken as dead
# STATE.md's Owner line while away, as scripts/working_mode.py writes it (OWNER_LINE and AWAY there).
AWAY_LINE = re.compile(r'^[^\S\r\n]*(?:[-*+][^\S\r\n]+)?\*\*Owner:\*\*[^\S\r\n]*away \(autopilot since \S+\)', re.M)
# A hook cannot read meaning, so the lead judges (owner, 2026-10-22: what the owner says or
# implies about being back or ending autopilot ends it; nothing else does).
BACK = ("Autopilot is on (.myagentkit/presence or the STATE.md Owner line says away). Judge this prompt: when it is the owner's own "
        "message and it says or implies that the owner is back or wants autopilot ended, run "
        "`python3 scripts/working_mode.py present` (`python` on native Windows) before anything else, tell "
        "the owner to type `/goal clear` (the goal stays active), give the report in two layers, then ask its questions one by one with AskUserQuestion. Any other message "
        "(a farewell, the /goal line, a late instruction, a worker's message, a task notification) does not "
        f'end it: act on it and stay in autopilot ({AUTOPILOT}, Ends).')


def main_checkout(root: Path):
    """The main checkout when ROOT is a linked worktree (its .git is a file), else None; a
    submodule (its common Git folder is no checkout's .git) keeps its own."""
    if not (root / '.git').is_file():
        return None
    try:
        # Made absolute here, not with --path-format (Git 2.31+): relative output is relative to ROOT.
        common = subprocess.run(['git', '-C', str(root), 'rev-parse', '--git-common-dir'],
                                capture_output=True, text=True, encoding='utf-8', timeout=5, check=True).stdout.strip()
        common = (root / common).resolve() if common else None
    except (OSError, subprocess.SubprocessError):
        return None
    return common.parent if common is not None and common.name == '.git' and common.is_dir() else None


def recorded(folder):
    """The first word of FOLDER's .myagentkit/presence ([] when empty), None when it has none."""
    try:
        return (folder / '.myagentkit/presence').read_text(encoding='utf-8').split()[:1]
    except (OSError, ValueError):
        return None


def away() -> bool:
    """The owner switched autopilot on: .myagentkit/presence starts with "away", the project's own
    or, in a linked worktree, the main checkout's, which working_mode.py writes there too (leeway
    L13). Without that record, STATE.md's committed away line counts (L12): a clone or worktree of a night's commit lacks the ignored record, and
    an owner wrongly taken as present is asked questions nobody answers until morning."""
    root = Path(os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd())
    word = recorded(main_checkout(root) or root)
    if word is not None:
        return word == ['away']
    try:
        return AWAY_LINE.search((root / 'docs/STATE.md').read_text(encoding='utf-8')) is not None
    except (OSError, ValueError):  # no file is present
        return False


def band(ctx: int) -> int:
    return -1 if ctx < LINE else (ctx - LINE) // STEP


def band_word(ctx: int) -> str:
    """The watcher's label uses the notice's thresholds and words."""
    return next((text.split()[0] for floor, text in BANDS if ctx >= floor), '')


def context(path: Path, *, require_request: bool = False) -> tuple[int, int]:
    """The last request's context (0 after a boundary), and the compaction count."""
    last, compactions, known, _, _, _ = scan(Path(path))
    if require_request and not known:
        raise ValueError('no request or compaction boundary in transcript')
    return last, compactions


def text(content) -> str:
    """A message's text: a string, or the text blocks of a list."""
    if isinstance(content, str):
        return content
    return ' '.join(b.get('text', '') for b in content if isinstance(b, dict)) if isinstance(content, list) else ''


def when(stamp) -> float:
    """A record's timestamp as seconds, 0 when it has none."""
    try:
        return datetime.fromisoformat(str(stamp).replace('Z', '+00:00')).timestamp()
    except ValueError:
        return 0.0


def scan(path: Path, saved: dict | None = None) -> tuple[int, int, bool, int, dict, dict]:
    """(last, compactions, known, offset, running, pending): from the start, or from a saved
    record boundary. RUNNING maps each job started in this session and not yet ended to
    [label, start seconds]; PENDING maps a Bash or Agent call still without its result to its
    label (None: a watch, no job), so the label survives a scan that saw only the call."""
    with open(path, 'rb') as stream:
        size = stream.seek(0, 2)
        start = (saved or {}).get('offset', 0)
        if start > size or size <= RECOUNT:
            start = 0  # a small or truncated transcript is read again whole
        last, compactions, known = (saved['last'], saved['compactions'], saved['known']) if start else (0, 0, False)
        running, described = (dict(saved['running']), dict(saved['pending'])) if start else ({}, {})
        latest = 0.0
        offset = stream.seek(start)
        for raw in stream:
            if not raw.endswith(b'\n'):
                break  # a partial record is read again on the next call
            offset += len(raw)
            line = raw.decode('utf-8', errors='replace')
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get('type') == 'system' and rec.get('subtype') == 'compact_boundary':
                last = 0
                compactions += 1
                known = True
                continue
            attached = rec.get('attachment')
            if rec.get('type') == 'attachment' and isinstance(attached, dict) and isinstance(attached.get('prompt'), str):
                # A notification that arrives mid-turn is a queued_command attachment, not a user record
                # (Claude Code 2.1.x, 2026-11-02: two ended reviews were still listed as running).
                for ended in TASK_ID.findall(attached['prompt']):
                    running.pop(ended, None)
                continue
            msg = rec.get('message')
            content = msg.get('content') if isinstance(msg, dict) else None
            latest = max(latest, when(rec.get('timestamp')))
            if rec.get('type') == 'user':
                result = rec.get('toolUseResult')
                uses = [b.get('tool_use_id') for b in content if isinstance(b, dict)] if isinstance(content, list) else []
                labels = [described.pop(u) for u in uses if u in described]
                if isinstance(result, dict):
                    job = result.get('backgroundTaskId') or (
                        result.get('agentId') if result.get('status') == 'async_launched' else None)
                    if isinstance(job, str) and job and None not in labels:
                        running[job] = [labels[0] if labels else job, latest]
                for ended in TASK_ID.findall(text(content)):
                    running.pop(ended, None)
                continue
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get('type') == 'tool_use':
                    inp = block.get('input') if isinstance(block.get('input'), dict) else {}
                    if block.get('name') == 'TaskStop':
                        running.pop(inp.get('task_id'), None)
                    # Every Bash call: a foreground one that times out is moved to the background (labricore #329).
                    elif block.get('name') == 'Bash':
                        described[block.get('id')] = None if WATCH.search(str(inp.get('command', ''))) else \
                            str(inp.get('description') or 'Bash')
                    elif block.get('name') == 'Agent':
                        described[block.get('id')] = str(inp.get('description') or 'Agent')
            usage = msg.get('usage') if isinstance(msg, dict) else None
            if rec.get('type') != 'assistant' or rec.get('isSidechain') or not isinstance(usage, dict) \
                    or msg.get('model') == '<synthetic>':
                continue
            # The API may send null for a counter it did not use.
            last = sum(usage.get(k) or 0 for k in
                       ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'))
            known = True
    for job in [j for j, (_, began) in running.items() if began and latest - began > JOB_LIFE]:
        del running[job]  # dead with an ended session, or a watch the kit itself gives up on
    return last, compactions, known, offset, running, described


def notice(transcript: Path) -> str:
    """The band line once per step, else ''."""
    state = transcript.with_suffix('.context-step')
    # A competing prompt stays silent. Closing the file releases the lock, even on a kill.
    # Keep the lock file: unlinking it lets overlapping prompts lock different files.
    with open(transcript.with_suffix('.context-lock'), 'a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            saved = json.loads(state.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            saved = None
        resume = saved if (isinstance(saved, dict) and type(saved.get('known')) is bool and isinstance(
            saved.get('running'), dict) and isinstance(saved.get('pending'), dict) and all(
            type(saved.get(key)) is int and saved[key] >= 0 for key in ('offset', 'last', 'compactions'))) else None
        ctx, compactions, known, offset, running, pending = scan(transcript, resume)
        # Before the step became a record the state held only an integer step.
        legacy = type(saved) is int
        try:
            said, previous = (saved, compactions) if legacy else (saved['step'], saved['compactions'])
            # Any other type (null, "0", true) is a missing file: compared, it raised and silenced the hook.
            if type(said) is not int or type(previous) is not int:
                raise TypeError(said, previous)
        except (KeyError, TypeError):
            said, previous = -1, 0
        if previous != compactions:
            said = -1
        now = band(ctx)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=state.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'step': max(now, said), 'compactions': compactions, 'offset': offset, 'last': ctx,
                       'known': known, 'running': running, 'pending': pending}, stream)
        try:
            os.replace(temporary, state)
        finally:
            temporary.unlink(missing_ok=True)
    if now <= said:
        return ''
    if away():
        return (f'Context is {ctx // 1000}k tokens ({band_word(ctx)} band). The owner is away (autopilot): '
                # A worker leaves STATE.md to the lead (docs/HANDOFF.md, leeway L14).
                + ('keep your result file current' if os.environ.get('MYAGENTKIT_ROLE') == 'worker' else
                   'update docs/STATE.md and the hand-off file now')
                + ', then keep going; no band and no compaction, '
                f'the second included, is a stop, and nothing waits for an answer ({AUTOPILOT}; rule 8).')
    if running:
        names = ', '.join(sorted(f'{label} ({job})' for job, (label, _) in running.items()))
        advice = (f'Hand-off blocked: {len(running)} job(s) started in this session still run ({names}). '
                  "In this turn's closing summary say so to the owner and offer two ways: finish the jobs, or wait "
                  'and tell the owner when the hand-off is ready; the hand-off itself waits for them'
                  + (', the hand-off file is written now' if ctx >= CEILING else '')
                  + '. A worker in its own session does not block (docs/HANDOFF.md); a job that died with an '
                  'earlier session is cleared by a TaskStop on the id in brackets'
                  + ('; never a second /compact' if compactions else
                     f'; "{COMPACT}" stays open while the work in flight continues'))
    elif compactions:
        advice = ('The lead session was compacted already, and a summary of a summary drifts: in this '
                  "turn's closing summary, recommend a hand-off (update STATE, write the handoff, "
                  'fresh session) to the owner in one line with this number, never a second /compact; '
                  'a worker follows its own rule: docs/HANDOFF.md')
    else:
        advice = ("In this turn's closing summary, recommend ONE to the owner in one line with this "
                  'number and the reason: /compact when docs/STATE.md and the open operation files '
                  'already hold what matters and the work in flight continues, never bare but as '
                  f'"{COMPACT}"; a hand-off (update STATE, write the handoff, fresh session) when the '
                  'work changes direction, a batch has just closed, or most of the context is detail '
                  'of finished work. Neither is the default')
    return (f'Context is {ctx // 1000}k tokens, ' + next(text for floor, text in BANDS if ctx >= floor)
            + '. Every turn re-sends it, and accuracy falls as it grows. ' + advice
            + ' (docs/WORKFLOW.md, "Worker cost", rule 8).')


def main() -> None:
    data = json.loads(sys.stdin.buffer.read().decode('utf-8'))
    if away() and os.environ.get('MYAGENTKIT_ROLE') != 'worker':
        print(BACK, flush=True)  # before the band, which a competing prompt's lock may silence
    said = notice(Path(data['transcript_path']))
    if said:
        print(said)


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--line']:
            print(LINE)
        elif len(sys.argv) == 3 and sys.argv[1] == '--band':
            print(band_word(int(sys.argv[2])))
        else:
            main()
    except Exception:  # noqa: BLE001 - see the docstring
        pass
