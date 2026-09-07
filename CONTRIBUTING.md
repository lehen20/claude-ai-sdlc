# Contributing

Thanks for looking. This is a small, opinionated project; the fastest way to get
a change merged is to know what it optimises for.

## Design rules

These are not style preferences. A PR that breaks one will be asked to change.

1. **No project specifics in the framework.** The plugin never names a repo,
   service, branch, environment or tracker. If your change needs such a fact,
   add a field to `.aisdlc/profile.yml` and read it — do not hardcode it.
2. **No third-party Python.** Hooks run in whatever interpreter the user has.
   `pyyaml` is not guaranteed, which is why a YAML-subset parser is bundled.
   Standard library only, Python 3.9+.
3. **Hooks fail open.** Every hook wraps `main()` and allows the tool call on an
   internal error. A crashing hook must never brick someone's session. The
   release gate stays safe under this rule because a failure means it cannot
   find a valid signature, which denies.
4. **Gates are never self-certifying.** Approval is written by `sdlc.py`, run by
   a human through a slash command. If a model could write an approval into
   `state.json` directly, the gate would be worth nothing.
5. **Ceremony is proportional.** Before adding a step, ask which tier it belongs
   to. Four approvals on a one-line change is how a framework gets abandoned.

## Getting set up

```bash
git clone https://github.com/lehen20/claude-ai-sdlc
cd claude-ai-sdlc
python3 -m unittest discover -s tests -v     # no dependencies to install
```

To run your working copy inside Claude Code:

```
/plugin marketplace add /absolute/path/to/claude-ai-sdlc
/plugin install sdlc
```

Hooks are read at session start — restart the session after changing one.

## Testing

`tests/` is stdlib `unittest`, no framework. Every test must pass on 3.9+.

**Any change to `release_gate.py` needs a test.** The classifier is the part of
this project that has to be right, and every case in
`tests/test_release_gate.py` is there because it once got through. Add the
command you are handling to the relevant class, in both the blocked and the
allowed direction — a gate that denies everything is as broken as one that
denies nothing.

Please read [SECURITY.md](SECURITY.md) before proposing gate changes. Fixes that
close one shell trick without closing its class will be declined; that path ends
in an unmaintainable list.

## Manual check

Automated tests do not cover the loop that matters. For anything touching the
workflow, run it end to end in a scratch repository:

```bash
mkdir /tmp/scratch && cd /tmp/scratch && git init && git commit --allow-empty -m init
```

Then `/sdlc:init`, `/sdlc:feature`, and try to push before signing. The gate
should block with a readable reason that names the fix.

## Pull requests

- One concern per PR. A gate fix and a docs rewrite are two PRs.
- Say what you tested and how, including what you could **not** verify.
- Prose in this repo is deliberately plain: say the thing, give the reason,
  stop. Match the surrounding voice.

Bug reports are welcome as issues — include the literal command, the verdict you
expected, and the one you got. For a genuine vulnerability, use private
reporting instead: see [SECURITY.md](SECURITY.md).

By contributing you agree your work is licensed under the [MIT License](LICENSE).
