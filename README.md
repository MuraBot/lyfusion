# lyfusion

Lily 的多 agent 协作与调度技能(Fusion 模式),也是对这套模式的研究记录。
1 个 Claude lead 加 1 个 Codex 助手(轻 lead,v3):lead 先选独做或搭档,搭档时只做判断(写规格级简报、看 diff、接手),Codex 助手一口气做完简报。双方只在任务的开头和结尾交换产物(边界交接)。
建立在 LiEC 技能(`C:\AI WithMe\LiEC`)的项目之上。2026-11-02 从 lilys-project-flow 拆出,之前的历史在那个仓库的标签 `final-before-split`。

## 里面有什么
| 路径 | 作用 |
|---|---|
| `SKILL.md` | 技能本体。保存技能时用的就是它 |
| `addon/` | 装进项目的文件,目录结构和项目相同 |
| `addon/prompts/` | lead 工作说明 `dispatch.md`,助手工作说明 `sidekick.md` |
| `addon/tools/` | 派工台账 `ledger.py`、Codex 派工脚本 `codex-dispatch.ps1`(含合并命令)和它的启动器 `run_logged.py`、提交检查 `commit_check.py` 和钩子 `hooks/`、最终报告格式 `schemas/` |
| `addon/ledger.jsonl` | 空台账。派工脚本每次运行自动记一行,只增不改 |
| `viewer/pareto-viewer.html` | 帕累托查看器:读实验文件夹里各组的 `ledger.jsonl`,画花费和分数 |
| `tests/` | 测试。`fake_codex/` 是假的 Codex,不联网、不耗额度 |
| `suggestions/` | 试点数据、复盘、协议草案,按日期存放 |
| `updates/` | 每次更新的简报和迁移说明 |

## 安装到项目
见 `SKILL.md` 的"安装到项目"。装好后项目里多出:台账 `ledger.jsonl`、派工日志和证据 `dispatch-logs/`(不提交)。

## 改了之后
```
python tests/test_fusion.py
python tests/test_dispatch.py
python tests/test_budget.py --show
```
测试用旁边文件夹里 LiEC 的模板加上 `addon/` 建项目。LiEC 在别处时,设置环境变量 `LIEC_HOME`。
`test_dispatch.py` 只在 Windows 上运行。规则文档有行数上限,提高上限要 Lily 同意。

## 需要
- Python 3(只用标准库)、git、Windows PowerShell 5.1。
- Codex CLI:在 Codex 桌面应用的安装包里,派工脚本自己找,不需要在 PATH 里。
