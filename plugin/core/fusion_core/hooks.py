"""Claude Code 钩子:只注入文字和提示,不批准、不阻止任何操作。

项目没有打开 Fusion(或关着)时什么都不输出,对别的项目零影响。
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from . import config as config_mod, views
from .commands import Ctx, cmd_lead_session

EVENT_NAMES = {"session-start": "SessionStart", "prompt": "UserPromptSubmit", "pre-edit": "PreToolUse"}


def _root(data: dict) -> Path | None:
    try:
        return config_mod.project_root(data.get("cwd") or None)
    except Exception:
        return None


def run(event: str, data: dict) -> str | None:
    """返回要注入的文字;None = 不输出。"""
    root = _root(data)
    if root is None or not config_mod.is_fusion_project(root):
        return None
    cfg = config_mod.load(root)
    if not cfg["local"].get("enabled"):
        return None
    ctx = Ctx(root)
    try:
        if event == "session-start":
            cmd_lead_session(ctx, data.get("session_id"), data.get("source"))
            return views.session_context(root, cfg, ctx.state(), data.get("source"))
        if event == "prompt":
            return views.prompt_line(ctx.state())
        if event == "pre-edit":
            path = (data.get("tool_input") or {}).get("file_path")
            return views.edit_hint(ctx.state(), path, root) if path else None
    finally:
        ctx.close()
    return None


def main(event: str) -> int:
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        data = {}
    try:
        text = run(event, data)
    except Exception:
        try:
            root = _root(data)
            if root and config_mod.is_fusion_project(root):
                p = root / "fusion" / "runs" / "hook-errors.log"
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "a", encoding="utf-8") as f:
                    f.write(f"{event}\n{traceback.format_exc()}\n")
        except Exception:
            pass
        return 0  # 钩子出错不能挡住 lead
    if text:
        out = {"hookSpecificOutput": {"hookEventName": EVENT_NAMES.get(event, event), "additionalContext": text}}
        sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0
