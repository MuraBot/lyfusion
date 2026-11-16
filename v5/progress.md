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

## v5.0.0-rc.1(2026-11-13 ~ 11-14)
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

### 任务 7 收尾:Lily 看面板后的意见 + 干净模式的沙箱(引擎 accepted `31aa098`,Fusion 里编号 T8;mod 由 lead 写)
- Lily 的意见(经 lyfusion 会话):"面板显示fusion开，但是下面按钮的颜色是灰色"、去掉冗余说明、"快速档也改为Fast Mode,如果助手模型不支持则变成灰色不可选"、"上下文栏目最低200k干不了什么东西，最低改为262k"、换工位不用灰字提示。mod 由 lead 改(`b4b54e9`、`d50459e` 和本次):底栏圆点跟着重画、去掉说明和换工位小字、Fast Mode 不支持时显示灰字"Fast Mode 不支持"(桌面端的 Select 没有禁用)、模型名用引擎给的显示名(GPT-6-Luna,和 Codex 自己的写法一样)、提示改成小号字
- **装上 rc.1 后发现的 bug(反馈第 16 条,高)**:T7 探索 r19 里助手的命令全被拒(`rejected: blocked by policy`)。看护会话查明:用户的 `config.toml` 里有 `[windows] sandbox = "elevated"`,干净模式的 `--ignore-user-config` 把它丢了。lead 取消 T7,临时在 `local.json` 的 `codex` 里加 `-c windows.sandbox="unelevated"` 重新探索(T8 的 r20,命令正常);Lily 定了修法后,改成按她说的临时关 `clean` 派工,验收后改回
- **修法(Lily 同意:"好的~ 非常好建议，谢谢你，就按建议来吧")**:干净模式下从 `$CODEX_HOME/config.toml` 只读 `windows.sandbox` 和 `sandbox_workspace_write.network_access` 两项,用 `-c` 原样传;项目 `network` 照旧。preflight 加"沙箱里能跑命令"(`codex sandbox … -- git rev-parse --show-toplevel`,不调用模型)。decisions #5 加了这个例外
- 同一次派工:引擎内置模型能力表(显示名、思考强度到 max/ultra、Fast、上下文最大 872000),`config panel` 加 `fast_models`、`model_names`,按模型校验 effort、fast、compact;不支持的模型 fast 当关、不传 `service_tier`;上下文候选最低 262144
- 审查 1 轮修改,7 处:项目 `network` 被关进了 `clean` 判断(回归,测试还锁住了)、测试读了真的 `~/.codex/config.toml`(加 autouse 的空 `CODEX_HOME`)、f-string 表达式里有反斜杠(3.10/3.11 语法错误)、status 测试改弱、preflight 换成读仓库的 git 命令、注释写中文、`CODEX_HOME` 空串
- **lead 定**:项目 lint 改成 `ruff check --target-version py310`(原来的 lint 查不出 3.10 的语法问题;反馈第 18 条)。**lead 小改(1 行)**:验收后把测试里一处 `\u4e0d\u652f\u6301` 改回中文
- lead 在本机实测(不启动助手):新引擎干净模式下传 `windows.sandbox="elevated"` 和 `network_access=true`;preflight 沙箱检查通过。全量测试 153 通过,ruff(py310)通过
- Lily 实测(00:42 的包):中途开关能用("中途关掉后问,lead知道已经关了");新会话要发出第一条消息后栏才出现,记成已知限制(设计文档)
- lead 用量:台账写"未记录":本会话在 Lily 重新上传前就开着,新 mod 没在本会话加载。`get_usage`:5 小时 77%、每周 22%
- Codex:T8 输入 10.33M(缓存 10.11M),输出 0.077M;探索 4.6 分钟、实现 13.2 分钟、修改 9.1 分钟
- 用时约 50 分钟(00:50~01:40,不含等 Lily)

