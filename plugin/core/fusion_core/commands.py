"""lead 的命令。每条命令在一个写事务里完成:读状态 → 校验 → 追加事件。真正的动作(启动 Codex、git)由监督者做。"""
from __future__ import annotations

from pathlib import Path

from . import config as config_mod, store, validate, views
from .state import TERMINAL, open_debt, open_questions, replay
from .util import FusionError, git


class Ctx:
    def __init__(self, root: Path, actor: str = "lead"):
        self.root = Path(root)
        if not config_mod.is_fusion_project(self.root):
            raise FusionError("这个项目还没有打开 Fusion。先运行 /fusion on(或 fusion-core init)。")
        self.cfg = config_mod.load(self.root)
        self.conn = store.connect(self.root)
        self.actor = actor

    def state(self) -> dict:
        return replay(store.read(self.conn))

    def close(self):
        self.conn.close()


def _task(s, tid) -> dict:
    t = s["tasks"].get(tid or "")
    if not t:
        raise FusionError(f"任务 {tid} 不存在。用 status 看现有任务。")
    return t


def _need_state(task, allowed, action):
    if task["state"] not in allowed:
        raise FusionError(f"{task['id']} 现在是 {views.STATE_CN.get(task['state'], task['state'])},不能{action}。"
                          f"只有在 {'/'.join(views.STATE_CN.get(x, x) for x in allowed)} 时可以。")


def _evidence_fresh(ctx, task, cand) -> tuple[bool, str]:
    chk = cand.get("checks")
    if not chk:
        return False, "这个候选还没有检查结果"
    if chk.get("plan_version") != task["version"]:
        return False, "任务单改过版本,检查要重跑(引擎会自动重跑)"
    if chk.get("check_hash") != config_mod.check_hash(ctx.cfg):
        return False, "检查配置改过,检查要重跑(引擎会自动重跑)"
    return True, ""


def _stale_refs(s, task) -> list[str]:
    refs = list(task["plan"].get("decisions") or [])
    for it in task["items"].values():
        refs += it.get("decisions") or []
    out = []
    for r in refs:
        did, _, ver = r.partition("@")
        d = s["decisions"].get(did)
        if d and (d["status"] != "active" or (ver and int(ver) != d["version"])):
            out.append(f"{r}(现在是 {did}@{d['version']}{',已取代' if d['status'] != 'active' else ''})")
    return out


def _commit(ctx, events, s=None):
    with store.transaction(ctx.conn):
        return store.append(ctx.conn, events, ctx.actor)


# ---------------- 命令 ----------------

def cmd_intent(ctx: Ctx, change: dict) -> dict:
    with store.transaction(ctx.conn):
        s = replay(store.read(ctx.conn))
        dec, _ = validate.decision(s, change)
        store.append(ctx.conn, [{"type": "intent_changed", "data": {"decision": dec, "op": change.get("op", "add")}}],
                     ctx.actor)
    s = ctx.state()
    affected = [t["id"] for t in s["tasks"].values() if t["state"] not in TERMINAL and _stale_refs(s, t)]
    text = f"已记下 {dec['id']}@{dec['version']}({dec['status']})。"
    if affected:
        text += f" 这些进行中的任务引用了旧版本,验收前要用 plan 改引用:{', '.join(affected)}"
    return {"decision": f"{dec['id']}@{dec['version']}", "affected": affected, "text": text}


def cmd_plan(ctx: Ctx, plan: dict, task: str | None = None) -> dict:
    with store.transaction(ctx.conn):
        s = replay(store.read(ctx.conn))
        p = validate.plan(s, ctx.cfg, plan, task)
        if task:
            t = _task(s, task)
            _need_state(t, ("planned", "in_review"), "改任务单")
            ev = {"type": "plan_revised", "task": task, "data": {"plan": p, "version": t["version"] + 1}}
            tid, ver = task, t["version"] + 1
        else:
            tid, ver = f"T{s['next_task']}", 1
            ev = {"type": "task_planned", "task": tid, "data": {"plan": p, "version": 1}}
        store.append(ctx.conn, [ev], ctx.actor)
    kind = "直接做" if p["direct"] else "派工"
    side = [i["id"] for i in p["items"] if i["owner"] == "sidekick"]
    text = f"{tid} 第 {ver} 版任务单已记下({kind})。"
    if side:
        text += f" 可以派给助手的工作项:{', '.join(side)}。"
    if p["direct"]:
        text += " 做完后用 accept 结束,引擎会在你的工作目录上跑检查。"
    return {"task": tid, "version": ver, "text": text}


