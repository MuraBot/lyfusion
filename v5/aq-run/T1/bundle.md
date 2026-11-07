# T1 交接包

- 状态:完成 · 最后阶段 3 · T1 阶段 1、2 已分别通过 8 项和 4 项测试；第 1 轮完成四字段引擎改造。第 2 轮修订后阶段 3 为 54 passed、1 项按 R14 跳过，lint 通过，插件打包成功；证据在 `dispatch-logs/evidence/T1/`。
- 会话编号:01a1b5a5-3ca5-7e63-99cc-8142281bd2e8
- 起点提交:d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf · 分支:v5-aq
- 起点之后还有不是助手的提交,下面的 diff 混了它们:19ab68d v5.0.0-aq:设计补 3 条(gitignore、违规一节写放行方法、cancel 存 diff)
- 探索之后、派工之前,代码又有 4 个提交,探索包可能过时

## 禁止的操作(验收前先告诉 Lily)
- `"C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Content -LiteralPath 'plugin/core/fusion_core/checks.py' -Encoding UTF8 | Select-Object -First 180;"`
- `"C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command 'Get-Content -Encoding UTF8 plugin/commands/fusion.md; Get-Content -Encoding UTF8 plugin/README.md | Select-Object -Last 70; Get-Content -Encoding UTF8 plugin/core/fusion_core/checks.py'`
- `"C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "python -m pytest -q tests -k 'not test_cancel_kills_running'"`

## 验收命令
- 测试:cd plugin/core && python -m pytest -q tests · 退出码 0
```
.......................................................                  [100%]
55 passed in 108.68s (0:01:48)
```
- lint:python -m ruff check plugin/core · 退出码 0
```
All checks passed!
```

## 原有测试里删掉的断言(先看这里)
```
plugin/core/tests/test_flow.py: "run": f"{PY} -c \"from app.farewell import bye; assert bye('A') == 'Bye, A'\""}]}
plugin/core/tests/test_flow.py: assert out["task"] == "T1"
plugin/core/tests/test_flow.py: assert len(t["debt"]) == 1
plugin/core/tests/test_flow.py: assert calls[0]["resume"] is False and "你是 lyfusion 的助手" in calls[0]["prompt"]
plugin/core/tests/test_flow.py: assert "T1.E1" in text and "检查" in text
plugin/core/tests/test_flow.py: assert "已经验收过了" in proj.do(C.cmd_accept, "T1")["text"]
plugin/core/tests/test_flow.py: assert "fusion/intent.md" in proj.git("log", "--name-only", "--format=", "-3")
plugin/core/tests/test_flow.py: assert "检查没有通过" in proj.calls()[1]["prompt"]
plugin/core/tests/test_flow.py: assert t["state"] == "planned" and t["direct"]
plugin/core/tests/test_flow.py: assert proj.read("app/farewell.py") == FAREWELL
plugin/core/tests/test_flow.py: assert t["items"]["W1"]["owner"] == "lead"
plugin/core/tests/test_flow.py: assert proj.task()["state"] == "accepted"
plugin/core/tests/test_flow.py: assert (proj.root / "fusion" / "runs" / "T1-rejected.diff").read_text(encoding="utf-8")
plugin/core/tests/test_flow.py: proj.do(C.cmd_request_changes, "T1", [{"text": f"第 {i + 1} 处", "expect": "改好"}])
plugin/core/tests/test_flow.py: proj.do(C.cmd_request_changes, "T1", [{"text": "第 4 处", "expect": "改好"}])
plugin/core/tests/test_flow.py: assert "第 1 处" in proj.calls()[1]["prompt"]
plugin/core/tests/test_flow.py: assert debt_q
plugin/core/tests/test_flow.py: assert "修改意见" in out["text"]
plugin/core/tests/test_flow.py: assert "驳回你自定的选择" in proj.calls()[1]["prompt"]
plugin/core/tests/test_flow.py: assert proj.task(out["task"])["state"] == "accepted"
plugin/core/tests/test_parts.py: assert "bounds" in msg and "judgment 工作项由 lead 负责" in msg
plugin/core/tests/test_parts.py: assert "至少对应 1 条验收检查" in msg and "W1、W2" in msg
plugin/core/tests/test_parts.py: assert out["task"] == "T1"
plugin/core/tests/test_parts.py: assert proj.do(C.cmd_plan, {**base, "decisions": ["D1"]})["task"] == "T1"
plugin/core/tests/test_parts.py: assert t["plan"]["decisions"] == ["D1@1"]
plugin/core/tests/test_parts.py: assert out["decision"] == "D1@2" and out["affected"] == ["T1"]
plugin/core/tests/test_parts.py: assert "D1@2" in proj.read("fusion/intent.md")
plugin/core/tests/test_parts.py: assert intent.recover(proj.root)[0]["version"] == 2
plugin/core/tests/test_parts.py: proj.do(C.cmd_request_changes, "T1", [{"text": "a", "expect": "b"}])
plugin/core/tests/test_parts.py: assert "你是 lyfusion 的助手" in calls[1]["prompt"]  # 探索时没发过规则,第一次实现要发
plugin/core/tests/test_parts.py: assert not call["resume"] and "上一个工位的交接摘要" in call["prompt"] and "gpt-6-astra" in call["args"]
plugin/core/tests/test_parts.py: proj.do(C.cmd_request_changes, "T1", [{"text": "继续做完", "expect": "bye 能用"}])
plugin/core/tests/test_parts.py: assert not call["resume"] and "## 任务 T1" in call["prompt"] and "继续做完" in call["prompt"]
plugin/core/tests/test_parts.py: assert by[1]["result"]["serverInfo"]["name"] == "fusion"
plugin/core/tests/test_parts.py: assert "fusion_plan" in names and len(names) == 12
plugin/core/tests/test_parts.py: assert "T1" in by[3]["result"]["content"][0]["text"] and not by[3]["result"]["isError"]
plugin/core/tests/test_parts.py: assert by[4]["result"]["isError"]
plugin/core/tests/test_parts.py: assert by[5]["error"]["code"] == -32601
plugin/core/tests/test_parts.py: assert res[0]["result"]["tools"] == []
plugin/core/tests/test_parts.py: assert res[0]["result"]["tools"] == []
```

## 改动
```
 design/v5.0.0-aq.md                        |   6 +-
 plugin/.claude-plugin/plugin.json          |   4 +-
 plugin/.mcp.json                           |   8 -
 plugin/README.md                           |  40 +-
 plugin/commands/fusion.md                  |  18 +-
 plugin/core/fusion-core.py                 |   2 +-
 plugin/core/fusion_core/__init__.py        |   2 +-
 plugin/core/fusion_core/aq.py              | 128 +++++
 plugin/core/fusion_core/checks.py          | 168 +++---
 plugin/core/fusion_core/cli.py             | 645 +++++++++++++---------
 plugin/core/fusion_core/codex.py           |   5 +-
 plugin/core/fusion_core/commands.py        | 549 +++++--------------
 plugin/core/fusion_core/config.py          |  14 +-
 plugin/core/fusion_core/gitops.py          |   4 +-
 plugin/core/fusion_core/hooks.py           |  57 +-
 plugin/core/fusion_core/intent.py          |  82 ---
 plugin/core/fusion_core/mcp.py             | 152 ------
 plugin/core/fusion_core/prompts.py         | 218 ++++----
 plugin/core/fusion_core/report_schema.json |  56 +-
 plugin/core/fusion_core/state.py           | 335 ++++--------
 plugin/core/fusion_core/store.py           |   3 +-
 plugin/core/fusion_core/supervisor.py      | 823 +++++++++++++++++++++--------
 plugin/core/fusion_core/tools.py           | 138 -----
 plugin/core/fusion_core/util.py            |  39 +-
 plugin/core/fusion_core/validate.py        | 248 ++-------
 plugin/core/fusion_core/views.py           | 484 ++---------------
 plugin/core/tests/conftest.py              |  11 +-
 plugin/core/tests/fake_codex.py            |   3 +-
 plugin/core/tests/test_cli.py              | 359 +++++++++++++
 plugin/core/tests/test_flow.py             | 159 +++---
 plugin/core/tests/test_parts.py            | 227 ++------
 plugin/core/tests/test_shape.py            |  52 ++
 plugin/hooks/hooks.json                    |   8 +-
 plugin/monitors/monitors.json              |   7 -
 34 files changed, 2250 insertions(+), 2804 deletions(-)
```

