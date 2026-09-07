#!/usr/bin/env python3
"""Stop -- checkpoint the workflow and expire a stale release signature.

If HEAD moved since the release gate was signed, the signature is revoked here
rather than waiting for the next push attempt. Belt and braces: release_gate.py
re-checks it anyway, but expiring eagerly keeps state.json honest for anyone
reading it as an audit record.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import sdlc_state as S  # noqa: E402


def main():
    data = S.read_hook_input()
    root = S.repo_root(data.get("cwd"))
    if not root or S.load_profile(root) is None:
        S.emit(None)

    state = S.load_state(root=root)
    if not state:
        S.emit(None)

    changed = False
    gate = (state.get("gates") or {}).get("release") or {}
    if gate.get("approved"):
        current = S.head_sha(root)
        if current and gate.get("head_sha") != current:
            gate.update({"approved": False, "expired_at": S.now(), "expired_reason": "HEAD moved"})
            changed = True

    branch = S.current_branch(root)
    if branch and state.get("branch") != branch:
        state["branch"] = branch
        changed = True

    if changed:
        state["updated_at"] = S.now()
        S.save_state(state, root=root)
        S.emit({"systemMessage": "ai-sdlc: release signature expired (HEAD moved). Re-run /sdlc:approve-push before pushing."})

    S.emit(None)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        S.emit(None)
