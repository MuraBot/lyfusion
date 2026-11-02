# 迁移说明:第 3 轮迭代(2026-10-28)

适用:已按 `updates/2026-10-28-migration.md` 切换到 lead 与助手协议的项目,例如 CraftTax。改了什么见 `updates/2026-10-28-b.md`。
已在 CraftTax 的本地克隆(提交 eaf2951)上演练第 1 步,结果见文末。

## 1. 复制文件
从 skill 的 `template/` 复制到项目里,同名覆盖:
| 文件 | 改了什么 |
|---|---|
| `tools/brief.py` | 新增"猜测"栏的检查 |
| `tools/mail.py` | `reply --contract`、`watch --follow`、任务完成时收尾信箱 |
| `tools/commit_check.py` | 在 `task/` 分支上自动补追溯信息 |
| `tools/progress.py` | `set-status done` 收尾信箱;`archive` 检查验收标准、`--clean` |
| `tools/check.py`、`tools/doc-rules.json` | 简报加"猜测";检查验收标准的里程碑标记 |
| `prompts/dispatch.md`、`prompts/sidekick.md`、`prompts/review.md` | 按三条原则压缩,并加入本轮的规则 |
| `tasks/T0-template.md` | 新增"## 猜测" |

`review.md` 末尾"本项目的补充"如果写过内容,复制前先另存,复制后再贴回去。
`ledger.py`、`lookup.py`、`tools/hooks/`、`tools/schemas/` 没有变化。

## 2. 派工脚本
1. 记下旧 `tools/codex-dispatch.ps1` 开头"项目设置"里的值,复制新版,再填回去。CraftTax 是:
   - `$DefaultSandbox = "danger-full-access"`
   - `$ProjectEnv = @{ GRADLE_USER_HOME = (Join-Path $env:USERPROFILE ".gradle") }`
   - `$CopyIntoWorktree = @("run/eula.txt")`
2. 新增的设置 `$NeedCommands`:填助手要用的命令,派工前脚本会检查。默认 `@("git", "python")`。CraftTax 可以加 `"java"`(推测,未证实:按 Gradle 需要的命令填)。
3. 不用再给 rg 配 PATH:脚本会把 `codex.exe` 所在目录放到 PATH 最前。
4. 文件保存为带 BOM 的 UTF-8。以后 lead 可以自己改"项目设置",在提交说明里写明;沙箱模式仍要 Lily 同意。

## 3. CLAUDE.md 和 AGENTS.md
标题没有变。手动合并下面几处,项目自己的内容保留:
- "写入规则":加"项目设置"那一句和"环境或工具问题:先消除,再检测,都做不到才记进 learning.md"。
- "开发规则":停止条件改成指向 `prompts/sidekick.md`。
- "运行命令":人工验收的清单写明具体操作,例如按哪个键。
- "验收":证据存原始输出;核对通过的测试数量;spec 的验收标准行尾标里程碑。
- "追溯":钩子在 `task/` 分支上自动补 5 行,助手只写 `Phase`。

合并完,把 `CLAUDE.md` 覆盖复制成 `AGENTS.md`。

## 4. learning.md
- 原来的分组和编号保留(`learning.md` 不检查标题)。末尾新增一节 `## 模块笔记`,格式照模板。
- 每条环境条目加一行"去向":已由脚本修复 / 已探测 / 仍是绕路。
- CraftTax 的第 13 条(没有 rg):M2 第一次派工后确认助手能用 `rg`,再标"已由脚本修复"。第 16 条(javap)同理,看它和 java 是否在同一目录。
- T10 的助手已经下线。只属于锻造模块的知识(真实的 `ServerGamePacketListenerImpl`、没覆盖的客户端按键路径),lead 写进"模块笔记"的"后端 · 锻造"下,不超过 30 行。第 15 条(`@AfterBatch`)是通用的,留在原处。

## 5. spec 的验收标准
- 每条验收标准行尾加里程碑标记,例如 `- [ ] 敲击生效 —— 证据:GameTest · M2`。
- M1 已经做完的标准打勾 `[x]` 并标 `· M1`。M1 没做完的(例如操作提示),标到它要去的里程碑。
- 改完运行 `python tools/check.py`,"没标里程碑"的警告应该清零。

## 6. 按新模板拆 M2
1. 已完成的简报(例如 T10)不用补"猜测"栏,`check.py` 认得这个版本。进行中的简报要补,否则 `brief.py check` 不通过。
2. M2 按 `prompts/dispatch.md` 的"拆分"写:按模块和上下文拆,一个模块一份简报,第 1 个阶段做最薄的端到端路径。
3. 简报里的根因判断和实现建议,放进"猜测",写依据或标"未证实"。
4. 同模块、历史不长,可以续用助手会话;换模块或隔了很久,新开会话,先读模块笔记。
5. 监视用 `python tools/mail.py watch --follow`,配合 Monitor 工具。影响后面阶段的回复,加 `--contract`。
6. 任务做完 `set-status T编号 done`,信箱会自动导出并删除。里程碑结束用 `archive M编号`,确认后 `--clean`。

## 演练结果(2026-10-28,CraftTax 的本地克隆)
- 复制第 1 步的文件后,`check.py`:0 个错误,8 个警告。
- 8 个警告都是"验收标准没标里程碑",每个 spec 文件 1 条,共 66 条标准。做完第 5 步就会清零。
- 演练中发现:已完成的 T10 因为没有"猜测"栏报错。已修:旧版简报的标题组合也被接受,并加了测试。
- 没有演练:第 2~6 步,以及真正派工给 Codex。