## 最终报告
- 状态:完成 · 最后阶段 3
- 摘要:T1 阶段 1、2 已分别通过 8 项和 4 项测试；第 1 轮完成四字段引擎改造。第 2 轮修订后阶段 3 为 54 passed、1 项按 R14 跳过，lint 通过，插件打包成功；证据在 `dispatch-logs/evidence/T1/`。

## 要 lead 回答的问题
- 无

## 修改请求的回应
- T1-R17: 探索包先覆盖写入 `fusion/explore.md`，再保存相同内容到 `fusion/tasks/T编号/explore.md`；命令结果路径为首行。测试核对两份内容一致及首行格式。
- T1-R18: 移除 `_wait` 对 `check_failed` 的两处退出；自动修复耗尽仍检查失败时，delegate/revise 以退出码 0 写审查包。测试验证两次自动修复失败后审查包包含“未通过”。
- T1-R19: 无违规时不生成违规节；改动清单使用 `git diff --numstat` 输出完整路径、增删行数、范围标记和文件总数。测试覆盖 `tests/` 路径标范围外且不输出汇总行。
- T1-R20: blocked 状态显示“停下:”及助手 summary；没有报告时显示运行日志路径，不暴露引擎内部状态名。
- T1-R21: delegate/revise 和审查包使用同一下一步判断，只输出一个不带 `--task` 的建议；停下、检查失败/违规和正常完成分别使用指定文字。
- T1-R22: accept 对合并冲突和 lead 工作目录未提交改动分别给出对应处理指引；新增测试覆盖两种错误提示。
- T1-R23: 恢复 preflight 的九项检查名称和逻辑，未打开项目提示改为运行 `fusion-core on`；测试恢复检查名集合断言。
- T1-R24: 探索提示按设计 §5 给出纯文字探索要求，不附 FIXED_RULES；`task_prompt` 删除 `first` 参数并始终附 FIXED_RULES，其中加入 Claude 配置与 Codex auth.json 的访问禁令。
- T1-R25: CLI 的单行多语句和内联 try/finally 已拆成多行；用普通 `replay` 导入替换动态导入，续等通过 `None` 表示未使用本次输入。

## 假设
- R1 代码审计剩余命中均保留：`config.py`、`cli.py`、`util.py` 的 `.items()` 是字典迭代；`report_schema.json` 的 `items` 是 JSON Schema 数组元素关键字；`state.py` 的 `intentionally` 位于忽略旧事件类型的兼容注释中。
- 按 R14 跳过 `test_cancel_kills_running`：Windows 沙箱无法终止 Codex 子进程，导致 `events.jsonl` 在 fixture 清理时仍被占用；其余测试正常运行。

## 接口修改请求
- 无

## 给下游
- 阶段 3 最新证据：`dispatch-logs/evidence/T1/3/tests.txt`、`lint.txt`、`package.txt`。
- 打包文件：`v5/dist/lyfusion-5.0.0-aq.0.zip`。

## 问题
- `python tools/check.py` 在第 1 轮报告根目录 `CLAUDE.md` 缺失及根目录 `README.md` 第 46 行既有长度警告；这些文件不属于 T1 本轮改动范围。

## 关键改动(不含测试,每个文件最多 40 行)

### design/v5.0.0-aq.md
```diff
@@ -42,7 +42,7 @@ lyfusion 已开:这个项目的代码活交给 Codex 助手做,你(lead)只做 4
 - 任务已有运行在进行(比如上一次命令被中断),explore/delegate/revise 不重开运行,接着等它
 - 结束时打印:结果文件路径、2~4 行摘要、下一步可用的命令
 - 退出码:0 结果写好了(检查不过也是 0,审查包里写);1 输入有误,什么都没开始,报错说清怎么改;2 要 lead 处理、没有结果文件(Codex 起不来、长时间无进展、修改轮数到上限、集成冲突等),报错说清下一步
-- 每个结果在 `fusion/tasks/T编号/` 留一份历史(`explore.md`、`review-1.md`、`review-2.md`……)。`fusion/explore.md`、`fusion/review.md`、`fusion/tasks/` 不进 git;`fusion/decisions.md` 进 git
+- 每个结果在 `fusion/tasks/T编号/` 留一份历史(`explore.md`、`review-1.md`、`review-2.md`……)。`fusion/explore.md`、`fusion/review.md`、`fusion/tasks/` 写进 `fusion/.gitignore`(和 `runs/` 一样),免得 lead 顺手提交进项目;`fusion/decisions.md` 进 git
 
 ## 4. 计划:4 个字段
 ```json
@@ -60,7 +60,7 @@ lyfusion 已开:这个项目的代码活交给 Codex 助手做,你(lead)只做 4
 ## 6. 审查包:只有一层
 按顺序:
 1. **检查**:每条一行(名字、命令、通过与否、退出码);没过的附输出最后 ≤20 行。另写自动修了几次、旧测试跑新代码的结果
-2. **违规**(只在有时出现这一节):禁止操作;测试被改弱(派工前的测试在新代码上失败)
+2. **违规**(只在有时出现这一节):禁止操作;测试被改弱(派工前的测试在新代码上失败)。这一节末尾直接写怎么放行:`accept --waive "原因"`,有禁止操作时原因里要写用户的原话。lead 一次调用就能验收,不用先被拒一次
 3. **助手的问题和自定的选择**:状态(做完/停下及原因)、摘要、问题、自定的选择、没做完和已知的问题
 4. **改动**:`diff --stat`,scope 之外的文件标"(范围外)";diff 不超过 400 行就全文附上,超过只列文件名
 
@@ -70,7 +70,7 @@ lyfusion 已开:这个项目的代码活交给 Codex 助手做,你(lead)只做 4
 - 修改意见是自由文字,同一个 Codex 会话续做。最多 3 轮(`max_change_rounds`),到上限退出码 2,先问用户
 - 验收拒绝的情况:检查没全过(只有环境类错误时可以 `--waive` 写原因放行);有违规又没 `--waive`(禁止操作要写用户的原话;测试被改弱,lead 确认是计划要的行为变化,写原因);助手停下提问还没用 revise 回答
 - 问题和自定的选择只列在审查包里,不强制逐条处理,也不拦验收
-- `reject` 并进 `cancel`:停运行、清工位、丢弃候选
+- `reject` 并进 `cancel`:先把任务的 diff 存进 `fusion/runs/` 当证据,再停运行、清工位、丢弃候选
 
 ## 8. 防设计跑偏:`fusion/decisions.md`
 只有这一个普通文件。`on` 时没有就建一个带两行说明的空文件。lead 直接编辑;引擎每次给助手的提示(探索、派工、修改、自动修)都附上全文。没有版本、没有引用、没有决定债。
