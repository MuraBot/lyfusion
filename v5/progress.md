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
- Codex:输入 15.2M(缓存 14.9M)、输出 0.06M(另有推理 0.03M),gpt-6-luna/high/fast off。台账显示 23.2M/22.7M/0.15M,是任务 3 修掉的 bug(把线程累计值当本次用量相加)算多了,这里按各次运行的原值求差改正。用时约 52 分钟(18:45~19:37;第 1 次实现约 23 分钟,修改约 20 分钟,其中全量测试每次约 2 分钟)
- 问题:助手沙箱里杀不了进程,`test_cancel_kills_running` 在它那里过不了(引擎的检查是通过的),报告里写"全量测试未通过",容易误读(反馈第 3 条,任务 8 处理);`config.json` 的 `clean` 写成非布尔值时按 true 处理、没有警告(低)
- **lead 小改(Lily 同意的例外)**:任务 1 后把项目测试命令改成 `cd plugin\core && python -m pytest -q tests -n 6`(pytest-xdist 3.8.0,全量 110 秒 → 约 26 秒,91 个通过),加 `plugin/core/requirements-dev.txt` 写明开发依赖(插件本身仍只用标准库)

### 任务 2 助手卡住、太慢的看护(accepted,`9588f55`)
- 结果:新模块 `runstats.py` 从 `events.jsonl` 算每次运行的命令数、碎读(读文件命令且整条输出 ≤ `small_read_lines` 行,只认命令名)、重复(不算测试、lint、git status/diff)和最近 8 条命令摘要;运行结束时连同用时、Codex 版本(启动前 `codex --version`)写进事件,`ledger` 加"运行"表。看护新加 `watch_minutes` 40、`watch_small_reads` 15、`watch_repeats` 5(项目配置,0 关掉),每 30 秒最多算一次,超阈值发 `watch` 信号,等待的命令退出码 2 并给出原因、最近命令和三条下一步(继续等、revise 改方向、cancel)。收尾只看进程退出;`turn.completed` 后 60 秒还不退出才杀掉收尾(不看 `last.txt`)。提示:WORK_RULES、FIXED_RULES、explore_prompt 都加了"整份或大段读、不反复跑同一条命令",探索提示补了安全规则
- **顺手修的 bug**:运行中 `revise` 原来只接着等、悄悄丢掉修改意见。改成发中断请求,由拿着租约的监督者停下这一轮(`interrupted`)、在同一会话按意见接着做(算一轮修改);意见和正在做的相同则接着等;请求悬空的三种情况都有处理和测试
- lead 调用约 15 次:explore、读探索包、自己看真实运行事件、写 brief 文件、delegate、读审查包 ×3、看 diff ×3、查时间戳格式和 cancel 流程 ×2、revise ×2、accept
- 修改 2 轮:第 1 轮 8 条(中断改走事件由监督者执行、"继续等"规则、提前收尾会读到空报告、无任务运行的 TypeError、阈值比较和中文提醒、时间戳函数合一、读命令判断太宽、叫醒文字);第 2 轮 1 条(中断请求悬空会让等待命令永不结束)
- Codex:输入 25.5M(缓存 25.0M)、输出 0.10M(另有推理 0.05M),gpt-6-luna/high/fast off(台账显示 69.5M/68.4M/0.44M,同上算多了)。实现换了新线程,原因也是这个 bug:上下文被估大,触发了换工位用时约 59 分钟(19:39~20:38;实现约 22 分钟,修改 2 轮约 21 + 6 分钟)
- 额度:任务 2 后 5 小时 52%(任务 2 约 12%)、每周 7%
- 问题:探索工位看不到 `fusion/runs/`(lead 自己摘事件样本);助手第 1 版用"看到 turn.completed 就收尾",和"Codex 最后才写 last.txt"冲突,审查时发现

