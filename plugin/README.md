# lyfusion 插件(v5.0.0-aq.0)

用于 Claude Code 的双代理协作插件:Claude 当 lead,Codex CLI 当助手。lead 通过 `explore`、`delegate`、`revise`、`accept` 四个阻塞命令工作;任务状态和检查由本地 Python 引擎管理。

## 组成

| 部分 | 位置 | 做什么 |
|---|---|---|
| 引擎 fusion-core | `core/` | Python 标准库和 sqlite;运行 Codex、检查候选并集成 |
| SessionStart 钩子 | `hooks/hooks.json` | Fusion 开启时注入简短使用说明 |
| 命令 | `commands/fusion.md` | `/fusion on`、`off`、`status`、`model`、`effort`、`fast`、`test` |
| `bin/` | `fusion-core`、`fusion-core.cmd` | 引擎的命令行入口 |

lead 在 Bash 后台运行四个主流程命令,每条命令会等待结果并写入 `fusion/explore.md` 或 `fusion/review.md`。跨任务设计决定保存在 `fusion/decisions.md`。

## 隐私和安全

- 不调用 Claude API,不读取 Claude 配置或 Codex 登录文件。
- 启动 Codex 前清除 `CLAUDE*`、`ANTHROPIC*` 环境变量;Codex 只在独立工位中工作。
- 运行日志按常见密钥格式脱敏,`fusion/runs/` 不进 git。

## 测试和打包

```bash
cd core && python -m pytest -q tests
python ../v5/build_plugin.py
```

测试使用假 Codex,不会调用真实 Codex。打包生成 `../v5/dist/lyfusion-5.0.0-aq.0.zip`。