```

### plugin/.claude-plugin/plugin.json
```diff
@@ -1,6 +1,6 @@
 {
   "name": "lyfusion",
-  "version": "5.0.0-a.0",
-  "description": "lyfusion v5:用于 Claude Code 的双代理协作插件。Claude 做 lead,Codex 做助手(开发中)",
+  "version": "5.0.0-aq.0",
+  "description": "lyfusion v5 aq:用于 Claude Code 的双代理协作插件。Claude 做 lead,Codex 做助手",
   "author": { "name": "MuraBot" }
 }
```

### plugin/.mcp.json
```diff
@@ -1,8 +0,0 @@
-{
-  "mcpServers": {
-    "fusion": {
-      "command": "python",
-      "args": ["${CLAUDE_PLUGIN_ROOT}/core/fusion-core.py", "serve"]
-    }
-  }
-}
```

### plugin/README.md
```diff
@@ -1,36 +1,26 @@
-# lyfusion 插件(v5.0.0-a,开发中)
+# lyfusion 插件(v5.0.0-aq.0)
 
-用于 Claude Code 的双代理协作插件:Claude 当 lead(理解用户、判断、计划、审查、验收),本机的 Codex CLI 当助手(在独立的工位目录里按任务单实现)。个人项目,不是 Anthropic 或 OpenAI 的官方产品;暂不发布到插件市场。
-
-设计:`../design/v5.0.0-a-engineering.md`。进度:`../v5/progress.md`。
+用于 Claude Code 的双代理协作插件:Claude 当 lead,Codex CLI 当助手。lead 通过 `explore`、`delegate`、`revise`、`accept` 四个阻塞命令工作;任务状态和检查由本地 Python 引擎管理。
 
 ## 组成
+
 | 部分 | 位置 | 做什么 |
 |---|---|---|
-| 引擎 fusion-core | `core/` | Python 标准库。事件库、状态机、任务单校验、Codex 运行、检查流水线、集成 |
-| MCP 服务器 | `.mcp.json` → `fusion-core serve` | 给 lead 的 12 个 `fusion_*` 工具;后台监督助手运行 |
-| 钩子 | `hooks/hooks.json` | 新对话注入使用说明和状态;每次提问注入一行状态;编辑到助手正在改的文件时给提示 |
-| monitor | `monitors/monitors.json` | 助手跑完、提阻塞问题、检查出结果时通知 lead |
+| 引擎 fusion-core | `core/` | Python 标准库和 sqlite;运行 Codex、检查候选并集成 |
+| SessionStart 钩子 | `hooks/hooks.json` | Fusion 开启时注入简短使用说明 |
 | 命令 | `commands/fusion.md` | `/fusion on`、`off`、`status`、`model`、`effort`、`fast`、`test` |
 | `bin/` | `fusion-core`、`fusion-core.cmd` | 引擎的命令行入口 |
 
-## 对别的项目零影响
-项目里没有 `fusion/config.json`(没用 `/fusion on` 打开过)时:MCP 工具列表是空的,钩子不输出,monitor 只安静地等。
+lead 在 Bash 后台运行四个主流程命令,每条命令会等待结果并写入 `fusion/explore.md` 或 `fusion/review.md`。跨任务设计决定保存在 `fusion/decisions.md`。
+
+## 隐私和安全
 
-## 遵守的规则
-- 只做 Claude Code 的普通使用:不调用 Claude 的 API,不经手任何登录凭据,不用定时器开回合,不替用户批准权限
-- 插件只运行自己安装目录里的代码;状态都在项目的 `fusion/` 里;不使用插件数据目录;不读取 Claude Code 的其他配置和记录;不读取 Codex 的登录文件
-- 启动 Codex 前去掉 `CLAUDE*`、`ANTHROPIC*` 环境变量;Codex 用 `workspace-write` 沙箱,只能写工位目录
-- 写进 `fusion/runs/` 的日志按常见密钥格式脱敏;`runs/` 不进 git
+- 不调用 Claude API,不读取 Claude 配置或 Codex 登录文件。
+- 启动 Codex 前清除 `CLAUDE*`、`ANTHROPIC*` 环境变量;Codex 只在独立工位中工作。
+- 运行日志按常见密钥格式脱敏,`fusion/runs/` 不进 git。
 
 ## 测试
-```bash
-cd core && python -m pytest -q tests
```
(共 52 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/README.md)

### plugin/commands/fusion.md
```diff
@@ -1,25 +1,23 @@
 ---
-description: 打开、关闭或设置 lyfusion(Claude lead + Codex 助手)
-argument-hint: on | off | status | guide | model <名字> | effort <low|medium|high|xhigh> | fast on|off | test <命令>
+description: 打开、关闭或设置 lyfusion
+argument-hint: on [--test <命令>] [--lint <命令>] | off | status | model <名字> | effort <low|medium|high|xhigh> | fast on|off | test <命令>
 ---
 用户给的参数:$ARGUMENTS
 
-`fusion-core` 是 lyfusion 插件 `bin/` 里的命令(插件启用时在 PATH 里)。找不到这个命令时,告诉用户插件可能没有启用,不要去别处找。
+`fusion-core` 是 lyfusion 插件 `bin/` 里的命令。找不到时告诉用户插件可能未启用,不要去别处找。
 
-按参数运行对应的一条命令,把结果用一两句中文告诉用户:
+按参数运行对应命令,把结果用一两句中文告诉用户:
 
 | 参数 | 命令 |
 |---|---|
 | 空 或 status | `fusion-core status` |
-| on | 先 `fusion-core preflight`,把没通过的项告诉用户;再 `fusion-core on`。项目还没打开过 Fusion 且不知道测试命令时,先问用户测试命令,然后 `fusion-core on --test "命令"` |
+| on --test 命令 [--lint 命令] | 先 `fusion-core preflight`,汇报未通过项;再运行 `fusion-core on --test "命令" [--lint "命令"]` |
 | off | `fusion-core off` |
-| guide | `fusion-core guide`,把输出当作 lead 的使用说明读一遍 |
 | model 名字 | `fusion-core config set '{"local":{"sidekick":{"model":"名字"}}}'` |
 | effort 档位 | `fusion-core config set '{"local":{"sidekick":{"effort":"档位"}}}'` |
 | fast on / fast off | `fusion-core config set '{"local":{"sidekick":{"fast":true}}}'`(off 写 false) |
 | test 命令 | `fusion-core config set '{"config":{"test":"命令"}}'` |
 
-打开之后:
-- `fusion_*` 工具会出现(在延迟工具列表里时,用 ToolSearch 搜 `fusion` 加载)
-- 新对话开始时会自动注入使用说明;当前这个对话里,运行一次 `fusion-core guide` 读说明
-- 这些命令只改项目里的 `fusion/` 文件夹,不改 Claude Code 的设置
+打开后,SessionStart 会注入 4 个动作的使用说明。所有状态都保存在项目的 `fusion/` 目录中。
+
+项目还没打开过 Fusion 且不知道测试命令时,先问用户测试命令,再 `fusion-core on --test "命令"`。
```

### plugin/core/fusion-core.py
```diff
@@ -4,6 +4,6 @@ import sys
 
 sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
 
 
 sys.exit(main())
```

### plugin/core/fusion_core/__init__.py
```diff
@@ -1,4 +1,4 @@
 """fusion-core:lyfusion v5 的引擎。只用 Python 标准库。"""
 
-VERSION = "5.0.0-a.0"
+VERSION = "5.0.0-aq.0"
 SCHEMA = 1  # 事件格式版本
```

