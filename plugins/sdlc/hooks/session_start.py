#!/usr/bin/env python3
"""SessionStart -- orient a fresh session inside an SDLC repo.

Injects the profile summary and any in-flight workflow so a session that starts
after /clear, or tomorrow, knows the phase, tier, pending gate, and that pushes
are gated. This is what makes /sdlc:resume cheap.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import sdlc_state as S  # noqa: E402


def main():
    data = S.read_hook_input()
    root = S.repo_root(data.get("cwd"))
    profile = S.load_profile(root)
    if profile is None:
        S.emit(None)

    base = S.profile_get(profile, "branch.base", "main")
    protected = ", ".join(str(b) for b in S.profile_get(profile, "branch.protected", []) or [])
    lines = [
        "# ai-sdlc active in this repo",
        "",
        "`.aisdlc/profile.yml` is present, so the release gate is ON.",
        "`git commit`, `git push` and `gh pr create` are BLOCKED until an engineer runs",
        "`/sdlc:approve-push`. Merging, force-pushing, pushing to a protected branch, and",
        "the profile's deploy commands are blocked outright and no approval unlocks them.",
        "Never try to route around the gate; surface the block to the engineer instead.",
        "",
        "- base branch: %s" % base,
        "- protected: %s" % (protected or "(none)"),
    ]

    commands = S.profile_get(profile, "commands", {}) or {}
    if commands:
        lines.append("- verification: " + "; ".join("%s=`%s`" % kv for kv in commands.items()))

    state = S.load_state(root=root)
    if state and state.get("phase") != "closed":
        pending = [
            name
            for name, gate in (state.get("gates") or {}).items()
            if gate.get("required") and not gate.get("approved")
        ]
        lines += [
            "",
            "## Workflow in flight: %s" % state.get("id"),
            "- mode/tier: %s / %s" % (state.get("mode"), state.get("tier")),
            "- phase: %s" % state.get("phase"),
            "- branch -> target: %s -> %s" % (state.get("branch"), state.get("target")),
            "- unsigned gates: %s" % (", ".join(pending) or "none"),
            "- artifacts: .aisdlc/work/%s/" % state.get("id"),
            "",
            "Run `/sdlc:status` for detail, or `/sdlc:resume` to continue it.",
        ]
    else:
        lines += ["", "No workflow in flight. Start one with `/sdlc:feature` or `/sdlc:fix`."]

    S.context("\n".join(lines), event="SessionStart")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        S.emit(None)
