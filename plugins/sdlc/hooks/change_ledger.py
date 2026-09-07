#!/usr/bin/env python3
"""PostToolUse(Edit|Write) -- append every file mutation to changes.jsonl.

The reviewer reads this rather than trusting a narrative of what changed. It is
also what survives a /clear: the ledger is on disk, the conversation is not.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import sdlc_state as S  # noqa: E402


def main():
    data = S.read_hook_input()
    target = (data.get("tool_input") or {}).get("file_path") or ""
    if not target:
        S.emit(None)

    root = S.repo_root(data.get("cwd"))
    if not root or S.load_profile(root) is None:
        S.emit(None)

    directory = S.work_dir(root=root)
    if not directory or not os.path.isdir(directory):
        S.emit(None)

    if S.is_inside(target, os.path.join(root, S.WORK_ROOT)):
        S.emit(None)  # don't log the workflow logging itself

    try:
        relative = os.path.relpath(os.path.abspath(target), root)
    except ValueError:
        relative = target

    entry = {
        "ts": S.now(),
        "tool": data.get("tool_name"),
        "file": relative,
        "agent": data.get("agent_type") or "main",
    }
    with open(os.path.join(directory, "changes.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")

    S.emit(None)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        S.emit(None)  # ledger failure must never interrupt work