### plugin/core/fusion_core/aq.py
```diff
@@ -0,0 +1,128 @@
+"""aq input parsing and task artifact formatting."""
+
+
+
+
+
+def read_input(value: str | None, stdin) -> str:
+    if not value:
+        raise FusionError("缺少输入文件或 - (标准输入)")
+    if value == "-":
+        return stdin.buffer.read().decode("utf-8-sig")
+    return Path(value).read_bytes().decode("utf-8-sig")
+
+
+def parse_plan(text: str) -> dict:
+    try:
+        return validate.plan(json.loads(text))
+    except json.JSONDecodeError as exc:
+        raise FusionError(f"计划不是合法的 JSON:{exc}") from exc
+
+
+def decisions_text(root: Path) -> str:
+    path = root / "fusion" / "decisions.md"
+    return path.read_text(encoding="utf-8") if path.exists() else ""
+
+
+def save_history(root: Path, task: str, name: str, text: str) -> None:
+    folder = root / "fusion" / "tasks" / task
+    folder.mkdir(parents=True, exist_ok=True)
+    (folder / name).write_text(text, encoding="utf-8")
+
+
+def review_pack(root: Path, task: dict, state: dict, round_no: int) -> str:
+    candidate = state["candidates"].get(task.get("latest"))
+    check = candidate.get("checks") or {} if candidate else {}
+    lines = [
+        f"# {task['id']} 审查包(第 {round_no} 轮)",
+        f"目标:{(task.get('plan') or {}).get('goal', '')}",
+        "",
```
(共 124 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/aq.py)

### plugin/core/fusion_core/checks.py
```diff
@@ -1,4 +1,4 @@
-"""检查流水线:证据由程序产生,绑定某一个候选提交。"""
+"""Candidate checks and source-only forbidden-operation scanning."""
 
@@ -10,8 +10,6 @@ from .util import any_match, clean_env, redact_file, run
 ENV_ERROR = re.compile(r"(?i)certificate verify failed|CERTIFICATE_VERIFY_FAILED|unable to get local issuer|"
                        r"SSL: |ECONNRESET|ETIMEDOUT|ECONNREFUSED|Could not resolve host|"
                        r"Temporary failure in name resolution|getaddrinfo|Connection timed out")
-
-# (正则, 原因, 用在哪:cmd=助手执行过的命令,diff=新增的代码行)
 BUILTIN_RULES = [
     (r"(?i)GIT_SSL_NO_VERIFY|http\.sslVerify\s*=?\s*false|sslVerify\s+false", "关闭了 git 的证书检查", "cmd diff"),
     (r"(?i)NODE_TLS_REJECT_UNAUTHORIZED\s*=?\s*['\"]?0", "关闭了 Node 的证书检查", "cmd diff"),
@@ -21,17 +19,23 @@ BUILTIN_RULES = [
     (r"(?i)\bverify\s*=\s*False\b", "代码里关闭了证书检查", "cmd diff"),
     (r"(?i)rejectUnauthorized\s*:\s*false", "代码里关闭了证书检查", "diff"),
     (r"(?i)--no-verify\b", "跳过了 git 钩子", "cmd"),
-    (r"\bgit\s+(push|commit|rebase|merge|switch|checkout\s+-b|branch\s+-[dD]|reset\s+--hard)\b", "助手执行了 git 写操作", "cmd"),
+    (r"\bgit\s+(push|commit|rebase|merge|switch|checkout\s+-b|branch\s+-[dD]|reset\s+--hard)\b",
+     "助手执行了 git 写操作", "cmd"),
 ]
 
-SUSPICIOUS_FILES = ["package.json", "**/package.json", "*.lock", "**/*.lock", "pyproject.toml", "setup.cfg",
-                    "requirements*.txt", "**/requirements*.txt", "build.gradle", "**/build.gradle", "*.gradle.kts",
-                    "**/*.gradle.kts", "gradle.properties", ".github/**", ".gitlab-ci.yml", "Makefile", "fusion/**"]
-URL = re.compile(r"https?://[^\s'\")]+")
+
+def _expected(expect) -> dict:
+    if isinstance(expect, dict):
+        return expect
+    if isinstance(expect, int):
+        return {"exit": expect}
+    if isinstance(expect, str):
+        return {"exit": 0, "regex": expect}
+    return {"exit": 0}
 
 
-def _expect_ok(res: dict, expect: dict | None) -> bool:
-    expect = expect or {"exit": 0}
+def _expect_ok(res: dict, expect=None) -> bool:
```
(共 220 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/checks.py)

### plugin/core/fusion_core/cli.py
```diff
@@ -1,309 +1,444 @@
-"""命令行:`fusion-core <命令> [JSON]`。参数是 JSON(命令行参数或标准输入),输出也是 JSON。"""
+"""Blocking command line interface for the four-field Fusion workflow."""
+
 
 
-
-
-def _out(obj) -> None:
-    sys.stdout.buffer.write((json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
-    sys.stdout.buffer.flush()
 
-
-def _args_json(text: str | None) -> dict:
-    if text is None or text == "-":
-        raw = sys.stdin.buffer.read().decode("utf-8") if not sys.stdin.isatty() else ""
-    else:
-        raw = text
-    raw = raw.strip()
-    return json.loads(raw) if raw else {}
+USAGE = views.LEAD_GUIDE
 
 
-def _root(args) -> Path:
+def _root(args):
     return config_mod.project_root(args.project)
 
 
-def cmd_init(args) -> dict:
-    root = _root(args)
-    cfg = config_mod.init(root, args.test, args.lint)
-    return {"ok": True, "root": str(root), "base_branch": cfg["base_branch"],
-            "text": f"Fusion 已在 {root} 打开。配置在 fusion/config.json,开关和助手模型在 fusion/local.json。"}
-
-
-def cmd_onoff(args, on: bool) -> dict:
-    root = _root(args)
-    if on and not config_mod.is_fusion_project(root):
-        return cmd_init(args)
-    if not config_mod.is_fusion_project(root):
```
(共 674 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/cli.py)

### plugin/core/fusion_core/codex.py
```diff
@@ -2,12 +2,11 @@
 
 
 
 SCHEMA = Path(__file__).with_name("report_schema.json")
 
@@ -22,7 +21,7 @@ def find_codex(cfg: dict) -> list[str]:
     if IS_WIN:
         p = subprocess.run(["powershell", "-NoProfile", "-Command",
                             "(Get-AppxPackage OpenAI.Codex -ErrorAction SilentlyContinue).InstallLocation"],
-                           capture_output=True, text=True)
+                           check=False, capture_output=True, text=True)
         loc = p.stdout.strip()
         if loc:
             exe = Path(loc) / "app" / "resources" / "codex.exe"
```

### plugin/core/fusion_core/commands.py
```diff
@@ -1,18 +1,19 @@
-"""lead 的命令。每条命令在一个写事务里完成:读状态 → 校验 → 追加事件。真正的动作(启动 Codex、git)由监督者做。"""
+"""Public command actions. Events, rather than mutable state, are authoritative."""
 
 
 
 
 class Ctx:
     def __init__(self, root: Path, actor: str = "lead"):
         self.root = Path(root)
         if not config_mod.is_fusion_project(self.root):
-            raise FusionError("这个项目还没有打开 Fusion。先运行 /fusion on(或 fusion-core init)。")
+            raise FusionError("这个项目没有打开 Fusion。先运行 fusion-core on")
         self.cfg = config_mod.load(self.root)
         self.conn = store.connect(self.root)
         self.actor = actor
@@ -24,418 +25,142 @@ class Ctx:
         self.conn.close()
 
 
-def _task(s, tid) -> dict:
-    t = s["tasks"].get(tid or "")
-    if not t:
-        raise FusionError(f"任务 {tid} 不存在。用 status 看现有任务。")
-    return t
-
-
-def _need_state(task, allowed, action):
-    if task["state"] not in allowed:
-        raise FusionError(f"{task['id']} 现在是 {views.STATE_CN.get(task['state'], task['state'])},不能{action}。"
-                          f"只有在 {'/'.join(views.STATE_CN.get(x, x) for x in allowed)} 时可以。")
-
-
-def _evidence_fresh(ctx, task, cand) -> tuple[bool, str]:
-    chk = cand.get("checks")
-    if not chk:
-        return False, "这个候选还没有检查结果"
-    if chk.get("plan_version") != task["version"]:
-        return False, "任务单改过版本,检查要重跑(引擎会自动重跑)"
-    if chk.get("check_hash") != config_mod.check_hash(ctx.cfg):
```
(共 565 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/commands.py)

