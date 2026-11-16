# v5.0.0-rc.7 任务说明(2026-11-16)

> 开工先读：仓库根 `CLAUDE.md`、本文件、`v5/progress.md` 末尾的"留给下一版"。依据：计划体检报告 `v5/plan-audit-2026-11-16/report.md` 第 5 节和第 11 节(含 Gemini 复核;这个文件夹没进 git,不要提交、不要改)。
> lead = Claude Opus 5.5 high;助手 = gpt-6-luna high、Fast 开(`fusion/local.json` 已设好);引擎 = 装好的 rc.6 插件。

## 怎么做
- 老规矩，用 Fusion 迭代 lyfusion:实现类任务派给助手;一两行的小改、mod 前端(`register.tsx`)、引擎本身坏了，由 lead 自己做。
- 少交流：和"lyfusion 会话"只在开工和收尾各一次。lead 自主排查、自己修顺手发现的 bug(在 progress 记一行)、小事自己定;要 Lily 定的事直接在这个会话里问 Lily。
- 这次的任务本身就在改"怎么写计划",派工时按本文件第 2 节的新规则写(附近的不变量、完成条件和已知环境限制不冲突、检查要验真)。
- 交接：上下文超过约 20 万时，在任务边界写交接到 `fusion/config.json` 的 `handoff_dir`(现在是 `v5/rc2-handoffs/`,文件名带日期和序号)。
- 每个任务结束在 `v5/progress.md` 新起的"v5.0.0-rc.7"一节记一行，只写台账没有的(问题、走的哪一档);收尾贴一次 `ledger`。
- 测试、lint、打包照 `CLAUDE.md`。不推送;不提交 `v5/gemini-consult-2026-11-15/`、`v5/plan-audit-2026-11-16/`。

## 任务(建议顺序;lead 可以调顺序、拆分或合并)

### 1. 沙箱噪音(体检采纳 1)
现象：助手沙箱里杀不掉进程,`test_cancel_kills_running` 总是失败;引擎固定提示的 Test instructions 又要求它把沙箱失败写进 problems,结果 24 份报告里 21 份都在写这件事,lead 每次要读,T18 还因此停下一次。另外助手在沙箱里写不了系统临时目录(progress"留给下一版"的 TEMP 那条)。
- 修根子：引擎启动 Codex 时设一个环境变量(例如 `FUSION_SANDBOX=1`),这条测试见到它、又确实杀不掉进程时 `skip` 并写明原因;引擎自己在沙箱外跑检查时照常跑，不能跳过。再给 Codex 设项目内、git 忽略的临时目录(TEMP/TMP)。
- 做减法：根子修好后，固定提示里"沙箱失败写进 problems"那句删掉或缩短;`decisions.md` 第 8 条里 `--basetemp` 的说法，如果不再需要也删。
- 完成标准：派一个真实的小任务验证，助手报告里不再出现 `test_cancel_kills_running`。

