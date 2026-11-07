"""给 lead 看的文字:交接视图(三层)、状态、注入、通知、台账。只读状态,不写事件。"""
from __future__ import annotations

from pathlib import Path

from . import gitops
from .state import TERMINAL, active_task, current_station, open_debt, open_questions

STATE_CN = {"planned": "待开工", "running": "助手在做", "blocked": "等回答", "checking": "检查中",
            "in_review": "待审", "integrating": "验收中", "accepted": "已验收", "rejected": "已退回",
            "cancelled": "已取消"}
KIND_CN = {"implement": "实现", "fix": "修复", "changes": "按意见修改", "answer": "带着回答续做",
           "report": "补报告", "explore": "只读探索"}
SIGNAL_CN = {"check_failed": "检查失败", "blocked": "阻塞", "perceivable_touched": "改了用户能感知的文件",
             "violation": "违规", "stalled": "卡住"}
SESSION_LIMIT = 20

OLD_LEAD_GUIDE = """# Fusion 已打开(lyfusion v5.0.0-a)
你是 lead:理解用户、做判断、写计划、审查和验收。助手(Codex)在独立的工位目录里按任务单实现。
工具是 fusion_*(在延迟工具列表里时,先用 ToolSearch 搜 fusion 加载)。任务状态、助手会话、检查证据
都由引擎记录,你不用自己记会话编号或续用命令。

## 每个任务先用三句话分类
1. 用户能感知到什么变化?(体验)
2. 哪些地方要靠判断,换个人做可能不一样?(判断)
3. 剩下哪些是照着样子就能做的?(机械)
- 小事、或几乎全是判断:fusion_plan 写 "direct": true,自己做,做完 fusion_accept。
- 有成块的机械活:写派工的任务单。

## 写任务单(fusion_plan)
- 先把影响结果的决定记下来(fusion_intent:experience 体验 / interface 接口 / rule 规则 / constraint 约束,
  写理由;能写成检查命令的就写 check)。任务单的 decisions 引用它们。
- goal:用户能感知的写成「体验:……」。
- items:judgment 由你做;mechanical 派给助手,每个至少 1 条验收检查
  (command 带 expect;manual 写 look 看什么、pass 怎样算过、signer 谁签字)。
- bounds 三组都要写(可以是空列表):must 必须遵守、free 可以自己定、escalate 必须上报。
- 同类的活先自己做 1 个样例提交到 main,其余工作项写 follows,派工时在 exemplar 里给样例的提交。
- 允许助手改的测试写进 tests_may_change,并引用决定。
- 不确定代码现状时先 fusion_explore(最多 3 个问题),答案以通知送达。

## 派工以后
- fusion_delegate 派出后先做自己的 judgment 工作项。要等助手时,用 Bash 在后台运行 `fusion-core wait`
  (run_in_background):助手跑完、提阻塞问题、检查出结果时它会结束并唤醒你。不要反复调 fusion_status 轮询。
- 阻塞问题用 fusion_answer 回答;值得长期记住的,带 promote 升格为决定。
- 你改到助手正在改的文件时会有提示;验收时引擎会合并并重跑检查。

## 审查和验收
- fusion_review 默认第 2 层(检查、信号、决定债明细、关键文件的 diff);不够再看第 3 层(完整 diff、日志)。
- 决定债 = 助手自定的选择。每条都要处理:认可 ratify、升格 promote,或在 fusion_request_changes 里驳回 overrule。
- 修改意见每条写 text 和 expect(期望的结果)。同一任务最多 3 轮;再要改先问用户:继续、接管
  (fusion_takeover)还是退回(fusion_reject)。
- fusion_accept 点名候选(如 T3.c2):引擎合并 main、跑集成检查、压成一个提交并快进 main。
- signer 为 user 的人工检查:把用户的原话写进 note,by 写 user-via-lead。

## 边界
- 证据只认引擎跑出来的;不要在工位目录里改代码或提交。
- 违规(关证书检查、跳过钩子、改弱测试)不放行;确实要放行,先问用户,把用户原话写进 waive。
- 遇到权限、环境、账号问题,停下来告诉用户。"""