### plugin/core/fusion_core/config.py
```diff
@@ -12,7 +12,6 @@ DEFAULT_CONFIG = {
     "test": None,                 # 项目测试命令,例如 "python -m pytest -q"
     "lint": None,                 # lint 命令,可以没有
     "tests_glob": ["tests/**", "test/**", "**/test_*.py", "**/*_test.py", "**/*.test.js", "**/*.spec.js"],
-    "perceivable": [],            # 用户能感知的文件,例如 ["ui/**", "assets/lang/**"]
     "forbidden": [],              # 额外的禁止规则:{"pattern": 正则, "why": 原因}
     "station_copy": [],           # 建工位目录时要复制的未跟踪文件
     "network": False,             # 助手的沙箱能否联网
@@ -34,7 +33,7 @@ DEFAULT_LOCAL = {
     "codex": None,                # Codex 命令,列表;默认自动查找
 }
 
-GITIGNORE = "fusion.db\nfusion.db-*\nlocal.json\nruns/\nhandoffs/\n"
+GITIGNORE = "fusion.db\nfusion.db-*\nlocal.json\nruns/\nhandoffs/\nexplore.md\nreview.md\ntasks/\n"
 
 
 def project_root(start: str | os.PathLike | None = None) -> Path:
@@ -81,7 +80,7 @@ def save_local(root: Path, local: dict) -> None:
 def check_hash(cfg: dict) -> str:
     """检查配置的指纹:变了,旧的检查证据就失效。"""
-    keys = ("test", "lint", "tests_glob", "perceivable", "forbidden", "network")
+    keys = ("test", "lint", "tests_glob", "forbidden", "network")
     blob = json.dumps({k: cfg.get(k) for k in keys}, sort_keys=True, ensure_ascii=False)
     return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]
 
@@ -91,7 +90,7 @@ def init(root: Path, test: str | None = None, lint: str | None = None) -> dict:
     fd.mkdir(exist_ok=True)
     cfg_path = fd / "config.json"
     if not cfg_path.exists():
-        cfg = {k: v for k, v in DEFAULT_CONFIG.items() if k in ("test", "lint", "perceivable", "station_copy", "network")}
+        cfg = {k: v for k, v in DEFAULT_CONFIG.items() if k in ("test", "lint", "station_copy", "network")}
         cfg["base_branch"] = git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
         cfg["test"], cfg["lint"] = test, lint
         cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
@@ -99,5 +98,12 @@ def init(root: Path, test: str | None = None, lint: str | None = None) -> dict:
         local = json.loads(json.dumps(DEFAULT_LOCAL))
         local["enabled"] = True
         save_local(root, local)
+    elif test is not None or lint is not None:
+        cfg = load(root)
```
(共 47 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/config.py)

### plugin/core/fusion_core/gitops.py
```diff
@@ -162,7 +162,7 @@ def squash_onto(wt: Path, base_branch: str, message: str, identity: dict | None
         env.update(GIT_AUTHOR_NAME=identity["name"], GIT_AUTHOR_EMAIL=identity["email"],
                    GIT_COMMITTER_NAME=identity["name"], GIT_COMMITTER_EMAIL=identity["email"])
     p = subprocess.run(["git", "commit-tree", tree, "-p", parent, "-F", "-"], cwd=wt, input=message.encode("utf-8"),
-                       capture_output=True, env=env)
+                       check=False, capture_output=True, env=env)
     if p.returncode != 0:
         raise FusionError("git commit-tree 失败:" + p.stderr.decode("utf-8", "replace"))
     return p.stdout.decode().strip()
@@ -206,7 +206,7 @@ def bring_changes(root: Path, wt_ref_cwd: Path, base: str, tip: str) -> tuple[li
             if target.exists():
                 target.unlink()
         else:
-            p = subprocess.run(["git", "show", f"{tip}:{path}"], cwd=wt_ref_cwd, capture_output=True)
+            p = subprocess.run(["git", "show", f"{tip}:{path}"], cwd=wt_ref_cwd, check=False, capture_output=True)
             if p.returncode == 0:
                 target.parent.mkdir(parents=True, exist_ok=True)
                 target.write_bytes(p.stdout)
```

### plugin/core/fusion_core/hooks.py
```diff
@@ -1,48 +1,30 @@
-"""Claude Code 钩子:只注入文字和提示,不批准、不阻止任何操作。
-
-项目没有打开 Fusion(或关着)时什么都不输出,对别的项目零影响。
-"""
+"""SessionStart injects the short aq usage guide; it never blocks the host."""
 
 
-
-EVENT_NAMES = {"session-start": "SessionStart", "prompt": "UserPromptSubmit", "pre-edit": "PreToolUse"}
-
-
-def _root(data: dict) -> Path | None:
-    try:
-        return config_mod.project_root(data.get("cwd") or None)
-    except Exception:
-        return None
 
 
 def run(event: str, data: dict) -> str | None:
-    """返回要注入的文字;None = 不输出。"""
-    root = _root(data)
-    if root is None or not config_mod.is_fusion_project(root):
+    if event not in ("session-start", "SessionStart"):
+        return None
+    try:
+        root = config_mod.project_root(data.get("cwd") or None)
+    except FusionError:
         return None
-    cfg = config_mod.load(root)
-    if not cfg["local"].get("enabled"):
+    if not config_mod.is_fusion_project(root) or not config_mod.load(root)["local"].get("enabled"):
         return None
     ctx = Ctx(root)
     try:
-        if event == "session-start":
-            cmd_lead_session(ctx, data.get("session_id"), data.get("source"))
-            return views.session_context(root, cfg, ctx.state(), data.get("source"))
-        if event == "prompt":
-            return views.prompt_line(ctx.state())
```
(共 74 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/hooks.py)

### plugin/core/fusion_core/intent.py
```diff
@@ -1,82 +0,0 @@
-"""生成 `fusion/intent.md`:给人和助手读,进 git。末尾附 JSON,事件库丢了时能恢复当前决定。"""
-
-
-CAT = {"experience": "体验", "interface": "接口", "rule": "规则", "constraint": "约束"}
-MARK = "lyfusion-intent-data"
-
-
-def render(state: dict) -> str:
-    decs = sorted(state["decisions"].values(), key=lambda d: int(d["id"][1:]))
-    active = [d for d in decs if d["status"] == "active"]
-    old = [d for d in decs if d["status"] != "active"]
-    lines = ["# 意图记录", "",
-             "> 由 lyfusion 生成,不要手改。要改决定,请让 lead 用 intent 工具。",
-             f"> 有效决定 {len(active)} 条,已取代 {len(old)} 条。", ""]
-    for d in active:
-        lines += _one(d)
-    if old:
-        lines += ["## 已取代", ""]
-        for d in old:
-            lines.append(f"- {d['id']}@{d['version']}:{_short(d.get('content'))}"
-                         + (f"(由 {d['superseded_by']} 取代)" if d.get("superseded_by") else ""))
-        lines.append("")
-    data = {"decisions": decs}
-    lines += [f"<!-- {MARK}", json.dumps(data, ensure_ascii=False), "-->", ""]
-    return "\n".join(lines)
-
-
-def _short(text, n=60):
-    text = (text or "").replace("\n", " ")
-    return text if len(text) <= n else text[: n - 1] + "…"
-
-
-def _one(d: dict) -> list[str]:
-    out = [f"## {d['id']}@{d['version']} · {CAT.get(d.get('category'), d.get('category'))}", "", d.get("content", ""), ""]
-    if d.get("reason"):
-        out.append(f"- 理由:{d['reason']}")
-    if d.get("scope"):
-        out.append("- 影响:" + "、".join(f"`{x}`" for x in d["scope"]))
-    if d.get("source"):
```
(共 79 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/intent.py)

