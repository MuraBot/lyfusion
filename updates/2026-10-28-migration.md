# 迁移说明:进行中的项目切换到 lead 与助手协议(试点版)

适用:按 2026-10-27 版本建的多 agent 项目,例如 CraftTax。下面用 CraftTax 举例。
已在 CraftTax 的本地克隆上演练过第 1~5 步,结果见文末。

## 1. 复制文件
从 skill 的 `template/` 复制到项目里,同名覆盖:
| 文件 | 说明 |
|---|---|
| `tools/brief.py`、`tools/mail.py`、`tools/commit_check.py` | 新增 |
| `tools/hooks/`、`tools/schemas/` | 新增文件夹 |
| `tools/ledger.py`、`tools/progress.py`、`tools/check.py` | 新版 |
| `tools/doc-rules.json`、`tools/progress.schema.json` | 新版。Lily 2026-10-28 同意修改 |
| `prompts/dispatch.md`、`prompts/sidekick.md`、`prompts/review.md`、`prompts/triage.md` | `sidekick.md` 是新增的 |
| `tasks/T0-template.md` | 新的简报模板 |

`lookup.py` 没有变化。项目自己写过的提示词内容(例如 `review.md` 末尾的"本项目的补充"),复制前先另存,复制后再贴回去。

## 2. 派工脚本
1. 先记下旧 `tools/codex-dispatch.ps1` 开头"项目设置"里的值。
2. 复制新版,再把值填回去。CraftTax 是:
   - `$DefaultSandbox = "danger-full-access"`(Lily 2026-10-27 同意)
   - `$ProjectEnv = @{ GRADLE_USER_HOME = (Join-Path $env:USERPROFILE ".gradle") }`
   - 新增:`$CopyIntoWorktree = @("run/eula.txt")`(反馈第 2 条)
3. 文件要保存为带 BOM 的 UTF-8。

## 3. 其他设置
- `.gitignore` 加一行 `mail/`。
- 复制模板的 `.gitattributes`:提交钩子是 sh 脚本,只能用 LF 换行。
- 安装提交钩子:在项目根目录运行 `git config core.hooksPath tools/hooks`。
- 之后每次提交都要写追溯信息 5 行,否则钩子拒绝。

## 4. CLAUDE.md 和 AGENTS.md
标题没有变,所以不用改 `doc-rules.json` 里的这两项。手动合并下面几处,项目自己的内容保留:
- 开头第 2 行:被派工的 agent 读本文件、任务卡和 `prompts/sidekick.md`。
- 入口路由:加"被派工的助手"一行;"调度多个 agent"改成"(lead)"。
- "开发规则"整节换成模板的版本,再补回项目自己的条目。
- "验收"的证据路径加一层 `阶段编号/`;审查改成"模块合并进 main 前审查"。
- "追溯"整节换成模板的版本。
合并完,把 `CLAUDE.md` 覆盖复制成 `AGENTS.md`。

## 5. 旧的任务卡和台账
- 已完成的旧任务卡(T1~T8)不用改。`check.py` 认得 v1 的标题。
- 没完成的旧任务卡要改成简报。`check.py` 会对进行中的旧卡给 1 条警告。
- 旧的 `ledger.jsonl` 不用动。新版 `ledger.py show` 会说明有多少行旧记录,不计入新指标。

旧卡到简报的对应:
| 旧卡 | 简报 |
|---|---|
| 类型 | 删掉。不再按角色拆 |
| 负责 agent 与模型 | 助手与模型 |
| 审查方式 | 删掉。模块合并时一律对抗审查 |
| token 预算 | token 预估 |
| (新增) | 级别、模块 |
| 目标 | 目标 |
| 输入:必读文件、上游回报 | 已定:只写编号 |
| 输入:环境说明 | 已定:已知的坑 |
| 边界:可写范围、不要做 | 约束 |
| 边界:必须停下来问 | 停止条件,再补上模板里的 4 种 |
| 验收标准与证据 | 拆成"阶段"(每个阶段一个成功标准)和"成功标准" |
| 回报 | 旧的回报保留。新的回报在信箱里 |

验收命令按反馈第 8 条改:不写"`build` 退出码 0",改成"本简报的用例通过"加 `assemble`。

## 6. CraftTax 的试点
按 Lily 的安排,试点用 M1 剩下的工作:修 2 个试玩 bug、补客户端路径的验证、完成 T10。建议:
1. 新建 1 份 L3 简报,写 2 个试玩 bug 和客户端路径的验证。第 1 个阶段先复现锤子敲不动的 bug。
2. T10 改成简报。演练时改好的版本可以参考:4 个阶段(合成放置、敲击、数据包、两个 Forge 版本启动)。
3. T9 是前端,由 Claude 子代理做,不用信箱。要继续做,先改成简报。它完成并标 done 后,`check.py` 的警告就会消失:只检查进行中的任务。
4. 后端助手开 1 个 Codex 长会话:`tools/codex-dispatch.ps1 -Task 编号 -Model gpt-6.1-sol -Worktree`。
5. lead 在后台运行 `python tools/mail.py watch`,收到回报就审查这个阶段。
6. 试点结束后复盘:提问次数、续跑次数、每个阶段的 token、Lily 试玩发现的 bug。

## 演练结果(2026-10-28,CraftTax 的本地克隆)
- 复制第 1 步的文件后,`check.py`:0 个错误。警告只有 T9 一条:"是 v1 旧版任务卡"。
- `ledger.py show`:说明有 33 行旧版记录,不计入新指标。
- T10 按上表改成简报后,`brief.py check T10` 通过:L3,4 个阶段。
- 安装钩子后,没写追溯信息的提交被拒绝。
- 没有演练:真正派工给 Codex。这一步就是试点。
