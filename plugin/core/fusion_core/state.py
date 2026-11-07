"""Replay durable events into the aq task, run, station, and candidate state."""
from __future__ import annotations

TERMINAL = ("accepted", "cancelled")


def empty() -> dict:
    return {"seq": 0, "tasks": {}, "next_task": 1, "runs": {}, "next_run": 1,
            "stations": {}, "station_seq": {}, "candidates": {}, "usage": {},
            "lead_sessions": [], "explore_answers": {}, "engine_errors": [], "next_question": 1}


def replay(events: list[dict], state: dict | None = None) -> dict:
    state = state or empty()
    for event in events:
        apply(state, event)
    return state


def _task(state, task_id):
    return state["tasks"][task_id]


def apply(state: dict, event: dict) -> None:
    state["seq"] = event["seq"]
    fn = HANDLERS.get(event["type"])
    if fn:
        fn(state, event, event.get("data") or {}, event.get("task"))
    # Unknown event types are intentionally ignored for old database compatibility.


def _task_created(s, e, d, tid):
    s["tasks"][tid] = {"id": tid, "version": 1, "plan": d.get("plan"), "state": d.get("state", "planned"),
                        "runs": [], "active_run": None, "candidates": [], "latest": None,
                        "fix_attempts": 0, "change_rounds": 0, "questions": [], "signals": [],
                        "branch": None, "base": None, "accepted_commit": None, "accept_cand": None,
                        "latest_report": None, "integration": None, "created": e["ts"], "closed": None}
    s["next_task"] = max(s["next_task"], int(tid[1:]) + 1)


def _plan_updated(s, e, d, tid):
    t = _task(s, tid)
    t["plan"], t["version"], t["state"] = d["plan"], d["version"], "planned"


def _lead_session(s, e, d, tid):
    s["lead_sessions"].append({"session_id": d.get("session_id"), "source": d.get("source"), "ts": e["ts"]})


def _run_requested(s, e, d, tid):
    rid = d["run"]
    run = {"id": rid, "task": tid, "kind": d["kind"], "message": d.get("message"),
           "questions": d.get("questions"), "status": "requested", "station": None, "pid": None,
           "dir": None, "result": None, "requested": e["ts"], "started": None, "ended": None,
           "usage": None, "ephemeral": False, "resumed": False}
    s["runs"][rid] = run
    s["next_run"] = max(s["next_run"], int(rid[1:]) + 1)
    if tid:
        task = _task(s, tid)
        task["runs"].append(rid)
        if d["kind"] == "explore":
            task["active_run"], task["state"] = rid, "exploring"
        else:
            task["active_run"], task["state"] = rid, "running"
            if d["kind"] == "fix":
                task["fix_attempts"] += 1
            elif d["kind"] != "report":
                task["fix_attempts"] = 0


def _station_created(s, e, d, tid):
    st = d["station"]
    s["stations"][st["name"]] = {**st, "thread": None, "status": "idle", "tasks": [], "files": [],
                                  "ctx_est": 0, "created": e["ts"]}
    line, number = st["name"].split("#")
    s["station_seq"][line] = max(s["station_seq"].get(line, 0), int(number))


def _station_retired(s, e, d, tid):
    st = s["stations"].get(d["station"])
    if st:
        st["status"], st["retired_reason"] = "retired", d.get("reason")


def _thread_bound(s, e, d, tid):
    if d.get("station") in s["stations"]:
        s["stations"][d["station"]]["thread"] = d.get("thread")


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
        task["base"] = task.get("base") or d.get("base")


