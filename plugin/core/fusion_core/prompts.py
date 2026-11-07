"""给助手的提示。规则短、任务单完整;同一个任务里续用时只发增量。"""
from __future__ import annotations

from . import intent as intent_doc

RULES = """你是 lyfusion 的助手,和一个 lead 合作:lead 负责设计和判断,你负责按任务单实现。
规则:
1. 只在当前目录(你的工位目录)里工作。不要 git 提交、不要切分支、不要推送,提交由引擎做。
2. 按任务单的三组边界办事:「必须遵守」不能违反;「可以自己定」由你决定;「必须上报」碰到就停下来提阻塞问题。
3. 有 follows 样例的工作项:先用 git show 读样例的提交,照它的结构、命名、风格扩展;偏离样例的地方写进 choices。
4. 没人要求、但你自己做了的选择(用户或其他模块可能在意的),全部写进 choices。没有就写空列表。
   每条:what 写你选的做法(一句话说清选了什么),options 写你考虑过但没选的其他做法,why 写理由,files 写涉及的文件。
5. 不确定、但猜错代价小的问题:按你的推荐继续,写进 questions(blocking=false,proceeded_with 写你选的)。
   猜错代价大,或碰到「必须上报」的情况:停下,不做依赖它的部分,questions 里写 blocking=true,然后结束本次运行。
6. 不要关闭证书检查、不要跳过钩子、不要为了通过检查删改原有测试。只能改任务单 tests_may_change 允许的测试。
7. 做完后跑项目的测试和 lint。最终回复只输出符合格式的 JSON 报告,不要别的文字。"""

REPORT_REMINDER = "最终回复只输出 JSON 报告(summary、items、decisions、choices、questions、assumptions、downstream、problems)。"


def _items_block(task: dict, ids: list[str]) -> str:
    out = []
    checks = {c["id"]: c for c in task["plan"].get("checks", [])}
    for iid in ids:
        it = task["items"][iid]
        out.append(f"- {iid}({it['type']}):{it['title']}")
        if it.get("files"):
            out.append(f"  文件范围:{', '.join(it['files'])}")
        if it.get("follows"):
            src = task["items"].get(it["follows"], {})
            commit = src.get("done_commit") or "(见 lead 的最新提交)"
            out.append(f"  照样例做:{it['follows']}「{src.get('title', '')}」,提交 {commit}")
        if it.get("decisions"):
            out.append(f"  引用的决定:{', '.join(it['decisions'])}")
        for cid in it.get("checks") or []:
            c = checks.get(cid)
            if not c:
                continue
            if c["kind"] == "command":
                out.append(f"  验收检查 {cid}:`{c['run']}`(期望 {c.get('expect')})")
            else:
                out.append(f"  人工检查 {cid}:看 {c['look']};通过标准:{c['pass']}")
        if it.get("notes"):
            out.append(f"  说明:{it['notes']}")
    return "\n".join(out)


def task_prompt(state: dict, cfg: dict, task: dict, items: list[str], handoff: str | None, first: bool) -> str:
    p = task["plan"]
    refs = list(dict.fromkeys(list(p.get("decisions") or []) +
                              [r for i in items for r in task["items"][i].get("decisions") or []]))
    b = p.get("bounds") or {}
    parts = []
    if first:
        parts.append(RULES)
    if handoff:
        parts.append("## 上一个工位的交接摘要(由引擎整理)\n" + handoff)
    parts.append(f"## 任务 {task['id']}\n目标:{p['goal']}")
    parts.append("## 三组边界\n"
                 + "必须遵守:\n" + "\n".join(f"- {x}" for x in b.get("must") or ["(无)"]) + "\n"
                 + "可以自己定:\n" + "\n".join(f"- {x}" for x in b.get("free") or ["(无)"]) + "\n"
                 + "必须上报(碰到就提阻塞问题):\n" + "\n".join(f"- {x}" for x in b.get("escalate") or ["(无)"]))
    parts.append("## 本次要做的工作项\n" + _items_block(task, items))
    if refs:
        parts.append("## 相关决定(全文)\n" + intent_doc.for_prompt(state, refs))
    if p.get("tests_may_change"):
        parts.append("## 允许修改的测试\n" + "\n".join(f"- {t['glob']}(依据 {t['decision']})" for t in p["tests_may_change"]))
    cmds = [x for x in (cfg.get("test"), cfg.get("lint")) if x]
    if cmds:
        parts.append("## 项目的测试和 lint\n" + "\n".join(f"- `{c}`" for c in cmds))
    if p.get("notes"):
        parts.append("## lead 的补充说明\n" + p["notes"])
    if not first:
        parts.append(REPORT_REMINDER)
    return "\n\n".join(parts)


def fix_prompt(failures: str) -> str:
    return ("## 检查没有通过\n下面是引擎跑出来的失败输出。请修好,然后再跑一遍测试。"
            "不要改弱原有测试。\n\n" + failures + "\n\n" + REPORT_REMINDER)


def changes_prompt(comments: list[dict], overruled: list[dict]) -> str:
    lines = ["## lead 的修改意见"]
    for c in comments:
        ref = f"[{c['ref']}] " if c.get("ref") else ""
        lines.append(f"- {ref}{c['text']}")
        if c.get("expect"):
            lines.append(f"  期望的结果:{c['expect']}")
    for o in overruled:
        lines.append(f"- 驳回你自定的选择 {o['eid']}:{o.get('what', '')}。{o.get('note') or ''}")
    lines += ["", REPORT_REMINDER]
    return "\n".join(lines)


def answer_prompt(answers: list[dict]) -> str:
    lines = ["## 你的阻塞问题有回答了"]
    for a in answers:
        lines.append(f"- 问:{a['text']}\n  答:{a['answer']}")
    lines += ["", "请按回答继续做完。", REPORT_REMINDER]
    return "\n".join(lines)


def explore_prompt(questions: list[str], task: dict | None) -> str:
    lines = ["你是 lyfusion 的助手。这是只读探索:只读代码、不要修改任何文件。",
             "请逐条回答下面的问题。回答要具体:写出文件路径和行号、现有约定、容易踩的坑。"]
    if task:
        lines.append(f"背景:任务 {task['id']},目标:{task['plan']['goal']}")
    lines.append("")
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")
    return "\n".join(lines)


def handoff_summary(state: dict, old: dict, refs: list[str]) -> str:
    """换工位时由引擎拼交接摘要,不让臃肿的旧会话自己写。"""
    lines = [f"上一个工位 {old['name']} 做过的任务:{', '.join(old['tasks']) or '(无)'}"]
    if old.get("files"):
        lines.append("改过的文件:" + ", ".join(old["files"][:60]) + ("……" if len(old["files"]) > 60 else ""))
    for tid in old["tasks"][-3:]:
        t = state["tasks"].get(tid)
        if not t:
            continue
        lines.append(f"- {tid}({t['state']}):{t['plan']['goal']}")
        for e in [x for x in t["debt"].values() if x["status"] == "open"]:
            lines.append(f"  未处理的自定选择 {e['eid']}:{e.get('what')}")
        for rid in t["runs"][-1:]:
            rep = (state["runs"][rid].get("report") or {})
            for prob in rep.get("problems") or []:
                lines.append(f"  已知问题:{prob}")
    if refs:
        lines.append("\n当前有效的相关决定:\n" + intent_doc.for_prompt(state, refs))
    return "\n".join(lines)