LEAD_GUIDE = """lyfusion 已开:这个项目的代码活交给 Codex 助手做,你(lead)只做 4 件事。
每条命令都在 Bash 里用 run_in_background 运行。命令自己等到有结果才结束,结束时会叫醒你:
不要开 Monitor、不要 sleep、不要轮询。醒来后直接读结果文件。
1. 探索:fusion-core explore - <<'EOF' …… EOF
   写用户的任务原话(一字不改)和你想知道的,最多 3 条,编号 Q1~Q3。结果:fusion/explore.md
2. 派工:fusion-core delegate - <<'EOF' {计划} EOF   续用探索的会话。结果:fusion/review.md
   计划是 JSON:{\"goal\": \"一句话\", \"brief\": \"Markdown 正文\", \"checks\": [{\"run\": \"命令\", \"expect\": 0}], \"scope\": [\"src/**\"]}
   checks、scope 可省。brief 推荐小标题:目标、决定、不要做的事、已知的坑。
3. 修改:fusion-core revise - <<'EOF' 修改意见 EOF   自由文字,助手的问题也在这里回答。结果:fusion/review.md
4. 验收:fusion-core accept   合并、重跑检查、压成 1 个提交、快进主分支。
跨任务都要守的设计决定写进 fusion/decisions.md(普通文件,直接编辑),引擎每次派工把全文带给助手。
审查包不够看时,用 Read 看具体文件。看进度 fusion-core status;放弃任务 fusion-core cancel。"""


def _short(text, n=80) -> str:
    text = str(text or "").replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _sig_line(sig) -> str:
    return f"[{SIGNAL_CN.get(sig['kind'], sig['kind'])}] {_short(sig.get('detail'), 200)}"


def _usage_line(s, tid) -> str | None:
    u = s["usage"].get(tid or "_")
    if not u:
        return None

    def fmt(b):
        total = b["input"] + b["output"]
        cache = b["cache_read"] / b["input"] if b["input"] else 0
        return f"{total / 1e6:.2f}M(缓存 {cache:.0%})"
    parts = []
    if "lead" in u:
        parts.append("lead " + fmt(u["lead"]))
    if "sidekick" in u:
        parts.append("助手 " + fmt(u["sidekick"]))
    return " · ".join(parts)


# ---------------- 交接视图 ----------------