### 收尾
- 版本 5.0.0-rc.1;本地标签 `v5.0.0-rc.1`(不推送);包 `v5/dist/lyfusion-plugin-5.0.0-rc.1.zip`(打包前 validate 通过)
- **回退**:`v5.0.0-aq.2` 标签和 `v5/dist/lyfusion-plugin-5.0.0-aq.2.zip` 是已知能用的版本,不要删。回退 = 重新上传 aq.2 的 zip;只在没有任务进行中时回退(aq.2 不检查格式版本)
- 没验证:新包的深浅主题样子要 Lily 上传后截图确认
## 日志
- 2026-11-06:开始 M0。S1、S6 完成
- 2026-11-07:v5.0.0-aq 完成(T1、T2、真实冒烟 T3),69 个测试;合并回 main,本地标签 `v5.0.0-aq`,zip `dist/lyfusion-5.0.0-aq.0.zip`
- 2026-11-06:M1 引擎完成(41 个测试);真实 Codex 跑通 2 个任务;M2 外壳写好并打包;探针测完 S2、S3,S4 没触发;J1 出好(起点 19.75 分,参考答案 100 分);预实验 J1 的 PB、PC 开跑
- 2026-11-07:v5.0.0-aq.1 补回 v4 的助手说明;本地标签 `v5.0.0-aq.1`,zip `dist/lyfusion-plugin-5.0.0-aq.1.zip`
- 2026-11-07:fusion-bench H2 插件版测试(C5,lead Opus 5.5 high 新会话,助手 luna high):**100 分**(v4 C2 是 96.97,助手 luna max);lead 22 次工具调用(Bash 18,另 4 次是桌面应用的任务列表和收尾);约 24 分钟;Codex 515 万输入/3.8 万输出,约 $0.09;每周额度 39%→40%。详见 `fusion-bench/results/summary-2026-11-03.md` 末尾。lead 的意见(探索可跳过要写明、decisions.md 要不要提交、审查包加工位路径、同一检查去重、默认禁止跑格式化器)留给下一版
- 2026-11-07:v5.0.0-aq.2 按 H2 测试 lead 的意见改:探索写成每个任务都先做;引擎在 delegate、revise 时自动提交 `fusion/decisions.md`;审查包加候选和工位一行,同一条命令只跑一次、只列一行;助手说明禁止整项目跑格式化器。75 个测试、lint 通过,没有重跑真实 Codex。lead 的 Claude 用量(mod 的 `$.session.usage()`)放进 M3。见设计 §15。本地标签 `v5.0.0-aq.2`,zip `dist/lyfusion-plugin-5.0.0-aq.2.zip`

## v5.0.0-rc.2(2026-11-15 ~)
> 任务说明 `rc2-brief.md`;lead = Claude Opus 5.5 xhigh,助手 = gpt-6-luna high、Fast Mode 开;用的引擎是装好的 rc.1 插件。
> 开始时额度:5 小时 27%、每周 27%(`get_usage`,2026-11-15 约 22:30)。
> lead 调用数:任务 1 装上之前由 lead 自己数(explore 到 accept 之间的工具调用,并行的每个都算)。

### 任务 2 计划接受 Markdown + 小项 8 的两条(accepted,`ea96ccf`;lead 小改 `e2e5ffb`;Fusion 里编号 T9)
- 做了什么:`aq.parse_plan` 第一个字符不是 `{` 就按 Markdown(第一行 `# 目标`,可选 `## scope`、`## checks`,围栏代码块里不算标题);LEAD_GUIDE 第 2 条改成 Markdown 写法、推荐小标题加"不变的行为"、提醒检查标准写在产出上(P5);`watch_minutes` 注释写明缓存关系;新测试 10 条
- lead 调用 10 次:探索、读探索包、派工、读审查包、验收各 1(这 5 次是下限);多出的 5 次 = 环境确认 1、python 管道把计划编成 GBK 派工失败 2(用 Markdown 派工后不会再有)、等待时结束本轮的 wrap_up 2(任务 9 前台运行能去掉)。验收后手改 2 次(BOM 原字符改转义)
- 修改轮 0;自动修 0;Codex 输入 5.99M(缓存 5.63M)、输出 0.08M;用时:探索 8.7 分钟(8 条命令)、实现 9.4 分钟(Fast Mode 开)
- 审查包附了完整 diff(含测试),读一次就够,没有第二次看 diff
- 问题:mod 的 explore/accept 快照从没记到过(库里没有 `lead_usage` 事件),台账 lead 用量"未记录",任务 1 修;为此另花约 12 次调用排查,原因还没找到(反馈第 19 条)
### 任务 9 前台运行 + 任务 1 的引擎一半(accepted,`50b9bb1`;Fusion 里编号 T10)
- 做了什么:项目设置 `wait_minutes`(默认 9)等满先返回、退出码 3;新命令 `wait [--task T]`;探索包、审查包直接打印到 stdout(≤20000 字符,超了先去掉 diff);LEAD_GUIDE 改成前台跑;`lead-usage` 收 `toolCalls`/`requests`,台账加"Lead 调用(工具/请求)"列;没有 session_id 不记 `lead_session`;`conftest` 清理重试
- 实测(任务 9 要求先测):前台 Bash 超过 timeout 会**自动转到后台**,不会被掐;用 Stop-Process 强杀等待中的 delegate,Codex 照跑,重跑同一条 delegate 能接着等,计划不会重复派
- lead 调用约 13 次:下限 5;多出的 = 审查包没附 diff 又拿了 2 次(diff 超过 30KB,被存成文件又 Read 一次)、accept 被拒和那一轮修改 2、实测前台和强杀 2、查 mod 类型 2
- 修改 1 轮(偶发测试、设计文档里一行中文变 `?`、`wait` 的一句提示);自动修 3 次;Codex 输入 16.33M(缓存 15.91M)、输出 0.12M;用时:探索 7.1、实现 15.3、自动修 1.3 + 2.6、修改 3.7、自动修 2.2 分钟
- 问题:`test_cancel_kills_running` 在引擎检查(`-n 6`)里偶发失败,accept 被拒,`--waive` 不放行没过的检查,只能多一轮修改(反馈第 27 条);已加清理重试
- 额度:T10 验收后 5 小时 62%、每周 31%;lead 上下文 26.4 万 → 写交接 `v5/rc2-handoffs/2026-11-15-01.md`,用 `clear_session` 清空

