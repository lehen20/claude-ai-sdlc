---
name: sdlc-profile
description: This skill should be used when creating, reading, validating or repairing an ai-sdlc project profile — when the user runs /sdlc:init, when .aisdlc/profile.yml is missing or malformed, when a gate blocks because of a profile setting like branch.protected or deny_patterns, or when adapting the ai-sdlc framework to a new repository or stack.
version: 0.1.0
---

# ai-sdlc project profile

`.aisdlc/profile.yml` is the **only** place project specifics live. The plugin
never names a repo, service, branch, environment or tracker — it reads them
here. That separation is what makes the framework reusable, so keep it: if an
agent or command would need a project-specific fact, add a profile field rather
than hardcoding it.

## Validating

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sdlc.py" init-check
```

Returns `{"ok": true|false, "problems": [...], "profile": {...}}`. Run it after
every edit. `ok: false` means the gates may misbehave — fix before continuing.

## Parser constraints

The profile is read by a bundled YAML-subset parser, because `pyyaml` is not
guaranteed to exist in the interpreter that runs hooks. Supported:

- nested maps by indentation
- block lists (`- item`)
- inline lists `[a, b]` and inline maps `{k: v}`
- quoted and bare scalars, booleans, integers, `null`
- `#` comments

**Not** supported: multi-line strings (`|`, `>`), anchors/aliases, multiple
documents, complex keys. Keep every value on one line.

Regex values must be double-quoted with escaped backslashes: `"^kubectl\\s+apply"`.

## Fields

| Field | Required | Used by |
|---|---|---|
| `branch.base` | yes | default PR target, sync source |
| `branch.protected` | yes | release gate hard-deny |
| `branch.prefixes` | no | branch naming at intake |
| `environments` | no | ordered promotion chain, shown to the engineer |
| `ticket` | **no** | intake; omit the block entirely for ticketless work |
| `impact_domains` | no | planner only asks about domains declared here |
| `shared_packages` | no | planner reuse check |
| `commands` | recommended | test runner and reviewer |
| `high_risk_paths` | no | forces Full tier |
| `deny_patterns` | recommended | release gate hard-deny (deploy/infra) |
| `severity_levels` | no | fix mode intake |

## Writing one for a new repo

Detect rather than ask, then confirm what you detected:

1. **Branches** — `git branch -r`, `git symbolic-ref refs/remotes/origin/HEAD`.
   Infer `base`; ask which branches are protected rather than guessing.
2. **Commands** — read `package.json` scripts, `Makefile`, `pyproject.toml`,
   `go.mod`, `Cargo.toml`, `build.gradle`. Populate only commands that exist;
   a wrong test command is worse than an absent one.
3. **Impact domains** — infer from the tree: an `api/`/`routes/` dir → `api`,
   `migrations/`/`schema.sql` → `database`, a broker client → `messaging`.
4. **High-risk paths** — auth, migrations, payments, infra, anything holding
   secrets. Err towards including a path; the cost is one extra gate.
5. **Deny patterns** — deploy tooling actually present in the repo (`kubectl`,
   `helm`, `terraform`, `serverless`, `flyctl`, a `deploy.sh`).

Start from `${CLAUDE_PLUGIN_ROOT}/templates/profile.yml`. Show the engineer the
generated profile and get confirmation before writing — `branch.protected` and
`deny_patterns` decide what gets blocked, and they own that decision.

Also ensure `.aisdlc/work/` is gitignored while `.aisdlc/profile.yml` is
committed: the profile is shared configuration, the work directory is local
scratch and audit trail.
