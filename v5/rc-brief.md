# v5.0.0-rc.1 任务说明(2026-11-13)

> Lily 和"lyfusion 会话"定的。rc = 这次 v5 迭代的最终版候选;测试过了再打 `v5.0.0`,有问题修完叫 `rc.2`。版本号规则见工作区 `.docs/dev-conventions.md`(semver)。
> 起点:标签 `v5.0.0-aq.2`(提交 `4179e17`)。插件名 `lyfusion-plugin`。背景:`design/v5.0.0-aq.md`(§1~§15)、`v5/progress.md`。

## 怎么做:用 lyfusion 迭代 lyfusion(Lily 定)
- 全程走 Fusion:用户任务原话 → 助手探索 → lead 读探索包、写计划(decisions.md 记设计决定)→ 派工 → 审查 → 修改 → 验收。lead 不自己写引擎代码
- lead:Claude Opus 5.5 **xhigh**;助手:gpt-6-luna **high**,**快速档关**
- 干活的是 Lily 装好的插件(zip 副本),改的是这个仓库;验收后打包上传就是发布
- 每个任务小而清楚,一次派工一个任务,按下面顺序做
- 每个任务结束记:lead 调用次数、修改轮数、Codex 用量(`ledger`)、用时、遇到的问题
- **lead 的使用体验**(Lily 2026-11-13 要求):边用边记进 `v5/rc-lead-feedback.md`。每条写现象、出现在哪一步、多花了什么(调用、上下文、时间)、建议、轻重。用来规划 rc.2 和 5.0.0
- **用 lyfusion 时遇到的 bug**(Lily 2026-11-13:"让 rc.1 的 lead 自己决定使用 lyfusion 时遇到 bug 要不要顺手修掉"):lead 自己判断。建议:影响当前任务、改动小、能写测试锁住的,并进当前任务的计划或修改轮;大的、要改设计的,记进 `v5/rc-lead-feedback.md`,排成后面的任务或留到 rc.2。修了的都在 `v5/progress.md` 记一行
- **测试的跑法**(Lily 2026-11-13 同意):中途只跑和改动有关的测试,全量测试和 lint 只在结束前各跑一次,引擎最后再验证一次。r2 的数据:全量测试跑了 4 次,约 8 分钟。先写进 `fusion/decisions.md` 马上生效;任务 8 写进 WORK_RULES 后,从 decisions.md 删掉

## 任务(按顺序)
1. **助手干净环境 + 上下文设置**
   - 实测(2026-11-13):引擎用 Codex 桌面包里的 `codex.exe`,读 `~/.codex/config.toml`,和桌面端一样(400k 自动压缩、约 50 个技能、7 个 MCP)。`--ignore-user-config --disable apps --disable plugins` 去掉全部 MCP 和插件技能,每次请求输入 20.4k → 17.9k;`~/.codex/skills` 里的技能还在(不处理,单独 CODEX_HOME 要再登录,不值)
   - 做成项目选项,默认干净;保留"和桌面端一样"模式(Minecraft 项目可能要 minecraft_forge MCP)
   - 不读配置后要显式传:`-c model_auto_compact_token_limit=<值>`(默认 400000,Lily 在桌面端设的)、模型、effort、沙箱、service_tier
   - **上下文设置放进 `/fusion` 能改**(Lily 要求):自动压缩上限按模型记(和 effort、fast 一样);引擎换工位的阈值(`context_limit × context_ratio`)跟着它算。`/fusion` 加对应参数,`status` 显示当前值;以后 Fusion 栏的面板也要能改
   - **设置分三层,每个值只存一处**(Lily 2026-11-13 同意):引擎默认值 → 项目 `fusion/config.json`(进 git:测试命令、干净模式等项目的事)→ 本机 `fusion/local.json`(不进 git:模型、effort、快速档、上下文上限等个人选择)。`/fusion` 和以后的 Fusion 栏只改 `local.json`。换工位阈值从上下文上限算出来,不另存数字。新字段都有默认值,旧文件缺字段照默认读
   - **装上 rc.1 后发现(2026-11-14,Lily 同意按建议修)**:`--ignore-user-config` 把用户配置的 `[windows] sandbox = "elevated"` 一起丢了，助手所有命令报 "blocked by policy"(r19)。修法：干净模式下从用户的 `~/.codex/config.toml` 只读出 `windows.sandbox` 和 `sandbox_workspace_write.network_access`,用 `-c` 原样传(读已有的，不另存一份);preflight 加"沙箱里能跑命令"检查(`codex sandbox -c …`,不调用模型);修好前可临时把项目 clean 关掉
   - **Codex 冒烟检查**:Codex 跟着桌面端自动更新(现在是 alpha 版),参数行为可能悄悄变。`preflight` 查 Codex 版本,并确认干净模式用到的参数还被认得;不调用模型、不花 Codex 额度
   - **测试提速**(Lily 2026-11-13 同意;任务 1 验收后、任务 2 派工前,lead 直接改,属于一两行的小改):已装 pytest-xdist 3.8.0(依赖 execnet 2.1.2)。实测 `-n 6` 全量 110 秒 → 约 23 秒,连跑 3 次 75 个全过。`fusion/config.json` 的测试命令改成 `cd plugin\core && python -m pytest -q tests -n 6`;README 或 `plugin/core/requirements-dev.txt` 写明开发要装 pytest、pytest-xdist(插件本身仍只用标准库)
