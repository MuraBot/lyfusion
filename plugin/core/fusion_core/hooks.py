"""SessionStart injects the short aq usage guide; it never blocks the host."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import config as config_mod, views
from .commands import Ctx, cmd_lead_session


def run(event: str, data: dict) -> str | None:
    if event not in ("session-start", "SessionStart"):
        return None
    try:
        root = config_mod.project_root(data.get("cwd") or None)
    except Exception:
        return None
    if not config_mod.is_fusion_project(root) or not config_mod.load(root)["local"].get("enabled"):
        return None
    ctx = Ctx(root)
    try:
        cmd_lead_session(ctx, data.get("session_id"), data.get("source"))
        return views.session_context(root, ctx.cfg, ctx.state(), data.get("source"))
    finally:
        ctx.close()


def main(event: str) -> int:
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}
    try:
        text = run(event, data)
    except Exception:
        return 0
    if text:
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
        sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0
