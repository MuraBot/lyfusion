"""SessionStart injects the short aq usage guide; it never blocks the host."""
from __future__ import annotations

import json
import sys

from . import config as config_mod
from . import views
from .commands import Ctx, cmd_lead_session
from .util import FormatTooNew, FusionError


def run(event: str, data: dict) -> str | None:
    if event not in ("session-start", "SessionStart"):
        return None
    try:
        root = config_mod.project_root(data.get("cwd") or None)
    except FusionError:
        return None
    if not config_mod.is_fusion_project(root):
        return None
    try:
        cfg = config_mod.load(root)
    except FormatTooNew as exc:
        return f"Fusion state format is too new: {exc.path} (version {exc.version}).\nUpgrade lyfusion-plugin before using this project."
    if not cfg["local"].get("enabled"):
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
    except FormatTooNew as exc:
        text = f"Fusion state format is too new: {exc.path} (version {exc.version}).\nUpgrade lyfusion-plugin before using this project."
    except Exception:  # noqa: BLE001 - host hooks must fail closed without surfacing plugin errors.
        return 0
    if text:
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
        sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0