### 任务 1 的 mod 一半(lead 写,`register.tsx`)+ 中间包 5.0.0-rc.1.1
- mod 数主代理的工具调用(`tool.call`)和模型请求(`turn.step`),跟快照一起交给引擎;快照改成在钩子自己的调度里 `await`(限时 8 秒,钩子预算 10 秒),失败第一次弹 toast,面板最后一行显示本会话的调用数、请求数、已记快照数和上次失败原因。`accept && explore` 连写时 explore 快照推到下一次模型请求再记(引擎把 explore 快照算给当时还开着的任务)。rc.1 一条都没记到的原因没查清,猜是钩子返回后再用 `$` 会失效(rc.1 是 `void` 出去的),装上后看面板就知道
- `claude plugin validate` 拦下一处:`turn.step` 是流式事件,钩子必须是 `async function*` 加 `return yield* next(e)`
- 顺手修:`v5/build_plugin.py` 打印 validate 输出时 GBK 编码报错(stdout、stderr 改 UTF-8)
- 中间包版本 `5.0.0-rc.1.1`(semver 排在 rc.1 之后、rc.2 之前;不覆盖 rc.1 的回退包),不打标签:`v5/dist/lyfusion-plugin-5.0.0-rc.1.1.zip`
- 验证(第 2 段开工):装好的引擎是 5.0.0-rc.1.1,`--help` 有 `wait`;探索包直接打到 stdout;mod 的 accept 快照能记到(T12),explore 快照没记到是 lead 用了 `$E` 变量写路径(反馈第 30 条)。开始时额度 5 小时 72%、每周 33%

### T11 任务 10、11、12、14 + 17 的 LEAD_GUIDE 部分(accepted,`34fa1d1`;C 档)
- 英文 LEAD_GUIDE(A/B/C 三档、brief 短清单、交接档位行)、`handoff_mode`/`handoff_tokens`(local.json)、`handoff_dir`(config.json,本仓库设成 `v5/rc2-handoffs`)、SessionStart 在 clear/compact 后指向最新交接、accept 过阈值提醒写交接、探索包末尾"Draft (mechanical only)";面板下拉框 lead 写(`10ae5e5`)
- 修改 0 轮;accept 要 `--waive`(旧测试断言是 brief 要改的旧措辞,装的还是旧引擎);问题:等待时长读数多 480 分钟(反馈第 31 条)
### T12 任务 6 + 17 的审查包部分(accepted,`2acd5ac`;C 档)
- 报告加 `brief_check`(助手在同一轮里自查,不加额外的 Codex 运行);审查包改英文,"和 brief 不同"放最前、引擎扫描(scope 外文件、公共签名、TODO)、测试断言原文、`-W` 函数上下文 diff、机械改动折叠;"旧测试跑新代码"不再算违规;删工位路径行、"自动修复 0 次";stdout 超长时指向任务目录里那份
- lead 定:低风险时不只给摘要,diff 放得下就照附(小 diff 便宜,大 diff 本来就不算低风险)
- 修改 1 轮(旧测试那项还列在 Checks 里、Full pack 路径自己拼);lead 用 sed 看了 2 次新代码(审查包没附 diff)
- 额度:T12 验收后 5 小时 80%、每周 34%;lead 上下文 18.5 万 → 写交接 02

