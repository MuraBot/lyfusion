# 更新简报:v3 轻 lead(2026-11-02)

> 来源:小熊对比实验和 Cognition Fusion 的调研(`suggestions/2026-11-02-research-fusion-gap.md`)。方案和 Lily 的决定见 `suggestions/2026-11-02-v3-plan.md`。
> Lily 的决定:1 个 Claude lead + 1 个 Codex 助手,最多再开 1 个 Claude 子代理做前端;不开审查者(弱模型审强模型,意见还要 lead 逐条反驳)。

## 改了什么
- **`prompts/dispatch.md` 重写(89 → 75 行)**:
  - 人数表:lead、1 个助手、可选的 1 个前端子代理;删掉审查者。同一时刻只有一个 agent 写同一个分支。
  - 先选模式:**独做**(短任务、判断就是交付物、连续排错)或**搭档**(能拆出执行部分)。拿不准选独做。搭档时 lead 的预算:每个任务 15 轮、3 次交接。
  - 搭档时 lead 只做判断:早放手;简报是规格不是口述;只读最终报告、`diff --stat` 和关键改动;要改的写成新交接、续用同一个助手会话,lead 不亲手改。
  - 简报级别表加一列"助手能不能反驳":L1 不改方向,L2 可以提疑问,L3 可以反驳。助手越弱,级别越低。
- **`prompts/sidekick.md`**:"简报的强度"按级别写清能不能反驳。
- **派工脚本**:删掉 `-Review`(只读审查会话);派工时自动 `progress.py set-status 任务 doing`,lead 每次派工只运行 1 条命令。
- **LiEC**:`stages/3-build.md` 和 `template/prompts/review.md` 里"多 agent 项目用 `-Review`"改成"由 lead 审查"。

## 数字
- 规则文档:lyfusion 172 → 158 行(上限 183)。
- 测试:`test_fusion.py` 4 个、`test_dispatch.py` 8 个,全部通过。审查测试删掉,改成"派工时改进度"和"合并前把 main 合并进任务分支"的断言。LiEC 14 个全部通过。

## 还要验证的
fusion-bench(M0 / M1)的结果:轻 lead 的质量能不能到 Opus 单 agent 的 80%,Claude 用量能不能低于单 agent。见 `C:\AI WithMe\fusion-bench\results\`。
