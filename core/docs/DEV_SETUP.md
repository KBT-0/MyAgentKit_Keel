# Dev setup — per clone

Things git cannot carry inside a commit. Run them once in every fresh clone, on every
machine — and note that a Windows shell and a WSL shell on the same box count as two
separate setups.

## 1. Wire the commit gate

```sh
git config core.hooksPath .githooks
```

`.githooks/pre-commit` runs `./scripts/check.sh` and aborts the commit when it fails.
`.githooks/pre-merge-commit` runs it for the merge commit a clean `git merge` creates, where
git does not run pre-commit. `.githooks/commit-msg` rejects an AI co-author trailer.
`core.hooksPath` is local configuration, not repository content, so **a clone without this
line has NO gate** — the commit succeeds and CI catches the problem later, if at all
(hooks do not travel with a clone; agents have been seen pointing `core.hooksPath` at
/dev/null: coder commit dd34e3d, Cursor forum).
Git older than 2.24 has no `pre-merge-commit` hook, so a clean merge there is ungated
(Git 2.24 release notes; git-scm.com/docs/githooks).
A sparse checkout needs Git 2.42 or later for the kit's refusal of a deleted skip-worktree file
(#53; the 2.42 floor is the kit's own record). Git added `sparse-checkout check-rules` in
2.41, as its [release notes](https://raw.githubusercontent.com/git/git/v2.41.0/Documentation/RelNotes/2.41.0.txt)
and [command documentation](https://raw.githubusercontent.com/git/git/v2.41.0/Documentation/git-sparse-checkout.txt)
show (checked 2026-10-16). If that command is unavailable, the review is refused.
A hook of the project's own (husky, lefthook, a script of yours) lives in `.githooks` too,
project-owned and executable: for a name the kit ships (`pre-commit`, `commit-msg`,
`pre-merge-commit`, `post-merge`) as `.githooks/<name>.project`, which the kit's hook runs
first with git's arguments (its failure fails the commit; `post-merge` runs after the merge
and cannot veto it); for any other name (`pre-push`, `prepare-commit-msg`, ...) as
`.githooks/<name>` itself, which git runs directly. A hook that finds its checks by its
own path (`$0`, its folder) stays where it is, and the `.project` file is two lines,
`#!/bin/sh` and `exec /its/old/path "$@"`: Git for Windows never runs a file without a `#!`
line, `chmod +x` or not, and the kit's hook then refuses the commit. No other
`core.hooksPath` is accepted: `bootstrap.sh` stops on one and names this migration. Others
refuse too: lefthook will not overwrite a hooks path that points elsewhere without `-f`.
The project's own machine checks (its dependencies installed, a browser its tests need) go
in `scripts/doctor.project.sh`, project-owned, executable and starting with a `#!` line
(without one, Git for Windows never runs it): `scripts/doctor.sh` is kit-owned and runs it
last, and its non-zero exit is one `MISSING` line.

**Git LFS.** With the hooks path at `.githooks`, git never runs the hooks `git lfs install`
wrote into `.git/hooks`: a push uploads no LFS object, and a fresh clone fails with "smudge
filter lfs failed" (#164). In a repository whose `.gitattributes` uses `filter=lfs`, commit
Git LFS's hooks in `.githooks`: `pre-push`, `post-checkout` and `post-commit` under their own
names, and its `post-merge` as `.githooks/post-merge.project`, which the kit's `post-merge`
runs first. Each is Git LFS's own body, with the hook's name in the last line:

```sh
#!/bin/sh
command -v git-lfs >/dev/null 2>&1 || { echo >&2 "This repository uses Git LFS, but git-lfs is not on PATH."; exit 2; }
git lfs pre-push "$@"
```

Add them with `git add --chmod=+x`. Never run `git lfs update --force` (or `install --force`)
here: it overwrites the kit's `post-merge`. `./scripts/doctor.sh` reports a `pre-push` that
does not run Git LFS.

Verify it is live:

```sh
git config core.hooksPath        # -> .githooks
```

`git commit --no-verify` skips the gate. That hatch exists for {{OWNER_NAME}}'s WIP commits.
Agents must not use it (`AGENTS.md`). The hook also skips the gate when nothing staged
differs from HEAD, as the commit then records HEAD's tree (#232), so a message-only
`git commit --amend` of a `--no-verify` commit stays as ungated as that commit already was.

**Recommended: the same gate in CI, as a required check.** A git hook is local and can be
skipped ([githooks](https://git-scm.com/docs/githooks)); the hook is the local backstop, and
the check that holds is the same `./scripts/check.sh` run by CI and set as a required status
check on the protected branch. Run it on every pull request with no `paths` or `paths-ignore`
filter, and let the script decide what to run: a workflow a path filter skips leaves its
required check Pending, and the pull request cannot merge
([troubleshooting required status checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks)).

**Line endings.** `sh` cannot run a script with CRLF line endings, and Git for Windows'
default `core.autocrlf=true` checks text files out with CRLF: on such a clone the gate, the
hooks and `doctor.sh` could not start. `.gitattributes` holds `*.sh text eol=lf` and one
`text eol=lf` line for each of the gate's hooks, so they check out with LF whatever a
clone's autocrlf says. Keep those lines. Recommended: `* text=auto` as the first line, so
every other text file is stored with LF too and `git diff` never churns on line endings alone
(a review refuses a line-ending-only diff unless `REVIEW_ALLOW_EOL_ONLY=1`). The working copy
still takes the clone's own line endings, CRLF in a default Windows clone: compare two
working trees with `diff --strip-trailing-cr` or `git diff --no-index --ignore-cr-at-eol`.
In a repository that already has CRLF files, run `git add --renormalize .` once after adding it and commit that alone
([gitattributes](https://git-scm.com/docs/gitattributes)). A clone made before they were
committed keeps its CRLF copies, because a pull does not check out again a file it did not
change. Repair it once, with no uncommitted change to the scripts or hooks (it stops and
names a file it would rewrite that has one):
`sh scripts/fix_crlf.sh` (kit-owned; its header says what it rewrites and what it leaves
alone). It turns each CRLF script and hook into LF and runs `git add --renormalize` on
them; a file added after the attributes, the script itself included, already checks out
with LF.

`./scripts/doctor.sh` names any script still checked out with CRLF. The kit's own clone is no
exception: upgrade from a fresh, full clone of the kit, never an older clone pulled forward,
whose scripts stay CRLF and cannot start (the kit's upgrade checklist runs them), and never a
shallow one, which lacks the older commit the checklist merges from.

## 2. Toolchain on PATH

`check.sh` needs {{TOOLCHAIN}}. Per-user installs are the usual trap here: they work in your
interactive shell and are missing from the non-login shell a git hook runs in, so the gate
fails for a reason that has nothing to do with the code.

{{TOOLCHAIN_SETUP_NOTES}}

If the gate fails with "command not found", that is this — not a broken build.

The gate runs one at a time per checkout and needs `python3` for its lock: `fcntl.flock` on
Linux, macOS, WSL and a POSIX Python under MSYS2 or Cygwin; on native Windows (Git for
Windows' `sh` with a Windows Python) a lock file held open without write sharing, which a
nested run proves it holds by the file's `FILE_ID_INFO` (NTFS and ReFS give one; on a volume
that gives none, nested runs fail `FAIL [lock]`). Every
process the build command starts holds the lock, so a build server it leaves running (a
compiler server, a build daemon) makes the next gate, and the commit hook, wait until that
server exits. Turn such servers off in the build command (`docs/GOTCHAS.md`); the waiting
`NOTE [lock]` line says how to find the holder.

## 3. The reviewing model — the Claude CLI alone is enough

`docs/REVIEW_GATE.md` asks for risky diffs to be reviewed in a fresh session by a tier at
least the author's. `scripts/review.sh` automates that. In solo mode, the default, it needs
only the Claude CLI you already use: the reviewer is a Claude tier, pinned in
`REVIEW_CLAUDE_MODEL` (`docs/REVIEW_GATE.md`, "Invariant"; `docs/WORKFLOW.md`, "Working
modes, by name"). A second CLI, such as Codex, is optional and serves cross mode only.
It runs from any shell the gate runs from, native Windows included (Git for Windows' `sh`
with a Windows Python: the reviewer runs in a Job Object of its own there). A CLI installed as
a `.cmd` (npm's) is found by its bare name; an argument `cmd.exe` would read as shell is
refused, so name the CLI's executable in `REVIEW_CLI_BIN` or `CLAUDE_CLI_BIN` if a review says
so.

**Ask your agent to set this up for you.** It can install the CLI and check the wiring; the
parts it cannot do are called out below. Nothing here is required to write code — the gate,
the hooks and CI all work without it. Skip the wrapper and the review protocol becomes the
paste-the-template-by-hand version in `docs/REVIEW_RUNNING.md`, which is a real fallback, not a
consolation prize.

**Required: the reviewing CLI itself.**

`scripts/review.sh` uses the project's configured default reviewer and pinned models. The
solo default is `./scripts/review.sh --uncommitted --reviewer claude` with
`REVIEW_CLAUDE_MODEL` set to a tier at least the author's (`docs/REVIEW_GATE.md`,
"Invariant"). Only for the
optional Codex direction (`codex exec -s workspace-write …`), check:

```sh
command -v codex          # already there?
```

If not, install it and log in. Point the script
somewhere else with `REVIEW_CLI_BIN`, but note that only swaps the BINARY — a CLI with a
different flag interface needs a matching adapter. For Claude Code, the kit ships one:
use `./scripts/review.sh --uncommitted --reviewer claude`. This requires Python 3.11+
and an installed, authenticated Claude CLI. `CLAUDE_CLI_BIN` selects that binary; the
adapter pins read tools and structured output. The Codex-host plugin also supports
`$myagentkit-review` and `$myagentkit-delegate` after installation from the kit marketplace.
Python 3.11+ is also required by `scripts/review.sh --self-test` (the review suite), even when
Codex is the only reviewing CLI.
Both live adapters now require Python as well, to bound the child process and preserve usage
on failure. The following is the canonical companion list for an existing-project upgrade.
Copy every listed file from the kit's `core/scripts/` into your project's `scripts/`
alongside the updated `review.sh`; reapply the project's default reviewer and model pins.

<!-- REVIEW_COMPANIONS_START -->

`review_dispatch.py`, `claude_bridge.py`,
`codex_bridge.py`, `agent_process.py`, `agent_usage.py`, `test_claude_bridge.py`, and
`test_agent_usage.py`, plus `codex_quota.py`, `test_codex_quota.py`, `review_test_support.py`
and `owns_check.py` (`review.sh` runs it on a `REVIEW_TASK_FILE` brief's `Owns:` line).

<!-- REVIEW_COMPANIONS_END -->

The offline review self-test runs on native Windows as well as Linux and macOS. Windows
fixtures use the current Python interpreter through pip's bundled console launcher, so pip
must be installed for the self-test (`python -m ensurepip` repairs a Python without it).
POSIX signal-mask, process-group, FIFO and resource-limit cases report NOT RUN on Windows;
Linux and macOS CI run them. Each platform enforces a minimum of executed tests per suite;
declared platform skips do not count, and unexpected skips fail the self-test.

Merge `.myagentkit/` (including the old backend place, `.myagentkit/backends/`)
into the root ignore rules. Also merge the raw review/handoff archive exclusions and final
summary re-include from the kit's `core/.gitignore`. The adapters refuse to launch if
private storage is not ignored or raw records are already tracked. Preserve any existing
records locally before removing them from Git's index; never delete them as part of an
upgrade. A project that committed its review reports under `docs/reviews/` (the pre-v0.11
convention) decides before its first review: untrack them with `git rm --cached`, or keep a
final one as `docs/reviews/*-summary.md`; until then every review refuses and names the
tracked paths. Private storage cannot use symlinked directories. See `docs/USAGE.md`.

Verify it end to end before trusting it — one real invocation, on a small diff:

```sh
./scripts/review.sh --uncommitted
```

A stub or a dry run does not count. A wrapper validated only against a fake CLI is a wrapper
that has never met the real contract (`docs/GOTCHAS.md`).

**Optional: a second Claude-compatible backend.**

The Claude CLI can talk to another provider's Anthropic-compatible endpoint, such as GLM's.
A backend is one regular UTF-8 file, `NAME.env`, at most 64 KiB, with one `KEY=VALUE` per
line. It lives outside the repository, so no checkout can provide or change it: in
`MYAGENTKIT_BACKENDS_DIR`, else `%APPDATA%\myagentkit\backends` (Windows) or
`$XDG_CONFIG_HOME/myagentkit/backends`, else `~/.config/myagentkit/backends`; a folder inside
the repository is refused (KARARLAR D09 inv2#80). The old place, `.myagentkit/backends/NAME.env`,
is read only while projects move, with a note naming the new folder; there it must be
Git-ignored and untracked, and both review and worker launch refuse a file that fails
either check. Leading and trailing whitespace is stripped;
blank lines (including whitespace-only lines) and lines starting with `#` are skipped.
Only these keys are accepted:

```sh
# <backend folder>/glm.env (the provider's documentation names the URL and the models)
ANTHROPIC_BASE_URL=<the provider's Anthropic-compatible URL>
ANTHROPIC_AUTH_TOKEN=<your API key for that provider>
ANTHROPIC_DEFAULT_OPUS_MODEL=<the provider's model id>
ANTHROPIC_DEFAULT_SONNET_MODEL=<the provider's model id>
ANTHROPIC_DEFAULT_HAIKU_MODEL=<the provider's model id>
# Optional: the model the review is pinned to; without it the OPUS model is the pin.
ANTHROPIC_MODEL=<the provider's model id>
```

The token stays in this file outside the repository. A project that still has backend files
in `.myagentkit/backends/` moves them to the backend folder; until then bootstrap's rules from
`core/.gitignore` keep them ignored (merge those rules into the project's own `.gitignore`,
and preserve the files locally before removing any from Git's index).
Never export the token in your shell profile. Then run
`./scripts/review.sh --uncommitted --reviewer claude --backend glm`, or set
`MYAGENTKIT_BACKEND=glm` for the run. A file without a nonempty `ANTHROPIC_AUTH_TOKEN`,
`ANTHROPIC_BASE_URL`, or a model fails the review before launch.
An existing project gets `--backend` only from the updated `review.sh` (the upgrade above); an older `review.sh` keeps working without it.
`scripts/spawn_worker.sh --backend glm` starts a Claude worker session on the same backend.
The worker reads the file at start, replacing every inherited `ANTHROPIC_*` variable;
the terminal script and tmux launch command carry the file path, never its token.
Both paths clear the Claude credential and provider controls listed in `BACKEND_CLEAR_KEYS`
in `review_dispatch.py`. Codex reviews ignore `--backend` and `MYAGENTKIT_BACKEND` with a notice.
With `--backend`, worker `--model` must name the provider's model id or a mapped alias,
such as `opus` with `ANTHROPIC_DEFAULT_OPUS_MODEL` set. A `claude-` model id is refused.
The CLI's `--model` flag overrides `ANTHROPIC_MODEL`.
The stored claude.ai login and `apiKeyHelper` cannot be removed from the environment.
With a backend, the CLI still prefers `ANTHROPIC_AUTH_TOKEN` for authentication.
User or managed settings can reintroduce environment values; verify settings before live backend use.
Claude reviews deny reads of `.myagentkit/backends` through tool permissions and the Bash sandbox.
Both layers are needed: Read and Edit deny rules do not apply to arbitrary subprocesses
([permissions](https://code.claude.com/docs/en/permissions)), and a sandbox `denyRead` entry
does not stop the Read tool ([sandboxing](https://code.claude.com/docs/en/sandboxing)).
The Codex review adapter uses legacy `workspace-write`, which has no per-path read-deny knob.
On Codex installations supporting managed read denies, administrators should add this to `requirements.toml`:

```toml
[permissions.filesystem]
deny_read = ["**/.myagentkit/backends", "**/.myagentkit/backends/**"]
```

The kit cannot install administrator policy. Without it, Codex can read a backend file by absolute path.
Do not claim that the throwaway copy alone prevents those reads.
See the [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
See [Claude environment precedence](https://code.claude.com/docs/en/env-vars)
and [sandbox filesystem rules](https://code.claude.com/docs/en/sandboxing).

Kit rules: docs/DEV_SETUP_KIT.md, "3. The reviewing model — the Claude CLI alone is enough".
A project that needs a different rule writes it here, and this file wins over `docs/DEV_SETUP_KIT.md`.

## 4. Check the machine — every session start, every machine

Kit rules: docs/DEV_SETUP_KIT.md, "4. Check the machine — every session start, every machine".

## 5. Prove the gate actually works

Once, on a fresh clone:

```sh
./scripts/check.sh
```

Each check the project adds has a fixture test in the suite the build command runs
(`docs/WORKFLOW.md`, "Writing a gate"): an input that breaks the rule turns the check red
with its own `FAIL` line, a clean one leaves it green. The gate does not check that those
tests exist or that the build command runs them: a green `CHECK: PASS` says the checks found
nothing, and only the fixture tests show that each check can fail.

{{PROJECT_SETUP_STEPS}}
