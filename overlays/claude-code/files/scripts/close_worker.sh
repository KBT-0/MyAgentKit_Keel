#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Close finished worker sessions: end each tmux session, then remove its worktree through the
# audited path. The branch is never deleted.
#
# Usage: close_worker.sh [--dry-run] [--finished] NAME [NAME...]
#   --dry-run  says what it would do, runs the removal's dry run, and changes nothing
#   --finished leaves a worker whose session still runs, unless its result is Kind: completed
#
# The lead runs it once it decides a worker session is finished: no next task fits what the
# session holds, or the session has been idle past the cache lifetime (docs/WORKFLOW.md,
# "Worker cost"). Left to the owner, finished sessions sat idle for hours and 39 worktrees
# piled up; left to the lead, worker tabs stayed open for hours after their merge, so the
# post-merge hook (core/.githooks/post-merge) now runs it, with --finished, for every kit worker
# whose branch tip a merge merged, and for one an earlier merge left running (its
# .myagentkit/workers/NAME.merged-running, written here, #195). For each NAME, in order, each step on its own line:
#   1. A name outside [A-Za-z0-9_-], a control character included, or one starting with `-`,
#      is refused before any tmux call; the next name still runs. So is a worker whose worktree
#      a gate (check.sh, by its lock) or a git operation (index.lock) is running in: the session
#      is not ended, since that would orphan the run.
#   2. `tmux kill-session -t =NAME`; the terminal tab attached to it closes by itself. The
#      processes below the session's panes, listed just before (`ps -A -o pid= -o ppid= -o
#      lstart=`), get SIGTERM, and SIGKILL once the wait below is over, each only while its pid
#      still has the start time it was listed with (a reused pid is never signalled): a
#      background tool command outlives the SIGHUP tmux sends, and one once kept a CPU core busy
#      for hours (#298). Only that tree: an
#      orphan whose parent was already gone cannot be told apart, and doctor.sh lists it. A
#      session that does not exist is reported, not an error, when tmux says so (no such session,
#      no server); any other failure of `tmux has-session` (a socket it cannot read) fails the
#      close with tmux's words, as the session may still run. Then it waits, up to 15 s, until
#      `tmux has-session` no longer finds it and, where /proc exists, no process works inside
#      the worktree: the tool inside takes a moment to exit, and the audit would see it. A tmux
#      that still cannot answer at the end of the wait fails the close with its words. The 15 s
#      is a bound, not a measurement (owner's choice), between `docker stop`'s 10 s and
#      Kubernetes' 30 s grace periods; a value too short only costs a second close.
#      Every project shares the default tmux server, so a session named NAME counts as this
#      worker's only when it started (`#{session_path}`, the spawn's -c) in the worker's worktree,
#      or in this checkout outside .claude/worktrees; another checkout's is never ended (#171).
#   3. The worktree's spawn lock (`git worktree lock`, reason `kit worker NAME`, set by
#      spawn_worker.sh and spawn_codex.sh) is lifted, then
#      `clean_worktrees.sh --apply --only=NAME --no-quiet`: the post-merge hook's audit, every
#      proof, for .claude/worktrees/NAME alone, without the quiet period: that margin stands in
#      for "no worker is still in it", and here the lead has just ended the session and decided
#      the work is finished (the hook never lifts it). Under --finished it is lifted only on a
#      positive end, a session this close ended or a Kind: completed result; a close that ended
#      nothing keeps it, for a worker neither scan can see (#194). No --assume-idle: a process still inside
#      keeps the worktree, as does anything else the audit cannot prove; the hook after a later
#      merge, or this script again, removes it then.
#   4. The branch worktree-NAME is never deleted; the line says how to delete merged branches.
#      `git gc` keeps everything under refs/* (git-gc(1)), so the branch holds every commit
#      the worker made; a merge done on a detached main and undone left them on no other ref
#      (RESEARCH_LOG 2026-10-03).
# A Claude Code background session (spawn_worker.sh recorded .myagentkit/workers/NAME.host as
# bg, on every host) takes step 2 by its id, NAME.id, never by its name: names are not unique
# (docs/research/worker-orchestration-spike.md, 6). Its row in `claude agents --json --all`
# (list_workers.sh --row, which also reads NAME.id) must have started in the worker's folder
# (#171); with no NAME.id, the one row of the name started there is it, and two are refused. A
# live session (a pid, or working or blocked) gets `claude stop ID` and a wait of up to 15 s
# until its row shows neither, then `claude rm ID`, which drops only the row and keeps a
# lead-made worktree (spike, 5): the audit in step 3 stays the one path that removes it. A row
# already gone is nothing to end; a list that cannot be read, or a session its stop leaves
# running, fails the close with the worktree untouched. `claude daemon stop` is never run: it
# ends every background session, the owner's too. After a removal NAME.id and NAME.host go too.
# A worker spawned on the other host (native Windows or WSL, whose session lists are disjoint;
# list_workers.sh tells by NAME.result-path) is refused: a row missing here proves nothing.
# Native Windows has no tmux: step 2 ends the Claude Code session named NAME instead, the
# claude.exe whose command line holds `-n NAME` and whose process id spawn_worker.sh recorded in
# .myagentkit/workers/NAME.pid (names are machine-wide there: another checkout's session of the
# name is never ended, #171; one running with no record is reported and nothing is done, unless
# the name has no NAME.result-path either: then it is no Claude worker of this checkout),
# with `taskkill /T /F` (its tree), and waits up
# to 15 s until no such process is left; its Windows Terminal tab closes by itself, because the
# tab's command ends with `exit 0` (spawn_worker.sh). A lister that cannot answer fails the
# close with its words, as the session may still run. A Codex worker (spawn_codex.sh) is a
# codex.exe whose command line names its folder with -C instead: one running in the worker's
# own worktree is ended the same way (taskkill /T /F, a 15 s wait), and the line names its
# session id (`codex resume ID` still opens the conversation); its wrapper then ends and so does
# its tab (owner 2026-10-16: a close that refused here left Codex tabs open for hours). A
# worker spawned without --worktree shares this checkout's folder, where any Codex session
# matches: nothing is done for that name; the lead quits it in its tab and closes again. Steps 1, 3 and 4
# are the same. On every host a Codex worker whose decision file (the path NAME.question
# records, else QUESTION-NAME.md at its top) still exists is refused before step 2: the lead
# answers it with spawn_codex.sh --resume, or deletes it to abandon the worker. Before step 3 an
# untracked RESULT-NAME.md at the worker's top moves to .myagentkit/workers/NAME.result.md:
# the lead read it and committed the files it lists (the numbered, never-overwritten archive is
# a kit design, owner decision 2026-10-12; a move is refused rather than retried by name
# because Windows renames race: MoveFile check-then-rename, sharing violations). An earlier report there stays, a
# byte-identical one from another run too, and this one takes the number above the highest
# there (NAME.result-2.md, -3, ...), so a newer report never has a lower number; a worktree the
# audit keeps gets its result back. Only a retry of an interrupted older move, whose source is
# still that archive's object, reuses the archive. Every non-collision move failure keeps the
# worktree without the audit. NAME.report-move records the move before consumption; a move
# refused before the report left its path (a Windows sharing violation, the refusals below)
# clears it (owner decision); any other failure, a killed helper included, keeps it, blocking
# later closes until the lead recovers the report and removes that marker.
# The helper prints the .report-move-* folder of a report it could not restore. Where neither
# an exclusive rename nor a hard link works, the move refuses and the report stays (owner
# decision). After a removal (or with no worktree), the Codex records NAME.session, NAME.exit,
# NAME.live and NAME.question go too, spawn_worker.sh's NAME.result-path, NAME.pid and
# NAME.hooks-ignore-spawned, a bg worker's NAME.id, NAME.host and NAME.supervisor.log, and
# NAME.merged-running (also gone once the worktree is unlocked);
# a kept worktree keeps them.
# Exit 0 when every named session is gone and every named worktree was removed or did not
# exist; 1 otherwise, with the first reason on the last line: a nonzero exit of
# clean_worktrees.sh is one whatever its summary says (after a removal, an outcome line its log
# could not take); 2 on a usage error. A dry run exits 1 only for a refused name, a waiting
# decision, a Codex session running in this checkout, an unfinished report move (NAME.report-move), a tmux or
# lister that could not answer, or a removal that could not run.
set -u

