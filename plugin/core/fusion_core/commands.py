"""Public command actions. Events, rather than mutable state, are authoritative."""
from __future__ import annotations

from pathlib import Path

from . import config as config_mod
from . import gitops, store, validate, views
from .state import TERMINAL, active_task, replay
from .util import FusionError, git


class Ctx:
    def __init__(self, root: Path, actor: str = "lead"):
        self.root = Path(root)
        if not config_mod.is_fusion_project(self.root):
            raise FusionError("Fusion has not been enabled for this project. Run /fusion on first.")
        self.cfg = config_mod.load(self.root)
        self.conn = store.connect(self.root)
        self.actor = actor

    def state(self) -> dict:
        return replay(store.read(self.conn))

    def close(self):
        self.conn.close()


def _emit(ctx: Ctx, events: list[dict]) -> None:
    with store.transaction(ctx.conn):
        store.append(ctx.conn, events, ctx.actor)


def _task(state: dict, task_id: str) -> dict:
    task = state["tasks"].get(task_id or "")
    if task is None:
        raise FusionError(f"Task {task_id} does not exist")
    return task


def _wip_check(state: dict, excluding: str | None = None) -> None:
    busy = [t["id"] for t in state["tasks"].values() if t["id"] != excluding and t["state"] not in TERMINAL]
    if busy:
        raise FusionError(f"Only one task may be active at a time: {busy[-1]} is not finished")


def _new_task(ctx: Ctx, plan: dict | None, initial_state: str) -> str:
    s = replay(store.read(ctx.conn))
    _wip_check(s)
    tid = f"T{s['next_task']}"
    _emit(ctx, [{"type": "task_created", "task": tid,
                 "data": {"plan": plan, "state": initial_state}}])
    return tid


def current_task(state: dict, task_id: str | None = None) -> dict:
    if task_id:
        return _task(state, task_id)
    return active_task(state)


DECISIONS = "fusion/decisions.md"


def commit_decisions(root: Path) -> str | None:
    """Commit only decisions.md when it has changes (a checkpoint). Failure does not block delegation; return the reason for lead."""
    if not (root / DECISIONS).exists():
        return None
    code, out, _ = git("status", "--porcelain", "--", DECISIONS, cwd=root, check=False)
    if code != 0 or not out.strip():
        return None
    git("add", "--", DECISIONS, cwd=root, check=False)
    code, _, err = git("commit", "-q", "-m", "fusion: update design decisions (decisions.md)", "--", DECISIONS,
                       cwd=root, check=False)
    return None if code == 0 else f"Could not commit {DECISIONS}: {err.strip()[:200]}"


def cmd_explore(ctx: Ctx, original: str) -> dict:
    if not isinstance(original, str) or not original.strip():
        raise FusionError("Exploration input cannot be empty; provide the user's task and questions")
    tid = _new_task(ctx, None, "exploring")
    state = replay(store.read(ctx.conn))
    rid = f"r{state['next_run']}"
    _emit(ctx, [{"type": "run_requested", "task": tid,
                 "data": {"run": rid, "kind": "explore", "questions": [original]}}])
    return {"task": tid, "run": rid}


def cmd_delegate(ctx: Ctx, raw_plan: dict, task_id: str | None = None) -> dict:
    plan = validate.plan(raw_plan)
    state = replay(store.read(ctx.conn))
    if task_id:
        task = _task(state, task_id)
    else:
        task = next((t for t in reversed(list(state["tasks"].values())) if t["state"] == "explored"), None)
    if task is None:
        tid = _new_task(ctx, plan, "planned")
    else:
        tid = task["id"]
        if task["state"] != "explored":
            raise FusionError(f"{tid} has no exploration result to delegate yet; run explore or select an explored task")
        _wip_check(state, excluding=tid)
        _emit(ctx, [{"type": "plan_updated", "task": tid,
                     "data": {"plan": plan, "version": task["version"] + 1}}])
    note = commit_decisions(ctx.root)
    state = replay(store.read(ctx.conn))
    rid = f"r{state['next_run']}"
    _emit(ctx, [{"type": "run_requested", "task": tid,
                 "data": {"run": rid, "kind": "implement"}}])
    return {"task": tid, "run": rid, "decisions_note": note}


