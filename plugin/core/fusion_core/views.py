"""Lead-facing status, ledger, and SessionStart usage text."""
from __future__ import annotations

import math

from .config import (
    configuration_warnings,
    current_model_settings,
    effective_settings,
    handoff_settings,
    supports_fast,
)
from .util import CMD

STATE_LABEL = {"exploring": "Exploring", "explored": "Explored", "planned": "Planned", "running": "Running",
            "blocked": "Blocked", "checking": "Checking", "in_review": "In review", "integrating": "Integrating",
            "accepted": "Accepted", "cancelled": "Cancelled"}
SESSION_LIMIT = 20

LEAD_GUIDE = """lyfusion is on: the Codex sidekick writes this project's code; you (the lead) define each task completely and review the result.
Run every command below in the foreground in Bash with timeout 600000; results print straight to the output. No run_in_background, Monitor, sleep or polling.
If the sidekick is still working after 9 minutes the command returns early (exit code 3); run fusion-core wait to keep waiting. The sidekick is not affected. Messages the user sends while you wait are queued.
Choose a tier after a quick look at the code, not from the task wording alone:
  A. Do it yourself: a small change in a known place (about 2 files, 30 lines), no slow tests; questions and architecture advice; serial root-cause debugging.
  B. Delegate without exploring: you already know which files change. Start at step 2.
  C. Full flow: location unclear, many files, mechanical refactors, expensive verification.
1. Explore: fusion-core explore - <<'EOF' … EOF
   The user's task verbatim, then at most 3 questions numbered Q1~Q3.
2. Delegate: fusion-core delegate - <<'EOF' plan EOF   Reuses the exploration thread.
   Line 1 is "# one-sentence goal", then the brief. Optional "## scope" and "## checks" sections hold one "- glob" or "- command" (exit code 0 expected) per line.
   The brief states constraints, edge cases, done criteria, behaviour that must not change and exact test assertions. Signatures and key snippets are fine; never dictate whole files. Put several small points into one brief.
   Write checks against outputs (command output, rendered text), not source wording: the sidekick will match wording literally.
3. Revise: fusion-core revise - <<'EOF' feedback EOF   Free text; answer the sidekick's questions here too.
4. Accept: fusion-core accept   Merges, reruns checks, squashes to one commit, fast-forwards main. Chain it with the next task: accept && explore ….
   One small fix left? fusion-core accept --minor-fix "one sentence": the sidekick makes it; it is merged only if it touches files this task already changed, at most 20 lines, with green checks; otherwise you get a review pack.
Design decisions every task must follow go in fusion/decisions.md (edit it directly); each delegation sends it in full and commits it.
Abandon a task: fusion-core cancel.
{handoff}"""


def lead_guide(cfg: dict | None = None) -> str:
    """Render the lead guide with project settings."""
    from . import config as config_mod
    cfg = cfg or {"local": config_mod.DEFAULT_LOCAL, **config_mod.DEFAULT_CONFIG}
    wait_minutes = cfg.get("wait_minutes", config_mod.DEFAULT_CONFIG["wait_minutes"])
    if (not isinstance(wait_minutes, (int, float)) or isinstance(wait_minutes, bool)
            or not math.isfinite(wait_minutes) or wait_minutes < 0):
        wait_minutes = config_mod.DEFAULT_CONFIG["wait_minutes"]
    handoff = config_mod.handoff_settings(cfg)
    handoff_lines = ""
    if handoff["mode"] != "off":
        first = (f"Handoff: when accept says your context passed {handoff['tokens']} tokens, write a handoff "
                 f"(at most 80 lines) to {handoff['dir']}/<YYYY-MM-DD>-<nn>.md: goal, done (commit ids, no code), "
                 "constraints that hold, workstation state, next commands, pitfalls and methods.")
        second = ("Then tell the user they can /clear when convenient. Do not clear the session yourself."
                  if handoff["mode"] == "write" else
                  'Then load the tool with ToolSearch "select:mcp__ccd_session_mgmt__clear_session" and call it '
                  'with session_id "self". Where that tool does not exist (CLI), ask the user to run /clear.')
        handoff_lines = f"{first}\n{second}"
    guide = LEAD_GUIDE.replace("9 minutes", f"{wait_minutes:g} minutes")
    guide = guide.replace("\n{handoff}", f"\n{handoff_lines}" if handoff_lines else "")
    return guide.replace("fusion-core ", CMD + " ")


