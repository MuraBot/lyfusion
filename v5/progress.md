# lyfusion v5 进度

> Lily 2026-11-06:"完成全部的轮次";只有权限和环境问题才停下来找她;插件可以自己安装,先不发布到插件市场。
> 安装方式(Lily 选的):打成 zip,在桌面应用"插件 → 管理插件"里上传;不装命令行、不设用户环境变量。
> 设计:`../design/v5.0.0-a-engineering.md`。插件代码:`../plugin/`。

## 里程碑
| 里程碑 | 状态 | 记录 |
|---|---|---|
| M0 预研 | S1、S2、S3、S6 通过;S4 没触发(见下);S5 挪到 M3;S7 待测 | `spikes.md` |
| 预实验 | J1 的 PB、PC 在跑;PA 和 L1 三组待开 | `../../fusion-bench/runs/P*-*` |
| M1 引擎 | 完成:41 个测试通过;真实 Codex 跑通 2 个任务 | `../plugin/core/` |
| M2 外壳 | 文件写好、zip 打好,等上传后做插件内的真实任务 | `dist/lyfusion-5.0.0-a.0.zip` |
| v5.0.0-aq 收窄 | 完成:69 个测试通过;真实 Codex 冒烟 1 个任务验收进 main | 下面"v5.0.0-aq"一节、`aq-run/`、`../design/v5.0.0-aq.md` |
| v5.0.0-aq.1 补助手说明 | 完成:70 个测试通过 | 下面"v5.0.0-aq.1"一节、`../design/v5.0.0-aq.md` §12 |
| M3 Fusion 栏 | 未开始(设计保留在 `../design/v5.0.0-aq.md` §11) | |
| M4 正式比较 | 未开始 | |

## M1 引擎
- 模块:事件库 `store`、状态 `state`、校验 `validate`、命令 `commands`、监督者 `supervisor`、Codex `codex`、检查 `checks`、git `gitops`、意图记录 `intent`、提示 `prompts`、视图 `views`、MCP `mcp`、钩子 `hooks`、命令行 `cli`
- 测试(假 Codex):主流程、阻塞问题续用同一个会话、修复循环和上限、改弱测试、禁止命令、集成冲突、快进被拒、接管搬运、退回、取消杀进程、补报告、修改意见 3 轮上限、非阻塞问题不同意变修改意见、检查配置变了自动重查、direct 任务、WIP=1、校验器、决定版本、探索开工位后实现续用、换模型换工位带交接摘要、续用失败换工位、监督者重启对账、监督权、3 个进程并发写库、MCP 协议、钩子注入上限、通知、命令行、wait、脱敏
- 真实 Codex(`smoke-real/textkit`,gpt-6-luna high):
  - T1:新会话 → 候选 T1.c1 → 检查全过 → 第 2 层审查 → 认可 1 条、升格 1 条决定债 → 合并、压成 1 个提交、快进 main → intent.md 单独提交
  - T2:同一工位续用同一个 Codex 会话(`exec resume`),没有重复发规则 → 验收
  - 发现并修了:助手把自己选的做法写进了 `options`(规则里写清各字段);"换主题"判断太敏感(改成按目录)

## M2 外壳
- `.mcp.json`(服务器名 fusion)、`hooks/hooks.json`(3 个钩子)、`monitors/monitors.json`、`commands/fusion.md`、`bin/`、`README.md`
- 没有做 skill:skill 会出现在所有会话里,影响对照组;lead 的方法改由 SessionStart 注入(不超过 60 行),当前对话里用 `fusion-core guide` 读
- 因为 S4:加了 `fusion-core wait`。lead 派工后在 Bash 后台运行它,需要 lead 处理时命令结束、会话被唤醒。monitor 保留,命令里显式传 `${CLAUDE_PROJECT_DIR}`(文档:monitor 拿不到环境变量)