### 任务 3 Codex 的 stdin + 用量 bug(accepted,`98fa81a`)
- 结果:3 个测试锁住 stdin(走 CLI 时调用者 stdin 是管道,Codex 的 stdin 是普通文件且内容等于 `prompt.txt`、参数以 `-` 结尾;直接测 `spawn_detached`;`util.run` 的子进程读 stdin 立即 EOF)。实现没改,只在 `spawn_detached` 的说明里写了原因
- **顺手修的 bug(看护会话发现,lead 核实)**:Codex `turn.completed` 的 usage 是**整个线程的累计值**,引擎当成本次用量:台账把同一线程的累计值一次次相加(任务 1 记多约 1.5 倍、任务 2 约 2.7 倍),`ctx_est` 也被估大、过早换工位。改法:事件里照旧存原值(格式不变),重放时按线程求差得到每次运行的用量,旧库重放也自动纠正;`ctx_est` 用本次增量估(`max(平均, 2×平均 − 上次估计)`)。输出 token 是否已含推理部分,Codex 源码没写明,先保持"输出 + 推理"相加(可能偏多,影响小)
- lead 调用约 11 次:explore、读探索包、查 `ctx_est` 和原始 usage、读 `codex.summarize`、写 brief、delegate、读审查包、看 diff、查 `thread_bound` 和 `run_ended` 的顺序 ×2、accept
- 修改 0 轮
- Codex:输入 5.4M(缓存 5.0M)、输出 0.03M(另有推理 0.01M),按原值求差。探索续用任务 2 的线程,实现又换了新线程(装着的 aq.2 引擎还有这个 bug)
- 用时约 22 分钟(20:35~20:57)
- 注意:aq.2 的 H2 对比数据(`fusion-bench`,Codex 约 $0.09)如果中间有续用同一线程的运行,也按累计值相加了,会偏高;对比时要按原值求差重算

### 任务 4 状态文件的格式版本(accepted,`7c2a6c4`)
- 结果:`fusion_core.SCHEMA` 改成 2,`config.json`、`local.json`、`fusion.db` 共用(aq.2 及更早没写,当作 1;只有旧版本会读错的改动才加 1,写进 decisions.md 第 9 条)。JSON 顶层 `schema_version`:缺 = 1、读时在内存迁移、下一次写入时落盘(项目配置的写入合成 `config.save_project`);库用 `PRAGMA user_version`,在建表前检查,0 → 2;新事件行 `v` = 2,读到行 `v` 更大也拒绝。太新 → `FormatTooNew`(退出码 2,提示升级插件,不删不改文件);SessionStart 改为注入升级提示;`preflight` 加"状态格式"一行。测试用冻结的 aq.2 建表语句和旧配置文件
- rc.1 要加到 2 的原因:aq.2 读不懂 rc.1 的事件(带 `interrupt` 的 `run_requested` 会被当成普通运行再启动一次)
- **lead 例外改动**:派工结束时引擎建候选失败(`git add -A` 碰到助手放在工位里的 pytest 临时目录 `plugin/core/tests/_pytest_tmp/`,里面有测试建的 git 仓库),`delegate` 退出码 1、任务卡在"助手在做"。lead 在工位 `.gitignore` 加了这一行(随候选提交),重跑 `delegate` 接着等,候选建出来。引擎的处理(候选失败转退出码 2、审查包先清旧的)并进任务 8(反馈第 10 条)
- lead 调用约 14 次:explore、读探索包、写 brief、改 decisions、delegate、看失败输出、查状态和工位、查临时目录来源、改 `.gitignore`、重跑 delegate、读审查包、看 diff、accept、看结果
- 修改 0 轮
- Codex(按原值求差):输入 3.7M(缓存 3.5M)、输出 0.02M(另有推理 0.01M);实现又换了新线程
- 用时约 17 分钟(20:58~21:14,含卡住后排查约 3 分钟)
- 额度:任务 4 后 5 小时 63%、每周 9%

### 任务 5 M3 小试验(通过,`a9f9694`、`e2b8e7c`)
- **lead 例外**:没走 Fusion,lead 直接写。mod 要读 Claude Code 的类型文件,按规则 Codex 不读;只有 3 个小文件(`v5/spike-mod/lyfusion-spike/`),打成 `v5/dist/lyfusion-spike-0.1.0.zip` 请 Lily 上传实测。没有写进 `~/.claude/dev-mods/`(工作区外)
- 结果(Lily 截图实测):上传的插件能加载 mod;`SessionMode` 能画灯和按钮;`AbovePrompt` 面板能显示;`PromptHint` 的 `tail` 桌面端不画;新会话发第一条消息后才出现;写在 `Button` 前面的 `<Text>●</Text>` 被画到按钮后面 → 圆点放进按钮里。详见 `v5/spikes.md`
- 任务 6、7 不用换方案