### T13 任务 13 `accept --minor-fix`(accepted,`cf36fc7`;B 档，没有探索,accept 流程用 T12 探索包的 Q3)
- 助手在同一线程照一句话改;supervisor 判护栏(只改本任务改过的文件、≤20 行、检查全绿、没违规、报告 done),过了自己发 `accept_requested`,没过留在审查、算一轮修改;合并后打印 `## Minor fix diff`;LEAD_GUIDE 第 4 步加一行
- 修改 1 轮:`wait` 命令被加了 `keep_waiting=True`,等于关掉 9 分钟先返回(为了让慢测试过);改回来并加回归测试
- 台账第一次有 lead 调用数:10 次工具 / 9 次请求(从 T12 accept 到 T13 accept),本任务 lead $0.74
### T14 运行批:任务 5 前半、7、8 的 args.json、17 的引擎部分 + 等待时长 bug(accepted,`503fd63`;C 档)
- 等待时长:存的是本地时间、没带时区，算的时候当成 UTC,这台机器 UTC−8 就多 480 分钟(交接 02 里猜的"UTC+8"方向反了);改成按本地时间解释
- 看护不再单独叫醒(删 `watch_*` 的信号和配置，旧配置忽略);每次退出码 3 打印用时、命令数、碎读、重复、最近的命令(英文);`stall_minutes` 照旧停下(lead 定)
- 删 `_same_area`;不再写顶层 `fusion/explore.md`/`review.md` 和占位文件，指向 `fusion/tasks/T*/`;已有的文件不删
- blocked 且没有阻塞问题时自动续一轮(`continue`,项目设置 `auto_continue` 默认 2)
- 按命令种类计时：引擎第一次读到事件时记时间(`runs/<run>/event-stamps.jsonl`),台账运行表加全量测试/部分测试/lint/其他/思考 5 列
- `args.json` 记完整 argv(含 codex 前缀)
- 修改 0 轮;accept 要 `--waive`(旧测试断言是要改掉的行为);旧测试跑新代码这一步跑了约 10 分钟，等待命令超过 10 分钟转到后台一次
- 额度:T14 验收后 5 小时 84%;之后 5 小时窗口重置为 0%,每周 34%
### T15 任务 4 读 Codex 的模型目录(accepted,`5152165`;C 档)
- 引擎读 `$CODEX_HOME/models_cache.json`(只读、不另存;同一进程按 mtime 缓存),能力按 缓存 → 内置表 → 保守默认 取;`visibility` 不是 `list` 的不进面板列表;面板按 `priority` 排;读不到或格式不对就用内置表并在面板、status、preflight 给 warning;内置表加 gpt-6.1-sol;测试用 conftest 把 `CODEX_HOME` 指到临时目录，不读真的
- 助手在沙箱里读不到用户目录，探索没拿到文件结构;lead 自己用 2 次调用看了字段(只打印键名和相关字段)再写 brief
- 修改 0 轮;decisions 第 5、10 条跟着改
### T16 任务 3 lint 规则(accepted,`debe0ab`;C 档)
- `lint/check.py`(只用标准库)接在 ruff 后面:P7 看不见的字符、C1 真实用户目录(用户名运行时取 `USERNAME`/`USER`)、T3 mod 的非注释代码里 `$.clock` 和 `.claude` 路径、C4 连续 3 个以上 `?`;C3 用 `fusion/config.json` 的 `forbidden`(只看新增行，正则写成 `n[o]qa` 这样，免得自己触发自己);P1、C2 按任务 18 不做
- C4 现有唯一命中是测试输入 `三个连续问号`,改成 `"?" * 3`,不加豁免注释;`lint/*.md` 的状态栏 lead 自己改(中文文档，避免丢编码)
- 修改 0 轮;lead 调用 4 次工具 / 3 次请求，到了下限
### T17 任务 15 lyfusion 的 CLAUDE.md(accepted,`1b03056`;B 档，助手自己读代码)
- 英文速查卡(状态机、命令、退出码、审查包、设置三层、mod 钩子和已探明的接口、开发命令、坑、"Claude usage boundaries (Claude 的使用边界)");lead 验收后改了 2 处(退出码 3 写全、补前台超时和强杀的坑)并补了 Lily 的协作规则;rc2-brief 末尾的规则摘要改成指向 CLAUDE.md
- 自动修 1 次:lead 写在 progress 里的连续 3 个问号触发了 C4,助手把那句改写了(范围外，意思没变)
### 任务 18 的 mod 一半(lead 写,`3a18541`)
- `register.tsx`、`types/index.d.ts` 的注释和面板文字改成英文(思考强度标签 Low/Medium/High/Extra high/Max/Ultra)
### T18 任务 18 插件内容改英文(accepted,`d00c9ca`;C 档)+ 收尾小改
- 引擎输出、提示词、注释、测试、`/fusion` 技能、插件 README、plugin.json 描述、`fusion/decisions.md` 全部英文;测试里只留测非 ASCII 处理的中文数据。mod 一半 lead 写(`3a18541`)
- 第 1 轮助手停下问要不要拆;第 2 轮做完第 1 批,把沙箱里已知的偶发失败当成阻塞;自动修 2 次 + 第 3 轮修改做完。共修改 3 轮(到上限)
- accept 的违规"关闭了 git 的证书检查"是误报:翻译 `checks.py` 规则表那一行时,规则自己的正则落在新增行里(留给 rc.3)
- 收尾时 lead 小改:status 两处英文括号前补空格(从中文标点翻过来留下的)