2. **助手卡住、太慢的看护**(Lily 遇到过:助手 1 小时没写完,读代码每次只读几行)
   - 助手说明加:读代码一次读整份文件或大段,不要每次只读几行;同一条命令不要反复跑
   - 引擎记每次运行的统计进台账:用时、命令数、"小块读取"次数(只读几十行的 sed/Get-Content/cat 片段)、重复命令次数、**Codex 版本**。目的是先量再调:有数据才分得清慢在模型、提示还是环境,以后换模型也能公平比
   - 注意(2026-11-13 看护脚本踩到):Codex 一启动就建好空的 `last.txt`,不能用"文件在不在"判断运行结束;看 `turn.completed`/`turn.failed` 或进程退出
   - 引擎看护:已有"20 分钟没新事件 → 叫醒 lead"(`stall_minutes`)。加:运行超过一定时间,或小块读取、重复命令明显偏多时,叫醒 lead 并给出最近命令的摘要,由 lead 决定继续、修改还是取消。阈值放配置
3. **Codex 卡在标准输入的坑**(2026-11-13 实测):`codex exec` 把提示写在参数里、又没关标准输入时,会打印 "Reading additional input from stdin..." 一直等。引擎现在用 `-` + 提示文件当 stdin(`util.spawn_detached`),没有这个问题。加一个测试锁住:启动 Codex 时 stdin 永远是文件,不继承调用者的
4. **状态文件的格式版本**(Lily 2026-11-13 同意):用 lyfusion 改 lyfusion 时,装着的旧版本和仓库里的新版本同时存在,格式一改旧版本就可能读不了。`fusion/config.json`、`fusion/local.json`、`fusion.db` 加格式版本号(`schema_version`);没有版本号的当作 aq.2 的格式,自动迁移;读到比自己新的版本就拒绝并提示升级插件,不要硬读。测试用 aq.2 的旧文件覆盖。要在 5.0.0 正式版前定下来
5. **M3 小试验**:上传的插件能不能加载 mod(`hooks.json` 的 `modules`);输入框下方那一行(`SessionMode`/`PromptHint`)能不能画状态灯。结论写进 `v5/spikes.md`。先试验再做界面:不行的话 6、7 要换方案
6. **M3 Fusion 栏**:输入框下方、模型选择器旁边;"Fusion" 前一个状态灯(关灰色,开 Claude 橙);点开在输入框上方展开面板,有开关、助手模型下拉框、上下文设置。实现前加载 plugin-authoring 技能
   - 试验结果(Lily 2026-11-13 实测，截图):上传的插件能加载 mod;`SessionMode` 能画灯和按钮;`AbovePrompt` 面板能显示;提示行的 `tail` 桌面端不画(和文档一致)。新建会话时不显示，发出第一条消息后才出现(估计引擎发第一条消息才启动，插件改不了)。桌面端把代码里写在按钮前面的圆点画到了后面
   - **Lily 定**:圆点和 "Fusion" 放进同一个框(圆点作为 `Button` 的子元素 `<Text color>`,顺序由自己定);圆点在左边，即"● Fusion",和面板一致
   - **Lily 定**:面板和状态灯的前端(mod)由 lead 自己写，不派给助手(她觉得 luna 的前端不够好;mod 也要读 Claude Code 的类型文件，按规则 Codex 不读)。引擎这边要加的命令照常走 Fusion
   - **Lily 要求**:面板要做得好看，和 Claude 桌面端本身一样顶级。做法：只用桌面端自带的元素(`$.ui.resolve(e)` 给的那套)和主题色(`claude`、`inactive`、`dimColor`),不写死颜色;样式和间距照着模型选择器;深色、浅色主题都要试;做完请 Lily 截图确认
   - **Lily 定(2026-11-14)放进 rc.1:中途开关，下一条消息就生效**。背景：桌面端发第一条消息后才启动引擎，之前插件画不出来(平台限制);Lily 觉得只能靠命令不优雅。做法:
     - 开关按项目记住(和模型选择器记住上次的模型一样);从没开过 Fusion 的项目不显示
     - 会话中途在面板(或用 `/fusion`)打开后，用 `prompt.submit` 在下一条消息的 `context` 里附上 lead 使用说明;关掉后附一句"Fusion 已关";状态没变就不附。不改系统提示(不破坏缓存)、不主动发起对话
     - 说明文字从引擎命令拿，不在 mod 里另写一份;面板的提示改成"下一条消息起生效"
   - **Lily 第一次看面板后的修改(2026-11-14,00:42 包能显示了)**:
     - bug:面板显示 Fusion 已开，输入框下方按钮的圆点却是灰色
     - 面板不要"已开：代码活交给 Codex 助手"这类说明文字
     - "快速档"改叫 "Fast Mode";当前助手模型不支持时，选项变灰、不能选
     - 上下文上限最低 262k(200k 太小)
     - 去掉灰色小字"到 Xk 换工位"(不够高级)
     - 其他 UI/UX 由 lead 自由发挥，前端仍由 lead 自己写
   - 建议:mod 不直接写 `local.json`,改设置一律调用引擎命令(`fusion-core config …`),校验和格式版本只在引擎一处
