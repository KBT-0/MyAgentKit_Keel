# {{PROJECT_NAME}} gate configuration — SOURCED by scripts/check.sh and scripts/review.sh, never run.
#
# PROJECT-OWNED: this project's values for the kit's gate and review wrapper. Those two scripts
# are KIT-OWNED and every sync replaces them; this file is never synced over (#94). Each line
# below is a VALUE, not code: a placeholder that has to be replaced INSIDE a comment is a trap,
# because a half-finished edit leaves the code commented out and the gate silently toothless.
# A value this file leaves out takes the kit's default in check.sh or review.sh, and an
# unconfigured build command FAILS the gate.

# --- scripts/check.sh --------------------------------------------------------------------

# Toolchains are commonly installed per-user and then missing from the PATH of git hooks
# and other non-login shells; without this the gate fails for the wrong reason. check.sh
# prepends it before anything else runs, and doctor.sh reads it from this line, so keep it
# on one line in this form. Example: "$HOME/.dotnet". Leave empty if nothing extra is needed.
toolchain_path="{{TOOLCHAIN_PATH_SETUP}}"

# One shell command that builds and tests, run by the gate on every commit (check.sh,
# section 4, says what it may not do). No step here may write to a remote (upload, publish,
# push, migrate a live database), need a deploy credential (an API token, a login) or change
# what users see. A step that only reads the project and writes inside the checkout may stay
# even when it is spelled like a deploy (`wrangler deploy --dry-run --outdir <dir>` compiles
# "without actually deploying", developers.cloudflare.com/workers/wrangler/commands/workers/;
# `terraform validate` "does not validate remote services", developer.hashicorp.com/terraform/
# cli/commands/validate), once it is recorded: one `# read-only:` line below names the exact
# step and why it writes nothing remote, checked with the deploy credentials unset (#300).
# An agent's permission layer may still read such a step as a production deploy and refuse the
# whole gate (it did once); give it an allow rule for that exact command (a Claude Code
# `permissions.allow` entry such as `Bash(npm run check)`, code.claude.com/docs/en/permissions),
# or move the step to its own CI job. Use 'true' if this project genuinely has nothing to run.
# read-only: (none)
build_test_cmd="{{BUILD_TEST_COMMAND}}"

# A commit that changes only documentation skips the build/test command, and nothing else:
# every scan and check has run. 1: on. 0: off, for a project whose build reads markdown
# everywhere (a documentation site).
docs_only_skip_build=1
# The documents a build or a test does read (a doc test, a generated page): a commit that
# changes one builds (#97). Space-separated paths or globs from the top of the repository,
# matched as Python's fnmatch.fnmatchcase does (a * also crosses a /): "docs/api/*.md README.md".
docs_always_build=""

# BUILD CACHE (check.sh, section 4, says what the key holds). build_cache_inputs is a command
# that prints whatever else the build depends on, which the tree does not hold. Starters, keep
# the ones your build uses (a missing tool fails the command, and a failing command means no
# cache):
#   cmake --version; ninja --version
#   cl 2>&1 | head -n 1                     # the MSVC banner (compiler version)
#   python --version; python -m pip freeze | sha256sum
#   blender --version
#   git lfs ls-files -l                     # LFS objects by id
#   echo "CC=$CC CXX=$CXX"                  # environment the build reads
# Unity: ProjectSettings/ProjectVersion.txt and Packages/packages-lock.json are tracked, so
# already in the key; Library/ is a cache Unity rebuilds and stays out.
# Ignored files (fetched dependencies, a build folder) and environment variables are NOT in the
# key unless this command prints them. Empty, there is no cache: an input nobody fingerprinted
# would otherwise pass on a stale result. Use "true" for a build that reads nothing but the
# tree. Entries expire after cache_days days.
build_cache_inputs=""
cache_days=7

# The folders whose subfolders are modules, space-separated, e.g. "src packages": each module
# folder must be named in the "## Module map" of docs/ARCHITECTURE.md (check.sh, section 2c).
# Empty, nothing is checked and a NOTE says so: a single-module project has no module folders.
module_roots=""

# The strong review cycle runs at least every STRONG_REVIEW_DAYS days or after
# STRONG_REVIEW_TASKS closed tasks, whichever comes first (docs/WORKFLOW.md, "The strong review
# cycle"): owner choices, not measured values.
STRONG_REVIEW_DAYS=10
STRONG_REVIEW_TASKS=20

# --- scripts/review.sh -------------------------------------------------------------------
#
# Pins are fixed snapshots and per reviewer: Codex's JSONL names no model, so the pin is the only
# record, and the vendors' id formats differ (platform.claude.com/docs/en/about-claude/models/model-ids-and-versions;
# learn.chatgpt.com/docs/non-interactive-mode). Critical work (WORKFLOW rule 7): set
# REVIEW_CLAUDE_MODEL to the strongest tier for that run.
#
# Both models are PINNED BY NAME, in both directions. An unpinned run records the reviewing
# CLI's own default, which is a moving target: two records made a month apart then claim the
# same provenance while naming no model that can be compared or reproduced. Codex emits no
# model identity in its JSON output, so there is nothing to fall back on and nothing to
# attest against — the pin is the only record there is, and an empty pin is a hard stop.
#
# BOTH ship empty on purpose. A kit that pre-filled one side would be quietly naming which
# vendor it expected in that role, and the setup interview would stop asking.
#
# The pins are per-reviewer rather than one shared REVIEW_MODEL: a single override would
# hand a Codex model id to Claude the moment the roles swapped, which is the exact failure
# this role-neutral wrapper exists to prevent. doctor.sh and check.sh read DEFAULT_REVIEWER and
# CODEX_MODEL from these lines, so keep each on a line of its own in this form.
DEFAULT_REVIEWER="claude"
CODEX_MODEL=""
CLAUDE_MODEL=""