### 任务 8 提示词体检的改动(accepted,`c38d7d1`;Fusion 里编号 T5)
- 结果:模型备注(`fusion_core/prompts/models/gpt-6-luna.md`,`prompts.model_notes` 先读插件再接项目 `fusion/models/`,给助手的拼进派工/修改/自动修提示,给 lead 的接在 SessionStart 说明后);LEAD_GUIDE 推荐小标题加"猜测(未证实)""停下的条件",最后一行改成看工位路径下的文件、加 `ledger`(设计文档说明块同步);审查包:阻塞问题标"(阻塞)"、diff 超上限先附非测试文件、旧测试没过列 `FAILED` 和最后 20 行、助手说测试没过而引擎检查通过时写"以引擎检查为准"、候选没建成时写原因和下一步;WORK_RULES 和 FIXED_RULES 的"不能做的事"都从 `FORBIDDEN` 生成,加 Brief 约定、测试跑法、沙箱说明;建候选失败(`git add -A`)→ 运行 blocked + `candidate_failed` 信号,不再崩;delegate/revise/explore 开工先把 `review.md`/`explore.md` 换成"T编号 第 N 轮:助手还在做"占位。反馈第 1~3、10 条已做
- 修改 2 轮:第 1 轮助手约 3 分钟就以 blocked 停下(沙箱里临时目录 PermissionError,反馈第 11 条),lead 说明是沙箱限制后做完;第 2 轮 lead 退回 6 处(LEAD_GUIDE 多改了字;"不能做的事"用正则包了一层、FIXED_RULES 里条目重复;全角标点;"以引擎为准"关键词太窄;后面轮次候选失败会显示旧候选;旧测试日志 `dir` 为 None 会崩)
- **lead 小改(验收后,3 行)**:助手为满足 lead 写的"源码里'不调用 Claude'只出现一次",把探索提示里的这句拆成 `"不调用 " + "Claude"`;lead 改回原样,测试改成检查 WORK_RULES、FIXED_RULES 各只出现一次(标准写在源码文字上是 lead 的错,见反馈第 12 条)。decisions.md 第 8 条删到只剩本项目参数(`-n 6`、`--basetemp`)
- lead 调用约 22 次:explore、读探索包、写 brief、delegate、读 blocked 审查包、revise、读审查包、看 diff ×4、revise、读审查包、看 diff ×2、accept、改回拆开的字符串 ×4、跑测试、查台账
- Codex(按原值求差):实现线程输入 16.5M(缓存 16.3M)、输出 0.13M(派工 1.1M + 修改 7.1M + 修改 8.3M);探索记 3.7M(续用旧线程,实际增量更小)。两轮修改都是续用会话、整份提示重读,修改轮比派工贵得多
- 用时约 45 分钟(21:15~21:59)
- 额度:任务 8 后 5 小时 82%、每周 11%

