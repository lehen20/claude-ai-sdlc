---
description: Set up ai-sdlc in this repository by generating .aisdlc/profile.yml
argument-hint: "[--validate]"
---

# Initialise ai-sdlc for this repository

Arguments: $ARGUMENTS

Load the `sdlc-profile` skill and follow it.

If `$ARGUMENTS` contains `--validate`, only run the check and report:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sdlc.py" init-check
```

Otherwise generate a profile:

1. If `.aisdlc/profile.yml` already exists, show it and ask whether to update it
   rather than overwriting.
2. **Detect, don't interrogate.** Inspect the repo for branches, build/test
   commands, impact domains, high-risk paths and deploy tooling, as described in
   the `sdlc-profile` skill. Start from
   `${CLAUDE_PLUGIN_ROOT}/templates/profile.yml`.
3. Present the proposed profile and **ask the engineer to confirm** before
   writing. `branch.protected` and `deny_patterns` determine what gets blocked
   outright — that is their call, not yours. Flag anything you had to guess.
4. Write `.aisdlc/profile.yml`, add `.aisdlc/work/` to `.gitignore`, and run
   `init-check` to confirm it parses.

Then tell them what just became true: the release gate is now active in this
repo, so `git commit`, `git push` and `gh pr create` require
`/sdlc:approve-push`. Show them `/sdlc:feature` as the next step.
