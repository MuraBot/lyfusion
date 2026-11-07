# forbidden.txt 的核对(lead,2026-11-07)

- 命中的是 v4.2.1 派工脚本的 `$ForbiddenPattern`(`--no-verify`)
- 核对事件流:命中在命令的输出(`aggregated_output`,助手用 `python -c` 打印 `supervisor.py` 的源码,源码里有引擎自己的禁止规则),命令本身没有
- 结论:误报,助手没有用禁止的操作。forbidden.txt 保留原样,不删;T1 验收时 lead 自己跑测试和 lint,不走 `-Accept`;在最终报告里告诉 Lily
- 改进(给 v4 脚本,以后再说):禁止操作扫描只看 `item.command`,不看整行事件
