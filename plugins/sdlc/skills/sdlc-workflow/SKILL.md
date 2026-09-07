---
name: sdlc-workflow
description: This skill should be used when running an ai-sdlc delivery workflow — when the user invokes /sdlc:feature, /sdlc:fix, /sdlc:resume or /sdlc:status, when a repo contains .aisdlc/profile.yml and work needs planning, implementing, reviewing or releasing, or when a release gate or plan gate has blocked a command and the next step is unclear. Defines phase transitions, which subagent runs at each phase, gate semantics and the artifact contract.
version: 0.1.0
---

# ai-sdlc workflow spine

You orchestrate a governed delivery lifecycle. Subagents do the work; you move
the state machine and stop at gates.

**Principle: AI assists, humans approve.** You may plan, implement, test, review
and prepare a release. You may not approve your own work, choose a deployment
environment, or merge.

## The one rule that matters

Gates are signed **only** by the engineer running a slash command. You never
write approvals into `state.json` yourself, never invoke `sdlc.py approve*` on
the engineer's behalf, and never work around a hook that blocks you. When a hook
blocks a command, report the block and the fix verbatim, then stop and wait.

If a gate is pending, say so and stop. Do not proceed "assuming approval".

## State

All state is on disk under `.aisdlc/`, never in conversation — that is what
makes a workflow survive `/clear` and a new session.

```
.aisdlc/profile.yml            project adapter (never edit without asking)
.aisdlc/active                 id of the in-flight workflow
.aisdlc/work/<id>/state.json   phase, tier, gates
.aisdlc/work/<id>/*.md         artifacts (see sdlc-artifacts skill)
.aisdlc/work/<id>/changes.jsonl  append-only file-mutation ledger
```

Read and write state only through the CLI:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sdlc.py" status
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sdlc.py" phase implement
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sdlc.py" tier full
```

## Phases

| Phase | You run | Produces | Then |
|---|---|---|---|
| `intake` | — (you, directly) | `request.md` | pick tier → `plan` (or `analysis` in fix mode) |
| `analysis` | `sdlc-error-analyst` | `analysis.md` | → `plan` |
| `plan` | `sdlc-planner`, then `sdlc-plan-validator` | `plan.md`, `validation.md` | **GATE: plan** |
| `implement` | `sdlc-implementor` | code, `changes.md` | → `validate` |
| `validate` | `sdlc-test-runner`, `sdlc-reviewer` (+ `sdlc-regression-guard` in fix mode) | `tests.md`, `review.md` | **GATE: implementation** |
| `package` | `sdlc-release-packager` | `pr.md` | **GATE: release** → agent pushes and opens the PR |
| `closed` | — | — | team reviews and merges |

Advance the phase with the CLI as each one completes. Never skip a phase, and
never enter `implement` while the plan gate is pending — the plan gate hook will
block your edits anyway, and hitting it is a workflow error, not a surprise.

## Tiers

Load `sdlc-risk-tiering` to score a change. Summary:

- **express** — one file, no interface/schema/dependency change. Release gate only.
- **standard** — the default. Plan + implementation + release gates.
- **full** — forced when the change touches `profile.high_risk_paths`, alters a
  schema or public interface, or targets anything other than `branch.base`.
  Adds an explicit branch/sync confirmation and runs implementation in a git
  worktree so a half-finished change never sits on the engineer's checkout.

Propose a tier with reasoning. The engineer may override. Escalation is
automatic and not negotiable; de-escalation needs the engineer to say so.

## Gates

| Gate | Signed by | Enforced by |
|---|---|---|
| plan | `/sdlc:approve plan` | `plan_gate.py` blocks Edit/Write |
| implementation | `/sdlc:approve implementation` | convention + release gate ordering |
| release | `/sdlc:approve-push` | `release_gate.py` blocks commit/push/PR |

The release signature binds to branch + HEAD + target. **Any new commit voids
it.** So commit everything first, then ask for the release approval, then push.
If you commit again afterwards, the engineer must re-approve — say so plainly
rather than retrying the push.

Blocked outright, no signature ever unlocks: merging a PR, force-pushing,
pushing to a protected branch, and the project's `deny_patterns` (deploy and
infra commands). If one of these is genuinely needed, tell the engineer to run
it themselves with `! <command>`.

## Running subagents

Each subagent reads its inputs from `.aisdlc/work/<id>/` and writes its output
back there. Pass the **work directory path and the artifact filenames** in the
prompt — not the content. Two reasons: subagent context stays small, and the
artifact on disk stays the single source of truth.

After a subagent returns, read its artifact before deciding the next move.
Report a one-paragraph summary to the engineer at each phase boundary; they are
approving on the strength of what you tell them, so lead with what would change
their mind, not with what went well.

## Detail

`references/state-machine.md` — full transition table, state.json schema, and
recovery from an interrupted or corrupt workflow.
