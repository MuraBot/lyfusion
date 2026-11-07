# lyfusion 插件(v5.0.0-a,开发中)

用于 Claude Code 的双代理协作插件:Claude 当 lead(理解用户、判断、计划、审查、验收),本机的 Codex CLI 当助手(在独立的工位目录里按任务单实现)。个人项目,不是 Anthropic 或 OpenAI 的官方产品;暂不发布到插件市场。

设计:`../design/v5.0.0-a-engineering.md`。进度:`../v5/progress.md`。

## 组成
| 部分 | 位置 | 做什么 |
|---|---|---|
| 引擎 fusion-core | `core/` | Python 标准库。事件库、状态机、任务单校验、Codex 运行、检查流水线、集成 |
| MCP 服务器 | `.mcp.json` → `fusion-core serve` | 给 lead 的 12 个 `fusion_*` 工具;后台监督助手运行 |
| 钩子 | `hooks/hooks.json` | 新对话注入使用说明和状态;每次提问注入一行状态;编辑到助手正在改的文件时给提示 |
| monitor | `monitors/monitors.json` | 助手跑完、提阻塞问题、检查出结果时通知 lead |
| 命令 | `commands/fusion.md` | `/fusion on`、`off`、`status`、`model`、`effort`、`fast`、`test` |
| `bin/` | `fusion-core`、`fusion-core.cmd` | 引擎的命令行入口 |

## 对别的项目零影响
项目里没有 `fusion/config.json`(没用 `/fusion on` 打开过)时:MCP 工具列表是空的,钩子不输出,monitor 只安静地等。

## 遵守的规则
- 只做 Claude Code 的普通使用:不调用 Claude 的 API,不经手任何登录凭据,不用定时器开回合,不替用户批准权限
- 插件只运行自己安装目录里的代码;状态都在项目的 `fusion/` 里;不使用插件数据目录;不读取 Claude Code 的其他配置和记录;不读取 Codex 的登录文件
- 启动 Codex 前去掉 `CLAUDE*`、`ANTHROPIC*` 环境变量;Codex 用 `workspace-write` 沙箱,只能写工位目录
- 写进 `fusion/runs/` 的日志按常见密钥格式脱敏;`runs/` 不进 git

## 测试
```bash
cd core && python -m pytest -q tests
```
测试用假 Codex(`core/tests/fake_codex.py`),不会调用真的 Codex。

## 打包
```bash
python ../v5/build_plugin.py
```
生成 `../v5/dist/lyfusion-<版本>.zip`,在 Claude 桌面应用的"插件 → 管理插件"里上传。
