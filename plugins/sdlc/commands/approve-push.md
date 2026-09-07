---
description: Sign the release gate, authorising commit, push and PR creation
argument-hint: "[--target <branch>]"
---

# Sign the release gate

Arguments: $ARGUMENTS

This is the gate that lets Claude write to the remote. It binds to the current
branch, the current `HEAD` commit, and the PR target — **any new commit voids
it**, by design.

## Before signing

1. Run `status` and confirm any required plan/implementation gates are signed.
   The CLI refuses to sign the release gate while an earlier gate is pending.
2. **Everything must already be committed.** If there are uncommitted changes,
   commit them first, then sign — signing before the final commit just invalidates
   the signature immediately.
3. Show the engineer exactly what they are authorising: the branch, the commit
   SHA and subject, the PR target, and a one-line summary of the diff. If tests
   failed or the review returned `REQUEST-CHANGES`, say so before they sign.

## Sign

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sdlc.py" approve-push $ARGUMENTS
```

With no workflow in flight this mints a minimal ad-hoc record so the push is
still signed and auditable. That is the gate being satisfied, not bypassed.

## After

Hand off to the `sdlc-release-packager` agent to write `pr.md`, push, and open
the PR. Then report the PR URL and state what stays human-owned: review,
approval, merge, and any promotion beyond the base branch.
