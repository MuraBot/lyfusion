"""从事件重放出当前状态。状态是纯数据(dict),不是数据来源;事件库才是。

任务状态:
    planned → running → checking → in_review → integrating → accepted
    running ⇄ blocked(阻塞问题)     checking → running(检查失败,助手修)
    in_review → running(修改意见)   integrating → in_review(冲突或集成检查失败)
    终态:accepted、rejected、cancelled
"""
from __future__ import annotations

TERMINAL = ("accepted", "rejected", "cancelled")


def empty() -> dict:
    return {
        "seq": 0,
        "decisions": {}, "next_decision": 1,
        "tasks": {}, "next_task": 1,
        "runs": {}, "next_run": 1,
        "stations": {}, "station_seq": {},
        "questions": {}, "next_question": 1,
        "candidates": {},
        "usage": {},
        "lead_sessions": [],
        "explore_answers": {},
        "engine_errors": [],
    }


def replay(events: list[dict], state: dict | None = None) -> dict:
    s = state or empty()
    for e in events:
        apply(s, e)
    return s


def _task(s, tid):
    return s["tasks"][tid]


def _add_usage(s, key, who, u):
    bucket = s["usage"].setdefault(key or "_", {}).setdefault(who, {"input": 0, "output": 0, "cache_read": 0,
                                                                     "cache_write": 0, "requests": 0})
    for k in ("input", "output", "cache_read", "cache_write", "requests"):
        bucket[k] += int(u.get(k) or 0)


def apply(s: dict, e: dict) -> None:
    s["seq"] = e["seq"]
    t, d, tid = e["type"], e.get("data", {}), e.get("task")
    fn = HANDLERS.get(t)
    if fn:
        fn(s, e, d, tid)


def _task_planned(s, e, d, tid):
    plan = d["plan"]
    items = {}
    for it in plan.get("items", []):
        items[it["id"]] = {**it, "status": "todo", "done_commit": None}
    s["tasks"][tid] = {
        "id": tid, "version": d["version"], "plan": plan, "state": "planned",
        "direct": bool(plan.get("direct")), "items": items,
        "runs": [], "active_run": None, "candidates": [], "latest": None,
        "fix_attempts": 0, "change_rounds": 0,
        "debt": {}, "next_debt": 1, "questions": [], "signals": [], "manual": {},
        "branch": None, "base": None, "accepted_commit": None, "accept_cand": None,
        "reviews": [], "found": [], "created": e["ts"], "closed": None,
        "lead_session": d.get("lead_session"),
    }
    num = int(tid[1:])
    s["next_task"] = max(s["next_task"], num + 1)


def _plan_revised(s, e, d, tid):
    task = _task(s, tid)
    old = task["items"]
    task["plan"], task["version"] = d["plan"], d["version"]
    task["direct"] = bool(d["plan"].get("direct"))
    items = {}
    for it in d["plan"].get("items", []):
        prev = old.get(it["id"], {})
        items[it["id"]] = {**it, "status": prev.get("status", "todo"), "done_commit": prev.get("done_commit")}
    task["items"] = items


def _intent_changed(s, e, d, tid):
    dec = d["decision"]
    s["decisions"][dec["id"]] = dec
    num = int(dec["id"][1:])
    s["next_decision"] = max(s["next_decision"], num + 1)


def _lead_session(s, e, d, tid):
    s["lead_sessions"].append({"session_id": d.get("session_id"), "source": d.get("source"), "ts": e["ts"]})


def _item_done(s, e, d, tid):
    item = _task(s, tid)["items"][e["item"]]
    item["status"], item["done_commit"] = "done", d.get("commit")


def _run_requested(s, e, d, tid):
    run = {"id": d["run"], "task": tid, "kind": d["kind"], "items": d.get("items", []),
           "message": d.get("message"), "questions": d.get("questions"), "status": "requested",
           "station": None, "pid": None, "dir": None, "result": None, "requested": e["ts"],
           "started": None, "ended": None, "usage": None, "ephemeral": False}
    s["runs"][run["id"]] = run
    s["next_run"] = max(s["next_run"], int(run["id"][1:]) + 1)
    if tid:
        task = _task(s, tid)
        task["runs"].append(run["id"])
        if run["kind"] != "explore":
            task["active_run"] = run["id"]
            task["state"] = "running"
            for i in run["items"]:
                if i in task["items"]:
                    task["items"][i]["status"] = "delegated"
            if run["kind"] == "fix":
                task["fix_attempts"] += 1
            elif run["kind"] != "report":
                task["fix_attempts"] = 0