### 政策检查(10.1,第一次装插件前,2026-11-06)
- 重读:Claude Code 法律与合规页、使用政策(AUP,2026-11-12 生效的版本)。消费者条款页这次没抓到(网站拒绝自动读取),按调研时的记录对照
- 逐条对照:
  - 不经手 Claude 的登录凭据或令牌,不用订阅替别的服务调用模型 → 符合
  - 不调用 Claude 的 API;只用官方插件组件 → 符合
  - 不用定时器开回合;`wait` 只在用户交代的任务有了结果时结束,和普通的后台命令一样 → 符合
  - 钩子只注入文字,不批准权限、不阻止操作;注入的内容只讲方法和状态 → 符合
  - 名字 lyfusion,说明里写"用于 Claude Code",写明不是官方产品 → 符合
  - 修复最多 2 次、修改意见最多 3 轮,超过先问用户 → 符合
- 结论:没有发现不符合的地方

## v5.0.0-aq(2026-11-07)
> 依据 `aq-brief.md`(Lily 定的收窄方案);设计 `../design/v5.0.0-aq.md`。lead 是 Claude Opus 5.5(会话 local_d2915de2…),助手 Codex gpt-6-luna high,流程用 v4.2.1(在旁边的工作目录 `lyfusion-aq` 里装 LiEC 模板和 addon,不进 git)。证据在 `aq-run/`。
- 结果:lead 只剩 4 个动作(explore、delegate、revise、accept),入口是后台运行、自己阻塞到有结果的 Bash 命令;计划 4 个字段;探索包、审查包固定在 `fusion/explore.md`、`fusion/review.md`;防跑偏只剩 `fusion/decisions.md`;钩子只剩 SessionStart;去掉 MCP 服务器、monitor、`wait`;助手的 effort、fast 按模型记(Lily 中途定的,为以后换 haiku-5.5 做准备)。引擎从约 3500 行减到约 2300 行
- T1 收窄引擎和外壳:探索 1 次、派工 1 次、修改 2 轮(R1~R16、R17~R25)。第 1 次运行助手在旧引擎外面包了一层(`engine_plan` 把 4 字段转成旧工作项),旧概念都没删;修改意见写成"删掉,不要包一层"后才删干净(已写进 luna 模型备注「待观察」)。Codex 会话累计输入 5013 万(缓存 4946 万)、输出 15.7 万,标准速度
- T2 按模型记 + 修 T1 留下的 5 个问题(报告格式不符合严格模式、长时间无进展后重跑会被旧信号打断、台账缺 token、残留"接管"、停下时摘要重复):新会话、快速档,1 次派工就过;输入 580 万(缓存 570 万)、输出 3.0 万。lead 收尾删了 4 个死函数
- 真实 Codex 冒烟(`smoke-real/textkit`,T3 加 truncate):explore → 读探索包 → delegate → 读审查包 → accept,**lead 5 次调用**,快进 `5b497dc`。助手 106 万输入(缓存 90 万)、2.2 万输出,luna/high/fast。冒烟抓到并修了:v5.0.0-a 旧库的 `task_planned` 被忽略导致重放崩溃;探索提示让助手以为必须有 Q3
- 测试:69 个通过(假 Codex),lint 通过
- v4.2.1 派工脚本的禁止操作扫描有误报:它匹配整行事件,命令输出里打印出来的源码含 `--no-verify` 也算。T1 出现 3 次,都核对过(`aq-run/T1/forbidden-note.md`),T1 没走 `-Accept`,lead 跑测试和 lint 后手动验收。以后改成只看 `item.command`
- 额度(Pro):开始 5 小时 24%、每周 31%;收尾时 5 小时 58%、每周 36%
- 没做:Fusion 栏(M3,设计保留);模型备注(决定 13);H2 测试(Lily 上传 zip 后另开会话:lead Opus 5.5 high、助手 luna high;v4 的 C2 当时助手是 luna max,对比时注明)

