#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件信箱:lead 与助手交换消息,双方都不用结束会话。试点版。

信箱在主项目文件夹的 mail/ 里,一个任务一个文件(mail/T5.jsonl),一行一条消息,只增不改。
从 git 工作目录里运行时,脚本会找到主项目文件夹,所以 lead 和助手读写的是同一个信箱。
只使用 Python 标准库。规则见 prompts/dispatch.md(lead)和 prompts/sidekick.md(助手)。

助手用:
    python tools/mail.py send T5 report --phase 1 --summary "..." --evidence dispatch-logs/evidence/T5/1 \\
        --decisions "..." --problems 无 --downstream 无
    python tools/mail.py send T5 question --kind 可撤回 --text "..." --assumption "超时就按这个做"
    python tools/mail.py wait T5 --reply-to T5-4          等回复,最多等 10 分钟,等待时不耗 token
    python tools/mail.py send T5 objection --claim ... --evidence ... --cost ... --alternative ...
    python tools/mail.py inbox T5 --as assistant          读 lead 发来的指引和停
lead 用:
    python tools/mail.py watch --follow                   一直等新消息,每条打印一行(给 Monitor 用)
    python tools/mail.py reply T5 T5-4 --text "..." [--in-brief] [--verdict 接受|拒绝] [--contract]
                                                          --contract:这条决定改变了契约,自动写进简报的"已定"
    python tools/mail.py send T5 guide --text "..."       不打断,助手在下个阶段开始前读
    python tools/mail.py send T5 stop --text "..."        助手做完当前步骤就停
    python tools/mail.py send T5 review --phase 2 --result ok|guide|stop [--note ...]
    python tools/mail.py send T5 bug --text "..."         记 Lily 试玩发现的 bug
    python tools/mail.py diff T5 --phase 2                阶段 2 比阶段 1 多改了什么(回报时自动存了快照)
    python tools/mail.py close T5                         任务收尾:信箱原文存进证据目录,再删信箱文件