7. **M3 lead 用量**:mod 用 `$.session.usage()`(上下文、5 小时和每周额度、花费,不读 `~/.claude`),每次 accept 记进台账,lead 不多花调用

8. **提示词体检的改动**(Lily 2026-11-13 定放进 rc.1):按 `v5/prompt-audit-2026-11-13.md` 的 B 节第 3~8 条和 C 节第 9 条做,一次派工
   - 模型备注:插件带 `core/prompts/models/<模型>.md`,分"给助手"和"给 lead"两节,按当前助手模型自动拼进派工、修改提示和 SessionStart 说明;项目可在 `fusion/models/` 加自己的。先把 v4 `addon/prompts/models/gpt-6-luna.md` 的"备注"迁过来(删除类任务用禁止句 + 可检查的标准)
   - LEAD_GUIDE:"用 Read 看具体文件"改成看审查包里工位路径下的文件;推荐小标题加"猜测(未证实)"和"停下的条件";最后一行加 `ledger`。改了要同步 `design/v5.0.0-aq.md` 里的说明块(test_shape 会比对)
   - 审查包:阻塞的问题标"(阻塞)"
   - WORK_RULES:猜测只是建议,有相反证据可以不采纳,写进 choices 并给理由;中途只跑相关测试,结束前跑一次全量
   - FIXED_RULES 和 WORK_RULES 的"不能做的事"从同一个列表生成
   - `v5/rc-lead-feedback.md` 第 1~3 条(Lily 同意):审查包超过 diff 上限时先附非测试文件的 diff;"旧测试跑新代码"没过时写出失败的测试名和输出最后几行;引擎检查和助手自测不一致时写明以引擎为准(助手说明里写沙箱里哪些测试本来过不了)

