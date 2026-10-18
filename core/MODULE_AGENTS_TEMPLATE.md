<!-- KIT-OWNED: do not edit locally; change it in the kit and re-sync. -->

# /{{MODULE}} rules

<!-- Copy this to each top-level module folder as its AGENTS.md, alongside a two-line
     pointer file for whichever tools you use. Delete the KIT-OWNED line at the top of the
     copy: the sync owns this template, never the module's file, which the project edits. Keep it under ~25 lines: it is read
     on top of the root constitution, and it must not repeat the root's rules.

     Write only what is TRUE HERE AND NOWHERE ELSE. A rule that applies project-wide
     belongs in the root AGENTS.md; duplicating it means two copies that drift. -->

- What this folder is, in one sentence, and what it is NOT allowed to contain.
- The boundary that defines it: which dependencies are forbidden here, and which gate in
  `scripts/check.sh` enforces that. If nothing enforces it, say so — an unenforced boundary
  is a request, not a rule.
- The one mistake someone will make here, stated as a rule with its reason. This is the
  line that earns the file.
- Testing expectation for this folder, if it differs from the root rule.
- Anything this folder must call rather than re-implement, and where that lives.
