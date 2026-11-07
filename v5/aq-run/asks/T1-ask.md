# T1 探索:lyfusion v5.0.0-aq

## 任务原话
任务说明在 `v5/aq-brief.md`(Lily 定的,全文就是任务原话,先读它)。这次要在 `plugin/` 里实现其中的"决定"1~11 和 13:把 v5.0.0-a 的插件收窄成 lead 只有 4 个动作(探索、派工、修改、验收)、入口是阻塞到有结果的 Bash 命令、计划是 4 个字段的 JSON,引擎内部能力保留。背景在 `v5/handoff-2026-11-07.md`、`design/v5.0.0-a-engineering.md`(只按需读,不用通读)。

## lead 想知道的
Q1. 现在 lead 面前有哪些入口:`cli.py` 的每个子命令、`tools.py` 的 12 个工具、`hooks.py` 的每个钩子、`monitors.json`、`commands/fusion.md`。每个入口调到 `commands.py` / `supervisor.py` / `views.py` 的哪个函数?`wait` 是怎么阻塞、怎么顺便监督的(supervisor 的哪个循环),能不能直接拿来做"探索/派工/修改/验收命令阻塞到有结果再退出"?

Q2. 说明里"砍掉"的那些(工作项和类型/负责人/follows、direct 任务、意图记录 `intent`、决定债、三组边界、"用户能感知的文件"、人工检查和签字、3 层审查视图、接管 takeover、多余的信号、UserPromptSubmit/PreToolUse 钩子)分别在哪(`文件:行`)?哪些和 `state.py` 的重放、`supervisor.py`、`prompts.py`、事件类型缠在一起,删掉会牵连什么?"留在引擎里"的那些(会话续用、工位和任务分支、候选提交、检查失败自动修 ≤2 次、环境错误重跑、禁止操作扫描、旧测试跑新代码、验收合并压成 1 个提交、修改 ≤3 轮、台账、脱敏)各在哪?

Q3. 测试现在怎么写:`conftest.py` 的夹具、`fake_codex.py` 的脚本格式、`test_flow.py` 和 `test_parts.py` 每个测试测什么(一行一个),哪些测的是要砍的功能?给 Codex 的提示(探索、实现、修改、自动修)在哪里拼出来,探索的结果和审查视图现在是哪个函数产出的、产出什么格式?