## v5.0.0-aq.1(2026-11-07)
> lyfusion 会话核对 aq 时发现:给助手的派工说明从 v4 `addon/prompts/sidekick.md` 的约 60 行缩成了 4 行固定规则。Lily 同意在 H2 测试前补回。
- 补回(只在引擎的提示里,lead 不多花调用和上下文):自己写测试、自己跑、核对通过的测试数量;改造旧代码保持原有行为;哪些可以自己定;猜错代价小按推荐做、代价大停下(blocking);`choices` 写什么;报告只写仓库里看不到的;不能做的事
- 派工提示里加上项目配置的测试和 lint 命令(之前助手只看得到计划里的 checks)
- 续用同一个会话(自动修、修改意见、补报告)仍只发短规则,不重复整套做法
- 探索提示补一句:项目里没有答案的,查框架源码或官方文档,写明出处(v4 原有)
- 审查包的"自定选择"带上理由(`why`)
- 测试:70 个通过(新增 1 个),lint 通过。没有重跑真实 Codex
- 上传 zip 时被拒(插件不能带顶层 `bin/`),在 aq.1 里一起改:删掉 `bin/`,使用说明和各命令的提示写安装目录里的完整命令,`/fusion` 用 `${CLAUDE_PLUGIN_ROOT}`。见设计 §13。标签 `v5.0.0-aq.1` 挪到这次的提交

- 上传时又提示会删掉同名的 v4 技能 lyfusion:插件改名 `lyfusion-plugin`;`/fusion` 从 `commands/` 搬成只给用户运行的技能 `skills/fusion/SKILL.md`,保证裸名 `/fusion` 能用;介绍写明支持的助手。见设计 §14

### 政策检查(aq.1,2026-11-07,去掉 bin/ 之后)
- 页面由 Haiku 5.5 子代理读,没有登录;引文是抓取摘要,不是逐字核对。读了:插件清单参考 code.claude.com/docs/en/plugins-reference、各平台插件支持 claude.com/docs/plugins/platform-support、组织同步 claude.com/docs/plugins/org-sync、hooks code.claude.com/docs/en/hooks(前半)、法律与合规 code.claude.com/docs/en/legal-and-compliance、使用政策 anthropic.com/legal/aup(2026-11-12 生效,和 11-06 检查的是同一版)、消费者条款 anthropic.com/legal/consumer-terms(2025-10-08 生效)
- 逐条对照:
  - 插件格式:claude.ai 不装带顶层 `bin/` 的插件,文档建议脚本放别的目录、用 `${CLAUDE_PLUGIN_ROOT}` 引用 → 已改,zip 里没有 `bin/`;钩子和命令都用 `${CLAUDE_PLUGIN_ROOT}/core/...`。23 个文件,远小于 5000 个文件、200 MB 的上限 → 符合
  - 平台:钩子在 Claude Code 和 Cowork 加载,在 Chat 里被忽略。lyfusion 只在桌面应用的 Code 标签用;在 Chat 里钩子不生效,插件什么都不做,也没有害处 → 符合
  - 订阅登录(法律与合规):Lily 用自己的订阅登录未修改的 Claude Code,个人使用;插件不提供 Claude 登录,不收集、存储或转发 Claude 凭据,不调用 Claude API,不用订阅替别的服务调用模型 → 符合
  - 消费者条款第 3 节"不用脚本等非人工方式访问服务":插件的脚本只驱动 Codex 和 git,从不向 Claude 发请求;Claude 只在 Lily 自己开的交互式会话里工作,由 Claude 自己调用 Bash 工具。后台命令结束后叫醒 lead 是 Claude Code 自带的功能,和等测试跑完一样;没有定时器、没有无人值守的 Claude → 符合
  - 使用政策:agentic 用法要守政策、用户对 agent 的操作负责 → Codex 只在沙箱工位里干活(只读或只写工位目录),禁止操作扫描、不关证书检查、不跳过钩子,提交和合并由引擎在验收时做;不用输出训练模型;不做批量账号或垃圾内容 → 符合
  - 消费者条款"不开发竞争产品":lyfusion 是给 Lily 自己用的 Claude Code 插件,不是和 Anthropic 竞争的 AI 服务 → 符合
  - 钩子:只注入使用说明,失败也放行(退出码 0),不阻止操作、不批准权限;钩子进程继承的环境变量不读、不记录,只记 Claude 的会话编号 → 符合
