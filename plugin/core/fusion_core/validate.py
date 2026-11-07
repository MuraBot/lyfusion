"""校验任务单、意图决定、助手报告。出错时说清原因,让 lead 当场能改。"""
from __future__ import annotations

import re

from .state import decision_ref
from .util import FusionError, any_match, globs_overlap

TYPES = ("judgment", "mechanical", "verify", "explore")
CATEGORIES = ("experience", "interface", "rule", "constraint")
ITEM_ID = re.compile(r"^W\d+$")
CHECK_ID = re.compile(r"^C\d+$")


def _need(cond, msg, errors):
    if not cond:
        errors.append(msg)


def check_refs(s: dict, refs, errors, where="任务单") -> None:
    for ref in refs or []:
        dec, ver = decision_ref(s, ref)
        if dec is None:
            errors.append(f"{where}引用的决定 {ref} 不存在")
        elif dec["status"] != "active":
            errors.append(f"{where}引用的决定 {ref} 已被取代,请引用新的决定")
        elif ver != dec["version"]:
            errors.append(f"{where}引用的是 {ref},但 {dec['id']} 已经是第 {dec['version']} 版;请改成 {dec['id']}@{dec['version']}")


def pin_refs(s: dict, refs) -> list[str]:
    """把不带版本的引用补成当前版本:'D3' → 'D3@2'。"""
    out = []
    for ref in refs or []:
        dec, ver = decision_ref(s, ref)
        out.append(f"{dec['id']}@{ver}" if dec else ref)
    return out


def plan(s: dict, cfg: dict, p: dict, task_id: str | None = None) -> dict:
    errors: list[str] = []
    if not isinstance(p, dict):
        raise FusionError("任务单要是一个 JSON 对象")
    goal = (p.get("goal") or "").strip()
    _need(goal, "缺少 goal(目标)。用户能感知的写成「体验:……」", errors)
    direct = bool(p.get("direct"))
    items = p.get("items") or []
    checks = p.get("checks") or []
    check_ids = set()
    for c in checks:
        cid = c.get("id", "")
        _need(CHECK_ID.match(cid or ""), f"检查编号 {cid!r} 要写成 C1、C2……", errors)
        _need(cid not in check_ids, f"检查编号 {cid} 重复", errors)
        check_ids.add(cid)
        kind = c.get("kind")
        if kind == "command":
            _need(isinstance(c.get("run"), str) and c["run"].strip(), f"{cid}:command 检查要写 run(命令)", errors)
            c.setdefault("expect", {"exit": 0})
        elif kind == "manual":
            _need(c.get("look"), f"{cid}:manual 检查要写 look(看什么)", errors)
            _need(c.get("pass"), f"{cid}:manual 检查要写 pass(什么算通过)", errors)
            _need(c.get("signer") in ("lead", "user"), f"{cid}:manual 检查要写 signer:lead 或 user", errors)
        else:
            errors.append(f"{cid}:kind 只能是 command 或 manual")

    plan_refs = p.get("decisions") or []
    check_refs(s, plan_refs, errors)
    if not direct:
        _need(items, "派工的任务至少要有 1 个工作项;只想自己做就写 \"direct\": true", errors)
        b = p.get("bounds")
        _need(isinstance(b, dict) and all(isinstance(b.get(k), list) for k in ("must", "free", "escalate")),
              "bounds 要写三组边界(可以是空列表,但要写):must 必须遵守、free 可以自己定、escalate 必须上报", errors)
    seen = {}
    for it in items:
        iid = it.get("id", "")
        _need(ITEM_ID.match(iid or ""), f"工作项编号 {iid!r} 要写成 W1、W2……", errors)
        _need(iid not in seen, f"工作项编号 {iid} 重复", errors)
        seen[iid] = it
        typ, owner = it.get("type"), it.get("owner") or ("lead" if it.get("type") == "judgment" else "sidekick")
        it["owner"] = owner
        _need(typ in TYPES, f"{iid}:type 只能是 {'/'.join(TYPES)}", errors)
        _need(owner in ("lead", "sidekick"), f"{iid}:owner 只能是 lead 或 sidekick", errors)
        _need(it.get("title"), f"{iid}:要写 title(一句话说明)", errors)
        if direct:
            _need(owner == "lead", f"{iid}:direct 任务的工作项都由 lead 负责", errors)
        if typ == "judgment" and owner == "sidekick":
            errors.append(f"{iid}:judgment 工作项由 lead 负责。要派给助手,先用 intent 写成决定,再改成 mechanical 并引用它")
        if typ in ("mechanical", "judgment"):
            _need(it.get("files"), f"{iid}:要写 files(文件范围,glob)", errors)
        if typ == "mechanical":
            _need(it.get("checks"), f"{iid}:mechanical 工作项至少对应 1 条验收检查", errors)
        for cid in it.get("checks") or []:
            _need(cid in check_ids, f"{iid}:引用的检查 {cid} 不存在", errors)
        check_refs(s, it.get("decisions"), errors, where=f"{iid} ")
        perceivable = it.get("perceivable") or any(any_match(f, cfg.get("perceivable")) for f in it.get("files") or [])
        if perceivable and typ != "explore":
            refs = list(plan_refs) + list(it.get("decisions") or [])
            cats = [decision_ref(s, r)[0] for r in refs]
            _need(any(c and c["category"] == "experience" for c in cats),
                  f"{iid}:影响用户能感知的内容,至少引用 1 条 experience 决定(没有就先用 intent 新增)", errors)
            it["perceivable"] = True
    for iid, it in seen.items():
        f = it.get("follows")
        if f:
            src = seen.get(f)
            _need(src is not None, f"{iid}:follows 指向的 {f} 不存在", errors)
            if src:
                _need(src.get("owner") == "lead" and src.get("type") == "judgment",
                      f"{iid}:follows 指向的样例 {f} 要是 lead 负责的 judgment 工作项", errors)
    lead_files = [g for it in items if it.get("owner") == "lead" for g in it.get("files") or []]
    side_files = [g for it in items if it.get("owner") == "sidekick" for g in it.get("files") or []]
    if lead_files and side_files and globs_overlap(lead_files, side_files):
        follows_only = all(it.get("follows") for it in items if it.get("owner") == "sidekick")
        if not follows_only:
            errors.append("lead 和助手的工作项文件范围重叠;请拆开范围,或让助手的工作项 follows lead 的样例")
    for tm in p.get("tests_may_change") or []:
        _need(tm.get("glob"), "tests_may_change 每条要写 glob", errors)
        check_refs(s, [tm.get("decision")] if tm.get("decision") else [], errors, where="tests_may_change ")
        _need(tm.get("decision"), "tests_may_change 每条要引用一条决定(为什么允许改这个测试)", errors)
    if p.get("fixes"):
        _need(p["fixes"] in s["tasks"], f"fixes 指向的任务 {p['fixes']} 不存在", errors)
    if errors:
        raise FusionError("任务单没通过校验:\n- " + "\n- ".join(errors))
    out = dict(p)
    out["goal"], out["direct"] = goal, direct
    out["decisions"] = pin_refs(s, plan_refs)
    for it in items:
        it["decisions"] = pin_refs(s, it.get("decisions"))
    out["items"], out["checks"] = items, checks
    out.setdefault("bounds", {"must": [], "free": [], "escalate": []})
    out.setdefault("tests_may_change", [])
    return out


