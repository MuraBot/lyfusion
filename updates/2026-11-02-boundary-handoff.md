# 更新简报:改为边界交接,删掉实时信箱(2026-11-02)

> 来源:`suggestions/2026-11-02-boundary-handoff.md`(CraftTax 的 lead 写,Lily 同意方向)。它取代 `2026-10-29-fusion-v4-draft.md`,v4 不落地。
> Lily 的 4 个决定:信箱按减法清单删;品味层放 LiEC;新增只做"合并任务"命令;升降级规则见第三节。
> 旧版(信箱)在本仓库的标签 `v2-mailbox`。

## 一、做法变了什么
| | 以前(信箱) | 现在(边界交接) |
|---|---|---|
| 途中 | 每阶段读 inbox、发回报;lead 用 Monitor 监视,逐阶段审查 | 不通信。助手一口气做完,lead 不监视 |
| 助手卡住 | 发提问,`wait` 等 10 分钟 | 结束本次运行,问题写进最终报告。lead 用 `-Resume` 回答 |
| 进度以什么为准 | 信箱里的阶段回报 | 证据目录:某阶段的目录是空的,监工就按"没做完"续跑 |
| 交回什么 | 回报消息 + 信箱快照 | 改动(脚本在任务分支提交)+ 证据 + 最终报告 `report.md` |
| 决定写回简报 | `mail.py reply --contract` | `-Resume ... -Contract`,或 LiEC 的 `brief.py decide` |
| 合并 | lead 手工十几步 | `codex-dispatch.ps1 -Task T5 -Merge [-Playtest]` |

## 二、删了什么(每项写明它补偿的不足为什么不在了)
- `tools/mail.py` 整个删掉(507 行):inbox、send、wait、watch、reply、diff、close。它治的是"助手一有问题就结束会话",病根已由第 3 轮的决策权、环境脚本、简报模板治好;M2 的信箱几乎没传有用的东西。
- 阶段回报和 lead 逐阶段审查:M2 的 7 次阶段审查全是 ok。高风险时,简报可以标 1 个"(检查点)"阶段。
- 派工记录 `mail/T5.meta.json`:脚本自己提交,追溯信息直接写进提交说明,钩子不用再补。
- 钩子的 `Phase` 和"信箱里要有回报"检查:现在只查 5 行追溯信息,以及 `task/` 分支上 Task 和分支一致。
- 沙箱的额外可写目录(`--add-dir`、`writable_roots`):没有信箱,不用写主目录。
- 异议、提问种类、`--in-brief`:改为最终报告的固定字段。接手信号"问已答问题"依赖 `--in-brief`,一起删。
- 冒烟检查派 haiku 或 terra 用电脑操控(可选项):没用过,删。需要时再提。

## 三、改了什么
**最终报告**(`schemas/final.schema.json`):固定字段 `status`、`last_phase`、`stop_reason`、`summary`,新增数组 `assumptions`(假设)、`interface_requests`(接口修改请求)、`downstream`(给下游)、`problems`。脚本把它存成 `dispatch-logs/evidence/T5/report.md`,超过 60 行就提醒。

**台账**(`ledger.py`):
- 新命令 `review --task T5 --result pass|changes --findings 条数`:一条命令记模块审查结论,同时运行 `progress.py set-review`。进度拒绝时,台账也不记。
- 新命令 `bug --task T5 [--count 2]`:试玩 bug。
- 新命令 `lead --milestone M3 --session 编号 --tokens-in/--tokens-cached/--tokens-out [--calls]`:lead 在里程碑开始和结束时,用 Claude 应用的用量工具读数后记一行。同一会话取最后减最初;只有 1 次读数时按新会话从 0 算。脚本不读 Claude 的记录。
- `show` 改列:一次通过(模块第 1 次审查就 pass)、审查轮数、发现条数、试玩 bug、平均输入和平均缓存读取、接手;下面列每个里程碑 lead 的用量。
- 升降级(Lily 2026-11-02):连续 2 个模块第 1 次审查就通过、试玩 bug 少于 2 个,升 1 级;接手信号累计 2 次(超过 1 次),降 1 级。升降后计数清零。
- 不再依赖 `mail.py`。主目录的查找挪进 `ledger.py`,在工作目录里运行也写主目录的台账。

