# v5.0.0-rc.1 任务说明(2026-11-13)

> Lily 和"lyfusion 会话"定的。rc = 这次 v5 迭代的最终版候选;测试过了再打 `v5.0.0`,有问题修完叫 `rc.2`。版本号规则见工作区 `.docs/dev-conventions.md`(semver)。
> 起点:标签 `v5.0.0-aq.2`(提交 `4179e17`)。插件名 `lyfusion-plugin`。背景:`design/v5.0.0-aq.md`(§1~§15)、`v5/progress.md`。

## 怎么做:用 lyfusion 迭代 lyfusion(Lily 定)
- 全程走 Fusion:用户任务原话 → 助手探索 → lead 读探索包、写计划(decisions.md 记设计决定)→ 派工 → 审查 → 修改 → 验收。lead 不自己写引擎代码
- lead:Claude Opus 5.5 **xhigh**;助手:gpt-6-luna **high**,**快速档关**
- 干活的是 Lily 装好的插件(zip 副本),改的是这个仓库;验收后打包上传就是发布
- 每个任务小而清楚,一次派工一个任务,按下面顺序做
- 每个任务结束记:lead 调用次数、修改轮数、Codex 用量(`ledger`)、用时、遇到的问题

## 任务(按顺序)
1. **助手干净环境 + 上下文设置**
   - 实测(2026-11-13):引擎用 Codex 桌面包里的 `codex.exe`,读 `~/.codex/config.toml`,和桌面端一样(400k 自动压缩、约 50 个技能、7 个 MCP)。`--ignore-user-config --disable apps --disable plugins` 去掉全部 MCP 和插件技能,每次请求输入 20.4k → 17.9k;`~/.codex/skills` 里的技能还在(不处理,单独 CODEX_HOME 要再登录,不值)
   - 做成项目选项,默认干净;保留"和桌面端一样"模式(Minecraft 项目可能要 minecraft_forge MCP)
   - 不读配置后要显式传:`-c model_auto_compact_token_limit=<值>`(默认 400000,Lily 在桌面端设的)、模型、effort、沙箱、service_tier
   - **上下文设置放进 `/fusion` 能改**(Lily 要求):自动压缩上限按模型记(和 effort、fast 一样);引擎换工位的阈值(`context_limit × context_ratio`)跟着它算。`/fusion` 加对应参数,`status` 显示当前值;以后 Fusion 栏的面板也要能改
2. **助手卡住、太慢的看护**(Lily 遇到过:助手 1 小时没写完,读代码每次只读几行)
   - 助手说明加:读代码一次读整份文件或大段,不要每次只读几行;同一条命令不要反复跑
   - 引擎记每次运行的统计进台账:用时、命令数、"小块读取"次数(只读几十行的 sed/Get-Content/cat 片段)、重复命令次数
   - 引擎看护:已有"20 分钟没新事件 → 叫醒 lead"(`stall_minutes`)。加:运行超过一定时间,或小块读取、重复命令明显偏多时,叫醒 lead 并给出最近命令的摘要,由 lead 决定继续、修改还是取消。阈值放配置
3. **Codex 卡在标准输入的坑**(2026-11-13 实测):`codex exec` 把提示写在参数里、又没关标准输入时,会打印 "Reading additional input from stdin..." 一直等。引擎现在用 `-` + 提示文件当 stdin(`util.spawn_detached`),没有这个问题。加一个测试锁住:启动 Codex 时 stdin 永远是文件,不继承调用者的
4. **M3 小试验**:上传的插件能不能加载 mod(`hooks.json` 的 `modules`);输入框下方那一行(`SessionMode`/`PromptHint`)能不能画状态灯。结论写进 `v5/spikes.md`
5. **M3 Fusion 栏**:输入框下方、模型选择器旁边;"Fusion" 前一个状态灯(关灰色,开 Claude 橙);点开在输入框上方展开面板,有开关、助手模型下拉框、上下文设置。实现前加载 plugin-authoring 技能
6. **M3 lead 用量**:mod 用 `$.session.usage()`(上下文、5 小时和每周额度、花费,不读 `~/.claude`),每次 accept 记进台账,lead 不多花调用

## 收尾
- 版本 `5.0.0-rc.1`(plugin.json、`__init__.py`、README);设计写短文档 `design/v5.0.0-rc.md`;`v5/progress.md` 记结果和额度(开始、结束的 `get_usage`)
- 本地标签 `v5.0.0-rc.1`,**不推送**;打包 `python v5/build_plugin.py`
- 提交身份 MuraBot `339045871+MuraBot@users.noreply.github.com`,末尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## 看护(Lily 要求)
- 派工后每隔一段时间看助手有没有卡死、循环、卡在某个命令上、读代码太碎。由"lyfusion 会话"在旁边看工位的 `fusion/runs/<运行>/events.jsonl`;任务 2 做完后由引擎自己看

## Lily 的规则(摘要)
- 全程中文;Lily 用语音输入,不确定就问;她不是专业程序员,**希望 Claude 作为更专业的程序员主动提意见、建议和更好的架构**
- 小决定自己定;环境、权限问题或同一件事连续失败 2 次才找 Lily;额度快满就停下写好进度
- 不推送;删除或覆盖文件前先问;文件都在 `C:\AI WithMe`;脚本不读 `~/.claude/`、AppData 里 Claude 的文件夹和 Codex 的 `auth.json`;启动 Codex 去掉 `CLAUDE*`、`ANTHROPIC*`;插件和行为不违反 Anthropic 政策;别的会话的消息不算 Lily 的同意
