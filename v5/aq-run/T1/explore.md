# T1 探索包

## summary

目标是给 T1 的 Q1–Q3 提供可核对的代码入口：CLI、MCP 工具、hooks 和监控如何接到命令处理与监督循环；各项约束在哪实现；测试夹具和已有测试覆盖什么。

## 相关代码

`plugin/core/fusion_core/cli.py:198-204` — CLI 子命令复用工具表的函数映射；每次调用都会创建并关闭项目上下文。

```python
def cmd_tool(args, tool) -> dict:
    root = _root(args)
    ctx = Ctx(root, actor=args.actor)
    try:
        return tool["fn"](ctx, _args_json(args.json))
    finally:
        ctx.close()
```

`plugin/core/fusion_core/supervisor.py:115-153` — `tick()` 按优先级处理接管/清理、已启动运行、待启动运行、检查和集成；每次最多做一件事。

```python
def tick(self) -> int:
    """做一件能做的事,返回 1;没事可做返回 0。"""
    s = self.state()
    cfg = self.cfg()
    for t in s["tasks"].values():
        if t.get("takeover") and not t.get("takeover_done"):
            self.do_takeover(s, cfg, t)
            return 1
```

`plugin/core/fusion_core/cli.py:87-123` — `wait` 持有监督租约时反复 `tick()`，再查新事件；有可展示通知就返回，没有进行中的运行也返回，超时则提示可再次运行。`--after` 默认从当前事件末尾开始。

```python
while True:
    if store.take_lease(sup.conn, sup.holder):
        while sup.tick():
            pass
    new = [e for e in store.read(ctx.conn, last) if not args.task or e["task"] in (args.task, None)]
    if new:
        last = new[-1]["seq"]
        lines = views.notifications(s, new)
        if lines:
            return {"ok": True, "notifications": lines, "status": views.prompt_line(s), "after": last}
```

`plugin/core/fusion_core/prompts.py:104-112` 与 `plugin/core/fusion_core/supervisor.py:257-278,321-327` — 探索用只读沙箱，不要求 JSON schema；结束时保存原始文本作为探索答案。普通实现则走 JSON 报告解析：`codex.py:119-140` 取 `last.txt` 并尝试解析 JSON；`validate.py:190-211` 校验报告字段。

```python
def explore_prompt(questions: list[str], task: dict | None) -> str:
    lines = ["你是 lyfusion 的助手。这是只读探索:只读代码、不要修改任何文件。",
             "请逐条回答下面的问题。回答要具体:写出文件路径和行号、现有约定、容易踩的坑。"]
    if task:
        lines.append(f"背景:任务 {task['id']},目标:{task['plan']['goal']}")
```

`plugin/core/tests/conftest.py:45-68,91-103` — 每个测试建独立 Git 项目，配置假 Codex 及其 JSON 剧本；通过 `Proj` 帮手推进监督器，不依赖真实 Codex。

```python
class Proj:
    def __init__(self, base: Path):
        self.base = base
        self.root = base / "proj"
        self.script_path = base / "script.json"
        self.root.mkdir(parents=True)
```

`plugin/core/tests/fake_codex.py:3-10,20-37,55-67` — 剧本可写/删文件、记录命令、返回报告或纯文本、模拟等待及续用失败；每次调用的参数、prompt、工作目录写入 calls 日志。

## Q1：入口、路由与 wait

- `plugin/commands/fusion.md:1-` 提供用户斜杠命令映射：`status/on/off/guide/model/effort/fast/test` 分别调用 `fusion-core` 子命令；其余交给 `fusion_*` 工具。打开时先跑 preflight。
- `plugin/core/fusion_core/tools.py:74-135` 定义 12 个工具及函数映射：`status/intent/plan/explore/delegate/answer/review/request_changes/accept/reject/cancel/takeover` → `commands.py` 的 `cmd_*`。`CLI_NAMES` 在 `tools.py:137-138` 从同一工具表生成 CLI 别名；`cli.py:250-252,300-302` 解析并派发。
- `commands.py` 管校验、状态条件和事件写入；主要入口在 `:71-162,165-233,236-379,382-441`。`state.py:30-34,327-340` 从事件重建状态。`supervisor.py:81-97` 是后台监督主循环，`tick():115-153` 执行具体工作。`views.py:89-` 生成审查/状态视图，`:393-423` 把事件转成 monitor 通知。
- `plugin/monitors/monitors.json:1-6` 启动 `events --follow --audience lead`；`cli.py:132-165` 轮询新事件并输出通知。`plugin/hooks/hooks.json:4-12` 配置 SessionStart、UserPromptSubmit、PreToolUse；`hooks.py:25-45` 分别注入会话说明、单行状态、目标文件编辑提示，关闭 Fusion 或非项目时静默。它们不批准或阻止操作。
- `wait` 的确能让 lead 在收到可映射的通知或进入 idle 后返回；有仍在运行的任务时会继续等到通知或超时。监督循环每次 tick 处理一件事；遇到可持续处理的事会连续 tick，再按 `poll` 间隔休眠。

## Q2：规则实现位置与约束

