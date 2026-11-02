---
name: lyfusion
description: lyfusion,Lily 的多 agent 协作与调度(Fusion 模式):Claude 当 lead 拆分、定接口、写简报、审查模块;Codex 助手一口气做完简报,只在开头和结尾交换产物(边界交接);派工脚本、合并命令、提交钩子、派工台账;以及对这套模式的试点数据和复盘研究。用于协作方式是 multi 的 LiEC 项目:派工给 Codex、模块审查与合并,或复盘和改进多 agent 协作。
---

# lyfusion

用途:让多个 agent 分工开发时不互相干扰,并用真实数据研究这套协作模式值不值。
前提:项目是按 LiEC 技能建立的。立项、spec、拆任务、收尾按 LiEC 做,本技能只管多 agent 的开发阶段。
原则:遵循 LiEC 的三条原则和"和 Lily 协作"。Claude 的使用边界见项目 `CLAUDE.md`,这里不重复。

## 安装到项目
1. 把本技能 `addon/` 里的全部内容复制到项目根目录。目录结构相同,只新增文件。
2. 运行 `git config core.hooksPath tools/hooks` 和 `python tools/progress.py set-collab multi`。
3. 运行 `python tools/check.py`,确认 0 个错误。

## 读什么
| 你是 | 读 |
|---|---|
| lead(Claude,Lily 开着的对话) | 项目里的 `prompts/dispatch.md` |
| 助手(被派工的 agent) | 项目里的 `prompts/sidekick.md` 和你的简报 |
| 迭代本技能的会话 | `suggestions/`(试点数据、复盘、草案)、`updates/`(每次改了什么) |

## 研究与复盘
- 流程问题整理成一份建议,交给迭代本技能的会话,存进 `suggestions/`。1 个样本只当线索,不直接推出规则。
- 一次只改一个主要变量,事先写下预测。先测整个系统(含 lead 的 token),再优化局部。
