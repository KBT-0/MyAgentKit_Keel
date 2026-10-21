# CHANGELOG

What changed in the kit, dated, newest first. `sync-kit.sh` writes the **ACTION** items added
since a project's recorded kit version to the project's `docs/kit/UPGRADE.md`, so an entry
must say what a project OWNER has to do — not just what moved. Mark anything needing
hand-application with **ACTION**: a project-owned file (no `KIT-OWNED` header) reaches a
project only through an ACTION item that names it.

Versions are `MAJOR.MINOR`. MINOR adds or refines; MAJOR changes a rule or a file layout in
a way that existing projects must reconcile by hand.

WHY an entry exists belongs in `RESEARCH_LOG.md`; this file records WHAT changed.

---

## v0.12.1 — 2026-10-21

CI fixes for the v0.12 push (run 39571614846: every Linux and macOS job, and Windows py3.11 slow,
failed). Every changed file is kit-owned; no ACTION.

- `spawn_worker.sh` and `watch_workers.sh` use no `-ef`, `-nt` or `-ot` (undefined in POSIX sh,
  shellcheck SC3013): a same-file test through `os.path.samefile` and a `newer` helper on `find
  -newer`, with the same results.
- `spawn_worker.sh`: the background host's two `cd "$dir"` clear CDPATH like every other `cd`.
- `claude_bridge.py`: macOS's bsdtar stops reading at the archive's end blocks, and `git archive`
  died of SIGPIPE writing its record padding; a SIGPIPE'd archive whose tar exited 0 is no
  copy failure (a review failed `copy_failed` on macOS).
- `claude_bridge.py`: `CLAUDE_CLI_BIN` naming a file is probed as the review launches it; on
  native Windows doctor called an unlaunchable extensionless file ready on Python 3.12+ and
  MISSING on 3.11.
- `doctor.sh`: the CLI check's output replaces what the console code page cannot hold; a
  localized Windows error ("[WinError 193] ... değil") raised in print, and doctor said ready.
