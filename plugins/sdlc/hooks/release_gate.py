#!/usr/bin/env python3
"""PreToolUse(Bash) -- the release gate.

Classifies every Bash command into HARD DENY / GATED / FREE. Gated commands run
only against a release signature bound to branch + HEAD + target.

Active whenever the repo carries `.aisdlc/profile.yml`, workflow in flight or
not. In a profiled repo `/sdlc:approve-push` is the only path for Claude to
commit, push, or open a PR.

Scope note: this is a governance guardrail, not a security boundary. It reads
the literal command string, so a determined bypass -- command substitution,
`bash -c`, a heredoc, an aliased binary, a script that shells out -- routes
around it. It exists to stop drift and accident, which is the actual threat.
See SECURITY.md for the full threat model.
"""

import os
import re
import shlex
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import sdlc_state as S  # noqa: E402

# Split a shell line into independently-classified segments. Newlines count:
# a multi-line Bash block is several commands, and classifying only the first
# would let `git status\ngit push origin main` through.
SEPARATORS = re.compile(r"&&|\|\||;|\||&|\n|\r")

# Rewriting published history. `-f` also arrives inside clusters like `-uf`,
# and the lease flags take an optional `=<ref>` suffix.
FORCE_FLAGS = {"-f", "--force", "--force-with-lease", "--force-if-includes"}

# Write every ref the local repo has -- protected branches included -- without
# ever naming a branch, so the refspec check below cannot see them.
BROADCAST_FLAGS = {"--all", "--mirror"}

# `git <these> <value> ...` -- the value is not the subcommand.
GIT_GLOBAL_VALUE_FLAGS = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--config-env",
}

# `git push <these> <value> ...` -- the value is not a refspec.
PUSH_VALUE_FLAGS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}

# Wrappers that pass through to the real command.
WRAPPERS = ("sudo", "command", "env", "nohup", "nice", "builtin", "exec")

# `gh` subcommands that publish, merge, approve or trigger CI. No signature
# unlocks these: they are outcomes a human owns, not steps in a release.
GH_DENY = {
    ("pr", "merge"): "merging a PR",
    ("pr", "review"): "approving or rejecting a PR",
    ("pr", "close"): "closing a PR",
    ("release", "create"): "publishing a release",
    ("release", "edit"): "editing a published release",
    ("release", "delete"): "deleting a release",
    ("release", "upload"): "uploading release assets",
    ("workflow", "run"): "triggering a workflow",
    ("workflow", "enable"): "enabling a workflow",
    ("workflow", "disable"): "disabling a workflow",
    ("run", "rerun"): "re-running a workflow",
    ("run", "cancel"): "cancelling a workflow run",
    ("repo", "delete"): "deleting a repository",
    ("secret", "set"): "writing a repository secret",
    ("secret", "delete"): "deleting a repository secret",
    ("variable", "set"): "writing a repository variable",
    ("auth", "logout"): "changing gh authentication",
}

# `gh api` is free to read and denied to write.
API_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def segments(command):
    return [seg.strip() for seg in SEPARATORS.split(command or "") if seg.strip()]


def tokenize(segment):
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def flags_of(tokens):
    """Every flag in `tokens`, with clusters expanded and `=<value>` stripped.

    `-uf` yields `-u` and `-f`; `--force-with-lease=main` yields
    `--force-with-lease`. Without this a one-character cluster hides a
    force-push from FORCE_FLAGS.
    """
    found = set()
    for token in tokens:
        if token == "--":
            break
        if token.startswith("--"):
            found.add(token.split("=", 1)[0])
        elif token.startswith("-") and len(token) > 1:
            found.add(token)
            found.update("-" + ch for ch in token[1:])
    return found


def subcommand(tokens):
    """(subcommand, index) skipping global options such as `git -C <dir>`.

    `git -C /elsewhere push origin main` must classify as a push, not fall
    through as an unrecognised token.
    """
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if not token.startswith("-"):
            return token, i
        i += 2 if token in GIT_GLOBAL_VALUE_FLAGS else 1
    return "", len(tokens)


def push_target(tokens, index, root):
    """Branch a `git push` writes to, best-effort.

    Handles `git push`, `git push origin`, `git push -u origin feat/x`,
    `git push origin HEAD:main`, `git push origin +main` (a `+` prefix is a
    forced refspec and must not hide the branch name from the protected check).
    """
    args, i = [], index + 1
    while i < len(tokens):
        token = tokens[i]
        if token in PUSH_VALUE_FLAGS:
            i += 2
            continue
        if not token.startswith("-"):
            args.append(token)
        i += 1
    if len(args) >= 2:
        refspec = args[1]
        dst = refspec.split(":")[-1] if ":" in refspec else refspec
        return dst.lstrip("+").replace("refs/heads/", "")
    return S.current_branch(root)


def forced_refspec(tokens, index):
    """True when any refspec is `+`-prefixed, i.e. a force-push in disguise."""
    for token in tokens[index + 1:]:
        if token.startswith("+") and len(token) > 1:
            return True
    return False


def classify_gh(tokens):
    """Return (verdict, reason) for a `gh ...` segment."""
    words = [t for t in tokens[1:] if not t.startswith("-")]
    pair = tuple(words[:2])
    if pair in GH_DENY:
        return "deny", (
            "%s is human-owned and no signature unlocks it. Do it yourself in the "
            "GitHub UI, or run the command directly with a leading `! `." % GH_DENY[pair]
        )
    if words[:1] == ["api"]:
        method = None
        for i, token in enumerate(tokens):
            if token in ("-X", "--method") and i + 1 < len(tokens):
                method = tokens[i + 1].upper()
            elif token.startswith("--method="):
                method = token.split("=", 1)[1].upper()
        if method in API_WRITE_METHODS:
            return "deny", (
                "`gh api -X %s` writes through the API and can reach merge, release "
                "and settings endpoints the gate cannot classify. Read-only `gh api` "
                "is allowed; run writes yourself with a leading `! `." % method
            )
        return "free", None
    if pair == ("pr", "create"):
        return "gated", None
    return "free", None


def classify(segment, profile, root):
    """Return (verdict, reason) where verdict is 'deny' | 'gated' | 'free'."""
    tokens = tokenize(segment)
    if not tokens:
        return "free", None

    # Strip leading env assignments and common wrappers.
    while tokens and ("=" in tokens[0] and not tokens[0].startswith("-")):
        tokens = tokens[1:]
    while tokens and tokens[0] in WRAPPERS:
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

    if tokens[0] == "gh":
        return classify_gh(tokens)

    if tokens[0] != "git":
        return "free", None

    sub, index = subcommand(tokens)

    if sub == "merge":
        branch = S.current_branch(root)
        if branch in protected:
            return "deny", (
                "merging into protected branch '%s' is human-owned." % branch
            )
        return "free", None

    if sub == "push":
        flags = flags_of(tokens)
        if flags & FORCE_FLAGS or forced_refspec(tokens, index):
            return "deny", (
                "force-push is never permitted by this framework. If a rewrite "
                "is genuinely required, run it yourself with `! %s`." % segment
            )
        if flags & BROADCAST_FLAGS:
            return "deny", (
                "`git push %s` writes every local ref, including protected "
                "branches, without naming one. Push a single branch explicitly."
                % ", ".join(sorted(flags & BROADCAST_FLAGS))
            )
        if "--dry-run" in flags:
            return "free", None
        target = push_target(tokens, index, root)
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
            sub, index = subcommand(tokens) if tokens and tokens[0] == "git" else ("", 0)
            branch = (
                push_target(tokens, index, root)
                if sub == "push"
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
