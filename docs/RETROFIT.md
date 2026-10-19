# Retrofitting a project that is already under way

`bootstrap.sh` skips files that already exist, so it is safe to run in a live repository.
That makes the mechanics easy. The sequencing is the part that needs care.

**Do not big-bang an in-flight project.** Take the steps in this order; each one is
independently useful, and each one is small enough to abandon if it turns out not to fit.

**The install itself is one sitting.** `bootstrap.sh` wires the pre-commit gate at once, and
the gate fails on every `{{PLACEHOLDER}}` marker left in the installed files: from the install
until the setup interview (`setup/INTERVIEW.md`) has filled them all, EVERY commit in that
clone is refused, an unrelated one too. Run the interview straight after the install. Only
the owner may bypass the hook meanwhile (`--no-verify`); CI and other clones are not affected,
since `core.hooksPath` is local. The steps below are the order in which the interview's
answers are worth getting right, not commits to spread over weeks.

## The order, and why

### 1. `scripts/check.sh` and `.githooks/pre-commit`

Start here even if the gate initially checks almost nothing. It establishes the thing
everything else depends on: ONE definition of green that CI, the hook and every agent run.

Wire the build and test command first, get it passing, then add boundary checks one at a
time — each with its negative test.

A hook the project already had keeps running beside the kit's: move it to
`.githooks/<same name>.project` (executable, with a `#!` line), and the kit's hook of that
name runs it first with git's arguments; a hook name the kit does not ship (`pre-push`, ...)
goes to `.githooks/<same name>` itself. A one-line `.project` file can `exec` the hook where
it lives (`docs/DEV_SETUP.md`). Never merge a hook's logic into a kit-owned hook: the next
sync overwrites it. Do not try to encode every rule you have ever wanted on
day one; a gate that fails constantly on pre-existing violations gets bypassed within a
week, and then you have taught everyone that bypassing it is normal.

For violations that already exist and are not worth fixing today: fix them, or narrow the
check's scope to new code, and write down which you chose. Do not add a blanket escape
hatch.

### 2. The instruction file

If the project already has one, **align rather than replace.** Read what is there, keep the
project-specific rules it already encodes, and fold in the kit's structure around them.
Replacing an instruction file that people have been following is how you lose rules nobody
remembers writing but everyone relies on.

Add the one-line pointers for other tools. Delete any duplicated copies —
[one canonical file](one-canonical-instruction-file.md).

### 3. The review gate

`docs/REVIEW_GATE.md` plus the duties-toward-the-owner block in the constitution.

The important work here is not installing the file, it is **naming the risky areas.** That
list is the most project-specific decision in the whole kit, and a generic one is worse than
none: it triggers on everything, so it triggers on nothing.

If the project already has a reviewer definition or a cross-review habit, generalise what it
already does and record the areas it already covers.

### 4. `docs/WORKFLOW.md`

Task lifecycle, sizing, the decay early-warning list, the periodic audit. Mostly this
formalises what a functioning project already does informally — which is exactly why it is
worth writing down before the informal version depends on one person's memory.

Add the audit as a scheduled task now, even if the first one is months away. An audit that
is not on a schedule does not happen.

### 5. `docs/HANDOFF.md`

Cheap, and it pays immediately if more than one tool touches the repository.

### 6. The state file and the token levers

Last, because they need the rest to be in place to make sense. If the project already has a
state or notes file, keep it and apply the discipline
([memory-across-tools](memory-across-tools.md)): delete completed work, tag permanent
findings, route them to a home before pruning.

Expect the first harvest to be large. That is normal and it is the point.

## What to confirm before touching anything

A live project has rules and habits that are not written down. Before replacing a file,
ask the owner what it is doing that you cannot see. The kit is opinionated; the project has
been running longer than you have been reading it.

## What NOT to do

- Do not install every overlay and pattern because they exist. Take what applies.
- Do not add a gate for a rule the project does not actually follow yet. Fix the code or
  drop the rule; a permanently red gate teaches people to ignore red.
- Do not rewrite history or reformat files to match kit style. The diff noise buries the
  actual change and makes the retrofit unreviewable.
