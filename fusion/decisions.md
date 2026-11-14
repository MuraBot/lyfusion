# 设计决定
> lead 直接编辑这个文件。每次派工,引擎把全文带给助手。只写所有任务都要守的决定。

## rc.1 全程
1. 引擎只用 Python 标准库和 sqlite,不加第三方依赖。测试用 pytest 和假 Codex(`tests/fake_codex.py`),不调用真 Codex、不联网
2. lead 看到的东西不随手改:使用说明(`views.lead_guide`,≤20 行)、4 个动作(explore、delegate、revise、accept)和它们的输出,只在任务明确要求时改。新功能藏在引擎里,lead 不多花调用
3. 设置分两处:`fusion/config.json`(项目的,进 git:test、lint、network、context_ratio 等)和 `fusion/local.json`(本机的,不进 git:开关、助手模型、按模型的设置、Codex 路径、Codex 环境)。按模型的设置都放 `sidekick.models.<模型>` 下,没登记的模型用默认值。读到旧格式或缺字段的文件不报错,用默认值
4. 用户改设置只走 `fusion-core config <动作>`(`/fusion` 技能和以后 Fusion 栏的面板都调它);`fusion-core status` 显示当前值。用户看到的文字用中文
5. 不读 `~/.claude/`、AppData 里 Claude 的文件夹、Codex 的 `auth.json`;引擎不解析 `~/.codex/config.toml`。启动 Codex 和检查命令前去掉 `CLAUDE*`、`ANTHROPIC*` 环境变量。Codex 不用绕过沙箱或审批的参数
6. 版本号保持 `5.0.0-aq.2`:不改 plugin.json、`__init__.py`、README 里的版本,lead 收尾时统一改
7. 已有测试都要继续通过。改了已有行为就同时改对应测试,并在报告里写明为什么
