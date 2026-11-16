# 通用规则(跨语言)

| # | 问题 | 出现记录 | 怎么接住 | 状态 |
|---|---|---|---|---|
| C1 | 提交的文件里出现真实的 Windows 用户目录(`C:\Users\<用户名>\…`) | rc.1:`v5/progress.md` 记了桌面端预备目录的完整路径，推送前改写历史脱敏(2026-11-14) | 自写检查：扫描受 git 管理的文件，用户名在运行时从环境变量 `USERNAME` 取，不写进仓库 | 待实现 |
| C2 | 中文写成转义(`\uXXXX`,JSON 里 `ensure_ascii` 默认转义) | 见 `python.md` P1 | Python 见 P1;写 JSON 时用 `ensure_ascii=False`(引擎已经这样写) | 待实现 |
| C3 | 新加绕过检查的注释(`noqa`、`eslint-disable`、`@ts-ignore`) | WORK_RULES 里禁止(aq.2 H2 的意见);rc.1 没出现 | 只看新增行才能判断(老代码里本来就有 `# noqa: BLE001`),用引擎的 `forbidden` 规则 | 待实现 |
| C4 | 写文件时编码丢了,中文变成一串 `?` | rc.2 T10 第 1 轮(`design/v5.0.0-aq.md` 命令表新加的 `wait` 一行),用修改意见改回 | 自写检查:受 git 管理的文本文件里出现 3 个以上连续的 `?` 就报错(TypeScript 的 `??` 是正常运算符,所以从 3 个算起) | 待实现 |