### 任务 6、7 M3 Fusion 栏和 lead 用量(引擎 accepted `2379a22`;mod 由 lead 写 `46b448f`、`cb11eb0`;等 Lily 深浅主题截图确认)
- **lead 定:两个任务的引擎部分合成一次 Fusion 派工**(Fusion 里编号 T6),省一轮探索和审查
- 引擎:`config panel`(一行 JSON:开关、助手模型和可选模型 `KNOWN_MODELS = gpt-6-luna、gpt-6-astra` + 登记过的、思考强度、快速档、上下文上限和可选值、`context_ratio`、换工位阈值、警告;不含 env、Codex 路径);`config enabled on|off`(和顶层 `on` 共用初始化函数,不打印说明);`lead-usage --at explore|accept [--task] -`(收 `$.session.usage()` 原样 JSON,记 `lead_usage` 事件,只存原始快照);ledger 的 lead 列改成"本任务 $x · 验收时 上下文 a/b · 5h y% · 周 z%"。新事件类型 aq.2 重放会忽略,SCHEMA 不加
- lead 用量的口径(看护会话建议,lead 定):`cost` 是会话累计值、`rateLimits` 是整个账号的,所以本任务花费 = 本任务最后一次 accept 快照 − 同一会话里配给本任务的 explore 快照;跨会话写"-";额度只当背景。助手对"explore 快照配给哪个任务"用的是"写入时还开着的最近任务,没有就配给之后最先建的任务",正常流程下和 lead 写的规则等价,没再返工(反馈第 13 条)
- mod(`plugin/hooks/register.tsx`、`plugin/types/index.d.ts`,`hooks.json` 加 `modules`,`plugin.json` 加 `types`):SessionMode 画 `<Button><Text color>●</Text> Fusion</Button>`;AbovePrompt 面板用 `Box`、`Text`、`Button`、`Select` 和主题色,有开关、助手、思考强度(低/中/高/超高)、快速档、上下文上限,下面显示换工位阈值、警告和命令失败原因;改设置都调用 `fusion-core config`,面板数据在会话开始、每轮结束、点开面板和改设置后刷新;lead 的 Bash 命令里有 `fusion-core.py … explore|accept` 时把用量快照交给 `lead-usage`,不等、不拦命令。没有 Select 的界面(手机)只显示文字
- 修改 1 轮(引擎):explore 快照和求差的新口径;`config enabled` 抄了 `on` 的代码 → 抽成共用函数;ledger 分隔符;非法 JSON 退出码 1
- **lead 小改**:验收后把 `views.py` 里助手写成 `\uXXXX` 的中文转义换回中文(脚本机械替换,14 处);版本号改成 5.0.0-rc.1
- **第一次上传不显示**(Lily:"我上传了rc.1,但是没有任何fusion的按钮 T T"):看护会话用桌面端自带的 Claude Code 2.1.317 跑 `plugin validate plugin`,报 `atom` 的 plugin 用了常量 `PLUGIN`(必须是字符串字面量),整个 mod 被拒绝加载。改成字面量后 validate 通过(反馈第 14 条)。排查期间 lead 还加了:引擎命令失败不藏(栏照画、toast、面板写原因、只读 `local.json` 退路)、第一次画栏时也刷新;`prompt.submit`、`tool.call` 两个能拦东西的 hook 加 `.catch` 照常放行
- **中途开关(Lily 定,放进 rc.1)**:会话中途在面板或 `/fusion` 开关后,下一条消息起生效。mod 在 `$.state` 记"lead 以为的开关",`prompt.submit` 时不一样才在 `context` 附说明(打开 = 引擎 `hook session-start` 的使用说明,关闭 = 一句话);不改系统提示,`prompt.submit` 里不调用引擎
- **第二个问题:toast "fusion-core 退出码 1:C:\Users\<用户名>\.claude\spares\spare-XXXXXX 不在 git 仓库里"**(Lily 截图,看护会话查明):桌面端先在预备目录起好进程,之后才挂到项目;mod 调引擎时没传 `cwd`,用的是预备目录。改:`core()` 显式传 `cwd = $.session.root()`;调引擎前先看 `fusion/config.json` 在不在,不在就不画、不弹 toast;`classic.CwdChanged` 和画栏、发消息、一轮结束时比较项目目录,换了就重新刷新、lead 以为的开关记成关(宁可多附一次说明,不能漏)。这多半也是"新会话发第一条消息前不显示"的原因
- **打包前必须过 validate**(Lily:"这个插件检查还挺重要的"):`build_plugin.py` 先跑 `claude.exe plugin validate`,没过不出包;脚本不去 AppData 里找 claude.exe,路径用 `--claude` 或 `LYFUSION_CLAUDE_EXE` 给(lead 改,`f06eae4`)
- 没验证:桌面端实际样子和中途开关要 Lily 上传 `v5/dist/lyfusion-plugin-5.0.0-rc.1.zip` 后截图确认;validate 只做静态检查
- lead 调用约 30 次(含查 mod 接口约 10 次、写 mod 和文档)
- Codex(按原值求差):输入约 6.5M(探索 1.3M,续用任务 8 的线程;派工 2.6M;修改 2.6M),输出约 0.16M
- 用时约 40 分钟(23:30~00:06,不含等 Lily)

## 日志
- 2026-11-06:开始 M0。S1、S6 完成
- 2026-11-07:v5.0.0-aq 完成(T1、T2、真实冒烟 T3),69 个测试;合并回 main,本地标签 `v5.0.0-aq`,zip `dist/lyfusion-5.0.0-aq.0.zip`
- 2026-11-06:M1 引擎完成(41 个测试);真实 Codex 跑通 2 个任务;M2 外壳写好并打包;探针测完 S2、S3,S4 没触发;J1 出好(起点 19.75 分,参考答案 100 分);预实验 J1 的 PB、PC 开跑
- 2026-11-07:v5.0.0-aq.1 补回 v4 的助手说明;本地标签 `v5.0.0-aq.1`,zip `dist/lyfusion-plugin-5.0.0-aq.1.zip`
- 2026-11-07:fusion-bench H2 插件版测试(C5,lead Opus 5.5 high 新会话,助手 luna high):**100 分**(v4 C2 是 96.97,助手 luna max);lead 22 次工具调用(Bash 18,另 4 次是桌面应用的任务列表和收尾);约 24 分钟;Codex 515 万输入/3.8 万输出,约 $0.09;每周额度 39%→40%。详见 `fusion-bench/results/summary-2026-11-03.md` 末尾。lead 的意见(探索可跳过要写明、decisions.md 要不要提交、审查包加工位路径、同一检查去重、默认禁止跑格式化器)留给下一版
- 2026-11-07:v5.0.0-aq.2 按 H2 测试 lead 的意见改:探索写成每个任务都先做;引擎在 delegate、revise 时自动提交 `fusion/decisions.md`;审查包加候选和工位一行,同一条命令只跑一次、只列一行;助手说明禁止整项目跑格式化器。75 个测试、lint 通过,没有重跑真实 Codex。lead 的 Claude 用量(mod 的 `$.session.usage()`)放进 M3。见设计 §15。本地标签 `v5.0.0-aq.2`,zip `dist/lyfusion-plugin-5.0.0-aq.2.zip`
