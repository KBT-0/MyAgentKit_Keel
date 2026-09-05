# Why each rule exists

The kit's files state rules tersely, because they are read at the start of every session and
length there is a recurring cost. The reasoning lives here, where it is read once.

Each page ends with **the failure mode it prevents**. If you are deciding whether to keep a
rule, that last section is the one to read — a rule whose failure mode no longer applies to
you should be deleted, and a rule you cannot find a failure mode for was never load-bearing.

| Page | The principle |
|---|---|
| [rules-that-enforce](rules-that-enforce.md) | A rule nothing enforces is a request |
| [gates-must-be-proven-red](gates-must-be-proven-red.md) | A gate you have only seen pass has not been tested |
| [one-canonical-instruction-file](one-canonical-instruction-file.md) | Tool-specific instruction files are pointers, never copies |
| [memory-across-tools](memory-across-tools.md) | If it is not in the state file, it did not happen |
| [knowledge-has-three-horizons](knowledge-has-three-horizons.md) | Permanent, episodic and momentary knowledge need three different files |
| [decorrelated-review](decorrelated-review.md) | The author of a change never reviews it |
| [context-is-a-budget](context-is-a-budget.md) | Every always-loaded file is a bill paid per session |
| [delegation-is-not-symmetric](delegation-is-not-symmetric.md) | The review roles swap; the plumbing under them does not |

Operational pages: [UPDATING](UPDATING.md) (how a project takes kit changes, and how it
sends lessons back), [RETROFIT](RETROFIT.md) (installing into a project already under way),
[ACCEPTANCE](ACCEPTANCE.md) (what was verified in this release, and how).