- `review_dispatch.py`: the backend folder inside the repository is refused when the repository
  is named through a symlink too (macOS's `/var` is `/private/var`).
- `clean_worktrees.py`: a tmux session of the worker's name that started in another checkout,
  or in another worker's worktree of this one, no longer keeps the worktree, as `close_worker.sh`
  already reads it (#171); one started in this worktree, or with no start folder, still does.
- `codex_worker.py`: a worker group whose members are all zombies (macOS answers `killpg` with
  EPERM) is nothing left to stop; a supervisor stopped by SIGTERM or SIGHUP exited 1.
- Tests: two new (the zombie group, POSIX and Windows; the early-ending tar, POSIX), so
  `test_codex_worker` is 66 on Windows, 68 or 67 elsewhere and `test_claude_bridge` 280 on POSIX;
  the POSIX count of `test_spawn_worker` is 97; the clean_worktrees, git option (run in
  the C locale), git_hooks (UTF-8 bytes, a binary lock file), doctor (the stub lists every flag
  but `--restricted`; the probe wait scales), sandbox, worker paths and bridge tests follow the
  current messages and macOS's resolved temp paths; the acceptance's stand-in flock reaches a
  nested run through `GATE_PYTHON` (#249).

---

## v0.12 — 2026-10-20

`sync-kit.sh` writes this section's **ACTION** items to `docs/kit/UPGRADE.md` of a project whose
recorded kit version is older than v0.12. The sync copies only `KIT-OWNED` files; every other
file the kit changed reaches the project through these items.

- **Workers run as Claude Code background sessions** (owner decision 77; research
  `docs/research/worker-orchestration-spike.md` and `-spike-posix.md`). `spawn_worker.sh` starts
  a worker with `claude --bg` on every platform whose CLI lists `--bg`; the Windows Terminal tab
  and tmux stay as the fallback, and `MYAGENTKIT_WORKER_HOST=bg|tab|tmux` forces one (`--bg` in
  the help counts with or without a comma after it). It records `NAME.host`, `NAME.id` and the full
  `NAME.session`, and prints `claude agents`, `claude attach
  ID` and `claude logs ID` to see the worker. A worker's settings carry `worktree.bgIsolation:
  none` (it never pushes on its own), `MYAGENTKIT_ROLE=worker` in `env` and no commit
  attribution. `--resume` wakes the same session by its full id from the worker's folder.
  The new `list_workers.sh` lists this checkout's workers (host, id, state, what it waits for,
  result); `watch_workers.sh` reports a background worker DONE, BLOCKED, WAITING or GONE from its
  row in `claude agents --json --all`; `close_worker.sh` ends it with `claude stop` and `claude
  rm` by id, never by name and never with `claude daemon stop`. **ACTION**: run `claude` once in
  the project's main checkout and accept the trust prompt, or a background spawn is refused with
  that instruction.

- **A watch never loops silently on a worker it cannot see.** A name with no record in the
  watching checkout and no session exits 2 on every host, tmux or none, and names the worktree
  that holds its records, or reads the `--result NAME=PATH` given; the printed watch line runs
  from the checkout holding the records, and a second printed line is a plain until-loop on the
  result file.

- **A finished worker's worktree is removed after its merge.** The gate's own state in the
  worktree's git folder (`kit-stop-gate.tree`, `check-gated-tree`) no longer counts as unsaved
  work. `codex_worker.py --publish` refuses a question file without the end marker, which left
  the session waiting forever; `close_worker.sh` no longer fails a project's shellcheck (SC2086).

- **A `--worktree` worker starts without a permission click.** Its brief, or a resume's answer,
  outside its folder is copied to `.myagentkit/workers/NAME.brief.md` inside it and the prompt
  names that copy: on a host not in auto mode the worker's first read stopped on a prompt. Its
  reach is not widened; `close_worker.sh` removes the copy before its audit.

- **A worker spawned from a linked worktree is closed.** Both spawns put a `--worktree` worker's
  worktree in the main checkout's `.claude/worktrees`, the one folder the audit removes from;
  nested in the lead's worktree, `close_worker.sh` said "nothing to remove" and left it. Close,
  watch and list look there; one an older spawn nested is kept, lock included, and named, never
  dropped.

- **The lead's done signal is a disk watch, not an idle notice** (owner order 2026-10-20).
  `spawn_worker.sh` prints `sh scripts/watch_workers.sh --result NAME=PATH NAME` first, on tmux and
  on a Windows Terminal tab, to run as one background command whose exit wakes the lead; a
  `notify_when_idle` subscription is optional, because 4 of 5 supervised closes sent no notice. A
  background review runs `review.sh` itself as the background command, or is waited on through
  its log, never a pid. WORKFLOW, REVIEW_RUNNING and the overlay README say the same; a lead that
  copied the old spawn steps should start the watch at every spawn.

- **A new hook refuses an agent's write to a secret file** (#297; `guard_secret_files.py`,
  PreToolUse on Edit, Write and NotebookEdit). `.env*`, `.dev.vars*`, `credentials` with no or a
  config extension, `*.pem`, `*.key`, `.npmrc` and `.netrc` are refused; templates (`.example`,
  `.sample`, `.template`, `.dist`) and source files such as `credentials.py` pass. The owner edits
  such a file from the terminal, so a secret never passes through an agent's context. It fails
  open on unreadable input or a missing Python. Shell writes and reads are not seen.
  **ACTION:** copy `.claude/hooks/guard_secret_files.py` from the kit's
  `overlays/claude-code/files/` (hooks are not synced) and add its PreToolUse entry to your
  `.claude/settings.json` as the overlay's has it: matcher `Edit|Write|NotebookEdit`, timeout 30,
  no `onFailure`.

- **watch_workers.sh reports a finished worker even when its session is already gone** (#294).
  A GONE session's result file is read first, so it reports DONE (or BLOCKED, HANDOFF) beside
  GONE, and a result reported once is not reported again after the session ends. A committed
  result is the exception: the first poll after `--resume` reports the earlier run's committed
  result once more.

- **A failed Codex review names Codex's own error** (#292). A `turn.failed` or `error` event's
  message (a refused model, for one) ends the evidence as `## Failure — Codex reported: ...`
  instead of "No final message", only when the run failed on Codex's side.

- **usage_summary.py reads older and moved review records** (#291). A record written before v0.9
  (no sha256) shows its verdict marked `hash=none` instead of `evidence mismatch`; an archive whose
  recorded absolute path is gone (a moved or recloned checkout, a Windows path read on POSIX) is
  read from `docs/reviews/<name>`. Hashed records keep the strict check.

- **REVIEW_RUNNING says where a worker's own review rounds count** (#293). A `review.sh` round a
  worker runs in its worktree is an inner round, not one of the lead's two; the lead's review of
  the merged change starts its own label in the main checkout with the worker's archive as
  dispositions.

- **A worktree kept for unmerged files says what to do** (#295). `clean_worktrees.py` tells you to
  copy each file to the same path in the main checkout or delete it, then close again;
  `worker.md` tells a worker to delete its helper script before its last commit (the overlay's
  `.claude/agents/worker.md` is project-owned: the test-rules entry below has it merged).

- **bootstrap.sh and sync-kit.sh list a project's own reviewer agent beside diff-reviewer.md**
  (#161). When `.claude/agents/diff-reviewer.md` exists, every other `.md` under
  `.claude/agents` (subfolders too, as Claude Code reads them) whose front matter `name:` holds
  "review" at a word start (not `ui-preview`) is printed as `conflict: ... keep one of the two`;
  it does not stop the run, and neither file is moved or changed. The description is not
  read: workers and planners mention reviews in passing. Nothing to do: keep one definition
  when the line appears (docs/UPDATING.md).

- **bootstrap.sh stops on an empty `docs/kit/.kit-version`** instead of stamping the latest
  version over it, as sync-kit.sh does. Nothing to do: the stop says to write the version or
  delete the file for a first install.

- **A new review focus starts its own round count** (#102, #248; owner decision 67;
  `scripts/claude_bridge.py`, `prior_rounds`). A high-tier change's natural order, logic round 1,
  fix, logic round 2, then portability, was refused before any model ran: a focus not seen under
  the label took the highest count. Now a named focus counts its own rounds plus the rounds without
  a focus, so portability gets its round 1 and round 2 after logic used both; its third still needs
  `REVIEW_ROUND_EXCEPTION`, and an unset focus still takes the highest count. Only `logic` and
  `portability` exist, so a made-up name opens nothing. `scripts/usage_summary.py` numbers the
  rounds the same way. `docs/REVIEW_GATE.md` ("Rounds") states the rule. The sync brings
  `scripts/usage_summary.py` only: `scripts/claude_bridge.py` comes with the review companion set
  (the "review companions move as one set" entry below), and `docs/REVIEW_GATE.md` with the
  project-owned docs.

- **A bridged reviewer gets the behaviour appendix without the author's rules** (#228;
  `scripts/claude_bridge.py`, `BEHAVIOUR.md`). The three bullets a reviewer cannot act on
  (finish the scope with its check, design before code, one test per behaviour change) carry
  `<!-- author-only -->`, and a review's prompt leaves those bullets out; a proposal and a
  spawned worker still get the whole file. The review's `behaviour_sha256` and fingerprint name
  the bytes the reviewer got. The sync brings `BEHAVIOUR.md`; `scripts/claude_bridge.py` comes
  with the review companion set (entry below).

- **Every plugin command and Codex skill says when the project's kit version is another**
  (#156). Each one names the plugin's kit version (`This plugin is kit v0.11.0.`, the whole
  version, stamped by `scripts/package_codex_plugin.py`, whose `--check` refuses a stale one),
  reads the project's `docs/kit/.kit-version` and, when the two differ as numbers (a missing
  part counts as 0: 0.12 is 0.12.0), prints one line: both versions, which is newer, and that `/myagentkit:sync` (Codex: the `myagentkit-sync` skill) brings the project to
  the newest release. It never stops and uses no network. Nothing to do: update the plugin.

- **A changed worktree-disposable list shows what it would remove before it removes it**
  (#288 point 2; `scripts/clean_worktrees.py`, Claude Code overlay). A removal that takes files
  only the changed committed list makes disposable waits one `--apply` (the post-merge hook's
  run, or close_worker.sh's `--apply --only=NAME`): that run prints it as `would remove ...`
  with the reason, and the next one removes it; a dry run prints it as `would preview ...` and
  counts it as kept. The list a full `--apply` ran with is kept in the git directory
  (`kit-worktree-disposable-applied`), and each worktree's own preview beside it
  (`kit-worktree-disposable-previewed/`): a worktree kept for another reason when the list
  changes keeps the list it was covered by, so it is previewed before the new list removes it.
  A project with no list recorded adopts the list in force; a record that cannot be read
  covers nothing. Nothing to do: the next sync brings the script.

- **The project gate keeps every AGENTS.md chain Codex loads under 24 KiB** (#143;
  `scripts/check.sh`, `[agents-size]`). Codex joins the AGENTS.md of each folder from the root
  down to the one it works in and drops, without a word, what passes 32 KiB
  (`project_doc_max_bytes`); the tail holds the STOP list and the completion checklist. Each
  chain must stay under 24 KiB when `scripts/review.sh` names Codex (`DEFAULT_REVIEWER="codex"`
  or a `CODEX_MODEL`); without it a chain over the margin is a NOTE. **ACTION:** merge the new
  section 2c2 into your `scripts/check.sh`; if it fails, move what only some tasks need out of
  `AGENTS.md` into a doc the reading order points to.

- **Test rules rest on a binding report** (`docs/research/test-rules.md`; decision 37). A logic
  change brings its test in the same change; writing the test first is advice, not a rule. A
  gate check keeps its red proof by a bad-input fixture test; an ordinary new test needs no
  mandatory red proof, and the review asks whether it breaks when the code is reverted.
  Existing tests stay; only tests measured as redundant or slow are consolidated, and a
  reviewer does not count such a measured consolidation as a deleted test. Recommended, from
  the leeway project's decision: a generated-content pipeline validates its output (data
  validation, captures); unit tests of the generator are not mandatory. `docs/gates-must-be-proven-red.md` says the rule is for gate
  checks; the setup interview says "a check never seen failing".
  **ACTION:** merge the new test rule into your copies of `AGENTS.md` (the "No untested code"
  bullet), `docs/WORKFLOW.md` (Task lifecycle step 4, the first bullet of "Writing a gate", and
  the sources under "Where the constitution's rules come from") and `docs/REVIEW_GATE.md`
  (priorities 5 and 6), and merge the overlay's `.claude/agents/worker.md` into yours (the
  report line, and the helper script deleted before the last commit, #295), keeping your pins.

- **The project gate's whole-gate `check.sh --self-test` is gone; each check is proven by its
  own fixture test** (decision 23; `docs/research/kit-self-checks.md`, findings 1 and 2). A
  fixture test feeds one check a small input in a throwaway folder, red with its own FAIL line
  on a bad input and green on a good one; it runs in the normal test suite in seconds and never
  runs the build. The gate loses its seams (`GATE_SELFTEST_*`, `GATE_BUILD_CMD_OVERRIDE`,
  `BOUNDARY_SELFTESTS_FILE`), exit code 3 and the token in its lock file; it exits 0, 1, 2
  (usage) or 75 (lock not taken). The Unity gate and the Stop hook lose their self-test paths,
  the overlay allow list loses its two `--self-test` rules, and the "self-test owed" rule and
  `sync-kit.sh`'s demand for it are gone. `review.sh --self-test`, the review suite runner,
  stays. (#80, #110, #124, #126, #152, #125, #84, #81 in part)
  **ACTION:** (1) Take the new `scripts/check.sh` whole and re-apply every value you filled
  (for example `toolchain_path`, `module_roots`, `architecture_file`, `build_test_cmd`,
  `docs_only_skip_build`, `STRONG_REVIEW_DAYS`/`STRONG_REVIEW_TASKS`); new: `build_cache_inputs`
  and `docs_always_build` (the gate-changes entry below); stop calling `check.sh --self-test`
  anywhere (scripts, CI, docs, agent briefs). (2) Delete `scripts/boundary_selftests.sh`, and in the header comment of your
  `scripts/boundary_checks.sh` replace "needs a matching case in scripts/boundary_selftests.sh"
  with the kit's fixture-test paragraph. For
  each check in `scripts/boundary_checks.sh` write a fixture test instead, as the example at the
  end of the kit's `boundary_checks.sh` header shows (`expect red '<FAIL line>' <path> '<line>'`
  and `expect green - <path> '<line>'`), and run it from your build command (for example
  `sh tests/boundary_checks_test.sh && <your build>`). (3) Claude Code overlay: remove the two
  `--self-test` allow rules from `.claude/settings.json` and take the new
  `.claude/hooks/gate_on_stop.sh`. (4) Unity overlay: take the new `scripts/unity_gate.sh` (no
  `--self-test`; it now needs `ProjectSettings`, converts paths with `cygpath` on Git for
  Windows, names Unity's separate CLI when it finds that instead of the editor, counts no suite
  or run result as a test case, and fails a failed suite over passing cases; #175, #166), and replace the `boundary_selftests.sh` case of the networking check with the
  two `expect` lines in `docs/UNITY_SETUP.md`. (5) Merge the self-test-free text into your
  copies of `docs/WORKFLOW.md` ("Writing a gate"; a run beside the reviews shares their worktree
  only when it writes nothing but ignored files), `docs/DEV_SETUP.md` §5 (a PASS says the checks
  found nothing; the gate does not check that fixture tests exist), `docs/GOTCHAS.md`,
  `docs/REVIEW_GATE.md`, `docs/REVIEW_RUNNING.md`, `.claude/agents/diff-reviewer.md` and the
  Unity overlay's `README.md`; re-copy `scripts/review.sh`, `scripts/claude_bridge.py`,
  `scripts/agent_usage.py`, `scripts/review_test_support.py` and `scripts/test_claude_bridge.py`
  (their comments and the reviewer prompt no longer name the self-test).

- **Opt-in build cache** (`scripts/check.sh`): the gate can skip a build that already passed on
  the same inputs. The key covers every file `git ls-files --cached --others --exclude-standard`
  lists (read from disk), the gate script itself and the output of `build_cache_inputs` (empty,
  the default, keeps it off; never used on CI). A cached run prints
  `NOTE [build]: not run: cached PASS <key> from <date>` and says so in its PASS line. The cache
  is off when a symlink in the tree points to a file outside the tree or in an ignored folder,
  since that target is not in the key. (#82)
  **ACTION:** to use it, set `build_cache_inputs` in the new `scripts/check.sh` (starters in its
  comment and in WORKFLOW "Writing a gate"); `GATE_CACHE=off` runs a full build.

- **Claude Code overlay: the git and e-mail guards judge every shell tool** (#93, #213). Both
  matched Bash only, so PowerShell and Monitor calls bypassed the destructive-git, `--no-verify`
  and private-e-mail guards. The hooks read `tool_input.command` from any tool and Monitor's
  `ws.url`; PowerShell syntax (no backslash escapes, `$env:X = v`, backtick, `--%`, a splat
  `git @a`) is read or refused as unreadable. The `git ... --output/--ext-diff/--textconv/--submodule`
  deny rules get PowerShell twins; Monitor already obeys the Bash rules.
  **ACTION:** in `.claude/settings.json`, change the PreToolUse matchers `"Bash"` to
  `"Bash|PowerShell|Monitor"` and `"WebFetch|WebSearch|Bash"` to
  `"WebFetch|WebSearch|Bash|PowerShell|Monitor"`, and add the four deny rules
  `PowerShell(git *--out*)`, `PowerShell(git *--ext*)`, `PowerShell(git *--textc*)` and
  `PowerShell(git *--sub*)` beside their Bash twins.

- **`guard_destructive_git.py`** (#127, #108, #77, #93):
  - Refused whatever the tree's state: a ref delete or forced move that loses commits no other
    ref reaches (`branch -D`/`-d -f`/`-f`/`-M`/`-C`, `tag -d`/`-f`, `update-ref`, `remote
    remove`/`rm`; a checked-out branch's own HEAD no longer counts as reaching them),
    `update-ref --stdin`, `reflog expire`/`delete`, `gc --prune=<anything but never>`,
    `-c gc.pruneExpire=now gc`, `prune` without `-n`, and `worktree remove --force` while the
    named worktree holds uncommitted or untracked work. Abbreviated long options are read.
  - Judged like `restore` on a dirty tree: `rm -f` (not `--cached`), `mv -f`,
    `checkout-index -f`, `read-tree -u --reset`.
  - Git that appears only in data or code is no longer refused: `$(...)`, backticks, `eval`,
    `sh -c` (also behind `timeout` or `xargs`, with its own `cd`) and a here-document a shell
    reads are parsed as shell; in interpreter code or another program's arguments each
    `git ...` is judged as the command it names, an argv list laid out one item per line
    included. doctor's `cd <repo> && git config core.hooksPath .githooks` passes as printed.
  - It fails closed on what it cannot read: a ref, remote, worktree, subcommand or folder named
    by a variable or a substitution of either shell (POSIX `$var`, `$(...)`, backticks;
    PowerShell `$var`, `$env:X`, `$(...)` and a `( ... )` sub-expression), an xargs-appended
    operand, `{}` or an interpolated operand (`{b}`, `#{b}`, `%s`), and code that sets a folder
    (`cwd=`, `chdir`), count as the worst case.
    Accepted cost: code or data that mentions a folder change and a dirty-sensitive git command
    is refused on a clean tree too; prose that names a loss-certain command (`git stash drop`)
    still reads as that command.
  - In PowerShell a `( ... )` operand is read as a sub-expression: `git branch -D ($b)`,
    `git tag -d (...)`, `git update-ref -d (...)` and `git remote remove (...)` name a ref the
    hook cannot read and are refused. A git subcommand run in a folder the line has not made yet
    (a `git clone` then `cd`) is refused by that name, not as an unreadable alias.
  - `#` comments end at their line; a `!` alias, `submodule foreach` and `bash -s` are judged.
  - The spawn scripts' clean-up hints no longer suggest `branch -D` (kit-owned, synced).
  **ACTION:** re-copy `.claude/hooks/guard_destructive_git.py`; merge the guard paragraph of
  `docs/GOTCHAS.md` and the guard rows of the Claude Code overlay README into your copies.

- **`guard_private_email.py`** (#211, #212, #213): reads the project's `user.email`
  (`CLAUDE_PROJECT_DIR`) as well as the current folder's, failing closed on a git error, so a
  per-project identity is protected from the scratchpad. A web command that prints an address
  at run time is refused: `git log`/`show`/`whatchanged` without `--oneline` or a custom format,
  a built-in `--format`/`--pretty` that prints addresses, `%ae`/`%ce`/`%(authoremail)` and the
  like, `git var`, `git config -l`/`--list`/`--get-regexp`/`list`/`get --regexp`, `env`,
  `printenv` and PowerShell `Get-ChildItem env:`. Quoted `-C` paths and `ws://`/`wss://` URLs are
  read. A git error reading the owner's address names the folder to fix and git's first error
  line. **ACTION:** re-copy `.claude/hooks/guard_private_email.py`.

- **`guard_worker_route.py`** (#137): an Agent call without model/effort passes when the agent's
  definition pins both with real values (diff-reviewer, and worker after setup). The definition
  is found by its `name:` field, project folder before user folder; a quoted `inherit` or a
  `{{placeholder}}` is no pin. The refusal states the worker rule and the reviewer rule
  separately. **ACTION:** re-copy `.claude/hooks/guard_worker_route.py`.

- **Stray background tool commands** (#298): a `find /` that outlived its session kept a CPU
  core busy for seven hours and skewed every timing. The new `guard_root_scan.py` (PreToolUse:
  Bash, PowerShell, Monitor) refuses a search or walk from a filesystem or drive root
  (`find /`, `grep -r /`, `rg`, `du`, `tree`, `ls -R`, `dir /s`, `Get-ChildItem -Recurse C:\`)
  unless bounded to depth 3 (`env -C DIR`, `env --chdir=DIR` and `sudo -D DIR` set the walk's
  folder); it reads the command as the shell does (heredoc bodies are data)
  and fails open, so a stalled guard never refuses a call. `close_worker.sh` ends the process
  tree below a tmux session's panes with the session, never a pid that has since gone to another
  process (Windows: `taskkill /T` already does). `doctor.sh` lists, never ends, search or walk
  tools and shells (on Windows also python, node, npm) older than two hours whose parent is gone
  and that used more than 5% of a CPU, each with the command that ends it. GOTCHAS: "A timing
  taken on a busy machine is not a result". **ACTION:** re-copy `.claude/hooks/guard_root_scan.py` and merge its
  PreToolUse entry into your `.claude/settings.json`; merge the timing entry of
  `docs/GOTCHAS.md` into your copy; `scripts/close_worker.sh` and `scripts/doctor.sh` come with sync.

- **`guard_boundaries.py`** (#151, #264, #265, #268): its docstring and the overlay README say that writes
  through the shell get no early warning; `scripts/check.sh` stays the gate. It now also sees a
  NotebookEdit and folds case on Windows and macOS. **ACTION:** re-copy
  `.claude/hooks/guard_boundaries.py` and change its PostToolUse matcher in
  `.claude/settings.json` from `Edit|Write` to `Edit|Write|NotebookEdit`.

- **Kit check (`scripts/check_kit.py`, kit-only):** each test module, each shard of a long module
  and each locale suite runs as its own unit, one unit per two CPUs; a test module without a
  count in `REQUIRED_SUITES` fails the check, and the count is checked before the run. A failing
  unit prints only its FAIL/ERROR blocks and the count, not a line per passing test. Discovery
  reads no Windows-only stat names, so POSIX Python 3.11 runs every suite. `test_doctor` and
  `test_spawn_worker` scale their wall-clock bounds with `MYAGENTKIT_TEST_TIMEOUT_SCALE`, which
  check_kit raises by at most 4 while units run side by side; a module this host does not run
  gets a NOT RUN line, no unit. The acceptance unit runs no nested gate self-test; its review
  cases call `scripts/review.sh --self-test` directly. A project-owned kit file (core/, setup/,
  overlays/ without a `KIT-OWNED` header) changed since the last release tag fails the check
  unless an ACTION item of the newest version names it; NOT RUN without a tag. CI runs the kit
  check only. (#146 in part, #111, #96, #134)
  Kit maintainers (not a project step): tag each release `vMAJOR.MINOR` at the release, when
  its CHANGELOG heading is renamed from Unreleased. After the tag the check reads the next
  cycle's ACTION items under the `## Unreleased` heading; only a newest versioned heading equal
  to the tag turns it red.

- **Kit check in two tiers** (`scripts/check_kit.py`, kit-only; #146, kit-self-checks findings
  6 to 8). The default run is the fast tier (structural checks, unit and fixture suites, within
  600 s on a 20-CPU Windows host), for every change and before a push; `--slow` runs the slow
  tier alone (`SLOW`: acceptance, bootstrap, the review bridge, doctor and the worker-spawn
  suites), `--all` runs both, and a release runs `--all`. CI runs the two tiers as parallel jobs
  (`MYAGENTKIT_TEST_TIMEOUT_SCALE: '3'`). A change that touches a slow-tier unit's area runs
  `./scripts/check.sh --slow` before its push (CONTRIBUTING). Each unit has a cap and each tier
  a budget (`CAPS`: fast 480/600 s, slow 3000/3600 s, times the scale); the budget is enforced
  during the run: a unit over its cap, or still running when the budget ends, is stopped and
  named with its seconds, a queued unit does not start, and the run is red with a summary
  before CI's `timeout-minutes`. Each unit leads its own process group on POSIX: a cap kill,
  SIGTERM/SIGINT and a closed terminal (SIGHUP, in `scripts/check.sh` and the runner) stop the
  unit's test processes too. A cancel stops each running unit at once instead of letting it run
  its next test, and on native Windows ends the unit's whole process tree (`taskkill /T`). A
  local Windows run now runs `test_bootstrap` (slow tier) instead of NOT RUN. The
  `test_gate_checks` count drops by one on a host that cannot make symlinks, whose link test is
  a declared skip. A failed `git diff` in the ACTION check prints a KIT CHECK: FAIL
  line, not a traceback (#134 follow-up). Test fixes: test_bootstrap names its global git config
  with `GIT_CONFIG_GLOBAL` (#147 follow-up); test_spawn_codex and test_worker_paths_windows scale
  their bounds; test_overlay_permissions writes with an encoding; stale guard counts in
  `REQUIRED_SUITES`; test_bootstrap's kit copies leave out the checkout's top-level `.claude`
  and `.myagentkit` (an old worktree's scratch folder denied access, WinError 5),
  `test_the_bg_host_needs_no_tmux_script` runs on native Windows instead of an undeclared skip,
  and the bridge's partial-timeout case scales its limit (one second ran out before the fake
  printed); test_kit_runner's units-at-once case proves the overlap with marks each unit waits
  for instead of timestamps (a loaded host started one unit after the other had ended), and
  test_spawn_codex's wait for the held launch scales too.

- **The review bridge test of every record outcome no longer times out on a loaded host:** only
  its timeout cases keep the 2 s bound (#95 follow-up). `codex_bridge.py`'s verdict rule is one
  function, `verdict_refused()`; its forms are tested in-process instead of one full wrapper
  run each.
  **ACTION:** re-copy `scripts/test_claude_bridge.py` and `scripts/codex_bridge.py`.

- **Kit CI and test isolation** (ci, redfix): CONTRIBUTING's release rule: a release is
  announced only after CI is green on every job of the release commit (`gh run list`,
  `gh run view`); red means not released. Job time limits were raised because a limit that cuts
  a run short reads as red; the two-tier entry above supersedes the numbers: each job runs one
  tier, `timeout-minutes` 40 (fast) or 190 (slow). `scripts/check_kit.py` exports
  `GIT_CONFIG_GLOBAL=<devnull>` and `GIT_CONFIG_NOSYSTEM=1` for every unit and test, and names
  the temp folder by its long path on Windows. The review suite's fixtures write their own
  ignore rules instead of copying a project's `.gitignore` (a project ignoring `.env` failed the
  kit's secret-file tests), the mode-change test sets the file mode, and a failing shard's output
  is written with `errors='replace'` so a cp1252 console cannot hide it. POSIX and Windows test
  fixtures fixed from CI run 39065623063. The kit's own CI clones the whole history
  (`fetch-depth: 0`), so the ACTION check runs there once a release tag is pushed. (#95, #96,
  #147, #91, #92, #163 in part)
  Kit maintainers (not a project step): set `master` branch protection with the twelve CI jobs
  (Ubuntu, macOS and Windows × Python 3.11 and 3.14 × the fast and slow tier) as required status
  checks (GitHub settings; the workflow cannot do it).
  **ACTION:** re-copy `scripts/test_claude_bridge.py`.

- **Binding research report on the kit's own checks:** `docs/research/kit-self-checks.md`
  (gate self-test, acceptance suites, test-time norms and tiers); every proposal about check_kit,
  the gate self-test, test tiers or time budgets cites a numbered finding of it (decision 22).

- **A kit upgrade commit is reviewable** (#114, decision 59). `review.sh --reviewer claude
  --commit <sha> --kit-verified [--kit DIR]` verifies by hash each changed `KIT-OWNED` file that
  equals the kit's after git's line-ending normalisation, with the kit's mode and no mode change,
  at the recorded `docs/kit/.kit-commit` (on a release tag `v*`, never older than the parent's),
  and reviews only the rest; line-ending churn is checked over every changed file. The verified
  list is in the evidence and the chain record. The Claude adapter reviews a `--commit` that is
  not HEAD from an archive of that commit; a `--commit HEAD` still needs a clean checkout. The DIFF_LIMIT refusal names its size and the
  largest files. `sync-kit.sh` and `docs/kit/UPGRADE.md` print the review line once the kit
  commit is recorded. `install.sh` fetches the release tags with the kit (`--tags --force`), so
  `--kit-verified` finds the release tag in `~/.myagentkit/kit`; a cache from an earlier install
  gets them on its next run. **ACTION:** add the "Kit upgrade commits" section to your copy of
  `docs/REVIEW_RUNNING.md` and its pointer line (end of "Invariant") to `docs/REVIEW_GATE.md`.

- **The review companions move as one set** (#114, #118 follow-up; `docs/DEV_SETUP.md`, the
  companion list). They carry no `KIT-OWNED` header, so the sync copies none of them. The v0.12
  adapters call `agent_process.run(..., watch=...)` and rely on the v0.12 dispatcher's tier and
  effort rule, `past_ok` and `--kit-verified`: new adapters beside a v0.11 `agent_process.py` or
  `review_dispatch.py` fail every review with a `TypeError` traceback, no evidence and no usage
  record; and the synced `usage_summary.py` imports `chain_failure` from the new
  `claude_bridge.py`, so it fails on import until the re-copy. **ACTION:** right after the sync,
  copy the whole set from the kit's `core/scripts/` into `scripts/`: `review.sh`,
  `review_dispatch.py`, `claude_bridge.py`, `codex_bridge.py`, `agent_process.py`,
  `agent_usage.py`, `codex_quota.py`, `owns_check.py`, `review_test_support.py` and the tests
  `test_claude_bridge.py`, `test_agent_usage.py`, `test_codex_quota.py`, `test_owns_check.py`,
  `test_agent_cost.py` and `test_context_buckets.py`; re-apply your default reviewer and model
  pins in `review.sh`.

- **The reviewer is at least the author's tier, at the author's effort** (#290, #181, #179,
  #225; owner decisions 63 to 66; `scripts/review_dispatch.py`). Reviews that ran in v0.11 are
  refused (exit 2) with this release:
  - `MYAGENTKIT_AUTHOR` naming no model tier (`claude`, `codex`, `anthropic`, `openai`,
    `claude-code`) is refused; an alias or vendor id (`opus`, `us.anthropic.claude-opus-5-v1:0`,
    `claude-3-5-sonnet-20241022`) counts as the tier it names.
  - A weaker tier than the author's runs only as a shadow opinion (`REVIEW_SHADOW=1`), never as
    the required review. The top tier (Fable; a Codex astra model) reviews its own tier in a
    fresh session. Any other tier's own-tier review is refused unless
    `REVIEW_SAME_TIER_EXCEPTION=<reason>` names the owner's exception, which needs
    `REVIEW_RISK=high` and effort high, holds one round per label and focus, and is recorded
    (`same_tier_exception`). The v0.11 solo setup of an Opus author reviewed by Opus needs it.
  - The review runs at the author's effort (`MYAGENTKIT_AUTHOR_EFFORT`; unset counts as high),
    high at most; an effort named below it is refused.
  A used-up quota switches to another tier of the author's family; a round 2 over the fix
  commits keeps its label and counts, so a round 3 is refused; an unreadable checkout after a
  review fails the chain and the round still counts.
  **ACTION:** wherever the lead or a brief sets `MYAGENTKIT_AUTHOR`, set it to the author's model
  id (`claude-opus-5-5`, not `claude`) and set `MYAGENTKIT_AUTHOR_EFFORT` to the author's effort;
  pin a reviewer of the author's tier or above in `scripts/review.sh`; a solo plan with no
  stronger tier runs a high-tier change's review with `REVIEW_SAME_TIER_EXCEPTION` and
  `REVIEW_RISK=high`. Merge the rule into your copies of `docs/REVIEW_GATE.md` ("Invariant", the
  effort rule), `docs/REVIEW_RUNNING.md` and `docs/WORKFLOW.md` ("Model routing", rule 7).

- **A review watches its checkout and names what follows it** (#118, #121, #117, #120, #197,
  #198, #277, #280). Once a minute a review hashes the checkout and stops the paid reviewer at
  the first change, as `stale_checkout`: edit nothing in the reviewed checkout while its review
  runs. The chain record names the attempt that follows (`next_attempt`: a capacity retry, a
  quota switch, a fallback), and a review is finished only without it; it also gains
  `top_tier_review`, `same_tier_exception` and `checkout_unverified`, and a usage record's
  `automatic_retry` may be `null`. A Codex review loads no project doc as instructions
  (`project_doc_max_bytes=0`); `AGENTS.md` stays evidence the prompt names. An Accept that its
  own findings contradict is read as the stricter verdict in both adapters: Reject when an item
  leads with Critical or High, also written `High, x.py:1`, `High in x.py:1` or `High
  severity:`. A finished reviewer whose descendant holds the output pipe ends after 5 s instead of
  as a timeout. Quoted backend
  values are unquoted. The scripts come with the companion set above; `docs/USAGE.md` and
  `docs/GOTCHAS.md` (project-owned docs, entry below) describe the records.

- **`Owns:` lines follow git's glob rules** (#206; `scripts/owns_check.py`). `*` stays within
  one folder and `**/` spans folders; a line inside a code block is skipped; a second `Owns:`
  line or an unclosed code fence is a usage error (exit 2). A brief that passed in v0.11
  (`Owns: src/*.cpp` covering `src/a/b.cpp`) is refused by `review.sh`. **ACTION:** in open
  briefs and your brief templates, rewrite a `dir/*.ext` meant recursively as `dir/**/*.ext`,
  and keep one `Owns:` line per brief; `docs/HANDOFF.md` item 2 states the rule (merged with the
  project-owned docs, entry below).

- **The working-mode record moves to `.myagentkit/`** (#272, #256, #257;
  `scripts/working_mode.py`, synced). The record and its lock are `.myagentkit/mode` and
  `.myagentkit/mode.lock`, ignored with the private store; temporary copies are written and
  fsynced there. `.claude/mode` is no longer read, and without the new record the mode comes from
  `docs/STATE.md`. Only a key-shaped `Working mode:` line counts, and both refusals name the
  lines. **ACTION:** delete `.claude/mode` and `.claude/mode.lock` (`git rm` the record if it
  was committed), remove the `/.claude/mode.lock` rule from your `.gitignore` (the
  `/.[Mm][Yy][Aa][Gg][Ee][Nn][Tt][Kk][Ii][Tt]/` rule of the kit's `core/.gitignore` covers the
  new place), and run `scripts/working_mode.py NAME` again if the mode is not the one
  `docs/STATE.md` names; take the overlay's `.claude/rules/state.md` (Read then Edit, never the
  `Working mode:` line).

- **Gate changes beyond the self-test** (`scripts/check.sh`, taken whole by the self-test
  entry's ACTION). `docs_always_build` names the documents a build or test reads, so a commit
  changing one builds although it changes only documentation (#97). The commit gate prints
  `NOTE [scan]: the gate checked the working tree; these paths are not what this commit records`
  for unstaged or untracked paths (#109). The `## Module map` names modules only in table rows
  and list entries, HTML comments cut out, and a module may be named by its path from the top
  (#274, #88, #141). **ACTION:** name each module of your architecture file's `## Module map` in
  a table row or a list entry: a module named only in prose or a comment fails `check.sh`.

- **doctor and fix_crlf** (synced; nothing to copy). `scripts/doctor.sh` reports
  MISSING for a project hook or `scripts/doctor.project.sh` without a `#!` line, a `.githooks`
  layout that runs no Git LFS on a project that uses LFS, a hook the committed
  `.claude/settings.json` does not register or registers without its file, and the Unity
  editor, `cygpath` or `wslpath` the Unity gate needs; it prints a NOTE for a missing
  ShellCheck and for an empty `.claude/worktree-disposable` (#165, #164, #101, #145, #216,
  #155). A machine ready for v0.11 may show new MISSING lines: each names its fix.
  `scripts/fix_crlf.sh` refuses a file with an edit beyond line endings, changing nothing, and
  lists what it staged (#207).

- **Claude Code overlay hooks and settings** (#83, #116, #138, #139, #174, #209, #210, #214,
  #289). `py.sh` keeps the interpreter that passed its probe in the user's cache folder (about
  0.5 s saved per hook call on native Windows) and refuses a missing hook file: a guard fails
  closed, the root-scan and secret-file guards open; a cached interpreter whose hook exits with a
  code other than 0, 1 or 2 is not run a second time on an emptied input (a guard fails closed).
  `gate_on_stop.sh` no longer reads a file name starting `160000 ` as a submodule (the gate ran
  on every new turn; the self-test entry's ACTION item 3 takes it). The context band is also
  named after a tool call, through `progress_reminder.py`; a worker session is not nudged and a
  sub-agent
  never spends the lead's nudge. `plain_report.py` bounces a final message that leaves an owner
  question in chat text and asks for one line, not a resend. Sub-agents are back on the
  five-minute prompt cache (long jobs go to `spawn_worker.sh` sessions). `after_compact.txt`
  points at WORKFLOW's "The rules in brief". The three blocking guards get a 30 s timeout.
  `.claude/worktree-disposable` documents `/NAME` (the root folder only) and the
  committed-versus-working rule. **ACTION:** copy whole from the kit's
  `overlays/claude-code/files/.claude/hooks/` (hooks are not synced): `py.sh`,
  `context_size.py`, `progress_reminder.py`, `plain_report.py` and `after_compact.txt`; merge
  the header comment of the overlay's `.claude/worktree-disposable` into yours, keeping your
  entries. In `.claude/settings.json`: remove `subagentPromptCacheTtl` and the `env` entry
  `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL`; add `"worktree": {"bgIsolation": "none"}`; raise
  the `timeout` of the `guard_destructive_git.py`, `guard_private_email.py` and
  `guard_worker_route.py` entries to 30; then commit it (worktree workers run the committed
  file).

- **The project's CI checks every commit of a pull request** (#135;
  `.github/workflows/ci.yml`). Its checkout fetched one commit, GitHub's own merge commit on a
  pull request, which carries no `Done:` trailer, so no commit of the pull request was checked
  and the strong-review reminder read no history. **ACTION:** add `with: fetch-depth: 0` to the
  `actions/checkout` step of your `.github/workflows/ci.yml`.

- **Project-owned docs** (#132, #142, #112, #150, #131, #107, #289). The kit's docs say what
  the code does: risk tiers and the critical-work mark, model routing in WORKFLOW's two tables,
  a worker's notes in `docs/worktree-notes/<branch>.md`, a brief that quotes its environment, a
  report's last question through the question tool, the glossary's new terms. **ACTION:** merge
  the kit's v0.12 changes into your copies of `docs/COMMUNICATION.md`, `docs/GLOSSARY.md`,
  `docs/HANDOFF.md`, `docs/USAGE.md`, and of the other project-owned files the entries above
  name; `"$KIT/sync-kit.sh" . --merge` merges every project-owned file under the kit's `core/`
  and lists each as `merged:` (`docs/UPDATING.md`); overlay files are copied by hand as their
  entries say.

## v0.11 — 2026-10-09

- **Python minimum raised to 3.11:** doctor, gate launchers, syntax checks and CI require Python 3.11+.
  **ACTION:** projects on Python 3.10 must upgrade to 3.11+ before updating the kit.
  Python 3.10 reached end of life on 2026-10-01 ([Python version status](https://devguide.python.org/versions/)).

- **Core docs:** the sources of the always-loaded AGENTS.md rules moved to WORKFLOW,
  "Where the constitution's rules come from". AGENTS.md reads ARCHITECTURE.md only when a
  task crosses a module boundary; a reviewer still reads it every time.
- **WORKFLOW Worker cost:** the hit target is an alarm, not a target (median of the first
  ten workers as the baseline, `cWrite>TTL`). The cost screen is `/usage`. 4 GB and
  two-at-a-time are starting values. Workers use the same 200k band. The watcher gets a
  timeout when the lead runs unattended. The idle-notice subscription facts are recorded.
  The worker review runs through nested sub-agents.
- **COMMUNICATION:** 'away' means the owner said so or 45 minutes without a reply
  (owner's choice). The progress reminder stops after three.
- **Backend files** live outside the repository (`MYAGENTKIT_BACKENDS_DIR`,
  `%APPDATA%\myagentkit\backends`, `~/.config/myagentkit/backends`). The old
  `.myagentkit/backends/` is read while projects move. **ACTION:** a project with
  `.myagentkit/backends/NAME.env` moves the file to the backend folder.
- **Closed audit findings:** the `Done:` history gate reports historical mentions in
  `docs/audits/*.md` as notes. Live state and review reports still fail. The commit-message
  hook still rejects a new closing trailer whose staged audit names that task.
  **ACTION:** merge the updated Done-history section of `core/scripts/check.sh` and the
  audit paragraph of `core/docs/WORKFLOW.md` into existing project-owned copies.
- **Windows directory measurement:** native Python 3.13 and `CreateDirectoryW` created
  every tested directory length from 247 to 300 characters on the test host, so the docs
  do not claim a universal 248-character directory limit.
- **Prompt consistency:** review and proposal prompts share one verification rule in
  `claude_bridge.py`; the Codex adapter imports the common reviewer reading list.

- **Worktree hooks and context visibility fixed** (`spawn_worker.sh`, `watch_workers.sh`,
  `.claude/hooks/context_size.py`, `core/docs/WORKFLOW.md`, `core/docs/HANDOFF.md`). Worktree
  workers keep project hook files, including when settings are untracked, without dirtying
  Git status. Settings accept UTF-8 BOM and Windows paths; merged settings are validated before
  creating a locked worktree. Every spawn clears stale context state. The `.state` line carries
  `context_tokens=N`; `watch_workers` computes the band and shows both the context size and band.
  Live pane context takes precedence over an older snapshot; notices fire once per band and
  honour `--context-warn`. Copied hooks use a self-ignoring `.claude/hooks/.gitignore`,
  without changing the shared `info/exclude` or hiding the lead's untracked hooks.
  Spawn records its exact bytes in `.myagentkit/workers/NAME.hooks-ignore-spawned`.
  Close sets it aside for the audit only while it matches that record byte for byte.
  The watcher uses the 200k context line when an older context hook or missing Python
  cannot answer. **ACTION:** sync the overlay (the sync writes its KIT-OWNED scripts; copy the
  changed hook files whole from the kit) and re-spawn existing workers.
- **Batch 10: kit checks, plugin release and review self-tests** (`scripts/check_kit.py`,
  `core/scripts/check.sh`, `core/scripts/test_claude_bridge.py`, `scripts/clean_worktrees.sh`,
  `scripts/close_worker.sh`, `tests/test_kit_runner.py`, `tests/test_selftest_status.py`,
  `plugins/myagentkit/`). The self-test's scratch folder no longer follows an inherited
  `work` variable. The kit check names a missing Turkish locale, reads `locale -a` as UTF-8,
  repeats the early checks' NOT RUN lines under the summary, and no longer takes a `+++`
  line inside a hunk for a file header. The plugin's version is now the kit's (0.11.0),
  and the kit check compares it with this file and runs `claude plugin validate --strict`.
  Kit maintainers (not a project step): after the push, run `claude plugin update` in each
  dogfood project (leeway, labricore-web) and verify the new version arrived; until now
  plugin.json said 0.1.0, so an install from GitHub may never have updated. The gate runs ShellCheck (SC2028, SC2086)
  where it is installed. **ACTION:** a project with ShellCheck installed may go red on its
  own scripts; fix or disable each with a reason. clean_worktrees and close_worker no longer
  keep every worktree under core.autocrlf. The review self-test divides bridge and preflight
  cases between two isolated parallel processes and rejects incomplete or duplicate coverage.
  A parent interrupt or exception stops both shard process trees before propagating.
  ShellCheck receives empty `SHELLCHECK_OPTS`, so ambient severity options cannot suppress
  mandatory SC2028/SC2086 diagnostics. The extracted existing-file boundary example passes its
  Python launcher as quoted arguments and prints the disposable baseline's diagnostics on failure.
  The Windows nested self-test bound is 1800 s; it measured 1357-1563 s on the kit host.
  ShellCheck includes extensionless sh, bash, dash and ksh hooks, including env shebangs,
  and excludes non-shell hooks. **ACTION:** merge the ShellCheck hook selector from
  `core/scripts/check.sh` into existing project gates.
- **Reviewer manual-check verdict instructions** (`core/scripts/claude_bridge.py`,
  `core/scripts/codex_bridge.py`, `core/scripts/test_claude_bridge.py`, plugin runtime).
  Both reviewer prompts classify NOT RUN and "could not verify" lines as manual checks
  requiring Accept with Manual Checks. A plain Accept ends with None. under Manual checks.
  The evidence validator still refuses a plain Accept carrying a check. **ACTION:** none.
- **Setup interview, feedback permissions and line-ending repair** (`setup/INTERVIEW.md`,
  `setup/RESEARCH_PROTOCOL.md`, `plugin/commands/kit-feedback.md`, `handoff.md`,
  `cross-review.md`, `core/scripts/fix_crlf.sh`, `core/docs/DEV_SETUP.md`, patterns and skills).
  Setup interview re-sourced: BOOTSTRAP_NOTE items become a status list in STATE.md with
  evidence; the reviewer is pinned by its full model id, never an alias; Q9 names Assisted-by
  and the attribution setting; Ponytail's numbers come from its README (latest version kept,
  owner's choice); module_roots is asked; Phase 5 goes through /myagentkit:kit-feedback. The
  research protocol's baseline is a date and the CLI versions. /myagentkit:kit-feedback
  pre-approves only read-only commands, so sending meets the permission prompt; a PR needs its
  issue first; scrubbing starts with a mechanical pass. The line-ending repair is
  `scripts/fix_crlf.sh` (kit-owned, synced; it also repairs `.githooks/<name>.project`).
  Patterns and skills carry their sources (KARARLAR B14, D07, B10 inv3#3, B12 inv3#186,
  D08 inv3#123, D09 inv3#176, D10 inv3#97). The repair skips files with -text/binary attributes
  and content Git detects as binary; kit-feedback pre-approves only exact read-only command
  forms. DEV_SETUP now calls the tested, kit-owned `scripts/fix_crlf.sh` repair; handoff and
  cross-review no longer pre-approve arbitrary Git commands. **ACTION:** `docs/DEV_SETUP.md`
  is project-owned, so sync-kit.sh never rewrites it: in section 1, "Wire the commit gate",
  replace the embedded line-ending repair program with the `sh scripts/fix_crlf.sh`
  paragraph from the kit's `core/docs/DEV_SETUP.md`. Update the plugin to the same kit
  version so kit-feedback, handoff and cross-review carry the tightened permissions.
  Sync ignores both no-action spellings. The update guide describes the existing ACTION
  listing. Line-ending repair stages only files it rewrites.
- **Source claims corrected after the web source check** (`core/docs/WORKFLOW.md`, `USAGE.md`,
  `DEV_SETUP.md`, `core/scripts/agent_usage.py`, `claude_bridge.py`, `context_buckets.py`,
  `docs/worker-cost-setups.md`, `.claude/hooks/py.sh`). Correct eight source claims about Claude
  Code cache lifetimes, quota messages, session cost statistics and hook blocking, Git
  sparse-checkout support, and context-analysis cuts; classify weekly and Opus/Sonnet plan
  limits as exhausted quotas. Kit docs and scripts only; nothing to do in a project.
  The top-up source check corrects subagent section labels and refactoring evidence, removes
  the drift citation, and narrows idle notices, MCP hosts, quota comments and clarification
  claims. **ACTION:** none.
- **Core templates re-sourced** (`core/docs/ARCHITECTURE.md`, `PHASES.md`, `PROJECT.md`,
  `STATE.md`, `GOTCHAS.md`, `STRONG_REVIEW.md`). ARCHITECTURE.md aims for about 100 lines, says
  what it holds and finds a contract change's consumers mechanically; PHASES.md asks what the
  phase must find out; PROJECT.md has a `Web contact` line, supersedes rather than changes a
  DECIDED item, stamps `Decided: date, approved by`, and an OPEN item stops only that item;
  GOTCHAS.md says how to recover a dropped stash or staged content, corrects the WSL `.exe`
  claim (unverified), names the guard hooks, and gains "An incremental build misses its
  always-run inputs"; sources beside each rule (KARARLAR B09, B10, B11, D03, D05, D08, D09,
  D10; owner answer 9). **ACTION:** these templates are project-owned, so sync does not touch
  them: add `**Web contact:**` near the top of `docs/PROJECT.md` (the e-mail guard points at
  it), change the PROJECT.md rights row to "Supersede ...", optionally copy the new GOTCHAS
  paragraphs.
- **Git and e-mail guard hooks** (`.claude/hooks/guard_destructive_git.py`,
  `guard_private_email.py`, `guard_boundaries.py`, `py.sh`, `.claude/settings.json`,
  `core/.githooks/pre-commit`). The destructive-git hook keeps the base rule as a floor (a
  loss-certain pattern anywhere in the command text, here-document bodies included, is refused
  while the tree is dirty) and reads the command as the shell does on top of it (`git -C`,
  `--git-dir`, `GIT_DIR=`, aliases, `cd` in any form adds the folder it reaches; the caller's
  folder is always checked). It refuses, whatever the tree's state, `stash drop/clear`, a force
  push without a lease (`--force`, `-f`, `+ref`, `--mirror`, `--delete`, a bare
  `--force-with-lease`), `remote set-url/add`, amending a pushed commit and a skipped gate
  (`--no-verify`, `commit -n`, `-c core.hooksPath=`, `--no-gpg-sign`); `clean -n`, `restore
  --staged` and a lease push pass. Guard hooks fail closed: `onFailure: block` (Claude Code
  2.1.295+), an unreadable payload blocks, `py.sh` with no Python blocks a guard. New
  `guard_private_email.py` refuses a WebFetch, WebSearch or web-client Bash call carrying git's
  `user.email` or an address in `MYAGENTKIT_PRIVATE_EMAILS` (owner decision 2026-10-15).
  `.claude/settings.json` sets `attribution` empty; `guard_boundaries.py` matches a Windows
  path; `pre-commit` no longer suggests `--no-verify`. Sources: KARARLAR B10 inv3/(g), B12
  inv1#28, inv3/(g), D09 inv3#5/#9/#11/#12, inv1#29/#233, inv3#74, D07 inv3#108, BACKLOG B2.
  The git guard rejects git-bearing interpreter arguments and input regardless of flags.
  It allows project-contained `.githooks` wiring only in a plain command without directory
  routing, resolving containment from the hook's own working directory.
  **ACTION:** copy the overlay's hook files whole from the kit (including the new one) and
  merge its `.claude/settings.json` by hand (sync-kit.sh writes neither); update Claude Code to
  2.1.295 or later; if the Claude account's e-mail differs from git's `user.email`, set
  `MYAGENTKIT_PRIVATE_EMAILS` in the user-level settings `env`.
- **Review gate rules** (`docs/REVIEW_GATE.md`, `docs/REVIEW_RUNNING.md`, `docs/WORKFLOW.md`,
  `/myagentkit:cross-review`, the review skill). The independence rule is written once, in
  REVIEW_GATE "Invariant" (solo: another tier, never the author's; cross: the other family);
  the other documents point there. The risk tier is the higher of the changed files' row and
  the lead's proposal, and a working mode never lowers it; two focus reviewers only at high,
  where the owner gets a ten-line summary and the diff before the merge. A doubt the reviewer
  cannot tie to a file, line and input goes under Manual checks; the Low cap lives only in
  `REVIEW_PROMPT`; a Medium is fixed in the round when a test can verify it, otherwise an
  issue; a gate finding goes back to the author's side. `/myagentkit:cross-review` is an
  extra review the owner asks for; the review its tier requires starts without asking. A diff
  past about 400 changed lines gets a split hint (KARARLAR B01, B02 inv2#10/#34, D03 inv1#104,
  D04, D06 inv1#37/#163; BACKLOG B14, B15).
  **ACTION:** merge the kit's changes into `docs/REVIEW_GATE.md`, `docs/REVIEW_RUNNING.md`,
  `docs/WORKFLOW.md` (`sync-kit.sh --merge`, from v0.10 with the `--base` the upgrade
  checklist below names, or by hand; they are project-owned).
- **Reminder hooks, labels, context counters, commit-msg** (`.claude/hooks/plain_report.py`,
  `.claude/hooks/progress_reminder.py`, `scripts/context_buckets.py`, `.githooks/commit-msg`).
  Progress reminders stop after three nudges per silent interval and reset on visible text or
  compaction; a tool result past the read tail no longer loses a visible line (the hook reads
  from the offset it saved). Final-message labels share the commit task grammar and are
  registered only from a task-id position in STATE/BACKLOG, never from prose, so UTF-8,
  SHA-256, win32 or x86 pass and every id the project names is caught whatever its prefix
  length; code fences need matching characters and lengths, indented and quoted fences
  included. Context measurements include the last selected request's refusals, add 5/30-request
  slices, and show a separate informational correction-phrase counter. commit-msg refuses a
  bracketed `Assisted-by: LLM [Claude]` trailer; the owner's opt-in is regression-tested
  (KARARLAR B08 inv1#253, B10 inv3/(f), inv3#7, inv1#93, inv2#151, B07 inv2#131/#132, D07
  inv3#108 b; BACKLOG B5, B13).
  The plain-report hook reads task files once per message and accepts project-owned regex
  patterns without mistaking unregistered products for task ids. Invalid patterns leave
  built-in checks and other valid project patterns working. **ACTION:** copy the updated
  `.claude/hooks/plain_report.py`, merge `core/docs/COMMUNICATION.md`, and keep project
  patterns in `.claude/plain_report_labels.json` instead of the synced commit hook.
  **ACTION:** copy the overlay hooks whole from the kit; the sync writes
  `scripts/context_buckets.py` and `.githooks/commit-msg` (a `conflict:` line that calls the
  file the project's, such as a `commit-msg` of your own: move yours aside first, a hook to
  `.githooks/<same name>.project`, as the sync says; only an earlier kit copy without the
  KIT-OWNED header is replaced by the kit's file whole).
- **Usage and cost measurement** (`scripts/agent_cost.py`, `scripts/usage_summary.py`,
  `docs/USAGE.md`, `docs/CODEX.md`, `docs/worker-cost-setups.md`). The worker cost analysis reads
  each cache write's recorded lifetime (one hour or five minutes) instead of treating every write
  after five minutes as an expiry; an 80% hit rate is an alarm, the owner's choice. The review
  summary keeps shadow runs out of real-review rates, counts `rate_limited` and
  `quota_exhausted` (and old `quota`) failures, prints author/reviewer pairs, and shows a Wilson
  95% interval with the sample floor (30 decided findings, ten rated rounds; the owner's choice).
  A later answer file replaces an earlier one per label and focus instead of counting the same
  answers again (KARARLAR B03, D06 inv2#45/#55/#107/#108/#54/#12, inv1#161/#172, D01 inv1#191;
  BACKLOG B9, B17). **ACTION:** the sync writes the two scripts (a `conflict:` line that calls
  the file the project's: move yours aside first, as the sync says; only an earlier kit copy
  without the KIT-OWNED header is replaced by the kit's file whole); merge `docs/USAGE.md`
  (`sync-kit.sh --merge`, from v0.10 with the `--base` the upgrade checklist below names, or
  by hand).
- **Review tooling: bridge, dispatcher, usage** (`scripts/review.sh`, `scripts/claude_bridge.py`,
  `scripts/codex_bridge.py`, `scripts/review_dispatch.py`, `scripts/agent_usage.py`,
  `scripts/agent_process.py`, `docs/REVIEW_GATE.md`, `docs/REVIEW_RUNNING.md`, `docs/USAGE.md`,
  `docs/GOTCHAS.md`). The reviewer runs only the narrow test that proves a finding, never the
  full suite; the lead's gate runs it. Quota failures split into `rate_limited` (Codex retried
  twice, the tool's delay or 600 s, doubled) and `quota_exhausted` (a used-up Codex quota switches
  the role to Claude, recorded); an authentication error never fails over. With
  `MYAGENTKIT_AUTHOR` set, review.sh refuses a reviewer of the author's tier and records the
  author. A secret-looking file in scope (`.env*`, `*.pem`, `*.key`, `.npmrc`, `.netrc`,
  `credentials*`, `.dev.vars`) stops a review unless `--allow-secret-file PATH` names it, one
  path per flag. Secret checks cover changed paths and list every refusal. Review fallback
  uses the resolved backend model family and refuses an unknown author family or the
  author's family. Capacity waits stop at the retry bound with the provider's requested time.
  Backend files live outside the repository (`MYAGENTKIT_BACKENDS_DIR` or the
  user's config folder); the old `.myagentkit/backends/` is read during the move. A high-effort
  Codex review defaults to a 3600-second limit; doctor reads `claude --version` (2.1.248 or
  newer) before `--help` (KARARLAR D04 inv2#44/#126/#85, B01 (1)/(6), B12 inv2#106/#81, D07
  inv3#103, D09 inv2#80/#99/#100, B03 inv2#31, B10 inv2#113, B02 inv2#158, inv2#104/#115/#144).
  **ACTION:** copy `scripts/review.sh` (keeping your project configuration, its PROJECT-OWNED
  CONFIGURATION block) and the review and usage scripts above whole from the kit;
  merge `docs/REVIEW_GATE.md`, `docs/REVIEW_RUNNING.md`, `docs/USAGE.md`, `docs/GOTCHAS.md`
  (`sync-kit.sh --merge`, from v0.10 with the `--base` the upgrade checklist below names, or
  by hand); move `.myagentkit/backends/*.env`
  to the user's config folder (or set `MYAGENTKIT_BACKENDS_DIR`).
- **Gate, doctor, boundary example** (`scripts/check.sh`, `scripts/doctor.sh`,
  `.claude/hooks/gate_on_stop.sh`, `docs/DEV_SETUP.md`, `docs/STRONG_REVIEW.md`, `.gitattributes`).
  The commit gate's self-test no longer writes in the tree: a review can share the worktree.
  doctor tells (NOTE) a shadowed grep, Python 3.10 past EOL and Claude Code older than 2.1.295.
  The Stop hook gates the session's project after a cd. check.sh: module folders must be in
  ARCHITECTURE's module map; strong review due after 10 days or 20 tasks; NOTE when STATE.md
  drops a lesson line. DEV_SETUP recommends the gate as a required CI check; `.gitattributes`
  starts with `* text=auto` (KARARLAR B02 inv2#39/#104/#143/#146/#161, D03 inv1#27/#106,
  inv2#156/#166, D05 inv1#76, B11 inv1#119/inv2#152, B10 inv1#239, D04 inv2#83).
  The module-map gate compares whole module names. **ACTION:** merge the module-map section
  of `core/scripts/check.sh` into existing project-owned gates.
  **ACTION:** the sync writes `scripts/doctor.sh`; copy the overlay Stop hook whole from the
  kit; merge `scripts/check.sh`, `docs/DEV_SETUP.md`, `docs/STRONG_REVIEW.md`
  (`sync-kit.sh --merge`, from v0.10 with the `--base` the upgrade checklist below names, or
  by hand); add `* text=auto` to the project's `.gitattributes`
  by hand (project-owned) and fill `module_roots` in `scripts/check.sh` if the project has modules.
- **Working modes and model routing** (`scripts/working_mode.py`, `docs/WORKFLOW.md`,
  `/myagentkit:mode`, `/myagentkit:cross-review`, `setup/INTERVIEW.md`, `docs/CODEX.md`).
  Working modes have English names only (solo, cross, saver); the mode helper finds a
  pre-v0.11 project by the kit version its sync recorded (`docs/kit/.kit-version`) and prints
  the ACTION, no longer by counting WORKFLOW's table rows. Model routing: one cost-per-task
  sentence; a weaker tier never reviews a high-tier or critical change; Codex xhigh only as the
  lead's reasoned exception; rule 7 names the reviewer in solo, in cross and when Codex is
  blocked; on a plan without Fable, Opus reviews Opus's high-tier or critical work in a fresh
  session, high effort, one round, and the owner's diff read is the second check (owner
  decision); saver keeps the cross rules at high and critical tier, and its `after:` return is
  the owner's standing permission. INTERVIEW Q8 keeps `worker.md` (LONG_JOBS none) and deletes
  only `spawn_worker.sh` (KARARLAR B05, B06, D05 inv2#137/inv3#180, D06 inv3#26, D10
  inv1#140/#150/inv2#136/inv3#181, B12 inv3#171).
  **ACTION:** replace the "Model routing" and "Working modes, by name" sections of
  `docs/WORKFLOW.md` with the kit's; a STATE.md "Working mode:" line written by hand with a
  Turkish name must be rewritten to its English name (the helper now refuses it).
- **Review budget and round-limit fixes** (`scripts/claude_bridge.py`, core and packaged copies).
  An old pathname containing ` b/` cannot disguise source as a vendored diff. Unreadable
  destination markers count toward the budget; a deleted lock or vendored file is named by
  its old path and spends none. Rounds count per `REVIEW_FOCUS`, so a high-tier change's two
  focus reviewers each get two rounds; a review without a focus counts toward every focus, and
  an unset or new focus takes the label's highest count. (Superseded in v0.12: a new named
  focus starts its own round count; see v0.12's "A new review focus starts its own round count".)
  Author independence requires the
  lead's model selection, and the docs no longer promise automatic author exclusion or Codex
  capacity retries.
  Review bridges cap the complete diff and carried rounds. Bridge test shards honor
  `MYAGENTKIT_TEST_TIMEOUT_SCALE`.
  **ACTION:** refresh the review runtime and `docs/REVIEW_GATE.md` / `docs/REVIEW_RUNNING.md`;
  record `REVIEW_ROUND_EXCEPTION` before a third completed review under a label.
- **Unity overlay re-checked against Unity's docs and the MCP for Unity v10.3.0 source**
  (`overlays/unity/`, `patterns/pure-core-plus-engine.md`). UnityYAMLMerge is set up as a
  mergetool, not a merge driver (Unity documents only the mergetool); a `file:` package path is
  relative to `Packages/`; the assembly whitelist names its precompiled-DLL and `autoReferenced`
  holes; the concurrency rule covers serialized files only; MCP cost depends on the client; only
  some MCP edits are Undo steps (delete, asset delete/move and script edits are not), so git is
  the undo that always works; `-logFile` and the results path are absolute; `-quit` is not used
  with `-runTests` (Unity's manual: it quits before tests finish); the gate's comments no longer
  claim undocumented Unity behaviour, and `unity_gate.sh --self-test` runs from a relative path.
  Sources: KARARLAR B13, B12 inv3#147, B14 inv3#153, D09 inv3#72, D10 inv3#148-149.
  **ACTION:** a Unity project takes the overlay's updated `AGENTS.md`, `UNITY_SETUP.md`,
  `unity_gate.sh` and the `.gitignore` fragment.
- **Worker lifecycle** (`scripts/spawn_worker.sh`, `spawn_codex.sh`, `close_worker.sh`,
  `watch_workers.sh`, `clean_worktrees.py`, `.claude/agents/worker.md`, `docs/HANDOFF.md`).
  A spawned worker's worktree is locked (`git worktree lock`, reason `kit worker NAME`) until
  `close_worker.sh`, which lifts only that lock before its audit and keeps it when the close
  fails; the audit never removes a locked worktree (KARARLAR B04 inv3#54; Claude Code
  worktrees doc; `--lock --reason` since Git 2.33). `spawn_worker.sh` starts every worker with
  `--disallowedTools AskUserQuestion`: the result file is the question channel (D02 inv3#35;
  Claude Code CLI reference). Both spawn scripts print `about to run 'NAME': model M, effort E`
  first (issue #68 item 1, B05 inv1#141). `watch_workers.sh --context-warn` takes `NNNk` or
  `NN%`, default the smaller of 200k and 50% of the window (it was 50%: 500k on a 1M window; a
  bare number keeps its old meaning), and reads `08k` as decimal (B07 inv3#67). The worker
  definition sets `autoCompactWindow: 200000`; a worker hands off at its second compaction,
  reviews its own diff with sub-agents also when it runs as one, and `Kind: blocked` also
  means failed (D06 inv1#164, D01 inv1#286, #202, D10 inv1#273). **ACTION:** take the
  updated scripts, `worker.md` and the `docs/HANDOFF.md` sections.
- **A finished worker closes itself, and a merge closes the worker it merged**
  (`core/.githooks/post-merge`, `scripts/close_worker.sh`, `spawn_worker.sh`, `spawn_codex.sh`,
  `codex_worker.py`, `docs/WORKFLOW.md`, `docs/HANDOFF.md`; owner 2026-10-16: finished Claude
  and Codex worker tabs stayed open for hours). `codex_worker.py` now supervises Claude workers
  too: a `Kind: completed` result, a handoff or a decision ends the session and its tab, once no commit or
  gate runs in its checkout; a progress result
  or a free-form file ends nothing. `spawn_worker.sh --result FILE` names the result (default
  `RESULT-NAME.md`) and records it in `.myagentkit/workers/NAME.result-path`. The post-merge
  hook runs `close_worker.sh --finished NAME` for each kit worker (the worktree its spawn locked
  `kit worker NAME`) whose branch tip the merge merged, never one that only came in as another
  worker's base; `--finished` leaves a worker whose session still runs without a completed
  result. A refused close is printed and the merge stands. On native Windows `close_worker.sh`
  now ends a Codex session whose `-C` argument is the worker's own worktree (the command line
  split as Windows splits it: a `-C` path inside another session's prompt is not matched)
  instead of refusing, and names its session id; one without a worktree is still refused. The
  printed resume command keeps the launch's `--backend`, `--settings` and `--allowed-tools`.
  `codex_worker.py --wait` judges NOT A RESULT on the age and bytes of one open file, and a file
  replaced while read is no verdict. `spawn_codex.sh`'s instruction names
  the four result header lines its wrapper needs: a `Kind: completed` result without them never
  closed its worker. A merge counts only a result published since the worker's latest spawn
  (a resumed worker keeps its last one); a tab ended on its published result closes at once;
  the supervisor finds the locks of a checkout with a non-ASCII name on any Windows locale.
  The supervisor keeps its `KIT_WORKER_*` settings out of the worker's environment, so
  nested supervisors cannot overwrite its exit record. With no gate running, it waits
  at most ten minutes on `index.lock`, then reports the stale lock and ends the worker.
  A failed spawn before session launch removes its new worktree and branch, including
  when a post-checkout hook fails. Once a session may have started, the worktree stays
  and the failure explains how to remove it. A handoff stays resumable with `--resume`.
  A spawn claims the worktree folder with mkdir before `git worktree add`, so a spawn that
  loses the race for a name changes nothing. Once a result, a handoff or a decision passed
  its grace, the supervisor keeps it while a commit or gate runs: a result the lead moves
  before committing no longer leaves the session open, and only a newly published result
  or question replaces it.
  `spawn_worker.sh --resume SESSION_ID` continues a worker's conversation
  under the same NAME (and worktree, locked again), so a resumed tab can be closed; the lead
  never opens a worker tab by hand. **ACTION:** take the updated hook, scripts and the
  `docs/WORKFLOW.md` and `docs/HANDOFF.md` sections.
- **A Codex Accept is read as strictly as a Claude one** (`scripts/claude_bridge.py`
  `review_parts`, used by `scripts/codex_bridge.py` and `scripts/usage_summary.py`). The
  Findings section ends only at another named section, so a `### **High**` sub-heading, a
  bold or plain paragraph finding and a nested severity line are read as findings, and a
  plain Accept that carries one fails as `invalid_evidence`; so does one whose Findings hold
  prose that is neither a Low, a `Pre-existing:` item nor a placeholder such as `None.`. A
  placeholder counts only as a whole block, its wrapped lines joined. A plain Accept that
  keeps a manual check, a heading-form check included, fails too: it is an Accept with
  Manual Checks. Review parsing preserves finding and manual-check headings across section
  boundaries and rejects hidden High findings or NOT RUN checks in structured output.
  Bare NOT RUN is a manual check. Clean placeholders and bold `Pre-existing:` items pass.
  Indented, numbered and emphasized High or Critical lines stay separate findings in every
  section, and NOT RUN or "could not verify" lines count even when emphasized or written
  on a verdict-like line.
  **ACTION:** copy the three scripts.
- **Lessons from the kit's own development, written where they apply** (`AGENTS.md`,
  `docs/COMMUNICATION.md`, `docs/WORKFLOW.md` "Model routing" rules 1 and 3,
  `CONTRIBUTING.md`; `RESEARCH_LOG.md` 2026-10-15). A bug the task can fix is fixed in it,
  not filed; a test runs in its own command and is read before a commit, never chained with
  `;` or filtered; a short yes to a proposed hand-off is the hand-off; while the owner is
  present decisions go through the question tool, while away no work waits on a question;
  a batch of paid runs is announced (how many, model, effort) and runs one after another;
  a step to a stronger model chooses the effort again. A new `AGENTS.md` section, "Compact
  instructions", tells `/compact` and automatic compaction what to keep (vendor:
  code.claude.com/docs/en/costs). **ACTION:** take the new `AGENTS.md` lines and section,
  the two `docs/COMMUNICATION.md` bullets and the two "Model routing" additions.
- **cross: both model families write, and each reviews the other** (`docs/WORKFLOW.md`,
  "Working modes, by name" and "Model routing" rule 7; `docs/HANDOFF.md`, "The brief";
  `scripts/owns_check.py`, `scripts/review.sh`, `scripts/spawn_codex.sh`). With a second
  family plugged in beside the Claude lead, Codex takes tasks with written acceptance
  criteria inside one module (`gpt-6-luna` medium for mechanical work, `gpt-6.1-sol`
  medium or high, never xhigh), and Claude takes the rest. Claude reviews every Codex
  change; Codex reviews a Claude change at every tier, one pass, report only, and
  the lead checks each finding. Critical work is written by Opus until the owner says
  otherwise, and the strongest Claude tier reviews it. Every brief names the paths its
  worker may change on an `Owns:` line, and `review.sh` refuses a diff outside them when
  the brief is `REVIEW_TASK_FILE`. Ownership checks allow standard worker reports, parse
  numbered `Owns:` lines, and fail closed without ownership.
  A Codex worker opens at most two sub-agents at once
  (`agents.max_concurrent_threads_per_session=2`). solo may name its family
  (`solo "family: codex"`), and a switch to saver records the mode it interrupts in its
  note (`low: claude, after: cross`), so the return to it survives a hand-off. The `normal` mode of earlier v0.11 drafts was never released;
  cross replaces it. **ACTION:** copy `scripts/owns_check.py`, `scripts/review.sh` and the
  Claude Code overlay's `scripts/spawn_codex.sh`; take the kit's "Working modes, by name"
  section and rule 7 into `docs/WORKFLOW.md` and the `Owns:` paragraph into
  `docs/HANDOFF.md`.
- **Every kit change cites its source** (`CONTRIBUTING.md`): a numbered finding of a report
  in `docs/research/`, an official vendor document, or a lesson a project paid for; with no
  source, research comes first, and the maintainer decides only when research settles
  nothing. The research reports moved from `docs/research-*.md` to `docs/research/` with an
  index, the kit's bibliography (`docs/research/README.md`); a report without a row fails
  `tests/test_doc_pointers.py`. Projects get the same idea as a recommendation in
  `docs/WORKFLOW.md`, "Documentation maintenance contract".
- **A `claude@NAME` review of another model family counts as the second model**
  (`docs/REVIEW_GATE.md`, "Invariant"; `docs/WORKFLOW.md`): independence comes from the model
  family, not the CLI. Its evidence header now says `model_attested: no (requested,
  unattested ...)`, because through a backend the CLI names the model it asked for, not the
  weights that answered.
- **How an agent talks to the owner is now one document** (`docs/COMMUNICATION.md`, pointed
  at from `AGENTS.md`, "Language & style"): the chat language with English identifiers in
  backticks, every term explained at first use, no bare session label (`D-1`, `r2`,
  `Accept-MC`) toward the owner, a final report that opens with the outcome and any failed
  step, a three-step confidence scale, one decision per question with a marked
  recommendation, a two-layer handoff (`docs/HANDOFF.md`, "Owner summary"), no compression
  modes. New `docs/GLOSSARY.md`: the terms the owner knows and the kit terms an agent
  explains. **ACTION:** copy both files from the kit's `core/docs/`, fill `{{CHAT_LANGUAGE}}`
  in `AGENTS.md` and `docs/COMMUNICATION.md`, and `{{KNOWN_TERMS}}` in the glossary (setup
  interview question 12). Claude Code overlay: two new hooks, `.claude/hooks/plain_report.py` (Stop: bounces a final
  message that names a bare label outside code, once per turn) and
  `.claude/hooks/progress_reminder.py` (PostToolUse: one line of context after five tool
  calls with no visible text); **ACTION:** copy both and their entries from the overlay's
  `.claude/settings.json`; hooks are not synced. The worker and reviewer definitions say
  their reports are for the lead, who translates. The dogfood period measures the rules
  (`docs/COMMUNICATION.md`, "Measuring the rules").
- **ACTION — v0.11 is used for real in its first projects; report every kit problem.** leeway
  and labricore-web take v0.11 straight away, and their first one and a half weeks on it are
  its dogfood period (`docs/ACCEPTANCE.md`). A lead upgrading one of them is extra careful
  with the upgrade and with the kit afterwards: every problem, surprise or doubt about
  MyAgentKit, and about this release above all, goes upstream through
  `/myagentkit:kit-feedback` (an issue), not only into the project's notes.
- **The lead's context line is a band, set by quality as well as cost** (`docs/WORKFLOW.md`,
  "Worker cost", rule 8; `AGENTS.md`, "MENTION ONCE"): yellow at 200k (plan the cut, no new
  round), red at 300k (cut at the next clean stop), ceiling at 400k (stop now), the same for
  every model; a rule corrected twice or two worker-route refusals cut at any size. A
  `/compact` carries a fixed instruction, never bare, and a second compaction in one session
  is a hand-off instead (the hook then recommends only a hand-off). The new
  `scripts/context_buckets.py` counts the lead's errors by context size (worker-route and
  AI-attribution refusals, pushes, owner prompts marked `#fix`, the 20 requests around each
  compaction): the dogfood data that keeps or moves the band. The old
  reason ("pays back in under ten turns") was wrong at today's cache prices. Evidence:
  `docs/research/context-limit.md`. Claude Code overlay: `context_size.py` names the band,
  `.claude/settings.json` sets `autoCompactWindow` to 450000 (a safety valve; the default is
  about 967k), and a `SessionStart` hook (matcher `compact`) prints
  `.claude/hooks/after_compact.txt`, what to re-read after a lossy summary. **ACTION** (Claude
  Code overlay): copy `context_size.py` and `after_compact.txt`, and add `autoCompactWindow`
  and the `SessionStart` entry from the overlay's `.claude/settings.json`; hooks are not synced.
- **No worker starts without a stated model and effort** (`docs/WORKFLOW.md`, "Model routing"
  rule 1 and "Worker cost" rule 5; Claude Code overlay). Before every worker the lead tells the
  owner in one plain line which model, which effort and why; a skill whose template names no
  model is no exception. The new `.claude/hooks/guard_worker_route.py` refuses an Agent call
  that names no model or no effort (a fork excepted). **ACTION** (Claude Code overlay): copy
  `.claude/hooks/guard_worker_route.py` and add its `PreToolUse` entry (matcher `Agent|Task`)
  from the overlay's `.claude/settings.json`; hooks are not synced.
- **The kit check asks for a killing test** (`scripts/check_kit.py`, a NOTE, never a failure):
  when the change against the upstream branch adds a refusal (a `raise`, a nonzero exit, `die`,
  a FAIL line) and no file under `tests/` changes, a NOTE names the line and asks which test
  fails if it is removed. Without an upstream branch the note is NOT RUN. Syntax and shell
  checks read tracked and untracked-but-not-ignored files, skipping ignored evidence and worktree copies.
- **Symlinks, junctions and long paths in the kit check** (tests only; nothing for a project to
  do): the symlink and junction classes were already held by required suites
  (`test_boundary_restore`, `test_check_gate`, `test_check_gate_windows` and `check.sh
  --self-test`), so no new fixture was written. One gap is closed: on native Windows a process
  whose working directory lies past 260 characters keeps its worktree from `clean_worktrees`;
  `test_clean_worktrees_windows` minimum 11.
- **The kit check's shell sensor** (`scripts/check_kit.py`; the shipped `check.sh`, `doctor.sh`,
  `watch_workers.sh`, `boundary_selftests.sh`, the `commit-msg` and `post-merge` hooks and the
  Unity overlay's `unity_gate.sh` change only in how they print): over the sh scripts git tracks
  (`.sh` files and files with an sh shebang), the kit's own lint refuses an `echo` that prints an
  expansion or a backslash (dash reads the backslash as an escape; 65 lines now use
  `printf '%s\n'`) and `mktemp -p`, `-t`, `--suffix`, `--tmpdir` (GNU-only, or another meaning
  on macOS), and `shellcheck -s sh` refuses a bashism (SC3xxx) or an error; its warnings stay a
  reviewer's, and no rc file or SHELLCHECK_OPTS can hide a code. Without shellcheck the step is
  NOT RUN, except on CI's Linux job. REVIEW_GATE's attack list keeps these classes: a project's
  `scripts/check.sh` has no such sensor.
- **The kit check's locale sensor** (`scripts/check_kit.py`, the kit's own check; nothing for a
  project to do): a `locale` unit runs seven fast text suites again with `PYTHONUTF8=0`, under
  `LC_ALL=C` and `tr_TR.UTF-8` on POSIX (NOT RUN without the Turkish locale; CI's Ubuntu job
  generates it) and under the ANSI code page on Windows, with an encoding-less `open`,
  `read_text`, `write_text` or text subprocess an error (`EncodingWarning`, PEP 597); each suite
  is held to its own minimum, skipped tests not counted. Locale and UTF-8 bugs were the second
  most frequent review finding class (91 mentions in the v0.11 archives). Its first run found
  encoding-less reads in the kit check and in the Claude Code overlay's `context_size.py` hook,
  which now reads and writes its state as UTF-8. **ACTION** (Claude Code overlay): the hook has
  no KIT-OWNED header, so `sync-kit.sh` does not copy it; copy
  `overlays/claude-code/files/.claude/hooks/context_size.py` over the project's copy by hand.
- **One review policy in two files, and one model** (`docs/REVIEW_GATE.md`,
  `docs/REVIEW_RUNNING.md`, `AGENTS.md`, `docs/WORKFLOW.md`; `claude_bridge.py`,
  `codex_bridge.py`, `review_dispatch.py`, `review.sh`, `agent_process.py`, `working_mode.py`,
  `agent_cost.py`; the Claude Code overlay): the review rules that lived in eight files live
  in two, each rule once, and the kit runs on one model family with a second vendor
  pluggable. A brief's `Risk:` line picks the tier: low gets the gate and one light review,
  medium one reviewer in one pass, high two reviewers at once with narrow prompts
  (`REVIEW_FOCUS`); the session that wrote a patch never reviews it. Reject needs a Critical
  or High; a Medium is fixed in the round only when the fix is one place with a test, else
  filed; Low is filed, and an Accept may carry Lows and pre-existing items. A label carries
  two rounds: the second confirms the first round's Critical and High fixes and reports new
  Critical or High only; a third attempt stops with exit 2 unless
  `REVIEW_ROUND_EXCEPTION=<reason>` is set, and the record keeps the reason. The one review
  prompt (`claude_bridge.REVIEW_PROMPT`, both adapters) states the finding threshold, the
  severities for this kit, what not to report, the Low ceiling and the round-two narrowing,
  and reads the brief (`REVIEW_TASK_FILE`), the tier (`REVIEW_RISK`) and the focus from the
  environment, which the wrapper passes. Default effort follows the tier (high for a high
  tier, else medium; xhigh and max are not review choices). `REVIEW_TIMEOUT_SECONDS`
  defaults to 2700 and is capped at 3600; a timed-out review returns no verdict and its
  quota is spent. The routing escalation rule is gone. The seven working modes are three:
  `solo` (default: one family, Claude unless the note says `family: codex`; a fresh session
  of another tier reviews), `cross` (both families write, each task by fit, and each
  reviews the other; entry below) and `saver` (the low side reviews within a small budget);
  `working_mode.py` refuses an old mode name and prints the mapping, a switch sets the note
  from its second argument (`saver "low: claude"` is required, `solo "family: codex"` is
  optional, cross takes none), and `--replace-state` accepts one edit of the mode line: an
  old name becoming one of the three. A high-tier change takes one label per focus reviewer. Worker and lead prompt caches live one hour
  (`CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL=1h` in `spawn_worker.sh`, `promptCacheTtl` and
  `subagentPromptCacheTtl` in the overlay `settings.json`; the frontmatter `cacheTtl` is
  dropped). `AGENTS.md` is a 165-line map: the review paragraph is three lines and a
  pointer, the STATE discipline moved to `docs/AGENTS.md` with the path-scoped
  `.claude/rules/state.md` pointing at it. `agent_cost.py` prints the cache-hit share
  per agent with an 80% target, and `docs/context-is-a-budget.md` corrects the cache and
  MCP-catalogue claims and states the compaction rule. **ACTION:** copy the listed scripts
  and the overlay files (`.claude/agents/worker.md`, `diff-reviewer.md`,
  `.claude/rules/state.md`, `scripts/spawn_worker.sh`); add `promptCacheTtl`,
  `subagentPromptCacheTtl` and the `env` entry `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` from
  the overlay's `.claude/settings.json` to your own (copying the file would drop your own
  `env` values, deny rules and plugin choices); take the
  kit's `docs/REVIEW_GATE.md`, `docs/REVIEW_RUNNING.md`, `docs/WORKFLOW.md`, `AGENTS.md` and
  `docs/AGENTS.md` and re-apply your project's own lines; BEFORE running `working_mode.py`,
  rewrite the `**Working mode:**` line of `docs/STATE.md` to `solo`, `cross` or `saver`
  through `--read-state` and `--replace-state` (claude-only becomes solo;
  cross-performance, claude-first and codex-first become cross; cross-saving, claude-saver
  and codex-saver become saver with a `(low: ...)` note)
  and the mode table of `docs/WORKFLOW.md` to those three rows, since the script refuses
  the old names;
  measure your first large review's duration from the chain record's timestamps and, if
  3600 s cut it off, ask the owner whether `MAX_REVIEW_TIMEOUT` rises.

- **Two ordinary accidents named** (issues #75, #76; `AGENTS.md` task discipline,
  `docs/REVIEW_GATE.md` attack list): a script's recursive delete of a directory chosen by a
  variable or a setting proves ownership by a marker it wrote and refuses roots, ancestors
  and unresolved links; a freshness stamp is bound to the fingerprints taken before the work,
  re-checked before it is published. Both were found by a downstream review in that
  project's own tooling, not in the kit, whose scratch folders and review snapshots already
  follow the pattern; the kit records them as guidance, not as a new gate. **ACTION:** copy
  the two sentences into your `AGENTS.md` and `docs/REVIEW_GATE.md`.

- **Reviewer configurations are measured** (`claude_bridge.py`, `codex_bridge.py`,
  `agent_usage.py`, `usage_summary.py`): each answer in `REVIEW_DISPOSITIONS` carries one
  key, `fixed:<commit>`, `disproved:<evidence>` or `deferred:<issue or decision>`; a file
  without a key stops the review (exit 2) before any model runs. The usage record keeps the
  counts, and `usage_summary.py` prints per task and per model, effort and backend the
  findings per round and the author-claimed acceptance rate (fixed + deferred over all
  answered), credited to the round the answers refer to. `REVIEW_SHADOW=1` archives a
  trial configuration's verdict with a `SHADOW REVIEW` banner, records `shadow` in the
  task, and the summary lists it apart as no round. The rate informs the owner; nothing
  switches a reviewer off by itself (`docs/USAGE.md`). **ACTION:** sync the review
  scripts and the Codex plugin; write every disposition with its key from now on.

- **Windows worker observation and generated paths corrected** (`spawn_worker.sh`,
  `watch_workers.sh`): an older hook's `waiting input` line means an idle prompt, never a
  permission WAIT; the watcher prints one older-kit notice per worker and asks for a re-spawn.
  State is read once as bytes: a zero-byte file is no signal yet, a NUL-only file is invalid,
  an unreadable one is an observation failure (exit 3). Spawn bounds every generated filename
  at 255 bytes (240 name characters) and the longest native Windows path at 259 characters
  before any worker file or worktree is made. **ACTION:** sync both scripts and re-spawn
  workers that still run the older hook; shorten the worker name or the checkout path when
  spawn refuses a generated path.

- **Worker launch cleanup follows confirmed session ownership** (`spawn_worker.sh`,
  `spawn_codex.sh`): an accepted tmux pane keeps its temporary script when its spawner is
  interrupted; a failed or interrupted launch without a confirmed session removes the script
  and releases the Codex reservation even when unlinking fails. Cleanup runs once, clears its
  traps and releases only its own reservation, so a repeated signal cannot remove a lock
  another spawner took meanwhile. **ACTION:** sync both launcher scripts.

- **Spawned workers register as peers** (`spawn_worker.sh`, `spawn_codex.sh`,
  `docs/WORKFLOW.md`): the lead's session markers are cleared with an `env -u` prefix on the
  worker's command; on the tmux path the command goes into a self-removing temporary script
  that tmux runs as `sh SCRIPT`, so tmux's default shell (fish included) parses two plain
  words. The lead subscribes with `notify_when_idle` conditionally on native Windows only; a
  tmux worker always registers. **ACTION:** sync both launcher scripts.

- **The behaviour appendix belongs to the reviewed snapshot** (issue #74; `claude_bridge.py`,
  `agent_usage.py`, `spawn_worker.sh`): a Claude review refuses a symlinked, non-regular or
  escaping appendix before launch. The appendix bytes reach the review copy, the fingerprint,
  the evidence and the usage record as `behaviour_sha256`; a change during the review fails as
  `stale_checkout`. The worker's appendix status line strips terminal control bytes, and the
  enabled and disabled lead launches are separate commands in `docs/WORKFLOW.md`. **ACTION:**
  sync the core scripts and the Claude worker overlay; start a fresh lead with the enabled or
  the disabled command.

- **Named Claude-compatible backends** (`review_dispatch.py`, `claude_bridge.py`, `review.sh`,
  `spawn_worker.sh`, `usage_summary.py`, `docs/DEV_SETUP.md`): `.myagentkit/backends/NAME.env`
  (Git-ignored, untracked, a regular file) holds a non-empty provider token and an explicit
  model id; `--backend NAME` or `MYAGENTKIT_BACKEND=NAME` routes a Claude review or worker
  through it. The launch clears every inherited Claude credential and routing control (one
  shared list) and restores it afterwards; a backend worker refuses a `claude-` model id; a
  Codex review ignores a backend request with one notice; the evidence records the reviewer as
  `claude@NAME`; Claude reviews deny reads of the backends folder. The usage summary groups by
  model, effort and backend. **ACTION:** sync the review and worker scripts; create the
  backend file by hand where a backend is wanted; configure the documented Codex administrator
  read-deny policy where supported.

- **Review results survive a late failure; the self-test and the check gate on native
  Windows** (issues #41 #53 #60 #71; `review_dispatch.py`, both adapters, `check.sh`,
  `check_kit.py`): the dispatcher's attempt loop keeps a handed-over result when printing or
  recording fails afterwards (`error_after_result`, the delivered exit code); each adapter's
  NOTE says whether the result completed, failed, or its evidence was never written. The tree
  check in both `check.sh` wrappers hashes every path in one batched `git hash-object` call
  under the run directory and fails by the first uncovered path. Self-test status, the check
  gate, boundary restore and `clean_worktrees` carry Windows-only suites. **ACTION:** sync
  `scripts/check.sh`; Git 2.42 or newer is required (`docs/DEV_SETUP.md`).

- **The shell case lint runs under bash 5.2** (issue #40; `scripts/check_kit.py`): every
  kit shell file is parsed with `bash --posix -n` by a bash of 5.2 or newer, found on PATH or
  through `MYAGENTKIT_BASH`; the prerequisite is checked even when no file needs it, scripts
  are decoded as UTF-8, and the version probe and the parser run in the C locale, so a
  translated version banner still satisfies the prerequisite and a syntax failure keeps bash's
  own reason. The case-lint test scans the kit's repository files, so stale copies in
  worker worktrees no longer fail it. The macOS CI job installs Homebrew bash before the gate.
  **ACTION:** a kit checkout on macOS needs `brew install bash` before `scripts/check.sh` passes.

- **Review launch and cut-off guidance corrected** (`docs/WORKFLOW.md`, `docs/REVIEW_RUNNING.md`,
  `docs/GOTCHAS.md`, `docs/REVIEW_GATE.md`, `docs/HANDOFF.md`, `AGENTS.md`): reviewers start
  together within the measured memory budget and the self-test is scheduled when capacity
  permits; running jobs take slots; never fewer reviews. When two jobs still do not fit, the
  lead asks the owner; no answer within one `REVIEW_TIMEOUT_SECONDS` permits a sequential
  exception only when one job fits, recorded with the budget in the lead's notes. After a
  cut-off, inspect the project gate lock at `git rev-parse --git-path check.lock` and the
  `check-selftest` marker beside it; reviews and the kit's own self-test hold no lock. Read the
  highest-numbered review chain checkpoint: a completed record is finished; a failed one is
  finished when its attempts equal the possible attempts, its `failure_kind` is outside the
  dispatcher's unavailable set, or no fallback is allowed; a failed attempt without evidence or
  a usage record ends the chain. Otherwise wait from the first checkpoint's mtime for the
  timeout (3600 s when the record stores none) times the possible attempts, then still confirm
  completion in the process listing by the reviewer copy (`myagentkit-codex-*` /
  `myagentkit-review-*`; on Windows `Get-Process -Id N | Select-Object Path` when CIM hides
  the working directory). Wait for survivors or ask the owner; never start heavy work beside
  them. **ACTION:** sync these docs or apply the launch and recovery rules by hand.

- **The existing-file boundary probe runs on native Windows** (issue #60;
  `scripts/boundary_selftests.sh`): under `env -i` the Python install manager's `python3`
  alias, missing LOCALAPPDATA, found no Python and downloaded and installed one on every
  self-test. On Git for Windows, MSYS2 and Cygwin `probe_env` now keeps SYSTEMROOT, WINDIR,
  LOCALAPPDATA, APPDATA, USERPROFILE, PATHEXT and COMSPEC, sets PYTHONNOUSERSITE=1 (the user
  site lives in the real APPDATA, where HOME is the copy's own on POSIX), and the probe's
  audit runs the Python `check.sh` resolved (`$kit_python`: python3, python or `py -3`), never
  a bare `python3`. The probe then ran into its own POSIX calls; it is ported: the copy keeps
  a symlink or junction as a link (`winsymlinks:nativestrict`; a host that cannot make one is
  reported NOT RUN by name, with Developer Mode as the remedy), the audit treats every reparse point as a link and never enters one, and
  the delete opens each entry as itself and removes it with POSIX semantics that ignore the
  read-only attribute without changing it, so git's read-only objects go and a file
  hard-linked with the checkout keeps its attribute. A copy is left (`cd /`) before it is
  deleted, a gate called by a Windows path (`C:\...\check.sh`) is found in the copy, the
  audit names paths with `/`, and the probe's Python prints UTF-8. On POSIX the delete and
  audit behave as before. Known limit on Windows: a relative folder link whose target sorts
  after it becomes a file symlink in the copy, so a gate that walks through it fails in the
  copy; the checkout is never at risk. **ACTION:** if you adapted the existing-file example, take the new `probe_env`,
  `probe_delete`, `probe_audit` and `cp` line from `$KIT/core/scripts/boundary_selftests.sh`
  into your `scripts/boundary_selftests.sh`.
- **A worktree path holding a newline is kept for the right reason** (issue #41;
  `scripts/clean_worktrees.py`): `git rev-parse` is asked one flag per call, each answer less
  exactly its own newline. Split on newlines, such a path was judged "its folder is not its
  own worktree"; it is now kept because the path is not printable. It was kept before too.
  **ACTION:** copy `$KIT/overlays/claude-code/files/scripts/clean_worktrees.py` to
  `scripts/clean_worktrees.py`.
- **Doctor catches an old Claude CLI earlier on PATH** (`scripts/doctor.sh`): the configured
  Claude reviewer must advertise `--effort`, which the adapter already requires. A newer
  installation later on PATH cannot satisfy that check. The probe finds the CLI as `review.sh`
  does, `~/.local/bin` included, under the grep probe's 5-second bound. Its `--help` output
  goes to a temp file, never a pipe, so a CLI whose background child keeps stdout open
  cannot hold session start past that bound. Where `setsid` exists, that child is killed with
  the probe's process group (otherwise a NOTE says it is not), and an interrupted doctor
  removes the temp file. Without `timeout` or a temp file the probe is skipped with a NOTE.
  Both probes print their exit status on a line of its own: a `--help` or an rc file ending
  without a newline once hid it, and doctor gave a false 'did not answer' (or 'did not
  complete') NOTE.
  **ACTION:** sync the kit or copy
  `$KIT/core/scripts/doctor.sh` to `scripts/doctor.sh`.
- **Live Claude adapter acceptance recorded** (issue #6; `docs/ACCEPTANCE.md`): a live
  proposal, and live permission and customization probes, passed on native Windows.
  On 2026-10-10, Bash write and network containment passed on WSL2 Debian; macOS is not covered.
- **The Claude reviewer's shell is sandboxed, or absent** (issue #39; `claude_bridge.py`,
  `review.sh`): on macOS, Linux and WSL2 its Bash runs inside Claude Code's sandbox. Verified:
  native Windows (no Bash) and the live WSL2 probe. NOT RUN: macOS and native Linux, where the
  enforcement is unverified. The sandbox allows writes only in the throwaway copy and Claude
  Code's temporary directory, allows no network, never retries a command outside it, and
  stops the review at startup where it
  cannot start (`sandbox_unavailable`, never a fallback). On native Windows, where Claude
  Code has no sandbox, the Claude reviewer gets no Bash: it reads the copy and marks its
  findings REASONED. A reviewer that found the repository by its absolute path could
  write to it before. **ACTION:** copy the core scripts; on Linux and WSL2 install
  `bubblewrap` and `socat` (`scripts/doctor.sh` says so).
- **Review clean-up gaps closed** (issue #39): a copy left by a killed adapter is removed
  by a later run once it is old and its lifetime lock is free. An old archive timestamp
  cannot cause a live copy to be swept; unmarked legacy folders are kept. A proposal makes
  no temporary folder. A copy that cannot be made, including an operating-system error,
  is a recorded failure (`copy_failed`, with evidence and a usage record) in both adapters.
  Scratch setup failures are recorded too and cleaned up. By the owner's decision, a
  temporary filesystem that refuses locks fails each review as `copy_failed`, whose message
  says to set `TMPDIR` to a filesystem with lock support; there is no age-only fallback. A
  `.lock` the adapter did not create is never removed: it picks another folder. A `TMPDIR`
  inside the reviewed repository is now a recorded `copy_failed` (exit 5, evidence and a
  usage record), not exit 2 without a record. Old orphan lock files are swept after acquiring
  their lock. Errors from a running reviewer are recorded as `run_failed`, with evidence,
  and the archive says whether the reviewer launched (`agent_process.run` records it), so a
  launch that failed and then raised on cleanup reads `did not start`, not `ran`,
  a failed usage record, captured output and a structured dispatcher result. They are never
  labelled as copy failures or preflight failures; one before the launch says the reviewer did
  not start. The evidence keeps only the tail of the reviewer's stderr, outside its own text;
  the usage record keeps all of it. A cancel stays a cancel when the look at the reviewer's
  exit fails; timeout handling stays unchanged.
  **ACTION:** update both the copied core scripts and the plugin to the same kit version;
  an older adapter still sweeps by age alone and can remove a new adapter's live copy.
  While no review is running, delete leftover `myagentkit-review-*` and `myagentkit-codex-*`
  temporary folders that have no `.lock` sibling; these unmarked legacy copies are kept.
- **A Codex copy failure says why** (`codex_bridge.py`): a review whose copy could not be
  made keeps the adapter's reason in its evidence (`## Failure`, `Codex never ran:` and the
  tail of the error), as Claude's evidence already did; the wrapper once printed
  `copy_failed` and no reason. **ACTION:** copy the core scripts.
- **One lock seam for the scratch copy** (`agent_process.lock_file()`): the copy's lifetime
  lock (Windows' one-byte range lock, `flock` elsewhere) moved out of `claude_bridge.py` into
  `agent_process.py`, beside the other process seams the review self-test stubs.
  **ACTION:** copy the core scripts.
- **doctor finds a claude CLI the review cannot use** (`scripts/doctor.sh`): one too old for
  a flag the review passes (the winget claude 2.1.218 lacked `--restricted`), or npm's
  `claude.cmd` on native Windows, or a CLI whose help probe cannot launch or times out,
  first on PATH or named by `CLAUDE_CLI_BIN`, is MISSING
  with the binary to put first or the `CLAUDE_CLI_BIN` to set. **ACTION:** copy
  `$KIT/core/scripts/doctor.sh` to `scripts/doctor.sh` and run it.
  Each executable's help is probed once per doctor run, and all probes share one 90-second
  budget; launch failures suggest reinstalling or selecting a working executable, and timeouts
  suggest checking first-run prompts and retrying. A candidate the spent budget cut short is
  named in the fix, never hidden.
- **The review self-test runs on native Windows** (issue #54): offline CLI fixtures use
  executable Python launchers, tests inject cancels without terminating the test runner,
  and per-platform suite minimums count executed tests. POSIX-only cases report NOT RUN;
  Linux and macOS CI still run them. The kit acceptance no longer bypasses review tests on
  Windows. Native gate-lock fixtures use owned Win32 process handles for forced exits;
  restricted hosts need no taskkill CLI. Redirected adapter output uses UTF-8 so a completed review with non-ANSI text
  remains usable. LFS fixtures use their own driver rather than the host's Git LFS process.
  The kit check recovers a missing temporary completion-marker directory and prints PASS
  only after writing that marker; a failed marker write still fails the check.
  **ACTION:** copy the review companion files listed in `core/docs/DEV_SETUP.md`,
  including the new `review_test_support.py`; Windows self-tests require pip's bundled launcher.
- **Cancels and timeouts also stop detached review descendants** (`agent_process.py`):
  Linux and macOS cleanup scans a unique inherited environment marker in addition to killing
  the reviewer's process group. Native Windows Job Object tests prove that detached children
  remain contained and breakaway is refused. A descendant whose environment cleanup cannot
  read is outside the POSIX marker mechanism: a cleared environment, a non-dumpable,
  setuid, setgid or file-capability process on Linux, or one `ps -E` does not show on
  macOS; on Windows a packaged-app execution alias (the WindowsApps `python3` stub) is started
  by the system broker and escapes the Job Object. On macOS each process is read on its own once the marker shows, so a multi-line
  environment value can no longer credit the marker to the wrong pid. A failed scan is
  retried, up to 20 scans, and a give-up is reported; a `ps` that cannot list environments
  is tried once per stop, and a pid that exits mid-scan is no failure. **ACTION:** copy
  `core/scripts/agent_process.py`.
- **Routing sets effort and risk checks.** Briefs name route,
  risk, checks, model and effort. `scripts/usage_summary.py` (kit-owned, synced) reports
  review rounds, verdicts and rejects per task and per model and effort; worker errands
  write no record and are not in it. Every printed label is escaped, the backslash included,
  so a literal `\x1b` and the control character it names print differently and stay in
  separate groups; a missing, null or empty model, callee, kind or effort prints as the reserved
  label `unknown`, and a value that is literally `unknown` joins that group. **ACTION:** reconcile `$KIT/core/docs/WORKFLOW.md`
  into `docs/WORKFLOW.md`,
  `$KIT/core/docs/HANDOFF.md` into `docs/HANDOFF.md`,
  `$KIT/core/docs/USAGE.md` into `docs/USAGE.md`, and
  `$KIT/overlays/claude-code/files/.claude/agents/worker.md` into `.claude/agents/worker.md`,
  preserving project settings.
- **Refused moves leave no marker** (owner decision): a report move refused before the report left its path (a Windows sharing violation, EACCES or EXDEV from `renameat2`, a failed probe link, "no-overwrite guarantee unavailable") exits 3 and clears `NAME.report-move`; the close keeps the worktree without the audit, and the next close runs normally. **ACTION:** sync `close_worker.sh` from the Claude Code overlay.
- **Stale markers are named**: when `NAME.report-move` cannot be removed after a publication, the close prints the published path and says only the marker is stale, instead of reporting a failed publication.
- **Clearer marker refusals**: the refusal says the session is not ended and prints the recorded source and target on lines of their own; the header lists a marker among the reasons a dry run exits 1.
- **STATE refusals name FILE**: `--replace-state FILE` whose own folder is not private names FILE and says its folder must be inside `.myagentkit/` or the temporary folder. **ACTION:** sync `scripts/working_mode.py`.
- **Unfinished report moves survive retries**: `NAME.report-move` records each move before consumption and, once the report left its path, blocks later closes, keeping the worktree and session records until the lead recovers the report and removes the marker. **ACTION:** sync `close_worker.sh` from the Claude Code overlay.
- **Failed moves skip the audit**: every non-collision report-move failure keeps the worktree, even when a successor occupies the source path; a collision whose restoration failed also stops the close.
- **Private STATE recovery parents**: `--replace-state FILE` checks the recovery folder's parent before consumption, so failed folder restoration cannot expose private contents to Git. **ACTION:** sync `scripts/working_mode.py`.
- **Archives without listing permission**: a denied archive scan supplies no reuse evidence; exclusive publication still proceeds without replacing an existing archive.
- **Exclusive STATE snapshots**: `--read-state OUT` creates with O_CREAT|O_EXCL; an existing hard link is never truncated. **ACTION:** sync `scripts/working_mode.py`.
- **A snapshot per edit**: `--read-state OUT` treats OUT as a prefix and prints `SHA256 PATH`; writers edit and replace their own returned PATH. **ACTION:** update the STATE protocol from `core/AGENTS.md` and `core/docs/WORKFLOW.md`.
- **Verified snapshot cleanup**: replacement consumes a private name and deletes only the published fstat identity, preserving a successor draft at the supplied path.
- **A folder is never a STATE file**: `--replace-state FILE` refuses a FILE that `lstat` does not show as a regular file before anything moves, and renames back a folder swapped in after that check; `.myagentkit`, a subfolder of it or the temporary folder named as FILE was moved whole into a private name. **ACTION:** sync `scripts/working_mode.py`.
- **A folder is never a snapshot prefix**: `--read-state OUT` refuses an OUT that is an existing folder or ends in a separator, and creates the snapshot only in a private folder; `--read-state .myagentkit/` put a committable copy of STATE.md in the project root.
- **Kept drafts are named**: a STATE draft that cannot go back to FILE stays in its private folder, and `working_mode.py` prints that path on stderr with its control bytes as `?`.
- **Private archive sources**: the hard-link fallback first moves the report into a caller-private name, preserving a newer publication at the source path. **ACTION:** sync `close_worker.sh` from the Claude Code overlay.
- **Archive refusal without safe publication**: when exclusive rename and hard links are unavailable, the helper refuses with "no-overwrite guarantee unavailable" instead of replacing an empty claim; the report and the worktree stay (owner decision, accepted trade).
- **Interrupted archive retries**: an existing archive of the same object is reused before another number is claimed; restoration uses the returned archive path. A byte-identical report from another run gets its own number (owner decision: separate runs never share an archive).
- **Archive reuse on native Windows**: archive names are compared within the records folder, so the same-object reuse also works with the `C:/` paths Git Bash passes.
- **Unreadable archives**: an earlier archive that vanishes or cannot be examined is not taken for this report and no longer fails the close.
- **Kept reports are named**: a report the archive move consumed and could not publish or put back stays in its `.report-move-*` folder, and the helper prints that path on stderr with its control bytes as `?`.
- **No audit without the report**: when the move fails after the report left the worktree, `close_worker.sh` keeps the worktree without running the audit and says where to recover the report.
- **Consecutive polling refusals**: every successful observation, cached results included, resets that path's refusal count. **ACTION:** sync `codex_worker.py` from the Claude Code overlay.
- **Working modes, by name** (issue #57; `docs/WORKFLOW.md`, "Model routing"): the kit ships
  the tier table and seven modes, claude-first, cross-performance (the main mode),
  cross-saving, codex-first, claude-saver, codex-saver and claude-only, each with who writes, reviews and
  fixes, worker caps, effort, when it ends and a Lessons list. The `{{MODEL_ROUTING}}`
  placeholder is gone, and `docs/STATE.md` carries a "Working mode:" line.
  `/myagentkit:mode` (and the Codex skill `myagentkit-mode`) uses the shared
  `scripts/working_mode.py` to show or switch the mode, recording `.claude/mode` and the
  STATE line under a shared `.claude/mode.lock`, refusing overlapping switches. Interrupted
  switches report disagreement on reads and name the repair: choose a mode explicitly.
  A STATE edit detected before replacement refuses the switch; rollback preserves later
  independent edits. Session edits of STATE are a compare-and-swap under the same lock that
  refuses a stale edit instead of losing a concurrent one (owner decision, `RESEARCH_LOG.md`):
  `--read-state OUT` creates a per-edit snapshot using OUT as a prefix and prints `SHA256 PATH`
  from one read; the writer edits PATH, and `--replace-state FILE --expect SHA256` publishes
  it and deletes the verified object. No command
  prints a hash apart from its bytes, which let a copy read earlier pass. The snapshot lives in
  `.myagentkit/` or the temporary folder outside the project, the STATE operations run only from
  the project root, and an edit that changes the "Working mode:" line is refused. Links
  below the project root, Windows junctions on Python 3.10/3.11 included, are refused before lock
  creation. The supplied root is resolved once, so macOS
  `/tmp` or a linked home names a project as usual; on Windows only a name-surrogate reparse
  point (a junction or symlink) is a link, a cloud-file placeholder is not.
  Handwritten names and Turkish
  labels are matched without case (including capital Turkish dotted I); a list-item or
  indented line is read and switched in place, and an unknown value, a second line or any
  other line naming "Working mode:" is refused before writes. The command's allowed tools
  are only `python`, `python3` and `py -3` running `scripts/working_mode.py`. Switches preserve STATE permissions and print UTF-8
  rules even through a Windows cp1252 pipe. Doctor names the mode command when its helper is
  missing. Saver modes route fixes to the
  side with allowance while preserving independent acceptance and the fresh final review.
  Codex-first now follows the owner's confirmed definition: the Claude Opus lead only
  plans, briefs, routes and reviews; Codex implements and fixes all findings. Only work the
  lead judges too heavy or too important goes to an Opus worker, reviewed by Codex; that
  Opus worker fixes Codex's findings on it, so no model reviews its own fix.
  Codex-saver remains the separate low-Codex-allowance mode: Claude leads and does the work;
  no Codex worker, Codex reviews only. The shared saver rules keep Claude as lead in both
  saver modes.
  **ACTION:** copy the "Model routing" section and "Working modes, by name" from the kit's
  `core/docs/WORKFLOW.md` into yours over your own routing text, keeping your model names,
  and add the "Working mode:" line to `docs/STATE.md`. Sync the core scripts to install
  `scripts/working_mode.py` and the updated doctor check; copy the `/.claude/mode.lock`
  ignore rule from `core/.gitignore`.
- **A stopped worker is answered in its own session** (issue #57; `docs/WORKFLOW.md`,
  "Worker cost"; `docs/HANDOFF.md`, rule 7): never by a fresh session. The handoff names
  the sidecars and publishes the blocked result atomically with the ready end marker before
  publishing the question the same way after independent work, without requiring a commit.
  A ten-second grace period lets the turn flush.
- **`scripts/spawn_codex.sh`** (issues #57 and #43; Claude Code overlay): an interactive Codex
  worker in a Windows Terminal tab on native Windows and in tmux elsewhere, with the
  workspace-write sandbox and no approval prompts. The lead commits all Codex worker work
  after the normal cross-review, with the usual commit gate; the brief and result identify
  exact uncommitted files. Git-directory writable roots are removed: the owner's native
  Windows codex-cli 0.162 probe proved `git add` still fails on `index.lock` with both roots.
  The spawning checkout records `.myagentkit/workers/NAME.session`, outside the worker,
  under a shared `.myagentkit/workers/spawn.lock` reservation from the initial checks through
  session recording, refusing concurrent launches. An unrecorded launch keeps its reservation,
  with its worker's name inside, until the printed `--resume SESSION_ID` of that name records
  the launch and takes it over, or the lead confirms the launch ended and runs
  `rm -r .myagentkit/workers/spawn.lock`; printed resume commands quote the model argument.
  The lead resumes it with `--resume`; successful `close_worker.sh NAME` removes the records,
  allowing cleanup and name reuse. The close refuses while the worker's decision file (its path
  recorded in `NAME.question`) waits for its answer; a resume removes the answered file once
  the resumed session publishes a new result or exits cleanly, never on elapsed time. It moves
  an uncommitted default `RESULT-NAME.md`, which the lead never commits, to `.myagentkit/workers/NAME.result.md`, so
  the audit can remove the finished worktree. An earlier report there is kept (the new one
  takes the number above the highest, `NAME.result-2.md` and on), never replaced, also on a
  filesystem without an exclusive rename (WSL `/mnt/c`, NFS, FUSE, SMB), and a worktree the audit
  keeps gets its result back.
  Workers publish decisions to `QUESTION-NAME.md`;
  `codex_worker.py` waits for the end marker and grace period before ending their process
  tree, and a fresh replacement is refused. Only a decision or a newly published
  `Kind: completed` result closes the worker; a progress, handoff or blocked result, or an
  in-place edit of an older result, leaves it running. The wrapper writes
  `.myagentkit/workers/NAME.exit` on every way out it controls, a decision without a blocked
  result included, and holds `NAME.live` locked while it runs, so `--wait` reports EXITED for
  a worker that stops without publishing, even when the wrapper is killed or its tab closed.
  A spawn whose session never shows still prints the wait command and the resume form. On native
  Windows `close_worker.sh` refuses while a Codex session runs in the worker's folder, and a
  kept worktree keeps its session record. Its printed
  `--wait FILE --since START --stale FILE_ID --exit RECORD` command notifies the lead of an
  uncommitted handoff as a background command. It uses the result identity captured before
  launch, so a delayed wait still excludes an in-place edit of an old result. On POSIX the
  supervisor and the waiter hold that result open, so a new result cannot be given its freed
  inode number. After PROGRESS or HANDOFF the wait prints its exact follow-up command, which
  waits for the worker's next result: other contents than the reported result's, by rename or
  by in-place rewrite; a byte-identical republication does not count. A follow-up printed with
  the earlier `INO:HASH` form compares its hash. A poll opens the result, and a new question,
  only after its id, size or time changed; the answered question is opened only to consume it.
  On Windows a poll's stat still holds the file for a moment and refuses a rename over it, so the
  worker publishes with `codex_worker.py --publish TEMPORARY_FILE DESTINATION`, which retries a
  refused rename for about two seconds. An open that meets a rename is read again at the next
  poll; 50 consecutive refusals of one file, about five seconds, are an error, not an endless
  wait. A resumed supervisor retries the rename of its live record while a waiter probes the
  previous run's, and a supervisor that fails to start writes its exit record, so the wait ends.
  Windows children join their job before running; POSIX escalation kills the entire group.
  POSIX SIGTERM and SIGHUP unwind supervisor cleanup and reap the worker's process group.
  The worker's instruction tells it to run the checks named on its brief's
  `Route: ... · Risk: ... · Checks: ...` line. The tab preserves quick startup errors behind an
  Enter prompt, and launches Git Bash by its full Windows path. `--no-daemon` keeps each
  runtime private. The default result is at the repository top; the brief uses the spawn-time
  path. `--result FILE` requires a `.md`
  file inside the worker's folder; its path and parent directory are validated before a
  worktree or branch is created, so a rejected path leaves the name available for retry.
  Ignore patterns keep project `docs/QUESTION-*.md` visible.
  **ACTION:** adopt the lead-owned commit rule from `core/docs/WORKFLOW.md` and copy
  `overlays/claude-code/files/scripts/spawn_codex.sh` and `codex_worker.py` into `scripts/` (`chmod +x`,
  `git add --chmod=+x`); a sync keeps them updated from then on. Copy `close_worker.sh` too
  and the worker-sidecar ignore rules from `core/.gitignore` into your project ignore file.
  Update Codex briefs with the atomic publication protocol and run spawn's printed wait
  command in the background.
  **ACTION:** a Codex worker started by the first v0.11 `spawn_codex.sh` (2026-10-09)
  recorded its session id in the git directory: `.git/codex-session-NAME`, or
  `.git/worktrees/NAME/codex-session-NAME` for a worktree worker. The new script does not
  read it: resume such a worker with `--resume <that id>`, then delete the file.
- **A review no longer dies on the kit's own limits** (`agent_process.py`, the adapters,
  `review.sh`): a review attempt now gets 3600 seconds (maximum 7200) and a Claude review
  200 turns (maximum 500); three high-effort reviews had died on 1800 seconds and 12 turns.
  `REVIEW_MAX_TURNS` is new and reaches the Claude CLI through `review.sh`, like
  `REVIEW_TIMEOUT_SECONDS`. The turn setting is validated only when Claude is the reviewer
  or fallback is allowed. Codex has no turn limit. Proposal ceilings stay at 3600 seconds
  and 100 turns. **ACTION:** copy `$KIT/core/scripts/agent_process.py` to `scripts/agent_process.py`,
  `$KIT/core/scripts/claude_bridge.py` to `scripts/claude_bridge.py`,
  `$KIT/core/scripts/codex_bridge.py` to `scripts/codex_bridge.py`,
  `$KIT/core/scripts/review_dispatch.py` to `scripts/review_dispatch.py`,
  `$KIT/core/scripts/review.sh` to `scripts/review.sh`, keeping your project configuration, and
  `$KIT/core/scripts/test_claude_bridge.py` to `scripts/test_claude_bridge.py`.
- **A spawned handoff records its question** (issue #42; the plugin's handoff command):
  item 7 now matches `docs/HANDOFF.md`; the upgrade checklist no longer copies
  `spawn_worker.sh` twice.
- **Linked test directories fail the kit check** (issue #65; `scripts/check_kit.py`):
  a linked package can no longer leave failing tests undiscovered, including Windows
  junctions on Python 3.10/3.11. Cloud reparse folders (including OneDrive) are accepted.
  Unreadable test directories fail discovery too.
- **The merge-action test probes mktemp** (issue #66; `tests/test_sync_kit.py`):
  BSD and GNU temporary-folder behavior is tested on every host, including macOS.
- **Strong review closure fails on missing or hidden index evidence** (issue #69;
  `.githooks/commit-msg`): a failed listing refuses a commit with a `Done:` trailer. Quoted paths under
  `docs/reviews` and a different case of that directory are refused before closure checks.
  Only review paths are listed, even when the caller exports `GIT_LITERAL_PATHSPECS`.
- **Context warnings survive concurrent prompts and compaction** (issue #70): the hook
  announces each step once, keeps its highest step until compaction, and re-arms even when
  a new request already followed the boundary. Upgrading an integer step preserves the
  warning already given in the current compaction. A state of the wrong type (a null or
  string step) counts as no state, so the hook is not silenced. **ACTION:** copy
  `$KIT/overlays/claude-code/files/.claude/hooks/context_size.py` to `.claude/hooks/context_size.py`.
- **A completed review is never relabelled adapter_error** (issue #71; `scripts/review_dispatch.py`,
  `scripts/review.sh`, `docs/REVIEW_RUNNING.md`, `docs/WORKFLOW.md`): an adapter that failed
  after it had recorded and handed over its result (printing the review) had that result
  replaced with `adapter_error`, so a completed, paid review was reported as none. The handed-over
  result now stands, the later failure is kept as `error_after_result`, and a checkout changed
  meanwhile still fails as `stale_checkout`. The docs say when a self-test may share the
  review's worktree: only when it writes files Git ignores and nothing else. **ACTION:** copy
  the core scripts, and update the self-test lines in `docs/WORKFLOW.md` (the lead's step 1)
  and `docs/REVIEW_RUNNING.md`.
- **A file deleted inside a sparse checkout's rules is refused** (issue #53; `scripts/claude_bridge.py`):
  under a sparse checkout every missing skip-worktree file was tolerated, so a file inside
  the cone marked skip-worktree by hand and deleted was a deletion the diff omitted. Only a
  path the sparse rules exclude may be missing now, asked of `git sparse-checkout check-rules`
  in one call; a Git older than 2.42, or a failed check, refuses the review. **ACTION:** copy
  the core scripts, and copy the Git 2.42 requirement in `docs/DEV_SETUP.md`.
- **The self-test fails when it changes the worktree** (`scripts/check.sh --self-test`, and the
  kit's own wrapper): it compares HEAD, the index, `git status --porcelain
  --untracked-files=all` and per-file content hashes of every tracked and untracked non-ignored
  file, using `git hash-object --no-filters --stdin-paths`, before and after; a difference FAILS
  it, naming each path. Files Git ignores may change. This proves only the end state is unchanged:
  sharing a review's worktree is allowed only when every case writes nothing but ignored files
  (`docs/WORKFLOW.md`, step 1); a non-ignored file written and removed can still fail the review
  as `stale_checkout`.
  **Your self-test can turn red after this upgrade without any code change:** a case, a
  build or a test that leaves an untracked file Git does not ignore now fails it. Make that
  case remove what it writes, or ignore its output path in `.gitignore`. **ACTION:** copy
  `$KIT/core/scripts/check.sh` to `scripts/check.sh` with your filled-in values, and update
  the self-test lines in `docs/WORKFLOW.md` (the lead's step 1, "Writing a gate") and
  `docs/REVIEW_RUNNING.md`.
- **Both adapters keep their handed-over status** (`scripts/claude_bridge.py`,
  `scripts/codex_bridge.py`): run directly, a failure after a result was recorded and handed
  over (printing it) made the Claude adapter print a "failed" line after the "completed" one
  and exit 2, and the Codex adapter raise it, ending in a FAIL line. The handed-over status decides the
  exit; the failure is a NOTE on stderr naming the evidence, and the dispatcher records it as
  `error_after_result`. The dispatcher's `stale_checkout` message now says "a new untracked
  file Git does not ignore", and the review threat model names a write to an ignored file as
  an accepted limit. **ACTION:** copy the core scripts.
- **A review names its next attempt** (issue #68, item 1; `scripts/review.sh`, `scripts/review_dispatch.py`):
  before each adapter runs, including a fallback, it prints the model and effort as
  "about to run"; adapter preflights may still stop the attempt before any model call.
  **ACTION:** copy `$KIT/core/scripts/review_dispatch.py` to `scripts/review_dispatch.py`.
- **Line-ending churn stops a review** (issue #68, item 2; `scripts/review.sh`,
  `scripts/review_dispatch.py`): two scope-wide line-count queries refuse files whose
  changed lines are mostly CR-only, including normalization mixed with real edits.
  The refusal names the file and repair; `REVIEW_ALLOW_EOL_ONLY=1` explicitly permits
  a deliberate normalization.
  **ACTION:** copy `$KIT/core/scripts/review_dispatch.py` to `scripts/review_dispatch.py`.
- **The lead's Stop hook stays out of a worker's self-test** (issue #68, item 3): the lead
  uses `git -C <worktree>` and keeps its shell in its own checkout. `check.sh --self-test`
  atomically publishes its shell pid and lock token to `check-selftest` beside the gate lock
  and removes it on exit. Linked markers are refused without changing their target data.
  After the cheap gated-paths check, the Stop hook skips with a NOTE only while that shell
  lives (an unreaped zombie does not count where `ps -o stat=` works), its token equals the
  lock file, and the lock is held. Surviving build descendants
  cannot make a killed self-test's marker skip the gate.
  File names never do: a `.selftest.*` file, tracked or not, no longer skips or blocks.
  **ACTION:** add the two sentences under "The lead's steps when a branch is ready" in
  `$KIT/core/docs/WORKFLOW.md` to your `docs/WORKFLOW.md`, copy
  `$KIT/overlays/claude-code/files/.claude/hooks/gate_on_stop.sh` to `.claude/hooks/gate_on_stop.sh`,
  keeping your gated paths and file pattern. Merge the marker removal in `cleanup` and the
  full marker-publication block at the start of `self_test` from `$KIT/core/scripts/check.sh`
  into `scripts/check.sh`. Upgrade both marker publication and the hook together. Without them
  the hook waits for a self-test's lock as for any gate run.
- **An incremental-build brief names both shared dependencies** (issue #68, item 4;
  `docs/HANDOFF.md`, "The brief"): always-run inputs belong to every stage's dependency
  set, and a changed driver script invalidates every stage. **ACTION:** add the two
  sentences in item 3 from `$KIT/core/docs/HANDOFF.md` to your `docs/HANDOFF.md`.
- **Bootstrap records executable Git modes on Windows** (issue #59; `bootstrap.sh`): in
  a Git repository it records executable modes for every kit-named shell script and hook,
  including differing older or customized copies, even when
  `core.fileMode=false`. Repair runs before a gate-content conflict stops installation.
  Only stage-0 100644 entries are repaired; symlinks and other index types stay unchanged.
  Tracked files keep their staged content, including in repository subfolders;
  new nonignored kit scripts are staged only at the repository top level, and only after
  the conflict check: a stopped install stages nothing new. Bootstrap prints each staged
  path and notes once that other kit files were not staged. Subfolder installs print
  the exact `git add --chmod=+x -- <files>` commands to run from the target instead.
  Ignored files stay out of the index.
  Other project-owned scripts are left alone. **ACTION:** rerun bootstrap with the project's
  overlays to repair kit modes. A customized gate still returns STOPPING (exit 1), but its
  mode is repaired; merge content separately, without `--force`.
- **Python that does not run** (issue #67): on Windows `python3` may be a Store alias that is
  on PATH but exits 9009. The Claude Code overlay's three Python hooks now start through the
  new `.claude/hooks/py.sh`, which runs the first of `python3`, `python`, `py -3` that runs;
  before, each hook failed there and Claude Code went on without it, so `git reset --hard`
  on a dirty tree was not refused. `check.sh`, `review.sh`, `doctor.sh`, `spawn_worker.sh`,
  `close_worker.sh` and `clean_worktrees.sh` choose the same way, by running the candidate
  instead of `command -v`. The sync updates `doctor.sh` and the three worker scripts
  (KIT-OWNED), but none of the files below. **ACTION:** copy
  `$KIT/overlays/claude-code/files/.claude/hooks/py.sh` to `.claude/hooks/py.sh`, and in
  `.claude/settings.json` replace `python3 ` at the start of each Python hook command with
  `sh "$CLAUDE_PROJECT_DIR/.claude/hooks/py.sh" `. In `scripts/check.sh` and
  `scripts/review.sh` (the project's own), replace `command -v python3` and `command -v
  python` in the `kit_python=` lines with `python3 -I -c '' </dev/null` and `python -I -c ''
  </dev/null`. Then, with an uncommitted change, `echo
  '{"tool_name":"Bash","tool_input":{"command":"git reset --hard"}}' | sh .claude/hooks/py.sh
  .claude/hooks/guard_destructive_git.py` must print BLOCKED.
- **A worker starts on native Windows** (issue #72; `scripts/spawn_worker.sh`): wt.exe drops
  every double quote it is handed, so inline `--settings` JSON reached claude broken and the
  tab closed at once with no error shown. The tab now runs a script that holds its command
  and deletes itself, a claude that ends within ten seconds keeps the tab open with its exit
  code, and the brief is named by its Windows path (`C:/...`), not Git Bash's `/tmp/...`.
- **A worker is never ended mid-run, and the lead knows when it cannot hear one**
  (`scripts/close_worker.sh`, `scripts/spawn_worker.sh`, `docs/WORKFLOW.md` "Worker cost"):
  `close_worker.sh` ends nothing while a gate (`check.sh`, by its lock) or a git operation
  (`index.lock`) runs in the worker's worktree, since a session ended mid-run orphans the run.
  On native Windows `spawn_worker.sh` waits up to 30 s for the worker's process, fails when
  none starts, and warns when Claude Code did not register it as a peer session: ListAgents
  then does not list it and no idle notice comes, so the lead watches its tab.
- **Running work is never ended without a reason that holds** (`AGENTS.md`, "Task
  discipline"): a session, a review, a gate or a build keeps running unless the owner asked
  for it to end, or it is provably finished or hung. On 2026-10-08 a stopped review left its
  `codex exec` running orphaned, and killed workers left their `check.sh` racing the lead's
  gate. **ACTION:** add the rule to your `AGENTS.md` under "Task discipline".
- **Routine commands ask no one** (`.claude/settings.json`, Claude Code overlay; the list the
  owner chose with project_leeway): the gate (`scripts/check.sh` and `--self-test`, exactly)
  and read-only commands (`git status`, `git log`/`diff`/`show` only as `git <cmd>
  --no-textconv --no-ext-diff ...`, `git worktree list`, `cat`,
  `head`, `tail`, `ls`, `wc`, `grep`, `date`, `pwd`, PowerShell `Get-Content` and
  `Get-ChildItem`) run without a permission prompt; ending a process, deleting a file and every
  other command still ask. `git branch` is allowed only in exact listing forms (a `*` admitted
  `git branch -vD`), no rule has a `*` before its subcommand (`git -C * diff*` admitted
  `git -C . branch -D x`), a `*` follows a whole word (`git diff*` admitted `git difftool
  --extcmd=...`, `date*` admitted `date -s`), and `git *--out*`, `git *--ext*`,
  `git *--textc*` and `git *--sub*` are denied (the first overwrites a file, the
  others run the repository's or a submodule's diff drivers). These prefixes cover Git
  versions that accept unambiguous long-option abbreviations; `--out`, not `--ou`, so
  `git checkout --ours` stays usable.
  The allow rules guard only the command's own arguments. The repository's local git
  configuration, including `diff.submodule` and every submodule's own configuration, is
  trusted: `git status` and the gate already run what it names
  (`core.fsmonitor`). No allow rule can defend against a hostile local config.
  **ACTION:** a project with its own `.claude/settings.json` adds the
  overlay's `permissions` block, `deny` included. Replace any plain `git diff`, `git show` and
  `git log` allowances with the overlay's `--no-textconv --no-ext-diff` forms: a plain one runs
  a repository-configured textconv driver, so a read could run any command.
- **A killed self-test's injection is named, not guessed at** (`scripts/boundary_selftests.sh`,
  worked example): SIGKILL and `taskkill /F` run no trap, so an injection can be left behind
  and every later self-test refuses to start. The refusal now says so and names the file to
  check and delete by hand; the self-test never deletes it itself, since a junction above it
  or an edit after the check would put the owner's content in its place. **ACTION:** add the
  same two lines to each refusal in your `scripts/boundary_selftests.sh`. Move the existing-path
  refusal BEFORE the baseline check, since a stale injection makes the baseline fail too.
- **A review archive written on Windows matches its record** (`scripts/agent_usage.py`): the
  archive was written in text mode, so Windows stored CRLF while the usage record hashed the
  LF text, and the next review of the same task refused the earlier archive as changed. The
  archive now holds the text's own bytes.
- **The kit check passes only with its PASS line** (`scripts/check.sh`, the kit's own wrapper):
  a self-test on native Windows exited 0 without printing `KIT CHECK: PASS`. The wrapper now
  asks the check to leave a file right after that line and fails an exit 0 without it. Kit
  only; nothing to do in a project.
- **A low allowance ends** (`docs/WORKFLOW.md`, "Model routing", rule 7; a v0.10 rule): the
  rule said when a low allowance starts and not when it ends, so a lead kept the low side
  reviewing only after its allowance had reset. It now ends when that side's allowance resets
  or the owner says otherwise; then the mode before it applies again. A
  decision made for a moment never outlives its reason. **ACTION:** replace rule 7's ending in
  your `docs/WORKFLOW.md` with these closing sentences.
### Upgrading a project from v0.10

<!-- Each numbered item is one checklist entry. sync-kit.sh prints an item from its marker to
the end of the item, so an item holds no blank line and no line that starts a list. -->

Work from the project's root, top to bottom. `KIT` is a fresh, full clone of the kit at v0.11
or later (`sync-kit.sh . --merge` needs v0.12 or later; without it merge by hand). A v0.10
project has no `docs/kit/.kit-commit`, so `--merge` stops until `--base <commit>` names the
kit commit its v0.10 came from. v0.10 has no release tag: take the kit's last commit before
the project recorded its version, `git -C "$KIT" rev-list -1 --first-parent
--before="$(git log -1 --format=%cI -- docs/kit/.kit-version)" HEAD`, and run
`"$KIT/sync-kit.sh" . --merge --base <that commit>`. The sync checks the base against the
project's kit-owned files and stops, writing nothing, when they differ: then merge by hand.
Each `--merge` below needs that `--base` until item 13 records the version and the commit. The bullets
above hold the reasons and each its own ACTION item, several of them the same instruction for
the next batch of one file; this list names each file once, in its final state, and covers
every one of them: tick a bullet's box in `docs/kit/UPGRADE.md` when an item here did what it
says. Item 2 writes what `sync-kit.sh` owns; every other file is the project's: a script, hook
or definition is copied whole (items 3 and 5), a project-owned file is merged (items 4 and 7 to
10), `.claude/settings.json` is the owner's (item 6).

1. **ACTION:** Prerequisites first: Python 3.11 or newer (3.10 reached end of life on
   2026-10-01), Git 2.42 or newer (`docs/DEV_SETUP.md`) and Claude Code 2.1.295 or newer. A
   Linux or WSL2 host installs `bubblewrap` and `socat` (the Claude reviewer's shell is
   sandboxed; `scripts/doctor.sh` says so once item 2 has run). On native Windows the review
   self-test needs pip's bundled launcher. If the Claude account's e-mail differs from git's
   `user.email`, set `MYAGENTKIT_PRIVATE_EMAILS` in the user-level settings `env`. A project
   with ShellCheck installed may go red on its own scripts once item 4 brings the gate's
   ShellCheck check: fix each finding or disable it with a reason. A kit checkout used for the
   kit's own check on macOS needs `brew install bash`.
2. **ACTION:** Run `"$KIT/sync-kit.sh" .`. It overwrites the KIT-OWNED files: the four
   `.githooks` files (`pre-commit`, `pre-merge-commit`, `commit-msg`, `post-merge`),
   `scripts/doctor.sh`, `scripts/fix_crlf.sh`, `scripts/context_buckets.py`,
   `scripts/working_mode.py`, `scripts/agent_cost.py`, `scripts/usage_summary.py`, and the
   Claude Code overlay's worker scripts the project already has (`spawn_worker.sh`,
   `spawn_codex.sh`, `codex_worker.py`, `close_worker.sh`, `show_workers.sh`,
   `watch_workers.sh`, `clean_worktrees.py`). It installs a kit-owned overlay file the project
   lacks only when the project already holds a kit-owned file of that overlay; otherwise
   copy a missing one from `$KIT/overlays/claude-code/files/scripts/` by hand (a Codex project's
   `spawn_codex.sh` and `codex_worker.py`, and `close_worker.sh`; `chmod +x` and
   `git add --chmod=+x`), and the sync keeps it from then on. A `conflict:` line that calls the
   file the project's (`so it is the project's`: a Git LFS `post-merge`, a `commit-msg` of
   your own) is never overwritten: move yours aside first, as the sync says, a hook of yours to
   `.githooks/<same name>.project` (executable, with a `#!` line; the kit's hook runs it first),
   any other file out of the way to carry what it did into the project's own files by hand
   (`$KIT/docs/RETROFIT.md`). Only a line that calls it the kit's own file from an earlier
   version is a copy without the KIT-OWNED header: copy the kit's file whole over that one.
   Then run the sync again. A project's own checks in `scripts/doctor.sh` move to `scripts/doctor.project.sh`. It also
   writes `docs/kit/UPGRADE.md` with this release's items, and records no version (item 13
   does).
3. **ACTION:** Copy these scripts whole from `$KIT/core/scripts/` into `scripts/`, replacing
   yours: `review.sh` (keeping your project configuration), `claude_bridge.py`,
   `codex_bridge.py`, `review_dispatch.py`, `agent_process.py`, `agent_usage.py`,
   `owns_check.py`, `test_claude_bridge.py`, `review_test_support.py`, and the other review
   companion files that `core/docs/DEV_SETUP.md` lists. Update the Claude plugin
   (`claude plugin update`) and the Codex plugin to the same kit version: an older adapter
   sweeps leftover review copies by age alone and can remove a new adapter's live copy. While no
   review is running, delete leftover `myagentkit-review-*` and `myagentkit-codex-*` temporary
   folders that have no `.lock` sibling (unmarked legacy copies are kept). In `review.sh` and
   `check.sh` (item 4), the `kit_python=` lines probe Python by running it: `python3 -I -c ''`
   and `python -I -c ''`, each with `</dev/null`, replace `command -v python3` and
   `command -v python` (a Windows Store alias passes the second form and does not run). From now
   on: write every disposition with its key, run the first large review and read its duration
   from the chain record's timestamps (if 3600 s cut it off, ask the owner whether
   `MAX_REVIEW_TIMEOUT` rises).
4. **ACTION:** Merge the kit's changes into `scripts/check.sh`, keeping your filled-in values
   (`sync-kit.sh . --merge --base <commit>`, the base named above, or by hand from
   `$KIT/core/scripts/check.sh`): the Done-history
   section, the ShellCheck hook selector, the module-map section (then fill `module_roots` if
   the project has modules), the Git 2.42 requirement, the self-test lines that keep it from
   changing the worktree, and, from the marker-publication change, the marker removal in
   `cleanup` and the whole marker-publication block at the start of `self_test`, together with
   the Stop hook of item 5. In `scripts/boundary_selftests.sh` (only if you adapted the
   existing-file example) take `probe_env`, `probe_delete`, `probe_audit` and the `cp` line from
   `$KIT/core/scripts/boundary_selftests.sh`, add the same two lines about a killed run's
   injection to each refusal, and move the existing-path refusal BEFORE the baseline check,
   since a stale injection makes the baseline fail too. Add `* text=auto` to the project's
   `.gitattributes` and these rules to its `.gitignore`: `/.claude/mode.lock`, the
   worker-sidecar rules of `core/.gitignore`, and, for a Unity project, the overlay's
   `.gitignore` fragment.
5. **ACTION:** Copy the Claude Code overlay's hook files whole from
   `$KIT/overlays/claude-code/files/.claude/hooks/` into `.claude/hooks/` (hooks are not
   synced): `guard_destructive_git.py`, `guard_private_email.py`, `guard_worker_route.py`,
   `guard_boundaries.py`, `plain_report.py`, `progress_reminder.py`, `context_size.py`,
   `after_compact.txt`, `py.sh` and `gate_on_stop.sh` (keeping your gated paths and file
   pattern; upgrade it together with the `check.sh` marker publication of item 4, or the hook
   waits for a self-test's lock as for any gate run). Keep project patterns for the plain-report
   hook in `.claude/plain_report_labels.json`, not in the commit hook. Once item 6 is applied,
   prove `py.sh`: with an uncommitted change, piping a Bash tool call that runs a hard git reset
   into `sh .claude/hooks/py.sh .claude/hooks/guard_destructive_git.py` must print BLOCKED. Also
   copy the overlay's agent definitions and rule: `.claude/agents/worker.md` and
   `.claude/agents/diff-reviewer.md` from `$KIT/overlays/claude-code/files/.claude/agents/`,
   preserving the project's own settings in `worker.md`, and `.claude/rules/state.md`.
6. **ACTION:** The owner prepares, applies and commits `.claude/settings.json` (Claude Code's
   auto mode refuses an agent's write to its own settings; a worktree worker runs the committed
   file). Add from `$KIT/overlays/claude-code/files/.claude/settings.json`, copying no whole
   file (it would drop your `env` values, deny rules and plugin choices): the hook entries of
   item 5 (`Stop` for `plain_report.py`, `PostToolUse` for `progress_reminder.py`, `PreToolUse`
   with matcher `Agent|Task` for `guard_worker_route.py`, the `SessionStart` entry, and the
   entries of the git and e-mail guards), `autoCompactWindow`, `promptCacheTtl`,
   `subagentPromptCacheTtl`, the `env` entry `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL`, and the
   whole `permissions` block, `deny` included (replace any plain `git diff`, `git show` and
   `git log` allowance by the overlay's `--no-textconv --no-ext-diff` forms: a plain one runs a
   repository-configured textconv driver). Replace `python3 ` at the start of each Python hook
   command with `sh "$CLAUDE_PROJECT_DIR/.claude/hooks/py.sh" `.
7. **ACTION:** Merge the kit's changes into `docs/WORKFLOW.md` (`sync-kit.sh . --merge --base
   <commit>`, the base named above, or by hand from `$KIT/core/docs/WORKFLOW.md`): "Model routing" and "Working modes, by name" over
   your own routing text, keeping your model names, with rule 7 and its low-allowance ending,
   the audit paragraph of the closed-findings gate, the review launch and recovery rules, the
   STATE protocol lines, the self-test lines (the lead's step 1, "Writing a gate") and the two
   sentences under "The lead's steps when a branch is ready". Then rewrite the
   `**Working mode:**` line of `docs/STATE.md` (add it if absent) to `solo`, `cross` or `saver`
   through `--read-state` and `--replace-state`, BEFORE you run `scripts/working_mode.py`:
   claude-only becomes solo; cross-performance, claude-first and codex-first become cross;
   cross-saving, claude-saver and codex-saver become saver with a `(low: ...)` note; and the
   mode table of `WORKFLOW.md` has those three rows. The script refuses the old names.
8. **ACTION:** Merge the kit's changes into the review and worker documents, each from
   `$KIT/core/docs/` (`sync-kit.sh . --merge --base <commit>`, the base named above, or by
   hand): `docs/REVIEW_GATE.md` and
   `docs/REVIEW_RUNNING.md` (the self-test lines, the launch and recovery rules, the two
   sentences of the accidents rule, `REVIEW_ROUND_EXCEPTION`, written before a third completed
   review under a label), `docs/HANDOFF.md` (the worker-lifecycle sections, the `Owns:`
   paragraph, the two sentences of the incremental-build brief), `docs/USAGE.md`,
   `docs/GOTCHAS.md` (its new paragraphs are optional), `docs/STRONG_REVIEW.md`. In
   `docs/DEV_SETUP.md` section 1, "Wire the commit gate", replace the embedded line-ending
   repair program with the `sh scripts/fix_crlf.sh` paragraph of the kit's file, and take the
   Git 2.42 requirement and the review companion list.
9. **ACTION:** Copy `docs/COMMUNICATION.md` and `docs/GLOSSARY.md` whole from `$KIT/core/docs/`
   (merge `COMMUNICATION.md` when you changed it), fill `{{CHAT_LANGUAGE}}` in `AGENTS.md` and
   in `docs/COMMUNICATION.md`, and `{{KNOWN_TERMS}}` in the glossary (setup interview question
   12). In `docs/PROJECT.md` add `**Web contact:**` near the top (the e-mail guard points at it)
   and change the rights row to "Supersede ...".
10. **ACTION:** Take the kit's changes into `AGENTS.md` and `docs/AGENTS.md`, re-applying the
    project's own lines: the new lines and section of the lessons from the kit's development,
    the two sentences of the accidents rule, the STATE protocol lines, and the rule that running
    work is never ended without a reason that holds, under "Task discipline". A Unity project
    takes the overlay's updated `AGENTS.md`, `UNITY_SETUP.md` and `unity_gate.sh` too.
11. **ACTION:** Backends: a project with `.myagentkit/backends/NAME.env` moves each file to the
    backend folder (`MYAGENTKIT_BACKENDS_DIR`, `%APPDATA%\myagentkit\backends` or
    `~/.config/myagentkit/backends`); create a backend file by hand where a named
    Claude-compatible backend is wanted; configure the documented Codex administrator read-deny
    policy where supported. A project that bootstrapped on native Windows reruns bootstrap with
    its overlays to repair the kit's executable modes (a customized gate still returns STOPPING,
    exit 1, with its mode repaired; merge its content separately, without `--force`).
12. **ACTION:** Workers: re-spawn every existing worker that still runs the older hook or
    scripts, and shorten the worker name or the checkout path when spawn refuses a generated
    path. Start a fresh lead with the enabled or the disabled behaviour-appendix command. A
    Codex worker the first v0.11 `spawn_codex.sh` (2026-10-09) started recorded its session id
    in the git directory (`.git/codex-session-NAME`, or
    `.git/worktrees/NAME/codex-session-NAME`): resume it with `--resume <that id>`, then delete
    the file. Adopt the lead-owned commit rule of `core/docs/WORKFLOW.md`, update Codex briefs
    with the atomic publication protocol, and run spawn's printed wait command in the
    background.
13. **ACTION:** Prove the result: `./scripts/doctor.sh`, then `./scripts/check.sh` (expect
    `CHECK: PASS`); the boundary fixture tests run inside it. A red gate or a check without its
    fixture test is not finished. Then record the version BEFORE the upgrade commit, so the
    commit carries it: run `"$KIT/sync-kit.sh" . --actions-applied` (every box of
    `docs/kit/UPGRADE.md` ticked), run `./scripts/check.sh` again, and commit everything the
    upgrade changed together with `docs/kit/.kit-version` in one commit. Then send every
    problem, surprise or doubt about MyAgentKit upstream through `/myagentkit:kit-feedback` (an
    issue), not only into the project's notes.

## v0.10 — 2026-10-07

Native Windows (Git for Windows' `sh` with python.org CPython) becomes a host the kit runs on,
not one it sends to WSL: the gate lock, a review run, a worker's spawn and close, and the
worktree clean-up each work there, with tests that run on native Windows (a CI job of their
own). It started as two fixes for a project that moved there from WSL, hardened by cross-model
reviews. Why each change is safe is in `RESEARCH_LOG.md` (2026-10-06 and 2026-10-07).

- **A low allowance** (`docs/WORKFLOW.md`, "Model routing", rule 7): when the owner says one
  side's allowance is low, that side only reviews and the other side fixes; reviews run at
  the lowest effort that fits, and the top model or highest effort needs the owner's yes
  (rule 2 says so too). A running review is not cancelled to lower its effort; a quota
  failure leaves its rerun command and waits. `docs/REVIEW_RUNNING.md`: a test failure in Codex's
  sandbox is set aside only when its diagnostic names a sandbox restriction and the same
  test passes outside the sandbox on the same platform.
- **The strong review cycle** (issue #61; `docs/WORKFLOW.md`, "The strong review cycle"): at
  least every ten days the strongest model available reviews what reached the main branch,
  a strong model of the other family reviews that report and the triage, and the owner
  decides after one exchange. New project-owned template `docs/STRONG_REVIEW.md` (the open
  list); reports are `docs/reviews/strong-<date>-<model>.md`. A closed finding is deleted:
  `.githooks/commit-msg` and `check.sh` refuse a `Done:` id that the list or a report still
  names. `check.sh` prints `NOTE [strong-review]` when the list exists and no report was
  added in ten days. **ACTION:** copy `$KIT/core/docs/STRONG_REVIEW.md` to
  `docs/STRONG_REVIEW.md` to start the cycle (the reminder stays silent without it).
- **Lead context line** (issue #58; `docs/WORKFLOW.md`, "Worker cost", rule 8): past 200k
  tokens of context the lead recommends `/compact` or a hand-off, whichever is cheaper at
  that moment, never a hand-off by default. The Claude Code overlay's new UserPromptSubmit
  hook `.claude/hooks/context_size.py` tells the agent the size once per 50k step past the
  line. `AGENTS.md` MENTION ONCE gains "a cheaper way you can see". `scripts/agent_cost.py
  --latest` now finds the transcripts of a project whose path holds `_` or another
  non-alphanumeric character. **ACTION:** a project with its own `.claude/settings.json`
  adds the UserPromptSubmit entry from the overlay's.
- **Ponytail mode** (`setup/INTERVIEW.md`, question 11; default yes): the Claude Code
  overlay's `.claude/settings.json` turns on `ponytail@ponytail`, which makes sessions and
  workers try the smallest working solution first: reuse, standard library, platform, one
  line, then the minimum code. It comes from `DietrichGebert/ponytail`'s own marketplace at
  the latest version, the same id as a user-level install, so it loads once. Token cost at
  each session and sub-agent start is not measured; it saves most on code-writing workers.
  Codex installs it with `codex plugin add ponytail@ponytail`. **ACTION:** to
  turn it on in an existing project, add the overlay's `extraKnownMarketplaces` and
  `enabledPlugins` entries to `.claude/settings.json`.
- **Model routing rules** (`docs/WORKFLOW.md`, "Model routing"): work is sorted into three
  tiers; the lead chooses model and effort for every errand with equal care and writes both
  into the brief; the top models (Codex Astra, Claude Fable) are the lead's pick for one
  errand and only where the subscription includes them; a failed mechanical errand is rerun
  one tier up; after three review rounds that do not come back clean the lead raises the
  effort or the model of the fixer, and of the reviewer when needed; model versions are kept
  current and a switch is reported to the kit; tier boundaries are moved by measured rejects
  and rework. `setup/INTERVIEW.md` carries an example tier table, provisional until the
  allowance draw per model is measured. `scripts/spawn_worker.sh` now refuses a worker
  without `--model` and `--effort`; a sub-agent gets both on every Agent call. The kit's own reviewer
  pins move to Codex `gpt-6.1-sol` and Claude `claude-opus-5-5`.
  **ACTION:** copy the six rules into your `docs/WORKFLOW.md` under "Model routing", fill your
  routing table by tier, and update the pins in your `scripts/review.sh` and the `model` in
  `~/.codex/config.toml` to the newest models your subscriptions include. Every
  `spawn_worker.sh` call in your briefs and notes now needs `--model` and `--effort`.
- **Worker scripts take Windows paths.** `spawn_worker.sh`, `close_worker.sh` and
  `watch_workers.sh` called by a path with backslashes (`D:\p\scripts\spawn_worker.sh`) looked
  for their sibling scripts in the current folder, and the spawn stopped at "the watcher
  exited 127". A brief named `C:\dir\brief.md` reached the worker as the caller's folder
  followed by that whole string. Both now resolve as with `/`.
- **The gate's Windows lock self-test under a short-name TEMP.** Where TEMP is an 8.3 short
  name (`C:\Users\RUNNER~1\...`, as on a GitHub Windows runner), four claim cases of
  `./scripts/check.sh --self-test` waited for the lock instead of being refused, and the
  self-test failed: the case named the lock by its short path, the gate by its long one. The
  case now computes the path as the gate does.
- **The kit's own check runs on native Windows** (`scripts/check.sh`, issue #56). Each suite
  or case that needs a POSIX host prints one NOT RUN line with its reason. CI's Linux and macOS
  jobs still run everything. Two Windows defects it found are filed: #59 (a project
  bootstrapped on Windows commits its scripts without the executable bit) and #60 (the
  existing-file boundary probe starts the Python install manager; fixed in v0.11).
- **The gate lock on native Windows.** `scripts/check.sh` run by Git for Windows' `sh` with a
  Windows `python3` failed every run with `FAIL [lock]: python3 has no fcntl module`, so every
  commit there was blocked. On that host the lock is now the lock file opened for writing
  without write sharing; the holder makes its handle inheritable and runs the gate as its
  child, so the gate and every process it starts hold the lock, and Windows releases it when
  the last of them exits. Nothing is reclaimed and no pid is trusted, as on POSIX. A second
  run waits with the same `NOTE [lock]` line (the hint names Resource Monitor instead of
  `fuser`) and honours `GATE_LOCK_WAIT` (`NOT RUN [lock]`, exit 75). On Windows
  `GATE_LOCK_FD` holds the holder's Win32 handle: a nested run proves it is open in its own
  process on this lock file, compared by the whole `FILE_ID_INFO` (volume serial and 128-bit
  file id), with write access, while a fresh open for writing fails with a sharing violation,
  so variables copied out of a killed gate fail `FAIL [env]`. A volume that gives no
  `FILE_ID_INFO` fails `FAIL [lock]` by name in a nested run. The self-test marker is a random
  token the holder clears when the gate ends. A gate that dies of a signal exits 128 + N
  there, never 0. On a host whose `uname -s` is MSYS, MINGW or Cygwin the lock path is kept in
  the `C:/` form a native program receives (`cygpath -m`); a `cygpath` that is merely on a
  POSIX `PATH` is never run. A linked worktree's `C:/` git path is read as absolute. The POSIX
  lock is unchanged. `python3` without `fcntl` on any other system still fails `FAIL [lock]`
  by name. The host (`os.name`) picks the lock, never whether `import fcntl` works, and both
  lock programs run isolated (`python3 -I`), so a `fcntl.py` or another stand-in module in
  the checkout or on `PYTHONPATH` is never imported. `docs/DEV_SETUP.md` and
  `docs/GOTCHAS.md` say so.
- **`--self-test` proves the Windows lock.** Thirteen new cases on native Windows: a nested run
  refuses a writable handle on another file, a read-only handle on the held lock file, a
  write handle while nothing holds the lock, a fresh open refused for a reason other than the
  lock (a read-only file), and a file id equal to the lock's in its volume and first 64 bits
  only; a volume without `FILE_ID_INFO` fails closed; the lock refuses a reparse point at its
  path (set with a tag any user may set, so the case never needs the symlink privilege and is
  never skipped); a gate killed by a signal never exits 0; the holder passes a failing gate's
  exit status on; a killed lock holder leaves the lock with the gate it started; the
  holder imports no stand-in `fcntl.py` or `secrets.py` from `PYTHONPATH`; and Ctrl-C (a
  `CTRL_C_EVENT` sent to a hidden console of the case's own) stops the gate and its build, the
  gate exits nonzero, the holder outlives it and exits 130, and the next gate takes the lock;
  and a Ctrl-C while the holder waits for the lock, before the gate exists, starts no gate
  and exits 130. The holder survives Ctrl-C through a handler that records it, not
  `SIG_IGN`; the two behave alike for the gate on the hosts measured, so the first case
  proves the survival, not which one, and the second proves the record (with a handler that
  records nothing, the Ctrl-C reached no gate, and the gate then ran and passed). The host check and the case runner run isolated
  (`python3 -I`) beside a `sitecustomize.py` on `PYTHONPATH` that marks its import and calls
  the host POSIX; imported, it would have skipped every Windows case, so the import fails the
  self-test there and the skip line is printed only without it. Each case
  asserts its exit status as well as its message, and the gate's throwaway copy passes right
  after it holds the lock, so a guard that prints its refusal and then carries on fails its
  case. On POSIX, a `cygpath` on `PATH` is never run. On every host, a nested run with a
  stand-in `fcntl.py` on `PYTHONPATH` passes without importing it. The Windows cases print one
  `skip` line on POSIX, and the POSIX case one on MSYS, MINGW and Cygwin.
- **Shell scripts and hooks check out with LF everywhere.** Git for Windows' default
  `core.autocrlf=true` checked them out with CRLF, which `sh` cannot run, so on such a clone
  the gate, the hooks and `doctor.sh` could not start. Bootstrap now installs a
  `.gitattributes` with `*.sh text eol=lf` and the same for each of the gate's four hooks by
  name, and the kit's own clone carries the rule for its scripts. A project that already has
  a `.gitattributes` keeps it: bootstrap appends the rules it lacks, and never replaces the
  file, `--force` included. An existing project adds them by hand (item 1 below);
  `docs/DEV_SETUP.md` section 1 says why.
- **`spawn_worker.sh` on native Windows.** There is no tmux there, and the script stopped
  with `tmux is not installed`. On Git for Windows' `sh`, MSYS2 and Cygwin the worker now opens
  as a Windows Terminal tab (`wt.exe`, or the launcher `KIT_WT` names), not a tmux session,
  with the brief's instruction as its first prompt. The tab runs Git Bash by its full Windows
  path, because a bare `bash` in a new tab is WSL's launcher, and every `;` handed to `wt.exe`
  is escaped as `\;`, because `wt.exe` splits its command line there even inside quotes and
  cut the instruction in two. The tab opens in the window the lead runs in (`-w 0`), its
  command ends with `exit 0` (Windows Terminal keeps a tab whose command ended nonzero open),
  and a name a running Claude Code session already has is refused. Nothing can read the tab,
  so the start-up dialog check, `--batch`, `show_workers.sh` and `watch_workers.sh` do not
  apply there: watch the tab and wait for the result file. `doctor.sh` asks for `wt.exe` (or
  `KIT_WT`) there instead of tmux.
- **`close_worker.sh` on native Windows.** It ends the Claude Code process (`claude.exe`, or
  `node.exe` running Claude Code's `cli.js`) whose arguments, split as Windows splits a
  command line, hold `-n NAME` (`taskkill /T /F`; the tab closes), waits up to 15 s for it to be gone, then
  removes the worktree through the audit, as on POSIX. A session that survives, or a process
  list it cannot read (PowerShell's `Get-CimInstance`, or the lister `KIT_PS` names), leaves
  the worktree untouched and fails the close.
- **`clean_worktrees.sh` on native Windows, and a junction is never followed.** It said
  `NOT RUN on this platform` there and kept everything. It now reads each process's working
  directory from the process itself (its PEB; MSYS shells included; a process it cannot read
  counts as unseen, as on Linux), and the gate's lock is held when its file cannot be opened
  for writing. There a tracked script's bytes are compared, and its executable bit only in the
  index: Windows keeps none on disk. On Windows a folder in the worktree that is a reparse point (a junction, a
  folder symlink) counts as a mount point, which keeps the worktree: `git worktree remove` on
  Windows went through a junction to the main checkout's virtual environment and deleted part
  of it. Workers must not link shared folders into a worktree (`docs/WORKFLOW.md`).
- **WSL: worker tabs open in the lead's window.** `show_workers.sh` passed `wt.exe -w
  kit-<project>`, which opened a second window beside the lead's; it now passes `-w 0`.
- **A review run on native Windows.** `select()` takes only sockets there, so `review.sh`
  failed at once. Each pipe of the reviewer, of the copy's preparation and of the quota
  reader is now read by a thread, and a reviewer starts suspended, joins a Job Object with
  kill-on-close, then runs: stopping it ends every process it started, also one that outlived
  it holding a pipe, and a supervisor that dies takes its reviewer with it. The review
  self-test (`review.sh --self-test`, and with it the review case of `check.sh --self-test`)
  still needs a POSIX host (item 4 below).
- **`doctor.sh` and native Windows Python.** Native Windows Python under Git for Windows' `sh`
  is no longer a MISSING line; under any other `sh` (WSL, through interop) it still is, since
  it would take the Windows lock on POSIX paths. A CRLF is a CR before a line feed, read as
  bytes; a lone CR is not one.
- **`review.sh` and Git LFS.** The v0.9 filter refusal checked every path in the checkout,
  not the paths a review changes, and `git lfs install` sets `filter.lfs.clean` globally:
  one LFS file anywhere refused every review. A filtered path the review does not change now
  passes, and only when HEAD records it as a canonical LFS pointer, its working bytes (read
  with no filter) are that pointer or the content it names by size and sha256, and Git's own
  rendered diff of the working tree and of the index does not name it, proven both before and
  after the diff and the fingerprint read the checkout, so a file replaced in between is
  refused (`which changed while the review was being prepared`). The payload diff leaves such a
  proven path out, so its filter is never asked again. A filtered path the
  review changes is refused, whichever side was filtered: candidates include names staged in
  the index, deleted and renamed-away names, and the attributes are read in the working tree,
  in the index and at each end of the reviewed range. So an index-only change to an LFS file, a commit
  that deletes one, renames it out of the filter or drops its attribute while changing it,
  a filter rule staged together with the object it filters, and any other clean filter or
  `ident` on a path are refused. A path the review excludes (its own archives) is never
  refused, and the refusal says whether the review changes the path or the path is not an
  unchanged LFS file.
- **A changed LFS path is refused with no LFS driver configured.** A fresh machine without
  `git lfs install` let a staged LFS pointer through (the named filter counted only with its
  driver); a changed path with any named filter is now refused. A snapshot reads commit
  attributes through an index in the git directory, never under `TMPDIR`.
- **The Windows lock holder and a Ctrl-C at the launch.** The gate is created suspended and the
  Ctrl-C record read after it exists: a Ctrl-C just before the launch starts no gate.
- **Bootstrap** stops when it cannot read the kit's own `.gitattributes` rules, instead of
  stamping the version without them, and when a later line of the project's own file overrides
  one of them (asked of git, not read as text).
- **A review run on native Windows, end to end.** A reviewer installed as a `.cmd` (npm's
  `codex`, `claude`) is found by its bare name, and an argument `cmd.exe` would read as shell
  is refused; the evidence writer no longer opens a folder to fsync it; a scratch folder that
  cannot be removed never loses a completed review; a Ctrl-C as the reviewer's launch returns
  is held until the reviewer is owned, then stops it.
- **The line-ending repair** (item 1, `docs/DEV_SETUP.md`) leaves alone a script below a
  symlinked or junction folder instead of writing into the link's target.

### Upgrading a project from v0.9

<!-- Each numbered item is one checklist entry. sync-kit.sh prints an item from its marker to
the end of the item, so an item holds no blank line and no line that starts a list. -->

Work from the project's root, top to bottom. `KIT` is a fresh, full clone of the kit at v0.10
or later, never a v0.9 clone pulled forward and never a shallow one: on Windows a clone made
with `core.autocrlf=true` keeps its CRLF scripts after a pull (a pull does not rewrite a file
it did not change), so its `sync-kit.sh` cannot start, and item 3 merges from `620f25e` (or `KIT_BASE`), the
kit's v0.9 base commit, which a shallow clone lacks. Start with `"$KIT/sync-kit.sh" .`: it
installs the new kit-owned files (`doctor.sh`, `spawn_worker.sh` and the rest) and prints
this list, exits 2 and records no version (item 5 does). A conflict it lists stops it before
it copies anything: resolve that and run it again until it prints this list, so that item 4
checks the new files and not v0.9's (on native Windows, v0.9's `doctor.sh` asks for tmux).

1. **ACTION:** Line endings first, before any script of the project runs: add the kit's
   rules to the project's `.gitattributes` (created if absent; a symlink or anything else that
   is not a regular file there stops the step before it writes), turn each CRLF into LF in
   the shell scripts and hooks they name (regular files only: a file that is, or lies below,
   a symlink or a junction is left alone, with a line saying so, and a
   lone CR is kept; each file is replaced whole, with its mode, so a killed run leaves it old
   or new, and a failed rewrite stops the step before anything is staged), then renormalize
   those files alone, from a committed project. The file list is read once and checked: a
   `git ls-files` that fails (a corrupt index) stops the step. A temporary copy is removed when
   the run is stopped; one a SIGKILL left behind (`.crlf-*`) stops the next run by its name:
   ```sh
   ( if [ -L .gitattributes ] || { [ -e .gitattributes ] && [ ! -f .gitattributes ]; }; then
       echo "STOP: .gitattributes is a symlink or not a regular file; make it a regular file first" >&2; exit 1
     fi
     left=$(git ls-files --others -- ':(glob)**/.crlf-*')
     [ -z "$left" ] || { echo "STOP: a killed run left $left; delete it, then run this again" >&2; exit 1; }
     list=$(mktemp) || exit 1
     trap 'rm -f "$list"' EXIT; trap 'exit 129' HUP; trap 'exit 130' INT; trap 'exit 143' TERM
     set -- '*.sh' .githooks/pre-commit .githooks/pre-merge-commit .githooks/commit-msg .githooks/post-merge
     git ls-files -z -- "$@" > "$list" ||
       { echo "STOP: git ls-files failed (above); nothing was changed" >&2; exit 1; }
     { echo; cat "$KIT/core/.gitattributes"; } >> .gitattributes || exit 1
     python3 -I -c 'if 1:
         import os, signal, stat, sys, tempfile
         signal.signal(signal.SIGTERM, lambda *a: sys.exit(143))
         def plain(name):
             # Every folder on the way and the file itself: no symlink, no junction (a reparse
             # point), or the rewrite wrote into what the link points at, outside the project.
             parts = name.split(b"/")
             for i in range(1, len(parts) + 1):
                 info = os.lstat(b"/".join(parts[:i]))
                 if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                     return False
             return stat.S_ISREG(info.st_mode)
         for name in sys.stdin.buffer.read().split(b"\0"):
             if name and not plain(name):
                 sys.stderr.write("left alone, a link or not a regular file on its way: %r\n" % name)
             elif name:
                 with open(name, "rb") as script:
                     data = script.read()
                 if b"\r\n" in data:
                     handle, new = tempfile.mkstemp(prefix=b".crlf-", dir=os.path.dirname(name) or b".")
                     try:
                         with os.fdopen(handle, "wb") as copy:
                             copy.write(data.replace(b"\r\n", b"\n"))
                         os.chmod(new, stat.S_IMODE(os.lstat(name).st_mode))
                         os.replace(new, name)
                     finally:
                         if os.path.lexists(new):
                             os.unlink(new)' < "$list" ||
       { echo "STOP: a script could not be rewritten (above); nothing was staged" >&2; exit 1; }
     if [ -s "$list" ]; then
       xargs -0 git add --renormalize -- < "$list" || { echo "STOP: renormalizing failed (above)" >&2; exit 1; }
     fi
     git add .gitattributes )
   ```
   `git status` then lists `.gitattributes`, and any script the index held with CRLF as
   modified; both go into the upgrade commit (item 5). Every other clone on Windows runs the
   lines of `docs/DEV_SETUP.md` section 1 once after it pulls that commit: a pull does not
   check out again a file it did not change, so its scripts stay CRLF until then.
2. **ACTION:** Copy `claude_bridge.py` and `test_claude_bridge.py` whole from
   `$KIT/core/scripts/` into `scripts/`, replacing yours (they hold no project content). Each
   is copied beside its destination and renamed over it, so a symlink at either name is
   replaced by the file, never written through (a plain `cp` wrote into the link's target).
   A linked parent folder (a symlink or Windows reparse point) stops the step before any copy:
   ```sh
   ( new=; trap '[ -z "$new" ] || rm -f "$new"' EXIT; trap 'exit 130' INT; trap 'exit 143' TERM
     python3 -I -c 'if 1:
         import os, stat, sys
         for name in sys.argv[1:]:
             parts = name.split("/")
             for i in range(1, len(parts)):
                 parent = "/".join(parts[:i])
                 info = os.lstat(parent)
                 if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                     sys.exit("STOP: %s is a linked folder; nothing was copied" % parent)
                 if not stat.S_ISDIR(info.st_mode):
                     sys.exit("STOP: %s is not a folder; nothing was copied" % parent)' \
       scripts/claude_bridge.py scripts/test_claude_bridge.py || exit 1
     for f in claude_bridge.py test_claude_bridge.py; do
       new=$(mktemp scripts/.kit-copy-XXXXXX) && cp -p "$KIT/core/scripts/$f" "$new" && mv -f "$new" "scripts/$f" ||
         { echo "STOP: scripts/$f could not be replaced; it and the files after it are unchanged" >&2; exit 1; }
       new=
     done )
   ```
   If
   v0.9's item 10 sent this project to the manual review template only because of Git LFS,
   use `scripts/review.sh` again for every scope that changes no LFS file.
3. **ACTION:** Merge the kit's changes since v0.9 into the three files that hold your setup
   content, one three-way merge per file, from a committed project. A file that is not a
   regular file (a symlink), or below a linked folder, stops the step before any merge.
   Windows reparse points count as links too. The v0.9 copies go to a private
   folder outside the project (a `TMPDIR` inside it stops the step), each merge result replaces
   its file whole, with its mode, and a failed read or merge stops the step there. A run that
   is stopped removes what it made; what a SIGKILL left (`.kit-merge-*`) stops the next run by
   name. The base is the kit commit your v0.9 came from: `620f25e`, the v0.9 release, unless
   the project synced an earlier v0.9 commit (project_leeway synced `00581dd`): then set
   `KIT_BASE` to that commit first, or the merge reads the kit's own later v0.9 fixes as yours:
   ```sh
   ( from=${KIT_BASE:-620f25e}
     set -- scripts/check.sh docs/DEV_SETUP.md docs/GOTCHAS.md
     python3 -I -c 'if 1:
         import os, stat, sys
         for name in sys.argv[1:]:
             parts = name.split("/")
             for i in range(1, len(parts) + 1):
                 path = "/".join(parts[:i])
                 info = os.lstat(path)
                 if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                     sys.exit("STOP: %s is a link; nothing was merged" % path)
                 if i < len(parts) and not stat.S_ISDIR(info.st_mode):
                     sys.exit("STOP: %s is not a folder; nothing was merged" % path)
             if not stat.S_ISREG(info.st_mode):
                 sys.exit("STOP: %s is not a regular file; nothing was merged" % name)' "$@" || exit 1
     for f do
       [ -f "$f" ] && [ ! -L "$f" ] ||
         { echo "STOP: $f is not a regular file (a symlink?); nothing was merged" >&2; exit 1; }
     done
     left=$(git ls-files --others -- ':(glob)**/.kit-merge-*')
     [ -z "$left" ] || { echo "STOP: a killed run left $left; delete it, then run this again" >&2; exit 1; }
     git -C "$KIT" cat-file -e "$from^{commit}" ||
       { echo "STOP: $KIT has no commit $from (a shallow clone?); clone the kit whole" >&2; exit 1; }
     base=$(mktemp -d) || exit 1
     new=; trap 'rm -rf "$base"; [ -z "$new" ] || rm -f "$new"' EXIT
     trap 'exit 129' HUP; trap 'exit 130' INT; trap 'exit 143' TERM
     case $(CDPATH= cd -- "$base" && pwd -P)/ in "$(pwd -P)"/*)
       echo "STOP: the temporary folder $base is inside the project (TMPDIR?); set TMPDIR outside it" >&2; exit 1 ;;
     esac
     for f do
       git -C "$KIT" show "$from:core/$f" > "$base/v0.9" ||
         { echo "STOP: cannot read core/$f at $from; $f and the files after it are not merged" >&2; exit 1; }
       git merge-file -p "$f" "$base/v0.9" "$KIT/core/$f" > "$base/merged"
       [ $? -lt 128 ] && new=$(mktemp "${f%/*}/.kit-merge-XXXXXX") && cp -p "$f" "$new" &&
         cat "$base/merged" > "$new" && mv -f "$new" "$f" ||
         { [ -z "${new:-}" ] || rm -f "$new"; echo "STOP: $f could not be merged; it and the files after it are unchanged" >&2; exit 1; }
       new=
     done )
   ```
   Resolve every conflict the merge left (`git diff --check` names each leftover marker) so
   that the kit's new lines and every line of yours survive, then read `git diff HEAD --
   <file>` for each file and account for every removed line.
4. **ACTION:** Prove the result: `./scripts/doctor.sh`, `./scripts/check.sh` (expect `CHECK:
   PASS`), then `./scripts/check.sh --self-test` (expect `SELF-TEST: PASS`). On native Windows
   the self-test cannot pass yet: its review case fails because `review.sh` needs POSIX
   signals (above). There, run `./scripts/check.sh` and `./scripts/check.sh --self-test` from
   Git for Windows' `sh` with the Windows `python3` and expect exactly this: `CHECK: PASS`;
   in the self-test, `ok` for every case including the thirteen Windows lock cases and the
   `sitecustomize.py` line, except
   `FAIL — review adapter negative tests failed or did not run` with the review tests' own
   output, the line `skip — a stray cygpath on a POSIX PATH` (a POSIX-only case), and a
   `skip` the project's own setup prints (the commit-msg hook when `AGENTS.md` has no
   attribution rule line); the last line is then `SELF-TEST: FAIL`. Any other `FAIL` or `skip`
   blocks the upgrade. Then run the whole `--self-test` once more from WSL or another POSIX
   shell on the same commit, where it must say `SELF-TEST: PASS` (there the Windows cases
   print one `skip` line). A project with no POSIX shell has partial acceptance only; say so
   in its state file.
5. **ACTION:** Record the version BEFORE the upgrade commit, so the commit carries it: run
   `"$KIT/sync-kit.sh" . --actions-applied`, which writes `docs/kit/.kit-version` (the first
   run already installed the kit-owned files, so it copies nothing new; if it lists a file as
   overwritten, prove item 4 again), then run `./scripts/check.sh` again and commit everything the upgrade changed together with
   `docs/kit/.kit-version` in one commit. Stamped after the commit, the version file was left
   modified and every other clone still read v0.9.

## v0.9 — 2026-10-03

Hardening from the unreported findings of two projects using the kit, then from cross-model
reviews of the result. Why each change was made, and the review history that shaped it, is
in `RESEARCH_LOG.md` (2026-10-03). Most of the files below are project-owned, so the section
"Upgrading a project from v0.8" at the end lists what to do by hand, once, in order.

- **Gate lock (issues #19, #20, #11).** `scripts/check.sh` runs one gate per checkout at a
  time. It re-executes itself, by the path it was called with, under a few lines of Python
  holding `fcntl.flock` on `<git dir>/check.lock`; the gate and everything it starts hold
  the lock until the last of them exits, and the kernel releases it. Nothing is reclaimed
  and no pid is trusted: a nested run skips the lock only by proving the descriptor it
  inherited (`GATE_LOCK_FD`) is open on this lock file and held, so variables copied from a
  gate killed with SIGKILL fail `FAIL [env]`. A second run (Stop hook, commit hook, manual)
  waits with a NOTE every 30 s that names `fuser -v` and `lsof` on the lock file instead of
  sharing the build directory and reporting a false FAIL. `GATE_LOCK_WAIT=<seconds>` bounds
  the wait: when it runs out the gate prints `NOT RUN [lock]` and exits 75 ("did not run",
  neither pass nor fail); `pre-commit` and `pre-merge-commit` report that as "did NOT RUN,
  commit blocked", and the Claude Code Stop hook waits up to 500 s and reports "gate did not
  run". INT/TERM stop the run after cleanup. The lock works on NFS; a file system without
  locks, or a Python without `fcntl` (native Windows), fails `FAIL [lock]` by name. The gate
  now needs `python3`, and applies `toolchain_path`, now at the top of the script, before it
  looks for one. It ignores `CDPATH`. A build that leaves a compiler server or build daemon
  running holds the lock until that exits (`docs/GOTCHAS.md`). A commit made during a long
  self-test waits for it.
- **Self-test seams are not a bypass (issues #25, #11).** `--self-test` writes nothing into
  the working tree: its injections come from outside it (`GATE_SELFTEST_EXTRA_FILE`), and
  "a self-test case never changes a tracked file" is a rule in `check.sh` and
  `docs/WORKFLOW.md`. The overrides are `GATE_BUILD_CMD_OVERRIDE`, `GATE_SELFTEST_STATE_FILE`,
  `GATE_SELFTEST_PROJECT_FILE`, `BOUNDARY_CHECKS_FILE`, `BOUNDARY_SELFTESTS_FILE`,
  `GATE_SELFTEST_EXTRA_FILE` and `GATE_SELFTEST_BREAK_SCANNER` (`STATE_FILE` and
  `PROJECT_FILE` were renamed). Only the self-test's own nested runs, which hold the lock,
  honour them; any other run prints `FAIL [env]: <name> is set; ...` and exits 1. The
  self-test fails when `boundary_checks.sh` has checks but the boundary self-tests printed no
  `  ok   — <label>` line, and has new cases for the hooks loop, the commit-msg hook and the
  build failure output.
- **Scan (issues #13, #14).** The gate reads text in the C locale: in a UTF-8 locale
  `grep -I` printed nothing for a line holding a non-UTF-8 byte, so a placeholder on a
  Latin-1 line passed. The build command still gets your own locale. A tracked file deleted
  without `git rm` fails `[scan]` under its own name with the command that fixes it, and
  every other scan still runs. Every tracked symlink's link text is scanned and the link is
  never followed, so an unfilled marker in a dangling link fails the setup gate (a link in
  `setup/` stays exempt); only regular files reach grep. A directory symlink (`node_modules`
  linked into a throwaway worktree), a submodule or a repository inside the tree is skipped
  with a `NOTE [scan]` line. A real grep failure keeps its old message.
- **Build output (issue #23).** The build step is quiet on a pass. On a failure it prints
  `FAIL [build]`, the last 150 lines (the whole log when `CI` is set) and the path of the
  full log, never a filtered subset. Keep deploy-shaped steps, dry runs included, out of the
  build command.
- **Commit gates (issues #16, #24).** `.githooks/pre-merge-commit` (new, kit-owned) runs the
  gate for the commit a clean `git merge` creates, where git does not run pre-commit; git
  older than 2.24 has no such hook and leaves merges ungated (`docs/DEV_SETUP.md` says so).
  `.githooks/commit-msg` (new, kit-owned) rejects an AI credit: a `Co-Authored-By`,
  `Signed-off-by` or `Assisted-by` trailer or a "Generated with" line whose whole name is a
  tool or model (quoted or not, from a list of current tool names), or whose address is a
  vendor's or a `[bot]`; a human name that contains a tool's passes. It checks the message whatever git later keeps: comment
  lines too, and nothing below a `commit -v` scissors line is cut (a credit quoted in that
  diff is rejected; commit without `-v`). It honours `Key : value` spacing, folded trailers,
  `trailer.separators`, `core.commentChar` and, on git 2.45 or later, `core.commentString`,
  and rejects the message when reading any of them fails. The line "No AI attribution in
  git" in `AGENTS.md` is the owner's switch: without it the hook passes every message; a
  missing or unreadable `AGENTS.md` keeps it on. The setup interview asks, and its opt-out
  also removes the worker definition's bullet.
- **Review tooling fails closed (issues #12, #9, #8).** A named reviewer is never silently
  replaced: `review.sh` fails when the requested reviewer cannot run, and `--fallback`
  (dispatcher `--allow-fallback`) allows one substitute whose evidence opens with
  `FALLBACK REVIEWER:`. A CLI that rejects a required flag (`cli_unsupported`) or cannot be
  launched after a cancel never fails over. A review scope with an effective git clean or
  process filter (any configured value) or `ident` is refused before launch, since the
  filtered diff can omit lines the fingerprint hashed. Ctrl-C, SIGTERM and SIGHUP kill the
  reviewer's process group and record `cancelled` wherever the cancel lands (launch, cleanup,
  the closing Codex quota read, the evidence and usage writes); a cancelled attempt never
  starts the fallback reviewer, a cancel after the reviewer finished keeps the completed
  review, and a signal the caller set to ignore (`nohup`, a background job) stays ignored.
  The Claude adapter prints a final `"correction": true` JSON line when a cancel lands while
  it prints its result; the last JSON line is authoritative. A failed quota read is
  "unavailable" and never costs a finished review its evidence. The usage record carries the
  archive's sha256 (a lost archive is `evidence_unavailable`); a malformed, unreadable or
  mismatching record, or a usage directory that cannot be listed, stops a labelled round
  (exit 2), and the refusal names the file and the command that moves it aside. An empty
  `MYAGENTKIT_TASK_ID` counts as unset. `review.sh` puts `~/.local/bin` at the end of PATH,
  not the front (an old binary there shadowed the current one), and ignores `CDPATH`. Claude's
  pin is attested only by its exact id or that id plus `-YYYYMMDD` (`claude-opus-5-5` used
  to attest the pin `claude-opus-5`; issue #36). One review resolves its base once, and the
  diff, the usage record and the carried-round check share that commit (issue #37). A Codex
  review that completed is not failed by a stream error it recovered from, such as an MCP
  reconnect (issue #34). A Claude review whose final result names an API error status is
  failed (`quota` for 429), never recorded as completed with a failure kind. The
  review self-test has a minimum test count per suite.
- **Review rounds converge (issue #18).** Both reviewers are asked for every finding, a
  severity (Critical, High, Medium, Low) on each, and a fix sketch. With the same
  `MYAGENTKIT_TASK_ID` a later round's prompt carries the earlier completed reviews from the
  reviewer's own archive, plus `REVIEW_DISPOSITIONS=<file>` for the author's answers. A
  disposition is a claim the reviewer verifies, never a settlement: a deferred finding stays
  open under Manual checks, and the closing Accept comes from one fresh review under a new
  label. Carried rounds must share scope and resolved reference with the new review, the same
  HEAD for `--commit` and `--uncommitted`, an ancestor head, and an archive whose sha256
  matches its usage record (a rebase, an amend or another head is refused and the message
  says to use a new label); they count toward the 400000-byte diff budget and show their
  verdicts as `Earlier verdict:`. A missing earlier archive exits 2 for both reviewers.
  `stale_checkout` still fails the review, and now says why and what to do.
  `docs/REVIEW_GATE.md` and `docs/USAGE.md` describe the rounds and the fallback.
- **Sync and bootstrap (issue #15).** `sync-kit.sh` records a new kit version only after its
  ACTION items are confirmed: it prints the entries, then the items again as a checklist,
  each item whole; leaves `docs/kit/.kit-version` unchanged and exits 2 until you rerun with
  `--actions-applied`. A line of the form `**ACTION** — none` is not an item, and versions
  without items are stamped as before. A kit-owned path holding a differing file without the
  KIT-OWNED header is reported as `conflict:`, and the sync copies nothing and keeps the
  stamp. A failed ACTION scan, or INT/TERM, never stamps. After a STOP, running
  `bootstrap.sh` again passes over every file identical to the kit's and lists only the
  files that differ; a differing gate file (`scripts/check.sh` or one of the three hooks)
  stops the run as `conflict: <path>`; `--force` overwrites every differing file listed.
  Both scripts judge every path they write or create one way (copied files, the version
  stamp, the note, the folders): each existing component below the target must be a real
  folder and the destination absent or a regular file; a FIFO, device, symlink, or a file
  where a folder belongs is a conflict that is not opened, `--force` included (a FIFO used
  to hang the run). Any failed write stops the run before the version is recorded or the
  hooks are wired (a regular file at `.githooks` used to end in a stamped project with no
  hooks). A retry after a failed run never records a version over a weaker state. There is no
  rollback: files a run already copied stay copied when a later step fails; each single
  file is either the old one or the new one, whole. A file is unchanged only when its
  content and its executable bit both match. Every file is written to a fresh `mktemp`
  sibling (`.kit-tmp.XXXXXX`) that takes the destination's mode first (a new file takes the
  umask's) and is then moved over it, so a full disk leaves the old stamp, note or hook
  whole and a 0600 note stays 0600; a stopped run's leftovers are named in a NOTE, not
  deleted. In bootstrap this run's own stamp move is the commit (a stamp that already held
  the version, on a re-run, is not): before it, a failure or INT, TERM or HUP puts the
  project's own `core.hooksPath` back; after it nothing is undone. Both
  scripts state their threat model in their header and `docs/UPDATING.md` repeats it: they
  protect against their own failures and interruptions and against honest mistakes in the
  tree, and by decision not against another process changing the tree during the run,
  files placed to attack them, or SIGKILL or power loss between two steps. Bootstrap's stop lists gate-file conflicts apart from
  other destinations it could not write. No script prints a supplied value through `echo`,
  so a backslash in a name or path is not turned into a terminal escape.
  `docs/UPDATING.md` and the README describe both.
- **`scripts/doctor.sh` (new, kit-owned; issue #10).** A machine check to run at session
  start, with one `MISSING: <what> — fix: <command>` line per trap and `DOCTOR: ready` or
  `DOCTOR: setup incomplete` (exit 1): mode 100755 on disk and in the index for every
  required hook and script (an untracked one is MISSING), `core.hooksPath`, the git identity,
  Python 3.10+, the six review runtime modules, `scripts/review.sh` with a readable
  `DEFAULT_REVIEWER="..."` line and the reviewer CLI it names (with `review.sh`'s
  `~/.local/bin` fallback and the `REVIEW_REVIEWER`, `REVIEW_CLI_BIN` and `CLAUDE_CLI_BIN`
  overrides; an explicitly empty one is MISSING), tmux where the worker script is installed,
  the `node` a git hook resolves with the PATH the gate really uses (`toolchain_path`) against
  `.nvmrc` (the login-less probe is a separate NOTE), the npm cache owner (three levels deep),
  `grep` shadowed by an alias or function in the interactive shell, a checkout under
  `/mnt/<drive>` on WSL, CRLF in a script, and an unignored `node_modules` symlink. It never
  evaluates `toolchain_path`: the line must read exactly `toolchain_path="..."`, only
  `$NAME` and `${NAME}` are expanded, an unset variable in it is reported, and a `check.sh`
  without the line gets a NOTE. A grep alias is accepted only when each word is a plain
  allowlisted option (`--color`, `--colour`, `--exclude-dir`). It changes nothing in the
  project; the grep probe starts the owner's interactive shell, so the shell's rc files run,
  under a 5 s bound on its whole process tree, and is skipped with a NOTE where `timeout` is
  absent.
- **Effort, STATE operation files, closing a worker (issues #17, #21, #30).** Delegated
  agents run at a stated effort: `worker.md` gets `effort: {{WORKER_EFFORT}}` (setup
  interview question 8), `diff-reviewer.md` gets `effort: high`, and WORKFLOW and HANDOFF
  say the brief names model and effort and the lead verifies both in the transcript.
  `docs/STATE.md` keeps a status line and a pointer; operation detail and worker results go
  to `docs/<OPERATION>.md`. A spawned worker session is
  closed by the lead once it has read the result file; `spawn_worker.sh` prints the command.
- **STATE.md stays clean by lifetime, not by size.** The next and parked tasks move to a
  new template, `docs/BACKLOG.md`, read when the next task is chosen, not every session;
  `docs/STATE.md` holds only what is in flight or waiting on someone, and its "Last session
  summary" heading is gone (it invited narrating finished work). A task may carry an id
  (K4, L1b: a letter first, at least one digit). The commit that finishes it carries one
  `Done: <id>` trailer per id; `commit-msg` rejects that commit while the staged STATE.md or
  BACKLOG.md still names the id, and `check.sh` fails `[state]` with file, line and closing
  commit when either file names an id any commit closed (git 2.22 or later; a shallow clone
  checks only the commits it holds and says so). A `Done:` value is exactly one id, read whole by the hook and the gate
  (folded values unfolded, the key in any case); a malformed one already in history closes
  nothing and gets a NOTE. A closed id is never reused, and the two templates name no id. Every length
  limit on STATE.md is removed: a limit saw neither a backlog that only grows nor finished
  work left in a live bullet.
- **How agents write.** `AGENTS.md` ("Language & style") states two registers and one rule
  above both. Chat and final answers: the result first, no restating, no prose between
  routine tool calls, listable facts in a list or table. Written artifacts another session
  reads cold (STATE.md, BACKLOG.md, operation files, handoff prompts, review verdicts,
  docs): full sentences, one instruction per sentence, a target of 20 words per instruction
  and 25 per description, active voice, one term per thing, numbered steps. Never shortened
  by a cap or a style: what failed, what was not run or not verified, a security warning,
  an action that cannot be undone. A worker's report defaults to 350 words with the
  sections "Not run / not verified" and "Noticed, not fixed" always present and outside the
  cap (`worker.md`, `docs/HANDOFF.md`). No standard or style product is named or required.
- **Worker routing and a documentation-only commit.** A worker runs the proof its brief
  names (`Proof:` in the brief skeleton); if it names none, it runs the gate; the expensive
  build or package step runs once, by the integrating session, after the merge. A review-fix
  round goes back to the worker that wrote the change while its context is not spent; a
  fresh worker takes it when the context is spent or the fix is a redesign; the reviewer is
  fresh in every round. A change outside the risky list does not require a review, and a
  lead that asks for one anyway says what doubt it is to settle (the blocking rule is
  unchanged). Work that ends in one exclusive resource is not run in parallel. The shape
  has a threshold: work expected to take more than about an hour, or more than one review
  round, runs in its own separate session the owner can talk to; a short read-only diagnosis
  or review runs as a sub-agent under the lead. `WORKFLOW.md` now says what the 2026-10-03
  comparison measured (cost per worker on one task) and what it did not (wall-clock,
  throughput, the lead's cost). `pre-commit` runs `check.sh --for-commit`: when every staged
  path is a regular `.md` file the build alone is skipped and the PASS line says so
  (`docs_only_skip_build=0` beside `build_test_cmd` turns it off); merges, manual runs, the
  Stop hook and the self-test always build. A staged submodule revision always builds, whatever
  `diff.ignoreSubmodules` or the submodule's `ignore` says.
- **A spawned worker is always visible, and watched.** `spawn_worker.sh` shows its session
  in a terminal tab once the worker has its brief (`--batch` defers; `scripts/show_workers.sh
  NAME...` opens a batch together in one window: Windows Terminal under WSL, iTerm2 or
  Terminal on macOS, otherwise it prints the attach line); its typed line tells the worker
  to write questions into its result file. `scripts/watch_workers.sh NAME...` returns when
  a session is gone or waits on a permission prompt, the folder-trust dialog or a question
  (`scripts/waiting_patterns.txt`, from real captures, each marked VERIFIED or UNVERIFIED).
  A spawned worker's result file starts with `Kind:` (`completed`, `blocked`, `handoff` or
  `progress`), `Task:`, `Attempt:` and `Remaining:`; only `completed` is done, an idle
  notice is a hint, and a worker that notices a compaction writes `Kind: handoff` at once.
  `watch_workers.sh --result NAME=PATH` reports DONE, BLOCKED, HANDOFF, PROGRESS or
  MALFORMED once the file is committed on a clean tree, QUESTIONS with their text when the
  file holds a "## Open questions" section (the lead asks them at once, one at a time), and
  CONTEXT once per session when the pane's status line shows more than `--context-warn`
  percent of the window used (the lead decides: finish, compact or hand off). The lead
  decides per task whether a finished session is reused or closed, from that figure, the
  idle time and the next task's length (`docs/worker-lifecycle-options.md` has the costs).
  `scripts/close_worker.sh NAME` closes a finished worker: it ends the tmux session (the
  terminal tab closes with it), waits up to 15 s for its processes to go, and removes the
  worktree through the same audit as the hook (`clean_worktrees.sh --apply --only=NAME
  --no-quiet`: the quiet period alone is lifted for that one worktree, because the lead has
  just decided the work is finished; the hook never lifts it); the branch is never deleted.
  `spawn_worker.sh`, `show_workers.sh`, `watch_workers.sh` and `waiting_patterns.txt` now
  carry the KIT-OWNED header, so a sync updates them where they exist.
- **Finished worker worktrees are removed after a merge, and only when nothing in them can
  be lost.** The new kit-owned `.githooks/post-merge` runs `scripts/clean_worktrees.sh
  --apply` (Claude Code overlay) after every merge that git completes in the main worktree.
  A worktree under `.claude/worktrees/` is removed only when every proof holds: registered,
  its own, not locked, no operation in progress, main on a branch; finished (a commit made
  in that worktree, its branch tip merged into main's branch); nothing reachable only from
  it (every object id the private git directory names is held by a ref, or is first saved
  under `refs/kit/saved/<name>-<time>/` by one atomic `update-ref`); every tracked file byte
  for byte what the index records and the index equal to HEAD; every untracked or ignored
  entry either in a disposable folder the project lists in `.claude/worktree-disposable`
  (matched exactly; never under `docs`, `.claude`, `.myagentkit`, `scripts` or `.git`,
  compared case-folded) or a regular file byte-identical to main's file outside every
  worktree and below no mount point; no mount point in the worktree or its git directory;
  quiet for 60 minutes (`quiet-minutes=` in the list); not in use (no process with its
  working directory inside, read fresh before each step through `/proc` or, elsewhere,
  `lsof`, which must show the script itself; no tmux session of its name; the gate lock not
  held); no filter or `ident` trusted: the bytes are compared. A branch is never deleted. The log
  `<git dir>/kit-worktree-removals.log` gets an `intent` line before anything is deleted and
  an `outcome` line after; the report prints the restore command. A failed `git worktree
  remove` is POSSIBLY MODIFIED and SIGINT, SIGTERM or SIGHUP during a removal is reported;
  both exit 1. Everything unproven keeps the worktree with its reason (`scripts/
  clean_worktrees.sh` is the dry run, `--all-reasons` prints every reason). Excluded by
  decision: a process changing a worktree's files, or main's copies of them, between the
  audit and the removal; files planted to attack the script; SIGKILL between two steps (a
  re-run is safe). Needs git 2.36. `KIT_NO_WORKTREE_CLEANUP=1` turns the hook off.
- **Six lessons become rules.** Before a review loop: write the threat model and agree the
  stopping rule; a stopping rule ends the hunt, not the reviewing of what is merged after
  it; a platform the kit claims is run before anything is called accepted; a review that
  ran no tests is not test evidence; a worker's "not done" line on something the brief
  asked for is a finding; under WSL a test never executes a `*.exe`.
- **Less context, same rules.** The always-loaded files lose a third (AGENTS.md, STATE.md,
  PHASES.md, ARCHITECTURE.md: duplicates and explanation moved to WORKFLOW and GOTCHAS, no
  rule lost) and the reviewer's document loses half: the caller's part of the review
  protocol moves to `docs/REVIEW_RUNNING.md`. `AGENTS.md` names sections, not whole files,
  and a test holds every named heading to its file. Passing suites print one line; a
  failing one prints its whole log. The Stop hook returns the whole failing gate output.
- **Faster review rounds, same coverage.** A worker that can start sub-agents reviews its
  own diff with fresh reviewers before it reports; reviewers are asked to run suites and
  reproductions in a throwaway copy and mark each finding REPRODUCED or REASONED; a new
  mechanism gets a one-page design review first; `REVIEW_GATE.md` gains "What a reviewer
  attacks first" and the worker a pre-report checklist pointing at it; the lead starts the
  self-test and two reviewers together under one label per feature.
- **The bridged reviewers execute, in a throwaway copy the adapter makes.** Codex runs
  `workspace-write` with the network off and Claude gets Bash, each with a copy of the
  checkout as its working directory, never the repository: the copy is built from the
  checkout's bytes (not a patch: git's stat cache and `apply.whitespace` cannot change what
  the reviewer reads), into a fresh tree that follows no symlink, under the review's one
  deadline, with its preparation processes killed as groups on a cancel; a temporary
  directory inside the repository is refused; the reviewer's environment names the
  repository through no variable and its git cannot discover a repository above the copy;
  the fingerprint covers the index as well as the working tree, so a reviewer's `git reset`
  fails the review as `stale_checkout`. Ten batched Codex rounds with the executing
  reviewer found and fixed the holes in this list (`docs/reviews/20261006T12*` to `16*`).
  A provider's content classifier stopping a run is `content_flagged`, an availability
  failure `--fallback` may route around.
- **A project that is not a plain POSIX checkout.** The kit ships a `.gitattributes` that
  keeps the hooks and scripts LF under `core.autocrlf=true` (a CRLF `#!/usr/bin/env sh`
  killed every hook); `bootstrap.sh` stops, and names it, on a `core.hooksPath` of the
  project's own (husky, lefthook) instead of replacing it in silence; the scripts find
  Python as `python` or `py` where `python3` is absent; a sparse checkout is reviewable (a
  skip-worktree entry whose file is absent hides nothing; a present one is still refused);
  a project that already runs its own hooks (husky, lefthook) keeps them beside the kit's
  as `.githooks/<name>.project`, project-owned, run first by the kit's hook with git's
  arguments (its failure is the commit's; the kit's hook runs after it); `bootstrap.sh`
  stops on any other `core.hooksPath` from any scope and verifies the wiring as git sees
  it; the review tooling and the worktree clean-up IMPORT on native Windows Python through one
  platform seam in `agent_process.py`, and no more than that: a review run (pipes are not
  selectable there), the gate lock and the clean-up need a POSIX host, and `doctor.sh` says
  so and sends the owner to WSL; the clean-up keeps every worktree there and says why. **ACTION:** `.gitattributes` is
  project-owned (a project's own merge and LFS rules must survive a sync), so the sync
  does not install it: copy `$KIT/core/.gitattributes` into the project, or append its
  three rules to the project's own file, and commit.
- **A faster kit check.** The kit's own check runs its suites and acceptance phases at
  once where the CPUs allow (sequential under four), rebuilds only the PATH directories a
  fixture must change, scales its child timeouts with the degree of parallelism, and prints
  one line per unit with its seconds (`--timing` for a table). About eight minutes down to
  under two on a twenty-CPU host. The kit check reads bytecode only from a private folder
  (a stale `.pyc` of the same size and second was read even under `-B`), the bridged review
  prompt asks the reviewer to run the suite and reproductions, a `Done:` id
  matches the state files in any case, and the kit check prints a `NOT RUN:` line for each
  test that could not run on that host.
- **The bridged reviewers execute.** Each review attempt runs in its own throwaway
  `git archive` copy of HEAD with the uncommitted diff applied, made and removed by the
  adapter, with Codex in `-s workspace-write` and Claude given Bash, and the evidence's
  sandbox field says so (`core/docs/REVIEW_RUNNING.md`).
- **Rules (issues #26, #27, #28, #31).** A web request carries no personal data
  (`docs/WORKFLOW.md` "Web requests carry no personal data", HANDOFF brief item 3,
  `docs/GOTCHAS.md`). A sub-agent returns its report as its final message; only a spawned
  session writes a result file (WORKFLOW rule 7). Worktree-isolated agents run plain
  commands, one per call, and put compound work in a script file (`worker.md`, overlay
  README). A red gate that passes on re-run is recorded, not retried away (WORKFLOW,
  GOTCHAS).
- **The boundary self-test examples.** The worked existing-file example in
  `scripts/boundary_selftests.sh` runs its probe in a disposable copy of the checkout, for a
  plain repository only: a checkout whose `.git` is not a directory (a linked worktree, a
  submodule, a separate git directory) or that holds a nested repository is refused by name
  and reported `NOT RUN`, which fails the self-test, so run `--self-test` from the main
  checkout. The copy is made with `cp -RP` outside the checkout (a `TMPDIR` inside it is
  refused); an audit of each copy before its run refuses every symlink that leads
  out of the copy and fails by name on a folder or link it cannot read; the target and the
  gate are resolved physically and a symlinked one is refused; git and the copied gate run
  under `probe_env`, which passes only the variables it names, with an empty HOME and no
  system or global git configuration; the copy's `.git/config` is replaced by an allowlist
  plus the keys named in `probe_config_keys`, and its `.git/hooks` is emptied. The baseline gate run and
  the injected run each get a fresh copy with its own empty HOME and TMPDIR, and the
  baseline's copy is deleted first, so nothing the baseline run wrote (a hook, a git
  setting, a Python start-up file in HOME, a link swapped in, a rewritten gate) can act in
  the injected run; the tree is copied twice. Each copy is hashed as taken, and a checkout
  that changed between the two is reported `NOT RUN` (run the self-test again). The example
  changes no mode and deletes a copy only through the folder `mktemp` made, entry by entry
  from that open folder: a root that is no longer that folder is refused by name with
  nothing deleted (one stated limit: an empty directory swapped into the name between that
  check and the last `rmdir` is removed), and a copy the gate left unreadable fails the case with its path. The
  carried git settings are read from the copy, never from the live checkout again, and the
  hash covers every entry's permission bits and the git index. Any `include.path` or
  `includeIf` entry in the repository's configuration is refused by name (`NOT RUN`),
  whatever its condition: an include matching only the checkout could turn the real gate
  off while the copies ran it on. For the same reason a key named in `probe_config_keys`
  that has a value from outside the repository's own config file (system, global, worktree
  or command scope) is `NOT RUN` by name, checked once in the real checkout before the first
  copy; this needs git 2.26. `TMPDIR` is resolved once, so a relative one names the same
  folder for both copies. The dot-file
  example runs in a subshell that removes its injection on INT/TERM as well as on exit.
- **Worker spawning (issues #32, #35).** `spawn_worker.sh` `cd`s into the folder before
  starting the tool (tmux hands a new session a stale `PWD`) and ignores `CDPATH`. Every
  value it puts into the session command goes through one quoting helper. The brief is not
  pasted: the script types `Read '<absolute path>' and follow it.`, and refuses a missing or
  unreadable brief, or a newline in its argument, before any session opens. `--worktree`
  runs `git worktree add .claude/worktrees/NAME -b worktree-NAME HEAD` itself instead of the
  tool's `-w` and refuses a leftover branch or path of that name; a relative `--settings`
  file is made absolute against the caller's folder, and inline JSON may start with
  whitespace. A control character in the worker name or the brief path is refused before
  anything else, and no message prints a raw control byte. `unity_gate.sh` and
  `gate_on_stop.sh` ignore `CDPATH`.
- **Tests that could not go red.** Twenty-two guards in `doctor.sh`, `commit-msg`,
  `check.sh`, `claude_bridge.py` and `sync-kit.sh` had a negative test that stayed green with
  the guard deleted; each now has one that goes red. A case that cannot run (uid 0, an old
  git) is no longer counted as a pass, the suites no longer fail when the caller ignores
  SIGINT, and `check_kit.py` holds every suite to its current test count and every unit to
  a `UNIT DONE:` line printed after its checks (an early exit 0 passed). The boundary
  suites wait 30 s per step, times `MYAGENTKIT_TEST_TIMEOUT_SCALE` on a slow host, and a
  deadline that fires ends the child's whole process group and prints its output (issue
  #29).

### Upgrading a project from v0.8

<!-- Each numbered item is one checklist entry. sync-kit.sh prints an item from its marker to
the end of the item, so an item holds no blank line and no line that starts a list. -->

Work from the project's root, top to bottom. `KIT` is the kit checkout you run `sync-kit.sh`
from, and `5c80c36` is the kit's v0.8 commit.

1. **ACTION:** If this project was stamped past a version whose ACTION items it never
   applied, set `docs/kit/.kit-version` back to the last version really applied and sync
   again, so those versions' items are listed too. A script of yours that runs
   `sync-kit.sh` must expect exit 2 while items are pending.
2. **ACTION:** With the Claude Code overlay, do this before the sync: copy
   `scripts/spawn_worker.sh` from `$KIT/overlays/claude-code/files/scripts/` over yours,
   along with any other script of that folder the project already has. The v0.8 copies
   have no KIT-OWNED header, so the sync stops on them as `conflict:`. Then let the sync
   install the kit-owned files: `.githooks/commit-msg`, `.githooks/pre-merge-commit` and
   `.githooks/post-merge` (all new), `.githooks/pre-commit`, `scripts/doctor.sh` (new) and
   `setup/INTERVIEW.md`. If it stops with `conflict:` lines on any of those, the project has
   a file of its own at that path: move yours aside, run the sync again, then carry what
   your file did into the project by hand (the kit's `docs/RETROFIT.md`). If it stops on an
   overlay file, replace it with the kit's copy the message names and sync again. A symlink
   or special file at one of those paths, or a symlinked folder on the way to it, is a
   conflict too: replace it with a real file or folder first.
3. **ACTION:** Copy these files whole from `$KIT/core/scripts/` into `scripts/`, replacing
   yours (they hold no project content): `agent_process.py`, `agent_usage.py`,
   `claude_bridge.py`, `codex_bridge.py`, `codex_quota.py`, `review_dispatch.py`,
   `test_agent_usage.py`, `test_claude_bridge.py`, `test_codex_quota.py`. With the Claude
   Code overlay also copy `scripts/show_workers.sh`,
   `scripts/watch_workers.sh`, `scripts/waiting_patterns.txt`,
   `scripts/clean_worktrees.sh`, `scripts/clean_worktrees.py` and `scripts/close_worker.sh` from
   `$KIT/overlays/claude-code/files/scripts/`, and `.claude/worktree-disposable` from
   `$KIT/overlays/claude-code/files/.claude/` (the sync never adds an overlay file that is
   missing; `chmod +x` the `.sh` files and `git add --chmod=+x` them); list your
   build-output folders in `.claude/worktree-disposable` and run `scripts/clean_worktrees.sh`
   once as a dry run; with the Unity overlay, `scripts/unity_gate.sh` from
   `$KIT/overlays/unity/files/scripts/`. Copy `$KIT/core/docs/REVIEW_RUNNING.md` to
   `docs/REVIEW_RUNNING.md` (new) and fill its `{{PROJECT_NAME}}` and `{{OWNER_NAME}}`.
4. **ACTION:** Before the merge of the next item, split `docs/STATE.md` by hand: copy
   `$KIT/core/docs/BACKLOG.md` to `docs/BACKLOG.md`, move your "Next tasks" and "Deferred /
   parked" entries into it, delete the two headings and the "Last session summary" heading
   from `docs/STATE.md`, and delete every line that narrates finished, committed work (it
   is in git). Remove any size or line limit your own `scripts/check.sh` put on STATE.md.
   From now on name tasks by id in both files and end the commit that finishes one (or the
   merge commit that integrates it) with `Done: <id>`; never reuse a closed id.
5. **ACTION:** Merge the kit's changes since v0.8 into the files that hold your setup
   content, one three-way merge per file (yours, the kit's v0.8 copy, the kit's current
   copy). Start from a committed project: the next item compares each merged file with
   `HEAD`. Conflicts are left in the file as `<<<<<<<` markers for the next item:
   ```sh
   for f in AGENTS.md docs/ARCHITECTURE.md docs/DEV_SETUP.md docs/GOTCHAS.md docs/HANDOFF.md \
       docs/PHASES.md docs/REVIEW_GATE.md docs/STATE.md docs/USAGE.md docs/WORKFLOW.md \
       scripts/check.sh scripts/review.sh scripts/boundary_selftests.sh; do
     git -C "$KIT" show "5c80c36:core/$f" > "$f.v0.8" && git merge-file "$f" "$f.v0.8" "$KIT/core/$f"
     rm -f "$f.v0.8"
   done
   ```
   With the Claude Code overlay, run the same loop over `.claude/agents/diff-reviewer.md`,
   `.claude/agents/worker.md` and `.claude/hooks/gate_on_stop.sh`, with
   `overlays/claude-code/files/$f` in place of `core/$f` in both places.
6. **ACTION:** Resolve every conflict the merge left (`git diff --check` names each
   leftover marker) so that both sides survive: the kit's new structure, and everything your
   side added, that is each value you had filled in and every check, step or rule of your
   own. Never drop a line of yours without knowing what it did: taking the kit's side whole
   deleted a project's own check from the build arm and the gate still passed. Expect
   conflicts where a filled placeholder sits next to a kit change: the
   `.githooks/pre-merge-commit` sentence in `AGENTS.md`, `build_test_cmd` in
   `scripts/check.sh`, and the `model:` line of both `.claude/agents/` files; and wherever
   you extended a block the kit rewrote, such as a check of your own in the build arm of
   `scripts/check.sh`, which goes into the kit's new arm after its `fi`, before the `;;`.
   If you replaced `scripts/boundary_selftests.sh` with your own cases at setup, the whole
   file is one conflict: keep your side there and see the boundary self-test item below.
   Then compare each merged file with your pre-merge copy (`git diff HEAD -- <file>`) and
   account for every removed line. For each file `$f` of the previous item, with `$src` its
   kit path there (`core/$f` or `overlays/claude-code/files/$f`), this prints the removed
   lines (taken from inside the hunks, so a removed `- rule` shows too) that the kit's own
   change does not also remove; each must be a line of yours whose job
   now sits in a kit line (a value you put back, a kit line you had edited), never a check,
   step or rule of yours that is gone:
   ```sh
   git -C "$KIT" diff 5c80c36 -- "$src" | sed '1,/^@@/d' | grep '^-' > "$f.kit-removed"
   git diff HEAD -- "$f" | sed '1,/^@@/d' | grep '^-' | grep -vxF -f "$f.kit-removed"; rm -f "$f.kit-removed"
   ```
   Then fill the placeholders the merge brought in, which
   `./scripts/check.sh` lists: `{{OWNER_NAME}}` in new lines of `AGENTS.md` and
   `docs/WORKFLOW.md`, and `{{WORKER_EFFORT}}` in `.claude/agents/worker.md` (`low`,
   `medium` or `high`: the effort a delegated worker runs at, setup interview question 8).
7. **ACTION:** Check the configured lines of `scripts/check.sh`: `toolchain_path` must read
   exactly `toolchain_path="<path>"` with no trailing comment, or doctor reports it. The
   build command is the proof a commit must pass; a package or pipeline step that takes
   many minutes is an integration step outside it. Set `docs_only_skip_build=0` beside it
   only if your build reads markdown. The
   build command must not filter its output (remove a `grep error` filter: the gate prints
   the tail and the log path itself), must not leave a compiler server or build daemon
   running (it would hold the gate lock; `docs/GOTCHAS.md` shows the flags) and must hold no
   deploy-shaped step, dry runs included. The gate now needs `python3` on the PATH a git
   hook sees; `toolchain_path` is applied first. Add any override variable your own boundary
   checks read to the list in the SELF-TEST SEAMS block; the kit's list now also holds
   `GATE_SELFTEST_HISTORY`.
8. **ACTION:** Bring `scripts/boundary_selftests.sh` up to the new contract: every case
   prints `  ok   — <label>` when it passes; a case that writes into the working tree moves
   outside it, or removes its file on INT/TERM as well as on exit, as the kit's dot-file
   example now does in a subshell with its own trap. If you adapted the existing-file
   example, replace your copy with the kit's current one and adapt its target and
   diagnostic again, name each repository setting your gate reads in `probe_config_keys`
   (it must be set in the repository's own config file) and add each variable your gate
   needs to `probe_env` by name (a tool that needs a cache directory gets its own); if the
   repository's configuration uses `include.path` or `includeIf`, move the settings your
   gate reads into `.git/config`, or do not use the existing-file example; the same goes
   for a key you name in `probe_config_keys` that is set in your global or system git
   configuration.
9. **ACTION:** Decide the attribution rule. The merged `AGENTS.md` now holds the bullet "No
   AI attribution in git", and the kit's `commit-msg` hook rejects AI credit while that
   line is there. To allow AI credit, delete that bullet, and with the Claude Code overlay
   the block marked "attribution rule" in `.claude/agents/worker.md`.
10. **ACTION:** Outside the files: unset the self-test seam variables named in
   `scripts/check.sh` wherever a shell profile or CI step exports them, since a normal gate
   run now fails `FAIL [env]` on them; pass `--fallback` to `scripts/review.sh` in any
   automation that relied on automatic reviewer failover; a repository with Git LFS, a
   clean filter or `ident` in the review scope cannot use `review.sh`, so use the manual
   template in `docs/REVIEW_RUNNING.md`, "Template to paste"; and where `.gitignore` says `node_modules/` and
   `node_modules` is a symlink, write `node_modules` without the slash.
11. **ACTION:** Move aside the review usage records that v0.7 and v0.8 wrote with an empty
   task id, which now stop every review: find them with
   `grep -l '"id": ""' .myagentkit/usage/*.json` and move each with
   `mkdir -p .myagentkit/usage-set-aside && mv <record> .myagentkit/usage-set-aside/`.
   Rounds recorded before v0.9 are not carried: give the next review a new
   `MYAGENTKIT_TASK_ID`.
12. **ACTION:** Prove the result, in this order: `git add -A` (doctor requires every hook
   and script in the index with mode 100755), `./scripts/doctor.sh` (fix each `MISSING:`
   line), `./scripts/check.sh` (expect `CHECK: PASS`), `./scripts/check.sh --self-test`
   from the main checkout, then commit. With the Claude Code overlay, restart Claude Code so
   the agents' `effort:` lines take effect.
13. **ACTION:** As the lead, from now on: a brief names the worker's model and effort and
   you check both in the transcript; you close a spawned worker session once you have read
   its result file (`spawn_worker.sh` prints the command); a brief file stays in place
   until the worker has read it; a brief that sends an agent to the web names a generic
   User-Agent. Then record the version with `"$KIT/sync-kit.sh" . --actions-applied`.

14. **ACTION:** A checkout holding the kit's hooks and scripts with CRLF (Windows,
    `core.autocrlf=true`) cannot even run its pre-commit (`sh\r`), so the repair comes
    before any commit. First commit or stash your edits under `.githooks/` and `scripts/`.
    Add the kit's `.gitattributes` rules (the bullet above) and stage them:
    `git add .gitattributes`. Then `git add --renormalize .githooks scripts` (LF in the
    index), then re-check out ONLY the tracked files there:
    `git ls-files -z -- .githooks scripts | xargs -0 rm -f && git checkout -- .githooks scripts`
    (untracked and ignored files under those folders stay), then
    `git commit -qm "Renormalise the kit scripts"`. A hook that still starts with `sh\r`
    is one this step missed.

## v0.8 — 2026-10-03

- **Worker cost (issue #22).** A measured rule set for routing workers lands in the
  `docs/WORKFLOW.md` template as the section "Worker cost — waits and long lives are what
  you pay for": a worker's cache must outlive its waits and it never polls, a review-fix
  round goes to a fresh worker, about 150 requests per worker, the lead does not poll,
  mechanical work to the cheaper model, short reports, cost read at the end of the day. The
  reasoning and the numbers are in `RESEARCH_LOG.md`. **ACTION:** copy the section into your
  project-owned `docs/WORKFLOW.md` (before "Token economics").
- `scripts/agent_cost.py` (kit-owned, synced): per-agent requests, cache read, cache write,
  cache write after gaps over five minutes, poll-only turns and the cache lifetime used,
  from a Claude Code session transcript and its sub-agents. `docs/HANDOFF.md` and the
  handoff command now ask for its table plus the tool's cost screen in an end-of-day
  handoff. **ACTION:** add the end-of-day paragraph to your project-owned `docs/HANDOFF.md`.
- Claude Code overlay: `.claude/agents/worker.md`, a worker definition with
  `experimental.cacheTtl: 1h`, `maxTurns: 150` and the worker rules in its body (placeholders
  `{{WORKER_MODEL}}`, `{{LONG_JOBS}}`), and `scripts/spawn_worker.sh`, which opens a separate
  worker session in tmux and pastes a brief file into it after the TUI is up. The overlay
  README documents the placeholders and the pitfalls. **ACTION:** overlays are not synced;
  copy both files from `overlays/claude-code/files/` by hand, fill the two placeholders, and
  restart any running session before spawning the worker.
  (Superseded in v0.11: overlay files already in a project are now synced; see docs/UPDATING.md.)
- `docs/worker-cost-setups.md`: the six measured setups with their figures, a "which setup,
  when" table for projects that cannot use the first choice (the one-hour cache ignored, no
  tmux, CI, a different host), and the alternatives the research pass rejected with their
  evidence. The WORKFLOW template's rule 1 points at it for the fallback.
- The first real-task measurement is in `docs/worker-cost-setups.md`; `agent_cost.py`'s poll
  detector no longer counts a Python run or a plain `tail` as waiting; `spawn_worker.sh` takes
  `--effort`; the overlay README records that the idle notice fires on every background park.
- `setup/INTERVIEW.md` asks question 8, "Will workers run jobs longer than five minutes?",
  and fills or deletes the worker files from the answer. It also asks what a worker must know
  before running those jobs, and the overlay README says to settle the permission mode of
  spawned sessions with the owner first (both were found missing when the founding project
  took this version).
- `docs/GOTCHAS.md` template: `pgrep -f` and shell wait loops match their own command line.
  **ACTION:** add the entry to your project-owned `docs/GOTCHAS.md` if your agents wait on
  processes.

## v0.7 — 2026-09-05 (unreleased)

- Downstream adoption exposed four review self-tests that assumed installed projects still
  used the template's empty model pins and Claude default. The fixture now explicitly sets
  those defaults in its temporary copy; project settings are preserved. **ACTION:** copy
  the updated `test_claude_bridge.py` with the complete companion set when upgrading.

- **Issue #7:** existing-file negative tests must restore current bytes and mode before
  deleting backups, including on EXIT/INT/TERM. A separate scaffold example isolates
  traps and terminates after signals; its regression preserves uncommitted content.
  **ACTION:** prefer disposable snapshots, or update project-owned destructive probes
  with restoration registered before mutation and interruption tests.

- The final review exposed initially hidden index changes and a verdict-only manual-check
  section. Review now rejects assume-unchanged/skip-worktree entries before model launch
  and excludes verdict declarations from manual-check validation. **ACTION:** upgrade the
  complete review runtime; clear such index flags before reviewing a complete checkout.

- The platform matrix exposed scanner exit-code differences between GNU and BSD xargs.
  The scanner now preserves each grep batch's match/no-match/error outcome explicitly.
  Real missing-file errors fail on both platforms. **ACTION:** take the updated project-owned
  `scripts/check.sh` scanner carefully, retaining your configured gates and build command.

- A follow-up review exposed four additional scope/evidence failures. Git diff drivers
  are disabled, raw checkout bytes and resolved references enter the fingerprint, merge
  commits are reviewed against their first parent, and Codex manual-check verdicts require
  actual checks. All four fixes have failing-before/passing-after regressions.
  **ACTION:** copy the complete review runtime/test companion list and repackage the plugin.

- The kit's own four legacy raw review archives are now untracked and preserved locally.
  Reference and commit reviews exclude removed legacy transcripts while keeping scrubbed
  summaries in scope. **ACTION:** use the same preserve-and-untrack migration for old
  project archives; historical Git commits are not rewritten by this change.

- The kit-source CI runs the full offline acceptance suite on Linux/macOS with Python
  3.10 and 3.14. Action revisions are pinned and jobs have read-only repository access.
  This does not run paid model calls or change installed projects' CI templates.

- **Issue #5:** an explicit transcript-Accept/no-final-response regression verifies that
  transcript text remains diagnostic only. Missing, empty, malformed and conflicting final
  responses are rejected by the wrapper. **ACTION:** take the complete review runtime/tests.

- **Issue #4:** a timeout-then-success regression proves failed evidence stays immutable,
  carries no verdict, and does not change the next review's diff or checkout fingerprint.
  **ACTION:** keep failed diagnostics locally; upgrade the adapters and ignore rules rather
  than deleting immutable reports to repair review scope.

- **Issue #3:** the interview now gives both vendor-plugin install commands explicitly
  and explains repository versus marketplace names. **ACTION:** use `codex@openai-codex`,
  matching the official marketplace manifest, rather than deriving the name from the repo.

- **Issue #2:** the boundary self-test example requires a green baseline and both a
  nonzero exit and the boundary's own diagnostic. An executable regression rejects
  unrelated failures and misleading success output. **ACTION:** adapt the example when
  maintaining project-owned boundary tests; generic exit-only gate cases remain explicit.

- **Issue #1:** setup now stages the foundation and hands it to fresh review before the
  first commit. The closing report identifies pending review explicitly. **ACTION:**
  use the updated setup interview; initial gate code has no implicit review exemption.

- **2026-09-06 review fixes:** model calls now require ignored, untracked private storage;
  malformed successful Claude envelopes stop without failover; malformed or conflicting
  Codex verdict declarations fail evidence validation. Kit acceptance requires the named
  regression suites and rejects skips. The existing-project companion list is canonical
  in `core/docs/DEV_SETUP.md` and has an upgrade regression. **ACTION:** copy that complete
  list, merge the ignore rules, and preserve/untrack any previously tracked raw diagnostics.
  The owner authorized committing and pushing these repairs with Claude review explicitly
  pending. This is not a review approval; see `docs/worktree-notes/role-neutral-review.md`.

- Review attempts now default to 30 minutes rather than 10, in both directions and in
  direct adapters. Explicit timeouts are preserved. This remains a total wall-clock limit,
  not an inactivity detector; two fallback attempts can take about an hour. Claude proposal
  defaults are unchanged. **ACTION:** upgrade the companion Python runtime files and
  repackage the Codex plugin after source review; existing explicit overrides still win.

- Owner-selected reviewer default is Claude. Reviews automatically fail over once to the
  other configured model on operational unavailability, in both directions. Each attempt
  retains its own evidence and usage, linked by immutable chain checkpoints. Completed
  Reject results, invalid evidence, stale scope, and storage failures never trigger failover.
  Author-model fallback findings remain advisory, not independent review approval.
  No default review monetary cap is added. **ACTION:** manually upgrade project-owned
  `review.sh` and its companion Python files, including `review_dispatch.py`; keep existing
  model pins. Sync does not overwrite those files. Repackage and reinstall the Codex plugin
  after source review to use the updated skill and bundled dispatcher.

**The kit no longer has an opinion about which model writes and which reviews.** The rule
was always "the author never reviews its own patch, and the reviewer is a different model".
The tooling did not say that: `review.sh` was pinned to Codex, and the documents described
Claude as the author. A real project ran out of the author's budget and swapped the roles;
the kit did not support the arrangement it had been claiming to require.

- `./scripts/review.sh [scope] --reviewer codex|claude` runs either direction. The default
  is the one configured at the top of the script, and the script accepts nothing else — the
  reviewer name is matched against a closed list and no flag is passed through to a CLI.
- **Both directions publish ONE evidence format**: the same header table, exactly one
  `VERDICT:` line (or none when the run failed), and the same
  `docs/reviews/<stamp>-<reviewer>-review.md` naming. The renderer refuses a header that has
  drifted and refuses a verdict for a run that did not complete, so this is enforced rather
  than agreed. Records made before and after a role swap can be compared.
- **Both models are pinned by name and the wrapper refuses to run unpinned.** A record that
  said "CLI default" named nothing a later review could be compared against. Claude's pin is
  additionally ATTESTED against the CLI's own `modelUsage`; Codex publishes no model identity
  in its output, so its record says the pin is requested and unattested. The evidence states
  which of the two it is.
- `AGENTS.md`, `WORKFLOW.md` and `REVIEW_GATE.md` now name AUTHOR and REVIEWER as roles and
  say the roles are expected to swap with the budget.
- The setup interview asks three separate questions — which model authors, which reviews,
  and which budget is scarce — instead of asking about budget and assuming the rest.
- New `docs/delegation-is-not-symmetric.md` records what in-session delegation actually
  exists in each direction, and why there is no `overlays/codex/`. Nothing was written from
  an inferred schema.

**ACTION — existing projects.** `scripts/review.sh` and the adapter Python files beside it
are PROJECT-OWNED: `sync-kit.sh` will not touch them, by design. To take this change:

Sync alone does not replace an existing wrapper or empty its model pins. The new pin
requirement applies to new installations and to projects that manually adopt this wrapper.

1. Copy `core/scripts/review.sh` over your own, then re-apply any local edits.
2. Copy every runtime and test companion in the canonical upgrade list in
   [core/docs/DEV_SETUP.md](core/docs/DEV_SETUP.md#3-the-second-model--only-if-you-want-cross-model-review).
3. **Fill in `DEFAULT_REVIEWER`, `CODEX_MODEL` and `CLAUDE_MODEL` at the top of
   `scripts/review.sh`.** Both model pins ship EMPTY and the wrapper stops until they are
   set. This is deliberate: an unpinned reviewer archives whatever its CLI defaulted to.
4. Run `./scripts/check.sh --self-test` and `./scripts/review.sh --self-test`.

Older reports named `<stamp>-<branch>.md` or `<stamp>-codex.md` are left alone; they stay
readable, they are simply not in the new shape.

Clarifications: both hosts can delegate reviews through the shipped command/skill entry
points; only structured implementation-proposal support is asymmetric. Synthetic live
checks are integration evidence, not independent acceptance of the implementation. For a
co-authored change, use a reviewer that did not author any part of the combined diff.

The owner selected Claude as the default reviewer for the Astra-author workflow. The
shipped wrapper now defaults to Claude; explicit `--reviewer codex` and per-project setup
remain available. Existing project-owned wrappers still require a manual settings update.

Codex can host the cross-model workflow through the MyAgentKit Codex plugin.

- Two skills request fresh Claude review-and-fix and implementation proposals. Codex remains
  the writer. Both support explicit and implicit discovery; spending still needs authorization.
- The Claude adapter restricts tools, disables customizations/MCP, pins the model, bounds
  execution, and archives structured results with source hashes. Stale or absent evidence fails.
- The wrapper gained a Claude adapter beside the Codex one; the kit-root wrapper now
  delegates to the core implementation rather than carrying a second copy. Codex collection
  rejects absent and conflicting final verdicts. (Reviewer selection and model pinning were
  reworked later in this same release — see the role-neutrality entry above for the shape
  that actually ships.)
- The new kit-source `scripts/check.sh` runs packaging drift, adapter regressions, and
  bootstrapped-project acceptance. Its self-test proves existing and new rejection paths.
- Both CLI directions now have bounded process execution and local per-invocation usage
  records, including partial/failing calls. Caller/task labels make review rounds comparable.
  Missing subscription percentages remain unknown, not inferred from tokens or API dollars.
- Quota, context exhaustion, timeout, and invalid replies stop the delegation loop while
  the host continues independent authorized work. Required review still blocks its protected
  commit/push. No automatic retry, credit purchase, or silent model fallback was added.
- Codex calls also capture bounded official account-quota observations before/after work,
  including the reported plan and window percentages. These are not per-call consumption
  claims. `MYAGENTKIT_CAPTURE_QUOTA=0` disables the optional reads.
- Both reviewers now capture and validate the same checkout snapshot, reject stale or
  mismatched reference context, and persist immutable evidence before reporting completed
  usage. Output capture uses bounded pipes rather than unbounded temporary output files.
- Bootstrapped projects ignore raw review archives; deliberately scrubbed summaries remain
  versionable. Claude's kit-layout guidance includes the architecture document.
- Bootstrap excludes locally generated Python bytecode from installed project files.
- Reviews no longer impose a default monetary cap. Claude's `--max-budget-usd` is sent
  only when explicitly supplied; timeout/turn/output protections remain unchanged.

**ACTION:** existing projects must hand-merge the project-owned review/check scripts and
review policy, and copy the Python runtime/test companions listed in
`core/docs/DEV_SETUP.md`. Merge the private usage and raw archive ignore rules from
`core/.gitignore`, and add `core/docs/USAGE.md`. Do not
overwrite customized project gates. Codex plugin installation is separate; see
`docs/CODEX.md`. Live validation and review debt are recorded in `docs/ACCEPTANCE.md`.
Python 3.10+ is now required for both live providers and their self-tests. Missing test
files and missing completion evidence fail closed. Runtime updates require rebuilding and
reinstalling the Codex plugin; Claude's cross-review command also carries recovery guidance.

## v0.6 — 2026-07-27

Renamed: **MyAgentKit → MyAgentKit_Keel**. A keel is a ship's backbone and the first part
laid down — "laying the keel" is the moment construction begins — which is what a project
foundation is for. It also carries the sense in "on an even keel": the thing that keeps a
project stable rather than the thing that moves it.

- The repository is now `KBT-0/MyAgentKit_Keel`. GitHub redirects the old path, so existing
  clones and marketplace entries keep working; the install lines in the README are updated
  to the new one.
- **The plugin is deliberately NOT renamed.** It stays `myagentkit`, so `/myagentkit:handoff`,
  `/myagentkit:cross-review` and `/myagentkit:kit-feedback` are exactly what they were. A
  command a person has learned to type is a bad thing to rename for cosmetic reasons (the
  name namespaces every command and `enabledPlugins` key: code.claude.com/docs/en/plugins-reference).
- Archived review reports under `docs/reviews/` are left untouched. They are dated evidence
  of what was said at the time, and evidence is not edited afterwards — including for a
  rename.

**ACTION** — none required. If you cloned by URL, `git remote set-url origin
git@github.com:KBT-0/MyAgentKit_Keel.git` avoids relying on the redirect.

## v0.5 — 2026-07-27

Sending findings upstream becomes opt-in, asked once, and the README stops describing an
overlay that no longer exists.

- **New placeholder `{{KIT_FEEDBACK_RULE}}` in the constitution.** Setup Phase 0.5 now asks
  whether the agent should ever offer to send kit findings upstream, and fills the
  placeholder with one of two whole bullets: the offer rule, or an instruction never to raise
  it. A no is therefore structural — the clause is simply absent from that project's
  constitution — instead of a preference every future session has to be told again.
- **The offer is separated from the learning.** Research passes, audits and trap logging run
  unchanged whatever the answer; they write to the project's own docs and always did. Only
  the outward-facing offer is gated. `setup/RESEARCH_PROTOCOL.md` checks the constitution
  before offering, and `INTERVIEW.md` Phase 5 is skipped outright on a no.
- **Tone.** The two sentences that leaned on obligation — "this is not a courtesy" and "a
  complaint that stays in a chat log improves nothing" — are gone. The mechanism is worth
  explaining; it is not worth guilting somebody into.
- **README corrections.** The overlay no longer claims to hold skills and commands (commands
  are the plugin; there are no skills), the status block tracks the real version, and the
  platform claim now says Linux native and WSL, naming macOS/BSD as the untested surface and
  the GNU `grep`/`sed` assumptions as where they would break first.

**ACTION** — existing projects: `AGENTS.md` is project-owned and is never overwritten, so
`sync-kit.sh` will not add this. Decide the question yourself and paste the matching bullet
from `setup/INTERVIEW.md` Phase 0.5 into the MENTION ONCE list, replacing the old
kit-feedback bullet if it is there. Doing nothing leaves the v0.4 behaviour, which is the
offer being made.

## v0.4 — 2026-07-27

A guard against the failure that produced it. During this kit's own development a
`git reset --hard`, run to drop a throwaway commit, destroyed uncommitted work — including a
review record the owner had written by hand, which git could not recover because the reflog
holds commits and nothing else.

- **`overlays/claude-code/files/.claude/hooks/guard_destructive_git.py`** blocks
  `reset --hard`, `checkout --`, `restore`, `clean -f`, `stash drop` and force pushes while
  the tree is dirty, printing the file list that would have been lost. `stash push`, `commit`
  and `--force-with-lease` pass through — the recoverable ways to do the same jobs.
- **The constitution** gains the rule for tools without the hook: commit or stash first,
  every time, and check `git status` rather than trusting that the tree is clean.
- **`core/docs/GOTCHAS.md`** carries the reasoning; `RESEARCH_LOG.md` finding #11 carries
  the general form, which is not about git: an agent's cleanup is the most dangerous thing it
  does, because attention has already moved to the next task.

**ACTION** — projects on v0.3 that took the claude-code overlay: copy the new hook in and add
the `PreToolUse` block to `.claude/settings.json` (see `overlays/claude-code/files/`).
Projects using another tool get the constitution rule and nothing enforcing it, which is
worth knowing rather than assuming.

## v0.3 — 2026-07-27

Project knowledge gets its own layer. Until now the kit had a slot for a design document
(`{{DESIGN_DOC}}`, a path the project supplied) and nothing at all for "what are we building
right now, and what are we deliberately not building yet". Both are shipped files now.

- **`docs/PROJECT.md`** replaces the `{{DESIGN_DOC}}` placeholder. Same role — permanent
  decisions, DECIDED/OPEN tagging, design authority — but a real file at a fixed path, so
  two placeholders disappear and the constitution stops pointing at something that might not
  exist. It is NOT in the reading order: sections are numbered, listed in a Contents, and
  cited by number rather than quoted.
- **`docs/PHASES.md`** is new and read every session. Current phase in full, later phases
  one line each, and — the half that earns its place — what is explicitly OUT of scope until
  later. Promoted from `patterns/staged-prototype.md`, which stays as the long-form
  reasoning.
- **An agent may add OPEN items to PROJECT.md freely and may NEVER mark anything DECIDED.**
  When the owner appears to settle something in conversation, it is recorded as OPEN with a
  note and a question. A wrongly captured question costs a minute; a wrongly promoted
  decision is invisible, binding, and compounds.
- **`scripts/check.sh` fails when a numbered PROJECT.md section is missing from its
  Contents.** Selective reading is what keeps that file affordable as it grows, and it only
  works while the Contents is complete. Four self-test cases, sixteen in total now.
- **No ROADMAP.md**, considered and rejected — the reasoning is in
  `docs/knowledge-has-three-horizons.md` along with the permanent / episodic / momentary
  split the three files implement.

**ACTION** — projects on v0.2 must add both files: copy `core/docs/PROJECT.md` and
`core/docs/PHASES.md` in and fill them. Add **`docs/PHASES.md` to the reading order** in
`AGENTS.md`, as the step after the constitution. Do NOT put `docs/PROJECT.md` in the reading
order — it is read by section, on demand; putting it there is the cost this release exists
to avoid. A project with an existing design document under another name (`GDD.md`,
`SPEC.md`) either renames it or makes `docs/PROJECT.md` the file that owns the Contents;
two canonical design documents is the duplicate-authority problem this release exists to
avoid. The gate FAILS until `docs/PROJECT.md` exists, which is deliberate.

## v0.2 — 2026-07-26

The three commands moved out of the Claude Code overlay into a proper plugin, and the kit
gained a way to be maintained by the projects using it rather than only by its author.

- **Commands are now a Claude Code plugin**, installed once per machine instead of copied
  into every project: `/myagentkit:cross-review`, `/myagentkit:handoff` and the new
  `/myagentkit:kit-feedback`. Namespacing comes from the plugin, which also ends the risk of
  a bare `handoff` or `cross-review` colliding silently with something else
  (code.claude.com/docs/en/skills, 'Resolve skills that share a name';
  anthropics/claude-code issues 12606, 62409, 62500).
- **`/myagentkit:kit-feedback`** sends a finding upstream as a GitHub issue or pull request.
  It scrubs the project out of the text, shows the exact body, and sends nothing without an
  explicit yes.
- **Two places now offer it unprompted:** the end of an ecosystem research pass
  (`setup/RESEARCH_PROTOCOL.md`) and the audit's backflow question
  (`core/docs/WORKFLOW.md`). A third lives in the constitution's MENTION ONCE list, for when
  the foundation itself misbehaves during ordinary work.
- **`CONTRIBUTING.md`** is the same process by hand, with what belongs upstream and what
  does not, the privacy rules, and the requirement that a gate change carries its negative
  test.

**ACTION** — install the plugin (`/plugin marketplace add KBT-0/MyAgentKit_Keel`, then
`/plugin install myagentkit@myagentkit`), then delete `.claude/skills/handoff` and
`.claude/skills/cross-review` from projects installed with v0.1. They are superseded;
leaving them means two copies of the same command, one of which no longer receives fixes.

## v0.1 — 2026-07-26

First extraction. The kit's Layer 1 (universal core), the Unity overlay and the optional
patterns were taken from a Unity + .NET multiplayer codebase written almost entirely by CLI
agents. Nothing here was designed in the abstract; every rule was paid for by real work.

Founding content, with the failure each rule prevents recorded in `RESEARCH_LOG.md`
(Backflow findings, 2026-07-26):

- Gates must be proven RED before they count, and each ships with an automated negative
  test — `core/scripts/check.sh --self-test`.
- Gates, CI and review tooling are a permanent risky area in every project's review gate.
- The cross-session state file is transient: completed work is deleted, permanent findings
  are tagged `[LESSON]` / `[GOTCHA]` and routed to a permanent home before deletion, and
  the rot gate keys on an empty "Active work" section rather than a line count.
- CLI output parsing strips ANSI escapes and never writes an extracted field as silently
  blank.
- Always-loaded documents are a recurring token bill and are kept small and stable.

Reviewed before release by TWO other models, read-only, both returning **Reject** — the
second one reviewing the first one's fixes:

- Codex CLI (gpt-5.6-sol): **seventeen findings**, five of them fail-open paths in the gates.
  Consequences worth naming: `.claude/` moved out of `core/` into `overlays/claude-code/`,
  and `scripts/review.sh` now states that it targets the Codex CLI's interface rather than
  implying vendor neutrality. Reasoning in `RESEARCH_LOG.md` backflow finding #6.
- Claude Fable 5, on the fixed tree: **eleven findings, two critical.** The remediation for
  the scanner had reintroduced the fail-open shape it fixed (`exit` inside a command
  substitution kills only the subshell), and the editor-side boundary hook read a payload
  field no tool sends, so everything written through Edit passed uninspected. Reasoning in
  backflow finding #7 — which is why `docs/REVIEW_GATE.md` now says a Reject is not closed
  by its own fixes.

Both reports are archived under `docs/reviews/` as evidence. `docs/ACCEPTANCE.md` lists what
was executed and what was not.

The first backflow from a project arrived the same day: applying these findings back to the
founding project uncovered a gate aimed at two directories that did not exist yet, which had
therefore reported PASS without reading a line since it was written. `boundary_checks.sh` and
the audit checklist now cover it (`RESEARCH_LOG.md` backflow finding #8).

**ACTION** — none. There is no earlier version to upgrade from.