def cmd_explore(ctx: Ctx, questions: list[str], task: str | None = None) -> dict:
    questions = [q for q in (questions or []) if q and q.strip()]
    if not questions or len(questions) > 3:
        raise FusionError("explore 一次问 1~3 个问题")
    with store.transaction(ctx.conn):
        s = replay(store.read(ctx.conn))
        if task:
            _task(s, task)
        rid = f"r{s['next_run']}"
        store.append(ctx.conn, [{"type": "run_requested", "task": task,
                                 "data": {"run": rid, "kind": "explore", "questions": questions}}], ctx.actor)
    return {"run": rid, "text": f"已派出只读探索 {rid}。答案会以通知送达,也可以用 status 查看。"}


def cmd_delegate(ctx: Ctx, task: str, items: list[str], exemplar: dict | None = None, notes: str | None = None) -> dict:
    exemplar = exemplar or {}
    with store.transaction(ctx.conn):
        s = replay(store.read(ctx.conn))
        t = _task(s, task)
        if t["direct"]:
            raise FusionError(f"{task} 是 direct 任务(lead 直接做)。要派工,先用 plan 改成非 direct")
        _need_state(t, ("planned", "in_review"), "派工")
        others = [x for x in s["tasks"].values() if x["id"] != task and x["state"] not in TERMINAL
                  and not x["direct"] and x["runs"]]
        if others:
            raise FusionError(f"alpha 只有 1 条工作线:{others[0]['id']} 还没收尾(验收、退回或取消)。")
        items = items or [i for i, it in t["items"].items() if it["owner"] == "sidekick" and it["status"] == "todo"]
        if not items:
            raise FusionError("没有可以派的工作项")
        events = []
        for iid in items:
            it = t["items"].get(iid)
            if not it:
                raise FusionError(f"{task} 里没有工作项 {iid}")
            if it["owner"] != "sidekick":
                raise FusionError(f"{iid} 由 lead 负责,不能派给助手")
            f = it.get("follows")
            if f:
                src = t["items"][f]
                commit = exemplar.get(f) or src.get("done_commit")
                if not commit:
                    raise FusionError(f"{iid} 要照样例 {f} 做:请先提交样例,再在 exemplar 里写 {{\"{f}\": 提交}}")
                full = git("rev-parse", commit, cwd=ctx.root)
                code = git("merge-base", "--is-ancestor", full, ctx.cfg["base_branch"], cwd=ctx.root, check=False)[0]
                if code != 0:
                    raise FusionError(f"样例提交 {commit} 不在 {ctx.cfg['base_branch']} 上;请先把样例提交到 {ctx.cfg['base_branch']}")
                if src.get("done_commit") != full:
                    events.append({"type": "item_done", "task": task, "item": f, "data": {"commit": full}})
        rid = f"r{s['next_run']}"
        kind = "implement"
        events.append({"type": "run_requested", "task": task,
                       "data": {"run": rid, "kind": kind, "items": items, "message": notes}})
        store.append(ctx.conn, events, ctx.actor)
    return {"run": rid, "text": f"已派出 {rid}:{', '.join(items)}。助手跑完、提阻塞问题或检查出结果时会通知你。"}


