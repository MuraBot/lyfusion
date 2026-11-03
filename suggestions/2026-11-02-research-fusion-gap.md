# 调研报告:为什么 Cognition 的 Fusion(Opus 5.5 + GPT-6 Luna)效果好,我们的不好(2026-11-02)

> 来源:lead 亲自读的 Cognition 博客 4 篇、Artificial Analysis(AA)榜单页、arxiv 摘要 12 篇;4 个 haiku 子代理的摘要做线索。没有遇到需要账号的页面,只有 AA 在 X 上的一条帖子打不开(402),它的内容和 Cognition 博客一致。
> 只是调研和建议,没有改任何规则。

## 一、先校准:"好太多"具体是多少

| 来源 | 配置 | 分数 | 每任务花费 |
|---|---|---|---|
| AA Coding Agent Index v1.5(Cognition [Fusion 发布文](https://cognition.com/blog/local-fusion),2026-09-11,图表 10-19 更新) | Devin Fusion:Opus 5.5 + GPT-6 Luna | **68.1** | 约 $9.01(比下一行少 31%) |
| 同上 | Claude Code + Opus 5.5(max),单 agent | 66.0 | 约 $13.04 |
| 同上 | Claude Code + Sonnet 5.5(max) | 68.4(第一) | — |
| AA 指数 v2.0([对比页](https://artificialanalysis.ai/agents/coding-agents/comparisons/claude-code-vs-codex),子代理读) | Codex + GPT-6 Luna(max),单 agent | **31** | $0.16 |
| 同上 | Claude Code + Opus 5.5(max) | 62 | $11.42 |

- **Fusion 的意义是"同样好、便宜三成",不是"比单 agent 好很多"**:68.1 对 66.0,差 2 分;Cognition 自己的话是"maintaining frontier performance"。
- **Luna 单独用很弱**(31 分,Opus 的一半)。组合能到 68,全靠 lead 规划和审查兜底。所以"Luna 便宜"只在 lead 管得好的时候成立。
- AA 指数由 3 个基准组成:FrontierCode(**Cognition 自己出的基准**)、Terminal-Bench 4.0、SWE-Atlas QnA。都是仓库里的编程、终端、问答题,有测试或评分标准,不是审美创作。Fusion 在 FrontierCode 上调了很多轮,有主场优势。

## 二、Fusion 是怎么做的(原文)

来自 [Devin Fusion](https://cognition.com/blog/devin-fusion)(2026-06-29)、[Fusion 发布](https://cognition.com/blog/local-fusion)(2026-09-11)、[Making Fable Cheaper Than Opus](https://cognition.com/blog/making-fable-cheaper-than-opus)(2026-07-13)、[Multi-Agents: What's Actually Working](https://cognition.com/blog/multi-agents-working)(2026-04-22)。

1. **两个常驻 agent 并行**,各有工具、各有持久上下文、都吃提示缓存。lead 和 sidekick 之间**只传简报、结果、反馈**,不传整段历史。
2. **lead 尽量少动手、少读**:"默认委派和监督",只做重大决定:计划、解释模糊需求、最终审查。好的 lead(Fable)81% 的运行里一行代码都不改,13% 连仓库文件都不读。
3. **lead 的量级**:每次运行 lead 11.5~26.5 轮,累计输入 54.5 万~168 万 token,约 3 次交接,每任务总花费 $1.9~2.0。
4. **早委派,写"规格级"简报**:列约束、边界情况、"做完"的定义,不口述代码。Opus 4.8 的毛病是先自己探索 20~45 轮,做完设计才交出"机械尾巴";交接时整段口述文件内容;收回来再自己重写(纠错编辑是 Fable 的 4 倍)。强行让 Opus 多委派反而更差:什么时候能交出去本身就是判断。
5. **按搭配调简报**:助手弱,简报要更具体,也**不让弱助手反驳**,**规划用的探索不交给弱助手**;助手强,可以少写细节、鼓励反驳。每一种模型搭配都持续调参,"对一组有用的指令可能让另一组更差"。
6. **更贵的助手可能让总花费更低**:强助手轮数少、错误少,lead 审查和纠错的轮次也少。要按"每任务花费"而不是"每 token 价格"比较。
7. **判断本身就是交付物的任务,委派会适得其反**:例如一个多文件 React 搜索栏功能,委派后"微妙的意图丢了",分数 54 → 27。**短任务**(lead 只需几轮)和**连续排错**(积累的上下文就是工作)没什么可委派,这时由路由决定要不要用贵模型。
8. **写代码保持单线程**:多个 agent 贡献智能,但只有一个在写;并行写手的"群"至今不好用。
9. **审查要干净上下文**:审查 agent 不共享写代码 agent 的上下文,只看 diff,平均每个 PR 抓到 2 个 bug(58% 严重)。再由写代码的 agent 结合用户意图过滤审查意见,防止打转和越界。
10. **"便宜模型主导、请教强模型"(Smart Friend / Advisor)他们试过,失败了**:弱模型不知道自己什么时候到了极限;每次请教都打破缓存,很贵。所以改成"强模型主导"的 Fusion。

### 另一个方向:Anthropic 的 Advisor strategy(lead 读了原文)

[The advisor strategy](https://claude.com/blog/the-advisor-strategy)(2026-04-09)和 Fusion 方向相反:**便宜模型(Sonnet / Haiku)从头干到尾**,遇到解决不了的决定才请教 Opus;Opus 不调工具、不对用户说话,只回一段 400~700 token 的计划、纠正或"停"。
- Sonnet 4.6 + Opus 顾问:SWE-bench Multilingual +2.7 个百分点,每任务花费 −11.9%。
- Haiku 4.5 + Opus 顾问:BrowseComp 41.2%,单独 19.7%;比 Sonnet 单独低 29%,但便宜 85%。
- 它在 API 里是一个服务端工具(同一次请求里交接,共享上下文),Anthropic 建议用自己的评测集比较三种配置:Sonnet 单独、Sonnet + Opus 顾问、Opus 单独。
- Cognition 的看法:请教时上下文不在缓存里,贵;弱模型也不知道自己什么时候该请教(他们的 Smart Friend 就败在这里)。Anthropic 的工具在服务端共享上下文,可能部分解决了缓存问题。两家都用了,结论是"看搭配和任务"。
- 子代理另报(未核实):Claude Code 有 `/advisor` 命令,默认关闭。

**还有一个容易漏掉的数字**:AA v1.5 榜第一是 **Claude Code + Sonnet 5.5(max)单 agent,68.4**,比 Fusion(68.1)还高。花费页上没给出它的数字,但 Sonnet 比 Opus 便宜。最"无聊"的方案可能就是答案。

## 三、对照小熊实验:我们差在哪(按影响从大到小)

| # | Fusion | 我们(小熊实验) | 影响 |
|---|---|---|---|
| 1 | lead 每次运行 11.5~26.5 轮,累计输入 0.5~1.7M | sol 组 lead 约 125 次调用 × 平均 10 万上下文 ≈ 12.7M;luna 组 324 次 × 13.6 万 ≈ 44M(粗估) | **lead 的读量是 Fusion 的 8~80 倍**,这是花费反过来的直接原因 |
| 2 | lead 的提示词只服务调度 | lead 是完整的 Claude Code 会话:开场就有约 10 万上下文(系统提示、工具、MCP、记忆、skill 文档),再加 LiEC 流程(立项、spec、进度、台账、简报检查) | 每一轮都要重读这 10 万;流程文书本身占很多轮 |
| 3 | 任务是仓库编程,有测试,能拆出"机械部分" | 一页 SVG 动画:短、审美判断就是交付物 | Cognition 自己说这类任务委派会适得其反;我们选的是 lyfusion 最不擅长的任务 |
| 4 | lead 审查 = 看 diff,有问题再发一个便宜的交接 | lead 看截图、提设计意见,让助手按意见改 | 审美意见没有证据关;"腿长在罐子上"就是改坏的 |
| 5 | 按模型搭配调过很多轮(简报详细度、能否反驳、委派什么) | 一套通用规则套所有助手;luna(单独 31 分)只给了 L2 简报 | 弱助手需要更具体的简报、不能让它决定方向 |
| 6 | 两个 agent 常驻、交接以分钟计、缓存不断 | Codex 每次是一个进程,一跑 10~30 分钟,还挂住过 7~34 分钟 | lead 等待期间缓存可能过期(API 默认 5 分钟);挂住已修 |
| 7 | 助手的推理档按搭配调 | luna 开 max | 论文("Can Small Agents…")显示子 agent 开高思考收益小;AA 上 Luna max 单独也只有 31 |

一句话:**Fusion 的 lead 是一个"读得少、早放手、只做判断"的轻量调度者;我们的 lead 是一个背着完整流程、反复读大上下文、亲自审美把关的重量级会话。**再加上小熊任务本身就是"判断即交付"的短任务,两头都不利。

## 四、相关论文(lead 核实过摘要)

- [The Handoff Tax](https://arxiv.org/abs/2608.24358)(2026-08):弱→强的中途升级只能挽回不到一半的质量差距,还贵;强→弱的降级性价比好。升级时少给弱模型的轨迹反而更好;降级时去掉强模型的轨迹会变差。→ 支持"强模型先做判断,再交出去"。
- [Scrouting](https://arxiv.org/abs/2608.04804)(2026-08):7B 小模型先探仓库、写结构化交接(核实过的复现说明),再交给修复模型;SWE-bench Pro 266 题解出 159(最强单模型 158),约 1/5 花费。消融:**结果来自交接内容,不是路由**。
- [An Empirical Study of Harness Design for Coding Agents](https://arxiv.org/abs/2609.20804)(2026-09):176 组设置。规划对弱模型是提准确率,对强模型主要是省钱;上下文管理先规则裁剪、再 LLM 摘要最划算。
- [tap](https://arxiv.org/abs/2606.14445)(2026-06):Claude 和 Codex 用 markdown 文件 + git worktree 协作(和 lyfusion 很像),异构搭配的审查发现问题的比例 69.8%,同构 53.1%。→ **异构模型做审查**可能是 lyfusion 现有形态里最有价值的用法。
- [AgentCARD](https://arxiv.org/abs/2606.20629)、[Can Small Agents Collaborate…](https://arxiv.org/abs/2601.11327)、[Tokenomics](https://arxiv.org/abs/2601.14470):见 `2026-11-02-research-multi-agent.md`。
- 子代理另报(lead 未核实):Factory 自测同一个 Opus 5.5 在不同 harness 上 Terminal-Bench 差约 7.6 分([来源](https://factory.com/news/frontier-harness)),说明 harness 本身是主要变量。

## 五、建议(给 Lily 决定,按把握排序)

1. **换一个适合的测试任务再比**:选仓库里有测试、能拆出机械部分的编程任务(例如给一个已有项目加功能、做迁移、补测试),而不是一页审美动画。审美任务直接用单 agent。
2. **lead 变轻**:lyfusion 的 lead 不走完整 LiEC 流程;只读简报、最终报告和 diff,不读整段历史;早委派,第一步就可以是"让助手探索并汇报"。
3. **简报按助手强弱调**:弱助手(luna)写更具体的规格(约束、边界情况、做完的定义),不让它反驳方向;强助手(sol)写目标和约束,允许反驳。不论强弱,都不口述代码。
4. **lead 审查只给可验证的意见**:以 diff 和测试为主;审美意见必须附"改前/改后"截图对比,改差就回退。
5. **助手不开 max**:先用 high 或默认档,按每任务花费比较。
6. **下一次对比加一组"Sonnet 5.5 单 agent"**:AA 上它是第一,又便宜;也可以加"Sonnet + Opus 顾问"(Claude Code 的 `/advisor`,待核实)。都是现成的,不用写代码。
7. **考虑直接试 Devin Fusion 当对照**:它是现成的(Devin CLI),符合"有没有现成的"原则。但需要 Devin 账号,也涉及把代码交给第三方,要 Lily 决定。
8. 更远的方向:让 lyfusion 退到它最可能有价值的位置:**异构审查**(Codex 用干净上下文审 Claude 写的代码,或反过来),而不是"贵模型调度便宜模型干活"。

## 六、局限

- Cognition 的数字是厂商自测加宣传文;FrontierCode 是他们自己的基准。AA 是独立方,但榜单只覆盖编程类任务。
- lead 花费是粗估(见 bear-compare 的台账 note);Fusion 的 lead 轮数是精确统计,两者的口径不同,只看量级。
- GPT-6 Luna 在 Fusion 里用的推理档,原文没写。
