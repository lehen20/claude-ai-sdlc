---
description: Show the current ai-sdlc workflow phase, tier, gates and artifacts
---

# Workflow status

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sdlc.py" status
```

Present the result readably. If a workflow is in flight, also:

- list which artifacts exist in the work directory and which are still missing
  for the current phase
- name the **next action** and whose it is — yours or the engineer's
- if a gate is pending, give the exact command that signs it

If no workflow is in flight, say so and offer `/sdlc:feature`.