**派工脚本**(`codex-dispatch.ps1`):
- 监工:没有最终报告就续"补最终报告";有阶段的证据目录是空的、又没停下,就续"继续"。
- 运行结束后,在任务分支上 `git add -A` 并提交,说明末尾写好 5 行追溯信息。没有工作目录时不提交(不替 lead 提交 main)。
- `-Contract`:和 `-Resume`、`-Message` 一起用,先把回答写进主目录简报的"已定",再带进工作目录。
- `-Merge`:要求 `TestCommand` 已填、主目录在 main 且除台账和进度外没有未提交的改动、工作目录干净、审查结果是 pass。先在工作目录里合并 main 并跑测试,证据存到 `dispatch-logs/evidence/T5/merge/test.txt`(带命令、开始时间、退出码),通过才 `--no-ff` 合并进 main,再改状态(`-Playtest` 改成 verify,否则 done)。有冲突或测试失败,main 不变。
- 项目设置新增 `$TestCommand`。
- 审查提示词加上 `report.md` 的位置。

**提示词**:`dispatch.md` 重写为边界交接,新增"接口:看谁在用"(并行用的由 lead 写成可编译存根,后面才用的由助手定,级别决定定到多深)和成本模型(上下文 × 调用次数)。`sidekick.md` 删掉信箱,加最终报告字段和多 agent 的停止例外(要改别人的接口先做适配、写请求,不停下)。

## 四、没做的(候选)
- lead 换会话时用脚本生成状态文件:`progress.py show` 加 `git log` 就是状态,不另做。
- 长日志交给 haiku 摘要:最终报告限 60 行后,先看还需不需要。
- 接口存根的生成脚本:先按 `dispatch.md` 手写,M3 看出错再说。
- sonnet 子代理审查:只写成可选对照,没有改审查流程。

## 五、迁移(CraftTax)
CraftTax 还没做拆分迁移。先按 `updates/2026-11-02-split.md` 做完,再做下面几步:
1. 用旧的 `mail.py close T编号` 收尾所有还开着的信箱(原文导出到证据目录)。旧台账里的 `box` 行留着,新台账不再计算它们。
2. 从 `addon/` 复制:`tools/ledger.py`、`tools/commit_check.py`、`tools/hooks/commit-msg`、`tools/schemas/final.schema.json`、`prompts/dispatch.md`、`prompts/sidekick.md`。删除项目里的 `tools/mail.py` 和 `mail/`。
3. `tools/codex-dispatch.ps1`:复制新版,再把项目原来的"项目设置"一块抄回去,填上 `$TestCommand`。文件保持带 BOM 的 UTF-8。
4. 从 LiEC 复制 `tools/progress.py`、`tools/brief.py`,按 LiEC 的 `updates/2026-11-02-taste-layer.md` 改 `CLAUDE.md`、`AGENTS.md`、`.gitignore` 等。
5. 运行 `python tools/check.py` 和 `python tools/ledger.py level`。级别从起始级别重新算:旧的阶段审查不计入新规则。

## 六、数字
- 规则文档:179 → 172 行(上限 183)。
- 代码(工具和测试):1,624 → 1,093 行(−531)。`mail.py` 删掉 507 行。
- 测试:`test_fusion.py` 4 个、`test_dispatch.py` 7 个,全部通过;LiEC 模板加 addon 的严格检查 0 个错误、0 个警告。信箱的 10 个测试随 `mail.py` 删除;新增合并命令、补最终报告、`-Contract`、台账审查和 lead 用量的测试。

## 七、仍未验证
- 真实 Codex 是否遵守新的最终报告格式(数组字段)。
- 真实项目里的 `-Merge`:Gradle 这类测试命令经 `cmd /c` 运行的输出和退出码。
- 第七节建议的 M3 预测(lead 每个任务缓存读取 ≤ 950 万、文书类调用 ≤ 30%、途中通信 0、交付分和作品分 ≥ 4)。只换了通信方式这一个主要变量。
