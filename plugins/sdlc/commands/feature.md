---
description: Start a governed feature delivery workflow
argument-hint: "[ticket-ref] <description of the feature>"
---

# Feature workflow

Request: $ARGUMENTS

Load the `sdlc-workflow` skill and drive the lifecycle. Load `sdlc-risk-tiering`
to pick a tier and `sdlc-artifacts` for the artifact shapes.

## Intake

1. Confirm the repo is initialised (`.aisdlc/profile.yml` exists). If not, stop
   and point at `/sdlc:init`.
2. If the request is too vague to plan against, ask now — not after planning.
   One round of specific questions, not a questionnaire.
3. **Ask the engineer for the branch.** Never assume or invent one. Offer a name
   built from `profile.branch.prefixes` and the request, and let them accept or
   replace it. Confirm the PR target too, defaulting to `profile.branch.base`.
4. Propose a tier with one line of reasoning. Escalation from
   `profile.high_risk_paths` is automatic and not negotiable.
5. Create the branch, sync it with the base branch, then start the workflow:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sdlc.py" start \
  --mode feature --tier <tier> --branch <branch> [--ref <ticket>] [--target <target>]
```

6. Write `request.md` into the work directory.

## Then

Follow the phase table in `sdlc-workflow`: `plan` → **gate** → `implement` →
`validate` → **gate** → `package` → **gate** → push and PR.

Stop at every gate. Report what the engineer needs in order to decide — lead
with risks and open questions, not with what went well — and wait. Never sign a
gate yourself, and never continue past one on the assumption it would be approved.
