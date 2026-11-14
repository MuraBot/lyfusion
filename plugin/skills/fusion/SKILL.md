---
name: fusion
description: 打开、关闭或设置 lyfusion-plugin(只由用户手动运行)
argument-hint: "on [--test <命令>] [--lint <命令>] | off | status | model <名字> | effort <low|medium|high|xhigh> | fast on|off | compact <数字> | test <命令>"
disable-model-invocation: true
---
用户给的参数:$ARGUMENTS

引擎命令是 `python "${CLAUDE_PLUGIN_ROOT}/core/fusion-core.py"`,下表写作 `FC`。运行时把 `FC` 换成这条完整的命令(带引号照写)。文件不存在时告诉用户插件可能没启用,不要去别处找。

按参数运行对应命令,把结果用一两句中文告诉用户:

| 参数 | 命令 |
|---|---|
| 空 或 status | `FC status` |
| on --test 命令 [--lint 命令] | 先 `FC preflight`,汇报没通过的项;再运行 `FC on --test "命令" [--lint "命令"]` |
| off | `FC off` |
| model 名字 | `FC config model 名字` |
| effort 档位 | `FC config effort 档位` |
| fast on / fast off | `FC config fast on|off` |
| compact 数字 | `FC config compact 数字` |
| test 命令 | `FC config set '{"config":{"test":"命令"}}'` |

打开后,SessionStart 会注入 4 个动作的使用说明。所有状态都保存在项目的 `fusion/` 目录里。

项目还没打开过 Fusion、又不知道测试命令时,先问用户测试命令,再 `FC on --test "命令"`。
