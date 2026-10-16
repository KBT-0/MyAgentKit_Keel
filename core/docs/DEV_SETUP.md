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
line has NO gate** — the commit succeeds and CI catches the problem later, if at all.
Git older than 2.24 has no `pre-merge-commit` hook, so a clean merge there is ungated.
A sparse checkout needs Git 2.42 or later for the kit's refusal of a deleted skip-worktree file
(#53): `git sparse-checkout check-rules` is missing before it, and the review is refused.
A hook of the project's own (husky, lefthook, a script of yours) lives in `.githooks` too,
project-owned and executable: for a name the kit ships (`pre-commit`, `commit-msg`,
`pre-merge-commit`, `post-merge`) as `.githooks/<name>.project`, which the kit's hook runs
first with git's arguments (its failure fails the commit; `post-merge` runs after the merge
and cannot veto it); for any other name (`pre-push`, `prepare-commit-msg`, ...) as
`.githooks/<name>` itself, which git runs directly. A hook that finds its checks by its
own path (`$0`, its folder) stays where it is, and the `.project` file is one line:
`exec /its/old/path "$@"`. No other `core.hooksPath` is accepted: `bootstrap.sh` stops on
one and names this migration.

Verify it is live:

```sh
git config core.hooksPath        # -> .githooks
```

