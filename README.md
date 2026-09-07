# ai-sdlc

[![ci](https://github.com/lehen20/claude-ai-sdlc/actions/workflows/ci.yml/badge.svg)](https://github.com/lehen20/claude-ai-sdlc/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-6b4fbb)](https://claude.com/claude-code)

A Claude Code plugin that puts an AI coding agent inside a real delivery
lifecycle — plan, implement, review, release — behind human approval gates that
are **enforced by hooks rather than by prompting**.

> AI assists. Humans approve.

## Why

Written as prose in an agent prompt, "never push without approval" is a request,
and a request is something a model can drift from — usually around turn fifty,
when the task feels finished and the instruction is far away.

Here it is a `PreToolUse` hook. `git push` does not run without a signature
bound to the branch, the commit, and the PR target. The model does not get a
vote on whether the hook runs, so the governance is mechanical rather than
aspirational.

The framework itself names no repository, service, branch, environment or issue
tracker. Every project-specific fact lives in one per-repo file,
`.aisdlc/profile.yml`, which is what makes it reusable across stacks.

**Read [SECURITY.md](SECURITY.md) before relying on this.** It is a guardrail
against drift and accident, not a sandbox, and the limits are documented
honestly there.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- Python 3.9+ (standard library only — nothing to install)
- `git`; `gh` if you want PRs opened for you

## Install

```
/plugin marketplace add lehen20/claude-ai-sdlc
/plugin install sdlc
```

Then, in any repository:

```
/sdlc:init                       # detect the stack, generate .aisdlc/profile.yml
/sdlc:feature add lifecycle logging
```

`/sdlc:init` writes the profile, gitignores the runtime state, and turns the
release gate on for that repo. Repositories without a profile are untouched —
the plugin stands down completely.

To develop against a local checkout instead:

```
/plugin marketplace add /absolute/path/to/claude-ai-sdlc
```

## Commands

| Command | Purpose |
|---|---|
| `/sdlc:init` | Generate or validate this repo's profile |
| `/sdlc:feature` | Start a governed feature workflow |
| `/sdlc:fix` | Start a governed defect-fix workflow |
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

**Never unlocked, by any signature:** merging a PR, force-pushing, pushing to a
protected branch, `--all`/`--mirror` pushes, publishing a release, triggering a
workflow, writing through `gh api`, and the project's declared deploy commands.
If one is genuinely needed, the engineer runs it themselves.

Everything else — reading, building, testing, linting — is untouched. The gate
is a narrow classifier, not a permission prompt on your whole terminal.

## Tiers

Ceremony is proportional to blast radius. Four approvals on a one-line change is
how a framework gets abandoned.

| | express | standard | full |
|---|---|---|---|
| plan + implementation gates | no | yes | yes |
| **release gate** | **yes** | **yes** | **yes** |
| worktree isolation | no | no | yes |

Full is *forced* by `high_risk_paths`, schema or interface changes, or a
non-base target. Escalation is automatic; de-escalation needs the engineer.

## Configuration

One file, committed to the repo, is the entire project adapter:

```yaml
branch:
  base: main
  protected: [ main ]              # never pushed to directly, never force-pushed
  prefixes: { feature: feat, fix: fix }

commands:
  test: "npm test"
  lint: "npm run lint"

high_risk_paths:                   # touching these forces the Full tier
  - "**/auth/**"
  - "**/migrations/**"

deny_patterns:                     # never run, signature or not
  - "^kubectl\\s+apply"
  - "^terraform\\s+apply"
```

See [`plugins/sdlc/templates/profile.yml`](plugins/sdlc/templates/profile.yml)
for the annotated full version. `/sdlc:init` generates it by inspecting the
repo, then asks you to confirm before writing — `branch.protected` and
`deny_patterns` decide what gets blocked outright, so they are your call.

## Layout

```
plugins/sdlc/
  commands/    7 entrypoints
  agents/      planner, implementor, reviewer, release-packager
  skills/      workflow spine, profile, artifacts, risk tiering
  hooks/       release gate, plan gate, change ledger, checkpoint, session start
  scripts/     sdlc_state.py (shared contract) + sdlc.py (state CLI)
  templates/   profile.yml
tests/         stdlib unittest; run with `python3 -m unittest discover -s tests`
```

State lives on disk under `.aisdlc/`, never in conversation — which is what lets
a workflow survive `/clear` and resume in a new session tomorrow.

```
.aisdlc/profile.yml              committed: the project adapter
.aisdlc/work/<id>/state.json     gitignored: phase, tier, gate signatures
.aisdlc/work/<id>/*.md           artifacts: the handoff bus between agents
.aisdlc/work/<id>/changes.jsonl  hook-written ledger of every file mutation
```

Subagents share no conversation context, so artifacts on disk are how one hands
off to the next — and they are what the engineer reads when deciding a gate. The
reviewer cross-checks the agent's own account of its work against
`changes.jsonl`, which is appended by a `PostToolUse` hook rather than narrated
by the agent, so an unmentioned edit still shows up.

## Design notes

- **No third-party Python.** Hooks run on the stdlib only; a YAML-subset parser
  is bundled because `pyyaml` is not guaranteed to exist.
- **Every hook fails open on internal error.** A crashing hook must never brick
  a session. The release gate stays safe under that rule, because a failure
  means it cannot find a valid signature — which denies.
- **Gates are never self-certifying.** Approvals are written by `sdlc.py`, run
  by a human through a slash command. If the model could write one into
  `state.json`, the gate would be worth nothing.

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the design
rules and the testing bar. Gate changes need tests.

## License

[MIT](LICENSE) © Lehen Zehra
