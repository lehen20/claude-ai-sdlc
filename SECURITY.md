# Security

## What this project is, precisely

ai-sdlc is a **governance guardrail**, not a security boundary, and the
distinction is load-bearing.

The threat it addresses is a *cooperative* agent that drifts: one that has been
told to wait for approval, means to, and pushes anyway because the instruction
was fifty turns ago and the task felt finished. Against that, a `PreToolUse`
hook is decisive — the model does not get a vote on whether the hook runs.

The threat it does **not** address is an *adversarial* agent, or an attacker who
already has code execution on the machine. If either applies, this project will
not save you, and no amount of hardening the command classifier would change
that.

## Known and accepted limits

The release gate reads the literal `command` string that the Bash tool was asked
to run. Anything that defers the real command past that string routes around it:

| Route | Example |
|---|---|
| Command substitution | `` $(echo git push origin main) `` |
| An interpreter | `bash -c 'git push origin main'` |
| A heredoc or script file | `bash deploy.sh` |
| A rebound name | `alias g=git`, a `git` earlier on `PATH` |
| Another language's process spawn | `python3 -c "import subprocess; ..."` |
| Direct filesystem writes | writing to `.git/` by hand |
| A tool that is not Bash | an MCP server with its own git integration |

These are not bugs and pull requests closing one case will be declined unless
they close the *class*. Enumerating shell tricks is a losing game; the honest
position is a documented limit rather than a false claim of containment.

**If you need containment, use containment:** run the agent under a sandbox
profile, restrict its credentials, and enforce branch protection **server-side**
on the forge. Server-side branch protection is the control that actually cannot
be argued with. This plugin is what keeps the day-to-day from drifting; it is a
complement to those controls, never a replacement.

## What is defended, and tested

Within the "literal command string" model, the gate is expected to hold, and
`tests/test_release_gate.py` is the contract. Regressions found and closed:

- multi-line Bash blocks — only the first command used to be classified
- clustered short flags — `-uf` hid a force-push from `-f`
- `--all` / `--mirror` — write every ref, protected branches included, without
  naming a branch for the refspec check to see
- `git -C <dir>` and other global options — hid the subcommand entirely
- `+`-prefixed refspecs — `+main` did not read as `main`
- `gh api -X PUT|POST|PATCH|DELETE` — reaches merge, release and settings
  endpoints the classifier cannot see; also `gh pr review --approve`,
  `gh release create`, `gh workflow run`
- path-prefix matching — `/repo/.aisdlcx/` counted as inside `/repo/.aisdlc/`
  and so skipped the plan gate

A bypass that fits the model above — a *literal* command string that reaches a
protected branch, a force-push, a merge or a deploy — is a real bug. Please
report it.

## Untrusted repositories

The hooks activate on any repository containing `.aisdlc/profile.yml`, and
`session_start.py` injects part of that file into the session context. A profile
is executable-adjacent configuration:

- `deny_patterns` are compiled as regexes
- `commands` and `brand.name` are rendered into the model's context, so a
  hostile profile is a **prompt-injection vector**
- `branch.protected` decides what is refused; an empty list protects nothing

**Treat `.aisdlc/profile.yml` as code.** Review it on `git pull` as you would a
CI config or a `Makefile`, and do not run an SDLC-enabled session in a
repository you would not run `make` in.

## Reporting a vulnerability

Please **do not** open a public issue for a genuine vulnerability.

Use GitHub's private reporting: **Security → Report a vulnerability** on
<https://github.com/lehen20/claude-ai-sdlc>. Include the literal command or
profile, the expected verdict, and the observed one.

Expect an acknowledgement within 7 days. This is an unfunded side project with
no SLA beyond a good-faith effort; there is no bounty.

## Scope

**In scope:** a literal command reaching a protected branch, force-pushing,
merging or deploying; a signature validating for the wrong branch, commit or
target; a plan-gate bypass; a crash that leaves a hook failing *closed* and
bricks a session.

**Out of scope:** everything in "Known and accepted limits"; anything requiring
existing code execution or filesystem write access; the model choosing to lie in
an artifact it authored (artifacts are cross-checked against the hook-written
`changes.jsonl` ledger, which is why that ledger exists).