`git commit --no-verify` skips the gate. That hatch exists for {{OWNER_NAME}}'s WIP commits.
Agents must not use it (`AGENTS.md`).

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
every other text file is stored with LF too and a diff never churns on line endings alone (a
review refuses a line-ending-only diff unless `REVIEW_ALLOW_EOL_ONLY=1`); in a repository that
already has CRLF files, run `git add --renormalize .` once after adding it and commit that alone
([gitattributes](https://git-scm.com/docs/gitattributes)). A clone made before they were committed keeps its
CRLF copies, because a pull does not check out again a file it did not change, until they
are rewritten once, with no uncommitted change to them: each CRLF becomes LF in a regular
file (a file that is, or lies below, a symlink or a junction is left alone, with a line
saying so; a lone CR is kept; each file is replaced whole, with its mode),
and each file is staged again so that `git status` does not list it as modified for its new
size. A rewrite that fails stops it before anything is staged, and so does a `git ls-files`
that fails (a corrupt index); a temporary copy a SIGKILL left (`.crlf-*`) stops the next run.

```sh
( left=$(git ls-files --others -- ':(glob)**/.crlf-*')
  [ -z "$left" ] || { echo "STOP: a killed run left $left; delete it, then run this again" >&2; exit 1; }
  list=$(mktemp) || exit 1
  trap 'rm -f "$list"' EXIT; trap 'exit 129' HUP; trap 'exit 130' INT; trap 'exit 143' TERM
  set -- '*.sh' .githooks/pre-commit .githooks/pre-merge-commit .githooks/commit-msg .githooks/post-merge
  git ls-files -z -- "$@" > "$list" || { echo "STOP: git ls-files failed (above); nothing was changed" >&2; exit 1; }
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
  if [ -s "$list" ]; then xargs -0 git add --renormalize -- < "$list"; fi )
```

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

## 3. The second model — only if you want cross-model review

`docs/REVIEW_GATE.md` asks for risky diffs to be reviewed by a DIFFERENT model in a fresh
session. `scripts/review.sh` automates that, and it needs a second CLI on this machine.
It runs from any shell the gate runs from, native Windows included (Git for Windows' `sh`
with a Windows Python: the reviewer runs in a Job Object of its own there). A CLI installed as
a `.cmd` (npm's) is found by its bare name; an argument `cmd.exe` would read as shell is
refused, so name the CLI's executable in `REVIEW_CLI_BIN` or `CLAUDE_CLI_BIN` if a review says
so.

**Ask your agent to set this up for you.** It can install the CLI and check the wiring; the
parts it cannot do are called out below. Nothing here is required to write code — the gate,
the hooks and CI all work without it. Skip it and the review protocol becomes the
paste-the-template-by-hand version in `docs/REVIEW_RUNNING.md`, which is a real fallback, not a
consolation prize.

**Required: the reviewing CLI itself.**

`scripts/review.sh` uses the project's configured default reviewer and pinned models.
For the Codex direction (`codex exec -s workspace-write …`), check:

```sh
command -v codex          # already there?
```

If not, install it and log in. Point the script
somewhere else with `REVIEW_CLI_BIN`, but note that only swaps the BINARY — a CLI with a
different flag interface needs a matching adapter. For Claude Code, the kit ships one:
use `./scripts/review.sh --uncommitted --reviewer claude`. This requires Python 3.10+
and an installed, authenticated Claude CLI. `CLAUDE_CLI_BIN` selects that binary; the
adapter pins read tools and structured output. The Codex-host plugin also supports
`$myagentkit-review` and `$myagentkit-delegate` after installation from the kit marketplace.
Python 3.10+ is also required by `scripts/review.sh --self-test` and the review tests included
in `scripts/check.sh --self-test`, even when Codex is the only reviewing CLI.
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

Merge `.myagentkit/` (including `.myagentkit/backends/`)
into the root ignore rules. Also merge the raw review/handoff archive exclusions and final
summary re-include from the kit's `core/.gitignore`. The adapters refuse to launch if
private storage is not ignored or raw records are already tracked. Preserve any existing
records locally before removing them from Git's index; never delete them as part of an
upgrade. Private storage cannot use symlinked directories. See `docs/USAGE.md`.

Verify it end to end before trusting it — one real invocation, on a small diff:

```sh
./scripts/review.sh --uncommitted
```

A stub or a dry run does not count. A wrapper validated only against a fake CLI is a wrapper
that has never met the real contract (`docs/GOTCHAS.md`).

**Optional: a second Claude-compatible backend.**

The Claude CLI can talk to another provider's Anthropic-compatible endpoint, such as GLM's.
A backend is one regular UTF-8 file, `.myagentkit/backends/NAME.env`, at most 64 KiB,
with one `KEY=VALUE` per line. It must be Git-ignored and untracked; both review and worker
launch refuse a file that fails either check. Leading and trailing whitespace is stripped;
blank lines (including whitespace-only lines) and lines starting with `#` are skipped.
Only these keys are accepted:

```sh
# .myagentkit/backends/glm.env (the provider's documentation names the URL and the models)
ANTHROPIC_BASE_URL=<the provider's Anthropic-compatible URL>
ANTHROPIC_AUTH_TOKEN=<your API key for that provider>
ANTHROPIC_DEFAULT_OPUS_MODEL=<the provider's model id>
ANTHROPIC_DEFAULT_SONNET_MODEL=<the provider's model id>
ANTHROPIC_DEFAULT_HAIKU_MODEL=<the provider's model id>
# Optional: the model the review is pinned to; without it the OPUS model is the pin.
ANTHROPIC_MODEL=<the provider's model id>
```

The token stays in this ignored, untracked file. Bootstrap installs the rules from
`core/.gitignore`; after sync, merge those rules into the project's own `.gitignore` and
preserve any existing backend files locally before removing them from Git's index.
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
See the [Codex configuration reference](https://developers.openai.com/codex/config-reference).
See [Claude environment precedence](https://code.claude.com/docs/en/env-vars)
and [sandbox filesystem rules](https://code.claude.com/docs/en/sandboxing).

**Optional: the vendor plugin for your host agent.**

Separate from the above, and NOT needed by `scripts/review.sh`. If your host agent has an
official plugin for the reviewing tool, it adds in-session commands without the copy-paste
loop. For Claude Code and Codex that is `openai/codex-plugin-cc`, which contributes:

- `/codex:review` — a Codex review against local git state.
- `/codex:adversarial-review` — a review that challenges the design, the tradeoffs and the
  assumptions rather than hunting implementation defects. Worth knowing separately: it asks
  a different question from the one `scripts/review.sh` asks, so it complements the gate
  instead of duplicating it.
- `/codex:rescue` — hand an investigation, or a fix you are stuck on, to a Codex subagent.
- `/codex:transfer` — move the whole session into a resumable Codex thread.

Installed with two slash commands **a human has to type** (an agent cannot invoke slash
commands):

```
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
```

The repository is `openai/codex-plugin-cc`, but its marketplace declares the name
`openai-codex`; `/plugin install` uses that declared name after `@`, not the repository
name. The [official marketplace manifest](https://github.com/openai/codex-plugin-cc/blob/main/.claude-plugin/marketplace.json)
was checked on 2026-09-06. A successful marketplace-add message names the registered
marketplace; do not retry registration under an inferred repository name.

An agent can prepare the configuration for you and tell you what to type; the typing and the
restart are yours.

Two cautions if you install it:

- **Check which of its commands a MODEL can invoke.** If any are model-invocable, a session
  can spend the other tool's budget without you deciding to. Write the project rule down:
  no session calls the second tool unless you asked for it in that session.
- **Leave any automatic review gate OFF.** The tempting setting makes the second model
  review every turn and block until fixes are applied. Unattended agent-to-agent loops burn
  a budget fast. All review here is manually triggered — record that decision so nobody
  turns it on later as a convenience.

Tool names, install commands and flags all rot. `setup/RESEARCH_PROTOCOL.md` is what keeps
this section current; if it disagrees with reality, reality wins and this file is wrong.

## 4. Check the machine — every session start, every machine

```sh
./scripts/doctor.sh
```

It changes nothing in the project and prints one `MISSING: <what> — fix: <command>` line per
trap, then `DOCTOR: ready` or `DOCTOR: setup incomplete` (exit 1). It checks what made a gate
fail for reasons unrelated to the code in the projects using the kit: the executable bit on
the scripts and hooks (on disk and in the git index), `core.hooksPath`, the git identity,
Python 3.10+, the second CLI `scripts/review.sh` calls, `tmux` when the worker script is
installed, the `node` a git hook resolves (nvm's default alias lives in the interactive
shell's rc file, so a hook never sees it), an npm cache owned by another user, and `grep`
shadowed by an alias or function in the interactive shell. To see that alias it starts your
interactive shell once (`$SHELL -ic`), so your rc files run, bounded to 5 s and skipped with a
NOTE where `timeout` is absent. It is not part of the gate and CI does not run it. When switching machines, this is the first command.

## 5. Prove the gate actually works

Once, on a fresh clone:

```sh
./scripts/check.sh --self-test
```

It injects each gate's failure condition and asserts the gate rejects it. A green
`CHECK: PASS` tells you the tree is clean; only the self-test tells you the gate could have
told you otherwise.

{{PROJECT_SETUP_STEPS}}
