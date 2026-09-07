---
name: sdlc-artifacts
description: This skill should be used when writing or reading ai-sdlc workflow artifacts — request.md, analysis.md, plan.md, validation.md, changes.md, tests.md, review.md, regression.md or pr.md — inside a .aisdlc/work/<id>/ directory. Defines the required section structure for each artifact so subagents can hand off to each other reliably.
version: 0.1.0
---

# ai-sdlc artifacts

Artifacts are the handoff bus. Subagents share no conversation context, so
everything one agent needs from another must be **on disk** in a known shape.

Rules for every artifact:

- Write the whole file; do not append to someone else's artifact.
- Re-running an agent overwrites its own artifact — they are idempotent.
- Lead with the conclusion. The engineer reads these to decide a gate, and they
  are deciding on the first paragraph.
- State uncertainty explicitly. "I could not verify X" is useful; a confident
  guess is a liability at an approval gate.
- No project-specific assumptions beyond what `profile.yml` declares.

## Shapes

**`request.md`** — intake, written by the orchestrator.
`## Request` (verbatim from the engineer) · `## Ref` · `## Scope` (in / out) ·
`## Proposed tier` with reasoning · `## Open questions`

**`analysis.md`** — fix mode, `sdlc-error-analyst`.
`## Root cause` (one sentence first) · `## Failure path` (call chain with
`file:line`) · `## Evidence` (what proves it — logs, tests, code) ·
`## Confidence` high/medium/low + what would raise it · `## Impact`

**`plan.md`** — `sdlc-planner` or `sdlc-fix-planner`.
`## Summary` · `## Files to change` (path → what → why) · `## Impact` (only the
domains in `profile.impact_domains`) · `## Reuse` (existing helpers/shared
packages found, with paths — say so explicitly if none) · `## Tests` ·
`## Risks` · `## Rollback` · `## Out of scope`

**`validation.md`** — `sdlc-plan-validator`.
`## Verdict` — `GO` | `GO-WITH-CHANGES` | `NO-GO`, first line, no preamble ·
`## Findings` severity-ranked (`blocker` / `major` / `minor`), each with the
plan claim, why it is wrong, and the fix · `## Verified` what was checked
against the codebase and held up

**`changes.md`** — `sdlc-implementor`.
`## Summary` · `## Changes` (path → what changed → why) · `## Deviations from
plan` (with reasoning — this is the section reviewers read first) ·
`## Not done` · `## Verification run` (commands and results)

**`tests.md`** — `sdlc-test-runner`.
`## Result` PASS/FAIL first line · `## Commands` (exact, from
`profile.commands`) · `## Output` (failures in full; passes summarised) ·
`## Coverage gaps`

**`review.md`** — `sdlc-reviewer`.
`## Verdict` — `APPROVE` | `APPROVE-WITH-COMMENTS` | `REQUEST-CHANGES` ·
`## Findings` severity-ranked, each `file:line` + concrete failure scenario ·
`## Checked` correctness, security, performance, architecture fit, test
coverage — say which of these you could not assess and why

**`regression.md`** — fix mode, `sdlc-regression-guard`.
`## Original issue` resolved yes/no + how verified · `## Side effects` ·
`## Preserved behaviour` what was checked still works

**`pr.md`** — `sdlc-release-packager`. Body must be paste-ready.
`## Branch` source → target · `## Commit message` (conventional commits, in a
fenced block) · `## PR title` · `## PR body` (summary, changes, test evidence,
risk, rollback) · `## Risk assessment` · `## Reviewer notes` (what to look at
hardest)

**`changes.jsonl`** — written by the `PostToolUse` hook, not by an agent.
One `{ts, tool, file, agent}` per mutation. The reviewer reads this to catch
files changed but undocumented in `changes.md`.

## Severity vocabulary

Use consistently across `validation.md` and `review.md`:

- **blocker** — ships a defect, a vulnerability, or data loss. Gate must not pass.
- **major** — real problem that will need a follow-up fix. Engineer decides.
- **minor** — style, naming, small clarity. Never block on these.

Rank most severe first and never pad the list — a review that lists six minors
to look thorough makes the blocker harder to see.
