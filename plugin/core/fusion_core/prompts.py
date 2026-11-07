"""Compact assistant prompts for the four-field task interface."""
from __future__ import annotations

REPORT_REMINDER = "最终回复只输出 JSON 报告:status、summary、questions、choices、problems。status 为 done 或 blocked。"
FIXED_RULES = """固定规则:
- 一口气做完本次任务;只在当前工位目录工作,不要提交或切换分支。
- 不要改弱原有测试。环境错误原样重跑,不要关闭证书检查或绕过检查。
- 最终回复只输出 JSON 报告(status/summary/questions/choices/problems)。"""


def _checks(plan: dict) -> str:
    return "\n".join(f"- `{item['run']}` (期望 {item.get('expect', 0)})" for item in plan.get("checks", [])) or "- (无)"


def task_prompt(task: dict, decisions: str, handoff: str | None = None, first: bool = True) -> str:
    plan = task["plan"]
    parts = []
    if first:
        parts.append(FIXED_RULES)
    if handoff:
        parts.append("## 上一个工位交接摘要\n" + handoff)
    parts += [f"## 目标\n{plan['goal']}", f"## Brief\n{plan['brief']}",
              "## 检查命令和期望\n" + _checks(plan),
              "## 文件范围\n" + ("\n".join(f"- {g}" for g in plan.get("scope", [])) or "- (未指定)"),
              "## fusion/decisions.md 全文\n" + decisions]
    if not first:
        parts.append(REPORT_REMINDER)
    return "\n\n".join(parts)


def fix_prompt(failures: str, decisions: str) -> str:
    return ("## 检查失败\n" + failures + "\n\n## fusion/decisions.md 全文\n" + decisions
            + "\n\n" + FIXED_RULES + "\n" + REPORT_REMINDER)


def changes_prompt(text: str, decisions: str) -> str:
    return ("## lead 的修改意见(原文)\n" + text + "\n\n## fusion/decisions.md 全文\n" + decisions
            + "\n\n" + FIXED_RULES + "\n" + REPORT_REMINDER)


def report_prompt(previous_error: str, decisions: str) -> str:
    return ("## 补交最终报告\n上次运行未返回有效报告。不要再改代码。\n" + previous_error
            + "\n\n## fusion/decisions.md 全文\n" + decisions + "\n\n" + FIXED_RULES + "\n" + REPORT_REMINDER)


def explore_prompt(original: str, decisions: str) -> str:
    return ("你是 lyfusion 助手,这是只读代码探索,不得修改任何文件。\n"
            "先复述任务目标和不确定之处;按问题逐条回答;提供相关代码路径、行号、原文片段和约定;不写实现方案。\n"
            "## lead 提供的任务原文(原样保留)\n" + original + "\n\n## fusion/decisions.md 全文\n"
            + decisions + "\n\n" + FIXED_RULES)


def handoff_summary(state: dict, old: dict) -> str:
    lines = [f"上一个工位 {old['name']} 做过的任务:{', '.join(old['tasks']) or '(无)'}"]
    if old.get("files"):
        lines.append("改过的文件:" + ", ".join(old["files"][:60]))
    for task_id in old["tasks"][-3:]:
        task = state["tasks"].get(task_id)
        if task:
            lines.append(f"- {task_id}({task['state']}):{(task.get('plan') or {}).get('goal', '')}")
            for run_id in task["runs"][-1:]:
                report = state["runs"][run_id].get("report") or {}
                lines.extend(f"  已知问题:{problem}" for problem in report.get("problems") or [])
    return "\n".join(lines)
