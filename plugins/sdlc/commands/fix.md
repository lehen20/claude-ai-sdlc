---
description: Start a governed defect-fix workflow
argument-hint: "[ticket-ref] <description of the defect>"
---

# Fix workflow

Report: $ARGUMENTS

Load the `sdlc-workflow` skill and drive the lifecycle. Load `sdlc-risk-tiering`
to pick a tier and `sdlc-artifacts` for the artifact shapes.

A fix differs from a feature in one way that matters: **you must establish the
cause before proposing a change.** A plan that only describes a symptom is not
approvable.

## Intake

1. Confirm the repo is initialised (`.aisdlc/profile.yml` exists). If not, stop
   and point at `/sdlc:init`.
2. Capture, in `request.md`: observed behaviour, expected behaviour, and how to
   reproduce. If you cannot reproduce it, say so explicitly — that is a finding,
   not a detail to gloss over.
3. **Ask the engineer for the branch.** Never assume or invent one. Offer a name
   built from `profile.branch.prefixes.fix` and the report. Confirm the PR
   target too, defaulting to `profile.branch.base`.
4. Propose a tier. A one-line fix in a high-risk path is still Full tier —
   escalation from `profile.high_risk_paths` is automatic and not negotiable.
5. Create the branch, sync it with the base branch, then start the workflow:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sdlc.py" start \
  --mode fix --tier <tier> --branch <branch> [--ref <ticket>] [--target <target>]
```

## Then

Follow the phase table in `sdlc-workflow`, with the analysis phase carrying real
weight: write `analysis.md` naming the cause and the evidence for it before
writing `plan.md`.

Add a regression test that fails before the fix and passes after, and record it
in `regression.md`. A fix without one is a fix that comes back.

Stop at every gate. Never sign a gate yourself.
