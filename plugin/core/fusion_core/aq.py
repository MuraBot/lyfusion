"""aq input parsing and task artifact formatting."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import gitops, validate
from .util import CMD, FusionError, any_match, git


def read_input(value: str | None, stdin) -> str:
    if not value:
        raise FusionError("缺少输入文件或 - (标准输入)")
    if value == "-":
        return stdin.buffer.read().decode("utf-8-sig")
    return Path(value).read_bytes().decode("utf-8-sig")


def parse_plan(text: str) -> dict:
    if not text.lstrip("\ufeff \t\r\n").startswith("{"):
        return validate.plan(_markdown_plan(text))
    try:
        return validate.plan(json.loads(text))
    except json.JSONDecodeError as exc:
        raise FusionError(f"计划不是合法的 JSON:{exc}") from exc


def _markdown_plan(text: str) -> dict:
    """把 Markdown 计划转换成四字段计划。"""
    text = text.lstrip("\ufeff \t\r\n")
    lines = text.splitlines()
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None:
        raise FusionError('Markdown 计划第一行要是 "# 一句话目标";也可以用 JSON(第一个字符是 {)')
    goal_match = re.fullmatch(r"#\s+(.+?)\s*", lines[first])
    if not goal_match or not goal_match.group(1).strip():
        raise FusionError('Markdown 计划第一行要是 "# 一句话目标";也可以用 JSON(第一个字符是 {)')
    goal = goal_match.group(1).strip()

    reserved: dict[str, list[str]] = {}
    removed = {first}
    section: str | None = None
    fence: str | None = None
    heading = re.compile(r"^#{1,6}\s+")
    reserved_heading = re.compile(r"^## (scope|checks)\s*$", re.IGNORECASE)
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if fence:
            if section:
                removed.add(index)
            if stripped.startswith(fence):
                fence = None
            continue
        if stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
            if section:
                removed.add(index)
            continue
        if heading.match(line):
            match = reserved_heading.fullmatch(line)
            if match:
                name = match.group(1).lower()
                if name in reserved:
                    raise FusionError(f"## {name} 一节只能写一次")
                reserved[name] = []
                section = name
                removed.add(index)
                continue
            section = None
        if section:
            removed.add(index)
            if not line.strip():
                continue
            item_match = re.fullmatch(r"\s*[-*]\s+(.+?)\s*", line)
            if not item_match:
                raise FusionError(f'## {section} 一节每行写 "- 项":{line}')
            item = item_match.group(1).strip()
            if len(item) >= 2 and item.startswith("`") and item.endswith("`"):
                item = item[1:-1].strip()
            if not item:
                raise FusionError(f'## {section} 一节每行写 "- 项":{line}')
            reserved[section].append(item)

    brief_lines = [line for index, line in enumerate(lines) if index not in removed]
    while brief_lines and not brief_lines[0].strip():
        brief_lines.pop(0)
    while brief_lines and not brief_lines[-1].strip():
        brief_lines.pop()
    plan = {"goal": goal, "brief": "\n".join(brief_lines)}
    if "scope" in reserved:
        plan["scope"] = reserved["scope"]
    if "checks" in reserved:
        plan["checks"] = [{"run": command} for command in reserved["checks"]]
    return plan


def decisions_text(root: Path) -> str:
    path = root / "fusion" / "decisions.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def save_history(root: Path, task: str, name: str, text: str) -> None:
    folder = root / "fusion" / "tasks" / task
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def _is_test_path(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    name = parts[-1]
    return "tests" in parts or (name.startswith("test_") and name.endswith(".py")) or "_test." in name or ".test." in name


def review_pack(root: Path, task: dict, state: dict, round_no: int) -> str:
    latest_run = (task.get("runs") or [None])[-1]
    failed = next(
        (signal for signal in task.get("signals", [])
         if signal.get("kind") == "candidate_failed" and signal.get("run") == latest_run),
        None,
    )
    candidate = None if failed else state["candidates"].get(task.get("latest"))
    check = candidate.get("checks") or {} if candidate else {}
    lines = [
        f"# {task['id']} 审查包(第 {round_no} 轮)",
        f"目标:{(task.get('plan') or {}).get('goal', '')}",
        "",
        "## 检查",
    ]
    for result in check.get("results", []):
        if result["name"] == "旧测试跑新代码":
            continue  # 下面单独一行
        status = "通过" if result["passed"] else "未通过"
        lines.append(
            f"- {result['name']}: `{result['cmd']}` {status}(退出码 {result['exit']})"
        )
        if not result["passed"]:
            lines.extend(
                f"  {line}" for line in result.get("tail", "").splitlines()[-20:]
            )
    lines.append(f"- 自动修复: {task.get('fix_attempts', 0)} 次")
    old_test = next((r for r in check.get("results", []) if "旧测试" in r.get("name", "")), None)
    if old_test:
        lines.append(
            f"- 旧测试跑新代码: {'通过' if old_test['passed'] else '未通过'}(退出码 {old_test['exit']})"
        )
        if not old_test["passed"]:
            run = state["runs"].get(candidate.get("run"), {}) if candidate else {}
            run_dir = run.get("dir")
            log = Path(run_dir) / "checks" / "old-tests.log" if run_dir else None
            if log and log.exists():
                output = log.read_text(encoding="utf-8", errors="replace").splitlines()
                lines.extend(f"  {line}" for line in [x for x in output if "FAILED " in x][:10])
                lines.extend(f"  {line}" for line in output[-20:])
    else:
        lines.append("- 旧测试跑新代码: 没跑(没改原有测试)")
    violations = check.get("violations", [])
    if violations:
        lines += ["", "## 违规"]
        lines.extend(f"- {v['why']} ({v['where']})" for v in violations)
        lines.append(
            f'验收要 `{CMD} accept --waive "原因"`;有禁止操作时,原因里要写用户的原话。'
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
    report_text = " ".join(str(x) for x in (report.get("summary", ""), *report.get("problems", []))).lower()
    mentions_test = any(marker in report_text for marker in ("测试", "test", "pytest"))
    mentions_failure = any(marker in report_text for marker in ("失败", "没过", "未通过", "fail"))
    if check.get("passed") and mentions_test and mentions_failure:
        lines.append("助手说有测试没过,引擎在沙箱外跑的检查是通过的,以引擎检查为准")
    for question in report.get("questions", []):
        lines.append(f"- {'(阻塞)' if question.get('blocking') else ''}问题:{question.get('text', '')}")
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
        station = _station_path(root, task, state)
        lines.append(
            f"候选 `{candidate['commit'][:10]}`(基于 `{candidate['base'][:10]}`);"
            f"工位 `{station}`(只看不改,要改用 revise)。完整 diff:`git diff {candidate['base'][:10]} {candidate['commit'][:10]}`"
        )
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
            files = [(line.split("\t", 2)[2], git("diff", candidate["base"], candidate["commit"], "--", line.split("\t", 2)[2], cwd=root)) for line in numstat.splitlines()]
            non_tests = [part for path, part in files if not _is_test_path(path)]
            tests = [path for path, _ in files if _is_test_path(path)]
            if sum(len(part.splitlines()) for part in non_tests) <= 400:
                if tests:
                    lines.append("测试文件的 diff 没附")
                    lines.extend(f"- {path}" for path in tests)
                selected = "\n".join(non_tests)
                if selected:
                    lines += ["", "```diff", selected.rstrip(), "```"]
    else:
        if failed:
            lines.append(f"- 候选没建成: {failed.get('detail', '')}")
            lines.append(f"下一步: {CMD} revise - (说明怎么改)或 {CMD} cancel")
            return "\n".join(lines) + "\n"
        lines.append("- 无代码候选")
    lines.append(next_step)
    return "\n".join(lines) + "\n"


def _station_path(root: Path, task: dict, state: dict) -> str:
    for run_id in reversed(task.get("runs") or []):
        name = (state["runs"].get(run_id) or {}).get("station")
        if name:
            line = (state["stations"].get(name) or {}).get("line", "main")
            return gitops.station_dir(root, line).as_posix()
    return gitops.station_dir(root).as_posix()


def next_step_text(task: dict, check: dict) -> str:
    report = task.get("latest_report") or {}
    if task.get("state") == "blocked" or report.get("status") == "blocked":
        return f"下一步: {CMD} revise -(回答助手的问题)"
    failed = any(not result.get("passed") for result in check.get("results", []))
    if failed or check.get("violations"):
        return (
            f'下一步: {CMD} revise -(或确认后 {CMD} accept --waive "原因")'
        )
    return f"下一步: {CMD} accept(要改就 {CMD} revise -)"
