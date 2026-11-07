# 基准测试调研(2026-11-06)

> 为 v5 准备:用外部基准测试比较 v4.2 和 v5。Lily 选定了 5 个 Terminal-Bench 任务,怎么跑还没定。
> 这份笔记供以后直接用,不用重新查。

## 数据来源
- 跑分页:Terminal-Bench 4.0.0 · Opus 5.5 / Claude Code · reasoning effort max
  https://hub.harborframework.com/jobs/96ad98a5-70e6-5e7b-bd1e-67eecfbc644c?tab=results
- 共 66 个任务,每个跑 5 次(`-k 5`),合计 330 次。按 API 计费,全程无人值守。
- 任务说明页:`https://hub.harborframework.com/tasks/terminal-bench/<任务名>`
  - README 里有类别、标签、人类专家估时、难点说明;Files 标签里有环境和评分脚本
  - 浏览器面板在后台时页面会卡在"Loading task details…",截一张图就能加载出来
- 运行说明:https://www.tbench.ai/run ;harbor 文档:https://docs.harborframework.com(每页加 `.md` 可取原文)

## 选定的 5 个任务(Lily 2026-11-06 定)
通过率是 5 次里通过的比例;时长取中位数;花费取平均。

| 任务 | 方向 | Opus 通过率 | Opus 时长 | 每次花费 | 专家估时 | 内容 |
|---|---|---|---|---|---|---|
| react-lead-form | 前端 | 4/5 | 51 分 | $12.2 | 5 小时 | 修 React + TypeScript 表单和提交流程:校验、数据规范化、写入 CRM 前的记录核对 |
| nextjs-performance | 网页前后端 | 3/5 | 78 分 | $13.2 | 3 小时 | Next.js 后台提速:并行服务端等待、延后加载 JS、日志移出响应路径 |
| mvcc-lsm-compaction | 后端/数据库 | 5/5 | 32 分 | $3.4 | 4 小时 | 修存储引擎的并发可见性错误 |
| freecad-spring-clip | 建模 | 5/5 | 25 分 | $5.0 | 2 小时 | 按文字规格用 FreeCAD 做参数化零件,改尺寸后重建 |
| embedding-drift-monitor | 软件调试 | 5/5 | 62 分 | $8.5 | 5 小时 | 漂移监控程序里 6 个互相牵连的错误 |

备选:
- payments-pipeline-fix:后端 Kafka 冷启动。5/5,128 分,$29.5;5 次里有 1 次评分文件丢失
- html-js-filter:XSS 过滤器(防御性)。3/5,55 分,$21.6
- freecad-platform-drawing:看工程图建模。5/5,16 分,$2.7;助手要能看图

选题理由:
- 任务要大到值得分工。专家估时 2~5 小时,Opus 只要 25~78 分钟,属中低难度
- 3/5、4/5 的题测质量会不会降;5/5 的题没有提分空间,测通过率不变时 lead 能省多少
- 都有自动评分

没选的:
- 游戏:表里没有。最接近的 retro-console-soc(Verilog 复古游戏机)专家估时 10 小时,太难
- Opus 0/5、1/5 的题(如 session-window-debug、wal-recovery-ordering):两边都失败,比不出差别
- 要 GPU(jax-speedrun-gpu)、要图形界面(legacy-utility-triage)、运营和行业类(heat-pump-warranty、intrastat-meldung)

## 全部 66 个任务的数据
格式:任务|通过率(5 次平均)|时长中位数(分)|平均花费

```
atrx-vep-crispr|0.60|23|$4.4        batched-eval-parity|1.00|38|$9.1
biped-contact-dynamics|0.80|158|$24.4  bun-sourcemap-leak|0.00|34|$6.5
cad-model|1.00|18|$2.6              cargo-flight-dispatch|0.00|36|$7.6
coq-block-bound|1.00|16|$2.5        ctr-optimization|0.80|291|$24.9
cumulative-layout-shift|1.00|167|$31.8  data-anonymization|0.20|102|$14.7
distributed-dedup|0.40|272|$42.8    embedding-drift-monitor|1.00|62|$8.5
fin-saccr-rwa|1.00|35|$6.0          foodstuff-beta-activity|0.00|43|$7.7
formal-crypto|0.60|74|$18.2         fp8-rmsnorm-gemm|1.00|82|$19.7
freecad-impeller|0.00|29|$5.6       freecad-platform-drawing|1.00|16|$2.7
freecad-spring-clip|1.00|25|$5.0    freight-dispatch-shift|0.00|128|$22.8
glycan-ms2-elucidation|0.00|29|$4.6 gsea-proteomics|1.00|22|$3.3
heat-pump-warranty|0.60|45|$11.0    hof-topology-interpenetration|1.00|23|$3.0
html-js-filter|0.60|55|$21.6        interleaved-vigenere|1.00|118|$15.7
intrastat-meldung|0.40|18|$4.9      jax-speedrun-gpu|1.00|382|$32.8
ks-solver-cpp|0.00|79|$11.6         kv-live-surgery|0.40|64|$10.9
lake-temp-glm|0.60|174|$26.6        layout-config-recreation2|1.00|15|$2.3
layout-config-recreation|1.00|217|$45.0  legacy-utility-triage|1.00|52|$11.6
live-database-cutover|0.60|143|$33.1  math-eval-grader|1.00|78|$23.6
medical-claims-processing|0.00|35|$9.3  mp-checkpoint-consolidation|1.00|24|$3.4
music-harmony|0.00|62|$14.8         mvcc-lsm-compaction|1.00|32|$3.4
nextjs-performance|0.60|78|$13.2    ontology-kg-querying|0.00|58|$17.5
payments-pipeline-fix|1.00|128|$29.5  photonic-waveguide-routing|0.20|84|$14.3
pretrain-shard-corruption|1.00|36|$4.5  production-planning|1.00|43|$7.3
protein-autointerp-disulfide|0.00|22|$3.3  react-lead-form|0.80|51|$12.2
retro-console-soc|1.00|132|$28.9    risk-scorer-replay|1.00|39|$7.6
roy-polymorph-cn|1.00|10|$1.9       rs-archive-clone|1.00|111|$24.1
satb-audio-transcription|1.00|24|$3.4  session-window-debug|0.20|56|$8.7
sglang-qwen-burst|0.60|98|$27.5     shadow-relay|0.60|9|$1.1
sound-change-cascade|1.00|59|$6.5   takens-embedding-lean|1.00|59|$22.8
telecom-entity-resolution|1.00|100|$16.8  uefi-bootkit|0.80|70|$14.5
vba-userform-port|0.00|92|$30.5     vf2-speedup-networkx|1.00|134|$32.9
vllm-deepseek-streaming|0.00|82|$17.5  vpp-loss-divergence|0.60|53|$12.2
wal-recovery-ordering|0.00|41|$8.4  wdm-design|1.00|190|$16.5
```

