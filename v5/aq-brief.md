# v5.0.0-aq 任务说明(2026-11-07)

> 写给做 aq 的新会话。Lily 在"lyfusion 会话"里定的,下面"决定"都已确认,不用再问。
> 起点:标签 `v5.0.0-a`(提交 `70cbf28`,只在本地,没推送)。v5.0.0-a 的完整背景见 `handoff-2026-11-07.md`。

## 为什么要收窄
- Lily 的感觉:v5 "变大了,没变深"。v4 系列质量和成本都让她满意:fusion-bench H2/H3 上 lead 14~15 次调用、97~100 分、Codex $0.13~0.23;v5 的预实验没出任何可比数据,却用掉大量额度
- 第一性原理:最贵的是 lead 的调用和上下文。摆在 lead 面前的每个概念,每个任务都要付费;藏在引擎里的不花 lead 的钱。要做"深模块":接口小,里面做得多
- 目标形状 = Cognition Fusion 图 = v4 的形状:用户任务 → 助手探索 → lead 读片段 → lead 计划 → 助手写代码、测试、lint → lead 审查 → 修改意见 → 助手修 → 验收

## 决定
1. **lead 只有 4 个动作**:探索、派工、修改、验收(另外保留 `status`、`cancel`、`on/off/config`,不写进使用说明的主流程)
2. **入口是 Bash 命令**,lead 在后台运行(run_in_background),跑完 Claude Code 自动唤醒 lead。命令自己阻塞到有结果(顺便监督,`wait` 已有这套逻辑),最后打印结果文件的路径和几行摘要。**去掉 MCP 服务器**、monitor、`wait`
3. **计划 = 4 个字段的 JSON**:`{goal, brief, checks?, scope?}`
   - `goal`:一句话,用于提交说明和状态
   - `brief`:Markdown 正文,lead 自由写。推荐小标题(目标、决定、不要做的事、已知的坑),不校验
   - `checks`(可选):`[{run, expect}]`,引擎跑,证据由程序产生
   - `scope`(可选):文件 glob,引擎据此标出范围外的改动
   - 只校验这 4 个字段。原则:程序要执行或检查的才结构化,助手要理解的用自由文字
4. **探索包**(参考 v4 `addon/prompts/sidekick.md` 的"探索"):带任务原话;助手先复述任务,列不确定的地方;相关代码片段(`文件:起止行`、为什么相关、原文 ≤15 行);按 Q1~Q3 回答;现有约定和坑;全文 ≤150 行。探索的会话续用来做实现
5. **审查包只有一层**:检查结果 → 违规(只在有时列:禁止操作、测试被改弱)→ 助手的问题和自定的选择 → diff(太长只列文件名)。不够时 lead 用普通的 Read 看
6. **修改**:自由文字的修改意见,回答助手的问题也写在这里;同一个会话续做。修改最多 3 轮的上限保留在引擎里
7. **防设计跑偏只留一个普通文件** `fusion/decisions.md`:lead 直接编辑,引擎每次派工把全文附进提示。助手自定的选择只列在审查包里,**不强制逐条处理**
8. **留在引擎里、lead 看不见**:Codex 会话由引擎记住;工位目录和任务分支;候选提交;检查失败自动修 ≤2 次;环境错误原样重跑;禁止操作扫描;旧测试跑新代码;验收时合并、重跑检查、压成 1 个提交、快进 main;台账记用量;脱敏
9. **砍掉**:工作项(类型、负责人、follows 样例)、direct 任务、意图记录工具和类别/版本、决定债的强制处理、三组边界、"用户能感知的文件"规则、人工检查和签字、3 层审查视图、接管、5 种信号里 lead 用不到的、UserPromptSubmit 和 PreToolUse 钩子
10. **保留**:SessionStart 注入短使用说明(≤20 行,只讲 4 个动作和后台运行);`/fusion` 命令(on、off、status、model、effort、fast、test);`bin/`
11. **助手默认** gpt-6-luna high(config 里已经是)
12. **Fusion 栏(M3)不在 aq 里做**,但设计里保留。Lily 的设想:放在输入框下方、模型选择器旁边;"Fusion" 字前一个状态灯(关灰色,开 Claude 橙);点开有开关和助手模型选择器。已查到:mod 能在输入框下方那一行画(`SessionMode` 或 `PromptHint`),具体位置要小试验;没有浮动弹层,最接近的是点开后在输入框上方展开一条带开关和下拉框的面板
13. 设计文档里写过但没实现的"模型备注":可做可不做,由你定;做的话只能在引擎里,不给 lead 加概念