def review(root: Path, cfg: dict, s: dict, t: dict, tier: int = 2) -> str:
    lines = [f"# {t['id']} · {STATE_CN.get(t['state'], t['state'])} · 任务单第 {t['version']} 版",
             f"目标:{t['plan']['goal']}"]
    cand = s["candidates"].get(t["latest"] or "")
    last_run = s["runs"][t["runs"][-1]] if t["runs"] else None
    if t["direct"]:
        lines.append("这是 direct 任务(lead 直接做),没有候选。做完用 fusion_accept。")
        if t.get("takeover_done"):
            d = t["takeover_done"]
            lines.append(f"接管时搬过来的文件:{', '.join(d.get('copied') or []) or '无'}")
            if d.get("conflicts"):
                lines.append(f"你改过、没有覆盖的文件(请手动对照 runs/{t['id']}-takeover.diff):"
                             + ", ".join(d["conflicts"]))
        return "\n".join(lines)
    if not cand:
        lines.append("还没有候选。")
        if last_run:
            lines.append(f"最近一次运行 {last_run['id']}({KIND_CN.get(last_run['kind'])}):"
                         f"{last_run['status']} {last_run.get('result') or ''}")
            if last_run.get("dir"):
                lines.append(f"日志:{last_run['dir']}")
        _waiting(lines, s, t)
        return "\n".join(lines)

    chk = cand.get("checks") or {}
    run = s["runs"].get(cand["run"]) or {}
    rep = run.get("report") or {}
    lines.append(f"候选 {cand['cand']}(提交 {cand['commit'][:10]},来自运行 {cand['run']}"
                 f"{',' + KIND_CN.get(run.get('kind'), '') if run.get('kind') else ''})")
    if len(t["candidates"]) > 1:
        prev = s["candidates"][t["candidates"][-2]]
        changed = [f["path"] for f in gitops.changed_files(root, prev["commit"], cand["commit"])]
        lines.append(f"和上一个候选 {prev['cand']} 相比改了:{', '.join(changed[:20]) or '无'}")

    # 第 1 层:摘要
    lines.append("\n## 检查")
    if not chk:
        lines.append("还没跑完检查。")
    else:
        lines.append(("全部通过" if chk.get("passed") else ("只有环境类错误" if chk.get("only_env") else "没有全部通过"))
                     + ("(重跑过)" if chk.get("recheck") else ""))
        for r in chk.get("results", []):
            mark = "通过" if r["passed"] else ("环境错误" if r.get("env_error") else "失败")
            extra = ",重跑过 1 次" if r.get("retried") else ""
            lines.append(f"- {r['name']}:{mark}({r['seconds']} 秒{extra})")
        if chk.get("not_run"):
            lines.append(f"- {chk.get('failures')}")
    sigs = [x for x in t["signals"] if x.get("cand") in (None, cand["cand"])][-8:]
    if sigs:
        lines.append("\n## 信号")
        lines += [f"- {_sig_line(x)}" for x in sigs]
    if rep:
        lines.append("\n## 助手的报告")
        lines.append(rep.get("summary") or "(没写摘要)")
        for it in rep.get("items") or []:
            if isinstance(it, dict):
                lines.append(f"- {it.get('id')}:{it.get('status')} {_short(it.get('note'), 160)}")
        decs = [d for d in rep.get("decisions") or [] if isinstance(d, dict)]
        if decs:
            lines.append("决定是怎么实现的:")
            for d in decs:
                dev = f"(偏离:{d['deviation']})" if d.get("deviation") else ""
                lines.append(f"- {d.get('ref')}:{_short(d.get('how'), 200)}{dev}")
        for key, label in (("assumptions", "假设"), ("downstream", "对下游的影响"), ("problems", "已知问题")):
            vals = rep.get(key) or []
            if vals:
                lines.append(f"{label}:" + ";".join(_short(v, 160) for v in vals))
    debt = open_debt(t)
    unsent = [d for d in t["debt"].values() if d["status"] == "overruled" and not d.get("sent")]
    lines.append(f"\n决定债:待处理 {len(debt)} 条" + (f";已驳回还没送给助手 {len(unsent)} 条" if unsent else ""))
    _waiting(lines, s, t)
    flagged = _flagged_files(t, chk)
    for key, label in (("out_of_scope", "超出文件范围"), ("tests_changed", "改了测试"),
                       ("suspicious", "可疑改动(构建、依赖、CI 配置)")):
        if chk.get(key):
            lines.append(f"{label}:{', '.join(chk[key][:20])}")
    if chk.get("urls"):
        lines.append("新加的网址:" + ", ".join(chk["urls"][:10]))
    use = _usage_line(s, t["id"])
    if use:
        lines.append(f"用量:{use}")
    if tier == 1:
        lines.append("\n(第 1 层。要看决定债明细和关键文件的 diff:tier 2)")
        return "\n".join(lines)

    # 第 2 层:决定债明细 + 关键文件的 diff
    if debt:
        lines.append("\n## 决定债明细")
        for d in debt:
            opts = f"(备选:{' / '.join(map(str, d['options']))})" if d.get("options") else ""
            lines.append(f"- {d['eid']}:{d['what']}{opts}")
            if d.get("why"):
                lines.append(f"  理由:{_short(d['why'], 200)}")
            if d.get("files"):
                lines.append(f"  文件:{', '.join(d['files'][:10])}")
    base = cand.get("base") or t["base"]
    if flagged:
        lines.append(f"\n## 关键文件的 diff({len(flagged)} 个)")
        lines.append("```diff")
        lines.append(gitops.diff_text(root, base, cand["commit"], flagged, max_chars=40000))
        lines.append("```")
    others = [p for p in chk.get("changed", []) if p not in flagged]
    if others:
        lines.append(f"其他改动的文件(diff 在第 3 层):{', '.join(others[:40])}")
    if tier == 2:
        lines.append("\n(第 2 层。完整 diff 和日志路径:tier 3)")
        return "\n".join(lines)

    # 第 3 层:完整 diff 和日志
    lines.append("\n## 完整 diff")
    lines.append("```diff")
    lines.append(gitops.diff_text(root, base, cand["commit"], max_chars=150000))
    lines.append("```")
    lines.append("\n## 日志")
    for rid in t["runs"]:
        r = s["runs"][rid]
        if r.get("dir"):
            lines.append(f"- {rid}({KIND_CN.get(r['kind'])},{r.get('result') or r['status']}):{r['dir']}")
    for r in chk.get("results", []):
        lines.append(f"- {r['name']}:{r['log']}")
    return "\n".join(lines)


