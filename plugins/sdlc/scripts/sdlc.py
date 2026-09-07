#!/usr/bin/env python3
"""ai-sdlc state CLI. Slash commands drive this rather than editing state.json.

Gate signing must be deterministic. If the model hand-wrote approvals into
state.json the gate would be self-certifying and worth nothing.

  sdlc.py init-check
  sdlc.py start   --mode feature|fix --ref ABC-123 --tier standard --branch feat/x [--target <branch>] [--title "..."]
  sdlc.py status  [--json]
  sdlc.py phase   <intake|analysis|plan|implement|validate|package|closed>
  sdlc.py approve <plan|implementation> [--by NAME]
  sdlc.py approve-push [--target BRANCH] [--by NAME]
  sdlc.py tier    <express|standard|full>
  sdlc.py abort
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sdlc_state as S  # noqa: E402

ARTIFACTS = [
    "request.md", "analysis.md", "plan.md", "validation.md",
    "changes.md", "tests.md", "review.md", "regression.md", "pr.md",
]


def fail(message, code=1):
    print("error: " + message, file=sys.stderr)
    sys.exit(code)


def need_profile(root):
    if S.load_profile(root) is None:
        fail("no .aisdlc/profile.yml in this repo. Run /sdlc:init first.")


def need_state(root):
    state = S.load_state(root=root)
    if not state:
        fail("no active workflow. Start one with /sdlc:feature or /sdlc:fix.")
    return state


def cmd_init_check(args, root):
    profile = S.load_profile(root)
    if profile is None:
        print(json.dumps({"ok": False, "reason": "missing .aisdlc/profile.yml"}))
        return
    problems = []
    if not S.profile_get(profile, "branch.base"):
        problems.append("branch.base is required")
    if not S.profile_get(profile, "branch.protected"):
        problems.append("branch.protected is required (at least the base branch)")
    if not isinstance(S.profile_get(profile, "commands", {}), dict):
        problems.append("commands must be a map")
    for pattern in S.profile_get(profile, "deny_patterns", []) or []:
        try:
            __import__("re").compile(str(pattern))
        except Exception:
            problems.append("deny_patterns entry is not a valid regex: %r" % pattern)
    print(json.dumps({"ok": not problems, "problems": problems, "profile": profile}, indent=2))


def cmd_start(args, root):
    need_profile(root)
    existing = S.load_state(root=root)
    if existing and existing.get("phase") != "closed":
        fail("workflow '%s' is already in flight (phase %s). Finish it, or /sdlc:abort."
             % (existing.get("id"), existing.get("phase")))

    profile = S.load_profile(root)
    target = args.target or S.profile_get(profile, "branch.base", "main")
    work_id = S.slugify(args.ref or args.title or args.branch)
    directory = os.path.join(root, S.WORK_ROOT, "work", work_id)
    os.makedirs(directory, exist_ok=True)

    state = S.new_state(work_id, args.mode, args.tier, args.branch, target, ref=args.ref)
    state["title"] = args.title
    state["artifacts"] = {name.split(".")[0]: name for name in ARTIFACTS}
    S.save_state(state, root=root)
    S.set_active(work_id, root=root)
    print(json.dumps({"ok": True, "id": work_id, "dir": os.path.relpath(directory, root),
                      "tier": args.tier, "target": target}, indent=2))


def cmd_status(args, root):
    profile = S.load_profile(root)
    state = S.load_state(root=root)
    if args.json:
        print(json.dumps({"profile": profile, "state": state}, indent=2))
        return
    if profile is None:
        print("ai-sdlc: not enabled in this repo (no .aisdlc/profile.yml)")
        return
    print("ai-sdlc  base=%s  protected=%s" % (
        S.profile_get(profile, "branch.base"),
        ",".join(str(b) for b in S.profile_get(profile, "branch.protected", []) or [])))
    if not state or state.get("phase") == "closed":
        print("no workflow in flight")
        return
    print("workflow %s  mode=%s tier=%s phase=%s" % (
        state.get("id"), state.get("mode"), state.get("tier"), state.get("phase")))
    print("branch   %s -> %s" % (state.get("branch"), state.get("target")))
    for name, gate in (state.get("gates") or {}).items():
        if not gate.get("required"):
            print("  gate %-14s not required at this tier" % name)
        elif gate.get("approved"):
            extra = ""
            if name == "release":
                extra = "  [%s @ %s]" % (gate.get("branch"), (gate.get("head_sha") or "")[:8])
            print("  gate %-14s SIGNED by %s at %s%s" % (name, gate.get("by"), gate.get("at"), extra))
        else:
            print("  gate %-14s PENDING" % name)
    directory = S.work_dir(root=root)
    if directory and os.path.isdir(directory):
        present = sorted(f for f in os.listdir(directory) if f.endswith((".md", ".jsonl")))
        print("artifacts %s" % (", ".join(present) or "(none yet)"))


def cmd_phase(args, root):
    state = need_state(root)
    if args.value not in S.PHASES:
        fail("phase must be one of: %s" % ", ".join(S.PHASES))
    state["phase"] = args.value
    state["updated_at"] = S.now()
    S.save_state(state, root=root)
    print(json.dumps({"ok": True, "phase": args.value}))


def cmd_tier(args, root):
    state = need_state(root)
    if args.value not in S.TIERS:
        fail("tier must be one of: %s" % ", ".join(S.TIERS))
    required = {"express": {"plan": False, "implementation": False},
                "standard": {"plan": True, "implementation": True},
                "full": {"plan": True, "implementation": True}}[args.value]
    for name, is_required in required.items():
        state["gates"][name]["required"] = is_required
    state["tier"] = args.value
    state["updated_at"] = S.now()
    S.save_state(state, root=root)
    print(json.dumps({"ok": True, "tier": args.value}))


def cmd_approve(args, root):
    state = need_state(root)
    if args.gate not in ("plan", "implementation"):
        fail("use approve-push for the release gate")
    gate = state["gates"][args.gate]
    if not gate.get("required"):
        print(json.dumps({"ok": True, "note": "%s gate not required at %s tier" % (args.gate, state["tier"])}))
        return
    S.sign_gate(state, args.gate, by=args.by)
    state["updated_at"] = S.now()
    S.save_state(state, root=root)
    print(json.dumps({"ok": True, "gate": args.gate, "by": args.by, "at": state["gates"][args.gate]["at"]}))


def cmd_approve_push(args, root):
    need_profile(root)
    profile = S.load_profile(root)
    state = S.load_state(root=root)
    branch = S.current_branch(root)
    sha = S.head_sha(root)
    if not branch or not sha:
        fail("not a git repository, or no commits yet")

    protected = [str(b) for b in S.profile_get(profile, "branch.protected", []) or []]
    if branch in protected:
        fail("refusing to sign: '%s' is a protected branch. Work on a feature branch." % branch)

    target = args.target or (state or {}).get("target") or S.profile_get(profile, "branch.base", "main")

    if not state or state.get("phase") == "closed":
        # Ad-hoc push: the gate still applies, so mint a minimal express record.
        # This is the gate being signed, not a bypass -- it is auditable like any other.
        work_id = S.slugify("adhoc-" + branch)
        os.makedirs(os.path.join(root, S.WORK_ROOT, "work", work_id), exist_ok=True)
        state = S.new_state(work_id, "adhoc", "express", branch, target)
        S.set_active(work_id, root=root)

    for name in ("plan", "implementation"):
        gate = state["gates"][name]
        if gate.get("required") and not gate.get("approved"):
            fail("cannot sign the release gate: the %s gate is still pending. "
                 "Run /sdlc:approve %s first." % (name, name))

    state["branch"] = branch
    S.sign_gate(state, "release", by=args.by, branch=branch, head_sha=sha, target=target)
    state["phase"] = "package"
    state["updated_at"] = S.now()
    S.save_state(state, root=root)
    print(json.dumps({"ok": True, "branch": branch, "head_sha": sha, "target": target,
                      "by": args.by, "note": "valid until HEAD moves"}, indent=2))


def cmd_abort(args, root):
    state = need_state(root)
    state["phase"] = "closed"
    state["closed_at"] = S.now()
    for gate in state.get("gates", {}).values():
        gate["approved"] = False
    S.save_state(state, root=root)
    S.clear_active(root=root)
    print(json.dumps({"ok": True, "closed": state.get("id")}))


def main():
    parser = argparse.ArgumentParser(prog="sdlc")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-check")

    start = sub.add_parser("start")
    start.add_argument("--mode", required=True, choices=["feature", "fix"])
    start.add_argument("--tier", required=True, choices=S.TIERS)
    start.add_argument("--branch", required=True)
    start.add_argument("--ref")
    start.add_argument("--title")
    start.add_argument("--target")

    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")

    phase = sub.add_parser("phase")
    phase.add_argument("value")

    tier = sub.add_parser("tier")
    tier.add_argument("value")

    approve = sub.add_parser("approve")
    approve.add_argument("gate")
    approve.add_argument("--by", default="engineer")

    push = sub.add_parser("approve-push")
    push.add_argument("--target")
    push.add_argument("--by", default="engineer")

    sub.add_parser("abort")

    args = parser.parse_args()
    root = S.repo_root()
    if not root:
        fail("not inside a git repository")

    {
        "init-check": cmd_init_check, "start": cmd_start, "status": cmd_status,
        "phase": cmd_phase, "tier": cmd_tier, "approve": cmd_approve,
        "approve-push": cmd_approve_push, "abort": cmd_abort,
    }[args.cmd](args, root)


if __name__ == "__main__":
    main()
