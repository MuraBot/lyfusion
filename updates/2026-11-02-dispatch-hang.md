# 更新简报:派工脚本不再挂住;打分改 10 分制(2026-11-02)

> 来源:小熊蜂蜜罐对比实验。② 组白等约 50 分钟,③ 组 lead 三次结束进程。Lily:"脚本挂住的问题,需要修复";打分用 10 分制、可以带小数。

## 一、挂住的原因
Codex 启动时在后台拉插件市场,拉取的 git 继承了 Codex 的输出管道,比 Codex 活得久。
- PowerShell 用 `&` 运行 Codex 并重定向输出时,要等管道关掉才返回。
- 调用派工脚本的工具(lead 的 Bash / PowerShell 工具)也在等它自己的输出管道。试过改用 `Start-Process` 并清掉脚本标准句柄的继承标记:脚本 0.9 秒就结束,工具仍等了 20 秒。PowerShell 手里还有别的可继承副本,脚本里清不干净。

## 二、改了什么
- **新文件 `tools/run_logged.py`**(27 行):派工脚本把 Codex 和合并时的测试命令交给它运行。它用 Python 的句柄清单启动子进程,子进程只继承输入、输出、错误三个文件,输出直接写进文件,只等子进程本身退出。
- **参数走文件:**派工脚本把命令写成 JSON(`日志前缀.run.json`)再交给 `run_logged.py`。Windows PowerShell 5.1 传参不转义引号的旧补丁(`"` 写成 `\"`)删掉了。
- **合并测试**也走 `run_logged.py`,输出在 `dispatch-logs/任务-merge-test.out.txt`,证据仍写进 `evidence/任务/merge/test.txt`。
- **`ledger.py score` 加 `--score`**(0~10,可以带小数)。`--delivery`、`--work` 改成可选:要么给 `--score`,要么两项都给。
- **帕累托查看器:**纵轴改成 0~10 分。只有交付分和作品分的旧记录,两分相加当分数。表格加"打分说明"一列(`--note`)。

## 三、验证
- 新测试:假 Codex 退出前留下一个继承输出管道、活 20 秒的子进程。改之前派工用了 20.9 秒,改之后通过(要求 12 秒内)。`test_dispatch.py` 8 个、`test_fusion.py` 4 个,全部通过。
- 真的 Codex(0.166.0-alpha.5.1):`--version` 经 `run_logged.py` 正常运行;用 gpt-6-luna low 跑了一次 `-Preflight`(输入约 4.6 万 token),脚本和输出管道都在 23.4 秒结束。这一次后台没有残留的 git,所以它只证明新启动方式能用;"后台进程占着管道"由上面的假 Codex 测试覆盖。

## 四、迁移
复制 `tools/run_logged.py`、`tools/codex-dispatch.ps1`、`tools/ledger.py`。派工需要本机有 `python`(台账和简报检查本来就要)。
