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

## 日志
- 2026-11-06:开始 M0。S1、S6 完成
- 2026-11-07:v5.0.0-aq 完成(T1、T2、真实冒烟 T3),69 个测试;合并回 main,本地标签 `v5.0.0-aq`,zip `dist/lyfusion-5.0.0-aq.0.zip`
- 2026-11-06:M1 引擎完成(41 个测试);真实 Codex 跑通 2 个任务;M2 外壳写好并打包;探针测完 S2、S3,S4 没触发;J1 出好(起点 19.75 分,参考答案 100 分);预实验 J1 的 PB、PC 开跑
- 2026-11-07:v5.0.0-aq.1 补回 v4 的助手说明;本地标签 `v5.0.0-aq.1`,zip `dist/lyfusion-5.0.0-aq.1.zip`
