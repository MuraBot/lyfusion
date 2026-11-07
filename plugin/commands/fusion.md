---
description: 打开、关闭或设置 lyfusion
argument-hint: on [--test <命令>] [--lint <命令>] | off | status | model <名字> | effort <low|medium|high|xhigh> | fast on|off | test <命令>
---
用户给的参数:$ARGUMENTS

`fusion-core` 是 lyfusion 插件 `bin/` 里的命令。找不到时告诉用户插件可能未启用,不要去别处找。

按参数运行对应命令,把结果用一两句中文告诉用户:

| 参数 | 命令 |
|---|---|
| 空 或 status | `fusion-core status` |
| on --test 命令 [--lint 命令] | 先 `fusion-core preflight`,汇报未通过项;再运行 `fusion-core on --test "命令" [--lint "命令"]` |
| off | `fusion-core off` |
| model 名字 | `fusion-core config model 名字` |
| effort 档位 | `fusion-core config effort 档位` |
| fast on / fast off | `fusion-core config fast on|off` |
| test 命令 | `fusion-core config set '{"config":{"test":"命令"}}'` |

打开后,SessionStart 会注入 4 个动作的使用说明。所有状态都保存在项目的 `fusion/` 目录中。

项目还没打开过 Fusion 且不知道测试命令时,先问用户测试命令,再 `fusion-core on --test "命令"`。