def decision(s: dict, ch: dict) -> tuple[dict, list[dict]]:
    """意图变更 → (新的决定, 受影响的决定列表)。"""
    op = ch.get("op", "add")
    errors: list[str] = []
    fields = ("content", "reason", "scope", "source", "examples", "counterexamples", "rejected", "check", "category")
    if op == "add":
        _need(ch.get("category") in CATEGORIES, f"category 只能是 {'/'.join(CATEGORIES)}", errors)
        _need(ch.get("content"), "要写 content(决定的内容)", errors)
        _need(ch.get("reason"), "要写 reason(为什么这样定)", errors)
        if errors:
            raise FusionError("意图决定没通过校验:\n- " + "\n- ".join(errors))
        did = f"D{s['next_decision']}"
        dec = {"id": did, "version": 1, "status": "active", "history": []}
        dec.update({k: ch.get(k) for k in fields if ch.get(k) is not None})
        dec.setdefault("scope", [])
        _check_cmd(dec, errors)
        if errors:
            raise FusionError("意图决定没通过校验:\n- " + "\n- ".join(errors))
        return dec, []
    did = ch.get("id")
    old = s["decisions"].get(did or "")
    if old is None:
        raise FusionError(f"决定 {did} 不存在")
    if old["status"] != "active":
        raise FusionError(f"决定 {did} 已经被取代,不能再改")
    _need(ch.get("reason"), "修改或取代决定要写 reason(为什么改)", errors)
    if errors:
        raise FusionError("意图决定没通过校验:\n- " + "\n- ".join(errors))
    dec = dict(old)
    dec["history"] = list(old.get("history", [])) + [{"version": old["version"], "content": old.get("content"),
                                                       "why_changed": ch["reason"]}]
    if op == "revise":
        for k in fields:
            if k in ch and k != "reason":
                dec[k] = ch[k]
        dec["version"] = old["version"] + 1
        _check_cmd(dec, errors)
    elif op == "supersede":
        dec["status"], dec["superseded_by"] = "superseded", ch.get("by")
        dec["version"] = old["version"] + 1
    else:
        raise FusionError("op 只能是 add、revise、supersede")
    if errors:
        raise FusionError("意图决定没通过校验:\n- " + "\n- ".join(errors))
    return dec, []


def _check_cmd(dec, errors):
    c = dec.get("check")
    if c is not None:
        _need(isinstance(c, dict) and c.get("run"), "check 要写成 {\"run\": 命令, \"expect\": {...}}", errors)
        if isinstance(c, dict):
            c.setdefault("expect", {"exit": 0})


def report(raw) -> tuple[dict, list[str]]:
    """校验助手报告。返回 (补齐后的报告, 问题列表)。"""
    problems = []
    if not isinstance(raw, dict):
        return {"status": "blocked", "summary": "", "questions": [], "choices": [],
                "problems": ["报告不是 JSON 对象"]}, ["报告不是 JSON 对象"]
    out = {k: raw.get(k) for k in ("status", "summary", "questions", "choices", "problems")}
    if out["status"] not in ("done", "blocked"):
        problems.append("status 要是 done 或 blocked")
        out["status"] = "done"
    if not isinstance(out["summary"], str) or not out["summary"].strip():
        problems.append("缺少 summary")
        out["summary"] = out["summary"] or ""
    for k in ("questions", "choices", "problems"):
        if out[k] is None:
            problems.append(f"缺少 {k}")
            out[k] = []
        elif not isinstance(out[k], list):
            problems.append(f"{k} 要是列表")
            out[k] = []
    for q in out["questions"]:
        if not isinstance(q, dict) or not q.get("text"):
            problems.append("questions 里每条要有 text")
    return out, problems