## rc.2 结果(2026-11-16)
- rc2-brief 的任务 1~15、17、18 都做完并验收(任务 16 撤回、任务 5 后半不做);版本 `5.0.0-rc.2`;设计 `design/v5.0.0-rc.2.md`;全量测试 215 个通过,lint(ruff + `lint/check.py`)通过;仓库里的新引擎验过 `--help`、status、`config panel`、clear 之后的 SessionStart(24 行,指向最新交接)、台账新列
- 额度:第 1 段开工 5 小时 27%、每周 27%;第 2 段开工 5 小时 72%、每周 33%;收尾 5 小时 11%(中途重置过一次)、每周 36%
- lead 调用(台账,工具/请求,从上一个 accept 或 explore 到本任务 accept):T13 10/9、T14 9/9、T15 10/9、T16 4/3、T17 2/1;T9~T12 没记到(装上 rc.1.1 之前 / lead 用了变量路径),T18 没记到原因待查。多出下限的主要是等待(实现一次约 10~28 分钟,每 9 分钟一次 `wait`)和审查包没附 diff 时看代码
- 台账(装好的 rc.1.1 引擎之外,用仓库里 rc.2 引擎打印,任务表):

| Task | Fixes | Change rounds | Lead (at acceptance) | Lead calls | Assistant input/cache/output (M) |
|---|---:|---:|---|---:|---|
| T9 | 0 | 0 | Not recorded | - | 5.991 / 5.629 / 0.076 |
| T10 | 1 | 1 | Not recorded | - | 16.329 / 15.908 / 0.117 |
| T11 | 0 | 0 | Not recorded | - | 18.602 / 18.078 / 0.122 |
| T12 | 0 | 1 | ctx 184k · 5h 79% · 7d 33% | - | 24.771 / 23.998 / 0.149 |
| T13 | 0 | 1 | $0.74 · ctx 211k · 5h 82% | 10 / 9 | 11.955 / 11.761 / 0.053 |
| T14 | 0 | 0 | $0.69 · ctx 236k · 5h 84% | 9 / 9 | 14.135 / 13.616 / 0.116 |
| T15 | 0 | 0 | $0.68 · ctx 261k · 5h 2% | 10 / 9 | 4.103 / 3.748 / 0.039 |
| T16 | 0 | 0 | $0.30 · ctx 278k · 5h 3% | 4 / 3 | 6.040 / 5.868 / 0.076 |
| T17 | 1 | 0 | $0.16 · ctx 289k · 5h 3% | 2 / 1 | 2.254 / 2.154 / 0.015 |
| T18 | 2 | 3 | ctx 341k · 5h 9% · 7d 35% | - | 27.460 / 26.867 / 0.150 |

### 留给下一版(lead 发现的,没做;原来叫"留给 rc.3",rc.3 已用作 H2 测试后的修复版)
- 禁止规则扫描会扫到引擎自己的规则表(`checks.py`),改那几行就误报(T18)
- `auto_continue` 的计数在 `minor_fix` 时没清零;`compact_choices` 当前值超过上限时不在选项里(都很小)
- mod 的快照正则只认字面的 `fusion-core.py`(反馈第 30 条);T18 的 lead 调用数没记到,原因待查
- 计划体检的采纳项(2026-11-16,Lily 说"先记下";依据 `v5/plan-audit-2026-11-16/report.md` 第 5 节和第 11 节、Gemini 复核，这个文件夹没进 git):
  1. 沙箱噪音：引擎固定提示的 Test instructions 让助手把沙箱失败写进 problems(24 份报告 21 份都在写 `test_cancel_kills_running`)。登记已知的沙箱失败、不用再报;最好修根子(沙箱里认出就跳过，或给 Codex 项目内、git 忽略的临时目录)
  2. LEAD_GUIDE 写计划那一行补词、不加行：附近的不变量;完成条件不和已知的环境限制冲突;检查结果要是真的(文件存在、数字对),不只看格式;大的机械任务按顺序拆成几个各自全绿、各自验收的任务
  3. "完整任务"清单按报告第 5 节 + 第 11 节的调整(已知的坑只写本任务特有的;计划里不重复 decisions.md;不贴测试代码，给夹具位置)
  4. 并行 worktree(v2/v3 那样多个助手并行、最后合并)暂不做：引擎现在一次只允许一个任务;并行省的是等待时间，不省 lead 的调用。遇到文件互不相关、等待很长的大任务，再用 fusion-bench 量一次
- 新 LEAD_GUIDE、审查包、`--minor-fix`、交接提醒、自动续用、按命令计时都还没在装好的引擎里真用过:装上 rc.2 后先跑一个小任务验证
- 实现一次 10~28 分钟,每 9 分钟一次 `wait`(反馈第 32 条);"量一次真比较"仍在待讨论