# Every line of this script is printed with its control bytes as `?` (a name is an argument).
say() { { printf 'close_worker: %s' "$1" | LC_ALL=C tr '\001-\037\177' '?'; echo; }; }
first=""
# failed: this name's close failed; its Codex session records are then kept (a resume handle).
fail() { say "$1"; [ -n "$first" ] || first=$1; failed=1; }
# Print the archive actually used; 2 is a collision, 3 a refusal before the source was
# consumed (it is untouched), 1 any other failure, with
# only its errno and text on stderr (a path can hold control bytes), after the private path of
# a report it consumed and could not publish or put back, its control bytes as `?`. Never fall
# back to a free-name check followed by an overwriting rename.
move_report() {
  $kit_python -I -c 'import ctypes, errno, os, re, sys, tempfile
source, target = sys.argv[1:]
consumed = False  # the source left its path: from here a failure needs the lead to recover it
unsupported = (errno.EINVAL, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP)

def archived(source, target):
    # An older link+unlink may have stopped after publication, the source still being that
    # archive. Reuse it rather than claim the next number on a retry. Only the same object is
    # this report: separate runs never share an archive, byte-identical ones included (owner
    # decision). Names are compared within the folder, as Git Bash passes C:/ paths that the
    # listing joins with a backslash; a candidate that vanished or cannot be read is not this.
    folder, name = os.path.split(target)
    match = re.fullmatch(r"(.*\.result)(?:-[1-9][0-9]*)?\.md", name)
    if not match:
        return None
    info = os.lstat(source)
    try:
        entries = sorted(os.listdir(folder or "."))
    except OSError:
        return None  # no reuse evidence; exclusive publication can still succeed
    for entry in entries:
        if re.fullmatch(re.escape(match[1]) + r"(?:-[1-9][0-9]*)?\.md", entry):
            path = target[:len(target) - len(name)] + entry
            try:
                if os.path.samestat(info, os.lstat(path)):
                    return path
            except OSError:
                pass
    return None

try:
    duplicate = archived(source, target)
    if os.name == "nt" and not duplicate:
        os.rename(source, target)  # Windows refuses an existing destination atomically.
    else:
        error = errno.ENOSYS  # a duplicate is consumed privately and verified again
        if not duplicate:
            try:
                api = ctypes.CDLL(None, use_errno=True)
                if sys.platform == "darwin":
                    rename = api.renamex_np
                    rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
                    rc = rename(os.fsencode(source), os.fsencode(target), 4)  # RENAME_EXCL
                else:
                    rename = api.renameat2
                    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
                    rc = rename(-100, os.fsencode(source), -100, os.fsencode(target), 1)  # AT_FDCWD, RENAME_NOREPLACE
                error = ctypes.get_errno() if rc else 0
            except AttributeError:
                error = errno.ENOSYS  # no such symbol: glibc before 2.28, an older musl
        if duplicate or error in unsupported:
            if not duplicate and os.path.lexists(target):
                raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST))
            folder = tempfile.mkdtemp(prefix=".report-move-", dir=os.path.dirname(target))
            probe, owned = os.path.join(folder, "probe"), os.path.join(folder, "report")
            try:
                # Test the exclusive link before moving anything. With neither primitive the
                # no-overwrite promise cannot be kept, so the report stays where it was.
                try:
                    os.link(source, probe, follow_symlinks=False)
                except OSError as link_error:
                    if link_error.errno in unsupported + (errno.EPERM,):
                        raise OSError(link_error.errno, "no-overwrite guarantee unavailable: exclusive rename and hard links unsupported")
                    raise
                os.rename(source, owned)  # only this caller can publish into its private directory
                consumed = True
                os.unlink(probe)
                try:
                    duplicate = archived(owned, target)
                    if duplicate:
                        target = duplicate
                    else:
                        os.link(owned, target, follow_symlinks=False)
                    os.unlink(owned)  # never unlink the reusable source pathname
                except OSError:
                    # Restore exclusively; a successor keeps its name and the old report stays
                    # private if restoration is refused. Never remove a published archive.
                    try:
                        os.link(owned, source, follow_symlinks=False)
                        os.unlink(owned)
                    except FileExistsError:
                        raise OSError(errno.EBUSY, "source changed during refused move; owned report preserved")
                    except OSError as restore_error:
                        raise OSError(restore_error.errno, "report restoration failed; owned report preserved")
                    raise
            finally:
                if os.path.lexists(probe):
                    os.unlink(probe)
                try:
                    os.rmdir(folder)
                except OSError:  # a refused transaction retains its owned report, and says where
                    if os.path.lexists(owned):
                        shown = re.sub(rb"[\x01-\x1f\x7f]", b"?", os.fsencode(owned))
                        sys.stderr.buffer.write(b"owned report preserved at " + shown + b"\n")
        elif error:
            raise OSError(error, os.strerror(error))
    consumed = True  # published by one exclusive rename or link
    sys.stdout.buffer.write(os.fsencode(target) + b"\n")