def _add_usage(s, key, who, usage):
    bucket = s["usage"].setdefault(key or "_", {}).setdefault(who, {
        "input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "requests": 0})
    for k in bucket:
        bucket[k] += int(usage.get(k) or 0)


def _run_ended(s, e, d, tid):
    run = s["runs"][d["run"]]
    run.update(status="ended", result=d["result"], ended=e["ts"], usage=d.get("usage"),
               report=d.get("report"), problems=d.get("problems"))
    st = s["stations"].get(run.get("station") or "")
    if st and st["status"] == "busy":
        st["status"] = "idle"
        if d.get("ctx_est") is not None:
            st["ctx_est"] = d["ctx_est"]
        for path in d.get("files", []):
            if path not in st["files"]:
                st["files"].append(path)
    if d.get("usage"):
        _add_usage(s, tid, "sidekick", d["usage"])
    if not tid:
        return
    task = _task(s, tid)
    if run["kind"] == "explore":
        if task["active_run"] == run["id"]:
            task["active_run"] = None
        task["state"] = "explored" if d["result"] == "ok" else "blocked"
        return
    if task["active_run"] == run["id"]:
        task["active_run"] = None
    if task["state"] in TERMINAL:
        return
    if d["result"] == "blocked":
        task["state"] = "blocked"
        task["latest_report"] = d.get("report")
    elif d["result"] == "ok":
        task["state"] = "checking"
        task["latest_report"] = d.get("report")
    else:
        task["state"] = "in_review"


def _explore_answered(s, e, d, tid):
    s["explore_answers"][d["run"]] = {"answer": d.get("answer"), "task": tid, "ts": e["ts"]}


def _question_asked(s, e, d, tid):
    q = {**d, "status": "open", "answer": None, "asked": e["ts"]}
    s["tasks"][tid]["questions"].append(q)
    s["next_question"] = max(s["next_question"], int(d["qid"][1:]) + 1)


def _question_answered(s, e, d, tid):
    t = _task(s, tid)
    for q in t["questions"]:
        if q.get("id") == d.get("id"):
            q.update(status="answered", answer=d.get("answer"))


def _candidate_created(s, e, d, tid):
    s["candidates"][d["cand"]] = {**d, "task": tid, "checks": None, "created": e["ts"]}
    t = _task(s, tid)
    t["candidates"].append(d["cand"])
    t["latest"] = d["cand"]


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


def _changes_requested(s, e, d, tid):
    t = _task(s, tid)
    t["change_rounds"] = d.get("round", t["change_rounds"] + 1)


def _accept_requested(s, e, d, tid):
    t = _task(s, tid)
    t["state"], t["accept_cand"], t["waive"] = "integrating", d.get("cand"), d.get("waive")


def _integration_ran(s, e, d, tid):
    t = _task(s, tid)
    t["integration"] = d
    if not d.get("ok") and t["state"] == "integrating":
        t["state"], t["accept_cand"] = "in_review", None


def _accepted(s, e, d, tid):
    _task(s, tid).update(state="accepted", accepted_commit=d.get("commit"), closed=e["ts"])


def _cancelled(s, e, d, tid):
    _task(s, tid).update(state="cancelled", closed=e["ts"], close_reason=d.get("reason"))


def _cleaned(s, e, d, tid):
    _task(s, tid).update(cleaned=True, branch=None)


def _usage(s, e, d, tid):
    _add_usage(s, tid, d.get("who", "lead"), d)


def _no_changes(s, e, d, tid):
    task = _task(s, tid)
    if task["state"] == "checking":
        task["state"] = "in_review"


def _engine_error(s, e, d, tid):
    s["engine_errors"].append({"seq": e["seq"], "ts": e["ts"], **d})
    del s["engine_errors"][:-20]


HANDLERS = {
    "task_created": _task_created, "plan_updated": _plan_updated, "lead_session": _lead_session,
    "run_requested": _run_requested, "station_created": _station_created, "station_retired": _station_retired,
    "thread_bound": _thread_bound, "run_started": _run_started, "run_ended": _run_ended,
    "explore_answered": _explore_answered, "question_asked": _question_asked,
    "question_answered": _question_answered, "candidate_created": _candidate_created,
    "check_ran": _check_ran, "signal": _signal, "changes_requested": _changes_requested,
    "accept_requested": _accept_requested, "integration_ran": _integration_ran, "accepted": _accepted,
    "cancelled": _cancelled, "cleaned": _cleaned, "usage": _usage, "no_changes": _no_changes,
    "engine_error": _engine_error,
}


def active_task(s: dict) -> dict | None:
    live = [t for t in s["tasks"].values() if t["state"] not in TERMINAL]
    return live[-1] if live else None


def current_station(s: dict, line: str = "main") -> dict | None:
    live = [station for station in s["stations"].values()
            if station["line"] == line and station["status"] != "retired"]
    return live[-1] if live else None