def _flagged_files(t, chk) -> list[str]:
    """第 2 层要给 diff 的文件:judgment 工作项、用户能感知的、测试、被标出的、范围外的、可疑的。"""
    out = []
    for key in ("perceivable", "tests_changed", "out_of_scope", "suspicious"):
        out += chk.get(key) or []
    for v in chk.get("violations") or []:
        for p in str(v.get("where", "")).split(", "):
            if p in (chk.get("changed") or []):
                out.append(p)
    for d in t["debt"].values():
        if d["status"] == "open":
            out += [p for p in d.get("files") or [] if p in (chk.get("changed") or [])]
    return list(dict.fromkeys(out))


def _waiting(lines, s, t) -> None:
    qs = open_questions(s, t["id"])
    if qs:
        lines.append("\n## 待答问题")
        for q in qs:
            tag = "阻塞" if q["blocking"] else f"非阻塞,已按「{_short(q.get('proceeded_with'), 40)}」继续"
            opts = f" 选项:{' / '.join(map(str, q['options']))}" if q.get("options") else ""
            rec = f" 推荐:{q['recommendation']}" if q.get("recommendation") else ""
            lines.append(f"- {q['id']}({tag}):{q['text']}{opts}{rec}")


# ---------------- 状态 ----------------

def status(root: Path, cfg: dict, s: dict, target: str | None = None) -> str:
    if target and target.startswith("r") and target in s["runs"]:
        return _run_status(s, s["runs"][target])
    if target:
        t = s["tasks"].get(target)
        if not t:
            return f"没有任务或运行 {target}"
        return _task_status(s, t)
    lines = ["# Fusion 状态"]
    live = [t for t in s["tasks"].values() if t["state"] not in TERMINAL]
    if live:
        for t in live:
            lines.append("- " + task_line(s, t))
    else:
        lines.append("没有进行中的任务。")
    done = [t for t in s["tasks"].values() if t["state"] in TERMINAL][-5:]
    if done:
        lines.append("最近结束:" + ";".join(f"{t['id']} {STATE_CN[t['state']]}" for t in done))
    lines += station_lines(s)
    qs = open_questions(s)
    if qs:
        lines.append("待答问题:")
        lines += [f"- {q['id']}({q['task'] or '无任务'},{'阻塞' if q['blocking'] else '非阻塞'}):{_short(q['text'], 120)}"
                  for q in qs]
    answers = list(s["explore_answers"].items())[-3:]
    if answers:
        lines.append("最近的探索答案(全文:fusion_status 加运行编号):")
        lines += [f"- {rid}:{_short(a['answer'], 160)}" for rid, a in answers]
    if s["engine_errors"]:
        e = s["engine_errors"][-1]
        lines.append(f"引擎最近的错误({e['ts']}):{_short(e.get('error'), 200)}")
    active = [d for d in s["decisions"].values() if d["status"] == "active"]
    lines.append(f"有效决定 {len(active)} 条(全文 fusion/intent.md)")
    return "\n".join(lines)


def _run_status(s, r) -> str:
    lines = [f"# 运行 {r['id']} · {KIND_CN.get(r['kind'], r['kind'])} · {r['status']} {r.get('result') or ''}"]
    if r["kind"] == "explore":
        lines.append("问题:")
        lines += [f"{i}. {q}" for i, q in enumerate(r.get("questions") or [], 1)]
        a = s["explore_answers"].get(r["id"])
        lines.append("\n答案:\n" + (a["answer"] if a else "(还没有)"))
    if r.get("dir"):
        lines.append(f"\n日志:{r['dir']}")
    return "\n".join(lines)