except FileExistsError:
    sys.exit(2)
except OSError as error:
    sys.stderr.write("[Errno %s] %s\n" % (error.errno, error.strerror))
    sys.exit(1 if consumed else 3)' "$1" "$2"
}
# A persistent per-worker marker precedes every move, including restoration after an audit.
# A killed helper or shell leaves it for the next close. Publication, a collision with the
# source intact and a refusal before consumption (3) clear it (owner decision); a report that
# really entered a .report-move-* folder needs the lead to recover it. 4: published, but the
# marker could not be removed, so only the marker is stale.
move_recorded_report() {
  if ! (set -C; printf 'source: %s\ntarget: %s\n' "$1" "$2" > "$record.report-move"); then
    printf '%s\n' 'could not record the report move; nothing moved' >&2
    return 1
  fi
  move_report "$1" "$2"; status=$?
  case $status in
    0) rm -- "$record.report-move" || return 4 ;;
    2|3) rm -- "$record.report-move" || return 1 ;;
  esac
  return "$status"
}
nl='
'
# Git for Windows' dirname handles both separators, including mixed paths such as D:/p\scripts\x.sh.
case $0 in *'\'*) kit=$(dirname -- "$0") ;; */*) kit=${0%/*} ;; *) kit=. ;; esac
# The physical path of the worktree, or empty; /proc/PID/cwd names physical paths.
top=$(git rev-parse --show-toplevel 2>/dev/null) || top=""
# below PID...: every process under the given ones (their children, theirs, ...), from ps, each as
# PID@START, START its start time with _ for blanks; empty where ps cannot list them (Git for
# Windows' ps has no -o).
below() {
  [ "$#" -gt 0 ] || return 0
  ps -A -o pid= -o ppid= -o lstart= 2>/dev/null | awk -v roots=" $* " '{ kid[NR] = $1; dad[NR] = $2
      $1 = $2 = ""; t = $0; gsub(/^ +| +$/, "", t); gsub(/ +/, "_", t); at[NR] = t }
    END { n = split(roots, r, " "); for (i = 1; i <= n; i++) seen[r[i]] = 1
          do { more = 0
               for (k = 1; k <= NR; k++) if ((dad[k] in seen) && !(kid[k] in seen)) { seen[kid[k]] = 1; out = out " " kid[k] "@" at[k]; more = 1 }
          } while (more)
          print substr(out, 2) }'
}
# same PID@START...: the ones still running as the same process: the pid with the start time it
# had when listed. A pid the system has given to another process since is never signalled. Being
# the same process, it is the one listed in the session's tree, though the session's end gave it
# a new parent.
same() {
  [ "$#" -gt 0 ] || return 0
  ps -A -o pid= -o lstart= 2>/dev/null | awk -v want=" $* " '{ p = $1; $1 = ""; t = $0
      gsub(/^ +| +$/, "", t); gsub(/ +/, "_", t); now[p "@" t] = 1 }
    END { n = split(want, w, " "); for (i = 1; i <= n; i++) if (w[i] in now) printf "%s ", w[i] }'
}
# pids PID@START...: the pids alone.
pids() { for p in "$@"; do printf '%s ' "${p%%@*}"; done; }
# inside DIR: prints one process working in DIR or below and succeeds; Linux /proc only.
inside() {
  [ -n "$1" ] && [ -e /proc/self/cwd ] || return 1
  for d in /proc/[0-9]*; do
    c=$(readlink "$d/cwd" 2>/dev/null) || continue
    case $c in "$1"|"$1"/*) printf '%s' "${d#/proc/}"; return 0 ;; esac
  done
  return 1
}
# has NAME: 0 this worker's session exists, 1 tmux says it or its server does not, or the
# session NAME started in another checkout ($other then says where, #171), 2 tmux could not
# tell (its words in $err): only 1 is proof of absence.
has() {
  other=""
  if err=$(tmux has-session -t "=$1" 2>&1); then
    # Session names hold no `:` (tmux replaces it), and worker names are [A-Za-z0-9_-].
    p=$(tmux list-sessions -F '#{session_name}:#{session_path}' 2>&1) || { err=$p; return 2; }
    p=$(printf '%s\n' "$p" | sed -n "s/^$1://p")
    # Its own worktree's folder counts even when that folder is gone (wt_dir is then $top).
    [ "$p" = "$wt_dir" ] && return 0
    case $p in "$top/.claude/worktrees/$1") return 0 ;; "$top/.claude/worktrees"|"$top/.claude/worktrees/"*) ;;
      "$top"|"$top/"*) return 0 ;; esac
    other=$p; return 1
  fi
  case $err in
    *"can't find session"*|*"session not found"*|*"no server running"*|*"no sessions"*) return 1 ;;
    *"error connecting to "*"(No such file or directory)"*) return 1 ;;
  esac
  return 2
}
# Native Windows (Git for Windows' sh, MSYS2, Cygwin): no tmux; a worker is a Windows Terminal
# tab running `claude -n NAME` (spawn_worker.sh). sessions NAME prints, on one line, the process
# id of each Claude Code process whose arguments hold `-n NAME`: a claude.exe, or a node.exe
# running Claude Code's cli.js (an npm install of `claude`). The command line Win32_Process
# gives is split as Windows splits it (CommandLineToArgvW's rules), so `-n w1` inside a quoted
# prompt is part of the prompt, never the name: read as words, it closed the wrong worker.
# KIT_PS names another lister (the kit's tests), printing "<pid> <command line>" lines as this
# one does. A command line Windows does not show (another user's process) names nothing. A
# lister that fails prints its words instead and returns 2.
if python3 -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python3
elif python -I -c '' </dev/null >/dev/null 2>&1; then kit_python=python
else kit_python="py -3"; fi   # unquoted at every use
# argv_py: the Python both listers (sessions, codex) start with: split(line) splits a command
# line as Windows does. ponytail: no single quote inside, it is a shell single-quoted string.
argv_py='if 1:
    import ntpath, sys
    def split(line):
        # CommandLineToArgvW: 2n backslashes and a quote are n and a toggle, 2n+1 are n and a
        # literal quote, "" inside quotes is a quote; any other backslash is itself.
        args, cur, have, quoted, i = [], [], False, False, 0
        while i < len(line):
            c = line[i]
            if c == "\\":
                n = len(line[i:]) - len(line[i:].lstrip("\\"))
                i += n
                if line[i:i + 1] == "\"":
                    cur.append("\\" * (n // 2))
                    if n % 2:
                        cur.append("\"")
                        i += 1
                else:
                    cur.append("\\" * n)
                have = True
            elif c == "\"":
                if quoted and line[i + 1:i + 2] == "\"":
                    cur.append("\"")
                    i += 1
                else:
                    quoted = not quoted
                have, i = True, i + 1
            elif c in " \t" and not quoted:
                if have:
                    args.append("".join(cur))
                cur, have, i = [], False, i + 1
            else:
                cur.append(c)
                have, i = True, i + 1
        if have:
            args.append("".join(cur))
        return args
'
sessions() {
  out=$(${KIT_PS:-powershell.exe -NoProfile -NonInteractive -Command} \
    "Get-CimInstance Win32_Process -Filter \"Name='claude.exe' or Name='node.exe'\" | ForEach-Object { \"\$(\$_.ProcessId) \$(\$_.CommandLine)\" }" \
    2>&1) || { printf '%s' "$out"; return 2; }
  printf '%s\n' "$out" | $kit_python -I -c "$argv_py"'
    pids = []
    for line in sys.stdin.read().replace("\r", "").split("\n"):
        pid, _, command = line.strip().partition(" ")
        argv = split(command)
        if not pid.isdigit() or not argv:
            continue
        exe = ntpath.basename(argv[0]).lower()
        if exe == "claude.exe" or exe == "claude":
            rest = argv[1:]
        elif exe in ("node.exe", "node") and len(argv) > 1 and \
                argv[1].replace("\\", "/").lower().split("/")[-3:] == ["@anthropic-ai", "claude-code", "cli.js"]:
            rest = argv[2:]
        else:
            continue
        if any(a in ("-n", "--name") and b == sys.argv[1] for a, b in zip(rest, rest[1:])):
            pids.append(pid)
    sys.stdout.write(" ".join(pids))' "$1"
}
# mine NAME: of the sessions named NAME, the ones spawn_worker.sh started for this checkout (the
# process ids in NAME.pid): a name is machine-wide on Windows, and another project's worker of
# the same name was ended (#171). 2: the lister failed (its words); 3: sessions of the name run
# and no record says whose (their ids). A name with neither NAME.pid nor NAME.result-path (both
# written by spawn_worker.sh) is no Claude worker of this checkout, a Codex worker say: none.
mine() {
  all=$(sessions "$1") || { printf '%s' "$all"; return 2; }
  [ -n "$all" ] || return 0
  [ -e "$top/.myagentkit/workers/$1.pid" ] || [ -e "$top/.myagentkit/workers/$1.result-path" ] || return 0
  ids=$(cat -- "$top/.myagentkit/workers/$1.pid" 2>/dev/null) || { printf '%s' "$all"; return 3; }
  own=""
  for p in $all; do case " $(printf '%s ' $ids)" in *" $p "*) own="$own${own:+ }$p" ;; esac; done
  printf '%s' "$own"
}
case $(uname -s 2>/dev/null) in MINGW*|MSYS*|CYGWIN*) windows=1 ;; *) windows="" ;; esac
# codex DIR: the process ids of the codex.exe programs whose -C (or --cd) argument is DIR, the
# command line split as sessions splits it: `-C DIR` inside another session's quoted prompt
# is that prompt (Codex review: a text match taskkilled the lead). A worker without --worktree
# shares this checkout's folder, so any Codex session there holds the close of such a name.
codex() {
  out=$(${KIT_PS:-powershell.exe -NoProfile -NonInteractive -Command} \
    "Get-CimInstance Win32_Process -Filter \"Name='codex.exe'\" | ForEach-Object { \"\$(\$_.ProcessId) \$(\$_.CommandLine)\" }" \
    2>&1) || { printf '%s' "$out"; return 2; }
  folder=$(cygpath -w "$1") || { printf '%s' "cygpath cannot convert $1"; return 2; }
  printf '%s\n' "$out" | $kit_python -I -c "$argv_py"'
    norm = lambda p: ntpath.normcase(ntpath.normpath(p))
    pids = []
    for line in sys.stdin.read().replace("\r", "").split("\n"):
        pid, _, command = line.strip().partition(" ")
        argv = split(command)
        if pid.isdigit() and any(a in ("-C", "--cd") and norm(b) == norm(sys.argv[1])
                                 for a, b in zip(argv[1:], argv[2:])):
            pids.append(pid)
    sys.stdout.write(" ".join(pids))' "$folder"
}
# busy DIR: prints what runs in the checkout at DIR and succeeds while a gate or a git
# operation runs there, or while that cannot be checked. Ending the session then orphans it: on
# Windows a killed worker's check.sh ran on without its caller and raced the lead's next gate
# in the same worktree. The gate holds check.lock in the checkout's git directory for its whole
# run (check.sh): a lock this cannot take is held. git holds index.lock while it writes the
# index, a commit included. A check that fails is not proof of a free checkout: it refuses too,
# as does a checkout that cannot be named (no repository here). ponytail: a commit waiting in
# its editor or in a hook holds no index.lock; workers commit with -m, and the kit's commit hook
# is the gate, which holds check.lock. ponytail: the checkout is the one this runs in (the
# lead's), as the lead runs it; run from another repository, it checks that one.
busy() {
  [ -n "$1" ] && [ -d "$1" ] ||
    { printf '%s' "the worker's checkout cannot be established here (no git repository), so whether a gate or a commit runs in it is unknown"; return 0; }
  for f in index.lock check.lock; do
    p=$(git -C "$1" rev-parse --path-format=absolute --git-path "$f" 2>/dev/null) ||
      { printf '%s' "git cannot name the $f of $1, so whether a gate or a commit runs there is unknown"; return 0; }
    [ -e "$p" ] || continue
    if [ "$f" = index.lock ]; then printf '%s' "a git operation holds $p"; return 0; fi
    [ -z "$windows" ] || p=$(cygpath -m "$p")
    $kit_python -I -c 'if 1:
    import os, sys
    try:
        if os.name == "nt":
            open(sys.argv[1], "r+").close()   # refused while a gate holds it: no write sharing
        else:
            import fcntl
            with open(sys.argv[1], "a") as f:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, PermissionError):
        sys.exit(0)
    except OSError as e:
        sys.stderr.write(str(e))
        sys.exit(2)
    sys.exit(1)' "$p" 2>/dev/null
    case $? in
      0) printf '%s' "a gate (check.sh) holds $p"; return 0 ;;
      1) ;;
      *) printf '%s' "the lock $p could not be checked, so whether a gate runs there is unknown"; return 0 ;;
    esac
  done
  return 1
}
# background NAME: whether NAME is a Claude Code background session (NAME.host bg).
background() { [ "$(cat -- "$top/.myagentkit/workers/$1.host" 2>/dev/null)" = bg ]; }
# agent NAME: reads its row (list_workers.sh --row) into bstate bwait bpid bhere bid bcwd; fails
# with the lister's words in $row when the sessions cannot be listed.
agent() {
  # The row is the lister's stdout; its words go to stderr, and only a failure keeps them.
  rowf=$(mktemp) || { row="cannot make a temporary file"; return 1; }
  if row=$(sh "$kit/list_workers.sh" --row "$1" 2>"$rowf"); then rm -f -- "$rowf"
  else row=$(cat -- "$rowf"); rm -f -- "$rowf"; return 1; fi
  IFS='	' read -r bstate bwait bpid bhere bid bcwd <<EOF
$row
EOF
}
# agent_live: whether that row's session runs: a process, or a turn working or blocked.
agent_live() {
  case $bstate in absent|ambiguous) return 1 ;; working|blocked) return 0 ;; esac
  [ "${bpid:--}" != - ]
}
# live NAME DIR: succeeds, printing what runs, while a session of the worker runs in DIR or
# under NAME, or while that cannot be told.
live() {
  if background "$1"; then
    agent "$1" || { printf '%s' "its background sessions cannot be listed ($row)"; return 0; }
    [ "$bstate" != elsewhere ] || { printf '%s' "its background session was started on $bwait, whose session list this host cannot see"; return 0; }
    [ "$bhere" = y ] && agent_live || return 1
    printf '%s' "its background session $bid still runs ($bstate)"; return 0
  fi
  if [ -n "$windows" ]; then
    if [ "$2" != "$top" ]; then
      p=$(codex "$2") || { printf '%s' "its Codex processes cannot be listed ($p)"; return 0; }
      [ -z "$p" ] || { printf '%s' "its Codex session still runs (process $p)"; return 0; }
    fi
    p=$(mine "$1"); case $? in
      2) printf '%s' "its Claude Code sessions cannot be listed ($p)"; return 0 ;;
      3) printf '%s' "a session named $1 runs (process $p) and no record says whose"; return 0 ;;
    esac
    [ -z "$p" ] || { printf '%s' "its session still runs (process $p)"; return 0; }
    return 1
  fi
  command -v tmux >/dev/null 2>&1 || return 1
  has "$1"; case $? in 1) return 1 ;; 0) printf '%s' "its session still runs (tmux session $1)" ;;
    *) printf '%s' "tmux cannot say whether its session runs ($err)" ;; esac
}
# completed DIR NAME: the worker's result is a published Kind: completed result, read by
# codex_worker.py's rules (beside this script): the path spawn_worker.sh recorded in
# NAME.result-path, else RESULT-NAME.md at DIR, the default of both spawns. ponytail: a Codex
# worker given another --result is told finished only by its ended session (its supervisor
# ends it on that result anyway). Each spawn, a resume too, rewrites NAME.result-path
# (spawn_worker.sh) or NAME.session (spawn_codex.sh): only a result published since that write
# is this run's (a resumed worker keeps its last one; #170: a Codex worker's counted).
completed() {
  rec=$top/.myagentkit/workers/$2.result-path
  r=$(cat -- "$rec" 2>/dev/null) && [ -n "$r" ] ||
    { r=$1/RESULT-$2.md; rec=$top/.myagentkit/workers/$2.session; [ -f "$rec" ] || rec=$r; }
  k=$kit
  [ -f "$r" ] && [ -f "$k/codex_worker.py" ] || return 1
  [ -z "$windows" ] || { r=$(cygpath -m "$r") && rec=$(cygpath -m "$rec") && k=$(cygpath -m "$k"); } || return 1
  $kit_python -I -c 'import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import codex_worker
since = 0 if sys.argv[3] == sys.argv[2] else Path(sys.argv[3]).stat().st_mtime
sys.exit(codex_worker.result_kind(Path(sys.argv[2]), since)[0] != "DONE")' "$k" "$r" "$rec" 2>/dev/null
}
dry=""; finished=""
while :; do
  case ${1-} in --dry-run) dry=1; shift ;; --finished) finished=1; shift ;; *) break ;; esac
done
[ $# -ge 1 ] || { sed -n '6,8p' "$0"; exit 2; }

for name; do
  failed=""
  case $name in
    ''|-*|*[!ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-]*)
      fail "refused the name '$name' (a control character shows as ?): a worker name is letters, digits, - and _, not starting with -; nothing done for it"
      continue ;;
  esac
  # The worker's checkout: its worktree, or, for one spawned without --worktree, this one.
  # Checked here, and again just before the session is ended, so a run that started while the
  # sessions were listed is seen too. ponytail: a run started in the moment between that last
  # check and the kill is not seen; a lock shared with spawn and the gate would close that gap.
  wt_dir=$top; [ -z "$top" ] || [ ! -d "$top/.claude/worktrees/$name" ] || wt_dir=$top/.claude/worktrees/$name
  refuse() { fail "$name: $why; ending the session now would leave it running without its caller, so nothing is done for $name: wait until it ends, then close again"; }
  if why=$(busy "$wt_dir"); then refuse; continue; fi
  # --finished (the post-merge hook): a merge proves its branch merged, not its session done.
  if [ -n "$finished" ] && why=$(live "$name" "$wt_dir") && ! completed "$wt_dir" "$name"; then
    # A later merge closes it once it has finished: its branch is no candidate again (#195).
    [ -n "$dry" ] || { mkdir -p -- "$top/.myagentkit/workers" && : > "$top/.myagentkit/workers/$name.merged-running"; } 2>/dev/null
    say "$name: left as it is: $why, and its result is no Kind: completed result; a merge ends only a finished worker, so nothing is done for $name; a later merge closes it once it has finished"
    continue
  fi
  # The quiet period stands in for "no worker is still in it". It is lifted only on a positive
  # end: a session this close ended, the lead's own close, or a Kind: completed result. Under
  # --finished a worker neither scan can see (another user's, an elevated one) was found by
  # nothing and ended by nothing (#194).
  noquiet=--no-quiet; [ -z "$finished" ] || completed "$wt_dir" "$name" || noquiet=""
  record=$top/.myagentkit/workers/$name
  if [ -e "$record.report-move" ] || [ -L "$record.report-move" ]; then
    fail "$name: unfinished report move recorded in $record.report-move; the session is not ended, the audit will not run and the worktree and session records are kept"
    cat -- "$record.report-move" 2>/dev/null | while IFS= read -r line || [ -n "$line" ]; do say "$name: recorded $line"; done
    say "$name: recover the original report to its recorded source or target, checking .report-move-* folders beside both paths, then remove $record.report-move and close again"
    continue
  fi
  # An unanswered Codex decision: its session record is the only way to answer it, and a fresh
  # spawn of the name is refused while the question exists, so a close would strand both.
  ask=$(cat "$record.question" 2>/dev/null) || ask=$wt_dir/QUESTION-$name.md
  # An empty record is a launch interrupted after the session id: where its decision lives is unknown.
  if [ -z "$ask" ]; then
    fail "$name: its decision record $record.question is empty, so a question it stopped on cannot be found; write the decision file's path into it (or delete it if none waits), then close again; nothing is done for $name"
    continue
  fi
  if [ -e "$ask" ]; then
    fail "$name: a decision waits for its answer in $ask; answer it (spawn_codex.sh --resume), or delete it to abandon the worker, then close again; nothing is done for $name"
    continue
  fi
  # A bg worker keeps its full sessionId in NAME.session too, and is no Codex worker.
  if [ -n "$windows" ] && ! background "$name" && { [ -e "$record.session" ] || [ "$wt_dir" != "$top" ]; }; then
    if ! pids=$(codex "$wt_dir"); then
      fail "$name: could not list the Codex processes, so its Codex session may still run: $pids; nothing is done for $name"
      continue
    elif [ -n "$pids" ] && [ "$wt_dir" = "$top" ]; then
      # No worktree of its own: any Codex session in this checkout matches, maybe not this worker's.
      fail "$name: a Codex session still runs in $wt_dir (process $pids); its session record and worktree are kept: quit it in its tab (/quit), then close again"
      continue
    elif [ -n "$pids" ]; then
      sid=$(cat "$record.session" 2>/dev/null) || sid=""
      resume=""; [ -z "$sid" ] || resume="; its conversation stays resumable: codex resume $sid"
      if [ -n "$dry" ]; then
        say "$name: dry run: would end the Codex session in $wt_dir (process $pids, taskkill /T /F) and wait up to 15 s for it; while it runs, the audit below keeps its worktree"; noquiet=--no-quiet
      elif why=$(busy "$wt_dir"); then
        refuse; continue
      else
        # Its wrapper (codex_worker.py) sees the session end, records why and returns; the tab's
        # script then ends with `exit 0`, on which Windows Terminal closes the tab.
        for pid in $pids; do MSYS_NO_PATHCONV=1 taskkill /PID "$pid" /T /F >/dev/null 2>&1; done
        # 15 s by the clock: each lister call takes about 0.8 s, and 15 rounds took 28-29 s (#242).
        end=$(( $(date +%s) + 15 ))
        while left=$(codex "$wt_dir"); st=$?; [ "$st" -eq 0 ] && [ -n "$left" ] && [ "$(date +%s)" -lt "$end" ]; do sleep 1; done
        if [ "$st" -ne 0 ]; then
          fail "$name: could not establish that the Codex session ended: $left; its worktree is not touched"
          continue
        elif [ -n "$left" ]; then
          fail "$name: the Codex session still runs after taskkill (process $left); its session record and worktree are kept"
          continue
        fi
        say "$name: Codex session ended (process $pids$resume); its Windows Terminal tab closes by itself"; noquiet=--no-quiet
      fi
    fi
  fi

  if background "$name"; then
    if ! agent "$name"; then
      fail "$name: could not list the background sessions, so $name may still run: $row; its worktree is not touched"
      continue
    elif [ "$bstate" = elsewhere ]; then
      fail "$name: its background session was started on $bwait, whose session list this host cannot see: close it there; nothing is done for $name"
      continue
    elif [ "$bstate" = absent ]; then
      id=$(cat -- "$record.id" 2>/dev/null) || id=""
      say "$name: no background session ${id:-named $name} is listed (claude agents --all); nothing to end"
    elif [ "$bstate" = ambiguous ]; then
      fail "$name: no $record.id, and several background sessions named $name run in its folder ($bwait), so which is this worker is unknown; stop the right one by its id (claude stop ID), then close again; nothing is done for $name"
      continue
    elif [ "$bhere" != y ]; then
      fail "$name: background session $bid runs in $bcwd, not in this worker's folder; another checkout's session is never stopped here; nothing is done for $name"
      continue
    elif [ -n "$dry" ]; then
      say "$name: dry run: would stop its background session $bid (claude stop) and remove its row (claude rm), waiting up to 15 s for it; while it runs, the audit below keeps its worktree"; noquiet=--no-quiet
    elif why=$(busy "$wt_dir"); then
      refuse; continue
    else
      if agent_live; then
        claude stop "$bid" >/dev/null 2>&1
        # 15 s by the clock, as on the Windows path: one listing takes about 0.8 s.
        end=$(( $(date +%s) + 15 ))
        while agent "$name" && agent_live && [ "$(date +%s)" -lt "$end" ]; do sleep 1; done
        if ! agent "$name"; then
          fail "$name: could not establish that background session $bid ended: $row; its worktree is not touched"
          continue
        elif agent_live; then
          fail "$name: background session $bid still runs after claude stop; its worktree is not touched"
          continue
        fi
      fi
      if out=$(claude rm "$bid" 2>&1); then
        say "$name: background session $bid stopped and removed (claude stop, claude rm); its worktree stays for the audit below"
      else
        fail "$name: background session $bid ended, but claude rm failed: $out"
      fi
      noquiet=--no-quiet
    fi
  elif [ -n "$windows" ]; then
    pids=$(mine "$name"); st=$?
    if [ "$st" -eq 2 ]; then
      fail "$name: could not list the Claude Code sessions, so $name may still run: $pids; its worktree is not touched"
      continue
    elif [ "$st" -eq 3 ]; then
      fail "$name: a Claude Code session named $name runs (process $pids), but no $record.pid says this checkout started it, and another checkout's is never ended; if it is this worker, quit it in its tab, then close again; its worktree is not touched"
      continue
    elif [ -z "$pids" ]; then
      say "$name: no Claude Code session this checkout started as $name runs; nothing to end"
    elif [ -n "$dry" ]; then
      say "$name: dry run: would end the Claude Code session $name (process $pids, taskkill /T /F) and wait up to 15 s for it; while it runs, the audit below keeps its worktree"; noquiet=--no-quiet
    elif why=$(busy "$wt_dir"); then
      refuse; continue
    else
      for pid in $pids; do MSYS_NO_PATHCONV=1 taskkill /PID "$pid" /T /F >/dev/null 2>&1; done
      end=$(( $(date +%s) + 15 ))
      while left=$(mine "$name"); st=$?; [ "$st" -eq 0 ] && [ -n "$left" ] && [ "$(date +%s)" -lt "$end" ]; do sleep 1; done
      if [ "$st" -ne 0 ]; then
        fail "$name: could not establish that the session ended: $left; its worktree is not touched"
        continue
      elif [ -n "$left" ]; then
        # Not audited: a session still running is the one thing the close exists to rule out.
        fail "$name: the Claude Code session still runs after taskkill (process $left); its worktree is not touched"
        continue
      else
        say "$name: Claude Code session ended (process $pids); its Windows Terminal tab closes by itself"; noquiet=--no-quiet
      fi
    fi
  elif ! command -v tmux >/dev/null 2>&1; then
    say "$name: no tmux session (tmux is not installed); nothing to end"
  elif has "$name"; st=$?; [ "$st" -eq 1 ]; then
    # Built outside "${other:+...}": shellcheck cannot parse a single quote there.
    [ -z "$other" ] || other=" started in this checkout (the one in $other is another checkout's, never ended here)"
    say "$name: no tmux session named $name$other; nothing to end"
  elif [ "$st" -eq 2 ]; then
    fail "$name: tmux could not say whether session $name exists, so it may still run: $err"
  elif [ -n "$dry" ]; then
    say "$name: dry run: would end tmux session $name (tmux kill-session -t =$name) and every process its session started, and wait up to 15 s for it; while it runs, the audit below keeps its worktree"; noquiet=--no-quiet
  elif why=$(busy "$wt_dir"); then
    refuse; continue
  elif panes=$(tmux list-panes -s -t "=$name" -F '#{pane_pid}' 2>/dev/null) || :
       # shellcheck disable=SC2086 # one pid per word
       tree=$(below $panes); tmux kill-session -t "=$name" 2>/dev/null; then
    say "$name: tmux session ended; the terminal tab attached to it closes by itself"; noquiet=--no-quiet
    # shellcheck disable=SC2086 # one pid per word, here and below
    left=$(same $tree)
    # shellcheck disable=SC2046,SC2086
    [ -z "$left" ] || kill -TERM $(pids $left) 2>/dev/null
    wt=""; [ -z "$top" ] || wt=$(CDPATH= cd -P -- "$top/.claude/worktrees/$name" 2>/dev/null && pwd -P) || wt=""
    i=0; on=""
    while :; do
      has "$name"; st=$?
      if [ "$st" -ne 1 ]; then w="the tmux session to end"
      elif pid=$(inside "$wt"); then w="process $pid inside its worktree to exit"
      else break; fi
      case " $on " in *" $w; "*) ;; *) on="$on$w; " ;; esac
      if [ "$i" -ge 15 ]; then
        # tmux never answered: nothing proves the session ended, so the close fails.
        if [ "$st" -eq 2 ]; then fail "$name: could not establish that the session ended: $err"
        else say "$name: still waiting on ${on%; } after 15 s; the audit below decides"; fi
        break
      fi
      i=$((i + 1)); sleep 1
    done
    [ "$i" -eq 0 ] || [ "$i" -ge 15 ] || say "$name: waited $i s for ${on%; }"
    if [ -n "$tree" ]; then
      # shellcheck disable=SC2086
      left=$(same $tree)
      # shellcheck disable=SC2086
      [ -z "$left" ] || { sleep 1; left=$(same $left); }
      # shellcheck disable=SC2046,SC2086
      [ -z "$left" ] || kill -KILL $(pids $left) 2>/dev/null
      # shellcheck disable=SC2086
      listed=$(pids $tree) killed=$(pids $left)
      say "$name: ended the processes its session started (process ${listed% })${killed:+; SIGKILL for ${killed% }}"
    fi
  else
    fail "$name: tmux kill-session -t =$name failed; the session may still run"
  fi

  # The spawn's lock (`kit worker NAME`) ends with the session: a closed worker leaves no locked
  # worktree, whether the audit below removes it or keeps it for a later merge's audit. A lock
  # with another reason is someone's choice to keep the worktree, and stays. A close that failed
  # above may leave the session running, so the lock stays and the audit keeps the worktree.
  if [ "$wt_dir" != "$top" ] && gd=$(git -C "$wt_dir" rev-parse --absolute-git-dir 2>/dev/null) &&
     [ "$(cat -- "$gd/locked" 2>/dev/null)" = "kit worker $name" ]; then
    if [ -n "$failed" ]; then say "$name: its worktree stays locked (kit worker $name): the close failed above"
    elif [ -n "$dry" ]; then say "$name: dry run: would unlock its worktree (kit worker $name)"
    elif git worktree unlock "$wt_dir" 2>/dev/null; then say "$name: worktree unlocked (kit worker $name)"; rm -f -- "$record.merged-running"
    else fail "$name: could not unlock its worktree; the audit below keeps it"; fi
  fi
  # The default result reports on the work and is not project content: once the lead committed
  # the files it lists, it is all the audit would keep the worktree for. It moves beside the
  # records instead. A custom --result is a project file: the lead commits it or removes it.
  # An earlier run's report is never replaced, and a worktree the audit keeps gets it back.
  moved=""; lost=""
  if [ -n "$(git -C "$wt_dir" ls-files --others -- "RESULT-$name.md" 2>/dev/null)" ]; then
    # Above the highest earlier number: a lower free one would make a newer report look older.
    n=0; [ ! -e "$record.result.md" ] || n=1
    for f in "$record".result-*.md; do
      k=${f##*.result-}; k=${k%.md}
      case $k in ''|0*|*[!0-9]*) ;; *)
        [ "${#k}" -gt 9 ] || { [ "$k" -le "$n" ] || n=$k; } ;;
      esac
    done
    n=$((n + 1)); saved=$record.result-$n.md; [ "$n" -ne 1 ] || saved=$record.result.md
    if [ -n "$dry" ]; then say "$name: dry run: would move its result RESULT-$name.md to $saved"
    elif mkdir -p -- "${record%/*}"; then
      while :; do
        actual=$(move_recorded_report "$wt_dir/RESULT-$name.md" "$saved"); move_rc=$?
        if [ "$move_rc" -eq 0 ]; then saved=$actual; moved=1; say "$name: its result RESULT-$name.md moved to $saved"; break
        elif [ "$move_rc" -eq 2 ]; then n=$((n + 1)); saved=$record.result-$n.md
        elif [ "$move_rc" -eq 3 ]; then
          fail "$name: could not move its result RESULT-$name.md to $saved; nothing moved, the report stays in the worktree"
          lost=untouched; break
        elif [ "$move_rc" -eq 4 ]; then
          fail "$name: its result RESULT-$name.md moved to $actual, but $record.report-move could not be removed; only that marker is stale: remove it and close again"
          lost=stale; break
        else
          fail "$name: could not move its result RESULT-$name.md to $saved"
          lost=1; break
        fi
      done
    else fail "$name: could not move its result RESULT-$name.md to $saved"; lost=1; fi
  fi
  kept=""; rc=0
  if [ "$lost" = untouched ] || [ "$lost" = stale ]; then
    say "$name: the audit did not run, so the worktree stays; nothing needs recovering, close again once the cause above is gone"
    kept=1
  elif [ -n "$lost" ]; then
    # A successor at the original path proves no restoration. Keep every non-collision failure.
    say "$name: the audit did not run, so a worktree stays: publication of RESULT-$name.md failed; recover the report from its source, archive or the path printed above, else from a .report-move-* folder in ${record%/*}; after recovery remove $record.report-move if present and close again"
    kept=1
  else
    apply=--apply; [ -z "$dry" ] || apply=""
    if [ -z "$noquiet" ]; then
      say "$name: no session of it was ended here and its result is no Kind: completed result, so the quiet period stays for its worktree: it covers a worker the process scan cannot see"
    elif [ -n "$dry" ]; then
      say "$name: dry run: the removal would lift the quiet period for this worktree alone (--no-quiet), every other proof stays"
    fi
    # spawn_worker.sh's ignore file for the hook files it copied has no copy in main, so the
    # audit kept the worktree for it alone: it is set aside for the audit and put back if the
    # worktree is kept, but only while it is byte for byte what the spawn wrote (its record
    # NAME.hooks-ignore-spawned) and untracked. A file the worker extended stays, and the audit
    # keeps the worktree for it. ponytail: a dry run's audit still sees it.
    ignore=$wt_dir/.claude/hooks/.gitignore; aside=""
    if [ -z "$dry" ] && [ "$wt_dir" != "$top" ] && [ -f "$ignore" ] && [ ! -L "$ignore" ] &&
       [ -f "$record.hooks-ignore-spawned" ] && cmp -s -- "$ignore" "$record.hooks-ignore-spawned" &&
       [ -z "$(git -C "$wt_dir" ls-files -- .claude/hooks/.gitignore 2>/dev/null)" ] &&
       mkdir -p -- "${record%/*}" && mv -- "$ignore" "$record.hooks-ignore"; then
      aside=$record.hooks-ignore
    fi
    out=$(sh "$kit/clean_worktrees.sh" $apply "--only=$name" $noquiet 2>&1); rc=$?
    # Deleted only with the worktree: a folder Windows moved aside and not back (MOVED) has no
    # .claude/hooks either, and the file goes back with it.
    removed=""; case $nl$out in *"${nl}clean_worktrees: removed 1,"*) removed=1 ;; esac
    if [ -z "$aside" ]; then :
    elif [ -n "$removed" ]; then rm -f -- "$aside"
    elif [ ! -d "${ignore%/*}" ] || ! mv -- "$aside" "$ignore"; then
      fail "$name: could not put its .claude/hooks/.gitignore back; it is at $aside: move it back once its worktree is back"; kept=1
    fi
    printf '%s\n' "$out" | LC_ALL=C tr '\001-\011\013-\037\177' '?'
    case $nl$out in
      *"${nl}clean_worktrees: no worktree at "*)
        say "$name: no worktree at .claude/worktrees/$name; nothing to remove" ;;
      *"${nl}clean_worktrees: removed 1,"*)
        say "$name: worktree removed through the audit (its log: kit-worktree-removals.log in the git directory)" ;;
      *"${nl}clean_worktrees: dry run: would remove 1,"*)
        say "$name: dry run: the audit would remove the worktree" ;;
      *)
        # The audit's first reason to keep, else its last line (a run that stopped).
        why=$(printf '%s\n' "$out" | sed -n -e 's/^         - //p' -e 's/^         stopped: //p' | sed -n 1p)
        [ -n "$why" ] || why=$(printf '%s\n' "$out" | sed -n '$p')
        if [ -n "$dry" ] && [ "$rc" -eq 0 ]; then
          say "$name: dry run: the audit would keep the worktree: $why"
        else
          fail "$name: worktree kept: $why"; kept=1
        fi ;;
    esac
  fi
  # A nonzero exit is a failed close whatever the summary says: a removal whose outcome line
  # the log could not take still prints `removed 1`, and its audit record is missing.
  [ "$rc" -eq 0 ] || [ -n "$kept" ] ||
    fail "$name: clean_worktrees.sh exited $rc: $(printf '%s\n' "$out" | sed -n '$p')"
  if [ -n "$moved" ] && [ "$wt_dir" != "$top" ] && [ -d "$wt_dir" ]; then
    restored=$wt_dir/RESULT-$name.md; n=0
    while :; do
      move_recorded_report "$saved" "$restored" >/dev/null; move_rc=$?
      if [ "$move_rc" -eq 0 ]; then
        if [ "$n" -eq 0 ]; then say "$name: its result moved back to RESULT-$name.md beside the kept work"
        else say "$name: newer RESULT-$name.md kept; its saved result moved back to $restored beside the kept work"; fi
        break
      elif [ "$move_rc" -eq 2 ]; then n=$((n + 1)); restored=$wt_dir/RESULT-$name-restored-$n.md
      elif [ "$move_rc" -eq 4 ]; then
        fail "$name: its result moved back to $restored beside the kept work, but $record.report-move could not be removed; only that marker is stale: remove it and close again"; kept=1; break
      else fail "$name: could not move its result back from $saved to the kept worktree"; kept=1; break; fi
    done
  fi
  # Any failure above (a tmux that could not answer) keeps them: a worker without a worktree
  # gives the audit nothing to keep, so its success proved no shutdown.
  if [ -z "$dry" ] && [ -z "$failed" ] && [ "$rc" -eq 0 ] && [ -z "$kept" ] && [ -n "$top" ] &&
     [ ! -e "$record.report-move" ] && [ ! -L "$record.report-move" ]; then
    rm -f -- "$record.session" "$record.exit" "$record.live" "$record.question" "$record.result-path" \
      "$record.hooks-ignore-spawned" "$record.pid" "$record.merged-running" "$record.id" "$record.host" \
      "$record.supervisor.log" || fail "$name: could not remove its Codex session records"
  fi
  if git show-ref --verify --quiet "refs/heads/worktree-$name" 2>/dev/null; then
    say "$name: branch worktree-$name is kept, never deleted here; \`git branch --merged\` lists the merged branches, \`git branch -d <name>\` deletes one"
  else
    say "$name: no branch worktree-$name; nothing to keep"
  fi
done

[ -z "$dry" ] || say "dry run: nothing was changed"
[ -z "$first" ] || { say "FAILED: $first"; exit 1; }
exit 0
