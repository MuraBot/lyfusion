"""Compact assistant prompts for the four-field task interface."""

from __future__ import annotations

import re
from pathlib import Path


def model_notes(root, model: str) -> dict[str, str]:
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        return {"sidekick": "", "lead": ""}
    result = {"sidekick": [], "lead": []}
    paths = (Path(__file__).parent / "prompts" / "models" / f"{model}.md",
             Path(root) / "fusion" / "models" / f"{model}.md")
    for path in paths:
        if not path.is_file():
            continue
        section = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() == "## 给助手":
                section = "sidekick"
            elif line.strip() == "## 给 lead":
                section = "lead"
            elif line.startswith("## "):
                section = None
            elif section and line.strip():
                result[section].append(line)
    return {key: "\n".join(value) for key, value in result.items()}

REPORT_REMINDER = "Return only the final JSON report with status, summary, questions, choices, problems and brief_check; status is done or blocked."
CONTINUE_PROMPT = ("You reported blocked but listed no blocking question. If nothing blocks you, continue and finish the brief. "
                   "If something does block you, report blocked again with a question marked blocking that says what you need from the lead.")

def continue_prompt() -> str:
    return CONTINUE_PROMPT + "\n" + REPORT_REMINDER
# 续用同一个会话时(自动修、修改意见、补报告)只重申的短规则;完整的做法在 WORK_RULES,派工时发一次
FIXED_RULES = """固定规则:
- 一口气做完本次任务。
- 读代码时一次读整份文件或大段,可以一条命令读几个文件;不要每次只读几十行。同一条命令不要反复跑,改了代码后重跑测试和 lint 除外。
- 中途只跑和改动有关的测试(单个文件或单个用例),沿用项目测试命令里的参数,比如并行;全量测试和 lint 只在结束前各跑一次。
- 最终回复只输出 JSON 报告(status/summary/questions/choices/problems)。"""

FORBIDDEN = [
    '只在当前工位目录工作;不提交、不推送、不切分支,提交由引擎做。',
    '不改弱、不删除原有测试来让自己通过;不改检查命令。环境错误原样重跑,不要关闭证书检查或绕过检查/钩子(--no-verify)。',
    '不调用 Claude,不读 ~/.claude/、AppData 里 Claude 的文件夹和 Codex 的 auth.json;不替用户接受协议,不下载和任务无关的文件。',
]

FIXED_RULES += "\n\n不能做的事:\n" + "\n".join(f"- {item}" for item in FORBIDDEN)


# 派工时给助手的完整做法(来自 v4 的 sidekick.md)。只给助手看,lead 不为它付调用和上下文
WORK_RULES = """你是 lyfusion 的助手。lead 负责设计和判断,你按下面的任务单实现。途中不和 lead 通信,你交回的只有代码改动和最终报告。

## 怎么做
1. 一口气做完:按 Brief 从头做到尾,一步做完直接做下一步。只在两种情况结束:全部做完;遇到下面"停下"的情况。
2. 自己写测试、自己写代码、自己跑测试。结束前把"项目的测试和 lint"和"检查命令"都跑一遍,核对通过的测试数量:有的框架跳过整批测试也返回 0,数量不对就是失败。只编译不运行不算测试。
   读代码时一次读整份文件或大段,可以一条命令读几个文件;不要每次只读几十行。同一条命令不要反复跑,改了代码后重跑测试和 lint 除外。
3. 改造现有代码时,原有行为(报错文字、空值和空行的处理、编号规则、输出格式)保持不变,除非 Brief 要求改。
   不要对整个项目或没改的文件跑格式化器(ruff format、black 等),只改任务需要的地方;lint 只修报出来的问题,不要加 `noqa` 绕过。
4. Brief 里的决定和"不要做的事"照做。发现和事实冲突时不改方向,在 problems 里写清冲突和证据。
5. 可以自己定:Brief 没定的内部结构、命名、测试用例;框架的常数和默认值(查框架源码确认);Brief 目标隐含要生成的文件。
6. 你结束后,引擎会再跑测试、lint 和检查命令,不通过会把输出交给你接着修。

## 不确定时
- 猜错代价小:按你的推荐做完,写进 questions(blocking=false),写清你选了什么、还有哪些选项。
- 猜错代价大(要改公开接口或数据格式、要删用户的数据、和 Brief 或 decisions.md 冲突、需要新的权限或下载):先做不依赖它的部分,然后停下,questions 里写 blocking=true,status 写 blocked。
- 环境或网络错误:原样重跑、加长超时、复用缓存。不要关证书检查,不要跳过钩子(--no-verify)。

## 最终报告(JSON)
只写仓库里看不到的。改了什么、测试过没过,lead 看 diff 和引擎的检查结果。
- summary:一两句话,做成了什么
- questions:要 lead 回答的问题,写清选项和你的推荐
- choices:没人要求、你自己定下的、用户或其他模块可能在意的做法。what 写选了什么,why 写理由和没选的做法。没有就写空列表
- problems:没做完的、已知的问题;改了哪些原有测试、为什么

"""