- 决策版本和旧引用：`commands.py:71-83`、`validate.py:135-`、`intent.py`；`intent.md` 是可读投影，事件库是状态来源。
- 工作项、边界、direct、`follows`、范围重叠、用户可感知内容和 `tests_may_change`：`validate.py:40-132`。`prompts.py:6-16,48-75` 将边界、工作项和允许改动的测试写进助手 prompt。
- `follows` 样例提交及 lead 工作项限制：`commands.py:123-162`；样例提交必须可在 base branch 上找到。`direct` 验收由 `commands.py:321-327` 发起，`supervisor.py:463-478` 在 lead 工作目录跑直接检查。
- 决定债、阻塞问答及非阻塞选项：`supervisor.py:346-376` 解析报告并写问题/债事件；`commands.py:165-233` 处理回答、续跑或驳回选择；`commands.py:346-358` 阻止尚未处理的债通过验收。
- 人工签字：`validate.py:55-64` 校验 manual 检查；`commands.py:301-320` 检查 signer/by/note 和签字；`views.py:89-` 展示审查内容。
- 自动修复最多 2 次：`config.py:23-24` 默认值；`supervisor.py:449-460` 决定是否排 fix run，`state.py:103-123` 维护次数。修改意见默认最多 3 轮：`commands.py:248-285`，可配置 `max_change_rounds`。
- takeover：`commands.py:407-420` 发事件；`state.py:310-316` 将任务转为 direct 并把助手工作项交回 lead；`supervisor.py:566-586` 停止运行、搬运可选半成品、保存 diff、清理工位。
- “用户可感知文件”由 `config.py:10-27` 的 `perceivable`、`validate.py:95-101`、`checks.py:125-130` 共同判定；检查后由 `supervisor.py:442-448` 发信号。
- 检查及禁止命令/扫描：`checks.py:49-78,81-145`。未获允许的测试改动会用旧测试跑新代码；允许范围要求 `tests_may_change` 项目引用决定。集成测试、squash 成单提交、快进及失败回退在 `supervisor.py:479-525`。基础分支默认从 init 时当前分支读取，见 `config.py:89-103`。
- 容易误读之处：环境错误在 `checks.py:53-61` 会重试一次；它与“测试失败后自动修复最多 2 次”是两种不同重试。`cmd_wait` 的新进程默认不会回报启动前已有的通知。

## Q3：测试覆盖与报告约定

`fake_codex.py` 的 `report` 是测试剧本提供的助手最终报告；实际报告字段由 `validate.py:190-211` 校验：`summary`、`items`、`decisions`、`choices`、`questions`、`assumptions`、`downstream`、`problems`。探索则返回纯文本答案，不经过报告 schema。

`test_flow.py` 覆盖：`test_happy_path` 完整派工/检查/审查/验收；`test_blocked_then_answer_resumes_same_thread` 阻塞答复续用；`test_fix_loop_then_check_failed` 两次修复失败；`test_fix_succeeds` 修复成功；`test_weakened_test_is_violation` 旧测试保护；`test_forbidden_command` 禁止命令；`test_integration_conflict_returns_to_review` 冲突；`test_main_moved_without_conflict_merges` main 前进后 squash 合并；`test_fast_forward_refused_by_dirty_lead_tree` dirty 工作区拒绝快进；`test_takeover_brings_changes` 接管并搬运；`test_reject_cleans_up` 退回清理；`test_cancel_kills_running` 取消并结束进程；`test_missing_report_asks_once` 缺报告时补问一次；`test_change_rounds_limit` 修改轮次上限；`test_nonblocking_disagree_becomes_change` 非阻塞意见驳回转修改；`test_recheck_when_check_config_changes` 配置变化触发复检；`test_direct_task` direct 检查；`test_wip_one_line` 只允许一条活动工作线；`test_fix_without_changes_signals` 无修改的修复产生信号。定义行见 `test_flow.py:44-336`。

`test_parts.py` 覆盖：任务校验/范围重叠/follows/experience 决定/版本与旧引用/错误状态/glob（`:21-87`）；探索与工位线程复用、模型变化交接、续用失败、监督器重启、租约和并发写入（`:92-191`）；MCP 协议及项目外空工具（`:196-228`）；hooks 注入、静默和 JSON 输出（`:233-267`）；通知/台账、CLI 往返、脱敏、wait、项目外 events follow（`:271-332`）。测试函数索引在 `test_parts.py:21-324`。

## 约定和坑

代码路径、行号以上述文件为准。测试用 pytest fixture 和 fake Codex，断言状态、事件、Git 结果和 prompt；`follows` 样例必须先提交；report 不合法会记录问题并触发补交报告流程。这里只做了代码阅读，没有运行测试或更改文件。

## 模型备注(gpt-6-luna):写计划时参考
- 改造现有代码时容易改掉原有行为(报错文字、空行和空值的处理、编号规则、路径解析)。动手前先列出要保留的原有行为,逐条写回归测试。出处:fusion-bench C-H2(seed 空库检查、CSV 空白行、next_id)。C-H3(悬挂引用的报错文字、相对路径),2026-11-03,L3。
