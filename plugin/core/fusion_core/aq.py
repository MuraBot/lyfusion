"""aq input parsing and task artifact formatting."""

from __future__ import annotations

import json
from pathlib import Path

from . import validate
from .util import FusionError, any_match, git


def read_input(value: str | None, stdin) -> str:
    if not value:
        raise FusionError("缺少输入文件或 - (标准输入)")
    if value == "-":
        return stdin.buffer.read().decode("utf-8-sig")
    return Path(value).read_bytes().decode("utf-8-sig")


def parse_plan(text: str) -> dict:
    try:
        return validate.plan(json.loads(text))
    except json.JSONDecodeError as exc:
        raise FusionError(f"计划不是合法的 JSON:{exc}") from exc


def decisions_text(root: Path) -> str:
    path = root / "fusion" / "decisions.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def save_history(root: Path, task: str, name: str, text: str) -> None:
    folder = root / "fusion" / "tasks" / task
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def review_pack(root: Path, task: dict, state: dict, round_no: int) -> str:
    candidate = state["candidates"].get(task.get("latest"))
    check = candidate.get("checks") or {} if candidate else {}
    lines = [
        f"# {task['id']} 审查包(第 {round_no} 轮)",
        f"目标:{(task.get('plan') or {}).get('goal', '')}",
        "",
        "## 检查",
    ]
    for result in check.get("results", []):
        status = "通过" if result["passed"] else "未通过"
        lines.append(
            f"- {result['name']}: `{result['cmd']}` {status}(退出码 {result['exit']})"
        )
        if not result["passed"]:
            lines.extend(
                f"  {line}" for line in result.get("tail", "").splitlines()[-20:]
            )
    lines.append(f"- 自动修复: {task.get('fix_attempts', 0)} 次")
    old_test = next(
        (r for r in check.get("results", []) if r["name"] == "旧测试跑新代码"), None
    )
    if old_test:
        lines.append(
            f"- 旧测试跑新代码: {'通过' if old_test['passed'] else '未通过'}(退出码 {old_test['exit']})"
        )
    else:
        lines.append("- 旧测试跑新代码: 没跑(没改原有测试)")
    violations = check.get("violations", [])
    if violations:
        lines += ["", "## 违规"]
        lines.extend(f"- {v['why']} ({v['where']})" for v in violations)
        lines.append(
            '验收要 `fusion-core accept --waive "原因"`;有禁止操作时,原因里要写用户的原话。'
        )
    report = task.get("latest_report") or {}
    blocked = task["state"] == "blocked" or report.get("status") == "blocked"
    if blocked:
        summary = report.get("summary")
        if summary:
            reason = f"停下:{summary}"
        else:
            run_id = (task.get("runs") or ["unknown"])[-1]
            reason = f"停下:助手运行没有正常结束,日志在 fusion/runs/{run_id}/"
    else:
        reason = "做完"
    lines += ["", "## 助手的问题和自定的选择"]
    if blocked:
        lines.append(f"状态:{reason}")
    else:
        lines.extend(["状态:做完", f"摘要:{report.get('summary') or ''}"])
    for question in report.get("questions", []):
        lines.append(f"- 问题:{question.get('text', '')}")
    for choice in report.get("choices", []):
        if isinstance(choice, dict):
            why = f"(理由:{choice['why']})" if choice.get("why") else ""
            lines.append(f"- 自定选择:{choice.get('what', '')}{why}")
        else:
            lines.append(f"- 自定选择:{choice}")
    for problem in report.get("problems", []):
        lines.append(f"- 已知问题:{problem}")
    next_step = next_step_text(task, check)
    scope = (task.get("plan") or {}).get("scope") or []
    lines += ["", "## 改动"]
    if candidate:
        numstat = git(
            "diff", "--numstat", candidate["base"], candidate["commit"], cwd=root
        )
        changed = []
        for line in numstat.splitlines():
            added, deleted, path = line.split("\t", 2)
            suffix = " (范围外)" if scope and not any_match(path, scope) else ""
            changed.append(f"- {path} +{added} -{deleted}{suffix}")
        lines.extend(changed)
        lines.append(f"共 {len(changed)} 个文件")
        diff = git("diff", candidate["base"], candidate["commit"], cwd=root)
        if len(diff.splitlines()) <= 400:
            lines += ["", "```diff", diff.rstrip(), "```"]
    else:
        lines.append("- 无代码候选")
    lines.append(next_step)
    return "\n".join(lines) + "\n"


def next_step_text(task: dict, check: dict) -> str:
    report = task.get("latest_report") or {}
    if task.get("state") == "blocked" or report.get("status") == "blocked":
        return "下一步: fusion-core revise -(回答助手的问题)"
    failed = any(not result.get("passed") for result in check.get("results", []))
    if failed or check.get("violations"):
        return (
            '下一步: fusion-core revise -(或确认后 fusion-core accept --waive "原因")'
        )
    return "下一步: fusion-core accept(要改就 fusion-core revise -)"
