#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""派工台账:记录每次运行、模块审查、试玩 bug 和 lead 的 token,算出各模型的表现,给出自主级别建议。试点版。

台账在项目根目录的 ledger.jsonl,一行一条,只增不改。只使用 Python 标准库。
- 助手、审查者的每次运行由派工脚本自动记一行(record)。
- lead 记程序看不到的事:模块审查结论(review)、试玩 bug(bug)、自己的 token(lead)、
  Lily 的打分(score)、越界或接手这类情况(flag)。

用法:
    python tools/ledger.py show [--by model|agent|kind]    汇总
    python tools/ledger.py level                           按台账建议每个"模型 · 模块"的自主级别
    python tools/ledger.py review --task T5 --result pass --findings 0    同时运行 progress.py set-review
    python tools/ledger.py bug --task T5 [--count 2] --note "敲不动"
    python tools/ledger.py lead --milestone M3 --session 会话编号 [--task T5] --calls 40 --tokens-in 1200 ...    记会话的累计读数
    python tools/ledger.py flag --task T5 --flag 接手 --signal 超预估 --note "用了 3 倍 token"
    python tools/ledger.py score --task T5 --score 6.5 [--delivery 4.5 --work 3]    Lily 的打分。花费和分数用 viewer/pareto-viewer.html 看
    python tools/ledger.py record ...                      派工脚本调用,一般不用手动运行
"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROLES = ["助手", "探索", "审查", "预检", "前端", "调研"]
FLAGS = ["越界", "谎报", "改了测试", "环境", "接手"]
SIGNALS = ["测试修2次", "超预估", "同类意见2次", "要改验收"]
# 起始级别(Lily 2026-10-27):gpt-6.1-sol 从 L3 起步,其他模型从 L2 起步
START_LEVELS = {"gpt-6.1-sol": 3}
DEFAULT_LEVEL = 2
# 升降级(Lily 2026-11-02):连续 2 个模块第 1 次审查就通过、试玩 bug 少于 2 个,升 1 级;接手信号超过 1 次,降 1 级
UP_STREAK = 2
MAX_BUGS = 1
DOWN_SIGNALS = 2


def fail(msg):
    print("错误:%s" % msg, file=sys.stderr)
    sys.exit(1)


def main_root():
    """主项目文件夹。在 git 工作目录里运行时,取主仓库,台账只有一份。"""
    try:
        out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             cwd=str(HERE), capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).parent
    except (OSError, subprocess.SubprocessError):
        pass
    return HERE.parent


ROOT = main_root()


def read_rows():
    path = ROOT / "ledger.jsonl"
    rows = []
    if not path.exists():
        return rows
    for i, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                fail("ledger.jsonl 第 %d 行不是合法的 JSON:%s。台账只增不改,请恢复这一行。" % (i, e.msg))
    return rows