def cmd_answer(ctx: Ctx, question: str, answer: str, promote: dict | None = None, agree: bool | None = None) -> dict:
    with store.transaction(ctx.conn):
        s = replay(store.read(ctx.conn))
        q = s["questions"].get(question or "")
        if not q:
            raise FusionError(f"问题 {question} 不存在")
        if q["status"] != "open":
            return {"text": f"{question} 已经回答过:{q['answer']}", "question": question}
        events = []
        did = None
        if promote:
            change = {"op": "add", "category": promote.get("category"),
                      "content": promote.get("content") or f"{q['text']} → {answer}",
                      "reason": promote.get("reason") or "回答助手的问题时定下", "scope": promote.get("scope") or []}
            dec, _ = validate.decision(s, change)
            did = f"{dec['id']}@{dec['version']}"
            events.append({"type": "intent_changed", "data": {"decision": dec, "op": "add"}})
        events.append({"type": "question_answered", "task": q["task"],
                       "data": {"qid": question, "answer": answer, "decision": did}})
        tid = q["task"]
        resumed = None
        changes = None
        if not q["blocking"] and tid:
            t = s["tasks"][tid]
            debt = next((d for d in t["debt"].values() if d.get("question") == question and d["status"] == "open"), None)
            if debt and agree is None:
                raise FusionError(f"{question} 是非阻塞问题,助手已按「{q.get('proceeded_with')}」继续。"
                                  "请写 agree:true(同意助手的选择)或 false(不同意,会变成修改意见)")
            if debt and agree:
                events.append({"type": "debt_resolved", "task": tid, "data": {
                    "eid": debt["eid"], "verdict": "promoted" if did else "ratified", "decision": did}})
            elif debt:
                events.append({"type": "debt_resolved", "task": tid, "data": {
                    "eid": debt["eid"], "verdict": "overruled", "decision": did, "note": f"lead 的回答:{answer}"}})
                if t["state"] == "in_review" and t["change_rounds"] < ctx.cfg.get("max_change_rounds", 3):
                    changes = f"r{s['next_run']}"
                    over = [{"eid": debt["eid"], "what": debt.get("what"), "note": f"lead 的回答:{answer}"}]
                    items = [i for i, it in t["items"].items() if it["owner"] == "sidekick" and it["status"] != "todo"]
                    events.append({"type": "changes_requested", "task": tid, "data": {
                        "cand": t["latest"], "round": t["change_rounds"] + 1, "comments": [], "overruled": over,
                        "found": {"tiers_viewed": sorted({r["tier"] for r in t["reviews"] if r["cand"] == t["latest"]}),
                                  "via": "answer"}}})
                    events.append({"type": "run_requested", "task": tid, "data": {
                        "run": changes, "kind": "changes", "items": items,
                        "message": {"comments": [], "overruled": over}}})
        if q["blocking"] and tid:
            t = s["tasks"][tid]
            rest = [x for x in open_questions(s, tid, blocking=True) if x["id"] != question]
            if t["state"] == "blocked" and not rest:
                answered = [x for x in s["questions"].values() if x["task"] == tid and x["blocking"]
                            and x["run"] == q["run"]]
                msgs = [{"text": x["text"], "answer": x["answer"] if x["id"] != question else answer} for x in answered]
                resumed = f"r{s['next_run']}"
                events.append({"type": "run_requested", "task": tid,
                               "data": {"run": resumed, "kind": "answer", "items": s["runs"][q["run"]]["items"],
                                        "message": msgs}})
        store.append(ctx.conn, events, ctx.actor)
    text = f"已回答 {question}。"
    if did:
        text += f" 并记成决定 {did}。"
    if resumed:
        text += f" 助手会接着做({resumed})。"
    if changes:
        text += f" 和助手的选择不同,已作为修改意见送出({changes})。"
    elif agree is False:
        text += " 和助手的选择不同,已记为驳回;任务进入待审后用 fusion_request_changes 送出(会自动带上)。"
    return {"question": question, "decision": did, "run": resumed or changes, "text": text}


def cmd_review(ctx: Ctx, task: str, tier: int = 2) -> dict:
    tier = int(tier or 2)
    if tier not in (1, 2, 3):
        raise FusionError("tier 只能是 1、2、3")
    s = ctx.state()
    t = _task(s, task)
    text = views.review(ctx.root, ctx.cfg, s, t, tier)
    if t["latest"]:
        _commit(ctx, [{"type": "review_viewed", "task": task, "data": {"cand": t["latest"], "tier": tier}}])
    return {"task": task, "tier": tier, "text": text}


def cmd_request_changes(ctx: Ctx, task: str, comments: list[dict], overrule: list[dict] | None = None) -> dict:
    comments, overrule = comments or [], overrule or []
    with store.transaction(ctx.conn):
        s = replay(store.read(ctx.conn))
        t = _task(s, task)
        _need_state(t, ("in_review",), "提修改意见")
        pending = [d for d in t["debt"].values() if d["status"] == "overruled" and not d.get("sent")]
        if not comments and not overrule and not pending:
            raise FusionError("至少写一条修改意见,或驳回一条自定的选择")
        for c in comments:
            if not c.get("text") or not c.get("expect"):
                raise FusionError("每条修改意见要写 text(问题)和 expect(期望的结果);ref 可选")
        limit = ctx.cfg.get("max_change_rounds", 3)
        if t["change_rounds"] >= limit:
            raise FusionError(f"{task} 已经提过 {limit} 轮修改意见。按约定先停下来问用户:继续改、接管,还是退回。")
        events, over = [], []
        for o in overrule:
            d = t["debt"].get(o.get("eid", ""))
            if not d:
                raise FusionError(f"自定的选择 {o.get('eid')} 不存在")
            events.append({"type": "debt_resolved", "task": task,
                           "data": {"eid": d["eid"], "verdict": "overruled", "note": o.get("note")}})
            over.append({"eid": d["eid"], "what": d.get("what"), "note": o.get("note")})
        for d in pending:
            if d["eid"] not in {o["eid"] for o in over}:
                over.append({"eid": d["eid"], "what": d.get("what"), "note": d.get("note")})
        tiers = sorted({r["tier"] for r in t["reviews"] if r["cand"] == t["latest"]})
        rid = f"r{s['next_run']}"
        rnd = t["change_rounds"] + 1
        events.append({"type": "changes_requested", "task": task,
                       "data": {"cand": t["latest"], "round": rnd, "comments": comments, "overruled": over,
                                "found": {"tiers_viewed": tiers}}})
        items = [i for i, it in t["items"].items() if it["owner"] == "sidekick" and it["status"] != "todo"]
        events.append({"type": "run_requested", "task": task,
                       "data": {"run": rid, "kind": "changes", "items": items,
                                "message": {"comments": comments, "overruled": over}}})
        store.append(ctx.conn, events, ctx.actor)
    return {"run": rid, "round": rnd, "text": f"第 {rnd} 轮修改意见已送出({rid})。"}


