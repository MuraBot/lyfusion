# M0 预研结论

> 版本:Codex CLI 0.166.0-alpha.6(Codex App 26.1029 自带);Python 3.12.10;sqlite 3.49.1;git 2.54。

## S1 会话编号和续用 — 通过
- `codex exec --json` 的第一条事件是 `{"type":"thread.started","thread_id":"<uuid>"}`,引擎从这里取会话编号
- `codex exec resume <id> "<提示>"`:
  - **没有 `-s`、`-C` 参数**。换沙箱用 `-c sandbox_mode="workspace-write"`;工作目录用子进程的 cwd(设成工位目录)
  - 从只读换成可写:可以,文件写进去了
  - 换模型 `-m gpt-6-astra`:可以,而且记得上一步做了什么
- 用量:每轮结束的 `turn.completed` 带 `usage`:`input_tokens`、`cached_input_tokens`、`cache_write_input_tokens`、`output_tokens`、`reasoning_output_tokens`。这是**一整轮**(多次请求)的合计,不是单次请求
  - 影响:"当前上下文"只能估算。引擎用"本轮输入 ÷ 本轮的请求次数(命令和消息条目数 + 1)"估,换工位阈值按这个估值算
- 示例:`v5/spike-scripts/spike_s1_s6.py`

## S6 沙箱边界 — 通过(有一个注意点)
- 工位是 git worktree,Codex 用 `-s workspace-write -C <工位目录>`:
  - 写工位目录内:可以
  - 写工位目录外(`../outside.txt`):**被拒绝**(PermissionDenied)
  - `git add`、`git switch`:**被拒绝**,因为 worktree 的 git 元数据在主仓库的 `.git/worktrees/` 里,沙箱把 `.git` 设成只读
- 注意点:系统临时目录(`%TEMP%`)默认可写。第一次测试把工位放在临时目录里,"目录外"的写入就成功了。工位目录不能放在临时目录里;引擎在 `preflight` 里检查
- 结论:"事前阻止"这一层成立:助手不能提交、切分支、写项目外的文件。提交只能由引擎做

## S2 Python MCP 服务器 — 通过(会话关闭后子进程是否还活着待补)
- 探针插件(zip 上传安装)在 `probe-project` 的新会话里:Python 标准库写的 stdio MCP 服务器正常握手、列工具、被调用
  - Claude Code 先发了一个 `server/discover`,再发 `initialize`。不认识的方法回 -32601 错误即可,不影响使用
  - 工具名:`mcp__plugin_<插件名>_<服务器名>__<工具名>`(例如 `mcp__plugin_fusion-probe_probe__probe_info`)
  - **工具默认在延迟列表里**,会话一开始显示 "still connecting",lead 要用 ToolSearch 搜一下才能调用。已写进 lead 的使用说明
  - 环境:`CLAUDE_PROJECT_DIR` 是项目目录,工作目录也是项目目录;`CLAUDE_PLUGIN_ROOT` 是插件的安装目录
- 分离子进程:在 Claude Code 里 `CREATE_BREAKAWAY_FROM_JOB` **成功**(在普通终端里会失败,所以代码两种都试)。子进程按时写心跳
- 待补:会话关闭(归档)后子进程还在不在。归档要 Lily 同意,收尾时一起做

## S3 PreToolUse 编辑提示 — 通过
- 钩子的输入里有 `tool_input.file_path`
- `hookSpecificOutput.additionalContext` 不阻止编辑;提示出现在 Edit 工具结果的后面,原样是 `PreToolUse:Edit hook additional context: …`
- 同一次测试里,`SessionStart`(source=startup)和 `UserPromptSubmit` 注入的文字也都进了上下文

## S4 monitor 通知 — 没有触发(原因待查)
- 探针的 monitor 应该在第 4、8 分钟各打印一行,并在 `.probe/monitor.log` 记一笔。8 分钟内两样都没有出现
- 可能:monitor 没被启动;或者它拿到的 `CLAUDE_PROJECT_DIR`、工作目录不是项目目录,被探针自己的项目检查挡掉了
- 影响:设计 6.6 已有降级方案(没有通知时,等待列表靠每次提问注入的状态行)。lead 的说明里写了"不用轮询",但没有通知时要靠状态行提醒
