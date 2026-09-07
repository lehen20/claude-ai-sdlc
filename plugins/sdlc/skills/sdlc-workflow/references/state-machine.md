# State machine reference

## state.json

```json
{
  "id": "abc-123",
  "ref": "ABC-123",
  "title": "Example change",
  "mode": "feature | fix | adhoc",
  "tier": "express | standard | full",
  "phase": "intake | analysis | plan | implement | validate | package | closed",
  "branch": "feat/example",
  "target": "release-target",
  "created_at": "2026-09-03T12:00:00+00:00",
  "gates": {
    "plan":           { "required": true, "approved": false, "by": null, "at": null },
    "implementation": { "required": true, "approved": false, "by": null, "at": null },
    "release":        { "required": true, "approved": false, "by": null, "at": null,
                        "branch": null, "head_sha": null, "target": null }
  },
  "artifacts": { "plan": "plan.md", "review": "review.md" }
}
```

`gates.release` carries three extra bindings. All must match at push time or the
gate blocks:

| Binding | Checked against | Why |
|---|---|---|
| `branch` | branch being pushed | an approval for `feat/a` must not authorise `feat/b` |
| `head_sha` | current `HEAD` | new commits were never reviewed under this approval |
| `target` | PR target branch | approving a PR into one branch is not approving one into another |

A boolean-only gate would let a single approval authorise every subsequent push.
That is the whole point of the binding.

## Transitions

```
                    ┌── fix mode ──> analysis ──┐
intake ─── feature ─┴───────────────────────────┴──> plan
                                                      │
                                            [GATE plan │ standard+full]
                                                      ▼
                                                  implement
                                                      │
                                                      ▼
                                                   validate
                                                      │
                                  [GATE implementation │ standard+full]
                                                      ▼
                                                   package
                                                      │
                                            [GATE release │ ALL tiers]
                                                      ▼
                                        push + PR ──> closed
```

Legal transitions only ever move forward, except:

- any phase → `closed` via `/sdlc:abort`
- `validate` → `implement` when review findings need fixing (re-signing the
  implementation gate is then required)
- `package` → `implement` when the engineer requests changes after seeing `pr.md`

## Tier → required gates

| Tier | plan | implementation | release | worktree |
|---|---|---|---|---|
| express | no | no | **yes** | no |
| standard | yes | yes | **yes** | no |
| full | yes | yes | **yes** | yes |

Changing tier mid-workflow with `sdlc.py tier <value>` recomputes which gates are
required. Escalating to `full` after the plan gate was signed does **not**
re-open it — the plan was still approved. Escalation adds the worktree and the
branch/sync confirmation only.

## Recovery

**Interrupted mid-phase.** `state.json` holds the last committed phase. Re-read
the artifacts present in the work directory to see how far the phase actually
got, then either resume it or re-run the phase's subagent. Subagents are written
to be idempotent — re-running one overwrites its artifact rather than appending.

**Corrupt `state.json`.** Every hook fails open on a parse error, so the session
stays usable, but the release gate will keep blocking because it cannot find a
valid signature. That is the safe direction. Recover by reading the artifacts,
then `/sdlc:abort` and starting a fresh workflow on the same branch — the code
changes are untouched by any of this.

**Signature expired mid-session.** The `Stop` hook revokes a release signature
once `HEAD` moves and says so. Ask for `/sdlc:approve-push` again; do not retry
the push first.

**Ad-hoc pushes.** `/sdlc:approve-push` with no workflow in flight mints a
minimal `adhoc` express record so the push is still signed and auditable. This
is the gate being satisfied, not bypassed — the record names who approved what
commit, exactly like a full workflow.
