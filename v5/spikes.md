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

## M3 小试验(rc.1 任务 5,2026-11-13)— 等 Lily 上传验证
**问题**:① 上传的插件能不能加载 mod(`hooks/hooks.json` 的 `modules`);② 输入框下方那一行(`SessionMode`/`PromptHint`)能不能画 Fusion 状态灯。不行的话任务 6、7 要换方案。

**为什么由 lead 直接做,不走 Fusion**:要读 Claude Code 自带的 mod 类型文件(在 AppData 里 Claude 的文件夹)、用 Claude Code 的命令检查、由 Lily 上传和看界面;按规则 Codex 不读 Claude 的文件夹、不调用 Claude。

**查文档得到的(本机 Claude Code 2.1.317 的 mod 类型和 reference)**:
- 插件的函数钩子写在一个 hooks 模块里,由 `hooks/hooks.json` 的 `modules` 指定(`.ts`/`.tsx`),导出 `register(on, options)`。已安装的插件(包括"桌面应用从上传保存的插件")是从安装时的副本加载;文档写明 marketplace 安装的、只有 hooks 模块的插件"Installed … Plugin is now active",但没写 claude.ai 上传的插件会不会加载 hooks 模块 → 要实测
- `SessionMode`:输入框底栏右侧的暗色模式标签(`focus`、`memory paused`,用 ` & ` 连起来)。钩子可以改 `modes`(只能是文字),或者**画自己的树**(可以有颜色的 `Text` 和 `Button`)。只在终端和桌面端触发
- `PromptHint`:输入框下方的提示行(`? for shortcuts` 等)。可以改 `hint`、加 `tail`,或画自己的树;`tail` **只有终端画**,其他界面还不画。只在终端和桌面端触发
- `AbovePrompt`:输入框上方的一条,适合点开后的面板
- 颜色可用主题色:`claude`(Claude 橙)、`inactive`(灰)
- 读文件:`$.fs.read(路径)`;项目目录:`$.session.root()`。不用读 `~/.claude`

**试验插件** `v5/spike-mod/lyfusion-spike/`(打包在 `v5/dist/lyfusion-spike-0.1.0.zip`,4 个文件,只读,不写任何文件):
- `SessionMode` 画"●(Fusion 开 = 橙,关 = 灰)+ 可点的 Fusion 按钮",原来的模式标签照样显示在前面;项目里没有 `fusion/local.json` 时不画,交给引擎
- 点 Fusion → `AbovePrompt` 显示一条试验面板:开/关、助手模型、"收起"按钮
- `PromptHint` 加 `tail`" · Fusion on/off"(预计桌面端不显示,用来核对文档)
- 本机没有 `claude` 命令行(桌面应用自带的不在 PATH),**没能跑 `claude plugin validate` 和类型检查**;上传时如果报错,把报错原文记下来

**请 Lily 验证**(结果填在下面):
1. 桌面应用"插件 → 管理插件"上传 `C:\AI WithMe\lyfusion\v5\dist\lyfusion-spike-0.1.0.zip`:能不能上传、有没有提示
2. 开一个新的 Code 会话,目录选 `C:\AI WithMe\lyfusion`(这里 Fusion 是开着的):输入框下方右侧有没有"● Fusion",点是什么颜色
3. 点 Fusion:输入框上方有没有出现试验面板;点"收起"能不能收起
4. 提示行末尾有没有" · Fusion on"(预计没有)
5. 会话里有没有暗色的报错行(例如 `lyfusion-spike: ui.render hook skipped …`),有就抄下来
6. 试完可以在"管理插件"里删掉 lyfusion-spike

**结果**(Lily 2026-11-13 桌面端截图实测,经 lyfusion 会话转达):**通过,任务 6、7 不用换方案**
- 上传的插件能加载 mod(`hooks/hooks.json` 的 `modules`)
- `SessionMode` 能画灯和按钮,Fusion 开着时灯是 Claude 橙
- 点 Fusion,`AbovePrompt` 面板正常显示"● Fusion 开 · 助手 gpt-6-luna(试验面板,只读)"和"收起"按钮
- `PromptHint` 的 `tail` 在桌面端不显示,和文档一致
- 未确认:"收起"按了能不能收起;有没有暗色报错行(截图里没有)
- 已知限制:新建会话时不显示,发出第一条消息后才出现(估计桌面端发第一条消息才启动引擎,插件这边改不了)
- 坑:桌面端把写在 `Button` 前面的 `<Text>●</Text>` 画到了按钮后面,显示成"Fusion ●"。做法:圆点放进按钮里,`<Button …><Text color=…>●</Text> Fusion</Button>`

**Lily 的决定(写进 rc-brief 任务 6)**:圆点和 Fusion 在同一个框里,圆点在左("● Fusion");面板和状态灯的前端(mod)由 lead 自己写,不派给助手;引擎要加的命令照常走 Fusion。lead 定:mod 不直接写 `local.json`,改设置一律调用引擎命令(`fusion-core config …`),校验和格式版本只在引擎一处管;下拉框和上下文设置的可选值也从引擎命令拿,不在 mod 里写死
