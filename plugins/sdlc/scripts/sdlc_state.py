"""Shared state/profile library for the ai-sdlc plugin.

Imported by every hook and helper script. Two hard rules:

1. No third-party imports. Hooks run in whatever interpreter the user has;
   pyyaml is not guaranteed (it is absent on the reference machine), so a
   minimal YAML-subset parser is bundled below.
2. Nothing here may raise into a hook. Callers wrap in try/except and fail
   open, but these functions also return safe defaults rather than throwing.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

WORK_ROOT = ".aisdlc"
PROFILE_NAME = "profile.yml"
ACTIVE_POINTER = "active"

PHASES = ["intake", "analysis", "plan", "implement", "validate", "package", "closed"]
TIERS = ["express", "standard", "full"]
GATES = ["plan", "implementation", "release"]


# --------------------------------------------------------------------------
# Minimal YAML subset parser
# --------------------------------------------------------------------------
# Supports exactly what templates/profile.yml uses: nested maps by indentation,
# block lists, inline [a, b] lists, inline {k: v} maps, quoted/bare scalars,
# booleans, ints, null, and # comments. Anything richer is not valid in a
# profile -- validate_profile.py enforces that so we never write a file this
# parser cannot read back.


def _strip_comment(line):
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _split_top(text, sep=","):
    """Split on `sep` at bracket depth 0, respecting quotes."""
    parts, buf, depth, quote = [], [], 0, None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0",
            '"': '"', "\\": "\\", "/": "/"}


def _scalar(text):
    text = text.strip()
    if not text:
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        body = text[1:-1]
        # Only double quotes process escapes, matching YAML. Done by
        # substitution rather than `unicode_escape`, which round-trips through
        # latin-1 and would turn a UTF-8 branch or brand name into mojibake.
        if text[0] != '"':
            return body
        return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(0)), body)
    low = text.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", ""):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _flow(text):
    """Parse an inline [..] list or {..} map."""
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return [_flow(p) for p in _split_top(text[1:-1])]
    if text.startswith("{") and text.endswith("}"):
        out = {}
        for pair in _split_top(text[1:-1]):
            if ":" not in pair:
                continue
            k, v = pair.split(":", 1)
            out[_scalar(k)] = _flow(v)
        return out
    return _scalar(text)


def _lines(text):
    rows = []
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if line.strip():
            rows.append((len(line) - len(line.lstrip(" ")), line.strip()))
    return rows


def _block(rows, i, indent):
    """Parse one indentation block. Returns (value, next_index)."""
    if i >= len(rows):
        return None, i
    if rows[i][1].startswith("- "):
        items = []
        while i < len(rows) and rows[i][0] >= indent and rows[i][1].startswith("- "):
            body = rows[i][1][2:].strip()
            i += 1
            if body:
                items.append(_flow(body))
            else:  # nested structure under the dash
                val, i = _block(rows, i, indent + 1)
                items.append(val)
        return items, i

    mapping = {}
    while i < len(rows) and rows[i][0] >= indent:
        cur_indent, line = rows[i]
        if cur_indent > indent or ":" not in line:
            i += 1
            continue
        key, rest = line.split(":", 1)
        key, rest = key.strip(), rest.strip()
        i += 1
        if rest:
            mapping[key] = _flow(rest)
        elif i < len(rows) and rows[i][0] > cur_indent:
            mapping[key], i = _block(rows, i, rows[i][0])
        else:
            mapping[key] = None
    return mapping, i


def parse_yaml(text):
    rows = _lines(text)
    value, _ = _block(rows, 0, rows[0][0] if rows else 0)
    return value if isinstance(value, (dict, list)) else {}


# --------------------------------------------------------------------------
# Repo / profile discovery
# --------------------------------------------------------------------------


def repo_root(start=None):
    """Nearest ancestor containing .git or .aisdlc. None if neither exists."""
    path = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(path, ".git")) or os.path.isdir(
            os.path.join(path, WORK_ROOT)
        ):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent


def is_inside(path, directory):
    """True when `path` is `directory` or sits beneath it.

    A bare `startswith` would treat `/repo/.aisdlcx` as inside `/repo/.aisdlc`,
    which is enough to slip an edit past the plan gate by naming a directory
    carefully.
    """
    if not path or not directory:
        return False
    path = os.path.abspath(path)
    directory = os.path.abspath(directory)
    return path == directory or path.startswith(directory + os.sep)


def profile_path(root=None):
    root = root or repo_root()
    return os.path.join(root, WORK_ROOT, PROFILE_NAME) if root else None


def load_profile(root=None):
    """Parsed profile dict, or None when this repo is not SDLC-enabled.

    None is the signal that every gate stands down -- a repo without a
    profile is outside the framework entirely.
    """
    path = profile_path(root)
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            parsed = parse_yaml(fh.read())
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def profile_get(profile, dotted, default=None):
    node = profile or {}
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node if node is not None else default


# --------------------------------------------------------------------------
# Workflow state
# --------------------------------------------------------------------------


def work_root(root=None):
    root = root or repo_root()
    return os.path.join(root, WORK_ROOT, "work") if root else None


def active_id(root=None):
    root = root or repo_root()
    if not root:
        return None
    pointer = os.path.join(root, WORK_ROOT, ACTIVE_POINTER)
    if not os.path.isfile(pointer):
        return None
    try:
        with open(pointer, "r", encoding="utf-8") as fh:
            return fh.read().strip() or None
    except Exception:
        return None


def work_dir(work_id=None, root=None):
    root = root or repo_root()
    work_id = work_id or active_id(root)
    if not root or not work_id:
        return None
    return os.path.join(root, WORK_ROOT, "work", work_id)


def state_path(work_id=None, root=None):
    directory = work_dir(work_id, root)
    return os.path.join(directory, "state.json") if directory else None


def load_state(work_id=None, root=None):
    path = state_path(work_id, root)
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        # Corrupt state must not brick the session; callers fail open.
        return None


def save_state(state, work_id=None, root=None):
    path = state_path(work_id or state.get("id"), root)
    if not path:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)  # atomic: a killed hook never leaves half a state file
    return True


def new_state(work_id, mode, tier, branch, target, ref=None):
    required = {
        "express": {"plan": False, "implementation": False, "release": True},
        "standard": {"plan": True, "implementation": True, "release": True},
        "full": {"plan": True, "implementation": True, "release": True},
    }[tier]
    return {
        "id": work_id,
        "ref": ref,
        "mode": mode,
        "tier": tier,
        "phase": "intake",
        "branch": branch,
        "target": target,
        "created_at": now(),
        "gates": {
            name: {
                "required": required[name],
                "approved": False,
                "by": None,
                "at": None,
                **({"branch": None, "head_sha": None, "target": None} if name == "release" else {}),
            }
            for name in GATES
        },
        "artifacts": {},
    }


def set_active(work_id, root=None):
    root = root or repo_root()
    if not root:
        return False
    os.makedirs(os.path.join(root, WORK_ROOT), exist_ok=True)
    with open(os.path.join(root, WORK_ROOT, ACTIVE_POINTER), "w", encoding="utf-8") as fh:
        fh.write(work_id + "\n")
    return True


def clear_active(root=None):
    root = root or repo_root()
    pointer = os.path.join(root, WORK_ROOT, ACTIVE_POINTER) if root else None
    if pointer and os.path.isfile(pointer):
        os.remove(pointer)


# --------------------------------------------------------------------------
# Git helpers
# --------------------------------------------------------------------------


def git(*args, root=None):
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=root or repo_root() or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def current_branch(root=None):
    return git("rev-parse", "--abbrev-ref", "HEAD", root=root)


def head_sha(root=None):
    return git("rev-parse", "HEAD", root=root)


# --------------------------------------------------------------------------
# Gate signing / verification
# --------------------------------------------------------------------------


def sign_gate(state, gate, by="engineer", **extra):
    entry = state.setdefault("gates", {}).setdefault(gate, {})
    entry.update({"approved": True, "by": by, "at": now()})
    entry.update(extra)
    return state


def release_signature_error(state, branch, target=None, root=None):
    """Why the current release signature does not authorise this push.

    Returns None when the signature is valid. All four bindings must match:
    a bare boolean would let one approval authorise every later push.
    """
    if not state:
        return "no active SDLC workflow -- run /sdlc:approve-push to sign this push"
    gate = (state.get("gates") or {}).get("release") or {}
    if not gate.get("approved"):
        return "release gate is not signed"
    if gate.get("branch") != branch:
        return "approval was signed for branch '%s', not '%s'" % (gate.get("branch"), branch)
    current = head_sha(root)
    if current and gate.get("head_sha") != current:
        return (
            "approval was signed at commit %s but HEAD is now %s -- new commits "
            "invalidate the signature" % ((gate.get("head_sha") or "?")[:8], current[:8])
        )
    if target and gate.get("target") and gate.get("target") != target:
        return "approval targets '%s', not '%s'" % (gate.get("target"), target)
    return None


# --------------------------------------------------------------------------
# Hook I/O
# --------------------------------------------------------------------------


def read_hook_input():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def emit(payload=None):
    """Print hook JSON and exit 0. Never exit 2: a JSON deny carries a
    readable reason, while a bare exit 2 surfaces only stderr."""
    if payload:
        sys.stdout.write(json.dumps(payload))
    sys.exit(0)


def deny(reason):
    emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


def allow():
    emit(None)


def context(text, event="SessionStart"):
    emit({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(text, limit=48):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (slug[:limit].rstrip("-")) or "work"