## v5.0.0-rc.3(2026-11-16,rc.2 测试后的修复)
> Lily 2026-11-16:"这次的引擎小问题和lead的意见要不你直接在rc.2上修了吧"。"lyfusion 会话"做;按 `.docs/dev-conventions.md`,上传过的 rc.2 不改内容重用,修完升 rc.3。
- 依据:fusion-bench H2 的 C6(rc.2,Lily 自己开的会话)96.97 分、lead 9 次调用,测出 4 个引擎问题和 lead 的 4 条意见(`fusion-bench/results/summary-2026-11-03.md` 末尾)
- T19(B 档:文件已知,不探索直接派工;`66f932f`):
  - 审查包按文件附 diff:总共 600 行,新文件优先,放不下的列 `Not attached: 路径 (+A -D): git diff …`;stdout 上限 20000 → 26000 字符,超长时从最后一个 diff 块开始去掉,并写 `Not printed (in the full pack): 路径`
  - 引擎扫描:同一个签名在删除行和新增行里都出现时不算签名变化
  - wait 打出审查包时,删掉误导的 "Keep waiting for this round to finish"
  - 台账:没探索的任务,lead 调用和花费从同一会话上一个快照算,没有就从会话开始算(原来显示 "-")
  - 使用说明:退出码 3 正常、通常要 wait 一两次;B/C 改成按"知不知道要改哪"分;交接那两行从说明里删掉,改成 accept 提醒时打印;模型备注标题改成 "About your sidekick (模型名)";说明 19 行
  - 版本 `5.0.0-rc.3`(四处 + decisions 第 6 条);CLAUDE.md 那条 400 行的坑跟着改
- lead:派工 1、wait 1(实现 14.2 分钟)、看 diff 1(装的 rc.2 审查包超长时把 diff 整段丢掉、也不提示,正是这次修的)、`accept --minor-fix` 1(使用说明末尾多的空行,护栏通过);修改 0 轮,不用 `--waive`(旧测试改了断言,现在只是提示)。台账 lead 用量"未记录":这个会话开在上传 rc.2 之前,用的是旧 mod
- Codex:输入 3.96M(缓存 3.81M)、输出 0.03M;luna high、Fast 开
- 全量测试 219 个通过,lint 通过;包 `v5/dist/lyfusion-plugin-5.0.0-rc.3.zip`(过了 2.1.325 的 `claude plugin validate`);本地标签 `v5.0.0-rc.3`,没推送
- 没做(留给下一版):助手在 Windows 沙箱里跑 pytest 写系统临时目录会报 PermissionError(C5、C6、T19 都有,每次都进"和 brief 不同"),可以考虑引擎给 Codex 设项目内、git 忽略的 TEMP

## v5.0.0-rc.4(2026-11-16,Fusion 卡片 + 版本不一致提示)
> "lyfusion 会话"派的任务:按概念图方案 1 重做 Fusion 面板,并修"上传新包后面板还是旧的"。前端 lead 自己写(不派给 luna);引擎改动小,也是 lead 直接改(A 档),这次没有 Fusion 任务、没用 Codex。
- 预览:用热加载的临时 mod(`lyfusion-preview`,放在 dev-mods,用完删)出了 5 版,Lily 每版截图反馈。定下来的样子:
  - 卡片放在桌面端的 **widget 小窗**(`placement: 'widget'`,透明背景),铺满小窗、跟着小窗大小变;不带自己的边框(Plain);行距 `xs`
  - 开关只有开关图:Svg 画开关,上面盖一个不画东西的 Client(`hooks/hit.tsx`)收点击;没有旁边的按钮,"Fusion" 下面没有小字
  - Sidekick、Reasoning effort、Context limit 做成和桌面端模型选择器一样的行(右边 `›`),点开在同一张卡里原地换成列表(顶行 `‹ 标题` 返回);每个列表顶部一行短说明,位置统一,说明里不写 Codex;每行是一个 Client(`hooks/row.tsx`),悬停变灰、选中打勾
  - Context limit 列表:原有档位 + 一直在下面的自定义输入框(单位 k,超过模型上限报错)
  - Fast mode 开关(不支持时写 Not supported)、Lead handoff 分段按钮 Clear/Write/Off、底部一行本会话 lead 调用数和请求数;界面文字全英文、颜色用主题色名(开关图只能写死颜色)
  - 其他界面(终端等)还是原来那种 Select 面板
- Lily 的 sidekick 规定(引擎里做,`/fusion` 也遵守):不提供 gpt-6-astra;gpt-6-luna 的 effort 最低 high,High 带灰字 "Recommended"(luna 的 low/medium 性能不够做 sidekick);存着更低的值时按 high 用
- 版本不一致:`config panel` 带上引擎版本,mod 和自己的 `MOD_VERSION` 比;不一致时卡片只显示 "lyfusion was updated (旧 → 新). Start a new session to load it.",弹一次提示,不用旧逻辑改任何设置(lead 用量也不记)
  - 只从 rc.4 起有效:rc.3 及更早的会话里的 mod 没有这个检查,上传 rc.4 后旧会话不会显示这句
  - 不开新会话能不能换上新 mod(查了 2.1.325 的 mod 文档,没实测):上传的插件跑的是桌面端自己保存的那份,`/reload-plugins` 会重读那个位置,所以上传新包后在旧会话里打 `/reload-plugins` **可以试**;userConfig 改设置只会用同一份代码重跑,换不了版本。没把这件事做死在 mod 里
