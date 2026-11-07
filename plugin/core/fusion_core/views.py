"""Lead-facing status, ledger, and SessionStart usage text."""
from __future__ import annotations

from .state import active_task

STATE_CN = {"exploring": "探索中", "explored": "探索完成", "planned": "待派工", "running": "助手在做",
            "blocked": "待回答", "checking": "检查中", "in_review": "待审", "integrating": "验收中",
            "accepted": "已验收", "cancelled": "已取消"}
SESSION_LIMIT = 20

LEAD_GUIDE = """lyfusion 已开:这个项目的代码活交给 Codex 助手做,你(lead)只做 4 件事。
每条命令都在 Bash 里用 run_in_background 运行。命令自己等到有结果才结束,结束时会叫醒你:
不要开 Monitor、不要 sleep、不要轮询。醒来后直接读结果文件。
1. 探索:fusion-core explore - <<'EOF' …… EOF
   写用户的任务原话(一字不改)和你想知道的,最多 3 条,编号 Q1~Q3。结果:fusion/explore.md
2. 派工:fusion-core delegate - <<'EOF' {计划} EOF   续用探索的会话。结果:fusion/review.md
   计划是 JSON:{\"goal\": \"一句话\", \"brief\": \"Markdown 正文\", \"checks\": [{\"run\": \"命令\", \"expect\": 0}], \"scope\": [\"src/**\"]}
   checks、scope 可省。brief 推荐小标题:目标、决定、不要做的事、已知的坑。
3. 修改:fusion-core revise - <<'EOF' 修改意见 EOF   自由文字,助手的问题也在这里回答。结果:fusion/review.md
4. 验收:fusion-core accept   合并、重跑检查、压成 1 个提交、快进主分支。
跨任务都要守的设计决定写进 fusion/decisions.md(普通文件,直接编辑),引擎每次派工把全文带给助手。
审查包不够看时,用 Read 看具体文件。看进度 fusion-core status;放弃任务 fusion-core cancel。"""


def session_context(root, cfg, state, source=None) -> str:
    return LEAD_GUIDE


def task_line(task: dict) -> str:
    plan = task.get("plan") or {}
    return f"{task['id']} · {STATE_CN.get(task['state'], task['state'])} · {plan.get('goal', '')}"


def status(root, cfg, state, target: str | None = None) -> str:
    if target and target.startswith("r"):
        run = state["runs"].get(target)
        return f"{target}: {run['status']} ({run['kind']})" if run else f"运行 {target} 不存在"
    if target:
        task = state["tasks"].get(target)
        return task_line(task) if task else f"任务 {target} 不存在"
    lines = [f"Fusion: {'开启' if cfg.get('local', {}).get('enabled') else '关闭'}"]
    for task in state["tasks"].values():
        lines.append(task_line(task))
        if task.get("latest"):
            cand = state["candidates"][task["latest"]]
            check = cand.get("checks") or {}
            lines.append(f"  候选 {task['latest']}: {'检查通过' if check.get('passed') else '检查未通过'}")
    if len(lines) == 1:
        lines.append("没有任务")
    return "\n".join(lines)


def prompt_line(state) -> str:
    task = active_task(state)
    return f"Fusion: {task_line(task)}" if task else "Fusion: 没有进行中的任务"


def ledger(state, task_id: str | None = None) -> str:
    lines = ["| 任务 | 状态 | 目标 | 修复 | 修改轮 |", "|---|---|---|---:|---:|"]
    for task in state["tasks"].values():
        if task_id and task["id"] != task_id:
            continue
        plan = task.get("plan") or {}
        lines.append(f"| {task['id']} | {task['state']} | {plan.get('goal', '')} | {task['fix_attempts']} | {task['change_rounds']} |")
    return "\n".join(lines)
