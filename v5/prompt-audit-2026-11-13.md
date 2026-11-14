# 提示词体检(2026-11-13,基于 v5.0.0-aq.2)

> Lily 要求的体检。看了 lead 和助手的全部提示:`views.LEAD_GUIDE`、`skills/fusion/SKILL.md`、`aq.review_pack` 和下一步文字、`prompts.py`(WORK_RULES、FIXED_RULES、explore/fix/changes/report)、`report_schema.json`,并对照 v4 的 `addon/prompts/sidekick.md`、`dispatch.md`、`models/gpt-6-luna.md`。只读,没改代码。

## 结论
整体和 aq 的架构一致:lead 的说明短(12 行),助手的完整做法只在派工时发一次,续用时只重申短规则。问题集中在 3 处:**探索提示太薄**、**v4 的模型备注机制丢了**、**lead 说明和审查包有两处对不上**。

## 问题和建议(按优先级)

### A. 影响正在做的 rc.1 任务(已转给 rc1-lead)
1. **探索提示没有"怎么读代码"和安全规则。** 探索只发 `explore_prompt`,不带 WORK_RULES 也不带 FIXED_RULES(`supervisor._start_explore`,只读沙箱)。助手读代码最多的就是探索,"每次只读几行"多半发生在这里;"不读 `~/.claude/`、auth.json、不调用 Claude"在探索里也没说(只读沙箱挡写不挡读)。→ 任务 2 加读代码规则时,探索提示也要加;安全规则补一行。
2. **换工位阈值必须小于自动压缩上限。** WORK_RULES 只在派工时发一次;Codex 一旦在任务中途自动压缩,规则可能被压掉。现在 400k × 0.6 = 240k 才换工位,而且只在任务开始时判断。→ 任务 1 让上下文设置可改时,校验"换工位阈值 < 自动压缩上限",不允许设反。

### B. 建议放进 rc.1(新任务 8"提示词体检",一次派工能做完)
3. **模型备注机制丢了。** v4 有 `addon/prompts/models/gpt-6-luna.md`,派工脚本自动带给助手、探索包和交接包;v5 插件里没有。已验证的 luna 备注:"改造时先列原有行为写回归测试"(大部分已进 WORK_RULES 第 3 条)、"删除类任务会包一层不删,要用禁止句 + 可检查的标准"(v5 里 lead 和助手都看不到)。建议:插件带 `core/prompts/models/<模型>.md`,分"给助手"和"给 lead"两节;按当前助手模型自动拼进派工、修改提示和 SessionStart 说明;项目可以在 `fusion/models/` 加自己的。换别的助手模型(sol、haiku)时自然扩展
4. **lead 说明说"用 Read 看具体文件",但改动在工位里。** aq.2 在审查包里加了工位路径,LEAD_GUIDE 最后一行还是笼统的"用 Read 看具体文件";lead 照做会读到自己目录里的旧代码。改成"看审查包里的工位路径下的文件"
5. **审查包不显示问题是否阻塞。** 报告的 `questions` 有 `blocking`,`review_pack` 只打印 `text`。lead 分不清"必须回答"还是"可以直接验收"。加"(阻塞)"标记
6. **brief 少了"猜测"和"什么情况停下"。** v4 的简报分"已定 / 猜测":猜测只是建议,助手有相反证据可以不采纳并写理由。v5 只剩"决定、不要做的事、已知的坑",luna 容易把 lead 的猜测当成决定。建议:LEAD_GUIDE 推荐小标题加"猜测(未证实)"和"停下的条件";WORK_RULES 写明猜测怎么处理。这和 Antigravity Orchestrator 的做法一致(见下)
7. **测试跑得太勤。** WORK_RULES 说"结束前跑全量测试和 lint",没说中途怎么跑。lyfusion 自己的全量测试要 2 分钟。加一句"中途只跑相关的测试,结束前跑一次全量"
8. **LEAD_GUIDE 没提 `ledger`。** rc 要求每个任务记用量,lead 只能靠 `--help` 找。最后一行加"看用量 fusion-core ledger"

### C. 小的代码整洁(顺手做,不急)
9. FIXED_RULES 和 WORK_RULES 的"不能做的事"是两份手写的文字,迟早不一致。从同一个列表生成
10. SKILL.md 的 `argument-hint` 要跟着任务 1 加上下文设置的参数(任务 1 自己会做)

### 不建议加的
- v4 的证据目录、L1/L2/L3 级别、notes.md、learning.md:aq 的设计就是把这些交给引擎(检查、交接摘要),加回来会让助手多写、lead 多读,和"收窄"相反
- 把提示改成英文:没有证据说 luna 读英文明显更好,中文报告对 lead 和 Lily 更直接

## 和 Google Antigravity 的 Orchestrator 对照
Antigravity 2026-11-12 加了 Orchestrator 模式:规划模型(Gemini 4 Argon 或 Carbon)先只读探索、写计划,Gemini 4 Hydrogen 改代码、跑测试、对照计划验证。和 Devin Fusion、lyfusion 是同一个思路。

| | Orchestrator | lyfusion |
|---|---|---|
| 分工 | 规划模型探索 + 计划;Hydrogen 执行和验证 | 助手探索;lead 计划和审查;助手执行;引擎验证 |
| 上下文 | 两个模型共用同一个对话 | 分开:lead 只看探索包和审查包(省 Claude 额度) |
| 交还规划模型 | 验证失败 2 次、界面和预期不符、计划没覆盖的设计选择 | 自动修 N 次后交给 lead;阻塞问题;(rc.1 任务 2)卡住、太慢 |
| 计划里写 | 具体步骤 + **重新规划的触发条件** | goal/brief/checks/scope(建议 6 补"停下的条件") |
| 中途汇报 | 长任务里 Hydrogen 向规划模型汇报进度 | 助手途中不汇报;看护代替 |
| 用户能调 | 不能调 effort(固定) | 每个模型各自的 effort、快速档 |
| 官方数字 | Terminal-Bench 4.1:成功率接近 Carbon,额度少 24%,快 19% | fusion-bench H2:100 分(v4 是 96.97),24 分钟(v4 是 62.8) |

可以借鉴的两点:计划里写"停下的条件"(问题 6);长任务的中途进度检查(rc.1 任务 2 的看护已经在做类似的事)。共用对话这一点不建议学:lyfusion 的意义之一就是 lead 的上下文小、省 Claude 额度。

没有找到论文或技术报告。官方资料:
- Antigravity 模型文档(Orchestrator 一节):https://antigravity.google/docs/models/
- Antigravity 官方博客:https://antigravity.google/blog/gemini-4-hydrogen-in-google-antigravity
- Google 的 Hydrogen 发布页(博客里的链接,没读):https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-hydrogen/
- 报道:https://9to5google.com/2026/11/12/gemini-4-hydrogen-launch/
