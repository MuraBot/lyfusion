#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""派工脚本用它启动 Codex 和测试命令,一般不用手动运行。

    python tools/run_logged.py 说明文件.json

说明文件(UTF-8):{"cmd": [程序, 参数...] 或 "shell": "命令", "cwd": 目录, "out": 输出文件, "err": 错误文件(不写就并进输出)}
为什么不让 PowerShell 直接运行:Codex 启动时在后台拉插件市场,拉取的 git 继承了输出管道、比 Codex 活得久,
PowerShell 和调用派工脚本的工具都会等管道关掉(小熊对比实验 2026-11-02 挂住 7~34 分钟)。
这里子进程只继承三个文件(Python 在 Windows 上按句柄清单继承),输出直接写进文件,只等子进程本身退出。
参数放在文件里传,也避开了 Windows PowerShell 5.1 传参不转义引号的问题。
"""
import json
import subprocess
import sys

with open(sys.argv[1], encoding="utf-8-sig") as f:
    spec = json.load(f)
with open(spec["out"], "wb") as out:
    err = open(spec["err"], "wb") if spec.get("err") else subprocess.STDOUT
    try:
        r = subprocess.run(spec["cmd"] if "cmd" in spec else spec["shell"], shell="cmd" not in spec, cwd=spec["cwd"],
                           stdin=subprocess.DEVNULL, stdout=out, stderr=err)
    finally:
        if err is not subprocess.STDOUT:
            err.close()
sys.exit(r.returncode)