def _station_created(s, e, d, tid):
    st = d["station"]
    s["stations"][st["name"]] = {**st, "thread": None, "status": "idle", "tasks": [], "files": [],
                                 "ctx_est": 0, "created": e["ts"]}
    line, num = st["name"].split("#")
    s["station_seq"][line] = max(s["station_seq"].get(line, 0), int(num))


def _station_retired(s, e, d, tid):
    st = s["stations"].get(d["station"])
    if st:
        st["status"], st["retired_reason"] = "retired", d.get("reason")


def _thread_bound(s, e, d, tid):
    s["stations"][d["station"]]["thread"] = d["thread"]


def _run_started(s, e, d, tid):
    run = s["runs"][d["run"]]
    run.update(status="started", station=d.get("station"), pid=d.get("pid"), dir=d.get("dir"),
               started=e["ts"], ephemeral=bool(d.get("ephemeral")), base=d.get("base"),
               resumed=bool(d.get("resumed")))
    st = s["stations"].get(d.get("station") or "")
    if st:
        st["status"] = "busy"
        if d.get("briefed"):
            st["briefed"] = True
        if tid and tid not in st["tasks"]:
            st["tasks"].append(tid)
    if tid and d.get("branch"):
        task = _task(s, tid)
        task["branch"] = d["branch"]
        if not task["base"]:
            task["base"] = d.get("base")


def _run_ended(s, e, d, tid):
    run = s["runs"][d["run"]]
    run.update(status="ended", result=d["result"], ended=e["ts"], usage=d.get("usage"), report=d.get("report"),
               problems=d.get("problems"))
    st = s["stations"].get(run.get("station") or "")
    if st and st["status"] == "busy":
        st["status"] = "idle"
        if d.get("ctx_est") is not None:
            st["ctx_est"] = d["ctx_est"]
        for f in d.get("files", []):
            if f not in st["files"]:
                st["files"].append(f)
    if d.get("usage"):
        _add_usage(s, tid, "sidekick", d["usage"])
    if not tid or run["kind"] == "explore":
        return
    task = _task(s, tid)
    if task["active_run"] == run["id"]:
        task["active_run"] = None
    if task["state"] in TERMINAL:
        return
    res = d["result"]
    if res == "blocked":
        task["state"] = "blocked"
    elif res == "ok":
        task["state"] = "checking"
    else:  # failed / lost / cancelled
        task["state"] = "in_review"


def _explore_answered(s, e, d, tid):
    s["explore_answers"][d["run"]] = {"answer": d.get("answer"), "task": tid, "ts": e["ts"]}


def _question_asked(s, e, d, tid):
    q = {"id": d["qid"], "task": tid, "run": d.get("run"), "text": d["text"], "blocking": bool(d.get("blocking")),
         "options": d.get("options") or [], "recommendation": d.get("recommendation"),
         "proceeded_with": d.get("proceeded_with"), "status": "open", "answer": None, "decision": None,
         "asked": e["ts"]}
    s["questions"][q["id"]] = q
    s["next_question"] = max(s["next_question"], int(q["id"][1:]) + 1)
    if tid:
        _task(s, tid)["questions"].append(q["id"])


def _question_answered(s, e, d, tid):
    q = s["questions"][d["qid"]]
    q.update(status="answered", answer=d.get("answer"), decision=d.get("decision"))


def _debt_added(s, e, d, tid):
    task = _task(s, tid)
    task["debt"][d["eid"]] = {**d, "status": "open"}
    task["next_debt"] = max(task["next_debt"], int(d["eid"].split(".E")[1]) + 1)


def _debt_resolved(s, e, d, tid):
    debt = _task(s, tid)["debt"][d["eid"]]
    debt.update(status=d["verdict"], decision=d.get("decision"), note=d.get("note"))


def _candidate_created(s, e, d, tid):
    s["candidates"][d["cand"]] = {**d, "task": tid, "checks": None, "created": e["ts"]}
    task = _task(s, tid)
    task["candidates"].append(d["cand"])
    task["latest"] = d["cand"]


def _check_ran(s, e, d, tid):
    cand = s["candidates"].get(d.get("cand") or "")
    if cand is not None:
        cand["checks"] = d
    task = _task(s, tid)
    if task["state"] == "checking":
        task["state"] = "in_review"


def _signal(s, e, d, tid):
    if tid:
        _task(s, tid)["signals"].append({"kind": d["kind"], "detail": d.get("detail"), "cand": d.get("cand"),
                                         "seq": e["seq"]})


def _review_viewed(s, e, d, tid):
    _task(s, tid)["reviews"].append({"cand": d.get("cand"), "tier": d.get("tier"), "seq": e["seq"]})


