#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""派工台账:自动记录每次运行,从信箱算出各模型的表现,给出自主级别建议。试点版。

台账在项目根目录的 ledger.jsonl,一行一条,只增不改。只使用 Python 标准库。
- 每次运行由派工脚本自动记一行(record)。lead 不打分。
- 指标从信箱(mail/)和已收尾任务存进台账的信箱事件算出:第 1 轮审查通过率、返工轮数、答案已在简报里的提问、试玩 bug、异议采纳率。
- 只有程序看不出的事,由 lead 用 flag 记一条:越界、谎报、改了测试、环境、接手。

用法:
    python tools/ledger.py show [--by model|agent|kind]    汇总
    python tools/ledger.py level                           按台账建议每个"模型 · 模块"的自主级别
    python tools/ledger.py flag --task T5 --flag 接手 --signal 超预估 --note "阶段 2 用了 3 倍 token"
    python tools/ledger.py record ...                      派工脚本调用,一般不用手动运行
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mail  # noqa: E402

ROOT = mail.main_root()
ROLES = ["助手", "审查", "预检", "前端", "调研"]
FLAGS = ["越界", "谎报", "改了测试", "环境", "接手"]
SIGNALS = ["测试修2次", "超预估", "同类意见2次", "要改验收", "问已答问题"]
# 起始级别(Lily 2026-10-27):gpt-6.1-sol 从 L3 起步,其他模型从 L2 起步
START_LEVELS = {"gpt-6.1-sol": 3}
DEFAULT_LEVEL = 2
UP_STREAK = 3  # 连续 3 个阶段第 1 轮审查通过,且没有试玩 bug,升 1 级


def fail(msg):
    print("错误:%s" % msg, file=sys.stderr)
    sys.exit(1)


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
    row = write_row({"kind": "run", "task": a.task, "role": a.role, "agent": a.agent, "model": a.model,
                     "effort": a.effort or "default", "session": a.session or "", "module": a.module or "",
                     "level": a.level or "", "run": a.run, "tokensIn": a.tokens_in,
                     "tokensCached": a.tokens_cached, "tokensOut": a.tokens_out, "note": a.note or ""})
    print("台账:%s %s 第 %d 次运行 · %s · 输入 %d" % (row["task"], row["role"], row["run"], row["model"], row["tokensIn"]))


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


def events(task):
    """一个任务的信箱事件:已收尾的部分在台账里(kind=box),加上信箱里现有的。"""
    saved = [e for r in read_rows() if r.get("kind") == "box" and r["task"] == task for e in r["events"]]
    try:
        return saved + mail.read_box(task)
    except mail.Fail as e:
        fail(str(e))


def task_metrics(task, rows):
    box = events(task)
    first = {}
    rework = 0
    for r in box:
        if r["type"] == "review":
            first.setdefault(int(r["phase"]), r["result"])
            rework += r["result"] != "ok"
    ids = {r["id"]: r for r in box}
    replies = [r for r in box if r["type"] == "reply"]
    objections = [r for r in box if r["type"] == "objection"]
    accepted = sum(1 for r in replies if ids.get(r["to"], {}).get("type") == "objection" and r.get("verdict") == "接受")
    flags = [r for r in rows if r.get("kind") == "flag" and r["task"] == task]
    return {"phases": len(first), "firstOk": sum(1 for v in first.values() if v == "ok"), "rework": rework,
            "inBrief": sum(1 for r in replies if r.get("in_brief")),
            "bugs": sum(1 for r in box if r["type"] == "bug"),
            "objections": len(objections), "accepted": accepted,
            "lead": sum(1 for r in box if r["type"] in ("reply", "guide", "stop")),
            "env": sum(1 for f in flags if f["flag"] == "环境"),
            "takeover": sum(1 for f in flags if f["flag"] == "接手")}


