# GOTCHAS — environment and tooling traps

**Not a session-start file.** It is referenced from `AGENTS.md` in one line and read when
something behaves unexpectedly — or before you spend an hour on a problem this project has
already paid for once. Keeping it off the every-session reading list is deliberate: it can
grow without costing anything per session.

Each entry: what happened, why it matters, what to do. Add one when a trap costs real time.
Delete one when the cause is gone for good — not when it merely feels old.

This is one of the permanent homes a `[GOTCHA]` line in `docs/STATE.md` gets moved into
before that line is deleted.

---

The entries below ship with the kit. They are not hypothetical: each cost a real day
somewhere, and none of them depends on a particular language or stack.

## Uncommitted work is NOT in the reflog

`git reset --hard`, `git checkout -- <path>`, `git restore`, `git clean -f` and
`git stash drop` discard the working tree, and the reflog does not save you: it records
COMMITS. Anything never committed is gone the moment one of these runs — no message, no
trace, and the next `git status` looks clean.

This kit exists because of failures like it, and it still happened during the kit's own
development: a `git reset --hard HEAD~1`, run to drop a throwaway test commit, also took a
set of uncommitted fixes and a review record the owner had written by hand. The second was
unrecoverable and had to be reconstructed from a chat transcript.

**Commit or stash first, every time**, including — especially — when you are sure the tree
is clean. `git stash push -u -m '...'` costs two seconds and is reversible.

The Claude Code overlay ships `guard_destructive_git.py`, which blocks these commands while
the tree is dirty and prints what would be lost. In any other tool the rule is yours to keep.

## `.gitignore` — the LAST matching rule wins

Git applies the last pattern that matches, so a broad rule written *after* a re-include
silently re-ignores the files you just rescued. This is easy to get backwards, because the
file reads top-to-bottom like a list of exceptions and behaves bottom-to-top.

Keep any re-include block at the very END of `.gitignore` and mark it as such. Never verify
by reading the file and reasoning about it: run `git check-ignore -v <path>`, which names
the winning rule and its line number.

A trailing slash matters too: `node_modules/` matches directories only, and git does not
count a symlink as one. A `node_modules` symlinked into a throwaway worktree is then an
untracked, non-ignored file: `git status` lists it, and the gate's scan skips it with a
`NOTE [scan]` line (older gates failed on it as "a scanner failed to run"). Write
`node_modules` without the slash when the directory may ever be a symlink
(`scripts/doctor.sh` flags it).

## The executable bit has to be put in the git index by hand

On filesystems where `core.filemode` is `false` — Windows mounts, some network shares — git
never notices a `chmod`. The mode recorded in the index is whatever was written when the
file was first added, and files added from such a mount land as `100644`. The script runs
fine locally and CI dies on it with `Permission denied`, exit 126.

That exact failure kept a CI pipeline red for weeks in this kit's founding project, because
a local `CHECK: PASS` was mistaken for evidence about CI. Anyone adding a script runs
`git update-index --chmod=+x <path>`, confirms with `git ls-files -s`, and checks the
pipeline after pushing rather than assuming.

## A fake-CLI test harness cannot catch what the real CLI rejects

A wrapper script was fully proven against a stub binary that recorded its arguments — and
the first REAL run failed instantly, because the actual CLI accepts either a scope flag or
custom instructions, never both.

A stub validates YOUR argument handling. Only a live run validates the CONTRACT. Budget one
real invocation before declaring any CLI wrapper done, and say "not run" until you have
spent it.

## A tool's relative output path resolves against ITS working directory, not yours

A test runner was told to write results to a relative path. It resolved that path against
the project directory it had been handed rather than the calling shell's, so the file
landed somewhere nobody looked. The runner still exited 0, and a gate that checked only the
exit code reported PASS for a run that had executed nothing.

Pass absolute paths to any tool you will read output back from, and make the gate **fail
when the evidence is absent** — no results file is a FAIL, not a pass. An exit code is not
evidence that work was done. (`scripts/check.sh` carries this rule and a negative test for
it.)

## Waiting on your own process: `pgrep -f` and shell wait loops match themselves

A wait loop such as `while pgrep -f "<pattern>"; do sleep 20; done` never ends when the
pattern also appears in the loop's own command line, because `pgrep -f` matches the shell
that runs the loop. It happened three times in one day in the founding project before the
rule was written. Match on the process name (`pgrep -x`), on a pid, or on a file the job
writes; never on text that is also in your command. The same holds for "wait until the
screen shows DONE" when the task text itself contains DONE.

Better still, do not wait at all: an agent that starts the job in the background is told
when it exits, and every waiting turn costs a full read of its context
(`docs/WORKFLOW.md`, "Worker cost").

## An agent puts the user's e-mail into a web request

Some APIs ask clients to put contact details in the `User-Agent` header, and an agent that
has the owner's e-mail address in its session context uses it. In one project five research
agents did, in up to thirteen requests each, before a rule was added to their briefs. The
address then sits in a third party's logs and cannot be recalled.

No personal data in any web request: when an API wants contact details, send a generic
project User-Agent or stop and ask. A brief that sends an agent to the web repeats the rule
and names that User-Agent (`docs/WORKFLOW.md`, "Web requests carry no personal data").

## A red gate that passes on re-run is a finding, not a pass

A full gate run failed on a deadline assertion in one test; the file passed alone and the
next full gate passed with no change. Re-running until `CHECK: PASS` deletes the failing
test, its error line and the load it ran under, so a real race is never seen again until it
bites in CI. Run it once more, and write down what failed, the retry count, what else was
running (another gate, a self-test, a review) and the suspected cause in `docs/STATE.md` or
the operation file before committing (`docs/WORKFLOW.md`, "A red gate that passes on
re-run").

## A checkout under `/mnt/<drive>` in WSL

A repository on a Windows drive seen from WSL gets CRLF line endings from git's autocrlf
(scripts then die with `\r: command not found` or a bad interpreter), installs
Windows-native binaries into `node_modules`, and runs its gate many times slower than on the
Linux filesystem. Clone into the WSL home instead. `scripts/doctor.sh` names the path and
flags a CR in a script.

## A build server the gate started keeps the gate lock

`scripts/check.sh` runs one gate per checkout at a time, through a kernel lock that every
process the build command starts inherits. A build tool that leaves a server running after
the build holds that lock for the server's whole idle life, and the next gate waits for it;
the commit hook waits without a limit. Known ones: MSBuild node reuse and the VBCSCompiler
server after `dotnet build` or `dotnet test`, the Gradle daemon, the `sccache` server. Turn
the server off in the build command (`dotnet build -nodeReuse:false
-p:UseSharedCompilation=false`, `gradle --no-daemon`, `sccache --stop-server` at the end).
The gate's waiting `NOTE [lock]` line names the lock file; `fuser -v <lock file>` or
`lsof <lock file>` shows which process holds it.