def write_row(row):
    read_rows()  # 先确认现有内容没坏
    row = dict({"time": datetime.datetime.now().isoformat(timespec="seconds")}, **row)
    with open(ROOT / "ledger.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def cmd_record(a):
    # Codex 续用会话时报的是整个会话的累计用量(CraftTax 对比实验 2026-11-02 发现)。记与上次的差值,累计值另存
    cum = {"tokensIn": a.tokens_in, "tokensCached": a.tokens_cached, "tokensOut": a.tokens_out}
    prev = [r for r in read_rows() if r.get("kind") == "run" and a.session and r.get("session") == a.session]
    last = prev[-1].get("cum") if prev else None
    if last and all(cum[k] >= last[k] for k in cum):
        delta = {k: cum[k] - last[k] for k in cum}
    else:
        delta = cum
    row = write_row(dict({"kind": "run", "task": a.task, "role": a.role, "agent": a.agent, "model": a.model,
                          "effort": a.effort or "default", "session": a.session or "", "module": a.module or "",
                          "level": a.level or "", "tier": a.tier or "", "run": a.run}, **delta, cum=cum, note=a.note or ""))
    print("台账:%s %s 第 %d 次运行 · %s · 输入 %d" % (row["task"], row["role"], row["run"], row["model"], row["tokensIn"]))


def cmd_review(a):
    # 先改进度:progress.py 拒绝时(例如 lead 记 pass 没写理由),台账也不记
    cmd = [sys.executable, str(ROOT / "tools" / "progress.py"), "set-review", a.task, a.result]
    if a.by:
        cmd += ["--by", a.by]
    if a.note:
        cmd += ["--note", a.note]
    r = subprocess.run(cmd, cwd=str(ROOT))
    if r.returncode != 0:
        sys.exit(r.returncode)
    n = sum(1 for x in read_rows() if x.get("kind") == "review" and x["task"] == a.task) + 1
    row = write_row({"kind": "review", "task": a.task, "result": a.result, "findings": a.findings,
                     "by": a.by or "reviewer", "note": a.note or ""})
    print("台账:%s 第 %d 次模块审查 %s,发现 %d 条" % (row["task"], n, row["result"], row["findings"]))


def cmd_bug(a):
    row = write_row({"kind": "bug", "task": a.task, "count": a.count, "note": a.note or ""})
    print("台账:%s 记了 %d 个试玩 bug" % (row["task"], row["count"]))


def cmd_lead(a):
    row = write_row({"kind": "lead", "milestone": a.milestone, "session": a.session, "task": a.task or "", "tokensIn": a.tokens_in,
                     "tokensCached": a.tokens_cached, "tokensOut": a.tokens_out, "calls": a.calls,
                     "context": a.context, "costUsd": a.cost_usd, "note": a.note or ""})
    print("台账:lead %s 会话 %s 的用量读数 · 缓存读取 %d" % (row["milestone"], row["session"], row["tokensCached"]))


def half_point(s):
    """交付分、作品分:1~5,可以打半分(HEX M1 Lily 打了交付 4.5)"""
    v = float(s)
    if not (1 <= v <= 5 and v * 2 == int(v * 2)):
        raise argparse.ArgumentTypeError("是 1~5 分,可以打半分,例如 4.5")
    return v


def cmd_score(a):
    if a.score is None and (a.delivery is None or a.work is None):
        sys.exit("要给 --score,或者同时给 --delivery 和 --work。")
    if a.score is not None and not 0 <= a.score <= 10:
        sys.exit("--score 是 0~10 分。")
    row = write_row({"kind": "score", "task": a.task, "label": a.label or "", "score": a.score, "delivery": a.delivery,
                     "work": a.work, "note": a.note or ""})
    print("台账:%s 打分 %s,交付分 %s,作品分 %s" % (row["task"], row["score"], row["delivery"], row["work"]))


def cmd_flag(a):
    if a.flag == "接手" and not a.signal:
        fail("记「接手」要写 --signal:%s" % "、".join(SIGNALS))
    row = write_row({"kind": "flag", "task": a.task, "flag": a.flag, "signal": a.signal or "", "note": a.note or ""})
    print("台账:%s 记了「%s」%s" % (row["task"], row["flag"], ("(%s)" % row["signal"]) if row["signal"] else ""))


def owners(rows):
    """任务 → 助手的 (模型, 模块, 工具)。取这个任务第一次助手运行的记录。"""
    out = {}
    for r in rows:
        if r.get("kind") == "run" and r["role"] in ("助手", "前端") and r["task"] not in out:
            out[r["task"]] = (r["model"], r.get("module") or "未分模块", r["agent"])
    return out


def task_metrics(task, rows):
    reviews = [r for r in rows if r.get("kind") == "review" and r["task"] == task]
    runs = [r for r in rows if r.get("kind") == "run" and r["task"] == task]
    return {"reviewed": 1 if reviews else 0, "firstOk": 1 if reviews and reviews[0]["result"] == "pass" else 0,
            "rounds": len(reviews), "findings": sum(r.get("findings", 0) for r in reviews),
            "bugs": sum(r.get("count", 1) for r in rows if r.get("kind") == "bug" and r["task"] == task),
            "tokensIn": sum(r["tokensIn"] for r in runs), "tokensCached": sum(r.get("tokensCached", 0) for r in runs),
            "takeover": sum(1 for r in rows if r.get("kind") == "flag" and r["task"] == task and r["flag"] == "接手"),
            "firstReview": reviews[0]["time"] if reviews else ""}


def lead_usage(rows):
    """里程碑 → lead 的用量。同一个会话记了多次读数时取最后减最初;只有 1 次时,按新会话从 0 算。"""
    by = {}
    for r in rows:
        if r.get("kind") == "lead":
            by.setdefault((r["milestone"], r["session"]), []).append(r)
    out = {}
    for (ms, _), rs in by.items():
        keys = ("tokensIn", "tokensCached", "tokensOut", "calls")
        d = {k: rs[-1][k] - (rs[0][k] if len(rs) > 1 else 0) for k in keys}
        tot = out.setdefault(ms, dict.fromkeys(keys, 0))
        for k in keys:
            tot[k] += d[k]
    return out


def lead_segments(rows):
    """每次读数和同一会话上一次读数的差,按记读数时写的任务分段。会话的第 1 次读数从 0 算。"""
    last, out = {}, []
    keys = ("tokensIn", "tokensCached", "tokensOut", "calls")
    for r in rows:
        if r.get("kind") != "lead":
            continue
        prev = last.get((r["milestone"], r["session"]))
        out.append((r["milestone"], r.get("task") or "-", {k: r[k] - (prev[k] if prev else 0) for k in keys}))
        last[(r["milestone"], r["session"])] = r
    return out


def cmd_show(a):
    rows = read_rows()
    runs = [r for r in rows if r.get("kind") == "run"]
    v1 = [r for r in rows if "kind" not in r or "score" in r]
    if v1:
        print("台账里有 %d 行旧版记录(人工评分格式),不计入下面的指标。" % len(v1))
    own = owners(rows)
    if own:
        keyf = {"model": lambda o: "%s · %s" % (o[0], o[1]), "agent": lambda o: o[2], "kind": lambda o: o[1]}[a.by]
        groups = {}
        for task, o in own.items():
            groups.setdefault(keyf(o), []).append(task)
        print("%-30s %4s %8s %6s %6s %6s %12s %12s %6s" % ("分组", "任务", "一次通过", "审查轮", "发现", "bug",
                                                       "平均输入/任务", "平均缓存/任务", "接手"))
        for k in sorted(groups):
            ms = [task_metrics(t, rows) for t in groups[k]]
            s = {x: sum(m[x] for m in ms) for x in ms[0] if x != "firstReview"}
            n = len(groups[k])
            print("%-30s %4d %8s %6d %6d %6d %12d %12d %6d" % (
                k, n, "%d/%d" % (s["firstOk"], s["reviewed"]) if s["reviewed"] else "-", s["rounds"], s["findings"],
                s["bugs"], s["tokensIn"] / n, s["tokensCached"] / n, s["takeover"]))
    else:
        print("还没有助手的运行记录。派工脚本每次运行后会自动记一行。")
    other = [r for r in runs if r["role"] not in ("助手", "前端")]
    if other:
        print("审查、预检等运行 %d 次,输入共 %d" % (len(other), sum(r["tokensIn"] for r in other)))
    lead = lead_usage(rows)
    for ms in sorted(lead):
        u = lead[ms]
        print("lead · %s:输入 %d,缓存读取 %d,输出 %d,调用 %d 次" % (ms, u["tokensIn"], u["tokensCached"], u["tokensOut"],
                                                             u["calls"]))
        for m, task, d in lead_segments(rows):
            if m == ms and task != "-":
                print("  到 %s 为止的这一段:调用 %d 次,输入 %d,缓存读取 %d" % (task, d["calls"], d["tokensIn"], d["tokensCached"]))
    print("一次通过=模块第 1 次审查就是 pass;发现=审查意见条数。成本 ≈ 上下文 × 调用次数,看缓存读取。"
          "样本少于 5 个模块的分组,先不要下结论。")


def cmd_level(a):
    rows = read_rows()
    groups = {}
    for task, o in owners(rows).items():
        groups.setdefault((o[0], o[1]), []).append(task)
    if not groups:
        print("台账还没有助手的运行记录。起始级别:gpt-6.1-sol 是 L3,其他模型是 L2。")
        return
    for (model, module), tasks in sorted(groups.items()):
        level = START_LEVELS.get(model, DEFAULT_LEVEL)
        timeline = []
        for t in tasks:
            m = task_metrics(t, rows)
            if m["firstReview"]:
                good = m["firstOk"] and m["bugs"] <= MAX_BUGS
                timeline.append((m["firstReview"], "good" if good else "bad"))
            timeline += [(f["time"], "down") for f in rows if f.get("kind") == "flag" and f["task"] == t and f["flag"] == "接手"]
        streak = downs = 0
        for _, ev in sorted(timeline, key=lambda x: x[0]):  # 同一秒的事件保持记录顺序
            if ev == "good":
                streak += 1
                if streak >= UP_STREAK:
                    level, streak, downs = min(3, level + 1), 0, 0
            elif ev == "down":
                downs += 1
                if downs >= DOWN_SIGNALS:
                    level, streak, downs = max(1, level - 1), 0, 0
            else:
                streak = 0
        print("%s · %s:建议 L%d(连续通过 %d/%d,接手信号 %d/%d)" % (model, module, level, streak, UP_STREAK,
                                                              downs, DOWN_SIGNALS))
    print("规则:连续 %d 个模块第 1 次审查就通过、试玩 bug 少于 %d 个,升 1 级;接手信号累计 %d 次,降 1 级。"
          % (UP_STREAK, MAX_BUGS + 1, DOWN_SIGNALS))


def tokens(p):
    p.add_argument("--tokens-in", type=int, default=0)
    p.add_argument("--tokens-cached", type=int, default=0)
    p.add_argument("--tokens-out", type=int, default=0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="命令")
    p = sub.add_parser("record", help="记一次运行(派工脚本调用)")
    p.add_argument("--task", required=True, help="任务编号;环境预检可以写「预检」")
    p.add_argument("--role", required=True, choices=ROLES)
    p.add_argument("--agent", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--effort")
    p.add_argument("--session")
    p.add_argument("--module")
    p.add_argument("--level")
    p.add_argument("--tier", help="Codex 的速度档,例如 fast;标准速度不传")
    p.add_argument("--run", type=int, default=1, help="这个任务的第几次运行(含自动续跑)")
    tokens(p)
    p.add_argument("--note")
    p.set_defaults(fn=cmd_record)
    p = sub.add_parser("review", help="记模块审查结论,同时运行 progress.py set-review")
    p.add_argument("--task", required=True)
    p.add_argument("--result", required=True, choices=["pass", "changes"])
    p.add_argument("--findings", type=int, required=True, help="审查意见条数,不算「建议」")
    p.add_argument("--by", choices=["reviewer", "lead"])
    p.add_argument("--note")
    p.set_defaults(fn=cmd_review)
    p = sub.add_parser("bug", help="记试玩发现的 bug")
    p.add_argument("--task", required=True)
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--note")
    p.set_defaults(fn=cmd_bug)
    p = sub.add_parser("lead", help="记 lead 会话的累计读数(Claude 应用用量工具上的数),不是这一段的增量。"
                                     "脚本按同一会话前后两次读数相减,算出每个里程碑和每段任务的用量")
    p.add_argument("--milestone", required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--task", help="刚做完的任务(独做的也记)。show 会列出每段任务的用量")
    tokens(p)
    p.add_argument("--calls", type=int, default=0, help="调用次数,应用显示了就填")
    p.add_argument("--context", type=int, default=0, help="上下文大小。用量工具只给这个时,token 三项留空")
    p.add_argument("--cost-usd", type=float, help="拿不到 token 拆分时的估算花费,在 --note 写估算方法")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_lead)
    p = sub.add_parser("score", help="记 Lily 的打分,帕累托查看器的纵轴")
    p.add_argument("--task", required=True)
    p.add_argument("--score", type=float, help="总分 0~10,可以带小数")
    p.add_argument("--delivery", type=half_point, help="交付分(1~5,可以打半分):做对了没有")
    p.add_argument("--work", type=half_point, help="作品分(1~5,可以打半分):对照体验目标,好不好")
    p.add_argument("--label", help="这一组的名字,例如「lead + gpt-6.1-sol」")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_score)
    p = sub.add_parser("flag", help="lead 记程序看不出的事")
    p.add_argument("--task", required=True)
    p.add_argument("--flag", required=True, choices=FLAGS)
    p.add_argument("--signal", choices=SIGNALS, help="接手信号,见 prompts/dispatch.md")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_flag)
    p = sub.add_parser("show", help="汇总")
    p.add_argument("--by", choices=["model", "agent", "kind"], default="model")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("level", help="自主级别建议")
    p.set_defaults(fn=cmd_level)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
