"""Lead-facing status, ledger, and SessionStart usage text."""
from __future__ import annotations

from .config import configuration_warnings, current_model_settings, effective_settings
from .util import CMD

STATE_CN = {"exploring": "探索中", "explored": "探索完成", "planned": "待派工", "running": "助手在做",
            "blocked": "待回答", "checking": "检查中", "in_review": "待审", "integrating": "验收中",
            "accepted": "已验收", "cancelled": "已取消"}
SESSION_LIMIT = 20

LEAD_GUIDE = """lyfusion 已开:这个项目的代码活交给 Codex 助手做,你(lead)只做 4 件事。
每条命令都在 Bash 里用 run_in_background 运行。命令自己等到有结果才结束,结束时会叫醒你:
不要开 Monitor、不要 sleep、不要轮询。醒来后直接读结果文件。
1. 探索(每个任务都先做,不要自己通读代码):fusion-core explore - <<'EOF' …… EOF
   写用户的任务原话(一字不改)和你想知道的,最多 3 条,编号 Q1~Q3。结果:fusion/explore.md
2. 派工:fusion-core delegate - <<'EOF' {计划} EOF   续用探索的会话。结果:fusion/review.md
   计划是 JSON:{\"goal\": \"一句话\", \"brief\": \"Markdown 正文\", \"checks\": [{\"run\": \"命令\", \"expect\": 0}], \"scope\": [\"src/**\"]}
   checks、scope 可省。brief 推荐小标题:目标、决定、不要做的事、已知的坑。
3. 修改:fusion-core revise - <<'EOF' 修改意见 EOF   自由文字,助手的问题也在这里回答。结果:fusion/review.md
4. 验收:fusion-core accept   合并、重跑检查、压成 1 个提交、快进主分支。
跨任务都要守的设计决定写进 fusion/decisions.md(普通文件,直接编辑),引擎每次派工把全文带给助手,并自动提交它。
审查包不够看时,用 Read 看具体文件。看进度 fusion-core status;放弃任务 fusion-core cancel。"""


def lead_guide() -> str:
    """注入给 lead 的使用说明:模板里的 fusion-core 换成安装目录里的完整命令(插件不能带 bin/)。"""
    return LEAD_GUIDE.replace("fusion-core ", CMD + " ")


def session_context(root, cfg, state, source=None) -> str:
    return lead_guide()


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
    local = cfg.get("local", {})
    sk = local.get("sidekick", {})
    settings = current_model_settings(sk)
    effective = effective_settings(cfg)
    lines = [f"Fusion: {'开启' if local.get('enabled') else '关闭'}",
             f"助手: {sk.get('model', '')} · effort {settings['effort'] or '默认'} · fast {'on' if settings['fast'] else 'off'} · 压缩 {settings['compact']}",
             ("Codex 环境: 干净(不读 ~/.codex/config.toml,关 apps、plugins)" if effective["clean"]
              else "Codex 环境: 和桌面端一样(读 ~/.codex/config.toml)")
             + "(项目设置 fusion/config.json 的 clean)",
             f"换工位: 上下文超过 {effective['switch_at']}(压缩上限 {settings['compact']} × {int(effective['context_ratio'] * 100)}%)"]
    lines.extend(f"警告: {warning}" for warning in configuration_warnings(cfg))
    for task in state["tasks"].values():
        lines.append(task_line(task))
        if task.get("latest"):
            cand = state["candidates"][task["latest"]]
            check = cand.get("checks") or {}
            lines.append(f"  候选 {task['latest']}: {'检查通过' if check.get('passed') else '检查未通过'}")
    if not state["tasks"]:
        lines.append("没有任务")
    return "\n".join(lines)


def ledger(state, task_id: str | None = None) -> str:
    lines = ["| 任务 | 状态 | 目标 | 修复 | 修改轮 | Lead 输入/缓存/输出 (M) | 助手输入/缓存/输出 (M) | 助手模型 / effort / fast |",
             "|---|---|---|---:|---:|---:|---:|---|"]
    for task in state["tasks"].values():
        if task_id and task["id"] != task_id:
            continue
        plan = task.get("plan") or {}
        usage = state.get("usage", {}).get(task["id"], {})
        # 引擎不读 Claude 的记录;lead 的用量由 lead 自己用用量工具看,没有数据就写明
        lead = _usage_triplet(usage["lead"]) if usage.get("lead") else "未记录(lead 用用量工具看)"
        assistant = _usage_triplet(usage.get("sidekick", {}))
        settings = []
        seen = set()
        for run_id in task.get("runs", []):
            run = state.get("runs", {}).get(run_id, {})
            model = run.get("model")
            if not model:
                continue
            item = (model, run.get("effort") or "默认", "on" if run.get("fast") else "off")
            if item not in seen:
                settings.append(" / ".join(item))
                seen.add(item)
        lines.append(f"| {task['id']} | {task['state']} | {plan.get('goal', '')} | {task['fix_attempts']} | {task['change_rounds']} | {lead} | {assistant} | {'<br>'.join(settings)} |")
    return "\n".join(lines)


def _usage_triplet(usage: dict) -> str:
    input_m = usage.get("input", 0) / 1_000_000
    cache_m = (usage.get("cache_read", 0) + usage.get("cache_write", 0)) / 1_000_000
    output_m = usage.get("output", 0) / 1_000_000
    return f"{input_m:.3f} / {cache_m:.3f} / {output_m:.3f}"