def session_context(root, cfg, state, source=None) -> str:
    from . import config as config_mod
    from .prompts import model_notes
    model = cfg.get("local", {}).get("sidekick", {}).get("model", "")
    note = model_notes(root, model)["lead"]
    context = lead_guide(cfg)
    if note:
        context += f"\n\n## Model notes for the lead ({model})\n{note}"
    handoff = config_mod.handoff_settings(cfg)
    if source in ("clear", "compact") and handoff["mode"] != "off":
        directory = root / handoff["dir"]
        if directory.is_dir():
            files = sorted(path.name for path in directory.glob("*.md")
                           if path.is_file() and path.name[:1].isdigit())
            if files:
                action = "cleared" if source == "clear" else "compacted"
                context += f"\nContext was {action}: read the latest handoff first: {handoff['dir']}/{files[-1]}"
    return context


def task_line(task: dict) -> str:
    plan = task.get("plan") or {}
    return f"{task['id']} · {STATE_LABEL.get(task['state'], task['state'])} · {plan.get('goal', '')}"


def status(root, cfg, state, target: str | None = None) -> str:
    if target and target.startswith("r"):
        run = state["runs"].get(target)
        return f"{target}: {run['status']} ({run['kind']})" if run else f"Run {target} does not exist"
    if target:
        task = state["tasks"].get(target)
        return task_line(task) if task else f"Task {target} does not exist"
    local = cfg.get("local", {})
    sk = local.get("sidekick", {})
    settings = current_model_settings(sk)
    effective = effective_settings(cfg)
    handoff = handoff_settings(cfg)
    fast_label = "on" if settings["fast"] else "off" if supports_fast(sk.get("model", "")) else "unsupported"
    lines = [f"Fusion: {'on' if local.get('enabled') else 'off'}",
             f"Assistant: {sk.get('model', '')} · effort {settings['effort'] or 'default'} · fast {fast_label} · compact {settings['compact']}",
             ("Codex environment: clean (does not read ~/.codex/config.toml; apps and plugins disabled)" if effective["clean"]
              else "Codex environment: same as desktop (reads ~/.codex/config.toml)")
             + " (set in fusion/config.json)",
             f"Station rotation: context exceeds {effective['switch_at']} (compact limit {settings['compact']} × {int(effective['context_ratio'] * 100)}%)",
             f"Handoff: {handoff['mode']} (at {handoff['tokens']} tokens) · {handoff['dir']}"]
    lines.extend(f"Warning: {warning}" for warning in configuration_warnings(cfg))
    for task in state["tasks"].values():
        lines.append(task_line(task))
        if task.get("latest"):
            cand = state["candidates"][task["latest"]]
            check = cand.get("checks") or {}
            lines.append(f"  Candidate {task['latest']}: {'checks passed' if check.get('passed') else 'checks failed'}")
    if not state["tasks"]:
        lines.append("No tasks")
    return "\n".join(lines)


