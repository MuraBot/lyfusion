# lyfusion

Lily 的多 agent 协作与调度技能(Fusion 模式),也是对这套模式的研究记录。
1 个 Claude lead 加 1 个 Codex 助手(v4,少调用)。lead 先选独做或搭档。
搭档时助手先探索代码,lead 读片段写计划,一条命令派工。助手写代码和测试,脚本跑测试和 lint、打交接包。lead 读交接包审查,一条命令验收。每次交换,lead 只花 1 次调用。
建立在 LiEC 技能(`C:\AI WithMe\LiEC`)的项目之上。2026-11-02 从 lilys-project-flow 拆出,之前的历史在那个仓库的标签 `final-before-split`。

## 里面有什么
| 路径 | 作用 |
|---|---|
| `SKILL.md` | 技能本体。保存技能时用的就是它 |
| `addon/` | 装进项目的文件,目录结构和项目相同 |
| `addon/prompts/` | lead 工作说明 `dispatch.md`,助手工作说明 `sidekick.md`,各模型的备注 `models/` |
| `addon/tools/` | 派工台账 `ledger.py`、Codex 派工脚本 `codex-dispatch.ps1`(含探索、验收、退回命令)和它的启动器 `run_logged.py`、提交检查 `commit_check.py` 和钩子 `hooks/`、最终报告格式 `schemas/` |
| `addon/ledger.jsonl` | 空台账。派工脚本每次运行自动记一行,只增不改 |
| `viewer/pareto-viewer.html` | 帕累托查看器:读实验文件夹里各组的 `ledger.jsonl`,画花费和分数 |
| `tests/` | 测试。`fake_codex/` 是假的 Codex,不联网、不耗额度 |
| `suggestions/` | 试点数据、复盘、协议草案,按日期存放 |
| `updates/` | 每次更新的简报和迁移说明 |

## 安装到项目
见 `SKILL.md` 的"安装到项目"。装好后项目里多出:台账 `ledger.jsonl`、派工日志和证据 `dispatch-logs/`(不提交)。

## lint
派工脚本的"项目设置"里填 `$LintCommand`,工具要先装好。下面是各语言的推荐命令,都是常用的现成工具:
| 语言 | 工具 | `$LintCommand` |
|---|---|---|
| Python | ruff(`pip install ruff`) | `python -m ruff check --fix --no-cache .`;老项目先用 `--select E4,E7,E9,F`,只查真错误 |
| Godot(GDScript) | gdtoolkit(`pip install gdtoolkit`) | `gdlint .` |
| Java(Gradle) | Spotless 或 Checkstyle 插件 | `gradlew.bat spotlessApply checkstyleMain` |
| JavaScript / TypeScript | Biome | `npx @biomejs/biome check --write .` |
| C#(.NET) | dotnet format | `dotnet format` |

一个项目里有多种语言时,改用 pre-commit 统一入口:`$LintCommand` 写成 `pre-commit run --all-files`。不用 `pre-commit install`,LiEC 项目的钩子目录已经设了 `core.hooksPath`。缓存目录用 `PRE_COMMIT_HOME` 指到工作区里。

## 改了之后
```
python tests/test_fusion.py
python tests/test_dispatch.py
python tests/test_budget.py --show
```
测试用旁边文件夹里 LiEC 的模板加上 `addon/` 建项目。LiEC 在别处时,设置环境变量 `LIEC_HOME`。
`test_dispatch.py` 只在 Windows 上运行。规则文档有行数上限,提高上限要 Lily 同意。

## 依赖 LiEC 的部分
lyfusion 现在装在 LiEC 的项目模板上,用到 LiEC 的:计划模板 `tasks/T0-template.md`、`tools/brief.py`(派工前检查计划)、`tools/progress.py`(登记进度)、`tools/check.py` 和 `doc-rules.json`(文档检查),以及模板的 `AGENTS.md`、`CLAUDE.md`、`learning.md`。v5 要把 lyfusion 拆成能单独用的(Lily 2026-11-06),这一节是拆分的起点。

## 需要
- Python 3(只用标准库)、git、Windows PowerShell 5.1。
- Codex CLI:在 Codex 桌面应用的安装包里,派工脚本自己找,不需要在 PATH 里。