def _task_status(s, t) -> str:
    lines = [f"# {t['id']} · {STATE_CN.get(t['state'], t['state'])} · 第 {t['version']} 版"
             + (" · direct" if t["direct"] else ""), f"目标:{t['plan']['goal']}"]
    for iid, it in t["items"].items():
        lines.append(f"- {iid} {it['type']} · {it['owner']} · {it['status']}:{_short(it.get('title'), 80)}")
    if t["runs"]:
        lines.append("运行:" + ";".join(
            f"{rid} {KIND_CN.get(s['runs'][rid]['kind'])} {s['runs'][rid].get('result') or s['runs'][rid]['status']}"
            for rid in t["runs"][-8:]))
    if t["candidates"]:
        lines.append(f"候选:{', '.join(t['candidates'])}(最新 {t['latest']})")
    lines.append(f"修复 {t['fix_attempts']} 次 · 修改意见 {t['change_rounds']} 轮 · 决定债待处理 {len(open_debt(t))} 条")
    for sig in t["signals"][-5:]:
        lines.append(f"- {_sig_line(sig)}")
    _waiting(lines, s, t)
    if t.get("integration") and not t["integration"].get("ok"):
        lines.append(f"上次验收没通过:{t['integration'].get('detail')}")
    use = _usage_line(s, t["id"])
    if use:
        lines.append(f"用量:{use}")
    return "\n".join(lines)


def task_line(s, t) -> str:
    bits = [f"{t['id']} {STATE_CN.get(t['state'], t['state'])}"]
    if t["state"] == "in_review" and t["latest"]:
        bits[0] += f"({t['latest']})"
    if t["state"] == "running" and t["active_run"]:
        r = s["runs"][t["active_run"]]
        bits[0] += f"({KIND_CN.get(r['kind'])} {r['id']})"
    qn = len(open_questions(s, t["id"], blocking=True))
    if qn:
        bits.append(f"{qn} 个问题待答")
    dn = len(open_debt(t))
    if dn:
        bits.append(f"决定债 {dn}")
    if t["direct"] and t["state"] == "planned":
        bits.append("lead 直接做")
    return " · ".join(bits) + f":{_short(t['plan']['goal'], 50)}"


def station_lines(s) -> list[str]:
    st = current_station(s)
    if not st:
        return ["工位:还没有(第一次派工或探索时建)"]
    thread = (st.get("thread") or "未开")[:8]
    lines = [f"工位 {st['name']}:{'忙' if st['status'] == 'busy' else '空闲'} · 模型 {st['model']}"
             f" · 会话 {thread} · 上下文约 {st.get('ctx_est', 0) // 1000}k · 做过 {', '.join(st['tasks']) or '无'}"]
    if st.get("predecessor"):
        prev = s["stations"].get(st["predecessor"]) or {}
        lines.append(f"  接替 {st['predecessor']}({prev.get('retired_reason') or '已退役'})")
    return lines


# ---------------- 注入 ----------------

def session_context(root: Path, cfg: dict, s: dict, source: str | None) -> str:
    return LEAD_GUIDE


def prompt_line(s) -> str:
    live = [t for t in s["tasks"].values() if t["state"] not in TERMINAL]
    if not live:
        return "Fusion:没有进行中的任务"
    return "Fusion:" + ";".join(task_line(s, t) for t in live[-2:])


def edit_hint(s, path: str, root: Path) -> str | None:
    from .util import any_match, norm
    try:
        rel = norm(str(Path(path).resolve().relative_to(root.resolve())))
    except ValueError:
        return None
    for t in s["tasks"].values():
        if t["state"] not in ("running", "blocked", "checking", "in_review", "integrating") or t["direct"]:
            continue
        globs = [g for it in t["items"].values() if it.get("owner") == "sidekick" and it["status"] == "delegated"
                 for g in it.get("files") or []]
        if any_match(rel, globs):
            return (f"Fusion 提示:{rel} 在 {t['id']} 派给助手的文件范围里,助手可能也在改。"
                    f"你可以继续改;验收时引擎会合并并重跑检查,冲突会告诉你。")
    return None