- 代码核对:引擎里没有读 `~/.claude/`、AppData 里 Claude 的文件夹、Codex `auth.json` 的代码;引擎自己不联网;启动 Codex 和检查命令前去掉 `CLAUDE*`、`ANTHROPIC*`;Codex 没用绕过沙箱或审批的参数
- 结论:没有发现不符合的地方。注意:如果以后把插件分享给别人,每个人都要用自己的订阅和自己的 Codex 登录,插件不能代管任何人的凭据

## v5.0.0-rc.1(2026-11-13,进行中)
> 依据 `rc-brief.md`(共 8 个任务)。第一次用 lyfusion 迭代 lyfusion 自己:lead 是 Claude Opus 5.5(xhigh,会话 local_d2915de2… 起的子会话),助手 gpt-6-luna high、快速档关;干活用 Lily 装好的 aq.2 插件(安装目录里的引擎),改的是这个仓库。lead 的使用体验记在 `rc-lead-feedback.md`。
- 额度起点(18:45,`get_usage`):5 小时 21%、每周 3%

### 任务 1 助手干净环境 + 上下文设置(accepted,`cdb1273`)
- 结果:项目配置 `clean`(默认 true)→ `exec`、`exec resume` 都加 `--ignore-user-config --disable apps --disable plugins`;两种模式都显式传 `model_auto_compact_token_limit`。压缩上限按模型记(`sidekick.models.<模型>.compact`,默认 400000),换工位阈值 = 压缩上限 × `context_ratio`(只能 0~1 之间,保证在 Codex 自动压缩前换工位);去掉 `context_limit`。`/fusion compact 数字`;`status` 显示压缩上限、Codex 环境、换工位阈值和配置警告;`config get` 加 `effective`;`preflight` 加 Codex 冒烟检查(`exec`、`exec resume` 的参数和 `apps`、`plugins` 两个 feature,不调模型)
- lead 调用约 16 次:explore、读探索包、自己核对 `codex exec resume --help`、写 decisions、写计划文件、delegate、读审查包 ×2、看 diff ×3、revise、accept、看结果和台账;其中约 4 次是派工中途简报更新(设置分三层、冒烟检查、阈值不能设反)带来的
- 修改 1 轮(把中途更新的要求补上);旧测试跑新代码"失败"是 `current_model_settings` 精确返回值多了 `compact`,计划要的变化,`--waive` 放行
- Codex(台账):输入 23.2M(缓存 22.7M)、输出 0.15M,gpt-6-luna/high/fast off。用时约 52 分钟(18:45~19:37;第 1 次实现约 23 分钟,修改约 20 分钟,其中全量测试每次约 2 分钟)
- 问题:助手沙箱里杀不了进程,`test_cancel_kills_running` 在它那里过不了(引擎的检查是通过的),报告里写"全量测试未通过",容易误读(反馈第 3 条,任务 8 处理);`config.json` 的 `clean` 写成非布尔值时按 true 处理、没有警告(低)
- **lead 小改(Lily 同意的例外)**:任务 1 后把项目测试命令改成 `cd plugin\core && python -m pytest -q tests -n 6`(pytest-xdist 3.8.0,全量 110 秒 → 约 26 秒,91 个通过),加 `plugin/core/requirements-dev.txt` 写明开发依赖(插件本身仍只用标准库)

