# v5.0.0-rc.9 任务说明(2026-11-17)

> 开工先读：仓库根 `CLAUDE.md`、本文件、`v5/progress.md` 末尾两节("H2 测试 C8""留给 rc.9")。
> lead = Claude Opus 5.5 high;助手 = gpt-6-luna high、Fast 开(`fusion/local.json` 已设好);引擎 = 装好的 rc.8 插件。

## 这一版的定位
rc.8 在 fusion-bench H2(C8)里测出一个会丢代码的 bug。rc.9 只修它和直接相关的两处小事，不加别的功能。使用说明的行数不增加。

## 先注意：装好的 rc.8 引擎本身就有这个 bug
- 任务 1 验收之前，助手运行中**不要** `cancel` 或 `takeover`,否则工位里没提交的改动会丢。
- 实在要用，先手动备份：`git -C "C:\AI WithMe\lyfusion-fusion" add -A`,再 `git -C "C:\AI WithMe\lyfusion-fusion" diff --cached --binary <base>`,输出存到项目的 `_tmp/`。
- 任务 1 验收以后，可以和 rc.7 一样，用仓库里的新引擎(`python "C:/AI WithMe/lyfusion/plugin/core/fusion-core.py"`)派后面的任务。

## 怎么做
- 和 rc.8 一样用 Fusion 迭代 lyfusion:实现类的任务派给助手;一两行的小改、引擎本身坏了，由 lead 自己做。
- 少交流：和"lyfusion 会话"只在收尾报告一次;要 Lily 定的事直接在这个会话里问 Lily。lead 自主排查，小事自己定。
- 引擎命令按使用说明在前台跑，不放后台。
- 上下文超过约 20 万时，在任务边界写交接到 `v5/rc2-handoffs/`。每个任务在 progress 新起的"v5.0.0-rc.9"一节记一行。
- 不推送;不提交 `v5/gemini-consult-2026-11-15/`、`v5/plan-audit-2026-11-16/`。

## 任务

### 1. 运行中 cancel / takeover 不再丢工位改动(最重要)
**现状**(`plugin/core/fusion_core/supervisor.py` 的 `cleanup`,`commands.py` 的 `cmd_takeover`,`cli.py` 的 `_do_takeover`):
- 助手干活时不提交，一轮结束后由引擎提交，生成候选。
- 运行中 cancel 或 takeover 时还没有候选。`cleanup` 存的证据只是 `git diff base 分支`(已提交的),然后 `detach_station` 把工位清干净。
- 结果：证据文件 0 字节，助手写好的改动全丢。C8 就是这样：助手测试全过后卡在写报告上,lead 接手，什么都没拿到。

**要求**:
- `cleanup` 先停掉助手(`_stop_active` 已经会杀进程;Windows 上要确认文件不再被占用),再存证据：工位相对任务 base 的全部改动，包括已提交的、没提交的、新文件(不含被忽略的，比如 `.fusion-tmp`),二进制安全，然后才重置工位。改的只是工位，lead 的工作区不动。
- 运行中 takeover、没有候选：把这份证据放进 lead 的工作区，规则和有候选时一样：
  - 不提交;
  - lead 的工作区里已跟踪的文件有改动，就在发出 `taken_over` 之前拒绝(有没有候选都要先查);
  - `git apply` 放不进去，takeover 照样完成，打印证据文件路径和一条能复制的 `git apply` 命令。
- 有候选时照旧放候选。如果当时还有一轮在跑(比如 revise 中),另外打印证据文件路径，告诉 lead 里面有更新的、没检查过的改动。
- takeover 的输出写清楚：
  - 放进来的是哪种改动("最新候选"还是"没跑完的改动，检查没跑过");
  - 改了哪些文件;
  - 下一步：lead 自己跑 test 和 lint、自己提交;这个任务在 Fusion 里已经结束，不用 accept。C8 的 lead 问过 takeover 后怎么收尾。
- cancel 的提示里说"会把助手的 diff 存进 fusion/runs/",修完以后要名副其实。
- **测试**(用假 Codex,断言写在输出和文件上):
  - 运行中的实现任务，工位里有改动过的已跟踪文件，也有新文件:takeover 以后 lead 工作区里两者都在、都没提交，证据文件非空;
  - 同样的情况下 cancel,证据文件里有那个新文件;
  - lead 工作区不干净时，运行中 takeover 被拒绝，工位和助手都没被动;
  - 原有的 takeover、cancel 测试照样通过。
- **真实演练**(lead 定做不做，推荐做，花费小):
  1. 在 scratchpad 建一个临时 git 仓库，用仓库引擎 `on`,在它的 `fusion/config.json` 里把 `wait_minutes` 设成 1;
  2. 派一个要几分钟的小任务，返回 3 以后马上 takeover;
  3. 看助手写的文件有没有到工作区。

### 2. 卡住要更早提示
- C8 里助手 07:20 就停了。07:30 出了一条重连错误以后，再没有任何事件;20 分钟的 `stall_minutes` 要到 07:50 才会提醒,lead 等了 3 次 wait。
- 先看数据：lyfusion 自己的 `fusion/runs/*/event-stamps.jsonl` 里，正常运行两条事件之间最长隔多久。按数据定新的默认值，推荐 10 分钟，要高于正常的最长间隔;把数据和结论写进 progress。
- 卡住信号的提示现在只说"再跑一次同样的命令继续等，或 cancel",改成也提 takeover(修完任务 1 以后，没跑完的改动会被拷过来)。
- 卡住信号只是提醒，不杀助手，所以默认值降一些风险不大。使用说明不加行。

### 3. 一行小改
`on` 每次都打印 "Fusion is already enabled",第一次打开也这样(`cli.py`,`_setup_project` 后面那句)。改成不管第一次还是再次打开都对的说法。

### 4. 版本和打包
- 版本 `5.0.0-rc.9`:五处 + decisions 第 6 条 + mod 测试的假引擎版本。
- mod 测试里"更新提示"那条现在用 rc.9,要改成比 rc.9 新的版本，比如 rc.10。
- 打包过 `claude plugin validate`;打本地标签(带说明),不推送。
- `CLAUDE.md`:状态一行里 `taken_over` 的说明，补上"没有候选时放工位里没跑完的改动";最后一行改成指向本文件。
- progress 记 rc.9 一节。

## 不做(记进 progress"留给 v5.1.0")
- 审查包"Changed test expectations"把全部断言都贴出来，测试多时太长(C8 lead 的意见)。
- 卡住时自动重启或续跑助手。

## 收尾
- 引擎全量测试、`claude plugin test plugin`、lint、validate 都过;包在 `v5/dist/`。
- 给"lyfusion 会话"一段短报告：提交号、标签、做了什么、测试结果、真实演练做没做、要 Lily 做什么。

## 之后(不在这个会话里)
- Lily 上传 rc.9,再跑一次 fusion-bench H2(C9)。卡住是碰巧才有的,H2 不一定会碰到，所以接手的修复主要靠任务 1 的测试和演练来证明。
- 没问题：只把版本号改成 `5.0.0`,单独提交，打包，打标签 `v5.0.0`;Lily 说推送时，先按 `.docs/github.md` 检查敏感信息，再推送 main 和标签。
- 还要改：改完叫 rc.10,再测。