# ---------------- 通知(给 monitor) ----------------

def notifications(s, events: list[dict]) -> list[str]:
    out = []
    for e in events:
        t, d, tid = e["type"], e.get("data") or {}, e.get("task")
        task = s["tasks"].get(tid or "")
        if t == "question_asked" and d.get("blocking"):
            out.append(f"{tid} 的助手有阻塞问题 {d['qid']}:{_short(d['text'], 200)}。用 fusion_answer 回答")
        elif t == "signal" and d.get("kind") in ("check_failed", "violation", "stalled"):
            out.append(f"{tid} {_sig_line(d)}")
        elif t == "check_ran" and not d.get("recheck") and task and task["state"] == "in_review" \
                and task["latest"] == d.get("cand"):
            res = "检查全部通过" if d.get("passed") else "检查没有全部通过"
            extra = f",改了用户能感知的文件 {len(d.get('perceivable') or [])} 个" if d.get("perceivable") else ""
            out.append(f"{d['cand']} 待审:{res}{extra},决定债 {len(open_debt(task))} 条。用 fusion_review 看")
        elif t == "no_changes":
            out.append(f"{tid} 的助手说做完了,但没有改动任何文件。用 fusion_review 看报告")
        elif t == "explore_answered":
            out.append(f"探索 {d['run']} 有答案了:{_short(d.get('answer'), 160)}(全文:fusion_status {d['run']})")
        elif t == "integration_ran":
            if d.get("ok"):
                out.append(f"{tid} 已验收" + (f",main 到 {d['commit'][:10]}" if d.get("commit") else ""))
            else:
                out.append(f"{tid} 验收没通过:{_short(d.get('detail'), 300)}")
        elif t == "takeover_done":
            msg = f"{tid} 已接管:搬了 {len(d.get('copied') or [])} 个文件到你的工作目录(没提交)"
            if d.get("conflicts"):
                msg += f";你改过、没覆盖的:{', '.join(d['conflicts'][:10])}"
            out.append(msg)
        elif t == "engine_error":
            out.append(f"引擎出错:{_short(d.get('error'), 200)}(日志 {d.get('log')})")
    return ["[Fusion] " + x for x in out]


# ---------------- 台账 ----------------

def ledger(s, task: str | None = None) -> str:
    rows = ["| 任务 | 状态 | 运行 | 修复 | 修改轮 | 决定债(认可/升格/驳回/待处理) | lead | 助手 |",
            "|---|---|---|---|---|---|---|---|"]
    for t in s["tasks"].values():
        if task and t["id"] != task:
            continue
        cnt = {k: 0 for k in ("ratified", "promoted", "overruled", "open")}
        for d in t["debt"].values():
            cnt[d["status"]] = cnt.get(d["status"], 0) + 1
        u = s["usage"].get(t["id"], {})

        def tot(who):
            b = u.get(who)
            return f"{(b['input'] + b['output']) / 1e6:.2f}M" if b else "未知"
        rows.append(f"| {t['id']} | {STATE_CN[t['state']]} | {len(t['runs'])} | {t['fix_attempts']} | "
                    f"{t['change_rounds']} | {cnt['ratified']}/{cnt['promoted']}/{cnt['overruled']}/{cnt['open']} | "
                    f"{tot('lead')} | {tot('sidekick')} |")
    found = [(t["id"], f) for t in s["tasks"].values() for f in t["found"] if not task or t["id"] == task]
    if found:
        rows.append("\n修改意见是在看过哪几层之后提的:")
        rows += [f"- {tid} 第 {f.get('round')} 轮:看过第 {f.get('found', {}).get('tiers_viewed') or '无'} 层"
                 for tid, f in found]
    misses = [t for t in s["tasks"].values() if t["plan"].get("fixes")]
    if misses:
        rows.append("漏检(验收后才发现、开新任务修):" + ", ".join(f"{t['id']} 修 {t['plan']['fixes']}" for t in misses))
    return "\n".join(rows)
