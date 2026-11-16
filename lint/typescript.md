# TypeScript 规则(Fusion 栏 mod)

只有一个文件 `plugin/hooks/register.tsx`。本机没有 TypeScript 和 eslint,现成的检查是桌面端自带的 `claude.exe plugin validate plugin`(`v5/build_plugin.py` 打包前会跑，没过不出包)。

| # | 问题 | 出现记录 | 怎么接住 | 状态 |
|---|---|---|---|---|
| T1 | `atom({ plugin, key })` 的 plugin、key 没写成字符串字面量，整个 mod 不加载，也不报错 | rc.1 任务 6(反馈第 14 条),Lily 上传了两次才查出来 | `claude plugin validate` | 已生效 |
| T2 | mod 调引擎时没传项目目录，在桌面端的预备目录里跑 | rc.1 任务 7(toast "不在 git 仓库里") | 写成规则太窄;记在 `register.tsx` 的注释和 `design/v5.0.0-rc.md` | 只能提示 |
| T3 | mod 用定时器发起回合、读 `~/.claude` | Lily 的规则(政策),rc.1 没出现 | 自写检查：在 `plugin/hooks/` 的非注释行里搜 `$.clock` 和 `.claude` 路径(注释里本来就提到 `~/.claude`,不能算) | 待实现 |