### plugin/core/fusion_core/mcp.py
```diff
@@ -1,152 +0,0 @@
-"""MCP stdio 服务器:给 lead 提供 fusion_* 工具,同时在后台线程里监督助手。
-
-- 项目没有打开 Fusion(没有 fusion/config.json)时,工具列表是空的,对别的项目零影响
-- 打开 Fusion 之后(/fusion on),发 tools/list_changed 通知,工具出现
-- 只用标准输入输出做 MCP 通道;日志写 fusion/runs/,不写标准输出
-"""
-
-
-
-PROTOCOL = "2025-06-18"
-
-
-class Server:
-    def __init__(self, root: Path | None, stdin=None, stdout=None, supervise: bool = True):
-        self.root = root
-        self.stdin = stdin or sys.stdin.buffer
-        self.stdout = stdout or sys.stdout.buffer
-        self.lock = threading.Lock()
-        self.supervise = supervise
-        self.sup: Supervisor | None = None
-        self._enabled_seen = self.active()
-        self._stop = threading.Event()
-
-    # ----- 状态 -----
-    def active(self) -> bool:
-        return bool(self.root) and config_mod.is_fusion_project(self.root)
-
-    def enabled(self) -> bool:
-        return self.active() and bool(config_mod.load(self.root)["local"].get("enabled"))
-
-    # ----- 输出 -----
-    def send(self, msg: dict) -> None:
-        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
-        with self.lock:
-            self.stdout.write(data)
-            self.stdout.flush()
-
-    def log(self, text: str) -> None:
-        if self.active():
```
(共 142 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/mcp.py)

### plugin/core/fusion_core/prompts.py
```diff
@@ -1,133 +1,107 @@
-"""给助手的提示。规则短、任务单完整;同一个任务里续用时只发增量。"""
-
-
-RULES = """你是 lyfusion 的助手,和一个 lead 合作:lead 负责设计和判断,你负责按任务单实现。
-规则:
-1. 只在当前目录(你的工位目录)里工作。不要 git 提交、不要切分支、不要推送,提交由引擎做。
-2. 按任务单的三组边界办事:「必须遵守」不能违反;「可以自己定」由你决定;「必须上报」碰到就停下来提阻塞问题。
-3. 有 follows 样例的工作项:先用 git show 读样例的提交,照它的结构、命名、风格扩展;偏离样例的地方写进 choices。
-4. 没人要求、但你自己做了的选择(用户或其他模块可能在意的),全部写进 choices。没有就写空列表。
-   每条:what 写你选的做法(一句话说清选了什么),options 写你考虑过但没选的其他做法,why 写理由,files 写涉及的文件。
-5. 不确定、但猜错代价小的问题:按你的推荐继续,写进 questions(blocking=false,proceeded_with 写你选的)。
-   猜错代价大,或碰到「必须上报」的情况:停下,不做依赖它的部分,questions 里写 blocking=true,然后结束本次运行。
-6. 不要关闭证书检查、不要跳过钩子、不要为了通过检查删改原有测试。只能改任务单 tests_may_change 允许的测试。
-7. 做完后跑项目的测试和 lint。最终回复只输出符合格式的 JSON 报告,不要别的文字。"""
-
-REPORT_REMINDER = "最终回复只输出 JSON 报告(summary、items、decisions、choices、questions、assumptions、downstream、problems)。"
-
-
-def _items_block(task: dict, ids: list[str]) -> str:
-    out = []
-    checks = {c["id"]: c for c in task["plan"].get("checks", [])}
-    for iid in ids:
-        it = task["items"][iid]
-        out.append(f"- {iid}({it['type']}):{it['title']}")
-        if it.get("files"):
-            out.append(f"  文件范围:{', '.join(it['files'])}")
-        if it.get("follows"):
-            src = task["items"].get(it["follows"], {})
-            commit = src.get("done_commit") or "(见 lead 的最新提交)"
-            out.append(f"  照样例做:{it['follows']}「{src.get('title', '')}」,提交 {commit}")
-        if it.get("decisions"):
-            out.append(f"  引用的决定:{', '.join(it['decisions'])}")
-        for cid in it.get("checks") or []:
-            c = checks.get(cid)
-            if not c:
-                continue
-            if c["kind"] == "command":
-                out.append(f"  验收检查 {cid}:`{c['run']}`(期望 {c.get('expect')})")
-            else:
```
(共 227 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/prompts.py)

### plugin/core/fusion_core/report_schema.json
```diff
@@ -1,66 +1,20 @@
 {
   "type": "object",
   "additionalProperties": false,
-  "required": ["summary", "items", "decisions", "choices", "questions", "assumptions", "downstream", "problems"],
+  "required": ["status", "summary", "questions", "choices", "problems"],
   "properties": {
+    "status": { "type": "string", "enum": ["done", "blocked"] },
     "summary": { "type": "string" },
-    "items": {
-      "type": "array",
-      "items": {
-        "type": "object",
-        "additionalProperties": false,
-        "required": ["id", "status", "note"],
-        "properties": {
-          "id": { "type": "string" },
-          "status": { "type": "string", "enum": ["done", "partial", "not_done"] },
-          "note": { "type": "string" }
-        }
-      }
-    },
-    "decisions": {
-      "type": "array",
-      "items": {
-        "type": "object",
-        "additionalProperties": false,
-        "required": ["ref", "how", "deviation"],
-        "properties": {
-          "ref": { "type": "string" },
-          "how": { "type": "string" },
-          "deviation": { "type": ["string", "null"] }
-        }
-      }
-    },
-    "choices": {
-      "type": "array",
-      "items": {
-        "type": "object",
-        "additionalProperties": false,
```
(共 72 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/report_schema.json)

### plugin/core/fusion_core/state.py
```diff
@@ -1,133 +1,79 @@
-"""从事件重放出当前状态。状态是纯数据(dict),不是数据来源;事件库才是。
-
-任务状态:
-    planned → running → checking → in_review → integrating → accepted
-    running ⇄ blocked(阻塞问题)     checking → running(检查失败,助手修)
-    in_review → running(修改意见)   integrating → in_review(冲突或集成检查失败)
-    终态:accepted、rejected、cancelled
-"""
+"""Replay durable events into the aq task, run, station, and candidate state."""
 
-TERMINAL = ("accepted", "rejected", "cancelled")
+TERMINAL = ("accepted", "cancelled")
 
 
 def empty() -> dict:
-    return {
-        "seq": 0,
-        "decisions": {}, "next_decision": 1,
-        "tasks": {}, "next_task": 1,
-        "runs": {}, "next_run": 1,
-        "stations": {}, "station_seq": {},
-        "questions": {}, "next_question": 1,
-        "candidates": {},
-        "usage": {},
-        "lead_sessions": [],
-        "explore_answers": {},
-        "engine_errors": [],
-    }
+    return {"seq": 0, "tasks": {}, "next_task": 1, "runs": {}, "next_run": 1,
+            "stations": {}, "station_seq": {}, "candidates": {}, "usage": {},
+            "lead_sessions": [], "explore_answers": {}, "engine_errors": [], "next_question": 1}
 
 
 def replay(events: list[dict], state: dict | None = None) -> dict:
-    s = state or empty()
-    for e in events:
-        apply(s, e)
-    return s
+    state = state or empty()
```
(共 458 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/state.py)