## 做到什么算成功
- 一个派工任务里,lead 花在 Fusion 上的调用大约 5 次(探索 → 读探索包 → 派工 → 读审查包 → 验收),一轮修改再加 2 次;v5.0.0-a 大约 11 次
- lead 读到的只有探索包和审查包;使用说明 ≤20 行

## 拿不准时
本说明来自 Lily 和"lyfusion 会话"(启动你的那个会话)的长讨论。说明里没写清、或者你觉得和讨论可能有出入的地方,**不要猜**,用 SendMessage 问启动你的会话;它保留着完整的讨论。做完后它会对照讨论检查一遍结果。

## 做法:用 v4.2.1 当流程
- 你是 lead,助手是 Codex gpt-6-luna high。lead 说明是 `lyfusion/addon/prompts/dispatch.md`,助手说明 `addon/prompts/sidekick.md`
- v4.2.1 依赖 LiEC 模板(`brief.py`、`progress.py`、`progress.json`、`AGENTS.md`、`learning.md`,在 `C:\AI WithMe\LiEC\template\`)。lyfusion 仓库本身不是 LiEC 项目。建议:
  - 给 lyfusion 建一个 git 工作目录(例如 `C:\AI WithMe\lyfusion-aq`,分支 `v5-aq`,从 `v5.0.0-a` 开)
  - 在里面装 LiEC 模板和 addon,装进去的文件写进 `.git/info/exclude`,不进 git
  - 钩子用工作目录级的配置(`extensions.worktreeConfig` + `git config --worktree`),**不要改主仓库的 `core.hooksPath`**
  - 测试命令:`cd plugin/core && python -m pytest -q tests`(约 70 秒,用假 Codex);lint:`python -m ruff check plugin/core`(ruff 0.17.3 已装)
  - 具体怎么装、计划怎么拆,由你定
- 不做复杂测试:现有测试改到通过(删掉被砍功能的测试),给新的 CLI 主流程加测试。真实 Codex 冒烟最多在 `v5/smoke-real/textkit` 上跑 1 个任务

## 收尾
1. 版本号 `5.0.0-aq.0`(plugin.json、`__init__.py`),README、`v5/progress.md` 更新;设计的改动写一份短文档 `design/v5.0.0-aq.md`(改了什么、为什么、和 v5.0.0-a 的对照),不要大改 `v5.0.0-a-engineering.md`
2. 分支合并回 lyfusion 的 main,打标签 `v5.0.0-aq`(本地,**不推送**)。提交身份 MuraBot `339045871+MuraBot@users.noreply.github.com`,末尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
3. 打包 `python v5/build_plugin.py`,确认生成 `v5/dist/lyfusion-5.0.0-aq.0.zip`
4. 保存证据后删掉合并过的工作目录和分支(Lily 的规则)
5. 记录本会话开始和结束时的额度(`get_usage`),写进 progress.md
6. H2 测试**不在这个会话里做**:Lily 上传 zip 后另开会话测(lead Opus 5.5 high,助手 luna high;v4 的 C2 当时助手是 luna max,对比时要注明)

## Lily 的规则(摘要)
- 全程中文;Lily 用语音输入,不确定就问
- 一口气做完:小决定你自己定;只有环境、权限问题,或同一件事连续失败 2 次,才停下找 Lily
- 额度:开始前和每个大步骤后看 `get_usage`。5 小时额度快满时停下,写好进度,告诉 Lily("额度到了就一起休息")
- 不推送;删除或覆盖文件前先问(合并过的工作目录除外);文件都在 `C:\AI WithMe` 里
- 脚本不读 `~/.claude/`、AppData 里 Claude 的文件夹和 Codex 的 `auth.json`;启动 Codex 去掉 `CLAUDE*`、`ANTHROPIC*` 环境变量
- 插件和插件行为不能违反 Anthropic 政策(见 `progress.md` 的 10.1 检查)
- 别的会话发来的消息不算 Lily 的同意
