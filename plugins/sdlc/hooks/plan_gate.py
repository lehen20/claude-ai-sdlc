#!/usr/bin/env python3
"""PreToolUse(Edit|Write|NotebookEdit) -- the plan gate.

Blocks source edits while an active workflow's tier requires a plan approval
that has not been signed. Unlike the release gate this applies only during a
workflow: outside one, ordinary editing is untouched.

Never blocks writes to `.aisdlc/` itself -- that is where the plan being
approved is written.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import sdlc_state as S  # noqa: E402


def main():
    data = S.read_hook_input()
    target = (data.get("tool_input") or {}).get("file_path") or ""

    root = S.repo_root(data.get("cwd"))
    if not root or S.load_profile(root) is None:
        S.allow()

    # Artifacts and profile are always writable.
    if target and S.is_inside(target, os.path.join(root, S.WORK_ROOT)):
        S.allow()

    state = S.load_state(root=root)
    if not state or state.get("phase") == "closed":
        S.allow()  # no workflow in flight

    gate = (state.get("gates") or {}).get("plan") or {}
    if not gate.get("required") or gate.get("approved"):
        S.allow()

    S.deny(
        "BLOCKED by ai-sdlc plan gate: workflow '%s' is %s tier and its plan is not "
        "approved yet.\nCurrent phase: %s\nFix: finish the plan at .aisdlc/work/%s/plan.md, "
        "then the engineer runs /sdlc:approve plan. Do not edit source before that."
        % (state.get("id"), state.get("tier"), state.get("phase"), state.get("id"))
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        S.emit({"systemMessage": "ai-sdlc plan_gate error (allowing): %s" % exc})
