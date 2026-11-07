# lyfusion-plugin(v5.0.0-aq.2)

专为 Claude Code 做的双代理协作插件,是 Lily 的个人项目,不是 Anthropic 官方产品。Claude 当 lead,Codex CLI 当助手。lead 通过 `explore`、`delegate`、`revise`、`accept` 四个阻塞命令工作;任务状态和检查由本地 Python 引擎管理。

## 组成

| 部分 | 位置 | 做什么 |
|---|---|---|
| 引擎 fusion-core | `core/` | Python 标准库和 sqlite;运行 Codex、检查候选并集成 |
| SessionStart 钩子 | `hooks/hooks.json` | Fusion 开启时注入简短使用说明 |
| 技能 `/fusion` | `skills/fusion/SKILL.md` | `/fusion on`、`off`、`status`、`model`、`effort`、`fast`、`test`;只由用户手动运行(`disable-model-invocation`),也可以写成 `/lyfusion-plugin:fusion` |

插件不带 `bin/`(claude.ai 托管的插件不允许):lead 用 `python "<安装目录>/core/fusion-core.py" <子命令>` 运行引擎,完整路径由 SessionStart 注入的使用说明给出;`/fusion` 用 `${CLAUDE_PLUGIN_ROOT}`。

lead 在 Bash 后台运行四个主流程命令,每条命令会等待结果并写入 `fusion/explore.md` 或 `fusion/review.md`。跨任务设计决定保存在 `fusion/decisions.md`。

## 支持什么
- lead:Claude Code 里的 Claude(桌面应用的 Code 标签或命令行)。在普通聊天里钩子不加载,插件不起作用
- 助手:OpenAI 的 Codex CLI(`codex exec`)。Codex CLI 能用的模型都可以用 `/fusion model 名字` 切换,每个模型各记各的 effort 和 fast。默认 gpt-6-luna、effort high、fast 关;实际任务里测过的是 gpt-6-luna,gpt-6-astra 只试过切换
- 需要:Python 3(只用标准库,在 3.12 上测过)、git、已登录的 Codex CLI。项目要是 git 仓库

## 隐私和安全

- 不调用 Claude API,不读取 Claude 配置或 Codex 登录文件。
- 启动 Codex 前清除 `CLAUDE*`、`ANTHROPIC*` 环境变量;Codex 只在独立工位中工作。
- 运行日志按常见密钥格式脱敏,`fusion/runs/` 不进 git。

## 测试

运行 `cd core && python -m pytest -q tests`。测试使用假 Codex,不会调用真实 Codex。

打包运行 `python ../v5/build_plugin.py`,生成 `../v5/dist/lyfusion-plugin-5.0.0-aq.2.zip`。未打开过 Fusion 的项目里钩子不输出。
