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
            "accepted": "Accepted", "cancelled": "Cancelled", "taken_over": "Taken over"}
SESSION_LIMIT = 20

LEAD_GUIDE = """lyfusion is on: the Codex sidekick writes this project's code; you (the lead) own the result: plan each task completely, review it against the user's whole request, and fix or report any defect you find that breaks that request.
Run every command below in the foreground in Bash with timeout 600000; results print straight to the output. No run_in_background, Monitor, sleep or polling.
Exit code 3 is normal, not an error: after 9 minutes the command returns while the sidekick keeps working; an implementation usually needs one or two fusion-core wait calls. Messages the user sends while you wait are queued.
Choose a tier after a quick look at the code, not from the task wording alone:
  A. Do it yourself: a small change in a known place (about 2 files, 30 lines), no slow tests; questions and architecture advice; serial root-cause debugging.
  B. Delegate without exploring: you know which files change, however large the change; reading the code yourself to write the brief is still B. Start at step 2.
  C. Explore, then delegate: you do not yet know where the change goes, or still do not after reading.
Anything bigger than A (many files, mechanical refactors, slow tests) is delegated with B or C. Split large mechanical work into several tasks that each pass every check and are accepted on their own.
1. Explore (C only): fusion-core explore - <<'EOF' … EOF   The user's task verbatim, then at most 3 questions numbered Q1~Q3.
2. Delegate: fusion-core delegate - <<'EOF' plan EOF   Reuses the exploration thread.
   Line 1 is "# one-sentence goal", then the brief. Optional "## scope" and "## checks" sections hold one "- glob" or "- command" (exit code 0 expected) per line.
   The brief states constraints, edge cases, behaviour that must not change (including invariants near the change), facts the sidekick cannot see (local files, anything outside its sandbox), pitfalls specific to this task, exact test assertions, and done criteria that known environment limits cannot break; for fixtures, point at existing tests instead of writing test code.
   Write checks against outputs (command output, rendered text), not source wording: the sidekick will match wording literally. Make each check prove the result is true (the file exists, the count is right), not only its shape. Checks run from the station root in the system shell (cmd on Windows); put a long one in a script file and list - python "<absolute path>".
3. Revise: fusion-core revise - <<'EOF' feedback EOF   Free text; answer the sidekick's questions here too.
4. Accept: fusion-core accept   Merges, reruns checks, squashes to one commit, fast-forwards main. Chain it with the next task: accept && explore ….
   One small fix left? fusion-core accept --minor-fix "one sentence": the sidekick makes it; it is merged only if it touches files this task already changed, at most 20 lines, with green checks; otherwise you get a review pack, then revise or accept as usual.
Design decisions every task must follow go in fusion/decisions.md (edit it directly); delegate and revise commit it on its own first, then send it in full.
Abandon a task: fusion-core cancel. Sidekick keeps failing at one point you can finish faster: fusion-core takeover."""


def lead_guide(cfg: dict | None = None) -> str:
    """Render the lead guide with project settings."""
    from . import config as config_mod
    cfg = cfg or {"local": config_mod.DEFAULT_LOCAL, **config_mod.DEFAULT_CONFIG}
    wait_minutes = cfg.get("wait_minutes", config_mod.DEFAULT_CONFIG["wait_minutes"])
    if (not isinstance(wait_minutes, (int, float)) or isinstance(wait_minutes, bool)
            or not math.isfinite(wait_minutes) or wait_minutes < 0):
        wait_minutes = config_mod.DEFAULT_CONFIG["wait_minutes"]
    guide = LEAD_GUIDE.replace("9 minutes", f"{wait_minutes:g} minutes")
    return guide.replace("fusion-core ", CMD + " ")


def session_context(root, cfg, state, source=None) -> str:
    from . import config as config_mod
    from .prompts import model_notes
    model = cfg.get("local", {}).get("sidekick", {}).get("model", "")
    note = model_notes(root, model)["lead"]
    context = lead_guide(cfg)
    if note:
        context += f"\n\n## About your sidekick ({model})\n{note}"
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
    baseline = _lead_usage_baseline(state, task_id, accept)
    if baseline is not None and "cost_usd" in accept_data:
        delta = accept_data["cost_usd"] - baseline.get("cost_usd", 0.0)
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
    baseline = _lead_usage_baseline(state, task_id, accept)
    if baseline is None:
        return "-"
    values = []
    for key in ("tool_calls", "requests"):
        if key in accept_data:
            values.append(str(accept_data[key] - baseline.get(key, 0)))
        else:
            values.append("-")
    return " / ".join(values)


def _lead_usage_baseline(state: dict, task_id: str, accept: dict) -> dict | None:
    accept_data = accept.get("data", {})
    if "started_at" not in accept_data:
        return None
    earlier = [
        record for record in state.get("lead_usage_events", [])
        if record.get("seq", 0) < accept.get("seq", 0)
        and record.get("data", {}).get("started_at") == accept_data["started_at"]
    ]
    same_task_explores = []
    for record in earlier:
        data = record.get("data", {})
        if data.get("at") != "explore":
            continue
        owner = record.get("task")
        if owner is None:
            owner = _explore_snapshot_task(state, record.get("seq", 0))
        if owner == task_id:
            same_task_explores.append(record)
    baseline = max(same_task_explores, key=lambda event: event.get("seq", 0), default=None)
    if baseline is None:
        baseline = max(earlier, key=lambda event: event.get("seq", 0), default=None)
    return baseline.get("data", {}) if baseline else {}


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
