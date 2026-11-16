# 设计决定
> lead 直接编辑这个文件。每次派工,引擎把全文带给助手。只写所有任务都要守的决定。

## rc.1 全程
1. 引擎只用 Python 标准库和 sqlite,不加第三方依赖。测试用 pytest 和假 Codex(`tests/fake_codex.py`),不调用真 Codex、不联网
2. lead 看到的东西不随手改:使用说明(`views.lead_guide`,≤24 行,rc.2 起)、4 个动作(explore、delegate、revise、accept)和它们的输出,只在任务明确要求时改。新功能藏在引擎里,lead 不多花调用
3. **设置分三层,每个值只存一处**(Lily 2026-11-13 同意):引擎默认值(`config.py` 的常量)→ 项目 `fusion/config.json`(进 git,项目的事:test、lint、network、干净模式 `clean`、`context_ratio` 等)→ 本机 `fusion/local.json`(不进 git,个人选择:开关、助手模型、按模型的 effort/fast/上下文上限、Codex 路径)。一个键只属于一层,不在两层里互相覆盖。按模型的设置都放 `sidekick.models.<模型>` 下,没登记的模型用默认值。算得出来的值(例如换工位阈值 = 上下文上限 × `context_ratio`)不另存。新字段都有默认值,读到旧格式或缺字段的文件不报错,照默认读
4. `/fusion` 技能和以后 Fusion 栏的面板只改 `local.json`,都走 `fusion-core config <动作>`;项目的事改 `fusion/config.json`。`fusion-core status` 显示当前值。用户看到的文字:rc.2 起新写、重写的用英文(见 rc.2 第 1 条)
5. 不读 `~/.claude/`、AppData 里 Claude 的文件夹、Codex 的 `auth.json`;引擎不解析 `~/.codex/config.toml`,**唯一例外**(Lily 2026-11-14 同意):干净模式下只读出 `windows.sandbox` 和 `sandbox_workspace_write.network_access` 两项、用 `-c` 原样传,别的键一概不读不带。启动 Codex 和检查命令前去掉 `CLAUDE*`、`ANTHROPIC*` 环境变量。Codex 不用绕过沙箱或审批的参数 Second exception (rc.2 task 4): the engine reads `models_cache.json` in the Codex home for model capabilities; nothing else in that folder.
6. 版本号已是 `5.0.0-rc.1`:不改 plugin.json、`__init__.py`、README 里的版本
7. 已有测试都要继续通过。改了已有行为就同时改对应测试,并在报告里写明为什么
9. 状态格式版本(任务 4 起):`fusion_core.SCHEMA` 一个数,`config.json`、`local.json`、`fusion.db` 共用。只有旧版本会读错的改动才加 1;只加带默认值的新字段、新的事件数据字段(旧版本忽略也不出错)不用加。改了格式就同时改迁移和测试
8. 本项目的测试参数:跑整份测试文件时加 `-n 6`(`test_cli.py` 单线程约 1 分钟,比并行跑全量的约 26 秒还慢),只跑单个用例不用加;在你的沙箱里跑 pytest 一律加 `--basetemp=tests/_pytest_tmp`(已在 `.gitignore`;沙箱写不了系统临时目录,否则清理时报 PermissionError)。通用的测试跑法见 WORK_RULES
10. Model capabilities (display name, reasoning efforts, Fast Mode, max context) come from Codex's own `$CODEX_HOME/models_cache.json` (default `~/.codex/models_cache.json`), read as it is, never copied (rc.2 task 4, Lily 2026-11-14). If it is missing, unreadable or has an unexpected shape, the engine uses its built-in table and shows a warning. Models in neither get conservative defaults: efforts low..xhigh, no Fast, no context cap.

## rc.2
1. Language (rc.2 task 18): every text a model reads that you write or rewrite is English: LEAD_GUIDE and model notes, sidekick prompts, engine output to the lead (explore/review packs, errors, next-step hints, status, ledger), code comments and docstrings, test names and assertion text, panel and `/fusion` text. Text you do not touch stays as it is until the final translation task. Process docs Lily reads stay Chinese: `v5/`, `design/`, `lint/`, handoffs. If you must edit a Chinese doc, change only what the brief names and check `git diff` shows no `?` runs where Chinese was (lint C4).
2. The rendered LEAD_GUIDE is at most 24 lines; the whole injected SessionStart context (guide + model notes + handoff pointer) is at most 30 lines.