def _changes_requested(s, e, d, tid):
    task = _task(s, tid)
    task["change_rounds"] = d.get("round", task["change_rounds"] + 1)
    task["found"].append({"cand": d.get("cand"), "found": d.get("found"), "comments": d.get("comments"),
                          "round": task["change_rounds"]})
    for o in d.get("overruled") or []:
        debt = task["debt"].get(o.get("eid"))
        if debt:
            debt["sent"] = True


def _manual_signed(s, e, d, tid):
    _task(s, tid)["manual"][d["check"]] = d


def _accept_requested(s, e, d, tid):
    task = _task(s, tid)
    task["state"], task["accept_cand"], task["waive"] = "integrating", d.get("cand"), d.get("waive")


def _integration_ran(s, e, d, tid):
    task = _task(s, tid)
    task["integration"] = d
    if not d.get("ok") and task["state"] == "integrating":
        task["state"] = "planned" if task["direct"] else "in_review"
        task["accept_cand"] = None


def _no_changes(s, e, d, tid):
    task = _task(s, tid)
    if task["state"] == "checking":
        task["state"] = "in_review"


def _cleaned(s, e, d, tid):
    task = _task(s, tid)
    task["cleaned"] = True
    task["branch"] = None


def _takeover_done(s, e, d, tid):
    task = _task(s, tid)
    task.update(takeover_done=d, cleaned=True, branch=None)


def _accepted(s, e, d, tid):
    task = _task(s, tid)
    task.update(state="accepted", accepted_commit=d.get("commit"), closed=e["ts"])
    for it in task["items"].values():
        if it["status"] != "done":
            it["status"] = "done"


def _rejected(s, e, d, tid):
    _task(s, tid).update(state="rejected", closed=e["ts"], close_reason=d.get("reason"))


def _cancelled(s, e, d, tid):
    _task(s, tid).update(state="cancelled", closed=e["ts"], close_reason=d.get("reason"))


def _takeover(s, e, d, tid):
    task = _task(s, tid)
    task.update(state="planned", direct=True, takeover=d)
    for i, it in task["items"].items():
        if it["status"] == "delegated":
            it["owner"], it["status"] = "lead", "todo"


def _engine_error(s, e, d, tid):
    s["engine_errors"].append({"seq": e["seq"], "ts": e["ts"], **d})
    del s["engine_errors"][:-20]


def _usage(s, e, d, tid):
    _add_usage(s, tid, d.get("who", "lead"), d)


HANDLERS = {
    "task_planned": _task_planned, "plan_revised": _plan_revised, "intent_changed": _intent_changed,
    "lead_session": _lead_session, "item_done": _item_done, "run_requested": _run_requested,
    "station_created": _station_created, "station_retired": _station_retired, "thread_bound": _thread_bound,
    "run_started": _run_started, "run_ended": _run_ended, "explore_answered": _explore_answered,
    "question_asked": _question_asked, "question_answered": _question_answered, "debt_added": _debt_added,
    "debt_resolved": _debt_resolved, "candidate_created": _candidate_created, "check_ran": _check_ran,
    "signal": _signal, "review_viewed": _review_viewed, "changes_requested": _changes_requested,
    "manual_signed": _manual_signed, "accept_requested": _accept_requested,
    "integration_ran": _integration_ran, "accepted": _accepted, "rejected": _rejected,
    "cancelled": _cancelled, "takeover": _takeover, "usage": _usage,
    "no_changes": _no_changes, "cleaned": _cleaned, "takeover_done": _takeover_done,
    "engine_error": _engine_error,
}


# ---- 常用查询 ----

def active_task(s: dict) -> dict | None:
    live = [t for t in s["tasks"].values() if t["state"] not in TERMINAL]
    return live[-1] if live else None


def open_questions(s: dict, task: str | None = None, blocking: bool | None = None) -> list[dict]:
    out = [q for q in s["questions"].values() if q["status"] == "open"]
    if task:
        out = [q for q in out if q["task"] == task]
    if blocking is not None:
        out = [q for q in out if q["blocking"] == blocking]
    return out


def open_debt(task: dict) -> list[dict]:
    return [x for x in task["debt"].values() if x["status"] == "open"]


def current_station(s: dict, line: str = "main") -> dict | None:
    live = [st for st in s["stations"].values() if st["line"] == line and st["status"] != "retired"]
    return live[-1] if live else None


def decision_ref(s: dict, ref: str) -> tuple[dict | None, int | None]:
    """'D12@2' → (决定, 引用的版本)。不带版本 = 当前版本。"""
    did, _, ver = ref.partition("@")
    dec = s["decisions"].get(did)
    return dec, (int(ver) if ver else (dec["version"] if dec else None))
