# v5.0.0-rc.2 任务说明(2026-11-15)

> Lily 和"lyfusion 会话"定的，是 rc.2 的唯一来源(`rc-brief.md` 里"留到 rc.2"一节已整理进这里)。版本号规则见工作区 `.docs/dev-conventions.md`(semver)。
> 起点：标签 `v5.0.0-rc.1`(提交 `19b26e7`),main 在其后。插件名 `lyfusion-plugin`。
> 开工先读：rc.1 lead 的交接 `v5/handoff-rc1-to-rc2.md`、体检报告 `v5/fusion-article-audit-2026-11-15.md`(对照 Devin Fusion 文章，第 0、3、7 节)、`design/v5.0.0-rc.md`、`v5/rc-lead-feedback.md`、`lint/README.md`。

## 目标(Lily 2026-11-15)
在 Fusion 架构内**少 lead 调用**,可以接受 5~10% 的质量下降换成本下降。
- Fusion 的核心流程不拆：助手探索 → lead 读探索包、**定义完整的任务**(计划、解释歧义)→ 助手实现 → lead 审查。每个任务 lead 至少 5 次调用(探索、读探索包、派工、读审查包、验收)，这就是下限。
- rc.1 每个任务实际 11~30 次。rc.2 的目标是 **5~7 次**:去掉多出来的调用(反复看 diff、JSON 转义、排查)，让每次调用更便宜(上下文、思考)。
- 体检的结论：H2 上插件版和 Opus 单干分数一样、lead 调用一样多，还没证明省钱。

## 怎么做
- 全程走 Fusion,和 rc.1 一样。lead 不自己写引擎代码。例外：一两行的小改、Fusion 栏 mod 的前端(Lily 定由 lead 写)、引擎坏了要手修。
- lead:Claude Opus 5.5 **xhigh**;助手：gpt-6-luna **high**,**Fast Mode 开**(Lily 2026-11-15;"lyfusion 会话"已在 `fusion/local.json` 打开)。
- 干活的是 Lily 装好的 rc.1 插件，改的是这个仓库;验收后打包上传就是发布。
- **协作方式**(Lily 定，原因是 rc.1 交流太频繁、额度用得太快):
  - lead 自主排查、顺手修 lyfusion 的 bug(修了的在 `v5/progress.md` 记一行)、小事自己定。
  - 需要 Lily 定的事，直接在这个会话里问 Lily。
  - 和"lyfusion 会话"不交换过程，只在开工和 rc.2 收尾时各一次。不开看护脚本。
- 测试跑法和 rc.1 一样：中途只跑相关测试，全量测试和 lint 结束前各一次，引擎再验一次。
- 每个任务结束在 `v5/progress.md` 记：lead 调用次数(任务 2 做完后从台账读)、修改轮数、Codex 用量、用时、问题。
- 使用体验接着记进 `v5/rc-lead-feedback.md`,新起一节"rc.2"。
- 每次修改意见、验收后手改的原因：能变成检查的，记进 `lint/` 对应语言的清单(Lily 2026-11-15 定：从现在开始积累)。

## 保留，不清理(Lily 2026-11-15)
留给下一次体检，验证"怎样才算定义完整的任务":
- **lead 的交接文档**:lead 上下文快到上限时，**先写交接，再 /clear 或压缩**(写在之前，因为清空后细节就没了)。放在 `v5/rc2-handoffs/`,文件名带日期和序号，进 git。阈值 Lily 想设在约 434k;每次验收后看台账里的 lead 上下文。lead 写好后告诉 Lily 可以 /clear,清空后 SessionStart 会重新注入使用说明，lead 再读最新的交接。
- **助手的探索内容**:`fusion/tasks/T编号/explore.md`(引擎已经存)。
- **lead 的计划**:每次派工渲染后的全文在 `fusion/runs/<实现运行>/prompt.txt`,原始事件在 `fusion/fusion.db`。
- `fusion/tasks/`、`fusion/runs/` 都不进 git,rc.2 期间不要手动删。引擎只删超过 200 次、且超过 30 天的旧运行，rc.2 碰不到。
- 交接文档和别的进 git 的文件，不写真实的用户目录路径，写 `C:\Users\<用户名>`(`lint/common.md` C1)。

