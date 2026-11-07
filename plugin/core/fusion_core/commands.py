"""Public command actions. Events, rather than mutable state, are authoritative."""
from __future__ import annotations

from pathlib import Path

from . import config as config_mod
from . import store, validate, views
from .state import TERMINAL, active_task, replay
from .util import FusionError, git


class Ctx:
    def __init__(self, root: Path, actor: str = "lead"):
        self.root = Path(root)
        if not config_mod.is_fusion_project(self.root):
            raise FusionError("这个项目没有打开 Fusion。先运行 /fusion on")
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
        raise FusionError(f"任务 {task_id} 不存在")
    return task


def _wip_check(state: dict, excluding: str | None = None) -> None:
    busy = [t["id"] for t in state["tasks"].values() if t["id"] != excluding and t["state"] not in TERMINAL]
    if busy:
        raise FusionError(f"同一时刻只允许 1 个进行中的任务:{busy[-1]} 还没结束")


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
    """decisions.md 有改动就只提交这一个文件(检查点)。失败不挡派工,返回原因给 lead 看。"""
    if not (root / DECISIONS).exists():
        return None
    code, out, _ = git("status", "--porcelain", "--", DECISIONS, cwd=root, check=False)
    if code != 0 or not out.strip():
        return None
    git("add", "--", DECISIONS, cwd=root, check=False)
    code, _, err = git("commit", "-q", "-m", "fusion: 更新设计决定(decisions.md)", "--", DECISIONS,
                       cwd=root, check=False)
    return None if code == 0 else f"没能提交 {DECISIONS}:{err.strip()[:200]}"


def cmd_explore(ctx: Ctx, original: str) -> dict:
    if not isinstance(original, str) or not original.strip():
        raise FusionError("探索输入不能为空;请写任务原话和问题")
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
            raise FusionError(f"{tid} 还没有可派工的探索结果;请运行 explore 或选择已探索任务")
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
        raise FusionError("修改意见不能为空")
    state = replay(store.read(ctx.conn))
    task = current_task(state, task_id)
    if task is None:
        raise FusionError("没有进行中的任务")
    if task["state"] not in ("in_review", "blocked"):
        raise FusionError(f"{task['id']} 当前状态不能修改:{views.STATE_CN.get(task['state'], task['state'])}")
    limit = ctx.cfg.get("max_change_rounds", 3)
    if task["change_rounds"] >= limit:
        raise FusionError(f"{task['id']} 已经提过 {limit} 轮修改意见。按约定先停下来问用户:继续改,还是取消。", code=2)
    note = commit_decisions(ctx.root)
    rid = f"r{state['next_run']}"
    _emit(ctx, [{"type": "changes_requested", "task": task["id"],
                 "data": {"round": task["change_rounds"] + 1}},
                {"type": "run_requested", "task": task["id"],
                 "data": {"run": rid, "kind": "changes", "message": text.strip()}}])
    return {"task": task["id"], "run": rid, "round": task["change_rounds"] + 1, "decisions_note": note}


def cmd_accept(ctx: Ctx, task_id: str | None = None, waive: str | None = None) -> dict:
    state = replay(store.read(ctx.conn))
    task = current_task(state, task_id)
    if task is None:
        raise FusionError("没有进行中的任务")
    if task["state"] == "accepted":
        return {"task": task["id"], "commit": task["accepted_commit"]}
    if task["state"] == "blocked" and (task.get("latest_report") or {}).get("status") == "blocked":
        raise FusionError("助手停下来问了问题,先用 revise 回答")
    if task["state"] != "in_review":
        raise FusionError(f"{task['id']} 还没有可验收的审查结果")
    if not task.get("latest"):
        raise FusionError(f"{task['id']} 还没有候选可以验收")
    candidate = state["candidates"][task["latest"]]
    check = candidate.get("checks") or {}
    errors = []
    if not check.get("passed") and (not check.get("only_env") or not waive):
        errors.append("检查没有全部通过")
    if check.get("violations") and not waive:
        errors.append("有违规;验收要用 --waive 写明原因,有禁止操作时原因里要写用户的原话")
    if errors:
        raise FusionError("; ".join(errors))
    _emit(ctx, [{"type": "accept_requested", "task": task["id"],
                 "data": {"cand": task["latest"], "waive": waive}}])
    return {"task": task["id"], "candidate": task["latest"]}


def cmd_cancel(ctx: Ctx, task_id: str | None = None, reason: str | None = None) -> dict:
    state = replay(store.read(ctx.conn))
    task = current_task(state, task_id)
    if task is None:
        raise FusionError("没有进行中的任务")
    _emit(ctx, [{"type": "cancelled", "task": task["id"], "data": {"reason": reason or "lead 取消"}}])
    return {"task": task["id"]}


def cmd_lead_session(ctx: Ctx, session_id: str | None, source: str | None) -> None:
    state = ctx.state()
    previous = state["lead_sessions"][-1] if state["lead_sessions"] else None
    if previous and previous["session_id"] == session_id and previous["source"] == source:
        return
    _emit(ctx, [{"type": "lead_session", "data": {"session_id": session_id, "source": source}}])