WORK_RULES += "\n\n## 不能做的事\n" + "\n".join(f"- {item}" for item in FORBIDDEN)
WORK_RULES += """

## Brief conventions
- The brief gives constraints, edge cases, done criteria, behaviour that must not change and exact test assertions. Follow its decisions; treat anything marked as a guess as a suggestion: with contrary evidence you may deviate, record it in choices with a reason.
- Before the final report, reread the brief and your work item's `git diff` item by item, then fill `brief_check` with one entry per decision, constraint and done criterion. Use `met`, `differs` (and explain why), or `not_done`; `where` must be `file:line` or empty.
- If the brief gives stop conditions, stop when one is met (status blocked).

## 测试跑法
- 中途只跑和改动有关的测试(单个文件或单个用例),沿用项目测试命令里的参数,比如并行;全量测试和 lint 只在结束前各跑一次。
- 沙箱不能结束别的进程,也可能写不了系统临时目录;这类测试在你那里过不了时,在 problems 写明是沙箱限制,引擎会在沙箱外再跑检查;不要把临时目录(例如 pytest 的 --basetemp)放在工位里会被提交的位置。"""

def _checks(plan: dict) -> str:
    return (
        "\n".join(
            f"- `{item['run']}` (期望 {item.get('expect', 0)})"
            for item in plan.get("checks", [])
        )
        or "- (无)"
    )


def task_prompt(
    task: dict, decisions: str, handoff: str | None = None, project_cmds: list[str] | None = None,
    model_note: str = "", model: str = "",
) -> str:
    plan = task["plan"]
    parts = [WORK_RULES]
    if model_note:
        parts.append(f"## 助手 {model} 的备注\n{model_note}")
    if handoff:
        parts.append("## 上一个工位交接摘要\n" + handoff)
    cmds = [c for c in project_cmds or [] if c]
    parts += [
        f"## 目标\n{plan['goal']}",
        f"## Brief\n{plan['brief']}",
        "## 项目的测试和 lint\n" + ("\n".join(f"- `{c}`" for c in cmds) or "- (未配置)"),
        "## 检查命令和期望\n" + _checks(plan),
        "## 文件范围\n"
        + ("\n".join(f"- {g}" for g in plan.get("scope", [])) or "- (未指定)"),
        "## fusion/decisions.md 全文\n" + decisions,
    ]
    return "\n\n".join(parts)


def fix_prompt(failures: str, decisions: str, model_note: str = "") -> str:
    return (
        "## 检查失败\n"
        + failures
        + "\n\n## fusion/decisions.md 全文\n"
        + decisions
        + "\n\n"
        + FIXED_RULES
        + "\n"
        + REPORT_REMINDER
        + (f"\n\n{model_note}" if model_note else "")
    )


def changes_prompt(text: str, decisions: str, model_note: str = "") -> str:
    return (
        "## lead 的修改意见(原文)\n"
        + text
        + "\n\n## fusion/decisions.md 全文\n"
        + decisions
        + "\n\n"
        + FIXED_RULES
        + "\n"
        + REPORT_REMINDER
        + (f"\n\n{model_note}" if model_note else "")
    )


def minor_fix_prompt(text: str, files: list[str]) -> str:
    allowed = "\n".join(f"- {path}" for path in files) or "- (no files)"
    return (
        "Make exactly this fix: " + text + "\n"
        "Change only these files:\n" + allowed + "\n"
        "Change at most 20 lines total (added plus deleted). Do not refactor or make any other edits.\n"
        "Then finish with the usual report.\n"
        + REPORT_REMINDER
    )


def report_prompt(previous_error: str, decisions: str) -> str:
    return (
        "Before returning the report, reread the brief and the work item's git diff item by item. Fill `brief_check` with one entry per decision, constraint and done criterion, using `met`, `differs` (explain why), or `not_done`; `where` must be `file:line` or empty.\n"
        "## 补交最终报告\n上次运行未返回有效报告。不要再改代码。\n"
        + previous_error
        + "\n\n## fusion/decisions.md 全文\n"
        + decisions
        + "\n\n"
        + FIXED_RULES
        + "\n"
        + REPORT_REMINDER
    )


def explore_prompt(original: str, decisions: str) -> str:
    return (
        "This is read-only code exploration. Do not modify any files. Keep the entire answer, including the draft, to 150 lines or fewer. Do not write an implementation plan.\n"
        "1. Restate the lead's task and goal, then list uncertainties.\n"
        "2. Find relevant code excerpts in order of importance. For each, give `file:start-end`, explain why it matters, and quote no more than 15 source lines.\n"
        "3. Answer the lead's numbered questions (Q1~Q3; answer those present and omit this section if there are none), referring to the excerpts above. If the repository cannot answer one, check framework source or official documentation and name the source.\n"
        "4. List existing conventions and pitfalls.\n"
        "Read whole files or large sections; one command may read several files. Do not repeat the same command (except rerunning tests and lint after code changes).\n"
        "Safety: do not read `~/.claude/`, Claude folders under AppData, or Codex auth.json; do not call Claude.\n"
        "Finish with `## Draft (mechanical only)` and exactly three lists: files involved (path — one line describing what is there), suggested check commands, and verbatim signatures of functions likely to change. The draft contains no approach or recommended implementation. Keep this section within the 150-line total.\n"
        "## Lead's task (verbatim)\n"
        + original
        + "\n\n## fusion/decisions.md (full text)\n"
        + decisions
    )

def handoff_summary(state: dict, old: dict) -> str:
    lines = [f"上一个工位 {old['name']} 做过的任务:{', '.join(old['tasks']) or '(无)'}"]
    if old.get("files"):
        lines.append("改过的文件:" + ", ".join(old["files"][:60]))
    for task_id in old["tasks"][-3:]:
        task = state["tasks"].get(task_id)
        if task:
            lines.append(
                f"- {task_id}({task['state']}):{(task.get('plan') or {}).get('goal', '')}"
            )
            for run_id in task["runs"][-1:]:
                report = state["runs"][run_id].get("report") or {}
                lines.extend(
                    f"  已知问题:{problem}" for problem in report.get("problems") or []
                )
    return "\n".join(lines)