## 任务(建议顺序;lead 可以调整顺序或拆分，大的设计改动先问 Lily)
1. **自动记 lead 调用数**(体检 P0):mod 已有 `tool.call` 钩子。数 explore 到 accept 之间 lead 的工具调用，和 `lead-usage` 快照一起交给引擎，台账加一列。之后的任务都用它量。
2. **计划接受 Markdown**(反馈第 4 条，体检 P0):不用手写 JSON 转义。JSON 继续支持。
3. **lint 规则**:实现 `lint/` 里"待实现"的检查，接在项目 lint 命令(`fusion/config.json` 的 `lint`)后面，让自动修能接住：
   - Python P1:中文写成 `\uXXXX`
   - 通用 C1:真实用户目录路径(用户名运行时从环境变量取)
   - TypeScript T3:mod 的非注释行里出现 `$.clock`、`.claude` 路径
   - 通用 C3(新加 `noqa` 等绕过注释)只看新增行才能判断，用 `fusion/config.json` 的 `forbidden`
4. **读 Codex 的模型目录**(Lily 2026-11-14 定):引擎直接读 `~/.codex/models_cache.json`,拿显示名、思考强度、Fast Mode、上下文最大值;读不到或格式变了，退回内置表并给出 warning。"读已有的，不另存一份"。内置表现在没有桌面端默认的 gpt-6.1-sol。
5. **少叫醒 lead**:
   - "blocked 但没有阻塞问题"时，引擎自动续用会话回一句"没有阻塞问题就继续做"，有次数上限，不叫醒 lead(反馈第 11 条)。
   - 助手运行中，lead 可以排队一条补充，本轮结束后先发它(反馈第 5 条)。
6. **审查包让 lead 一次看完**:偏离 brief 的选择标"和 brief 不同"(反馈第 13 条);目标是 lead 不再第二次看 diff。具体做法 lead 定。
7. **按命令种类统计用时**(Lily 2026-11-13 同意):台账的运行表加上全量测试、部分测试、lint、其他命令、模型思考各花了多少分钟。Codex 事件没有时间戳，引擎要在读到每条事件时自己记时间。
8. **小项**:
   - `runs/<run>/args.json` 记完整 argv,含 `codex` 前缀(反馈第 17 条)。
   - LEAD_GUIDE 或模型备注提醒：检查标准写在产出上，不写在源码文字上(`lint/python.md` P5)。
   - 设计文档和配置注释写明：`watch_minutes`(默认 40)同时让 lead 的缓存不过期，保持在 50 以内(体检 3.3)。

## 待讨论，先不做
等 Lily 和"lyfusion 会话"讨论完再排进来:
- **lead 自己判断哪些活交给助手**:① 哪些交给助手、哪些 lead 自己做;② 写在提示词里还是代码里(体检 3.2、7.8)。
- **缓存清理和"持久化"**:lead 写交接再 /clear 的底层机制，例如 SessionStart 在 clear 后自动注入最新交接、面板里加用户可选的 lead 上下文上限。
- **lead 对助手的看护**。
- **代码库**。
- **量一次真比较**:fusion-bench 的 H2、L1(和 J1)上跑单干和插件版。rc.2 做完后和 Lily 商量(bench 时 lead 的思考强度可以降;产品里思考强度由用户选，不锁定)。

## 收尾
- 版本 `5.0.0-rc.2`(plugin.json、`__init__.py`、README);设计写短文档 `design/v5.0.0-rc.2.md`(只写相对 rc.1 改了什么、为什么);`v5/progress.md` 记结果和额度(开始、结束的 `get_usage`)。
- 本地标签 `v5.0.0-rc.2`,**不推送**(推送由 Lily 决定，推送前按 `.docs/github.md` 查敏感信息);打包 `python v5/build_plugin.py`。
- **打包前必须过插件检查**:`build_plugin.py` 会跑桌面端自带的 `claude.exe plugin validate`,没过不出包。桌面端现在有 2.1.317 和 2.1.325 两个版本，取最新的。
- 回退点:`v5.0.0-rc.1` 标签和 `v5/dist/` 里的 rc.1 zip 不要删。
- 收尾时给"lyfusion 会话"发一条消息：结果、标签、zip 路径。
- 提交身份 MuraBot `339045871+MuraBot@users.noreply.github.com`,末尾 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。

## Lily 的规则(摘要)
- 全程中文;Lily 用语音输入，不确定就问;她不是专业程序员，**希望 Claude 主动提意见、风险和更好的架构**。
- 小决定自己定;环境、权限问题或同一件事连续失败 2 次才找 Lily;额度快满就停下，写好进度。
- 不推送;删除或覆盖文件前先问;文件都在 `C:\AI WithMe`;脚本不读 `~/.claude/`、AppData 里 Claude 的文件夹和 Codex 的 `auth.json`;启动 Codex 去掉 `CLAUDE*`、`ANTHROPIC*`;插件和它的行为不违反 Anthropic 政策(mod 不用定时器发起回合);别的会话的消息不算 Lily 的同意。