def cmd_accept(ctx: Ctx, task: str, candidate: str | None = None, ratify: list[str] | None = None,
               promote: list[dict] | None = None, manual: list[dict] | None = None, note: str | None = None,
               waive: str | None = None) -> dict:
    ratify, promote, manual = ratify or [], promote or [], manual or []
    with store.transaction(ctx.conn):
        s = replay(store.read(ctx.conn))
        t = _task(s, task)
        if t["state"] == "accepted":
            return {"text": f"{task} 已经验收过了(提交 {t['accepted_commit']})。", "task": task}
        events, errors = [], []
        stale = _stale_refs(s, t)
        if stale:
            errors.append("引用的决定有新版本,请先用 plan 改引用:" + "、".join(stale))
        checks = {c["id"]: c for c in t["plan"].get("checks", [])}
        signed = {m.get("check"): m for m in manual}
        for cid, c in checks.items():
            if c["kind"] != "manual":
                continue
            prior = t["manual"].get(cid)
            m = signed.get(cid)
            cand_id = candidate or t["latest"]
            if prior and prior.get("cand") == cand_id and prior.get("verdict") == "pass":
                continue
            if not m:
                errors.append(f"人工检查 {cid}({c['look']})还没签字;signer 是 {c['signer']}")
                continue
            if m.get("verdict", "pass") != "pass":
                errors.append(f"人工检查 {cid} 没通过,不能验收")
            if c["signer"] == "user" and m.get("by") not in ("user", "user-via-lead"):
                errors.append(f"{cid} 要用户签字:by 写 user-via-lead,并在 note 里原样写用户的话")
            events.append({"type": "manual_signed", "task": task,
                           "data": {"check": cid, "cand": cand_id, "by": m.get("by", "lead"),
                                    "note": m.get("note"), "verdict": m.get("verdict", "pass")}})
        if t["direct"]:
            _need_state(t, ("planned",), "验收")
            if errors:
                raise FusionError("还不能验收:\n- " + "\n- ".join(errors))
            events.append({"type": "accept_requested", "task": task, "data": {"cand": None, "note": note}})
            store.append(ctx.conn, events, ctx.actor)
            return {"task": task, "text": f"{task} 开始收尾:引擎在你的工作目录上跑检查,结果会通知你。"}
        _need_state(t, ("in_review",), "验收")
        cand_id = candidate or t["latest"]
        if not cand_id:
            raise FusionError(f"{task} 还没有候选可以验收")
        if cand_id != t["latest"]:
            errors.append(f"最新的候选是 {t['latest']},你点名的是 {cand_id}。请先审查最新的候选")
        cand = s["candidates"][cand_id]
        fresh, why = _evidence_fresh(ctx, t, cand)
        if not fresh:
            errors.append(why)
        chk = cand.get("checks") or {}
        if chk and not chk.get("passed"):
            if chk.get("only_env") and waive:
                pass
            else:
                errors.append("检查没有全部通过。" + ("只有环境类错误:确认无关后,用 waive 写明原因再验收。" if chk.get("only_env") else ""))
        if chk.get("violations") and not waive:
            errors.append("有违规(禁止操作或测试被改弱)。先提修改意见;确实要放行的,先问用户,再把用户的原话写进 waive")
        if open_questions(s, task, blocking=True):
            errors.append("还有没回答的阻塞问题")
        unsent = [d["eid"] for d in t["debt"].values() if d["status"] == "overruled" and not d.get("sent")]
        if unsent:
            errors.append("这些驳回还没送给助手,先用 fusion_request_changes 送出:" + "、".join(unsent))
        open_ids = {d["eid"] for d in open_debt(t)}
        handled = set(ratify) | {p.get("eid") for p in promote}
        unknown = handled - set(t["debt"])
        if unknown:
            errors.append("这些自定的选择不存在:" + "、".join(sorted(unknown)))
        missing = open_ids - handled
        if missing:
            errors.append("还有自定的选择没处理(认可 ratify、升格 promote,或在修改意见里驳回):" + "、".join(sorted(missing)))
        if errors:
            raise FusionError("还不能验收:\n- " + "\n- ".join(errors))
        for eid in ratify:
            events.append({"type": "debt_resolved", "task": task, "data": {"eid": eid, "verdict": "ratified"}})
        state_for_ids = s
        for p in promote:
            d = t["debt"][p["eid"]]
            change = {"op": "add", "category": p.get("category"), "content": p.get("content") or d.get("what"),
                      "reason": p.get("reason") or d.get("why") or "验收时认可助手的选择", "scope": d.get("files") or []}
            dec, _ = validate.decision(state_for_ids, change)
            events.append({"type": "intent_changed", "data": {"decision": dec, "op": "add"}})
            state_for_ids["next_decision"] += 1
            events.append({"type": "debt_resolved", "task": task,
                           "data": {"eid": p["eid"], "verdict": "promoted", "decision": f"{dec['id']}@1"}})
        events.append({"type": "accept_requested", "task": task,
                       "data": {"cand": cand_id, "note": note, "waive": waive}})
        store.append(ctx.conn, events, ctx.actor)
    return {"task": task, "candidate": cand_id,
            "text": f"{task} 开始验收 {cand_id}:合并 main、跑集成检查、快进。结果会通知你。"}


