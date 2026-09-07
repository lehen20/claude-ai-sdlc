#!/usr/bin/env python3
"""PreToolUse(Bash) -- the release gate.

Classifies every Bash command into HARD DENY / GATED / FREE. Gated commands run
only against a release signature bound to branch + HEAD + target.

Active whenever the repo carries `.aisdlc/profile.yml`, workflow in flight or
not. In a profiled repo `/sdlc:approve-push` is the only path for Claude to
commit, push, or open a PR.

Scope note: this is a governance guardrail, not a security boundary. It reads
the literal command string, so command substitution or a heredoc could route
around it. It exists to stop drift and accident, which is the actual threat.
"""

import os
import re
import shlex
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import sdlc_state as S  # noqa: E402

# Split a shell line into independently-classified segments.
SEPARATORS = re.compile(r"&&|\|\||;|\|")

FORCE_FLAGS = {"-f", "--force", "--force-with-lease"}


def segments(command):
    return [seg.strip() for seg in SEPARATORS.split(command or "") if seg.strip()]


def tokenize(segment):
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def push_target(tokens, root):
    """Branch a `git push` writes to, best-effort.

    `git push`, `git push origin`, `git push -u origin feat/x`,
    `git push origin HEAD:main`, `git push origin src:dst`.
    """
    args = [t for t in tokens[2:] if not t.startswith("-")]
    if len(args) >= 2:
        refspec = args[1]
        dst = refspec.split(":")[-1] if ":" in refspec else refspec
        return dst.replace("refs/heads/", "")
    return S.current_branch(root)


def classify(segment, profile, root):
    """Return (verdict, reason) where verdict is 'deny' | 'gated' | 'free'."""
    tokens = tokenize(segment)
    if not tokens:
        return "free", None

    # Strip leading env assignments and common wrappers.
    while tokens and ("=" in tokens[0] and not tokens[0].startswith("-")):
        tokens = tokens[1:]
    if tokens and tokens[0] in ("sudo", "command", "env"):
        tokens = tokens[1:]
    if not tokens:
        return "free", None

    normalized = " ".join(tokens)
    protected = [str(b) for b in (S.profile_get(profile, "branch.protected", []) or [])]

    # --- project-declared hard denies (deploy/release/infra) ---
    for pattern in S.profile_get(profile, "deny_patterns", []) or []:
        try:
            if re.search(str(pattern), normalized):
                return "deny", (
                    "matches deny_patterns entry %r in .aisdlc/profile.yml. "
                    "Deployments and releases are human-owned; run it yourself "
                    "with `! %s` if intended." % (pattern, segment)
                )
        except re.error:
            continue

    if tokens[0] == "gh" and len(tokens) >= 3 and tokens[1] == "pr":
        if tokens[2] == "merge":
            return "deny", (
                "merging a PR is human-owned and no signature unlocks it. "
                "Merge it yourself in the GitHub UI or with `! gh pr merge`."
            )
        if tokens[2] == "create":
            return "gated", None
        return "free", None

    if tokens[0] != "git":
        return "free", None

    sub = tokens[1] if len(tokens) > 1 else ""

    if sub == "merge":
        branch = S.current_branch(root)
        if branch in protected:
            return "deny", (
                "merging into protected branch '%s' is human-owned." % branch
            )
        return "free", None

    if sub == "push":
        flags = {t for t in tokens if t.startswith("-")}
        if flags & FORCE_FLAGS:
            return "deny", (
                "force-push is never permitted by this framework. If a rewrite "
                "is genuinely required, run it yourself with `! %s`." % segment
            )
        if "--dry-run" in flags:
            return "free", None
        target = push_target(tokens, root)
        if target in protected:
            return "deny", (
                "'%s' is a protected branch in .aisdlc/profile.yml; pushes go to a "
                "feature branch and reach it through a reviewed PR." % target
            )
        return "gated", None

    if sub == "commit":
        return "gated", None

    return "free", None


def main():
    data = S.read_hook_input()
    command = (data.get("tool_input") or {}).get("command", "")
    if not command:
        S.allow()

    root = S.repo_root(data.get("cwd"))
    profile = S.load_profile(root)
    if profile is None:
        S.allow()  # not an SDLC repo -- the framework stands down entirely

    state = S.load_state(root=root)

    for segment in segments(command):
        verdict, reason = classify(segment, profile, root)
        if verdict == "deny":
            S.deny("BLOCKED by ai-sdlc: %s" % reason)
        if verdict == "gated":
            tokens = tokenize(segment)
            branch = (
                push_target(tokens, root)
                if len(tokens) > 1 and tokens[1] == "push"
                else S.current_branch(root)
            )
            error = S.release_signature_error(state, branch, root=root)
            if error:
                S.deny(
                    "BLOCKED by ai-sdlc release gate: %s.\n"
                    "Command: %s\n"
                    "Fix: run /sdlc:approve-push to sign this release, then retry. "
                    "Do not attempt to work around this gate." % (error, segment)
                )

    S.allow()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # a crashing hook must never brick the session
        S.emit({"systemMessage": "ai-sdlc release_gate error (allowing): %s" % exc})