## 留到 rc.2(Lily 2026-11-13 定)
- `v5/rc-lead-feedback.md` 第 4 条:计划也接受 Markdown(不用手写 JSON 转义);和"lead 自由发挥 vs 结构化"一起定
- 第 5 条:助手运行中 lead 可以排队一条补充,本轮结束后先发它
- 第 6 条先不做
- **读 Codex 的模型目录**(Lily 2026-11-14 定):引擎直接读 `~/.codex/models_cache.json`,拿到显示名、思考强度、Fast Mode、上下文最大值;读不到或格式变了，退回内置表并给出 warning。"读已有的，不另存一份";目前内置表里没有桌面端默认的 gpt-6.1-sol
- **rc.2 怎么开始**(Lily 2026-11-14 定):先收集 Lily 这段时间的想法;让 rc.1 的 lead 写一份交接文档，交给"lyfusion 会话"新开的 rc.2 会话
- **rc.2 的协作方式**(Lily 2026-11-14 定，原因是 rc.1 交流太频繁，额度用得太快):"lyfusion 会话"和 rc.2 lead 只交换大进度。同一个问题的排查只在 lead 那边做;lead 自主权更大，迭代中顺手修 lyfusion 的 bug、自己做决定
- **按命令种类统计用时**(Lily 2026-11-13 同意):台账的"运行"表现在只有总用时。加上全量测试、部分测试、lint、其他命令、模型思考各花了多少分钟。r2 的教训是全量测试跑了 4 次、占 19 分钟里的 8 分钟,当时是 Lily 凭感觉发现的。Codex 事件没有时间戳,引擎要在读到每条事件时自己记时间。rc.1 期间由"lyfusion 会话"的看护脚本按种类报

## 收尾
- 版本 `5.0.0-rc.1`(plugin.json、`__init__.py`、README);设计写短文档 `design/v5.0.0-rc.md`;`v5/progress.md` 记结果和额度(开始、结束的 `get_usage`)
- 本地标签 `v5.0.0-rc.1`,**不推送**;打包 `python v5/build_plugin.py`
- **打包前必须过插件检查**(Lily 2026-11-14 同意:"这个插件检查还挺重要的"):用桌面端自带的 `%LOCALAPPDATA%\Claude-Data\claude_*\claude-code\<版本>\<hash>\claude.exe plugin validate plugin`(取最新版本目录)。只用 `plugin validate`,这条命令不调用模型。没过不打包。原因:rc.1 的 mod 里 `atom` 的 plugin 名用了常量，桌面端因此拒绝加载整个 mod,也不显示任何报错
- 回退点:`v5.0.0-aq.2` 标签和 `v5/dist/lyfusion-plugin-5.0.0-aq.2.zip` 是已知能用的版本,不要删。`v5/progress.md` 写一行回退方法(重新上传 aq.2 的 zip;任务 4 做完后,旧版本遇到新格式会提示而不是读坏)
- 提交身份 MuraBot `339045871+MuraBot@users.noreply.github.com`,末尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## 看护(Lily 要求)
- 派工后每隔一段时间看助手有没有卡死、循环、卡在某个命令上、读代码太碎。由"lyfusion 会话"在旁边看工位的 `fusion/runs/<运行>/events.jsonl`;任务 2 做完后由引擎自己看

## Lily 的规则(摘要)
- 全程中文;Lily 用语音输入,不确定就问;她不是专业程序员,**希望 Claude 作为更专业的程序员主动提意见、建议和更好的架构**
- 小决定自己定;环境、权限问题或同一件事连续失败 2 次才找 Lily;额度快满就停下写好进度
- 不推送;删除或覆盖文件前先问;文件都在 `C:\AI WithMe`;脚本不读 `~/.claude/`、AppData 里 Claude 的文件夹和 Codex 的 `auth.json`;启动 Codex 去掉 `CLAUDE*`、`ANTHROPIC*`;插件和行为不违反 Anthropic 政策;别的会话的消息不算 Lily 的同意