- mod 测试:新加 `plugin/tests/fusion-card.test.tsx`(假引擎,`claude plugin test plugin`,4 个通过,不打进包);引擎全量测试 220 个通过,lint 通过;`claude plugin validate` 通过
- 版本 `5.0.0-rc.4`(五处:多了 `hooks/register.tsx` 的 `MOD_VERSION` + decisions 第 6 条);包 `v5/dist/lyfusion-plugin-5.0.0-rc.4.zip`;本地标签 `v5.0.0-rc.4`,没推送
- 等 Lily:上传 rc.4 包、新开会话,截深色和浅色的卡片图;旧会话里试一下 `/reload-plugins`

## v5.0.0-rc.5(2026-11-16,rc.4 测试后的修改)
> Lily 测完 rc.4(旧会话里 `/reload-plugins` 能换上新面板),经"lyfusion 会话"提了四件事:Fusion 开着时底部小灯不亮、选择框是直角、sidekick 由我们定白名单(只留 6.1 sol、6.1 terra、6 luna)、修 astra 的小漏洞。lead 自己做(A 档),没有 Fusion 任务、没用 Codex。
- 预览:热加载临时 mod 出了 7 轮(第 2、3 轮 Lily 那边没显示，第 4 轮起加了"加载了就弹提示 + 重画底栏 + 自动开窗",之后都正常)。查清楚的事:
  - **小灯**:桌面端画 Button 时不认里面 `Text` 的颜色(主题色名 claude、写死的十六进制、plain 按钮都是灰的),emoji 的颜色是它自己的。改成按钮文字 "🟠 Fusion"(开)、"⚪ Fusion"(关)、"🟡 Fusion"(要新开会话)
  - **按钮大小**:试了 Text 的 `size`、Button 的 `variant`,底栏按钮大小都一样，是桌面端自己定的，对不齐模型选择器(Lily 看过，先这样)
  - **圆角**:Box 没有圆角属性;`borderStyle: 'round'` 的边框要占一整格，行变得太大(R2、R3);Client 里不能画 Svg。做法:行的灰底换成一张圆角图(Svg,高 22 px、圆角 6 px,Lily 在 P1~P4 里选的 P3),用 Box 的 `hover` 在鼠标移上去时显示;"Recommended"、"Unavailable" 小标签也换成圆角图垫底，和桌面端"推荐"一样
  - 行的文字改由卡片自己画，上面盖一层不画东西的 Client(`hooks/hit.tsx`)收点击;`hooks/row.tsx` 删掉(做减法)
  - 底栏按钮前面改成放引擎自己画的内容(`next(e)`),模式标签由引擎画，我们不再自己拼
- sidekick 白名单(引擎):`SIDEKICK_MODELS = gpt-6.1-sol、gpt-6.1-terra、gpt-6-luna`;名字、effort、Fast、上下文照旧从 Codex 的 models_cache.json 读，按 Codex 的 priority 排;白名单里但 Codex 没列的标 Unavailable;`config model <白名单外>` 报错、不写文件(`/fusion model` 也一样);local.json 里存着白名单外的当前模型时按 gpt-6-luna 用，存着的白名单外模型设置不列出来;luna 最低 high、推荐 high 不变。删掉 `EXCLUDED_MODELS`、`KNOWN_MODELS`、`is_hidden_model` 和 MODEL_INFO 里的 astra;"Codex 缓存里没有的内置模型也算可用"这条规则也删了(白名单模型没被 Codex 列出就是 Unavailable)
- 测试:引擎全量 222 个通过(新加 2 个:白名单外的当前模型按 luna 用且不列出、Codex 没列的白名单模型标 Unavailable;astra 的 `config model` 改成断言被拒且文件不变;测试里假的 Codex 缓存加了 terra,还留着 astra 用来测过滤);mod 测试 4 个通过(行的点击、圆角高亮的图、底栏 🟠/🟡);lint 通过;`claude plugin validate` 通过
- 版本 `5.0.0-rc.5`(五处 + decisions 第 6 条);包 `v5/dist/lyfusion-plugin-5.0.0-rc.5.zip`(29 个文件);本地标签 `v5.0.0-rc.5`,没推送
- 等 Lily:上传 rc.5,新会话(或旧会话 `/reload-plugins`)看底栏小灯和卡片列表的圆角，深浅色各截一张

## v5.0.0-rc.6(2026-11-16,rc.5 测试后的修复)
> Lily 测完 rc.5:"一切都好",只有面板放大时列表行的灰底不完整(右边一截没有)。"lyfusion 会话"直接改(A 档),没有 Fusion 任务、没用 Codex。
- 原因:灰底图的 SVG 写的是 `width="100%"`,自己没有宽度,桌面端按图片默认的 300 px 画;面板窄于 300 px 时看不出来。把图写宽(4096)也不行:缩到行宽时圆角被横向压扁(内置浏览器里试过)
- 改法:每行的灰底拆成左右两半(各占 50%),每半是一张不缩放的长图(`slice`),被自己的框裁掉多余部分:左半留左边两个圆角，右半留右边两个。内置浏览器里试了 120、451(半边是小数像素)、700 px 三种宽度：两端圆角都对，中间看不出缝。"Recommended"/"Unavailable" 小标签不到 300 px,不用改
- mod 测试改成数两半、并断言灰底图不再用 `width="100%"`;CLAUDE.md 的桌面端画法坑加了这条
- 版本 `5.0.0-rc.6`(rc.5 已上传，按规矩升号);Lily 定推送这一版(只推 rc.6 标签;rc.2、rc.4、rc.5 标签留在本地);概念图不推

