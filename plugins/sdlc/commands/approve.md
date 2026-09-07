---
description: Sign the plan or implementation gate for the active workflow
argument-hint: "plan | implementation"
---

# Sign a gate

Gate: $ARGUMENTS

This command represents the **engineer's** approval. It is being run by them, on
purpose. Sign exactly the gate named — never a different one, and never both.

If `$ARGUMENTS` is empty, run `status` and ask which gate they mean rather than
guessing.

Before signing, make sure they have seen what they are approving:

- **plan** — `plan.md`, and `validation.md` if it exists. If the validator
  returned `NO-GO` or unresolved blockers, say so plainly before signing.
- **implementation** — `changes.md`, `tests.md`, `review.md`. If the reviewer
  returned `REQUEST-CHANGES`, or tests failed, state that clearly. They may
  still choose to approve; that is their call, but it must be an informed one.

Then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sdlc.py" approve <gate>
```

Afterwards, advance the phase and state what happens next.