文字较长或带引号时,写进文件,用 @文件路径 代替文字,例如 --summary @dispatch-logs/T5-1.md
"""
import argparse
import datetime
import difflib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
WAIT_SECONDS = 600  # 提问的等待时间,Lily 2026-10-27 暂定 10 分钟
POLL_SECONDS = 5

# 类型:(发送方, 必填字段, 可选字段)
TYPES = {
    "report": ("assistant", ["phase", "summary", "evidence", "decisions", "problems", "downstream"], ["proposal"]),
    "question": ("assistant", ["kind", "text"], ["assumption", "phase"]),
    "objection": ("assistant", ["claim", "evidence", "cost", "alternative"], ["blocking", "phase"]),
    "guide": ("lead", ["text"], ["phase"]),
    "stop": ("lead", ["text"], []),
    "reply": ("lead", ["to", "text"], ["verdict", "in_brief"]),
    "review": ("lead", ["phase", "result"], ["note"]),
    "bug": ("lead", ["text"], ["phase"]),
}
NAMES = {"report": "回报", "question": "提问", "objection": "异议", "guide": "指引", "stop": "停",
         "reply": "回复", "review": "阶段审查", "bug": "试玩 bug"}
QUESTION_KINDS = ["可撤回", "产品", "不可撤回", "接口"]
REVIEW_RESULTS = ["ok", "guide", "stop"]
VERDICTS = ["接受", "拒绝"]


class Fail(Exception):
    pass


def main_root():
    """主项目文件夹。在 git 工作目录里时,取主仓库,不取工作目录。"""
    env = os.environ.get("LPF_MAIL_ROOT")
    if env:
        return Path(env)
    try:
        out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             cwd=str(HERE), capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).parent
    except (OSError, subprocess.SubprocessError):
        pass
    return HERE.parent


def mail_dir():
    d = main_root() / "mail"
    d.mkdir(parents=True, exist_ok=True)
    return d


def check_task(task):
    if not task or any(c in task for c in "/\\:*?\"<>| ") or task.startswith("."):
        raise Fail("任务编号不能含路径符号或空格:%s" % task)
    return task


def box(task):
    return mail_dir() / ("%s.jsonl" % check_task(task))


def read_box(task):
    p = box(task)
    if not p.exists():
        return []
    rows = []
    for i, line in enumerate(p.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise Fail("%s 第 %d 行不是合法的 JSON:%s。信箱只增不改,请恢复这一行。" % (p.name, i, e.msg))
    return rows


def append(task, msg):
    rows = read_box(task)
    msg["id"] = "%s-%d" % (task, len(rows) + 1)
    with open(box(task), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    return msg


def text_arg(v):
    """@路径 表示从文件读文字,避免命令行里的引号问题。"""
    if isinstance(v, str) and v.startswith("@") and len(v) > 1:
        p = Path(v[1:])
        if not p.exists():
            raise Fail("找不到文件:%s" % p)
        return p.read_text(encoding="utf-8-sig").strip()
    return v


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def build(task, mtype, a):
    sender, required, optional = TYPES[mtype]
    msg = {"time": now(), "task": task, "type": mtype, "from": sender}
    missing = []
    for k in required + optional:
        v = getattr(a, k, None)
        v = text_arg(v)
        if isinstance(v, str):
            v = v.strip()
        if v in (None, "", False):
            if k in required:
                missing.append("--" + k.replace("_", "-"))
            continue
        msg[k] = v
    if missing:
        raise Fail("%s 缺少:%s。字段说明见 python tools/mail.py --help" % (NAMES[mtype], "、".join(missing)))
    if mtype == "question" and msg["kind"] not in QUESTION_KINDS:
        raise Fail("提问的 --kind 只能是:%s" % "、".join(QUESTION_KINDS))
    if mtype == "question" and msg["kind"] == "可撤回" and "assumption" not in msg:
        raise Fail("可撤回的提问要写 --assumption:超时没有回复时,你按什么保守假设继续")
    if mtype == "review" and msg["result"] not in REVIEW_RESULTS:
        raise Fail("阶段审查的 --result 只能是:%s" % "、".join(REVIEW_RESULTS))
    if mtype == "reply":
        rows = read_box(task)
        target = next((r for r in rows if r["id"] == msg["to"]), None)
        if not target:
            raise Fail("信箱里没有消息 %s" % msg["to"])
        if target["type"] == "objection" and msg.get("verdict") not in VERDICTS:
            raise Fail("回复异议要写 --verdict 接受 或 拒绝。拒绝时在 --text 里写理由")
    return msg


def cmd_send(a):
    task = check_task(a.task)
    msg = build(task, a.type, a)
    if a.type == "report":
        ev = Path(msg["evidence"])
        if not ev.is_absolute():
            ev = Path.cwd() / ev
        if not ev.exists() or (ev.is_dir() and not any(ev.iterdir())):
            raise Fail("证据不存在或是空文件夹:%s。先把验收命令的原始输出存进去" % msg["evidence"])
        msg["snapshot"] = snapshot(task, msg["phase"])
    msg = append(task, msg)
    print("已发送 %s %s" % (NAMES[a.type], msg["id"]))
    if a.type == "report":
        print("本阶段的改动快照:%s。继续下一个阶段,不用等回复。" % msg["snapshot"])
    if a.type == "question":
        print("接着运行:python tools/mail.py wait %s --reply-to %s" % (task, msg["id"]))


def git_out(*args):
    out = subprocess.run(["git"] + list(args), capture_output=True, encoding="utf-8", errors="replace")
    return out.stdout if out.returncode in (0, 1) else ""


def snapshot(task, phase):
    """把当前工作目录相对 HEAD 的全部改动(含新文件)存进信箱。只用只读的 git 命令,沙箱里也能运行。
    开着沙箱时助手不能提交(Codex 把 .git 设为只读,2026-10-28 实测),lead 靠快照审查每个阶段。"""
    parts = [git_out("diff", "HEAD")]
    for f in git_out("ls-files", "--others", "--exclude-standard").splitlines():
        if f and not f.startswith("dispatch-logs/"):
            parts.append(git_out("diff", "--no-index", "--", os.devnull, f))
    d = mail_dir() / task
    d.mkdir(exist_ok=True)
    p = d / ("phase-%d.patch" % int(phase))
    p.write_text("".join(parts), encoding="utf-8", newline="\n")
    return p.relative_to(main_root()).as_posix()


def cmd_diff(a):
    """lead 用:阶段 N 比阶段 N-1 多了哪些改动(两份快照的差别)。"""
    d = mail_dir() / check_task(a.task)
    cur = d / ("phase-%d.patch" % a.phase)
    if not cur.exists():
        raise Fail("没有阶段 %d 的快照" % a.phase)
    prev = d / ("phase-%d.patch" % (a.phase - 1))
    old = prev.read_text(encoding="utf-8").splitlines(True) if prev.exists() else []
    new = cur.read_text(encoding="utf-8").splitlines(True)
    if not old:
        sys.stdout.write("".join(new))
        return
    sys.stdout.writelines(difflib.unified_diff(old, new, prev.name, cur.name, n=2))


def cursor_path(task, side):
    return mail_dir() / (".read-%s-%s" % (task, side))


def unread(task, side, mark):
    """side 一方还没读过的、对方发来的消息。"""
    other = "lead" if side == "assistant" else "assistant"
    rows = read_box(task)
    cp = cursor_path(task, side)
    seen = int(cp.read_text().strip() or 0) if cp.exists() else 0
    new = [r for r in rows[seen:] if r["from"] == other]
    if mark:
        cp.write_text(str(len(rows)))
    return new


def fmt(r):
    head = "[%s] %s %s" % (r["id"], NAMES.get(r["type"], r["type"]), r["time"])
    if "phase" in r:
        head += " · 阶段 %s" % r["phase"]
    body = ["  %s:%s" % (k, r[k]) for k in r if k not in ("id", "time", "task", "type", "from", "phase")]
    return "\n".join([head] + body)


def cmd_inbox(a):
    new = unread(check_task(a.task), a.side, not a.peek)
    if not new:
        print("没有新消息")
        return
    for r in new:
        print(fmt(r))
    if a.side == "assistant" and any(r["type"] == "stop" for r in new):
        print("\n有「停」:做完当前步骤就停下,发一条回报说明停在哪里。")


def cmd_wait(a):
    task = check_task(a.task)
    rows = read_box(task)
    q = next((r for r in rows if r["id"] == a.reply_to), None)
    if not q:
        raise Fail("信箱里没有消息 %s" % a.reply_to)
    deadline = time.time() + a.timeout
    while True:
        rep = next((r for r in read_box(task) if r["type"] == "reply" and r.get("to") == a.reply_to), None)
        if rep:
            print(fmt(rep))
            return 0
        if time.time() >= deadline:
            break
        time.sleep(min(POLL_SECONDS, max(0.1, deadline - time.time())))
    kind = q.get("kind")
    print("等了 %d 秒没有回复。" % a.timeout)
    if kind == "可撤回":
        print("按你写的保守假设继续:%s。在下一条回报的 decisions 里标出来。" % q.get("assumption", ""))
    elif q["type"] == "question":
        print("这是%s问题:先做不依赖它的阶段。没有可做的阶段时,停下并在最后一条消息里说明。" % kind)
    return 2


def one_line(r):
    text = r.get("summary") or r.get("text") or r.get("claim") or r.get("result") or ""
    ph = " · 阶段 %s" % r["phase"] if "phase" in r else ""
    return "[%s] %s%s:%s" % (r["id"], NAMES.get(r["type"], r["type"]), ph, str(text).replace("\n", " ")[:80])


def cmd_watch(a):
    """lead 用:等任何任务出现助手发来的新消息。
    默认出现新消息就打印并退出;--follow 一直运行,每条消息打印一行,适合 Claude Code 的 Monitor。"""
    deadline = time.time() + a.timeout if a.timeout else None
    while True:
        found = []
        for p in sorted(mail_dir().glob("*.jsonl")):
            found += unread(p.stem, "lead", True)
        if found and a.follow:
            for r in found:
                print(one_line(r), flush=True)
        elif found:
            for r in found:
                print(fmt(r))
            return 0
        if deadline and time.time() >= deadline:
            print("没有新消息")
            return 2
        time.sleep(POLL_SECONDS)


def brief_path(task):
    return main_root() / "tasks" / ("%s.md" % task)


def add_decision(task, msg):
    """改变契约的决定写进简报的"已定"。简报是契约的唯一来源,新会话只读简报也不会漏掉。"""
    p = brief_path(task)
    if not p.exists():
        raise Fail("找不到简报 %s,决定没有写进去" % p.name)
    lines = p.read_text(encoding="utf-8-sig").splitlines()
    try:
        start = lines.index("## 已定")
    except ValueError:
        raise Fail("简报 %s 没有「## 已定」,决定没有写进去" % p.name)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, "- 决定(%s,%s):%s" % (msg["id"], msg["time"][:10], msg["text"]))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def cmd_reply(a):
    a.to = a.to_id
    task = check_task(a.task)
    msg = append(task, build(task, "reply", a))
    print("已回复 %s(%s)" % (a.to_id, msg["id"]))
    if a.contract:
        add_decision(task, msg)
        print("已写进简报 tasks/%s.md 的「已定」。派工脚本下次运行时会把新简报带进工作目录。" % task)


def status(task):
    rows = read_box(task)
    reported = sorted({int(r["phase"]) for r in rows if r["type"] == "report"})
    replied = {r["to"] for r in rows if r["type"] == "reply"}
    open_q = [r["id"] for r in rows if r["type"] in ("question", "objection") and r["id"] not in replied]
    return {"task": task, "reportedPhases": reported, "openQuestions": open_q,
            "stopped": any(r["type"] == "stop" for r in rows), "messages": len(rows)}


def cmd_status(a):
    s = status(check_task(a.task))
    if a.json:
        print(json.dumps(s, ensure_ascii=False))
    else:
        print("已回报的阶段:%s" % ("、".join(map(str, s["reportedPhases"])) or "无"))
        print("没回复的提问和异议:%s" % ("、".join(s["openQuestions"]) or "无"))


def export_text(task):
    rows = read_box(task)
    out = ["# %s 信箱记录(%s 导出,共 %d 条)" % (task, now()[:10], len(rows)), ""]
    out += ["- " + fmt(r).replace("\n", "\n  ") for r in rows]
    return "\n".join(out) + "\n"


def cmd_export(a):
    sys.stdout.write(export_text(check_task(a.task)))


def meta_path(task):
    return mail_dir() / ("%s.meta.json" % task)


def read_meta(task):
    p = meta_path(task)
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}


def pid_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % int(pid), "/NH"], capture_output=True, text=True, errors="replace")
        return str(pid) in out.stdout
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def close(task, force=False):
    """任务收尾:指标存进台账,信箱原文存进证据目录,删信箱文件,检查派工进程,列出过期的"下一步"。返回提示行。"""
    notes = []
    meta = read_meta(task)
    if not meta.get("finished") and pid_alive(meta.get("pid")):
        msg = "派工进程 %s 还在运行。先确认它做完了,再结束它:Stop-Process -Id %s" % (meta["pid"], meta["pid"])
        if not force:
            raise Fail(msg + "。确定要收尾,加 --force")
        notes.append(msg)
    rows = read_box(task)
    if rows:
        # 台账的指标从信箱算;删信箱前把要用的字段存进 ledger.jsonl(只增不改,随项目提交)
        keep = ("id", "time", "type", "from", "phase", "result", "in_brief", "verdict", "to")
        row = {"time": now(), "kind": "box", "task": task, "events": [{k: r[k] for k in keep if k in r} for r in rows]}
        with open(main_root() / "ledger.jsonl", "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        dest = main_root() / "dispatch-logs" / "evidence" / task
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "mailbox.md").write_text(export_text(task), encoding="utf-8", newline="\n")
        notes.append("信箱原文已存到 %s" % (dest / "mailbox.md").relative_to(main_root()).as_posix())
    d = mail_dir()
    for f in [box(task), meta_path(task)] + list(d.glob(".read-%s-*" % task)):
        if f.exists():
            f.unlink()
    snap = d / task
    if snap.is_dir():
        for f in snap.iterdir():
            f.unlink()
        snap.rmdir()
    prog = main_root() / "progress.json"
    if prog.exists():
        nxt = json.loads(prog.read_text(encoding="utf-8-sig")).get("next", [])
        old = [(i, t) for i, t in enumerate(nxt, 1) if re.search(r"\b%s\b" % re.escape(task), t)]
        for i, t in old:
            notes.append("「下一步」第 %d 条提到 %s,过期了就运行 progress.py remove-next %d:%s" % (i, task, i, t))
    return notes


def cmd_close(a):
    for n in close(check_task(a.task), a.force):
        print(n)
    print("%s 的信箱已收尾" % a.task)


def add_fields(p, mtype):
    _, required, optional = TYPES[mtype]
    for k in required + optional:
        flag = "--" + k.replace("_", "-")
        if k == "phase":
            p.add_argument(flag, type=int)
        elif k in ("blocking", "in_brief"):
            p.add_argument(flag, action="store_true")
        else:
            p.add_argument(flag)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="命令")
    p = sub.add_parser("send", help="发一条消息")
    p.add_argument("task")
    ts = p.add_subparsers(dest="type", required=True, metavar="类型")
    for t in TYPES:
        if t == "reply":
            continue
        tp = ts.add_parser(t, help=NAMES[t])
        add_fields(tp, t)
    p.set_defaults(fn=cmd_send)
    p = sub.add_parser("reply", help="lead 回复提问或异议")
    p.add_argument("task")
    p.add_argument("to_id", metavar="消息编号")
    p.add_argument("--text", required=True)
    p.add_argument("--verdict", choices=VERDICTS)
    p.add_argument("--in-brief", action="store_true", help="答案已经写在简报里")
    p.add_argument("--contract", action="store_true", help="这条决定改变了契约,写进简报的「已定」")
    p.set_defaults(fn=cmd_reply)
    p = sub.add_parser("inbox", help="读对方发来的新消息")
    p.add_argument("task")
    p.add_argument("--as", dest="side", choices=["assistant", "lead"], required=True)
    p.add_argument("--peek", action="store_true", help="只看,不标为已读")
    p.set_defaults(fn=cmd_inbox)
    p = sub.add_parser("wait", help="助手等某条提问的回复")
    p.add_argument("task")
    p.add_argument("--reply-to", required=True)
    p.add_argument("--timeout", type=float, default=WAIT_SECONDS)
    p.set_defaults(fn=cmd_wait)
    p = sub.add_parser("watch", help="lead 等任何任务的新消息")
    p.add_argument("--timeout", type=float, default=0, help="秒;0 表示一直等")
    p.add_argument("--follow", action="store_true", help="一直运行,每条新消息打印一行")
    p.set_defaults(fn=cmd_watch)
    p = sub.add_parser("status", help="已回报的阶段、没回复的提问")
    p.add_argument("task")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("diff", help="lead 看某个阶段比上一阶段多改了什么")
    p.add_argument("task")
    p.add_argument("--phase", type=int, required=True)
    p.set_defaults(fn=cmd_diff)
    p = sub.add_parser("export", help="转成 Markdown")
    p.add_argument("task")
    p.set_defaults(fn=cmd_export)
    p = sub.add_parser("close", help="任务收尾:导出信箱、删信箱文件、检查派工进程")
    p.add_argument("task")
    p.add_argument("--force", action="store_true", help="派工进程还在运行时也收尾")
    p.set_defaults(fn=cmd_close)
    a = ap.parse_args()
    try:
        code = a.fn(a)
    except Fail as e:
        print("错误:%s" % e, file=sys.stderr)
        sys.exit(1)
    sys.exit(code or 0)


if __name__ == "__main__":
    main()