### 任务 2 助手卡住、太慢的看护(accepted,`9588f55`)
- 结果:新模块 `runstats.py` 从 `events.jsonl` 算每次运行的命令数、碎读(读文件命令且整条输出 ≤ `small_read_lines` 行,只认命令名)、重复(不算测试、lint、git status/diff)和最近 8 条命令摘要;运行结束时连同用时、Codex 版本(启动前 `codex --version`)写进事件,`ledger` 加"运行"表。看护新加 `watch_minutes` 40、`watch_small_reads` 15、`watch_repeats` 5(项目配置,0 关掉),每 30 秒最多算一次,超阈值发 `watch` 信号,等待的命令退出码 2 并给出原因、最近命令和三条下一步(继续等、revise 改方向、cancel)。收尾只看进程退出;`turn.completed` 后 60 秒还不退出才杀掉收尾(不看 `last.txt`)。提示:WORK_RULES、FIXED_RULES、explore_prompt 都加了"整份或大段读、不反复跑同一条命令",探索提示补了安全规则
- **顺手修的 bug**:运行中 `revise` 原来只接着等、悄悄丢掉修改意见。改成发中断请求,由拿着租约的监督者停下这一轮(`interrupted`)、在同一会话按意见接着做(算一轮修改);意见和正在做的相同则接着等;请求悬空的三种情况都有处理和测试
- lead 调用约 15 次:explore、读探索包、自己看真实运行事件、写 brief 文件、delegate、读审查包 ×3、看 diff ×3、查时间戳格式和 cancel 流程 ×2、revise ×2、accept
- 修改 2 轮:第 1 轮 8 条(中断改走事件由监督者执行、"继续等"规则、提前收尾会读到空报告、无任务运行的 TypeError、阈值比较和中文提醒、时间戳函数合一、读命令判断太宽、叫醒文字);第 2 轮 1 条(中断请求悬空会让等待命令永不结束)
- Codex(台账):输入 69.5M(缓存 68.4M)、输出 0.44M,gpt-6-luna/high/fast off;探索续用了任务 1 的会话,累计上下文大,输入多。用时约 59 分钟(19:39~20:38;实现约 22 分钟,修改 2 轮约 21 + 6 分钟)
- 额度:任务 2 后 5 小时 52%(任务 2 约 12%)、每周 7%
- 问题:探索工位看不到 `fusion/runs/`(lead 自己摘事件样本);助手第 1 版用"看到 turn.completed 就收尾",和"Codex 最后才写 last.txt"冲突,审查时发现

## 日志
- 2026-11-06:开始 M0。S1、S6 完成
- 2026-11-07:v5.0.0-aq 完成(T1、T2、真实冒烟 T3),69 个测试;合并回 main,本地标签 `v5.0.0-aq`,zip `dist/lyfusion-5.0.0-aq.0.zip`
- 2026-11-06:M1 引擎完成(41 个测试);真实 Codex 跑通 2 个任务;M2 外壳写好并打包;探针测完 S2、S3,S4 没触发;J1 出好(起点 19.75 分,参考答案 100 分);预实验 J1 的 PB、PC 开跑
- 2026-11-07:v5.0.0-aq.1 补回 v4 的助手说明;本地标签 `v5.0.0-aq.1`,zip `dist/lyfusion-plugin-5.0.0-aq.1.zip`
- 2026-11-07:fusion-bench H2 插件版测试(C5,lead Opus 5.5 high 新会话,助手 luna high):**100 分**(v4 C2 是 96.97,助手 luna max);lead 22 次工具调用(Bash 18,另 4 次是桌面应用的任务列表和收尾);约 24 分钟;Codex 515 万输入/3.8 万输出,约 $0.09;每周额度 39%→40%。详见 `fusion-bench/results/summary-2026-11-03.md` 末尾。lead 的意见(探索可跳过要写明、decisions.md 要不要提交、审查包加工位路径、同一检查去重、默认禁止跑格式化器)留给下一版
- 2026-11-07:v5.0.0-aq.2 按 H2 测试 lead 的意见改:探索写成每个任务都先做;引擎在 delegate、revise 时自动提交 `fusion/decisions.md`;审查包加候选和工位一行,同一条命令只跑一次、只列一行;助手说明禁止整项目跑格式化器。75 个测试、lint 通过,没有重跑真实 Codex。lead 的 Claude 用量(mod 的 `$.session.usage()`)放进 M3。见设计 §15。本地标签 `v5.0.0-aq.2`,zip `dist/lyfusion-plugin-5.0.0-aq.2.zip`
