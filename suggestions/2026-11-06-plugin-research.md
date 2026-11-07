# 调研:把 lyfusion 做成 Claude Code 插件(2026-11-06)

> Lily 想在 v5 把 lyfusion 从 skill 改成插件。本文记录插件能做什么、相关规则和政策,以及 lyfusion 可以怎么用。
> 来源是 Claude Code 官方文档(https://code.claude.com/docs ,每页加 `.md` 可取原文)和 Anthropic 的 Consumer Terms(2025-10-08 生效版)。

## 插件是什么
- 插件就是一个文件夹,里面放多个组件,作为一个整体安装、启用和更新。清单文件 `.claude-plugin/plugin.json` 里只有 `name` 是必填的
- 安装来源是"市场"(marketplace):一个 JSON 目录。可以自己建,比如放在 GitHub 仓库里;也可以直接把文件夹给别人加载
- 插件在 CLI、桌面端 Code 标签页、VS Code 扩展里都能用
- 插件启用后每个会话都会加载:每个 skill、agent 的名字和描述每轮都会占上下文。全文只在用到时才加载

## 插件能装的组件
| 组件 | 能做什么 | lyfusion 能怎么用 |
|---|---|---|
| skills | 和现在的 SKILL.md 一样,也能用 `/插件名:技能` 调用 | 保留,但只写判断和方法,步骤交给下面的组件 |
| agents | 子代理,有自己的提示、工具限制和模型 | 比如便宜模型读交接包;要算 Claude 用量,慎用 |
| hooks | 在生命周期的节点自动执行:编辑后、工具调用前、回合结束、会话开始等 | **用结构代替提醒**:派工期间拦住 lead 改助手负责的文件;任务没验收时提醒、不让结束;会话开始时注入当前任务状态 |
| bin/ | 插件启用时放进 PATH 的命令行工具 | 派工脚本不再复制到每个项目,版本跟着插件走 |
| monitors | 会话开始(或某个 skill 第一次运行)时启动的后台命令,输出会以通知形式发给 Claude | Codex 跑完或卡住时通知 lead,不用等、不用轮询 |
| MCP 服务器 | 给 Claude 提供带参数结构的工具 | 把探索、派工、验收、退回做成工具,参数有结构,比命令行参数少出错 |
| mods(JS 钩子模块) | 画面板、加 `/命令`(不发起 Claude 回合)、拦截或改写工具调用、注册工具、在会话之间发消息、读写文件、启动进程 | 面板显示任务、台账、Codex 进度;登记、检查、台账、提交这类固定步骤用 `/命令` 直接跑,**不花 Claude 用量** |
| workflows | 用脚本编排多个 Claude 子代理 | 编排的是 Claude 而不是 Codex,和 lyfusion 的目标关系不大 |
| userConfig | 安装时让用户填的设置 | 推理强度、速度档、Codex 路径等项目设置 |
| settings.json | 只认 `agent` 和 `subagentStatusLine` 两个键 | 基本用不上 |
| 输出风格、主题 | 改回复风格和界面颜色 | 不需要 |

其他:
- `${CLAUDE_PLUGIN_ROOT}` 是安装目录,每个版本一份,不要往里写状态;`${CLAUDE_PLUGIN_DATA}` 是 `~/.claude/plugins/data/<id>/`,跨版本保留;`${CLAUDE_PROJECT_DIR}` 是项目根目录
- 插件可以声明依赖其他插件,支持版本范围
- `claude plugin validate .` 检查格式;mod 有自己的测试框架,不用登录也能测

## 插件评测(和基准测试有关)
- `claude plugin eval`:每个用例是"一段提示 + 若干评分器"。默认跑 3 次,并且自动和**不装插件**的对照组比较
- 评分器可以用正则匹配回复、检查有没有调用某个工具、检查生成的文件,或让另一个模型按标准打分
- 每次运行都是一个新的、隔离的非交互会话,用 Lily 的账号额度
- 适合测"lyfusion 有没有让结果变好、用量变少";但长任务 × 3 次 × 2 组,额度消耗大。文档里提到它可能还在抢先体验阶段

## 规则和政策
### 允许的
- 自己写插件、建自己的市场(比如 MuraBot 的 GitHub 仓库)、自己安装使用,都不需要审核
- 插件里的 hooks、mods 调模型(`$.model.complete`)、monitors 都是 Claude Code 的官方功能,用的是会话本身的登录,计入 Lily 自己的套餐

### 不允许或要小心的
- **订阅登录只能用于 Claude Code 和 Anthropic 自家应用的正常使用。** 不能把订阅的登录凭据或令牌拿去给别的工具用,也不能收集、保存或转发它们(Claude Code 法律与合规页)
- **Consumer Terms 禁止用脚本、机器人等自动化方式访问服务**,除非用 API key 或官方明确允许。插件里的官方功能属于"明确允许";自己写脚本在 Claude Code 之外驱动 Claude 不属于
- **套餐额度是按"普通的个人使用"设计的。** mod 可以用定时器和 `$.prompt.submit` 自动发起回合,但设计上不要做成自己循环、无人值守的样子。这和 Lily 的规则一致:每个 Claude 回合都应该由 Lily 发起,或由明确的事件触发(比如 Codex 跑完了)
- **名字和标识。** 不能用 Claude、Claude Code、Anthropic 的名字或 logo 当产品名,也不能暗示是官方出品。"lyfusion" 没问题;说明里写"用于 Claude Code"这类如实描述可以
- **插件以用户的权限运行**,能读写文件、启动进程、联网。我们自己定的限制(不读 Claude 的记录、不读 Codex 的 auth.json)要写进代码里守住
- 要上架 Anthropic 的目录,需要付费套餐和审核,而且主要面向 claude.ai 和 Cowork。自用不需要上架
- 没查 OpenAI 对 Codex CLI 的条款。lyfusion 调 Codex 和现在一样,是 Lily 在本机用自己的账号

## 和现有规则的冲突(Lily 2026-11-06 同意按下面的建议办)
- Lily 的规则是"脚本不能读 Claude 的记录(`~/.claude/` 等)"。但插件本身就装在 `~/.claude/plugins/cache/` 里,`${CLAUDE_PLUGIN_DATA}` 也在 `~/.claude/plugins/data/` 下
- 建议:插件只运行自己安装目录里的代码(这一步由 Claude Code 完成);状态和台账照旧放在项目文件夹;不用 `${CLAUDE_PLUGIN_DATA}`;除此之外 `~/.claude/` 一律不读
- 落地:做插件时,把 LiEC 模板和各项目 CLAUDE.md、AGENTS.md 里"不读取 Claude 的配置……"那一行补上这个例外(LiEC 行数预算届时另算)

## 插件能解决现在的哪些问题
| 现在的问题 | 插件的做法 |
|---|---|
| 规则靠文字提醒,文档有行数预算,lead 还是会漏步骤 | hooks 和 mod 在关键节点自动检查和拦截 |
| 固定流程约 15 次调用(fusion-bench 的结论),短任务省不出来 | 固定步骤改成 mod 的 `/命令` 或 MCP 工具,不占 lead 的回合 |
| 派工脚本复制到每个项目,HEX 停在 v4.1,迁移要写说明 | 从自己的市场安装,`/plugin` 更新,版本号统一 |
| lead 等 Codex 时只能干等 | monitor 在 Codex 结束时通知 |
| 看不到助手在做什么 | mod 面板实时显示 |
| 和 LiEC 绑在一起 | 拆成两个插件,lyfusion 声明可选依赖或完全独立 |

## 还没确认的
- Codex 的 `exec --json` 事件流能不能直接给 monitor 用,要实测
- mod 的 `$.process.spawn` 在 Windows 上跑 PowerShell 和 Codex 的表现
- 插件评测在 Lily 的账号上能不能用
