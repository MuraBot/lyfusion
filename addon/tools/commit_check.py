#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交检查,由 tools/hooks/commit-msg 调用。只使用 Python 标准库。

所有分支:提交说明末尾要有追溯信息 Task、Agent、Model、Effort、Session 5 行。
task/ 分支:Task 要和分支一致。助手的改动由派工脚本在运行结束后提交,追溯信息由脚本写好。
合并提交不检查。
"""
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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


def problems(msg, branch):
    errs = []
    t = trailers(msg)
    miss = [k for k in TRAILERS if k not in t]
    if miss:
        errs.append("提交说明末尾缺少追溯信息:%s。格式见 prompts/dispatch.md 的「提交与 token」" % "、".join(miss))
    m = re.fullmatch(r"task/(T\d+)", branch or "")
    if m and t.get("Task") and t["Task"] != m.group(1):
        errs.append("分支是 %s,Task 却写了 %s" % (branch, t["Task"]))
    return errs


def main():
    gitdir = git("rev-parse", "--absolute-git-dir")
    if gitdir and (Path(gitdir) / "MERGE_HEAD").exists():
        return 0
    raw = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    msg = "\n".join(l for l in raw.splitlines() if not l.startswith("#"))
    errs = problems(msg, git("rev-parse", "--abbrev-ref", "HEAD"))
    for e in errs:
        print("[提交被拒] %s" % e, file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
