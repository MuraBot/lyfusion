# T2 最终报告

- 状态:停止 · 最后阶段 3
- 摘要:T2 三阶段已完成：助手设置改为按模型保存，修复五项问题；打包成功。阶段 2 的 8 项测试通过；全量测试中 67 项通过，另按任务卡说明排除一个无法在当前沙箱终止子进程的用例后重跑通过。
- 停止原因:仓库检查遇到环境/范围问题：python tools/check.py 报告 CLAUDE.md 缺失，并提示根目录 README.md 有一条超长句。请 lead 选择：恢复 CLAUDE.md 并处理 README 警告后重跑检查（推荐）；或记录为仓库既有问题并接受 T2。

## 要 lead 回答的问题
- 仓库检查如何处理：恢复缺失的 CLAUDE.md 并处理 README.md 警告后重跑（推荐），还是将其记录为既有问题并接受 T2？

## 修改请求的回应
- 无

## 假设
- 无

## 接口修改请求
- 无

## 给下游
- fusion/local.json 的 sidekick 设置采用 {"model": "名字", "models": {"名字": {"effort": "档位或 null", "fast": true/false}}}；旧版平铺 effort/fast 会在读取时迁移到当前模型。
- 每次运行事件记录实际使用的 model、effort、fast，台账按任务汇总助手档位和 lead/助手 token 用量（单位 M）。

## 问题
- 全量测试中 test_cancel_kills_running 因 Windows 沙箱未能终止子进程而失败，清理时日志文件仍被占用；按任务卡约定使用 -k 排除此用例，67 passed、1 deselected。失败和重跑输出均已保存。
- python tools/check.py 报 CLAUDE.md 不存在，并提示 README.md 第 46 行超长；两者均在任务允许写入范围 plugin/ 之外。
- 未更新 learning.md 的 fusion-core 模块笔记，因为任务卡可写范围限定为 plugin/；T2 工作记录已保存在 dispatch-logs/evidence/T2/notes.md。
