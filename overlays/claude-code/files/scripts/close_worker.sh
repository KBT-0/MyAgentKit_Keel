#!/usr/bin/env sh
# KIT-OWNED: do not edit locally; change it in the kit and re-sync.
# Close finished worker sessions: end each tmux session, then remove its worktree through the
# audited path. The branch is never deleted.
#
# Usage: close_worker.sh [--dry-run] NAME [NAME...]
#   --dry-run  says what it would do, runs the removal's dry run, and changes nothing
#
# The lead runs it once it decides a worker session is finished: no next task fits what the
# session holds, or the session has been idle past the cache lifetime (docs/WORKFLOW.md,
# "Worker cost"). Left to the owner, finished sessions sat idle for hours and 39 worktrees
# piled up. For each NAME, in order, each step on its own line:
#   1. A name outside [A-Za-z0-9_-], a control character included, or one starting with `-`,
#      is refused before any tmux call; the next name still runs. So is a worker whose worktree
#      a gate (check.sh, by its lock) or a git operation (index.lock) is running in: the session
#      is not ended, since that would orphan the run.
#   2. `tmux kill-session -t =NAME`; the terminal tab attached to it closes by itself. A
#      session that does not exist is reported, not an error, when tmux says so (no such session,
#      no server); any other failure of `tmux has-session` (a socket it cannot read) fails the
#      close with tmux's words, as the session may still run. Then it waits, up to 15 s, until
#      `tmux has-session` no longer finds it and, where /proc exists, no process works inside
#      the worktree: the tool inside takes a moment to exit, and the audit would see it. A tmux
#      that still cannot answer at the end of the wait fails the close with its words.
#   3. `clean_worktrees.sh --apply --only=NAME --no-quiet`: the post-merge hook's audit, every
#      proof, for .claude/worktrees/NAME alone, without the quiet period: that margin stands in
#      for "no worker is still in it", and here the lead has just ended the session and decided
#      the work is finished (the hook never lifts it). No --assume-idle: a process still inside
#      keeps the worktree, as does anything else the audit cannot prove; the hook after a later
#      merge, or this script again, removes it then.
#   4. The branch worktree-NAME is never deleted; the line says how to delete merged branches.
# Native Windows has no tmux: step 2 ends the Claude Code session named NAME instead, the
# claude.exe whose command line holds `-n NAME`, with `taskkill /T /F` (its tree), and waits up
# to 15 s until no such process is left; its Windows Terminal tab closes by itself, because the
# tab's command ends with `exit 0` (spawn_worker.sh). A lister that cannot answer fails the
# close with its words, as the session may still run. A Codex worker (spawn_codex.sh) is a
# codex.exe whose command line names its folder with -C instead: while one runs in the worker's
# folder, nothing is done for that name, since its .myagentkit/workers/NAME.session record is
# the only id to resume it by; the lead quits it in its tab and closes again. Steps 1, 3 and 4
# are the same. On every host a Codex worker whose decision file (the path NAME.question
# records, else QUESTION-NAME.md at its top) still exists is refused before step 2: the lead
# answers it with spawn_codex.sh --resume, or deletes it to abandon the worker. Before step 3 an
# untracked RESULT-NAME.md at the worker's top moves to .myagentkit/workers/NAME.result.md:
# the lead read it and committed the files it lists. An earlier report there stays, and this one
# takes the number above the highest there (NAME.result-2.md, -3, ...), so a newer report never
# has a lower number; a worktree the audit keeps gets its result back. After a
# removal (or with no worktree), the Codex records NAME.session, NAME.exit, NAME.live and
# NAME.question go too; a kept worktree keeps them.
# Exit 0 when every named session is gone and every named worktree was removed or did not
# exist; 1 otherwise, with the first reason on the last line: a nonzero exit of
# clean_worktrees.sh is one whatever its summary says (after a removal, an outcome line its log
# could not take); 2 on a usage error. A dry run exits 1 only for a refused name, a waiting
# decision, a running Codex session, a tmux or lister that could not answer, or a removal that
# could not run.
set -u

