#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交检查,由 tools/hooks/commit-msg 调用。试点版。只使用 Python 标准库。

所有分支:提交说明末尾要有追溯信息 Task、Agent、Model、Effort、Session 5 行。
task/ 分支(助手按阶段提交):助手只写 Phase: 阶段编号。其余 5 行由本钩子按派工记录
(mail/T编号.meta.json)自动补上,模型不手写编号。信箱里要有这个阶段的回报,回报写的证据要存在。
lead 一次提交全部阶段时写 Phase: 全部。合并提交不检查。
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mail  # noqa: E402  与本脚本同目录

TRAILERS = ["Task", "Agent", "Model", "Effort", "Session"]


def git(*args):
    out = subprocess.run(["git"] + list(args), capture_output=True, text=True, encoding="utf-8")
    return out.stdout.strip() if out.returncode == 0 else ""


def trailers(text):
    found = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z-]+):\s*(\S.*)$", line.strip())
        if m:
            found[m.group(1)] = m.group(2).strip()
    return found


def session_of(task, meta):
    """会话编号:优先用派工记录里的;没有时从最新的派工日志第一条事件里取;再没有就用运行编号。"""
    if meta.get("session"):
        return meta["session"]
    logs = sorted((mail.main_root() / "dispatch-logs").glob("%s-*.events.jsonl" % task))
    for p in reversed(logs):
        for line in p.read_text(encoding="utf-8-sig", errors="replace").splitlines()[:5]:
            if '"thread.started"' in line:
                try:
                    return json.loads(line)["thread_id"]
                except (ValueError, KeyError):
                    pass
    return meta.get("runId", "")


def stamp(msg, task):
    """task/ 分支:按派工记录补上缺少的追溯信息。返回补好的提交说明。"""
    t = trailers(msg)
    meta = mail.read_meta(task)
    values = {"Task": task, "Agent": meta.get("agent", ""), "Model": meta.get("model", ""),
              "Effort": meta.get("effort", ""), "Session": session_of(task, meta)}
    add = ["%s: %s" % (k, values[k]) for k in TRAILERS if k not in t and values[k]]
    if not add:
        return msg
    return msg.rstrip("\n") + "\n" + "\n".join(add) + "\n"


def problems(msg, branch, top):
    errs = []
    t = trailers(msg)
    miss = [k for k in TRAILERS if k not in t]
    if miss:
        errs.append("提交说明末尾缺少追溯信息:%s。格式见 prompts/dispatch.md 的「提交」" % "、".join(miss))
    m = re.fullmatch(r"task/(T\d+)", branch or "")
    if not m:
        return errs
    task = m.group(1)
    if t.get("Task") and t["Task"] != task:
        errs.append("分支是 %s,Task 却写了 %s" % (branch, t["Task"]))
    phase = t.get("Phase", "")
    if phase == "全部":
        # 开着沙箱时,助手不提交,全部阶段做完后由 lead 一次提交
        import brief
        brief.ROOT = Path(top)
        wanted = [p["n"] for p in brief.check(task)[1]]
    elif phase.isdigit():
        wanted = [int(phase)]
    else:
        errs.append("task/ 分支上的提交要写 Phase: 阶段编号(lead 一次提交全部阶段时写 Phase: 全部)")
        return errs
    box = mail.read_box(task)
    for n in wanted:
        reports = [r for r in box if r["type"] == "report" and int(r["phase"]) == n]
        if not reports:
            errs.append("信箱里没有 %s 阶段 %d 的回报。先运行 python tools/mail.py send %s report ..." % (task, n, task))
            continue
        ev = Path(reports[-1]["evidence"])
        if not ev.is_absolute():
            ev = Path(top) / ev
        if not ev.exists() or (ev.is_dir() and not any(ev.iterdir())):
            errs.append("阶段 %d 回报里的证据不存在或是空的:%s" % (n, reports[-1]["evidence"]))
    return errs


def main():
    msg_file = Path(sys.argv[1])
    top = git("rev-parse", "--show-toplevel") or os.getcwd()
    gitdir = git("rev-parse", "--absolute-git-dir")
    if gitdir and (Path(gitdir) / "MERGE_HEAD").exists():
        return 0
    raw = msg_file.read_text(encoding="utf-8", errors="replace")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    try:
        m = re.fullmatch(r"task/(T\d+)", branch or "")
        if m:
            stamped = stamp(raw, m.group(1))
            if stamped != raw:
                msg_file.write_text(stamped, encoding="utf-8", newline="\n")
                raw = stamped
        msg = "\n".join(l for l in raw.splitlines() if not l.startswith("#"))
        errs = problems(msg, branch, top)
    except mail.Fail as e:
        errs = [str(e)]
    if errs:
        for e in errs:
            print("[提交被拒] %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
