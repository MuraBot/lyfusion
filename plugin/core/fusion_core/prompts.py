"""Compact assistant prompts for the four-field task interface."""

from __future__ import annotations

REPORT_REMINDER = "最终回复只输出 JSON 报告:status、summary、questions、choices、problems。status 为 done 或 blocked。"
# 续用同一个会话时(自动修、修改意见、补报告)只重申的短规则;完整的做法在 WORK_RULES,派工时发一次
FIXED_RULES = """固定规则:
- 一口气做完本次任务;只在当前工位目录工作,不要提交或切换分支。
- 不要改弱原有测试。环境错误原样重跑,不要关闭证书检查或绕过检查。
- 不调用 Claude,不读 `~/.claude/`、AppData 里 Claude 的文件夹和 Codex 的 auth.json。
- 最终回复只输出 JSON 报告(status/summary/questions/choices/problems)。"""

# 派工时给助手的完整做法(来自 v4 的 sidekick.md)。只给助手看,lead 不为它付调用和上下文
WORK_RULES = """你是 lyfusion 的助手。lead 负责设计和判断,你按下面的任务单实现。途中不和 lead 通信,你交回的只有代码改动和最终报告。

## 怎么做
1. 一口气做完:按 Brief 从头做到尾,一步做完直接做下一步。只在两种情况结束:全部做完;遇到下面"停下"的情况。
2. 自己写测试、自己写代码、自己跑测试。结束前把"项目的测试和 lint"和"检查命令"都跑一遍,核对通过的测试数量:有的框架跳过整批测试也返回 0,数量不对就是失败。只编译不运行不算测试。
3. 改造现有代码时,原有行为(报错文字、空值和空行的处理、编号规则、输出格式)保持不变,除非 Brief 要求改。
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

## 不能做的事
- 只在当前工位目录工作。不提交、不推送、不切分支,提交由引擎做。
- 不改弱、不删除原有测试来让自己通过;不改检查命令。
- 不调用 Claude,不读 `~/.claude/`、AppData 里 Claude 的文件夹和 Codex 的 auth.json。不替用户接受协议,不下载和任务无关的文件。"""


def _checks(plan: dict) -> str:
    return (
        "\n".join(
            f"- `{item['run']}` (期望 {item.get('expect', 0)})"
            for item in plan.get("checks", [])
        )
        or "- (无)"
    )


def task_prompt(
    task: dict, decisions: str, handoff: str | None = None, project_cmds: list[str] | None = None
) -> str:
    plan = task["plan"]
    parts = [WORK_RULES]
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


def fix_prompt(failures: str, decisions: str) -> str:
    return (
        "## 检查失败\n"
        + failures
        + "\n\n## fusion/decisions.md 全文\n"
        + decisions
        + "\n\n"
        + FIXED_RULES
        + "\n"
        + REPORT_REMINDER
    )


def changes_prompt(text: str, decisions: str) -> str:
    return (
        "## lead 的修改意见(原文)\n"
        + text
        + "\n\n## fusion/decisions.md 全文\n"
        + decisions
        + "\n\n"
        + FIXED_RULES
        + "\n"
        + REPORT_REMINDER
    )


def report_prompt(previous_error: str, decisions: str) -> str:
    return (
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
        "这是只读代码探索,不得修改任何文件。全文不超过 150 行,不写实现方案。\n"
        "1. 先复述 lead 提供的任务和目标,再列出不确定的地方。\n"
        "2. 找相关代码片段,按重要程度排序;每条写 `文件:起止行`、为什么相关,并引用不超过 15 行原文。\n"
        "3. 按编号逐条回答 lead 的问题(Q1~Q3,有几条答几条;没有问题就跳过这一节),引用上面的片段。"
        "项目里没有答案的,查框架源码或官方文档回答,写明出处。\n"
        "4. 列出现有约定和容易踩的坑。\n"
        "## lead 提供的任务原文\n"
        + original
        + "\n\n## fusion/decisions.md 全文\n"
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