### plugin/core/fusion_core/store.py
```diff
@@ -90,8 +90,7 @@ def upgrade(event: dict) -> dict:
 def export_jsonl(conn: sqlite3.Connection, path: Path) -> int:
     events = read(conn)
     with open(path, "w", encoding="utf-8") as f:
-        for e in events:
-            f.write(dumps(e) + "\n")
+        f.writelines(dumps(e) + "\n" for e in events)
     return len(events)
 
 
```

### plugin/core/fusion_core/supervisor.py
```diff
@@ -3,16 +3,27 @@
 命令只写"想要什么"(例如 run_requested),监督者负责"去做"。这样命令很快、可以重复调用;
 动作做到一半崩溃了,下次启动时按状态对账接着做。
 """
+
 
 
+    FusionError,
+    git,
+    globs_overlap,
+    kill_tree,
+    now,
+    pid_alive,
+    redact_file,
+)
 
 
 def _same_area(files: list[str], globs: list[str]) -> bool:
@@ -27,8 +38,13 @@ def _same_area(files: list[str], globs: list[str]) -> bool:
             d = fixed.rsplit("/", 1)[0] if "/" in fixed else ""
             out.add(d)
         return out
+
     a, b = dirs(files), dirs(globs)
-    return any(x == y or (x and y and (x.startswith(y + "/") or y.startswith(x + "/"))) for x in a for y in b)
+    return any(
+        x == y or (x and y and (x.startswith(y + "/") or y.startswith(x + "/")))
+        for x in a
+        for y in b
+    )
 
 
 class Supervisor:
@@ -64,16 +80,26 @@ class Supervisor:
     def prune_runs(self) -> int:
         """runs/ 保留最近 runs_keep_count 次,或 runs_keep_days 天内的运行;只删已经结束的运行。"""
+
         cfg, s = self.cfg(), self.state()
-        keep_n, keep_days = cfg.get("runs_keep_count", 200), cfg.get("runs_keep_days", 30)
-        ended = sorted((r for r in s["runs"].values() if r["status"] == "ended" and r.get("dir")),
```
(共 1094 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/supervisor.py)

### plugin/core/fusion_core/tools.py
```diff
@@ -1,138 +0,0 @@
-"""lead 的工具表:MCP 和命令行共用。说明文字要短,参数说明写在 schema 里。"""
-
-
-_STR = {"type": "string"}
-_STRS = {"type": "array", "items": {"type": "string"}}
-_TASK = {"type": "string", "description": "任务编号,例如 T3"}
-
-PLAN_SCHEMA = {
-    "type": "object",
-    "description": "任务单",
-    "properties": {
-        "goal": {"type": "string", "description": "目标;用户能感知的写成「体验:……」"},
-        "direct": {"type": "boolean", "description": "true = lead 自己做(只写 goal 也行)"},
-        "decisions": {"type": "array", "items": _STR, "description": "引用的决定,例如 D3 或 D3@2"},
-        "bounds": {"type": "object", "description": "三组边界,派工时必须写(可以是空列表)",
-                   "properties": {"must": _STRS, "free": _STRS, "escalate": _STRS}},
-        "items": {"type": "array", "description": "工作项", "items": {"type": "object", "properties": {
-            "id": {"type": "string", "description": "W1、W2……"},
-            "type": {"type": "string", "enum": ["judgment", "mechanical", "verify", "explore"]},
-            "title": _STR,
-            "owner": {"type": "string", "enum": ["lead", "sidekick"],
-                      "description": "默认:judgment 归 lead,其他归 sidekick"},
-            "files": {"type": "array", "items": _STR, "description": "文件范围(glob)"},
-            "decisions": _STRS,
-            "checks": {"type": "array", "items": _STR, "description": "对应的验收检查编号"},
-            "follows": {"type": "string", "description": "照哪个 lead 的 judgment 工作项做(样例)"},
-            "perceivable": {"type": "boolean"},
-            "notes": _STR}}},
-        "checks": {"type": "array", "description": "验收检查", "items": {"type": "object", "properties": {
-            "id": {"type": "string", "description": "C1、C2……"},
-            "kind": {"type": "string", "enum": ["command", "manual"]},
-            "run": {"type": "string", "description": "command:要跑的命令"},
-            "expect": {"type": "object", "description": "command 的期望:exit、contains、regex、passed_min",
-                       "properties": {"exit": {"type": "integer"}, "contains": _STR, "regex": _STR,
-                                      "passed_min": {"type": "integer"}}},
-            "look": {"type": "string", "description": "manual:看什么"},
-            "pass": {"type": "string", "description": "manual:怎样算通过"},
-            "signer": {"type": "string", "enum": ["lead", "user"]}}}},
-        "tests_may_change": {"type": "array", "items": {"type": "object", "properties": {
```
(共 137 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/tools.py)

### plugin/core/fusion_core/util.py
```diff
@@ -2,7 +2,6 @@
 
@@ -18,6 +17,10 @@ IS_WIN = os.name == "nt"
 class FusionError(Exception):
     """给 lead 看的错误:原因写清楚,lead 当场能改。"""
 
+    def __init__(self, message: str, code: int = 1):
+        super().__init__(message)
+        self.code = code
+
 
 def now() -> str:
     return time.strftime("%Y-%m-%dT%H:%M:%S")
@@ -74,9 +77,8 @@ def globs_overlap(a, b) -> bool:
             if glob_match(x2, y2) or glob_match(y2, x2):
                 return True
             px, py = x2.split("*")[0], y2.split("*")[0]
-            if px.startswith(py) or py.startswith(px):
-                if "*" in x2 or "*" in y2:
-                    return True
+            if (px.startswith(py) or py.startswith(px)) and ("*" in x2 or "*" in y2):
+                return True
     return False
 
 
@@ -93,7 +95,7 @@ def run(cmd, cwd, timeout=600, env=None, shell=False, out_file: Path | None = No
     if out_file is None:
         try:
             p = subprocess.run(cmd, cwd=cwd, shell=shell, env=env, stdin=subprocess.DEVNULL,
-                               capture_output=True, timeout=timeout)
+                               check=False, capture_output=True, timeout=timeout)
             out = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
             code = p.returncode
         except subprocess.TimeoutExpired as e:
@@ -104,7 +106,7 @@ def run(cmd, cwd, timeout=600, env=None, shell=False, out_file: Path | None = No
     with open(out_file, "wb") as fo:
         try:
             p = subprocess.run(cmd, cwd=cwd, shell=shell, env=env, stdin=subprocess.DEVNULL,
-                               stdout=fo, stderr=subprocess.STDOUT, timeout=timeout)
+                               check=False, stdout=fo, stderr=subprocess.STDOUT, timeout=timeout)
```
(共 111 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/util.py)