### 2. 使用说明(LEAD_GUIDE)(体检采纳 2、3,Lily 2026-11-16 同意)
渲染后仍然不超过 24 行,SessionStart 全部不超过 30 行(decisions rc.2 #2);设计文档里和 `test_shape` 对比的那段同步改。下面是意思，措辞 lead 定:
- **第一句改成 lead 对整个需求负责**(针对 H2 C6:lead 看到违反题目合同的 bug,判断"不混入别的题"没修,96.97 分;C5 修了,100 分)。草稿:`you (the lead) own the result: plan each task completely, review it against the user's whole request, and fix or report any defect you find that breaks it.`
- **写计划那一行**补几个词，不加行：改动附近的不变量;助手看不到的事实(本机文件、沙箱外的东西);本任务特有的坑;完成条件不能和已知的环境限制冲突;不重复 `fusion/decisions.md`(它每次都整份附上);需要夹具时给现有测试的位置，不贴测试代码。
- **"检查写在输出上"那一句**后面加半句：检查结果是真的(文件存在、数字对),不只看格式。
- **"比 A 大的都派出去"那一行**加：大的机械任务拆成几个各自全绿、各自验收的任务(T18 一个任务 3 轮修改、lead 22 次调用)。
- 不加笼统的"尽力而为""think hard"之类的话(Lily 同意:思考强度由用户选，语气太重容易做过头、多花调用)。

### 3. lead 接手(新功能;Lily 2026-11-16 要的，设计是"lyfusion 会话"提的，可以按实际情况改)
场景：助手在**同一个点上反复做不对**,lead 判断剩下的部分自己做更省。大任务的办法是拆(第 2 节),不是接手。
- **吃力信号**(引擎从 fusion.db 算，不靠 lead 记):
  1. 同一条检查命令，本任务最新候选和上一个候选都没过(已经过了自动修);
  2. 本任务助手第 2 次停下(自动续用之后仍 blocked),或第 2 次卡住、运行失败;
  3. 修改轮到了上限(`max_change_rounds`,现在是"停下问用户"):提示改成列出三条路：问用户要不要继续 / 接手 / 取消。
- 有信号时，审查包的"下一步"多一行，说明是哪个信号，并给出 `fusion-core takeover`。**引擎不自动接手**,由 lead 判断(接手意味着最贵的模型亲自写代码)。
- **`fusion-core takeover [--task T]`**:
  - 停掉本任务还在跑的运行(和 cancel 一样);
  - 把最新候选相对基准的改动(压成一份)放进 lead 自己的目录，作为**未提交的改动**;lead 目录里有未提交的受管改动、或改动放不进去时拒绝，并告诉 lead 改用 cancel(cancel 会把 diff 存成证据);
  - 没有候选时：只停运行、标记，告诉 lead 从头自己做;
  - 任务进入终态 `taken_over`(和 accepted、cancelled 一样，之后可以开新任务),事件里记下当时的信号和没过的检查;台账能看出来;
  - 输出：放进来的文件、没过的检查、项目的 test/lint 命令，最后一句"自己改完、跑测试和 lint、提交;引擎不再管这个任务"。
- 使用说明里和 cancel 合成一行(不超 24 行),例如 `Abandon a task: fusion-core cancel. Sidekick keeps failing at something you can finish faster: fusion-core takeover.`
- 不做：自动接手;接手后"再交回给助手"(要再派就开新任务)。
- 测试：三种信号各自让"下一步"出现接手那行、没信号时不出现;takeover 把候选改动放进 lead 目录、任务变 `taken_over`、之后能开新任务;lead 目录不干净时拒绝;没有候选时只标记。
- `/fusion` 技能和 mod 面板如果显示任务状态，要认得 `taken_over`(mod 由 lead 自己改)。

### 4. 可选小项(progress"留给下一版",lead 定做不做)
禁止规则扫描扫到引擎自己的规则表(T18 误报);`auto_continue` 计数在 `minor_fix` 时没清零;`compact_choices` 当前值超过上限时不在选项里;T18 的 lead 调用数没记到的原因。

### 5. 版本和文档
- 版本 `5.0.0-rc.7`(五处 + decisions 第 6 条);打包过 `claude plugin validate`;本地标签(带说明),不推送。
- `CLAUDE.md` 最后一行改成指向本文件;engine 命令表加 `takeover`、状态加 `taken_over`。
- `v5/progress.md` 记 rc.7 一节;`design/` 下写一篇短的 `v5.0.0-rc.7.md`(中文，给 Lily 看)。

## 收尾
- 引擎全量测试、mod 测试(`claude plugin test plugin`)、lint、validate 都过;包在 `v5/dist/`。
- 给"lyfusion 会话"一段短报告：提交号、标签、做了什么、测试结果、要 Lily 做什么。
- 之后(不在这个会话里):Lily 上传 rc.7,另开独立会话跑 fusion-bench H2(C7),和 C5、C6 比分数和 lead 调用数。
