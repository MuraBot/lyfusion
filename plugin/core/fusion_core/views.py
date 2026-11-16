"""Lead-facing status, ledger, and SessionStart usage text."""
from __future__ import annotations

from .config import (
    configuration_warnings,
    current_model_settings,
    effective_settings,
    supports_fast,
)
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
2. 派工:fusion-core delegate - <<'EOF' 计划 EOF   续用探索的会话。结果:fusion/review.md
   计划用 Markdown:第一行 "# 一句话目标",下面是 brief 正文;可选的 "## scope"、"## checks" 两节每行写 "- glob" 或 "- 命令"(期望退出码 0)。
   也接受原来的 JSON(第一个字符是 {)。brief 推荐小标题:目标、决定、不变的行为、猜测(未证实)、不要做的事、已知的坑、停下的条件。
   检查标准写在产出上(命令输出、渲染出的文字),不写在源码文字上:助手会照字面去凑。
3. 修改:fusion-core revise - <<'EOF' 修改意见 EOF   自由文字,助手的问题也在这里回答。结果:fusion/review.md
4. 验收:fusion-core accept   合并、重跑检查、压成 1 个提交、快进主分支。
跨任务都要守的设计决定写进 fusion/decisions.md(普通文件,直接编辑),引擎每次派工把全文带给助手,并自动提交它。
审查包不够看时,用 Read 看审查包里工位路径下的文件(你自己目录里的还是旧代码)。看进度 fusion-core status;看用量 fusion-core ledger;放弃任务 fusion-core cancel。"""


def lead_guide() -> str:
    """注入给 lead 的使用说明:模板里的 fusion-core 换成安装目录里的完整命令(插件不能带 bin/)。"""
    return LEAD_GUIDE.replace("fusion-core ", CMD + " ")


def session_context(root, cfg, state, source=None) -> str:
    from .prompts import model_notes
    model = cfg.get("local", {}).get("sidekick", {}).get("model", "")
    note = model_notes(root, model)["lead"]
    guide = lead_guide()
    return guide + (f"\n\n## 给 lead 的模型备注({model})\n{note}" if note else "")


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
    fast_label = "on" if settings["fast"] else "off" if supports_fast(sk.get("model", "")) else "不支持"
    lines = [f"Fusion: {'开启' if local.get('enabled') else '关闭'}",
             f"助手: {sk.get('model', '')} · effort {settings['effort'] or '默认'} · fast {fast_label} · 压缩 {settings['compact']}",
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
    lines = ["| 任务 | 状态 | 目标 | 修复 | 修改轮 | Lead(验收时) | 助手输入/缓存/输出 (M) | 助手模型 / effort / fast |",
             "|---|---|---|---:|---:|---:|---:|---|"]
    for task in state["tasks"].values():
        if task_id and task["id"] != task_id:
            continue
        plan = task.get("plan") or {}
        usage = state.get("usage", {}).get(task["id"], {})
        # 引擎不读 Claude 的记录;lead 的用量由 lead 自己用用量工具看,没有数据就写明
        lead = _lead_usage_display(state, task["id"])
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
    lines += ["", "| 任务 | 运行 | 种类 | 结束状态 | 用时(分钟) | 命令 | 碎读 | 重复 | Codex 版本 |",
              "|---|---|---|---|---:|---:|---:|---:|---|"]
    kinds = {"explore": "探索", "implement": "实现", "changes": "修改", "fix": "自动修", "report": "补报告"}
    for run in state.get("runs", {}).values():
        if task_id and run.get("task") != task_id:
            continue
        stats = run.get("runstats") or {}
        duration = run.get("duration")
        minutes = f"{duration / 60:.1f}" if isinstance(duration, (int, float)) else "-"
        lines.append(
            f"| {run.get('task') or '-'} | {run['id']} | {kinds.get(run.get('kind'), run.get('kind', '-'))} | "
            f"{run.get('result') or run.get('status', '-')} | {minutes} | {stats.get('commands', '-')} | "
            f"{stats.get('small_reads', '-')} | {stats.get('repeats', '-')} | {run.get('codex_version') or '-'} |"
        )
    return "\n".join(lines)


def _usage_triplet(usage: dict) -> str:
    input_m = usage.get("input", 0) / 1_000_000
    cache_m = (usage.get("cache_read", 0) + usage.get("cache_write", 0)) / 1_000_000
    output_m = usage.get("output", 0) / 1_000_000
    return f"{input_m:.3f} / {cache_m:.3f} / {output_m:.3f}"



def _lead_usage_display(state: dict, task_id: str) -> str:
    accept = state.get("lead_usage", {}).get(task_id)
    if not accept:
        return "未记录"
    accept_data = accept.get("data", {})
    explores = []
    for record in state.get("lead_usage_events", []):
        if record.get("seq", 0) >= accept.get("seq", 0):
            continue
        data = record.get("data", {})
        if data.get("at") != "explore" or "started_at" not in accept_data:
            continue
        if data.get("started_at") != accept_data["started_at"]:
            continue
        owner = record.get("task")
        if owner is None:
            owner = _explore_snapshot_task(state, record.get("seq", 0))
        if owner == task_id:
            explores.append(record)
    explore = max(explores, key=lambda event: event.get("seq", 0), default=None)

    if explore and "cost_usd" in accept_data and "cost_usd" in explore.get("data", {}):
        delta = accept_data["cost_usd"] - explore["data"]["cost_usd"]
        amount = f"-${abs(delta):.2f}" if delta < 0 else f"${delta:.2f}"
    else:
        amount = "-"
    parts = [f"本任务 {amount}"]
    context = []
    if "tokens" in accept_data and "window" in accept_data:
        context.append(
            f"上下文 {_compact_tokens(accept_data['tokens'])}/"
            f"{_compact_tokens(accept_data['window'])}"
        )
    if "five_hour" in accept_data:
        context.append(f"5h {_format_percent(accept_data['five_hour'])}")
    if "seven_day" in accept_data:
        context.append(f"周 {_format_percent(accept_data['seven_day'])}")
    if context:
        parts.append(f"验收时 {context[0]}")
        parts.extend(context[1:])
    return " · ".join(parts)


def _explore_snapshot_task(state: dict, seq: int) -> str | None:
    tasks = list(state.get("tasks", {}).values())
    active = [task for task in tasks
              if task.get("created_seq", 0) < seq
              and (task.get("closed_seq") is None or task["closed_seq"] > seq)]
    if active:
        return max(active, key=lambda task: task.get("created_seq", 0))["id"]
    upcoming = [task for task in tasks if task.get("created_seq", 0) > seq]
    if upcoming:
        return min(upcoming, key=lambda task: task.get("created_seq", 0))["id"]
    return None


def _compact_tokens(value) -> str:
    if value >= 1000:
        thousands = value / 1000
        return f"{int(thousands)}k" if thousands.is_integer() else f"{thousands:g}k"
    return str(value)


def _format_percent(value) -> str:
    return f"{int(value)}%" if value == int(value) else f"{value:g}%"