## 官方跑法和它的问题
- 安装:`uv tool install harbor`。默认沙箱是本机 Docker(`-e docker`);官网示例的 `modal` 是云沙箱,要账号
- 运行:`harbor run -t terminal-bench/<任务名> -e docker -a claude-code -m anthropic/claude-opus-5-5`
- `-a claude-code` 要在环境变量里给 `ANTHROPIC_API_KEY` 或 `CLAUDE_CODE_OAUTH_TOKEN`,Claude Code 在容器里无人值守跑完
- 和规则冲突:Claude 在桌面端和 Claude Code 之外运行;要经手密钥;也接不进 lyfusion 的 lead + Codex 分工
- harbor 官方没说支持 Windows,装进 WSL 的 Ubuntu 最稳
- 其他有用的命令:`harbor download <任务>` 下载任务;`harbor view jobs` 看结果;`harbor trial handoff` 把一次运行接回本地 Claude Code

## 想到的跑法(还没定)
1. 写一个"等人"agent(推荐):harbor 的自定义 agent(`BaseAgent`,用 `-a 模块:类名` 指定)不调用任何模型,搭好容器后把任务说明和容器编号写进文件,然后等。Lily 在 Claude Code 里开 lead 会话照常用 lyfusion;做完放一个完成标记,harbor 用自带评分程序打分。合规、官方评分、结果格式和 Opus 表一致
2. `harbor download` 下载任务,自己搭容器、手动跑评分:不写代码,但每题手动,容易出错
3. 官方 `-a claude-code`:最省事,但要给规则开例外,另付 API 费

比较口径(推荐):表里的 Opus 数据看通过率;花费要自己用同样方式跑一遍单独 Claude Code 来比。表里是 API 计费、max 强度、跑 5 次,我们是订阅额度、跑 1 次。

## 不用 Docker 的路
- fusion-bench(`C:\AI WithMe\fusion-bench`):已经在 Windows 上跑,隐藏测试 + `python hidden/grade.py`。问题是题太容易(Opus 9 题全满分)、太短(单独做 22~30 次调用,lyfusion 固定流程就要约 15 次)。要的是更长更难的题
- 把选好的任务搬到 Windows:任务本质是"起点仓库 + 说明 + 评分脚本",和 fusion-bench 一样。Python、Node 类的题很可能装好依赖就能跑;评分脚本用了 Linux 命令的要改。先在 Files 标签看每题的环境和评分脚本再判断
- 给 fusion-bench 出新长题:让 Codex 出 1~3 小时、多文件、模块牵连的题。自己可控,但没有外部数据对照
- Aider Polyglot:本地能跑,但每题几分钟,太短。SWE-bench 等基本都要 Docker 和 Linux

## Lily 电脑的情况(2026-11-06 查)
- WSL 没装;CPU 虚拟化已开;内存 31GB;C 盘剩 442GB;账号有管理员权限
- 装法:管理员 PowerShell 运行 `wsl --install` 后重启 → 装 Docker Desktop 勾"使用 WSL 2",Docker 账号登录可跳过 → `docker run hello-world` 验证
- Docker Desktop 对个人和小公司免费;超过 250 人或年收入超过 1000 万美元的公司要付费。系统是 Windows 企业版,如果是公司电脑要先看规定;有限制就在 WSL 里直接装 Docker Engine
- Docker 开着时 WSL 默认最多用一半内存

## 待 Lily 定
1. 跑法:等人 agent / 手动下载 / 官方 claude-code
2. 安装:Docker Desktop 由 Lily 装;harbor 装进用户目录(工作区外)要 Lily 同意
3. 比较口径:只用表里数据 / 再自己跑单独 Claude Code 对照
4. 或者不用 Docker:先看 5 个任务的 Files,判断哪些能搬到 Windows
