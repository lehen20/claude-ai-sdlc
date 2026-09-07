---
name: sdlc-risk-tiering
description: This skill should be used when choosing how much ceremony an ai-sdlc change needs — scoring a change as express, standard or full tier, deciding whether a plan gate is warranted, or handling a forced escalation from high-risk paths. Use at workflow intake and whenever the scope of a change grows mid-flight.
version: 0.1.0
---

# Risk tiering

Ceremony must be proportional to blast radius. Four approvals on a one-line log
change is how a governance framework gets abandoned; one approval on a schema
migration is how it fails. Tiering is what keeps both from happening.

## Tiers

| | express | standard | full |
|---|---|---|---|
| plan gate | no | yes | yes |
| implementation gate | no | yes | yes |
| **release gate** | **yes** | **yes** | **yes** |
| worktree isolation | no | no | yes |

The release gate is in every tier. Express skips deliberation, never
authorisation — nothing reaches a remote unsigned.

## Scoring

**express** — all of:
- one or two files, no public interface change
- no schema, migration, config or dependency change
- no path in `profile.high_risk_paths`
- behaviour is obvious from the diff and covered by existing tests
- targets `profile.branch.base`

Typical: a log line, a copy fix, a constant, a comment, a narrow null guard.

**standard** — the default. Anything that changes behaviour a caller depends on,
adds a code path, or needs new tests. **When genuinely torn, choose standard.**

**full** — forced, not chosen, when **any** of:
- a path matching `profile.high_risk_paths` is touched
- a database schema or migration changes
- a public API, event contract or shared-package interface changes
- the target is anything other than `profile.branch.base`
- the fix is for a `P0`/`P1`-equivalent incident
- the change spans more than one service in `profile.repos`

## Rules

**Escalation is automatic and not negotiable.** If a forcing condition is met,
say the tier is full and why. Do not offer to lower it, and do not accept "just
do it as express" — the engineer can override by editing the profile, which is a
deliberate act, not a passing instruction.

**De-escalation requires the engineer.** You may propose that standard is
overkill; you may not decide it.

**Re-score when scope grows.** If implementation reveals the change touches a
high-risk path the plan missed, stop, tell the engineer, and escalate:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sdlc.py" tier full
```

Escalating after the plan gate was signed does not re-open it — the plan was
still approved. It adds the worktree and the branch/sync confirmation only.

## Stating a tier

Give the tier, the deciding factor, and nothing else:

> Standard tier — changes the retry path that three callers depend on, but no
> schema or high-risk path.

> Full tier (forced) — touches `src/auth/session.py`, which matches
> `high_risk_paths`.