## v5.0.0-rc.7(2026-11-16,计划体检采纳项 + lead 对整个需求负责 + lead 接手)
> 依据 `v5/rc7-brief.md`。lead = Claude Opus 5.5 high;助手 gpt-6-luna high、Fast 开;引擎 = 装好的 rc.6。
- 任务 2 使用说明(A 档,lead 自己改):第一句改成 "you (the lead) own the result: plan each task completely, review it against the user's whole request, and fix or report any defect you find that breaks that request";写计划那行补"附近的不变量、助手看不到的事实、本任务特有的坑",新起一行写"完成条件不和已知环境限制冲突、夹具给现有测试位置不贴代码、不重复 decisions.md";检查那句加"证明结果是真的";"比 A 大"那行加"大的机械任务拆成几个各自全绿、各自验收的任务"。说明 19 → 20 行;设计文档 `v5.0.0-aq.md` 的副本同步;`test_parts` 的断言跟着改
- 任务 1 沙箱噪音(T20,B 档,`ef40c55`;修改 0 轮):引擎启动 Codex 时设 `FUSION_SANDBOX=1`,写入型运行另把 TEMP/TMP/TMPDIR 指到工位里自带 `.gitignore`(`*`)的 `.fusion-tmp`;`clean_env` 去掉继承来的 `FUSION_SANDBOX`(引擎自己的检查永远照常跑);`test_cancel_kills_running` 在沙箱里确实杀不掉进程时等它自己结束再 skip;固定提示改成"沙箱里 skip 是预期的，不写进 problems";decisions 第 8 条删 `--basetemp`。真实验证：下一个任务 T21 用仓库引擎派，助手报告只写"2 expected sandbox skips",不再出现 `test_cancel_kills_running`
- 任务 3 lead 接手(T21,B 档,`5193dd9`;修改 0 轮;用仓库引擎派，顺带验证任务 1):三种吃力信号、审查包"下一步"多一行、`takeover`、终态 `taken_over`、轮数上限的错误改成三条路;在真实 lead 目录(autocrlf、CRLF)试过 `git apply --check` 能用。lead 验收后自己补了一处：轮数到上限但候选全绿时，下一步仍是 accept(写"revision rounds are used up"),不算吃力信号(原来会叫 lead 去问用户)
- 任务 4 里"T18 的 lead 调用数没记到":其实记到了(seq 417,22 次工具 / 17 次请求、$2.16);当时没探索的任务算不出基准,rc.3 的 T19 已修，现在台账能显示
- 任务 4 小项(T22,B 档,`2624ecc`;修改 0 轮):禁止规则表的正则改成不匹配自己那一行(`GIT_SSL_NO_VERIF[Y]` 这种写法),加了扫 `checks.py` 每一行都不命中的测试;`minor_fix` 时 `auto_continue` 计数清零;上下文上限超过模型上限时出警告。accept 用了 `--waive`:5 条"违规"是 `test_lint_rules.py` 里验证规则仍然生效的正例字符串，没有真的关掉证书检查。`compact_choices` 不改(本来就只列合法值，缺的是说明，所以加警告)
- 任务 5 版本和文档(lead 做):版本 `5.0.0-rc.7`(五处 + decisions 第 6 条;mod 测试的假引擎版本跟着改);CLAUDE.md 加 `takeover`/`taken_over`、沙箱标记那条坑，测试命令去掉 `--basetemp`,最后一行指向 `v5/rc7-brief.md`;设计短文 `design/v5.0.0-rc.7.md`
- 结果：引擎全量测试 240 个通过,lint 通过,mod 测试 4 个通过;T21、T22 用仓库里的新引擎派(装的还是 rc.6)
- 台账(lead 用量这三个任务都是"未记录":这个会话是从"lyfusion 会话"开出来的，可能没装上 Fusion 栏的 mod,没查):

| Task | Fixes | Change rounds | Assistant input/cache/output (M) | Run | Minutes | Commands |
|---|---:|---:|---|---|---:|---:|
| T20 | 0 | 0 | 6.312 / 6.125 / 0.029 | r54 | 8.0 | 19 |
| T21 | 0 | 0 | 6.224 / 6.095 / 0.035 | r55 | 15.5 | 39 |
| T22 | 0 | 0 | 1.187 / 1.119 / 0.008 | r56 | 5.4 | 16 |
