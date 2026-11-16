# rc.1 lead → rc.2 lead 交接(2026-11-15)

> 写的人:rc.1 的 lead(Claude Opus 5.5 xhigh)。只写文档里没有的东西。rc.2 的任务以 `v5/rc2-brief.md` 为准;已经记下的不重复,见 `v5/progress.md`(rc.1 一节)、`v5/rc-lead-feedback.md`(第 1~18 条)、`design/v5.0.0-rc.md`。
> 提交号用推送前改写后的:rc.1 标签 `19b26e7`,任务 7 引擎 `31aa098`,lead 小改 `1273b86`。

## 1. 开工前先确认三件事(我在这上面丢的调用最多)
1. **装好的引擎路径**:每次 Lily 重新上传,路径里的 `plugin_<id>` 就变,旧路径直接没了(反馈第 15 条)。会话开始注入的说明里的路径,在会话中途上传后就过期了。我是手动找的:`find "$LOCALAPPDATA/Claude-Data" -path '*rpm*' -name fusion-core.py`(lead 手动跑,别写进脚本:脚本不读 AppData 里 Claude 的文件夹)。**永远不要把仓库里的 `plugin/core/fusion-core.py` 当 Fusion 工具用**,那是被改的代码
2. **mod 在不在这个会话里**:mod 只在上传之后新开的会话里加载。rc.1 的 T8 台账里 lead 用量是"未记录",因为我的会话比上传早。rc.2 任务 1 要靠 mod 计数,**先确认输入框下方有"● Fusion",再开工**;中途 Lily 重新上传,要开新会话才用得上新 mod
3. **先跑一次很小的真运行**:新引擎装上后,先派一个一两分钟的小探索,看 `fusion/runs/<run>/stderr.log` 里有没有 `blocked by policy`、台账里"命令"数是不是 0。rc.1 的沙箱 bug(反馈第 16 条)就是第一次真运行才暴露的,而且助手照样交了一份像样的探索包(凭记忆写的),只看探索包看不出来

## 2. 引擎和 mod 的坑(文档里没写的)
- **mod 的 `tool.call` 看到的是命令原文,不是 shell 展开后的**。`SNAPSHOT_AT` 正则找 `fusion-core.py explore|accept`;我为了省事写 `E=…/fusion-core.py; python "$E" explore`,原文里没有 `fusion-core.py explore`,快照就记不到(T8 "未记录"可能也有这个原因,我没核实)。rc.2 任务 1 数调用时要考虑这点:要么 lead 一律写完整路径,要么钩子换个认法
- 引擎命令的小坑:`config set` 的 JSON 是**位置参数**,不收 `-`(`config set '{"local":{…}}'`);`ledger --task T8`,不是 `ledger T8`;`explore` 每次都新建任务,探索白跑了只能先 `cancel --task` 旧的
- `local.json` 的 `codex` 可以是列表,前面的参数排在 `exec` 之前(`["…\\codex.exe", "-c", "key=value"]`)。临时绕过引擎问题很好用,但 `args.json` 记不到(反馈第 17 条),用完要改回 `null`
- Codex 装在 `C:\Program Files\WindowsApps\OpenAI.Codex_<版本>_…\app\resources\codex.exe`,版本号在路径里,Codex 一更新就变;引擎用 `Get-AppxPackage` 找,别把路径写死进文件
- **查 Codex 行为不花用量的办法**:`codex sandbox -c windows.sandbox="elevated" -c sandbox_mode="read-only" -- <命令>`、`codex features list`、`codex exec --help`。要花一点用量时,用 luna、`-c model_reasoning_effort=low`、一句"只跑这条命令并原样回复输出",十几秒。手动跑 Codex 前去掉环境变量:`U=$(env | grep -oE '^(CLAUDE|ANTHROPIC)[A-Z_]*' | sed 's/^/-u /'); env $U "<codex.exe>" …`
- Python 3.10 没有 `tomllib`:干净模式读不到用户的 `windows.sandbox`,Windows 上的 bug 会回来。preflight 的"沙箱里能跑命令"能查出来,但不会自动修
- 没查清的现象:在 Codex 的 read-only 沙箱里跑 `git status --short`,lead 目录里 5 个改动只列出 3 个(`design/…`、`fusion/config.json` 没列)。可能是沙箱里刷新不了索引。助手在沙箱里看到的 `git status` 也许不可靠,碰到"助手说没改动"时留意
- mod:桌面端的 `Select`、`Button` 都**没有禁用**,不可选只能画灰字(`<Text dimColor>`)。`Text` 有 `size`(`footnote` 等)和 `hover`。两个画的位置读同一个 atom,改完要 `$.ui.invalidate('ui.render')`,不然底栏不重画(Lily 截到过"面板开、圆点灰")
- mod 的类型文件:加载 `plugin-authoring` 技能后,在 `C:\Users\<用户名>\AppData\Local\Temp\claude\bundled-skills\<版本>\<hash>\plugin-authoring\types\claude-code.d.ts`,约 1.4 万行,按名字 grep(`export type SelectProps`、`'prompt.submit'`),别整个读

