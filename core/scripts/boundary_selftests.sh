# Negative tests for scripts/boundary_checks.sh — SOURCED by check.sh --self-test.
#
# One case per check. First require a green baseline, then construct the violation,
# require both a nonzero exit and this check's specific diagnostic, and clean up.
# Set `st_fail=1` when a gate did not reject what it claims to reject. An unrelated
# failure or a diagnostic printed by a command that succeeded is not a passing test.
#
# `sh "$0"` re-runs the gate without the self-test flag, so it exits nonzero on a violation.
#
# REPLACE THIS WHOLE FILE alongside scripts/boundary_checks.sh.
#
# Worked example, matching the example check:
# The dot-prefixed injection is intended to avoid common build/lint include globs.
# Verify your project's actual include rules; dotfiles are not universally excluded.
#
#   if ! sh "$0" >/dev/null 2>&1; then
#     echo "  FAIL — domain/web baseline is already red; the injection would prove nothing."
#     st_fail=1
#   elif [ -e src/domain/.selftest.py ] || [ -L src/domain/.selftest.py ]; then
#     echo "  FAIL — the injection path already exists; refusing to overwrite owner content."
#     st_fail=1
#   else
#     mkdir -p src/domain && printf 'from myapp.web import router\n' > src/domain/.selftest.py
#     boundary_status=0
#     boundary_output=$(sh "$0" 2>&1) || boundary_status=$?
#     if [ "$boundary_status" -ne 0 ] && printf '%s\n' "$boundary_output" |
#         grep -Fq 'FAIL [boundary]: the domain layer imports the web layer:'; then
#       echo "  ok   — domain/web boundary gate rejects a forbidden import"
#     else
#       echo "  FAIL — the injection did not produce the domain/web gate's failure."
#       st_fail=1
#     fi
#     rm -f src/domain/.selftest.py
#   fi
#
# {{BOUNDARY_SELF_TESTS}}

# Existing-file probes need a different cleanup contract. Prefer a disposable project
# snapshot. If a test must modify an existing file, preserve its CURRENT bytes and mode
# (including uncommitted edits), not merely HEAD. Register restoration before mutation,
# restore before deleting backups, and exit after signal cleanup. Never replace the
# caller's cleanup trap with one that only deletes the backup directory.
#
# This separate worked example runs in a subshell so its traps do not replace the
# surrounding self-test traps. Its own backup directory is independent of the caller's.
# Adapt the target and diagnostic to your gate. A failed restore retains the backup and
# reports its location. SIGKILL/power loss cannot run shell traps: use a disposable
# snapshot for destructive probes that need protection from those failures too.
#
# | if (
# |   restore_target=src/domain/existing.py
# |   [ -f "$restore_target" ] && [ ! -L "$restore_target" ] || exit 1
# |   sh "$0" >/dev/null 2>&1 || exit 1
# |   restore_backup=$(mktemp -d) || exit 1
# |   if ! cp -p "$restore_target" "$restore_backup/original"; then
# |     rm -rf "$restore_backup"
# |     exit 1
# |   fi
# |   restore_and_exit() {
# |     restore_exit=$1
# |     trap '' INT TERM
# |     trap - EXIT
# |     if ! cp -p "$restore_backup/original" "$restore_target"; then
# |       echo "FAIL: restore failed; original remains at $restore_backup/original" >&2
# |       exit 1
# |     fi
# |     rm -rf "$restore_backup"
# |     exit "$restore_exit"
# |   }
# |   trap 'restore_and_exit "$?"' EXIT
# |   trap 'restore_and_exit 130' INT
# |   trap 'restore_and_exit 143' TERM
# |   printf 'from myapp.web import router\n' > "$restore_target" || exit 1
# |   restore_gate_status=0
# |   restore_gate_output=$(sh "$0" 2>&1) || restore_gate_status=$?
# |   [ "$restore_gate_status" -ne 0 ] && printf '%s\n' "$restore_gate_output" |
# |     grep -Fq 'FAIL [boundary]: the domain layer imports the web layer:'
# | ); then
# |   :
# | else
# |   restore_case_status=$?
# |   case "$restore_case_status" in
# |     130|143) exit "$restore_case_status" ;;
# |     *) st_fail=1 ;;
# |   esac
# | fi
