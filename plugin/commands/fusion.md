---
description: 打开、关闭或设置 lyfusion(Claude lead + Codex 助手)
argument-hint: on | off | status | guide | model <名字> | effort <low|medium|high|xhigh> | fast on|off | test <命令>
---
用户给的参数:$ARGUMENTS

`fusion-core` 是 lyfusion 插件 `bin/` 里的命令(插件启用时在 PATH 里)。找不到这个命令时,告诉用户插件可能没有启用,不要去别处找。

按参数运行对应的一条命令,把结果用一两句中文告诉用户:

| 参数 | 命令 |
|---|---|
| 空 或 status | `fusion-core status` |
| on | 先 `fusion-core preflight`,把没通过的项告诉用户;再 `fusion-core on`。项目还没打开过 Fusion 且不知道测试命令时,先问用户测试命令,然后 `fusion-core on --test "命令"` |
| off | `fusion-core off` |
| guide | `fusion-core guide`,把输出当作 lead 的使用说明读一遍 |
| model 名字 | `fusion-core config set '{"local":{"sidekick":{"model":"名字"}}}'` |
| effort 档位 | `fusion-core config set '{"local":{"sidekick":{"effort":"档位"}}}'` |
| fast on / fast off | `fusion-core config set '{"local":{"sidekick":{"fast":true}}}'`(off 写 false) |
| test 命令 | `fusion-core config set '{"config":{"test":"命令"}}'` |

打开之后:
- `fusion_*` 工具会出现(在延迟工具列表里时,用 ToolSearch 搜 `fusion` 加载)
- 新对话开始时会自动注入使用说明;当前这个对话里,运行一次 `fusion-core guide` 读说明
- 这些命令只改项目里的 `fusion/` 文件夹,不改 Claude Code 的设置