## 3. 我的工作方法
- **全量测试**:`cd plugin/core && python -m pytest -q tests -n 6`(约 35 秒,153 条);**lint**:`python -m ruff check --target-version py310 plugin/core`(和项目设置里的 lint 一样;不带版本查不出 3.10 的语法问题)
- **在本机验证引擎改动、又不启动助手**:写个小脚本,`sys.path.insert(0, "plugin/core")` 后直接调 `codex.build_args(...)`、`cli._preflight(root)`,看实际参数和检查结果。rc.1 我就是这样确认新引擎会传 `windows.sandbox="elevated"` 的
- **打包**:`python v5/build_plugin.py --claude "<claude.exe>"`(`rc2-brief.md` 收尾那行没写 `--claude`,不给会直接退出)。`claude.exe` 在 `%LOCALAPPDATA%\Claude-Data\<…>\claude-code\<版本>\<hash>\claude.exe`,`ls "$LOCALAPPDATA"/Claude-Data/*/claude-code/` 看有哪些版本,用最大的(现在有 2.1.317、2.1.325)。validate 的 LICENSE ✘(只针对目录)和 README 没有 marketplace 安装行的提示都不影响通过。打完包用 python 的 `zipfile` 看一眼:没有 tests、有 `types/index.d.ts`、改的东西在里面
- **写派工计划**:brief 写成 Markdown 放 scratchpad,再用小 python 脚本读进来、`json.dumps` 成 `{"goal","brief","scope"}`,`delegate - < plan.json`。rc.2 任务 2 做完就不用了
- **Git Bash 的 heredoc 会吃反斜杠**(`\u`、`\\`):含反斜杠的脚本一律先用 Write 写到 scratchpad 再跑。`progress.md`、`rc-lead-feedback.md`、`decisions.md`、不少测试文件是 CRLF,用 Edit 工具或按字节替换(先 `file` 看换行)
- **读审查包时一次把测试 diff 也拿来**:审查包不附测试文件的 diff,`git diff <基> <候选> -- plugin/core/tests` 和读审查包放同一次调用,能省一次
- "旧测试跑新代码:未通过"在 brief 本来就要改行为时一定会出现;逐条看改后的断言有没有变弱,再 `accept --waive "原因"`
- 引擎命令都用 `run_in_background`,等通知,不轮询

## 4. 对 luna(gpt-6-luna high)的经验
- 给到"函数名 + 代码片段 + 每种情况的期望"的 brief,它基本一次做对;修改意见列成编号清单,7 条一轮全改了
- **brief 里一句话能两种理解时,它选省事的那种**:我写"`clean` 为假时什么都不读、不加",它把项目原有的联网参数也关进了 `if clean:`,还写了测试把回归锁住。以后 brief 里加一节"**这些行为不变**"
- 让它"改已有测试"时,它会把整行断言改成宽松的 `in` 判断。直接写出新断言的原文
- 老毛病:Python 里中文写成 `\uXXXX`(任务 6、7 都有,还写进过 f-string 表达式,3.10 语法错误);注释和 docstring 默认写英文。brief 里写一句"直接写中文"
- 它的沙箱里 `test_cancel_kills_running` 永远过不了(杀不了进程),每次都在"已知问题"里报,以引擎检查为准
- 探索很好用:按 Q1~Q4 回答,会主动找出 lead 没想到的冲突测试(T8 的 `haiku-5.5` 那条)。不知道的(比如 `codex sandbox` 子命令)会推断成"做不到",别全信
- 用时(Fast Mode 关):探索约 5 分钟,实现约 13 分钟,一轮修改约 9 分钟。探索和派工续用同一个线程,输入大部分是缓存(T8 输入 10.3M,缓存 10.1M)

## 5. 没做完的
- 我不知道 Lily 有没有用 01:37 的包在深浅主题下截图确认最后的面板(Fast Mode 灰字、GPT-6-Luna 写法、小号提示字)
- T8 的 lead 用量没记上(见 1.2、2 第一条)
- 内置模型表没有 gpt-6.1-sol;rc.2 任务 4 读 `models_cache.json` 后,内置表只做退路

## 6. rc.2 我建议先做什么
- **先做任务 2(计划接受 Markdown)再做任务 1**:任务 2 小、改动集中,做完以后每次派工都少 1~2 次调用,任务 1 本身的派工也用得上。任务 1 动手前先想清 2 第一条的"命令原文"问题,不然量出来的数不准
- 我数过 rc.1 多出来的调用:环境意外(路径变、沙箱)最多,其次是第二次看 diff 和测试 diff,再次是拼 JSON、转义。任务 2、6 和上面 1.3 的"小真运行"能去掉大半

## 7. 如果重来
- 第一天就跑 `claude plugin validate`,每次装新引擎先跑一次小真运行(都比后来排查便宜)
- brief 固定三节:要改什么、**不变的行为**、测试的原文断言
- 引擎命令写完整路径,不用 shell 变量(为了 mod 能认出来)
- 脚本从一开始就放 scratchpad 文件,不用 heredoc
- 能一次调用拿完的东西(审查包 + 测试 diff + ledger)一次拿完
