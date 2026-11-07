"""The small, blocking v5.0.0-aq workflow over the existing engine."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config as config_mod
from .commands import Ctx, cmd_accept, cmd_cancel, cmd_delegate, cmd_explore, cmd_plan, cmd_request_changes
from .util import FusionError, any_match, git


def read_input(value: str | None, stdin) -> str:
    if not value:
        raise FusionError("缺少输入文件或 - (标准输入)")
    if value == "-":
        return stdin.buffer.read().decode("utf-8-sig")
    return Path(value).read_bytes().decode("utf-8-sig")


def parse_plan(text: str) -> dict:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FusionError(f"计划不是合法的 JSON:{exc}") from exc
    allowed = ("goal", "brief", "checks", "scope")
    if not isinstance(raw, dict):
        raise FusionError("计划要是 JSON 对象")
    extra = sorted(set(raw) - set(allowed))
    if extra:
        raise FusionError(f"计划只允许字段: {', '.join(allowed)};不允许: {', '.join(extra)}")
    goal = raw.get("goal")
    if not isinstance(goal, str) or not goal.strip() or "\n" in goal.strip():
        raise FusionError("goal 要是非空的一行文字")
    brief = raw.get("brief")
    if not isinstance(brief, str) or not brief.strip():
        raise FusionError("brief 要是非空字符串")
    checks, scope = raw.get("checks", []), raw.get("scope", [])
    if not isinstance(checks, list) or not isinstance(scope, list) or any(not isinstance(x, str) for x in scope):
        raise FusionError("checks 要是列表,scope 要是 glob 字符串列表")
    normalized = []
    for i, check in enumerate(checks, 1):
        if not isinstance(check, dict) or set(check) - {"run", "expect"}:
            raise FusionError(f"checks[{i - 1}] 只允许 run 和 expect")
        run, expect = check.get("run"), check.get("expect", 0)
        if not isinstance(run, str) or not run.strip():
            raise FusionError(f"checks[{i - 1}].run 要是非空字符串")
        if not isinstance(expect, (str, int)) or isinstance(expect, bool):
            raise FusionError(f"checks[{i - 1}].expect 要是整数或字符串")
        if isinstance(expect, str):
            try:
                re.compile(expect)
            except re.error as exc:
                raise FusionError(f"checks[{i - 1}].expect 正则无效:{exc}") from exc
        normalized.append({"id": f"C{i}", "kind": "command", "run": run,
                           "expect": {"exit": expect} if isinstance(expect, int) else {"regex": expect}})
    return {"goal": goal.strip(), "brief": brief, "checks": normalized, "scope": scope or ["**"]}


def engine_plan(plan: dict, cfg: dict) -> dict:
    """Adapt the four public fields to the engine's internal one-item task shape."""
    cids = [c["id"] for c in plan["checks"]]
    work_type = "mechanical" if cids else "verify"
    return {"goal": plan["goal"], "notes": plan["brief"], "checks": plan["checks"],
            "scope": plan["scope"], "bounds": {"must": [], "free": [], "escalate": []},
            "items": [{"id": "W1", "type": work_type, "title": plan["goal"],
                       "files": plan["scope"], "checks": cids}]}


def decisions_text(root: Path) -> str:
    path = root / "fusion" / "decisions.md"
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        path.write_text("# 跨任务设计决定\n\n在这里记录所有任务都要遵守的决定。\n", encoding="utf-8")
    return path.read_text(encoding="utf-8")


def save_history(root: Path, task: str, name: str, text: str) -> None:
    folder = root / "fusion" / "tasks" / task
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def review_pack(root: Path, task: dict, state: dict) -> str:
    candidate = state["candidates"].get(task.get("latest"))
    checks = candidate.get("checks") or {} if candidate else {}
    lines = ["# 检查"]
    for result in checks.get("results", []):
        lines.append(f"- {result['name']}: `{result['cmd']}` — {'通过' if result['passed'] else '未通过'} (退出码 {result['exit']})")
        if not result["passed"]:
            lines.extend("  " + x for x in result.get("tail", "").splitlines()[-20:])
    lines.append(f"- 自动修复: {task.get('fix_attempts', 0)} 次")
    lines.append("- 旧测试跑新代码: " + ("通过" if not any(v.get("kind") == "old_tests" for v in checks.get("violations", [])) else "未通过"))
    violations = checks.get("violations", [])
    if violations:
        lines += ["", "# 违规"]
        lines += [f"- {v['why']} ({v['where']})" for v in violations]
    report = state["runs"].get(task.get("active_run") or "", {}).get("report") or {}
    if not report:
        report = next((state["runs"][r].get("report") or {} for r in reversed(task["runs"])
                       if state["runs"][r].get("report")), {})
    lines += ["", "# 助手的问题和自定的选择", f"状态: {task['state']}", f"摘要: {report.get('summary') or ''}"]
    for q in report.get("questions", []):
        lines.append(f"- 问题: {q.get('text', q)}")
    for c in report.get("choices", []):
        lines.append(f"- 自定选择: {c.get('what', c)}")
    for p in report.get("problems", []):
        lines.append(f"- 已知问题: {p}")
    paths = candidate and candidate.get("checks", {}).get("changed", []) or []
    scope = task["plan"].get("scope", ["**"])
    lines += ["", "# 改动", f"文件: {', '.join(paths) or '无'}"]
    outside = [p for p in paths if not any_match(p, scope)]
    if outside:
        lines.append("范围外: " + ", ".join(outside))
    if candidate:
        stat = git("diff", "--stat", candidate["base"], candidate["commit"], cwd=root)
        diff = git("diff", candidate["base"], candidate["commit"], cwd=root)
        lines.append(stat or "diff: 无")
        if len(diff.splitlines()) <= 400:
            lines += ["", "```diff", diff.rstrip(), "```"]
    return "\n".join(lines) + "\n"


__all__ = ["read_input", "parse_plan", "engine_plan", "decisions_text", "save_history", "review_pack"]