def cmd_revise(ctx: Ctx, task_id: str | None, text: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise FusionError("Revision request cannot be empty")
    state = replay(store.read(ctx.conn))
    task = current_task(state, task_id)
    if task is None:
        raise FusionError("There is no active task")
    active_run = state["runs"].get(task.get("active_run") or "")
    if task["state"] == "running" and active_run and active_run["kind"] in ("implement", "changes", "fix"):
        if active_run["status"] != "started":
            raise FusionError("The run has not started yet; run revise again later")
        if task.get("pending_revise"):
            raise FusionError(f"{task['id']} already has a revision request in progress; wait for it to start before revising")
        lead_text = text
        normalized = lead_text.strip()
        previous_text = active_run.get("lead_text", active_run.get("message")) or ""
        if active_run["kind"] == "changes" and previous_text.strip() == normalized:
            return {"task": task["id"], "run": active_run["id"], "continue_wait": True}
        limit = ctx.cfg.get("max_change_rounds", 3)
        if task["change_rounds"] >= limit:
            raise FusionError(f"{task['id']} already has {limit} revision rounds. Stop and ask the user whether to continue or cancel.", code=2)
        note = commit_decisions(ctx.root)
        rid = f"r{state['next_run']}"
        _emit(ctx, [{"type": "run_requested", "task": task["id"],
                     "data": {"run": rid, "kind": "changes", "interrupt": active_run["id"],
                              "lead_text": lead_text, "message": normalized}}])
        return {"task": task["id"], "run": rid, "interrupt": active_run["id"],
                "decisions_note": note}
    if task["state"] not in ("in_review", "blocked"):
        raise FusionError(f"{task['id']} cannot be revised in its current state: {views.STATE_LABEL.get(task['state'], task['state'])}")
    limit = ctx.cfg.get("max_change_rounds", 3)
    if task["change_rounds"] >= limit:
        raise FusionError(f"{task['id']} already has {limit} revision rounds. Stop and ask the user whether to continue or cancel.", code=2)
    note = commit_decisions(ctx.root)
    rid = f"r{state['next_run']}"
    _emit(ctx, [{"type": "changes_requested", "task": task["id"],
                 "data": {"round": task["change_rounds"] + 1}},
                {"type": "run_requested", "task": task["id"],
                 "data": {"run": rid, "kind": "changes", "message": text.strip(),
                          "lead_text": text}}])
    return {"task": task["id"], "run": rid, "round": task["change_rounds"] + 1, "decisions_note": note}


def cmd_accept(ctx: Ctx, task_id: str | None = None, waive: str | None = None,
               minor_fix: str | None = None) -> dict:
    if minor_fix is not None and waive is not None:
        raise FusionError("--minor-fix cannot be combined with --waive")
    if minor_fix is not None and (not isinstance(minor_fix, str) or not minor_fix.strip()):
        raise FusionError("--minor-fix must be non-empty")
    state = replay(store.read(ctx.conn))
    task = current_task(state, task_id)
    if task is None:
        raise FusionError("There is no active task")
    if task["state"] == "accepted":
        return {"task": task["id"], "commit": task["accepted_commit"]}
    if task["state"] == "blocked" and (task.get("latest_report") or {}).get("status") == "blocked":
        raise FusionError("The assistant stopped to ask a question; answer it with revise first")
    if task["state"] != "in_review":
        raise FusionError(f"{task['id']} has no review result to accept yet")
    if not task.get("latest"):
        raise FusionError(f"{task['id']} has no candidate to accept yet")
    candidate = state["candidates"][task["latest"]]
    check = candidate.get("checks") or {}
    if minor_fix is not None:
        limit = ctx.cfg.get("max_change_rounds", 3)
        if task["change_rounds"] >= limit:
            raise FusionError(f"{task['id']} already has {limit} revision rounds. Stop and ask the user whether to continue or cancel.", code=2)
        files = [item["path"] for item in gitops.changed_files(
            ctx.root, candidate["base"], candidate["commit"]
        )]
        rid = f"r{state['next_run']}"
        _emit(ctx, [
            {"type": "minor_fix_requested", "task": task["id"],
             "data": {"previous": task["latest"], "files": files, "run": rid}},
            {"type": "run_requested", "task": task["id"],
             "data": {"run": rid, "kind": "minor_fix", "message": minor_fix.strip()}},
        ])
        return {"task": task["id"], "candidate": task["latest"], "minor_fix": True}
    errors = []
    if not check.get("passed") and (not check.get("only_env") or not waive):
        errors.append("Not all checks passed")
    if check.get("violations") and not waive:
        errors.append("Violations were found; use --waive with a reason to accept. If a prohibited action was involved, include the user's exact words in the reason.")
    if errors:
        raise FusionError("; ".join(errors))
    _emit(ctx, [{"type": "accept_requested", "task": task["id"],
                 "data": {"cand": task["latest"], "waive": waive}}])
    return {"task": task["id"], "candidate": task["latest"]}


def cmd_cancel(ctx: Ctx, task_id: str | None = None, reason: str | None = None) -> dict:
    state = replay(store.read(ctx.conn))
    task = current_task(state, task_id)
    if task is None:
        raise FusionError("There is no active task")
    _emit(ctx, [{"type": "cancelled", "task": task["id"], "data": {"reason": reason or "Lead cancelled"}}])
    return {"task": task["id"]}


def cmd_lead_session(ctx: Ctx, session_id: str | None, source: str | None) -> None:
    if not session_id:
        return
    state = ctx.state()
    previous = state["lead_sessions"][-1] if state["lead_sessions"] else None
    if previous and previous["session_id"] == session_id and previous["source"] == source:
        return
    _emit(ctx, [{"type": "lead_session", "data": {"session_id": session_id, "source": source}}])
