# Project boundary checks — SOURCED by scripts/check.sh, never executed on its own.
#
# Available to you here: `scan_grep <extended-regex>` (searches tracked and
# untracked-but-not-ignored files, printing path:line:text) and the `fail` variable.
# Set `fail=1` to fail the build. If the scanner itself fails mid-scan, check.sh fails the
# whole gate at the end — you do not need to handle that case, and `$(scan_grep …)` is safe.
#
# REPLACE THIS WHOLE FILE with your project's checks. Do not edit around the comments —
# the file is the unit of replacement precisely so that a half-edit cannot leave a check
# sitting inside a comment, which is how a gate ends up enforcing nothing.
#
# Every check here needs a fixture test in the project's test suite: a small input that breaks
# the rule turns the check red with its own FAIL line, and a clean one leaves it green. A check
# that has never been observed rejecting anything has not been tested.
#
# Worked example — a domain layer that must not depend on the delivery layer:
#
#   hits=$(scan_grep 'from myapp\.web' | grep '^src/domain/')
#   if [ -n "$hits" ]; then
#     echo "FAIL [boundary]: the domain layer imports the web layer:"
#     echo "$hits"
#     fail=1
#   fi
#
# Its fixture test, e.g. tests/boundary_checks_test.sh, run by the build/test command in
# scripts/check.sh (`sh tests/boundary_checks_test.sh && <your build>`). Each case writes one
# file into a throwaway folder and sources this file there, with a scan_grep over that folder
# only: it never touches the checkout and never runs the whole gate or the build, so a case
# costs milliseconds (docs/WORKFLOW.md, "Writing a gate"; Semgrep's ruleid/ok cases):
#
# > checks="$(pwd)/scripts/boundary_checks.sh" status=0
# > scan_grep() { find . -type f | sed 's|^\./||' | xargs grep -HInE -e "$1" --; }
# > expect() {  # expect <red|green> <the check's FAIL line, or -> <path> <line of the file>
# >   dir=$(mktemp -d) && mkdir -p "$dir/$(dirname "$3")" && printf '%s\n' "$4" > "$dir/$3"
# >   out=$(CDPATH= cd -- "$dir" && fail=0 && . "$checks" && exit "$fail"); rc=$?
# >   rm -rf "$dir"
# >   case "$1:$rc" in
# >     red:0|green:[!0]*) printf '%s\n' "FAIL: $3 should turn the check $1: $out"; status=1 ;;
# >     red:*) case "$out" in *"$2"*) ;; *) printf '%s\n' "FAIL: $3 is red without '$2': $out"; status=1 ;; esac ;;
# >   esac
# > }
# > expect red 'FAIL [boundary]: the domain layer imports the web layer:' src/domain/order.py 'from myapp.web import router'
# > expect green - src/web/order.py 'from myapp.web import router'
# > exit "$status"
#
# IF A CHECK GUARDS A PATH THAT DOES NOT EXIST YET, SAY SO OUT LOUD. Writing the gate
# before the module is good practice; letting it stay silent is not. A scan over a missing
# directory finds nothing, which looks exactly like a clean result — so the check accrues
# the credibility of a gate while doing nothing, and when the module finally lands (quite
# possibly under a slightly different name) nothing announces that it was missed. A real
# project shipped precisely this on its money modules and the gate had never once run.
#
#   GUARDED="src/billing src/ledger"
#   present=""
#   for d in $GUARDED; do [ -d "$d" ] && present="$present $d"; done
#   if [ -z "$present" ]; then
#     echo "NOTE [boundary]: none of $GUARDED exists yet — this check is DORMANT."
#     echo "                 It arms itself when one appears; if the module lands under a"
#     echo "                 different name, update GUARDED in the same commit."
#   else
#     hits=$(scan_grep 'forbidden_pattern' | grep -E "^($(echo $present | tr ' ' '|'))/")
#     ...
#   fi
#
# {{BOUNDARY_CHECKS}}