### plugin/core/fusion_core/validate.py
```diff
@@ -1,211 +1,69 @@
-"""校验任务单、意图决定、助手报告。出错时说清原因,让 lead 当场能改。"""
+"""Validation for the public four-field plan and five-field Codex report."""
 
 
 
-TYPES = ("judgment", "mechanical", "verify", "explore")
-CATEGORIES = ("experience", "interface", "rule", "constraint")
-ITEM_ID = re.compile(r"^W\d+$")
-CHECK_ID = re.compile(r"^C\d+$")
+PLAN_FIELDS = ("goal", "brief", "checks", "scope")
+REPORT_FIELDS = ("status", "summary", "questions", "choices", "problems")
 
 
-def _need(cond, msg, errors):
-    if not cond:
-        errors.append(msg)
-
-
-def check_refs(s: dict, refs, errors, where="任务单") -> None:
-    for ref in refs or []:
-        dec, ver = decision_ref(s, ref)
-        if dec is None:
-            errors.append(f"{where}引用的决定 {ref} 不存在")
-        elif dec["status"] != "active":
-            errors.append(f"{where}引用的决定 {ref} 已被取代,请引用新的决定")
-        elif ver != dec["version"]:
-            errors.append(f"{where}引用的是 {ref},但 {dec['id']} 已经是第 {dec['version']} 版;请改成 {dec['id']}@{dec['version']}")
-
-
-def pin_refs(s: dict, refs) -> list[str]:
-    """把不带版本的引用补成当前版本:'D3' → 'D3@2'。"""
-    out = []
-    for ref in refs or []:
-        dec, ver = decision_ref(s, ref)
-        out.append(f"{dec['id']}@{ver}" if dec else ref)
-    return out
-
-
-def plan(s: dict, cfg: dict, p: dict, task_id: str | None = None) -> dict:
```
(共 260 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/validate.py)

### plugin/core/fusion_core/views.py
```diff
@@ -1,453 +1,65 @@
-"""给 lead 看的文字:交接视图(三层)、状态、注入、通知、台账。只读状态,不写事件。"""
+"""Lead-facing status, ledger, and SessionStart usage text."""
 
 
+STATE_CN = {"exploring": "探索中", "explored": "探索完成", "planned": "待派工", "running": "助手在做",
+            "blocked": "待回答", "checking": "检查中", "in_review": "待审", "integrating": "验收中",
+            "accepted": "已验收", "cancelled": "已取消"}
+SESSION_LIMIT = 20
 
-STATE_CN = {"planned": "待开工", "running": "助手在做", "blocked": "等回答", "checking": "检查中",
-            "in_review": "待审", "integrating": "验收中", "accepted": "已验收", "rejected": "已退回",
-            "cancelled": "已取消"}
-KIND_CN = {"implement": "实现", "fix": "修复", "changes": "按意见修改", "answer": "带着回答续做",
-           "report": "补报告", "explore": "只读探索"}
-SIGNAL_CN = {"check_failed": "检查失败", "blocked": "阻塞", "perceivable_touched": "改了用户能感知的文件",
-             "violation": "违规", "stalled": "卡住"}
-SESSION_LIMIT = 100  # SessionStart 注入的总行数上限(角色说明 60 + 状态 40)
+LEAD_GUIDE = """lyfusion 已开:这个项目的代码活交给 Codex 助手做,你(lead)只做 4 件事。
+每条命令都在 Bash 里用 run_in_background 运行。命令自己等到有结果才结束,结束时会叫醒你:
+不要开 Monitor、不要 sleep、不要轮询。醒来后直接读结果文件。
+1. 探索:fusion-core explore - <<'EOF' …… EOF
+   写用户的任务原话(一字不改)和你想知道的,最多 3 条,编号 Q1~Q3。结果:fusion/explore.md
+2. 派工:fusion-core delegate - <<'EOF' {计划} EOF   续用探索的会话。结果:fusion/review.md
+   计划是 JSON:{\"goal\": \"一句话\", \"brief\": \"Markdown 正文\", \"checks\": [{\"run\": \"命令\", \"expect\": 0}], \"scope\": [\"src/**\"]}
+   checks、scope 可省。brief 推荐小标题:目标、决定、不要做的事、已知的坑。
+3. 修改:fusion-core revise - <<'EOF' 修改意见 EOF   自由文字,助手的问题也在这里回答。结果:fusion/review.md
+4. 验收:fusion-core accept   合并、重跑检查、压成 1 个提交、快进主分支。
+跨任务都要守的设计决定写进 fusion/decisions.md(普通文件,直接编辑),引擎每次派工把全文带给助手。
+审查包不够看时,用 Read 看具体文件。看进度 fusion-core status;放弃任务 fusion-core cancel。"""
 
-LEAD_GUIDE = """# Fusion 已打开(lyfusion v5.0.0-a)
-你是 lead:理解用户、做判断、写计划、审查和验收。助手(Codex)在独立的工位目录里按任务单实现。
-工具是 fusion_*(在延迟工具列表里时,先用 ToolSearch 搜 fusion 加载)。任务状态、助手会话、检查证据
-都由引擎记录,你不用自己记会话编号或续用命令。
 
-## 每个任务先用三句话分类
-1. 用户能感知到什么变化?(体验)
-2. 哪些地方要靠判断,换个人做可能不一样?(判断)
-3. 剩下哪些是照着样子就能做的?(机械)
```
(共 496 行,其余用 git diff d3b362bbf67fbfc2c242d5ec4ab477fc9b6fbbcf..HEAD -- plugin/core/fusion_core/views.py)

### plugin/hooks/hooks.json
```diff
@@ -1,14 +1,8 @@
 {
-  "description": "lyfusion:只注入使用说明、状态行和编辑提示;不批准、不阻止任何操作。项目没打开 Fusion 时什么都不输出",
+  "description": "lyfusion:仅在新会话注入 4 个动作的使用说明。项目没打开 Fusion 时什么都不输出",
   "hooks": {
     "SessionStart": [
       { "hooks": [ { "type": "command", "command": "python", "args": ["${CLAUDE_PLUGIN_ROOT}/core/fusion-core.py", "hook", "session-start"] } ] }
-    ],
-    "UserPromptSubmit": [
-      { "hooks": [ { "type": "command", "command": "python", "args": ["${CLAUDE_PLUGIN_ROOT}/core/fusion-core.py", "hook", "prompt"] } ] }
-    ],
-    "PreToolUse": [
-      { "matcher": "Write|Edit|MultiEdit", "hooks": [ { "type": "command", "command": "python", "args": ["${CLAUDE_PLUGIN_ROOT}/core/fusion-core.py", "hook", "pre-edit"] } ] }
     ]
   }
 }
```

### plugin/monitors/monitors.json
```diff
@@ -1,7 +0,0 @@
-[
-  {
-    "name": "fusion-events",
-    "command": "python \"${CLAUDE_PLUGIN_ROOT}/core/fusion-core.py\" --project \"${CLAUDE_PROJECT_DIR}\" events --follow --audience lead",
-    "description": "lyfusion:助手跑完、提阻塞问题、检查出结果、验收结束时通知 lead。项目没打开 Fusion 时不输出任何东西"
-  }
-]
```

## 模型备注(gpt-6-luna):写修改请求时参考
- 改造现有代码时容易改掉原有行为(报错文字、空行和空值的处理、编号规则、路径解析)。动手前先列出要保留的原有行为,逐条写回归测试。出处:fusion-bench C-H2(seed 空库检查、CSV 空白行、next_id)。C-H3(悬挂引用的报错文字、相对路径),2026-11-03,L3。

## 下一步
- 要改:修改请求写进文件(每条一行,行首写编号 R1、R2…),-Task T1 -Model gpt-6-luna -Resume 01a1b5a5-3ca5-7e63-99cc-8142281bd2e8 -MessageFile 文件
- 验收:-Task T1 -Accept -Session lead的会话编号 -Note "看了哪些"
- 整个退回:-Task T1 -Rollback -Session lead的会话编号
