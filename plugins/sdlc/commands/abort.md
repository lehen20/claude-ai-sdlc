---
description: Close the active ai-sdlc workflow and revoke its gates
---

# Abort the active workflow

Show the engineer what is being closed first — the workflow id, phase, and which
artifacts exist — and confirm, since this revokes every signed gate.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sdlc.py" abort
```

This only closes workflow state. **Code changes, branches and commits are left
exactly as they are** — say so explicitly, and tell them the artifacts remain
readable under `.aisdlc/work/<id>/` if they want them.

If what they actually wanted was to undo code changes, do not use this command;
ask them what they want reverted.