def cmd_reject(ctx: Ctx, task: str, reason: str) -> dict:
    if not reason:
        raise FusionError("退回要写 reason")
    with store.transaction(ctx.conn):
        s = replay(store.read(ctx.conn))
        t = _task(s, task)
        if t["state"] == "rejected":
            return {"text": f"{task} 已经退回过了。"}
        _need_state(t, ("in_review", "blocked", "planned"), "退回")
        store.append(ctx.conn, [{"type": "rejected", "task": task, "data": {"reason": reason}}], ctx.actor)
    return {"text": f"{task} 已退回:任务分支会删除,候选的 diff 和日志留在 fusion/runs/。"}


def cmd_cancel(ctx: Ctx, task: str, reason: str | None = None) -> dict:
    with store.transaction(ctx.conn):
        s = replay(store.read(ctx.conn))
        t = _task(s, task)
        if t["state"] == "cancelled":
            return {"text": f"{task} 已经取消过了。"}
        if t["state"] in TERMINAL:
            raise FusionError(f"{task} 已经{views.STATE_CN[t['state']]},不能取消")
        store.append(ctx.conn, [{"type": "cancelled", "task": task, "data": {"reason": reason}}], ctx.actor)
    return {"text": f"{task} 已取消:正在运行的助手会被停止。"}


def cmd_takeover(ctx: Ctx, task: str, bring: bool = True, reason: str | None = None) -> dict:
    if not reason:
        raise FusionError("接管要写 reason")
    with store.transaction(ctx.conn):
        s = replay(store.read(ctx.conn))
        t = _task(s, task)
        _need_state(t, ("running", "blocked", "in_review"), "接管")
        items = [i for i, it in t["items"].items() if it["status"] == "delegated"]
        store.append(ctx.conn, [{"type": "takeover", "task": task,
                                 "data": {"bring": bool(bring), "items": items, "reason": reason,
                                          "run": t["active_run"], "branch": t["branch"], "base": t["base"],
                                          "tip": t["latest"] and s["candidates"][t["latest"]]["commit"]}}], ctx.actor)
    return {"text": f"{task} 改由你来做(工作项 {', '.join(items) or '无'})。"
                    + ("助手的半成品会搬到你的工作目录(不提交)。" if bring else "") + "做完用 accept 结束。"}


def cmd_status(ctx: Ctx, task: str | None = None) -> dict:
    s = ctx.state()
    return {"text": views.status(ctx.root, ctx.cfg, s, task)}


def cmd_usage(ctx: Ctx, record: dict) -> dict:
    s = ctx.state()
    from .state import active_task
    t = active_task(s)
    _commit(ctx, [{"type": "usage", "task": t["id"] if t else None, "data": {"who": "lead", **record}}])
    return {"text": "ok"}


def cmd_lead_session(ctx: Ctx, session_id: str | None, source: str | None) -> None:
    s = ctx.state()
    last = s["lead_sessions"][-1] if s["lead_sessions"] else None
    if last and last["session_id"] == session_id and last["source"] == source:
        return
    _commit(ctx, [{"type": "lead_session", "data": {"session_id": session_id, "source": source}}])