# Every line of this script is printed with its control bytes as `?` (a name is an argument).
say() { { printf 'close_worker: %s' "$1" | LC_ALL=C tr '\001-\037\177' '?'; echo; }; }
first=""
fail() { say "$1"; [ -n "$first" ] || first=$1; }
# Claim the destination with an exclusive rename: 2 is a collision, 1 any other failure, with
# only its errno and text on stderr (a path can hold control bytes). Never fall back to a
# free-name check followed by an overwriting rename.
move_report() {
  $kit_python -I -c 'import ctypes, errno, os, sys
source, target = sys.argv[1:]
unsupported = (errno.EINVAL, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP)
try:
    if os.name == "nt":
        os.rename(source, target)  # Windows refuses an existing destination atomically.
    else:
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
        if error in unsupported:
            # A filesystem without an exclusive rename (WSL /mnt/c, NFS, FUSE, SMB): a hard
            # link refuses an existing name as atomically, and names a symlink, not its target.
            try:
                os.link(source, target, follow_symlinks=False)
            except OSError as link_error:
                if link_error.errno not in unsupported + (errno.EPERM,):
                    raise
                # ponytail: the weaker case, no hard links either: the name is claimed
                # exclusively, but a writer that opens the claimed empty file without O_EXCL
                # before this replace loses its bytes to it.
                os.close(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
                try:
                    os.replace(source, target)
                except OSError:
                    os.unlink(target)
                    raise
            else:
                os.unlink(source)
        elif error:
            raise OSError(error, os.strerror(error))
except FileExistsError:
    sys.exit(2)
except OSError as error:
    sys.exit("[Errno %s] %s" % (error.errno, error.strerror))' "$1" "$2"
}
nl='
'
# Git for Windows' dirname handles both separators, including mixed paths such as D:/p\scripts\x.sh.
case $0 in *'\'*) kit=$(dirname -- "$0") ;; */*) kit=${0%/*} ;; *) kit=. ;; esac
# The physical path of the worktree, or empty; /proc/PID/cwd names physical paths.
top=$(git rev-parse --show-toplevel 2>/dev/null) || top=""
# inside DIR: prints one process working in DIR or below and succeeds; Linux /proc only.
inside() {
  [ -n "$1" ] && [ -e /proc/self/cwd ] || return 1
  for d in /proc/[0-9]*; do
    c=$(readlink "$d/cwd" 2>/dev/null) || continue
    case $c in "$1"|"$1"/*) printf '%s' "${d#/proc/}"; return 0 ;; esac
  done
  return 1
}
# has NAME: 0 the session exists, 1 tmux says it or its server does not, 2 tmux could not
# tell (its words in $err): only the second is proof of absence.
has() {
  err=$(tmux has-session -t "=$1" 2>&1) && return 0
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
sessions() {
  out=$(${KIT_PS:-powershell.exe -NoProfile -NonInteractive -Command} \
    "Get-CimInstance Win32_Process -Filter \"Name='claude.exe' or Name='node.exe'\" | ForEach-Object { \"\$(\$_.ProcessId) \$(\$_.CommandLine)\" }" \
    2>&1) || { printf '%s' "$out"; return 2; }
  printf '%s\n' "$out" | $kit_python -I -c 'if 1:
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
case $(uname -s 2>/dev/null) in MINGW*|MSYS*|CYGWIN*) windows=1 ;; *) windows="" ;; esac
# codex DIR: the process ids of the codex.exe programs whose command line names DIR with -C,
# as spawn_codex.sh's running() reads them. ponytail: a text match on `-C <folder>`, not a
# full command-line parse; a worker without --worktree shares this checkout's folder, so any
# Codex session there holds the close of such a name.
codex() {
  out=$(${KIT_PS:-powershell.exe -NoProfile -NonInteractive -Command} \
    "Get-CimInstance Win32_Process -Filter \"Name='codex.exe'\" | ForEach-Object { \"\$(\$_.ProcessId) \$(\$_.CommandLine)\" }" \
    2>&1) || { printf '%s' "$out"; return 2; }
  folder=$(cygpath -w "$1") || { printf '%s' "cygpath cannot convert $1"; return 2; }
  printf '%s\n' "$out" | $kit_python -I -c 'if 1:
    import re, sys
    folder = re.escape(sys.argv[1].rstrip("\\/"))
    pat = re.compile(r"\s-C\s+(\"%s[\\/]?\"|%s[\\/]?)(\s|$)" % (folder, folder), re.I)
    print(" ".join(l.split(" ", 1)[0] for l in sys.stdin.read().replace("\r", "").split("\n")
                   if l.split(" ", 1)[0].isdigit() and pat.search(l)))' "$folder"
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
dry=""
[ "${1-}" = --dry-run ] && { dry=1; shift; }
[ $# -ge 1 ] || { sed -n '6,7p' "$0"; exit 2; }

for name; do
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
  record=$top/.myagentkit/workers/$name
  # An unanswered Codex decision: its session record is the only way to answer it, and a fresh
  # spawn of the name is refused while the question exists, so a close would strand both.
  ask=$(cat "$record.question" 2>/dev/null) || ask=$wt_dir/QUESTION-$name.md
  if [ -e "$ask" ]; then
    fail "$name: a decision waits for its answer in $ask; answer it (spawn_codex.sh --resume), or delete it to abandon the worker, then close again; nothing is done for $name"
    continue
  fi
  if [ -n "$windows" ] && { [ -e "$record.session" ] || [ "$wt_dir" != "$top" ]; }; then
    if ! pids=$(codex "$wt_dir"); then
      fail "$name: could not list the Codex processes, so its Codex session may still run: $pids; nothing is done for $name"
      continue
    elif [ -n "$pids" ]; then
      fail "$name: a Codex session still runs in $wt_dir (process $pids); its session record and worktree are kept: quit it in its tab (/quit), then close again"
      continue
    fi
  fi

  if [ -n "$windows" ]; then
    if ! pids=$(sessions "$name"); then
      fail "$name: could not list the Claude Code sessions, so $name may still run: $pids; its worktree is not touched"
      continue
    elif [ -z "$pids" ]; then
      say "$name: no Claude Code session named $name runs; nothing to end"
    elif [ -n "$dry" ]; then
      say "$name: dry run: would end the Claude Code session $name (process $pids, taskkill /T /F) and wait up to 15 s for it; while it runs, the audit below keeps its worktree"
    elif why=$(busy "$wt_dir"); then
      refuse; continue
    else
      for pid in $pids; do MSYS_NO_PATHCONV=1 taskkill /PID "$pid" /T /F >/dev/null 2>&1; done
      i=0
      while left=$(sessions "$name") && [ -n "$left" ] && [ "$i" -lt 15 ]; do i=$((i + 1)); sleep 1; done
      if ! left=$(sessions "$name"); then
        fail "$name: could not establish that the session ended: $left; its worktree is not touched"
        continue
      elif [ -n "$left" ]; then
        # Not audited: a session still running is the one thing the close exists to rule out.
        fail "$name: the Claude Code session still runs after taskkill (process $left); its worktree is not touched"
        continue
      else
        say "$name: Claude Code session ended (process $pids); its Windows Terminal tab closes by itself"
      fi
    fi
  elif ! command -v tmux >/dev/null 2>&1; then
    say "$name: no tmux session (tmux is not installed); nothing to end"
  elif has "$name"; st=$?; [ "$st" -eq 1 ]; then
    say "$name: no tmux session named $name; nothing to end"
  elif [ "$st" -eq 2 ]; then
    fail "$name: tmux could not say whether session $name exists, so it may still run: $err"
  elif [ -n "$dry" ]; then
    say "$name: dry run: would end tmux session $name (tmux kill-session -t =$name) and wait up to 15 s for it; while it runs, the audit below keeps its worktree"
  elif why=$(busy "$wt_dir"); then
    refuse; continue
  elif tmux kill-session -t "=$name" 2>/dev/null; then
    say "$name: tmux session ended; the terminal tab attached to it closes by itself"
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
  else
    fail "$name: tmux kill-session -t =$name failed; the session may still run"
  fi

  # The default result reports on the work and is not project content: once the lead committed
  # the files it lists, it is all the audit would keep the worktree for. It moves beside the
  # records instead. A custom --result is a project file: the lead commits it or removes it.
  # An earlier run's report is never replaced, and a worktree the audit keeps gets it back.
  moved=""
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
        move_report "$wt_dir/RESULT-$name.md" "$saved"; move_rc=$?
        if [ "$move_rc" -eq 0 ]; then moved=1; say "$name: its result RESULT-$name.md moved to $saved"; break
        elif [ "$move_rc" -eq 2 ]; then n=$((n + 1)); saved=$record.result-$n.md
        else fail "$name: could not move its result RESULT-$name.md to $saved"; break; fi
      done
    else fail "$name: could not move its result RESULT-$name.md to $saved"; fi
  fi
  apply=--apply; [ -z "$dry" ] || { apply=""; say "$name: dry run: the removal would lift the quiet period for this worktree alone (--no-quiet), every other proof stays"; }
  out=$(sh "$kit/clean_worktrees.sh" $apply "--only=$name" --no-quiet 2>&1); rc=$?
  printf '%s\n' "$out" | LC_ALL=C tr '\001-\011\013-\037\177' '?'
  kept=""
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
  # A nonzero exit is a failed close whatever the summary says: a removal whose outcome line
  # the log could not take still prints `removed 1`, and its audit record is missing.
  [ "$rc" -eq 0 ] || [ -n "$kept" ] ||
    fail "$name: clean_worktrees.sh exited $rc: $(printf '%s\n' "$out" | sed -n '$p')"
  if [ -n "$moved" ] && [ "$wt_dir" != "$top" ] && [ -d "$wt_dir" ]; then
    restored=$wt_dir/RESULT-$name.md; n=0
    while :; do
      move_report "$saved" "$restored"; move_rc=$?
      if [ "$move_rc" -eq 0 ]; then
        if [ "$n" -eq 0 ]; then say "$name: its result moved back to RESULT-$name.md beside the kept work"
        else say "$name: newer RESULT-$name.md kept; its saved result moved back to $restored beside the kept work"; fi
        break
      elif [ "$move_rc" -eq 2 ]; then n=$((n + 1)); restored=$wt_dir/RESULT-$name-restored-$n.md
      else fail "$name: could not move its result back from $saved to the kept worktree"; break; fi
    done
  fi
  if [ -z "$dry" ] && [ "$rc" -eq 0 ] && [ -z "$kept" ] && [ -n "$top" ]; then
    rm -f -- "$record.session" "$record.exit" "$record.live" "$record.question" || fail "$name: could not remove its Codex session records"
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