def cmd_show(a):
    rows = read_rows()
    runs = [r for r in rows if r.get("kind") == "run"]
    v1 = [r for r in rows if "kind" not in r or "score" in r]
    if v1:
        print("台账里有 %d 行旧版记录(人工评分格式),不计入下面的指标。" % len(v1))
    if not runs:
        print("还没有新版的运行记录。派工脚本每次运行后会自动记一行。")
        return
    own = owners(rows)
    keyf = {"model": lambda o: "%s · %s" % (o[0], o[1]), "agent": lambda o: o[2], "kind": lambda o: o[1]}[a.by]
    groups = {}
    for task, o in own.items():
        groups.setdefault(keyf(o), []).append(task)
    print("%-30s %4s %8s %6s %6s %6s %8s %12s %8s" % ("分组", "任务", "一次通过", "返工", "已答", "bug", "异议采纳", "平均输入/任务",
                                                    "lead 消息"))
    for k in sorted(groups):
        ms = [task_metrics(t, rows) for t in groups[k]]
        s = {x: sum(m[x] for m in ms) for x in ms[0]}
        tin = sum(r["tokensIn"] for r in runs if r["task"] in groups[k]) / len(groups[k])
        print("%-30s %4d %8s %6d %6d %6d %8s %12d %8d" % (
            k, len(groups[k]), "%d/%d" % (s["firstOk"], s["phases"]) if s["phases"] else "-", s["rework"],
            s["inBrief"], s["bugs"], "%d/%d" % (s["accepted"], s["objections"]) if s["objections"] else "-", tin, s["lead"]))
    other = [r for r in runs if r["role"] not in ("助手", "前端")]
    if other:
        print("审查、预检等运行 %d 次,输入共 %d" % (len(other), sum(r["tokensIn"] for r in other)))
    print("一次通过=阶段第 1 次审查就是 ok;已答=答案已在简报里的提问;lead 消息=lead 发的回复、指引和停。样本少于 5 个阶段的分组,先不要下结论。")


def cmd_level(a):
    rows = read_rows()
    own = owners(rows)
    groups = {}
    for task, o in own.items():
        groups.setdefault((o[0], o[1]), []).append(task)
    if not groups:
        print("台账还没有助手的运行记录。起始级别:gpt-6.1-sol 是 L3,其他模型是 L2。")
        return
    for (model, module), tasks in sorted(groups.items()):
        level = START_LEVELS.get(model, DEFAULT_LEVEL)
        timeline = []
        for t in tasks:
            seen = set()
            for r in events(t):
                if r["type"] == "review" and int(r["phase"]) not in seen:
                    seen.add(int(r["phase"]))
                    timeline.append((r["time"], "ok" if r["result"] == "ok" else "no"))
                elif r["type"] == "bug":
                    timeline.append((r["time"], "bug"))
            timeline += [(f["time"], "down") for f in rows if f.get("kind") == "flag" and f["task"] == t and f["flag"] == "接手"]
        streak = 0
        for _, ev in sorted(timeline, key=lambda x: x[0]):  # 同一秒的事件保持记录顺序
            if ev == "ok":
                streak += 1
                if streak >= UP_STREAK:
                    level, streak = min(3, level + 1), 0
            elif ev == "down":
                level, streak = max(1, level - 1), 0
            else:
                streak = 0
        print("%s · %s:建议 L%d(连续通过 %d/%d)" % (model, module, level, streak, UP_STREAK))
    print("规则:连续 3 个阶段第 1 轮审查通过且没有试玩 bug,升 1 级;出现 1 次接手信号,降 1 级。")


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
    p.add_argument("--run", type=int, default=1, help="这个任务的第几次运行(含自动续跑)")
    p.add_argument("--tokens-in", type=int, default=0)
    p.add_argument("--tokens-cached", type=int, default=0)
    p.add_argument("--tokens-out", type=int, default=0)
    p.add_argument("--note")
    p.set_defaults(fn=cmd_record)
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
