# AI-SDLC for Claude Code

A reusable, project-agnostic software delivery lifecycle: planning,
implementation, review and release packaging, behind human approval gates that
are **enforced by hooks rather than by prompting**.

> AI assists. Humans approve.

## Why this exists

Written as prose in an agent prompt, "never push without approval" is a request
the model can drift from. Here it is a `PreToolUse` hook: `git push` never runs
without a signature bound to the branch, the commit and the PR target. The
governance is mechanical.

The framework itself names no repository, service, branch, environment or issue
tracker. Every project specific lives in one per-repo file, `.aisdlc/profile.yml`,
which is what makes it reusable across stacks.

## Install

```bash
/plugin marketplace add ~/Projects/self/claude-ai-sdlc
/plugin install sdlc
```

Then, in any repository:

```
/sdlc:init          # detect the stack, generate .aisdlc/profile.yml
/sdlc:feature MYM-123 add lifecycle logging
```

## Commands

| Command | Purpose |
|---|---|
| `/sdlc:init` | Generate or validate this repo's profile |
| `/sdlc:feature` | Start a governed feature workflow |
| `/sdlc:status` | Phase, tier, gates, artifacts, next action |
| `/sdlc:approve` | Sign the plan or implementation gate |
| `/sdlc:approve-push` | Sign the release gate (commit, push, PR) |
| `/sdlc:abort` | Close the workflow; code is left untouched |

## The gates

| Gate | Enforced by | Unlocks |
|---|---|---|
| plan | `plan_gate.py` blocks Edit/Write | source editing |
| implementation | ordering in the CLI | the release gate |
| release | `release_gate.py` blocks Bash | `git commit`, `git push`, `gh pr create` |

The release signature binds to **branch + HEAD + target**. Any new commit voids
it. A boolean would let one approval authorise every later push.

**Never unlocked, by any signature:** `gh pr merge`, force-push, pushing to a
protected branch, and the project's declared deploy commands. If one is genuinely
needed, the engineer runs it themselves.

**Not a security boundary.** The gate reads the literal command string, so
command substitution could route around it. It exists to stop drift and
accident, which is the actual risk.

## Tiers

Ceremony is proportional to blast radius — four approvals on a one-line change is
how a framework gets abandoned.

| | express | standard | full |
|---|---|---|---|
| plan + implementation gates | no | yes | yes |
| **release gate** | **yes** | **yes** | **yes** |
| worktree isolation | no | no | yes |

Full is *forced* by `high_risk_paths`, schema/interface changes, or a non-base
target. Escalation is automatic; de-escalation needs the engineer.

## Layout

```
plugins/sdlc/
  commands/    6 entrypoints
  agents/      planner, implementor, reviewer, release-packager
  skills/      workflow spine, profile, artifacts, risk tiering
  hooks/       release gate, plan gate, change ledger, checkpoint, session start
  scripts/     sdlc_state.py (shared contract) + sdlc.py (state CLI)
  templates/   profile.yml
```

State lives on disk under `.aisdlc/`, never in conversation — which is what lets
a workflow survive `/clear` and resume in a new session tomorrow.

```
.aisdlc/profile.yml            committed: the project adapter
.aisdlc/work/<id>/state.json   gitignored: phase, tier, gate signatures
.aisdlc/work/<id>/*.md         artifacts: the handoff bus between agents
.aisdlc/work/<id>/changes.jsonl  hook-written ledger of every file mutation
```

Subagents share no conversation context, so artifacts on disk are how one hands
off to the next — and they are what the engineer reads when deciding a gate.

## Notes

- No third-party Python. Hooks run on stdlib only; a YAML-subset parser is
  bundled because `pyyaml` is not guaranteed to exist.
- Every hook fails open on internal error. A crashing hook must never brick a
  session — the release gate still blocks, because it cannot find a valid
  signature, which is the safe direction.
