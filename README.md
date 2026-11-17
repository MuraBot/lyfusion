# lyfusion

Lily 的多 agent 协作插件 `lyfusion-plugin`(Fusion 模式),也是对这套模式的研究记录。
当前版本 v5.0.0(2026-11-17):Claude Code 插件。Claude 当 lead,负责计划、审查和验收;Codex 当助手，写代码和测试;本地的 Python 引擎 fusion-core 管任务状态、跑检查、合并改动。
- 用法和安装：见 `plugin/README.md`。
- 开发 lyfusion 本身：先读 `CLAUDE.md`。

v4 及以前是一个技能(`SKILL.md` + `addon/`,装在 LiEC 的项目模板上),已经被 v5 插件取代，文件只留作历史。2026-11-02 从 lilys-project-flow 拆出，更早的历史在那个仓库的标签 `final-before-split`。

## 里面有什么
| 路径 | 作用 |
|---|---|
| `plugin/` | v5 插件:引擎 `core/`、SessionStart 钩子和 Fusion 卡片 `hooks/`、`/fusion` 命令 `skills/`。说明见 `plugin/README.md` |
| `fusion/` | 用 Fusion 迭代 lyfusion 本身时的项目设置(`config.json`、`decisions.md`);`tasks/`、`runs/`、`fusion.db` 是运行数据，不提交 |
| `lint/` | 检查清单和 `check.py`(本仓库 lint 命令的一部分) |
| `design/` | 设计文档，各版本的改动见 `design/v5.0.0-*.md` |
| `v5/` | 进度 `progress.md`(含"留给 v5.1.0"的清单)、各 rc 的任务说明 `rc*-brief.md`、交接 `rc2-handoffs/`、打包脚本 `build_plugin.py`(包在 `dist/`,不提交)、预研和证据 |
| `.claude-plugin/marketplace.json` | 本机用的插件市场，开发时加载 `plugin/`,不发布 |
| `suggestions/`、`updates/` | 试点数据、复盘、更新简报(大多是 v4 及以前的) |
| `SKILL.md`、`addon/`、`tests/`、`viewer/` | v4 技能的历史文件:技能本体、装进项目的派工脚本和台账、测试、帕累托查看器 |

## lint 推荐命令
打开 Fusion 时用 `--lint` 填写(例如 `/fusion on --test "<测试命令>" --lint "<lint 命令>"`),工具要先装好。lint 是检查，只报错、不改文件，所以用不带自动修复的写法:
| 语言 | 工具 | lint 命令 |
|---|---|---|
| Python | ruff(`pip install ruff`) | `python -m ruff check --no-cache .`;老项目先加 `--select E4,E7,E9,F`,只查真错误 |
| Godot(GDScript) | gdtoolkit(`pip install gdtoolkit`) | `gdlint .` |
| Java(Gradle,比如 Minecraft 模组) | Spotless 或 Checkstyle 插件 | `gradlew.bat spotlessCheck checkstyleMain` |
| JavaScript / TypeScript | Biome | `npx @biomejs/biome check .` |
| C#(.NET) | dotnet format | `dotnet format --verify-no-changes` |

一个项目里有多种语言时，用 pre-commit 统一入口:`--lint "pre-commit run --all-files"`,缓存目录用 `PRE_COMMIT_HOME` 指到工作区里。

## 改了之后
测试、lint、mod 测试和打包的命令见 `CLAUDE.md` 的 "Developing"。

## 需要
- Claude Code(桌面应用的 Code 标签页或命令行)。
- Python 3(只用标准库)和 Git。项目要是 git 仓库;v5 不依赖 LiEC。
- 登录好的 Codex CLI。它可能装在 WindowsApps 下带版本号的路径里，由引擎自己找。