def ledger(state, task_id: str | None = None) -> str:
    lines = ["| Task | State | Goal | Fixes | Change rounds | Lead (at acceptance) | Lead calls (tools/requests) | Assistant input/cache/output (M) | Assistant model / effort / fast |",
             "|---|---|---|---:|---:|---:|---:|---:|---|"]
    for task in state["tasks"].values():
        if task_id and task["id"] != task_id:
            continue
        plan = task.get("plan") or {}
        usage = state.get("usage", {}).get(task["id"], {})
        # The engine does not read Claude usage; lead checks usage with its own usage tool. Missing data is shown explicitly.
        lead = _lead_usage_display(state, task["id"])
        lead_calls = _lead_calls_display(state, task["id"])
        assistant = _usage_triplet(usage.get("sidekick", {}))
        settings = []
        seen = set()
        for run_id in task.get("runs", []):
            run = state.get("runs", {}).get(run_id, {})
            model = run.get("model")
            if not model:
                continue
            item = (model, run.get("effort") or "default", "on" if run.get("fast") else "off")
            if item not in seen:
                settings.append(" / ".join(item))
                seen.add(item)
        lines.append(f"| {task['id']} | {task['state']} | {plan.get('goal', '')} | {task['fix_attempts']} | {task['change_rounds']} | {lead} | {lead_calls} | {assistant} | {'<br>'.join(settings)} |")
    lines += ["", "| Task | Run | Kind | Final state | Duration (minutes) | Commands | Small reads | Repeats | Full tests | Partial tests | Lint | Other commands | Thinking | Codex version |",
              "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    kinds = {"explore": "explore", "implement": "implement", "changes": "changes", "fix": "auto-fix", "report": "report retry", "minor_fix": "minor fix", "continue": "continue"}
    for run in state.get("runs", {}).values():
        if task_id and run.get("task") != task_id:
            continue
        stats = run.get("runstats") or {}
        duration = run.get("duration")
        minutes = f"{duration / 60:.1f}" if isinstance(duration, (int, float)) else "-"
        def command_minutes(name, run=run):
            value = run.get(f"{name}_seconds")
            return f"{value / 60:.1f}" if isinstance(value, (int, float)) else "-"
        lines.append(
            f"| {run.get('task') or '-'} | {run['id']} | {kinds.get(run.get('kind'), run.get('kind', '-'))} | "
            f"{run.get('result') or run.get('status', '-')} | {minutes} | {stats.get('commands', '-')} | "
            f"{stats.get('small_reads', '-')} | {stats.get('repeats', '-')} | "
            f"{command_minutes('full_tests')} | {command_minutes('partial_tests')} | {command_minutes('lint')} | "
            f"{command_minutes('other_cmds')} | {command_minutes('thinking')} | {run.get('codex_version') or '-'} |"
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
        return "Not recorded"
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
    parts = [f"This task {amount}"]
    context = []
    if "tokens" in accept_data and "window" in accept_data:
        context.append(
            f"Context {_compact_tokens(accept_data['tokens'])}/"
            f"{_compact_tokens(accept_data['window'])}"
        )
    if "five_hour" in accept_data:
        context.append(f"5h {_format_percent(accept_data['five_hour'])}")
    if "seven_day" in accept_data:
        context.append(f"7d {_format_percent(accept_data['seven_day'])}")
    if context:
        parts.append(f"At acceptance {context[0]}")
        parts.extend(context[1:])
    return " · ".join(parts)


def _lead_calls_display(state: dict, task_id: str) -> str:
    accept = state.get("lead_usage", {}).get(task_id)
    if not accept:
        return "-"
    accept_data = accept.get("data", {})
    explore = None
    if "started_at" in accept_data:
        explores = []
        for record in state.get("lead_usage_events", []):
            if record.get("seq", 0) >= accept.get("seq", 0):
                continue
            data = record.get("data", {})
            if data.get("at") != "explore" or data.get("started_at") != accept_data["started_at"]:
                continue
            owner = record.get("task")
            if owner is None:
                owner = _explore_snapshot_task(state, record.get("seq", 0))
            if owner == task_id:
                explores.append(record)
        explore = max(explores, key=lambda event: event.get("seq", 0), default=None)
    if not explore:
        return "-"
    before = explore.get("data", {})
    values = []
    for key in ("tool_calls", "requests"):
        if key in accept_data and key in before:
            values.append(str(accept_data[key] - before[key]))
        else:
            values.append("-")
    return " / ".join(values)


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
